# -*- encoding: utf-8 -*-

import os
import tempfile
import unittest

import OlivOS
from OlivOS.adapter.milky import milkySDK
from OlivOS.adapter.qqGuild import qqGuildv2SDK


class AdapterMessageIdTest(unittest.TestCase):
    def test_milky_reply_uses_complete_message_id(self):
        segments = milkySDK.completeRxReplyMessageIds(
            [{'type': 'reply', 'data': {'message_seq': 42}}, {'type': 'text', 'data': {'text': '继续'}}],
            'group',
            123456,
        )
        message = OlivOS.messageAPI.Message_templet('milky_para_rx', segments)
        reply = next(item for item in message.data if isinstance(item, OlivOS.messageAPI.PARA.reply))
        self.assertEqual('group|123456|42', reply.data['id'])

    def test_qqguild_reference_mapping_survives_memory_cache_reset(self):
        old_cwd = os.getcwd()
        old_db = qqGuildv2SDK.sdkPersistentMessageDB
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                qqGuildv2SDK.sdkPersistentMessageDB = None
                qqGuildv2SDK.sdkPersistentMessageLastCleanup = 0.0
                qqGuildv2SDK.sdkRxMessageInfo.clear()
                qqGuildv2SDK.sdkMsgIdxInfo.clear()
                qqGuildv2SDK._register_qq_rx_message(
                    'bot-hash',
                    'qq_group',
                    'group-openid',
                    'message-id-1',
                    content='持久化正文',
                    raw_content='持久化正文',
                    msg_idx='REFIDX_123',
                )
                qqGuildv2SDK.sdkRxMessageInfo.clear()
                qqGuildv2SDK.sdkMsgIdxInfo.clear()
                qqGuildv2SDK.sdkPersistentMessageDB.close()
                qqGuildv2SDK.sdkPersistentMessageDB = None

                self.assertEqual(
                    'message-id-1',
                    qqGuildv2SDK._get_qq_message_id_by_idx(
                        'bot-hash', 'qq_group', 'group-openid', 'REFIDX_123',
                    ),
                )
                restored = qqGuildv2SDK._get_qq_rx_message('bot-hash', 'message-id-1')
                self.assertEqual('持久化正文', restored['message'])
            finally:
                if qqGuildv2SDK.sdkPersistentMessageDB is not None:
                    qqGuildv2SDK.sdkPersistentMessageDB.close()
                qqGuildv2SDK.sdkPersistentMessageDB = old_db
                qqGuildv2SDK.sdkRxMessageInfo.clear()
                qqGuildv2SDK.sdkMsgIdxInfo.clear()
                os.chdir(old_cwd)


if __name__ == '__main__':
    unittest.main()
