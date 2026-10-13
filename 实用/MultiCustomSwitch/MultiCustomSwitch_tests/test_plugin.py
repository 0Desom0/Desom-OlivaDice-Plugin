import concurrent.futures
import json
import threading
import types

import pytest


def test_initial_state_and_shared_recover_file(env):
    store, bot = env.store, env.bots[0]
    assert store.status(bot)['effective'] == 1
    assert store.configs[bot] == {'reply_model': 1, 'enabled': True}
    assert [item['selection'] for item in store.list_replies(bot)] == [1, 2]
    store.modules(bot, ['OlivaDiceCore', 'MultiCustomSwitch'])
    assert env.webui.gui_parity.recover_modules(env.proc, bot) == ['OlivaDiceCore', 'MultiCustomSwitch']
    env.webui.gui_parity.recover_modules(env.proc, bot, ['OlivaDiceCore'])
    assert store.modules(bot) == ['OlivaDiceCore']
    assert store.recover_model[bot] == ['OlivaDiceCore']
    assert not (store.directory(bot) / 'recover_model.json').exists()
    assert env.webui.service.LOCK is env.plugin.files.LOCK


def test_sparse_reply_falls_back_to_smp_and_real_bot_name(env):
    bot = env.bots[0]
    env.core.msgCustomManager.setMsgCustomByBotHash(bot, 'strRoll', 'Core 已修改')
    reply = env.store.import_pack(bot, '风格', {'strForGroupOnly': '只在群聊'})
    values = env.store.values(bot, reply['selection'])
    assert values['strRoll'] == env.core.msgCustom.dictStrCustom['strRoll']
    assert values['strRoll'] != 'Core 已修改'
    assert env.store.smp(bot)['strBotName'] == '真实骰子1001'


def test_default_is_live_both_directions_with_actual_webui(env):
    bot = env.bots[0]
    snapshot = env.store.snapshot(bot, 1)
    env.store.edit(bot, 1, 'strRoll', '插件修改', snapshot['revision'])
    official = env.webui.service.replies(env.proc, bot)
    assert next(item for item in official if item['key'] == 'strRoll')['value'] == '插件修改'
    env.webui.service.set_reply(env.proc, bot, 'strRoll', '官方面板修改')
    assert env.store.values(bot, 1)['strRoll'] == '官方面板修改'
    with pytest.raises(env.plugin.store.Conflict):
        env.store.edit(bot, 1, 'strRoll', '过期修改', snapshot['revision'])
    data = env.plugin.files.read_json(env.store.core_file(bot, 'customReply.json'))
    assert data['strRoll'] == '官方面板修改'


def test_default_restore_prunes_updates_like_official_webui(env):
    bot = env.bots[0]
    env.webui.service.set_reply(env.proc, bot, 'strRoll', '修改')
    snapshot = env.store.snapshot(bot, 1)
    env.store.edit(bot, 1, 'strRoll', None, snapshot['revision'], reset=True)
    assert 'strRoll' not in env.core.msgCustom.dictStrCustomUpdateDict[bot]
    assert 'strRoll' not in env.plugin.files.read_json(env.store.core_file(bot, 'customReply.json'))


def test_unity_not_callable_until_import_and_all_collision_choices(env):
    store, bot = env.store, env.bots[0]
    store.import_pack('unity', '共享', {'strRoll': '甲'})
    assert all(item['name'] != '共享' for item in store.list_replies(bot))
    values = store.values('unity', '共享')
    first = store.import_pack(bot, '共享', values)
    group = store.group_hash(env.event())
    store.select(bot, first['selection'], group_hash=group)
    conflict = store.import_pack(bot, '共享', {'strRoll': '乙'})
    assert conflict['options'] == ['overwrite', 'copy', 'cancel']
    assert store.import_pack(bot, '共享', {'strRoll': '乙'}, 'cancel')['cancelled']
    assert store.values(bot, first['selection'])['strRoll'] == '甲'
    overwrite = store.import_pack(bot, '共享', {'strRoll': '乙'}, 'overwrite')
    assert overwrite['selection'] == first['selection']
    assert store.status(bot, group)['effective'] == first['selection']
    duplicate = store.import_pack(bot, '共享', {'strRoll': '丙'}, 'copy')
    assert duplicate['selection'] != first['selection']
    assert store.values(bot, duplicate['selection'])['strRoll'] == '丙'
    copied_back = env.plugin.api.dispatch(
        {
            'op': 'transfer',
            'scope': 'unity',
            'source_scope': bot,
            'source_selection': first['selection'],
            'name': '导出到共享',
        }
    )
    assert copied_back['name'] == '导出到共享'


def test_global_and_group_selection_switches_and_bot_isolation(env):
    store, bot = env.store, env.bots[0]
    a = store.import_pack(bot, '甲', {'strRoll': '甲'})['selection']
    b = store.import_pack(bot, '乙', {'strRoll': '乙'})['selection']
    group = store.group_hash(env.event(group='10'))
    other_group = store.group_hash(env.event(group='20'))
    store.select(bot, a, group_hash=group)
    store.select(bot, b)
    assert store.status(bot, group)['effective'] == a
    assert store.status(bot, other_group)['effective'] == b
    assert store.effective(env.event(group=None))['strRoll'] == '乙'
    store.select(bot, enabled=False)
    store.select(bot, enabled=True, group_hash=group)
    assert store.status(bot, group)['effective'] == 1
    assert store.status(bot, other_group)['effective'] == 1
    assert store.status(env.bots[1])['global']['enabled']
    store.select(bot, enabled=True)
    store.select(bot, enabled=False, group_hash=group)
    assert store.status(bot, group)['effective'] == 1
    assert store.status(bot, other_group)['effective'] == b


@pytest.mark.parametrize(
    ('kind', 'group', 'host', 'platform'),
    [
        ('group_message', 10, None, 'qq'),
        ('group_message', '10', None, 'qq'),
        ('group_message', '12345678901234567890', '98765432109876543210', 'qqGuild'),
        ('group_message', '10', '频道甲', 'discord'),
        ('group_message', '10', 0, 'qqGuild'),
        ('group_message', '10', '', 'qqGuild'),
        ('group_message', -1, None, 'qq'),
        ('private_message', None, None, 'qq'),
        ('private_message', '10', '20', 'qqGuild'),
    ],
)
def test_message_group_hash_matches_actual_core_functions(env, kind, group, host, platform):
    event = env.event(group=group, host=host)
    event.plugin_info['func_type'] = kind
    event.platform['platform'] = platform
    hag_id = env.core.msgReply.getHagIDFromMsg(event, env.proc)
    expected = (
        env.core.userConfig.getUserHash(userId=hag_id, userType='group', platform=platform)
        if hag_id is not None
        else None
    )
    assert env.store.group_hash(event) == expected


@pytest.mark.parametrize('kind', ['group_member_increase', 'poke'])
@pytest.mark.parametrize('host', [None, '20'])
def test_notification_group_hash_matches_core_group_message(env, kind, host):
    message = env.event(group='10', host=host)
    notification = env.event(group='10', host=host)
    notification.plugin_info['func_type'] = kind
    hag_id = env.core.msgReply.getHagIDFromMsg(message, env.proc)
    expected = env.core.userConfig.getUserHash(hag_id, 'group', message.platform['platform'])
    assert env.store.group_hash(notification) == expected


@pytest.mark.parametrize('group', [None, -1, '-1'])
def test_private_poke_has_no_group_hash(env, group):
    event = env.event(group=group)
    event.plugin_info['func_type'] = 'poke'
    assert env.store.group_hash(event) is None


def test_private_message_with_group_metadata_uses_global_selection(env):
    bot = env.bots[0]
    model = env.store.import_pack(bot, '仅本群', {'strRoll': '群回复'})['selection']
    message = env.event(group='10', host='20')
    env.store.select(bot, model, group_hash=env.store.group_hash(message))
    env.store.select(bot, 2)
    message.plugin_info['func_type'] = 'private_message'
    assert env.store.effective(message) == env.store.smp(bot)


def test_group_hash_separates_hosts_and_platforms_but_not_bots(env):
    ordinary = env.event(group='10')
    first = env.event(group='10', host='20')
    second = env.event(group='10', host='30')
    other_platform = env.event(group='10', host='20')
    other_platform.platform['platform'] = 'qqGuild'
    hashes = [env.store.group_hash(event) for event in (ordinary, first, second, other_platform)]
    assert len(set(hashes)) == 4
    other_bot = env.event(bot=env.bots[1], group='10', host='20')
    assert env.store.group_hash(other_bot) == hashes[1]
    env.store.select(env.bots[0], 2, group_hash=hashes[1])
    assert (env.store.directory(env.bots[0]) / 'group' / f'{hashes[1]}.json').is_file()
    assert not (env.store.directory(env.bots[1]) / 'group' / f'{hashes[1]}.json').exists()
    assert env.store.status(env.bots[1], hashes[1])['effective'] == 1


def test_reindex_swap_updates_all_disk_groups_global_and_restart(env):
    store, bot = env.store, env.bots[0]
    a = store.import_pack(bot, '甲', {'strRoll': '甲'})['selection']
    b = store.import_pack(bot, '乙', {'strRoll': '乙'})['selection']
    group = store.group_hash(env.event())
    store.select(bot, a, group_hash=group)
    store.select(bot, b)
    # 磁盘上新增、不在内存缓存中的群也必须同步。
    offline = 'c' * 32
    env.plugin.files.write_json(
        store.directory(bot) / 'group' / f'{offline}.json', {'reply_model': a, 'enabled': False}
    )
    store.reindex(bot, {str(a): b, str(b): a})
    assert store.indexes[bot] == {b: '甲', a: '乙'}
    assert store.status(bot, group)['selected'] == b
    assert store.status(bot)['selected'] == a
    assert env.plugin.files.read_json(store.directory(bot) / 'group' / f'{offline}.json')['reply_model'] == b
    restarted = env.plugin.store.ReplyStore(env.proc, store.root)
    assert restarted.status(bot, group)['selected'] == b
    assert restarted.values(bot, b)['strRoll'] == '甲'
    for mapping in ({str(a): 2, str(b): b}, {str(a): 5, str(b): 5}, {str(a): 7}):
        with pytest.raises(env.plugin.store.InvalidInput):
            store.reindex(bot, mapping)


def test_rename_moves_file_keeps_model_and_group_bytes(env):
    store, bot = env.store, env.bots[0]
    selection = store.import_pack(bot, '旧名', {'strRoll': '回复'})['selection']
    group = store.group_hash(env.event())
    store.select(bot, selection, group_hash=group)
    path = store.directory(bot) / 'group' / f'{group}.json'
    before = path.read_bytes()
    store.rename(bot, selection, '新名')
    assert not (store.directory(bot) / '旧名.json').exists()
    assert (store.directory(bot) / '新名.json').exists()
    assert store.indexes[bot][selection] == '新名'
    assert path.read_bytes() == before
    store.import_pack(bot, '另一个', {'strRoll': '另一个'})
    with pytest.raises(env.plugin.store.Conflict):
        store.rename(bot, selection, '另一个')


def test_case_only_rename_on_windows(env):
    bot = env.bots[0]
    model = env.store.import_pack(bot, 'Example', {'strRoll': '回复'})['selection']
    env.store.rename(bot, model, 'example')
    names = [path.name for path in env.store.directory(bot).glob('*.json')]
    assert 'example.json' in names
    assert 'Example.json' not in names


def test_smp_readonly_and_new_reply_can_copy_any_library(env):
    bot = env.bots[0]
    snapshot = env.store.snapshot(bot, 2)
    assert snapshot['readonly']
    with pytest.raises(env.plugin.store.InvalidInput):
        env.store.edit(bot, 2, 'strRoll', '不能修改', snapshot['revision'])
    created = env.store.clone(bot, '默认副本', bot, 2)
    assert env.store.values(bot, created['selection'])['strBotName'] == '真实骰子1001'
    copy = env.store.clone(env.bots[1], '来自另一个 Bot', bot, created['selection'])
    assert env.store.values(env.bots[1], copy['selection'])['strBotName'] == '真实骰子1001'
    with pytest.raises(env.plugin.store.Conflict):
        env.store.clone(bot, '默认副本', bot, 1)


def test_unity_baseline_and_modified_filter_values(env, monkeypatch):
    module = types.ModuleType('ExtraReply')
    module.msgCustom = types.SimpleNamespace(dictStrCustom={'strExtra': '外部默认'})
    monkeypatch.setitem(__import__('sys').modules, 'ExtraReply', module)
    env.store.import_pack('unity', '测试', {'strExtra': '外部默认'})
    all_defaults = env.store.snapshot('unity', '测试')
    assert not next(item for item in all_defaults['entries'] if item['key'] == 'strExtra')['modified']
    only_core = env.store.snapshot('unity', '测试', env.bots[0])
    assert next(item for item in only_core['entries'] if item['key'] == 'strExtra')['modified']


def test_no_group_crosstalk_under_concurrent_plugin_routing(env):
    bot = env.bots[0]
    model = env.store.import_pack(bot, '特定群', {'strRoll': '独立群回复'})['selection']
    event_a, event_b = env.event(group='10'), env.event(group='20')
    env.store.select(bot, model, group_hash=env.store.group_hash(event_a))
    barrier = threading.Barrier(2)

    def callback(event, proc):
        values = env.core.msgCustom.dictStrCustomDict[bot]
        barrier.wait(timeout=3)
        return values['strRoll']

    plugin_model = types.SimpleNamespace(
        main=types.SimpleNamespace(Event=types.SimpleNamespace(group_message=callback))
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(env.proc.plugin_event_router, event_a, plugin_model, 'Core')
        b = pool.submit(env.proc.plugin_event_router, event_b, plugin_model, 'Core')
        assert a.result(timeout=4) == '独立群回复'
        assert b.result(timeout=4) == env.core.msgCustom.dictStrCustom['strRoll']
    assert env.plugin.runtime.CONTEXT.get() is None
    assert env.store.default_values(bot)['strRoll'] == env.core.msgCustom.dictStrCustom['strRoll']


def test_core_saving_inside_custom_context_never_saves_selected_pack(env):
    bot = env.bots[0]
    model = env.store.import_pack(bot, '风格', {'strRoll': '风格内容'})['selection']
    env.store.select(bot, model)
    context = env.plugin.runtime.CONTEXT.set((bot, env.store.values(bot, model)))
    try:
        env.core.msgCustomManager.setMsgCustomByBotHash(bot, 'strRoll', '原始内容更新')
        assert env.core.msgCustom.dictStrCustomDict[bot]['strRoll'] == '风格内容'
        assert env.store.default_values(bot)['strRoll'] == '原始内容更新'
    finally:
        env.plugin.runtime.CONTEXT.reset(context)
    data = env.plugin.files.read_json(env.store.core_file(bot, 'customReply.json'))
    assert data['strRoll'] == '原始内容更新'
    assert env.store.values(bot, model)['strRoll'] == '风格内容'


@pytest.mark.parametrize(
    'role,user,global_action,allowed',
    [
        ('admin', '456', False, True),
        ('owner', '456', False, True),
        ('member', '123', False, False),
        ('sub_admin', '123', False, False),
        ('admin', '456', True, False),
        ('member', '123', True, True),
    ],
)
def test_command_permissions(env, role, user, global_action, allowed):
    event = env.event(message='.mcs global off' if global_action else '.mcs off', role=role, user=user)
    env.plugin.commands.handle(event, env.proc)
    assert event.blocked
    status = env.store.status(env.bots[0], None if global_action else env.store.group_hash(event))
    actual = status['global']['enabled'] if global_action else (status['group'] or {'enabled': True})['enabled']
    assert actual is (not allowed)


def test_mcs_show_list_help_private_and_numeric_switch(env):
    bot = env.bots[0]
    model = env.store.import_pack(bot, '风格', {'strRoll': '风格'})['selection']
    for suffix in ('', 'show', 'list', 'help', str(model), 'global 2'):
        event = env.event(message=f'.mcs {suffix}'.rstrip())
        env.plugin.commands.handle(event, env.proc)
        assert event.blocked and event.sent
    private = env.event(message='.mcs show', group=None)
    env.plugin.commands.handle(private, env.proc)
    assert '请在群内' in private.sent[-1]
    help_event = env.event(message='.mcs help')
    env.plugin.commands.handle(help_event, env.proc)
    assert '1 = default' in help_event.sent[-1] and '2 = smp' in help_event.sent[-1]


@pytest.mark.parametrize('message', ['.mcs3', '.mcs风格', '.mcsglobal3', '.mcsglobal风格', '。MCSGLOBAL3'])
def test_greedy_command_switch_without_spaces(env, message):
    bot = env.bots[0]
    env.store.import_pack(bot, '风格', {'strRoll': '风格'})
    event = env.event(message=message)
    env.plugin.commands.handle(event, env.proc)
    target = None if 'global' in message.casefold() else env.store.group_hash(event)
    assert env.store.status(bot, target)['selected'] == 3


@pytest.mark.parametrize('message', ['.mcsoff', '.mcsglobaloff', '。MCSGLOBALOFF'])
def test_greedy_command_switch_off_without_spaces(env, message):
    event = env.event(message=message)
    env.plugin.commands.handle(event, env.proc)
    target = None if 'global' in message.casefold() else env.store.group_hash(event)
    assert not env.store.status(env.bots[0], target)['enabled']


def test_actual_core_fuzzy_selection_without_file_lock_during_wait(env, monkeypatch):
    bot = env.bots[0]
    env.store.import_pack(bot, '可爱回复', {'strRoll': '可爱'})
    entered, finish = threading.Event(), threading.Event()

    def wait(**kwargs):
        entered.set()
        assert finish.wait(3)
        return '1'

    monkeypatch.setattr(env.core.msgReplyModel, 'replyCONTEXT_regWait', wait)
    event = env.event(message='.mcs 可爱回')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        command = pool.submit(env.plugin.commands.handle, event, env.proc)
        assert entered.wait(3)
        # 等待数字期间另一线程仍能修改文件，证明没有跨等待持有文件锁。
        save = pool.submit(env.store.import_pack, bot, '另一套', {'strRoll': '另一套'})
        assert save.result(timeout=2)['name'] == '另一套'
        finish.set()
        command.result(timeout=3)
    assert env.store.status(bot, env.store.group_hash(event))['selected'] == 3
    assert any('请选择' in text for text in event.sent)


@pytest.mark.parametrize('name', ['../escape', 'bad/name', 'custom_list', 'config', 'NUL', 'bad.'])
def test_invalid_names_and_import_structure(env, name):
    with pytest.raises(env.plugin.store.InvalidInput):
        env.store.import_pack(env.bots[0], name, {'strRoll': '文本'})
    for data in ([], {'strRoll': ['不能是数组']}, {'strRoll': 1}, {'strRoll': {'nested': 'object'}}):
        with pytest.raises(env.plugin.store.InvalidInput):
            env.store.import_pack(env.bots[0], '结构错误', data)


def test_reindex_rolls_back_all_files_on_write_failure(env, monkeypatch):
    bot = env.bots[0]
    model = env.store.import_pack(bot, '风格', {'strRoll': '文本'})['selection']
    group = env.store.group_hash(env.event())
    env.store.select(bot, model, group_hash=group)
    paths = [
        env.store.directory(bot) / 'custom_list.json',
        env.store.directory(bot) / 'config.json',
        env.store.directory(bot) / 'group' / f'{group}.json',
    ]
    previous = {path: path.read_bytes() for path in paths}
    original = env.plugin.files._write
    calls = [0]

    def fail_once(path, data):
        calls[0] += 1
        if calls[0] == 2:
            raise OSError('模拟写入失败')
        original(path, data)

    monkeypatch.setattr(env.plugin.files, '_write', fail_once)
    with pytest.raises(OSError):
        env.store.reindex(bot, {str(model): 9})
    assert {path: path.read_bytes() for path in paths} == previous
    assert env.store.status(bot, group)['selected'] == model


def test_missing_reply_files_fall_back_and_invalid_group_blocks_reindex(env):
    bot = env.bots[0]
    model = env.store.import_pack(bot, '风格', {'strRoll': '文本'})['selection']
    env.store.select(bot, model)
    (env.store.directory(bot) / '风格.json').unlink()
    env.store.reload(bot)
    assert env.store.status(bot)['missing'] and env.store.status(bot)['effective'] == 1
    path = env.store.directory(bot) / 'group' / f'{"c" * 32}.json'
    path.write_text('{bad json', encoding='utf-8')
    index = (env.store.directory(bot) / 'custom_list.json').read_bytes()
    with pytest.raises(ValueError):
        env.store.reindex(bot, {str(model): 9})
    assert (env.store.directory(bot) / 'custom_list.json').read_bytes() == index


def test_chunk_bridge_owner_offset_and_unicode(env):
    api = env.plugin.api
    owner = 'session-digest'
    text = json.dumps(
        {'op': 'import', 'scope': env.bots[0], 'name': '分片', 'data': {'strRoll': '中文🦊' * 2000}}, ensure_ascii=True
    )
    token = api.bridge({'transport': 'upload_start'}, owner)['token']
    with pytest.raises(env.plugin.store.InvalidInput):
        api.bridge({'transport': 'upload_chunk', 'token': token, 'offset': 0, 'text': text}, 'another-owner')
    api.bridge({'transport': 'upload_chunk', 'token': token, 'offset': 0, 'text': text[:123]}, owner)
    with pytest.raises(env.plugin.store.InvalidInput):
        api.bridge({'transport': 'upload_chunk', 'token': token, 'offset': 0, 'text': 'x'}, owner)
    api.bridge({'transport': 'upload_chunk', 'token': token, 'offset': 123, 'text': text[123:]}, owner)
    result = api.bridge({'transport': 'upload_finish', 'token': token}, owner)
    assert result['name'] == '分片'
    assert env.store.values(env.bots[0], result['selection'])['strRoll'] == '中文🦊' * 2000


def test_webui_menu_context_and_help_in_memory(env):
    event = env.event()
    event.bot_info = None
    event.plugin_info['func_type'] = 'menu'
    event.data = types.SimpleNamespace(
        namespace='MultiCustomSwitch',
        event=env.plugin.api.EVENT,
        payload={'op': 'help'},
        webui={'request_id': 'test', 'session': 'test-session'},
    )
    env.plugin.main.Event.menu(event, env.proc)
    assert event.sent[0][0:2] == ('webui', 'test')
    assert '自定义回复编写帮助' in event.sent[0][2]['result']['markdown']
    assert env.plugin.resources.WRITER_HELP


def test_uninstall_restores_official_state_and_route(env):
    core_dict = env.core.msgCustom.dictStrCustomDict
    env.plugin.runtime.uninstall()
    assert type(env.core.msgCustom.dictStrCustomDict) is dict
    assert env.core.msgCustom.dictStrCustomDict is not core_dict
    assert not hasattr(env.core.msgCustomManager, 'open')
    assert env.webui.service.LOCK is not env.plugin.files.LOCK


def test_legacy_core_without_optional_helpers_initializes_and_has_builtin_replies(env, monkeypatch):
    manager = env.core.msgCustomManager
    env.plugin.runtime.uninstall()
    defaults = manager.getDictStrCustomDefault()
    helpers = ('getDictStrCustomDefault', 'setMsgCustomByBotHash', 'pruneMsgCustomByBotHash', 'pruneAndSaveMsgCustom')
    for name in helpers:
        monkeypatch.delattr(manager, name)
    # 旧版 Core 的实际保存函数没有 defaults/prune 参数。
    def legacy_save(bot):
        env.plugin.files.write_json(
            env.store.core_file(bot, 'customReply.json'), env.core.msgCustom.dictStrCustomUpdateDict.get(bot, {})
        )

    monkeypatch.setattr(manager, 'saveMsgCustomByBotHash', legacy_save)
    env.plugin.main.Event.init_after(None, env.proc)
    store = env.plugin.runtime.STORE
    assert store is not None and env.plugin.runtime.INIT_ERROR is None
    assert env.plugin.store.core_defaults() == defaults
    bot = env.bots[0]
    assert [row['selection'] for row in store.list_replies(bot)] == [1, 2]
    assert store.snapshot(bot, 1)['entries']
    assert store.snapshot(bot, 2)['readonly']
    snapshot = store.snapshot(bot, 1)
    store.edit(bot, 1, 'strRoll', '旧版 Core 保存', snapshot['revision'])
    assert env.webui.gui_parity.replies_snapshot(env.proc, bot)['strRoll'] == '旧版 Core 保存'
    assert env.plugin.files.read_json(store.core_file(bot, 'customReply.json'))['strRoll'] == '旧版 Core 保存'


def test_initialization_failure_reports_type_and_call_site_without_private_details(env, monkeypatch):
    env.plugin.runtime.uninstall()

    def broken_install(proc):
        raise ValueError('不应出现在日志或界面中的私有配置内容')

    monkeypatch.setattr(env.plugin.runtime, 'install', broken_install)
    env.plugin.main.Event.init_after(None, env.proc)
    assert env.plugin.runtime.STORE is None
    assert 'ValueError' in env.plugin.runtime.INIT_ERROR
    log = env.proc.logs[-1][0][1]
    assert 'broken_install' in log
    assert '不应出现在日志或界面中的私有配置内容' not in log
    with pytest.raises(env.plugin.store.InvalidInput, match='ValueError'):
        env.plugin.api.dispatch({'op': 'accounts'})


def test_default_helper_compatibility_and_local_module_merge_fallback(env, monkeypatch):
    expected = env.core.msgCustomManager.getDictStrCustomDefault()
    calls = []

    def available_helper():
        calls.append(True)
        return expected

    monkeypatch.setattr(env.core.msgCustomManager, 'getDictStrCustomDefault', available_helper)
    assert env.plugin.store.core_defaults() == expected
    assert calls == [True]
    monkeypatch.delattr(env.core.msgCustomManager, 'getDictStrCustomDefault')
    first = types.ModuleType('McsFirstDefaults')
    first.msgCustom = types.SimpleNamespace(dictStrCustom={'strRoll': '先加载', 'strExtra': '额外默认'})
    second = types.ModuleType('McsLastDefaults')
    second.msgCustom = types.SimpleNamespace(dictStrCustom={'strRoll': '后加载', 'invalid': 123})
    monkeypatch.setitem(__import__('sys').modules, first.__name__, first)
    monkeypatch.setitem(__import__('sys').modules, second.__name__, second)
    defaults = env.plugin.store.core_defaults()
    assert defaults['strRoll'] == '后加载' and defaults['strExtra'] == '额外默认'
    assert 'invalid' not in defaults
    bot = env.bots[0]
    assert env.store.smp(bot)['strRoll'] == '后加载'
    created = env.store.clone(bot, '旧版默认副本', bot, 2)
    assert env.store.values(bot, created['selection'])['strExtra'] == '额外默认'
    assert env.store.snapshot(bot, 2)['readonly']
