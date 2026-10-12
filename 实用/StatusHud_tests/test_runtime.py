import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.mark.parametrize('command', ['.r 1d6', '.r 4#1d6', '.r 1+2', '.r 1d0', '.ra 侦查', '.sc 0/1'])
def test_real_core_rolls(runtime, command):
    runtime.card()
    event = runtime.Event(command)
    runtime.proc.run(event)
    assert event.sent
    assert event.sent[0][2].startswith('Alice HP10/12 SAN')
    assert sum(text.count('Alice HP10/12') for _, _, text in event.sent) == 1


def test_no_roll_or_no_card_is_unchanged(runtime):
    event = runtime.Event('.r 1d6')
    runtime.proc.run(event)
    assert event.sent and not event.sent[0][2].startswith('Alice')
    runtime.card()
    event = runtime.Event('.hud show')
    runtime.hud(event)
    assert event.sent[0][2].startswith('HUD：开启')
    assert 'Alice' not in event.sent[0][2]


@pytest.mark.parametrize('prefix', ['.', '。', '/'])
@pytest.mark.parametrize('action,enabled', [('hudon', True), ('HUD off', False), ('hud', False)])
def test_commands_and_greedy_matching(runtime, prefix, action, enabled):
    event = runtime.Event(prefix + action)
    runtime.hud(event)
    assert event.blocked
    assert runtime.storage.status('bot', '1', 'qq')['enabled'] is enabled


def test_linked_defaults_and_overrides(runtime):
    runtime.core.console.setAccountRelation('slave', 'bot')
    runtime.storage.initialize('slave')
    runtime.storage.set_user('slave', '1', 'qq', True)
    runtime.storage.set_global('slave', False)
    assert runtime.storage.status('bot', '1', 'qq')['enabled']
    assert not runtime.storage.status('bot', '2', 'qq')['enabled']
    assert not (runtime.storage.root / 'slave').exists()
    assert not (runtime.storage.root / 'bot/user' / (runtime.core.userConfig.getUserHash('2', 'user', 'qq') + '.json')).exists()


def test_global_permission_uses_current_bot(runtime):
    runtime.core.console.setAccountRelation('slave', 'bot')
    runtime.core.console.dictConsoleSwitch['bot']['masterList'] = [['1', 'qq']]
    event = runtime.Event('.hud global off', bot='slave')
    runtime.hud(event)
    assert '只有当前 bot' in event.sent[0][2]
    assert runtime.storage.status('slave', '1', 'qq')['enabled']
    runtime.core.console.dictConsoleSwitch['slave']['masterList'] = [['1', 'qq']]
    event = runtime.Event('.hud global off', bot='slave')
    runtime.hud(event)
    assert not runtime.storage.status('bot', '2', 'qq')['enabled']


def test_proxy_uses_target_setting_and_last_at(runtime):
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    runtime.card('3', 'Carol')
    runtime.storage.set_user('bot', '1', 'qq', False)
    event = runtime.Event('.ra 侦查 [CQ:at,qq=2][CQ:at,qq=3]', role='admin')
    runtime.proc.run(event)
    assert event.sent[0][2].startswith('Carol HP10/12')
    assert not event.sent[0][2].startswith('Alice')
    runtime.storage.set_user('bot', '3', 'qq', False)
    event = runtime.Event('.ra 侦查 [CQ:at,qq=3]', role='admin')
    runtime.proc.run(event)
    assert not event.sent[0][2].startswith('Carol')


def test_unprivileged_at_and_plain_r_do_not_become_proxy(runtime):
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    event = runtime.Event('.ra 侦查 [CQ:at,qq=2]')
    runtime.proc.run(event)
    assert 'Bob HP10/12' not in event.sent[0][2]
    assert 'Alice HP10/12' not in event.sent[0][2]
    event = runtime.Event('.r 1d6 [CQ:at,qq=2]', role='admin')
    runtime.proc.run(event)
    assert event.sent[0][2].startswith('Alice HP10/12')


def test_hidden_notice_is_unchanged_and_all_private_results_have_hud(runtime):
    runtime.card()
    observer = runtime.core.userConfig.getUserHash('2', 'user', 'qq')
    runtime.core.userConfig.setUserConfigByKey('2', 'user', 'qq', 'userName', 'observer', 'bot')
    runtime.core.userConfig.setUserConfigByKey('100', 'group', 'qq', 'groupObList', [observer], 'bot')
    event = runtime.Event('.rh 1d6')
    runtime.proc.run(event)
    assert event.sent[0][0] == 'group'
    assert 'Alice HP10/12' not in event.sent[0][2]
    private = [text for kind, _, text in event.sent if kind == 'private']
    assert len(private) == 2
    assert all(text.startswith('Alice HP10/12') for text in private)


def test_hidden_proxy_keeps_initiator_delivery(runtime):
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    event = runtime.Event('.rah 侦查 [CQ:at,qq=2]', role='owner')
    runtime.proc.run(event)
    assert 'Bob HP10/12' not in event.sent[0][2]
    assert event.sent[1][:2] == ('private', '1')
    assert event.sent[1][2].startswith('Bob HP10/12')


def test_private_sn_uses_global_selection(runtime):
    runtime.card('1', 'Alice', 'Private {tName}')
    event = runtime.Event('.r 1d6', group=None)
    runtime.proc.run(event)
    assert event.sent[0][2].startswith('Private Alice\n')


def test_sn_precedence_group_binding_and_no_card_writes(runtime):
    pc_hash = runtime.card('1', 'Alice', 'Global {tName}')
    pc = runtime.core.pcCard
    pc.dictPcCardSelection['unity'][pc_hash]['lockList']['guild|100'] = 'Bound'
    pc.dictPcCardData['unity'][pc_hash]['Bound'] = {'HP': 7, 'HPMAX': 9}
    pc.dictPcCardTemplate['unity'][pc_hash]['Bound'] = {
        'template': 'default',
        'noteRecord': {'名片' + runtime.core.userConfig.getUserHash('guild|100', 'group', 'qq')[:8]: 'Group {tName} {HP}'},
    }
    before = copy.deepcopy(pc.dictPcCardData)
    assert runtime.sn.get('1', 'qq', 'guild|100') == 'Group Bound 7'
    assert runtime.sn.get('1', 'qq', None) == 'Global Alice'
    assert pc.dictPcCardData == before
    assert not list(runtime.path.rglob('*.json'))


@pytest.mark.parametrize('team_command', ['.team r 1d6', '.team ra 侦查', '.team sc 0/1', '.team st HP+1d6'])
def test_team_displays_every_member(runtime, team_command):
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    runtime.core.userConfig.setUserConfigByKey(
        '100', 'group', 'qq', 'teamConfig', {'squad': {'members': ['1', '2']}}, 'bot',
    )
    runtime.core.userConfig.setUserConfigByKey('100', 'group', 'qq', 'activeTeam', 'squad', 'bot')
    event = runtime.Event(team_command, role='owner')
    runtime.proc.run(event)
    first = event.sent[-1][2].splitlines()[0]
    assert 'Alice HP' in first and 'Bob HP' in first


def test_third_party_direct_send_and_nested_roll_are_covered_once(runtime):
    runtime.card()
    event = runtime.Event('.custom')
    def handler(plugin_event, Proc):
        runtime.core.onedice.RD('1d6+1d6').roll()
        assert plugin_event.reply('first') == 'reply-result'
        plugin_event.reply('second')
        plugin_event.send('private', '1', 'secret')
    runtime.proc.run(event, handler, namespace='Custom')
    assert event.sent[0][2].startswith('Alice HP10/12')
    assert event.sent[1][2] == 'second'
    assert event.sent[2][2].startswith('Alice HP10/12')


def test_third_party_core_record_identifies_target(runtime):
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    event = runtime.Event('.custom')
    def handler(plugin_event, Proc):
        rd = runtime.core.onedice.RD('1d6')
        rd.roll()
        runtime.core.onediceOverride.saveRDDataUser(rd, 'bot', '2', 'qq')
        plugin_event.reply('result')
    runtime.proc.run(event, handler, namespace='Custom')
    assert event.sent[0][2].startswith('Bob HP10/12')
    assert 'Alice HP10/12' not in event.sent[0][2]


def test_page_header_follows_hud_and_subsequent_pages_do_not_repeat(runtime):
    runtime.card()
    runtime.core.console.dictConsoleSwitch['bot']['messageSplitGate'] = 20
    event = runtime.Event('.custom')
    def handler(plugin_event, Proc):
        runtime.core.onedice.RD('1d6').roll()
        runtime.core.msgReply.replyMsg(plugin_event, 'x' * 45)
    runtime.proc.run(event, handler)
    assert len(event.sent) == 3
    assert event.sent[0][2].startswith('Alice HP10/12')
    assert event.sent[0][2].splitlines()[1].startswith('---[第')
    assert all('Alice HP10/12' not in text for _, _, text in event.sent[1:])


def test_concurrent_events_and_context_cleanup(runtime):
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    barrier = threading.Barrier(2)
    def run(user):
        event = runtime.Event('.custom', user_id=user)
        def handler(plugin_event, Proc):
            runtime.core.onedice.RD('1d6').roll()
            barrier.wait(timeout=5)
            plugin_event.reply('result')
        runtime.proc.run(event, handler, namespace='Custom')
        return event.sent[0][2]
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(run, ('1', '2')))
    assert a.startswith('Alice') and b.startswith('Bob')
    assert runtime.manager.current.get() is None


def test_callback_exception_resets_context(runtime):
    event = runtime.Event('.custom')
    def handler(plugin_event, Proc):
        runtime.core.onedice.RD('1d6').roll()
        raise RuntimeError('test failure')
    with pytest.raises(RuntimeError):
        runtime.proc.run(event, handler)
    assert runtime.manager.current.get() is None


def test_event_carrying_background_worker(runtime):
    runtime.card()
    event = runtime.Event('.custom')
    def worker(plugin_event):
        runtime.core.onedice.RD('1d6').roll()
        plugin_event.reply('result')
    thread = threading.Thread(target=worker, args=(event,))
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert event.sent[0][2].startswith('Alice HP10/12')


def test_reload_does_not_stack_and_uninstall_restores(runtime):
    from StatusHud.hooks import HookManager
    original_roll = runtime.manager.patches[1][2]
    newer = HookManager(runtime.olivos, runtime.core, runtime.proc, runtime.storage, runtime.sn)
    newer.install()
    runtime.card()
    event = runtime.Event('.r 1d6')
    runtime.proc.run(event)
    assert event.sent[0][2].count('Alice HP10/12') == 1
    newer.uninstall()
    event = runtime.Event('.r 1d6')
    runtime.proc.run(event)
    assert 'Alice HP10/12' not in event.sent[0][2]
    assert runtime.core.onedice.RD.roll is not original_roll


def test_corrupt_storage_preserves_result_and_data(runtime):
    runtime.card()
    runtime.storage.initialize('bot')
    path = runtime.storage.root / 'bot/config.json'
    path.write_text('{broken', encoding='utf-8')
    event = runtime.Event('.r 1d6')
    runtime.proc.run(event)
    assert event.sent and not event.sent[0][2].startswith('Alice HP10/12')
    assert path.read_text(encoding='utf-8') == '{broken'


def test_multimodal_payload_and_literal_sn_are_preserved(runtime):
    runtime.card(title='A [CQ:at,qq=123]\nB')
    event = runtime.Event('.custom')
    def handler(plugin_event, Proc):
        runtime.core.onedice.RD('1d6').roll()
        plugin_event.reply('[OP:image,file=https://example.invalid/image.png]')
    runtime.proc.run(event, handler, namespace='Custom', mode='olivos_string')
    assert '[CQ:image,file=https://example.invalid/image.png]' in event.sent[0][2]
    assert '[CQ:at,qq=123]' not in event.sent[0][2]
    assert 'B\n' in event.sent[0][2]


def test_no_roll_direct_reply_preserves_payload_identity(runtime):
    event = runtime.Event('.custom')
    payload = runtime.olivos.messageAPI.Message_templet('old_string', 'unchanged [CQ:image,file=x]')
    def handler(plugin_event, Proc):
        plugin_event.reply(payload)
    runtime.proc.run(event, handler, namespace='Custom')
    assert event.sent[0][2] == payload.get('old_string')


def test_remote_placeholder_does_not_consume_first_hud(runtime):
    runtime.card()
    event = runtime.Event('.custom')
    def handler(plugin_event, Proc):
        runtime.core.onedice.RD('1d6').roll()
        plugin_event.reply('remote', remote=True)
        plugin_event.send('group', '100', 'remote', None, True, True)
        plugin_event.reply('actual')
    runtime.proc.run(event, handler, namespace='Custom')
    assert len(event.sent) == 1
    assert event.sent[0][2].startswith('Alice HP10/12')


def test_empty_sn_preserves_result_and_default_template_fallback(runtime):
    runtime.card(title='')
    assert runtime.sn.get('1', 'qq', '100') is None
    event = runtime.Event('.r 1d6')
    runtime.proc.run(event)
    assert not event.sent[0][2].startswith('Alice HP10/12')
    pc_hash = runtime.card()
    runtime.core.pcCard.dictPcCardTemplateDefault['unity']['without_sn'] = {'defaultSkillValue': {}}
    runtime.core.pcCard.dictPcCardTemplate['unity'][pc_hash]['Alice']['template'] = 'without_sn'
    assert runtime.sn.get('1', 'qq', '100').startswith('Alice HP10/12')


def test_team_respects_each_members_personal_switch(runtime):
    runtime.card('1', 'Alice')
    runtime.card('2', 'Bob')
    runtime.storage.set_user('bot', '2', 'qq', False)
    runtime.core.userConfig.setUserConfigByKey(
        '100', 'group', 'qq', 'teamConfig', {'squad': {'members': ['1', '2']}}, 'bot',
    )
    runtime.core.userConfig.setUserConfigByKey('100', 'group', 'qq', 'activeTeam', 'squad', 'bot')
    event = runtime.Event('.team r 1d6', role='owner')
    runtime.proc.run(event)
    first = event.sent[0][2].splitlines()[0]
    assert 'Alice HP' in first and 'Bob HP' not in first


def test_core_markdown_success_and_plain_fallback_do_not_duplicate(runtime):
    runtime.card()
    for success in (True, False):
        event = runtime.Event('.custom')
        event.platform['sdk'] = 'qqGuildv2_link'
        event.data.extend = {'flag_from_qq': True}
        captures = []
        class Inde:
            def hasAPI(self, name):
                return name == 'create_markdown_message'
            def create_markdown_message(self, **kwargs):
                captures.append(kwargs['markdown']['content'])
                return {'active': success}
        runtime.olivos.qqGuildv2SDK = type('SDK', (), {
            'markdown_tag': type('Tags', (), {'at_para': staticmethod(lambda para: '<@' + para.data['id'] + '>')}),
        })
        event.indeAPI = Inde()
        def handler(plugin_event, Proc):
            runtime.core.onedice.RD('1d6').roll()
            runtime.core.msgReply.replyMsg(plugin_event, '[CQ:at,qq=1] result')
        runtime.proc.run(event, handler)
        assert captures[0].startswith('Alice HP10/12')
        if success:
            assert not event.sent
        else:
            assert event.sent[0][2].count('Alice HP10/12') == 1
