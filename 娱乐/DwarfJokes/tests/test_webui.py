# -*- encoding: utf-8 -*-
"""验证 DwarfJokes WebUI 接口与 app.json 配置。"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = '_dwarfjokes_webui_test'


class DwarfJokesWebUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules_patch = patch.dict(sys.modules, {'OlivOS': types.ModuleType('OlivOS'), 'tkinter': None})
        cls.modules_patch.start()
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_DIR / '__init__.py')
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        cls.main = package.main
        cls.webui = package.main.webui
        cls.utils = package.main.utils
        cls.function = package.main.webui.function
        cls.config = cls.webui.config
        cls.messages = cls.utils.message_custom

    @classmethod
    def tearDownClass(cls):
        cls.modules_patch.stop()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='dwarfjokes-webui-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        data_patch = patch.object(self.config, 'plugin_data_dir', str(self.root / 'data'))
        data_patch.start()
        self.addCleanup(data_patch.stop)
        self.function.joke_pack_cache.update({'path': '', 'mtime': None, 'jokes': []})
        self.parent_hash = 'a' * 32
        self.child_hash = 'b' * 32
        link_patch = patch.object(
            self.utils,
            'get_linked_bot_hash',
            side_effect=lambda value: self.parent_hash if value == self.child_hash else value,
        )
        link_patch.start()
        self.addCleanup(link_patch.stop)
        bots = {
            self.parent_hash: types.SimpleNamespace(id=10001, name='主账号', platform={'platform': 'qq'}),
            self.child_hash: types.SimpleNamespace(id=10002, name='从账号', platform={'platform': 'qq'}),
        }
        self.proc = types.SimpleNamespace(Proc_data={'bot_info_dict': bots}, log=Mock())
        self.function.save_joke_pack(
            [self.function.make_joke_item(1, '问：为什么矮人使用不了望远镜？答：因为目光短浅。')]
        )

    def event(self, payload):
        return types.SimpleNamespace(
            bot_info=None,
            data=types.SimpleNamespace(
                namespace='DwarfJokes',
                event=self.config.webui_event,
                webui={'request_id': 'test-request', 'session': 'test-only-private-context'},
                payload=payload,
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

    def overlay(self, bot_hash):
        path = Path(self.utils.get_message_custom_file_path(bot_hash))
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding='utf-8'))

    def reply_item(self, key, bot_hash=None):
        response = self.call('get_state', bot_hash=bot_hash or self.child_hash)
        self.assertTrue(response['ok'])
        return next(item for item in response['state']['bot']['replies'] if item['key'] == key)

    def test_registered_page_exists_and_manifest_has_no_bom(self):
        data = (PLUGIN_DIR / 'app.json').read_bytes()
        self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(data[0], 0x7B)
        manifest = json.loads(data)
        self.assertEqual(manifest['namespace'], 'DwarfJokes')
        for page in manifest['webui_config']:
            self.assertTrue((PLUGIN_DIR / page['path']).is_file())
        html = (PLUGIN_DIR / 'webui' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('DwarfJokes_WebUI_Config', html)

    def test_state_includes_joke_pack_and_admins(self):
        response = self.call('get_state')
        self.assertTrue(response['ok'])
        joke_pack = response['state']['joke_pack']
        self.assertEqual(joke_pack['count'], 1)
        self.assertEqual(joke_pack['next_id'], 2)
        self.assertEqual(response['state']['bot']['admins'], [])
        self.assertIn('masters', response['state']['bot'])

    def test_add_and_delete_joke_from_webui(self):
        add_response = self.call('add_joke', text='矮人点餐只要半份，因为他们站不到柜台那么高。')
        self.assertTrue(add_response['ok'])
        self.assertEqual(add_response['result']['id'], 2)
        self.assertEqual(add_response['state']['joke_pack']['count'], 2)

        duplicate = self.call('add_joke', text='矮人点餐只要半份，因为他们站不到柜台那么高。')
        self.assertFalse(duplicate['ok'])
        self.assertIn('序号 2', duplicate['error'])

        delete_response = self.call('delete_joke', id=2)
        self.assertTrue(delete_response['ok'])
        self.assertEqual(delete_response['state']['joke_pack']['count'], 1)
        self.assertEqual(delete_response['state']['joke_pack']['next_id'], 2)

    def test_draw_jokes_returns_text(self):
        response = self.call('draw_jokes', count=1)
        self.assertTrue(response['ok'])
        self.assertIn('矮人笑话', response['result']['text'])

    def test_admin_list_is_raw_bot_isolated(self):
        self.assertTrue(self.call('add_admins', ids=['222', '444', '222'])['ok'])
        self.assertEqual(self.utils.get_configured_admin_list(self.child_hash), ['222', '444'])
        self.assertEqual(self.utils.get_configured_admin_list(self.parent_hash), [])
        self.assertTrue(self.call('remove_admins', ids=['222'])['ok'])
        self.assertEqual(self.utils.get_configured_admin_list(self.child_hash), ['444'])

    def test_bot_and_master_changes_preserve_admin_and_other_fields(self):
        self.utils.save_bot_config(self.child_hash, {
            'disabled_group_list': ['333'],
            'configured_admin_list': ['555'],
            'future_setting': 'keep',
        })
        self.assertTrue(self.call('save_bot', bot_enable_switch=False)['ok'])
        self.assertTrue(self.call('add_masters', ids=['222'])['ok'])
        actual = self.utils.load_bot_config(self.child_hash)
        self.assertFalse(actual['bot_enable_switch'])
        self.assertEqual(actual['configured_master_list'], ['222'])
        self.assertEqual(actual['configured_admin_list'], ['555'])
        self.assertEqual(actual['disabled_group_list'], ['333'])
        self.assertEqual(actual['future_setting'], 'keep')

    def test_invalid_joke_payload_is_rejected(self):
        self.assertFalse(self.call('add_joke', text='')['ok'])
        self.assertFalse(self.call('add_joke', text=123)['ok'])
        self.assertFalse(self.call('delete_joke', id=0)['ok'])
        self.assertFalse(self.call('delete_joke', id='1')['ok'])
        self.assertFalse(self.call('draw_jokes', count='1')['ok'])
        self.assertEqual(self.function.get_joke_pack_summary()['count'], 1)

    def test_native_menu_still_routes_to_gui(self):
        gui = types.ModuleType(f'{PACKAGE}.gui')
        gui.handle_menu_event = Mock()
        event = types.SimpleNamespace(
            data=types.SimpleNamespace(namespace='DwarfJokes', event='DwarfJokes_Menu_001'),
        )
        with patch.object(self.main, 'gui', gui):
            self.main.Event.menu(event, self.proc)
        gui.handle_menu_event.assert_called_once_with(event, self.proc)

    def test_native_menu_without_gui_logs_real_import_error(self):
        event = types.SimpleNamespace(
            data=types.SimpleNamespace(namespace='DwarfJokes', event='DwarfJokes_Menu_001'),
        )
        self.assertIsNone(self.main.gui)
        self.main.Event.menu(event, self.proc)
        logged = self.proc.log.call_args.args[1]
        self.assertIn('无法打开桌面配置面板', logged)
        self.assertIn('请改用 OlivOS WebUI 配置页面', logged)

    def test_invalid_context_is_ignored(self):
        event = self.event({'action': 'get_state'})
        event.data.namespace = 'OtherPlugin'
        self.main.Event.menu(event, self.proc)
        event.send.assert_not_called()

    def test_reply_save_reset_and_extension_delete_share_parent_storage(self):
        self.assertTrue(self.call('save_reply', key='reply_permission_denied', value='自定义权限')['ok'])
        self.assertEqual(
            self.utils.load_bot_message_custom(self.parent_hash)['reply_permission_denied'],
            '自定义权限',
        )
        self.assertEqual(self.overlay(self.parent_hash), {'reply_permission_denied': '自定义权限'})
        self.assertNotIn('reply_draw_empty', self.overlay(self.parent_hash))
        self.assertFalse((self.root / 'data' / self.child_hash / 'message_custom.json').exists())
        self.assertFalse(self.call('reset_reply', key='reply_permission_denied')['ok'])
        self.assertTrue(self.call('reset_reply', key='reply_permission_denied', confirm=True)['ok'])
        self.assertEqual(
            self.utils.load_bot_message_custom(self.parent_hash)['reply_permission_denied'],
            self.messages.default_custom_message_dict['reply_permission_denied'],
        )
        self.assertNotIn('reply_permission_denied', self.overlay(self.parent_hash))
        self.utils.set_bot_message_custom_value(self.parent_hash, 'extension_reply', '扩展')
        self.assertTrue(self.call('save_reply', key='extension_reply', value='修改扩展')['ok'])
        self.assertTrue(self.call('reset_reply', key='extension_reply', confirm=True)['ok'])
        self.assertNotIn('extension_reply', self.utils.load_bot_message_custom(self.parent_hash))
        self.assertNotIn('extension_reply', self.overlay(self.parent_hash))

    def test_reply_modified_compares_default_text_not_emptiness(self):
        item = self.reply_item('reply_permission_denied')
        self.assertFalse(item['modified'])
        self.assertEqual(item['default'], self.messages.default_custom_message_dict['reply_permission_denied'])
        self.assertTrue(self.call('save_reply', key='reply_permission_denied', value='自定义')['ok'])
        self.assertTrue(self.reply_item('reply_permission_denied')['modified'])
        default_text = self.messages.default_custom_message_dict['reply_permission_denied']
        self.assertTrue(self.call('save_reply', key='reply_permission_denied', value=default_text)['ok'])
        item = self.reply_item('reply_permission_denied')
        self.assertFalse(item['modified'])
        self.assertNotIn('reply_permission_denied', self.overlay(self.parent_hash))
        self.assertTrue(self.call('reset_reply', key='reply_permission_denied', confirm=True)['ok'])
        self.assertFalse(self.reply_item('reply_permission_denied')['modified'])
        self.utils.set_bot_message_custom_value(self.parent_hash, 'extension_reply', '扩展')
        extra = self.reply_item('extension_reply')
        self.assertTrue(extra['modified'])
        self.assertIsNone(extra['default'])

    def test_reset_all_requires_confirmation_and_preserves_other_storage(self):
        self.utils.set_bot_message_custom_value(self.parent_hash, 'extension_reply', '扩展')
        self.utils.save_bot_message_variables(self.parent_hash, {'variable': '保留'})
        self.assertFalse(self.call('reset_replies', confirm=False)['ok'])
        self.assertIn('extension_reply', self.utils.load_bot_message_custom(self.parent_hash))
        self.assertTrue(self.call('reset_replies', confirm=True)['ok'])
        self.assertEqual(
            self.utils.load_bot_message_custom(self.parent_hash),
            self.messages.default_custom_message_dict,
        )
        self.assertEqual(self.overlay(self.parent_hash), {})
        self.assertEqual(self.utils.load_bot_message_variables(self.parent_hash)['variable'], '保留')

    def test_import_export_global_bot_and_replies(self):
        self.assertTrue(self.call('save_global', global_enable_switch=False, global_debug_mode_switch=True)['ok'])
        exported_global = self.call('export_global')
        self.assertTrue(exported_global['ok'])
        self.assertFalse(exported_global['data']['global_enable_switch'])
        self.assertTrue(exported_global['filename'].endswith('global-config.json'))
        self.assertTrue(self.call('save_global', global_enable_switch=True, global_debug_mode_switch=False)['ok'])
        self.assertTrue(self.call(
            'import_global', confirm=True,
            data={'global_enable_switch': False, 'future_setting': 'keep'},
        )['ok'])
        actual_global = self.utils.load_global_config()
        self.assertFalse(actual_global['global_enable_switch'])
        self.assertEqual(actual_global['future_setting'], 'keep')
        self.assertFalse(self.call('import_global', data={'global_enable_switch': True})['ok'])

        self.assertTrue(self.call('save_bot', bot_enable_switch=False)['ok'])
        self.assertTrue(self.call('add_masters', ids=['123'])['ok'])
        exported_bot = self.call('export_bot')
        self.assertFalse(exported_bot['data']['bot_enable_switch'])
        self.assertEqual(exported_bot['data']['configured_master_list'], ['123'])
        self.assertTrue(self.call('save_bot', bot_enable_switch=True)['ok'])
        self.assertTrue(self.call(
            'import_bot', confirm=True,
            data={'bot_enable_switch': False, 'future_setting': 'keep'},
        )['ok'])
        actual_bot = self.utils.load_bot_config(self.child_hash)
        self.assertFalse(actual_bot['bot_enable_switch'])
        self.assertEqual(actual_bot['configured_master_list'], ['123'])
        self.assertEqual(actual_bot['future_setting'], 'keep')

        self.assertTrue(self.call('save_reply', key='reply_permission_denied', value='导入前')['ok'])
        exported_replies = self.call('export_replies')
        self.assertEqual(exported_replies['data'], {'reply_permission_denied': '导入前'})
        self.assertTrue(self.call('save_reply', key='reply_permission_denied', value='将被覆盖')['ok'])
        self.assertTrue(self.call(
            'import_replies', confirm=True,
            data={
                'reply_permission_denied': self.messages.default_custom_message_dict['reply_permission_denied'],
                'reply_draw_empty': '自定义空合集',
            },
        )['ok'])
        overlay = self.overlay(self.parent_hash)
        self.assertNotIn('reply_permission_denied', overlay)
        self.assertEqual(overlay['reply_draw_empty'], '自定义空合集')
        self.assertFalse(self.reply_item('reply_permission_denied')['modified'])
        self.assertTrue(self.reply_item('reply_draw_empty')['modified'])
        self.assertFalse(self.call('import_replies', data={'reply_permission_denied': 'x'})['ok'])
        self.assertFalse(self.call('import_replies', confirm=True, data=['not-an-object'])['ok'])
        self.assertFalse(self.call('import_bot', confirm=True, data={'bot_enable_switch': 'yes'})['ok'])

    def test_legacy_full_reply_file_is_stripped_on_next_save(self):
        full = dict(self.messages.default_custom_message_dict)
        full['reply_permission_denied'] = '旧自定义'
        path = Path(self.utils.get_message_custom_file_path(self.parent_hash))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(full, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(
            self.utils.load_bot_message_custom(self.parent_hash)['reply_permission_denied'],
            '旧自定义',
        )
        default_empty = self.messages.default_custom_message_dict['reply_draw_empty']
        self.assertTrue(self.call('save_reply', key='reply_draw_empty', value=default_empty)['ok'])
        overlay = self.overlay(self.parent_hash)
        self.assertEqual(overlay, {'reply_permission_denied': '旧自定义'})
        self.assertTrue(self.reply_item('reply_permission_denied')['modified'])
        self.assertFalse(self.reply_item('reply_draw_empty')['modified'])


if __name__ == '__main__':
    unittest.main()
