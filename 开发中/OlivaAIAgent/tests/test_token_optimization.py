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
            'extra_headers': {'X-Test': 'yes'},
            'extra_body': {'seed': 7},
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
        self.assertEqual({'X-Test': 'yes'}, backend['extra_headers'])
        self.assertEqual({'seed': 7}, backend['extra_body'])

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

    def test_tool_router_retries_malformed_small_model_output(self):
        responses = [
            {'ok': True, 'text': '{"d":"NEXT"}'},
            {'ok': True, 'text': 'web_search'},
        ]
        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=responses) as chat,
            mock.patch.object(OlivaAIAgent.voice, 'getStatus', return_value={'ready': False}),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
        ):
            names = OlivaAIAgent.tools.selectToolNames({}, '帮我查一下资料')

        self.assertIn('web_search', names)
        self.assertIn('fetch_url', names)
        self.assertEqual(2, chat.call_count)

    def test_tool_route_parser_accepts_aliases_and_plain_text(self):
        available = {'web_search': {}, 'fetch_url': {}}

        self.assertEqual(
            {'web_search'},
            OlivaAIAgent.tools._parseToolRoute('{"tool":"web_search"}', available),
        )
        self.assertEqual(
            {'fetch_url'},
            OlivaAIAgent.tools._parseToolRoute('建议调用 fetch_url 即可', available),
        )
        self.assertEqual(set(), OlivaAIAgent.tools._parseToolRoute('无需任何工具', available))

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

    def test_malformed_successful_reply_gets_one_json_repair_before_local_fallback(self):
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
        self.assertEqual(2, chat.call_count)
        self.assertTrue(chat.call_args.kwargs['response_json'])
        self.assertTrue(chat.call_args.kwargs['thinking_off'])

    def test_participation_parser_accepts_json_alias_and_plain_text(self):
        self.assertEqual(
            'SKIP',
            OlivaAIAgent.ambient._parseParticipationDecision('{"should_reply":false}'),
        )
        self.assertEqual('SKIP', OlivaAIAgent.ambient._parseParticipationDecision('不需要回复'))
        self.assertEqual('NEXT', OlivaAIAgent.ambient._parseParticipationDecision('NEXT，因为被点名了'))

    def test_image_parser_accepts_alias_filename_and_plain_text(self):
        candidates = {'fox.gif': {'content': '狐狸捂脸', 'intent': '无奈'}}

        self.assertEqual(
            '无奈',
            OlivaAIAgent.preflight._imageValue('{"i":"无奈"}', candidates),
        )
        self.assertEqual(
            'fox.gif',
            OlivaAIAgent.preflight._imageValue('建议选择 fox.gif 比较合适', candidates),
        )
        self.assertEqual(
            '狐狸捂脸',
            OlivaAIAgent.preflight._imageValue('图片：狐狸捂脸', candidates),
        )
        self.assertEqual(
            '',
            OlivaAIAgent.preflight._imageValue('{"image":"img_4f6b4a', candidates),
        )

    def test_auxiliary_cluster_isolates_failed_task(self):
        def failed():
            raise RuntimeError('bad output')

        with mock.patch.object(OlivaAIAgent.conf, 'traceLog'):
            results = OlivaAIAgent.preflight.runCluster({
                'reply': lambda: 'NEXT',
                'image': failed,
                'tools': lambda: ['web_search'],
            })

        self.assertEqual('NEXT', results['reply'])
        self.assertIsNone(results['image'])
        self.assertEqual(['web_search'], results['tools'])


if __name__ == '__main__':
    unittest.main()
