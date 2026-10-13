"""用指定 OlivOS 实例的解释器与真实 OPK，在独立目录验证加载、GUI 和宿主 WebUI。"""

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host-root', required=True)
    parser.add_argument('--package', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--expect-failure', action='store_true')
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    host_root = Path(args.host_root).resolve()
    package = Path(args.package).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(host_root))
    import OlivOS

    # 只读取账号 ID/平台，构建相同的 bot_hash；不复制凭据，不启动消息协议连接。
    document = json.loads((host_root / 'conf/account.json').read_text(encoding='utf-8-sig'))
    bots = {}
    for item in document['account']:
        bot = OlivOS.API.bot_info_T(
            id=item['id'],
            platform_sdk=item['sdk_type'],
            platform_platform=item['platform_type'],
            platform_model=item['model_type'],
        )
        bots[bot.hash] = bot
    assert bots, '指定实例没有配置账号。'
    del document
    sandbox = Path(tempfile.mkdtemp(prefix='mcs-host-', dir=host_root / 'runtime'))
    (sandbox / 'plugin/app').mkdir(parents=True)
    for name in (
        'OlivaDiceCore', 'OlivaDiceJoy', 'OlivaDiceMaster', 'OlivaDiceLogger',
        'OlivaDiceOdyssey', 'OlivaStoryCore', 'ChanceCustom', 'OlivaDiceNativeGUI', 'OlivaDiceWebUI',
    ):
        shutil.copy2(host_root / 'plugin/app' / f'{name}.opk', sandbox / 'plugin/app')
    shutil.copy2(package, sandbox / 'plugin/app/MultiCustomSwitch.opk')
    os.chdir(sandbox)
    (sandbox / 'plugin/conf').mkdir(parents=True)
    for name in ('plugin/app', 'plugin/tmp'):
        Path(name).mkdir(parents=True, exist_ok=True)
        sys.path.insert(0, str(sandbox / name))
    control = queue.Queue()
    host = OlivOS.webUI.serverAPI.server(
        root_path=sandbox,
        rx_queue=queue.Queue(),
        control_queue=control,
        bot_info_dict=bots,
        server_conf={'port': 0, 'host': '127.0.0.1'},
    )
    loader = OlivOS.pluginAPI.shallow(control_queue=control, bot_info_dict=bots)
    errors = []

    def log(level=None, text='', *args, **kwargs):
        level = kwargs.get('log_level', level)
        text = kwargs.get('log_message', text)
        # Core 初始化日志含动态骰主验证信息；不保存、不回显普通日志。
        if level >= 4:
            errors.append(text)
            for line in text.splitlines():
                if re.match(r'\s*File ".+", line \d+, in ', line) or re.match(
                    r"ModuleNotFoundError: No module named '[A-Za-z0-9_.]+'$", line
                ):
                    print(line, flush=True)

    loader.log = log
    host.log = log
    loader.database = OlivOS.userModule.UserConfDB.DataBaseAPI(log, max_thread=1)
    OlivOS.pluginAPI.gProc = loader
    # 测试边界：登录信息不可用，使用账号 ID 回退，避免发起真实消息协议请求。
    OlivOS.API.Event.get_login_info = lambda *args, **kwargs: {'active': False, 'data': {}}
    root = None
    manager = None
    thread = None
    bus_thread = None
    stop = threading.Event()
    start_thread = threading.Thread.start

    def start_test_thread(thread):
        # 不运行本次验证无关的长驻心跳；其它真实宿主/数据库线程保持原样。
        if getattr(thread._target, '__name__', '') in {'sendKOOKManageThread', 'getCheckAPI'}:
            return None
        return start_thread(thread)

    try:
        threading.Thread.start = start_test_thread
        loader.load_plugin_list()
        assert not errors, '真实 OPK 导入失败。'
        import MultiCustomSwitch as plugin
        import OlivaDiceLogger as logger
        import OlivaDiceMaster as master
        import OlivaDiceNativeGUI as native
        import OlivaDiceWebUI as official

        # 官方 GUI 的在线人数轮询与此测试无关，不启动长驻外网请求。
        native.load.checkOnlineStatusLoop = lambda: None
        master.backup.initBackupSystem = lambda proc: None
        logger.logger.init_logger = lambda event, proc: None
        loader.run_plugin_func(None, 'init_after')
        threading.Thread.start = start_thread
        if args.expect_failure:
            assert plugin.runtime.STORE is None
            try:
                plugin.runtime.install(loader)
            except AttributeError as exc:
                missing = exc.name
                print(f'已复现旧包初始化失败：AttributeError，缺少 Core 接口 {missing}。', flush=True)
            else:
                raise AssertionError('没有复现预期异常。')
            plugin.runtime.uninstall()
            return
        assert not errors, '真实宿主 init_after 失败。'
        assert plugin.runtime.STORE is not None
        assert not (sandbox / 'plugin/tmp/MultiCustomSwitch').exists()
        accounts = plugin.api.dispatch({'op': 'accounts'})['accounts']
        assert {row['hash'] for row in accounts} == {'unity', *bots}
        for bot in bots:
            state = plugin.api.dispatch({'op': 'state', 'scope': bot})
            assert [(row['selection'], row['readonly']) for row in state['replies']] == [(1, False), (2, True)]
            assert plugin.api.dispatch({'op': 'snapshot', 'scope': bot, 'selection': 1})['entries']
            assert plugin.api.dispatch({'op': 'snapshot', 'scope': bot, 'selection': 2})['readonly']
        assert official.service.LOCK is plugin.files.LOCK
        # 使用真实 OneBot 事件解析与宿主分发；仅替换消息发送出口，不向群发送测试消息。
        chat_bot = next((bot for bot in bots.values() if bot.platform['sdk'] == 'onebot'), None)
        if chat_bot is not None:
            replies = []
            original_reply = OlivOS.API.Event.reply
            OlivOS.API.Event.reply = lambda event, message, **kwargs: replies.append(message)
            try:
                payload = {
                    'time': int(time.time()), 'self_id': chat_bot.id, 'post_type': 'message',
                    'message_type': 'group', 'sub_type': 'normal', 'group_id': 90000001,
                    'user_id': 123, 'message_id': 1, 'font': 0,
                    'sender': {'user_id': 123, 'nickname': '测试群管理员', 'role': 'admin'},
                }
                for command in ('.mcslist', '.mcs2', '.mcshelp', '.mcsoff', '.mcson'):
                    payload['message'] = command
                    previous = len(replies)
                    sdk_event = OlivOS.onebotSDK.event(json.dumps(payload))
                    sdk_event.platform['model'] = chat_bot.platform['model']
                    loader.run_plugin(sdk_event)
                    assert len(replies) > previous, f'真实宿主指令未回复：{command}'
                import OlivaDiceCore

                group_hash = OlivaDiceCore.userConfig.getUserHash('90000001', 'group', chat_bot.platform['platform'])
                assert plugin.runtime.STORE.status(chat_bot.hash, group_hash)['effective'] == 2
            finally:
                OlivOS.API.Event.reply = original_reply
            assert not errors, '真实宿主指令执行失败。'
        root = tk.Tk()
        root.withdraw()
        loader.Proc_data['main_tk'] = root
        menu = OlivOS.API.Control.packet('send', {'data': {
            'action': 'plugin_menu', 'namespace': 'MultiCustomSwitch', 'event': 'MultiCustomSwitch_Open',
        }})
        loader.run_plugin(menu)
        root.update()
        manager = plugin.gui._WINDOW
        assert manager is not None and manager.root.winfo_exists()
        manager.root.withdraw()
        assert len(manager.accounts) == len(bots) + 1
        manager.scope_var.set(manager.accounts[1]['label'])
        manager.change_scope()
        assert list(manager.pack_map.values()) == [1, 2]
        bot = manager.scope
        entry = next(row for row in manager.snapshot['entries'] if row['key'] == 'strRoll')
        original = entry['value']
        manager.set_editor(entry)
        manager.editor.delete('1.0', 'end')
        manager.editor.insert('1.0', 'D 盘真实 GUI 验证')
        manager.save()
        assert official.gui_parity.replies_snapshot(loader, bot)['strRoll'] == 'D 盘真实 GUI 验证'
        official.service.set_reply(loader, bot, 'strRoll', original)
        manager.load_pack()
        manager.pack_var.set('2. smp')
        manager.change_pack()
        manager.set_editor(next(row for row in manager.snapshot['entries'] if row['key'] == 'strRoll'))
        assert str(manager.editor['state']) == 'disabled'
        # 图形窗口重复打开沿用现有窗口，与宿主 Tk 主循环共同工作。
        plugin.gui.open_window()
        root.update()
        assert plugin.gui._WINDOW is manager
        manager.root.withdraw()
        loader.sendPluginList(ready=True)
        while not control.empty():
            host.consume(control.get_nowait())
        client = host.app.test_client()
        assert client.post('/api/login', headers={'X-Auth-Token': host.token}).status_code == 200
        page = client.get('/plugin/MultiCustomSwitch/webui/index.html')
        assert page.status_code == 200
        assert b'MultiCustomSwitch_Request' in page.data
        report = {
            'host_svn': OlivOS.infoAPI.OlivOS_SVN,
            'core_version': loader.plugin_models_dict['OlivaDiceCore']['appconf']['version'],
            'plugin_version': plugin.resources.VERSION,
            'account_count': len(bots),
            'checks': ['真实 OPK 加载及解包清理', '全部账号与 default/smp', '宿主菜单打开及复用 GUI',
                       'GUI 保存与官方面板双向同步', 'smp 编辑框只读', '宿主缓存提供 WebUI 页面'],
            'sandbox': str(sandbox),
            'package_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
        }
        if chat_bot is not None:
            report['checks'].append('真实 OneBot 事件执行免空格 list/切换/help/off/on，发送出口隔离')
        if args.serve:
            def bus():
                while not stop.is_set():
                    try:
                        packet = control.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if packet.key.get('data', {}).get('action') == 'plugin_menu':
                        loader.run_plugin(packet)
                    else:
                        host.consume(packet)

            bus_thread = threading.Thread(target=bus, daemon=True)
            bus_thread.start()
            thread = threading.Thread(target=host.run, daemon=True)
            thread.start()
            assert host.ready.wait(10) and host.error is None
            address = json.loads(host.listen_path.read_text(encoding='utf-8'))
            report['url'] = f'http://127.0.0.1:{address["port"]}'
        (output / 'host-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(
            f'真实宿主验证通过：Core {report["core_version"]}，{len(bots)} 个账号，GUI/default/smp 正常。',
            flush=True,
        )
        if args.serve:
            print('WebUI 实测服务已就绪。', flush=True)
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline and not (output / 'browser-done').exists():
                root.update()
                time.sleep(0.05)
        assert not errors, '宿主验证期间发生错误。'
    finally:
        threading.Thread.start = start_thread
        stop.set()
        host.on_terminate()
        if thread is not None:
            thread.join(timeout=5)
        if bus_thread is not None:
            bus_thread.join(timeout=2)
        if manager is not None:
            manager.close()
        if root is not None:
            root.destroy()
        if 'MultiCustomSwitch' in sys.modules:
            sys.modules['MultiCustomSwitch'].runtime.uninstall()
        loader.database.stop()


if __name__ == '__main__':
    main()
