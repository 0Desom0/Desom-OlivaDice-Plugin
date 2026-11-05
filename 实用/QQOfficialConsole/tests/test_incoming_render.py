"""入站消息渲染：@ 昵称替换与 QQ 表情标签剥离。"""
import importlib
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
    monkeypatch.setattr(main, '_initialise', lambda proc: (database, None, None, None, None))
    yield main, database
    database.close()


def group_message(main, bot, group, msg_id, content, mentions=None, attachments=None):
    raw = {'id': msg_id, 'content': content, 'timestamp': 1700000000}
    if mentions is not None:
        raw['mentions'] = mentions
    if attachments is not None:
        raw['attachments'] = attachments
    event = SimpleNamespace(
        platform={'sdk': 'qqGuildv2_link'}, bot_info=SimpleNamespace(hash=bot),
        data=SimpleNamespace(group_id=group, user_id='member', sender={}, extend={
            'flag_from_qq': True, 'qq_event_data': raw,
        }),
        sdk_event=SimpleNamespace(payload=SimpleNamespace(data=SimpleNamespace(t='GROUP_MESSAGE_CREATE'))),
    )
    main._incoming(event, None, True)


def mention(ident, username):
    return {'id': ident, 'member_openid': ident, 'username': username, 'bot': False}


def test_at_placeholder_replaced_with_nickname(plugin):
    main, db = plugin
    group_message(main, 'a', 'g', 'one', '<@AAAA> 你好 <@BBBB>',
                  mentions=[mention('AAAA', '爱丽丝'), mention('BBBB', '波波')])
    row = db.list_messages('a', 'qq_group', 'g')[0]
    assert row['content_text'] == '@爱丽丝 你好 @波波'
    assert '<@' not in row['content_text']


def test_at_unknown_id_keeps_placeholder_text_but_strips_markup(plugin):
    main, db = plugin
    group_message(main, 'a', 'g', 'one', '<@ZZZZ> 谁', mentions=[])
    row = db.list_messages('a', 'qq_group', 'g')[0]
    # mentions 里没有的 id 退化为 @成员，不能把原始标记漏给用户
    assert row['content_text'] == '@成员 谁'


def test_face_tag_stripped_and_marked(plugin):
    main, db = plugin
    group_message(main, 'a', 'g', 'one', '<faceType=6,faceId="0",ext="eyJ0ZXh0IjoiIn0="> 早上好')
    row = db.list_messages('a', 'qq_group', 'g')[0]
    assert row['content_text'] == '[表情] 早上好'
    assert 'faceType' not in row['content_text']


def test_face_only_message_with_attachment_keeps_media_kind(plugin):
    main, db = plugin
    group_message(main, 'a', 'g', 'one', '<faceType=6,faceId="0",ext="***=">',
                  attachments=[{'url': 'https://example.invalid/a.jpg', 'content_type': 'image/jpeg'}])
    row = db.list_messages('a', 'qq_group', 'g')[0]
    assert row['msg_kind'] == 'media'
    assert row['content_text'] == '[表情]'


def test_plain_text_unchanged(plugin):
    main, db = plugin
    group_message(main, 'a', 'g', 'one', '普通消息 <notatag>')
    row = db.list_messages('a', 'qq_group', 'g')[0]
    assert row['content_text'] == '普通消息 <notatag>'


def test_at_everyone_tag_renders_text_and_flag(plugin):
    main, db = plugin
    group_message(main, 'a', 'g', 'one', '<qqbot-at-everyone /> 大家注意')
    row = db.list_messages('a', 'qq_group', 'g')[0]
    # @全体成员显示成固定文案，原始标签不能漏给用户；未 @ 机器人时不算 @我。
    assert row['content_text'] == 'at全体成员 大家注意'
    assert 'qqbot-at-everyone' not in row['content_text']
    assert row['is_everyone'] == 1 and row['is_mention'] == 0


def test_at_everyone_placeholder_and_mentions_entry(plugin):
    main, db = plugin
    # 两种来源都要认：<@all> 占位符、mentions 里的 all/everyone 条目。
    group_message(main, 'a', 'g', 'one', '<@all> 点名', mentions=[])
    group_message(main, 'a', 'g', 'two', '集合', mentions=[mention('everyone', '全体成员')])
    rows = db.list_messages('a', 'qq_group', 'g')
    assert rows[0]['content_text'] == 'at全体成员 点名'
    assert rows[1]['content_text'] == '集合'
    assert [row['is_everyone'] for row in rows] == [1, 1]
