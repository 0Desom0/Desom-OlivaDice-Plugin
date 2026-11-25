# -*- encoding: utf-8 -*-
"""CelestePlugin 的 Markdown / 按钮页面渲染。

按钮回调统一用 `clst:<action>:<arg>` 作为 button_data，由 message.handle_button_click 处理。
纯文本回退仍然走 function.format_*，两套渲染共用同一份数据。
"""

from typing import Any

from urllib.parse import quote

from . import function
from . import utils


LABEL_LIMIT = 20
MAX_ROWS = 5
MAX_BUTTONS_PER_ROW = 4


def _label(text: Any, limit: int = LABEL_LIMIT) -> str:
    value = utils.safe_str(text).strip() or '未命名'
    return value[:limit]


def cmd_input(text: str, show: str | None = None) -> str:
    """QQ Markdown 蓝色可点文字：点一下把 text 填进输入框（不自动发送）。

    适配器里有同款 markdown_tag.cmd_input，但插件拿不到那个对象，
    这里按官方标签格式自己拼；show 是客户端显示的文字。
    """
    encoded = quote(str(text), safe='')
    tag = '<qqbot-cmd-input text="%s"' % encoded
    if show is not None:
        tag += ' show="%s"' % quote(str(show), safe='')
    return tag + ' reference="false" />'


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
            '> 前缀 `.clst`；中英文命令都能用，也可以直接点下面的按钮',
            '',
            '**查询 Query**',
            '- `.clst 关键词` / `.clst keyword` 标题搜索',
            '- `.clst id 424541` 按 GameBanana ID 精确查询 / exact lookup',
            '- `.clst 作者 名称` / `.clst author` 按投稿者查询',
            '- `.clst 分类 Maps` / `.clst category` 按主分类、子分类查询',
            '- `.clst 标签 关键词` / `.clst tag` 按子分类、标题与简介关键词查询',
            '',
            '**推荐 Picks**',
            '- `.clst 随机 [1-10]` / `.clst random` 全库随机地图',
            '- `.clst 发现` / `.clst pools` 六个挑图池：新图/老图 · 热门/冷门 · 好图/烂图',
            '  池名英文 new / old / hot / cold / good / bad，例如 `.clst latest 3`',
            '- `.clst today` 今日 Mod（每人每天一张，当天固定）',
            '- `.clst 更新` / `.clst update` 骰主手动重建索引',
            '',
            '**无尽挑战 Endless**',
            '- `.clst 无尽 开始` / `.clst endless start`',
            '- `.clst 无尽 帮助` / `.clst endless help`',
        ]
    )
    rows = [
        [
            button('发现', 'clst:pools', style=1, callback=True),
            button('随机一张', 'clst:rnd:1', callback=True),
        ],
        [
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
    show_pool: str = '',
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
    if show_pool:
        controls.extend(_pool_controls(show_pool))
    if show_endless:
        controls.append(button('返回无尽', 'clst:en:status', callback=True))
    if show_today:
        # 指令型：点一下只把命令填进输入框，让其他人也能抽自己那份。
        controls.append(button('我也要抽取', '.clst today'))
    if controls:
        # 一行最多 2 个按钮，否则客户端把标签截成「随机 3…」。
        control_rows = [controls[index : index + 2] for index in range(0, len(controls), 2)]
        rows = rows[: MAX_ROWS - len(control_rows)] + control_rows
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
        links = f'[查看详情]({page_url})' if page_url else ''
        # 蓝字：点一下把 `.clst id` 精确查询命令填进输入框，回车即查这一张。
        id_text = int(item.get('id', 0) or 0)
        if id_text > 0:
            links = f'{links} · {cmd_input(f".clst id {id_text}", "精确查询")}' if links else cmd_input(
                f'.clst id {id_text}', '精确查询'
            )
        if links:
            lines.append(links)
        lines.append('')
        if show_cover:
            add_cover(lines, images, item, f'地图封面 {index}')
    rows = [
        [
            button('再来一张', 'clst:rnd:1', style=1, callback=True),
            button('随机 3 张', 'clst:rnd:3', callback=True),
        ],
        [button('今日 Mod', 'clst:today', callback=True)],
    ]
    return '\n'.join(lines), keyboard(rows), images


def render_pool_home(
    pools: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    """发现页：六个池子的口径与池内张数，按钮点一下直接抽 1 张。"""
    lines = [
        '## 挑图池',
        '> 池子按本地索引现算，张数随收录变化',
        '',
    ]
    for pool in pools:
        label = utils.safe_str(pool.get('label'), '池子')
        rule = utils.safe_str(pool.get('rule'), '—')
        size = int(pool.get('pool_size', 0) or 0)
        lines.append(
            f'- **{label}** · {rule} · 池内 {size:,} 张' if size else f'- **{label}** · {rule} · 池内 0 张（暂时抽不了）'
        )
    lines.extend(
        [
            '',
            '点下面的按钮直接抽 1 张；要一次多张就发 `.clst 新图 3`（换成本页任意池名，英文 new / old / hot / cold / good / bad 也可以）。',
        ]
    )
    rows: list[list[dict[str, Any]]] = []
    row: list[dict[str, Any]] = []
    for index, pool in enumerate(pools):
        key = utils.safe_str(pool.get('key'))
        short = utils.safe_str(pool.get('short')) or utils.safe_str(pool.get('label'), '池子')
        # 有货的池子用高亮样式，空池子仍可点（点了会明确说池子是空的）。
        row.append(
            button(
                short,
                f'clst:pool:{key}:1',
                style=1 if index == 0 and pool.get('pool_size') else 0,
                callback=True,
            )
        )
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([button('返回帮助', 'clst:help', callback=True)])
    return '\n'.join(lines), keyboard(rows)


def render_pool_summary(
    items: list[dict[str, Any]],
    heading: str,
    pool_key: str,
    notice: str = '',
) -> tuple[str, dict[str, Any] | None, dict[str, str]]:
    """池内多张概要：标题带池口径与规模，条目结构与随机一致。"""
    lines = [f'**{heading}**', '']
    if notice:
        lines.append(f'提示：{notice}')
        lines.append('')
    images: dict[str, str] = {}
    show_cover = utils.load_global_config().get('show_cover_image_switch', True)
    for index, item in enumerate(items, start=1):
        category = ' / '.join(
            value for value in [item.get('category', ''), item.get('subcategory', '')] if value
        )
        meta = utils.safe_str(item.get('author', '未知作者'))
        if category:
            meta = f'{meta} · {category}'
        downloads = int(item.get('downloads', 0) or 0)
        if downloads > 0:
            likes = int(item.get('likes', 0) or 0)
            meta = f'{meta} · 下载 {downloads:,} · 赞 {likes:,}'
        lines.append(f'**{index}. {item.get("name", "未知地图")}**')
        lines.append(meta)
        page_url = utils.safe_str(item.get('page_url'))
        links = f'[查看详情]({page_url})' if page_url else ''
        id_text = int(item.get('id', 0) or 0)
        if id_text > 0:
            detail_cmd = cmd_input(f'.clst id {id_text}', '精确查询')
            links = f'{links} · {detail_cmd}' if links else detail_cmd
        if links:
            lines.append(links)
        lines.append('')
        if show_cover:
            add_cover(lines, images, item, f'地图封面 {index}')
    rows = [
        [
            button('再来一张', f'clst:pool:{pool_key}:1', style=1, callback=True),
            button('再来 3 张', f'clst:pool:{pool_key}:3', callback=True),
        ],
        [button('换个池', 'clst:pools', callback=True)],
    ]
    return '\n'.join(lines), keyboard(rows), images


def _pool_controls(pool_key: str) -> list[dict[str, Any]]:
    return [
        button('再来一张', f'clst:pool:{pool_key}:1', style=1, callback=True),
        button('再来 3 张', f'clst:pool:{pool_key}:3', callback=True),
        button('换个池', 'clst:pools', callback=True),
    ]


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
    pending = state.get('status') == 'pending'
    rows: list[list[dict[str, Any]]] = []
    if pending:
        rows.append(
            [
                button('继续抽下一图', 'clst:en:continue', style=1, callback=True),
                button('状态', 'clst:en:status', callback=True),
            ]
        )
    rows.extend(
        [
            [
                button('通关', 'clst:en:clear', style=1, callback=True),
                button('全收集', 'clst:en:full_clear', callback=True),
            ],
            [
                button('跳过', 'clst:en:skip', callback=True),
                button('坏图重抽', 'clst:en:reroll', callback=True),
            ],
            [
                button('撤销', 'clst:en:undo', callback=True),
                button('放弃', 'clst:en:give_up', callback=True),
            ],
        ]
    )
    if pending:
        # 等待抽下一图时没有当前地图，查看详情没有意义，正好省一行。
        rows.append(
            [
                button('记录', 'clst:en:record', callback=True),
                button('结束挑战', 'clst:en:end', callback=True),
            ]
        )
    else:
        rows.append(
            [
                button('状态', 'clst:en:status', callback=True),
                button('记录', 'clst:en:record', callback=True),
            ]
        )
        rows.append(
            [
                button('结束挑战', 'clst:en:end', callback=True),
                button('查看详情', 'clst:en:detail', callback=True),
            ]
        )
    return '\n'.join(lines), keyboard(rows), images


def render_endless_help() -> tuple[str, dict[str, Any] | None]:
    text = '\n'.join(
        [
            '## Celeste Endless',
            '> 地图从 WEGFan 镜像抽取，每次抽图都会带封面；中英文命令都能用',
            '',
            '**开始与查看 Start & Status**',
            '- `.clst 无尽 开始 [0-10]` / `.clst endless start` 开始挑战，默认 1 次跳过',
            '- `.clst 无尽 状态` / `.clst endless status` 查看分数、跳过次数与当前地图',
            '- `.clst 无尽 详情` / `.clst endless detail` 当前地图的完整 Mod 信息',
            '',
            '**结算当前地图 Settle**',
            '- `.clst 无尽 通关` / `.clst endless clear` 分数 +1，抽取下一图',
            '- `.clst 无尽 全收集` / `.clst endless fc` 分数 +1、跳过次数 +1，抽取下一图',
            '- `.clst 无尽 跳过` / `.clst endless skip` 消耗 1 次跳过；次数不足本局失败',
            '- `.clst 无尽 坏图` / `.clst endless reroll` 免费重抽，不计分也不消耗跳过',
            '',
            '**其它 Others**',
            '- `.clst 无尽 撤销` / `.clst endless undo` 撤销上一步操作',
            '- `.clst 无尽 放弃` / `.clst endless giveup` 本局失败并记录分数',
            '- `.clst 无尽 结束` / `.clst endless end` 主动结束并记录分数',
            '- `.clst 无尽 记录` / `.clst endless record` 查看个人战绩',
        ]
    )
    rows = [
        [
            button('开始挑战', 'clst:en:start', style=1, callback=True),
            button('状态', 'clst:en:status', callback=True),
        ],
        [
            button('记录', 'clst:en:record', callback=True),
            button('返回帮助', 'clst:help', callback=True),
        ],
    ]
    return text, keyboard(rows)


def render_endless_record(record: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None]:
    normalized = function.normalize_endless_record(record)
    result_name_dict = {
        'failed': '失败',
        'give_up': '放弃',
        'ended': '结束',
        'replaced': '重新开始',
    }
    lines = [
        '## 我的无尽记录',
        '',
        f'- **上次分数**：{normalized["last_endless_score"]}',
        f'- **最佳分数**：{normalized["best_endless_score"]}',
        f'- **已记录局数**：{normalized["total_runs"]}',
    ]
    if normalized.get('last_result'):
        lines.append(
            f'- **上次结果**：{result_name_dict.get(normalized["last_result"], normalized["last_result"])}'
        )
    rows = [
        [
            button('开始挑战', 'clst:en:start', style=1, callback=True),
            button('返回无尽', 'clst:en:status', callback=True),
        ]
    ]
    return '\n'.join(lines), keyboard(rows)
