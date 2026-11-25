# -*- encoding: utf-8 -*-
"""验证 I Wanna Archive 2026.014 API 新接口与过滤器功能。"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path
from unittest.mock import Mock, patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = '_iwanna_search_feature_test'


def _fake_event(message_text: str):
    """最小 plugin_event：够走 handle_message 的分发即可。"""
    import types
    data = types.SimpleNamespace(
        user_id='U', group_id='G', message_id='M', message=message_text,
        extend={'flag_from_qq': True, 'flag_from_direct': False},
    )
    event = types.SimpleNamespace(
        data=data,
        plugin_info={'func_type': 'group_message'},
        platform={'platform': 'qqguild'},
    )
    return event


class IWannaSearchAPIFeaturesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules_patch = patch.dict(sys.modules, {'OlivOS': types.ModuleType('OlivOS')})
        cls.modules_patch.start()
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_DIR / '__init__.py')
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        cls.message = package.main.message
        cls.function = package.main.message.function
        cls.config = package.main.message.config
        cls.message_custom = package.main.utils.message_custom
        cls.utils = package.main.utils

    @classmethod
    def tearDownClass(cls):
        cls.modules_patch.stop()

    def test_normalize_filter_params_and_url_builder(self):
        """测试过滤器参数标准化与 URL 构建。"""
        params = {
            'year': 2021,
            'tag': ['needle', 'adventure'],
            'tag_not': 'trap',
            'engine': 'Godot',
            'engine_not': 'Unity',
            'source': 'wiki',
            'source_not': 'df',
        }
        url = self.function.build_query_url('api/search', 'https://fangame-archive.com', params)
        self.assertIn('https://fangame-archive.com/api/search?', url)
        self.assertIn('date_from=2021-01-01', url)
        self.assertIn('date_to=2021-12-31', url)
        self.assertIn('tag=needle', url)
        self.assertIn('tag=adventure', url)
        self.assertIn('tag_not=trap', url)
        self.assertIn('engine=Godot', url)
        self.assertIn('engine_not=Unity', url)
        self.assertIn('source=wiki', url)
        self.assertIn('source_not=df', url)

    def test_normalize_game_item_metadata_and_sources(self):
        """测试游戏条目元数据解析与外部链接提取。"""
        raw_item = {
            'id': 14327,
            'title': 'I Wanna Use My New Engine',
            'creator': 'TheZero3546',
            'engine': 'Godot',
            'release_date': '2021-08-11',
            'rating': 3.75,
            'difficulty': 25,
            'rating_count': 7,
            'file_size': 19591423,
            'url': 'https://file.fangame-archive.com/Game/14327.zip',
            'page_url': 'https://fangame-archive.com/?game=14327',
            'tags': ['different_engine', 'godot', 'needle'],
            'source': [
                {
                    'id': '23470',
                    'site': 'Delicious Fruit',
                    'type': 'df',
                    'url': 'https://delicious-fruit.com/ratings/game_details.php?id=23470',
                },
                {
                    'id': '10050',
                    'site': 'IWanna Wiki',
                    'type': 'wiki',
                    'url': 'https://iwannawiki.com/games/10050',
                },
            ],
        }
        normalized = self.function.normalize_game_item(raw_item)
        self.assertEqual(normalized['id'], '14327')
        self.assertEqual(normalized['release_date'], '2021-08-11')
        self.assertEqual(normalized['page_url'], 'https://fangame-archive.com/?game=14327')
        self.assertEqual(normalized['df_url'], 'https://delicious-fruit.com/ratings/game_details.php?id=23470')
        self.assertEqual(normalized['wiki_url'], 'https://iwannawiki.com/games/10050')
        self.assertIn('Delicious Fruit', normalized['sources'])
        self.assertIn('IWanna Wiki', normalized['sources'])
        self.assertIn('DF: https://delicious-fruit.com', normalized['external_urls'])
        self.assertIn('Wiki: https://iwannawiki.com', normalized['external_urls'])

        template_val = self.function.build_game_template_value(normalized)
        self.assertEqual(template_val['release_date'], '2021-08-11')
        self.assertEqual(template_val['page_url'], 'https://fangame-archive.com/?game=14327')
        self.assertIn('Delicious Fruit', template_val['sources'])
        self.assertEqual(template_val['rating'], '3.8/10')
        self.assertEqual(template_val['difficulty'], '25.0/100')

    def test_parse_filter_flags(self):
        """测试命令参数中的多维过滤器解析。"""
        text = 'Needle Space --engine="GameMaker 8" --tag=needle --not-tag=trap --year=2021 --source=wiki'
        clean, filters = self.message.parse_filter_flags(text)
        self.assertEqual(clean, 'Needle Space')
        self.assertEqual(filters.get('engine'), 'GameMaker 8')
        self.assertEqual(filters.get('tag'), 'needle')
        self.assertEqual(filters.get('tag_not'), 'trap')
        self.assertEqual(filters.get('year'), '2021')
        self.assertEqual(filters.get('source'), 'wiki')

    def test_parse_random_argument(self):
        """测试随机游戏参数与三态过滤器组合解析。"""
        res = self.message.parse_random_argument('5 --engine=Godot --year=2021')
        self.assertTrue(res['ok'])
        self.assertEqual(res['count'], 5)
        self.assertEqual(res['filters']['engine'], 'Godot')
        self.assertEqual(res['filters']['year'], '2021')

        res_tag = self.message.parse_random_argument('--tag=needle')
        self.assertTrue(res_tag['ok'])
        self.assertEqual(res_tag['count'], 1)
        self.assertEqual(res_tag['filters']['tag'], 'needle')

    def test_catalog_endpoints(self):
        """测试 tag, engine, releasedate, all 四大专用接口返回数据结构。"""
        with patch.object(self.function, 'fetch_json') as mock_fetch:
            # 1. tag
            mock_fetch.return_value = {
                'success': True,
                'count': 2,
                'tags': [{'tag': 'needle', 'count': 8000}, {'tag': 'trap', 'count': 2000}],
            }
            tags_resp = self.function.fetch_tags('https://fangame-archive.com', 10)
            self.assertTrue(tags_resp['ok'])
            self.assertEqual(tags_resp['count'], 2)
            self.assertEqual(len(tags_resp['tags']), 2)

            # 2. engine
            mock_fetch.return_value = {
                'success': True,
                'count': 2,
                'engines': [{'engine': 'Godot', 'count': 16}, {'engine': 'Unity', 'count': 11}],
            }
            eng_resp = self.function.fetch_engines('https://fangame-archive.com', 10)
            self.assertTrue(eng_resp['ok'])
            self.assertEqual(eng_resp['count'], 2)

            # 3. releasedate
            mock_fetch.return_value = {
                'success': True,
                'dated': 15000,
                'undated': 5000,
                'games_considered': 20000,
                'earliest': '2007-10-05',
                'latest': '2026-09-18',
                'by_year': [{'year': '2021', 'count': 1300}],
            }
            date_resp = self.function.fetch_release_dates('https://fangame-archive.com', 10)
            self.assertTrue(date_resp['ok'])
            self.assertEqual(date_resp['dated'], 15000)
            self.assertEqual(date_resp['earliest'], '2007-10-05')

            # 4. all
            mock_fetch.return_value = {
                'success': True,
                'catalog_size': 20879,
                'total': 20879,
                'count': 1,
                'results': [{'id': 1, 'title': 'Game1'}],
            }
            all_resp = self.function.fetch_catalog_all('https://fangame-archive.com', 10, limit=1)
            self.assertTrue(all_resp['ok'])
            self.assertEqual(all_resp['catalog_size'], 20879)
            self.assertEqual(len(all_resp['results']), 1)

    def test_command_routing(self):
        """测试 .iw year, tag, engine, date, catalog 新指令路由。"""
        replies = []
        fake_event = types.SimpleNamespace(
            bot_info=types.SimpleNamespace(id='12345'),
            data=types.SimpleNamespace(message=''),
            reply=lambda text: replies.append(text),
        )

        with patch.object(self.utils, 'reply_message', side_effect=lambda evt, txt, **kw: replies.append(txt)), \
             patch.object(self.function, 'fetch_release_dates', return_value={'ok': True, 'dated': 15000, 'undated': 5000, 'earliest': '2007-01-01', 'latest': '2026-09-20', 'by_year': [{'year': '2021', 'count': 100}]}), \
             patch.object(self.function, 'fetch_engines', return_value={'ok': True, 'count': 2, 'engines': [{'engine': 'Godot', 'count': 16}]}), \
             patch.object(self.function, 'fetch_tags', return_value={'ok': True, 'count': 1, 'tags': [{'tag': 'needle', 'count': 8000}]}), \
             patch.object(self.function, 'fetch_catalog_all', return_value={'ok': True, 'catalog_size': 20879, 'total': 20879, 'count': 1, 'results': []}):

            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw date')
            self.assertTrue(any('发行日期统计' in r for r in replies))

            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw engine')
            self.assertTrue(any('游戏引擎分布' in r for r in replies))

            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw tag')
            self.assertTrue(any('热门标签' in r for r in replies))

            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw all')
            self.assertTrue(any('全库概况' in r for r in replies))

    def test_year_command_routing(self):
        """测试 .iw year 指令及其校验。"""
        replies = []
        fake_event = types.SimpleNamespace(
            bot_info=types.SimpleNamespace(id='12345'),
            data=types.SimpleNamespace(message=''),
            reply=lambda text: replies.append(text),
        )

        with patch.object(self.utils, 'reply_message', side_effect=lambda evt, txt, **kw: replies.append(txt)), \
             patch.object(self.function, 'search_catalog', return_value={'ok': True, 'count': 1, 'results': [{'id': '10', 'title': 'Test 2021'}]}):

            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw year')
            self.assertTrue(any('请输入要查询的 4 位年份' in r for r in replies))

            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw year abc')
            self.assertTrue(any('年份格式不正确' in r for r in replies))

            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw year 2021')
            self.assertTrue(any('Test 2021' in r for r in replies))

    def test_search_and_random_with_filters(self):
        """测试 search 和 random 携带复杂过滤器。"""
        replies = []
        fake_event = types.SimpleNamespace(
            bot_info=types.SimpleNamespace(id='12345'),
            data=types.SimpleNamespace(message=''),
            reply=lambda text: replies.append(text),
        )

        with patch.object(self.utils, 'reply_message', side_effect=lambda evt, txt, **kw: replies.append(txt)), \
             patch.object(self.function, 'search_catalog') as mock_search, \
             patch.object(self.function, 'random_games') as mock_random:

            mock_search.return_value = {'ok': True, 'count': 1, 'results': [{'id': '1', 'title': 'G'}]}
            mock_random.return_value = {'ok': True, 'count': 1, 'results': [{'id': '2', 'title': 'R'}]}

            self.message.parse_iw_command(fake_event, 'iw search Needle --engine=Godot --year=2021')
            mock_search.assert_called_once()
            call_filters = mock_search.call_args[0][0]
            self.assertEqual(call_filters.get('q'), 'Needle')
            self.assertEqual(call_filters.get('engine'), 'Godot')
            self.assertEqual(call_filters.get('year'), '2021')

            self.message.parse_iw_command(fake_event, 'iw random 3 --source=wiki --tag-not=trap')
            mock_random.assert_called_once()
            kwargs = mock_random.call_args[1]
            self.assertEqual(mock_random.call_args[1].get('count', mock_random.call_args[0][0] if mock_random.call_args[0] else None), 3)
            self.assertEqual(kwargs.get('source'), 'wiki')
            self.assertEqual(kwargs.get('tag_not'), 'trap')

    def test_parse_extended_filter_flags(self):
        """测试新增筛选词解析、多值累积与无值 flag。"""
        clean, filters = self.message.parse_filter_flags(
            'needle --rating-min 8 --tag-all a --tag-all b --date-in 2010-01-01:2012-12-31'
        )
        self.assertEqual(clean, 'needle')
        self.assertEqual(filters.get('tag_all'), ['a', 'b'])
        self.assertEqual(filters.get('date_in'), ['2010-01-01:2012-12-31'])
        self.assertEqual(filters.get('rating_min'), '8')

        clean2, filters2 = self.message.parse_filter_flags(
            'boss --local --engine gm8 --engine godot --date-not :2015-12-31 --unknown-flag foo'
        )
        self.assertEqual(clean2, 'boss --unknown-flag foo')
        self.assertEqual(filters2.get('local'), 'true')
        self.assertEqual(filters2.get('engine'), ['gm8', 'godot'])
        self.assertEqual(filters2.get('date_not'), [':2015-12-31'])

    def test_normalize_filter_params_list_and_explicit_date(self):
        """测试 list 参数展开、空值跳过、显式日期优先与数值透传。"""
        tuples = self.function.normalize_filter_params({
            'year': '2021',
            'date_in': ['2010-01-01:2012-12-31', '', None, '2020-01-01:'],
            'tag_all': ['a', 'b'],
            'rating_min': '8.5',
            'local': 'true',
            'empty_str': '   ',
            'none_val': None,
        })
        self.assertIn(('date_in', '2010-01-01:2012-12-31'), tuples)
        self.assertIn(('date_in', '2020-01-01:'), tuples)
        self.assertEqual([v for k, v in tuples if k == 'date_in'], ['2010-01-01:2012-12-31', '2020-01-01:'])
        self.assertEqual([v for k, v in tuples if k == 'tag_all'], ['a', 'b'])
        self.assertIn(('rating_min', '8.5'), tuples)
        self.assertIn(('local', 'true'), tuples)
        # 给了 date_in 后不再用 year 生成 date_from/date_to
        self.assertFalse(any(k in ('date_from', 'date_to') for k, _ in tuples))

    def test_jump_page_is_a_root_subcommand(self):
        """`.iw 跳页 2` 必须走翻页，而不是当成搜索关键词。"""
        session = {'results': [{'id': str(i), 'title': f'G{i}'} for i in range(20)], 'count': 20, 'page_size': 8, 'page_index': 0}
        with (
            mock.patch.object(self.message, 'get_valid_selection_session', return_value=session),
            mock.patch.object(self.message, 'handle_jump_page_input') as jump_mock,
        ):
            self.message.handle_message(_fake_event('/iw 跳页 2'), None)
        jump_mock.assert_called_once()
        self.assertEqual(str(jump_mock.call_args[0][2]).strip(), '2')

    def test_button_callback_reply_tries_passive_then_active(self):
        """回调回复顺序：卡片 msg_id → event_id → 主动。"""
        calls = []
        class _Sender:
            def __call__(self, **kwargs):
                calls.append(dict(kwargs))
                return {'active': len(calls) == 3}
        fake = _fake_event('/iw x')
        fake.plugin_info = {'func_type': 'button_click'}
        fake.data.extend = {'event_id': 'EVT-1', 'chat_type': 'qq_group', 'chat_id': 'G'}
        fake.data.message_id = 'CARD-1'
        plugin_event = type('E', (), {
            'data': fake.data,
            'plugin_info': fake.plugin_info,
            'platform': fake.platform,
        })()
        from IWannaSearch import utils as iw_utils
        with (
            mock.patch.object(iw_utils, 'get_runtime_proc', return_value=None),
            mock.patch.object(iw_utils.markdown, 'reply_markdown', return_value=False),
        ):
            plugin_event.indeAPI = type('A', (), {'send_message': _Sender()})()
            iw_utils.reply_message(plugin_event, '翻到第 2 页')
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].get('msg_id'), 'CARD-1')
        self.assertEqual(calls[1].get('event_id'), 'EVT-1')
        self.assertNotIn('msg_id', calls[2])
        self.assertNotIn('event_id', calls[2])

    def test_build_game_template_value_meta(self):
        """测试列表模板字段 meta 在有评分难度、仅评分、均无时的输出。"""
        both = self.function.build_game_template_value(
            {'id': '21342', 'title': 'I wanna be the Cerulean', 'rating': 8.8, 'difficulty': 71.7},
            index=1,
        )
        self.assertEqual(
            both['meta'],
            ' · <font color="#FF6B35">评分 8.8/10</font>'
            ' · <font color="#FF6B35">难度 71.7/100</font>',
        )
        rendered = self.message_custom.default_custom_message_dict['reply_multiple_item'].format(**both)
        self.assertIn('<font color="#FF6B35">评分 8.8/10</font>', rendered)

        only_rating = self.function.build_game_template_value(
            {'id': '100', 'title': 'Only Rating', 'rating': 7.0, 'difficulty': None},
            index=2,
        )
        self.assertEqual(only_rating['meta'], ' · <font color="#FF6B35">评分 7.0/10</font>')

        none_both = self.function.build_game_template_value(
            {'id': '101', 'title': 'No Score', 'rating': None, 'difficulty': None},
            index=3,
        )
        self.assertEqual(none_both['meta'], '')
        rendered_none = self.message_custom.default_custom_message_dict['reply_multiple_item'].format(**none_both)
        self.assertEqual(rendered_none, '3. [101] No Score')

    def _prepare_temp_index(self, items):
        temp_dir = tempfile.TemporaryDirectory(prefix='iwanna-index-test-')
        self.addCleanup(temp_dir.cleanup)
        data_patch = patch.object(self.config, 'plugin_data_dir', temp_dir.name)
        data_patch.start()
        self.addCleanup(data_patch.stop)
        self.function._index_cache.update({'path': '', 'built_at': 0.0, 'count': 0, 'items': [], 'loaded': False})
        with patch.object(self.function, 'fetch_json', return_value={'success': True, 'results': items}):
            res = self.function.rebuild_index(base_url='https://fangame-archive.com', timeout_seconds=30)
        self.assertTrue(res['ok'])
        return temp_dir

    def test_local_index_filtering_and_sorting(self):
        """测试本地索引的 tag/tag_all/tag_not/rating_min/date_in/size_max_mb/sort/limit=0。"""
        fake_items = [
            {
                'id': 1, 'title': 'Alpha Needle', 'creator': 'Alice', 'tags': ['needle', 'avoidance'],
                'engine': 'GameMaker 8', 'release_date': '2011-05-01', 'rating': 8.5,
                'difficulty': 70.0, 'rating_count': 20, 'file_size': 5 * 1024 * 1024,
                'source': [{'type': 'df', 'id': '101'}],
            },
            {
                'id': 2, 'title': 'Beta Trap', 'creator': 'Bob', 'tags': ['needle', 'trap'],
                'engine': 'Godot', 'release_date': '2012-03-10', 'rating': 9.0,
                'difficulty': 50.0, 'rating_count': 10, 'file_size': 30 * 1024 * 1024,
                'source': [{'type': 'wiki', 'id': '202'}],
            },
            {
                'id': 3, 'title': 'Gamma Unrated', 'creator': 'Carol', 'tags': ['needle', 'avoidance'],
                'engine': None, 'release_date': None, 'rating': None,
                'difficulty': None, 'rating_count': 0, 'file_size': 2 * 1024 * 1024,
                'source': [],
            },
            {
                'id': 4, 'title': 'Delta Adventure', 'creator': 'Dave', 'tags': ['adventure'],
                'engine': 'Unity', 'release_date': '2021-07-07', 'rating': 6.0,
                'difficulty': 30.0, 'rating_count': 5, 'file_size': 10 * 1024 * 1024,
                'source': [{'type': 'df', 'id': '404'}],
            },
            {
                'id': 5, 'title': 'Epsilon Old', 'creator': 'Eve', 'tags': ['needle'],
                'engine': 'GameMaker Studio', 'release_date': '2009-12-31', 'rating': 7.5,
                'difficulty': 80.0, 'rating_count': 15, 'file_size': None,
                'source': [{'type': 'wiki', 'id': '505'}],
            },
            {
                'id': 6, 'title': 'Zeta Precision', 'creator': 'Frank', 'tags': ['needle', 'avoidance', 'gimmick'],
                'engine': 'GameMaker 8', 'release_date': '2011-11-11', 'rating': 8.2,
                'difficulty': 90.0, 'rating_count': 30, 'file_size': 8 * 1024 * 1024,
                'source': [{'type': 'df', 'id': '606'}],
            },
            {
                'id': 7, 'title': 'Eta Minimal', 'creator': 'Grace', 'tags': ['needle', 'avoidance'],
                'engine': 'Godot', 'release_date': '2012-12-31', 'rating': 7.8,
                'difficulty': 60.0, 'rating_count': 8, 'file_size': 4 * 1024 * 1024,
                'source': [{'type': 'df', 'id': '707'}],
            },
        ]
        self._prepare_temp_index(fake_items)

        # tag + tag_not
        r_tag = self.function.search_local_index({'tag': ['needle'], 'tag_not': ['trap']})
        self.assertEqual([x['id'] for x in r_tag['results']], [1, 3, 5, 6, 7])

        # tag_all
        r_all = self.function.search_local_index({'tag_all': ['needle', 'avoidance']})
        self.assertEqual([x['id'] for x in r_all['results']], [1, 3, 6, 7])

        # rating_min 排除 None
        r_rating = self.function.search_local_index({'tag_all': ['needle', 'avoidance'], 'rating_min': '8'})
        self.assertEqual([x['id'] for x in r_rating['results']], [1, 6])

        # date_in 区间（排除 release_date 为 None）
        r_date = self.function.search_local_index({'date_in': ['2010-01-01:2012-12-31']})
        self.assertEqual([x['id'] for x in r_date['results']], [1, 2, 6, 7])

        # size_max_mb 排除 file_size 为 None 及超出上限的条目
        r_size = self.function.search_local_index({'size_max_mb': '10'})
        self.assertEqual([x['id'] for x in r_size['results']], [1, 3, 4, 6, 7])

        # sort 缺失值永远排在最后（即使 desc），limit=0 返回全部且 count 正确
        r_sort_desc = self.function.search_local_index({'sort': 'rating', 'order': 'desc', 'limit': 0})
        self.assertEqual(r_sort_desc['count'], 7)
        self.assertEqual(len(r_sort_desc['results']), 7)
        self.assertEqual([x['id'] for x in r_sort_desc['results']], [2, 1, 6, 7, 5, 4, 3])

        # limit 截断时 count 仍为总匹配数
        r_limit = self.function.search_local_index({'tag': 'needle', 'limit': '2'})
        self.assertEqual(r_limit['count'], 6)
        self.assertEqual(len(r_limit['results']), 2)

    def test_request_search_falls_back_to_api_when_index_unavailable(self):
        """索引不可用或含不可本地求值键时，request_search 回落到 API。"""
        temp_dir = tempfile.TemporaryDirectory(prefix='iwanna-empty-index-')
        self.addCleanup(temp_dir.cleanup)
        with patch.object(self.config, 'plugin_data_dir', temp_dir.name):
            self.function._index_cache.update({'path': '', 'built_at': 0.0, 'count': 0, 'items': [], 'loaded': False})
            with patch.object(self.function, 'request_api_url', return_value={'ok': True, 'error': '', 'results': [{'id': '99', 'title': 'FromAPI'}], 'count': 1}) as mock_api:
                res = self.function.request_search({'q': 'needle'}, 'https://fangame-archive.com', 10)
            mock_api.assert_called_once()
            self.assertTrue(res['ok'])
            self.assertEqual(res['results'][0]['id'], '99')

        # 即使索引就绪，含 fields/offset/local/has_download 也必须走 API
        self._prepare_temp_index([{'id': 1, 'title': 'Local', 'tags': []}])
        with patch.object(self.function, 'request_api_url', return_value={'ok': True, 'error': '', 'results': [], 'count': 0}) as mock_api:
            self.function.request_search({'q': 'Local', 'local': 'true'}, 'https://fangame-archive.com', 10)
        mock_api.assert_called_once()

    def test_random_games_uses_local_index_without_network(self):
        """索引就绪时 random_games 走本地索引，不发起网络请求。"""
        self._prepare_temp_index([
            {'id': 10, 'title': 'Rand One', 'tags': ['needle'], 'rating': 8.0},
            {'id': 11, 'title': 'Rand Two', 'tags': ['needle'], 'rating': 9.0},
        ])
        with patch.object(self.function, 'request_api_url', side_effect=AssertionError('不应发网络请求')), \
             patch.object(self.function, 'fetch_json', side_effect=AssertionError('不应发网络请求')):
            res = self.function.random_games(count=2, base_url='https://fangame-archive.com', timeout_seconds=10, tag='needle')
        self.assertTrue(res['ok'])
        self.assertEqual(len(res['results']), 2)
        self.assertEqual({item['id'] for item in res['results']}, {'10', '11'})

    def test_index_commands_and_permissions(self):
        """测试 .iw index status 与 .iw index update 权限控制。"""
        self._prepare_temp_index([{'id': 1, 'title': 'One', 'tags': []}])
        replies = []
        fake_event = types.SimpleNamespace(
            bot_info=types.SimpleNamespace(id='12345', hash='test-bot'),
            data=types.SimpleNamespace(user_id='99999', message=''),
            platform={'platform': 'qq'},
        )

        with patch.object(self.utils, 'reply_message', side_effect=lambda evt, txt, **kw: replies.append(txt)), \
             patch.object(self.message, 'sender_has_master_permission', return_value=False):
            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw index status')
            self.assertTrue(any('收录条数：1 条' in r for r in replies))

            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw index update')
            self.assertTrue(any('权限不足' in r for r in replies))

        with patch.object(self.utils, 'reply_message', side_effect=lambda evt, txt, **kw: replies.append(txt)), \
             patch.object(self.message, 'sender_has_master_permission', return_value=True), \
             patch.object(self.function, 'fetch_json', return_value={'success': True, 'results': [{'id': 1, 'title': 'A'}, {'id': 2, 'title': 'B'}]}):
            replies.clear()
            self.message.parse_iw_command(fake_event, 'iw index update')
            self.assertTrue(any('共 2 条游戏' in r for r in replies))


if __name__ == '__main__':
    unittest.main()

