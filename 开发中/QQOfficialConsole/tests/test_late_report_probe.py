"""QQ 接口延迟上报问题的独立诊断；全程不连 QQ。"""

from test_group_info import call
from test_group_info import console as group_console  # noqa: F401


def test_group_name_requests_use_a_30_per_minute_window(group_console):  # noqa: F811
    """官方限制是每机器人 30 QPM；按窗口放行，不额外假设固定间隔。"""
    c = group_console
    for index in range(31):
        c.store.upsert_chat(c.bot.hash, 'qq_group', 'g%d' % index)
        c.store.enqueue_group_info(c.bot.hash, 'g%d' % index, enqueued_at=100 + index)
    c.bridge.pump_group_info(limit=100)
    assert [path for _, path in c.calls] == ['/v2/groups/g%d/info' % index for index in range(30)]
    c.ticks[0] += 60
    c.bridge.pump_group_info(limit=100)
    assert [path for _, path in c.calls] == ['/v2/groups/g%d/info' % index for index in range(31)]


def test_manual_group_refresh_does_not_bypass_cooling_fifo_head(group_console):  # noqa: F811
    c = group_console
    for group, stamp in [('g1', 100), ('g2', 200)]:
        c.store.upsert_chat(c.bot.hash, 'qq_group', group)
        c.store.enqueue_group_info(c.bot.hash, group, enqueued_at=stamp)
    c.info_failure['/v2/groups/g1/info'] = (429, {'message': 'rate limited'})
    c.bridge.pump_group_info(limit=10)
    assert [path for _, path in c.calls] == ['/v2/groups/g1/info']
    result = call(c, 'RefreshGroupName', chat_id='g2')
    assert result['ok'] and result['queued'] is True
    assert [path for _, path in c.calls] == ['/v2/groups/g1/info']
    c.bridge.pump_group_info(limit=10)
    assert [path for _, path in c.calls] == ['/v2/groups/g1/info']


def test_full_platform_error_code_yields_permission_message():
    from QQOfficialConsole import errors
    raw = {'active': False, 'data': {'error_code': 40012010}}
    assert errors.result(raw)['keyword'] == '无接口权限'


def test_manual_refreshes_respect_30_per_minute(group_console, monkeypatch):  # noqa: F811
    c = group_console
    monkeypatch.setattr(c.bridge, 'wake_group_info', lambda: None)
    for index in range(31):
        result = call(c, 'RefreshGroupName', chat_id='g' + str(index))
        assert result['ok'] and result['queued'] is True
    assert c.calls == []  # 手动刷新不再绕过队列直接打接口
    c.bridge.pump_group_info(limit=100)
    assert len(c.calls) == 30, len(c.calls)


def test_group_jobs_are_isolated_by_bot(group_console):  # noqa: F811
    c = group_console
    c.store.enqueue_group_info('bot-one', 'same-group')
    c.store.enqueue_group_info('bot-two', 'same-group')
    c.store.complete_group_info_job('bot-one', 'same-group')
    assert c.store.group_info_job('bot-one', 'same-group')['status'] == 'done'
    assert c.store.group_info_job('bot-two', 'same-group')['status'] == 'pending'
