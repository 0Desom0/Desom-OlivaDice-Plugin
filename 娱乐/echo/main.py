import re

import OlivOS
import echo


REPLY_SEGMENT_PATTERN = re.compile(
    r'^\[(?:OP|CQ):reply(?:,[^\]]*)?\]',
    re.IGNORECASE,
)
AT_SEGMENT_PATTERN = re.compile(
    r'^\[(?:OP|CQ):at,(?P<params>[^\]]*)\]',
    re.IGNORECASE,
)


def _safe_text(value):
    try:
        return str(value)
    except Exception:
        return ''


def _op_escape(value):
    return (
        _safe_text(value)
        .replace('&', '&amp;')
        .replace('[', '&#91;')
        .replace(']', '&#93;')
        .replace(',', '&#44;')
    )


def _current_bot_target_ids(plugin_event):
    target_ids = []
    try:
        target_ids.append(plugin_event.base_info.get('self_id'))
    except Exception:
        pass
    try:
        target_ids.append(plugin_event.bot_info.id)
    except Exception:
        pass
    try:
        extend = getattr(plugin_event.data, 'extend', {}) or {}
        target_ids.extend([
            extend.get('sub_self_id'),
            extend.get('sub_self_open_id'),
        ])
    except Exception:
        pass
    return {
        _safe_text(target_id).strip()
        for target_id in target_ids
        if target_id is not None and _safe_text(target_id).strip()
    }


def parse_command_message(plugin_event, message):
    remaining = _safe_text(message).lstrip()
    while True:
        matched_reply = REPLY_SEGMENT_PATTERN.match(remaining)
        if not matched_reply:
            break
        remaining = remaining[matched_reply.end():].lstrip()

    leading_at_ids = []
    while True:
        matched_at = AT_SEGMENT_PATTERN.match(remaining)
        if not matched_at:
            break
        params = {}
        for item in matched_at.group('params').split(','):
            key, separator, value = item.partition('=')
            if separator:
                params[key.strip().casefold()] = value.strip()
        leading_at_ids.append(params.get('id') or params.get('qq') or '')
        remaining = remaining[matched_at.end():].lstrip()

    if leading_at_ids:
        current_ids = _current_bot_target_ids(plugin_event)
        current_ids.add('all')
        if not any(_safe_text(target_id).strip() in current_ids for target_id in leading_at_ids):
            return None
    return remaining


def reply_message(plugin_event, message):
    final_message = _safe_text(message)
    try:
        is_group = plugin_event.plugin_info.get('func_type') == 'group_message'
        message_id = _safe_text(plugin_event.data.message_id).strip()
        if is_group and message_id and message_id != '-1':
            final_message = f'[OP:reply,id={_op_escape(message_id)}]{final_message}'
    except Exception:
        pass
    return plugin_event.reply(final_message)


class Event(object):
    def init(plugin_event, Proc):
        pass
        
    def private_message(plugin_event, Proc):
        unity_reply(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        unity_reply(plugin_event, Proc)


def unity_reply(plugin_event, Proc):
    msg = parse_command_message(plugin_event, plugin_event.data.message)
    if msg is None:
        return
    if msg.startswith('.echo') or msg.startswith('。echo'):
        echo_content = msg[5:].strip()
        if echo_content:  # 如果有内容
            reply_message(plugin_event, echo_content)
        else:
            reply_message(plugin_event, '请输入要小芙重复的的内容哦！例如: .echo 你好')
