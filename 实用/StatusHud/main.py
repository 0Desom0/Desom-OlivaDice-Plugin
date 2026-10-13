"""官方原生模板事件入口。"""

import sys

import OlivOS

from . import commands, hooks
from .sn import SnProvider
from .storage import Storage, StorageError

gProc = None
gManager = None


class Event:
    def init(plugin_event, Proc):
        global gProc
        gProc = Proc

    def init_after(plugin_event, Proc):
        global gProc, gManager
        gProc = Proc
        core = sys.modules.get('OlivaDiceCore')
        if core is None:
            Proc.log(4, 'StatusHud 需要先装载 OlivaDiceCore。', [('StatusHud', 'default')])
            return
        storage = Storage(core)
        manager = hooks.HookManager(OlivOS, core, Proc, storage, SnProvider(core))
        try:
            for bot_hash in Proc.Proc_data.get('bot_info_dict', {}):
                try:
                    storage.initialize(bot_hash)
                except StorageError as error:
                    manager.log('初始化 HUD 设置失败，保留现有数据', error)
            manager.install()
        except Exception as error:
            manager.uninstall()
            manager.log('HUD 接入失败', error)
            return
        gManager = manager
        Proc.log(2, 'StatusHud 已接入 OneDice；初始全局默认关闭。', [('StatusHud', 'default')])

    def private_message(plugin_event, Proc):
        unity_reply(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        unity_reply(plugin_event, Proc)

    def save(plugin_event, Proc):
        global gManager
        if gManager is not None:
            gManager.uninstall()
            gManager = None


def unity_reply(plugin_event, Proc):
    if gManager is None:
        return
    try:
        commands.handle(plugin_event, Proc, gManager, OlivOS)
    except Exception as error:
        gManager.log('HUD 命令处理失败', error)
