# -*- encoding: utf-8 -*-
"""赛博角斗场业务逻辑。"""

import json
import os
import random
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import config
from . import utils


function_module_note = '赛博角斗场纯 Python 业务逻辑模块。'

MAX_PARTICIPANTS = 4
HP_RANGE = (800, 1200)
MP_RANGE = (200, 400)
ROLL_COUNT = 10
SEGMENT_SEPARATOR = '|||'
SEGMENT_DELAY_RANGE = (
    config.default_segment_delay_min_seconds,
    config.default_segment_delay_max_seconds,
)

battle_state_lock = threading.RLock()
cancelled_battle_id_set = set()


def _now_text() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _safe_filename(text: Any) -> str:
    safe_name = re.sub(r'[^0-9A-Za-z_-]+', '_', utils.safe_str(text).strip())
    return safe_name or 'default'


def _coerce_int(value: Any, default_value: int) -> int:
    try:
        return int(value)
    except Exception:
        return default_value


def _coerce_float(value: Any, default_value: float) -> float:
    try:
        return float(value)
    except Exception:
        return default_value


def _coerce_bool(value: Any, default_value: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized_text = utils.safe_str(value).strip().lower()
    if normalized_text in ('1', 'true', 'yes', 'on'):
        return True
    if normalized_text in ('0', 'false', 'no', 'off'):
        return False
    return default_value


def normalize_segment_delay_range(min_seconds: Any, max_seconds: Any) -> tuple[int, int]:
    delay_min_seconds = max(_coerce_int(min_seconds, SEGMENT_DELAY_RANGE[0]), 1)
    delay_max_seconds = max(_coerce_int(max_seconds, SEGMENT_DELAY_RANGE[1]), delay_min_seconds)
    return delay_min_seconds, delay_max_seconds


def get_segment_delay_range_from_bot_config(bot_config: Dict[str, Any]) -> tuple[int, int]:
    if not isinstance(bot_config, dict):
        return SEGMENT_DELAY_RANGE
    return normalize_segment_delay_range(
        bot_config.get('segment_delay_min_seconds', SEGMENT_DELAY_RANGE[0]),
        bot_config.get('segment_delay_max_seconds', SEGMENT_DELAY_RANGE[1]),
    )


def _build_battle_key(plugin_event) -> str:
    bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    hag_id = utils.get_hag_id_from_event(plugin_event)
    return f'{bot_hash}::{hag_id}'


def _build_battle_id() -> str:
    return datetime.now().strftime('%Y%m%d%H%M%S%f')


def _mark_battle_cancelled(battle_id: str) -> None:
    if battle_id:
        cancelled_battle_id_set.add(utils.safe_str(battle_id))


def _clear_battle_cancelled(battle_id: str) -> None:
    if battle_id:
        cancelled_battle_id_set.discard(utils.safe_str(battle_id))


def _storage_root(bot_hash: str) -> str:
    return utils.get_storage_dir(bot_hash)


def _group_state_dir(bot_hash: str) -> str:
    return utils.ensure_folder(os.path.join(_storage_root(bot_hash), 'groups'))


def _archive_dir(bot_hash: str) -> str:
    month_folder = datetime.now().strftime('%Y%m')
    archive_root = os.path.join(_storage_root(bot_hash), 'archives', month_folder)
    return utils.ensure_folder(archive_root)


def _group_state_file_path(bot_hash: str, hag_id: str) -> str:
    return os.path.join(_group_state_dir(bot_hash), f'{_safe_filename(hag_id)}.json')


def _build_default_group_state(plugin_event) -> Dict[str, Any]:
    return {
        'hag_id': utils.get_hag_id_from_event(plugin_event),
        'group_id': utils.get_group_id_from_event(plugin_event),
        'host_id': utils.get_host_id_from_event(plugin_event),
        'plugin_enabled': True,
        'waiting_room': [],
        'battle_running': False,
        'stop_requested': False,
        'active_battle_id': '',
        'battle_started_at': '',
        'battle_count': 0,
        'last_archive_file': '',
        'updated_at': _now_text(),
    }


def _sanitize_waiting_room(waiting_room: Any) -> List[Dict[str, str]]:
    sanitized_list = []
    if not isinstance(waiting_room, list):
        return sanitized_list

    for entry in waiting_room:
        if not isinstance(entry, dict):
            continue
        sanitized_list.append(
            {
                'user_id': utils.safe_str(entry.get('user_id', '')).strip(),
                'user_name': utils.safe_str(entry.get('user_name', '')).strip(),
                'group_display_name': utils.safe_str(entry.get('group_display_name', '')).strip(),
                'input_text': utils.safe_str(entry.get('input_text', '')).strip(),
                'joined_at': utils.safe_str(entry.get('joined_at', '')).strip(),
                'updated_at': utils.safe_str(entry.get('updated_at', '')).strip(),
            }
        )
    return sanitized_list


def load_group_state(plugin_event) -> Dict[str, Any]:
    bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    hag_id = utils.get_hag_id_from_event(plugin_event)
    default_state = _build_default_group_state(plugin_event)
    file_path = _group_state_file_path(bot_hash, hag_id)
    file_data = utils.read_json_file(file_path, default_state)
    merged_state = utils.merge_dict_with_default(file_data, default_state)
    merged_state['waiting_room'] = _sanitize_waiting_room(merged_state.get('waiting_room', []))
    return merged_state


def save_group_state(plugin_event, group_state: Dict[str, Any]) -> bool:
    bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    hag_id = utils.get_hag_id_from_event(plugin_event)
    default_state = _build_default_group_state(plugin_event)
    final_state = utils.merge_dict_with_default(group_state, default_state)
    final_state['waiting_room'] = _sanitize_waiting_room(final_state.get('waiting_room', []))
    final_state['updated_at'] = _now_text()
    return utils.save_json_file(_group_state_file_path(bot_hash, hag_id), final_state)


def is_group_plugin_enabled(plugin_event) -> bool:
    group_state = load_group_state(plugin_event)
    return bool(group_state.get('plugin_enabled', True))


def set_group_plugin_enabled(plugin_event, enabled: bool) -> Dict[str, Any]:
    group_state = load_group_state(plugin_event)
    group_state['plugin_enabled'] = bool(enabled)
    save_group_state(plugin_event, group_state)
    return group_state


def is_global_plugin_enabled() -> bool:
    global_config = utils.load_global_config()
    return bool(global_config.get('global_enable_switch', True))


def set_global_plugin_enabled(enabled: bool) -> Dict[str, Any]:
    global_config = utils.load_global_config()
    global_config['global_enable_switch'] = bool(enabled)
    utils.save_global_config(global_config)
    return global_config


def is_group_battle_running(plugin_event) -> bool:
    group_state = load_group_state(plugin_event)
    return bool(group_state.get('battle_running', False))


def is_battle_stop_requested(plugin_event, battle_id: Optional[str] = None) -> bool:
    if battle_id and utils.safe_str(battle_id) in cancelled_battle_id_set:
        return True

    group_state = load_group_state(plugin_event)
    if not group_state.get('battle_running', False):
        return False
    if battle_id and utils.safe_str(group_state.get('active_battle_id', '')) != utils.safe_str(battle_id):
        return False
    return bool(group_state.get('stop_requested', False))


def prepare_battle_run(plugin_event) -> Dict[str, Any]:
    with battle_state_lock:
        group_state = load_group_state(plugin_event)
        waiting_room = group_state.get('waiting_room', [])
        if group_state.get('battle_running', False):
            return {
                'ok': False,
                'reason': 'battle_running',
                'waiting_count': len(waiting_room),
            }
        if len(waiting_room) < 2:
            return {
                'ok': False,
                'reason': 'not_enough_players',
                'waiting_count': len(waiting_room),
            }

        bot_config = get_runtime_bot_config(plugin_event)
        if not api_config_dict_is_ready(bot_config):
            return {
                'ok': False,
                'reason': 'missing_api_config',
            }

        battle_id = _build_battle_id()
        group_state['battle_running'] = True
        group_state['stop_requested'] = False
        group_state['active_battle_id'] = battle_id
        group_state['battle_started_at'] = _now_text()
        save_group_state(plugin_event, group_state)
        return {
            'ok': True,
            'battle_id': battle_id,
            'waiting_room': list(waiting_room),
            'waiting_count': len(waiting_room),
            'bot_config': bot_config,
        }


def request_stop_battle(plugin_event) -> Dict[str, Any]:
    with battle_state_lock:
        group_state = load_group_state(plugin_event)
        waiting_room = group_state.get('waiting_room', [])
        if not group_state.get('battle_running', False):
            return {
                'ok': False,
                'reason': 'battle_not_running',
                'waiting_count': len(waiting_room),
            }

        battle_id = utils.safe_str(group_state.get('active_battle_id', '')).strip()
        _mark_battle_cancelled(battle_id)
        group_state['stop_requested'] = False
        group_state['battle_running'] = False
        group_state['active_battle_id'] = ''
        group_state['battle_started_at'] = ''
        group_state['waiting_room'] = []
        save_group_state(plugin_event, group_state)
        return {
            'ok': True,
            'reason': 'stop_requested',
            'battle_id': battle_id,
            'waiting_count': len(waiting_room),
        }


def get_waiting_room_snapshot(plugin_event) -> Dict[str, Any]:
    group_state = load_group_state(plugin_event)
    waiting_room = group_state.get('waiting_room', [])
    return {
        'group_state': group_state,
        'waiting_room': waiting_room,
        'waiting_count': len(waiting_room),
    }


def _iter_group_members(group_member_list: Any) -> List[Dict[str, Any]]:
    if not isinstance(group_member_list, dict):
        return []
    if group_member_list.get('active') is False:
        return []
    members = group_member_list.get('data', [])
    if not isinstance(members, list):
        return []
    return [member for member in members if isinstance(member, dict)]


def get_group_display_name(plugin_event, user_id: Optional[str] = None) -> str:
    target_user_id = utils.safe_str(
        user_id or utils.get_sender_id_from_event(plugin_event)
    ).strip()
    sender_id = utils.get_sender_id_from_event(plugin_event)
    group_id = utils.get_group_id_from_event(plugin_event)

    if group_id:
        try:
            group_member_list = plugin_event.get_group_member_list(group_id)
            for member in _iter_group_members(group_member_list):
                member_user_id = member.get('user_id') or member.get('id') or member.get('qq')
                if utils.safe_str(member_user_id).strip() != target_user_id:
                    continue
                display_name = utils.safe_str(
                    member.get('card') or member.get('name') or member.get('nickname') or ''
                ).strip()
                if display_name:
                    return display_name
        except Exception:
            pass

    if target_user_id == sender_id:
        sender_name = utils.get_sender_name_from_event(plugin_event).strip()
        if sender_name:
            return sender_name

    try:
        stranger_info = plugin_event.get_stranger_info(target_user_id)
        if isinstance(stranger_info, dict) and stranger_info.get('active'):
            stranger_data = stranger_info.get('data', {})
            if isinstance(stranger_data, dict):
                stranger_name = utils.safe_str(
                    stranger_data.get('nickname') or stranger_data.get('name') or ''
                ).strip()
                if stranger_name:
                    return stranger_name
    except Exception:
        pass

    return target_user_id or '未知角斗士'


def build_default_input_text(display_name: str) -> str:
    return f'姓名：{display_name}，请AI完全随机生成离谱设定'


def _build_waiting_room_entry(plugin_event, input_text: str) -> Dict[str, str]:
    user_id = utils.get_sender_id_from_event(plugin_event)
    user_name = utils.get_sender_name_from_event(plugin_event)
    group_display_name = get_group_display_name(plugin_event, user_id=user_id)
    final_input_text = utils.safe_str(input_text).strip()
    final_input_text = final_input_text or build_default_input_text(group_display_name)
    now_text = _now_text()
    return {
        'user_id': user_id,
        'user_name': user_name,
        'group_display_name': group_display_name,
        'input_text': final_input_text,
        'joined_at': now_text,
        'updated_at': now_text,
    }


def add_waiting_player(plugin_event, input_text: str) -> Dict[str, Any]:
    group_state = load_group_state(plugin_event)
    waiting_room = group_state.get('waiting_room', [])
    waiting_entry = _build_waiting_room_entry(plugin_event, input_text)

    if len(waiting_room) >= MAX_PARTICIPANTS:
        return {
            'ok': False,
            'reason': 'room_full',
            'waiting_count': len(waiting_room),
            'user_display_name': waiting_entry.get('group_display_name', ''),
        }

    waiting_room.append(waiting_entry)
    group_state['waiting_room'] = waiting_room
    save_group_state(plugin_event, group_state)
    return {
        'ok': True,
        'waiting_count': len(waiting_room),
        'user_display_name': waiting_entry.get('group_display_name', ''),
        'input_text': waiting_entry.get('input_text', ''),
        'entry_index': len(waiting_room),
    }


def get_waiting_entries_by_user(plugin_event, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    waiting_room = load_group_state(plugin_event).get('waiting_room', [])
    target_user_id = utils.safe_str(user_id or utils.get_sender_id_from_event(plugin_event)).strip()
    result = []
    for entry_index, entry in enumerate(waiting_room, start=1):
        if utils.safe_str(entry.get('user_id', '')).strip() != target_user_id:
            continue
        result.append(
            {
                'entry_index': entry_index,
                'entry': entry,
            }
        )
    return result


def update_waiting_player_by_index_for_user(
    plugin_event,
    entry_index: int,
    input_text: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    group_state = load_group_state(plugin_event)
    waiting_room = group_state.get('waiting_room', [])
    zero_based_index = entry_index - 1
    target_user_id = utils.safe_str(user_id or utils.get_sender_id_from_event(plugin_event)).strip()
    if zero_based_index < 0 or zero_based_index >= len(waiting_room):
        return {
            'ok': False,
            'reason': 'invalid_index',
            'waiting_count': len(waiting_room),
        }

    target_entry = waiting_room[zero_based_index]
    if utils.safe_str(target_entry.get('user_id', '')).strip() != target_user_id:
        return {
            'ok': False,
            'reason': 'not_owner',
            'waiting_count': len(waiting_room),
        }

    new_entry = _build_waiting_room_entry(plugin_event, input_text)
    target_entry['user_name'] = new_entry['user_name']
    target_entry['group_display_name'] = new_entry['group_display_name']
    target_entry['input_text'] = new_entry['input_text']
    target_entry['updated_at'] = new_entry['updated_at']
    group_state['waiting_room'] = waiting_room
    save_group_state(plugin_event, group_state)
    return {
        'ok': True,
        'waiting_count': len(waiting_room),
        'entry_index': entry_index,
        'user_display_name': target_entry.get('group_display_name', ''),
        'input_text': target_entry.get('input_text', ''),
    }


def remove_waiting_player_by_index(plugin_event, entry_index: int) -> Dict[str, Any]:
    group_state = load_group_state(plugin_event)
    waiting_room = group_state.get('waiting_room', [])
    zero_based_index = entry_index - 1
    if zero_based_index < 0 or zero_based_index >= len(waiting_room):
        return {
            'ok': False,
            'reason': 'invalid_index',
            'waiting_count': len(waiting_room),
        }

    removed_entry = waiting_room.pop(zero_based_index)
    group_state['waiting_room'] = waiting_room
    save_group_state(plugin_event, group_state)
    return {
        'ok': True,
        'waiting_count': len(waiting_room),
        'removed_entry': removed_entry,
    }


def remove_waiting_player_by_user(plugin_event, user_id: Optional[str] = None) -> Dict[str, Any]:
    group_state = load_group_state(plugin_event)
    waiting_room = group_state.get('waiting_room', [])
    target_user_id = utils.safe_str(user_id or utils.get_sender_id_from_event(plugin_event)).strip()

    removed_entry_list = []
    removed_index_list = []
    next_waiting_room = []
    for zero_based_index, entry in enumerate(waiting_room):
        if utils.safe_str(entry.get('user_id', '')).strip() == target_user_id:
            removed_entry_list.append(entry)
            removed_index_list.append(zero_based_index + 1)
            continue
        next_waiting_room.append(entry)

    if removed_entry_list:
        group_state['waiting_room'] = next_waiting_room
        save_group_state(plugin_event, group_state)
        return {
            'ok': True,
            'waiting_count': len(next_waiting_room),
            'removed_entry_list': removed_entry_list,
            'removed_index_list': removed_index_list,
            'removed_count': len(removed_entry_list),
        }

    return {
        'ok': False,
        'reason': 'self_not_found',
        'waiting_count': len(waiting_room),
    }


def clear_waiting_room(plugin_event) -> Dict[str, Any]:
    group_state = load_group_state(plugin_event)
    previous_count = len(group_state.get('waiting_room', []))
    group_state['waiting_room'] = []
    save_group_state(plugin_event, group_state)
    return {
        'ok': True,
        'previous_count': previous_count,
    }


def get_runtime_bot_config(plugin_event) -> Dict[str, Any]:
    config_bot_hash = utils.get_bot_hash_from_event(plugin_event)
    bot_config = utils.load_bot_config(config_bot_hash)
    timeout_seconds = _coerce_int(bot_config.get('request_timeout_seconds', 180), 180)
    delay_min_seconds, delay_max_seconds = get_segment_delay_range_from_bot_config(bot_config)
    god_war_enable_switch = _coerce_bool(bot_config.get('god_war_enable_switch', False), False)
    normal_system_prompt = utils.safe_str(bot_config.get('system_prompt') or config.SYSTEM_PROMPT).strip()
    god_war_system_prompt = utils.safe_str(
        bot_config.get('god_war_system_prompt') or config.GOD_WAR_SYSTEM_PROMPT
    ).strip()
    return {
        'api_url': utils.safe_str(bot_config.get('api_url', '')).strip(),
        'api_key': utils.safe_str(bot_config.get('api_key', '')).strip(),
        'model': utils.safe_str(bot_config.get('model', '')).strip(),
        'request_timeout_seconds': max(timeout_seconds, 30),
        'temperature': _coerce_float(bot_config.get('temperature', 0.9), 0.9),
        'segment_delay_min_seconds': delay_min_seconds,
        'segment_delay_max_seconds': delay_max_seconds,
        'qq_forward_message_switch': _coerce_bool(
            bot_config.get('qq_forward_message_switch', False),
            False,
        ),
        'god_war_enable_switch': god_war_enable_switch,
        'normal_system_prompt': normal_system_prompt,
        'god_war_system_prompt': god_war_system_prompt,
        'system_prompt': god_war_system_prompt if god_war_enable_switch else normal_system_prompt,
        'user_prompt_prefix': utils.safe_str(bot_config.get('user_prompt_prefix', '')).strip(),
        'victory_speech_prompt': utils.safe_str(bot_config.get('victory_speech_prompt', '')).strip(),
    }


def api_config_is_ready(plugin_event) -> bool:
    bot_config = get_runtime_bot_config(plugin_event)
    return bool(bot_config['api_url'] and bot_config['api_key'] and bot_config['model'])


def api_config_dict_is_ready(bot_config: Dict[str, Any]) -> bool:
    """判断一份 bot_config 字典里的 API 关键字段是否完整。"""
    if not isinstance(bot_config, dict):
        return False
    return bool(
        utils.safe_str(bot_config.get('api_url', '')).strip()
        and utils.safe_str(bot_config.get('api_key', '')).strip()
        and utils.safe_str(bot_config.get('model', '')).strip()
    )


def test_chat_api_with_bot_config(bot_config: Dict[str, Any]) -> Dict[str, Any]:
    """使用轻量提示词测试当前 API 配置是否可用。"""
    normalized_bot_config = {
        'api_url': utils.safe_str(bot_config.get('api_url', '')).strip(),
        'api_key': utils.safe_str(bot_config.get('api_key', '')).strip(),
        'model': utils.safe_str(bot_config.get('model', '')).strip(),
        'request_timeout_seconds': max(
            _coerce_int(bot_config.get('request_timeout_seconds', 60), 60),
            5,
        ),
        'temperature': _coerce_float(bot_config.get('temperature', 0.2), 0.2),
    }

    if not api_config_dict_is_ready(normalized_bot_config):
        return {
            'ok': False,
            'error_message': 'API 地址、API Key 和模型名称必须完整填写后才能测试。',
            'response_text': '',
            'status_code': None,
        }

    system_prompt = '你是 API 连通性测试助手。请只回复“API测试成功”以及不超过 20 字的补充说明。'
    user_prompt = '请回复 API测试成功，并说明这是一次连接测试。'
    return _call_chat_api(normalized_bot_config, system_prompt, user_prompt)


def build_query_entries(waiting_room: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result = []
    for entry_index, entry in enumerate(waiting_room, start=1):
        result.append(
            {
                'entry_index': str(entry_index),
                'user_display_name': (
                    entry.get('group_display_name')
                    or entry.get('user_name')
                    or entry.get('user_id')
                ),
                'input_text': entry.get('input_text', ''),
            }
        )
    return result


def _generate_combatants(waiting_room: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    combatant_list = []
    for entry_index, entry in enumerate(waiting_room, start=1):
        combatant_list.append(
            {
                'entry_index': entry_index,
                'user_id': entry.get('user_id', ''),
                'display_name': (
                    entry.get('group_display_name')
                    or entry.get('user_name')
                    or entry.get('user_id', '')
                ),
                'input_text': entry.get('input_text', ''),
                'hp': random.randint(*HP_RANGE),
                'mp': random.randint(*MP_RANGE),
                'rolls': [random.randint(1, 20) for _ in range(ROLL_COUNT)],
            }
        )
    return combatant_list


def _build_players_info_str(combatant_list: List[Dict[str, Any]]) -> str:
    text_block_list = []
    for combatant in combatant_list:
        text_block_list.append(
            '\n'.join(
                [
                    f'【参赛资料槽位 {combatant["entry_index"]}】：',
                    f'- 情报：“{combatant["input_text"]}”',
                    (
                        '- 你必须先根据这条情报，总结一个稳定的出场名字/称号。'
                        ' 后续所有播报和面板都只能用这个名字，不能再写成角斗士编号。'
                        ' 无论情报多短，攻击方式、施法方式、特性都必须写完整。'
                    ),
                    f'- 初始面板：[HP: {combatant["hp"]}] / [MP: {combatant["mp"]}]',
                    f'- 命运序列（前10回合固定骰点）：{combatant["rolls"]}',
                ]
            )
        )
    return '\n\n'.join(text_block_list)


def _build_user_prompt(bot_config: Dict[str, Any], combatant_list: List[Dict[str, Any]]) -> str:
    custom_user_prompt = bot_config.get('user_prompt_prefix', '').strip()
    custom_section = ''
    if custom_user_prompt:
        custom_section = custom_user_prompt + '\n\n'
    victory_speech_prompt = utils.safe_str(bot_config.get('victory_speech_prompt', '')).strip()
    victory_speech_prompt_section = ''
    if victory_speech_prompt:
        victory_speech_prompt_section = '\n\n额外的获胜感言要求：\n' + victory_speech_prompt
    user_prompt_template = config.GOD_WAR_USER_PROMPT_TEMPLATE
    if not bot_config.get('god_war_enable_switch', False):
        user_prompt_template = config.USER_PROMPT_TEMPLATE
    return user_prompt_template.format(
        custom_user_prompt_section=custom_section,
        players_info_str=_build_players_info_str(combatant_list),
        victory_speech_prompt_section=victory_speech_prompt_section,
    )


def _mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return '*' * len(api_key)
    return f'{api_key[:4]}***{api_key[-4:]}'


def _call_chat_api(bot_config: Dict[str, Any], system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    payload = {
        'model': bot_config['model'],
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': bot_config['temperature'],
    }
    request_body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request_object = urllib.request.Request(
        bot_config['api_url'],
        data=request_body,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {bot_config["api_key"]}',
        },
    )
    ssl_context = ssl.create_default_context()

    try:
        with urllib.request.urlopen(
            request_object,
            timeout=bot_config['request_timeout_seconds'],
            context=ssl_context,
        ) as response_object:
            response_text = response_object.read().decode('utf-8')
            response_data = json.loads(response_text)
            choices = response_data.get('choices', [])
            status_code = getattr(response_object, 'status', 200)
            if not isinstance(choices, list) or not choices:
                return {
                    'ok': False,
                    'error_message': 'API 返回内容缺少 choices。',
                    'response_text': response_text,
                    'status_code': status_code,
                }
            message_data = choices[0].get('message', {})
            content_text = utils.safe_str(message_data.get('content', '')).strip()
            if not content_text:
                return {
                    'ok': False,
                    'error_message': 'API 返回内容为空。',
                    'response_text': response_text,
                    'status_code': status_code,
                }
            return {
                'ok': True,
                'content': content_text,
                'response_text': response_text,
                'status_code': status_code,
            }
    except urllib.error.HTTPError as error_object:
        error_body = error_object.read().decode('utf-8', errors='ignore')
        return {
            'ok': False,
            'error_message': f'HTTP {error_object.code}：{error_body or error_object.reason}',
            'response_text': error_body,
            'status_code': error_object.code,
        }
    except urllib.error.URLError as error_object:
        return {
            'ok': False,
            'error_message': f'网络请求失败：{utils.safe_str(error_object.reason)}',
            'response_text': '',
            'status_code': None,
        }
    except Exception as error_object:
        return {
            'ok': False,
            'error_message': (
                f'请求模型失败：{type(error_object).__name__}: '
                f'{utils.safe_str(error_object)}'
            ),
            'response_text': '',
            'status_code': None,
        }


def _split_broadcast_segments(response_text: str) -> List[str]:
    segment_list = []
    for raw_segment in utils.safe_str(response_text).split(SEGMENT_SEPARATOR):
        cleaned_segment = raw_segment.strip()
        if cleaned_segment:
            segment_list.append(cleaned_segment)
    return segment_list


def _archive_payload(
    plugin_event,
    bot_config: Dict[str, Any],
    combatant_list: List[Dict[str, Any]],
    system_prompt: str,
    user_prompt: str,
    api_result: Dict[str, Any],
    segment_list: List[str],
    delay_list: List[int],
    success: bool,
    stopped: bool = False,
    used_forward_message: bool = False,
) -> str:
    bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    hag_id = utils.get_hag_id_from_event(plugin_event)
    archive_name = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_file_name = f'{archive_name}_{_safe_filename(hag_id)}.json'
    archive_file_path = os.path.join(_archive_dir(bot_hash), archive_file_name)
    archive_payload = {
        'created_at': _now_text(),
        'plugin_name': config.plugin_name,
        'group_id': utils.get_group_id_from_event(plugin_event),
        'host_id': utils.get_host_id_from_event(plugin_event),
        'hag_id': hag_id,
        'success': success,
        'stopped': stopped,
        'participants': combatant_list,
        'request': {
            'api_url': bot_config.get('api_url', ''),
            'api_key_masked': _mask_api_key(bot_config.get('api_key', '')),
            'model': bot_config.get('model', ''),
            'request_timeout_seconds': bot_config.get('request_timeout_seconds', 180),
            'temperature': bot_config.get('temperature', 0.9),
            'segment_delay_min_seconds': bot_config.get('segment_delay_min_seconds', SEGMENT_DELAY_RANGE[0]),
            'segment_delay_max_seconds': bot_config.get('segment_delay_max_seconds', SEGMENT_DELAY_RANGE[1]),
            'qq_forward_message_switch': bot_config.get('qq_forward_message_switch', False),
            'system_prompt': system_prompt,
            'user_prompt': user_prompt,
        },
        'response': {
            'ok': api_result.get('ok', False),
            'status_code': api_result.get('status_code'),
            'error_message': api_result.get('error_message', ''),
            'response_text': api_result.get('response_text', ''),
            'content': api_result.get('content', ''),
            'segments': segment_list,
            'broadcast_delays': delay_list,
            'used_forward_message': used_forward_message,
        },
    }
    utils.save_json_file(archive_file_path, archive_payload)
    return archive_file_path


def _finish_battle_run(
    plugin_event,
    battle_id: str,
    archive_file_path: str,
    count_battle: bool,
    clear_waiting_room: bool,
) -> None:
    with battle_state_lock:
        group_state = load_group_state(plugin_event)
        if utils.safe_str(group_state.get('active_battle_id', '')) != utils.safe_str(battle_id):
            return
        if count_battle:
            battle_count = _coerce_int(group_state.get('battle_count', 0), 0)
            group_state['battle_count'] = battle_count + 1
        group_state['last_archive_file'] = archive_file_path
        if clear_waiting_room:
            group_state['waiting_room'] = []
        group_state['battle_running'] = False
        group_state['stop_requested'] = False
        group_state['active_battle_id'] = ''
        group_state['battle_started_at'] = ''
        save_group_state(plugin_event, group_state)


def _interruptible_sleep(plugin_event, battle_id: str, sleep_seconds: int) -> bool:
    remaining_seconds = max(int(sleep_seconds), 0)
    while remaining_seconds > 0:
        if is_battle_stop_requested(plugin_event, battle_id=battle_id):
            return True
        time.sleep(1)
        remaining_seconds -= 1
    return is_battle_stop_requested(plugin_event, battle_id=battle_id)


def _create_forward_node(user_id: Any, nickname: str, content: str) -> Dict[str, Any]:
    return {
        'type': 'node',
        'data': {
            'user_id': utils.safe_str(user_id),
            'nickname': nickname,
            'content': content,
        },
    }


def _send_forward_segments(plugin_event, segment_list: List[str]) -> bool:
    if utils.safe_str(getattr(plugin_event, 'platform', {}).get('platform', '')).strip() != 'qq':
        return False
    group_id = utils.get_group_id_from_event(plugin_event)
    if not group_id:
        return False

    bot_name = utils.safe_str(getattr(getattr(plugin_event, 'bot_info', None), 'name', '')).strip()
    bot_name = bot_name or config.plugin_display_name
    bot_id = utils.safe_str(getattr(getattr(plugin_event, 'bot_info', None), 'id', '')).strip() or '0'
    forward_messages = [
        _create_forward_node(bot_id, bot_name, segment_text)
        for segment_text in segment_list
    ]

    try:
        plugin_event.send_group_forward_msg(group_id, forward_messages)
        return True
    except Exception:
        return False


def _broadcast_segments(
    plugin_event,
    segment_list: List[str],
    bot_config: Dict[str, Any],
    battle_id: str,
) -> Dict[str, Any]:
    delay_list = []
    used_forward_message = False
    delay_range = get_segment_delay_range_from_bot_config(bot_config)
    if not segment_list:
        return {
            'delay_list': delay_list,
            'stopped': False,
            'used_forward_message': False,
        }

    if is_battle_stop_requested(plugin_event, battle_id=battle_id):
        return {
            'delay_list': delay_list,
            'stopped': True,
            'used_forward_message': False,
        }

    for index, segment_text in enumerate(segment_list):
        if is_battle_stop_requested(plugin_event, battle_id=battle_id):
            return {
                'delay_list': delay_list,
                'stopped': True,
                'used_forward_message': bool(bot_config.get('qq_forward_message_switch', False)),
            }
        if bot_config.get('qq_forward_message_switch', False):
            if not _send_forward_segments(plugin_event, [segment_text]):
                utils.reply_message(plugin_event, segment_text)
            else:
                used_forward_message = True
        else:
            utils.reply_message(plugin_event, segment_text)
        if index >= len(segment_list) - 1:
            continue
        sleep_seconds = random.randint(*delay_range)
        delay_list.append(sleep_seconds)
        if _interruptible_sleep(plugin_event, battle_id, sleep_seconds):
            return {
                'delay_list': delay_list,
                'stopped': True,
                'used_forward_message': used_forward_message,
            }
    return {
        'delay_list': delay_list,
        'stopped': False,
        'used_forward_message': used_forward_message,
    }


def run_battle(plugin_event, Proc=None, battle_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if battle_context is None:
        battle_context = prepare_battle_run(plugin_event)
    if not battle_context.get('ok'):
        return battle_context

    battle_id = utils.safe_str(battle_context.get('battle_id', '')).strip()
    waiting_room = battle_context.get('waiting_room', [])
    bot_config = battle_context.get('bot_config', get_runtime_bot_config(plugin_event))

    archive_file_path = ''
    count_battle = False
    combatant_list = _generate_combatants(waiting_room)
    system_prompt = bot_config.get('system_prompt') or config.SYSTEM_PROMPT
    user_prompt = _build_user_prompt(bot_config, combatant_list)
    api_result = _call_chat_api(bot_config, system_prompt, user_prompt)
    segment_list: List[str] = []
    delay_list: List[int] = []
    stopped = False
    used_forward_message = False

    if api_result.get('ok'):
        segment_list = _split_broadcast_segments(api_result.get('content', ''))
        if not segment_list:
            api_result = {
                'ok': False,
                'error_message': '模型返回内容中没有可播报的有效切片。',
                'response_text': api_result.get('response_text', ''),
                'status_code': api_result.get('status_code'),
                'content': api_result.get('content', ''),
            }

    if api_result.get('ok'):
        broadcast_result = _broadcast_segments(
            plugin_event,
            segment_list,
            bot_config,
            battle_id,
        )
        delay_list = broadcast_result.get('delay_list', [])
        stopped = bool(broadcast_result.get('stopped', False))
        used_forward_message = bool(broadcast_result.get('used_forward_message', False))

    if stopped:
        _clear_battle_cancelled(battle_id)
        api_result = {
            'ok': False,
            'error_message': 'battle_stopped',
            'response_text': api_result.get('response_text', ''),
            'status_code': api_result.get('status_code'),
            'content': api_result.get('content', ''),
        }

    archive_file_path = _archive_payload(
        plugin_event=plugin_event,
        bot_config=bot_config,
        combatant_list=combatant_list,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        api_result=api_result,
        segment_list=segment_list,
        delay_list=delay_list,
        success=bool(api_result.get('ok')),
        stopped=stopped,
        used_forward_message=used_forward_message,
    )
    count_battle = True

    _finish_battle_run(
        plugin_event,
        battle_id=battle_id,
        archive_file_path=archive_file_path,
        count_battle=count_battle,
        clear_waiting_room=bool(api_result.get('ok')) or stopped,
    )

    if stopped:
        utils.info_log(Proc, f'赛博角斗场已被强制停止，归档：{archive_file_path}')
        return {
            'ok': False,
            'reason': 'battle_stopped',
            'archive_file_path': archive_file_path,
        }

    if not api_result.get('ok'):
        _clear_battle_cancelled(battle_id)
        error_message = api_result.get('error_message', '未知错误')
        utils.error_log(Proc, f'赛博角斗场推演失败：{error_message}')
        return {
            'ok': False,
            'reason': 'battle_failed',
            'error_message': error_message,
            'archive_file_path': archive_file_path,
        }

    _clear_battle_cancelled(battle_id)
    utils.info_log(Proc, f'赛博角斗场推演完成，归档：{archive_file_path}')
    return {
        'ok': True,
        'archive_file_path': archive_file_path,
        'segment_count': len(segment_list),
        'delay_list': delay_list,
    }
