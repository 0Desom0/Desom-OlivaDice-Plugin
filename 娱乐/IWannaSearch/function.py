# -*- encoding: utf-8 -*-
"""I Wanna Archive API 访问与结果整理。"""

import json
import math
import os
import re
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from . import config


function_module_note = 'I Wanna Archive API 查询模块。'
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


def build_search_url(base_url: str, query_param: str, query_value: str) -> str:
    encoded_query = urllib.parse.urlencode({query_param: query_value})
    return f'{normalize_base_url(base_url)}/api/search?{encoded_query}'


def build_random_url(base_url: str, count: int = 1, tag: str = '') -> str:
    random_url = f'{normalize_base_url(base_url)}/api/random?count={max(1, int(count))}'
    safe_tag = safe_text(tag).strip()
    if safe_tag:
        random_url = f'{random_url}&tag={urllib.parse.quote(safe_tag, safe="")}'
    return random_url


def fetch_json(search_url: str, timeout_seconds: int) -> Dict[str, Any]:
    request = urllib.request.Request(search_url, headers={'User-Agent': 'IWannaSearch/1.0'})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response_object:
        charset = response_object.headers.get_content_charset() or 'utf-8'
        response_text = response_object.read().decode(charset, errors='replace')
    parsed_data = json.loads(response_text)
    if not isinstance(parsed_data, dict):
        raise ValueError('API 返回值不是 JSON 对象')
    return parsed_data


def request_api_url(api_url: str, timeout_seconds: int) -> Dict[str, Any]:
    try:
        api_data = fetch_json(api_url, timeout_seconds)
    except urllib.error.HTTPError as exception_object:
        return {'ok': False, 'error': f'HTTP {exception_object.code}', 'results': [], 'count': 0}
    except urllib.error.URLError as exception_object:
        return {'ok': False, 'error': safe_text(exception_object.reason, '网络连接失败'), 'results': [], 'count': 0}
    except TimeoutError:
        return {'ok': False, 'error': '请求超时', 'results': [], 'count': 0}
    except Exception as exception_object:
        return {'ok': False, 'error': f'{type(exception_object).__name__}: {exception_object}', 'results': [], 'count': 0}

    if not api_data.get('success', False):
        return {'ok': False, 'error': 'API 返回 success=false', 'results': [], 'count': 0}

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


def request_search(query_param: str, query_value: str, base_url: str, timeout_seconds: int) -> Dict[str, Any]:
    search_url = build_search_url(base_url, query_param, query_value)
    return request_api_url(search_url, timeout_seconds)


def search_by_id(game_id: str, base_url: str, timeout_seconds: int) -> Dict[str, Any]:
    return request_search('id', safe_text(game_id).strip(), base_url, timeout_seconds)


def search_by_name(game_name: str, base_url: str, timeout_seconds: int) -> Dict[str, Any]:
    return request_search('q', safe_text(game_name).strip(), base_url, timeout_seconds)


def random_games(count: int, tag: str, base_url: str, timeout_seconds: int) -> Dict[str, Any]:
    return request_api_url(build_random_url(base_url, count=count, tag=tag), timeout_seconds)


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
    return {
        'id': safe_text(item.get('id', default_empty_text), default_empty_text),
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
    }


def format_score_value(value: Any) -> str:
    if value_is_empty(value):
        return default_empty_text
    try:
        return f'{float(value):.1f}/10'
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
    return {
        'index': safe_text(index),
        'id': safe_text(game_item.get('id', default_empty_text), default_empty_text),
        'title': safe_text(game_item.get('title', default_empty_text), default_empty_text),
        'creator': safe_text(game_item.get('creator', default_empty_text), default_empty_text),
        'release_date': format_release_date(game_item.get('release_date')),
        'rating': format_score_value(game_item.get('rating')),
        'difficulty': format_score_value(game_item.get('difficulty')),
        'rating_count': format_rating_count(game_item.get('rating_count')),
        'tags': tag_text,
        'engine': format_engine_value(game_item.get('engine')),
        'url': safe_text(game_item.get('url', default_empty_text), default_empty_text),
        'file_size': format_file_size(game_item.get('file_size')),
    }


def get_page_items(results: List[Dict[str, Any]], page_index: int, page_size: int) -> List[Dict[str, Any]]:
    start_index = max(page_index, 0) * max(page_size, 1)
    end_index = start_index + max(page_size, 1)
    return results[start_index:end_index]
