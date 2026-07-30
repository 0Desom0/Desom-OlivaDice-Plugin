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
        self.bot_info = SimpleNamespace(hash='bot-hash')
        self.result = result
        self.get_msg_calls = []
        self.blocked = False
        self.replies = []

    def get_msg(self, message_id):
        self.get_msg_calls.append(str(message_id))
        return self.result

    def set_block(self):
        self.blocked = True

    def reply(self, message):
        self.replies.append(message)


class QuoteContextTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        self.old_groups = OlivaAIAgent.conf.gGroups
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.conf.gGroups = {}
        OlivaAIAgent.identifiers._initialized_path = None

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.conf.gGroups = self.old_groups
        OlivaAIAgent.identifiers._initialized_path = None
        self.temp_dir.cleanup()

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
        self.assertFalse(parsed['reply_to_me'])

    def test_reply_to_bot_is_detected_from_outgoing_registry(self):
        source_event = FakeEvent('机器人上一条回复')
        OlivaAIAgent.identifiers.recordOutgoing(source_event, '机器人上一条回复', ['bot-message-1'])
        event = FakeEvent('[CQ:reply,id=bot-message-1]继续说说')
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=[]):
            parsed = OlivaAIAgent.msgReply.parseMessage(event)

        self.assertTrue(parsed['reply_to_me'])
        self.assertTrue(parsed['quote']['from_self'])
        self.assertEqual('机器人上一条回复', parsed['quote']['text'])

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

    def test_qqguildv2_group_at_event_is_treated_as_at_bot_without_segment(self):
        event = FakeEvent('机器人在吗')
        event.data.extend['qq_event_type'] = 'GROUP_AT_MESSAGE_CREATE'
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=[]):
            parsed = OlivaAIAgent.msgReply.parseMessage(event)
        self.assertTrue(parsed['at_me'])

    def test_group_quote_log_only_runs_when_group_is_usable(self):
        for group_usable in [False, True]:
            with self.subTest(group_usable=group_usable):
                event = FakeEvent(
                    '[CQ:reply,id=quoted-log]继续说说',
                    {
                        'active': True,
                        'data': {
                            'message': '引用正文',
                            'sender': {'user_id': 'user-2', 'nickname': '青桔'},
                        },
                    },
                )
                with mock.patch.object(OlivaAIAgent.identifiers, 'recordIncoming'), \
                        mock.patch.object(OlivaAIAgent.msgReply, '_logQuotedMessage') as quote_log, \
                        mock.patch.object(OlivaAIAgent.reminder, 'registerSender'), \
                        mock.patch.object(OlivaAIAgent.msgReply, '_seenMessage', return_value=False), \
                        mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=False), \
                        mock.patch.object(
                            OlivaAIAgent.msgReply,
                            '_checkGroupUsable',
                            return_value=group_usable,
                        ), \
                        mock.patch.object(OlivaAIAgent.conf, 'isAmbientEnabled', return_value=False), \
                        mock.patch.object(OlivaAIAgent.conf, 'isGroupHistoryMemory', return_value=False), \
                        mock.patch.object(OlivaAIAgent.conf, 'isGroupLongMemory', return_value=False):
                    OlivaAIAgent.msgReply._onGroupMessage(event, None)

                self.assertEqual(group_usable, quote_log.called)

    def test_qqguildv2_sub_self_open_id_is_treated_as_bot_mention(self):
        event = FakeEvent('[CQ:at,qq=bot-member-openid] 机器人在吗')
        event.data.extend['sub_self_open_id'] = 'bot-member-openid'
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=[]):
            parsed = OlivaAIAgent.msgReply.parseMessage(event)
        self.assertTrue(parsed['at_me'])
        self.assertIn('bot-member-openid', parsed['at_list'])

    def test_op_segments_are_parsed_for_mention_reply_and_image(self):
        event = FakeEvent(
            '[OP:at,id=bot-member-openid][OP:reply,id=quoted-op]'
            '[OP:image,file=https://example.com/op.png]看这张图',
            {
                'active': True,
                'data': {
                    'message': '被引用的消息',
                    'sender': {'id': 'user-2', 'name': '测试用户'},
                },
            },
        )
        event.data.extend['sub_self_open_id'] = 'bot-member-openid'
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=[]):
            parsed = OlivaAIAgent.msgReply.parseMessage(event)

        self.assertTrue(parsed['at_me'])
        self.assertEqual('quoted-op', parsed['reference_message_id'])
        self.assertEqual(['https://example.com/op.png'], parsed['images'])
        self.assertIn('看这张图', parsed['text'])

    def test_safe_reply_uses_op_reply_segment(self):
        event = FakeEvent('测试消息')
        OlivaAIAgent.msgReply._safeReply(event, '回复内容', {'message_id': 'current-1'})
        self.assertEqual('[OP:reply,id=current-1]回复内容', event.replies[0])

    def test_qqguildv2_at_event_is_silent_when_ambient_is_disabled(self):
        event = FakeEvent('机器人在吗')
        event.data.extend['qq_event_type'] = 'GROUP_AT_MESSAGE_CREATE'
        with mock.patch.object(OlivaAIAgent.identifiers, 'recordIncoming'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_logQuotedMessage'), \
                mock.patch.object(OlivaAIAgent.reminder, 'registerSender'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_seenMessage', return_value=False), \
                mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=False), \
                mock.patch.object(OlivaAIAgent.msgReply, '_checkGroupUsable', return_value=True), \
                mock.patch.object(OlivaAIAgent.conf, 'isAmbientEnabled', return_value=False), \
                mock.patch.object(OlivaAIAgent.ambient, 'process') as process:
            OlivaAIAgent.msgReply._onGroupMessage(event, None)

        process.assert_not_called()
        self.assertFalse(event.blocked)

    def test_reply_to_bot_routes_through_first_thinking_without_probability(self):
        event = FakeEvent('[CQ:reply,id=bot-message-2]你刚才是什么意思？')
        parsed = {
            'trace_id': 'trace-reply',
            'text': '你刚才是什么意思？',
            'at_me': False,
            'reply_to_me': True,
            'quote': {'message_id': 'bot-message-2', 'text': '上一条回复', 'from_self': True},
            'message_id': 'current-1',
            'images': [],
        }
        with mock.patch.object(OlivaAIAgent.msgReply, 'parseMessage', return_value=parsed), \
                mock.patch.object(OlivaAIAgent.identifiers, 'recordIncoming'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_logQuotedMessage'), \
                mock.patch.object(OlivaAIAgent.reminder, 'registerSender'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_seenMessage', return_value=False), \
                mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=False), \
                mock.patch.object(OlivaAIAgent.msgReply, '_checkGroupUsable', return_value=True), \
                mock.patch.object(OlivaAIAgent.conf, 'isAmbientEnabled', return_value=True), \
                mock.patch.object(OlivaAIAgent.ambient, 'process') as process:
            OlivaAIAgent.msgReply._onGroupMessage(event, None)

        process.assert_called_once()
        self.assertTrue(process.call_args.kwargs['force'])
        self.assertFalse(process.call_args.kwargs['skip_first_thinking'])
        self.assertTrue(event.blocked)

    def test_reply_to_bot_is_silent_when_ambient_is_disabled(self):
        event = FakeEvent('[CQ:reply,id=bot-message-3]继续')
        parsed = {
            'trace_id': 'trace-reply-disabled',
            'text': '继续',
            'at_me': False,
            'reply_to_me': True,
            'quote': {'message_id': 'bot-message-3', 'text': '上一条回复', 'from_self': True},
            'message_id': 'current-1',
            'images': [],
        }
        with mock.patch.object(OlivaAIAgent.msgReply, 'parseMessage', return_value=parsed), \
                mock.patch.object(OlivaAIAgent.identifiers, 'recordIncoming'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_logQuotedMessage'), \
                mock.patch.object(OlivaAIAgent.reminder, 'registerSender'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_seenMessage', return_value=False), \
                mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=False), \
                mock.patch.object(OlivaAIAgent.msgReply, '_checkGroupUsable', return_value=True), \
                mock.patch.object(OlivaAIAgent.conf, 'isAmbientEnabled', return_value=False), \
                mock.patch.object(OlivaAIAgent.ambient, 'process') as process:
            OlivaAIAgent.msgReply._onGroupMessage(event, None)

        process.assert_not_called()
        self.assertFalse(event.blocked)

    def test_keyword_skips_first_thinking(self):
        event = FakeEvent('小芙在吗')
        with mock.patch.object(OlivaAIAgent.identifiers, 'recordIncoming'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_logQuotedMessage'), \
                mock.patch.object(OlivaAIAgent.reminder, 'registerSender'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_seenMessage', return_value=False), \
                mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=False), \
                mock.patch.object(OlivaAIAgent.msgReply, '_checkGroupUsable', return_value=True), \
                mock.patch.object(OlivaAIAgent.msgReply, '_unionKeywords', return_value=['小芙']), \
                mock.patch.object(OlivaAIAgent.ambient, 'process') as process:
            OlivaAIAgent.msgReply._onGroupMessage(event, None)

        process.assert_called_once()
        self.assertTrue(process.call_args.kwargs['force'])
        self.assertTrue(process.call_args.kwargs['skip_first_thinking'])

    def test_group_prefix_still_routes_when_ambient_is_disabled(self):
        event = FakeEvent('.ai 你好')
        with mock.patch.object(OlivaAIAgent.identifiers, 'recordIncoming'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_logQuotedMessage'), \
                mock.patch.object(OlivaAIAgent.reminder, 'registerSender'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_seenMessage', return_value=False), \
                mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=False), \
                mock.patch.object(OlivaAIAgent.msgReply, '_checkGroupUsable', return_value=True), \
                mock.patch.object(OlivaAIAgent.conf, 'isAmbientEnabled', return_value=False), \
                mock.patch.object(OlivaAIAgent.ambient, 'process') as process:
            OlivaAIAgent.msgReply._onGroupMessage(event, None)

        process.assert_called_once()
        self.assertTrue(process.call_args.kwargs['force'])
        self.assertEqual('你好', process.call_args.kwargs['text_override'])
        self.assertTrue(event.blocked)

    def test_ambient_probability_does_not_recheck_at_or_global_keywords(self):
        OlivaAIAgent.conf.gConf['trigger']['keywords'] = ['小芙']
        parsed = {'text': '小芙在吗', 'at_me': True}
        with mock.patch.object(OlivaAIAgent.ambient.random, 'random', return_value=0.9):
            self.assertFalse(
                OlivaAIAgent.ambient.shouldReply(
                    parsed,
                    lambda key, default=None: 0.3 if key == 'reply_probability' else default,
                )
            )

    def test_group_disabled_blocks_keyword_but_master_can_recover_with_prefix(self):
        keyword_event = FakeEvent('小芙在吗')
        with mock.patch.object(OlivaAIAgent.identifiers, 'recordIncoming'), \
                mock.patch.object(OlivaAIAgent.reminder, 'registerSender'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_seenMessage', return_value=False), \
                mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=False), \
                mock.patch.object(OlivaAIAgent.msgReply, '_checkGroupUsable', return_value=False), \
                mock.patch.object(OlivaAIAgent.ambient, 'process') as process:
            OlivaAIAgent.msgReply._onGroupMessage(keyword_event, None)
        process.assert_not_called()

        recovery_event = FakeEvent('.ai on')
        with mock.patch.object(OlivaAIAgent.identifiers, 'recordIncoming'), \
                mock.patch.object(OlivaAIAgent.reminder, 'registerSender'), \
                mock.patch.object(OlivaAIAgent.msgReply, '_seenMessage', return_value=False), \
                mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=True), \
                mock.patch.object(OlivaAIAgent.msgReply, '_checkGroupUsable', return_value=False), \
                mock.patch.object(OlivaAIAgent.conf, 'setGroupSwitch') as set_switch, \
                mock.patch.object(OlivaAIAgent.ambient, 'process') as process:
            OlivaAIAgent.msgReply._onGroupMessage(recovery_event, None)

        set_switch.assert_called_once_with('qqGuild', 'group-1', 'enabled', True)
        process.assert_not_called()
        self.assertTrue(recovery_event.blocked)

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

    def test_uses_qqguild_extend_identifiers_without_confusing_passive_reply_token(self):
        event = FakeEvent(
            '继续说说',
            {
                'active': True,
                'data': {'message': '扩展字段引用的正文', 'sender': {'id': 'user-9', 'name': '引用者'}},
            },
        )
        event.data.message_id = None
        event.data.extend = {
            'event_id': 'event-extend',
            'qq_message_id': 'current-extend',
            'qq_reference_message_id': 'quoted-extend',
            'qq_msg_idx': 'REFIDX_CURRENT',
            'qq_ref_msg_idx': 'REFIDX_QUOTED',
            'reply_msg_id': 'passive-token-must-not-be-used',
        }
        with mock.patch.object(OlivaAIAgent.ambient, 'getHistory', return_value=[]):
            parsed = OlivaAIAgent.msgReply.parseMessage(event)

        self.assertEqual('current-extend', parsed['message_id'])
        self.assertEqual('quoted-extend', parsed['reference_message_id'])
        self.assertEqual('event-extend', parsed['event_id'])
        self.assertEqual('REFIDX_CURRENT', parsed['msg_idx'])
        self.assertEqual('REFIDX_QUOTED', parsed['ref_msg_idx'])
        self.assertEqual(['quoted-extend'], event.get_msg_calls)
        context = OlivaAIAgent.msgReply.attachQuotedContext(parsed, parsed['text'])
        self.assertIn('引用消息ID：quoted-extend', context)
        self.assertNotIn('passive-token-must-not-be-used', context)


if __name__ == '__main__':
    unittest.main()
