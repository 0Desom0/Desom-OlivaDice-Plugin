# -*- encoding: utf-8 -*-

import copy
import tempfile
import unittest
from unittest import mock

import OlivaAIAgent


class ConversationPolicyTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.conversation.resetBudgetForTest()

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.conversation.resetBudgetForTest()
        self.temp_dir.cleanup()

    def test_owner_continues_thread_and_outsider_is_interrupt_after_bot_reply(self):
        parsed = {'text': '继续刚才的', 'at_me': False, 'reply_to_me': False}
        first = OlivaAIAgent.conversation.observeIncoming(
            'qq', 'g1', parsed, 'user-a', nickname='甲',
        )
        self.assertTrue(first['is_owner'])
        self.assertFalse(first['is_interrupt'])
        OlivaAIAgent.conversation.observeOutgoing('qq', 'g1')
        outsider = OlivaAIAgent.conversation.observeIncoming(
            'qq', 'g1', {'text': '插一句', 'at_me': False}, 'user-b', nickname='乙',
        )
        self.assertTrue(outsider['is_interrupt'])
        self.assertEqual('甲', outsider['owner_name'])
        directed = OlivaAIAgent.conversation.observeIncoming(
            'qq', 'g1', {'text': '小芙', 'at_me': True}, 'user-b', nickname='乙', directed=True,
        )
        self.assertTrue(directed['is_owner'])
        self.assertFalse(directed['is_interrupt'])

    def test_classify_reason_codes(self):
        self.assertEqual(
            'at_me',
            OlivaAIAgent.conversation.classifyReason({'at_me': True}),
        )
        OlivaAIAgent.conf.gConf['trigger']['keywords'] = ['小芙']
        self.assertEqual(
            'named',
            OlivaAIAgent.conversation.classifyReason({'text': '小芙在吗', 'at_me': False}),
        )
        self.assertEqual(
            'thread_continue',
            OlivaAIAgent.conversation.classifyReason(
                {'text': '然后呢', 'at_me': False},
                {'is_owner': True},
            ),
        )
        self.assertEqual(
            'chitchat',
            OlivaAIAgent.conversation.classifyReason(
                {'text': '哈哈', 'at_me': False},
                {'is_interrupt': True},
            ),
        )

    def test_parse_participation_json_reason(self):
        decision, reason = OlivaAIAgent.conversation.parseParticipation(
            '{"d":"SKIP","r":"chitchat"}',
        )
        self.assertEqual('SKIP', decision)
        self.assertEqual('chitchat', reason)
        self.assertEqual(
            'SKIP',
            OlivaAIAgent.ambient._parseParticipationDecision('{"should_reply":false}'),
        )

    def test_context_isolation_is_opt_in(self):
        history = [
            {'user_id': 'a', 'nickname': '甲', 'message': '线程内1'},
            {'user_id': 'c', 'nickname': '丙', 'message': '旁人闲聊'},
            {'user_id': 'a', 'nickname': '甲', 'message': '线程内2'},
            {'user_id': None, 'nickname': None, 'message': '我回了'},
        ]
        affinity = {'owner_id': 'a', 'user_ids': ['a']}
        full, digest = OlivaAIAgent.conversation.splitContext(history, affinity)
        self.assertEqual(history, full)
        self.assertEqual('', digest)
        OlivaAIAgent.conf.gConf['ambient']['context_isolation']['enable'] = True
        thread, digest = OlivaAIAgent.conversation.splitContext(history, affinity)
        self.assertEqual(['线程内1', '线程内2', '我回了'], [item['message'] for item in thread])
        self.assertIn('丙:旁人闲聊', digest)

    def test_interrupt_scales_passive_probability(self):
        parsed = {'text': '插话', 'standalone_emoji': False}
        with mock.patch.object(OlivaAIAgent.ambient.random, 'random', return_value=0.5):
            self.assertTrue(OlivaAIAgent.ambient.shouldReply(
                parsed, lambda key, default=None: 1.0, probability_scale=1.0,
            ))
            self.assertFalse(OlivaAIAgent.ambient.shouldReply(
                parsed, lambda key, default=None: 1.0, probability_scale=0.2,
            ))

    def test_tool_group_whitelist_and_daily_budget(self):
        ctx = {'func_type': 'group_message', 'platform': 'qq', 'group_id': '10001'}
        OlivaAIAgent.conf.gConf['permissions']['search_groups'] = ['99999']
        ok, why = OlivaAIAgent.conversation.checkToolGate('web_search', ctx)
        self.assertFalse(ok)
        self.assertIn('未开放', why)
        OlivaAIAgent.conf.gConf['permissions']['search_groups'] = []
        OlivaAIAgent.conf.gConf['permissions']['search_daily_limit'] = 1
        ok, _why = OlivaAIAgent.conversation.checkToolGate('web_search', ctx, consume=True)
        self.assertTrue(ok)
        ok, why = OlivaAIAgent.conversation.checkToolGate('web_search', ctx, consume=True)
        self.assertFalse(ok)
        self.assertIn('次数已用完', why)
        self.assertEqual(['run_command'], OlivaAIAgent.conversation.filterToolNames(
            ['web_search', 'run_command'], ctx,
        ))


if __name__ == '__main__':
    unittest.main()
