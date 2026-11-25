# -*- encoding: utf-8 -*-
"""CelestePlugin 纯业务逻辑测试（WEGFan 单一数据源版本）。"""

import copy
import io
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import wait
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from CelestePlugin import function  # noqa: E402
from CelestePlugin import render  # noqa: E402
from CelestePlugin import message  # noqa: E402
from CelestePlugin import message_custom  # noqa: E402
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

    # ---------- 挑图池 ----------

    def pool_index_item(self, item_id, category='Maps', downloads=1200, likes=20, age_days=100, item_type='Mod'):
        return {
            'id': item_id,
            'weg_id': f'w{item_id}',
            'item_type': item_type,
            'category': category,
            'downloads': downloads,
            'likes': likes,
            'created_at': int(time.time()) - age_days * 86400,
        }

    def pool_index_items(self):
        return {
            'ok': True,
            'data': {
                'items': [
                    # 新（3 天）+ 热门（1200）+ 好图（2.0%）
                    self.pool_index_item(1, downloads=1200, likes=24, age_days=3),
                    # 老（400 天）；下载正好 1000 不算热门；比例 1.0%
                    self.pool_index_item(2, downloads=1000, likes=10, age_days=400),
                    self.pool_index_item(3, downloads=5000, likes=50, age_days=1200),
                    # 不是 Maps / 不是 Mod，六个池子都不该收
                    self.pool_index_item(4, category='Skins', downloads=9000, likes=900, age_days=2),
                    self.pool_index_item(5, item_type='Tool', downloads=9000, likes=900, age_days=2),
                    # 冷门（下载 5）
                    self.pool_index_item(6, downloads=5, likes=0, age_days=1200),
                    # 烂图（0%），下载 >= 508
                    self.pool_index_item(7, downloads=600, likes=0, age_days=1200),
                    # 下载 < 508，不参与好/烂
                    self.pool_index_item(8, downloads=400, likes=0, age_days=1200),
                ]
            },
        }

    def test_build_pool_new_and_old_split_by_age(self):
        with mock.patch.object(function, 'load_index', return_value=self.pool_index_items()):
            new_pool = function.build_pool('new')
            old_pool = function.build_pool('old')
        self.assertEqual([item['id'] for item in new_pool['pool']], [1])
        self.assertEqual(new_pool['rule'], '发布 < 30 天')
        self.assertTrue(new_pool['heading'].startswith('新图池 · 发布 < 30 天 · 池内 1 张'))
        self.assertEqual([item['id'] for item in old_pool['pool']], [3, 6, 7, 8])
        self.assertEqual(old_pool['rule'], '发布 > 1095 天')

    def test_build_pool_hot_cold_and_ratio_pools(self):
        with mock.patch.object(function, 'load_index', return_value=self.pool_index_items()):
            hot_pool = function.build_pool('hot')
            cold_pool = function.build_pool('cold')
            good_pool = function.build_pool('good')
            bad_pool = function.build_pool('bad')
        # 下载必须严格大于 1000；下载 < 100 才算冷门
        self.assertEqual([item['id'] for item in hot_pool['pool']], [1, 3])
        self.assertEqual([item['id'] for item in cold_pool['pool']], [6])
        # 好图：下载 >= 508 且 赞/下载 >= 2%
        self.assertEqual([item['id'] for item in good_pool['pool']], [1])
        # 烂图：下载 >= 508 且 赞/下载 <= 0.5%
        self.assertEqual([item['id'] for item in bad_pool['pool']], [7])
        self.assertIn('赞/下载 ≥ 2%', good_pool['rule'])
        self.assertIn('赞/下载 ≤ 0.5%', bad_pool['rule'])

    def test_build_pool_uses_settings_and_reports_empty(self):
        with (
            mock.patch.object(function, 'load_index', return_value=self.pool_index_items()),
            mock.patch.object(function, 'get_pool_settings', return_value={
                'new_days': 30,
                'old_days': 365,
                'hot_min_downloads': 3000,
                'cold_max_downloads': 10,
                'ratio_min_downloads': 508,
                'good_min_ratio': 1.0,
                'bad_max_ratio': 0.9,
            }),
        ):
            hot_pool = function.build_pool('hot')
            # 阈值提到 3000，只剩 5000 那张
            self.assertEqual([item['id'] for item in hot_pool['pool']], [3])
            empty_pool = function.build_pool('cold', {
                'new_days': 30,
                'old_days': 365,
                'hot_min_downloads': 1000,
                'cold_max_downloads': 1,
                'ratio_min_downloads': 508,
                'good_min_ratio': 2.0,
                'bad_max_ratio': 0.3,
            })
        self.assertFalse(empty_pool['ok'])
        self.assertIn('冷门池现在是空的', empty_pool['error'])

    def test_default_pool_thresholds(self):
        settings = function.get_pool_settings()
        self.assertEqual(settings['cold_max_downloads'], 100)
        self.assertEqual(settings['old_days'], 1095)
        self.assertEqual(settings['bad_max_ratio'], 0.5)
        self.assertEqual(settings['good_min_ratio'], 2.0)
        self.assertEqual(settings['ratio_min_downloads'], 508)
        self.assertEqual(settings['new_days'], 30)
        self.assertEqual(settings['hot_min_downloads'], 1000)

    def test_build_pool_rejects_unknown_key_and_index_failure(self):
        with mock.patch.object(function, 'load_index', return_value={'ok': False, 'error': '索引不可用'}):
            result = function.build_pool('hot')
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], '索引不可用')
        unknown = function.build_pool('nope')
        self.assertFalse(unknown['ok'])
        self.assertEqual(unknown['error'], '没有这个池子')

    def test_build_all_pools_returns_six_in_order(self):
        with mock.patch.object(function, 'load_index', return_value=self.pool_index_items()):
            pools = function.build_all_pools()
        self.assertEqual([pool['key'] for pool in pools], ['new', 'old', 'hot', 'cold', 'good', 'bad'])
        self.assertEqual([pool['short'] for pool in pools], ['新图', '老图', '热门', '冷门', '好图', '烂图'])
        self.assertTrue(all(pool['heading'] for pool in pools))

    def test_pool_mods_returns_pool_size_and_details(self):
        with (
            mock.patch.object(function, 'load_index', return_value=self.pool_index_items()),
            mock.patch.object(
                function,
                'get_item_by_id',
                side_effect=lambda item_id, *args, **kwargs: {
                    'ok': True, 'data': {'id': item_id, 'name': f'M{item_id}'}, 'error': ''
                },
            ) as detail_mock,
        ):
            result = function.pool_mods('new', 1)
        self.assertTrue(result['ok'])
        self.assertEqual(result['pool_size'], 1)
        self.assertTrue(result['heading'].startswith('新图池 · 发布 < 30 天'))
        self.assertEqual(result['results'][0]['id'], 1)
        self.assertEqual(detail_mock.call_count, 1)

    def test_pool_mods_clamps_count_and_skips_failed_detail(self):
        with (
            mock.patch.object(function, 'load_index', return_value=self.pool_index_items()),
            mock.patch.object(
                function,
                'get_item_by_id',
                side_effect=[
                    {'ok': False, 'data': {}, 'error': '详情 404'},
                    {'ok': True, 'data': {'id': 2, 'name': 'B'}, 'error': ''},
                    {'ok': True, 'data': {'id': 3, 'name': 'C'}, 'error': ''},
                    {'ok': True, 'data': {'id': 6, 'name': 'D'}, 'error': ''},
                ],
            ) as detail_mock,
        ):
            result = function.pool_mods('old', 3)
        # 第一条详情失败，换成池内下一条；总数仍是 3
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['results']), 3)
        self.assertEqual(detail_mock.call_count, 4)

        with (
            mock.patch.object(function, 'load_index', return_value=self.pool_index_items()),
            mock.patch.object(
                function,
                'get_item_by_id',
                return_value={'ok': True, 'data': {'id': 6, 'name': 'D'}, 'error': ''},
            ),
        ):
            clamped = function.pool_mods('cold', 10)
        # 冷门池只有 1 张，要 10 张也只给 1 张
        self.assertTrue(clamped['ok'])
        self.assertEqual(len(clamped['results']), 1)

    def test_pool_mods_reports_empty_and_detail_failure(self):
        empty_pool = {
            'ok': False,
            'key': 'cold',
            'label': '冷门池',
            'short': '冷门',
            'pool': [],
            'pool_size': 0,
            'rule': '下载 < 100',
            'heading': '冷门池 · 下载 < 100 · 池内 0 张',
            'error': '冷门池现在是空的（下载 < 100）',
        }
        with mock.patch.object(function, 'build_pool', return_value=empty_pool):
            empty = function.pool_mods('cold', 1)
        self.assertFalse(empty['ok'])
        self.assertEqual(empty['results'], [])
        self.assertIn('冷门池', empty['error'])

        with (
            mock.patch.object(function, 'load_index', return_value=self.pool_index_items()),
            mock.patch.object(
                function,
                'get_item_by_id',
                return_value={'ok': False, 'data': {}, 'error': '详情 500'},
            ),
        ):
            failed = function.pool_mods('new', 1)
        self.assertFalse(failed['ok'])
        self.assertEqual(failed['error'], '详情 500')

    # ---------- Endless ----------
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

    def test_pool_subcommands_dispatch(self):
        with (
            mock.patch.object(message, 'handle_pool') as pool_mock,
            mock.patch.object(message, 'handle_pools') as pools_mock,
        ):
            message.dispatch_clst_command(object(), '新图')
            message.dispatch_clst_command(object(), '老图 2')
            message.dispatch_clst_command(object(), '热门')
            message.dispatch_clst_command(object(), '冷门 3')
            message.dispatch_clst_command(object(), '好图')
            message.dispatch_clst_command(object(), '烂图 5')
            message.dispatch_clst_command(object(), '发现')
        self.assertEqual(
            [call[0][1:] for call in pool_mock.call_args_list],
            [('new', ''), ('old', '2'), ('hot', ''), ('cold', '3'), ('good', ''), ('bad', '5')],
        )
        pools_mock.assert_called_once()

    def test_pool_english_aliases_dispatch(self):
        cases = [
            ('new', 'new'), ('latest', 'new'), ('recent', 'new'),
            ('old', 'old'), ('classic', 'old'), ('vintage', 'old'),
            ('hot', 'hot'), ('popular', 'hot'), ('top', 'hot'),
            ('cold', 'cold'), ('niche', 'cold'), ('obscure', 'cold'),
            ('good', 'good'), ('best', 'good'),
            ('bad', 'bad'), ('worst', 'bad'),
        ]
        with mock.patch.object(message, 'handle_pool') as pool_mock:
            for alias, _expected in cases:
                message.dispatch_clst_command(object(), f'{alias} 2')
        self.assertEqual(
            [call[0][1] for call in pool_mock.call_args_list],
            [expected for _alias, expected in cases],
        )
        self.assertTrue(all(call[0][2] == '2' for call in pool_mock.call_args_list))

    def test_english_pool_word_falls_back_to_title_search(self):
        # `.clst old times` 是搜索标题，不是老图池 + 非法参数
        with (
            mock.patch.object(message, 'handle_pool') as pool_mock,
            mock.patch.object(message.function, 'search_title', return_value={'ok': True, 'results': [], 'count': 0}) as search_mock,
            mock.patch.object(message, 'reply_search_result'),
        ):
            message.dispatch_clst_command(object(), 'old times')
            message.dispatch_clst_command(object(), 'new beginning')
            message.dispatch_clst_command(object(), 'best ever')
        pool_mock.assert_not_called()
        self.assertEqual(search_mock.call_count, 3)
        self.assertEqual(
            [call[0][0] for call in search_mock.call_args_list],
            ['old times', 'new beginning', 'best ever'],
        )

    def test_looks_like_english_pool_search(self):
        self.assertTrue(message.looks_like_english_pool_search('old times', 'times'))
        self.assertFalse(message.looks_like_english_pool_search('old 3', '3'))
        self.assertFalse(message.looks_like_english_pool_search('old', ''))
        self.assertFalse(message.looks_like_english_pool_search('老图 times', 'times'))

    def test_parse_count_argument_labels_pool(self):
        with mock.patch.object(
            message.utils, 'load_global_config', return_value={'random_max_count': 10}
        ):
            self.assertEqual(message.parse_count_argument('', '新图'), (True, 1, ''))
            self.assertEqual(message.parse_count_argument('3', '新图'), (True, 3, ''))
            valid, _count, error = message.parse_count_argument('abc', '新图')
            self.assertFalse(valid)
            self.assertIn('.clst 新图 5', error)
            valid, _count, error = message.parse_count_argument('11', '新图')
            self.assertFalse(valid)
            self.assertIn('1 至 10', error)

    def test_handle_pool_single_uses_detail_page(self):
        heading = '新图池 · 发布 < 30 天 · 池内 79 张'
        pool_result = {
            'ok': True,
            'results': [{'id': 1, 'name': 'A'}],
            'pool_size': 79,
            'heading': heading,
            'count': 1,
            'error': '',
        }
        with (
            mock.patch.object(message.function, 'pool_mods', return_value=pool_result),
            mock.patch.object(message, 'reply_detail_data') as detail_mock,
        ):
            message.handle_pool(object(), 'new', '')
        detail_mock.assert_called_once()
        self.assertEqual(detail_mock.call_args.kwargs['show_pool'], 'new')
        self.assertEqual(detail_mock.call_args.kwargs['heading'], heading)

    def test_handle_pool_multiple_uses_summary(self):
        heading = '新图池 · 发布 < 30 天 · 池内 79 张'
        pool_result = {
            'ok': True,
            'results': [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}],
            'pool_size': 79,
            'heading': heading,
            'count': 2,
            'error': '',
        }
        with (
            mock.patch.object(message.function, 'pool_mods', return_value=pool_result),
            mock.patch.object(message.utils, 'can_send_markdown', return_value=True),
            mock.patch.object(message.utils, 'reply_markdown', return_value=True) as markdown_mock,
        ):
            message.handle_pool(object(), 'new', '2')
        markdown_mock.assert_called_once()
        text = markdown_mock.call_args[0][1]
        self.assertIn(heading, text)
        self.assertIn('**2. B**', text)

    def test_handle_pool_reports_empty_pool_and_unknown_key(self):
        with (
            mock.patch.object(
                message.function,
                'pool_mods',
                return_value={
                    'ok': False,
                    'results': [],
                    'pool_size': 0,
                    'heading': '冷门池 · 下载 < 100 · 池内 0 张',
                    'count': 1,
                    'error': '冷门池现在是空的（下载 < 100）',
                },
            ),
            mock.patch.object(message.utils, 'reply_message') as reply_mock,
        ):
            message.handle_pool(object(), 'cold', '')
        self.assertIn('冷门池抽不出来', reply_mock.call_args[0][1])
        self.assertIn('冷门池现在是空的', reply_mock.call_args[0][1])

        with mock.patch.object(message.utils, 'reply_message') as reply_mock:
            message.handle_pool(object(), 'nope', '')
        self.assertIn('没有这个池子', reply_mock.call_args[0][1])

    def test_handle_pools_renders_home_and_handles_all_empty(self):
        pools = [
            {
                'key': 'new',
                'label': '新图池',
                'short': '新图',
                'rule': '发布 < 30 天',
                'pool_size': 79,
                'heading': '新图池 · 发布 < 30 天 · 池内 79 张',
            }
        ]
        with (
            mock.patch.object(message.function, 'build_all_pools', return_value=pools),
            mock.patch.object(message.utils, 'can_send_markdown', return_value=True),
            mock.patch.object(message.utils, 'reply_markdown', return_value=True) as markdown_mock,
        ):
            message.handle_pools(object())
        home_text = markdown_mock.call_args[0][1]
        self.assertIn('新图池', home_text)
        self.assertIn('池内 79 张', home_text)

        empty = [dict(pool, pool_size=0) for pool in pools]
        with (
            mock.patch.object(message.function, 'build_all_pools', return_value=empty),
            mock.patch.object(message.utils, 'reply_message') as reply_mock,
        ):
            message.handle_pools(object())
        self.assertIn('都是空的', reply_mock.call_args[0][1])

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

    def test_render_list_only_has_paging_buttons(self):
        items = [{'name': f'Map {index}', 'author': 'A', 'category': 'Maps'} for index in range(10)]
        text, keyboard = render.render_list('标题搜索：map', items, 0, 8, 10)
        buttons = [item for row in keyboard['content']['rows'] for item in row.get('buttons', [])]
        payloads = [item['action']['data'] for item in buttons]
        self.assertEqual(payloads, ['clst:pg:next', '.clst 跳页 '])
        # 回调按钮 type=1；只有跳页是 type=2 指令型（需要用户补页码）。
        self.assertEqual([item['action']['type'] for item in buttons], [1, 2])
        # 回调按钮不带 enter/reply；跳页按钮 enter=False 只把命令填进输入框。
        self.assertNotIn('enter', buttons[0]['action'])
        self.assertFalse(buttons[1]['action']['enter'])
        self.assertIn('**标题搜索：map**', text)
        self.assertIn('回复序号看详情', text)

    def test_render_detail_download_buttons_are_links(self):
        detail = function.normalize_wegfan_item(sample_search_item())
        text, keyboard, images = render.render_detail(detail)
        buttons = [item for row in keyboard['content']['rows'] for item in row.get('buttons', [])]
        link_buttons = [item for item in buttons if item['action']['type'] == 0]
        self.assertTrue(link_buttons)
        self.assertIn('download/files', link_buttons[0]['action']['data'])
        self.assertIn('**', text)
        # 详情页每项信息都是列表项。
        self.assertIn('- **ID**：', text)
        self.assertIn('- **作者**：', text)
        self.assertIn('- **数据**：', text)
        # 封面交给适配器上传，正文只留占位符。
        self.assertEqual(list(images), ['地图封面'])
        self.assertIn('{{地图封面}}', text)
        self.assertNotIn(images['地图封面'], text)

    def test_render_detail_has_callback_controls(self):
        detail = function.normalize_wegfan_item(sample_search_item())
        _, keyboard, _ = render.render_detail(detail, show_random=True, show_endless=True)
        buttons = [item for row in keyboard['content']['rows'] for item in row.get('buttons', [])]
        controls = [item for item in buttons if item['action']['type'] != 0]
        self.assertTrue(controls)
        self.assertTrue(all(item['action']['type'] == 1 for item in controls))
        payloads = {item['action']['data'] for item in controls}
        self.assertEqual(payloads, {'clst:rnd:1', 'clst:rnd:3', 'clst:en:status'})
        self.assertLessEqual(len(keyboard['content']['rows']), 5)

    def test_render_endless_has_action_buttons(self):
        state = {
            'status': 'active',
            'clears': 2,
            'skips': 1,
            'current_map': {'name': 'M', 'author': 'A', 'page_url': 'https://gamebanana.com/mods/1'},
        }
        text, keyboard, _ = render.render_endless(state, notice='已抽取下一图。')
        buttons = [item for row in keyboard['content']['rows'] for item in row.get('buttons', [])]
        payloads = {item['action']['data'] for item in buttons}
        self.assertIn('clst:en:clear', payloads)
        self.assertIn('clst:en:undo', payloads)
        self.assertTrue(all(item['action']['type'] == 1 for item in buttons))
        self.assertIn('Celeste Endless', text)

    def test_handle_id_renders_markdown_with_download_buttons(self):
        detail = {
            'item_type': 'Mod',
            'id': 644315,
            'name': 'Test Map',
            'author': 'Tester',
            'category': 'Maps',
            'subcategory': 'Standalone',
            'downloads': 12,
            'views': 34,
            'likes': 5,
            'description': 'desc',
            'page_url': 'https://gamebanana.com/mods/644315',
            'files': [{'id': 999, 'name': 'map.zip', 'size': 2048, 'url': 'https://x/map.zip'}],
        }
        captured = {}

        def fake_reply_markdown(event, text, keyboard=None, images=None):
            captured['text'] = text
            captured['keyboard'] = keyboard
            return True

        class Data(object):
            message_id = '-1'
            group_id = 'GROUP'
            user_id = 'USER'
            extend = {'flag_from_qq': True, 'flag_from_direct': False}

        class FakeEvent(object):
            data = Data()
            plugin_info = {'func_type': 'group_message'}
            platform = {'platform': 'qqguild'}

        with (
            mock.patch.object(message.function, 'get_item_by_id', return_value={'ok': True, 'data': detail}),
            mock.patch.object(message.utils, 'can_send_markdown', return_value=True),
            mock.patch.object(message.utils, 'reply_markdown', side_effect=fake_reply_markdown),
        ):
            message.handle_id(FakeEvent(), '644315')

        self.assertIn('- **ID**：Mod 644315', captured['text'])
        buttons = [item for row in captured['keyboard']['content']['rows'] for item in row['buttons']]
        self.assertTrue(buttons)
        # 下载/外链都是跳转型按钮（type 0），不是纯文本里的裸链接
        self.assertTrue(all(item['action']['type'] == 0 for item in buttons))

    def test_cover_cache_keeps_100_and_drops_oldest(self):
        import hashlib  # noqa: F401
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, 'covers')
            os.makedirs(folder)
            for index in range(105):
                path = os.path.join(folder, '%03d.jpg' % index)
                with open(path, 'wb') as handle:
                    handle.write(b'x')
                os.utime(path, (1000 + index, 1000 + index))
            with (
                mock.patch.object(utils, 'get_cover_cache_dir', return_value=folder),
                mock.patch.object(
                    utils, 'load_global_config', return_value={'cover_cache_max_items': 100}
                ),
            ):
                removed = utils.trim_cover_cache()
            remaining = sorted(os.listdir(folder))
        self.assertEqual(removed, 5)
        self.assertEqual(len(remaining), 100)
        self.assertNotIn('000.jpg', remaining)
        self.assertIn('104.jpg', remaining)

    def test_cover_cache_hit_never_expires_and_touches_mtime(self):
        import hashlib
        import os
        import tempfile
        import time

        url = 'https://celeste.weg.fan/images/demo.jpg'
        digest = hashlib.sha1(url.encode('utf-8')).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, 'covers')
            os.makedirs(folder)
            path = os.path.join(folder, digest + '.jpg')
            with open(path, 'wb') as handle:
                handle.write(b'cached')
            old = 1000.0
            os.utime(path, (old, old))
            with (
                mock.patch.object(utils, 'get_cover_cache_dir', return_value=folder),
                mock.patch.object(utils, 'load_global_config', return_value={}),
            ):
                resource = utils.prepare_local_image(url)
            stat = os.stat(path)
        self.assertEqual(resource, 'CelestePlugin/covers/' + digest + '.jpg')
        # 命中后 mtime 被刷新，「最久没被用过」才算数
        self.assertGreater(stat.st_mtime, old + 1)
        self.assertLess(abs(stat.st_mtime - time.time()), 120)

    def test_cold_covers_overlap_and_failed_label_does_not_change_reply(self):
        folder = self.temporary_dir.name
        barrier = threading.Barrier(3)
        png = b'\x89PNG\r\n\x1a\npixels'
        jpg = b'\xff\xd8pixels'
        images = {label: 'https://example.org/' + label for label in ('first', 'bad', 'last')}
        images['repeat'] = images['first']

        def open_cover(request, timeout):
            barrier.wait(timeout=3)  # 串行实现无法让三个下载同时到达这里。
            self.assertEqual(timeout, 8)
            if request.full_url == images['bad']:
                raise TimeoutError('unavailable')
            return io.BytesIO(png if request.full_url == images['first'] else jpg)

        sender = mock.Mock(return_value={'active': True})
        event = SimpleNamespace(
            data=SimpleNamespace(extend={'chat_type': 'qq_private', 'chat_id': 'here'}, message_id='42'),
            indeAPI=SimpleNamespace(create_markdown_message=sender), plugin_info={'func_type': 'private_message'},
        )
        text = 'intro\n\n{{first}}\n\n{{bad}}\n\n{{last}}\n\n{{repeat}}\n\nfooter'
        keyboard = {'content': {'rows': []}}
        with (
            mock.patch.object(utils, 'get_cover_cache_dir', return_value=folder),
            mock.patch.object(utils, 'load_global_config', return_value={}),
            mock.patch.object(utils.urllib.request, 'urlopen', side_effect=open_cover) as download,
            mock.patch.object(utils, 'error_log') as log,
        ):
            self.assertTrue(utils.reply_markdown(event, text, keyboard, images=images))
            self.assertEqual(download.call_count, 3)
            log.assert_called_once()
            payload = sender.call_args.kwargs
            paths = payload['local_images']
            self.assertEqual(list(paths), ['first', 'last', 'repeat'])
            self.assertEqual(paths['first'], paths['repeat'])
            self.assertEqual((Path(folder) / Path(paths['first']).name).read_bytes(), png)
            self.assertEqual((Path(folder) / Path(paths['last']).name).read_bytes(), jpg)
            self.assertEqual(payload['markdown']['content'], text.replace('{{bad}}\n\n', ''))
            self.assertEqual(payload['msg_id'], '42')
            self.assertEqual(payload['keyboard'], keyboard)
            hot_images = {label: images[label] for label in paths}
            with mock.patch.object(utils._cover_pool, 'submit') as submit, mock.patch.object(utils, 'wait') as join:
                self.assertTrue(utils.reply_markdown(
                    event, payload['markdown']['content'], keyboard, images=hot_images,
                ))
            submit.assert_not_called()
            join.assert_not_called()
            self.assertEqual(sender.call_args.kwargs, payload)

    def test_reply_omits_covers_evicted_by_small_cache_limit(self):
        folder = Path(self.temporary_dir.name)
        images = {'a': 'https://example.org/a', 'b': 'https://example.org/b'}
        with (
            mock.patch.object(utils, 'get_cover_cache_dir', return_value=str(folder)),
            mock.patch.object(utils, 'get_cover_cache_limit', return_value=1),
            mock.patch.object(utils, '_download_cover', return_value=b'pixels'),
        ):
            paths = utils._prepare_local_images(images)
        self.assertEqual(len(paths), 1)
        self.assertEqual([path.name for path in folder.iterdir()], [Path(next(iter(paths.values()))).name])

    def test_cover_batch_deadline_sends_without_waiting_for_running_downloads(self):
        # 三个 worker 都阻塞时模拟整批到期。第四张仍在排队，不能拖延正文或在后台写缓存。
        started = threading.Barrier(4)
        release = threading.Event()
        tasks = []

        def blocked_download(url):
            started.wait(timeout=3)
            if not release.wait(timeout=5):
                raise TimeoutError('reply waited for a download past its deadline')
            return b'late'

        def reach_deadline(futures, timeout):
            self.assertEqual(timeout, 12)
            tasks.extend(futures)
            started.wait(timeout=3)
            return wait(futures, timeout=0)

        sender = mock.Mock(return_value={'active': True})
        event = SimpleNamespace(
            data=SimpleNamespace(extend={'chat_type': 'qq_private', 'chat_id': 'here'}),
            indeAPI=SimpleNamespace(create_markdown_message=sender), plugin_info={'func_type': 'private_message'},
        )
        images = {str(n): f'https://example.org/{n}' for n in range(4)}
        text = 'before\n\n' + ''.join('{{' + label + '}}\n\n' for label in images) + 'after'
        try:
            with (
                mock.patch.object(utils, 'get_cover_cache_dir', return_value=self.temporary_dir.name),
                mock.patch.object(utils, 'load_global_config', return_value={}),
                mock.patch.object(utils, '_download_cover', side_effect=blocked_download),
                mock.patch.object(utils, 'time', SimpleNamespace(monotonic=lambda: 100.0)),
                mock.patch.object(utils, 'wait', side_effect=reach_deadline),
            ):
                self.assertTrue(utils.reply_markdown(event, text, images=images))
                self.assertEqual(sender.call_args.kwargs['markdown']['content'], 'before\n\nafter')
                self.assertNotIn('local_images', sender.call_args.kwargs)
                self.assertEqual(sum(task.running() for task in tasks), 3)
                self.assertTrue(tasks[-1].cancelled())
        finally:
            release.set()
            for task in tasks:
                if not task.cancelled():
                    task.result(timeout=3)
        self.assertEqual(list(Path(self.temporary_dir.name).iterdir()), [])

    def test_render_random_summary_returns_images(self):
        items = [function.normalize_wegfan_item(sample_search_item())]
        text, keyboard, images = render.render_random_summary(items)
        self.assertEqual(list(images), ['地图封面 1'])
        self.assertIn('{{地图封面 1}}', text)
        self.assertTrue(keyboard['content']['rows'])

    def test_render_pool_summary_heading_and_buttons(self):
        items = [function.normalize_wegfan_item(sample_search_item())]
        heading = '新图池 · 发布 < 30 天 · 池内 79 张'
        text, keyboard, images = render.render_pool_summary(items, heading, 'new')
        self.assertIn(f'**{heading}**', text)
        # 条目带下载数、赞数与蓝字精确查询入口
        self.assertIn('下载 157', text)
        self.assertIn('赞 16', text)
        self.assertIn('<qqbot-cmd-input', text)
        self.assertEqual(list(images), ['地图封面 1'])
        buttons = [item for row in keyboard['content']['rows'] for item in row.get('buttons', [])]
        self.assertEqual(
            [item['action']['data'] for item in buttons],
            ['clst:pool:new:1', 'clst:pool:new:3', 'clst:pools'],
        )
        self.assertTrue(all(item['action']['type'] == 1 for item in buttons))

    def test_render_pool_summary_shows_notice(self):
        items = [function.normalize_wegfan_item(sample_search_item())]
        text, _keyboard, _images = render.render_pool_summary(
            items, '冷门池 · 下载 < 100 · 池内 4 张', 'cold', notice='池里只有 4 张，这次全给你了。'
        )
        self.assertIn('提示：池里只有 4 张，这次全给你了。', text)

    def test_render_pool_home_lists_six_pools(self):
        pools = function.POOL_ORDER  # 顺序参考
        payloads = []
        pool_list = []
        for key in pools:
            label, short = function.POOL_META[key]
            pool_list.append({
                'key': key,
                'label': label,
                'short': short,
                'rule': '规则',
                'pool_size': 10,
                'heading': f'{label} · 规则 · 池内 10 张',
            })
        text, keyboard = render.render_pool_home(pool_list)
        self.assertIn('## 挑图池', text)
        for key in pools:
            label = function.POOL_META[key][0]
            self.assertIn(f'**{label}** · 规则 · 池内 10 张', text)
            payloads.append(f'clst:pool:{key}:1')
        buttons = [item for row in keyboard['content']['rows'] for item in row.get('buttons', [])]
        self.assertEqual([item['action']['data'] for item in buttons], payloads + ['clst:help'])
        self.assertEqual(
            [item['render_data']['label'] for item in buttons],
            ['新图', '老图', '热门', '冷门', '好图', '烂图', '返回帮助'],
        )

    def test_render_pool_home_marks_empty_pool(self):
        pool_list = [
            {'key': 'cold', 'label': '冷门池', 'short': '冷门', 'rule': '下载 < 100', 'pool_size': 0, 'heading': ''},
        ]
        text, _keyboard = render.render_pool_home(pool_list)
        self.assertIn('池内 0 张（暂时抽不了）', text)

    def test_help_buttons_show_full_labels_two_per_row(self):
        text, kb = render.render_help()
        self.assertIn('.clst 发现', text)
        self.assertNotIn('.clst 热门', text)
        rows = kb['content']['rows']
        self.assertLessEqual(len(rows), render.MAX_ROWS)
        labels = []
        for row in rows:
            # 一行超过 2 个时客户端会把标签截成「热门…」
            self.assertLessEqual(len(row['buttons']), 2)
            labels.extend(item['render_data']['label'] for item in row['buttons'])
        self.assertIn('发现', labels)
        self.assertIn('今日 Mod', labels)
        # 半宽按钮放得下 6 个字，超过就有可能被截断
        for label in labels:
            self.assertLessEqual(len(label), 6, label)

    def test_help_covers_chinese_and_english_for_every_entry(self):
        text, _kb = render.render_help()
        pairs = [
            ('`.clst 关键词`', '`.clst keyword`'),
            ('`.clst id 424541`', 'exact lookup'),
            ('`.clst 作者 名称`', '`.clst author`'),
            ('`.clst 分类 Maps`', '`.clst category`'),
            ('`.clst 标签 关键词`', '`.clst tag`'),
            ('`.clst 随机 [1-10]`', '`.clst random`'),
            ('`.clst 发现`', '`.clst pools`'),
            ('`.clst today`', ''),
            ('`.clst 更新`', '`.clst update`'),
            ('`.clst 无尽 开始`', '`.clst endless start`'),
            ('`.clst 无尽 帮助`', '`.clst endless help`'),
        ]
        for chinese, english in pairs:
            self.assertIn(chinese, text)
            if english:
                self.assertIn(english, text)
        # 每个条目都要中文 + 英文各一份
        for line in text.splitlines():
            if not line.startswith('- `'):
                continue
            self.assertTrue(any('一' <= char <= '鿿' for char in line), line)
            self.assertRegex(line, r'[A-Za-z]{3,}', line)

    def test_endless_help_covers_chinese_and_english_for_every_entry(self):
        text, _kb = render.render_endless_help()
        self.assertIn('`.clst 无尽 全收集`', text)
        self.assertIn('`.clst endless fc`', text)
        for line in text.splitlines():
            if not line.startswith('- `'):
                continue
            self.assertTrue(any('一' <= char <= '鿿' for char in line), line)
            self.assertIn('endless ', line)

    def test_plain_text_help_also_has_english_aliases(self):
        plain = message_custom.help_text
        for token in [
            'keyword',
            'author',
            'category',
            'tag',
            'random',
            'pools',
            'update',
            'endless start',
        ]:
            self.assertIn(token, plain)
        self.assertIn('new|old|hot|cold|good|bad', plain)
        for token in ['endless status', 'endless clear', 'endless undo', 'endless record']:
            self.assertIn(token, message_custom.endless_help_text)

    def test_keyboards_use_two_buttons_per_row(self):
        detail = function.normalize_wegfan_item(sample_search_item())
        pool_list = [
            {'key': key, 'label': function.POOL_META[key][0], 'short': function.POOL_META[key][1],
             'rule': '规则', 'pool_size': 10, 'heading': '标题'}
            for key in function.POOL_ORDER
        ]
        pages = {
            'help': render.render_help()[1],
            'pool_home': render.render_pool_home(pool_list)[1],
            'pool_summary': render.render_pool_summary([detail], '标题', 'new')[1],
            'random_summary': render.render_random_summary([detail])[1],
            'detail_pool': render.render_detail(detail, show_pool='hot')[1],
            'detail_rnd_endless': render.render_detail(
                detail, show_random=True, show_endless=True
            )[1],
            'detail_today': render.render_detail(detail, show_today=True)[1],
            'endless': render.render_endless({'status': 'active', 'current_map': {}})[1],
            'endless_pending': render.render_endless({'status': 'pending', 'current_map': {}})[1],
            'endless_help': render.render_endless_help()[1],
        }
        for page_name, page_keyboard in pages.items():
            rows = page_keyboard['content']['rows']
            self.assertLessEqual(len(rows), render.MAX_ROWS, page_name)
            for row in rows:
                self.assertLessEqual(len(row['buttons']), 2, page_name)

    def test_render_detail_pool_controls(self):
        detail = function.normalize_wegfan_item(sample_search_item())
        heading = '热门池 · 下载 > 1,000 · 池内 533 张'
        text, keyboard, _ = render.render_detail(detail, heading=heading, show_pool='hot')
        self.assertIn(heading, text)
        buttons = [item for row in keyboard['content']['rows'] for item in row.get('buttons', [])]
        controls = [item for item in buttons if item['action']['type'] != 0]
        self.assertEqual(
            [item['action']['data'] for item in controls],
            ['clst:pool:hot:1', 'clst:pool:hot:3', 'clst:pools'],
        )
        self.assertLessEqual(len(keyboard['content']['rows']), 5)

    def test_reply_markdown_uses_event_id_on_button_click(self):
        class Data(object):
            message_id = 'ORIGIN_CARD'
            group_id = 'GROUP'
            user_id = 'USER'
            extend = {'event_id': 'INTERACTION', 'chat_type': 'qq_group', 'chat_id': 'GROUP'}

        class API(object):
            captured = None

            def create_markdown_message(self, **payload):
                API.captured = payload
                return {'active': True, 'data': {}}

        class FakeEvent(object):
            data = Data()
            indeAPI = API()
            plugin_info = {'func_type': 'button_click'}
            platform = {'platform': 'qqguild'}

        with (
            mock.patch.object(utils, 'load_global_config', return_value={}),
            mock.patch.object(utils, '_prepare_local_images', return_value={'地图封面': '/tmp/cover.jpg'}),
        ):
            ok = utils.reply_markdown(
                FakeEvent(), 'body', {'content': {'rows': []}}, images={'地图封面': 'https://x/y.jpg'}
            )
        self.assertTrue(ok)
        captured = API.captured
        self.assertEqual(captured['event_id'], 'INTERACTION')
        self.assertNotIn('msg_id', captured)
        self.assertEqual(captured['local_images'], {'地图封面': '/tmp/cover.jpg'})

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

    def test_quote_with_image_becomes_markdown_line(self):
        class Data(object):
            message_id = 'MSG'
            group_id = 'GROUP'
            user_id = 'USER'
            message = '看看这张图'
            extend = {'flag_from_qq': True, 'flag_from_direct': False}

        class FakeEvent(object):
            data = Data()
            plugin_info = {'func_type': 'group_message'}
            platform = {'platform': 'qqguild'}

        config_dict = {'reply_quote_switch': True, 'markdown_enable_switch': True}
        with mock.patch.object(utils, 'load_global_config', return_value=config_dict):
            quoted = utils.add_reply_quote(
                FakeEvent(), '[OP:image,file=https://x/cover.png]图'
            )
        # 带图的消息不能出现 reply 段，否则适配器整条拒绝 Markdown
        self.assertNotIn('[OP:reply', quoted)
        self.assertTrue(quoted.startswith('> <qqbot-at-user id="USER" />'))
        self.assertIn('看看这张图', quoted)
        self.assertIn('[OP:image', quoted)

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
