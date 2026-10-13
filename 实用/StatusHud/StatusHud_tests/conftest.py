"""使用本地真实 Core/OneDice 和消息解析器，仅替换宿主与远端发送。"""

import copy
import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def pytest_addoption(parser):
    parser.addoption('--core-source', default=None)
    parser.addoption('--olivos-source', default=None)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runtime(request, monkeypatch, tmp_path):
    core_source = request.config.getoption('--core-source')
    olivos_source = request.config.getoption('--olivos-source')
    if not core_source or not olivos_source:
        pytest.skip('需指定 --core-source 与 --olivos-source 来运行真实源码集成测试')
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(PLUGIN_ROOT))
    monkeypatch.syspath_prepend(str(Path(core_source)))
    for name in list(sys.modules):
        if name == 'StatusHud' or name.startswith('StatusHud.') or name == 'OlivaDiceCore' or name.startswith(
            'OlivaDiceCore.',
        ):
            monkeypatch.delitem(sys.modules, name)
    olivos = ModuleType('OlivOS')
    message_api = _load('statushud_reference_message', Path(olivos_source) / 'OlivOS/core/core/messageAPI.py')
    olivos.messageAPI = message_api
    olivos.infoAPI = SimpleNamespace(OlivOS_Version='test', OlivOS_SVN=190)

    class FakeEvent:
        def __init__(self, message='.r 1d6', user_id='1', bot='bot', group='100', host=None, role='member'):
            kind = 'private_message' if group is None else 'group_message'
            self.bot_info = SimpleNamespace(hash=bot, id='999', platform={'platform': 'qq'})
            self.base_info = {'self_id': '999'}
            self.platform = {'platform': 'qq', 'sdk': 'onebot', 'model': 'default'}
            self.plugin_info = {'func_type': kind, 'message_mode_tx': 'old_string', 'message_mode_rx': 'old_string'}
            self.data = SimpleNamespace(
                user_id=str(user_id), group_id=group, host_id=host, message=message, raw_message=message,
                message_sdk=message_api.Message_templet('old_string', message), extend={},
                sender={'name': f'user{user_id}', 'nickname': f'user{user_id}', 'role': role},
            )
            self.blocked = False
            self.sent = []
            self.cards = []
            self.indeAPI = None

        def _text(self, message):
            if isinstance(message, message_api.Message_templet):
                return message.get('old_string')
            return message

        def reply(self, message, flag_log=True, remote=False):
            if not remote:
                kind = 'private' if self.data.group_id is None else 'group'
                target = self.data.user_id if kind == 'private' else self.data.group_id
                self.sent.append((kind, str(target), self._text(message)))
            return 'reply-result'

        def send(self, send_type, target_id, message, host_id=None, flag_log=True, remote=False):
            if not remote:
                self.sent.append((send_type, str(target_id), self._text(message)))
            return 'send-result'

        def set_block(self):
            self.blocked = True

        def get_group_member_info(self, group_id, user_id, host_id=None, no_cache=False):
            return {'active': True, 'data': {'name': f'user{user_id}', 'nickname': f'user{user_id}'}}

        def get_stranger_info(self, user_id, no_cache=False):
            return {'active': True, 'data': {'name': f'user{user_id}', 'nickname': f'user{user_id}'}}

        def set_group_card(self, **kwargs):
            self.cards.append(kwargs)

    olivos.API = SimpleNamespace(Event=FakeEvent, bot_info_T=SimpleNamespace)
    monkeypatch.setitem(sys.modules, 'OlivOS', olivos)
    core = importlib.import_module('OlivaDiceCore')
    core.onediceOverride.random_default_mode = 'default'

    class FakeProc:
        def __init__(self):
            self.Proc_data = {'bot_info_dict': {
                key: SimpleNamespace(hash=key, platform={'platform': 'qq'}) for key in ('bot', 'slave', 'other')
            }}
            self.logs = []

        def log(self, *args, **kwargs):
            self.logs.append((args, kwargs))

        def plugin_event_router(self, plugin_event, plugin_model, plugin_name):
            kind = plugin_event.plugin_info['func_type']
            plugin_event.plugin_info.update(namespace=plugin_name, message_mode_tx=plugin_model.mode)
            plugin_event.data.message = plugin_event.data.message_sdk.get(plugin_model.mode)
            return getattr(plugin_model.main.Event, kind)(plugin_event=plugin_event, Proc=self)

        def run(self, event, callback=None, namespace='OlivaDiceCore', mode='old_string'):
            if callback is None:
                callback = core.main.Event.group_message if event.data.group_id is not None else (
                    core.main.Event.private_message
                )
            callbacks = SimpleNamespace(group_message=callback, private_message=callback)
            model = SimpleNamespace(main=SimpleNamespace(Event=callbacks), mode=mode)
            return self.plugin_event_router(event, model, namespace)

    proc = FakeProc()
    core.data.global_Proc = proc
    core.console.initConsoleSwitchByBotDict(proc.Proc_data['bot_info_dict'])
    for bot in proc.Proc_data['bot_info_dict']:
        core.msgCustom.dictStrCustomDict[bot] = copy.deepcopy(core.msgCustom.dictStrCustom)
        core.console.dictConsoleSwitch[bot]['messageSplitDelay'] = 0
    core.pcCard.dataPcCardTemplateDefaultInit()
    core.pcCard.dataPcCardTemplateInit()
    core.pcCard.dictPcCardTemplateDefault['unity']['default'] = copy.deepcopy(
        core.pcCardData.dictPcCardTemplateDefault['default'],
    )
    core.pcCard.dictPcCardTemplateDefault['unity']['default']['snTitle'] = '{tName} HP{HP}/{HPMAX} SAN{SAN}/{SANMAX}'
    plugin = importlib.import_module('StatusHud')
    from StatusHud.hooks import HookManager
    from StatusHud.sn import SnProvider
    from StatusHud.storage import Storage

    storage = Storage(core, tmp_path / 'plugin/data/StatusHud')
    sn = SnProvider(core)
    manager = HookManager(olivos, core, proc, storage, sn)
    manager.install()

    def card(user='1', name='Alice', title=None, hag_id=None):
        pc = core.pcCard
        pc_hash = pc.getPcHash(user, 'qq')
        pc.dictPcCardSelection['unity'][pc_hash] = {'selection': name, 'lockList': {}}
        pc.dictPcCardData['unity'][pc_hash] = {
            name: {'HP': 10, 'HPMAX': 12, 'SAN': 65, 'DEX': 55, '克苏鲁神话': 5, '侦查': 75},
        }
        notes = {}
        if title is not None:
            key = '名片'
            if hag_id is not None:
                key += core.userConfig.getUserHash(hag_id, 'group', 'qq')[:8]
            notes[key] = title
        pc.dictPcCardTemplate['unity'][pc_hash] = {
            name: {'template': 'default', 'checkRules': 'default', 'noteRecord': notes},
        }
        return pc_hash

    def hud(event):
        return proc.run(
            event, lambda plugin_event, Proc: plugin.commands.handle(plugin_event, Proc, manager, olivos),
            namespace='StatusHud', mode='olivos_string',
        )

    rt = SimpleNamespace(
        core=core, olivos=olivos, proc=proc, manager=manager, storage=storage, sn=sn,
        Event=FakeEvent, card=card, hud=hud, path=tmp_path,
    )
    yield rt
    manager.uninstall()


@pytest.fixture
def hud_enabled(runtime):
    """显式开启全局默认，供 HUD 显示功能测试使用。"""
    runtime.storage.set_global('bot', True)
