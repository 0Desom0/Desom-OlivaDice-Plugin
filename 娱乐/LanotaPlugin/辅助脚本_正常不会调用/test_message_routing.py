# -*- encoding: utf-8 -*-
"""引用与 At 指名命令的离线路由测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PLUGIN_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_PARENT))

from LanotaPlugin import message  # noqa: E402
from LanotaPlugin import utils  # noqa: E402


def make_event(message_text: str, *, self_id=None, extend=None, group_id='3000', message_id='456'):
    base_info = {} if self_id is None else {'self_id': self_id}
    return SimpleNamespace(
        base_info=base_info,
        bot_info=SimpleNamespace(id='1000', hash='bot-hash'),
        data=SimpleNamespace(
            message=message_text,
            user_id='2000',
            group_id=group_id,
            message_id=message_id,
            sender={'name': 'Tester'},
            extend=extend or {},
        ),
        platform={'platform': 'qq'},
    )


class MessageRoutingTest(unittest.TestCase):
    def assert_help_call_count(self, message_text: str, expected_count: int, **event_kwargs) -> None:
        event = make_event(message_text, **event_kwargs)
        help_handler = Mock()
        with (
            patch.object(message.utils, 'initialize_plugin'),
            patch.object(message.utils, 'check_core_group_enable', return_value=True),
            patch.object(message.utils, 'load_bot_config', return_value={'bot_enable_switch': True}),
            patch.object(message.utils, 'load_global_config', return_value={'global_enable_switch': True}),
            patch.object(message.utils, 'is_group_disabled', return_value=False),
            patch.dict(message.command_handler_dict, {'help': help_handler}),
        ):
            message.handle_message(event, object())
        self.assertEqual(help_handler.call_count, expected_count)

    def test_plain_help_responds(self):
        self.assert_help_call_count('/la help', 1)

    def test_at_current_bot_falls_back_to_bot_info_id(self):
        self.assert_help_call_count('[OP:at,id=1000] /la help', 1)

    def test_at_other_user_does_not_respond(self):
        self.assert_help_call_count('[OP:at,id=9999] /la help', 0)

    def test_at_list_containing_current_bot_responds(self):
        self.assert_help_call_count('[OP:at,id=9999][OP:at,id=1000] /la help', 1)

    def test_sub_self_id_is_recognized(self):
        self.assert_help_call_count(
            '[OP:at,id=sub-bot] /la help',
            1,
            extend={'sub_self_id': 'sub-bot'},
        )

    def test_op_reply_prefix_is_removed(self):
        self.assert_help_call_count('[OP:reply,id=42,seq=7] /la help', 1)

    def test_reply_then_at_current_bot_responds(self):
        self.assert_help_call_count('[OP:reply,id=42][OP:at,id=1000] /la help', 1)

    def test_cq_reply_and_at_are_compatible(self):
        self.assert_help_call_count('[CQ:reply,id=42][CQ:at,qq=1000] /la help', 1)

    def test_get_self_id_uses_nonempty_fallback(self):
        self.assertEqual(utils.get_self_id_from_event(make_event('/la help')), '1000')

    def test_group_reply_quotes_trigger_message(self):
        event = make_event('/la help')
        event.reply = Mock()
        utils.reply_message(event, '帮助内容')
        event.reply.assert_called_once_with('[OP:reply,id=456]帮助内容')

    def test_private_reply_does_not_add_group_quote(self):
        event = make_event('/la help', group_id='')
        event.reply = Mock()
        utils.reply_message(event, '帮助内容')
        event.reply.assert_called_once_with('帮助内容')

    def test_group_image_reply_quotes_trigger_message(self):
        event = make_event('/la b30')
        event.reply = Mock()
        utils.reply_image(event, str(Path(__file__).resolve()), '生成失败')
        reply_content = event.reply.call_args.args[0]
        self.assertTrue(reply_content.startswith('[OP:reply,id=456][OP:image,file='))

    def test_each_group_image_reply_quotes_trigger_message(self):
        event = make_event('/la song test')
        event.reply = Mock()
        image_path = str(Path(__file__).resolve())
        utils.reply_images_with_text(event, [image_path, image_path])
        self.assertEqual(event.reply.call_count, 2)
        for reply_call in event.reply.call_args_list:
            self.assertTrue(reply_call.args[0].startswith('[OP:reply,id=456][OP:image,file='))

    def test_short_text_reply_does_not_generate_image(self):
        event = make_event('/la help')
        with (
            patch.object(message.utils, 'load_bot_config', return_value={'send_as_image': True}),
            patch.object(message.function, 'create_text_image') as create_text_image,
            patch.object(message.utils, 'reply_message') as reply_message,
        ):
            message.reply_text(event, '简短提示')
        create_text_image.assert_not_called()
        reply_message.assert_called_once_with(event, '简短提示')

    def test_long_text_reply_still_generates_image(self):
        event = make_event('/la help')
        long_text = '长内容' * message.config.text_image_min_chars
        with (
            patch.object(message.utils, 'load_bot_config', return_value={'send_as_image': True}),
            patch.object(message, 'is_plain_text_mode', return_value=False),
            patch.object(message.function, 'create_text_image', return_value='help.png') as create_text_image,
            patch.object(message.utils, 'reply_image') as reply_image,
        ):
            message.reply_text(event, long_text)
        create_text_image.assert_called_once()
        reply_image.assert_called_once_with(event, 'help.png', long_text)


if __name__ == '__main__':
    unittest.main()
