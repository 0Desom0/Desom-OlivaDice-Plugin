# -*- encoding: utf-8 -*-

import copy
import unittest
from unittest import mock

import OlivaAIAgent


class GroupAgentInterruptTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = copy.deepcopy(OlivaAIAgent.conf.gConf)
        OlivaAIAgent.conf.gConf = {
            'ambient': {
                'retry_count': 1,
                'agent_max_turns': 4,
            },
            'agent': {
                'interrupt_previous_in_group': True,
                'max_auto_continuations': 2,
            },
            'debug_log': False,
        }
        OlivaAIAgent.ambient.cancelAllGroupAgents()

    def tearDown(self):
        OlivaAIAgent.ambient.cancelAllGroupAgents()
        OlivaAIAgent.conf.gConf = self.old_conf

    def test_default_config_and_gui_expose_group_interrupt_switch(self):
        self.assertTrue(
            OlivaAIAgent.conf.DEFAULT_CONF['agent']['interrupt_previous_in_group'],
        )
        self.assertEqual(
            '群内新对话打断旧 Agent',
            OlivaAIAgent.gui.FIELD_LABELS['interrupt_previous_in_group'],
        )

    def test_new_task_only_interrupts_previous_task_in_same_group(self):
        first = OlivaAIAgent.ambient._beginGroupAgent('qq', 'group-1', 'trace-first')
        other_group = OlivaAIAgent.ambient._beginGroupAgent('qq', 'group-2', 'trace-other')
        latest = OlivaAIAgent.ambient._beginGroupAgent('qq', 'group-1', 'trace-latest')

        self.assertFalse(OlivaAIAgent.ambient._groupAgentActive(first))
        self.assertTrue(OlivaAIAgent.ambient._groupAgentActive(other_group))
        self.assertTrue(OlivaAIAgent.ambient._groupAgentActive(latest))
        self.assertEqual('trace-first', latest['interrupted_trace_id'])

    def test_disabled_switch_keeps_existing_queue_behavior(self):
        OlivaAIAgent.conf.gConf['agent']['interrupt_previous_in_group'] = False

        self.assertIsNone(
            OlivaAIAgent.ambient._beginGroupAgent('qq', 'group-1', 'trace-disabled'),
        )

    def test_interruption_during_model_request_discards_old_reply(self):
        old_token = OlivaAIAgent.ambient._beginGroupAgent('qq', 'group-1', 'trace-old')

        def replace_old_task(*_args, **_kwargs):
            OlivaAIAgent.ambient._beginGroupAgent('qq', 'group-1', 'trace-new')
            return {'ok': True, 'text': '{"r":["过时回复"]}', 'tool_calls': []}

        with mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=replace_old_task) as chat:
            with self.assertRaises(OlivaAIAgent.ambient.GroupAgentInterrupted):
                OlivaAIAgent.ambient._callReply(
                    None,
                    None,
                    'bot',
                    'group-1',
                    [{'role': 'user', 'content': '旧消息'}],
                    [],
                    False,
                    trace_id='trace-old',
                    request_text='旧消息',
                    agent_token=old_token,
                )

        self.assertEqual(1, chat.call_count)

    def test_interruption_after_tool_plan_prevents_tool_execution(self):
        old_token = OlivaAIAgent.ambient._beginGroupAgent('qq', 'group-1', 'trace-old')

        def replace_old_task(*_args, **_kwargs):
            OlivaAIAgent.ambient._beginGroupAgent('qq', 'group-1', 'trace-new')
            return {
                'ok': True,
                'text': '准备执行工具',
                'tool_calls': [{
                    'id': 'call-old',
                    'name': 'run_command',
                    'arguments': '{"message":".r d100"}',
                }],
            }

        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=replace_old_task),
            mock.patch.object(OlivaAIAgent.tools, 'execTool') as exec_tool,
        ):
            with self.assertRaises(OlivaAIAgent.ambient.GroupAgentInterrupted):
                OlivaAIAgent.ambient._callReplyWithTools(
                    None,
                    None,
                    'bot',
                    'group-1',
                    [{'role': 'user', 'content': '旧消息'}],
                    [],
                    trace_id='trace-old',
                    tool_ctx={'trace_id': 'trace-old'},
                    tool_defs=[{'name': 'run_command'}],
                    request_text='旧消息',
                    agent_token=old_token,
                )

        exec_tool.assert_not_called()


if __name__ == '__main__':
    unittest.main()
