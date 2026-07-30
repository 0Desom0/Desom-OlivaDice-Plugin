import copy
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

import OlivaAIAgent


class ContentSafetyTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = copy.deepcopy(OlivaAIAgent.conf.gConf)
        self.temp_dir = tempfile.TemporaryDirectory()
        OlivaAIAgent.conf.gConf = {
            'security': {
                'politics_guard': True,
                'politics_reply': '换个话题吧',
                'use_olivadice_censor': True,
                'external_sensitive_words': False,
                'sensitive_word_files': [],
                'sensitive_word_dirs': [],
            },
            'memory': {'max_rounds': 4, 'context_buffer': 10},
        }
        OlivaAIAgent.contentSafety._external_signature = None

    def tearDown(self):
        self.temp_dir.cleanup()
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.contentSafety._external_signature = None

    def test_builtin_guard_blocks_politics_and_leader_names(self):
        self.assertEqual(
            OlivaAIAgent.contentSafety.match('聊聊现实政治和政治立场'),
            'builtin_politics',
        )
        self.assertEqual(
            OlivaAIAgent.contentSafety.match('介绍一下习近平'),
            'builtin_leader',
        )
        self.assertIsNotNone(
            OlivaAIAgent.contentSafety.match('现在的中国国家领导人是谁'),
        )

    def test_normal_trpg_and_natural_language_are_allowed(self):
        allowed = [
            '帮我投一个侦查检定',
            '李强的角色卡职业是记者',
            '这个王国由议会和国王统治',
            '讨论一下游戏中的阵营立场',
            '这个模组的故事发生在中国',
            '我国调查员在国内找到了能直连的资源',
        ]
        for text in allowed:
            with self.subTest(text=text):
                self.assertIsNone(OlivaAIAgent.contentSafety.match(text))

    def test_olivadice_core_censor_uses_current_bot_dfa_and_switch(self):
        class FakeDFA:
            def find(self, text, mode=None):
                matches = []
                if 'Core测试词' in text:
                    matches.append('Core测试词')
                if '中国' in text:
                    matches.append('中国')
                return matches

        switch = {'value': 1}
        fake_core = types.SimpleNamespace(
            censorAPI=types.SimpleNamespace(
                gCensorDFA={'bot-1': FakeDFA()},
                gCensorList={'unity': ['全局词'], 'bot-1': ['bot词']},
                getConfigList=lambda bot_hash: ['配置词'] if bot_hash == 'bot-1' else [],
            ),
            censorDFA=types.SimpleNamespace(maxMatchType='MAX'),
            console=types.SimpleNamespace(
                getConsoleSwitchByHash=lambda key, bot_hash: switch['value'],
            ),
        )
        with mock.patch.dict(sys.modules, {'OlivaDiceCore': fake_core}):
            self.assertEqual(
                'olivadice_censor',
                OlivaAIAgent.contentSafety.match('这里有Core测试词', bot_hash='bot-1'),
            )
            self.assertIsNone(
                OlivaAIAgent.contentSafety.match('故事发生在中国', bot_hash='bot-1'),
            )
            status = OlivaAIAgent.contentSafety.externalStatus('bot-1')
            self.assertTrue(status['core_ready'])
            self.assertEqual(3, status['core_words'])
            switch['value'] = 0
            self.assertIsNone(
                OlivaAIAgent.contentSafety.match('这里有Core测试词', bot_hash='bot-1'),
            )

    def test_olivadice_core_censor_can_be_disabled_in_plugin(self):
        OlivaAIAgent.conf.gConf['security']['use_olivadice_censor'] = False
        fake_dfa = mock.Mock()
        with mock.patch.dict(sys.modules, {'OlivaDiceCore': mock.Mock()}):
            self.assertIsNone(
                OlivaAIAgent.contentSafety.match('Core测试词', bot_hash='bot-1'),
            )
        fake_dfa.find.assert_not_called()

    def test_optional_text_and_json_lexicons_reload_locally(self):
        text_path = os.path.join(self.temp_dir.name, 'words.txt')
        json_path = os.path.join(self.temp_dir.name, 'words.json')
        with open(text_path, 'w', encoding='utf-8') as handle:
            handle.write('# comment\n选装测试词\n')
        with open(json_path, 'w', encoding='utf-8') as handle:
            json.dump(['第二测试词'], handle, ensure_ascii=False)
        OlivaAIAgent.conf.gConf['security'].update({
            'external_sensitive_words': True,
            'sensitive_word_dirs': [self.temp_dir.name],
        })
        self.assertEqual(
            OlivaAIAgent.contentSafety.match('这里有选装测试词'),
            'external_lexicon',
        )
        self.assertEqual(
            OlivaAIAgent.contentSafety.match('这里有第二测试词'),
            'external_lexicon',
        )
        self.assertEqual(OlivaAIAgent.contentSafety.externalStatus()['words'], 2)

    def test_agent_output_is_replaced_before_send(self):
        event = mock.Mock()
        event.plugin_info = {'func_type': 'private_message'}
        event.reply.return_value = {'active': True, 'data': {'message_id': '1'}}
        event.data.message_id = 'incoming'
        with mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'):
            OlivaAIAgent.msgReply._safeReply(event, '介绍一下习近平', parsed={})
        event.reply.assert_called_once_with('换个话题吧')

    def test_voice_and_storage_reject_blocked_content(self):
        event = mock.Mock()
        voice_result = OlivaAIAgent.voice.sendVoice(
            {'plugin_event': event, 'Proc': None, 'trace_id': 'voice'},
            '介绍一下习近平',
        )
        self.assertFalse(voice_result['active'])
        with mock.patch.object(OlivaAIAgent.memory, 'memAdd') as mem_add:
            result = OlivaAIAgent.tools._t_mem_save(
                {
                    'Proc': None,
                    'trace_id': 'memory',
                    'platform': 'qq',
                    'func_type': 'private_message',
                    'user_id': 'u1',
                },
                {'scope': 'user', 'content': '介绍一下习近平'},
            )
        self.assertFalse(result['active'])
        mem_add.assert_not_called()

    def test_existing_session_content_is_hidden_on_read(self):
        key = 'qq|private|safety-test'
        OlivaAIAgent.memory._sessions[key] = [
            {'role': 'user', 'content': '介绍一下习近平'},
            {'role': 'assistant', 'content': '正常回复'},
        ]
        session = OlivaAIAgent.memory.getSession(key)
        self.assertEqual(session[0]['content'], OlivaAIAgent.contentSafety.HIDDEN_TEXT)
        self.assertEqual(session[1]['content'], '正常回复')
        OlivaAIAgent.memory._sessions.pop(key, None)


if __name__ == '__main__':
    unittest.main()
