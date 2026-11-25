from contextlib import contextmanager
from copy import deepcopy
import importlib
from itertools import product
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import fake_bili

PLUGIN = Path(__file__).resolve().parents[1]
BOT = 'fake-bot'
GROUP = {'sdk': 'onebot', 'platform': 'qq', 'group_id': '123456789', 'chat_type': 'group'}


@contextmanager
def offline_plugin():
    # 不导入真实宿主，模拟装载器调用；未打桩的网络请求立即失败。
    names = ('OlivOS', 'OlivOS.core', 'OlivOS.core.core', 'OlivOS.core.core.scheduleAPI')
    host = {name: ModuleType(name) for name in names}

    def interval(task_id, *, seconds, run_on_start):
        def decorate(callback):
            callback.schedule = (task_id, seconds, run_on_start)
            return callback
        return decorate

    host[names[-1]].interval = interval

    def network_forbidden(*args, **kwargs):
        raise AssertionError('离线测试禁止联网')

    with (patch.dict(sys.modules, host), patch.object(socket.socket, 'connect', network_forbidden),
          patch.object(socket.socket, 'connect_ex', network_forbidden),
          patch.object(socket, 'getaddrinfo', network_forbidden)):
        sys.path.insert(0, str(PLUGIN.parent))
        try:
            yield importlib.import_module(PLUGIN.name)
        finally:
            sys.path.remove(str(PLUGIN.parent))


class FakeEvent:
    def __init__(self, text='', role='member', user_id='10001', *, sdk='onebot', chat_type='group'):
        self.bot_info = SimpleNamespace(hash=BOT, id='99999')
        self.base_info = {'self_id': '99999'}
        self.plugin_info = {'func_type': 'private_message' if chat_type == 'qq_private' else 'group_message'}
        self.platform = {'sdk': sdk, 'platform': 'qq' if sdk == 'onebot' else 'qqGuild'}
        self.data = SimpleNamespace(message=text, group_id='' if chat_type == 'qq_private' else GROUP['group_id'],
                                    user_id=user_id, sender={'role': role}, extend={'chat_type': chat_type})
        self.replies = []

    def reply(self, text):
        self.replies.append(text)

    def get_group_member_info(self, group_id, user_id):
        if group_id != GROUP['group_id'] or user_id != self.data.user_id:
            raise AssertionError('查错了群成员')
        return {'active': True, 'data': {'role': 'admin'}}


class Suite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = self.enterContext(TemporaryDirectory(dir=PLUGIN, prefix='.selftest-'))
        self.enterContext(patch.object(store, 'ROOT', Path(self.temp_dir)))
        self.enterContext(patch.object(store, '_snapshots', {}))
        self.enterContext(patch.object(function, 'names', {}))
        self.enterContext(fake_bili.api_fixtures(bili_api))
        self.proc = SimpleNamespace(log=lambda *_: None, Proc_data={'bot_info_dict': {BOT: None}})

    def command(self, text, role='member', **context):
        event = FakeEvent(text, role, **context)
        message.handle_message(event, self.proc)
        return event.replies

    def test_commands(self):
        for prefix in config.allowed_prefix_list:
            for help_command in ('help', '帮助'):
                with self.subTest(prefix=prefix, command=help_command):
                    replies = self.command(f'[OP:reply,id=42][OP:at,id=99999] {prefix}bili {help_command}')
                    self.assertEqual(len(replies), 1)
                    self.assertIn(f'{prefix}bili up', replies[0])
        self.assertFalse(self.command('bili help'))
        self.assertFalse(self.command('[OP:at,id=12345] .bili help'))
        self.assertFalse(self.command('.bili help', sdk='qqGuildv2_link', chat_type='guild_channel'))
        self.assertIn('只在群里用', self.command('.bili help', sdk='qqGuildv2_link', chat_type='qq_private')[0])
        self.assertEqual(message.parse_action('up live 2 on'), ('live', ('2', 'on'), True))
        self.assertFalse(message.parse_action('live add 2')[2])
        self.assertEqual(message.parse_action('主播添加 2'), ('add', ('2',), True))
        with store.edit_bot(BOT) as settings:
            settings['prefix_list'] = []
        self.assertFalse(self.command('.bili help'))

    def test_binding(self):
        self.assertEqual(function.extract_uid('2'), '2')
        self.assertEqual(function.extract_uid('https://space.bilibili.com/2?tracking=4'), '2')
        self.assertFalse(function.extract_uid('https://live.bilibili.com/1024'))
        self.assertIn('没查到 UID 1024', self.command('.bili up add 1024', 'owner')[0])
        self.assertIn('碧诗（UID 2 / 房间 1024）', self.command('.bili 主播添加 2', 'owner')[0])
        self.assertIn('未开播的主播（UID 3）', self.command('.bili up add 3', 'owner')[0])
        path = Path(self.temp_dir) / 'accounts' / BOT / 'rooms.json'
        payload = json.loads(path.read_text(encoding='utf-8'))
        first = payload['rooms']['2']
        self.assertEqual(first['room_id'], '1024')
        self.assertGreater(first['resolved_at'], 0)
        self.assertEqual(first['dynamic']['last_id'], '197')
        self.assertEqual(first['video']['last_bvid'], 'BV1Fixture')
        self.assertNotRegex(path.read_text(encoding='utf-8'), r'"(?:uname|avatar)"\s*:')
        self.assertEqual(payload['rooms']['3']['room_id'], '')
        sid = function.sid_for(GROUP)
        self.assertEqual(payload['groups'][sid]['push'], dict.fromkeys(config.KINDS, True))
        self.assertIn('订阅成功', self.command('.bili up sub 2')[0])
        self.assertIn('已关闭', self.command('.bili up live 2 off', 'owner')[0])
        self.assertIn('清理了 1 位', self.command('.bili up del 2', 'owner')[0])
        self.assertNotIn(sid, store.rooms(BOT)['rooms']['2']['targets'])

    def test_permissions(self):
        for role, allowed in (('owner', True), ('admin', True), ('member', False)):
            self.assertIs(utils.sender_can_manage(FakeEvent(role=role)), allowed)
        with store.edit_global() as value:
            value['whitelist'] = [{'platform': 'qq', 'user_id': '10010'}]
        self.assertTrue(utils.sender_can_manage(FakeEvent(user_id='10010')))
        self.assertFalse(utils.sender_can_manage(FakeEvent(user_id='10011')))
        self.assertTrue(utils.sender_can_manage(FakeEvent(role='', sdk='qqGuildv2_link', chat_type='qq_group')))
        core = ModuleType('OlivaDiceCore')
        core.userConfig = SimpleNamespace(getUserHash=lambda user_id, label, platform: (user_id, label, platform))
        core.ordinaryInviteManager = SimpleNamespace(
            isInMasterList=lambda bot, hashed: bot == BOT and hashed == ('10020', 'user', 'qq'),
        )
        with patch.dict(sys.modules, {'OlivaDiceCore': core}):
            self.assertTrue(utils.sender_can_manage(FakeEvent(user_id='10020')))
            self.assertFalse(utils.sender_can_manage(FakeEvent(user_id='10021')))

    def test_storage(self):
        store.load_bot(BOT)
        path = Path(self.temp_dir) / 'accounts' / BOT / 'config.json'
        old = path.read_bytes()
        with store.edit_bot(BOT) as value:
            value['poll']['live_seconds'] = 6
        new = path.read_bytes()
        self.assertEqual(path.with_suffix('.json.bak').read_bytes(), old)
        self.assertEqual(json.loads(new)['poll']['live_seconds'], 6)
        with patch.object(store.os, 'replace', side_effect=PermissionError):
            with self.assertRaises(store.StorageError):
                with store.edit_bot(BOT) as value:
                    value['poll']['live_seconds'] = 7
        self.assertEqual(path.read_bytes(), new)
        self.assertFalse(list(path.parent.glob('*.tmp')))
        self.assertEqual(store.bot_config(BOT)['poll']['live_seconds'], 6)
        store._snapshots.clear()
        path.write_bytes(b'{invalid')
        self.assertEqual(store.bot_config(BOT)['poll']['live_seconds'], config.BOT_DEFAULT['poll']['live_seconds'])
        archived, = path.parent.glob('config.json.corrupt-*')
        self.assertEqual(archived.read_bytes(), b'{invalid')
        self.assertIn(archived.name, (path.parent / 'persist_error.log').read_text(encoding='utf-8'))

    def test_live(self):
        old = {'live_status': 0, 'last_area_v2_name': ''}
        active = deepcopy(fake_bili.LIVE)
        self.assertEqual(notify.live_transition(old, active), 'start')
        old.update(live_status=1, last_area_v2_name='旧分区')
        self.assertEqual(notify.live_transition(old, active), 'area')
        old['last_area_v2_name'] = active['area_v2_name']
        self.assertFalse(notify.live_transition(old, active))
        active['live_status'] = 0
        self.assertEqual(notify.live_transition(old, active), 'end')
        old['live_status'] = 0
        self.assertFalse(notify.live_transition(old, active))

    def test_dynamics(self):
        state = {'last_id': '10', 'last_ts': 10}
        recent = fake_bili.dynamic('13', 12)
        items = [recent, fake_bili.dynamic('10', 11), fake_bili.dynamic('11', 20, video=True),
                 fake_bili.dynamic('12', 22, pinned=True), fake_bili.dynamic('9', 8), recent]
        self.assertEqual(notify.new_entries('dynamic', state, items), [recent])
        self.assertFalse(notify.new_entries('dynamic', {'last_id': '13', 'last_ts': 12}, items))

    def test_videos(self):
        state = {'last_bvid': 'BVOld', 'last_ts': 4}
        first, second = fake_bili.video('BVFirst', 5), fake_bili.video('BVSecond', 6)
        items = [second, fake_bili.video('BVOld', 7), first, second, fake_bili.video('BVHistory', 2)]
        self.assertEqual(notify.new_entries('video', state, items), [first, second])
        self.assertFalse(notify.new_entries('video', {'last_bvid': 'BVSecond', 'last_ts': 6}, [second, first]))

    def test_quota(self):
        settings = config.BOT_DEFAULT
        data = {'groups': {}}
        group = function.ensure_group(data, settings, GROUP)
        self.assertFalse(notify.consume_at_all(group, settings, 1, day='2026-01-01'))
        group['at_all'] = True
        self.assertEqual([notify.consume_at_all(group, settings, 1, day='2026-01-01') for _ in range(11)],
                         [True] * 10 + [False])
        self.assertTrue(notify.consume_at_all(group, settings, 1, day='2026-01-02'))
        self.assertEqual(group['at_quota']['used'], 1)
        group = function.ensure_group(data, settings, {**GROUP, 'sdk': 'qqGuildv2_link', 'chat_type': 'qq_group'})
        group['at_all'] = True
        self.assertTrue(notify.consume_at_all(group, settings, 101))
        self.assertFalse(notify.consume_at_all(group, settings, 101))
        self.assertTrue(notify.consume_at_all(group, settings, 102))

    def test_subscribers(self):
        users = [str(1000000000 + index) for index in range(300)]
        mentions = sender.mention_segments('onebot', users + users)
        self.assertEqual(mentions[0], '[OP:at,id=1000000000]')
        self.assertEqual(mentions[-1], '[OP:at,id=1000000299]')
        self.assertEqual(len(mentions), 300)
        segments = ['a' * 3995, *mentions]
        messages = sender.split_segments(segments)
        self.assertGreater(len(messages), 1)
        self.assertTrue(all(len(text) <= 4000 for text in messages))
        self.assertEqual(''.join(messages), ''.join(segments))
        self.assertEqual(sum(text.count('[OP:') for text in messages), sum(text.count(']') for text in messages))
        self.assertEqual(len(sender.mention_segments('qqGuildv2_link', ['abc123', 'abc123'])), 1)

    def test_images(self):
        images = ('', 'invalid', fake_bili.LIVE_URL, fake_bili.VIDEO_URL)
        self.assertEqual(sender.pick_first_image(images), fake_bili.LIVE_URL)
        self.assertEqual(sender.pick_first_image([None, '', 'invalid']), '')
        self.assertEqual(sender.pick_first_image([fake_bili.VIDEO_URL, fake_bili.LIVE_URL]), fake_bili.VIDEO_URL)
        received = []
        event = SimpleNamespace(send=lambda _mode, _group, text, **_flags: received.append(text))
        with patch.object(sender, '_event', return_value=event):
            self.assertTrue(sender.send(self.proc, BOT, GROUP, 'video', {'name': 'UP', 'title': '无图'}))
            self.assertTrue(sender.send(self.proc, BOT, GROUP, 'video', {'name': 'UP', 'title': '有图'},
                                        image=fake_bili.LIVE_URL))
        self.assertNotIn('[OP:image', received[0])
        self.assertIn(f'[OP:image,file={fake_bili.LIVE_URL}]', received[1])

    def test_eligibility(self):
        settings = config.BOT_DEFAULT
        for all_group, all_target, all_room in product((False, True), repeat=3):
            group = {**GROUP, 'push': {'live': all_group}}
            target = {**GROUP, 'live': all_target}
            room = {'live': {'enabled': all_room}}
            self.assertIs(notify.eligible(settings, group, room, target, 'live'), all_group and all_target and all_room)
        target = {**target, 'sdk': 'qqGuildv2_link', 'chat_type': 'guild_channel'}
        self.assertFalse(notify.eligible(settings, group, room, target, 'live'))

    def test_livesocket(self):
        """弹幕包解析：明文/zlib 两种正文、多包拼接、指令白名单、半截包。"""
        import struct
        import zlib

        header = struct.Struct('>IHHII')

        def frame(payload, version, operation=5):
            return header.pack(header.size + len(payload), header.size, version, operation, 1) + payload

        live = frame(json.dumps({'cmd': 'LIVE', 'roomid': 755313}).encode(), 0)
        # 真实协议里 zlib 压的是「完整的内部包序列」，不是裸 JSON。
        inner = frame(json.dumps({'cmd': 'PREPARING', 'roomid': 755313}).encode(), 0)
        end = frame(zlib.compress(inner), 1)
        messages = livesocket.parse_packet(live + end)
        self.assertEqual(len(messages), 2)
        self.assertEqual(livesocket.wanted_events(messages), ['live', 'end'])
        danmu = frame(json.dumps({'cmd': 'DANMU_MSG:4:0:2:2:2:0'}).encode(), 0)
        self.assertEqual(livesocket.wanted_events(livesocket.parse_packet(danmu)), [])
        self.assertEqual(livesocket.parse_packet(live[:-3]), [])

    def test_manifest(self):
        manifest = (PLUGIN / 'app.json').read_bytes()
        self.assertEqual(manifest[:1], b'{')
        payload = json.loads(manifest)
        self.assertEqual(payload['namespace'], PLUGIN.name)
        self.assertNotIn('menu_config', payload)
        html = payload['webui_config'][0]['path']
        self.assertEqual(main.Event.bili_tick.schedule, ('bili_tick', 1, True))
        expected = (
            '__init__.py', 'main.py', 'config.py', 'message.py', 'message_custom.py', 'store.py', 'utils.py',
            'bili_api.py', 'notify.py', 'sender.py', 'function.py', 'webui.py', html,
            'tests/selftest.py', 'tests/fake_bili.py', 'RUN_REPORT.md', 'LICENSE',
        )
        self.assertEqual([name for name in expected if not (PLUGIN / name).is_file()], [])


CASES = (
    ('test_commands', '命令解析'), ('test_binding', 'UID 两级绑定与群订阅'), ('test_permissions', '权限'),
    ('test_storage', '存储原子性与损坏归档'), ('test_live', '直播状态机'), ('test_dynamics', '动态去重及过滤'),
    ('test_videos', '视频去重'), ('test_quota', '@全体配额'), ('test_subscribers', '@订阅者去重与分段'),
    ('test_images', '首图选择'), ('test_eligibility', '三重开关真值表'),
    ('test_livesocket', '弹幕包解析'), ('test_manifest', '清单与文件结构'),
)


if __name__ == '__main__':
    with offline_plugin():
        from BiliBiliNotify import bili_api, config, function, livesocket, main, message, notify, sender, store, utils

        failed = []
        for method, label in CASES:
            result = unittest.TestResult()
            Suite(method).run(result)
            if result.wasSuccessful():
                print(f'[PASS] {label}')
            else:
                print(f'[FAIL] {label}')
                failed.append(label)
                for _, error in result.errors + result.failures:
                    print(error.rstrip())
        if failed:
            print('失败：' + '、'.join(failed))
        else:
            print(f'全部通过 ({len(CASES)}/{len(CASES)})')
        sys.exit(bool(failed))
