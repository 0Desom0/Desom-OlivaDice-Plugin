"""群名获取队列：FIFO、限流退避、永久失败、手动刷新与机器人 openid 记录。"""
import importlib
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import OlivOS
import pytest
from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as sdk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def console(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in list(sys.modules):
        if name == 'QQOfficialConsole' or name.startswith('QQOfficialConsole.'):
            monkeypatch.delitem(sys.modules, name)
    main = importlib.import_module('QQOfficialConsole.main')
    from QQOfficialConsole import media, passive, roster, store, webui
    clock = [1700000000]
    ticks = [100.0]
    monkeypatch.setattr(time, 'time', lambda: clock[0])
    monkeypatch.setattr(webui, 'time', SimpleNamespace(time=lambda: clock[0], monotonic=lambda: ticks[0]))
    monkeypatch.setattr(sdk, 'getTokenNow', lambda bot_info: 'local-token')
    bot = OlivOS.API.bot_info_T(id=int(uuid.uuid4().int % 10**12), platform_sdk='qqGuildv2_link',
                                platform_platform='qqGuild', platform_model='public')
    proc = SimpleNamespace(Proc_data={'bot_info_dict': {bot.hash: bot}}, log=lambda *args, **kwargs: None)
    database = store.Store(tmp_path / 'db')
    pool = passive.PassivePool(database)
    members = roster.Roster(database)
    images = media.MediaManager(tmp_path)
    state = SimpleNamespace(bot=bot, proc=proc, store=database, calls=[], ticks=ticks, clock=clock,
                            group_name='测试群', info_failure={})

    def request(method, url, **kwargs):
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        state.calls.append((method, parts.path))
        if parts.path.endswith('/bot_state'):
            status, body = state.info_failure.get(
                parts.path, (200, {'member_role': 'member', 'allow_proactive_msg': False,
                                   'member_openid': 'BOTOPENID123'})
            )
        elif parts.path.endswith('/info'):
            status, body = state.info_failure.get(parts.path, (200, {'group_name': state.group_name}))
        else:
            raise AssertionError(f'unexpected QQ HTTP request: {method} {url}')
        return SimpleNamespace(status_code=status, text=json.dumps(body), headers={})

    monkeypatch.setattr(sdk.req, 'request', request)
    bridge = webui.Bridge(database, pool, members, images, proc)
    state.bridge = bridge
    state.main = main
    yield state
    bridge.close()
    database.close()


def call(c, event_name, **payload):
    return c.bridge.handle('QQOfficialConsole_' + event_name, {
        'bot_hash': c.bot.hash, 'chat_type': 'qq_group', 'chat_id': payload.pop('chat_id', 'group'), **payload,
    })


def test_queue_is_fifo_by_join_record_time(console):
    c = console
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g1')
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g2')
    c.store.enqueue_group_info(c.bot.hash, 'g2', enqueued_at=200)
    c.store.enqueue_group_info(c.bot.hash, 'g1', enqueued_at=100)
    c.store.enqueue_group_info(c.bot.hash, 'g1', enqueued_at=999)  # 重复入队不改变顺序
    c.bridge.pump_group_info(limit=10)
    assert [path for _, path in c.calls] == ['/v2/groups/g1/info', '/v2/groups/g2/info']
    assert c.store.get_chat(c.bot.hash, 'qq_group', 'g1')['display_name'] == '测试群'
    assert c.store.get_chat(c.bot.hash, 'qq_group', 'g2')['display_name'] == '测试群'
    assert c.store.group_info_status(c.bot.hash) == {}


def test_rate_limited_info_retries_later_and_keeps_queue(console):
    c = console
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g1')
    c.store.enqueue_group_info(c.bot.hash, 'g1')
    c.info_failure['/v2/groups/g1/info'] = (429, {'code': 40034100, 'message': '频率限制'})
    c.bridge.pump_group_info(limit=10)
    assert c.store.get_chat(c.bot.hash, 'qq_group', 'g1')['display_name'] is None
    job = c.store.group_info_job(c.bot.hash, 'g1')
    assert job['status'] == 'pending' and job['next_at'] >= int(time.time()) + 60
    assert c.store.group_info_status(c.bot.hash) == {'g1': 'queued'}
    # 冷却未到不重试
    c.bridge.pump_group_info(limit=10)
    assert len(c.calls) == 1
    # 冷却到了继续
    c.ticks[0] += 120
    c.clock[0] += 120
    c.info_failure.clear()
    c.bridge.pump_group_info(limit=10)
    assert c.store.get_chat(c.bot.hash, 'qq_group', 'g1')['display_name'] == '测试群'


def test_permanent_failure_marks_job_failed(console):
    c = console
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g1')
    c.store.enqueue_group_info(c.bot.hash, 'g1')
    c.info_failure['/v2/groups/g1/info'] = (400, {'code': 11255, 'message': '资源不存在'})
    c.bridge.pump_group_info(limit=10)
    job = c.store.group_info_job(c.bot.hash, 'g1')
    assert job['status'] == 'failed' and job['error_code'] == 11255
    c.bridge.pump_group_info(limit=10)
    assert len(c.calls) == 1  # 不再重试


def test_attempts_exhausted_marks_failed(console):
    c = console
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g1')
    c.store.enqueue_group_info(c.bot.hash, 'g1')
    c.info_failure['/v2/groups/g1/info'] = (500, {'code': 50055001})
    for _ in range(5):
        c.ticks[0] += 600
        c.clock[0] += 600
        c.bridge.pump_group_info(limit=10)
    assert c.store.group_info_job(c.bot.hash, 'g1')['status'] == 'failed'


def test_manual_refresh_updates_name_and_clears_queue(console):
    c = console
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g1', display_name='旧名字')
    c.store.enqueue_group_info(c.bot.hash, 'g1')
    c.group_name = '新名字'
    result = call(c, 'RefreshGroupName', chat_id='g1')
    assert result['ok'] and result['chat']['display_name'] == '新名字'
    assert c.store.group_info_job(c.bot.hash, 'g1')['status'] == 'done'
    # 备注不受影响
    call(c, 'SetRemark', chat_id='g1', remark='备注名')
    chat = c.store.get_chat(c.bot.hash, 'qq_group', 'g1')
    assert chat['remark'] == '备注名' and chat['display_name'] == '新名字'


def test_group_add_robot_event_enqueues_group_name(console, monkeypatch):
    c = console
    event = SimpleNamespace(
        platform={'sdk': 'qqGuildv2_link'}, bot_info=c.bot,
        data=SimpleNamespace(group_id='g-new', user_id='', sender={}, extend={
            'flag_from_qq': True, 'event_id': 'ev-1',
            'qq_event_data': {'timestamp': 1700000000, 'group_openid': 'g-new'},
        }),
        sdk_event=SimpleNamespace(payload=SimpleNamespace(data=SimpleNamespace(t='GROUP_ADD_ROBOT'))))
    from QQOfficialConsole import passive as passive_mod
    pool = passive_mod.PassivePool(c.store)
    monkeypatch.setattr(c.main, '_initialise', lambda proc: (c.store, pool, None, None, c.bridge))
    c.main.Event.group_member_increase(event, c.proc)
    # 入队后唤醒 worker，等待其把群名取回（最多 5 秒）。
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if (c.store.get_chat(c.bot.hash, 'qq_group', 'g-new') or {}).get('display_name') == '测试群':
            break
        time.sleep(0.05)
    assert c.store.get_chat(c.bot.hash, 'qq_group', 'g-new')['display_name'] == '测试群'


def test_backfill_enqueues_existing_groups_without_name(console):
    c = console
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'old1')
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'old2', display_name='已有名字')
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'left1')
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'left1', left_group=1)
    c.store.upsert_chat(c.bot.hash, 'qq_private', 'p1')
    c.bridge.backfill_group_names()
    assert c.store.group_info_job(c.bot.hash, 'old1')['status'] == 'pending'
    assert c.store.group_info_job(c.bot.hash, 'old2') is None
    assert c.store.group_info_job(c.bot.hash, 'left1') is None


def test_bot_openid_recorded_from_bot_state(console):
    c = console
    result = call(c, 'RefreshRole')
    assert result['ok'] and result['chat']['bot_openid'] == 'BOTOPENID123'
    chats = call(c, 'ListChats')['chats']
    assert chats[0]['bot_openid'] == 'BOTOPENID123'


def test_worker_wakes_on_enqueue(console):
    c = console
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g1')
    done = threading.Event()
    original = c.bridge.fetch_group_name

    def fetch(bot_hash, group_id):
        result = original(bot_hash, group_id)
        done.set()
        return result

    c.bridge.fetch_group_name = fetch
    c.store.enqueue_group_info(c.bot.hash, 'g1')
    c.bridge.wake_group_info()
    assert done.wait(5), 'group info worker did not process the queued job'
    assert c.store.get_chat(c.bot.hash, 'qq_group', 'g1')['display_name'] == '测试群'


def test_fifo_does_not_skip_cooling_head(console):
    c = console
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g1')
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g2')
    c.store.enqueue_group_info(c.bot.hash, 'g1', enqueued_at=100)
    c.store.enqueue_group_info(c.bot.hash, 'g2', enqueued_at=200)
    c.info_failure['/v2/groups/g1/info'] = (429, {'code': 40034100, 'message': '频率限制'})
    c.bridge.pump_group_info(limit=10)
    assert [path for _, path in c.calls] == ['/v2/groups/g1/info']
    assert c.store.get_chat(c.bot.hash, 'qq_group', 'g2')['display_name'] is None
    c.bridge.pump_group_info(limit=10)
    assert len(c.calls) == 1
    c.clock[0] += 120
    c.info_failure.clear()
    c.bridge.pump_group_info(limit=10)
    assert [path for _, path in c.calls] == [
        '/v2/groups/g1/info', '/v2/groups/g1/info', '/v2/groups/g2/info',
    ]


def test_recover_running_jobs_then_process(console):
    c = console
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'g1')
    c.store.enqueue_group_info(c.bot.hash, 'g1')
    with c.store.meta(c.bot.hash) as db:
        db.execute("UPDATE group_info_jobs SET status='running' WHERE group_openid='g1'")
    c.store.recover_group_info_jobs(c.bot.hash)
    c.bridge.pump_group_info(limit=10)
    assert c.store.get_chat(c.bot.hash, 'qq_group', 'g1')['display_name'] == '测试群'


def test_failed_role_refresh_keeps_cached_role(console):
    c = console
    first = call(c, 'RefreshRole')
    assert first['ok'] and first['chat']['self_role'] == 'member'
    c.info_failure['/v2/groups/group/bot_state'] = (500, {'code': 50055001})
    again = call(c, 'RefreshRole')
    assert not again['ok']
    assert c.store.get_chat(c.bot.hash, 'qq_group', 'group')['self_role'] == 'member'


def test_add_chat_enqueues_group_name(console):
    c = console
    result = call(c, 'AddChat', chat_id='g-add')
    assert result['ok']
    job = c.store.group_info_job(c.bot.hash, 'g-add')
    assert job and job['status'] in ('pending', 'running', 'done')

