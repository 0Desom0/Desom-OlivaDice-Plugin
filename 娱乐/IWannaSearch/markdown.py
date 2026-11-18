# -*- encoding: utf-8 -*-
"""QQ 官方机器人的 Markdown 渲染与回调按钮。

回复词在配置里是纯文本（`· 字段：值`、`【标题】`），这里统一转成 Markdown：
`· ` 变列表项、`【X】` 变粗体标题，然后用 create_markdown_message 发送。
发送失败返回 False，由 utils.reply_message 回退到原来的纯文本通道。
"""

import re
from typing import Any, Dict, List

OP_PATTERN = re.compile(r'\[OP:[^\]]*\]')
HEADING_PATTERN = re.compile(r'【([^】]+)】')
BUTTON_LABEL_LIMIT = 20
MAX_ROWS = 5
MAX_BUTTONS_PER_ROW = 4


def safe_text(value: Any, default_value: str = '') -> str:
    if value is None:
        return default_value
    return str(value)


def convert(content: str) -> str:
    """把纯文本回复词转成 Markdown；已经带 Markdown 的段落保持原样。"""
    text = OP_PATTERN.sub('', safe_text(content)).strip()
    if not text:
        return ''
    line_list = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith('·'):
            body = stripped.lstrip('·').lstrip()
            line_list.append(f'- {body}' if body else '-')
            continue
        if stripped.startswith('- '):
            line_list.append(stripped)
            continue
        line_list.append(HEADING_PATTERN.sub(lambda match: f'**{match.group(1)}**', line))
    return '\n'.join(line_list).strip()


def get_chat_context(plugin_event) -> tuple:
    """从事件推导 chat_type / chat_id（群、C2C、频道、频道私信）。"""
    data = getattr(plugin_event, 'data', None)
    extend = getattr(data, 'extend', None)
    extend = extend if isinstance(extend, dict) else {}
    func_type = safe_text((getattr(plugin_event, 'plugin_info', {}) or {}).get('func_type', ''))
    group_id = safe_text(getattr(data, 'group_id', None))
    user_id = safe_text(getattr(data, 'user_id', None))
    host_id = safe_text(extend.get('host_group_id')) or safe_text(getattr(data, 'host_id', None))
    if extend.get('chat_type') and extend.get('chat_id'):
        return safe_text(extend.get('chat_type')), safe_text(extend.get('chat_id'))
    flag_direct = bool(extend.get('flag_from_direct', func_type == 'private_message'))
    if 'flag_from_qq' in extend:
        if bool(extend.get('flag_from_qq')):
            return ('qq_private' if flag_direct else 'qq_group'), (user_id if flag_direct else group_id)
        return (
            ('guild_private' if flag_direct else 'guild_channel'),
            ((host_id or group_id) if flag_direct else group_id),
        )
    try:
        platform_name = safe_text(getattr(plugin_event, 'platform', {}).get('platform', '')).lower()
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


def can_send_markdown(plugin_event) -> bool:
    from . import utils

    if not utils.load_global_config().get('markdown_enable_switch', True):
        return False
    return callable(getattr(getattr(plugin_event, 'indeAPI', None), 'create_markdown_message', None))


def button(label: str, data: str, style: int = 0, link: bool = False, callback: bool = False) -> Dict[str, Any]:
    """0 跳转、1 回调、2 指令；指令型 enter=False 只把命令填进输入框。"""
    data_text = safe_text(data)
    action = {
        'type': 0 if link else (1 if callback else 2),
        'permission': {'type': 2},
        'data': data_text,
        'unsupport_tips': '请更新 QQ 客户端后使用按钮',
    }
    if not link and not callback:
        action.update(enter=False, reply=False)
    return {
        'id': data_text[:64] or 'btn',
        'render_data': {
            'label': safe_text(label)[:BUTTON_LABEL_LIMIT],
            'visited_label': safe_text(label)[:BUTTON_LABEL_LIMIT],
            'style': style,
        },
        'action': action,
    }


def keyboard(rows: List[List[Dict[str, Any]]]):
    rows = [row[:MAX_BUTTONS_PER_ROW] for row in rows if row]
    if not rows:
        return None
    return {'content': {'rows': [{'buttons': row} for row in rows[:MAX_ROWS]]}}


def page_keyboard(page_index: int, total_page: int):
    """翻页键盘：上下页回调，跳页只填入 `.iw 跳页 `。"""
    nav = []
    if page_index > 0:
        nav.append(button('上一页', 'iw:pg:prev', callback=True))
    if page_index < total_page - 1:
        nav.append(button('下一页', 'iw:pg:next', style=1, callback=True))
    nav.append(button('跳页', '.iw 跳页 '))
    return keyboard([nav])


def build_header(plugin_event) -> str:
    """Markdown 不支持引用，用首行 @发送者 + 原消息代替。"""
    from . import utils

    if utils.load_global_config().get('reply_quote_switch', True) is False:
        return ''
    data = getattr(plugin_event, 'data', None)
    user_id = safe_text(getattr(data, 'user_id', None)).strip()
    if not user_id:
        return ''
    text = OP_PATTERN.sub('', safe_text(getattr(data, 'message', ''))).strip()
    if len(text) > 40:
        text = f'{text[:40]}…'
    at_tag = f'<qqbot-at-user id="{user_id}" />'
    return f'> {at_tag}：{text}' if text else f'> {at_tag}'


def reply_markdown(plugin_event, content: str, keyboard_dict=None) -> bool:
    """发送 Markdown 消息；调用方在返回 False 时回退纯文本。"""
    if not can_send_markdown(plugin_event):
        return False
    text = convert(content)
    if not text:
        return False
    chat_type, chat_id = get_chat_context(plugin_event)
    if not chat_type or not chat_id:
        return False
    header = build_header(plugin_event)
    if header:
        text = f'{header}\n\n{text}'
    payload = {'chat_type': chat_type, 'chat_id': chat_id, 'markdown': {'content': text}}
    is_qq_chat = chat_type in ('qq_group', 'qq_private')
    if keyboard_dict and is_qq_chat:
        payload['keyboard'] = keyboard_dict
    data = getattr(plugin_event, 'data', None)
    extend = getattr(data, 'extend', None)
    extend = extend if isinstance(extend, dict) else {}
    message_id = safe_text(getattr(data, 'message_id', '')).strip()
    event_id = safe_text(extend.get('event_id')).strip()
    func_type = safe_text((getattr(plugin_event, 'plugin_info', {}) or {}).get('func_type', ''))
    # 带键盘/图片的 Markdown 必须是被动回复，否则客户端会把按钮退化成文字。
    if func_type == 'button_click':
        if event_id:
            payload['event_id'] = event_id
    elif message_id and message_id != '-1':
        payload['msg_id'] = message_id
    elif event_id:
        payload['event_id'] = event_id
    try:
        result = plugin_event.indeAPI.create_markdown_message(**payload)
    except Exception:
        return False
    if isinstance(result, dict) and not result.get('active', False):
        return False
    return True
