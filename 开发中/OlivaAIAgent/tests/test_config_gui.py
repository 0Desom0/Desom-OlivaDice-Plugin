import copy
import json
import os
import tempfile
import unittest
from unittest import mock

import OlivaAIAgent


class FakeProc:
    def __init__(self):
        self.records = []

    def log(self, level, message, segments=None):
        self.records.append((level, message, segments))


class ConfigMigrationTest(unittest.TestCase):
    def test_default_config_has_one_global_prompt(self):
        default_conf = OlivaAIAgent.conf.DEFAULT_CONF
        self.assertIn('system', default_conf['prompt'])
        self.assertNotIn('append', default_conf['prompt'])
        self.assertNotIn('personality', default_conf['ambient'])
        self.assertNotIn('enabled_groups', default_conf['ambient'])
        self.assertNotIn('first_thinking_cooldown', default_conf['ambient'])
        self.assertNotIn('mention_reply', default_conf['ambient'])
        self.assertTrue(default_conf['memory']['long_term_default'])
        self.assertIn('mcp', default_conf)
        self.assertIn('voice', default_conf)
        self.assertEqual('dashscope_multimodal', default_conf['voice']['provider'])
        self.assertEqual('qwen3-tts-instruct-flash', default_conf['voice']['model'])
        self.assertEqual('Chinese', default_conf['voice']['language_type'])
        self.assertTrue(default_conf['voice']['optimize_instructions'])
        self.assertEqual(10, default_conf['voice']['max_files'])
        self.assertNotIn('instructions', default_conf['voice'])
        self.assertNotIn('groups', default_conf['whitelist'])
        self.assertEqual(8, default_conf['memory']['max_rounds'])
        self.assertEqual(16, default_conf['memory']['prompt_cache_max_rounds'])
        self.assertEqual(8, default_conf['ambient']['history_size'])
        self.assertEqual(16, default_conf['ambient']['prompt_cache_history_size'])
        self.assertTrue(default_conf['security']['use_olivadice_censor'])
        self.assertEqual('骰主', default_conf['masters']['default_title'])
        self.assertEqual({}, default_conf['masters']['titles'])

    def test_legacy_prompts_and_permissions_are_migrated_once(self):
        config = {
            'prompt': {'system': '基础规则', 'append': '补充规则'},
            'ambient': {'personality': '自定义人设', 'enabled_groups': ['10001']},
            'permissions': {'admin_tools_master_only': True, 'admin_tools_min_role': 'everyone'},
        }

        legacy_groups = OlivaAIAgent.conf._migrate(config)
        first_prompt = config['prompt']['system']
        OlivaAIAgent.conf._migrate(config)

        self.assertIn('基础规则', first_prompt)
        self.assertIn('自定义人设', first_prompt)
        self.assertIn('补充规则', first_prompt)
        self.assertEqual(first_prompt, config['prompt']['system'])
        self.assertNotIn('append', config['prompt'])
        self.assertNotIn('personality', config['ambient'])
        self.assertNotIn('admin_tools_master_only', config['permissions'])
        self.assertEqual('master', config['permissions']['admin_tools_min_role'])
        self.assertEqual(['10001'], legacy_groups)

    def test_legacy_all_group_switch_becomes_default(self):
        config = {'prompt': {}, 'ambient': {'enabled_groups': 'all'}, 'permissions': {}}
        legacy_groups = OlivaAIAgent.conf._migrate(config)
        self.assertEqual([], legacy_groups)
        self.assertTrue(config['ambient']['enable_default'])

    def test_legacy_voice_config_keeps_openai_compatible_wire(self):
        config = {
            'prompt': {},
            'ambient': {},
            'permissions': {},
            'voice': {
                'api_url': 'https://example.invalid/v1/audio/speech',
                'instructions': '旧的固定表现指令',
                'max_files': 100,
            },
        }
        OlivaAIAgent.conf._migrate(config)
        self.assertEqual('openai_compatible', config['voice']['provider'])
        self.assertNotIn('instructions', config['voice'])
        self.assertEqual(10, config['voice']['max_files'])

    def test_legacy_persona_master_ids_move_to_internal_titles(self):
        config = {
            'prompt': {
                'system': (
                    '前文。你的主人Desom-fu认主唯一标准是发送者的QQ号（openid）为PRIMARY-ID'
                    '或其小号SECONDARY-ID，若昵称同但QQ号（openid）不符直接称呼QQ号（openid）。'
                    '主人喜欢音游。后文。'
                ),
            },
            'masters': {'from_olivadice': True, 'extra': []},
            'ambient': {},
            'permissions': {},
        }

        OlivaAIAgent.conf._migrate(config)

        self.assertEqual('主人', config['masters']['titles']['PRIMARY-ID'])
        self.assertEqual('主人小号', config['masters']['titles']['SECONDARY-ID'])
        self.assertEqual('骰主', config['masters']['default_title'])
        self.assertIn('Desom-fu喜欢音游', config['prompt']['system'])
        self.assertNotIn('认主唯一标准', config['prompt']['system'])

    def test_persisted_config_omits_description_metadata(self):
        clean = OlivaAIAgent.conf._persistableConfig({
            '_说明': '不落盘',
            'normal': 1,
            'nested': {'_提示': '不落盘', 'value': True},
        })
        self.assertEqual({'normal': 1, 'nested': {'value': True}}, clean)

    def test_wildcard_group_migration_preserves_platform_override_priority(self):
        old_groups = copy.deepcopy(OlivaAIAgent.conf.gGroups)
        try:
            OlivaAIAgent.conf.gGroups = {'*': {'10001': {'ambient': True}}}
            self.assertTrue(OlivaAIAgent.conf.getGroupSwitch('qq', '10001', 'ambient', False))
            OlivaAIAgent.conf.gGroups['qq'] = {'10001': {'ambient': False}}
            self.assertFalse(OlivaAIAgent.conf.getGroupSwitch('qq', '10001', 'ambient', True))
        finally:
            OlivaAIAgent.conf.gGroups = old_groups

    def test_load_migrates_old_file_without_losing_prompt_text(self):
        conf = OlivaAIAgent.conf
        old_state = {
            name: copy.deepcopy(getattr(conf, name))
            for name in (
                'dataPath',
                'tmpPath',
                'CONFIG_PATH',
                'GROUPS_PATH',
                'LOG_DIR',
                'gConf',
                'gGroups',
                '_config_mtime',
                '_groups_mtime',
            )
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                conf.dataPath = os.path.join(temp_dir, 'data')
                conf.tmpPath = os.path.join(temp_dir, 'tmp')
                conf.CONFIG_PATH = os.path.join(conf.dataPath, 'config.json')
                conf.GROUPS_PATH = os.path.join(conf.dataPath, 'groups.json')
                conf.LOG_DIR = os.path.join(conf.dataPath, 'logs')
                os.makedirs(conf.dataPath, exist_ok=True)
                with open(conf.CONFIG_PATH, 'w', encoding='utf-8') as config_file:
                    json.dump(
                        {
                            '_说明': '旧说明',
                            'prompt': {'system': '旧系统', 'append': '旧附加'},
                            'ambient': {'personality': '旧人设', 'enabled_groups': ['20002']},
                            'whitelist': {'enabled': True, 'groups': ['30003']},
                            'voice': {'api_url': 'https://example.invalid/v1/audio/speech'},
                        },
                        config_file,
                        ensure_ascii=False,
                    )

                conf.load()
                with open(conf.CONFIG_PATH, encoding='utf-8') as config_file:
                    persisted = json.load(config_file)

                self.assertIn('旧系统', persisted['prompt']['system'])
                self.assertIn('旧人设', persisted['prompt']['system'])
                self.assertIn('旧附加', persisted['prompt']['system'])
                self.assertNotIn('append', persisted['prompt'])
                self.assertNotIn('personality', persisted['ambient'])
                self.assertNotIn('enabled_groups', persisted['ambient'])
                self.assertNotIn('_说明', persisted)
                self.assertNotIn('groups', persisted['whitelist'])
                self.assertEqual('openai_compatible', persisted['voice']['provider'])
                self.assertTrue(conf.gGroups['*']['20002']['ambient'])
                self.assertTrue(conf.gGroups['*']['30003']['enabled'])
        finally:
            for name, value in old_state.items():
                setattr(conf, name, value)


class ConfigGuiSchemaTest(unittest.TestCase):
    def test_cache_and_core_censor_fields_have_clear_gui_labels(self):
        labels = OlivaAIAgent.gui.FIELD_LABELS
        self.assertEqual('会话历史轮数', labels['max_rounds'])
        self.assertEqual('会话缓存上限轮数', labels['prompt_cache_max_rounds'])
        self.assertEqual('潜行历史条数', labels['history_size'])
        self.assertEqual('潜行缓存上限条数', labels['prompt_cache_history_size'])
        self.assertEqual('跟随 OlivaDiceCore 敏感词', labels['use_olivadice_censor'])
        self.assertIn('olivadice_logger', OlivaAIAgent.gui.SECTION_ORDER)
        self.assertEqual('OlivaDice 团日志', OlivaAIAgent.gui.SECTION_LABELS['olivadice_logger'])
        self.assertTrue(OlivaAIAgent.conf.DEFAULT_CONF['olivadice_logger']['enabled'])
        self.assertEqual('骰主与专属称呼', OlivaAIAgent.gui.SECTION_LABELS['masters'])
        self.assertEqual('未单独设置时的骰主称呼', labels['default_title'])
        self.assertEqual('骰主专属称呼（JSON）', labels['titles'])
        self.assertIn('titles', OlivaAIAgent.gui.JSON_OBJECT_NAMES)

    def test_group_table_has_no_per_group_trigger_override_columns(self):
        self.assertNotIn('prefixes', OlivaAIAgent.gui.GROUP_TREE_COLUMNS)
        self.assertNotIn('keywords', OlivaAIAgent.gui.GROUP_TREE_COLUMNS)
        self.assertNotIn('触发前缀', OlivaAIAgent.gui.GROUP_TREE_HEADINGS)
        self.assertNotIn('触发关键词', OlivaAIAgent.gui.GROUP_TREE_HEADINGS)

    def test_gui_action_has_one_clear_log(self):
        proc = FakeProc()
        window = OlivaAIAgent.gui.ConfigWindow(Proc=proc)
        window._logAction('正在保存并应用配置')
        self.assertEqual(1, len(proc.records))
        self.assertIn('GUI | 正在保存并应用配置', proc.records[0][1])

    def test_gui_sections_cover_every_runtime_config_section(self):
        expected = {
            key
            for key, value in OlivaAIAgent.conf.DEFAULT_CONF.items()
            if isinstance(value, dict) and not key.startswith('_')
        }
        actual = set(OlivaAIAgent.gui.SECTION_ORDER)
        actual.discard('general')
        expected -= {'enable', 'whitelist'}
        self.assertEqual(expected, actual)
        self.assertNotIn('enable', OlivaAIAgent.gui.SECTION_ORDER)
        self.assertNotIn('whitelist', OlivaAIAgent.gui.SECTION_ORDER)

    def test_group_trigger_override_parser_supports_inherit_and_disable(self):
        parser = OlivaAIAgent.gui.ConfigWindow._parseStringList
        self.assertIsNone(parser('', '群触发前缀', allow_inherit=True))
        self.assertEqual([], parser('[]', '群触发前缀', allow_inherit=True))
        self.assertEqual(['.bot'], parser('[".bot"]', '群触发前缀', allow_inherit=True))
        with self.assertRaises(ValueError):
            parser('[1]', '群触发前缀', allow_inherit=True)

    def test_typed_editor_values(self):
        self.assertEqual(12, OlivaAIAgent.gui._parseValue('12', 1, ('agent', 'max_tool_rounds')))
        self.assertEqual(0.25, OlivaAIAgent.gui._parseValue('0.25', 0.0, ('semantic_memory', 'min_score')))
        self.assertEqual(['a', 'b'], OlivaAIAgent.gui._parseValue('["a", "b"]', [], ('trigger', 'keywords')))
        self.assertIs(True, OlivaAIAgent.gui._parseValue('true', 'auto', ('vision', 'use_main')))

    def test_mcp_and_voice_have_visible_gui_sections(self):
        self.assertIn('mcp', OlivaAIAgent.gui.SECTION_ORDER)
        self.assertIn('voice', OlivaAIAgent.gui.SECTION_ORDER)
        self.assertEqual(
            ('dashscope_multimodal', 'openai_compatible'),
            OlivaAIAgent.gui.ENUM_VALUES[('voice', 'provider')],
        )
        self.assertEqual(
            [{'name': 'demo', 'transport': 'streamable_http'}],
            OlivaAIAgent.gui._parseValue(
                '[{"name":"demo","transport":"streamable_http"}]',
                [],
                ('mcp', 'servers'),
            ),
        )

    def test_mcp_maintenance_action_uses_logged_runner(self):
        window = OlivaAIAgent.gui.ConfigWindow()
        with mock.patch.object(window, '_runMaintenance') as runner:
            window.refreshMcp()
        self.assertEqual('MCP 工具刷新', runner.call_args.args[0])

    def test_sensitive_lexicon_action_uses_maintenance_runner(self):
        window = OlivaAIAgent.gui.ConfigWindow()
        window.working_conf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        with mock.patch.object(window, '_commitCurrent', return_value=True), \
                mock.patch.object(window, '_commitGroupGlobal', return_value=True), \
                mock.patch.object(window, '_runMaintenance') as runner:
            window.updateSensitiveLexicon()
        self.assertEqual('敏感词库更新', runner.call_args.args[0])
        self.assertIn('on_success', runner.call_args.kwargs)

    def test_security_section_exposes_synced_lexicon_actions(self):
        self.assertEqual(
            ('下载 / 检查更新', '打开词库目录'),
            OlivaAIAgent.gui.SECURITY_LEXICON_ACTIONS,
        )
        self.assertTrue(OlivaAIAgent.gui._sectionHasLexiconActions('security'))
        self.assertFalse(OlivaAIAgent.gui._sectionHasLexiconActions('maintenance'))


class UnifiedGroupConfigTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = OlivaAIAgent.conf.gConf
        self.old_groups = OlivaAIAgent.conf.gGroups
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.conf.gGroups = {}

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.conf.gGroups = self.old_groups

    def test_whitelist_uses_group_table_membership_including_empty_nodes(self):
        OlivaAIAgent.conf.gConf['whitelist']['enabled'] = True
        OlivaAIAgent.conf.gGroups = {'qq': {'10001': {}}, '*': {'20002': {'enabled': False}}}

        self.assertTrue(OlivaAIAgent.conf.isWhitelisted('qq', '10001'))
        self.assertTrue(OlivaAIAgent.conf.isWhitelisted('qqGuild', '20002'))
        self.assertFalse(OlivaAIAgent.conf.isWhitelisted('qq', '30003'))

    def test_whitelist_off_allows_unlisted_group_then_uses_group_default(self):
        OlivaAIAgent.conf.gConf['whitelist']['enabled'] = False
        OlivaAIAgent.conf.gConf['enable']['group_default'] = False

        self.assertTrue(OlivaAIAgent.conf.isWhitelisted('qq', 'unlisted'))
        self.assertFalse(OlivaAIAgent.conf.isGroupEnabled('qq', 'unlisted'))

        OlivaAIAgent.conf.gConf['enable']['group_default'] = True
        self.assertTrue(OlivaAIAgent.conf.isGroupEnabled('qq', 'unlisted'))

    def test_group_prefixes_and_keywords_always_use_global_values(self):
        OlivaAIAgent.conf.gConf['trigger']['prefix'] = ['.ai']
        OlivaAIAgent.conf.gConf['trigger']['keywords'] = ['小芙']
        OlivaAIAgent.conf.gGroups = {
            'qq': {
                'custom': {'prefixes': ['.bot'], 'keywords': ['助手']},
            },
        }

        self.assertEqual(['.ai'], OlivaAIAgent.conf.getGroupPrefixes('qq', 'custom'))
        self.assertEqual(['小芙'], OlivaAIAgent.conf.getGroupKeywords('qq', 'custom'))
        self.assertEqual('你好', OlivaAIAgent.msgReply._matchPrefix('.ai 你好', 'qq', 'custom'))
        self.assertIsNone(OlivaAIAgent.msgReply._matchPrefix('.bot 你好', 'qq', 'custom'))

    def test_normalize_groups_removes_trigger_overrides_and_merges_duplicate_group_ids(self):
        OlivaAIAgent.conf.gGroups = {
            '*': {
                'same': {'ambient': True, 'prefixes': ['.bot']},
                'wildcard_only': {'enabled': True},
            },
            'qq': {
                'same': {'enabled': False, 'keywords': ['助手']},
            },
        }

        changed = OlivaAIAgent.conf._normalizeGroups()

        self.assertTrue(changed)
        self.assertNotIn('same', OlivaAIAgent.conf.gGroups.get('*', {}))
        self.assertEqual(
            {'ambient': True, 'enabled': False},
            OlivaAIAgent.conf.gGroups['qq']['same'],
        )
        self.assertEqual({'enabled': True}, OlivaAIAgent.conf.gGroups['*']['wildcard_only'])

    def test_saving_same_group_overwrites_old_platform_record(self):
        OlivaAIAgent.conf.gGroups = {
            '*': {'same': {'ambient': True}},
            'qq': {'same': {'enabled': True}},
        }

        with mock.patch.object(OlivaAIAgent.conf, 'saveGroups'):
            OlivaAIAgent.conf.replaceGroupConfig('*', 'same', {'enabled': False})

        records = [
            (platform, node['same'])
            for platform, node in OlivaAIAgent.conf.gGroups.items()
            if 'same' in node
        ]
        self.assertEqual([('qq', {'enabled': False})], records)

    def test_runtime_switch_update_promotes_wildcard_record_without_duplicate(self):
        OlivaAIAgent.conf.gGroups = {'*': {'same': {'enabled': True}}}

        with mock.patch.object(OlivaAIAgent.conf, 'saveGroups'):
            OlivaAIAgent.conf.setGroupSwitch('qq', 'same', 'ambient', False)

        self.assertNotIn('*', OlivaAIAgent.conf.gGroups)
        self.assertEqual(
            {'enabled': True, 'ambient': False},
            OlivaAIAgent.conf.gGroups['qq']['same'],
        )

if __name__ == '__main__':
    unittest.main()
