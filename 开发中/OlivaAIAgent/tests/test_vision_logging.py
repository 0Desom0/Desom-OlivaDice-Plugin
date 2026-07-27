# -*- encoding: utf-8 -*-

import copy
import json
import unittest
from unittest import mock

import OlivaAIAgent


class FakeProc:
    def __init__(self):
        self.records = []

    def log(self, level, message, segments=None):
        self.records.append((level, message, segments))


class FakeResponse:
    status_code = 200
    text = ''

    def json(self):
        content = json.dumps(
            {'content': '一只白色狐狸站在雪地里', 'intent': '展示图片', 'type': '插画'},
            ensure_ascii=False,
        )
        return {'choices': [{'message': {'content': content}}]}


class FakeErrorResponse:
    status_code = 400
    text = '{"error":"unsupported image format"}'


class FakeBotInfo:
    hash = 'bot-hash'


class FakeData:
    group_id = 'group-1'
    user_id = 'user-1'


class FakeEvent:
    platform = {'platform': 'qqGuild', 'sdk': 'qqGuildv2_link', 'model': 'public'}
    data = FakeData()
    bot_info = FakeBotInfo()


class VisionLoggingTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = copy.deepcopy(OlivaAIAgent.conf.gConf)
        self.old_proc = OlivaAIAgent.conf.gProc
        self.proc = FakeProc()
        OlivaAIAgent.conf.gProc = self.proc
        OlivaAIAgent.conf.gConf = {
            'backend': 'openai',
            'openai': {'vision': False, 'api_url': 'https://api.deepseek.com/v1/chat/completions'},
            'vision': {
                'enable': True,
                'use_main': 'auto',
                'api_url': 'https://api.moonshot.cn/v1/chat/completions',
                'api_key': 'secret-key',
                'model': 'kimi-k2.6',
                'mode': 'base64',
            },
            'debug_log': True,
        }

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.conf.gProc = self.old_proc

    def test_config_routes_to_independent_vision(self):
        status = OlivaAIAgent.vision.getVisionStatus()
        self.assertTrue(status['enabled'])
        self.assertTrue(status['ready'])
        self.assertEqual('independent', status['route'])
        self.assertEqual('kimi-k2.6', status['model'])
        self.assertEqual('base64', status['mode'])

    def test_ocr_success_is_logged_without_image_data(self):
        vc = OlivaAIAgent.vision._visionConf()
        with mock.patch.object(OlivaAIAgent.vision.requests, 'post', return_value=FakeResponse()):
            result = OlivaAIAgent.vision._callOcr(
                vc,
                'data:image/jpeg;base64,VERY_LONG_IMAGE_DATA',
                trace_id='trace-1',
            )
        self.assertEqual('一只白色狐狸站在雪地里', result['content'])
        logs = '\n'.join(record[1] for record in self.proc.records)
        self.assertIn('图片识别请求', logs)
        self.assertIn('图片识别成功', logs)
        self.assertNotIn('VERY_LONG_IMAGE_DATA', logs)
        self.assertNotIn('secret-key', logs)

    def test_ocr_http_error_is_logged(self):
        vc = OlivaAIAgent.vision._visionConf()
        with mock.patch.object(OlivaAIAgent.vision.requests, 'post', return_value=FakeErrorResponse()):
            result = OlivaAIAgent.vision._callOcr(
                vc,
                'data:image/jpeg;base64,ERROR_IMAGE_DATA',
                trace_id='trace-http-error',
            )
        self.assertIsNone(result)
        logs = '\n'.join(record[1] for record in self.proc.records)
        self.assertIn('图片识别接口错误', logs)
        self.assertIn('状态码=400', logs)
        self.assertIn('unsupported image format', logs)
        self.assertNotIn('ERROR_IMAGE_DATA', logs)
        self.assertNotIn('secret-key', logs)

    def test_private_agent_uses_vision_summary_not_main_image(self):
        ctx = {
            'Proc': self.proc,
            'func_type': 'private_message',
            'group_id': None,
            'user_id': 'user-1',
        }
        parsed = {
            'trace_id': 'trace-2',
            'raw': '[CQ:image,file=test.jpg,url=https://example.invalid/test.jpg]',
            'images': ['https://example.invalid/test.jpg'],
        }
        with mock.patch.object(
            OlivaAIAgent.vision,
            'translateIncoming',
            return_value='[图片：一只白色狐狸；意图：展示图片；类型：插画]',
        ):
            text, images = OlivaAIAgent.msgReply._prepareAgentVision(
                FakeEvent(),
                ctx,
                '这是什么？',
                parsed,
            )
        self.assertIn('一只白色狐狸', text)
        self.assertEqual([], images)

    def test_sync_ocr_false_defers_group_vision_to_worker(self):
        parsed = {
            'trace_id': 'trace-3',
            'raw': '[CQ:image,file=test.jpg,url=https://example.invalid/test.jpg]',
            'images': ['https://example.invalid/test.jpg'],
            'text': '',
        }
        thread = mock.Mock()
        with mock.patch.object(OlivaAIAgent.ambient.threading, 'Thread', return_value=thread) as thread_factory:
            OlivaAIAgent.ambient.process(FakeEvent(), self.proc, parsed, 'bot-1', force=True, tools=True)
        thread_factory.assert_called_once()
        self.assertEqual('OlivaAIAgent-Vision', thread_factory.call_args.kwargs['name'])
        thread.start.assert_called_once()

    def test_trace_log_redacts_sensitive_fields(self):
        OlivaAIAgent.conf.traceLog(
            self.proc,
            'test.stage',
            'trace-4',
            api_key='top-secret',
            image='data:image/png;base64,IMAGE_SECRET',
        )
        message = self.proc.records[-1][1]
        self.assertIn('api_key=<已隐藏>', message)
        self.assertIn('<图片数据:', message)
        self.assertNotIn('top-secret', message)
        self.assertNotIn('IMAGE_SECRET', message)


if __name__ == '__main__':
    unittest.main()
