import base64
from contextlib import closing, contextmanager
from copy import deepcopy
import importlib
import io
from itertools import product
import json
from pathlib import Path
import socket
import sqlite3
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import warnings

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
    def __init__(self, text='', role='member', user_id='10001', *, sdk='onebot', chat_type='group',
                 bot_role='admin'):
        self.bot_info = SimpleNamespace(hash=BOT, id='99999')
        self.base_info = {'self_id': '99999'}
        self.plugin_info = {'func_type': 'private_message' if chat_type == 'qq_private' else 'group_message'}
        self.platform = {'sdk': sdk, 'platform': 'qq' if sdk == 'onebot' else 'qqGuild'}
        self.data = SimpleNamespace(message=text, group_id='' if chat_type == 'qq_private' else GROUP['group_id'],
                                    user_id=user_id, sender={'role': role}, extend={'chat_type': chat_type})
        self.bot_role = bot_role
        self.replies = []

    def reply(self, text):
        self.replies.append(text)

    def get_group_member_info(self, group_id, user_id, no_cache=False):
        if group_id != GROUP['group_id']:
            raise AssertionError('查错了群成员')
        if user_id == self.base_info['self_id']:
            return {'active': True, 'data': {'role': self.bot_role}}
        if user_id != self.data.user_id:
            raise AssertionError('查错了群成员')
        return {'active': True, 'data': {'role': 'admin'}}


class Suite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = self.enterContext(TemporaryDirectory(dir=PLUGIN, prefix='.selftest-'))
        self.enterContext(patch.object(store, 'ROOT', Path(self.temp_dir)))
        self.enterContext(patch.object(store, '_snapshots', {}))
        self.enterContext(patch.object(function, 'names', {}))
        bili_api.reset_channel_state()
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
                    replies = self.command(f'[OP:reply,id=42][OP:at,id=99999] {prefix}bpush {help_command}')
                    self.assertEqual(len(replies), 1)
                    self.assertIn(f'{prefix}bpush up', replies[0])
        self.assertFalse(self.command(f'{config.COMMAND_NAME} help'))
        self.assertFalse(self.command('[OP:at,id=12345] .bpush help'))
        self.assertFalse(self.command(f'.{config.COMMAND_NAME} help', sdk='qqGuildv2_link', chat_type='guild_channel'))
        private_reply = self.command(f'.{config.COMMAND_NAME} help', sdk='qqGuildv2_link',
                                     chat_type='qq_private')
        self.assertIn('只在群里用', private_reply[0])
        self.assertEqual(message.parse_action('up live 2 on'), ('live', ('2', 'on'), True))
        self.assertFalse(message.parse_action('live add 2')[2])
        self.assertEqual(message.parse_action('主播添加 2'), ('add', ('2',), True))
        with store.edit_bot(BOT) as settings:
            settings['prefix_list'] = []
        self.assertFalse(self.command(f'.{config.COMMAND_NAME} help'))

    def test_binding(self):
        self.assertEqual(function.extract_uid('2'), '2')
        self.assertEqual(function.extract_uid('https://space.bilibili.com/2?tracking=4'), '2')
        self.assertFalse(function.extract_uid('https://live.bilibili.com/1024'))
        self.assertIn('核对主播 UID 1024', self.command(f'.{config.COMMAND_NAME} up add 1024', 'owner')[0])
        self.assertIn('碧诗（UID 2 / 房间 1024）', self.command(f'.{config.COMMAND_NAME} 主播添加 2', 'owner')[0])
        self.assertIn('未开播的主播（UID 3）', self.command(f'.{config.COMMAND_NAME} up add 3', 'owner')[0])
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
        self.assertIn('订阅成功', self.command(f'.{config.COMMAND_NAME} up sub 2')[0])
        self.assertIn('已关闭', self.command(f'.{config.COMMAND_NAME} up live 2 off', 'owner')[0])
        self.assertIn('清理了 1 位', self.command(f'.{config.COMMAND_NAME} up del 2', 'owner')[0])
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
            'capabilities.py', 'render_base.py', 'dynamic_render.py', 'live_stats.py',
            'report_render.py', 'wordcloud_render.py',
            'tests/selftest.py', 'tests/fake_bili.py', 'RUN_REPORT.md', 'LICENSE',
        )
        self.assertEqual([name for name in expected if not (PLUGIN / name).is_file()], [])

    def test_atall_admin_guard(self):
        # 1. OneBot 与 qqGuildv2 的机器人自身管理角色检测
        for role, expected in (('owner', True), ('admin', True), ('sub_admin', True), ('member', False), ('', False)):
            self.assertIs(sender.event_bot_is_group_admin(
                FakeEvent(bot_role=role), GROUP['group_id'], sdk='onebot',
            ), expected)
        broken_event = FakeEvent()
        with patch.object(broken_event, 'get_group_member_info',
                          return_value={'active': False, 'data': {'role': 'admin'}}):
            self.assertFalse(sender.event_bot_is_group_admin(broken_event, GROUP['group_id'], sdk='onebot'))
        with patch.object(broken_event, 'get_group_member_info', side_effect=RuntimeError('boom')):
            self.assertFalse(sender.event_bot_is_group_admin(broken_event, GROUP['group_id'], sdk='onebot'))

        qq_target = {**GROUP, 'sdk': 'qqGuildv2_link', 'platform': 'qqGuild', 'chat_type': 'qq_group'}
        qq_event = FakeEvent(sdk='qqGuildv2_link', chat_type='qq_group')
        for member_role, expected in (('admin', True), ('owner', True), ('member', False), ('', False)):
            qq_sdk = SimpleNamespace(event_action=SimpleNamespace(
                get_qq_group_bot_state=lambda _ev, _gid, r=member_role: {
                    'active': True, 'data': {'response': {'member_role': r}},
                },
            ))
            with patch.object(sender.OlivOS, 'qqGuildv2SDK', qq_sdk, create=True):
                self.assertIs(sender.event_bot_is_group_admin(
                    qq_event, qq_target['group_id'], sdk='qqGuildv2_link',
                ), expected)
        qq_fail = SimpleNamespace(event_action=SimpleNamespace(
            get_qq_group_bot_state=lambda _ev, _gid: {
                'active': False, 'data': {'response': {'member_role': 'admin'}},
            },
        ))
        with patch.object(sender.OlivOS, 'qqGuildv2SDK', qq_fail, create=True):
            self.assertFalse(sender.event_bot_is_group_admin(qq_event, qq_target['group_id'], sdk='qqGuildv2_link'))

        # 2. .bpush atall on：非管理时允许开关打开但附加提示
        ok_reply = self.command(f'.{config.COMMAND_NAME} atall on', 'owner', bot_role='admin')[0]
        self.assertIn('已开启', ok_reply)
        self.assertNotIn('将机器人设为本群管理员', ok_reply)
        warn_reply = self.command(f'.{config.COMMAND_NAME} atall on', 'owner', bot_role='member')[0]
        self.assertIn('已开启', warn_reply)
        self.assertIn('将机器人设为本群管理员', warn_reply)

        # 3. OneBot 推送期校验：非管理时回退跳过 @全体 且不扣配额，其余内容与 @订阅者正常发
        self.assertEqual(function.add_up(BOT, '2', GROUP, '10001')[0], 'added')
        sid = function.sid_for(GROUP)
        self.assertTrue(function.set_subscriber(BOT, '2', sid, '10002', True))
        with store.edit_rooms(BOT) as data:
            data['groups'][sid]['at_all'] = True
        room = store.rooms(BOT)['rooms']['2']
        job = notify._Job(BOT, '2', 'live', room['resolved_at'], time.time() + 1)
        notice = notify._Notice('start', {'name': '碧诗', 'title': '试播', 'area': '虚拟主播',
                                          'time': '2026-11-26 14:00:00', 'link': 'https://live.bilibili.com/1024'},
                                '', live_time=1764000123)
        engine = notify._Engine.__new__(notify._Engine)
        engine.proc = self.proc
        engine.closed = notify.Event()
        engine.write_lock = notify.Lock()
        engine._target = lambda j, s, a, w=False: notify._Engine._target(engine, j, s, a, w)
        engine._claim = lambda j, s, a, n: notify._Engine._claim(engine, j, s, a, n)
        engine._is_mounted = lambda j, r: r is not None

        sent_texts = []
        fake_onebot = SimpleNamespace(
            base_info={'self_id': '99999'},
            bot_info=SimpleNamespace(id='99999'),
            platform={'sdk': 'onebot', 'platform': 'qq'},
            get_group_member_info=lambda group_id, user_id, no_cache=False: {
                'active': True, 'data': {'role': 'member'},
            },
            send=lambda _mode, _gid, text, **_flags: (sent_texts.append(text), {'active': True})[1],
        )
        with patch.object(sender, '_event', return_value=fake_onebot):
            engine._deliver(job, ((sid, room['targets'][sid]['added_at']),), (notice,), False)
        self.assertEqual(len(sent_texts), 1)
        self.assertNotIn('[OP:at,id=all]', sent_texts[0])
        self.assertIn('[OP:at,id=10002]', sent_texts[0])
        self.assertEqual(store.rooms(BOT)['groups'][sid]['at_quota']['used'], 0)
        self.assertTrue(store.rooms(BOT)['groups'][sid]['at_all'])

        # 变为管理员后正常发 @全体 并扣配额
        fake_onebot.get_group_member_info = (
            lambda group_id, user_id, no_cache=False: {'active': True, 'data': {'role': 'admin'}}
        )
        with patch.object(sender, '_event', return_value=fake_onebot):
            engine._deliver(job, ((sid, room['targets'][sid]['added_at']),), (notice,), False)
        self.assertEqual(len(sent_texts), 2)
        self.assertIn('[OP:at,id=all]', sent_texts[1])
        self.assertEqual(store.rooms(BOT)['groups'][sid]['at_quota']['used'], 1)

        # 4. OneBot 发送兜底：带 @全体 被协议端明确拒收时，去掉 @全体 重发
        attempts = []

        def reject_at_all(_mode, _gid, text, **_flags):
            attempts.append(text)
            if '[OP:at,id=all]' in text:
                return {'active': False, 'data': {'retcode': 1200, 'error': 'not admin'}}
            return {'active': True, 'data': {'retcode': 0}}

        fake_onebot.send = reject_at_all
        with patch.object(sender, '_event', return_value=fake_onebot):
            self.assertTrue(sender.send(self.proc, BOT, GROUP, 'start', notice.fields,
                                        at_all=True, subscribers=('10002',)))
        self.assertEqual(len(attempts), 2)
        self.assertIn('[OP:at,id=all]', attempts[0])
        self.assertNotIn('[OP:at,id=all]', attempts[1])
        self.assertIn('[OP:at,id=10002]', attempts[1])

        # 5. qqGuildv2 推送期校验：非管理时跳过 <qqbot-at-everyone /> 且保留 Markdown 卡片
        self.assertEqual(function.add_up(BOT, '2', qq_target, 'open_user')[0], 'added')
        qsid = function.sid_for(qq_target)
        with store.edit_rooms(BOT) as data:
            data['groups'][qsid]['at_all'] = True
        qroom = store.rooms(BOT)['rooms']['2']
        qjob = notify._Job(BOT, '2', 'live', qroom['resolved_at'], time.time() + 1)
        md_sent = []
        fake_qq = SimpleNamespace(
            indeAPI=SimpleNamespace(
                create_markdown_message=lambda **kwargs: (
                    md_sent.append(kwargs['markdown']['content']), {'active': True},
                )[1],
            ),
        )
        qq_member_sdk = SimpleNamespace(event_action=SimpleNamespace(
            get_qq_group_bot_state=lambda _ev, _gid: {'active': True, 'data': {'response': {'member_role': 'member'}}},
        ))
        with patch.object(sender, '_event', return_value=fake_qq), \
                patch.object(sender.OlivOS, 'qqGuildv2SDK', qq_member_sdk, create=True):
            engine._deliver(qjob, ((qsid, qroom['targets'][qsid]['added_at']),), (notice,), False)
        self.assertEqual(len(md_sent), 1)
        self.assertNotIn('<qqbot-at-everyone', md_sent[0])
        self.assertEqual(store.rooms(BOT)['groups'][qsid]['at_quota']['last_at_live_time'], 0)

        qq_admin_sdk = SimpleNamespace(event_action=SimpleNamespace(
            get_qq_group_bot_state=lambda _ev, _gid: {'active': True, 'data': {'response': {'member_role': 'admin'}}},
        ))
        with patch.object(sender, '_event', return_value=fake_qq), \
                patch.object(sender.OlivOS, 'qqGuildv2SDK', qq_admin_sdk, create=True):
            engine._deliver(qjob, ((qsid, qroom['targets'][qsid]['added_at']),), (notice,), False)
        self.assertEqual(len(md_sent), 2)
        self.assertIn('<qqbot-at-everyone />', md_sent[1])
        self.assertEqual(store.rooms(BOT)['groups'][qsid]['at_quota']['last_at_live_time'], 1764000123)

    def test_maintain_does_not_block_tick(self):
        """后台关注流 HTTP 阻塞时不能占用 self.condition，宿主 1s bili_tick 必须立即返回。"""
        import threading

        with store.edit_bot(BOT) as cfg:
            cfg['dynamic_source'] = 'follow'
            cfg['poll']['dynamic_seconds'] = 10
        self.assertEqual(function.add_up(BOT, '2', GROUP, '10001')[0], 'added')

        entered = threading.Event()
        release = threading.Event()

        def slow_follow():
            entered.set()
            release.wait(5)
            return {'2': 999999999}, None

        notify.start(self.proc)
        try:
            engine = notify._engine
            self.assertIsNotNone(engine)
            with patch.object(bili_api, 'follow_max_ids', side_effect=slow_follow):
                worker = threading.Thread(target=engine._sync_follow, args=(time.time(),), daemon=True)
                worker.start()
                self.assertTrue(entered.wait(2))
                # 关注流请求挂起期间，schedule() 与 status() 都必须毫秒级返回。
                began = time.monotonic()
                engine.schedule()
                snap = notify.status(BOT)
                elapsed = time.monotonic() - began
                self.assertLess(elapsed, 0.2)
                self.assertGreaterEqual(snap['ticks'], 1)
                release.set()
                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())
        finally:
            release.set()
            notify.stop(self.proc)


class PhaseOneSuite(Suite):
    def setUp(self):
        super().setUp()
        root = Path(self.temp_dir)
        self.enterContext(patch.object(config, 'DATA_ROOT', root / 'plugin-data'))
        self.enterContext(patch.object(config, 'IMAGE_ROOT', root / 'images' / 'covers'))
        self.proc.Proc_data['bot_info_dict'][BOT] = SimpleNamespace(name='离线测试', platform=GROUP)
        self.sid = function.sid_for(GROUP)

    def web(self, action, **payload):
        return webui.dispatch({'action': action, 'bot_hash': BOT, **payload}, self.proc)['state']

    def test_capabilities_and_webui(self):
        self.assertEqual(config.KINDS, ('live', 'dynamic', 'video'))
        self.assertEqual(set(capabilities.snapshot()['deps']), {'pil', 'qrcode', 'brotli', 'websocket', 'jieba'})
        with patch.object(capabilities, 'import_module', side_effect=ImportError):
            self.assertFalse(capabilities._has_module.__wrapped__('PIL'))

        def load_optional(name):
            warnings.warn('pkg_resources is deprecated as an API', DeprecationWarning, stacklevel=2)
            if name != 'jieba':
                raise ImportError(name)
            return ModuleType(name)

        with patch.object(capabilities, 'import_module', side_effect=load_optional), warnings.catch_warnings():
            warnings.simplefilter('error', DeprecationWarning)
            self.assertTrue(capabilities._has_module.__wrapped__('jieba'))
        self.web('save_group', sid=self.sid)
        with store.edit_rooms(BOT) as data:
            del data['groups'][self.sid]['dynamic_image']
        with patch.object(capabilities, '_has_module', side_effect=lambda name: name == 'brotli'):
            state = self.web('get_state')
            self.assertEqual(state['capabilities']['features'], dict.fromkeys(
                ('dynamic_image', 'live_stats', 'live_report', 'wordcloud', 'qr_login'), False,
            ))
            self.assertEqual(state['capabilities']['segmenter'], 'builtin')
            self.assertIsNone(state['groups'][self.sid]['dynamic_image'])
            self.assertIs(state['bot']['dynamic_image'], False)
            self.assertIs(state['bot']['save_dynamic_image'], False)
            with patch.object(bili_api, 'qr_generate') as request:
                with self.assertRaisesRegex(webui._InvalidRequest, '安装 qrcode 后启用'):
                    self.web('qr_generate')
                request.assert_not_called()
            for payload in ({'dynamic_image': True}, {'save_dynamic_image': True}):
                with self.assertRaisesRegex(webui._InvalidRequest, '安装 Pillow 后启用'):
                    self.web('save_bot', **payload)
            for value in ('on', True):
                with self.assertRaisesRegex(webui._InvalidRequest, '安装 Pillow 后启用'):
                    self.web('save_group', sid=self.sid, dynamic_image=value)
            for value in (1, [], {}):
                with self.assertRaises(webui._InvalidRequest):
                    self.web('save_group', sid=self.sid, dynamic_image=value)
            poll = dict(state['bot']['poll'], max_sockets=32)
            with self.assertRaisesRegex(webui._InvalidRequest, '安装 websocket-client 后启用'):
                self.web('save_bot', poll=poll)
            changed = self.web('save_bot', poll={**poll, 'max_sockets': 0})
            self.assertEqual(changed['bot']['poll']['max_sockets'], 0)
            self.assertIs(changed['bot']['dynamic_image'], False)
            self.assertFalse(message.parse_action('push dynamic_img on')[0])
            self.assertFalse(self.command('.bpush push dynamic_img on', 'owner'))
            self.assertFalse(self.command('.bpush 推送 动态图片 默认', 'owner'))
            self.assertNotIn('dynamic_img', self.command('.bpush help push')[0])
            self.assertNotIn('help stats', self.command('.bpush help')[0])
            self.assertFalse(self.command('.bpush help 统计'))
            self.assertIsNone(self.web('get_state')['groups'][self.sid]['dynamic_image'])

        login = {'url': 'https://www.bilibili.com/', 'qrcode_key': 'offline-fixture'}
        with patch.object(bili_api, 'qr_generate', return_value=(login, None)):
            with patch.object(capabilities, '_has_module', side_effect=lambda name: name == 'qrcode'):
                qr = self.web('qr_generate')['qr']
                self.assertTrue(qr['image'].startswith('data:image/svg+xml;base64,'))
            qr = self.web('qr_generate')['qr']
            self.assertTrue(qr['image'].startswith('data:image/png;base64,'))
        with patch.object(capabilities, '_has_module', return_value=True):
            state = self.web('save_bot', dynamic_image=True, save_dynamic_image=True)
            self.assertIs(state['bot']['dynamic_image'], True)
            self.assertIs(state['bot']['save_dynamic_image'], True)
            self.assertEqual(state['capabilities']['segmenter'], 'jieba')
            for mode, expected in (('on', True), ('off', False), ('inherit', None), (False, False), (None, None)):
                state = self.web('save_group', sid=self.sid, dynamic_image=mode)
                self.assertIs(state['groups'][self.sid]['dynamic_image'], expected)

    def test_help_sections_and_copy(self):
        with patch.object(capabilities, '_has_module', return_value=True):
            main_help, = self.command('.bpush help')
            self.assertEqual([main_help], self.command('.bpush 帮助'))
            self.assertLessEqual(len(main_help.splitlines()), 10)
            self.assertIn('.bpush help sub', main_help)
            self.assertIn('.bpush help push', main_help)
            self.assertIn('.bpush help stats', main_help)
            self.assertIn('.bpush status', self.command('.bpush help 统计')[0])
            for name in ('sub', '订阅'):
                text, = self.command(f'.bpush help {name}')
                self.assertIn('.bpush up add <UID>', text)
                self.assertIn('.bpush up sub <UID>', text)
                self.assertIn('.bpush test <UID>', text)
                self.assertNotIn('dynamic_img', text)
            for name in ('push', '推送'):
                text, = self.command(f'.bpush 帮助 {name}')
                self.assertIn('dynamic_img on|off|auto', text)
                self.assertIn('.bpush atall on|off', text)
            self.assertIn('权限', self.command('.bpush push dynamic_img on')[0])
            for mode, value in (('on', True), ('off', False), ('auto', None), ('on', True), ('默认', None)):
                self.command(f'.bpush push 动态图片 {mode}', 'owner')
                self.assertIs(store.rooms(BOT)['groups'][self.sid]['dynamic_image'], value)

        with self.assertRaisesRegex(webui._InvalidRequest, 'B站个人空间数字 UID'):
            self.web('add_up', uid='https://live.bilibili.com/1024')
        with self.assertRaisesRegex(webui._InvalidRequest, '单个 Cookie 字段值'):
            self.web('save_global', cookie={'sessdata': 'field=a; other=b'})
        for source in ('message_custom.py', 'webui.py', 'webui/index.html'):
            text = (PLUGIN / source).read_text(encoding='utf-8')
            self.assertNotRegex(text, r'不是直播间号|不要粘贴|不用手抄|0\s*=\s*不(?:放宽|重试)')

    def test_dynamic_png(self):
        from PIL import Image

        tmp = Path(self.temp_dir)
        name = 'https://t.bilibili.com/198'
        text = fake_bili.dynamic('198', 1764000123)
        text['modules']['module_dynamic']['desc']['text'] = (
            '开场 #测试话题# @某位主播\n\n' + '完整正文 Python 3.12 与中文混排。' * 70
        )
        pictures = fake_bili.dynamic('199', 1764000124)
        urls = [f'https://i0.hdslb.com/bfs/dynamic/{index}.png' for index in range(10)]
        paths = {}
        colors = []
        for index, url in enumerate(urls):
            path = tmp / f'{index}.png'
            color = (60 + index * 16, 35, 190)
            with Image.new('RGB', (80 + index, 52), color) as img:
                img.save(path)
            paths[url] = path
            colors.append(color)
        pictures['modules']['module_dynamic']['major'] = {'draw': {'items': [{'src': url} for url in urls]}}
        forward = fake_bili.dynamic('200', 1764000125)
        forward.update(type='DYNAMIC_TYPE_FORWARD', orig=pictures)
        opus = bili_api._opus_item({'opus_id': '201', 'content': '降级动态', 'cover': {'url': urls[9]}})
        archived = tmp / 'archive'
        with (patch.object(bili_api, 'download_image', side_effect=paths.get) as download,
              patch.object(bili_api, 'release_image') as release):
            for item, expected in ((text, []), (pictures, urls[:9]), (forward, urls[:9]), (opus, urls[9:])):
                with self.subTest(kind=item['type'], entry=item['id_str']):
                    path = dynamic_render.render_dynamic_card(item, fallback_name='备用昵称', link=name,
                                                              archive_dir=archived)
                    self.assertIsInstance(path, Path)
                    self.assertEqual(path.parent.resolve(), (config.IMAGE_ROOT.parent / 'generated').resolve())
                    with Image.open(path) as img:
                        self.assertEqual(img.format, 'PNG')
                        self.assertEqual(img.width, 880)
                        self.assertLessEqual(img.height, 3400)
                        if item is text:
                            self.assertGreater(img.height, 900)
                        if expected:
                            palette = {color for _, color in img.convert('RGB').getcolors(1_000_000)}
                            self.assertTrue(all(colors[urls.index(url)] in palette for url in expected))
                    self.assertEqual((archived / path.name).read_bytes(), path.read_bytes())
                    self.assertEqual([call.args[0] for call in download.call_args_list], expected)
                    self.assertEqual([call.args[0] for call in release.call_args_list],
                                     [paths[url] for url in expected])
                    download.reset_mock()
                    release.reset_mock()

    def test_local_image_adapters(self):
        root = config.IMAGE_ROOT.parent / 'generated'
        root.mkdir(parents=True)
        path = root / '插画,卡片.png'
        path.write_bytes(b'local fixture')
        link = 'https://t.bilibili.com/198'
        fields = {'name': '碧诗', 'link': link}
        op = SimpleNamespace(send=Mock(return_value={'retcode': 0}))
        with patch.object(sender, '_event', return_value=op):
            self.assertTrue(sender.send(self.proc, BOT, GROUP, 'dynamic', fields, local_image=path))
        self.assertEqual(op.send.call_args.args[2], f'[OP:image,file={path.resolve().as_uri()}]\n【B站动态】\n碧诗\n{link}')

        qq_target = dict(GROUP, sdk='qqGuildv2_link', platform='qqGuild', chat_type='qq_group')
        markdown = Mock(side_effect=({'active': True}, {'active': False}))
        qq = SimpleNamespace(indeAPI=SimpleNamespace(create_markdown_message=markdown))
        para = SimpleNamespace(image=lambda **kw: ('image', kw['file']), text=lambda text: ('text', text))
        api = SimpleNamespace(PARA=para, Message_templet=lambda _, parts: parts)
        plain = Mock(return_value={'active': True})
        sdk = SimpleNamespace(event_action=SimpleNamespace(send_qq_msg=plain))
        with (patch.object(sender, '_event', return_value=qq),
              patch.object(sender.OlivOS, 'messageAPI', api, create=True),
              patch.object(sender.OlivOS, 'qqGuildv2SDK', sdk, create=True)):
            for _ in range(2):
                self.assertTrue(sender.send_local_image(self.proc, BOT, qq_target, path, f'【B站动态】\n碧诗\n{link}'))
            mark = markdown.call_args.kwargs
            self.assertEqual(mark['local_images'], {'cover': f'{config.PLUGIN_NAME}/generated/{path.name}'})
            self.assertIn(link, mark['markdown']['content'])
            self.assertFalse(plain.call_args.kwargs['allow_markdown'])
            parts = plain.call_args.args[2]
            self.assertIn(('image', str(path.resolve())), parts)
            self.assertIn(link, ''.join(text for kind, text in parts if kind == 'text'))

        request = SimpleNamespace(data=SimpleNamespace(), do_api=Mock(side_effect=(
            SimpleNamespace(body='{"status":"failed","retcode":100}'),
            SimpleNamespace(body={'status': 'ok', 'retcode': 0}),
        )))
        v11_event = SimpleNamespace(platform={'model': 'v11'}, plugin_info={'control_queue': object()}, send=Mock())
        sdk_v11 = SimpleNamespace(
            api=SimpleNamespace(send_msg=lambda _: request), get_SDK_bot_info_from_Event=lambda e: e,
            paraMsgMap=(), formatMessage=lambda chunk, mode: chunk,
        )
        adapter = SimpleNamespace(gCheckList=('v11',))
        api.Message_templet = lambda *args: SimpleNamespace(get=lambda _: args[-1])
        with (patch.object(sender, '_event', return_value=v11_event),
              patch.object(sender.OlivOS, 'onebotV11LinkServerAPI', adapter, create=True),
              patch.object(sender.OlivOS, 'onebotSDK', sdk_v11, create=True),
              patch.object(sender.OlivOS, 'messageAPI', api, create=True)):
            self.assertFalse(sender.send_local_image(self.proc, BOT, GROUP, path))
            self.assertTrue(sender.send_local_image(self.proc, BOT, GROUP, path))
        self.assertIn(path.as_uri(), request.data.message)
        v11_event.send.assert_not_called()

        op.send.return_value = None
        with (patch.object(sender, '_local_leases', {}), patch.object(sender.time, 'monotonic', return_value=100),
              patch.object(sender, '_event', return_value=op)):
            self.assertTrue(sender.send_local_image(self.proc, BOT, GROUP, path))
            sender.release_local_image(path)
            self.assertTrue(path.is_file())
            with patch.object(sender.time, 'monotonic', return_value=221):
                sender.reap_local_images()
            self.assertFalse(path.exists())

    def test_dynamic_delivery_reuse_and_fallback(self):
        on, off = (dict(GROUP, group_id=str(number)) for number in (987, 654))
        for target in (GROUP, on, off):
            self.assertEqual(function.add_up(BOT, '2', target)[0], 'added')
        with store.edit_rooms(BOT) as data:
            del data['groups'][self.sid]['dynamic_image']  # 模拟旧 rooms.json。
            data['groups'][function.sid_for(on)]['dynamic_image'] = True
            data['groups'][function.sid_for(off)]['dynamic_image'] = False
        with store.edit_bot(BOT) as settings:
            settings.update(dynamic_image=True, save_dynamic_image=True)
        room = store.rooms(BOT)['rooms']['2']
        job = notify._Job(BOT, '2', 'dynamic', room['resolved_at'], time.time() + 1)
        item = fake_bili.dynamic('198', 1764000123)
        item['modules']['module_dynamic']['major'] = {'draw': {'items': [{'src': fake_bili.VIDEO_URL}]}}
        notices, *_ = notify._record({}, deepcopy(room), notify._Result(job, 0, [item]))
        notice, = notices
        destinations = tuple(notify._targets(room, job))
        engine = notify._Engine.__new__(notify._Engine)
        engine.proc = self.proc
        engine.closed = notify.Event()
        sent = []

        def send(_mode, group_id, text, **kwargs):
            sent.append((group_id, text))
            if group_id == on['group_id'] and 'file=file:' in text:
                return {'status': 'failed', 'retcode': 100}
            return {'status': 'ok', 'retcode': 0}

        event = SimpleNamespace(send=send)
        original = dynamic_render.render_dynamic_card
        with (patch.object(engine.closed, 'wait', return_value=False),
              patch.object(sender, '_event', return_value=event),
              patch.object(bili_api, 'download_image', return_value=None),
              patch.object(dynamic_render, 'render_dynamic_card', wraps=original) as render):
            engine._deliver(job, destinations, (notice,), False)
            render.assert_called_once()
            self.assertIs(render.call_args.args[0], item)
        first, second, fallback, text_group = sent
        self.assertEqual(first[1], second[1])
        self.assertIn('【B站动态】\n碧诗\nhttps://t.bilibili.com/198', first[1])
        self.assertIn(fake_bili.VIDEO_URL, fallback[1])
        self.assertEqual(fallback[1], text_group[1])
        generated = config.IMAGE_ROOT.parent / 'generated'
        self.assertFalse(list(generated.glob('*.png')))
        self.assertEqual(len(list(config.DATA_ROOT.glob('dynamics/*.png'))), 1)

        sent.clear()
        with (patch.object(sender, '_event', return_value=event),
              patch.object(bili_api, 'download_image', return_value=None),
              patch.object(bili_api, 'dynamics', return_value=([item], None))):
            self.assertEqual(notify.test_push(self.proc, BOT, '2', 'dynamic', targets=(GROUP,)), 'ok')
        self.assertEqual(len(sent), 1)
        self.assertIn('file=file:', sent[0][1])
        self.assertIn('[测试] 【B站动态】\n碧诗', sent[0][1])
        self.assertFalse(list(generated.glob('*.png')))

        sent.clear()
        with (patch.object(notify, 'sleep'), patch.object(sender, '_event', return_value=event),
              patch.object(bili_api, 'dynamics', return_value=([item], None)),
              patch.object(dynamic_render, 'render_dynamic_card', side_effect=OSError) as render):
            self.assertEqual(notify.test_push(self.proc, BOT, '2', 'dynamic'), 'ok')
            render.assert_called_once()
        self.assertEqual(len(sent), 3)
        self.assertTrue(all('[测试]' in text and fake_bili.VIDEO_URL in text for _, text in sent))

        with store.edit_bot(BOT) as settings:
            settings['dynamic_image'] = False
        with (patch.object(sender, '_event', return_value=event),
              patch.object(dynamic_render, 'render_dynamic_card') as render):
            self.assertEqual(notify.test_push(self.proc, BOT, '2', 'dynamic', targets=(GROUP,)), 'ok')
            render.assert_not_called()


class ChainSuite(unittest.TestCase):
    """三链条级联取数、冷却去噪、手动自检与 WebUI 脱敏测试（直接测真实 bili_api / webui 逻辑）。"""

    def setUp(self):
        self.temp_dir = self.enterContext(TemporaryDirectory(dir=PLUGIN, prefix='.selftest-chain-'))
        self.enterContext(patch.object(store, 'ROOT', Path(self.temp_dir)))
        self.enterContext(patch.object(store, '_snapshots', {}))
        self.enterContext(patch.object(store, '_recent', store.deque(maxlen=200)))
        self.enterContext(patch.object(function, 'names', {}))
        bili_api.reset_channel_state()
        with bili_api._wbi_lock:
            bili_api._wbi_cache = ('0' * 32, time.monotonic())
        with bili_api._name_lock:
            bili_api._name_cache.clear()
        bot_info = SimpleNamespace(name='测试Bot', id='99999', platform={'sdk': 'onebot', 'platform': 'qq'})
        self.proc = SimpleNamespace(log=lambda *_: None, Proc_data={'bot_info_dict': {BOT: bot_info}})

    def tearDown(self):
        bili_api.reset_channel_state()

    def test_dynamic_three_chain_cascade(self):
        calls = []

        def fake_req(url, *, params=None, **kwargs):
            calls.append((url, params, kwargs.get('quiet')))
            if url == bili_api._DYNAMIC:
                return None, bili_api._RISK
            if url == bili_api._OPUS:
                return {'items': [{'opus_id': '88001', 'content': '兜底动态', 'cover': {'url': ''}}]}, None
            raise AssertionError(f'意外请求 {url}')

        with patch.object(bili_api, 'request_json', side_effect=fake_req):
            # 1. 未登录：链 1（关注流）默认失败且不发请求；链 2 只撞一次 -412（不再重复撞）；链 3 成功。
            items, err = bili_api.dynamics('2')
            self.assertIsNone(err)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]['id_str'], '88001')
            self.assertEqual([c[0] for c in calls], [bili_api._DYNAMIC, bili_api._OPUS])
            self.assertGreater(bili_api._cooldown_left('dynamic', 2), 0)
            self.assertEqual(bili_api.uid_chain('2', 'dynamic')['chain'], 3)
            self.assertEqual(bili_api.channel_health()['dynamic']['overall'], 'degraded')
            log_count = len(store.recent_logs())

            # 2. 冷却期内再次轮询：直接跳过链 2 走链 3，且不再追加重复告警日志。
            calls.clear()
            items2, err2 = bili_api.dynamics('2')
            self.assertIsNone(err2)
            self.assertEqual(len(items2), 1)
            self.assertEqual([c[0] for c in calls], [bili_api._OPUS])
            self.assertEqual(len(store.recent_logs()), log_count)

            # 3. 未登录时 follow_max_ids 也直接守卫返回 _NO_LOGIN，不发网络请求。
            calls.clear()
            ids, ferr = bili_api.follow_max_ids()
            self.assertIsNone(ids)
            self.assertEqual(ferr[0], -101)
            self.assertEqual(calls, [])

        # 4. 登录后：链 1 关注流优先；仅含 DYNAMIC_TYPE_AV 不误判动态命中，也不冷却链 1。
        with store.edit_global() as cfg:
            cfg['cookie']['sessdata'] = 'fake_sess_token'
            cfg['cookie']['bili_jct'] = 'fake_jct_token'
        bili_api.reset_channel_state()
        calls.clear()

        def logged_req(url, *, params=None, **kwargs):
            calls.append((url, params))
            if url == bili_api._FEED_ALL:
                return {'items': [
                    {
                        'id_str': '99001', 'type': 'DYNAMIC_TYPE_AV',
                        'modules': {'module_author': {'mid': 2, 'pub_ts': 100, 'name': '碧诗'}},
                    },
                    {
                        'id_str': '99002', 'type': 'DYNAMIC_TYPE_DRAW',
                        'modules': {'module_author': {'mid': 7, 'pub_ts': 200, 'name': '七号'},
                                    'module_dynamic': {'desc': {'text': '文字动态'}}},
                    },
                ]}, None
            if url == bili_api._DYNAMIC:
                return {'items': [fake_bili.dynamic('99003', 300)]}, None
            raise AssertionError(f'意外请求 {url}')

        with patch.object(bili_api, 'request_json', side_effect=logged_req):
            # UID 2 在关注流里只有投稿动态，动态链 1 应未命中并顺延链 2，且链 1 不挂冷却。
            items, err = bili_api.dynamics('2')
            self.assertIsNone(err)
            self.assertEqual(items[0]['id_str'], '99003')
            self.assertEqual(bili_api._cooldown_left('dynamic', 1), 0)
            self.assertEqual([c[0] for c in calls], [bili_api._FEED_ALL, bili_api._DYNAMIC])

            # UID 7 在关注流里有非视频动态，直接复用 5s 缓存命中链 1，零新请求！
            calls.clear()
            items7, err7 = bili_api.dynamics('7')
            self.assertIsNone(err7)
            self.assertEqual(items7[0]['id_str'], '99002')
            self.assertEqual(calls, [])
            self.assertEqual(bili_api.channel_health()['dynamic']['overall'], 'ok')
            self.assertEqual(bili_api.channel_health()['dynamic']['active_chain'], 1)

    def test_video_three_chain_cascade(self):
        calls = []

        def unauth_req(url, *, params=None, **kwargs):
            calls.append((url, params))
            if url == bili_api._VIDEO:
                return None, bili_api._RISK
            if url == bili_api._CARD:
                return {'card': {'name': '碧诗'}}, None
            if url == bili_api._SEARCH:
                return {'result': [{
                    'mid': 2, 'bvid': 'BVSearch1', 'title': '<em>新视频</em>',
                    'pic': '//i0.hdslb.com/v1.jpg', 'pubdate': 1700000100, 'author': '碧诗',
                }]}, None
            raise AssertionError(f'意外请求 {url}')

        with patch.object(bili_api, 'request_json', side_effect=unauth_req):
            items, err = bili_api.videos('2')
            self.assertIsNone(err)
            self.assertEqual(items[0]['bvid'], 'BVSearch1')
            self.assertEqual(items[0]['pic'], 'https://i0.hdslb.com/v1.jpg')
            self.assertEqual([c[0] for c in calls], [bili_api._VIDEO, bili_api._CARD, bili_api._SEARCH])
            self.assertGreater(bili_api._cooldown_left('video', 2), 0)

            # 冷却期内不再撞 _VIDEO（也不重查已缓存昵称 _CARD），直奔 _SEARCH。
            calls.clear()
            items2, err2 = bili_api.videos('2')
            self.assertIsNone(err2)
            self.assertEqual(items2[0]['bvid'], 'BVSearch1')
            self.assertEqual([c[0] for c in calls], [bili_api._SEARCH])

        # 登录后：链 1 走 feed/all?type=video，把 DYNAMIC_TYPE_AV 归一化为与链 2/3 同构的视频结构。
        with store.edit_global() as cfg:
            cfg['cookie']['sessdata'] = 'fake_sess_token'
            cfg['cookie']['bili_jct'] = 'fake_jct_token'
        bili_api.reset_channel_state()
        calls.clear()

        def logged_video_req(url, *, params=None, **kwargs):
            calls.append((url, params))
            if url == bili_api._FEED_ALL:
                self.assertEqual(params.get('type'), 'video')
                return {'items': [{
                    'id_str': '555', 'type': 'DYNAMIC_TYPE_AV',
                    'modules': {
                        'module_author': {'mid': 2, 'pub_ts': 1700000200, 'name': '碧诗'},
                        'module_dynamic': {'major': {'archive': {
                            'bvid': 'BVFollow1', 'title': '关注流视频', 'cover': '//i0.hdslb.com/f1.jpg',
                        }}},
                    },
                }]}, None
            raise AssertionError(f'意外请求 {url}')

        with patch.object(bili_api, 'request_json', side_effect=logged_video_req):
            items, err = bili_api.videos('2')
            self.assertIsNone(err)
            self.assertEqual(items, [{
                'bvid': 'BVFollow1', 'title': '关注流视频', 'pic': 'https://i0.hdslb.com/f1.jpg',
                'created': 1700000200, 'author': '碧诗',
            }])
            # 与 notify.new_entries 完全同构，切链不会重复推送。
            state = {'last_bvid': 'BVFollow1', 'last_ts': 1700000200}
            self.assertEqual(notify.new_entries('video', state, items), [])

    def test_live_three_chain_and_normalization(self):
        from datetime import datetime, timedelta, timezone

        def live_req(url, *, params=None, **kwargs):
            if url == bili_api._LIVE:
                return None, bili_api._RISK
            if url == bili_api._LIVE_ROOM_INFO:
                return {
                    'uid': 2, 'room_id': 1024, 'live_status': 1,
                    'live_time': '2026-11-27 12:00:00', 'title': '单间测试',
                    'area_name': '虚拟主播', 'user_cover': '//i0.hdslb.com/u.jpg', 'keyframe': '',
                }, None
            if url == bili_api._DANMU:
                return {
                    'token': 'SECRET_DANMU_TOKEN_999',
                    'host_list': [{'host': 'broadcastlv.chat.bilibili.com'}],
                }, None
            raise AssertionError(f'意外请求 {url}')

        with patch.object(bili_api, 'request_json', side_effect=live_req):
            payload, err = bili_api.live_detail('2', room_id='1024')
            self.assertIsNone(err)
            expected_ts = int(datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone(timedelta(hours=8))).timestamp())
            self.assertEqual(payload['live_time'], expected_ts)
            self.assertEqual(payload['area_v2_name'], '虚拟主播')
            self.assertEqual(payload['cover_from_user'], 'https://i0.hdslb.com/u.jpg')
            # 字段已归一化，切换链条不触发虚假分区变更。
            self.assertEqual(notify.live_transition({'live_status': 1, 'last_area_v2_name': '虚拟主播'}, payload), '')

            # 手动完整排查模式：3 条链全部执行，且 token 绝不泄漏。
            full_probe = bili_api.probe_chain('live', '2', mode='full', room_id='1024')
            self.assertTrue(full_probe['success'])
            self.assertEqual(full_probe['overall'], 'degraded')
            self.assertEqual(full_probe['active_chain'], 2)
            self.assertEqual([step['status'] for step in full_probe['steps']], ['fail', 'ok', 'ok'])
            self.assertNotIn('SECRET_DANMU_TOKEN_999', json.dumps(full_probe, ensure_ascii=False))

            # 级联短路模式：链 1 失败、链 2 成功 → 链 3 标 skipped。
            cascade_probe = bili_api.probe_chain('live', '2', mode='cascade', room_id='1024')
            self.assertTrue(cascade_probe['success'])
            self.assertEqual([step['status'] for step in cascade_probe['steps']], ['fail', 'ok', 'skipped'])

        # 链 1 链 2 均失败、仅链 3 弹幕鉴权成功 → 整体仍算成功（降级可用）。
        def only_danmu(url, *, params=None, **kwargs):
            if url in (bili_api._LIVE, bili_api._LIVE_ROOM_INFO):
                return None, bili_api._RISK
            if url == bili_api._DANMU:
                return {'token': 'SECRET_DANMU_TOKEN_999', 'host_list': [{'host': 'h1'}, {'host': 'h2'}]}, None
            raise AssertionError(f'意外请求 {url}')

        with patch.object(bili_api, 'request_json', side_effect=only_danmu):
            p3 = bili_api.probe_chain('live', '2', mode='cascade', room_id='1024')
            self.assertTrue(p3['success'])
            self.assertEqual(p3['active_chain'], 3)
            self.assertEqual([step['status'] for step in p3['steps']], ['fail', 'fail', 'ok'])
            self.assertNotIn('SECRET_DANMU_TOKEN_999', json.dumps(p3, ensure_ascii=False))

    def test_probe_api_webui_and_redaction(self):
        # 写入敏感凭据，验证 probe_api / get_state / 日志全部脱敏且不回显。
        secret_sess = 'SECRET_SESSDATA_XYZ'
        secret_jct = 'SECRET_BILIJCT_XYZ'
        secret_proxy = 'http://127.0.0.1:17899'
        with store.edit_global() as cfg:
            cfg['cookie']['sessdata'] = secret_sess
            cfg['cookie']['bili_jct'] = secret_jct
            cfg['proxy'] = secret_proxy

        # 先让动态链 2 处于 60s 冷却中，测试手动自检 bypass_cooldown=True 测通后自动解除冷却。
        bili_api._set_cooldown('dynamic', 2, 60.0)
        self.assertGreater(bili_api._cooldown_left('dynamic', 2), 0)

        def probe_req(url, *, params=None, **kwargs):
            if url == bili_api._FEED_ALL:
                return {'items': []}, None
            if url == bili_api._DYNAMIC:
                return {'items': [fake_bili.dynamic('701', 1000)]}, None
            raise AssertionError(f'意外请求 {url}')

        with patch.object(bili_api, 'request_json', side_effect=probe_req):
            reply = webui.dispatch({
                'action': 'probe_api', 'bot_hash': BOT, 'uid': '2',
                'kind': 'dynamic', 'mode': 'cascade', 'bypass_cooldown': True,
            }, self.proc)
        self.assertTrue(reply['ok'])
        probe_state = reply['state']
        self.assertTrue(probe_state['success'])
        self.assertEqual(probe_state['overall'], 'degraded')
        self.assertEqual(probe_state['active_chain'], 2)
        self.assertEqual([s['status'] for s in probe_state['steps']], ['fail', 'ok', 'skipped'])
        # 链 2 测通后冷却必须已解除！
        self.assertEqual(bili_api._cooldown_left('dynamic', 2), 0)

        # 非法 mode 参数必须被校验拒绝。
        with self.assertRaises(webui._InvalidRequest):
            webui.dispatch({
                'action': 'probe_api', 'bot_hash': BOT, 'uid': '2',
                'kind': 'dynamic', 'mode': 'invalid_mode',
            }, self.proc)

        # get_state 携带 channels / logged_in，且所有输出和日志不含任何凭据原文。
        full_state = webui.dispatch({'action': 'get_state', 'bot_hash': BOT}, self.proc)
        self.assertTrue(full_state['ok'])
        self.assertTrue(full_state['state']['global']['logged_in'])
        self.assertIn('dynamic', full_state['state']['status']['channels'])
        dumped = json.dumps({'probe': reply, 'state': full_state, 'logs': store.recent_logs()}, ensure_ascii=False)
        for secret in (secret_sess, secret_jct, secret_proxy):
            self.assertNotIn(secret, dumped)

    def test_multi_account_and_follow_guard(self):
        # 1. 构造假头像临时文件（1x1 PNG），测试头像 data URI 转换且不外泄原始 URL。
        png_bytes = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
            b'\x00\x00\x00\x0bIDATx\x9cc`\x00\x02\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        avatar_file = Path(self.temp_dir) / 'avatar.png'
        avatar_file.write_bytes(png_bytes)
        with bili_api._avatar_lock:
            bili_api._avatar_cache.clear()

        face_a = 'https://i0.hdslb.com/bfs/face/acc_a.png'
        face_b = 'https://i0.hdslb.com/bfs/face/acc_b.png'
        profiles = {
            'SESS_A_SECRET': {'uid': '1001', 'uname': '小芙一号', 'face': face_a},
            'SESS_B_SECRET': {'uid': '1002', 'uname': '小芙二号', 'face': face_b},
        }

        def fake_profile(quiet=True):
            sess = store.global_config()['cookie']['sessdata']
            if sess in profiles:
                return dict(profiles[sess]), None
            return None, (-101, '未登录')

        def fake_poll(key):
            if key == 'qr_a':
                url = 'https://passport.bilibili.com/cb?SESSDATA=SESS_A_SECRET&bili_jct=JCT_A_SECRET&DedeUserID=1001'
            else:
                url = 'https://passport.bilibili.com/cb?SESSDATA=SESS_B_SECRET&bili_jct=JCT_B_SECRET&DedeUserID=1002'
            return {'code': 0, 'url': url}, None

        with (patch.object(bili_api, 'qr_poll', side_effect=fake_poll),
              patch.object(bili_api, 'account_profile', side_effect=fake_profile),
              patch.object(bili_api, 'download_image', return_value=avatar_file),
              patch.object(bili_api, 'release_image')):
            # 扫码登录账号 A，再扫码登录账号 B：两个账号都保留，当前激活 B。
            r1 = webui.dispatch({'action': 'qr_poll', 'qrcode_key': 'qr_a'}, self.proc)
            self.assertEqual(r1['state']['qr']['uid'], '1001')
            self.assertEqual(r1['state']['qr']['uname'], '小芙一号')

            r2 = webui.dispatch({'action': 'qr_poll', 'qrcode_key': 'qr_b'}, self.proc)
            self.assertEqual(r2['state']['qr']['uid'], '1002')
            st = webui.dispatch({'action': 'get_state', 'bot_hash': BOT}, self.proc)['state']
            self.assertEqual(st['global']['active_account'], '1002')
            self.assertEqual([a['uid'] for a in st['global']['accounts']], ['1002', '1001'])
            self.assertTrue(st['global']['accounts'][0]['avatar'].startswith('data:image/png;base64,'))

            # 严禁回显任何账号的 SESSDATA / bili_jct 或外部 face URL。
            dumped = json.dumps(st, ensure_ascii=False)
            for secret in ('SESS_A_SECRET', 'JCT_A_SECRET', 'SESS_B_SECRET', 'JCT_B_SECRET', face_a, face_b):
                self.assertNotIn(secret, dumped)

            # 自由切换回账号 A：active cookie 变为 A，且清空 _TICKET 与 _uid_cache。
            with bili_api._TICKET_LOCK:
                bili_api._TICKET.update(value='OLD_TICKET', expires=time.time() + 3600)
            bili_api._uid_cache = (1002, time.monotonic())
            sw = webui.dispatch({'action': 'switch_account', 'bot_hash': BOT, 'uid': '1001'}, self.proc)
            self.assertTrue(sw['ok'])
            self.assertEqual(sw['state']['global']['active_account'], '1001')
            self.assertEqual(store.global_config()['cookie']['sessdata'], 'SESS_A_SECRET')
            self.assertEqual(bili_api._TICKET['value'], '')
            self.assertEqual(bili_api._uid_cache[0], 0)

            # 移除非当前账号 B：A 仍保持生效。
            rm_b = webui.dispatch({'action': 'remove_account', 'bot_hash': BOT, 'uid': '1002'}, self.proc)
            self.assertEqual([a['uid'] for a in rm_b['state']['global']['accounts']], ['1001'])
            self.assertEqual(rm_b['state']['global']['active_account'], '1001')

            # 旧配置兼容：只有 cookie 没有 accounts 时，account_sync 自动识别并入库。
            with store.edit_global() as cfg:
                cfg['accounts'] = []
                cfg['active_account'] = ''
            synced = webui.dispatch({'action': 'account_sync', 'bot_hash': BOT}, self.proc)
            self.assertEqual(synced['state']['global']['active_account'], '1001')
            self.assertEqual(synced['state']['global']['accounts'][0]['uname'], '小芙一号')

            # 移除当前激活账号 A：自动清空登录态。
            rm_a = webui.dispatch({'action': 'remove_account', 'bot_hash': BOT, 'uid': '1001'}, self.proc)
            self.assertFalse(rm_a['state']['global']['logged_in'])
            self.assertEqual(rm_a['state']['global']['accounts'], [])

        # 2. follow_user 遇到 B站 22014（已关注）时按成功返回，不误报失败。
        with store.edit_global() as cfg:
            cfg['cookie']['sessdata'] = 'SESS_A_SECRET'
            cfg['cookie']['bili_jct'] = 'JCT_A_SECRET'

        class FakeResp:
            status_code = 200
            content = b'{"code": 22014}'

            def json(self):
                return {'code': 22014, 'message': '已经关注用户，无法重复关注'}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        class FakeSession:
            trust_env = True

            def post(self, *args, **kwargs):
                return FakeResp()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch.object(bili_api.requests, 'Session', return_value=FakeSession()):
            ok, err = bili_api.follow_user('2394718')
            self.assertTrue(ok)
            self.assertIsNone(err)


class PhaseTwoSuite(Suite):
    def setUp(self):
        super().setUp()
        self.addCleanup(live_stats.close)

    def test_brotli_dispatch_and_fans(self):
        def packet(data, version):
            return struct.pack('>IHHII', 16 + len(data), 16, version, 5, 1) + data

        first = packet(b'{"cmd":"LIVE"}', 0)
        second = packet(b'{"cmd":"DANMU_MSG:4"}', 1)
        valid = packet(livesocket.brotli.compress(first + first + second), 3)
        invalid = packet(b'bad brotli', 3)
        broken_header = struct.pack('>IHHII', 0, 0, 1, 5, 1)
        self.assertFalse(livesocket.parse_packet(broken_header))
        self.assertEqual(livesocket.parse_packet(invalid + valid),
                         [{'cmd': 'LIVE'}, {'cmd': 'LIVE'}, {'cmd': 'DANMU_MSG:4'}])
        with patch.object(livesocket, 'brotli', None):
            self.assertEqual(livesocket.parse_packet(valid + first), [{'cmd': 'LIVE'}])
        received = []

        def on_message(msg):
            received.append(msg['cmd'])
            if len(received) == 1:
                raise RuntimeError

        states, logs = [], []
        watcher = livesocket.LiveWatcher('1024', states.append, logs.append, on_message)
        self.assertEqual(json.loads(watcher._auth_payload('', '', 0))['protover'], 3)
        watcher._dispatch_messages(livesocket.parse_packet(valid))
        self.assertEqual(states, ['live'])
        self.assertEqual(received, ['LIVE', 'LIVE', 'DANMU_MSG:4'])
        self.assertIn('RuntimeError', logs[0])

        with patch.object(bili_api, 'request_json', return_value=({'follower': 1234}, None)) as fetch:
            self.assertEqual(bili_api.fans_count(2), (1234, None))
            self.assertEqual(fetch.call_args.args, (bili_api._RELATION_STAT,))
            self.assertEqual(fetch.call_args.kwargs['params'], {'vmid': '2'})
            self.assertIs(fetch.call_args.kwargs['quiet'], True)
        with patch.object(bili_api, 'request_json', return_value=({'follower': 1.5}, None)):
            self.assertEqual(bili_api.fans_count(2), (None, bili_api._FORMAT))

    def test_stats_events_and_persistence(self):
        sid, resumed = live_stats.on_live_start('2', '1024', start_at=1000, fans_start=100)
        self.assertFalse(resumed)
        viewer = {'uid': 7, 'uname': '小粉丝'}

        def emit(cmd, **data):
            live_stats.record_event('2', '1024', {'cmd': cmd, 'data': data}, now=1061)

        for kind, text in ((0, '晚安'), (1, '[表情]')):
            live_stats.record_event('2', '1024', {
                'cmd': 'DANMU_MSG:4:0:2:2:2:0', 'info': [[0] * 12 + [kind], text, [7, '小粉丝']],
            }, now=1061)
        emit('SEND_GIFT', **viewer, giftId=1, giftName='测试盲盒', num=2, coin_type='gold', total_coin=3503,
             blind_gift={'original_gift_price': 1001})
        emit('COMBO_SEND', **viewer, gift_id=1, total_num=2, combo_total_coin=3503)
        emit('SEND_GIFT', **viewer, giftId=2, giftName='测试付费礼物', num=1, coin_type='gold', total_coin=203)
        emit('SEND_GIFT', **viewer, giftId=3, giftName='测试免费礼物', num=4, coin_type='silver', total_coin=400)
        emit('SUPER_CHAT_MESSAGE', uid=7, user_info={'uname': '小粉丝'}, price=30)
        for _ in range(2):
            emit('GUARD_BUY', **viewer, guard_level=3, start_time=1050, num=2, price=198000)
        # uid=7、uname=小粉丝、msg_type=1，附加未知定长字段检验 wire 跳过规则。
        name = '小粉丝'.encode()
        pb = b'\x08\x07\x12' + bytes([len(name)]) + name + b'\x28\x01\xa5\x06\x01\x02\x03\x04'
        encoded = base64.b64encode(pb).decode()
        self.assertEqual(live_stats.decode_interact_v2(encoded), {'uid': 7, 'uname': '小粉丝', 'msg_type': 1})
        emit('INTERACT_WORD_V2', pb=encoded)
        emit('INTERACT_WORD_V2', pb='!')
        for kind in (1, 2, 3):
            emit('INTERACT_WORD', **viewer, msg_type=kind)
        emit('ENTRY_EFFECT', uid=8, copy_writing='欢迎 <%新观众%> 进入直播间')
        emit('LIKE_INFO_V3_UPDATE', click_count=500)
        emit('LIKE_INFO_V3_CLICK', **viewer, like_count=2)
        emit('LIKE_INFO_V3_UPDATE', click_count=505)
        emit('LIKE_INFO_V3_UPDATE', click_count=504)
        emit('ONLINE_RANK_COUNT', count=55)
        emit('ONLINE_RANK_COUNT', count=40)
        emit('WATCHED_CHANGE', num=100)
        emit('WATCHED_CHANGE', num=87)

        latest = live_stats.room_summary('2', '1024')['session']
        expected = {'danmu': 2, 'text_danmu': 1, 'emoticon_danmu': 1, 'free_count': 4,
                    'gift_gold': 2205, 'sc_gold': 30000, 'guard_gold': 396000, 'gold': 428205,
                    'entry': 3, 'unique_entry': 2, 'follow': 1, 'share': 1, 'like': 5,
                    'online_peak': 55, 'watched_peak': 100}
        self.assertEqual({key: latest[key] for key in expected}, expected)
        detail = live_stats.session_detail(sid)
        self.assertEqual([detail[key] for key in ('box_cost', 'box_payout', 'box_profit')], [2002, 3503, 1501])
        self.assertEqual(detail['guard_levels'], {1: 0, 2: 0, 3: 2})
        self.assertEqual([row['text'] for row in detail['danmu_rows']], ['晚安'])
        self.assertEqual(detail['minutes'], [{'minute': 1020, 'danmu': 2, 'gold': 428205, 'online_peak': 55,
                                              'entry': 3}])
        self.assertEqual(live_stats.room_ranking('2', 'box')[0]['value'], 1501)
        self.assertEqual(live_stats.room_ranking('2', 'like')[0]['value'], 2)
        user = live_stats.user_summary('2', user_name='小粉丝')
        self.assertEqual(user['uid'], '7')
        self.assertEqual(user['ranks']['session']['danmu'], 1)
        live_stats.on_live_end('1024', end_at=1080, grace_seconds=0)
        self.assertEqual(live_stats.finalize_due(now=1081, fans_fetcher=lambda uid: (102, None)), [sid])
        ended = live_stats.room_summary('2')['session']
        self.assertEqual((ended['fans_start'], ended['fans_end'], ended['duration']), (100, 102, 80))
        with closing(sqlite3.connect(store.ROOT / 'stats.db')) as db:
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone(), ('wal',))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM session_danmu').fetchone(), (1,))
        live_stats.cleanup_danmu(30)
        with closing(sqlite3.connect(store.ROOT / 'stats.db')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM session_danmu').fetchone(), (0,))
        self.assertEqual(live_stats.room_summary('2')['total']['danmu'], 2)

    def test_stats_resume_and_scoped_likes(self):
        first, _ = live_stats.on_live_start('2', '1024', start_at=1000)
        live_stats.on_live_end('1024', end_at=1100, grace_seconds=120)
        self.assertEqual(live_stats.room_summary('2')['session']['status'], 'pending_end')
        self.assertEqual(live_stats.finalize_due(now=1219), [])
        self.assertEqual(live_stats.on_live_start('2', '1024', start_at=1219), (first, True))
        self.assertEqual(live_stats.on_live_start('2', '1024', start_at=1219), (first, True))
        self.assertEqual(live_stats.finalize_due(now=1221), [])
        live_stats.on_live_end('1024', end_at=1300, grace_seconds=120)
        second, resumed = live_stats.on_live_start('2', '1024', start_at=1421)
        self.assertFalse(resumed)
        self.assertNotEqual(first, second)
        self.assertEqual(live_stats.finalize_due(now=1422), [first])
        self.assertEqual(live_stats.finalize_due(now=1423), [])
        for count in (505, 507):
            live_stats.record_event('2', '1024', {'cmd': 'LIKE_INFO_V3_UPDATE', 'data': {'click_count': count}},
                                    now=1424)
        summary = live_stats.room_summary('2')
        self.assertEqual(summary['session']['like'], 2)
        self.assertEqual(summary['total']['sessions'], 2)
        live_stats.on_live_end('1024', end_at=1500, grace_seconds=0)
        self.assertEqual(live_stats.finalize_due(now=1501), [second])
        third, resumed = live_stats.on_live_start('2', '1024', start_at=1502)
        self.assertFalse(resumed)
        self.assertNotIn(third, (first, second))
        live_stats.on_live_end('1024', end_at=1503, grace_seconds=0)
        fourth, resumed = live_stats.on_live_start('2', '1024', start_at=1503)
        self.assertFalse(resumed)
        self.assertNotEqual(fourth, third)
        self.assertEqual(live_stats.finalize_due(now=1504), [third])

    def test_stats_background_flush(self):
        live_stats.on_live_start('2', '1024', start_at=1000)
        event = {'cmd': 'DANMU_MSG', 'info': [[0], '批量采集', [7, '观众']]}
        with closing(sqlite3.connect(store.ROOT / 'stats.db')) as reader:
            def wait_count(expected):
                deadline = time.monotonic() + 2
                while True:
                    count, = reader.execute('SELECT COUNT(*) FROM session_danmu').fetchone()
                    if count >= expected or time.monotonic() >= deadline:
                        self.assertEqual(count, expected)
                        return
                    time.sleep(0.01)

            with patch.object(live_stats, '_BATCH_SECONDS', 30):
                for _ in range(50):
                    live_stats.record_event('2', '1024', event, now=1001)
                wait_count(50)
            with patch.object(live_stats, '_BATCH_SECONDS', 0.02):
                live_stats.record_event('2', '1024', event, now=1002)
                wait_count(51)

        live_stats.record_event('3', '1025', event, now=1200, active=True)
        summary = live_stats.room_summary('3')['session']
        self.assertEqual((summary['status'], summary['danmu']), ('live', 1))

    def test_stats_group_commands(self):
        self.command('.bpush up add 2', 'owner')
        live_stats.on_live_start('2', '1024', uname='碧诗')
        live_stats.record_event('2', '1024', {
            'cmd': 'SEND_GIFT',
            'data': {'uid': 7, 'uname': '小粉丝', 'giftId': 1, 'giftName': '礼物',
                     'coin_type': 'gold', 'num': 1, 'total_coin': 1234},
        })
        live_stats.record_event('2', '1024', {'cmd': 'DANMU_MSG', 'info': [[0], '好', [7, '小粉丝']]})
        clock = Mock(return_value=time.monotonic())
        with patch.object(message, 'time', SimpleNamespace(monotonic=clock, time=time.time)):
            self.assertIn('7', self.command('.bpush 绑定 7')[0])
            me, = self.command('.bpush me')
            self.assertIn('小粉丝', me)
            self.assertIn('1.234', me)
            blocked, = self.command('.bpush room', user_id='10003')
            self.assertIn('10', blocked)
            clock.return_value += 10
            self.assertIn('1.234', self.command('.bpush 房间统计')[0])
            clock.return_value += 10
            self.assertIn('小粉丝', self.command('.bpush rank 弹幕')[0])
            self.command('.bpush up add 3', 'owner')
            clock.return_value += 10
            self.assertIn('主播', self.command('.bpush room')[0])
            self.assertIn('1.234', self.command('.bpush room 碧')[0])
            clock.return_value += 10
            self.assertIn('小粉丝', self.command('.bpush rank 弹幕 总榜 2')[0])
            clock.return_value += 10
            self.assertIn('小粉丝', self.command('.bpush 个人统计 小粉丝 2')[0])

            with store.edit_bot(BOT) as settings:
                settings['live_stats']['hide_revenue'] = True
            for command in ('room 2', 'me 7 2'):
                clock.return_value += 10
                reply, = self.command(f'.bpush {command}')
                self.assertNotIn('1.234', reply)
                self.assertNotIn('¥', reply)
            clock.return_value += 10
            self.assertIn('隐私', self.command('.bpush rank 礼物 本场 2')[0])

        with patch.object(capabilities, '_has_module', side_effect=lambda name: name != 'websocket'):
            self.assertNotIn('help stats', self.command('.bpush help')[0])
            for command in ('room 2', 'me 7 2', 'rank 弹幕', '绑定 7', 'help 统计'):
                self.assertIsNone(message.parse_action(command)[0])
                self.assertFalse(self.command(f'.bpush {command}'))

    def test_stats_notify_lifecycle(self):
        second_bot = 'another-bot'
        self.proc.Proc_data['bot_info_dict'][second_bot] = None
        for bot in (BOT, second_bot):
            self.assertEqual(function.add_up(bot, '2', GROUP)[0], 'added')
            with store.edit_rooms(bot) as data:
                data['rooms']['2']['runtime']['live_status'] = 0
        delivered, finalized = [], []
        finished = Event()

        def on_finalized(session_id):
            finalized.append(session_id)
            finished.set()

        notify.start(self.proc, on_session_finalized=on_finalized)
        engine = notify._engine
        try:
            with patch.object(livesocket.LiveWatcher, 'start'):
                engine._sync_watchers()
            watcher, = engine.watchers.values()
            self.assertEqual(watcher.room_id, '1024')
            stamp = int(time.time()) - 300

            def apply(at, live, start_at):
                for bot in (BOT, second_bot):
                    mount = store.rooms(bot)['rooms']['2']['resolved_at']
                    job = notify._Job(bot, '2', 'live', mount, time.time())
                    payload = dict(fake_bili.LIVE, live_status=int(live), live_time=start_at)
                    engine._apply(notify._Result(job, at, payload))

            with patch.object(engine, '_deliver', side_effect=lambda job, _, notices, risk: delivered.extend(
                (job.bot, notice.kind) for notice in notices
            )):
                apply(stamp, True, stamp)
                watcher._dispatch_messages([{'cmd': 'DANMU_MSG', 'info': [[0], '一次', [7, '小粉丝']]}])
                original = live_stats.room_summary('2')['session']
                self.assertEqual(original['danmu'], 1)
                apply(stamp + 10, False, 0)
                apply(stamp + 15, True, stamp + 15)
                self.assertEqual(live_stats.room_summary('2')['session']['id'], original['id'])
                self.assertEqual([bot for bot, kind in delivered if kind == 'start'], [BOT, second_bot])
                apply(stamp + 20, False, 0)
            with patch.object(bili_api, 'fans_count', side_effect=[(100, None), (103, None)]):
                engine._maintain_stats()
            self.assertTrue(finished.wait(3))
            self.assertEqual(finalized, [original['id']])
            ended = live_stats.room_summary('2')['session']
            self.assertEqual((ended['status'], ended['fans_start'], ended['fans_end']), ('ended', 100, 103))
        finally:
            notify.stop(self.proc)

    def test_stats_webui_validation(self):
        stats = {'enabled': True, 'reconnect_grace_seconds': 0, 'query_cooldown_seconds': 0,
                 'danmu_retention_days': 1, 'hide_revenue': True}
        with patch.object(capabilities, '_has_module', return_value=True):
            webui._save_bot({'live_stats': stats}, BOT)
            expected = {**config.BOT_DEFAULT['live_stats'], **stats}
            self.assertEqual(store.bot_config(BOT)['live_stats'], expected)
            with self.assertRaises(webui._InvalidRequest):
                webui._save_bot({'live_stats': dict(stats, danmu_retention_days=0)}, BOT)
        with patch.object(capabilities, '_has_module', side_effect=lambda name: name != 'websocket'):
            with self.assertRaisesRegex(webui._InvalidRequest, '安装 websocket-client 后启用'):
                webui._save_bot({'live_stats': dict(stats, enabled=False), 'enable': False}, BOT)
            self.assertTrue(store.bot_config(BOT)['enable'])
            self.assertEqual(store.bot_config(BOT)['live_stats'], expected)


class PhaseThreeSuite(PhaseOneSuite):
    def setUp(self):
        super().setUp()
        self.addCleanup(live_stats.close)
        self.enterContext(patch.object(message, '_stats_last', {}))
        self.enterContext(patch.object(wordcloud_render, 'jieba', None))

    def session(self, start, duration=None, *, words=None, paid=False, uid='2', room_id='1024', viewer='观众七'):
        session_id, _ = live_stats.on_live_start(uid, room_id, uname='碧诗', title='晨间工坊', area='虚拟主播',
                                                 start_at=start, fans_start=105)
        for index, text in enumerate(words or ()):
            now = start + (5 if index < 3 else min(duration or 360, 340) - 1)
            live_stats.record_event(uid, room_id, {
                'cmd': 'DANMU_MSG', 'info': [[0], text, [index % 2 + 7, viewer]],
            }, now=now)
        if paid:
            def emit(cmd, **attrs):
                event = {'cmd': cmd, 'data': {'uid': 7, 'uname': viewer, **attrs}}
                live_stats.record_event(uid, room_id, event, now=start + 10)

            emit('SEND_GIFT', giftId=1, giftName='妙想火花', num=2, coin_type='gold', total_coin=96300,
                 blind_gift={'original_gift_price': 9900, 'original_gift_name': '星夜盲盒'})
            emit('SEND_GIFT', giftId=2, giftName='羽毛', num=4, coin_type='silver', total_coin=100)
            emit('SUPER_CHAT_MESSAGE', price=30)
            emit('GUARD_BUY', guard_level=3, num=2, total_coin=396000)
            emit('INTERACT_WORD', msg_type=1)
            emit('ONLINE_RANK_COUNT', count=93)
            emit('WATCHED_CHANGE', num=142)
            live_stats.record_event(uid, room_id, {
                'cmd': 'DANMU_MSG', 'info': [[0] * 12 + [1], '[表情]', [8, '观众八']],
            }, now=start + 70)
        if duration is not None:
            live_stats.on_live_end(room_id, end_at=start + duration, grace_seconds=0)
        return session_id

    def png(self, source, *, size=None):
        from PIL import Image

        with Image.open(source) as image:
            self.assertEqual(image.format, 'PNG')
            self.assertEqual(image.width, 960)
            if size is not None:
                self.assertEqual(image.size, size)
            result = image.height
            image.verify()
            return result

    def test_report_png_privacy_and_sparse(self):
        from PIL import ImageDraw

        full = self.session(10_000, 420, words=['奇思妙想'] * 6, paid=True)
        sparse = self.session(11_000, 60, words=['早安'], viewer='观***')
        live_stats.finalize_due(now=12_000, fans_fetcher=lambda _: (109, None))
        actual_text = ImageDraw.ImageDraw.text

        def render(session_id, **kwargs):
            labels = []

            def capture(draw, xy, text, *args, **options):
                labels.append(text)
                return actual_text(draw, xy, text, *args, **options)

            with patch.object(ImageDraw.ImageDraw, 'text', capture):
                path = report_render.render_live_report(live_stats.session_detail(session_id), **kwargs)
            self.assertIsNotNone(path)
            try:
                return self.png(path), ' '.join(labels)
            finally:
                sender.release_local_image(path)

        height, text = render(full)
        for marker in ('碧诗', '已结束', '晨间工坊', '净增粉丝', '弹幕', '峰值', '盲盒', '妙想火花',
                       '醒目留言', '大航海', '观众七'):
            self.assertIn(marker, text)
        self.assertIn('¥', text)
        self.assertNotIn('登录', text)
        private_height, text = render(full, hide_revenue=True)
        for marker in ('¥', '盲盒', '醒目留言', '妙想火花', '礼物贡献榜'):
            self.assertNotIn(marker, text)
        for marker in ('礼物', '大航海', '观众七', '舰长'):
            self.assertIn(marker, text)
        sparse_height, text = render(sparse)
        for marker in ('盲盒', '礼物分析', '醒目留言', '大航海'):
            self.assertNotIn(marker, text)
        self.assertIn('登录', text)
        self.assertLess(sparse_height, private_height)
        self.assertLess(private_height, height)

    def test_wordcloud_engines_and_png(self):
        rows = [{'uid': '7', 'text': '刷屏词'}] * 50
        rows += [{'uid': str(index), 'text': '冰雪列车 [热词系列_赞] https://example.net/path 🙂'}
                 for index in range(8, 16)]
        rows += [{'uid': '8', 'text': '哈哈哈哈 233333 66666 草草草 wwwww 某停用词'}]
        options = {'stopwords': ['某停用词'], 'custom_words': ['冰雪列车', '刷屏词', '某停用词']}
        detail = {'uname': '碧诗', 'start_at': 1000, 'end_at': 1200, 'danmu_rows': rows}
        for engine in ('builtin', 'jieba'):
            with self.subTest(engine=engine):
                tokenizer = None
                if engine == 'jieba':
                    try:
                        with warnings.catch_warnings():
                            warnings.filterwarnings('ignore', message=r'.*pkg_resources.*')
                            tokenizer = importlib.import_module('jieba')
                    except ImportError:
                        # 可选增强库缺席时，离线替身仅提供该库的现有接口。
                        tokenizer = SimpleNamespace(Tokenizer=lambda: SimpleNamespace(
                            add_word=lambda *args, **kw: None, cut=lambda text, **kw: iter(text.split()),
                        ))
                with patch.object(wordcloud_render, 'jieba', tokenizer):
                    terms, analyzed, used = wordcloud_render.extract_terms(rows, **options)
                    self.assertEqual(used, engine)
                    self.assertEqual(analyzed, len(rows))
                    self.assertEqual(terms[0][:2], ('冰雪列车', 8))
                    terms = {word: (raw, score) for word, raw, score in terms}
                    self.assertEqual(terms['刷屏词'][0], 50)
                    self.assertLess(terms['刷屏词'][1], terms['冰雪列车'][1])
                    self.assertGreater(terms['刷屏词'][1], 3)
                    self.assertTrue({'哈哈', '2333', '666', '草', 'www'} <= terms.keys())
                    self.assertFalse({'某停用词', '热词系列', 'example', '🙂', '哈哈哈哈'} & terms.keys())
                    path = wordcloud_render.render_wordcloud(detail, **options)
                    self.assertIsNotNone(path)
                    try:
                        self.png(path, size=(960, 700))
                    finally:
                        sender.release_local_image(path)
        empty = {**detail, 'danmu_rows': [{'uid': '7', 'text': '！！！ [热词系列_赞] https://example.org 🙂'}]}
        self.assertIsNone(wordcloud_render.render_wordcloud(empty))

    def test_auto_images_async_routing_and_archive(self):
        second_bot = 'other-bot'
        self.proc.Proc_data['bot_info_dict'][second_bot] = self.proc.Proc_data['bot_info_dict'][BOT]
        groups = [dict(GROUP, group_id=str(int(GROUP['group_id']) + index)) for index in range(4)]
        for bot, mounts in ((BOT, groups), (second_bot, groups[:1])):
            for group in mounts:
                self.assertEqual(function.add_up(bot, '2', group)[0], 'added')
            with store.edit_bot(bot) as settings:
                settings['send_interval_seconds'] = 0
                settings['poll']['max_sockets'] = 0  # 场次由离线事件写入，维护线程只负责封账。
                if bot == second_bot:
                    settings['live_stats'].update(auto_report=False, auto_wordcloud=False, save_report_image=True)
                else:
                    settings['disabled_group_list'] = [function.sid_for(groups[3])]
        with store.edit_rooms(BOT) as data:
            del data['groups'][self.sid]['report']  # 旧配置继承 Bot 开关。
            data['groups'][function.sid_for(groups[1])]['cloud'] = False
            data['groups'][function.sid_for(groups[2])]['report'] = False
        with store.edit_rooms(second_bot) as data:
            data['groups'][self.sid].update(report=True, cloud=True)

        stamp = int(time.time()) - 1600
        below_minutes = self.session(stamp, 120, words=['冰雪列车'] * 6)
        below_danmu = self.session(stamp + 200, 240, words=['冰雪列车'] * 2)
        qualifies = self.session(stamp + 500, 180, words=['冰雪列车'] * 5)
        render = function.render_session_image
        rendering, resume = Event(), Event()
        rendered, deliveries = [], []

        def gated_render(kind, detail, settings):
            rendered.append((kind, detail['id']))
            rendering.set()
            if not resume.wait(3):
                raise AssertionError('封账维护线程被渲染阻塞')
            return render(kind, detail, settings)

        def deliver(Proc, bot, target, path, caption, *, still_current):
            if not still_current() or not path.is_file():
                return False
            deliveries.append((bot, target['group_id'], caption.partition(' · ')[0], path))
            return True

        notify.start(self.proc)
        engine = notify._engine
        try:
            with (patch.object(bili_api, 'fans_count', return_value=(108, None)),
                  patch.object(bili_api, 'live_detail', return_value=(None, (-1, 'offline'))),
                  patch.object(function, 'render_session_image', side_effect=gated_render),
                  patch.object(sender, 'send_local_image', side_effect=deliver)):
                try:
                    engine._maintain_stats()
                    self.assertTrue(rendering.wait(3))
                    notify.tick(self.proc)
                    self.assertEqual(deliveries, [])
                finally:
                    resume.set()
                with engine.condition:
                    self.assertTrue(engine.condition.wait_for(lambda: not engine.finalizing
                                                              and not engine.finalized_sessions, timeout=5))
                self.assertCountEqual(rendered, [('report', qualifies), ('cloud', qualifies)])
                expected = [(BOT, groups[0]['group_id'], label) for label in ('直播报告', '弹幕词云')]
                expected += [(BOT, groups[1]['group_id'], '直播报告'), (BOT, groups[2]['group_id'], '弹幕词云')]
                expected += [(second_bot, groups[0]['group_id'], label) for label in ('直播报告', '弹幕词云')]
                self.assertCountEqual([item[:3] for item in deliveries], expected)
                paths = {item[3] for item in deliveries}
                self.assertEqual(len(paths), 2)
                self.assertFalse(any(path.exists() for path in paths))
                archive = config.DATA_ROOT / 'reports' / '2'
                self.assertEqual({path.name for path in archive.glob('*.png')}, {path.name for path in paths})
                for path in archive.glob('*.png'):
                    self.png(path)
                self.assertTrue(all(live_stats.session_detail(sid)['status'] == 'ended'
                                    for sid in (below_minutes, below_danmu)))

                with store.edit_bot(BOT) as settings:
                    settings['live_stats'].update(min_report_minutes=0, min_report_danmu=0)
                with store.edit_bot(second_bot) as settings:
                    settings['live_stats'].update(min_report_minutes=0, min_report_danmu=0, hide_revenue=True,
                                                  wordcloud_limit=20)
                deliveries.clear()
                short = self.session(stamp + 1000, 20, words=['冰雪列车'])
                engine._maintain_stats()
                with engine.condition:
                    self.assertTrue(engine.condition.wait_for(lambda: not engine.finalizing
                                                              and not engine.finalized_sessions, timeout=5))
                self.assertCountEqual([item for item in rendered if item[1] == short],
                                      [('report', short), ('cloud', short)] * 2)
                for label in ('直播报告', '弹幕词云'):
                    by_bot = {bot: path for bot, _, title, path in deliveries if title == label}
                    self.assertEqual(set(by_bot), {BOT, second_bot})
                    self.assertNotEqual(by_bot[BOT], by_bot[second_bot])
        finally:
            notify.stop(self.proc)

    def test_image_commands_and_help_gates(self):
        self.command('.bpush up add 2', 'owner')
        self.assertIn('场次', self.command('.bpush report')[0])
        self.session(time.time() - 20)
        self.assertIn('文字弹幕', self.command('.bpush cloud')[0])
        live_stats.record_event('2', '1024', {'cmd': 'DANMU_MSG', 'info': [[0], '冰雪列车', [7, '小粉丝']]})
        clock = Mock(return_value=time.monotonic())
        sent = []

        def send(Proc, bot, target, path, caption):
            sent.append((path, caption, self.png(path)))
            return True

        with (patch.object(sender, 'send_local_image', side_effect=send),
              patch.object(message, 'time', SimpleNamespace(monotonic=clock, time=time.time))):
            self.assertFalse(self.command('.bpush report'))
            self.assertIn('10 秒', self.command('.bpush 词云', user_id='10002')[0])
            clock.return_value += 10
            self.assertFalse(self.command('.bpush cloud 2'))
            clock.return_value += 10
            self.assertFalse(self.command('.bpush 直播报告 2'))
        self.assertEqual([caption for _, caption, _ in sent], ['直播报告 · 碧诗', '弹幕词云 · 碧诗', '直播报告 · 碧诗'])
        self.assertEqual(sent[1][2], 700)
        self.assertFalse(any(path.exists() for path, _, _ in sent))
        self.assertIn('权限', self.command('.bpush push report off')[0])
        for kind, cn in (('report', '直播报告'), ('cloud', '弹幕词云')):
            for command, value in ((f'push {kind} on', True), (f'推送 {cn} off', False), (f'push {kind} auto', None)):
                self.assertIn(cn, self.command(f'.bpush {command}', 'owner')[0])
                self.assertIs(store.rooms(BOT)['groups'][self.sid][kind], value)
        self.assertIn('report [主播]', self.command('.bpush help stats')[0])
        self.assertIn('push cloud', self.command('.bpush help push')[0])
        with patch.object(capabilities, '_has_module', side_effect=lambda name: name != 'PIL'):
            for command in ('report', 'cloud', '直播报告', '词云', 'push report on', '推送 弹幕词云 off'):
                self.assertIsNone(message.parse_action(command)[0])
                self.assertFalse(self.command(f'.bpush {command}', 'owner'))
            self.assertNotIn('report', self.command('.bpush help stats')[0])
            self.assertNotIn('cloud', self.command('.bpush help push')[0])
            self.assertIn('room [主播]', self.command('.bpush help stats')[0])
        code = '''
import sys
from selftest import offline_plugin
sys.modules['PIL'] = sys.modules['jieba'] = None
with offline_plugin():
    from BiliBiliNotify import report_render, wordcloud_render
    assert report_render.render_live_report({}) is None
    assert wordcloud_render.render_wordcloud({}) is None
    assert wordcloud_render.extract_terms([{'uid': '7', 'text': '哈哈哈哈'}])[0][0][0] == '哈哈'
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=PLUGIN / 'tests',
                                capture_output=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_web_sessions_preview_and_settings(self):
        self.command('.bpush up add 2', 'owner')
        self.command('.bpush up add 3', 'owner')
        stamp = int(time.time()) - 1200
        ids = [self.session(stamp + index * 90, 45, words=['冰雪列车'], paid=index == 10) for index in range(11)]
        self.session(stamp + 1000, 45, uid='3', room_id='2048')
        live_stats.finalize_due(now=stamp + 1100)
        sessions = self.web('list_sessions', uid='2')['sessions']
        self.assertEqual([row['id'] for row in sessions], ids[:0:-1])
        self.assertEqual((sessions[0]['duration'], sessions[0]['online_peak'], sessions[0]['danmu']), (45, 93, 2))
        self.assertGreater(sessions[0]['gold'], 0)
        self.assertEqual([row['id'] for row in live_stats.list_sessions('2', limit=2)], ids[:-3:-1])
        for kind in ('report', 'cloud'):
            image = self.web('preview_session_image', uid='2', session_id=ids[-1], kind=kind)['image']
            self.assertTrue(image.startswith('data:image/png;base64,'))
            self.png(io.BytesIO(base64.b64decode(image.partition(',')[2], validate=True)))
            with self.assertRaises(webui._InvalidRequest):
                self.web('preview_session_image', uid='3', session_id=ids[-1], kind=kind)
        with self.assertRaises(webui._InvalidRequest):
            self.web('list_sessions', uid='999')
        self.assertFalse(list(config.IMAGE_ROOT.parent.rglob('*.png')))
        stats = self.web('save_bot', live_stats={
            'hide_revenue': True, 'auto_report': True, 'auto_wordcloud': True, 'save_report_image': True,
            'min_report_minutes': 120, 'min_report_danmu': 0, 'wordcloud_limit': 10,
            'wordcloud_stopwords': ['  一般  ', '', '一般'], 'wordcloud_words': [' 冰雪列车 ', '冰雪列车'],
        })['bot']['live_stats']
        self.assertEqual(stats['min_report_minutes'], 120)
        self.assertEqual(stats['wordcloud_stopwords'], ['一般'])
        self.assertEqual(stats['wordcloud_words'], ['冰雪列车'])
        self.assertNotIn('gold', self.web('list_sessions', uid='2')['sessions'][0])
        for field, value in (('min_report_minutes', 121), ('min_report_danmu', 1001), ('wordcloud_limit', 301),
                             ('wordcloud_words', '冰雪列车'), ('wordcloud_stopwords', [12]),
                             ('wordcloud_words', ['词' * 33]),
                             ('wordcloud_stopwords', [f'词{index}' for index in range(201)])):
            with self.assertRaises(webui._InvalidRequest):
                self.web('save_bot', live_stats={field: value})
        for kind in ('report', 'cloud'):
            for mode in ('on', 'off', 'inherit'):
                group = self.web('save_group', sid=self.sid, **{kind: mode})['groups'][self.sid]
                self.assertEqual(group[kind], mode)
        huge = Path(self.temp_dir) / 'oversize.png'
        huge.write_bytes(b'X' * (2 * 1024 * 1024 + 1))
        with patch.object(function, 'render_session_image', return_value=huge) as render:
            with self.assertRaisesRegex(webui._InvalidRequest, '2 MiB'):
                self.web('preview_session_image', uid='2', session_id=ids[-1], kind='report')
            self.assertTrue(render.call_args.args[2]['hide_revenue'])
        self.assertFalse(huge.exists())
        with patch.object(capabilities, '_has_module', side_effect=lambda name: name != 'PIL'):
            self.assertEqual(len(self.web('list_sessions', uid='2')['sessions']), 10)
            for kind, key in (('report', 'auto_report'), ('cloud', 'auto_wordcloud')):
                with self.assertRaisesRegex(webui._InvalidRequest, '安装 Pillow'):
                    self.web('preview_session_image', uid='2', session_id=ids[-1], kind=kind)
                with self.assertRaisesRegex(webui._InvalidRequest, '安装 Pillow'):
                    self.web('save_group', sid=self.sid, **{kind: 'on'})
                with self.assertRaisesRegex(webui._InvalidRequest, '安装 Pillow'):
                    self.web('save_bot', live_stats={key: True})
                self.assertFalse(self.web('save_bot', live_stats={key: False})['bot']['live_stats'][key])
            with self.assertRaisesRegex(webui._InvalidRequest, '安装 Pillow'):
                self.web('save_bot', live_stats={'save_report_image': True})

    def test_sourcery_audit_regressions(self):
        from PIL import Image, ImageDraw
        from BiliBiliNotify import render_base

        # 1. OneBot V11 _send_local_op 必须移除 user_id 并确保 group_id 为字符串（与 OlivOS-2 POST 契约对齐）。
        root = config.IMAGE_ROOT.parent / 'generated'
        root.mkdir(parents=True, exist_ok=True)
        local_png = root / 'audit-check.png'
        with Image.new('RGB', (16, 16), '#ffffff') as img:
            img.save(local_png)
        request = SimpleNamespace(data=SimpleNamespace(user_id=-1), do_api=Mock(
            return_value=SimpleNamespace(body={'status': 'ok', 'retcode': 0}),
        ))
        v11_event = SimpleNamespace(platform={'model': 'v11'}, plugin_info={'control_queue': object()}, send=Mock())
        sdk_v11 = SimpleNamespace(
            api=SimpleNamespace(send_msg=lambda _: request), get_SDK_bot_info_from_Event=lambda e: e,
            paraMsgMap=(), formatMessage=lambda chunk, mode: chunk,
        )
        api = SimpleNamespace(Message_templet=lambda *args: SimpleNamespace(get=lambda _: args[-1]))
        with (patch.object(sender, '_event', return_value=v11_event),
              patch.object(sender.OlivOS, 'onebotV11LinkServerAPI', SimpleNamespace(gCheckList=('v11',)), create=True),
              patch.object(sender.OlivOS, 'onebotSDK', sdk_v11, create=True),
              patch.object(sender.OlivOS, 'messageAPI', api, create=True)):
            self.assertTrue(sender.send_local_image(self.proc, BOT, GROUP, local_png))
        self.assertFalse(hasattr(request.data, 'user_id'))
        self.assertIsInstance(request.data.group_id, str)

        # 2. Brotli 与 zlib 解压炸弹上限守卫。
        def packet(data, version):
            return struct.pack('>IHHII', 16 + len(data), 16, version, 5, 1) + data

        payload = packet(b'{"cmd":"DANMU_MSG","pad":"' + b'x' * 120 + b'"}', 0)
        z_frame = packet(livesocket.zlib.compress(payload), 2)
        b_frame = packet(livesocket.brotli.compress(payload), 3)
        with patch.object(livesocket, '_MAX_DECOMPRESSED', 64):
            self.assertEqual(livesocket.parse_packet(z_frame), [])
            self.assertEqual(livesocket.parse_packet(b_frame), [])

        # 3. 词云能力门控与非 dict 入参守卫。
        self.assertIsNone(wordcloud_render.render_wordcloud(None))
        with patch.object(capabilities, '_has_module', side_effect=lambda name: name != 'PIL'):
            self.assertIsNone(wordcloud_render.render_wordcloud({
                'uname': '碧诗', 'danmu_rows': [{'uid': '7', 'text': '冰雪列车'}],
            }))

        # 4. 直播报告异常时间戳、未知大航海等级、45 条上舰上限截断与精确营收格式。
        self.assertEqual(report_render._stamp(-999999999999), '—')
        many_guards = [{'uid': str(i), 'uname': f'舰长{i}', 'guard_level': 3 if i else 99,
                        'months': 1, 'gold': 198000} for i in range(45)]
        detail = {
            'uid': '2', 'uname': '碧诗', 'title': '审计场次', 'area': '虚拟主播', 'status': 'ended',
            'start_at': -999999999999, 'end_at': 1000, 'duration': 600,
            'danmu': 5, 'interactors': 2, 'online_peak': 10, 'watched_peak': 20,
            'entry': 3, 'like': 4, 'follow': 1, 'share': 0, 'gold': 1234560,
            'guards': many_guards, 'guard_levels': {1: 0, 2: 0, 3: 44},
            'gifts': [], 'minutes': [], 'rankings': {},
        }
        texts = []
        actual_text = ImageDraw.ImageDraw.text

        def capture_text(draw, xy, text, *args, **kwargs):
            texts.append(text)
            return actual_text(draw, xy, text, *args, **kwargs)

        with patch.object(ImageDraw.ImageDraw, 'text', capture_text):
            report_path = report_render.render_live_report(detail)
        self.assertIsNotNone(report_path)
        try:
            height = self.png(report_path)
            self.assertLess(height, 2600)
            joined = ' '.join(texts)
            self.assertIn('¥1,234.56', joined)
            self.assertIn('另有 15 条上舰记录', joined)
        finally:
            sender.release_local_image(report_path)

        # 5. render_base.save_generated_png 拒绝目录穿越 subdir。
        with Image.new('RGB', (4, 4), '#fff') as tiny:
            with self.assertRaises(ValueError):
                render_base.save_generated_png(tiny, subdir='../escape')

        # 6. 不完整 push dynamic_img 路由至 push 分流帮助；session_detail 为 None 时安全回退。
        self.command('.bpush up add 2', 'owner')
        help_reply, = self.command('.bpush push dynamic_img', 'owner')
        self.assertIn('dynamic_img', help_reply)
        with (patch.object(live_stats, 'current_session_id', return_value=999),
              patch.object(live_stats, 'session_detail', return_value=None)):
            reply, = self.command('.bpush report')
            self.assertIn('场次', reply)

    def test_bot_nicknames_and_sync(self):
        with webui._bot_nick_lock:
            webui._bot_nick_cache.clear()
        bot_a = 'aa0ee01502c7d673633be9908676df62'
        bot_b = '23c1c9409599b84d65ca6b9366aa5b3c'
        bot_c = '0a47d5024e221827bbae786e5d5d29ad'
        bots = {
            bot_a: SimpleNamespace(id=3948837959, platform={'sdk': 'onebot', 'platform': 'qq'}, extends={}),
            bot_b: SimpleNamespace(id=102080146, platform={'sdk': 'qqGuildv2_link', 'platform': 'qqGuild'}, extends={}),
            bot_c: SimpleNamespace(id=90307142, platform={'sdk': 'heybox', 'platform': 'xiaoheihe'},
                                   extends={}, enable=False),
        }
        proc = SimpleNamespace(log=lambda *_: None, Proc_data={'bot_info_dict': bots})
        fake_core = SimpleNamespace(msgCustom=SimpleNamespace(dictStrCustomDict={
            bot_a: {'strBotName': 'Fronia芙萝妮娅'},
            bot_b: {'strBotName': 'OlivaDice'},  # 默认模板名不覆盖真实昵称
        }))
        with patch.dict(sys.modules, {'OlivaDiceCore': fake_core}):
            st = webui.dispatch({'action': 'get_state', 'bot_hash': bot_a}, proc)['state']
            by_hash = {b['hash']: b for b in st['bots']}
            self.assertEqual(by_hash[bot_a]['nickname'], 'Fronia芙萝妮娅')
            self.assertEqual(by_hash[bot_a]['id'], '3948837959')
            self.assertEqual(by_hash[bot_b]['nickname'], '')
            self.assertEqual(by_hash[bot_b]['name'], '102080146')

            # sync_bot_names 并行通过 Event.get_login_info 拉取平台真实昵称并缓存，跳过禁用 Bot。
            called_ids = []

            class FakeEvent:
                def __init__(self, raw, **kw):
                    self.bot_info = raw

                def get_login_info(self, flag_log=False):
                    called_ids.append(self.bot_info.id)
                    if self.bot_info.id == 3948837959:
                        return {'active': True, 'data': {'name': '小芙QQ真名', 'id': '3948837959'}}
                    if self.bot_info.id == 102080146:
                        return {'active': True, 'data': {'name': '芙萝妮娅官方号', 'id': '102080146'}}
                    return None

            fake_content = SimpleNamespace(fake_sdk_event=lambda bot, **kw: bot)
            fake_api = SimpleNamespace(Event=FakeEvent)
            with (patch.object(webui.OlivOS, 'contentAPI', fake_content, create=True),
                  patch.object(webui.OlivOS, 'API', fake_api, create=True)):
                synced = webui.dispatch({'action': 'sync_bot_names', 'bot_hash': bot_a}, proc)['state']
            synced_map = {b['hash']: b for b in synced['bots']}
            self.assertEqual(synced_map[bot_a]['nickname'], '小芙QQ真名')
            self.assertEqual(synced_map[bot_b]['nickname'], '芙萝妮娅官方号')
            self.assertEqual(synced_map[bot_c]['nickname'], '')
            self.assertCountEqual(called_ids, [3948837959, 102080146])
        with webui._bot_nick_lock:
            webui._bot_nick_cache.clear()

    def test_opk_eager_module_preload(self):
        # OPK 在 init 后会清理 plugin/tmp/<namespace>，所有插件子模块必须在 import BiliBiliNotify 时完成预加载。
        code = '''
import sys
from pathlib import Path
from selftest import PLUGIN, offline_plugin
with offline_plugin():
    import BiliBiliNotify  # noqa: F401
    expected = sorted(p.stem for p in Path(PLUGIN).glob('*.py') if p.name != '__init__.py')
    missing = [name for name in expected if f'BiliBiliNotify.{name}' not in sys.modules]
    assert not missing, f'OPK 运行期可能触发 ImportError，未在启动期预加载的模块: {missing}'
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=PLUGIN / 'tests',
                                capture_output=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_push_newlines_and_end_duration(self):
        # 全部 OP 推送方框后必须紧跟换行；下播推送有开播时间时展示直播时长，缺失或时钟倒流时省略该行。
        sample_fields = {
            'name': '碧诗', 'title': '晚间闲聊', 'area': '虚拟主播',
            'time': '2026-11-27 20:00:00', 'body': '动态正文', 'link': 'https://live.bilibili.com/1024',
        }
        for kind, header in (
            ('start', '【B站开播】\n'),
            ('area', '【B站换分区】\n'),
            ('end', '【B站下播】\n'),
            ('dynamic', '【B站动态】\n'),
            ('video', '【B站投稿】\n'),
        ):
            rendered = ''.join(sender._render(kind, sample_fields, 'onebot', '', False, (), False))
            self.assertIn(header, rendered)
        # 无开播时间：OP 与 Markdown 均不显示直播时长。
        room = {'uid': '2', 'room_id': '1024'}
        no_start = notify._live_fields(
            room, '2', {'live_status': 1, 'last_live_time': 0, 'last_title': 'T', 'last_area_v2_name': 'A'},
            {'live_status': 0}, 'end', 1700003600,
        )
        self.assertEqual(no_start['duration'], '')
        for sdk in ('onebot', 'qqGuildv2_link'):
            text = ''.join(sender._render('end', {**no_start, 'name': '碧诗'}, sdk, '', False, (), False))
            self.assertNotIn('直播时长', text)
        # 时钟倒流也不显示。
        reversed_clock = notify._live_fields(
            room, '2', {'live_status': 1, 'last_live_time': 1700004000, 'last_title': 'T', 'last_area_v2_name': 'A'},
            {'live_status': 0}, 'end', 1700003600,
        )
        self.assertEqual(reversed_clock['duration'], '')
        # 有开播时间（含直播中途绑定/重载持久化下来的 last_live_time）：精准计算并渲染。
        with_start = notify._live_fields(
            room, '2', {'live_status': 1, 'last_live_time': 1700000000, 'last_title': 'T', 'last_area_v2_name': 'A'},
            {'live_status': 0}, 'end', 1700005445,
        )
        self.assertEqual(with_start['duration'], '1小时30分45秒')
        op_end = ''.join(sender._render('end', {**with_start, 'name': '碧诗'}, 'onebot', '', False, (), False))
        md_end = ''.join(sender._render('end', {**with_start, 'name': '碧诗'}, 'qqGuildv2_link', '', False, (), False))
        self.assertIn('【B站下播】\n碧诗 下播了', op_end)
        self.assertIn('\n直播时长：1小时30分45秒', op_end)
        self.assertIn('\n**直播时长**：1小时30分45秒', md_end)
        # 开启直播统计且断流续接场次：优先取 stats.db 整场 start_at。
        live_stats.on_live_start('2', '1024', start_at=1700000000, title='T', area='A', grace_seconds=120)
        live_stats.on_live_end('1024', end_at=1700007200, grace_seconds=120)
        with_stats = notify._live_fields(
            room, '2', {'live_status': 1, 'last_live_time': 1700003600, 'last_title': 'T', 'last_area_v2_name': 'A'},
            {'live_status': 0}, 'end', 1700007200, use_stats=True,
        )
        self.assertEqual(with_stats['duration'], '2小时')


CASES = (
    (Suite, 'test_commands', '命令解析'), (Suite, 'test_binding', 'UID 两级绑定与群订阅'), (Suite, 'test_permissions', '权限'),
    (Suite, 'test_storage', '存储原子性与损坏归档'), (Suite, 'test_live', '直播状态机'), (Suite, 'test_dynamics', '动态去重及过滤'),
    (Suite, 'test_videos', '视频去重'), (Suite, 'test_quota', '@全体配额'), (Suite, 'test_subscribers', '@订阅者去重与分段'),
    (Suite, 'test_images', '首图选择'), (Suite, 'test_eligibility', '三重开关真值表'),
    (Suite, 'test_livesocket', '弹幕包解析'), (Suite, 'test_manifest', '清单与文件结构'),
    (Suite, 'test_atall_admin_guard', '@全体管理权限与回退'),
    (Suite, 'test_maintain_does_not_block_tick', '后台维护锁外请求不阻塞 tick'),
    (ChainSuite, 'test_dynamic_three_chain_cascade', '动态三链条级联、冷却与日志去噪'),
    (ChainSuite, 'test_video_three_chain_cascade', '视频三链条级联与关注流归一化'),
    (ChainSuite, 'test_live_three_chain_and_normalization', '直播三步探测与单间字段对齐'),
    (ChainSuite, 'test_probe_api_webui_and_redaction', 'WebUI 手动自检、冷却解除与凭据脱敏'),
    (ChainSuite, 'test_multi_account_and_follow_guard', '多账号扫码保存切换、头像脱敏与自动关注'),
    (PhaseOneSuite, 'test_capabilities_and_webui', '能力探测、WebUI 门控与三态配置'),
    (PhaseOneSuite, 'test_help_sections_and_copy', '分流帮助、群命令权限与正向文案'),
    (PhaseOneSuite, 'test_dynamic_png', '动态 PNG：长正文、九宫格、转发与 Opus'),
    (PhaseOneSuite, 'test_local_image_adapters', '双平台本地图、QQ 降级与 OneBot 队列清理'),
    (PhaseOneSuite, 'test_dynamic_delivery_reuse_and_fallback', '群动态图片复用、存档与失败回退'),
    (PhaseTwoSuite, 'test_brotli_dispatch_and_fans', 'Brotli 弹幕帧、事件回调隔离与粉丝快照接口'),
    (PhaseTwoSuite, 'test_stats_events_and_persistence', '直播全事件计量、WAL 持久化及弹幕清理'),
    (PhaseTwoSuite, 'test_stats_resume_and_scoped_likes', '断流续接、过期封账及跨场点赞增量'),
    (PhaseTwoSuite, 'test_stats_background_flush', '事件达到数量或计时阈值时后台提交、直播中途补建'),
    (PhaseTwoSuite, 'test_stats_webui_validation', 'WebUI 统计配置与缺依赖写入拦截'),
    (PhaseTwoSuite, 'test_stats_group_commands', '群统计查询、昵称匹配、共享冷却及营收隐私'),
    (PhaseTwoSuite, 'test_stats_notify_lifecycle', '共享直播间采集、断流开播去重与封账回调'),
    (PhaseThreeSuite, 'test_report_png_privacy_and_sparse', '报告 PNG：完整场次、稀疏板块与营收隐私'),
    (PhaseThreeSuite, 'test_wordcloud_engines_and_png', '词云 PNG：双分词、清洗、热词与同观众降权'),
    (PhaseThreeSuite, 'test_auto_images_async_routing_and_archive', '异步封账推送：分群路由与阈值、复用及存档'),
    (PhaseThreeSuite, 'test_image_commands_and_help_gates', '群报告与词云查询、管理三态、帮助与缺依赖门控'),
    (PhaseThreeSuite, 'test_web_sessions_preview_and_settings', 'WebUI 历史、预览权限与体积、统计配置门控'),
    (PhaseThreeSuite, 'test_sourcery_audit_regressions', 'Sourcery 审计缺陷回归：V11 POST、解压上限、报告边界与路由'),
    (PhaseThreeSuite, 'test_bot_nicknames_and_sync', 'WebUI Bot 选择器昵称解析与异步登录信息同步'),
    (PhaseThreeSuite, 'test_opk_eager_module_preload', 'OPK 生命周期：启动期预加载全部插件子模块防延迟导入失败'),
    (PhaseThreeSuite, 'test_push_newlines_and_end_duration', '推送方框换行与下播直播时长计算及缺失隐藏'),
)


if __name__ == '__main__':
    with offline_plugin():
        from BiliBiliNotify import (
            bili_api, capabilities, config, dynamic_render, function, live_stats, livesocket, main, message,
            notify, report_render, sender, store, utils, webui, wordcloud_render,
        )

        failed = []
        for cls, method, label in CASES:
            result = unittest.TestResult()
            cls(method).run(result)
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
