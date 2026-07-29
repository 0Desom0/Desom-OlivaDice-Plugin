# -*- encoding: utf-8 -*-

import copy
import tempfile
import unittest

import OlivaAIAgent


class FakeBot:
    hash = 'bot-hash'


class FakeData:
    def __init__(self, message, message_id, extend):
        self.message = message
        self.message_id = message_id
        self.group_id = 'group-1'
        self.user_id = 'user-1'
        self.extend = extend
        self.sender = {'nickname': '测试用户'}


class FakeEvent:
    def __init__(self, sdk, message, message_id, extend, result=None):
        self.platform = {'sdk': sdk, 'platform': 'qq', 'model': 'test'}
        self.plugin_info = {'func_type': 'group_message'}
        self.data = FakeData(message, message_id, extend)
        self.base_info = {'self_id': 'bot-1'}
        self.bot_info = FakeBot()
        self.result = result
        self.get_msg_calls = []

    def get_msg(self, message_id):
        self.get_msg_calls.append(str(message_id))
        return self.result or {'active': False, 'data': {}}


class AdapterMessageIdTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.identifiers._initialized_path = None
        OlivaAIAgent.identifiers._last_cleanup = 0.0

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.identifiers._initialized_path = None
        OlivaAIAgent.identifiers._last_cleanup = 0.0
        self.temp_dir.cleanup()

    def test_milky_reply_is_completed_inside_plugin(self):
        event = FakeEvent(
            'milky_link',
            '[CQ:reply,id=42]继续',
            'group|123456|99',
            {},
        )
        parsed = OlivaAIAgent.msgReply.parseMessage(event)

        self.assertEqual('group|123456|42', parsed['reference_message_id'])
        self.assertEqual(['group|123456|42'], event.get_msg_calls)

    def test_qq_reference_index_survives_plugin_restart(self):
        source_event = FakeEvent(
            'qqGuildv2_link',
            '持久化正文',
            'message-id-1',
            {'qq_msg_idx': 'REFIDX_123', 'event_id': 'event-1'},
        )
        source = OlivaAIAgent.msgReply.parseMessage(source_event)
        OlivaAIAgent.identifiers.recordIncoming(source_event, source)

        # 模拟插件重载：只保留磁盘 SQLite，不保留模块初始化状态。
        OlivaAIAgent.identifiers._initialized_path = None
        quoted_event = FakeEvent(
            'qqGuildv2_link',
            '继续说说',
            'message-id-2',
            {'qq_ref_msg_idx': 'REFIDX_123', 'event_id': 'event-2'},
        )
        parsed = OlivaAIAgent.msgReply.parseMessage(quoted_event)

        self.assertEqual('message-id-1', parsed['reference_message_id'])
        self.assertEqual('插件消息注册表', parsed['quote']['source'])
        self.assertEqual('持久化正文', parsed['quote']['text'])
        self.assertEqual([], quoted_event.get_msg_calls)


if __name__ == '__main__':
    unittest.main()
