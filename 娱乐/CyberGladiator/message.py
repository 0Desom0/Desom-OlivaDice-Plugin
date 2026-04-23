# -*- encoding: utf-8 -*-
"""赛博角斗场消息解析与回复模块。"""

from . import config
from . import function
from . import message_custom
from . import utils


gladiator_command_prefix_tuple = ('角斗', '决斗')
gladiator_command_suffix_tuple = ('加入', '更新', '录入', '开始', '查询', '退出', '清空', '停止', '关闭', '开启', '配置', '帮助')
command_name_list = [
    f'{command_prefix}{command_suffix}'
    for command_prefix in gladiator_command_prefix_tuple
    for command_suffix in gladiator_command_suffix_tuple
]
management_command_name_set = {'清空', '停止', '关闭', '开启'}
master_only_command_name_set = {'配置'}
locked_command_name_set = {'加入', '更新', '开始', '退出', '清空'}


def handle_init(plugin_event, Proc) -> None:
    utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    utils.info_log(Proc, '赛博角斗场 init 完成。')


def handle_init_after(plugin_event, Proc) -> None:
    utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    utils.debug_log(Proc, '赛博角斗场 init_after 已执行。', plugin_event=plugin_event)


def handle_private_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_group_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def is_management_command(command_name: str) -> bool:
    return command_name in management_command_name_set


def is_master_only_command(command_name: str) -> bool:
    return command_name in master_only_command_name_set


def is_privileged_command(command_name: str) -> bool:
    return is_management_command(command_name) or is_master_only_command(command_name)


def normalize_command_name(command_name: str) -> str:
    normalized_command_name = utils.safe_str(command_name).strip()
    for command_prefix in gladiator_command_prefix_tuple:
        if not normalized_command_name.startswith(command_prefix):
            continue
        command_suffix = normalized_command_name[len(command_prefix) :]
        if command_suffix == '录入':
            return '加入'
        if command_suffix in gladiator_command_suffix_tuple:
            return command_suffix
        return normalized_command_name
    return normalized_command_name


def sender_has_master_permission(plugin_event) -> bool:
    return utils.get_master_permission_info(plugin_event)['sender_is_master']


def sender_has_group_management_permission(plugin_event) -> bool:
    return utils.is_group_admin(plugin_event) or sender_has_master_permission(plugin_event)


def build_runtime_value_dict(plugin_event, command_argument: str = '', extra_value_dict=None):
    config_bot_hash = utils.get_bot_hash_from_event(plugin_event)
    reply_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)
    delay_min_seconds, delay_max_seconds = function.get_segment_delay_range_from_bot_config(bot_config)
    configured_master_list = utils.get_configured_master_list(config_bot_hash)
    variable_dict = utils.load_bot_message_variables(reply_bot_hash)

    runtime_value_dict = utils.build_base_template_value_dict(
        plugin_event,
        command_argument=command_argument,
        extra_value_dict={
            'plugin_display_name': config.plugin_display_name,
            'global_enable': 'ON' if global_config.get('global_enable_switch', True) else 'OFF',
            'global_debug': 'ON' if global_config.get('global_debug_mode_switch', False) else 'OFF',
            'bot_enable': 'ON' if bot_config.get('bot_enable_switch', True) else 'OFF',
            'configured_masters': ', '.join(configured_master_list) or '无',
            'function_module_note': function.function_module_note,
            'max_participants': str(function.MAX_PARTICIPANTS),
            'delay_min_seconds': str(delay_min_seconds),
            'delay_max_seconds': str(delay_max_seconds),
        },
    )
    runtime_value_dict.update(variable_dict)
    if isinstance(extra_value_dict, dict):
        runtime_value_dict.update(extra_value_dict)
    return runtime_value_dict


def render_custom_message(plugin_event, message_key: str, command_argument: str = '', extra_value_dict=None) -> str:
    reply_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    custom_message_dict = utils.load_bot_message_custom(reply_bot_hash)
    template_text = custom_message_dict.get(message_key, '')
    value_dict = build_runtime_value_dict(plugin_event, command_argument, extra_value_dict)
    return utils.render_text_template(template_text, value_dict)


def reply_permission_denied(plugin_event) -> None:
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_permission_denied'))


def reply_global_permission_denied(plugin_event) -> None:
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_global_permission_denied'))


def reply_config_permission_denied(plugin_event) -> None:
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_config_permission_denied'))


def reply_battle_locked(plugin_event) -> None:
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_battle_locked'))


def normalize_toggle_scope(command_argument: str) -> str:
    argument_text = utils.safe_str(command_argument).strip()
    if argument_text == '全局':
        return 'global'
    return 'group'


def handle_gladiator_help(plugin_event) -> None:
    utils.reply_message(plugin_event, message_custom.help_document_dict['gladiator_help'])


def handle_gladiator_join(plugin_event, command_argument: str) -> None:
    result = function.add_waiting_player(plugin_event, command_argument)
    if not result.get('ok'):
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_room_full',
                extra_value_dict={'waiting_count': result.get('waiting_count', 0)},
            ),
        )
        return

    utils.reply_message(
        plugin_event,
        render_custom_message(
            plugin_event,
            'reply_room_joined',
            extra_value_dict={
                'user_display_name': result.get('user_display_name', ''),
                'waiting_count': result.get('waiting_count', 0),
                'entry_index': result.get('entry_index', 0),
            },
        ),
    )


def handle_gladiator_update(plugin_event, command_argument: str) -> None:
    self_entry_list = function.get_waiting_entries_by_user(plugin_event)
    self_entry_count = len(self_entry_list)
    if self_entry_count <= 0:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_update_no_entry'))
        return

    argument_text = utils.safe_str(command_argument).strip()
    first_token, remaining_text = utils.split_first_token(argument_text)
    entry_index = _parse_positive_index(first_token)
    update_text = argument_text

    if self_entry_count == 1:
        target_entry_index = self_entry_list[0]['entry_index']
        if entry_index > 0:
            target_entry_index = entry_index
            update_text = remaining_text
    else:
        if entry_index <= 0:
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_update_need_index',
                    extra_value_dict={'self_entry_count': self_entry_count},
                ),
            )
            return
        target_entry_index = entry_index
        update_text = remaining_text

    result = function.update_waiting_player_by_index_for_user(plugin_event, target_entry_index, update_text)
    if not result.get('ok'):
        if result.get('reason') == 'not_owner':
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_update_not_owner'))
            return
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_invalid_index',
                extra_value_dict={'waiting_count': result.get('waiting_count', 0)},
            ),
        )
        return

    utils.reply_message(
        plugin_event,
        render_custom_message(
            plugin_event,
            'reply_room_updated',
            extra_value_dict={
                'user_display_name': result.get('user_display_name', ''),
                'waiting_count': result.get('waiting_count', 0),
                'entry_index': result.get('entry_index', 0),
            },
        ),
    )


def handle_gladiator_query(plugin_event) -> None:
    snapshot = function.get_waiting_room_snapshot(plugin_event)
    if snapshot['waiting_count'] <= 0:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_room_query_empty'))
        return

    line_list = [
        render_custom_message(
            plugin_event,
            'reply_room_query_header',
            extra_value_dict={'waiting_count': snapshot['waiting_count']},
        )
    ]
    for entry in function.build_query_entries(snapshot['waiting_room']):
        line_list.append(
            render_custom_message(
                plugin_event,
                'reply_room_query_item',
                extra_value_dict=entry,
            )
        )
    utils.reply_message(plugin_event, '\n\n'.join(line_list))


def _parse_positive_index(command_argument: str) -> int:
    try:
        return int(utils.safe_str(command_argument).strip())
    except Exception:
        return 0


def handle_gladiator_leave(plugin_event, command_argument: str) -> None:
    snapshot = function.get_waiting_room_snapshot(plugin_event)
    argument_text = utils.safe_str(command_argument).strip()
    if argument_text == '':
        result = function.remove_waiting_player_by_user(plugin_event)
        if not result.get('ok'):
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_self_not_in_room'))
            return
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_room_removed_all',
                extra_value_dict={
                    'removed_count': result.get('removed_count', 0),
                    'waiting_count': result.get('waiting_count', 0),
                },
            ),
        )
        return

    entry_index = _parse_positive_index(argument_text)
    if entry_index <= 0:
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_invalid_index',
                extra_value_dict={'waiting_count': snapshot['waiting_count']},
            ),
        )
        return

    result = function.remove_waiting_player_by_index(plugin_event, entry_index)
    if not result.get('ok'):
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_invalid_index',
                extra_value_dict={'waiting_count': result.get('waiting_count', 0)},
            ),
        )
        return

    utils.reply_message(
        plugin_event,
        render_custom_message(
            plugin_event,
            'reply_room_removed',
            extra_value_dict={
                'entry_index': entry_index,
                'waiting_count': result.get('waiting_count', 0),
            },
        ),
    )


def handle_gladiator_clear(plugin_event) -> None:
    function.clear_waiting_room(plugin_event)
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_room_cleared'))


def handle_gladiator_stop(plugin_event) -> None:
    result = function.request_stop_battle(plugin_event)
    if not result.get('ok'):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_stop_not_running'))
        return
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_stop_requested'))


def handle_gladiator_close(plugin_event, command_argument: str) -> None:
    toggle_scope = normalize_toggle_scope(command_argument)
    if toggle_scope == 'global':
        if not function.is_global_plugin_enabled():
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_global_already_closed'))
            return
        function.set_global_plugin_enabled(False)
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_global_close_success'))
        return

    if not function.is_group_plugin_enabled(plugin_event):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_already_closed'))
        return
    function.set_group_plugin_enabled(plugin_event, False)
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_close_success'))


def handle_gladiator_open(plugin_event, command_argument: str) -> None:
    toggle_scope = normalize_toggle_scope(command_argument)
    if toggle_scope == 'global':
        if function.is_global_plugin_enabled():
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_global_already_open'))
            return
        function.set_global_plugin_enabled(True)
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_global_open_success'))
        return

    if function.is_group_plugin_enabled(plugin_event):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_already_open'))
        return
    function.set_group_plugin_enabled(plugin_event, True)
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_open_success'))


def _parse_delay_config_command(command_argument: str) -> dict:
    token_list = utils.safe_str(command_argument).strip().split()
    if not token_list:
        return {'ok': True, 'action': 'show'}

    option_name = token_list[0]
    if option_name not in {'等待', '等待时间', '间隔', '延时'}:
        return {'ok': False}

    if len(token_list) == 1:
        return {'ok': True, 'action': 'show'}
    if len(token_list) != 3:
        return {'ok': False}

    try:
        delay_min_seconds = int(token_list[1])
        delay_max_seconds = int(token_list[2])
    except Exception:
        return {'ok': False}

    if delay_min_seconds <= 0 or delay_max_seconds <= 0 or delay_max_seconds < delay_min_seconds:
        return {'ok': False}
    return {
        'ok': True,
        'action': 'set',
        'delay_min_seconds': delay_min_seconds,
        'delay_max_seconds': delay_max_seconds,
    }


def handle_gladiator_config(plugin_event, config_bot_hash: str, command_argument: str) -> None:
    parse_result = _parse_delay_config_command(command_argument)
    if not parse_result.get('ok'):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_delay_config_invalid'))
        return

    if parse_result.get('action') == 'show':
        bot_config = utils.load_bot_config(config_bot_hash)
        delay_min_seconds, delay_max_seconds = function.get_segment_delay_range_from_bot_config(bot_config)
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_delay_config_status',
                extra_value_dict={
                    'delay_min_seconds': str(delay_min_seconds),
                    'delay_max_seconds': str(delay_max_seconds),
                },
            ),
        )
        return

    bot_config = utils.load_bot_config(config_bot_hash)
    bot_config['segment_delay_min_seconds'] = parse_result['delay_min_seconds']
    bot_config['segment_delay_max_seconds'] = parse_result['delay_max_seconds']
    utils.save_bot_config(config_bot_hash, bot_config)
    utils.reply_message(
        plugin_event,
        render_custom_message(
            plugin_event,
            'reply_delay_config_updated',
            extra_value_dict={
                'delay_min_seconds': str(parse_result['delay_min_seconds']),
                'delay_max_seconds': str(parse_result['delay_max_seconds']),
            },
        ),
    )


def handle_gladiator_start(plugin_event, Proc) -> None:
    battle_context = function.prepare_battle_run(plugin_event)
    if not battle_context.get('ok'):
        if battle_context.get('reason') == 'battle_running':
            reply_battle_locked(plugin_event)
            return
        if battle_context.get('reason') == 'not_enough_players':
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_room_not_enough'))
            return
        if battle_context.get('reason') == 'missing_api_config':
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_missing_api_config'))
            return
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_battle_failed',
                extra_value_dict={'error_message': battle_context.get('reason', '未知错误')},
            ),
        )
        return

    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_room_starting'))
    result = function.run_battle(plugin_event, Proc, battle_context=battle_context)
    if result.get('ok'):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_battle_finished'))
        return

    if result.get('reason') == 'battle_running':
        reply_battle_locked(plugin_event)
        return
    if result.get('reason') == 'not_enough_players':
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_room_not_enough'))
        return
    if result.get('reason') == 'missing_api_config':
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_missing_api_config'))
        return
    if result.get('reason') == 'battle_stopped':
        return
    utils.reply_message(
        plugin_event,
        render_custom_message(
            plugin_event,
            'reply_battle_failed',
            extra_value_dict={'error_message': result.get('error_message', '未知错误')},
        ),
    )


def _reply_unknown_gladiator_command(plugin_event) -> None:
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_unknown_command'))


def _is_group_context(plugin_event) -> bool:
    return bool(utils.get_group_id_from_event(plugin_event))


@utils.log_exception('handle_message')
def handle_message(plugin_event, Proc) -> None:
    config_bot_hash = utils.ensure_runtime_storage_by_event(plugin_event, Proc)

    if not utils.check_core_group_enable(plugin_event):
        utils.debug_log(Proc, '当前群在 OlivaDiceCore 中处于关闭状态，插件不继续处理。', plugin_event=plugin_event)
        return

    original_message_text = utils.get_message_text_from_event(plugin_event)
    cleaned_message_text = utils.strip_reply_segment(original_message_text)
    at_item_list, remaining_after_at = utils.parse_at_segments(cleaned_message_text, allow_multi=True)
    allow_no_prefix = utils.is_force_reply_to_current_bot(at_item_list, plugin_event)
    command_info = utils.parse_command(
        remaining_after_at,
        prefix_list=config.allowed_prefix_list,
        allow_no_prefix=allow_no_prefix,
        command_name=command_name_list,
    )

    if not command_info['is_command']:
        generic_command_info = utils.parse_command(
            remaining_after_at,
            prefix_list=config.allowed_prefix_list,
            allow_no_prefix=allow_no_prefix,
        )
        if (
            generic_command_info['is_command']
            and generic_command_info['command_name'].startswith(gladiator_command_prefix_tuple)
        ):
            if _is_group_context(plugin_event):
                _reply_unknown_gladiator_command(plugin_event)
            else:
                utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_group_only'))
        return

    if not _is_group_context(plugin_event):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_group_only'))
        return

    command_name = normalize_command_name(command_info['command_name'])
    command_argument = command_info['command_argument']
    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)

    if not is_privileged_command(command_name):
        if not global_config.get('global_enable_switch', True):
            utils.debug_log(Proc, '全局启用开关已关闭，普通命令不再处理。', plugin_event=plugin_event)
            return
        if not bot_config.get('bot_enable_switch', True):
            utils.debug_log(Proc, '当前 Bot 开关已关闭，普通命令不再处理。', plugin_event=plugin_event)
            return
        if command_name != '帮助' and not function.is_group_plugin_enabled(plugin_event):
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_plugin_disabled'))
            return

    if command_name in locked_command_name_set and function.is_group_battle_running(plugin_event):
        reply_battle_locked(plugin_event)
        return

    if command_name == '帮助':
        handle_gladiator_help(plugin_event)
        return

    if command_name == '加入':
        handle_gladiator_join(plugin_event, command_argument)
        return

    if command_name == '更新':
        handle_gladiator_update(plugin_event, command_argument)
        return

    if command_name == '查询':
        handle_gladiator_query(plugin_event)
        return

    if command_name == '退出':
        handle_gladiator_leave(plugin_event, command_argument)
        return

    if command_name in master_only_command_name_set:
        if not sender_has_master_permission(plugin_event):
            reply_config_permission_denied(plugin_event)
            return

    if command_name in management_command_name_set:
        if command_name in {'关闭', '开启'} and normalize_toggle_scope(command_argument) == 'global':
            if not sender_has_master_permission(plugin_event):
                reply_global_permission_denied(plugin_event)
                return
        elif not sender_has_group_management_permission(plugin_event):
            reply_permission_denied(plugin_event)
            return

    if command_name == '清空':
        handle_gladiator_clear(plugin_event)
        return

    if command_name == '停止':
        handle_gladiator_stop(plugin_event)
        return

    if command_name == '关闭':
        handle_gladiator_close(plugin_event, command_argument)
        return

    if command_name == '开启':
        handle_gladiator_open(plugin_event, command_argument)
        return

    if command_name == '配置':
        handle_gladiator_config(plugin_event, config_bot_hash, command_argument)
        return

    if command_name == '开始':
        handle_gladiator_start(plugin_event, Proc)
        return

    _reply_unknown_gladiator_command(plugin_event)
