# -*- encoding: utf-8 -*-
"""矮人笑话命令解析与回复。"""

from . import config
from . import function
from . import message_custom
from . import utils


def handle_init(plugin_event, Proc) -> None:
    """初始化目录，并确保全局笑话合集已经落地。"""
    utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    function.ensure_joke_pack_initialized(Proc)
    utils.info_log(Proc, 'DwarfJokes init 完成。')


def handle_init_after(plugin_event, Proc) -> None:
    """所有插件 init 后再确认一次合集文件。"""
    utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    function.ensure_joke_pack_initialized(Proc)
    utils.debug_log(Proc, 'DwarfJokes init_after 已执行。', plugin_event=plugin_event)


def handle_private_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_group_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_poke(plugin_event, Proc) -> None:
    """本插件不响应戳一戳。"""
    return


def handle_friend_add_request(plugin_event, Proc) -> None:
    return


def handle_group_invite_request(plugin_event, Proc) -> None:
    return


def handle_group_member_increase(plugin_event, Proc) -> None:
    return


def handle_heartbeat(plugin_event, Proc) -> None:
    return


def handle_save(plugin_event, Proc) -> None:
    """合集在每次增删时已经落盘。"""
    return


def sender_has_master_permission(plugin_event) -> bool:
    """OlivaDiceCore 骰主或本插件骰主。"""
    return utils.get_master_permission_info(plugin_event)['sender_is_master']


def sender_can_manage_jokes(plugin_event) -> bool:
    """新增/删除笑话：骰主或本插件管理员。"""
    return sender_has_master_permission(plugin_event) or utils.is_sender_configured_admin(plugin_event)


def sender_can_manage_admins(plugin_event) -> bool:
    """管理员增删只允许骰主。"""
    return sender_has_master_permission(plugin_event)


def build_runtime_value_dict(plugin_event, command_argument: str = '', extra_value_dict=None):
    """构建回复词格式化变量。"""
    reply_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    variable_dict = utils.load_bot_message_variables(reply_bot_hash)
    runtime_value_dict = utils.build_base_template_value_dict(
        plugin_event,
        command_argument=command_argument,
        extra_value_dict={
            'rank_gate': config.joke_duplicate_rank_gate,
            'max_length': config.joke_text_max_length,
        },
    )
    runtime_value_dict.update(variable_dict)
    if isinstance(extra_value_dict, dict):
        runtime_value_dict.update(extra_value_dict)
    return runtime_value_dict


def render_custom_message(plugin_event, message_key: str, command_argument: str = '', extra_value_dict=None) -> str:
    """读取当前 bot 的自定义回复并渲染。"""
    reply_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    custom_message_dict = utils.load_bot_message_custom(reply_bot_hash)
    template_text = custom_message_dict.get(message_key, '')
    value_dict = build_runtime_value_dict(plugin_event, command_argument, extra_value_dict)
    return utils.render_text_template(template_text, value_dict)


def reply_permission_denied(plugin_event, admin_command: bool = False) -> None:
    """按命令类型发送权限不足提示。"""
    message_key = 'reply_permission_denied_admin' if admin_command else 'reply_permission_denied'
    utils.reply_message(plugin_event, render_custom_message(plugin_event, message_key))


def format_admin_list_text(admin_id_list) -> str:
    """管理员列表展示文本。"""
    if admin_id_list:
        return ', '.join(admin_id_list)
    return message_custom.default_custom_message_dict['reply_admin_list_empty']


def handle_draw(plugin_event, draw_count: int = 1) -> None:
    """抽取笑话。"""
    draw_result = function.draw_jokes(draw_count)
    if not draw_result.get('ok'):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_draw_empty'))
        return
    utils.reply_message(plugin_event, function.format_draw_result(draw_result))


def handle_add(plugin_event, joke_text: str) -> None:
    """新增笑话。"""
    if not sender_can_manage_jokes(plugin_event):
        reply_permission_denied(plugin_event)
        return
    stripped_text = utils.safe_str(joke_text).strip()
    if not stripped_text:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_add_usage'))
        return
    add_result = function.add_joke(stripped_text)
    if add_result.get('ok'):
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_add_success',
                extra_value_dict={
                    'joke_id': add_result['id'],
                    'joke_count': add_result['count'],
                },
            ),
        )
        return
    reason = add_result.get('reason')
    if reason == 'empty':
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_add_empty'))
        return
    if reason == 'too_long':
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_add_too_long',
                extra_value_dict={'max_length': add_result.get('max_length', config.joke_text_max_length)},
            ),
        )
        return
    if reason == 'duplicate':
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_add_duplicate',
                extra_value_dict={
                    'joke_id': add_result['id'],
                    'rank': add_result['rank'],
                    'rank_gate': config.joke_duplicate_rank_gate,
                },
            ),
        )
        return
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_add_save_failed'))


def handle_delete(plugin_event, argument_text: str) -> None:
    """删除笑话。"""
    if not sender_can_manage_jokes(plugin_event):
        reply_permission_denied(plugin_event)
        return
    stripped_text = utils.safe_str(argument_text).strip()
    if not stripped_text:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_delete_usage'))
        return
    if not stripped_text.isdigit():
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_delete_invalid'))
        return
    delete_result = function.delete_joke(int(stripped_text))
    if delete_result.get('ok'):
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_delete_success',
                extra_value_dict={
                    'joke_id': delete_result['id'],
                    'joke_count': delete_result['count'],
                },
            ),
        )
        return
    if delete_result.get('reason') == 'missing':
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_delete_missing',
                extra_value_dict={'joke_id': delete_result.get('id', stripped_text)},
            ),
        )
        return
    if delete_result.get('reason') == 'invalid_id':
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_delete_invalid'))
        return
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_delete_save_failed'))


def handle_list(plugin_event, argument_text: str = '') -> None:
    """无参数展示合集数量；带序号则展示指定笑话。"""
    stripped_text = utils.safe_str(argument_text).strip()
    if not stripped_text:
        summary = function.get_joke_pack_summary()
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_list',
                extra_value_dict={
                    'joke_count': summary['count'],
                    'next_id': summary['next_id'],
                },
            ),
        )
        return
    if not stripped_text.isdigit():
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_list_invalid'))
        return
    joke_id = int(stripped_text)
    if joke_id < 1:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_list_invalid'))
        return
    joke_item = function.get_joke_by_id(joke_id)
    if joke_item is None:
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_list_missing',
                extra_value_dict={'joke_id': joke_id},
            ),
        )
        return
    utils.reply_message(
        plugin_event,
        render_custom_message(
            plugin_event,
            'reply_list_item',
            extra_value_dict={
                'joke_id': joke_item.get('id', joke_id),
                'joke_text': utils.safe_str(joke_item.get('text', '')).strip(),
            },
        ),
    )


def handle_help(plugin_event) -> None:
    """帮助文档。"""
    help_text = message_custom.help_document_dict['dwarf_help']
    prefix_text = config.allowed_prefix_list[0] if config.allowed_prefix_list else '.'
    utils.reply_message(plugin_event, help_text.replace('{prefix}', prefix_text))


def handle_admin(plugin_event, argument_text: str) -> None:
    """添加或删除本插件管理员。"""
    if not sender_can_manage_admins(plugin_event):
        reply_permission_denied(plugin_event, admin_command=True)
        return

    action_info = function.match_greedy_command(argument_text, config.admin_action_names)
    if not action_info['is_command']:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_admin_usage'))
        return

    config_bot_hash = utils.get_bot_hash_from_event(plugin_event)
    target_id_list = utils.normalize_id_list(action_info['command_argument'])
    admin_list = utils.get_configured_admin_list(config_bot_hash)
    action_name = action_info['command_name']

    if action_name in config.add_command_names:
        if not target_id_list:
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_admin_add_empty'))
            return
        for target_id in target_id_list:
            if target_id not in admin_list:
                admin_list.append(target_id)
        utils.set_configured_admin_list(config_bot_hash, admin_list)
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_admin_add_success',
                extra_value_dict={
                    'admin_ids': ', '.join(target_id_list),
                    'admin_list': format_admin_list_text(admin_list),
                },
            ),
        )
        return

    if action_name in config.delete_command_names:
        if not target_id_list:
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_admin_del_empty'))
            return
        admin_list = [admin_id for admin_id in admin_list if admin_id not in target_id_list]
        utils.set_configured_admin_list(config_bot_hash, admin_list)
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_admin_del_success',
                extra_value_dict={
                    'admin_ids': ', '.join(target_id_list),
                    'admin_list': format_admin_list_text(admin_list),
                },
            ),
        )
        return

    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_admin_usage'))


def dispatch_dwarf_command(plugin_event, command_argument: str) -> None:
    """
    主命令命中后的子命令分发。
    全部使用贪婪匹配，不按空格切第一词。
    未命中子命令且不是纯数字时保持静默。
    """
    argument_text = utils.safe_str(command_argument)
    if argument_text.strip() == '':
        handle_draw(plugin_event, 1)
        return

    sub_info = function.match_greedy_command(argument_text, config.subcommand_names)
    if sub_info['is_command']:
        command_name = sub_info['command_name']
        remaining_argument = sub_info['command_argument']
        if command_name == 'admin':
            handle_admin(plugin_event, remaining_argument)
            return
        if command_name in config.add_command_names:
            handle_add(plugin_event, remaining_argument)
            return
        if command_name in config.delete_command_names:
            handle_delete(plugin_event, remaining_argument)
            return
        if command_name in config.list_command_names:
            handle_list(plugin_event, remaining_argument)
            return
        if command_name in config.help_command_names:
            handle_help(plugin_event)
            return
        return

    draw_count = function.parse_draw_count(argument_text)
    if draw_count is not None:
        handle_draw(plugin_event, draw_count)
        return


@utils.log_exception('handle_message')
def handle_message(plugin_event, Proc) -> None:
    """统一消息入口：前缀 + 贪婪主命令，未命中不回复。"""
    config_bot_hash = utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    function.ensure_joke_pack_initialized(Proc)

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
        command_name=config.primary_command_names,
    )
    if not command_info['is_command']:
        return

    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)
    if not global_config.get('global_enable_switch', True):
        utils.debug_log(Proc, '全局启用开关已关闭，普通命令不再处理。', plugin_event=plugin_event)
        return
    if not bot_config.get('bot_enable_switch', True):
        utils.debug_log(Proc, '当前 Bot 开关已关闭，普通命令不再处理。', plugin_event=plugin_event)
        return
    if utils.is_group_disabled(plugin_event):
        utils.debug_log(Proc, '当前群已在本插件群禁用列表中，普通命令不再处理。', plugin_event=plugin_event)
        return

    dispatch_dwarf_command(plugin_event, command_info['command_argument'])
