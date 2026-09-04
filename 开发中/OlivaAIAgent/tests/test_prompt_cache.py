# -*- encoding: utf-8 -*-

import copy
import tempfile
import unittest

import OlivaAIAgent


class PromptCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.memory._sessions.clear()

    def tearDown(self):
        OlivaAIAgent.memory._sessions.clear()
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        self.temp_dir.cleanup()

    @staticmethod
    def _round(index):
        return [
            {'role': 'user', 'content': 'u%d' % index},
            {'role': 'assistant', 'content': 'a%d' % index},
        ]

    def test_agent_history_grows_then_rolls_over_in_a_batch(self):
        memory_conf = OlivaAIAgent.conf.gConf['memory']
        memory_conf['max_rounds'] = 2
        memory_conf['prompt_cache_optimized'] = True
        memory_conf['prompt_cache_max_rounds'] = 4

        for index in range(1, 5):
            OlivaAIAgent.memory.appendSession('session', self._round(index))
        self.assertEqual(8, len(OlivaAIAgent.memory.getSession('session')))

        OlivaAIAgent.memory.appendSession('session', self._round(5))
        self.assertEqual(
            ['u4', 'a4', 'u5', 'a5'],
            [item['content'] for item in OlivaAIAgent.memory.getSession('session')],
        )

    def test_cache_optimization_can_be_disabled(self):
        memory_conf = OlivaAIAgent.conf.gConf['memory']
        memory_conf['max_rounds'] = 2
        memory_conf['prompt_cache_optimized'] = False

        for index in range(1, 4):
            OlivaAIAgent.memory.appendSession('session', self._round(index))
        self.assertEqual(
            ['u2', 'a2', 'u3', 'a3'],
            [item['content'] for item in OlivaAIAgent.memory.getSession('session')],
        )

    def test_invalid_cache_rounds_falls_back_safely(self):
        memory_conf = OlivaAIAgent.conf.gConf['memory']
        memory_conf['max_rounds'] = 'invalid'
        memory_conf['prompt_cache_max_rounds'] = None

        OlivaAIAgent.memory.appendSession('session', self._round(1))
        self.assertEqual(2, len(OlivaAIAgent.memory.getSession('session')))

    def test_volatile_context_stays_after_history(self):
        messages = OlivaAIAgent.ambient.buildContextMessages(
            'system',
            [{'nickname': '甲', 'user_id': '1', 'time': 'now', 'message': 'history'}],
            patch={'time': 'later'},
        )

        self.assertEqual('system', messages[0]['content'])
        self.assertIn('history', messages[1]['content'])
        self.assertIn('later', messages[2]['content'])

    def test_force_task_is_not_part_of_stable_system_prompt(self):
        source = __import__('inspect').getsource(OlivaAIAgent.ambient._reply)

        self.assertNotIn('system_content += _mainDecisionTask', source)
        self.assertIn(
            "messages.append({'role': 'system', 'content': _mainDecisionTask(require_reply)})",
            source,
        )


if __name__ == '__main__':
    unittest.main()
