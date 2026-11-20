"""在临时实例目录验证 QQ 适配器收到的完整消息以及旧发送路径。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from LanotaPlugin import config, function, message, utils  # noqa: E402


@pytest.fixture
def event(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return SimpleNamespace(
        data=SimpleNamespace(group_id='group', user_id='user', message='[OP:at,id=bot] /la song',
                             message_id='msg', extend={'event_id': 'event'}),
        plugin_info={'func_type': 'group_message'},
        indeAPI=SimpleNamespace(create_markdown_message=Mock(return_value={'active': True})),
        reply=Mock(),
    )


def test_existing_config_gets_markdown_default(event):
    path = Path(utils.get_bot_config_path('default'))
    path.write_text(json.dumps({'plain_text_mode': True}), encoding='utf-8')
    assert config.default_bot_config['reply_mode'] == utils.get_reply_mode(event) == 'markdown'
    assert not message.is_plain_text_mode(event)
    assert utils.get_reply_mode(event, {'send_as_image': False}) == 'text'
    assert utils.get_reply_mode(event, {'reply_mode': 'image', 'plain_text_mode': True}) == 'image'


@pytest.mark.parametrize('group,kind', [('group', 'qq_group'), ('', 'qq_private')])
def test_quote_and_passive_credentials(event, group, kind):
    event.data.group_id = group
    event.data.message = '[OP:reply,id=1][OP:at,id=bot]' + '音' * 41
    message.reply_text(event, '【曲目】\n\n\n· 曲师：Art')
    payload = event.indeAPI.create_markdown_message.call_args.kwargs
    body = '**曲目**\n\n**曲师**：Art'
    if group:
        body = '> <qqbot-at-user id="user" />：' + '音' * 40 + '…\n\n' + body
    assert payload == {'chat_type': kind, 'chat_id': group or 'user', 'msg_id': 'msg',
                       'markdown': {'content': body}}
    event.reply.assert_not_called()


@pytest.mark.parametrize('func_type,message_id', [('button_click', 'old-card'), ('private_message', '-1')])
def test_event_only_credentials(event, func_type, message_id):
    event.plugin_info['func_type'] = func_type
    event.data.message_id = message_id
    message.reply_text(event, '详情')
    payload = event.indeAPI.create_markdown_message.call_args.kwargs
    assert 'msg_id' not in payload and payload['event_id'] == 'event'


@pytest.mark.parametrize('command', ['detail', 'card'])
def test_song_images_and_caption_share_one_send(event, tmp_path, monkeypatch, command):
    cover, card = tmp_path / 'cover.png', tmp_path / 'card.webp'
    cover.write_bytes(b'cover')
    card.write_bytes(b'card')
    monkeypatch.setattr(message.crawler, 'ensure_song_covers', lambda song: [str(cover)])
    monkeypatch.setattr(function, 'load_table_data', lambda: {})
    monkeypatch.setattr(function, 'format_song_info', lambda song: '· 曲名：Stasis')
    monkeypatch.setattr(message.portal, 'render_song_card', lambda data: str(card))

    def receive(**payload):
        content = payload['markdown']['content']
        assert '**曲名**：Stasis' in content
        files = []
        for label, relative in payload['local_images'].items():
            assert '{{' + label + '}}' in content
            assert relative.startswith('LanotaPlugin/') and '\\' not in relative
            files.append((Path('data/images') / relative).read_bytes())
        assert files == ([b'card', b'cover'] if command == 'card' else [b'cover'])
        return {'active': True}

    event.indeAPI.create_markdown_message.side_effect = receive
    if command == 'detail':
        message.reply_song_detail(event, '今日曲', {})
    else:
        message.reply_song_card(event, {})
    event.indeAPI.create_markdown_message.assert_called_once()
    event.reply.assert_not_called()
    assert not list(Path('data/images/LanotaPlugin').iterdir())


@pytest.mark.parametrize('failure', ['unsupported', 'guild', 'inactive', 'exception', 'disabled'])
def test_markdown_failure_falls_back_to_image(event, monkeypatch, failure):
    sender = event.indeAPI.create_markdown_message
    if failure == 'unsupported':
        del event.indeAPI.create_markdown_message
    elif failure == 'guild':
        event.data.extend.update(chat_type='guild_channel', chat_id='channel')
    elif failure == 'inactive':
        sender.return_value = {'active': False}
    elif failure == 'exception':
        sender.side_effect = OSError('offline')
    else:
        monkeypatch.setattr(utils, 'load_global_config', lambda: {'markdown_enable_switch': False})
    errors = Mock()
    monkeypatch.setattr(utils, 'error_log', errors)
    monkeypatch.setattr(function, 'create_text_image', lambda *args, **kwargs: 'fallback.webp')
    message.reply_text(event, '长' * config.text_image_min_chars)
    event.reply.assert_called_once()
    assert '[OP:image,file=' in event.reply.call_args.args[0]
    assert 'fallback.webp' in event.reply.call_args.args[0]
    assert sender.call_count == errors.call_count == int(failure in ('inactive', 'exception'))


def test_real_search_page_keeps_titles_and_navigation(event):
    title = 'The Nightfall ' * 12 + 'END'
    songs = [{'id': i, 'chapter': 'Ch. 1', 'title': title} for i in (101, 102, 103)]
    page, _, _ = function.format_search_results_with_pagination(songs, 0, 2)
    message.reply_text(event, page)
    body = event.indeAPI.create_markdown_message.call_args.kwargs['markdown']['content']
    assert f'**1. [101] {title}**\n**2. [102] {title}**' in body
    assert body.endswith('**输入序号查看详情 | 下一页/上一页/第X页 | 结束**')


@pytest.mark.parametrize('mode,expected', [('image', 2), ('text', 2), ('markdown', 1)])
def test_combined_sender_message_count(event, tmp_path, mode, expected):
    utils.save_bot_config('default', {'reply_mode': mode})
    image = tmp_path / 'cover.png'
    image.write_bytes(b'cover')
    utils.reply_images_with_text(event, [str(image)], '说明')
    assert event.reply.call_count + event.indeAPI.create_markdown_message.call_count == expected
    if mode != 'markdown':
        assert '[OP:image,' in event.reply.call_args_list[0].args[0]
        assert event.reply.call_args_list[1].args[0].endswith('说明')
