# -*- encoding: utf-8 -*-
"""update/fullcheck 官方 ID 与新曲数字 ID 的离线回归测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_PARENT))

from LanotaPlugin import crawler  # noqa: E402
from LanotaPlugin import function  # noqa: E402


def official_song(song_id: str, title: str) -> dict:
    return {
        "songId": song_id,
        "title": title,
        "artist": "Artist",
        "charts": [
            {"difficulty": index, "level": index + 1, "levelFraction": 0}
            for index in range(4)
        ],
        "_portal_region": "global",
    }


class UpdateIdFlowTest(unittest.TestCase):
    def test_fullcheck_reapplies_legacy_official_fields_after_fandom_parse(self):
        current_official = official_song('song_new', 'Song')
        legacy_official = official_song('song', 'Song (Legacy)')
        local = {
            'id': 1,
            'chapter': '1-1',
            'title': 'Song',
            'source_url': 'https://example/wiki/Song',
            'difficulty': {},
            'notes': {'whisper': '1', 'acoustic': '2', 'ultra': '3', 'master': '4'},
            'Legacy': {'Chart Design': 'Local Charter'},
        }
        parsed = {
            'title': 'Song',
            'difficulty': {},
            'notes': {'whisper': '1', 'acoustic': '2', 'ultra': '3', 'master': '4'},
            'Legacy': {
                'Chart Design': 'Wiki Charter',
                'MaxWhisper': '10',
                'MaxAcoustic': '20',
                'MaxUltra': '30',
                'MaxMaster': '40',
            },
        }
        with (
            patch.object(crawler, 'fetch_wikitext', return_value='wikitext'),
            patch.object(crawler, 'parse_song_from_wikitext', return_value=parsed),
            patch.object(crawler, 'fill_missing_notes_from_portal'),
        ):
            updated, _changed = crawler.overwrite_existing_song_from_wiki(
                object(),
                local,
                current_official,
                legacy_official,
            )
        self.assertEqual(updated['id'], 1)
        self.assertEqual(updated['Legacy']['Chart Design'], 'Local Charter')
        self.assertEqual(updated['Legacy']['official_songid'], 'song')
        self.assertEqual(updated['Legacy']['official_constant']['master'], 4.0)

    def test_new_song_gets_numeric_id_without_official_id_matching(self):
        data = [
            {
                "id": 41,
                "title": "Existing",
                "title_outside": "Existing",
                "chapter": "1-1",
            }
        ]
        info = {
            "display_title": "New Song",
            "page_name": "New Song",
            "href": "https://example/wiki/New_Song",
        }
        parsed = {
            "id": 42,
            "title": "New Song",
            "title_outside": "New Song",
            "artist": "Artist",
            "chapter": "Event-2",
            "difficulty": {
                "whisper": "1",
                "acoustic": "2",
                "ultra": "3",
                "master": "4",
            },
            "notes": {"whisper": "1", "acoustic": "2", "ultra": "3", "master": "4"},
        }
        with (
            patch.object(crawler, "fetch_song_list_from_api", return_value=[info]),
            patch.object(crawler, "fetch_wikitext", return_value="wikitext"),
            patch.object(crawler, "parse_song_from_wikitext", return_value=parsed),
            patch.object(crawler, "fill_missing_notes_from_portal"),
            patch.object(crawler.time, "sleep"),
        ):
            result = crawler.sync_new_songs_from_wiki(object(), data, [], apply=True)

        self.assertEqual(
            result["official_pending"][0]["reason"],
            "新曲等待辅助脚本匹配 official_songid",
        )
        self.assertEqual(data[-1]["id"], 42)
        self.assertNotIn("official_songid", data[-1])

    def test_note_fallback_uses_official_songid(self):
        calls = []

        def fake_api_get(path, params=None, region="global"):
            calls.append((path, params, region))
            difficulty = params["difficulty"]
            return {
                "scores": [
                    {
                        "difficulty": difficulty,
                        "ratingRecord": {"total": 100 + difficulty},
                    }
                ]
            }

        song = {
            "id": 7,
            "official_songid": "official-song",
            "notes": {"whisper": "", "acoustic": "", "ultra": "", "master": ""},
        }
        with patch.object(crawler.portal, "api_get", side_effect=fake_api_get):
            stats = crawler.fill_missing_notes_from_portal(
                song, official_song("official-song", "Song")
            )

        self.assertEqual(stats, {"requested": 4, "filled": 4, "unavailable": 0})
        self.assertEqual({call[1]["songId"] for call in calls}, {"official-song"})

    def test_search_accepts_both_numeric_and_official_id(self):
        song = {
            "id": 7,
            "official_songid": "official-song",
            "title": "Song",
            "chapter": "1-1",
        }
        for search_term in ("7", "official-song"):
            matched, match_type, _score = function.find_song_by_search_term(
                search_term, [song], {}
            )
            self.assertEqual(matched, [song])
            self.assertEqual(match_type, "ID匹配")


if __name__ == "__main__":
    unittest.main()
