# -*- encoding: utf-8 -*-
"""矮人笑话合集、重复度与贪婪命令解析测试。"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = '_dwarfjokes_function_test'
CORE_ROOT = Path(r'C:\Users\Administrator\OneDrive\0跑团相关\OlivOS青果相关\青果主项目\OlivaDiceCore')


class DwarfJokesFunctionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules_patch = patch.dict(sys.modules, {'OlivOS': types.ModuleType('OlivOS'), 'tkinter': None})
        cls.modules_patch.start()
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_DIR / '__init__.py')
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        cls.main = package.main
        cls.function = package.main.message.function
        cls.utils = package.main.utils
        cls.config = package.main.utils.config

    @classmethod
    def tearDownClass(cls):
        cls.modules_patch.stop()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='dwarfjokes-function-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        data_dir = self.root / 'data'
        data_patch = patch.object(self.config, 'plugin_data_dir', str(data_dir))
        data_patch.start()
        self.addCleanup(data_patch.stop)
        self.function.joke_pack_cache.update({'path': '', 'mtime': None, 'jokes': []})
        self.utils.ensure_folder(str(data_dir))
        self.function.save_joke_pack(
            [
                self.function.make_joke_item(1, '问：为什么矮人总是不受其他种族的重视？答：因为他们之中没有高人。'),
                self.function.make_joke_item(3, '矮人企业家从不投资百货大楼，因为踩踏时总是第一个遭殃。'),
            ]
        )

    def test_bundled_seed_pack_exists(self):
        seed_path = PLUGIN_DIR / 'Data' / 'DwarfJokesPack.json'
        self.assertTrue(seed_path.is_file())
        data = json.loads(seed_path.read_text(encoding='utf-8'))
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 819)
        self.assertEqual(data[0]['id'], 1)
        self.assertIn('text', data[0])

    def test_greedy_primary_and_subcommand_without_spaces(self):
        info = self.utils.parse_command(
            '.矮人add 这是一条新笑话',
            prefix_list=self.config.allowed_prefix_list,
            command_name=self.config.primary_command_names,
        )
        self.assertTrue(info['is_command'])
        self.assertEqual(info['command_name'], '矮人')
        self.assertEqual(info['command_argument'], 'add 这是一条新笑话')

        sub_info = self.function.match_greedy_command(info['command_argument'], self.config.subcommand_names)
        self.assertEqual(sub_info['command_name'], 'add')
        self.assertEqual(sub_info['command_argument'], '这是一条新笑话')

        admin_info = self.utils.parse_command(
            '。dwarfjokesadminadd10086',
            prefix_list=self.config.allowed_prefix_list,
            command_name=self.config.primary_command_names,
        )
        self.assertEqual(admin_info['command_name'], 'dwarfjokes')
        admin_sub = self.function.match_greedy_command(admin_info['command_argument'], self.config.subcommand_names)
        self.assertEqual(admin_sub['command_name'], 'admin')
        admin_action = self.function.match_greedy_command(admin_sub['command_argument'], self.config.admin_action_names)
        self.assertEqual(admin_action['command_name'], 'add')
        self.assertEqual(admin_action['command_argument'], '10086')

    def test_longer_command_wins_over_shorter_alias(self):
        info = self.utils.parse_command(
            '/矮人笑话10',
            prefix_list=self.config.allowed_prefix_list,
            command_name=self.config.primary_command_names,
        )
        self.assertEqual(info['command_name'], '矮人笑话')
        self.assertEqual(self.function.parse_draw_count(info['command_argument']), 10)

        dwarf_info = self.utils.parse_command(
            '.dwarfjokes',
            prefix_list=self.config.allowed_prefix_list,
            command_name=self.config.primary_command_names,
        )
        self.assertEqual(dwarf_info['command_name'], 'dwarfjokes')

    def test_draw_count_clamps_to_one_through_ten(self):
        self.assertEqual(self.function.parse_draw_count('10'), 10)
        self.assertEqual(self.function.parse_draw_count('99'), 10)
        self.assertEqual(self.function.parse_draw_count('0'), 1)
        self.assertEqual(self.function.parse_draw_count('-3'), 1)
        self.assertEqual(self.function.parse_draw_count('7'), 7)
        self.assertIsNone(self.function.parse_draw_count('10abc'))
        self.assertIsNone(self.function.parse_draw_count('add'))
        self.assertIsNone(self.function.parse_draw_count(''))

    def test_next_id_fills_gaps_then_increments(self):
        joke_list = self.function.load_joke_pack()
        self.assertEqual(self.function.get_next_joke_id(joke_list), 2)
        add_result = self.function.add_joke('联合驾驶协会决定停止向矮人颁发驾驶证。')
        self.assertTrue(add_result['ok'])
        self.assertEqual(add_result['id'], 2)
        self.assertEqual(add_result['count'], 3)
        self.assertEqual(self.function.get_next_joke_id(self.function.load_joke_pack()), 4)

    def test_delete_then_add_reuses_deleted_id(self):
        delete_result = self.function.delete_joke(1)
        self.assertTrue(delete_result['ok'])
        self.assertEqual(delete_result['count'], 1)
        add_result = self.function.add_joke('反直觉地，矮人是天下最高的种族。')
        self.assertTrue(add_result['ok'])
        self.assertEqual(add_result['id'], 1)

    def test_duplicate_uses_olivadice_rank_gate(self):
        original = '问：为什么矮人总是不受其他种族的重视？答：因为他们之中没有高人。'
        duplicate = self.function.add_joke(original)
        self.assertFalse(duplicate['ok'])
        self.assertEqual(duplicate['reason'], 'duplicate')
        self.assertEqual(duplicate['id'], 1)
        self.assertEqual(duplicate['rank'], 0)

        substring = self.function.add_joke('为什么矮人总是不受其他种族的重视')
        self.assertFalse(substring['ok'])
        self.assertEqual(substring['reason'], 'duplicate')
        self.assertLess(substring['rank'], self.config.joke_duplicate_rank_gate)

        paraphrase = self.function.add_joke(
            '问：为什么矮人总是不受其他种族的重视？答：因为他们里面没有高人。'
        )
        self.assertFalse(paraphrase['ok'])
        self.assertEqual(paraphrase['id'], 1)

        fresh = self.function.add_joke('精灵点了一杯超大杯咖啡，矮人看了一眼说：这也叫高？')
        self.assertTrue(fresh['ok'])
        self.assertEqual(fresh['id'], 2)

    def test_local_rank_matches_core_when_available(self):
        if not (CORE_ROOT / 'OlivaDiceCore' / 'helpDoc.py').is_file():
            self.skipTest('本机没有 OlivaDiceCore 源码目录')
        if str(CORE_ROOT) not in sys.path:
            sys.path.insert(0, str(CORE_ROOT))
        try:
            import OlivaDiceCore.helpDoc as help_doc
        except Exception as exception_object:
            self.skipTest(f'无法导入 OlivaDiceCore.helpDoc：{type(exception_object).__name__}')

        samples = [
            ('hello', 'hello'),
            ('矮人笑话', '矮人笑话合集'),
            ('abc', 'xyzxyzxyzxyz'),
            (
                '问：为什么矮人总是不受其他种族的重视？答：因为他们之中没有高人。',
                '问：为什么矮人总是不受其他种族的重视？答：因为他们之中没有高人。',
            ),
        ]
        for left, right in samples:
            with self.subTest(left=left, right=right):
                self.assertEqual(
                    self.function.get_local_recommend_rank(left, right),
                    help_doc.getRecommendRank(left, right),
                )

    def test_get_joke_by_id(self):
        joke_item = self.function.get_joke_by_id(1)
        self.assertIsNotNone(joke_item)
        self.assertEqual(joke_item['id'], 1)
        self.assertIn('没有高人', joke_item['text'])
        self.assertIsNone(self.function.get_joke_by_id(2))
        self.assertIsNone(self.function.get_joke_by_id(99))

    def test_draw_from_empty_pack(self):
        self.function.save_joke_pack([])
        draw_result = self.function.draw_jokes(3)
        self.assertFalse(draw_result['ok'])
        self.assertEqual(draw_result['reason'], 'empty_pack')

    def test_draw_does_not_exceed_available_jokes(self):
        draw_result = self.function.draw_jokes(10)
        self.assertTrue(draw_result['ok'])
        self.assertEqual(len(draw_result['jokes']), 2)

    def test_normalize_id_list_keeps_uinfo_hash(self):
        hex_id = 'A9EEAF03BE4844ED78B6523A63D0728F'
        record_hash = '97044885a4820bae161671fb34253587'
        self.assertEqual(self.utils.normalize_id_list(hex_id), [hex_id])
        self.assertEqual(self.utils.normalize_id_list(f'({hex_id})'), [hex_id])
        self.assertEqual(self.utils.normalize_id_list('12345'), ['12345'])
        self.assertEqual(self.utils.normalize_id_list('host123|group456'), ['host123|group456'])
        self.assertEqual(self.utils.normalize_id_list(['abc123', 'ABC123']), ['abc123'])
        self.assertEqual(self.utils.normalize_id_list('oops'), [])
        uinfo = (
            f'[亮亮] - ({hex_id})\n'
            f'记录哈希: {record_hash}\n'
            '平台: qqGuild'
        )
        result = self.utils.normalize_id_list(uinfo)
        self.assertEqual(result[0], hex_id)
        self.assertIn(record_hash, result)
        self.assertNotIn('qqGuild', result)
        self.assertNotIn('9034844786523630728', result)


if __name__ == '__main__':
    unittest.main()
