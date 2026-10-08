"""验证 IWannaSearch WebUI 接口与 app.json 配置。"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = '_iwanna_search_webui_test'


class IWannaSearchWebUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules_patch = patch.dict(sys.modules, {'OlivOS': types.ModuleType('OlivOS')})
        cls.modules_patch.start()
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_DIR / '__init__.py')
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        cls.main = package.main
        cls.webui = package.main.webui
        cls.utils = package.main.utils
        cls.config = cls.webui.config
        cls.messages = cls.utils.message_custom

    @classmethod
    def tearDownClass(cls):
        cls.modules_patch.stop()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='iwanna-webui-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        data_patch = patch.object(self.config, 'plugin_data_dir', str(self.root / 'data'))
        data_patch.start()
        self.addCleanup(data_patch.stop)
        self.parent_hash = 'a' * 32
        self.child_hash = 'b' * 32
        link_patch = patch.object(
            self.utils,
            'get_linked_bot_hash',
            side_effect=lambda val: self.parent_hash if val == self.child_hash else val,
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
                namespace='IWannaSearch',
                event=self.config.webui_event,
                webui={'request_id': 'test-request-iw', 'session': 'test-session'},
                payload=payload,
            ),
            send=Mock(return_value=True),
        )

    def call(self, action, **fields):
        event = self.event({'action': action, 'bot_hash': self.child_hash, **fields})
        self.main.Event.menu(event, self.proc)
        event.send.assert_called_once()
        destination, request_id, response = event.send.call_args.args
        self.assertEqual((destination, request_id), ('webui', 'test-request-iw'))
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

    def save_global_payload(self, **overrides):
        payload = {
            'global_enable_switch': True,
            'global_debug_mode_switch': False,
            'api_base_url': self.config.api_default_base_url,
            'api_timeout_seconds': self.config.api_timeout_seconds,
            'result_page_size': self.config.result_page_size,
            'selection_timeout_seconds': self.config.selection_timeout_seconds,
            'max_download_concurrency': self.config.download_concurrency_default,
        }
        payload.update(overrides)
        return self.call('save_global', **payload)

    def test_app_json_no_bom_and_paths_exist(self):
        data = (PLUGIN_DIR / 'app.json').read_bytes()
        self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(data[0:1], b'{')
        manifest = json.loads(data)
        self.assertIn('menu_config', manifest)
        self.assertTrue(len(manifest['menu_config']) > 0)
        self.assertIn('webui_config', manifest)
        for page in manifest['webui_config']:
            self.assertTrue((PLUGIN_DIR / page['path']).is_file())

    def test_get_state(self):
        res = self.call('get_state')
        self.assertTrue(res['ok'])
        state = res['state']
        self.assertEqual(state['plugin_name'], 'IWannaSearch')
        self.assertIn('global_enable_switch', state['global_config'])
        self.assertIn('api_base_url', state['global_config'])
        self.assertEqual(state['bot']['hash'], self.child_hash)
        self.assertEqual(state['bot']['linked_hash'], self.parent_hash)

    def test_save_global(self):
        res = self.call(
            'save_global',
            global_enable_switch=False,
            global_debug_mode_switch=True,
            api_base_url='https://custom-archive.com',
            api_timeout_seconds=20,
            result_page_size=15,
            selection_timeout_seconds=120,
            max_download_concurrency=8,
        )
        self.assertTrue(res['ok'])
        gc = res['state']['global_config']
        self.assertFalse(gc['global_enable_switch'])
        self.assertTrue(gc['global_debug_mode_switch'])
        self.assertEqual(gc['api_base_url'], 'https://custom-archive.com')
        self.assertEqual(gc['max_download_concurrency'], 8)

    def test_save_bot(self):
        res = self.call(
            'save_bot',
            bot_enable_switch=True,
            merge_forward_enabled=False,
        )
        self.assertTrue(res['ok'])
        bot = res['state']['bot']
        self.assertTrue(bot['bot_enable_switch'])
        self.assertFalse(bot['merge_forward_enabled'])

    def test_reply_save_reset_and_extension_delete_share_parent_storage(self):
        self.assertTrue(self.call('save_reply', key='reply_help_hint', value='自定义帮助')['ok'])
        self.assertEqual(self.utils.load_bot_message_custom(self.parent_hash)['reply_help_hint'], '自定义帮助')
        self.assertEqual(self.overlay(self.parent_hash), {'reply_help_hint': '自定义帮助'})
        self.assertNotIn('reply_empty_query', self.overlay(self.parent_hash))
        self.assertFalse((self.root / 'data' / self.child_hash / 'message_custom.json').exists())
        self.assertFalse(self.call('reset_reply', key='reply_help_hint')['ok'])
        self.assertTrue(self.call('reset_reply', key='reply_help_hint', confirm=True)['ok'])
        self.assertEqual(
            self.utils.load_bot_message_custom(self.parent_hash)['reply_help_hint'],
            self.messages.default_custom_message_dict['reply_help_hint'],
        )
        self.assertNotIn('reply_help_hint', self.overlay(self.parent_hash))
        self.utils.set_bot_message_custom_value(self.parent_hash, 'extension_reply', '扩展')
        self.assertTrue(self.call('save_reply', key='extension_reply', value='修改扩展')['ok'])
        self.assertTrue(self.call('reset_reply', key='extension_reply', confirm=True)['ok'])
        self.assertNotIn('extension_reply', self.utils.load_bot_message_custom(self.parent_hash))
        self.assertNotIn('extension_reply', self.overlay(self.parent_hash))

    def test_reply_modified_compares_default_text_not_emptiness(self):
        hint = self.reply_item('reply_help_hint')
        self.assertFalse(hint['modified'])
        self.assertEqual(hint['default'], self.messages.default_custom_message_dict['reply_help_hint'])
        self.assertTrue(self.call('save_reply', key='reply_help_hint', value='自定义')['ok'])
        self.assertTrue(self.reply_item('reply_help_hint')['modified'])
        default_text = self.messages.default_custom_message_dict['reply_help_hint']
        self.assertTrue(self.call('save_reply', key='reply_help_hint', value=default_text)['ok'])
        hint = self.reply_item('reply_help_hint')
        self.assertFalse(hint['modified'])
        self.assertNotIn('reply_help_hint', self.overlay(self.parent_hash))
        self.assertTrue(self.call('reset_reply', key='reply_help_hint', confirm=True)['ok'])
        self.assertFalse(self.reply_item('reply_help_hint')['modified'])
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
        self.assertTrue(self.save_global_payload(
            global_enable_switch=False,
            global_debug_mode_switch=True,
        )['ok'])
        exported_global = self.call('export_global')
        self.assertTrue(exported_global['ok'])
        self.assertFalse(exported_global['data']['global_enable_switch'])
        self.assertTrue(exported_global['filename'].endswith('global-config.json'))
        self.assertTrue(self.save_global_payload()['ok'])
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

        self.assertTrue(self.call('save_reply', key='reply_help_hint', value='导入前')['ok'])
        exported_replies = self.call('export_replies')
        self.assertEqual(exported_replies['data'], {'reply_help_hint': '导入前'})
        self.assertTrue(self.call('save_reply', key='reply_help_hint', value='将被覆盖')['ok'])
        self.assertTrue(self.call(
            'import_replies', confirm=True,
            data={
                'reply_help_hint': self.messages.default_custom_message_dict['reply_help_hint'],
                'reply_empty_query': '自定义空查询',
            },
        )['ok'])
        overlay = self.overlay(self.parent_hash)
        self.assertNotIn('reply_help_hint', overlay)
        self.assertEqual(overlay['reply_empty_query'], '自定义空查询')
        self.assertFalse(self.reply_item('reply_help_hint')['modified'])
        self.assertTrue(self.reply_item('reply_empty_query')['modified'])
        self.assertFalse(self.call('import_replies', data={'reply_help_hint': 'x'})['ok'])
        self.assertFalse(self.call('import_replies', confirm=True, data=['not-an-object'])['ok'])
        self.assertFalse(self.call('import_bot', confirm=True, data={'bot_enable_switch': 'yes'})['ok'])

    def test_legacy_full_reply_file_is_stripped_on_next_save(self):
        full = dict(self.messages.default_custom_message_dict)
        full['reply_help_hint'] = '旧自定义'
        path = Path(self.utils.get_message_custom_file_path(self.parent_hash))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(full, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(self.utils.load_bot_message_custom(self.parent_hash)['reply_help_hint'], '旧自定义')
        default_empty = self.messages.default_custom_message_dict['reply_empty_query']
        self.assertTrue(self.call('save_reply', key='reply_empty_query', value=default_empty)['ok'])
        overlay = self.overlay(self.parent_hash)
        self.assertEqual(overlay, {'reply_help_hint': '旧自定义'})
        self.assertTrue(self.reply_item('reply_help_hint')['modified'])
        self.assertFalse(self.reply_item('reply_empty_query')['modified'])


if __name__ == '__main__':
    unittest.main()
