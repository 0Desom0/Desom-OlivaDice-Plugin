# -*- encoding: utf-8 -*-
"""Lanota Portal 登录、数据读取和用户卡片渲染。"""

from __future__ import annotations

import base64
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import config
from . import china_grpc
from . import function
from . import utils

try:
    import requests

    REQUESTS_AVAILABLE = True
except Exception:
    requests = None
    REQUESTS_AVAILABLE = False


portal_lock = threading.RLock()
portal_token: dict[str, Any] = {}
china_portal_token: dict[str, Any] = {}
render_context = threading.local()
compare_cache_lock = threading.RLock()
compare_cache: dict[str, dict[str, Any]] = {}
compare_cache_ttl_seconds = 60
CHINA_FALLBACK_NOTICE = '现已切换备用 API，部分字段暂无法获取；如需查询完整信息请联系管理员更新 Token。'

REGION_ALIAS_MAP = {
    'global': 'global',
    'international': 'global',
    'intl': 'global',
    '国际服': 'global',
    'cn': 'china',
    'china': 'china',
    '中国': 'china',
    '中国服': 'china',
    '国服': 'china',
}


def _auth_file_path() -> str:
    return os.path.join(utils.get_plugin_data_dir(), 'portal_auth.json')


def _china_auth_file_path() -> str:
    return os.path.join(utils.get_plugin_data_dir(), 'portal_auth_china.json')


def _template_path(region: str = 'global', card_type: str = 'user') -> Path:
    normalized_region = normalize_region(region)
    if card_type == 'b30':
        file_name = config.lanota_portal_b30_template_file_name
    elif card_type == 'song':
        file_name = (
            config.lanota_portal_china_song_template_file_name
            if normalized_region == 'china'
            else config.lanota_portal_song_template_file_name
        )
    else:
        file_name = (
            config.lanota_portal_china_template_file_name
            if normalized_region == 'china'
            else config.lanota_portal_template_file_name
        )
    runtime_data_dir = Path(utils.get_plugin_data_dir()).resolve()
    candidates = [
        config.package_dir / 'Data' / file_name,
        config.package_dir / file_name,
        runtime_data_dir / file_name,
        runtime_data_dir / 'Data' / file_name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    checked_paths = '\n'.join(f'- {candidate.resolve()}' for candidate in candidates)
    raise FileNotFoundError(
        f'未找到 Lanota Portal {region_display_name(normalized_region)} HTML 模板，已检查：\n{checked_paths}'
    )


def _request_headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}


def _request_json(method: str, url: str, **kwargs) -> dict[str, Any]:
    if not REQUESTS_AVAILABLE or requests is None:
        raise RuntimeError('缺少 requests 依赖。')
    response = requests.request(
        method,
        url,
        timeout=(config.lanota_portal_connect_timeout_seconds, config.lanota_portal_timeout_seconds),
        **kwargs,
    )
    if response.status_code == 401:
        raise PermissionError('Portal 登录已失效。')
    if response.status_code == 404:
        raise LookupError('没有找到对应的 Lanota 玩家。')
    try:
        data = response.json()
    except ValueError as exception_object:
        if response.ok:
            raise RuntimeError('Portal 返回了无法解析的响应。') from exception_object
        response.raise_for_status()
        raise RuntimeError('Portal 请求失败。') from exception_object
    if not response.ok:
        error_data = data.get('error', {}) if isinstance(data, dict) else {}
        error_message = error_data.get('message', '') if isinstance(error_data, dict) else ''
        if error_message == 'INVALID_LOGIN_CREDENTIALS':
            raise PermissionError('Lanota Portal 登录账号或密码不正确。')
        if error_message:
            raise RuntimeError(f'Portal 请求失败：{error_message}')
        response.raise_for_status()
    if not isinstance(data, dict):
        raise RuntimeError('Portal 返回了无法识别的数据。')
    return data


def _save_token_data(data: dict[str, Any]) -> None:
    # Token 文件仅保存到运行期数据目录，不进入源码仓库。
    utils.save_json_file(_auth_file_path(), data)


def _save_china_token_data(data: dict[str, Any]) -> bool:
    # 国服 Token 与国际服 Firebase Token 分开保存，避免跨区误用。
    return utils.save_json_file(_china_auth_file_path(), data)


def _password_config() -> tuple[str, str]:
    global_config = utils.load_global_config()
    email = str(global_config.get('lanota_portal_email', '') or '').strip()
    password = str(global_config.get('lanota_portal_password', '') or '')
    if not email or not password:
        config_path = os.path.abspath(utils.get_global_config_path())
        raise RuntimeError(f'尚未配置 Lanota Portal 登录账号或密码，请填写：{config_path}')
    return email, password


def _firebase_api_key() -> str:
    global_config = utils.load_global_config()
    api_key = str(global_config.get('lanota_portal_firebase_api_key', '') or '').strip()
    if not api_key:
        raise RuntimeError('尚未配置 Lanota Portal Firebase Web API Key。')
    return api_key


def _login() -> dict[str, Any]:
    email, password = _password_config()
    url = (
        'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key='
        f'{_firebase_api_key()}'
    )
    data = _request_json(
        'POST',
        url,
        json={'email': email, 'password': password, 'returnSecureToken': True},
        headers={'Accept': 'application/json'},
    )
    token_data = {
        'id_token': data.get('idToken', ''),
        'refresh_token': data.get('refreshToken', ''),
        'expires_at': int(time.time()) + max(60, int(data.get('expiresIn', 3600)) - 120),
        'uid': data.get('localId', ''),
        'email': email,
    }
    if not token_data['id_token']:
        raise RuntimeError('Firebase 登录响应中没有 ID Token。')
    _save_token_data(token_data)
    return token_data


def _refresh_token(refresh_token: str, email: str) -> dict[str, Any]:
    url = f'https://securetoken.googleapis.com/v1/token?key={_firebase_api_key()}'
    if not REQUESTS_AVAILABLE or requests is None:
        raise RuntimeError('缺少 requests 依赖。')
    response = requests.post(
        url,
        data={'grant_type': 'refresh_token', 'refresh_token': refresh_token},
        headers={'Accept': 'application/json'},
        timeout=(config.lanota_portal_connect_timeout_seconds, config.lanota_portal_timeout_seconds),
    )
    try:
        response.raise_for_status()
        data = response.json()
    except Exception as exception_object:
        raise PermissionError('Lanota Portal 登录会话刷新失败。') from exception_object
    token_data = {
        'id_token': data.get('id_token', ''),
        'refresh_token': data.get('refresh_token', refresh_token),
        'expires_at': int(time.time()) + max(60, int(data.get('expires_in', 3600)) - 120),
        'uid': data.get('user_id', ''),
        'email': email,
    }
    if not token_data['id_token']:
        raise RuntimeError('Token 刷新响应中没有 ID Token。')
    _save_token_data(token_data)
    return token_data


def get_id_token() -> str:
    """取得可用的 Portal Bearer Token。"""
    global portal_token
    with portal_lock:
        email, _password = _password_config()
        cached_email = str(portal_token.get('email', '') or '').casefold()
        if (
            portal_token.get('id_token')
            and cached_email == email.casefold()
            and int(portal_token.get('expires_at', 0)) > int(time.time())
        ):
            return str(portal_token['id_token'])
        saved = utils.read_json_file(_auth_file_path(), {})
        saved_email = str(saved.get('email', '') or '').casefold() if isinstance(saved, dict) else ''
        if isinstance(saved, dict) and saved.get('id_token') and saved_email == email.casefold():
            portal_token = saved
            if int(saved.get('expires_at', 0)) > int(time.time()):
                return str(saved['id_token'])
            if saved.get('refresh_token'):
                try:
                    portal_token = _refresh_token(str(saved['refresh_token']), email)
                    return str(portal_token['id_token'])
                except Exception:
                    pass
        portal_token = _login()
        return str(portal_token['id_token'])


def normalize_region(region: Any) -> str:
    """把命令参数和旧绑定统一为 global/china。"""
    region_text = str(region or '').strip().casefold()
    return REGION_ALIAS_MAP.get(region_text, 'global')


def split_region_argument(argument: Any, greedy: bool = False) -> tuple[str | None, str]:
    """从命令参数开头提取区域别名；greedy=True 时不要求别名后存在空格。"""
    source = str(argument or '').strip()
    if not source:
        return None, ''
    parts = source.split(maxsplit=1)
    region = REGION_ALIAS_MAP.get(parts[0].casefold())
    if region is not None:
        return region, parts[1].strip() if len(parts) > 1 else ''
    if greedy:
        compare_source = source.casefold()
        for alias in sorted(REGION_ALIAS_MAP, key=len, reverse=True):
            if compare_source.startswith(alias):
                return REGION_ALIAS_MAP[alias], source[len(alias) :].lstrip()
    return None, source


def region_display_name(region: Any) -> str:
    return '国服' if normalize_region(region) == 'china' else '国际服'


def credential_error_hint(exception_object: Exception, region: Any) -> str:
    """Portal 凭据失效时返回面向查询用户的管理员处理提示。"""
    if isinstance(exception_object, ChinaApiUnavailableError):
        return '国服 Portal 与备用 API 均不可用，请联系管理员更新 Token。'
    error_text = format_error(exception_object).casefold()
    credential_markers = ('token', '登录', '账号', '密码', '授权', 'credential')
    if not isinstance(exception_object, PermissionError) and not any(
        marker in error_text for marker in credential_markers
    ):
        return ''
    if normalize_region(region) == 'china':
        return '国服 Portal Token 可能已过期，请联系管理员更新 Token。'
    return '国际服登录失败，请联系管理员检查登录账号或密码配置。'


def _jwt_exp(token: str) -> int:
    try:
        payload_text = str(token).split('.')[1]
        payload_text += '=' * (-len(payload_text) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_text.encode('ascii')).decode('utf-8'))
        return int(payload.get('exp', 0))
    except Exception:
        return 0


def get_china_token() -> str:
    """读取尚未过期的国服 chinaToken；国服没有刷新接口。"""
    global china_portal_token
    with portal_lock:
        # 手机上传的新文件优先于内存缓存，使 Token 无需重载插件即可热更新。
        candidates = [utils.read_json_file(_china_auth_file_path(), {}), china_portal_token]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            token = str(candidate.get('china_token', '') or '').strip()
            expires_at = int(candidate.get('expires_at', 0) or _jwt_exp(token))
            if token and (not expires_at or expires_at > int(time.time()) + 30):
                china_portal_token = dict(candidate)
                china_portal_token['expires_at'] = expires_at
                return token
        china_portal_token = {}
    raise PermissionError('国服 Portal Token 不可用，请联系管理员更新 Token。')


def api_get(
    path: str,
    params: dict[str, Any] | None = None,
    region: str = 'global',
) -> dict[str, Any]:
    """请求 Portal API，遇到过期 Token 时自动重新登录一次。"""
    normalized_region = normalize_region(region)
    if normalized_region == 'china':
        url = f'{config.lanota_portal_china_api_base_url}/{path.lstrip("/")}'
        request_token = get_china_token()
        try:
            return _request_json('GET', url, params=params, headers=_request_headers(request_token))
        except PermissionError as exception_object:
            global china_portal_token
            with portal_lock:
                china_portal_token = {}
                saved = utils.read_json_file(_china_auth_file_path(), {})
                saved_token = str(saved.get('china_token', '') or '') if isinstance(saved, dict) else ''
                # 只清除本次请求实际使用的旧 Token，不覆盖手机刚上传的新 Token。
                if saved_token == request_token:
                    _save_china_token_data({})
            raise PermissionError('国服 Portal Token 已失效，请联系管理员更新 Token。') from exception_object

    url = f'{config.lanota_portal_api_base_url}/{path.lstrip("/")}'
    try:
        return _request_json('GET', url, params=params, headers=_request_headers(get_id_token()))
    except PermissionError:
        global portal_token
        with portal_lock:
            portal_token = _login()
        return _request_json('GET', url, params=params, headers=_request_headers(str(portal_token['id_token'])))


def get_player(nano_id: str, region: str = 'global') -> dict[str, Any]:
    """读取公开玩家页所需的完整数据。"""
    clean_id = str(nano_id or '').strip()
    if not clean_id or len(clean_id) > 32 or not clean_id.isalnum():
        raise ValueError('好友码格式不正确。')
    normalized_region = normalize_region(region)
    try:
        data = api_get(f'player/{quote(clean_id, safe="")}', region=normalized_region)
    except Exception as portal_error:
        if normalized_region != 'china':
            raise
        data = _china_fallback_player(clean_id, portal_error)
    data['_portal_region'] = normalized_region
    return data


def get_me(region: str = 'global') -> dict[str, Any]:
    return api_get('me', region=region)


def _user_data_and_info(plugin_event) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    user_id = str(utils.get_sender_id_from_event(plugin_event) or '').strip()
    user_data = function.load_user_data(bot_hash)
    user_info = user_data.setdefault(user_id, {})
    return bot_hash, user_id, user_info, user_data


def _normalize_binds(user_info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    binds = user_info.get('lanota_binds', {})
    if not isinstance(binds, dict):
        binds = {}
    legacy_id = str(user_info.get('lanota_nano_id', '') or '').strip()
    legacy_region = normalize_region(user_info.get('lanota_region', 'global'))
    if legacy_id:
        legacy_entry = binds.setdefault(legacy_region, {})
        legacy_entry.setdefault('nano_id', legacy_id)
        legacy_entry.setdefault('username', user_info.get('lanota_username', ''))
    return binds


def get_bound_nano_id(plugin_event, region: str | None = None) -> str:
    _bot_hash, _user_id, user_info, _user_data = _user_data_and_info(plugin_event)
    binds = _normalize_binds(user_info)
    if region is not None:
        normalized_region = normalize_region(region)
        entry = binds.get(normalized_region, {})
        return str(entry.get('nano_id', '') or '').strip()
    for preferred_region in ('global', 'china'):
        entry = binds.get(preferred_region, {})
        nano_id = str(entry.get('nano_id', '') or '').strip()
        if nano_id:
            return nano_id
    return ''


def fallback_notice(data: Any) -> str:
    """返回备用 API 成功时需要附带的降级说明。"""
    if isinstance(data, dict) and data.get('_api_fallback'):
        return str(data.get('_api_fallback_notice') or CHINA_FALLBACK_NOTICE)
    return ''


class ChinaApiUnavailableError(RuntimeError):
    """国服 Portal 与备用 API 均失败。"""

    def __init__(self, portal_error: Exception, fallback_error: Exception):
        self.portal_error = portal_error
        self.fallback_error = fallback_error
        super().__init__(
            f'国服 Portal 与备用 API 均不可用：{format_error(portal_error)}；'
            f'备用 API：{format_error(fallback_error)}'
        )


def _china_fallback_player(nano_id: str, portal_error: Exception) -> dict[str, Any]:
    try:
        data = china_grpc.get_player(nano_id, timeout=config.lanota_portal_timeout_seconds)
    except Exception as fallback_error:
        raise ChinaApiUnavailableError(portal_error, fallback_error) from fallback_error
    data['_portal_error'] = format_error(portal_error)
    return data


def _china_fallback_compare(nano_id: str, portal_error: Exception) -> dict[str, Any]:
    try:
        data = china_grpc.get_compare(nano_id, timeout=config.lanota_portal_timeout_seconds)
    except Exception as fallback_error:
        raise ChinaApiUnavailableError(portal_error, fallback_error) from fallback_error
    data['_portal_error'] = format_error(portal_error)
    return data


def get_bound_region(plugin_event) -> str:
    if get_bound_nano_id(plugin_event, 'global'):
        return 'global'
    if get_bound_nano_id(plugin_event, 'china'):
        return 'china'
    return ''


def _save_user_cache(plugin_event, region: str, nano_id: str, data: dict[str, Any]) -> None:
    bot_hash, user_id, user_info, user_data = _user_data_and_info(plugin_event)
    cache = user_info.get('lanota_cache', {})
    if not isinstance(cache, dict):
        cache = {}
    cache[region] = {
        'nano_id': nano_id,
        'data': data,
        'saved_at': int(time.time()),
    }
    user_info['lanota_cache'] = cache
    if not function.save_user_data(user_data, bot_hash):
        utils.debug_log(None, '玩家资料缓存保存失败，请检查插件数据目录权限。')


def _load_user_cache(plugin_event, region: str, nano_id: str) -> dict[str, Any] | None:
    _bot_hash, _user_id, user_info, _user_data = _user_data_and_info(plugin_event)
    cache = user_info.get('lanota_cache', {})
    if not isinstance(cache, dict):
        return None
    entry = cache.get(region, {})
    if not isinstance(entry, dict):
        return None
    if str(entry.get('nano_id', '') or '').strip() != nano_id or not entry.get('data'):
        return None
    return entry


def bind_nano_id(plugin_event, nano_id: str, region: str = 'global') -> tuple[bool, str]:
    clean_id = str(nano_id or '').strip()
    normalized_region = normalize_region(region)
    try:
        data = get_player(clean_id, region=normalized_region)
        player = data.get('player', {})
        if not isinstance(player, dict) or not player.get('nanoId'):
            raise RuntimeError('Portal 返回的玩家资料不完整。')
        bot_hash, user_id, user_info, user_data = _user_data_and_info(plugin_event)
        if not user_id:
            raise RuntimeError('无法取得当前消息发送者 ID。')
        binds = _normalize_binds(user_info)
        binds[normalized_region] = {
            'nano_id': clean_id,
            'username': player.get('username', ''),
            'updated_at': int(time.time()),
        }
        user_info['lanota_binds'] = binds
        user_info['lanota_nano_id'] = clean_id
        user_info['lanota_region'] = normalized_region
        user_info['lanota_username'] = player.get('username', '')
        user_info['lanota_bind_updated_at'] = int(time.time())
        cache = user_info.get('lanota_cache', {})
        if isinstance(cache, dict):
            cache.pop(normalized_region, None)
            user_info['lanota_cache'] = cache
        if not function.save_user_data(user_data, bot_hash):
            raise OSError('好友码验证成功，但保存绑定失败，请检查插件数据目录权限。')
    except Exception as exception_object:
        return False, format_error(exception_object)
    username = player.get('username') or '未知玩家'
    return True, f'绑定成功：{username}（{region_display_name(normalized_region)}）'


def unbind_nano_id(plugin_event, region: str = 'global') -> tuple[bool, str]:
    normalized_region = normalize_region(region)
    bot_hash, user_id, user_info, user_data = _user_data_and_info(plugin_event)
    binds = _normalize_binds(user_info)
    if not str(binds.get(normalized_region, {}).get('nano_id', '') or '').strip():
        return False, f'尚未绑定 {region_display_name(normalized_region)}好友码。'
    binds.pop(normalized_region, None)
    user_info['lanota_binds'] = binds
    cache = user_info.get('lanota_cache', {})
    if isinstance(cache, dict):
        cache.pop(normalized_region, None)
        user_info['lanota_cache'] = cache
    remaining = [(region_name, entry) for region_name, entry in binds.items() if isinstance(entry, dict)]
    if remaining:
        fallback_region, fallback_entry = remaining[0]
        user_info['lanota_nano_id'] = fallback_entry.get('nano_id', '')
        user_info['lanota_region'] = fallback_region
        user_info['lanota_username'] = fallback_entry.get('username', '')
    else:
        user_info.pop('lanota_nano_id', None)
        user_info.pop('lanota_region', None)
        user_info.pop('lanota_username', None)
        user_info.pop('lanota_bind_updated_at', None)
    if not function.save_user_data(user_data, bot_hash):
        return False, '解除绑定失败，请检查插件数据目录权限。'
    return True, f'已解除 {region_display_name(normalized_region)}好友码绑定。'


def get_user_data(plugin_event, region: str | None = None) -> tuple[dict[str, Any], str]:
    selected_region = normalize_region(region) if region else get_bound_region(plugin_event)
    if not selected_region:
        raise RuntimeError('尚未绑定 Lanota 好友码，请先使用 .la bind <好友码>。')
    nano_id = get_bound_nano_id(plugin_event, selected_region)
    if not nano_id:
        raise RuntimeError('尚未绑定 Lanota 好友码，请先使用 .la bind <好友码>。')
    return get_player(nano_id, region=selected_region), nano_id


def get_user_data_cached(
    plugin_event,
    region: str | None = None,
) -> tuple[dict[str, Any], str, Exception | None]:
    """网络优先获取玩家资料，失败时回退到该区最后一次成功缓存。"""
    selected_region = normalize_region(region) if region else get_bound_region(plugin_event)
    if not selected_region:
        raise RuntimeError('尚未绑定 Lanota 好友码，请先使用 .la bind <好友码>。')
    nano_id = get_bound_nano_id(plugin_event, selected_region)
    if not nano_id:
        raise RuntimeError('尚未绑定 Lanota 好友码，请先使用 .la bind <好友码>。')
    try:
        data = get_player(nano_id, region=selected_region)
        _save_user_cache(plugin_event, selected_region, nano_id, data)
        return data, nano_id, None
    except Exception as exception_object:
        cache = _load_user_cache(plugin_event, selected_region, nano_id)
        if cache:
            return cache['data'], nano_id, exception_object
        raise


def get_compare_data_cached(
    plugin_event,
    region: str | None = None,
) -> tuple[dict[str, Any], str, Exception | None]:
    """读取绑定玩家逐谱面成绩；一分钟内复用缓存，失败时回退到旧缓存。"""
    selected_region = normalize_region(region) if region else get_bound_region(plugin_event)
    if not selected_region:
        raise RuntimeError('尚未绑定 Lanota 好友码，请先使用 .la bind <好友码>。')
    nano_id = get_bound_nano_id(plugin_event, selected_region)
    if not nano_id:
        region_name = region_display_name(selected_region)
        raise RuntimeError(f'尚未绑定 Lanota {region_name}好友码，请先使用 .la bind {"cn " if selected_region == "china" else ""}<好友码>。')

    cache_key = f'{selected_region}|{nano_id.casefold()}'
    now_time = time.time()
    with compare_cache_lock:
        cached_entry = compare_cache.get(cache_key, {})
        cached_data = cached_entry.get('data') if isinstance(cached_entry, dict) else None
        saved_at = float(cached_entry.get('saved_at', 0) or 0) if isinstance(cached_entry, dict) else 0
        if isinstance(cached_data, dict) and now_time - saved_at <= compare_cache_ttl_seconds:
            return cached_data, nano_id, None

    try:
        try:
            data = api_get('compare', params={'friendNanoId': nano_id}, region=selected_region)
        except Exception as portal_error:
            if selected_region != 'china':
                raise
            data = _china_fallback_compare(nano_id, portal_error)
        data['_portal_region'] = selected_region
        with compare_cache_lock:
            compare_cache[cache_key] = {'data': data, 'saved_at': now_time}
        return data, nano_id, None
    except Exception as exception_object:
        if isinstance(cached_data, dict):
            return cached_data, nano_id, exception_object
        raise


def _difficulty_index(value: Any) -> int | None:
    difficulty_text = str(value if value is not None else '').strip().casefold()
    difficulty_map = {
        '0': 0,
        'whisper': 0,
        '1': 1,
        'acoustic': 1,
        '2': 2,
        'ultra': 2,
        '3': 3,
        'master': 3,
    }
    return difficulty_map.get(difficulty_text)


def _clear_display_name(value: Any) -> Any:
    clear_name_map = {
        '0': 'No Play',
        '1': 'Failed',
        '2': 'Tuned',
        '3': 'Purified',
        '4': 'All Combo',
        '5': 'Perfect Purified',
    }
    return clear_name_map.get(str(value), value)


def find_compare_song_scores(
    compare_data: dict[str, Any],
    official_songid: Any,
    chart_set: str = 'current',
) -> list[dict[str, Any]]:
    """从 compare 响应提取目标玩家指定歌曲的已游玩成绩。"""
    target_song_id = str(official_songid or '').strip().casefold()
    if not target_song_id:
        return []
    song_rows = compare_data.get('songs', [])
    if not isinstance(song_rows, list):
        return []

    result_by_difficulty: dict[int, dict[str, Any]] = {}
    missing_value = '暂无法获取' if compare_data.get('_api_fallback') else None
    for raw_row in song_rows:
        if not isinstance(raw_row, dict):
            continue
        row_song_id = str(raw_row.get('songId', '') or '').strip().casefold()
        if row_song_id != target_song_id:
            continue
        difficulty_index = _difficulty_index(raw_row.get('difficulty'))
        if difficulty_index is None:
            continue
        score = raw_row.get('friendScore')
        clear = raw_row.get('friendClear')
        rank = raw_row.get('friendRank')
        if score is None and clear is None and rank is None:
            continue
        result_by_difficulty[difficulty_index] = {
            'chartSet': chart_set,
            'difficulty': difficulty_index,
            'score': score,
            'clear': _clear_display_name(clear),
            'rank': rank if rank is not None else missing_value,
            # compare 接口不公开目标玩家的单谱 Rating 和判定明细。
            'singleRating': None,
            'harmony': missing_value,
            'tune': missing_value,
            'fail': missing_value,
        }
    return [result_by_difficulty[index] for index in sorted(result_by_difficulty)]


def _escape_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')


def _registry_browser_paths() -> list[str]:
    if os.name != 'nt':
        return []
    try:
        import winreg
    except Exception:
        return []

    result = []
    executable_names = ['msedge.exe', 'chrome.exe', 'chromium.exe', 'brave.exe']
    root_keys = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]
    registry_views = [0, winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]
    for executable_name in executable_names:
        sub_key = rf'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable_name}'
        for root_key in root_keys:
            for registry_view in registry_views:
                try:
                    with winreg.OpenKey(root_key, sub_key, 0, winreg.KEY_READ | registry_view) as key:
                        executable_path, _value_type = winreg.QueryValueEx(key, None)
                        result.append(str(executable_path))
                except OSError:
                    continue
    return result


def _expand_browser_candidate(candidate: str) -> list[str]:
    clean_path = os.path.expandvars(os.path.expanduser(str(candidate or '').strip().strip('"')))
    if not clean_path:
        return []
    if os.path.isdir(clean_path):
        executable_names = ['msedge.exe', 'chrome.exe', 'chromium.exe', 'brave.exe', 'headless_shell.exe']
        return [os.path.join(clean_path, executable_name) for executable_name in executable_names]
    return [clean_path]


def _browser_candidates() -> list[str]:
    global_config = utils.load_global_config()
    configured = str(global_config.get('lanota_portal_browser_path', '') or '').strip()
    program_files_x86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
    program_files = os.environ.get('ProgramFiles', r'C:\Program Files')
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    raw_candidates = [
        configured,
        os.environ.get('LANOTA_BROWSER_PATH', ''),
        os.environ.get('EDGE_PATH', ''),
        os.environ.get('CHROME_PATH', ''),
    ]
    for executable_name in [
        'msedge',
        'msedge.exe',
        'microsoft-edge',
        'google-chrome',
        'chrome',
        'chrome.exe',
        'chromium',
        'chromium.exe',
        'chromium-browser',
        'brave-browser',
        'brave.exe',
    ]:
        raw_candidates.append(shutil.which(executable_name) or '')
    raw_candidates.extend(_registry_browser_paths())

    common_paths = [
        os.path.join(program_files_x86, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(program_files, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(local_app_data, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(program_files_x86, 'Microsoft', 'Edge Beta', 'Application', 'msedge.exe'),
        os.path.join(program_files_x86, 'Microsoft', 'Edge Dev', 'Application', 'msedge.exe'),
        os.path.join(local_app_data, 'Microsoft', 'Edge SxS', 'Application', 'msedge.exe'),
        os.path.join(program_files, 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(program_files_x86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(local_app_data, 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(program_files, 'Chromium', 'Application', 'chrome.exe'),
        os.path.join(local_app_data, 'Chromium', 'Application', 'chrome.exe'),
        os.path.join(program_files, 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe'),
        os.path.join(local_app_data, 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe'),
        '/usr/bin/microsoft-edge',
        '/usr/bin/google-chrome',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ]
    raw_candidates.extend(common_paths)

    glob_roots = [
        Path(program_files_x86) / 'Microsoft' / 'EdgeCore',
        Path(program_files) / 'Microsoft' / 'EdgeCore',
    ]
    for glob_root in glob_roots:
        try:
            raw_candidates.extend(str(path) for path in sorted(glob_root.glob('*/msedge.exe'), reverse=True))
        except Exception:
            pass

    playwright_roots = [
        os.environ.get('PLAYWRIGHT_BROWSERS_PATH', ''),
        os.path.join(local_app_data, 'ms-playwright'),
        str(Path.home() / '.cache' / 'ms-playwright'),
    ]
    playwright_patterns = [
        'chromium-*/chrome-win/chrome.exe',
        'chromium-*/chrome-win64/chrome.exe',
        'chromium_headless_shell-*/chrome-headless-shell-win64/headless_shell.exe',
        'chromium_headless_shell-*/chrome-headless-shell-win/headless_shell.exe',
        'chromium-*/chrome-linux/chrome',
        'chromium_headless_shell-*/chrome-headless-shell-linux64/headless_shell',
    ]
    for playwright_root in playwright_roots:
        if not playwright_root:
            continue
        root_path = Path(playwright_root)
        for pattern in playwright_patterns:
            try:
                raw_candidates.extend(str(path) for path in sorted(root_path.glob(pattern), reverse=True))
            except Exception:
                pass

    candidates = []
    seen = set()
    for raw_candidate in raw_candidates:
        for candidate in _expand_browser_candidate(raw_candidate):
            normalized = os.path.normcase(os.path.abspath(candidate))
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(candidate)
    return candidates


def _find_browser() -> str | None:
    candidates = _browser_candidates()
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def browser_status_text() -> str:
    browser = _find_browser()
    if browser:
        return f'已自动检测浏览器：{browser}'
    config_path = os.path.abspath(utils.get_global_config_path())
    return (
        '未检测到 Edge、Chrome、Chromium、Brave 或 Playwright Chromium。\n'
        f'可在 {config_path} 中填写 lanota_portal_browser_path，支持填写浏览器 exe 或 Application 目录。\n'
        f'当前 Python：{sys.executable}'
    )


def _set_render_error(message: str) -> None:
    render_context.error = str(message or '').strip()


def render_status_text() -> str:
    status_text = browser_status_text()
    error_text = str(getattr(render_context, 'error', '') or '').strip()
    if not error_text:
        return status_text
    return f'{status_text}\n浏览器错误：{error_text}'


def _device_scale_factor() -> float:
    global_config = utils.load_global_config()
    try:
        scale_factor = float(
            global_config.get(
                'lanota_portal_device_scale_factor',
                config.lanota_portal_device_scale_factor,
            )
        )
    except (TypeError, ValueError):
        scale_factor = float(config.lanota_portal_device_scale_factor)
    # 低于 2 时文字和素材会被 Chromium 以 1x 光栅化，国服卡片会明显发糊。
    return max(2.0, min(3.0, scale_factor))


def _b30_screenshot_height(data: dict[str, Any]) -> int:
    entries = data.get('entries', [])
    entry_count = len(entries) if isinstance(entries, list) else 0
    best_rows = math.ceil(min(entry_count, 30) / 3) if entry_count else 0
    overflow_rows = math.ceil(min(max(entry_count - 30, 0), 3) / 3)
    notice_text = str(data.get('notice', '') or '').strip()
    notice_lines = math.ceil(len(notice_text) / 48) if notice_text else 0
    notice_height = 24 + notice_lines * 32 if notice_lines else 0
    content_height = 510 + notice_height + best_rows * 180 + overflow_rows * 248
    maximum_height = int(config.lanota_portal_b30_screenshot_height)
    return max(600, min(maximum_height, content_height))


def _crop_song_card(path: Path, scale_factor: float) -> None:
    """按页面实际内容裁掉歌曲卡片底部空白，并保留稳定外边距。"""
    try:
        from PIL import Image, ImageChops

        with Image.open(path) as source_image:
            image = source_image.convert('RGB')
        background = Image.new('RGB', image.size, image.getpixel((0, image.height - 1)))
        difference = ImageChops.difference(image, background).convert('L')
        visible = difference.point(lambda value: 255 if value > 3 else 0)
        bounding_box = visible.getbbox()
        if not bounding_box:
            return
        bottom_padding = max(48, int(round(52 * scale_factor)))
        target_bottom = min(image.height, bounding_box[3] + bottom_padding)
        if target_bottom < image.height - 4:
            image.crop((0, 0, image.width, target_bottom)).save(path)
    except Exception as exception_object:
        utils.debug_log(None, f'歌曲卡片自适应裁切失败：{type(exception_object).__name__}: {exception_object}')


def _compress_rendered_card(path: Path) -> Path:
    """保持截图像素尺寸不变，以高质量 WebP 缩小 Portal 卡片体积。"""
    output_path = path.with_suffix('.webp')
    try:
        from PIL import Image

        with Image.open(path) as source_image:
            source_image.convert('RGB').save(
                output_path,
                format='WEBP',
                quality=95,
                method=6,
            )
        if output_path.stat().st_size >= path.stat().st_size:
            output_path.unlink(missing_ok=True)
            return path
        path.unlink(missing_ok=True)
        return output_path
    except Exception as exception_object:
        output_path.unlink(missing_ok=True)
        utils.debug_log(None, f'Portal 图片压缩失败：{type(exception_object).__name__}: {exception_object}')
        return path


def _template_html(data: dict[str, Any], card_type: str = 'user') -> str:
    normalized_region = normalize_region(data.get('_portal_region', 'global'))
    template = _template_path(normalized_region, card_type).read_text(encoding='utf-8')
    placeholder = '/*__LANOTA_DATA__*/'
    if placeholder not in template:
        raise RuntimeError('Lanota Portal HTML 模板缺少数据占位符。')
    template_data = dict(data)
    template_data.pop('_portal_region', None)
    asset_base_url = (
        config.lanota_portal_china_asset_base_url
        if normalized_region == 'china'
        else config.lanota_portal_asset_base_url
    )
    # 兼容部署目录中遗留的 1.3.x 模板：把其中固定的国际服资源域名按当前区域替换。
    template = template.replace(config.lanota_portal_asset_base_url, asset_base_url)
    template_data['portalAssetBaseUrl'] = asset_base_url
    template_data['portalSourceLabel'] = (
        'GMZON LANOTA PORTAL' if normalized_region == 'china' else 'NOXYGAMES LANOTA PORTAL'
    )
    template_data['portalRegionName'] = region_display_name(normalized_region)
    if card_type == 'b30':
        utils.sync_b30_assets()
        template_data['b30AssetBaseUrl'] = Path(utils.get_b30_asset_dir()).resolve().as_uri()
    for portal_font_file_name in config.portal_font_file_name_list:
        runtime_font_path = Path(utils.get_portal_font_path(portal_font_file_name)).resolve()
        font_path = (
            runtime_font_path
            if runtime_font_path.is_file()
            else config.asset_data_dir / portal_font_file_name
        )
        template = template.replace(f'./{portal_font_file_name}', font_path.resolve().as_uri())
    if card_type in {'user', 'b30'}:
        player = dict(data.get('player', {}))
        player.pop('nanoId', None)
        template_data['player'] = player
    return template.replace(placeholder, f'window.__LANOTA_DATA__ = {_escape_json(template_data)};', 1)


def _render_card(data: dict[str, Any], card_type: str, output_prefix: str) -> str | None:
    """使用固定 HTML 模板截图，用户卡片与歌曲卡片共用浏览器渲染流程。"""
    _set_render_error('')
    browser = _find_browser()
    if not browser:
        _set_render_error('未找到可用的 Chromium 浏览器。')
        return None
    function.cleanup_image_cache()
    output_dir = Path(utils.get_generate_image_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'{output_prefix}_{uuid.uuid4().hex[:12]}.png'
    html_path = Path(tempfile.gettempdir()) / f'lanota_portal_{uuid.uuid4().hex[:12]}.html'
    browser_data_dir = Path(tempfile.gettempdir()) / f'lanota_portal_browser_{uuid.uuid4().hex[:12]}'
    try:
        html_path.write_text(_template_html(data, card_type), encoding='utf-8')
        browser_data_dir.mkdir(parents=True, exist_ok=True)
        scale_factor = _device_scale_factor()
        if card_type == 'song':
            screenshot_height = config.lanota_portal_song_screenshot_height
        elif card_type == 'b30':
            screenshot_height = _b30_screenshot_height(data)
        else:
            screenshot_height = config.lanota_portal_screenshot_height
        screenshot_width = (
            config.lanota_portal_b30_screenshot_width
            if card_type == 'b30'
            else config.lanota_portal_screenshot_width
        )
        last_error = ''
        for headless_mode in ['--headless=new', '--headless']:
            output_path.unlink(missing_ok=True)
            command = [
                browser,
                headless_mode,
                '--disable-gpu',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--high-dpi-support=1',
                f'--force-device-scale-factor={scale_factor:g}',
                '--hide-scrollbars',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-extensions',
                '--disable-background-networking',
                '--allow-file-access-from-files',
                '--run-all-compositor-stages-before-draw',
                '--virtual-time-budget=8000',
                f'--window-size={screenshot_width},{screenshot_height}',
                f'--user-data-dir={browser_data_dir}',
                f'--screenshot={output_path}',
                html_path.resolve().as_uri(),
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    errors='replace',
                    timeout=45,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                last_error = f'{headless_mode} 启动超过 45 秒，已终止。'
                continue
            except Exception as exception_object:
                last_error = f'{headless_mode} 启动异常：{type(exception_object).__name__}: {exception_object}'
                continue
            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size >= 1000:
                if card_type == 'song':
                    _crop_song_card(output_path, scale_factor)
                return str(_compress_rendered_card(output_path))
            detail = (result.stderr or result.stdout or '').strip().replace('\r', ' ').replace('\n', ' ')
            if not detail:
                detail = '浏览器未生成有效 PNG 文件。'
            last_error = f'{headless_mode} 退出码 {result.returncode}：{detail[-800:]}'
        _set_render_error(last_error)
        utils.debug_log(None, f'Portal 浏览器截图失败：{last_error}')
        return None
    except Exception as exception_object:
        error_text = f'{type(exception_object).__name__}: {exception_object}'
        _set_render_error(error_text)
        utils.debug_log(None, f'Portal 卡片渲染失败：{error_text}')
        return None
    finally:
        try:
            html_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            shutil.rmtree(browser_data_dir, ignore_errors=True)
        except Exception:
            pass


def render_player_card(data: dict[str, Any]) -> str | None:
    """使用 Portal 用户 HTML 模板截图。"""
    return _render_card(data, 'user', 'lanota_portal_user')


def render_song_card(data: dict[str, Any]) -> str | None:
    """使用歌曲/查分 HTML 模板截图。"""
    return _render_card(data, 'song', 'lanota_portal_song')


def render_b30_card(data: dict[str, Any]) -> str | None:
    """使用 B30 HTML 模板截图。"""
    return _render_card(data, 'b30', 'lanota_portal_b30')


def build_fallback_text(data: dict[str, Any]) -> str:
    player = data.get('player', {})
    stats = data.get('stats', {})
    clear_counts = stats.get('clearCounts', {})
    rank_counts = stats.get('rankCounts', {})
    region_name = region_display_name(data.get('_portal_region', 'global'))
    text = (
        f'玩家：{player.get("username") or "未知玩家"}（{region_name}）\n'
        f'Rating：{player.get("rating", "未知")}\n'
        f'总分：{player.get("totalScore", "未知")}\n'
        f'已游玩谱面：{stats.get("totalSongsPlayed", 0)}\n'
        f'通关：Tuned {clear_counts.get("2", 0)} / Purified {clear_counts.get("3", 0)} / '
        f'All Combo {clear_counts.get("4", 0)} / Perfect Purified {clear_counts.get("5", 0)}\n'
        f'Rank：L {rank_counts.get("L", 0)} / S {rank_counts.get("S", 0)} / '
        f'A {rank_counts.get("A", 0)} / B {rank_counts.get("B", 0)} / '
        f'C {rank_counts.get("C", 0)} / D {rank_counts.get("D", 0)}'
    )
    notice = fallback_notice(data)
    return f'{text}\n{notice}' if notice else text


def format_error(exception_object: Exception) -> str:
    message = str(exception_object).strip()
    return message or f'Portal 请求失败：{type(exception_object).__name__}'
