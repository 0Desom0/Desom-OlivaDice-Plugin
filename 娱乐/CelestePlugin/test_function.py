# -*- encoding: utf-8 -*-
"""CelestePlugin 纯业务逻辑测试。"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from CelestePlugin import function  # noqa: E402
from CelestePlugin import message  # noqa: E402
from CelestePlugin import utils  # noqa: E402


class CelestePluginFunctionTest(unittest.TestCase):
    def test_greedy_root_and_subcommand(self):
        root = utils.parse_command('.clstrandom5', prefix_list=['.', '。', '/'], command_name='clst')
        self.assertTrue(root['is_command'])
        self.assertEqual(root['command_argument'], 'random5')
        command, argument = message.parse_subcommand(root['command_argument'])
        self.assertEqual(command, 'random')
        self.assertEqual(argument, '5')

    def test_plain_number_uses_title_search(self):
        search_result = {'ok': True, 'results': [], 'count': 0, 'error': ''}
        with (
            mock.patch.object(message.function, 'search_title', return_value=search_result) as search_mock,
            mock.patch.object(message, 'reply_search_result') as reply_mock,
            mock.patch.object(message, 'handle_id') as id_mock,
        ):
            message.dispatch_clst_command(object(), '2020')
        search_mock.assert_called_once_with('2020')
        reply_mock.assert_called_once()
        id_mock.assert_not_called()

    def test_explicit_id_uses_exact_lookup(self):
        plugin_event = object()
        with mock.patch.object(message, 'handle_id') as id_mock:
            message.dispatch_clst_command(plugin_event, 'id424541')
        id_mock.assert_called_once_with(plugin_event, '424541')

    def test_download_mirror_urls(self):
        urls = function.get_download_urls(1414214)
        self.assertEqual(urls['gamebanana'], 'https://gamebanana.com/dl/1414214')
        self.assertIn('/gamebanana-files/1414214', urls['wegfan'])
        self.assertTrue(urls['0x0ade'].endswith('/1414214.zip'))

    def test_group_updater_components(self):
        components = [
            {
                'InternalName': 'Main',
                'Version': '1.2.0',
                'GameBananaFileId': 123,
                'LastUpdate': 20,
            },
            {
                'InternalName': 'Helper',
                'Version': '2.0.0',
                'GameBananaFileId': 123,
                'LastUpdate': 20,
            },
        ]
        groups = function.group_updater_components(components)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['components'], ['Main', 'Helper'])
        self.assertEqual(groups[0]['versions'], ['1.2.0', '2.0.0'])

    def test_community_file_id_from_url(self):
        file_item = function.normalize_file({'URL': 'https://gamebanana.com/dl/1414214', 'Name': 'map.zip'})
        self.assertEqual(file_item['id'], 1414214)

    def test_profile_root_category_and_game(self):
        profile = function.normalize_profile(
            {
                '_sName': 'Helper',
                '_aCategory': {'_sName': 'Helpers'},
                '_aSuperCategory': None,
                '_aGame': {'_idRow': 6460},
                '_aPreviewMedia': {
                    '_aImages': [
                        {
                            '_sBaseUrl': 'https://images.gamebanana.com/img/ss/mods',
                            '_sFile': 'cover.jpg',
                        }
                    ]
                },
            },
            'Mod',
            1,
        )
        self.assertEqual(profile['category'], 'Helpers')
        self.assertEqual(profile['subcategory'], '')
        self.assertEqual(profile['game_id'], 6460)
        self.assertEqual(profile['cover_url'], 'https://images.gamebanana.com/img/ss/mods/cover.jpg')

    def test_cover_priority_wegfan_then_0x0ade_then_gamebanana(self):
        detail = function.apply_cover_priority(
            {
                'mirrored_screenshots': ['https://0x0ade.example/cover.png'],
                'screenshots': ['https://images.gamebanana.com/cover.jpg'],
                'cover_url': 'https://images.gamebanana.com/fallback.jpg',
            },
            'https://celeste.weg.fan/images/cover.jpg',
        )
        self.assertEqual(detail['cover_url'], 'https://celeste.weg.fan/images/cover.jpg')
        self.assertEqual(
            detail['cover_urls'],
            [
                'https://celeste.weg.fan/images/cover.jpg',
                'https://0x0ade.example/cover.png',
                'https://images.gamebanana.com/cover.jpg',
                'https://images.gamebanana.com/fallback.jpg',
            ],
        )

    def test_wegfan_cover_requires_matching_gamebanana_id(self):
        response_data = {
            'data': {
                'content': [
                    {
                        'gameBananaId': 2,
                        'gameBananaSection': 'Mod',
                        'screenshots': [{'url': 'https://celeste.weg.fan/wrong.jpg'}],
                    },
                    {
                        'gameBananaId': 1,
                        'gameBananaSection': 'Mod',
                        'screenshots': [{'url': 'https://celeste.weg.fan/correct.jpg'}],
                    },
                ]
            },
            'code': 200,
        }
        with (
            mock.patch.object(
                function,
                'http_get',
                return_value={
                    'ok': True,
                    'status': 200,
                    'headers': {},
                    'content': json.dumps(response_data).encode('utf-8'),
                },
            ),
            mock.patch.object(
                function.utils,
                'load_global_config',
                return_value={'cover_mirror_lookup_timeout_seconds': 6},
            ),
        ):
            cover_url = function.get_wegfan_cover_url('Mod', 1, 'Test Map')
        self.assertEqual(cover_url, 'https://celeste.weg.fan/correct.jpg')

    def test_cover_image_is_first_segment(self):
        detail_text = function.format_detail(
            {
                'id': 1,
                'item_type': 'Mod',
                'name': 'Cover Test',
                'author': 'Tester',
                'cover_url': 'https://example.com/a.png?x=1&y=2,3',
            },
            heading='【每日 Mod】',
        )
        self.assertTrue(
            detail_text.startswith(
                '[OP:image,file=https://example.com/a.png?x=1&amp;y=2&#44;3]【每日 Mod】\n'
            )
        )
        self.assertFalse(detail_text.startswith('[OP:image,file=https://example.com/a.png?x=1&amp;y=2&#44;3]\n'))
        self.assertFalse(detail_text.endswith('\n'))

    def test_html_truncation(self):
        text = function.truncate_text('<b>Hello</b><br>World &amp; Celeste', 14)
        self.assertEqual(text, 'Hello\nWorld &…')

    def test_detail_credit_and_description_limits(self):
        detail = {
            'id': 1,
            'item_type': 'Mod',
            'name': 'Limit Test',
            'author': 'A' * 30,
            'description': 'D' * 30,
            'credits': [
                {
                    'group': 'Authors',
                    'authors': [{'name': 'CollaboratorName', 'role': 'Mapper'}],
                }
            ],
        }
        with mock.patch.object(
            function.utils,
            'load_global_config',
            return_value={
                'description_max_length': 10,
                'credit_max_length': 12,
                'detail_download_component_limit': 6,
                'show_cover_image_switch': False,
            },
        ):
            text = function.format_detail(detail)
        self.assertIn('作者/投稿者：AAAAAAAAAAA…', text)
        self.assertIn('完整署名：Authors：Col…', text)
        self.assertIn('简介：DDDDDDDDD…', text)

    def test_daily_mod_is_stable(self):
        candidates = [
            {'GameBananaId': 1, 'GameBananaType': 'Mod', 'Name': 'A'},
            {'GameBananaId': 2, 'GameBananaType': 'Mod', 'Name': 'B'},
        ]
        normalized = [function.normalize_item(item) for item in candidates]
        with mock.patch.object(
            function,
            'get_eligible_random_items',
            return_value={'ok': True, 'results': normalized, 'error': ''},
        ):
            first = function.get_daily_mod('2026-07-13')
            second = function.get_daily_mod('2026-07-13')
        self.assertEqual(first['data']['id'], second['data']['id'])

    def test_title_search_short_cache(self):
        response_data = [{'GameBananaId': 1, 'GameBananaType': 'Mod', 'Name': 'Cached Map'}]
        function.search_memory_cache.clear()
        with tempfile.TemporaryDirectory() as temporary_dir:
            with (
                mock.patch.object(function.utils, 'get_shared_cache_dir', return_value=temporary_dir),
                mock.patch.object(
                    function.utils,
                    'load_global_config',
                    return_value={'search_cache_seconds': 300},
                ),
                mock.patch.object(
                    function,
                    'http_get',
                    return_value={
                        'ok': True,
                        'status': 200,
                        'headers': {},
                        'content': json.dumps(response_data).encode('utf-8'),
                    },
                ) as http_mock,
            ):
                first = function.search_title('Cached Map')
                second = function.search_title('cached map')
        self.assertEqual(first, second)
        self.assertEqual(http_mock.call_count, 1)

    def test_full_detail_short_cache(self):
        response_data = {'GameBananaId': 1, 'GameBananaType': 'Mod', 'Name': 'Cached Detail'}
        function.detail_memory_cache.clear()
        with tempfile.TemporaryDirectory() as temporary_dir:
            with (
                mock.patch.object(function.utils, 'get_shared_cache_dir', return_value=temporary_dir),
                mock.patch.object(
                    function.utils,
                    'load_global_config',
                    return_value={'detail_cache_seconds': 600},
                ),
                mock.patch.object(
                    function,
                    'http_get',
                    return_value={
                        'ok': True,
                        'status': 200,
                        'headers': {},
                        'content': json.dumps(response_data).encode('utf-8'),
                    },
                ) as http_mock,
                mock.patch.object(function, 'get_profile', return_value={'ok': False, 'error': ''}) as profile_mock,
                mock.patch.object(function, 'load_updater_index', return_value={'ok': True, 'data': {}, 'error': ''}),
                mock.patch.object(
                    function,
                    'get_wegfan_cover_url',
                    return_value='https://celeste.weg.fan/cached.jpg',
                ) as cover_mock,
            ):
                first = function.get_item_by_id(1, 'Mod')
                second = function.get_item_by_id(1, 'Mod')
        self.assertTrue(first['ok'])
        self.assertTrue(second['ok'])
        self.assertEqual(second['data']['cover_url'], 'https://celeste.weg.fan/cached.jpg')
        self.assertEqual(http_mock.call_count, 1)
        self.assertEqual(profile_mock.call_count, 1)
        self.assertEqual(cover_mock.call_count, 1)

    def test_random_candidates_only_include_maps(self):
        database = [
            {
                'GameBananaId': 1,
                'GameBananaType': 'Mod',
                'Name': 'Map A',
                'CategoryName': 'Maps',
            },
            {
                'GameBananaId': 2,
                'GameBananaType': 'Mod',
                'Name': 'Helper B',
                'CategoryName': 'Helpers',
            },
        ]
        updater_index = {
            ('mod', 1): [{'InternalName': 'MapA', 'Version': '1.0.0'}],
            ('mod', 2): [{'InternalName': 'HelperB', 'Version': '1.0.0'}],
        }
        with (
            mock.patch.object(function, 'load_mod_database', return_value={'ok': True, 'data': database}),
            mock.patch.object(function, 'load_updater_index', return_value={'ok': True, 'data': updater_index}),
            mock.patch.object(
                function.utils,
                'load_global_config',
                return_value={'random_category_name': 'Maps'},
            ),
        ):
            result = function.get_eligible_random_items()
        self.assertTrue(result['ok'])
        self.assertEqual([item['id'] for item in result['results']], [1])

    def test_endless_random_retries_until_maps(self):
        responses = [
            {'status': 302, 'headers': {'Location': 'https://gamebanana.com/mods/1'}},
            {'status': 302, 'headers': {'Location': 'https://gamebanana.com/mods/2'}},
        ]
        details = [
            {'ok': True, 'data': {'id': 1, 'item_type': 'Mod', 'category': 'Helpers'}},
            {'ok': True, 'data': {'id': 2, 'item_type': 'Mod', 'category': 'Maps'}},
        ]
        with (
            mock.patch.object(function, 'http_get', side_effect=responses) as http_mock,
            mock.patch.object(function, 'get_item_by_id', side_effect=details),
            mock.patch.object(
                function.utils,
                'load_global_config',
                return_value={'endless_category_name': 'Maps'},
            ),
        ):
            result = function.get_random_map()
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['id'], 2)
        self.assertEqual(http_mock.call_count, 2)

    def test_endless_state_machine(self):
        map_a = {'GameBananaId': 1, 'GameBananaType': 'Mod', 'Name': 'A'}
        map_b = {'GameBananaId': 2, 'GameBananaType': 'Mod', 'Name': 'B'}
        map_c = {'GameBananaId': 3, 'GameBananaType': 'Mod', 'Name': 'C'}
        state = function.new_endless_state(1, map_a)
        self.assertTrue(state['run_id'])
        self.assertFalse(state['score_recorded'])
        cleared = function.transition_endless(state, 'clear', map_b)
        self.assertEqual(cleared['clears'], 1)
        self.assertEqual(cleared['skips'], 1)
        full_cleared = function.transition_endless(cleared, 'full_clear', map_c)
        self.assertEqual(full_cleared['clears'], 2)
        self.assertEqual(full_cleared['skips'], 2)
        restored = function.transition_endless(full_cleared, 'undo')
        self.assertEqual(restored['clears'], 1)
        self.assertEqual(restored['current_map']['id'], 2)

        no_skip = copy.deepcopy(state)
        no_skip['skips'] = 0
        failed = function.transition_endless(no_skip, 'skip')
        self.assertEqual(failed['status'], 'failed')
        with self.assertRaises(ValueError):
            function.transition_endless(failed, 'clear', map_b)

        pending = function.transition_endless(state, 'clear')
        self.assertEqual(pending['status'], 'pending')
        self.assertEqual(pending['clears'], 1)

    def test_endless_record_last_best_and_duplicate(self):
        first_state = {'run_id': 'run-a', 'clears': 2, 'finished_at': 10}
        second_state = {'run_id': 'run-b', 'clears': 5, 'finished_at': 20}
        record = function.add_endless_score_record({}, first_state, 'ended')
        record = function.add_endless_score_record(record, first_state, 'ended')
        record = function.add_endless_score_record(record, second_state, 'failed')
        self.assertEqual(record['last_endless_score'], 5)
        self.assertEqual(record['best_endless_score'], 5)
        self.assertEqual(record['total_runs'], 2)
        self.assertEqual(record['last_result'], 'failed')

        restored = function.remove_endless_score_record(record, 'run-b')
        self.assertEqual(restored['last_endless_score'], 2)
        self.assertEqual(restored['best_endless_score'], 2)
        self.assertEqual(restored['total_runs'], 1)
        self.assertEqual(restored['last_result'], 'ended')

    def test_endless_map_is_compact(self):
        compact = function.compact_endless_map(
            {
                'GameBananaId': 1,
                'GameBananaType': 'Mod',
                'Name': 'A',
                'Text': 'x' * 10000,
                'Files': [{'URL': 'https://gamebanana.com/dl/1'}],
            }
        )
        self.assertNotIn('text', compact)
        self.assertNotIn('files', compact)

    def test_user_storage_isolated_by_context(self):
        class Object(object):
            pass

        event = Object()
        event.bot_info = Object()
        event.bot_info.hash = 'bot'
        event.data = Object()
        event.data.user_id = '10001'
        event.data.group_id = '20001'
        event.data.host_id = None
        event.platform = {'platform': 'qq'}
        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.object(utils, 'get_storage_dir', return_value=temporary_dir):
                personal_path = utils.get_personal_storage_dir(event)
                endless_path = message.get_endless_file_path(event)
                group_path = utils.get_user_storage_dir(event)
                event.data.group_id = '20002'
                other_group_path = utils.get_user_storage_dir(event)
                other_personal_path = utils.get_personal_storage_dir(event)
                other_endless_path = message.get_endless_file_path(event)
                event.data.group_id = None
                private_path = utils.get_user_storage_dir(event)
        self.assertNotEqual(group_path, other_group_path)
        self.assertNotEqual(group_path, private_path)
        self.assertEqual(personal_path, other_personal_path)
        self.assertEqual(endless_path, other_endless_path)

    def test_group_switch_uses_hag_context(self):
        class Object(object):
            pass

        event = Object()
        event.bot_info = Object()
        event.bot_info.hash = 'bot'
        event.data = Object()
        event.data.user_id = '10001'
        event.data.group_id = '20001'
        event.data.host_id = '30001'
        event.data.sender = {'role': 'admin'}
        event.platform = {'platform': 'qq'}
        stored_config = {'bot_enable_switch': True, 'disabled_group_list': []}

        def load_config(_bot_hash):
            return copy.deepcopy(stored_config)

        def save_config(_bot_hash, data):
            stored_config.clear()
            stored_config.update(copy.deepcopy(data))
            return True

        with (
            mock.patch.object(utils, 'load_bot_config', side_effect=load_config),
            mock.patch.object(utils, 'save_bot_config', side_effect=save_config),
        ):
            self.assertTrue(utils.can_manage_group_switch(event))
            self.assertFalse(utils.is_group_disabled(event))
            self.assertTrue(utils.set_group_disabled(event, True))
            self.assertTrue(utils.is_group_disabled(event))
            self.assertEqual(stored_config['disabled_group_list'], ['30001|20001'])
            self.assertTrue(utils.set_group_disabled(event, False))
            self.assertFalse(utils.is_group_disabled(event))

    def test_disabled_group_only_allows_switch_commands(self):
        class Object(object):
            pass

        event = Object()
        event.data = Object()
        event.data.message = '.clst on'
        with (
            mock.patch.object(utils, 'ensure_runtime_storage_by_event', return_value='bot'),
            mock.patch.object(utils, 'check_core_group_enable', return_value=True),
            mock.patch.object(utils, 'load_global_config', return_value={'global_enable_switch': True}),
            mock.patch.object(utils, 'load_bot_config', return_value={'bot_enable_switch': True}),
            mock.patch.object(utils, 'is_group_disabled', return_value=True),
            mock.patch.object(message, 'dispatch_clst_command') as dispatch_mock,
        ):
            message.handle_message(event, None)
            dispatch_mock.assert_called_once_with(event, 'on')
            dispatch_mock.reset_mock()
            event.data.message = '.clst random'
            message.handle_message(event, None)
            dispatch_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
