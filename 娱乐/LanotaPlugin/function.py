# -*- encoding: utf-8 -*-
"""Lanota 曲库业务逻辑与图片渲染。"""

import datetime
import math
import random
import re
import uuid
from pathlib import Path
from typing import Any

from . import config
from . import utils

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

function_module_note = 'Lanota 曲库查询、随机、今日曲、计算与图片回复。'
DEFAULT_BG_COLOR = (247, 219, 255, 255)
FONT_SIZE = 24
PADDING = 30
LINE_SPACING = 5
MAX_WIDTH = 800


category_map = {
    'main': 'main',
    '主线': 'main',
    'side': 'side',
    '支线': 'side',
    'expansion': 'expansion',
    '扩展': 'expansion',
    '扩展包': 'expansion',
    '曲包': 'expansion',
    'event': 'event',
    '活动': 'event',
    '限时活动': 'event',
    'subscription': 'subscription',
    '书房': 'subscription',
    '订阅': 'subscription',
    'inf': 'subscription',
    '无限': 'subscription',
}

category_name_map = {
    'main': '主线',
    'side': '支线',
    'expansion': '曲包',
    'event': '活动',
    'subscription': '书房',
}


def load_song_data() -> list[dict[str, Any]]:
    data = utils.read_json_file(utils.get_song_list_path(), [])
    return data if isinstance(data, list) else []


def save_song_data(song_data: list[dict[str, Any]]) -> bool:
    return utils.save_json_file(utils.get_song_list_path(), song_data)


def load_alias_data() -> dict[str, list[str]]:
    data = utils.read_json_file(utils.get_song_alias_path(), {})
    return data if isinstance(data, dict) else {}


def save_alias_data(alias_data: dict[str, list[str]]) -> bool:
    return utils.save_json_file(utils.get_song_alias_path(), alias_data)


def load_table_data() -> dict[str, Any]:
    data = utils.read_json_file(utils.get_song_table_path(), {})
    return data if isinstance(data, dict) else {}


def load_user_data(bot_hash: Any = None) -> dict[str, Any]:
    data = utils.read_json_file(utils.ensure_user_data_file(bot_hash), {})
    return data if isinstance(data, dict) else {}


def save_user_data(user_data: dict[str, Any], bot_hash: Any = None) -> bool:
    return utils.save_json_file(utils.ensure_user_data_file(bot_hash), user_data)


def get_today_seed() -> int:
    return int(datetime.date.today().strftime('%Y%m%d'))


def get_user_today_song(user_id: str, bot_hash: Any = None):
    user_data = load_user_data(bot_hash)
    today_seed = get_today_seed()
    user_key = str(user_id)
    user_info = user_data.setdefault(user_key, {})

    if user_info.get('today_date') == today_seed:
        chapter = str(user_info.get('today_chapter', '')).lower()
        for song in load_song_data():
            if str(song.get('chapter', '')).lower() == chapter:
                return song

    song_data = load_song_data()
    if not song_data:
        return None
    try:
        random.seed(today_seed + int(user_id))
    except Exception:
        random.seed(today_seed)
    today_song = random.choice(song_data)
    user_info['today_chapter'] = today_song.get('chapter', '')
    user_info['today_date'] = today_seed
    save_user_data(user_data, bot_hash)
    return today_song


def get_value(value: Any) -> str:
    if value is None:
        return '未知'
    text = str(value).strip()
    if text.lower() in ['none', 'no', 'n/a', 'unknown', '未知', '', 'no info']:
        return '未知'
    return text


def format_table_constant(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    range_match = re.match(r'^(\d+(?:\.\d+)?)(\s*[~-]\s*)(\d+(?:\.\d+)?)$', text)
    if range_match:
        left, sep, right = range_match.groups()
        return f'{format_table_constant(left)}{sep}{format_table_constant(right)}'
    try:
        return f'{float(text):.1f}'
    except ValueError:
        return text


def format_song_info(song: dict[str, Any]) -> str:
    """按原 nonebot 插件格式渲染乐曲信息。"""
    table_data = load_table_data()
    chapter = get_value(song.get('chapter'))
    chapter_difficulty = table_data.get(chapter, {}) if chapter else {}
    legacy_info = song.get('Legacy', {})
    difficulty = song.get('difficulty', {}) if isinstance(song.get('difficulty'), dict) else {}
    notes = song.get('notes', {}) if isinstance(song.get('notes'), dict) else {}

    def format_difficulty_info(diff_type: str) -> str:
        diff_str = get_value(difficulty.get(diff_type))
        notes_str = f'物量: {get_value(notes.get(diff_type))}'
        table_key = diff_type.capitalize()
        table_diff = chapter_difficulty.get(table_key)
        if table_diff:
            return f'{diff_str}({format_table_constant(table_diff)}) ({notes_str})'
        return f'{diff_str} ({notes_str})'

    def format_legacy_difficulty(diff_key: str, max_key: str) -> str:
        if not isinstance(legacy_info, dict):
            return '无信息'
        diff_value = legacy_info.get(diff_key)
        max_value = legacy_info.get(max_key)
        if diff_value or max_value:
            return f'{get_value(diff_value)} (物量: {get_value(max_value)})'
        return '无信息'

    line_list = [
        '══════════ 乐曲信息 ══════════',
        f'▪ 乐曲ID: {get_value(song.get("id"))}',
        f'▪ 曲名: {get_value(song.get("title"))}',
        f'▪ 分类: {category_name_map.get(song.get("category"), get_value(song.get("category")))}',
        f'▪ 章节: {chapter}',
        f'▪ 曲师: {get_value(song.get("artist"))}',
        f'▪ 歌手: {get_value(song.get("vocals"))}',
        f'▪ 曲风: {get_value(song.get("genre"))}',
        f'▪ 乐曲BPM: {get_value(song.get("bpm"))}',
        f'▪ 时长: {get_value(song.get("time"))}',
        f'▪ 更新版本: {get_value(song.get("version"))}',
        '══════════ 难度信息 ══════════',
        f'▪ 谱师: {get_value(song.get("chart_design"))}',
        f'    ┌ Whisper: {format_difficulty_info("whisper")}',
        f'    ├ Acoustic: {format_difficulty_info("acoustic")}',
        f'    ├ Ultra: {format_difficulty_info("ultra")}',
        f'    └ Master: {format_difficulty_info("master")}',
    ]
    if isinstance(legacy_info, dict) and legacy_info:
        line_list.extend(
            [
                '══════════ 旧谱信息 ══════════',
                f'▪ 谱师: {get_value(legacy_info.get("Chart Design"))}',
                f'    ┌ Whisper: {format_legacy_difficulty("DiffWhisper", "MaxWhisper")}',
                f'    ├ Acoustic: {format_legacy_difficulty("DiffAcoustic", "MaxAcoustic")}',
                f'    ├ Ultra: {format_legacy_difficulty("DiffUltra", "MaxUltra")}',
                f'    └ Master: {format_legacy_difficulty("DiffMaster", "MaxMaster")}',
            ]
        )
    line_list.extend(
        [
            '══════════ 其他信息 ══════════',
            '▪ 全曲列表: https://lanota.fandom.com/wiki/Songs',
            f'▪ 信息来源: {get_value(song.get("source_url"))}',
            '═════════════════════════',
        ]
    )
    return '\n'.join(line_list)


def get_songs_by_category(song_data: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    return [song for song in song_data if song.get('category') == category]


def get_songs_by_level(song_data: list[dict[str, Any]], level: str) -> list[dict[str, Any]]:
    return [
        song
        for song in song_data
        if str(song.get('difficulty', {}).get('whisper')) == level
        or str(song.get('difficulty', {}).get('acoustic')) == level
        or str(song.get('difficulty', {}).get('ultra')) == level
        or str(song.get('difficulty', {}).get('master')) == level
    ]


def find_song_by_search_term(
    search_term: str,
    song_data: list[dict[str, Any]],
    alias_data: dict[str, list[str]] | None = None,
    max_display: int = 10,
) -> tuple[list[dict[str, Any]], str | None, int]:
    alias_data = alias_data if isinstance(alias_data, dict) else load_alias_data()
    search_text = str(search_term).strip()
    if not search_text:
        return [], None, 0

    matched_songs = [song for song in song_data if str(song.get('chapter', '')).lower() == search_text.lower()]
    match_type = '章节号匹配' if matched_songs else None

    if not matched_songs:
        try:
            song_id = int(search_text)
            matched_songs = [song for song in song_data if int(song.get('id', -1)) == song_id]
            match_type = 'ID匹配' if matched_songs else None
        except Exception:
            pass

    if not matched_songs:
        alias_matches = []
        for song in song_data:
            aliases = alias_data.get(str(song.get('title')), [])
            if search_text.lower() in [str(alias).lower() for alias in aliases]:
                alias_matches.append(song)
        matched_songs = alias_matches
        match_type = '别名匹配' if matched_songs else None

    if not matched_songs:
        matched_songs = [song for song in song_data if str(song.get('title', '')).lower() == search_text.lower()]
        match_type = '曲名匹配' if matched_songs else None

    if not matched_songs:
        search_lower = search_text.lower()
        title_matches = [song for song in song_data if search_lower in str(song.get('title', '')).lower()]
        alias_matches = []
        for song in song_data:
            for alias in alias_data.get(str(song.get('title')), []):
                if search_lower in str(alias).lower():
                    alias_matches.append(song)
                    break
        unique = {}
        for song in title_matches + alias_matches:
            unique[str(song.get('id'))] = song
        matched_songs = list(unique.values())
        match_type = '模糊搜索' if matched_songs else None

    total_count = len(matched_songs)
    return matched_songs[:max_display], match_type, total_count


def find_artist_by_search_term(search_term: str, song_data: list[dict[str, Any]], max_display: int = 10):
    search_lower = str(search_term).strip().lower()
    if not search_lower:
        return [], None, 0
    artist_map = {}
    for song in song_data:
        artist = str(song.get('artist', '')).strip()
        if artist:
            artist_map.setdefault(artist.lower(), artist)
    artists = list(artist_map.values())
    matched = [artist for artist in artists if artist.lower() == search_lower]
    match_type = '曲师精确匹配' if matched else None
    if not matched:
        matched = [artist for artist in artists if search_lower in artist.lower()]
        match_type = '曲师模糊匹配' if matched else None
    return matched[:max_display], match_type, len(matched)


def calculate_rating(harmony: int, tune: int, fail: int, notes: int, level: str):
    try:
        notes = int(notes)
    except Exception:
        return 0.0, fail, 0, False, False, 0, 0
    if harmony < 0 or tune < 0 or fail < 0 or notes < 0:
        return 0.0, fail, 0, False, True, 0, 0
    if not (notes > 0):
        return 0.0, fail, 0, False, False, 0, 0
    if harmony + tune + fail > notes:
        return 0.0, fail, 0, True, False, 0, 0

    level_text = str(level).strip()
    bonus = 0.0
    if level_text.endswith('+'):
        try:
            base_level = float(level_text[:-1])
        except ValueError:
            return 0.0, fail, 0, False, False, 0, 0
        bonus = {'13+': 0.5, '14+': 0.5, '15+': 0.75, '16+': 1.25}.get(level_text, 0.0)
    else:
        try:
            base_level = float(level_text)
        except ValueError:
            return 0.0, fail, 0, False, False, 0, 0
        bonus = 0.5 if base_level == 16 else 0.0
    if not 1 <= base_level <= 16:
        return 0.0, fail, 0, False, False, 0, 0

    adjustment = notes - (harmony + tune + fail)
    adjusted_fail = fail + adjustment
    rating = (harmony + tune / 3) / notes * (base_level + 1 + bonus)
    return round(rating, 5), adjusted_fail, adjustment, False, False, bonus, base_level


def random_index(max_index: int) -> int:
    try:
        import requests

        url = (
            'https://www.random.org/integers/'
            f'?num=1&min=0&max={max_index}&col=1&base=10&format=plain&rnd=new'
        )
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return int(response.text.strip())
    except Exception:
        pass
    return random.randint(0, max_index)


def parse_color(value: str):
    color_text = str(value).strip().lstrip('#')
    if not re.match(r'^[0-9a-fA-F]{6}$', color_text):
        return None
    return tuple(int(color_text[index : index + 2], 16) for index in (0, 2, 4)) + (255,)


def get_user_bg_color(user_id: str, bot_hash: Any = None):
    user_info = load_user_data(bot_hash).get(str(user_id), {})
    color = parse_color(user_info.get('bg_color', ''))
    return color or DEFAULT_BG_COLOR


def is_dark_color(color) -> bool:
    return (0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]) < 128


def get_font():
    if not PIL_AVAILABLE:
        return None
    font_path = utils.get_font_path()
    try:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, FONT_SIZE)
    except Exception:
        pass
    return ImageFont.load_default()


def wrap_text(text: str, max_chars: int = 20) -> list[str]:
    lines = []
    token_pattern = re.compile(
        r'(\d+[\+\-\*/=]+\d+|'
        r"[a-zA-Z_]+(?:'[a-zA-Z_]+)*|"
        r'\d+|'
        r'[^\w\s\u4e00-\u9fff]|'
        r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]|'
        r'\s)'
    )

    for paragraph in str(text).split('\n'):
        if not paragraph.strip():
            lines.append('\n')
            continue

        token_list = []
        last_end = 0
        for match in token_pattern.finditer(paragraph):
            if match.start() > last_end:
                token_list.extend(list(paragraph[last_end : match.start()]))
            token_list.append(match.group())
            last_end = match.end()
        if last_end < len(paragraph):
            token_list.extend(list(paragraph[last_end:]))

        current_line = []
        current_length = 0
        for token in token_list:
            token_length = 1
            if current_length + token_length <= max_chars:
                current_line.append(token)
                current_length += token_length
            else:
                if current_line:
                    lines.append(''.join(current_line))
                current_line = [token]
                current_length = token_length
        if current_line:
            lines.append(''.join(current_line))
    return lines


def cubic_bezier(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    u = 1 - t
    return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3


def get_line_size(draw, line: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), line, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def cleanup_image_cache() -> None:
    try:
        files = sorted(Path(utils.get_generate_image_dir()).glob('lanota_*.png'), key=lambda item: item.stat().st_mtime)
        for file_path in files[:-config.image_cache_limit]:
            file_path.unlink()
    except Exception:
        pass


def create_text_image(text: str, user_id: str = '', max_chars: int | None = None, bot_hash: Any = None) -> str | None:
    if not PIL_AVAILABLE:
        return None
    cleanup_image_cache()
    font = get_font()
    max_chars = max_chars or config.image_max_chars
    lines = wrap_text(text, max_chars=max_chars)
    dummy = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(dummy)
    content_width = 0
    content_height = 0
    for line in lines:
        if line == '\n':
            content_height += FONT_SIZE + LINE_SPACING
            continue
        line_width, line_height = get_line_size(draw, line, font)
        content_width = max(content_width, line_width)
        content_height += line_height + LINE_SPACING
    canvas_width = content_width + PADDING * 2
    canvas_height = content_height + PADDING * 2

    bg_color = get_user_bg_color(user_id, bot_hash)
    dark_mode = is_dark_color(bg_color)
    end_color = (0, 0, 0, 255) if dark_mode else (255, 255, 255, 255)
    image = Image.new('RGBA', (canvas_width, canvas_height), end_color)
    center_x, center_y = canvas_width // 2, canvas_height // 2
    max_radius = math.sqrt(center_x**2 + center_y**2)
    for step in range(256, 0, -1):
        progress = cubic_bezier(step / 256, 0, 0.2, 0.8, 1.0)
        radius = int(max_radius * progress)
        color = tuple(int(bg_color[i] + (end_color[i] - bg_color[i]) * progress) for i in range(3)) + (255,)
        if radius > 0:
            ImageDraw.Draw(image).ellipse(
                (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                fill=color,
            )
    for _index in range(3):
        image = image.filter(ImageFilter.GaussianBlur(radius=1))

    draw = ImageDraw.Draw(image)
    text_color = (255, 255, 255, 255) if dark_mode else (0, 0, 0, 255)
    outline_color = (0, 0, 0, 255) if dark_mode else (255, 255, 255, 255)
    y = PADDING
    for line in lines:
        if line == '\n':
            y += FONT_SIZE + LINE_SPACING
            continue
        _line_width, line_height = get_line_size(draw, line, font)
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    draw.text((PADDING + dx, y + dy), line, font=font, fill=outline_color)
        draw.text((PADDING, y), line, font=font, fill=text_color)
        y += line_height + LINE_SPACING

    output_path = Path(utils.get_generate_image_dir()) / f'lanota_{uuid.uuid4().hex[:10]}.png'
    image.convert('RGB').save(output_path)
    return str(output_path)


def build_update_report(result: dict[str, Any]) -> str:
    message = '乐曲数据更新完成！\n'
    message += f'原有乐曲: {result.get("before", 0)}首\n'

    missing_songs = result.get('missing_songs', 0)
    missing_updated = result.get('missing_updated', 0)
    missing_results = result.get('missing_results', [])

    message += '\n【缺失信息更新】\n'
    if missing_songs > 0:
        message += f'待更新: {missing_songs}首\n'
        message += f'成功更新: {missing_updated}首\n'
        if missing_results:
            message += '\n详细结果:\n'
            for item in missing_results:
                status = '✓' if item.get('success') else '✗'
                missing_text = ', '.join(str(field) for field in item.get('missing', [])) or '无'
                updated_text = ', '.join(str(field) for field in item.get('updated', [])) or '无'
                message += f'{status} {item.get("title", "")}\n'
                message += f'  缺失: {missing_text}\n'
                message += f'  已更新: {updated_text}\n'
    else:
        message += '✓ 所有歌曲信息完整\n'

    message += '\n【新增乐曲】\n'
    message += f'新增: {result.get("added", 0)}首\n'
    added_titles = result.get('added_titles') or []
    if added_titles:
        message += '\n新增曲目:\n' + '\n'.join(str(title) for title in added_titles[:30])
        if len(added_titles) > 30:
            message += f'\n……共{len(added_titles)}首'
    message += f'\n\n【总计】\n当前总乐曲: {result.get("total", 0)}首'
    return message
