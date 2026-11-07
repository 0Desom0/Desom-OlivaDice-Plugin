"""右上角「@我 / N 条新消息」跳转：标读前快照与标读后兜底。"""
import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    for name in list(sys.modules):
        if name == 'QQOfficialConsole' or name.startswith('QQOfficialConsole.'):
            monkeypatch.delitem(sys.modules, name)
    main = importlib.import_module('QQOfficialConsole.main')
    database = main.store.Store(tmp_path)
    monkeypatch.setattr(main, '_initialise', lambda proc: (database,))
    yield main, database
    database.close()


def add_at(db, text, created):
    db.add_message(
        'a', 'qq_group', 'g',
        {
            'direction': 'in', 'msg_kind': 'text', 'content_text': text,
            'created_at': created, 'is_mention': 1,
        },
    )
    return db.list_messages('a', 'qq_group', 'g')[-1]['id']


def make_bridge(main, db):
    """只测动作分发：跳过构造里的线程 / 宿主依赖，机器人列表用桩。"""
    bridge = main.webui.Bridge.__new__(main.webui.Bridge)
    bridge.store = db
    bridge._bots = lambda: {'a': object()}
    return bridge


def test_unread_target_is_lost_once_marked_read(plugin):
    _, db = plugin
    first = add_at(db, '@我 第一条', 1700000000)
    add_at(db, '@我 第二条', 1700000001)
    before = db.unread_target('a', 'qq_group', 'g')
    assert before == {
        'unread': 2, 'mention_unread': 2,
        'first_unread': first, 'first_mention': first,
    }
    # 这正是前端竞态的后果：宿主先执行标读，随后到达的 UnreadState 就只剩全 0。
    db.mark_read_all('a', 'qq_group', 'g')
    after = db.unread_target('a', 'qq_group', 'g')
    assert after['first_unread'] is None and after['first_mention'] is None


def test_chat_action_read_returns_snapshot_before_marking(plugin):
    main, db = plugin
    first = add_at(db, '@我 第一条', 1700000000)
    before = db.unread_target('a', 'qq_group', 'g')
    bridge = make_bridge(main, db)
    result = bridge.handle('QQOfficialConsole_ChatAction', {
        'bot_hash': 'a', 'chat_type': 'qq_group', 'chat_id': 'g',
        'action': 'read', 'all': True,
    })
    assert result['ok'] is True and result['keyword'] == '成功'
    assert result['snapshot'] == before
    assert result['snapshot']['first_mention'] == first
    assert result['chat']['mention_unread'] == 0
    # 标读确实执行了，但跳转目标已经随响应留下。
    assert db.unread_target('a', 'qq_group', 'g')['first_mention'] is None


def test_mention_target_falls_back_only_when_requested(plugin):
    main, db = plugin
    add_at(db, '@我 第一条', 1700000000)
    last = add_at(db, '@我 第二条', 1700000001)
    db.mark_read_all('a', 'qq_group', 'g')
    # 默认语义不变：没有未读 @ 就是没有。
    assert db.mention_target('a', 'qq_group', 'g') == {'message_id': None, 'newer_count': 0}
    # 右上角按钮的后备跳转才开启：退到最近一条 @。
    assert db.mention_target('a', 'qq_group', 'g', include_history=True) == {
        'message_id': last, 'newer_count': 0,
    }
    result = make_bridge(main, db).handle('QQOfficialConsole_MentionTarget', {
        'bot_hash': 'a', 'chat_type': 'qq_group', 'chat_id': 'g',
    })
    assert result['message_id'] == last
