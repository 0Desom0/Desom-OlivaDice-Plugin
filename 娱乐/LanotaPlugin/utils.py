# -*- encoding: utf-8 -*-
"""OlivOS 通用工具与安全封装。"""

import copy
import functools
import json
import os
import re
import shutil
import threading
import traceback
from pathlib import Path
from typing import Any

from . import config

runtime_proc = None
initialized = False
file_lock = threading.RLock()
reply_segment_pattern = re.compile(r'^\[OP:reply,id=[^\]]+\]\s*')
at_segment_pattern = re.compile(r'^\[OP:at,id=(?P<id>[^,\]]+?)(?:,name=(?P<name>[^\]]*))?\]')

has_oliva_dice_core = False
try:
    import OlivaDiceCore

    has_oliva_dice_core = True
except Exception:
    has_oliva_dice_core = False


def safe_str(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return ''


def set_runtime_proc(Proc) -> None:
    global runtime_proc
    if Proc is not None:
        runtime_proc = Proc


def log_message(Proc, level: int, level_name: str, text: str) -> None:
    message_text = f'[{config.plugin_name}][{level_name}] {safe_str(text)}'
    if Proc is not None and hasattr(Proc, 'log'):
        try:
            Proc.log(level, message_text, [])
            return
        except Exception:
            pass
    print(message_text)


def info_log(Proc, text: str) -> None:
    log_message(Proc, 2, 'INFO', text)


def error_log(Proc, text: str) -> None:
    log_message(Proc, 4, 'ERROR', text)


def debug_log(Proc, text: str) -> None:
    if load_global_config().get('global_debug_mode_switch', False):
        log_message(Proc, 0, 'DEBUG', text)


def log_exception(action_name: str):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            Proc = kwargs.get('Proc')
            if Proc is None and len(args) >= 2:
                Proc = args[1]
            try:
                return func(*args, **kwargs)
            except Exception as exception_object:
                error_log(
                    Proc,
                    f'{action_name} 执行失败：{type(exception_object).__name__}: '
                    f'{safe_str(exception_object)}\n{traceback.format_exc()}',
                )
                return None

        return wrapper

    return decorator


def ensure_folder(path: str | Path) -> str:
    os.makedirs(path, exist_ok=True)
    return str(path)


def read_json_file(file_path: str | Path, default_value: Any) -> Any:
    try:
        if not os.path.exists(file_path):
            return copy.deepcopy(default_value)
        with file_lock:
            with open(file_path, 'r', encoding='utf-8') as file_object:
                return json.load(file_object)
    except Exception:
        return copy.deepcopy(default_value)


def save_json_file(file_path: str | Path, data: Any) -> bool:
    try:
        with file_lock:
            ensure_folder(Path(file_path).parent)
            with open(file_path, 'w', encoding='utf-8') as file_object:
                json.dump(data, file_object, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def merge_dict_with_default(source: Any, default: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(default)
    if isinstance(source, dict):
        merged.update(source)
    return merged


def get_plugin_data_dir() -> str:
    return ensure_folder(config.plugin_data_dir)


def get_global_config_path() -> str:
    return os.path.join(get_plugin_data_dir(), config.global_config_file_name)


def get_linked_bot_hash(bot_hash: Any) -> str:
    """按照 OlivaDiceCore 群链规则获取 linked bot hash。"""
    raw_bot_hash = safe_str(bot_hash).strip() or 'default'
    if has_oliva_dice_core:
        try:
            linked_bot_hash = OlivaDiceCore.console.getMasterBotHash(raw_bot_hash)
            if linked_bot_hash:
                return safe_str(linked_bot_hash)
        except Exception:
            pass
    return raw_bot_hash


def get_config_bot_hash(bot_hash: Any) -> str:
    """获取原始 bot hash，用于 bot_config。"""
    return safe_str(bot_hash).strip() or 'default'


def get_bot_hash_from_event(plugin_event, use_linked: bool = False) -> str:
    try:
        raw_bot_hash = safe_str(plugin_event.bot_info.hash).strip() or 'default'
        if use_linked:
            return get_linked_bot_hash(raw_bot_hash)
        return get_config_bot_hash(raw_bot_hash)
    except Exception:
        return 'default'


def get_bot_root_dir() -> str:
    """所有 bot 独立数据统一放在 plugin/data/LanotaPlugin/bot/ 下。"""
    return ensure_folder(os.path.join(config.plugin_data_dir, 'bot'))


def get_bot_config_dir(bot_hash: Any) -> str:
    return ensure_folder(os.path.join(get_bot_root_dir(), get_config_bot_hash(bot_hash)))


def get_bot_config_path(bot_hash: Any) -> str:
    return os.path.join(get_bot_config_dir(bot_hash), config.bot_config_file_name)


def load_global_config() -> dict[str, Any]:
    file_path = get_global_config_path()
    file_exists = os.path.exists(file_path)
    file_data = read_json_file(file_path, config.default_global_config)
    data = merge_dict_with_default(file_data, config.default_global_config)
    data['configured_master_list'] = normalize_id_list(data.get('configured_master_list', []))
    if not file_exists or data != file_data:
        save_json_file(file_path, data)
    return data


def save_global_config(global_config: dict[str, Any]) -> bool:
    data = merge_dict_with_default(global_config, config.default_global_config)
    data['configured_master_list'] = normalize_id_list(data.get('configured_master_list', []))
    return save_json_file(get_global_config_path(), data)


def migrate_configured_master_list_to_global(master_list: Any) -> None:
    legacy_master_list = normalize_id_list(master_list)
    if not legacy_master_list:
        return
    global_config = load_global_config()
    configured_master_list = normalize_id_list(global_config.get('configured_master_list', []))
    changed = False
    for master_id in legacy_master_list:
        if master_id not in configured_master_list:
            configured_master_list.append(master_id)
            changed = True
    if changed:
        global_config['configured_master_list'] = configured_master_list
        save_global_config(global_config)


def load_bot_config(bot_hash: Any) -> dict[str, Any]:
    file_path = get_bot_config_path(bot_hash)
    file_exists = os.path.exists(file_path)
    file_data = read_json_file(file_path, config.default_bot_config)
    if isinstance(file_data, dict) and 'configured_master_list' in file_data:
        migrate_configured_master_list_to_global(file_data.get('configured_master_list', []))
        file_data = dict(file_data)
        file_data.pop('configured_master_list', None)
    data = merge_dict_with_default(file_data, config.default_bot_config)
    data['disabled_group_list'] = normalize_id_list(data.get('disabled_group_list', []))
    if not file_exists or data != file_data:
        save_json_file(file_path, data)
    return data


def save_bot_config(bot_hash: Any, bot_config: dict[str, Any]) -> bool:
    data = merge_dict_with_default(bot_config, config.default_bot_config)
    if 'configured_master_list' in data:
        migrate_configured_master_list_to_global(data.get('configured_master_list', []))
        data.pop('configured_master_list', None)
    data['disabled_group_list'] = normalize_id_list(data.get('disabled_group_list', []))
    return save_json_file(get_bot_config_path(bot_hash), data)


def get_runtime_bot_dir(bot_hash: Any) -> str:
    """获取 linked 运行期目录，用于个人数据等 storage 内容。"""
    return ensure_folder(os.path.join(get_bot_root_dir(), get_linked_bot_hash(bot_hash)))


def get_storage_dir(bot_hash: Any = None) -> str:
    return ensure_folder(os.path.join(get_runtime_bot_dir(bot_hash or 'default'), 'storage'))



def get_user_data_path(bot_hash: Any = None) -> str:
    return os.path.join(get_storage_dir(bot_hash), config.user_data_file_name)





def ensure_user_data_file(bot_hash: Any = None) -> str:
    """确保 bot 个人数据文件存在于 bot/<hash>/storage/ 下。"""
    user_data_path = get_user_data_path(bot_hash)
    if os.path.exists(user_data_path):
        return user_data_path
    save_json_file(user_data_path, {})
    return user_data_path


def get_song_data_dir() -> str:
    return ensure_folder(os.path.join(config.plugin_data_dir, 'SongList'))


def get_song_list_path() -> str:
    return os.path.join(get_song_data_dir(), config.song_list_file_name)


def get_song_alias_path() -> str:
    return os.path.join(get_song_data_dir(), config.song_alias_file_name)


def get_song_table_path() -> str:
    return os.path.join(get_song_data_dir(), config.song_table_file_name)


def get_cover_art_dir() -> str:
    """获取运行期曲绘缓存目录。"""
    return ensure_folder(os.path.join(config.plugin_data_dir, config.cover_art_folder_name))


def get_cover_index_path() -> str:
    """获取曲绘缓存索引文件。"""
    return os.path.join(get_cover_art_dir(), config.cover_index_file_name)


def get_seed_cover_art_dir() -> str:
    """获取随插件源码/安装包发布的预置曲绘目录。"""
    return str(config.asset_data_dir / config.cover_art_folder_name)


def get_seed_cover_index_path() -> str:
    return os.path.join(get_seed_cover_art_dir(), config.cover_index_file_name)


def get_excel_table_dir() -> str:
    return ensure_folder(os.path.join(config.plugin_data_dir, config.excel_table_folder_name))


def get_seed_excel_table_dir() -> Path:
    return config.asset_data_dir / config.excel_table_folder_name


def get_excel_table_file_list() -> list[str]:
    """列出运行期 excel_table 内的普通文件，忽略 Excel 临时锁文件。"""
    table_dir = Path(get_excel_table_dir())
    result = []
    try:
        for item in table_dir.iterdir():
            if item.is_file() and not item.name.startswith('~$'):
                result.append(str(item))
    except Exception:
        return []
    return sorted(result)


def copy_seed_excel_table_if_empty() -> None:
    """首次运行时把随插件携带的 Excel 定数表复制到运行期目录。"""
    try:
        target_dir = Path(get_excel_table_dir())
        if get_excel_table_file_list():
            return
        seed_dir = get_seed_excel_table_dir()
        if not seed_dir.exists():
            return
        seed_files = [
            item
            for item in sorted(seed_dir.iterdir())
            if item.is_file()
            and not item.name.startswith('~$')
            and item.suffix.lower() in config.excel_table_extension_list
        ]
        if seed_files:
            shutil.copy2(seed_files[0], target_dir / seed_files[0].name)
    except Exception:
        return


def get_generate_image_dir() -> str:
    return ensure_folder(os.path.join(config.plugin_data_dir, 'generate_image'))


def get_font_path() -> str:
    return os.path.join(config.plugin_data_dir, config.font_file_name)


def copy_seed_file(seed_path: Path, target_path: str, default_value: Any) -> None:
    try:
        if os.path.exists(target_path):
            return
        ensure_folder(Path(target_path).parent)
        if seed_path.exists():
            shutil.copy2(seed_path, target_path)
        else:
            save_json_file(target_path, default_value)
    except Exception:
        save_json_file(target_path, default_value)


def ensure_runtime_bot_config_files(Proc=None) -> None:
    """初始化时为当前进程已知 bot 预生成 bot_config。"""
    try:
        bot_info_dict = getattr(Proc, 'Proc_data', {}).get('bot_info_dict', {}) if Proc is not None else {}
        for bot_hash in bot_info_dict.keys():
            load_bot_config(bot_hash)
    except Exception:
        pass


def initialize_plugin(Proc=None) -> None:
    """初始化数据目录并复制种子数据。"""
    global initialized
    try:
        ensure_folder(config.plugin_data_dir)
        ensure_folder(get_bot_root_dir())
        ensure_folder(get_storage_dir())
        ensure_folder(get_song_data_dir())
        ensure_folder(get_cover_art_dir())
        ensure_folder(get_excel_table_dir())
        ensure_folder(get_generate_image_dir())
        save_global_config(load_global_config())
        ensure_runtime_bot_config_files(Proc)

        copy_seed_file(config.asset_data_dir / 'SongList' / config.song_list_file_name, get_song_list_path(), [])
        copy_seed_file(config.asset_data_dir / 'SongList' / config.song_alias_file_name, get_song_alias_path(), {})
        copy_seed_file(config.asset_data_dir / 'SongList' / config.song_table_file_name, get_song_table_path(), {})
        copy_seed_excel_table_if_empty()
        copy_seed_file(config.asset_data_dir / config.font_file_name, get_font_path(), {})
        if not os.path.exists(get_user_data_path()):
            save_json_file(get_user_data_path(), {})
        if not initialized:
            info_log(Proc, 'LanotaPlugin 数据目录初始化完成。')
        initialized = True
    except Exception as exception_object:
        error_log(Proc, f'初始化失败：{type(exception_object).__name__}: {exception_object}')


def get_message_text_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.data.message)
    except Exception:
        return ''


def get_sender_id_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.data.user_id)
    except Exception:
        return ''


def get_sender_name_from_event(plugin_event) -> str:
    try:
        sender = getattr(plugin_event.data, 'sender', {})
        if isinstance(sender, dict):
            return safe_str(sender.get('name') or sender.get('nickname') or '')
    except Exception:
        pass
    return ''


def get_group_id_from_event(plugin_event) -> str:
    try:
        return safe_str(getattr(plugin_event.data, 'group_id', '') or '')
    except Exception:
        return ''


def get_platform_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.platform.get('platform', 'unknown'))
    except Exception:
        return 'unknown'


def get_self_id_from_event(plugin_event) -> str:
    try:
        return safe_str(plugin_event.base_info.get('self_id', ''))
    except Exception:
        try:
            return safe_str(plugin_event.bot_info.id)
        except Exception:
            return ''


def strip_reply_segment(message_text: str) -> str:
    return reply_segment_pattern.sub('', safe_str(message_text), count=1)


def parse_at_segments(message_text: str):
    remaining = safe_str(message_text)
    at_list = []
    while True:
        remaining = remaining.lstrip()
        match = at_segment_pattern.match(remaining)
        if not match:
            break
        at_list.append({'id': safe_str(match.group('id')).strip(), 'raw': match.group(0)})
        remaining = remaining[match.end() :]
    return at_list, remaining.lstrip()


def is_force_reply_to_current_bot(at_list: list[dict[str, str]], plugin_event) -> bool:
    self_id = get_self_id_from_event(plugin_event)
    return any(item.get('id') in [self_id, 'all'] for item in at_list)


def parse_prefix(message_text: str, prefix_list: list[str] | None = None):
    source = safe_str(message_text)
    real_prefix_list = config.allowed_prefix_list if prefix_list is None else prefix_list
    for prefix in real_prefix_list:
        if source.startswith(prefix):
            return prefix, source[len(prefix) :].lstrip()
    return '', source


def split_first_token(message_text: str) -> tuple[str, str]:
    source = safe_str(message_text).strip()
    if not source:
        return '', ''
    parts = source.split(None, 1)
    return parts[0], parts[1] if len(parts) > 1 else ''


def parse_command(
    message_text: str,
    prefix_list: list[str] | None = None,
    allow_no_prefix: bool = False,
    command_name: Any = None,
    ignore_case: bool = True,
) -> dict[str, Any]:
    """模板式命令解析。

    传入 command_name 时按长度从长到短贪婪匹配，不要求命令名后存在空格。
    """
    cleaned_text = strip_reply_segment(message_text)
    matched_prefix = ''
    remaining_text = cleaned_text
    if prefix_list is not None and prefix_list:
        matched_prefix, remaining_text = parse_prefix(cleaned_text, prefix_list)
    if prefix_list is not None and not matched_prefix and not allow_no_prefix:
        return {
            'is_command': False,
            'prefix': '',
            'command_name': '',
            'command_argument': '',
            'remaining_text': cleaned_text,
        }

    command_source = remaining_text if matched_prefix else cleaned_text.lstrip()
    command_text = ''
    command_argument = ''

    if command_name is None:
        command_text, command_argument = split_first_token(command_source)
    else:
        command_name_list = [command_name] if isinstance(command_name, str) else list(command_name or [])
        normalized_list = []
        for item in command_name_list:
            raw_name = safe_str(item).strip()
            if not raw_name:
                continue
            normalized_list.append((raw_name, raw_name.lower() if ignore_case else raw_name))

        compare_source = command_source.lower() if ignore_case else command_source
        for raw_name, compare_name in sorted(normalized_list, key=lambda item: len(item[0]), reverse=True):
            if compare_source.startswith(compare_name):
                command_text = raw_name
                command_argument = command_source[len(raw_name) :].lstrip()
                break

    return {
        'is_command': bool(command_text),
        'prefix': matched_prefix,
        'command_name': safe_str(command_text).lower() if ignore_case else safe_str(command_text),
        'command_argument': command_argument,
        'remaining_text': command_source,
    }


def normalize_id_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_list = re.split(r'[\s,;，；]+', value)
    elif isinstance(value, list):
        raw_list = value
    else:
        raw_list = []
    result = []
    for item in raw_list:
        normalized = re.sub(r'[^0-9]', '', safe_str(item))
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def get_configured_master_list(bot_hash: Any = None) -> list[str]:
    return normalize_id_list(load_global_config().get('configured_master_list', []))


def set_configured_master_list(bot_hash: Any, master_list: list[str]) -> bool:
    global_config = load_global_config()
    global_config['configured_master_list'] = normalize_id_list(master_list)
    return save_global_config(global_config)


def sender_is_core_master(plugin_event) -> bool:
    if not has_oliva_dice_core:
        return False
    try:
        user_hash = OlivaDiceCore.userConfig.getUserHash(
            plugin_event.data.user_id,
            'user',
            plugin_event.platform['platform'],
        )
        return bool(OlivaDiceCore.ordinaryInviteManager.isInMasterList(plugin_event.bot_info.hash, user_hash))
    except Exception:
        return False


def sender_has_master_permission(plugin_event) -> bool:
    sender_id = get_sender_id_from_event(plugin_event)
    return sender_is_core_master(plugin_event) or sender_id in get_configured_master_list()


def is_group_owner(plugin_event) -> bool:
    """判断发送者是否是群主。"""
    try:
        return safe_str(plugin_event.data.sender.get('role', '')).lower() == 'owner'
    except Exception:
        return False


def is_group_admin(plugin_event) -> bool:
    """判断发送者是否是群主或群管。"""
    try:
        return safe_str(plugin_event.data.sender.get('role', '')).lower() in ['owner', 'admin', 'sub_admin']
    except Exception:
        return False


def sender_has_group_management_permission(plugin_event) -> bool:
    """群级管理权限：插件管理员、骰主、群主或群管。"""
    return sender_has_master_permission(plugin_event) or is_group_admin(plugin_event)


def get_disabled_group_list(bot_hash: Any) -> list[str]:
    """获取当前原始 bot 的群禁用列表。"""
    return normalize_id_list(load_bot_config(bot_hash).get('disabled_group_list', []))


def set_disabled_group_list(bot_hash: Any, group_id_list: list[str]) -> bool:
    """保存当前原始 bot 的群禁用列表。"""
    bot_config = load_bot_config(bot_hash)
    bot_config['disabled_group_list'] = normalize_id_list(group_id_list)
    return save_bot_config(bot_hash, bot_config)


def is_group_disabled(plugin_event) -> bool:
    """检查当前群是否已在本插件中禁用。"""
    group_id = get_group_id_from_event(plugin_event)
    if not group_id:
        return False
    return group_id in get_disabled_group_list(get_bot_hash_from_event(plugin_event))


def add_disabled_group(bot_hash: Any, group_id: Any) -> bool:
    disabled_group_list = get_disabled_group_list(bot_hash)
    target_group_list = normalize_id_list([group_id])
    changed = False
    for target_group in target_group_list:
        if target_group not in disabled_group_list:
            disabled_group_list.append(target_group)
            changed = True
    if changed:
        return set_disabled_group_list(bot_hash, disabled_group_list)
    return True


def remove_disabled_group(bot_hash: Any, group_id: Any) -> bool:
    disabled_group_list = get_disabled_group_list(bot_hash)
    target_group_list = normalize_id_list([group_id])
    new_group_list = [item for item in disabled_group_list if item not in target_group_list]
    return set_disabled_group_list(bot_hash, new_group_list)


def is_group_message(plugin_event) -> bool:
    return bool(get_group_id_from_event(plugin_event))


def is_alias_group_allowed(plugin_event) -> bool:
    group_id = get_group_id_from_event(plugin_event)
    if not group_id:
        return False
    return group_id in normalize_id_list(load_global_config().get('alias_groups', []))


def check_core_group_enable(plugin_event) -> bool:
    if not has_oliva_dice_core or not get_group_id_from_event(plugin_event):
        return True
    try:
        group_enable = OlivaDiceCore.userConfig.getUserConfigByKey(
            userId=get_group_id_from_event(plugin_event),
            userType='group',
            platform=plugin_event.platform['platform'],
            userConfigKey='groupEnable',
            botHash=plugin_event.bot_info.hash,
        )
        return bool(group_enable)
    except Exception:
        return True


def op_escape(value: Any) -> str:
    return safe_str(value).replace('&', '&amp;').replace('[', '&#91;').replace(']', '&#93;').replace(',', '&#44;')


def reply_message(plugin_event, message_text: str) -> Any:
    try:
        return plugin_event.reply(safe_str(message_text))
    except Exception:
        return None


def reply_image(plugin_event, image_path: str, fallback_text: str) -> Any:
    try:
        file_uri = Path(image_path).resolve().as_uri()
        return plugin_event.reply(f'[OP:image,file={op_escape(file_uri)}]')
    except Exception:
        return reply_message(plugin_event, fallback_text)


def reply_images_with_text(plugin_event, image_path_list: list[str], message_text: str = '') -> Any:
    """在一条 olivos_string 消息中发送多张本地图片，并可附带文本。"""
    segment_list = []
    for image_path in image_path_list:
        if not image_path or not os.path.isfile(image_path):
            continue
        file_uri = Path(image_path).resolve().as_uri()
        segment_list.append(f'[OP:image,file={op_escape(file_uri)}]')
    if message_text:
        segment_list.append(f'\n{safe_str(message_text)}')
    if not segment_list:
        return reply_message(plugin_event, message_text)
    try:
        return plugin_event.reply(''.join(segment_list))
    except Exception:
        return reply_message(plugin_event, message_text)


def split_text_by_line(message_text: str, max_chars: int = 1000) -> list[str]:
    """按行切分长文本，避免纯文本消息过长。"""
    source = safe_str(message_text).strip()
    if not source:
        return []

    chunk_list = []
    current_lines = []
    current_length = 0
    for raw_line in source.splitlines():
        line = raw_line.rstrip()
        line_length = len(line) + 1
        if current_lines and current_length + line_length > max_chars:
            chunk_list.append('\n'.join(current_lines).strip())
            current_lines = []
            current_length = 0
        if len(line) > max_chars:
            if current_lines:
                chunk_list.append('\n'.join(current_lines).strip())
                current_lines = []
                current_length = 0
            for start in range(0, len(line), max_chars):
                chunk_list.append(line[start : start + max_chars])
            continue
        current_lines.append(line)
        current_length += line_length
    if current_lines:
        chunk_list.append('\n'.join(current_lines).strip())
    return [chunk for chunk in chunk_list if chunk]


def create_forward_node(plugin_event, content: str) -> dict[str, Any]:
    bot_id = safe_str(getattr(getattr(plugin_event, 'bot_info', None), 'id', '')).strip() or '0'
    return {
        'type': 'node',
        'data': {
            'user_id': bot_id,
            'nickname': config.plugin_name,
            'content': safe_str(content),
        },
    }


def send_forward_messages(plugin_event, message_list: list[str]) -> bool:
    """QQ 环境优先使用合并转发，接口不可用时返回 False。"""
    if get_platform_from_event(plugin_event).lower() != 'qq':
        return False

    forward_messages = [create_forward_node(plugin_event, message_text) for message_text in message_list if message_text]
    if not forward_messages:
        return False

    group_id = get_group_id_from_event(plugin_event)
    try:
        if group_id and hasattr(plugin_event, 'send_group_forward_msg'):
            plugin_event.send_group_forward_msg(group_id, forward_messages)
            return True
        if hasattr(plugin_event, 'send_private_forward_msg'):
            plugin_event.send_private_forward_msg(get_sender_id_from_event(plugin_event), forward_messages)
            return True
    except Exception:
        return False
    return False


def reply_long_plain_text(plugin_event, message_text: str, max_chars: int = 1000) -> None:
    chunk_list = split_text_by_line(message_text, max_chars=max_chars)
    if not chunk_list:
        return
    if len(chunk_list) > 1 and send_forward_messages(plugin_event, chunk_list):
        return
    for chunk in chunk_list:
        reply_message(plugin_event, chunk)
