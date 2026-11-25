# -*- encoding: utf-8 -*-
"""I Wanna Archive API 访问与结果整理。"""

import json
import math
import os
import random
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from . import config
from . import utils


function_module_note = 'I Wanna Archive API 查询模块。'
# 三个高亮色：序号橙红、评分天蓝、难度浅紫，深色卡片上都清楚且互不混淆
BSLASH = chr(92)  # 反斜杠；别写字面量，源码里的 	 会被当成制表符
MARK_COLOR_INDEX = "#FF6B35"
MARK_COLOR_RATING = "#4FC3F7"
MARK_COLOR_DIFFICULTY = "#C792EA"


def mark_text(text: str, color: str = MARK_COLOR_INDEX) -> str:
    r"""需要醒目标注的片段：语法统一收在这里，改一处就够。

    QQ 只认单层 \textcolor{...}{...}，再嵌 \text{} 会整段渲染失败；
    数学模式会吞空格，所以正文里的空格写成反斜杠加空格。
    """
    if not text:
        return ''
    escaped = str(text).replace('\\', '\\\\')
    for char in ('$', '{', '}', '_', '^', '&', '%', '#'):
        escaped = escaped.replace(char, '\\' + char)
    escaped = escaped.replace(' ', '\\' + ' ')
    return f'$' + BSLASH + f'textcolor{{{color}}}{{{escaped}}}$'


default_empty_text = '暂无'


class DownloadError(Exception):
    """下载阶段可安全展示给用户的错误。"""


def normalize_download_concurrency(value: Any) -> int:
    """把并发配置限制在允许范围内。"""
    try:
        normalized_value = int(value)
    except Exception:
        normalized_value = config.download_concurrency_default
    return max(
        config.download_concurrency_min,
        min(config.download_concurrency_max, normalized_value),
    )


class DownloadTaskManager(object):
    """只启动当前并发上限数量的后台任务，并支持运行期调整上限。"""

    def __init__(self, max_concurrency: int):
        self._lock = threading.RLock()
        self._pending_task_list: Deque[Callable[[], None]] = deque()
        self._active_count = 0
        self._max_concurrency = normalize_download_concurrency(max_concurrency)
        self._stopping = False

    def set_max_concurrency(self, max_concurrency: Any) -> int:
        """设置新的并发上限；已在执行的任务不会被强行中断。"""
        normalized_value = normalize_download_concurrency(max_concurrency)
        with self._lock:
            self._max_concurrency = normalized_value
            self._start_pending_tasks_locked()
        return normalized_value

    def get_status(self) -> Dict[str, int]:
        """返回当前活动数、排队数和并发上限。"""
        with self._lock:
            return {
                'active': self._active_count,
                'pending': len(self._pending_task_list),
                'max_concurrency': self._max_concurrency,
            }

    def submit(self, task: Callable[[], None]) -> Dict[str, Any]:
        """提交一个任务，并返回是否立即开始及排队位置。"""
        if not callable(task):
            raise TypeError('下载任务必须是可调用对象')

        with self._lock:
            if self._stopping:
                raise RuntimeError('下载任务管理器已停止')

            starts_immediately = self._active_count < self._max_concurrency and not self._pending_task_list
            self._pending_task_list.append(task)
            queue_position = 0 if starts_immediately else len(self._pending_task_list)
            self._start_pending_tasks_locked()
            return {
                'started': starts_immediately,
                'queue_position': queue_position,
            }

    def _start_pending_tasks_locked(self) -> None:
        while self._pending_task_list and self._active_count < self._max_concurrency:
            task = self._pending_task_list.popleft()
            self._active_count += 1
            try:
                worker_thread = threading.Thread(
                    target=self._run_task,
                    args=(task,),
                    name='IWannaDownload',
                    daemon=True,
                )
                worker_thread.start()
            except Exception:
                self._active_count -= 1
                self._pending_task_list.appendleft(task)
                break

    def _run_task(self, task: Callable[[], None]) -> None:
        try:
            task()
        except Exception:
            # 具体任务负责把异常写入插件日志，管理器只保证释放并发名额。
            pass
        finally:
            with self._lock:
                self._active_count = max(0, self._active_count - 1)
                self._start_pending_tasks_locked()

    def stop(self) -> None:
        """停止接受新任务并清空尚未开始的任务。"""
        with self._lock:
            self._stopping = True
            self._pending_task_list.clear()


download_task_manager = DownloadTaskManager(config.download_concurrency_default)


def set_download_concurrency(value: Any) -> int:
    """更新全局下载队列的并发上限。"""
    return download_task_manager.set_max_concurrency(value)


def safe_text(value: Any, default_value: str = '') -> str:
    try:
        text = str(value)
    except Exception:
        return default_value
    return text if text else default_value


def value_is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == '':
        return True
    return False


def normalize_base_url(base_url: str) -> str:
    source_url = safe_text(base_url, 'https://fangame-archive.com').strip()
    if not source_url:
        source_url = 'https://fangame-archive.com'
    return source_url.rstrip('/')


def _append_multi_param(
    result: List[tuple],
    api_key: str,
    value: Any,
    split_comma: bool = False,
    lowercase: bool = False,
) -> None:
    """把单个值或集合值展开追加为 URL 查询参数，跳过空字符串与 None。"""
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    elif split_comma:
        items = safe_text(value).split(',')
    else:
        items = [value]

    for item in items:
        if item is None:
            continue
        item_str = safe_text(item).strip()
        if not item_str:
            continue
        if lowercase:
            item_str = item_str.lower()
        result.append((api_key, item_str))


def _append_scalar_param(result: List[tuple], api_key: str, value: Any) -> None:
    """透传标量参数；若传入集合则展开为多个同名参数，跳过空字符串与 None。"""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _append_scalar_param(result, api_key, item)
        return
    if value is None:
        return
    if isinstance(value, bool):
        result.append((api_key, 'true' if value else 'false'))
        return
    val = safe_text(value).strip()
    if val:
        result.append((api_key, val))


def _has_nonempty_param(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(item is not None and safe_text(item).strip() != '' for item in value)
    return safe_text(value).strip() != ''


def normalize_filter_params(params: Optional[Dict[str, Any]]) -> List[tuple]:
    """把各种灵活的过滤参数转换成 API 规范的 URL 参数元组列表。"""
    if not params:
        return []
    result: List[tuple] = []

    year_val = params.get('year')
    has_explicit_date = any(
        _has_nonempty_param(params.get(k))
        for k in ('date_from', 'from_date', 'start_date', 'date_to', 'to_date', 'end_date', 'date_in')
    )
    auto_date_from = ''
    auto_date_to = ''
    if year_val and not has_explicit_date:
        year_str = safe_text(year_val).strip()
        if re.fullmatch(r'\d{4}', year_str):
            auto_date_from = f'{year_str}-01-01'
            auto_date_to = f'{year_str}-12-31'

    multi_key_map = {
        'tag': ('tag', True, False),
        'tags': ('tag', True, False),
        'tag_not': ('tag_not', True, False),
        'tags_not': ('tag_not', True, False),
        'not_tag': ('tag_not', True, False),
        'not_tags': ('tag_not', True, False),
        'tag_all': ('tag_all', True, False),
        'tags_all': ('tag_all', True, False),
        'all_tag': ('tag_all', True, False),
        'all_tags': ('tag_all', True, False),
        'date_in': ('date_in', False, False),
        'date_not': ('date_not', False, False),
        'engine': ('engine', False, False),
        'engines': ('engine', False, False),
        'engine_not': ('engine_not', False, False),
        'engines_not': ('engine_not', False, False),
        'not_engine': ('engine_not', False, False),
        'not_engines': ('engine_not', False, False),
        'source': ('source', False, True),
        'sources': ('source', False, True),
        'source_not': ('source_not', False, True),
        'sources_not': ('source_not', False, True),
        'not_source': ('source_not', False, True),
        'not_sources': ('source_not', False, True),
    }

    scalar_key_map = {
        'q': 'q',
        'query': 'q',
        'name': 'q',
        'keyword': 'q',
        'title': 'title',
        'creator': 'creator',
        'id': 'id',
        'game_id': 'id',
        'date_from': 'date_from',
        'from_date': 'date_from',
        'start_date': 'date_from',
        'date_to': 'date_to',
        'to_date': 'date_to',
        'end_date': 'date_to',
        'rating_min': 'rating_min',
        'min_rating': 'rating_min',
        'rating_max': 'rating_max',
        'max_rating': 'rating_max',
        'difficulty_min': 'difficulty_min',
        'min_difficulty': 'difficulty_min',
        'difficulty_max': 'difficulty_max',
        'max_difficulty': 'difficulty_max',
        'reviews_min': 'reviews_min',
        'min_reviews': 'reviews_min',
        'reviews_max': 'reviews_max',
        'max_reviews': 'reviews_max',
        'size_min_mb': 'size_min_mb',
        'size_max_mb': 'size_max_mb',
        'local': 'local',
        'has_download': 'has_download',
        'has_engine': 'has_engine',
        'has_date': 'has_date',
        'source_id': 'source_id',
        'sort': 'sort',
        'order': 'order',
        'fields': 'fields',
    }

    for key, value in params.items():
        if value is None or key == 'year':
            continue
        key_lower = safe_text(key).strip().lower()
        if key_lower in multi_key_map:
            api_key, split_comma, lowercase = multi_key_map[key_lower]
            _append_multi_param(result, api_key, value, split_comma=split_comma, lowercase=lowercase)
        elif key_lower in scalar_key_map:
            _append_scalar_param(result, scalar_key_map[key_lower], value)
        elif key_lower in {'count', 'offset', 'limit'}:
            try:
                result.append((key_lower, int(value)))
            except Exception as exc:
                utils.info_log(utils.get_runtime_proc(), f'忽略无效整数参数 {key_lower}={value!r}: {exc}')

    if auto_date_from and not any(k == 'date_from' for k, _ in result):
        result.append(('date_from', auto_date_from))
    if auto_date_to and not any(k == 'date_to' for k, _ in result):
        result.append(('date_to', auto_date_to))

    return result


def build_query_url(endpoint_path: str, base_url: str, params: Optional[Dict[str, Any]] = None) -> str:
    base = normalize_base_url(base_url)
    endpoint = endpoint_path.strip('/')
    query_tuples = normalize_filter_params(params)
    if query_tuples:
        encoded_query = urllib.parse.urlencode(query_tuples)
        return f'{base}/{endpoint}?{encoded_query}'
    return f'{base}/{endpoint}'


def build_search_url(base_url: str, query_param: str, query_value: str) -> str:
    return build_query_url('api/search', base_url, {query_param: query_value})


def build_random_url(base_url: str, count: int = 1, tag: str = '', **filter_kwargs) -> str:
    params = dict(filter_kwargs)
    params['count'] = max(1, int(count))
    if tag:
        params['tag'] = tag
    return build_query_url('api/random', base_url, params)


def fetch_json(search_url: str, timeout_seconds: int) -> Dict[str, Any]:
    request = urllib.request.Request(search_url, headers={'User-Agent': 'IWannaSearch/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response_object:
            charset = response_object.headers.get_content_charset() or 'utf-8'
            response_text = response_object.read().decode(charset, errors='replace')
        parsed_data = json.loads(response_text)
        if not isinstance(parsed_data, dict):
            raise ValueError('API 返回值不是 JSON 对象')
        return parsed_data
    except urllib.error.HTTPError as exception_object:
        err_msg = f'HTTP {exception_object.code}'
        try:
            charset = exception_object.headers.get_content_charset() or 'utf-8'
            body = exception_object.read().decode(charset, errors='replace')
            data = json.loads(body)
            if isinstance(data, dict):
                server_error = data.get('error')
                if server_error:
                    err_msg = f'{err_msg}：{server_error}'
                elif data.get('errors'):
                    err_msg = f'{err_msg}：{"; ".join(str(e) for e in data.get("errors", []))}'
        except Exception:
            pass
        raise ValueError(err_msg) from exception_object


def request_api_url(api_url: str, timeout_seconds: int) -> Dict[str, Any]:
    try:
        api_data = fetch_json(api_url, timeout_seconds)
    except urllib.error.HTTPError as exception_object:
        return {'ok': False, 'error': f'HTTP {exception_object.code}', 'results': [], 'count': 0}
    except urllib.error.URLError as exception_object:
        return {'ok': False, 'error': safe_text(exception_object.reason, '网络连接失败'), 'results': [], 'count': 0}
    except TimeoutError:
        return {'ok': False, 'error': '请求超时', 'results': [], 'count': 0}
    except ValueError as exception_object:
        return {'ok': False, 'error': safe_text(exception_object, 'API 错误'), 'results': [], 'count': 0}
    except Exception as exception_object:
        return {'ok': False, 'error': f'{type(exception_object).__name__}: {exception_object}', 'results': [], 'count': 0}

    if not api_data.get('success', False):
        error_text = api_data.get('error', 'API 返回 success=false')
        return {'ok': False, 'error': error_text, 'results': [], 'count': 0}

    results = api_data.get('results', [])
    if not isinstance(results, list):
        results = []
    normalized_results = [normalize_game_item(item) for item in results if isinstance(item, dict)]
    count_value = api_data.get('count', len(normalized_results))
    try:
        count = int(count_value)
    except Exception:
        count = len(normalized_results)
    if count < len(normalized_results):
        count = len(normalized_results)

    return {'ok': True, 'error': '', 'results': normalized_results, 'count': count}


INDEX_FIELDS = (
    'id,title,creator,tags,engine,release_date,rating,difficulty,'
    'rating_count,file_size,url,page_url,source,screenshots'
)

LOCAL_INDEX_ALLOWED_KEYS = {
    'q', 'title', 'creator', 'id',
    'tag', 'tag_all', 'tag_not',
    'engine', 'engine_not', 'has_engine',
    'date_from', 'date_to', 'date_in', 'date_not', 'has_date',
    'rating_min', 'rating_max',
    'difficulty_min', 'difficulty_max',
    'reviews_min', 'reviews_max',
    'size_min_mb', 'size_max_mb',
    'source', 'source_not', 'source_id',
    'sort', 'order', 'limit',
}

LOCAL_INDEX_ALIAS_MAP = {
    'query': 'q',
    'name': 'q',
    'keyword': 'q',
    'game_id': 'id',
    'tags': 'tag',
    'tags_all': 'tag_all',
    'all_tag': 'tag_all',
    'all_tags': 'tag_all',
    'tags_not': 'tag_not',
    'not_tag': 'tag_not',
    'not_tags': 'tag_not',
    'engines': 'engine',
    'engines_not': 'engine_not',
    'not_engine': 'engine_not',
    'not_engines': 'engine_not',
    'from_date': 'date_from',
    'start_date': 'date_from',
    'to_date': 'date_to',
    'end_date': 'date_to',
    'min_rating': 'rating_min',
    'max_rating': 'rating_max',
    'min_difficulty': 'difficulty_min',
    'max_difficulty': 'difficulty_max',
    'min_reviews': 'reviews_min',
    'max_reviews': 'reviews_max',
    'sources': 'source',
    'sources_not': 'source_not',
    'not_source': 'source_not',
    'not_sources': 'source_not',
}

LOCAL_INDEX_VALID_SORTS = {
    'id', 'title', 'creator', 'rating', 'difficulty', 'date', 'reviews', 'size', 'random',
}

_index_lock = threading.RLock()
_index_build_lock = threading.Lock()
_index_cache: Dict[str, Any] = {
    'path': '',
    'built_at': 0.0,
    'count': 0,
    'items': [],
    'loaded': False,
}


def get_index_path() -> str:
    """返回本地全库索引文件路径。"""
    return os.path.join(config.plugin_data_dir, 'cache', 'iwanna_index.json')


def _get_index_refresh_hours() -> float:
    global_config = utils.load_global_config()
    try:
        hours = float(global_config.get('index_refresh_hours', 24))
    except Exception as exc:
        utils.info_log(utils.get_runtime_proc(), f'读取 index_refresh_hours 失败，使用默认值 24：{exc}')
        hours = 24.0
    return hours


def _get_index_build_timeout() -> int:
    global_config = utils.load_global_config()
    try:
        timeout = int(global_config.get('index_build_timeout_seconds', 180))
    except Exception as exc:
        utils.info_log(utils.get_runtime_proc(), f'读取 index_build_timeout_seconds 失败，使用默认值 180：{exc}')
        timeout = 180
    return max(10, timeout)


def _is_local_index_enabled() -> bool:
    global_config = utils.load_global_config()
    return bool(global_config.get('local_index_enable', True))


def _read_index_from_disk(index_path: str) -> Optional[Dict[str, Any]]:
    """从磁盘读取本地索引文件并校验基本结构。"""
    if not os.path.isfile(index_path):
        return None
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            utils.error_log(utils.get_runtime_proc(), f'本地索引文件格式无效（非对象）：{index_path}')
            return None
        items = data.get('items')
        if not isinstance(items, list):
            utils.error_log(utils.get_runtime_proc(), f'本地索引文件缺少 items 列表：{index_path}')
            return None
        valid_items = [item for item in items if isinstance(item, dict)]
        try:
            built_at = float(data.get('built_at', 0) or 0)
        except Exception as exc:
            utils.info_log(utils.get_runtime_proc(), f'本地索引 built_at 解析失败，按 0 处理：{exc}')
            built_at = 0.0
        return {
            'path': index_path,
            'built_at': built_at,
            'count': len(valid_items),
            'items': valid_items,
            'loaded': True,
        }
    except Exception as exc:
        utils.error_log(utils.get_runtime_proc(), f'读取本地索引文件失败 {index_path}：{type(exc).__name__}: {exc}')
        return None


def _get_cached_or_disk_entry() -> Optional[Dict[str, Any]]:
    """非阻塞获取内存缓存或磁盘上的索引记录，绝不触发重建。"""
    index_path = get_index_path()
    with _index_lock:
        if _index_cache['loaded'] and _index_cache['path'] == index_path:
            return dict(_index_cache)
    disk_entry = _read_index_from_disk(index_path)
    if disk_entry is not None:
        with _index_lock:
            _index_cache.update(disk_entry)
            return dict(_index_cache)
    return None


def index_is_stale() -> bool:
    """判断本地索引是否已超过刷新周期（不存在或 built_at 无效均视为过期）。"""
    entry = _get_cached_or_disk_entry()
    if entry is None:
        return True
    built_at = float(entry.get('built_at', 0) or 0)
    if built_at <= 0:
        return True
    refresh_hours = _get_index_refresh_hours()
    if refresh_hours <= 0:
        return True
    return (time.time() - built_at) > (refresh_hours * 3600.0)


def rebuild_index(base_url: str = '', timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
    """同步请求 /api/all 构建本地索引并原子写盘。"""
    global_config = utils.load_global_config()
    target_base = normalize_base_url(base_url or global_config.get('api_base_url', config.api_default_base_url))
    if timeout_seconds is not None:
        try:
            target_timeout = max(5, int(timeout_seconds))
        except Exception as exc:
            utils.info_log(utils.get_runtime_proc(), f'索引构建超时参数无效，改用配置默认值：{exc}')
            target_timeout = _get_index_build_timeout()
    else:
        target_timeout = _get_index_build_timeout()

    query_url = build_query_url(
        'api/all',
        target_base,
        {'limit': 0, 'fields': INDEX_FIELDS},
    )

    with _index_build_lock:
        tmp_path = ''
        try:
            data = fetch_json(query_url, target_timeout)
            if not data.get('success', False):
                err_msg = safe_text(data.get('error', 'API 返回 success=false'))
                utils.error_log(utils.get_runtime_proc(), f'构建本地索引失败：{err_msg}')
                return {'ok': False, 'items': [], 'count': 0, 'built_at': 0, 'error': err_msg}

            raw_results = data.get('results', [])
            if not isinstance(raw_results, list):
                err_msg = 'API 返回的 results 不是列表'
                utils.error_log(utils.get_runtime_proc(), f'构建本地索引失败：{err_msg}')
                return {'ok': False, 'items': [], 'count': 0, 'built_at': 0, 'error': err_msg}

            items = [item for item in raw_results if isinstance(item, dict)]
            built_at = int(time.time())
            count = len(items)
            payload = {
                'built_at': built_at,
                'count': count,
                'items': items,
            }

            index_path = get_index_path()
            cache_dir = os.path.dirname(index_path)
            os.makedirs(cache_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix='iwanna_index_', suffix='.tmp', dir=cache_dir)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as tmp_file:
                    json.dump(payload, tmp_file, ensure_ascii=False)
                    tmp_file.flush()
                os.replace(tmp_path, index_path)
                tmp_path = ''
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    _remove_file(tmp_path)

            with _index_lock:
                _index_cache.update({
                    'path': index_path,
                    'built_at': float(built_at),
                    'count': count,
                    'items': items,
                    'loaded': True,
                })

            utils.info_log(utils.get_runtime_proc(), f'本地索引构建完成：共 {count} 条。')
            return {'ok': True, 'items': items, 'count': count, 'built_at': built_at, 'error': ''}
        except Exception as exc:
            err_msg = f'{type(exc).__name__}: {safe_text(exc)}'
            utils.error_log(utils.get_runtime_proc(), f'构建本地索引异常：{err_msg}')
            return {'ok': False, 'items': [], 'count': 0, 'built_at': 0, 'error': err_msg}


def load_index(force: bool = False) -> Dict[str, Any]:
    """加载本地索引：内存缓存 -> 磁盘 -> 重建。"""
    if not force:
        entry = _get_cached_or_disk_entry()
        if entry is not None:
            return {
                'ok': True,
                'items': entry['items'],
                'count': entry['count'],
                'built_at': entry['built_at'],
                'error': '',
            }
    return rebuild_index()


_async_refresh_lock = threading.Lock()
_async_refresh_running = False


_warm_lock = threading.Lock()
_warm_running = False


def warm_index_async() -> None:
    """把磁盘索引预读进内存（不重建），避免上线后第一次查询卡在 JSON 解析上。"""
    global _warm_running
    if not _is_local_index_enabled():
        return
    if _get_cached_or_disk_entry() is not None:
        return
    with _warm_lock:
        if _warm_running:
            return
        _warm_running = True

    def _worker() -> None:
        global _warm_running
        try:
            entry = _get_cached_or_disk_entry()
            if entry:
                utils.info_log(
                    utils.get_runtime_proc(),
                    f'本地索引已预读入内存：{len(entry.get("items") or [])} 条',
                )
        except Exception as exc:  # noqa: BLE001
            utils.error_log(utils.get_runtime_proc(), f'预读本地索引失败：{type(exc).__name__}: {exc}')
        finally:
            with _warm_lock:
                _warm_running = False

    try:
        threading.Thread(target=_worker, name='IWannaIndexWarm', daemon=True).start()
    except Exception as exc:  # noqa: BLE001
        with _warm_lock:
            _warm_running = False
        utils.error_log(utils.get_runtime_proc(), f'启动索引预读线程失败：{type(exc).__name__}: {exc}')


def maybe_refresh_index_async(force: bool = False) -> None:
    """在后台线程按需刷新本地索引，同一时间只允许一次后台构建。"""
    global _async_refresh_running
    if not _is_local_index_enabled():
        return
    if not force and not index_is_stale():
        return

    with _async_refresh_lock:
        if _async_refresh_running or _index_build_lock.locked():
            return
        _async_refresh_running = True

    def _worker() -> None:
        global _async_refresh_running
        try:
            utils.info_log(utils.get_runtime_proc(), '开始后台刷新本地游戏索引...')
            rebuild_index()
        except Exception as exc:
            utils.error_log(utils.get_runtime_proc(), f'后台刷新本地索引失败：{type(exc).__name__}: {exc}')
        finally:
            with _async_refresh_lock:
                _async_refresh_running = False

    try:
        worker = threading.Thread(target=_worker, name='IWannaIndexRefresh', daemon=True)
        worker.start()
    except Exception as exc:
        with _async_refresh_lock:
            _async_refresh_running = False
        utils.error_log(utils.get_runtime_proc(), f'启动本地索引刷新线程失败：{type(exc).__name__}: {exc}')


def get_index_status() -> Dict[str, Any]:
    """获取本地索引状态摘要，供状态指令展示。"""
    index_path = get_index_path()
    entry = _get_cached_or_disk_entry()
    exists = os.path.isfile(index_path)
    size_bytes = 0
    if exists:
        try:
            size_bytes = os.path.getsize(index_path)
        except OSError as exc:
            utils.error_log(utils.get_runtime_proc(), f'获取索引文件大小失败：{exc}')
    count = int(entry.get('count', 0)) if entry else 0
    built_at = float(entry.get('built_at', 0) or 0) if entry else 0.0
    return {
        'enabled': _is_local_index_enabled(),
        'exists': exists,
        'count': count,
        'built_at': built_at,
        'size_mb': size_bytes / 1024.0 / 1024.0,
        'stale': index_is_stale(),
    }


def _collect_str_list(value: Any, split_comma: bool = False, lowercase: bool = False) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    elif split_comma:
        raw_items = safe_text(value).split(',')
    else:
        raw_items = [value]
    out: List[str] = []
    for item in raw_items:
        if item is None:
            continue
        s = safe_text(item).strip()
        if not s:
            continue
        if lowercase:
            s = s.lower()
        out.append(s)
    return out


def _parse_bool_filter(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    s = safe_text(value).strip().lower()
    if s in {'true', '1', 'yes', 'on'}:
        return True
    if s in {'false', '0', 'no', 'off'}:
        return False
    return None


def _parse_float_filter(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    s = safe_text(value).strip()
    if not s:
        return None
    val = float(s)
    if not math.isfinite(val):
        raise ValueError('非有限数值')
    return val


def _normalize_date_bound(bound: str, is_end: bool) -> str:
    s = bound.strip()
    if not s:
        return ''
    if re.fullmatch(r'\d{4}', s):
        return f'{s}-12-31' if is_end else f'{s}-01-01'
    if re.fullmatch(r'\d{4}-\d{2}', s):
        return f'{s}-31' if is_end else f'{s}-01'
    return s


def _parse_date_range_expr(expr: str) -> tuple:
    text = safe_text(expr).strip()
    if ':' in text:
        start_raw, _, end_raw = text.partition(':')
    else:
        start_raw, end_raw = text, text
    return _normalize_date_bound(start_raw, False), _normalize_date_bound(end_raw, True)


def _date_in_bounds(rel_date: str, start_bound: str, end_bound: str) -> bool:
    if start_bound and rel_date < start_bound:
        return False
    if end_bound and rel_date > end_bound:
        return False
    return True


def _match_numeric_bounds(raw_val: Any, min_val: Optional[float], max_val: Optional[float], divisor: float = 1.0) -> bool:
    if min_val is None and max_val is None:
        return True
    if raw_val is None or isinstance(raw_val, bool):
        return False
    try:
        num = float(raw_val) / divisor
    except Exception as exc:
        utils.info_log(utils.get_runtime_proc(), f'索引数值字段解析失败，已排除：{raw_val!r} ({exc})')
        return False
    if not math.isfinite(num):
        return False
    if min_val is not None and num < min_val:
        return False
    if max_val is not None and num > max_val:
        return False
    return True


def _extract_item_sources(item: Dict[str, Any]) -> tuple:
    source_types = set()
    source_ids = set()
    for src in (item.get('source') or []):
        if not isinstance(src, dict):
            continue
        s_type = safe_text(src.get('type', '')).strip().lower()
        s_site = safe_text(src.get('site', '')).strip().lower()
        s_url = safe_text(src.get('url', '')).strip().lower()
        s_id = safe_text(src.get('id', '')).strip()
        if s_type:
            source_types.add(s_type)
        if s_site:
            source_types.add(s_site)
        if 'delicious-fruit' in s_url or 'delicious' in s_site:
            source_types.add('df')
        if 'iwannawiki' in s_url or 'wiki' in s_site:
            source_types.add('wiki')
        if s_id:
            source_ids.add(s_id)
    return source_types, source_ids


def _prepare_local_filters(filters: Optional[Dict[str, Any]]) -> tuple:
    """将输入 filters 规范化并检查是否全部可由本地索引求值。"""
    if not filters:
        return True, {}
    normalized: Dict[str, Any] = {}
    for key, value in filters.items():
        if value is None:
            continue
        key_lower = safe_text(key).strip().lower()
        if not key_lower:
            continue
        if key_lower == 'year':
            normalized['year'] = value
            continue
        mapped = LOCAL_INDEX_ALIAS_MAP.get(key_lower, key_lower)
        if mapped not in LOCAL_INDEX_ALLOWED_KEYS:
            return False, {}
        normalized[mapped] = value

    year_val = normalized.pop('year', None)
    has_explicit_date = any(
        _has_nonempty_param(normalized.get(k)) for k in ('date_from', 'date_to', 'date_in')
    )
    if year_val is not None and not has_explicit_date:
        year_str = safe_text(year_val).strip()
        if year_str:
            if not re.fullmatch(r'\d{4}', year_str):
                return False, {}
            normalized['date_from'] = f'{year_str}-01-01'
            normalized['date_to'] = f'{year_str}-12-31'

    sort_val = safe_text(normalized.get('sort', '')).strip().lower()
    if sort_val and sort_val not in LOCAL_INDEX_VALID_SORTS:
        return False, {}

    # 布尔/数值参数无法解析时回落 API，保持报错或边界语义一致
    for bool_key in ('has_engine', 'has_date'):
        if bool_key in normalized and _has_nonempty_param(normalized[bool_key]):
            if _parse_bool_filter(normalized[bool_key]) is None:
                return False, {}

    for num_key in (
        'rating_min', 'rating_max',
        'difficulty_min', 'difficulty_max',
        'reviews_min', 'reviews_max',
        'size_min_mb', 'size_max_mb',
    ):
        if num_key in normalized and _has_nonempty_param(normalized[num_key]):
            try:
                _parse_float_filter(normalized[num_key])
            except Exception as exc:
                utils.info_log(utils.get_runtime_proc(), f'过滤参数 {num_key}={normalized[num_key]!r} 非有效数字，回落 API：{exc}')
                return False, {}

    return True, normalized


def _filter_local_items(items: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """按 API 语义对本地索引记录列表执行纯内存过滤。"""
    q_lower = safe_text(filters.get('q', '')).strip().lower()
    title_lower = safe_text(filters.get('title', '')).strip().lower()
    creator_lower = safe_text(filters.get('creator', '')).strip().lower()
    target_ids = set(_collect_str_list(filters.get('id'), split_comma=True))

    tags_any = _collect_str_list(filters.get('tag'), split_comma=True, lowercase=True)
    tags_all = _collect_str_list(filters.get('tag_all'), split_comma=True, lowercase=True)
    tags_not = set(_collect_str_list(filters.get('tag_not'), split_comma=True, lowercase=True))

    engines_any = set(_collect_str_list(filters.get('engine'), split_comma=False, lowercase=True))
    engines_not = set(_collect_str_list(filters.get('engine_not'), split_comma=False, lowercase=True))
    has_engine = _parse_bool_filter(filters.get('has_engine')) if _has_nonempty_param(filters.get('has_engine')) else None

    has_date = _parse_bool_filter(filters.get('has_date')) if _has_nonempty_param(filters.get('has_date')) else None
    date_from = _normalize_date_bound(safe_text(filters.get('date_from', '')), False)
    date_to = _normalize_date_bound(safe_text(filters.get('date_to', '')), True)
    date_in_ranges = [_parse_date_range_expr(expr) for expr in _collect_str_list(filters.get('date_in'))]
    date_not_ranges = [_parse_date_range_expr(expr) for expr in _collect_str_list(filters.get('date_not'))]
    has_date_range_filter = bool(date_from or date_to or date_in_ranges or date_not_ranges)

    rating_min = _parse_float_filter(filters.get('rating_min'))
    rating_max = _parse_float_filter(filters.get('rating_max'))
    difficulty_min = _parse_float_filter(filters.get('difficulty_min'))
    difficulty_max = _parse_float_filter(filters.get('difficulty_max'))
    reviews_min = _parse_float_filter(filters.get('reviews_min'))
    reviews_max = _parse_float_filter(filters.get('reviews_max'))
    size_min_mb = _parse_float_filter(filters.get('size_min_mb'))
    size_max_mb = _parse_float_filter(filters.get('size_max_mb'))

    sources_any = set(_collect_str_list(filters.get('source'), split_comma=False, lowercase=True))
    sources_not = set(_collect_str_list(filters.get('source_not'), split_comma=False, lowercase=True))
    source_ids_req = set(_collect_str_list(filters.get('source_id'), split_comma=True))

    matched: List[Dict[str, Any]] = []
    for item in items:
        if target_ids and safe_text(item.get('id', '')).strip() not in target_ids:
            continue

        item_title = safe_text(item.get('title', '')).lower()
        item_creator = safe_text(item.get('creator', '')).lower()
        raw_tags = item.get('tags') if isinstance(item.get('tags'), list) else []
        item_tags_lower = [safe_text(t).strip().lower() for t in raw_tags if not value_is_empty(t)]
        item_tags_set = set(item_tags_lower)

        if q_lower:
            if (
                q_lower not in item_title
                and q_lower not in item_creator
                and not any(q_lower in t for t in item_tags_lower)
            ):
                continue
        if title_lower and title_lower not in item_title:
            continue
        if creator_lower and creator_lower not in item_creator:
            continue

        if tags_any and not any(t in item_tags_set for t in tags_any):
            continue
        if tags_all and not all(t in item_tags_set for t in tags_all):
            continue
        if tags_not and any(t in item_tags_set for t in tags_not):
            continue

        raw_engine = item.get('engine')
        engine_str = '' if raw_engine is None else safe_text(raw_engine).strip()
        engine_lower = engine_str.lower()
        if has_engine is True and not engine_str:
            continue
        if has_engine is False and engine_str:
            continue
        if engines_any and (not engine_str or engine_lower not in engines_any):
            continue
        if engines_not and engine_lower in engines_not:
            continue

        raw_date = item.get('release_date')
        rel_date = '' if raw_date is None else safe_text(raw_date).strip()
        if has_date is True and not rel_date:
            continue
        if has_date is False and rel_date:
            continue
        if has_date_range_filter:
            if not rel_date:
                continue
            if (date_from or date_to) and not _date_in_bounds(rel_date, date_from, date_to):
                continue
            if date_in_ranges and not any(_date_in_bounds(rel_date, s, e) for s, e in date_in_ranges):
                continue
            if date_not_ranges and any(_date_in_bounds(rel_date, s, e) for s, e in date_not_ranges):
                continue

        if not _match_numeric_bounds(item.get('rating'), rating_min, rating_max):
            continue
        if not _match_numeric_bounds(item.get('difficulty'), difficulty_min, difficulty_max):
            continue
        if not _match_numeric_bounds(item.get('rating_count'), reviews_min, reviews_max):
            continue
        if not _match_numeric_bounds(item.get('file_size'), size_min_mb, size_max_mb, divisor=1024.0 * 1024.0):
            continue

        if sources_any or sources_not or source_ids_req:
            item_sources, item_source_ids = _extract_item_sources(item)
            if sources_any and not any(src in item_sources for src in sources_any):
                continue
            if sources_not and any(src in item_sources for src in sources_not):
                continue
            if source_ids_req and not any(sid in item_source_ids for sid in source_ids_req):
                continue

        matched.append(item)

    return matched


def _extract_sort_key(item: Dict[str, Any], sort_field: str):
    if sort_field == 'id':
        try:
            return int(item.get('id'))
        except Exception as exc:
            utils.info_log(utils.get_runtime_proc(), f'索引排序字段 id 解析失败：{item.get("id")!r} ({exc})')
            return None
    if sort_field == 'title':
        val = safe_text(item.get('title', '')).strip().lower()
        return val if val else None
    if sort_field == 'creator':
        val = safe_text(item.get('creator', '')).strip().lower()
        return val if val else None
    if sort_field == 'rating':
        val = item.get('rating')
        if val is None or isinstance(val, bool):
            return None
        try:
            num = float(val)
            return num if math.isfinite(num) else None
        except Exception as exc:
            utils.info_log(utils.get_runtime_proc(), f'索引排序字段 rating 解析失败：{val!r} ({exc})')
            return None
    if sort_field == 'difficulty':
        val = item.get('difficulty')
        if val is None or isinstance(val, bool):
            return None
        try:
            num = float(val)
            return num if math.isfinite(num) else None
        except Exception as exc:
            utils.info_log(utils.get_runtime_proc(), f'索引排序字段 difficulty 解析失败：{val!r} ({exc})')
            return None
    if sort_field == 'date':
        val = item.get('release_date')
        s = '' if val is None else safe_text(val).strip()
        return s if s else None
    if sort_field == 'reviews':
        val = item.get('rating_count')
        if val is None or isinstance(val, bool):
            return None
        try:
            return int(val)
        except Exception as exc:
            utils.info_log(utils.get_runtime_proc(), f'索引排序字段 rating_count 解析失败：{val!r} ({exc})')
            return None
    if sort_field == 'size':
        val = item.get('file_size')
        if val is None or isinstance(val, bool):
            return None
        try:
            num = float(val)
            return num if math.isfinite(num) else None
        except Exception as exc:
            utils.info_log(utils.get_runtime_proc(), f'索引排序字段 file_size 解析失败：{val!r} ({exc})')
            return None
    return None


def _sort_local_items(items: List[Dict[str, Any]], sort_field: str, order: str) -> List[Dict[str, Any]]:
    if not sort_field:
        return items
    if sort_field == 'random':
        shuffled = list(items)
        random.shuffle(shuffled)
        return shuffled

    reverse = safe_text(order).strip().lower() == 'desc'
    with_key = []
    without_key = []
    for item in items:
        key = _extract_sort_key(item, sort_field)
        if key is None:
            without_key.append(item)
        else:
            with_key.append((key, item))
    with_key.sort(key=lambda pair: pair[0], reverse=reverse)
    return [pair[1] for pair in with_key] + without_key


def search_local_index(filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """基于本地索引执行纯本地过滤、排序与限量截取，返回原始记录。"""
    entry = _get_cached_or_disk_entry()
    if entry is None:
        return {'ok': False, 'error': '本地索引不可用', 'results': [], 'count': 0}

    ok, normalized = _prepare_local_filters(filters)
    if not ok:
        return {'ok': False, 'error': '包含不支持本地求值的过滤参数', 'results': [], 'count': 0}

    matched = _filter_local_items(entry['items'], normalized)
    sort_field = safe_text(normalized.get('sort', '')).strip().lower()
    order = safe_text(normalized.get('order', 'asc')).strip().lower()
    sorted_items = _sort_local_items(matched, sort_field, order)
    total_count = len(sorted_items)

    limit_val = 100
    if 'limit' in normalized and _has_nonempty_param(normalized.get('limit')):
        try:
            parsed_limit = int(normalized['limit'])
            if parsed_limit >= 0:
                limit_val = parsed_limit
        except Exception as exc:
            utils.info_log(utils.get_runtime_proc(), f'本地索引 limit 参数无效，使用默认 100：{exc}')

    sliced = sorted_items if limit_val == 0 else sorted_items[:limit_val]
    return {
        'ok': True,
        'error': '',
        'results': sliced,
        'count': total_count,
    }


def random_local_index(count: int = 1, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """基于本地索引按条件随机抽样，返回原始记录。"""
    entry = _get_cached_or_disk_entry()
    if entry is None:
        return {'ok': False, 'error': '本地索引不可用', 'results': [], 'count': 0}

    ok, normalized = _prepare_local_filters(filters)
    if not ok:
        return {'ok': False, 'error': '包含不支持本地求值的过滤参数', 'results': [], 'count': 0}

    matched = _filter_local_items(entry['items'], normalized)
    total_count = len(matched)
    req_count = max(1, int(count))
    sampled = random.sample(matched, min(req_count, total_count)) if total_count > 0 else []
    return {
        'ok': True,
        'error': '',
        'results': sampled,
        'count': total_count,
    }


def _try_local_search(filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _is_local_index_enabled():
        return None
    if _index_build_lock.locked():
        return None
    can_eval, normalized = _prepare_local_filters(filters)
    if not can_eval:
        return None
    if _get_cached_or_disk_entry() is None:
        return None
    local_res = search_local_index(normalized)
    if not local_res.get('ok', False):
        return None
    return {
        'ok': True,
        'error': '',
        'results': [normalize_game_item(item) for item in local_res.get('results', [])],
        'count': local_res.get('count', 0),
    }


def _try_local_random(count: int, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _is_local_index_enabled():
        return None
    if _index_build_lock.locked():
        return None
    can_eval, normalized = _prepare_local_filters(filters)
    if not can_eval:
        return None
    if _get_cached_or_disk_entry() is None:
        return None
    local_res = random_local_index(count, normalized)
    if not local_res.get('ok', False):
        return None
    return {
        'ok': True,
        'error': '',
        'results': [normalize_game_item(item) for item in local_res.get('results', [])],
        'count': local_res.get('count', 0),
    }


def request_search(
    query_param_or_filters: Any,
    query_value: Any = None,
    base_url: str = '',
    timeout_seconds: int = 10,
) -> Dict[str, Any]:
    if isinstance(query_param_or_filters, dict):
        filters = dict(query_param_or_filters)
        target_base = safe_text(query_value or base_url)
        target_timeout = timeout_seconds if query_value else (base_url or 10)
        try:
            target_timeout = int(target_timeout)
        except Exception as exc:
            utils.info_log(utils.get_runtime_proc(), f'解析搜索超时失败，使用默认值 10：{exc}')
            target_timeout = 10
    else:
        filters = {safe_text(query_param_or_filters): query_value}
        target_base = base_url
        target_timeout = timeout_seconds

    try:
        local_payload = _try_local_search(filters)
        if local_payload is not None:
            return local_payload
    except Exception as exc:
        utils.error_log(utils.get_runtime_proc(), f'本地索引搜索异常，回落 API：{type(exc).__name__}: {exc}')

    search_url = build_query_url('api/search', target_base, filters)
    return request_api_url(search_url, target_timeout)


def search_by_id(game_id: str, base_url: str, timeout_seconds: int) -> Dict[str, Any]:
    return request_search('id', safe_text(game_id).strip(), base_url, timeout_seconds)


def search_by_name(game_name: str, base_url: str, timeout_seconds: int, **filter_kwargs) -> Dict[str, Any]:
    filters = dict(filter_kwargs)
    safe_name = safe_text(game_name).strip()
    if safe_name:
        filters['q'] = safe_name
    return request_search(filters, base_url, timeout_seconds)


def search_catalog(filters: Dict[str, Any], base_url: str, timeout_seconds: int) -> Dict[str, Any]:
    return request_search(filters, base_url, timeout_seconds)


def random_games(count: int = 1, tag: str = '', base_url: str = '', timeout_seconds: int = 10, **filter_kwargs) -> Dict[str, Any]:
    req_count = max(1, int(count))
    local_filters = dict(filter_kwargs)
    if tag:
        local_filters['tag'] = tag
    try:
        local_payload = _try_local_random(req_count, local_filters)
        if local_payload is not None:
            return local_payload
    except Exception as exc:
        utils.error_log(utils.get_runtime_proc(), f'本地索引随机异常，回落 API：{type(exc).__name__}: {exc}')

    params = dict(local_filters)
    params['count'] = req_count
    return request_api_url(build_query_url('api/random', base_url, params), timeout_seconds)


def fetch_catalog_all(base_url: str, timeout_seconds: int, **filter_kwargs) -> Dict[str, Any]:
    query_url = build_query_url('api/all', base_url, filter_kwargs)
    try:
        data = fetch_json(query_url, timeout_seconds)
    except Exception as exc:
        return {'ok': False, 'error': safe_text(exc), 'results': [], 'count': 0, 'catalog_size': 0, 'total': 0}
    if not data.get('success', False):
        return {'ok': False, 'error': safe_text(data.get('error', 'API 返回 success=false')), 'results': [], 'count': 0, 'catalog_size': 0, 'total': 0}
    results = data.get('results', [])
    if not isinstance(results, list):
        results = []
    normalized = [normalize_game_item(item) for item in results if isinstance(item, dict)]
    return {
        'ok': True,
        'error': '',
        'catalog_size': int(data.get('catalog_size', len(normalized))),
        'total': int(data.get('total', len(normalized))),
        'count': int(data.get('count', len(normalized))),
        'results': normalized,
    }


def fetch_tags(base_url: str, timeout_seconds: int, **filter_kwargs) -> Dict[str, Any]:
    query_url = build_query_url('api/tag', base_url, filter_kwargs)
    try:
        data = fetch_json(query_url, timeout_seconds)
    except Exception as exc:
        return {'ok': False, 'error': safe_text(exc), 'tags': [], 'count': 0}
    if not data.get('success', False):
        return {'ok': False, 'error': safe_text(data.get('error', 'API 返回 success=false')), 'tags': [], 'count': 0}
    tags = data.get('tags', [])
    if not isinstance(tags, list):
        tags = []
    return {
        'ok': True,
        'error': '',
        'count': int(data.get('count', len(tags))),
        'tags': tags,
    }


def fetch_engines(base_url: str, timeout_seconds: int, **filter_kwargs) -> Dict[str, Any]:
    query_url = build_query_url('api/engine', base_url, filter_kwargs)
    try:
        data = fetch_json(query_url, timeout_seconds)
    except Exception as exc:
        return {'ok': False, 'error': safe_text(exc), 'engines': [], 'count': 0}
    if not data.get('success', False):
        return {'ok': False, 'error': safe_text(data.get('error', 'API 返回 success=false')), 'engines': [], 'count': 0}
    engines = data.get('engines', [])
    if not isinstance(engines, list):
        engines = []
    return {
        'ok': True,
        'error': '',
        'count': int(data.get('count', len(engines))),
        'engines': engines,
    }


def fetch_release_dates(base_url: str, timeout_seconds: int, **filter_kwargs) -> Dict[str, Any]:
    query_url = build_query_url('api/releasedate', base_url, filter_kwargs)
    try:
        data = fetch_json(query_url, timeout_seconds)
    except Exception as exc:
        return {'ok': False, 'error': safe_text(exc), 'dated': 0, 'undated': 0, 'earliest': default_empty_text, 'latest': default_empty_text, 'by_year': []}
    if not data.get('success', False):
        return {'ok': False, 'error': safe_text(data.get('error', 'API 返回 success=false')), 'dated': 0, 'undated': 0, 'earliest': default_empty_text, 'latest': default_empty_text, 'by_year': []}
    return {
        'ok': True,
        'error': '',
        'dated': int(data.get('dated', 0)),
        'undated': int(data.get('undated', 0)),
        'games_considered': int(data.get('games_considered', 0)),
        'earliest': safe_text(data.get('earliest', default_empty_text), default_empty_text),
        'latest': safe_text(data.get('latest', default_empty_text), default_empty_text),
        'by_year': data.get('by_year', []) if isinstance(data.get('by_year'), list) else [],
    }


def parse_file_size_bytes(value: Any) -> Optional[int]:
    """解析 API 或 HTTP 头中的字节数；非正数和非有限值视为无效。"""
    if value_is_empty(value) or isinstance(value, bool):
        return None
    try:
        numeric_value = float(value)
    except Exception:
        return None
    if not math.isfinite(numeric_value) or numeric_value <= 0:
        return None
    integer_value = int(numeric_value)
    if numeric_value != integer_value:
        return None
    return integer_value


def build_download_file_name(game_item: Dict[str, Any]) -> str:
    """从下载 URL 生成安全的群文件名，避免把路径片段直接带入本地文件名。"""
    game_id = safe_text(game_item.get('id', 'iwanna')).strip() or 'iwanna'
    download_url = safe_text(game_item.get('url', '')).strip()
    url_name = os.path.basename(urllib.parse.unquote(urllib.parse.urlsplit(download_url).path))
    extension = os.path.splitext(url_name)[1]
    if not re.fullmatch(r'\.[A-Za-z0-9]{1,12}', extension):
        extension = '.zip'

    title = safe_text(game_item.get('title', '')).strip()
    file_stem = f'{game_id}_{title}' if title else game_id
    file_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', file_stem).rstrip(' .')
    file_stem = file_stem[:140] or game_id
    return f'{file_stem}{extension.lower()}'


def validate_download_item(game_item: Dict[str, Any], max_file_size_bytes: int) -> Dict[str, Any]:
    """在发起下载前校验 API 给出的 URL 和文件大小。"""
    if not isinstance(game_item, dict):
        return {'ok': False, 'error_key': 'invalid_item', 'error': 'API 返回的游戏数据无效。'}

    download_url = safe_text(game_item.get('url', '')).strip()
    parsed_url = urllib.parse.urlsplit(download_url)
    if parsed_url.scheme not in {'http', 'https'} or not parsed_url.netloc:
        return {'ok': False, 'error_key': 'url_missing', 'error': 'API 未返回可下载链接。'}

    file_size = parse_file_size_bytes(game_item.get('file_size'))
    if file_size is None:
        return {'ok': False, 'error_key': 'size_unknown', 'error': 'API 未返回有效的文件大小。'}
    if file_size >= max_file_size_bytes:
        return {
            'ok': False,
            'error_key': 'too_large',
            'error': f'文件大小为 {format_file_size(file_size)}，必须小于 200 MB。',
            'file_size': file_size,
        }

    return {
        'ok': True,
        'url': download_url,
        'file_size': file_size,
        'file_name': build_download_file_name(game_item),
    }


def _remove_file(file_path: str) -> None:
    """尽力删除临时文件；调用方负责记录删除失败。"""
    if not file_path:
        return
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass


def download_game_file(
    download_info: Dict[str, Any],
    target_dir: str,
    timeout_seconds: int,
    max_file_size_bytes: int,
) -> Dict[str, Any]:
    """流式下载游戏文件，并在本地再次执行严格大小限制。"""
    download_url = safe_text(download_info.get('url', '')).strip()
    expected_size = parse_file_size_bytes(download_info.get('file_size'))
    if not download_url or expected_size is None:
        raise DownloadError('下载信息不完整，已取消下载。')
    if expected_size >= max_file_size_bytes:
        raise DownloadError('文件大小达到 200 MB 上限，已取消下载。')

    os.makedirs(target_dir, exist_ok=True)
    file_name = safe_text(download_info.get('file_name', 'iwanna.zip')).strip() or 'iwanna.zip'
    file_suffix = os.path.splitext(file_name)[1] or '.zip'
    temporary_path = ''
    try:
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix='iwanna_',
            suffix=file_suffix,
            dir=target_dir,
        )
        os.close(file_descriptor)

        request = urllib.request.Request(download_url, headers={'User-Agent': 'IWannaSearch/1.0'})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response_object:
            headers = getattr(response_object, 'headers', None)
            content_length = parse_file_size_bytes(headers.get('Content-Length')) if headers is not None else None
            if content_length is not None and content_length >= max_file_size_bytes:
                raise DownloadError('下载源文件大小达到 200 MB 上限，已取消下载。')

            total_size = 0
            with open(temporary_path, 'wb') as file_object:
                while True:
                    chunk = response_object.read(config.download_chunk_size_bytes)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size >= max_file_size_bytes:
                        raise DownloadError('实际下载文件达到 200 MB 上限，已取消下载。')
                    file_object.write(chunk)

        if total_size <= 0:
            raise DownloadError('下载源返回了空文件。')

        return {
            'path': temporary_path,
            'file_name': file_name,
            'file_size': total_size,
            'api_file_size': expected_size,
        }
    except DownloadError:
        _remove_file(temporary_path)
        raise
    except urllib.error.HTTPError as exception_object:
        _remove_file(temporary_path)
        raise DownloadError(f'下载源返回 HTTP {exception_object.code}') from exception_object
    except urllib.error.URLError as exception_object:
        _remove_file(temporary_path)
        raise DownloadError(f'无法连接下载源：{safe_text(exception_object.reason, "网络连接失败")}') from exception_object
    except TimeoutError as exception_object:
        _remove_file(temporary_path)
        raise DownloadError('下载超时。') from exception_object
    except Exception as exception_object:
        _remove_file(temporary_path)
        raise DownloadError(f'{type(exception_object).__name__}: {safe_text(exception_object)}') from exception_object


def normalize_game_item(item: Dict[str, Any]) -> Dict[str, Any]:
    tags = item.get('tags', [])
    if not isinstance(tags, list):
        tags = []

    source_list = item.get('source', [])
    if not isinstance(source_list, list):
        source_list = []

    df_url = ''
    wiki_url = ''
    source_names = []
    for s in source_list:
        if isinstance(s, dict):
            s_type = safe_text(s.get('type', '')).lower()
            s_url = safe_text(s.get('url', ''))
            s_site = safe_text(s.get('site', ''))
            if s_type == 'df' or 'delicious-fruit' in s_url or 'delicious' in s_site.lower():
                df_url = s_url
                if 'Delicious Fruit' not in source_names:
                    source_names.append('Delicious Fruit')
            elif s_type == 'wiki' or 'iwannawiki' in s_url or 'wiki' in s_site.lower():
                wiki_url = s_url
                if 'IWanna Wiki' not in source_names:
                    source_names.append('IWanna Wiki')
            elif s_site and s_site not in source_names:
                source_names.append(s_site)

    ext_parts = []
    if df_url:
        ext_parts.append(f'DF: {df_url}')
    if wiki_url:
        ext_parts.append(f'Wiki: {wiki_url}')
    external_urls = ' | '.join(ext_parts) if ext_parts else default_empty_text
    sources_text = ', '.join(source_names) if source_names else default_empty_text

    game_id = safe_text(item.get('id', default_empty_text), default_empty_text)
    page_url = safe_text(item.get('page_url', ''))
    if not page_url and game_id != default_empty_text:
        page_url = f'https://fangame-archive.com/?game={game_id}'
    if not page_url:
        page_url = default_empty_text

    # 封面：API 的 screenshots 第一张；外部页面按来源逐条留存，详情页拿来做按钮
    screenshot_list = [
        safe_text(shot).strip()
        for shot in (item.get('screenshots') or [])
        if safe_text(shot).strip().startswith(('http://', 'https://'))
    ]
    external_sources = []
    for source_item in source_list:
        if isinstance(source_item, dict) and safe_text(source_item.get('url')):
            external_sources.append({
                'site': safe_text(source_item.get('site')) or safe_text(source_item.get('type')).upper(),
                'url': safe_text(source_item.get('url')),
            })

    return {
        'id': game_id,
        'screenshots': screenshot_list,
        'cover_url': screenshot_list[0] if screenshot_list else '',
        'external_sources': external_sources,
        'title': safe_text(item.get('title', default_empty_text), default_empty_text),
        'creator': safe_text(item.get('creator', default_empty_text), default_empty_text),
        'url': safe_text(item.get('url', default_empty_text), default_empty_text),
        'tags': [safe_text(tag) for tag in tags if safe_text(tag)],
        'engine': item.get('engine'),
        'release_date': item.get('release_date'),
        'rating': item.get('rating'),
        'difficulty': item.get('difficulty'),
        'rating_count': item.get('rating_count'),
        'file_size': item.get('file_size'),
        'page_url': page_url,
        'df_url': df_url or default_empty_text,
        'wiki_url': wiki_url or default_empty_text,
        'sources': sources_text,
        'external_urls': external_urls,
    }


def format_score_value(value: Any, scale: int = 10) -> str:
    if value_is_empty(value):
        return default_empty_text
    try:
        return f'{float(value):.1f}/{scale}'
    except Exception:
        return default_empty_text


def format_rating_count(value: Any) -> str:
    if value_is_empty(value):
        return default_empty_text
    try:
        return f'{int(value)}人'
    except Exception:
        return f'{safe_text(value, default_empty_text)}人'


def format_file_size(value: Any) -> str:
    if value_is_empty(value):
        return default_empty_text
    try:
        byte_size = float(value)
        if byte_size <= 0:
            return default_empty_text
        return f'{byte_size / 1024 / 1024:.1f} MB'
    except Exception:
        return default_empty_text


def format_engine_value(value: Any) -> str:
    if value_is_empty(value):
        return '未知'
    return safe_text(value, '未知')


def format_release_date(value: Any) -> str:
    if value_is_empty(value):
        return default_empty_text
    return safe_text(value, default_empty_text)


def build_game_template_value(game_item: Dict[str, Any], index: int = 0) -> Dict[str, str]:
    tag_text = ', '.join(game_item.get('tags', [])) or default_empty_text
    raw_rating = game_item.get('rating')
    raw_difficulty = game_item.get('difficulty')
    rating_text = format_score_value(raw_rating, 10)
    difficulty_text = format_score_value(raw_difficulty, 100)
    meta_parts = []
    # 醒目标注：橙红色（#FF6B35）在这套深色卡片上对比强、又不刺眼；
    # QQ Markdown 不吃 <font color>，实测认 KaTeX 的 	extcolor（见 mark_text）。
    if not value_is_empty(raw_rating) and rating_text != default_empty_text:
        meta_parts.append(f' · 评分 {mark_text(rating_text, MARK_COLOR_RATING)}')
    if not value_is_empty(raw_difficulty) and difficulty_text != default_empty_text:
        meta_parts.append(f' · 难度 {mark_text(difficulty_text, MARK_COLOR_DIFFICULTY)}')
    return {
        'index': safe_text(index),
        # 列表序号由 markdown 层上色（见 markdown.mark_index），模板仍可用 {index}
        'index_mark': mark_text(safe_text(index)) if safe_text(index) else '',
        'id': safe_text(game_item.get('id', default_empty_text), default_empty_text),
        'title': safe_text(game_item.get('title', default_empty_text), default_empty_text),
        'meta': ''.join(meta_parts),
        'creator': safe_text(game_item.get('creator', default_empty_text), default_empty_text),
        'release_date': format_release_date(game_item.get('release_date')),
        # 详情页的 {rating}/{difficulty} 保持纯文本，颜色由 markdown.convert 按“评分：/难度：”统一加，
        # 这样各 bot 已保存的旧自定义模板也能变色
        'rating': rating_text,
        'difficulty': difficulty_text,
        'rating_count': format_rating_count(game_item.get('rating_count')),
        'tags': tag_text,
        'engine': format_engine_value(game_item.get('engine')),
        'url': safe_text(game_item.get('url', default_empty_text), default_empty_text),
        'file_size': format_file_size(game_item.get('file_size')),
        'page_url': safe_text(game_item.get('page_url', default_empty_text), default_empty_text),
        'df_url': safe_text(game_item.get('df_url', default_empty_text), default_empty_text),
        'wiki_url': safe_text(game_item.get('wiki_url', default_empty_text), default_empty_text),
        'sources': safe_text(game_item.get('sources', default_empty_text), default_empty_text),
        'external_urls': safe_text(game_item.get('external_urls', default_empty_text), default_empty_text),
    }


def get_page_items(results: List[Dict[str, Any]], page_index: int, page_size: int) -> List[Dict[str, Any]]:
    start_index = max(page_index, 0) * max(page_size, 1)
    end_index = start_index + max(page_size, 1)
    return results[start_index:end_index]
