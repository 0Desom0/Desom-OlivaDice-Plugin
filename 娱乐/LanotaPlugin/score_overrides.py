# -*- encoding: utf-8 -*-
"""Lanota Portal 成绩覆盖：手动录入、PaddleOCR 与用户档案。"""

from __future__ import annotations

import base64
import difflib
import html
import importlib.util
import re
import tempfile
import threading
import urllib.parse
from pathlib import Path
from typing import Any

from . import config
from . import function
from . import portal
from . import utils

try:
    import requests
except Exception:  # pragma: no cover - 运行环境可选
    requests = None

_paddle_ocr = None
_paddle_ocr_lock = threading.RLock()

DIFFICULTY_MAP = {
    '0': 0, 'whisper': 0, 'w': 0, '低': 0, '简单': 0,
    '1': 1, 'acoustic': 1, 'a': 1, '中': 1,
    '2': 2, 'ultra': 2, 'u': 2, '高': 2,
    '3': 3, 'master': 3, 'm': 3, '大师': 3,
}
DIFFICULTY_NAMES = ('Whisper', 'Acoustic', 'Ultra', 'Master')
REGION_ALIASES = {
    'global': 'global', 'intl': 'global', 'international': 'global', '国际': 'global', '国际服': 'global',
    'cn': 'china', 'china': 'china', '国服': 'china',
}


def paddleocr_available() -> bool:
    return bool(
        importlib.util.find_spec('paddleocr')
        and importlib.util.find_spec('paddle')
    )


def normalize_region(value: Any) -> str:
    return REGION_ALIASES.get(str(value or '').strip().casefold(), 'global')


def _user_bucket(plugin_event) -> tuple[dict[str, Any], str, str]:
    bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    user_id = utils.get_sender_id_from_event(plugin_event)
    data = function.load_user_data(bot_hash)
    data.setdefault(str(user_id), {})
    return data, str(user_id), bot_hash


def load_overrides(plugin_event, region: str | None = None) -> list[dict[str, Any]]:
    try:
        data, user_id, _bot_hash = _user_bucket(plugin_event)
        storage = data.get(user_id, {}).get('lanota_score_overrides', {})
        if isinstance(storage, list):
            rows = [row for row in storage if isinstance(row, dict)]
        elif isinstance(storage, dict):
            rows = []
            for region_data in storage.values():
                if not isinstance(region_data, dict):
                    continue
                for chapter_data in region_data.values():
                    if not isinstance(chapter_data, dict):
                        continue
                    rows.extend(row for row in chapter_data.values() if isinstance(row, dict))
        else:
            rows = []
        selected = normalize_region(region) if region else None
        return [
            row for row in rows
            if isinstance(row, dict) and (selected is None or normalize_region(row.get('region')) == selected)
        ]
    except Exception:
        return []


def save_overrides(plugin_event, rows: list[dict[str, Any]]) -> bool:
    try:
        data, user_id, bot_hash = _user_bucket(plugin_event)
        storage: dict[str, dict[str, dict[str, Any]]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            region = normalize_region(row.get('region'))
            chapter = str(row.get('chapter') or '').strip()
            difficulty = _difficulty(row.get('difficulty'))
            if not chapter or difficulty is None:
                continue
            storage.setdefault(region, {}).setdefault(chapter, {})[str(difficulty)] = row
        data[user_id]['lanota_score_overrides'] = storage
        return function.save_user_data(data, bot_hash)
    except Exception:
        return False


def _clean_rating_percent(value: Any) -> float | None:
    text = str(value or '').replace(',', '').replace('，', '').replace('％', '%').strip()
    if text.endswith('%'):
        text = text[:-1]
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if 0 < number <= 1:
        number *= 100
    return number if 0 < number <= 100 else None


def _clean_single_rating(value: Any) -> float | None:
    try:
        number = float(str(value or '').replace(',', '.').strip())
    except (TypeError, ValueError):
        return None
    return number if 0 < number <= 30 else None


def _clean_score(value: Any) -> int | None:
    try:
        compact = re.sub(r'\s+', '', str(value))
        number = int(compact.replace(',', '').replace('，', ''))
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 1_000_000 else None


def _difficulty(value: Any) -> int | None:
    text = str(value or '').strip().casefold()
    if text in DIFFICULTY_MAP:
        return DIFFICULTY_MAP[text]
    match = re.search(r'\b(whisper|acoustic|ultra|master)\b', text)
    return DIFFICULTY_MAP.get(match.group(1)) if match else None


def _new_record(
    song: dict[str, Any],
    difficulty: int,
    single_rating: float,
    region: str,
    rating_percent: float | None = None,
    score: int | None = None,
    source: str = 'manual',
) -> dict[str, Any]:
    return {
        'id': f'{region}:{str(song.get("chapter") or "unknown")}:{difficulty}',
        'region': normalize_region(region),
        'chapter': str(song.get('chapter') or '').strip(),
        'song_id': str(song.get('official_songid') or song.get('id') or ''),
        'title': str(song.get('title') or song.get('title_outside') or ''),
        'difficulty': difficulty,
        'difficulty_name': DIFFICULTY_NAMES[difficulty],
        'single_rating': round(float(single_rating), 4),
        'rating_percent': round(float(rating_percent), 4) if rating_percent is not None else None,
        'score': score,
        'source': source,
    }


def _matched_chart_summary(song: dict[str, Any], difficulty: int | None = None) -> str:
    """格式化已匹配的曲目；难度已识别时一并报告。"""
    title = str(song.get('title') or song.get('title_outside') or '未知歌曲').strip()
    chapter = str(song.get('chapter') or '未知').strip()
    details = [f'章节号 {chapter}']
    if isinstance(difficulty, int) and 0 <= difficulty < len(DIFFICULTY_NAMES):
        details.append(f'难度 {DIFFICULTY_NAMES[difficulty]}')
    return f'已匹配：{title}（{"，".join(details)}）'


def _rating_hundredths(value: Any) -> int | None:
    cleaned = _clean_single_rating(value)
    if cleaned is None:
        return None
    return int(cleaned * 100 + 1e-7)


def _evaluate_record_rating(
    single_rating: float,
    score: int | None,
    total: int,
    chart_constant: float,
    source: str,
) -> dict[str, Any] | None:
    """校验录入分数；缺少或无效时仅由两位 Single Rating 近似反推。"""
    from . import b30

    inferred = b30.infer_score_from_single_rating(single_rating, total, chart_constant)
    if inferred is None:
        return None
    score_rating = b30.calculate_score_rating(score, total, chart_constant) if score is not None else None
    result = {
        'score_accuracy': float(inferred['scoreAccuracy']),
        'inferred_score': int(inferred['score']),
        'inferred_accuracy': float(inferred['scoreAccuracy']),
        'score_inferred': score is None,
        'accuracy_inferred': score_rating is None,
        'calculated_single_rating': None,
    }
    if score is None:
        result['validation_status'] = 'manual_inferred' if source == 'manual' else 'missing_score_inferred'
        return result
    if score_rating is None:
        result['validation_status'] = 'invalid_score_format'
        return result

    calculated_rating = float(score_rating['singleRating'])
    result.update({
        'score_accuracy': float(score_rating['scoreAccuracy']),
        'score_inferred': False,
        'accuracy_inferred': False,
        'calculated_single_rating': calculated_rating,
        'validation_status': (
            'score_valid'
            if _rating_hundredths(calculated_rating) == _rating_hundredths(single_rating)
            else 'rating_mismatch'
        ),
    })
    return result


def _chart_values(song: dict[str, Any], difficulty: int) -> tuple[int | None, float | None]:
    difficulty_key = DIFFICULTY_NAMES[difficulty].casefold()
    notes = song.get('notes', {})
    constants = song.get('official_constant', {})
    try:
        total = int(notes.get(difficulty_key)) if isinstance(notes, dict) else None
    except (TypeError, ValueError):
        total = None
    try:
        chart_constant = float(constants.get(difficulty_key)) if isinstance(constants, dict) else None
    except (TypeError, ValueError):
        chart_constant = None
    return total, chart_constant


def _validation_warning(record: dict[str, Any]) -> str:
    status = str(record.get('validation_status') or '')
    accuracy = record.get('score_accuracy')
    accuracy_text = f'{float(accuracy):.2f}%' if accuracy is not None else '未知'
    if status == 'manual_inferred':
        return f'手动录入仅含 Single Rating；当前分数与准度 {accuracy_text} 均为近似反推值'
    if status == 'missing_score_inferred':
        return f'截图未识别到可校验分数；当前分数与准度 {accuracy_text} 由 Single Rating 近似反推'
    if status == 'invalid_score_format':
        return '录入分数无法按 4.0+ 公式校验；按录入 Single Rating 覆盖，准度为近似反推值'
    if status == 'rating_mismatch':
        calculated = record.get('calculated_single_rating')
        calculated_text = f'{float(calculated):.2f}' if calculated is not None else '未知'
        return (
            f'录入分数换算 Single Rating {calculated_text} 与录入值 '
            f'{float(record.get("single_rating", 0)):.2f} 不一致；按录入值覆盖'
        )
    return ''


def _match_song(title: str, songs: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    aliases = function.load_alias_data()
    matched_songs, match_type, _total_count = function.find_song_by_search_term(
        title,
        songs,
        aliases,
        len(songs),
    )
    if not matched_songs:
        return None, 0.0
    best_song = matched_songs[0]
    if match_type != '打分制模糊搜索':
        return best_song, 1.0
    candidates = [str(best_song.get('title') or '')]
    candidates.extend(str(item) for item in aliases.get(str(best_song.get('title') or ''), []) if item)
    best_score = min(function.calculate_search_score(title, candidate) for candidate in candidates)
    return best_song, max(0.0, 1 - best_score / 1000)


def resolve_song(title: str, songs: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any] | None, float]:
    return _match_song(title, songs if isinstance(songs, list) else function.load_song_data())


def parse_manual_argument(argument: str) -> tuple[str, str, int | None, float | None, str]:
    text = str(argument or '').strip()
    region = 'global'
    for token, normalized in REGION_ALIASES.items():
        if re.search(rf'(?<!\S){re.escape(token)}(?!\S)', text, re.IGNORECASE):
            region = normalized
            text = re.sub(rf'(?<!\S){re.escape(token)}(?!\S)', ' ', text, flags=re.IGNORECASE)
    diff_match = re.search(
        r'(?<!\w)(whisper|acoustic|ultra|master|大师|简单|低|中|高|[0-3])(?!\w)',
        text,
        re.IGNORECASE,
    )
    if not diff_match:
        return text.strip(), '', None, None, region
    difficulty = _difficulty(diff_match.group(1))
    number_matches = list(re.finditer(r'(?<![\w.])\d+(?:[.,]\d+)?%?', text))
    single_rating = _clean_single_rating(number_matches[-1].group(0).rstrip('%')) if number_matches else None
    title = text[:diff_match.start()] + text[diff_match.end():]
    if number_matches:
        raw_number = number_matches[-1].group(0)
        title = title.replace(raw_number, ' ')
    title = re.sub(r'(?<![\w])\d{1,3}(?:,\d{3})+(?![\w])', ' ', title)
    return re.sub(r'\s+', ' ', title).strip(), diff_match.group(1), difficulty, single_rating, region


def add_manual(plugin_event, argument: str) -> tuple[bool, str]:
    title, _diff_text, difficulty, single_rating, region = parse_manual_argument(argument)
    if difficulty is None or single_rating is None or not title:
        return False, '用法：/la score <曲名> <难度(master/ultra/acoustic/whisper)> <单曲Rating> [cn|global]'
    song, confidence = resolve_song(title)
    if song is None:
        return False, f'没有匹配到曲名“{title}”，请提供更完整的曲名。'
    record = _new_record(song, difficulty, single_rating, region, source='manual')
    match_summary = _matched_chart_summary(song, difficulty)
    total, chart_constant = _chart_values(song, difficulty)
    if total is None or chart_constant is None:
        return False, f'{match_summary}\n本地缺少该谱面的物量或官方定数，无法反推成绩。'
    evaluation = _evaluate_record_rating(single_rating, None, total, chart_constant, 'manual')
    if evaluation is None:
        return False, (
            f'{match_summary}\n单曲 Rating {single_rating:.2f} '
            '不可能由该谱面的 4.0+ 公式得到，请检查输入。'
        )
    record.update(evaluation)
    record.update({'total': total, 'chart_constant': chart_constant})
    rows = load_overrides(plugin_event)
    rows = [
        row for row in rows
        if not (
            normalize_region(row.get('region')) == record['region']
            and str(row.get('chapter')) == record['chapter']
            and int(row.get('difficulty', -1)) == difficulty
        )
    ]
    rows.append(record)
    if not save_overrides(plugin_event, rows):
        return False, f'{match_summary}\n成绩已解析，但写入玩家档案失败。'
    return True, (
        f'已录入：{record["title"]}\n'
        f'章节号：{record["chapter"]}\n'
        f'区服：{portal.region_display_name(record["region"])}\n'
        f'难度：{record["difficulty_name"]}\n'
        f'单曲 Rating：{record["single_rating"]:.2f}\n'
        f'近似反推分数：{int(record["inferred_score"]):,}\n'
        f'近似反推准度：{float(record["inferred_accuracy"]):.2f}%\n'
        '说明：Single Rating 仅显示两位小数，以上分数和准度取可行区间中值。\n'
        f'曲名匹配度：{confidence:.0%}'
    )


def extract_image_refs(message_text: str) -> list[str]:
    refs = []
    for match in re.finditer(r'\[(?:OP|CQ):image,(?P<params>[^\]]+)\]', str(message_text or ''), re.IGNORECASE):
        params = utils.parse_message_segment_params(match.group('params'))
        value = params.get('url') or params.get('file') or params.get('path')
        if value:
            refs.append(html.unescape(urllib.parse.unquote(value)))
    return refs


def _read_image(ref: str) -> Path | None:
    try:
        if ref.startswith('base64://'):
            encoded = ref.removeprefix('base64://')
            if len(encoded) > config.ocr_image_max_bytes * 4 // 3 + 16:
                return None
            decoded = base64.b64decode(encoded, validate=True)
            temp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            temp.write(decoded)
            temp.close()
            return Path(temp.name)
        if ref.startswith('file://'):
            raw_path = urllib.parse.urlparse(ref).path
            if re.match(r'^/[A-Za-z]:', raw_path):
                raw_path = raw_path.lstrip('/')
            path = Path(urllib.parse.unquote(raw_path))
            return (
                path
                if path.is_file() and path.stat().st_size <= config.ocr_image_max_bytes
                else None
            )
        path = Path(ref)
        if path.is_file() and path.stat().st_size <= config.ocr_image_max_bytes:
            return path
        olivos_file_path = Path('data') / 'files' / ref
        if (
            olivos_file_path.is_file()
            and olivos_file_path.stat().st_size <= config.ocr_image_max_bytes
        ):
            return olivos_file_path
        if ref.startswith(('http://', 'https://')) and requests is not None:
            response = requests.get(ref, timeout=20)
            response.raise_for_status()
            if len(response.content) > config.ocr_image_max_bytes:
                return None
            temp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            temp.write(response.content)
            temp.close()
            return Path(temp.name)
    except Exception:
        return None
    return None


def _prediction_lines(result: Any) -> list[str]:
    lines = []
    for page in result or []:
        data = getattr(page, 'json', None)
        if callable(data):
            data = data()
        if not isinstance(data, dict) and isinstance(page, dict):
            data = page
        if isinstance(data, dict):
            payload = data.get('res', data)
            texts = payload.get('rec_texts', []) if isinstance(payload, dict) else []
            lines.extend(str(item) for item in texts if str(item).strip())
    return lines


def _predict_ocr_text(ocr_input: Any) -> str:
    global _paddle_ocr
    with _paddle_ocr_lock:
        if _paddle_ocr is None:
            from paddleocr import PaddleOCR

            # mobile 模型兼顾手机长截图；Windows CPU 关闭 MKL-DNN 以避开 oneDNN 兼容问题。
            _paddle_ocr = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
                text_detection_model_name='PP-OCRv5_mobile_det',
                text_recognition_model_name='PP-OCRv5_mobile_rec',
            )
        paddle_input = str(ocr_input) if isinstance(ocr_input, (str, Path)) else ocr_input
        return '\n'.join(_prediction_lines(_paddle_ocr.predict(paddle_input)))


def _is_portrait_ocr_candidate(path: Path) -> bool:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.height > image.width
    except Exception:
        return False


def _portal_fast_ocr_input(path: Path) -> Any | None:
    """移除 Portal 纵向页面中无需录入的明细和导航区域，减少 OCR 像素量。"""
    try:
        import numpy as np
        from PIL import Image

        with Image.open(path) as source_image:
            image = np.asarray(source_image.convert('RGB'))
        height, width = image.shape[:2]
        if height <= width:
            return None
        band_ratios = ((0.08, 0.34), (0.34, 0.57), (0.74, 0.91))
        bands = [
            image[int(top * height):int(bottom * height)]
            for top, bottom in band_ratios
        ]
        if any(band.size == 0 for band in bands):
            return None
        return np.concatenate(bands, axis=0)
    except Exception:
        return None


def _looks_like_game_result(text: str) -> bool:
    source = str(text or '')
    if re.search(r'(?i)(?:单曲|single)\s*rating|rating\s*(?:分数|score)', source):
        return False
    if re.search(r'判定详情|高分[记紀記]录刷新|连击比率', source):
        return True
    has_result_score = any(
        re.fullmatch(r'[01]\d{6}', re.sub(r'\s+', '', line))
        for line in source.splitlines()
    )
    return has_result_score and bool(re.search(r'(?i)harmony|rank|重试|继续|purified', source))


def _ocr_has_score(text: str) -> bool:
    return any(
        re.fullmatch(r'[01]\d{6}', re.sub(r'[\s,，]+', '', line))
        for line in str(text or '').splitlines()
    )


def _ocr_has_difficulty_hint(text: str) -> bool:
    for line in str(text or '').splitlines():
        letters = re.sub(r'[^a-z]', '', line.casefold())
        if 2 <= len(letters) <= 10 and letters.startswith('ma'):
            return True
        if any(
            difflib.SequenceMatcher(None, letters, name.casefold()).ratio() >= 0.65
            for name in DIFFICULTY_NAMES
        ):
            return True
    return False


def _ocr_plain_integer(line: str) -> int | None:
    compact = re.sub(r'\s+', '', str(line or '')).translate(str.maketrans({'O': '0', 'o': '0', 'I': '1', 'l': '1'}))
    if not re.fullmatch(r'\d{1,5}', compact):
        return None
    return int(compact)


def _select_judgement_triplet(values: list[int], total: int) -> tuple[int, int, int] | None:
    """从标签前的候选数字中选出物量校验成立的连续 H/T/F。"""
    for index in range(len(values) - 3, -1, -1):
        candidate = tuple(values[index:index + 3])
        if sum(candidate) == total:
            return candidate
    return None


def _needed_game_ocr_sections(text: str) -> tuple[str, ...]:
    """判断完整 OCR 缺哪些字段，只为缺失字段追加裁切推理。"""
    source = str(text or '')
    needed = []
    if not _ocr_has_score(source):
        needed.append('score')
    if not _ocr_has_difficulty_hint(source):
        needed.append('meta')

    labels = [
        bool(re.search(rf'(?i)\b{label}\b', source))
        for label in ('harmony', 'tune', 'fail')
    ]
    if any(labels):
        if not all(labels):
            needed.append('judgements')
        else:
            lines = [re.sub(r'\s+', ' ', line).strip() for line in source.splitlines() if line.strip()]
            first_label = next(
                (
                    index for index, line in enumerate(lines)
                    if re.search(r'(?i)\b(?:harmony|tune|fail)\b', line)
                ),
                len(lines),
            )
            judgement_values = [
                value
                for line in lines[:first_label]
                if (value := _ocr_plain_integer(line)) is not None
            ]
            visible_totals = {
                int(match.group(1))
                for line in lines
                for match in re.finditer(r'\d{1,5}\s*/\s*(\d{1,5})', line)
            }
            has_valid_triplet = any(
                _select_judgement_triplet(judgement_values, total) is not None
                for total in visible_totals
            )
            if (
                len(judgement_values) < 3
                or (visible_totals and not has_valid_triplet)
                or (not visible_totals and len(judgement_values) != 3)
            ):
                needed.append('judgements')
    return tuple(dict.fromkeys(needed))


def _adaptive_game_result_sections(
    path: Path,
    section_names: tuple[str, ...] | None = None,
) -> dict[str, str]:
    """按画面比例放大结算页关键区域，补足小号判定数字的 OCR。"""
    try:
        from PIL import Image, ImageEnhance, ImageFilter

        with Image.open(path) as source_image:
            image = source_image.convert('RGB')
        width, height = image.size
        section_boxes = {
            'meta': (0.02, 0.10, 0.42, 0.52),
            'judgements': (0.20, 0.24, 0.80, 0.66),
            'score': (0.25, 0.58, 0.75, 0.92),
        }
        scale = 2 if width < 2400 else 1
        requested_sections = section_names or ('meta', 'judgements', 'score')
        sections = {}
        with tempfile.TemporaryDirectory(prefix='lanota_ocr_') as temp_dir:
            for section_name in requested_sections:
                ratios = section_boxes[section_name]
                left, top, right, bottom = (
                    int(ratios[0] * width),
                    int(ratios[1] * height),
                    int(ratios[2] * width),
                    int(ratios[3] * height),
                )
                crop = image.crop((left, top, right, bottom))
                if scale > 1:
                    crop = crop.resize((crop.width * scale, crop.height * scale))
                crop = ImageEnhance.Contrast(crop).enhance(1.4).filter(ImageFilter.SHARPEN)
                crop_path = Path(temp_dir) / f'{section_name}.png'
                crop.save(crop_path)
                sections[section_name] = _predict_ocr_text(crop_path)
        return sections
    except Exception as exception_object:
        utils.debug_log(None, f'结算图分区 OCR 失败：{type(exception_object).__name__}: {exception_object}')
        return {}


def _ocr_text(path: Path, force_full_image: bool = False) -> str:
    """使用 PaddleOCR 识别 Portal 或 4.0+ 游戏结算截图。"""
    try:
        fast_input = None if force_full_image else _portal_fast_ocr_input(path)
        full_text = _predict_ocr_text(path if fast_input is None else fast_input)
        if not full_text or not _looks_like_game_result(full_text):
            return full_text
        needed_sections = _needed_game_ocr_sections(full_text)
        if not needed_sections:
            return full_text
        sections = _adaptive_game_result_sections(path, needed_sections)
        parts = ['[[LANOTA_OCR_FULL]]', full_text]
        for section_name in ('meta', 'judgements', 'score'):
            section_text = sections.get(section_name, '')
            if section_text:
                parts.extend([f'[[LANOTA_OCR_{section_name.upper()}]]', section_text])
        return '\n'.join(parts)
    except Exception as exception_object:
        utils.debug_log(None, f'PaddleOCR 识别失败：{type(exception_object).__name__}: {exception_object}')
    return ''


def _split_ocr_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {'full': []}
    current_section = 'full'
    for raw_line in str(text or '').splitlines():
        marker = re.fullmatch(r'\[\[LANOTA_OCR_([A-Z]+)\]\]', raw_line.strip())
        if marker:
            current_section = marker.group(1).casefold()
            sections.setdefault(current_section, [])
            continue
        line = re.sub(r'\s+', ' ', raw_line).strip()
        if line:
            sections.setdefault(current_section, []).append(line)
    return sections


def _ocr_difficulty(lines: list[str]) -> int | None:
    for line in lines:
        direct_match = re.search(r'(?i)\b(whisper|acoustic|ultra|master)\b', line)
        if direct_match:
            return _difficulty(direct_match.group(1))
        letters = re.sub(r'[^a-z]', '', line.casefold())
        if not 2 <= len(letters) <= 10:
            continue
        if letters.startswith('ma'):
            return 3
        best_name = max(DIFFICULTY_NAMES, key=lambda name: difflib.SequenceMatcher(None, letters, name.casefold()).ratio())
        if difflib.SequenceMatcher(None, letters, best_name.casefold()).ratio() >= 0.65:
            return DIFFICULTY_NAMES.index(best_name)
    return None


def _parse_game_result_ocr(
    text: str,
    songs: list[dict[str, Any]],
    region: str,
) -> tuple[dict[str, Any] | None, str]:
    from . import b30

    sections = _split_ocr_sections(text)
    full_lines = sections.get('full', [])
    meta_lines = sections.get('meta', [])
    all_lines = [line for lines in sections.values() for line in lines]
    visible_total_candidates = [
        int(match.group(1))
        for line in all_lines
        for match in re.finditer(r'\d{1,5}\s*/\s*(\d{1,5})', line)
    ]
    title_candidates = []
    for line in [*full_lines, *meta_lines]:
        if re.search(
            r'(?i)harmony|tune|fail|fast|slow|rank|master|ultra|acoustic|whisper|'
            r'判定|重试|继续|高分|连击|purified|\d+\s*/\s*\d+|\d+%',
            line,
        ):
            continue
        if re.fullmatch(r'[\d\s,，.]+', line) or len(line) < 2:
            continue
        title_candidates.append(line)
    song = None
    confidence = 0.0
    best_match_score = 0.0
    for candidate in title_candidates:
        matched_song, matched_confidence = _match_song(candidate, songs)
        if matched_song is None:
            continue
        matched_notes = matched_song.get('notes', {}) if isinstance(matched_song.get('notes'), dict) else {}
        note_values = set()
        for value in matched_notes.values():
            try:
                note_values.add(int(value))
            except (TypeError, ValueError):
                continue
        match_score = matched_confidence + (0.25 if note_values.intersection(visible_total_candidates) else 0.0)
        if match_score > best_match_score:
            song, confidence, best_match_score = matched_song, matched_confidence, match_score
    if song is None:
        return None, f'游戏结算图未能匹配曲名（当前识别：{title_candidates[:3]}），未录入。'

    total_candidates = visible_total_candidates
    notes = song.get('notes', {}) if isinstance(song.get('notes'), dict) else {}
    note_totals = {}
    for difficulty, difficulty_name in enumerate(DIFFICULTY_NAMES):
        try:
            note_totals[difficulty] = int(notes.get(difficulty_name.casefold()))
        except (TypeError, ValueError):
            continue
    matching_totals = [value for value in total_candidates if value in note_totals.values()]
    difficulty = _ocr_difficulty([*meta_lines, *full_lines])
    if matching_totals:
        total = matching_totals[-1]
        total_difficulties = [index for index, notes_value in note_totals.items() if notes_value == total]
        if difficulty is None or note_totals.get(difficulty) != total:
            difficulty = total_difficulties[0] if len(total_difficulties) == 1 else None
    elif difficulty in note_totals:
        total = note_totals[difficulty]
    else:
        return None, (
            f'{_matched_chart_summary(song, difficulty)}\n'
            '游戏结算图缺少与该曲谱面相符的难度或物量，未录入。'
        )
    if difficulty is None:
        return None, (
            f'{_matched_chart_summary(song)}\n'
            '游戏结算图未能可靠确定难度，或该物量对应多个难度，未录入。'
        )

    match_summary = _matched_chart_summary(song, difficulty)

    score_candidates = []
    for line in all_lines:
        compact = re.sub(r'[\s,，]+', '', str(line))
        if re.fullmatch(r'[01]\d{6}', compact):
            score_value = _clean_score(compact)
            if score_value is not None:
                score_candidates.append(score_value)
    if not score_candidates:
        return None, f'{match_summary}\n游戏结算图缺少底部七位分数，未录入。'
    screenshot_score = score_candidates[-1]

    judgement_lines = sections.get('judgements', full_lines)
    normalized_judgement_lines = [re.sub(r'[^a-z]', '', line.casefold()) for line in judgement_lines]
    label_indexes = {
        label: next((index for index, line in enumerate(normalized_judgement_lines) if label in line), None)
        for label in ('harmony', 'tune', 'fail')
    }

    _total, chart_constant = _chart_values(song, difficulty)
    if chart_constant is None:
        return None, f'{match_summary}\n本地缺少该谱面的官方定数，无法校验结算分数，未录入。'
    recognized_label_count = sum(index is not None for index in label_indexes.values())
    harmony = tune = fail = None
    if recognized_label_count:
        if recognized_label_count != 3:
            return None, f'{match_summary}\n游戏结算图的 Harmony/Tune/Fail 标签识别不完整，未录入。'
        first_label_index = min(int(index) for index in label_indexes.values() if index is not None)
        judgement_values = [
            value
            for line in judgement_lines[:first_label_index]
            if (value := _ocr_plain_integer(line)) is not None
        ]
        if len(judgement_values) < 3:
            return None, f'{match_summary}\n游戏结算图未能完整识别 Harmony/Tune/Fail 三项数字，未录入。'
        triplet = _select_judgement_triplet(judgement_values, total)
        harmony, tune, fail = triplet or tuple(judgement_values[-3:])
        if harmony + tune + fail != total:
            return None, (
                f'{match_summary}\n游戏结算图判定合计 {harmony + tune + fail} 与总物量 {total} 不一致，'
                '可能存在 OCR 误识别，未录入。'
            )
        calculated = b30.calculate_judgement_rating(harmony, tune, fail, total, chart_constant)
        validation_status = 'game_judgement_validated'
    else:
        calculated = b30.calculate_score_rating(screenshot_score, total, chart_constant)
        validation_status = 'game_score_validated'
    if calculated is None:
        return None, f'{match_summary}\n截图分数无法按该谱面的 4.0+ 整数公式还原，未录入。'
    calculated_score = int(calculated['score'])
    if calculated_score != screenshot_score:
        return None, (
            f'{match_summary}\n游戏结算图分数校验失败：截图 {screenshot_score:07d}，'
            f'按 H/T/F 应为 {calculated_score:07d}；未录入。'
        )

    record = _new_record(
        song,
        difficulty,
        float(calculated['singleRatingExact']),
        region,
        rating_percent=float(calculated['ratingPercent']),
        score=screenshot_score,
        source='game_ocr',
    )
    record.update({
        'score_accuracy': float(calculated['scoreAccuracy']),
        'validation_status': validation_status,
        'score_inferred': False,
        'accuracy_inferred': False,
        'calculated_single_rating': float(calculated['singleRating']),
        'total': total,
        'chart_constant': chart_constant,
        'title_match_confidence': confidence,
    })
    if harmony is not None and tune is not None and fail is not None:
        record.update({'harmony': harmony, 'tune': tune, 'fail': fail})
    return record, ''


def _parse_ocr(text: str, songs: list[dict[str, Any]], region: str) -> tuple[dict[str, Any] | None, str]:
    if _looks_like_game_result(text) or '[[LANOTA_OCR_' in str(text):
        return _parse_game_result_ocr(text, songs, region)

    lines = [re.sub(r'\s+', ' ', line).strip() for line in str(text).splitlines() if line.strip()]
    difficulty = None
    for line in lines:
        found = re.search(r'(?i)\b(master|ultra|acoustic|whisper)\b', line)
        if found:
            difficulty = _difficulty(found.group(1))
            break
    rating_percent = None
    rating_label_index = next(
        (
            index for index, line in enumerate(lines)
            if re.search(r'(?i)rating\s*(?:分数|score)|(?:分数|score)\s*rating', line)
            and '单曲' not in line
        ),
        None,
    )
    if rating_label_index is not None:
        for line in lines[rating_label_index:rating_label_index + 9]:
            found = re.search(r'(\d{1,3}(?:[.,]\d{1,3})?)\s*%', line)
            if found:
                rating_percent = _clean_rating_percent(found.group(1))
                break

    single_rating = None
    single_label_index = next(
        (
            index for index, line in enumerate(lines)
            if re.search(r'(?i)(?:单曲|single)\s*rating', line)
        ),
        None,
    )
    if single_label_index is not None:
        for line in lines[single_label_index:single_label_index + 4]:
            label_removed = re.sub(r'(?i)(?:单曲|single)\s*rating', ' ', line)
            found = re.search(r'(?<!\d)(\d{1,2}(?:[.,]\d{1,3})?)(?!\d)', label_removed)
            if found:
                single_rating = _clean_single_rating(found.group(1))
                if single_rating is not None:
                    break

    score = None
    for line in lines:
        found = re.fullmatch(r'\s*(\d{1,3}(?:[,，]\s*\d{3})+)\s*', line)
        if found:
            candidate_score = _clean_score(found.group(1))
            if candidate_score is not None and candidate_score >= 100_000:
                score = candidate_score
                break
    title_candidates = []
    for line in lines:
        if re.fullmatch(r'(?i)lanota(?:\s+portal)?|portal', line):
            continue
        if re.search(r'(?i)rank|score|rating|combo|notes|harmony|tune|fail|master|ultra|acoustic|whisper|\d+%|\d{3},\d{3}', line):
            continue
        if re.fullmatch(r'[\d\s,，.]+', line) or len(line) < 2:
            continue
        title_candidates.append(line)
    best = None
    best_conf = 0.0
    for candidate in title_candidates:
        song, confidence = _match_song(candidate, songs)
        if confidence > best_conf:
            best, best_conf = song, confidence
    if best is None:
        return None, (
            'OCR 信息不足（需要曲名、难度和“单曲 RATING”数值；'
            f'当前识别：{title_candidates[:2]}）'
        )
    match_summary = _matched_chart_summary(best, difficulty)
    if difficulty is None or single_rating is None:
        return None, (
            f'{match_summary}\nOCR 信息不足（需要曲名、难度和“单曲 RATING”数值；'
            f'当前识别：{title_candidates[:2]}）'
        )
    record = _new_record(
        best,
        difficulty,
        single_rating,
        region,
        rating_percent=rating_percent,
        score=score,
        source='portal_ocr',
    )
    total, chart_constant = _chart_values(best, difficulty)
    if total is None or chart_constant is None:
        return None, f'{match_summary}\n本地缺少该谱面的物量或官方定数，无法校验录入。'
    evaluation = _evaluate_record_rating(single_rating, score, total, chart_constant, 'portal_ocr')
    if evaluation is None:
        return None, (
            f'{match_summary}\nOCR 的单曲 Rating {single_rating:.2f} '
            '不可能由该谱面的 4.0+ 公式得到。'
        )
    record.update(evaluation)
    record.update({'total': total, 'chart_constant': chart_constant, 'title_match_confidence': best_conf})
    return record, ''


def process_images(plugin_event, message_text: str, region: str = 'global') -> tuple[int, list[str]]:
    refs = extract_image_refs(message_text)
    ignored_count = max(0, len(refs) - config.ocr_max_images_per_message)
    refs = refs[:config.ocr_max_images_per_message]
    songs = function.load_song_data()
    rows = load_overrides(plugin_event)
    messages = []
    added = 0
    for ref in refs:
        path = _read_image(ref)
        if path is None:
            messages.append('图片下载/读取失败')
            continue
        is_downloaded_temp = ref.startswith(('http://', 'https://', 'base64://'))
        try:
            text = _ocr_text(path)
            record, error = _parse_ocr(text, songs, region)
            if record is None and _is_portrait_ocr_candidate(path):
                text = _ocr_text(path, force_full_image=True)
                record, error = _parse_ocr(text, songs, region)
        except Exception as exception_object:
            record = None
            error = f'图片识别失败：{type(exception_object).__name__}: {exception_object}'
        finally:
            if is_downloaded_temp:
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
        if record is None:
            messages.append(error)
            continue
        rows = [
            row for row in rows
            if not (
                normalize_region(row.get('region')) == record['region']
                and str(row.get('chapter')) == record['chapter']
                and int(row.get('difficulty', -1)) == int(record['difficulty'])
            )
        ]
        rows.append(record)
        added += 1
        rating_percent_text = (
            f'\n  Rating%：{record["rating_percent"]:.2f}%'
            if record.get('rating_percent') is not None
            else ''
        )
        if record.get('source') == 'game_ocr':
            if all(record.get(key) is not None for key in ('harmony', 'tune', 'fail')):
                validation_text = (
                    f'  判定：H {record["harmony"]} / T {record["tune"]} / F {record["fail"]}\n'
                    f'  总物量：{record["total"]}\n'
                )
            else:
                validation_text = f'  校验：七位分数符合该谱面物量 {record["total"]} 的 4.0+ 公式\n'
            messages.append(
                f'识别并校验通过：{record["title"]}\n'
                f'  章节号：{record["chapter"]}\n'
                f'  区服：{portal.region_display_name(record["region"])}\n'
                f'  难度：{record["difficulty_name"]}\n'
                f'{validation_text}'
                f'  新版分数：{int(record["score"]):07d}\n'
                f'  分数准度：{float(record["score_accuracy"]):.2f}%\n'
                f'  单曲 Rating：{record["single_rating"]:.2f}{rating_percent_text}'
            )
        else:
            displayed_score = record.get('score')
            score_prefix = ''
            if displayed_score is None:
                displayed_score = record.get('inferred_score')
                score_prefix = '近似反推'
            score_text = (
                f'\n  {score_prefix}分数：{int(displayed_score):,}'
                if displayed_score is not None
                else ''
            )
            warning = _validation_warning(record)
            warning_text = f'\n  提示：{warning}' if warning else ''
            messages.append(
                f'识别结果：{record["title"]}\n'
                f'  章节号：{record["chapter"]}\n'
                f'  区服：{portal.region_display_name(record["region"])}\n'
                f'  难度：{record["difficulty_name"]}'
                f'{score_text}{rating_percent_text}\n'
                f'  单曲 Rating：{record["single_rating"]:.2f}'
                f'{warning_text}'
            )
    if added and not save_overrides(plugin_event, rows):
        messages.insert(0, '识别成功，但写入玩家档案失败；本次结果未保存。')
        added = 0
    if not refs:
        messages.append(
            '未找到图片。Portal 图至少包含曲名、难度和“单曲 RATING”；'
            '4.0+ 结算图须包含曲名、难度、H/T/F、总物量和底部七位分数。'
        )
    elif ignored_count:
        messages.append(f'单条消息最多处理 {config.ocr_max_images_per_message} 张图片，已忽略 {ignored_count} 张。')
    return added, messages


def list_text(plugin_event, region: str | None = None) -> str:
    rows = load_overrides(plugin_event, region)
    if not rows:
        return '当前没有录入成绩。用法：/la score <曲名> <难度> <单曲Rating>，或附带 Portal/游戏结算截图。'
    try:
        from . import b30

        catalog = b30.build_chart_catalog()
    except Exception:
        catalog = {}
    lines = [f'已录入成绩（{portal.region_display_name(region) if region else "全部区服"}）：']
    for index, raw_row in enumerate(rows, 1):
        row = dict(raw_row)
        chart = _find_override_chart(catalog, row)
        if (
            chart is not None
            and chart.get('total') is not None
            and chart.get('chartConstant') is not None
            and not str(row.get('validation_status') or '').startswith('game_')
        ):
            evaluation = _evaluate_record_rating(
                float(row.get('single_rating', 0)),
                _clean_score(row.get('score')),
                int(chart['total']),
                float(chart['chartConstant']),
                str(row.get('source') or 'manual'),
            )
            if evaluation is not None:
                row.update(evaluation)
        display_score = row.get('score')
        approximate = False
        if display_score is None:
            display_score = row.get('inferred_score')
            approximate = display_score is not None
        score_text = f' / {"≈" if approximate else ""}分数 {int(display_score):,}' if display_score is not None else ''
        warning = _validation_warning(row)
        warning_text = f' / {warning}' if warning else ''
        lines.append(
            f'{index}. [{row.get("chapter", "未知章节")}] {row.get("title", "未知")} '
            f'[{row.get("difficulty_name", "未知")}] '
            f'单曲 Rating {float(row.get("single_rating", 0)):.2f} - '
            f'{portal.region_display_name(row.get("region"))}{score_text}{warning_text}'
        )
    lines.append('删除：/la score delete <序号>；清空某区服：/la score delete all [cn|global]')
    return '\n'.join(lines)


def delete(plugin_event, argument: str) -> str:
    text = str(argument or '').strip()
    region = None
    for token, normalized in REGION_ALIASES.items():
        if text.casefold().endswith(f' {token}'):
            region, text = normalized, text[:-(len(token) + 1)].strip()
            break
    rows = load_overrides(plugin_event)
    if not rows:
        return '当前没有录入成绩。'
    indexes = [index for index, row in enumerate(rows) if isinstance(row, dict) and (region is None or normalize_region(row.get('region')) == region)]
    if text.casefold() == 'all':
        for index in reversed(indexes):
            rows.pop(index)
        if not save_overrides(plugin_event, rows):
            return '删除失败：无法写入玩家档案。'
        return f'已删除 {len(indexes)} 条录入成绩。'
    try:
        selected = int(text) - 1
        if selected < 0:
            raise IndexError
        actual = indexes[selected]
    except (ValueError, IndexError):
        return '用法：/la score delete <序号> [cn|global]，序号请先用 /la score list 查看。'
    removed = rows.pop(actual)
    if not save_overrides(plugin_event, rows):
        return '删除失败：无法写入玩家档案。'
    return f'已删除：{removed.get("title", "未知")} [{removed.get("difficulty_name", "未知")}]。'


def _find_override_chart(
    catalog: dict[tuple[str, int], dict[str, Any]],
    override: dict[str, Any],
) -> dict[str, Any] | None:
    difficulty = _difficulty(override.get('difficulty'))
    if difficulty is None:
        return None
    song_id = str(override.get('song_id') or '').strip().casefold()
    if song_id:
        exact = catalog.get((song_id, difficulty))
        if exact is not None:
            return exact
    chapter = str(override.get('chapter') or '').strip().casefold()
    candidates = [
        chart
        for chart in catalog.values()
        if int(chart.get('difficulty', -1)) == difficulty
        and str(chart.get('chapter') or '').strip().casefold() == chapter
    ]
    return next(
        (chart for chart in candidates if str(chart.get('chartSet')) == 'current'),
        candidates[0] if candidates else None,
    )


def merge_into_entries(
    entries: list[dict[str, Any]],
    overrides: list[dict[str, Any]],
    catalog: dict[tuple[str, int], dict[str, Any]],
    region: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """按 Single Rating 比较覆盖成绩并返回新的排序结果。"""
    from . import b30

    normalized_region = normalize_region(region)
    by_key = {(str(item.get('songId', '')).casefold(), int(item.get('difficulty', -1))): item for item in entries}
    remaining = []
    used = 0
    removed = 0
    for override in overrides:
        if normalize_region(override.get('region')) != normalized_region:
            remaining.append(override)
            continue
        difficulty = _difficulty(override.get('difficulty'))
        chart = _find_override_chart(catalog, override)
        if chart is None:
            remaining.append(override)
            continue
        song_id = str(chart.get('songId') or override.get('song_id') or '').strip()
        single_rating = _clean_single_rating(override.get('single_rating'))
        rating_percent = _clean_rating_percent(override.get('rating_percent'))
        score = _clean_score(override.get('score'))
        total = chart.get('total')
        constant = chart.get('chartConstant')
        if single_rating is None or total is None or constant is None:
            remaining.append(override)
            continue
        evaluated_override = dict(override)
        if not str(evaluated_override.get('validation_status') or '').startswith('game_'):
            evaluation = _evaluate_record_rating(
                single_rating,
                score,
                int(total),
                float(constant),
                str(evaluated_override.get('source') or 'manual'),
            )
            if evaluation is None:
                remaining.append(override)
                continue
            evaluated_override.update(evaluation)
        base_rating, max_single_rating = b30.get_rating_constants(float(constant))
        calculated = {
            'scoreAccuracy': float(evaluated_override.get('score_accuracy') or 0.0),
            'baseRating': base_rating,
            'singleRatingExact': single_rating,
            'singleRating': b30.truncate_two(single_rating),
            'ratingPercent': (
                rating_percent
                if rating_percent is not None
                else b30.truncate_two(single_rating / max_single_rating * 100)
            ),
        }
        key = (song_id.casefold(), difficulty)
        current = by_key.get(key)
        current_exact = float(current.get('_singleRatingExact', -1)) if current else -1
        if (
            current is not None
            and not str(current.get('warning', '') or '').strip()
            and current_exact >= single_rating
        ):
            removed += 1
            continue
        source = {'songId': song_id, 'difficulty': difficulty, 'title': chart.get('title', override.get('title'))}
        display_score = score
        if display_score is None:
            display_score = _clean_score(evaluated_override.get('inferred_score'))
        item = b30._base_entry(
            source=source,
            chart=chart,
            score=display_score or 0,
            total=int(total),
            constant=float(constant),
            rating_data=calculated,
            exact=False,
        )
        item.update({
            'override': True,
            'warning': _validation_warning(evaluated_override),
            'overrideStatus': evaluated_override.get('validation_status'),
            'scoreInferred': bool(evaluated_override.get('score_inferred')),
            'accuracyInferred': bool(evaluated_override.get('accuracy_inferred')),
            '_overrideSingleRating': single_rating,
        })
        by_key[key] = item
        used += 1
        remaining.append(override)
    merged = list(by_key.values())
    merged.sort(key=lambda item: (-float(item.get('_singleRatingExact', 0)), -int(item.get('score', 0)), str(item.get('title', '')).casefold()))
    for rank, item in enumerate(merged[:b30.B30_ENTRY_COUNT + b30.OVERFLOW_ENTRY_COUNT], 1):
        item['rank'] = rank
        item['overflow'] = rank > b30.B30_ENTRY_COUNT
    return merged[:b30.B30_ENTRY_COUNT + b30.OVERFLOW_ENTRY_COUNT], remaining, {'used': used, 'removed': removed}


def apply_to_song_scores(
    plugin_event,
    song: dict[str, Any],
    score_rows: list[dict[str, Any]],
    region: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """为 /la info 合并当前歌曲的玩家录入 Single Rating。"""
    from . import b30

    all_overrides = load_overrides(plugin_event)
    if not all_overrides:
        return list(score_rows), {'used': 0, 'removed': 0}
    normalized_region = normalize_region(region)
    current_id = str(song.get('official_songid') or '').strip()
    legacy = song.get('Legacy', {})
    legacy_id = str(legacy.get('official_songid') or '').strip() if isinstance(legacy, dict) else ''
    song_id_map = {
        current_id.casefold(): 'current',
        legacy_id.casefold(): 'legacy',
    }
    song_id_map.pop('', None)
    by_key = {
        (str(row.get('chartSet', 'current')), int(row.get('difficulty', -1))): dict(row)
        for row in score_rows
        if isinstance(row, dict)
    }
    catalog = b30.build_chart_catalog()
    remaining = []
    used = 0
    removed = 0
    for override in all_overrides:
        override_region = normalize_region(override.get('region'))
        song_id = str(override.get('song_id') or '').strip()
        override_chapter = str(override.get('chapter') or '').strip().casefold()
        song_chapter = str(song.get('chapter') or '').strip().casefold()
        chart_set = song_id_map.get(song_id.casefold())
        if chart_set is None and override_chapter == song_chapter:
            chart_set = 'current'
        if override_region != normalized_region or chart_set is None:
            remaining.append(override)
            continue
        difficulty = _difficulty(override.get('difficulty'))
        single_rating = _clean_single_rating(override.get('single_rating'))
        if difficulty is None or single_rating is None:
            remaining.append(override)
            continue
        key = (chart_set, difficulty)
        official = by_key.get(key)
        chart = _find_override_chart(catalog, override)
        official_rating = None
        if official is not None and chart is not None:
            official_rating = b30.calculate_score_rating(
                official.get('score'),
                chart.get('total'),
                chart.get('chartConstant'),
            )
        if (
            official_rating is not None
            and float(official_rating['singleRatingExact']) >= single_rating
        ):
            removed += 1
            continue
        remaining.append(override)
        row = dict(official or {})
        override_score = _clean_score(override.get('score'))
        evaluated_override = dict(override)
        if (
            chart is not None
            and chart.get('total') is not None
            and chart.get('chartConstant') is not None
            and not str(evaluated_override.get('validation_status') or '').startswith('game_')
        ):
            evaluation = _evaluate_record_rating(
                single_rating,
                override_score,
                int(chart.get('total')),
                float(chart.get('chartConstant')),
                str(evaluated_override.get('source') or 'manual'),
            )
            if evaluation is not None:
                evaluated_override.update(evaluation)
        display_score = override_score
        if display_score is None:
            display_score = _clean_score(evaluated_override.get('inferred_score'))
        row.update({
            'chartSet': chart_set,
            'difficulty': difficulty,
            'score': display_score if display_score is not None else row.get('score'),
            'clear': row.get('clear') or '玩家录入',
            'rank': row.get('rank') or '—',
            'singleRating': single_rating,
            'ratingPercent': _clean_rating_percent(override.get('rating_percent')),
            'override': True,
            'scoreAccuracy': evaluated_override.get('score_accuracy'),
            'scoreInferred': bool(evaluated_override.get('score_inferred')),
            'accuracyInferred': bool(evaluated_override.get('accuracy_inferred')),
            'overrideStatus': evaluated_override.get('validation_status'),
            'overrideWarning': _validation_warning(evaluated_override),
        })
        by_key[key] = row
        used += 1
    if removed:
        save_overrides(plugin_event, remaining)
    merged = [
        by_key[key]
        for key in sorted(by_key, key=lambda item: (0 if item[0] == 'current' else 1, item[1]))
    ]
    return merged, {'used': used, 'removed': removed}


def reconcile_official_scores(
    plugin_event,
    catalog: dict[tuple[str, int], dict[str, Any]],
    region: str,
    official_rows: list[dict[str, Any]],
    score_field: str,
) -> int:
    """用完整官网成绩集清理 Single Rating 不高于官网计算结果的录入。"""
    from . import b30

    normalized_region = normalize_region(region)
    official_by_key: dict[tuple[str, int], int] = {}
    for row in official_rows:
        if not isinstance(row, dict):
            continue
        song_id = str(row.get('songId') or '').strip().casefold()
        difficulty = _difficulty(row.get('difficulty'))
        score = _clean_score(row.get(score_field))
        if not song_id or difficulty is None or score is None:
            continue
        key = (song_id, difficulty)
        official_by_key[key] = max(score, official_by_key.get(key, -1))

    overrides = load_overrides(plugin_event)
    remaining = []
    removed = 0
    for override in overrides:
        if normalize_region(override.get('region')) != normalized_region:
            remaining.append(override)
            continue
        chart = _find_override_chart(catalog, override)
        single_rating = _clean_single_rating(override.get('single_rating'))
        if chart is None or single_rating is None:
            remaining.append(override)
            continue
        key = (str(chart.get('songId') or '').strip().casefold(), int(chart.get('difficulty', -1)))
        official_score = official_by_key.get(key)
        calculated = b30.calculate_score_rating(
            official_score,
            chart.get('total'),
            chart.get('chartConstant'),
        )
        if calculated is not None and float(calculated['singleRatingExact']) >= single_rating:
            removed += 1
            continue
        remaining.append(override)
    if removed:
        save_overrides(plugin_event, remaining)
    return removed


def apply_to_card(plugin_event, card_data: dict[str, Any], catalog: dict[tuple[str, int], dict[str, Any]], region: str) -> dict[str, Any]:
    """把玩家档案中的成绩覆盖到一次 B30 查询结果。"""
    try:
        rows = load_overrides(plugin_event)
        if not rows:
            return card_data
        merged, remaining, stats = merge_into_entries(card_data.get('entries', []), rows, catalog, region)
        if stats.get('removed'):
            save_overrides(plugin_event, remaining)
        card_data['entries'] = merged
        best_entries = [item for item in merged if not item.get('overflow')][:30]
        b30_sum = sum(float(item.get('_singleRatingExact', 0.0)) for item in best_entries)
        b30_contribution = b30_sum / 35
        from . import b30
        limits = b30.calculate_player_limits(best_entries, b30_contribution)
        metrics = card_data.setdefault('metrics', {})
        metrics['b30Contribution'] = b30.truncate_two(b30_contribution)
        metrics['maxR5'] = limits['maxR5']
        metrics['maxRating'] = limits['maxRating']
        card_data['overrides'] = stats
        notice = (
            f'已比较玩家录入成绩：采用 {stats["used"]} 条覆盖，删除 {stats["removed"]} 条较低录入。'
            '反推值或校验异常会在对应条目中单独标注。'
        )
        card_data['notice'] = f'{str(card_data.get("notice", "")).strip()} {notice}'.strip()
    except Exception as exception_object:
        utils.debug_log(None, f'应用成绩覆盖失败：{type(exception_object).__name__}: {exception_object}')
    return card_data
