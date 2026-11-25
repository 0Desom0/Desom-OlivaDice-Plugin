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
# 列表项：`1. xxx`（搜索结果是编号列表）。
LIST_ITEM_PATTERN = re.compile(r'^(\d+)[.、)]\s+(.+)$')
# 序号高亮色（与 function.MARK_COLOR_INDEX 一致；这里独立定义避免循环 import）
INDEX_MARK_COLOR = "#FF6B35"
BSLASH = chr(92)  # 反斜杠；不用字面量，免得源码里的 \t 被当成制表符


def mark_index(number: str) -> str:
    """序号上色：QQ 认 KaTeX 的 \textcolor，\text{} 保住空格。"""
    return f'$\\textcolor{{{INDEX_MARK_COLOR}}}{{{number}}}$'
# 详情页里原本文本形式的链接行，改由按钮承载后从正文剔除。
LINK_LINE_PATTERN = re.compile(r'^(外部页面|外部链接|档案页面|档案页|下载链接)[：:]\s*\S*https?://')
# 字段行：`· ID：11510` 或 `· 评分：8.1/10  难度：91.2/100`
FIELD_PATTERN = re.compile(r'^[·•]\s*([^：:]+)[：:]\s*(.*)$')
BUTTON_LABEL_LIMIT = 20
# 外部站点在按钮上用的短名（手机一行放不下全称）
SITE_LABELS = {
    'delicious fruit': 'DF',
    'iwanna wiki': 'Wiki',
    'i wanna wiki': 'Wiki',
    'iwannawiki': 'Wiki',
}
# 列表条目最长字符数：手机上一行大约放得下 28 个西文字符，超了就截断，避免折成两行。
ITEM_LINE_LIMIT = 48
MAX_ROWS = 5
MAX_BUTTONS_PER_ROW = 4


def safe_text(value: Any, default_value: str = '') -> str:
    if value is None:
        return default_value
    return str(value)


# 详情页字段：`评分：8.8/10` / `**评分**：8.8/10`，按字段名上不同颜色
SCORE_FIELD_PATTERN = re.compile(r'(评分|难度)(\**)[：:]\s*([^\s，,；;]+)')
SCORE_FIELD_COLORS = {
    '评分': '#4FC3F7',
    '难度': '#C792EA',
}


def highlight_scores(text: str) -> str:
    """把详情页的评分/难度数值染上各自颜色（纯文本回退时由 strip_markup 洗掉）。"""
    def _wrap(match):
        label, stars, value = match.group(1), match.group(2), match.group(3)
        color = SCORE_FIELD_COLORS.get(label)
        if not color:
            return match.group(0)
        return f'{label}{stars}：$' + BSLASH + f'textcolor{{{color}}}{{{value}}}$'

    return SCORE_FIELD_PATTERN.sub(_wrap, text)


def convert(content: str) -> str:
    """把纯文本回复词转成 Markdown。

    排版跟 CelestePlugin 一致：标题加粗、每个条目自成一段（标题行 + 空行），
    不使用 `-` / `1.` 这类列表语法——QQ 客户端会把列表块和后面的正文并成一段。
    """
    text = OP_PATTERN.sub('', safe_text(content)).strip()
    if not text:
        return ''
    line_list = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            line_list.append('')
            continue
        field_match = FIELD_PATTERN.match(stripped)
        if field_match:
            # `· ID：11510` → `**ID**：11510`
            label, value = field_match.group(1), field_match.group(2)
            line_list.append(highlight_scores(f'**{label}**：{value}' if value else f'**{label}**'))
            continue
        item_match = LIST_ITEM_PATTERN.match(stripped)
        if item_match:
            # `1. [11510] 标题` → 整行加粗；标题完整显示，长标题由客户端折行
            line_list.append(
                f'**{mark_index(item_match.group(1))}. {item_match.group(2)}**'
            )
            continue
        line_list.append(HEADING_PATTERN.sub(lambda match: f'**{match.group(1)}**', line))
    # 压缩连续空行，保持条目之间恰好一个空行
    compact = []
    for line in line_list:
        if line == '' and (not compact or compact[-1] == ''):
            continue
        compact.append(line)
    return '\n'.join(compact).strip()


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


def log_failure(reason: str) -> None:
    """失败原因写进 OlivOS 日志，不要再被 except 静默掉。"""
    try:
        from . import utils
        utils.error_log(utils.get_runtime_proc(), f'[Markdown] {reason}')
    except Exception:
        pass


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
    # OlivOS 偶尔把没有正文的回调事件传成字符串 "null"/"None"，别把它印在引用行里
    if text.lower() in {'null', 'none', 'undefined'}:
        text = ''
    if len(text) > 40:
        text = f'{text[:40]}…'
    at_tag = f'<qqbot-at-user id="{user_id}" />'
    # 不再用行首 ">"：QQ 客户端渲染这个引用行时会额外打出一个 "null"，
    # 换成加粗的一行（实测日志里我们发出的正文本身没有 null）。
    return f'{at_tag}：{text}' if text else at_tag


def strip_link_lines(content: str) -> str:
    """去掉正文里的纯链接行（这些改成了按钮）。"""
    kept = []
    for line in safe_text(content).splitlines():
        if LINK_LINE_PATTERN.match(line.strip()):
            continue
        kept.append(line)
    return '\n'.join(kept)


def detail_keyboard(game_item: Dict[str, Any]):
    """详情页按钮：下载、档案页，以及每个外部来源各一个链接按钮。"""
    if not isinstance(game_item, dict):
        return None
    rows = []
    main_row = []
    download_url = safe_text(game_item.get('url')).strip()
    if download_url.startswith(('http://', 'https://')):
        main_row.append(button('下载', download_url, style=1, link=True))
    page_url = safe_text(game_item.get('page_url')).strip()
    if page_url.startswith(('http://', 'https://')):
        main_row.append(button('档案页', page_url, link=True))
    if main_row:
        rows.append(main_row)

    external_row = []
    seen_url = set()
    for source_item in game_item.get('external_sources') or []:
        if not isinstance(source_item, dict):
            continue
        url = safe_text(source_item.get('url')).strip()
        if not url.startswith(('http://', 'https://')) or url in seen_url:
            continue
        seen_url.add(url)
        site_name = safe_text(source_item.get('site'))
        label = SITE_LABELS.get(site_name.casefold()) or site_name or '外部页'
        external_row.append(button(label[:12], url, link=True))
    if external_row:
        rows.append(external_row)
    return keyboard(rows)


def reply_detail(plugin_event, content: str, game_item: Dict[str, Any]) -> bool:
    """详情页：正文删掉链接行，链接改按钮，封面走 local_images。"""
    images = {}
    text = strip_link_lines(content)
    cover_url = safe_text((game_item or {}).get('cover_url')).strip()
    if cover_url.startswith(('http://', 'https://')):
        from . import utils
        local_path = utils.prepare_local_image(cover_url)
        if local_path:
            images['封面'] = local_path
            text = f'{{{{封面}}}}\n\n{text}'
    return reply_markdown(plugin_event, text, detail_keyboard(game_item), images=images)


def _release_images(payload: dict) -> None:
    """发送结束后删掉本地临时封面（适配器在发送过程中已读完文件）。"""
    for resource in (payload.get('local_images') or {}).values():
        try:
            from . import utils
            utils.release_local_image(resource)
        except Exception:
            pass


def reply_markdown(plugin_event, content: str, keyboard_dict=None, images=None) -> bool:
    """发送 Markdown 消息；调用方在返回 False 时回退纯文本。"""
    sender = getattr(getattr(plugin_event, 'indeAPI', None), 'create_markdown_message', None)
    if not callable(sender):
        log_failure(
            f"indeAPI 没有 create_markdown_message（indeAPI={type(getattr(plugin_event, 'indeAPI', None)).__name__}）"
        )
    text = convert(content)
    if not text:
        log_failure('正文转换后为空')
        return False
    chat_type, chat_id = get_chat_context(plugin_event)
    if not chat_type or not chat_id:
        extend = getattr(getattr(plugin_event, 'data', None), 'extend', {})
        log_failure(f'拿不到会话类型 chat_type={chat_type!r} chat_id={chat_id!r} extend_keys={list(extend) if isinstance(extend, dict) else extend!r}')
        return False
    header = build_header(plugin_event)
    if header:
        text = f'{header}\n\n{text}'
    payload = {'chat_type': chat_type, 'chat_id': chat_id, 'markdown': {'content': text}}
    is_qq_chat = chat_type in ('qq_group', 'qq_private')
    if keyboard_dict and is_qq_chat:
        payload['keyboard'] = keyboard_dict
    if images:
        if not is_qq_chat:
            return False
        # 图片已由 prepare_local_image 落在 data/images/<ns>/covers 下，
        # 这里只把相对路径交给适配器；发送完在 finally 里删掉临时文件。
        payload['local_images'] = images
    data = getattr(plugin_event, 'data', None)
    extend = getattr(data, 'extend', None)
    extend = extend if isinstance(extend, dict) else {}
    message_id = safe_text(getattr(data, 'message_id', '')).strip()
    event_id = safe_text(extend.get('event_id')).strip()
    func_type = safe_text((getattr(plugin_event, 'plugin_info', {}) or {}).get('func_type', ''))
    # 带键盘/图片的 Markdown 必须是被动回复，否则客户端会把按钮退化成文字。
    # 回调事件：先用卡片 msg_id（最稳），再试 event_id，最后才退回主动发送。
    attempts = []
    if func_type == 'button_click':
        if message_id and message_id != '-1':
            attempts.append({'msg_id': message_id})
        if event_id:
            attempts.append({'event_id': event_id})
        attempts.append({})
    elif message_id and message_id != '-1':
        attempts.append({'msg_id': message_id})
    elif event_id:
        attempts.append({'event_id': event_id})
    else:
        attempts.append({})
    if callable(sender):
        for extra in attempts:
            call_payload = dict(payload, **extra)
            try:
                result = sender(**call_payload)
            except Exception as error:
                log_failure(f'indeAPI 调用抛错 {type(error).__name__}: {error}')
                result = None
            if isinstance(result, dict) and result.get('active', False):
                _release_images(payload)
                return True
            if isinstance(result, dict):
                log_failure(
                    f'indeAPI 发送未激活（凭据 {extra or "主动"}）：{result.get("data")}'
                )
        payload = dict(payload, **attempts[-1])
    # 二级通道：直接走 qqGuildv2 适配器，绕过 indeAPI 的包装层。
    try:
        import OlivOS
        target_event = getattr(getattr(plugin_event, 'indeAPI', None), 'event', None) or plugin_event
        result = OlivOS.qqGuildv2SDK.event_action.create_markdown_message(target_event, **payload)
    except Exception as error:
        log_failure(f'适配器直调也失败 {type(error).__name__}: {error}')
        _release_images(payload)
        return False
    _release_images(payload)
    if isinstance(result, dict) and result.get('active', False):
        return True
    log_failure(f'适配器直调未激活：{result if not isinstance(result, dict) else result.get("data")}')
    return False
