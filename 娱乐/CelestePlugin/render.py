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
    instruction: bool = False,
) -> dict[str, Any]:
    """构造键盘按钮：link=跳转链接，instruction=指令（点击填入/发送指令），否则回调。"""
    data_text = utils.safe_str(data)
    action_type = 0 if link else (1 if instruction else 2)
    return {
        'id': data_text[:64] or 'btn',
        'render_data': {'label': _label(text), 'visited_label': _label(text), 'style': style},
        'action': {
            'type': action_type,
            'permission': {'type': 2},
            'data': data_text,
            'unsupport_tips': '请更新 QQ 客户端后使用按钮',
        },
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
            '- `.clst today` 每人每天一张',
            '- `.clst 更新` 骰主手动重建索引',
            '',
            '**无尽挑战**',
            '- `.clst 无尽 开始` / `.clst 无尽 帮助`',
        ]
    )
    rows = [
        [
            button('随机一张', 'clst:rnd:1', style=1),
            button('随机 3 张', 'clst:rnd:3'),
            button('每日一图', 'clst:today'),
        ],
        [
            button('无尽模式', 'clst:en:help'),
            button('刷新帮助', 'clst:help'),
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
    lines.append('点下面的按钮直接看详情；翻页可以点按钮，也可以发送 上一页 / 下一页 / 跳页 3。')

    rows: list[list[dict[str, Any]]] = []
    row: list[dict[str, Any]] = []
    for offset, item in enumerate(page_items):
        index = start + offset
        row.append(button(item.get('name', ''), f'clst:sel:{index}', style=1))
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav = []
    if page_index > 0:
        nav.append(button('上一页', 'clst:pg:prev'))
    if page_index < page_count - 1:
        nav.append(button('下一页', 'clst:pg:next', style=1))
    nav.append(button('跳页', '.clst 跳页', instruction=True))
    rows.append(nav)
    return '\n'.join(lines), keyboard(rows)


def render_detail(
    detail: dict[str, Any],
    compact: bool = False,
    heading: str = '',
    show_random: bool = False,
) -> tuple[str, dict[str, Any] | None]:
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
    if heading:
        lines.append(f'**{heading}**')
    lines.append(f'**{title}**')
    lines.append(f"ID：{utils.safe_str(detail.get('item_type'), 'Mod')} {int(detail.get('id', 0) or 0)}")
    lines.append(
        f"作者/投稿者：{utils.safe_str(detail.get('author'), '未知作者')} · 分类：{_category_text(detail)}"
    )
    lines.append(_stats_line(detail))
    if credit_text:
        lines.append(f'完整署名：{credit_text}')
    lines.append('')
    if not compact:
        lines.append(description)
        lines.append('')
    page_url = utils.safe_str(detail.get('page_url'))
    if page_url:
        lines.append(f'[在 GameBanana 上查看]({page_url})')

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

    if show_random:
        rows.append([button('再来一张', 'clst:rnd:1'), button('随机 3 张', 'clst:rnd:3')])
    return '\n'.join(lines), keyboard(rows)


def render_random_summary(items: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    lines = [f'**随机地图 · {len(items)} 张**', '']
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
    rows = [
        [
            button('再来一张', 'clst:rnd:1', style=1),
            button('随机 3 张', 'clst:rnd:3'),
            button('每日一图', 'clst:today'),
        ]
    ]
    return '\n'.join(lines), keyboard(rows)


def render_endless(state: dict[str, Any], notice: str = '') -> tuple[str, dict[str, Any] | None]:
    status_name = {'active': '进行中', 'pending': '等待抽取下一图', 'failed': '已失败'}
    current_map = state.get('current_map', {}) or {}
    lines = []
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
            button('通关', 'clst:en:clear', style=1),
            button('全收集', 'clst:en:full_clear'),
            button('跳过', 'clst:en:skip'),
            button('坏图重抽', 'clst:en:reroll'),
        ],
        [
            button('撤销', 'clst:en:undo'),
            button('放弃', 'clst:en:give_up'),
            button('状态', 'clst:en:status'),
            button('记录', 'clst:en:record'),
        ],
        [
            button('结束挑战', 'clst:en:end'),
            button('查看详情', 'clst:en:detail'),
        ],
    ]
    if state.get('status') == 'pending':
        rows.insert(0, [button('继续抽下一图', 'clst:en:continue', style=1)])
    return '\n'.join(lines), keyboard(rows)
