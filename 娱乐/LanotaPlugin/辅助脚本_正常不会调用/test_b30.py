# -*- encoding: utf-8 -*-
"""B30 公式、数据筛选、命令路由与冷却的离线回归测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PLUGIN_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_PARENT))

from LanotaPlugin import b30  # noqa: E402
from LanotaPlugin import config  # noqa: E402
from LanotaPlugin import message  # noqa: E402
from LanotaPlugin import portal  # noqa: E402


class B30FormulaTest(unittest.TestCase):
    def test_immaculate_known_result(self) -> None:
        result = b30.calculate_score_rating(934_838, 2701, 16.5)
        self.assertIsNotNone(result)
        self.assertEqual(result['exScore'], 5050)
        self.assertEqual(result['scoreAccuracy'], 93.48)
        self.assertEqual(result['singleRating'], 17.26)
        self.assertEqual(result['ratingPercent'], 92.10)

    def test_invalid_old_score_is_rejected(self) -> None:
        self.assertIsNone(b30.calculate_score_rating(123_456, 1000, 15.8))

    def test_zero_score_has_zero_rating(self) -> None:
        result = b30.calculate_score_rating(0, 1000, 16.5)
        self.assertEqual(result['singleRating'], 0)
        self.assertEqual(result['ratingPercent'], 0)

    def test_single_rating_infers_midpoint_score_and_accuracy(self) -> None:
        result = b30.infer_score_from_single_rating(17.74, 1000, 16.0)
        self.assertIsNotNone(result)
        self.assertTrue(result['inferred'])
        self.assertEqual(result['singleRating'], 17.74)
        self.assertLessEqual(result['inferredScoreMin'], result['score'])
        self.assertLessEqual(result['score'], result['inferredScoreMax'])
        self.assertIsNotNone(b30.calculate_score_rating(result['score'], 1000, 16.0))

    def test_impossible_single_rating_cannot_be_inferred(self) -> None:
        self.assertIsNone(b30.infer_score_from_single_rating(29.99, 1000, 16.0))

    def test_known_judgement_scores_use_new_ex_formula(self) -> None:
        samples = [
            (1497, 1, 1, 1499, 998_999),
            (1497, 1, 0, 1498, 999_666),
            (1912, 100, 7, 2019, 971_768),
            (2261, 20, 5, 2286, 993_438),
        ]
        for harmony, tune, fail, total, expected_score in samples:
            with self.subTest(total=total, expected_score=expected_score):
                result = b30.calculate_judgement_rating(harmony, tune, fail, total, 16.5)
                self.assertIsNotNone(result)
                self.assertEqual(result['score'], expected_score)

    def test_player_limit_uses_b1_for_all_five_recent_entries(self) -> None:
        entries = [
            {'_singleRatingExact': 18.75},
            *[{'_singleRatingExact': 17.0} for _index in range(29)],
        ]
        limits = b30.calculate_player_limits(entries, b30_contribution=14.82)
        self.assertEqual(limits['maxR5'], 2.67)
        self.assertEqual(limits['maxRating'], 17.49)

    def test_inferred_entries_skip_invalid_and_unmapped_scores(self) -> None:
        song = {'title': 'Valid Song', 'chapter': 'A-1'}
        catalog = {
            ('valid', 3): {
                'songId': 'valid',
                'title': 'Valid Song',
                'chapter': 'A-1',
                'difficulty': 3,
                'difficultyName': 'Master',
                'constantText': '15+.8(15.6)',
                'chartConstant': 15.8,
                'total': 1000,
                'chartSet': 'current',
                '_sourceSong': song,
            },
            ('invalid', 3): {
                'songId': 'invalid',
                'title': 'Invalid Song',
                'chapter': 'A-2',
                'difficulty': 3,
                'difficultyName': 'Master',
                'constantText': '15.8',
                'chartConstant': 15.8,
                'total': 1000,
                'chartSet': 'current',
                '_sourceSong': {'title': 'Invalid Song', 'chapter': 'A-2'},
            },
        }
        compare_data = {
            'songs': [
                {'songId': 'valid', 'difficulty': 3, 'friendScore': 1_000_000},
                {'songId': 'invalid', 'difficulty': 3, 'friendScore': 123_456},
                {'songId': 'missing', 'difficulty': 3, 'friendScore': 1_000_000},
            ]
        }
        entries, validation = b30.build_inferred_entries(compare_data, catalog)
        self.assertEqual([item['songId'] for item in entries], ['valid'])
        self.assertEqual(validation['invalid'], 1)
        self.assertEqual(validation['unmapped'], 1)

    def test_exact_entry_marks_stale_portal_score(self) -> None:
        source = {
            'songId': 'song',
            'title': 'Song',
            'difficulty': 3,
            'level': 15,
            'levelFraction': 8,
            'harmony': 99,
            'tune': 1,
            'fail': 0,
            'total': 100,
            'exScore': 199,
            'maxExScore': 200,
            'exScoreRate': 99.5,
            'singleRating': 17.59,
            'ratingPercent': 99.4,
        }
        rating_data = {'best30': {'entries': [source]}}
        scores_data = {'songs': [{'songId': 'song', 'difficulty': 3, 'score': 1_000_000}]}
        entries, validation = b30.build_exact_entries(rating_data, scores_data, {})
        self.assertEqual(entries[0]['score'], 995_000)
        self.assertIn('当前最高分 1,000,000', entries[0]['warning'])
        self.assertEqual(validation['mismatch'], 1)

    def test_exact_entries_append_inferred_overflow(self) -> None:
        exact_source = {
            'songId': 'best',
            'difficulty': 3,
            'level': 15,
            'levelFraction': 8,
            'harmony': 99,
            'tune': 1,
            'fail': 0,
            'total': 100,
            'exScore': 199,
            'maxExScore': 200,
            'singleRating': 17.59,
        }
        catalog = {}
        for song_id in ('overflow-1', 'overflow-2', 'overflow-3', 'overflow-4'):
            catalog[(song_id, 3)] = {
                'songId': song_id,
                'title': song_id,
                'chapter': 'Test',
                'difficulty': 3,
                'difficultyName': 'Master',
                'constantText': '15+.8(15.8)',
                'chartConstant': 15.8,
                'total': 1000,
                '_sourceSong': {'title': song_id},
            }
        scores_data = {
            'songs': [
                {'songId': 'best', 'difficulty': 3, 'score': 995_000},
                {'songId': 'overflow-1', 'difficulty': 3, 'score': 1_000_000},
                {'songId': 'overflow-2', 'difficulty': 3, 'score': 999_500},
                {'songId': 'overflow-3', 'difficulty': 3, 'score': 999_000},
                {'songId': 'overflow-4', 'difficulty': 3, 'score': 998_500},
            ]
        }
        rating_data = {'best30': {'entries': [exact_source]}}

        entries, validation = b30.build_exact_entries(rating_data, scores_data, catalog)

        overflow = [item for item in entries if item['overflow']]
        self.assertEqual([item['songId'] for item in overflow], ['overflow-1', 'overflow-2', 'overflow-3'])
        self.assertEqual([item['rank'] for item in overflow], [31, 32, 33])
        self.assertTrue(all(not item['exact'] for item in overflow))
        self.assertEqual(validation['overflow'], 3)

        card_data = b30.build_exact_card_data(rating_data, scores_data, catalog, 'global')
        expected_b30 = b30.truncate_two(float(entries[0]['_singleRatingExact']) / 35)
        self.assertEqual(card_data['metrics']['b30Contribution'], expected_b30)


class B30CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        message.b30_last_used.clear()

    def test_b30_command_replaces_rating_command(self) -> None:
        self.assertEqual(message.match_command('la b30 cn'), ('b30', 'cn'))
        self.assertNotEqual(message.match_command('la rating')[0], 'rating')

    def test_calculate_alias_uses_reimplemented_handler(self) -> None:
        argument = '1497/1/1/1499/16.5'
        self.assertEqual(message.match_command(f'la calculate {argument}'), ('cal', argument))
        with patch.object(message, 'reply_text') as reply_text:
            message.handle_cal(object(), argument)
        output = reply_text.call_args.args[1]
        self.assertIn('新版分数: 998,999', output)
        self.assertIn('EX = 2×Harmony + Tune', output)
        self.assertNotIn('Tune/3', output)

    def test_all_region_aliases_use_shared_table(self) -> None:
        for alias in ('global', 'international', 'intl', '国际服'):
            self.assertEqual(portal.split_region_argument(f'{alias} value'), ('global', 'value'))
        for alias in ('cn', 'china', '中国', '中国服', '国服'):
            self.assertEqual(portal.split_region_argument(f'{alias} value'), ('china', 'value'))

    def test_b30_cooldown_is_separate_between_regions(self) -> None:
        event = SimpleNamespace(
            bot_info=SimpleNamespace(hash='bot'),
            data=SimpleNamespace(user_id='user'),
        )
        with patch.object(message.time, 'monotonic', side_effect=[1000.0, 1001.0, 1002.0, 1300.0]):
            self.assertEqual(message._consume_b30_cooldown(event, 'global'), 0)
            self.assertEqual(message._consume_b30_cooldown(event, 'china'), 0)
            self.assertEqual(message._consume_b30_cooldown(event, 'global'), 298)
            self.assertEqual(message._consume_b30_cooldown(event, 'global'), 0)

    def test_different_users_have_independent_cooldowns(self) -> None:
        first = SimpleNamespace(bot_info=SimpleNamespace(hash='bot'), data=SimpleNamespace(user_id='one'))
        second = SimpleNamespace(bot_info=SimpleNamespace(hash='bot'), data=SimpleNamespace(user_id='two'))
        with patch.object(message.time, 'monotonic', side_effect=[1000.0, 1000.0]):
            self.assertEqual(message._consume_b30_cooldown(first, 'global'), 0)
            self.assertEqual(message._consume_b30_cooldown(second, 'global'), 0)

    def test_b30_prepares_official_fields_before_building_catalog(self) -> None:
        event = object()
        local_song = {'id': 1, 'title': 'Song', 'chapter': '1-1'}
        updated_song = {
            **local_song,
            'official_songid': 'song',
            'official_constant': {
                'whisper': 1.0,
                'acoustic': 2.0,
                'ultra': 3.0,
                'master': 4.0,
            },
        }
        card_data = {'entries': [], 'notice': '', 'player': {}, 'metrics': {}}
        with (
            patch.object(message.portal, 'get_bound_region', return_value='global'),
            patch.object(message.portal, 'get_bound_nano_id', return_value='NANO'),
            patch.object(message, '_consume_b30_cooldown', return_value=0),
            patch.object(message.utils, 'reply_message'),
            patch.object(message.function, 'load_song_data', return_value=[local_song]),
            patch.object(
                message.crawler,
                'ensure_official_catalog_fields',
                return_value=(
                    [updated_song],
                    {'attempted': True, 'changed': True, 'persisted': True, 'error': ''},
                ),
            ) as ensure_fields,
            patch.object(message.b30, 'build_chart_catalog', return_value={}) as build_catalog,
            patch.object(message.portal, 'get_me', return_value={'nanoId': 'OTHER'}),
            patch.object(
                message.portal,
                'get_compare_data_cached',
                return_value=({'friend': {}, 'songs': []}, 'NANO', None),
            ),
            patch.object(message.b30, 'build_inferred_card_data', return_value=card_data),
            patch.object(message.score_overrides, 'reconcile_official_scores', return_value=0),
            patch.object(message.score_overrides, 'apply_to_card', side_effect=lambda *_args: card_data),
            patch.object(message.b30, 'build_fallback_text', return_value='fallback'),
            patch.object(message, 'is_plain_text_mode', return_value=True),
            patch.object(message.b30, 'strip_internal_fields'),
            patch.object(message, 'reply_large_text'),
        ):
            message.handle_b30(event, '')

        ensure_fields.assert_called_once_with([local_song])
        build_catalog.assert_called_once_with([updated_song])
        self.assertIn('补全', card_data['notice'])


class B30RenderTest(unittest.TestCase):
    def test_screenshot_height_tracks_entry_rows(self) -> None:
        expected_heights = {
            0: 600,
            1: 690,
            10: 1230,
            30: 2310,
            33: 2558,
        }
        for entry_count, expected_height in expected_heights.items():
            with self.subTest(entry_count=entry_count):
                data = {'entries': [{} for _index in range(entry_count)]}
                self.assertEqual(portal._b30_screenshot_height(data), expected_height)

        notice_data = {
            'entries': [{} for _index in range(33)],
            'notice': '4.0以前旧版本成绩无法查询真实 B30 与判定明细；请重新游玩歌曲获得更准确的结果。',
        }
        self.assertGreater(portal._b30_screenshot_height(notice_data), expected_heights[33])

    def test_portal_webp_compression_keeps_pixel_dimensions(self) -> None:
        try:
            from PIL import Image
        except Exception:
            self.skipTest('Pillow unavailable')
        with tempfile.TemporaryDirectory() as temporary_dir:
            source_path = Path(temporary_dir) / 'b30.png'
            Image.new('RGB', (1200, 800), (242, 232, 215)).save(source_path)
            output_path = portal._compress_rendered_card(source_path)
            self.assertEqual(output_path.suffix, '.webp')
            self.assertFalse(source_path.exists())
            with Image.open(output_path) as output_image:
                self.assertEqual(output_image.size, (1200, 800))

    def test_all_portal_templates_use_local_fonts(self) -> None:
        for card_type in ('user', 'song', 'b30'):
            with self.subTest(card_type=card_type):
                html = portal._template_html({'_portal_region': 'china'}, card_type)
                self.assertNotIn('./Kawoszeh.ttf', html)
                self.assertNotIn('./千图雪花体.ttf', html)
                self.assertIn('Kawoszeh.ttf', html)
                self.assertIn('%E5%8D%83%E5%9B%BE%E9%9B%AA%E8%8A%B1%E4%BD%93.ttf', html)

    def test_b30_logo_is_synced_to_runtime_asset_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source_data_dir = root / 'package-data'
            source_asset_dir = source_data_dir / 'B30Assets'
            source_asset_dir.mkdir(parents=True)
            (source_asset_dir / 'Lanotalogo_top.png').write_bytes(b'logo-data')
            runtime_data_dir = root / 'plugin' / 'data' / 'LanotaPlugin'
            with (
                patch.object(config, 'asset_data_dir', source_data_dir),
                patch.object(config, 'plugin_data_dir', str(runtime_data_dir)),
            ):
                html = portal._template_html({'_portal_region': 'global'}, 'b30')

            runtime_logo = runtime_data_dir / 'B30Assets' / 'Lanotalogo_top.png'
            self.assertEqual(runtime_logo.read_bytes(), b'logo-data')
            self.assertIn((runtime_data_dir / 'B30Assets').resolve().as_uri(), html)

    def test_b30_template_colors_difficulty_name_and_keeps_exact_overflow(self) -> None:
        html = portal._template_html({'_portal_region': 'global'}, 'b30')
        self.assertIn("wrapper.classList.add('difficulty-accent')", html)
        self.assertNotIn('data.accurate || (hasRuntimeData && !overflowEntries.length)', html)
        self.assertIn('width: min(1216px, 100%)', html)
        self.assertIn('width: 190px', html)
        self.assertIn('white-space: normal', html)
        self.assertIn('background-size: auto 100%', html)
        self.assertIn("const cover = document.createElement('div');", html)
        self.assertNotIn("const cover = document.createElement('img');", html)
        self.assertIn("fact('单曲', Number(entry.singleRating).toFixed(2))", html)
        self.assertIn('Number(entry.score || 0) < 1000000', html)
        self.assertIn("document.querySelectorAll('.song-title').forEach(fitSongTitle)", html)
        self.assertEqual(config.lanota_portal_b30_screenshot_width, 1320)

    def test_user_templates_spell_out_clear_types(self) -> None:
        for region in ('global', 'china'):
            with self.subTest(region=region):
                html = portal._template_html({'_portal_region': region}, 'user')
                self.assertIn('<b>${label}</b>', html)
                self.assertNotIn("label === 'Perfect Purified' ? 'PP'", html)


if __name__ == '__main__':
    unittest.main()
