# -*- encoding: utf-8 -*-

import copy
import inspect
import unittest
from unittest import mock

import OlivaAIAgent


class FakeProc:
    def __init__(self):
        self.records = []

    def log(self, level, message, segments=None):
        self.records.append((level, message, segments))


class SignalLoggingTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = copy.deepcopy(OlivaAIAgent.conf.gConf)
        self.old_proc = OlivaAIAgent.conf.gProc
        self.proc = FakeProc()
        OlivaAIAgent.conf.gProc = self.proc
        OlivaAIAgent.conf.gConf = {'debug_log': True}

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.conf.gProc = self.old_proc

    def test_normalizes_token_usage_from_supported_api_shapes(self):
        cases = [
            (
                {
                    'prompt_tokens': 120,
                    'completion_tokens': 30,
                    'total_tokens': 150,
                    'prompt_cache_hit_tokens': 80,
                    'prompt_cache_miss_tokens': 40,
                },
                {'input_tokens': 120, 'output_tokens': 30, 'total_tokens': 150,
                 'cached_tokens': 80, 'cache_miss_tokens': 40},
            ),
            (
                {'input_tokens': 90, 'output_tokens': 10, 'cache_read_input_tokens': 50,
                 'cache_creation_input_tokens': 20},
                {'input_tokens': 90, 'output_tokens': 10, 'total_tokens': 100,
                 'cached_tokens': 50, 'cache_creation_tokens': 20},
            ),
            (
                {'input_tokens': 200, 'output_tokens': 25, 'total_tokens': 225,
                 'input_tokens_details': {'cached_tokens': 160}},
                {'input_tokens': 200, 'output_tokens': 25, 'total_tokens': 225, 'cached_tokens': 160},
            ),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(expected, OlivaAIAgent.aiClient._normalizeUsage(raw))

    def test_model_response_log_contains_trace_purpose_and_tokens(self):
        backend = {
            '_name': 'intent',
            'wire': 'openai',
            'api_url': 'https://example.invalid/chat',
            'api_key': 'secret',
            'model': 'small-model',
            'stream': False,
        }
        response = {
            'ok': True,
            'text': '{"d":"SKIP","i":""}',
            'tool_calls': [],
            'error': '',
            '_usage': {'prompt_tokens': 100, 'completion_tokens': 8, 'total_tokens': 108},
        }
        with mock.patch.object(OlivaAIAgent.aiClient, '_chat_openai', return_value=response):
            result = OlivaAIAgent.aiClient.chat(
                [{'role': 'user', 'content': '判断'}],
                backend_conf=backend,
                trace_id='trace-thinking',
                purpose='前置判断',
            )
        self.assertEqual(108, result['usage']['total_tokens'])
        logs = '\n'.join(record[1] for record in self.proc.records)
        self.assertIn('编号=trace-thinking', logs)
        self.assertIn('用途=前置判断', logs)
        self.assertIn('输入Token=100', logs)
        self.assertIn('输出Token=8', logs)
        self.assertIn('总Token=108', logs)

    def test_skill_log_names_selected_materials_on_cache_hits(self):
        context = (
            '[Skill: coc7 | Section: 战斗/闪避]\n规则内容\n\n'
            '[Skill: coc7 | Section: 战斗/反击]\n规则内容'
        )
        OlivaAIAgent.skills._logContextSelection(context, trace_id='trace-skill', cached=True)
        message = self.proc.records[-1][1]
        self.assertIn('已获取技能资料', message)
        self.assertIn('缓存命中=是', message)
        self.assertIn('技能=coc7', message)
        self.assertIn('coc7/战斗/闪避', message)
        self.assertIn('资料片段数=2', message)

    def test_conversation_decision_logs_reply_or_skip_in_one_line(self):
        OlivaAIAgent.ambient._logConversationDecision(
            self.proc,
            'trace-result',
            '回复',
            '主回复模型决定参与',
            result=['第一句', '第二句'],
            messages=2,
        )
        message = self.proc.records[-1][1]
        self.assertIn('本轮对话决定', message)
        self.assertIn('决定=回复', message)
        self.assertIn('结果=["第一句", "第二句"]', message)
        self.assertIn('消息数=2', message)

    def test_group_router_no_longer_emits_high_frequency_noise(self):
        source = inspect.getsource(OlivaAIAgent.msgReply._onGroupMessage)
        self.assertNotIn('message.group.received', source)
        self.assertNotIn('route.group.ambient_off', source)
        self.assertNotIn('route.group.disabled', source)


if __name__ == '__main__':
    unittest.main()
