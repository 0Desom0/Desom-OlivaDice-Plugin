# -*- encoding: utf-8 -*-
"""
消息解析与回复模块。

职责边界严格保持如下：
1. main.py 只把事件转交到这里。
2. 这里负责命令解析、权限判断、回复组织。
3. 这里不承担通用能力实现，那些都在 utils.py。
4. 这里不提前把业务逻辑塞进 function.py，因为本模板就是轻量结构模板。
"""

from . import config
from . import function
from . import message_custom
from . import utils


management_command_name_set = {'tplglobal', 'tplbot'}


def handle_init(plugin_event, Proc) -> None:
    """插件 init 事件。这里只做初始化确认与日志提示。"""
    utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    utils.info_log(Proc, '轻量级插件模板 init 完成。')


def handle_init_after(plugin_event, Proc) -> None:
    """插件 init_after 事件。这里只保留结构化入口。"""
    utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    utils.debug_log(Proc, '轻量级插件模板 init_after 已执行。', plugin_event=plugin_event)


def handle_private_message(plugin_event, Proc) -> None:
    """私聊消息统一入口。"""
    handle_message(plugin_event, Proc)


def handle_group_message(plugin_event, Proc) -> None:
    """群聊消息统一入口。"""
    handle_message(plugin_event, Proc)


def handle_poke(plugin_event, Proc) -> None:
    """
    戳一戳事件处理示例。

    这里保留与官方最小模板相近的行为：
    - 戳到当前 bot 时回复。
    - 自己戳自己时也允许回复。
    - 没有有效群上下文时，保留一个兜底回复示例。
    """
    config_bot_hash = utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)
    if not global_config.get('global_enable_switch', True):
        return
    if not bot_config.get('bot_enable_switch', True):
        return

    target_id = utils.safe_str(getattr(plugin_event.data, 'target_id', ''))
    group_id = utils.safe_str(getattr(plugin_event.data, 'group_id', ''))
    self_id = utils.get_self_id_from_event(plugin_event)
    sender_id = utils.get_sender_id_from_event(plugin_event)

    if target_id in [self_id, sender_id] or group_id == '-1':
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_poke'))


def handle_friend_add_request(plugin_event, Proc) -> None:
    """
    好友申请事件示例。

    模板默认只记录日志，不自动同意申请，避免直接带出有副作用的默认行为。
    需要时可以在这里接入你自己的审核或自动通过逻辑。
    """
    requester_id = utils.safe_str(getattr(plugin_event.data, 'user_id', '')) or '未知'
    utils.info_log(Proc, f'收到好友申请事件示例：user_id={requester_id}')


def handle_group_invite_request(plugin_event, Proc) -> None:
    """
    群邀请事件示例。

    模板默认只做日志记录；如果你想自动同意某些群邀请，可以把规则写在这里。
    """
    group_id = utils.safe_str(getattr(plugin_event.data, 'group_id', '')) or '未知'
    utils.info_log(Proc, f'收到群邀请事件示例：group_id={group_id}')


def handle_group_member_increase(plugin_event, Proc) -> None:
    """
    群成员增加事件示例。

    这里适合放欢迎语、自动发私信或初始化群成员数据之类的逻辑。
    模板默认只记录日志，避免直接发送消息影响实际群聊。
    """
    group_id = utils.safe_str(getattr(plugin_event.data, 'group_id', '')) or '未知'
    user_id = utils.safe_str(getattr(plugin_event.data, 'user_id', '')) or '未知'
    utils.info_log(Proc, f'收到群成员增加事件示例：group_id={group_id} user_id={user_id}')


def handle_heartbeat(plugin_event, Proc) -> None:
    """
    心跳事件示例。

    这里通常用于轻量保活、定时缓存刷新或状态同步。
    为了避免刷屏，模板默认只打 debug 日志。
    """
    utils.debug_log(Proc, '收到 heartbeat 事件示例。', plugin_event=plugin_event)


def handle_save(plugin_event, Proc) -> None:
    """
    保存事件示例。

    如果你的插件维护了额外内存态缓存，可以在这里统一落盘。
    当前模板只保留一个日志示例入口。
    """
    utils.info_log(Proc, '收到 save 事件示例，可在这里执行额外的持久化逻辑。')


# 这里是通过utils里面的函数放到这里进行组装，所以丢在这里更方便取用
def is_management_command(command_name: str) -> bool:
    """判断命令是否属于管理命令。"""
    return command_name in management_command_name_set


def sender_has_master_permission(plugin_event) -> bool:
    """统一判断是否拥有骰主权限。"""
    master_permission_info = utils.get_master_permission_info(plugin_event)
    return master_permission_info['sender_is_master']


def build_runtime_value_dict(plugin_event, command_argument: str = '', extra_value_dict=None):
    """构建本模块用到的格式化变量字典。"""
    config_bot_hash = utils.get_bot_hash_from_event(plugin_event)
    reply_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)
    configured_master_list = utils.get_configured_master_list(config_bot_hash)
    variable_dict = utils.load_bot_message_variables(reply_bot_hash)

    # 这里新增了不少字段，在实际编写过程中也可以用类似的方法去新增字段
    runtime_value_dict = utils.build_base_template_value_dict(
        plugin_event,
        command_argument=command_argument,
        extra_value_dict={
            'global_enable': 'ON' if global_config.get('global_enable_switch', True) else 'OFF',
            'global_debug': 'ON' if global_config.get('global_debug_mode_switch', False) else 'OFF',
            'bot_enable': 'ON' if bot_config.get('bot_enable_switch', True) else 'OFF',
            'configured_masters': ', '.join(configured_master_list) or '无',
            'function_module_note': function.function_module_note,
        },
    )
    runtime_value_dict.update(variable_dict)
    if isinstance(extra_value_dict, dict):
        runtime_value_dict.update(extra_value_dict)
    return runtime_value_dict


def render_custom_message(plugin_event, message_key: str, command_argument: str = '', extra_value_dict=None) -> str:
    """从当前 bot 的自定义回复集中读取并渲染一条消息。"""
    reply_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    custom_message_dict = utils.load_bot_message_custom(reply_bot_hash)
    template_text = custom_message_dict.get(message_key, '')
    value_dict = build_runtime_value_dict(plugin_event, command_argument, extra_value_dict)
    return utils.render_text_template(template_text, value_dict)


def reply_permission_denied(plugin_event) -> None:
    """统一发送权限不足提示。"""
    utils.reply_message(
        plugin_event,
        render_custom_message(plugin_event, 'reply_permission_denied'),
    )


def parse_secondary_action(command_argument: str):
    """把命令参数拆成 action 与剩余参数。"""
    return utils.split_first_token(command_argument)


# 这里是命令函数
def handle_tplhelp(plugin_event) -> None:
    """帮助命令示例。"""
    help_text = message_custom.help_document_dict['template_help']
    utils.reply_message(plugin_event, help_text)


def handle_tplping(plugin_event) -> None:
    """最基础的自定义回复示例。"""
    reply_text = render_custom_message(plugin_event, 'reply_ping')
    utils.reply_message(plugin_event, reply_text)


def handle_tplecho(plugin_event, command_argument: str) -> None:
    """
    回声命令示例。

    这个命令专门演示 utils.reply_message 的 record_by_logger 开关。
    - .tplecho 你好 -> 尝试按日志记录型回复发送
    - .tplecho silent 你好 -> 纯净回复，不主动调用日志钩子
    """
    action_name, remaining_argument = parse_secondary_action(command_argument)
    record_by_logger = True
    echo_text = command_argument

    if action_name == 'silent':
        record_by_logger = False
        echo_text = remaining_argument

    if not echo_text.strip():
        echo_text = render_custom_message(plugin_event, 'reply_help_hint')
    else:
        echo_text = render_custom_message(
            plugin_event,
            'reply_echo',
            command_argument=echo_text,
            extra_value_dict={'echo_text': echo_text},
        )

    utils.reply_message(plugin_event, echo_text, record_by_logger=record_by_logger)


def handle_tplglobal(plugin_event, command_argument: str) -> None:
    """全局配置命令示例。"""
    if not sender_has_master_permission(plugin_event):
        reply_permission_denied(plugin_event)
        return

    global_config = utils.load_global_config()
    action_name, action_argument = parse_secondary_action(command_argument)

    if action_name in ['', 'status']:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_global_status'))
        return

    if action_name == 'on':
        global_config['global_enable_switch'] = True
    elif action_name == 'off':
        global_config['global_enable_switch'] = False
    elif action_name == 'debug':
        debug_action, _unused_argument = parse_secondary_action(action_argument)
        if debug_action == 'on':
            global_config['global_debug_mode_switch'] = True
        elif debug_action == 'off':
            global_config['global_debug_mode_switch'] = False
        else:
            utils.reply_message(plugin_event, '用法：.tplglobal debug on 或 .tplglobal debug off')
            return
    else:
        utils.reply_message(plugin_event, '用法：.tplglobal status/on/off/debug on/debug off')
        return

    utils.save_global_config(global_config)
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_global_status'))


def handle_tplbot(plugin_event, command_argument: str) -> None:
    """Bot 级隔离配置命令示例。"""
    if not sender_has_master_permission(plugin_event):
        reply_permission_denied(plugin_event)
        return

    config_bot_hash = utils.get_bot_hash_from_event(plugin_event)
    bot_config = utils.load_bot_config(config_bot_hash)
    action_name, action_argument = parse_secondary_action(command_argument)

    if action_name in ['', 'status']:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_bot_status'))
        return

    if action_name == 'on':
        bot_config['bot_enable_switch'] = True
        utils.save_bot_config(config_bot_hash, bot_config)
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_bot_status'))
        return

    if action_name == 'off':
        bot_config['bot_enable_switch'] = False
        utils.save_bot_config(config_bot_hash, bot_config)
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_bot_status'))
        return

    # 以上是回复使用自定义消息范例，以下是回复不使用自定义消息范例
    
    if action_name == 'master':
        master_action, master_argument = parse_secondary_action(action_argument)
        configured_master_list = utils.get_configured_master_list(config_bot_hash)
        target_master_id_list = utils.normalize_id_list(master_argument)

        if master_action in ['', 'list']:
            master_text = ', '.join(configured_master_list) or '无'
            utils.reply_message(plugin_event, f'当前本插件配置骰主列表：{master_text}')
            return

        if master_action == 'add':
            for target_master_id in target_master_id_list:
                if target_master_id not in configured_master_list:
                    configured_master_list.append(target_master_id)
            utils.set_configured_master_list(config_bot_hash, configured_master_list)
            utils.reply_message(
                plugin_event,
                f'已更新本插件配置骰主列表：{", ".join(configured_master_list) or "无"}',
            )
            return

        if master_action == 'del':
            configured_master_list = [
                configured_master_id
                for configured_master_id in configured_master_list
                if configured_master_id not in target_master_id_list
            ]
            utils.set_configured_master_list(config_bot_hash, configured_master_list)
            utils.reply_message(
                plugin_event,
                f'已更新本插件配置骰主列表：{", ".join(configured_master_list) or "无"}',
            )
            return

    utils.reply_message(
        plugin_event,
        '用法：.tplbot status/on/off 或 .tplbot master list/add/del [用户ID]',
    )


def handle_tplwhoami(plugin_event) -> None:
    """权限展示示例，方便模板使用者快速验证权限判断是否正确。"""
    permission_info = utils.get_master_permission_info(plugin_event)
    message_text = (
        f'发送者：{utils.get_sender_name_from_event(plugin_event)}({utils.get_sender_id_from_event(plugin_event)})\n'
        f'OlivaDiceCore 骰主：{"是" if permission_info["sender_is_core_master"] else "否"}\n'
        f'本插件配置骰主：{"是" if permission_info["sender_is_configured_master"] else "否"}\n'
        f'群主：{"是" if utils.is_group_owner(plugin_event) else "否"}\n'
        f'群管：{"是" if utils.is_group_admin(plugin_event) else "否"}\n'
        f'function.py 说明：{function.function_module_note}'
    )
    utils.reply_message(plugin_event, message_text)


@utils.log_exception('handle_message')
def handle_message(plugin_event, Proc) -> None:
    """
    统一消息处理入口。

    这里是整个模板最核心的流程调度点：
    - 先初始化目录
    - 再做 at / 前缀 / 命令解析
    - 然后判断权限与开关
    - 最后把命令分派到具体处理函数
    """
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
    )

    if not command_info['is_command']:
        return

    command_name = command_info['command_name']
    command_argument = command_info['command_argument']
    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)

    if not is_management_command(command_name):
        if not global_config.get('global_enable_switch', True):
            utils.debug_log(Proc, '全局启用开关已关闭，普通命令不再处理。', plugin_event=plugin_event)
            return
        if not bot_config.get('bot_enable_switch', True):
            utils.debug_log(Proc, '当前 Bot 开关已关闭，普通命令不再处理。', plugin_event=plugin_event)
            return

    if command_name == 'tplhelp':
        handle_tplhelp(plugin_event)
        return

    if command_name == 'tplping':
        handle_tplping(plugin_event)
        return

    if command_name == 'tplecho':
        handle_tplecho(plugin_event, command_argument)
        return

    if command_name == 'tplglobal':
        handle_tplglobal(plugin_event, command_argument)
        return

    if command_name == 'tplbot':
        handle_tplbot(plugin_event, command_argument)
        return

    if command_name == 'tplwhoami':
        handle_tplwhoami(plugin_event)
        return

    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_help_hint'))
