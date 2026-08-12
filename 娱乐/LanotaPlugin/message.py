# -*- encoding: utf-8 -*-
"""LanotaPlugin 消息解析与命令处理。"""

import datetime
import math
import re
import threading
import time
from typing import Any

from . import b30
from . import config
from . import crawler
from . import function
from . import portal
from . import score_overrides
from . import utils

# 全局搜索结果会话管理（用于分页和序号选择）
search_session_dict = {}

management_command_name_set = {'laglobal', 'labot', 'lagroup', 'sync', 'cover'}
b30_cooldown_lock = threading.RLock()
b30_last_used: dict[str, float] = {}

command_configs = [
    ('today', '今日曲'),
    ('random', '随机'),
    ('alias', '别名'),
    ('song', '歌曲'),
    ('info', '查分'),
    ('artist', '曲师'),
    ('help', '帮助'),
    ('time', '时长'),
    ('all', '全部'),
    ('update', '更新'),
    ('fullcheck', '全量检测'),
    ('sync', '同步'),
    ('cover', '曲绘'),
    ('cal', '计算'),
    ('notes', '物量'),
    ('b30', 'b30'),
    ('score', '成绩录入'),
    ('override', '成绩覆盖'),
    ('bind', '绑定'),
    ('unbind', '解绑'),
    ('user', '用户'),
    ('friend', '好友码'),
    ('category', 'cate'),
    ('table', '定数表'),
    ('ritmo', '里莫'),
]


root_command_name_list = ['lanota', 'la']
subcommand_alias_dict = {
    'today': 'today',
    '今日曲': 'today',
    'random': 'random',
    'rand': 'random',
    '随机': 'random',
    'alias': 'alias',
    '别名': 'alias',
    'song': 'song',
    '歌曲': 'song',
    'info': 'info',
    '查分': 'info',
    'artist': 'artist',
    '曲师': 'artist',
    'help': 'help',
    '帮助': 'help',
    'time': 'time',
    '时长': 'time',
    'all': 'all',
    '全部': 'all',
    'update': 'update',
    '更新': 'update',
    'fullcheck': 'fullcheck',
    'full': 'fullcheck',
    '全量检测': 'fullcheck',
    '全量': 'fullcheck',
    'sync': 'sync',
    '同步': 'sync',
    'cover': 'cover',
    '曲绘': 'cover',
    'cal': 'cal',
    'calculate': 'cal',
    '计算': 'cal',
    'notes': 'notes',
    '物量': 'notes',
    'b30': 'b30',
    'score': 'score',
    '成绩': 'score',
    '录入': 'score',
    '成绩录入': 'score',
    'override': 'score',
    '覆盖': 'score',
    '成绩覆盖': 'score',
    'bind': 'bind',
    '绑定': 'bind',
    'unbind': 'unbind',
    '解绑': 'unbind',
    'user': 'user',
    '用户': 'user',
    '玩家': 'user',
    'friend': 'friend',
    '好友码': 'friend',
    'category': 'category',
    'cate': 'category',
    '分类': 'category',
    'table': 'table',
    '定数表': 'table',
    'ritmo': 'ritmo',
    '里莫': 'ritmo',
    'global': 'laglobal',
    'bot': 'labot',
    'on': 'lagroup',
    'off': 'lagroup',
    'color': 'color',
    '设置背景色': 'color',
    '自定义背景色': 'color',
    'set_bg': 'color',
    'bg_set': 'color',
    'set-bg': 'color',
    'bg-set': 'color',
    'set-bgcolor': 'color',
    'confirm': 'confirm',
    'deny': 'deny',
}
subcommand_name_list = list(subcommand_alias_dict.keys())
group_short_action_set = {'on', 'off'}


# ============ 搜索会话管理相关 ============

def build_session_key(plugin_event) -> str:
    """构建用户会话密钥（基于bot、用户ID和群组）。"""
    bot_hash = utils.get_bot_hash_from_event(plugin_event)
    user_id = utils.get_sender_id_from_event(plugin_event)
    group_id = utils.get_group_id_from_event(plugin_event)
    if group_id:
        return f'{bot_hash}|group|{group_id}|{user_id}'
    return f'{bot_hash}|private|{user_id}'


def save_search_session(
    plugin_event,
    results: list[dict[str, Any]],
    match_type: str | None,
    view_mode: str = 'song',
    region: str | None = None,
) -> None:
    """保存搜索结果为会话。"""
    session_key = build_session_key(plugin_event)
    search_session_dict[session_key] = {
        'results': results,
        'match_type': match_type,
        'view_mode': view_mode,
        'region': region,
        'page_index': 0,
        'updated_at': time.time(),
    }


def get_search_session(plugin_event) -> dict[str, Any]:
    """获取有效的搜索会话。"""
    clear_expired_sessions()
    session_key = build_session_key(plugin_event)
    return search_session_dict.get(session_key, {})


def clear_search_session(plugin_event) -> None:
    """清除搜索会话。"""
    session_key = build_session_key(plugin_event)
    search_session_dict.pop(session_key, None)


def clear_expired_sessions(force: bool = False) -> None:
    """清除过期的会话。"""
    now_time = time.time()
    timeout_seconds = config.selection_timeout_seconds
    expired_keys = []
    for session_key, session_data in search_session_dict.items():
        if force or now_time - session_data.get('updated_at', now_time) > timeout_seconds:
            expired_keys.append(session_key)
    for session_key in expired_keys:
        search_session_dict.pop(session_key, None)


def get_current_page_range(session_data: dict[str, Any]) -> range:
    """获取当前页的索引范围（从1开始）。"""
    results = session_data.get('results', [])
    page_size = config.result_page_size
    page_index = session_data.get('page_index', 0)
    total_pages = max(1, math.ceil(len(results) / page_size))
    page_index = max(0, min(page_index, total_pages - 1))
    
    start_idx = page_index * page_size + 1
    end_idx = min((page_index + 1) * page_size, len(results)) + 1
    return range(start_idx, end_idx)


def handle_search_session_input(plugin_event, input_text: str) -> bool:
    """处理搜索会话的后续输入（序号、分页命令等）。
    
    返回True表示处理成功，False表示无有效会话或处理失败。
    """
    session_data = get_search_session(plugin_event)
    if not session_data:
        return False
    
    stripped_text = utils.safe_str(input_text).strip()
    results = session_data.get('results', [])
    page_size = config.result_page_size
    page_index = session_data.get('page_index', 0)
    total_pages = max(1, math.ceil(len(results) / page_size))
    page_index = max(0, min(page_index, total_pages - 1))

    if stripped_text.lower() in ['end', '结束']:
        clear_search_session(plugin_event)
        reply_text(plugin_event, '已结束本次搜索选择。')
        return True
    
    # 处理分页命令：下一页/上一页/第X页
    if stripped_text.lower() in ['下一页', 'next', 'down']:
        if len(results) <= page_size:
            reply_text(plugin_event, '只有一页，无法翻页。')
            return True
        if page_index >= total_pages - 1:
            formatted_results, _, _ = function.format_search_results_with_pagination(results, page_index, page_size)
            reply_text(plugin_event, f'已是最后一页\n\n{formatted_results}', max_chars=config.search_image_max_chars)
            return True
        session_data['page_index'] = page_index + 1
        session_data['updated_at'] = time.time()
        formatted_results, _, _ = function.format_search_results_with_pagination(results, page_index + 1, page_size)
        reply_text(plugin_event, formatted_results, max_chars=config.search_image_max_chars)
        return True
    
    if stripped_text.lower() in ['上一页', 'prev', 'up']:
        if len(results) <= page_size:
            reply_text(plugin_event, '只有一页，无法翻页。')
            return True
        if page_index <= 0:
            formatted_results, _, _ = function.format_search_results_with_pagination(results, page_index, page_size)
            reply_text(plugin_event, f'已是第一页\n\n{formatted_results}', max_chars=config.search_image_max_chars)
            return True
        session_data['page_index'] = page_index - 1
        session_data['updated_at'] = time.time()
        formatted_results, _, _ = function.format_search_results_with_pagination(results, page_index - 1, page_size)
        reply_text(plugin_event, formatted_results, max_chars=config.search_image_max_chars)
        return True
    
    # 处理"第X页"命令
    page_match = re.match(r'^第(\d+)页$', stripped_text)
    if page_match:
        target_page = int(page_match.group(1))
        if target_page < 1 or target_page > total_pages:
            reply_text(plugin_event, f'页码无效，总共 {total_pages} 页。')
            return True
        session_data['page_index'] = target_page - 1
        session_data['updated_at'] = time.time()
        formatted_results, _, _ = function.format_search_results_with_pagination(results, target_page - 1, page_size)
        reply_text(plugin_event, formatted_results, max_chars=config.search_image_max_chars)
        return True
    
    # 处理序号选择
    if re.match(r'^\d+$', stripped_text):
        selected_index = int(stripped_text)
        current_range = get_current_page_range(session_data)
        if selected_index not in current_range:
            reply_text(plugin_event, f'序号无效，当前页可用的序号为：{min(current_range)}-{max(current_range)}')
            return True
        
        selected_song = results[selected_index - 1]
        clear_search_session(plugin_event)
        if session_data.get('view_mode') == 'info':
            reply_song_info(plugin_event, selected_song, region=session_data.get('region'))
        else:
            reply_song_card(plugin_event, selected_song)
        return True
    
    # 如果输入不符合预期的格式
    if len(results) > page_size:
        reply_text(plugin_event, '请输入序号、"下一页"、"上一页"、"第X页" 或 "结束"。')
        return True
    reply_text(plugin_event, '请输入序号或 "结束"。')
    return True


# ============ 消息处理相关 ============

def handle_init(plugin_event, Proc) -> None:
    utils.info_log(Proc, 'LanotaPlugin init 完成。')


def handle_init_after(plugin_event, Proc) -> None:
    utils.debug_log(Proc, 'LanotaPlugin init_after 已执行。')


def handle_private_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_group_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_save(plugin_event, Proc) -> None:
    clear_expired_sessions(force=True)
    utils.debug_log(Proc, 'LanotaPlugin save 已执行。')


def is_plain_text_mode(plugin_event) -> bool:
    bot_hash = utils.get_bot_hash_from_event(plugin_event)
    bot_config = utils.load_bot_config(bot_hash)
    return bool(bot_config.get('plain_text_mode', False)) or not bool(bot_config.get('send_as_image', True))


def reply_text(plugin_event, text: str, max_chars: int | None = None) -> None:
    bot_hash = utils.get_bot_hash_from_event(plugin_event)
    bot_config = utils.load_bot_config(bot_hash)
    user_id = utils.get_sender_id_from_event(plugin_event)
    text_content = utils.safe_str(text)
    use_text_image = len(text_content.strip()) >= config.text_image_min_chars
    if use_text_image and bot_config.get('send_as_image', True) and not is_plain_text_mode(plugin_event):
        linked_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
        image_path = function.create_text_image(
            text_content,
            user_id=user_id,
            max_chars=max_chars,
            bot_hash=linked_bot_hash,
        )
        if image_path:
            utils.reply_image(plugin_event, image_path, text)
            return
    if not use_text_image:
        text_content = re.sub(r'\s*\n+\s*', ' ', text_content).strip()
    utils.reply_message(plugin_event, text_content)


def reply_large_text(plugin_event, text: str) -> None:
    if is_plain_text_mode(plugin_event):
        utils.reply_long_plain_text(plugin_event, text)
        return
    reply_text(plugin_event, text)


def reply_song_detail(plugin_event, header: str, song: dict[str, Any]) -> None:
    """发送单曲详情，并在启用时附带本地缓存曲绘。"""
    message_text = f'{header}\n\n{function.format_song_info(song)}'
    global_config = utils.load_global_config()
    if not global_config.get('send_cover_art', True):
        reply_text(plugin_event, message_text, max_chars=config.image_max_chars)
        return

    cover_paths = crawler.ensure_song_covers(song)
    if not cover_paths:
        reply_text(plugin_event, message_text, max_chars=config.image_max_chars)
        return

    if is_plain_text_mode(plugin_event):
        utils.reply_images_with_text(plugin_event, cover_paths, message_text)
        return
    linked_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    text_image_path = function.create_text_image(
        message_text,
        user_id=utils.get_sender_id_from_event(plugin_event),
        max_chars=config.image_max_chars,
        bot_hash=linked_bot_hash,
    )
    if text_image_path:
        utils.reply_images_with_text(plugin_event, [*cover_paths, text_image_path])
    else:
        utils.reply_images_with_text(plugin_event, cover_paths, message_text)


def _add_calculated_info_ratings(
    song: dict[str, Any],
    scores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """仅为可按 4.0+ 整数公式还原的官网成绩补充 Rating 信息。"""
    difficulty_names = ('whisper', 'acoustic', 'ultra', 'master')
    result = []
    legacy = song.get('Legacy', {})
    for row in scores:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item['scoreRatingValid'] = False
        try:
            difficulty = int(item.get('difficulty', -1))
        except (TypeError, ValueError):
            result.append(item)
            continue
        if not 0 <= difficulty < len(difficulty_names):
            result.append(item)
            continue

        difficulty_key = difficulty_names[difficulty]
        chart_set = str(item.get('chartSet', 'current')).casefold()
        if chart_set == 'legacy' and isinstance(legacy, dict):
            total = legacy.get(f'Max{difficulty_key.capitalize()}')
            constants = legacy.get('official_constant', {})
        elif chart_set == 'current':
            notes = song.get('notes', {})
            total = notes.get(difficulty_key) if isinstance(notes, dict) else None
            constants = song.get('official_constant', {})
        else:
            result.append(item)
            continue
        chart_constant = constants.get(difficulty_key) if isinstance(constants, dict) else None
        calculated = b30.calculate_score_rating(item.get('score'), total, chart_constant)
        if calculated is not None:
            item.update({
                'scoreAccuracy': calculated['scoreAccuracy'],
                'singleRating': calculated['singleRating'],
                'ratingPercent': calculated['ratingPercent'],
                'scoreRatingValid': True,
            })
        result.append(item)
    return result


def _song_info_fallback_text(
    song: dict[str, Any],
    *,
    info_mode: bool = False,
    region: str | None = None,
    player: dict[str, Any] | None = None,
    scores: list[dict[str, Any]] | None = None,
    notice: str = '',
) -> str:
    """浏览器不可用时使用的歌曲/查分文本回退。"""
    lines = [function.format_song_info(song)]
    if info_mode and player:
        lines.extend([
            '',
            f'玩家：{player.get("username") or "未知玩家"}（{portal.region_display_name(region or "global")}）',
            f'Rating：{player.get("rating", "未知")}',
        ])
        score_map = {
            (
                str(item.get('chartSet', 'current')),
                int(item.get('difficulty', -1)),
            ): item
            for item in (scores or [])
            if isinstance(item, dict)
        }
        diff_names = ['Whisper', 'Acoustic', 'Ultra', 'Master']
        chart_sets = [('现行谱面', 'current')]
        if isinstance(song.get('Legacy'), dict) and song.get('Legacy'):
            chart_sets.append(('Legacy 谱面', 'legacy'))
        for chart_set_name, chart_set in chart_sets:
            lines.append(f'[{chart_set_name}]')
            for difficulty_index, difficulty_name in enumerate(diff_names):
                row = score_map.get((chart_set, difficulty_index))
                if row:
                    score_display = (
                        row.get('score')
                        if row.get('score') is not None
                        else '未录入'
                    )
                    line = (
                        f'{difficulty_name}：分数 {score_display} / '
                        f'Clear {row.get("clear", "未知")} / Rank {row.get("rank", "未知")}'
                    )
                    if row.get('override'):
                        line = (
                            f'{line} / 录入单曲 Rating {float(row.get("singleRating", 0)):.2f}'
                        )
                        if row.get('ratingPercent') is not None:
                            line = f'{line} / Rating% {float(row["ratingPercent"]):.2f}%'
                        if row.get('scoreAccuracy') is not None:
                            accuracy_prefix = '≈' if row.get('accuracyInferred') else ''
                            line = f'{line} / {accuracy_prefix}准度 {float(row["scoreAccuracy"]):.2f}%'
                        if row.get('overrideWarning'):
                            line = f'{line} / 提示：{row["overrideWarning"]}'
                    elif row.get('scoreRatingValid'):
                        line = (
                            f'{line} / 单曲 Rating {float(row["singleRating"]):.2f}'
                            f' / Rating% {float(row["ratingPercent"]):.2f}%'
                            f' / 准度 {float(row["scoreAccuracy"]):.2f}%'
                        )
                    lines.append(line)
                else:
                    lines.append(f'{difficulty_name}：未游玩')
    if notice:
        lines.extend(['', notice])
    return '\n'.join(lines)


def reply_song_card(
    plugin_event,
    song: dict[str, Any],
    *,
    info_mode: bool = False,
    region: str | None = None,
    player_data: dict[str, Any] | None = None,
    score_rows: list[dict[str, Any]] | None = None,
    notice: str = '',
) -> None:
    """发送歌曲卡片；曲绘与 HTML 成绩卡片分开发送。"""
    selected_region = portal.normalize_region(region or (player_data or {}).get('_portal_region', 'global'))
    player = {}
    if isinstance(player_data, dict):
        candidate = player_data.get('friend') or player_data.get('player') or {}
        if isinstance(candidate, dict):
            player = dict(candidate)
    effective_info_mode = bool(info_mode and player and score_rows)
    fallback_text = _song_info_fallback_text(
        song,
        info_mode=effective_info_mode,
        region=selected_region,
        player=player,
        scores=score_rows,
        notice=notice,
    )

    global_config = utils.load_global_config()
    if global_config.get('send_cover_art', True):
        try:
            cover_paths = crawler.ensure_song_covers(song)
            if cover_paths:
                utils.reply_images_with_text(plugin_event, cover_paths)
        except Exception as exception_object:
            utils.debug_log(None, f'歌曲曲绘发送失败：{type(exception_object).__name__}: {exception_object}')

    card_song = dict(song)
    chapter_table = function.load_table_data().get(str(song.get('chapter', '')), {})
    if isinstance(chapter_table, dict):
        card_song['folk_constant'] = {
            difficulty_name: chapter_table.get(difficulty_name.capitalize())
            for difficulty_name in ['whisper', 'acoustic', 'ultra', 'master']
            if chapter_table.get(difficulty_name.capitalize()) not in [None, '']
        }
    card_data = {
        '_portal_region': selected_region,
        'song': card_song,
        'infoMode': effective_info_mode,
        'player': player,
        'scores': score_rows or [],
        'notice': notice,
    }
    bot_config = utils.load_bot_config(utils.get_bot_hash_from_event(plugin_event))
    html_card_enabled = bool(bot_config.get('song_card_html_enable', True))
    if is_plain_text_mode(plugin_event) or not html_card_enabled:
        reply_text(plugin_event, fallback_text, max_chars=config.image_max_chars)
        return
    try:
        image_path = portal.render_song_card(card_data)
    except Exception as exception_object:
        utils.debug_log(None, f'歌曲 HTML 卡片渲染失败：{type(exception_object).__name__}: {exception_object}')
        image_path = None
    if image_path:
        utils.reply_image(plugin_event, image_path, fallback_text)
        return
    reply_text(plugin_event, f'{fallback_text}\n\nHTML 卡片截图失败。\n{portal.render_status_text()}')


def reply_song_info(plugin_event, song: dict[str, Any], region: str | None = None) -> None:
    """查询绑定玩家该歌曲成绩；没有成绩时回退为歌曲卡片并提示。"""
    legacy_data = song.get('Legacy', {})
    legacy_song_id = (
        str(legacy_data.get('official_songid', '') or '').strip()
        if isinstance(legacy_data, dict)
        else ''
    )
    current_song_id = str(song.get('official_songid', '') or '').strip()
    if not current_song_id and not legacy_song_id:
        reply_song_card(
            plugin_event,
            song,
            region=region,
            notice='这首歌曲尚未关联官方 ID，暂时无法查询个人成绩。',
        )
        return
    try:
        compare_data, _nano_id, cache_error = portal.get_compare_data_cached(plugin_event, region)
        selected_region = portal.normalize_region(region or compare_data.get('_portal_region', 'global'))
        score_rows = portal.find_compare_song_scores(
            compare_data,
            current_song_id,
            chart_set='current',
        )
        if legacy_song_id:
            score_rows.extend(
                portal.find_compare_song_scores(
                    compare_data,
                    legacy_song_id,
                    chart_set='legacy',
                )
            )
        score_rows = _add_calculated_info_ratings(song, score_rows)
        notice = portal.fallback_notice(compare_data)
        if cache_error is not None:
            cache_notice = f'网络查询失败，当前显示最近缓存：{portal.format_error(cache_error)}'
            notice = f'{notice} {cache_notice}'.strip()
            credential_hint = portal.credential_error_hint(cache_error, selected_region)
            if credential_hint:
                notice = f'{notice} {credential_hint}'
        score_rows, override_stats = score_overrides.apply_to_song_scores(
            plugin_event,
            song,
            score_rows,
            selected_region,
        )
        if override_stats['used'] or override_stats['removed']:
            override_notice = (
                f'已比较玩家录入 Single Rating：采用 {override_stats["used"]} 条覆盖，'
                f'删除 {override_stats["removed"]} 条不高于官网计算结果的录入。'
            )
            notice = f'{notice} {override_notice}'.strip()
        if not score_rows:
            no_score_notice = '你没有这首曲子的分数。'
            notice = f'{no_score_notice} {notice}'.strip()
            reply_song_card(
                plugin_event,
                song,
                info_mode=False,
                region=selected_region,
                player_data=compare_data,
                notice=notice,
            )
            return
        reply_song_card(
            plugin_event,
            song,
            info_mode=True,
            region=selected_region,
            player_data=compare_data,
            score_rows=score_rows,
            notice=notice,
        )
    except Exception as exception_object:
        selected_region = region or portal.get_bound_region(plugin_event)
        error_text = f'查询成绩失败：{portal.format_error(exception_object)}'
        credential_hint = portal.credential_error_hint(exception_object, selected_region)
        if credential_hint:
            error_text = f'{error_text}\n{credential_hint}'
        reply_text(plugin_event, error_text)
        return


def match_command(message_text: str) -> tuple[str, str]:
    source = utils.safe_str(message_text).strip()
    root_info = utils.parse_command(
        source,
        prefix_list=[],
        allow_no_prefix=True,
        command_name=root_command_name_list,
    )
    if not root_info['is_command']:
        return '', ''

    subcommand_source = root_info['command_argument']
    subcommand_info = utils.parse_command(
        subcommand_source,
        prefix_list=[],
        allow_no_prefix=True,
        command_name=subcommand_name_list,
    )
    if not subcommand_info['is_command']:
        return 'help', ''

    subcommand_key = subcommand_info['command_name']
    if subcommand_key in group_short_action_set:
        action_argument = subcommand_info['command_argument'].strip()
        if action_argument:
            return 'lagroup', f'{subcommand_key} {action_argument}'
        return 'lagroup', subcommand_key
    return subcommand_alias_dict.get(subcommand_key, ''), subcommand_info['command_argument']


def parse_action(argument: str, action_name_list: list[str]) -> tuple[str, str]:
    action_info = utils.parse_command(
        argument,
        prefix_list=[],
        allow_no_prefix=True,
        command_name=action_name_list,
    )
    if action_info['is_command']:
        return action_info['command_name'], action_info['command_argument']
    return utils.split_first_token(argument)


def handle_laglobal(plugin_event, argument: str) -> None:
    if not utils.sender_has_master_permission(plugin_event):
        reply_text(plugin_event, '权限不足，只有骰主或本插件配置管理员可以使用。')
        return
    global_config = utils.load_global_config()
    action, value = parse_action(argument, ['status', 'debug', 'master', 'off', 'on'])
    if action in ['', 'status']:
        reply_text(
            plugin_event,
            'LanotaPlugin 全局状态：\n'
            f'启用：{"ON" if global_config.get("global_enable_switch", True) else "OFF"}\n'
            f'调试：{"ON" if global_config.get("global_debug_mode_switch", False) else "OFF"}\n'
            f'本插件管理员：{", ".join(utils.get_configured_master_list()) or "无"}',
        )
        return
    if action == 'on':
        global_config['global_enable_switch'] = True
    elif action == 'off':
        global_config['global_enable_switch'] = False
    elif action == 'debug':
        global_config['global_debug_mode_switch'] = value.lower() == 'on'
    elif action == 'master':
        sub_action, sub_value = parse_action(value, ['list', 'add', 'del'])
        masters = utils.get_configured_master_list()
        target_list = utils.normalize_id_list(sub_value)
        if sub_action in ['', 'list']:
            reply_text(plugin_event, f'本插件管理员：{", ".join(masters) or "无"}')
            return
        if sub_action == 'add':
            for target in target_list:
                if target not in masters:
                    masters.append(target)
            utils.set_configured_master_list(None, masters)
            reply_text(plugin_event, f'已更新全局管理员：{", ".join(masters) or "无"}')
            return
        if sub_action == 'del':
            masters = [item for item in masters if item not in target_list]
            utils.set_configured_master_list(None, masters)
            reply_text(plugin_event, f'已更新全局管理员：{", ".join(masters) or "无"}')
            return
        reply_text(plugin_event, '用法：.laglobal master list/add/del [用户ID]')
        return
    else:
        reply_text(plugin_event, '用法：.laglobal status/on/off/debug on/debug off/master list/add/del [用户ID]')
        return
    utils.save_global_config(global_config)
    reply_text(plugin_event, 'LanotaPlugin 全局配置已更新。')


def handle_labot(plugin_event, argument: str) -> None:
    if not utils.sender_has_master_permission(plugin_event):
        reply_text(plugin_event, '权限不足，只有骰主或本插件配置管理员可以使用。')
        return
    bot_hash = utils.get_bot_hash_from_event(plugin_event)
    bot_config = utils.load_bot_config(bot_hash)
    action, value = parse_action(
        argument,
        ['status', 'master', 'image', 'songcard', 'card', '歌曲卡片', 'plain', 'text', '纯文本', 'off', 'on'],
    )
    if action in ['', 'status']:
        reply_text(
            plugin_event,
            f'当前 Bot 开关：{"ON" if bot_config.get("bot_enable_switch", True) else "OFF"}\n'
            f'图片回复：{"ON" if bot_config.get("send_as_image", True) and not bot_config.get("plain_text_mode", False) else "OFF"}\n'
            f'歌曲 HTML 卡片：{"ON" if bot_config.get("song_card_html_enable", True) else "OFF"}\n'
            f'纯文本模式：{"ON" if is_plain_text_mode(plugin_event) else "OFF"}',
        )
        return
    if action == 'on':
        bot_config['bot_enable_switch'] = True
        utils.save_bot_config(bot_hash, bot_config)
        reply_text(plugin_event, '当前 Bot 已启用 LanotaPlugin。')
        return
    if action == 'off':
        bot_config['bot_enable_switch'] = False
        utils.save_bot_config(bot_hash, bot_config)
        reply_text(plugin_event, '当前 Bot 已停用 LanotaPlugin。')
        return
    if action == 'image':
        if value.lower() not in ['on', 'off']:
            reply_text(plugin_event, '用法：.labot image on/off')
            return
        bot_config['send_as_image'] = value.lower() == 'on'
        bot_config['plain_text_mode'] = not bot_config['send_as_image']
        utils.save_bot_config(bot_hash, bot_config)
        reply_text(plugin_event, f'当前 Bot 图片回复已{"开启" if bot_config["send_as_image"] else "关闭"}。')
        return
    if action in ['songcard', 'card', '歌曲卡片']:
        if value.lower() not in ['on', 'off']:
            reply_text(plugin_event, '用法：.labot songcard on/off')
            return
        bot_config['song_card_html_enable'] = value.lower() == 'on'
        utils.save_bot_config(bot_hash, bot_config)
        state_text = '开启' if bot_config['song_card_html_enable'] else '关闭'
        reply_text(plugin_event, f'歌曲 HTML 卡片已{state_text}。关闭时 song/info 使用兼容文本排版。')
        return
    if action in ['plain', 'text', '纯文本']:
        if value.lower() not in ['on', 'off']:
            reply_text(plugin_event, '用法：.labot plain on/off')
            return
        bot_config['plain_text_mode'] = value.lower() == 'on'
        bot_config['send_as_image'] = not bot_config['plain_text_mode']
        utils.save_bot_config(bot_hash, bot_config)
        reply_text(plugin_event, f'当前 Bot 纯文本模式已{"开启" if bot_config["plain_text_mode"] else "关闭"}。')
        return
    if action == 'master':
        sub_action, sub_value = parse_action(value, ['list', 'add', 'del'])
        masters = utils.get_configured_master_list()
        target_list = utils.normalize_id_list(sub_value)
        if sub_action in ['', 'list']:
            reply_text(plugin_event, f'本插件全局管理员：{", ".join(masters) or "无"}')
            return
        if sub_action == 'add':
            for target in target_list:
                if target not in masters:
                    masters.append(target)
            utils.set_configured_master_list(bot_hash, masters)
            reply_text(plugin_event, f'已更新全局管理员：{", ".join(masters) or "无"}')
            return
        if sub_action == 'del':
            masters = [item for item in masters if item not in target_list]
            utils.set_configured_master_list(bot_hash, masters)
            reply_text(plugin_event, f'已更新全局管理员：{", ".join(masters) or "无"}')
            return
    reply_text(
        plugin_event,
        '用法：.labot status/on/off/image on/off/songcard on/off/plain on/off；'
        '管理员请用 .laglobal master list/add/del [用户ID]',
    )


def handle_lagroup(plugin_event, argument: str) -> None:
    """当前群开关管理。"""
    action, _value = parse_action(argument, ['off', 'on'])
    if not utils.sender_has_group_management_permission(plugin_event):
        reply_text(plugin_event, '权限不足，只有群主、群管、骰主或本插件配置管理员可以管理当前群开关。')
        return

    bot_hash = utils.get_bot_hash_from_event(plugin_event)
    current_group_id = utils.get_group_id_from_event(plugin_event)

    if action == 'off':
        if not current_group_id:
            reply_text(plugin_event, '当前不在群聊场景中，无法关闭群级开关。')
            return
        utils.add_disabled_group(bot_hash, current_group_id)
        reply_text(plugin_event, f'已在当前群（{current_group_id}）禁用 LanotaPlugin 普通命令。')
        return

    if action == 'on':
        if not current_group_id:
            reply_text(plugin_event, '当前不在群聊场景中，无法开启群级开关。')
            return
        utils.remove_disabled_group(bot_hash, current_group_id)
        reply_text(plugin_event, f'已在当前群（{current_group_id}）重新启用 LanotaPlugin 普通命令。')
        return

    reply_text(plugin_event, '用法：/la on 或 /la off')



def handle_fullcheck(plugin_event, argument: str = '') -> None:
    """对本地曲库做包含新增歌曲在内的全量检测；仅 apply 时实际写入。"""
    if not utils.sender_has_master_permission(plugin_event):
        reply_text(plugin_event, '权限不足，只有管理员可以执行全量检测。')
        return
    action_text = str(argument or '').strip().lower()
    if action_text in {'', 'detect', 'check', 'preview', '检测', '检查', '预览'}:
        apply_edit = False
    elif action_text in {'apply', '执行', '确认'}:
        apply_edit = True
    else:
        reply_text(plugin_event, '用法：/la fullcheck 或 /la fullcheck apply')
        return
    reply_text(
        plugin_event,
        '开始对数据库全部歌曲进行全量检测（含新增歌曲检查），请稍候……'
        if not apply_edit
        else '开始对数据库全部歌曲进行全量覆盖写入（含新增歌曲补充），请稍候……',
    )
    try:
        result = crawler.run_full_check(apply=apply_edit)
        report = function.build_full_check_report(result)
        reply_large_text(plugin_event, report)
    except Exception as exception_object:
        reply_text(
            plugin_event,
            f'全量检测过程中发生错误：{type(exception_object).__name__}: {exception_object}',
        )


def handle_update(plugin_event, argument: str = '') -> None:
    if not utils.sender_has_master_permission(plugin_event):
        reply_text(plugin_event, '权限不足，只有 OlivaDiceCore 骰主或本插件配置管理员可以更新曲库。')
        return
    argument_text = str(argument or '').strip().lower()
    fullcheck_action, fullcheck_argument = parse_action(argument_text, ['full', 'fullcheck', 'all', '全量', '全量检测'])
    if fullcheck_action in {'full', 'fullcheck', 'all', '全量', '全量检测'}:
        handle_fullcheck(plugin_event, fullcheck_argument)
        return
    reply_text(plugin_event, '开始更新乐曲数据，请稍候...')
    try:
        result = crawler.run_update()
        reply_text(plugin_event, function.build_update_report(result))
    except Exception as exception_object:
        reply_text(plugin_event, f'更新过程中发生错误：{type(exception_object).__name__}: {exception_object}')


def handle_sync(plugin_event, argument: str) -> None:
    """由骰主预览或执行 Wiki Songs 页面同步。"""
    if not utils.sender_has_master_permission(plugin_event):
        reply_text(plugin_event, '权限不足，只有 OlivaDiceCore 骰主或本插件配置管理员可以同步 Wiki。')
        return
    action_text = argument.strip().lower()
    apply_edit = action_text in {'apply', '执行', '确认'} or 'apply' in action_text.split()
    add_only = 'add-only' in action_text.split() or '仅新增' in action_text
    global_config = utils.load_global_config()
    username = str(global_config.get('wiki_sync_username', '')).strip()
    password = str(global_config.get('wiki_sync_bot_password', '')).strip()
    if apply_edit and (not username or not password):
        reply_text(
            plugin_event,
            '尚未配置 Wiki 账号。请在 plugin/data/LanotaPlugin/global_config.json 中填写 '
            'wiki_sync_username 与 wiki_sync_bot_password。',
        )
        return

    mode_text = '实际编辑' if apply_edit else '预览'
    reply_text(plugin_event, f'开始进行 Songs {mode_text}，请稍候……')
    try:
        from . import wiki_sync

        result = wiki_sync.run_sync(
            username=username,
            password=password,
            apply=apply_edit,
            add_only=add_only,
            summary=str(global_config.get('wiki_sync_edit_summary', '')).strip()
            or config.default_global_config['wiki_sync_edit_summary'],
            timeout=max(config.api_timeout_seconds, 30),
            output_dir=utils.get_plugin_data_dir(),
        )
        if not apply_edit:
            reply_large_text(
                plugin_event,
                'Songs 同步预览（仅显示差异）：\n' + str(result.get('difference_text', '没有差异。')),
            )
        else:
            reply_text(
                plugin_event,
                f'Songs 同步完成：已编辑 Wiki\n'
                f'新增歌曲：{result.get("added", 0)}\n'
                f'已有字段变化：{result.get("changed", 0)}\n'
                f'无效候选页：{result.get("invalid", 0)}',
            )
    except Exception as exception_object:
        reply_text(plugin_event, f'Songs 同步失败：{type(exception_object).__name__}: {exception_object}')


def handle_cover(plugin_event, argument: str) -> None:
    """由骰主管理本地曲绘缓存。"""
    if not utils.sender_has_master_permission(plugin_event):
        reply_text(plugin_event, '权限不足，只有 OlivaDiceCore 骰主或本插件配置管理员可以管理曲绘缓存。')
        return
    action_text = argument.strip().lower()
    if action_text in {'', 'status', '状态'}:
        cache_status = crawler.get_cover_cache_status()
        reply_text(
            plugin_event,
            f'本地曲绘缓存：{cache_status["cached"]}/{cache_status["total"]} 张\n'
            f'曲绘文件数量：{cache_status["images"]}\n'
            f'已校正曲绘：{cache_status["adjusted_images"]}\n'
            # f'预置目录：{cache_status["seed_dir"]}\n运行期目录：{cache_status["runtime_dir"]}\n'
            '使用 /la cover update 下载缺失曲绘，/la cover resize 批量校正，或 /la cover force 强制重下。',
        )
        return
    if action_text in {'resize', 'adjust', 'stretch', '校正', '修复', '拉伸'}:
        if not utils.sender_is_core_master(plugin_event):
            reply_text(plugin_event, '权限不足，只有 OlivaDiceCore 骰主可以批量校正曲绘。')
            return
        reply_text(plugin_event, '开始校正本地曲绘，已有校正缓存会自动跳过，请稍候……')

        def report_adjustment_progress(current: int, total: int, result: dict[str, Any]) -> None:
            if current == total or current % 25 == 0:
                utils.info_log(
                    getattr(utils, 'runtime_proc', None),
                    f'曲绘校正进度 {current}/{total}，新增 {result["adjusted"]}，失败 {result["failed"]}',
                )

        try:
            result = crawler.run_cover_adjustment(progress_callback=report_adjustment_progress)
            reply_text(
                plugin_event,
                f'曲绘校正完成！\n'
                f'扫描原图：{result.get("total", 0)}\n'
                f'本次校正：{result.get("adjusted", 0)}\n'
                f'已有缓存：{result.get("cached", 0)}\n'
                f'非 2:1 原图：{result.get("unchanged", 0)}\n'
                f'失败：{result.get("failed", 0)}\n'
                f'目录：{result.get("cover_dir", "")}',
            )
        except Exception as exception_object:
            reply_text(plugin_event, f'曲绘校正失败：{type(exception_object).__name__}: {exception_object}')
        return
    if action_text not in {'update', '更新', 'download', '下载', 'force', '强制'}:
        reply_text(plugin_event, '用法：/la cover status、/la cover update、/la cover resize、/la cover force')
        return

    force = action_text in {'force', '强制'}
    reply_text(plugin_event, '开始下载曲绘。首次下载可能耗时较长，请稍候……')

    def report_progress(current: int, total: int, downloaded: int, failed: int) -> None:
        if current == total or current % 25 == 0:
            utils.info_log(
                getattr(utils, 'runtime_proc', None),
                f'曲绘下载进度 {current}/{total}，本次下载 {downloaded}，失败 {failed}',
            )

    try:
        result = crawler.run_cover_update(force=force, progress_callback=report_progress)
        reply_text(
            plugin_event,
            f'曲绘缓存更新完成！\n'
            f'曲库歌曲：{result.get("total", 0)}\n'
            f'本次下载：{result.get("downloaded", 0)}\n'
            f'已有缓存：{result.get("cached", 0)}\n'
            f'失败：{result.get("failed", 0)}\n'
            f'目录：{result.get("cover_dir", "")}',
        )
    except Exception as exception_object:
        reply_text(plugin_event, f'曲绘下载失败：{type(exception_object).__name__}: {exception_object}')


def handle_today(plugin_event) -> None:
    user_id = utils.get_sender_id_from_event(plugin_event)
    linked_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    song = function.get_user_today_song(user_id, linked_bot_hash)
    if not song:
        reply_text(plugin_event, '今日乐曲获取失败，可能是乐曲数据未加载。')
        return
    nickname = utils.get_sender_name_from_event(plugin_event) or f'玩家{user_id}'
    reply_song_detail(plugin_event, f'[{nickname}]的今日乐曲：', song)


def handle_random(plugin_event, argument: str) -> None:
    song_data = function.load_song_data()
    if not song_data:
        reply_text(plugin_event, '没有可用的乐曲数据。')
        return

    filtered_songs = song_data
    title = '随机乐曲'
    sub_command, sub_argument = parse_action(
        argument.lower(),
        ['include', 'contain', 'except', 'level', 'exc', *function.category_map.keys()],
    )
    if sub_command:
        sub_parts = sub_argument.split()
        if sub_command in ['except', 'exc'] and sub_argument:
            exclude_categories = sorted({function.category_map[item] for item in sub_parts if item in function.category_map})
            filtered_songs = [song for song in song_data if song.get('category') not in exclude_categories]
            title = f'随机乐曲(排除{", ".join(exclude_categories)})'
        elif sub_command in ['include', 'contain'] and sub_argument:
            include_categories = sorted({function.category_map[item] for item in sub_parts if item in function.category_map})
            filtered_songs = [song for song in song_data if song.get('category') in include_categories]
            title = f'随机乐曲(包含{", ".join(include_categories)})'
        elif sub_command == 'level' and sub_argument:
            level = sub_argument.split()[0]
            filtered_songs = function.get_songs_by_level(song_data, level)
            title = f'随机乐曲(难度{level})'
        elif sub_command in function.category_map:
            category = function.category_map[sub_command]
            filtered_songs = function.get_songs_by_category(song_data, category)
            title = f'随机乐曲({category})'
    if not filtered_songs:
        reply_text(plugin_event, '没有找到符合条件的乐曲。')
        return
    selected = filtered_songs[function.random_index(len(filtered_songs) - 1)]
    reply_song_detail(plugin_event, f'{title}:', selected)


def _find_alias_target(search_term: str, songs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """别名写操作只接受唯一标识或完整原名，不启动模糊搜索。"""
    source = str(search_term or '').strip()
    source_casefold = source.casefold()
    direct_matches = []
    for song in songs:
        legacy = song.get('Legacy', {})
        identifiers = {
            str(song.get('chapter', '')).strip().casefold(),
            str(song.get('id', '')).strip().casefold(),
            str(song.get('official_songid', '')).strip().casefold(),
            str(song.get('title', '')).strip().casefold(),
        }
        if isinstance(legacy, dict):
            identifiers.add(str(legacy.get('official_songid', '')).strip().casefold())
        identifiers.discard('')
        if source_casefold in identifiers:
            direct_matches.append(song)
    if direct_matches:
        return direct_matches

    normalized_source = re.sub(r'[^\w\u4e00-\u9fff]+', '', source_casefold)
    if not normalized_source:
        return []
    return [
        song for song in songs
        if re.sub(r'[^\w\u4e00-\u9fff]+', '', str(song.get('title', '')).casefold()) == normalized_source
    ]


def handle_alias(plugin_event, argument: str) -> None:
    if not argument.strip():
        reply_text(
            plugin_event,
            '用法：\n/la alias add <别名>/<章节号、ID或完整原名>'
            '\n/la alias del <别名>\n/la alias show <章节号、ID、别名或曲名>',
        )
        return
    action, remaining = parse_action(argument, ['show', 'add', 'del'])
    action = action.lower()
    if action != 'show' and not utils.is_alias_group_allowed(plugin_event):
        reply_text(plugin_event, '权限不足，只有白名单群可以使用 alias add/del。')
        return

    alias_data = function.load_alias_data()
    song_data = function.load_song_data()
    all_titles = {str(song.get('title', '')).lower() for song in song_data}
    if action == 'add':
        if '/' not in remaining:
            reply_text(plugin_event, '格式错误，请使用 <别名>/<章节号、ID或完整原名> 格式。')
            return
        alias, search_term = [item.strip() for item in remaining.split('/', 1)]
        matched_songs = _find_alias_target(search_term, song_data)
        if not matched_songs:
            reply_text(
                plugin_event,
                f'没有找到章节号、ID或完整原名为[{search_term}]的唯一乐曲。'
                '请先使用 /la song <搜索词> 查到准确标识。',
            )
            return
        if len(matched_songs) > 1:
            reply_text(plugin_event, '该标识对应多首歌曲，无法唯一确定；请改用歌曲 ID 或官方 songId。')
            return
        std_name = str(matched_songs[0].get('title', ''))
        if alias.lower() in all_titles:
            reply_text(plugin_event, f'[{alias}]已经是乐曲原名，不能作为别名。')
            return
        for existing_std_name, aliases in alias_data.items():
            if alias in aliases:
                reply_text(plugin_event, f'别名[{alias}]已经被[{existing_std_name}]使用。')
                return
        alias_data.setdefault(std_name, [])
        if alias not in alias_data[std_name]:
            alias_data[std_name].append(alias)
            function.save_alias_data(alias_data)
        reply_text(plugin_event, f'成功为[{std_name}]添加别名[{alias}]。')
        return

    if action == 'del':
        alias = remaining.split('/')[0].strip()
        deleted = False
        for aliases in alias_data.values():
            if alias in aliases:
                aliases.remove(alias)
                deleted = True
                break
        if deleted:
            function.save_alias_data(alias_data)
            reply_text(plugin_event, f'成功删除别名[{alias}]。')
        else:
            reply_text(plugin_event, f'未找到别名[{alias}]。')
        return

    if action == 'show':
        matched_songs, _match_type, total_count = function.find_song_by_search_term(remaining.strip(), song_data, alias_data)
        if not matched_songs:
            reply_text(plugin_event, f'没有找到章节号、ID、别名或原名为[{remaining}]的乐曲。')
            return
        if total_count == 1:
            std_name = str(matched_songs[0].get('title', ''))
            aliases = alias_data.get(std_name, [])
            if not aliases:
                reply_text(plugin_event, f'乐曲[{std_name}]目前没有设置别名。')
            else:
                reply_text(plugin_event, f'乐曲[{std_name}]的别名({len(aliases)}个):\n' + '\n'.join(f'{i + 1}. {a}' for i, a in enumerate(aliases)))
            return
        
        reply_text(
            plugin_event,
            render_song_list(
                f'匹配到多首歌曲({total_count}首)，请使用更精确的章节号、ID、别名或完整原名：',
                matched_songs,
            ),
            max_chars=config.search_image_max_chars,
        )
        return
    reply_text(plugin_event, '无效操作，只能使用 add/del/show。')


def render_song_list(header: str, songs: list[dict[str, Any]], start_index: int = 1) -> str:
    lines = [header]
    for index, song in enumerate(songs, start_index):
        lines.append(f'{index}. {song.get("chapter")} - {song.get("title")} (ID: {song.get("id")})')
    return '\n'.join(lines)


def _search_songs(plugin_event, search_term: str, view_mode: str) -> None:
    """执行歌曲搜索，并根据 view_mode 打开歌曲或查分卡片。"""
    song_data = function.load_song_data()
    alias_data = function.load_alias_data()
    matched_songs, match_type, total_count = function.find_song_by_search_term(
        search_term,
        song_data,
        alias_data,
        len(song_data),
    )
    if not matched_songs:
        reply_text(plugin_event, f'没有找到与[{search_term}]相关的乐曲。')
        return

    if total_count == 1:
        clear_search_session(plugin_event)
        if view_mode == 'info':
            reply_song_info(plugin_event, matched_songs[0])
        else:
            reply_song_card(plugin_event, matched_songs[0])
        return

    save_search_session(plugin_event, matched_songs, match_type, view_mode=view_mode)
    formatted_results, _total_pages, _page_index = function.format_search_results_with_pagination(
        matched_songs,
        0,
        config.result_page_size,
    )
    action_name = '查分' if view_mode == 'info' else '查看歌曲信息'
    header = (
        # f'通过搜索词[{search_term}]进行[{match_type}]找到匹配的乐曲({total_count}首)，'
        f'找到匹配的乐曲({total_count}首)，'
        f'请输入序号{action_name}，或输入“结束”退出：\n'
    )
    reply_text(plugin_event, header + formatted_results, max_chars=config.search_image_max_chars)


def handle_song(plugin_event, argument: str) -> None:
    raw_arg = argument.strip()
    if not raw_arg:
        reply_text(plugin_event, '用法：/la song <搜索词>（只显示歌曲信息）')
        return
    _search_songs(plugin_event, raw_arg, 'song')


def handle_info(plugin_event, argument: str) -> None:
    raw_arg = argument.strip()
    region, remaining = portal.split_region_argument(raw_arg, greedy=True)
    if region is not None:
        raw_arg = remaining
    if not raw_arg:
        reply_text(plugin_event, '用法：/la info <搜索词>，或 /la info cn <搜索词>（查询国服成绩）')
        return

    song_data = function.load_song_data()
    alias_data = function.load_alias_data()
    matched_songs, match_type, total_count = function.find_song_by_search_term(
        raw_arg,
        song_data,
        alias_data,
        len(song_data),
    )
    if not matched_songs:
        reply_text(plugin_event, f'没有找到与[{raw_arg}]相关的乐曲。')
        return
    if total_count == 1:
        clear_search_session(plugin_event)
        reply_song_info(plugin_event, matched_songs[0], region=region)
        return

    save_search_session(plugin_event, matched_songs, match_type, view_mode='info', region=region)
    formatted_results, _total_pages, _page_index = function.format_search_results_with_pagination(
        matched_songs,
        0,
        config.result_page_size,
    )
    region_hint = '国服' if region == 'china' else '绑定区域'
    header = (
        f'通过搜索词[{raw_arg}]进行[{match_type}]找到匹配的乐曲({total_count}首)，'
        f'请输入序号查询{region_hint}成绩，或输入“结束”退出：\n'
    )
    reply_text(plugin_event, header + formatted_results, max_chars=config.search_image_max_chars)


def handle_artist(plugin_event, argument: str) -> None:
    search_term = argument.strip()
    if not search_term:
        reply_text(plugin_event, '用法：/la artist <曲师名>')
        return
    song_data = function.load_song_data()
    matched_artists, match_type, total_artists = function.find_artist_by_search_term(search_term, song_data, len(song_data))
    if not matched_artists:
        reply_text(plugin_event, f'没有找到与曲师[{search_term}]相关的结果。')
        return
    if total_artists > 1:
        reply_text(plugin_event, f'通过曲师关键词[{search_term}]进行[{match_type}]，找到多个曲师({total_artists}个):\n' + '\n'.join(f'{i + 1}. {artist}' for i, artist in enumerate(matched_artists)))
        return
    target_artist = matched_artists[0]
    artist_songs = [song for song in song_data if str(song.get('artist', '')).strip().lower() == target_artist.lower()]
    reply_text(plugin_event, render_song_list(f'曲师[{target_artist}]的歌曲列表（共{len(artist_songs)}首）：', artist_songs))


def handle_time(plugin_event) -> None:
    def parse_time_value(value: Any) -> int:
        try:
            minute, second = map(int, str(value).split(':'))
            return minute * 60 + second
        except Exception:
            return 0

    processed = []
    for song in function.load_song_data():
        seconds = parse_time_value(song.get('time', ''))
        if seconds > 0:
            processed.append({'song': song, 'seconds': seconds, 'time': song.get('time', '')})
    long_songs = sorted([item for item in processed if item['seconds'] > 180], key=lambda item: -item['seconds'])
    short_songs = sorted([item for item in processed if item['seconds'] < 120], key=lambda item: item['seconds'])
    lines = ['时长统计：\n']
    lines.append(f'长于3分钟的乐曲(共{len(long_songs)}首，时长降序):')
    lines.extend(f'{i + 1}. {item["song"].get("title")} -|- {item["time"]} (Chapter: {item["song"].get("chapter")})' for i, item in enumerate(long_songs))
    lines.append(f'\n短于2分钟的乐曲(共{len(short_songs)}首，时长升序):')
    lines.extend(f'{i + 1}. {item["song"].get("title")} -|- {item["time"]} (Chapter: {item["song"].get("chapter")})' for i, item in enumerate(short_songs))
    reply_large_text(plugin_event, '\n'.join(lines))


def handle_all(plugin_event) -> None:
    song_data = function.load_song_data()
    counts = {}
    for song in song_data:
        category = song.get('category', 'unknown')
        counts[category] = counts.get(category, 0) + 1
    lines = ['Lanota曲库统计（Fandom已收录）:', f'总乐曲数量: {len(song_data)}首', '', '按分类统计:']
    for category, count in counts.items():
        lines.append(f'{function.category_name_map.get(category, category)}: {count}首')
    reply_text(plugin_event, '\n'.join(lines))


def handle_cal(plugin_event, argument: str) -> None:
    if not argument.strip():
        reply_text(plugin_event, '用法：\n/la cal harmony/tune/fail/难度/曲目\n/la cal harmony/tune/fail/物量/官方定数')
        return
    parts = argument.split('/', 4)
    if len(parts) < 5:
        reply_text(plugin_event, '参数格式错误，需要5个参数用/分隔。')
        return
    try:
        harmony, tune, fail = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        reply_text(plugin_event, '前三个参数必须是数字。')
        return
    if harmony < 0 or tune < 0 or fail < 0:
        reply_text(plugin_event, '输入的判定/物量不能为负数！')
        return

    if parts[3].lower() in ['whisper', 'acoustic', 'ultra', 'master']:
        difficulty_type = parts[3].lower()
        matched_songs, _match_type, total_count = function.find_song_by_search_term(parts[4], function.load_song_data(), function.load_alias_data())
        if not matched_songs:
            reply_text(plugin_event, f'没有找到与[{parts[4]}]相关的乐曲。')
            return
        if total_count > 1:
            reply_text(plugin_event, render_song_list(f'找到多个匹配的乐曲({total_count}首)，请使用更精确的搜索词：', matched_songs))
            return
        song = matched_songs[0]
        difficulty_value = song.get('difficulty', {}).get(difficulty_type, '未知')
        notes_value = song.get('notes', {}).get(difficulty_type, 0)
        official_constant = song.get('official_constant', {}).get(difficulty_type)
        if difficulty_value == '未知' or not notes_value or official_constant in [None, '']:
            reply_text(plugin_event, f'乐曲[{song.get("title")}]没有{difficulty_type}难度的数据。')
            return
        chapter_constants = function.load_table_data().get(str(song.get('chapter', '')), {})
        folk_constant = (
            chapter_constants.get(difficulty_type.capitalize())
            if isinstance(chapter_constants, dict)
            else None
        )
        constant_text = function.format_compact_chart_constant(
            official_constant,
            folk_constant,
            difficulty_value,
        )
        prefix = (
            f'乐曲: {song.get("title")}\n'
            f'谱面: {difficulty_type.capitalize()} {constant_text}\n'
            f'官方定数: {float(official_constant):.2f}\n'
            f'总物量: {notes_value}\n'
        )
    else:
        try:
            notes_value = int(parts[3])
        except ValueError:
            reply_text(plugin_event, '物量参数必须是数字。')
            return
        try:
            official_constant = float(parts[4])
        except ValueError:
            reply_text(plugin_event, '官方定数必须是数字，例如 15.8 或 16.5。')
            return
        if not 0 < official_constant <= 30:
            reply_text(plugin_event, '官方定数必须大于 0 且不超过 30。')
            return
        prefix = f'总物量: {notes_value}\n官方定数: {official_constant:.2f}\n'

    if notes_value <= 0:
        reply_text(plugin_event, '总物量必须大于 0。')
        return
    if harmony + tune + fail > int(notes_value):
        reply_text(plugin_event, prefix + f'当前输入总物量为：{harmony + tune + fail}，已经高于物量：{notes_value}，无法计算。')
        return
    result = b30.calculate_judgement_rating(
        harmony,
        tune,
        fail,
        int(notes_value),
        float(official_constant),
    )
    if result is None:
        reply_text(plugin_event, '输入数据无法按新版公式计算，请检查判定、物量和官方定数。')
        return
    message = prefix + f'输入判定: {harmony + tune + fail} (Harmony: {harmony}, Tune: {tune}, Fail: {fail})\n'
    if result['adjustment']:
        message += f'自动调整: Fail {fail} -> {result["fail"]} (+{result["adjustment"]})\n'
    message += (
        f'EX Score: {result["exScore"]}/{result["maxExScore"]}\n'
        f'新版分数: {int(result["score"]):,}\n'
        f'分数准度: {float(result["scoreAccuracy"]):.2f}%\n'
        f'基础 Rating: {float(result["baseRating"]):.2f}\n'
        f'Single Rating: {float(result["singleRating"]):.2f}\n'
        f'ratingPercent: {float(result["ratingPercent"]):.2f}%\n'
        f'计算核心: EX = 2×Harmony + Tune = {result["exScore"]}'
    )
    reply_text(plugin_event, message)


def handle_notes(plugin_event) -> None:
    charts = []
    for song in function.load_song_data():
        for diff_type in ['whisper', 'acoustic', 'ultra', 'master']:
            notes_value = song.get('notes', {}).get(diff_type, 0)
            difficulty_value = song.get('difficulty', {}).get(diff_type, '未知')
            try:
                notes_int = int(notes_value)
            except Exception:
                continue
            if difficulty_value != '未知':
                charts.append((notes_int, song, diff_type.capitalize(), difficulty_value))
    charts.sort(key=lambda item: -item[0])
    lines = ['物量最高的前50个谱面:']
    for index, (notes_value, song, difficulty, difficulty_value) in enumerate(charts[:50], 1):
        lines.append(f'{index}. {song.get("title")} -|- 物量{notes_value} (难度: {difficulty} {difficulty_value}, Chapter: {song.get("chapter")})')
    reply_large_text(plugin_event, '\n'.join(lines) if len(lines) > 1 else '没有找到有效的谱面数据。')


def _consume_b30_cooldown(plugin_event, region: str) -> int:
    cooldown_seconds = max(1, int(config.b30_cooldown_seconds))
    user_key = '|'.join([
        utils.get_bot_hash_from_event(plugin_event, use_linked=True),
        utils.get_sender_id_from_event(plugin_event),
        portal.normalize_region(region),
    ])
    now_time = time.monotonic()
    with b30_cooldown_lock:
        expired_keys = [
            key for key, used_at in b30_last_used.items()
            if now_time - used_at >= cooldown_seconds
        ]
        for key in expired_keys:
            b30_last_used.pop(key, None)
        last_used = b30_last_used.get(user_key)
        if last_used is not None:
            return max(1, math.ceil(cooldown_seconds - (now_time - last_used)))
        b30_last_used[user_key] = now_time
    return 0


def _append_b30_notice(card_data: dict[str, Any], notice: str) -> None:
    clean_notice = str(notice or '').strip()
    if not clean_notice:
        return
    current_notice = str(card_data.get('notice', '') or '').strip()
    card_data['notice'] = f'{current_notice} {clean_notice}'.strip()


def handle_b30(plugin_event, argument: str) -> None:
    region, remaining = portal.split_region_argument(argument)
    if remaining or (argument.strip() and region is None):
        reply_text(plugin_event, '用法：/la b30 或 /la b30 cn')
        return
    selected_region = region or portal.get_bound_region(plugin_event)
    if not selected_region:
        reply_text(plugin_event, '尚未绑定 Lanota 好友码，请先使用 /la bind <好友码>。')
        return
    nano_id = portal.get_bound_nano_id(plugin_event, selected_region)
    if not nano_id:
        region_name = portal.region_display_name(selected_region)
        bind_prefix = 'cn ' if selected_region == 'china' else ''
        reply_text(plugin_event, f'尚未绑定 Lanota {region_name}好友码，请先使用 /la bind {bind_prefix}<好友码>。')
        return

    cooldown_remaining = _consume_b30_cooldown(plugin_event, selected_region)
    if cooldown_remaining:
        minutes, seconds = divmod(cooldown_remaining, 60)
        region_name = portal.region_display_name(selected_region)
        reply_text(plugin_event, f'/la b30 在{region_name}每人 5 分钟只能使用一次，请在 {minutes}分{seconds:02d}秒后重试。')
        return

    utils.reply_message(
        plugin_event,
        f'正在生成 Lanota {portal.region_display_name(selected_region)} B30，请稍候...',
    )
    try:
        catalog = b30.build_chart_catalog()
        card_data = None
        exact_check_error = None
        reconcile_rows = []
        reconcile_score_field = 'score'
        try:
            me_data = portal.get_me(selected_region)
            is_current_account = str(me_data.get('nanoId', '')).casefold() == nano_id.casefold()
            if is_current_account:
                rating_data = portal.api_get('rating', region=selected_region)
                exact_entries = rating_data.get('best30', {}).get('entries', [])
                if isinstance(exact_entries, list) and exact_entries:
                    try:
                        scores_data = portal.api_get('scores', region=selected_region)
                        reconcile_rows = (
                            scores_data.get('songs', [])
                            if isinstance(scores_data, dict)
                            else []
                        )
                    except Exception as exception_object:
                        scores_data = None
                        exact_check_error = exception_object
                    card_data = b30.build_exact_card_data(
                        rating_data,
                        scores_data,
                        catalog,
                        selected_region,
                    )
                else:
                    exact_check_error = RuntimeError('当前账号未开放 B30/R15 明细。')
        except Exception as exception_object:
            exact_check_error = exception_object

        if card_data is None:
            compare_data, _bound_id, cache_error = portal.get_compare_data_cached(
                plugin_event,
                selected_region,
            )
            card_data = b30.build_inferred_card_data(compare_data, catalog, selected_region)
            reconcile_rows = (
                compare_data.get('songs', [])
                if isinstance(compare_data, dict)
                else []
            )
            reconcile_score_field = 'friendScore'
            using_fallback_api = bool(portal.fallback_notice(compare_data))
            if exact_check_error is not None and not using_fallback_api:
                _append_b30_notice(
                    card_data,
                    f'未使用准确 B30：{portal.format_error(exact_check_error)}',
                )
            if cache_error is not None:
                _append_b30_notice(
                    card_data,
                    f'网络查询失败，当前使用最近缓存：{portal.format_error(cache_error)}',
                )

        reconciled_count = score_overrides.reconcile_official_scores(
            plugin_event,
            catalog,
            selected_region,
            reconcile_rows,
            reconcile_score_field,
        )
        card_data = score_overrides.apply_to_card(plugin_event, card_data, catalog, selected_region)
        if reconciled_count:
            _append_b30_notice(
                card_data,
                f'已删除 {reconciled_count} 条不高于官网计算结果的玩家录入。',
            )

        fallback_text = b30.build_fallback_text(card_data)
        if is_plain_text_mode(plugin_event):
            b30.strip_internal_fields(card_data)
            reply_large_text(plugin_event, fallback_text)
            return
        b30.attach_cover_urls(card_data)
        image_path = portal.render_b30_card(card_data)
        if image_path:
            utils.reply_image(plugin_event, image_path, fallback_text)
            return
        reply_text(plugin_event, f'{fallback_text}\n\nHTML 截图失败。\n{portal.render_status_text()}')
    except Exception as exception_object:
        selected_region = selected_region or portal.get_bound_region(plugin_event)
        error_text = f'B30 查询失败：{portal.format_error(exception_object)}'
        credential_hint = portal.credential_error_hint(exception_object, selected_region)
        if credential_hint:
            error_text = f'{error_text}\n{credential_hint}'
        reply_text(plugin_event, error_text)


def handle_score(plugin_event, argument: str) -> None:
    """成绩覆盖档案命令：list/add/delete，或直接附带图片触发 OCR。"""
    text = utils.safe_str(argument).strip()
    region, remaining = portal.split_region_argument(text, greedy=True)
    selected_region = region or portal.get_bound_region(plugin_event) or 'global'
    if region is None:
        for alias, alias_region in score_overrides.REGION_ALIASES.items():
            if re.search(rf'(?<!\S){re.escape(alias)}(?!\S)', remaining, re.IGNORECASE):
                selected_region = alias_region
                break
    lower = remaining.casefold().strip()
    if lower in {'list', 'ls', '查看', '查询', ''}:
        reply_text(plugin_event, score_overrides.list_text(plugin_event, selected_region))
        return
    if lower.startswith(('delete ', 'del ', '删除 ')):
        delete_argument = remaining.split(None, 1)[1] if len(remaining.split(None, 1)) > 1 else ''
        has_delete_region = any(
            re.search(rf'(?<!\S){re.escape(alias)}(?!\S)', delete_argument, re.IGNORECASE)
            for alias in score_overrides.REGION_ALIASES
        )
        if not has_delete_region:
            delete_argument = f'{delete_argument} {selected_region}'.strip()
        reply_text(plugin_event, score_overrides.delete(plugin_event, delete_argument))
        return

    message_text = utils.get_message_text_from_event(plugin_event)
    if score_overrides.extract_image_refs(message_text):
        if not score_overrides.ocr_available():
            reply_text(
                plugin_event,
                '截图 OCR 不可用：请按 LanotaPlugin/requirements.txt 安装 RapidOCR 或 PaddleOCR；'
                '手动录入仍可正常使用。',
            )
            return
        reply_text(
            plugin_event,
            '已收到官网单曲/Rating 列表/游戏结算成绩截图，正在识别哪些歌曲并校验分数，请稍等……',
        )
        added, messages = score_overrides.process_images(plugin_event, message_text, selected_region)
        reply_text(plugin_event, f'截图录入完成：成功 {added} 条。\n' + '\n'.join(messages))
        return
    has_region_token = any(
        re.search(rf'(?<!\S){re.escape(alias)}(?!\S)', remaining, re.IGNORECASE)
        for alias in score_overrides.REGION_ALIASES
    )
    manual_argument = remaining if has_region_token else f'{remaining} {selected_region}'
    success, message = score_overrides.add_manual(plugin_event, manual_argument)
    reply_text(plugin_event, message if success else f'成绩录入失败：{message}')


def handle_bind(plugin_event, argument: str) -> None:
    region, remaining = portal.split_region_argument(argument, greedy=True)
    region = region or 'global'
    nano_id = ''.join(remaining.split()).strip()
    if not nano_id:
        utils.reply_message(plugin_event, '用法：.la bind <好友码> 或 .la bind cn <国服好友码>')
        return
    utils.reply_message(plugin_event, f'正在验证 Lanota {portal.region_display_name(region)}好友码，请稍候...')
    try:
        success, message_text = portal.bind_nano_id(plugin_event, nano_id, region=region)
        if success or message_text.startswith(('验证失败：', '国服主力 API 与备用 API 均不可用')):
            reply_message = message_text
        else:
            reply_message = f'绑定失败：{message_text}'
        utils.reply_message(plugin_event, reply_message)
    except Exception as exception_object:
        utils.error_log(None, f'Lanota 好友码绑定失败：{type(exception_object).__name__}: {exception_object}')
        utils.reply_message(plugin_event, f'绑定失败：{portal.format_error(exception_object)}')


def handle_unbind(plugin_event, argument: str) -> None:
    region, remaining = portal.split_region_argument(argument)
    if remaining or (argument.strip() and region is None):
        utils.reply_message(plugin_event, '用法：.la unbind 或 .la unbind cn')
        return
    region = region or 'global'
    try:
        success, message_text = portal.unbind_nano_id(plugin_event, region=region)
        utils.reply_message(plugin_event, message_text if success else f'解绑失败：{message_text}')
    except Exception as exception_object:
        utils.error_log(None, f'Lanota 好友码解绑失败：{type(exception_object).__name__}: {exception_object}')
        utils.reply_message(plugin_event, f'解绑失败：{portal.format_error(exception_object)}')


def handle_friend(plugin_event, argument: str) -> None:
    friend_argument = argument.strip()
    region = None
    if friend_argument:
        region, remaining = portal.split_region_argument(friend_argument, greedy=True)
        if region is None or remaining:
            reply_text(plugin_event, '用法：.la friend 或 .la friend cn')
            return

    target_regions = (region,) if region else ('global', 'china')
    bound_items = []
    for target_region in target_regions:
        nano_id = portal.get_bound_nano_id(plugin_event, target_region)
        if nano_id:
            bound_items.append((portal.region_display_name(target_region), nano_id))
    if not bound_items:
        if region:
            message_text = f'尚未绑定 Lanota {portal.region_display_name(region)}好友码。'
        else:
            message_text = '尚未绑定 Lanota 好友码。'
    elif len(bound_items) == 1:
        region_name, nano_id = bound_items[0]
        message_text = f'你绑定的 Lanota {region_name}好友码：{nano_id}'
    else:
        message_text = '你绑定的 Lanota 好友码：\n' + '\n'.join(
            f'{region_name}：{nano_id}' for region_name, nano_id in bound_items
        )
    if not utils.get_group_id_from_event(plugin_event):
        utils.reply_message(plugin_event, message_text)
        return
    user_id = utils.get_sender_id_from_event(plugin_event)
    if utils.send_private_message(plugin_event, user_id, message_text):
        utils.reply_message(plugin_event, '绑定的 Lanota 好友码已通过私聊发送。')
        return
    utils.reply_message(plugin_event, '私聊发送失败，请私聊 Bot 使用 .la friend 查询。')


def handle_user(plugin_event, argument: str) -> None:
    user_argument = argument.strip()
    normalized_argument = user_argument.casefold()
    if normalized_argument in ['friend', '好友码']:
        handle_friend(plugin_event, '')
        return
    region, remaining = portal.split_region_argument(user_argument)
    if user_argument:
        if region is None or remaining:
            reply_text(plugin_event, '用法：.la user、.la user cn 或 .la user friend')
            return
    utils.reply_message(plugin_event, '正在查询中，请稍等。')
    try:
        player_data, _nano_id, cache_error = portal.get_user_data_cached(plugin_event, region)
        if cache_error is not None:
            selected_region = region or player_data.get('_portal_region') or portal.get_bound_region(plugin_event)
            credential_hint = portal.credential_error_hint(cache_error, selected_region)
            hint_line = credential_hint or '若问题持续，请联系管理员检查主力 API 连接。'
            utils.reply_message(
                plugin_event,
                f'网络查询失败：{portal.format_error(cache_error)}\n'
                f'{hint_line}\n正在显示上次缓存。',
            )
        image_path = portal.render_player_card(player_data)
        fallback_text = portal.build_fallback_text(player_data)
        if image_path:
            utils.reply_image(plugin_event, image_path, fallback_text)
            return
        reply_text(plugin_event, f'{fallback_text}\n\nHTML 截图失败。\n{portal.render_status_text()}')
    except Exception as exception_object:
        selected_region = region or portal.get_bound_region(plugin_event)
        error_text = f'查询失败：{portal.format_error(exception_object)}'
        credential_hint = portal.credential_error_hint(exception_object, selected_region)
        if credential_hint:
            error_text = f'{error_text}\n{credential_hint}'
        reply_text(plugin_event, error_text)


def handle_category(plugin_event, argument: str) -> None:
    parts = argument.lower().split()
    if not parts:
        reply_text(plugin_event, '用法：/la category <分类或章节前缀> [min[/max]]')
        return
    category_info = utils.parse_command(
        argument.lower(),
        prefix_list=[],
        allow_no_prefix=True,
        command_name=list(function.category_map.keys()),
    )
    if category_info['is_command']:
        category_or_chapter = category_info['command_name']
        min_max = category_info['command_argument'].strip() or ('1' if len(parts) < 2 else parts[1])
    else:
        category_or_chapter = parts[0]
        min_max = '1' if len(parts) < 2 else parts[1]
    if '/' in min_max:
        min_text, max_text = min_max.split('/', 1)
    else:
        min_text, max_text = '1', min_max
    try:
        min_val, max_val = int(min_text), int(max_text)
    except ValueError:
        reply_text(plugin_event, '范围参数必须是数字。')
        return
    if min_val < 1 or min_val > max_val:
        reply_text(plugin_event, '范围参数无效。')
        return
    song_data = function.load_song_data()
    if category_or_chapter in function.category_map:
        category = function.category_map[category_or_chapter]
        filtered = [song for song in song_data if song.get('category') == category]
    else:
        filtered = [song for song in song_data if str(song.get('chapter', '')).split('-')[0].lower() == category_or_chapter]
    if not filtered:
        reply_text(plugin_event, f'没有找到分类或章节为[{category_or_chapter}]的列表。')
        return
    total = len(filtered)
    if min_val > total:
        reply_text(plugin_event, f'最小值{min_val}超过了该分类的歌曲总数({total})。')
        return
    max_val = min(max_val, total, min_val + 99)
    lines = [f'分类/章节: {category_or_chapter} (显示 {min_val}-{max_val}/{total} 首)']
    current_prefix = None
    for index, song in enumerate(filtered[min_val - 1 : max_val], min_val):
        chapter_prefix = str(song.get('chapter', '')).split('-')[0]
        if chapter_prefix != current_prefix:
            lines.append('')
            current_prefix = chapter_prefix
        lines.append(f'{index}. {song.get("chapter")} -|- {song.get("title")} (ID: {song.get("id")})')
    reply_text(plugin_event, '\n'.join(lines))


def handle_table(plugin_event, argument: str = '') -> None:
    action, _value = parse_action(argument, ['update', 'import', '更新', '导入', '转换', '刷新'])
    if action:
        if action in ['update', 'import', '更新', '导入', '转换', '刷新']:
            if not utils.sender_has_master_permission(plugin_event):
                reply_text(plugin_event, '权限不足，只有 OlivaDiceCore 骰主或本插件配置管理员可以导入 Excel 定数表。')
                return
            try:
                _success, message_text = function.import_excel_table_to_song_table()
                reply_text(plugin_event, message_text)
            except Exception as exception_object:
                reply_text(plugin_event, f'导入 Excel 定数表失败：{type(exception_object).__name__}: {exception_object}')
            return
        reply_text(plugin_event, '用法：/la table 或 /la table update')
        return

    song_data = function.load_song_data()
    table_data = function.load_table_data()
    if not song_data:
        reply_text(plugin_event, '没有可用的乐曲数据。')
        return
    if not table_data:
        reply_text(plugin_event, '未找到精确定数表，请检查定数表文件。')
        return
    song_by_chapter = {str(song.get('chapter')): song for song in song_data}
    charts = []
    for chapter, difficulties in table_data.items():
        if not isinstance(difficulties, dict):
            continue
        for difficulty_name, rating_value in difficulties.items():
            diff_type = str(difficulty_name).lower()
            if diff_type not in ['whisper', 'acoustic', 'ultra', 'master']:
                continue
            song = song_by_chapter.get(str(chapter), {'chapter': chapter, 'title': f'未找到歌曲 ({chapter})', 'id': 'Unknown', 'difficulty': {}})
            level_text = str(rating_value)
            values = []
            if '~' in level_text:
                try:
                    start, end = [float(item) for item in level_text.split('~', 1)]
                    current = start
                    while current <= end + 0.05:
                        values.append((current, current >= end - 0.05, level_text))
                        current = round(current + 0.1, 1)
                except Exception:
                    values = []
            if not values:
                try:
                    sort_value = float(level_text.rstrip('+')) + (0.5 if level_text.endswith('+') else 0)
                    values = [(sort_value, False, None)]
                except Exception:
                    continue
            for sort_value, is_range, original_range in values:
                charts.append((sort_value, original_range is not None, song, diff_type.capitalize(), rating_value, is_range, original_range))
    charts.sort(key=lambda item: (-item[0], item[1]))
    lines = ['Lanota 民间定数表']
    current_group = None
    current_exact = None
    for sort_value, _has_range, song, diff_type, rating_value, is_range, original_range in charts:
        base_level = int(sort_value)
        level_group = f'标级：{base_level}'
        if current_group != level_group:
            lines.extend(['', '==============', level_group, '=============='])
            current_group = level_group
            current_exact = None
        if current_exact != sort_value:
            lines.append(f'\n定数 {function.format_table_constant(sort_value)}：')
            current_exact = sort_value
        song_difficulty = song.get('difficulty', {}).get(diff_type.lower(), '未知')
        range_tag = f' [范围定数: {original_range}]' if is_range else ''
        lines.append(f'{song.get("chapter")} -|- {song.get("title")} (ID: {song.get("id")}) [{diff_type} {song_difficulty}]{range_tag}')
    reply_large_text(plugin_event, '\n'.join(lines))


help_categories = {
    'daily': {
        'name': '今日乐曲',
        'aliases': ['today', '今日曲'],
        'commands': [
            '/la today - 获取今日随机乐曲(每天固定)',
            '/la 今日曲 - 同上',
        ],
        'examples': [
            '/la today',
        ],
    },
    'random': {
        'name': '随机乐曲',
        'aliases': ['random', '随机'],
        'commands': [
            '/la random - 随机获取一首乐曲',
            '/la random level <难度> - 随机指定难度的乐曲',
            '/la random <分类> - 随机指定分类的乐曲',
            '/la random except <分类1> <分类2>... - 排除指定分类后随机',
            '/la random include <分类1> <分类2>... - 仅在指定分类中随机',
        ],
        'sub_commands': {
            '分类': ['main(主线)', 'side(支线)', 'expansion(曲包)', 'event(活动)', 'subscription(订阅)'],
        },
        'examples': [
            '/la random level 12',
            '/la random main',
            '/la random except event expansion',
            '/la random include main side',
        ],
    },
    'alias': {
        'name': '别名管理',
        'aliases': ['alias', '别名'],
        'commands': [
            '/la alias add <别名>/<章节号、ID或完整原名> - 添加别名',
            '/la alias del <别名> - 删除别名',
            '/la alias show <章节号、ID、别名或曲名> - 查看乐曲别名',
        ],
        'examples': [
            '/la alias show Frey',
            '/la alias add frey/1-1',
        ],
    },
    'search': {
        'name': '歌曲信息与单曲查分',
        'aliases': ['song', 'info'],
        'commands': [
            '/la song <搜索词> - 只查看歌曲信息',
            '/la info <搜索词> - 查看绑定玩家的该曲成绩（双区绑定时默认国际服）',
            '/la info cn <搜索词> - 查看国服绑定玩家的该曲成绩',
            '/la info global <搜索词> - 查看国际服绑定玩家的该曲成绩',
        ],
        'priority': [
            '1. 完全匹配章节号',
            '2. 完全匹配ID',
            '3. 完全匹配别名',
            '4. 完全匹配曲名',
            '5. 模糊匹配曲名或别名',
        ],
        'examples': [
            '/la song Frey',
            '/la info Frey',
            '/la info cn Frey',
        ],
    },
    'artist': {
        'name': '曲师查询',
        'aliases': ['artist', '曲师'],
        'commands': [
            '/la artist <曲师名> - 按曲师查歌曲',
            '/la 曲师 <曲师名> - 同上',
        ],
        'priority': [
            '1. 先进行曲师名精确匹配（忽略大小写）',
            '2. 无精确结果时再进行曲师名模糊匹配（忽略大小写）',
            '3. 匹配到唯一曲师后，返回该曲师名忽略大小写完全匹配的全部歌曲（不分页）',
        ],
        'examples': [
            '/la artist Tiny',
            '/la 曲师 karasu',
        ],
    },
    'calculate': {
        'name': '单曲rating计算功能',
        'aliases': ['cal', '计算', 'calculate'],
        'commands': [
            '/la cal harmony数目/tune数目/fail数目/难度/曲目 - 使用曲目官方定数计算新版 Rating',
            '/la cal harmony数目/tune数目/fail数目/物量/官方定数 - 直接计算新版 Rating',
        ],
        'priority': [
            '1. 前三个参数必须是数字',
            '2. 难度可以是: Whisper, Acoustic, Ultra, Master',
            '3. 直接计算时最后一项必须是官方定数，例如 15.8 或 16.5',
            '4. 如果输入的物量之和不正确，将自动补到fail数目',
        ],
        'examples': [
            '/la cal 900/300/50/Master/8-6',
            '/la cal 900/300/50/2000/16.5',
        ],
    },
    'category': {
        'name': '分类查询',
        'aliases': ['category', '分类', 'cate'],
        'commands': [
            '/la category <分类> [min[/max]] - 显示指定分类的歌曲',
            '/la cate <分类> [min[/max]] - 同上',
        ],
        'sub_commands': {
            '分类': ['main', 'side', 'expansion', 'event', 'subscription', '章节前缀(如0、1、inf)'],
        },
        'examples': [
            '/la category 0 5 - 显示第0章前5首',
            '/la category x - 显示分类x的所有曲目(最多100首)',
            '/la category inf 101/200 - 显示inf分类的第101-200首',
        ],
    },
    'account': {
        'name': '用户相关',
        'aliases': ['user', 'bind', '账号', '绑定', '用户'],
        'commands': [
            '/la bind <好友码> - 绑定自己的国际服 Lanota 好友码',
            '/la bind cn <好友码> - 绑定自己的国服 Lanota 好友码',
            '/la unbind - 解除国际服好友码绑定',
            '/la unbind cn - 解除国服好友码绑定',
            '/la user - 查询绑定玩家的国际服状态卡片',
            '/la user cn - 查询绑定玩家的国服状态卡片',
            '/la friend - 私聊查询当前绑定的国际服/国服好友码',
            '/la friend cn - 私聊查询当前绑定的国服好友码',
            '/la user friend - .la friend 的兼容写法',
            '/la b30 - 查询国际服优先的 B30；国际服与国服分别计算 5 分钟冷却',
            '/la b30 cn - 查询国服 B30',
        ],
        'priority': [
            '注：如果只绑定了国服好友码，所有 cn 均可忽略',
        ],
        'examples': [
            '/la bind <好友码>',
            '/la bind cn <好友码>',
            '/la unbind',
            '/la unbind cn',
            '/la user',
            '/la user cn',
            '/la friend',
            '/la friend cn',
        ],
    },
    'score': {
        'name': '成绩录入与覆盖',
        'aliases': ['score', '成绩', '录入', '覆盖'],
        'commands': [
            '/la score <曲名> <难度> <单曲Rating> - 手动录入当前绑定区服成绩',
            '/la score global <曲名> <难度> <单曲Rating> - 手动录入国际服成绩',
            '/la score cn <曲名> <难度> <单曲Rating> - 手动录入国服成绩',
            '/la score list - 查看当前绑定区服的录入成绩',
            '/la score global list - 查看国际服录入成绩',
            '/la score cn list - 查看国服录入成绩',
            '/la score delete <序号> - 删除录入成绩',
            '/la score delete all cn - 清空国服录入成绩',
            '/la score delete all global - 清空国际服录入成绩',
            '/la score + 官网单曲/Rating 列表/4.0+ 游戏结算截图 - 自动 OCR 识别，可一次发送多张图片',
        ],
        'priority': [
            '官网单曲图至少包含曲名、难度标签和底部“单曲 RATING”数值；Rating 列表图需保留每行曲名、难度、Rating% 和右侧单曲 Rating；两类都支持长截图。',
            '游戏结算图至少包含曲名、难度和底部七位分数；展开判定详情时会同时严格校验 H/T/F 与总物量。',
            '只显示分数的 4.0+ 结算图会按曲目物量校验分数格式，通过后反推准度与 Single Rating。',
            '录入值只在其 Single Rating 高于官网值或官网记录格式异常时覆盖；确认后会自动清理较低录入。',
            '未写区服时优先使用当前绑定区服；只绑定国服时默认录入、查看和删除国服档案。',
        ],
        'examples': [
            '/la score The Nightfall will be Conce... master 17.70',
            '/la score cn Immaculate master 18.18',
            '/la score list',
            '/la score delete 1',
        ],
    },
    'stats': {
        'name': '其它功能',
        'aliases': ['other', '其它'],
        'commands': [
            '/la time - 显示长于3分钟和短于2分钟的乐曲列表',
            '/la all - 显示曲库统计信息',
            '/la notes - 物量最多的前50个谱面',
            '/la ritmo - 显示里莫绝赞昏睡时间',
        ],
        'examples': [
            '/la time',
            '/la all',
            '/la notes',
            '/la b30',
            '/la b30 cn',
            '/la ritmo',
        ],
    },
    'table': {
        'name': '定数表',
        'aliases': ['table', '定数表'],
        'commands': [
            '/la table - 按定数从高到低显示所有谱面',
            '/la 定数表 - 同上',
            '/la table update - 从 Excel 生成定数表 JSON（仅骰主/插件管理员）',
        ],
        'priority': [
            '将唯一的 .xlsx 或 .xlsm 定数表放入 plugin/data/LanotaPlugin/excel_table/。',
            '执行后生成并覆盖 plugin/data/LanotaPlugin/SongList/song_table.json。',
            '权限：仅 OlivaDiceCore 骰主或本插件配置管理员可执行更新。',
        ],
        'priority_title': '说明',
        'examples': [
            '/la table',
            '/la table update',
        ],
    },
    'color': {
        'name': '背景色设置',
        'aliases': ['color', '设置背景色'],
        'commands': [
            '/la color <色号> - 设置消息背景颜色',
            '/la color default - 重置为默认背景色',
            '/la confirm - 确认当前背景色变更',
            '/la deny - 取消当前背景色变更',
        ],
        'examples': [
            '/la color #1f1e33 - 设置背景色为#1f1e33',
            '/la color default - 重置为默认背景色',
            '/la confirm',
            '/la deny',
        ],
    },
    'manage': {
        'name': '插件管理',
        'aliases': ['manage', '管理', 'on', 'off', 'bot', 'global'],
        'commands': [
            '/la off - 在当前群关闭普通命令',
            '/la on - 在当前群开启普通命令',
            '/la bot status/on/off - 查看或修改当前 Bot 开关',
            '/la bot songcard on/off - 开关 song/info HTML 卡片（默认开启，关闭后使用兼容文本排版）',
            '/la global status/on/off - 查看或修改全局开关',
            '/la update - 更新本地曲库数据（仅骰主）',
            '/la fullcheck - 全量检测 Fandom 与本地差异及新增歌曲（不写入，仅骰主）',
            '/la fullcheck apply - 全量覆盖 Fandom 数据（仅骰主）',
            '/la sync - 预览 Wiki Songs 页面同步（仅骰主）',
            '/la sync apply - 实际同步 Wiki Songs 页面（仅骰主）',
            '/la cover status - 查看本地曲绘缓存（仅骰主）',
            '/la cover update - 下载缺失曲绘（仅骰主）',
            '/la cover resize - 校正全部 2:1 曲绘，已有结果跳过（仅骰主）',
        ],
        'priority': [
            '1. /la on 和 /la off 需要群主、群管、骰主或本插件管理员',
            '2. bot/global/update/fullcheck 需要骰主或本插件管理员',
            '3. 被关闭的群仍可使用 /la on 重新开启',
        ],
        'examples': [
            '/la off',
            '/la on',
            '/la update',
            '/la fullcheck',
            '/la fullcheck apply',
            '/la sync',
            '/la sync apply',
            '/la cover update',
            '/la cover resize',
            '/la table update',
        ],
    },
}


def handle_help(plugin_event, argument: str) -> None:
    category = argument.strip().lower()
    if not category:
        lines = [
            'Lanota 机器人使用帮助',
            '══════════════',
            '输入以下分类指令查看详细帮助：',
        ]
        for help_category in help_categories.values():
            lines.append(f'- /la help {help_category["aliases"][0]} - {help_category["name"]}')
        lines.extend(
            [
                '══════════════',
                '输入 /la help <分类> 查看详细帮助',
                '示例: /la help random',
            ]
        )
        reply_text(plugin_event, '\n'.join(lines))
        return

    matched_category = None
    for help_category in help_categories.values():
        if category in [alias.lower() for alias in help_category['aliases']]:
            matched_category = help_category
            break

    if matched_category is None:
        reply_text(plugin_event, '未找到该分类，请输入 /la help 查看所有分类。')
        return

    lines = [
        f'【{matched_category["name"]}】',
        '══════════════',
        '命令:',
        *matched_category['commands'],
    ]

    if 'sub_commands' in matched_category:
        lines.extend(['', '可用子命令:'])
        for key, values in matched_category['sub_commands'].items():
            lines.append(f'{key}: {", ".join(values)}')

    if 'priority' in matched_category:
        priority_title = matched_category.get('priority_title', '匹配优先级')
        lines.extend(['', f'{priority_title}:', *matched_category['priority']])

    if matched_category['examples']:
        lines.extend(['', '示例:', *matched_category['examples']])

    lines.extend(
        [
            '══════════════',
            '输入 /la help 查看主菜单',
        ]
    )
    reply_text(plugin_event, '\n'.join(lines))


def handle_ritmo(plugin_event) -> None:
    start_date = datetime.date(2021, 9, 7)
    today = datetime.date.today()
    total_days = (today - start_date).days
    current = start_date
    years = 0
    while True:
        try:
            next_year = datetime.date(current.year + 1, current.month, current.day)
        except ValueError:
            next_year = datetime.date(current.year + 1, 2, 28)
        if next_year <= today:
            years += 1
            current = next_year
        else:
            break
    months = 0
    while True:
        try:
            next_month = datetime.date(current.year + (1 if current.month == 12 else 0), 1 if current.month == 12 else current.month + 1, current.day)
        except ValueError:
            break
        if next_month <= today:
            months += 1
            current = next_month
        else:
            break
    days = (today - current).days
    reply_text(plugin_event, f'【里莫绝赞昏睡时间】\n\n昏睡日期: 2021年9月7日\n今天日期: {today.year}年{today.month}月{today.day}日\n\n已经过去:\n{years}年{months}月{days}日\n总共: {total_days}天\n让我们看看可爱的小里莫\n什么时候才能睡醒吧~')


def handle_color(plugin_event, argument: str) -> None:
    user_id = utils.get_sender_id_from_event(plugin_event)
    linked_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    user_data = function.load_user_data(linked_bot_hash)
    user_info = user_data.setdefault(user_id, {})
    if argument.strip().lower() == 'default':
        user_info['event'] = 'changing_bgcolor'
        user_info['temp_bgcolor'] = 'default'
        function.save_user_data(user_data, linked_bot_hash)
        reply_text(plugin_event, '你确定要将背景色重置为默认颜色吗？请输入 /la confirm 确认或 /la deny 取消。')
        return
    if not re.match(r'^#?[0-9a-fA-F]{6}$', argument.strip()):
        reply_text(plugin_event, '请输入正确的色号格式，例如 #1f1e33；或使用 /la color default 重置。')
        return
    color_code = argument.strip().lstrip('#').lower()
    user_info['event'] = 'changing_bgcolor'
    user_info['temp_bgcolor'] = color_code
    user_info.setdefault('previous_bgcolor', user_info.get('bg_color', 'f7dbff'))
    user_info['bg_color'] = color_code
    function.save_user_data(user_data, linked_bot_hash)
    reply_text(
        plugin_event,
        f'当前预览背景色: #{color_code}，可以随便输入命令预览背景色。'
        '请输入 /la confirm 确认或 /la deny 取消。',
    )


def handle_confirm_or_deny(plugin_event, confirm: bool) -> None:
    user_id = utils.get_sender_id_from_event(plugin_event)
    linked_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    user_data = function.load_user_data(linked_bot_hash)
    user_info = user_data.setdefault(user_id, {})
    if user_info.get('event') != 'changing_bgcolor':
        reply_text(plugin_event, '你现在似乎没有需要确定的事情。')
        return
    if confirm:
        if user_info.get('temp_bgcolor') == 'default':
            user_info.pop('bg_color', None)
            message = '背景色已重置为默认颜色。'
        else:
            user_info['bg_color'] = user_info.get('temp_bgcolor', user_info.get('bg_color', 'f7dbff'))
            message = f'更改背景色成功！\n当前背景色号为：#{user_info["bg_color"]}'
    else:
        if 'previous_bgcolor' in user_info:
            user_info['bg_color'] = user_info['previous_bgcolor']
            message = '已恢复之前的背景色设置。'
        else:
            message = '你取消了更改背景色。'
    for key in ['temp_bgcolor', 'previous_bgcolor']:
        user_info.pop(key, None)
    user_info['event'] = 'nothing'
    function.save_user_data(user_data, linked_bot_hash)
    reply_text(plugin_event, message)


command_handler_dict = {
    'today': lambda event, arg: handle_today(event),
    'random': handle_random,
    'alias': handle_alias,
    'song': handle_song,
    'info': handle_info,
    'artist': handle_artist,
    'help': handle_help,
    'time': lambda event, arg: handle_time(event),
    'all': lambda event, arg: handle_all(event),
    'update': handle_update,
    'fullcheck': handle_fullcheck,
    'full': handle_fullcheck,
    '全量检测': handle_fullcheck,
    '全量': handle_fullcheck,
    'sync': handle_sync,
    'cover': handle_cover,
    'cal': handle_cal,
    'notes': lambda event, arg: handle_notes(event),
    'b30': handle_b30,
    'score': handle_score,
    'bind': handle_bind,
    'unbind': handle_unbind,
    'user': handle_user,
    'friend': handle_friend,
    'category': handle_category,
    'table': handle_table,
    'ritmo': lambda event, arg: handle_ritmo(event),
    'color': handle_color,
    'confirm': lambda event, arg: handle_confirm_or_deny(event, True),
    'deny': lambda event, arg: handle_confirm_or_deny(event, False),
    'laglobal': handle_laglobal,
    'labot': handle_labot,
    'lagroup': handle_lagroup,
}


@utils.log_exception('handle_message')
def handle_message(plugin_event, Proc) -> None:
    utils.initialize_plugin(Proc)
    if not utils.check_core_group_enable(plugin_event):
        return
    message_text = utils.strip_reply_segment(utils.get_message_text_from_event(plugin_event))
    at_list, remaining_after_at = utils.parse_at_segments(message_text)
    if at_list and not utils.is_force_reply_to_current_bot(at_list, plugin_event):
        return
    prefix, remaining_text = utils.parse_prefix(remaining_after_at)
    
    # 如果没有前缀，先尝试处理搜索会话的输入
    if not prefix:
        bot_hash = utils.get_bot_hash_from_event(plugin_event)
        bot_config = utils.load_bot_config(bot_hash)
        global_config = utils.load_global_config()
        
        if global_config.get('global_enable_switch', True) and bot_config.get('bot_enable_switch', True):
            if handle_search_session_input(plugin_event, remaining_after_at):
                return
        return
    
    command_name, argument = match_command(remaining_text)
    if not command_name:
        return

    bot_hash = utils.get_bot_hash_from_event(plugin_event)
    bot_config = utils.load_bot_config(bot_hash)
    global_config = utils.load_global_config()
    if command_name not in management_command_name_set:
        if not global_config.get('global_enable_switch', True) or not bot_config.get('bot_enable_switch', True):
            return
        if utils.is_group_disabled(plugin_event):
            return
    if is_plain_text_mode(plugin_event) and command_name in ['color', 'confirm', 'deny']:
        reply_text(plugin_event, '当前 Bot 已开启纯文本模式，背景色功能不可用。')
        return
    handler = command_handler_dict.get(command_name)
    if handler:
        handler(plugin_event, argument)
