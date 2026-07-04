# -*- encoding: utf-8 -*-
"""Lanota Fandom API 更新逻辑。

本移植版只保留 MediaWiki API 方式：
- Songs 列表通过 API 读取 wikitext 后解析；
- 单曲详情也通过 API 读取 wikitext；
- 不包含网页 HTML 获取、cookies、浏览器或 Selenium 兜底。
"""

import re
import time
from typing import Any
from urllib.parse import quote, unquote, urlparse

from . import config
from . import function

try:
    import mwparserfromhell
    import requests

    API_DEPENDENCIES_AVAILABLE = True
except Exception:
    API_DEPENDENCIES_AVAILABLE = False


def clean_ref(text: str) -> str:
    return re.sub(r'<ref[^>]*>.*?</ref>|<ref[^/]*/>', '', str(text), flags=re.DOTALL)


def clean_wiki_links(text: str) -> str:
    source = str(text)
    source = re.sub(r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]', r'\1', source)
    return re.sub(r"'{2,}", '', source).strip()


def replace_br(text: str) -> str:
    return re.sub(r'<br\s*/?>', ', ', str(text), flags=re.IGNORECASE)


def classify(chap_left: str) -> str:
    value = str(chap_left).strip().lower()
    if value in ['0', '1', '2', '3', '4', '5', '6']:
        return 'main'
    if value in ['a', 'b', 'c', 'd', 'e', 'f']:
        return 'side'
    if value in ['event', 'time limited']:
        return 'event'
    if value in ['inf', 'infinite', 'subscription']:
        return 'subscription'
    return 'expansion'


def wiki_title_to_url(title: str) -> str:
    safe_title = quote(str(title).replace(' ', '_'), safe=':/()\'!-._~')
    return f'{config.api_base_url}/wiki/{safe_title}'


def wiki_url_to_page_name(url: str) -> str:
    path = urlparse(str(url)).path
    if '/wiki/' in path:
        return unquote(path.split('/wiki/', 1)[1]).replace('_', ' ')
    return unquote(path.strip('/')).replace('_', ' ')


def is_song_list_link(title: str) -> bool:
    title_text = str(title).strip()
    if not title_text or title_text.startswith(('File:', 'Category:', 'Special:', 'Template:')):
        return False
    lowered = title_text.lower()
    blocked = {
        'songs',
        'songlist',
        'main page',
        'lanota',
        'chapter',
        'chapters',
        'terms of use',
        'privacy policy',
    }
    return lowered not in blocked


def fetch_wikitext(session, page_name: str) -> str:
    page_name = str(page_name or '').split('#', 1)[0].strip()
    if not page_name:
        return ''

    params = {
        'action': 'query',
        'prop': 'revisions',
        'titles': page_name,
        'rvprop': 'content',
        'rvslots': 'main',
        'redirects': 1,
        'format': 'json',
        'formatversion': 2,
    }
    response = session.get(config.api_url, params=params, timeout=config.api_timeout_seconds)
    if response.status_code == 200:
        data = response.json()
        pages = (data.get('query') or {}).get('pages') or []
        for page in pages:
            revisions = page.get('revisions') or []
            if not revisions:
                continue
            slots = revisions[0].get('slots') or {}
            main_slot = slots.get('main') or {}
            content = main_slot.get('content') or revisions[0].get('content') or ''
            if content:
                return str(content)

    parse_params = {
        'action': 'parse',
        'page': page_name,
        'prop': 'wikitext',
        'redirects': 1,
        'format': 'json',
    }
    response = session.get(config.api_url, params=parse_params, timeout=config.api_timeout_seconds)
    if response.status_code != 200:
        return ''
    data = response.json()
    wikitext = ((data.get('parse') or {}).get('wikitext') or {}).get('*', '')
    return str(wikitext or '')


def extract_song_links_from_wikitext(wikitext: str) -> list[dict[str, str]]:
    result = []
    seen = set()
    rows = re.split(r'\n\|-\s*\n?', str(wikitext))
    for row in rows:
        row_text = row.strip()
        if not row_text.startswith('|') or row_text.startswith('|}'):
            continue

        first_link = None
        wikicode = mwparserfromhell.parse(row_text)
        for link in wikicode.filter_wikilinks(recursive=True):
            title = str(link.title).strip()
            if is_song_list_link(title):
                first_link = link
                break
        if first_link is None:
            continue

        title = str(first_link.title).strip()
        display_title = clean_wiki_links(str(first_link.text or first_link.title)).strip()
        if not display_title:
            display_title = title.replace('_', ' ')
        key = (title.lower(), display_title.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                'display_title': display_title,
                'href': wiki_title_to_url(title),
                'page_name': title,
            }
        )
    return result


def fetch_song_list_from_api(session) -> list[dict[str, str]]:
    wikitext = fetch_wikitext(session, 'Songs')
    if not wikitext:
        raise RuntimeError('API 未返回 Songs 页面 wikitext')
    songs_info = extract_song_links_from_wikitext(wikitext)
    if not songs_info:
        raise RuntimeError('API Songs 列表解析结果为空')
    return songs_info


def check_missing_fields(song: dict[str, Any]) -> list[str]:
    missing = []
    if not str(song.get('bpm', '')).strip():
        missing.append('bpm')
    if not str(song.get('time', '')).strip():
        missing.append('time')

    notes = song.get('notes', {})
    notes_missing = []
    if isinstance(notes, dict):
        for difficulty in ['whisper', 'acoustic', 'ultra', 'master']:
            if not str(notes.get(difficulty, '')).strip():
                notes_missing.append(difficulty)
    if notes_missing:
        missing.append(f'notes({",".join(notes_missing)})')

    legacy = song.get('Legacy', {})
    if isinstance(legacy, dict) and legacy:
        legacy_missing = []
        for field in ['MaxWhisper', 'MaxAcoustic', 'MaxUltra', 'MaxMaster']:
            if not str(legacy.get(field, '')).strip():
                legacy_missing.append(field)
        if legacy_missing:
            missing.append(f'legacy_notes({",".join(legacy_missing)})')
    return missing


def get_song_template(wikitext: str):
    wikicode = mwparserfromhell.parse(wikitext)
    return next((item for item in wikicode.filter_templates() if item.name.strip().lower() == 'song'), None), wikicode


def get_template_field(template, field_name: str) -> str:
    if not template or not template.has(field_name):
        return ''
    value = str(template.get(field_name).value)
    return replace_br(clean_wiki_links(clean_ref(value))).strip()


def parse_song_from_wikitext(wikitext: str, info: dict[str, str], next_id: int) -> dict[str, Any] | None:
    template, wikicode = get_song_template(wikitext)
    if template is None:
        return None

    raw_chap_left = get_template_field(template, 'Chapter')
    left_standard = raw_chap_left.replace('∞', 'Inf')
    chap_left_clean = 'Event' if left_standard.lower() == 'time limited' else left_standard
    chap_right = get_template_field(template, 'Id')
    real_chapter = f'{chap_left_clean}-{chap_right}' if chap_right else chap_left_clean

    chart_design = get_template_field(template, 'Chart Design')
    if chart_design.strip().upper() == 'SYM':
        chart_design = ''

    field_title = get_template_field(template, 'Song')
    display_title = info.get('display_title', '')
    real_title = field_title if len(field_title) >= len(display_title) else display_title
    source_url = info.get('href') or wiki_title_to_url(info.get('page_name', real_title))

    song = {
        'id': next_id,
        'title': real_title,
        'title_outside': display_title,
        'artist': get_template_field(template, 'Artist'),
        'chapter': real_chapter,
        'category': 'event' if chap_left_clean == 'Event' else classify(chap_left_clean),
        'difficulty': {
            'whisper': get_template_field(template, 'DiffWhisper'),
            'acoustic': get_template_field(template, 'DiffAcoustic'),
            'ultra': get_template_field(template, 'DiffUltra'),
            'master': get_template_field(template, 'DiffMaster'),
        },
        'time': get_template_field(template, 'Time'),
        'bpm': get_template_field(template, 'BPM'),
        'version': get_template_field(template, 'Version'),
        'area': get_template_field(template, 'Area'),
        'genre': get_template_field(template, 'Genre'),
        'vocals': get_template_field(template, 'Vocals'),
        'chart_design': chart_design,
        'cover_art': get_template_field(template, 'Cover Art'),
        'notes': {
            'whisper': get_template_field(template, 'MaxWhisper'),
            'acoustic': get_template_field(template, 'MaxAcoustic'),
            'ultra': get_template_field(template, 'MaxUltra'),
            'master': get_template_field(template, 'MaxMaster'),
        },
        'source_url': source_url,
    }

    if '==Trivia==' in wikitext:
        trivia_text = wikitext.split('==Trivia==', 1)[1]
        trivia = [clean_wiki_links(clean_ref(item.strip())) for item in re.findall(r'\*([^\n]+)', trivia_text)]
        if trivia:
            song['Trivia'] = trivia

    legacy = {}
    for template_item in wikicode.filter_templates():
        if template_item.name.strip().lower() == 'legacytable':
            for param in template_item.params:
                key = clean_wiki_links(str(param.name).strip())
                value = replace_br(clean_ref(str(param.value).strip()))
                if value:
                    legacy[key] = value
    song['Legacy'] = legacy
    return song


def update_existing_song_from_wiki(session, song: dict[str, Any]):
    source_url = song.get('source_url')
    if not source_url:
        return None, []
    wikitext = fetch_wikitext(session, wiki_url_to_page_name(source_url))
    if not wikitext:
        return None, []
    parsed_song = parse_song_from_wikitext(
        wikitext,
        {
            'display_title': str(song.get('title', '')),
            'href': str(source_url),
            'page_name': wiki_url_to_page_name(source_url),
        },
        int(song.get('id', 0) or 0),
    )
    if not parsed_song:
        return None, []

    before_missing = set(check_missing_fields(song))
    merged = dict(song)
    for key, value in parsed_song.items():
        if value not in [None, '', {}, []]:
            merged[key] = value
    after_missing = set(check_missing_fields(merged))
    updated_fields = sorted(before_missing - after_missing)
    return merged, updated_fields


def run_update() -> dict[str, Any]:
    if not API_DEPENDENCIES_AVAILABLE:
        raise RuntimeError('缺少依赖：requests 与 mwparserfromhell')

    session = requests.Session()
    session.headers.update(
        {
            'User-Agent': 'Mozilla/5.0 LanotaPlugin-OlivOS/1.0',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
    )

    data = function.load_song_data()
    original_count = len(data)
    songs_with_missing = [
        {
            'song': song,
            'missing': check_missing_fields(song),
        }
        for song in data
        if check_missing_fields(song)
    ]

    songs_info = fetch_song_list_from_api(session)
    existing_titles = {str(item.get('title', '')).lower() for item in data}
    existing_outside = {str(item.get('title_outside', '')).lower() for item in data if item.get('title_outside')}
    existing_chapters = {str(item.get('chapter', '')).lower() for item in data}
    candidates = [
        info
        for info in songs_info
        if info['display_title'].lower() not in existing_titles
        and info['display_title'].lower() not in existing_outside
    ]

    update_results = []
    for item in songs_with_missing:
        song = item['song']
        updated_song, updated_fields = update_existing_song_from_wiki(session, song)
        success = bool(updated_song and updated_fields)
        if updated_song:
            for index, old_song in enumerate(data):
                if old_song.get('chapter') == song.get('chapter'):
                    data[index] = updated_song
                    break
        update_results.append(
            {
                'title': song.get('title', ''),
                'chapter': song.get('chapter', ''),
                'missing': item['missing'],
                'updated': updated_fields,
                'success': success,
            }
        )
        time.sleep(0.2)

    new_titles = []
    for info in candidates:
        page_name = info.get('page_name') or wiki_url_to_page_name(info.get('href', ''))
        wikitext = fetch_wikitext(session, page_name)
        if not wikitext:
            continue
        parsed_song = parse_song_from_wikitext(wikitext, info, len(data) + 1)
        if not parsed_song:
            continue
        chapter = str(parsed_song.get('chapter', '')).lower()
        if chapter in existing_chapters:
            for old_song in data:
                if str(old_song.get('chapter', '')).lower() == chapter and not old_song.get('title_outside'):
                    old_song['title_outside'] = info.get('display_title', '')
            continue
        data.append(parsed_song)
        existing_chapters.add(chapter)
        existing_titles.add(str(parsed_song.get('title', '')).lower())
        new_titles.append(parsed_song.get('title', ''))
        time.sleep(0.2)

    function.save_song_data(data)
    return {
        'before': original_count,
        'missing_songs': len(songs_with_missing),
        'missing_updated': sum(1 for item in update_results if item.get('success')),
        'missing_results': update_results,
        'added': len(new_titles),
        'added_titles': new_titles,
        'total': len(data),
    }
