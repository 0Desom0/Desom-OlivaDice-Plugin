"""后台刷新入群申请的行为回归；不访问 QQ 网络。"""
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from QQOfficialConsole import webui


class Roster:
    def __init__(self):
        self.rows = []
        self.commits = []

    def list_requests(self, bot, chat, limit):
        return list(self.rows)

    def refresh_requests(self, bot, chat, rows, complete):
        self.commits.append((list(rows), complete))
        self.rows = list(rows)


def test_refresh_is_background_and_merges_same_group(tmp_path):
    entered, release = threading.Event(), threading.Event()
    roster = Roster()
    roster.rows = [{'join_request_id': 'old'}]
    bridge = webui.Bridge(SimpleNamespace(root=tmp_path), None, roster, None, None)
    bridge._admin = lambda *args: None

    def fetch(*args, **kwargs):
        entered.set()
        release.wait(5)
        return {'active': True, 'data': {'response': {'list': [], 'next_cursor': ''}}}

    bridge._event = lambda bot: SimpleNamespace(indeAPI=SimpleNamespace(get_qq_group_join_request_list=fetch))
    try:
        first = bridge._join_request_list('bot', 'group', True)
        assert first['refreshing']
        assert entered.wait(2)
        second = bridge._join_request_list('bot', 'group', True)
        assert second['refreshing']
        assert len(bridge._jobs) == 1
        release.set()
        bridge._jobs[('bot', 'group')]['thread'].join(5)
        result = bridge._join_request_list('bot', 'group', False)
        assert result['ok'] and not result['refreshing']
        assert roster.commits == [([], True)]
        assert not bridge._jobs
    finally:
        release.set()
        bridge.close()


def test_close_prevents_inflight_refresh_from_committing(tmp_path):
    entered, release = threading.Event(), threading.Event()
    roster = Roster()
    bridge = webui.Bridge(SimpleNamespace(root=tmp_path), None, roster, None, None)
    bridge._admin = lambda *args: None

    def fetch(*args, **kwargs):
        entered.set()
        release.wait(5)
        return {'active': True, 'data': {'response': {'list': [], 'next_cursor': ''}}}

    bridge._event = lambda bot: SimpleNamespace(indeAPI=SimpleNamespace(get_qq_group_join_request_list=fetch))
    bridge._join_request_list('bot', 'group', True)
    assert entered.wait(2)
    thread = bridge._jobs[('bot', 'group')]['thread']
    bridge.close()
    release.set()
    thread.join(5)
    assert not roster.commits
