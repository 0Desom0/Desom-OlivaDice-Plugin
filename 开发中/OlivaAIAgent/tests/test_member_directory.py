# -*- encoding: utf-8 -*-

import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import OlivaAIAgent


class FakeEvent:
    def __init__(self, user_id='user-1', nickname='甲', sdk='qqGuildv2_link'):
        self.platform = {'sdk': sdk, 'platform': 'qqGuild', 'model': 'public'}
        self.plugin_info = {'func_type': 'group_message'}
        self.data = SimpleNamespace(
            group_id='group-1',
            user_id=user_id,
            sender={'nickname': nickname, 'name': nickname, 'card': '群名片-' + nickname},
        )
        self.base_info = {'self_id': 'bot-1'}
        self.bot_info = SimpleNamespace(hash='bot-hash')


class MemberDirectoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.memberDirectory._initialized_path = None

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.memberDirectory._initialized_path = None
        self.temp_dir.cleanup()

    def test_records_openid_and_all_sender_aliases(self):
        event = FakeEvent(user_id='openid-1', nickname='雨多落为萁')

        self.assertTrue(OlivaAIAgent.memberDirectory.recordIncoming(event))

        self.assertEqual(
            'openid-1',
            OlivaAIAgent.memberDirectory.resolveNickname(event, '雨多落为萁'),
        )
        self.assertEqual(
            'openid-1',
            OlivaAIAgent.memberDirectory.resolveNickname(event, '群名片-雨多落为萁'),
        )

    def test_olivos_cache_has_priority_over_local_fallback(self):
        event = FakeEvent(user_id='local-openid', nickname='雨多落为萁')
        OlivaAIAgent.memberDirectory.recordIncoming(event)
        adapter = OlivaAIAgent.memberDirectory.OlivOS.qqGuildv2SDK
        cache = {
            ('bot-hash', 'cache-openid'): {
                'id': 'cache-openid',
                'member_openid': 'cache-openid',
                'name': '雨多落为萁',
                'chat_type': 'qq_group',
                'chat_id': 'group-1',
            },
        }
        with (
            mock.patch.object(adapter, 'sdkUserInfo', cache),
            mock.patch.object(adapter, 'sdkUserInfoLock', threading.Lock()),
        ):
            result = OlivaAIAgent.memberDirectory.resolveNickname(event, '雨多落为萁')

        self.assertEqual('cache-openid', result)

    def test_ambiguous_local_nickname_is_not_guessed(self):
        first = FakeEvent(user_id='openid-1', nickname='同名群友', sdk='onebot')
        second = FakeEvent(user_id='openid-2', nickname='同名群友', sdk='onebot')
        OlivaAIAgent.memberDirectory.recordIncoming(first)
        OlivaAIAgent.memberDirectory.recordIncoming(second)

        self.assertIsNone(OlivaAIAgent.memberDirectory.resolveNickname(first, '同名群友'))
        self.assertEqual(
            '@同名群友 你好',
            OlivaAIAgent.memberDirectory.normalizeLiteralMentions(first, '@同名群友 你好'),
        )

    def test_normalizes_other_member_mentions_without_touching_email_or_op_segments(self):
        event = FakeEvent(user_id='sender-openid', nickname='发送者', sdk='onebot')
        other = FakeEvent(user_id='other-openid', nickname='雨多落为萁', sdk='onebot')
        OlivaAIAgent.memberDirectory.recordIncoming(event)
        OlivaAIAgent.memberDirectory.recordIncoming(other)

        result = OlivaAIAgent.memberDirectory.normalizeLiteralMentions(
            event,
            '请@雨多落为萁 来讲，邮箱 a@雨多落为萁.com，已有[OP:at,id=kept]。',
        )

        self.assertEqual(
            '请[OP:at,id=other-openid] 来讲，邮箱 a@雨多落为萁.com，已有[OP:at,id=kept]。',
            result,
        )


if __name__ == '__main__':
    unittest.main()
