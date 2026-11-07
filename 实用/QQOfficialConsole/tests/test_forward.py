"""合并转发（聊天记录）：把 message_type=102 的文本块还原成卡片数据。"""
import importlib
import json
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


def image_line(index, url, size='628x471', name=None):
    name = name or 'shot%d.jpg' % index
    return '[附件%d] 类型:图片 文件名:%s 尺寸:%s 大小:350.3KB URL:%s' % (index, name, size, url)


def group_message(main, bot, group, msg_id, content, attachments=None, message_type=None):
    raw = {'id': msg_id, 'content': content, 'timestamp': 1700000000}
    if attachments is not None:
        raw['attachments'] = attachments
    if message_type is not None:
        raw['message_type'] = message_type
    event = SimpleNamespace(
        platform={'sdk': 'qqGuildv2_link'}, bot_info=SimpleNamespace(hash=bot),
        data=SimpleNamespace(group_id=group, user_id='member', sender={}, extend={
            'flag_from_qq': True, 'qq_event_data': raw,
        }),
        sdk_event=SimpleNamespace(payload=SimpleNamespace(data=SimpleNamespace(t='GROUP_MESSAGE_CREATE'))),
    )
    main._incoming(event, None, True)


def payload(row):
    return json.loads(row['content_json'])


def test_forward_parsed_into_card(plugin):
    main, db = plugin
    content = '\n'.join([
        '[眼·星夜的聊天记录]',
        '=== 消息 1 ===',
        '[发送者] 眼·星夜',
        '[消息内容] 今晚开团吗',
        image_line(1, 'https://multimedia.nt.qq.com.cn/download?fileid=AAA&rkey=K1'),
        '=== 消息 2 ===',
        '[发送者] 阿米娅',
        '[消息内容] 开，八点',
    ])
    group_message(main, 'a', 'g', 'f1', content, message_type=102)
    row = db.list_messages('a', 'qq_group', 'g')[0]
    assert row['msg_kind'] == 'forward'
    assert row['content_text'] == '[聊天记录]'
    data = payload(row)
    forward = data['forward']
    assert forward['title'] == '眼·星夜的聊天记录'
    assert [item['name'] for item in forward['messages']] == ['眼·星夜', '阿米娅']
    assert forward['messages'][0]['segments'][0] == {'type': 'text', 'text': '今晚开团吗'}
    assert forward['messages'][0]['segments'][1] == {'type': 'image', 'attachment': 0}
    assert data['attachments'][0]['url'].startswith('https://multimedia.nt.qq.com.cn/download')
    assert data['attachments'][0]['content_type'] == 'image/jpeg'
    assert data['attachments'][0]['width'] == 628


def test_forward_image_indices_follow_existing_attachments(plugin):
    main, db = plugin
    outer = {'content_type': 'image/png', 'url': 'https://multimedia.nt.qq.com.cn/download?fileid=OUT'}
    content = '\n'.join([
        '=== 消息 1 ===',
        '[发送者] 甲',
        '[消息内容] 看图',
        image_line(1, 'https://multimedia.nt.qq.com.cn/download?fileid=A'),
        image_line(2, 'https://multimedia.nt.qq.com.cn/download?fileid=B'),
    ])
    group_message(main, 'a', 'g', 'f2', content, attachments=[outer], message_type=102)
    data = payload(db.list_messages('a', 'qq_group', 'g')[0])
    segments = data['forward']['messages'][0]['segments']
    # 原有附件占了下标 0，转发里的两张图排到 1、2
    assert [s['attachment'] for s in segments if s['type'] == 'image'] == [1, 2]
    assert len(data['attachments']) == 3
    assert data['attachments'][0]['url'].endswith('OUT')


def test_forward_without_message_type_still_parsed(plugin):
    main, db = plugin
    content = '\n'.join([
        '=== 消息 1 ===',
        '[发送者] 甲',
        '[消息内容] 文字',
    ])
    group_message(main, 'a', 'g', 'f3', content)
    row = db.list_messages('a', 'qq_group', 'g')[0]
    assert row['msg_kind'] == 'forward'


def test_plain_text_with_equals_header_is_not_forward(plugin):
    main, db = plugin
    content = '=== 消息 1 ===\n这就是一段别人手打的文字'
    group_message(main, 'a', 'g', 'f4', content)
    row = db.list_messages('a', 'qq_group', 'g')[0]
    assert row['msg_kind'] == 'text'
    assert row['content_text'] == content


def test_forward_limits_messages_and_images(plugin, monkeypatch):
    main, db = plugin
    monkeypatch.setattr(main, '_FORWARD_LIMIT', 3)
    monkeypatch.setattr(main, '_FORWARD_IMAGE_LIMIT', 2)
    blocks = ['=== 消息 %d ===' % (i + 1) for i in range(5)]
    content = []
    for index, header in enumerate(blocks):
        content.append(header)
        content.append('[发送者] 甲')
        content.append('[消息内容] 第%d条' % (index + 1))
        content.append(image_line(1, 'https://multimedia.nt.qq.com.cn/download?fileid=%d' % index))
    group_message(main, 'a', 'g', 'f5', '\n'.join(content), message_type=102)
    data = payload(db.list_messages('a', 'qq_group', 'g')[0])
    assert len(data['forward']['messages']) == 3
    # 最多两张图，其余退化成文字占位
    assert len([a for a in data['attachments'] if a.get('content_type', '').startswith('image/')]) == 2
    assert data['forward']['messages'][2]['segments'][-1] == {'type': 'text', 'text': '[图片]'}


def test_forward_preview_is_placeholder(plugin):
    main, db = plugin
    content = '=== 消息 1 ===\n[发送者] 甲\n[消息内容] 只有文字'
    group_message(main, 'a', 'g', 'f6', content, message_type=102)
    chats = db.list_chats('a')
    assert chats[0]['last_preview'] == '[聊天记录]'


def test_forward_file_attachment_becomes_note(plugin):
    main, db = plugin
    content = '\n'.join([
        '=== 消息 1 ===',
        '[发送者] 甲',
        '[消息内容] 资料',
        '[附件1] 类型:文件 文件名:规则.pdf 大小:1.2MB URL:https://multimedia.nt.qq.com.cn/download?fileid=PDF',
    ])
    group_message(main, 'a', 'g', 'f7', content, message_type=102)
    data = payload(db.list_messages('a', 'qq_group', 'g')[0])
    assert data['forward']['messages'][0]['segments'][-1] == {'type': 'file', 'name': '规则.pdf'}
