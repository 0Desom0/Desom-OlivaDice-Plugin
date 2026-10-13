"""加载本机真实 Core/WebUI 函数；只替换宿主 SDK、网络账号和消息出口。"""

import ast
import hashlib
import html
import importlib
import importlib.util
import os
import sys
import time
import types
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
PROJECT = PLUGIN.parents[3] / '青果主项目'
CORE = Path(os.environ.get('OLIVADICE_CORE_SOURCE', PROJECT / 'OlivaDiceCore' / 'OlivaDiceCore'))
WEBUI = PROJECT / 'OlivaDiceWebUI' / 'OlivaDiceWebUI'


def source_module(name, path, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def source_functions(path, names, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(definitions) == len(names)
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), namespace)


class FakeEvent:
    def __init__(self, sdk_event=None, log_func=None):
        self.bot_info = sdk_event
        self.sent = []
        self.blocked = False

    def get_login_info(self):
        return {'active': True, 'data': {'name': f'真实骰子{self.bot_info.id}'}}

    def set_block(self):
        self.blocked = True

    def send(self, kind, target, value):
        self.sent.append((kind, target, value))
        return True


class FakeProc:
    def __init__(self):
        self.Proc_data = {
            'bot_info_dict': {
                bot: types.SimpleNamespace(
                    hash=bot, id=number, platform={'platform': 'qq', 'sdk': 'onebot', 'model': 'all'}
                )
                for bot, number in [('a' * 32, 1001), ('b' * 32, 1002)]
            }
        }
        self.logs = []

    def get_plugin_list(self):
        return ['OlivaDiceCore', 'OlivaDiceWebUI', 'OlivaDiceNativeGUI', 'MultiCustomSwitch']

    def log(self, *args, **kwargs):
        self.logs.append((args, kwargs))

    def plugin_event_router(self, event, plugin_model, plugin_name):
        return getattr(plugin_model.main.Event, event.plugin_info['func_type'])(event, self)


@pytest.fixture
def env(tmp_path, monkeypatch):
    if not CORE.is_dir():
        pytest.fail('找不到本机 Core 源码，请设置 OLIVADICE_CORE_SOURCE。')
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(PLUGIN.parent))
    for name in list(sys.modules):
        if name == 'MultiCustomSwitch' or name.startswith('MultiCustomSwitch.'):
            monkeypatch.delitem(sys.modules, name)
    sdk = types.ModuleType('OlivOS')
    sdk.API = types.SimpleNamespace(Event=FakeEvent, bot_info_T=types.SimpleNamespace)
    sdk.contentAPI = types.SimpleNamespace(fake_sdk_event=lambda bot_info, fakename: bot_info)
    monkeypatch.setitem(sys.modules, 'OlivOS', sdk)
    core = types.ModuleType('OlivaDiceCore')
    monkeypatch.setitem(sys.modules, 'OlivaDiceCore', core)
    core.msgCustom = source_module('OlivaDiceCore.msgCustom', CORE / 'msgCustom.py', monkeypatch)
    core.msgCustomManager = source_module('OlivaDiceCore.msgCustomManager', CORE / 'msgCustomManager.py', monkeypatch)
    core.helpDoc = source_module('OlivaDiceCore.helpDoc', CORE / 'helpDoc.py', monkeypatch)
    namespace = {'OlivaDiceCore': core, 'OlivOS': sdk, 'hashlib': hashlib, 'time': time, 'contextFeq': 0.1}
    context_names = ['contextRegHash', 'replyCONTEXT_regWait', 'replyCONTEXT_regGet']
    source_functions(CORE / 'msgReplyModel.py', context_names, namespace)
    core.msgReplyModel = types.SimpleNamespace(**{name: namespace[name] for name in context_names})
    core.data = types.SimpleNamespace(dataDirRoot=str(tmp_path / 'OlivaDice'))
    core.userConfig = types.SimpleNamespace()
    namespace = {'hashlib': hashlib}
    source_functions(CORE / 'userConfig.py', ['getUserHash'], namespace)
    core.userConfig.getUserHash = namespace['getUserHash']
    proc = FakeProc()
    bots = list(proc.Proc_data['bot_info_dict'])
    core.console = types.SimpleNamespace(
        dictConsoleSwitch={bot: {'masterList': [['123', 'qq']]} for bot in bots},
        getConsoleSwitchByHash=lambda key, bot: 25,
    )
    core.crossHook = types.SimpleNamespace(
        dictHookList={'prefix': ['.', '。', '/'], 'replyContextFliter': []},
        dictReplyContextReg={},
        dictHookFunc={'msgFormatHook': lambda text, values: text},
    )
    core.drawCard = types.SimpleNamespace(draw=lambda **kwargs: None)
    namespace = {'OlivaDiceCore': core, 'html': html}
    names = [
        'htmlUnescape',
        'msgIsCommand',
        'skipSpaceStart',
        'isMatchWordStart',
        'getMatchWordStartRight',
        'getHagIDFromMsg',
    ]
    source_functions(CORE / 'msgReply.py', names, namespace)
    core.msgReply = types.SimpleNamespace(**{name: namespace[name] for name in names})
    core.msgReply.replyMsg = lambda event, text: event.sent.append(text)
    namespace = {'OlivaDiceCore': core}
    source_functions(CORE / 'ordinaryInviteManager.py', ['isInMasterList'], namespace)
    core.ordinaryInviteManager = types.SimpleNamespace(isInMasterList=namespace['isInMasterList'])
    core.helpDocData = types.SimpleNamespace(dictHelpDoc={bot: {} for bot in bots})
    for bot in bots:
        core.msgCustom.dictStrCustomDict[bot] = dict(core.msgCustom.dictStrCustom)
        core.msgCustom.dictStrCustomUpdateDict[bot] = {}
    webui = types.ModuleType('OlivaDiceWebUI')
    webui.__path__ = [str(WEBUI)]
    monkeypatch.setitem(sys.modules, 'OlivaDiceWebUI', webui)
    webui.service = source_module('OlivaDiceWebUI.service', WEBUI / 'service.py', monkeypatch)
    webui.gui_parity = source_module('OlivaDiceWebUI.gui_parity', WEBUI / 'gui_parity.py', monkeypatch)
    native = types.ModuleType('OlivaDiceNativeGUI')
    native.GUI = types.ModuleType('OlivaDiceNativeGUI.GUI')
    native.msgCustom = types.SimpleNamespace(dictStrCustomNote={'strRoll': '真实 Core 掷骰回复说明'})
    monkeypatch.setitem(sys.modules, 'OlivaDiceNativeGUI', native)
    plugin = importlib.import_module('MultiCustomSwitch')
    store = plugin.runtime.install(proc)

    def event(message='.mcs', bot=bots[0], group='10', role='admin', user='123', host=None):
        value = FakeEvent(proc.Proc_data['bot_info_dict'][bot])
        value.data = types.SimpleNamespace(
            message=message,
            group_id=group,
            host_id=host,
            user_id=user,
            sender={'name': '测试用户', 'role': role},
            extend={},
        )
        value.platform = {'platform': 'qq'}
        value.base_info = {'self_id': value.bot_info.id}
        value.plugin_info = {'func_type': 'group_message' if group is not None else 'private_message'}
        return value

    yield types.SimpleNamespace(
        plugin=plugin,
        core=core,
        webui=webui,
        proc=proc,
        store=store,
        bots=bots,
        event=event,
        tmp=tmp_path,
        native=native,
    )
    plugin.runtime.uninstall()
    plugin.api.clear_transfers()
