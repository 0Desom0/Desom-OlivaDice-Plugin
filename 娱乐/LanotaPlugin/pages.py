"""曲库长页的数据与纯文本表示；渲染与发送不访问外部服务。"""

import base64
import datetime
import re
import time
from pathlib import Path

from . import function, portal, utils


DIFFICULTIES = ('whisper', 'acoustic', 'ultra', 'master')
RITMO_START = datetime.date(2021, 9, 7)
_RITMO_IMAGE = None


def _ritmo_image() -> str:
    """里莫立绘内联成 data URI：无头浏览器截图时不需要额外读文件。"""
    global _RITMO_IMAGE
    if _RITMO_IMAGE is None:
        path = Path(__file__).parent / 'Data' / 'ritmo.webp'
        try:
            payload = base64.b64encode(path.read_bytes()).decode('ascii')
            _RITMO_IMAGE = 'data:image/webp;base64,' + payload
        except OSError:
            _RITMO_IMAGE = ''
    return _RITMO_IMAGE


def _split_years_months_days(start, today):
    current = start
    years = 0
    while True:
        try:
            next_year = datetime.date(current.year + 1, current.month, current.day)
        except ValueError:
            next_year = datetime.date(current.year + 1, 2, 28)
        if next_year <= today:
            years += 1
            current = next_year
        else:
            break
    months = 0
    while True:
        try:
            next_month = datetime.date(
                current.year + (1 if current.month == 12 else 0),
                1 if current.month == 12 else current.month + 1, current.day,
            )
        except ValueError:
            break
        if next_month <= today:
            months += 1
            current = next_month
        else:
            break
    return years, months, (today - current).days


def ritmo_page(start=RITMO_START, today=None):
    """里莫昏睡计时页面；返回 (data, 纯文本回退)。"""
    today = today or datetime.date.today()
    years, months, days = _split_years_months_days(start, today)
    total_days = (today - start).days
    elapsed = f'{years}年{months}月{days}日'
    data = {
        'start': f'{start.year}年{start.month}月{start.day}日',
        'today': f'{today.year}年{today.month}月{today.day}日',
        'elapsed': elapsed,
        'years': years,
        'months': months,
        'days': days,
        'total': total_days,
        'range': f'{start:%Y.%m.%d} → {today:%Y.%m.%d}',
        'image': _ritmo_image(),
    }
    text = (
        f'【里莫绝赞昏睡时间】\n\n昏睡日期: {data["start"]}\n'
        f'今天日期: {data["today"]}\n\n已经过去:\n{elapsed}\n'
        f'总共: {total_days}天\n让我们看看可爱的小里莫\n什么时候才能睡醒吧~'
    )
    return data, text


LEVEL = re.compile(r'(\d{1,2})(\+?)')


def _duration_rows(songs, descending=True):
    dated = []
    for song in songs:
        match = re.fullmatch(r'(\d+):([0-5]\d)', str(song.get('time', '')).strip())
        if match:
            minutes, seconds = map(int, match.groups())
            if minutes or seconds:
                dated.append((minutes * 60 + seconds, song))
    dated.sort(key=lambda entry: entry[0], reverse=descending)
    average = round(sum(seconds for seconds, _ in dated) / len(dated)) if dated else 0

    def entry(song):
        return {'name': song.get('title'), 'id': song.get('id'), 'chapter': song.get('chapter'),
                'duration': song.get('time'), 'artist': song.get('artist'),
                'difficulty': 'Master', 'level': song.get('difficulty', {}).get('master', ''),
                'notes_count': None}

    return dated, average, entry


def time_all_pages(songs):
    """.la time all：一张图列出「全部长于 3 分钟」和「全部短于 2 分钟」，不截断不分页。"""
    dated, average, entry = _duration_rows(songs)
    average_text = f'{average // 60}:{average % 60:02}' if average else '—'
    long_rows = [entry(song) for seconds, song in dated if seconds > 180]
    short_rows = [entry(song) for seconds, song in reversed(dated) if seconds < 120]
    data = {
        'mode': 'all',
        'long': long_rows,
        'short': short_rows,
        'longCount': len(long_rows),
        'shortCount': len(short_rows),
        'average': average_text,
    }
    lines = [f'长于 3 分钟（共 {len(long_rows)} 首）',
             *[f'{i}. {row["name"]} · {row["duration"]} · {row["chapter"]}'
               for i, row in enumerate(long_rows, 1)],
             f'短于 2 分钟（共 {len(short_rows)} 首）',
             *[f'{i}. {row["name"]} · {row["duration"]} · {row["chapter"]}'
               for i, row in enumerate(short_rows, 1)]]
    return [(data, '\n'.join(lines))]


def time_page(songs):
    durations = []
    for song in songs:
        match = re.fullmatch(r'(\d+):([0-5]\d)', str(song.get('time', '')).strip())
        if match:
            minutes, seconds = map(int, match.groups())
            if minutes or seconds:
                durations.append((minutes * 60 + seconds, song))
    durations.sort(key=lambda entry: entry[0])
    average = round(sum(seconds for seconds, _ in durations) / len(durations)) if durations else 0

    def entry(song):
        return {'name': song.get('title'), 'id': song.get('id'), 'chapter': song.get('chapter'),
                'duration': song['time']}

    long = [entry(song) for seconds, song in reversed(durations) if seconds > 180]
    short = [entry(song) for seconds, song in durations if seconds < 120]
    summary = f'曲库 {len(songs)} 首 · 长曲 {len(long)} 首 · 短曲 {len(short)} 首'
    avg = f'{average // 60}:{average % 60:02}' if durations else '—'
    lines = [summary + f' · 平均时长 {avg}']
    for title, rows in [('长于 3 分钟', long), ('短于 2 分钟', short)]:
        lines.append(title)
        lines.extend(f'{i}. {r["name"]} · {r["duration"]} · {r["chapter"]}' for i, r in enumerate(rows, 1))
    return {'total': len(songs), 'average': avg, 'long_count': len(long), 'short_count': len(short),
            'long': long[:30], 'short': short[:30]}, '\n'.join(lines)


def notes_page(songs):
    rows = []
    for song in songs:
        for difficulty in DIFFICULTIES:
            level = song.get('difficulty', {}).get(difficulty)
            try:
                count = int(song.get('notes', {}).get(difficulty))
            except (TypeError, ValueError):
                continue
            if count > 0 and level not in (None, '', '未知'):
                rows.append({'name': song.get('title'), 'id': song.get('id'), 'chapter': song.get('chapter'),
                             'difficulty': difficulty.title(), 'level': level, 'notes': count})
    rows.sort(key=lambda row: -row['notes'])
    top = rows[:50]
    lines = ['物量最高的前 50 个谱面']
    lines.extend(f'{i}. {r["name"]} · {r["difficulty"]} · {r["notes"]} · {r["chapter"]}'
                 for i, r in enumerate(top, 1))
    return {'rows': top}, '\n'.join(lines)


def table_groups(songs, constants):
    by_chapter = {str(song.get('chapter')): song for song in songs}
    groups = {}
    for chapter, values in constants.items():
        if not isinstance(values, dict):
            continue
        song = by_chapter.get(str(chapter), {})
        for difficulty, value in values.items():
            diff = difficulty.lower()
            if diff not in DIFFICULTIES:
                continue
            constant = str(value).strip()
            order, plus = constant_order(constant)
            if order < 0:
                continue
            order += 0.05 if plus else 0
            level = str(song.get('difficulty', {}).get(diff, '未知'))
            row = {'constant': constant, 'level': level, 'difficulty': diff.title(),
                   'id': song.get('id', '—'), 'name': song.get('title') or f'未找到歌曲 ({chapter})'}
            groups.setdefault(level, []).append((order, row))

    def level_order(level):
        match = LEVEL.fullmatch(level)
        return (int(match[1]), bool(match[2])) if match else (-1, False)

    return {level: [row for _, row in sorted(groups[level], key=lambda pair: -pair[0])]
            for level in sorted(groups, key=level_order, reverse=True)}


def _tier_order(level):
    match = LEVEL.fullmatch(str(level).strip())
    if not match:
        return (0.0, 0)
    return (float(match.group(1)), 1 if match.group(2) else 0)


RANGE_SPLIT = re.compile(r'\s*(?:~|-|–|—)\s*')


def _trim_number(text):
    """去掉多余的零：15.0 → 15、15.90 → 15.9，保留结尾的 +。"""
    text = str(text).strip().replace('＋', '+')
    plus = text.endswith('+')
    body = text[:-1] if plus else text
    if '.' in body:
        body = body.rstrip('0').rstrip('.')
    return body + ('+' if plus else '')


def constant_label(value):
    """定数显示名：合并 15 与 15.0，把 15.8-15.9 写成 15.8 ~ 15.9。"""
    text = str(value).strip()
    parts = [part for part in RANGE_SPLIT.split(text) if part]
    if len(parts) == 2:
        return '%s ~ %s' % (_trim_number(parts[0]), _trim_number(parts[1]))
    return _trim_number(text)


def constant_order(value):
    """定数字符串的排序值：15.9、16、15+、15.8-15.9 都能量化（区间取中点）。"""
    text = str(value).strip()
    parts = [part for part in RANGE_SPLIT.split(text) if part]
    numbers = []
    plus = False
    for part in parts[:2]:
        part = part.strip()
        if part.endswith('+'):
            plus = True
            part = part[:-1]
        try:
            numbers.append(float(part))
        except ValueError:
            return (-1.0, 0)
    if not numbers:
        return (-1.0, 0)
    return (sum(numbers) / len(numbers), 1 if plus else 0)


def table_page(level, rows, group_by='constant'):
    # 行的定数统一成显示名（15.0 → 15，15.8-15.9 → 15.8 ~ 15.9）。
    rows = [dict(row, constant=constant_label(row.get('constant'))) for row in rows]
    buckets = {}
    for row in rows:
        if group_by == 'constant':
            key = constant_label(row.get('constant'))
        else:
            key = str(row.get('level') or level).strip()
        buckets.setdefault(key, []).append(row)
    tiers = [{'level': key, 'rows': buckets[key]} for key in buckets]
    if group_by == 'constant':
        tiers.sort(key=lambda tier: constant_order(tier['level']), reverse=True)
    else:
        tiers.sort(key=lambda tier: _tier_order(tier['level']), reverse=True)
    for tier in tiers:
        tier['count'] = len(tier['rows'])
    span = '、'.join(tier['level'] for tier in tiers)
    page_level = level
    if len(tiers) > 1:
        span = f'{tiers[0]["level"]} → {tiers[-1]["level"]}'
    head = '定数' if group_by == 'constant' else '标级'
    lines = [f'Lanota 民间定数表 · {head} {span}']
    # 合并小标级后，每行用自己那一档的标级，别一律套页面的 level。
    lines.extend(
        f'{r["constant"]} · {r["name"]}（{r["id"]}）· {r["difficulty"]} {r.get("level", level)}'
        for r in rows
    )
    return {'level': page_level, 'span': span, 'head': head, 'groupBy': group_by,
            'tiers': tiers, 'rows': rows}, '\n'.join(lines)


def fullcheck_rows(result):
    for item in result.get('results', []):
        name = f'{item.get("chapter", "?")} {item.get("title", "?")}'
        if not item.get('success'):
            yield f'失败 · {name}：{item.get("error") or "未知错误"}'
        elif fields := item.get('changed'):
            yield f'变化 · {name}：{", ".join(map(str, fields))}'
    for name in result.get('added_titles', []):
        yield f'新增 · {name}'
    for item in result.get('official_pending', []):
        yield f'待确认 · {item.get("chapter", "?")} {item.get("title", "?")}'


def version(kind):
    paths = [utils.get_song_list_path()]
    if kind == 'table':
        paths.append(utils.get_song_table_path())
    stamps = []
    for path in paths:
        try:
            stamps.append(Path(path).stat().st_mtime_ns)
        except FileNotFoundError:
            stamps.append(None)
    return stamps


def send(event, kind, caption, pages):
    """每个元素是一张 HTML 页及对应的完整文本；失败时只回退受影响的一页。"""
    mode = utils.get_reply_mode(event)
    if mode == 'text':
        utils.reply_long_plain_text(event, '\n\n'.join([caption, *(text for _, text in pages)]))
        return
    stamps = version(kind)
    images = []
    started = time.monotonic()
    for data, text in pages:
        # 一条消息最多等 12 秒：超出的页直接走文字，别让群员干等三张冷渲染。
        if images and time.monotonic() - started > 12.0:
            caption += '\n\n' + text
            continue
        image = portal.render_page(kind, data, stamps)
        if not image:
            image = function.create_text_image(text, user_id=utils.get_sender_id_from_event(event),
                                               bot_hash=utils.get_bot_hash_from_event(event, use_linked=True))
        if image:
            images.append(image)
        else:
            caption += '\n\n' + text
    if mode == 'markdown' and utils.reply_markdown(event, caption, images=images):
        return
    utils.reply_image_segments(event, images, caption)
