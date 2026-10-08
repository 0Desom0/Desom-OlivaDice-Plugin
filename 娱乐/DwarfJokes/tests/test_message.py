# -*- encoding: utf-8 -*-
"""矮人笑话命令分发与权限测试。"""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = '_dwarfjokes_message_test'


class FakeEvent:
    def __init__(self, message_text, user_id='10001', group_id='20001'):
        self.bot_info = types.SimpleNamespace(hash='a' * 32, id=90001)
        self.platform = {'platform': 'qq'}
        self.plugin_info = {'func_type': 'group_message'}
        self.base_info = {'self_id': 90001}
        self.data = types.SimpleNamespace(
            message=message_text,
            user_id=user_id,
            group_id=group_id,
            host_id='',
            sender={'name': '测试员', 'role': 'member'},
            message_id='1',
        )
        self.reply = Mock(return_value=True)


class DwarfJokesMessageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules_patch = patch.dict(sys.modules, {'OlivOS': types.ModuleType('OlivOS'), 'tkinter': None})
        cls.modules_patch.start()
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_DIR / '__init__.py')
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        cls.main = package.main
        cls.message = package.main.message
        cls.function = package.main.message.function
        cls.utils = package.main.utils
        cls.config = package.main.utils.config

    @classmethod
    def tearDownClass(cls):
        cls.modules_patch.stop()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='dwarfjokes-message-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        data_patch = patch.object(self.config, 'plugin_data_dir', str(self.root / 'data'))
        data_patch.start()
        self.addCleanup(data_patch.stop)
        self.function.joke_pack_cache.update({'path': '', 'mtime': None, 'jokes': []})
        self.bot_hash = 'a' * 32
        self.utils.initialize_bot_storage(self.bot_hash, bot_id='90001')
        self.function.save_joke_pack(
            [self.function.make_joke_item(1, '问：为什么一般来说矮人都很友善？答：因为他们都具有矮心。')]
        )
        self.proc = types.SimpleNamespace(Proc_data={'bot_info_dict': {}}, log=Mock())

    def test_unknown_command_is_silent(self):
        event = FakeEvent('.unknown')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash):
            self.message.handle_message(event, self.proc)
        event.reply.assert_not_called()

    def test_unmatched_argument_is_silent(self):
        event = FakeEvent('.矮人 咖啡')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash):
            self.message.handle_message(event, self.proc)
        event.reply.assert_not_called()

    def test_draw_and_list_and_help(self):
        event = FakeEvent('.矮人')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash):
            self.message.handle_message(event, self.proc)
        event.reply.assert_called()
        self.assertIn('矮人笑话', event.reply.call_args.args[0])

        list_event = FakeEvent('.矮人list')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash):
            self.message.handle_message(list_event, self.proc)
        self.assertIn('当前共有 1 条', list_event.reply.call_args.args[0])

        help_event = FakeEvent('.矮人帮助')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash):
            self.message.handle_message(help_event, self.proc)
        self.assertIn('DwarfJokes', help_event.reply.call_args.args[0])
        self.assertIn('带序号则展示指定笑话', help_event.reply.call_args.args[0])

    def _handle_message(self, event):
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash):
            self.message.handle_message(event, self.proc)

    def test_list_by_id_shows_specified_joke(self):
        greedy_event = FakeEvent('.矮人list1')
        self._handle_message(greedy_event)
        self.assertIn('【矮人笑话 #1】', greedy_event.reply.call_args.args[0])
        self.assertIn('矮心', greedy_event.reply.call_args.args[0])

        spaced_event = FakeEvent('.矮人show 1')
        self._handle_message(spaced_event)
        self.assertIn('【矮人笑话 #1】', spaced_event.reply.call_args.args[0])

        chinese_event = FakeEvent('.矮人 展示 1')
        self._handle_message(chinese_event)
        self.assertIn('【矮人笑话 #1】', chinese_event.reply.call_args.args[0])

        missing_event = FakeEvent('.矮人list999')
        self._handle_message(missing_event)
        self.assertIn('序号 999 不存在', missing_event.reply.call_args.args[0])

        invalid_event = FakeEvent('.矮人show abc')
        self._handle_message(invalid_event)
        self.assertIn('请提供有效的正整数序号', invalid_event.reply.call_args.args[0])

        zero_event = FakeEvent('.矮人list0')
        self._handle_message(zero_event)
        self.assertIn('请提供有效的正整数序号', zero_event.reply.call_args.args[0])

    def test_add_requires_permission_and_reports_duplicate(self):
        guest = FakeEvent('.矮人add 新的一条矮人笑话')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'is_sender_core_master', return_value=False), \
                patch.object(self.utils, 'is_sender_configured_master', return_value=False), \
                patch.object(self.utils, 'is_sender_configured_admin', return_value=False):
            self.message.handle_message(guest, self.proc)
        self.assertIn('权限不足', guest.reply.call_args.args[0])

        master = FakeEvent('.矮人add 新的一条矮人笑话')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'is_sender_core_master', return_value=True), \
                patch.object(self.utils, 'is_sender_configured_master', return_value=False), \
                patch.object(self.utils, 'is_sender_configured_admin', return_value=False):
            self.message.handle_message(master, self.proc)
        self.assertIn('添加成功', master.reply.call_args.args[0])
        self.assertIn('序号是 2', master.reply.call_args.args[0])

        duplicate = FakeEvent('.矮人添加 新的一条矮人笑话')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'is_sender_core_master', return_value=False), \
                patch.object(self.utils, 'is_sender_configured_master', return_value=False), \
                patch.object(self.utils, 'is_sender_configured_admin', return_value=True):
            self.message.handle_message(duplicate, self.proc)
        self.assertIn('添加失败', duplicate.reply.call_args.args[0])
        self.assertIn('序号 2', duplicate.reply.call_args.args[0])

    def test_admin_requires_master_not_plugin_admin(self):
        admin_user = FakeEvent('.矮人admin add 12345')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'is_sender_core_master', return_value=False), \
                patch.object(self.utils, 'is_sender_configured_master', return_value=False), \
                patch.object(self.utils, 'is_sender_configured_admin', return_value=True):
            self.message.handle_message(admin_user, self.proc)
        self.assertIn('只有 OlivaDiceCore 骰主或本插件骰主', admin_user.reply.call_args.args[0])

        master = FakeEvent('.矮人adminadd12345')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'is_sender_core_master', return_value=True), \
                patch.object(self.utils, 'is_sender_configured_master', return_value=False), \
                patch.object(self.utils, 'is_sender_configured_admin', return_value=False):
            self.message.handle_message(master, self.proc)
        self.assertIn('已添加插件管理员', master.reply.call_args.args[0])
        self.assertEqual(self.utils.get_configured_admin_list(self.bot_hash), ['12345'])

    def test_admin_add_keeps_qqguild_uinfo_hash(self):
        hex_id = 'A9EEAF03BE4844ED78B6523A63D0728F'
        master = FakeEvent(f'.矮人 admin add {hex_id}')
        with patch.object(self.utils, 'ensure_runtime_storage_by_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash), \
                patch.object(self.utils, 'is_sender_core_master', return_value=True), \
                patch.object(self.utils, 'is_sender_configured_master', return_value=False), \
                patch.object(self.utils, 'is_sender_configured_admin', return_value=False):
            self.message.handle_message(master, self.proc)
        self.assertIn(hex_id, master.reply.call_args.args[0])
        self.assertEqual(self.utils.get_configured_admin_list(self.bot_hash), [hex_id])
        self.assertNotIn('9034844786523630728', self.utils.get_configured_admin_list(self.bot_hash))

    def test_configured_admin_matches_uinfo_user_id_and_record_hash(self):
        hex_id = 'A9EEAF03BE4844ED78B6523A63D0728F'
        event = FakeEvent('.矮人add x', user_id=hex_id)
        event.platform = {'platform': 'qqGuild'}
        self.utils.set_configured_admin_list(self.bot_hash, [hex_id.lower()])
        with patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash):
            self.assertTrue(self.utils.is_sender_configured_admin(event))
        record_hash = self.utils.get_user_hash(hex_id, 'user', 'qqGuild')
        self.utils.set_configured_admin_list(self.bot_hash, [record_hash])
        with patch.object(self.utils, 'get_bot_hash_from_event', return_value=self.bot_hash):
            self.assertTrue(self.utils.is_sender_configured_admin(event))


if __name__ == '__main__':
    unittest.main()
