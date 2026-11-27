"""把直播场次快照绘制成 960px 宽的本地报告。"""

from dataclasses import dataclass
from datetime import datetime
from functools import partial
from heapq import nsmallest
from math import ceil
from pathlib import Path

from . import bili_api, capabilities, store
from . import render_base as rb

# 参考 StarBot：按场次数据选配报告板块；排版、图表与隐私筛选独立实现。
_WIDTH = 960
_MARGIN = 28
_GAP = 16
_PAD = 24
_AVATAR = 92
_BUCKET_SECONDS = 300
_TOP = 5
_BG = '#ecf2f7'
_PAPER = '#ffffff'
_INSET = '#f2f6fa'
_BORDER = '#dbe6ef'
_INK = '#182a41'
_MUTED = '#50647b'
_NAVY = '#172c43'
_PALE = '#bcd5e6'
_ACCENT = '#087b89'
_ORCHID = '#7860b9'
_LOSS = '#ad3b56'
_TIERS = ((3, '舰长', '#176784'), (2, '提督', '#6746aa'), (1, '总督', '#986713'))
_TIER_STYLE = {level: (label, color) for level, label, color in _TIERS}


def _inline(text):
    return ' '.join(text.split()) if text else ''


def _line(draw, x, y, width, text, size, *, color=_INK, bold=False, align='left', min_size=None):
    font = rb.get_font(size, bold=bold)
    used = rb.text_width(draw, text, font) if len(text) <= 128 else float('inf')
    if min_size is not None:
        while used > width and size > min_size:
            size = max(min_size, size - 3)
            font = rb.get_font(size, bold=bold)
            used = rb.text_width(draw, text, font)
    if used > width:
        lines = rb.wrap_text(draw, text, font, width, max_lines=1)
        if not lines:
            return
        text = lines[0]
        used = rb.text_width(draw, text, font)
    if align == 'right':
        x += width - used
    elif align == 'center':
        x += (width - used) / 2
    rb.draw_text(draw, (x, y), text, font, color)


def _text(draw, x, y, text, size, *, color=_INK, bold=False):
    rb.draw_text(draw, (x, y), text, rb.get_font(size, bold=bold), color)


def _rect(draw, x, y, w, h, fill, *, radius=15, outline=None):
    rb.draw_rounded_rect(draw, (x, y, x + w - 1, y + h - 1), radius=radius, fill=fill, outline=outline)


def _cells(left, width, cols, gap=12):
    span = width - gap * (cols - 1)
    for i in range(cols):
        start = span * i // cols
        yield left + start + gap * i, span * (i + 1) // cols - start


def _money(gold, *, signed=False):
    whole, remainder = divmod(abs(gold), 1000)
    fraction = f'.{remainder:03d}'.rstrip('0') if remainder else ''
    sign = '-' if gold < 0 else ('+' if signed and gold else '')
    return f'{sign}¥{whole:,}{fraction}'


def _percent(part, total):
    value = 100 * part / total if total else 0
    return f'{value:.1f}'.rstrip('0').rstrip('.') + '%'


def _stamp(ts, fmt='%Y-%m-%d %H:%M:%S'):
    if ts is None:
        return '—'
    try:
        return datetime.fromtimestamp(ts).strftime(fmt)
    except (OSError, OverflowError, TypeError, ValueError):
        return '—'


def _person(row):
    return _inline(row.get('uname')) or (f"UID {row['uid']}" if row.get('uid') else '匿名观众')


def _duration(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f'{hours} 小时 {minutes:02d} 分 {secs:02d} 秒' if hours else f'{minutes} 分 {secs:02d} 秒'


def _avatar(avatar_url, name):
    path = bili_api.download_image(avatar_url) if avatar_url else None
    try:
        return rb.make_circle_avatar(path, _AVATAR, name)
    finally:
        if path is not None:
            bili_api.release_image(path)


def _header(canvas, draw, x, y, w, h, *, detail, name, title, stop, avatar_url):
    _rect(draw, x, y, w, h, _NAVY, radius=24)
    left, right = x + _PAD, x + w - _PAD
    _text(draw, left, y + 18, '直播报告', 22, color=_PALE, bold=True)
    live = detail.get('status') == 'live'
    badge = (right - 102, y + 18, right - 1, y + 51)
    rb.draw_rounded_rect(draw, badge, radius=16, fill='#1e535c' if live else '#314861')
    rb.draw_centered_text(draw, badge, '直播中' if live else '已结束', rb.get_font(18, bold=True),
                          '#baffe9' if live else '#e0ebf5')
    draw.ellipse((left - 2, y + 61, left + _AVATAR + 1, y + 62 + _AVATAR), outline='#54768f', width=2)
    with _avatar(avatar_url, name) as avatar:
        canvas.paste(avatar, (left, y + 63), avatar)
    text_x = left + _AVATAR + 23
    _line(draw, text_x, y + 56, right - text_x, name, 23, color=_PALE, bold=True)
    for i, line in enumerate(title):
        _text(draw, text_x, y + 86 + 46 * i, line, 36, color=_PAPER, bold=True)
    area = _inline(detail.get('area')) or '—'
    room = detail.get('room_id') or '—'
    _line(draw, text_x, y + h - 88, right - text_x, f'房间 {room}  /  分区 {area}', 18, color=_PALE)
    draw.line((left, y + h - 48, right - 1, y + h - 48), fill='#38536b')
    time_range = f"{_stamp(detail.get('start_at'))}  —  {_stamp(stop)}"
    _line(draw, left, y + h - 37, right - left - 244, time_range, 18, color=_PALE)
    _line(draw, right - 236, y + h - 38, 236, f"时长  {_duration(detail.get('duration', 0))}", 19,
          color=_PAPER, bold=True, align='right', min_size=15)


_TILE = 76
_TILE_GAP = 10
_PANEL_TOP = 60
_RANK_ROW = 34


def _tiles_height(count, columns):
    rows = (count + columns - 1) // columns
    return rows * (_TILE + _TILE_GAP) - _TILE_GAP


def _tiles(draw, x, y, w, metrics, columns):
    for row, start in enumerate(range(0, len(metrics), columns)):
        labels = metrics[start:start + columns]
        top = y + row * (_TILE + _TILE_GAP)
        for (label, value), (left, width) in zip(labels, _cells(x, w, len(labels), _TILE_GAP)):
            _rect(draw, left, top, width, _TILE, _INSET)
            tone = _ACCENT if value.startswith('+') else _LOSS if value.startswith('-') else _INK
            _line(draw, left + 13, top + 9, width - 26, label, 17, color=_MUTED)
            _line(draw, left + 13, top + 30, width - 26, value, 29, color=tone, bold=True, min_size=15)


def _rank_height(items):
    return 52 + _RANK_ROW * len(items)


def _rank_panel(draw, x, y, w, h, title, items):
    _rect(draw, x, y, w, h, _INSET)
    _text(draw, x + 14, y + 10, title, 20, bold=True)
    _line(draw, x + w - 82, y + 14, 68, 'TOP 5', 15, color=_ACCENT, bold=True, align='right')
    value_font = rb.get_font(17, bold=True)
    for i, (name, value) in enumerate(items, 1):
        top = y + 42 + (i - 1) * _RANK_ROW
        value_space = min(w // 2, ceil(rb.text_width(draw, value, value_font)))
        if i > 1:
            draw.line((x + 14, top - 1, x + w - 14, top - 1), fill=_BORDER)
        _text(draw, x + 14, top + 3, f'{i:02d}', 16, color=_ACCENT, bold=True)
        _line(draw, x + 47, top + 2, w - value_space - 71, name, 17)
        _line(draw, x + w - value_space - 14, top + 2, value_space, value, 17, bold=True, align='right', min_size=14)


def _rankings(detail, key, formatter):
    return tuple((_person(row), formatter(row['value'])) for row in detail.get('rankings', {}).get(key, ())[:_TOP])


@dataclass(slots=True)
class _Section:
    title: str
    metrics: tuple
    columns: int
    ranks: tuple = ()

    @property
    def height(self):
        height = _PANEL_TOP + _tiles_height(len(self.metrics), self.columns) + _PAD
        if self.ranks:
            height += _GAP + max(_rank_height(items) for _, items in self.ranks)
        return height

    def paint(self, _canvas, draw, x, y, w, h):
        _rect(draw, x, y, w, h, _PAPER, radius=22, outline=_BORDER)
        left, width = x + _PAD, w - 2 * _PAD
        _text(draw, left, y + 15, self.title, 27, bold=True)
        _tiles(draw, left, y + _PANEL_TOP, width, self.metrics, self.columns)
        if self.ranks:
            rank_y = y + _PANEL_TOP + _tiles_height(len(self.metrics), self.columns) + _GAP
            for (title, items), (cell_x, cell_w) in zip(self.ranks, _cells(left, width, len(self.ranks))):
                _rank_panel(draw, cell_x, rank_y, cell_w, y + h - rank_y - _PAD, title, items)


def _overview(detail, private):
    fields = (
        ('总弹幕', 'danmu'), ('互动人数', 'interactors'), ('高能峰值', 'online_peak'), ('看过人次', 'watched_peak'),
        ('进房', 'entry'), ('点赞', 'like'), ('关注', 'follow'), ('分享', 'share'),
    )
    metrics = [(label, f'{detail.get(key, 0):,}') for label, key in fields]
    if (fans := detail.get('fans_delta')) is not None:
        metrics.append(('净增粉丝', f'{fans:+,}' if fans else '0'))
    if not private:
        metrics.append(('付费总营收', _money(detail.get('gold', 0))))
    return _Section('本场概览', tuple(metrics), 4)


def _danmu_buckets(detail, stop):
    """按真实时钟分桶；未记录的区间为零，不压缩断流或空闲时间。"""
    counts = {}
    peak_minute, peak_rate = None, 0
    for row in detail.get('minutes', ()):
        count = row['danmu']
        if not count:
            continue
        minute = row['minute']
        slot = minute // _BUCKET_SECONDS
        counts[slot] = counts.get(slot, 0) + count
        if peak_minute is None or count > peak_rate or (count == peak_rate and minute < peak_minute):
            peak_minute, peak_rate = minute, count
    if not counts:
        return None
    first, last = min(counts), max(counts)
    if (start := detail.get('start_at')) is not None:
        first = min(first, int(start // _BUCKET_SECONDS))
    if stop is not None:
        last = max(last, ceil(stop / _BUCKET_SECONDS) - 1)
    return first, last, counts, peak_minute, peak_rate


def _trend_samples(first, last, counts):
    # 连续的零桶只保留两端，画出相同的平线而不按跨度分配内存。
    next_slot = first
    for slot, count in sorted(counts.items()):
        if slot > next_slot:
            yield next_slot, 0
            if slot - 1 > next_slot:
                yield slot - 1, 0
        yield slot, count
        next_slot = slot + 1
    if next_slot <= last:
        yield next_slot, 0
        if next_slot < last:
            yield last, 0


def _trend(draw, x, y, w, data):
    first, last, counts, peak_minute, peak_rate = data
    peak_slot = max(counts, key=lambda slot: (counts[slot], -slot))
    peak = counts[peak_slot]
    first_dt = datetime.fromtimestamp(first * _BUCKET_SECONDS)
    last_dt = datetime.fromtimestamp(last * _BUCKET_SECONDS)
    fmt = '%H:%M' if first_dt.date() == last_dt.date() else '%m-%d %H:%M'
    _text(draw, x, y, '每 5 分钟弹幕趋势', 20, bold=True)
    bucket_label = f'区间峰值 {_stamp(peak_slot * _BUCKET_SECONDS, fmt)} · {peak:,} 条'
    minute_label = f'单分钟峰值 {_stamp(peak_minute, fmt)} · {peak_rate:,} 条/分钟'
    _line(draw, x, y + 31, w // 2 - 12, bucket_label, 17, color=_ACCENT, bold=True, min_size=14)
    _line(draw, x + w // 2, y + 31, w - w // 2, minute_label, 17, color=_MUTED, align='right', min_size=14)
    top, bottom, right = y + 70, y + 178, x + w - 6
    widest = rb.text_width(draw, f'{peak:,}', rb.get_font(15))
    left = x + max(46, ceil(widest) + 14)

    def fraction(slot):
        return 0.5 if first == last else (slot - first) / (last - first)

    def px(slot):
        return left + (right - left) * fraction(slot)

    slots, values = zip(*_trend_samples(first, last, counts))
    for tick in (0, peak) if peak == 1 else (0, peak // 2, peak):
        py = bottom - (bottom - top) * tick / peak
        draw.line((left, py, right, py), fill=_BORDER)
        _line(draw, x, py - 9, left - x - 10, f'{tick:,}', 15, color=_MUTED, align='right')
    rb.draw_line_chart(draw, (left, top, right, bottom), values, fill=_ACCENT, grid=None,
                       x_fractions=(fraction(slot) for slot in slots))
    peak_x = px(peak_slot)
    draw.ellipse((peak_x - 5, top - 5, peak_x + 5, top + 5), fill=_ACCENT, outline=_PAPER, width=2)
    if first == last:
        _line(draw, left, bottom + 8, right - left, first_dt.strftime(fmt), 15, color=_MUTED, align='center')
    else:
        _text(draw, left, bottom + 8, first_dt.strftime(fmt), 15, color=_MUTED)
        _line(draw, left, bottom + 8, right - left, last_dt.strftime(fmt), 15, color=_MUTED, align='right')
        if last - first > 1:
            middle = (first + last) // 2
            center = px(middle)
            if center - left > 104 and right - center > 104:
                _line(draw, center - 58, bottom + 8, 116, _stamp(middle * _BUCKET_SECONDS, fmt), 15,
                      color=_MUTED, align='center')


def _danmu_ratio(canvas, draw, x, y, w, h, detail):
    _rect(draw, x, y, w, h, _INSET)
    _text(draw, x + 14, y + 10, '弹幕构成', 20, bold=True)
    text, emoji = detail.get('text_danmu', 0), detail.get('emoticon_danmu', 0)
    top = y + 46 + (h - 116) // 2
    rb.draw_ratio_bar(canvas, (x + 14, top, x + w - 14, top + 12), ((text, _ACCENT), (emoji, _ORCHID)))
    parts = (('文字弹幕', text, _ACCENT), ('表情弹幕', emoji, _ORCHID))
    for (label, count, color), (left, width) in zip(parts, _cells(x + 14, w - 28, len(parts))):
        _line(draw, left, top + 17, width, f'{label} · {count:,} 条', 16, color=_MUTED)
        _line(draw, left, top + 38, width, _percent(count, text + emoji), 22, color=color, bold=True)


def _danmu(canvas, draw, x, y, w, h, *, detail, trend, rank):
    _rect(draw, x, y, w, h, _PAPER, radius=22, outline=_BORDER)
    left, width = x + _PAD, w - 2 * _PAD
    _text(draw, left, y + 15, '弹幕分析', 27, bold=True)
    top = y + _PANEL_TOP
    if trend is not None:
        _trend(draw, left, top, width, trend)
        top += 221
    panels_h = y + h - top - _PAD
    if rank:
        (rx, rw), (kx, kw) = _cells(left, width, 2)
        _danmu_ratio(canvas, draw, rx, top, rw, panels_h, detail)
        _rank_panel(draw, kx, top, kw, panels_h, '弹幕话痨榜', rank)
    else:
        _danmu_ratio(canvas, draw, left, top, width, panels_h, detail)


def _popular(gifts):
    totals, names = {}, {}
    for gift in gifts:
        name, identifier = _inline(gift.get('gift_name')), gift.get('gift_id', '')
        key = ('id', identifier) if identifier else ('name', name)
        totals[key] = totals.get(key, 0) + gift.get('count', 0)
        if name:
            names.setdefault(key, name)
    top = nsmallest(_TOP, totals, key=lambda key: (-totals[key], names.get(key, ''), key))
    return tuple((names.get(key) or key[1] or '未命名礼物', f'{totals[key]:,} 件') for key in top)


def _commerce(detail, private):
    boxes, gifts, sc = None, None, None
    if not private and (count := detail.get('box_count', 0)) > 0:
        metrics = [('盲盒数量', f'{count:,} 个')]
        metrics.extend((label, _money(detail.get(key, 0), signed=key == 'box_profit')) for label, key in (
            ('盲盒投入', 'box_cost'), ('爆出价值', 'box_payout'), ('净盈亏', 'box_profit'),
        ))
        entries = _rankings(detail, 'box', partial(_money, signed=True))
        boxes = _Section('盲盒分析', tuple(metrics), 2, (('盲盒盈亏榜', entries),) if entries else ())
    if count := detail.get('gift_count', 0):
        free = detail.get('free_count', 0)
        metrics = [('付费礼物', f'{max(0, count - free):,} 件'), ('免费礼物', f'{free:,} 件')]
        ranks = ()
        if not private:
            metrics.append(('礼物金额', _money(detail.get('gift_gold', 0))))
            ranks = tuple((label, items) for label, items in (
                ('热门礼物', _popular(detail.get('gifts', ()))),
                ('礼物贡献榜', _rankings(detail, 'gift', _money)),
            ) if items)
        gifts = _Section('礼物分析', tuple(metrics), 2 if private else 3, ranks)
    if not private and (count := detail.get('sc_count', 0)) > 0:
        metrics = (('留言条数', f'{count:,} 条'), ('SC 总额', _money(detail.get('sc_gold', 0))))
        entries = _rankings(detail, 'sc', _money)
        sc = _Section('醒目留言分析', metrics, 2, (('SC 贡献榜', entries),) if entries else ())
    if boxes is not None and sc is None:
        boxes.columns = 4
    return [tuple(section for section in (boxes, sc) if section is not None), (gifts,) if gifts is not None else ()]


_GUARD_ROW = 40
_GUARD_TOP = 153


_MAX_GUARD_ROWS = 30


def _guards(canvas, draw, x, y, w, h, *, guards, levels, private, columns):
    _rect(draw, x, y, w, h, _PAPER, radius=22, outline=_BORDER)
    left, width = x + _PAD, w - 2 * _PAD
    _text(draw, left, y + 15, '大航海分析', 27, bold=True)
    total = sum(levels.values())
    rb.draw_ratio_bar(canvas, (left, y + 59, left + width, y + 73),
                      ((levels.get(level, 0), color) for level, _, color in _TIERS))
    for (level, label, color), (cell_x, cell_w) in zip(_TIERS, _cells(left, width, len(_TIERS))):
        count = levels.get(level, 0)
        draw.ellipse((cell_x, y + 89, cell_x + 9, y + 98), fill=color)
        _line(draw, cell_x + 17, y + 81, cell_w - 17, f'{label}  {count:,} 月 · {_percent(count, total)}', 17,
              color=_MUTED)
    _text(draw, left, y + 116, '本场上舰名单', 20, bold=True)
    font = rb.get_font(16, bold=True)
    cells = tuple(_cells(left, width, columns))
    visible = guards[:_MAX_GUARD_ROWS]
    for i, guard in enumerate(visible):
        row, col = divmod(i, columns)
        cell_x, cell_w = cells[col]
        top = y + _GUARD_TOP + row * _GUARD_ROW
        title, color = _TIER_STYLE.get(guard.get('guard_level'), ('大航海', _ACCENT))
        meta = f"{title} · {guard.get('months', 0):,} 月"
        if not private:
            meta += f"  {_money(guard.get('gold', 0))}"
        meta_width = min(cell_w * 2 // 3, ceil(rb.text_width(draw, meta, font)))
        _rect(draw, cell_x, top, cell_w, _GUARD_ROW - 5, _INSET, radius=9)
        _line(draw, cell_x + 10, top + 6, cell_w - meta_width - 31, _person(guard), 17)
        _line(draw, cell_x + cell_w - meta_width - 10, top + 6, meta_width, meta, 16, color=color,
              bold=True, align='right', min_size=14)
    if len(guards) > _MAX_GUARD_ROWS:
        extra = len(guards) - _MAX_GUARD_ROWS
        note_y = y + _GUARD_TOP + ceil(len(visible) / columns) * _GUARD_ROW + 4
        _line(draw, left, note_y, width, f'另有 {extra:,} 条上舰记录（总计 {len(guards):,} 条）', 16, color=_MUTED)


def render_live_report(detail, *, hide_revenue=False, avatar_url='', archive_dir=None) -> Path | None:
    """从统计快照生成发送用 PNG；不查询快照之外的直播数据。"""
    if rb.Image is None or not capabilities.can('live_report') or not isinstance(detail, dict) or not detail:
        return None
    try:
        name = _inline(detail.get('uname')) or (f"UID {detail['uid']}" if detail.get('uid') else '主播')
        start, stop = detail.get('start_at'), detail.get('end_at')
        if stop is None:
            if detail.get('status') == 'live' and start is not None:
                stop = start + detail.get('duration', 0)
            else:
                stop = detail.get('pending_end_at')
        panel_w = _WIDTH - 2 * _MARGIN
        title_w = panel_w - 2 * _PAD - _AVATAR - 23
        with rb.Image.new('RGB', (1, 1)) as measure:
            title = rb.wrap_text(rb.ImageDraw.Draw(measure), _inline(detail.get('title')) or '未命名直播',
                                 rb.get_font(36, bold=True), title_w, max_lines=2)
        overview = _overview(detail, hide_revenue)
        rows = [((222 + 46 * (len(title) - 1), partial(_header, detail=detail, name=name, title=title, stop=stop,
                                                       avatar_url=avatar_url)),),
                ((overview.height, overview.paint),)]
        if detail.get('danmu', 0):
            trend = _danmu_buckets(detail, stop)
            rank = _rankings(detail, 'danmu', lambda value: f'{value:,} 条')
            h = _PANEL_TOP + max(116, _rank_height(rank)) + _PAD + (221 if trend is not None else 0)
            rows.append(((h, partial(_danmu, detail=detail, trend=trend, rank=rank)),))
        for sections in _commerce(detail, hide_revenue):
            if sections:
                rows.append(tuple((section.height, section.paint) for section in sections))
        if guards := detail.get('guards'):
            shown = min(len(guards), _MAX_GUARD_ROWS)
            columns = min(shown, 3 if hide_revenue else 2)
            overflow = 28 if len(guards) > _MAX_GUARD_ROWS else 0
            h = _GUARD_TOP + ceil(shown / columns) * _GUARD_ROW + overflow + _PAD - 5
            rows.append(((h, partial(_guards, guards=guards, levels=detail.get('guard_levels', {}),
                                     private=hide_revenue, columns=columns)),))
        heights = [max(h for h, _ in row) for row in rows]
        anonymous = detail.get('all_anonymous', False)
        height = 2 * _MARGIN + sum(heights) + _GAP * len(rows) + (53 if anonymous else 24)
        with rb.Image.new('RGB', (_WIDTH, height), _BG) as canvas:
            draw = rb.ImageDraw.Draw(canvas)
            y = _MARGIN
            for row, h in zip(rows, heights):
                for (_, paint), (x, w) in zip(row, _cells(_MARGIN, panel_w, len(row), _GAP)):
                    paint(canvas, draw, x, y, w, h)
                y += h + _GAP
            _text(draw, _MARGIN + 4, y, f'由 BiliBiliNotify 生成 · {datetime.now():%Y-%m-%d %H:%M}', 17, color=_MUTED)
            if anonymous:
                _text(draw, _MARGIN + 4, y + 25, '本场互动记录均为匿名 · 登录 B站账号可展示完整观众榜单', 17,
                      color=_MUTED)
            return rb.save_generated_png(canvas, prefix='live-report', archive_dir=archive_dir)
    except (OSError, OverflowError, ValueError) as error:
        store.log(None, f'直播报告绘制失败：{type(error).__name__}', level=3)
        return None
