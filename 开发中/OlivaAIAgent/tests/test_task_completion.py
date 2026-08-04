# -*- encoding: utf-8 -*-

import copy
import inspect
import unittest
from unittest import mock

import OlivaAIAgent


class TaskCompletionTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = copy.deepcopy(OlivaAIAgent.conf.gConf)
        OlivaAIAgent.conf.gConf = {
            'ambient': {
                'retry_count': 1,
                'agent_max_turns': 4,
            },
            'agent': {
                'max_auto_continuations': 2,
            },
            'debug_log': False,
        }

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf

    def test_detects_promises_and_fake_completion(self):
        incomplete = [
            '资料我这就发出来，稍等一小小会儿~',
            '这个模组的开局背景、故事大纲和简介都帮你理好了呢。',
            '刚才已经放到旧城区那个文件夹里了，翻翻看呀。',
            '还在帮你生成，马上就好。',
        ]
        for reply in incomplete:
            with self.subTest(reply=reply):
                self.assertTrue(OlivaAIAgent.completion.needsContinuation(reply))

    def test_accepts_delivered_content_and_real_action_confirmation(self):
        delivered = (
            '我已经帮你整理好了：开局背景是夜之城旧城区发生连续失踪案，'
            '玩家受雇调查一枚会篡改记忆的义体芯片。'
        )
        self.assertFalse(OlivaAIAgent.completion.needsContinuation(delivered))
        self.assertFalse(OlivaAIAgent.completion.needsContinuation(
            '已经整理好了。',
            action_performed=True,
        ))
        self.assertFalse(OlivaAIAgent.completion.needsContinuation(
            '提醒已经设好，稍后会给你发消息。',
            action_performed=True,
        ))

    def test_only_successful_non_read_only_tools_count_as_completed_actions(self):
        success = '{"active":true,"data":"ok"}'
        failure = '{"error":"failed"}'
        self.assertTrue(OlivaAIAgent.completion.toolCompletedAction('schedule_reminder', success))
        self.assertFalse(OlivaAIAgent.completion.toolCompletedAction('web_search', success))
        self.assertFalse(OlivaAIAgent.completion.toolCompletedAction('schedule_reminder', failure))

    def test_ambient_reply_continues_until_content_is_delivered(self):
        responses = [
            {'ok': True, 'text': '{"r":["资料我这就发，稍等一下"]}', 'tool_calls': []},
            {
                'ok': True,
                'text': '{"r":["开局背景：夜之城旧城区爆发了记忆失窃案。"]}',
                'tool_calls': [],
            },
        ]
        with mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=responses) as chat:
            reply = OlivaAIAgent.ambient._callReply(
                None,
                None,
                'bot',
                'group',
                [{'role': 'user', 'content': '帮我写开局背景'}],
                [],
                False,
                trace_id='continuation-test',
            )

        self.assertEqual(['开局背景：夜之城旧城区爆发了记忆失窃案。'], reply)
        self.assertEqual(2, chat.call_count)
        second_messages = chat.call_args_list[1].args[0]
        self.assertTrue(any(
            message.get('role') == 'system' and '未完成任务自动续行' in message.get('content', '')
            for message in second_messages
        ))

    def test_ambient_tool_chain_also_continues_without_a_tool_call(self):
        responses = [
            {'ok': True, 'text': '{"r":["都整理好了呢"]}', 'tool_calls': []},
            {'ok': True, 'text': '{"r":["故事大纲：义体芯片正在吞噬持有者的记忆。"]}', 'tool_calls': []},
        ]
        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=responses) as chat,
            mock.patch.object(OlivaAIAgent.voice, 'hasSentVoice', return_value=False),
        ):
            reply = OlivaAIAgent.ambient._callReplyWithTools(
                None,
                None,
                'bot',
                'group',
                [{'role': 'user', 'content': '帮我写故事大纲'}],
                [],
                trace_id='continuation-tools-test',
                tool_ctx={'trace_id': 'continuation-tools-test'},
                tool_defs=[{'name': 'dummy'}],
            )

        self.assertEqual(['故事大纲：义体芯片正在吞噬持有者的记忆。'], reply)
        self.assertEqual(2, chat.call_count)

    def test_repeated_empty_promises_stop_at_configured_limit(self):
        response = {'ok': True, 'text': '{"r":["稍等一下，我马上发"]}', 'tool_calls': []}
        with mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=[response, response, response]) as chat:
            reply = OlivaAIAgent.ambient._callReply(
                None,
                None,
                'bot',
                'group',
                [{'role': 'user', 'content': '直接给我结果'}],
                [],
                False,
            )

        self.assertEqual([OlivaAIAgent.completion.exhaustedReply()], reply)
        self.assertEqual(3, chat.call_count)

    def test_full_agent_loop_uses_the_same_completion_audit(self):
        source = inspect.getsource(OlivaAIAgent.msgReply._runAgent)
        self.assertIn('completion.needsContinuation', source)
        self.assertIn('max_auto_continuations', source)


if __name__ == '__main__':
    unittest.main()
