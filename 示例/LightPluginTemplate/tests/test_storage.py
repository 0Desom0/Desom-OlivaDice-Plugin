# -*- encoding: utf-8 -*-
"""验证配置读写与运行期初始化：坏文件不被覆盖、写入原子、消息热路径不再重写配置。"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


TEMPLATE_DIR = Path(__file__).resolve().parents[1]
PLUGIN_DIR = TEMPLATE_DIR / 'YourPluginName'
PACKAGE = '_light_template_storage_test'


class StorageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules_patch = patch.dict(
            sys.modules,
            {'OlivOS': types.ModuleType('OlivOS'), 'tkinter': None},
        )
        cls.modules_patch.start()
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_DIR / '__init__.py')
        assert spec and spec.loader
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        cls.utils = package.main.utils
        cls.config = package.main.utils.config

    @classmethod
    def tearDownClass(cls):
        cls.modules_patch.stop()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='light-storage-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        data_patch = patch.object(self.config, 'plugin_data_dir', str(self.root / 'data'))
        data_patch.start()
        self.addCleanup(data_patch.stop)
        self.addCleanup(self.utils.initialized_storage_map.clear)

    def event(self, bot_hash='a' * 32, bot_id=10001):
        return types.SimpleNamespace(bot_info=types.SimpleNamespace(hash=bot_hash, id=bot_id))

    def test_corrupt_bot_config_is_archived_before_defaults(self):
        """坏掉的 bot_config 必须先归档，再返回默认值，且留下日志。"""
        bot_hash = 'c' * 32
        config_path = Path(self.utils.get_bot_config_file_path(bot_hash))
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"bot_enable_switch": tru', encoding='utf-8')

        loaded = self.utils.load_bot_config(bot_hash)

        self.assertIs(loaded['bot_enable_switch'], True)
        self.assertEqual(loaded['configured_master_list'], [])
        self.assertFalse(config_path.exists(), '坏文件应已被改名归档')
        archived = sorted(config_path.parent.glob('bot_config.json.corrupt-*'))
        self.assertEqual(len(archived), 1)
        self.assertIn('tru', archived[0].read_text(encoding='utf-8'))

        log_path = Path(self.utils.get_persist_error_log_path())
        self.assertTrue(log_path.is_file())
        log_text = log_path.read_text(encoding='utf-8')
        self.assertIn('Bot 配置 读取失败', log_text)
        self.assertIn(archived[0].name, log_text)

    def test_missing_file_returns_defaults_without_noise(self):
        """文件不存在是首次运行的正常情况，不该产生归档或错误日志。"""
        bot_hash = 'd' * 32
        loaded = self.utils.load_bot_config(bot_hash)
        self.assertIs(loaded['bot_enable_switch'], True)
        self.assertEqual(list(Path(self.config.plugin_data_dir).rglob('*.corrupt-*')), [])
        self.assertFalse(Path(self.utils.get_persist_error_log_path()).exists())

    def test_save_json_file_is_atomic_and_keeps_backup(self):
        """写入走临时文件 + 原子替换；覆盖前留一份 .bak。"""
        target = Path(self.root / 'data' / 'case.json')
        self.assertTrue(self.utils.save_json_file(target, {'value': 1}, '用例'))
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'value': 1})
        backup = target.with_name(target.name + '.bak')
        self.assertFalse(backup.exists(), '首次写入没有旧文件，不应产生 .bak')

        self.assertTrue(self.utils.save_json_file(target, {'value': 2}, '用例'))
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'value': 2})
        self.assertTrue(backup.is_file())
        self.assertEqual(json.loads(backup.read_text(encoding='utf-8')), {'value': 1})
        self.assertEqual(list(target.parent.glob('*.tmp-*')), [])

    def test_runtime_init_no_longer_rewrites_config_per_message(self):
        """模拟「配置在磁盘上被改坏 + 又来一条消息」：不能再被默认值覆盖。"""
        event = self.event()
        self.utils.ensure_runtime_storage_by_event(event, None)
        config_path = Path(self.utils.get_bot_config_file_path(event.bot_info.hash))
        self.assertTrue(config_path.is_file())

        config_path.write_text('{broken', encoding='utf-8')
        broken_bytes = config_path.read_bytes()
        for _ in range(5):
            self.utils.ensure_runtime_storage_by_event(event, None)
        self.assertEqual(config_path.read_bytes(), broken_bytes, '消息热路径不应重写配置')

    def test_force_reinit_recovers_corrupt_config(self):
        """force=True 时按磁盘现状重新初始化：坏文件归档，写回可用默认值。"""
        event = self.event(bot_hash='e' * 32)
        self.utils.ensure_runtime_storage_by_event(event, None)
        config_path = Path(self.utils.get_bot_config_file_path(event.bot_info.hash))
        config_path.write_text('{broken', encoding='utf-8')

        self.utils.ensure_runtime_storage_by_event(event, None, force=True)

        self.assertTrue(config_path.is_file())
        self.assertEqual(json.loads(config_path.read_text(encoding='utf-8'))['bot_enable_switch'], True)
        self.assertEqual(len(list(config_path.parent.glob('bot_config.json.corrupt-*'))), 1)

    def test_initialize_creates_files_only_when_missing(self):
        """初始化只在缺失时落盘；已存在的配置内容不被改写。"""
        bot_hash = 'f' * 32
        self.utils.save_bot_config(bot_hash, {'bot_enable_switch': False})
        config_path = Path(self.utils.get_bot_config_file_path(bot_hash))
        before = config_path.read_text(encoding='utf-8')

        self.utils.initialize_bot_storage(bot_hash, bot_id=10001)
        self.assertEqual(config_path.read_text(encoding='utf-8'), before)
        self.assertFalse(self.utils.load_bot_config(bot_hash)['bot_enable_switch'])

    def test_persist_error_log_is_capped_in_memory(self):
        """内存里的最近错误列表有上限，不会无限增长。"""
        for index in range(30):
            self.utils.record_persist_error('用例错误 %d' % index)
        recent = self.utils.get_recent_persist_errors()
        self.assertEqual(len(recent), 20)
        self.assertIn('用例错误 29', recent[-1])


if __name__ == '__main__':
    unittest.main()
