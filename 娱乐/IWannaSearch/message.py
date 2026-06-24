# -*- encoding: utf-8 -*-
"""IWannaSearch 消息解析与回复。"""

import datetime
import math
import os
import re
import time
from typing import Any, Dict, List

from . import config
from . import function
from . import message_custom
from . import utils


management_command_name_set = {'iwglobal', 'iwbot'}
selection_session_dict: Dict[str, Dict[str, Any]] = {}
number_pattern = re.compile(r'^\d+$')
random_tag_pattern = re.compile(r'--tag=(.*)')


def handle_init(plugin_event, Proc) -> None:
    utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    utils.info_log(Proc, 'IWannaSearch init 完成。')


def handle_init_after(plugin_event, Proc) -> None:
    utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    utils.debug_log(Proc, 'IWannaSearch init_after 已执行。', plugin_event=plugin_event)


def handle_private_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_group_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_heartbeat(plugin_event, Proc) -> None:
    clear_expired_selection_sessions()


def handle_save(plugin_event, Proc) -> None:
    clear_expired_selection_sessions(force=True)


def is_management_command(command_name: str) -> bool:
    return command_name in management_command_name_set


def build_runtime_value_dict(plugin_event, command_argument: str = '', extra_value_dict=None):
    config_bot_hash = utils.get_bot_hash_from_event(plugin_event)
    reply_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)
    configured_master_list = utils.get_configured_master_list(config_bot_hash)
    variable_dict = utils.load_bot_message_variables(reply_bot_hash)

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
    reply_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    custom_message_dict = utils.load_bot_message_custom(reply_bot_hash)
    template_text = custom_message_dict.get(message_key, '')
    value_dict = build_runtime_value_dict(plugin_event, command_argument, extra_value_dict)
    return utils.render_text_template(template_text, value_dict)


def sender_has_master_permission(plugin_event) -> bool:
    return utils.get_master_permission_info(plugin_event)['sender_is_master']


def reply_permission_denied(plugin_event) -> None:
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_permission_denied'))


def parse_secondary_action(command_argument: str):
    return utils.split_first_token(command_argument)


def handle_iw_help(plugin_event) -> None:
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_help'))


def handle_iwglobal(plugin_event, command_argument: str) -> None:
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
            utils.reply_message(plugin_event, '用法：.iwglobal debug on 或 .iwglobal debug off')
            return
    else:
        utils.reply_message(plugin_event, '用法：.iwglobal status/on/off/debug on/debug off')
        return

    utils.save_global_config(global_config)
    utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_global_status'))


def handle_iwbot(plugin_event, command_argument: str) -> None:
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
    if action_name == 'master':
        master_action, master_argument = parse_secondary_action(action_argument)
        configured_master_list = utils.get_configured_master_list(config_bot_hash)
        target_master_id_list = utils.normalize_id_list(master_argument)
        if master_action in ['', 'list']:
            utils.reply_message(plugin_event, f'当前本插件配置骰主列表：{", ".join(configured_master_list) or "无"}')
            return
        if master_action == 'add':
            for target_master_id in target_master_id_list:
                if target_master_id not in configured_master_list:
                    configured_master_list.append(target_master_id)
            utils.set_configured_master_list(config_bot_hash, configured_master_list)
            utils.reply_message(plugin_event, f'已更新本插件配置骰主列表：{", ".join(configured_master_list) or "无"}')
            return
        if master_action == 'del':
            configured_master_list = [item for item in configured_master_list if item not in target_master_id_list]
            utils.set_configured_master_list(config_bot_hash, configured_master_list)
            utils.reply_message(plugin_event, f'已更新本插件配置骰主列表：{", ".join(configured_master_list) or "无"}')
            return
    utils.reply_message(plugin_event, '用法：.iwbot status/on/off 或 .iwbot master list/add/del [用户ID]')


def get_int_config(global_config: Dict[str, Any], key: str, default_value: int, min_value: int, max_value: int) -> int:
    try:
        value = int(global_config.get(key, default_value))
    except Exception:
        value = default_value
    return max(min_value, min(max_value, value))


def get_api_runtime_config() -> Dict[str, Any]:
    global_config = utils.load_global_config()
    return {
        'base_url': function.normalize_base_url(global_config.get('api_base_url', config.api_default_base_url)),
        'timeout_seconds': get_int_config(global_config, 'api_timeout_seconds', config.api_timeout_seconds, 3, 60),
        'page_size': get_int_config(global_config, 'result_page_size', config.result_page_size, 1, 10),
        'selection_timeout': get_int_config(
            global_config,
            'selection_timeout_seconds',
            config.selection_timeout_seconds,
            30,
            3600,
        ),
    }


def build_selection_key(plugin_event) -> str:
    bot_hash = utils.get_bot_hash_from_event(plugin_event)
    user_id = utils.get_sender_id_from_event(plugin_event)
    host_id = utils.get_host_id_from_event(plugin_event)
    group_id = utils.get_group_id_from_event(plugin_event)
    if group_id:
        return f'{bot_hash}|group|{host_id}|{group_id}|{user_id}'
    return f'{bot_hash}|private|{user_id}'


def get_user_hash_from_event(plugin_event) -> str:
    platform_name = utils.safe_str(getattr(plugin_event, 'platform', {}).get('platform', 'unknown'))
    user_id = utils.get_sender_id_from_event(plugin_event) or 'unknown'
    return utils.get_user_hash(user_id, 'user', platform_name)


def sanitize_path_name(source_text: str) -> str:
    sanitized_text = re.sub(r'[^0-9A-Za-z_.-]+', '_', utils.safe_str(source_text).strip())
    return sanitized_text or 'unknown'


def get_today_cache_file_path(plugin_event) -> str:
    user_hash = get_user_hash_from_event(plugin_event)
    storage_dir = utils.get_storage_dir(utils.get_bot_hash_from_event(plugin_event, use_linked=True))
    user_dir = utils.ensure_folder(os.path.join(storage_dir, 'user', sanitize_path_name(user_hash)))
    return os.path.join(user_dir, 'today.json')


def clear_expired_selection_sessions(force: bool = False) -> None:
    now_time = time.time()
    expired_key_list = []
    for session_key, session_data in selection_session_dict.items():
        timeout_seconds = session_data.get('selection_timeout', config.selection_timeout_seconds)
        if force or now_time - session_data.get('updated_at', now_time) > timeout_seconds:
            expired_key_list.append(session_key)
    for session_key in expired_key_list:
        selection_session_dict.pop(session_key, None)


def get_valid_selection_session(plugin_event) -> Dict[str, Any]:
    clear_expired_selection_sessions()
    session_key = build_selection_key(plugin_event)
    return selection_session_dict.get(session_key, {})


def save_selection_session(plugin_event, results: List[Dict[str, Any]], count: int, page_size: int, selection_timeout: int) -> None:
    selection_session_dict[build_selection_key(plugin_event)] = {
        'results': results,
        'count': count,
        'page_index': 0,
        'page_size': page_size,
        'selection_timeout': selection_timeout,
        'updated_at': time.time(),
    }


def pop_selection_session(plugin_event) -> None:
    selection_session_dict.pop(build_selection_key(plugin_event), None)


def render_game_metadata(plugin_event, game_item: Dict[str, Any]) -> str:
    return render_custom_message(
        plugin_event,
        'reply_game_metadata',
        extra_value_dict=function.build_game_template_value(game_item),
    )


def render_game_detail_with_prefix(plugin_event, game_item: Dict[str, Any], prefix_key: str) -> str:
    prefix_text = render_custom_message(plugin_event, prefix_key).strip()
    metadata_text = render_game_metadata(plugin_event, game_item)
    if prefix_text:
        return f'{prefix_text}\n{metadata_text}'
    return metadata_text


def render_search_game_detail(plugin_event, game_item: Dict[str, Any]) -> str:
    return render_game_detail_with_prefix(plugin_event, game_item, 'reply_search_result_prefix')


def render_random_game_detail(plugin_event, game_item: Dict[str, Any]) -> str:
    return render_game_detail_with_prefix(plugin_event, game_item, 'reply_random_result_prefix')


def create_forward_node(plugin_event, content: str) -> Dict[str, Any]:
    bot_id = utils.safe_str(getattr(getattr(plugin_event, 'bot_info', None), 'id', '')).strip() or '0'
    bot_name = utils.get_bot_display_name(plugin_event) or config.plugin_name
    return {
        'type': 'node',
        'data': {
            'user_id': bot_id,
            'nickname': bot_name,
            'content': content,
        },
    }


def send_forward_detail_messages(plugin_event, detail_text_list: List[str]) -> bool:
    if utils.safe_str(getattr(plugin_event, 'platform', {}).get('platform', '')).lower() != 'qq':
        return False

    forward_messages = [create_forward_node(plugin_event, detail_text) for detail_text in detail_text_list if detail_text]
    if not forward_messages:
        return False

    group_id = utils.get_group_id_from_event(plugin_event)
    try:
        if group_id and hasattr(plugin_event, 'send_group_forward_msg'):
            plugin_event.send_group_forward_msg(group_id, forward_messages)
            return True
        if hasattr(plugin_event, 'send_private_forward_msg'):
            plugin_event.send_private_forward_msg(utils.get_sender_id_from_event(plugin_event), forward_messages)
            return True
    except Exception:
        return False
    return False


def send_detail_messages(plugin_event, detail_text_list: List[str]) -> None:
    normalized_text_list = [utils.safe_str(detail_text).strip() for detail_text in detail_text_list if detail_text]
    if not normalized_text_list:
        return
    if len(normalized_text_list) > 1 and send_forward_detail_messages(plugin_event, normalized_text_list):
        return
    for index, detail_text in enumerate(normalized_text_list):
        if index > 0:
            time.sleep(1)
        utils.reply_message(plugin_event, detail_text)


def render_result_list(plugin_event, session_data: Dict[str, Any]) -> str:
    results = session_data.get('results', [])
    count = int(session_data.get('count', len(results)))
    available_count = len(results)
    page_size = int(session_data.get('page_size', config.result_page_size))
    page_index = int(session_data.get('page_index', 0))
    total_page = max(1, math.ceil(available_count / max(page_size, 1)))
    page_index = max(0, min(page_index, total_page - 1))
    start_index = page_index * page_size
    page_items = function.get_page_items(results, page_index, page_size)

    line_list = [render_custom_message(plugin_event, 'reply_multiple_header', extra_value_dict={'count': count})]
    for offset, game_item in enumerate(page_items):
        display_index = start_index + offset + 1
        line_list.append(
            render_custom_message(
                plugin_event,
                'reply_multiple_item',
                extra_value_dict=function.build_game_template_value(game_item, display_index),
            )
        )

    if len(results) > page_size:
        line_list.append(
            render_custom_message(
                plugin_event,
                'reply_page_info',
                extra_value_dict={'current_page': page_index + 1, 'total_page': total_page},
            )
        )
        if count > available_count:
            line_list.append(
                render_custom_message(
                    plugin_event,
                    'reply_result_limited_note',
                    extra_value_dict={
                        'count': count,
                        'available_count': available_count,
                        'total_page': total_page,
                    },
                )
            )
        line_list.append(render_custom_message(plugin_event, 'reply_paged_footer'))
    else:
        line_list.append(render_custom_message(plugin_event, 'reply_multiple_footer'))
    return '\n'.join(line_list)


def reply_search_payload(plugin_event, payload: Dict[str, Any]) -> None:
    if not payload.get('ok', False):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_api_error', extra_value_dict=payload))
        return

    results = payload.get('results', [])
    count = int(payload.get('count', len(results)))
    if not results or count <= 0:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_not_found'))
        return

    if count == 1 or len(results) == 1:
        pop_selection_session(plugin_event)
        utils.reply_message(plugin_event, render_search_game_detail(plugin_event, results[0]))
        return

    runtime_config = get_api_runtime_config()
    save_selection_session(
        plugin_event,
        results,
        count,
        runtime_config['page_size'],
        runtime_config['selection_timeout'],
    )
    session_data = get_valid_selection_session(plugin_event)
    utils.reply_message(plugin_event, render_result_list(plugin_event, session_data))


def handle_iw_id(plugin_event, query_text: str) -> None:
    game_id = utils.safe_str(query_text).strip()
    if not game_id:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_empty_query'))
        return
    runtime_config = get_api_runtime_config()
    payload = function.search_by_id(game_id, runtime_config['base_url'], runtime_config['timeout_seconds'])
    reply_search_payload(plugin_event, payload)


def handle_iw_search(plugin_event, query_text: str) -> None:
    game_name = utils.safe_str(query_text).strip()
    if not game_name:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_empty_query'))
        return
    runtime_config = get_api_runtime_config()
    payload = function.search_by_name(game_name, runtime_config['base_url'], runtime_config['timeout_seconds'])
    reply_search_payload(plugin_event, payload)


def parse_random_argument(argument_text: str) -> Dict[str, Any]:
    source_text = utils.safe_str(argument_text).strip()
    tag_text = ''
    tag_match = random_tag_pattern.search(source_text)
    if tag_match:
        tag_text = utils.safe_str(tag_match.group(1)).strip()
        source_text = f'{source_text[:tag_match.start()]} {source_text[tag_match.end():]}'.strip()

    count_text = source_text.strip()
    if not count_text:
        return {'ok': True, 'count': 1, 'tag': tag_text, 'error_key': ''}
    if not number_pattern.match(count_text):
        return {'ok': False, 'count': 1, 'tag': tag_text, 'error_key': 'reply_random_count_invalid'}

    count = int(count_text)
    if count < 1:
        return {'ok': False, 'count': 1, 'tag': tag_text, 'error_key': 'reply_random_count_invalid'}
    if count > 10:
        return {'ok': False, 'count': 10, 'tag': tag_text, 'error_key': 'reply_random_count_too_large'}
    return {'ok': True, 'count': count, 'tag': tag_text, 'error_key': ''}


def reply_random_payload(plugin_event, payload: Dict[str, Any], requested_count: int) -> None:
    if not payload.get('ok', False):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_api_error', extra_value_dict=payload))
        return

    results = payload.get('results', [])
    if not results:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_not_found'))
        return

    if requested_count <= 1 or len(results) == 1:
        utils.reply_message(plugin_event, render_random_game_detail(plugin_event, results[0]))
        return

    prefix_text = render_custom_message(plugin_event, 'reply_random_result_prefix').strip()
    if prefix_text:
        utils.reply_message(plugin_event, prefix_text)
    send_detail_messages(plugin_event, [render_game_metadata(plugin_event, game_item) for game_item in results])


def handle_iw_random(plugin_event, argument_text: str) -> None:
    random_argument = parse_random_argument(argument_text)
    if not random_argument.get('ok', False):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, random_argument.get('error_key', 'reply_random_count_invalid')))
        return

    runtime_config = get_api_runtime_config()
    payload = function.random_games(
        random_argument['count'],
        random_argument['tag'],
        runtime_config['base_url'],
        runtime_config['timeout_seconds'],
    )
    reply_random_payload(plugin_event, payload, random_argument['count'])


def load_today_cache(plugin_event) -> Dict[str, Any]:
    with utils.file_lock:
        return utils.read_json_file(get_today_cache_file_path(plugin_event), {})


def save_today_cache(plugin_event, game_item: Dict[str, Any], today_text: str) -> None:
    cache_data = {
        'date': today_text,
        'user_hash': get_user_hash_from_event(plugin_event),
        'iw': game_item,
    }
    with utils.file_lock:
        utils.save_json_file(get_today_cache_file_path(plugin_event), cache_data)


def reply_today_game(plugin_event, game_item: Dict[str, Any]) -> None:
    title_text = render_custom_message(plugin_event, 'reply_today_title').strip()
    detail_text = render_game_metadata(plugin_event, game_item)
    if title_text:
        detail_text = f'{title_text}\n{detail_text}'
    utils.reply_message(plugin_event, detail_text)


def handle_iw_today(plugin_event) -> None:
    today_text = datetime.date.today().isoformat()
    cache_data = load_today_cache(plugin_event)
    if not isinstance(cache_data, dict):
        cache_data = {}
    cached_game = cache_data.get('iw') if isinstance(cache_data, dict) else None
    if cache_data.get('date') == today_text and isinstance(cached_game, dict):
        reply_today_game(plugin_event, cached_game)
        return

    runtime_config = get_api_runtime_config()
    payload = function.random_games(1, '', runtime_config['base_url'], runtime_config['timeout_seconds'])
    if not payload.get('ok', False):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_api_error', extra_value_dict=payload))
        return

    results = payload.get('results', [])
    if not results:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_not_found'))
        return

    today_game = results[0]
    save_today_cache(plugin_event, today_game, today_text)
    reply_today_game(plugin_event, today_game)


def get_current_page_range(session_data: Dict[str, Any]) -> range:
    results = session_data.get('results', [])
    page_size = int(session_data.get('page_size', config.result_page_size))
    page_index = int(session_data.get('page_index', 0))
    start_index = page_index * page_size
    end_index = min(start_index + page_size, len(results))
    return range(start_index + 1, end_index + 1)


def handle_jump_page_input(plugin_event, session_data: Dict[str, Any], page_text: str) -> bool:
    results = session_data.get('results', [])
    page_size = int(session_data.get('page_size', config.result_page_size))
    total_page = max(1, math.ceil(len(results) / max(page_size, 1)))
    stripped_page_text = utils.safe_str(page_text).strip()
    if not stripped_page_text:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_jump_page_empty'))
        return True
    if not number_pattern.match(stripped_page_text):
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_jump_page_invalid'))
        return True

    target_page = int(stripped_page_text)
    if target_page < 1 or target_page > total_page:
        utils.reply_message(
            plugin_event,
            render_custom_message(
                plugin_event,
                'reply_jump_page_out_of_range',
                extra_value_dict={'total_page': total_page},
            ),
        )
        return True

    session_data['page_index'] = target_page - 1
    session_data['updated_at'] = time.time()
    utils.reply_message(plugin_event, render_result_list(plugin_event, session_data))
    return True


def handle_selection_input(plugin_event, input_text: str) -> bool:
    session_data = get_valid_selection_session(plugin_event)
    if not session_data:
        return False

    stripped_text = utils.safe_str(input_text).strip()
    results = session_data.get('results', [])
    page_size = int(session_data.get('page_size', config.result_page_size))
    total_page = max(1, math.ceil(len(results) / max(page_size, 1)))

    jump_info = utils.parse_command(
        stripped_text,
        prefix_list=[],
        allow_no_prefix=True,
        command_name=['跳页', 'page'],
    )
    if jump_info['is_command']:
        return handle_jump_page_input(plugin_event, session_data, jump_info['command_argument'])

    page_match = re.match(r'^第(\d+)页$', stripped_text)
    if page_match:
        return handle_jump_page_input(plugin_event, session_data, page_match.group(1))

    if stripped_text.lower() in ['下一页', '上一页', 'down', 'up', 'next', 'prev']:
        if len(results) <= page_size:
            utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_input_invalid'))
            return True
        if stripped_text.lower() in ['下一页', 'down', 'next']:
            if session_data.get('page_index', 0) >= total_page - 1:
                utils.reply_message(
                    plugin_event,
                    f'{render_custom_message(plugin_event, "reply_last_page")}\n{render_result_list(plugin_event, session_data)}',
                )
                return True
            session_data['page_index'] = int(session_data.get('page_index', 0)) + 1
        else:
            if session_data.get('page_index', 0) <= 0:
                utils.reply_message(
                    plugin_event,
                    f'{render_custom_message(plugin_event, "reply_first_page")}\n{render_result_list(plugin_event, session_data)}',
                )
                return True
            session_data['page_index'] = int(session_data.get('page_index', 0)) - 1
        session_data['updated_at'] = time.time()
        utils.reply_message(plugin_event, render_result_list(plugin_event, session_data))
        return True

    if not number_pattern.match(stripped_text):
        message_key = 'reply_paged_input_invalid' if len(results) > page_size else 'reply_input_invalid'
        utils.reply_message(plugin_event, render_custom_message(plugin_event, message_key))
        return True

    selected_index = int(stripped_text)
    current_range = get_current_page_range(session_data)
    if selected_index not in current_range:
        utils.reply_message(plugin_event, render_custom_message(plugin_event, 'reply_index_out_of_range'))
        return True

    game_item = results[selected_index - 1]
    pop_selection_session(plugin_event)
    utils.reply_message(plugin_event, render_search_game_detail(plugin_event, game_item))
    return True


def parse_iw_command(plugin_event, remaining_text: str) -> None:
    command_info = utils.parse_command(
        remaining_text,
        prefix_list=[],
        allow_no_prefix=True,
        command_name='iw',
    )
    if not command_info['is_command']:
        return

    command_argument = command_info['command_argument'].strip()
    if command_argument == 'help':
        handle_iw_help(plugin_event)
        return

    today_info = utils.parse_command(
        command_argument,
        prefix_list=[],
        allow_no_prefix=True,
        command_name='today',
    )
    if today_info['is_command']:
        handle_iw_today(plugin_event)
        return

    random_info = utils.parse_command(
        command_argument,
        prefix_list=[],
        allow_no_prefix=True,
        command_name=['random', 'rand'],
    )
    if random_info['is_command']:
        handle_iw_random(plugin_event, random_info['command_argument'])
        return

    id_info = utils.parse_command(
        command_argument,
        prefix_list=[],
        allow_no_prefix=True,
        command_name='id',
    )
    if id_info['is_command']:
        handle_iw_id(plugin_event, id_info['command_argument'])
        return

    search_info = utils.parse_command(
        command_argument,
        prefix_list=[],
        allow_no_prefix=True,
        command_name='search',
    )
    if search_info['is_command']:
        handle_iw_search(plugin_event, search_info['command_argument'])
        return

    handle_iw_search(plugin_event, command_argument)


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

    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(config_bot_hash)
    matched_prefix, remaining_after_prefix = utils.parse_prefix(remaining_after_at, config.allowed_prefix_list)
    if not matched_prefix:
        if not global_config.get('global_enable_switch', True):
            return
        if not bot_config.get('bot_enable_switch', True):
            return
        if handle_selection_input(plugin_event, remaining_after_at):
            return
        return

    management_info = utils.parse_command(
        remaining_after_prefix,
        prefix_list=[],
        allow_no_prefix=True,
        command_name=['iwglobal', 'iwbot'],
    )
    if management_info['is_command']:
        if management_info['command_name'] == 'iwglobal':
            handle_iwglobal(plugin_event, management_info['command_argument'])
            return
        if management_info['command_name'] == 'iwbot':
            handle_iwbot(plugin_event, management_info['command_argument'])
            return

    if not global_config.get('global_enable_switch', True):
        utils.debug_log(Proc, '全局启用开关已关闭，普通命令不再处理。', plugin_event=plugin_event)
        return
    if not bot_config.get('bot_enable_switch', True):
        utils.debug_log(Proc, '当前 Bot 开关已关闭，普通命令不再处理。', plugin_event=plugin_event)
        return

    iw_info = utils.parse_command(
        remaining_after_prefix,
        prefix_list=[],
        allow_no_prefix=True,
        command_name='iw',
    )
    if iw_info['is_command']:
        parse_iw_command(plugin_event, remaining_after_prefix)
        return
