# -*- encoding: utf-8 -*-
"""song_sync.py 的纯离线回归测试。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "lanota_song_sync_test_target", PLUGIN_DIR / "song_sync.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("无法加载 song_sync.py。")
song_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(song_sync)


def official_song(song_id: str, title: str, levels, artist: str = "Artist"):
    return {
        "songId": song_id,
        "title": title,
        "artist": artist,
        "charts": [
            {"difficulty": index, "level": level, "levelFraction": fraction}
            for index, (level, fraction) in enumerate(levels)
        ],
    }


class SongSyncTest(unittest.TestCase):
    def test_official_fields_use_fraction_for_plus_and_constant(self):
        song = official_song(
            "sample",
            "Sample",
            [(3, 0), (9, 0), (13, 5), (15, 3)],
        )
        fields = song_sync.official_song_fields(song)
        self.assertEqual(fields["official_songid"], "sample")
        self.assertEqual(fields["difficulty"]["ultra"], "13+")
        self.assertEqual(fields["difficulty"]["master"], "15")
        self.assertEqual(fields["official_constant"]["ultra"], 13.5)
        self.assertEqual(fields["official_constant"]["master"], 15.3)

    def test_same_title_legacy_pair_is_selected_by_difficulty(self):
        local = [
            {
                "id": 1,
                "title": "Same Song",
                "artist": "Artist",
                "chapter": "1-1",
                "difficulty": {
                    "whisper": "3",
                    "acoustic": "7",
                    "ultra": "11",
                    "master": "13+",
                },
            }
        ]
        catalog = [
            official_song(
                "samesong", "Same Song (Legacy)", [(2, 0), (5, 0), (9, 0), (12, 0)]
            ),
            official_song(
                "samesong_new", "Same Song", [(3, 0), (7, 0), (11, 0), (13, 5)]
            ),
        ]
        result = song_sync.match_song_catalog(local, catalog)
        self.assertEqual(len(result["review"]), 0)
        self.assertEqual(result["matched"][0]["song_id"], "samesong_new")

    def test_legacy_chart_is_matched_and_written_into_legacy_node(self):
        local = [
            {
                "id": 1,
                "title": "Same Song",
                "artist": "Artist",
                "chapter": "1-1",
                "difficulty": {},
                "Legacy": {"Version": "1.0", "MaxMaster": "777"},
            }
        ]
        catalog = [
            official_song(
                "samesong", "Same Song (Legacy)", [(2, 0), (5, 0), (9, 0), (12, 0)]
            ),
            official_song(
                "samesong_new", "Same Song", [(3, 0), (7, 0), (11, 0), (13, 5)]
            ),
        ]
        matches = song_sync.match_song_catalog(local, catalog)
        self.assertEqual(matches["matched"][0]["song_id"], "samesong_new")
        self.assertEqual(matches["legacy_matched"][0]["song_id"], "samesong")
        updated, stats = song_sync.apply_catalog_matches(local, catalog, matches)
        legacy = updated[0]["Legacy"]
        self.assertEqual(legacy["official_songid"], "samesong")
        self.assertEqual(legacy["DiffMaster"], "12")
        self.assertEqual(legacy["official_constant"]["master"], 12.0)
        self.assertEqual(legacy["MaxMaster"], "777")
        self.assertEqual(stats["legacy_matched"], 1)

    def test_low_confidence_match_stays_in_review(self):
        local = [
            {
                "id": 1,
                "title": "Completely Different",
                "artist": "Unknown",
                "chapter": "Event-1",
                "difficulty": {},
            }
        ]
        catalog = [
            official_song("official", "Official Song", [(1, 0), (2, 0), (3, 0), (4, 0)])
        ]
        result = song_sync.match_song_catalog(local, catalog)
        self.assertEqual(len(result["matched"]), 0)
        self.assertEqual(len(result["review"]), 1)

    def test_apply_preserves_numeric_id_and_reorders_by_numeric_id(self):
        local = [
            {
                "id": 1,
                "title": "Zulu",
                "artist": "A",
                "chapter": "1-1",
                "difficulty": {},
            },
            {
                "id": 2,
                "title": "Alpha",
                "artist": "A",
                "chapter": "1-2",
                "difficulty": {},
            },
        ]
        catalog = [
            official_song(
                "alpha", "Alpha", [(1, 0), (2, 0), (3, 0), (4, 0)], artist="A"
            ),
            official_song("zulu", "Zulu", [(1, 0), (2, 0), (3, 0), (4, 0)], artist="A"),
        ]
        matches = song_sync.match_song_catalog(local, catalog)
        updated, stats = song_sync.apply_catalog_matches(local, catalog, matches)
        self.assertEqual([song["id"] for song in updated], [1, 2])
        self.assertEqual(
            [song["official_songid"] for song in updated], ["zulu", "alpha"]
        )
        self.assertEqual(stats["matched"], 2)

    def test_existing_official_songid_is_used_before_title_matching(self):
        local = [
            {
                "id": 7,
                "official_songid": "target",
                "title": "Completely Different",
                "artist": "Unknown",
                "chapter": "1-7",
                "difficulty": {},
            }
        ]
        catalog = [
            official_song("target", "Official Title", [(1, 0), (2, 0), (3, 0), (4, 0)])
        ]
        result = song_sync.match_song_catalog(local, catalog)
        self.assertEqual(result["matched"][0]["method"], "song_id")

    def test_next_numeric_song_id_ignores_official_id_field(self):
        songs = [
            {"id": 7, "official_songid": "seven"},
            {"id": 12, "official_songid": "twelve"},
        ]
        self.assertEqual(song_sync.next_numeric_song_id(songs), 13)

    def test_clean_title_preserves_unicode(self):
        title = "Anökumene of the endless ocher"
        self.assertEqual(song_sync.clean_title_text(title), title)

    def test_strip_nowiki_markup_recurses_without_removing_content(self):
        song = {
            "title": "<nowiki>#</nowiki>1f1e33",
            "cover_art": "<nowiki>:Poin7less</nowiki>",
            "nested": ["<NOWIKI>kept</NOWIKI>"],
        }
        self.assertEqual(
            song_sync.strip_nowiki_markup(song),
            {
                "title": "#1f1e33",
                "cover_art": ":Poin7less",
                "nested": ["kept"],
            },
        )

    def test_sanitize_song_markup_removes_html_and_preserves_visible_text(self):
        song = {
            "title": "VECTOR<span style=\"font-family: Arial\">↑</span>ZΣ",
            "Trivia": [
                "Master 14<sup>+</sup><br>visible",
                "<!--remove this-->Keep this",
            ],
            "cover_art": "<!--comment only-->",
            "literal": "Lian Meng Liang Mian <3 Syndrome",
        }
        self.assertEqual(
            song_sync.sanitize_song_markup(song),
            {
                "title": "VECTOR↑ZΣ",
                "Trivia": ["Master 14+ visible", "Keep this"],
                "cover_art": "",
                "literal": "Lian Meng Liang Mian <3 Syndrome",
            },
        )


if __name__ == "__main__":
    unittest.main()
