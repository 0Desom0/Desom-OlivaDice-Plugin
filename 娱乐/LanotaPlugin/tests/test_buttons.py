"""覆盖 QQ 四个入口的实际消息、键盘权限、互动凭据与会话边界。"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from LanotaPlugin import config, function, main, message, render, utils  # noqa: E402


def event(user='reader', group='group', bot='bot', kind='qq_group'):
    return SimpleNamespace(
        data=SimpleNamespace(user_id=user, group_id=group, message='', message_id='msg',
                             extend={'chat_type': kind, 'chat_id': group or user, 'event_id': 'interaction'}),
        bot_info=SimpleNamespace(hash=bot), platform={'sdk': 'qqGuildv2_link'},
        plugin_info={'func_type': 'group_message' if group else 'private_message'}, reply=Mock(),
        indeAPI=SimpleNamespace(create_markdown_message=Mock(return_value={'active': True}), send_message=Mock()),
    )


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(utils, 'initialized', True)
    monkeypatch.setattr(message, 'search_session_dict', {})
    monkeypatch.setattr(message, 'selection_cards', {})
    utils.save_global_config({'send_cover_art': False})
    utils.save_bot_config('bot', {'song_card_html_enable': False})


@pytest.fixture
def songs(monkeypatch):
    catalog = [{'id': i, 'title': f'{"长乐曲 " * 14}{i}', 'source_url': f'https://lanota.fandom.com/wiki/Song_{i}'}
               for i in range(1, 24)]
    monkeypatch.setattr(function, 'load_song_data', lambda: catalog)
    monkeypatch.setattr(function, 'load_alias_data', lambda: {})
    return catalog


def send(e, text):
    e.data.message = text
    e.plugin_info['func_type'] = 'group_message' if e.data.group_id else 'private_message'
    message.handle_message(e, None)


def click(e, action, button_id=None):
    e.data.button_data = action
    e.data.button_id = button_id
    e.plugin_info['func_type'] = 'button_click'
    e.data.message = ''
    main.Event.button_click(e, None)


def payload(e):
    return e.indeAPI.create_markdown_message.call_args.kwargs


def buttons(kb):
    rows = kb['content']['rows']
    assert 1 <= len(rows) <= 5
    result = []
    for row in rows:
        assert 1 <= len(row['buttons']) <= 4
        for b in row['buttons']:
            label = b['render_data']['label']
            assert 1 <= len(label) <= 20 and b['render_data']['visited_label'] == label
            action = b['action']
            if action['type'] == 1:
                assert action['permission'] == {'type': 0, 'specify_user_ids': ['reader']}
            else:
                assert action['permission'] == {'type': 2}
            result.append((label, action['type'], action['data']))
    return result


def test_search_click_jump_selection_and_end(songs):
    e = event()
    send(e, '.la 查询 长乐曲')
    text = payload(e)['markdown']['content']
    assert '查询到 23 首乐曲' in text
    assert f'**1. [1] {songs[0]["title"]}**\n**2. [2] {songs[1]["title"]}**' in text
    assert buttons(payload(e)['keyboard']) == [('下一页', 1, 'la:pg:next'), ('跳页', 2, '.la 跳页 ')]
    assert not payload(e)['keyboard']['content']['rows'][0]['buttons'][-1]['action']['enter']
    click(e, 'la:pg:next')
    assert message.get_search_session(e)['page_index'] == 1
    assert payload(e)['event_id'] == 'interaction' and 'msg_id' not in payload(e)
    assert [b[0] for b in buttons(payload(e)['keyboard'])] == ['上一页', '下一页', '跳页']
    send(e, '.la 跳页 9')
    assert '页码无效' in payload(e)['markdown']['content']
    assert message.get_search_session(e)['page_index'] == 1
    send(e, '.la 跳页 3')
    assert [b[0] for b in buttons(payload(e)['keyboard'])] == ['上一页', '跳页']
    click(e, 'la:pg:prev')
    assert message.get_search_session(e)['page_index'] == 1
    send(e, '跳页1')
    assert message.get_search_session(e)['page_index'] == 0
    send(e, 'end')
    click(e, 'la:pg:next')
    assert '过期' in payload(e)['markdown']['content']
    message.save_search_session(e, songs[:2], None)
    message.reply_search_page(e, songs[:2])
    assert 'keyboard' not in payload(e) and '下方按钮' not in payload(e)['markdown']['content']
    send(e, '2')
    assert [b[0] for b in buttons(payload(e)['keyboard'])] == ['全曲列表', '信息来源']
    assert not message.get_search_session(e)


@pytest.mark.parametrize('other', [{'user': 'other'}, {'group': 'another'}, {'bot': 'otherbot'}])
def test_search_isolation(songs, other):
    owner = event()
    message.save_search_session(owner, songs, None)
    stranger = event(**other)
    click(stranger, 'la:pg:next')
    assert message.get_search_session(owner)['page_index'] == 0
    assert '重新搜索' in payload(stranger)['markdown']['content']


def test_today_and_random_keep_original_cards(songs, monkeypatch):
    e = event()
    monkeypatch.setattr(function, 'get_user_today_song', lambda *_: songs[0])
    send(e, '.la today')
    kb = payload(e)['keyboard']
    assert buttons(kb) == [('完整详情', 1, 'la:today:detail'), ('换一首随机', 2, '.la random')]
    today_id = kb['content']['rows'][0]['buttons'][0]['id']
    picks = iter((1, 2))
    monkeypatch.setattr(function, 'random_index', lambda _: next(picks))
    send(e, '.la random')
    kb = payload(e)['keyboard']
    assert buttons(kb) == [('再来一首', 2, '.la random'), ('查看详情', 1, 'la:random:detail')]
    random_id = kb['content']['rows'][0]['buttons'][1]['id']
    send(e, '.la random')
    click(e, 'la:random:detail', random_id)
    assert [b[0] for b in buttons(payload(e)['keyboard'])] == ['全曲列表', '信息来源']
    click(e, 'la:random:detail')
    assert '原卡片标识' in payload(e)['markdown']['content']
    click(e, 'la:today:detail', today_id)
    assert [b[0] for b in buttons(payload(e)['keyboard'])] == ['全曲列表', '信息来源']
    stranger = event(user='other')
    click(stranger, 'la:today:detail', today_id)
    assert '过期' in payload(stranger)['markdown']['content']
    monkeypatch.setattr(config, 'selection_timeout_seconds', -1)
    click(e, 'la:today:detail', today_id)
    assert '过期' in payload(e)['markdown']['content']


def test_info_link_shapes_and_limits(songs):
    song = dict(songs[0], url='https://download.example/song', page_url='https://archive.example/song',
                external_sources=[{'site': 'Delicious Fruit', 'url': 'https://delicious-fruit.com/song'},
                                  {'site': 'Lanota Wiki', 'url': songs[0]['source_url']},
                                  {'site': '非网页', 'url': 'file:///private'}])
    e = event()
    message.reply_song_card(e, song)
    labels = [b[0] for b in buttons(payload(e)['keyboard'])]
    assert labels[:2] == ['下载', '档案页']
    assert '全曲列表' in labels and 'DF' in labels
    # 空曲目也会给「全曲列表」这一个固定按钮。
    assert [b[0] for b in buttons(render.detail_keyboard({}))] == ['全曲列表']
    more = [{'site': '曲目来源' * 12, 'url': f'https://external.example/{i}'} for i in range(22)]
    assert len(buttons(render.detail_keyboard({'external_sources': more}))) == 20


def test_private_commands_and_channel_body_only(songs):
    e = event(group=None, kind='qq_private')
    message.reply_search_page(e, songs)
    assert buttons(payload(e)['keyboard']) == [('下一页', 2, '.la 跳页 2'), ('跳页', 2, '.la 跳页 ')]
    message.reply_song_detail(e, '随机乐曲', songs[0], entry='random')
    assert buttons(payload(e)['keyboard']) == [('再来一首', 2, '.la random'), ('查看详情', 2, '.la info 1')]
    channel = event(kind='guild_channel')
    message.reply_search_page(channel, songs)
    message.reply_song_detail(channel, '今日曲', songs[0], entry='today')
    message.reply_song_card(channel, songs[0])
    channel.indeAPI.create_markdown_message.assert_not_called()
    assert channel.reply.call_count == 3
    assert all('[OP:image' not in call.args[0] for call in channel.reply.call_args_list)


@pytest.mark.parametrize('setting', ['text', 'image', 'disabled_group', 'disabled_bot', 'disabled_global', 'other'])
def test_stale_callbacks_respect_current_switches(setting, songs):
    e = event()
    message.save_search_session(e, songs, None)
    if setting in ('text', 'image'):
        utils.save_bot_config('bot', {'reply_mode': setting})
    elif setting == 'disabled_group':
        utils.set_disabled_group_list('bot', ['group'])
    elif setting == 'disabled_bot':
        utils.save_bot_config('bot', {'bot_enable_switch': False})
    elif setting == 'disabled_global':
        utils.save_global_config({'global_enable_switch': False})
    click(e, 'other:pg:next' if setting == 'other' else 'la:pg:next')
    e.indeAPI.create_markdown_message.assert_not_called()
    assert message.get_search_session(e)['page_index'] == 0


def test_click_fallback_uses_interaction_not_generic_reply():
    e = event()
    e.indeAPI.create_markdown_message.return_value = {'active': False}
    click(e, 'la:pg:next')
    e.indeAPI.send_message.assert_called_once_with(
        'qq_group', 'group', '搜索已结束或过期，请重新搜索。', event_id='interaction',
    )
    e.reply.assert_not_called()
