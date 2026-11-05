"""群名任务暂时性故障必须留在队列里；所有请求使用本地模拟。"""
import pytest
from test_group_info import console as group_console  # noqa: F401
from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as sdk


@pytest.mark.parametrize('failure', ['timeout', 'server_error', 'token_unavailable'])
def test_transient_group_info_failure_does_not_discard_fifo(group_console, monkeypatch, failure):  # noqa: F811
    c = group_console
    for group, stamp in [('g1', 100), ('g2', 200)]:
        c.store.upsert_chat(c.bot.hash, 'qq_group', group)
        c.store.enqueue_group_info(c.bot.hash, group, enqueued_at=stamp)
    if failure == 'timeout':
        def timed_out(*args, **kwargs):
            raise TimeoutError('模拟网络超时')
        monkeypatch.setattr(sdk.req, 'request', timed_out)
    elif failure == 'token_unavailable':
        monkeypatch.setattr(sdk, 'getTokenNow', lambda bot_info: None)
    else:
        c.info_failure['/v2/groups/g1/info'] = (503, {'message': '暂时不可用'})
    for _ in range(7):
        c.bridge.pump_group_info(limit=10)
        job = c.store.group_info_job(c.bot.hash, 'g1')
        assert job['status'] == 'pending'
        assert c.store.group_info_job(c.bot.hash, 'g2')['status'] == 'pending'
        c.clock[0] += 120
        c.ticks[0] += 120
