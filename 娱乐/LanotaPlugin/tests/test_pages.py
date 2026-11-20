"""排名边界、定数分段、报告截断、截图失败与缓存失效。"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from LanotaPlugin import function, message, pages, portal, utils  # noqa: E402


def test_duration_cutoffs_and_missing_metadata():
    songs = [{'title': str(i), 'time': f'3:{i:02}'} for i in range(32)]
    songs.extend({'title': str(i), 'time': time} for i, time in enumerate(('1:59', '1:20', '2:00', 'invalid')))
    data, text = pages.time_page(songs)
    assert (data['total'], data['long_count'], data['short_count']) == (36, 31, 2)
    assert [r['duration'] for r in data['short']] == ['1:20', '1:59']
    assert [r['duration'] for r in data['long']] == [f'3:{i:02}' for i in range(31, 1, -1)]
    assert '3:01' in text  # 文本不因页面限高而丢失第 31 首。


@pytest.fixture
def event(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return SimpleNamespace(data=SimpleNamespace(group_id='g', user_id='u', message='', message_id='m', extend={}),
                           indeAPI=SimpleNamespace(create_markdown_message=Mock(return_value={'active': True})),
                           plugin_info={'func_type': 'group_message'}, reply=Mock())


def test_table_uses_shown_chart_level_not_floor_of_constant(event, monkeypatch):
    levels = ('14+', '15', '15+', '16')
    songs = [{'chapter': level, 'title': level, 'id': i, 'difficulty': {'master': level}}
             for i, level in enumerate(levels)]
    monkeypatch.setattr(function, 'load_song_data', lambda: songs)
    monkeypatch.setattr(function, 'load_table_data', lambda: {level: {'Master': '14.8~15.2'} for level in levels})
    send = Mock()
    monkeypatch.setattr(pages, 'send', send)
    message.handle_table(event, '')
    _, kind, caption, segments = send.call_args.args
    assert kind == 'table' and '另有 1 段：14+' in caption
    assert [data['level'] for data, _ in segments] == ['16', '15+', '15']
    message.handle_table(event, '15')
    [(page, text)] = send.call_args.args[-1]
    assert page['rows'] == [{'constant': '14.8~15.2', 'level': '15', 'difficulty': 'Master', 'id': 1, 'name': '15'}]
    assert 'Master 15' in text


def test_report_counts_untruncated_differences(event, monkeypatch):
    monkeypatch.setattr(utils, 'sender_has_master_permission', lambda _: True)
    changes = [{'success': True, 'chapter': '1-1', 'title': f'曲{i}', 'changed': ['artist']} for i in range(50)]
    monkeypatch.setattr(message.crawler, 'run_full_check', lambda **_: {'results': changes, 'checked': 50})
    send = Mock()
    monkeypatch.setattr(pages, 'send', send)
    message.handle_fullcheck(event)
    [(page, _)] = send.call_args.args[-1]
    assert page['total'] == 50 and len(page['rows']) == 40 and page['rows'][-1].startswith('变化 · 1-1 曲39')


def test_failed_render_sends_pil_fallback_after_caption(event, monkeypatch):
    monkeypatch.setattr(portal, '_find_browser', lambda: None)
    image = Path('fallback.png')
    image.write_bytes(b'fallback')
    fallback = Mock(return_value=str(image))
    monkeypatch.setattr(function, 'create_text_image', fallback)
    monkeypatch.setattr(utils, 'error_log', errors := Mock())
    pages.send(event, 'notes', '谱面物量', [({'rows': []}, '文字版')])
    assert '未找到' in errors.call_args.args[-1] and fallback.call_args.args == ('文字版',)
    payload = event.indeAPI.create_markdown_message.call_args.kwargs
    assert 'keyboard' not in payload and payload['local_images'].get('图片1')
    assert payload['markdown']['content'].endswith('谱面物量\n\n{{图片1}}')


def test_update_preview_counts_songs_not_diff_lines_and_never_writes(event, monkeypatch):
    monkeypatch.setattr(utils, 'sender_has_master_permission', lambda _: True)
    update = Mock(side_effect=AssertionError('preview must not update the local catalog'))
    monkeypatch.setattr(message.crawler, 'run_update', update)
    sync = Mock(return_value={'added': 1, 'changed': 1, 'invalid': 0,
                              'difference_text': '+ 1-1 新曲\n* 2-2 旧曲\n  artist: A → B'})
    monkeypatch.setattr(message, 'wiki_sync', SimpleNamespace(run_sync=sync))
    send = Mock()
    monkeypatch.setattr(pages, 'send', send)
    message.handle_update(event, 'preview')
    update.assert_not_called()
    assert not sync.call_args.kwargs['apply']
    [(page, _)] = send.call_args.args[-1]
    assert page['total'] == 2 and page['rows'][-1] == '* 2-2 旧曲：artist: A → B'


def test_file_cache_canonicalization_and_lru(event, monkeypatch):
    def draw(data, kind, prefix, *, page_path, deadline):
        page_path.write_bytes(b'completed')
        return str(page_path)

    monkeypatch.setattr(portal, '_render_card', renderer := Mock(side_effect=draw))
    a = Path(portal.render_page('notes', {'rows': [], 'tag': 'a'}, 1))
    b = Path(portal.render_page('notes', {'rows': [], 'tag': 'b'}, 1))
    os.utime(a, (1, 1))
    os.utime(b, (2, 2))
    for stamp in range(2, 60):
        portal.render_page('notes', {'rows': []}, stamp)
    assert str(a) == portal.render_page('notes', {'tag': 'a', 'rows': []}, 1)
    newest = Path(portal.render_page('notes', {'rows': []}, 60))
    assert renderer.call_count == 61 and newest.is_file() and a.is_file() and not b.exists()
    assert newest.parent.name == 'portal_cache' and len(list(newest.parent.glob('*.png'))) == 60
