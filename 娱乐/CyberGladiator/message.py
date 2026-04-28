# -*- encoding: utf-8 -*-
"""赛博角斗场消息解析与回复模块。"""

from . import config
from . import function
from . import message_custom
from . import utils


gladiator_command_prefix_tuple = ('角斗', '决斗')
gladiator_command_suffix_tuple = ('加入', '更新', '录入', '开始', '查询', '状态', '退出', '清空', '停止', '关闭', '开启', '配置', '帮助', '神战')
command_name_list = [
    f'{command_prefix}{command_suffix}'
    for command_prefix in gladiator_command_prefix_tuple
    for command_suffix in gladiator_command_suffix_tuple
]
management_command_name_set = {'清空', '停止', '关闭', '开启'}
master_only_command_name_set = {'配置'}
locked_command_name_set = {'加入', '更新', '开始', '退出', '清空'}
config_command_definition_list = [
    ('global_enable', '全局启用', ('全局启用', '全局开关')),
    ('global_debug', '全局调试', ('全局调试', '全局调试模式')),
    ('global_god_war', '全局神战', ('全局神战', '神战总开关', '神战默认')),
    ('api_url', 'API 地址', ('api地址', 'api url')),
    ('api_key', 'API Key', ('apikey', 'api key', 'api_key')),
    ('model', '模型名称', ('模型名称', '模型')),
    ('timeout', '请求超时', ('请求超时', '超时')),
    ('temperature', 'Temperature', ('temperature', '温度')),
    ('delay', '切片等待', ('等待时间', '切片等待', '等待', '间隔', '延时')),
    ('input_limit', '设定字数限制', ('字数限制', '字数', '限制')),
    ('forward', 'QQ 合并转发', ('qq合并转发', 'qq 合并转发', 'qq转发', '合并转发', '转发')),
    ('system_prompt', '系统提示词', ('系统提示词', '普通系统提示词')),
    ('user_prompt_prefix', '用户前置提示词', ('用户前置提示词', '前置提示词', '用户提示词')),
    ('god_war_system_prompt', '神战系统提示词', ('神战系统提示词', '神战提示词')),
]
config_command_alias_to_key_dict = {}
config_command_alias_name_list = []
config_command_label_dict = {}
for config_option_key, config_option_label, alias_name_tuple in config_command_definition_list:
    config_command_label_dict[config_option_key] = config_option_label
    for alias_name in alias_name_tuple:
        normalized_alias_name = utils.safe_str(alias_name).strip().lower()
        if not normalized_alias_name:
            continue
        config_command_alias_to_key_dict[normalized_alias_name] = config_option_key
        config_command_alias_name_list.append(normalized_alias_name)


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


def _parse_scope_toggle_command(command_argument: str) -> dict:
    argument_text = utils.safe_str(command_argument).strip()
    if not argument_text:
        return {'ok': True, 'action': 'show', 'scope': 'group'}

    scope_info = utils.parse_command(
        argument_text,
        allow_no_prefix=True,
        command_name=('全局',),
    )
    if scope_info.get('is_command'):
        action_argument = utils.safe_str(scope_info.get('command_argument', '')).strip()
        if not action_argument:
            return {'ok': True, 'action': 'show', 'scope': 'global'}
        action_info = utils.parse_command(
            action_argument,
            allow_no_prefix=True,
            command_name=('开启', '关闭'),
        )
        if not action_info.get('is_command') or utils.safe_str(action_info.get('command_argument', '')).strip():
            return {'ok': False}
        return {
            'ok': True,
            'action': 'set',
            'scope': 'global',
            'enabled': action_info.get('command_name', '') == '开启',
        }

    action_info = utils.parse_command(
        argument_text,
        allow_no_prefix=True,
        command_name=('开启', '关闭'),
    )
    if not action_info.get('is_command') or utils.safe_str(action_info.get('command_argument', '')).strip():
        return {'ok': False}
    return {
        'ok': True,
        'action': 'set',
        'scope': 'group',
        'enabled': action_info.get('command_name', '') == '开启',
    }


def _parse_god_war_command(command_argument: str) -> dict:
    return _parse_scope_toggle_command(command_argument)


def _bool_to_text(enabled: bool) -> str:
    return '开启' if enabled else '关闭'


def _summarize_config_text(text_value: str, empty_text: str) -> str:
    normalized_text = ' '.join(utils.safe_str(text_value).strip().split())
    if not normalized_text:
        return empty_text
    if len(normalized_text) > 80:
        normalized_text = normalized_text[:77] + '...'
    return normalized_text


def _build_config_overview_value_dict(config_bot_hash: str) -> dict:
    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)
    delay_min_seconds, delay_max_seconds = function.get_segment_delay_range_from_bot_config(bot_config)
    normal_input_limit = function.get_input_limit_from_bot_config(bot_config, god_war_mode=False)
    god_war_input_limit = function.get_input_limit_from_bot_config(bot_config, god_war_mode=True)
    return {
        'global_enable_mode': _bool_to_text(bool(global_config.get('global_enable_switch', True))),
        'global_debug_mode': _bool_to_text(bool(global_config.get('global_debug_mode_switch', False))),
        'global_god_war_mode': _bool_to_text(bool(global_config.get('global_god_war_enable_switch', True))),
        'api_url_text': utils.safe_str(bot_config.get('api_url', '')).strip() or '未配置',
        'api_key_text': function._mask_api_key(utils.safe_str(bot_config.get('api_key', '')).strip()) or '未配置',
        'model_text': utils.safe_str(bot_config.get('model', '')).strip() or '未配置',
        'request_timeout_seconds_text': str(bot_config.get('request_timeout_seconds', 180)),
        'temperature_text': str(bot_config.get('temperature', 0.9)),
        'delay_min_seconds': str(delay_min_seconds),
        'delay_max_seconds': str(delay_max_seconds),
        'normal_input_limit_text': function.format_input_limit(normal_input_limit),
        'god_war_input_limit_text': function.format_input_limit(god_war_input_limit),
        'qq_forward_message_mode': _bool_to_text(bool(bot_config.get('qq_forward_message_switch', False))),
        'system_prompt_summary_text': _summarize_config_text(
            utils.safe_str(bot_config.get('system_prompt', config.SYSTEM_PROMPT)),
            '未配置系统提示词',
        ),
        'user_prompt_prefix_summary_text': _summarize_config_text(
            utils.safe_str(bot_config.get('user_prompt_prefix', '')),
            '当前为空',
        ),
        'god_war_system_prompt_summary_text': _summarize_config_text(
            utils.safe_str(bot_config.get('god_war_system_prompt', config.GOD_WAR_SYSTEM_PROMPT)),
            '未配置神战系统提示词',
        ),
    }


def _parse_bool_config_argument(command_argument: str) -> dict:
    argument_text = utils.safe_str(command_argument).strip()
    if not argument_text:
        return {'ok': True, 'action': 'show'}
    command_info = utils.parse_command(
        argument_text,
        allow_no_prefix=True,
        command_name=('开启', '关闭', 'true', 'false', 'on', 'off', '1', '0', 'yes', 'no'),
    )
    if not command_info.get('is_command') or utils.safe_str(command_info.get('command_argument', '')).strip():
        return {'ok': False}
    return {
        'ok': True,
        'action': 'set',
        'enabled': command_info.get('command_name', '') in {'开启', 'true', 'on', '1', 'yes'},
    }


def _parse_integer_config_argument(command_argument: str, minimum_value=None) -> dict:
    argument_text = utils.safe_str(command_argument).strip()
    if not argument_text:
        return {'ok': True, 'action': 'show'}
    if ' ' in argument_text or '\n' in argument_text or '\t' in argument_text:
        return {'ok': False}
    try:
        int_value = int(argument_text)
    except Exception:
        return {'ok': False}
    if minimum_value is not None and int_value < minimum_value:
        return {'ok': False}
    return {'ok': True, 'action': 'set', 'value': int_value}


def _parse_float_config_argument(command_argument: str) -> dict:
    argument_text = utils.safe_str(command_argument).strip()
    if not argument_text:
        return {'ok': True, 'action': 'show'}
    if ' ' in argument_text or '\n' in argument_text or '\t' in argument_text:
        return {'ok': False}
    try:
        float_value = float(argument_text)
    except Exception:
        return {'ok': False}
    return {'ok': True, 'action': 'set', 'value': float_value}


def _parse_text_config_argument(command_argument: str, allow_default: bool = False) -> dict:
    argument_text = utils.safe_str(command_argument)
    if not argument_text.strip():
        return {'ok': True, 'action': 'show'}
    trimmed_text = argument_text.strip()
    if trimmed_text == '清空':
        return {'ok': True, 'action': 'set', 'value': ''}
    if allow_default and trimmed_text == '默认':
        return {'ok': True, 'action': 'reset_default'}
    return {'ok': True, 'action': 'set', 'value': argument_text}


def handle_gladiator_help(plugin_event) -> None:
    utils.reply_message(plugin_event, message_custom.help_document_dict['gladiator_help'])


def handle_gladiator_join(plugin_event, command_argument: str) -> None:
    result = function.add_waiting_player(plugin_event, command_argument)
    if not result.get('ok'):
        if result.get('reason') == 'input_too_long':
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_input_limit_exceeded',
                    extra_value_dict={
                        'mode_name': result.get('mode_name', '普通'),
                        'input_limit_text': result.get('input_limit_text', function.format_input_limit(0)),
                        'current_length_text': result.get(
                            'current_length_text',
                            function.format_weighted_text_length(result.get('current_length', 0)),
                        ),
                    },
                ),
            )
            return
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
        if result.get('reason') == 'input_too_long':
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_input_limit_exceeded',
                    extra_value_dict={
                        'mode_name': result.get('mode_name', '普通'),
                        'input_limit_text': result.get('input_limit_text', function.format_input_limit(0)),
                        'current_length_text': result.get(
                            'current_length_text',
                            function.format_weighted_text_length(result.get('current_length', 0)),
                        ),
                    },
                ),
            )
            return
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

    segment_list = [
        render_custom_message(
            plugin_event,
            'reply_room_query_header',
            extra_value_dict={'waiting_count': snapshot['waiting_count']},
        )
    ]
    for entry in function.build_query_entries(snapshot['waiting_room']):
        segment_list.append(
            render_custom_message(
                plugin_event,
                'reply_room_query_item',
                extra_value_dict=entry,
            )
        )
    function.send_segment_messages(plugin_event, segment_list, prefer_forward=True)


def handle_gladiator_status(plugin_event) -> None:
    status_info = function.get_gladiator_status(plugin_event)
    bot_config = function.get_runtime_bot_config(plugin_event)
    utils.reply_message(
        plugin_event,
        render_custom_message(
            plugin_event,
            'reply_gladiator_status',
            extra_value_dict={
                'battle_mode': '神战' if status_info.get('god_war_enable_switch', False) else '普通',
                'battle_progress': '进行中' if status_info.get('battle_running', False) else '未开始',
                'waiting_count': status_info.get('waiting_count', 0),
                'normal_input_limit_text': function.format_input_limit(bot_config.get('normal_input_limit', 0)),
                'god_war_input_limit_text': function.format_input_limit(bot_config.get('god_war_input_limit', 0)),
            },
        ),
    )


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


def _parse_delay_config_tokens(argument_text: str) -> dict:
    if not utils.safe_str(argument_text).strip():
        return {'ok': True, 'config_type': 'delay', 'action': 'show'}
    first_token, remaining_text = utils.split_first_token(argument_text)
    second_token, tail_text = utils.split_first_token(remaining_text)
    if not first_token or not second_token or utils.safe_str(tail_text).strip():
        return {'ok': False, 'config_type': 'delay'}

    try:
        delay_min_seconds = int(first_token)
        delay_max_seconds = int(second_token)
    except Exception:
        return {'ok': False, 'config_type': 'delay'}

    if delay_min_seconds <= 0 or delay_max_seconds <= 0 or delay_max_seconds < delay_min_seconds:
        return {'ok': False, 'config_type': 'delay'}
    return {
        'ok': True,
        'config_type': 'delay',
        'action': 'set',
        'delay_min_seconds': delay_min_seconds,
        'delay_max_seconds': delay_max_seconds,
    }


def _parse_input_limit_mode(mode_text: str) -> str:
    mode_info = utils.parse_command(
        mode_text,
        allow_no_prefix=True,
        command_name=('普通模式', '神战模式', '普通', '神战'),
    )
    if not mode_info.get('is_command'):
        return ''
    command_name = mode_info.get('command_name', '')
    if command_name in {'普通', '普通模式'}:
        return 'normal'
    if command_name in {'神战', '神战模式'}:
        return 'god_war'
    return ''


def _parse_input_limit_config_tokens(argument_text: str) -> dict:
    if not utils.safe_str(argument_text).strip():
        return {'ok': True, 'config_type': 'input_limit', 'action': 'show'}
    parse_whole_value_result = _parse_integer_config_argument(argument_text, minimum_value=0)
    if parse_whole_value_result.get('ok') and parse_whole_value_result.get('action') == 'set':
        return {
            'ok': True,
            'config_type': 'input_limit',
            'action': 'set',
            'target_mode': 'all',
            'input_limit': parse_whole_value_result['value'],
        }
    mode_info = utils.parse_command(
        argument_text,
        allow_no_prefix=True,
        command_name=('普通模式', '神战模式', '普通', '神战'),
    )
    if not mode_info.get('is_command'):
        return {'ok': False, 'config_type': 'input_limit'}

    target_mode = _parse_input_limit_mode(mode_info.get('command_name', ''))
    if not target_mode:
        return {'ok': False, 'config_type': 'input_limit'}

    parse_value_result = _parse_integer_config_argument(mode_info.get('command_argument', ''), minimum_value=0)
    if not parse_value_result.get('ok') or parse_value_result.get('action') != 'set':
        return {'ok': False, 'config_type': 'input_limit'}
    return {
        'ok': True,
        'config_type': 'input_limit',
        'action': 'set',
        'target_mode': target_mode,
        'input_limit': parse_value_result['value'],
    }


def _parse_config_command(command_argument: str) -> dict:
    argument_text = utils.safe_str(command_argument).strip()
    if not argument_text:
        return {'ok': True, 'config_type': 'all', 'action': 'show'}
    command_info = utils.parse_command(
        argument_text,
        allow_no_prefix=True,
        command_name=config_command_alias_name_list,
    )
    if not command_info.get('is_command'):
        return {'ok': False, 'config_type': ''}
    config_type = config_command_alias_to_key_dict.get(command_info.get('command_name', ''), '')
    return {
        'ok': True,
        'config_type': config_type,
        'config_label': config_command_label_dict.get(config_type, ''),
        'command_argument': command_info.get('command_argument', ''),
    }


def handle_gladiator_config(plugin_event, config_bot_hash: str, command_argument: str) -> None:
    parse_result = _parse_config_command(command_argument)
    if not parse_result.get('ok'):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_config_invalid'))
        return

    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)
    config_type = parse_result.get('config_type', '')
    config_label = parse_result.get('config_label', '')
    config_argument = parse_result.get('command_argument', '')

    if config_type == 'all':
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_config_status',
                extra_value_dict=_build_config_overview_value_dict(config_bot_hash),
            ),
        )
        return

    if config_type == 'delay':
        delay_parse_result = _parse_delay_config_tokens(config_argument)
        if not delay_parse_result.get('ok'):
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_delay_config_invalid'))
            return
        delay_min_seconds, delay_max_seconds = function.get_segment_delay_range_from_bot_config(bot_config)
        if delay_parse_result.get('action') == 'show':
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_config_item_status',
                    extra_value_dict={
                        'config_label': config_label,
                        'config_value_display': f'{delay_min_seconds} 到 {delay_max_seconds} 秒',
                    },
                ),
            )
            return
        bot_config['segment_delay_min_seconds'] = delay_parse_result['delay_min_seconds']
        bot_config['segment_delay_max_seconds'] = delay_parse_result['delay_max_seconds']
        utils.save_bot_config(config_bot_hash, bot_config)
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_config_updated',
                extra_value_dict={
                    'config_label': config_label,
                    'config_value_display': (
                        f'{delay_parse_result["delay_min_seconds"]} 到 {delay_parse_result["delay_max_seconds"]} 秒'
                    ),
                },
            ),
        )
        return

    if config_type == 'input_limit':
        input_limit_parse_result = _parse_input_limit_config_tokens(config_argument)
        if not input_limit_parse_result.get('ok'):
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_input_limit_invalid'))
            return
        normal_input_limit = function.get_input_limit_from_bot_config(bot_config, god_war_mode=False)
        god_war_input_limit = function.get_input_limit_from_bot_config(bot_config, god_war_mode=True)
        if input_limit_parse_result.get('action') == 'show':
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_config_item_status',
                    extra_value_dict={
                        'config_label': config_label,
                        'config_value_display': (
                            f'普通模式 {function.format_input_limit(normal_input_limit)}；'
                            f'神战模式 {function.format_input_limit(god_war_input_limit)}'
                        ),
                    },
                ),
            )
            return
        target_mode = input_limit_parse_result.get('target_mode')
        if target_mode == 'all':
            bot_config['normal_input_limit'] = input_limit_parse_result['input_limit']
            bot_config['god_war_input_limit'] = input_limit_parse_result['input_limit']
            utils.save_bot_config(config_bot_hash, bot_config)
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_config_updated',
                    extra_value_dict={
                        'config_label': '普通/神战字数限制',
                        'config_value_display': function.format_input_limit(input_limit_parse_result['input_limit']),
                    },
                ),
            )
            return
        config_key = 'normal_input_limit'
        target_mode_name = '普通模式'
        if target_mode == 'god_war':
            config_key = 'god_war_input_limit'
            target_mode_name = '神战模式'
        bot_config[config_key] = input_limit_parse_result['input_limit']
        utils.save_bot_config(config_bot_hash, bot_config)
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_config_updated',
                extra_value_dict={
                    'config_label': f'{target_mode_name}字数限制',
                    'config_value_display': function.format_input_limit(input_limit_parse_result['input_limit']),
                },
            ),
        )
        return

    if config_type in {'global_enable', 'global_debug', 'global_god_war', 'forward'}:
        bool_parse_result = _parse_bool_config_argument(config_argument)
        if not bool_parse_result.get('ok'):
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_config_invalid'))
            return
        config_value_lookup_dict = {
            'global_enable': bool(global_config.get('global_enable_switch', True)),
            'global_debug': bool(global_config.get('global_debug_mode_switch', False)),
            'global_god_war': bool(global_config.get('global_god_war_enable_switch', True)),
            'forward': bool(bot_config.get('qq_forward_message_switch', False)),
        }
        if bool_parse_result.get('action') == 'show':
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_config_item_status',
                    extra_value_dict={
                        'config_label': config_label,
                        'config_value_display': _bool_to_text(config_value_lookup_dict.get(config_type, False)),
                    },
                ),
            )
            return
        target_enabled = bool(bool_parse_result.get('enabled', False))
        if config_type == 'global_enable':
            global_config['global_enable_switch'] = target_enabled
            utils.save_global_config(global_config)
        elif config_type == 'global_debug':
            global_config['global_debug_mode_switch'] = target_enabled
            utils.save_global_config(global_config)
        elif config_type == 'global_god_war':
            global_config['global_god_war_enable_switch'] = target_enabled
            utils.save_global_config(global_config)
        else:
            bot_config['qq_forward_message_switch'] = target_enabled
            utils.save_bot_config(config_bot_hash, bot_config)
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_config_updated',
                extra_value_dict={
                    'config_label': config_label,
                    'config_value_display': _bool_to_text(target_enabled),
                },
            ),
        )
        return

    if config_type == 'timeout':
        timeout_parse_result = _parse_integer_config_argument(config_argument, minimum_value=1)
        if not timeout_parse_result.get('ok'):
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_config_invalid'))
            return
        if timeout_parse_result.get('action') == 'show':
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_config_item_status',
                    extra_value_dict={
                        'config_label': config_label,
                        'config_value_display': f'{bot_config.get("request_timeout_seconds", 180)} 秒',
                    },
                ),
            )
            return
        bot_config['request_timeout_seconds'] = timeout_parse_result['value']
        utils.save_bot_config(config_bot_hash, bot_config)
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_config_updated',
                extra_value_dict={
                    'config_label': config_label,
                    'config_value_display': f'{timeout_parse_result["value"]} 秒',
                },
            ),
        )
        return

    if config_type == 'temperature':
        temperature_parse_result = _parse_float_config_argument(config_argument)
        if not temperature_parse_result.get('ok'):
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_config_invalid'))
            return
        if temperature_parse_result.get('action') == 'show':
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_config_item_status',
                    extra_value_dict={
                        'config_label': config_label,
                        'config_value_display': str(bot_config.get('temperature', 0.9)),
                    },
                ),
            )
            return
        bot_config['temperature'] = temperature_parse_result['value']
        utils.save_bot_config(config_bot_hash, bot_config)
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_config_updated',
                extra_value_dict={
                    'config_label': config_label,
                    'config_value_display': str(temperature_parse_result['value']),
                },
            ),
        )
        return

    if config_type in {'api_url', 'api_key', 'model', 'system_prompt', 'user_prompt_prefix', 'god_war_system_prompt'}:
        allow_default = config_type in {'system_prompt', 'god_war_system_prompt'}
        text_parse_result = _parse_text_config_argument(config_argument, allow_default=allow_default)
        if not text_parse_result.get('ok'):
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_config_invalid'))
            return
        config_key_lookup_dict = {
            'api_url': 'api_url',
            'api_key': 'api_key',
            'model': 'model',
            'system_prompt': 'system_prompt',
            'user_prompt_prefix': 'user_prompt_prefix',
            'god_war_system_prompt': 'god_war_system_prompt',
        }
        config_key = config_key_lookup_dict[config_type]
        if text_parse_result.get('action') == 'show':
            current_text = utils.safe_str(bot_config.get(config_key, '')).strip()
            if config_type == 'system_prompt' and not current_text:
                current_text = config.SYSTEM_PROMPT
            if config_type == 'god_war_system_prompt' and not current_text:
                current_text = config.GOD_WAR_SYSTEM_PROMPT
            if config_type == 'api_key':
                current_text = function._mask_api_key(current_text) or '未配置'
            else:
                current_text = current_text or '当前为空'
            utils.reply_message(
                plugin_event,
                render_custom_message(
                    plugin_event,
                    'reply_config_item_status',
                    extra_value_dict={
                        'config_label': config_label,
                        'config_value_display': current_text,
                    },
                ),
            )
            return
        if text_parse_result.get('action') == 'reset_default':
            if config_type == 'system_prompt':
                bot_config[config_key] = config.SYSTEM_PROMPT
            else:
                bot_config[config_key] = config.GOD_WAR_SYSTEM_PROMPT
        else:
            bot_config[config_key] = text_parse_result.get('value', '')
        utils.save_bot_config(config_bot_hash, bot_config)
        display_text = utils.safe_str(bot_config.get(config_key, '')).strip() or '当前为空'
        if config_type == 'api_key':
            display_text = function._mask_api_key(utils.safe_str(bot_config.get(config_key, '')).strip()) or '未配置'
        elif config_type in {'system_prompt', 'user_prompt_prefix', 'god_war_system_prompt'}:
            display_text = _summarize_config_text(display_text, '当前为空')
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_config_updated',
                extra_value_dict={
                    'config_label': config_label,
                    'config_value_display': display_text,
                },
            ),
        )
        return

    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_config_invalid'))


def handle_gladiator_god_war(plugin_event, config_bot_hash: str, command_argument: str) -> None:
    parse_result = _parse_god_war_command(command_argument)
    if not parse_result.get('ok'):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_god_war_invalid'))
        return

    total_switch = function.is_global_god_war_enabled()
    group_override_switch = function.is_group_god_war_override_enabled(plugin_event)
    group_switch = function.is_group_god_war_enabled(plugin_event)
    effective_switch = function.get_effective_god_war_enabled(plugin_event)

    if parse_result.get('action') == 'show':
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_god_war_status',
                extra_value_dict={
                    'god_war_mode': '开启' if effective_switch else '关闭',
                    'god_war_total_mode': '开启' if total_switch else '关闭',
                    'god_war_group_override_mode': '开启' if group_override_switch else '关闭',
                    'god_war_group_mode': '开启' if group_switch else '关闭',
                },
            ),
        )
        return

    target_switch = bool(parse_result.get('enabled', False))
    target_scope = parse_result.get('scope', 'group')
    current_switch = total_switch if target_scope == 'global' else (group_override_switch and group_switch == target_switch)

    if target_scope == 'global' and current_switch == target_switch:
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                (
                    'reply_god_war_global_already_enabled'
                    if target_switch and target_scope == 'global'
                    else 'reply_god_war_global_already_disabled'
                    if not target_switch and target_scope == 'global'
                    else 'reply_god_war_group_already_enabled'
                    if target_switch
                    else 'reply_god_war_group_already_disabled'
                ),
            ),
        )
        return

    if target_scope == 'group' and group_override_switch and group_switch == target_switch:
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_god_war_group_already_enabled' if target_switch else 'reply_god_war_group_already_disabled',
            ),
        )
        return

    if target_scope == 'global':
        function.set_global_god_war_enabled(target_switch)
    else:
        function.set_group_god_war_enabled(plugin_event, target_switch)

    utils.reply_message(
        plugin_event,
        render_custom_message(
            plugin_event,
            (
                'reply_god_war_global_enabled'
                if target_switch and target_scope == 'global'
                else 'reply_god_war_global_disabled'
                if not target_switch and target_scope == 'global'
                else 'reply_god_war_group_enabled'
                if target_switch
                else 'reply_god_war_group_disabled'
            ),
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
    if at_item_list and not utils.is_force_reply_to_current_bot(at_item_list, plugin_event):
        return
    command_info = utils.parse_command(
        remaining_after_at,
        prefix_list=config.allowed_prefix_list,
        allow_no_prefix=False,
        command_name=command_name_list,
    )

    if not command_info['is_command']:
        generic_command_info = utils.parse_command(
            remaining_after_at,
            prefix_list=config.allowed_prefix_list,
            allow_no_prefix=False,
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

    if command_name == '状态':
        handle_gladiator_status(plugin_event)
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

    if command_name == '神战':
        parse_result = _parse_god_war_command(command_argument)
        target_scope = parse_result.get('scope', 'group') if parse_result.get('ok') else 'group'
        if target_scope == 'global':
            if not sender_has_master_permission(plugin_event):
                reply_global_permission_denied(plugin_event)
                return
        elif not sender_has_group_management_permission(plugin_event):
            reply_permission_denied(plugin_event)
            return
        handle_gladiator_god_war(plugin_event, config_bot_hash, command_argument)
        return

    if command_name == '开始':
        handle_gladiator_start(plugin_event, Proc)
        return

    _reply_unknown_gladiator_command(plugin_event)
