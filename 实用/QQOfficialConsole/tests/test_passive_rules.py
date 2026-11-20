"""2026-11-17 群消息被动回复规则：60 分钟有效期、5/50 次上限、群消息私聊回复。"""
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import OlivOS
import pytest
from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as sdk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from QQOfficialConsole import main, media, passive, roster, store, webui


@pytest.fixture
def console(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now = 1700000000
    monkeypatch.setattr(time, 'time', lambda: now)
    monkeypatch.setattr(webui, 'time', SimpleNamespace(time=lambda: now, monotonic=lambda: 100.0))
    monkeypatch.setattr(sdk, 'getTokenNow', lambda bot_info: 'local-token')
    bot = OlivOS.API.bot_info_T(id=int(uuid.uuid4().int % 10**12), platform_sdk='qqGuildv2_link',
                                platform_platform='qqGuild', platform_model='public')
    proc = SimpleNamespace(Proc_data={'bot_info_dict': {bot.hash: bot}}, log=lambda *args, **kwargs: None)
    database = store.Store(tmp_path / 'db')
    pool = passive.PassivePool(database)
    members = roster.Roster(database)
    images = media.MediaManager(tmp_path)
    bridge = webui.Bridge(database, pool, members, images, proc)
    bridge._closed = threading.Event()
    monkeypatch.setattr(main, '_state', (database, pool, members, images, bridge))
    state = SimpleNamespace(bot=bot, proc=proc, store=database, pool=pool, roster=members,
                            bridge=bridge, calls=[], role='admin', now=now)

    def request(method, url, **kwargs):
        parts = urlsplit(url)
        state.calls.append((method, parts.path))
        if parts.path.endswith('/bot_state'):
            response = {'member_role': state.role, 'allow_proactive_msg': True}
        else:
            response = {'id': 'sent'}
        return SimpleNamespace(status_code=200, text=json.dumps(response), headers={})

    monkeypatch.setattr(sdk.req, 'request', request)
    yield state
    bridge.close()
    database.close()


def call(c, event_name, **payload):
    return c.bridge.handle('QQOfficialConsole_' + event_name, {
        'bot_hash': c.bot.hash, 'chat_type': 'qq_group', 'chat_id': 'group', **payload,
    })


def incoming(c, platform_id='msg-1', sender='member-1'):
    return c.store.add_message(
        c.bot.hash,
        'qq_group',
        'group',
        {
            'direction': 'in',
            'platform_message_id': platform_id,
            'sender_id': sender,
            'sender_name': '小明',
            'msg_kind': 'text',
            'content_text': '你好',
            'content_json': {'text': '你好'},
            'created_at': c.now,
        },
        token={'id_type': 'msg_id', 'id_value': platform_id, 'created_at': c.now},
    )


def token_row(c, chat_type, chat_id, value):
    with c.store.session(c.bot.hash, chat_type, chat_id) as db:
        row = db.execute(
            'SELECT * FROM passive_tokens WHERE id_type=? AND id_value=?', ('msg_id', str(value))
        ).fetchone()
        return dict(row) if row else None


def test_group_token_window_is_sixty_minutes(console):
    console.pool.add(console.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    row = token_row(console, 'qq_group', 'group', 'token')
    # 平台 2026-11-17 起把群聊被动回复有效期从 5 分钟延长到 60 分钟。
    assert row['expire_at'] - row['created_at'] == 3600


def test_group_token_counts_against_role_limit(console):
    c = console
    c.pool.add(c.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    for _ in range(5):
        assert c.pool.mark_used(c.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    # 普通成员只能回 5 次；机器人是群主/管理员时上限 50 次。
    assert c.pool.candidates(c.bot.hash, 'qq_group', 'group', limit=5) == []
    assert [row['id_value'] for row in c.pool.candidates(c.bot.hash, 'qq_group', 'group', limit=50)] == ['token']
    assert c.pool.status(c.bot.hash, 'qq_group', 'group', limit=5) is None
    assert c.pool.status(c.bot.hash, 'qq_group', 'group', limit=50)['max_count'] == 50


def test_send_stops_after_five_replies_for_normal_member(console):
    c = console
    c.role = 'member'
    c.store.upsert_chat(c.bot.hash, 'qq_group', 'group', self_role='member', role_updated_at=c.now)
    c.pool.add(c.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    for _ in range(5):
        c.pool.mark_used(c.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    result = call(c, 'Send', kind='text', text='hello')
    # 5 次用完就改走主动消息，不会拿同一条凭据去撞平台的次数上限。
    assert result['ok'] and result['channel'] == 'active'


def test_import_from_copies_used_count_and_expiry(console):
    c = console
    c.pool.add(c.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    c.pool.mark_used(c.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    c.pool.mark_used(c.bot.hash, 'qq_group', 'group', 'msg_id', 'token')

    c.pool.import_from(c.bot.hash, 'qq_private', 'member-1', 'qq_group', 'group', 'msg_id', 'token')

    source = token_row(c, 'qq_group', 'group', 'token')
    copied = token_row(c, 'qq_private', 'member-1', 'token')
    # 同一个 msg_id 在群里和私聊共用次数，复制时必须带上已用次数与到期时间。
    assert copied['used_count'] == source['used_count'] == 2
    assert copied['expire_at'] == source['expire_at']


def test_private_reply_registers_group_credential_for_sender(console):
    c = console
    local_id = incoming(c)
    c.pool.mark_used(c.bot.hash, 'qq_group', 'group', 'msg_id', 'msg-1')

    result = call(c, 'PrivateReply', message_id=local_id)

    assert result['ok']
    assert (result['chat_type'], result['chat_id']) == ('qq_private', 'member-1')
    assert c.store.get_chat(c.bot.hash, 'qq_private', 'member-1')['display_name'] == '小明'
    copied = token_row(c, 'qq_private', 'member-1', 'msg-1')
    assert copied['used_count'] == 1
    assert [(method, path) for method, path in c.calls] == [('GET', '/v2/groups/group/bot_state')]


def test_private_reply_rejects_outgoing_message(console):
    c = console
    local_id = c.store.add_message(
        c.bot.hash,
        'qq_group',
        'group',
        {
            'direction': 'out',
            'platform_message_id': 'out-1',
            'sender_name': '机器人',
            'msg_kind': 'text',
            'content_text': 'hi',
            'content_json': {'text': 'hi'},
            'created_at': c.now,
        },
        unread=False,
    )

    result = call(c, 'PrivateReply', message_id=local_id)

    assert not result['ok'] and result['keyword'] == '消息不存在'


def test_private_reply_requires_group_chat(console):
    result = console.bridge.handle('QQOfficialConsole_PrivateReply', {
        'bot_hash': console.bot.hash, 'chat_type': 'qq_private', 'chat_id': 'member-1',
        'message_id': 1,
    })
    assert not result['ok'] and result['keyword'] == '仅群消息支持私聊回复'
