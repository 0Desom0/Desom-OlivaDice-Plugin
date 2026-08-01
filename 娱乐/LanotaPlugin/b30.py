# -*- encoding: utf-8 -*-
"""Lanota B30 数据整理、Rating 推断与曲绘准备。"""

from __future__ import annotations

import datetime
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import crawler
from . import function
from . import utils


DIFFICULTY_NAMES = ('whisper', 'acoustic', 'ultra', 'master')
DIFFICULTY_DISPLAY_NAMES = ('Whisper', 'Acoustic', 'Ultra', 'Master')
B30_ENTRY_COUNT = 30
OVERFLOW_ENTRY_COUNT = 3


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def truncate_two(value: float) -> float:
    """复现 Portal 的两位小数向下截断。"""
    return math.floor(float(value) * 100) / 100


def get_rating_constants(chart_constant: float) -> tuple[float, float]:
    """返回基础 Rating 与满分 Single Rating。"""
    constant = float(chart_constant)
    if constant <= 15:
        return constant, constant + 1.5
    return 1.5 * constant - 7.5, 1.5 * constant - 6


def _calculate_ex_rating(ex_score: int, total: int, chart_constant: float) -> dict[str, float | int]:
    max_ex_score = 2 * total
    accuracy = ex_score / max_ex_score
    base_rating, max_single_rating = get_rating_constants(chart_constant)
    if accuracy < 0.90:
        single_rating = (base_rating + 1) * accuracy
    elif accuracy < 0.95:
        single_rating = (base_rating + 7) * accuracy - 5.40
    elif accuracy < 0.98:
        single_rating = (base_rating + 4) * accuracy - 2.55
    elif accuracy < 0.99:
        single_rating = (base_rating + 6) * accuracy - 4.51
    else:
        single_rating = (base_rating + 7) * accuracy - 5.50
    single_rating = max(0.0, single_rating)
    rating_percent = single_rating / max_single_rating * 100
    return {
        'exScore': ex_score,
        'maxExScore': max_ex_score,
        'score': 1_000_000 * ex_score // max_ex_score,
        'accuracyExact': accuracy,
        'scoreAccuracy': truncate_two(accuracy * 100),
        'baseRating': base_rating,
        'maxSingleRating': max_single_rating,
        'singleRatingExact': single_rating,
        'singleRating': truncate_two(single_rating),
        'ratingPercentExact': rating_percent,
        'ratingPercent': truncate_two(rating_percent),
    }


def calculate_score_rating(score: int, total: int, chart_constant: float) -> dict[str, float | int] | None:
    """由新版整数分数、物量和定数恢复准度与 Single Rating。"""
    score_value = _safe_int(score)
    total_value = _safe_int(total)
    constant_value = _safe_float(chart_constant)
    if (
        score_value is None
        or total_value is None
        or constant_value is None
        or not 0 <= score_value <= 1_000_000
        or total_value <= 0
        or constant_value <= 0
    ):
        return None

    max_ex_score = 2 * total_value
    ex_score = (max_ex_score * score_value + 999_999) // 1_000_000
    if 1_000_000 * ex_score // max_ex_score != score_value:
        return None

    return _calculate_ex_rating(ex_score, total_value, constant_value)


def calculate_judgement_rating(
    harmony: int,
    tune: int,
    fail: int,
    total: int,
    chart_constant: float,
) -> dict[str, float | int] | None:
    """由 H/T/F 计算新版分数和 Rating；未填满物量的判定自动计入 Fail。"""
    values = [_safe_int(value) for value in (harmony, tune, fail, total)]
    constant = _safe_float(chart_constant)
    if any(value is None or value < 0 for value in values) or constant is None or constant <= 0:
        return None
    harmony_value, tune_value, fail_value, total_value = values
    if total_value <= 0 or harmony_value + tune_value + fail_value > total_value:
        return None
    adjustment = total_value - (harmony_value + tune_value + fail_value)
    adjusted_fail = fail_value + adjustment
    result = _calculate_ex_rating(2 * harmony_value + tune_value, total_value, constant)
    result.update({
        'harmony': harmony_value,
        'tune': tune_value,
        'fail': adjusted_fail,
        'inputFail': fail_value,
        'adjustment': adjustment,
        'total': total_value,
        'chartConstant': constant,
    })
    return result


def _chart_constant_from_api(entry: dict[str, Any]) -> float | None:
    level = _safe_float(entry.get('level'))
    fraction = _safe_int(entry.get('levelFraction'))
    if level is None:
        return None
    return level + (fraction or 0) / 10


def _chart_from_song(
    song: dict[str, Any],
    difficulty_index: int,
    table_data: dict[str, Any],
    *,
    chart_set: str,
) -> dict[str, Any] | None:
    difficulty_key = DIFFICULTY_NAMES[difficulty_index]
    difficulty_name = DIFFICULTY_DISPLAY_NAMES[difficulty_index]
    chapter = str(song.get('chapter', '') or '').strip()
    if chart_set == 'legacy':
        legacy = song.get('Legacy', {})
        if not isinstance(legacy, dict):
            return None
        song_id = str(legacy.get('official_songid', '') or '').strip()
        level_text = str(legacy.get(f'Diff{difficulty_name}', '') or '').strip()
        total = _safe_int(legacy.get(f'Max{difficulty_name}'))
        constant_map = legacy.get('official_constant', {})
        constant = _safe_float(constant_map.get(difficulty_key)) if isinstance(constant_map, dict) else None
        folk_constant = None
    else:
        song_id = str(song.get('official_songid', '') or '').strip()
        difficulty_map = song.get('difficulty', {})
        notes_map = song.get('notes', {})
        constant_map = song.get('official_constant', {})
        level_text = str(difficulty_map.get(difficulty_key, '') or '').strip() if isinstance(difficulty_map, dict) else ''
        total = _safe_int(notes_map.get(difficulty_key)) if isinstance(notes_map, dict) else None
        constant = _safe_float(constant_map.get(difficulty_key)) if isinstance(constant_map, dict) else None
        chapter_constants = table_data.get(chapter, {})
        folk_constant = (
            chapter_constants.get(difficulty_name)
            if isinstance(chapter_constants, dict)
            else None
        )
    if not song_id:
        return None
    constant_text = function.format_compact_chart_constant(constant, folk_constant, level_text)
    return {
        'songId': song_id,
        'title': str(song.get('title') or song.get('title_outside') or song_id),
        'chapter': chapter,
        'difficulty': difficulty_index,
        'difficultyName': difficulty_name,
        'level': level_text,
        'chartConstant': constant,
        'constantText': constant_text,
        'total': total,
        'chartSet': chart_set,
        '_sourceSong': song,
    }


def build_chart_catalog(
    song_data: list[dict[str, Any]] | None = None,
    table_data: dict[str, Any] | None = None,
) -> dict[tuple[str, int], dict[str, Any]]:
    """把当前谱面和 Legacy 谱面整理成可按官方 songId 查询的表。"""
    songs = song_data if isinstance(song_data, list) else function.load_song_data()
    constants = table_data if isinstance(table_data, dict) else function.load_table_data()
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for song in songs:
        if not isinstance(song, dict):
            continue
        for chart_set in ('current', 'legacy'):
            for difficulty_index in range(len(DIFFICULTY_NAMES)):
                chart = _chart_from_song(
                    song,
                    difficulty_index,
                    constants,
                    chart_set=chart_set,
                )
                if chart is None:
                    continue
                key = (str(chart['songId']).casefold(), difficulty_index)
                result.setdefault(key, chart)
    return result


def _fallback_constant_text(constant: float | None) -> str:
    if constant is None:
        return '未知'
    return function.format_table_constant(constant)


def _base_entry(
    *,
    source: dict[str, Any],
    chart: dict[str, Any] | None,
    score: int,
    total: int,
    constant: float,
    rating_data: dict[str, float | int],
    exact: bool,
) -> dict[str, Any]:
    difficulty_index = _safe_int(source.get('difficulty')) or 0
    difficulty_name = (
        chart.get('difficultyName')
        if chart
        else DIFFICULTY_DISPLAY_NAMES[max(0, min(3, difficulty_index))]
    )
    return {
        'songId': str(source.get('songId', '') or ''),
        'title': str((chart or {}).get('title') or source.get('title') or source.get('songId') or 'Unknown Song'),
        'chapter': str((chart or {}).get('chapter') or ''),
        'difficulty': difficulty_index,
        'difficultyName': difficulty_name,
        'constantText': str((chart or {}).get('constantText') or _fallback_constant_text(constant)),
        'chartConstant': constant,
        'total': total,
        'score': score,
        'scoreAccuracy': rating_data['scoreAccuracy'],
        'baseRating': rating_data['baseRating'],
        'singleRating': rating_data['singleRating'],
        'ratingPercent': rating_data['ratingPercent'],
        'exact': exact,
        'warning': '',
        'coverUrl': '',
        '_singleRatingExact': rating_data['singleRatingExact'],
        '_sourceSong': (chart or {}).get('_sourceSong'),
    }


def _score_lookup(scores_data: dict[str, Any] | None) -> dict[tuple[str, int], int]:
    result = {}
    rows = scores_data.get('songs', []) if isinstance(scores_data, dict) else []
    for row in rows:
        if not isinstance(row, dict) or row.get('score') is None:
            continue
        difficulty = _safe_int(row.get('difficulty'))
        score = _safe_int(row.get('score'))
        song_id = str(row.get('songId', '') or '').strip().casefold()
        if song_id and difficulty is not None and score is not None:
            result[(song_id, difficulty)] = score
    return result


def _build_score_overflow_entries(
    scores_data: dict[str, Any] | None,
    catalog: dict[tuple[str, int], dict[str, Any]],
    excluded_keys: set[tuple[str, int]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """从当前账号的全谱面最高分中推断 B31-B33。"""
    selected_rows: dict[tuple[str, int], dict[str, Any]] = {}
    rows = scores_data.get('songs', []) if isinstance(scores_data, dict) else []
    for row in rows:
        if not isinstance(row, dict) or row.get('score') is None:
            continue
        song_id = str(row.get('songId', '') or '').strip().casefold()
        difficulty = _safe_int(row.get('difficulty'))
        score = _safe_int(row.get('score'))
        if not song_id or difficulty is None or score is None:
            continue
        key = (song_id, difficulty)
        if key in excluded_keys:
            continue
        previous = selected_rows.get(key)
        if previous is None or int(previous.get('score', -1)) < score:
            selected_rows[key] = row

    result = []
    invalid_count = 0
    unmapped_count = 0
    for key, source in selected_rows.items():
        chart = catalog.get(key)
        if chart is None:
            unmapped_count += 1
            continue
        score = _safe_int(source.get('score'))
        total = _safe_int(chart.get('total'))
        constant = _safe_float(chart.get('chartConstant'))
        calculated = (
            calculate_score_rating(score, total, constant)
            if score is not None and total is not None and constant is not None
            else None
        )
        if calculated is None:
            invalid_count += 1
            continue
        item = _base_entry(
            source=source,
            chart=chart,
            score=score,
            total=total,
            constant=constant,
            rating_data=calculated,
            exact=False,
        )
        item['overflow'] = True
        result.append(item)

    result.sort(
        key=lambda item: (
            -float(item['_singleRatingExact']),
            -int(item['score']),
            str(item['title']).casefold(),
            int(item['difficulty']),
        )
    )
    result = result[:OVERFLOW_ENTRY_COUNT]
    for rank, item in enumerate(result, B30_ENTRY_COUNT + 1):
        item['rank'] = rank
    return result, {
        'valid': len(result),
        'invalid': invalid_count,
        'unmapped': unmapped_count,
    }


def build_exact_entries(
    rating_data: dict[str, Any],
    scores_data: dict[str, Any] | None,
    catalog: dict[tuple[str, int], dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """使用 /rating 生成准确 B30，并从 /scores 推断 B31-B33。"""
    current_scores = _score_lookup(scores_data)
    entries = rating_data.get('best30', {}).get('entries', [])
    result = []
    best_keys: set[tuple[str, int]] = set()
    invalid_count = 0
    mismatch_count = 0
    for source_rank, source in enumerate(entries[:B30_ENTRY_COUNT], 1):
        if not isinstance(source, dict):
            invalid_count += 1
            continue
        difficulty = _safe_int(source.get('difficulty'))
        song_id = str(source.get('songId', '') or '').strip()
        total = _safe_int(source.get('total'))
        ex_score = _safe_int(source.get('exScore'))
        max_ex_score = _safe_int(source.get('maxExScore'))
        constant = _chart_constant_from_api(source)
        key = (song_id.casefold(), difficulty) if song_id and difficulty is not None else None
        if key is not None:
            best_keys.add(key)
        if (
            difficulty is None
            or not song_id
            or total is None
            or total <= 0
            or ex_score is None
            or max_ex_score is None
            or max_ex_score <= 0
            or constant is None
        ):
            invalid_count += 1
            continue
        score = 1_000_000 * ex_score // max_ex_score
        calculated = calculate_score_rating(score, total, constant)
        if calculated is None:
            invalid_count += 1
            continue
        api_accuracy = _safe_float(source.get('exScoreRate'))
        api_single_rating = _safe_float(source.get('singleRating'))
        api_rating_percent = _safe_float(source.get('ratingPercent'))
        if api_accuracy is not None:
            calculated['scoreAccuracy'] = api_accuracy
        if api_single_rating is not None:
            calculated['singleRating'] = api_single_rating
        if api_rating_percent is not None:
            calculated['ratingPercent'] = api_rating_percent

        chart = catalog.get((song_id.casefold(), difficulty))
        item = _base_entry(
            source=source,
            chart=chart,
            score=score,
            total=total,
            constant=constant,
            rating_data=calculated,
            exact=True,
        )
        item['rank'] = source_rank
        item['overflow'] = False
        harmony = _safe_int(source.get('harmony'))
        tune = _safe_int(source.get('tune'))
        fail = _safe_int(source.get('fail'))
        record_consistent = (
            max_ex_score == 2 * total
            and harmony is not None
            and tune is not None
            and fail is not None
            and harmony + tune + fail == total
            and 2 * harmony + tune == ex_score
        )
        current_score = current_scores.get(key)
        if current_score is not None and current_score != score:
            item['warning'] = f'B30 记录与当前最高分 {current_score:,} 不一致'
            item['currentHighestScore'] = current_score
            mismatch_count += 1
        elif not record_consistent:
            item['warning'] = 'B30 判定记录内部不一致'
            mismatch_count += 1
        result.append(item)

    overflow_entries, overflow_validation = _build_score_overflow_entries(
        scores_data,
        catalog,
        best_keys,
    )
    result.extend(overflow_entries)
    return result, {
        'invalid': invalid_count,
        'mismatch': mismatch_count,
        'overflow': overflow_validation['valid'],
        'overflowInvalid': overflow_validation['invalid'],
        'overflowUnmapped': overflow_validation['unmapped'],
    }


def build_inferred_entries(
    compare_data: dict[str, Any],
    catalog: dict[tuple[str, int], dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """使用 /compare 的公开最高分推断 B30 与 B31-B33。"""
    selected_rows: dict[tuple[str, int], dict[str, Any]] = {}
    played_count = 0
    for row in compare_data.get('songs', []):
        if not isinstance(row, dict) or row.get('friendScore') is None:
            continue
        played_count += 1
        song_id = str(row.get('songId', '') or '').strip().casefold()
        difficulty = _safe_int(row.get('difficulty'))
        score = _safe_int(row.get('friendScore'))
        if not song_id or difficulty is None or score is None:
            continue
        key = (song_id, difficulty)
        previous = selected_rows.get(key)
        if previous is None or int(previous.get('friendScore', -1)) < score:
            selected_rows[key] = row

    result = []
    invalid_count = 0
    unmapped_count = 0
    for key, source in selected_rows.items():
        chart = catalog.get(key)
        if chart is None:
            unmapped_count += 1
            continue
        score = _safe_int(source.get('friendScore'))
        total = _safe_int(chart.get('total'))
        constant = _safe_float(chart.get('chartConstant'))
        calculated = (
            calculate_score_rating(score, total, constant)
            if score is not None and total is not None and constant is not None
            else None
        )
        if calculated is None:
            invalid_count += 1
            continue
        item = _base_entry(
            source=source,
            chart=chart,
            score=score,
            total=total,
            constant=constant,
            rating_data=calculated,
            exact=False,
        )
        result.append(item)

    result.sort(
        key=lambda item: (
            -float(item['_singleRatingExact']),
            -int(item['score']),
            str(item['title']).casefold(),
            int(item['difficulty']),
        )
    )
    result = result[: B30_ENTRY_COUNT + OVERFLOW_ENTRY_COUNT]
    for rank, item in enumerate(result, 1):
        item['rank'] = rank
        item['overflow'] = rank > B30_ENTRY_COUNT
    return result, {
        'played': played_count,
        'valid': len(result),
        'invalid': invalid_count,
        'unmapped': unmapped_count,
    }


def calculate_player_limits(
    entries: list[dict[str, Any]],
    b30_contribution: float | None = None,
) -> dict[str, float]:
    """计算当前玩家用 B1 连续填满五次 Recent 时的 Rating 上限。"""
    b1_single_rating = max(
        (
            _safe_float(item.get('_singleRatingExact'))
            or _safe_float(item.get('singleRating'))
            or 0.0
        )
        for item in entries
    ) if entries else 0.0
    if b30_contribution is None:
        b30_sum = sum(
            _safe_float(item.get('_singleRatingExact'))
            or _safe_float(item.get('singleRating'))
            or 0.0
            for item in entries[:B30_ENTRY_COUNT]
        )
        b30_contribution = b30_sum / 35
    max_r5_exact = 5 * b1_single_rating / 35
    return {
        'b1SingleRating': truncate_two(b1_single_rating),
        'maxR5Exact': max_r5_exact,
        'maxR5': truncate_two(max_r5_exact),
        'maxRating': truncate_two(float(b30_contribution) + max_r5_exact),
    }


def _player_data(source: dict[str, Any]) -> dict[str, Any]:
    return {
        'username': source.get('username') or 'Unknown Player',
        'rating': _safe_float(source.get('rating')) or 0.0,
        'avatarId': source.get('avatarId') or 'av_default',
    }


def build_exact_card_data(
    rating_data: dict[str, Any],
    scores_data: dict[str, Any] | None,
    catalog: dict[tuple[str, int], dict[str, Any]],
    region: str,
) -> dict[str, Any]:
    entries, validation = build_exact_entries(rating_data, scores_data, catalog)
    player = _player_data(rating_data.get('player', {}))
    best30 = rating_data.get('best30', {})
    recent = rating_data.get('recent', {})
    best_entries = [item for item in entries if not item.get('overflow')][:B30_ENTRY_COUNT]
    b30_contribution = _safe_float(best30.get('calculatedRating'))
    calculated_b30_contribution = sum(float(item['_singleRatingExact']) for item in best_entries) / 35
    if b30_contribution is None:
        b30_contribution = calculated_b30_contribution
    limits = calculate_player_limits(best_entries, calculated_b30_contribution)
    notices = []
    if validation['mismatch']:
        notices.append(f'B30 中有 {validation["mismatch"]} 条分数记录与当前成绩不一致，已用警示色标记。')
    if validation['invalid']:
        notices.append(f'另有 {validation["invalid"]} 条 B30 记录字段不完整，未显示。')
    if validation['overflow']:
        notices.append('B31-B33 由完整最高分、当前谱面定数与新版公式推断。')
    if validation['overflow'] < OVERFLOW_ENTRY_COUNT:
        notices.append(f'当前只能推断 {validation["overflow"]} 条 Overflow 记录。')
    return {
        '_portal_region': region,
        'accurate': True,
        'player': player,
        'entries': entries,
        'metrics': {
            'currentRating': player['rating'],
            'possibleR5': _safe_float(recent.get('calculatedRating')) or 0.0,
            'maxR5': limits['maxR5'],
            'maxRating': limits['maxRating'],
            'b30Contribution': truncate_two(b30_contribution),
        },
        'notice': ' '.join(notices),
        'generatedAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'validation': validation,
    }


def build_inferred_card_data(
    compare_data: dict[str, Any],
    catalog: dict[tuple[str, int], dict[str, Any]],
    region: str,
) -> dict[str, Any]:
    entries, validation = build_inferred_entries(compare_data, catalog)
    player = _player_data(compare_data.get('friend', {}))
    b30_sum = sum(float(item['_singleRatingExact']) for item in entries[:B30_ENTRY_COUNT])
    b30_contribution = b30_sum / 35
    limits = calculate_player_limits(entries, b30_contribution)
    possible_r5 = max(0.0, min(limits['maxR5Exact'], player['rating'] - b30_contribution))
    notice_parts = ['4.0以前旧版本成绩无法查询真实 B30 与判定明细；请重新游玩歌曲获得更准确的结果。']
    if validation['invalid']:
        notice_parts.append(f'已略过 {validation["invalid"]} 条无法按新版公式还原的成绩。')
    if validation['unmapped']:
        notice_parts.append(f'另有 {validation["unmapped"]} 条成绩缺少本地谱面数据。')
    return {
        '_portal_region': region,
        'accurate': False,
        'player': player,
        'entries': entries,
        'metrics': {
            'currentRating': player['rating'],
            'possibleR5': truncate_two(possible_r5),
            'maxR5': limits['maxR5'],
            'maxRating': limits['maxRating'],
            'b30Contribution': truncate_two(b30_contribution),
        },
        'notice': ' '.join(notice_parts),
        'generatedAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'validation': validation,
    }


def attach_cover_urls(card_data: dict[str, Any], max_workers: int = 6) -> dict[str, Any]:
    """按 /la song 相同方式获取第一张曲绘，并转换为浏览器可读 URI。"""
    entries = card_data.get('entries', [])
    source_map: dict[str, dict[str, Any]] = {}
    for item in entries:
        source_song = item.get('_sourceSong')
        if not isinstance(source_song, dict):
            continue
        source_key = str(source_song.get('chapter') or source_song.get('id') or id(source_song))
        source_map.setdefault(source_key, source_song)

    cover_url_map = {}

    def load_cover(source_key: str, song: dict[str, Any]) -> tuple[str, str]:
        try:
            cover_path = crawler.ensure_song_cover(song)
            if cover_path and Path(cover_path).is_file():
                return source_key, Path(cover_path).resolve().as_uri()
        except Exception as exception_object:
            utils.debug_log(None, f'B30 曲绘获取失败：{type(exception_object).__name__}: {exception_object}')
        return source_key, ''

    if source_map:
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(source_map)))) as executor:
            future_map = {
                executor.submit(load_cover, source_key, song): source_key
                for source_key, song in source_map.items()
            }
            for future in as_completed(future_map):
                source_key, cover_url = future.result()
                cover_url_map[source_key] = cover_url

    for item in entries:
        source_song = item.pop('_sourceSong', None)
        if isinstance(source_song, dict):
            source_key = str(source_song.get('chapter') or source_song.get('id') or id(source_song))
            item['coverUrl'] = cover_url_map.get(source_key, '')
        item.pop('_singleRatingExact', None)
    return card_data


def strip_internal_fields(card_data: dict[str, Any]) -> dict[str, Any]:
    for item in card_data.get('entries', []):
        item.pop('_sourceSong', None)
        item.pop('_singleRatingExact', None)
    return card_data


def build_fallback_text(card_data: dict[str, Any]) -> str:
    player = card_data.get('player', {})
    metrics = card_data.get('metrics', {})
    mode_name = '准确 B30' if card_data.get('accurate') else '推断 B30'
    lines = [
        f'{player.get("username") or "Unknown Player"} · {mode_name}',
        f'当前 Rating：{float(metrics.get("currentRating", 0)):.2f}',
        f'{"当前" if card_data.get("accurate") else "可能"} R5：{float(metrics.get("possibleR5", 0)):.2f}',
        f'最高 R5：{float(metrics.get("maxR5", 0)):.2f}',
        f'可达最高 Rating：{float(metrics.get("maxRating", 0)):.2f}',
        f'已生成条目：{len(card_data.get("entries", []))}',
    ]
    if card_data.get('notice'):
        lines.extend(['', str(card_data['notice'])])
    return '\n'.join(lines)
