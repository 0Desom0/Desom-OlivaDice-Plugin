# -*- encoding: utf-8 -*-

import unittest
from types import SimpleNamespace
from unittest import mock

import OlivaAIAgent


class RunCommandMentionTest(unittest.TestCase):
    def test_op_at_is_structurally_converted_for_old_string_rerx(self):
        self.assertEqual(
            '.jrrp [CQ:at,qq=target-openid]',
            OlivaAIAgent.tools._commandForRerx('.jrrp [OP:at,id=target-openid]'),
        )

    def test_current_message_mention_can_target_jrrp(self):
        target, error = OlivaAIAgent.tools._mentionedCommandTarget(
            {'mentioned_user_ids': ['target-openid']},
            '.jrrp [OP:at,id=target-openid]',
        )

        self.assertEqual('target-openid', target)
        self.assertIsNone(error)

    def test_unmentioned_user_cannot_be_impersonated(self):
        target, error = OlivaAIAgent.tools._mentionedCommandTarget(
            {'mentioned_user_ids': ['other-openid']},
            '.jrrp [OP:at,id=target-openid]',
        )

        self.assertIsNone(target)
        self.assertIn('当前消息中明确 AT', error)

    def test_non_jrrp_command_never_switches_user(self):
        target, error = OlivaAIAgent.tools._mentionedCommandTarget(
            {'mentioned_user_ids': ['target-openid']},
            '.st show [OP:at,id=target-openid]',
        )

        self.assertIsNone(target)
        self.assertIsNone(error)

    def test_target_event_uses_directory_name_without_inheriting_sender_role(self):
        rerx = SimpleNamespace(data=SimpleNamespace(user_id='sender-openid', sender={'role': 'owner'}))
        source_event = object()
        with mock.patch.object(
            OlivaAIAgent.memberDirectory,
            'displayName',
            return_value='Fire of Rain',
        ):
            OlivaAIAgent.tools._applyMentionedCommandTarget(
                rerx,
                source_event,
                'target-openid',
            )

        self.assertEqual('target-openid', rerx.data.user_id)
        self.assertEqual('Fire of Rain', rerx.data.sender['name'])
        self.assertNotIn('role', rerx.data.sender)


if __name__ == '__main__':
    unittest.main()
