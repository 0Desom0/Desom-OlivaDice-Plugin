# -*- encoding: utf-8 -*-

import unittest
from types import SimpleNamespace
from unittest import mock

import OlivaAIAgent


class FakeEvent:
    def __init__(self, sdk='qqGuildv2_link', markdown_result=None):
        self.platform = {'sdk': sdk, 'platform': 'qqGuild', 'model': 'public'}
        self.plugin_info = {'func_type': 'group_message'}
        self.data = SimpleNamespace(
            group_id='group-1',
            user_id='user-1',
            message_id='current-1',
            extend={'flag_from_qq': True, 'flag_from_direct': False},
        )
        self.base_info = {'self_id': 'bot-1'}
        self.bot_info = SimpleNamespace(hash='bot-hash')
        self.replies = []
        self.sends = []
        self.markdown_calls = []
        self.markdown_result = markdown_result or {
            'active': True,
            'data': {'message_id': 'markdown-1'},
        }
        self.indeAPI = SimpleNamespace(create_markdown_message=self.create_markdown_message)

    def create_markdown_message(self, **kwargs):
        self.markdown_calls.append(kwargs)
        return self.markdown_result

    def reply(self, message):
        self.replies.append(message)
        return {'active': True, 'data': {'message_id': 'reply-1'}}

    def send(self, send_type, target_id, message):
        self.sends.append((send_type, target_id, message))
        return {'active': True, 'data': {'message_id': 'send-1'}}


class MarkdownMentionFallbackTest(unittest.TestCase):
    def test_converts_op_and_cq_at_segments_with_sdk_format(self):
        op_content = OlivaAIAgent.msgReply._qqGuildMarkdownMentionContent(
            '[OP:reply,id=quoted-1][OP:at,id=user-2] 你好',
        )
        cq_content = OlivaAIAgent.msgReply._qqGuildMarkdownMentionContent(
            '[CQ:at,qq=user-3] 你好',
        )

        self.assertEqual('<qqbot-at-user id="user-2" /> 你好', op_content)
        self.assertEqual('<qqbot-at-user id="user-3" /> 你好', cq_content)

    def test_accepts_sdk_markdown_at_tag(self):
        content = OlivaAIAgent.msgReply._qqGuildMarkdownMentionContent(
            '你好 <qqbot-at-user id="user-2" />',
        )

        self.assertEqual('你好 <qqbot-at-user id="user-2" />', content)

    def test_safe_reply_sends_at_as_markdown_and_preserves_quote(self):
        event = FakeEvent()
        parsed = {'message_id': 'current-1', 'trace_id': 'trace-1'}
        with (
            mock.patch.object(OlivaAIAgent.coreLogger, 'recordToolCall'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '[OP:at,id=user-2] 你好',
                parsed,
                safety_check=False,
            )

        self.assertEqual([], event.replies)
        self.assertEqual(1, len(event.markdown_calls))
        self.assertEqual('qq_group', event.markdown_calls[0]['chat_type'])
        self.assertEqual('group-1', event.markdown_calls[0]['chat_id'])
        self.assertEqual('current-1', event.markdown_calls[0]['quote_msg_id'])
        self.assertEqual(
            {'content': '<qqbot-at-user id="user-2" /> 你好'},
            event.markdown_calls[0]['markdown'],
        )

    def test_markdown_failure_falls_back_to_normal_reply(self):
        event = FakeEvent(markdown_result={'active': False, 'data': {'error': 'denied'}})
        parsed = {'message_id': 'current-1', 'trace_id': 'trace-2'}
        with (
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '[OP:at,id=user-2] 你好',
                parsed,
                safety_check=False,
            )

        self.assertEqual(
            ['[OP:reply,id=current-1][OP:at,id=user-2] 你好'],
            event.replies,
        )

    def test_non_qqguildv2_keeps_normal_reply_path(self):
        event = FakeEvent(sdk='onebot')
        with (
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '[OP:at,id=user-2] 你好',
                safety_check=False,
            )

        self.assertEqual([], event.markdown_calls)
        self.assertEqual(['[OP:at,id=user-2] 你好'], event.replies)

    def test_ambient_at_reply_uses_same_markdown_fallback(self):
        event = FakeEvent()
        with (
            mock.patch.object(OlivaAIAgent.ambient.time, 'sleep'),
            mock.patch.object(OlivaAIAgent.coreLogger, 'recordToolCall'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            records = OlivaAIAgent.ambient._sendMulti(
                event,
                ['<qqbot-at-user id="user-2" /> 你好'],
                total_past=0,
                trace_id='trace-3',
            )

        self.assertEqual([], event.sends)
        self.assertEqual(1, len(event.markdown_calls))
        self.assertEqual(1, len(records))


if __name__ == '__main__':
    unittest.main()
