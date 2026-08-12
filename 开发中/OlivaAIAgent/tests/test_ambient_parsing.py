import json
import unittest

import OlivaAIAgent


class AmbientReplyParsingTest(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
