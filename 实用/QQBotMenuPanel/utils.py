# -*- encoding: utf-8 -*-
"""日志、配置读写与 Bot 辅助方法。"""

import base64
import copy
import json
import os
import tempfile
import threading
import time
import traceback
from collections import OrderedDict
from io import BytesIO
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests

from . import config
from . import function
from . import message_custom

has_oliva_dice_core = False
try:
    import OlivaDiceCore

    has_oliva_dice_core = True
except Exception:
    has_oliva_dice_core = False

file_lock = threading.RLock()
runtime_proc = None

# 头像：先拉 QQ 在线头像并写入该 bot 目录的 avatar.png，失败再用该目录里的 avatar 图片。
# 点刷新可跳过内存缓存重拉；在线和本地都没有时，前端用原来的蓝色渐变圈。
AVATAR_STEM = 'avatar'
AVATAR_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')
MAX_AVATAR_BYTES = 4 * 1024 * 1024
_avatar_cache = OrderedDict()
_avatar_lock = threading.Lock()


def safe_str(value: Any) -> str:
    return function.safe_str(value)


def deep_copy_default(default_value: Any) -> Any:
    return copy.deepcopy(default_value)


def merge_dict_with_default(source_dict: Any, default_dict: Dict[str, Any]) -> Dict[str, Any]:
    merged_dict = deep_copy_default(default_dict)
    if isinstance(source_dict, dict):
        for key, value in source_dict.items():
            merged_dict[key] = value
    return merged_dict


def ensure_folder(folder_path: str) -> str:
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def log_message(Proc, log_level: int, level_name: str, message_text: str) -> None:
    full_message = f'[{config.plugin_name}][{level_name}] {safe_str(message_text)}'
    if Proc is not None and hasattr(Proc, 'log'):
        try:
            Proc.log(log_level, full_message, [])
            return
        except Exception:
            pass
    print(full_message)


def debug_log(Proc, message_text: str, plugin_event=None, bot_hash: Optional[str] = None) -> None:
    global_config = load_global_config()
    if global_config.get('global_debug_mode_switch', False):
        log_message(Proc, 0, 'DEBUG', message_text)


def info_log(Proc, message_text: str) -> None:
    log_message(Proc, 2, 'INFO', message_text)


def error_log(Proc, message_text: str) -> None:
    log_message(Proc, 4, 'ERROR', message_text)


def set_runtime_proc(Proc) -> None:
    global runtime_proc
    if Proc is not None:
        runtime_proc = Proc


def get_runtime_proc():
    return runtime_proc


def initialize_plugin(Proc) -> None:
    try:
        ensure_folder(config.plugin_data_dir)
        load_global_config()
        info_log(Proc, 'QQBotMenuPanel 初始化完成。')
    except Exception as exception_object:
        error_log(Proc, f'初始化失败：{type(exception_object).__name__}: {exception_object}')


def read_json_file(file_path: str, default_value: Any) -> Any:
    with file_lock:
        if not os.path.isfile(file_path):
            return deep_copy_default(default_value)
        try:
            with open(file_path, 'r', encoding='utf-8') as file_obj:
                loaded_value = json.load(file_obj)
            if loaded_value is None:
                return deep_copy_default(default_value)
            return loaded_value
        except Exception:
            return deep_copy_default(default_value)


def write_json_file(file_path: str, value: Any) -> bool:
    with file_lock:
        try:
            folder_path = os.path.dirname(file_path)
            if folder_path:
                ensure_folder(folder_path)
            with open(file_path, 'w', encoding='utf-8') as file_obj:
                json.dump(value, file_obj, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False


def get_global_config_path() -> str:
    ensure_folder(config.plugin_data_dir)
    return os.path.join(config.plugin_data_dir, config.global_config_file_name)


def load_global_config() -> dict:
    loaded_config = read_json_file(get_global_config_path(), config.default_global_config)
    merged_config = merge_dict_with_default(loaded_config, config.default_global_config)
    return merged_config


def save_global_config(global_config: dict) -> bool:
    merged_config = merge_dict_with_default(global_config, config.default_global_config)
    return write_json_file(get_global_config_path(), merged_config)


def get_config_bot_hash(bot_hash: Any) -> str:
    return safe_str(bot_hash).strip() or 'default'


def get_config_bot_root_dir(bot_hash: Any) -> str:
    return ensure_folder(os.path.join(config.plugin_data_dir, get_config_bot_hash(bot_hash)))


def get_bot_config_path(bot_hash: Any) -> str:
    return os.path.join(get_config_bot_root_dir(bot_hash), config.bot_config_file_name)


def normalize_bot_config(raw_config: Any) -> dict:
    raw_selected_present = isinstance(raw_config, dict) and 'chat_selected_scopes' in raw_config
    merged_config = merge_dict_with_default(raw_config, config.default_bot_config)
    merged_config['menu_draft'] = function.normalize_menu_draft(merged_config.get('menu_draft', {}))
    panel_drafts = merged_config.get('panel_drafts', {})
    if not isinstance(panel_drafts, dict):
        panel_drafts = {}
    normalized_panel_drafts = {}
    for scope in config.SCOPE_LIST:
        records = panel_drafts.get(scope, [])
        if not isinstance(records, list):
            records = []
        normalized_panel_drafts[scope] = [
            function.normalize_panel_record(record, fallback_scope=scope)
            for record in records
        ]
    merged_config['panel_drafts'] = normalized_panel_drafts
    merged_config['unified_panel_mode'] = bool(merged_config.get('unified_panel_mode', False))
    current_scope = merged_config.get('chat_current_scope', config.SCOPE_C2C)
    if current_scope not in config.SCOPE_LIST:
        current_scope = config.SCOPE_C2C
    if not raw_selected_present and merged_config.get('unified_panel_mode'):
        selected = list(config.SCOPE_LIST)
    else:
        selected = function.normalize_scope_list(
            merged_config.get('chat_selected_scopes'),
            current_scope,
        )
    if current_scope not in selected:
        current_scope = selected[0]
    merged_config['chat_current_scope'] = current_scope
    merged_config['chat_selected_scopes'] = selected
    return merged_config


def load_bot_config(bot_hash: Any) -> dict:
    loaded_config = read_json_file(get_bot_config_path(bot_hash), config.default_bot_config)
    return normalize_bot_config(loaded_config)


def save_bot_config(bot_hash: Any, bot_config: dict) -> bool:
    return write_json_file(get_bot_config_path(bot_hash), normalize_bot_config(bot_config))


def get_bot_hash_from_event(plugin_event) -> str:
    try:
        return get_config_bot_hash(plugin_event.bot_info.hash)
    except Exception:
        return 'default'


def get_raw_bot_hash_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.bot_info.hash)
    except Exception:
        return ''


def get_bot_id_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.bot_info.id)
    except Exception:
        return ''


def get_platform_sdk(bot_info) -> str:
    try:
        platform_info = getattr(bot_info, 'platform', {}) or {}
        if isinstance(platform_info, dict):
            return safe_str(platform_info.get('sdk', ''))
        return safe_str(getattr(platform_info, 'sdk', ''))
    except Exception:
        return ''


def is_qqguildv2_bot(bot_info) -> bool:
    return get_platform_sdk(bot_info) == config.qqguildv2_sdk


def is_qqguildv2_event(plugin_event) -> bool:
    try:
        return safe_str(plugin_event.platform.get('sdk', '')) == config.qqguildv2_sdk
    except Exception:
        return False


def filter_qqguildv2_bots(bot_info_dict) -> dict:
    result = {}
    if not isinstance(bot_info_dict, dict):
        return result
    for bot_hash, bot_info in bot_info_dict.items():
        if is_qqguildv2_bot(bot_info):
            result[safe_str(bot_hash)] = bot_info
    return result


def normalize_avatar(data: bytes) -> bytes:
    from PIL import Image, ImageOps

    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 16_000_000:
            raise ValueError('Avatar dimensions exceeded')
        image = ImageOps.exif_transpose(source).convert('RGBA')
        image.thumbnail((256, 256))
        output = BytesIO()
        image.save(output, format='PNG')
    return output.getvalue()


def qq_avatar(appid: str, openid: str, refresh: bool = False) -> bytes:
    """只访问 QQ 头像域名，不带账号密钥；成功缓存一小时，失败冷却一分钟。"""
    appid = safe_str(appid)
    openid = safe_str(openid).strip()
    if not openid or not appid.isdecimal():
        return b''
    key = (appid, openid)
    with _avatar_lock:
        now = time.monotonic()
        cached = _avatar_cache.get(key)
        if not refresh and cached and cached[0] > now:
            return cached[1]
        data = b''
        try:
            url = 'https://q.qlogo.cn/qqapp/%s/%s/0' % (quote(appid, safe=''), quote(openid, safe=''))
            with requests.get(url, timeout=(3, 5), stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Unexpected avatar response')
                if int(response.headers.get('Content-Length', '0')) > MAX_AVATAR_BYTES:
                    raise ValueError('Avatar response exceeded')
                body = bytearray()
                deadline = now + 10
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body) > MAX_AVATAR_BYTES or time.monotonic() > deadline:
                        raise ValueError('Avatar download exceeded')
                data = normalize_avatar(bytes(body))
        except Exception:
            pass
        _avatar_cache[key] = (time.monotonic() + (3600 if data else 60), data)
        _avatar_cache.move_to_end(key)
        while len(_avatar_cache) > 64:
            _avatar_cache.popitem(last=False)
        return data


def cache_avatar(bot_hash: Any, data: bytes) -> None:
    """只写当前 bot 目录的 avatar.png。"""
    folder = get_config_bot_root_dir(bot_hash)
    destination = os.path.join(folder, AVATAR_STEM + '.png')
    temporary = None
    try:
        if os.path.isfile(destination):
            with open(destination, 'rb') as file_obj:
                if file_obj.read() == data:
                    return
        fd, tmp_name = tempfile.mkstemp(dir=folder, suffix='.tmp')
        temporary = tmp_name
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, destination)
        temporary = None
    except OSError:
        pass
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def local_avatar(bot_hash: Any) -> bytes:
    folder = get_config_bot_root_dir(bot_hash)
    try:
        names = os.listdir(folder)
    except OSError:
        return b''
    files = {}
    for name in names:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            files[name.lower()] = path
    for suffix in AVATAR_SUFFIXES:
        candidate = files.get(AVATAR_STEM + suffix)
        if not candidate:
            continue
        try:
            if os.path.getsize(candidate) > MAX_AVATAR_BYTES:
                continue
            with open(candidate, 'rb') as file_obj:
                return normalize_avatar(file_obj.read())
        except Exception:
            continue
    return b''


def get_sdk_bot_openid(bot_hash: Any) -> str:
    try:
        import OlivOS

        sdk = getattr(OlivOS, 'qqGuildv2SDK', None)
        cache = getattr(sdk, 'sdkSubSelfOpenInfo', None)
        if not isinstance(cache, dict):
            return ''
        groups = cache.get(safe_str(bot_hash), {})
        if isinstance(groups, dict):
            for value in groups.values():
                text = safe_str(value).strip()
                if text:
                    return text
    except Exception:
        pass
    return ''


def remember_bot_openid(bot_hash: Any, openid: Any) -> None:
    text = safe_str(openid).strip()
    if not text:
        return
    bot_config = load_bot_config(bot_hash)
    if safe_str(bot_config.get('bot_openid', '')).strip() == text:
        return
    bot_config['bot_openid'] = text
    save_bot_config(bot_hash, bot_config)


def remember_bot_openid_from_event(plugin_event) -> None:
    try:
        if not is_qqguildv2_event(plugin_event):
            return
        extend = getattr(getattr(plugin_event, 'data', None), 'extend', None) or {}
        remember_bot_openid(
            get_raw_bot_hash_from_event(plugin_event),
            extend.get('sub_self_open_id'),
        )
    except Exception:
        pass


def resolve_bot_openid(bot_hash: Any) -> str:
    saved = safe_str(load_bot_config(bot_hash).get('bot_openid', '')).strip()
    if saved:
        return saved
    sdk_openid = get_sdk_bot_openid(bot_hash)
    if sdk_openid:
        remember_bot_openid(bot_hash, sdk_openid)
        return sdk_openid
    return ''


def bot_avatar_data_uri(bot_hash: Any, bot_info=None, refresh: bool = False) -> str:
    appid = safe_str(getattr(bot_info, 'id', '')) if bot_info is not None else ''
    data = qq_avatar(appid, resolve_bot_openid(bot_hash), refresh=refresh)
    if data:
        cache_avatar(bot_hash, data)
    else:
        data = local_avatar(bot_hash)
    if not data:
        return ''
    try:
        return 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')
    except Exception:
        return ''


def get_bot_display_text(bot_hash: str, bot_info=None) -> str:
    if bot_info is None:
        return safe_str(bot_hash) or '未知 Bot'
    platform_name = safe_str(getattr(bot_info, 'platform', {}).get('platform', 'qqGuild'))
    bot_id = safe_str(getattr(bot_info, 'id', '未知Bot'))
    bot_name = safe_str(getattr(bot_info, 'name', ''))
    if bot_name:
        return f'{platform_name} | {bot_name} | {bot_id}'
    return f'{platform_name} | {bot_id}'


def get_linked_bot_hash(bot_hash: Any) -> str:
    raw_bot_hash = get_config_bot_hash(bot_hash)
    if has_oliva_dice_core:
        try:
            linked_bot_hash = OlivaDiceCore.console.getMasterBotHash(raw_bot_hash)
            if linked_bot_hash:
                return safe_str(linked_bot_hash)
        except Exception:
            pass
    return raw_bot_hash


def get_olivadice_master_id_list(bot_hash: Any) -> list:
    """读取 OlivaDiceCore 全局骰主，只展示不在本插件里改。"""
    result = []
    if not has_oliva_dice_core:
        return result
    hash_list = [get_config_bot_hash(bot_hash)]
    linked_bot_hash = get_linked_bot_hash(bot_hash)
    if linked_bot_hash not in hash_list:
        hash_list.append(linked_bot_hash)
    for one_hash in hash_list:
        try:
            master_list = OlivaDiceCore.console.getConsoleSwitchByHash('masterList', one_hash)
        except Exception:
            continue
        if not isinstance(master_list, list):
            continue
        for item in master_list:
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                text = safe_str(item[0]).strip()
            else:
                text = safe_str(item).strip()
            if text and text not in result:
                result.append(text)
    return result


def is_olivadice_master(plugin_event) -> bool:
    if not has_oliva_dice_core:
        return False
    try:
        user_hash = OlivaDiceCore.userConfig.getUserHash(
            plugin_event.data.user_id,
            'user',
            plugin_event.platform['platform'],
        )
        bot_hash = get_bot_hash_from_event(plugin_event)
        for one_hash in [bot_hash, get_linked_bot_hash(bot_hash)]:
            if OlivaDiceCore.ordinaryInviteManager.isInMasterList(one_hash, user_hash):
                return True
    except Exception:
        pass
    sender_id = get_sender_id_from_event(plugin_event)
    return sender_id in get_olivadice_master_id_list(get_bot_hash_from_event(plugin_event))


def get_configured_master_list(bot_hash: Any) -> list:
    bot_config = load_bot_config(bot_hash)
    master_list = bot_config.get('configured_master_list', [])
    if not isinstance(master_list, list):
        return []
    return [safe_str(item) for item in master_list if safe_str(item)]


def set_configured_master_list(bot_hash: Any, master_list) -> bool:
    bot_config = load_bot_config(bot_hash)
    cleaned_list = []
    for item in master_list or []:
        text = safe_str(item).strip()
        if text and text not in cleaned_list:
            cleaned_list.append(text)
    bot_config['configured_master_list'] = cleaned_list
    return save_bot_config(bot_hash, bot_config)


def get_sender_id_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.data.user_id)
    except Exception:
        return ''


def is_plugin_master(plugin_event) -> bool:
    sender_id = get_sender_id_from_event(plugin_event)
    if not sender_id:
        return False
    if is_olivadice_master(plugin_event):
        return True
    bot_hash = get_bot_hash_from_event(plugin_event)
    return sender_id in get_configured_master_list(bot_hash)


def load_bot_message_custom(bot_hash: Any) -> dict:
    file_path = os.path.join(get_config_bot_root_dir(bot_hash), config.message_custom_file_name)
    loaded_dict = read_json_file(file_path, message_custom.default_custom_message_dict)
    return merge_dict_with_default(loaded_dict, message_custom.default_custom_message_dict)


def render_custom_message(bot_hash: Any, message_key: str, replace_dict: Optional[dict] = None) -> str:
    custom_dict = load_bot_message_custom(bot_hash)
    template_text = safe_str(custom_dict.get(message_key, ''))
    if not isinstance(replace_dict, dict):
        return template_text
    for key, value in replace_dict.items():
        template_text = template_text.replace('{' + key + '}', safe_str(value))
    return template_text


def reply_message(plugin_event, message_text: str) -> None:
    try:
        plugin_event.reply(safe_str(message_text))
    except Exception:
        pass


def format_api_result(result: Any) -> str:
    if not isinstance(result, dict):
        return safe_str(result)
    try:
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception:
        return safe_str(result)


def exception_text(exception_object) -> str:
    return f'{type(exception_object).__name__}: {safe_str(exception_object)}\n{traceback.format_exc()}'
