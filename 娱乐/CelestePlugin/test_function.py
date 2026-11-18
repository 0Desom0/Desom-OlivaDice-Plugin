# -*- encoding: utf-8 -*-
"""CelestePlugin 纯业务逻辑测试（WEGFan 单一数据源版本）。"""

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from CelestePlugin import function  # noqa: E402
from CelestePlugin import render  # noqa: E402
from CelestePlugin import message  # noqa: E402
from CelestePlugin import utils  # noqa: E402


def sample_search_item(item_id=708235):
    return {
        'id': '570697585105248105',
        'createTime': '2026-08-22T19:41:38Z',
        'updateTime': '2026-08-24T19:22:49Z',
        'name': "Crispybag's Spring Collab Pack",
        'submissionType': 'GAME_BANANA_MOD',
        'submitter': 'Crispybag',
        'pageUrl': f'https://gamebanana.com/mods/{item_id}',
        'gameBananaSection': 'Mod',
        'gameBananaId': item_id,
        'categoryId': 6800,
        'categoryName': 'Maps',
        'subCategoryId': 6802,
        'subCategoryName': 'Campaign',
        'subtitle': 'Spring Collab in 2026??',
        'description': '5 Maps with 5 rooms each!<br><br>Music: <a href="#">x</a>',
        'views': 766,
        'likes': 16,
        'downloads': 157,
        'latestUpdateAddedTime': '2026-08-24T19:23:20Z',
        'screenshots': [
            {'url': 'https://celeste.weg.fan/images/gamebanana-submissions/Mod/708235/a.jpg', 'caption': None}
        ],
        'credits': [
            {
                'groupName': 'Crispybag',
                'authors': [{'name': 'the mapper', 'role': '', 'url': ''}],
            }
        ],
        'files': [
            {
                'id': '571417175059155101',
                'createTime': '2026-08-24T19:22:41Z',
                'updateTime': '2026-08-24T19:22:41Z',
                'url': 'https://celeste.weg.fan/api/v2/download/files/571417175059155101',
                'fileName': 'crispybagsspringcollabpack_e67c2.zip',
                'description': '',
                'downloads': 92,
                'size': 23838352,
                'gameBananaId': 1796085,
                'mods': [
                    {
                        'id': '570697955264777066',
                        'name': 'CrispybagsSpringCollabPack',
                        'version': '1.0.3',
                    }
                ],
            }
        ],
    }


class CelestePluginFunctionTest(unittest.TestCase):
    def setUp(self):
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_dir.cleanup)
        patches = [
            mock.patch.object(
                function,
                'get_short_cache_path',
                side_effect=lambda group, key: str(
                    Path(self.temporary_dir.name) / f'{group}-{abs(hash(key))}.json'
                ),
            ),
            mock.patch.object(
                function,
                'get_index_cache_path',
                return_value=str(Path(self.temporary_dir.name) / 'wegfan_index.json'),
            ),
        ]
        for patch_object in patches:
            patch_object.start()
            self.addCleanup(patch_object.stop)
        function.index_memory_cache.clear()
        function.search_memory_cache.clear()
        function.detail_memory_cache.clear()

    # ---------- 命令解析 ----------

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

    # ---------- WEGFan 数据映射 ----------

    def test_user_agent_identifies_bot(self):
        headers = function.build_headers()
        self.assertEqual(headers['User-Agent'], "Desom's Bot - Fronia (CelestePlugin)")

    def test_parse_wegfan_time(self):
        self.assertEqual(function.parse_wegfan_time('1970-01-01T00:00:00Z'), 0)
        self.assertEqual(function.parse_wegfan_time('2026-08-22T19:41:38Z'), 1787427698)
        self.assertEqual(function.parse_wegfan_time(''), 0)
        self.assertEqual(function.parse_wegfan_time(None), 0)

    def test_normalize_wegfan_item_maps_fields(self):
        item = function.normalize_wegfan_item(sample_search_item())
        self.assertEqual(item['id'], 708235)
        self.assertEqual(item['weg_id'], '570697585105248105')
        self.assertEqual(item['item_type'], 'Mod')
        self.assertEqual(item['author'], 'Crispybag')
        self.assertEqual(item['category'], 'Maps')
        self.assertEqual(item['subcategory'], 'Campaign')
        self.assertEqual(item['cover_url'], item['screenshots'][0])
        self.assertEqual(item['page_url'], 'https://gamebanana.com/mods/708235')
        self.assertEqual(item['credits'][0]['authors'][0]['name'], 'the mapper')
        self.assertTrue(item['files'][0]['has_everest_yaml'])
        self.assertEqual(item['files'][0]['version'], '1.0.3')

    def test_normalize_wegfan_item_compact_drops_files(self):
        item = function.normalize_wegfan_item(sample_search_item(), compact=True)
        self.assertEqual(item['files'], [])
        self.assertEqual(item['credits'], [])
        self.assertTrue(item['weg_id'])

    def test_normalize_wegfan_file_keeps_gamebanana_file_id_and_url(self):
        item = function.normalize_wegfan_item(sample_search_item())
        file_item = item['files'][0]
        self.assertEqual(file_item['id'], 1796085)
        self.assertEqual(file_item['weg_file_id'], '571417175059155101')
        self.assertTrue(file_item['url'].startswith('https://celeste.weg.fan/api/v2/download/files/'))

    def test_build_updater_components_groups_by_file(self):
        raw = sample_search_item()
        raw['files'][0]['mods'].append({'name': 'Helper', 'version': '2.0.0'})
        components = function.build_updater_components(raw['files'])
        self.assertEqual(len(components), 2)
        groups = function.group_updater_components(components)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['file_id'], 1796085)
        self.assertEqual(groups[0]['components'], ['CrispybagsSpringCollabPack', 'Helper'])
        self.assertTrue(groups[0]['verified'])

    def test_download_urls_only_use_wegfan(self):
        urls = function.get_download_urls(1796085)
        self.assertEqual(list(urls.keys()), ['wegfan'])
        self.assertEqual(urls['wegfan'], 'https://celeste.weg.fan/api/v2/download/gamebanana-files/1796085')

    def test_format_detail_uses_wegfan_mirror_only(self):
        detail = function.normalize_wegfan_item(sample_search_item())
        detail['cover_url'] = ''
        with mock.patch.object(
            function.utils,
            'load_global_config',
            return_value={
                'description_max_length': 320,
                'credit_max_length': 180,
                'show_cover_image_switch': False,
                'detail_download_component_limit': 6,
            },
        ):
            text = function.format_detail(detail)
        self.assertIn('WEGFan 镜像：https://celeste.weg.fan/api/v2/download/files/571417175059155101', text)
        self.assertNotIn('0x0ade', text)
        self.assertNotIn('gamebanana.com/dl/', text)
        self.assertIn('CrispybagsSpringCollabPack v1.0.3', text)

    # ---------- 本地索引 ----------

    def test_prepare_index_builds_gamebanana_lookup(self):
        prepared = function.prepare_index(
            {'items': [function.normalize_wegfan_item(sample_search_item(), compact=True)], 'fetched_at': 10}
        )
        self.assertEqual(prepared['by_gamebanana_id']['mod:708235']['weg_id'], '570697585105248105')
        self.assertEqual(prepared['fetched_at'], 10)

    def test_load_index_builds_from_search_pages(self):
        pages = {
            1: {'content': [sample_search_item(1)], 'hasNextPage': True},
            2: {'content': [sample_search_item(2)], 'hasNextPage': False},
        }

        def fake_wegfan_get(_path, params=None, timeout_seconds=None):
            if params.get('section') != 'Mod':
                return {'content': [], 'hasNextPage': False}
            return pages[params['page']]

        with mock.patch.object(function, 'wegfan_get', side_effect=fake_wegfan_get):
            result = function.load_index(force_refresh=True)
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['data']['items']), 2)
        self.assertEqual(function.resolve_weg_id('Mod', 2), '570697585105248105')

    def test_fetch_full_index_retries_and_marks_partial(self):
        def fake_wegfan_get(_path, params=None, timeout_seconds=None):
            if params.get('section') != 'Mod':
                return {'content': [], 'hasNextPage': False}
            if params['page'] == 1:
                raise ValueError('handshake operation timed out')
            return {'content': [sample_search_item(5)], 'hasNextPage': False}

        with (
            mock.patch.object(function, 'wegfan_get', side_effect=fake_wegfan_get),
            mock.patch.object(function.time, 'sleep'),
        ):
            result = function.fetch_full_index()
        self.assertTrue(result['ok'])
        self.assertFalse(result['complete'])
        self.assertIn('第 1 页', result['error'])
        self.assertEqual(len(result['items']), 1)

    def test_load_index_reuses_disk_cache(self):
        with mock.patch.object(
            function,
            'fetch_full_index',
            return_value={
                'ok': True,
                'items': [function.normalize_wegfan_item(sample_search_item(), compact=True)],
                'fetched_at': 9_999_999_999,
                'error': '',
            },
        ) as fetch_mock:
            function.load_index(force_refresh=True)
        function.index_memory_cache.clear()
        with mock.patch.object(function, 'fetch_full_index') as second_fetch:
            result = function.load_index()
        second_fetch.assert_not_called()
        self.assertTrue(result['ok'])
        self.assertTrue(result['from_cache'])
        self.assertEqual(len(result['data']['items']), 1)
        self.assertEqual(fetch_mock.call_count, 1)

    # ---------- 搜索 ----------

    def test_search_title_uses_wegfan_search(self):
        payload = {'content': [sample_search_item()], 'totalElements': 10, 'hasNextPage': True}
        with mock.patch.object(function, 'wegfan_get', return_value=payload) as wegfan_mock:
            result = function.search_title('spring collab')
        self.assertTrue(result['ok'])
        self.assertEqual(result['count'], 10)
        self.assertEqual(result['results'][0]['id'], 708235)
        self.assertIn('notice', result)
        self.assertEqual(wegfan_mock.call_args[0][0], '/submission/search')

    def test_search_title_falls_back_to_index(self):
        with (
            mock.patch.object(function, 'wegfan_get', side_effect=ValueError('请求超时')),
            mock.patch.object(
                function,
                'search_local',
                return_value={'ok': True, 'results': [{'id': 1, 'name': 'X'}], 'count': 1, 'error': ''},
            ) as local_mock,
        ):
            result = function.search_title('some map')
        local_mock.assert_called_once()
        self.assertTrue(result['ok'])
        self.assertIn('本地索引', result['notice'])

    def test_search_tag_marks_partial(self):
        with mock.patch.object(
            function,
            'search_local',
            return_value={'ok': True, 'results': [], 'count': 0, 'error': ''},
        ):
            result = function.search_tag('strawberry')
        self.assertTrue(result.get('partial'))
        self.assertIn('WEGFan 不提供自由标签', result['notice'])

    # ---------- 详情 ----------

    def test_get_item_by_id_uses_given_weg_id(self):
        with mock.patch.object(function, 'wegfan_get', return_value=sample_search_item()) as wegfan_mock:
            result = function.get_item_by_id(708235, 'Mod', weg_id='570697585105248105')
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['name'], "Crispybag's Spring Collab Pack")
        self.assertEqual(wegfan_mock.call_args[0][0], '/submission/detail')
        self.assertEqual(wegfan_mock.call_args[0][1], {'id': '570697585105248105'})

    def test_get_item_by_id_resolves_from_index(self):
        with (
            mock.patch.object(function, 'resolve_weg_id', return_value='570697585105248105') as resolve_mock,
            mock.patch.object(function, 'wegfan_get', return_value=sample_search_item()),
        ):
            result = function.get_item_by_id(708235, 'Mod')
        resolve_mock.assert_called_once_with('Mod', 708235)
        self.assertTrue(result['ok'])

    def test_get_item_by_id_without_index_entry_reports_error(self):
        with (
            mock.patch.object(function, 'resolve_weg_id', return_value=''),
            mock.patch.object(function, 'refresh_index_incremental') as incremental_mock,
            mock.patch.object(function, 'start_background_index_rebuild') as rebuild_mock,
        ):
            result = function.get_item_by_id(123456, 'Mod')
        incremental_mock.assert_called_once_with('Mod')
        rebuild_mock.assert_called_once()
        self.assertFalse(result['ok'])
        self.assertIn('索引', result['error'])

    def test_get_item_by_id_refreshes_index_on_miss(self):
        resolved = {'value': ''}

        def fake_resolve(_item_type, _item_id):
            return resolved['value']

        def fake_incremental(*_args, **_kwargs):
            resolved['value'] = '570697585105248105'
            return {'ok': True, 'added': 1, 'error': ''}

        with (
            mock.patch.object(function, 'resolve_weg_id', side_effect=fake_resolve),
            mock.patch.object(function, 'refresh_index_incremental', side_effect=fake_incremental) as incremental_mock,
            mock.patch.object(function, 'start_background_index_rebuild') as rebuild_mock,
            mock.patch.object(function, 'wegfan_get', return_value=sample_search_item()),
        ):
            result = function.get_item_by_id(708235, 'Mod')
        self.assertTrue(result['ok'])
        incremental_mock.assert_called_once_with('Mod')
        rebuild_mock.assert_not_called()

    def test_get_item_by_id_rejects_mismatched_id(self):
        with (
            mock.patch.object(function, 'resolve_weg_id', return_value='570697585105248105'),
            mock.patch.object(function, 'wegfan_get', return_value=sample_search_item(1)),
        ):
            result = function.get_item_by_id(2, 'Mod')
        self.assertFalse(result['ok'])
        self.assertIn('不一致', result['error'])

    # ---------- 随机 ----------

    def test_random_map_prefers_index(self):
        with (
            mock.patch.object(
                function,
                'pick_random_index_item',
                return_value={'id': 708235, 'weg_id': '570697585105248105', 'item_type': 'Mod'},
            ),
            mock.patch.object(
                function,
                'get_item_by_id',
                return_value={'ok': True, 'data': {'id': 708235, 'name': 'X'}, 'error': ''},
            ) as detail_mock,
        ):
            result = function.get_random_map()
        self.assertTrue(result['ok'])
        detail_mock.assert_called_once_with(708235, 'Mod', True, weg_id='570697585105248105')

    def test_random_map_falls_back_to_api(self):
        with (
            mock.patch.object(function, 'pick_random_index_item', return_value={}),
            mock.patch.object(
                function,
                'pick_random_via_api',
                return_value={'id': 5, 'weg_id': 'abc', 'item_type': 'Mod'},
            ),
            mock.patch.object(
                function,
                'get_item_by_id',
                return_value={'ok': True, 'data': {'id': 5, 'name': 'Y'}, 'error': ''},
            ) as detail_mock,
        ):
            result = function.get_random_map()
        self.assertTrue(result['ok'])
        detail_mock.assert_called_once_with(5, 'Mod', True, weg_id='abc')

    # ---------- Endless ----------

    def test_endless_state_machine(self):
        map_a = {'id': 1, 'item_type': 'Mod', 'name': 'A'}
        map_b = {'id': 2, 'item_type': 'Mod', 'name': 'B'}
        map_c = {'id': 3, 'item_type': 'Mod', 'name': 'C'}
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
                'id': 1,
                'item_type': 'Mod',
                'name': 'A',
                'description': 'x' * 10000,
                'files': [{'url': 'https://celeste.weg.fan/api/v2/download/files/1'}],
                'cover_url': 'https://celeste.weg.fan/cover.png',
            }
        )
        self.assertNotIn('description', compact)
        self.assertNotIn('files', compact)
        self.assertEqual(compact['cover_url'], 'https://celeste.weg.fan/cover.png')
        self.assertEqual(compact['id'], 1)

    def test_endless_state_cover_is_first_segment(self):
        state = {
            'status': 'active',
            'clears': 2,
            'skips': 1,
            'current_map': {
                'name': 'Cover Map',
                'author': 'Mapper',
                'page_url': 'https://gamebanana.com/mods/1',
                'cover_url': 'https://example.com/cover.png?x=1&y=2',
                'credits': [],
            },
        }
        with mock.patch.object(
            function.utils,
            'load_global_config',
            return_value={'show_cover_image_switch': True},
        ):
            text = function.format_endless_state(state, notice='已抽取下一图。')
        self.assertTrue(
            text.startswith('[OP:image,file=https://example.com/cover.png?x=1&amp;y=2]已抽取下一图。\n')
        )

    # ---------- 管理命令 ----------

    def test_update_subcommand_dispatches_refresh(self):
        with mock.patch.object(message, 'handle_refresh') as refresh_mock:
            message.dispatch_clst_command(object(), '更新')
            message.dispatch_clst_command(object(), 'update')
        self.assertEqual(refresh_mock.call_count, 2)

    def test_refresh_command_is_master_only(self):
        event = object()
        with (
            mock.patch.object(utils, 'is_sender_core_master', return_value=False),
            mock.patch.object(utils, 'reply_message') as reply_mock,
            mock.patch.object(message.function, 'refresh_community_data') as refresh_mock,
        ):
            message.handle_refresh(event)
        refresh_mock.assert_not_called()
        self.assertIn('骰主', reply_mock.call_args[0][1])

        refresh_result = {
            'ok': True,
            'database_count': 6402,
            'database_from_cache': False,
            'error': '',
        }
        with (
            mock.patch.object(utils, 'is_sender_core_master', return_value=True),
            mock.patch.object(utils, 'reply_message') as reply_mock,
            mock.patch.object(message.function, 'refresh_community_data', return_value=refresh_result),
        ):
            message.handle_refresh(event)
        self.assertEqual(reply_mock.call_count, 2)
        self.assertIn('6,402', reply_mock.call_args[0][1])
        self.assertIn('已重新抓取', reply_mock.call_args[0][1])

    def test_prewarm_worker_warm_index_only(self):
        class FakeThread(object):
            def __init__(self, target=None, name=None, daemon=None):
                self.target = target

            def start(self):
                self.target()

        message.prewarm_started = False
        log_records = []
        with (
            mock.patch.object(message.threading, 'Thread', FakeThread),
            mock.patch.object(
                message.function,
                'warm_index',
                return_value={'ok': True, 'count': 6410, 'mode': 'incremental', 'added': 7, 'error': ''},
            ) as warm_mock,
            mock.patch.object(message.utils, 'info_log', side_effect=lambda _p, t: log_records.append(('info', t))),
            mock.patch.object(message.utils, 'error_log', side_effect=lambda _p, t: log_records.append(('error', t))),
        ):
            message.start_prewarm_thread(None)
        warm_mock.assert_called_once_with()
        self.assertTrue(any('6,410' in text and 'incremental' in text for _level, text in log_records))
        message.prewarm_started = False

    def test_warm_index_runs_incremental_when_index_exists(self):
        prepared = {'items': [{'id': 1}], 'fetched_at': 100, 'watermark': 100}
        with (
            mock.patch.object(
                function,
                'load_index',
                return_value={'ok': True, 'data': prepared, 'error': '', 'from_cache': True},
            ),
            mock.patch.object(
                function,
                'refresh_index_incremental',
                return_value={'ok': True, 'added': 3, 'watermark': 120, 'error': ''},
            ) as incremental_mock,
        ):
            function.index_memory_cache['data'] = {'items': [{'id': 1}, {'id': 2}], 'watermark': 120}
            result = function.warm_index()
        incremental_mock.assert_called_once_with(min_interval_seconds=0)
        self.assertTrue(result['ok'])
        self.assertEqual(result['mode'], 'incremental')
        self.assertEqual(result['added'], 3)

    def test_render_list_builds_select_buttons(self):
        items = [{'name': f'Map {index}', 'author': 'A', 'category': 'Maps'} for index in range(10)]
        text, keyboard = render.render_list('标题搜索：map', items, 0, 8, 10)
        rows = keyboard['content']['rows']
        buttons = [item for row in rows for item in row.get('buttons', [])]
        self.assertIn('## 标题搜索：map', text)
        self.assertTrue(any(item['action']['data'] == 'clst:sel:0' for item in buttons))
        self.assertTrue(any(item['action']['data'] == 'clst:pg:next' for item in buttons))
        self.assertTrue(all(len(row.get('buttons', [])) <= 4 for row in rows))
        self.assertLessEqual(len(rows), 5)

    def test_render_detail_download_buttons_are_links(self):
        detail = function.normalize_wegfan_item(sample_search_item())
        text, keyboard = render.render_detail(detail)
        buttons = [item for row in keyboard['content']['rows'] for item in row.get('buttons', [])]
        link_buttons = [item for item in buttons if item['action']['type'] == 0]
        self.assertTrue(link_buttons)
        self.assertIn('download/files', link_buttons[0]['action']['data'])
        self.assertIn('##', text)

    def test_render_endless_has_action_buttons(self):
        state = {
            'status': 'active',
            'clears': 2,
            'skips': 1,
            'current_map': {'name': 'M', 'author': 'A', 'page_url': 'https://gamebanana.com/mods/1'},
        }
        text, keyboard = render.render_endless(state, notice='已抽取下一图。')
        buttons = [item for row in keyboard['content']['rows'] for item in row.get('buttons', [])]
        payloads = {item['action']['data'] for item in buttons}
        self.assertIn('clst:en:clear', payloads)
        self.assertIn('clst:en:undo', payloads)
        self.assertIn('Celeste Endless', text)

    def test_chat_context_from_extend(self):
        class Data(object):
            group_id = 'GROUP'
            user_id = 'USER'
            extend = {'flag_from_qq': True}

        class FakeEvent(object):
            data = Data()
            plugin_info = {'func_type': 'group_message'}
            platform = {'platform': 'qqguild'}

        self.assertEqual(utils.get_chat_context(FakeEvent()), ('qq_group', 'GROUP'))

    def test_reply_quote_switch_can_disable_quote(self):
        class Data(object):
            message_id = 'MSG'
            group_id = 'GROUP'
            user_id = 'USER'
            extend = {}

        class FakeEvent(object):
            data = Data()
            plugin_info = {'func_type': 'group_message'}
            platform = {'platform': 'qqguild'}

        with mock.patch.object(utils, 'load_global_config', return_value={'reply_quote_switch': False}):
            self.assertEqual(utils.add_reply_quote(FakeEvent(), 'hello'), 'hello')
        with mock.patch.object(utils, 'load_global_config', return_value={'reply_quote_switch': True}):
            self.assertTrue(utils.add_reply_quote(FakeEvent(), 'hello').startswith('[OP:reply'))

    def test_button_click_help_dispatch(self):
        class Data(object):
            button_data = 'clst:help'
            group_id = 'GROUP'
            user_id = 'USER'
            extend = {}

        class FakeEvent(object):
            data = Data()
            plugin_info = {'func_type': 'button_click'}
            platform = {'platform': 'qqguild'}

        with (
            mock.patch.object(utils, 'check_core_group_enable', return_value=True),
            mock.patch.object(utils, 'is_group_disabled', return_value=False),
            mock.patch.object(message, 'send_help') as help_mock,
        ):
            message.handle_button_click(FakeEvent(), None)
        help_mock.assert_called_once()

    def test_button_click_ignores_foreign_buttons(self):
        class Data(object):
            button_data = 'other:thing'
            group_id = 'GROUP'
            user_id = 'USER'
            extend = {}

        class FakeEvent(object):
            data = Data()
            plugin_info = {'func_type': 'button_click'}
            platform = {'platform': 'qqguild'}

        with mock.patch.object(message, 'send_help') as help_mock:
            message.handle_button_click(FakeEvent(), None)
        help_mock.assert_not_called()

    def test_heartbeat_schedules_incremental(self):
        with mock.patch.object(message, 'clear_expired_selection_sessions'), mock.patch.object(
            message.function, 'maybe_schedule_incremental'
        ) as schedule_mock:
            message.handle_heartbeat(object(), None)
        schedule_mock.assert_called_once_with()

    def test_maybe_schedule_incremental_respects_interval(self):
        function.index_memory_cache['data'] = {'items': [{'id': 1}], 'watermark': 10}
        function.index_refresh_state['last_incremental_at'] = 0
        function.index_refresh_state['running'] = False
        with (
            mock.patch.object(function, 'get_incremental_interval', return_value=300),
            mock.patch.object(function, 'refresh_index_incremental') as incremental_mock,
            mock.patch.object(function.threading, 'Thread') as thread_mock,
        ):
            function.index_refresh_state['last_incremental_at'] = 2_000_000_000
            scheduled = function.maybe_schedule_incremental()
        self.assertFalse(scheduled)
        thread_mock.assert_not_called()
        incremental_mock.assert_not_called()

    def test_maybe_schedule_incremental_spawns_background_thread(self):
        function.index_memory_cache['data'] = {'items': [{'id': 1}], 'watermark': 10}
        function.index_refresh_state['last_incremental_at'] = 0
        function.index_refresh_state['running'] = False
        with (
            mock.patch.object(function, 'get_incremental_interval', return_value=60),
            mock.patch.object(function.threading, 'Thread') as thread_mock,
        ):
            scheduled = function.maybe_schedule_incremental()
        self.assertTrue(scheduled)
        thread_mock.assert_called_once()
        thread_mock.return_value.start.assert_called_once()
        function.index_refresh_state['running'] = False

    def test_memory_cache_is_trimmed(self):
        function.index_memory_cache.clear()
        with mock.patch.object(function, 'get_index_cache_path', return_value=str(Path(self.temporary_dir.name) / 'idx.json')):
            for index in range(10):
                function.save_short_cache(
                    function.search_memory_cache,
                    'searches',
                    f'key-{index}',
                    {'index': index},
                )
        self.assertLessEqual(len(function.search_memory_cache), 300)

        bounded = {'a': {'cached_at': 1}, 'b': {'cached_at': 2}, 'c': {'cached_at': 3}}
        with mock.patch.object(function, 'get_memory_cache_limit', return_value=2):
            function.trim_memory_cache(bounded)
        self.assertEqual(sorted(bounded), ['b', 'c'])

    def test_warm_index_reports_failure(self):
        with mock.patch.object(
            function,
            'load_index',
            return_value={'ok': False, 'data': None, 'error': '网络连接失败', 'from_cache': False},
        ):
            result = function.warm_index()
        self.assertFalse(result['ok'])
        self.assertIn('网络连接失败', result['error'])


if __name__ == '__main__':
    unittest.main()
