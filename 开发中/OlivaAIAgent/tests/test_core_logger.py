# -*- encoding: utf-8 -*-

import copy
import types
import unittest
from unittest import mock

import OlivOS
import OlivaAIAgent


class FakeEvent:
    def __init__(self):
        self.bot_info = types.SimpleNamespace(hash='bot-hash', id='10000', name='AI Bot')
        self.data = types.SimpleNamespace(host_id=None, group_id='20000', user_id='30000', message_id='40000')
        self.platform = {'platform': 'qq', 'sdk': 'onebot'}
        self.replies = []
        self.sends = []

    def reply(self, message, *args, **kwargs):
        self.replies.append(message)
        return {'active': True, 'data': {'message_id': '50000'}}

    def send(self, send_type, target_id, message, host_id=None, *args, **kwargs):
        self.sends.append((send_type, target_id, message, host_id))
        return {'active': True, 'data': {'message_id': '50001'}}


class CoreLoggerTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        self.calls = []
        hook = lambda *args: self.calls.append(args)
        self.core = types.SimpleNamespace(
            crossHook=types.SimpleNamespace(dictHookFunc={'msgHook': hook}),
            msgCustom=types.SimpleNamespace(dictStrCustomDict={
                'bot-hash': {'strBotName': '小芙'},
            }),
        )
        self.core_patch = mock.patch.object(OlivaAIAgent.coreLogger, '_core', return_value=self.core)
        self.core_patch.start()

    def tearDown(self):
        self.core_patch.stop()
        OlivaAIAgent.conf.gConf = self.old_conf

    def test_event_reply_and_send_are_recorded_through_core_hook(self):
        event = FakeEvent()
        OlivaAIAgent.coreLogger.install(event)

        event.reply('普通文本 **Markdown**')
        event.send('group', '20001', '主动文本')

        self.assertEqual(2, len(self.calls))
        self.assertEqual('reply', self.calls[0][1])
        self.assertEqual('普通文本 **Markdown**', self.calls[0][4])
        self.assertEqual('send_group', self.calls[1][1])
        self.assertEqual([None, '20001', None], self.calls[1][3])
        self.assertEqual('主动文本', self.calls[1][4])

    def test_disabled_bridge_does_not_call_core_hook(self):
        OlivaAIAgent.conf.gConf['olivadice_logger']['enabled'] = False
        event = FakeEvent()
        OlivaAIAgent.coreLogger.install(event)

        event.reply('不应记录')

        self.assertEqual([], self.calls)
        self.assertEqual(1, len(event.replies))

    def test_failed_send_is_not_recorded(self):
        event = FakeEvent()
        event.reply = lambda message, *args, **kwargs: {'active': False, 'data': {}}
        OlivaAIAgent.coreLogger.install(event)

        event.reply('发送失败')

        self.assertEqual([], self.calls)

    def test_voice_uses_local_source_text_instead_of_audio_path(self):
        event = FakeEvent()
        OlivaAIAgent.coreLogger.install(event)
        message = OlivOS.messageAPI.Message_templet(
            'olivos_para',
            [OlivOS.messageAPI.PARA.record(file='C:/secret/audio.mp3')],
        )

        with OlivaAIAgent.coreLogger.messageHint('[语音:今晚八点开团]'):
            event.reply(message)

        self.assertEqual('[语音:今晚八点开团]', self.calls[0][4])
        self.assertNotIn('audio.mp3', self.calls[0][4])

    def test_image_uses_cached_content_instead_of_local_path(self):
        event = FakeEvent()
        message = '[OP:image,file=file:///C:/cache/img_demo.jpg]'
        with mock.patch.object(
            OlivaAIAgent.vision,
            'imageCacheMap',
            return_value={'img_demo.jpg': {'content': '一只挥手的猫'}},
        ):
            readable = OlivaAIAgent.coreLogger.readableMessage(event, message)

        self.assertEqual('[图片：一只挥手的猫]', readable)
        self.assertNotIn('C:/cache', readable)

    def test_successful_markdown_tool_call_is_recorded_once(self):
        event = FakeEvent()
        ctx = {'plugin_event': event, 'func_type': 'group_message', 'group_id': '20000'}
        recorded = OlivaAIAgent.coreLogger.recordToolCall(
            ctx,
            'inde.create_markdown_message',
            [],
            {'chat_type': 'qq_group', 'chat_id': '20000', 'markdown': {'content': '# 标题\n正文'}},
            {'active': True, 'data': {}},
        )

        self.assertTrue(recorded)
        self.assertEqual(1, len(self.calls))
        self.assertEqual('send_group', self.calls[0][1])
        self.assertEqual('# 标题\n正文', self.calls[0][4])

    def test_positional_markdown_tool_call_does_not_log_chat_type_as_content(self):
        event = FakeEvent()
        ctx = {'plugin_event': event, 'func_type': 'group_message', 'group_id': '20000'}
        recorded = OlivaAIAgent.coreLogger.recordToolCall(
            ctx,
            'inde.create_markdown_message',
            ['qq_group', '20000', {'content': '# 位置参数标题\n正文'}],
            {},
            {'active': True, 'data': {}},
        )

        self.assertTrue(recorded)
        self.assertEqual('# 位置参数标题\n正文', self.calls[0][4])
        self.assertNotEqual('qq_group', self.calls[0][4])

    def test_named_group_send_uses_explicit_target(self):
        event = FakeEvent()
        ctx = {'plugin_event': event, 'func_type': 'group_message', 'group_id': '20000'}
        recorded = OlivaAIAgent.coreLogger.recordToolCall(
            ctx,
            'sdk.demo.send_group_msg',
            [],
            {'group_id': '28888', 'message': '发往另一个群'},
            {'active': True, 'data': {}},
        )

        self.assertTrue(recorded)
        self.assertEqual([None, '28888', None], self.calls[0][3])
        self.assertEqual('发往另一个群', self.calls[0][4])

    def test_cloned_reminder_event_rebinds_wrappers_to_clone(self):
        source = FakeEvent()
        OlivaAIAgent.coreLogger.install(source)
        clone = copy.copy(source)
        clone.data = copy.copy(source.data)
        clone.replies = []
        clone.sends = []
        clone.data.group_id = '29999'
        OlivaAIAgent.coreLogger.prepareClone(clone)

        clone.send('group', '29999', '提醒')

        self.assertEqual([None, '29999', None], self.calls[0][3])
        self.assertEqual([], source.sends)


if __name__ == '__main__':
    unittest.main()
