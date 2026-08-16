# -*- encoding: utf-8 -*-

import json
import unittest
from unittest import mock

import OlivaAIAgent


class FinalReplyTest(unittest.TestCase):
    def test_strict_parser_only_accepts_exact_string_array_envelope(self):
        self.assertEqual(
            ['第一条', '第二条'],
            OlivaAIAgent.finalReply.parseStrictEnvelope('{"r":["第一条","第二条"]}'),
        )
        invalid_values = [
            '```json\n{"r":["回复"]}\n```',
            '{"r":["回复"],"reason":"过程"}',
            '{"r":[1]}',
            '前缀 {"r":["回复"]}',
            '{:r:["回复"]}',
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertIsNone(OlivaAIAgent.finalReply.parseStrictEnvelope(value))

    def test_dumped_envelope_can_always_be_strictly_parsed(self):
        raw = OlivaAIAgent.finalReply.dumpEnvelope(['包含“引号”与\n换行'])

        self.assertEqual({'r': ['包含“引号”与\n换行']}, json.loads(raw))
        self.assertEqual(['包含“引号”与\n换行'], OlivaAIAgent.finalReply.parseStrictEnvelope(raw))

    def test_finalizer_has_no_tools_and_forces_json_without_thinking(self):
        response = {'ok': True, 'text': '{"r":["最终答案"]}', 'tool_calls': []}
        with mock.patch.object(OlivaAIAgent.aiClient, 'chat', return_value=response) as chat:
            replies = OlivaAIAgent.finalReply.finalize(
                [{'role': 'user', 'content': '问题'}],
                draft='候选答案',
                max_attempts=2,
            )

        self.assertEqual(['最终答案'], replies)
        self.assertIsNone(chat.call_args.kwargs['tools'])
        self.assertTrue(chat.call_args.kwargs['force_no_stream'])
        self.assertTrue(chat.call_args.kwargs['response_json'])
        self.assertTrue(chat.call_args.kwargs['thinking_off'])
        self.assertIn('最终回复 JSON 整理', chat.call_args.args[0][-1]['content'])

    def test_mixed_deliberation_is_never_locally_wrapped_as_reply(self):
        leaked = {
            'ok': True,
            'text': '当前发言者是燕尘，让我构思一下。\n\n真正回复放这里。',
            'tool_calls': [],
        }
        with mock.patch.object(OlivaAIAgent.aiClient, 'chat', return_value=leaked):
            replies = OlivaAIAgent.finalReply.finalize(
                [{'role': 'user', 'content': '帮我构思'}],
                draft=leaked['text'],
                max_attempts=2,
            )

        self.assertIsNone(replies)

    def test_safe_relaxed_json_is_canonicalized_locally(self):
        malformed = {'ok': True, 'text': '{:r:["宽容回复"]}', 'tool_calls': []}
        with mock.patch.object(OlivaAIAgent.aiClient, 'chat', return_value=malformed):
            replies = OlivaAIAgent.finalReply.finalize(
                [{'role': 'user', 'content': '问题'}],
                max_attempts=2,
                relaxed_parser=OlivaAIAgent.ambient._parseR,
            )

        self.assertEqual(['宽容回复'], replies)


if __name__ == '__main__':
    unittest.main()
