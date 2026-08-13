import json
import unittest
from unittest import mock

import OlivaAIAgent


class AmbientReplyParsingTest(unittest.TestCase):
    def assert_relaxed_reply(self, raw, expected):
        self.assertEqual(expected, OlivaAIAgent.ambient._parseR(raw))
        self.assertEqual(expected, OlivaAIAgent.ambient._fallback_parse_intent(raw))
        self.assertEqual(
            '\n\n'.join(expected),
            OlivaAIAgent.msgReply._normalizeAgentFinalText(raw),
        )

    def test_relaxed_reply_envelopes_are_unwrapped(self):
        cases = (
            ('{:r:["正文"]}', ['正文']),
            ('{r:["正文"]}', ['正文']),
            ("{'r':['正文']}", ['正文']),
            ('｛：r：［“正文一”，“正文二”］｝', ['正文一', '正文二']),
            ('```json\n{:r:["正文"]}\n```', ['正文']),
        )

        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assert_relaxed_reply(raw, expected)

    def test_relaxed_reply_preserves_content_and_escapes(self):
        raw = '{:r:["哪有那么文明呀~🦊 中文“引号”：保留。\\n下一行"]}'
        self.assert_relaxed_reply(
            raw,
            ['哪有那么文明呀~🦊 中文“引号”：保留。\n下一行'],
        )

    def test_broken_relaxed_reply_envelope_is_not_sent_verbatim(self):
        raw = '{:r:["正文没有结束]}'

        self.assertIsNone(OlivaAIAgent.ambient._parseR(raw))
        self.assertEqual([], OlivaAIAgent.ambient._fallback_parse_intent(raw))
        self.assertEqual('', OlivaAIAgent.msgReply._normalizeAgentFinalText(raw))

    def test_plain_text_that_only_mentions_reply_syntax_is_unchanged(self):
        raw = '普通聊天里提到 {:r: 但不是完整结构'

        self.assertIsNone(OlivaAIAgent.ambient._parseR(raw))
        self.assertEqual([raw], OlivaAIAgent.ambient._fallback_parse_intent(raw))
        self.assertEqual(raw, OlivaAIAgent.msgReply._normalizeAgentFinalText(raw))

    def test_smart_quotes_around_reply_key_are_normalized(self):
        raw = '{“r”:["这只小狗配个“乐”字也太贴脸了吧"]}'
        expected = ['这只小狗配个“乐”字也太贴脸了吧']

        self.assertEqual(expected, OlivaAIAgent.ambient._parseR(raw))
        self.assertEqual(expected, OlivaAIAgent.ambient._fallback_parse_intent(raw))
        self.assertEqual(expected[0], OlivaAIAgent.msgReply._normalizeAgentFinalText(raw))

    def test_fully_smart_quoted_reply_json_preserves_inner_chinese_quotes(self):
        raw = '{“r”:[“这只小狗配个“乐”字也太贴脸了吧”]}'

        self.assertEqual(
            ['这只小狗配个“乐”字也太贴脸了吧'],
            OlivaAIAgent.ambient._parseR(raw),
        )

    def test_broken_smart_quoted_json_is_not_sent_as_plain_text(self):
        raw = '{“r”:["回复没有结束]}'

        self.assertIsNone(OlivaAIAgent.ambient._parseR(raw))
        self.assertEqual([], OlivaAIAgent.ambient._fallback_parse_intent(raw))
        self.assertEqual('', OlivaAIAgent.msgReply._normalizeAgentFinalText(raw))

    def test_tesla_env_json_body_is_unwrapped_without_losing_content(self):
        reply = (
            '小芙帮你找了几个国内能直连的资源～\n\n'
            '**淘声网**：\nhttps://www.tosound.com/search/word-test\n'
            '搜"生化危机 获得道具 音效"就能找到一堆'
        )
        body = json.dumps({'r': [reply]}, ensure_ascii=False)
        wrapped = '{:ok, %%Tesla.Env{status: 200, body: %s}}' % json.dumps(body, ensure_ascii=False)

        self.assertEqual([reply], OlivaAIAgent.ambient._parseR(wrapped))
        self.assertEqual([reply], OlivaAIAgent.ambient._fallback_parse_intent(wrapped))

    def test_malformed_tesla_env_is_not_sent_as_plain_text(self):
        malformed = '{:ok, %Tesla.Env{status: 200, body: "{\\"r\\":[\\"broken]"}}'

        self.assertIsNone(OlivaAIAgent.ambient._parseR(malformed))
        self.assertEqual([], OlivaAIAgent.ambient._fallback_parse_intent(malformed))

    def test_blank_lines_split_one_model_item_into_multiple_messages(self):
        self.assertEqual(
            ['第一段', '第二段\n仍是第二段', '第三段'],
            OlivaAIAgent.ambient._replyWash(['第一段\n\n第二段\n仍是第二段\n  \n第三段']),
        )

    def test_blank_line_splitting_respects_max_message_count(self):
        old_conf = OlivaAIAgent.conf.gConf
        try:
            OlivaAIAgent.conf.gConf = {
                'reply': {'split_length': 1500, 'max_split_count': 2},
            }
            self.assertEqual(
                ['第一段', '第二段'],
                OlivaAIAgent.ambient._replyWash(['第一段\n\n第二段\n\n第三段']),
            )
        finally:
            OlivaAIAgent.conf.gConf = old_conf

    def test_mention_segments_are_not_kept_in_model_text(self):
        self.assertEqual(
            '这是什么',
            OlivaAIAgent.msgReply.stripMentionSegments(
                '[OP:at,id=owner-openid] 这是什么',
            ),
        )

    def test_self_action_narration_is_removed_but_answer_is_kept(self):
        self.assertEqual(
            '叶师傅这伤看着不轻呀。',
            OlivaAIAgent.replyStyle.cleanReplyText(
                '小芙看了一眼图，尾巴微微一顿~叶师傅这伤看着不轻呀。',
            ),
        )
        self.assertEqual(
            '这波教程的步骤是先构建，再上传。',
            OlivaAIAgent.replyStyle.cleanReplyText(
                '小芙瞄了眼这段log提取的教程截图，尾巴轻轻晃了晃~\n\n这波教程的步骤是先构建，再上传。',
            ),
        )

    def test_plain_tail_content_is_not_removed(self):
        self.assertEqual('小芙的尾巴是设定里的装饰。', OlivaAIAgent.replyStyle.cleanReplyText(
            '小芙的尾巴是设定里的装饰。',
        ))

    def test_action_prefix_does_not_consume_the_actual_answer(self):
        self.assertEqual('答案是猫。', OlivaAIAgent.replyStyle.cleanReplyText(
            '小芙看了一眼图，答案是猫。',
        ))

    def test_normal_parenthetical_reply_content_is_kept(self):
        self.assertEqual('答案在这里（这是补充说明）。', OlivaAIAgent.replyStyle.cleanReplyText(
            '答案在这里（这是补充说明）。',
        ))

    def test_internal_agent_deliberation_is_never_outgoing_text(self):
        leaked = (
            'The current message from Zeroyume is "狗被小芙咬了". '
            'Wait, but the current speaker listed in internal context is Zeroyume.'
        )
        self.assertTrue(OlivaAIAgent.replyStyle.containsInternalDeliberation(leaked))
        self.assertEqual('', OlivaAIAgent.replyStyle.cleanReplyText(leaked))

    def test_hidden_thinking_block_is_removed_but_final_answer_is_kept(self):
        self.assertEqual(
            '这锅我可不背。',
            OlivaAIAgent.replyStyle.cleanReplyText(
                '<think>Let me check the current speaker in internal context.</think>这锅我可不背。',
            ),
        )

    def test_ambient_retries_instead_of_sending_internal_deliberation(self):
        leaked = {
            'ok': True,
            'text': '{"r":["Actually the last message in history is from Zeroyume."]}',
            'tool_calls': [],
        }
        repaired = {'ok': True, 'text': '{"r":["这锅我可不背。"]}', 'tool_calls': []}
        with mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=[leaked, repaired]) as chat:
            reply = OlivaAIAgent.ambient._callReply(
                None,
                None,
                'bot',
                'group',
                [{'role': 'user', 'content': '狗被小芙咬了'}],
                [],
                False,
                request_text='狗被小芙咬了',
            )

        self.assertEqual(['这锅我可不背。'], reply)
        self.assertEqual(2, chat.call_count)
        self.assertIn('内部过程泄漏修正', chat.call_args.args[0][-1]['content'])

    def test_non_json_multiline_deliberation_uses_the_same_repair_path(self):
        leaked = {
            'ok': True,
            'text': (
                'The current message from Zeroyume is "狗被小芙咬了". Wait, but the current speaker '
                'listed in internal context is Zeroyume.\n\n'
                'Actually the last message in history is from another user.\n\n'
                'Best to respond in character as 小芙.'
            ),
            'tool_calls': [],
        }
        repaired = {'ok': True, 'text': '{"r":["谁咬的？小芙可不认这口锅。"]}', 'tool_calls': []}
        with mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=[leaked, repaired]) as chat:
            reply = OlivaAIAgent.ambient._callReply(
                None,
                None,
                'bot',
                'group',
                [{'role': 'user', 'content': '狗被小芙咬了'}],
                [],
                False,
                request_text='狗被小芙咬了',
            )

        self.assertEqual(['谁咬的？小芙可不认这口锅。'], reply)
        self.assertEqual(2, chat.call_count)

    def test_chinese_planning_that_stops_before_json_is_repaired(self):
        leaked_text = (
            '用户当前触发我的是一条日文小调戏，但历史消息我已有回复。'
            '而当前最新消息是那条合并转发的跑团检定。这其实是被引用的历史，'
            '我现在收到的是“当前消息”应该是转发内容。\n\n'
            '不过按当前任务，我是被触发需要回应。最新实质内容是这个转发里的检定。'
            '我作为骰娘可以自然回应一下这个失败结果。\n\n'
            '我可以皮一下回个话。\n\n输出 JSON。'
        )
        self.assertTrue(OlivaAIAgent.replyStyle.containsInternalDeliberation(leaked_text))
        responses = [
            {'ok': True, 'text': leaked_text, 'tool_calls': []},
            {'ok': True, 'text': '{"r":["这调查失败得也太快了吧。"]}', 'tool_calls': []},
        ]
        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=responses) as chat,
            mock.patch.object(OlivaAIAgent.voice, 'hasSentVoice', return_value=False),
        ):
            reply = OlivaAIAgent.ambient._callReplyWithTools(
                None,
                None,
                'bot',
                'group',
                [{'role': 'user', 'content': '[合并转发:检定失败]'}],
                [],
                trace_id='chinese-planning-leak-test',
                tool_ctx={'trace_id': 'chinese-planning-leak-test'},
                tool_defs=[{'name': 'run_command'}],
                request_text='[合并转发:检定失败]',
            )

        self.assertEqual(['这调查失败得也太快了吧。'], reply)
        self.assertEqual(2, chat.call_count)


if __name__ == '__main__':
    unittest.main()
