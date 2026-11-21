"""排名边界、定数分段、报告截断、截图失败与缓存失效。"""
import datetime
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


def test_table_default_groups_by_constant_desc(event, monkeypatch):
    levels = ('14+', '15', '15+', '16')
    songs = [{'chapter': level, 'title': level, 'id': i, 'difficulty': {'master': level}}
             for i, level in enumerate(levels)]
    constants = {'14+': '14.8', '15': '15.0', '15+': '15.3', '16': '16.2'}
    monkeypatch.setattr(function, 'load_song_data', lambda: songs)
    monkeypatch.setattr(function, 'load_table_data',
                        lambda: {level: {'Master': constants[level]} for level in levels})
    send = Mock()
    monkeypatch.setattr(pages, 'send', send)

    message.handle_table(event, '')
    _, kind, caption, segments = send.call_args.args
    assert kind == 'table'
    [(page, text)] = segments
    # 默认全部：按定数分级，数值高的排在前面。
    assert page['groupBy'] == 'constant'
    assert [tier['level'] for tier in page['tiers']] == ['16.2', '15.3', '15', '14.8']
    assert len(page['rows']) == 4
    assert '全部定数' in caption
    assert 'Master 15+' in text and 'Master 14+' in text

    # .la table 16 会把 16+ 一起带上
    message.handle_table(event, '16')
    [(page, _text)] = send.call_args.args[-1]
    assert {tier['level'] for tier in page['tiers']} == {'16.2'}
    assert {row['level'] for row in page['rows']} == {'16'}

    # .la table 15+ 只出 15+
    message.handle_table(event, '15+')
    [(page, _text)] = send.call_args.args[-1]
    assert {row['level'] for row in page['rows']} == {'15+'}


def test_table_plus_level_includes_plain_level(event, monkeypatch):
    songs = [{'chapter': 'a', 'title': 'A', 'id': 1, 'difficulty': {'master': '16'}},
             {'chapter': 'b', 'title': 'B', 'id': 2, 'difficulty': {'master': '16+'}}]
    monkeypatch.setattr(function, 'load_song_data', lambda: songs)
    monkeypatch.setattr(function, 'load_table_data',
                        lambda: {'a': {'Master': '16.2'}, 'b': {'Master': '16.4'}})
    send = Mock()
    monkeypatch.setattr(pages, 'send', send)
    message.handle_table(event, '16')
    [(page, _text)] = send.call_args.args[-1]
    assert {row['level'] for row in page['rows']} == {'16', '16+'}


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


def test_ritmo_page_wraps_years_months_days():
    today = datetime.date(2026, 11, 21)
    data, text = pages.ritmo_page(today=today)
    total = (today - datetime.date(2021, 9, 7)).days
    assert data['total'] == total
    assert (data['years'], data['months'], data['days']) == (5, 2, 14)
    assert data['elapsed'] == '5年2月14日'
    assert data['image'].startswith('data:image/webp;base64,')
    assert f'总共: {total}天' in text


def test_ritmo_template_and_kind_registered():
    template = Path(pages.__file__).parent / 'Data' / 'lanota_portal_ritmo.html'
    assert template.exists()
    assert 'ritmo' in portal._PAGE_KINDS


def test_table_page_tiers_sorted_by_constant():
    rows = [
        {'constant': '15.9', 'level': '15.9', 'difficulty': 'Master', 'id': 'b', 'name': 'B'},
        {'constant': '16.2', 'level': '16', 'difficulty': 'Master', 'id': 'a', 'name': 'A'},
        {'constant': '16.0', 'level': '16', 'difficulty': 'Master', 'id': 'c', 'name': 'C'},
    ]
    data, text = pages.table_page('', rows, group_by='constant')
    assert [tier['level'] for tier in data['tiers']] == ['16.2', '16', '15.9']
    assert data['groupBy'] == 'constant'
    assert data['span'] == '16.2 → 15.9'
    assert '定数 16.2 → 15.9' in text


def test_time_all_pages_cover_long_and_short_lists():
    long_songs = [{'title': f'L{i}', 'id': f'l{i}', 'chapter': 'Inf-1', 'time': f'4:{i:02d}'} for i in range(40)]
    short_songs = [{'title': f'S{i}', 'id': f's{i}', 'chapter': 'Inf-1', 'time': f'1:{i:02d}'} for i in range(40)]
    middle = {'title': 'M', 'id': 'm', 'chapter': 'Inf-1', 'time': '2:30'}
    result = pages.time_all_pages(long_songs + short_songs + [middle])
    # 一张图，不再分页
    assert len(result) == 1
    data, text = result[0]
    assert data['mode'] == 'all'
    assert len(data['long']) == 40 and len(data['short']) == 40
    assert data['longCount'] == 40 and data['shortCount'] == 40
    long_seconds = [int(r['duration'].split(':')[0]) * 60 + int(r['duration'].split(':')[1]) for r in data['long']]
    short_seconds = [int(r['duration'].split(':')[0]) * 60 + int(r['duration'].split(':')[1]) for r in data['short']]
    assert long_seconds == sorted(long_seconds, reverse=True)
    assert short_seconds == sorted(short_seconds)
    assert '2:30' not in text
