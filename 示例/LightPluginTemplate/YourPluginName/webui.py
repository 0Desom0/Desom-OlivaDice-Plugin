# -*- encoding: utf-8 -*-
"""WebUI 配置接口：复用 GUI 的存储方法，认证与会话回包交给 OlivOS。"""

import os
import re

from . import config, message_custom, utils


def get_bot_info_dict(Proc) -> dict:
    """只从宿主拿账号列表，网页不能指定磁盘目录或 linked hash。"""
    proc_data = getattr(Proc, 'Proc_data', {})
    bot_info_dict = proc_data.get('bot_info_dict', {}) if isinstance(proc_data, dict) else {}
    return bot_info_dict if isinstance(bot_info_dict, dict) else {}


def bot_label(bot_hash: str, bot_info_dict: dict) -> str:
    """只展示名称、平台和账号 ID，不序列化 bot_info 中的认证配置。"""
    bot_info = bot_info_dict.get(bot_hash)
    if bot_info is None:
        return bot_hash
    platform = getattr(bot_info, 'platform', {})
    platform_name = utils.safe_str(platform.get('platform', '未知平台')) if isinstance(platform, dict) else '未知平台'
    parts = (platform_name, getattr(bot_info, 'name', ''), getattr(bot_info, 'id', ''))
    return ' | '.join(utils.safe_str(part) for part in parts if part)


def get_state(Proc, requested_bot_hash: str = '') -> dict:
    """按字段返回配置；开关与骰主用原始账号，回复词通过 utils 解析群链。"""
    bot_info_dict = get_bot_info_dict(Proc)
    bots = [{'hash': key, 'label': bot_label(key, bot_info_dict)} for key in bot_info_dict if isinstance(key, str)]
    bots.sort(key=lambda item: (item['label'], item['hash']))
    global_config = utils.load_global_config()
    state = {
        'plugin_name': config.plugin_name,
        'global_config': {key: bool(global_config[key]) for key in config.default_global_config},
        'global_directory': os.path.abspath(config.plugin_data_dir),
        'bots': bots,
        'bot': None,
    }
    if not bots:
        return state
    # 刷新时账号可能已被宿主移除，回到列表里的第一个账号；写操作仍严格校验账号。
    bot_hash = requested_bot_hash if requested_bot_hash in bot_info_dict else bots[0]['hash']
    linked_hash = utils.get_linked_bot_hash(bot_hash)
    bot_config = utils.load_bot_config(bot_hash)
    replies = utils.load_bot_message_custom(bot_hash)
    state['bot'] = {
        'hash': bot_hash,
        'label': bot_label(bot_hash, bot_info_dict),
        'linked_hash': linked_hash,
        'linked_label': bot_label(linked_hash, bot_info_dict),
        'bot_enable_switch': bool(bot_config['bot_enable_switch']),
        'masters': bot_config['configured_master_list'],
        'config_directory': os.path.abspath(utils.get_config_bot_root_dir(bot_hash)),
        'reply_directory': os.path.abspath(utils.get_reply_bot_root_dir(bot_hash)),
        'replies': [
            {
                'key': key,
                'note': utils.get_message_note_text(key),
                'value': utils.safe_str(replies.get(key, '')),
                'is_default': key in message_custom.default_custom_message_dict,
            }
            for key in utils.get_bot_message_key_list(bot_hash)
        ],
    }
    return state


def require_bool(payload: dict, key: str) -> bool:
    """不把字符串 'false' 或数字误当成布尔开关。"""
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError('开关必须为 true 或 false。')
    return value


def require_master_ids(payload: dict) -> list[str]:
    """完整校验后再保存，拒绝把混有字母的输入静默变成另一个用户 ID。"""
    values = payload.get('ids')
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ValueError('请提供 1 至 100 个数字用户 ID。')
    if any(not isinstance(value, str) or re.fullmatch(r'[0-9]{1,32}', value) is None for value in values):
        raise ValueError('用户 ID 必须是 1 至 32 位数字字符串。')
    return list(dict.fromkeys(values))


def save_bot_action(action: str, payload: dict, bot_hash: str) -> bool:
    """只写本次操作的字段，保留群禁用列表与使用者自行扩展的配置。"""
    if action == 'save_bot':
        enabled = require_bool(payload, 'bot_enable_switch')
        bot_config = utils.load_bot_config(bot_hash)
        bot_config['bot_enable_switch'] = enabled
        return utils.save_bot_config(bot_hash, bot_config)

    if action in ('add_masters', 'remove_masters'):
        ids = require_master_ids(payload)
        masters = utils.get_configured_master_list(bot_hash)
        if action == 'add_masters':
            masters = list(dict.fromkeys(masters + ids))
        else:
            masters = [master_id for master_id in masters if master_id not in ids]
        return utils.set_configured_master_list(bot_hash, masters)

    if action == 'reset_replies':
        if payload.get('confirm') is not True:
            raise ValueError('请确认恢复全部默认回复。')
        return utils.save_bot_message_custom(bot_hash, message_custom.default_custom_message_dict)

    if action in ('save_reply', 'reset_reply'):
        key = payload.get('key')
        if not isinstance(key, str) or key not in utils.get_bot_message_key_list(bot_hash):
            raise ValueError('回复词条目不存在，请刷新后重新选择。')
        if action == 'save_reply':
            value = payload.get('value')
            if not isinstance(value, str) or len(value) > 32768:
                raise ValueError('回复词必须是文本，且不超过 32768 字。')
            return utils.set_bot_message_custom_value(bot_hash, key, value)
        if payload.get('confirm') is not True:
            raise ValueError('请确认恢复或删除这条回复词。')
        if key in message_custom.default_custom_message_dict:
            return utils.reset_bot_message_custom_value(bot_hash, key)
        replies = utils.load_bot_message_custom(bot_hash)
        replies.pop(key, None)
        return utils.save_bot_message_custom(bot_hash, replies)

    raise ValueError('未知的 WebUI 操作。')


def dispatch(payload: dict, Proc) -> dict:
    """所有读写共用文件锁，避免同一时刻的网页请求互相覆盖其他字段。"""
    action = payload.get('action')
    bot_hash = payload.get('bot_hash', '')
    if not isinstance(bot_hash, str):
        raise ValueError('Bot 标识必须为字符串。')
    with utils.file_lock:
        if action == 'get_state':
            return {'ok': True, 'state': get_state(Proc, bot_hash)}
        if action == 'save_global':
            changes = {key: require_bool(payload, key) for key in config.default_global_config}
            global_config = utils.load_global_config()
            global_config.update(changes)
            saved = utils.save_global_config(global_config)
        else:
            if not bot_hash or bot_hash not in get_bot_info_dict(Proc):
                raise ValueError('所选 Bot 已不可用，请刷新账号列表。')
            saved = save_bot_action(action, payload, bot_hash)
        if not saved:
            raise OSError('Configuration save failed')
        return {'ok': True, 'state': get_state(Proc, bot_hash)}


def handle_menu_event(plugin_event, Proc) -> None:
    """在原始网页事件上回包；不依赖 bot_info，不使用机器人 reply()。"""
    data = getattr(plugin_event, 'data', None)
    if getattr(data, 'namespace', None) != config.plugin_name:
        return
    context = getattr(data, 'webui', None)
    if not isinstance(context, dict):
        return
    request_id = context.get('request_id')
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        return
    try:
        if getattr(data, 'event', None) != config.webui_event:
            raise ValueError('未知的 WebUI 事件。')
        payload = getattr(data, 'payload', None)
        if not isinstance(payload, dict):
            raise ValueError('请求数据必须为对象。')
        response = dispatch(payload, Proc)
    except ValueError as error:
        response = {'ok': False, 'error': str(error)}
    except Exception as error:
        # 不把事件、payload、认证上下文或异常中的路径写入日志与回包。
        utils.error_log(Proc, f'WebUI 配置操作失败：{type(error).__name__}')
        response = {'ok': False, 'error': '配置读写失败，请检查服务器数据目录权限，再刷新确认当前状态。'}
    try:
        if plugin_event.send('webui', request_id, response) is False:
            utils.error_log(Proc, 'WebUI 回包未能入队。')
    except Exception as error:
        utils.error_log(Proc, f'WebUI 回包失败：{type(error).__name__}')
