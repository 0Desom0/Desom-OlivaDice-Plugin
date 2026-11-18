# -*- encoding: utf-8 -*-
"""CelestePlugin 的 Markdown / 按钮页面渲染。

按钮回调统一用 `clst:<action>:<arg>` 作为 button_data，由 message.handle_button_click 处理。
纯文本回退仍然走 function.format_*，两套渲染共用同一份数据。
"""

from typing import Any

from . import function
from . import utils


LABEL_LIMIT = 20
MAX_ROWS = 5
MAX_BUTTONS_PER_ROW = 4


def _label(text: Any, limit: int = LABEL_LIMIT) -> str:
    value = utils.safe_str(text).strip() or '未命名'
    return value[:limit]


def button(
    text: Any,
    data: str,
    style: int = 0,
    link: bool = False,
    callback: bool = False,
) -> dict[str, Any]:
    """构造键盘按钮：link=跳转链接，callback=服务端回调，默认是指令型（data 为真命令）。"""
    data_text = utils.safe_str(data)
    # QQ 官方键盘：0 跳转，1 回调，2 指令。只有跳页需要填入输入框。
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
        'render_data': {'label': _label(text), 'visited_label': _label(text), 'style': style},
        'action': action,
    }


def keyboard(rows: list[list[dict[str, Any]]]) -> dict[str, Any] | None:
    rows = [row[:MAX_BUTTONS_PER_ROW] for row in rows if row]
    if not rows:
        return None
    rows = rows[:MAX_ROWS]
    return {'content': {'rows': [{'buttons': row} for row in rows]}}


def _stats_line(detail: dict[str, Any]) -> str:
    return (
        f"下载 **{int(detail.get('downloads', 0) or 0):,}** · "
        f"浏览 **{int(detail.get('views', 0) or 0):,}** · "
        f"喜欢 **{int(detail.get('likes', 0) or 0):,}**"
    )


def _category_text(detail: dict[str, Any]) -> str:
    return ' / '.join(
        value for value in [detail.get('category', ''), detail.get('subcategory', '')] if value
    ) or '未分类'


def render_help() -> tuple[str, dict[str, Any] | None]:
    text = '\n'.join(
        [
            '## Celeste Mod 工具',
            '> 前缀 `.clst`；也可以直接点下面的按钮',
            '',
            '**查询**',
            '- `.clst 关键词` 标题搜索',
            '- `.clst id 424541` 按 GameBanana ID 精确查询',
            '- `.clst 作者 名称` · `.clst 分类 Maps` · `.clst 标签 关键词`',
            '',
            '**推荐**',
            '- `.clst 随机 [1-10]` 随机地图',
            '- `.clst today` 今日 Mod（每人每天一张，当天固定）',
            '- `.clst 更新` 骰主手动重建索引',
            '',
            '**无尽挑战**',
            '- `.clst 无尽 开始` / `.clst 无尽 帮助`',
        ]
    )
    rows = [
        [
            button('随机一张', 'clst:rnd:1', style=1, callback=True),
            button('随机 3 张', 'clst:rnd:3', callback=True),
            button('今日 Mod', 'clst:today', callback=True),
        ],
        [
            button('无尽帮助', 'clst:en:help', callback=True),
            button('刷新帮助', 'clst:help', callback=True),
        ],
    ]
    return text, keyboard(rows)


def render_list(
    title: str,
    items: list[dict[str, Any]],
    page_index: int,
    page_size: int,
    total_count: int,
    notice: str = '',
) -> tuple[str, dict[str, Any] | None]:
    page_size = max(1, page_size)
    start = page_index * page_size
    page_items = items[start : start + page_size]
    page_count = max(1, (len(items) + page_size - 1) // page_size)
    lines = [f'**{title}**', f'第 {page_index + 1}/{page_count} 页 · 共 {total_count} 项']
    if notice:
        lines.append(notice)
    lines.append('')
    for offset, item in enumerate(page_items):
        index = start + offset
        category = ' / '.join(
            value for value in [item.get('category', ''), item.get('subcategory', '')] if value
        )
        meta = utils.safe_str(item.get('author', '未知作者'))
        if category:
            meta = f'{meta} · {category}'
        lines.append(f'**{index + 1}. {item.get("name", "未知标题")}**')
        lines.append(meta)
        lines.append('')
    lines.append('回复序号看详情；翻页可以点下面的按钮，也可以直接发送 上一页 / 下一页 / 跳页 3。')

    nav = []
    if page_index > 0:
        nav.append(button('上一页', 'clst:pg:prev', callback=True))
    if page_index < page_count - 1:
        nav.append(button('下一页', 'clst:pg:next', style=1, callback=True))
    # 结尾留一个空格，点完直接在输入框里补页码。
    nav.append(button('跳页', '.clst 跳页 '))
    return '\n'.join(lines), keyboard([nav])


def add_cover(lines: list[str], images: dict[str, str], item: dict[str, Any], label: str) -> None:
    url = utils.safe_str(item.get('cover_url')).strip()
    if url.startswith(('https://', 'http://')):
        lines.extend([f'{{{{{label}}}}}', ''])
        images[label] = url


def render_detail(
    detail: dict[str, Any],
    compact: bool = False,
    heading: str = '',
    show_random: bool = False,
    show_endless: bool = False,
    show_today: bool = False,
) -> tuple[str, dict[str, Any] | None, dict[str, str]]:
    config = utils.load_global_config()
    description = function.truncate_text(
        detail.get('description') or detail.get('text') or '暂无简介',
        int(config.get('description_max_length', 320)),
    )
    credit_text = function.truncate_text(
        function.format_credit_text(detail),
        int(config.get('credit_max_length', 180)),
    )
    title = utils.safe_str(detail.get('name'), '未知标题')
    lines = []
    images: dict[str, str] = {}
    if config.get('show_cover_image_switch', True):
        add_cover(lines, images, detail, '地图封面')
    if heading:
        lines.append(f'**{heading}**')
        lines.append('')
    lines.append(f'**{title}**')
    lines.append('')
    # 每项信息单独一条列表，正文不再挤成一整段。
    lines.append(f"- **ID**：{utils.safe_str(detail.get('item_type'), 'Mod')} "
                 f"{int(detail.get('id', 0) or 0)}")
    lines.append(
        f"- **作者**：{utils.safe_str(detail.get('author'), '未知作者')} · "
        f"**分类**：{_category_text(detail)}"
    )
    lines.append(f'- **数据**：{_stats_line(detail)}')
    if credit_text:
        lines.append(f'- **署名**：{credit_text}')
    if not compact:
        one_line_description = ' '.join(description.split())
        lines.append(f'- **简介**：{one_line_description}')
    page_url = utils.safe_str(detail.get('page_url'))
    if page_url:
        lines.append(f'- [在 GameBanana 上查看]({page_url})')

    file_url_map: dict[int, str] = {}
    for file_item in detail.get('files', []):
        file_id = int(file_item.get('id', 0) or 0)
        if file_id > 0 and file_item.get('url'):
            file_url_map[file_id] = utils.safe_str(file_item['url'])

    download_groups = function.build_download_groups(detail)
    limit = 1 if compact else int(config.get('detail_download_component_limit', 6))
    rows: list[list[dict[str, Any]]] = []
    download_row: list[dict[str, Any]] = []
    if download_groups:
        lines.append('')
        lines.append('**下载**')
        for index, group in enumerate(download_groups[: max(1, limit)], start=1):
            entry_texts = [function.format_component_entry(entry) for entry in group.get('entries', [])]
            component_text = '、'.join(entry_texts) or '、'.join(group.get('components', []))
            file_id = int(group.get('file_id', 0) or 0)
            url = file_url_map.get(file_id) or function.get_download_urls(file_id)['wegfan']
            lines.append(
                f'- {component_text or f"文件 {file_id}"} · {function.format_file_size(group.get("size", 0))}'
            )
            download_row.append(button(component_text or f'下载 {index}', url, style=1, link=True))
            if len(download_row) >= 2:
                rows.append(download_row)
                download_row = []
        if download_row:
            rows.append(download_row)
        if len(download_groups) > limit:
            lines.append(f'- 另有 {len(download_groups) - limit} 个组件未展开')
    else:
        lines.append('')
        lines.append('**下载**：未找到可用文件')

    controls = []
    if show_random:
        controls.extend([
            button('再来一张', 'clst:rnd:1', callback=True),
            button('随机 3 张', 'clst:rnd:3', callback=True),
        ])
    if show_endless:
        controls.append(button('返回无尽', 'clst:en:status', callback=True))
    if show_today:
        # 指令型：点一下只把命令填进输入框，让其他人也能抽自己那份。
        controls.append(button('我也要抽取', '.clst today'))
    if controls:
        rows = rows[:MAX_ROWS - 1] + [controls]
    return '\n'.join(lines), keyboard(rows), images


def render_random_summary(items: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None, dict[str, str]]:
    lines = [f'**随机地图 · {len(items)} 张**', '']
    images: dict[str, str] = {}
    show_cover = utils.load_global_config().get('show_cover_image_switch', True)
    for index, item in enumerate(items, start=1):
        category = ' / '.join(
            value for value in [item.get('category', ''), item.get('subcategory', '')] if value
        )
        meta = utils.safe_str(item.get('author', '未知作者'))
        if category:
            meta = f'{meta} · {category}'
        lines.append(f'**{index}. {item.get("name", "未知地图")}**')
        lines.append(meta)
        page_url = utils.safe_str(item.get('page_url'))
        if page_url:
            lines.append(f'[查看详情]({page_url})')
        lines.append('')
        if show_cover:
            add_cover(lines, images, item, f'地图封面 {index}')
    rows = [
        [
            button('再来一张', 'clst:rnd:1', style=1, callback=True),
            button('随机 3 张', 'clst:rnd:3', callback=True),
            button('今日 Mod', 'clst:today', callback=True),
        ]
    ]
    return '\n'.join(lines), keyboard(rows), images


def render_endless(
    state: dict[str, Any], notice: str = '',
) -> tuple[str, dict[str, Any] | None, dict[str, str]]:
    status_name = {'active': '进行中', 'pending': '等待抽取下一图', 'failed': '已失败'}
    current_map = state.get('current_map', {}) or {}
    lines = []
    images: dict[str, str] = {}
    if utils.load_global_config().get('show_cover_image_switch', True):
        add_cover(lines, images, current_map, '地图封面')
    if notice:
        lines.append(f'**{notice}**')
    lines.append('**Celeste Endless**')
    lines.append(
        f"分数 **{int(state.get('clears', 0) or 0)}** · "
        f"剩余跳过 **{int(state.get('skips', 0) or 0)}** · "
        f"状态 **{status_name.get(state.get('status'), '未知')}**"
    )
    if current_map:
        lines.append('')
        lines.append(f"当前地图：**{current_map.get('name', '未知地图')}**")
        lines.append(f"**作者**：{current_map.get('author', '未知作者')}")
        page_url = utils.safe_str(current_map.get('page_url'))
        if page_url:
            lines.append(f'[查看地图页面]({page_url})')
    rows = [
        [
            button('通关', 'clst:en:clear', style=1, callback=True),
            button('全收集', 'clst:en:full_clear', callback=True),
            button('跳过', 'clst:en:skip', callback=True),
            button('坏图重抽', 'clst:en:reroll', callback=True),
        ],
        [
            button('撤销', 'clst:en:undo', callback=True),
            button('放弃', 'clst:en:give_up', callback=True),
            button('状态', 'clst:en:status', callback=True),
            button('记录', 'clst:en:record', callback=True),
        ],
        [
            button('结束挑战', 'clst:en:end', callback=True),
            button('查看详情', 'clst:en:detail', callback=True),
        ],
    ]
    if state.get('status') == 'pending':
        rows.insert(0, [button('继续抽下一图', 'clst:en:continue', style=1, callback=True)])
    return '\n'.join(lines), keyboard(rows), images
