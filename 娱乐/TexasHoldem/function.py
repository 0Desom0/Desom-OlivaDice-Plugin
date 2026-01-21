# -*- encoding: utf-8 -*-

import os
import json
import random
import itertools
import re
import uuid
from typing import Dict, List, Optional, Tuple

import OlivaDiceCore
import OlivOS


# ----------------------------
# 数据持久化
# ----------------------------


def texas_default() -> dict:
    return {
        'version': 1,
        'state': 'idle',  # idle（空闲）| waiting（等待开局）| playing（游戏中）
        'base_stake': 1000,
        'bb': 10,
        'sb': 5,
        'players': [],  # 玩家列表（list[Player]）
        'join_order': [],  # 按加入顺序记录 seat_id（用于 quit/leave 兜底）
        'user_nicknames': {},  # 用户自定义昵称字典 {user_id: nickname}

        # 单手状态
        'hand_no': 0,
        'dealer_seat_id': None,  # 当前庄位 seat_id（跨手保留）
        'sb_seat_id': None,
        'bb_seat_id': None,

        'street': None,  # preflop|flop|turn|river|showdown
        'community_cards': [],
        'deck': [],

        'pot': 0,
        'dead_money': 0,  # 例如：leave/kick 罚没的剩余筹码

        'current_high': 0,  # 本街最高投入（当前需跟到的额度）
        'min_raise': 0,  # 最小加注增量（delta）

        'acting_seat_id': None,
        'need_action_seat_ids': [],

        'end_flag': False,
    }


def get_texas_data_path() -> str:
    texas_data_path = os.path.join('plugin', 'data', 'TexasHoldem')
    if not os.path.exists(texas_data_path):
        os.makedirs(texas_data_path)
    return texas_data_path


def get_texas_images_path() -> str:
    """图片缓存目录"""
    img_path = os.path.join('data', 'images', 'TexasHoldem')
    if not os.path.exists(img_path):
        os.makedirs(img_path)
    return img_path


def _parse_hex_color(value: str, default=(247, 219, 255, 255)):
    try:
        if value is None:
            return default
        s = str(value).strip().lstrip('#')
        if len(s) == 6:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
            return (r, g, b, 255)
        if len(s) == 8:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
            a = int(s[6:8], 16)
            return (r, g, b, a)
    except Exception:
        pass
    return default


def _color_brightness(rgba) -> float:
    try:
        r, g, b = int(rgba[0]), int(rgba[1]), int(rgba[2])
        return 0.299 * r + 0.587 * g + 0.114 * b
    except Exception:
        return 255.0


class TexasHoldemImageReply:
    """把文本渲染为图片并通过 CQ 码发送的工具类。"""

    DEFAULT_MAX_WIDTH = 860
    DEFAULT_PADDING = 26
    DEFAULT_LINE_SPACING = 10
    DEFAULT_CACHE_LIMIT = 60

    def __init__(self, dictStrCustom: dict):
        self.dictStrCustom = dictStrCustom or {}

        self.max_width = int(self.dictStrCustom.get('strTHImgMaxWidth', self.DEFAULT_MAX_WIDTH) or self.DEFAULT_MAX_WIDTH)
        self.padding = int(self.dictStrCustom.get('strTHImgPadding', self.DEFAULT_PADDING) or self.DEFAULT_PADDING)
        self.line_spacing = int(self.dictStrCustom.get('strTHImgLineSpacing', self.DEFAULT_LINE_SPACING) or self.DEFAULT_LINE_SPACING)
        self.cache_limit = int(self.dictStrCustom.get('strTHImgCacheLimit', self.DEFAULT_CACHE_LIMIT) or self.DEFAULT_CACHE_LIMIT)

        self.bg_start = _parse_hex_color(self.dictStrCustom.get('strTHImgBgStart', '#F7DBFF'))
        self.bg_end = _parse_hex_color(self.dictStrCustom.get('strTHImgBgEnd', '#FFFFFF'), default=(255, 255, 255, 255))

        self.dark_text = _parse_hex_color(self.dictStrCustom.get('strTHImgTextDark', '#111827'), default=(17, 24, 39, 255))
        self.light_text = _parse_hex_color(self.dictStrCustom.get('strTHImgTextLight', '#F9FAFB'), default=(249, 250, 251, 255))

    def _cleanup_cache(self, folder: str) -> None:
        try:
            files = []
            for name in os.listdir(folder):
                if not name.startswith('send_'):
                    continue
                if not (name.endswith('.png') or name.endswith('.jpg') or name.endswith('.jpeg')):
                    continue
                path = os.path.join(folder, name)
                try:
                    files.append((os.path.getmtime(path), path))
                except Exception:
                    continue
            files.sort(key=lambda x: x[0])
            if len(files) <= self.cache_limit:
                return
            for _, path in files[:-self.cache_limit]:
                try:
                    os.remove(path)
                except Exception:
                    pass
        except Exception:
            pass

    def _resolve_cjk_font_path(self) -> Optional[str]:
        """尽量选择系统自带的中文字体，兼容 Windows/Linux/macOS。

        可选：在 dictStrCustom 中配置 strTHImgFontPath 指定字体文件路径（ttf/otf/ttc）。
        """
        custom_path = self.dictStrCustom.get('strTHImgFontPath')
        if custom_path:
            p = str(custom_path).strip().strip('"').strip("'")
            if p and os.path.isfile(p):
                return p

        # 常见中文字体文件名（优先无衬线）
        candidate_files = [
            # Windows 常见
            'msyh.ttc', 'msyh.ttf',          # Microsoft YaHei
            'msyhbd.ttc', 'msyhbd.ttf',
            'simhei.ttf',                   # SimHei
            'simsun.ttc', 'simsun.ttf',     # SimSun
            'deng.ttf', 'dengb.ttf',        # DengXian
            # macOS 常见
            'PingFang.ttc',
            'PingFang SC.ttc',
            'PingFangHK.ttc',
            'PingFangTC.ttc',
            'STHeiti Medium.ttc',
            'STHeiti Light.ttc',
            'Hiragino Sans GB.ttc',
            'Hiragino Sans GB W3.ttc',
            'Songti.ttc',
            # Linux 常见
            'NotoSansCJK-Regular.ttc',
            'NotoSansCJKsc-Regular.otf',
            'NotoSansSC-Regular.otf',
            'SourceHanSansSC-Regular.otf',
            'WenQuanYiZenHei.ttf',
            'wqy-zenhei.ttc',
            'DroidSansFallback.ttf',
            'AR PL UMing CN.ttf',
            'AR PL UKai CN.ttf',
        ]

        search_dirs: List[str] = []

        # Windows 字体目录
        try:
            windir = os.environ.get('WINDIR') or os.environ.get('SystemRoot')
            if windir:
                search_dirs.append(os.path.join(windir, 'Fonts'))
        except Exception:
            pass

        # Linux 常见字体目录
        search_dirs.extend([
            '/usr/share/fonts',
            '/usr/local/share/fonts',
            os.path.expanduser('~/.fonts'),
            os.path.expanduser('~/.local/share/fonts'),
        ])

        # macOS 常见字体目录
        search_dirs.extend([
            '/System/Library/Fonts',
            '/System/Library/Fonts/Supplemental',
            '/Library/Fonts',
            os.path.expanduser('~/Library/Fonts'),
        ])

        # 先尝试“直接拼路径”的快速命中
        for d in search_dirs:
            if not d or not os.path.isdir(d):
                continue
            for fname in candidate_files:
                p = os.path.join(d, fname)
                if os.path.isfile(p):
                    return p

        # 再做一次有限的递归搜索（避免全盘扫描）
        lower_candidates = {f.lower() for f in candidate_files}
        for base in search_dirs:
            if not base or not os.path.isdir(base):
                continue
            try:
                for root, _, files in os.walk(base):
                    # 小优化：文件名做一次 lower 映射
                    file_map = {fn.lower(): fn for fn in files}
                    hit = lower_candidates.intersection(file_map.keys())
                    if hit:
                        # 取第一个命中
                        real = file_map[next(iter(hit))]
                        return os.path.join(root, real)
            except Exception:
                continue

        return None

    def _resolve_emoji_font_path(self) -> Optional[str]:
        """尽量选择系统 Emoji 字体（可选），兼容 Windows/Linux/macOS。

        优先级：NotoEmoji（黑白、兼容性好）> NotoColorEmoji（彩色）> 平台默认。
        """
        custom_path = self.dictStrCustom.get('strTHImgEmojiFontPath')
        if custom_path:
            p = str(custom_path).strip().strip('"').strip("'")
            if p and os.path.isfile(p):
                return p

        candidate_files = [
            # Linux
            'NotoEmoji-Regular.ttf',
            'NotoEmoji.ttf',
            'NotoColorEmoji.ttf',
            # macOS
            'Apple Color Emoji.ttc',
            # Windows
            'seguiemj.ttf',
        ]

        search_dirs: List[str] = []
        try:
            windir = os.environ.get('WINDIR') or os.environ.get('SystemRoot')
            if windir:
                search_dirs.append(os.path.join(windir, 'Fonts'))
        except Exception:
            pass

        search_dirs.extend([
            '/usr/share/fonts',
            '/usr/local/share/fonts',
            os.path.expanduser('~/.fonts'),
            os.path.expanduser('~/.local/share/fonts'),
            '/System/Library/Fonts',
            '/System/Library/Fonts/Supplemental',
            '/Library/Fonts',
            os.path.expanduser('~/Library/Fonts'),
        ])

        for d in search_dirs:
            if not d or not os.path.isdir(d):
                continue
            for fname in candidate_files:
                p = os.path.join(d, fname)
                if os.path.isfile(p):
                    return p

        lower_candidates = {f.lower() for f in candidate_files}
        for base in search_dirs:
            if not base or not os.path.isdir(base):
                continue
            try:
                for root, _, files in os.walk(base):
                    file_map = {fn.lower(): fn for fn in files}
                    hit = lower_candidates.intersection(file_map.keys())
                    if hit:
                        real = file_map[next(iter(hit))]
                        return os.path.join(root, real)
            except Exception:
                continue

        return None

    def _resolve_color_emoji_font_path(self) -> Optional[str]:
        """选择“彩色 emoji”字体（可选），用于花色等需要 emoji 呈现时。

        优先：NotoColorEmoji > Apple Color Emoji > Segoe UI Emoji
        可选：dictStrCustom['strTHImgColorEmojiFontPath'] 指定路径
        """
        custom_path = self.dictStrCustom.get('strTHImgColorEmojiFontPath')
        if custom_path:
            p = str(custom_path).strip().strip('"').strip("'")
            if p and os.path.isfile(p):
                return p

        candidate_files = [
            'NotoColorEmoji.ttf',
            'Apple Color Emoji.ttc',
            'seguiemj.ttf',
        ]

        search_dirs: List[str] = []
        try:
            windir = os.environ.get('WINDIR') or os.environ.get('SystemRoot')
            if windir:
                search_dirs.append(os.path.join(windir, 'Fonts'))
        except Exception:
            pass

        search_dirs.extend([
            '/usr/share/fonts',
            '/usr/local/share/fonts',
            os.path.expanduser('~/.fonts'),
            os.path.expanduser('~/.local/share/fonts'),
            '/System/Library/Fonts',
            '/System/Library/Fonts/Supplemental',
            '/Library/Fonts',
            os.path.expanduser('~/Library/Fonts'),
        ])

        for d in search_dirs:
            if not d or not os.path.isdir(d):
                continue
            for fname in candidate_files:
                p = os.path.join(d, fname)
                if os.path.isfile(p):
                    return p

        lower_candidates = {f.lower() for f in candidate_files}
        for base in search_dirs:
            if not base or not os.path.isdir(base):
                continue
            try:
                for root, _, files in os.walk(base):
                    file_map = {fn.lower(): fn for fn in files}
                    hit = lower_candidates.intersection(file_map.keys())
                    if hit:
                        real = file_map[next(iter(hit))]
                        return os.path.join(root, real)
            except Exception:
                continue
        return None

    @staticmethod
    def _is_emoji_char(ch: str) -> bool:
        if not ch:
            return False
        cp = ord(ch)
        # 常见 emoji / 符号范围（不追求 100% 完整，够用即可）
        if 0x1F300 <= cp <= 0x1FAFF:
            return True
        if 0x2600 <= cp <= 0x27BF:
            return True
        # 变体选择符/连接符
        if cp in (0xFE0F, 0x200D):
            return True
        return False

    @staticmethod
    def _is_suit_symbol(ch: str) -> bool:
        if not ch:
            return False
        return ord(ch) in (0x2660, 0x2663, 0x2665, 0x2666)

    @staticmethod
    def _is_variation_selector(ch: str) -> bool:
        return bool(ch) and ord(ch) == 0xFE0F

    @staticmethod
    def _is_zwj(ch: str) -> bool:
        return bool(ch) and ord(ch) == 0x200D

    @staticmethod
    def _is_skin_tone(ch: str) -> bool:
        if not ch:
            return False
        cp = ord(ch)
        return 0x1F3FB <= cp <= 0x1F3FF

    def _split_runs(self, s: str, emoji_font, color_emoji_font) -> List[Tuple[str, bool]]:
        """把一行文本拆成 (run, is_emoji) 列表。

        - 普通文本尽量合并为长 run，提升性能
        - emoji run 会尽量把 VS16/肤色/ZWJ 组合并到同一 run，避免错位与宽度计算偏差
        """
        s = '' if s is None else str(s)
        if not s:
            return []
        allow_emoji = (emoji_font is not None) or (color_emoji_font is not None)
        # allow_color 仅表示“存在彩色 emoji 字体”，最终是否使用由渲染阶段决定
        allow_color = color_emoji_font is not None

        out: List[Tuple[str, bool]] = []
        i = 0
        while i < len(s):
            ch = s[i]

            if allow_emoji and self._is_emoji_char(ch):
                run = ch
                i += 1
                # 变体选择符/肤色修饰
                while i < len(s) and (self._is_variation_selector(s[i]) or self._is_skin_tone(s[i])):
                    run += s[i]
                    i += 1

                # 约定：花色（♠♣♥♦）强制走“黑白 emoji/符号”风格，不额外补 VS16
                # 其它 emoji 的彩色/黑白选择在渲染阶段处理
                # ZWJ 组合：emoji + ZWJ + emoji (+ VS16/肤色) ...
                while i < len(s) and self._is_zwj(s[i]):
                    run += s[i]
                    i += 1
                    if i < len(s):
                        run += s[i]
                        i += 1
                        while i < len(s) and (self._is_variation_selector(s[i]) or self._is_skin_tone(s[i])):
                            run += s[i]
                            i += 1
                out.append((run, True))
                continue

            # 普通文本：尽量合并
            j = i
            while j < len(s):
                if allow_emoji and self._is_emoji_char(s[j]):
                    break
                j += 1
            out.append((s[i:j], False))
            i = j

        return out

    @staticmethod
    def _run_bbox(draw, text: str, font) -> Tuple[int, int, int, int]:
        """返回 bbox=(x0,y0,x1,y1)，优先使用基线锚点，减少裁切。"""
        t = text if text else ' '
        try:
            return tuple(draw.textbbox((0, 0), t, font=font, anchor='ls'))  # type: ignore
        except Exception:
            try:
                return tuple(draw.textbbox((0, 0), t, font=font))
            except Exception:
                return (0, 0, 0, 0)

    @staticmethod
    def _run_advance(draw, text: str, font) -> int:
        """返回 advance 宽度，优先 textlength，兜底 bbox 宽度。"""
        t = text if text else ''
        try:
            return int(draw.textlength(t, font=font))
        except Exception:
            bbox = TexasHoldemImageReply._run_bbox(draw, t, font)
            return int(bbox[2] - bbox[0])

    @staticmethod
    def _is_suit_only_run(run: str) -> bool:
        if not run:
            return False
        # 去掉 VS16 变体选择符后，只剩一个花色符号
        stripped = ''.join(ch for ch in run if ord(ch) != 0xFE0F)
        return len(stripped) == 1 and TexasHoldemImageReply._is_suit_symbol(stripped)

    @staticmethod
    def _run_advance_effective(draw, text: str, font, *, tight_right: bool = False) -> int:
        """返回用于排版的 advance。

        对“单独花色 emoji”做紧凑处理：用 bbox 右边界替代 textlength，去掉 emoji 字体自带的右侧留白。
        """
        adv = TexasHoldemImageReply._run_advance(draw, text, font)
        if not tight_right:
            return adv
        try:
            bbox = TexasHoldemImageReply._run_bbox(draw, text, font)
            tight = int(bbox[2])
            if 0 < tight < adv:
                return tight
        except Exception:
            pass
        return adv

    @staticmethod
    def _text_width(draw, text: str, font) -> int:
        try:
            return int(draw.textlength(text, font=font))
        except Exception:
            try:
                bbox = draw.textbbox((0, 0), text if text else ' ', font=font)
                return int(bbox[2] - bbox[0])
            except Exception:
                return 0

    @staticmethod
    def _font_metrics(draw, font) -> Tuple[int, int, int]:
        """返回 (ascent, descent, line_height)。"""
        try:
            a, d = font.getmetrics()
            a = int(a)
            d = int(d)
            return a, d, max(1, a + d)
        except Exception:
            try:
                bbox = draw.textbbox((0, 0), 'Hg', font=font)
                h = int(bbox[3] - bbox[1])
                a = int(h * 0.8)
                d = max(0, h - a)
                return a, d, max(1, h)
            except Exception:
                return 14, 4, 18

    @staticmethod
    def _char_size(draw, ch: str, font) -> Tuple[int, int]:
        try:
            bbox = draw.textbbox((0, 0), ch if ch else ' ', font=font)
            return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])
        except Exception:
            # 兜底：给一个近似值
            return 0, 0

    def _load_emoji_font(self):
        try:
            from PIL import ImageFont
            size = int(self.dictStrCustom.get('strTHImgFontSize', 18) or 18)
            font_path = self._resolve_emoji_font_path()
            if not font_path:
                return None
            try:
                return ImageFont.truetype(font_path, size=size)
            except Exception:
                return None
        except Exception:
            return None

    def _load_color_emoji_font(self):
        try:
            from PIL import ImageFont
            size = int(self.dictStrCustom.get('strTHImgFontSize', 18) or 18)
            font_path = self._resolve_color_emoji_font_path()
            if not font_path:
                return None
            try:
                return ImageFont.truetype(font_path, size=size)
            except Exception:
                return None
        except Exception:
            return None

    def _load_font(self):
        """加载支持中文的字体（优先系统字体），保证 Win/Linux 显示正常。"""
        try:
            from PIL import ImageFont
            size = int(self.dictStrCustom.get('strTHImgFontSize', 18) or 18)

            font_path = self._resolve_cjk_font_path()
            if font_path:
                # ttc 可能需要 index 参数；不同系统字体集合索引可能不同
                for idx in (0, 1, 2, 3):
                    try:
                        return ImageFont.truetype(font_path, size=size, index=idx)
                    except Exception:
                        continue
                try:
                    return ImageFont.truetype(font_path, size=size)
                except Exception:
                    pass

            # 兜底：Pillow 默认字体（可能不含中文，但确保不报错）
            try:
                return ImageFont.load_default(size=size)
            except Exception:
                return ImageFont.load_default()
        except Exception:
            return None

    def _wrap_lines_by_pixel(self, draw, text: str, base_font, emoji_font, color_emoji_font, max_pixel_width: int) -> List[str]:
        text = '' if text is None else str(text)
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        out: List[str] = []

        for para in text.split('\n'):
            if para == '':
                out.append('')
                continue

            cur = ''
            cur_w = 0
            tokens = self._split_runs(para, emoji_font, color_emoji_font)
            for run, is_emoji in tokens:
                has_suit = any(self._is_suit_symbol(c) for c in run)
                is_suit_run = is_emoji and self._is_suit_only_run(run)
                # 规则：花色强制黑白；其它 emoji 优先彩色
                if is_emoji and has_suit:
                    # 花色尽量用 emoji 字体显示，但不启用 embedded_color（黑白）
                    f = emoji_font if (emoji_font is not None) else (color_emoji_font if (color_emoji_font is not None) else base_font)
                elif is_emoji and (color_emoji_font is not None):
                    f = color_emoji_font
                elif is_emoji and (emoji_font is not None):
                    f = emoji_font
                else:
                    f = base_font
                run_w = self._run_advance_effective(draw, run, f, tight_right=is_suit_run)

                # 若一个普通 run 太长，拆成单字符以便换行
                if (not is_emoji) and run_w > max_pixel_width and len(run) > 1:
                    for ch in run:
                        ch_w = self._run_advance_effective(draw, ch, f, tight_right=False)
                        if cur == '':
                            cur = ch
                            cur_w = ch_w
                        elif cur_w + ch_w <= max_pixel_width:
                            cur += ch
                            cur_w += ch_w
                        else:
                            out.append(cur)
                            cur = ch
                            cur_w = ch_w
                    continue

                if cur == '':
                    cur = run
                    cur_w = run_w
                    continue

                if cur_w + run_w <= max_pixel_width:
                    cur += run
                    cur_w += run_w
                else:
                    out.append(cur)
                    cur = run
                    cur_w = run_w
            if cur != '':
                out.append(cur)
        return out

    def _make_vertical_gradient(self, width: int, height: int):
        from PIL import Image

        base = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        px = base.load()
        for y in range(height):
            t = y / max(1, height - 1)
            r = int(self.bg_start[0] + (self.bg_end[0] - self.bg_start[0]) * t)
            g = int(self.bg_start[1] + (self.bg_end[1] - self.bg_start[1]) * t)
            b = int(self.bg_start[2] + (self.bg_end[2] - self.bg_start[2]) * t)
            a = 255
            for x in range(width):
                px[x, y] = (r, g, b, a)
        return base

    def render_text_to_image(self, text: str) -> Optional[Tuple[str, str]]:
        """返回 (abs_path, cq_file_path)。cq_file_path 以 TexasHoldem/ 开头。"""
        try:
            from PIL import Image, ImageDraw
        except Exception:
            return None

        base_font = self._load_font()
        if base_font is None:
            return None
        emoji_font = self._load_emoji_font()
        color_emoji_font = self._load_color_emoji_font()

        folder = get_texas_images_path()
        self._cleanup_cache(folder)

        dummy = Image.new('RGBA', (10, 10), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy)

        base_a, base_d, _ = self._font_metrics(draw, base_font)
        if emoji_font is not None:
            emoji_a, emoji_d, _ = self._font_metrics(draw, emoji_font)
        else:
            emoji_a, emoji_d = base_a, base_d
        if color_emoji_font is not None:
            color_a, color_d, _ = self._font_metrics(draw, color_emoji_font)
        else:
            color_a, color_d = emoji_a, emoji_d

        content_max = max(200, self.max_width - self.padding * 2)
        lines = self._wrap_lines_by_pixel(draw, str(text), base_font, emoji_font, color_emoji_font, content_max)

        # 计算尺寸
        max_w = 0
        line_heights: List[int] = []
        line_ascents: List[int] = []
        line_min_lefts: List[int] = []
        for line in lines:
            s = line if line else ' '
            x = 0
            min_left = 0
            max_right = 0
            ascent = base_a
            descent = base_d

            tokens = self._split_runs(s, emoji_font, color_emoji_font)
            for run, is_emoji in tokens:
                has_suit = any(self._is_suit_symbol(c) for c in run)
                is_suit_run = is_emoji and self._is_suit_only_run(run)
                # 规则：花色强制黑白；其它 emoji 优先彩色
                if is_emoji and has_suit:
                    f = emoji_font if (emoji_font is not None) else (color_emoji_font if (color_emoji_font is not None) else base_font)
                    a, d = (emoji_a, emoji_d) if (emoji_font is not None) else ((color_a, color_d) if (color_emoji_font is not None) else (base_a, base_d))
                elif is_emoji and (color_emoji_font is not None):
                    f = color_emoji_font
                    a, d = color_a, color_d
                elif is_emoji and (emoji_font is not None):
                    f = emoji_font
                    a, d = emoji_a, emoji_d
                else:
                    f = base_font
                    a, d = base_a, base_d

                bbox = self._run_bbox(draw, run, f)
                min_left = min(min_left, x + int(bbox[0]))
                max_right = max(max_right, x + int(bbox[2]))
                ascent = max(ascent, -int(bbox[1]), a)
                descent = max(descent, int(bbox[3]), d)
                x += self._run_advance_effective(draw, run, f, tight_right=is_suit_run)

            w = max_right - min_left
            h = max(1, ascent + descent)
            max_w = max(max_w, w)
            line_heights.append(h)
            line_ascents.append(ascent)
            line_min_lefts.append(min_left)
        # 给负 left bearing 留空间，防止“短一截/被裁切”
        global_min_left = min(line_min_lefts) if line_min_lefts else 0
        extra_left = max(0, -int(global_min_left))
        canvas_w = max_w + self.padding * 2 + extra_left
        # 允许为 extra_left 适度放宽，避免右侧被挤掉导致“短一截”
        canvas_w = min(self.max_width + extra_left, canvas_w)
        total_h = sum(line_heights) + self.line_spacing * max(0, len(lines) - 1)
        canvas_h = total_h + self.padding * 2
        canvas_h = max(canvas_h, 120)

        bg = self._make_vertical_gradient(canvas_w, canvas_h)
        canvas = bg.copy()
        draw = ImageDraw.Draw(canvas)

        # 文字颜色根据背景亮度自动切换（使用配置色）
        dark_mode = _color_brightness(self.bg_start) < 128
        text_color = self.light_text if dark_mode else self.dark_text
        stroke_color = self.dark_text if dark_mode else self.light_text
        try:
            stroke_width = int(self.dictStrCustom.get('strTHImgStrokeWidth', 2) or 2)
        except Exception:
            stroke_width = 2
        stroke_width = max(0, stroke_width)

        x0 = self.padding + extra_left
        y = self.padding
        for idx, line in enumerate(lines):
            x = x0
            baseline_y = y + (line_ascents[idx] if idx < len(line_ascents) else base_a)
            # 行级别再修正一次 left bearing
            try:
                x = x - int(line_min_lefts[idx])
            except Exception:
                pass

            for run, is_emoji in self._split_runs(line, emoji_font, color_emoji_font):
                has_suit = any(self._is_suit_symbol(c) for c in run)
                is_suit_run = is_emoji and self._is_suit_only_run(run)
                # 规则：花色强制黑白；其它 emoji 优先彩色
                if is_emoji and has_suit:
                    f = emoji_font if (emoji_font is not None) else (color_emoji_font if (color_emoji_font is not None) else base_font)
                    a = emoji_a if (emoji_font is not None) else (color_a if (color_emoji_font is not None) else base_a)
                    use_embedded_color = False
                    draw_stroke = True
                elif is_emoji and (color_emoji_font is not None):
                    f = color_emoji_font
                    a = color_a
                    use_embedded_color = True
                    draw_stroke = False
                elif is_emoji and (emoji_font is not None):
                    f = emoji_font
                    a = emoji_a
                    use_embedded_color = False
                    draw_stroke = True
                else:
                    f = base_font
                    a = base_a
                    use_embedded_color = False
                    draw_stroke = True
                try:
                    if use_embedded_color:
                        draw.text((x, baseline_y), run, font=f, fill=text_color, embedded_color=True, anchor='ls')
                    elif draw_stroke:
                        draw.text(
                            (x, baseline_y),
                            run,
                            font=f,
                            fill=text_color,
                            stroke_width=stroke_width,
                            stroke_fill=stroke_color,
                            anchor='ls',
                        )
                    else:
                        draw.text((x, baseline_y), run, font=f, fill=text_color, anchor='ls')
                except TypeError:
                    # 兼容旧 Pillow：没有 anchor/embedded_color
                    y_top = baseline_y - a
                    try:
                        draw.text((x, y_top), run, font=f, fill=text_color)
                    except Exception:
                        pass
                x += self._run_advance_effective(draw, run, f, tight_right=is_suit_run)
            y += line_heights[idx] + self.line_spacing

        file_id = uuid.uuid4().hex[:10]
        filename = f"send_{file_id}.png"
        abs_path = os.path.join(folder, filename)
        canvas.save(abs_path)

        # CQ 码路径要求：从 TexasHoldem 开始
        cq_path = f"TexasHoldem/{filename}"
        return abs_path, cq_path


_AT_RE = re.compile(r"\[CQ:at,[^\]]+\]")


def _extract_at_segments(message: str) -> Tuple[str, str]:
    """返回 (at_segments, message_without_at)。"""
    msg = '' if message is None else str(message)
    ats = _AT_RE.findall(msg)
    if not ats:
        return '', msg
    msg_wo = _AT_RE.sub('', msg)
    return ''.join(ats), msg_wo


def replyMsg(plugin_event, message, at_user: bool = False):
    """TexasHoldem 专用 replyMsg：支持按配置把文本转成图片发送。

    - dictStrCustom['strTHSendMode'] == 1: 发送文本
    - 其它值（含 0/2/...）: 发送图片
    """
    base_reply = OlivaDiceCore.msgReply.replyMsg
    try:
        dictStrCustom = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]
    except Exception:
        dictStrCustom = {}

    try:
        mode = int(dictStrCustom.get('strTHSendMode', 0))
    except Exception:
        mode = 0

    # 文本模式：完全走原始 replyMsg
    if mode == 1:
        return base_reply(plugin_event, message, at_user)

    # 图片模式：抽离 @，把剩余文本渲染成图片
    at_in_msg, msg_wo_at = _extract_at_segments(message)

    at_prefix = ''
    if at_user:
        try:
            at_prefix = OlivOS.messageAPI.PARA.at(str(plugin_event.data.user_id)).get_string_by_key('CQ')
        except Exception:
            at_prefix = ''

    text_for_image = (msg_wo_at or '').strip()
    if not text_for_image:
        # 只有 at 没有正文：直接发回
        return base_reply(plugin_event, (at_prefix + at_in_msg).strip(), False)

    renderer = TexasHoldemImageReply(dictStrCustom)
    rendered = renderer.render_text_to_image(text_for_image)
    if not rendered:
        # 没有 Pillow 或渲染失败：兜底文本
        return base_reply(plugin_event, message, at_user)

    _, cq_path = rendered
    cq_msg = f"[CQ:image,file={cq_path}]"
    out = (at_prefix + at_in_msg + cq_msg).strip()
    return base_reply(plugin_event, out, False)


def get_redirected_bot_hash(bot_hash: str) -> str:
    """遵循 OlivaDiceCore 主从账号链接：从账号读写主账号目录。"""
    try:
        master = OlivaDiceCore.console.getMasterBotHash(bot_hash)
        if master:
            return str(master)
    except Exception:
        pass
    return bot_hash


def get_group_file_path(bot_hash: str, group_hash: str) -> str:
    texas_data_path = get_texas_data_path()
    bot_hash = get_redirected_bot_hash(bot_hash)
    bot_path = os.path.join(texas_data_path, bot_hash)
    if not os.path.exists(bot_path):
        os.makedirs(bot_path)
    return os.path.join(bot_path, f"{group_hash}.json")


def load_group_data(bot_hash: str, group_hash: str) -> dict:
    # 默认按“主从链接”后的 botHash 读取
    file_path = get_group_file_path(bot_hash, group_hash)
    default_data = texas_default()

    # 兜底：若当前 botHash 为从账号，且主账号目录里不存在，则尝试读取旧的从账号目录
    redirected_bot_hash = get_redirected_bot_hash(bot_hash)
    if redirected_bot_hash != bot_hash and not os.path.exists(file_path):
        texas_data_path = get_texas_data_path()
        legacy_bot_path = os.path.join(texas_data_path, bot_hash)
        legacy_path = os.path.join(legacy_bot_path, f"{group_hash}.json")
        if os.path.exists(legacy_path):
            file_path = legacy_path

    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and all(k in data for k in default_data.keys()):
                    return data
        except (IOError, json.JSONDecodeError):
            pass

    return default_data


def save_group_data(bot_hash: str, group_hash: str, data: dict) -> None:
    file_path = get_group_file_path(bot_hash, group_hash)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ----------------------------
# 工具函数
# ----------------------------


def get_nickname(
    plugin_event,
    user_id: str,
    tmp_hagID: Optional[str] = None,
    fallback_prefix: str = '',
    bot_hash: Optional[str] = None,
    group_hash: Optional[str] = None,
) -> str:
    """
    获取用户昵称，优先级：文件中记录的昵称 -> 人物卡名称 -> QQ昵称
    """
    try:
        fallback_prefix = fallback_prefix or ''
        default_name = f"{fallback_prefix}{user_id}" if fallback_prefix else str(user_id)
        
        # 1. 优先尝试从文件中记录的昵称获取
        if bot_hash and group_hash:
            try:
                game_data = load_group_data(bot_hash, group_hash)
                user_nicknames = game_data.get('user_nicknames', {})
                if str(user_id) in user_nicknames:
                    stored_nickname = user_nicknames.get(str(user_id))
                    if stored_nickname and stored_nickname.strip():
                        return str(stored_nickname)
            except Exception:
                pass
        
        # 2. 其次使用人物卡名称
        tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(user_id, plugin_event.platform['platform'])
        tmp_pcName = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
        if tmp_pcName:
            return tmp_pcName

        # 3. QQ频道：若无人物卡名，则回退到人物卡hash
        if plugin_event.platform['platform'] == 'qqGuild':
            return f"{fallback_prefix}{tmp_pcHash}" if fallback_prefix else str(tmp_pcHash)

        # 4. 尝试从用户配置获取QQ昵称
        pid_nickname = OlivaDiceCore.userConfig.getUserConfigByKey(
            userId=user_id,
            userType='user',
            platform=plugin_event.platform['platform'],
            userConfigKey='userName',
            botHash=plugin_event.bot_info.hash,
            default=default_name,
        )
        if pid_nickname and pid_nickname != default_name and pid_nickname != fallback_prefix:
            return pid_nickname

        # 5. 尝试从平台API获取昵称
        plres = plugin_event.get_stranger_info(user_id)
        if plres.get('active'):
            pid_nickname = plres['data']['name']
            if pid_nickname == fallback_prefix and fallback_prefix:
                return default_name
            if pid_nickname and pid_nickname != default_name and pid_nickname != fallback_prefix:
                return pid_nickname
            return default_name
        return default_name
    except Exception:
        return f"{fallback_prefix}{user_id}" if fallback_prefix else str(user_id)


def set_user_nickname(bot_hash: str, group_hash: str, user_id: str, nickname: str) -> None:
    """
    在群组文件中设置用户自定义昵称
    """
    try:
        game_data = load_group_data(bot_hash, group_hash)
        if 'user_nicknames' not in game_data:
            game_data['user_nicknames'] = {}
        game_data['user_nicknames'][str(user_id)] = str(nickname)
        save_group_data(bot_hash, group_hash, game_data)
    except Exception:
        pass


def compute_blinds(base_stake: int) -> Tuple[int, int]:
    bb = int(base_stake * 0.01)
    sb = int(bb * 0.5)
    return bb, sb


def find_player(players: List[dict], seat_id: int) -> Optional[dict]:
    for p in players:
        if p.get('seat_id') == seat_id:
            return p
    return None


def list_seat_ids(players: List[dict], include_out: bool = False) -> List[int]:
    seat_ids = []
    for p in players:
        if not include_out and p.get('status') == 'out':
            continue
        seat_ids.append(int(p['seat_id']))
    return sorted(seat_ids)


def next_seat_in_order(seat_order: List[int], current: int) -> int:
    if not seat_order:
        raise ValueError('empty seat_order')
    if current not in seat_order:
        return seat_order[0]
    idx = seat_order.index(current)
    return seat_order[(idx + 1) % len(seat_order)]


def next_action_seat(game: dict, from_seat_id: int) -> Optional[int]:
    """获取下一个可行动的座位（仅限 active）。"""
    seat_order = list_seat_ids(game['players'], include_out=False)
    if not seat_order:
        return None
    cur = from_seat_id
    for _ in range(len(seat_order)):
        cur = next_seat_in_order(seat_order, cur)
        p = find_player(game['players'], cur)
        if p and p.get('status') == 'active':
            return cur
    return None


def active_in_hand(players: List[dict]) -> List[dict]:
    return [p for p in players if p.get('status') in ('active', 'allin', 'folded')]


def alive_players(players: List[dict]) -> List[dict]:
    return [p for p in players if p.get('status') != 'out']


def in_showdown_eligible(players: List[dict]) -> List[dict]:
    return [p for p in players if p.get('status') in ('active', 'allin')]


# ----------------------------
# 牌/牌型评估
# ----------------------------


RANKS = '23456789TJQKA'
SUITS = 'SHDC'
RANK_TO_VAL = {r: i + 2 for i, r in enumerate(RANKS)}
VAL_TO_RANK = {v: r for r, v in RANK_TO_VAL.items()}
SUIT_TO_ICON = {
    # 花色不使用 VS16（emoji 变体），以“文本符号”方式呈现，避免花色后出现明显空隙
    'S': '♠黑桃',
    'H': '♥红桃',
    'D': '♦方片',
    'C': '♣梅花',
}


def new_deck() -> List[str]:
    return [s + r for s in SUITS for r in RANKS]


def shuffle_deck(deck: List[str]) -> None:
    random.shuffle(deck)


def card_to_text(card: str) -> str:
    suit = card[0]
    rank = card[1]
    rank_show = '10' if rank == 'T' else rank
    return f"[{SUIT_TO_ICON.get(suit, suit)}{rank_show}]"


def cards_to_text(cards: List[str]) -> str:
    return ' '.join(card_to_text(c) for c in cards)


def _rank_char_to_show(rank_char: str) -> str:
    if rank_char == 'T':
        return '10'
    return str(rank_char)


def _val_to_show(v: int) -> str:
    return _rank_char_to_show(VAL_TO_RANK.get(int(v), str(v)))


def format_best5_compact(category: int, tiebreak: Tuple[int, ...]) -> str:
    """把最佳 5 张牌格式化为紧凑点数串（不含花色），并按牌型规则排序。

    例如：
    - 三条 KKKQJ（而不是 KKKJQ）
    - 两对 AAQQK（大对在前）
    - 同花/高牌：按点数从大到小
    - 顺子/同花顺：按高张到低张（车轮顺子为 5432A）

    依赖 evaluate_5/evaluate_7 返回的 (category, tiebreak) 结构。
    """
    cat = int(category)
    tb = tuple(int(x) for x in tiebreak)

    vals: List[int]
    if cat in (9, 5):
        # 同花顺 / 顺子：tiebreak=(straight_high,)
        high = int(tb[0]) if tb else 0
        if high == 5:
            # 车轮顺子 A2345
            vals = [5, 4, 3, 2, 14]
        else:
            vals = [high, high - 1, high - 2, high - 3, high - 4]
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 8:
        # 四条：tiebreak=(quad, kicker)
        quad, kicker = tb
        vals = [quad, quad, quad, quad, kicker]
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 7:
        # 葫芦：tiebreak=(trip, pair)
        trip, pair = tb
        vals = [trip, trip, trip, pair, pair]
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 6:
        # 同花：tiebreak 为 5 张从大到小
        return ''.join(_val_to_show(v) for v in tb)

    if cat == 4:
        # 三条：tiebreak=(trip, k1, k2)
        trip = tb[0]
        kickers = list(tb[1:])
        vals = [trip, trip, trip] + kickers
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 3:
        # 两对：tiebreak=(pair_high, pair_low, kicker)
        ph, pl, kicker = tb
        vals = [ph, ph, pl, pl, kicker]
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 2:
        # 一对：tiebreak=(pair, k1, k2, k3)
        pair = tb[0]
        kickers = list(tb[1:])
        vals = [pair, pair] + kickers
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 1:
        # 高牌：tiebreak 为 5 张从大到小
        return ''.join(_val_to_show(v) for v in tb)

    # 兜底
    return ''.join(_val_to_show(v) for v in tb)


def _card_rank_show(card: str) -> str:
    """把单张牌的点数统一为展示格式（T->10）。"""
    try:
        r = str(card)[1]
    except Exception:
        return ''
    return '10' if r == 'T' else str(r)


def _split_compact_ranks(compact: str) -> List[str]:
    """把紧凑点数串拆成点数 token 列表（支持 10）。"""
    s = str(compact or '')
    out: List[str] = []
    i = 0
    while i < len(s):
        if s.startswith('10', i):
            out.append('10')
            i += 2
        else:
            out.append(s[i])
            i += 1
    return out


def order_best5_by_compact(best5: List[str], compact: str) -> List[str]:
    """按 format_best5_compact 给出的点数顺序，对 best5 进行重排。
    说明：best5 本身包含正确的 5 张牌，但其顺序可能不符合展示规则。
    这里用 compact 的点数序列作为目标顺序，在 best5 中按点数逐个匹配取出。
    """
    try:
        tokens = _split_compact_ranks(compact)
        if not best5 or len(best5) != 5 or len(tokens) != 5:
            return list(best5) if best5 else []

        remaining = list(best5)
        ordered: List[str] = []
        for t in tokens:
            hit_idx = None
            for i, c in enumerate(remaining):
                if _card_rank_show(c) == t:
                    hit_idx = i
                    break
            if hit_idx is None:
                # 理论上不应发生；兜底返回原顺序
                return list(best5)
            ordered.append(remaining.pop(hit_idx))

        return ordered
    except Exception:
        return list(best5) if best5 else []


def hand_category_text(category: int) -> str:
    """把 evaluate_5/evaluate_7 的 category 转为可展示的牌型名。"""
    mapping = {
        9: '同花顺（Straight Flush）',
        8: '四条（Four of a Kind）',
        7: '葫芦（Full House）',
        6: '同花（Flush）',
        5: '顺子（Straight）',
        4: '三条（Three of a Kind）',
        3: '两对（Two Pair）',
        2: '一对（One Pair）',
        1: '高牌（High Card）',
    }
    return mapping.get(int(category), f'未知牌型({category})')


def _is_royal_flush(best5: List[str]) -> bool:
    """判断 best5 是否为皇家同花顺（10JQKA 且同花色）。"""
    if not best5 or len(best5) != 5:
        return False
    suits = [c[0] for c in best5 if isinstance(c, str) and len(c) >= 2]
    ranks = [c[1] for c in best5 if isinstance(c, str) and len(c) >= 2]
    if len(suits) != 5 or len(ranks) != 5:
        return False
    if len(set(suits)) != 1:
        return False
    return set(ranks) == set(['T', 'J', 'Q', 'K', 'A'])


def hand_type_text(category: int, best5: Optional[List[str]] = None) -> str:
    """把牌型 category（必要）+ best5（可选）转为展示文本。

    用于在同花顺中区分“皇家同花顺”。
    """
    cat = int(category)
    if cat == 9 and best5 and _is_royal_flush(list(best5)):
        return '皇家同花顺（Royal Flush）'
    return hand_category_text(cat)


def _is_straight(values_desc: List[int]) -> Optional[int]:
    """判断是否顺子；若是则返回顺子的高牌点数，否则返回 None。

    values_desc 必须为去重后的降序点数列表。
    """
    if len(values_desc) < 5:
        return None
    vals = values_desc
    # 车轮顺子
    if set([14, 5, 4, 3, 2]).issubset(set(vals)):
        return 5

    # 普通顺子
    for i in range(len(vals) - 4):
        window = vals[i:i + 5]
        if window[0] - window[4] == 4 and len(window) == 5:
            return window[0]
    return None


def evaluate_5(cards5: List[str]) -> Tuple[int, Tuple[int, ...]]:
    """评估 5 张牌。

    返回 (category, tiebreak_tuple)，越大越强。
    """
    vals = sorted([RANK_TO_VAL[c[1]] for c in cards5], reverse=True)
    suits = [c[0] for c in cards5]
    is_flush = len(set(suits)) == 1

    unique_vals = sorted(set(vals), reverse=True)
    straight_high = _is_straight(unique_vals)

    # 点数计数
    count_map: Dict[int, int] = {}
    for v in vals:
        count_map[v] = count_map.get(v, 0) + 1
    counts = sorted(((cnt, v) for v, cnt in count_map.items()), reverse=True)
    # 计数结果按（数量降序，点数降序）排序

    if is_flush and straight_high is not None:
        # 同花顺
        return 9, (straight_high,)

    if counts[0][0] == 4:
        quad_val = counts[0][1]
        kicker = max(v for v in vals if v != quad_val)
        return 8, (quad_val, kicker)

    if counts[0][0] == 3 and len(counts) > 1 and counts[1][0] == 2:
        trip = counts[0][1]
        pair = counts[1][1]
        return 7, (trip, pair)

    if is_flush:
        return 6, tuple(sorted(vals, reverse=True))

    if straight_high is not None:
        return 5, (straight_high,)

    if counts[0][0] == 3:
        trip = counts[0][1]
        kickers = sorted([v for v in vals if v != trip], reverse=True)
        return 4, (trip, *kickers)

    if counts[0][0] == 2 and len(counts) > 1 and counts[1][0] == 2:
        pair_high = max(counts[0][1], counts[1][1])
        pair_low = min(counts[0][1], counts[1][1])
        kicker = max(v for v in vals if v not in (pair_high, pair_low))
        return 3, (pair_high, pair_low, kicker)

    if counts[0][0] == 2:
        pair = counts[0][1]
        kickers = sorted([v for v in vals if v != pair], reverse=True)
        return 2, (pair, *kickers)

    return 1, tuple(sorted(vals, reverse=True))


def evaluate_7(cards7: List[str]) -> Tuple[int, Tuple[int, ...], List[str]]:
    best = None
    best_cards = None
    for comb in itertools.combinations(cards7, 5):
        cat, tb = evaluate_5(list(comb))
        key = (cat, tb)
        if best is None or key > best:
            best = key
            best_cards = list(comb)
    assert best is not None and best_cards is not None
    return best[0], best[1], best_cards


# ----------------------------
# 位置/行动顺序
# ----------------------------


def compute_positions(game: dict) -> dict:
    """根据当前 dealer_seat_id 与在场玩家，计算 dealer/sb/bb/utg 的 seat_id。"""
    seats = list_seat_ids(game['players'], include_out=False)
    if len(seats) < 2:
        return {'dealer': None, 'sb': None, 'bb': None, 'utg': None}

    dealer = game.get('dealer_seat_id')
    if dealer not in seats:
        dealer = seats[0]
        game['dealer_seat_id'] = dealer

    if len(seats) == 2:
        sb = dealer
        bb = next_seat_in_order(seats, dealer)
        utg = sb  # 单挑：翻牌前先行动的是按钮位
    else:
        sb = next_seat_in_order(seats, dealer)
        bb = next_seat_in_order(seats, sb)
        utg = next_seat_in_order(seats, bb)

    return {'dealer': dealer, 'sb': sb, 'bb': bb, 'utg': utg}


def first_to_act_postflop(game: dict, dealer: int) -> Optional[int]:
    seats = list_seat_ids(game['players'], include_out=False)
    if len(seats) < 2:
        return None
    if len(seats) == 2:
        # 单挑：翻牌后由大盲位先行动（但必须仍为 active；否则跳过 allin/folded）
        cur = dealer
        for _ in range(len(seats)):
            cur = next_seat_in_order(seats, cur)
            p = find_player(game['players'], cur)
            if p and p.get('status') == 'active':
                return cur
        return None
    # 3+：从庄左开始找第一个可行动的玩家（跳过已弃牌/已全压/已出局）
    cur = dealer
    for _ in range(len(seats)):
        cur = next_seat_in_order(seats, cur)
        p = find_player(game['players'], cur)
        if p and p.get('status') == 'active':
            return cur
        if p and p.get('status') == 'allin':
            continue
        if p and p.get('status') == 'folded':
            continue
    return None


def role_name_for_seat(game: dict, seat_id: int) -> str:
    # 仅对“仍在场（未出局）”玩家分配位置；已出局座位返回空
    seats = list_seat_ids(game['players'], include_out=False)
    if seat_id not in seats:
        return ''

    pos = compute_positions(game)
    dealer = pos.get('dealer')
    if dealer is None or dealer not in seats:
        return ''

    # 按庄位开始的顺时针顺序排列
    order = [int(dealer)]
    cur = int(dealer)
    for _ in range(len(seats) - 1):
        cur = int(next_seat_in_order(seats, cur))
        order.append(cur)

    # 2-10 人局标准位置映射（相对庄位）
    role_codes_by_n = {
        2: ['BTN/D+SB', 'BB'],
        3: ['BTN/D', 'SB', 'BB'],
        4: ['BTN/D', 'SB', 'BB', 'UTG'],
        5: ['BTN/D', 'SB', 'BB', 'UTG', 'CO'],
        6: ['BTN/D', 'SB', 'BB', 'UTG', 'MP', 'CO'],
        7: ['BTN/D', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'CO'],
        8: ['BTN/D', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'HJ', 'CO'],
        9: ['BTN/D', 'SB', 'BB', 'UTG', 'UTG+1', 'UTG+2', 'MP', 'HJ', 'CO'],
        10: ['BTN/D', 'SB', 'BB', 'UTG', 'UTG+1', 'UTG+2', 'MP1', 'MP2', 'HJ', 'CO'],
    }
    codes = role_codes_by_n.get(len(order))
    if not codes:
        return ''

    seat_to_role = {order[i]: codes[i] for i in range(min(len(order), len(codes)))}
    return seat_to_role.get(int(seat_id), '')


# ----------------------------
# 牌局流程辅助
# ----------------------------


def reset_for_new_hand(game: dict) -> None:
    game['hand_no'] = int(game.get('hand_no', 0)) + 1
    game['street'] = 'preflop'
    game['community_cards'] = []
    game['deck'] = new_deck()
    shuffle_deck(game['deck'])
    game['pot'] = 0
    game['dead_money'] = 0
    game['current_high'] = 0
    game['min_raise'] = int(game.get('bb', 0))
    game['acting_seat_id'] = None
    game['need_action_seat_ids'] = []

    for p in game['players']:
        if p.get('chips', 0) <= 0:
            p['status'] = 'out'
            p['chips'] = 0
        else:
            p['status'] = 'active'
        p['current_bet'] = 0
        p['total_bet'] = 0
        p['hand_cards'] = []
        p['last_action'] = ''


def deal_hole_cards(game: dict) -> None:
    for p in game['players']:
        if p.get('status') != 'out':
            p['hand_cards'] = [game['deck'].pop(), game['deck'].pop()]


def post_blind(game: dict, seat_id: int, amount: int) -> int:
    p = find_player(game['players'], seat_id)
    if not p or p.get('status') == 'out':
        return 0
    pay = min(int(p.get('chips', 0)), int(amount))
    p['chips'] -= pay
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay
    if p['chips'] == 0:
        p['status'] = 'allin'
    return pay


def init_betting_round(game: dict, first_actor_seat_id: Optional[int]) -> None:
    game['acting_seat_id'] = first_actor_seat_id
    need = []
    for sid in list_seat_ids(game['players'], include_out=False):
        p = find_player(game['players'], int(sid))
        if p and p.get('status') == 'active':
            need.append(int(sid))
    game['need_action_seat_ids'] = need


def next_pending_actor(game: dict, from_seat_id: int) -> Optional[int]:
    """在 need_action_seat_ids 中寻找下一个仍为 active 的座位。"""
    need = set(int(x) for x in game.get('need_action_seat_ids', []))
    if not need:
        return None
    seat_order = list_seat_ids(game['players'], include_out=False)
    if not seat_order:
        return None
    cur = from_seat_id
    for _ in range(len(seat_order)):
        cur = next_seat_in_order(seat_order, cur)
        if cur in need:
            p = find_player(game['players'], cur)
            if p and p.get('status') == 'active':
                return cur
    return None


def start_hand(game: dict) -> dict:
    """把 game 推进到新的一手，并返回本手的位置信息（dealer/sb/bb/utg）。"""
    reset_for_new_hand(game)

    pos = compute_positions(game)
    game['dealer_seat_id'] = pos['dealer']
    game['sb_seat_id'] = pos['sb']
    game['bb_seat_id'] = pos['bb']

    deal_hole_cards(game)
    
    # 一开始就发好5张公共牌
    cc = game.get('community_cards', [])
    if len(cc) < 5:
        needed = 5 - len(cc)
        for _ in range(needed):
            if len(game['deck']) > 0:
                game['community_cards'].append(game['deck'].pop())
    # 如果牌数超过5张，把多余的牌放回牌堆（按原顺序放回到堆顶）
    elif len(cc) > 5:
        extras = cc[5:]
        game['community_cards'] = cc[:5]
        # 还回到牌堆的顺序：把 extras 按原序追加到 deck（deck.pop() 从末尾取牌）
        for card in extras:
            game['deck'].append(card)

    # 盲注
    sb_paid = post_blind(game, pos['sb'], int(game['sb']))
    bb_paid = post_blind(game, pos['bb'], int(game['bb']))

    # 本街最高投入初始化为大盲注额
    game['current_high'] = max(sb_paid, bb_paid)
    game['min_raise'] = int(game['bb'])

    # 翻牌前的第一个行动者
    if len(list_seat_ids(game['players'], include_out=False)) == 2:
        first_actor = pos['sb']
    else:
        first_actor = pos['utg']

    init_betting_round(game, first_actor)

    # 记录盲注动作文本（用于面板显示）
    sb_p = find_player(game['players'], pos['sb'])
    if sb_p:
        sb_p['last_action'] = f"SB {sb_paid}"
    bb_p = find_player(game['players'], pos['bb'])
    if bb_p:
        bb_p['last_action'] = f"BB {bb_paid}"

    return pos


def can_check(game: dict, seat_id: int) -> bool:
    p = find_player(game['players'], seat_id)
    if not p:
        return False
    return int(p.get('current_bet', 0)) == int(game.get('current_high', 0))


def apply_fold(game: dict, seat_id: int) -> None:
    p = find_player(game['players'], seat_id)
    if not p:
        return
    p['status'] = 'folded'
    p['last_action'] = 'fold'
    if seat_id in game['need_action_seat_ids']:
        game['need_action_seat_ids'].remove(seat_id)


def apply_call_or_check(game: dict, seat_id: int) -> Tuple[str, int]:
    p = find_player(game['players'], seat_id)
    if not p:
        return 'invalid', 0

    gap = int(game['current_high']) - int(p.get('current_bet', 0))
    if gap <= 0:
        p['last_action'] = 'check'
        if seat_id in game['need_action_seat_ids']:
            game['need_action_seat_ids'].remove(seat_id)
        return 'check', 0

    pay = min(int(p.get('chips', 0)), gap)
    p['chips'] -= pay
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay

    if p['chips'] == 0:
        p['status'] = 'allin'
        p['last_action'] = f"allin {pay}"
    else:
        p['last_action'] = f"call {pay}"

    if seat_id in game['need_action_seat_ids']:
        game['need_action_seat_ids'].remove(seat_id)

    return 'call', pay


def apply_bet(game: dict, seat_id: int, amount: int) -> Tuple[bool, str]:
    p = find_player(game['players'], seat_id)
    if not p or p.get('status') != 'active':
        return False, 'invalid'

    if int(game.get('current_high', 0)) != 0:
        return False, 'not_allowed'

    bb = int(game.get('bb', 0))
    if amount < bb:
        return False, 'too_small'

    pay = min(int(p.get('chips', 0)), int(amount))
    p['chips'] -= pay
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay

    new_high = int(p['current_bet'])
    game['current_high'] = new_high
    game['min_raise'] = max(bb, int(amount))

    if p['chips'] == 0:
        p['status'] = 'allin'
        p['last_action'] = f"allin {pay}"
    else:
        p['last_action'] = f"bet {pay}"

    # 重新设置其它玩家的待行动列表
    need = []
    for sid in list_seat_ids(game['players'], include_out=False):
        if int(sid) == int(seat_id):
            continue
        q = find_player(game['players'], int(sid))
        if q and q.get('status') == 'active':
            need.append(int(sid))
    game['need_action_seat_ids'] = need
    return True, 'ok'


def apply_raise(game: dict, seat_id: int, raise_delta: int) -> Tuple[bool, str, int]:
    p = find_player(game['players'], seat_id)
    if not p or p.get('status') != 'active':
        return False, 'invalid', 0

    gap = int(game['current_high']) - int(p.get('current_bet', 0))
    if gap < 0:
        gap = 0

    min_raise = int(game.get('min_raise', 0))
    if raise_delta < min_raise:
        return False, 'too_small', 0

    need_total = gap + int(raise_delta)
    pay = min(int(p.get('chips', 0)), need_total)

    p['chips'] -= pay
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay

    new_high = int(p['current_bet'])
    if new_high > int(game['current_high']):
        actual_delta = new_high - int(game['current_high'])
        game['current_high'] = new_high
        # 仅当满足“完整加注”时才更新最小加注阈值
        if actual_delta >= min_raise:
            game['min_raise'] = actual_delta
            # 重新设置其它玩家的待行动列表
            need = []
            for sid in list_seat_ids(game['players'], include_out=False):
                if int(sid) == int(seat_id):
                    continue
                q = find_player(game['players'], int(sid))
                if q and q.get('status') == 'active':
                    need.append(int(sid))
            game['need_action_seat_ids'] = need
        else:
            if seat_id in game['need_action_seat_ids']:
                game['need_action_seat_ids'].remove(seat_id)
    else:
        if seat_id in game['need_action_seat_ids']:
            game['need_action_seat_ids'].remove(seat_id)

    if p['chips'] == 0:
        p['status'] = 'allin'
        p['last_action'] = f"allin {pay}"
    else:
        p['last_action'] = f"raise {pay}"

    return True, 'ok', pay


def apply_allin(game: dict, seat_id: int) -> Tuple[bool, str, int]:
    p = find_player(game['players'], seat_id)
    if not p or p.get('status') != 'active':
        return False, 'invalid', 0

    pay = int(p.get('chips', 0))
    if pay <= 0:
        return False, 'invalid', 0

    gap = int(game['current_high']) - int(p.get('current_bet', 0))
    if gap < 0:
        gap = 0

    p['chips'] = 0
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay
    p['status'] = 'allin'

    new_high = int(p['current_bet'])
    if new_high > int(game['current_high']):
        actual_delta = new_high - int(game['current_high'])
        min_raise = int(game.get('min_raise', 0))
        game['current_high'] = new_high
        if actual_delta >= min_raise:
            # 完整加注：重新设置所有 active 玩家的待行动列表
            game['min_raise'] = actual_delta
            need = []
            for sid in list_seat_ids(game['players'], include_out=False):
                if int(sid) == int(seat_id):
                    continue
                q = find_player(game['players'], int(sid))
                if q and q.get('status') == 'active':
                    need.append(int(sid))
            game['need_action_seat_ids'] = need
        else:
            # 不足最小加注（The Full Bet Rule）：锁定之前已经行动过的玩家
            # 只保留那些还没有行动过的玩家（current_bet < current_high）在待行动列表中
            if seat_id in game['need_action_seat_ids']:
                game['need_action_seat_ids'].remove(seat_id)
            # 移除所有已经行动过的玩家（current_bet >= current_high）
            need_action = []
            for sid in game.get('need_action_seat_ids', []):
                q = find_player(game['players'], int(sid))
                if q and q.get('status') == 'active':
                    current_bet = int(q.get('current_bet', 0))
                    if current_bet < int(game['current_high']):
                        # 还没有行动过，保留在待行动列表中
                        need_action.append(int(sid))
            game['need_action_seat_ids'] = need_action
    else:
        if seat_id in game['need_action_seat_ids']:
            game['need_action_seat_ids'].remove(seat_id)

    p['last_action'] = f"allin {pay}"
    return True, 'ok', pay


def is_betting_round_over(game: dict) -> bool:
    # 若仅剩 1 名仍在争夺底池的玩家（active/allin），本手等同结束
    eligible = [p for p in game['players'] if p.get('status') in ('active', 'allin')]
    if len(eligible) <= 1:
        return True

    # 否则仅当本街所有需要行动的 active 都已行动，下注轮才结束
    return len(game.get('need_action_seat_ids', [])) == 0


def advance_street(game: dict) -> None:
    street = game.get('street')
    cc = game.get('community_cards', [])
    
    if street == 'preflop':
        # 翻牌：需要3张，如果不够则补发
        game['street'] = 'flop'
        if len(cc) < 3:
            needed = 3 - len(cc)
            for _ in range(needed):
                if len(game['deck']) > 0:
                    game['community_cards'].append(game['deck'].pop())
    elif street == 'flop':
        # 转牌：需要4张，如果不够则补发
        game['street'] = 'turn'
        if len(cc) < 4:
            needed = 4 - len(cc)
            for _ in range(needed):
                if len(game['deck']) > 0:
                    game['community_cards'].append(game['deck'].pop())
    elif street == 'turn':
        # 河牌：需要5张，如果不够则补发
        game['street'] = 'river'
        if len(cc) < 5:
            needed = 5 - len(cc)
            for _ in range(needed):
                if len(game['deck']) > 0:
                    game['community_cards'].append(game['deck'].pop())
    elif street == 'river':
        game['street'] = 'showdown'

    # 若 community_cards 超过 5 张，多余的应退回牌堆以保持牌堆一致性
    cc_now = game.get('community_cards', [])
    if len(cc_now) > 5:
        extras = cc_now[5:]
        game['community_cards'] = cc_now[:5]
        for card in extras:
            game['deck'].append(card)

    # 重置本街下注
    for p in game['players']:
        p['current_bet'] = 0
        p['last_action'] = '' if p.get('status') == 'active' else p.get('last_action', '')

    game['current_high'] = 0
    game['min_raise'] = int(game.get('bb', 0))

    # 若本局 active 少于 2 人，则后续不会再产生有效下注（对手无法回应）。
    # 这种情况下不再初始化行动位，交给上层流程直接补齐公共牌到摊牌。
    active_cnt = len([p for p in game.get('players', []) if p.get('status') == 'active'])
    if active_cnt < 2:
        game['acting_seat_id'] = None
        game['need_action_seat_ids'] = []
        return

    # 初始化新一轮下注
    dealer = game.get('dealer_seat_id')
    first_actor = None
    if game['street'] in ('flop', 'turn', 'river'):
        if dealer is not None:
            first_actor = first_to_act_postflop(game, int(dealer))
    game['acting_seat_id'] = first_actor
    need = []
    for sid in list_seat_ids(game['players'], include_out=False):
        p = find_player(game['players'], int(sid))
        if p and p.get('status') == 'active':
            need.append(int(sid))
    game['need_action_seat_ids'] = need


def fast_forward_to_showdown(game: dict) -> None:
    """按正常发牌流程将公共牌补齐到摊牌（最多 5 张）。

    用于“提前弃牌/只剩一人”等场景：虽然无需继续行动，但结算展示仍希望
    公共牌完整到 5 张。
    """
    max_steps = 10
    steps = 0
    while steps < max_steps and game.get('street') != 'showdown':
        st = game.get('street')
        if st not in ('preflop', 'flop', 'turn', 'river'):
            break
        advance_street(game)
        steps += 1


def award_single_winner(game: dict, winner_seat_id: int) -> None:
    p = find_player(game['players'], winner_seat_id)
    if not p:
        return
    p['chips'] += int(game.get('pot', 0))
    game['pot'] = 0


def build_side_pots(players: List[dict], dead_money: int = 0) -> List[dict]:
    contrib = []
    for p in players:
        tb = int(p.get('total_bet', 0))
        if tb > 0:
            contrib.append((int(p['seat_id']), tb, p.get('status')))

    if not contrib:
        if dead_money > 0:
            # 仅有死钱：直接作为奖池，给仍在争夺底池的玩家竞争
            elig = [int(p['seat_id']) for p in players if p.get('status') in ('active', 'allin')]
            return [{'amount': dead_money, 'eligible_seat_ids': elig}]
        return []

    # 取所有不同的投入层级
    levels = sorted(set(tb for _, tb, _ in contrib))
    pots = []
    prev = 0
    for lvl in levels:
        delta = lvl - prev
        if delta <= 0:
            continue
        seats_in_layer = [sid for sid, tb, _ in contrib if tb >= lvl]
        amount = delta * len(seats_in_layer)
        elig = [sid for sid, tb, st in contrib if tb >= lvl and st in ('active', 'allin')]
        pots.append({'amount': amount, 'eligible_seat_ids': elig})
        prev = lvl

    # 把死钱合并进主池（第一个奖池）
    if dead_money > 0:
        if pots:
            pots[0]['amount'] += int(dead_money)
        else:
            elig = [int(p['seat_id']) for p in players if p.get('status') in ('active', 'allin')]
            pots.append({'amount': int(dead_money), 'eligible_seat_ids': elig})

    return pots


def settle_showdown(game: dict) -> dict:
    """进行摊牌结算并返回结算结果（用于渲染）。"""
    eligible = in_showdown_eligible(game['players'])
    # 确保有完整的5张公共牌（兜底逻辑）
    cc = game.get('community_cards', [])
    if len(cc) < 5:
        needed = 5 - len(cc)
        for _ in range(needed):
            if len(game.get('deck', [])) > 0:
                game['community_cards'].append(game['deck'].pop())
    # 如果牌数超过5张，只保留前5张（保护机制，确保只用5张公共牌）
    elif len(cc) > 5:
        game['community_cards'] = cc[:5]
    # 结算时只使用前5张公共牌
    board = list(game.get('community_cards', []))[:5]
    
    if len(eligible) == 1:
        winner = int(eligible[0]['seat_id'])
        pot_amount = int(game.get('pot', 0))
        award_single_winner(game, winner)
        
        # 即使只有一个人赢，也要返回showdown类型以显示详细结算
        # 构建eval_map，包含所有有手牌的玩家（包括已弃牌的）
        eval_map: Dict[int, Tuple[int, Tuple[int, ...], List[str]]] = {}
        for p in game['players']:
            if p.get('hand_cards') and p.get('status') != 'out' and not p.get('left'):
                sid = int(p['seat_id'])
                cards7 = board + list(p.get('hand_cards', []))
                eval_map[sid] = evaluate_7(cards7)
        
        # 构建单赢家的分配结果
        distribution = [{'pot': pot_amount, 'winners': [winner]}]
        
        return {
            'type': 'showdown',
            'distribution': distribution,
            'eval': {str(sid): {'cat': eval_map[sid][0], 'best5': eval_map[sid][2]} for sid in eval_map},
            'refunds': [],
            'single_winner': True,  # 标记这是单赢家情况
        }

    eval_map: Dict[int, Tuple[int, Tuple[int, ...], List[str]]] = {}
    for p in eligible:
        sid = int(p['seat_id'])
        cards7 = board + list(p.get('hand_cards', []))
        eval_map[sid] = evaluate_7(cards7)

    pots = build_side_pots(game['players'], int(game.get('dead_money', 0)))
    distribution = []
    refunds = []

    for pot in pots[::-1]:
        amt = int(pot['amount'])
        elig_sids = [sid for sid in pot['eligible_seat_ids'] if sid in eval_map]
        if not elig_sids or amt <= 0:
            continue
        best_key = None
        winners = []
        for sid in elig_sids:
            key = (eval_map[sid][0], eval_map[sid][1])
            if best_key is None or key > best_key:
                best_key = key
                winners = [sid]
            elif key == best_key:
                winners.append(sid)

        share = amt // len(winners)
        rem = amt % len(winners)

        # 若该奖池层只有 1 个 eligible，说明是未被跟注的超额投入（应退款而非展示边池）
        if len(elig_sids) == 1 and len(winners) == 1:
            sid_only = int(winners[0])
            find_player(game['players'], sid_only)['chips'] += int(amt)
            refunds.append({'seat_id': sid_only, 'amount': int(amt)})
            continue

        for sid in winners:
            find_player(game['players'], sid)['chips'] += share
        if rem > 0:
            # 余数给庄位左手边第一个在赢家列表中的玩家（标准规则）
            # 即从 SB 位置开始，按顺时针顺序找到第一个在赢家列表中的玩家
            pos = compute_positions(game)
            sb_seat = pos.get('sb')
            seats = list_seat_ids(game['players'], include_out=False)
            winner_set = set(winners)
            sid0 = None
            if sb_seat and sb_seat in winner_set:
                sid0 = sb_seat
            else:
                # 从 SB 位置开始，按顺时针顺序查找
                cur = sb_seat if sb_seat else seats[0]
                for _ in range(len(seats)):
                    if cur in winner_set:
                        sid0 = cur
                        break
                    cur = next_seat_in_order(seats, cur)
            # 如果还是没找到（理论上不应该发生），则使用座位号最小的作为兜底
            if sid0 is None:
                sid0 = sorted(winners)[0]
            find_player(game['players'], sid0)['chips'] += rem

        distribution.append({'pot': amt, 'winners': sorted(winners)})

    # 底池已完全分配
    game['pot'] = 0

    return {
        'type': 'showdown',
        'distribution': distribution[::-1],
        'eval': {str(sid): {'cat': eval_map[sid][0], 'best5': eval_map[sid][2]} for sid in eval_map},
        'refunds': refunds,
    }


def rotate_dealer(game: dict) -> None:
    seats = list_seat_ids(game['players'], include_out=False)
    if len(seats) < 2:
        return
    dealer = game.get('dealer_seat_id')
    if dealer not in seats:
        game['dealer_seat_id'] = seats[0]
        return
    game['dealer_seat_id'] = next_seat_in_order(seats, int(dealer))


def remove_broke_players(game: dict) -> List[int]:
    removed = []
    for p in game['players']:
        if int(p.get('chips', 0)) <= 0:
            if p.get('status') != 'out':
                p['status'] = 'out'
                removed.append(int(p['seat_id']))
    return removed


def compact_players(game: dict) -> None:
    """移除已出局（out）的玩家（可选使用）。"""
    game['players'] = [p for p in game['players'] if p.get('status') != 'out']


def check_auto_end(game: dict) -> Optional[int]:
    alive = [p for p in game['players'] if p.get('status') != 'out' and int(p.get('chips', 0)) > 0]
    if len(alive) == 1:
        return int(alive[0]['seat_id'])
    return None


def qq_is_friend(plugin_event, user_id: str) -> bool:
    """仅 QQ 平台使用好友列表验证是否可私聊。"""
    try:
        if plugin_event.platform.get('platform') != 'qq':
            return True
    except Exception:
        return True

    try:
        friend_res = plugin_event.get_friend_list()
        if not isinstance(friend_res, dict):
            return False
        friend_items = friend_res.get('data')
        if not isinstance(friend_items, list):
            return False

        target = str(user_id)
        for u in friend_items:
            if not isinstance(u, dict):
                continue
            uid = u.get('id')
            if uid is None:
                continue
            if str(uid) == target:
                return True

        return False
    except Exception:
        return False


# ----------------------------
# 字符串解析辅助函数
# ----------------------------


def getNumberPara(data, reverse=False):
    """
    从字符串中分离出数字和非数字部分。
    
    Args:
        data: 输入字符串
        reverse: False时从左往右找数字，True时从右往左找数字
        
    Returns:
        [非数字部分, 数字部分] (当reverse=False)
        或 [数字部分, 非数字部分] (当reverse=True)
    """
    tmp_output_str_1 = ''
    tmp_output_str_2 = ''
    if len(data) > 0:
        flag_have_para = False
        tmp_offset = 0
        tmp_total_offset = 0
        while True:
            tmp_offset += 1
            if reverse:
                tmp_total_offset = len(data) - tmp_offset
            else:
                tmp_total_offset = tmp_offset - 1
            if not reverse and tmp_total_offset >= len(data):
                flag_have_para = True
                break
            if reverse and tmp_total_offset < 0:
                tmp_total_offset = 0
                flag_have_para = True
                break
            if data[tmp_total_offset].isdecimal():
                pass
            else:
                flag_have_para = True
                if reverse:
                    tmp_total_offset += 1
                break
        if flag_have_para:
            tmp_output_str_1 = data[:tmp_total_offset]
            tmp_output_str_2 = data[tmp_total_offset:]
    return [tmp_output_str_1, tmp_output_str_2]


def getToNumberPara(data):
    """
    从字符串中找到第一个数字或空格的位置，并分割字符串。
    
    Args:
        data: 输入字符串
        
    Returns:
        [数字/空格之前的部分, 数字/空格及之后的部分]
    """
    tmp_output_str_1 = ''
    tmp_output_str_2 = ''
    if len(data) > 0:
        flag_have_para = False
        tmp_offset = 0
        tmp_total_offset = 0
        while True:
            tmp_offset += 1
            tmp_total_offset = tmp_offset - 1
            if tmp_total_offset >= len(data):
                flag_have_para = True
                break
            if data[tmp_total_offset].isdecimal():
                flag_have_para = True
                break
            if data[tmp_total_offset] == ' ':
                flag_have_para = True
                break

        if flag_have_para:
            tmp_output_str_1 = data[:tmp_total_offset]
            tmp_output_str_2 = data[tmp_total_offset:]
        else:
            tmp_output_str_2 = data
    return [tmp_output_str_1, tmp_output_str_2]


# ----------------------------
# 消息发送辅助
# ----------------------------
def sendMsgByEvent(plugin_event, message, target_id, target_type, host_id=None):
    group_id = None
    user_id = None
    tmp_name = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]['strBotName']
    tmp_self_id = plugin_event.bot_info.id
    if target_type == 'private':
        user_id = target_id
    elif target_type == 'group':
        group_id = target_id
    OlivaDiceCore.crossHook.dictHookFunc['msgHook'](
        plugin_event,
        'send_%s' % target_type,
        {
            'name': tmp_name,
            'id': tmp_self_id
        },
        [host_id, group_id, user_id],
        str(message)
    )
    return OlivaDiceCore.msgReply.pluginSend(plugin_event, target_type, target_id, message, host_id=host_id)