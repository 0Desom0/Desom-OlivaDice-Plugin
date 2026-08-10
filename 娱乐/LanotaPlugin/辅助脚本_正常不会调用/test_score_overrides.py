# -*- encoding: utf-8 -*-
"""玩家成绩录入、Single Rating 覆盖与 Portal/游戏结算截图回归测试。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PLUGIN_DIR = Path(__file__).resolve().parents[1]
PLUGIN_PARENT = PLUGIN_DIR.parent
FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures'
sys.path.insert(0, str(PLUGIN_PARENT))

from LanotaPlugin import b30  # noqa: E402
from LanotaPlugin import function  # noqa: E402
from LanotaPlugin import message  # noqa: E402
from LanotaPlugin import score_overrides  # noqa: E402
from LanotaPlugin import utils  # noqa: E402


class ScoreOverrideTest(unittest.TestCase):
    @staticmethod
    def _chart() -> dict:
        return {
            'songId': 'test',
            'title': 'Test Song',
            'chapter': 'Boss-3',
            'difficulty': 3,
            'difficultyName': 'Master',
            'constantText': '16',
            'chartConstant': 16.0,
            'total': 1000,
            'chartSet': 'current',
            '_sourceSong': {'title': 'Test Song', 'chapter': 'Boss-3'},
        }

    def test_multiple_image_segments_are_extracted(self) -> None:
        message = (
            '.la score cn '
            '[OP:image,url=https://example.com/a.png?x=1&amp;y=2]'
            '[CQ:image,file=file:///C:/Temp/b.png]'
        )
        self.assertEqual(
            score_overrides.extract_image_refs(message),
            [
                'https://example.com/a.png?x=1&y=2',
                'file:///C:/Temp/b.png',
            ],
        )

    def test_game_ocr_only_runs_missing_crop_sections(self) -> None:
        image_path = FIXTURE_DIR / 'game_result_mononoke_score_only_valid.jpg'
        complete_text = '\n'.join([
            'Erasure: A World Without You', 'MASTER', '0978748',
            '2449', '76', '16', '2', '96%', '3%', '1%',
            'Harmony', 'Tune', 'Fail', '341/2541',
        ])
        with (
            patch.object(score_overrides, '_predict_ocr_text', return_value=complete_text),
            patch.object(score_overrides, '_adaptive_game_result_sections') as adaptive,
        ):
            self.assertEqual(score_overrides._ocr_text(image_path), complete_text)
        adaptive.assert_not_called()

        incomplete_text = '\n'.join([
            'Nemexis', 'MASTER', '0993282', '2208', '20',
            'Harmony', 'Tune', 'Fail',
        ])
        with (
            patch.object(score_overrides, '_predict_ocr_text', return_value=incomplete_text),
            patch.object(score_overrides, '_adaptive_game_result_sections', return_value={'judgements': '5'}) as adaptive,
        ):
            output = score_overrides._ocr_text(image_path)
        adaptive.assert_called_once_with(image_path, ('judgements',))
        self.assertIn('[[LANOTA_OCR_JUDGEMENTS]]', output)

    def test_portrait_portal_ocr_can_force_full_image_fallback(self) -> None:
        image_path = FIXTURE_DIR / 'portal_score_mobile_nightfall.png'
        compact_input = object()
        self.assertEqual(score_overrides._clean_score('981, 118'), 981_118)
        with (
            patch.object(score_overrides, '_portal_fast_ocr_input', return_value=compact_input),
            patch.object(score_overrides, '_predict_ocr_text', return_value='') as predict,
        ):
            self.assertEqual(score_overrides._ocr_text(image_path), '')
        predict.assert_called_once_with(compact_input)

        with (
            patch.object(score_overrides, '_portal_fast_ocr_input', return_value=compact_input),
            patch.object(score_overrides, '_predict_ocr_text', return_value='') as predict,
        ):
            self.assertEqual(score_overrides._ocr_text(image_path, force_full_image=True), '')
        predict.assert_called_once_with(image_path)

    def test_manual_input_uses_single_rating(self) -> None:
        title, _difficulty_text, difficulty, single_rating, region = (
            score_overrides.parse_manual_argument(
                'cn Immaculate master 18.18',
            )
        )
        self.assertEqual(title, 'Immaculate')
        self.assertEqual(difficulty, 3)
        self.assertEqual(single_rating, 18.18)
        self.assertEqual(region, 'china')

    def test_manual_failure_reports_matched_song_and_chart(self) -> None:
        song = {
            'title': 'Apotheosis (Lanota Edit)',
            'chapter': 'Event-110',
            'official_songid': 'apotheosis_lanota_edit',
            'notes': {'master': 1000},
            'official_constant': {'master': 10.0},
        }
        with patch.object(score_overrides, 'resolve_song', return_value=(song, 0.95)):
            success, result = score_overrides.add_manual(
                SimpleNamespace(),
                'apoptheosis master 17.70',
            )
        self.assertFalse(success)
        self.assertIn('Apotheosis (Lanota Edit)', result)
        self.assertIn('章节号 Event-110', result)
        self.assertIn('难度 Master', result)
        self.assertIn('不可能由该谱面的 4.0+ 公式得到', result)

    def test_manual_typo_uses_the_same_best_match_as_song_search(self) -> None:
        song, confidence = score_overrides.resolve_song('apoptheosis')
        self.assertIsNotNone(song)
        self.assertEqual(song['title'], 'Apotheosis (Lanota Edit)')
        self.assertGreater(confidence, 0.9)

    def test_manual_typo_records_apotheosis_rating(self) -> None:
        with (
            patch.object(score_overrides, 'load_overrides', return_value=[]),
            patch.object(score_overrides, 'save_overrides', return_value=True),
        ):
            success, result = score_overrides.add_manual(
                SimpleNamespace(),
                'apoptheosis master 17.70',
            )
        self.assertTrue(success)
        self.assertIn('已录入：Apotheosis (Lanota Edit)', result)
        self.assertIn('章节号：Event-110', result)

    def test_storage_is_keyed_by_region_chapter_and_difficulty(self) -> None:
        memory = {'42': {}}
        event = SimpleNamespace()
        rows = [{
            'region': 'global',
            'chapter': 'Boss-3',
            'difficulty': 3,
            'title': 'Test Song',
            'single_rating': 17.74,
        }]
        with (
            patch.object(utils, 'get_bot_hash_from_event', return_value='bot'),
            patch.object(utils, 'get_sender_id_from_event', return_value='42'),
            patch.object(function, 'load_user_data', return_value=memory),
            patch.object(function, 'save_user_data', return_value=True),
        ):
            self.assertTrue(score_overrides.save_overrides(event, rows))
        stored = memory['42']['lanota_score_overrides']
        self.assertEqual(stored['global']['Boss-3']['3']['single_rating'], 17.74)

    def test_comparison_uses_single_rating_not_rating_percent(self) -> None:
        chart = {
            'songId': 'test',
            'title': 'Test Song',
            'chapter': 'Boss-3',
            'difficulty': 3,
            'difficultyName': 'Master',
            'constantText': '16',
            'chartConstant': 16.0,
            'total': 1000,
            'chartSet': 'current',
            '_sourceSong': {'title': 'Test Song', 'chapter': 'Boss-3'},
        }
        calculated = b30.calculate_score_rating(1_000_000, 1000, 16.0)
        current = b30._base_entry(
            source={'songId': 'test', 'difficulty': 3},
            chart=chart,
            score=1_000_000,
            total=1000,
            constant=16.0,
            rating_data=calculated,
            exact=False,
        )
        override = {
            'region': 'global',
            'chapter': 'Boss-3',
            'song_id': 'test',
            'difficulty': 3,
            'single_rating': 17.74,
            # 即使官网 Rating% 很高，也不能代替 Single Rating 比较。
            'rating_percent': 99.99,
            'score': 981_118,
        }
        merged, remaining, stats = score_overrides.merge_into_entries(
            [current],
            [override],
            {('test', 3): chart},
            'global',
        )
        self.assertFalse(merged[0].get('override', False))
        self.assertEqual(remaining, [])
        self.assertEqual(stats, {'used': 0, 'removed': 1})

    def test_full_official_score_set_removes_lower_override(self) -> None:
        chart = {
            'songId': 'test',
            'title': 'Test Song',
            'chapter': 'Boss-3',
            'difficulty': 3,
            'difficultyName': 'Master',
            'constantText': '16',
            'chartConstant': 16.0,
            'total': 1000,
            'chartSet': 'current',
            '_sourceSong': {'title': 'Test Song', 'chapter': 'Boss-3'},
        }
        override = {
            'region': 'global',
            'chapter': 'Boss-3',
            'song_id': 'test',
            'difficulty': 3,
            'single_rating': 17.74,
            'rating_percent': 99.99,
        }
        saved = []
        with (
            patch.object(score_overrides, 'load_overrides', return_value=[override]),
            patch.object(
                score_overrides,
                'save_overrides',
                side_effect=lambda _event, rows: saved.extend(rows) or True,
            ),
        ):
            removed = score_overrides.reconcile_official_scores(
                SimpleNamespace(),
                {('test', 3): chart},
                'global',
                [{'songId': 'test', 'difficulty': 3, 'score': 1_000_000}],
                'score',
            )
        self.assertEqual(removed, 1)
        self.assertEqual(saved, [])

    def test_manual_override_infers_score_and_has_specific_warning(self) -> None:
        override = {
            'region': 'global',
            'chapter': 'Boss-3',
            'song_id': 'test',
            'difficulty': 3,
            'single_rating': 17.74,
            'source': 'manual',
        }
        merged, _remaining, stats = score_overrides.merge_into_entries(
            [],
            [override],
            {('test', 3): self._chart()},
            'global',
        )
        self.assertEqual(stats['used'], 1)
        self.assertGreater(merged[0]['score'], 0)
        self.assertGreater(merged[0]['scoreAccuracy'], 0)
        self.assertTrue(merged[0]['scoreInferred'])
        self.assertIn('手动录入仅含 Single Rating', merged[0]['warning'])

    def test_invalid_score_format_and_rating_mismatch_have_distinct_warnings(self) -> None:
        base_override = {
            'region': 'global',
            'chapter': 'Boss-3',
            'song_id': 'test',
            'difficulty': 3,
            'single_rating': 17.74,
            'source': 'portal_ocr',
        }
        cases = [
            (123_456, '无法按 4.0+ 公式校验'),
            (1_000_000, '换算 Single Rating 18.00 与录入值 17.74 不一致'),
        ]
        for score, warning_text in cases:
            with self.subTest(score=score):
                override = dict(base_override, score=score)
                merged, _remaining, stats = score_overrides.merge_into_entries(
                    [],
                    [override],
                    {('test', 3): self._chart()},
                    'global',
                )
                self.assertEqual(stats['used'], 1)
                self.assertIn(warning_text, merged[0]['warning'])

    def test_score_command_defaults_to_only_bound_china_region(self) -> None:
        event = SimpleNamespace()
        with (
            patch.object(message.portal, 'get_bound_region', return_value='china'),
            patch.object(message.score_overrides, 'add_manual', return_value=(True, 'ok')) as add_manual,
            patch.object(message, 'reply_text'),
        ):
            message.handle_score(event, 'Nemexis master 17.70')
        add_manual.assert_called_once_with(event, 'Nemexis master 17.70 china')

    def test_list_and_clear_default_to_bound_china_region(self) -> None:
        event = SimpleNamespace()
        with (
            patch.object(message.portal, 'get_bound_region', return_value='china'),
            patch.object(message.score_overrides, 'list_text', return_value='ok') as list_text,
            patch.object(message.score_overrides, 'delete', return_value='ok') as delete,
            patch.object(message, 'reply_text'),
        ):
            message.handle_score(event, 'list')
            message.handle_score(event, 'delete all')
        list_text.assert_called_once_with(event, 'china')
        delete.assert_called_once_with(event, 'all china')

    def test_help_lists_global_clear_command(self) -> None:
        self.assertIn('/la score delete all global - 清空国际服录入成绩', message.help_categories['score']['commands'])
        self.assertTrue(
            any('Portal 单曲/Rating 列表' in command for command in message.help_categories['score']['commands']),
        )

    def test_portal_rating_list_records_multiple_rows_and_keeps_highest_duplicate(self) -> None:
        songs = [
            {
                'title': 'Test Alpha',
                'chapter': 'T-1',
                'official_songid': 'test_alpha',
                'notes': {'master': 1000},
                'official_constant': {'master': 16.0},
            },
            {
                'title': 'Test Beta',
                'chapter': 'T-2',
                'official_songid': 'test_beta',
                'notes': {'master': 1000},
                'official_constant': {'master': 15.0},
            },
        ]
        text = '''Best 30
01 Test Alpha 18.00
MASTER Lv.16+
Rating 99.90%
02 Test Beta 16.50
MASTER Lv.15+
Rating 99.80%
Recent 15
01 Test Alpha 17.80
MASTER Lv.16+
Rating 98.20%'''
        records, errors, stats = score_overrides._parse_ocr_records(text, songs, 'global')
        self.assertFalse(errors)
        self.assertEqual(stats['mode'], 'portal_list')
        self.assertEqual(stats['rows'], 3)
        self.assertEqual(stats['deduplicated'], 1)
        self.assertEqual(len(records), 2)
        by_title = {record['title']: record for record in records}
        self.assertEqual(by_title['Test Alpha']['single_rating'], 18.0)
        self.assertEqual(by_title['Test Alpha']['rating_percent'], 99.9)
        self.assertEqual(by_title['Test Beta']['single_rating'], 16.5)
        self.assertTrue(all(record['score_inferred'] for record in records))

    def test_portal_rating_list_detection_accepts_one_visible_row(self) -> None:
        self.assertTrue(score_overrides._looks_like_portal_rating_list('''Best 30
Immaculate 18.27
MASTER Lv.16+
Rating 97.35%'''))

    def test_portal_rating_list_failure_reports_matched_song(self) -> None:
        songs = [
            {
                'title': 'Test Alpha',
                'chapter': 'T-1',
                'official_songid': 'test_alpha',
                'notes': {'master': 1000},
                'official_constant': {'master': 16.0},
            },
            {
                'title': 'Test Beta',
                'chapter': 'T-2',
                'official_songid': 'test_beta',
                'notes': {'master': 1000},
                'official_constant': {'master': 15.0},
            },
        ]
        text = '''Best 30
Test Alpha 18.00
MASTER Lv.16+
Rating 100.00%
Test Beta 25.00
MASTER Lv.15+
Rating 99.80%'''
        records, errors, stats = score_overrides._parse_ocr_records(text, songs, 'global')
        self.assertEqual(stats['rows'], 2)
        self.assertEqual(len(records), 1)
        self.assertIn('已匹配：Test Beta（章节号 T-2，难度 Master）', errors[0])
        self.assertIn('不可能由该谱面的 4.0+ 公式得到', errors[0])

    def test_unmatched_portal_list_row_does_not_change_neighbor_ratings(self) -> None:
        songs = [
            {
                'title': 'Test Alpha',
                'chapter': 'T-1',
                'official_songid': 'test_alpha',
                'notes': {'master': 1000},
                'official_constant': {'master': 16.0},
            },
            {
                'title': 'Test Beta',
                'chapter': 'T-2',
                'official_songid': 'test_beta',
                'notes': {'master': 1000},
                'official_constant': {'master': 15.0},
            },
        ]
        text = '''Best 30
Test Alpha 18.00
MASTER Lv.16+
Rating 100.00%
Completely Unknown Song 10.00
MASTER Lv.10
Rating 80.00%
Test Beta 16.50
MASTER Lv.15+
Rating 100.00%'''
        records, errors, stats = score_overrides._parse_ocr_records(text, songs, 'global')
        self.assertEqual(stats['rows'], 3)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(errors), 1)
        by_title = {record['title']: record for record in records}
        self.assertEqual(by_title['Test Alpha']['single_rating'], 18.0)
        self.assertEqual(by_title['Test Beta']['single_rating'], 16.5)

    def test_process_one_portal_rating_image_saves_multiple_records(self) -> None:
        songs = [
            {
                'title': 'Test Alpha',
                'chapter': 'T-1',
                'official_songid': 'test_alpha',
                'notes': {'master': 1000},
                'official_constant': {'master': 16.0},
            },
            {
                'title': 'Test Beta',
                'chapter': 'T-2',
                'official_songid': 'test_beta',
                'notes': {'master': 1000},
                'official_constant': {'master': 15.0},
            },
        ]
        text = '''Best 30
Test Alpha 18.00
MASTER Lv.16+
Rating 100.00%
Test Beta 16.50
MASTER Lv.15+
Rating 100.00%'''
        saved = []
        with (
            patch.object(score_overrides.function, 'load_song_data', return_value=songs),
            patch.object(score_overrides, 'load_overrides', return_value=[]),
            patch.object(score_overrides, '_read_image', return_value=Path('rating.png')),
            patch.object(score_overrides, '_ocr_text', return_value=text),
            patch.object(
                score_overrides,
                'save_overrides',
                side_effect=lambda _event, rows: saved.extend(rows) or True,
            ),
        ):
            added, messages = score_overrides.process_images(
                SimpleNamespace(),
                '[OP:image,file=rating.png]',
                'global',
            )
        self.assertEqual(added, 2)
        self.assertEqual({row['chapter'] for row in saved}, {'T-1', 'T-2'})
        self.assertIn('共识别 2 行，保留 2 条', '\n'.join(messages))

    def test_portal_list_does_not_replace_higher_or_validated_archive_record(self) -> None:
        rows = [{
            'region': 'global',
            'chapter': 'T-1',
            'difficulty': 3,
            'single_rating': 18.0,
            'score': 1_000_000,
        }]
        lower = {
            'region': 'global',
            'chapter': 'T-1',
            'difficulty': 3,
            'single_rating': 17.8,
            'score': None,
        }
        same_inferred = dict(lower, single_rating=18.0)
        self.assertEqual(score_overrides._upsert_ocr_record(rows, lower), (False, 'kept_higher'))
        self.assertEqual(
            score_overrides._upsert_ocr_record(rows, same_inferred),
            (False, 'kept_validated'),
        )
        self.assertEqual(rows[0]['score'], 1_000_000)

    def test_score_only_game_result_is_accepted_and_bad_score_is_rejected(self) -> None:
        songs = function.load_song_data()
        valid_text = '\n'.join(['MONONOKE', 'seatrus', 'MASIER', '0999584', 'Rank', '判定详情'])
        record, error = score_overrides._parse_ocr(valid_text, songs, 'global')
        self.assertFalse(error)
        self.assertEqual(record['title'], 'MONONOKE')
        self.assertEqual(record['score'], 999_584)
        self.assertEqual(record['validation_status'], 'game_score_validated')
        self.assertNotIn('harmony', record)

        invalid_text = valid_text.replace('0999584', '0999583')
        record, error = score_overrides._parse_ocr(invalid_text, songs, 'global')
        self.assertIsNone(record)
        self.assertIn('已匹配：MONONOKE（章节号 Inf-105，难度 Master）', error)
        self.assertIn('无法按该谱面的 4.0+ 整数公式还原', error)

    def test_portal_ocr_failure_reports_matched_song_and_chart(self) -> None:
        text = '\n'.join([
            'Lanota',
            'Apotheosis (Lanota Edit)',
            'MASTER',
            '单曲 RATING',
            '25.00',
        ])
        record, error = score_overrides._parse_ocr(text, function.load_song_data(), 'global')
        self.assertIsNone(record)
        self.assertIn(
            '已匹配：Apotheosis (Lanota Edit)（章节号 Event-110，难度 Master）',
            error,
        )
        self.assertIn('不可能由该谱面的 4.0+ 公式得到', error)

    def test_expanded_game_result_rejects_score_mismatch(self) -> None:
        text = '''[[LANOTA_OCR_FULL]]
Nemexis
MASTER
0993281
[[LANOTA_OCR_JUDGEMENTS]]
2208
20
5
98%
1%
1%
Harmony
Tune
Fail
534 / 2233'''
        record, error = score_overrides._parse_ocr(text, function.load_song_data(), 'global')
        self.assertIsNone(record)
        self.assertIn('已匹配：Nemexis（章节号 8-5，难度 Master）', error)
        self.assertIn('按 H/T/F 应为 0993282', error)


@unittest.skipUnless(
    importlib.util.find_spec('rapidocr_onnxruntime') and importlib.util.find_spec('onnxruntime'),
    '需要安装 RapidOCR 与 ONNXRuntime 才能运行列表图回归',
)
class RapidOCRPortalRatingListScreenshotTest(unittest.TestCase):
    def test_new_portal_rating_list_screenshots(self) -> None:
        plugin_dir = Path(__file__).resolve().parents[1]
        fixtures = {
            '80351d682a60bf3005f5df046c15abba.jpg': 30,
            '941f745d493cead9759efaa5076af3ef.jpg': 20,
            '9519f6933e99f0aba5fe4e9fd7e8d152.png': 10,
            'a72f9b06ac433de066aae6f6154178aa.png': 31,
        }
        songs = function.load_song_data()
        for file_name, expected_count in fixtures.items():
            with self.subTest(file_name=file_name):
                image_path = plugin_dir / file_name
                self.assertTrue(image_path.is_file(), f'缺少用户新增回归截图：{image_path}')
                text = score_overrides._ocr_text(image_path)
                records, errors, stats = score_overrides._parse_ocr_records(text, songs, 'global')
                self.assertEqual(stats['mode'], 'portal_list')
                self.assertEqual(len(records), expected_count)
                self.assertFalse(errors)
                self.assertTrue(all(record.get('chapter') for record in records))
                self.assertTrue(all(record.get('difficulty_name') for record in records))
                self.assertTrue(all(record.get('single_rating') for record in records))
                if file_name == 'a72f9b06ac433de066aae6f6154178aa.png':
                    by_title = {record['title']: record for record in records}
                    self.assertIn('Fortuna', by_title)
                    self.assertIn('GHOST VS. GHOUL MASHUP', by_title)
                else:
                    self.assertTrue(all(record.get('rating_percent') is not None for record in records))


@unittest.skipUnless(
    importlib.util.find_spec('paddleocr') and importlib.util.find_spec('paddle'),
    '需要安装 PaddleOCR 与 PaddlePaddle 才能运行实图回归',
)
class PaddleOCRPortalScreenshotTest(unittest.TestCase):
    def test_desktop_tablet_and_mobile_screenshots(self) -> None:
        fixtures = {
            'portal_score_desktop_wolves.png': {
                'title': 'Wolves Standing Towards Enemies',
                'chapter': '6-7',
                'single_rating': 17.74,
                'rating_percent': 98.60,
                'score': 981_118,
            },
            'portal_score_tablet_immaculate.png': {
                'title': 'Immaculate',
                'chapter': '8-8',
                'single_rating': 18.18,
                'rating_percent': 96.96,
                'score': 975_564,
            },
            'portal_score_mobile_nightfall.png': {
                'title': 'The Nightfall will be Conceal Everything Before Long.',
                'chapter': 'Event-40',
                'single_rating': 17.70,
                'rating_percent': 98.37,
                'score': 962_085,
            },
        }
        songs = function.load_song_data()
        for file_name, expected in fixtures.items():
            with self.subTest(file_name=file_name):
                image_path = FIXTURE_DIR / file_name
                self.assertTrue(image_path.is_file(), f'缺少回归截图：{image_path}')
                ocr_text = score_overrides._ocr_text(image_path)
                record, error = score_overrides._parse_ocr(
                    ocr_text,
                    songs,
                    'global',
                )
                self.assertFalse(error)
                self.assertIsNotNone(record)
                self.assertEqual(record['title'], expected['title'])
                self.assertEqual(record['chapter'], expected['chapter'])
                self.assertEqual(record['difficulty'], 3)
                self.assertEqual(record['difficulty_name'], 'Master')
                self.assertAlmostEqual(record['single_rating'], expected['single_rating'], places=2)
                self.assertAlmostEqual(record['rating_percent'], expected['rating_percent'], places=2)
                self.assertEqual(record['score'], expected['score'])

    def test_game_result_screenshots(self) -> None:
        fixtures = {
            'game_result_erasure_valid.jpg': {
                'title': 'Erasure: A World Without You',
                'chapter': 'Event-107',
                'score': 978_748,
                'judgements': (2449, 76, 16),
            },
            'game_result_mononoke_score_only_valid.jpg': {
                'title': 'MONONOKE',
                'chapter': 'Inf-105',
                'score': 999_584,
                'judgements': None,
            },
            'game_result_thank_you_mrs_nory_valid.jpeg': {
                'title': 'Thank You, Mrs. Nory',
                'chapter': 'Inf-368',
                'score': 969_072,
                'judgements': (1566, 64, 19),
            },
            'game_result_nemexis_valid.jpg': {
                'title': 'Nemexis',
                'chapter': '8-5',
                'score': 993_282,
                'judgements': (2208, 20, 5),
            },
            'game_result_ave_mary_sue_valid.jpeg': {
                'title': 'Ave Mary Sue',
                'chapter': 'Inf-387',
                'score': 999_155,
                'judgements': (1183, 0, 1),
            },
        }
        songs = function.load_song_data()
        for file_name, expected in fixtures.items():
            with self.subTest(file_name=file_name):
                image_path = FIXTURE_DIR / file_name
                self.assertTrue(image_path.is_file(), f'缺少回归截图：{image_path}')
                ocr_text = score_overrides._ocr_text(image_path)
                record, error = score_overrides._parse_ocr(ocr_text, songs, 'global')
                self.assertFalse(error)
                self.assertIsNotNone(record)
                self.assertEqual(record['title'], expected['title'])
                self.assertEqual(record['chapter'], expected['chapter'])
                self.assertEqual(record['difficulty'], 3)
                self.assertEqual(record['score'], expected['score'])
                self.assertGreater(record['score_accuracy'], 0)
                self.assertGreater(record['single_rating'], 0)
                if expected['judgements'] is None:
                    self.assertEqual(record['validation_status'], 'game_score_validated')
                    self.assertNotIn('harmony', record)
                else:
                    self.assertEqual(record['validation_status'], 'game_judgement_validated')
                    self.assertEqual(
                        (record['harmony'], record['tune'], record['fail']),
                        expected['judgements'],
                    )


if __name__ == '__main__':
    unittest.main()
