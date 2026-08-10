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
        self.sender = {'nickname': '当前用户', 'name': '当前用户'}
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

    def test_nested_forward_accepts_inline_content_nodes(self):
        event = FakeEvent(
            '[OP:forward,id=outer]',
            forward_results={
                'outer': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '外层用户',
                        'content': [{
                            'type': 'forward',
                            'data': {
                                'content': [{
                                    'type': 'node',
                                    'data': {
                                        'nickname': '内层用户',
                                        'content': [{'type': 'text', 'data': {'text': '内层正文'}}],
                                    },
                                }],
                            },
                        }],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertIn('外层用户: [合并转发:\n内层用户: 内层正文\n]', parsed['text'])
        self.assertEqual(2, parsed['forward_count'])
        self.assertNotIn('未能读取', parsed['text'])

    def test_chat_record_marker_with_inline_nodes_is_expanded(self):
        event = FakeEvent(
            '[OP:forward,id=outer]',
            forward_results={
                'outer': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '用户',
                        'content': [{'type': 'text', 'data': {'text': '[聊天记录]'}}],
                        'msg_elements': [{
                            'author': {'username': '内层甲'},
                            'content': '第一条',
                        }, {
                            'author': {'username': '内层乙'},
                            'content': '第二条',
                        }],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertIn('内层甲: 第一条', parsed['text'])
        self.assertIn('内层乙: 第二条', parsed['text'])
        self.assertNotIn('[聊天记录]', parsed['text'])
        self.assertNotIn('未能读取', parsed['text'])

    def test_flattened_chat_record_marker_is_not_kept_as_message(self):
        event = FakeEvent(
            '[OP:forward,id=outer]',
            forward_results={
                'outer': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '用户',
                        'content': [{'type': 'text', 'data': {'text': '[聊天记录]'}}],
                    },
                }, {
                    'type': 'node',
                    'data': {
                        'nickname': '内层甲',
                        'content': [{'type': 'text', 'data': {'text': '第一条'}}],
                    },
                }, {
                    'type': 'node',
                    'data': {
                        'nickname': '内层乙',
                        'content': [{'type': 'text', 'data': {'text': '第二条'}}],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertIn('内层甲: 第一条\n内层乙: 第二条', parsed['text'])
        self.assertNotIn('[聊天记录]', parsed['text'])

    def test_duplicate_sender_metadata_is_not_kept_as_message(self):
        event = FakeEvent(
            '[OP:forward,id=outer]',
            forward_results={
                'outer': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '番茄酱香饼',
                        'content': [{
                            'type': 'text',
                            'data': {'text': '[发送者] 番茄酱香饼'},
                        }],
                    },
                }, {
                    'type': 'node',
                    'data': {
                        'nickname': 'Letoic',
                        'content': [{'type': 'text', 'data': {'text': '实际正文'}}],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertIn('Letoic: 实际正文', parsed['text'])
        self.assertNotIn('[发送者]', parsed['text'])

    def test_unresolved_chat_record_marker_is_reported_as_incomplete(self):
        event = FakeEvent(
            '[OP:forward,id=outer]',
            forward_results={
                'outer': forward_result([{
                    'type': 'node',
                    'data': {
                        'id': 'missing-inner',
                        'nickname': '用户',
                        'content': [{'type': 'text', 'data': {'text': '[聊天记录]'}}],
                    },
                }]),
            },
        )

        parsed = self.parse(event)

        self.assertIn('[嵌套合并转发:未能读取]', parsed['text'])
        self.assertNotIn('用户: [聊天记录]', parsed['text'])

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

    def test_ambient_history_and_current_ai_turn_keep_expanded_forward(self):
        event = FakeEvent(
            '[OP:forward,id=context-forward]',
            forward_results={
                'context-forward': forward_result([
                    {
                        'type': 'node',
                        'data': {
                            'nickname': '甲',
                            'content': [{'type': 'text', 'data': {'text': '第一段'}}],
                        },
                    },
                    {
                        'type': 'node',
                        'data': {
                            'nickname': '乙',
                            'content': [{'type': 'text', 'data': {'text': '第二段'}}],
                        },
                    },
                ]),
            },
        )
        parsed = self.parse(event)

        class ImmediateThread:
            def __init__(self, target, **_kwargs):
                self.target = target

            def start(self):
                self.target()

        class ImmediateLock:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with mock.patch.object(OlivaAIAgent.ambient, 'addToHistory') as add_history, \
                mock.patch.object(OlivaAIAgent.ambient, 'getGroupLock', return_value=ImmediateLock()), \
                mock.patch.object(OlivaAIAgent.ambient, '_reply') as reply, \
                mock.patch.object(OlivaAIAgent.ambient.threading, 'Thread', ImmediateThread):
            OlivaAIAgent.ambient.process(
                event,
                None,
                parsed,
                'bot-1',
                force=True,
                attempt=True,
                _vision_worker=True,
            )

        stored_text = add_history.call_args.args[5]
        current_ai_text = reply.call_args.args[8]
        self.assertEqual(stored_text, current_ai_text)
        self.assertIn('甲: 第一段\n乙: 第二段', stored_text)
        self.assertNotIn('[OP:forward', stored_text)

    def test_forward_image_facts_are_placed_into_expanded_nodes(self):
        OlivaAIAgent.conf.gConf['forward']['image'] = True
        event = FakeEvent(
            '[OP:forward,id=image-forward]',
            forward_results={
                'image-forward': forward_result([{
                    'type': 'node',
                    'data': {
                        'nickname': '图片用户',
                        'content': [{
                            'type': 'image',
                            'data': {'url': 'https://example.invalid/forward.jpg'},
                        }],
                    },
                }]),
            },
        )
        parsed = self.parse(event)
        fact = '[图片:一张展开后的合并转发图片]'
        with mock.patch.object(OlivaAIAgent.ambient, 'addToHistory') as add_history, \
                mock.patch.object(
                    OlivaAIAgent.vision,
                    'translateIncoming',
                    return_value='[OP:forward,id=image-forward]',
                ), \
                mock.patch.object(OlivaAIAgent.vision, 'ensureImageFacts', return_value=[fact]):
            OlivaAIAgent.ambient.process(
                event,
                None,
                parsed,
                'bot-1',
                attempt=False,
                _vision_worker=True,
            )

        stored_text = add_history.call_args.args[5]
        self.assertIn('图片用户: %s' % fact, stored_text)
        self.assertNotIn('[[OLIVA_IMAGE_', stored_text)
        self.assertNotIn('[OP:forward', stored_text)

    def test_failed_forward_keeps_readable_failure_in_ambient_history(self):
        event = FakeEvent('[OP:forward,id=missing-forward]')
        parsed = self.parse(event)
        with mock.patch.object(OlivaAIAgent.ambient, 'addToHistory') as add_history:
            OlivaAIAgent.ambient.process(
                event,
                None,
                parsed,
                'bot-1',
                attempt=False,
                _vision_worker=True,
            )

        stored_text = add_history.call_args.args[5]
        self.assertEqual('[合并转发:未能读取]', stored_text)
        self.assertNotIn('[OP:forward', stored_text)


if __name__ == '__main__':
    unittest.main()
