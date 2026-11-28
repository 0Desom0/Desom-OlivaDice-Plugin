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


def make_event(
    sdk,
    appid,
    *,
    platform=None,
    bot_hash='bot_hash_1',
    self_id=None,
    user_id='USER_OPENID',
    extend=None,
    proc_data=None,
):
    plat = {}
    if sdk is not None:
        plat['sdk'] = sdk
    if platform is not None:
        plat['platform'] = platform
    return SimpleNamespace(
        platform=plat,
        bot_info=SimpleNamespace(id=appid, hash=bot_hash),
        base_info={'self_id': appid if self_id is None else self_id},
        data=SimpleNamespace(user_id=user_id, extend={} if extend is None else dict(extend)),
        Proc=SimpleNamespace(Proc_data={} if proc_data is None else dict(proc_data)),
    )


class AvatarUrlTest(unittest.TestCase):
    def setUp(self):
        self._orig_qq_sdk = getattr(msgReply.OlivOS, 'qqGuildv2SDK', None)
        if hasattr(msgReply.OlivOS, 'qqGuildv2SDK'):
            delattr(msgReply.OlivOS, 'qqGuildv2SDK')
        msgReply.OlivaDiceCore.msgCustomManager = SimpleNamespace(
            formatReplySTR=lambda tpl, values: tpl.format(**values)
        )

    def tearDown(self):
        if self._orig_qq_sdk is None:
            if hasattr(msgReply.OlivOS, 'qqGuildv2SDK'):
                delattr(msgReply.OlivOS, 'qqGuildv2SDK')
        else:
            msgReply.OlivOS.qqGuildv2SDK = self._orig_qq_sdk

    def test_official_bot_uses_qqapp_url(self):
        """官 bot：AppID + openid 拼 qqapp 头像地址。"""
        event = make_event('qqGuildv2_link', '102080146')
        self.assertEqual(
            msgReply.build_avatar_url(event, 'OPENID_ABC'),
            'https://q.qlogo.cn/qqapp/102080146/OPENID_ABC/0',
        )

    def test_official_bot_self_appid_uses_sub_self_open_id_from_extend(self):
        """官 bot 抽到自己且 user_id 为 AppID 时，用 extend.sub_self_open_id 拼头像。"""
        event = make_event(
            'qqGuildv2_link',
            '102080146',
            platform='qqGuild',
            extend={'sub_self_open_id': 'BOT_OPENID_32HEX', 'sub_self_id': '144115218000'},
        )
        self.assertEqual(
            msgReply.build_avatar_url(event, '102080146'),
            'https://q.qlogo.cn/qqapp/102080146/BOT_OPENID_32HEX/0',
        )
        self.assertEqual(
            msgReply.build_avatar_url(event, '144115218000'),
            'https://q.qlogo.cn/qqapp/102080146/BOT_OPENID_32HEX/0',
        )

    def test_official_bot_self_resolves_from_proc_data_and_sdk_cache(self):
        """extend 缺失 sub_self_open_id 时，依次回退 Proc_data 与 qqGuildv2SDK 缓存。"""
        event_proc = make_event(
            'qqGuildv2_link',
            '102080146',
            platform='qqGuild',
            bot_hash='hash_proc',
            proc_data={'qqGuildv2_self_openid': {'hash_proc': 'OPENID_FROM_PROC'}},
        )
        self.assertEqual(
            msgReply.build_avatar_url(event_proc, '102080146'),
            'https://q.qlogo.cn/qqapp/102080146/OPENID_FROM_PROC/0',
        )

        msgReply.OlivOS.qqGuildv2SDK = SimpleNamespace(
            sdkSubSelfOpenInfo={'hash_sdk': 'OPENID_FROM_SDK'},
            sdkSelfInfo={'hash_avatar': {'avatar': 'https://q.qlogo.cn/bot/custom.png'}},
        )
        event_sdk = make_event('qqGuildv2_link', '102080146', bot_hash='hash_sdk')
        self.assertEqual(
            msgReply.build_avatar_url(event_sdk, '102080146'),
            'https://q.qlogo.cn/qqapp/102080146/OPENID_FROM_SDK/0',
        )

        event_avatar = make_event('qqGuildv2_link', '102080146', bot_hash='hash_avatar')
        self.assertEqual(
            msgReply.build_avatar_url(event_avatar, '102080146'),
            'https://q.qlogo.cn/bot/custom.png',
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

    def test_reply_image_newline_only_on_qqguild(self):
        """qqGuild 图片后补 \\n，普通平台不加 \\n；抽到 bot 自身 OpenID 也触发 jrlpRobot。"""
        custom = {
            'jrlpFirst': 'first:{name}({qq})',
            'jrlpRobot': 'robot:{name}({qq})',
            'jrlpSelf': 'self:{name}({qq})',
            'jrlpRepeat': 'repeat:{name}({qq})',
        }
        sent = []

        def reply_fn(ev, text):
            sent.append(text)

        qq_event = make_event(
            'qqGuildv2_link',
            '102080146',
            platform='qqGuild',
            extend={'sub_self_open_id': 'BOT_OPENID_32HEX'},
        )
        msgReply.reply_today_wife_result(qq_event, reply_fn, custom, {}, '102080146', '小芙')
        self.assertEqual(
            sent[-1],
            '[CQ:image,file=https://q.qlogo.cn/qqapp/102080146/BOT_OPENID_32HEX/0]\nrobot:小芙(102080146)',
        )

        msgReply.reply_today_wife_result(qq_event, reply_fn, custom, {}, 'BOT_OPENID_32HEX', '小芙')
        self.assertEqual(
            sent[-1],
            '[CQ:image,file=https://q.qlogo.cn/qqapp/102080146/BOT_OPENID_32HEX/0]\nrobot:小芙(BOT_OPENID_32HEX)',
        )

        legacy_guild_event = make_event('qqGuild_link', '102080146', platform='qqGuild')
        msgReply.reply_today_wife_result(legacy_guild_event, reply_fn, custom, {}, '123456', '群友')
        self.assertEqual(
            sent[-1],
            '[CQ:image,file=https://q1.qlogo.cn/g?b=qq&nk=123456&s=640]\nfirst:群友(123456)',
        )

        onebot_event = make_event('onebot', '999999', platform='qq', user_id='10001')
        msgReply.reply_today_wife_result(onebot_event, reply_fn, custom, {}, '123456', '群友')
        self.assertEqual(
            sent[-1],
            '[CQ:image,file=https://q1.qlogo.cn/g?b=qq&nk=123456&s=640]first:群友(123456)',
        )

        msgReply.reply_today_wife_result(qq_event, reply_fn, custom, {}, '102080146', '小芙', is_repeat=True)
        self.assertEqual(sent[-1], 'repeat:小芙(102080146)')


if __name__ == '__main__':
    unittest.main()
