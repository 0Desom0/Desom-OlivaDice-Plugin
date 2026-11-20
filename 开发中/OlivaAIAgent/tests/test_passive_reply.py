# -*- encoding: utf-8 -*-

import types
import unittest
import unittest.mock

import OlivOS
import OlivaAIAgent


class FakeEvent:
    def __init__(self, message_id, group_id='group-1', private=False):
        self.platform = {'sdk': 'qqGuildv2_link', 'platform': 'qqGuild', 'model': 'public'}
        self.plugin_info = {'func_type': 'private_message' if private else 'group_message'}
        self.base_info = {'self_id': 'bot-1'}
        self.bot_info = types.SimpleNamespace(hash='bot-hash')
        self.data = types.SimpleNamespace(
            group_id=group_id,
            user_id='user-1',
            message_id=message_id,
            extend={
                'flag_from_qq': True,
                'flag_from_direct': private,
                'reply_msg_id': message_id,
                'qq_event_type': 'C2C_MESSAGE_CREATE' if private else 'GROUP_AT_MESSAGE_CREATE',
            },
        )
        self.replies = []
        self.sends = []

    def reply(self, message, *args, **kwargs):
        self.replies.append((message, self.data.extend.get('reply_msg_id')))
        return {
            'active': True,
            'data': {'message_id': 'out-%d' % len(self.replies)},
        }

    def send(self, send_type, target_id, message, host_id=None, *args, **kwargs):
        self.sends.append((send_type, target_id, message))
        return {
            'active': True,
            'data': {'message_id': 'active-%d' % len(self.sends)},
        }


class PassiveReplyTest(unittest.TestCase):
    def setUp(self):
        OlivaAIAgent.passiveReply.resetForTests()

    def tearDown(self):
        OlivaAIAgent.passiveReply.resetForTests()

    def _register(self, *events):
        for event in events:
            OlivaAIAgent.passiveReply.install(event)

    def test_group_rolls_over_to_recent_message_after_five_replies(self):
        old = FakeEvent('old')
        self._register(old)
        current = FakeEvent('current')
        self._register(current)

        for _ in range(6):
            current.reply('正文')

        self.assertEqual(['current'] * 5 + ['old'], [item[1] for item in current.replies])
        self.assertEqual([], current.sends)

    def test_private_rolls_over_after_four_replies(self):
        old = FakeEvent('old', private=True)
        self._register(old)
        current = FakeEvent('current', private=True)
        self._register(current)

        for _ in range(5):
            current.reply('正文')

        self.assertEqual(['current'] * 4 + ['old'], [item[1] for item in current.replies])
        self.assertEqual([], current.sends)

    def test_other_group_message_is_not_used(self):
        other = FakeEvent('other', group_id='group-2')
        self._register(other)
        current = FakeEvent('current', group_id='group-1')
        self._register(current)

        for _ in range(6):
            current.reply('正文')

        self.assertEqual(['current'] * 5, [item[1] for item in current.replies[:5]])
        self.assertEqual([('group', 'group-1', '正文')], current.sends)

    def test_expired_message_is_not_used(self):
        old = FakeEvent('old')
        self._register(old)
        key = ('bot-hash', 'qq_group', 'group-1')
        # 群聊被动回复有效期 2026-11-17 起为 60 分钟，过期的判定线跟着后移。
        OlivaAIAgent.passiveReply._credentials[key]['old']['seen_at'] -= 3601
        current = FakeEvent('current')
        self._register(current)

        for _ in range(6):
            current.reply('正文')

        self.assertEqual(['current'] * 5, [item[1] for item in current.replies[:5]])
        self.assertEqual([('group', 'group-1', '正文')], current.sends)

    def test_credential_survives_the_old_five_minute_window(self):
        event = FakeEvent('long-lived')
        self._register(event)
        key = ('bot-hash', 'qq_group', 'group-1')
        OlivaAIAgent.passiveReply._credentials[key]['long-lived']['seen_at'] -= 1800

        event.reply('正文')

        self.assertEqual([('正文', 'long-lived')], event.replies)
        self.assertEqual([], event.sends)

    def test_group_uses_fifty_replies_for_administrator(self):
        with unittest.mock.patch.object(
            OlivOS.qqGuildv2SDK, 'get_SDK_bot_info_from_Plugin_bot_info', lambda info: info
        ), unittest.mock.patch.object(
            OlivOS.qqGuildv2SDK, 'get_qq_group_passive_limit', lambda bot_info, group_id: 50
        ):
            event = FakeEvent('current')
            self._register(event)
            for _ in range(50):
                event.reply('正文')
            self.assertEqual([], event.sends)

            event.reply('第 51 条')

            self.assertEqual([('group', 'group-1', '第 51 条')], event.sends)

    def test_new_message_restores_passive_reply_after_active_fallback(self):
        current = FakeEvent('current')
        self._register(current)
        for _ in range(6):
            current.reply('正文')
        self.assertEqual(1, len(current.sends))

        new_event = FakeEvent('new')
        self._register(new_event)
        new_event.reply('[OP:reply,id=visible]继续')

        self.assertEqual([('[OP:reply,id=visible]继续', 'new')], new_event.replies)
        self.assertEqual([], new_event.sends)

    def test_markdown_rollover_does_not_change_visible_quote(self):
        old = FakeEvent('old')
        self._register(old)
        current = FakeEvent('current')
        self._register(current)
        calls = []

        def sender(**kwargs):
            calls.append(kwargs)
            return {'active': True, 'data': {'message_id': 'markdown-%d' % len(calls)}}

        kwargs = {
            'chat_type': 'qq_group',
            'chat_id': 'group-1',
            'markdown': {'content': '正文'},
            'quote_msg_id': 'visible-quote',
        }
        for _ in range(6):
            OlivaAIAgent.passiveReply.sendMarkdown(current, sender, kwargs)

        self.assertEqual(['current'] * 5 + ['old'], [item['msg_id'] for item in calls])
        self.assertEqual(['visible-quote'] * 6, [item['quote_msg_id'] for item in calls])

    def test_snapshot_rebinds_passive_wrapper_over_core_logger(self):
        source = FakeEvent('source')
        OlivaAIAgent.coreLogger.install(source)
        OlivaAIAgent.passiveReply.install(source)
        snapshot = OlivaAIAgent.coreLogger.snapshotEvent(source)
        snapshot.replies = []
        snapshot.sends = []

        snapshot.reply('后台回复')

        self.assertEqual([('后台回复', 'source')], snapshot.replies)
        self.assertEqual([], source.replies)
        self.assertEqual([], snapshot.sends)
        self.assertEqual([], source.sends)

    def test_markdown_uses_the_same_credential_pool(self):
        old = FakeEvent('old')
        current = FakeEvent('current')
        self._register(old, current)
        calls = []

        def sender(**kwargs):
            calls.append(kwargs)
            return {'active': True, 'data': {'message_id': 'markdown-%d' % len(calls)}}

        for _ in range(6):
            OlivaAIAgent.passiveReply.sendMarkdown(
                current,
                sender,
                {
                    'chat_type': 'qq_group',
                    'chat_id': 'group-1',
                    'markdown': {'content': '正文'},
                },
            )

        self.assertEqual(['current'] * 5 + ['old'], [item['msg_id'] for item in calls])


if __name__ == '__main__':
    unittest.main()
