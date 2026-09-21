"""使用真实存储封装和模拟的 OlivOS 事件验证 WebUI，不接触运行中插件数据。"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


TEMPLATE_DIR = Path(__file__).resolve().parents[1]
PLUGIN_DIR = TEMPLATE_DIR / 'YourPluginName'
PACKAGE = '_light_template_webui_test'


class WebUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Tkinter 不可用时也必须能够加载整个插件和网页接口。
        cls.modules_patch = patch.dict(sys.modules, {'OlivOS': types.ModuleType('OlivOS'), 'tkinter': None})
        cls.modules_patch.start()
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_DIR / '__init__.py')
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        cls.main = package.main
        cls.webui = package.main.webui
        cls.utils = package.main.utils
        cls.config = cls.webui.config
        cls.messages = cls.webui.message_custom

    @classmethod
    def tearDownClass(cls):
        cls.modules_patch.stop()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='light-webui-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        data_patch = patch.object(self.config, 'plugin_data_dir', str(self.root / 'data'))
        data_patch.start()
        self.addCleanup(data_patch.stop)
        self.parent_hash = 'a' * 32
        self.child_hash = 'b' * 32
        link_patch = patch.object(
            self.utils, 'get_linked_bot_hash', side_effect=lambda value: self.parent_hash
            if value == self.child_hash else value,
        )
        link_patch.start()
        self.addCleanup(link_patch.stop)
        bots = {
            self.parent_hash: types.SimpleNamespace(id=10001, name='主账号', platform={'platform': 'qq'}),
            self.child_hash: types.SimpleNamespace(id=10002, name='从账号', platform={'platform': 'qq'}),
        }
        self.proc = types.SimpleNamespace(Proc_data={'bot_info_dict': bots}, log=Mock())

    def event(self, payload):
        return types.SimpleNamespace(
            bot_info=None,
            data=types.SimpleNamespace(
                namespace='YourPluginName', event=self.config.webui_event,
                webui={'request_id': 'test-request', 'session': 'test-only-private-context'}, payload=payload,
            ),
            send=Mock(return_value=True),
        )

    def call(self, action, **fields):
        event = self.event({'action': action, 'bot_hash': self.child_hash, **fields})
        self.main.Event.menu(event, self.proc)
        event.send.assert_called_once()
        destination, request_id, response = event.send.call_args.args
        self.assertEqual((destination, request_id), ('webui', 'test-request'))
        json.dumps(response, ensure_ascii=False)
        return response

    def test_registered_page_exists_and_manifest_has_no_bom(self):
        data = (PLUGIN_DIR / 'app.json').read_bytes()
        self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
        manifest = json.loads(data)
        for page in manifest['webui_config']:
            self.assertTrue((PLUGIN_DIR / page['path']).is_file())

    def test_state_uses_raw_bot_and_linked_replies_without_private_context(self):
        self.proc.Proc_data['bot_info_dict'][self.child_hash].post_info = {'private': 'private-bot-marker'}
        self.utils.save_bot_config(self.child_hash, {'custom_private_field': 'private-config-marker'})
        response = self.call('get_state')
        self.assertTrue(response['ok'])
        bot = response['state']['bot']
        self.assertEqual(bot['hash'], self.child_hash)
        self.assertEqual(bot['linked_hash'], self.parent_hash)
        self.assertEqual(Path(bot['config_directory']).name, self.child_hash)
        self.assertEqual(Path(bot['reply_directory']).name, self.parent_hash)
        encoded = json.dumps(response)
        for marker in ('private-bot-marker', 'private-config-marker', 'test-only-private-context'):
            self.assertNotIn(marker, encoded)

    def test_global_settings_remain_available_without_bots(self):
        self.proc.Proc_data['bot_info_dict'] = {}
        self.utils.save_global_config({'future_setting': 'keep'})
        response = self.call('save_global', global_enable_switch=False, global_debug_mode_switch=True)
        self.assertTrue(response['ok'])
        self.assertIsNone(response['state']['bot'])
        self.assertEqual(response['state']['bots'], [])
        self.assertFalse(self.utils.load_global_config()['global_enable_switch'])
        self.assertEqual(self.utils.load_global_config()['future_setting'], 'keep')
        self.assertTrue(self.call('save_global', global_enable_switch=True, global_debug_mode_switch=False)['ok'])

    def test_boolean_validation_does_not_partially_save(self):
        self.utils.save_global_config(self.config.default_global_config)
        before = Path(self.utils.get_global_config_file_path()).read_bytes()
        for invalid in ('false', 0, None, [], {}):
            with self.subTest(invalid=invalid):
                self.assertFalse(self.call(
                    'save_global', global_enable_switch=False, global_debug_mode_switch=invalid,
                )['ok'])
                self.assertEqual(Path(self.utils.get_global_config_file_path()).read_bytes(), before)
                self.assertFalse(self.call('save_bot', bot_enable_switch=invalid)['ok'])

    def test_bot_and_master_changes_preserve_other_fields_and_raw_isolation(self):
        self.utils.save_bot_config(self.parent_hash, {'configured_master_list': ['111']})
        self.utils.save_bot_config(self.child_hash, {'disabled_group_list': ['333'], 'future_setting': 'keep'})
        self.assertTrue(self.call('save_bot', bot_enable_switch=False)['ok'])
        self.assertTrue(self.call('add_masters', ids=['222', '444', '222'])['ok'])
        self.assertTrue(self.call('add_masters', ids=['222'])['ok'])
        self.assertEqual(self.utils.get_configured_master_list(self.child_hash), ['222', '444'])
        self.assertTrue(self.call('remove_masters', ids=['222'])['ok'])
        self.assertTrue(self.call('remove_masters', ids=['222'])['ok'])
        actual = self.utils.load_bot_config(self.child_hash)
        self.assertFalse(actual['bot_enable_switch'])
        self.assertEqual(actual['configured_master_list'], ['444'])
        self.assertEqual(actual['disabled_group_list'], ['333'])
        self.assertEqual(actual['future_setting'], 'keep')
        self.assertEqual(self.utils.get_configured_master_list(self.parent_hash), ['111'])
        self.assertTrue(self.utils.load_bot_config(self.parent_hash)['bot_enable_switch'])

    def test_master_validation_rejects_mixed_or_non_string_ids(self):
        for ids in ([], '123', ['123', 'oops456'], [123], ['-123'], ['1' * 33], ['１２３']):
            with self.subTest(ids=ids):
                self.assertFalse(self.call('add_masters', ids=ids)['ok'])
                self.assertEqual(self.utils.get_configured_master_list(self.child_hash), [])

    def test_reply_save_reset_and_extension_delete_share_parent_storage(self):
        self.assertTrue(self.call('save_reply', key='reply_ping', value='自定义\n{user_name}')['ok'])
        self.assertEqual(self.utils.load_bot_message_custom(self.parent_hash)['reply_ping'], '自定义\n{user_name}')
        self.assertFalse((self.root / 'data' / self.child_hash / 'message_custom.json').exists())
        self.assertFalse(self.call('reset_reply', key='reply_ping')['ok'])
        self.assertTrue(self.call('reset_reply', key='reply_ping', confirm=True)['ok'])
        self.assertEqual(
            self.utils.load_bot_message_custom(self.parent_hash)['reply_ping'],
            self.messages.default_custom_message_dict['reply_ping'],
        )
        self.utils.set_bot_message_custom_value(self.parent_hash, 'extension_reply', '扩展')
        self.assertTrue(self.call('save_reply', key='extension_reply', value='修改扩展')['ok'])
        self.assertTrue(self.call('reset_reply', key='extension_reply', confirm=True)['ok'])
        self.assertNotIn('extension_reply', self.utils.load_bot_message_custom(self.parent_hash))

    def test_reset_all_requires_confirmation_and_preserves_other_storage(self):
        self.utils.set_bot_message_custom_value(self.parent_hash, 'extension_reply', '扩展')
        self.utils.save_bot_message_variables(self.parent_hash, {'variable': '保留'})
        self.assertFalse(self.call('reset_replies', confirm=False)['ok'])
        self.assertIn('extension_reply', self.utils.load_bot_message_custom(self.parent_hash))
        self.assertTrue(self.call('reset_replies', confirm=True)['ok'])
        self.assertEqual(
            self.utils.load_bot_message_custom(self.parent_hash), self.messages.default_custom_message_dict,
        )
        self.assertEqual(self.utils.load_bot_message_variables(self.parent_hash)['variable'], '保留')

    def test_invalid_targets_and_reply_values_do_not_write(self):
        for bot_hash in ('../outside', '', 'unknown', None, {}):
            with self.subTest(bot_hash=bot_hash):
                self.assertFalse(self.call('save_bot', bot_hash=bot_hash, bot_enable_switch=False)['ok'])
        self.assertFalse(self.call('save_reply', key='missing', value='content')['ok'])
        self.assertFalse(self.call('save_reply', key='reply_ping', value='x' * 32769)['ok'])
        self.assertFalse(self.call('save_reply', key='reply_ping', value={})['ok'])
        self.assertFalse(self.call('unknown')['ok'])
        self.assertEqual(list(self.root.rglob('*.json')), [])

    def test_missing_bot_on_refresh_falls_back_to_current_accounts(self):
        self.proc.Proc_data['bot_info_dict'].pop(self.child_hash)
        response = self.call('get_state')
        self.assertEqual(response['state']['bot']['hash'], self.parent_hash)
        self.assertFalse(self.call('save_bot', bot_enable_switch=True)['ok'])

    def test_save_failure_and_exception_are_reported_without_sensitive_details(self):
        with patch.object(self.utils, 'save_global_config', return_value=False):
            self.assertFalse(self.call('save_global', global_enable_switch=True, global_debug_mode_switch=False)['ok'])
        with patch.object(self.utils, 'load_global_config', side_effect=OSError('private-error-marker')):
            response = self.call('get_state')
            self.assertFalse(response['ok'])
            self.assertNotIn('private-error-marker', json.dumps(response))
            self.assertNotIn('private-error-marker', str(self.proc.log.call_args_list))

    def test_invalid_context_is_ignored_and_unknown_requests_receive_error(self):
        invalid_contexts = (('OtherPlugin', 'id'), ('YourPluginName', ''), ('YourPluginName', 'x' * 129))
        for namespace, request_id in invalid_contexts:
            event = self.event({'action': 'get_state'})
            event.data.namespace = namespace
            event.data.webui['request_id'] = request_id
            self.main.Event.menu(event, self.proc)
            event.send.assert_not_called()
        for payload in (None, [], 'not an object'):
            event = self.event(payload)
            self.main.Event.menu(event, self.proc)
            self.assertFalse(event.send.call_args.args[2]['ok'])
        event = self.event({'action': 'get_state'})
        event.data.event = 'YourPluginName_Menu_001'
        self.main.Event.menu(event, self.proc)
        self.assertFalse(event.send.call_args.args[2]['ok'])

    def test_native_menu_still_routes_to_gui(self):
        gui = types.ModuleType(f'{PACKAGE}.gui')
        gui.handle_menu_event = Mock()
        event = types.SimpleNamespace(
            data=types.SimpleNamespace(namespace='YourPluginName', event='YourPluginName_Menu_001'),
        )
        with patch.dict(sys.modules, {f'{PACKAGE}.gui': gui}):
            self.main.Event.menu(event, self.proc)
        gui.handle_menu_event.assert_called_once_with(event, self.proc)

    def test_reply_transport_failure_does_not_escape_event_handler(self):
        event = self.event({'action': 'get_state'})
        event.send.side_effect = RuntimeError('transport failed')
        self.main.Event.menu(event, self.proc)
        self.proc.log.assert_called()

    def test_unknown_prefixed_command_is_silent(self):
        event = types.SimpleNamespace()
        global_config = self.config.default_global_config.copy()
        bot_config = self.config.default_bot_config.copy()
        with patch.object(self.main.message.utils, 'ensure_runtime_storage_by_event', return_value=self.child_hash), \
                patch.object(self.main.message.utils, 'check_core_group_enable', return_value=True), \
                patch.object(self.main.message.utils, 'get_message_text_from_event', return_value='.unknown'), \
                patch.object(self.main.message.utils, 'load_global_config', return_value=global_config), \
                patch.object(self.main.message.utils, 'load_bot_config', return_value=bot_config), \
                patch.object(self.main.message.utils, 'is_group_disabled', return_value=False), \
                patch.object(self.main.message.utils, 'reply_message') as reply_message:
            self.main.message.handle_message(event, self.proc)
        reply_message.assert_not_called()

    def test_reply_message_does_not_quote_by_default(self):
        event = types.SimpleNamespace(
            data=types.SimpleNamespace(group_id='123', message_id='456'),
            reply=Mock(return_value=True),
        )
        self.utils.reply_message(event, 'hello')
        event.reply.assert_called_once_with('hello')
        event.reply.reset_mock()
        self.utils.reply_message(event, 'hello', quote_reply=True)
        event.reply.assert_called_once_with('[OP:reply,id=456]hello')


if __name__ == '__main__':
    unittest.main()
