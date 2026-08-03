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


if __name__ == '__main__':
    unittest.main()
