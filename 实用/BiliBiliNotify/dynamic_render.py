"""将订阅链路已取得的 B 站动态绘为本地 PNG。"""

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import bili_api, capabilities
from . import render_base as rb
from . import store

# 参考 StarBot：动态卡片按作者、正文、媒体、转发与原文入口组织，绘制独立实现。
_WIDTH = 880
_MAX_HEIGHT = 3400
_MARGIN = 28
_PADDING = 36
_PANEL_WIDTH = _WIDTH - 2 * _MARGIN
_SECTION_GAP = 20
_ORIGINAL_INSET = 20
_AVATAR = 72
_ORIGINAL_AVATAR = 50
_PHOTO_GAP = 10
_TEXT = '#25354a'
_MUTED = '#5b6d83'
_LINK = '#126f9e'
_BACKGROUND = '#ecf2f8'
_PANEL = '#ffffff'
_INSET = '#f4f7fb'
_BORDER = '#d9e4ef'
_TINT = '#e5f4fa'
_CHARGE_BG = '#fff4f7'
_CHARGE_BORDER = '#f4c6d7'
_CHARGE_TEXT = '#c03761'
_CHARGE_PILL = '#fb7299'
_VARIATION_SELECTORS = '\ufe0e\ufe0f'
_TYPES = {
    'DYNAMIC_TYPE_WORD': '文字动态',
    'DYNAMIC_TYPE_DRAW': '图文动态',
    'DYNAMIC_TYPE_FORWARD': '转发动态',
    'DYNAMIC_TYPE_AV': '视频动态',
    'DYNAMIC_TYPE_ARTICLE': '专栏动态',
    'DYNAMIC_TYPE_OPUS': '图文动态',
    'DYNAMIC_TYPE_LIVE_RCMD': '直播动态',
    'DYNAMIC_TYPE_COMMON_SQUARE': '分享动态',
    'DYNAMIC_TYPE_COMMON_VERTICAL': '分享动态',
    'DYNAMIC_TYPE_NONE': '原动态',
}
_RICH = re.compile(r'#[^#\r\n]+#|(?<![A-Za-z0-9_@])@[\w.-]+')
_HIGHLIGHTS = frozenset({'RICH_TEXT_NODE_TYPE_TOPIC', 'RICH_TEXT_NODE_TYPE_AT'})


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else ()


def _text(value):
    return value if isinstance(value, str) else ''


def _plain_spans(text):
    start = 0
    for match in _RICH.finditer(text):
        if start < match.start():
            yield text[start:match.start()], None
        yield match[0], _LINK
        start = match.end()
    if start < len(text):
        yield text[start:], None


def _body_spans(desc):
    text = _text(desc.get('text'))
    nodes = _list(desc.get('rich_text_nodes'))
    if not nodes:
        yield from _plain_spans(text)
        return
    if not text:
        for node in nodes:
            item = _mapping(node)
            value = _text(item.get('text')) or _text(item.get('orig_text'))
            if value:
                if _text(item.get('type')) in _HIGHLIGHTS:
                    yield value, _LINK
                else:
                    yield from _plain_spans(value)
        return
    # 以完整正文为准，按顺序标记富文本节点，节点之间的原始空行与字符照常保留。
    start = 0
    for node in nodes:
        item = _mapping(node)
        value = _text(item.get('text')) or _text(item.get('orig_text'))
        if not value or (index := text.find(value, start)) < 0:
            continue
        yield from _plain_spans(text[start:index])
        if _text(item.get('type')) in _HIGHLIGHTS:
            yield value, _LINK
        else:
            yield from _plain_spans(value)
        start = index + len(value)
    yield from _plain_spans(text[start:])


def _published(author):
    try:
        stamp = int(author.get('pub_ts') or 0)
        if stamp > 0:
            return datetime.fromtimestamp(stamp).strftime('%Y-%m-%d %H:%M')
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    return _text(author.get('pub_time'))


def _image_url(value):
    if isinstance(value, dict):
        value = value.get('url') or value.get('src')
    url = _text(value).strip()
    return f'https:{url}' if url.startswith('//') else url


@contextmanager
def _downloaded_image(url):
    path = bili_api.download_image(url) if url else None
    try:
        yield path
    finally:
        if path is not None:
            bili_api.release_image(path)


def _load_image(url, transform):
    with _downloaded_image(url) as path:
        return rb.load_bitmap(path, transform)


def _draw_line(draw, at, value, width, font, fill=_TEXT):
    lines = rb.wrap_text(draw, value, font, width, max_lines=1)
    if lines:
        rb.draw_text(draw, at, lines[0], font, fill)


def _header(canvas, draw, left, top, width, author, label, fallback_name, nested, *, badge_style=None):
    size = _ORIGINAL_AVATAR if nested else _AVATAR
    name_font = rb.get_font(26 if nested else 34, bold=True)
    note_font = rb.get_font(18 if nested else 22)
    badge_font = rb.get_font(18 if nested else 21, bold=True)
    name = _text(author.get('name')).strip() or fallback_name.strip() or 'B站用户'
    published = _published(author)
    with _downloaded_image(_image_url(author.get('face'))) as path:
        avatar = rb.make_circle_avatar(path, size, name)
    with avatar:
        canvas.paste(avatar, (left, top), avatar)
    badge_fill, badge_color = badge_style if badge_style is not None else (_TINT, _LINK)
    badge_width = round(rb.text_width(draw, label, badge_font)) + 26
    badge_left = left + width - badge_width
    badge_top = top + (size - 34) // 2
    badge = (badge_left, badge_top, left + width, badge_top + 34)
    rb.draw_rounded_rect(draw, badge, radius=17, fill=badge_fill)
    rb.draw_centered_text(draw, badge, label, badge_font, badge_color)
    text_left = left + size + (14 if nested else 18)
    text_width = badge_left - text_left - 14
    name_top = top if published else top + (12 if nested else 15)
    _draw_line(draw, (text_left, name_top), name, text_width, name_font)
    if published:
        _draw_line(draw, (text_left, top + (29 if nested else 41)), published, text_width, note_font, _MUTED)
    return top + size


@dataclass(slots=True)
class _Gallery:
    tiles: list
    height: int
    extra: int = 0

    def draw(self, canvas, draw, left, top):
        for x, y, width, height, bitmap in self.tiles:
            x, y = left + x, top + y
            if bitmap is None:
                rb.draw_rounded_rect(draw, (x, y, x + width - 1, y + height - 1), radius=14, fill=_BACKGROUND)
            else:
                with bitmap:
                    rb.paste_rounded(canvas, bitmap, (x, y), radius=14)
        if not self.extra:
            return
        label = f'+{self.extra}'
        font = rb.get_font(32, bold=True)
        badge_width = round(rb.text_width(draw, label, font)) + 24
        x, y, width, height, _ = self.tiles[-1]
        right, bottom = left + x + width - 10, top + y + height - 10
        box = (right - badge_width, bottom - 44, right, bottom)
        rb.draw_rounded_rect(draw, box, radius=18, fill='#253c52')
        rb.draw_centered_text(draw, box, label, font, 'white')


def _gallery(major, width, nested):
    urls = [url for item in _list(_mapping(major.get('draw')).get('items')) if (url := _image_url(item))]
    if not urls:
        urls = [url for item in _list(_mapping(major.get('opus')).get('pics')) if (url := _image_url(item))]
    if not urls:
        return None
    if len(urls) == 1:
        image = _load_image(urls[0], lambda source: rb.contain_image(source, (width, 720 if nested else 1200)))
        if image is None:
            return None
        return _Gallery([((width - image.width) // 2, 0, image.width, image.height, image)], image.height)
    count = min(9, len(urls))
    columns = 2 if count in (2, 4) else 3
    tile_width = (width - (columns - 1) * _PHOTO_GAP) // columns
    tile_height = min(176 if nested else 222, round(tile_width * 0.8))
    tiles = []
    for index, url in enumerate(urls[:count]):
        row, col = divmod(index, columns)
        bitmap = _load_image(url, lambda source: rb.fit_image(source, (tile_width, tile_height)))
        tiles.append((col * (tile_width + _PHOTO_GAP), row * (tile_height + _PHOTO_GAP),
                      tile_width, tile_height, bitmap))
    if not any(tile[-1] is not None for tile in tiles):
        return None
    rows = (count + columns - 1) // columns
    return _Gallery(tiles, rows * tile_height + (rows - 1) * _PHOTO_GAP, len(urls) - count)


@dataclass(slots=True)
class _Preview:
    label: str
    title: str
    summary: str
    thumbnail: object
    height: int = 150

    def draw(self, canvas, draw, left, top, width):
        box = (left, top, left + width - 1, top + self.height - 1)
        rb.draw_rounded_rect(draw, box, radius=16, fill=_INSET, outline=_BORDER)
        x = left + 16
        if self.thumbnail is not None:
            with self.thumbnail:
                rb.paste_rounded(canvas, self.thumbnail, (x, top + 14), radius=10)
            x += self.thumbnail.width + 16
        _draw_line(draw, (x, top + 15), self.label, left + width - x - 16, rb.get_font(18, bold=True), _LINK)
        font = rb.get_font(25, bold=True)
        available = left + width - x - 16
        title = rb.wrap_text(draw, self.title, font, available, max_lines=2)
        for index, line in enumerate(title):
            rb.draw_text(draw, (x, top + 42 + 30 * index), line, font, _TEXT)
        font = rb.get_font(19)
        summary = rb.wrap_text(draw, self.summary, font, available, max_lines=3 - len(title))
        for index, line in enumerate(summary):
            rb.draw_text(draw, (x, top + 47 + 30 * len(title) + 23 * index), line, font, _MUTED)


def live_share_info(major):
    """展开直播分享卡片的 JSON 内容，兼容平铺的直播资料。"""
    entry = _mapping(major.get('live_rcmd'))
    content = entry.get('content')
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (ValueError, RecursionError):
            content = None
    content = _mapping(content)
    return _mapping(content.get('live_play_info')) or content or entry


def _preview(major):
    for key, label in (('archive', '视频'), ('article', '专栏'), ('live_rcmd', '直播')):
        entry = live_share_info(major) if key == 'live_rcmd' else _mapping(major.get(key))
        if not entry:
            continue
        title = _text(entry.get('title'))
        detail = entry.get('desc') or entry.get('description') or entry.get('summary') or entry.get('digest')
        summary = _text(detail) or _text(_mapping(detail).get('text'))
        if key == 'live_rcmd' and not summary:
            areas = (_text(entry.get('parent_area_name')), _text(entry.get('area_name')))
            summary = ' · '.join(dict.fromkeys(area for area in areas if area))
        cover = _image_url(entry.get('cover') or entry.get('keyframe')) or next(
            (url for value in _list(entry.get('covers')) if (url := _image_url(value))), '',
        )
        if not (title or summary or cover):
            continue
        thumbnail = _load_image(cover, lambda source: rb.fit_image(source, (200, 122)))
        if title or summary or thumbnail is not None:
            return _Preview(label, title, summary, thumbnail)
    return None


def blocked_info(major):
    """解析充电专属等锁定动态（MAJOR_TYPE_BLOCKED）的档位徽章与提示文案。"""
    major = _mapping(major)
    blocked = _mapping(major.get('blocked'))
    if not blocked and _text(major.get('type')) != 'MAJOR_TYPE_BLOCKED':
        return None
    button = _mapping(blocked.get('button'))
    button_text = _text(button.get('text')).strip()
    title = _text(blocked.get('title')).strip()
    hint = _text(blocked.get('hint_message')).strip()
    blocked_type = blocked.get('blocked_type')
    if button_text:
        badge = button_text if button_text.endswith('动态') else f'{button_text}动态'
    elif blocked_type == 1:
        badge = '充电动态'
    else:
        badge = '专属动态'
    if not (title or hint):
        hint = '加入充电即可解锁观看此动态' if '充电' in badge else '当前动态需要解锁后查看'
    return {
        'badge': badge,
        'title': title,
        'hint': hint,
        'button_text': button_text or ('充电解锁' if '充电' in badge else '前往解锁'),
        'blocked_type': blocked_type,
    }


def _clean_display_text(value, font=None):
    text = value.translate({ord(ch): None for ch in _VARIATION_SELECTORS})
    if font is None or rb.Image is None:
        return text
    try:
        notdef = bytes(font.getmask('\uffff'))
    except (AttributeError, OSError, TypeError, ValueError):
        return text
    kept = []
    for ch in text:
        if ch in '\r\n\t ':
            kept.append(ch)
            continue
        try:
            if bytes(font.getmask(ch)) == notdef:
                continue
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        kept.append(ch)
    return ''.join(kept)


@dataclass(slots=True)
class _BlockedCard:
    pill: str
    heading: list
    detail: list
    nested: bool
    height: int

    def draw(self, canvas, draw, left, top, width):
        box = (left, top, left + width - 1, top + self.height - 1)
        rb.draw_rounded_rect(draw, box, radius=16, fill=_CHARGE_BG, outline=_CHARGE_BORDER)
        pad_x = 20 if self.nested else 24
        y = top + (16 if self.nested else 20)
        pill_font = rb.get_font(17 if self.nested else 19, bold=True)
        pill_h = 28 if self.nested else 32
        pill_w = round(rb.text_width(draw, self.pill, pill_font)) + 24
        pill_box = (left + pad_x, y, left + pad_x + pill_w, y + pill_h)
        rb.draw_rounded_rect(draw, pill_box, radius=pill_h // 2, fill=_CHARGE_PILL)
        rb.draw_centered_text(draw, pill_box, self.pill, pill_font, 'white')
        sub = '充电专属内容' if '充电' in self.pill else '专属锁定内容'
        sub_font = rb.get_font(17 if self.nested else 19)
        rb.draw_text(draw, (pill_box[2] + 12, y + (pill_h - (18 if self.nested else 20)) // 2 - 2),
                     sub, sub_font, _CHARGE_TEXT)
        y += pill_h + (12 if self.nested else 14)
        if self.heading:
            head_font = rb.get_font(22 if self.nested else 25, bold=True)
            head_step = 30 if self.nested else 35
            for line in self.heading:
                rb.draw_text(draw, (left + pad_x, y), line, head_font, _TEXT)
                y += head_step
            if self.detail:
                y += 4
        if self.detail:
            detail_font = rb.get_font(19 if self.nested else 21)
            detail_step = 26 if self.nested else 30
            for line in self.detail:
                rb.draw_text(draw, (left + pad_x, y), line, detail_font, _MUTED)
                y += detail_step


def _blocked_card(draw, major, width, nested):
    info = blocked_info(major)
    if info is None:
        return None
    pad_x = 20 if nested else 24
    inner_w = max(80, width - 2 * pad_x)
    head_font = rb.get_font(22 if nested else 25, bold=True)
    detail_font = rb.get_font(19 if nested else 21)
    pill_font = rb.get_font(17 if nested else 19, bold=True)
    raw_lines = [line.strip() for line in _clean_display_text(info['hint'], head_font).splitlines() if line.strip()]
    title = _clean_display_text(info['title'], head_font).strip()
    if title:
        head_src = title
        detail_src = '\n'.join(
            line.strip() for line in _clean_display_text(info['hint'], detail_font).splitlines() if line.strip()
        )
    elif len(raw_lines) >= 2:
        head_src = raw_lines[0]
        detail_lines = [
            line.strip() for line in _clean_display_text(info['hint'], detail_font).splitlines() if line.strip()
        ]
        detail_src = '\n'.join(detail_lines[1:])
    else:
        head_src = raw_lines[0] if raw_lines else ''
        detail_src = ''
    heading = rb.wrap_text(draw, head_src, head_font, inner_w, max_lines=3) if head_src else []
    detail = rb.wrap_text(draw, detail_src, detail_font, inner_w, max_lines=4) if detail_src else []
    pad_y = 16 if nested else 20
    pill_h = 28 if nested else 32
    head_step = 30 if nested else 35
    detail_step = 26 if nested else 30
    height = pad_y * 2 + pill_h + (12 if nested else 14) + len(heading) * head_step + len(detail) * detail_step
    if heading and detail:
        height += 4
    return _BlockedCard(_clean_display_text(info['button_text'], pill_font), heading, detail, nested, height)


@dataclass(slots=True)
class _Post:
    author: dict
    label: str
    display_name: str
    nested: bool
    width: int
    body: list
    title: list
    gallery: _Gallery | None
    preview: _Preview | None
    blocked: _BlockedCard | None = None
    badge_style: tuple | None = None

    @property
    def line_height(self):
        return 36 if self.nested else 43

    @property
    def body_font(self):
        return rb.get_font(25 if self.nested else 30)

    @property
    def title_font(self):
        return rb.get_font(28 if self.nested else 33, bold=True)

    @property
    def fixed_height(self):
        header = _ORIGINAL_AVATAR if self.nested else _AVATAR
        title = _SECTION_GAP + len(self.title) * self.line_height if self.title else 0
        return header + title + sum(
            block.height + _SECTION_GAP for block in (self.gallery, self.preview, self.blocked) if block is not None
        )

    @property
    def body_height(self):
        return _SECTION_GAP + len(self.body) * self.line_height if self.body else 0

    def fit_body(self, draw, height):
        if self.body_height > height:
            limit = (height - _SECTION_GAP) // self.line_height
            self.body = rb.limit_lines(draw, self.body, self.body_font, self.width, max_lines=limit)

    def draw(self, canvas, draw, left, top):
        top = _header(canvas, draw, left, top, self.width, self.author, self.label, self.display_name, self.nested,
                      badge_style=self.badge_style)
        if self.title:
            font = self.title_font
            top += _SECTION_GAP
            for line in self.title:
                rb.draw_text(draw, (left, top), line, font, _TEXT)
                top += self.line_height
        if self.body:
            font = self.body_font
            top += _SECTION_GAP
            for line in self.body:
                rb.draw_spans(draw, (left, top), line, font, fill=_TEXT)
                top += self.line_height
        if self.gallery is not None:
            top += _SECTION_GAP
            self.gallery.draw(canvas, draw, left, top)
            top += self.gallery.height
        if self.preview is not None:
            top += _SECTION_GAP
            self.preview.draw(canvas, draw, left, top, self.width)
            top += self.preview.height
        if self.blocked is not None:
            top += _SECTION_GAP
            self.blocked.draw(canvas, draw, left, top, self.width)
            top += self.blocked.height
        return top


def _prepare_post(draw, item, width, *, fallback_name='', nested=False):
    modules = _mapping(item.get('modules'))
    author = _mapping(modules.get('module_author'))
    dynamic = _mapping(modules.get('module_dynamic'))
    major = _mapping(dynamic.get('major'))
    opus = _mapping(major.get('opus'))
    desc = _mapping(dynamic.get('desc'))
    if not (_text(desc.get('text')) or _list(desc.get('rich_text_nodes'))):
        desc = _mapping(opus.get('summary'))
    if not desc and (tip := _text(_mapping(major.get('none')).get('tips'))):
        desc = {'text': tip}
    blocked = blocked_info(major)
    label = blocked['badge'] if blocked else _TYPES.get(_text(item.get('type')), '')
    badge_style = (_CHARGE_BG, _CHARGE_TEXT) if blocked else None
    if nested:
        label = f'原动态 · {label}' if label and label != '原动态' else '原动态'
    else:
        label = label or '发布动态'
    post = _Post(
        author, label, fallback_name, nested, width, [], [],
        _gallery(major, width, nested), _preview(major),
        _blocked_card(draw, major, width, nested), badge_style,
    )
    title = _text(opus.get('title'))
    if title and title != desc.get('text'):
        post.title = rb.wrap_text(draw, title, post.title_font, width, max_lines=2)
    post.body = rb.wrap_spans(draw, _body_spans(desc), post.body_font, width,
                              max_lines=_MAX_HEIGHT // post.line_height)
    return post


def _footer(canvas, draw, y, link, qr):
    left = _MARGIN + _PADDING
    right = canvas.width - left
    draw.line((left, y, right, y), fill=_BORDER, width=1)
    top = y + 16
    if qr is not None:
        canvas.paste(qr, (right - qr.width, top))
        right -= qr.width + 20
    if link:
        if qr is not None:
            top += 17
        label = '扫码查看 B站原动态' if qr is not None else 'B站原动态'
        rb.draw_text(draw, (left, top), label, rb.get_font(21, bold=True), _TEXT)
        _draw_line(draw, (left, top + 32), link, right - left, rb.get_font(19), _LINK)
    else:
        rb.draw_text(draw, (left, top), '哔哩哔哩 · 动态', rb.get_font(21, bold=True), _MUTED)


def render_dynamic_card(item, *, fallback_name='', link='', archive_dir=None) -> Path | None:
    """用关注流、空间动态或已归一化的 Opus 条目生成发送用卡片。"""
    if rb.Image is None or not capabilities.can('dynamic_image') or not isinstance(item, dict) or not item:
        return None
    identity = str(item.get('id_str') or '')
    link = _text(link).strip()
    if not link and re.fullmatch(r'[0-9]{1,25}', identity):
        link = f'https://t.bilibili.com/{identity}'
    qr = None
    try:
        qr = rb.make_qr_image(link, 88)
        footer = (qr.height + 16) if qr is not None else (76 if link else 45)
        width = _PANEL_WIDTH - 2 * _PADDING
        with rb.Image.new('RGB', (1, 1)) as probe:
            measure = rb.ImageDraw.Draw(probe)
            post = _prepare_post(measure, item, width, fallback_name=_text(fallback_name))
            orig_data = _mapping(item.get('orig'))
            orig = _prepare_post(measure, orig_data, width - 2 * _ORIGINAL_INSET, nested=True) if orig_data else None
            # 先容纳媒体与转发框；只有两段正文同时超出时才共享剩余版面。
            body_room = _MAX_HEIGHT - 2 * _MARGIN - 3 * _PADDING - footer - post.fixed_height
            if orig is not None:
                original_fixed = _SECTION_GAP + 2 * _ORIGINAL_INSET + orig.fixed_height
                body_room -= original_fixed
                post.fit_body(measure, max(body_room // 2, body_room - orig.body_height))
                orig.fit_body(measure, body_room - post.body_height)
                original_height = original_fixed + orig.body_height
            else:
                post.fit_body(measure, body_room)
                original_height = 0
        height = 2 * _MARGIN + 3 * _PADDING + footer + post.fixed_height + post.body_height + original_height
        with rb.Image.new('RGB', (_WIDTH, height), _BACKGROUND) as canvas:
            draw = rb.ImageDraw.Draw(canvas)
            rb.draw_rounded_rect(draw, (_MARGIN, _MARGIN, _WIDTH - _MARGIN - 1, height - _MARGIN - 1),
                                 radius=28, fill=_PANEL)
            left = _MARGIN + _PADDING
            top = post.draw(canvas, draw, left, left)
            if orig is not None:
                top += _SECTION_GAP
                bottom = top + original_height - _SECTION_GAP
                rb.draw_rounded_rect(draw, (left, top, left + width - 1, bottom - 1),
                                     radius=18, fill=_INSET, outline=_BORDER)
                orig.draw(canvas, draw, left + _ORIGINAL_INSET, top + _ORIGINAL_INSET)
                top = bottom
            _footer(canvas, draw, top + _PADDING, link, qr)
            return rb.save_generated_png(canvas, archive_dir=archive_dir)
    except (OSError, ValueError) as error:
        store.log(None, f'动态卡片绘制失败：{type(error).__name__}', level=3)
        return None
    finally:
        if qr is not None:
            qr.close()
