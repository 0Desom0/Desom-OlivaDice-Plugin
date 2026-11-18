# -*- encoding: utf-8 -*-
"""Celeste 社区数据（统一走 WEGFan 镜像）、缓存、格式化与 Endless 业务逻辑。

数据来源全部是 https://celeste.weg.fan 的 /api/v2 接口：
- /submission/search  搜索、分页、按分节/分类过滤、排序
- /submission/detail  按站内 ID 取详情（含文件与 mod 清单）
- /download/files/... 或 /download/gamebanana-files/... 下载镜像

WEGFan 详情只认站内 ID，不认 GameBanana ID，所以插件会先把搜索列表抓成本地索引，
用 GameBanana ID 反查站内 ID；索引同时承担作者/分类检索与随机抽图。
"""

import copy
import datetime
import hashlib
import html
import json
import os
import random
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


cache_lock = threading.RLock()
index_build_lock = threading.Lock()
index_memory_cache: dict[str, Any] = {}
profile_memory_cache: dict[str, dict[str, Any]] = {}
search_memory_cache: dict[str, dict[str, Any]] = {}
detail_memory_cache: dict[str, dict[str, Any]] = {}


GAMEBANANA_SECTION_TYPES = {
    'mods': 'Mod',
    'mod': 'Mod',
    'tools': 'Tool',
    'tool': 'Tool',
    'wips': 'Wip',
    'wip': 'Wip',
    'sounds': 'Sound',
    'sound': 'Sound',
    'sprays': 'Spray',
    'spray': 'Spray',
}


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
        'User-Agent': 'CelestePlugin-OlivOS/1.4',
        'Accept': 'application/json, text/plain, */*',
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


def wegfan_get(
    path: str,
    params: dict[str, Any] | None = None,
    timeout_seconds: int | None = None,
) -> Any:
    """调用 WEGFan /api/v2 接口，校验统一响应包装并返回 data。"""
    url = f'{config.wegfan_api_base}{path}'
    if isinstance(params, dict):
        cleaned_params = {key: value for key, value in params.items() if value not in ['', None]}
        if cleaned_params:
            url = f'{url}?{urllib.parse.urlencode(cleaned_params)}'
    payload = decode_json_response(http_get(url, timeout_seconds=timeout_seconds))
    if not isinstance(payload, dict):
        raise ValueError('WEGFan 接口返回格式异常')
    code = payload.get('code')
    if code not in [200, 0, '200']:
        raise ValueError(utils.safe_str(payload.get('message'), 'WEGFan 接口返回错误') or f'WEGFan 接口返回 {code}')
    data = payload.get('data')
    if data is None:
        raise ValueError('WEGFan 未返回对应数据')
    return data


def safe_int(value: Any, default_value: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default_value


def parse_wegfan_time(value: Any) -> int:
    """把 WEGFan 的 ISO8601 时间转成时间戳（秒），失败返回 0。"""
    text = utils.safe_str(value).strip()
    if not text:
        return 0
    normalized = text.replace('Z', '+00:00')
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except Exception:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return int(parsed.timestamp())


def normalize_wegfan_credits(raw_credits: Any) -> list[dict[str, Any]]:
    groups = []
    for raw_group in raw_credits if isinstance(raw_credits, list) else []:
        if not isinstance(raw_group, dict):
            continue
        authors = []
        for raw_author in raw_group.get('authors') or []:
            if not isinstance(raw_author, dict):
                continue
            name = utils.safe_str(raw_author.get('name'))
            if not name:
                continue
            authors.append(
                {
                    'name': name,
                    'role': utils.safe_str(raw_author.get('role')),
                    'id': raw_author.get('id'),
                    'url': utils.safe_str(raw_author.get('url')),
                }
            )
        if authors:
            groups.append({'group': utils.safe_str(raw_group.get('groupName'), '署名') or '署名', 'authors': authors})
    return groups


def normalize_wegfan_file(raw_file: Any) -> dict[str, Any]:
    """把 WEGFan 的文件对象映射成插件内部结构（id 保留 GameBanana 文件 ID）。"""
    if not isinstance(raw_file, dict):
        return {}
    download_url = utils.safe_str(raw_file.get('url'))
    if download_url.startswith('/'):
        download_url = f'{config.wegfan_origin}{download_url}'
    raw_mods = [mod for mod in raw_file.get('mods') or [] if isinstance(mod, dict)]
    versions = [utils.safe_str(mod.get('version')) for mod in raw_mods if utils.safe_str(mod.get('version'))]
    return {
        'id': safe_int(raw_file.get('gameBananaId')),
        'weg_file_id': utils.safe_str(raw_file.get('id')),
        'name': utils.safe_str(raw_file.get('fileName')),
        'size': safe_int(raw_file.get('size')),
        'created_at': parse_wegfan_time(raw_file.get('createTime') or raw_file.get('updateTime')),
        'downloads': safe_int(raw_file.get('downloads')),
        'url': download_url,
        'version': versions[0] if versions else '',
        'description': utils.safe_str(raw_file.get('description')),
        'archived': bool(raw_file.get('deleteTime')),
        'has_everest_yaml': bool(raw_mods),
        'mods': [
            {'name': utils.safe_str(mod.get('name')), 'version': utils.safe_str(mod.get('version'))}
            for mod in raw_mods
        ],
    }


def build_updater_components(raw_files: Any) -> list[dict[str, Any]]:
    """用 WEGFan 文件里的 mod 清单生成下载分组所需的组件条目。"""
    components = []
    for raw_file in raw_files if isinstance(raw_files, list) else []:
        if not isinstance(raw_file, dict):
            continue
        file_id = safe_int(raw_file.get('gameBananaId'))
        size = safe_int(raw_file.get('size'))
        updated_at = parse_wegfan_time(raw_file.get('updateTime') or raw_file.get('createTime'))
        download_url = utils.safe_str(raw_file.get('url'))
        for raw_mod in raw_file.get('mods') or []:
            if not isinstance(raw_mod, dict):
                continue
            components.append(
                {
                    'InternalName': utils.safe_str(raw_mod.get('name')),
                    'Version': utils.safe_str(raw_mod.get('version')),
                    'GameBananaFileId': file_id,
                    'Size': size,
                    'LastUpdate': updated_at,
                    'URL': download_url,
                }
            )
    return components


def normalize_wegfan_item(raw_item: Any, compact: bool = False) -> dict[str, Any]:
    """把 WEGFan 的 submission 对象映射成插件内部条目。

    compact=True 时只保留列表/索引需要的字段，用于本地索引与搜索结果。
    """
    if not isinstance(raw_item, dict):
        return {}
    item_id = safe_int(raw_item.get('gameBananaId'))
    if item_id <= 0:
        return {}
    item_type = utils.safe_str(raw_item.get('gameBananaSection')).strip()
    if not item_type:
        matched = re.search(r'gamebanana\.com/([A-Za-z]+)/', utils.safe_str(raw_item.get('pageUrl')))
        item_type = GAMEBANANA_SECTION_TYPES.get(matched.group(1).casefold(), '') if matched else ''
    screenshots = []
    for raw_shot in raw_item.get('screenshots') or []:
        image_url = utils.safe_str(raw_shot.get('url')) if isinstance(raw_shot, dict) else utils.safe_str(raw_shot)
        if image_url and image_url not in screenshots:
            screenshots.append(image_url)
    description = utils.safe_str(raw_item.get('description'))
    item = {
        'id': item_id,
        'weg_id': utils.safe_str(raw_item.get('id')),
        'item_type': item_type or 'Mod',
        'name': utils.safe_str(raw_item.get('name'), '未知标题') or '未知标题',
        'author': utils.safe_str(raw_item.get('submitter'), '未知作者') or '未知作者',
        'subtitle': utils.safe_str(raw_item.get('subtitle')),
        'description': description if not compact else description[:600],
        'text': '',
        'page_url': utils.safe_str(raw_item.get('pageUrl')) or f'https://gamebanana.com/mods/{item_id}',
        'category': utils.safe_str(raw_item.get('categoryName')),
        'subcategory': utils.safe_str(raw_item.get('subCategoryName')),
        'views': safe_int(raw_item.get('views')),
        'likes': safe_int(raw_item.get('likes')),
        'downloads': safe_int(raw_item.get('downloads')),
        'created_at': parse_wegfan_time(raw_item.get('createTime')),
        'updated_at': parse_wegfan_time(
            raw_item.get('latestUpdateAddedTime') or raw_item.get('updateTime') or raw_item.get('createTime')
        ),
        'screenshots': screenshots[:3] if compact else screenshots,
        'mirrored_screenshots': [],
        'cover_urls': screenshots[:3],
        'cover_url': screenshots[0] if screenshots else '',
        'credits': [],
        'tags': [],
        'nsfw': False,
        'files': [],
        'updater_components': [],
        'weg_synced_at': int(time.time()),
    }
    if compact:
        return item
    raw_files = raw_item.get('files')
    if not isinstance(raw_files, list):
        raw_files = []
    item['files'] = [normalize_wegfan_file(raw_file) for raw_file in raw_files if isinstance(raw_file, dict)]
    item['updater_components'] = build_updater_components(raw_files)
    item['credits'] = normalize_wegfan_credits(raw_item.get('credits'))
    return item


# ---------------------------------------------------------------------------
# 本地索引：WEGFan 搜索列表 → GameBanana ID ↔ 站内 ID
# ---------------------------------------------------------------------------


def get_index_cache_path() -> str:
    return os.path.join(utils.get_shared_cache_dir(), f'{config.wegfan_index_cache_name}.json')


def prepare_index(payload: Any) -> dict[str, Any]:
    raw_items = payload.get('items') if isinstance(payload, dict) else []
    items = []
    for raw_item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw_item, dict):
            continue
        if safe_int(raw_item.get('id')) <= 0:
            continue
        items.append(raw_item)
    by_gamebanana_id = {}
    for item in items:
        item_type = utils.safe_str(item.get('item_type'), 'Mod').casefold() or 'mod'
        by_gamebanana_id[f'{item_type}:{safe_int(item.get("id"))}'] = item
    return {
        'items': items,
        'by_gamebanana_id': by_gamebanana_id,
        'fetched_at': safe_int(payload.get('fetched_at')) if isinstance(payload, dict) else 0,
        'complete': bool(payload.get('complete', True)) if isinstance(payload, dict) else True,
    }


def fetch_full_index() -> dict[str, Any]:
    """逐分节抓取 WEGFan 搜索列表，构建完整索引。"""
    items: dict[str, dict[str, Any]] = {}
    error_parts = []
    page_size = max(1, int(config.wegfan_index_page_size))
    max_pages = max(1, int(config.wegfan_index_max_pages))
    index_timeout = max(30, get_timeout_seconds() * 3)
    for section in config.wegfan_index_sections:
        page = 1
        consecutive_failures = 0
        while page <= max_pages:
            page_data = None
            last_error = ''
            for _attempt in range(3):
                try:
                    page_data = wegfan_get(
                        config.wegfan_search_path,
                        {
                            'page': page,
                            'size': page_size,
                            'section': section,
                            'sort': config.wegfan_sort_default,
                        },
                        timeout_seconds=index_timeout,
                    )
                    break
                except Exception as exception_object:
                    last_error = utils.safe_str(exception_object)
                    page_data = None
                    time.sleep(1.5)
            if page_data is None:
                error_parts.append(f'{section} 第 {page} 页：{last_error}')
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    break
                page += 1
                continue
            consecutive_failures = 0
            content = page_data.get('content') if isinstance(page_data, dict) else None
            if not isinstance(content, list) or not content:
                break
            for raw_item in content:
                record = normalize_wegfan_item(raw_item, compact=True)
                if not record.get('id'):
                    continue
                items[f"{record['item_type'].casefold()}:{record['id']}"] = record
            if not page_data.get('hasNextPage'):
                break
            page += 1
    if not items:
        return {
            'ok': False,
            'items': [],
            'fetched_at': 0,
            'complete': False,
            'error': '；'.join(error_parts) or 'WEGFan 索引为空',
        }
    return {
        'ok': True,
        'items': list(items.values()),
        'fetched_at': int(time.time()),
        'complete': not error_parts,
        'error': '；'.join(error_parts),
    }


def load_index(force_refresh: bool = False) -> dict[str, Any]:
    """读取 WEGFan 本地索引；过期时重建，重建失败则沿用旧索引。"""
    ttl = max(600, int(utils.load_global_config().get('database_cache_seconds', 21600)))
    current_time = time.time()
    with cache_lock:
        memory_index = index_memory_cache.get('data')
        if (
            memory_index
            and not force_refresh
            and current_time - float(index_memory_cache.get('loaded_at', 0) or 0) < ttl
        ):
            return {'ok': True, 'data': memory_index, 'error': '', 'from_cache': True}

    cache_path = get_index_cache_path()
    disk_payload = utils.read_json_file(cache_path, {})
    if not isinstance(disk_payload, dict):
        disk_payload = {}
    disk_has_items = bool(disk_payload.get('items'))
    disk_complete = bool(disk_payload.get('complete', True))
    effective_ttl = ttl if disk_complete else min(ttl, 1800)
    disk_fresh = (
        disk_has_items
        and not force_refresh
        and current_time - float(disk_payload.get('fetched_at', 0) or 0) < effective_ttl
    )
    if disk_fresh:
        prepared = prepare_index(disk_payload)
        with cache_lock:
            index_memory_cache.update({'data': prepared, 'loaded_at': current_time})
        return {
            'ok': True,
            'data': prepared,
            'error': utils.safe_str(disk_payload.get('error')),
            'from_cache': True,
        }

    if not index_build_lock.acquire(blocking=False):
        if disk_has_items:
            prepared = prepare_index(disk_payload)
            with cache_lock:
                index_memory_cache.update({'data': prepared, 'loaded_at': current_time})
            return {'ok': True, 'data': prepared, 'error': 'WEGFan 索引正在重建，本次使用旧索引', 'from_cache': True}
        return {'ok': False, 'data': None, 'error': 'WEGFan 本地索引正在建立，请稍后再试', 'from_cache': False}

    try:
        fetched = fetch_full_index()
    finally:
        index_build_lock.release()

    if fetched.get('ok'):
        utils.save_json_file(cache_path, fetched)
        prepared = prepare_index(fetched)
        with cache_lock:
            index_memory_cache.update({'data': prepared, 'loaded_at': current_time})
        return {'ok': True, 'data': prepared, 'error': fetched.get('error', ''), 'from_cache': False}

    if disk_has_items:
        prepared = prepare_index(disk_payload)
        with cache_lock:
            index_memory_cache.update({'data': prepared, 'loaded_at': current_time})
        return {
            'ok': True,
            'data': prepared,
            'error': fetched.get('error', '') or 'WEGFan 索引重建失败，已沿用旧索引',
            'from_cache': True,
        }
    return {'ok': False, 'data': None, 'error': fetched.get('error', 'WEGFan 索引构建失败'), 'from_cache': False}


def refresh_community_data() -> dict[str, Any]:
    """骰主手动更新：忽略 TTL，强制重建 WEGFan 本地索引。"""
    result = load_index(force_refresh=True)
    prepared = result.get('data') if isinstance(result.get('data'), dict) else {}
    return {
        'ok': bool(result.get('ok')),
        'database_count': len(prepared.get('items', [])) if prepared else 0,
        'database_from_cache': bool(result.get('from_cache', False)),
        'error': result.get('error', ''),
    }


def resolve_weg_id(item_type: str, item_id: int) -> str:
    """GameBanana ID → WEGFan 站内 ID。"""
    index_result = load_index()
    if not index_result.get('ok'):
        return ''
    prepared = index_result.get('data') or {}
    record = (prepared.get('by_gamebanana_id') or {}).get(
        f'{utils.safe_str(item_type, "Mod").casefold()}:{safe_int(item_id)}'
    )
    return utils.safe_str(record.get('weg_id')) if isinstance(record, dict) else ''


index_refresh_state = {'last_incremental_at': 0.0}
index_rebuild_lock = threading.Lock()


def merge_index_items(records: list[dict[str, Any]]) -> int:
    """把新抓到的条目合并进内存与磁盘索引，返回新增条数。"""
    if not records:
        return 0
    cache_path = get_index_cache_path()
    payload = utils.read_json_file(cache_path, {})
    if not isinstance(payload, dict):
        payload = {}
    existing = {}
    for item in payload.get('items') or []:
        if not isinstance(item, dict) or safe_int(item.get('id')) <= 0:
            continue
        existing[f'{utils.safe_str(item.get("item_type"), "Mod").casefold()}:{safe_int(item.get("id"))}'] = item
    added = 0
    for record in records:
        if safe_int(record.get('id')) <= 0:
            continue
        key = f'{utils.safe_str(record.get("item_type"), "Mod").casefold()}:{safe_int(record.get("id"))}'
        if key not in existing:
            added += 1
        existing[key] = record
    payload['items'] = list(existing.values())
    payload.setdefault('fetched_at', int(time.time()))
    payload.setdefault('complete', False)
    utils.save_json_file(cache_path, payload)
    with cache_lock:
        index_memory_cache.update({'data': prepare_index(payload), 'loaded_at': time.time()})
    return added


def refresh_index_incremental(section: str = '', min_interval_seconds: int = 60) -> dict[str, Any]:
    """索引未命中时补抓最新一页（默认 500 条），覆盖刚发布/刚更新的条目。

    section 为空时补抓全部分节；传入具体分节只补该节，避免一次拖太久。
    """
    current_time = time.time()
    if current_time - float(index_refresh_state.get('last_incremental_at', 0) or 0) < min_interval_seconds:
        return {'ok': False, 'added': 0, 'error': '刚刚补抓过，仍在冷却期'}
    index_refresh_state['last_incremental_at'] = current_time
    section_list = [section] if section else list(config.wegfan_index_sections)
    records: list[dict[str, Any]] = []
    error_parts = []
    for section_name in section_list:
        try:
            data = wegfan_get(
                config.wegfan_search_path,
                {
                    'page': 1,
                    'size': config.wegfan_index_page_size,
                    'section': section_name,
                    'sort': config.wegfan_sort_default,
                },
                timeout_seconds=max(20, get_timeout_seconds()),
            )
        except Exception as exception_object:
            error_parts.append(f'{section_name}：{utils.safe_str(exception_object)}')
            continue
        for raw_item in data.get('content') or []:
            record = normalize_wegfan_item(raw_item, compact=True)
            if record.get('id'):
                records.append(record)
    added = merge_index_items(records)
    return {'ok': bool(records), 'added': added, 'error': '；'.join(error_parts)}


def start_background_index_rebuild() -> None:
    """索引未命中且补抓也没找到时，后台整份重建一次，避免阻塞当前回复。"""
    if not index_rebuild_lock.acquire(blocking=False):
        return

    def worker():
        try:
            load_index(force_refresh=True)
        except Exception:
            pass
        finally:
            index_rebuild_lock.release()

    threading.Thread(target=worker, name='CelestePluginIndexRebuild', daemon=True).start()


# ---------------------------------------------------------------------------
# 短期缓存
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------


def search_title(query: str) -> dict[str, Any]:
    query_text = utils.safe_str(query).strip()
    if not query_text:
        return {'ok': False, 'results': [], 'count': 0, 'error': '请输入搜索关键词'}
    cache_key = f'title|{query_text.casefold()}'
    cache_ttl = max(0, int(utils.load_global_config().get('search_cache_seconds', 300)))
    cached_result = load_short_cache(search_memory_cache, 'searches', cache_key, cache_ttl)
    if isinstance(cached_result, dict):
        return cached_result

    result_limit = max(1, int(utils.load_global_config().get('search_result_limit', 100)))
    try:
        data = wegfan_get(
            config.wegfan_search_path,
            {
                'search': query_text,
                'page': 1,
                'size': result_limit,
                'sort': config.wegfan_sort_default,
            },
            timeout_seconds=max(8, get_timeout_seconds()),
        )
    except Exception as exception_object:
        fallback = search_local(['name'], query_text)
        if fallback.get('ok') and fallback.get('results'):
            fallback['notice'] = 'WEGFan 搜索接口暂时不可用，本次使用本地索引做关键词匹配。'
            save_short_cache(search_memory_cache, 'searches', cache_key, fallback)
            return fallback
        return {'ok': False, 'results': [], 'count': 0, 'error': utils.safe_str(exception_object)}

    content = data.get('content') if isinstance(data, dict) else []
    results = [normalize_wegfan_item(raw_item, compact=True) for raw_item in content or []]
    results = [item for item in results if item.get('id')]
    total_count = safe_int(data.get('totalElements')) if isinstance(data, dict) else len(results)
    total_count = max(total_count, len(results))
    result = {'ok': True, 'results': results, 'count': total_count, 'error': ''}
    if total_count > len(results):
        result['notice'] = f'共匹配 {total_count} 项，列表展示前 {len(results)} 项；加关键词可以缩窄范围。'
    save_short_cache(search_memory_cache, 'searches', cache_key, result)
    return result


def search_local(field_names: list[str], query: str, limit: int = 10000) -> dict[str, Any]:
    query_text = utils.safe_str(query).strip().casefold()
    if not query_text:
        return {'ok': False, 'results': [], 'count': 0, 'error': '请输入筛选内容'}
    index_result = load_index()
    if not index_result.get('ok'):
        return {'ok': False, 'results': [], 'count': 0, 'error': index_result.get('error', 'WEGFan 索引不可用')}

    exact_matches = []
    contains_matches = []
    for item in index_result['data'].get('items', []):
        values = [utils.safe_str(item.get(field_name, '')).casefold() for field_name in field_names]
        if query_text in values:
            exact_matches.append(dict(item))
        elif any(query_text in value for value in values):
            contains_matches.append(dict(item))
    results = exact_matches + contains_matches
    results.sort(key=lambda item: (item.get('downloads', 0), item.get('likes', 0)), reverse=True)
    return {
        'ok': True,
        'results': results[:limit],
        'count': len(results),
        'error': '',
        'notice': utils.safe_str(index_result.get('error')),
    }


def search_author(query: str) -> dict[str, Any]:
    result = search_local(['author'], query)
    if not result.get('ok'):
        return result
    notices = [notice for notice in [result.get('notice', ''), '作者检索基于 WEGFan 本地索引的投稿者字段。'] if notice]
    result['notice'] = '；'.join(notices)
    return result


def search_category(query: str) -> dict[str, Any]:
    return search_local(['category', 'subcategory'], query)


def search_tag(query: str) -> dict[str, Any]:
    """WEGFan 没有自由标签字段，按子分类、标题与简介关键词匹配。"""
    result = search_local(['subcategory', 'name', 'description'], query)
    if not result.get('ok'):
        return result
    notices = [notice for notice in [result.get('notice', ''), 'WEGFan 不提供自由标签，本次按子分类、标题与简介关键词匹配。'] if notice]
    result['notice'] = '；'.join(notices)
    result['partial'] = True
    return result


# ---------------------------------------------------------------------------
# 详情
# ---------------------------------------------------------------------------


def get_item_by_id(
    item_id: int,
    item_type: str = 'Mod',
    include_cover_mirror: bool = True,
    weg_id: str = '',
) -> dict[str, Any]:
    """按 GameBanana ID 取详情；weg_id 存在时直接用它请求 WEGFan 详情。"""
    try:
        item_id = int(item_id)
    except Exception:
        item_id = 0
    item_type = utils.safe_str(item_type, 'Mod') or 'Mod'
    detail_cache_key = f'{item_type.casefold()}:{item_id}'
    detail_cache_ttl = max(0, int(utils.load_global_config().get('detail_cache_seconds', 600)))
    cached_detail = load_short_cache(
        detail_memory_cache,
        'details',
        detail_cache_key,
        detail_cache_ttl,
    )
    if isinstance(cached_detail, dict) and cached_detail.get('id') and cached_detail.get('name'):
        return {'ok': True, 'data': cached_detail, 'error': '', 'from_cache': True}
    if item_id <= 0:
        return {'ok': False, 'data': {}, 'error': '无法解析该条目的 GameBanana ID'}

    resolved_weg_id = utils.safe_str(weg_id).strip() or resolve_weg_id(item_type, item_id)
    if not resolved_weg_id:
        # 索引里没有：先补抓该分节最新一页（刚发布/刚更新），仍没有就后台整份重建。
        refresh_index_incremental(item_type)
        resolved_weg_id = resolve_weg_id(item_type, item_id)
    if not resolved_weg_id:
        start_background_index_rebuild()
        return {
            'ok': False,
            'data': {},
            'error': (
                f'WEGFan 索引和最新更新页里都还没有 {item_type} {item_id}；'
                '如果它刚发布，等 WEGFan 收录后再试，或直接用标题搜索定位'
                '（索引正在后台补全）。'
            ),
        }

    try:
        raw_item = wegfan_get(
            config.wegfan_detail_path,
            {'id': resolved_weg_id},
            timeout_seconds=max(8, get_timeout_seconds()),
        )
        detail = normalize_wegfan_item(raw_item)
        if not detail:
            raise ValueError('WEGFan 详情为空')
        if safe_int(detail.get('id')) != item_id:
            raise ValueError('WEGFan 返回的条目与请求的 GameBanana ID 不一致')
    except Exception as exception_object:
        if isinstance(cached_detail, dict) and cached_detail.get('id'):
            return {
                'ok': True,
                'data': cached_detail,
                'error': utils.safe_str(exception_object),
                'from_cache': True,
            }
        return {'ok': False, 'data': {}, 'error': utils.safe_str(exception_object), 'from_cache': False}

    detail['stale_warning'] = ''
    save_short_cache(detail_memory_cache, 'details', detail_cache_key, detail)
    return {'ok': True, 'data': detail, 'error': '', 'from_cache': False}


def hydrate_item(item: dict[str, Any]) -> dict[str, Any]:
    return get_item_by_id(
        safe_int(item.get('id', 0)),
        utils.safe_str(item.get('item_type', 'Mod'), 'Mod'),
        weg_id=utils.safe_str(item.get('weg_id', '')),
    )


# ---------------------------------------------------------------------------
# 随机与每日
# ---------------------------------------------------------------------------


def pick_random_index_item() -> dict[str, Any]:
    index_result = load_index()
    if not index_result.get('ok'):
        return {}
    items = index_result['data'].get('items', [])
    map_items = [
        item
        for item in items
        if utils.safe_str(item.get('item_type'), '').casefold() == 'mod'
        and utils.safe_str(item.get('category'), '').casefold() == 'maps'
    ]
    pool = map_items or [item for item in items if utils.safe_str(item.get('item_type'), '').casefold() == 'mod']
    return random.choice(pool) if pool else {}


def pick_random_via_api() -> dict[str, Any]:
    """索引不可用时的兜底：随机翻一页 WEGFan 的 Maps 搜索结果。"""
    base_params = {
        'section': 'Mod',
        'categoryId': config.wegfan_categories['maps'],
        'sort': config.wegfan_sort_default,
    }
    try:
        first_page = wegfan_get(
            config.wegfan_search_path,
            dict(base_params, page=1, size=1),
            timeout_seconds=max(8, get_timeout_seconds()),
        )
        total_count = safe_int(first_page.get('totalElements')) if isinstance(first_page, dict) else 0
        page_size = 50
        page_count = max(1, (total_count + page_size - 1) // page_size)
        page = random.randint(1, page_count)
        page_data = wegfan_get(
            config.wegfan_search_path,
            dict(base_params, page=page, size=page_size),
            timeout_seconds=max(8, get_timeout_seconds()),
        )
        content = page_data.get('content') if isinstance(page_data, dict) else []
        candidates = [normalize_wegfan_item(raw_item, compact=True) for raw_item in content or []]
        candidates = [item for item in candidates if item.get('id')]
        if not candidates:
            return {'error': 'WEGFan 搜索结果为空'}
        return random.choice(candidates)
    except Exception as exception_object:
        return {'error': utils.safe_str(exception_object)}


def get_random_map(include_cover_mirror: bool = True) -> dict[str, Any]:
    """随机地图：优先本地索引，索引不可用时随机翻页 WEGFan 搜索。"""
    picked = pick_random_index_item()
    if picked:
        detail_result = get_item_by_id(
            safe_int(picked.get('id')),
            'Mod',
            include_cover_mirror,
            weg_id=utils.safe_str(picked.get('weg_id')),
        )
        if detail_result.get('ok'):
            return detail_result
    fallback_picked = pick_random_via_api()
    if fallback_picked.get('id'):
        return get_item_by_id(
            safe_int(fallback_picked.get('id')),
            'Mod',
            include_cover_mirror,
            weg_id=utils.safe_str(fallback_picked.get('weg_id')),
        )
    return {'ok': False, 'data': {}, 'error': fallback_picked.get('error') or '无法抽取随机地图'}


def random_mods(count: int, excluded_ids: set[int] | None = None) -> dict[str, Any]:
    """批量随机，避免重复 ID。"""
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
            item_id = safe_int(item.get('id'))
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


# ---------------------------------------------------------------------------
# 下载分组与文本格式化
# ---------------------------------------------------------------------------


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


def get_download_urls(file_id: int) -> dict[str, str]:
    """下载地址统一走 WEGFan 镜像。"""
    return {'wegfan': config.wegfan_gamebanana_file_url.format(file_id=int(file_id))}


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
    description = truncate_text(description_source, description_limit) or '暂无简介'
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
    if credit_text:
        lines.append(f'完整署名：{credit_text}')
    detail_lines = [
        f'分类：{category_text}',
        f'标签：{tag_text}',
        f'数据：下载 {detail.get("downloads", 0):,} / 浏览 {detail.get("views", 0):,} / 喜欢 {detail.get("likes", 0):,}',
    ]
    if not compact:
        detail_lines.append(f'简介：{description}')
    detail_lines.append(f'Mod 页面：{detail.get("page_url", "")}')
    lines.extend(detail_lines)

    download_groups = build_download_groups(detail)
    file_url_map = {}
    for file_item in detail.get('files', []):
        file_id = int(file_item.get('id', 0) or 0)
        if file_id > 0 and file_item.get('url'):
            file_url_map[file_id] = utils.safe_str(file_item['url'])
    if download_groups:
        lines.append('最新下载：')
        for index, group in enumerate(download_groups[: max(1, component_limit)], start=1):
            entry_texts = [format_component_entry(entry) for entry in group.get('entries', [])]
            component_text = '、'.join(entry_texts) or '、'.join(group.get('components', []))
            component_text = component_text or f'文件 {group.get("file_id", 0)}'
            verified = bool(group.get('verified'))
            marker = '含 Everest mod 清单' if verified else '无 mod 清单'
            lines.append(
                f'{index}. {component_text}\n'
                f'   大小：{format_file_size(group.get("size", 0))}｜{marker}'
            )
            file_id = int(group.get('file_id', 0) or 0)
            download_url = file_url_map.get(file_id) or get_download_urls(file_id)['wegfan']
            lines.append(f'   WEGFan 镜像：{download_url}')
            if not verified:
                lines.append('   提示：该文件没有 mod 清单信息，可能不是可直接加载的 Mod。')
        if len(download_groups) > component_limit:
            lines.append(f'另有 {len(download_groups) - component_limit} 个当前组件未展开。')
    else:
        lines.append('最新下载：未找到可用文件。')

    if detail.get('stale_warning'):
        lines.append('提示：部分实时数据获取失败，本次使用了缓存中的旧数据。')
    return image_prefix + '\n'.join(lines)


def format_list_item(item: dict[str, Any], index: int) -> str:
    category = ' / '.join(value for value in [item.get('category'), item.get('subcategory')] if value)
    suffix = f'｜{category}' if category else ''
    return f'{index}. {item.get("name", "未知标题")}｜{item.get("author", "未知作者")}{suffix}'


# ---------------------------------------------------------------------------
# Celeste Endless
# ---------------------------------------------------------------------------


def make_endless_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    snapshot = copy.deepcopy(state)
    snapshot.pop('undo_stack', None)
    return snapshot


def compact_endless_map(raw_map: dict[str, Any]) -> dict[str, Any]:
    item = raw_map if isinstance(raw_map, dict) else {}
    return {
        'id': safe_int(item.get('id', 0)),
        'weg_id': utils.safe_str(item.get('weg_id', '')),
        'item_type': utils.safe_str(item.get('item_type', 'Mod'), 'Mod'),
        'name': utils.safe_str(item.get('name', '未知地图'), '未知地图'),
        'author': utils.safe_str(item.get('author', '未知作者'), '未知作者'),
        'category': utils.safe_str(item.get('category', '')),
        'subcategory': utils.safe_str(item.get('subcategory', '')),
        'cover_url': utils.safe_str(item.get('cover_url', '')),
        'cover_urls': copy.deepcopy(item.get('cover_urls', [])),
        'page_url': utils.safe_str(item.get('page_url', '')),
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
