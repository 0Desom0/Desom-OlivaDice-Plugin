import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if 'jrlp' not in sys.modules:
    sys.modules['jrlp'] = types.ModuleType('jrlp')
if 'OlivOS' not in sys.modules:
    sys.modules['OlivOS'] = types.ModuleType('OlivOS')
if 'OlivaDiceCore' not in sys.modules:
    sys.modules['OlivaDiceCore'] = types.ModuleType('OlivaDiceCore')

SPEC = importlib.util.spec_from_file_location('jrlp_msgReply_avatar', ROOT / 'msgReply.py')
assert SPEC is not None and SPEC.loader is not None
msgReply = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(msgReply)


def make_event(sdk, appid):
    return SimpleNamespace(
        platform={'sdk': sdk} if sdk is not None else {},
        bot_info=SimpleNamespace(id=appid),
    )


class AvatarUrlTest(unittest.TestCase):
    def test_official_bot_uses_qqapp_url(self):
        """官 bot：AppID + openid 拼 qqapp 头像地址。"""
        event = make_event('qqGuildv2_link', '102080146')
        self.assertEqual(
            msgReply.build_avatar_url(event, 'OPENID_ABC'),
            'https://q.qlogo.cn/qqapp/102080146/OPENID_ABC/0',
        )

    def test_sdk_case_insensitive(self):
        """sdk 名大小写归一化后仍识别为官 bot。"""
        event = make_event('QQGUILDV2_LINK', '102080146')
        self.assertEqual(
            msgReply.build_avatar_url(event, 'OID'),
            'https://q.qlogo.cn/qqapp/102080146/OID/0',
        )

    def test_onebot_uses_legacy_url(self):
        """普通 onebot 平台沿用 QQ 号接口。"""
        event = make_event('onebot', '102080146')
        self.assertEqual(
            msgReply.build_avatar_url(event, '123456'),
            'https://q1.qlogo.cn/g?b=qq&nk=123456&s=640',
        )

    def test_non_numeric_appid_falls_back(self):
        """AppID 非纯数字时回退旧接口，不产出畸形地址。"""
        event = make_event('qqGuildv2_link', 'NOT_NUM')
        self.assertEqual(
            msgReply.build_avatar_url(event, 'OID'),
            'https://q1.qlogo.cn/g?b=qq&nk=OID&s=640',
        )

    def test_missing_appid_falls_back(self):
        """缺少 bot id 时回退旧接口。"""
        event = make_event('qqGuildv2_link', None)
        self.assertEqual(
            msgReply.build_avatar_url(event, 'OID'),
            'https://q1.qlogo.cn/g?b=qq&nk=OID&s=640',
        )

    def test_missing_sdk_falls_back(self):
        """无 platform 数据时回退旧接口。"""
        event = make_event(None, '102080146')
        self.assertEqual(
            msgReply.build_avatar_url(event, 'OID'),
            'https://q1.qlogo.cn/g?b=qq&nk=OID&s=640',
        )

    def test_empty_user_id_falls_back(self):
        """目标 ID 为空时回退旧接口，不拼接空 openid。"""
        event = make_event('qqGuildv2_link', '102080146')
        self.assertEqual(
            msgReply.build_avatar_url(event, ''),
            'https://q1.qlogo.cn/g?b=qq&nk=&s=640',
        )


if __name__ == '__main__':
    unittest.main()
