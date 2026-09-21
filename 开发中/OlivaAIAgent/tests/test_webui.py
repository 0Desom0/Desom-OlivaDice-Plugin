"""验证 OlivaAIAgent WebUI 接口、Schema 生成与 app.json 配置。"""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

TEST_DIR = Path(__file__).resolve().parent
ROOT_DIR = TEST_DIR.parent
PACKAGE_DIR = ROOT_DIR / 'OlivaAIAgent'

# 确保能 import 到 OlivaAIAgent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import OlivaAIAgent


class OlivaAIAgentWebUITest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix='oliva-ai-webui-test-')
        self.addCleanup(self.temp_dir.cleanup)
        self.tmp_path = Path(self.temp_dir.name)

        # 隔离数据路径
        self.conf_patch = patch.object(OlivaAIAgent.conf, 'dataPath', str(self.tmp_path / 'data'))
        self.config_path_patch = patch.object(OlivaAIAgent.conf, 'CONFIG_PATH', str(self.tmp_path / 'data' / 'config.json'))
        self.groups_path_patch = patch.object(OlivaAIAgent.conf, 'GROUPS_PATH', str(self.tmp_path / 'data' / 'groups.json'))
        self.conf_patch.start()
        self.config_path_patch.start()
        self.groups_path_patch.start()
        self.addCleanup(self.conf_patch.stop)
        self.addCleanup(self.config_path_patch.stop)
        self.addCleanup(self.groups_path_patch.stop)

        OlivaAIAgent.conf.initDataPath()
        OlivaAIAgent.conf.load()
        self.proc = types.SimpleNamespace(
            Proc_data={'bot_info_dict': {}},
            log=Mock(),
        )

    def event(self, payload):
        return types.SimpleNamespace(
            bot_info=None,
            data=types.SimpleNamespace(
                namespace='OlivaAIAgent',
                event=OlivaAIAgent.webui.WEBUI_EVENT,
                webui={'request_id': 'req-test-ai-agent', 'session': 'test-session'},
                payload=payload,
            ),
            send=Mock(return_value=True),
        )

    def call(self, action, **kwargs):
        payload = {'action': action, **kwargs}
        event = self.event(payload)
        OlivaAIAgent.main.Event.menu(event, self.proc)
        event.send.assert_called_once()
        destination, req_id, res = event.send.call_args.args
        self.assertEqual(destination, 'webui')
        self.assertEqual(req_id, 'req-test-ai-agent')
        json.dumps(res, ensure_ascii=False)
        return res

    def test_app_json_no_bom_and_config(self):
        data = (PACKAGE_DIR / 'app.json').read_bytes()
        self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(data[0:1], b'{')
        manifest = json.loads(data)

        # 原生 GUI 菜单项必须保留
        self.assertIn('menu_config', manifest)
        menu_events = [m['event'] for m in manifest['menu_config']]
        self.assertIn('OlivaAIAgent_Menu_OpenConf', menu_events)
        self.assertIn('OlivaAIAgent_Menu_Reload', menu_events)

        # WebUI 必须配置且文件存在
        self.assertIn('webui_config', manifest)
        self.assertTrue(len(manifest['webui_config']) > 0)
        for page in manifest['webui_config']:
            self.assertTrue((PACKAGE_DIR / page['path']).is_file())

    def test_get_state_and_schema(self):
        res = self.call('get_state')
        self.assertTrue(res['ok'])
        state = res['state']
        schema = res['schema']

        self.assertEqual(state['plugin_name'], 'OlivaAIAgent')
        self.assertIn('conf', state)
        self.assertIn('groups', state)
        self.assertIn('sections', state)
        self.assertIn('runtime_status', state)

        # 检查所有分类都有对应的 schema 且包含字段
        self.assertEqual(len(state['sections']), len(OlivaAIAgent.gui.SECTION_ORDER))
        for sec in state['sections']:
            sec_id = sec['id']
            self.assertIn(sec_id, schema)
            self.assertIsInstance(schema[sec_id]['fields'], list)

    def test_save_conf(self):
        current_conf = OlivaAIAgent.conf.snapshot()
        current_conf['backend'] = 'custom'
        current_conf['openai']['model'] = 'gpt-4o-test'

        res = self.call('save_conf', conf=current_conf)
        self.assertTrue(res['ok'])
        saved_conf = res['state']['conf']
        self.assertEqual(saved_conf['backend'], 'custom')
        self.assertEqual(saved_conf['openai']['model'], 'gpt-4o-test')

    def test_save_group_globals(self):
        res = self.call(
            'save_group_globals',
            **{'global': True},
            whitelist=True,
            group_default=False,
            ambient_default=True,
            prefix=['.ai_test'],
            keywords=['小芙测试'],
        )
        self.assertTrue(res['ok'])
        conf = res['state']['conf']
        self.assertTrue(conf['enable']['global'])
        self.assertTrue(conf['whitelist']['enabled'])
        self.assertFalse(conf['enable']['group_default'])
        self.assertTrue(conf['ambient']['enable_default'])
        self.assertEqual(conf['trigger']['prefix'], ['.ai_test'])
        self.assertEqual(conf['trigger']['keywords'], ['小芙测试'])

    def test_group_override_lifecycle(self):
        # 1. 保存群覆盖
        save_res = self.call(
            'save_group',
            platform='qq',
            group_id='12345678',
            values={'enabled': True, 'ambient': False},
        )
        self.assertTrue(save_res['ok'])
        groups = save_res['state']['groups']
        self.assertIn('qq', groups)
        self.assertIn('12345678', groups['qq'])
        self.assertTrue(groups['qq']['12345678']['enabled'])
        self.assertFalse(groups['qq']['12345678']['ambient'])

        # 2. 删除群覆盖
        del_res = self.call('delete_group', platform='qq', group_id='12345678')
        self.assertTrue(del_res['ok'])
        groups = del_res['state']['groups']
        self.assertNotIn('12345678', groups.get('qq', {}))

    def test_reset_section(self):
        # 先修改
        current_conf = OlivaAIAgent.conf.snapshot()
        current_conf['debug_log'] = True
        self.call('save_conf', conf=current_conf)

        # 再重置
        res = self.call('reset_section', section='general')
        self.assertTrue(res['ok'])
        self.assertEqual(
            res['state']['conf']['debug_log'],
            OlivaAIAgent.conf.DEFAULT_CONF['debug_log'],
        )


if __name__ == '__main__':
    unittest.main()
