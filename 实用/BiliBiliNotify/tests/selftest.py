from contextlib import contextmanager
from copy import deepcopy
import importlib
from itertools import product
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import time
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
        self.assertIn('没查到 UID 1024', self.command(f'.{config.COMMAND_NAME} up add 1024', 'owner')[0])
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
        self.assertNotIn('未检测到机器人是本群管理员', ok_reply)
        warn_reply = self.command(f'.{config.COMMAND_NAME} atall on', 'owner', bot_role='member')[0]
        self.assertIn('已开启', warn_reply)
        self.assertIn('未检测到机器人是本群管理员', warn_reply)

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
)


if __name__ == '__main__':
    with offline_plugin():
        from BiliBiliNotify import (
            bili_api, config, function, livesocket, main, message, notify, sender, store, utils, webui,
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
