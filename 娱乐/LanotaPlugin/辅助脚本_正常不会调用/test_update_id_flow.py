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
    @staticmethod
    def _complete_song_with_nowiki() -> dict:
        return {
            'id': 1,
            'title': '<nowiki>#</nowiki><span style="font-family: Arial">1f1e33</span>',
            'chapter': 'Event-6',
            'official_songid': '1f1e33',
            'bpm': '181',
            'time': '2:49',
            'notes': {'whisper': '1', 'acoustic': '2', 'ultra': '3', 'master': '4'},
            'Trivia': ['Master 14<sup>+</sup><br>visible'],
        }

    def test_official_catalog_fetch_always_attempts_international_api(self):
        calls = []

        def fake_api_get(path, region='global'):
            calls.append((path, region))
            if region == 'global':
                return {'songs': [official_song('global-song', 'Global Song')]}
            raise PermissionError('china unavailable')

        with patch.object(crawler.portal, 'api_get', side_effect=fake_api_get):
            catalog, errors = crawler.fetch_official_song_catalog()

        self.assertEqual(calls[0], ('songs', 'global'))
        self.assertEqual([song['songId'] for song in catalog], ['global-song'])
        self.assertEqual(len(errors), 1)

    def test_update_fills_missing_official_id_and_constants_for_existing_song(self):
        local_song = {
            'id': 1,
            'title': 'Existing Song',
            'title_outside': 'Existing Song',
            'artist': 'Artist',
            'chapter': '1-1',
            'difficulty': {
                'whisper': '1',
                'acoustic': '2',
                'ultra': '3',
                'master': '4',
            },
            'bpm': '180',
            'time': '2:00',
            'notes': {
                'whisper': '100',
                'acoustic': '200',
                'ultra': '300',
                'master': '400',
            },
        }
        empty_new = {
            'added_songs': [],
            'title_outside_updates': [],
            'official_pending': [],
        }
        catalog = [official_song('existing-song', 'Existing Song')]

        with (
            patch.object(function, 'load_song_data', return_value=[local_song]),
            patch.object(crawler, 'fetch_official_song_catalog', return_value=(catalog, [])),
            patch.object(crawler, 'sync_new_songs_from_wiki', return_value=empty_new),
            patch.object(function, 'save_song_data', return_value=True) as save_song_data,
            patch.object(crawler, 'update_new_song_covers', return_value={}),
        ):
            result = crawler.run_update()

        saved_song = save_song_data.call_args.args[0][0]
        self.assertEqual(saved_song['official_songid'], 'existing-song')
        self.assertEqual(
            saved_song['official_constant'],
            {'whisper': 1.0, 'acoustic': 2.0, 'ultra': 3.0, 'master': 4.0},
        )
        self.assertEqual(result['official_changed_fields']['official_songid'], 1)
        self.assertEqual(result['official_changed_fields']['official_constant'], 1)
        self.assertEqual(result['missing_songs'], 0)

    def test_missing_check_includes_official_id_and_constants(self):
        missing = crawler.check_missing_fields(
            {
                'bpm': '180',
                'time': '2:00',
                'notes': {
                    'whisper': '100',
                    'acoustic': '200',
                    'ultra': '300',
                    'master': '400',
                },
            }
        )
        self.assertIn('official_songid', missing)
        self.assertIn('official_constant(whisper,acoustic,ultra,master)', missing)

    def test_query_preflight_skips_api_when_official_fields_are_complete(self):
        song = {
            'official_songid': 'complete-song',
            'official_constant': {
                'whisper': 1.0,
                'acoustic': 2.0,
                'ultra': 3.0,
                'master': 4.0,
            },
        }
        with patch.object(crawler, 'fetch_official_song_catalog') as fetch_catalog:
            updated, result = crawler.ensure_official_catalog_fields([song])

        fetch_catalog.assert_not_called()
        self.assertIs(updated[0], song)
        self.assertFalse(result['attempted'])

    def test_query_preflight_fetches_and_persists_missing_official_fields(self):
        song = {
            'id': 1,
            'title': 'Existing Song',
            'artist': 'Artist',
            'chapter': '1-1',
            'difficulty': {},
        }
        catalog = [official_song('existing-song', 'Existing Song')]
        with (
            patch.object(crawler, 'fetch_official_song_catalog', return_value=(catalog, [])),
            patch.object(function, 'save_song_data', return_value=True) as save_song_data,
        ):
            updated, result = crawler.ensure_official_catalog_fields([song])

        self.assertEqual(updated[0]['official_songid'], 'existing-song')
        self.assertEqual(updated[0]['official_constant']['master'], 4.0)
        self.assertTrue(result['attempted'])
        self.assertTrue(result['changed'])
        self.assertTrue(result['persisted'])
        save_song_data.assert_called_once()

    def test_wiki_field_removes_nowiki_tags(self):
        self.assertEqual(
            crawler.clean_wiki_links('<nowiki>#</nowiki>1f1e33'),
            '#1f1e33',
        )

    def test_update_strips_historical_nowiki_before_save(self):
        song = self._complete_song_with_nowiki()
        empty_match = {'matched': [], 'review': [], 'legacy_review': []}
        empty_new = {'added_songs': [], 'title_outside_updates': [], 'official_pending': []}
        with (
            patch.object(function, 'load_song_data', return_value=[song]),
            patch.object(crawler, 'fetch_official_song_catalog', return_value=([], [])),
            patch.object(
                crawler,
                'match_and_apply_official_catalog',
                side_effect=lambda data, _catalog: (data, {}, empty_match),
            ),
            patch.object(crawler, 'sync_new_songs_from_wiki', return_value=empty_new),
            patch.object(function, 'save_song_data', return_value=True) as save_song_data,
        ):
            crawler.run_update()
        self.assertEqual(save_song_data.call_args.args[0][0]['title'], '#1f1e33')
        self.assertEqual(
            save_song_data.call_args.args[0][0]['Trivia'],
            ['Master 14+ visible'],
        )

    def test_update_only_downloads_and_adjusts_new_song_covers(self):
        song = self._complete_song_with_nowiki()
        new_song = {'id': 2, 'title': 'New Song', 'chapter': 'Event-2'}
        empty_match = {'matched': [], 'review': [], 'legacy_review': []}
        new_result = {
            'added_songs': [new_song],
            'title_outside_updates': [],
            'official_pending': [],
        }
        cover_result = {
            'total': 1,
            'ready': 1,
            'images': 1,
            'adjusted': 1,
            'failed': 0,
            'failed_songs': [],
        }
        with (
            patch.object(function, 'load_song_data', return_value=[song]),
            patch.object(crawler, 'fetch_official_song_catalog', return_value=([], [])),
            patch.object(
                crawler,
                'match_and_apply_official_catalog',
                side_effect=lambda data, _catalog: (data, {}, empty_match),
            ),
            patch.object(crawler, 'sync_new_songs_from_wiki', return_value=new_result),
            patch.object(function, 'save_song_data', return_value=True),
            patch.object(crawler, 'update_new_song_covers', return_value=cover_result) as update_covers,
        ):
            result = crawler.run_update()
        update_covers.assert_called_once_with([new_song])
        self.assertEqual(result['new_cover_result'], cover_result)

    def test_update_rematches_wiki_new_song_against_official_catalog(self):
        existing_song = self._complete_song_with_nowiki()
        existing_song.update(
            {
                'title': 'Existing Song',
                'title_outside': 'Existing Song',
                'artist': 'Artist',
                'chapter': '1-1',
                'official_songid': 'existing-song',
                'difficulty': {
                    'whisper': '1',
                    'acoustic': '2',
                    'ultra': '3',
                    'master': '4',
                },
            }
        )
        new_song = {
            'id': 724,
            'title': 'Moonlight Chaser',
            'title_outside': 'Moonlight Chaser',
            'artist': 'BlackY vs. Yooh',
            'chapter': 'SRI-3',
            'difficulty': {
                'whisper': '6',
                'acoustic': '10',
                'ultra': '14',
                'master': '15+',
            },
            'bpm': '180',
            'time': '2:34',
            'notes': {
                'whisper': '100',
                'acoustic': '200',
                'ultra': '300',
                'master': '400',
            },
        }
        catalog = [
            official_song('existing-song', 'Existing Song'),
            official_song('moonlightchaser', 'Moonlight Chaser'),
        ]
        new_result = {
            'added_songs': [new_song],
            'title_outside_updates': [],
            'official_pending': [
                {
                    'title': 'Moonlight Chaser',
                    'chapter': 'SRI-3',
                    'reason': '新曲等待辅助脚本匹配 official_songid',
                }
            ],
        }

        def append_new_song(_session, data, *_args, **_kwargs):
            data.append(new_song)
            return new_result

        with (
            patch.object(function, 'load_song_data', return_value=[existing_song]),
            patch.object(crawler, 'fetch_official_song_catalog', return_value=(catalog, [])),
            patch.object(crawler, 'sync_new_songs_from_wiki', side_effect=append_new_song),
            patch.object(function, 'save_song_data', return_value=True) as save_song_data,
            patch.object(
                crawler,
                'update_new_song_covers',
                return_value={
                    'total': 1,
                    'ready': 0,
                    'images': 0,
                    'adjusted': 0,
                    'failed': 1,
                    'failed_songs': ['Moonlight Chaser'],
                },
            ),
        ):
            result = crawler.run_update()

        saved_songs = save_song_data.call_args.args[0]
        saved_new_song = next(song for song in saved_songs if song.get('chapter') == 'SRI-3')
        self.assertEqual(saved_new_song['official_songid'], 'moonlightchaser')
        self.assertEqual(saved_new_song['official_constant']['master'], 4.0)
        self.assertEqual(result['official_pending'], [])
        self.assertEqual(result['official_matched'], 2)

    def test_update_reports_new_song_when_international_catalog_has_no_match(self):
        existing_song = self._complete_song_with_nowiki()
        new_song = {
            'id': 724,
            'title': 'Moonlight Chaser',
            'chapter': 'SRI-3',
            'difficulty': {},
            'notes': {'whisper': '', 'acoustic': '', 'ultra': '', 'master': ''},
        }
        new_result = {
            'added_songs': [new_song],
            'title_outside_updates': [],
            'official_pending': [],
        }

        def append_new_song(_session, data, *_args, **_kwargs):
            data.append(new_song)
            return new_result

        with (
            patch.object(function, 'load_song_data', return_value=[existing_song]),
            patch.object(
                crawler,
                'fetch_official_song_catalog',
                return_value=([official_song('1f1e33', '#1f1e33')], []),
            ),
            patch.object(crawler, 'sync_new_songs_from_wiki', side_effect=append_new_song),
            patch.object(function, 'save_song_data', return_value=True),
            patch.object(crawler, 'update_new_song_covers', return_value={}),
        ):
            result = crawler.run_update()

        self.assertEqual(result['official_pending'][0]['chapter'], 'SRI-3')
        self.assertEqual(
            result['official_pending'][0]['reason'],
            '国际服 API 未找到可信的对应曲目',
        )

    def test_new_song_cover_update_forces_download_and_counts_adjusted_paths(self):
        songs = [
            {'title': 'Ready Song', 'chapter': 'Event-2'},
            {'title': 'Failed Song', 'chapter': 'Event-3'},
        ]
        adjusted_dir = str(Path('adjusted').resolve())

        def fake_covers(song, force=False):
            self.assertTrue(force)
            if song['title'] == 'Ready Song':
                return [str(Path(adjusted_dir) / 'Event-2.png')]
            return []

        with (
            patch.object(crawler.utils, 'get_adjusted_cover_art_dir', return_value=adjusted_dir),
            patch.object(crawler, 'ensure_song_covers', side_effect=fake_covers) as ensure_covers,
        ):
            result = crawler.update_new_song_covers(songs)
        self.assertEqual(ensure_covers.call_count, 2)
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['ready'], 1)
        self.assertEqual(result['images'], 1)
        self.assertEqual(result['adjusted'], 1)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['failed_songs'], ['Failed Song'])

    def test_cover_failure_does_not_undo_successful_song_update(self):
        song = self._complete_song_with_nowiki()
        new_song = {'id': 2, 'title': 'New Song', 'chapter': 'Event-2'}
        empty_match = {'matched': [], 'review': [], 'legacy_review': []}
        new_result = {
            'added_songs': [new_song],
            'title_outside_updates': [],
            'official_pending': [],
        }
        with (
            patch.object(function, 'load_song_data', return_value=[song]),
            patch.object(crawler, 'fetch_official_song_catalog', return_value=([], [])),
            patch.object(
                crawler,
                'match_and_apply_official_catalog',
                side_effect=lambda data, _catalog: (data, {}, empty_match),
            ),
            patch.object(crawler, 'sync_new_songs_from_wiki', return_value=new_result),
            patch.object(function, 'save_song_data', return_value=True),
            patch.object(crawler, 'update_new_song_covers', side_effect=RuntimeError('offline')),
            patch.object(crawler.utils, 'debug_log'),
        ):
            result = crawler.run_update()
        self.assertEqual(result['added_titles'], ['New Song'])
        self.assertEqual(result['new_cover_result']['failed'], 1)
        self.assertEqual(result['new_cover_result']['failed_songs'], ['New Song'])

    def test_update_report_includes_new_song_cover_result(self):
        report = function.build_update_report({
            'before': 1,
            'added': 2,
            'added_titles': ['Ready Song', 'Failed Song'],
            'new_cover_result': {
                'total': 2,
                'ready': 1,
                'images': 1,
                'adjusted': 1,
                'failed': 1,
                'failed_songs': ['Failed Song'],
            },
            'total': 3,
        })
        self.assertIn('【新曲曲绘】', report)
        self.assertIn('处理成功: 1/2首', report)
        self.assertIn('2:1 自动校正: 1张', report)
        self.assertIn('失败歌曲: Failed Song', report)

    def test_fullcheck_apply_strips_historical_nowiki_before_save(self):
        song = self._complete_song_with_nowiki()
        empty_match = {'matched': [], 'review': [], 'legacy_review': []}
        empty_new = {'added_songs': [], 'title_outside_updates': [], 'official_pending': []}
        with (
            patch.object(function, 'load_song_data', return_value=[song]),
            patch.object(crawler, 'fetch_official_song_catalog', return_value=([], [])),
            patch.object(crawler.song_sync, 'match_song_catalog', return_value=empty_match),
            patch.object(
                crawler.song_sync,
                'apply_catalog_matches',
                side_effect=lambda data, _catalog, _matches: (data, {}),
            ),
            patch.object(crawler, 'sync_new_songs_from_wiki', return_value=empty_new),
            patch.object(function, 'save_song_data', return_value=True) as save_song_data,
        ):
            crawler.run_full_check(apply=True)
        self.assertEqual(save_song_data.call_args.args[0][0]['title'], '#1f1e33')
        self.assertEqual(
            save_song_data.call_args.args[0][0]['Trivia'],
            ['Master 14+ visible'],
        )

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
