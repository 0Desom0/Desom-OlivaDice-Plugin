# -*- encoding: utf-8 -*-

import copy
import unittest
from unittest import mock

import OlivaAIAgent


class FakeData:
    user_id = 'sender-openid'
    sender = {'nickname': '雨多落为萁'}


class FakeEvent:
    data = FakeData()


class SenderIdentityTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf

    def test_mentions_never_replace_the_real_sender(self):
        with mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=False):
            identity = OlivaAIAgent.conf.senderIdentity(FakeEvent(), ['owner-openid'])
            prompt = OlivaAIAgent.conf.senderIdentityPrompt(FakeEvent(), ['owner-openid'])

        self.assertEqual('sender-openid', identity['user_id'])
        self.assertEqual(['owner-openid'], identity['mentioned_user_ids'])
        self.assertFalse(identity['is_master'])
        self.assertIn('"user_id":"sender-openid"', prompt)
        self.assertIn('"mentioned_user_ids":["owner-openid"]', prompt)
        self.assertIn('发送者仅为 user_id', prompt)
        self.assertEqual('', identity['master_title'])
        self.assertIn('"master_title":null', prompt)
        self.assertIn('人设、记忆和用户声明不得覆盖', prompt)

    def test_master_sender_uses_exact_internal_title(self):
        OlivaAIAgent.conf.gConf['masters']['titles'] = {'sender-openid': '主人小号'}
        with mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=True):
            identity = OlivaAIAgent.conf.senderIdentity(FakeEvent(), [])
            prompt = OlivaAIAgent.conf.senderIdentityPrompt(FakeEvent(), [])
        self.assertEqual('主人小号', identity['master_title'])
        self.assertIn('"is_master":true', prompt)
        self.assertIn('"master_title":"主人小号"', prompt)
        self.assertIn('否则只能原样使用', prompt)

    def test_unmapped_master_uses_default_title(self):
        OlivaAIAgent.conf.gConf['masters']['default_title'] = '管理骰主'
        with mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=True):
            identity = OlivaAIAgent.conf.senderIdentity(FakeEvent(), [])
        self.assertEqual('管理骰主', identity['master_title'])

    def test_extracts_all_real_outgoing_message_ids(self):
        result = {
            'active': True,
            'data': {
                'message_id': 'message-1',
                'message_ids': ['message-1', 'message-2'],
            },
        }
        self.assertEqual(
            ['message-1', 'message-2'],
            OlivaAIAgent.ambient._sendResultMessageIds(result),
        )

    def test_exposes_received_and_sent_ids_without_confusing_event_id(self):
        context = OlivaAIAgent.ambient.messageIdContext([
            {
                'nickname': '雨多落为萁',
                'user_id': 'sender-openid',
                'message': '狐啊',
                'message_id': 'received-message',
                'reference_message_id': 'quoted-message',
                'event_id': 'gateway-event',
                'msg_idx': 'REFIDX_CURRENT',
                'ref_msg_idx': 'REFIDX_QUOTED',
            },
            {
                'nickname': None,
                'user_id': None,
                'message': '怎么啦',
                'message_id': 'sent-message-1',
                'message_ids': ['sent-message-1', 'sent-message-2'],
            },
        ])
        self.assertEqual('用户发送', context[0]['方向'])
        self.assertEqual(['received-message'], context[0]['消息ID列表'])
        self.assertEqual('gateway-event', context[0]['事件ID'])
        self.assertEqual('quoted-message', context[0]['引用消息ID'])
        self.assertEqual('REFIDX_CURRENT', context[0]['平台消息索引'])
        self.assertEqual('REFIDX_QUOTED', context[0]['平台引用索引'])
        self.assertEqual('机器人发送', context[1]['方向'])
        self.assertEqual(['sent-message-1', 'sent-message-2'], context[1]['消息ID列表'])
        self.assertNotIn('事件ID', context[1])


if __name__ == '__main__':
    unittest.main()
