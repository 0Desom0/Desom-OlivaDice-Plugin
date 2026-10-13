"""本机真实规则插件的 OneDice/HUD 接入回归。"""

import importlib
import sys
from pathlib import Path

import pytest


def extension(runtime, monkeypatch, name):
    if name == 'OlivaDiceCore':
        return runtime.core
    for key in list(sys.modules):
        if key == name or key.startswith(name + '.'):
            monkeypatch.delitem(sys.modules, key)
    root = Path(__file__).resolve().parents[2]
    if not (root / name).is_dir():
        pytest.skip(f'本地缺少 {name} 源码')
    module = importlib.import_module(name)
    for bot in runtime.proc.Proc_data['bot_info_dict']:
        runtime.core.helpDocData.dictHelpDoc[bot] = {}
    module.main.Event.init(None, runtime.proc)
    module.main.Event.init_after(None, runtime.proc)
    if name == 'OlivaDiceMS':
        runtime.core.userConfig.setUserConfigByKey('100', 'group', 'qq', 'groupTemplate', 'ms', 'bot')
    return module


CASES = [
    ('OlivaDiceShouHun', '.sh 3#2'),
    ('OlivaDiceSanchi', '.tq 3'),
    ('OlivaDiceMS', '.ms'),
    ('OlivaDiceCore', '.ra 侦查'),
    ('OlivaDiceTA', '.ta 1'),
]


@pytest.mark.parametrize('name,command', CASES)
@pytest.mark.usefixtures('hud_enabled')
def test_real_plugin_normal_rolls_add_hud(runtime, monkeypatch, name, command):
    module = extension(runtime, monkeypatch, name)
    runtime.card()
    event = runtime.Event(command)
    runtime.proc.run(event, module.main.Event.group_message, namespace=name)
    assert event.sent, runtime.proc.logs
    assert event.sent[0][2].startswith('『Alice HP10/12'), event.sent
    assert '』\n\n' in event.sent[0][2]
    assert sum(text.count('Alice HP10/12') for _, _, text in event.sent) == 1


@pytest.mark.parametrize('name,command', CASES)
@pytest.mark.usefixtures('hud_enabled')
def test_real_plugin_proxy_uses_target_settings(runtime, monkeypatch, name, command):
    module = extension(runtime, monkeypatch, name)
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    runtime.storage.set_user('bot', '1', 'qq', False)
    event = runtime.Event(command + ' [CQ:at,qq=2]', role='owner')
    runtime.proc.run(event, module.main.Event.group_message, namespace=name)
    assert event.sent, runtime.proc.logs
    assert event.sent[0][2].startswith('『Bob HP10/12'), event.sent
    assert all('Alice HP10/12' not in text for _, _, text in event.sent)
    runtime.storage.set_user('bot', '1', 'qq', True)
    runtime.storage.set_user('bot', '2', 'qq', False)
    event = runtime.Event(command + ' [CQ:at,qq=2]', role='owner')
    runtime.proc.run(event, module.main.Event.group_message, namespace=name)
    assert all(' HP10/12' not in text for _, _, text in event.sent)


@pytest.mark.parametrize('name,command', [
    ('OlivaDiceShouHun', '.shh 3#2'),
    ('OlivaDiceSanchi', '.tqh 3'),
    ('OlivaDiceCore', '.rah 侦查'),
])
@pytest.mark.parametrize('proxy', [False, True])
@pytest.mark.usefixtures('hud_enabled')
def test_real_plugin_hidden_notices_and_results(runtime, monkeypatch, name, command, proxy):
    module = extension(runtime, monkeypatch, name)
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    if proxy:
        command += ' [CQ:at,qq=2]'
    event = runtime.Event(command, role='owner')
    runtime.proc.run(event, module.main.Event.group_message, namespace=name)
    assert event.sent[0][0] == 'group'
    assert ' HP10/12' not in event.sent[0][2], event.sent
    assert event.sent[1][:2] == ('private', '1')
    expected = 'Bob' if proxy else 'Alice'
    assert event.sent[1][2].startswith('『' + expected + ' HP10/12'), event.sent
    assert '』\n\n' in event.sent[1][2]
    if proxy:
        assert 'Alice HP10/12' not in event.sent[1][2]


@pytest.mark.parametrize('name,command', [
    ('OlivaDiceShouHun', '.sh set show'),
    ('OlivaDiceSanchi', '.tqav'),
    ('OlivaDiceMS', '.ms invalid'),
    ('OlivaDiceCore', '.ra'),
    ('OlivaDiceTA', '.tcs'),
])
def test_real_plugin_without_roll_keeps_original_reply(runtime, monkeypatch, name, command):
    module = extension(runtime, monkeypatch, name)
    runtime.card()
    event = runtime.Event(command)
    runtime.proc.run(event, module.main.Event.group_message, namespace=name)
    state = getattr(event, '_statushud_message_state', None)
    assert state is None or not state.rolls
    assert all('Alice HP10/12' not in text for _, _, text in event.sent)


@pytest.mark.parametrize('name,command', [
    ('OlivaDiceShouHun', '.shh 3#2'),
    ('OlivaDiceSanchi', '.tqh 2#3'),
])
@pytest.mark.usefixtures('hud_enabled')
def test_extension_custom_hidden_notice_keeps_text_and_observer_gets_hud(runtime, monkeypatch, name, command):
    module = extension(runtime, monkeypatch, name)
    runtime.card()
    observer = runtime.core.userConfig.getUserHash('2', 'user', 'qq')
    runtime.core.userConfig.setUserConfigByKey('2', 'user', 'qq', 'userName', 'observer', 'bot')
    runtime.core.userConfig.setUserConfigByKey('100', 'group', 'qq', 'groupObList', [observer], 'bot')
    keys = ('strShHideShow',) if name == 'OlivaDiceShouHun' else ('strTQHideShow', 'strTQHideShowMore')
    for key in keys:
        runtime.core.msgCustom.dictStrCustomDict['bot'][key] = 'CUSTOM {tName} notice'
    event = runtime.Event(command)
    runtime.proc.run(event, module.main.Event.group_message, namespace=name)
    assert event.sent[0][2] == 'CUSTOM Alice notice'
    private = [text for kind, _, text in event.sent if kind == 'private']
    assert len(private) == 2
    assert all(text.startswith('『Alice HP10/12') and text.count('Alice HP10/12') == 1 for text in private)


@pytest.mark.usefixtures('hud_enabled')
def test_extension_rival_rolls_show_both_users(runtime, monkeypatch):
    module = extension(runtime, monkeypatch, 'OlivaDiceSanchi')
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    event = runtime.Event('.tqav 1#1 [CQ:at,qq=2]')
    runtime.proc.run(event, module.main.Event.group_message, namespace='OlivaDiceSanchi')
    lines = event.sent[0][2].splitlines()
    assert lines[0].startswith('『Alice HP10/12') and lines[0].endswith('』')
    assert lines[1].startswith('『Bob HP10/12') and lines[1].endswith('』')
    assert lines[2] == ''
    assert lines[3]



@pytest.mark.parametrize('enabled_users', [[], ['1'], ['2'], ['1', '2']])
def test_extension_rival_reads_each_users_switch(runtime, monkeypatch, enabled_users):
    module = extension(runtime, monkeypatch, 'OlivaDiceSanchi')
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    for user in ('1', '2'):
        runtime.storage.set_user('bot', user, 'qq', user in enabled_users)
    event = runtime.Event('.tqav 1#1 [CQ:at,qq=2]')
    runtime.proc.run(event, module.main.Event.group_message, namespace='OlivaDiceSanchi')
    assert event.sent
    result = event.sent[0][2]
    if enabled_users:
        expected = '\n'.join(f"『{runtime.sn.get(user, 'qq', '100')}』" for user in enabled_users) + '\n\n'
        assert result.startswith(expected)
        hud = result.split('\n\n', 1)[0]
        for user, name in [('1', 'Alice'), ('2', 'Bob')]:
            assert (name in hud) is (user in enabled_users)
    else:
        assert not result.startswith('『')
