# -*- encoding: utf-8 -*-
"""CelestePlugin 命令解析、选择会话和 Endless 状态编排。"""

import os
import re
import threading
import time
import uuid
from typing import Any

from . import config
from . import function
from . import message_custom
from . import utils


selection_session_dict: dict[str, dict[str, Any]] = {}
selection_lock = threading.RLock()
prewarm_started = False


subcommand_alias_dict = {
    'help': 'help',
    '帮助': 'help',
    'info': 'search',
    'search': 'search',
    'find': 'search',
    '查询': 'search',
    '搜索': 'search',
    'id': 'id',
    '作者': 'author',
    'author': 'author',
    '分类': 'category',
    'category': 'category',
    'cat': 'category',
    '标签': 'tag',
    'tag': 'tag',
    'random': 'random',
    'rand': 'random',
    '随机': 'random',
    'today': 'today',
    '每日': 'today',
    '今日': 'today',
    'endless': 'endless',
    '无尽': 'endless',
    'status': 'plugin_status',
    '状态': 'plugin_status',
    'on': 'plugin_on',
    '开启': 'plugin_on',
    '启用': 'plugin_on',
    'off': 'plugin_off',
    '关闭': 'plugin_off',
    '禁用': 'plugin_off',
}


endless_action_alias_dict = {
    'help': 'help',
    '帮助': 'help',
    'start': 'start',
    '开始': 'start',
    'status': 'status',
    '状态': 'status',
    'continue': 'continue',
    '继续': 'continue',
    '下一图': 'continue',
    'clear': 'clear',
    '通关': 'clear',
    '过关': 'clear',
    'fc': 'full_clear',
    'fullclear': 'full_clear',
    '全收集': 'full_clear',
    '全清': 'full_clear',
    'skip': 'skip',
    '跳过': 'skip',
    'reroll': 'reroll',
    'badmap': 'reroll',
    'bad': 'reroll',
    '坏图': 'reroll',
    '重抽': 'reroll',
    'undo': 'undo',
    '撤销': 'undo',
    'giveup': 'give_up',
    '放弃': 'give_up',
    'detail': 'detail',
    '详情': 'detail',
    'record': 'record',
    '记录': 'record',
    'end': 'end',
    '结束': 'end',
}


def start_prewarm_thread(Proc) -> None:
    """后台预热大型社区数据库，避免首次作者查询长时间阻塞。"""
    global prewarm_started
    if prewarm_started:
        return
    prewarm_started = True

    def worker():
        database_result = function.load_mod_database()
        updater_result = function.load_updater_index()
        if database_result.get('ok') and updater_result.get('ok'):
            utils.info_log(Proc, 'Celeste 社区数据库与 Everest 更新库预热完成。')
        else:
            utils.debug_log(
                Proc,
                f'缓存预热未完全成功：{database_result.get("error", "")} {updater_result.get("error", "")}',
            )

    threading.Thread(target=worker, name='CelestePluginPrewarm', daemon=True).start()


def handle_init(plugin_event, Proc) -> None:
    utils.ensure_runtime_storage_by_event(plugin_event)
    start_prewarm_thread(Proc)
    utils.info_log(Proc, 'CelestePlugin init 完成。')


def handle_init_after(plugin_event, Proc) -> None:
    utils.ensure_runtime_storage_by_event(plugin_event)


def handle_private_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_group_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_heartbeat(plugin_event, Proc) -> None:
    clear_expired_selection_sessions()


def handle_save(plugin_event, Proc) -> None:
    with selection_lock:
        selection_session_dict.clear()


def build_selection_key(plugin_event) -> str:
    linked_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    user_id = utils.get_sender_id_from_event(plugin_event)
    group_id = utils.get_group_id_from_event(plugin_event)
    host_id = utils.get_host_id_from_event(plugin_event)
    if group_id:
        return f'{linked_hash}|group|{host_id}|{group_id}|{user_id}'
    return f'{linked_hash}|private|{user_id}'


def clear_expired_selection_sessions() -> None:
    current_time = time.time()
    with selection_lock:
        expired_keys = []
        for session_key, session in selection_session_dict.items():
            timeout_seconds = float(session.get('timeout_seconds', 300))
            if current_time - float(session.get('updated_at', 0)) > timeout_seconds:
                expired_keys.append(session_key)
        for session_key in expired_keys:
            selection_session_dict.pop(session_key, None)


def save_selection_session(
    plugin_event,
    results: list[dict[str, Any]],
    total_count: int,
    title: str,
    partial: bool = False,
    notice: str = '',
) -> dict[str, Any]:
    global_config = utils.load_global_config()
    session = {
        'results': results,
        'total_count': total_count,
        'title': title,
        'partial': partial,
        'notice': notice,
        'page_index': 0,
        'page_size': max(1, int(global_config.get('result_page_size', 8))),
        'timeout_seconds': max(30, int(global_config.get('selection_timeout_seconds', 300))),
        'updated_at': time.time(),
    }
    with selection_lock:
        selection_session_dict[build_selection_key(plugin_event)] = session
    return session


def get_selection_session(plugin_event) -> dict[str, Any] | None:
    clear_expired_selection_sessions()
    with selection_lock:
        return selection_session_dict.get(build_selection_key(plugin_event))


def render_selection_page(session: dict[str, Any]) -> str:
    session['updated_at'] = time.time()
    results = session.get('results', [])
    page_size = max(1, int(session.get('page_size', 8)))
    page_count = max(1, (len(results) + page_size - 1) // page_size)
    page_index = min(max(0, int(session.get('page_index', 0))), page_count - 1)
    session['page_index'] = page_index
    start_index = page_index * page_size
    page_items = results[start_index : start_index + page_size]

    lines = [
        f'【{session.get("title", "Celeste Mod 搜索")}】',
        f'第 {page_index + 1}/{page_count} 页，共匹配 {session.get("total_count", len(results))} 项',
    ]
    if session.get('partial'):
        lines.append('提示：子分类结果完整；GameBanana 自由标签来自本地详情缓存，可能不完整。')
    if session.get('notice'):
        lines.append(f'提示：{session["notice"]}')
    for offset, item in enumerate(page_items):
        lines.append(function.format_list_item(item, start_index + offset + 1))
    lines.append('直接发送本页序号查看详情；发送“下一页”“上一页”“跳页3”翻页，或发送“结束”退出选择。')
    return '\n'.join(lines)


def reply_detail(plugin_event, item: dict[str, Any], compact: bool = False) -> None:
    detail_result = function.hydrate_item(item)
    if not detail_result.get('ok'):
        utils.reply_message(plugin_event, f'获取 Mod 详情失败：{detail_result.get("error", "未知错误")}')
        return
    utils.reply_long_text(plugin_event, function.format_detail(detail_result['data'], compact=compact))


def reply_search_result(
    plugin_event,
    search_result: dict[str, Any],
    title: str,
) -> None:
    if not search_result.get('ok'):
        utils.reply_message(plugin_event, f'查询失败：{search_result.get("error", "未知错误")}')
        return
    results = search_result.get('results', [])
    if not results:
        utils.reply_message(plugin_event, '没有找到符合条件的 Celeste Mod。')
        return
    if len(results) == 1:
        if search_result.get('partial'):
            utils.reply_message(plugin_event, '提示：该自由标签结果来自本地详情缓存，可能不完整。')
        if search_result.get('notice'):
            utils.reply_message(plugin_event, f'提示：{search_result["notice"]}')
        reply_detail(plugin_event, results[0])
        return
    session = save_selection_session(
        plugin_event,
        results,
        int(search_result.get('count', len(results))),
        title,
        partial=bool(search_result.get('partial', False)),
        notice=utils.safe_str(search_result.get('notice', '')),
    )
    utils.reply_long_text(plugin_event, render_selection_page(session))


def handle_selection_input(plugin_event, message_text: str) -> bool:
    session = get_selection_session(plugin_event)
    if session is None:
        return False
    text = utils.safe_str(message_text).strip().lower()
    if text in ['取消', 'cancel', 'end', '结束']:
        with selection_lock:
            selection_session_dict.pop(build_selection_key(plugin_event), None)
        utils.reply_message(plugin_event, '已结束本次 Celeste Mod 选择。')
        return True

    page_size = max(1, int(session.get('page_size', 8)))
    results = session.get('results', [])
    page_count = max(1, (len(results) + page_size - 1) // page_size)
    if text in ['下一页', '下页', 'next', 'down']:
        session['page_index'] = min(page_count - 1, int(session.get('page_index', 0)) + 1)
        utils.reply_long_text(plugin_event, render_selection_page(session))
        return True
    if text in ['上一页', '上页', 'prev', 'previous', 'up']:
        session['page_index'] = max(0, int(session.get('page_index', 0)) - 1)
        utils.reply_long_text(plugin_event, render_selection_page(session))
        return True

    page_match = re.fullmatch(r'(?:跳页|第|page)\s*(\d+)\s*(?:页)?', text)
    if page_match:
        page_number = int(page_match.group(1))
        if page_number < 1 or page_number > page_count:
            utils.reply_message(plugin_event, f'页码范围为 1 至 {page_count}。')
            return True
        session['page_index'] = page_number - 1
        utils.reply_long_text(plugin_event, render_selection_page(session))
        return True

    if not text.isdigit():
        return False
    session['updated_at'] = time.time()
    selected_index = int(text) - 1
    page_index = int(session.get('page_index', 0))
    current_start = page_index * page_size
    current_end = min(len(results), current_start + page_size)
    if selected_index < current_start or selected_index >= current_end:
        utils.reply_message(plugin_event, f'请输入本页序号 {current_start + 1} 至 {current_end}。')
        return True
    selected_item = results[selected_index]
    with selection_lock:
        selection_session_dict.pop(build_selection_key(plugin_event), None)
    reply_detail(plugin_event, selected_item)
    return True


def parse_subcommand(command_argument: str) -> tuple[str, str]:
    command_info = utils.parse_command(
        command_argument,
        allow_no_prefix=True,
        command_name=list(subcommand_alias_dict.keys()),
    )
    if not command_info.get('is_command'):
        return '', command_argument.strip()
    canonical_name = subcommand_alias_dict.get(command_info['command_name'], '')
    return canonical_name, command_info.get('command_argument', '')


def handle_id(plugin_event, argument: str) -> None:
    matched = re.fullmatch(r'(?:(Mod|Tool|Wip)\s*[:#]?\s*)?(\d+)', argument.strip(), flags=re.I)
    if not matched:
        utils.reply_message(plugin_event, '用法：.clst id 424541，或 .clst id Tool:6924')
        return
    item_type = matched.group(1) or 'Mod'
    item_type = item_type[:1].upper() + item_type[1:].lower()
    result = function.get_item_by_id(int(matched.group(2)), item_type)
    if not result.get('ok'):
        utils.reply_message(plugin_event, f'精确查询失败：{result.get("error", "未知错误")}')
        return
    utils.reply_long_text(plugin_event, function.format_detail(result['data']))


def parse_random_count(argument: str) -> tuple[bool, int, str]:
    text = argument.strip()
    if not text:
        return True, 1, ''
    matched = re.fullmatch(r'(\d+)', text)
    if not matched:
        return False, 0, '随机数量应为整数，例如 .clst 随机 5'
    count = int(matched.group(1))
    max_count = int(utils.load_global_config().get('random_max_count', 10))
    if count < 1 or count > max_count:
        return False, 0, f'随机数量范围为 1 至 {max_count}。'
    return True, count, ''


def handle_random(plugin_event, argument: str) -> None:
    valid, count, error = parse_random_count(argument)
    if not valid:
        utils.reply_message(plugin_event, error)
        return
    random_result = function.random_mods(count)
    if not random_result.get('ok'):
        utils.reply_message(plugin_event, f'随机失败：{random_result.get("error", "未知错误")}')
        return
    detail_texts = []
    for index, item in enumerate(random_result.get('results', []), start=1):
        if count == 1:
            detail_result = function.hydrate_item(item)
            if not detail_result.get('ok'):
                continue
            detail = detail_result['data']
        else:
            detail = item
        heading = f'【随机 {index}/{count}】' if count > 1 else ''
        detail_texts.append(function.format_detail(detail, compact=count > 1, heading=heading))
    if not detail_texts:
        utils.reply_message(plugin_event, '随机到了候选条目，但详情暂时无法获取。')
        return
    utils.reply_long_text(plugin_event, '\n\n──────────\n\n'.join(detail_texts))


def get_today_file_path(plugin_event) -> str:
    linked_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    return os.path.join(utils.get_storage_dir(linked_hash), 'today.json')


def handle_today(plugin_event) -> None:
    today_date = function.get_hong_kong_date()
    cache_path = get_today_file_path(plugin_event)
    cached = utils.read_json_file(cache_path, {})
    cached_detail = cached.get('detail', {})
    if not isinstance(cached_detail, dict):
        cached_detail = {}
    if (
        cached.get('date') == today_date
        and cached.get('source') == 'maddie_random_map'
        and cached_detail
    ):
        detail = cached_detail
    else:
        daily_result = function.get_daily_mod(today_date)
        if not daily_result.get('ok'):
            utils.reply_message(plugin_event, f'每日 Mod 获取失败：{daily_result.get("error", "未知错误")}')
            return
        detail = daily_result['data']
        utils.save_json_file(
            cache_path,
            {'date': today_date, 'source': 'maddie_random_map', 'detail': detail},
        )
    text = function.format_detail(detail, heading=f'【{today_date} 每日 Celeste Mod】')
    utils.reply_long_text(plugin_event, text)


def get_endless_file_path(plugin_event) -> str:
    return os.path.join(utils.get_personal_storage_dir(plugin_event), 'endless.json')


def get_endless_record_file_path(plugin_event) -> str:
    return os.path.join(utils.get_personal_storage_dir(plugin_event), 'endless_record.json')


def load_endless_state(plugin_event) -> dict[str, Any]:
    return utils.read_json_file(get_endless_file_path(plugin_event), {})


def save_endless_state(plugin_event, state: dict[str, Any]) -> bool:
    return utils.save_json_file(get_endless_file_path(plugin_event), state)


def load_endless_record(plugin_event) -> dict[str, Any]:
    return function.normalize_endless_record(
        utils.read_json_file(get_endless_record_file_path(plugin_event), {})
    )


def save_endless_record(plugin_event, record: dict[str, Any]) -> bool:
    return utils.save_json_file(
        get_endless_record_file_path(plugin_event),
        function.normalize_endless_record(record),
    )


def persist_endless_state(plugin_event, state: dict[str, Any]) -> bool:
    if save_endless_state(plugin_event, state):
        return True
    utils.reply_message(plugin_event, '无尽挑战状态保存失败，本次操作未确认，请检查磁盘权限或空间。')
    return False


def record_endless_score(plugin_event, state: dict[str, Any], result: str) -> bool:
    """把本局分数写入跨群共享的个人战绩，并在状态中标记防重。"""
    if state.get('score_recorded'):
        return True
    if not utils.safe_str(state.get('run_id', '')).strip():
        state['run_id'] = uuid.uuid4().hex
    state['finished_at'] = int(time.time())
    try:
        record = function.add_endless_score_record(load_endless_record(plugin_event), state, result)
    except ValueError as exception_object:
        utils.reply_message(plugin_event, f'无尽战绩生成失败：{exception_object}')
        return False
    if not save_endless_record(plugin_event, record):
        utils.reply_message(plugin_event, '无尽战绩保存失败，本次结束操作未确认，请检查磁盘权限或空间。')
        return False
    state['score_recorded'] = True
    state['record_result'] = result
    return True


def remove_recorded_endless_score(plugin_event, state: dict[str, Any]) -> bool:
    """撤销已结束状态时同步撤销个人战绩。"""
    if not state.get('score_recorded'):
        return True
    record = function.remove_endless_score_record(
        load_endless_record(plugin_event),
        utils.safe_str(state.get('run_id', '')),
    )
    if save_endless_record(plugin_event, record):
        return True
    utils.reply_message(plugin_event, '撤销个人无尽战绩失败，本次撤销未执行。')
    return False


def delete_endless_state(plugin_event) -> None:
    try:
        os.remove(get_endless_file_path(plugin_event))
    except FileNotFoundError:
        pass
    except Exception:
        pass


def parse_endless_action(argument: str) -> tuple[str, str]:
    command_info = utils.parse_command(
        argument,
        allow_no_prefix=True,
        command_name=list(endless_action_alias_dict.keys()),
    )
    if not command_info.get('is_command'):
        return '', argument.strip()
    return (
        endless_action_alias_dict.get(command_info['command_name'], ''),
        command_info.get('command_argument', ''),
    )


def handle_plugin_switch(plugin_event, action: str) -> None:
    """处理当前群的 CelestePlugin 独立开关。"""
    if not utils.get_group_switch_key(plugin_event):
        return
    currently_disabled = utils.is_group_disabled(plugin_event)
    if action == 'plugin_status':
        status_text = '关闭' if currently_disabled else '开启'
        utils.reply_message(plugin_event, f'当前群 CelestePlugin 状态：{status_text}')
        return
    if not utils.can_manage_group_switch(plugin_event):
        utils.reply_message(plugin_event, '仅群主、群管理员或 OlivaDiceCore 骰主可以修改本群插件开关。')
        return
    target_disabled = action == 'plugin_off'
    if currently_disabled == target_disabled:
        status_text = '关闭' if target_disabled else '开启'
        utils.reply_message(plugin_event, f'当前群 CelestePlugin 已经是{status_text}状态。')
        return
    if not utils.set_group_disabled(plugin_event, target_disabled):
        utils.reply_message(plugin_event, 'CelestePlugin 群开关保存失败，请检查磁盘权限或空间。')
        return
    status_text = '关闭' if target_disabled else '开启'
    utils.reply_message(plugin_event, f'已将当前群 CelestePlugin 设置为：{status_text}')


def handle_endless(plugin_event, argument: str) -> None:
    action, action_argument = parse_endless_action(argument)
    if action in ['', 'help']:
        utils.reply_message(plugin_event, message_custom.endless_help_text)
        return

    if action == 'record':
        utils.reply_message(plugin_event, function.format_endless_record(load_endless_record(plugin_event)))
        return

    if action == 'start':
        existing_state = load_endless_state(plugin_event)
        if existing_state.get('status') in ['active', 'pending']:
            utils.reply_message(plugin_event, '当前已有进行中的挑战；请先使用“.clst无尽 结束”，避免覆盖进度。')
            return
        if existing_state.get('status') == 'failed':
            if not record_endless_score(plugin_event, existing_state, 'replaced'):
                return
        initial_skips = 1
        if action_argument.strip():
            if not re.fullmatch(r'\d+', action_argument.strip()):
                utils.reply_message(plugin_event, '初始跳过次数应为 0 至 10 的整数。')
                return
            initial_skips = int(action_argument.strip())
        if initial_skips < 0 or initial_skips > 10:
            utils.reply_message(plugin_event, '初始跳过次数应为 0 至 10。')
            return
        random_map_result = function.get_random_map(include_cover_mirror=True)
        if not random_map_result.get('ok'):
            utils.reply_message(plugin_event, f'开始失败：{random_map_result.get("error", "无法抽取地图")}')
            return
        state = function.new_endless_state(initial_skips, random_map_result['data'])
        if not persist_endless_state(plugin_event, state):
            return
        utils.reply_long_text(
            plugin_event,
            function.format_endless_state(state, notice='新的 Celeste Endless 已开始。'),
        )
        return

    state = load_endless_state(plugin_event)
    if not state:
        utils.reply_message(plugin_event, '当前没有无尽挑战，请使用“.clst无尽 开始”。')
        return

    if action == 'status':
        utils.reply_long_text(plugin_event, function.format_endless_state(state))
        return
    if action == 'continue':
        if state.get('status') != 'pending':
            utils.reply_message(plugin_event, '当前没有等待抽取的下一张地图。')
            return
        random_map_result = function.get_random_map(include_cover_mirror=True)
        if not random_map_result.get('ok'):
            utils.reply_message(plugin_event, f'仍未能抽取下一图：{random_map_result.get("error", "未知错误")}')
            return
        state['current_map'] = function.compact_endless_map(random_map_result['data'])
        state['status'] = 'active'
        state['updated_at'] = int(time.time())
        if not persist_endless_state(plugin_event, state):
            return
        utils.reply_long_text(
            plugin_event,
            function.format_endless_state(state, notice='已成功抽取下一图。'),
        )
        return
    if action == 'detail':
        current_map = state.get('current_map', {})
        if not current_map:
            utils.reply_message(plugin_event, '当前无尽挑战没有地图信息。')
            return
        reply_detail(plugin_event, current_map)
        return
    if action == 'end':
        if not record_endless_score(plugin_event, state, 'ended'):
            return
        score = int(state.get('clears', 0) or 0)
        delete_endless_state(plugin_event)
        utils.reply_message(plugin_event, f'本次 Celeste Endless 已结束并记录，最终分数：{score}。')
        return

    if action == 'reroll':
        random_map_result = function.get_random_map(include_cover_mirror=True)
        if not random_map_result.get('ok'):
            utils.reply_message(plugin_event, f'操作未执行：{random_map_result.get("error", "无法抽取下一图")}')
            return
        try:
            new_state = function.transition_endless(state, action, next_map=random_map_result['data'])
        except ValueError as exception_object:
            utils.reply_message(plugin_event, utils.safe_str(exception_object))
            return
        if not persist_endless_state(plugin_event, new_state):
            return
        utils.reply_long_text(
            plugin_event,
            function.format_endless_state(new_state, notice='已将当前地图标记为坏图并免费重抽。'),
        )
        return

    try:
        new_state = function.transition_endless(state, action)
    except ValueError as exception_object:
        utils.reply_message(plugin_event, utils.safe_str(exception_object))
        return

    if action == 'undo' and state.get('score_recorded'):
        if not remove_recorded_endless_score(plugin_event, state):
            return
    if new_state.get('status') == 'failed':
        record_result = 'give_up' if action == 'give_up' else 'failed'
        if not record_endless_score(plugin_event, new_state, record_result):
            return
    if not persist_endless_state(plugin_event, new_state):
        return

    if new_state.get('status') == 'pending':
        random_map_result = function.get_random_map(include_cover_mirror=True)
        if random_map_result.get('ok'):
            new_state['current_map'] = function.compact_endless_map(random_map_result['data'])
            new_state['status'] = 'active'
            new_state['updated_at'] = int(time.time())
            if not persist_endless_state(plugin_event, new_state):
                return
    action_message_dict = {
        'clear': '已记录普通通关，分数 +1。',
        'full_clear': '已记录全收集，分数 +1、跳过次数 +1。',
        'skip': '已执行跳过。' if state.get('skips', 0) > 0 else '没有可用跳过次数，本局挑战失败。',
        'undo': '已撤销上一步操作。',
        'give_up': '已放弃本局挑战。',
    }
    utils.reply_long_text(
        plugin_event,
        function.format_endless_state(
            new_state,
            notice=action_message_dict.get(action, '操作完成。'),
        ),
    )


def dispatch_clst_command(plugin_event, command_argument: str) -> None:
    argument = command_argument.strip()
    if not argument:
        utils.reply_message(plugin_event, message_custom.help_text)
        return

    subcommand, sub_argument = parse_subcommand(argument)
    if subcommand == 'help':
        utils.reply_message(plugin_event, message_custom.help_text)
        return
    if subcommand in ['plugin_status', 'plugin_on', 'plugin_off']:
        handle_plugin_switch(plugin_event, subcommand)
        return
    if subcommand == 'search':
        reply_search_result(plugin_event, function.search_title(sub_argument), f'标题搜索：{sub_argument}')
        return
    if subcommand == 'id':
        handle_id(plugin_event, sub_argument)
        return
    if subcommand == 'author':
        reply_search_result(plugin_event, function.search_author(sub_argument), f'作者搜索：{sub_argument}')
        return
    if subcommand == 'category':
        reply_search_result(plugin_event, function.search_category(sub_argument), f'分类搜索：{sub_argument}')
        return
    if subcommand == 'tag':
        reply_search_result(plugin_event, function.search_tag(sub_argument), f'标签搜索：{sub_argument}')
        return
    if subcommand == 'random':
        handle_random(plugin_event, sub_argument)
        return
    if subcommand == 'today':
        handle_today(plugin_event)
        return
    if subcommand == 'endless':
        handle_endless(plugin_event, sub_argument)
        return

    reply_search_result(plugin_event, function.search_title(argument), f'标题搜索：{argument}')


@utils.log_exception('handle_message')
def handle_message(plugin_event, Proc) -> None:
    """消息入口：群开关管理命令优先，其余命令受当前群独立开关控制。"""
    raw_bot_hash = utils.ensure_runtime_storage_by_event(plugin_event)
    if not utils.check_core_group_enable(plugin_event):
        return

    original_text = utils.get_message_text_from_event(plugin_event)
    cleaned_text = utils.strip_reply_segment(original_text)
    at_items, remaining_after_at = utils.parse_at_segments(cleaned_text)
    if at_items and not utils.is_force_reply_to_current_bot(at_items, plugin_event):
        return

    prefix, _remaining = utils.parse_prefix(remaining_after_at, config.allowed_prefix_list)
    global_config = utils.load_global_config()
    bot_config = utils.load_bot_config(raw_bot_hash)
    if not global_config.get('global_enable_switch', True):
        return
    if not bot_config.get('bot_enable_switch', True):
        return

    root_command = utils.parse_command(
        remaining_after_at,
        prefix_list=config.allowed_prefix_list,
        command_name=config.root_command_name,
    )
    if utils.is_group_disabled(plugin_event):
        if root_command.get('is_command'):
            subcommand, _sub_argument = parse_subcommand(root_command.get('command_argument', ''))
            if subcommand in ['plugin_status', 'plugin_on', 'plugin_off']:
                dispatch_clst_command(plugin_event, root_command.get('command_argument', ''))
        return
    if not prefix and handle_selection_input(plugin_event, remaining_after_at):
        return
    if not root_command.get('is_command'):
        return

    dispatch_clst_command(plugin_event, root_command.get('command_argument', ''))
