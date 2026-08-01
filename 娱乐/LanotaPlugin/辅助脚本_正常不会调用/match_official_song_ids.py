# -*- encoding: utf-8 -*-
"""逐首匹配 Portal songId，并同步官方难度、定数和缺失物量。"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent
REPOSITORY_DIR = PLUGIN_DIR.parents[1]
DEFAULT_SONG_LIST = PLUGIN_DIR / "Data" / "SongList" / "song_list.json"
DEFAULT_RUNTIME_CONFIG = (
    REPOSITORY_DIR / "plugin" / "data" / "LanotaPlugin" / "global_config.json"
)
DEFAULT_CHINA_AUTH = (
    REPOSITORY_DIR / "plugin" / "data" / "LanotaPlugin" / "portal_auth_china.json"
)
DEFAULT_REVIEW = SCRIPT_DIR / "song_id_match_review.json"
DEFAULT_OVERRIDES = SCRIPT_DIR / "song_id_match_overrides.json"
DEFAULT_CONSTANTS_MD = PLUGIN_DIR / "Lanota_官方谱面定数.md"
GLOBAL_API_BASE = "https://noxygames.com/lanota/portal/api"
CHINA_API_BASE = "https://lanota.gmzon.com/portal/api"
FIREBASE_LOGIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)


def load_song_sync_module():
    spec = importlib.util.spec_from_file_location(
        "lanota_song_sync", PLUGIN_DIR / "song_sync.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 song_sync.py。")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


song_sync = load_song_sync_module()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def jwt_exp(token: str) -> int:
    try:
        payload = str(token).split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(
            json.loads(base64.urlsafe_b64decode(payload).decode("utf-8")).get("exp", 0)
        )
    except Exception:
        return 0


class PortalSession:
    def __init__(self, runtime_config_path: Path, china_auth_path: Path):
        self.runtime_config_path = runtime_config_path
        self.china_auth_path = china_auth_path
        self.runtime_config = load_json(runtime_config_path, {})
        self.tokens: dict[str, str] = {}

    def login_global(self) -> str:
        if self.tokens.get("global"):
            return self.tokens["global"]
        email = str(self.runtime_config.get("lanota_portal_email", "") or "").strip()
        password = str(self.runtime_config.get("lanota_portal_password", "") or "")
        api_key = str(
            self.runtime_config.get("lanota_portal_firebase_api_key", "") or ""
        ).strip()
        if not email or not password or not api_key:
            raise RuntimeError(
                f"国际服 Portal 登录配置不完整：{self.runtime_config_path}"
            )
        response = requests.post(
            FIREBASE_LOGIN_URL,
            params={"key": api_key},
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=30,
        )
        response.raise_for_status()
        token = str(response.json().get("idToken", "") or "")
        if not token:
            raise RuntimeError("Firebase 登录响应缺少 idToken。")
        self.tokens["global"] = token
        return token

    def login_china(self) -> str:
        if self.tokens.get("china"):
            return self.tokens["china"]
        auth_data = load_json(self.china_auth_path, {})
        token = str(auth_data.get("china_token", "") or "").strip()
        expires_at = int(auth_data.get("expires_at", 0) or jwt_exp(token))
        if not token or (expires_at and expires_at <= int(time.time()) + 30):
            raise PermissionError(
                f"国服 Portal Token 不存在或已过期：{self.china_auth_path}"
            )
        self.tokens["china"] = token
        return token

    def api_get(
        self, path: str, region: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if region == "china":
            token = self.login_china()
            api_base = CHINA_API_BASE
        else:
            token = self.login_global()
            api_base = GLOBAL_API_BASE
        response = requests.get(
            f"{api_base}/{path.lstrip('/')}",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Portal {region} 返回了非对象 JSON。")
        return data


def fetch_official_catalog(
    portal_session: PortalSession, region: str
) -> tuple[list[dict[str, Any]], list[str]]:
    requested_regions = ["global", "china"] if region == "auto" else [region]
    catalogs: dict[str, list[dict[str, Any]]] = {}
    errors = []
    for requested_region in requested_regions:
        try:
            songs = portal_session.api_get("songs", requested_region).get("songs", [])
            catalog = song_sync.validate_official_catalog(songs)
            catalogs[requested_region] = [
                dict(song, _portal_region=requested_region) for song in catalog
            ]
        except Exception as exception_object:
            errors.append(
                f"{requested_region}: {type(exception_object).__name__}: {exception_object}"
            )
    if not catalogs:
        raise RuntimeError("；".join(errors) or "没有取得任何官方曲库。")

    primary_region = max(catalogs, key=lambda item: len(catalogs[item]))
    merged_by_id = {str(song["songId"]): song for song in catalogs[primary_region]}
    # 重叠歌曲优先用国际服账号，缺少的新歌保留国服来源。
    for requested_region in ("china", "global"):
        for song in catalogs.get(requested_region, []):
            merged_by_id[str(song["songId"])] = song
    merged = sorted(
        merged_by_id.values(), key=lambda song: str(song["songId"]).casefold()
    )
    return merged, errors


def load_official_catalog(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    songs = data.get("songs", []) if isinstance(data, dict) else data
    return [
        dict(song, _portal_region="global")
        for song in song_sync.validate_official_catalog(songs)
    ]


def review_payload(match_result: dict[str, Any]) -> dict[str, Any]:
    review = []
    for item in [
        *match_result.get("review", []),
        *match_result.get("legacy_review", []),
    ]:
        review.append(
            {
                "chart_type": "legacy"
                if item.get("method") == "legacy_review"
                else "current",
                "chapter": item.get("chapter", ""),
                "local_id": item.get("local_id"),
                "title": item.get("title", ""),
                "suggested_song_id": item.get("song_id", ""),
                "score": item.get("score", 0),
                "margin": item.get("margin", 0),
                "candidates": item.get("candidates", []),
                "override_hint": f'在 {DEFAULT_OVERRIDES.name} 中添加 "{item.get("chapter", "")}": "songId"',
            }
        )
    return {
        "matched": len(match_result.get("matched", [])),
        "legacy_matched": len(match_result.get("legacy_matched", [])),
        "needs_review": len(review),
        "review": review,
        "unmatched_official": match_result.get("unmatched_official", []),
    }


def score_total(data: dict[str, Any], difficulty_index: int) -> str:
    for score in data.get("scores", []):
        if (
            not isinstance(score, dict)
            or int(score.get("difficulty", -1)) != difficulty_index
        ):
            continue
        rating_record = score.get("ratingRecord")
        if not isinstance(rating_record, dict):
            return ""
        total = rating_record.get("total")
        return str(total) if total not in [None, ""] else ""
    return ""


def fill_missing_note_totals(
    songs: list[dict[str, Any]],
    official_by_id: dict[str, dict[str, Any]],
    portal_session: PortalSession,
) -> dict[str, int]:
    requested = 0
    filled = 0
    unavailable = 0
    for song in songs:
        official_song = official_by_id.get(
            str(song.get(song_sync.OFFICIAL_SONG_ID_FIELD, ""))
        )
        if not official_song:
            continue
        notes = song.get("notes")
        if not isinstance(notes, dict):
            notes = {}
            song["notes"] = notes
        for difficulty_index, difficulty_name in enumerate(song_sync.DIFFICULTY_NAMES):
            if str(notes.get(difficulty_name, "") or "").strip():
                continue
            requested += 1
            region = str(official_song.get("_portal_region", "global"))
            try:
                detail = portal_session.api_get(
                    "score/song",
                    region,
                    params={
                        "songId": song[song_sync.OFFICIAL_SONG_ID_FIELD],
                        "difficulty": difficulty_index,
                    },
                )
                total = score_total(detail, difficulty_index)
            except Exception:
                total = ""
            if total:
                notes[difficulty_name] = total
                filled += 1
            else:
                notes[difficulty_name] = ""
                unavailable += 1
    return {"requested": requested, "filled": filled, "unavailable": unavailable}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--song-list", type=Path, default=DEFAULT_SONG_LIST)
    parser.add_argument("--portal-config", type=Path, default=DEFAULT_RUNTIME_CONFIG)
    parser.add_argument("--china-auth", type=Path, default=DEFAULT_CHINA_AUTH)
    parser.add_argument("--official-json", type=Path)
    parser.add_argument("--region", choices=["auto", "global", "china"], default="auto")
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--constants-md", type=Path, default=DEFAULT_CONSTANTS_MD)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-note-fallback", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    local_songs = load_json(args.song_list)
    if not isinstance(local_songs, list):
        raise ValueError(f"曲库不是 JSON 列表：{args.song_list}")
    overrides = load_json(args.overrides, {})
    portal_session = PortalSession(args.portal_config, args.china_auth)
    if args.official_json:
        official_songs = load_official_catalog(args.official_json)
        fetch_errors = []
    else:
        official_songs, fetch_errors = fetch_official_catalog(
            portal_session, args.region
        )

    match_result = song_sync.match_song_catalog(local_songs, official_songs, overrides)
    for item in match_result["matched"]:
        print(
            f"[OK] {item['chapter']} {item['title']} -> {item['song_id']} "
            f"({item['method']})"
        )
    for item in match_result["legacy_matched"]:
        print(
            f"[OK LEGACY] {item['chapter']} {item['title']} -> {item['song_id']} "
            f"({item['method']})"
        )
    for item in match_result["review"]:
        print(
            f"[REVIEW] {item['chapter']} {item['title']} -> {item['song_id'] or '无候选'}"
        )
    for item in match_result["legacy_review"]:
        print(
            f"[REVIEW LEGACY] {item['chapter']} {item['title']} -> "
            f"{item['song_id'] or '无候选'}"
        )
    save_json(args.review_output, review_payload(match_result))
    print(
        f"匹配完成：现行谱面 {len(match_result['matched'])}，"
        f"Legacy {len(match_result['legacy_matched'])}，"
        f"待确认 {len(match_result['review']) + len(match_result['legacy_review'])}，"
        f"官方未映射 {len(match_result['unmatched_official'])}。"
    )
    for error in fetch_errors:
        print(f"[WARN] {error}")
    if not args.apply:
        print(f"当前为预览模式；检查报告：{args.review_output}")
        return 0
    if match_result["review"] or match_result["legacy_review"]:
        print(f"存在待确认项目，拒绝写入。请编辑 {args.overrides} 后重试。")
        return 2

    updated_songs, update_stats = song_sync.apply_catalog_matches(
        local_songs, official_songs, match_result
    )
    note_stats = {"requested": 0, "filled": 0, "unavailable": 0}
    if not args.no_note_fallback and not args.official_json:
        official_by_id = {str(song["songId"]): song for song in official_songs}
        note_stats = fill_missing_note_totals(
            updated_songs, official_by_id, portal_session
        )
    save_json(args.song_list, updated_songs)
    source_url = (
        f"{CHINA_API_BASE}/songs"
        if len(official_songs) > 720
        else f"{GLOBAL_API_BASE}/songs"
    )
    args.constants_md.write_text(
        song_sync.render_official_constants_markdown(official_songs, source_url),
        encoding="utf-8",
    )
    print(f"已写入：{args.song_list}")
    print(f"官方字段更新：{json.dumps(update_stats, ensure_ascii=False)}")
    print(f"物量回退：{json.dumps(note_stats, ensure_ascii=False)}")
    print(f"官方定数文档：{args.constants_md}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exception_object:
        print(
            f"执行失败：{type(exception_object).__name__}: {exception_object}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exception_object
