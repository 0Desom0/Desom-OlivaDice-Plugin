"""Pillow 可选绘图底座，供动态卡片、报告与词云共用。"""

import re
from functools import lru_cache
from itertools import islice
from os import environ
from pathlib import Path
from shutil import copyfile
from struct import error as StructError
from tempfile import NamedTemporaryFile
from time import time

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = ImageChops = ImageDraw = ImageFont = ImageOps = None

try:
    import qrcode
except ImportError:
    qrcode = None

from . import capabilities, config, store

_RESAMPLE = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', None)
_TOKENS = re.compile(r'\r\n?|\n|[^\S\r\n]+|[!-~]+|.')
_FILENAME_PREFIX = 'generated-'
_TEMP_LIMIT = 128
_TEMP_MAX_AGE = 24 * 60 * 60
_TEMP_MIN_AGE = 120
_ARCHIVE_LIMIT = 256
_MAX_SOURCE_PIXELS = 16_000_000
_MAX_SOURCE_SIDE = 12_000


def _font_candidates(bold):
    windows = Path(environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    yield windows / ('msyhbd.ttc' if bold else 'msyh.ttc'), 0
    yield windows / ('Dengb.ttf' if bold else 'Deng.ttf'), 0
    if bold:
        yield windows / 'msyh.ttc', 0
    yield windows / 'simhei.ttf', 0
    yield windows / 'simsun.ttc', 0

    system_fonts = Path('/System/Library/Fonts')
    yield system_fonts / 'PingFang.ttc', 0
    yield system_fonts / 'STHeiti Medium.ttc', 0
    yield system_fonts / 'Supplemental/Songti.ttc', 0
    yield Path('/Library/Fonts/Arial Unicode.ttf'), 0

    weight = 'Bold' if bold else 'Regular'
    roots = [Path('/usr/share/fonts'), Path('/usr/local/share/fonts')]
    if data_home := environ.get('XDG_DATA_HOME'):
        roots.append(Path(data_home) / 'fonts')
    elif home := environ.get('HOME'):
        roots.append(Path(home) / '.local/share/fonts')
    for root in roots:
        for folder in ('opentype/noto', 'google-noto-cjk', 'google-noto-sans-cjk-fonts', 'noto-cjk', 'noto', ''):
            yield root / folder / f'NotoSansCJK-{weight}.ttc', 2
            if bold:
                yield root / folder / 'NotoSansCJK-Regular.ttc', 2
            yield root / folder / f'NotoSansSC-{weight}.otf', 0
        yield root / 'adobe-source-han-sans-cn-fonts' / f'SourceHanSansSC-{weight}.otf', 0
        yield root / 'truetype/wqy/wqy-microhei.ttc', 0
        yield root / 'truetype/wqy/wqy-zenhei.ttc', 0
        yield root / 'TTF/wqy-microhei.ttc', 0
    yield 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf', 0


@lru_cache(maxsize=2)
def _font_source(bold):
    for path, index in _font_candidates(bold):
        try:
            if isinstance(path, Path) and not path.is_file():
                continue
            ImageFont.truetype(str(path), 24, index=index)
        except OSError:
            continue
        return str(path), index
    return None


@lru_cache(maxsize=32)
def get_font(size, *, bold=False):
    """缓存字体路径与常用字号；缺少 CJK 字体时仍使用 Pillow 默认字体。"""
    if ImageFont is None:
        return None
    if source := _font_source(bold):
        try:
            return ImageFont.truetype(source[0], size, index=source[1])
        except OSError:
            # 缓存后系统字体仍可能被移除。
            _font_source.cache_clear()
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def text_width(draw, text, font):
    try:
        return draw.textlength(text, font=font)
    except UnicodeEncodeError:
        return draw.textlength(text.encode('latin-1', 'replace').decode('latin-1'), font=font)


def draw_text(draw, position, text, font, fill):
    try:
        draw.text(position, text, font=font, fill=fill)
    except UnicodeEncodeError:
        draw.text(position, text.encode('latin-1', 'replace').decode('latin-1'), font=font, fill=fill)


def draw_centered_text(draw, box, text, font, fill):
    left, top, right, bottom = box
    try:
        x0, y0, x1, y1 = font.getbbox(text)
    except UnicodeEncodeError:
        text = text.encode('latin-1', 'replace').decode('latin-1')
        x0, y0, x1, y1 = font.getbbox(text)
    draw.text(((left + right - x0 - x1) / 2, (top + bottom - y0 - y1) / 2), text, font=font, fill=fill)


def _append_span(line, text, color):
    if line and line[-1][1] == color:
        line[-1] = (line[-1][0] + text, color)
    else:
        line.append((text, color))


def _wrapped_lines(draw, spans, font, max_width):
    line, spaces = [], []
    used = space_width = 0
    seen_text = False
    for text, color in spans:
        for match in _TOKENS.finditer(text):
            token = match[0]
            seen_text = True
            if token in ('\n', '\r', '\r\n'):
                yield line
                line, spaces = [], []
                used = space_width = 0
                continue
            if token.isspace():
                if line:
                    token = token.expandtabs(4)
                    spaces.append((token, color))
                    space_width += text_width(draw, token, font)
                continue
            # 拉长的英文或地址按字回绕；避免一次测量异常长的输入。
            advance = text_width(draw, token, font) if len(token) <= 1024 else float('inf')
            if line and used + space_width + advance > max_width:
                yield line
                line, used = [], 0
            if line:
                for gap, gap_color in spaces:
                    _append_span(line, gap, gap_color)
                used += space_width
            spaces, space_width = [], 0
            if advance <= max_width:
                _append_span(line, token, color)
                used += advance
                continue
            for char in token:
                advance = text_width(draw, char, font)
                if line and used + advance > max_width:
                    yield line
                    line, used = [], 0
                if advance <= max_width:
                    _append_span(line, char, color)
                    used += advance
    if seen_text:
        yield line


def wrap_spans(draw, spans, font, max_width, *, max_lines=None):
    """按像素换行；输入为 (文字, 色值)，输出逐行保留颜色与段落。"""
    if max_width <= 0 or (max_lines is not None and max_lines <= 0):
        return []
    wrapped = _wrapped_lines(draw, spans, font, max_width)
    if max_lines is None:
        return list(wrapped)
    lines = list(islice(wrapped, max_lines + 1))
    return limit_lines(draw, lines, font, max_width, max_lines=max_lines)


def limit_lines(draw, lines, font, max_width, *, max_lines):
    """在画布实际容量确定后截短已换行文字，保持最后一行的颜色。"""
    if max_lines <= 0:
        return []
    if len(lines) <= max_lines:
        return lines
    overflow = lines[max_lines]
    lines = lines[:max_lines]
    last = lines[-1] = lines[-1].copy()
    color = last[-1][1] if last else (overflow[0][1] if overflow else None)
    ellipsis = '…'
    ellipsis_width = text_width(draw, ellipsis, font)
    while last and sum(text_width(draw, text, font) for text, _ in last) + ellipsis_width > max_width:
        text, span_color = last.pop()
        if trimmed := text[:-1].rstrip():
            last.append((trimmed, span_color))
    if ellipsis_width <= max_width:
        _append_span(last, ellipsis, color)
    return lines


def wrap_text(draw, text, font, max_width, max_lines=None):
    lines = wrap_spans(draw, ((text, None),), font, max_width, max_lines=max_lines)
    return [''.join(text for text, _ in line) for line in lines]


def draw_spans(draw, position, line, font, *, fill):
    x, y = position
    for text, color in line:
        draw_text(draw, (x, y), text, font, fill if color is None else color)
        x += text_width(draw, text, font)


def draw_rounded_rect(draw, box, *, radius=16, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _rounded_mask(size, radius):
    width, height = (side * 2 for side in size)
    mask = Image.new('L', (width, height))
    draw_rounded_rect(ImageDraw.Draw(mask), (0, 0, width - 1, height - 1), radius=radius * 2, fill=255)
    return mask.resize(size, _RESAMPLE)


def paste_rounded(canvas, image, position, *, radius=16):
    mask = _rounded_mask(image.size, radius)
    if 'A' in image.getbands():
        mask = ImageChops.multiply(mask, image.getchannel('A'))
    canvas.paste(image, position, mask)


def load_bitmap(image_path, transform):
    """限尺寸解码本地图像并变换；下载租约由调用方释放。"""
    if Image is None or image_path is None:
        return None
    try:
        with Image.open(image_path) as image:
            if image.width * image.height > _MAX_SOURCE_PIXELS or max(image.size) > _MAX_SOURCE_SIDE:
                return None
            orientation = image.getexif().get(274, 1)  # EXIF Orientation
            if orientation in (2, 3, 4, 5, 6, 7, 8):
                with ImageOps.exif_transpose(image) as oriented:
                    return _transform_bitmap(oriented, transform)
            return _transform_bitmap(image, transform)
    except (OSError, ValueError, SyntaxError, EOFError, StructError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None


def _transform_bitmap(image, transform):
    alpha = 'A' in image.getbands() or 'transparency' in image.info
    mode = 'RGBA' if alpha else 'RGB'
    if image.mode == mode:
        return transform(image)
    with image.convert(mode) as bitmap:
        return transform(bitmap)


def _circle_avatar(image, size):
    avatar = fit_image(image, (size, size))
    if avatar.mode != 'RGBA':
        avatar = avatar.convert('RGBA')
    mask = _rounded_mask(avatar.size, size // 2)
    avatar.putalpha(ImageChops.multiply(mask, avatar.getchannel('A')))
    return avatar


def make_circle_avatar(image_path_or_none, size, fallback_text):
    """生成圆形头像；缺图或坏图时显示带首字的圆形底色。"""
    if Image is None:
        return None
    avatar = load_bitmap(image_path_or_none, lambda bitmap: _circle_avatar(bitmap, size))
    if avatar is not None:
        return avatar
    avatar = Image.new('RGBA', (size, size), '#e5f4fa')
    avatar.putalpha(_rounded_mask(avatar.size, size // 2))
    glyph = fallback_text.strip()[:1]
    if glyph:
        draw_centered_text(ImageDraw.Draw(avatar), (0, 0, size, size), glyph,
                           get_font(max(1, size // 2), bold=True), '#126f9e')
    return avatar


def fit_image(image, size):
    """按目标比例裁切图片，供有固定尺寸的缩略图与网格使用。"""
    return ImageOps.fit(image, size, method=_RESAMPLE)


def contain_image(image, size):
    """在目标边界内保留原图比例。"""
    scale = min(size[0] / image.width, size[1] / image.height)
    return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), _RESAMPLE)


def make_qr_image(url, size):
    """按整数模块边长绘制并保留静区；缺少 qrcode 时省略。"""
    if Image is None or qrcode is None or not url or not capabilities.can('qr_login'):
        return None
    code = qrcode.QRCode(box_size=1, border=4)
    try:
        code.add_data(url)
        code.make(fit=True)
    except (qrcode.exceptions.DataOverflowError, UnicodeError):
        return None
    matrix = code.get_matrix()
    scale = size // len(matrix)
    if scale < 2:
        return None
    offset = (size - len(matrix) * scale) // 2
    image = Image.new('RGB', (size, size), 'white')
    draw = ImageDraw.Draw(image)
    for row, modules in enumerate(matrix):
        for col, dark in enumerate(modules):
            if dark:
                x, y = offset + col * scale, offset + row * scale
                draw.rectangle((x, y, x + scale - 1, y + scale - 1), fill='#172b38')
    return image


def draw_line_chart(draw, box, values, *, fill='#087dab', grid='#dce7ef', x_fractions=None):
    """画折线；默认等间隔，稀疏时间序列可显式提供归一化横坐标。"""
    left, top, right, bottom = box
    if grid is not None:
        for index in range(4):
            y = top + (bottom - top) * index / 3
            draw.line((left, y, right, y), fill=grid)
    if not isinstance(values, (list, tuple)):
        values = tuple(values)
    if not values:
        return
    low, high = min(0, min(values)), max(0, max(values))
    spread = high - low or 1
    if x_fractions is None:
        x_fractions = (0.5,) if len(values) == 1 else (i / (len(values) - 1) for i in range(len(values)))
    points = [
        (left + (right - left) * fraction, bottom - (bottom - top) * (value - low) / spread)
        for fraction, value in zip(x_fractions, values)
    ]
    if len(points) == 1:
        x, y = points[0]
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=fill)
    else:
        draw.line(points, fill=fill, width=3, joint='curve')


def draw_ratio_bar(canvas, box, segments, *, radius=8, background='#e9f0f6'):
    """按 (数量, 色值) 绘制分段占比；全零时绘制底色。"""
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return
    bar = Image.new('RGB', (width, height), background)
    draw = ImageDraw.Draw(bar)
    segments = [(value, color) for value, color in segments if value > 0]
    total = sum(value for value, _ in segments)
    accumulated = start = 0
    for value, color in segments:
        accumulated += value
        end = round(width * accumulated / total)
        if end > start:
            draw.rectangle((start, 0, end - 1, height - 1), fill=color)
        start = end
    paste_rounded(canvas, bar, (left, top), radius=radius)


def _prune_generated(directory, *, limit, min_age=0, max_age=float('inf')):
    now = time()
    entries = []
    error = None
    for path in directory.glob(f'{_FILENAME_PREFIX}*.png'):
        try:
            if not path.is_symlink() and path.is_file():
                entries.append((path.stat().st_mtime, path))
        except FileNotFoundError:
            continue  # 发送结束可能已释放该文件。
        except OSError as exc:
            error = exc
    for index, (mtime, path) in enumerate(sorted(entries, reverse=True)):
        age = now - mtime
        if age >= min_age and (index >= limit or age >= max_age):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                error = exc
    if error is not None:
        raise error


def archive_generated_png(path, archive_dir):
    """复制已渲染的发送图；跨 Bot 共用临时图时按需单独存档。"""
    try:
        archive = Path(archive_dir)
        archive.mkdir(parents=True, exist_ok=True)
        if archive.resolve() != path.parent.resolve():
            copyfile(path, archive / path.name)
            _prune_generated(archive, limit=_ARCHIVE_LIMIT)
    except OSError as error:
        store.log(None, f'生成图片存档失败：{type(error).__name__}', level=3)


def save_generated_png(img, subdir='generated', prefix='card', archive_dir=None) -> Path | None:
    """写入发送用的 PNG；存档副本与发送文件各自保留生命周期。"""
    if not isinstance(subdir, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', subdir):
        raise ValueError('invalid subdir')
    prefix = re.sub(r'[^A-Za-z0-9_-]', '-', prefix)[:40] or 'card'
    directory = config.IMAGE_ROOT.parent / subdir
    path = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=directory, prefix=f'{_FILENAME_PREFIX}{prefix}-',
                                suffix='.png', delete=False) as file:
            path = Path(file.name)
            img.save(file, format='PNG')
    except OSError as error:
        store.log(None, f'生成图片保存失败：{type(error).__name__}', level=3)
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                store.log(None, '生成图片临时文件清理失败', level=3)
        return None

    if archive_dir is not None:
        archive_generated_png(path, archive_dir)
    try:
        _prune_generated(directory, limit=_TEMP_LIMIT, min_age=_TEMP_MIN_AGE, max_age=_TEMP_MAX_AGE)
    except OSError as error:
        store.log(None, f'生成图片定期清理失败：{type(error).__name__}', level=3)
    return path
