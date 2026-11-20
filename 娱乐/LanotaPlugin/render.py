"""QQ Markdown 列表及按键；只使用曲库实际提供的链接。"""
from urllib.parse import urlsplit


def button(label, data, *, kind, user_id=None, button_id=None, enter=False):
    label = label[:20]
    permission = {'type': 0, 'specify_user_ids': [user_id]} if user_id else {'type': 2}
    action = {'type': kind, 'data': data, 'permission': permission, 'unsupport_tips': '请更新 QQ 客户端后使用按钮'}
    if kind == 2:
        action.update(enter=enter, reply=False)
    result = {'render_data': {'label': label, 'visited_label': label, 'style': 0}, 'action': action}
    if kind == 1:
        result['id'] = button_id or data
    return result


def cmd_input(label, command, *, enter=False):
    return button(label, command, kind=2, enter=enter)


def keyboard(buttons):
    if not buttons:
        return None
    rows = [{'buttons': buttons[i:i + 4]} for i in range(0, min(len(buttons), 20), 4)]
    return {'content': {'rows': rows}}


def search_page(songs, page_index, page_size, *, callbacks_for=None):
    count = len(songs)
    total_pages = max(1, (count + page_size - 1) // page_size)
    page_index = max(0, min(page_index, total_pages - 1))
    lines = [f'查询到 {count} 首乐曲', f'第 {page_index + 1}/{total_pages} 页']
    start = page_index * page_size
    for n, song in enumerate(songs[start:start + page_size], start + 1):
        title = ' '.join(str(song.get('title') or '未知曲名').splitlines())
        lines.append(f'{n}. [{song.get("id", "?")}] {title}')
    controls = []
    if total_pages > 1:
        for label, direction, target in [('上一页', 'prev', page_index - 1), ('下一页', 'next', page_index + 1)]:
            if 0 <= target < total_pages:
                if callbacks_for:
                    controls.append(button(label, f'la:pg:{direction}', kind=1, user_id=callbacks_for))
                else:
                    controls.append(cmd_input(label, f'.la 跳页 {target + 1}', enter=True))
        controls.append(cmd_input('跳页', '.la 跳页 '))
        lines.append('输入序号查看详情，或点下方按钮翻页，输入 跳页[页码]，输入 end 结束')
    else:
        lines.append('输入序号查看详情，输入 end 结束')
    return '\n'.join(lines), keyboard(controls)


SONG_LIST_URL = 'https://lanota.fandom.com/wiki/Songs'


def detail_keyboard(song):
    links = [
        ('档案页', song.get('page_url')),
        ('全曲列表', SONG_LIST_URL),
        ('信息来源', song.get('page_url') or song.get('source_url')),
    ]
    if song.get('source_url'):
        links.append(('Lanota Wiki', song['source_url']))
    for source in song.get('external_sources') or ():
        if isinstance(source, dict):
            links.append((source.get('site') or '外部来源', source.get('url')))
    buttons = []
    seen = set()
    for name, url in links:
        if not isinstance(url, str) or url in seen:
            continue
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if parts.scheme not in ('https', 'http') or not parts.hostname:
            continue
        seen.add(url)
        label = {'delicious fruit': 'DF', 'lanota wiki': 'Wiki'}.get(name.casefold(), name)
        buttons.append(button(label, url, kind=0))
    return keyboard(buttons)


def selection_keyboard(entry, song_id, *, callbacks_for=None, regions=None):
    """详情入口按绑定区域生成：未绑定不给按钮，绑定两个服就给两个。"""
    today = entry == 'today'
    action = f'la:{entry}:detail'
    regions = [region for region in (regions or []) if region][:2]
    details = []
    for region in regions:
        label = '个人详情' + (f'·{REGION_LABELS.get(region, region)}' if len(regions) > 1 else '')
        if callbacks_for:
            details.append(button(
                label,
                action,
                kind=1,
                user_id=callbacks_for,
                button_id=f'{action}:{song_id}:{region}',
            ))
        else:
            command = f'.la info {song_id}' if region == 'global' else f'.la info {region} {song_id}'
            details.append(cmd_input(label, command, enter=True))
    random = cmd_input('换一首随机' if today else '再来一首', '.la random', enter=True)
    row = ([*details, random] if today else [random, *details])
    return keyboard(row)


REGION_LABELS = {'global': '国际服', 'china': '国服'}
