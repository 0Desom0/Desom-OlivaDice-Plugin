# -*- encoding: utf-8 -*-
"""CelestePlugin 公共能力。"""

import copy
import hashlib
import json
import os
import re
import shutil
import threading
import time
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from functools import wraps
from typing import Any, Iterable

from . import config


has_oliva_dice_core = False
try:
    import OlivaDiceCore

    has_oliva_dice_core = True
except Exception:
    has_oliva_dice_core = False


file_lock = threading.RLock()
runtime_proc = None
reply_segment_pattern = re.compile(r'^\[(?:OP|CQ):reply(?:,[^\]]*)?\]', re.IGNORECASE)
at_segment_pattern = re.compile(r'^\[(?:OP|CQ):at,(?P<params>[^\]]*)\]', re.IGNORECASE)

_COVER_WORKERS = 3
_COVER_TIMEOUT = 8
_COVER_BATCH_TIMEOUT = 12
_COVER_MAX_BYTES = 10 * 1024 * 1024
_cover_pool = ThreadPoolExecutor(max_workers=_COVER_WORKERS, thread_name_prefix='CelesteCover')
_cover_write_lock = threading.Lock()


def safe_str(value: Any, default_value: str = '') -> str:
    """安全转换字符串。"""
    try:
        text = str(value)
    except Exception:
        return default_value
    return text if text else default_value


def op_escape(value: Any) -> str:
    """转义 OP 码参数中的保留字符。"""
    return safe_str(value).replace('&', '&amp;').replace('[', '&#91;').replace(']', '&#93;').replace(',', '&#44;')


def deep_copy_default(value: Any) -> Any:
    """复制默认值，避免模块级字典被修改。"""
    return copy.deepcopy(value)


def merge_dict_with_default(source: Any, default: dict[str, Any]) -> dict[str, Any]:
    """用默认值补齐字典。"""
    result = deep_copy_default(default)
    if isinstance(source, dict):
        result.update(source)
    return result


def ensure_folder(folder_path: str) -> str:
    """确保目录存在。"""
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def read_json_file(file_path: str, default_value: Any) -> Any:
    """读取 JSON，失败时返回默认值。"""
    if not os.path.exists(file_path):
        return deep_copy_default(default_value)
    with file_lock:
        try:
            with open(file_path, encoding='utf-8') as file_object:
                return json.load(file_object)
        except Exception:
            return deep_copy_default(default_value)


def save_json_file(file_path: str, data: Any) -> bool:
    """保存 JSON。"""
    with file_lock:
        try:
            ensure_folder(os.path.dirname(file_path))
            temporary_path = f'{file_path}.tmp'
            with open(temporary_path, 'w', encoding='utf-8') as file_object:
                json.dump(data, file_object, ensure_ascii=False, indent=2)
            os.replace(temporary_path, file_path)
            return True
        except Exception:
            return False


def read_text_file(file_path: str, default_value: str = '') -> str:
    """读取 UTF-8 文本。"""
    if not os.path.exists(file_path):
        return default_value
    with file_lock:
        try:
            with open(file_path, encoding='utf-8') as file_object:
                return file_object.read()
        except Exception:
            return default_value


def save_text_file(file_path: str, content: str) -> bool:
    """保存 UTF-8 文本。"""
    with file_lock:
        try:
            ensure_folder(os.path.dirname(file_path))
            temporary_path = f'{file_path}.tmp'
            with open(temporary_path, 'w', encoding='utf-8') as file_object:
                file_object.write(content)
            os.replace(temporary_path, file_path)
            return True
        except Exception:
            return False


def set_runtime_proc(Proc) -> None:
    """保存运行期 Proc。"""
    global runtime_proc
    if Proc is not None:
        runtime_proc = Proc


def log_message(Proc, level: int, level_name: str, message: str) -> None:
    """统一日志输出。"""
    text = f'[{config.plugin_name}][{level_name}] {safe_str(message)}'
    if Proc is not None and hasattr(Proc, 'log'):
        try:
            Proc.log(level, text, [])
            return
        except Exception:
            pass
    print(text)


def info_log(Proc, message: str) -> None:
    log_message(Proc, 2, 'INFO', message)


def error_log(Proc, message: str) -> None:
    log_message(Proc, 4, 'ERROR', message)


def debug_log(Proc, message: str) -> None:
    if load_global_config().get('global_debug_mode_switch', False):
        log_message(Proc, 0, 'DEBUG', message)


def log_exception(action_name: str):
    """拦截事件函数异常，防止影响 OlivOS 主进程。"""

    def decorator(target_function):
        @wraps(target_function)
        def wrapper(*args, **kwargs):
            Proc = kwargs.get('Proc')
            if Proc is None and len(args) >= 2:
                Proc = args[1]
            try:
                return target_function(*args, **kwargs)
            except Exception as exception_object:
                error_log(
                    Proc,
                    f'{action_name} 失败：{type(exception_object).__name__}: {exception_object}\n'
                    f'{traceback.format_exc()}',
                )
                return None

        return wrapper

    return decorator


def get_linked_bot_hash(bot_hash: Any) -> str:
    """获取群链后的 bot hash，运行数据跟随主账号。"""
    raw_hash = safe_str(bot_hash).strip() or 'default'
    if has_oliva_dice_core:
        try:
            linked_hash = OlivaDiceCore.console.getMasterBotHash(raw_hash)
            if linked_hash:
                return safe_str(linked_hash)
        except Exception:
            pass
    return raw_hash


def get_raw_bot_hash_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.bot_info.hash, 'default')
    except Exception:
        return 'default'


def get_bot_hash_from_event(plugin_event, use_linked: bool = False) -> str:
    raw_hash = get_raw_bot_hash_from_event(plugin_event)
    return get_linked_bot_hash(raw_hash) if use_linked else raw_hash


def get_bot_id_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.bot_info.id)
    except Exception:
        return ''


def get_self_id_from_event(plugin_event) -> str:
    target_id_list = get_current_bot_target_ids(plugin_event)
    return target_id_list[0] if target_id_list else ''


def get_current_bot_target_ids(plugin_event) -> list[str]:
    """Return every account id that can address the current bot."""
    target_id_list = []
    try:
        base_info = plugin_event.base_info
        if isinstance(base_info, dict):
            target_id_list.append(base_info.get('self_id'))
        else:
            target_id_list.append(getattr(base_info, 'self_id', None))
    except Exception:
        pass
    try:
        target_id_list.append(plugin_event.bot_info.id)
    except Exception:
        pass
    try:
        extend = getattr(plugin_event.data, 'extend', {}) or {}
        for key in ['sub_self_id', 'sub_self_open_id']:
            if isinstance(extend, dict):
                target_id_list.append(extend.get(key))
            else:
                target_id_list.append(getattr(extend, key, None))
    except Exception:
        pass
    normalized_id_list = []
    for target_id in target_id_list:
        normalized_id = safe_str(target_id).strip() if target_id is not None else ''
        if normalized_id and normalized_id not in normalized_id_list:
            normalized_id_list.append(normalized_id)
    return normalized_id_list


def get_sender_id_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.data.user_id)
    except Exception:
        return ''


def get_group_id_from_event(plugin_event) -> str:
    try:
        return safe_str(getattr(plugin_event.data, 'group_id', '') or '')
    except Exception:
        return ''


def get_host_id_from_event(plugin_event) -> str:
    try:
        return safe_str(getattr(plugin_event.data, 'host_id', '') or '')
    except Exception:
        return ''


def get_platform_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.platform.get('platform', 'unknown'))
    except Exception:
        return 'unknown'


def get_message_text_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.data.message)
    except Exception:
        return ''


def get_hag_id_from_event(plugin_event) -> str:
    group_id = get_group_id_from_event(plugin_event)
    host_id = get_host_id_from_event(plugin_event)
    if not group_id:
        return ''
    return f'{host_id}|{group_id}' if host_id else group_id


def get_user_hash_from_event(plugin_event) -> str:
    """生成与用户及平台绑定的稳定哈希。"""
    source = f'{get_sender_id_from_event(plugin_event)}|user|{get_platform_from_event(plugin_event)}'
    return hashlib.md5(source.encode('utf-8')).hexdigest()


def get_global_config_file_path() -> str:
    return os.path.join(config.plugin_data_dir, config.global_config_file_name)


def get_bot_root_dir(bot_hash: Any, use_linked: bool = False) -> str:
    folder_hash = get_linked_bot_hash(bot_hash) if use_linked else safe_str(bot_hash, 'default')
    return ensure_folder(os.path.join(config.plugin_data_dir, folder_hash))


def get_bot_config_file_path(bot_hash: Any) -> str:
    return os.path.join(get_bot_root_dir(bot_hash), config.bot_config_file_name)


def get_storage_dir(bot_hash: Any) -> str:
    return ensure_folder(os.path.join(get_bot_root_dir(bot_hash, use_linked=True), config.storage_folder_name))


def get_shared_cache_dir() -> str:
    return ensure_folder(os.path.join(config.plugin_data_dir, 'cache'))


def get_personal_storage_dir(plugin_event) -> str:
    """获取跟随群链、但不区分群聊上下文的个人存储目录。"""
    linked_hash = get_bot_hash_from_event(plugin_event, use_linked=True)
    user_hash = get_user_hash_from_event(plugin_event)
    return ensure_folder(os.path.join(get_storage_dir(linked_hash), 'user', user_hash))


def get_user_storage_dir(plugin_event) -> str:
    group_id = get_group_id_from_event(plugin_event)
    if group_id:
        context_source = f'group|{get_host_id_from_event(plugin_event)}|{group_id}'
    else:
        context_source = 'private'
    context_hash = hashlib.md5(context_source.encode('utf-8')).hexdigest()
    return ensure_folder(os.path.join(get_personal_storage_dir(plugin_event), context_hash))


def load_global_config() -> dict[str, Any]:
    data = read_json_file(get_global_config_file_path(), config.default_global_config)
    return merge_dict_with_default(data, config.default_global_config)


def save_global_config(data: dict[str, Any]) -> bool:
    return save_json_file(
        get_global_config_file_path(),
        merge_dict_with_default(data, config.default_global_config),
    )


def load_bot_config(bot_hash: Any) -> dict[str, Any]:
    data = read_json_file(get_bot_config_file_path(bot_hash), config.default_bot_config)
    return merge_dict_with_default(data, config.default_bot_config)


def save_bot_config(bot_hash: Any, data: dict[str, Any]) -> bool:
    return save_json_file(
        get_bot_config_file_path(bot_hash),
        merge_dict_with_default(data, config.default_bot_config),
    )


def initialize_bot_storage(bot_hash: Any) -> None:
    """初始化原始 bot 配置和群链存储。"""
    get_bot_root_dir(bot_hash)
    get_storage_dir(bot_hash)
    if not os.path.exists(get_bot_config_file_path(bot_hash)):
        save_bot_config(bot_hash, config.default_bot_config)


def migrate_legacy_data_dir(Proc) -> None:
    """首次更名时把 CelesteSearch 的运行数据复制到 CelestePlugin。"""
    if os.path.exists(config.plugin_data_dir) or not os.path.isdir(config.legacy_plugin_data_dir):
        return
    try:
        shutil.copytree(config.legacy_plugin_data_dir, config.plugin_data_dir)
        info_log(Proc, '已将旧 CelesteSearch 数据目录迁移到 CelestePlugin。')
    except Exception as exception_object:
        error_log(Proc, f'迁移旧插件数据失败：{exception_object}')


def initialize_plugin(Proc) -> None:
    """初始化插件数据目录。"""
    migrate_legacy_data_dir(Proc)
    ensure_folder(config.plugin_data_dir)
    get_shared_cache_dir()
    if not os.path.exists(get_global_config_file_path()):
        save_global_config(config.default_global_config)
    try:
        bot_info_dict = getattr(Proc, 'Proc_data', {}).get('bot_info_dict', {})
        for raw_bot_hash in bot_info_dict:
            initialize_bot_storage(raw_bot_hash)
    except Exception as exception_object:
        error_log(Proc, f'初始化 bot 目录失败：{exception_object}')


def ensure_runtime_storage_by_event(plugin_event) -> str:
    raw_hash = get_raw_bot_hash_from_event(plugin_event)
    initialize_bot_storage(raw_hash)
    return raw_hash


def strip_reply_segment(message_text: str) -> str:
    remaining = safe_str(message_text)
    while True:
        remaining = remaining.lstrip()
        matched = reply_segment_pattern.match(remaining)
        if not matched:
            return remaining
        remaining = remaining[matched.end() :]


def parse_prefix(message_text: str, prefix_list: Iterable[str] | None = None) -> tuple[str, str]:
    source = safe_str(message_text)
    for prefix in list(prefix_list or config.allowed_prefix_list):
        if source.startswith(prefix):
            return prefix, source[len(prefix) :].lstrip()
    return '', source


def parse_command(
    message_text: str,
    prefix_list: Iterable[str] | None = None,
    allow_no_prefix: bool = False,
    command_name: Any = None,
    ignore_case: bool = True,
) -> dict[str, Any]:
    """按长度倒序执行贪婪命令匹配。"""
    cleaned = strip_reply_segment(message_text)
    prefix, remaining = parse_prefix(cleaned, prefix_list)
    if not prefix and not allow_no_prefix:
        return {'is_command': False, 'prefix': '', 'command_name': '', 'command_argument': ''}

    source = remaining if prefix else cleaned.lstrip()
    if command_name is None:
        tokens = source.split(None, 1)
        name = tokens[0] if tokens else ''
        argument = tokens[1] if len(tokens) > 1 else ''
        return {
            'is_command': bool(name),
            'prefix': prefix,
            'command_name': name.lower() if ignore_case else name,
            'command_argument': argument,
        }

    command_list = [command_name] if isinstance(command_name, str) else list(command_name or [])
    compare_source = source.lower() if ignore_case else source
    for raw_name in sorted((safe_str(item) for item in command_list), key=len, reverse=True):
        compare_name = raw_name.lower() if ignore_case else raw_name
        if raw_name and compare_source.startswith(compare_name):
            return {
                'is_command': True,
                'prefix': prefix,
                'command_name': compare_name,
                'command_argument': source[len(raw_name) :].lstrip(),
            }
    return {'is_command': False, 'prefix': prefix, 'command_name': '', 'command_argument': source}


def parse_at_segments(message_text: str) -> tuple[list[dict[str, str]], str]:
    """解析消息开头连续的 OP at 段。"""
    remaining = safe_str(message_text)
    result = []
    while True:
        remaining = remaining.lstrip()
        matched = at_segment_pattern.match(remaining)
        if not matched:
            break
        params = {}
        for item in safe_str(matched.group('params')).split(','):
            key, separator, value = item.partition('=')
            if separator:
                params[key.strip().casefold()] = value.strip()
        result.append(
            {
                'id': safe_str(params.get('id') or params.get('qq') or ''),
                'raw': matched.group(0),
            }
        )
        remaining = remaining[matched.end() :]
    return result, remaining.lstrip()


def is_force_reply_to_current_bot(at_items: list[dict[str, str]], plugin_event) -> bool:
    current_bot_id_set = set(get_current_bot_target_ids(plugin_event))
    current_bot_id_set.add('all')
    return any(safe_str(item.get('id')).strip() in current_bot_id_set for item in at_items)


def check_core_group_enable(plugin_event) -> bool:
    """尊重 OlivaDiceCore 的群开关。"""
    if not has_oliva_dice_core:
        return True
    try:
        if safe_str(plugin_event.plugin_info.get('func_type', '')) != 'group_message':
            return True
        host_id = get_host_id_from_event(plugin_event)
        hag_id = get_hag_id_from_event(plugin_event)
        platform = get_platform_from_event(plugin_event)
        bot_hash = plugin_event.bot_info.hash
        if host_id:
            enabled = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId=host_id,
                userType='host',
                platform=platform,
                userConfigKey='hostLocalEnable',
                botHash=bot_hash,
            )
            if not enabled:
                return False
        if hag_id:
            enabled = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId=hag_id,
                userType='group',
                platform=platform,
                userConfigKey='groupEnable',
                botHash=bot_hash,
            )
            if not enabled:
                return False
    except Exception:
        return True
    return True


def is_sender_core_master(plugin_event) -> bool:
    """判断发送者是否为 OlivaDiceCore 骰主。"""
    if not has_oliva_dice_core:
        return False
    try:
        user_hash = OlivaDiceCore.userConfig.getUserHash(
            plugin_event.data.user_id,
            'user',
            plugin_event.platform['platform'],
        )
        return bool(
            OlivaDiceCore.ordinaryInviteManager.isInMasterList(
                plugin_event.bot_info.hash,
                user_hash,
            )
        )
    except Exception:
        return False


def is_group_admin(plugin_event) -> bool:
    """判断发送者是否为群主或群管理员。"""
    try:
        role = safe_str(plugin_event.data.sender.get('role', '')).lower()
        return role in ['owner', 'admin', 'sub_admin']
    except Exception:
        return False


def can_manage_group_switch(plugin_event) -> bool:
    """群主、群管或 OlivaDiceCore 骰主可以管理本插件群开关。"""
    return is_group_admin(plugin_event) or is_sender_core_master(plugin_event)


def get_group_switch_key(plugin_event) -> str:
    """优先使用 HAG 标识，避免频道子群之间发生开关冲突。"""
    return get_hag_id_from_event(plugin_event) or get_group_id_from_event(plugin_event)


def get_disabled_group_list(bot_hash: Any) -> list[str]:
    """读取当前 Bot 的 CelestePlugin 群级禁用列表。"""
    raw_list = load_bot_config(bot_hash).get('disabled_group_list', [])
    if not isinstance(raw_list, list):
        return []
    result = []
    for raw_item in raw_list:
        item = safe_str(raw_item).strip()
        if item and item not in result:
            result.append(item)
    return result


def set_disabled_group_list(bot_hash: Any, group_key_list: Iterable[str]) -> bool:
    """保存当前 Bot 的 CelestePlugin 群级禁用列表。"""
    normalized_list = []
    for raw_item in group_key_list:
        item = safe_str(raw_item).strip()
        if item and item not in normalized_list:
            normalized_list.append(item)
    bot_config = load_bot_config(bot_hash)
    bot_config['disabled_group_list'] = normalized_list
    return save_bot_config(bot_hash, bot_config)


def is_group_disabled(plugin_event) -> bool:
    """检查当前群是否单独关闭了 CelestePlugin。"""
    group_key = get_group_switch_key(plugin_event)
    if not group_key:
        return False
    bot_hash = get_bot_hash_from_event(plugin_event)
    return group_key in get_disabled_group_list(bot_hash)


def set_group_disabled(plugin_event, disabled: bool) -> bool:
    """设置当前群的 CelestePlugin 独立开关。"""
    group_key = get_group_switch_key(plugin_event)
    if not group_key:
        return False
    bot_hash = get_bot_hash_from_event(plugin_event)
    disabled_list = get_disabled_group_list(bot_hash)
    if disabled and group_key not in disabled_list:
        disabled_list.append(group_key)
    elif not disabled:
        disabled_list = [item for item in disabled_list if item != group_key]
    return set_disabled_group_list(bot_hash, disabled_list)


def reply_message(plugin_event, message_text: str) -> Any:
    """统一回复：回调事件没有 reply 通道，改走该会话的主动发送接口。"""
    text = add_reply_quote(plugin_event, message_text)
    if safe_str((getattr(plugin_event, 'plugin_info', {}) or {}).get('func_type')) == 'button_click':
        chat_type, chat_id = get_chat_context(plugin_event)
        sender = getattr(getattr(plugin_event, 'indeAPI', None), 'send_message', None)
        extend = getattr(getattr(plugin_event, 'data', None), 'extend', None)
        event_id = safe_str(extend.get('event_id')) if isinstance(extend, dict) else ''
        if chat_type and chat_id and callable(sender):
            try:
                # 带 event_id 才是被动回复；不带会被平台当成主动消息（无权限直接 400）
                return sender(chat_type=chat_type, chat_id=chat_id, message=text, event_id=event_id or None)
            except Exception:
                return None
        return None
    try:
        return plugin_event.reply(text)
    except Exception:
        return None


def build_reply_quote_segment(plugin_event) -> str:
    """Quote the triggering message for group replies."""
    if not get_group_id_from_event(plugin_event):
        return ''
    try:
        message_id = safe_str(getattr(plugin_event.data, 'message_id', '')).strip()
    except Exception:
        return ''
    if not message_id or message_id == '-1':
        return ''
    return f'[OP:reply,id={op_escape(message_id)}]'


def add_reply_quote(plugin_event, message_text: str) -> str:
    source = safe_str(message_text)
    if load_global_config().get('reply_quote_switch', True) is False:
        return source
    # 按钮回调没有可直接引用的源消息，引用了反而会让主动消息被平台拒绝。
    if safe_str((getattr(plugin_event, 'plugin_info', {}) or {}).get('func_type')) == 'button_click':
        return source
    if reply_segment_pattern.match(source.lstrip()):
        return source
    # QQ 官方机器人的图文混排消息：只要带 reply 段，适配器就整条拒绝走 Markdown
    # （日志「带引用的图文消息不走 Markdown；回退到原有图文发送流程」）。
    # 所以自己把引用拼成 Markdown 引用行，消息里不再出现原生引用段。
    if (
        '[OP:image' in source
        and load_global_config().get('markdown_enable_switch', True)
        and get_chat_context(plugin_event)[0] == 'qq_group'
    ):
        header = build_markdown_header(plugin_event)
        return f'{header}\n\n{source}' if header else source
    return f'{build_reply_quote_segment(plugin_event)}{source}'


def get_chat_context(plugin_event) -> tuple[str, str]:
    """从事件推导 QQ 官方机器人的 chat_type / chat_id（群、C2C、频道、频道私信）。"""
    data = getattr(plugin_event, 'data', None)
    extend = getattr(data, 'extend', None)
    extend = extend if isinstance(extend, dict) else {}
    func_type = safe_str((getattr(plugin_event, 'plugin_info', {}) or {}).get('func_type', ''))
    group_id = safe_str(getattr(data, 'group_id', None))
    user_id = safe_str(getattr(data, 'user_id', None))
    host_id = safe_str(extend.get('host_group_id')) or safe_str(getattr(data, 'host_id', None))
    if extend.get('chat_type') and extend.get('chat_id'):
        return safe_str(extend.get('chat_type')), safe_str(extend.get('chat_id'))
    flag_direct = bool(extend.get('flag_from_direct', func_type == 'private_message'))
    if 'flag_from_qq' in extend:
        if bool(extend.get('flag_from_qq')):
            return ('qq_private' if flag_direct else 'qq_group'), (user_id if flag_direct else group_id)
        return (
            ('guild_private' if flag_direct else 'guild_channel'),
            ((host_id or group_id) if flag_direct else group_id),
        )
    platform_name = ''
    try:
        platform_name = safe_str(plugin_event.platform.get('platform', '')).lower()
    except Exception:
        platform_name = ''
    if platform_name == 'qqguild':
        if host_id:
            return (
                ('guild_private' if flag_direct else 'guild_channel'),
                ((host_id or group_id) if flag_direct else group_id),
            )
        return ('qq_private' if flag_direct else 'qq_group'), (user_id if flag_direct else group_id)
    return '', ''


def get_cover_cache_dir() -> str:
    """临时封面目录（相对 OlivOS 根目录）。

    适配器读取本地图时会走 contentAPI.resourcePathTransform('images', path)：
    绝对路径原样使用，相对路径一律拼到 <OlivOS>/data/images/ 下。所以这里
    直接落在 data/images/CelestePlugin/covers，交给适配器的也是同一相对路径，
    换机器/换部署目录都不用改。
    """
    base = os.path.join('data', 'images', 'CelestePlugin', 'covers')
    os.makedirs(base, exist_ok=True)
    return base


def get_cover_cache_limit() -> int:
    """封面缓存条数上限（默认 100），配错就按 100 处理。"""
    try:
        return max(1, int(load_global_config().get('cover_cache_max_items', 100)))
    except Exception:
        return 100


def get_cover_cache_entries() -> list[tuple[float, str]]:
    """列出封面缓存文件，按最后使用时间（mtime）升序，最旧的在前。"""
    folder = get_cover_cache_dir()
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    entries = []
    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        try:
            entries.append((os.path.getmtime(path), path))
        except OSError:
            continue
    entries.sort()
    return entries


def trim_cover_cache() -> int:
    """超出上限就删最久没被用过的那几张，返回删除数量。

    命中缓存时会把 mtime 刷成当前时间，所以「最久远」实际是「最久没被用过」，
    常发的封面不会被新图挤掉。
    """
    limit = get_cover_cache_limit()
    entries = get_cover_cache_entries()
    overflow = len(entries) - limit
    if overflow <= 0:
        return 0
    removed = 0
    for _mtime, path in entries[:overflow]:
        try:
            os.remove(path)
            removed += 1
        except OSError:
            continue
    return removed


def _cached_cover(folder: str, digest: str) -> str:
    for suffix in ('.jpg', '.png'):
        path = os.path.join(folder, digest + suffix)
        try:
            if os.path.getsize(path) <= 0:
                continue
        except OSError:
            continue
        try:
            os.utime(path, None)
        except OSError:
            pass
        return 'CelestePlugin/covers/' + digest + suffix
    return ''


def _download_cover(source: str) -> bytearray | bytes:
    deadline = time.monotonic() + _COVER_TIMEOUT
    request = urllib.request.Request(source, headers={'User-Agent': config.bot_user_agent})
    with urllib.request.urlopen(request, timeout=_COVER_TIMEOUT) as response:
        # socket 超时只限制单次读；持续缓慢传输的封面也不能无限占用工作线程。
        data = bytearray()
        while time.monotonic() < deadline:
            chunk = response.read1(min(64 * 1024, _COVER_MAX_BYTES + 1 - len(data)))
            if not chunk:
                return data if time.monotonic() < deadline else b''
            data.extend(chunk)
            if len(data) > _COVER_MAX_BYTES:
                break
    return b''


def _store_cover(folder: str, digest: str, data: bytes | bytearray) -> str:
    name = digest + ('.png' if data.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg')
    path = os.path.join(folder, name)
    # 读缓存不加锁；原子替换确保别的消息只会读到完整的图。
    temporary = path + '.tmp'
    try:
        with open(temporary, 'wb') as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return 'CelestePlugin/covers/' + name


def _prepare_local_images(images: dict[str, str]) -> dict[str, str]:
    started = time.monotonic()
    try:
        folder = get_cover_cache_dir()
    except OSError as exc:
        error_log(runtime_proc, f'无法访问封面缓存：{exc}')
        return {}
    sources = {label: safe_str(url).strip() for label, url in images.items()}
    paths = {}
    pending = {}
    for url in dict.fromkeys(sources.values()):
        if not url.startswith(('http://', 'https://')):
            continue
        digest = hashlib.sha1(url.encode('utf-8')).hexdigest()
        cached = _cached_cover(folder, digest)
        if cached:
            paths[url] = cached
        else:
            pending[_cover_pool.submit(_download_cover, url)] = (url, digest)
    if pending:
        # 共用工作池；到期只取已完成项，不能退出 with 等慢下载收尾。
        budget = _COVER_TIMEOUT if len(pending) <= _COVER_WORKERS else _COVER_BATCH_TIMEOUT
        done, unfinished = wait(pending, timeout=max(0, started + budget - time.monotonic()))
        for future in unfinished:
            future.cancel()
        cached_count = len(paths)
        with _cover_write_lock:
            for future, (url, digest) in pending.items():
                if future not in done:
                    continue
                try:
                    data = future.result()
                    if data:
                        paths[url] = _store_cover(folder, digest, data)
                except Exception as exc:
                    error_log(runtime_proc, f'封面准备失败：{url}：{exc}')
            if len(paths) > cached_count and trim_cover_cache():
                # 缓存上限可能比本批图片数还低；不能把已淘汰的文件交给适配器。
                paths = {url: path for url, path in paths.items() if os.path.isfile(
                    os.path.join(folder, os.path.basename(path))
                )}
    return {label: paths[url] for label, url in sources.items() if url in paths}


def prepare_local_image(url: str) -> str:
    """取单张封面；与多图回复共用缓存、超时和并发上限。"""
    return _prepare_local_images({'cover': url}).get('cover', '')


def release_local_image(resource: str) -> None:
    """封面改为缓存复用，发送后不再删除；保留空实现兼容旧调用点。

    缓存清理交给 trim_cover_cache（上限 cover_cache_max_items），
    这里删文件会让缓存永远命中不了。
    """
    return None


def can_send_markdown(plugin_event) -> bool:
    if not load_global_config().get('markdown_enable_switch', True):
        return False
    return callable(getattr(getattr(plugin_event, 'indeAPI', None), 'create_markdown_message', None))


def build_markdown_header(plugin_event) -> str:
    """Markdown 不支持引用，用首行引用块 @发送者 + 原消息内容代替。"""
    if not load_global_config().get('reply_quote_switch', True):
        return ''
    data = getattr(plugin_event, 'data', None)
    user_id = safe_str(getattr(data, 'user_id', None)).strip()
    if not user_id:
        return ''
    text = safe_str(get_message_text_from_event(plugin_event)).strip()
    text = strip_reply_segment(text)
    text = re.sub(r'\[OP:[^\]]*\]', '', text).strip()
    if len(text) > 40:
        text = f'{text[:40]}…'
    at_tag = f'<qqbot-at-user id="{op_escape(user_id)}" />'
    return f'> {at_tag}：{text}' if text else f'> {at_tag}'


def reply_markdown(plugin_event, markdown_text: str, keyboard=None, *, images=None) -> bool:
    """发 QQ Markdown，可带键盘及图片；不支持时由调用方走原有图文回复。"""
    if not can_send_markdown(plugin_event):
        return False
    content = safe_str(markdown_text)
    if not content:
        return False
    chat_type, chat_id = get_chat_context(plugin_event)
    if not chat_type or not chat_id:
        return False
    # C2C 私聊不支持 qqbot-at-user（平台回 40034106），只在群里加引用头。
    header = build_markdown_header(plugin_event) if chat_type == 'qq_group' else ''
    if header:
        content = f'{header}\n\n{content}'
    sender = plugin_event.indeAPI.create_markdown_message
    payload = {'chat_type': chat_type, 'chat_id': chat_id, 'markdown': {'content': content}}
    # 频道/频道私信不支持回调按钮，只发 Markdown 正文。
    is_qq_chat = chat_type in ('qq_group', 'qq_private')
    if keyboard and is_qq_chat:
        payload['keyboard'] = keyboard
    if images:
        if not is_qq_chat:
            return False
        local_images = _prepare_local_images(images)
        if local_images:
            payload['local_images'] = local_images
            for label in images.keys() - local_images.keys():
                # 仅移除失败封面的占位行，保留其他封面和正文原有的空行。
                placeholder = re.escape('{{' + label + '}}')
                content = re.sub(placeholder + r'\n*', '', content)
            payload['markdown']['content'] = content
        else:
            # 封面全部拿不到时把占位符去掉，正文照常发 Markdown。
            payload['markdown']['content'] = re.sub(
                r'\{\{[^}]+\}\}\n*', '', payload['markdown']['content']
            ).strip()
    data = getattr(plugin_event, 'data', None)
    extend = getattr(data, 'extend', None)
    extend = extend if isinstance(extend, dict) else {}
    message_id = safe_str(getattr(data, 'message_id', '')).strip()
    event_id = safe_str(extend.get('event_id')).strip()
    if plugin_event.plugin_info.get('func_type') == 'button_click':
        # message_id 是原卡片 ID，不是用户这次点击的被动回复凭据。
        if event_id:
            payload['event_id'] = event_id
    elif message_id and message_id != '-1':
        payload['msg_id'] = message_id
    elif event_id:
        payload['event_id'] = event_id
    local_resources = list((payload.get('local_images') or {}).values())
    try:
        result = sender(**payload)
    except Exception:
        for resource in local_resources:
            release_local_image(resource)
        return False
    for resource in local_resources:
        release_local_image(resource)
    if isinstance(result, dict) and not result.get('active', False):
        error_log(None, 'Markdown 发送失败：%s' % safe_str(result.get('data', {}).get('error', result)))
        return False
    return True


def split_long_text(message_text: str, chunk_size: int) -> list[str]:
    """优先按换行拆分长文本。"""
    text = safe_str(message_text)
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    current = ''
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) <= chunk_size:
            current += line
            continue
        if current:
            chunks.append(current.rstrip())
            current = ''
        while len(line) > chunk_size:
            chunks.append(line[:chunk_size])
            line = line[chunk_size:]
        current = line
    if current:
        chunks.append(current.rstrip())
    return [chunk for chunk in chunks if chunk]


def reply_long_text(plugin_event, message_text: str) -> None:
    """纯文字分段回复，不生成图片。"""
    chunk_size = int(load_global_config().get('long_reply_chunk_size', 1800))
    for chunk in split_long_text(message_text, max(500, chunk_size)):
        reply_message(plugin_event, chunk)
