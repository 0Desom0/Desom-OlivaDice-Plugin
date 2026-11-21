import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
if 'BiliShareInfo' not in sys.modules:
    sys.modules['BiliShareInfo'] = types.ModuleType('BiliShareInfo')

SPEC = importlib.util.spec_from_file_location('bili_share_info_main_qqv2', ROOT / 'main.py')
assert SPEC is not None and SPEC.loader is not None
main = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(main)

IMAGE_MESSAGE = '[OP:image,file=https://i0.hdslb.com/bfs/archive/test.jpg]标题：测试视频'
TEXT_MESSAGE = '这是一条纯文本回复，含普通单词 image 但没有图片消息段'


def _install_olivos_stub(send_side_effect=None):
    """把 OlivOS 换成桩：只暴露 qqGuildv2SDK.event_action 两个方法。"""

    def normalize_outgoing_message(plugin_event, message):
        return SimpleNamespace(active=True, raw=message)

    event_action = SimpleNamespace(
        _normalize_outgoing_message=Mock(side_effect=normalize_outgoing_message),
        send_qq_msg=Mock(return_value={'active': True, 'via': 'send_qq_msg'}),
    )
    if send_side_effect is not None:
        event_action.send_qq_msg.side_effect = send_side_effect
    olivos_mod = types.ModuleType('OlivOS')
    setattr(olivos_mod, 'qqGuildv2SDK', SimpleNamespace(event_action=event_action))
    sys.modules['OlivOS'] = olivos_mod
    return event_action


def _make_event(sdk, func_type='group_message'):
    return SimpleNamespace(
        platform={'sdk': sdk, 'platform': 'qq', 'model': 'default'},
        plugin_info={'func_type': func_type},
        data=SimpleNamespace(message_id='msg-1', group_id='G1', user_id='U1'),
        reply=Mock(return_value={'active': True, 'via': 'plugin_event.reply'}),
        log_func=Mock(),
    )


class QQGuildV2ReplyTest(unittest.TestCase):
    def test_image_reply_uses_plain_send_with_native_quote(self):
        """qqGuildv2 图文回复：强制普通图文（allow_markdown=False），保留原生引用。"""
        event_action = _install_olivos_stub()
        event = _make_event('qqGuildv2_link')

        result = main.reply_message(event, IMAGE_MESSAGE)

        self.assertEqual(result, {'active': True, 'via': 'send_qq_msg'})
        event_action.send_qq_msg.assert_called_once()
        call_args, call_kwargs = event_action.send_qq_msg.call_args
        self.assertIs(call_args[0], event)
        self.assertEqual(call_args[1], 'G1')
        self.assertTrue(call_kwargs.get('allow_markdown') is False)
        self.assertIn('[OP:reply,id=msg-1]', call_args[2].raw)
        self.assertIn('[OP:image', call_args[2].raw)
        event.reply.assert_not_called()
        event.log_func.assert_called_once()

    def test_private_image_reply_uses_plain_send(self):
        """qqGuildv2 私聊图文回复：同样走普通图文发送，并标记 flag_direct。"""
        event_action = _install_olivos_stub()
        event = _make_event('qqGuildv2_link', func_type='private_message')

        main.reply_message(event, IMAGE_MESSAGE)

        call_args, call_kwargs = event_action.send_qq_msg.call_args
        self.assertEqual(call_args[1], 'U1')
        self.assertTrue(call_kwargs.get('flag_direct') is True)
        self.assertTrue(call_kwargs.get('allow_markdown') is False)
        event.reply.assert_not_called()

    def test_plain_text_reply_keeps_standard_path(self):
        """qqGuildv2 纯文本回复不碰特判，仍走 plugin_event.reply。"""
        event_action = _install_olivos_stub()
        event = _make_event('qqGuildv2_link')

        main.reply_message(event, TEXT_MESSAGE)

        event_action.send_qq_msg.assert_not_called()
        event.reply.assert_called_once_with(f'[OP:reply,id=msg-1]{TEXT_MESSAGE}')

    def test_other_platform_keeps_standard_path(self):
        """非 qqGuildv2 平台行为不变：图片消息也走 plugin_event.reply。"""
        event_action = _install_olivos_stub()
        event = _make_event('onebot')

        main.reply_message(event, IMAGE_MESSAGE)

        event_action.send_qq_msg.assert_not_called()
        event.reply.assert_called_once_with(f'[OP:reply,id=msg-1]{IMAGE_MESSAGE}')

    def test_fallback_when_plain_send_raises(self):
        """普通图文发送抛异常时回落 plugin_event.reply，且只发一次。"""
        event_action = _install_olivos_stub(send_side_effect=RuntimeError('boom'))
        event = _make_event('qqGuildv2_link')

        result = main.reply_message(event, IMAGE_MESSAGE)

        self.assertEqual(result, {'active': True, 'via': 'plugin_event.reply'})
        self.assertEqual(event_action.send_qq_msg.call_count, 1)
        event.reply.assert_called_once_with(f'[OP:reply,id=msg-1]{IMAGE_MESSAGE}')
        event.log_func.assert_not_called()


if __name__ == '__main__':
    unittest.main()
