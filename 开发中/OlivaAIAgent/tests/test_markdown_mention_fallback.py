# -*- encoding: utf-8 -*-

import tempfile
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
            sender={'nickname': '哈基米路多', 'name': '哈基米路多'},
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
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.memberDirectory._initialized_path = None

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.memberDirectory._initialized_path = None
        self.temp_dir.cleanup()

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

    def test_detects_explicit_markdown_without_matching_plain_punctuation(self):
        markdown_samples = [
            '# 标题\n正文',
            '**粗体内容**',
            '- 第一项\n- 第二项',
            '| 名称 | 数值 |\n| --- | --- |\n| 力量 | 80 |',
            '```python\nprint("ok")\n```',
            '[规则书](https://example.com/rule)',
        ]

        for sample in markdown_samples:
            with self.subTest(sample=sample):
                self.assertTrue(OlivaAIAgent.msgReply._looksLikeMarkdown(sample))
        self.assertFalse(OlivaAIAgent.msgReply._looksLikeMarkdown('普通回复 * 只是乘号'))
        self.assertFalse(OlivaAIAgent.msgReply._looksLikeMarkdown('今天编号是 item_1'))

    def test_safe_reply_sends_formatted_text_as_markdown(self):
        event = FakeEvent()
        content = '# 检定结果\n\n- 力量：80\n- 结果：成功'
        with (
            mock.patch.object(OlivaAIAgent.coreLogger, 'recordToolCall'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            OlivaAIAgent.msgReply._safeReply(event, content, safety_check=False)

        self.assertEqual([], event.replies)
        self.assertEqual(1, len(event.markdown_calls))
        self.assertEqual({'content': content}, event.markdown_calls[0]['markdown'])

    def test_markdown_switch_can_disable_automatic_format_sending(self):
        event = FakeEvent()
        original_get = OlivaAIAgent.conf.get

        def config_get(section, key, default=None):
            if section == 'reply' and key == 'qqguild_auto_markdown':
                return False
            return original_get(section, key, default=default)

        with (
            mock.patch.object(OlivaAIAgent.conf, 'get', side_effect=config_get),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            OlivaAIAgent.msgReply._safeReply(event, '**普通粗体**', safety_check=False)

        self.assertEqual([], event.markdown_calls)
        self.assertEqual(['**普通粗体**'], event.replies)

    def test_ambient_markdown_keeps_links_and_paragraphs_in_one_message(self):
        event = FakeEvent()
        content = '# 资料\n\n[规则书](https://example.com/rule)\n\n**请查收**'
        with (
            mock.patch.object(OlivaAIAgent.ambient.time, 'sleep'),
            mock.patch.object(OlivaAIAgent.coreLogger, 'recordToolCall'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            washed = OlivaAIAgent.ambient._replyWash([content], plugin_event=event)
            records = OlivaAIAgent.ambient._sendMulti(
                event,
                washed,
                total_past=0,
                trace_id='trace-markdown',
            )

        self.assertEqual([content], washed)
        self.assertEqual({'content': content}, event.markdown_calls[0]['markdown'])
        self.assertEqual(content, records[0]['message'])

    def test_safe_reply_sends_at_as_markdown_without_forced_quote(self):
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
        self.assertNotIn('quote_msg_id', event.markdown_calls[0])
        self.assertEqual(
            {'content': '<qqbot-at-user id="user-2" /> 你好'},
            event.markdown_calls[0]['markdown'],
        )

    def test_safe_reply_sends_model_selected_plain_quote_through_markdown_sdk(self):
        event = FakeEvent()
        parsed = {'message_id': 'current-1', 'trace_id': 'trace-quote'}
        with (
            mock.patch.object(OlivaAIAgent.coreLogger, 'recordToolCall'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '[OP:reply,id=current-1]普通文字回复',
                parsed,
                safety_check=False,
            )

        self.assertEqual([], event.replies)
        self.assertEqual(1, len(event.markdown_calls))
        self.assertEqual('current-1', event.markdown_calls[0]['quote_msg_id'])
        self.assertEqual(
            {'content': '普通文字回复'},
            event.markdown_calls[0]['markdown'],
        )

    def test_ambient_model_selected_quote_uses_markdown_and_records_reference(self):
        event = FakeEvent()
        with (
            mock.patch.object(OlivaAIAgent.ambient.time, 'sleep'),
            mock.patch.object(OlivaAIAgent.coreLogger, 'recordToolCall'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing') as record_outgoing,
        ):
            records = OlivaAIAgent.ambient._sendMulti(
                event,
                ['[OP:reply,id=current-1]普通文字回复'],
                total_past=0,
                trace_id='trace-ambient-quote',
            )

        self.assertEqual([], event.replies)
        self.assertEqual('current-1', event.markdown_calls[0]['quote_msg_id'])
        self.assertEqual('current-1', records[0]['reference_message_id'])
        self.assertEqual('current-1', record_outgoing.call_args.kwargs['reference_message_id'])

    def test_quote_switch_disables_model_reply_segment(self):
        event = FakeEvent()
        original_get = OlivaAIAgent.conf.get

        def config_get(section, key, default=None):
            if section == 'reply' and key == 'quote_reply':
                return False
            return original_get(section, key, default=default)

        with (
            mock.patch.object(OlivaAIAgent.conf, 'get', side_effect=config_get),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '[OP:reply,id=current-1]普通文字回复',
                {'message_id': 'current-1'},
                safety_check=False,
            )

        self.assertEqual([], event.markdown_calls)
        self.assertEqual(['普通文字回复'], event.replies)

    def test_safe_reply_converts_literal_current_sender_mention(self):
        event = FakeEvent()
        with (
            mock.patch.object(OlivaAIAgent.coreLogger, 'recordToolCall'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '@哈基米路多 就是说啊?',
                safety_check=False,
            )

        self.assertEqual([], event.replies)
        self.assertEqual(1, len(event.markdown_calls))
        self.assertEqual(
            {'content': '<qqbot-at-user id="user-1" /> 就是说啊?'},
            event.markdown_calls[0]['markdown'],
        )

    def test_literal_other_user_mention_uses_local_member_directory(self):
        event = FakeEvent()
        other = FakeEvent()
        other.data.user_id = 'user-2'
        other.data.sender = {'nickname': '另一个群友', 'name': '另一个群友'}
        OlivaAIAgent.memberDirectory.recordIncoming(other)
        with (
            mock.patch.object(OlivaAIAgent.coreLogger, 'recordToolCall'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '@另一个群友 你好',
                safety_check=False,
            )

        self.assertEqual([], event.replies)
        self.assertEqual(
            {'content': '<qqbot-at-user id="user-2" /> 你好'},
            event.markdown_calls[0]['markdown'],
        )

    def test_unknown_literal_mention_remains_plain_text(self):
        event = FakeEvent()
        with (
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            OlivaAIAgent.msgReply._safeReply(event, '@未知群友 你好', safety_check=False)

        self.assertEqual([], event.markdown_calls)
        self.assertEqual(['@未知群友 你好'], event.replies)

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
            ['[OP:at,id=user-2] 你好'],
            event.replies,
        )

    def test_non_qqguildv2_keeps_normal_reply_path(self):
        event = FakeEvent(sdk='onebot')
        other = FakeEvent(sdk='onebot')
        other.data.user_id = 'user-2'
        other.data.sender = {'nickname': '另一个群友', 'name': '另一个群友'}
        OlivaAIAgent.memberDirectory.recordIncoming(other)
        with (
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '@另一个群友 你好',
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

    def test_ambient_plain_text_uses_passive_reply_path(self):
        event = FakeEvent()
        with (
            mock.patch.object(OlivaAIAgent.ambient.time, 'sleep'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
        ):
            records = OlivaAIAgent.ambient._sendMulti(
                event,
                ['普通回复'],
                total_past=0,
                trace_id='trace-passive',
            )

        self.assertEqual(['普通回复'], event.replies)
        self.assertEqual([], event.sends)
        self.assertEqual(1, len(records))


if __name__ == '__main__':
    unittest.main()
