import re
import sys
from functools import wraps
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import config, store
from .message_custom import TEXT

reply_segment_pattern = re.compile(r'^\[(?:OP|CQ):reply(?:,[^\]]*)?\]', re.IGNORECASE)
at_segment_pattern = re.compile(r'^\[(?:OP|CQ):at,(?P<params>[^\]]*)\]', re.IGNORECASE)


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


def op_escape(value: Any) -> str:
    """转义 OP 码参数中的保留字符。"""
    return (
        safe_str(value)
        .replace('&', '&amp;')
        .replace('[', '&#91;')
        .replace(']', '&#93;')
        .replace(',', '&#44;')
    )


def ensure_runtime_storage_by_event(plugin_event, Proc):
    # Bot hash 为原始账户标识，不使用 Core 的群链作为配置命名空间。
    bot_hash = plugin_event.bot_info.hash
    store.load_bot(bot_hash)
    return bot_hash


def get_current_bot_target_ids(plugin_event):
    base_info = getattr(plugin_event, 'base_info', {})
    extend = getattr(plugin_event.data, 'extend', {}) or {}
    candidates = (base_info.get('self_id'), plugin_event.bot_info.id,
                  extend.get('sub_self_id'), extend.get('sub_self_open_id'))
    return list(dict.fromkeys(str(value).strip() for value in candidates if value is not None and str(value).strip()))


def get_sender_id_from_event(plugin_event) -> str:
    """获取发送者 user_id。"""
    try:
        return safe_str(plugin_event.data.user_id)
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


def get_platform_from_event(plugin_event) -> str:
    """从事件对象中安全获取平台标识。"""
    try:
        return safe_str(plugin_event.platform.get('platform', 'unknown'))
    except Exception:
        return 'unknown'


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


def get_hag_id_from_event(plugin_event):
    return build_hag_id(get_host_id_from_event(plugin_event), get_group_id_from_event(plugin_event))


# 以下命令解析函数沿用轻量模板；空前缀列表表示停用所有命令。
def strip_reply_segment(message_text: str) -> str:
    """
    去掉消息开头的 [OP:reply,id=xxx]。

    模板的命令解析不应被回复头干扰，因此这里先统一做一次剥离。
    """
    remaining_text = safe_str(message_text)
    while True:
        remaining_text = remaining_text.lstrip()
        matched_reply = reply_segment_pattern.match(remaining_text)
        if not matched_reply:
            return remaining_text
        remaining_text = remaining_text[matched_reply.end():]


def parse_prefix(message_text: str, prefix_list: Optional[Iterable[str]] = None) -> Tuple[str, str]:
    """
    解析前缀。

    返回值是 (命中的前缀, 去掉前缀后的剩余字符串)。
    如果没有命中前缀，则前缀返回空字符串，剩余字符串返回原文。
    """
    source_text = safe_str(message_text)
    real_prefix_list = config.allowed_prefix_list if prefix_list is None else prefix_list
    for prefix_text in real_prefix_list:
        if source_text.startswith(prefix_text):
            return prefix_text, source_text[len(prefix_text):].lstrip()
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
            command_argument = command_source[len(raw_command_name):].lstrip()
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

    输入同时兼容 OP/CQ 码以及 id/qq 参数。
    """
    remaining_text = safe_str(message_text)
    at_item_list: List[Dict[str, str]] = []

    while True:
        remaining_text = remaining_text.lstrip()
        matched_at = at_segment_pattern.match(remaining_text)
        if not matched_at:
            break

        params = {}
        for item in safe_str(matched_at.group('params')).split(','):
            key, separator, value = item.partition('=')
            if separator:
                params[key.strip().casefold()] = value.strip()
        at_item_list.append({
            'id': safe_str(params.get('id') or params.get('qq') or ''),
            'name': safe_str(params.get('name') or ''),
            'raw': matched_at.group(0),
        })
        remaining_text = remaining_text[matched_at.end():]
        if not allow_multi:
            break

    return at_item_list, remaining_text.lstrip()


def is_force_reply_to_current_bot(at_item_list: List[Dict[str, str]], plugin_event) -> bool:
    """
    判断解析出的 at 列表里是否包含当前 bot 或 all。

    这类判断通常用于“前置 at 时，只允许 at 到当前 bot / all 的消息继续进入命令解析”。
    """
    current_bot_id_set = set(get_current_bot_target_ids(plugin_event))
    current_bot_id_set.add('all')
    return any(
        safe_str(at_item.get('id', '')).strip() in current_bot_id_set
        for at_item in at_item_list
    )


def is_sender_core_master(plugin_event):
    # OlivaDiceCore ordinaryInviteManager.py: isInMasterList 仅读取 console.masterList。
    core = sys.modules.get('OlivaDiceCore')
    if core is None:
        return False
    try:
        user_hash = core.userConfig.getUserHash(plugin_event.data.user_id, 'user', plugin_event.platform['platform'])
        return bool(core.ordinaryInviteManager.isInMasterList(plugin_event.bot_info.hash, user_hash))
    except (AttributeError, KeyError, TypeError):
        return False


def get_master_permission_info(plugin_event):
    # 保留模板配置字段，但这个插件不读取其授权值。
    return {'sender_is_core_master': is_sender_core_master(plugin_event)}


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
    OlivaDiceCore = sys.modules.get('OlivaDiceCore')
    if OlivaDiceCore is None:
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


def target_from_event(plugin_event):
    group_id = get_group_id_from_event(plugin_event)
    if not group_id:
        return None
    sdk = plugin_event.platform['sdk']
    chat_type = getattr(plugin_event.data, 'extend', {}).get('chat_type', 'group')
    # adapter/qqGuild/qqGuildv2SDKCommon.py 区分 qq_group、guild_channel 和私聊。
    if sdk == 'qqGuildv2_link' and chat_type != 'qq_group':
        return None
    return {'sdk': sdk, 'platform': get_platform_from_event(plugin_event), 'group_id': group_id,
            'chat_type': chat_type}


def is_group_disabled(plugin_event):
    group_id = get_group_id_from_event(plugin_event)
    if not group_id:
        return False
    settings = store.bot_config(plugin_event.bot_info.hash)
    sid = '|'.join((plugin_event.platform['sdk'], get_platform_from_event(plugin_event), group_id))
    return group_id in settings['disabled_group_list'] or sid in settings['disabled_group_list']


def in_global_whitelist(plugin_event):
    user_id = get_sender_id_from_event(plugin_event)
    platform = get_platform_from_event(plugin_event)
    return any(item['platform'] == platform and item['user_id'] == user_id
               for item in store.global_config()['whitelist'])


def resolve_group_role(plugin_event):
    role = (getattr(plugin_event.data, 'sender', {}).get('role') or '').lower()
    if role or plugin_event.platform['sdk'] != 'qqGuildv2_link':
        return role
    try:
        # core/core/API.py: Event.get_group_member_info；qqGuildv2SDKCommon.py 返回 data.role。
        result = plugin_event.get_group_member_info(
            group_id=get_group_id_from_event(plugin_event), user_id=get_sender_id_from_event(plugin_event),
        )
    except Exception as error:
        store.log(None, f'读取群角色失败：{type(error).__name__}')
        return ''
    if isinstance(result, dict) and result.get('active') is not False:
        info = result.get('data') or result.get('member') or result
        return (info.get('role') or '').lower()
    return ''


def sender_can_manage(plugin_event):
    return (get_master_permission_info(plugin_event)['sender_is_core_master']
            or is_group_owner(plugin_event) or is_group_admin(plugin_event) or in_global_whitelist(plugin_event)
            or resolve_group_role(plugin_event) in ('owner', 'admin', 'sub_admin'))


def reply_message(plugin_event, message_text):
    # core/core/API.py: Event.reply；宿主按 app.json 的 olivos_string 转换。
    return plugin_event.reply(message_text)


def log_exception(action_name):
    def decorator(target_function):
        @wraps(target_function)
        def wrapper(plugin_event, Proc):
            try:
                return target_function(plugin_event, Proc)
            except store.StorageError:
                store.log(Proc, f'{action_name}：持久化失败')
                reply_message(plugin_event, TEXT['persist'])
            except Exception as error:
                store.log(Proc, f'{action_name}：{type(error).__name__}')
                reply_message(plugin_event, TEXT['error'])
        return wrapper
    return decorator
