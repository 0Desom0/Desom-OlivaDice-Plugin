# -*- encoding: utf-8 -*-
"""I Wanna Archive API 访问与结果整理。"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List


function_module_note = 'I Wanna Archive API 查询模块。'
default_empty_text = '暂无'


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


def build_game_template_value(game_item: Dict[str, Any], index: int = 0) -> Dict[str, str]:
    tag_text = ', '.join(game_item.get('tags', [])) or default_empty_text
    return {
        'index': safe_text(index),
        'id': safe_text(game_item.get('id', default_empty_text), default_empty_text),
        'title': safe_text(game_item.get('title', default_empty_text), default_empty_text),
        'creator': safe_text(game_item.get('creator', default_empty_text), default_empty_text),
        'rating': format_score_value(game_item.get('rating')),
        'difficulty': format_score_value(game_item.get('difficulty')),
        'rating_count': format_rating_count(game_item.get('rating_count')),
        'tags': tag_text,
        'url': safe_text(game_item.get('url', default_empty_text), default_empty_text),
        'file_size': format_file_size(game_item.get('file_size')),
    }


def get_page_items(results: List[Dict[str, Any]], page_index: int, page_size: int) -> List[Dict[str, Any]]:
    start_index = max(page_index, 0) * max(page_size, 1)
    end_index = start_index + max(page_size, 1)
    return results[start_index:end_index]
