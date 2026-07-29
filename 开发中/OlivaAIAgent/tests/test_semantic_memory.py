# -*- encoding: utf-8 -*-

import copy
import tempfile
import unittest
from unittest import mock

import OlivaAIAgent


class SemanticMemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.semantic._initialized_path = None
        OlivaAIAgent.semantic._embedding_cache.clear()
        OlivaAIAgent.semantic._failure_until = 0.0
        OlivaAIAgent.semantic._last_error = ''

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.semantic._initialized_path = None
        self.temp_dir.cleanup()

    def test_keyword_fallback_persists_source_identifiers(self):
        with mock.patch.object(OlivaAIAgent.semantic, 'embedTexts', return_value=[None]):
            saved = OlivaAIAgent.semantic.upsertFacts(
                'bot-1',
                'qq',
                'group-1',
                [{
                    'subject': '旧城区失踪案',
                    'content': '调查员正在旧城区追查连续失踪事件',
                    'keywords': ['旧城区', '失踪案'],
                }],
                source={
                    'message_id': 'source-message',
                    'reference_message_id': 'source-reference',
                    'event_id': 'source-event',
                    'time': '2026-07-29T12:00:00+08:00',
                },
            )
        self.assertEqual(1, saved)
        with mock.patch.object(OlivaAIAgent.semantic, 'embedTexts', return_value=[None]):
            found = OlivaAIAgent.semantic.searchFacts('bot-1', 'qq', 'group-1', '旧城区有什么线索')
        self.assertEqual('旧城区失踪案', found[0]['subject'])
        self.assertEqual('source-message', found[0]['source_message_id'])
        self.assertEqual('source-reference', found[0]['source_reference_id'])
        self.assertIsNone(found[0]['vector_score'])

    def test_vector_search_and_deduplication(self):
        def fake_embeddings(texts):
            vectors = []
            for text in texts:
                if '红色钥匙' in text or '开门的东西' in text:
                    vectors.append([1.0, 0.0])
                else:
                    vectors.append([0.0, 1.0])
            return vectors

        facts = [
            {'subject': '红色钥匙', 'content': '红色钥匙藏在旧图书馆二楼'},
            {'subject': '天气', 'content': '今日天气晴朗'},
        ]
        with mock.patch.object(OlivaAIAgent.semantic, 'embedTexts', side_effect=fake_embeddings):
            OlivaAIAgent.semantic.upsertFacts('bot-1', 'qq', 'group-1', facts)
            OlivaAIAgent.semantic.upsertFacts('bot-1', 'qq', 'group-1', facts[:1])
            found = OlivaAIAgent.semantic.searchFacts('bot-1', 'qq', 'group-1', '开门的东西在哪里')

        self.assertEqual(2, OlivaAIAgent.semantic.countFacts('bot-1', 'qq', 'group-1'))
        self.assertEqual('红色钥匙', found[0]['subject'])
        self.assertGreater(found[0]['vector_score'], 0.9)


if __name__ == '__main__':
    unittest.main()
