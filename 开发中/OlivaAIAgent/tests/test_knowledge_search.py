# -*- encoding: utf-8 -*-

import copy
import tempfile
import time
import unittest

import OlivaAIAgent


class KnowledgeSearchTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.knowledge._mem = {}
        OlivaAIAgent.knowledge._static = {}
        OlivaAIAgent.pacing.clear_peakup_cache()

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.knowledge._mem = {}
        OlivaAIAgent.knowledge._static = {}
        OlivaAIAgent.pacing.clear_peakup_cache()
        self.temp_dir.cleanup()

    def test_concatenated_history_finds_keyword_among_many_entries(self):
        noise = {'闲聊%d' % index: '无关内容%d' % index for index in range(80)}
        noise['旧城区'] = '霓虹暴雨的舞台'
        OlivaAIAgent.knowledge.updateKnowledge('bot-1', noise)
        history = [
            {'message': '今天吃什么', 'nickname': '甲', 'user_id': '1'},
            {'message': '随便吧', 'nickname': '乙', 'user_id': '2'},
            {'message': '旧城区怎么走', 'nickname': '丙', 'user_id': '3'},
        ]
        started = time.perf_counter()
        found = OlivaAIAgent.knowledge.searchRelevant('bot-1', history, 900, 0)
        elapsed = time.perf_counter() - started
        self.assertIn('旧城区', found)
        self.assertEqual('霓虹暴雨的舞台', found['旧城区'])
        self.assertLess(elapsed, 0.5)
