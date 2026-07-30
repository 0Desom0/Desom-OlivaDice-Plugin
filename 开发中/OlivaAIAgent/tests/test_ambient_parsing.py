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


if __name__ == '__main__':
    unittest.main()
