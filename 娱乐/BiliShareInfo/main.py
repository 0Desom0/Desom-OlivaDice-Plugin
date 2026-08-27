import copy
import difflib
import hashlib
import html
import json
import os
import random
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from typing import Any

import BiliShareInfo  # noqa: F401

try:
    import OlivaDiceCore

    HAS_OLIVA_DICE_CORE = True
except Exception:
    OlivaDiceCore = None
    HAS_OLIVA_DICE_CORE = False


# 插件标识与数据目录
gProc = None
gPluginName = 'BiliShareInfo'

PLUGIN_NAMESPACE = 'BiliShareInfo'
DATA_ROOT = os.path.join('plugin', 'data', PLUGIN_NAMESPACE)
LEGACY_DATA_ROOT = os.path.join('data', PLUGIN_NAMESPACE)

# 默认配置
DEFAULT_CONFIG = {
    'global_enable': True,
    'default_group_enable': True,
    'single_forward_enable': False,
    'multi_forward_enable': True,
    'live_enable': True,
    'parse_debug_enable': False,
    'preview_ocr_enable': True,
    'configured_master_list': [],
}

DEFAULT_GROUP_CONFIG = {
    'groups': {},
    'live_groups': {},
}

# 运行期状态
DATA_LOCK = threading.RLock()
gRecentKeyTime = {}
gParseDebugContext = ContextVar('BiliShareInfo_parse_debug', default=False)
gPreviewOcrLock = threading.RLock()
gPreviewOcrEngine = None
gPreviewOcrUnavailable = False
gWbiMixinKey = None
gWbiMixinKeyTime = 0.0
gHttpThrottleLock = threading.Lock()
gHttpLastRequestTime = 0.0
gHttpBlockedContext = ContextVar('BiliShareInfo_http_blocked', default=None)
gParseNoticeContext = ContextVar('BiliShareInfo_parse_notice', default=None)
gApiCache = {}
gApiCacheLock = threading.RLock()

# 命令与解析常量
COMMAND_PREFIXES = ('.', '/', '。')
HTTP_TIMEOUT = 8
RECENT_TTL_SECONDS = 30
PARSE_LOG_LEVEL = 2
MIN_TITLE_SEARCH_SIGNAL_LENGTH = 3
PREVIEW_OCR_MAX_BYTES = 4 * 1024 * 1024
CARD_SEARCH_WORKERS = 2
CARD_SEARCH_CANDIDATE_LIMIT = 20
OWNER_EXACT_DETAIL_LIMIT = 8
LIVE_ROOM_API = 'https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo'
WBI_KEY_CACHE_TTL_SECONDS = 3600
# B 站公开接口按 IP 限流，超额时直接返回 412，需要重试并控制请求节奏。
HTTP_RETRY_STATUS_SET = frozenset({412, 429, 500, 502, 503, 504})
HTTP_MAX_ATTEMPTS = 4
HTTP_RETRY_BASE_DELAY_SECONDS = 0.45
HTTP_MIN_REQUEST_INTERVAL_SECONDS = 0.15
# 命中一次就缓存一段时间，重复分享同一个视频不再重复触发风控。
API_CACHE_TTL_SECONDS = 300
API_CACHE_MAX_ENTRIES = 256
# 卡片没有 BV/av 号时只能靠标题反查，标题对不上的候选一律不作为结果。
CARD_TITLE_MATCH_MIN_RATIO = 0.72
CARD_TITLE_MATCH_MIN_ORDERED_COVERAGE = 0.8
CARD_TITLE_MATCH_MIN_PREFIX_LENGTH = 6
PARSE_FAILURE_NOTICE_LIMIT = 3
TITLE_TRAILING_ELLIPSIS_PATTERN = re.compile(r'(?:\.{2,}|。{2,}|…+)\s*$')
WBI_MIXIN_KEY_TABLE = (
    46, 47, 18, 2, 53, 8, 23, 32,
    15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19,
    29, 28, 37, 1, 4, 51, 17, 25,
)

REPLY_SEGMENT_PATTERN = re.compile(
    r'^\[(?:OP|CQ):reply(?:,[^\]]*)?\]',
    re.IGNORECASE,
)
AT_SEGMENT_PATTERN = re.compile(
    r'^\[(?:OP|CQ):at,(?P<params>[^\]]*)\]',
    re.IGNORECASE,
)
AV_REFERENCE_PATTERN = re.compile(
    r'(?<![A-Za-z0-9_-])(?:av|aid\s*=\s*)(\d+)(?![A-Za-z0-9])',
    re.IGNORECASE,
)
LIVE_ROOM_ID_PATTERN = re.compile(
    r'(?i)(?:https?://)?live\.bilibili\.com/(?:h5/)?(?P<room_id>\d+)'
)


def _safe_text(value):
    try:
        return str(value)
    except Exception:
        return ''


def _op_escape(value):
    return (
        _safe_text(value)
        .replace('&', '&amp;')
        .replace('[', '&#91;')
        .replace(']', '&#93;')
        .replace(',', '&#44;')
    )


def _current_bot_target_ids(plugin_event):
    target_ids = []
    try:
        target_ids.append(plugin_event.base_info.get('self_id'))
    except Exception:
        pass
    try:
        target_ids.append(plugin_event.bot_info.id)
    except Exception:
        pass
    try:
        extend = getattr(plugin_event.data, 'extend', {}) or {}
        target_ids.extend([
            extend.get('sub_self_id'),
            extend.get('sub_self_open_id'),
        ])
    except Exception:
        pass
    return {
        _safe_text(target_id).strip()
        for target_id in target_ids
        if target_id is not None and _safe_text(target_id).strip()
    }


def parse_command_message(plugin_event, message):
    remaining = _safe_text(message).lstrip()
    while True:
        matched_reply = REPLY_SEGMENT_PATTERN.match(remaining)
        if not matched_reply:
            break
        remaining = remaining[matched_reply.end():].lstrip()

    leading_at_ids = []
    while True:
        matched_at = AT_SEGMENT_PATTERN.match(remaining)
        if not matched_at:
            break
        params = {}
        for item in matched_at.group('params').split(','):
            key, separator, value = item.partition('=')
            if separator:
                params[key.strip().casefold()] = value.strip()
        leading_at_ids.append(params.get('id') or params.get('qq') or '')
        remaining = remaining[matched_at.end():].lstrip()

    if leading_at_ids:
        current_ids = _current_bot_target_ids(plugin_event)
        current_ids.add('all')
        if not any(_safe_text(target_id).strip() in current_ids for target_id in leading_at_ids):
            return None
    return remaining


def prepare_current_message(plugin_event, message: str) -> tuple[str, bool]:
    has_reference = has_message_reference(plugin_event, message)
    if not has_reference:
        return message, False
    return strip_leading_reply_context(message), True


def has_message_reference(plugin_event, message: str) -> bool:
    if has_leading_reply_segment(message):
        return True

    try:
        event_extend = getattr(plugin_event.data, 'extend', {})
    except Exception:
        event_extend = {}
    if isinstance(event_extend, dict):
        if event_extend.get('qq_reference_message_id') or event_extend.get('qq_ref_msg_idx'):
            return True
        qq_event_data = event_extend.get('qq_event_data')
        if isinstance(qq_event_data, dict):
            message_reference = qq_event_data.get('message_reference')
            if isinstance(message_reference, dict) and message_reference.get('message_id'):
                return True

    try:
        message_sdk = getattr(plugin_event.data, 'message_sdk', None)
    except Exception:
        message_sdk = None
    return message_object_has_leading_reply(message_sdk)


def has_leading_reply_segment(message: str) -> bool:
    remaining = safe_str(message).lstrip()
    while remaining:
        reply_match = REPLY_SEGMENT_PATTERN.match(remaining)
        if reply_match:
            return True
        at_match = AT_SEGMENT_PATTERN.match(remaining)
        if not at_match:
            return False
        remaining = remaining[at_match.end():].lstrip()
    return False


def strip_leading_reply_context(message: str) -> str:
    original_message = safe_str(message)
    remaining = original_message.lstrip()
    found_reply = False
    while remaining:
        reply_match = REPLY_SEGMENT_PATTERN.match(remaining)
        if reply_match:
            found_reply = True
            remaining = remaining[reply_match.end():].lstrip()
            continue
        at_match = AT_SEGMENT_PATTERN.match(remaining)
        if not at_match:
            break
        remaining = remaining[at_match.end():].lstrip()
    return remaining if found_reply else original_message


def message_object_has_leading_reply(message_object: Any) -> bool:
    if message_object is None:
        return False
    for attribute_name in ['data', 'data_raw']:
        message_segments = getattr(message_object, attribute_name, None)
        if not isinstance(message_segments, list):
            continue
        for message_segment in message_segments:
            if isinstance(message_segment, dict):
                segment_type = safe_str(message_segment.get('type')).casefold()
            else:
                segment_type = safe_str(getattr(message_segment, 'type', '')).casefold()
            if segment_type == 'reply':
                return True
            if segment_type != 'at':
                break
    return False


def reply_message(plugin_event, message):
    final_message = _safe_text(message)
    try:
        is_group = plugin_event.plugin_info.get('func_type') == 'group_message'
        message_id = _safe_text(plugin_event.data.message_id).strip()
        if is_group and message_id and message_id != '-1':
            final_message = f'[OP:reply,id={_op_escape(message_id)}]{final_message}'
    except Exception:
        pass
    return plugin_event.reply(final_message)


class Event:
    def init(plugin_event, Proc):
        global gProc
        gProc = Proc
        load_config()

    def init_after(plugin_event, Proc):
        global gProc
        gProc = Proc
        initialize_all_bot_data(Proc)

    def save(plugin_event, Proc):
        save_config()

    def private_message(plugin_event, Proc):
        handle_message(plugin_event, is_group=False)

    def group_message(plugin_event, Proc):
        handle_message(plugin_event, is_group=True)


def handle_message(plugin_event, is_group: bool) -> None:
    debug_token = None
    blocked_token = None
    notice_token = None
    try:
        message = safe_str(plugin_event.data.message)
        command_message = parse_command_message(plugin_event, message)
        if command_message is not None and handle_command(plugin_event, command_message, is_group):
            return
        if not is_group:
            return
        group_enabled = is_group_enabled(plugin_event)
        live_enabled = is_live_enabled(plugin_event)
        if not group_enabled and not live_enabled:
            return

        current_message, has_reference = prepare_current_message(plugin_event, message)
        is_candidate = is_parse_candidate_message(
            plugin_event,
            current_message,
            include_event_cards=not has_reference,
        )
        if not is_candidate:
            return

        debug_token = gParseDebugContext.set(is_parse_debug_enabled(plugin_event))
        blocked_token = gHttpBlockedContext.set([])
        notice_token = gParseNoticeContext.set([])
        parse_log(
            f'开始处理候选消息 group={is_group} '
            f'group_key={get_group_key(plugin_event)} '
            f'platform={safe_str(getattr(plugin_event, "platform", {}))} '
            f'has_reference={has_reference} '
            f'message={shorten_log_text(current_message, 240)}'
        )
        parse_log(f'群解析开关 enabled={group_enabled}')
        parse_log(f'本群直播解析开关 enabled={live_enabled}')
        if has_reference:
            parse_log('当前消息带引用，仅解析引用后的文本，跳过extend/message_sdk卡片')

        video_ref_list = extract_video_refs_from_event(
            plugin_event,
            current_message,
            include_event_cards=not has_reference,
            video_enable=group_enabled,
            live_enable=live_enabled,
        )
        parse_log(f'消息引用提取完成 count={len(video_ref_list)} refs={format_video_ref_list(video_ref_list)}')
        if not video_ref_list:
            send_parse_failure_notice(plugin_event)
            return

        video_info_list = []
        sent_dedupe_key_list = []
        for video_ref in video_ref_list:
            dedupe_key = build_dedupe_key(plugin_event, video_ref)
            if is_recent_duplicate(dedupe_key):
                parse_log(f'跳过近期重复引用 ref={format_video_ref(video_ref)}')
                continue
            if is_live_ref(video_ref):
                video_info = fetch_live_info(video_ref)
            else:
                video_info = fetch_video_info(video_ref)
            if not video_info:
                parse_log(f'媒体信息获取失败 ref={format_video_ref(video_ref)}')
                add_parse_notice(build_fetch_failure_notice(video_ref))
                continue
            video_info_list.append(video_info)
            sent_dedupe_key_list.append(dedupe_key)

        if not video_info_list:
            send_parse_failure_notice(plugin_event)
            return

        send_video_info_list(plugin_event, video_info_list)
        parse_log(f'媒体信息发送完成 count={len(video_info_list)}')
        for dedupe_key in sent_dedupe_key_list:
            mark_recent_key(dedupe_key)
        send_parse_failure_notice(plugin_event)
    except Exception as exception_object:
        parse_log(
            f'处理消息异常 error={type(exception_object).__name__}: '
            f'{shorten_log_text(exception_object, 240)}'
        )
    finally:
        if debug_token is not None:
            gParseDebugContext.reset(debug_token)
        if blocked_token is not None:
            gHttpBlockedContext.reset(blocked_token)
        if notice_token is not None:
            gParseNoticeContext.reset(notice_token)


def add_parse_notice(notice_text: str) -> None:
    """登记一条待回复的解析失败提示，避免同一条消息重复提示。"""
    notice_text = safe_str(notice_text).strip()
    if not notice_text:
        return
    notice_list = gParseNoticeContext.get()
    if notice_list is None:
        return
    if notice_text not in notice_list:
        notice_list.append(notice_text)


def send_parse_failure_notice(plugin_event) -> None:
    """把本次解析累积的失败原因回复给用户，而不是静默什么都不做。"""
    notice_list = gParseNoticeContext.get()
    if not notice_list:
        return
    del notice_list[PARSE_FAILURE_NOTICE_LIMIT:]

    dedupe_key = build_notice_dedupe_key(plugin_event, notice_list)
    if is_recent_duplicate(dedupe_key):
        parse_log(f'跳过近期重复的解析失败提示 count={len(notice_list)}')
        notice_list.clear()
        return

    reply_message(plugin_event, '\n'.join(notice_list))
    mark_recent_key(dedupe_key)
    bili_log(f'已回复解析失败提示 count={len(notice_list)}', 2)
    notice_list.clear()


def build_card_failure_notice(title_hint: str) -> str:
    card_title = shorten_text(clean_search_keyword(title_hint), 40)
    title_part = f'「{card_title}」' if card_title else '该分享'
    if has_http_blocked():
        return (
            f'B站解析失败：{title_part}没有携带BV号，'
            f'反查时B站接口被限流，稍后再发一次即可。'
        )
    return (
        f'B站解析失败：{title_part}没有携带BV号，'
        f'也没有找到标题完全一致的视频，无法确认是哪一个。'
    )


def build_fetch_failure_notice(video_ref: dict[str, str]) -> str:
    if video_ref.get('live_id'):
        target = f'直播间 {video_ref["live_id"]}'
    elif video_ref.get('bvid'):
        target = safe_str(video_ref['bvid'])
    elif video_ref.get('aid'):
        target = f'av{video_ref["aid"]}'
    else:
        target = '该链接'
    if has_http_blocked():
        return f'B站解析失败：{target} 的信息获取被B站限流，稍后再发一次即可。'
    return f'B站解析失败：没能获取到 {target} 的信息。'


def build_notice_dedupe_key(plugin_event, notice_list: list[str]) -> str:
    try:
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        group_key = get_group_key(plugin_event)
        notice_digest = hashlib.md5(
            '\n'.join(notice_list).encode('utf-8')
        ).hexdigest()
        return f'notice|{bot_hash}|{group_key}|{notice_digest}'
    except Exception:
        return 'notice|unknown'


def bili_log(message_text: str, level: int = 2) -> None:
    try:
        if gProc is None:
            return
        gProc.log(level, f'[{PLUGIN_NAMESPACE}] {message_text}', [])
    except Exception:
        try:
            if gProc is not None:
                gProc.log(level, f'[{PLUGIN_NAMESPACE}] {message_text}')
        except Exception:
            return


def parse_log(message_text: str) -> None:
    if not gParseDebugContext.get():
        return
    bili_log(message_text, PARSE_LOG_LEVEL)


def log_resolved_video_refs(video_ref_list: list[dict[str, str]]) -> None:
    for video_ref in video_ref_list:
        if video_ref.get('bvid'):
            bili_log(f'解析出BV号: {video_ref["bvid"]}', 2)
        elif video_ref.get('aid'):
            bili_log(f'解析出av号: av{video_ref["aid"]}', 2)
        elif video_ref.get('live_id'):
            bili_log(f'解析出直播间号: {video_ref["live_id"]}', 2)


def handle_command(plugin_event, message: str, is_group: bool) -> bool:
    command_info = parse_bili_command(message)
    if command_info is None:
        return False

    if not command_info:
        return False

    command_scope = command_info.get('scope', '')
    command_action = command_info.get('action', '')

    if command_scope == 'help':
        reply_message(plugin_event, build_help_message(plugin_event, is_group))
        plugin_event.set_block()
        return True

    if command_scope == 'global':
        if command_action not in ['on', 'off']:
            reply_message(plugin_event, '用法：.bili global on/off')
            plugin_event.set_block()
            return True
        if not has_global_switch_permission(plugin_event):
            reply_message(plugin_event, '权限不足：只有骰主可以切换全局开关。')
            plugin_event.set_block()
            return True

        set_global_enable(plugin_event, command_action == 'on')
        reply_message(plugin_event, f'B站解析全局开关已{"开启" if command_action == "on" else "关闭"}。')
        plugin_event.set_block()
        return True

    if command_scope == 'parse_debug':
        if command_action not in ['on', 'off']:
            reply_message(plugin_event, '用法：.bili debug on/off')
            plugin_event.set_block()
            return True
        if not has_global_switch_permission(plugin_event):
            reply_message(plugin_event, '权限不足：只有骰主可以切换解析调试日志。')
            plugin_event.set_block()
            return True

        set_parse_debug_enable(plugin_event, command_action == 'on')
        reply_message(
            plugin_event,
            f'解析调试日志已{"开启" if command_action == "on" else "关闭"}。',
        )
        plugin_event.set_block()
        return True

    if command_scope == 'preview_ocr':
        if command_action not in ['on', 'off']:
            reply_message(plugin_event, '用法：.bili ocr on/off')
            plugin_event.set_block()
            return True
        if not has_global_switch_permission(plugin_event):
            reply_message(plugin_event, '权限不足：只有骰主可以切换预览图OCR匹配。')
            plugin_event.set_block()
            return True

        set_preview_ocr_enable(plugin_event, command_action == 'on')
        reply_message(
            plugin_event,
            f'预览图OCR匹配已{"开启" if command_action == "on" else "关闭"}。',
        )
        plugin_event.set_block()
        return True

    if command_scope == 'live':
        if command_action not in ['on', 'off']:
            reply_message(plugin_event, '用法：.bili live on/off')
            plugin_event.set_block()
            return True
        if not is_group:
            reply_message(plugin_event, '直播解析开关只能在群聊中使用。')
            plugin_event.set_block()
            return True
        if not has_group_switch_permission(plugin_event):
            reply_message(plugin_event, '权限不足：只有群主、群管理或骰主可以切换本群直播解析。')
            plugin_event.set_block()
            return True

        set_live_enable(plugin_event, command_action == 'on')
        reply_message(
            plugin_event,
            f'本群B站直播解析已{"开启" if command_action == "on" else "关闭"}。',
        )
        plugin_event.set_block()
        return True

    if command_scope == 'default_group':
        if command_action not in ['on', 'off']:
            reply_message(plugin_event, '用法：.bili default on/off')
            plugin_event.set_block()
            return True
        if not has_global_switch_permission(plugin_event):
            reply_message(plugin_event, '权限不足：只有骰主可以切换本群默认开关。')
            plugin_event.set_block()
            return True

        set_default_group_enable(plugin_event, command_action == 'on')
        reply_message(plugin_event, f'本群B站解析默认状态已设为{"开启" if command_action == "on" else "关闭"}。')
        plugin_event.set_block()
        return True

    if command_scope in ['single_forward', 'multi_forward']:
        if command_action not in ['on', 'off']:
            reply_message(plugin_event, '用法：.bili singleforward on/off 或 .bili multiforward on/off')
            plugin_event.set_block()
            return True
        if not has_global_switch_permission(plugin_event):
            reply_message(plugin_event, '权限不足：只有骰主可以切换合并转发。')
            plugin_event.set_block()
            return True

        if command_scope == 'single_forward':
            set_single_forward_enable(plugin_event, command_action == 'on')
            reply_message(plugin_event, f'单链接合并转发已{"开启" if command_action == "on" else "关闭"}。')
        else:
            set_multi_forward_enable(plugin_event, command_action == 'on')
            reply_message(plugin_event, f'多链接合并转发已{"开启" if command_action == "on" else "关闭"}。')
        plugin_event.set_block()
        return True

    if command_scope == 'group':
        if not is_group:
            reply_message(plugin_event, '群级开关只能在群聊中使用。')
            plugin_event.set_block()
            return True
        if not has_group_switch_permission(plugin_event):
            reply_message(plugin_event, '权限不足：只有群主、群管理或骰主可以切换本群开关。')
            plugin_event.set_block()
            return True

        set_group_enable(plugin_event, command_action == 'on')
        reply_message(plugin_event, f'本群B站解析已{"开启" if command_action == "on" else "关闭"}。')
        plugin_event.set_block()
        return True

    reply_message(plugin_event, '用法：.bili on/off 或 .bili global on/off')
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
        if compact_tail in ['debugon', 'debugoff', 'parsedebugon', 'parsedebugoff']:
            action = compact_tail.removeprefix('parsedebug').removeprefix('debug')
            return {'scope': 'parse_debug', 'action': action}
        if compact_tail in ['ocron', 'ocroff', 'previewocron', 'previewocroff']:
            action = compact_tail.removeprefix('previewocr').removeprefix('ocr')
            return {'scope': 'preview_ocr', 'action': action}
        if compact_tail in ['liveon', 'liveoff']:
            return {'scope': 'live', 'action': compact_tail.removeprefix('live')}
        if compact_tail in ['globalon', 'globaloff']:
            return {'scope': 'global', 'action': compact_tail.removeprefix('global')}
        if compact_tail in ['defaulton', 'defaultoff']:
            return {'scope': 'default_group', 'action': compact_tail.removeprefix('default')}
        if compact_tail in ['groupdefaulton', 'groupdefaultoff']:
            return {'scope': 'default_group', 'action': compact_tail.removeprefix('groupdefault')}
        if compact_tail in ['defaultgroupon', 'defaultgroupoff']:
            return {'scope': 'default_group', 'action': compact_tail.removeprefix('defaultgroup')}
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
        op_match = re.match(r'^\[(?:OP|CQ):(?:at|reply)(?:,[^\]]*)?\]\s*', stripped_message, re.IGNORECASE)
        if not op_match:
            return stripped_message
        stripped_message = stripped_message[op_match.end() :].lstrip()


def build_help_message(plugin_event, is_group: bool) -> str:
    return '\n'.join(
        [
            'B站解析帮助',
            '本群开关：.bili on/off（群主、管理员、骰主）',
            '全局开关：.bili global on/off（仅骰主）',
            '本群默认开关：.bili default on/off（仅骰主）',
            '单链接合并转发：.bili singleforward on/off（仅骰主）',
            '多链接合并转发：.bili multiforward on/off（仅骰主）',
            '解析调试日志：.bili debug on/off（仅骰主）',
            '预览图OCR匹配：.bili ocr on/off（仅骰主，可选依赖）',
            '本群直播解析：.bili live on/off（群主、管理员、骰主）',
            '帮助：.bili help',
            '未单独设置的群会使用本群默认开关。',
            '开启后会自动解析群内的B站小程序/链接分享并回复视频或直播信息。',
            '小程序卡片没带BV号且无法确认视频时，会回复解析失败原因。',
        ]
    )


def _migrate_legacy_data_dir() -> None:
    """在初始化时一次性迁移旧数据目录到新位置，然后删除旧目录。"""
    try:
        with DATA_LOCK:
            if os.path.isdir(LEGACY_DATA_ROOT):
                # 创建新目录
                os.makedirs(DATA_ROOT, exist_ok=True)
                # 遍历旧目录中的所有文件和子目录，复制到新位置
                for item in os.listdir(LEGACY_DATA_ROOT):
                    src = os.path.join(LEGACY_DATA_ROOT, item)
                    dst = os.path.join(DATA_ROOT, item)
                    # 如果目标已存在则跳过（保留新目录的内容）
                    if not os.path.exists(dst):
                        if os.path.isdir(src):
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
                # 删除旧目录
                shutil.rmtree(LEGACY_DATA_ROOT)
                bili_log(f'成功迁移数据目录从 {LEGACY_DATA_ROOT} 到 {DATA_ROOT}', 2)
    except Exception as e:
        try:
            bili_log(f'迁移数据目录失败: {e}', 3)
        except Exception:
            pass


def load_config() -> None:
    try:
        with DATA_LOCK:
            os.makedirs(DATA_ROOT, exist_ok=True)
        # 执行一次性的旧目录迁移
        _migrate_legacy_data_dir()
    except Exception:
        pass


def initialize_all_bot_data(Proc) -> None:
    """启动时为所有已加载 Bot 初始化配置目录与数据文件。"""
    try:
        bot_info_dict = getattr(Proc, 'Proc_data', {}).get('bot_info_dict', {})
    except Exception as exception_object:
        bili_log(f'读取 Bot 列表失败: {exception_object}', 3)
        return

    if not isinstance(bot_info_dict, dict):
        bili_log('初始化数据目录失败: bot_info_dict 不是字典。', 3)
        return

    initialized_bot_hash_set = set()
    for raw_bot_hash in bot_info_dict:
        try:
            bot_hash = get_linked_bot_hash(raw_bot_hash)
            if bot_hash in initialized_bot_hash_set:
                continue
            initialized_bot_hash_set.add(bot_hash)

            bot_config = load_bot_config(bot_hash)
            group_config = load_group_config(bot_hash)
            config_saved = save_bot_config(bot_hash, bot_config)
            group_saved = save_group_config(bot_hash, group_config)
            if not config_saved or not group_saved:
                bili_log(f'初始化 Bot 数据失败: {bot_hash}', 3)
        except Exception as exception_object:
            bili_log(f'初始化 Bot 数据失败: {raw_bot_hash}: {exception_object}', 3)


def save_config(plugin_event=None) -> bool:
    return True


def set_global_enable(plugin_event, enable: bool) -> None:
    bot_hash = get_config_bot_hash_from_event(plugin_event)
    bot_config = load_bot_config(bot_hash)
    bot_config['global_enable'] = bool(enable)
    save_bot_config(bot_hash, bot_config)


def set_parse_debug_enable(plugin_event, enable: bool) -> None:
    bot_hash = get_config_bot_hash_from_event(plugin_event)
    bot_config = load_bot_config(bot_hash)
    bot_config['parse_debug_enable'] = bool(enable)
    save_bot_config(bot_hash, bot_config)


def set_preview_ocr_enable(plugin_event, enable: bool) -> None:
    bot_hash = get_config_bot_hash_from_event(plugin_event)
    bot_config = load_bot_config(bot_hash)
    bot_config['preview_ocr_enable'] = bool(enable)
    save_bot_config(bot_hash, bot_config)


def set_default_group_enable(plugin_event, enable: bool) -> None:
    bot_hash = get_config_bot_hash_from_event(plugin_event)
    bot_config = load_bot_config(bot_hash)
    bot_config['default_group_enable'] = bool(enable)
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


def set_live_enable(plugin_event, enable: bool) -> None:
    group_key = get_group_key(plugin_event)
    if group_key:
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        group_config = load_group_config(bot_hash)
        group_config.setdefault('live_groups', {})[group_key] = bool(enable)
        save_group_config(bot_hash, group_config)


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
    return bool(
        group_config.get('groups', {}).get(
            group_key,
                bot_config.get('default_group_enable', True),
        )
    )


def is_parse_debug_enabled(plugin_event) -> bool:
    try:
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        bot_config = load_bot_config(bot_hash)
        return bool(bot_config.get('parse_debug_enable', False))
    except Exception:
        return False


def is_preview_ocr_enabled(plugin_event) -> bool:
    try:
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        bot_config = load_bot_config(bot_hash)
        return bool(bot_config.get('preview_ocr_enable', True))
    except Exception:
        return True


def is_live_enabled(plugin_event) -> bool:
    try:
        bot_hash = get_config_bot_hash_from_event(plugin_event)
        bot_config = load_bot_config(bot_hash)
        if not bool(bot_config.get('global_enable', True)):
            return False
        group_key = get_group_key(plugin_event)
        if not group_key:
            return False
        group_config = load_group_config(bot_hash)
        return bool(
            group_config.get('live_groups', {}).get(
                group_key,
                bot_config.get('live_enable', True),
            )
        )
    except Exception:
        return False


def get_group_key(plugin_event) -> str:
    try:
        host_id = safe_str(getattr(plugin_event.data, 'host_id', None)) or 'none'
        group_id = safe_str(plugin_event.data.group_id)
        return f'{host_id}|{group_id}'
    except Exception:
        return ''


def load_bot_config(bot_hash: Any) -> dict[str, Any]:
    config_file = get_bot_config_file(bot_hash)
    config_data = read_json_file(config_file, DEFAULT_CONFIG)
    normalized_config = normalize_config_data(config_data)
    if config_data != normalized_config:
        write_json_file(config_file, normalized_config)
    return normalized_config


def save_bot_config(bot_hash: Any, config_data: dict[str, Any]) -> bool:
    return write_json_file(get_bot_config_file(bot_hash), normalize_config_data(config_data))


def load_group_config(bot_hash: Any) -> dict[str, Any]:
    group_file = get_group_config_file(bot_hash)
    group_data = read_json_file(group_file, DEFAULT_GROUP_CONFIG)
    normalized_group_data = normalize_group_data(group_data)
    if group_data != normalized_group_data:
        write_json_file(group_file, normalized_group_data)
    return normalized_group_data


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
    normalized_config['default_group_enable'] = bool(config_data.get('default_group_enable', True))
    normalized_config['single_forward_enable'] = bool(config_data.get('single_forward_enable', False))
    normalized_config['multi_forward_enable'] = bool(config_data.get('multi_forward_enable', True))
    normalized_config['live_enable'] = bool(config_data.get('live_enable', True))
    normalized_config['parse_debug_enable'] = bool(config_data.get('parse_debug_enable', False))
    normalized_config['preview_ocr_enable'] = bool(config_data.get('preview_ocr_enable', True))
    normalized_config['configured_master_list'] = normalize_id_list(
        config_data.get('configured_master_list', [])
    )
    return normalized_config


def normalize_group_data(group_data: Any) -> dict[str, Any]:
    normalized_group_data = dict(DEFAULT_GROUP_CONFIG)
    groups = group_data.get('groups', {}) if isinstance(group_data, dict) else {}
    live_groups = group_data.get('live_groups', {}) if isinstance(group_data, dict) else {}
    if not isinstance(groups, dict):
        groups = {}
    if not isinstance(live_groups, dict):
        live_groups = {}
    normalized_group_data['groups'] = {
        safe_str(group_key): bool(enable)
        for group_key, enable in groups.items()
        if safe_str(group_key)
    }
    normalized_group_data['live_groups'] = {
        safe_str(group_key): bool(enable)
        for group_key, enable in live_groups.items()
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
    found_marker = False
    for marker in ['[OP:json', '[CQ:json']:
        start_index = message.find(marker)
        if start_index < 0:
            continue
        found_marker = True
        parse_log(f'发现JSON卡片标记 marker={marker} offset={start_index}')

        data_index = message.find('data=', start_index)
        if data_index < 0:
            parse_log(f'JSON卡片缺少data参数 marker={marker}')
            continue

        brace_index = message.find('{', data_index)
        if brace_index < 0:
            parse_log(f'JSON卡片data中未找到对象 marker={marker}')
            continue

        json_text = extract_balanced_json(message, brace_index)
        if not json_text:
            parse_log(f'JSON卡片对象括号不完整 marker={marker} brace_offset={brace_index}')
            continue

        try:
            card_data = json.loads(html.unescape(json_text))
            if isinstance(card_data, dict):
                parse_log(
                    f'JSON卡片解析成功 keys={format_log_list(list(card_data.keys()), 12)} '
                    f'json_len={len(json_text)}'
                )
                return card_data
            parse_log(f'JSON卡片解析结果不是对象 type={type(card_data).__name__}')
        except Exception as exception_object:
            parse_log(
                f'JSON卡片解析失败 error={type(exception_object).__name__}: '
                f'{shorten_log_text(exception_object, 180)} json_len={len(json_text)}'
            )
    if not found_marker:
        parse_log('消息中未发现OP/CQ JSON卡片标记')
    else:
        parse_log('消息中的JSON卡片标记均未成功解析')
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


def extract_video_refs_from_event(
    plugin_event,
    message: str,
    include_event_cards: bool = True,
    video_enable: bool = True,
    live_enable: bool = False,
) -> list[dict[str, str]]:
    qq_ark_card_list = []
    if include_event_cards:
        qq_ark_card_list = [
            card_data
            for card_data in extract_qq_ark_cards(plugin_event)
            if is_probable_bili_card(card_data)
        ]
    else:
        parse_log('消息带引用，跳过QQ ARK extend/message_sdk卡片提取')
    use_qq_ark_card = bool(qq_ark_card_list)
    parse_log(
        f'卡片来源选择 source={"qq_ark" if use_qq_ark_card else "op_json"} '
        f'qq_ark_count={len(qq_ark_card_list)}'
    )

    if video_enable:
        video_ref_list = extract_video_refs_from_message(
            message,
            include_json_card=not use_qq_ark_card,
            preview_ocr_enable=is_preview_ocr_enabled(plugin_event),
        )
    else:
        video_ref_list = []
        parse_log('本群普通视频解析关闭，跳过视频引用提取')
    seen_key_set = {
        video_key
        for video_ref in video_ref_list
        if (video_key := get_video_ref_key(video_ref))
    }
    if live_enable:
        for live_ref in extract_live_refs_from_text(message):
            add_video_ref(video_ref_list, seen_key_set, live_ref)
        for card_data in qq_ark_card_list:
            for live_ref in extract_live_refs_from_card(card_data):
                add_video_ref(video_ref_list, seen_key_set, live_ref)
    parse_log(f'消息文本解析初始refs={format_video_ref_list(video_ref_list)}')
    url_ref_cache = {}

    parse_log(f'QQ ARK卡片提取数量={len(qq_ark_card_list)}')
    if video_enable:
        for card_index, card_data in enumerate(qq_ark_card_list, start=1):
            add_video_refs_from_card(
                card_data,
                video_ref_list,
                seen_key_set,
                url_ref_cache,
                f'QQ官机ARK卡片#{card_index}',
                preview_ocr_enable=is_preview_ocr_enabled(plugin_event),
            )

    log_resolved_video_refs(video_ref_list)
    return video_ref_list


def extract_qq_ark_cards(plugin_event) -> list[dict[str, Any]]:
    try:
        event_extend = getattr(plugin_event.data, 'extend', {})
    except Exception as exception_object:
        parse_log(
            f'读取事件extend失败 error={type(exception_object).__name__}: '
            f'{shorten_log_text(exception_object, 180)}'
        )
        return []
    if not isinstance(event_extend, dict):
        parse_log(f'事件extend不是字典 type={type(event_extend).__name__}')
        return []

    parse_log(f'事件extend keys={format_log_list(list(event_extend.keys()), 20)}')

    card_data_list = []
    add_unique_card_data(card_data_list, event_extend.get('qq_ark_data'))

    qq_event_data = event_extend.get('qq_event_data')
    if isinstance(qq_event_data, dict):
        add_unique_card_data(card_data_list, qq_event_data.get('ark_data'))
        collect_ark_cards_from_message_elements(qq_event_data.get('msg_elements'), card_data_list)

    collect_ark_cards_from_message_elements(event_extend.get('qq_msg_elements'), card_data_list)
    collect_ark_cards_from_message_object(
        getattr(plugin_event.data, 'message_sdk', None),
        card_data_list,
    )
    parse_log(
        f'QQ ARK卡片收集完成 count={len(card_data_list)} '
        f'card_keys={format_log_list([list(card_data.keys()) for card_data in card_data_list], 8)}'
    )
    return card_data_list


def collect_ark_cards_from_message_elements(message_elements: Any, card_data_list: list[dict[str, Any]]) -> None:
    if not isinstance(message_elements, list):
        return
    for message_element in message_elements:
        if not isinstance(message_element, dict):
            continue
        add_unique_card_data(card_data_list, message_element.get('ark_data'))
        collect_ark_cards_from_message_elements(message_element.get('msg_elements'), card_data_list)


def add_unique_card_data(card_data_list: list[dict[str, Any]], card_data: Any) -> None:
    if isinstance(card_data, dict) and card_data not in card_data_list:
        card_data_list.append(card_data)


def collect_ark_cards_from_message_object(
    message_object: Any,
    card_data_list: list[dict[str, Any]],
) -> None:
    """兼容部分适配器只把 JSON 卡片保留在 message_sdk.data 的情况。"""
    if message_object is None:
        return
    for attribute_name in ['data', 'data_raw']:
        message_segments = getattr(message_object, attribute_name, None)
        if not isinstance(message_segments, list):
            continue
        for message_segment in message_segments:
            if isinstance(message_segment, dict):
                add_unique_card_data(card_data_list, message_segment.get('ark_data'))
                add_card_payload(message_segment.get('data'), card_data_list)
                continue
            segment_type = safe_str(getattr(message_segment, 'type', '')).casefold()
            if segment_type in ['json', 'ark', 'light_app']:
                add_card_payload(getattr(message_segment, 'data', None), card_data_list)


def add_card_payload(payload: Any, card_data_list: list[dict[str, Any]]) -> None:
    if isinstance(payload, dict):
        if set(payload).issubset({'data', 'resid'}) and 'data' in payload:
            add_card_payload(payload.get('data'), card_data_list)
            return
        add_unique_card_data(card_data_list, payload)
        nested_payload = payload.get('data')
        if isinstance(nested_payload, (dict, str)):
            add_card_payload(nested_payload, card_data_list)
        return
    if not isinstance(payload, str) or not payload.strip():
        return
    try:
        parsed_payload = json.loads(html.unescape(payload))
    except Exception:
        return
    add_card_payload(parsed_payload, card_data_list)


def is_parse_candidate_message(
    plugin_event,
    message: str,
    include_event_cards: bool = True,
) -> bool:
    """仅对可能包含 B 站引用的消息开启解析诊断日志。"""
    if (
        extract_video_refs_from_text(message)
        or extract_live_refs_from_text(message)
        or extract_urls(message)
    ):
        return True

    lowered_message = safe_str(message).lower()
    if '[op:json' in lowered_message or '[cq:json' in lowered_message:
        return True
    if '卡片消息' in message and any(
        keyword in lowered_message
        for keyword in ['bilibili', 'b23.tv', 'bili2233.cn', '哔哩哔哩', 'bili']
    ):
        return True

    if include_event_cards:
        for card_data in extract_qq_ark_cards(plugin_event):
            if is_probable_bili_card(card_data):
                return True
    return False


def extract_video_refs_from_message(
    message: str,
    include_json_card: bool = True,
    preview_ocr_enable: bool = True,
) -> list[dict[str, str]]:
    video_ref_list = []
    seen_key_set = set()
    url_ref_cache = {}
    has_escaped_slash = '\\/' in message
    parse_log(
        f'开始解析消息文本 length={len(message)} escaped_slash={has_escaped_slash} '
        f'text={shorten_log_text(message, 240)}'
    )

    text_video_ref_list = extract_video_refs_from_text(message)
    if text_video_ref_list:
        parse_log(f'原始文本BV/av={format_video_ref_list(text_video_ref_list)}')
    for video_ref in text_video_ref_list:
        add_video_ref(video_ref_list, seen_key_set, video_ref)

    message_url_list = extract_urls(message)
    if message_url_list:
        parse_log(
            f'原始消息URL count={len(message_url_list)} escaped_slash={has_escaped_slash} '
            f'urls={format_log_list(message_url_list, 5)}'
        )
    for url in message_url_list:
        video_ref = resolve_video_ref_from_url_cached(url, url_ref_cache)
        parse_log(f'原始消息URL解析 url={shorten_log_text(url, 180)} ref={format_video_ref(video_ref)}')
        add_video_ref(video_ref_list, seen_key_set, video_ref)

    if not include_json_card:
        parse_log('已选择QQ ARK卡片来源，跳过消息内OP/CQ JSON卡片解析')
        return video_ref_list

    card_data = extract_json_card(message)
    if not card_data:
        parse_log(f'未解析到消息内JSON卡片，当前refs={format_video_ref_list(video_ref_list)}')
        return video_ref_list

    add_video_refs_from_card(
        card_data,
        video_ref_list,
        seen_key_set,
        url_ref_cache,
        'JSON卡片',
        preview_ocr_enable=preview_ocr_enable,
    )
    return video_ref_list


def add_video_refs_from_card(
    card_data: dict[str, Any],
    video_ref_list: list[dict[str, str]],
    seen_key_set: set[str],
    url_ref_cache: dict[str, dict[str, str] | None],
    card_label: str,
    preview_ocr_enable: bool = True,
) -> None:
    is_bili_card = is_probable_bili_card(card_data)
    parse_log(
        f'{card_label} probable_bili={is_bili_card} keys={format_log_list(list(card_data.keys()), 12)} '
        f'title_hint={shorten_log_text(get_title_hint(card_data), 120)}'
    )
    if not is_bili_card:
        return

    card_url_list = extract_urls_from_card(card_data)
    parse_log(f'{card_label} URL count={len(card_url_list)} urls={format_log_list(card_url_list, 8)}')

    card_video_ref_list = find_video_refs(card_data, url_ref_cache)
    parse_log(f'{card_label} 字段解析refs={format_video_ref_list(card_video_ref_list)}')
    for video_ref in card_video_ref_list:
        add_video_ref(video_ref_list, seen_key_set, video_ref)

    if not card_video_ref_list and not video_ref_list:
        if extract_live_refs_from_card(card_data):
            parse_log(f'{card_label} 识别为直播卡片，跳过视频标题搜索')
            return
        title_hint = get_title_hint(card_data)
        parse_log(
            f'{card_label} 未解析到显式视频引用，进入OCR/标题并行搜索 '
            f'keyword={shorten_log_text(title_hint, 120)}'
        )
        video_ref = search_video_by_card_comparison(
            card_data,
            title_hint,
            preview_ocr_enable=preview_ocr_enable,
        )
        parse_log(
            f'{card_label} OCR/标题对比结果 ref={format_video_ref(video_ref)} '
            f'http_blocked={format_http_blocked_log()}'
        )
        if not video_ref:
            add_parse_notice(build_card_failure_notice(title_hint))
            bili_log(
                f'小程序卡片无法确认视频 blocked={has_http_blocked()} '
                f'title={shorten_text(clean_search_keyword(title_hint), 60)}',
                2,
            )
        add_video_ref(video_ref_list, seen_key_set, video_ref)
    elif not card_video_ref_list:
        parse_log(f'{card_label} 消息中已有视频引用，跳过卡片标题搜索')


def find_video_refs(
    card_data: dict[str, Any],
    url_ref_cache: dict[str, dict[str, str] | None] | None = None,
) -> list[dict[str, str]]:
    video_ref_list = []
    seen_key_set = set()
    string_list = collect_strings(card_data)
    parse_log(f'卡片字符串字段数量={len(string_list)}')
    for field_index, text in enumerate(string_list, start=1):
        text_ref_list = extract_video_refs_from_text(text)
        text_url_list = extract_urls(text)
        if text_ref_list or text_url_list:
            parse_log(
                f'卡片字段#{field_index} text={shorten_log_text(text, 240)} '
                f'text_refs={format_video_ref_list(text_ref_list)} '
                f'urls={format_log_list(text_url_list, 6)}'
            )
        for video_ref in text_ref_list:
            add_video_ref(video_ref_list, seen_key_set, video_ref)

    for text in string_list:
        url_list = extract_urls(text)
        for url in url_list:
            video_ref = resolve_video_ref_from_url_cached(url, url_ref_cache)
            parse_log(
                f'卡片URL解析 url={shorten_log_text(url, 180)} '
                f'ref={format_video_ref(video_ref)}'
            )
            add_video_ref(video_ref_list, seen_key_set, video_ref)
    parse_log(f'卡片字段解析汇总 refs={format_video_ref_list(video_ref_list)}')
    return video_ref_list


def extract_urls_from_card(card_data: dict[str, Any]) -> list[str]:
    result = []
    for text in collect_strings(card_data):
        for url in extract_urls(text):
            if url not in result:
                result.append(url)
    return result


def extract_video_ref_from_text(text: str) -> dict[str, str] | None:
    video_ref_list = extract_video_refs_from_text(text)
    if video_ref_list:
        return video_ref_list[0]
    return None


def extract_video_refs_from_text(text: str) -> list[dict[str, str]]:
    unescaped_text = html.unescape(safe_str(text))
    video_ref_list = []
    seen_key_set = set()

    text_candidates = [unescaped_text]
    decoded_text = urllib.parse.unquote(unescaped_text)
    if decoded_text != unescaped_text:
        text_candidates.append(decoded_text)

    for text_candidate in text_candidates:
        for bvid_match in re.finditer(r'(BV[0-9A-Za-z]{10})', text_candidate):
            add_video_ref(video_ref_list, seen_key_set, {'bvid': bvid_match.group(1)})

        for aid_match in AV_REFERENCE_PATTERN.finditer(text_candidate):
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
    if video_ref.get('live_id'):
        return f'live:{video_ref["live_id"]}'
    return ''


def format_video_ref(video_ref: dict[str, str] | None) -> str:
    if not video_ref:
        return 'None'
    video_key = get_video_ref_key(video_ref)
    if video_key:
        return video_key
    return safe_str(video_ref)


def format_video_ref_list(video_ref_list: list[dict[str, str]]) -> str:
    if not video_ref_list:
        return '[]'
    return '[' + ', '.join(format_video_ref(video_ref) for video_ref in video_ref_list) + ']'


def format_log_list(value_list: list[Any], limit: int) -> str:
    shown_list = [shorten_log_text(safe_str(value), 180) for value in value_list[:limit]]
    if len(value_list) > limit:
        shown_list.append(f'...(+{len(value_list) - limit})')
    return '[' + ', '.join(shown_list) + ']'


def shorten_log_text(text: Any, limit: int = 300) -> str:
    value = safe_str(text).replace('\r', '\\r').replace('\n', '\\n')
    if len(value) <= limit:
        return value
    return f'{value[:limit]}...'


def is_live_ref(video_ref: dict[str, str] | None) -> bool:
    return bool(video_ref and safe_str(video_ref.get('live_id', '')).strip())


def is_live_bilibili_url(url: str) -> bool:
    try:
        raw_url = safe_str(url).strip()
        if not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', raw_url):
            raw_url = f'https://{raw_url}'
        return urllib.parse.urlsplit(raw_url).netloc.casefold().rstrip('.') == 'live.bilibili.com'
    except Exception:
        return False


def extract_live_ref_from_url(url: str) -> dict[str, str] | None:
    try:
        raw_url = safe_str(url).strip()
        if not raw_url:
            return None
        if not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', raw_url):
            raw_url = f'https://{raw_url}'
        parsed_url = urllib.parse.urlsplit(raw_url)
        if parsed_url.netloc.casefold().rstrip('.') != 'live.bilibili.com':
            return None
        path_match = re.match(r'^/(?:h5/)?(?P<room_id>\d+)(?:/|$)', parsed_url.path)
        room_id = path_match.group('room_id') if path_match else ''
        if not room_id:
            query_data = urllib.parse.parse_qs(parsed_url.query)
            room_id = safe_str(
                (query_data.get('room_id') or query_data.get('roomid') or [''])[0]
            ).strip()
        if not room_id or not room_id.isdigit() or int(room_id) <= 0:
            return None
        return {'live_id': room_id}
    except Exception:
        return None


def extract_live_refs_from_text(text: str) -> list[dict[str, str]]:
    live_ref_list = []
    seen_key_set = set()
    for url in extract_urls(text):
        live_ref = extract_live_ref_from_url(url)
        add_video_ref(live_ref_list, seen_key_set, live_ref)
    for room_match in LIVE_ROOM_ID_PATTERN.finditer(html.unescape(safe_str(text))):
        add_video_ref(
            live_ref_list,
            seen_key_set,
            {'live_id': room_match.group('room_id')},
        )
    return live_ref_list


def extract_live_refs_from_card(card_data: dict[str, Any]) -> list[dict[str, str]]:
    live_ref_list = []
    seen_key_set = set()
    for text in collect_strings(card_data):
        for live_ref in extract_live_refs_from_text(text):
            add_video_ref(live_ref_list, seen_key_set, live_ref)
    return live_ref_list


def extract_urls(text: str) -> list[str]:
    clean_text = urllib.parse.unquote(html.unescape(safe_str(text))).replace('\\/', '/')
    url_pattern = (
        r'https?://live\.bilibili\.com/[^\s"\'<>]+|'
        r'https?://(?:www\.|m\.)?bilibili\.com/[^\s"\'<>]+|'
        r'https?://b23\.tv/[^\s"\'<>]+|'
        r'https?://bili2233\.cn/[^\s"\'<>]+|'
        r'https?://m\.q\.qq\.com/[^\s"\'<>]+|'
        r'live\.bilibili\.com/[^\s"\'<>]+|'
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
    live_ref = extract_live_ref_from_url(url)
    if live_ref or is_live_bilibili_url(url):
        parse_log(f'识别为直播间URL，跳过视频链接解析 ref={format_video_ref(live_ref)}')
        return None
    parse_log(f'开始解析URL url={shorten_log_text(url, 180)}')
    direct_ref = extract_video_ref_from_text(url)
    if direct_ref:
        parse_log(f'URL中直接命中视频引用 ref={format_video_ref(direct_ref)}')
        return direct_ref

    request_url_list = build_resolve_url_candidates(url)
    parse_log(f'URL解析候选 count={len(request_url_list)} urls={format_log_list(request_url_list, 5)}')
    for request_url in request_url_list:
        try:
            response_url, response_text = http_get_text(request_url, allow_response_body=True)
        except urllib.error.HTTPError as exception_object:
            video_ref = extract_video_ref_from_http_error(exception_object)
            error_url = get_http_error_url(exception_object)
            if video_ref:
                parse_log(
                    f'HTTP错误响应URL解析成功 url={shorten_log_text(request_url, 180)} '
                    f'final={shorten_log_text(error_url, 180)} ref={format_video_ref(video_ref)}'
                )
                return video_ref
            parse_log(
                f'URL请求失败 url={shorten_log_text(request_url, 180)} '
                f'final={shorten_log_text(error_url, 180)} '
                f'error={type(exception_object).__name__}: {shorten_log_text(exception_object, 160)}'
            )
            continue
        except Exception as exception_object:
            parse_log(
                f'URL请求失败 url={shorten_log_text(request_url, 180)} '
                f'error={type(exception_object).__name__}: {shorten_log_text(exception_object, 160)}'
            )
            continue

        for text in [response_url, response_text]:
            video_ref = extract_video_ref_from_text(text)
            if video_ref:
                if request_url != url:
                    parse_log(
                        f'短链净化后解析成功 original={shorten_log_text(url, 180)} '
                        f'request={shorten_log_text(request_url, 180)} ref={format_video_ref(video_ref)}'
                    )
                return video_ref

        parse_log(
            f'URL响应未找到BV/av url={shorten_log_text(request_url, 180)} '
            f'final={shorten_log_text(response_url, 180)} body_len={len(response_text)}'
        )
    return None


def extract_video_ref_from_http_error(exception_object: urllib.error.HTTPError) -> dict[str, str] | None:
    error_url = get_http_error_url(exception_object)
    video_ref = extract_video_ref_from_text(error_url)
    if video_ref:
        return video_ref

    try:
        response_body = exception_object.read(128 * 1024)
        charset = exception_object.headers.get_content_charset() or 'utf-8'
        response_text = response_body.decode(charset, errors='ignore')
    except Exception:
        return None
    return extract_video_ref_from_text(response_text)


def get_http_error_url(exception_object: urllib.error.HTTPError) -> str:
    try:
        return safe_str(exception_object.geturl())
    except Exception:
        return ''


def resolve_video_ref_from_url_cached(
    url: str,
    url_ref_cache: dict[str, dict[str, str] | None] | None,
) -> dict[str, str] | None:
    if url_ref_cache is None:
        return resolve_video_ref_from_url(url)
    if url not in url_ref_cache:
        parse_log(f'URL缓存未命中 url={shorten_log_text(url, 180)}')
        url_ref_cache[url] = resolve_video_ref_from_url(url)
    else:
        parse_log(
            f'URL缓存命中 url={shorten_log_text(url, 180)} '
            f'ref={format_video_ref(url_ref_cache[url])}'
        )
    return url_ref_cache[url]


def build_resolve_url_candidates(url: str) -> list[str]:
    url = safe_str(url)
    result = []
    parsed_url = urllib.parse.urlsplit(url)
    host = parsed_url.netloc.lower()
    if host in ['b23.tv', 'bili2233.cn']:
        clean_url = urllib.parse.urlunsplit(
            (
                parsed_url.scheme or 'https',
                parsed_url.netloc,
                parsed_url.path.rstrip('/'),
                '',
                '',
            )
        )
        if clean_url:
            result.append(clean_url)

    if url not in result:
        result.append(url)
    return result


def search_video_by_card_comparison(
    card_data: dict[str, Any],
    title_hint: str,
    preview_ocr_enable: bool = True,
) -> dict[str, str] | None:
    """并行获取 OCR 元数据与标题候选，再逐条交叉评分。"""
    parse_log(
        f'开始OCR/标题并行搜索 keyword={shorten_log_text(title_hint, 120)} '
        f'ocr_enabled={preview_ocr_enable}'
    )
    with ThreadPoolExecutor(
        max_workers=CARD_SEARCH_WORKERS,
        thread_name_prefix='BiliShareInfoSearch',
    ) as executor:
        ocr_future = executor.submit(
            copy_context().run,
            search_video_by_preview_metadata_candidate,
            card_data,
            title_hint,
            preview_ocr_enable,
        )
        title_future = executor.submit(
            copy_context().run,
            search_video_candidates_by_keyword,
            title_hint,
            CARD_SEARCH_CANDIDATE_LIMIT,
        )
        ocr_result = get_card_search_future_result(ocr_future, 'OCR')
        title_candidate_list = get_card_search_future_result(title_future, '标题候选')
        if not isinstance(title_candidate_list, list):
            title_candidate_list = []

        ocr_video_ref = None
        preview_metadata = {}
        if isinstance(ocr_result, dict):
            ocr_video_ref = ocr_result.get('video_ref')
            metadata_value = ocr_result.get('preview_metadata')
            if isinstance(metadata_value, dict):
                preview_metadata = metadata_value

        parse_log(
            f'OCR/标题并行搜索完成 ocr_ref={format_video_ref(ocr_video_ref)} '
            f'title_candidates={len(title_candidate_list)} '
            f'ocr_owner={shorten_log_text(preview_metadata.get("owner", ""), 80)} '
            f'ocr_stats={format_preview_stat_log(preview_metadata)}'
        )

        compact_keyword = build_compact_search_keyword(title_hint)
        if (
            compact_keyword
            and compact_keyword != clean_search_keyword(title_hint)
            and not has_exact_title_candidate(title_hint, title_candidate_list)
        ):
            parse_log(
                f'完整标题搜索未命中，补充紧凑关键词搜索 keyword='
                f'{shorten_log_text(compact_keyword, 160)}'
            )
            compact_candidate_list = search_video_candidates_by_keyword(
                compact_keyword,
                CARD_SEARCH_CANDIDATE_LIMIT,
            )
            title_candidate_list.extend(compact_candidate_list)

        owner_name = safe_str(preview_metadata.get('owner', '')).strip()
        # 已有同名候选时仍然补查 OCR 识别出的 UP 主；否则会把“同名但非同一视频”
        # 的全站搜索结果误当成最终结果，失去按投稿数据核验的机会。
        if owner_name and not ocr_video_ref:
            owner_keyword = f'{compact_keyword or title_hint} {owner_name}'
            parse_log(
                f'补充UP主联合搜索 keyword='
                f'{shorten_log_text(owner_keyword, 160)}'
            )
            owner_candidate_list = search_video_candidates_by_keyword(
                owner_keyword,
                CARD_SEARCH_CANDIDATE_LIMIT,
            )
            title_candidate_list.extend(owner_candidate_list)

        ocr_key = get_video_ref_key(ocr_video_ref or {})
        candidate_key_set = {
            get_video_ref_key(build_video_ref_from_archive_candidate(candidate) or {})
            for candidate in title_candidate_list
        }
        if ocr_key and ocr_key not in candidate_key_set:
            ocr_info_future = executor.submit(
                copy_context().run,
                fetch_video_info,
                ocr_video_ref,
            )
            ocr_video_info = get_card_search_future_result(ocr_info_future, 'OCR候选详情')
            ocr_candidate = build_search_candidate_from_video_info(
                ocr_video_ref,
                ocr_video_info,
                'ocr_owner',
            )
            if ocr_candidate:
                title_candidate_list.append(ocr_candidate)

    return choose_card_search_result(
        title_hint,
        preview_metadata,
        title_candidate_list,
    )


def get_card_search_future_result(future, label: str):
    try:
        return future.result()
    except Exception as exception_object:
        parse_log(
            f'{label}异步任务失败 error={type(exception_object).__name__}: '
            f'{shorten_log_text(exception_object, 180)}'
        )
        return None


def choose_card_search_result(
    title_hint: str,
    preview_metadata: dict[str, Any],
    candidate_list: list[dict[str, Any]],
) -> dict[str, str] | None:
    candidate_list = merge_search_candidates(candidate_list)
    scored_candidate_list = []
    exact_candidate_list = []
    for candidate in candidate_list:
        video_ref = build_video_ref_from_archive_candidate(candidate)
        if not video_ref:
            continue
        score, score_detail, is_exact = score_card_search_comparison_candidate(
            title_hint,
            preview_metadata,
            candidate,
        )
        result_rank = int(candidate.get('_search_rank', CARD_SEARCH_CANDIDATE_LIMIT + 1))
        scored_candidate_list.append((score, -result_rank, video_ref, candidate, score_detail))
        if is_exact:
            exact_candidate_list.append((video_ref, candidate))

    scored_candidate_list.sort(key=lambda item: (item[0], item[1]), reverse=True)
    compared_candidate_list = scored_candidate_list[:CARD_SEARCH_CANDIDATE_LIMIT]
    compared_key_set = {
        get_video_ref_key(item[2])
        for item in compared_candidate_list
    }
    exact_candidate_list = [
        item for item in exact_candidate_list
        if get_video_ref_key(item[0]) in compared_key_set
    ]
    parse_log(
        f'卡片候选逐条对比 count={len(compared_candidate_list)} '
        f'total_unique={len(scored_candidate_list)}'
    )
    for candidate_index, (score, _, video_ref, candidate, score_detail) in enumerate(
        compared_candidate_list,
        start=1,
    ):
        parse_log(
            f'卡片候选#{candidate_index} source={safe_str(candidate.get("_search_source", "title"))} '
            f'ref={format_video_ref(video_ref)} '
            f'author={shorten_log_text(candidate.get("author", ""), 80)} '
            f'play={safe_str(candidate.get("play", ""))} '
            f'danmaku={safe_str(candidate.get("video_review", ""))} '
            f'like={safe_str(candidate.get("like", ""))} '
            f'score={score} detail={score_detail}'
        )

    if exact_candidate_list:
        if has_preview_metadata_signal(preview_metadata):
            metadata_candidate_list = []
            for video_ref, candidate in exact_candidate_list:
                metadata_score, metadata_detail = score_preview_metadata_for_search_candidate(
                    preview_metadata,
                    candidate,
                )
                metadata_candidate_list.append(
                    (metadata_score, video_ref, candidate, metadata_detail)
                )
                parse_log(
                    f'卡片同名候选OCR核验 ref={format_video_ref(video_ref)} '
                    f'score={metadata_score} detail={metadata_detail}'
                )
            best_metadata_score = max(item[0] for item in metadata_candidate_list)
            best_metadata_candidates = [
                item for item in metadata_candidate_list
                if item[0] == best_metadata_score
            ]
            _, selected_ref, selected_candidate, _ = random.choice(best_metadata_candidates)
            parse_log(
                f'卡片完整标题匹配按OCR元数据选择 count={len(exact_candidate_list)} '
                f'tied={len(best_metadata_candidates)} '
                f'source={safe_str(selected_candidate.get("_search_source", "title"))} '
                f'ref={format_video_ref(selected_ref)} score={best_metadata_score}'
            )
        else:
            selected_ref, selected_candidate = random.choice(exact_candidate_list)
            parse_log(
                f'卡片完整标题匹配随机选择 count={len(exact_candidate_list)} '
                f'source={safe_str(selected_candidate.get("_search_source", "title"))} '
                f'ref={format_video_ref(selected_ref)}'
            )
        return selected_ref

    if not compared_candidate_list:
        parse_log('卡片候选逐条对比无可用结果')
        return None
    selected_score, _, selected_ref, selected_candidate, _ = compared_candidate_list[0]
    selected_title = clean_search_result_title(selected_candidate.get('title', ''))
    match_level, match_ratio = evaluate_title_match(title_hint, selected_title)
    if match_level not in ['exact', 'strong']:
        # 卡片没有 BV/av 号，标题对不上就无法确认是同一个视频；
        # 宁可不回复，也不要把标题无关的视频当成分享结果发出去。
        parse_log(
            f'卡片候选标题置信度不足，放弃解析 level={match_level} ratio={match_ratio:.2f} '
            f'keyword={shorten_log_text(title_hint, 120)} '
            f'candidate_title={shorten_log_text(selected_title, 120)} '
            f'ref={format_video_ref(selected_ref)} score={selected_score} '
            f'http_blocked={format_http_blocked_log()}'
        )
        return None
    parse_log(
        f'卡片候选评分选择 source={safe_str(selected_candidate.get("_search_source", "title"))} '
        f'ref={format_video_ref(selected_ref)} score={selected_score} '
        f'title_level={match_level} title_ratio={match_ratio:.2f}'
    )
    return selected_ref


def score_card_search_comparison_candidate(
    title_hint: str,
    preview_metadata: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[int, str, bool]:
    candidate_title = clean_search_result_title(candidate.get('title', ''))
    exact_title = normalize_exact_search_match_text(title_hint)
    is_exact = bool(
        exact_title
        and exact_title == normalize_exact_search_match_text(candidate_title)
    )
    title_score = score_search_result_title(title_hint, candidate_title)
    metadata_score, metadata_detail = score_preview_metadata_for_search_candidate(
        preview_metadata,
        candidate,
    )
    result_rank = int(candidate.get('_search_rank', CARD_SEARCH_CANDIDATE_LIMIT + 1))
    rank_score = max(0, 210 - result_rank * 10)
    total_score = title_score * 30 + metadata_score + rank_score
    return (
        total_score,
        f'exact={int(is_exact)},title={title_score}x30,rank={rank_score},'
        f'{metadata_detail},'
        f'candidate_title={shorten_log_text(candidate_title, 120)}',
        is_exact,
    )


def score_preview_metadata_for_search_candidate(
    preview_metadata: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[int, str]:
    score = 0
    detail_list = []
    expected_owner = safe_str(preview_metadata.get('owner', '')).strip()
    actual_owner = safe_str(candidate.get('author', '')).strip()
    if expected_owner and actual_owner:
        owner_ratio = difflib.SequenceMatcher(
            None,
            expected_owner.casefold(),
            actual_owner.casefold(),
        ).ratio()
        if expected_owner.casefold() == actual_owner.casefold():
            owner_score = 30000
        elif owner_ratio >= 0.75:
            owner_score = round(owner_ratio * 15000)
        else:
            owner_score = -8000
        score += owner_score
        detail_list.append(f'owner={owner_score}/{owner_ratio:.2f}')

    for stat_name, candidate_key in [('view', 'play'), ('danmaku', 'video_review'), ('like', 'like')]:
        expected_value = parse_count_text(preview_metadata.get(stat_name))
        actual_value = parse_count_text(candidate.get(candidate_key))
        if expected_value is None or actual_value is None:
            continue
        difference_ratio = abs(actual_value - expected_value) / max(expected_value, actual_value, 1)
        stat_score = max(0, 5000 - round(difference_ratio * 5000))
        score += stat_score
        detail_list.append(f'{stat_name}={stat_score}/{difference_ratio:.2f}')
    return score, ';'.join(detail_list) or 'metadata=none'


def has_preview_metadata_signal(preview_metadata: dict[str, Any]) -> bool:
    if safe_str(preview_metadata.get('owner', '')).strip():
        return True
    return any(
        parse_count_text(preview_metadata.get(stat_name)) is not None
        for stat_name in ['view', 'danmaku', 'like']
    )


def has_exact_title_candidate(title_hint: str, candidate_list: list[dict[str, Any]]) -> bool:
    exact_title = normalize_exact_search_match_text(title_hint)
    return bool(exact_title) and any(
        exact_title
        == normalize_exact_search_match_text(clean_search_result_title(candidate.get('title', '')))
        for candidate in candidate_list
    )


def merge_search_candidates(candidate_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_by_key = {}
    for candidate in candidate_list:
        if not isinstance(candidate, dict):
            continue
        video_ref = build_video_ref_from_archive_candidate(candidate)
        video_key = get_video_ref_key(video_ref or {})
        if not video_key:
            continue
        existing_candidate = candidate_by_key.get(video_key)
        if existing_candidate is None:
            candidate_by_key[video_key] = dict(candidate)
            continue
        for field_name, field_value in candidate.items():
            if existing_candidate.get(field_name) in ['', None] and field_value not in ['', None]:
                existing_candidate[field_name] = field_value
        existing_source = safe_str(existing_candidate.get('_search_source', ''))
        new_source = safe_str(candidate.get('_search_source', ''))
        if new_source and new_source not in existing_source.split('+'):
            existing_candidate['_search_source'] = '+'.join(
                value for value in [existing_source, new_source] if value
            )
        existing_candidate['_search_rank'] = min(
            int(existing_candidate.get('_search_rank', CARD_SEARCH_CANDIDATE_LIMIT + 1)),
            int(candidate.get('_search_rank', CARD_SEARCH_CANDIDATE_LIMIT + 1)),
        )
    return list(candidate_by_key.values())


def build_search_candidate_from_video_info(
    video_ref: dict[str, str],
    video_info: dict[str, Any] | None,
    source: str,
) -> dict[str, Any] | None:
    if not isinstance(video_info, dict):
        return None
    candidate = dict(video_ref)
    candidate['title'] = safe_str(video_info.get('title', ''))
    owner_data = video_info.get('owner', {})
    if isinstance(owner_data, dict):
        candidate['author'] = safe_str(owner_data.get('name', ''))
        candidate['mid'] = owner_data.get('mid')
    stat_data = video_info.get('stat', {})
    if isinstance(stat_data, dict):
        candidate['play'] = stat_data.get('view')
        candidate['video_review'] = stat_data.get('danmaku')
        candidate['like'] = stat_data.get('like')
    candidate['_search_source'] = source
    candidate['_search_rank'] = CARD_SEARCH_CANDIDATE_LIMIT + 1
    return candidate


def search_video_by_preview_metadata(
    card_data: dict[str, Any],
    title_hint: str,
    preview_ocr_enable: bool = True,
) -> dict[str, str] | None:
    search_result = search_video_by_preview_metadata_candidate(
        card_data,
        title_hint,
        preview_ocr_enable,
    )
    if isinstance(search_result, dict):
        video_ref = search_result.get('video_ref')
        return video_ref if isinstance(video_ref, dict) else None
    return None


def search_video_by_preview_metadata_candidate(
    card_data: dict[str, Any],
    title_hint: str,
    preview_ocr_enable: bool = True,
) -> dict[str, Any] | None:
    """从 QQ 卡片预览图提取 UP 主和统计值，再在该 UP 的投稿中定位视频。"""
    if not preview_ocr_enable:
        parse_log('预览图OCR匹配已关闭，跳过预览图增强搜索')
        return None

    preview_url_list = extract_preview_image_urls(card_data)
    if not preview_url_list:
        parse_log('卡片未找到可用预览图URL，跳过预览图增强搜索')
        return None

    best_metadata_result = None
    best_metadata_signal_count = -1
    for preview_url in preview_url_list[:2]:
        parse_log(f'开始预览图OCR url={shorten_log_text(preview_url, 180)}')
        preview_text = recognize_preview_image(preview_url)
        if not preview_text:
            continue
        preview_metadata = parse_preview_ocr_metadata(preview_text)
        parse_log(
            f'预览图OCR结果 owner={shorten_log_text(preview_metadata.get("owner", ""), 80)} '
            f'stats={format_preview_stat_log(preview_metadata)} '
            f'text={shorten_log_text(" | ".join(preview_text), 240)}'
        )
        metadata_signal_count = sum(
            value not in ['', None]
            for value in preview_metadata.values()
        )
        if metadata_signal_count > best_metadata_signal_count:
            best_metadata_signal_count = metadata_signal_count
            best_metadata_result = {
                'video_ref': None,
                'preview_metadata': preview_metadata,
            }
        owner_name = preview_metadata.get('owner', '')
        if not owner_name:
            parse_log('预览图OCR未识别到UP主')
            continue

        owner_mid = search_bili_user_mid(owner_name)
        if not owner_mid:
            parse_log(f'UP主搜索未命中 owner={shorten_log_text(owner_name, 80)}')
            continue

        video_ref = search_video_by_owner_metadata(
            owner_mid,
            owner_name,
            title_hint,
            preview_metadata,
        )
        if video_ref:
            return {
                'video_ref': video_ref,
                'preview_metadata': preview_metadata,
            }
    return best_metadata_result


def extract_preview_image_urls(card_data: dict[str, Any]) -> list[str]:
    result = []

    def visit(value: Any, key_name: str = '') -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                visit(nested_value, safe_str(key).casefold())
            return
        if isinstance(value, list):
            for nested_value in value:
                visit(nested_value, key_name)
            return
        if not isinstance(value, str) or not value.strip():
            return

        for url in re.findall(r'https?://[^\s"\'<>]+', value):
            clean_url = url.rstrip('，。,.;；)）]】')
            host = urllib.parse.urlsplit(clean_url).netloc.casefold()
            is_preview_key = key_name in {'preview', 'preview_url', 'previewurl'}
            is_qq_preview = host.endswith('ugcimg.cn') or host.endswith('ugcimg.qq.com')
            if (is_preview_key or is_qq_preview) and clean_url not in result:
                result.append(clean_url)

    visit(card_data)
    return result


def recognize_preview_image(preview_url: str) -> list[str]:
    try:
        image_bytes = http_get_binary(preview_url, PREVIEW_OCR_MAX_BYTES)
        ocr_engine = get_preview_ocr_engine()
        if ocr_engine is None:
            return []
        image_object = decode_preview_image(image_bytes)
        if image_object is None:
            parse_log('预览图OCR图片解码失败')
            return []

        with gPreviewOcrLock:
            ocr_result = ocr_engine(image_object)
            if isinstance(ocr_result, tuple):
                ocr_result = ocr_result[0]
        return extract_ocr_texts(ocr_result)
    except Exception as exception_object:
        parse_log(
            f'预览图OCR失败 error={type(exception_object).__name__}: '
            f'{shorten_log_text(exception_object, 180)}'
        )
        return []


def get_preview_ocr_engine():
    global gPreviewOcrEngine, gPreviewOcrUnavailable
    with gPreviewOcrLock:
        if gPreviewOcrEngine is not None:
            return gPreviewOcrEngine
        if gPreviewOcrUnavailable:
            return None

        try:
            from rapidocr_onnxruntime import RapidOCR

            gPreviewOcrEngine = RapidOCR()
            parse_log('预览图OCR后端=rapidocr_onnxruntime')
            return gPreviewOcrEngine
        except Exception as rapid_exception:
            gPreviewOcrUnavailable = True
            parse_log(
                f'RapidOCR不可用，将回退标题搜索 error={type(rapid_exception).__name__}: '
                f'{shorten_log_text(rapid_exception, 180)}'
            )
            return None


def decode_preview_image(image_bytes: bytes):
    try:
        import cv2
        import numpy

        image_array = numpy.frombuffer(image_bytes, dtype=numpy.uint8)
        return cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    except Exception:
        return None


def extract_ocr_texts(value: Any) -> list[str]:
    text_list = []
    if value is None:
        return text_list
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        for key in ['rec_texts', 'text', 'texts', 'rec_text']:
            if key in value:
                text_list.extend(extract_ocr_texts(value[key]))
        if not text_list:
            for nested_value in value.values():
                text_list.extend(extract_ocr_texts(nested_value))
        return unique_text_list(text_list)
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[1], str):
            return [value[1].strip()] if value[1].strip() else []
        for nested_value in value:
            text_list.extend(extract_ocr_texts(nested_value))
        return unique_text_list(text_list)

    json_method = getattr(value, 'json', None)
    if callable(json_method):
        try:
            return extract_ocr_texts(json_method())
        except Exception:
            return []
    if isinstance(json_method, (dict, list, tuple)):
        return extract_ocr_texts(json_method)
    if isinstance(json_method, str):
        try:
            return extract_ocr_texts(json.loads(json_method))
        except Exception:
            return []
    return []


def unique_text_list(text_list: list[str]) -> list[str]:
    result = []
    for text in text_list:
        clean_text = re.sub(r'\s+', ' ', safe_str(text)).strip()
        if clean_text and clean_text not in result:
            result.append(clean_text)
    return result


def parse_preview_ocr_metadata(text_list: list[str]) -> dict[str, Any]:
    lines = unique_text_list(text_list)
    owner = ''
    for index, line in enumerate(lines):
        if 'UP主' not in line and 'UP' not in line.upper():
            continue
        prefix = re.split(r'UP主|UP', line, maxsplit=1, flags=re.IGNORECASE)[0]
        prefix = re.sub(r'[|｜:：\-\s]+$', '', prefix).strip()
        if is_valid_ocr_owner(prefix):
            owner = prefix
            break
        if index > 0 and is_valid_ocr_owner(lines[index - 1]):
            owner = lines[index - 1]
            break

    joined_text = ' '.join(lines)
    stat_patterns = {
        'view': r'([\d]+(?:[.,][\d]+)?\s*[万亿]?)\s*播(?:放|放量)',
        'danmaku': r'([\d]+(?:[.,][\d]+)?\s*[万亿]?)\s*弹幕',
        'like': r'([\d]+(?:[.,][\d]+)?\s*[万亿]?)\s*点(?:赞|赞数)',
    }
    metadata = {'owner': owner}
    for stat_name, pattern in stat_patterns.items():
        matched = re.search(pattern, joined_text, re.IGNORECASE)
        if matched:
            parsed_value = parse_count_text(matched.group(1))
            if parsed_value is not None:
                metadata[stat_name] = parsed_value
    return metadata


def is_valid_ocr_owner(owner: str) -> bool:
    owner = safe_str(owner).strip()
    if len(owner) < 2 or len(owner) > 40:
        return False
    return not bool(re.fullmatch(r'[\d\W_]+', owner, re.UNICODE))


def parse_count_text(value: Any) -> int | None:
    matched = re.search(r'([\d]+(?:[.,][\d]+)?)\s*([万亿]?)', safe_str(value))
    if not matched:
        return None
    try:
        number = float(matched.group(1).replace(',', ''))
        unit = matched.group(2)
        if unit == '亿':
            number *= 100000000
        elif unit == '万':
            number *= 10000
        return round(number)
    except Exception:
        return None


def format_preview_stat_log(metadata: dict[str, Any]) -> str:
    return ','.join(
        f'{name}={metadata[name]}'
        for name in ['view', 'danmaku', 'like']
        if metadata.get(name) is not None
    ) or 'none'


def search_bili_user_mid(owner_name: str) -> str | None:
    cache_key = f'user_mid:{safe_str(owner_name).strip().casefold()}'
    cached_mid = get_api_cache(cache_key, missing='')
    if cached_mid != '':
        parse_log(
            f'UP主搜索命中缓存 owner={shorten_log_text(owner_name, 80)} mid={cached_mid}'
        )
        return cached_mid or None

    search_url_list = [
        'https://api.bilibili.com/x/web-interface/search/type?'
        + urllib.parse.urlencode(
            {
                'search_type': 'bili_user',
                'keyword': owner_name,
                'page': 1,
                'page_size': 20,
            }
        ),
        'https://api.bilibili.com/x/web-interface/search/all/v2?'
        + urllib.parse.urlencode({'keyword': owner_name, 'page': 1, 'pagesize': 20}),
    ]
    fallback_candidates = []
    for api_index, api_url in enumerate(search_url_list, start=1):
        try:
            response_data = json.loads(
                http_get_json_text(api_url, referer='https://search.bilibili.com/')
            )
            response_code = response_data.get('code')
            if response_code != 0:
                parse_log(f'UP主搜索API#{api_index}返回非零code={response_code}')
                continue
            candidates = extract_bili_user_search_results(response_data)
            if not candidates:
                parse_log(f'UP主搜索API#{api_index}无候选')
                continue
            fallback_candidates.extend(candidates)
            exact_candidates = [
                item for item in candidates
                if safe_str(item.get('uname', '')).casefold() == safe_str(owner_name).casefold()
            ]
            if exact_candidates:
                owner_mid = safe_str(exact_candidates[0].get('mid', '')).strip()
                parse_log(
                    f'UP主搜索命中 api={api_index} owner={shorten_log_text(owner_name, 80)} '
                    f'mid={owner_mid} exact=True'
                )
                set_api_cache(cache_key, owner_mid)
                return owner_mid or None
        except Exception as exception_object:
            parse_log(
                f'UP主搜索API#{api_index}失败 owner={shorten_log_text(owner_name, 80)} '
                f'error={describe_http_error(exception_object)}'
            )
    fuzzy_candidate_list = []
    for candidate in fallback_candidates:
        candidate_name = safe_str(candidate.get('uname', '')).strip()
        name_ratio = difflib.SequenceMatcher(
            None,
            safe_str(owner_name).casefold(),
            candidate_name.casefold(),
        ).ratio()
        fuzzy_candidate_list.append((name_ratio, candidate))
    fuzzy_candidate_list.sort(key=lambda item: item[0], reverse=True)
    if fuzzy_candidate_list and fuzzy_candidate_list[0][0] >= 0.75:
        best_ratio, selected = fuzzy_candidate_list[0]
        owner_mid = safe_str(selected.get('mid', '')).strip()
        parse_log(
            f'UP主搜索模糊命中 owner={shorten_log_text(owner_name, 80)} '
            f'candidate={shorten_log_text(selected.get("uname", ""), 80)} '
            f'mid={owner_mid} ratio={best_ratio:.2f}'
        )
        set_api_cache(cache_key, owner_mid)
        return owner_mid or None
    parse_log(
        f'UP主搜索无可靠候选 owner={shorten_log_text(owner_name, 80)} '
        f'http_blocked={format_http_blocked_log()}'
    )
    return None


def extract_bili_user_search_results(response_data: dict[str, Any]) -> list[dict[str, Any]]:
    result_data = response_data.get('data', {}).get('result', [])
    if not isinstance(result_data, list):
        return []
    if result_data and all(isinstance(item, dict) and item.get('mid') for item in result_data):
        return result_data

    for bucket in result_data:
        if not isinstance(bucket, dict) or bucket.get('result_type') != 'bili_user':
            continue
        user_result_list = bucket.get('data', [])
        if isinstance(user_result_list, list):
            return [
                item for item in user_result_list
                if isinstance(item, dict) and item.get('mid')
            ]
    return []


def search_video_by_owner_metadata(
    owner_mid: str,
    owner_name: str,
    title_hint: str,
    preview_metadata: dict[str, Any],
) -> dict[str, str] | None:
    if not normalize_search_match_text(title_hint):
        # 没有标题时无法判断是这个 UP 主的哪一个投稿，猜测只会给出错误结果。
        parse_log(f'卡片没有可用标题，跳过UP主投稿匹配 mid={owner_mid}')
        return None

    candidate_list = []
    for page in range(1, 4):
        page_candidates = fetch_owner_archive_candidates(
            owner_mid,
            title_hint,
            'pubdate',
            page,
        )
        candidate_list.extend(page_candidates)
        if not page_candidates:
            break
        if any(
            normalize_exact_search_match_text(clean_search_result_title(candidate.get('title', '')))
            == normalize_exact_search_match_text(title_hint)
            for candidate in page_candidates
        ):
            break

    if not has_exact_title_candidate(title_hint, candidate_list):
        for page in range(1, 4):
            page_candidates = fetch_owner_search_candidates(owner_name, page)
            owner_candidates = [
                candidate for candidate in page_candidates
                if safe_str(candidate.get('author', '')).casefold()
                == safe_str(owner_name).casefold()
            ]
            candidate_list.extend(owner_candidates)
            if has_exact_title_candidate(title_hint, owner_candidates):
                break

    if not candidate_list:
        parse_log(
            f'UP主投稿列表为空 mid={owner_mid} http_blocked={format_http_blocked_log()}'
        )
        return None

    candidate_list = merge_search_candidates(candidate_list)
    enrich_exact_owner_archive_candidates(title_hint, candidate_list)

    scored_candidates = []
    exact_candidates = []
    for rank, candidate in enumerate(candidate_list, start=1):
        score, is_exact = score_owner_archive_candidate(title_hint, preview_metadata, candidate, rank)
        scored_candidates.append((score, candidate))
        if is_exact:
            exact_candidates.append((score, candidate))
        parse_log(
            f'UP主投稿候选 mid={owner_mid} rank={rank} bvid={safe_str(candidate.get("bvid", ""))} '
            f'score={score} title={shorten_log_text(candidate.get("title", ""), 120)} '
            f'play={safe_str(candidate.get("play", ""))} '
            f'danmaku={safe_str(candidate.get("video_review", ""))} '
            f'like={safe_str(candidate.get("like", ""))}'
        )

    if exact_candidates:
        best_exact_score = max(item[0] for item in exact_candidates)
        best_exact_candidates = [
            item for item in exact_candidates
            if item[0] == best_exact_score
        ]
        _, selected = random.choice(best_exact_candidates)
        parse_log(
            f'UP主投稿完整标题按OCR统计选择 count={len(exact_candidates)} '
            f'tied={len(best_exact_candidates)} bvid={safe_str(selected.get("bvid", ""))} '
            f'score={best_exact_score}'
        )
        return build_video_ref_from_archive_candidate(selected)

    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    if not scored_candidates:
        return None
    selected = scored_candidates[0][1]
    selected_title = clean_search_result_title(safe_str(selected.get('title', '')))
    match_level, match_ratio = evaluate_title_match(title_hint, selected_title)
    if match_level not in ['exact', 'strong']:
        # 同一个 UP 主往往有大量投稿，标题对不上时命中的只是“同作者的另一个视频”。
        parse_log(
            f'UP主投稿标题置信度不足，放弃OCR结果 mid={owner_mid} level={match_level} '
            f'ratio={match_ratio:.2f} keyword={shorten_log_text(title_hint, 120)} '
            f'candidate_title={shorten_log_text(selected_title, 120)} '
            f'bvid={safe_str(selected.get("bvid", ""))} '
            f'http_blocked={format_http_blocked_log()}'
        )
        return None
    parse_log(
        f'UP主投稿统计/标题模糊命中 bvid={safe_str(selected.get("bvid", ""))} '
        f'score={scored_candidates[0][0]} title_level={match_level} '
        f'title_ratio={match_ratio:.2f}'
    )
    return build_video_ref_from_archive_candidate(selected)


def enrich_exact_owner_archive_candidates(
    title_hint: str,
    candidate_list: list[dict[str, Any]],
) -> None:
    exact_title = normalize_exact_search_match_text(title_hint)
    exact_candidate_list = [
        candidate for candidate in candidate_list
        if exact_title
        and exact_title
        == normalize_exact_search_match_text(
            clean_search_result_title(candidate.get('title', ''))
        )
    ][:OWNER_EXACT_DETAIL_LIMIT]
    if not exact_candidate_list:
        return

    with ThreadPoolExecutor(
        max_workers=min(4, len(exact_candidate_list)),
        thread_name_prefix='BiliShareInfoOwnerDetail',
    ) as executor:
        future_list = []
        for candidate in exact_candidate_list:
            video_ref = build_video_ref_from_archive_candidate(candidate)
            if not video_ref:
                continue
            future_list.append(
                (
                    candidate,
                    executor.submit(copy_context().run, fetch_video_info, video_ref),
                )
            )
        for candidate, detail_future in future_list:
            video_ref = build_video_ref_from_archive_candidate(candidate)
            video_info = get_card_search_future_result(detail_future, 'UP主同名投稿详情')
            detailed_candidate = build_search_candidate_from_video_info(
                video_ref or {},
                video_info,
                'owner_detail',
            )
            if not detailed_candidate:
                continue
            existing_source = safe_str(candidate.get('_search_source', 'owner_archive'))
            existing_rank = candidate.get('_search_rank', CARD_SEARCH_CANDIDATE_LIMIT + 1)
            candidate.update(detailed_candidate)
            candidate['_search_source'] = f'{existing_source}+owner_detail'
            candidate['_search_rank'] = existing_rank


def fetch_owner_search_candidates(owner_name: str, page: int) -> list[dict[str, Any]]:
    api_url = 'https://api.bilibili.com/x/web-interface/search/all/v2?' + urllib.parse.urlencode(
        {'keyword': owner_name, 'page': page, 'pagesize': 20}
    )
    try:
        response_data = json.loads(http_get_json_text(api_url, referer='https://search.bilibili.com/'))
        response_code = response_data.get('code')
        if response_code != 0:
            parse_log(f'UP主视频搜索返回非零code={response_code} page={page}')
            return []
        video_list = extract_video_search_results(response_data)
        parse_log(
            f'UP主视频搜索完成 owner={shorten_log_text(owner_name, 80)} '
            f'page={page} count={len(video_list)}'
        )
        return video_list
    except Exception as exception_object:
        parse_log(
            f'UP主视频搜索失败 owner={shorten_log_text(owner_name, 80)} page={page} '
            f'error={describe_http_error(exception_object)}'
        )
        return []


def fetch_owner_keyword_archive_candidates(
    owner_mid: str,
    title_hint: str,
    order: str,
    page: int,
) -> tuple[list[dict[str, Any]], bool]:
    """返回 (候选列表, 结果是否可信)。请求被风控时第二项为 False。"""
    keyword = clean_search_keyword(title_hint)
    cache_key = f'owner_keyword:{owner_mid}:{order}:{page}:{keyword}'
    cached_result = get_api_cache(cache_key)
    if cached_result is not None:
        parse_log(
            f'UP主关键词投稿命中缓存 mid={owner_mid} page={page} count={len(cached_result)}'
        )
        return cached_result, True

    api_url = 'https://api.bilibili.com/x/series/recArchivesByKeywords?' + urllib.parse.urlencode(
        {
            'mid': owner_mid,
            'keywords': keyword,
            'ps': 20,
            'pn': page,
            'orderby': 'views' if order == 'click' else order,
        }
    )
    try:
        response_data = json.loads(
            http_get_json_text(
                api_url,
                referer=f'https://space.bilibili.com/{owner_mid}',
                # 该公开接口带 Origin 时容易被 B 站网关误判为风控请求。
                include_origin=False,
            )
        )
        response_code = response_data.get('code')
        archive_list = response_data.get('data', {}).get('archives', [])
        if not isinstance(archive_list, list):
            archive_list = []
        parse_log(
            f'UP主关键词投稿API响应 mid={owner_mid} page={page} order={order} '
            f'code={response_code} count={len(archive_list)}'
        )
        if response_code != 0:
            mark_http_blocked(f'recArchivesByKeywords code={response_code}')
            return [], False

        result = []
        for result_rank, archive in enumerate(archive_list, start=1):
            if not isinstance(archive, dict):
                continue
            candidate = dict(archive)
            stat_data = archive.get('stat', {})
            if isinstance(stat_data, dict):
                candidate['play'] = stat_data.get('view')
                candidate['video_review'] = stat_data.get('danmaku')
                candidate['like'] = stat_data.get('like')
            candidate['_search_source'] = 'owner_keyword_api'
            candidate['_search_rank'] = (page - 1) * 20 + result_rank
            result.append(candidate)
        set_api_cache(cache_key, result)
        return result, True
    except Exception as exception_object:
        parse_log(
            f'UP主关键词投稿API请求失败 mid={owner_mid} page={page} '
            f'error={describe_http_error(exception_object)}'
        )
        return [], False


def get_wbi_mixin_key() -> str | None:
    global gWbiMixinKey, gWbiMixinKeyTime
    with DATA_LOCK:
        if (
            gWbiMixinKey
            and time.time() - gWbiMixinKeyTime < WBI_KEY_CACHE_TTL_SECONDS
        ):
            return gWbiMixinKey

    try:
        response_data = json.loads(
            http_get_json_text(
                'https://api.bilibili.com/x/web-interface/nav',
                referer='https://www.bilibili.com/',
            )
        )
        wbi_image_data = response_data.get('data', {}).get('wbi_img', {})
        if not isinstance(wbi_image_data, dict):
            parse_log(f'WBI密钥接口未返回密钥 code={response_data.get("code")}')
            return None
        image_key = extract_wbi_image_key(wbi_image_data.get('img_url'))
        sub_key = extract_wbi_image_key(wbi_image_data.get('sub_url'))
        original_key = image_key + sub_key
        if len(original_key) <= max(WBI_MIXIN_KEY_TABLE):
            parse_log('WBI密钥接口缺少有效img/sub密钥')
            return None
        mixin_key = ''.join(original_key[index] for index in WBI_MIXIN_KEY_TABLE)[:32]
        with DATA_LOCK:
            gWbiMixinKey = mixin_key
            gWbiMixinKeyTime = time.time()
        parse_log('WBI密钥获取成功')
        return mixin_key
    except Exception as exception_object:
        parse_log(
            f'WBI密钥获取失败 error={type(exception_object).__name__}: '
            f'{shorten_log_text(exception_object, 180)}'
        )
        return None


def extract_wbi_image_key(image_url: Any) -> str:
    image_path = urllib.parse.urlsplit(safe_str(image_url)).path
    return os.path.splitext(os.path.basename(image_path))[0]


def build_wbi_signed_url(api_path: str, params: dict[str, Any]) -> str | None:
    mixin_key = get_wbi_mixin_key()
    if not mixin_key:
        return None

    signed_params = dict(params)
    signed_params['wts'] = int(time.time())
    query_parts = []
    for key in sorted(signed_params):
        value = re.sub(r"[!'()*]", '', safe_str(signed_params[key]))
        query_parts.append(
            f'{urllib.parse.quote(safe_str(key), safe="")}='
            f'{urllib.parse.quote(value, safe="")}'
        )
    query_text = '&'.join(query_parts)
    w_rid = hashlib.md5(
        f'{query_text}{mixin_key}'.encode('utf-8')
    ).hexdigest()
    return f'https://api.bilibili.com{api_path}?{query_text}&w_rid={w_rid}'


def fetch_owner_archive_candidates(
    owner_mid: str,
    title_hint: str,
    order: str,
    page: int,
) -> list[dict[str, Any]]:
    keyword_archive_list, keyword_api_trusted = fetch_owner_keyword_archive_candidates(
        owner_mid,
        title_hint,
        order,
        page,
    )
    if keyword_archive_list:
        return keyword_archive_list
    if keyword_api_trusted and title_hint:
        # 关键词投稿接口已明确回复该 UP 主没有匹配投稿，
        # 再打空间接口只会增加请求量并提高被限流的概率。
        parse_log(
            f'UP主关键词投稿接口明确无匹配，跳过空间投稿接口 mid={owner_mid} page={page}'
        )
        return []

    params = {
        'mid': owner_mid,
        'pn': page,
        'ps': 30,
        'order': order,
        'tid': 0,
        'jsonp': 'json',
        'platform': 'web',
        'web_location': 1550101,
    }
    if title_hint:
        params['keyword'] = clean_search_keyword(title_hint)
    api_url_list = []
    wbi_api_url = build_wbi_signed_url('/x/space/wbi/arc/search', params)
    if wbi_api_url:
        api_url_list.append(('wbi', wbi_api_url))
    legacy_params = {
        key: value
        for key, value in params.items()
        if key not in {'platform', 'web_location'}
    }
    api_url_list.append(
        (
            'legacy',
            'https://api.bilibili.com/x/space/arc/search?'
            + urllib.parse.urlencode(legacy_params),
        )
    )

    for api_name, api_url in api_url_list:
        try:
            response_data = json.loads(
                http_get_json_text(
                    api_url,
                    referer=f'https://space.bilibili.com/{owner_mid}',
                )
            )
            response_code = response_data.get('code')
            parse_log(
                f'UP主投稿API响应 api={api_name} mid={owner_mid} page={page} order={order} '
                f'code={response_code} body_len={len(json.dumps(response_data, ensure_ascii=False))}'
            )
            if response_code != 0:
                continue
            video_list = response_data.get('data', {}).get('list', {}).get('vlist', [])
            return video_list if isinstance(video_list, list) else []
        except Exception as exception_object:
            parse_log(
                f'UP主投稿API请求失败 api={api_name} mid={owner_mid} page={page} '
                f'error={type(exception_object).__name__}: '
                f'{shorten_log_text(exception_object, 180)}'
            )
    return []


def score_owner_archive_candidate(
    title_hint: str,
    preview_metadata: dict[str, Any],
    candidate: dict[str, Any],
    rank: int,
) -> tuple[int, bool]:
    candidate_title = clean_search_result_title(safe_str(candidate.get('title', '')))
    exact_title = normalize_exact_search_match_text(title_hint)
    is_exact = bool(exact_title and exact_title == normalize_exact_search_match_text(candidate_title))
    title_score = score_search_result_title(title_hint, candidate_title) if title_hint else 0
    score = title_score + max(0, 120 - rank * 4)
    if is_exact:
        score += 100000
    for stat_name, candidate_key in [('view', 'play'), ('danmaku', 'video_review'), ('like', 'like')]:
        expected = preview_metadata.get(stat_name)
        actual = parse_count_text(candidate.get(candidate_key))
        if expected is None or actual is None:
            continue
        difference_ratio = abs(actual - expected) / max(expected, actual, 1)
        score += max(0, 3000 - round(difference_ratio * 3000))
    return score, is_exact


def build_video_ref_from_archive_candidate(candidate: dict[str, Any]) -> dict[str, str] | None:
    bvid = safe_str(candidate.get('bvid', '')).strip()
    if re.fullmatch(r'BV[0-9A-Za-z]{10}', bvid):
        return {'bvid': bvid}
    aid = safe_str(candidate.get('aid', '')).strip()
    if aid.isdigit():
        return {'aid': aid}
    return None


def search_video_by_keyword(keyword: str) -> dict[str, str] | None:
    candidate_list = search_video_candidates_by_keyword(
        keyword,
        CARD_SEARCH_CANDIDATE_LIMIT,
    )
    if not candidate_list:
        parse_log('标题搜索未命中视频')
        return None

    exact_candidate_list = [
        candidate for candidate in candidate_list
        if bool(candidate.get('_search_exact'))
    ]
    if exact_candidate_list:
        selected = random.choice(exact_candidate_list)
        video_ref = build_video_ref_from_archive_candidate(selected)
        parse_log(
            f'标题搜索完整匹配随机选择 count={len(exact_candidate_list)} '
            f'ref={format_video_ref(video_ref)} '
            f'title={shorten_log_text(selected.get("title", ""), 120)}'
        )
        return video_ref

    selected = candidate_list[0]
    selected_title = clean_search_result_title(selected.get('title', ''))
    match_level, match_ratio = evaluate_title_match(keyword, selected_title)
    if match_level not in ['exact', 'strong']:
        parse_log(
            f'标题搜索候选置信度不足，放弃解析 level={match_level} ratio={match_ratio:.2f} '
            f'title={shorten_log_text(selected_title, 120)}'
        )
        return None
    video_ref = build_video_ref_from_archive_candidate(selected)
    parse_log(
        f'标题搜索模糊命中 ref={format_video_ref(video_ref)} '
        f'score={safe_str(selected.get("_search_score", 0))} '
        f'title_level={match_level} '
        f'title={shorten_log_text(selected_title, 120)}'
    )
    return video_ref


def build_compact_search_keyword(keyword: str) -> str:
    """提取前三个信息量较高的词，作为完整标题搜索失败后的补充查询。"""
    keyword = clean_search_keyword(keyword)
    stop_word_set = {'by', 'feat', 'ft', 'official', 'video', 'mv'}
    selected_token_list = []
    seen_token_set = set()
    for token in re.findall(r'[^\W_]+(?:\+[^\W_]+)*', keyword, re.UNICODE):
        token_key = token.casefold()
        if token_key in stop_word_set or token_key in seen_token_set:
            continue
        if len(token) == 1 and token.isascii() and token.isalpha():
            continue
        seen_token_set.add(token_key)
        selected_token_list.append(token)
        if len(selected_token_list) >= 3:
            break
    return ' '.join(selected_token_list)


def search_video_candidates_by_keyword(
    keyword: str,
    limit: int = CARD_SEARCH_CANDIDATE_LIMIT,
) -> list[dict[str, Any]]:
    keyword = clean_search_keyword(keyword)
    if not keyword:
        parse_log('标题候选搜索跳过：关键词为空')
        return []

    normalized_keyword = normalize_search_match_text(keyword)
    cache_key = f'title_search:{limit}:{keyword}'
    cached_candidate_list = get_api_cache(cache_key)
    if cached_candidate_list is not None:
        parse_log(
            f'标题搜索命中缓存 keyword={shorten_log_text(keyword, 120)} '
            f'count={len(cached_candidate_list)}'
        )
        return cached_candidate_list

    parse_log(
        f'开始标题搜索 keyword={shorten_log_text(keyword, 120)} '
        f'normalized={normalized_keyword} length={len(normalized_keyword)}'
    )

    search_url_list = [
        'https://api.bilibili.com/x/web-interface/search/type?'
        + urllib.parse.urlencode(
            {
                'search_type': 'video',
                'keyword': keyword,
                'page': 1,
                'pagesize': 20,
                'order': 'totalrank',
            }
        ),
        'https://api.bilibili.com/x/web-interface/search/all/v2?'
        + urllib.parse.urlencode({'keyword': keyword, 'page': 1, 'pagesize': 20}),
    ]
    raw_candidate_list = []
    for api_index, api_url in enumerate(search_url_list, start=1):
        if any(candidate.get('_search_exact') for candidate in raw_candidate_list):
            # 已经拿到完整标题匹配，第二个搜索接口只会增加被限流的概率。
            parse_log(f'标题搜索已命中完整匹配，跳过搜索接口#{api_index}')
            break
        try:
            response_text = http_get_json_text(api_url, referer='https://search.bilibili.com/')
            response_data = json.loads(response_text)
            response_code = response_data.get('code')
            parse_log(
                f'标题搜索API响应 code={response_code} body_len={len(response_text)} '
                f'url={shorten_log_text(api_url, 180)}'
            )
            if response_code != 0:
                parse_log(f'标题搜索API返回非零code={response_code}')
                continue
            result_list = extract_video_search_results(response_data)
            parse_log(f'标题搜索结果数量={len(result_list)}')
        except Exception as exception_object:
            parse_log(
                f'标题搜索请求失败 url={shorten_log_text(api_url, 180)} '
                f'error={describe_http_error(exception_object)}'
            )
            continue

        for result_rank, item in enumerate(result_list[:20], start=1):
            if not isinstance(item, dict):
                continue
            bvid = safe_str(item.get('bvid', ''))
            title = clean_search_result_title(safe_str(item.get('title', '')))
            if not re.fullmatch(r'BV[0-9A-Za-z]{10}', bvid):
                continue

            candidate_score, score_detail, is_exact_match = score_search_result_candidate(
                keyword,
                title,
                result_rank,
            )
            candidate = dict(item)
            candidate['title'] = title
            candidate['_search_source'] = f'title_api_{api_index}'
            candidate['_search_api'] = api_index
            candidate['_search_rank'] = result_rank
            candidate['_search_score'] = candidate_score
            candidate['_search_detail'] = score_detail
            candidate['_search_exact'] = is_exact_match
            raw_candidate_list.append(candidate)
            parse_log(
                f'标题搜索候选 api={api_index} rank={result_rank} bvid={bvid} '
                f'score={candidate_score} '
                f'detail={score_detail} title={shorten_log_text(title, 120)}'
            )
            if is_exact_match:
                parse_log(
                    f'标题搜索完整匹配候选 bvid={bvid} api={api_index} rank={result_rank} '
                    f'title={shorten_log_text(title, 120)}'
                )

    raw_candidate_list.sort(
        key=lambda candidate: (
            bool(candidate.get('_search_exact')),
            int(candidate.get('_search_score', 0)),
            -int(candidate.get('_search_api', 0)),
            -int(candidate.get('_search_rank', CARD_SEARCH_CANDIDATE_LIMIT + 1)),
        ),
        reverse=True,
    )
    candidate_list = merge_search_candidates(raw_candidate_list)[:max(1, limit)]
    parse_log(
        f'标题搜索候选池完成 raw={len(raw_candidate_list)} '
        f'unique_selected={len(candidate_list)} limit={limit}'
    )
    if candidate_list:
        set_api_cache(cache_key, candidate_list)
    return candidate_list


def extract_video_search_results(response_data: dict[str, Any]) -> list[dict[str, Any]]:
    result_data = response_data.get('data', {}).get('result', [])
    if not isinstance(result_data, list):
        return []

    for result_bucket in result_data:
        if not isinstance(result_bucket, dict) or result_bucket.get('result_type') != 'video':
            continue
        video_result_list = result_bucket.get('data', [])
        return video_result_list if isinstance(video_result_list, list) else []

    return result_data


def clean_search_result_title(title: str) -> str:
    title = re.sub(r'<[^>]+>', '', safe_str(title))
    return html.unescape(title).strip()


def is_search_result_title_match(keyword: str, title: str) -> bool:
    return score_search_result_title(keyword, title) > 0


def score_search_result_title(keyword: str, title: str) -> int:
    """计算标题语义相似度；返回值越大越相关，允许短关键词参与比较。"""
    exact_keyword = normalize_exact_search_match_text(keyword)
    exact_title = normalize_exact_search_match_text(title)
    is_exact_match = bool(exact_keyword and exact_keyword == exact_title)
    exact_sequence_ratio = difflib.SequenceMatcher(
        None,
        exact_keyword.casefold(),
        exact_title.casefold(),
    ).ratio()
    normalized_keyword = normalize_search_match_text(keyword)
    normalized_title = normalize_search_match_text(title)
    if not normalized_keyword or not normalized_title:
        return round(exact_sequence_ratio * 320) + (100000 if is_exact_match else 0)

    query_length = len(normalized_keyword)
    title_length = len(normalized_title)
    normalized_sequence_ratio = difflib.SequenceMatcher(
        None,
        normalized_keyword,
        normalized_title,
    ).ratio()
    common_char_count = sum(
        min(normalized_keyword.count(char), normalized_title.count(char))
        for char in set(normalized_keyword)
    )
    character_coverage = common_char_count / query_length
    length_fit = min(query_length, title_length) / max(query_length, title_length)
    ordered_coverage = calculate_ordered_character_coverage(normalized_keyword, normalized_title)

    score = round(
        exact_sequence_ratio * 320
        + normalized_sequence_ratio * 180
        + min(1.0, character_coverage) * 260
        + ordered_coverage * 220
        + length_fit * 100
    )
    if is_exact_match:
        score += 100000
    elif exact_title.casefold().startswith(exact_keyword.casefold()):
        score += 2200
    elif exact_keyword.casefold() in exact_title.casefold():
        score += 1500
    elif normalized_keyword == normalized_title:
        score += 900
    elif normalized_title.startswith(normalized_keyword):
        score += 600
    elif normalized_keyword in normalized_title:
        score += 350

    # 单字/双字标题通常是泛关键词，轻微偏向更短、更贴近查询词的标题。
    if query_length <= MIN_TITLE_SEARCH_SIGNAL_LENGTH - 1 and character_coverage > 0:
        score += max(0, 260 - max(0, title_length - query_length) * 12)
    return score


def score_search_result_candidate(
    keyword: str,
    title: str,
    result_rank: int,
) -> tuple[int, str, bool]:
    """合并标题相似度和搜索排名，返回总分及可读的 debug 明细。"""
    title_score = score_search_result_title(keyword, title)
    exact_keyword = normalize_exact_search_match_text(keyword)
    exact_title = normalize_exact_search_match_text(title)
    is_exact_match = bool(exact_keyword and exact_keyword == exact_title)
    normalized_keyword = normalize_search_match_text(keyword)
    normalized_title = normalize_search_match_text(title)
    rank_bonus = max(0, 240 - max(0, result_rank - 1) * 12)
    if normalized_keyword and normalized_title:
        sequence_score = round(
            difflib.SequenceMatcher(None, normalized_keyword, normalized_title).ratio() * 100
        )
        ordered_score = round(
            calculate_ordered_character_coverage(normalized_keyword, normalized_title) * 100
        )
    else:
        sequence_score = 0
        ordered_score = 0
    is_short_keyword = len(normalized_keyword) < MIN_TITLE_SEARCH_SIGNAL_LENGTH
    contains_keyword = bool(normalized_keyword and normalized_keyword in normalized_title)
    if is_short_keyword and not is_exact_match:
        # 单字/双字无法可靠区分具体视频，尊重 B 站排序，避免长标题相似度反超前排结果。
        short_match_bonus = 2400 if contains_keyword else 0
        total_score = rank_bonus * 4 + short_match_bonus
        detail = (
            f'exact=0,mode=short_rank,contains={int(contains_keyword)},title={title_score},'
            f'rank={rank_bonus},seq={sequence_score},order={ordered_score}'
        )
    else:
        total_score = title_score + rank_bonus
        detail = (
            f'exact={int(is_exact_match)},title={title_score},rank={rank_bonus},'
            f'seq={sequence_score},order={ordered_score}'
        )
    return total_score, detail, is_exact_match


def calculate_ordered_character_coverage(query: str, target: str) -> float:
    """计算查询字符按顺序出现在标题中的覆盖率，适合中文短标题。"""
    if not query or not target:
        return 0.0
    target_index = 0
    matched_count = 0
    for query_char in query:
        matched_index = target.find(query_char, target_index)
        if matched_index < 0:
            continue
        matched_count += 1
        target_index = matched_index + 1
    return matched_count / len(query)


def normalize_search_match_text(text: str) -> str:
    text = safe_str(text).casefold()
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return re.sub(r'\s+', '', text)


def normalize_exact_search_match_text(text: str) -> str:
    """仅处理 HTML 实体和首尾空白，完整保留标题中的符号。"""
    return html.unescape(safe_str(text)).strip()


def strip_title_ellipsis(text: str) -> str:
    """QQ 卡片标题过长时会以省略号截断，比较前先去掉尾部省略号。"""
    return TITLE_TRAILING_ELLIPSIS_PATTERN.sub('', safe_str(text)).strip()


def evaluate_title_match(title_hint: str, candidate_title: str) -> tuple[str, float]:
    """判断候选标题与卡片标题的匹配等级。

    返回 (level, ratio)，level 取 exact / strong / weak / none。
    卡片没有 BV/av 号时标题是唯一权威信号，只有 exact 或 strong 才能作为结果。
    """
    exact_hint = normalize_exact_search_match_text(title_hint)
    exact_candidate = normalize_exact_search_match_text(candidate_title)
    normalized_hint = normalize_search_match_text(title_hint)
    normalized_candidate = normalize_search_match_text(candidate_title)
    if not normalized_hint or not normalized_candidate:
        return 'none', 0.0

    similarity_ratio = difflib.SequenceMatcher(
        None,
        normalized_hint,
        normalized_candidate,
    ).ratio()
    if exact_hint == exact_candidate or normalized_hint == normalized_candidate:
        return 'exact', 1.0

    trimmed_hint = normalize_search_match_text(strip_title_ellipsis(title_hint))
    trimmed_candidate = normalize_search_match_text(strip_title_ellipsis(candidate_title))
    if trimmed_hint and trimmed_candidate:
        if trimmed_hint == trimmed_candidate:
            return 'exact', 1.0
        shorter_text, longer_text = sorted([trimmed_hint, trimmed_candidate], key=len)
        # 被截断的标题是完整标题的前缀，前缀足够长时同样视为可靠匹配。
        if (
            longer_text.startswith(shorter_text)
            and len(shorter_text) >= CARD_TITLE_MATCH_MIN_PREFIX_LENGTH
        ):
            return 'strong', similarity_ratio

    ordered_coverage = calculate_ordered_character_coverage(
        normalized_hint,
        normalized_candidate,
    )
    if (
        similarity_ratio >= CARD_TITLE_MATCH_MIN_RATIO
        and ordered_coverage >= CARD_TITLE_MATCH_MIN_ORDERED_COVERAGE
    ):
        return 'strong', similarity_ratio
    if similarity_ratio >= CARD_TITLE_MATCH_MIN_RATIO / 2:
        return 'weak', similarity_ratio
    return 'none', similarity_ratio


def fetch_video_info(video_ref: dict[str, str]) -> dict[str, Any] | None:
    try:
        if video_ref.get('bvid'):
            query = urllib.parse.urlencode({'bvid': video_ref['bvid']})
        elif video_ref.get('aid'):
            query = urllib.parse.urlencode({'aid': video_ref['aid']})
        else:
            parse_log(f'获取视频信息跳过：引用格式无效 ref={safe_str(video_ref)}')
            return None

        cache_key = f'video_info:{query}'
        cached_info = get_api_cache(cache_key)
        if cached_info is not None:
            parse_log(f'视频信息命中缓存 ref={format_video_ref(video_ref)}')
            return cached_info

        api_url = f'https://api.bilibili.com/x/web-interface/view?{query}'
        parse_log(f'开始获取视频信息 ref={format_video_ref(video_ref)} url={api_url}')
        response_text = http_get_json_text(api_url, referer='https://www.bilibili.com/')
        parse_log(f'视频信息API响应 body_len={len(response_text)}')
        response_data = json.loads(response_text)
        if not isinstance(response_data, dict):
            parse_log(f'视频信息API响应不是对象 type={type(response_data).__name__}')
            return None
        response_code = response_data.get('code')
        if response_code != 0:
            parse_log(
                f'视频信息API返回非零code={response_code} '
                f'message={shorten_log_text(response_data.get("message", ""), 180)}'
            )
            return None
        data = response_data.get('data', {})
        if not isinstance(data, dict):
            parse_log(f'视频信息API data不是对象 type={type(data).__name__}')
            return None
        parse_log(
            f'视频信息API解析成功 bvid={safe_str(data.get("bvid", ""))} '
            f'title={shorten_log_text(data.get("title", ""), 120)}'
        )
        set_api_cache(cache_key, data)
        return data
    except Exception as exception_object:
        parse_log(
            f'获取视频信息异常 ref={format_video_ref(video_ref)} '
            f'error={describe_http_error(exception_object)}'
        )
        return None


def fetch_live_info(live_ref: dict[str, str]) -> dict[str, Any] | None:
    room_id = safe_str(live_ref.get('live_id', '')).strip()
    if not room_id.isdigit() or int(room_id) <= 0:
        parse_log(f'获取直播间信息跳过：引用格式无效 ref={safe_str(live_ref)}')
        return None

    api_url_list = [
        LIVE_ROOM_API + '?' + urllib.parse.urlencode(
            {'room_ids': room_id, 'req_biz': 'web_room_componet'}
        ),
        'https://api.live.bilibili.com/room/v1/Room/get_info?'
        + urllib.parse.urlencode({'room_id': room_id}),
    ]
    for api_index, api_url in enumerate(api_url_list, start=1):
        try:
            parse_log(f'开始获取直播间信息 ref={format_video_ref(live_ref)} api={api_index}')
            response_data = json.loads(
                http_get_json_text(api_url, referer=f'https://live.bilibili.com/{room_id}')
            )
            if response_data.get('code') != 0:
                parse_log(
                    f'直播间信息API#{api_index}返回非零code={response_data.get("code")} '
                    f'message={shorten_log_text(response_data.get("message", response_data.get("msg", "")), 180)}'
                )
                continue

            data = response_data.get('data', {})
            if api_index == 1:
                room_data_map = data.get('by_room_ids', {})
                room_data = room_data_map.get(room_id, {})
                if not room_data and isinstance(room_data_map, dict) and len(room_data_map) == 1:
                    room_data = next(iter(room_data_map.values()))
            else:
                room_data = data
                if isinstance(room_data, dict) and room_data.get('user_cover'):
                    room_data = dict(room_data)
                    room_data['cover'] = room_data.get('user_cover')
            if not isinstance(room_data, dict) or not room_data:
                parse_log(f'直播间信息API#{api_index}未找到房间 room_id={room_id}')
                continue

            live_info = dict(room_data)
            live_info['_content_type'] = 'live'
            live_info['_live_ref'] = dict(live_ref)
            live_info['room_id'] = safe_str(live_info.get('room_id') or room_id)
            live_info['live_url'] = (
                safe_str(live_info.get('live_url')).strip()
                or f'https://live.bilibili.com/{live_info["room_id"]}'
            )
            parse_log(
                f'直播间信息解析成功 room_id={live_info["room_id"]} '
                f'live_status={safe_str(live_info.get("live_status", ""))} '
                f'title={shorten_log_text(live_info.get("title", ""), 120)}'
            )
            return live_info
        except Exception as exception_object:
            parse_log(
                f'获取直播间信息API#{api_index}失败 room_id={room_id} '
                f'error={type(exception_object).__name__}: '
                f'{shorten_log_text(exception_object, 200)}'
            )
    return None


def http_get_text(url: str, allow_response_body: bool = False) -> tuple[str, str]:
    def build_request():
        return urllib.request.Request(url, headers=get_http_headers())

    with open_http_with_retry(build_request) as response:
        response_url = response.geturl()
        if not allow_response_body:
            return response_url, ''
        content = response.read(128 * 1024)
        charset = response.headers.get_content_charset() or 'utf-8'
        response_text = content.decode(charset, errors='ignore')
        return response_url, response_text


def http_get_binary(url: str, max_bytes: int) -> bytes:
    def build_request():
        return urllib.request.Request(url, headers=get_http_headers())

    with open_http_with_retry(build_request) as response:
        content = response.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError(f'响应图片过大：{len(content)} bytes')
        return content


def http_get_json_text(
    url: str,
    referer: str = 'https://www.bilibili.com/',
    include_origin: bool = True,
) -> str:
    def build_request():
        headers = get_http_headers()
        headers['Referer'] = referer
        if not include_origin:
            headers.pop('Origin', None)
        return urllib.request.Request(url, headers=headers)

    with open_http_with_retry(build_request) as response:
        return response.read().decode('utf-8', errors='ignore')


def open_http_with_retry(request_factory):
    """B 站风控会随机返回 412，重试可避免单次抖动让解析静默降级为错误结果。"""
    last_exception = None
    for attempt in range(1, HTTP_MAX_ATTEMPTS + 1):
        throttle_http_request()
        try:
            return urllib.request.urlopen(request_factory(), timeout=HTTP_TIMEOUT)
        except Exception as exception_object:
            last_exception = exception_object
            if not is_transient_http_error(exception_object):
                raise
            if attempt >= HTTP_MAX_ATTEMPTS:
                break
            retry_delay = HTTP_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            retry_delay += random.uniform(0, HTTP_RETRY_BASE_DELAY_SECONDS / 2)
            parse_log(
                f'请求被限流，{retry_delay:.2f}s后重试 attempt={attempt}/{HTTP_MAX_ATTEMPTS} '
                f'error={describe_http_error(exception_object)}'
            )
            time.sleep(retry_delay)
    mark_http_blocked(describe_http_error(last_exception))
    raise last_exception


def throttle_http_request() -> None:
    """串行化并留出最小请求间隔，避免插件自己把 IP 打进限流窗口。"""
    global gHttpLastRequestTime
    with gHttpThrottleLock:
        wait_seconds = (
            gHttpLastRequestTime + HTTP_MIN_REQUEST_INTERVAL_SECONDS - time.monotonic()
        )
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        gHttpLastRequestTime = time.monotonic()


def is_transient_http_error(exception_object: BaseException) -> bool:
    if isinstance(exception_object, urllib.error.HTTPError):
        return exception_object.code in HTTP_RETRY_STATUS_SET
    return isinstance(
        exception_object,
        (urllib.error.URLError, TimeoutError, ConnectionError),
    )


def describe_http_error(exception_object: BaseException | None) -> str:
    if isinstance(exception_object, urllib.error.HTTPError):
        return f'HTTP {exception_object.code}'
    if exception_object is None:
        return 'unknown'
    return f'{type(exception_object).__name__}: {shorten_log_text(exception_object, 120)}'


def mark_http_blocked(reason: str) -> None:
    """记录本次解析里未能恢复的风控失败，供置信度判定和日志使用。"""
    blocked_reason_list = gHttpBlockedContext.get()
    if blocked_reason_list is None:
        return
    if reason not in blocked_reason_list:
        blocked_reason_list.append(reason)


def has_http_blocked() -> bool:
    blocked_reason_list = gHttpBlockedContext.get()
    return bool(blocked_reason_list)


def format_http_blocked_log() -> str:
    blocked_reason_list = gHttpBlockedContext.get() or []
    return format_log_list(blocked_reason_list, 4) if blocked_reason_list else 'none'


def get_api_cache(cache_key: str, missing=None):
    """短期缓存 B 站接口结果，减少请求量并让重复分享得到一致结果。"""
    with gApiCacheLock:
        cache_entry = gApiCache.get(cache_key)
        if cache_entry is None:
            return missing
        cached_time, cached_value = cache_entry
        if time.monotonic() - cached_time > API_CACHE_TTL_SECONDS:
            gApiCache.pop(cache_key, None)
            return missing
    return copy.deepcopy(cached_value)


def set_api_cache(cache_key: str, cache_value) -> None:
    with gApiCacheLock:
        expire_api_cache()
        if len(gApiCache) >= API_CACHE_MAX_ENTRIES:
            oldest_key = min(gApiCache, key=lambda key: gApiCache[key][0])
            gApiCache.pop(oldest_key, None)
        gApiCache[cache_key] = (time.monotonic(), copy.deepcopy(cache_value))


def expire_api_cache() -> None:
    now = time.monotonic()
    with gApiCacheLock:
        for cache_key in [
            cache_key
            for cache_key, (cached_time, _) in gApiCache.items()
            if now - cached_time > API_CACHE_TTL_SECONDS
        ]:
            gApiCache.pop(cache_key, None)


def get_http_headers() -> dict[str, str]:
    return {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/126.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'identity',
        # 搜索接口对缺少 Origin 的非浏览器请求更容易返回 412。
        'Origin': 'https://www.bilibili.com',
        'Referer': 'https://www.bilibili.com/',
    }


def format_video_reply(video_info: dict[str, Any]) -> str:
    cover_url = normalize_cover_url(safe_str(video_info.get('pic', '')))
    reply_text = format_video_text(video_info)
    if cover_url:
        return f'[OP:image,file={op_escape(cover_url)}]{reply_text}'
    return reply_text


def format_live_reply(live_info: dict[str, Any]) -> str:
    cover_url = normalize_cover_url(
        safe_str(live_info.get('cover') or live_info.get('user_cover', ''))
    )
    reply_text = format_live_text(live_info)
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


def format_live_forward_content(live_info: dict[str, Any]) -> list[dict[str, Any]]:
    content_list = []
    cover_url = normalize_cover_url(
        safe_str(live_info.get('cover') or live_info.get('user_cover', ''))
    )
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
                'text': format_live_text(live_info),
            },
        }
    )
    return content_list


def format_info_reply(info: dict[str, Any]) -> str:
    if info.get('_content_type') == 'live':
        return format_live_reply(info)
    return format_video_reply(info)


def format_info_forward_content(info: dict[str, Any]) -> list[dict[str, Any]]:
    if info.get('_content_type') == 'live':
        return format_live_forward_content(info)
    return format_video_forward_content(info)


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


def format_live_text(live_info: dict[str, Any]) -> str:
    live_status = {
        0: '未开播',
        1: '直播中',
        2: '轮播中',
    }.get(parse_count_text(live_info.get('live_status')), '未知')
    title = safe_str(live_info.get('title', '未知直播间')).strip() or '未知直播间'
    owner_name = safe_str(live_info.get('uname', '未知UP主')).strip() or '未知UP主'
    parent_area = safe_str(live_info.get('parent_area_name', '')).strip()
    area_name = safe_str(live_info.get('area_name', '')).strip()
    area_text = ' / '.join(value for value in [parent_area, area_name] if value) or '未知分区'
    announcement = safe_str(live_info.get('description', '')).strip() or '无公告'
    tags = live_info.get('tags', '')
    if isinstance(tags, list):
        tags = ', '.join(safe_str(tag).strip() for tag in tags if safe_str(tag).strip())
    tags = safe_str(tags).strip() or '无'
    live_time = safe_str(live_info.get('live_time', '')).strip()
    if not live_time or live_time.startswith('0000-00-00'):
        live_time = '未开播'
    room_id = safe_str(live_info.get('room_id', '')).strip()
    short_id = safe_str(live_info.get('short_id', '')).strip()
    room_id_text = room_id or '未知'
    if short_id.isdigit() and int(short_id) > 0 and short_id != room_id:
        room_id_text = f'{room_id_text}（短号：{short_id}）'
    lines = [
        f'直播间：{title}',
        f'房间号：{room_id_text}',
        f'状态：{live_status}',
        f'UP主：{owner_name}',
        f'分区：{area_text}',
        f'公告：{shorten_text(announcement, 240)}',
        f'标签：{shorten_text(tags, 240)}',
        (
            f'关注：{format_count(live_info.get("attention"))}  '
            f'在线：{format_count(live_info.get("online"))}'
        ),
        f'开播时间：{live_time}',
    ]
    live_url = safe_str(live_info.get('live_url', '')).strip()
    if live_url:
        lines.append(f'链接：{live_url}')
    return '\n'.join(lines)


def send_video_info_list(plugin_event, video_info_list: list[dict[str, Any]]) -> None:
    parse_log(
        f'准备发送媒体信息 count={len(video_info_list)} '
        f'platform={safe_str(getattr(plugin_event, "platform", {}))}'
    )
    if len(video_info_list) == 1:
        if (
            is_qq_platform(plugin_event)
            and is_single_forward_enabled(plugin_event)
            and send_group_forward(plugin_event, video_info_list)
        ):
            parse_log('单条媒体采用合并转发发送')
            return
        reply_message(plugin_event, format_info_reply(video_info_list[0]))
        parse_log('单条媒体采用普通回复发送')
        return

    if (
        is_qq_platform(plugin_event)
        and is_multi_forward_enabled(plugin_event)
        and send_group_forward(plugin_event, video_info_list)
    ):
        parse_log('多条媒体采用合并转发发送')
        return

    for video_info in video_info_list:
        reply_message(plugin_event, format_info_reply(video_info))
    parse_log('多条媒体采用逐条普通回复发送')


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
        parse_log(f'构造合并转发节点 count={len(video_info_list)} bot_id={bot_id}')
        for video_info in video_info_list:
            message_node_list.append(
                {
                    'type': 'node',
                    'data': {
                        'name': gPluginName,
                        'uin': bot_id,
                        'content': format_info_forward_content(video_info),
                    },
                }
            )

        result = plugin_event.send_group_forward_msg(plugin_event.data.group_id, message_node_list)
        parse_log(f'合并转发接口返回 result={shorten_log_text(result, 300)}')
        if isinstance(result, dict) and result.get('active') is False:
            return False
        return True
    except Exception as exception_object:
        parse_log(
            f'合并转发发送异常 error={type(exception_object).__name__}: '
            f'{shorten_log_text(exception_object, 200)}'
        )
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
        ['meta', 'detail_1', 'title'],
        ['meta', 'detail_1', 'desc'],
        ['fields', 'title'],
        ['fields', 'desc'],
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
    return keyword.strip()


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
        video_key = get_video_ref_key(video_ref)
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
