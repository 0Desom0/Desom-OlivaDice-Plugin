# -*- encoding: utf-8 -*-

import unittest
from unittest import mock

import OlivOS
import OlivaAIAgent


class FakeSDKEvent:
    pass


FakeSDKEvent.__module__ = 'OlivOS.adapter.qqGuild.qqGuildv2SDK'


class FakeData:
    group_id = 'group-1'
    user_id = 'user-1'
    host_id = 'guild-1'
    extend = {}


class FakeEvent:
    def __init__(self):
        self.platform = {'sdk': 'qqGuildv2_link', 'platform': 'qqGuild', 'model': 'public'}
        self.sdk_event = FakeSDKEvent()
        self.data = FakeData()
        self.log_func = None
        self.bot_info = OlivOS.API.bot_info_T(
            id='bot-1',
            access_token='token',
            platform_sdk='qqGuildv2_link',
            platform_platform='qqGuild',
            platform_model='public',
        )
        self.plugin_info = {'control_queue': None}
        self.indeAPI = OlivOS.qqGuildv2SDK.inde_interface(self, 'qqGuild')

    def echo(self, value):
        return {'active': True, 'data': value}


class FakeProc:
    def get_plugin_list(self):
        return ['OlivaAIAgent', 'OlivaDiceCore']


def make_context():
    event = FakeEvent()
    return {
        'plugin_event': event,
        'Proc': FakeProc(),
        'group_id': event.data.group_id,
        'user_id': event.data.user_id,
        'self_id': 'bot-1',
    }


def make_real_event_context():
    event = object.__new__(OlivOS.API.Event)
    event.platform = {'sdk': 'qqGuildv2_link', 'platform': 'qqGuild', 'model': 'public'}
    event.sdk_event = FakeSDKEvent()
    event.data = FakeData()
    event.bot_info = None
    event.plugin_info = {'control_queue': None}
    event.indeAPI = OlivOS.qqGuildv2SDK.inde_interface(event, 'qqGuild')
    return {
        'plugin_event': event,
        'Proc': FakeProc(),
        'group_id': event.data.group_id,
        'user_id': event.data.user_id,
        'self_id': 'bot-1',
    }


class IntrospectionTest(unittest.TestCase):
    def test_initializes_sdk_catalog_once_in_memory(self):
        ctx = make_context()
        stats = OlivaAIAgent.introspection.initialize(
            ctx['plugin_event'],
            ctx['Proc'],
            force=True,
        )
        self.assertGreater(stats['sdk_modules'], 0)
        self.assertGreater(stats['sdk_interfaces'], 0)
        self.assertGreater(stats['inde_types'], 1)
        with mock.patch.object(
            OlivaAIAgent.introspection,
            '_scan_sdk_roots',
            side_effect=AssertionError('不应重复扫描 SDK'),
        ):
            result = OlivaAIAgent.introspection.discover(ctx, query='markdown')
        self.assertTrue(result['active'])

    def test_discovers_real_event_interfaces(self):
        send_result = OlivaAIAgent.introspection.discover(
            make_real_event_context(),
            query='event.send',
            scope='event',
            limit=10,
        )
        ban_result = OlivaAIAgent.introspection.discover(
            make_real_event_context(),
            query='set_group_ban',
            scope='event',
            limit=10,
        )
        self.assertIn('event.send', [item['path'] for item in send_result['data']['interfaces']])
        self.assertIn('event.set_group_ban', [item['path'] for item in ban_result['data']['interfaces']])

    def test_discovers_qqguild_markdown_from_inde_and_sdk(self):
        result = OlivaAIAgent.introspection.discover(
            make_context(),
            query='markdown',
            scope='all',
            limit=20,
        )
        paths = [item['path'] for item in result['data']['interfaces']]
        self.assertIn('inde.create_markdown_message', paths)
        self.assertIn('sdk.qqGuildv2SDK.event_action.create_markdown_message', paths)
        self.assertEqual(['qqGuildv2SDK'], result['data']['current_sdk_modules'])

    def test_prompt_summary_exposes_current_qqguild_markdown(self):
        summary = OlivaAIAgent.introspection.prompt_interface_summary(make_context())
        self.assertIn('inde.create_markdown_message', summary)
        self.assertIn('chat_type', summary)
        self.assertIn('markdown', summary)

    def test_system_prompt_injects_verified_current_interfaces(self):
        ctx = make_context()
        ctx.update({
            'func_type': 'group_message',
            'platform': 'qqGuild',
            'trace_id': 'trace-markdown-prompt',
        })
        with (
            mock.patch.object(OlivaAIAgent.conf, 'getMasters', return_value=[]),
            mock.patch.object(OlivaAIAgent.conf, 'loadedPlugins', return_value=[]),
        ):
            prompt = OlivaAIAgent.msgReply._buildSystemPrompt(ctx['plugin_event'], ctx, False)
        self.assertIn('当前协议已验证接口', prompt)
        self.assertIn('inde.create_markdown_message', prompt)
        self.assertIn('不得与模型训练知识冲突时擅自否认', prompt)
        self.assertIn('必须输出[OP:at,id=当前发言者user_id]', prompt)

    def test_qqguildv2_platform_prompt_requires_op_at_for_final_reply(self):
        event = mock.Mock()
        event.platform = {'sdk': 'qqGuildv2_link', 'platform': 'qqGuild', 'model': 'public'}
        prompt = OlivaAIAgent.conf.platformBrief(event)
        ctx = {
            'func_type': 'group_message',
            'group_id': 'group-1',
            'self_id': 'bot-1',
            'Proc': None,
            'trace_id': 'trace-mention-prompt',
        }
        with (
            mock.patch.object(OlivaAIAgent.conf, 'getMasters', return_value=[]),
            mock.patch.object(OlivaAIAgent.conf, 'loadedPlugins', return_value=[]),
            mock.patch.object(
                OlivaAIAgent.introspection,
                'prompt_interface_summary',
                return_value='inde.create_markdown_message(...)',
            ),
        ):
            agent_prompt = OlivaAIAgent.msgReply._buildSystemPrompt(event, ctx, False)

        self.assertIn('inde.create_markdown_message', agent_prompt)
        self.assertIn('禁止输出字面“@昵称”', prompt)
        self.assertIn('必须输出[OP:at,id=当前发言者user_id]', prompt)
        self.assertIn('插件会自动通过SDK转成Markdown @', prompt)
        self.assertIn('必须输出[OP:at,id=当前发言者user_id]', agent_prompt)

    def test_invokes_real_sdk_helper(self):
        result = OlivaAIAgent.introspection.invoke(
            make_context(),
            'sdk.qqGuildv2SDK.markdown_tag.cmd_enter',
            kwargs={'text': 'hello'},
        )
        self.assertTrue(result['active'])
        self.assertEqual('<qqbot-cmd-enter text="hello" />', result['data']['result'])

    def test_invokes_current_event_method(self):
        result = OlivaAIAgent.introspection.invoke(
            make_context(),
            'event.echo',
            kwargs={'value': 'ok'},
        )
        self.assertEqual('ok', result['data']['result']['data'])

    def test_discovers_and_invokes_proc_interface(self):
        ctx = make_context()
        found = OlivaAIAgent.introspection.discover(
            ctx,
            query='get_plugin_list',
            scope='proc',
        )
        self.assertEqual('proc.get_plugin_list', found['data']['interfaces'][0]['path'])
        called = OlivaAIAgent.introspection.invoke(ctx, 'proc.get_plugin_list')
        self.assertEqual(['OlivaAIAgent', 'OlivaDiceCore'], called['data']['result'])

    def test_auto_injects_target_event_for_sdk_function(self):
        result = OlivaAIAgent.introspection.invoke(
            make_context(),
            'sdk.qqGuildv2SDK.get_SDK_bot_info_from_Event',
        )
        self.assertTrue(result['active'])
        self.assertIsInstance(result['data']['result'], OlivOS.qqGuildv2SDK.bot_info_T)

    def test_calls_qqguild_markdown_through_current_inde_api(self):
        api_result = {'active': True, 'data': {'message_id': 'message-1'}}
        with mock.patch.object(
            OlivOS.qqGuildv2SDK.event_action,
            '_send_qq_api',
            return_value=api_result,
        ):
            result = OlivaAIAgent.introspection.invoke(
                make_context(),
                'inde.create_markdown_message',
                kwargs={
                    'chat_type': 'guild_channel',
                    'chat_id': 'channel-1',
                    'markdown': {'content': '# hello'},
                },
            )
        self.assertTrue(result['active'])
        self.assertEqual('message-1', result['data']['result']['data']['message_id'])

    def test_normalizes_guessed_markdown_target_to_current_context(self):
        api_result = {'active': True, 'data': {'message_id': 'message-current'}}
        ctx = make_context()
        with mock.patch.object(
            OlivOS.qqGuildv2SDK.event_action,
            '_send_qq_api',
            return_value=api_result,
        ):
            result = OlivaAIAgent.introspection.invoke(
                ctx,
                'inde.create_markdown_message',
                kwargs={
                    'chat_type': 'channel',
                    'chat_id': 'CURRENT_CHANNEL',
                    'markdown': {'content': '# hello'},
                },
            )
        self.assertTrue(result['active'])
        self.assertEqual(
            {'chat_type': 'guild_channel', 'chat_id': 'group-1'},
            result['data']['normalized_context'],
        )

    def test_qq_group_context_is_derived_from_event_flags(self):
        ctx = make_context()
        ctx['plugin_event'].data.extend = {
            'flag_from_qq': True,
            'flag_from_direct': False,
        }
        ctx['plugin_event'].data.host_id = None
        chat_context = OlivaAIAgent.introspection.current_chat_context(ctx)
        self.assertEqual({'chat_type': 'qq_group', 'chat_id': 'group-1'}, chat_context)
        prompt = OlivaAIAgent.introspection.prompt_chat_context_summary(ctx)
        self.assertIn('chat_type=qq_group', prompt)
        self.assertIn('chat_id=group-1', prompt)

    def test_normalizes_markdown_target_for_public_qq_group_event(self):
        api_result = {'active': True, 'data': {'message_id': 'message-qq-group'}}
        ctx = make_context()
        ctx['plugin_event'].data.extend = {
            'flag_from_qq': True,
            'flag_from_direct': False,
        }
        ctx['plugin_event'].data.host_id = None
        with mock.patch.object(
            OlivOS.qqGuildv2SDK.event_action,
            '_send_qq_api',
            return_value=api_result,
        ):
            result = OlivaAIAgent.introspection.invoke(
                ctx,
                'inde.create_markdown_message',
                kwargs={
                    'chat_type': 'guild',
                    'chat_id': 'CURRENT_CHANNEL',
                    'markdown': {'content': '## 我不是串子'},
                },
            )
        self.assertTrue(result['active'])
        self.assertEqual(
            {'chat_type': 'qq_group', 'chat_id': 'group-1'},
            result['data']['normalized_context'],
        )
        self.assertEqual('message-qq-group', result['data']['result']['data']['message_id'])

    def test_rejects_private_and_unknown_paths(self):
        private_result = OlivaAIAgent.introspection.invoke(
            make_context(),
            'sdk.qqGuildv2SDK.event_action._get_local_resource_data',
        )
        unknown_result = OlivaAIAgent.introspection.invoke(make_context(), 'sdk.missing.call')
        self.assertFalse(private_result['active'])
        self.assertFalse(unknown_result['active'])

    def test_generic_call_is_registered_as_dangerous(self):
        tools = OlivaAIAgent.tools.getToolsForRequest(make_context())
        self.assertIn('olivos_discover', [item['name'] for item in tools])
        self.assertIn('olivos_call', [item['name'] for item in tools])
        self.assertTrue(OlivaAIAgent.tools._TOOL_MAP['olivos_call']['danger'])

    def test_handwritten_olivos_tools_are_removed(self):
        tool_names = set(OlivaAIAgent.tools._TOOL_MAP)
        removed_names = {
            'send_msg',
            'delete_msg',
            'get_msg',
            'get_forward_msg',
            'send_forward_msg',
            'set_msg_emoji_like',
            'send_like',
            'group_poke',
            'friend_poke',
            'send_group_sign',
            'list_plugins',
            'get_login_info',
            'get_stranger_info',
            'get_friend_list',
            'get_group_info',
            'get_group_list',
            'get_group_member_info',
            'get_group_member_list',
            'get_host_list',
            'get_host_info',
            'get_status',
            'get_version_info',
            'can_send_image',
            'can_send_record',
            'set_group_kick',
            'set_group_ban',
            'set_group_whole_ban',
            'set_group_admin',
            'set_group_card',
            'set_group_name',
            'set_group_leave',
            'set_group_special_title',
            'set_group_anonymous',
            'set_group_anonymous_ban',
            'set_friend_add_request',
            'set_group_add_request',
            'get_group_system_msg',
            'get_group_ignore_add_request',
            'get_doubt_friends_add_request',
            'set_doubt_friends_add_request',
            'get_essence_msg_list',
            'set_essence_msg',
            'delete_essence_msg',
            'get_group_notice',
            'send_group_notice',
            'del_group_notice',
            'get_group_file_system_info',
            'get_group_root_files',
            'get_group_files_by_folder',
            'get_group_file_url',
            'upload_group_file',
            'upload_private_file',
            'delete_group_file',
            'create_group_file_folder',
            'delete_group_folder',
            'rename_group_file_folder',
            'rename_group_file',
            'set_group_file_forever',
        }
        self.assertFalse(tool_names & removed_names)


if __name__ == '__main__':
    unittest.main()
