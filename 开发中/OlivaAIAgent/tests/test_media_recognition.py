# -*- encoding: utf-8 -*-

import base64
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
        return {
            'choices': [{
                'message': {'content': json.dumps({'text': '今天晚上八点开团'}, ensure_ascii=False)},
            }],
        }


class DashscopeAudioResponse:
    status_code = 200
    text = ''

    def json(self):
        return {
            'output': {
                'output': {'sentence': {'text': '百炼原生接口转写成功'}},
                'text': '百炼原生接口转写成功',
            },
            'request_id': 'dashscope-request',
        }


class FakeData:
    message = ''
    message_id = 'message-1'
    user_id = 'user-1'
    group_id = 'group-1'
    extend = {}
    sender = {'name': '测试用户'}


class FakeBotInfo:
    hash = 'bot-hash'


class FakeEvent:
    data = FakeData()
    bot_info = FakeBotInfo()
    base_info = {'self_id': 'bot-1'}
    platform = {'platform': 'qqGuild', 'sdk': 'qqGuildv2_link', 'model': 'public'}
    plugin_info = {'func_type': 'group_message'}


class MediaRecognitionTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = copy.deepcopy(OlivaAIAgent.conf.gConf)
        self.old_proc = OlivaAIAgent.conf.gProc
        self.proc = FakeProc()
        OlivaAIAgent.conf.gProc = self.proc
        OlivaAIAgent.media._result_cache.clear()
        OlivaAIAgent.conf.gConf = {
            'backend': 'openai',
            'openai': {
                'wire': 'openai',
                'api_url': 'https://api.example.invalid/v1/chat/completions',
                'api_key': 'main-secret',
                'model': 'text-model',
                'vision': False,
                'audio': False,
                'video': False,
            },
            'media': {
                'enable': True,
                'use_main': 'auto',
                'max_bytes': 1024 * 1024,
                'audio': {
                    'enable': True,
                    'api_url': 'https://dashscope.example.invalid/v1/chat/completions',
                    'api_key': 'media-secret',
                    'model': 'qwen3-asr-flash',
                    'mode': 'base64',
                    'timeout_sec': 120,
                    'max_tokens': 1200,
                },
                'video': {
                    'enable': True,
                    'api_url': 'https://dashscope.example.invalid/v1/chat/completions',
                    'api_key': 'media-secret',
                    'model': 'qwen-vl-max',
                    'mode': 'url',
                    'timeout_sec': 120,
                    'max_tokens': 1200,
                },
            },
            'debug_log': True,
        }

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.conf.gProc = self.old_proc
        OlivaAIAgent.media._result_cache.clear()

    def test_parse_op_record_and_video(self):
        event = FakeEvent()
        event.data = FakeData()
        event.data.message = (
            '听这个'
            '[OP:record,file=https://multimedia.nt.qq.com.cn/audio?rkey=secret,'
            'url=https://multimedia.nt.qq.com.cn/audio?rkey=secret]'
            '[OP:video,file=https://multimedia.nt.qq.com.cn/video?rkey=secret,'
            'url=https://multimedia.nt.qq.com.cn/video?rkey=secret]'
        )
        parsed = OlivaAIAgent.msgReply.parseMessage(event)
        self.assertEqual(['https://multimedia.nt.qq.com.cn/audio?rkey=secret'], parsed['audio_urls'])
        self.assertEqual(['https://multimedia.nt.qq.com.cn/video?rkey=secret'], parsed['video_urls'])
        self.assertIn(OlivaAIAgent.media.audioPlaceholder(0), parsed['text'])
        self.assertIn(OlivaAIAgent.media.videoPlaceholder(0), parsed['text'])
        self.assertNotIn('rkey=secret', parsed['text'])

    def test_mp4_file_message_is_parsed_as_video(self):
        event = FakeEvent()
        event.data = FakeData()
        url = 'https://njc-download.ftn.qq.com/ftn_handler/token?fname=clip.mp4'
        event.data.message = '[OP:file,file=%s,url=%s,name=clip.mp4,size=11369930]' % (url, url)

        parsed = OlivaAIAgent.msgReply.parseMessage(event)

        self.assertEqual([url], parsed['video_urls'])
        self.assertEqual(1, parsed['video_count'])
        self.assertEqual(OlivaAIAgent.media.videoPlaceholder(0), parsed['text'])

    def test_non_video_file_is_not_added_to_video_inputs(self):
        event = FakeEvent()
        event.data = FakeData()
        event.data.message = (
            '[OP:file,file=https://example.invalid/report.pdf,'
            'url=https://example.invalid/report.pdf,name=report.pdf,size=100]'
        )

        parsed = OlivaAIAgent.msgReply.parseMessage(event)

        self.assertEqual([], parsed['video_urls'])
        self.assertEqual(0, parsed['video_count'])

    def test_independent_route_replaces_media_with_facts(self):
        parsed = {
            'audio_urls': ['https://example.invalid/audio.mp3?rkey=secret'],
            'video_urls': ['https://example.invalid/video.mp4?rkey=secret'],
        }
        with mock.patch.object(
            OlivaAIAgent.media,
            '_recognize',
            side_effect=['[语音:今天八点开团]', '[视频:两个人在桌边掷骰子]'],
        ):
            result = OlivaAIAgent.media.translateIncoming(
                '听听[[OLIVA_AUDIO_0]][[OLIVA_VIDEO_0]]',
                parsed,
                trace_id='media-independent',
            )
        self.assertEqual('听听[语音:今天八点开团][视频:两个人在桌边掷骰子]', result)
        self.assertEqual([], parsed['audio_urls'])
        self.assertEqual([], parsed['video_urls'])
        self.assertNotIn('example.invalid', result)

    def test_audio_and_video_switches_are_independent(self):
        OlivaAIAgent.conf.gConf['media']['video']['enable'] = False
        parsed = {
            'audio_urls': ['https://example.invalid/audio.mp3'],
            'video_urls': ['https://example.invalid/video.mp4'],
        }
        with mock.patch.object(
            OlivaAIAgent.media,
            '_recognize',
            return_value='[语音:今晚八点开团]',
        ) as recognize:
            result = OlivaAIAgent.media.translateIncoming(
                '听听[[OLIVA_AUDIO_0]][[OLIVA_VIDEO_0]]',
                parsed,
                trace_id='split-switches',
            )

        self.assertEqual('听听[语音:今晚八点开团][视频]', result)
        recognize.assert_called_once_with(
            'audio',
            'https://example.invalid/audio.mp3',
            trace_id='split-switches',
        )
        self.assertEqual([], parsed['audio_urls'])
        self.assertEqual([], parsed['video_urls'])

    def test_deprecated_global_media_switch_is_ignored(self):
        OlivaAIAgent.conf.gConf['media']['enable'] = True
        OlivaAIAgent.conf.gConf['media']['audio']['enable'] = False
        OlivaAIAgent.conf.gConf['media']['video']['enable'] = False

        status = OlivaAIAgent.media.getStatus()

        self.assertFalse(status['enabled'])
        self.assertFalse(status['audio']['enabled'])
        self.assertFalse(status['video']['enabled'])

    def test_main_route_keeps_inputs_and_uses_openai_media_parts(self):
        OlivaAIAgent.conf.gConf['openai']['audio'] = True
        OlivaAIAgent.conf.gConf['openai']['video'] = True
        audio_data = base64.b64encode(b'voice-bytes').decode('ascii')
        messages = [{
            'role': 'user',
            'content': '识别这个',
            'audios': ['data:audio/mpeg;base64,' + audio_data],
            'videos': ['https://example.invalid/video.mp4'],
        }]
        result = OlivaAIAgent.aiClient._to_openai_messages(messages, False, True, True)
        content = result[0]['content']
        self.assertEqual('input_audio', content[1]['type'])
        self.assertEqual(audio_data, content[1]['input_audio']['data'])
        self.assertEqual('mp3', content[1]['input_audio']['format'])
        self.assertEqual('video_url', content[2]['type'])

    def test_main_full_modal_route_remains_available(self):
        OlivaAIAgent.conf.gConf['openai']['audio'] = True
        OlivaAIAgent.conf.gConf['openai']['video'] = True
        self.assertEqual('main', OlivaAIAgent.media._route('audio'))
        self.assertEqual('main', OlivaAIAgent.media._route('video'))

    def test_independent_audio_request_and_logs_are_redacted(self):
        ref = 'data:audio/mpeg;base64,' + base64.b64encode(b'voice-bytes').decode('ascii')
        cfg = OlivaAIAgent.media._independentConf('audio')
        with mock.patch.object(OlivaAIAgent.media.requests, 'post', return_value=FakeResponse()) as post:
            result = OlivaAIAgent.media._callIndependent('audio', ref, cfg, 'media-log')
        self.assertEqual('今天晚上八点开团', result)
        request = post.call_args.kwargs['json']
        media_part = request['messages'][1]['content'][1]
        self.assertEqual('input_audio', media_part['type'])
        self.assertEqual('mp3', media_part['input_audio']['format'])
        logs = '\n'.join(item[1] for item in self.proc.records)
        self.assertIn('语音识别请求', logs)
        self.assertIn('语音识别结果', logs)
        self.assertNotIn('voice-bytes', logs)
        self.assertNotIn('media-secret', logs)
        self.assertNotIn('data:audio', logs)

    def test_qwen_audio_dashscope_native_request(self):
        audio_data = base64.b64encode(b'voice-bytes').decode('ascii')
        ref = 'data:audio/mpeg;base64,' + audio_data
        cfg = OlivaAIAgent.media._independentConf('audio')
        cfg.update({
            'api_url': 'https://workspace.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/'
            'multimodal-generation/generation',
            'api_key': 'media-secret',
            'model': 'qwen-audio-3.0-asr-flash',
            'provider': 'auto',
            'format': '',
            'prompt': '请转写这段语音',
        })
        with mock.patch.object(
            OlivaAIAgent.media.requests,
            'post',
            return_value=DashscopeAudioResponse(),
        ) as post:
            result = OlivaAIAgent.media._callIndependent('audio', ref, cfg, 'dashscope-media')
        self.assertEqual('百炼原生接口转写成功', result)
        request = post.call_args.kwargs
        self.assertTrue(post.call_args.args[0].endswith('/multimodal-generation/generation'))
        self.assertEqual('disable', request['headers']['X-DashScope-SSE'])
        payload = request['json']
        self.assertEqual('qwen-audio-3.0-asr-flash', payload['model'])
        self.assertNotIn('response_format', payload)
        self.assertEqual('input_text', payload['input']['messages'][0]['content'][0]['type'])
        media_part = payload['input']['messages'][0]['content'][-1]
        self.assertEqual('input_audio', media_part['type'])
        self.assertEqual(ref, media_part['input_audio']['data'])
        self.assertEqual('mp3', payload['parameters']['format'])
        logs = '\n'.join(item[1] for item in self.proc.records)
        self.assertNotIn(audio_data, logs)

    def test_audio_provider_auto_keeps_openai_and_detects_dashscope(self):
        self.assertEqual('openai_compatible', OlivaAIAgent.media._audioProvider({
            'model': 'qwen3-asr-flash',
            'api_url': 'https://dashscope.example.invalid/compatible-mode/v1/chat/completions',
        }))
        self.assertEqual('dashscope_asr', OlivaAIAgent.media._audioProvider({
            'model': 'qwen-audio-3.0-asr-flash',
            'api_url': 'https://dashscope.example.invalid/compatible-mode/v1/chat/completions',
        }))
        self.assertEqual(
            'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation',
            OlivaAIAgent.media._dashscopeAudioUrl({
                'api_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
            }),
        )

    def test_qwen_audio_maps_ogg_mime_to_opus(self):
        self.assertEqual('opus', OlivaAIAgent.media._formatFromMime('audio/ogg', 'voice'))
        self.assertEqual('opus', OlivaAIAgent.media._formatFromMime('audio/opus', 'voice'))

    def test_quote_media_fact_is_same_priority_as_current_text(self):
        parsed = {
            'quote': {
                'text': '之前发的内容',
                'audio_count': 1,
                'video_count': 0,
            },
        }
        result = OlivaAIAgent.msgReply.attachQuotedContext(
            parsed,
            '这是什么意思',
            media_facts=['[语音:今晚八点开团]'],
        )
        self.assertEqual('[引用上文:之前发的内容 [语音:今晚八点开团]] 这是什么意思', result)


if __name__ == '__main__':
    unittest.main()
