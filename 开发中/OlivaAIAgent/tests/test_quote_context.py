# -*- encoding: utf-8 -*-

import unittest
from unittest import mock

import OlivaAIAgent


class FakeData:
    def __init__(self, message):
        self.message = message
        self.message_id = 'current-1'
        self.group_id = 'group-1'
        self.user_id = 'user-1'
        self.extend = {'event_id': 'event-1'}


class FakeEvent:
    def __init__(self, message, result=None):
        self.platform = {'sdk': 'qqGuildv2_link', 'platform': 'qqGuild', 'model': 'public'}
        self.plugin_info = {'func_type': 'group_message'}
        self.data = FakeData(message)
        self.base_info = {'self_id': 'bot-1'}
        self.result = result
        self.get_msg_calls = []

    def get_msg(self, message_id):
        self.get_msg_calls.append(str(message_id))
        return self.result


class QuoteContextTest(unittest.TestCase):
    def test_resolves_quote_through_olivos_get_msg(self):
        event = FakeEvent(
            '[CQ:reply,id=quoted-1]这个结论是什么意思？',
            {
                'active': True,
                'data': {
                    'message': '原消息的完整正文',
                    'sender': {'user_id': 'user-2', 'nickname': '青桔'},
                },
            },
        )
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=[]):
            parsed = OlivaAIAgent.msgReply.parseMessage(event)

        self.assertEqual('这个结论是什么意思？', parsed['text'])
        self.assertEqual(['quoted-1'], event.get_msg_calls)
        self.assertEqual('原消息的完整正文', parsed['quote']['text'])
        self.assertEqual('青桔', parsed['quote']['sender_name'])
        self.assertEqual('event-1', parsed['event_id'])
        context = OlivaAIAgent.msgReply.attachQuotedContext(parsed, parsed['text'])
        self.assertIn('【所引用的消息', context)
        self.assertIn('原消息的完整正文', context)
        self.assertIn('【当前消息】\n这个结论是什么意思？', context)

    def test_prefers_persisted_ambient_history(self):
        event = FakeEvent('[CQ:reply,id=quoted-2]继续说说', None)
        history = [{
            'message_id': 'quoted-2',
            'user_id': 'user-3',
            'nickname': '苏米',
            'message': '已写盘的群聊内容',
        }]
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=history):
            parsed = OlivaAIAgent.msgReply.parseMessage(event)

        self.assertEqual([], event.get_msg_calls)
        self.assertEqual('潜行历史', parsed['quote']['source'])
        self.assertEqual('已写盘的群聊内容', parsed['quote']['text'])

    def test_quoted_image_uses_existing_vision_pipeline(self):
        event = FakeEvent(
            '[CQ:reply,id=quoted-image]图里是什么？',
            {
                'active': True,
                'data': {
                    'message': '[OP:image,file=https://example.com/a.png,url=https://example.com/a.png]',
                    'sender': {'id': 'user-4', 'name': '测试用户'},
                },
            },
        )
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=[]):
            parsed = OlivaAIAgent.msgReply.parseMessage(event)
        self.assertEqual(1, parsed['quote']['image_count'])
        self.assertEqual(['https://example.com/a.png'], parsed['quote']['images'])

        with mock.patch.object(OlivaAIAgent.vision, 'getVisionStatus', return_value={'ready': True}), \
                mock.patch.object(OlivaAIAgent.vision, 'describeImages', return_value=['[图片:一只橘猫]']):
            facts = OlivaAIAgent.msgReply.prepareQuotedImages(parsed, 'group-1', 'bot-1', 'trace-1')
        context = OlivaAIAgent.msgReply.attachQuotedContext(parsed, parsed['text'], facts)
        self.assertIn('内容：[图片:一只橘猫]', context)
        self.assertNotIn('引用图片：', context)

    def test_unresolved_quote_does_not_invent_content(self):
        event = FakeEvent('[CQ:reply,id=missing]还记得吗？', {'active': False, 'data': {}})
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=[]):
            parsed = OlivaAIAgent.msgReply.parseMessage(event)
        self.assertIsNone(parsed['quote'])
        self.assertEqual('还记得吗？', OlivaAIAgent.msgReply.attachQuotedContext(parsed, parsed['text']))


if __name__ == '__main__':
    unittest.main()
