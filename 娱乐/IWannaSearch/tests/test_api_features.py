# -*- encoding: utf-8 -*-
"""验证 I Wanna Archive 2026.014 API 新接口与过滤器功能。"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = '_iwanna_search_feature_test'


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
        cls.message_custom = package.main.webui.message_custom
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


if __name__ == '__main__':
    unittest.main()

