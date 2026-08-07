# -*- encoding: utf-8 -*-

import copy
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import OlivaAIAgent


class FakeData:
    def __init__(self, message):
        self.message = message
        self.message_id = 'current-message'
        self.group_id = 'group-1'
        self.user_id = 'user-1'
        self.extend = {}


class FakeEvent:
    def __init__(self, message, get_msg_result=None, forward_results=None):
        self.platform = {'sdk': 'qqGuildv2_link', 'platform': 'qqGuild', 'model': 'public'}
        self.plugin_info = {'func_type': 'group_message'}
        self.data = FakeData(message)
        self.base_info = {'self_id': 'bot-1'}
        self.bot_info = SimpleNamespace(hash='bot-hash')
        self.get_msg_result = get_msg_result
        self.forward_results = forward_results or {}
        self.get_msg_calls = []
        self.get_forward_msg_calls = []

    def get_msg(self, message_id):
        self.get_msg_calls.append(str(message_id))
        return self.get_msg_result

    def get_forward_msg(self, message_id):
        self.get_forward_msg_calls.append(str(message_id))
        return self.forward_results.get(str(message_id), {'active': False, 'data': {'messages': []}})


def forward_result(messages):
    return {'active': True, 'data': {'messages': messages}}


class ForwardMessageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.identifiers._initialized_path = None

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.identifiers._initialized_path = None
        self.temp_dir.cleanup()

    def parse(self, event):
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=[]):
            return OlivaAIAgent.msgReply.parseMessage(event)

    def test_reads_onebot_qqguild_and_milky_node_shapes(self):
        event = FakeEvent(
            '[OP:forward,id=outer-forward]',
            forward_results={
                'outer-forward': forward_result([
                    {
                        'sender': {'user_id': '10001', 'nickname': 'OneBot用户'},
                        'content': [{'type': 'text', 'data': {'text': 'OneBot正文'}}],
                    },
                    {
                        'type': 'node',
                        'data': {
                            'user_id': 'openid-2',
                            'nickname': 'QQ官方用户',
                            'content': [{'type': 'text', 'data': {'text': 'QQ正文'}}],
                        },
                    },
                    {
                        'sender_name': 'Milky用户',
                        'segments': [{'type': 'text', 'data': {'text': 'Milky正文'}}],
                    },
                ]),
            },
        )

        parsed = self.parse(event)

        self.assertEqual(['outer-forward'], event.get_forward_msg_calls)
        self.assertIn('[合并转发:', parsed['text'])
        self.assertIn('OneBot用户: OneBot正文', parsed['text'])
        self.assertIn('QQ官方用户: QQ正文', parsed['text'])
        self.assertIn('Milky用户: Milky正文', parsed['text'])
        self.assertEqual(1, parsed['forward_count'])
        self.assertEqual(3, parsed['forward_nodes'])

    def test_forward_media_is_cleaned_by_default(self):
        secret = 'https://multimedia.nt.qq.com.cn/resource?rkey=secret'
        event = FakeEvent(
            '[OP:forward,id=media-forward]',
            forward_results={
                'media-forward': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '媒体用户',
                        'content': [
                            {'type': 'image', 'data': {'url': secret + '-image'}},
                            {'type': 'record', 'data': {'url': secret + '-audio'}},
                            {'type': 'video', 'data': {'url': secret + '-video'}},
                        ],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertIn('媒体用户: [图片][语音][视频]', parsed['text'])
        self.assertNotIn('multimedia.nt.qq.com.cn', parsed['text'])
        self.assertEqual([], parsed['images'])
        self.assertEqual([], parsed['audio_urls'])
        self.assertEqual([], parsed['video_urls'])
        self.assertEqual(1, parsed['image_count'])
        self.assertEqual(1, parsed['audio_count'])
        self.assertEqual(1, parsed['video_count'])

    def test_enabled_forward_media_reuses_normal_placeholders(self):
        OlivaAIAgent.conf.gConf['forward'].update({'image': True, 'audio': True, 'video': True})
        refs = {
            'image': 'https://example.invalid/picture.jpg',
            'audio': 'https://example.invalid/voice.mp3',
            'video': 'https://example.invalid/movie.mp4',
        }
        event = FakeEvent(
            '[OP:forward,id=media-forward]',
            forward_results={
                'media-forward': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '媒体用户',
                        'content': [
                            {'type': 'image', 'data': {'url': refs['image']}},
                            {'type': 'record', 'data': {'url': refs['audio']}},
                            {'type': 'video', 'data': {'url': refs['video']}},
                        ],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertEqual([refs['image']], parsed['images'])
        self.assertEqual([refs['audio']], parsed['audio_urls'])
        self.assertEqual([refs['video']], parsed['video_urls'])
        self.assertIn(OlivaAIAgent.vision.imagePlaceholder(0), parsed['text'])
        self.assertIn(OlivaAIAgent.media.audioPlaceholder(0), parsed['text'])
        self.assertIn(OlivaAIAgent.media.videoPlaceholder(0), parsed['text'])
        self.assertNotIn('example.invalid', parsed['text'])

    def test_forward_mp4_file_is_treated_as_video(self):
        OlivaAIAgent.conf.gConf['forward']['video'] = True
        ref = 'https://example.invalid/download?fname=forward-clip.mp4'
        event = FakeEvent(
            '[OP:forward,id=file-forward]',
            forward_results={
                'file-forward': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '文件用户',
                        'content': [{
                            'type': 'file',
                            'data': {'url': ref, 'name': 'forward-clip.mp4', 'size': 1024},
                        }],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertEqual([ref], parsed['video_urls'])
        self.assertEqual(1, parsed['video_count'])
        self.assertIn(OlivaAIAgent.media.videoPlaceholder(0), parsed['text'])

    def test_quote_reads_outer_message_then_expands_forward(self):
        event = FakeEvent(
            '[OP:reply,id=outer-message]这里说了什么？',
            get_msg_result={
                'active': True,
                'data': {
                    'message': '[OP:forward,id=outer-message]',
                    'raw_message': 'QQ原始展开文本',
                    'sender': {'user_id': 'user-2', 'nickname': '转发者'},
                },
            },
            forward_results={
                'outer-message': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '节点用户',
                        'content': [{'type': 'text', 'data': {'text': '真正的转发正文'}}],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertEqual(['outer-message'], event.get_msg_calls)
        self.assertEqual(['outer-message'], event.get_forward_msg_calls)
        self.assertIn('节点用户: 真正的转发正文', parsed['quote']['text'])
        context = OlivaAIAgent.msgReply.attachQuotedContext(parsed, parsed['text'])
        self.assertTrue(context.startswith('[引用上文:[合并转发:'))
        self.assertTrue(context.endswith('] 这里说了什么？'))

    def test_nested_forward_is_expanded_and_cycle_is_bounded(self):
        event = FakeEvent(
            '[OP:forward,id=outer]',
            forward_results={
                'outer': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '外层',
                        'content': [{'type': 'forward', 'data': {'id': 'inner'}}],
                    },
                }]),
                'inner': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '内层',
                        'content': [
                            {'type': 'text', 'data': {'text': '嵌套正文'}},
                            {'type': 'forward', 'data': {'id': 'outer'}},
                        ],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertEqual(['outer', 'inner'], event.get_forward_msg_calls)
        self.assertIn('内层: 嵌套正文[合并转发:循环引用]', parsed['text'])
        self.assertEqual(3, parsed['forward_count'])
        self.assertEqual(1, parsed['forward_failed'])

    def test_quote_falls_back_to_raw_message_when_forward_fetch_fails(self):
        event = FakeEvent(
            '[OP:reply,id=missing-forward]继续',
            get_msg_result={
                'active': True,
                'data': {
                    'message': '[OP:forward,id=missing-forward]',
                    'raw_message': '平台保留的原始展开文本',
                    'sender': {'user_id': 'user-2', 'nickname': '转发者'},
                },
            },
        )

        parsed = self.parse(event)

        self.assertEqual(['missing-forward'], event.get_forward_msg_calls)
        self.assertEqual('平台保留的原始展开文本', parsed['quote']['text'])
        self.assertEqual('OlivOS消息接口(raw_message兜底)', parsed['quote']['source'])

    def test_raw_message_fallback_still_cleans_forward_media(self):
        secret = 'https://multimedia.nt.qq.com.cn/resource?rkey=secret'
        event = FakeEvent(
            '[OP:reply,id=missing-forward]继续',
            get_msg_result={
                'active': True,
                'data': {
                    'message': '[OP:forward,id=missing-forward]',
                    'raw_message': (
                        '原始节点'
                        '[OP:image,file=%s,url=%s]'
                        '[OP:record,file=%s,url=%s]'
                        '[OP:video,file=%s,url=%s]'
                    ) % ((secret,) * 6),
                    'sender': {'user_id': 'user-2', 'nickname': '转发者'},
                },
            },
        )

        parsed = self.parse(event)

        self.assertEqual('原始节点 [图片] [语音] [视频]', parsed['quote']['text'])
        self.assertEqual([], parsed['quote']['images'])
        self.assertEqual([], parsed['quote']['audio_urls'])
        self.assertEqual([], parsed['quote']['video_urls'])
        self.assertNotIn('rkey=secret', parsed['quote']['text'])

    def test_expanded_forward_is_persisted_and_reused_for_later_quote(self):
        long_text = '本地保存的转发正文' * 700
        source_event = FakeEvent(
            '[OP:forward,id=stored-forward]',
            forward_results={
                'stored-forward': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '存档用户',
                        'content': [{'type': 'text', 'data': {'text': long_text}}],
                    },
                }]),
            },
        )
        source_event.data.message_id = 'stored-forward'
        source = self.parse(source_event)
        self.assertGreater(len(source['text']), 4096)
        OlivaAIAgent.identifiers.recordIncoming(source_event, source)

        OlivaAIAgent.identifiers._initialized_path = None
        quoted_event = FakeEvent('[OP:reply,id=stored-forward]继续')
        quoted = self.parse(quoted_event)

        self.assertEqual('插件消息注册表', quoted['quote']['source'])
        self.assertEqual(source['text'], quoted['quote']['text'])
        self.assertEqual([], quoted_event.get_msg_calls)
        self.assertEqual([], quoted_event.get_forward_msg_calls)


if __name__ == '__main__':
    unittest.main()
