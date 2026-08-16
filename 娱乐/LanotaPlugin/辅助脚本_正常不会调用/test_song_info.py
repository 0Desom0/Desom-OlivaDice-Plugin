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
        self.assertEqual(message.match_command('la find Frey'), ('help', ''))
        self.assertEqual(message.match_command('la info Frey'), ('info', 'Frey'))
        self.assertEqual(message.match_command('la info cn Frey'), ('info', 'cn Frey'))
        self.assertEqual(message.match_command('la infocnFrey'), ('info', 'cnFrey'))
        self.assertEqual(message.match_command('la bindcnNANO'), ('bind', 'cnNANO'))
        self.assertEqual(message.match_command('la friendcn'), ('friend', 'cn'))

    def test_fuzzy_song_search_keeps_only_close_best_matches(self) -> None:
        matched, match_type, total_count = message.function.find_song_by_search_term(
            'apoptheosis',
            message.function.load_song_data(),
            {},
            1000,
        )
        self.assertEqual(match_type, '打分制模糊搜索')
        self.assertEqual(total_count, 1)
        self.assertEqual(matched[0]['title'], 'Apotheosis (Lanota Edit)')

    def test_alias_add_uses_exact_target_without_search_session(self) -> None:
        event = object()
        alias_data = {}
        songs = [{
            'id': 706,
            'chapter': 'Event-110',
            'official_songid': 'apotheosis_lanota_edit',
            'title': 'Apotheosis (Lanota Edit)',
        }]
        with (
            patch.object(message.utils, 'is_alias_group_allowed', return_value=True),
            patch.object(message.function, 'load_alias_data', return_value=alias_data),
            patch.object(message.function, 'load_song_data', return_value=songs),
            patch.object(message.function, 'save_alias_data') as save_alias_data,
            patch.object(message, 'save_search_session') as save_search_session,
            patch.object(message, 'reply_text') as reply_text,
        ):
            message.handle_alias(event, 'add Apotheosis/Apotheosis(Lanota Edit)')
        save_alias_data.assert_called_once_with({
            'Apotheosis (Lanota Edit)': ['Apotheosis'],
        })
        save_search_session.assert_not_called()
        self.assertIn('成功为[Apotheosis (Lanota Edit)]添加别名', reply_text.call_args.args[1])

    def test_region_argument_greedy_matching_is_opt_in(self) -> None:
        self.assertEqual(portal.split_region_argument('cnFrey'), (None, 'cnFrey'))
        self.assertEqual(portal.split_region_argument('cnFrey', greedy=True), ('china', 'Frey'))
        self.assertEqual(portal.split_region_argument('globalFrey', greedy=True), ('global', 'Frey'))

    def test_bind_greedily_extracts_china_region(self) -> None:
        event = object()
        with (
            patch.object(message.portal, 'bind_nano_id', return_value=(True, 'ok')) as bind_nano_id,
            patch.object(message.utils, 'reply_message'),
        ):
            message.handle_bind(event, 'cnNANO')
        bind_nano_id.assert_called_once_with(event, 'NANO', region='china')

    def test_bind_does_not_prefix_classified_china_failures(self) -> None:
        event = object()
        with (
            patch.object(
                message.portal,
                'bind_nano_id',
                return_value=(False, '验证失败：没有找到对应玩家。'),
            ),
            patch.object(message.utils, 'reply_message') as reply_message,
        ):
            message.handle_bind(event, 'cn MISSING')
        self.assertEqual(reply_message.call_args_list[-1].args[1], '验证失败：没有找到对应玩家。')

    def test_friend_greedily_extracts_china_region(self) -> None:
        event = object()
        with (
            patch.object(
                message.portal,
                'get_bound_nano_id',
                side_effect=lambda _event, region: 'CHINA-ID' if region == 'china' else '',
            ) as get_bound_nano_id,
            patch.object(message.utils, 'get_group_id_from_event', return_value=''),
            patch.object(message.utils, 'reply_message') as reply_message,
        ):
            message.handle_friend(event, 'cn')
        get_bound_nano_id.assert_called_once_with(event, 'china')
        self.assertIn('CHINA-ID', reply_message.call_args.args[1])

    def test_unknown_la_subcommand_opens_help(self) -> None:
        self.assertEqual(message.match_command('la Frey'), ('help', ''))
        self.assertEqual(message.match_command('la unknown-command'), ('help', ''))

    def test_account_help_is_separate_from_other_commands(self) -> None:
        account_commands = '\n'.join(message.help_categories['account']['commands'])
        other_commands = '\n'.join(message.help_categories['stats']['commands'])
        self.assertIn('/la bind', account_commands)
        self.assertIn('/la user', account_commands)
        self.assertNotIn('/la bind', other_commands)
        self.assertNotIn('/la user', other_commands)

    def test_table_help_documents_excel_json_conversion_and_permission(self) -> None:
        table_help = message.help_categories['table']
        help_text = '\n'.join([*table_help['commands'], *table_help['priority']])
        self.assertIn('/la table update', help_text)
        self.assertIn('Excel', help_text)
        self.assertIn('plugin/data/LanotaPlugin/excel_table/', help_text)
        self.assertIn('plugin/data/LanotaPlugin/SongList/song_table.json', help_text)
        self.assertIn('仅 OlivaDiceCore 骰主或本插件配置管理员', help_text)

    def test_table_update_requires_master_permission(self) -> None:
        event = object()
        with (
            patch.object(message.utils, 'sender_has_master_permission', return_value=False),
            patch.object(message.function, 'import_excel_table_to_song_table') as import_table,
            patch.object(message, 'reply_text') as reply_text,
        ):
            message.handle_table(event, 'update')
        import_table.assert_not_called()
        self.assertIn('权限不足', reply_text.call_args.args[1])

    def test_table_update_allows_master_permission(self) -> None:
        event = object()
        with (
            patch.object(message.utils, 'sender_has_master_permission', return_value=True),
            patch.object(
                message.function,
                'import_excel_table_to_song_table',
                return_value=(True, 'Excel 定数表转换完成。'),
            ) as import_table,
            patch.object(message, 'reply_text') as reply_text,
        ):
            message.handle_table(event, 'update')
        import_table.assert_called_once_with()
        reply_text.assert_called_once_with(event, 'Excel 定数表转换完成。')

    def test_search_image_wrap_uses_proportional_character_count(self) -> None:
        source = '1. Event - ThisIsAnExtremelyLongUnbrokenSongTitleForWrapping (ID: 123)'
        lines = message.function.wrap_text(source, max_chars=message.config.search_image_max_chars)
        self.assertTrue(lines)
        self.assertEqual(message.function.get_text_display_length('abc'), 1)
        self.assertEqual(message.function.get_text_display_length('abcdef'), 2)
        self.assertTrue(
            all(
                message.function.get_text_display_length(line) <= message.config.search_image_max_chars
                for line in lines
            )
        )
        self.assertTrue(any(len(line) > message.config.search_image_max_chars for line in lines))

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
        self.assertIn('更新 Token', reply_song_card.call_args.kwargs['notice'])

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
        self.assertIn('更新 Token', reply_text.call_args.args[1])

    def test_user_command_sends_querying_notice_first(self) -> None:
        event = object()
        player_data = {'_portal_region': 'global', 'player': {}}
        with (
            patch.object(message.portal, 'get_user_data_cached', return_value=(player_data, 'NANO', None)),
            patch.object(message.portal, 'render_player_card', return_value=None),
            patch.object(message.portal, 'build_fallback_text', return_value='fallback'),
            patch.object(message.portal, 'render_status_text', return_value='ready'),
            patch.object(message.utils, 'reply_message') as reply_message,
            patch.object(message, 'reply_text'),
        ):
            message.handle_user(event, '')
        reply_message.assert_called_once_with(event, '正在查询中，请稍等。')

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
            patch.object(message, '_prepare_song_for_query', return_value=(song, '')),
            patch.object(message, 'reply_song_info') as reply_song_info,
        ):
            message.handle_info(event, 'cn Frey')
        reply_song_info.assert_called_once_with(
            event,
            song,
            region='china',
            notice_prefix='',
        )

    def test_info_prepares_missing_official_fields_before_query(self) -> None:
        song = {'id': 1, 'title': 'Frey', 'chapter': '1-1'}
        updated_song = {
            **song,
            'official_songid': 'frey',
            'official_constant': {
                'whisper': 6.0,
                'acoustic': 8.0,
                'ultra': 12.0,
                'master': 15.0,
            },
        }
        with (
            patch.object(message.function, 'load_song_data', return_value=[song]),
            patch.object(
                message.crawler,
                'ensure_official_catalog_fields',
                return_value=(
                    [updated_song],
                    {'attempted': True, 'changed': True, 'persisted': True, 'error': ''},
                ),
            ) as ensure_fields,
        ):
            result, notice = message._prepare_song_for_query(song)

        ensure_fields.assert_called_once_with([song])
        self.assertEqual(result['official_songid'], 'frey')
        self.assertIn('补全', notice)

    def test_info_queries_current_and_legacy_scores(self) -> None:
        event = object()
        song = {
            'id': 1,
            'title': 'Song',
            'official_songid': 'song_new',
            'notes': {'master': 1000},
            'official_constant': {'master': 16.0},
            'Legacy': {
                'official_songid': 'song',
                'MaxMaster': 1000,
                'official_constant': {'master': 15.0},
            },
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
        self.assertTrue(all(row['scoreRatingValid'] for row in score_rows))
        self.assertTrue(all(row['singleRating'] > 0 for row in score_rows))
        self.assertTrue(all(row['ratingPercent'] > 0 for row in score_rows))
        self.assertTrue(all(row['scoreAccuracy'] > 0 for row in score_rows))

    def test_info_skips_rating_for_score_outside_4_0_integer_formula(self) -> None:
        rows = message._add_calculated_info_ratings(
            {
                'notes': {'master': 1000},
                'official_constant': {'master': 16.0},
            },
            [{
                'chartSet': 'current',
                'difficulty': 3,
                'score': 900_001,
            }],
        )
        self.assertFalse(rows[0]['scoreRatingValid'])
        self.assertNotIn('scoreAccuracy', rows[0])

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
        self.assertIn('GMZON LANOTA', html)
        self.assertNotIn('GMZON LANOTA PORTAL', html)
        self.assertIn('!row.override && row.scoreRatingValid', html)


if __name__ == '__main__':
    unittest.main()
