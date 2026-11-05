"""真实 Bridge 和 OlivOS SDK 行为测试；QQ HTTP 在进程内替身，不连接平台。"""
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import OlivOS
import pytest
from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as sdk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from QQOfficialConsole import main, media, passive, roster, store, webui


@pytest.fixture
def console(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    now = 1700000000
    ticks = [100.0]
    sleeps = []

    monkeypatch.setattr(time, 'time', lambda: now)
    monkeypatch.setattr(webui, 'time', SimpleNamespace(time=lambda: now, monotonic=lambda: ticks[0]))
    monkeypatch.setattr(sdk, 'getTokenNow', lambda bot_info: 'local-token')
    bot = OlivOS.API.bot_info_T(id=int(uuid.uuid4().int % 10**12), platform_sdk='qqGuildv2_link',
                                platform_platform='qqGuild', platform_model='public')
    proc = SimpleNamespace(Proc_data={'bot_info_dict': {bot.hash: bot}}, log=lambda *args, **kwargs: None)
    database = store.Store(tmp_path / 'db')
    pool = passive.PassivePool(database)
    members = roster.Roster(database)
    images = media.MediaManager(tmp_path)
    bridge = webui.Bridge(database, pool, members, images, proc)
    class DeterministicCloseEvent:
        def __init__(self):
            self.event = threading.Event()

        def set(self):
            self.event.set()

        def is_set(self):
            return self.event.is_set()

        def wait(self, seconds):
            if seconds > 0:
                sleeps.append(seconds)
                ticks[0] += seconds
            return self.event.is_set()

    bridge._closed = DeterministicCloseEvent()
    monkeypatch.setattr(main, '_state', (database, pool, members, images, bridge))
    state = SimpleNamespace(bot=bot, proc=proc, store=database, pool=pool, roster=members,
                            bridge=bridge, calls=[], role='admin', pages={}, failure={}, sleeps=sleeps, now=now)

    def request(method, url, **kwargs):
        parts = urlsplit(url)
        body = kwargs.get('data')
        body = json.loads(body) if isinstance(body, str) else body
        query = parse_qs(parts.query)
        state.calls.append((method, parts.path, query, body))
        if parts.path.endswith('/bot_state'):
            response = {'member_role': state.role, 'allow_proactive_msg': True}
        elif parts.path.endswith('/join_request_list'):
            cursor = query.get('cursor', [None])[0]
            response = state.pages[cursor]
        elif '/approval_join_request/' in parts.path or method == 'DELETE':
            response = {}
        elif parts.path.endswith('/messages'):
            response = {'id': 'sent-join'}
        else:
            raise AssertionError(f'unexpected QQ HTTP request: {method} {url}')
        status, response = state.failure.get(parts.path, (200, response))
        return SimpleNamespace(status_code=status, text=json.dumps(response), headers={})

    monkeypatch.setattr(sdk.req, 'request', request)
    yield state
    bridge.close()
    database.close()


def call(c, event_name, **payload):
    return c.bridge.handle('QQOfficialConsole_' + event_name, {
        'bot_hash': c.bot.hash, 'chat_type': 'qq_group', 'chat_id': 'group', **payload,
    })


def refresh_requests(c):
    started = call(c, 'JoinRequestList', refresh=True)
    assert started['ok'] and started['refreshing']
    with c.bridge._jobs_lock:
        thread = c.bridge._jobs[(c.bot.hash, 'group')]['thread']
    thread.join(timeout=5)
    assert not thread.is_alive(), '入群申请刷新没有在预期时间内结束'
    return call(c, 'JoinRequestList')


def entry(ident, member, stamp='2023-11-14T22:13:20Z'):
    return {'join_request_id': ident, 'member_openid': member, 'username': member,
            'apply_at': stamp, 'verify_info': {'answer': ident}}


def requests_by_id(c):
    return {row['join_request_id']: row for row in c.roster.list_requests(c.bot.hash, 'group', status=None)}


@pytest.mark.parametrize('action,params', [
    ('ListMembers', {'refresh': True}),
    ('Admin', {'action': 'restrict_query'}),
    ('Admin', {'action': 'restrict_set', 'member_openid': 'someone', 'duration': 60}),
    ('JoinRequestList', {'refresh': True}),
    ('JoinRequestAct', {'op': 'approve', 'join_request_id': 'r1', 'member_openid': 'u1'}),
])
def test_non_admin_management_is_denied_before_privileged_http(console, action, params):
    console.role = 'member'
    result = refresh_requests(console) if action == 'JoinRequestList' else call(console, action, **params)
    assert not result['ok'] and result['keyword'] == '无管理员权限'
    assert [(method, path) for method, path, _, _ in console.calls] == [('GET', '/v2/groups/group/bot_state')]

def test_missing_live_role_does_not_authorize_cached_admin(console):
    console.store.upsert_chat(console.bot.hash, 'qq_group', 'group', self_role='admin')
    console.role = None
    result = call(console, 'Admin', action='restrict_query')
    assert not result['ok']
    assert [(method, path) for method, path, _, _ in console.calls] == [('GET', '/v2/groups/group/bot_state')]
    assert console.store.get_chat(console.bot.hash, 'qq_group', 'group')['self_role'] == 'admin'


def test_non_admin_can_read_cached_members(console):
    console.role = 'member'
    console.roster.upsert_member(console.bot.hash, 'qq_group', 'group', 'u1', 'Alice')
    result = call(console, 'ListMembers')
    assert result['ok'] and [member['member_openid'] for member in result['members']] == ['u1']
    assert console.calls == []



def test_refresh_returns_while_authorization_is_in_flight(console, monkeypatch):
    c = console
    c.pages = {None: {'list': [entry('r1', 'u1')]}}
    c.roster.refresh_requests(c.bot.hash, 'group', [entry('old', 'u-old')])
    entered, release = threading.Event(), threading.Event()
    original = sdk.req.request

    def gated_request(method, url, **kwargs):
        if urlsplit(url).path.endswith('/bot_state'):
            entered.set()
            if not release.wait(5):
                raise AssertionError('等待授权门超时')
        return original(method, url, **kwargs)

    monkeypatch.setattr(sdk.req, 'request', gated_request)
    try:
        started = call(c, 'JoinRequestList', refresh=True)
        assert started['ok'] and started['refreshing'] and started['requests'] == []
        assert entered.wait(5)
        pending = call(c, 'JoinRequestList')
        assert pending['ok'] and pending['refreshing'] and pending['requests'] == []
        again = call(c, 'JoinRequestList', refresh=True)
        assert again['ok'] and again['refreshing'] and again['requests'] == []
        with c.bridge._jobs_lock:
            assert len(c.bridge._jobs) == 1
            thread = c.bridge._jobs[(c.bot.hash, 'group')]['thread']
    finally:
        release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    result = call(c, 'JoinRequestList')
    assert result['ok'] and not result['refreshing']
    assert [row['join_request_id'] for row in result['requests']] == ['r1']
    assert requests_by_id(c)['old']['status'] == 'gone'
    assert len([path for _, path, _, _ in c.calls if path.endswith('/bot_state')]) == 1


def test_join_request_pages_and_approval_status(console):
    c = console
    c.pages = {None: {'list': [entry('r1', 'u1')], 'next_cursor': 'page-2'},
               'page-2': {'list': [entry('r2', 'u2')], 'next_cursor': None}}
    result = refresh_requests(c)
    assert result['ok'] and not result['refreshing'] and not result['truncated']
    assert {r['join_request_id'] for r in result['requests']} == {'r1', 'r2'}
    page_calls = [(query, method) for method, path, query, _ in c.calls if path.endswith('/join_request_list')]
    assert page_calls == [({'limit': ['50']}, 'GET'), ({'cursor': ['page-2'], 'limit': ['50']}, 'GET')]
    assert c.sleeps == [2.0]
    rows = requests_by_id(c)
    assert rows['r1']['apply_at'] == c.now
    assert json.loads(rows['r2']['verify_json']) == {'answer': 'r2'}

    approved = call(c, 'JoinRequestAct', op='approve', join_request_id='r1', member_openid='u1')
    declined = call(c, 'JoinRequestAct', op='decline', join_request_id='r2', member_openid='u2',
                    reject_reason='not eligible', add_to_member_blacklist=True)
    assert approved['ok'] and declined['ok']
    posts = [(path, body) for method, path, _, body in c.calls if method == 'POST']
    assert posts == [('/v2/groups/group/approval_join_request/u1',
                      {'op': 'approve', 'join_request_id': 'r1', 'add_to_member_blacklist': False}),
                     ('/v2/groups/group/approval_join_request/u2',
                      {'op': 'decline', 'join_request_id': 'r2', 'reject_reason': 'not eligible',
                       'add_to_member_blacklist': True})]
    rows = requests_by_id(c)
    assert rows['r1']['status'] == 'approved' and rows['r2']['status'] == 'declined'
    assert call(c, 'JoinRequestList')['requests'] == []
    repeat = call(c, 'JoinRequestAct', op='approve', join_request_id='r1', member_openid='u1')
    assert not repeat['ok'] and repeat['keyword'] == '申请已失效'
    assert len([x for x in c.calls if x[0] == 'POST']) == 2


def test_platform_permission_failure_keeps_pending_status(console):
    c = console
    c.pages = {None: {'list': [entry('r1', 'u1')]}}
    assert refresh_requests(c)['ok']
    c.failure['/v2/groups/group/approval_join_request/u1'] = (403, {'code': 11253, 'message': 'secret detail'})
    result = call(c, 'JoinRequestAct', op='approve', join_request_id='r1', member_openid='u1')
    assert not result['ok'] and result['keyword'] == '无接口权限' and result['error_code'] == 11253
    assert 'message' not in result and 'secret detail' not in str(result)
    assert requests_by_id(c)['r1']['status'] == 'pending'


def test_platform_role_permission_failure_stops_management(console):
    console.failure['/v2/groups/group/bot_state'] = (403, {'code': 11253, 'message': 'private detail'})
    result = refresh_requests(console)
    assert not result['ok'] and result['keyword'] == '无接口权限' and result['error_code'] == 11253
    assert 'message' not in result
    assert [path for _, path, _, _ in console.calls] == ['/v2/groups/group/bot_state']


def test_failed_second_request_page_does_not_replace_cached_requests(console):
    c = console
    c.roster.refresh_requests(c.bot.hash, 'group', [entry('old', 'u-old')])
    c.pages = {None: {'list': [entry('r1', 'u1')], 'next_cursor': 'page-2'}, 'page-2': {}}
    original = sdk.req.request

    def fail_second(method, url, **kwargs):
        if parse_qs(urlsplit(url).query).get('cursor') == ['page-2']:
            c.calls.append((method, urlsplit(url).path, parse_qs(urlsplit(url).query), None))
            return SimpleNamespace(status_code=403, text=json.dumps({'code': 11253}), headers={})
        return original(method, url, **kwargs)

    sdk.req.request = fail_second
    try:
        result = refresh_requests(c)
    finally:
        sdk.req.request = original
    assert not result['ok'] and result['keyword'] == '无接口权限'
    assert set(requests_by_id(c)) == {'old'} and requests_by_id(c)['old']['status'] == 'pending'


@pytest.mark.parametrize('event_type', ['GROUP_ADD_ROBOT', 'GROUP_MEMBER_ADD'])
def test_group_join_event_id_used_for_bridge_send(console, event_type):
    c = console
    event = SimpleNamespace(platform={'sdk': 'qqGuildv2_link'}, bot_info=c.bot,
        data=SimpleNamespace(group_id='group', user_id='joined',
                             extend={'flag_from_qq': True, 'event_id': 'join-event',
                                     'qq_event_data': {'timestamp': c.now}}),
        sdk_event=SimpleNamespace(payload=SimpleNamespace(data=SimpleNamespace(t=event_type))))
    main.Event.group_member_increase(event, c.proc)
    candidates = c.pool.candidates(c.bot.hash, 'qq_group', 'group')
    assert len(candidates) == 1 and candidates[0]['id_type'] == 'event_id'
    assert candidates[0]['id_value'] == 'join-event' and candidates[0]['source_event'] == event_type
    result = call(c, 'Send', kind='text', text='welcome')
    assert result['ok'] and result['channel'] == 'passive'
    posts = [body for method, path, _, body in c.calls if method == 'POST' and path.endswith('/messages')]
    assert len(posts) == 1 and posts[0]['event_id'] == 'join-event' and 'msg_id' not in posts[0]


def test_successful_recall_marks_record_without_deleting_content(console):
    c = console
    c.store.add_message(c.bot.hash, 'qq_group', 'group', {
        'direction': 'out', 'platform_message_id': 'message-1', 'msg_kind': 'text',
        'content_text': 'keep this content', 'content_json': {'text': 'keep this content'}, 'created_at': c.now,
    }, unread=False)
    before = call(c, 'PullMessages')['messages']
    result = call(c, 'Recall', message_id='message-1')
    assert result['ok']
    after = call(c, 'PullMessages')['messages']
    assert len(before) == len(after) == 1
    assert before[0]['recalled'] == 0 and after[0]['recalled'] == 1
    assert {k: v for k, v in before[0].items() if k != 'recalled'} == {
        k: v for k, v in after[0].items() if k != 'recalled'}
    deletes = [(method, path) for method, path, _, _ in c.calls if method == 'DELETE']
    assert deletes == [('DELETE', '/v2/groups/group/messages/message-1')]


def test_failed_recall_preserves_record(console):
    c = console
    c.store.add_message(c.bot.hash, 'qq_group', 'group', {
        'direction': 'out', 'platform_message_id': 'failed-recall', 'msg_kind': 'text',
        'content_text': 'still visible', 'created_at': c.now,
    }, unread=False)
    c.failure['/v2/groups/group/messages/failed-recall'] = (403, {'code': 40062003})
    result = call(c, 'Recall', message_id='failed-recall')
    assert not result['ok'] and result['keyword'] == '无撤回权限'
    rows = call(c, 'PullMessages')['messages']
    assert len(rows) == 1 and rows[0]['recalled'] == 0 and rows[0]['content_text'] == 'still visible'
