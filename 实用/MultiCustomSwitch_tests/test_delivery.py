import importlib
import json
import shutil
import sys
import threading
import time
import tkinter as tk
import types
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


def test_empty_core_overwrite_file_is_valid_default_template(env):
    result = env.store.import_pack(env.bots[0], '全默认', {})
    assert env.store.values(env.bots[0], result['selection']) == env.store.smp(env.bots[0])


def test_builtin_import_collisions_and_default_shared_overwrite(env):
    bot = env.bots[0]
    for name in ('default', 'smp'):
        assert env.store.import_pack(bot, name, {'strRoll': '文本'})['conflict']
    assert env.store.import_pack(bot, 'default', {'strRoll': '文本'}, 'cancel')['cancelled']
    assert env.store.import_pack(bot, 'default', {'strRoll': '导入 Core'}, 'overwrite')['selection'] == 1
    assert env.webui.gui_parity.replies_snapshot(env.proc, bot)['strRoll'] == '导入 Core'
    with pytest.raises(env.plugin.store.InvalidInput):
        env.store.import_pack(bot, 'smp', {'strRoll': '文本'}, 'overwrite')
    assert env.store.import_pack(bot, 'smp', {'strRoll': '文本'}, 'copy')['selection'] >= 3
    unity = env.store.import_pack('unity', 'default', {'strRoll': '模板库同名模板'})
    assert unity['selection'] == 'default'
    env.store.reload('unity')
    assert env.store.values('unity', 'default')['strRoll'] == '模板库同名模板'


def test_global_off_does_not_materialize_disabled_local_switch(env):
    bot = env.bots[0]
    env.store.select(bot, enabled=False)
    group = env.store.group_hash(env.event())
    env.store.select(bot, model=2, group_hash=group)
    assert env.store.groups[bot][group]['enabled']
    assert env.store.status(bot, group)['effective'] == 1
    env.store.select(bot, enabled=True)
    assert env.store.status(bot, group)['effective'] == 2


def test_stale_reindex_or_changed_recover_baseline_is_rejected(env):
    bot = env.bots[0]
    env.store.import_pack(bot, '甲', {'strRoll': '甲'})
    env.store.import_pack(bot, '乙', {'strRoll': '乙'})
    revision = env.store.index_revision(bot)
    env.store.reindex(bot, {'3': 4, '4': 3}, revision)
    with pytest.raises(env.plugin.store.Conflict):
        env.store.reindex(bot, {'3': 4, '4': 3}, revision)
    snapshot = env.store.snapshot(bot, 1)
    env.store.modules(bot, ['OlivaDiceCore', 'MultiCustomSwitch'])
    with pytest.raises(env.plugin.store.Conflict):
        env.store.edit(bot, 1, 'strRoll', '旧基线', snapshot['revision'])


def test_real_core_context_wait_and_numeric_reply_end_to_end(env):
    bot = env.bots[0]
    env.store.import_pack(bot, '可爱回复', {'strRoll': '可爱'})
    event = env.event(message='.mcs可爱回')
    thread = threading.Thread(target=env.plugin.commands.handle, args=(event, env.proc))
    thread.start()
    try:
        deadline = time.monotonic() + 3
        while bot not in env.core.crossHook.dictReplyContextReg and time.monotonic() < deadline:
            time.sleep(0.01)
        assert bot in env.core.crossHook.dictReplyContextReg
        response = env.event(message='1')
        assert env.core.msgReplyModel.replyCONTEXT_regGet(response, '1')
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert env.store.status(bot, env.store.group_hash(event))['selected'] == 3
    finally:
        env.core.crossHook.dictReplyContextReg.clear()
        thread.join(timeout=3)


def test_reindex_and_settings_preserve_unrelated_config_keys(env):
    bot = env.bots[0]
    env.store.import_pack(bot, '甲', {'strRoll': '甲'})
    group = env.store.group_hash(env.event())
    path = env.store.directory(bot) / 'group' / f'{group}.json'
    env.plugin.files.write_json(path, {'reply_model': 3, 'enabled': True, 'note': '用户备注'})
    env.store.reload(bot)
    env.store.select(bot, enabled=False, group_hash=group)
    env.store.reindex(bot, {'3': 8})
    assert env.plugin.files.read_json(path) == {'reply_model': 8, 'enabled': False, 'note': '用户备注'}


@pytest.mark.parametrize(
    'message', ['.str strRoll', '[CQ:at,qq=1001] .str strRoll', '[CQ:reply,id=1][CQ:at,qq=1001] 。str strRoll']
)
def test_original_str_command_reads_default_even_with_quote_and_at(env, message):
    bot = env.bots[0]
    model = env.store.import_pack(bot, '风格', {'strRoll': '风格'})['selection']
    env.store.select(bot, model)
    event = env.event(message=message)
    handler = types.SimpleNamespace(
        main=types.SimpleNamespace(
            Event=types.SimpleNamespace(
                group_message=lambda event, proc: env.core.msgCustom.dictStrCustomDict[bot]['strRoll'],
            )
        )
    )
    assert env.proc.plugin_event_router(event, handler, 'Core') == env.store.default_values(bot)['strRoll']


def test_uninstall_preserves_dictionary_replacements_by_both_editors(env):
    bot = env.bots[0]
    env.store.edit(bot, 1, 'strRoll', '插件更新', env.store.snapshot(bot, 1)['revision'])
    env.webui.gui_parity.replies_apply(env.proc, bot, 'import', {'strForGroupOnly': '官方整表更新'})
    current = env.store.default_values(bot)
    env.plugin.runtime.uninstall()
    assert env.core.msgCustom.dictStrCustomDict[bot] == current
    assert current['strRoll'] == env.core.msgCustom.dictStrCustom['strRoll']
    assert current['strForGroupOnly'] == '官方整表更新'


def test_real_http_download_json_validation_and_redirect(env):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/valid')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            bodies = {
                '/valid': json.dumps({'strRoll': '下载回复🦊'}, ensure_ascii=False).encode('utf-8'),
                '/empty': b'{}',
                '/array': b'{"strRoll": ["invalid"]}',
                '/html': b'<html>not json</html>',
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(bodies[self.path])))
            self.end_headers()
            self.wfile.write(bodies[self.path])

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        assert env.plugin.api.download(base + '/redirect')['strRoll'] == '下载回复🦊'
        assert env.plugin.api.download(base + '/empty') == {}
        for suffix in ('/array', '/html'):
            with pytest.raises(env.plugin.store.InvalidInput):
                env.plugin.api.download(base + suffix)
        with pytest.raises(env.plugin.store.InvalidInput):
            env.plugin.api.download('file:///C:/private.json')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_actual_tk_editor_save_readonly_and_layout(env):
    root = tk.Tk()
    root.withdraw()
    manager = None
    try:
        manager = env.plugin.gui.Manager()
        manager.root.withdraw()
        manager.scope_var.set(manager.accounts[1]['label'])
        manager.change_scope()
        assert manager.selection == 1
        entry = next(item for item in manager.snapshot['entries'] if item['key'] == 'strRoll')
        manager.set_editor(entry)
        manager.editor.delete('1.0', 'end')
        manager.editor.insert('1.0', 'GUI 实际保存')
        assert manager.dirty()
        manager.save()
        assert not manager.dirty()
        assert env.webui.gui_parity.replies_snapshot(env.proc, env.bots[0])['strRoll'] == 'GUI 实际保存'
        manager.pack_var.set('2. smp')
        manager.change_pack()
        manager.set_editor(manager.snapshot['entries'][0])
        assert str(manager.editor['state']) == 'disabled'
        manager.root.update_idletasks()
        assert manager.root.winfo_reqwidth() >= 850
        assert manager.tree.get_children()
    finally:
        if manager is not None:
            manager.close()
        root.destroy()


def test_first_commands_and_help_after_opk_extraction_deleted(env, monkeypatch):
    plugin_root = Path(env.plugin.__file__).parent
    archive = env.tmp / 'MultiCustomSwitch.opk'
    with zipfile.ZipFile(archive, 'w') as package:
        for path in plugin_root.rglob('*'):
            if path.is_file() and path.suffix in {'.py', '.json', '.md', '.html'}:
                package.write(path, path.relative_to(plugin_root).as_posix())
    extracted = env.tmp / 'plugin' / 'tmp' / 'MultiCustomSwitch'
    extracted.mkdir(parents=True)
    with zipfile.ZipFile(archive) as package:
        package.extractall(extracted)
    env.plugin.runtime.uninstall()
    for name in list(sys.modules):
        if name == 'MultiCustomSwitch' or name.startswith('MultiCustomSwitch.'):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(extracted.parent))
    plugin = importlib.import_module('MultiCustomSwitch')
    plugin.main.Event.init(None, env.proc)
    # 验证递归删除目标是本次测试的独立临时目录。
    assert extracted.resolve().is_relative_to(env.tmp.resolve())
    shutil.rmtree(extracted)
    try:
        plugin.main.Event.init_after(None, env.proc)
        assert plugin.runtime.STORE is not None
        event = env.event(message='.mcs help')
        plugin.main.Event.group_message(event, env.proc)
        assert event.sent and '1 = default' in event.sent[-1]
        assert '编写帮助' in plugin.api.dispatch({'op': 'help'})['markdown']
        assert plugin.api.dispatch({'op': 'snapshot', 'scope': env.bots[0], 'selection': 1})['entries']
        menu = env.event()
        menu.bot_info = None
        menu.data = types.SimpleNamespace(
            namespace='MultiCustomSwitch',
            event=plugin.api.EVENT,
            payload={'op': 'help'},
            webui={'request_id': 'after-opk', 'session': 's'},
        )
        plugin.main.Event.menu(menu, env.proc)
        assert menu.sent[0][2]['ok']
    finally:
        plugin.runtime.uninstall()
