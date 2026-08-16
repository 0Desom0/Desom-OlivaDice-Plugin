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

    def test_ordinary_chat_does_not_start_completion_chain(self):
        self.assertFalse(OlivaAIAgent.completion.requestRequiresDelivery('我到时候给小芙也p一张'))
        self.assertFalse(OlivaAIAgent.completion.needsContinuation(
            '刚才没有真正完成你的请求，请再发一次。',
            request_text='我到时候给小芙也p一张',
        ))

    def test_explicit_request_still_starts_completion_chain(self):
        self.assertTrue(OlivaAIAgent.completion.requestRequiresDelivery('帮我写一个模组简介'))
        self.assertTrue(OlivaAIAgent.completion.needsContinuation(
            '资料我马上发。',
            request_text='帮我写一个模组简介',
        ))

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
                request_text='帮我写开局背景',
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
            {'ok': True, 'text': '都整理好了呢', 'tool_calls': []},
            {'ok': True, 'text': '{"r":["都整理好了呢"]}', 'tool_calls': []},
            {'ok': True, 'text': '故事大纲：义体芯片正在吞噬持有者的记忆。', 'tool_calls': []},
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
                request_text='帮我写故事大纲',
        )

        self.assertEqual(['故事大纲：义体芯片正在吞噬持有者的记忆。'], reply)
        self.assertEqual(4, chat.call_count)
        self.assertIsNotNone(chat.call_args_list[2].kwargs['tools'])
        self.assertIsNone(chat.call_args_list[3].kwargs['tools'])

    def test_tool_call_with_intermediate_text_continues_to_final_reply(self):
        responses = [
            {
                'ok': True,
                'text': '我先查一下，马上告诉你。',
                'tool_calls': [{
                    'id': 'call-1',
                    'name': 'web_search',
                    'arguments': '{"query":"测试"}',
                }],
            },
            {
                'ok': True,
                'text': '查到了：这是测试结果。',
                'tool_calls': [],
            },
            {'ok': True, 'text': '{"r":["查到了：这是测试结果。"]}', 'tool_calls': []},
        ]
        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=responses) as chat,
            mock.patch.object(
                OlivaAIAgent.tools,
                'execTool',
                return_value='{"active":true,"data":{"items":["ok"]}}',
            ) as exec_tool,
            mock.patch.object(OlivaAIAgent.voice, 'hasSentVoice', return_value=False),
        ):
            reply = OlivaAIAgent.ambient._callReplyWithTools(
                None,
                None,
                'bot',
                'group',
                [{'role': 'user', 'content': '帮我查测试'}],
                [],
                trace_id='tool-intermediate-text-test',
                tool_ctx={'trace_id': 'tool-intermediate-text-test'},
                tool_defs=[{'name': 'web_search'}],
                request_text='帮我查测试',
            )

        self.assertEqual(['查到了：这是测试结果。'], reply)
        self.assertEqual(3, chat.call_count)
        exec_tool.assert_called_once()
        final_call = chat.call_args_list[2]
        self.assertIsNone(final_call.kwargs['tools'])
        self.assertTrue(final_call.kwargs['response_json'])
        self.assertTrue(final_call.kwargs['thinking_off'])

    def test_planning_draft_is_always_finalized_by_separate_json_call(self):
        planning = {
            'ok': True,
            'text': '最终回复。',
            'tool_calls': [],
        }
        finalized = {'ok': True, 'text': '{"r":["最终回复。"]}', 'tool_calls': []}
        with (
            mock.patch.object(
                OlivaAIAgent.aiClient,
                'chat',
                side_effect=[planning, finalized],
            ) as chat,
            mock.patch.object(OlivaAIAgent.voice, 'hasSentVoice', return_value=False),
        ):
            reply = OlivaAIAgent.ambient._callReplyWithTools(
                None,
                None,
                'bot',
                'group',
                [{'role': 'user', 'content': '接着说'}],
                [],
                trace_id='agent-round-budget-test',
                tool_ctx={'trace_id': 'agent-round-budget-test'},
                tool_defs=[{'name': 'dummy'}],
                request_text='接着说',
            )

        self.assertEqual(['最终回复。'], reply)
        self.assertEqual(2, chat.call_count)
        self.assertIsNotNone(chat.call_args_list[0].kwargs['tools'])
        self.assertIsNone(chat.call_args_list[1].kwargs['tools'])
        self.assertTrue(chat.call_args_list[1].kwargs['response_json'])
        self.assertTrue(chat.call_args_list[1].kwargs['thinking_off'])

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
                request_text='直接给我结果',
            )

        self.assertEqual([OlivaAIAgent.completion.exhaustedReply()], reply)
        self.assertEqual(3, chat.call_count)

    def test_full_agent_loop_uses_the_same_completion_audit(self):
        source = inspect.getsource(OlivaAIAgent.msgReply._runAgent)
        self.assertIn('completion.needsContinuation', source)
        self.assertIn('max_auto_continuations', source)
        self.assertIn('智能体工具收尾', source)
        self.assertIn('finalReply.finalize', source)

    def test_explicit_agent_normalizes_reply_json_but_keeps_plain_text(self):
        self.assertEqual(
            '已经查到了。',
            OlivaAIAgent.msgReply._normalizeAgentFinalText('{"r":["已经查到了。"]}'),
        )
        self.assertEqual(
            '普通自然语言回复。',
            OlivaAIAgent.msgReply._normalizeAgentFinalText('普通自然语言回复。'),
        )
        self.assertEqual(
            '',
            OlivaAIAgent.msgReply._normalizeAgentFinalText('{"r":["结果未闭合"'),
        )


if __name__ == '__main__':
    unittest.main()
