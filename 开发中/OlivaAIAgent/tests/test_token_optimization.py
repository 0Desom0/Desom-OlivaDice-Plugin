# -*- encoding: utf-8 -*-

import copy
import json
import unittest
from unittest import mock

import OlivaAIAgent


class TokenOptimizationTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf

    def test_official_deepseek_explicitly_disables_default_thinking(self):
        payload = {}
        backend = {
            'api_url': 'https://api.deepseek.com/v1/chat/completions',
            'thinking': {'type': 'disabled'},
        }

        OlivaAIAgent.aiClient._apply_thinking(payload, backend, {})

        self.assertEqual({'type': 'disabled'}, payload['thinking'])
        self.assertNotIn('reasoning_effort', payload)

    def test_strict_openai_endpoint_does_not_receive_disabled_extension(self):
        payload = {}
        backend = {
            'api_url': 'https://api.openai.com/v1/chat/completions',
            'thinking': {'type': 'disabled'},
        }

        OlivaAIAgent.aiClient._apply_thinking(payload, backend, {})

        self.assertNotIn('thinking', payload)

    def test_thinking_off_overrides_enabled_for_official_deepseek(self):
        payload = {}
        backend = {
            'api_url': 'https://api.deepseek.com/v1/chat/completions',
            'thinking': {'type': 'enabled'},
            'reasoning_effort': 'max',
        }

        OlivaAIAgent.aiClient._apply_thinking(payload, backend, {'thinking_off': True})

        self.assertEqual({'type': 'disabled'}, payload['thinking'])
        self.assertNotIn('reasoning_effort', payload)

    def test_auxiliary_backend_uses_intent_api_with_task_limits(self):
        OlivaAIAgent.conf.gConf['ambient']['intent_api'].update({
            'enable': True,
            'api_url': 'https://example.test/v1/responses',
            'api_key': 'test-key',
            'model': 'cheap-model',
        })

        backend = OlivaAIAgent.aiClient.getAuxiliaryBackendConf(
            max_tokens=1200,
            temperature=0.2,
        )

        self.assertEqual('intent', backend['_name'])
        self.assertEqual('responses', backend['wire'])
        self.assertEqual(1200, backend['max_tokens'])
        self.assertEqual(0.2, backend['temperature'])
        self.assertFalse(backend['stream'])

    def test_tool_router_can_select_no_tools_for_plain_chat(self):
        response = {'ok': True, 'text': json.dumps({'tools': []})}
        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', return_value=response),
            mock.patch.object(OlivaAIAgent.voice, 'getStatus', return_value={'ready': False}),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
        ):
            names = OlivaAIAgent.tools.selectToolNames({}, '晚上好呀')

        self.assertEqual([], names)

    def test_tool_router_expands_dependent_tool_family(self):
        response = {'ok': True, 'text': json.dumps({'tools': ['web_search']})}
        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', return_value=response),
            mock.patch.object(OlivaAIAgent.voice, 'getStatus', return_value={'ready': False}),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
        ):
            names = OlivaAIAgent.tools.selectToolNames({}, '帮我联网搜索这个资料')

        self.assertIn('web_search', names)
        self.assertIn('fetch_url', names)

    def test_tool_router_failure_preserves_all_available_tools(self):
        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=RuntimeError('offline')),
            mock.patch.object(OlivaAIAgent.voice, 'getStatus', return_value={'ready': False}),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
        ):
            expected = [item['name'] for item in OlivaAIAgent.tools.getToolsForRequest({})]
            names = OlivaAIAgent.tools.selectToolNames({}, '执行一个操作')

        self.assertEqual(expected, names)

    def test_tool_definitions_are_filtered_by_routed_names(self):
        with mock.patch.object(OlivaAIAgent.voice, 'getStatus', return_value={'ready': False}):
            definitions = OlivaAIAgent.tools.getToolsForRequest(
                {},
                names=['web_search', 'fetch_url'],
            )

        self.assertEqual(['web_search', 'fetch_url'], [item['name'] for item in definitions])

    def test_malformed_successful_reply_uses_local_fallback_without_retry(self):
        response = {'ok': True, 'text': '直接回复内容'}
        with mock.patch.object(OlivaAIAgent.aiClient, 'chat', return_value=response) as chat:
            replies = OlivaAIAgent.ambient._callReply(
                None,
                None,
                'bot-hash',
                'group-1',
                [{'role': 'user', 'content': '你好'}],
                [],
                False,
            )

        self.assertEqual(['直接回复内容'], replies)
        self.assertEqual(1, chat.call_count)


if __name__ == '__main__':
    unittest.main()
