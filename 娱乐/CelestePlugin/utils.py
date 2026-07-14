# -*- encoding: utf-8 -*-
"""CelestePlugin 公共能力。"""

import copy
import hashlib
import json
import os
import re
import shutil
import threading
import traceback
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
reply_segment_pattern = re.compile(r'^\[OP:reply,id=[^\]]+\]\s*')
at_segment_pattern = re.compile(r'^\[OP:at,id=(?P<id>[^,\]]+?)(?:,name=(?P<name>[^\]]*))?\]')


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
    try:
        return safe_str(plugin_event.base_info.get('self_id', ''))
    except Exception:
        return get_bot_id_from_event(plugin_event)


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
    return reply_segment_pattern.sub('', safe_str(message_text), count=1)


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
        result.append({'id': safe_str(matched.group('id')), 'raw': matched.group(0)})
        remaining = remaining[matched.end() :]
    return result, remaining.lstrip()


def is_force_reply_to_current_bot(at_items: list[dict[str, str]], plugin_event) -> bool:
    self_id = get_self_id_from_event(plugin_event)
    return any(item.get('id') in [self_id, 'all'] for item in at_items)


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
    """统一回复。"""
    try:
        return plugin_event.reply(safe_str(message_text))
    except Exception:
        return None


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
