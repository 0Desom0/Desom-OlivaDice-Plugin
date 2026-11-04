"""明确 @ 提醒的持久化、重复事件和可见消息已读语义。"""
import importlib
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

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


def incoming(main, bot, group, msg_id, event_type, at=None):
    event = SimpleNamespace(
        platform={'sdk': 'qqGuildv2_link'}, bot_info=SimpleNamespace(hash=bot),
        data=SimpleNamespace(group_id=group, user_id='member', sender={}, extend={
            'flag_from_qq': True, 'qq_at_bot': at,
            'qq_event_data': {'id': msg_id, 'content': 'hello', 'timestamp': 1700000000},
        }),
        sdk_event=SimpleNamespace(payload=SimpleNamespace(data=SimpleNamespace(t=event_type))),
    )
    main._incoming(event, None, True)


def test_duplicate_upgrade_and_visible_read(plugin):
    main, db = plugin
    incoming(main, 'a', 'g', 'one', 'GROUP_MESSAGE_CREATE')
    incoming(main, 'a', 'g', 'two', 'GROUP_AT_MESSAGE_CREATE', True)
    rows = db.list_messages('a', 'qq_group', 'g')
    assert [row['is_mention'] for row in rows] == [0, 1]
    cursor = db.message_changes('a', 'qq_group', 'g', after=None, limit=200)['cursor']
    incoming(main, 'a', 'g', 'one', 'GROUP_AT_MESSAGE_CREATE', True)
    incoming(main, 'a', 'g', 'one', 'GROUP_AT_MESSAGE_CREATE', True)
    chat = db.get_chat('a', 'qq_group', 'g')
    assert chat['unread'] == 2 and chat['mention_unread'] == 2
    assert chat['mention_version'] == 2 and 'mention_ids' not in chat
    assert db.message_changes('a', 'qq_group', 'g', after=cursor, limit=200)['changes']
    db.mark_read_visible('a', 'qq_group', 'g', [rows[0]['id']])
    assert db.get_chat('a', 'qq_group', 'g')['mention_version'] == 2
    assert db.mention_target('a', 'qq_group', 'g')['message_id'] == rows[1]['id']
    assert db.mention_total('a') == 1
    incoming(main, 'a', 'g', 'one', 'GROUP_AT_MESSAGE_CREATE', True)
    assert db.mention_total('a') == 1
    assert db.get_chat('a', 'qq_group', 'g')['mention_version'] == 2


def test_late_mention_after_read_and_other_account(plugin):
    main, db = plugin
    incoming(main, 'a', 'g', 'one', 'GROUP_MESSAGE_CREATE')
    row = db.list_messages('a', 'qq_group', 'g')[0]
    db.mark_read_visible('a', 'qq_group', 'g', [row['id']])
    incoming(main, 'a', 'g', 'one', 'GROUP_AT_MESSAGE_CREATE', True)
    assert db.list_messages('a', 'qq_group', 'g')[0]['is_mention'] == 1
    assert db.mention_total('a') == 0
    assert db.get_chat('a', 'qq_group', 'g')['mention_version'] == 0
    incoming(main, 'b', 'g', 'two', 'GROUP_AT_MESSAGE_CREATE', True)
    assert db.mention_total('b') == 1
    db.save()
    root = db.root
    reopened = main.store.Store(root)
    try:
        assert reopened.mention_total('b') == 1
        assert reopened.get_chat('b', 'qq_group', 'g')['mention_version'] == 1
    finally:
        reopened.close()


def test_mention_target_counts_rows_not_id_gaps(plugin):
    main, db = plugin
    incoming(main, 'a', 'g', 'first', 'GROUP_AT_MESSAGE_CREATE', True)
    incoming(main, 'a', 'g', 'second', 'GROUP_AT_MESSAGE_CREATE', True)
    incoming(main, 'a', 'g', 'third', 'GROUP_MESSAGE_CREATE')
    incoming(main, 'a', 'g', 'fourth', 'GROUP_MESSAGE_CREATE')
    rows = db.list_messages('a', 'qq_group', 'g')
    with db.session('a', 'qq_group', 'g') as session:
        session.execute('DELETE FROM messages WHERE id=?', (rows[2]['id'],))
    assert db.mention_target('a', 'qq_group', 'g') == {'message_id': rows[0]['id'], 'newer_count': 2}
    assert db.mention_total('a') == 2
    db.mark_read_visible('a', 'qq_group', 'g', [rows[0]['id']])
    assert db.mention_target('a', 'qq_group', 'g') == {'message_id': rows[1]['id'], 'newer_count': 1}
    db.mark_read_visible('a', 'qq_group', 'g', [rows[1]['id']])
    assert db.mention_target('a', 'qq_group', 'g') == {'message_id': None, 'newer_count': 0}


def test_legacy_session_migrates_mention_index(plugin):
    main, db = plugin
    path = db.root / 'legacy' / 'msg' / 'qq_group' / 'g.sqlite3'
    path.parent.mkdir(parents=True)
    schema = main.store._CHAT.replace(
        ',\n is_mention INTEGER NOT NULL DEFAULT 0, mention_unread INTEGER NOT NULL DEFAULT 0', ''
    ).replace(',is_mention,mention_unread ON messages BEGIN', ' ON messages BEGIN')
    with sqlite3.connect(path) as old:
        old.executescript(schema)
    incoming(main, 'legacy', 'g', 'one', 'GROUP_AT_MESSAGE_CREATE', True)
    assert db.mention_target('legacy', 'qq_group', 'g')['message_id'] is not None
    with db.session('legacy', 'qq_group', 'g') as session:
        indexes = {row['name'] for row in session.execute('PRAGMA index_list(messages)')}
        assert 'messages_mention_unread' in indexes
