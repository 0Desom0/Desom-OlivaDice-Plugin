# -*- encoding: utf-8 -*-
"""LanotaPlugin 消息解析与命令处理。"""

import datetime
import random
import re
from typing import Any

from . import crawler
from . import function
from . import utils

management_command_name_set = {'laglobal', 'labot', 'lagroup'}

command_configs = [
    ('today', '今日曲'),
    ('random', '随机'),
    ('alias', '别名'),
    ('find', '查找'),
    ('artist', '曲师'),
    ('help', '帮助'),
    ('time', '时长'),
    ('all', '全部'),
    ('update', '更新'),
    ('cal', '计算'),
    ('notes', '物量'),
    ('rating', 'rating'),
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
    'find': 'find',
    'info': 'find',
    '查找': 'find',
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
    'cal': 'cal',
    'calculate': 'cal',
    '计算': 'cal',
    'notes': 'notes',
    '物量': 'notes',
    'rating': 'rating',
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


def handle_init(plugin_event, Proc) -> None:
    utils.info_log(Proc, 'LanotaPlugin init 完成。')


def handle_init_after(plugin_event, Proc) -> None:
    utils.debug_log(Proc, 'LanotaPlugin init_after 已执行。')


def handle_private_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_group_message(plugin_event, Proc) -> None:
    handle_message(plugin_event, Proc)


def handle_save(plugin_event, Proc) -> None:
    utils.debug_log(Proc, 'LanotaPlugin save 已执行。')


def reply_text(plugin_event, text: str, max_chars: int | None = None) -> None:
    global_config = utils.load_global_config()
    user_id = utils.get_sender_id_from_event(plugin_event)
    if global_config.get('send_as_image', True):
        linked_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
        image_path = function.create_text_image(
            text,
            user_id=user_id,
            max_chars=max_chars,
            bot_hash=linked_bot_hash,
        )
        if image_path:
            utils.reply_image(plugin_event, image_path, text)
            return
    utils.reply_message(plugin_event, text)


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
        if not subcommand_source.strip():
            return 'help', ''
        return 'find', subcommand_source

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
        reply_text(plugin_event, '权限不足，只有 OlivaDiceCore 骰主或本插件配置管理员可以使用。')
        return
    global_config = utils.load_global_config()
    action, value = parse_action(argument, ['status', 'debug', 'image', 'off', 'on'])
    if action in ['', 'status']:
        reply_text(
            plugin_event,
            'LanotaPlugin 全局状态：\n'
            f'启用：{"ON" if global_config.get("global_enable_switch", True) else "OFF"}\n'
            f'调试：{"ON" if global_config.get("global_debug_mode_switch", False) else "OFF"}\n'
            f'图片回复：{"ON" if global_config.get("send_as_image", True) else "OFF"}',
        )
        return
    if action == 'on':
        global_config['global_enable_switch'] = True
    elif action == 'off':
        global_config['global_enable_switch'] = False
    elif action == 'debug':
        global_config['global_debug_mode_switch'] = value.lower() == 'on'
    elif action == 'image':
        global_config['send_as_image'] = value.lower() == 'on'
    else:
        reply_text(plugin_event, '用法：.laglobal status/on/off/debug on/debug off/image on/image off')
        return
    utils.save_global_config(global_config)
    reply_text(plugin_event, 'LanotaPlugin 全局配置已更新。')


def handle_labot(plugin_event, argument: str) -> None:
    if not utils.sender_has_master_permission(plugin_event):
        reply_text(plugin_event, '权限不足，只有 OlivaDiceCore 骰主或本插件配置管理员可以使用。')
        return
    bot_hash = utils.get_bot_hash_from_event(plugin_event)
    bot_config = utils.load_bot_config(bot_hash)
    action, value = parse_action(argument, ['status', 'master', 'off', 'on'])
    if action in ['', 'status']:
        reply_text(
            plugin_event,
            f'当前 Bot 开关：{"ON" if bot_config.get("bot_enable_switch", True) else "OFF"}\n'
            f'本插件管理员：{", ".join(utils.get_configured_master_list(bot_hash)) or "无"}',
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
    if action == 'master':
        sub_action, sub_value = parse_action(value, ['list', 'add', 'del'])
        masters = utils.get_configured_master_list(bot_hash)
        target_list = utils.normalize_id_list(sub_value)
        if sub_action in ['', 'list']:
            reply_text(plugin_event, f'本插件管理员：{", ".join(masters) or "无"}')
            return
        if sub_action == 'add':
            for target in target_list:
                if target not in masters:
                    masters.append(target)
            utils.set_configured_master_list(bot_hash, masters)
            reply_text(plugin_event, f'已更新管理员：{", ".join(masters) or "无"}')
            return
        if sub_action == 'del':
            masters = [item for item in masters if item not in target_list]
            utils.set_configured_master_list(bot_hash, masters)
            reply_text(plugin_event, f'已更新管理员：{", ".join(masters) or "无"}')
            return
    reply_text(plugin_event, '用法：.labot status/on/off 或 .labot master list/add/del [用户ID]')


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


def handle_update(plugin_event) -> None:
    if not utils.sender_has_master_permission(plugin_event):
        reply_text(plugin_event, '权限不足，只有 OlivaDiceCore 骰主或本插件配置管理员可以更新曲库。')
        return
    reply_text(plugin_event, '开始通过 Fandom/MediaWiki API 更新乐曲数据，请稍候...')
    try:
        result = crawler.run_update()
        reply_text(plugin_event, function.build_update_report(result))
    except Exception as exception_object:
        reply_text(plugin_event, f'更新过程中发生错误：{type(exception_object).__name__}: {exception_object}')


def handle_today(plugin_event) -> None:
    user_id = utils.get_sender_id_from_event(plugin_event)
    linked_bot_hash = utils.get_bot_hash_from_event(plugin_event, use_linked=True)
    song = function.get_user_today_song(user_id, linked_bot_hash)
    if not song:
        reply_text(plugin_event, '今日乐曲获取失败，可能是乐曲数据未加载。')
        return
    nickname = utils.get_sender_name_from_event(plugin_event) or f'玩家{user_id}'
    reply_text(plugin_event, f'[{nickname}]的今日乐曲：\n\n{function.format_song_info(song)}')


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
    reply_text(plugin_event, f'{title}:\n\n{function.format_song_info(selected)}')


def handle_alias(plugin_event, argument: str) -> None:
    if not argument.strip():
        reply_text(plugin_event, '用法：\n/la alias add <别名>/<章节号或原名>\n/la alias del <别名>\n/la alias show <章节号/ID/别名/曲名>')
        return
    action, remaining = parse_action(argument, ['show', 'add', 'del'])
    action = action.lower()
    if action != 'show' and not utils.is_alias_group_allowed(plugin_event):
        reply_text(plugin_event, '权限不足，只有 alias_groups 白名单群可以使用 alias add/del。')
        return

    alias_data = function.load_alias_data()
    song_data = function.load_song_data()
    all_titles = {str(song.get('title', '')).lower() for song in song_data}
    if action == 'add':
        if '/' not in remaining:
            reply_text(plugin_event, '格式错误，请使用 <别名>/<章节号或原名> 格式。')
            return
        alias, search_term = [item.strip() for item in remaining.split('/', 1)]
        matched_songs, _match_type, total_count = function.find_song_by_search_term(search_term, song_data, alias_data)
        if not matched_songs:
            reply_text(plugin_event, f'没有找到章节号、ID或原名为[{search_term}]的乐曲。')
            return
        if total_count > 1:
            reply_text(plugin_event, render_song_list(f'找到多个匹配的乐曲({total_count}个)，请使用更精确的搜索词：', matched_songs))
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
        if total_count > 1:
            reply_text(plugin_event, render_song_list(f'找到多个匹配的乐曲({total_count}个)：', matched_songs))
            return
        std_name = str(matched_songs[0].get('title', ''))
        aliases = alias_data.get(std_name, [])
        if not aliases:
            reply_text(plugin_event, f'乐曲[{std_name}]目前没有设置别名。')
        else:
            reply_text(plugin_event, f'乐曲[{std_name}]的别名({len(aliases)}个):\n' + '\n'.join(f'{i + 1}. {a}' for i, a in enumerate(aliases)))
        return
    reply_text(plugin_event, '无效操作，只能使用 add/del/show。')


def render_song_list(header: str, songs: list[dict[str, Any]], start_index: int = 1) -> str:
    lines = [header]
    for index, song in enumerate(songs, start_index):
        lines.append(f'{index}. {song.get("chapter")} - {song.get("title")} (ID: {song.get("id")})')
    return '\n'.join(lines)


def handle_find(plugin_event, argument: str) -> None:
    raw_arg = argument.strip()
    if not raw_arg:
        reply_text(plugin_event, '用法：/la info <搜索词> 或 /la info <搜索词> p<页码>')
        return
    page = 1
    search_term = raw_arg
    page_match = re.match(r'^(.+?)\s+(?:p|page|页)\s*(\d+)$', raw_arg, re.IGNORECASE)
    if page_match:
        search_term = page_match.group(1).strip()
        page = int(page_match.group(2))
    song_data = function.load_song_data()
    alias_data = function.load_alias_data()
    matched_songs, match_type, total_count = function.find_song_by_search_term(search_term, song_data, alias_data, len(song_data))
    if not matched_songs:
        reply_text(plugin_event, f'没有找到与[{search_term}]相关的乐曲。')
        return
    if total_count == 1 and page == 1:
        reply_text(plugin_event, f'通过搜索词[{search_term}]进行[{match_type}]找到这首乐曲:\n\n{function.format_song_info(matched_songs[0])}')
        return
    page_size = 10
    total_pages = (total_count + page_size - 1) // page_size
    if page < 1 or page > total_pages:
        reply_text(plugin_event, f'页码超出范围，当前共有{total_pages}页。')
        return
    start = (page - 1) * page_size
    page_songs = matched_songs[start : min(start + page_size, total_count)]
    message = render_song_list(
        f'通过搜索词[{search_term}]进行[{match_type}]找到匹配的乐曲({total_count}首)\n第{page}/{total_pages}页：',
        page_songs,
        start + 1,
    )
    if page < total_pages:
        message += f'\n\n下一页：/la info {search_term} p{page + 1}'
    reply_text(plugin_event, message)


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
    reply_text(plugin_event, '\n'.join(lines))


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
        reply_text(plugin_event, '用法：\n/la cal harmony/tune/fail/难度/曲目\n/la cal harmony/tune/fail/物量/等级')
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
        if difficulty_value == '未知' or not notes_value:
            reply_text(plugin_event, f'乐曲[{song.get("title")}]没有{difficulty_type}难度的数据。')
            return
        rating, adjusted_fail, adjustment, exceeded, negative, bonus, base_level = function.calculate_rating(harmony, tune, fail, notes_value, str(difficulty_value))
        prefix = f'乐曲: {song.get("title")}\n难度: {difficulty_type.capitalize()} {difficulty_value}\n总物量: {notes_value}\n'
    else:
        try:
            notes_value = int(parts[3])
        except ValueError:
            reply_text(plugin_event, '物量参数必须是数字。')
            return
        level = parts[4]
        if level not in [str(i) for i in range(1, 17)] + ['13+', '14+', '15+', '16+']:
            reply_text(plugin_event, '等级必须是1-16或13+,14+,15+,16+。')
            return
        rating, adjusted_fail, adjustment, exceeded, negative, bonus, base_level = function.calculate_rating(harmony, tune, fail, notes_value, level)
        prefix = f'总物量: {notes_value}\n等级: {level}\n'

    if negative:
        reply_text(plugin_event, '输入的判定/物量不能为负数！')
    elif exceeded:
        reply_text(plugin_event, prefix + f'当前输入总物量为：{harmony + tune + fail}，已经高于物量：{notes_value}，无法计算。')
    else:
        message = prefix + f'输入判定: {harmony + tune + fail} (Harmony: {harmony}, Tune: {tune}, Fail: {fail})\n'
        if adjustment != 0:
            message += f'自动调整: Fail {fail} -> {adjusted_fail} ({adjustment:+})\n'
        message += f'单曲Rating: {rating}\n计算方式: ({harmony} + {tune}/3) / {notes_value} * ({base_level} + 1 + 难度加成({bonus}))'
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
    reply_text(plugin_event, '\n'.join(lines) if len(lines) > 1 else '没有找到有效的谱面数据。')


def handle_rating(plugin_event) -> None:
    high_level_charts = []
    for song in function.load_song_data():
        for diff_type in ['master', 'ultra']:
            level_text = str(song.get('difficulty', {}).get(diff_type, '未知'))
            try:
                notes_value = int(song.get('notes', {}).get(diff_type, 0))
                base_level = float(level_text[:-1] if level_text.endswith('+') else level_text)
            except Exception:
                continue
            if base_level >= 15:
                high_level_charts.append({'song': song, 'diff': diff_type.capitalize(), 'level': level_text, 'notes': notes_value})
    if not high_level_charts:
        reply_text(plugin_event, '没有找到15级以上的Master或Ultra难度谱面。')
        return
    level_groups = {}
    for chart in high_level_charts:
        level_groups.setdefault(chart['level'], []).append(chart)
    sorted_levels = sorted(level_groups.keys(), key=lambda item: (-float(item[:-1] if item.endswith('+') else item), -item.endswith('+')))
    b30 = []
    remaining = 30
    for level in sorted_levels:
        charts = level_groups[level]
        random.shuffle(charts)
        take = min(len(charts), remaining)
        for chart in charts[:take]:
            rating, *_unused = function.calculate_rating(chart['notes'], 0, 0, chart['notes'], chart['level'])
            b30.append({**chart, 'rating': rating})
        remaining -= take
        if remaining <= 0:
            break
    if not b30:
        reply_text(plugin_event, '没有可用于计算 rating 的谱面。')
        return
    while len(b30) < 30:
        b30.append({**b30[-1], 'song': {'title': 'N/A'}})
    max_rating = max(item['rating'] for item in b30)
    top_rated = [item for item in b30 if item['rating'] == max_rating]
    r5 = (top_rated * 5)[:5] if len(top_rated) < 5 else random.sample(top_rated, 5)
    total_rating = (sum(item['rating'] for item in b30) + sum(item['rating'] for item in r5)) / 35
    lines = [
        '========== Rating计算 ==========',
        f'理论Max Rating: {total_rating:.2f}',
        f'B30平均: {sum(item["rating"] for item in b30) / 30:.2f}',
        f'R5平均: {sum(item["rating"] for item in r5) / 5:.2f}',
        '========== B30谱面 ==========',
    ]
    lines.extend(f'{i:2d}. {item["song"].get("title")} -|- {item["diff"]} {item["level"]} (Rating: {item["rating"]:.2f})' for i, item in enumerate(b30, 1))
    lines.append('========== R5谱面 ==========')
    lines.extend(f'{i}. {item["song"].get("title")} -|- {item["diff"]} {item["level"]} (Rating: {item["rating"]:.2f})' for i, item in enumerate(r5, 1))
    reply_text(plugin_event, '\n'.join(lines))


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
    reply_text(plugin_event, '\n'.join(lines))


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
            '/la alias add <别名>/<搜索词> - 添加别名',
            '/la alias del <别名> - 删除别名',
            '/la alias show <搜索词> - 查看乐曲别名',
        ],
        'examples': [
            '/la alias show Frey',
            '/la alias add frey/1-1',
        ],
    },
    'search': {
        'name': '查找乐曲',
        'aliases': ['info', '查找', 'find'],
        'commands': [
            '/la info <搜索词> - 查找乐曲信息',
            '/la find <搜索词> - 同上',
            '/la info <搜索词> p<页码> - 分页查看搜索结果',
        ],
        'priority': [
            '1. 完全匹配章节号',
            '2. 完全匹配ID',
            '3. 完全匹配别名',
            '4. 完全匹配曲名',
            '5. 模糊匹配曲名或别名',
        ],
        'examples': [
            '/la info Frey',
            '/la info Frey p2',
            '/la info Frey 页3',
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
        'name': '定数计算功能',
        'aliases': ['cal', '计算', 'calculate'],
        'commands': [
            '/la cal harmony数目/tune数目/fail数目/难度/曲目 - 根据曲目计算rating',
            '/la cal harmony数目/tune数目/fail数目/物量/等级 - 直接计算rating',
        ],
        'priority': [
            '1. 前三个参数必须是数字',
            '2. 难度可以是: Whisper, Acoustic, Ultra, Master',
            '3. 等级可以是: 1-16, 13+, 14+, 15+, 16+',
            '4. 如果输入的物量之和不正确，将自动补到fail数目',
        ],
        'examples': [
            '/la cal 900/300/50/Master/8-6',
            '/la cal 900/300/50/2000/16',
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
    'stats': {
        'name': '其它功能',
        'aliases': ['other', '其它'],
        'commands': [
            '/la time - 显示长于3分钟和短于2分钟的乐曲列表',
            '/la all - 显示曲库统计信息',
            '/la notes - 物量最多的前50个谱面',
            '/la rating - 显示当前的Max Rating，并且给出可能的B30和R5',
            '/la ritmo - 显示里莫绝赞昏睡时间',
        ],
        'examples': [
            '/la time',
            '/la all',
            '/la notes',
            '/la rating',
            '/la ritmo',
        ],
    },
    'table': {
        'name': '定数表',
        'aliases': ['table', '定数表'],
        'commands': [
            '/la table - 按定数从高到低显示所有谱面',
            '/la 定数表 - 同上',
            '/la table update - 从 excel_table 文件夹导入 Excel 定数表并覆盖 song_table.json（骰主/插件管理员）',
        ],
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
            '/la global status/on/off - 查看或修改全局开关',
            '/la update - 通过 Fandom/MediaWiki API 更新曲库',
            '/la table update - 从 Excel 定数表更新 song_table.json',
        ],
        'priority': [
            '1. /la on 和 /la off 需要群主、群管、骰主或本插件管理员',
            '2. bot/global/update 需要骰主或本插件管理员',
            '3. 被关闭的群仍可使用 /la on 重新开启',
        ],
        'examples': [
            '/la off',
            '/la on',
            '/la update',
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
        reply_text(plugin_event, '未找到该分类，\n请输入 /la help\n查看所有分类')
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
        lines.extend(['', '匹配优先级:', *matched_category['priority']])

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
        reply_text(plugin_event, '你确定要将背景色重置为默认颜色吗？\n请输入 /la confirm 确认或 /la deny 取消。')
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
    reply_text(plugin_event, f'当前预览背景色: #{color_code}\n可以随便输入命令预览背景色\n请输入 /la confirm 确认或 /la deny 取消。')


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
    'find': handle_find,
    'artist': handle_artist,
    'help': handle_help,
    'time': lambda event, arg: handle_time(event),
    'all': lambda event, arg: handle_all(event),
    'update': lambda event, arg: handle_update(event),
    'cal': handle_cal,
    'notes': lambda event, arg: handle_notes(event),
    'rating': lambda event, arg: handle_rating(event),
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
    if not prefix:
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
    handler = command_handler_dict.get(command_name)
    if handler:
        handler(plugin_event, argument)
