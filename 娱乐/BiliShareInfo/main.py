import html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

import BiliShareInfo  # noqa: F401

try:
    import OlivaDiceCore

    HAS_OLIVA_DICE_CORE = True
except Exception:
    OlivaDiceCore = None
    HAS_OLIVA_DICE_CORE = False


gProc = None
gPluginName = 'BiliShareInfo'

PLUGIN_NAMESPACE = 'BiliShareInfo'
DATA_ROOT = os.path.join('data', PLUGIN_NAMESPACE)

DEFAULT_CONFIG = {
    'global_enable': True,
    'single_forward_enable': False,
    'multi_forward_enable': True,
    'configured_master_list': [],
}

DEFAULT_GROUP_CONFIG = {
    'groups': {},
}

DATA_LOCK = threading.RLock()
gRecentKeyTime = {}

COMMAND_PREFIXES = ('.', '/', '。')
HTTP_TIMEOUT = 8
RECENT_TTL_SECONDS = 30


class Event(object):
    def init(plugin_event, Proc):
        load_config()

    def init_after(plugin_event, Proc):
        global gProc
        gProc = Proc

    def save(plugin_event, Proc):
        save_config()

    def private_message(plugin_event, Proc):
        handle_message(plugin_event, is_group=False)

    def group_message(plugin_event, Proc):
        handle_message(plugin_event, is_group=True)


def handle_message(plugin_event, is_group: bool) -> None:
    try:
        message = safe_str(plugin_event.data.message)
        if handle_command(plugin_event, message, is_group):
            return
        if not is_group:
            return
        if not is_group_enabled(plugin_event):
            return

        video_ref_list = extract_video_refs_from_message(message)
        if not video_ref_list:
            return

        video_info_list = []
        sent_dedupe_key_list = []
        for video_ref in video_ref_list:
            dedupe_key = build_dedupe_key(plugin_event, video_ref)
            if is_recent_duplicate(dedupe_key):
                continue
            video_info = fetch_video_info(video_ref)
            if not video_info:
                continue
            video_info_list.append(video_info)
            sent_dedupe_key_list.append(dedupe_key)

        if not video_info_list:
            return

        send_video_info_list(plugin_event, video_info_list)
        for dedupe_key in sent_dedupe_key_list:
            mark_recent_key(dedupe_key)
    except Exception:
        return


def handle_command(plugin_event, message: str, is_group: bool) -> bool:
    command_info = parse_bili_command(message)
    if command_info is None:
        return False

    if not command_info:
        return False

    command_scope = command_info.get('scope', '')
    command_action = command_info.get('action', '')

    if command_scope == 'help':
        plugin_event.reply(build_help_message(plugin_event, is_group))
        plugin_event.set_block()
        return True

    if command_scope == 'global':
        if command_action not in ['on', 'off']:
            plugin_event.reply('用法：.bili global on/off')
            plugin_event.set_block()
            return True
        if not has_global_switch_permission(plugin_event):
            plugin_event.reply('权限不足：只有骰主可以切换全局开关。')
            plugin_event.set_block()
            return True

        set_global_enable(plugin_event, command_action == 'on')
        plugin_event.reply(f'B站解析全局开关已{"开启" if command_action == "on" else "关闭"}。')
        plugin_event.set_block()
        return True

    if command_scope in ['single_forward', 'multi_forward']:
        if command_action not in ['on', 'off']:
            plugin_event.reply('用法：.bili singleforward on/off 或 .bili multiforward on/off')
            plugin_event.set_block()
            return True
        if not has_global_switch_permission(plugin_event):
            plugin_event.reply('权限不足：只有骰主可以切换合并转发。')
            plugin_event.set_block()
            return True

        if command_scope == 'single_forward':
            set_single_forward_enable(plugin_event, command_action == 'on')
            plugin_event.reply(f'单链接合并转发已{"开启" if command_action == "on" else "关闭"}。')
        else:
            set_multi_forward_enable(plugin_event, command_action == 'on')
            plugin_event.reply(f'多链接合并转发已{"开启" if command_action == "on" else "关闭"}。')
        plugin_event.set_block()
        return True

    if command_scope == 'group':
        if not is_group:
            plugin_event.reply('群级开关只能在群聊中使用。')
            plugin_event.set_block()
            return True
        if not has_group_switch_permission(plugin_event):
            plugin_event.reply('权限不足：只有群主、群管理或骰主可以切换本群开关。')
            plugin_event.set_block()
            return True

        set_group_enable(plugin_event, command_action == 'on')
        plugin_event.reply(f'本群B站解析已{"开启" if command_action == "on" else "关闭"}。')
        plugin_event.set_block()
        return True

    plugin_event.reply('用法：.bili on/off 或 .bili global on/off')
    plugin_event.set_block()
    return True


def parse_bili_command(message: str) -> dict[str, str] | None:
    stripped_message = strip_leading_op_command_prefix(message).strip()
    for prefix in COMMAND_PREFIXES:
        command_head = f'{prefix}bili'
        if not stripped_message.startswith(command_head):
            continue

        command_tail = stripped_message[len(command_head) :]
        compact_tail = re.sub(r'\s+', '', command_tail).lower()
        if not compact_tail:
            return {'scope': 'help', 'action': ''}
        if compact_tail in ['on', 'off']:
            return {'scope': 'group', 'action': compact_tail}
        if compact_tail in ['globalon', 'globaloff']:
            return {'scope': 'global', 'action': compact_tail.removeprefix('global')}
        if compact_tail in ['singleforwardon', 'singleforwardoff']:
            return {'scope': 'single_forward', 'action': compact_tail.removeprefix('singleforward')}
        if compact_tail in ['singlemergeon', 'singlemergeoff']:
            return {'scope': 'single_forward', 'action': compact_tail.removeprefix('singlemerge')}
        if compact_tail in ['multiforwardon', 'multiforwardoff']:
            return {'scope': 'multi_forward', 'action': compact_tail.removeprefix('multiforward')}
        if compact_tail in ['multimergeon', 'multimergeoff']:
            return {'scope': 'multi_forward', 'action': compact_tail.removeprefix('multimerge')}
        if compact_tail in ['forwardon', 'forwardoff']:
            return {'scope': 'multi_forward', 'action': compact_tail.removeprefix('forward')}
        if compact_tail in ['mergeon', 'mergeoff']:
            return {'scope': 'multi_forward', 'action': compact_tail.removeprefix('merge')}
        if compact_tail in ['help', 'h', '?']:
            return {'scope': 'help', 'action': ''}
        return {'scope': 'invalid', 'action': compact_tail}
    return None


def strip_leading_op_command_prefix(message: str) -> str:
    stripped_message = safe_str(message).lstrip()
    while True:
        op_match = re.match(r'^\[OP:(?:at|reply)(?:,[^\]]*)?\]\s*', stripped_message)
        if not op_match:
            return stripped_message
        stripped_message = stripped_message[op_match.end() :].lstrip()


def build_help_message(plugin_event, is_group: bool) -> str:
    return '\n'.join(
        [
            'B站解析帮助',
            '本群开关：.bili on/off（群主、管理员、骰主）',
            '全局开关：.bili global on/off（仅骰主）',
            '单链接合并转发：.bili singleforward on/off（仅骰主）',
            '多链接合并转发：.bili multiforward on/off（仅骰主）',
            '帮助：.bili help',
            '本群开关默认关闭，需要手动开启。',
            '开启后会自动解析群内的B站小程序/链接分享并回复视频信息。',
        ]
    )


def load_config() -> None:
    try:
        os.makedirs(DATA_ROOT, exist_ok=True)
    except Exception:
        pass


def save_config(plugin_event=None) -> bool:
    return True


def set_global_enable(plugin_event, enable: bool) -> None:
    bot_hash = get_config_bot_hash_from_event(plugin_event)
    bot_config = load_bot_config(bot_hash)
    bot_config['global_enable'] = bool(enable)
    save_bot_config(bot_hash, bot_config)


def set_single_forward_enable(plugin_event, enable: bool) -> None:
    bot_hash = get_config_bot_hash_from_event(plugin_event)
    bot_config = load_bot_config(bot_hash)
    bot_config['single_forward_enable'] = bool(enable)
    save_bot_config(bot_hash, bot_config)


def set_multi_forward_enable(plugin_event, enable: bool) -> None:
    bot_hash = get_config_bot_hash_from_event(plugin_event)
    bot_config = load_bot_config(bot_hash)
    bot_config['multi_forward_enable'] = bool(enable)
    save_bot_config(bot_hash, bot_config)


def set_group_enable(plugin_event, enable: bool) -> None:
    group_key = get_group_key(plugin_event)
    if group_key:
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        group_config = load_group_config(bot_hash)
        group_config.setdefault('groups', {})[group_key] = bool(enable)
        save_group_config(bot_hash, group_config)


def is_group_enabled(plugin_event) -> bool:
    bot_hash = get_config_bot_hash_from_event(plugin_event)
    bot_config = load_bot_config(bot_hash)
    if not bool(bot_config.get('global_enable', True)):
        return False
    group_key = get_group_key(plugin_event)
    if not group_key:
        return False
    group_config = load_group_config(bot_hash)
    return bool(group_config.get('groups', {}).get(group_key, False))


def get_group_key(plugin_event) -> str:
    try:
        host_id = safe_str(getattr(plugin_event.data, 'host_id', None)) or 'none'
        group_id = safe_str(plugin_event.data.group_id)
        return f'{host_id}|{group_id}'
    except Exception:
        return ''


def load_bot_config(bot_hash: Any) -> dict[str, Any]:
    config_data = read_json_file(get_bot_config_file(bot_hash), DEFAULT_CONFIG)
    return normalize_config_data(config_data)


def save_bot_config(bot_hash: Any, config_data: dict[str, Any]) -> bool:
    return write_json_file(get_bot_config_file(bot_hash), normalize_config_data(config_data))


def load_group_config(bot_hash: Any) -> dict[str, Any]:
    group_data = read_json_file(get_group_config_file(bot_hash), DEFAULT_GROUP_CONFIG)
    return normalize_group_data(group_data)


def save_group_config(bot_hash: Any, group_data: dict[str, Any]) -> bool:
    return write_json_file(get_group_config_file(bot_hash), normalize_group_data(group_data))


def read_json_file(file_path: str, default_data: dict[str, Any]) -> dict[str, Any]:
    with DATA_LOCK:
        try:
            if os.path.exists(file_path):
                with open(file_path, encoding='utf-8') as data_file:
                    loaded_data = json.load(data_file)
                if isinstance(loaded_data, dict):
                    return loaded_data
        except Exception:
            pass
        return dict(default_data)


def write_json_file(file_path: str, data: dict[str, Any]) -> bool:
    with DATA_LOCK:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            temp_file = f'{file_path}.tmp'
            with open(temp_file, 'w', encoding='utf-8') as data_file:
                json.dump(data, data_file, ensure_ascii=False, indent=2)
            os.replace(temp_file, file_path)
            return True
        except Exception:
            return False


def normalize_config_data(config_data: Any) -> dict[str, Any]:
    normalized_config = dict(DEFAULT_CONFIG)
    if not isinstance(config_data, dict):
        return normalized_config
    normalized_config['global_enable'] = bool(config_data.get('global_enable', True))
    normalized_config['single_forward_enable'] = bool(config_data.get('single_forward_enable', False))
    normalized_config['multi_forward_enable'] = bool(config_data.get('multi_forward_enable', True))
    normalized_config['configured_master_list'] = normalize_id_list(
        config_data.get('configured_master_list', [])
    )
    return normalized_config


def normalize_group_data(group_data: Any) -> dict[str, Any]:
    normalized_group_data = dict(DEFAULT_GROUP_CONFIG)
    groups = group_data.get('groups', {}) if isinstance(group_data, dict) else {}
    if not isinstance(groups, dict):
        groups = {}
    normalized_group_data['groups'] = {
        safe_str(group_key): bool(enable)
        for group_key, enable in groups.items()
        if safe_str(group_key)
    }
    return normalized_group_data


def normalize_id_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_id_list = re.split(r'[\s,，;；]+', value)
    elif isinstance(value, list):
        raw_id_list = value
    else:
        raw_id_list = []

    normalized_id_list = []
    for raw_id in raw_id_list:
        normalized_id = safe_str(raw_id).strip()
        if normalized_id and normalized_id not in normalized_id_list:
            normalized_id_list.append(normalized_id)
    return normalized_id_list


def get_bot_config_file(bot_hash: Any) -> str:
    return os.path.join(get_bot_data_dir(bot_hash), 'config.json')


def get_group_config_file(bot_hash: Any) -> str:
    return os.path.join(get_bot_data_dir(bot_hash), 'group.json')


def get_bot_data_dir(bot_hash: Any) -> str:
    return os.path.join(DATA_ROOT, sanitize_path_name(safe_str(bot_hash).strip() or 'default'))


def sanitize_path_name(path_name: str) -> str:
    sanitized_name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', safe_str(path_name).strip())
    return sanitized_name or 'default'


def get_config_bot_hash_from_event(plugin_event) -> str:
    try:
        raw_bot_hash = safe_str(plugin_event.bot_info.hash).strip() or 'default'
        return get_linked_bot_hash(raw_bot_hash)
    except Exception:
        return 'default'


def get_linked_bot_hash(bot_hash: Any) -> str:
    raw_bot_hash = safe_str(bot_hash).strip() or 'default'
    if HAS_OLIVA_DICE_CORE:
        try:
            linked_bot_hash = OlivaDiceCore.console.getMasterBotHash(raw_bot_hash)
            if linked_bot_hash:
                return safe_str(linked_bot_hash).strip() or raw_bot_hash
        except Exception:
            pass
    return raw_bot_hash


def has_group_switch_permission(plugin_event) -> bool:
    return (
        is_sender_core_master(plugin_event)
        or is_sender_configured_master(plugin_event)
        or is_group_admin(plugin_event)
    )


def has_global_switch_permission(plugin_event) -> bool:
    return is_sender_core_master(plugin_event) or is_sender_configured_master(plugin_event)


def is_sender_core_master(plugin_event) -> bool:
    if not HAS_OLIVA_DICE_CORE:
        return False
    try:
        user_hash = OlivaDiceCore.userConfig.getUserHash(
            plugin_event.data.user_id,
            'user',
            plugin_event.platform['platform'],
        )
        return bool(
            OlivaDiceCore.ordinaryInviteManager.isInMasterList(
                plugin_event.bot_info.hash,
                user_hash,
            )
        )
    except Exception:
        return False


def is_sender_configured_master(plugin_event) -> bool:
    try:
        sender_id = safe_str(plugin_event.data.user_id)
        if not sender_id:
            return False
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        bot_config = load_bot_config(bot_hash)
        return sender_id in bot_config.get('configured_master_list', [])
    except Exception:
        return False


def is_group_admin(plugin_event) -> bool:
    try:
        role = safe_str(plugin_event.data.sender.get('role', '')).lower()
        return role in ['owner', 'admin', 'sub_admin']
    except Exception:
        return False


def extract_json_card(message: str) -> dict[str, Any] | None:
    for marker in ['[OP:json', '[CQ:json']:
        start_index = message.find(marker)
        if start_index < 0:
            continue

        data_index = message.find('data=', start_index)
        if data_index < 0:
            continue

        brace_index = message.find('{', data_index)
        if brace_index < 0:
            continue

        json_text = extract_balanced_json(message, brace_index)
        if not json_text:
            continue

        try:
            return json.loads(html.unescape(json_text))
        except Exception:
            continue
    return None


def extract_balanced_json(text: str, start_index: int) -> str:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]
    return ''


def is_probable_bili_card(card_data: dict[str, Any]) -> bool:
    string_list = collect_strings(card_data)
    joined_text = '\n'.join(string_list).lower()
    return any(
        keyword in joined_text
        for keyword in [
            'bilibili',
            'b23.tv',
            '哔哩哔哩',
            'bili',
            '1109937557',
            'com.tencent.miniapp_01',
        ]
    )


def extract_video_refs_from_message(message: str) -> list[dict[str, str]]:
    video_ref_list = []
    seen_key_set = set()

    for video_ref in extract_video_refs_from_text(message):
        add_video_ref(video_ref_list, seen_key_set, video_ref)

    for url in extract_urls(message):
        video_ref = resolve_video_ref_from_url(url)
        add_video_ref(video_ref_list, seen_key_set, video_ref)

    card_data = extract_json_card(message)
    if not card_data or not is_probable_bili_card(card_data):
        return video_ref_list

    card_ref_count_before = len(video_ref_list)
    for video_ref in find_video_refs(card_data):
        add_video_ref(video_ref_list, seen_key_set, video_ref)

    if len(video_ref_list) == card_ref_count_before:
        title_hint = get_title_hint(card_data)
        video_ref = search_video_by_keyword(title_hint)
        add_video_ref(video_ref_list, seen_key_set, video_ref)

    return video_ref_list


def find_video_refs(card_data: dict[str, Any]) -> list[dict[str, str]]:
    video_ref_list = []
    seen_key_set = set()
    string_list = collect_strings(card_data)
    for text in string_list:
        for video_ref in extract_video_refs_from_text(text):
            add_video_ref(video_ref_list, seen_key_set, video_ref)

    for text in string_list:
        url_list = extract_urls(text)
        for url in url_list:
            video_ref = resolve_video_ref_from_url(url)
            add_video_ref(video_ref_list, seen_key_set, video_ref)
    return video_ref_list


def extract_video_ref_from_text(text: str) -> dict[str, str] | None:
    video_ref_list = extract_video_refs_from_text(text)
    if video_ref_list:
        return video_ref_list[0]
    return None


def extract_video_refs_from_text(text: str) -> list[dict[str, str]]:
    unescaped_text = html.unescape(safe_str(text))
    video_ref_list = []
    seen_key_set = set()

    for bvid_match in re.finditer(r'(BV[0-9A-Za-z]{10})', unescaped_text):
        add_video_ref(video_ref_list, seen_key_set, {'bvid': bvid_match.group(1)})

    for aid_match in re.finditer(r'(?:^|[^A-Za-z0-9])(?:av|aid=)(\d+)', unescaped_text, re.IGNORECASE):
        add_video_ref(video_ref_list, seen_key_set, {'aid': aid_match.group(1)})

    return video_ref_list


def add_video_ref(
    video_ref_list: list[dict[str, str]],
    seen_key_set: set[str],
    video_ref: dict[str, str] | None,
) -> None:
    if not video_ref:
        return
    video_key = get_video_ref_key(video_ref)
    if not video_key or video_key in seen_key_set:
        return
    seen_key_set.add(video_key)
    video_ref_list.append(video_ref)


def get_video_ref_key(video_ref: dict[str, str]) -> str:
    if video_ref.get('bvid'):
        return f'bvid:{video_ref["bvid"]}'
    if video_ref.get('aid'):
        return f'aid:{video_ref["aid"]}'
    return ''


def extract_urls(text: str) -> list[str]:
    clean_text = html.unescape(safe_str(text)).replace('\\/', '/')
    url_pattern = (
        r'https?://(?:www\.|m\.)?bilibili\.com/[^\s"\'<>]+|'
        r'https?://b23\.tv/[^\s"\'<>]+|'
        r'https?://bili2233\.cn/[^\s"\'<>]+|'
        r'https?://m\.q\.qq\.com/[^\s"\'<>]+|'
        r'(?:www\.|m\.)?bilibili\.com/[^\s"\'<>]+|'
        r'b23\.tv/[^\s"\'<>]+|'
        r'bili2233\.cn/[^\s"\'<>]+|'
        r'm\.q\.qq\.com/[^\s"\'<>]+'
    )
    url_list = re.findall(url_pattern, clean_text)
    result = []
    for raw_url in url_list:
        url = raw_url.rstrip('，。,.;；)）]】')
        if not url.startswith('http://') and not url.startswith('https://'):
            url = f'https://{url}'
        if url not in result:
            result.append(url)
    return result


def resolve_video_ref_from_url(url: str) -> dict[str, str] | None:
    direct_ref = extract_video_ref_from_text(url)
    if direct_ref:
        return direct_ref

    try:
        response_url, response_text = http_get_text(url, allow_response_body=True)
    except Exception:
        return None

    for text in [response_url, response_text]:
        video_ref = extract_video_ref_from_text(text)
        if video_ref:
            return video_ref
    return None


def search_video_by_keyword(keyword: str) -> dict[str, str] | None:
    keyword = clean_search_keyword(keyword)
    if not keyword:
        return None

    try:
        query = urllib.parse.urlencode({'search_type': 'video', 'keyword': keyword})
        api_url = f'https://api.bilibili.com/x/web-interface/search/type?{query}'
        response_text = http_get_json_text(api_url, referer='https://search.bilibili.com/')
        response_data = json.loads(response_text)
        result_list = response_data.get('data', {}).get('result', [])
        if not isinstance(result_list, list):
            return None
        for item in result_list[:5]:
            bvid = safe_str(item.get('bvid', ''))
            if re.fullmatch(r'BV[0-9A-Za-z]{10}', bvid):
                return {'bvid': bvid}
    except Exception:
        return None
    return None


def fetch_video_info(video_ref: dict[str, str]) -> dict[str, Any] | None:
    try:
        if video_ref.get('bvid'):
            query = urllib.parse.urlencode({'bvid': video_ref['bvid']})
        elif video_ref.get('aid'):
            query = urllib.parse.urlencode({'aid': video_ref['aid']})
        else:
            return None

        api_url = f'https://api.bilibili.com/x/web-interface/view?{query}'
        response_text = http_get_json_text(api_url, referer='https://www.bilibili.com/')
        response_data = json.loads(response_text)
        if response_data.get('code') != 0:
            return None
        data = response_data.get('data', {})
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def http_get_text(url: str, allow_response_body: bool = False) -> tuple[str, str]:
    request = urllib.request.Request(url, headers=get_http_headers())
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        response_url = response.geturl()
        if not allow_response_body:
            return response_url, ''
        content = response.read(128 * 1024)
        charset = response.headers.get_content_charset() or 'utf-8'
        response_text = content.decode(charset, errors='ignore')
        return response_url, response_text


def http_get_json_text(url: str, referer: str = 'https://www.bilibili.com/') -> str:
    headers = get_http_headers()
    headers['Referer'] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return response.read().decode('utf-8', errors='ignore')


def get_http_headers() -> dict[str, str]:
    return {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/126.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }


def format_video_reply(video_info: dict[str, Any]) -> str:
    cover_url = normalize_cover_url(safe_str(video_info.get('pic', '')))
    reply_text = format_video_text(video_info)
    if cover_url:
        return f'[OP:image,file={op_escape(cover_url)}]{reply_text}'
    return reply_text


def format_video_forward_content(video_info: dict[str, Any]) -> list[dict[str, Any]]:
    content_list = []
    cover_url = normalize_cover_url(safe_str(video_info.get('pic', '')))
    if cover_url:
        content_list.append(
            {
                'type': 'image',
                'data': {
                    'file': cover_url,
                },
            }
        )
    content_list.append(
        {
            'type': 'text',
            'data': {
                'text': format_video_text(video_info),
            },
        }
    )
    return content_list


def format_video_text(video_info: dict[str, Any]) -> str:
    title = safe_str(video_info.get('title', '未知标题'))
    bvid = safe_str(video_info.get('bvid', ''))
    owner = video_info.get('owner', {}) if isinstance(video_info.get('owner'), dict) else {}
    up_name = safe_str(owner.get('name', '未知UP主'))
    desc = shorten_text(safe_str(video_info.get('desc', '无简介')), 160)
    stat = video_info.get('stat', {}) if isinstance(video_info.get('stat'), dict) else {}

    lines = [
        f'标题：{title}',
        f'BV号：{bvid or "未知"}',
        f'UP主：{up_name}',
        f'简介：{desc}',
        f'播放：{format_count(stat.get("view"))}  弹幕：{format_count(stat.get("danmaku"))}',
        (
            f'点赞：{format_count(stat.get("like"))}  投币：{format_count(stat.get("coin"))}  '
            f'收藏：{format_count(stat.get("favorite"))}  转发：{format_count(stat.get("share"))}'
        ),
    ]
    if bvid:
        lines.append(f'链接：https://www.bilibili.com/video/{bvid}')
    return '\n'.join(lines)


def send_video_info_list(plugin_event, video_info_list: list[dict[str, Any]]) -> None:
    if len(video_info_list) == 1:
        if (
            is_qq_platform(plugin_event)
            and is_single_forward_enabled(plugin_event)
            and send_group_forward(plugin_event, video_info_list)
        ):
            return
        plugin_event.reply(format_video_reply(video_info_list[0]))
        return

    if (
        is_qq_platform(plugin_event)
        and is_multi_forward_enabled(plugin_event)
        and send_group_forward(plugin_event, video_info_list)
    ):
        return

    for video_info in video_info_list:
        plugin_event.reply(format_video_reply(video_info))


def is_single_forward_enabled(plugin_event) -> bool:
    try:
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        bot_config = load_bot_config(bot_hash)
        return bool(bot_config.get('single_forward_enable', False))
    except Exception:
        return False


def is_multi_forward_enabled(plugin_event) -> bool:
    try:
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        bot_config = load_bot_config(bot_hash)
        return bool(bot_config.get('multi_forward_enable', True))
    except Exception:
        return True


def send_group_forward(plugin_event, video_info_list: list[dict[str, Any]]) -> bool:
    try:
        message_node_list = []
        bot_id = get_bot_id(plugin_event)
        for video_info in video_info_list:
            message_node_list.append(
                {
                    'type': 'node',
                    'data': {
                        'name': gPluginName,
                        'uin': bot_id,
                        'content': format_video_forward_content(video_info),
                    },
                }
            )

        result = plugin_event.send_group_forward_msg(plugin_event.data.group_id, message_node_list)
        if isinstance(result, dict) and result.get('active') is False:
            return False
        return True
    except Exception:
        return False


def is_qq_platform(plugin_event) -> bool:
    try:
        return safe_str(plugin_event.platform.get('platform', '')).lower() == 'qq'
    except Exception:
        return False


def get_bot_id(plugin_event) -> str:
    try:
        bot_id = safe_str(plugin_event.bot_info.id)
        if bot_id and bot_id != '-1':
            return bot_id
    except Exception:
        pass

    try:
        bot_id = safe_str(plugin_event.base_info.get('self_id', ''))
        if bot_id:
            return bot_id
    except Exception:
        pass
    return '0'


def normalize_cover_url(cover_url: str) -> str:
    if cover_url.startswith('//'):
        return f'https:{cover_url}'
    return cover_url


def format_count(value: Any) -> str:
    try:
        number = int(value)
    except Exception:
        return '0'
    if number >= 100000000:
        return f'{number / 100000000:.2f}亿'
    if number >= 10000:
        return f'{number / 10000:.1f}万'
    return str(number)


def get_title_hint(card_data: dict[str, Any]) -> str:
    for key_path in [
        ['meta', 'detail_1', 'desc'],
        ['prompt'],
        ['desc'],
        ['title'],
    ]:
        value = get_nested_value(card_data, key_path)
        if value:
            return safe_str(value)
    return ''


def clean_search_keyword(keyword: str) -> str:
    keyword = safe_str(keyword)
    keyword = re.sub(r'^\s*\[QQ小程序\]\s*', '', keyword)
    keyword = re.sub(r'<[^>]+>', '', keyword)
    keyword = keyword.strip()
    if len(keyword) > 80:
        keyword = keyword[:80]
    return keyword


def get_nested_value(data: dict[str, Any], key_path: list[str]) -> Any:
    current_value = data
    for key in key_path:
        if not isinstance(current_value, dict):
            return None
        current_value = current_value.get(key)
    return current_value


def collect_strings(data: Any) -> list[str]:
    string_list = []
    if isinstance(data, str):
        string_list.append(data)
    elif isinstance(data, dict):
        for value in data.values():
            string_list.extend(collect_strings(value))
    elif isinstance(data, list):
        for value in data:
            string_list.extend(collect_strings(value))
    elif data is not None:
        string_list.append(safe_str(data))
    return string_list


def build_dedupe_key(plugin_event, video_ref: dict[str, str]) -> str:
    try:
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        group_key = get_group_key(plugin_event)
        video_key = video_ref.get('bvid') or video_ref.get('aid') or ''
        return f'{bot_hash}|{group_key}|{video_key}'
    except Exception:
        return ''


def is_recent_duplicate(dedupe_key: str) -> bool:
    if not dedupe_key:
        return False
    now_time = time.time()
    expire_recent_keys(now_time)
    return now_time - gRecentKeyTime.get(dedupe_key, 0) < RECENT_TTL_SECONDS


def mark_recent_key(dedupe_key: str) -> None:
    if dedupe_key:
        gRecentKeyTime[dedupe_key] = time.time()


def expire_recent_keys(now_time: float) -> None:
    expired_key_list = [
        key
        for key, key_time in gRecentKeyTime.items()
        if now_time - key_time >= RECENT_TTL_SECONDS
    ]
    for key in expired_key_list:
        gRecentKeyTime.pop(key, None)


def op_escape(text: str) -> str:
    return (
        safe_str(text)
        .replace('&', '&amp;')
        .replace('[', '&#91;')
        .replace(']', '&#93;')
        .replace(',', '&#44;')
    )


def safe_str(value: Any) -> str:
    if value is None:
        return ''
    return str(value)


def shorten_text(text: str, max_length: int) -> str:
    clean_text = re.sub(r'\s+', ' ', text).strip()
    if len(clean_text) <= max_length:
        return clean_text or '无简介'
    return f'{clean_text[:max_length - 1]}…'
