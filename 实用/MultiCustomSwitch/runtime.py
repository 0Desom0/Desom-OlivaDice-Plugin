"""通过宿主已有事件路由隔离回复；管理面板始终访问原始 Core 字典。"""

import contextvars
import functools
import sys
import types

import OlivaDiceCore
import OlivOS

from . import files, msgCustom
from .store import ReplyStore

CONTEXT = contextvars.ContextVar('mcs_reply_context', default=None)
ORIGINAL_MODE = contextvars.ContextVar('mcs_original_mode', default=False)
STORE = None
INIT_ERROR = None
_RESTORE = []


class ContextReplies(dict):
    def original_get(self, key, default=None):
        return dict.get(self, key, default)

    def __getitem__(self, key):
        context = CONTEXT.get()
        if not ORIGINAL_MODE.get() and context is not None and key == context[0]:
            return context[1]
        return dict.__getitem__(self, key)

    def get(self, key, default=None):
        if key not in self:
            return default
        return self[key]


def _patch(target, key, value):
    existed = hasattr(target, key)
    original = getattr(target, key, None)
    _RESTORE.append((target, key, existed, original))
    setattr(target, key, value)


def _protect(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        token = ORIGINAL_MODE.set(True)
        try:
            with files.LOCK:
                return func(*args, **kwargs)
        finally:
            ORIGINAL_MODE.reset(token)

    return wrapped


def _original_command(event):
    if not hasattr(event.data, 'message'):
        return False
    # commands 已在导入期加载；包括引用消息、@ Bot 的 .str，仍管理 default。
    from .commands import command_text

    return command_text(event, command_name='str') is not None


def install(proc):
    global STORE, INIT_ERROR
    uninstall()
    INIT_ERROR = None
    STORE = ReplyStore(proc)
    core = OlivaDiceCore
    with files.LOCK:
        for bot in STORE.bots:
            current = core.msgCustom.dictStrCustomDict.setdefault(bot, {})
            for key, value in msgCustom.dictStrCustom.items():
                current.setdefault(key, value)
            core.helpDocData.dictHelpDoc.setdefault(bot, {})['mcs'] = msgCustom.COMMAND_HELP
        _patch(core.msgCustom, 'dictStrCustomDict', ContextReplies(core.msgCustom.dictStrCustomDict))
        manager = core.msgCustomManager
        _patch(manager, 'open', files.locked_open)
        for key in (
            'setMsgCustomByBotHash',
            'saveMsgCustomByBotHash',
            'initMsgCustom',
            'pruneMsgCustomByBotHash',
            'pruneAndSaveMsgCustom',
            'saveMsgCustom',
        ):
            # 旧版 Core 仅有初始化与保存接口；不存在的新版辅助函数无需包装。
            original = getattr(manager, key, None)
            if callable(original):
                _patch(manager, key, _protect(original))
        # 与现有 WebUI 共用同一把可重入锁，避免互相持锁后等待另一把锁。
        webui = sys.modules.get('OlivaDiceWebUI')
        service = getattr(webui, 'service', None)
        if service is not None and hasattr(service, 'LOCK'):
            _patch(service, 'LOCK', files.LOCK)
        gui = getattr(sys.modules.get('OlivaDiceNativeGUI'), 'GUI', None)
        if gui is not None:
            _patch(gui, 'open', files.locked_open)
        original_router = proc.plugin_event_router
        installed_store = STORE

        def router(this, event, plugin_model, plugin_name):
            context = None
            function = event.plugin_info.get('func_type')
            bot_info = getattr(event, 'bot_info', None)
            if function != 'menu' and bot_info is not None and bot_info.hash in installed_store.bots:
                if not _original_command(event):
                    try:
                        context = (bot_info.hash, installed_store.effective(event))
                    except Exception:
                        proc.log(4, 'MultiCustomSwitch: 无法解析事件回复，当前事件使用 Core 原始回复。')
            token = CONTEXT.set(context)
            try:
                return original_router(event, plugin_model, plugin_name)
            finally:
                CONTEXT.reset(token)

        _patch(proc, 'plugin_event_router', types.MethodType(router, proc))
    # 网络调用不持有文件锁。以账号登录信息获取真实 Bot 名。
    for bot, info in STORE.bots.items():
        try:
            event = OlivOS.API.Event(
                OlivOS.contentAPI.fake_sdk_event(bot_info=info, fakename='MultiCustomSwitch'), proc.log
            )
            result = event.get_login_info()
            if isinstance(result, dict) and result.get('active') and isinstance(result.get('data'), dict):
                name = result['data'].get('name')
                if isinstance(name, str) and name:
                    with files.LOCK:
                        STORE.bot_names[bot] = name
        except Exception:
            proc.log(3, 'MultiCustomSwitch: 登录名称暂不可用，smp 暂显示账号 ID。')
    return STORE


def uninstall():
    global STORE
    with files.LOCK:
        for target, key, existed, original in reversed(_RESTORE):
            if target is OlivaDiceCore.msgCustom and key == 'dictStrCustomDict':
                # 面板可替换整个 bot 字典，卸载时保留安装后发生的所有原始回复修改。
                current = getattr(target, key)
                original.clear()
                original.update(dict.items(current))
            if existed:
                setattr(target, key, original)
            else:
                delattr(target, key)
        _RESTORE.clear()
        STORE = None
