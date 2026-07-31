# -*- encoding: utf-8 -*-

import copy
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import OlivaAIAgent


class FakeEvent:
    def __init__(self):
        self.platform = {'sdk': 'onebot', 'platform': 'qq', 'model': 'default'}
        self.plugin_info = {'func_type': 'private_message'}
        self.data = SimpleNamespace(user_id='user-1', group_id=None, message_id='message-1')
        self.base_info = {'self_id': 'bot-1'}
        self.bot_info = SimpleNamespace(hash='bot-hash')
        self.replies = []

    def reply(self, message):
        self.replies.append(message)
        return {'active': True, 'data': {'message_id': 'sent-1'}}


class MainImageSendingTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf

    def test_agent_prompt_allows_main_model_to_choose_cached_image(self):
        event = FakeEvent()
        ctx = {
            'plugin_event': event,
            'Proc': None,
            'trace_id': 'trace-prompt',
            'platform': 'qq',
            'func_type': 'private_message',
            'group_id': None,
            'user_id': 'user-1',
            'self_id': 'bot-1',
        }
        with (
            mock.patch.object(OlivaAIAgent.conf, 'getMasters', return_value=[]),
            mock.patch.object(OlivaAIAgent.conf, 'loadedPlugins', return_value=[]),
            mock.patch.object(OlivaAIAgent.introspection, 'prompt_interface_summary', return_value=''),
        ):
            prompt = OlivaAIAgent.msgReply._buildSystemPrompt(event, ctx, False)

        self.assertIn('【主动发图】', prompt)
        self.assertIn('[发图片:缓存文件名或图片内容/意图关键词]', prompt)
        self.assertIn('自行决定是否发图', prompt)

    def test_agent_dynamic_context_contains_shared_image_candidates(self):
        event = FakeEvent()
        ctx = {
            'plugin_event': event,
            'Proc': None,
            'platform': 'qq',
            'func_type': 'private_message',
            'group_id': None,
            'user_id': 'user-1',
            'self_id': 'bot-1',
        }
        candidates = {
            'fox.gif': {'content': '狐狸捂脸', 'intent': '无奈', 'type': '表情包'},
        }
        with (
            mock.patch.object(OlivaAIAgent.introspection, 'prompt_chat_context_summary', return_value=''),
            mock.patch.object(OlivaAIAgent.vision, 'emojiIntentCache', return_value=candidates),
            mock.patch.object(OlivaAIAgent.memory, 'memFormat', return_value=''),
            mock.patch.object(OlivaAIAgent.knowledge, 'getMem', return_value={'全局': {}}),
            mock.patch.object(OlivaAIAgent.identifiers, 'recent', return_value=[]),
        ):
            context = OlivaAIAgent.msgReply._buildVolatileContext(event, ctx, False)

        self.assertIn('【可发送图片缓存】', context)
        self.assertIn('fox.gif', context)
        self.assertIn('狐狸捂脸', context)

    def test_first_model_reuses_main_model_image_candidates(self):
        candidates = {
            'fox.gif': {'content': '狐狸捂脸', 'intent': '无奈', 'type': '表情包'},
        }
        captured = {}

        def fake_chat(messages, **_kwargs):
            captured['messages'] = messages
            return {'ok': True, 'text': json.dumps({'d': 'NEXT', 'i': '狐狸捂脸'}, ensure_ascii=False)}

        with (
            mock.patch.object(OlivaAIAgent.aiClient, 'chat', side_effect=fake_chat),
            mock.patch.object(OlivaAIAgent.vision, 'emojiIntentCache') as build_candidates,
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
        ):
            decision, image_ref = OlivaAIAgent.ambient._firstThink(
                None,
                'bot-hash',
                'group-1',
                [],
                {},
                'system',
                'bot-1',
                image_candidates=candidates,
            )

        self.assertEqual(('NEXT', '狐狸捂脸'), (decision, image_ref))
        build_candidates.assert_not_called()
        self.assertIn('fox.gif', '\n'.join(item['content'] for item in captured['messages']))

    def test_agent_reply_uses_existing_outgoing_image_translation(self):
        event = FakeEvent()
        image_message = '[OP:image,file=file:///cache/fox.gif]'
        with (
            mock.patch.object(
                OlivaAIAgent.vision,
                'translateOutgoing',
                return_value=[image_message],
            ) as translate,
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '[发图片:狐狸捂脸]',
                safety_check=False,
            )

        translate.assert_called_once_with(
            ['[发图片:狐狸捂脸]'],
            'bot-hash',
            trace_id=None,
        )
        self.assertEqual([image_message], event.replies)

    def test_unmatched_agent_image_reference_is_not_sent(self):
        event = FakeEvent()
        with (
            mock.patch.object(OlivaAIAgent.vision, 'translateOutgoing', return_value=['']),
            mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'),
            mock.patch.object(OlivaAIAgent.conf, 'traceLog'),
        ):
            OlivaAIAgent.msgReply._safeReply(
                event,
                '[发图片:不存在的图片]',
                safety_check=False,
            )

        self.assertEqual([], event.replies)


if __name__ == '__main__':
    unittest.main()
