"""验证 CyberGladiator WebUI 接口与 app.json 配置。"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = '_cyber_gladiator_webui_test'


class CyberGladiatorWebUITest(unittest.TestCase):
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
        cls.messages = cls.webui.message_custom

    @classmethod
    def tearDownClass(cls):
        cls.modules_patch.stop()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='cyber-webui-test-')
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
                namespace='CyberGladiator',
                event=self.config.webui_event,
                webui={'request_id': 'test-request-cg', 'session': 'test-session'},
                payload=payload,
            ),
            send=Mock(return_value=True),
        )

    def call(self, action, **fields):
        event = self.event({'action': action, 'bot_hash': self.child_hash, **fields})
        self.main.Event.menu(event, self.proc)
        event.send.assert_called_once()
        destination, request_id, response = event.send.call_args.args
        self.assertEqual((destination, request_id), ('webui', 'test-request-cg'))
        json.dumps(response, ensure_ascii=False)
        return response

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
        self.assertEqual(state['plugin_name'], 'CyberGladiator')
        self.assertIn('global_enable_switch', state['global_config'])
        self.assertIn('global_god_war_enable_switch', state['global_config'])
        self.assertEqual(state['bot']['hash'], self.child_hash)
        self.assertEqual(state['bot']['linked_hash'], self.parent_hash)

    def test_callbacks_do_not_recreate_removed_import_directory(self):
        import_root = self.root / 'plugin/tmp/CyberGladiator'
        with patch.object(self.utils, '__file__', str(import_root / 'utils.py')):
            self.main.Event.init(None, self.proc)
            self.main.Event.init_after(None, self.proc)
            self.assertTrue(self.call('get_state')['ok'])
        self.assertFalse(import_root.exists())

    def test_save_global(self):
        res = self.call('save_global', global_enable_switch=False, global_debug_mode_switch=True,
                        global_god_war_enable_switch=False)
        self.assertTrue(res['ok'])
        gc = res['state']['global_config']
        self.assertFalse(gc['global_enable_switch'])
        self.assertTrue(gc['global_debug_mode_switch'])
        self.assertFalse(gc['global_god_war_enable_switch'])

    def test_save_bot(self):
        res = self.call(
            'save_bot',
            bot_enable_switch=True,
            model='test-model',
            temperature=0.7,
            request_timeout_seconds=300,
            normal_input_limit=1500,
        )
        self.assertTrue(res['ok'])
        bot = res['state']['bot']
        self.assertEqual(bot['model'], 'test-model')
        self.assertEqual(bot['temperature'], 0.7)
        self.assertEqual(bot['request_timeout_seconds'], 300)
        self.assertEqual(bot['normal_input_limit'], 1500)


if __name__ == '__main__':
    unittest.main()
