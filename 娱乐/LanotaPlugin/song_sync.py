# -*- encoding: utf-8 -*-
"""Lanota Portal 官方曲库的纯数据归一化、匹配与重排逻辑。"""

from __future__ import annotations

import html
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import unquote, urlparse


DIFFICULTY_NAMES = ("whisper", "acoustic", "ultra", "master")
DIFFICULTY_LABELS = ("Whisper", "Acoustic", "Ultra", "Master")
OFFICIAL_SONG_ID_FIELD = "official_songid"
MEDIAWIKI_TAG_PATTERN = re.compile(r"<[^>]+>")
NOWIKI_TAG_PATTERN = re.compile(r"</?nowiki\b[^>]*>", flags=re.I)
NON_ALNUM_PATTERN = re.compile(r"[^\w]+", flags=re.UNICODE)
CHARACTER_FOLD_MAP = str.maketrans(
    {
        "ı": "i",
        "ø": "o",
        "đ": "d",
        "ð": "d",
        "þ": "th",
        "ł": "l",
        "æ": "ae",
        "œ": "oe",
        "α": "a",
        "Α": "a",
        "λ": "a",
        "Λ": "a",
        "σ": "s",
        "Σ": "s",
        "ς": "s",
        "∀": "a",
    }
)


def next_numeric_song_id(songs: list[dict[str, Any]]) -> int:
    """返回新曲应使用的数字 ID；官方字符串 ID 始终存放在独立字段。"""
    numeric_ids = []
    for song in songs:
        raw_id = str(song.get("id", "") or "").strip()
        if raw_id.isdigit():
            numeric_ids.append(int(raw_id))
    return max(numeric_ids, default=0) + 1


def strip_nowiki_markup(value: Any) -> Any:
    """递归移除 Fandom 残留的 nowiki 标签，保留标签内容和数据结构。"""
    if isinstance(value, dict):
        return {key: strip_nowiki_markup(item) for key, item in value.items()}
    if isinstance(value, list):
        return [strip_nowiki_markup(item) for item in value]
    if isinstance(value, str):
        return NOWIKI_TAG_PATTERN.sub("", value)
    return value


def clean_title_text(value: Any) -> str:
    """去掉 Fandom 标题残留的 HTML/MediaWiki 标记并统一实体。"""
    text = str(strip_nowiki_markup(value or ""))
    for _unused in range(2):
        text = html.unescape(text)
    text = MEDIAWIKI_TAG_PATTERN.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_match_text(value: Any) -> str:
    text = clean_title_text(value).translate(CHARACTER_FOLD_MAP).casefold()
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return NON_ALNUM_PATTERN.sub("", without_marks).replace("_", "")


def _source_title(song: dict[str, Any]) -> str:
    source_url = str(song.get("source_url", "") or "").strip()
    if not source_url:
        return ""
    path = unquote(urlparse(source_url).path)
    if "/wiki/" in path:
        return path.split("/wiki/", 1)[1].replace("_", " ")
    return ""


def local_title_variants(song: dict[str, Any]) -> list[str]:
    variants = []
    for value in (song.get("title"), song.get("title_outside"), _source_title(song)):
        normalized = normalize_match_text(value)
        if normalized and normalized not in variants:
            variants.append(normalized)
        phase_normalized = normalized.replace("1stphase", "1").replace("2ndphase", "2")
        if phase_normalized and phase_normalized not in variants:
            variants.append(phase_normalized)
        without_parenthetical = normalize_match_text(
            re.sub(r"\s*\([^)]*\)\s*$", "", clean_title_text(value))
        )
        if without_parenthetical and without_parenthetical not in variants:
            variants.append(without_parenthetical)
    return variants


def official_title_variants(song: dict[str, Any]) -> list[str]:
    variants = []
    for value in (song.get("title"), song.get("songId")):
        normalized = normalize_match_text(value)
        if normalized and normalized not in variants:
            variants.append(normalized)
    return variants


def validate_official_catalog(official_songs: Any) -> list[dict[str, Any]]:
    if not isinstance(official_songs, list):
        raise ValueError("Portal /songs 响应中的 songs 不是列表。")
    result = []
    seen_ids = set()
    for item in official_songs:
        if not isinstance(item, dict):
            continue
        song_id = str(item.get("songId", "") or "").strip()
        if not song_id:
            raise ValueError("Portal /songs 中存在空 songId。")
        if song_id in seen_ids:
            raise ValueError(f"Portal /songs 中存在重复 songId：{song_id}")
        seen_ids.add(song_id)
        charts = item.get("charts")
        if not isinstance(charts, list):
            raise ValueError(f"Portal 歌曲 {song_id} 缺少 charts。")
        difficulties = {
            int(chart.get("difficulty", -1))
            for chart in charts
            if isinstance(chart, dict)
        }
        if difficulties != set(range(len(DIFFICULTY_NAMES))):
            raise ValueError(
                f"Portal 歌曲 {song_id} 的难度不完整：{sorted(difficulties)}"
            )
        result.append(item)
    return result


def chart_display_level(chart: dict[str, Any]) -> str:
    level = int(chart.get("level", 0))
    fraction = int(chart.get("levelFraction", 0))
    return f"{level}+" if fraction >= 5 else str(level)


def chart_official_constant(chart: dict[str, Any]) -> float:
    level = int(chart.get("level", 0))
    fraction = int(chart.get("levelFraction", 0))
    return float(f"{level}.{fraction}")


def official_song_fields(official_song: dict[str, Any]) -> dict[str, Any]:
    charts = {
        int(chart["difficulty"]): chart
        for chart in official_song.get("charts", [])
        if isinstance(chart, dict) and "difficulty" in chart
    }
    difficulty = {}
    official_constant = {}
    for difficulty_index, difficulty_name in enumerate(DIFFICULTY_NAMES):
        chart = charts[difficulty_index]
        difficulty[difficulty_name] = chart_display_level(chart)
        official_constant[difficulty_name] = chart_official_constant(chart)
    return {
        OFFICIAL_SONG_ID_FIELD: str(official_song.get("songId", "")).strip(),
        "difficulty": difficulty,
        "official_constant": official_constant,
    }


def apply_official_song(
    song: dict[str, Any], official_song: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    result = dict(song)
    changed = []
    for key, value in official_song_fields(official_song).items():
        if result.get(key) != value:
            result[key] = value
            changed.append(key)
    return result, changed


def apply_legacy_official_song(
    song: dict[str, Any], official_song: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """把 Portal 的 Legacy songId、标级和定数写入本地 Legacy 节点。"""
    result = dict(song)
    legacy = dict(song.get("Legacy", {}))
    official_fields = official_song_fields(official_song)
    changed = []
    legacy_fields = {
        OFFICIAL_SONG_ID_FIELD: official_fields[OFFICIAL_SONG_ID_FIELD],
        "official_constant": official_fields["official_constant"],
    }
    for difficulty_name, difficulty_label in zip(
        DIFFICULTY_NAMES, DIFFICULTY_LABELS, strict=True
    ):
        legacy_fields[f"Diff{difficulty_label}"] = official_fields["difficulty"][
            difficulty_name
        ]
    for key, value in legacy_fields.items():
        if legacy.get(key) != value:
            legacy[key] = value
            changed.append(key)
    result["Legacy"] = legacy
    return result, changed


def _title_score(local_song: dict[str, Any], official_song: dict[str, Any]) -> float:
    local_variants = local_title_variants(local_song)
    official_variants = official_title_variants(official_song)
    if not local_variants or not official_variants:
        return 0.0
    return max(
        SequenceMatcher(None, local_variant, official_variant).ratio()
        for local_variant in local_variants
        for official_variant in official_variants
    )


def _artist_score(local_song: dict[str, Any], official_song: dict[str, Any]) -> float:
    local_artist = normalize_match_text(local_song.get("artist"))
    official_artist = normalize_match_text(official_song.get("artist"))
    if not local_artist or not official_artist:
        return 0.0
    return SequenceMatcher(None, local_artist, official_artist).ratio()


def _difficulty_score(
    local_song: dict[str, Any], official_song: dict[str, Any]
) -> float:
    local_difficulty = local_song.get("difficulty")
    if not isinstance(local_difficulty, dict):
        return 0.0
    official_difficulty = official_song_fields(official_song)["difficulty"]
    comparable = [
        difficulty_name
        for difficulty_name in DIFFICULTY_NAMES
        if str(local_difficulty.get(difficulty_name, "") or "").strip()
    ]
    if not comparable:
        return 0.0
    matches = sum(
        str(local_difficulty.get(difficulty_name, "")).strip()
        == official_difficulty[difficulty_name]
        for difficulty_name in comparable
    )
    return matches / len(comparable)


def _candidate_score(
    local_song: dict[str, Any],
    official_song: dict[str, Any],
) -> tuple[float, float, float, float]:
    title_score = _title_score(local_song, official_song)
    artist_score = _artist_score(local_song, official_song)
    difficulty_score = _difficulty_score(local_song, official_song)
    combined_score = title_score * 0.78 + artist_score * 0.07 + difficulty_score * 0.15
    return combined_score, title_score, artist_score, difficulty_score


def _override_song_id(song: dict[str, Any], overrides: dict[str, str]) -> str:
    for key in (song.get("chapter"), song.get("id"), song.get("title")):
        key_text = str(key or "").strip()
        if key_text and key_text in overrides:
            return str(overrides[key_text] or "").strip()
    return ""


def _result_item(
    local_index: int,
    local_song: dict[str, Any],
    official_song: dict[str, Any] | None,
    method: str,
    score: float,
    margin: float,
    confident: bool,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "local_index": local_index,
        "local_id": local_song.get("id"),
        "chapter": str(local_song.get("chapter", "") or ""),
        "title": str(local_song.get("title", "") or ""),
        "song_id": str(official_song.get("songId", "") or "") if official_song else "",
        "official_title": str(official_song.get("title", "") or "")
        if official_song
        else "",
        "method": method,
        "score": round(score, 6),
        "margin": round(margin, 6),
        "confident": confident,
        "official_song": official_song,
        "candidates": candidates or [],
    }


def _is_legacy_official_song(song: dict[str, Any]) -> bool:
    return bool(re.search(r"\s*\(legacy\)\s*$", str(song.get("title", "")), re.I))


def _legacy_official_title(song: dict[str, Any]) -> str:
    return re.sub(
        r"\s*\(legacy\)\s*$",
        "",
        clean_title_text(song.get("title")),
        flags=re.I,
    )


def match_song_catalog(
    local_songs: list[dict[str, Any]],
    official_songs: list[dict[str, Any]],
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """按 ID、标题与曲师逐首匹配，低置信结果只进入 review。"""
    full_official_catalog = validate_official_catalog(official_songs)
    legacy_official_catalog = [
        song for song in full_official_catalog if _is_legacy_official_song(song)
    ]
    official_catalog = [
        song for song in full_official_catalog if not _is_legacy_official_song(song)
    ]
    override_map = {str(key): str(value) for key, value in (overrides or {}).items()}
    official_by_id = {str(song["songId"]): song for song in official_catalog}
    available_ids = set(official_by_id)
    matched_by_index: dict[int, dict[str, Any]] = {}

    def assign(
        index: int,
        official_song: dict[str, Any],
        method: str,
        score: float = 1.0,
        margin: float = 1.0,
    ):
        song_id = str(official_song["songId"])
        if song_id not in available_ids:
            return False
        matched_by_index[index] = _result_item(
            index,
            local_songs[index],
            official_song,
            method,
            score,
            margin,
            True,
        )
        available_ids.remove(song_id)
        return True

    # 已迁移官方 ID 与人工覆盖拥有最高优先级；本地数字 id 永不作为官方 ID 覆盖。
    for index, local_song in enumerate(local_songs):
        current_id = str(local_song.get(OFFICIAL_SONG_ID_FIELD, "") or "").strip()
        override_id = _override_song_id(local_song, override_map)
        if override_id:
            if override_id not in official_by_id:
                raise ValueError(f"人工覆盖指向不存在的 songId：{override_id}")
            if not assign(index, official_by_id[override_id], "manual_override"):
                raise ValueError(f"人工覆盖重复使用 songId：{override_id}")
        elif current_id in official_by_id:
            assign(index, official_by_id[current_id], "song_id")

    # 标准化后标题唯一相等时直接确认。
    progress = True
    while progress:
        progress = False
        title_index: dict[str, list[dict[str, Any]]] = {}
        for song_id in available_ids:
            official_song = official_by_id[song_id]
            title_variant = normalize_match_text(official_song.get("title"))
            title_index.setdefault(title_variant, []).append(official_song)
        for index, local_song in enumerate(local_songs):
            if index in matched_by_index:
                continue
            candidates = []
            for title_variant in local_title_variants(local_song):
                candidates.extend(title_index.get(title_variant, []))
            unique_candidates = {str(item["songId"]): item for item in candidates}
            if len(unique_candidates) == 1:
                official_song = next(iter(unique_candidates.values()))
                if assign(index, official_song, "normalized_title"):
                    progress = True

    # 同名曲通过曲师区分；其余曲目按标题相似度和曲师辅助分逐首分配。
    proposals = []
    for index, local_song in enumerate(local_songs):
        if index in matched_by_index:
            continue
        scored = []
        for song_id in available_ids:
            official_song = official_by_id[song_id]
            combined_score, title_score, artist_score, difficulty_score = (
                _candidate_score(local_song, official_song)
            )
            scored.append(
                (
                    combined_score,
                    title_score,
                    artist_score,
                    difficulty_score,
                    official_song,
                )
            )
        scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        best = scored[0] if scored else (0.0, 0.0, 0.0, 0.0, None)
        (
            best_score,
            best_title_score,
            best_artist_score,
            best_difficulty_score,
            best_song,
        ) = best
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = best_score - second_score
        exact_title = best_title_score == 1.0
        confident = bool(
            best_song
            and (
                (exact_title and best_difficulty_score >= 0.75 and margin >= 0.025)
                or (
                    best_title_score >= 0.70
                    and best_artist_score >= 0.95
                    and margin >= 0.05
                )
                or (best_title_score >= 0.86 and best_score >= 0.86 and margin >= 0.055)
            )
        )
        proposals.append(
            {
                "index": index,
                "song": best_song,
                "score": best_score,
                "title_score": best_title_score,
                "artist_score": best_artist_score,
                "difficulty_score": best_difficulty_score,
                "margin": margin,
                "confident": confident,
                "scored": scored,
            }
        )

    proposals.sort(
        key=lambda item: (item["confident"], item["score"], item["margin"]),
        reverse=True,
    )
    deferred = []
    for proposal in proposals:
        official_song = proposal["song"]
        song_id = str(official_song.get("songId", "") or "") if official_song else ""
        if proposal["confident"] and song_id in available_ids:
            assign(
                proposal["index"],
                official_song,
                "fuzzy_title_artist",
                proposal["score"],
                proposal["margin"],
            )
        else:
            deferred.append(proposal["index"])

    review = []
    for index in deferred:
        if index in matched_by_index:
            continue
        local_song = local_songs[index]
        scored = []
        for song_id in available_ids:
            official_song = official_by_id[song_id]
            combined_score, title_score, artist_score, difficulty_score = (
                _candidate_score(local_song, official_song)
            )
            scored.append(
                (
                    combined_score,
                    title_score,
                    artist_score,
                    difficulty_score,
                    official_song,
                )
            )
        scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        best = scored[0] if scored else (0.0, 0.0, 0.0, 0.0, None)
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        candidates = [
            {
                "songId": str(item[4].get("songId", "")),
                "title": str(item[4].get("title", "")),
                "artist": str(item[4].get("artist", "")),
                "score": round(item[0], 6),
                "title_score": round(item[1], 6),
                "artist_score": round(item[2], 6),
                "difficulty_score": round(item[3], 6),
            }
            for item in scored[:5]
        ]
        review.append(
            _result_item(
                index,
                local_song,
                best[4],
                "review",
                best[0],
                best[0] - second_score,
                False,
                candidates,
            )
        )

    matched = [matched_by_index[index] for index in sorted(matched_by_index)]

    legacy_by_id = {
        str(song["songId"]): song for song in legacy_official_catalog
    }
    available_legacy_ids = set(legacy_by_id)
    legacy_matched = []
    legacy_review = []
    for index, local_song in enumerate(local_songs):
        legacy_data = local_song.get("Legacy", {})
        if not isinstance(legacy_data, dict) or not legacy_data:
            continue
        current_legacy_id = str(
            legacy_data.get(OFFICIAL_SONG_ID_FIELD, "") or ""
        ).strip()
        selected_song = None
        method = ""
        if current_legacy_id in available_legacy_ids:
            selected_song = legacy_by_id[current_legacy_id]
            method = "legacy_song_id"
        else:
            local_variants = set(local_title_variants(local_song))
            exact_candidates = [
                official_song
                for song_id, official_song in legacy_by_id.items()
                if song_id in available_legacy_ids
                and normalize_match_text(_legacy_official_title(official_song))
                in local_variants
            ]
            if len(exact_candidates) == 1:
                selected_song = exact_candidates[0]
                method = "legacy_title"
        if selected_song is not None:
            song_id = str(selected_song["songId"])
            available_legacy_ids.remove(song_id)
            legacy_matched.append(
                _result_item(
                    index,
                    local_song,
                    selected_song,
                    method,
                    1.0,
                    1.0,
                    True,
                )
            )
            continue

        candidates = []
        local_variants = local_title_variants(local_song)
        for song_id in available_legacy_ids:
            official_song = legacy_by_id[song_id]
            official_title = normalize_match_text(_legacy_official_title(official_song))
            title_score = max(
                (
                    SequenceMatcher(None, local_title, official_title).ratio()
                    for local_title in local_variants
                ),
                default=0.0,
            )
            candidates.append(
                {
                    "songId": song_id,
                    "title": str(official_song.get("title", "")),
                    "artist": str(official_song.get("artist", "")),
                    "score": round(title_score, 6),
                }
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        suggested_song = (
            legacy_by_id[candidates[0]["songId"]] if candidates else None
        )
        legacy_review.append(
            _result_item(
                index,
                local_song,
                suggested_song,
                "legacy_review",
                candidates[0]["score"] if candidates else 0.0,
                0.0,
                False,
                candidates[:5],
            )
        )

    unmatched_official_ids = set(available_ids) | set(available_legacy_ids)
    full_official_by_id = {
        str(song["songId"]): song for song in full_official_catalog
    }
    return {
        "matched": matched,
        "review": review,
        "legacy_matched": legacy_matched,
        "legacy_review": legacy_review,
        "unmatched_official": [
            {
                "songId": str(full_official_by_id[song_id].get("songId", "")),
                "title": str(full_official_by_id[song_id].get("title", "")),
                "artist": str(full_official_by_id[song_id].get("artist", "")),
            }
            for song_id in sorted(unmatched_official_ids)
        ],
    }


def apply_catalog_matches(
    local_songs: list[dict[str, Any]],
    official_songs: list[dict[str, Any]],
    match_result: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = [dict(song) for song in local_songs]
    changed_song_indexes = set()
    changed_fields = {
        OFFICIAL_SONG_ID_FIELD: 0,
        "difficulty": 0,
        "official_constant": 0,
        "Legacy.official_songid": 0,
        "Legacy.difficulty": 0,
        "Legacy.official_constant": 0,
    }
    for match in match_result.get("matched", []):
        index = int(match["local_index"])
        updated_song, fields = apply_official_song(
            result[index], match["official_song"]
        )
        result[index] = updated_song
        if fields:
            changed_song_indexes.add(index)
        for field in fields:
            changed_fields[field] = changed_fields.get(field, 0) + 1

    for match in match_result.get("legacy_matched", []):
        index = int(match["local_index"])
        updated_song, fields = apply_legacy_official_song(
            result[index], match["official_song"]
        )
        result[index] = updated_song
        if fields:
            changed_song_indexes.add(index)
        for field in fields:
            if field == OFFICIAL_SONG_ID_FIELD:
                field_name = "Legacy.official_songid"
            elif field == "official_constant":
                field_name = "Legacy.official_constant"
            elif field.startswith("Diff"):
                field_name = "Legacy.difficulty"
            else:
                field_name = f"Legacy.{field}"
            changed_fields[field_name] = changed_fields.get(field_name, 0) + 1

    validate_official_catalog(official_songs)

    def song_order(item: tuple[int, dict[str, Any]]) -> tuple[int, int, str, int]:
        old_index, song = item
        numeric_id = str(song.get("id", "") or "").strip()
        if numeric_id.isdigit():
            return 0, int(numeric_id), "", old_index
        official_id = str(song.get(OFFICIAL_SONG_ID_FIELD, "") or "").strip()
        return 1, 0, official_id.casefold(), old_index

    result = [song for _old_index, song in sorted(enumerate(result), key=song_order)]
    return result, {
        "changed_songs": len(changed_song_indexes),
        "changed_fields": changed_fields,
        "matched": len(match_result.get("matched", [])),
        "review": len(match_result.get("review", [])),
        "legacy_matched": len(match_result.get("legacy_matched", [])),
        "legacy_review": len(match_result.get("legacy_review", [])),
    }


def render_official_constants_markdown(
    official_songs: list[dict[str, Any]], source_url: str
) -> str:
    rows = []
    for song in validate_official_catalog(official_songs):
        for chart in song.get("charts", []):
            difficulty_index = int(chart["difficulty"])
            rows.append(
                {
                    "major": int(chart["level"]),
                    "constant": chart_official_constant(chart),
                    "song_id": str(song["songId"]),
                    "title": clean_title_text(song.get("title")).replace("|", "\\|"),
                    "difficulty": DIFFICULTY_LABELS[difficulty_index],
                }
            )
    rows.sort(
        key=lambda item: (
            -item["constant"],
            item["title"].casefold(),
            -DIFFICULTY_LABELS.index(item["difficulty"]),
        )
    )
    lines = [
        "# Lanota 官方谱面定数",
        "",
        f"> 数据源：`{source_url}`。`level.levelFraction` 按官方接口原值整理。",
        "> 难度显示规则：`levelFraction >= 5` 显示为 `等级+`，官方定数仍保留完整小数。",
        "> `song_list.json` 中的 `official_constant` 即对应四个难度的官方定数。",
        "",
    ]
    current_major = None
    current_constant = None
    for row in rows:
        if row["major"] != current_major:
            current_major = row["major"]
            current_constant = None
            if lines[-1] != "":
                lines.append("")
            lines.extend([f"## Lv.{current_major}", ""])
        if row["constant"] != current_constant:
            current_constant = row["constant"]
            if lines[-1] != "":
                lines.append("")
            lines.extend([f"### {current_constant:.1f}", ""])
        lines.append(f"- {row['title']} - {row['difficulty']} (`{row['song_id']}`)")
    lines.append("")
    return "\n".join(lines)
