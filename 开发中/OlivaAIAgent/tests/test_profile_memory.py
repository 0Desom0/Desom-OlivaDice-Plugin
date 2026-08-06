# -*- encoding: utf-8 -*-

import copy
import json
import tempfile
import unittest
from unittest import mock

import OlivaAIAgent


class ProfileMemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.knowledge._mem.clear()
        OlivaAIAgent.knowledge._mem_mtime.clear()

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.knowledge._mem.clear()
        OlivaAIAgent.knowledge._mem_mtime.clear()
        self.temp_dir.cleanup()

    def test_profile_update_receives_old_impression_and_is_limited_to_100_chars(self):
        OlivaAIAgent.knowledge.updateProfiles('bot-hash', {'user-1': '小雨：喜欢音乐，聊天直接'})
        history = [{
            'user_id': 'user-1',
            'nickname': '小雨',
            'message': '最近开始主持赛博朋克团',
        }]
        merged = '小雨：喜欢音乐，聊天直接；最近开始主持赛博朋克团，重视气氛和临场发挥。' + ('新' * 100)
        response = {'ok': True, 'text': json.dumps({'u': {'user-1': merged}}, ensure_ascii=False)}

        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'getAuxiliaryBackendConf', return_value={}),
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', return_value=response) as chat,
            mock.patch.object(OlivaAIAgent.ambient, 'formatHistoryForModel', return_value='聊天记录'),
        ):
            OlivaAIAgent.knowledge.runMemoryExtraction(
                'bot-hash',
                'group-1',
                history,
                record_knowledge=False,
                record_summary=False,
                record_vector=False,
                record_profiles=True,
            )

        prompt = chat.call_args.args[0][1]['content']
        saved = OlivaAIAgent.knowledge.getMem('bot-hash')['全局']['用户侧写']['user-1']
        self.assertIn('已有个人印象', prompt)
        self.assertIn('小雨：喜欢音乐，聊天直接', prompt)
        self.assertLessEqual(len(saved), 100)
        self.assertTrue(saved.startswith('小雨：喜欢音乐，聊天直接；最近开始主持赛博朋克团'))


if __name__ == '__main__':
    unittest.main()
