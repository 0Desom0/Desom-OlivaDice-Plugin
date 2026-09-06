# -*- encoding: utf-8 -*-

import copy
import tempfile
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
        self.old_data_path = OlivaAIAgent.conf.dataPath
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        self.temp_dir = tempfile.TemporaryDirectory()
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.identifiers._initialized_path = None
        OlivaAIAgent.ambient._history.clear()
        self.calls = []

        def hook(*args):
            self.calls.append(args)

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
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.identifiers._initialized_path = None
        OlivaAIAgent.ambient._history.clear()
        self.temp_dir.cleanup()

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

    def test_tool_sent_message_id_is_persisted_for_future_quote_lookup(self):
        event = FakeEvent()
        event.platform = {'platform': 'qqGuild', 'sdk': 'qqGuildv2_link'}
        event.plugin_info = {'func_type': 'group_message'}
        ctx = {
            'plugin_event': event,
            'func_type': 'group_message',
            'platform': 'qqGuild',
            'group_id': '20000',
            '_record_tool_outgoing_history': True,
        }
        result = OlivaAIAgent.coreLogger.recordToolCall(
            ctx,
            'inde.create_markdown_message',
            [],
            {
                'chat_type': 'qq_group',
                'chat_id': '20000',
                'markdown': {'content': 'AI 发出的正文'},
                'quote_msg_id': 'incoming-quote',
            },
            {
                'active': True,
                'data': {
                    'message_id': 'ai-message-1',
                    'results': [{
                        'active': True,
                        'data': {'ext_info': {'ref_idx': 'REFIDX_AI_1'}},
                    }],
                },
            },
        )

        self.assertTrue(result)
        saved = OlivaAIAgent.identifiers.getByMessageId(event, 'ai-message-1')
        self.assertEqual('AI 发出的正文', saved['content'])
        self.assertEqual('incoming-quote', saved['reference_message_id'])
        self.assertEqual('REFIDX_AI_1', saved['message_index'])
        history = OlivaAIAgent.ambient.getHistory('qqGuild', '20000')
        self.assertEqual('ai-message-1', history[-1]['message_id'])
        self.assertEqual(['ai-message-1'], history[-1]['message_ids'])
        self.assertEqual('REFIDX_AI_1', history[-1]['msg_idx'])

    def test_event_reply_tool_call_is_persisted_without_duplicate_logger_hook(self):
        event = FakeEvent()
        ctx = {
            'plugin_event': event,
            'func_type': 'group_message',
            'platform': 'qq',
            'group_id': '20000',
        }
        recorded = OlivaAIAgent.coreLogger.recordToolCall(
            ctx,
            'event.reply',
            [],
            {'message': '直接回复正文'},
            {'active': True, 'data': {'message_id': 'event-reply-1'}},
        )

        self.assertFalse(recorded)
        saved = OlivaAIAgent.identifiers.getByMessageId(event, 'event-reply-1')
        self.assertEqual('直接回复正文', saved['content'])
        self.assertEqual([], self.calls)

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

    def test_async_snapshot_freezes_plugin_context_and_rebinds_event(self):
        source = FakeEvent()
        source.plugin_info = {'name': 'OlivaAIAgent', 'func_type': 'group_message'}
        source.base_info = {'self_id': '10000'}
        source.data.sender = {'name': '当前用户'}
        source.data.extend = {'event_id': 'event-1'}
        source.indeAPI = types.SimpleNamespace(event=source)
        OlivaAIAgent.coreLogger.install(source)

        snapshot = OlivaAIAgent.coreLogger.snapshotEvent(source)
        source.plugin_info['name'] = '最终物语检定规则'
        source.platform['sdk'] = 'changed-sdk'
        source.base_info['self_id'] = 'changed-bot'
        source.data.sender['name'] = 'changed-user'

        self.assertIsNot(snapshot, source)
        self.assertEqual('OlivaAIAgent', snapshot.plugin_info['name'])
        self.assertEqual('onebot', snapshot.platform['sdk'])
        self.assertEqual('10000', snapshot.base_info['self_id'])
        self.assertEqual('当前用户', snapshot.data.sender['name'])
        self.assertIs(snapshot, snapshot.indeAPI.event)

        snapshot.reply('线程回复')

        self.assertIs(snapshot, self.calls[0][0])


    def test_should_block_for_log_on_respects_switch_and_core_log_enable(self):
        event = FakeEvent()
        self.core_patch.stop()
        fake_core = types.SimpleNamespace(
            userConfig=types.SimpleNamespace(
                getUserConfigByKey=mock.Mock(return_value=True),
            )
        )
        with mock.patch.object(OlivaAIAgent.coreLogger, '_coreModule', return_value=fake_core):
            OlivaAIAgent.conf.gConf['olivadice_logger']['block_when_log_on'] = False
            self.assertFalse(OlivaAIAgent.coreLogger.shouldBlockForLogOn(event))

            OlivaAIAgent.conf.gConf['olivadice_logger']['block_when_log_on'] = True
            self.assertTrue(OlivaAIAgent.coreLogger.shouldBlockForLogOn(event))
            fake_core.userConfig.getUserConfigByKey.assert_called()
            kwargs = fake_core.userConfig.getUserConfigByKey.call_args.kwargs
            self.assertEqual('20000', kwargs['userId'])
            self.assertEqual('logEnable', kwargs['userConfigKey'])
            self.assertEqual('bot-hash', kwargs['botHash'])

            event.data.host_id = 'guild-1'
            OlivaAIAgent.coreLogger.shouldBlockForLogOn(event)
            self.assertEqual('guild-1|20000', fake_core.userConfig.getUserConfigByKey.call_args.kwargs['userId'])

        with mock.patch.object(OlivaAIAgent.coreLogger, '_coreModule', return_value=None):
            self.assertFalse(OlivaAIAgent.coreLogger.shouldBlockForLogOn(event))
        self.core_patch.start()

    def test_group_message_skips_ambient_when_log_on_block_enabled(self):
        event = FakeEvent()
        event.data.sender = {'name': '玩家', 'nickname': '玩家'}
        event.base_info = {'self_id': '10000'}
        event.set_block = mock.Mock()
        parsed = {
            'trace_id': 't1',
            'text': '普通聊天',
            'message_id': 'mid-1',
            'at_me': False,
            'reply_to_me': False,
            'reference_message_id': None,
            'event_id': None,
            'msg_idx': None,
            'ref_msg_idx': None,
        }
        proc = types.SimpleNamespace()
        with mock.patch.object(OlivaAIAgent.msgReply, 'parseMessage', return_value=parsed), \
             mock.patch.object(OlivaAIAgent.conf, 'isMaster', return_value=False), \
             mock.patch.object(OlivaAIAgent.msgReply, '_checkGroupUsable', return_value=True), \
             mock.patch.object(OlivaAIAgent.memberDirectory, 'recordIncoming'), \
             mock.patch.object(OlivaAIAgent.identifiers, 'recordIncoming'), \
             mock.patch.object(OlivaAIAgent.msgReply, '_logQuotedMessage'), \
             mock.patch.object(OlivaAIAgent.reminder, 'registerSender'), \
             mock.patch.object(OlivaAIAgent.msgReply, '_seenMessage', return_value=False), \
             mock.patch.object(OlivaAIAgent.msgReply, '_matchPrefix', return_value=None), \
             mock.patch.object(OlivaAIAgent.coreLogger, 'shouldBlockForLogOn', return_value=True), \
             mock.patch.object(OlivaAIAgent.ambient, 'process') as ambient_process, \
             mock.patch.object(OlivaAIAgent.conf, 'traceLog') as trace_log:
            OlivaAIAgent.msgReply._onGroupMessage(event, proc)
        ambient_process.assert_not_called()
        event.set_block.assert_not_called()
        self.assertTrue(any(
            call.args and call.args[1] == 'route.group.blocked_by_log_on'
            for call in trace_log.mock_calls
        ))


if __name__ == '__main__':
    unittest.main()
