# -*- encoding: utf-8 -*-
"""
公共方法模块。

这个文件承担插件模板里绝大多数“可复用能力”，包括：

1. 日志输出封装。
2. 插件初始化与分 bot 数据目录初始化。
3. 群链辅助方法。
4. 前缀、命令、at 解析。
5. 回复封装，并提供“是否主动写入 OlivaDiceLogger”开关。
6. 通用文件/文件夹读写封装。
7. 权限相关辅助方法，例如骰主、群主、群管识别。
8. 在存在 OlivaDiceCore 时，检查当前群是否处于 bot on/off 可用状态。
"""

import OlivOS
import copy
import json
import os
import re
import threading
import traceback
from functools import wraps
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import config
from . import message_custom

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


def safe_str(value: Any) -> str:
    """
    尽量把任意对象安全转成字符串。
    模板里很多值来自 OlivOS 事件对象。为了避免某些协议端字段缺失时抛异常，
    这里统一做一个轻量级兜底转换。
    """
    try:
        return str(value)
    except Exception:
        return ''


def deep_copy_default(default_value: Any) -> Any:
    """对默认值做深拷贝，避免把模块级默认字典直接改脏。"""
    return copy.deepcopy(default_value)


def merge_dict_with_default(source_dict: Any, default_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    用默认值补齐配置缺失字段。

    这个行为在模板里很重要，因为用户手动改配置文件时，可能删除某些字段。
    我们在读取时自动补齐，模板就不会因为老配置缺少新字段而直接崩掉。
    """
    merged_dict = deep_copy_default(default_dict)
    if isinstance(source_dict, dict):
        for key, value in source_dict.items():
            merged_dict[key] = value
    return merged_dict


def ensure_folder(folder_path: str) -> str:
    """确保目录存在，并返回该目录路径。"""
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def list_folder_entries(
    folder_path: str,
    only_file: bool = False,
    only_folder: bool = False,
) -> List[str]:
    """
    读取目录内容。

    这个封装给模板使用者一个统一入口，避免未来想换成更复杂的过滤逻辑时，
    还得在各个业务模块里到处改 os.listdir。
    """
    if not os.path.exists(folder_path):
        return []

    entry_list = []
    for entry_name in os.listdir(folder_path):
        entry_path = os.path.join(folder_path, entry_name)
        if only_file and not os.path.isfile(entry_path):
            continue
        if only_folder and not os.path.isdir(entry_path):
            continue
        entry_list.append(entry_name)
    return sorted(entry_list)


def read_json_file(file_path: str, default_value: Any) -> Any:
    """
    读取 JSON 文件，失败时返回默认值。

    这里不直接把异常抛给业务层，是因为模板更重视“先稳定跑起来”。
    真正要查错时，会通过 error_log 输出详细信息。
    """
    if not os.path.exists(file_path):
        return deep_copy_default(default_value)

    with file_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as file_object:
                return json.load(file_object)
        except Exception:
            return deep_copy_default(default_value)


def save_json_file(file_path: str, data: Any) -> bool:
    """保存 JSON 文件，成功返回 True。"""
    with file_lock:
        try:
            ensure_folder(os.path.dirname(file_path))
            with open(file_path, 'w', encoding='utf-8') as file_object:
                json.dump(data, file_object, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False


def read_text_file(file_path: str, default_value: str = '') -> str:
    """读取纯文本文件。"""
    if not os.path.exists(file_path):
        return default_value

    with file_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as file_object:
                return file_object.read()
        except Exception:
            return default_value


def save_text_file(file_path: str, text_content: str) -> bool:
    """保存纯文本文件。"""
    with file_lock:
        try:
            ensure_folder(os.path.dirname(file_path))
            with open(file_path, 'w', encoding='utf-8') as file_object:
                file_object.write(text_content)
            return True
        except Exception:
            return False


def log_message(Proc, log_level: int, level_name: str, message_text: str) -> None:
    """
    底层日志输出函数。

    这里尽量贴近 OlivOS 的 Proc.log 调用习惯：
    - info 和 debug 走正常输出。
    - error 仅用于错误日志。
    - 如果当前环境拿不到 Proc，则退化为 print，保证模板在脱离 OlivOS 单测时也能看日志。
    """
    full_message = f'[{config.plugin_name}][{level_name}] {safe_str(message_text)}'
    if Proc is not None and hasattr(Proc, 'log'):
        try:
            Proc.log(log_level, full_message, [])
            return
        except Exception:
            pass
    print(full_message)


def debug_log(Proc, message_text: str, plugin_event=None, bot_hash: Optional[str] = None) -> None:
    """
    Debug 级日志。

    调试模式开关属于所有 bot 共用的全局配置。
    因此这里虽然保留 bot_hash 参数以兼容旧调用，但实际判断只读取
    plugin/data/CyberGladiator/global_config.json 这一份共享配置。
    """
    global_config = load_global_config()
    if global_config.get('global_debug_mode_switch', False):
        log_message(Proc, 2, 'DEBUG', message_text)


def info_log(Proc, message_text: str) -> None:
    """Info 级日志，直接输出。"""
    log_message(Proc, 2, 'INFO', message_text)


def error_log(Proc, message_text: str) -> None:
    """Error 级日志，仅用于错误输出。"""
    log_message(Proc, 3, 'ERROR', message_text)


def log_exception(action_name: str):
    """
    异常拦截装饰器。

    模板里常见的事件处理函数几乎都接受 (plugin_event, Proc) 作为前两个参数。
    这个装饰器会自动尝试抓取 Proc，并把异常写到 error_log 中，方便模板使用者
    在需要时直接复用。
    """

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
                    f'{action_name} 执行失败：{type(exception_object).__name__}: '
                    f'{safe_str(exception_object)}\n{traceback.format_exc()}',
                )
                return None

        return wrapper

    return decorator


def set_runtime_proc(Proc) -> None:
    """
    缓存当前运行期 Proc。

    Proc 在插件 init 阶段确定后就不会再变化，
    因此只需要在 init 时全局缓存一次即可。
    """
    global runtime_proc
    if Proc is not None:
        runtime_proc = Proc


def get_runtime_proc():
    """获取当前缓存的运行期 Proc。"""
    return runtime_proc


def get_linked_bot_hash(bot_hash: Any) -> str:
    """
    按照 OlivaDiceCore 的 bot 群链规则，获取真正用于读写配置的 bot hash。

    为什么模板要做这一步：
    1. 用户可能把多个 bot 账号链接到同一个主 bot。
    2. 这时配置如果还按原始 bot hash 各存一份，会出现配置割裂。
    3. 因此模板统一把配置目录落到“群链后的 bot hash”上。
    """
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
    """
    获取当前 bot 的原始配置 hash。

    当前模板里，bot_config.json 仍按原始 bot 单独保存，
    不跟随 linked_bot_hash。
    """
    return safe_str(bot_hash).strip() or 'default'


def get_reply_runtime_bot_hash(bot_hash: Any) -> str:
    """获取运行期用于读取 linked 目录数据的 linked_bot_hash。"""
    return get_linked_bot_hash(bot_hash)


def get_bot_hash_from_event(plugin_event, use_linked: bool = False) -> str:
    """
    从事件对象中获取当前 bot 的 hash。

    参数说明：
    - use_linked=False：返回原始 bot hash，用于 bot_config.json。
    - use_linked=True：返回 linked_bot_hash，用于 configured_master_list、storage、
      message_custom.json、message_variable.json。
    """
    try:
        raw_bot_hash = plugin_event.bot_info.hash
        if use_linked:
            return get_reply_runtime_bot_hash(raw_bot_hash)
        return get_config_bot_hash(raw_bot_hash)
    except Exception:
        return 'default'


def get_raw_bot_hash_from_event(plugin_event) -> str:
    """从事件对象中获取原始 bot hash。"""
    try:
        return safe_str(plugin_event.bot_info.hash)
    except Exception:
        return 'default'


def get_bot_id_from_event(plugin_event) -> str:
    """从事件对象中获取 bot_id。"""
    try:
        return safe_str(plugin_event.bot_info.id)
    except Exception:
        return ''


def get_self_id_from_event(plugin_event) -> str:
    """拿到当前 bot 的 self_id，主要用于 at 判定。"""
    try:
        return safe_str(plugin_event.base_info.get('self_id', ''))
    except Exception:
        return get_bot_id_from_event(plugin_event)


def get_sender_id_from_event(plugin_event) -> str:
    """获取发送者 user_id。"""
    try:
        return safe_str(plugin_event.data.user_id)
    except Exception:
        return ''


def get_sender_name_from_event(plugin_event) -> str:
    """获取发送者昵称。"""
    try:
        return safe_str(plugin_event.data.sender.get('name', ''))
    except Exception:
        return ''


def get_host_id_from_event(plugin_event) -> str:
    """获取 host_id。没有时返回空字符串。"""
    try:
        return safe_str(getattr(plugin_event.data, 'host_id', '') or '')
    except Exception:
        return ''


def get_group_id_from_event(plugin_event) -> str:
    """获取 group_id。没有时返回空字符串。"""
    try:
        return safe_str(getattr(plugin_event.data, 'group_id', '') or '')
    except Exception:
        return ''


def get_message_text_from_event(plugin_event) -> str:
    """获取当前事件的原始消息字符串。"""
    try:
        return safe_str(plugin_event.data.message)
    except Exception:
        return ''


def get_config_bot_root_dir(bot_hash: Any) -> str:
    """
    获取某个 bot 的原始配置目录。

    这个目录用于保存：
    - bot_config.json

    当前模板里，只有 bot_config.json 仍固定保存在原始 bot 目录。
    """
    folder_bot_hash = get_config_bot_hash(bot_hash)
    return ensure_folder(os.path.join(config.plugin_data_dir, folder_bot_hash))


def get_reply_bot_root_dir(bot_hash: Any) -> str:
    """
    获取运行期用于读取 linked 数据的目录。

    当前模板里，这个目录会按 linked_bot_hash 折叠，统一保存：
    - storage/
    - message_custom.json
    - message_variable.json

    但 bot_config.json 和 configured_master_list 不在这里，
    它们仍保存在原始 bot 目录。
    """
    folder_bot_hash = get_reply_runtime_bot_hash(bot_hash)
    return ensure_folder(os.path.join(config.plugin_data_dir, folder_bot_hash))


def get_bot_root_dir(bot_hash: Any) -> str:
    """兼容旧调用，返回当前 bot 的 linked 目录。"""
    return get_reply_bot_root_dir(bot_hash)


def get_raw_bot_root_dir(bot_hash: Any) -> str:
    """兼容旧调用，返回当前 bot 的原始配置目录。"""
    return get_config_bot_root_dir(bot_hash)


def get_storage_dir(bot_hash: Any) -> str:
    """
    获取某个 bot 的通用存储目录。

    当前模板里，storage 跟随 linked_bot_hash。
    """
    return ensure_folder(os.path.join(get_reply_bot_root_dir(bot_hash), config.storage_folder_name))


def ensure_raw_bot_init_folder(bot_hash: Any) -> str:
    """
    为原始 bot hash 预先建立初始化目录。

    当前只负责 bot_config 所在的原始目录。
    """
    raw_bot_root_dir = get_config_bot_root_dir(bot_hash)
    return raw_bot_root_dir


def get_global_config_file_path(bot_hash: Any = None) -> str:
    """
    获取全局配置文件路径。

    这里的“全局”就是整个插件所有 bot 共用的一份全局配置。
    为了兼容旧调用，函数仍然保留 bot_hash 形参，但该参数不会参与路径计算。
    """
    ensure_folder(config.plugin_data_dir)
    return os.path.join(config.plugin_data_dir, config.global_config_file_name)


def get_bot_config_file_path(bot_hash: Any) -> str:
    """
    获取 bot 配置文件路径。

    这个文件只保存 bot 自己的基础开关信息。
    当前模板里，它不跟随 linked_bot_hash。
    """
    return os.path.join(get_config_bot_root_dir(bot_hash), config.bot_config_file_name)


def get_message_custom_file_path(bot_hash: Any) -> str:
    """
    获取自定义回复词文件路径。

    回复词文件在模板里会按 linked_bot_hash 生效。
    这意味着主从 bot 会自动读取主账号目录中的自定义回复。
    """
    return os.path.join(get_reply_bot_root_dir(bot_hash), config.message_custom_file_name)


def get_message_variable_file_path(bot_hash: Any) -> str:
    """
    获取自定义变量文件路径。

    变量文件和回复词文件保持同一套 linked_bot_hash 路径，
    方便一套回复词与其变量同时被主从 bot 共用。
    """
    return os.path.join(get_reply_bot_root_dir(bot_hash), config.message_variable_file_name)


def load_global_config(bot_hash: Any = None) -> Dict[str, Any]:
    """
    读取全局配置。

    读取后会自动用默认结构补齐字段，避免老配置缺少新字段时直接报错。
    这份配置对所有 bot 共用。
    """
    file_path = get_global_config_file_path(bot_hash)
    file_data = read_json_file(file_path, config.default_global_config)
    return merge_dict_with_default(file_data, config.default_global_config)


def save_global_config(global_config: Dict[str, Any], bot_hash: Any = None) -> bool:
    """
    保存全局配置。

    保存前同样先做一次默认结构补齐，防止调用方误传不完整字典。
    这里写入的是所有 bot 共用的一份 global_config.json。
    """
    final_config = merge_dict_with_default(global_config, config.default_global_config)
    return save_json_file(get_global_config_file_path(), final_config)


def load_bot_config(bot_hash: Any) -> Dict[str, Any]:
    """
    读取 bot 配置。

    这里除了补齐默认字段外，还会把 configured_master_list 统一清洗成
    只包含数字字符串、且不重复的列表。
    """
    file_path = get_bot_config_file_path(bot_hash)
    file_data = read_json_file(file_path, config.default_bot_config)
    merged_config = merge_dict_with_default(file_data, config.default_bot_config)
    merged_config['configured_master_list'] = normalize_id_list(merged_config.get('configured_master_list', []))
    return merged_config


def save_bot_config(bot_hash: Any, bot_config: Dict[str, Any]) -> bool:
    """
    保存 bot 配置。

    模板要求 bot_config 与 configured_master_list 都按原始 bot 隔离，
    这个函数就是它们的统一持久化出口。
    """
    final_config = merge_dict_with_default(bot_config, config.default_bot_config)
    for legacy_key in ['bot_id', 'bot_hash', 'raw_bot_hash']:
        final_config.pop(legacy_key, None)
    final_config.pop('victory_speech_prompt', None)
    final_config['configured_master_list'] = normalize_id_list(final_config.get('configured_master_list', []))
    return save_json_file(get_bot_config_file_path(bot_hash), final_config)


def load_bot_message_custom(bot_hash: Any) -> Dict[str, str]:
    """
    读取当前 bot 的自定义回复词。

    这里会读取 linked_bot_hash 对应目录中的回复词文件。
    这些文件在初始化阶段就会被准备好，因此正常情况下会直接读取
    对应 bot_hash 目录中的文件内容。
    """
    file_path = get_message_custom_file_path(bot_hash)
    file_data = read_json_file(file_path, message_custom.default_custom_message_dict)
    return merge_dict_with_default(file_data, message_custom.default_custom_message_dict)


def save_bot_message_custom(bot_hash: Any, custom_message_dict: Dict[str, str]) -> bool:
    """保存当前 bot 的自定义回复词。"""
    final_dict = merge_dict_with_default(custom_message_dict, message_custom.default_custom_message_dict)
    return save_json_file(get_message_custom_file_path(bot_hash), final_dict)


def load_bot_message_variables(bot_hash: Any) -> Dict[str, str]:
    """读取当前 bot 的自定义变量。"""
    file_path = get_message_variable_file_path(bot_hash)
    file_data = read_json_file(file_path, message_custom.default_custom_variable_dict)
    return merge_dict_with_default(file_data, message_custom.default_custom_variable_dict)


def save_bot_message_variables(bot_hash: Any, variable_dict: Dict[str, str]) -> bool:
    """保存当前 bot 的自定义变量。"""
    final_dict = merge_dict_with_default(variable_dict, message_custom.default_custom_variable_dict)
    return save_json_file(get_message_variable_file_path(bot_hash), final_dict)


def get_bot_message_key_list(bot_hash: Any) -> List[str]:
    """
    获取当前 bot 可编辑的自定义回复词 key 列表。

    这里会合并三部分来源：
    1. 模板默认内置的回复词 key。
    2. 说明字典里存在的 key。
    3. 当前 bot 已经保存过的自定义 key。

    这样 GUI 无论面对“模板自带词条”还是“用户后续扩展词条”，都能把它们列出来。
    """
    key_set = set(message_custom.default_custom_message_dict.keys())
    key_set.update(message_custom.custom_message_note_dict.keys())
    key_set.update(load_bot_message_custom(bot_hash).keys())
    return sorted(key_set)


def get_message_note_text(message_key: str) -> str:
    """获取某个回复词 key 在 GUI 中显示的说明文本。"""
    return safe_str(message_custom.custom_message_note_dict.get(message_key, '这个回复词当前没有额外说明。'))


def set_bot_message_custom_value(bot_hash: Any, message_key: str, message_text: str) -> bool:
    """设置当前 bot 某一条自定义回复词。"""
    custom_message_dict = load_bot_message_custom(bot_hash)
    custom_message_dict[safe_str(message_key)] = safe_str(message_text)
    return save_bot_message_custom(bot_hash, custom_message_dict)


def reset_bot_message_custom_value(bot_hash: Any, message_key: str) -> bool:
    """
    把当前 bot 某一条自定义回复词重置为模板默认值。

    如果该 key 不在模板默认回复词里，则重置为空字符串，
    让模板使用者能明显看到这个词条还没有给出默认文本。
    """
    custom_message_dict = load_bot_message_custom(bot_hash)
    if message_key in message_custom.default_custom_message_dict:
        custom_message_dict[message_key] = message_custom.default_custom_message_dict[message_key]
    else:
        custom_message_dict[message_key] = ''
    return save_bot_message_custom(bot_hash, custom_message_dict)


def initialize_bot_storage(bot_hash: Any, bot_id: Any = '') -> Dict[str, Any]:
    """
    初始化单个 bot 的目录与配置文件。

    每次 bot 首次出现时，会把必要的初始化文件都准备好：
    - 原始 bot 目录中的 bot_config.json
    - 解析后的 linked_bot_hash 目录中的 storage/
    - 解析后的 linked_bot_hash 目录中的 message_custom.json
    - 解析后的 linked_bot_hash 目录中的 message_variable.json
    """
    config_bot_hash = get_config_bot_hash(bot_hash)
    reply_bot_hash = get_reply_runtime_bot_hash(bot_hash)
    ensure_folder(config.plugin_data_dir)
    if not os.path.exists(get_global_config_file_path()):
        save_global_config(config.default_global_config)

    ensure_folder(get_config_bot_root_dir(config_bot_hash))
    ensure_folder(get_reply_bot_root_dir(reply_bot_hash))
    ensure_folder(get_storage_dir(reply_bot_hash))
    ensure_folder(get_reply_bot_root_dir(reply_bot_hash))

    bot_config = load_bot_config(config_bot_hash)
    save_bot_config(config_bot_hash, bot_config)

    if not os.path.exists(get_message_custom_file_path(reply_bot_hash)):
        save_bot_message_custom(reply_bot_hash, message_custom.default_custom_message_dict)

    if not os.path.exists(get_message_variable_file_path(reply_bot_hash)):
        save_bot_message_variables(reply_bot_hash, message_custom.default_custom_variable_dict)

    return {
        'bot_id': safe_str(bot_id),
        'config_bot_hash': safe_str(config_bot_hash),
        'reply_bot_hash': safe_str(reply_bot_hash),
    }


def initialize_plugin(Proc) -> None:
    """
    初始化整个插件的数据目录。

    OlivOS 在 init 阶段通常会把 bot_info_dict 放在 Proc.Proc_data 中。
    模板在这里把所有 bot 的目录预先建立好，后续 message.py 读取配置时
    就不会遇到“目录还没创建”的问题。
    """
    ensure_folder(config.plugin_data_dir)

    bot_info_dict = {}
    try:
        bot_info_dict = getattr(Proc, 'Proc_data', {}).get('bot_info_dict', {})
    except Exception:
        bot_info_dict = {}

    if not isinstance(bot_info_dict, dict):
        info_log(Proc, '初始化时未获取到可用的 bot_info_dict，跳过批量目录初始化。')
        return

    for raw_bot_hash, bot_info in bot_info_dict.items():
        bot_id = getattr(bot_info, 'id', '')
        runtime_info = initialize_bot_storage(raw_bot_hash, bot_id=bot_id)
        info_log(
            Proc,
            f'已初始化 bot 目录：bot_id={runtime_info["bot_id"]} '
            f'config_bot_hash={runtime_info["config_bot_hash"]} '
            f'reply_bot_hash={runtime_info["reply_bot_hash"]}',
        )


def ensure_runtime_storage_by_event(plugin_event, Proc=None) -> str:
    """按当前事件确保当前 bot 的目录已初始化。"""
    raw_bot_hash = get_raw_bot_hash_from_event(plugin_event)
    bot_id = get_bot_id_from_event(plugin_event)
    runtime_info = initialize_bot_storage(raw_bot_hash, bot_id=bot_id)
    debug_log(
        Proc,
        f'已确认当前事件目录可用：config={runtime_info["config_bot_hash"]} '
        f'reply={runtime_info["reply_bot_hash"]}',
        plugin_event=plugin_event,
    )
    return runtime_info['config_bot_hash']


def build_hag_id(host_id: Any, group_id: Any) -> str:
    """
    构建 hag_id。

    这里的 hag_id 指的是 host_id|group_id 这一组标识。
    在 OlivaDice 相关插件里，很多群级配置都使用这个形式作为 key：

    1. 如果消息来自带 host 的场景，则使用 host_id|group_id。
    2. 如果消息来自普通群场景，则直接使用 group_id。

    因此它是“群上下文标识”，不是 bot 群链。
    """
    safe_host_id = safe_str(host_id).strip()
    safe_group_id = safe_str(group_id).strip()
    if not safe_group_id:
        return ''
    if safe_host_id:
        return f'{safe_host_id}|{safe_group_id}'
    return safe_group_id


def split_hag_id(hag_id: str) -> Tuple[str, str]:
    """把 hag_id 拆回 host_id 与 group_id。"""
    if '|' in safe_str(hag_id):
        host_id, group_id = safe_str(hag_id).split('|', 1)
        return host_id, group_id
    return '', safe_str(hag_id)


def get_hag_id_from_event(plugin_event) -> str:
    """从事件对象中直接构建当前 hag_id。"""
    return build_hag_id(get_host_id_from_event(plugin_event), get_group_id_from_event(plugin_event))


def strip_reply_segment(message_text: str) -> str:
    """
    去掉消息开头的 [OP:reply,id=xxx]。

    模板的命令解析不应被回复头干扰，因此这里先统一做一次剥离。
    """
    return reply_segment_pattern.sub('', safe_str(message_text), count=1)


def parse_prefix(message_text: str, prefix_list: Optional[Iterable[str]] = None) -> Tuple[str, str]:
    """
    解析前缀。

    返回值是 (命中的前缀, 去掉前缀后的剩余字符串)。
    如果没有命中前缀，则前缀返回空字符串，剩余字符串返回原文。
    """
    source_text = safe_str(message_text)
    real_prefix_list = list(prefix_list or config.allowed_prefix_list)
    for prefix_text in real_prefix_list:
        if source_text.startswith(prefix_text):
            return prefix_text, source_text[len(prefix_text) :].lstrip()
    return '', source_text


def split_first_token(message_text: str) -> Tuple[str, str]:
    """
    从字符串头部切出第一个 token。

    例如：
    'abc def ghi' -> ('abc', 'def ghi')
    'abc' -> ('abc', '')
    '' -> ('', '')
    """
    stripped_text = safe_str(message_text).lstrip()
    if not stripped_text:
        return '', ''
    token_list = stripped_text.split(None, 1)
    first_token = token_list[0]
    remaining_text = token_list[1] if len(token_list) > 1 else ''
    return first_token, remaining_text


def parse_command(
    message_text: str,
    prefix_list: Optional[Iterable[str]] = None,
    allow_no_prefix: bool = False,
    command_name: Any = None,
    ignore_case: bool = True,
) -> Dict[str, Any]:
    """
    解析命令。

    默认行为是把命令头切成“第一个 token + 剩余参数”。
    如果传入 command_name：
    - 可以是单个字符串，也可以是字符串列表。
    - 会按长度从长到短做贪婪匹配。
    - 命中后把右侧剩余部分作为 command_argument 返回。

    例如：
    - command_name=['clear', 'clea'] 时，'clear ab' 会先命中 clear。
    - 同样地，'clea ab' 也能正确命中 clea。
    """
    cleaned_text = strip_reply_segment(message_text)
    matched_prefix, remaining_text = parse_prefix(cleaned_text, prefix_list)

    if not matched_prefix and not allow_no_prefix:
        return {
            'is_command': False,
            'prefix': '',
            'command_name': '',
            'command_argument': '',
            'remaining_text': cleaned_text,
        }

    command_source = remaining_text if matched_prefix else cleaned_text.lstrip()
    command_name_text = ''
    command_argument = ''

    if command_name is None:
        command_name_text, command_argument = split_first_token(command_source)
    else:
        compare_source = command_source.lower() if ignore_case else command_source
        command_name_list = [command_name] if isinstance(command_name, str) else list(command_name or [])
        normalized_name_list = []
        for command_item in command_name_list:
            raw_command_name = safe_str(command_item).strip()
            if raw_command_name == '':
                continue
            compare_command_name = raw_command_name.lower() if ignore_case else raw_command_name
            normalized_name_list.append((raw_command_name, compare_command_name))

        for raw_command_name, compare_command_name in sorted(
            normalized_name_list,
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if len(compare_source) < len(compare_command_name):
                continue
            if compare_source[: len(compare_command_name)] != compare_command_name:
                continue
            command_name_text = raw_command_name
            command_argument = command_source[len(raw_command_name) :].lstrip()
            break

    return {
        'is_command': bool(command_name_text),
        'prefix': matched_prefix,
        'command_name': safe_str(command_name_text).lower(),
        'command_argument': command_argument,
        'remaining_text': command_source,
    }


def parse_at_segments(message_text: str, allow_multi: bool = True) -> Tuple[List[Dict[str, str]], str]:
    """
    解析开头连续出现的 at 段。

    这是用户特别指定的行为：
    - 只从当前字符串起始位置往后解析。
    - 支持多 at，可通过 allow_multi 开关控制。
    - 一旦遇到第一个“不是 at 的内容”，立即停止。
    - 返回值为 (at 列表, 剩余字符串)，两者都可能为空。

    这里默认按 compatible_svn 190+、message_mode 为 olivos_string 的 OP 码处理，
    因此识别的是 [OP:at,id=xxx,name=xxx] 或 [OP:at,id=xxx]。
    """
    remaining_text = safe_str(message_text)
    at_item_list: List[Dict[str, str]] = []

    while True:
        remaining_text = remaining_text.lstrip()
        matched_at = at_segment_pattern.match(remaining_text)
        if not matched_at:
            break

        at_item_list.append(
            {
                'id': safe_str(matched_at.group('id')).strip(),
                'name': safe_str(matched_at.group('name')).strip(),
                'raw': matched_at.group(0),
            }
        )
        remaining_text = remaining_text[matched_at.end() :]
        if not allow_multi:
            break

    return at_item_list, remaining_text.lstrip()


def is_force_reply_to_current_bot(at_item_list: List[Dict[str, str]], plugin_event) -> bool:
    """
    判断解析出的 at 列表里是否包含当前 bot 或 all。

    这类判断通常用于“前置 at 时，只允许 at 到当前 bot / all 的消息继续进入命令解析”。
    """
    self_id = get_self_id_from_event(plugin_event)
    for at_item in at_item_list:
        target_id = safe_str(at_item.get('id', ''))
        if target_id in [self_id, 'all']:
            return True
    return False


def normalize_id_list(id_iterable: Any) -> List[str]:
    """把用户输入的各种 id 列表统一清洗成去重后的字符串列表。"""
    if isinstance(id_iterable, str):
        raw_item_list = re.split(r'[\s,;，；]+', id_iterable)
    elif isinstance(id_iterable, list):
        raw_item_list = id_iterable
    else:
        raw_item_list = []

    normalized_id_list = []
    for raw_item in raw_item_list:
        normalized_id = re.sub(r'[^0-9]', '', safe_str(raw_item))
        if normalized_id and normalized_id not in normalized_id_list:
            normalized_id_list.append(normalized_id)
    return normalized_id_list


def get_configured_master_list(bot_hash: Any) -> List[str]:
    """获取当前 bot 的本插件配置骰主列表。"""
    bot_config = load_bot_config(bot_hash)
    return normalize_id_list(bot_config.get('configured_master_list', []))


def set_configured_master_list(bot_hash: Any, master_id_list: Iterable[str]) -> bool:
    """保存当前 bot 的本插件配置骰主列表。"""
    bot_config = load_bot_config(bot_hash)
    bot_config['configured_master_list'] = normalize_id_list(list(master_id_list))
    return save_bot_config(bot_hash, bot_config)


def is_sender_configured_master(plugin_event) -> bool:
    """判断发送者是否属于当前 bot 的本插件配置骰主。"""
    sender_id = get_sender_id_from_event(plugin_event)
    config_bot_hash = get_bot_hash_from_event(plugin_event)
    return sender_id in get_configured_master_list(config_bot_hash)


def is_sender_core_master(plugin_event) -> bool:
    """
    判断发送者是否属于 OlivaDiceCore 骰主。

    这里用的是 ordinaryInviteManager.isInMasterList，
    这是模板里最稳妥、最常见的判定方式。
    """
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


def get_master_permission_info(plugin_event) -> Dict[str, Any]:
    """
    获取骰主权限信息。

    这个函数不只判断“是不是骰主”，还会把两类来源拆开返回：
    - OlivaDiceCore 骰主
    - 本插件配置骰主

    这样模板使用者后续扩展权限时，就不会把两套权限来源混在一起。
    """
    configured_master_list = get_configured_master_list(get_bot_hash_from_event(plugin_event))
    sender_is_core_master = is_sender_core_master(plugin_event)
    sender_is_configured_master = is_sender_configured_master(plugin_event)
    return {
        'configured_master_list': configured_master_list,
        'sender_is_core_master': sender_is_core_master,
        'sender_is_configured_master': sender_is_configured_master,
        'sender_is_master': sender_is_core_master or sender_is_configured_master,
    }


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


def check_core_group_enable(plugin_event) -> bool:
    """
    在存在 OlivaDiceCore 时，检查当前上下文是否允许 bot 工作。

    这里采用与你提供的 MusicSearch 思路相同的轻量规则：
    - host 场景检查 hostLocalEnable
    - group 场景检查 groupEnable
    - 没有 OlivaDiceCore 时直接放行
    """
    if not has_oliva_dice_core:
        return True

    try:
        is_group_message = safe_str(plugin_event.plugin_info.get('func_type', '')) == 'group_message'
        if not is_group_message:
            return True

        host_id = getattr(plugin_event.data, 'host_id', None)
        hag_id = get_hag_id_from_event(plugin_event)

        if host_id is not None:
            host_local_enable = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId=host_id,
                userType='host',
                platform=plugin_event.platform['platform'],
                userConfigKey='hostLocalEnable',
                botHash=plugin_event.bot_info.hash,
            )
            if not host_local_enable:
                return False

        if hag_id:
            group_enable = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId=hag_id,
                userType='group',
                platform=plugin_event.platform['platform'],
                userConfigKey='groupEnable',
                botHash=plugin_event.bot_info.hash,
            )
            if not group_enable:
                return False
    except Exception:
        return True

    return True


class TemplateValueDict(dict):
    """安全格式化用字典。缺失字段时原样保留占位符，而不是抛 KeyError。"""

    def __missing__(self, key):
        return '{' + safe_str(key) + '}'


def render_text_template(template_text: str, value_dict: Dict[str, Any]) -> str:
    """用安全字典格式化回复词。"""
    try:
        return safe_str(template_text).format_map(TemplateValueDict(value_dict))
    except Exception:
        return safe_str(template_text)


def build_base_template_value_dict(
    plugin_event,
    command_argument: str = '',
    extra_value_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    构建最常见的回复格式化变量。

    这里把 hag_id 直接放进默认变量里，是为了让模板使用者后续写回复词时
    可以直接引用当前群上下文标识，而不用再手动拼 host_id|group_id。
    """
    config_bot_hash = get_bot_hash_from_event(plugin_event)
    reply_bot_hash = get_bot_hash_from_event(plugin_event, use_linked=True)
    value_dict = {
        'bot_id': get_bot_id_from_event(plugin_event),
        'bot_hash': config_bot_hash,
        'config_bot_hash': config_bot_hash,
        'linked_bot_hash': reply_bot_hash,
        'reply_bot_hash': reply_bot_hash,
        'user_id': get_sender_id_from_event(plugin_event),
        'user_name': get_sender_name_from_event(plugin_event),
        'group_id': get_group_id_from_event(plugin_event),
        'host_id': get_host_id_from_event(plugin_event),
        'hag_id': get_hag_id_from_event(plugin_event),
        'command_argument': safe_str(command_argument),
        'prefix': config.allowed_prefix_list[0],
    }
    if isinstance(extra_value_dict, dict):
        value_dict.update(extra_value_dict)
    return value_dict


def get_bot_display_name(plugin_event) -> str:
    """
    获取用于日志记录的 bot 显示名。

    若当前环境已经接入 OlivaDiceCore 自定义 bot 名字，则优先拿它；
    否则退化为 bot_id，保证日志里至少有一个稳定标识。
    """
    if has_oliva_dice_core:
        try:
            bot_hash = plugin_event.bot_info.hash
            return safe_str(OlivaDiceCore.msgCustom.dictStrCustomDict[bot_hash]['strBotName'])
        except Exception:
            pass
    return get_bot_id_from_event(plugin_event)


def send_message_force(bot_hash: Any, send_type: str, target_id: Any, message_text: str, Proc=None) -> Any:
    """
    主动发送消息封装。

    设计目的与官方模板的 send_message_force 一致：
    - 当前逻辑没有现成 plugin_event 可用时，仍可指定 bot 主动发消息。
    - 典型场景包括定时任务、后台线程、菜单操作或其他非消息事件回调。

    参数说明：
        - bot_hash：传哪个 bot_hash，就严格使用哪个 bot 发消息。
            这里不会再按 link 做反查或自动切换。
    - send_type：通常为 group 或 private。
    - target_id：目标群号或用户号。
    - message_text：要发送的文本内容。
    - Proc：可选；不传则尝试使用 init/init_after 缓存的 Proc。
    """
    Proc = Proc or get_runtime_proc()
    if Proc is None:
        return None

    runtime_bot_hash = safe_str(bot_hash).strip()
    bot_info_dict = getattr(Proc, 'Proc_data', {}).get('bot_info_dict', {})
    if not runtime_bot_hash or runtime_bot_hash not in bot_info_dict:
        return None

    try:
        plugin_event = OlivOS.API.Event(
            OlivOS.contentAPI.fake_sdk_event(
                bot_info=bot_info_dict[runtime_bot_hash],
                fakename=config.plugin_name,
            ),
            Proc.log,
        )
        return plugin_event.send(safe_str(send_type), target_id, safe_str(message_text))
    except Exception:
        return None


def record_reply_to_logger(plugin_event, message_text: str) -> None:
    """
    主动把回复写入 OlivaDiceLogger 的消息钩子。
    也就是说，如果回复调用了这个钩子，bot 的消息就能在日志染色网站上看到
    """
    if not has_oliva_dice_core:
        return

    try:
        msg_hook = OlivaDiceCore.crossHook.dictHookFunc.get('msgHook')
        if not callable(msg_hook):
            return

        msg_hook(
            plugin_event,
            'reply',
            {
                'name': get_bot_display_name(plugin_event),
                'id': get_bot_id_from_event(plugin_event),
            },
            [
                get_host_id_from_event(plugin_event) or None,
                get_group_id_from_event(plugin_event) or None,
                get_sender_id_from_event(plugin_event) or None,
            ],
            safe_str(message_text),
        )
    except Exception:
        pass


def reply_message(
    plugin_event,
    message_text: str,
    record_by_logger: bool = True,
    at_sender: bool = False,
) -> Any:
    """
    统一回复封装。

    参数说明：
    - record_by_logger=True：主动调用 Logger 钩子，便于被日志系统记录。
    - record_by_logger=False：不主动调用 Logger 钩子，只发送消息。
    - at_sender=True：在消息前追加一个 at 当前用户的 OP 码。
    """
    final_message = safe_str(message_text)
    if at_sender:
        sender_id = get_sender_id_from_event(plugin_event)
        if sender_id:
            final_message = f'[OP:at,id={sender_id}] {final_message}'

    if record_by_logger:
        record_reply_to_logger(plugin_event, final_message)

    try:
        return plugin_event.reply(final_message)
    except Exception:
        return None
