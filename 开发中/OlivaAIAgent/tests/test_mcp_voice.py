# -*- encoding: utf-8 -*-

import copy
import json
import os
import tempfile
import unittest
from unittest import mock

import OlivOS
import OlivaAIAgent


class FakeHttpResponse:
    def __init__(self, data=None, content=b'', content_type='application/json', status_code=200, session_id=None):
        self._data = data
        self.content = content
        self.status_code = status_code
        self.headers = {'Content-Type': content_type}
        if session_id:
            self.headers['Mcp-Session-Id'] = session_id
        self.text = '' if data is None else json.dumps(data, ensure_ascii=False)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code < 200 or self.status_code >= 300:
            raise RuntimeError('HTTP %s' % self.status_code)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.requests.append({'url': url, 'headers': headers, 'json': json, 'timeout': timeout})
        return self.responses.pop(0)

    def close(self):
        pass


class FakeVoiceEvent:
    def __init__(self):
        self.replies = []

    def reply(self, message):
        self.replies.append(message)
        return {'active': True, 'data': {'message_id': 'voice-message-1'}}


class McpVoiceTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.conf.gConf['debug_log'] = False
        OlivaAIAgent.mcp.invalidate()

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.mcp.invalidate()

    def test_streamable_http_discovers_and_calls_mcp_tool(self):
        OlivaAIAgent.conf.gConf['mcp'].update({
            'enabled': True,
            'servers': [{
                'name': 'demo',
                'transport': 'streamable_http',
                'url': 'https://mcp.example.invalid/rpc',
                'headers': {'Authorization': 'Bearer hidden'},
                'danger': False,
            }],
        })
        discovery = FakeSession([
            FakeHttpResponse({
                'jsonrpc': '2.0',
                'id': 1,
                'result': {
                    'protocolVersion': '2025-03-26',
                    'serverInfo': {'name': 'demo-server', 'version': '1.0'},
                    'capabilities': {'tools': {}},
                },
            }, session_id='session-1'),
            FakeHttpResponse(None, status_code=202),
            FakeHttpResponse({
                'jsonrpc': '2.0',
                'id': 2,
                'result': {
                    'tools': [{
                        'name': 'echo',
                        'description': '返回输入内容',
                        'inputSchema': {
                            'type': 'object',
                            'properties': {'text': {'type': 'string'}},
                            'required': ['text'],
                        },
                    }],
                },
            }),
        ])
        caller = FakeSession([
            FakeHttpResponse({
                'jsonrpc': '2.0',
                'id': 1,
                'result': {'protocolVersion': '2025-03-26', 'capabilities': {}},
            }, session_id='session-2'),
            FakeHttpResponse(None, status_code=202),
            FakeHttpResponse({
                'jsonrpc': '2.0',
                'id': 2,
                'result': {'content': [{'type': 'text', 'text': '你好'}], 'isError': False},
            }),
        ])

        with mock.patch.object(OlivaAIAgent.mcp.requests, 'Session', side_effect=[discovery, caller]):
            status = OlivaAIAgent.mcp.refresh(force=True)
            definitions = OlivaAIAgent.tools.getToolsForRequest({})
            result = json.loads(OlivaAIAgent.tools.execTool('mcp_demo_echo', {'text': '你好'}, {}))

        self.assertEqual(1, status['connected'])
        self.assertEqual(1, status['tools'])
        self.assertIn('mcp_demo_echo', [item['name'] for item in definitions])
        self.assertTrue(result['active'])
        self.assertEqual('echo', result['data']['tool'])
        self.assertEqual('tools/call', caller.requests[-1]['json']['method'])
        self.assertEqual({'text': '你好'}, caller.requests[-1]['json']['params']['arguments'])
        self.assertEqual('session-2', caller.requests[-1]['headers']['Mcp-Session-Id'])

    def test_stdio_resolves_windows_path_commands_without_shell(self):
        process = mock.MagicMock()
        process.stdout = []
        process.stderr = []
        with mock.patch.object(OlivaAIAgent.mcp.shutil, 'which', return_value=r'C:\Tools\npx.cmd') as which, \
                mock.patch.object(OlivaAIAgent.mcp.subprocess, 'Popen', return_value=process) as popen:
            transport = OlivaAIAgent.mcp._StdioTransport({
                'command': 'npx',
                'args': ['-y', 'demo-mcp'],
                'env': {'MCP_TEST': '1'},
            })

        which.assert_called_once()
        kwargs = popen.call_args.kwargs
        self.assertEqual([r'C:\Tools\npx.cmd', '-y', 'demo-mcp'], kwargs['args'])
        self.assertNotIn('shell', kwargs)
        self.assertEqual('1', kwargs['env']['MCP_TEST'])
        transport.process = process

    def test_send_voice_tool_is_visible_only_when_ready_and_sends_record_segment(self):
        OlivaAIAgent.conf.gConf['voice'].update({
            'enabled': True,
            'provider': 'openai_compatible',
            'api_url': 'https://voice.example.invalid/v1/audio/speech',
            'api_key': 'secret-key',
            'model': 'qwen-tts',
            'voice': 'Cherry',
            'response_format': 'mp3',
        })
        event = FakeVoiceEvent()
        response = FakeHttpResponse(content=b'ID3FAKEAUDIO', content_type='audio/mpeg')
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(OlivaAIAgent.voice, 'outputDir', return_value=directory), \
                mock.patch.object(OlivaAIAgent.voice.requests, 'post', return_value=response) as post, \
                mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing') as record_outgoing:
            definitions = OlivaAIAgent.tools.getToolsForRequest({})
            result = OlivaAIAgent.voice.sendVoice(
                {'plugin_event': event, 'Proc': None, 'trace_id': 'voice-test'},
                '今晚八点开团。',
            )

        self.assertIn('send_voice', [item['name'] for item in definitions])
        self.assertTrue(result['active'])
        self.assertEqual(1, len(event.replies))
        message = event.replies[0]
        self.assertIsInstance(message, OlivOS.messageAPI.Message_templet)
        self.assertIsInstance(message.data[0], OlivOS.messageAPI.PARA.record)
        self.assertTrue(os.path.isabs(message.data[0].data['file']))
        request = post.call_args.kwargs
        self.assertEqual('Bearer secret-key', request['headers']['Authorization'])
        self.assertEqual('今晚八点开团。', request['json']['input'])
        record_outgoing.assert_called_once()

    def test_dashscope_non_streaming_tts_uses_official_payload_and_audio_url(self):
        OlivaAIAgent.conf.gConf['voice'].update({
            'enabled': True,
            'provider': 'dashscope_multimodal',
            'api_key': 'dashscope-key',
            'optimize_instructions': True,
        })
        event = FakeVoiceEvent()
        response = FakeHttpResponse(data={
            'status_code': 200,
            'output': {
                'audio': {
                    'url': 'https://dashscope-result.example.invalid/generated.wav?Expires=1',
                },
            },
        })
        download = FakeHttpResponse(
            content=b'RIFF\x00\x00\x00\x00WAVEfmt FAKEAUDIO',
            content_type='audio/wav',
        )

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(OlivaAIAgent.voice, 'outputDir', return_value=directory), \
                mock.patch.object(OlivaAIAgent.voice.requests, 'post', return_value=response) as post, \
                mock.patch.object(OlivaAIAgent.voice.requests, 'get', return_value=download) as get, \
                mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'):
            result = OlivaAIAgent.voice.sendVoice(
                {'plugin_event': event, 'Proc': None, 'trace_id': 'dashscope-voice-test'},
                '今晚八点开团。',
                '语速轻快，语调自然上扬。',
            )

        self.assertTrue(result['active'])
        self.assertEqual('wav', result['data']['format'])
        request = post.call_args.kwargs
        self.assertEqual(
            'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation',
            post.call_args.args[0],
        )
        self.assertEqual('Bearer dashscope-key', request['headers']['Authorization'])
        self.assertEqual({
            'model': 'qwen3-tts-instruct-flash',
            'input': {
                'text': '今晚八点开团。',
                'voice': 'Cherry',
                'language_type': 'Chinese',
            },
            'parameters': {
                'instructions': '语速轻快，语调自然上扬。',
                'optimize_instructions': True,
                'stream': False,
            },
        }, request['json'])
        get.assert_called_once_with(
            'https://dashscope-result.example.invalid/generated.wav?Expires=1',
            timeout=120.0,
        )
        self.assertTrue(event.replies[0].data[0].data['file'].endswith('.wav'))

    def test_send_voice_tool_requires_contextual_performance_instructions(self):
        OlivaAIAgent.conf.gConf['voice']['enabled'] = True
        definition = next(
            item for item in OlivaAIAgent.tools.getToolsForRequest({}) if item['name'] == 'send_voice'
        )
        self.assertEqual(['text', 'instructions'], definition['params']['required'])
        instruction_schema = definition['params']['properties']['instructions']
        self.assertIn('当前上下文', instruction_schema['description'])
        self.assertIn('语速', instruction_schema['description'])

    def test_voice_tool_is_hidden_when_disabled(self):
        OlivaAIAgent.conf.gConf['voice']['enabled'] = False
        definitions = OlivaAIAgent.tools.getToolsForRequest({})
        self.assertNotIn('send_voice', [item['name'] for item in definitions])


if __name__ == '__main__':
    unittest.main()
