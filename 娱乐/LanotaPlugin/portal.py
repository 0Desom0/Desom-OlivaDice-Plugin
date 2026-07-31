# -*- encoding: utf-8 -*-
"""Lanota Portal 登录、数据读取和用户卡片渲染。"""

from __future__ import annotations

import base64
import json
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
from urllib.parse import quote, urlencode

from . import config
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


def _auth_file_path() -> str:
    return os.path.join(utils.get_plugin_data_dir(), 'portal_auth.json')


def _china_auth_file_path() -> str:
    return os.path.join(utils.get_plugin_data_dir(), 'portal_auth_china.json')


def _template_path(region: str = 'global') -> Path:
    normalized_region = normalize_region(region)
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
    if region_text in ['cn', 'china', '中国', '中国服', '国服']:
        return 'china'
    return 'global'


def region_display_name(region: Any) -> str:
    return '国服' if normalize_region(region) == 'china' else '国际服'


def _jwt_exp(token: str) -> int:
    try:
        payload_text = str(token).split('.')[1]
        payload_text += '=' * (-len(payload_text) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_text.encode('ascii')).decode('utf-8'))
        return int(payload.get('exp', 0))
    except Exception:
        return 0


def create_china_login_session() -> dict[str, str]:
    """创建国服 App 授权会话，并返回可供 Lanota 扫描的深链。"""
    data = _request_json(
        'POST',
        f'{config.lanota_portal_china_api_base_url}/auth/init-app-login',
        headers={'Accept': 'application/json'},
    )
    session_id = str(data.get('session_id', '') or '').strip()
    if not session_id:
        raise RuntimeError('国服 Portal 没有返回登录会话 ID。')
    callback_query = urlencode({'session_id': session_id, 'flow': 'qr'})
    callback_url = f'{config.lanota_portal_china_asset_base_url}/auth/callback?{callback_query}'
    deep_link_query = urlencode({'session_id': session_id, 'callback': callback_url})
    deep_link = f'{config.lanota_portal_china_app_scheme}://portal-auth?{deep_link_query}'
    return {
        'session_id': session_id,
        'callback_url': callback_url,
        'deep_link': deep_link,
    }


def _exchange_china_login(session_id: str, code: str) -> dict[str, Any]:
    data = _request_json(
        'POST',
        f'{config.lanota_portal_china_api_base_url}/auth/exchange',
        json={'code': code, 'session_id': session_id},
        headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
    )
    token = str(data.get('chinaToken', '') or '').strip()
    if not token:
        raise RuntimeError('国服 Portal 授权响应中没有 chinaToken。')
    expires_at = _jwt_exp(token)
    if expires_at and expires_at <= int(time.time()):
        raise PermissionError('国服 Portal 返回了已经过期的 Token。')
    token_data = {
        'china_token': token,
        'uid': str(data.get('uid', '') or ''),
        'expires_at': expires_at,
        'saved_at': int(time.time()),
    }
    global china_portal_token
    with portal_lock:
        china_portal_token = token_data
        if not _save_china_token_data(token_data):
            china_portal_token = {}
            raise OSError('国服授权成功，但保存 Token 失败，请检查插件数据目录权限。')
    return token_data


def poll_china_login(session_id: str) -> dict[str, Any]:
    """轮询国服 App 授权结果；此函数应在后台线程中调用。"""
    clean_session_id = str(session_id or '').strip()
    if not clean_session_id:
        raise ValueError('国服登录会话 ID 为空。')
    deadline = time.monotonic() + config.lanota_portal_china_login_timeout_seconds
    while time.monotonic() < deadline:
        data = _request_json(
            'GET',
            f'{config.lanota_portal_china_api_base_url}/auth/poll',
            params={'session_id': clean_session_id},
            headers={'Accept': 'application/json'},
        )
        status = str(data.get('status', '') or '').strip().casefold()
        code = str(data.get('code', '') or '').strip()
        if status == 'ready' and code:
            return _exchange_china_login(clean_session_id, code)
        if status in ['expired', 'cancelled', 'canceled', 'failed', 'error']:
            raise PermissionError(f'国服 Portal 授权未完成：{status}')
        time.sleep(config.lanota_portal_china_poll_interval_seconds)
    raise TimeoutError('国服 Portal 授权已超时，请重新执行 .la china login。')


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
    raise PermissionError('国服 Portal 尚未登录或登录已过期，请管理员使用 .la china login 扫码授权。')


def china_auth_status_text() -> str:
    saved = utils.read_json_file(_china_auth_file_path(), {})
    if not isinstance(saved, dict):
        return '国服 Portal：未登录'
    token = str(saved.get('china_token', '') or '').strip()
    expires_at = int(saved.get('expires_at', 0) or _jwt_exp(token))
    if not token:
        return '国服 Portal：未登录'
    if expires_at and expires_at <= int(time.time()):
        return '国服 Portal：登录已过期，需要重新扫码授权'
    if expires_at:
        remaining_minutes = max(0, (expires_at - int(time.time())) // 60)
        return f'国服 Portal：已登录，Token 约 {remaining_minutes} 分钟后过期'
    return '国服 Portal：已登录，Token 未提供过期时间'


def render_china_login_qr(deep_link: str) -> str | None:
    """生成本地二维码；缺少 qrcode/Pillow 时由命令层退化为发送深链。"""
    try:
        import qrcode
    except Exception:
        return None
    try:
        function.cleanup_image_cache()
        output_dir = Path(utils.get_generate_image_dir()).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f'lanota_china_login_{uuid.uuid4().hex[:12]}.png'
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
        qr.add_data(str(deep_link))
        qr.make(fit=True)
        qr.make_image(fill_color='black', back_color='white').save(output_path)
        return str(output_path)
    except Exception as exception_object:
        utils.debug_log(None, f'国服登录二维码生成失败：{type(exception_object).__name__}: {exception_object}')
        return None


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
            raise PermissionError(
                '国服 Portal 登录已失效，请管理员使用 .la china login 重新扫码授权。'
            ) from exception_object

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
    data = api_get(f'player/{quote(clean_id, safe="")}', region=normalized_region)
    data['_portal_region'] = normalized_region
    return data


def get_me(region: str = 'global') -> dict[str, Any]:
    return api_get('me', region=region)


def get_bound_nano_id(plugin_event) -> str:
    bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    user_id = utils.get_sender_id_from_event(plugin_event)
    user_data = function.load_user_data(bot_hash)
    user_info = user_data.get(str(user_id), {})
    return str(user_info.get('lanota_nano_id', '') or '').strip()


def get_bound_region(plugin_event) -> str:
    bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    user_id = utils.get_sender_id_from_event(plugin_event)
    user_data = function.load_user_data(bot_hash)
    user_info = user_data.get(str(user_id), {})
    return normalize_region(user_info.get('lanota_region', 'global'))


def bind_nano_id(plugin_event, nano_id: str, region: str = 'global') -> tuple[bool, str]:
    clean_id = str(nano_id or '').strip()
    normalized_region = normalize_region(region)
    try:
        data = get_player(clean_id, region=normalized_region)
        player = data.get('player', {})
        if not isinstance(player, dict) or not player.get('nanoId'):
            raise RuntimeError('Portal 返回的玩家资料不完整。')
        bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
        user_id = utils.get_sender_id_from_event(plugin_event)
        if not user_id:
            raise RuntimeError('无法取得当前消息发送者 ID。')
        user_data = function.load_user_data(bot_hash)
        user_info = user_data.setdefault(str(user_id), {})
        user_info['lanota_nano_id'] = clean_id
        user_info['lanota_region'] = normalized_region
        user_info['lanota_username'] = player.get('username', '')
        user_info['lanota_bind_updated_at'] = int(time.time())
        if not function.save_user_data(user_data, bot_hash):
            raise OSError('好友码验证成功，但保存绑定失败，请检查插件数据目录权限。')
    except Exception as exception_object:
        return False, format_error(exception_object)
    username = player.get('username') or '未知玩家'
    return True, f'绑定成功：{username}（{region_display_name(normalized_region)}）'


def get_user_data(plugin_event) -> tuple[dict[str, Any], str]:
    nano_id = get_bound_nano_id(plugin_event)
    if not nano_id:
        raise RuntimeError('尚未绑定 Lanota 好友码，请先使用 .la bind <好友码>。')
    return get_player(nano_id, region=get_bound_region(plugin_event)), nano_id


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
    return max(1.0, min(3.0, scale_factor))


def _template_html(data: dict[str, Any]) -> str:
    normalized_region = normalize_region(data.get('_portal_region', 'global'))
    template = _template_path(normalized_region).read_text(encoding='utf-8')
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
    player = dict(data.get('player', {}))
    player.pop('nanoId', None)
    template_data['player'] = player
    return template.replace(placeholder, f'window.__LANOTA_DATA__ = {_escape_json(template_data)};', 1)


def render_player_card(data: dict[str, Any]) -> str | None:
    """使用固定 HTML 模板截图；模板只读取一次，数据按请求填充。"""
    _set_render_error('')
    browser = _find_browser()
    if not browser:
        _set_render_error('未找到可用的 Chromium 浏览器。')
        return None
    function.cleanup_image_cache()
    output_dir = Path(utils.get_generate_image_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'lanota_portal_{uuid.uuid4().hex[:12]}.png'
    html_path = Path(tempfile.gettempdir()) / f'lanota_portal_{uuid.uuid4().hex[:12]}.html'
    browser_data_dir = Path(tempfile.gettempdir()) / f'lanota_portal_browser_{uuid.uuid4().hex[:12]}'
    try:
        html_path.write_text(_template_html(data), encoding='utf-8')
        browser_data_dir.mkdir(parents=True, exist_ok=True)
        scale_factor = _device_scale_factor()
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
                f'--window-size={config.lanota_portal_screenshot_width},{config.lanota_portal_screenshot_height}',
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
                return str(output_path)
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


def build_fallback_text(data: dict[str, Any]) -> str:
    player = data.get('player', {})
    stats = data.get('stats', {})
    clear_counts = stats.get('clearCounts', {})
    rank_counts = stats.get('rankCounts', {})
    region_name = region_display_name(data.get('_portal_region', 'global'))
    return (
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


def format_error(exception_object: Exception) -> str:
    message = str(exception_object).strip()
    return message or f'Portal 请求失败：{type(exception_object).__name__}'
