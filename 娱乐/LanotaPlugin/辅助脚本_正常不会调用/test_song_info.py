# -*- encoding: utf-8 -*-
"""歌曲卡片、绑定区域和单曲查分的离线回归测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_PARENT))

from LanotaPlugin import message  # noqa: E402
from LanotaPlugin import portal  # noqa: E402


class SongInfoTest(unittest.TestCase):
    def setUp(self) -> None:
        portal.compare_cache.clear()

    def test_song_and_info_are_separate_commands(self) -> None:
        self.assertEqual(message.match_command('la song Frey'), ('song', 'Frey'))
        self.assertEqual(message.match_command('la find Frey'), ('song', 'Frey'))
        self.assertEqual(message.match_command('la info Frey'), ('info', 'Frey'))
        self.assertEqual(message.match_command('la info cn Frey'), ('info', 'cn Frey'))

    def test_compact_constant_format(self) -> None:
        self.assertEqual(
            message.function.format_compact_chart_constant(15.3, 15.4, '15'),
            '15.3(15.4)',
        )
        self.assertEqual(
            message.function.format_compact_chart_constant(15.3, None, '15'),
            '15.3',
        )
        self.assertEqual(
            message.function.format_compact_chart_constant(15.3, '15.8-15.9', '15'),
            '15.3(15.8-15.9)',
        )
        self.assertEqual(
            message.function.format_compact_chart_constant(15.5, 15.6, '15+'),
            '15+.5(15.6)',
        )

    def test_info_china_token_error_adds_admin_hint_to_cached_card(self) -> None:
        event = object()
        song = {'id': 1, 'title': 'Song', 'official_songid': 'song'}
        compare_data = {'_portal_region': 'china', 'friend': {'username': 'Player'}, 'songs': []}
        with (
            patch.object(
                message.portal,
                'get_compare_data_cached',
                return_value=(compare_data, 'NANO', PermissionError('国服 Portal 登录已失效。')),
            ),
            patch.object(message, 'reply_song_card') as reply_song_card,
        ):
            message.reply_song_info(event, song, region='china')
        self.assertIn('.la china login', reply_song_card.call_args.kwargs['notice'])

    def test_info_global_invalid_credentials_returns_admin_hint(self) -> None:
        event = object()
        song = {'id': 1, 'title': 'Song', 'official_songid': 'song'}
        with (
            patch.object(
                message.portal,
                'get_compare_data_cached',
                side_effect=PermissionError('Lanota Portal 登录账号或密码不正确。'),
            ),
            patch.object(message, 'reply_text') as reply_text,
        ):
            message.reply_song_info(event, song, region='global')
        self.assertIn('检查登录账号或密码配置', reply_text.call_args.args[1])

    def test_user_china_token_error_keeps_admin_hint(self) -> None:
        event = object()
        with (
            patch.object(
                message.portal,
                'get_user_data_cached',
                side_effect=PermissionError('国服 Portal 登录已失效。'),
            ),
            patch.object(message, 'reply_text') as reply_text,
        ):
            message.handle_user(event, 'cn')
        self.assertIn('.la china login', reply_text.call_args.args[1])

    def test_normal_network_error_has_no_credential_hint(self) -> None:
        self.assertEqual(
            message.portal.credential_error_hint(TimeoutError('请求超时'), 'global'),
            '',
        )

    def test_default_bound_region_prefers_global(self) -> None:
        with patch.object(
            portal,
            'get_bound_nano_id',
            side_effect=lambda _event, region: 'GLOBAL' if region == 'global' else 'CHINA',
        ):
            self.assertEqual(portal.get_bound_region(object()), 'global')

    def test_default_bound_region_falls_back_to_china(self) -> None:
        with patch.object(
            portal,
            'get_bound_nano_id',
            side_effect=lambda _event, region: 'CHINA' if region == 'china' else '',
        ):
            self.assertEqual(portal.get_bound_region(object()), 'china')

    def test_compare_scores_match_official_song_id(self) -> None:
        data = {
            'songs': [
                {
                    'songId': 'frey',
                    'difficulty': 0,
                    'friendScore': 0,
                    'friendClear': 'Failed',
                    'friendRank': 'D',
                },
                {
                    'songId': 'frey',
                    'difficulty': 1,
                    'friendScore': None,
                    'friendClear': None,
                    'friendRank': None,
                },
                {
                    'songId': 'other',
                    'difficulty': 3,
                    'friendScore': 1000000,
                    'friendClear': 'Perfect Purified',
                    'friendRank': 'L',
                },
            ]
        }
        rows = portal.find_compare_song_scores(data, 'FREY')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['difficulty'], 0)
        self.assertEqual(rows[0]['score'], 0)
        self.assertEqual(rows[0]['chartSet'], 'current')

    def test_numeric_clear_is_rendered_with_portal_name(self) -> None:
        data = {
            'songs': [
                {
                    'songId': 'legacy_song',
                    'difficulty': 3,
                    'friendScore': 999000,
                    'friendClear': 5,
                    'friendRank': 'L',
                }
            ]
        }
        rows = portal.find_compare_song_scores(data, 'legacy_song', chart_set='legacy')
        self.assertEqual(rows[0]['chartSet'], 'legacy')
        self.assertEqual(rows[0]['clear'], 'Perfect Purified')

    def test_info_cn_keeps_explicit_region(self) -> None:
        song = {'id': 1, 'title': 'Frey', 'official_songid': 'frey'}
        event = object()
        with (
            patch.object(message.function, 'load_song_data', return_value=[song]),
            patch.object(message.function, 'load_alias_data', return_value={}),
            patch.object(
                message.function,
                'find_song_by_search_term',
                return_value=([song], '原名匹配', 1),
            ),
            patch.object(message, 'clear_search_session'),
            patch.object(message, 'reply_song_info') as reply_song_info,
        ):
            message.handle_info(event, 'cn Frey')
        reply_song_info.assert_called_once_with(event, song, region='china')

    def test_info_queries_current_and_legacy_scores(self) -> None:
        event = object()
        song = {
            'id': 1,
            'title': 'Song',
            'official_songid': 'song_new',
            'Legacy': {'official_songid': 'song'},
        }
        compare_data = {
            '_portal_region': 'global',
            'friend': {'username': 'Player', 'rating': 10, 'avatarId': 'av_default'},
            'songs': [
                {
                    'songId': 'song_new',
                    'difficulty': 3,
                    'friendScore': 900000,
                    'friendClear': 2,
                    'friendRank': 'A',
                },
                {
                    'songId': 'song',
                    'difficulty': 3,
                    'friendScore': 980000,
                    'friendClear': 4,
                    'friendRank': 'L',
                },
            ],
        }
        with (
            patch.object(
                message.portal,
                'get_compare_data_cached',
                return_value=(compare_data, 'NANO', None),
            ),
            patch.object(message, 'reply_song_card') as reply_song_card,
        ):
            message.reply_song_info(event, song)
        score_rows = reply_song_card.call_args.kwargs['score_rows']
        self.assertEqual({row['chartSet'] for row in score_rows}, {'current', 'legacy'})

    def test_song_template_keeps_song_data_nested(self) -> None:
        html = portal._template_html(
            {
                '_portal_region': 'china',
                'song': {'title': 'Frey'},
                'infoMode': False,
                'player': {},
                'scores': [],
                'notice': '',
            },
            'song',
        )
        self.assertIn('"song":{"title":"Frey"}', html)
        self.assertIn('"portalRegionName":"国服"', html)
        self.assertIn('GMZON LANOTA PORTAL', html)


if __name__ == '__main__':
    unittest.main()
