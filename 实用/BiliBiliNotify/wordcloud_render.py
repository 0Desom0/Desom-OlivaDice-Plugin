"""直播弹幕词频提取与纯 Pillow 词云。"""

import re
import warnings
from collections import Counter, defaultdict
from datetime import datetime
from functools import cache
from math import fsum, log1p, sqrt
from pathlib import Path
from unicodedata import normalize

from . import capabilities
from . import render_base as rb
from . import store

try:
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message=r'pkg_resources is deprecated as an API.*', category=UserWarning)
        warnings.filterwarnings('ignore', message=r'.*pkg_resources.*', category=DeprecationWarning)
        import jieba
except ImportError:
    jieba = None

# 参考 StarBot：清洗直播表情与拉长语，按单观众的词频衰减刷屏权重。
_CJK = '\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ee5f\U0002f800-\U0002fa1f\U00030000-\U000323af'
_CHUNKS = re.compile(fr'[{_CJK}]+|[a-z0-9]+')
_NOISE = re.compile(fr'[^a-z0-9{_CJK}]+')
_EMOTE = re.compile(r'\[[^\[\]\r\n]*\]')
_EMOJI = re.compile(
    r'[#*0-9][\ufe0e\ufe0f]?\u20e3|[\u203c\u2049\u2122\u2139\u24c2\u3297\u3299]|[\U0001f000-\U0001faff]'
)
_URL = re.compile(
    r'(?:https?://|ftp://|www\.|(?<![a-z0-9.-])(?:[a-z0-9-]+\.)+(?:com|cn|net|org|tv|io)(?![a-z0-9.-]))'
    r"[a-z0-9:/?#[\]@!$&'()*+,;=.%_~-]*"
)
_REPEATS = (
    (re.compile('哈{3,}'), '哈哈'),
    (re.compile(r'(?<![a-z0-9])23{3,}(?![a-z0-9])'), '2333'),
    (re.compile(r'(?<![a-z0-9])6{3,}(?![a-z0-9])'), '666'),
    (re.compile('草{2,}'), '草'),
    (re.compile(r'(?<![a-z0-9])w{3,}(?![a-z0-9])'), 'www'),
)
_NUMERIC_MEMES = frozenset('88 233 2333 555 666 777 888 999 886 9494 114514'.split())
_STOPWORDS = frozenset('''
    这个 那个 这些 那些 这样 那样 什么 怎么 为什么 一个 一下 一些 一点 时候
    我们 你们 他们 她们 它们 这里 那里 现在 就是 然后 以及 还是 已经 比较
    不是 这么 那么 所以 因为 如果 但是 不过 还有 可能 应该 可以 能够 其实
    的了 的是 的人 的话 了吧 的吗 了吗 吗呢 呢吧
    the an and or for to of is it in on was are be with this that you your there here
'''.split())
_JIEBA_BLOCK = re.compile(r'[\u4e00-\u9fd5a-z0-9]+')


def _clean(text):
    text = normalize('NFKC', _EMOJI.sub(' ', text)).lower()
    text = _NOISE.sub(' ', _URL.sub(' ', _EMOTE.sub(' ', text))).strip()
    for pattern, replacement in _REPEATS:
        text = pattern.sub(replacement, text)
    return text


def _dictionary(words):
    return {word for text in words if isinstance(text, str) and (word := _clean(text))}


def _custom_matcher(words):
    # 正向最大匹配：位置相同时先取长词，英文热词不切进更长的英文单词。
    alternatives = []
    for word in sorted(words, key=lambda word: (-len(word), word)):
        left = r'(?<![a-z0-9])' if word[0].isascii() else ''
        right = r'(?![a-z0-9])' if word[-1].isascii() else ''
        alternatives.append(f'{left}{re.escape(word)}{right}')
    return re.compile('|'.join(alternatives)) if alternatives else None


def _parts(text, matcher):
    end = 0
    if matcher is not None:
        for match in matcher.finditer(text):
            if match.start() > end:
                yield text[end:match.start()], False
            yield match[0], True
            end = match.end()
    if end < len(text):
        yield text[end:], False


def _is_term(word):
    return word == '草' or (len(word) >= 2 and (not word.isdigit() or word in _NUMERIC_MEMES))


def _builtin_terms(text, excluded):
    for match in _CHUNKS.finditer(text):
        chunk = match[0]
        if chunk in excluded:
            continue
        if _is_term(chunk) and (chunk.isascii() or len(chunk) <= 6):
            yield chunk, True
        if not chunk.isascii():
            for width in range(2, min(4, len(chunk) - 1) + 1):
                for start in range(len(chunk) - width + 1):
                    yield chunk[start:start + width], False


def _viewer(row):
    uid = str(row.get('uid') or '')
    # 匿名弹幕合用一个保守的刷屏权重桶；不猜测人数，原始词频仍完整计数。
    return uid.lstrip('0') if uid.isascii() and uid.isdigit() else ''


def _weight(count):
    return count if count <= 3 else 3 + log1p(count - 3)


def extract_terms(danmu_rows, *, stopwords=(), custom_words=()):
    """返回 (按加权分数降序的词/原始次数/分数, 清洗后非空弹幕数, 分词引擎)。"""
    excluded = _STOPWORDS | _dictionary(stopwords)
    custom = _dictionary(custom_words)
    tokenizer = jieba.Tokenizer() if jieba is not None else None
    forced = custom
    if tokenizer is not None:
        forced = set()
        for word in sorted(custom):
            if _JIEBA_BLOCK.fullmatch(word):
                tokenizer.add_word(word)
            else:
                # 短语或扩展汉字超出 jieba 的分词块时，单独保留整条热词。
                forced.add(word)
    matcher = _custom_matcher(forced)

    by_word = defaultdict(Counter)
    exact_words = set()
    analyzed = 0
    for row in danmu_rows:
        text = row.get('text')
        if not isinstance(text, str) or not (text := _clean(text)):
            continue
        analyzed += 1
        viewer = _viewer(row)
        for part, explicit in _parts(text, matcher):
            if part.strip() in excluded:
                continue
            if explicit:
                candidates = ((part, True),)
            elif tokenizer is None:
                candidates = _builtin_terms(part, excluded)
            else:
                candidates = ((word, True) for word in tokenizer.cut(part) if word in custom or _is_term(word))
            for word, exact in candidates:
                if word in excluded:
                    continue
                by_word[word][viewer] += 1
                if exact:
                    exact_words.add(word)

    raw = {word: sum(viewers.values()) for word, viewers in by_word.items()}
    phrases = {word for word, count in raw.items() if count >= 2 and word not in exact_words}
    # 高频候选中，短片段只随同一长片段出现时，展示更完整的短语。
    redundant = set()
    for phrase in (exact_words | phrases) - custom:
        if phrase.isascii() or raw[phrase] < 2:
            continue
        for width in range(2, min(4, len(phrase) - 1) + 1):
            for start in range(len(phrase) - width + 1):
                shorter = phrase[start:start + width]
                if shorter in phrases and raw[shorter] == raw[phrase]:
                    redundant.add(shorter)
    terms = [(word, raw[word], fsum(_weight(count) for count in by_word[word].values()))
             for word in exact_words | (phrases - redundant)]
    terms.sort(key=lambda item: (-item[2], -item[1], item[0]))
    return terms, analyzed, 'builtin' if tokenizer is None else 'jieba'


_WIDTH, _HEIGHT = 960, 700
_PLOT_LEFT, _PLOT_TOP = 64, 180
_CELL = 4
_COLS, _ROWS = 208, 95
_INK = '#25354a'
_MUTED = '#536781'
_PLOT_BG = '#f4f7fb'
_OUTLINE = '#d9e4ef'
_COLORS = ('#aa315a', '#17668d', '#6e4b9d', '#146b62', '#315995', '#984723', '#254768')
_FILLED = b'\x01' * _COLS


def _glyph_checker(font):
    try:
        missing = font.getmask('\U0010ffff')
        missing_size, missing_pixels = missing.size, bytes(missing)
    except UnicodeEncodeError:
        missing_size, missing_pixels = None, None

    @cache
    def supported(char):
        if char == ' ':
            return True
        try:
            mask = font.getmask(char)
        except UnicodeEncodeError:
            return False
        return (mask.getbbox() is not None
                and (mask.size != missing_size or bytes(mask) != missing_pixels))

    return supported


@cache
def _spiral():
    """从中心向外按四像素网格作方形螺旋。"""
    x, y = _COLS // 2, _ROWS // 2
    points = [(x, y)]
    for side in range(1, max(_COLS, _ROWS) + 1):
        step = 1 if side % 2 else -1
        for _ in range(side):
            x += step
            if 0 <= x < _COLS and 0 <= y < _ROWS:
                points.append((x, y))
        for _ in range(side):
            y += step
            if 0 <= x < _COLS and 0 <= y < _ROWS:
                points.append((x, y))
    return points


def _reserve(grid, cursors, cols, rows):
    if cols > _COLS or rows > _ROWS:
        return None
    key = (cols, rows)
    points = _spiral()
    first = cursors.get(key, 0)
    half_cols, half_rows = cols // 2, rows // 2
    left_limit, top_limit = _COLS - cols, _ROWS - rows
    for index in range(first, len(points)):
        cx, cy = points[index]
        x, y = cx - half_cols, cy - half_rows
        if not (0 <= x <= left_limit and 0 <= y <= top_limit):
            continue
        offsets = range(y * _COLS + x, (y + rows) * _COLS + x, _COLS)
        for offset in offsets:
            if grid.find(b'\x01', offset, offset + cols) >= 0:
                break
        else:
            cells = _FILLED[:cols]
            for offset in offsets:
                grid[offset:offset + cols] = cells
            # 已试过的位置对相同尺寸只会越来越拥挤。
            cursors[key] = index + 1
            return x, y
    cursors[key] = len(points)
    return None


def _draw_words(draw, terms, word_limit):
    grid = bytearray(_COLS * _ROWS)
    cursors = {}
    lead = terms[0][2]
    spread = 28 + 52 / sqrt(max(1, min(word_limit, len(terms)) / 8))
    placed = 0
    for word, _, score in terms:
        desired = round(16 + spread * (score / lead) ** 0.58)
        for size in sorted({desired, max(16, desired * 3 // 4), max(16, desired * 4 // 7), 16}, reverse=True):
            font = rb.get_font(size, bold=True)
            x0, y0, x1, y1 = font.getbbox(word)
            width, height = x1 - x0, y1 - y0
            cols, rows = (width + _CELL - 1) // _CELL + 2, (height + _CELL - 1) // _CELL + 2
            slot = _reserve(grid, cursors, cols, rows)
            if slot is None:
                continue
            x, y = slot
            left = _PLOT_LEFT + x * _CELL + (cols * _CELL - width) // 2 - x0
            top = _PLOT_TOP + y * _CELL + (rows * _CELL - height) // 2 - y0
            rb.draw_text(draw, (left, top), word, font, _COLORS[placed % len(_COLORS)])
            placed += 1
            if placed >= word_limit:
                return placed
            break
    return placed


def _stamp(timestamp):
    if timestamp is None:
        return ''
    try:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
    except (OSError, OverflowError, ValueError):
        return ''


def _draw_header(draw, detail, analyzed, engine, supports, chinese):
    small = rb.get_font(15, bold=True)
    accent = _COLORS[0]
    draw.ellipse((48, 41, 57, 50), fill=accent)
    rb.draw_text(draw, (66, 36), 'BILIBILI  /  LIVE ANALYTICS', small, accent)
    rb.draw_text(draw, (46, 58), '弹幕词云' if chinese else 'Danmu Word Cloud', rb.get_font(40, bold=True), _INK)

    medium = rb.get_font(18, bold=True)
    name = ' '.join((detail.get('uname') or '').split())
    name = ''.join(char for char in name if supports(char)).strip()
    x = 48
    if label := rb.wrap_text(draw, name, medium, 230, max_lines=1):
        rb.draw_text(draw, (x, 115), label[0], medium, _INK)
        x += round(rb.text_width(draw, label[0], medium)) + 20
    start, end = _stamp(detail.get('start_at')), _stamp(detail.get('end_at'))
    if start:
        end = end or ('至今' if chinese else 'NOW')
        rb.draw_text(draw, (x, 116), f'{start}  –  {end}', medium, _MUTED)

    rb.draw_rounded_rect(draw, (652, 38, 912, 107), radius=16, fill=_PLOT_BG, outline=_OUTLINE)
    draw.line((782, 51, 782, 93), fill=_OUTLINE, width=1)
    rb.draw_text(draw, (670, 49), '分析弹幕' if chinese else 'MESSAGES', small, _MUTED)
    rb.draw_text(draw, (800, 49), '分词引擎' if chinese else 'TOKENIZER', small, _MUTED)
    rb.draw_text(draw, (670, 73), f'{analyzed:,}', medium, _INK)
    engine_title = '内置分词' if chinese and engine == 'builtin' else engine
    rb.draw_text(draw, (800, 73), engine_title, medium, _INK)


def _draw_footer(draw, terms, chinese):
    font = rb.get_font(17, bold=True)
    title = 'TOP 5 热词' if chinese else 'TOP 5  /  RAW FREQUENCY'
    rb.draw_text(draw, (48, 595), title, font, _INK)
    note = '字号按防刷屏权重' if chinese else 'SIZE WEIGHTED FOR REPEATS'
    small = rb.get_font(14, bold=True)
    rb.draw_text(draw, (912 - rb.text_width(draw, note, small), 597), note, small, _MUTED)
    top = sorted(terms, key=lambda item: (-item[1], item[0]))[:5]
    for index, (word, count, _) in enumerate(top):
        left = 48 + 174 * index
        right = left + 166
        rb.draw_rounded_rect(draw, (left, 627, right, 660), radius=16, fill=_PLOT_BG, outline=_OUTLINE)
        raw = f'{count:,}'
        count_x = right - 12 - rb.text_width(draw, raw, small)
        label = rb.wrap_text(draw, word, font, count_x - left - 22, max_lines=1)
        if label:
            rb.draw_text(draw, (left + 12, 632), label[0], font, _INK)
        rb.draw_text(draw, (count_x, 635), raw, small, _COLORS[index])


def render_wordcloud(detail, *, word_limit=80, stopwords=(), custom_words=(), archive_dir=None) -> Path | None:
    """生成 960 × 700 弹幕词云；没有可展示的词时返回 None。"""
    if rb.Image is None or not capabilities.can('wordcloud') or not isinstance(detail, dict) or word_limit < 1:
        return None
    terms, analyzed, engine = extract_terms(
        detail.get('danmu_rows', ()), stopwords=stopwords, custom_words=custom_words,
    )
    if not terms:
        return None
    try:
        supports = _glyph_checker(rb.get_font(24, bold=True))
        visible = [term for term in terms if all(supports(char) for char in term[0])]
        if not visible:
            return None
        chinese = all(supports(char) for char in '弹幕词云至今分析分词引擎内置原始频字号按防刷屏权重')
        with rb.Image.new('RGB', (_WIDTH, _HEIGHT), '#ecf2f8') as image:
            draw = rb.ImageDraw.Draw(image)
            rb.draw_rounded_rect(draw, (20, 20, 939, 679), radius=28, fill='#ffffff')
            _draw_header(draw, detail, analyzed, engine, supports, chinese)
            rb.draw_rounded_rect(draw, (44, 162, 915, 576), radius=22, fill=_PLOT_BG, outline=_OUTLINE)
            for y in range(192, 558, 36):
                for x in range(73, 902, 36):
                    draw.ellipse((x, y, x + 1, y + 1), fill='#dce6f1')
            if not _draw_words(draw, visible, word_limit):
                return None
            _draw_footer(draw, visible, chinese)
            return rb.save_generated_png(image, subdir='generated', prefix='wordcloud', archive_dir=archive_dir)
    except (OSError, ValueError) as error:
        store.log(None, f'弹幕词云绘制失败：{type(error).__name__}', level=3)
        return None
