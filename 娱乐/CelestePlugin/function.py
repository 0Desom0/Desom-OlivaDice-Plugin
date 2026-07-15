# -*- encoding: utf-8 -*-
"""Celeste 社区 API、缓存、格式化与 Endless 业务逻辑。"""

import copy
import datetime
import hashlib
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from . import config
from . import utils


try:
    import yaml
except Exception:
    yaml = None


cache_lock = threading.RLock()
yaml_cache_lock_dict = {
    'mod_search_database': threading.RLock(),
    'everest_update': threading.RLock(),
}
database_memory_cache: dict[str, Any] = {}
updater_memory_cache: dict[str, Any] = {}
profile_memory_cache: dict[str, dict[str, Any]] = {}
search_memory_cache: dict[str, dict[str, Any]] = {}
detail_memory_cache: dict[str, dict[str, Any]] = {}


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁止 urllib 自动跟随跳转。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_timeout_seconds() -> int:
    value = utils.load_global_config().get('api_timeout_seconds', 20)
    try:
        return max(3, int(value))
    except Exception:
        return 20


def build_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        'User-Agent': 'CelestePlugin-OlivOS/1.3',
        'Accept': 'application/json, text/yaml, text/plain, */*',
    }
    if isinstance(extra_headers, dict):
        headers.update(extra_headers)
    return headers


def http_get(
    url: str,
    extra_headers: dict[str, str] | None = None,
    no_redirect: bool = False,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """执行 GET，并统一返回状态、响应头和字节内容。"""
    request = urllib.request.Request(url, headers=build_headers(extra_headers), method='GET')
    opener = urllib.request.build_opener(NoRedirectHandler()) if no_redirect else urllib.request.build_opener()
    try:
        timeout = get_timeout_seconds() if timeout_seconds is None else max(1, int(timeout_seconds))
        with opener.open(request, timeout=timeout) as response:
            return {
                'ok': True,
                'status': int(response.status),
                'headers': dict(response.headers.items()),
                'content': response.read(),
                'url': response.geturl(),
                'error': '',
            }
    except urllib.error.HTTPError as exception_object:
        content = b''
        try:
            content = exception_object.read()
        except Exception:
            pass
        return {
            'ok': exception_object.code in [301, 302, 303, 307, 308, 304],
            'status': int(exception_object.code),
            'headers': dict(exception_object.headers.items()),
            'content': content,
            'url': url,
            'error': f'HTTP {exception_object.code}',
        }
    except urllib.error.URLError as exception_object:
        return {
            'ok': False,
            'status': 0,
            'headers': {},
            'content': b'',
            'url': url,
            'error': utils.safe_str(exception_object.reason, '网络连接失败'),
        }
    except TimeoutError:
        return {'ok': False, 'status': 0, 'headers': {}, 'content': b'', 'url': url, 'error': '请求超时'}
    except Exception as exception_object:
        return {
            'ok': False,
            'status': 0,
            'headers': {},
            'content': b'',
            'url': url,
            'error': f'{type(exception_object).__name__}: {exception_object}',
        }


def decode_json_response(response: dict[str, Any]) -> Any:
    if not response.get('ok') or response.get('status') != 200:
        raise ValueError(response.get('error') or f'HTTP {response.get("status", 0)}')
    return json.loads(response.get('content', b'').decode('utf-8'))


def get_cache_paths(cache_name: str) -> tuple[str, str]:
    cache_dir = utils.get_shared_cache_dir()
    return (
        os.path.join(cache_dir, f'{cache_name}.yaml'),
        os.path.join(cache_dir, f'{cache_name}.meta.json'),
    )


def get_short_cache_path(cache_group: str, cache_key: str) -> str:
    safe_group = re.sub(r'[^A-Za-z0-9_-]', '', cache_group) or 'short'
    digest = hashlib.sha256(cache_key.encode('utf-8')).hexdigest()
    folder = utils.ensure_folder(os.path.join(utils.get_shared_cache_dir(), safe_group))
    return os.path.join(folder, f'{digest}.json')


def load_short_cache(
    memory_cache: dict[str, dict[str, Any]],
    cache_group: str,
    cache_key: str,
    ttl_seconds: int,
) -> Any:
    """读取短期内存/磁盘缓存；返回 None 表示未命中。"""
    if ttl_seconds <= 0:
        return None
    current_time = time.time()
    with cache_lock:
        memory_value = memory_cache.get(cache_key)
        if memory_value and current_time - float(memory_value.get('cached_at', 0) or 0) < ttl_seconds:
            return copy.deepcopy(memory_value.get('data'))
    cache_path = get_short_cache_path(cache_group, cache_key)
    cached_value = utils.read_json_file(cache_path, {})
    if not isinstance(cached_value, dict):
        return None
    if current_time - float(cached_value.get('cached_at', 0) or 0) >= ttl_seconds:
        return None
    with cache_lock:
        memory_cache[cache_key] = cached_value
    return copy.deepcopy(cached_value.get('data'))


def save_short_cache(
    memory_cache: dict[str, dict[str, Any]],
    cache_group: str,
    cache_key: str,
    data: Any,
) -> None:
    """保存短期内存/磁盘缓存，失败时不影响主查询。"""
    cache_value = {'cached_at': int(time.time()), 'data': copy.deepcopy(data)}
    with cache_lock:
        memory_cache[cache_key] = cache_value
    utils.save_json_file(get_short_cache_path(cache_group, cache_key), cache_value)


def parse_yaml_text(yaml_text: str) -> Any:
    if yaml is None:
        raise RuntimeError('缺少 PyYAML，无法读取 Celeste 社区数据库')
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
    return yaml.load(yaml_text, Loader=loader)


def load_cached_yaml(cache_name: str, url: str, ttl_seconds: int) -> dict[str, Any]:
    """串行更新同一组大型缓存，避免预热线程与消息线程同时写临时文件。"""
    target_lock = yaml_cache_lock_dict.setdefault(cache_name, threading.RLock())
    with target_lock:
        return _load_cached_yaml_unlocked(cache_name, url, ttl_seconds)


def _load_cached_yaml_unlocked(cache_name: str, url: str, ttl_seconds: int) -> dict[str, Any]:
    """使用 ETag 与本地文件缓存大型 YAML。"""
    yaml_path, meta_path = get_cache_paths(cache_name)
    current_time = time.time()
    memory_cache = database_memory_cache if cache_name == 'mod_search_database' else updater_memory_cache

    with cache_lock:
        if memory_cache.get('data') is not None and current_time - memory_cache.get('loaded_at', 0) < ttl_seconds:
            return {'ok': True, 'data': memory_cache['data'], 'error': '', 'from_cache': True}

    file_exists = os.path.exists(yaml_path)
    file_is_fresh = file_exists and current_time - os.path.getmtime(yaml_path) < ttl_seconds
    if file_is_fresh:
        try:
            parsed = parse_yaml_text(utils.read_text_file(yaml_path))
            with cache_lock:
                memory_cache.update({'data': parsed, 'loaded_at': current_time})
            return {'ok': True, 'data': parsed, 'error': '', 'from_cache': True}
        except Exception:
            pass

    meta = utils.read_json_file(meta_path, {})
    conditional_headers = {}
    if meta.get('etag'):
        conditional_headers['If-None-Match'] = utils.safe_str(meta['etag'])
    if meta.get('last_modified'):
        conditional_headers['If-Modified-Since'] = utils.safe_str(meta['last_modified'])

    response = http_get(url, extra_headers=conditional_headers)
    if response.get('status') == 304 and file_exists:
        try:
            parsed = parse_yaml_text(utils.read_text_file(yaml_path))
            os.utime(yaml_path, None)
            with cache_lock:
                memory_cache.update({'data': parsed, 'loaded_at': current_time})
            return {'ok': True, 'data': parsed, 'error': '', 'from_cache': True}
        except Exception as exception_object:
            return {'ok': False, 'data': None, 'error': f'缓存解析失败：{exception_object}', 'from_cache': True}

    if response.get('ok') and response.get('status') == 200:
        try:
            yaml_text = response['content'].decode('utf-8')
            parsed = parse_yaml_text(yaml_text)
            utils.save_text_file(yaml_path, yaml_text)
            header_dict = {key.lower(): value for key, value in response.get('headers', {}).items()}
            utils.save_json_file(
                meta_path,
                {
                    'etag': header_dict.get('etag', ''),
                    'last_modified': header_dict.get('last-modified', ''),
                    'updated_at': int(current_time),
                },
            )
            with cache_lock:
                memory_cache.update({'data': parsed, 'loaded_at': current_time})
            return {'ok': True, 'data': parsed, 'error': '', 'from_cache': False}
        except Exception as exception_object:
            response['error'] = f'数据解析失败：{exception_object}'

    if file_exists:
        try:
            parsed = parse_yaml_text(utils.read_text_file(yaml_path))
            with cache_lock:
                memory_cache.update({'data': parsed, 'loaded_at': current_time})
            return {
                'ok': True,
                'data': parsed,
                'error': response.get('error', ''),
                'from_cache': True,
            }
        except Exception as exception_object:
            return {'ok': False, 'data': None, 'error': f'网络及缓存均不可用：{exception_object}', 'from_cache': True}

    return {'ok': False, 'data': None, 'error': response.get('error', '社区数据库不可用'), 'from_cache': False}


def load_mod_database() -> dict[str, Any]:
    ttl = int(utils.load_global_config().get('database_cache_seconds', 21600))
    result = load_cached_yaml('mod_search_database', config.database_url, max(600, ttl))
    if result.get('ok') and not isinstance(result.get('data'), list):
        return {'ok': False, 'data': [], 'error': 'Mod 数据库格式异常'}
    return result


def build_updater_index(raw_data: Any) -> dict[tuple[str, int], list[dict[str, Any]]]:
    index: dict[tuple[str, int], list[dict[str, Any]]] = {}
    if not isinstance(raw_data, dict):
        return index
    for internal_name, raw_info in raw_data.items():
        if not isinstance(raw_info, dict):
            continue
        try:
            item_id = int(raw_info.get('GameBananaId', 0))
        except Exception:
            continue
        item_type = utils.safe_str(raw_info.get('GameBananaType', 'Mod'), 'Mod')
        if item_id <= 0:
            continue
        info = dict(raw_info)
        info['InternalName'] = utils.safe_str(internal_name)
        index.setdefault((item_type.lower(), item_id), []).append(info)
    for component_list in index.values():
        component_list.sort(key=lambda item: int(item.get('LastUpdate', 0) or 0), reverse=True)
    return index


def load_updater_index() -> dict[str, Any]:
    ttl = int(utils.load_global_config().get('database_cache_seconds', 21600))
    result = load_cached_yaml('everest_update', config.updater_url, max(600, ttl))
    if not result.get('ok'):
        return {'ok': False, 'data': {}, 'error': result.get('error', '')}
    with cache_lock:
        source_identity = id(result.get('data'))
        if updater_memory_cache.get('index_source_identity') != source_identity:
            updater_memory_cache['index'] = build_updater_index(result.get('data'))
            updater_memory_cache['index_source_identity'] = source_identity
        index = updater_memory_cache.get('index', {})
    return {'ok': True, 'data': index, 'error': result.get('error', '')}


def normalize_file(raw_file: Any) -> dict[str, Any]:
    if not isinstance(raw_file, dict):
        return {}
    file_id = raw_file.get('_idRow', raw_file.get('id', 0))
    try:
        file_id = int(file_id)
    except Exception:
        file_id = extract_file_id(raw_file.get('_sDownloadUrl', raw_file.get('URL', '')))
    if file_id <= 0:
        file_id = extract_file_id(
            raw_file.get('_sDownloadUrl', raw_file.get('URL', raw_file.get('url', '')))
        )
    return {
        'id': file_id,
        'name': utils.safe_str(raw_file.get('_sFile', raw_file.get('Name', raw_file.get('name', '')))),
        'size': int(raw_file.get('_nFilesize', raw_file.get('Size', raw_file.get('size', 0))) or 0),
        'created_at': int(
            raw_file.get('_tsDateAdded', raw_file.get('CreatedDate', raw_file.get('created_at', 0))) or 0
        ),
        'downloads': int(
            raw_file.get('_nDownloadCount', raw_file.get('Downloads', raw_file.get('downloads', 0))) or 0
        ),
        'url': utils.safe_str(
            raw_file.get(
                '_sDownloadUrl',
                raw_file.get('URL', raw_file.get('url', f'https://gamebanana.com/dl/{file_id}')),
            )
        ),
        'version': utils.safe_str(raw_file.get('_sVersion', raw_file.get('version', ''))),
        'description': utils.safe_str(
            raw_file.get('_sDescription', raw_file.get('Description', raw_file.get('description', '')))
        ),
        'archived': bool(raw_file.get('_bIsArchived', raw_file.get('archived', False))),
        'has_everest_yaml': bool(raw_file.get('HasEverestYaml', raw_file.get('has_everest_yaml', False))),
    }


def normalize_item(raw_item: Any) -> dict[str, Any]:
    if not isinstance(raw_item, dict):
        return {}
    item_id = raw_item.get('GameBananaId', raw_item.get('id', 0))
    try:
        item_id = int(item_id)
    except Exception:
        item_id = 0
    files = raw_item.get('Files', raw_item.get('files', []))
    if not isinstance(files, list):
        files = []
    screenshots = raw_item.get('Screenshots', raw_item.get('screenshots', []))
    mirrored_screenshots = raw_item.get('MirroredScreenshots', raw_item.get('mirrored_screenshots', []))
    if not isinstance(screenshots, list):
        screenshots = []
    if not isinstance(mirrored_screenshots, list):
        mirrored_screenshots = []
    screenshots = [utils.safe_str(url) for url in screenshots if utils.safe_str(url)]
    mirrored_screenshots = [utils.safe_str(url) for url in mirrored_screenshots if utils.safe_str(url)]
    provided_cover_urls = raw_item.get('cover_urls', [])
    if not isinstance(provided_cover_urls, list):
        provided_cover_urls = []
    provided_cover_urls = [utils.safe_str(url) for url in provided_cover_urls if utils.safe_str(url)]
    cover_url = utils.safe_str(raw_item.get('cover_url', ''))
    if provided_cover_urls:
        cover_url = provided_cover_urls[0]
    elif mirrored_screenshots:
        cover_url = mirrored_screenshots[0]
    elif not cover_url:
        cover_url = screenshots[0] if screenshots else ''
    return {
        'id': item_id,
        'item_type': utils.safe_str(raw_item.get('GameBananaType', raw_item.get('item_type', 'Mod')), 'Mod'),
        'name': utils.safe_str(raw_item.get('Name', raw_item.get('name', '未知标题')), '未知标题'),
        'author': utils.safe_str(raw_item.get('Author', raw_item.get('author', '未知作者')), '未知作者'),
        'description': utils.safe_str(raw_item.get('Description', raw_item.get('description', ''))),
        'text': utils.safe_str(raw_item.get('Text', raw_item.get('text', ''))),
        'page_url': utils.safe_str(
            raw_item.get('PageURL', raw_item.get('page_url', f'https://gamebanana.com/mods/{item_id}'))
        ),
        'category': utils.safe_str(raw_item.get('CategoryName', raw_item.get('category', ''))),
        'subcategory': utils.safe_str(raw_item.get('SubcategoryName', raw_item.get('subcategory', ''))),
        'category_id': raw_item.get('CategoryId', raw_item.get('category_id')),
        'subcategory_id': raw_item.get('SubcategoryId', raw_item.get('subcategory_id')),
        'views': int(raw_item.get('Views', raw_item.get('views', 0)) or 0),
        'likes': int(raw_item.get('Likes', raw_item.get('likes', 0)) or 0),
        'downloads': int(raw_item.get('Downloads', raw_item.get('downloads', 0)) or 0),
        'created_at': int(raw_item.get('CreatedDate', raw_item.get('created_at', 0)) or 0),
        'updated_at': int(raw_item.get('UpdatedDate', raw_item.get('updated_at', 0)) or 0),
        'files': [normalize_file(file_item) for file_item in files if isinstance(file_item, dict)],
        'screenshots': screenshots,
        'mirrored_screenshots': mirrored_screenshots,
        'cover_urls': provided_cover_urls,
        'cover_url': cover_url,
        'credits': copy.deepcopy(raw_item.get('credits', [])),
        'tags': list(raw_item.get('tags', [])) if isinstance(raw_item.get('tags', []), list) else [],
        'nsfw': bool(raw_item.get('nsfw', False)),
    }


def search_title(query: str) -> dict[str, Any]:
    query_text = utils.safe_str(query).strip()
    if not query_text:
        return {'ok': False, 'results': [], 'count': 0, 'error': '请输入搜索关键词'}
    cache_key = query_text.casefold()
    cache_ttl = max(0, int(utils.load_global_config().get('search_cache_seconds', 300)))
    cached_result = load_short_cache(search_memory_cache, 'searches', cache_key, cache_ttl)
    if isinstance(cached_result, dict):
        return cached_result
    url = f'{config.search_api_url}?{urllib.parse.urlencode({"q": query_text, "full": "true"})}'
    try:
        data = decode_json_response(http_get(url))
    except Exception as exception_object:
        fallback = search_local(['name'], query_text)
        if fallback.get('ok'):
            fallback['notice'] = '标题搜索接口暂时不可用，本次使用本地数据库的普通包含匹配。'
            save_short_cache(search_memory_cache, 'searches', cache_key, fallback)
            return fallback
        return {'ok': False, 'results': [], 'count': 0, 'error': utils.safe_str(exception_object)}
    if not isinstance(data, list):
        data = []
    results = [normalize_item(item) for item in data if isinstance(item, dict)]
    result = {'ok': True, 'results': results, 'count': len(results), 'error': ''}
    save_short_cache(search_memory_cache, 'searches', cache_key, result)
    return result


def make_index_item(item: dict[str, Any]) -> dict[str, Any]:
    """移除列表会话不需要的大字段，降低大分类查询的内存占用。"""
    compact_item = dict(item)
    compact_item['text'] = ''
    compact_item['description'] = ''
    compact_item['files'] = []
    compact_item['credits'] = []
    compact_item['tags'] = []
    compact_item['screenshots'] = compact_item.get('screenshots', [])[:1]
    compact_item['mirrored_screenshots'] = compact_item.get('mirrored_screenshots', [])[:1]
    return compact_item


def search_local(field_names: list[str], query: str, limit: int = 10000) -> dict[str, Any]:
    query_text = utils.safe_str(query).strip().casefold()
    if not query_text:
        return {'ok': False, 'results': [], 'count': 0, 'error': '请输入筛选内容'}
    database_result = load_mod_database()
    if not database_result.get('ok'):
        return {'ok': False, 'results': [], 'count': 0, 'error': database_result.get('error', '')}

    exact_matches = []
    contains_matches = []
    for raw_item in database_result.get('data', []):
        normalized = normalize_item(raw_item)
        values = [utils.safe_str(normalized.get(field_name, '')).casefold() for field_name in field_names]
        if query_text in values:
            exact_matches.append(make_index_item(normalized))
        elif any(query_text in value for value in values):
            contains_matches.append(make_index_item(normalized))
    results = exact_matches + contains_matches
    results.sort(key=lambda item: (item.get('downloads', 0), item.get('likes', 0)), reverse=True)
    return {'ok': True, 'results': results[:limit], 'count': len(results), 'error': ''}


def search_author(query: str) -> dict[str, Any]:
    result = search_local(['author'], query)
    if not result.get('ok'):
        return result
    query_text = utils.safe_str(query).strip().casefold()
    result_map = {
        (item.get('item_type', '').lower(), item.get('id', 0)): item for item in result.get('results', [])
    }
    profile_dir = os.path.join(utils.get_shared_cache_dir(), 'profiles')
    if os.path.isdir(profile_dir):
        for file_name in os.listdir(profile_dir):
            if not file_name.endswith('.json'):
                continue
            cached = utils.read_json_file(os.path.join(profile_dir, file_name), {})
            credited_names = []
            for group in cached.get('credits', []):
                credited_names.extend(author.get('name', '') for author in group.get('authors', []))
            if any(query_text in utils.safe_str(name).casefold() for name in credited_names):
                item = make_index_item(normalize_item(cached))
                result_map[(item.get('item_type', '').lower(), item.get('id', 0))] = item
    results = list(result_map.values())
    results.sort(key=lambda item: (item.get('downloads', 0), item.get('likes', 0)), reverse=True)
    return {
        'ok': True,
        'results': results,
        'count': len(results),
        'error': '',
        'notice': '主投稿者搜索覆盖完整社区数据库；合作者搜索仅覆盖已缓存过的详情。',
    }


def search_category(query: str) -> dict[str, Any]:
    return search_local(['category', 'subcategory'], query)


def get_profile_cache_path(item_type: str, item_id: int) -> str:
    folder = utils.ensure_folder(os.path.join(utils.get_shared_cache_dir(), 'profiles'))
    safe_type = re.sub(r'[^A-Za-z0-9_-]', '', item_type) or 'Mod'
    return os.path.join(folder, f'{safe_type}_{item_id}.json')


def normalize_credit_groups(raw_credits: Any) -> list[dict[str, Any]]:
    if isinstance(raw_credits, list):
        groups = raw_credits
    elif isinstance(raw_credits, dict) and '_aAuthors' in raw_credits:
        groups = [raw_credits]
    elif isinstance(raw_credits, dict):
        groups = list(raw_credits.values())
    else:
        groups = []
    result = []
    for raw_group in groups:
        if not isinstance(raw_group, dict):
            continue
        raw_authors = raw_group.get('_aAuthors', [])
        if isinstance(raw_authors, dict):
            raw_authors = [raw_authors]
        authors = []
        for raw_author in raw_authors if isinstance(raw_authors, list) else []:
            if not isinstance(raw_author, dict):
                continue
            authors.append(
                {
                    'name': utils.safe_str(raw_author.get('_sName', '')),
                    'role': utils.safe_str(raw_author.get('_sRole', '')),
                    'id': raw_author.get('_idRow'),
                    'url': utils.safe_str(raw_author.get('_sProfileUrl', '')),
                }
            )
        if authors:
            result.append({'group': utils.safe_str(raw_group.get('_sGroupName', '署名')), 'authors': authors})
    return result


def normalize_profile(raw_profile: Any, item_type: str, item_id: int) -> dict[str, Any]:
    if not isinstance(raw_profile, dict):
        return {}
    raw_tags = raw_profile.get('_aTags', [])
    if isinstance(raw_tags, dict):
        raw_tags = [raw_tags]
    tags = []
    for raw_tag in raw_tags if isinstance(raw_tags, list) else []:
        value = raw_tag.get('_sValue', '') if isinstance(raw_tag, dict) else raw_tag
        value_text = utils.safe_str(value).strip()
        if value_text and value_text not in tags:
            tags.append(value_text)

    submitter = raw_profile.get('_aSubmitter', {})
    category = raw_profile.get('_aCategory', {})
    super_category = raw_profile.get('_aSuperCategory', {})
    game = raw_profile.get('_aGame', {})
    root_category_name = utils.safe_str(super_category.get('_sName', '')) if isinstance(super_category, dict) else ''
    leaf_category_name = utils.safe_str(category.get('_sName', '')) if isinstance(category, dict) else ''
    if not root_category_name:
        root_category_name = leaf_category_name
        leaf_category_name = ''
    raw_files = raw_profile.get('_aFiles', [])
    if not isinstance(raw_files, list):
        raw_files = []
    preview_media = raw_profile.get('_aPreviewMedia', {})
    raw_images = preview_media.get('_aImages', []) if isinstance(preview_media, dict) else []
    if isinstance(raw_images, dict):
        raw_images = [raw_images]
    screenshots = []
    for raw_image in raw_images if isinstance(raw_images, list) else []:
        if not isinstance(raw_image, dict):
            continue
        base_url = utils.safe_str(raw_image.get('_sBaseUrl', '')).rstrip('/')
        file_name = utils.safe_str(raw_image.get('_sFile', ''))
        if file_name.startswith(('http://', 'https://')):
            image_url = file_name
        elif base_url and file_name:
            image_url = f'{base_url}/{file_name}'
        else:
            image_url = ''
        if image_url and image_url not in screenshots:
            screenshots.append(image_url)
    return {
        'id': item_id,
        'item_type': item_type,
        'name': utils.safe_str(raw_profile.get('_sName', '未知标题'), '未知标题'),
        'page_url': utils.safe_str(
            raw_profile.get('_sProfileUrl', f'https://gamebanana.com/{item_type.lower()}s/{item_id}')
        ),
        'author': utils.safe_str(submitter.get('_sName', '')) if isinstance(submitter, dict) else '',
        'description': utils.safe_str(raw_profile.get('_sDescription', '')),
        'text': utils.safe_str(raw_profile.get('_sText', '')),
        'category': root_category_name,
        'subcategory': leaf_category_name,
        'views': int(raw_profile.get('_nViewCount', 0) or 0),
        'likes': int(raw_profile.get('_nLikeCount', 0) or 0),
        'downloads': int(raw_profile.get('_nDownloadCount', 0) or 0),
        'created_at': int(raw_profile.get('_tsDateAdded', 0) or 0),
        'updated_at': int(raw_profile.get('_tsDateModified', 0) or 0),
        'credits': normalize_credit_groups(raw_profile.get('_aCredits', [])),
        'tags': tags,
        'files': [normalize_file(file_item) for file_item in raw_files],
        'screenshots': screenshots,
        'cover_url': screenshots[0] if screenshots else '',
        'nsfw': bool(raw_profile.get('_bIsNsfw', False))
        or utils.safe_str(raw_profile.get('_sInitialVisibility', 'show')).lower() not in ['', 'show', 'visible']
        or bool(raw_profile.get('_aContentRatings')),
        'game_id': int(game.get('_idRow', 0) or 0) if isinstance(game, dict) else 0,
        'page_version': utils.safe_str(raw_profile.get('_sVersion', '')),
        'cached_at': int(time.time()),
    }


def get_profile(item_type: str, item_id: int, force_refresh: bool = False) -> dict[str, Any]:
    cache_key = f'{item_type.lower()}:{item_id}'
    ttl = int(utils.load_global_config().get('profile_cache_seconds', 21600))
    current_time = time.time()
    with cache_lock:
        memory_value = profile_memory_cache.get(cache_key)
        if memory_value and not force_refresh and current_time - memory_value.get('cached_at', 0) < ttl:
            return {'ok': True, 'data': copy.deepcopy(memory_value), 'error': '', 'from_cache': True}

    cache_path = get_profile_cache_path(item_type, item_id)
    cached_value = utils.read_json_file(cache_path, {})
    if (
        cached_value
        and not force_refresh
        and current_time - float(cached_value.get('cached_at', 0) or 0) < ttl
    ):
        with cache_lock:
            profile_memory_cache[cache_key] = cached_value
        return {'ok': True, 'data': copy.deepcopy(cached_value), 'error': '', 'from_cache': True}

    url = config.gamebanana_profile_url.format(item_type=item_type, item_id=item_id)
    try:
        raw_profile = decode_json_response(http_get(url))
        normalized = normalize_profile(raw_profile, item_type, item_id)
        if not normalized:
            raise ValueError('GameBanana 详情为空')
        utils.save_json_file(cache_path, normalized)
        with cache_lock:
            profile_memory_cache[cache_key] = normalized
        return {'ok': True, 'data': copy.deepcopy(normalized), 'error': '', 'from_cache': False}
    except Exception as exception_object:
        if cached_value:
            return {
                'ok': True,
                'data': cached_value,
                'error': utils.safe_str(exception_object),
                'from_cache': True,
            }
        return {'ok': False, 'data': {}, 'error': utils.safe_str(exception_object), 'from_cache': False}


def get_wegfan_cover_url(item_type: str, item_id: int, item_name: str) -> str:
    """通过 WEGFan 搜索接口按标题查询，再用 GameBanana ID 精确核对封面。"""
    query_name = utils.safe_str(item_name).strip()
    if item_id <= 0 or not query_name or query_name == '未知标题':
        return ''
    query = urllib.parse.urlencode(
        {
            'search': query_name,
            'page': 1,
            'size': 20,
            'section': item_type,
            'sort': 'updateAdded',
        }
    )
    timeout = int(utils.load_global_config().get('cover_mirror_lookup_timeout_seconds', 6))
    try:
        response = http_get(f'{config.wegfan_search_url}?{query}', timeout_seconds=max(2, timeout))
        raw_result = decode_json_response(response)
    except Exception:
        return ''
    data = raw_result.get('data', {}) if isinstance(raw_result, dict) else {}
    content = data.get('content', []) if isinstance(data, dict) else []
    for raw_item in content if isinstance(content, list) else []:
        if not isinstance(raw_item, dict):
            continue
        try:
            gamebanana_id = int(raw_item.get('gameBananaId', 0) or 0)
        except Exception:
            continue
        section = utils.safe_str(raw_item.get('gameBananaSection', '')).casefold()
        if gamebanana_id != item_id or (section and section != item_type.casefold()):
            continue
        screenshots = raw_item.get('screenshots', [])
        if not isinstance(screenshots, list):
            return ''
        for screenshot in screenshots:
            if not isinstance(screenshot, dict):
                continue
            image_url = utils.safe_str(screenshot.get('url', '')).strip()
            if image_url:
                return image_url
    return ''


def apply_cover_priority(detail: dict[str, Any], wegfan_cover_url: str = '') -> dict[str, Any]:
    """按 WEGFan、0x0ade、GameBanana 原站的顺序选择封面。"""
    result = copy.deepcopy(detail)
    candidate_urls = []
    source_groups = [
        [wegfan_cover_url],
        result.get('mirrored_screenshots', []),
        result.get('screenshots', []),
        [result.get('cover_url', '')],
    ]
    for source_group in source_groups:
        if not isinstance(source_group, list):
            continue
        for raw_url in source_group:
            image_url = utils.safe_str(raw_url).strip()
            if image_url and image_url not in candidate_urls:
                candidate_urls.append(image_url)
    result['cover_urls'] = candidate_urls
    result['cover_url'] = candidate_urls[0] if candidate_urls else ''
    return result


def get_item_by_id(
    item_id: int,
    item_type: str = 'Mod',
    include_cover_mirror: bool = True,
) -> dict[str, Any]:
    detail_cache_key = f'{item_type.casefold()}:{item_id}'
    detail_cache_ttl = max(0, int(utils.load_global_config().get('detail_cache_seconds', 600)))
    cached_detail = load_short_cache(
        detail_memory_cache,
        'details',
        detail_cache_key,
        detail_cache_ttl,
    )
    if isinstance(cached_detail, dict) and cached_detail.get('id'):
        return {'ok': True, 'data': cached_detail, 'error': '', 'from_cache': True}

    query = urllib.parse.urlencode({'itemtype': item_type, 'itemid': item_id})
    try:
        raw_item = decode_json_response(http_get(f'{config.info_api_url}?{query}'))
        base_item = normalize_item(raw_item)
        community_ok = True
    except Exception as exception_object:
        base_item = {'id': item_id, 'item_type': item_type}
        community_error = utils.safe_str(exception_object)
        community_ok = False
    else:
        community_error = ''

    profile_result = get_profile(item_type, item_id)
    if not base_item.get('name') and not profile_result.get('ok'):
        return {
            'ok': False,
            'data': {},
            'error': community_error or profile_result.get('error', '未找到对应 Mod'),
        }

    detail = dict(base_item)
    if profile_result.get('ok'):
        profile = profile_result['data']
        game_id = int(profile.get('game_id', 0) or 0)
        if game_id and game_id != 6460:
            return {'ok': False, 'data': {}, 'error': '该 GameBanana 条目不属于 Celeste'}
        if not community_ok and game_id != 6460:
            return {'ok': False, 'data': {}, 'error': '无法确认该 GameBanana 条目属于 Celeste'}
        for key, value in profile.items():
            if value not in ['', None, [], {}, 0, False]:
                detail[key] = value
    detail.setdefault('name', f'{item_type} {item_id}')
    detail.setdefault('author', '未知作者')
    detail.setdefault('page_url', f'https://gamebanana.com/{item_type.lower()}s/{item_id}')

    updater_result = load_updater_index()
    detail['updater_components'] = updater_result.get('data', {}).get((item_type.lower(), item_id), [])
    detail['stale_warning'] = profile_result.get('error', '') or community_error or updater_result.get('error', '')
    wegfan_cover_url = ''
    if include_cover_mirror:
        wegfan_cover_url = get_wegfan_cover_url(item_type, item_id, detail.get('name', ''))
    detail = apply_cover_priority(detail, wegfan_cover_url)
    if include_cover_mirror:
        save_short_cache(detail_memory_cache, 'details', detail_cache_key, detail)
    return {'ok': True, 'data': detail, 'error': '', 'from_cache': False}


def hydrate_item(item: dict[str, Any]) -> dict[str, Any]:
    return get_item_by_id(int(item.get('id', 0)), utils.safe_str(item.get('item_type', 'Mod'), 'Mod'))


def search_tag(query: str) -> dict[str, Any]:
    """完整筛选社区子分类，并用详情缓存补充 GameBanana 自由标签。"""
    query_text = utils.safe_str(query).strip().casefold()
    if not query_text:
        return {'ok': False, 'results': [], 'count': 0, 'error': '请输入标签'}

    result_map: dict[tuple[str, int], dict[str, Any]] = {}
    subcategory_result = search_local(['subcategory'], query)
    if subcategory_result.get('ok'):
        for item in subcategory_result.get('results', []):
            result_map[(item.get('item_type', '').lower(), item.get('id', 0))] = item

    profile_dir = os.path.join(utils.get_shared_cache_dir(), 'profiles')
    if os.path.isdir(profile_dir):
        for file_name in os.listdir(profile_dir):
            if not file_name.endswith('.json'):
                continue
            cached = utils.read_json_file(os.path.join(profile_dir, file_name), {})
            tags = [utils.safe_str(tag).casefold() for tag in cached.get('tags', [])]
            if any(query_text in tag for tag in tags):
                normalized = normalize_item(cached)
                result_map[(normalized.get('item_type', '').lower(), normalized.get('id', 0))] = normalized

    title_result = search_title(query)
    for item in title_result.get('results', [])[:8]:
        detail_result = hydrate_item(item)
        if not detail_result.get('ok'):
            continue
        detail = detail_result['data']
        tags = [utils.safe_str(tag).casefold() for tag in detail.get('tags', [])]
        if any(query_text in tag for tag in tags):
            result_map[(detail.get('item_type', '').lower(), detail.get('id', 0))] = normalize_item(detail)

    results = list(result_map.values())
    results.sort(key=lambda item: (item.get('downloads', 0), item.get('likes', 0)), reverse=True)
    return {
        'ok': True,
        'results': results,
        'count': len(results),
        'error': '',
        'partial': True,
    }


def extract_file_id(url_or_id: Any) -> int:
    try:
        numeric_id = int(url_or_id)
        if numeric_id > 0:
            return numeric_id
    except Exception:
        pass
    matched = re.search(r'(\d+)(?:\D*)$', utils.safe_str(url_or_id))
    return int(matched.group(1)) if matched else 0


def group_updater_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for component in components:
        file_id = extract_file_id(component.get('GameBananaFileId', 0))
        if file_id <= 0:
            file_id = extract_file_id(component.get('URL', ''))
        if file_id <= 0:
            continue
        group = grouped.setdefault(
            file_id,
            {
                'file_id': file_id,
                'components': [],
                'versions': [],
                'entries': [],
                'size': int(component.get('Size', 0) or 0),
                'last_update': int(component.get('LastUpdate', 0) or 0),
                'verified': True,
            },
        )
        internal_name = utils.safe_str(component.get('InternalName', ''))
        version = utils.safe_str(component.get('Version', '未知'))
        if internal_name and internal_name not in group['components']:
            group['components'].append(internal_name)
        if version and version not in group['versions']:
            group['versions'].append(version)
        entry = {'name': internal_name or f'文件 {file_id}', 'version': version or '未知'}
        if entry not in group['entries']:
            group['entries'].append(entry)
        group['last_update'] = max(group['last_update'], int(component.get('LastUpdate', 0) or 0))
        group['size'] = max(group['size'], int(component.get('Size', 0) or 0))
    return sorted(grouped.values(), key=lambda item: item.get('last_update', 0), reverse=True)


def build_download_groups(detail: dict[str, Any]) -> list[dict[str, Any]]:
    groups = group_updater_components(detail.get('updater_components', []))
    if groups:
        return groups
    files = [file_item for file_item in detail.get('files', []) if not file_item.get('archived')]
    files.sort(key=lambda item: item.get('created_at', 0), reverse=True)
    if not files:
        return []
    fallback_groups = []
    for file_item in files:
        file_id = int(file_item.get('id', 0) or 0)
        if file_id <= 0:
            continue
        version = file_item.get('version') or detail.get('page_version') or file_item.get('description') or '未知'
        file_name = file_item.get('name') or detail.get('name', f'文件 {file_id}')
        fallback_groups.append(
            {
                'file_id': file_id,
                'components': [file_name],
                'versions': [version],
                'entries': [{'name': file_name, 'version': version}],
                'size': file_item.get('size', 0),
                'last_update': file_item.get('created_at', 0),
                'verified': False,
            }
        )
    return fallback_groups


def get_download_urls(file_id: int, include_mirrors: bool = True) -> dict[str, str]:
    urls = {'gamebanana': f'https://gamebanana.com/dl/{file_id}'}
    if include_mirrors:
        urls.update(
            {
                'wegfan': f'https://celeste.weg.fan/api/v2/download/gamebanana-files/{file_id}',
                '0x0ade': f'https://celestemodupdater.0x0a.de/banana-mirror/{file_id}.zip',
            }
        )
    return urls


def strip_html_text(source_text: str) -> str:
    text = re.sub(r'<(?:script|style)[^>]*>.*?</(?:script|style)>', ' ', source_text, flags=re.I | re.S)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'</(?:p|li|div|h\d)>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()


def truncate_text(source_text: str, max_length: int) -> str:
    text = strip_html_text(source_text)
    if len(text) <= max_length:
        return text
    return f'{text[: max(1, max_length - 1)].rstrip()}…'


def format_file_size(byte_size: Any) -> str:
    try:
        size = float(byte_size)
    except Exception:
        return '未知'
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024 or unit == 'GB':
            return f'{size:.1f} {unit}'
        size /= 1024
    return '未知'


def format_credit_text(detail: dict[str, Any]) -> str:
    groups = []
    for group in detail.get('credits', []):
        author_texts = []
        for author in group.get('authors', []):
            name = utils.safe_str(author.get('name', ''))
            role = utils.safe_str(author.get('role', ''))
            if name:
                author_texts.append(f'{name}（{role}）' if role else name)
        if author_texts:
            groups.append(f'{group.get("group", "署名")}：{"、".join(author_texts)}')
    return '；'.join(groups)


def format_component_entry(entry: dict[str, Any]) -> str:
    name = utils.safe_str(entry.get('name', '未知组件'), '未知组件')
    version = utils.safe_str(entry.get('version', '未知'), '未知')
    if version != '未知' and not version.lower().startswith('v'):
        version = f'v{version}'
    return f'{name} {version}'


def format_detail(detail: dict[str, Any], compact: bool = False, heading: str = '') -> str:
    global_config = utils.load_global_config()
    description_limit = int(global_config.get('description_max_length', 320))
    credit_limit = int(global_config.get('credit_max_length', 180))
    component_limit = 1 if compact else int(global_config.get('detail_download_component_limit', 6))
    description_source = detail.get('description') or detail.get('text') or '暂无简介'
    description = truncate_text(description_source, 140 if compact else description_limit) or '暂无简介'
    category_text = ' / '.join(
        value for value in [detail.get('category', ''), detail.get('subcategory', '')] if value
    ) or '未分类'
    tag_text = '、'.join(detail.get('tags', [])) or '无'
    active_credit_limit = min(100, credit_limit) if compact else credit_limit
    credit_text = truncate_text(format_credit_text(detail), active_credit_limit)
    author_text = truncate_text(
        utils.safe_str(detail.get('author', '未知作者'), '未知作者'),
        active_credit_limit,
    ) or '未知作者'

    image_prefix = ''
    cover_url = utils.safe_str(detail.get('cover_url', ''))
    if global_config.get('show_cover_image_switch', True) and cover_url:
        image_prefix = f'[OP:image,file={utils.op_escape(cover_url)}]'
    lines = []
    if heading:
        lines.append(heading)
    lines.extend(
        [
            f'【{detail.get("name", "未知标题")}】',
            f'ID：{detail.get("item_type", "Mod")} {detail.get("id", 0)}',
            f'作者/投稿者：{author_text}',
        ]
    )
    if detail.get('nsfw'):
        lines.append('⚠ 内容警告：GameBanana 将该条目标记为需要内容分级或初始隐藏。')
    if credit_text:
        lines.append(f'完整署名：{credit_text}')
    lines.extend(
        [
            f'分类：{category_text}',
            f'标签：{tag_text}',
            f'数据：下载 {detail.get("downloads", 0):,} / 浏览 {detail.get("views", 0):,} / 喜欢 {detail.get("likes", 0):,}',
            f'简介：{description}',
            f'Mod 页面：{detail.get("page_url", "")}',
        ]
    )

    download_groups = build_download_groups(detail)
    if download_groups:
        lines.append('最新下载：')
        for index, group in enumerate(download_groups[: max(1, component_limit)], start=1):
            entry_texts = [format_component_entry(entry) for entry in group.get('entries', [])]
            component_text = '、'.join(entry_texts) or '、'.join(group.get('components', []))
            component_text = component_text or f'文件 {group.get("file_id", 0)}'
            verified = bool(group.get('verified'))
            marker = 'Everest 已确认' if verified else '非 Everest 确认'
            lines.append(
                f'{index}. {component_text}\n'
                f'   大小：{format_file_size(group.get("size", 0))}｜{marker}'
            )
            urls = get_download_urls(int(group.get('file_id', 0)), include_mirrors=True)
            lines.append(f'   GameBanana：{urls["gamebanana"]}')
            lines.append(f'   WEGFan：{urls["wegfan"]}')
            lines.append(f'   0x0ade：{urls["0x0ade"]}')
            if not verified:
                lines.append('   镜像提示：该文件未进入 Everest 当前更新库，镜像可能不存在。')
        if len(download_groups) > component_limit:
            lines.append(f'另有 {len(download_groups) - component_limit} 个当前组件未展开。')
    else:
        lines.append('最新下载：未找到可用文件。')

    if detail.get('stale_warning'):
        lines.append('提示：部分实时数据获取失败，本次使用了缓存或社区数据库中的旧数据。')
    return image_prefix + '\n'.join(lines)


def format_list_item(item: dict[str, Any], index: int) -> str:
    category = ' / '.join(value for value in [item.get('category'), item.get('subcategory')] if value)
    suffix = f'｜{category}' if category else ''
    return f'{index}. {item.get("name", "未知标题")}｜{item.get("author", "未知作者")}{suffix}'


def random_mods(count: int, excluded_ids: set[int] | None = None) -> dict[str, Any]:
    """直接调用 Maddie random-map；批量随机时避免重复 ID。"""
    target_count = max(1, int(count))
    excluded = set(excluded_ids or set())
    results = []
    last_error = ''
    for _index in range(target_count):
        selected = None
        for _attempt in range(5):
            random_result = get_random_map(include_cover_mirror=target_count == 1)
            if not random_result.get('ok'):
                last_error = random_result.get('error', '随机地图接口不可用')
                continue
            item = random_result.get('data', {})
            item_id = int(item.get('id', 0) or 0)
            if item_id <= 0 or item_id in excluded:
                last_error = '随机地图接口连续返回了重复条目'
                continue
            selected = item
            excluded.add(item_id)
            break
        if selected is None:
            return {'ok': False, 'results': [], 'error': last_error or '无法抽取足够数量的地图'}
        results.append(selected)
    return {'ok': True, 'results': results, 'error': ''}


def get_hong_kong_date() -> str:
    return datetime.datetime.now(ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m-%d')


def get_daily_mod(date_text: str | None = None) -> dict[str, Any]:
    date_value = date_text or get_hong_kong_date()
    random_result = get_random_map(include_cover_mirror=True)
    if not random_result.get('ok'):
        return {'ok': False, 'data': {}, 'date': date_value, 'error': random_result.get('error', '')}
    return {'ok': True, 'data': random_result.get('data', {}), 'date': date_value, 'error': ''}


def get_random_map(include_cover_mirror: bool = True) -> dict[str, Any]:
    """Maddie random-map 只返回地图，直接解析跳转 ID 并获取详情。"""
    response = http_get(config.random_map_url, no_redirect=True)
    if response.get('status') not in [301, 302, 303, 307, 308]:
        return {'ok': False, 'data': {}, 'error': response.get('error', '随机地图接口没有返回跳转')}
    header_dict = {key.lower(): value for key, value in response.get('headers', {}).items()}
    location = utils.safe_str(header_dict.get('location', ''))
    matched = re.search(r'/mods/(\d+)', location)
    if not matched:
        return {'ok': False, 'data': {}, 'error': '无法从随机地图地址解析 Mod ID'}
    return get_item_by_id(
        int(matched.group(1)),
        'Mod',
        include_cover_mirror=include_cover_mirror,
    )


def make_endless_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    snapshot = copy.deepcopy(state)
    snapshot.pop('undo_stack', None)
    return snapshot


def compact_endless_map(raw_map: dict[str, Any]) -> dict[str, Any]:
    item = normalize_item(raw_map)
    return {
        'id': item.get('id', 0),
        'item_type': item.get('item_type', 'Mod'),
        'name': item.get('name', '未知地图'),
        'author': item.get('author', '未知作者'),
        'category': item.get('category', ''),
        'subcategory': item.get('subcategory', ''),
        'cover_url': item.get('cover_url', ''),
        'cover_urls': copy.deepcopy(item.get('cover_urls', [])),
        'page_url': item.get('page_url', ''),
        'credits': copy.deepcopy(item.get('credits', [])),
    }


def new_endless_state(initial_skips: int, current_map: dict[str, Any]) -> dict[str, Any]:
    current_time = int(time.time())
    return {
        'version': 2,
        'run_id': uuid.uuid4().hex,
        'status': 'active',
        'initial_skips': initial_skips,
        'skips': initial_skips,
        'clears': 0,
        'current_map': compact_endless_map(current_map),
        'history': [],
        'undo_stack': [],
        'score_recorded': False,
        'started_at': current_time,
        'updated_at': current_time,
    }


def safe_nonnegative_int(value: Any, default_value: int = 0) -> int:
    """把存档字段安全转换为非负整数。"""
    try:
        return max(0, int(value or 0))
    except Exception:
        return max(0, int(default_value))


def normalize_endless_record(record: dict[str, Any] | None) -> dict[str, Any]:
    """补齐并重新计算个人无尽战绩汇总。"""
    source = copy.deepcopy(record) if isinstance(record, dict) else {}
    raw_history = source.get('history', [])
    history = []
    seen_run_ids = set()
    if isinstance(raw_history, list):
        for raw_entry in raw_history:
            if not isinstance(raw_entry, dict):
                continue
            run_id = utils.safe_str(raw_entry.get('run_id', '')).strip()
            if not run_id or run_id in seen_run_ids:
                continue
            seen_run_ids.add(run_id)
            history.append(
                {
                    'run_id': run_id,
                    'score': safe_nonnegative_int(raw_entry.get('score', 0)),
                    'result': utils.safe_str(raw_entry.get('result', 'ended'), 'ended'),
                    'finished_at': safe_nonnegative_int(raw_entry.get('finished_at', 0)),
                }
            )
    if history:
        last_entry = history[-1]
        last_score = last_entry['score']
        best_score = max(entry['score'] for entry in history)
        last_result = last_entry['result']
        last_finished_at = last_entry['finished_at']
        total_runs = len(history)
    else:
        last_score = safe_nonnegative_int(source.get('last_endless_score', 0))
        best_score = max(last_score, safe_nonnegative_int(source.get('best_endless_score', 0)))
        total_runs = safe_nonnegative_int(source.get('total_runs', 0))
        last_result = utils.safe_str(source.get('last_result', ''))
        last_finished_at = safe_nonnegative_int(source.get('last_finished_at', 0))
    return {
        'last_endless_score': last_score,
        'best_endless_score': best_score,
        'total_runs': total_runs,
        'last_result': last_result,
        'last_finished_at': last_finished_at,
        'history': history,
    }


def add_endless_score_record(
    record: dict[str, Any] | None,
    state: dict[str, Any],
    result: str,
) -> dict[str, Any]:
    """加入一局无尽战绩；相同 run_id 不会重复计数。"""
    normalized = normalize_endless_record(record)
    run_id = utils.safe_str(state.get('run_id', '')).strip()
    if not run_id:
        raise ValueError('无尽挑战缺少 run_id')
    if any(entry.get('run_id') == run_id for entry in normalized['history']):
        return normalized
    normalized['history'].append(
        {
            'run_id': run_id,
            'score': safe_nonnegative_int(state.get('clears', 0)),
            'result': utils.safe_str(result, 'ended'),
            'finished_at': safe_nonnegative_int(state.get('finished_at', 0), int(time.time())),
        }
    )
    return normalize_endless_record(normalized)


def remove_endless_score_record(record: dict[str, Any] | None, run_id: str) -> dict[str, Any]:
    """撤销失败状态时移除对应战绩并重算个人汇总。"""
    normalized = normalize_endless_record(record)
    target_run_id = utils.safe_str(run_id).strip()
    normalized['history'] = [
        entry for entry in normalized['history'] if entry.get('run_id') != target_run_id
    ]
    normalized['last_endless_score'] = 0
    normalized['best_endless_score'] = 0
    normalized['total_runs'] = 0
    normalized['last_result'] = ''
    normalized['last_finished_at'] = 0
    return normalize_endless_record(normalized)


def format_endless_record(record: dict[str, Any] | None) -> str:
    """格式化个人无尽战绩。"""
    normalized = normalize_endless_record(record)
    result_name_dict = {
        'failed': '失败 / Failed',
        'give_up': '放弃 / Gave Up',
        'ended': '结束 / Ended',
        'replaced': '重新开始 / Restarted',
    }
    lines = [
        '【Celeste Endless 记录 / Record】',
        f'上次无尽分数 / Last Score：{normalized["last_endless_score"]}',
        f'最佳无尽分数 / Best Score：{normalized["best_endless_score"]}',
        f'已记录局数 / Runs：{normalized["total_runs"]}',
    ]
    if normalized.get('last_result'):
        result_text = result_name_dict.get(normalized['last_result'], normalized['last_result'])
        lines.append(f'上次结果 / Last Result：{result_text}')
    return '\n'.join(lines)


def transition_endless(
    state: dict[str, Any],
    action: str,
    next_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """复刻 Celeste Endless 的主要状态机。"""
    if not isinstance(state, dict) or state.get('status') not in ['active', 'pending', 'failed']:
        raise ValueError('当前没有可操作的无尽挑战')

    if action == 'undo':
        undo_stack = copy.deepcopy(state.get('undo_stack', []))
        if not undo_stack:
            raise ValueError('没有可以撤销的操作')
        restored = undo_stack.pop()
        restored['undo_stack'] = undo_stack
        restored['updated_at'] = int(time.time())
        return restored

    if state.get('status') == 'failed':
        raise ValueError('本局已经失败，只能撤销、重新开始或结束挑战')
    if state.get('status') == 'pending':
        raise ValueError('上一项成绩已保存，请先继续抽取下一图或撤销')

    result = copy.deepcopy(state)
    undo_stack = copy.deepcopy(result.get('undo_stack', []))
    undo_stack.append(make_endless_snapshot(result))
    result['undo_stack'] = undo_stack[-20:]

    if action == 'reroll' and next_map is None:
        raise ValueError('未能抽取下一张地图')

    current_map = compact_endless_map(result.get('current_map', {}))
    if action == 'clear':
        result['clears'] = int(result.get('clears', 0)) + 1
        result.setdefault('history', []).append({'result': 'clear', 'map': current_map})
        result['current_map'] = compact_endless_map(next_map) if next_map is not None else {}
        result['status'] = 'active' if next_map is not None else 'pending'
    elif action == 'full_clear':
        result['clears'] = int(result.get('clears', 0)) + 1
        result['skips'] = int(result.get('skips', 0)) + 1
        result.setdefault('history', []).append({'result': 'full_clear', 'map': current_map})
        result['current_map'] = compact_endless_map(next_map) if next_map is not None else {}
        result['status'] = 'active' if next_map is not None else 'pending'
    elif action == 'skip':
        if int(result.get('skips', 0)) <= 0:
            result['status'] = 'failed'
        else:
            result['skips'] = int(result.get('skips', 0)) - 1
            result.setdefault('history', []).append({'result': 'skip', 'map': current_map})
            result['current_map'] = compact_endless_map(next_map) if next_map is not None else {}
            result['status'] = 'active' if next_map is not None else 'pending'
    elif action == 'reroll':
        result['current_map'] = compact_endless_map(next_map)
    elif action == 'give_up':
        result['status'] = 'failed'
    else:
        raise ValueError('未知无尽模式操作')

    result['updated_at'] = int(time.time())
    return result


def format_endless_state(state: dict[str, Any], notice: str = '') -> str:
    status_name_dict = {'active': '进行中', 'pending': '等待抽取下一图', 'failed': '已失败'}
    status_text = status_name_dict.get(state.get('status'), '未知')
    current_map = state.get('current_map', {})
    lines = []
    if notice:
        lines.append(notice)
    lines.extend([
        '【Celeste Endless】',
        f'状态：{status_text}',
        f'分数：{int(state.get("clears", 0))}',
        f'剩余跳过：{int(state.get("skips", 0))}',
    ])
    if current_map:
        credited_names = []
        for group in current_map.get('credits', []):
            for author in group.get('authors', []):
                name = utils.safe_str(author.get('name', ''))
                if name and name not in credited_names:
                    credited_names.append(name)
        lines.extend(
            [
                f'当前地图：{current_map.get("name", "未知地图")}',
                f'作者：{current_map.get("author", "未知作者")}',
                f'页面：{current_map.get("page_url", "")}',
            ]
        )
        if credited_names:
            lines.insert(-1, f'完整署名：{"、".join(credited_names)}')
    if state.get('status') == 'active':
        lines.append('操作：通关 / 全收集 / 跳过 / 坏图 / 撤销 / 放弃')
    elif state.get('status') == 'pending':
        lines.append('上一项成绩已保存；请使用“.clst无尽 继续”重试抽取下一图，或使用“撤销”。')
    else:
        lines.append('可使用“.clst无尽 撤销”恢复，或“.clst无尽 开始”重新挑战。')
    image_prefix = ''
    cover_url = utils.safe_str(current_map.get('cover_url', ''))
    if utils.load_global_config().get('show_cover_image_switch', True) and cover_url:
        image_prefix = f'[OP:image,file={utils.op_escape(cover_url)}]'
    return image_prefix + '\n'.join(lines)
