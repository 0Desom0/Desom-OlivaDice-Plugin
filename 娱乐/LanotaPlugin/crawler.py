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
from . import portal
from . import song_sync
from . import utils

try:
    import mwparserfromhell
    import requests

    API_DEPENDENCIES_AVAILABLE = True
except Exception:
    API_DEPENDENCIES_AVAILABLE = False


cover_index_lock = threading.RLock()
cover_adjustment_lock = threading.RLock()


def clean_ref(text: str) -> str:
    return re.sub(r'<ref[^>]*>.*?</ref>|<ref[^/]*/>', '', str(text), flags=re.DOTALL)


def clean_wiki_links(text: str) -> str:
    source = str(song_sync.strip_nowiki_markup(text))
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


def fetch_official_song_catalog() -> tuple[list[dict[str, Any]], list[str]]:
    """合并可用的国际服/国服官方曲库；重叠项优先国际服账号。"""
    catalogs = {}
    errors = []
    for region in ('global', 'china'):
        try:
            songs = portal.api_get('songs', region=region).get('songs', [])
            catalogs[region] = [
                dict(song, _portal_region=region)
                for song in song_sync.validate_official_catalog(songs)
            ]
        except Exception as exception_object:
            region_name = '国际服' if region == 'global' else '国服'
            errors.append(f'{region_name}: {type(exception_object).__name__}: {exception_object}')
    if not catalogs:
        raise RuntimeError('无法取得官网曲库：' + '；'.join(errors))

    primary_region = max(catalogs, key=lambda item: len(catalogs[item]))
    merged_by_id = {str(song['songId']): song for song in catalogs[primary_region]}
    for region in ('china', 'global'):
        for song in catalogs.get(region, []):
            merged_by_id[str(song['songId'])] = song
    merged = sorted(merged_by_id.values(), key=lambda song: str(song['songId']).casefold())
    return merged, errors


def get_rating_record_total(data: dict[str, Any], difficulty_index: int) -> str:
    for score in data.get('scores', []):
        if not isinstance(score, dict) or int(score.get('difficulty', -1)) != difficulty_index:
            continue
        rating_record = score.get('ratingRecord')
        if not isinstance(rating_record, dict):
            return ''
        total = rating_record.get('total')
        return str(total) if total not in [None, ''] else ''
    return ''


def fill_missing_notes_from_portal(
    song: dict[str, Any],
    official_song: dict[str, Any],
) -> dict[str, int]:
    """Fandom 物量为空时，按单曲个人成绩 ratingRecord.total 回退。"""
    notes = song.get('notes')
    if not isinstance(notes, dict):
        notes = {}
        song['notes'] = notes
    stats = {'requested': 0, 'filled': 0, 'unavailable': 0}
    region = str(official_song.get('_portal_region', 'global'))
    song_id = str(official_song.get('songId', ''))
    for difficulty_index, difficulty_name in enumerate(song_sync.DIFFICULTY_NAMES):
        if str(notes.get(difficulty_name, '') or '').strip():
            continue
        stats['requested'] += 1
        try:
            detail = portal.api_get(
                'score/song',
                params={'songId': song_id, 'difficulty': difficulty_index},
                region=region,
            )
            total = get_rating_record_total(detail, difficulty_index)
        except Exception:
            total = ''
        if total:
            notes[difficulty_name] = total
            stats['filled'] += 1
        else:
            notes[difficulty_name] = ''
            stats['unavailable'] += 1
    return stats


def match_and_apply_official_catalog(
    data: list[dict[str, Any]],
    official_catalog: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    match_result = song_sync.match_song_catalog(data, official_catalog)
    updated_data, update_stats = song_sync.apply_catalog_matches(data, official_catalog, match_result)
    return updated_data, update_stats, match_result


def official_review_reason(item: dict[str, Any], legacy: bool = False) -> str:
    candidates = item.get('candidates', [])
    first_candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
    score_field = 'score' if legacy else 'title_score'
    try:
        candidate_score = float(first_candidate.get(score_field, 0) or 0)
    except (TypeError, ValueError):
        candidate_score = 0.0
    official_title = str(item.get('official_title', '') or '').strip()
    song_id = str(item.get('song_id', '') or '').strip()
    chart_name = 'Legacy 曲目' if legacy else '曲目'
    if official_title and candidate_score >= 0.7:
        candidate_label = f'{song_id} {official_title}'.strip()
        return f'候选 {candidate_label}，未达到唯一可信匹配条件'
    return f'国际服 API 未找到可信的对应{chart_name}'


def check_missing_fields(song: dict[str, Any]) -> list[str]:
    missing = []
    if not str(song.get(song_sync.OFFICIAL_SONG_ID_FIELD, '') or '').strip():
        missing.append(song_sync.OFFICIAL_SONG_ID_FIELD)

    official_constant = song.get('official_constant', {})
    constant_missing = []
    for difficulty in song_sync.DIFFICULTY_NAMES:
        value = official_constant.get(difficulty) if isinstance(official_constant, dict) else None
        if value in [None, '']:
            constant_missing.append(difficulty)
    if constant_missing:
        missing.append(f'official_constant({",".join(constant_missing)})')

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


def has_missing_official_fields(song: dict[str, Any]) -> bool:
    """判断歌曲现行谱或 Legacy 是否缺少官方 songId/定数。"""
    if not isinstance(song, dict):
        return False

    def constant_map_missing(value: Any) -> bool:
        if not isinstance(value, dict):
            return True
        return any(value.get(difficulty) in [None, ''] for difficulty in song_sync.DIFFICULTY_NAMES)

    if (
        not str(song.get(song_sync.OFFICIAL_SONG_ID_FIELD, '') or '').strip()
        or constant_map_missing(song.get('official_constant'))
    ):
        return True

    legacy = song.get('Legacy')
    if isinstance(legacy, dict) and legacy:
        return (
            not str(legacy.get(song_sync.OFFICIAL_SONG_ID_FIELD, '') or '').strip()
            or constant_map_missing(legacy.get('official_constant'))
        )
    return False


def ensure_official_catalog_fields(
    data: list[dict[str, Any]],
    *,
    persist: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """查询前按需从官方 /songs 目录补全 ID、标级和定数。"""
    if not any(has_missing_official_fields(song) for song in data if isinstance(song, dict)):
        return data, {
            'attempted': False,
            'changed': False,
            'persisted': False,
            'changed_fields': {},
            'error': '',
        }

    try:
        official_catalog, source_errors = fetch_official_song_catalog()
        updated_data, update_stats, match_result = match_and_apply_official_catalog(
            data,
            official_catalog,
        )
    except Exception as exception_object:
        return data, {
            'attempted': True,
            'changed': False,
            'persisted': False,
            'changed_fields': {},
            'error': f'{type(exception_object).__name__}: {exception_object}',
        }

    changed = bool(update_stats.get('changed_songs'))
    persisted = False
    if changed and persist:
        persisted = function.save_song_data(song_sync.sanitize_song_markup(updated_data))
    return updated_data, {
        'attempted': True,
        'changed': changed,
        'persisted': persisted,
        'changed_fields': update_stats.get('changed_fields', {}),
        'matched': update_stats.get('matched', 0),
        'review': update_stats.get('review', 0),
        'source_errors': source_errors,
        'unmatched_official': match_result.get('unmatched_official', []),
        'error': '',
    }


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


def parse_song_from_wikitext(wikitext: str, info: dict[str, str], next_id: Any) -> dict[str, Any] | None:
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


def get_adjusted_cover_path(source_path: str) -> str:
    return os.path.join(utils.get_adjusted_cover_art_dir(), os.path.basename(source_path))


def _prepare_cover_for_display(source_path: str) -> tuple[str, str]:
    """把严格 2:1 的曲绘纵向拉伸 9/8；返回展示路径与处理状态。"""
    source_path = os.path.abspath(str(source_path))
    if not os.path.isfile(source_path):
        return source_path, 'failed'
    adjusted_path = get_adjusted_cover_path(source_path)
    if os.path.isfile(adjusted_path):
        return adjusted_path, 'cached'

    with cover_adjustment_lock:
        if os.path.isfile(adjusted_path):
            return adjusted_path, 'cached'
        temp_path = f'{adjusted_path}.{os.getpid()}.{threading.get_ident()}.part'
        adjusted_image = None
        try:
            from PIL import Image

            with Image.open(source_path) as source_image:
                source_image.load()
                width, height = source_image.size
                if width <= 0 or height <= 0 or width != height * 2:
                    return source_path, 'unchanged'
                image_format = source_image.format
                if not image_format:
                    return source_path, 'failed'
                target_height = round(height * 9 / 8)
                resampling = getattr(Image, 'Resampling', Image).LANCZOS
                adjusted_image = source_image.resize((width, target_height), resampling)
                save_options = {}
                if image_format.upper() in {'JPEG', 'JPG'}:
                    save_options.update({'quality': 100, 'subsampling': 0})
                elif image_format.upper() == 'WEBP':
                    save_options.update({'lossless': True, 'quality': 100})
                icc_profile = source_image.info.get('icc_profile')
                if icc_profile:
                    save_options['icc_profile'] = icc_profile
                adjusted_image.save(temp_path, format=image_format, **save_options)
            os.replace(temp_path, adjusted_path)
            return adjusted_path, 'created'
        except Exception as exception_object:
            utils.debug_log(
                None,
                f'曲绘纵向校正失败：{os.path.basename(source_path)}：'
                f'{type(exception_object).__name__}: {exception_object}',
            )
            return source_path, 'failed'
        finally:
            if adjusted_image is not None:
                adjusted_image.close()
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass


def prepare_cover_for_display(source_path: str) -> str:
    """返回曲绘最终展示路径；非 2:1 或处理失败时使用原图。"""
    display_path, _status = _prepare_cover_for_display(source_path)
    return display_path


def prepare_cover_paths_for_display(source_paths: list[str]) -> list[str]:
    return [prepare_cover_for_display(source_path) for source_path in source_paths]


def list_cover_source_paths() -> list[str]:
    """列出运行期与预置目录中的原始曲绘，同名时优先运行期文件。"""
    result_by_name = {}
    for cover_dir in (utils.get_cover_art_dir(), utils.get_seed_cover_art_dir()):
        if not os.path.isdir(cover_dir):
            continue
        try:
            for entry in os.scandir(cover_dir):
                if not entry.is_file() or entry.name == config.cover_index_file_name or entry.name.endswith('.part'):
                    continue
                result_by_name.setdefault(entry.name, entry.path)
        except Exception:
            continue
    return list(result_by_name.values())


def get_adjusted_cover_count() -> int:
    try:
        return sum(1 for entry in os.scandir(utils.get_adjusted_cover_art_dir()) if entry.is_file())
    except Exception:
        return 0


def run_cover_adjustment(progress_callback=None) -> dict[str, Any]:
    """批量生成缺失的展示曲绘；已有缓存直接跳过。"""
    source_paths = list_cover_source_paths()
    result = {
        'total': len(source_paths),
        'adjusted': 0,
        'cached': 0,
        'unchanged': 0,
        'failed': 0,
        'cover_dir': utils.get_adjusted_cover_art_dir(),
    }
    for current, source_path in enumerate(source_paths, 1):
        _display_path, status = _prepare_cover_for_display(source_path)
        if status in result:
            result[status] += 1
        elif status == 'created':
            result['adjusted'] += 1
        else:
            result['failed'] += 1
        if callable(progress_callback):
            progress_callback(current, len(source_paths), result)
    return result


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


def search_wiki_page_name(session, search_text: Any) -> str:
    """源页面失效时按歌曲名查找最接近的 Wiki 页面。"""
    clean_text = str(search_text or '').strip()
    if not clean_text:
        return ''
    response = session.get(
        config.api_url,
        params={
            'action': 'query',
            'list': 'search',
            'srsearch': clean_text,
            'srnamespace': 0,
            'srlimit': 5,
            'format': 'json',
            'formatversion': 2,
        },
        timeout=config.api_timeout_seconds,
    )
    response.raise_for_status()
    rows = response.json().get('query', {}).get('search', [])
    return str(rows[0].get('title', '') or '').strip() if rows else ''


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
            searched_page_name = search_wiki_page_name(
                session,
                song.get('title') or song.get('title_outside'),
            )
            if searched_page_name and searched_page_name.casefold() != page_name.casefold():
                searched_wikitext = fetch_wikitext(session, searched_page_name)
                searched_template, _wikicode = get_song_template(searched_wikitext)
                searched_variants = get_song_cover_variants(searched_template)
                if searched_variants:
                    page_name = searched_page_name
                    variants = searched_variants
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
        'adjusted_images': get_adjusted_cover_count(),
        'missing': max(0, len(song_list) - cached_count),
        'runtime_dir': utils.get_cover_art_dir(),
        'adjusted_dir': utils.get_adjusted_cover_art_dir(),
        'seed_dir': utils.get_seed_cover_art_dir(),
    }


def ensure_song_covers(song: dict[str, Any], force: bool = False) -> list[str]:
    """优先返回全部本地曲绘；需要时通过 API 按需下载。"""
    cached_paths = get_cached_cover_paths(song)
    if cached_paths and not force:
        return prepare_cover_paths_for_display(cached_paths)
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
        return prepare_cover_paths_for_display(paths)
    except Exception:
        return []


def ensure_song_cover(song: dict[str, Any], force: bool = False) -> str:
    """兼容旧调用，返回第一张曲绘。"""
    cover_paths = ensure_song_covers(song, force=force)
    return cover_paths[0] if cover_paths else ''


def update_new_song_covers(songs: list[dict[str, Any]]) -> dict[str, Any]:
    """下载本次新增歌曲的曲绘，并立即生成需要的 2:1 校正版。"""
    valid_songs = [song for song in songs if isinstance(song, dict)]
    result = {
        'total': len(valid_songs),
        'ready': 0,
        'images': 0,
        'adjusted': 0,
        'failed': 0,
        'failed_songs': [],
    }
    if not valid_songs:
        return result

    adjusted_dir = os.path.abspath(utils.get_adjusted_cover_art_dir())

    with ThreadPoolExecutor(max_workers=max(1, min(config.cover_download_workers, len(valid_songs)))) as executor:
        future_song_map = {
            executor.submit(ensure_song_covers, song, force=True): song
            for song in valid_songs
        }
        for future in as_completed(future_song_map):
            song = future_song_map[future]
            try:
                cover_paths = future.result()
            except Exception as exception_object:
                utils.debug_log(
                    None,
                    f'新曲曲绘自动处理失败：{song.get("title") or song.get("chapter") or "未知歌曲"}：'
                    f'{type(exception_object).__name__}: {exception_object}',
                )
                result['failed'] += 1
                result['failed_songs'].append(str(song.get('title') or song.get('chapter') or '未知歌曲'))
                continue
            if not cover_paths:
                result['failed'] += 1
                result['failed_songs'].append(str(song.get('title') or song.get('chapter') or '未知歌曲'))
                continue
            result['ready'] += 1
            result['images'] += len(cover_paths)
            result['adjusted'] += sum(
                os.path.dirname(os.path.abspath(path)) == adjusted_dir
                for path in cover_paths
            )
    return result


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


def update_existing_song_from_wiki(
    session,
    song: dict[str, Any],
    official_song: dict[str, Any],
    legacy_official_song: dict[str, Any] | None = None,
):
    before_missing = set(check_missing_fields(song))
    merged = dict(song)
    source_url = song.get('source_url')
    if source_url:
        wikitext = fetch_wikitext(session, wiki_url_to_page_name(source_url))
        if wikitext:
            parsed_song = parse_song_from_wikitext(
                wikitext,
                {
                    'display_title': str(song.get('title', '')),
                    'href': str(source_url),
                    'page_name': wiki_url_to_page_name(source_url),
                },
                song.get('id', ''),
            )
            if parsed_song:
                for key, value in parsed_song.items():
                    if value not in [None, '', {}, []]:
                        merged[key] = value
    merged, _official_changed = song_sync.apply_official_song(merged, official_song)
    if legacy_official_song is not None:
        merged, _legacy_changed = song_sync.apply_legacy_official_song(
            merged,
            legacy_official_song,
        )
    fill_missing_notes_from_portal(merged, official_song)
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


def overwrite_existing_song_from_wiki(
    session,
    song: dict[str, Any],
    official_song: dict[str, Any],
    legacy_official_song: dict[str, Any] | None = None,
):
    """用 wiki 数据全量覆盖本地曲目，但保留数字 id / 章节号 / 谱师。"""
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
        song.get('id', ''),
    )
    if not parsed_song:
        return None, []

    merged = dict(parsed_song)
    # 章节号、谱师与数字 id 绝对保留本地值。
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

    merged, _official_changed = song_sync.apply_official_song(merged, official_song)
    if legacy_official_song is not None:
        merged, _legacy_changed = song_sync.apply_legacy_official_song(
            merged,
            legacy_official_song,
        )
    fill_missing_notes_from_portal(merged, official_song)
    changed_fields = _song_field_diff(song, merged, PRESERVE_ON_FULL_CHECK)
    return merged, changed_fields


def sync_new_songs_from_wiki(
    session,
    data: list[dict[str, Any]],
    official_catalog: list[dict[str, Any]],
    matched_official_ids: set[str] | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """发现 Fandom 新曲并分配数字 id；新曲官方 ID 留给辅助脚本匹配。"""
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

    added_songs = []
    title_outside_updates = []
    official_pending = []
    next_numeric_id = song_sync.next_numeric_song_id(data)
    for info in candidates:
        page_name = info.get('page_name') or wiki_url_to_page_name(info.get('href', ''))
        wikitext = fetch_wikitext(session, page_name)
        if not wikitext:
            continue
        parsed_song = parse_song_from_wikitext(wikitext, info, next_numeric_id)
        if not parsed_song:
            continue

        chapter = str(parsed_song.get('chapter', '')).lower()
        if chapter in existing_chapters:
            matched_song = next(
                (old_song for old_song in data if str(old_song.get('chapter', '')).lower() == chapter),
                None,
            )
            if matched_song and not matched_song.get('title_outside'):
                display_title = info.get('display_title', '')
                if display_title:
                    if apply:
                        matched_song['title_outside'] = display_title
                    title_outside_updates.append(
                        {
                            'title': matched_song.get('title', ''),
                            'chapter': matched_song.get('chapter', ''),
                            'display_title': display_title,
                        }
                    )
            continue

        if apply:
            data.append(parsed_song)
        added_songs.append(parsed_song)
        official_pending.append(
            {
                'title': parsed_song.get('title', ''),
                'chapter': parsed_song.get('chapter', ''),
                'candidates': [],
                'reason': '新曲等待辅助脚本匹配 official_songid',
            }
        )
        next_numeric_id += 1
        existing_chapters.add(chapter)
        existing_titles.add(str(parsed_song.get('title', '')).lower())
        existing_outside.add(str(parsed_song.get('title_outside', '')).lower())
        time.sleep(0.2)

    return {
        'added_songs': added_songs,
        'title_outside_updates': title_outside_updates,
        'official_pending': official_pending,
    }


def run_full_check(apply: bool = False) -> dict[str, Any]:
    """全量检测 Fandom 元数据，并用 Portal 覆盖官方 ID、难度与定数。"""
    if not API_DEPENDENCIES_AVAILABLE:
        raise RuntimeError('缺少依赖：requests 与 mwparserfromhell')

    session = requests.Session()
    session.headers.update(
        {
            'User-Agent': 'Mozilla/5.0 LanotaPlugin-OlivOS/1.0',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
    )

    data = song_sync.sanitize_song_markup(function.load_song_data())
    original_count = len(data)
    official_catalog, official_source_errors = fetch_official_song_catalog()
    official_match_result = song_sync.match_song_catalog(data, official_catalog)
    _official_preview, official_update_stats = song_sync.apply_catalog_matches(
        data,
        official_catalog,
        official_match_result,
    )
    official_by_local_index = {
        int(item['local_index']): item['official_song']
        for item in official_match_result.get('matched', [])
    }
    legacy_official_by_local_index = {
        int(item['local_index']): item['official_song']
        for item in official_match_result.get('legacy_matched', [])
    }
    matched_official_ids = {
        str(item.get('song_id', ''))
        for item in official_match_result.get('matched', [])
        if item.get('song_id')
    }
    checked = 0
    updated = 0
    unchanged = 0
    failed = 0
    results = []

    for index, song in enumerate(data):
        checked += 1
        title = str(song.get('title') or song.get('title_outside') or song.get('chapter') or index)
        official_song = official_by_local_index.get(index)
        if official_song is None:
            failed += 1
            results.append(
                {
                    'title': title,
                    'chapter': song.get('chapter', ''),
                    'success': False,
                    'changed': [],
                    'error': '没有取得唯一可信的官方 songId 匹配',
                }
            )
            continue
        try:
            overwritten, changed_fields = overwrite_existing_song_from_wiki(
                session,
                song,
                official_song,
                legacy_official_by_local_index.get(index),
            )
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
                if apply:
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

    new_song_result = sync_new_songs_from_wiki(
        session,
        data,
        official_catalog,
        matched_official_ids=matched_official_ids,
        apply=apply,
    )
    added_songs = new_song_result.get('added_songs', [])
    title_outside_updates = new_song_result.get('title_outside_updates', [])
    official_pending = [
        {
            'title': item.get('title', ''),
            'chapter': item.get('chapter', ''),
            'candidates': item.get('candidates', []),
        }
        for item in official_match_result.get('review', [])
    ]
    official_pending.extend(
        {
            'title': item.get('title', ''),
            'chapter': item.get('chapter', ''),
            'chart_type': 'legacy',
            'candidates': item.get('candidates', []),
        }
        for item in official_match_result.get('legacy_review', [])
    )
    official_pending.extend(new_song_result.get('official_pending', []))

    if apply:
        data = song_sync.sanitize_song_markup(data)
        if not function.save_song_data(data):
            raise RuntimeError('写入 song_list.json 失败，请检查插件数据目录权限。')
    return {
        'mode': 'full_check_apply' if apply else 'full_check_detect',
        'apply': apply,
        'before': original_count,
        'checked': checked,
        'updated': updated,
        'added': len(added_songs),
        'added_titles': [str(song.get('title', '')) for song in added_songs],
        'title_outside_updated': len(title_outside_updates),
        'title_outside_updates': title_outside_updates,
        'official_matched': official_update_stats.get('matched', 0),
        'official_legacy_matched': official_update_stats.get('legacy_matched', 0),
        'official_updated': official_update_stats.get('changed_songs', 0),
        'official_pending': official_pending,
        'official_source_errors': official_source_errors,
        'unchanged': unchanged,
        'failed': failed,
        'results': results,
        'total': len(data),
        'projected_total': len(data) if apply else original_count + len(added_songs),
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

    data = song_sync.sanitize_song_markup(function.load_song_data())
    original_count = len(data)
    official_catalog, official_source_errors = fetch_official_song_catalog()
    data, official_update_stats, official_match_result = match_and_apply_official_catalog(
        data,
        official_catalog,
    )
    matched_official_ids = {
        str(item.get('song_id', ''))
        for item in official_match_result.get('matched', [])
        if item.get('song_id')
    }
    new_song_result = sync_new_songs_from_wiki(
        session,
        data,
        official_catalog,
        matched_official_ids=matched_official_ids,
        apply=True,
    )
    new_songs = [song for song in new_song_result.get('added_songs', []) if isinstance(song, dict)]
    new_titles = [str(song.get('title', '')) for song in new_songs]

    # Wiki 新曲是在首次匹配之后才加入的；同一轮更新必须用国际服目录再次匹配，
    # 否则新曲会被保存为没有 official_songid，直到下一次手动更新才会补齐。
    data, rematch_stats, official_match_result = match_and_apply_official_catalog(
        data,
        official_catalog,
    )
    official_update_stats = {
        'matched': rematch_stats.get('matched', official_update_stats.get('matched', 0)),
        'legacy_matched': rematch_stats.get(
            'legacy_matched', official_update_stats.get('legacy_matched', 0)
        ),
        'changed_songs': official_update_stats.get('changed_songs', 0)
        + rematch_stats.get('changed_songs', 0),
        'changed_fields': dict(official_update_stats.get('changed_fields', {})),
    }
    for field, count in rematch_stats.get('changed_fields', {}).items():
        official_update_stats['changed_fields'][field] = (
            official_update_stats['changed_fields'].get(field, 0) + count
        )

    # 新曲二次匹配完成后再检查缺失字段，确保新增曲也会进入本轮 Wiki/API 补全。
    official_by_id = {str(song.get('songId', '')): song for song in official_catalog}
    songs_with_missing = []
    for song in data:
        missing = check_missing_fields(song)
        if missing:
            songs_with_missing.append({'song': song, 'missing': missing})

    update_results = []
    for item in songs_with_missing:
        song = item['song']
        official_song = official_by_id.get(str(song.get(song_sync.OFFICIAL_SONG_ID_FIELD, '')))
        if official_song is None:
            update_results.append(
                {
                    'title': song.get('title', ''),
                    'chapter': song.get('chapter', ''),
                    'missing': item['missing'],
                    'updated': [],
                    'success': False,
                    'error': '国际服 API 未找到对应曲目，无法进行官方数据补全',
                }
            )
            continue
        legacy_data = song.get('Legacy', {})
        legacy_song_id = (
            str(legacy_data.get(song_sync.OFFICIAL_SONG_ID_FIELD, '') or '')
            if isinstance(legacy_data, dict)
            else ''
        )
        updated_song, updated_fields = update_existing_song_from_wiki(
            session,
            song,
            official_song,
            official_by_id.get(legacy_song_id),
        )
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

    data = song_sync.sanitize_song_markup(data)
    if not function.save_song_data(data):
        raise RuntimeError('写入 song_list.json 失败，请检查插件数据目录权限。')
    try:
        new_cover_result = update_new_song_covers(new_songs)
    except Exception as exception_object:
        utils.debug_log(
            None,
            f'新曲已写入，但自动处理曲绘失败：{type(exception_object).__name__}: {exception_object}',
        )
        new_cover_result = {
            'total': len(new_songs),
            'ready': 0,
            'images': 0,
            'adjusted': 0,
            'failed': len(new_songs),
            'failed_songs': [str(song.get('title') or song.get('chapter') or '未知歌曲') for song in new_songs],
        }
    official_pending = [
        {
            'title': item.get('title', ''),
            'chapter': item.get('chapter', ''),
            'song_id': item.get('song_id', ''),
            'official_title': item.get('official_title', ''),
            'reason': official_review_reason(item),
            'candidates': item.get('candidates', []),
        }
        for item in official_match_result.get('review', [])
    ]
    official_pending.extend(
        {
            'title': item.get('title', ''),
            'chapter': item.get('chapter', ''),
            'chart_type': 'legacy',
            'song_id': item.get('song_id', ''),
            'official_title': item.get('official_title', ''),
            'reason': official_review_reason(item, legacy=True),
            'candidates': item.get('candidates', []),
        }
        for item in official_match_result.get('legacy_review', [])
    )
    pending_keys = {
        (str(item.get('chapter', '')).casefold(), str(item.get('title', '')).casefold())
        for item in official_pending
    }
    matched_keys = {
        (str(item.get('chapter', '')).casefold(), str(item.get('title', '')).casefold())
        for match_type in ('matched', 'legacy_matched')
        for item in official_match_result.get(match_type, [])
    }
    for item in new_song_result.get('official_pending', []):
        key = (str(item.get('chapter', '')).casefold(), str(item.get('title', '')).casefold())
        if key not in pending_keys and key not in matched_keys:
            official_pending.append(item)
            pending_keys.add(key)
    return {
        'before': original_count,
        'missing_songs': len(songs_with_missing),
        'missing_updated': sum(1 for item in update_results if item.get('success')),
        'missing_results': update_results,
        'added': len(new_titles),
        'added_titles': new_titles,
        'new_cover_result': new_cover_result,
        'official_matched': official_update_stats.get('matched', 0),
        'official_legacy_matched': official_update_stats.get('legacy_matched', 0),
        'official_updated': official_update_stats.get('changed_songs', 0),
        'official_changed_fields': official_update_stats.get('changed_fields', {}),
        'official_pending': official_pending,
        'official_unmatched_catalog': official_match_result.get('unmatched_official', []),
        'official_source_errors': official_source_errors,
        'official_catalog_size': len(official_catalog),
        'total': len(data),
    }
