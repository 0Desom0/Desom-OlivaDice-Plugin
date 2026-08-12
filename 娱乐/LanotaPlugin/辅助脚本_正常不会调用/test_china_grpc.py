# -*- encoding: utf-8 -*-
"""国服 Portal 备用 gRPC 适配层离线回归测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_PARENT))

from LanotaPlugin import china_grpc  # noqa: E402
from LanotaPlugin import message  # noqa: E402
from LanotaPlugin import portal  # noqa: E402


SEARCH_RESPONSE = bytes.fromhex(
    '0a260a0d386b784a353773725934395754120a5269746d6f393532363725ae47e13f280230b19173'
)
RECORD_RESPONSE = bytes.fromhex(
    '0a0f0a05706f70707910021889fd3a20030a0f0a05706f707079100318a894382003'
)


class ChinaGrpcTest(unittest.TestCase):
    def setUp(self) -> None:
        portal.compare_cache.clear()

    def test_search_player_wire_response(self) -> None:
        profiles = china_grpc._parse_search_response(SEARCH_RESPONSE)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]['nanoId'], '8kxJ57srY49WT')
        self.assertEqual(profiles[0]['username'], 'Ritmo95267')
        self.assertAlmostEqual(profiles[0]['rating'], 1.76, places=2)
        self.assertEqual(profiles[0]['notalium'], 2)
        self.assertEqual(profiles[0]['totalScore'], 1_886_385)

    def test_song_record_wire_response(self) -> None:
        records = china_grpc._parse_record_response(RECORD_RESPONSE)
        self.assertEqual(records, [
            {'songId': 'poppy', 'difficulty': 2, 'score': 966_281, 'clear': 3},
            {'songId': 'poppy', 'difficulty': 3, 'score': 920_104, 'clear': 3},
        ])

    def test_fallback_player_rounds_rating_and_marks_missing_stats(self) -> None:
        profile = china_grpc._parse_search_response(SEARCH_RESPONSE)[0]
        records = china_grpc._parse_record_response(RECORD_RESPONSE)
        data = china_grpc._build_player_data(profile, records, records_available=True)
        self.assertEqual(data['player']['rating'], 1.76)
        self.assertEqual(data['stats']['rankCounts']['L'], 0)
        self.assertEqual(data['stats']['rankCounts']['S'], 1)
        self.assertEqual(data['stats']['rankCounts']['A'], 1)
        self.assertEqual(data['stats']['totalCharts'], '暂无法获取')

    def test_fallback_info_marks_missing_rank(self) -> None:
        compare_data = {
            '_api_fallback': True,
            'songs': [{
                'songId': 'poppy',
                'difficulty': 3,
                'friendScore': 920_104,
                'friendClear': 3,
                'friendRank': None,
            }],
        }
        rows = portal.find_compare_song_scores(compare_data, 'poppy')
        self.assertEqual(rows[0]['rank'], '暂无法获取')

    def test_rank_is_derived_from_score(self) -> None:
        self.assertEqual(china_grpc.rank_from_score(1_000_000), 'L')
        self.assertEqual(china_grpc.rank_from_score(980_000), 'L')
        self.assertEqual(china_grpc.rank_from_score(979_999), 'S')
        self.assertEqual(china_grpc.rank_from_score(950_000), 'S')
        self.assertEqual(china_grpc.rank_from_score(949_999), 'A')
        self.assertEqual(china_grpc.rank_from_score(900_000), 'A')
        self.assertEqual(china_grpc.rank_from_score(899_999), 'B')
        self.assertEqual(china_grpc.rank_from_score(700_000), 'B')
        self.assertEqual(china_grpc.rank_from_score(699_999), 'C')
        self.assertEqual(china_grpc.rank_from_score(600_000), 'C')
        self.assertEqual(china_grpc.rank_from_score(599_999), 'D')
        self.assertIsNone(china_grpc.rank_from_score(1_000_001))

    def test_player_query_falls_back_after_portal_failure(self) -> None:
        fallback_data = {
            '_api_fallback': True,
            '_api_fallback_notice': portal.CHINA_FALLBACK_NOTICE,
            'player': {'nanoId': 'NANO', 'username': 'Player'},
            'stats': {},
        }
        with (
            patch.object(portal, 'api_get', side_effect=PermissionError('Token expired')),
            patch.object(portal.china_grpc, 'get_player', return_value=fallback_data) as get_player,
        ):
            result = portal.get_player('NANO', region='china')
        get_player.assert_called_once()
        self.assertTrue(result['_api_fallback'])
        self.assertIn('备用 API', portal.fallback_notice(result))

    def test_portal_not_found_and_fallback_unavailable_is_validation_failure(self) -> None:
        with (
            patch.object(portal, 'api_get', side_effect=LookupError('Portal not found')),
            patch.object(portal.china_grpc, 'get_player', side_effect=RuntimeError('gRPC offline')),
        ):
            with self.assertRaisesRegex(LookupError, '验证失败：没有找到对应玩家'):
                portal.get_player('MISSING', region='china')

    def test_portal_unavailable_and_fallback_not_found_is_validation_failure(self) -> None:
        with (
            patch.object(portal, 'api_get', side_effect=PermissionError('Token expired')),
            patch.object(
                portal.china_grpc,
                'get_player',
                side_effect=china_grpc.ChinaPlayerNotFoundError('not found'),
            ),
        ):
            with self.assertRaisesRegex(LookupError, '验证失败：没有找到对应玩家'):
                portal.get_player('MISSING', region='china')

    def test_portal_not_found_but_fallback_success_still_binds(self) -> None:
        fallback_data = {
            '_api_fallback': True,
            'player': {'nanoId': 'NANO', 'username': 'Player'},
            'stats': {},
        }
        with (
            patch.object(portal, 'api_get', side_effect=LookupError('Portal not found')),
            patch.object(portal.china_grpc, 'get_player', return_value=fallback_data),
        ):
            result = portal.get_player('NANO', region='china')
        self.assertEqual(result['player']['username'], 'Player')

    def test_bind_formats_not_found_and_double_unavailable(self) -> None:
        with patch.object(portal, 'get_player', side_effect=LookupError('not found')):
            success, text = portal.bind_nano_id(object(), 'MISSING', region='china')
        self.assertFalse(success)
        self.assertEqual(text, '验证失败：没有找到对应玩家。')

        unavailable = portal.ChinaApiUnavailableError(
            PermissionError('Token expired'),
            RuntimeError('gRPC offline'),
        )
        with patch.object(portal, 'get_player', side_effect=unavailable):
            success, text = portal.bind_nano_id(object(), 'NANO', region='china')
        self.assertFalse(success)
        self.assertEqual(text, '国服主力 API 与备用 API 均不可用，请联系管理员更新 Token。')

    def test_compare_query_falls_back_after_portal_failure(self) -> None:
        fallback_data = {
            '_api_fallback': True,
            '_api_fallback_notice': portal.CHINA_FALLBACK_NOTICE,
            'friend': {'nanoId': 'NANO', 'username': 'Player'},
            'songs': [{'songId': 'poppy', 'difficulty': 3, 'friendScore': 920_104}],
        }
        with (
            patch.object(portal, 'get_bound_region', return_value='china'),
            patch.object(portal, 'get_bound_nano_id', return_value='NANO'),
            patch.object(portal, 'api_get', side_effect=PermissionError('Token expired')),
            patch.object(portal.china_grpc, 'get_compare', return_value=fallback_data),
        ):
            result, nano_id, cache_error = portal.get_compare_data_cached(object(), 'china')
        self.assertEqual(nano_id, 'NANO')
        self.assertIsNone(cache_error)
        self.assertEqual(result['songs'][0]['friendScore'], 920_104)

    def test_both_apis_failed_returns_combined_error(self) -> None:
        with (
            patch.object(portal, 'api_get', side_effect=PermissionError('Token expired')),
            patch.object(portal.china_grpc, 'get_player', side_effect=RuntimeError('gRPC offline')),
        ):
            with self.assertRaises(portal.ChinaApiUnavailableError) as raised:
                portal.get_player('NANO', region='china')
        self.assertIn('主力 API 与备用 API 均不可用', str(raised.exception))
        self.assertIn('更新 Token', portal.credential_error_hint(raised.exception, 'china'))

    def test_login_commands_are_not_exposed(self) -> None:
        self.assertEqual(message.match_command('la china login'), ('help', ''))
        help_text = '\n'.join(
            command
            for category in message.help_categories.values()
            for command in category.get('commands', []) + category.get('examples', [])
        )
        self.assertNotIn('china login', help_text.casefold())
        self.assertNotIn('china status', help_text.casefold())


if __name__ == '__main__':
    unittest.main()
