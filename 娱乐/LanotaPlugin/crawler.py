# -*- encoding: utf-8 -*-
"""Lanota Fandom API 更新逻辑。

本移植版只保留 MediaWiki API 方式：
- Songs 列表通过 API 读取 wikitext 后解析；
- 单曲详情也通过 API 读取 wikitext；
- 不包含网页 HTML 获取、cookies、浏览器或 Selenium 兜底。
"""

import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

from . import config
from . import function
from . import utils

try:
    import mwparserfromhell
    import requests

    API_DEPENDENCIES_AVAILABLE = True
except Exception:
    API_DEPENDENCIES_AVAILABLE = False


cover_index_lock = threading.RLock()


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
    parsed_url = urlparse(str(url))
    path = parsed_url.path
    if parsed_url.params:
        path = f'{path};{parsed_url.params}'
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


def normalize_cover_file_title(title: str) -> str:
    title = str(title).strip()
    if title.lower().startswith('image:'):
        return f'File:{title.split(":", 1)[1]}'
    return title


def extract_cover_file_from_wikitext(wikitext: str) -> str:
    for link in mwparserfromhell.parse(wikitext).filter_wikilinks(recursive=True):
        title = normalize_cover_file_title(str(link.title))
        if title.lower().startswith('file:'):
            return title
    return ''


def get_song_cover_variants(template) -> list[dict[str, str]]:
    """只保留上色版与全连版；单图或无状态差异时只保留一张。"""
    if not template:
        return []
    image_value = next(
        (str(param.value) for param in template.params if str(param.name).strip().casefold() == 'img'),
        '',
    )
    if not image_value:
        return []
    tabber_match = re.search(r'<tabber>(.*?)</tabber>', image_value, flags=re.I | re.S)
    variants = []
    if tabber_match:
        for tab_part in re.split(r'\|\-\|', tabber_match.group(1).strip()):
            if '=' not in tab_part:
                continue
            label, content = tab_part.split('=', 1)
            file_title = extract_cover_file_from_wikitext(content)
            if file_title:
                variants.append({'label': re.sub(r'\s+', ' ', label).strip(), 'file_title': file_title})
    else:
        file_title = extract_cover_file_from_wikitext(image_value)
        if file_title:
            variants.append({'label': 'Colored', 'file_title': file_title})

    if len(variants) <= 1:
        return variants

    selected = []
    for variant in variants:
        label = variant['label'].casefold()
        if label == 'before playing':
            continue
        if any(
            keyword in label
            for keyword in (
                'before/after playing',
                'after first play',
                'after playing',
                'after all combo',
                'after 3 challenges',
                'full combo',
            )
        ):
            selected.append(variant)
    if selected:
        return selected[:2]
    return [variants[-1]]


def get_song_cover_files(template) -> list[str]:
    """兼容曲库字段：返回筛选后的曲绘文件标题。"""
    return [variant['file_title'] for variant in get_song_cover_variants(template)]


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
        'cover_files': get_song_cover_files(template),
        'cover_variants': get_song_cover_variants(template),
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


def get_cover_cache_key(song: dict[str, Any]) -> str:
    """使用章节号作为曲绘缓存主键；章节号在 Lanota 曲库中唯一且稳定。"""
    return str(song.get('chapter', '')).strip().casefold()


def normalize_song_lookup_name(value: Any) -> str:
    """用于历史标题匹配：忽略大小写、空格与下划线差异。"""
    return re.sub(r'[\s_]+', '', str(value or '')).casefold()


def load_cover_index() -> dict[str, Any]:
    """合并随插件发布的曲绘索引与运行期缓存索引，运行期内容优先。"""
    seed_data = utils.read_json_file(utils.get_seed_cover_index_path(), {})
    runtime_data = utils.read_json_file(utils.get_cover_index_path(), {})
    result = seed_data if isinstance(seed_data, dict) else {}
    result = dict(result)
    if isinstance(runtime_data, dict):
        result.update(runtime_data)
    return result


def load_runtime_cover_index() -> dict[str, Any]:
    data = utils.read_json_file(utils.get_cover_index_path(), {})
    return data if isinstance(data, dict) else {}


def save_cover_index(index_data: dict[str, Any]) -> bool:
    return utils.save_json_file(utils.get_cover_index_path(), index_data)


def get_index_file_names(entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return []
    file_list = entry.get('files')
    if isinstance(file_list, list):
        return [str(item.get('file_name', '')).strip() for item in file_list if isinstance(item, dict)]
    legacy_file_name = str(entry.get('file_name', '')).strip()
    return [legacy_file_name] if legacy_file_name else []


def get_cover_paths_from_sources(song: dict[str, Any], index_sources) -> list[str]:
    cache_key = get_cover_cache_key(song)
    for index_data, cover_dir in index_sources:
        entry = index_data.get(cache_key, {}) if isinstance(index_data, dict) else {}
        file_path_list = [os.path.join(cover_dir, file_name) for file_name in get_index_file_names(entry)]
        if file_path_list and all(os.path.isfile(file_path) for file_path in file_path_list):
            return file_path_list
    return []


def get_cached_cover_paths(song: dict[str, Any]) -> list[str]:
    """返回歌曲全部已缓存曲绘路径，顺序为上色版、全连版。"""
    index_sources = (
        (load_runtime_cover_index(), utils.get_cover_art_dir()),
        (utils.read_json_file(utils.get_seed_cover_index_path(), {}), utils.get_seed_cover_art_dir()),
    )
    return get_cover_paths_from_sources(song, index_sources)


def get_cached_cover_path(song: dict[str, Any]) -> str:
    """兼容旧调用，返回第一张曲绘。"""
    cover_paths = get_cached_cover_paths(song)
    return cover_paths[0] if cover_paths else ''


def build_cover_file_name(song: dict[str, Any], mime_type: str, variant_index: int) -> str:
    extension_map = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
        'image/gif': '.gif',
    }
    extension = extension_map.get(mime_type.lower()) or '.img'
    chapter = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', str(song.get('chapter', 'unknown'))).strip(' ._')
    return f'{chapter or "unknown"}_{variant_index}{extension}'


def get_original_image_url(image_url: str) -> str:
    """要求 Wikia CDN 返回源 PNG/JPG，而不是自动转码的 WebP。"""
    parsed = urlparse(image_url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items['format'] = 'original'
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def fetch_image_info(session, file_title_list: list[str]) -> dict[str, dict[str, Any]]:
    """通过 imageinfo API 批量获取曲绘原图信息。"""
    result = {}
    unique_titles = list(dict.fromkeys(file_title_list))
    for offset in range(0, len(unique_titles), 50):
        params = {
            'action': 'query',
            'prop': 'imageinfo',
            'iiprop': 'url|mime|size',
            'titles': '|'.join(unique_titles[offset : offset + 50]),
            'format': 'json',
            'formatversion': 2,
        }
        response = session.get(config.api_url, params=params, timeout=config.api_timeout_seconds)
        response.raise_for_status()
        query = response.json().get('query') or {}
        edges = {}
        for item in query.get('normalized') or []:
            edges[str(item.get('from', ''))] = str(item.get('to', ''))
        for item in query.get('redirects') or []:
            edges[str(item.get('from', ''))] = str(item.get('to', ''))
        batch_info = {}
        for page in query.get('pages') or []:
            image_info_list = page.get('imageinfo') or []
            if image_info_list:
                batch_info[str(page.get('title', ''))] = image_info_list[0]
                result[str(page.get('title', '')).casefold()] = image_info_list[0]
        for original_title in unique_titles[offset : offset + 50]:
            target_title = original_title
            visited = set()
            while target_title in edges and target_title not in visited:
                visited.add(target_title)
                target_title = edges[target_title]
            image_info = batch_info.get(target_title)
            if image_info is None:
                image_info = next(
                    (info for title, info in batch_info.items() if title.casefold() == target_title.casefold()),
                    None,
                )
            if image_info is not None:
                result[original_title.casefold()] = image_info
    return result


def fetch_song_cover_sources(session, song: dict[str, Any]) -> list[dict[str, Any]]:
    """获取单曲筛选后的曲绘及 imageinfo；只访问 MediaWiki API。"""
    variants = song.get('cover_variants') if isinstance(song.get('cover_variants'), list) else []
    if not variants:
        source_url = str(song.get('source_url', '')).strip()
        if not source_url:
            return []
        page_name = wiki_url_to_page_name(source_url)
        wikitext = fetch_wikitext(session, page_name)
        template, _wikicode = get_song_template(wikitext)
        variants = get_song_cover_variants(template)
        if not variants:
            variants = [
                {'label': 'Colored', 'file_title': f'File:{page_name}.png'},
                {'label': 'Colored', 'file_title': f'File:{page_name}.jpg'},
                {'label': 'Colored', 'file_title': f'File:{page_name}.jpeg'},
            ]
    image_info_map = fetch_image_info(session, [str(item.get('file_title', '')) for item in variants])
    result = []
    for variant in variants:
        file_title = str(variant.get('file_title', ''))
        image_info = image_info_map.get(file_title.casefold())
        if image_info:
            result.append({**variant, 'image_info': image_info})
            if variant.get('label') == 'Colored' and len(variants) > 1:
                break
    return result[:2]


def download_cover_file(
    session,
    song: dict[str, Any],
    file_title: str,
    image_info: dict[str, Any],
    variant_index: int,
    force: bool = False,
) -> str:
    """下载一张原始 PNG/JPG 曲绘到运行期 data 目录。"""
    image_url = get_original_image_url(str(image_info.get('url', '')).strip())
    mime_type = str(image_info.get('mime', '')).strip().lower()
    if not image_url or not mime_type.startswith('image/'):
        return ''

    response = session.get(image_url, stream=True, timeout=config.cover_download_timeout_seconds)
    response.raise_for_status()
    content_type = str(response.headers.get('Content-Type', mime_type)).split(';', 1)[0].strip().lower()
    if not content_type.startswith('image/'):
        return ''
    if content_type == 'image/webp' and mime_type != 'image/webp':
        return ''
    file_name = build_cover_file_name(song, mime_type, variant_index)
    target_path = os.path.join(utils.get_cover_art_dir(), file_name)
    if os.path.isfile(target_path) and not force:
        return target_path
    temp_path = f'{target_path}.part'
    downloaded_bytes = 0
    try:
        with open(temp_path, 'wb') as file_object:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                downloaded_bytes += len(chunk)
                if downloaded_bytes > config.cover_download_max_bytes:
                    raise RuntimeError(f'曲绘超过大小限制：{file_title}')
                file_object.write(chunk)
        os.replace(temp_path, target_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    return target_path


def get_cover_cache_status(songs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    song_list = songs if isinstance(songs, list) else function.load_song_data()
    index_sources = (
        (load_runtime_cover_index(), utils.get_cover_art_dir()),
        (utils.read_json_file(utils.get_seed_cover_index_path(), {}), utils.get_seed_cover_art_dir()),
    )
    cached_path_lists = [get_cover_paths_from_sources(song, index_sources) for song in song_list]
    cached_count = sum(1 for path_list in cached_path_lists if path_list)
    return {
        'total': len(song_list),
        'cached': cached_count,
        'images': sum(len(path_list) for path_list in cached_path_lists),
        'missing': max(0, len(song_list) - cached_count),
        'runtime_dir': utils.get_cover_art_dir(),
        'seed_dir': utils.get_seed_cover_art_dir(),
    }


def ensure_song_covers(song: dict[str, Any], force: bool = False) -> list[str]:
    """优先返回全部本地曲绘；需要时通过 API 按需下载。"""
    cached_paths = get_cached_cover_paths(song)
    if cached_paths and not force:
        return cached_paths
    global_config = utils.load_global_config()
    if not force and not global_config.get('download_cover_on_demand', True):
        return []
    if not API_DEPENDENCIES_AVAILABLE:
        return []
    session = requests.Session()
    session.headers.update({'User-Agent': 'LanotaPlugin-OlivOS-Cover/1.0'})
    try:
        sources = fetch_song_cover_sources(session, song)
        paths = []
        file_entries = []
        for index, source in enumerate(sources, 1):
            file_title = str(source.get('file_title', ''))
            image_info = source.get('image_info') or {}
            path = download_cover_file(session, song, file_title, image_info, index, force=force)
            if not path:
                return []
            paths.append(path)
            file_entries.append(
                {
                    'label': str(source.get('label', '')),
                    'source_file': file_title,
                    'file_name': os.path.basename(path),
                    'url': get_original_image_url(str(image_info.get('url', ''))),
                    'size': os.path.getsize(path),
                }
            )
        if paths:
            with cover_index_lock:
                index_data = load_runtime_cover_index()
                index_data[get_cover_cache_key(song)] = {
                    'chapter': str(song.get('chapter', '')),
                    'files': file_entries,
                }
                save_cover_index(index_data)
        return paths
    except Exception:
        return []


def ensure_song_cover(song: dict[str, Any], force: bool = False) -> str:
    """兼容旧调用，返回第一张曲绘。"""
    cover_paths = ensure_song_covers(song, force=force)
    return cover_paths[0] if cover_paths else ''


def fetch_cover_file_map(session, songs: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    """批量读取歌曲页，返回“章节缓存键 -> 筛选后的曲绘变体”。"""
    result = {}
    songs_page_info = fetch_song_list_from_api(session)
    page_name_by_song_name = {}
    for info in songs_page_info:
        page_name = str(info.get('page_name', '')).strip()
        for name in (info.get('display_title'), page_name):
            normalized_name = normalize_song_lookup_name(name)
            if normalized_name:
                page_name_by_song_name[normalized_name] = page_name
    page_song_map = {}
    for song in songs:
        page_name = ''
        for name in (song.get('title_outside'), song.get('title')):
            page_name = page_name_by_song_name.get(normalize_song_lookup_name(name), '')
            if page_name:
                break
        source_url = str(song.get('source_url', '')).strip()
        if not page_name and source_url.startswith(f'{config.api_base_url}/wiki/'):
            page_name = wiki_url_to_page_name(source_url)
        if not page_name:
            page_name = str(song.get('title_outside') or song.get('title') or '').strip()
        if page_name:
            page_song_map[page_name] = song

    page_names = list(page_song_map)

    for offset in range(0, len(page_names), 50):
        params = {
            'action': 'query',
            'prop': 'revisions',
            'titles': '|'.join(page_names[offset : offset + 50]),
            'rvprop': 'content',
            'rvslots': 'main',
            'redirects': 1,
            'format': 'json',
            'formatversion': 2,
        }
        response = session.get(config.api_url, params=params, timeout=config.api_timeout_seconds)
        response.raise_for_status()
        query = response.json().get('query') or {}
        edges = {}
        for item in query.get('normalized') or []:
            edges[str(item.get('from', ''))] = str(item.get('to', ''))
        for item in query.get('redirects') or []:
            edges[str(item.get('from', ''))] = str(item.get('to', ''))
        pages_by_title = {str(page.get('title', '')): page for page in query.get('pages') or []}
        for original_title in page_names[offset : offset + 50]:
            target_title = original_title
            visited = set()
            while target_title in edges and target_title not in visited:
                visited.add(target_title)
                target_title = edges[target_title]
            page = pages_by_title.get(target_title)
            if page is None:
                page = next(
                    (item for title, item in pages_by_title.items() if title.casefold() == target_title.casefold()),
                    None,
                )
            if page is None:
                continue
            revisions = page.get('revisions') or []
            if not revisions:
                continue
            wikitext = revisions[0].get('slots', {}).get('main', {}).get('content', '')
            template, _wikicode = get_song_template(str(wikitext))
            cover_variants = get_song_cover_variants(template)
            if not template:
                continue
            song = page_song_map[original_title]
            result[get_cover_cache_key(song)] = cover_variants or [
                {'label': 'Colored', 'file_title': f'File:{page.get("title", "")}.png'}
            ]
    return result


def run_cover_update(force: bool = False, progress_callback=None) -> dict[str, Any]:
    """批量下载本地曲库的曲绘；该函数由骰主命令调用。"""
    if not API_DEPENDENCIES_AVAILABLE:
        raise RuntimeError('缺少依赖：requests 与 mwparserfromhell')
    songs = function.load_song_data()
    session = requests.Session()
    session.headers.update({'User-Agent': 'LanotaPlugin-OlivOS-Cover/1.0'})
    index_data = load_cover_index()
    cached_key_set = set()
    for cache_key, entry in index_data.items():
        file_names = get_index_file_names(entry)
        search_dirs = (utils.get_cover_art_dir(), utils.get_seed_cover_art_dir())
        if file_names and any(
            all(os.path.isfile(os.path.join(cover_dir, file_name)) for file_name in file_names)
            for cover_dir in search_dirs
        ):
            cached_key_set.add(str(cache_key))
    pending_songs = [song for song in songs if force or get_cover_cache_key(song) not in cached_key_set]
    cover_file_map = fetch_cover_file_map(session, pending_songs)
    all_file_titles = [
        str(variant.get('file_title', ''))
        for variants in cover_file_map.values()
        for variant in variants
    ]
    image_info_map = fetch_image_info(session, all_file_titles)
    downloaded = 0
    cached = len(songs) - len(pending_songs)
    failed = []

    def download_one(song: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        variants = cover_file_map.get(get_cover_cache_key(song), [])
        sources = []
        for variant in variants:
            file_title = str(variant.get('file_title', ''))
            image_info = image_info_map.get(file_title.casefold()) if file_title else None
            if image_info:
                sources.append({**variant, 'image_info': image_info})
        if not sources:
            return song, []
        worker_session = requests.Session()
        worker_session.headers.update({'User-Agent': 'LanotaPlugin-OlivOS-Cover/1.0'})
        try:
            file_entries = []
            for variant_index, source in enumerate(sources, 1):
                file_title = str(source.get('file_title', ''))
                image_info = source.get('image_info') or {}
                cover_path = download_cover_file(
                    worker_session,
                    song,
                    file_title,
                    image_info,
                    variant_index,
                    force=force,
                )
                if not cover_path:
                    return song, []
                file_entries.append(
                    {
                        'label': str(source.get('label', '')),
                        'source_file': file_title,
                        'file_name': os.path.basename(cover_path),
                        'url': get_original_image_url(str(image_info.get('url', ''))),
                        'size': os.path.getsize(cover_path),
                    }
                )
            return song, file_entries
        except Exception:
            return song, []

    completed = cached
    with ThreadPoolExecutor(max_workers=max(1, config.cover_download_workers)) as executor:
        future_list = [executor.submit(download_one, song) for song in pending_songs]
        for future in as_completed(future_list):
            song, file_entries = future.result()
            completed += 1
            if file_entries:
                downloaded += 1
                with cover_index_lock:
                    runtime_index = load_runtime_cover_index()
                    runtime_index[get_cover_cache_key(song)] = {
                        'chapter': str(song.get('chapter', '')),
                        'files': file_entries,
                    }
                    save_cover_index(runtime_index)
            else:
                failed.append(str(song.get('chapter') or song.get('title') or completed))
            if callable(progress_callback):
                progress_callback(completed, len(songs), downloaded, len(failed))
    return {
        'total': len(songs),
        'downloaded': downloaded,
        'cached': cached,
        'failed': len(failed),
        'failed_songs': failed,
        'cover_dir': utils.get_cover_art_dir(),
    }


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



PRESERVE_ON_FULL_CHECK = {'id', 'chapter', 'chart_design'}


def _normalize_compare_value(value: Any) -> Any:
    """把字段值规整成可比较的结构，避免 list/dict 顺序和空白噪音。"""
    if isinstance(value, dict):
        return {str(k): _normalize_compare_value(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize_compare_value(item) for item in value]
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    return value


def _song_field_diff(old_song: dict[str, Any], new_song: dict[str, Any], preserve_keys: set[str]) -> list[str]:
    changed = []
    keys = set(old_song.keys()) | set(new_song.keys())
    for key in sorted(keys):
        if key in preserve_keys:
            continue
        if _normalize_compare_value(old_song.get(key)) != _normalize_compare_value(new_song.get(key)):
            changed.append(key)
    return changed


def overwrite_existing_song_from_wiki(session, song: dict[str, Any]):
    """用 wiki 数据全量覆盖本地曲目，但保留 id / 章节号 / 谱师。"""
    source_url = song.get('source_url')
    page_name = ''
    if source_url:
        page_name = wiki_url_to_page_name(source_url)
    if not page_name:
        # 没有 source_url 时，尝试用 title_outside / title 作为 wiki 页名
        page_name = str(song.get('title_outside') or song.get('title') or '').strip()
    if not page_name:
        return None, []

    wikitext = fetch_wikitext(session, page_name)
    if not wikitext:
        return None, []

    display_title = str(song.get('title_outside') or song.get('title') or page_name)
    href = str(source_url or wiki_title_to_url(page_name))
    parsed_song = parse_song_from_wikitext(
        wikitext,
        {
            'display_title': display_title,
            'href': href,
            'page_name': page_name,
        },
        int(song.get('id', 0) or 0),
    )
    if not parsed_song:
        return None, []

    merged = dict(parsed_song)
    # 章节号与谱师绝对保留本地值；id 也保持本地
    for key in PRESERVE_ON_FULL_CHECK:
        if key in song:
            merged[key] = song.get(key)

    # Legacy 内的 Chart Design 也属于谱师信息，保持本地
    local_legacy = song.get('Legacy')
    wiki_legacy = merged.get('Legacy')
    if isinstance(local_legacy, dict) and isinstance(wiki_legacy, dict):
        if 'Chart Design' in local_legacy:
            wiki_legacy = dict(wiki_legacy)
            wiki_legacy['Chart Design'] = local_legacy.get('Chart Design', '')
            merged['Legacy'] = wiki_legacy
    elif isinstance(local_legacy, dict) and 'Chart Design' in local_legacy and not isinstance(wiki_legacy, dict):
        # wiki 没有 Legacy 时，不凭空塞整表；仅当本地本身有 Legacy 且 wiki 解析出 Legacy 才处理
        pass

    changed_fields = _song_field_diff(song, merged, PRESERVE_ON_FULL_CHECK)
    return merged, changed_fields


def run_full_check() -> dict[str, Any]:
    """对数据库中全部歌曲做 wiki 全量检测覆盖（不改章节号与谱师）。"""
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
    checked = 0
    updated = 0
    unchanged = 0
    failed = 0
    results = []

    for index, song in enumerate(data):
        checked += 1
        title = str(song.get('title') or song.get('title_outside') or song.get('chapter') or index)
        try:
            overwritten, changed_fields = overwrite_existing_song_from_wiki(session, song)
            if overwritten is None:
                failed += 1
                results.append(
                    {
                        'title': title,
                        'chapter': song.get('chapter', ''),
                        'success': False,
                        'changed': [],
                        'error': 'wiki 页面解析失败或无 source_url/标题',
                    }
                )
            elif changed_fields:
                data[index] = overwritten
                updated += 1
                results.append(
                    {
                        'title': title,
                        'chapter': song.get('chapter', ''),
                        'success': True,
                        'changed': changed_fields,
                    }
                )
            else:
                unchanged += 1
                results.append(
                    {
                        'title': title,
                        'chapter': song.get('chapter', ''),
                        'success': True,
                        'changed': [],
                    }
                )
        except Exception as exception_object:
            failed += 1
            results.append(
                {
                    'title': title,
                    'chapter': song.get('chapter', ''),
                    'success': False,
                    'changed': [],
                    'error': f'{type(exception_object).__name__}: {exception_object}',
                }
            )
        time.sleep(0.15)

    function.save_song_data(data)
    return {
        'mode': 'full_check',
        'before': original_count,
        'checked': checked,
        'updated': updated,
        'unchanged': unchanged,
        'failed': failed,
        'results': results,
        'total': len(data),
    }



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
