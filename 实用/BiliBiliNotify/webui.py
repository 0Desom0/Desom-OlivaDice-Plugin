"""通过 OlivOS 菜单事件提供订阅推送管理面板。"""

import base64
from concurrent.futures import ThreadPoolExecutor, wait
import io
import re
import sys
from threading import Lock
import time
from datetime import date
from urllib.parse import urlsplit

import OlivOS

from . import bili_api, capabilities, config, function, live_stats, notify, sender, store

_GROUP_TYPES = {('onebot', 'qq'): 'group', ('qqGuildv2_link', 'qqGuild'): 'qq_group'}
_POLL_LABELS = {
    'live_seconds': '直播轮询间隔',
    'dynamic_seconds': '动态轮询间隔',
    'video_seconds': '视频轮询间隔',
    'max_concurrent': '最大并发请求数',
    'max_sockets': '直播间长连接上限',
    'live_relaxed_seconds': '长连接在线时的直播轮询间隔',
}
_SOCKET_POLL_MAX = {'max_sockets': 32, 'live_relaxed_seconds': 3600}
_IMAGE_SETTINGS = {'dynamic_image': '动态图片卡片', 'save_dynamic_image': '动态图片卡片存档'}
_IMAGE_MODES = {'inherit': None, 'on': True, 'off': False}
_MODE_NAMES = {value: mode for mode, value in _IMAGE_MODES.items()}
_STATS_BOOLS = {
    'enabled': '直播数据统计',
    'hide_revenue': '隐藏营收金额与付费排行',
    'save_report_image': '场次图片存档',
}
_STATS_LIMITS = {
    'reconnect_grace_seconds': ('断流续接宽限', 0, None),
    'query_cooldown_seconds': ('群查询冷却', 0, None),
    'danmu_retention_days': ('弹幕原文保留天数', 1, None),
    'min_report_minutes': ('自动推送最短直播时长', 0, 120),
    'min_report_danmu': ('自动推送最少弹幕数', 0, 1000),
    'wordcloud_limit': ('词云最大词数', 10, 300),
}
_WORD_LISTS = {'wordcloud_stopwords': '自定义停用词', 'wordcloud_words': '自定义热词'}
_MAX_WORDS = 200
_MAX_WORD_LENGTH = 32
_IMAGES = {'.jpg': 'jpeg', '.png': 'png', '.gif': 'gif', '.webp': 'webp', '.avif': 'avif', '.bmp': 'bmp'}
_MAX_PREVIEW = 512 * 1024
_MAX_SESSION_PREVIEW = 2 * 1024 * 1024
_SESSION_FIELDS = frozenset((
    'id', 'room_id', 'uname', 'title', 'area', 'status', 'start_at', 'end_at', 'duration',
    'danmu', 'online_peak', 'interactors',
))
_GLOBAL_ACTIONS = {'get_state', 'save_global', 'refresh_buvid', 'probe_api', 'sync_bot_names',
                   'qr_generate', 'qr_poll', 'account_sync', 'switch_account', 'remove_account'}
_BOT_NICK_TTL = 1800.0
_BOT_NICK_RETRY_TTL = 30.0
_bot_nick_lock = Lock()
_bot_nick_cache = {}


class _InvalidRequest(ValueError):
    pass


def _obj(value, label):
    if not isinstance(value, dict):
        raise _InvalidRequest(f'{label}必须为对象。')
    return value


def _list(value, label):
    if not isinstance(value, list):
        raise _InvalidRequest(f'{label}必须为列表。')
    return value


def _text(value, label):
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise _InvalidRequest(f'请用单行纯文本填写{label}。')
    return value.strip()


def _bool(value, label):
    if type(value) is not bool:
        raise _InvalidRequest(f'{label}必须为布尔开关。')
    return value


def _int(value, label, minimum, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        span = f'{minimum} 至 {maximum} 的整数' if maximum is not None else f'{minimum} 或更大的整数'
        raise _InvalidRequest(f'{label}必须为 {span}。')
    return value


def _require_feature(feature):
    if not capabilities.can(feature):
        raise _InvalidRequest(capabilities.hint(feature))


def _image_override(value):
    if isinstance(value, str) and value in _IMAGE_MODES:
        value = _IMAGE_MODES[value]
    if value is not None and type(value) is not bool:
        raise _InvalidRequest('请选择动态图片模式：跟随本账号、开启图片或文字模式。')
    if value is True:
        _require_feature('dynamic_image')
    return value


def _session_image_override(value, feature, label):
    if not isinstance(value, str) or value not in _IMAGE_MODES:
        raise _InvalidRequest(f'请选择{label}模式：跟随本账号、开启或关闭。')
    if value == 'on':
        _require_feature(feature)
    return _IMAGE_MODES[value]


def _session_image_mode(value):
    return _MODE_NAMES[value if type(value) is bool else None]


def _flags(value, label):
    fields = _obj(value, label)
    return {kind: _bool(fields.get(kind), f'{label} · {config.LABELS[kind]}') for kind in config.KINDS}


def _kind(payload, choices=config.KINDS):
    kind = payload.get('kind')
    if kind not in choices:
        raise _InvalidRequest('请选择有效的推送或自检类型。')
    return kind


def _uid(value):
    uid = _text(value, '主播 UID')
    if not re.fullmatch(r'[0-9]{1,20}', uid) or not uid.strip('0'):
        raise _InvalidRequest('请输入 B站个人空间数字 UID。')
    return uid.lstrip('0')


def _id(value, platform, label):
    text = _text(value, label)
    if platform == 'qq':
        if re.fullmatch(r'[0-9]{1,20}', text) and text.strip('0'):
            return text.lstrip('0')
        raise _InvalidRequest(f'{label}须为有效的 QQ 数字 ID。')
    if platform == 'qqGuild' and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', text):
        return text
    raise _InvalidRequest(f'{label}须为有效的 QQ 群平台 OpenID。')


def _bot_pair(bot_info):
    platform = getattr(bot_info, 'platform', {})
    return (platform.get('sdk', ''), platform.get('platform', '')) if isinstance(platform, dict) else ('', '')


def _target(value):
    sid = _text(value, '群标识')
    parts = sid.split('|')
    if len(parts) != 3 or tuple(parts[:2]) not in _GROUP_TYPES:
        raise _InvalidRequest('群标识格式为 SDK|平台|群 ID，如 onebot|qq|123456。')
    sdk, platform, group_id = parts
    group_id = _id(group_id, platform, '群 ID')
    return {'sdk': sdk, 'platform': platform, 'group_id': group_id, 'chat_type': _GROUP_TYPES[sdk, platform]}


def _group_matches(group, target):
    return all(group.get(key) == value for key, value in target.items())


def _group_target(payload, bot_hash, bot_info, *, create=False):
    target = _target(payload.get('sid'))
    sid = function.sid_for(target)
    if (target['sdk'], target['platform']) != _bot_pair(bot_info):
        raise _InvalidRequest('请选择与当前 Bot 平台一致的群。')
    saved = store.rooms(bot_hash)['groups'].get(sid)
    if saved is not None:
        if not _group_matches(saved, target):
            raise _InvalidRequest('群订阅适用于 QQ 群，请选择 QQ 群。')
    elif not create:
        raise _InvalidRequest('请先到「群订阅」登记该群。')
    elif target['chat_type'] == 'qq_group':
        # QQ 官方群与频道共用 SDK，只有宿主确认见过的 QQ 群才能新建。
        group = OlivOS.qqGuildv2SDK.qqStore.get_group(bot_hash, target['group_id'])
        if not group or group.get('state') != 'active':
            raise _InvalidRequest('请先在 QQ 群内向 Bot 发送消息，再填写该群的 OpenID。')
    return sid, target


def _bot_map(Proc):
    data = getattr(Proc, 'Proc_data', {})
    bots = data.get('bot_info_dict', {}) if isinstance(data, dict) else {}
    if not isinstance(bots, dict):
        return {}
    return {
        key: value for key, value in bots.items()
        if isinstance(key, str) and re.fullmatch(r'[\w-]+', key, re.ASCII)
    }


def _clean_accounts(raw_accounts):
    """规整已保存的 B站账号列表（按 uid 去重）。"""
    items = []
    seen = set()
    for raw in raw_accounts if isinstance(raw_accounts, list) else ():
        if not isinstance(raw, dict):
            continue
        uid = str(raw.get('uid') or '').strip()
        if not re.fullmatch(r'[0-9]{1,20}', uid) or not uid.strip('0'):
            continue
        uid = uid.lstrip('0')
        if uid in seen:
            continue
        seen.add(uid)
        items.append({
            'uid': uid,
            'uname': str(raw.get('uname') or '').strip()[:64],
            'face': str(raw.get('face') or '').strip(),
            'sessdata': str(raw.get('sessdata') or '').strip(),
            'bili_jct': str(raw.get('bili_jct') or '').strip(),
            'updated_at': int(raw.get('updated_at') or 0) if isinstance(raw.get('updated_at'), int) else 0,
        })
    return items


def _upsert_account(settings, *, uid, uname='', face='', sessdata='', bili_jct='', updated_at=None):
    accounts = _clean_accounts(settings.get('accounts'))
    stamp = int(time.time()) if updated_at is None else int(updated_at)
    existing = next((acc for acc in accounts if acc['uid'] == uid), None)
    entry = {
        'uid': uid,
        'uname': uname or (existing['uname'] if existing else ''),
        'face': face or (existing['face'] if existing else ''),
        'sessdata': sessdata or (existing['sessdata'] if existing else ''),
        'bili_jct': bili_jct or (existing['bili_jct'] if existing else ''),
        'updated_at': stamp,
    }
    remaining = [acc for acc in accounts if acc['uid'] != uid]
    settings['accounts'] = [entry, *remaining][:20]
    return entry


def _view_account(account, active_uid):
    uid = account['uid']
    face = account.get('face') or ''
    return {
        'uid': uid,
        'uname': account.get('uname') or '',
        'avatar': bili_api.avatar_data_uri(face, fetch=False) if face else '',
        'has_face': bool(face),
        'updated_at': account.get('updated_at', 0),
        'active': bool(active_uid and uid == active_uid),
        'has_credentials': bool(account.get('sessdata') and account.get('bili_jct')),
    }


def _global_view():
    settings = store.global_config()
    logged = bili_api.logged_in()
    accounts = _clean_accounts(settings.get('accounts'))
    active_uid = str(settings.get('active_account') or '').strip() if logged else ''
    if active_uid and not any(acc['uid'] == active_uid for acc in accounts):
        active_uid = ''
    # 凭据只发布已配置状态；不发送原文、片段、缓存 Cookie 或代理地址。
    return {
        'cookie': {key: bool(settings['cookie'][key]) for key in config.GLOBAL_DEFAULT['cookie']},
        'logged_in': logged,
        'active_account': active_uid,
        'accounts': [_view_account(acc, active_uid) for acc in accounts],
        'user_agent': settings['user_agent'],
        'proxy': bool(settings['proxy']),
        'whitelist': settings['whitelist'],
        'buvid_cache': {
            'configured': bool(settings['buvid_cache']['cookie']),
            'fetched_at': settings['buvid_cache']['fetched_at'],
        },
        'log_to_file': settings['log_to_file'],
    }


def _view_room(bot_hash, uid, room):
    runtime = room['runtime']
    checks = {'live': runtime, **{kind: room[kind] for kind in ('dynamic', 'video')}}
    return {
        'uid': uid,
        'name': function.names.get((bot_hash, uid)) or f'UID {uid}',
        'room_id': room['room_id'],
        'enabled': {kind: room[kind]['enabled'] for kind in config.KINDS},
        'live_status': runtime['live_status'],
        'has_cover': bool(runtime['last_cover']),
        'last_checks': {kind: check['last_check_at'] for kind, check in checks.items()},
        'last_errors': {kind: check.get('last_error', '') for kind, check in checks.items()},
        'last_chains': {kind: bili_api.uid_chain(uid, kind) for kind in config.KINDS},
        'targets': {
            sid: {**{kind: target[kind] for kind in config.KINDS}, 'subscribers': target['subscribers']}
            for sid, target in room['targets'].items()
        },
    }


def _view_group(sid, group, pair, disabled, today):
    quota = group['at_quota']
    sdk, platform = pair
    group_id = group['group_id']
    supported = (
        (sdk, platform) in _GROUP_TYPES
        and sid == f'{sdk}|{platform}|{group_id}'
        and _group_matches(group, {
            'sdk': sdk, 'platform': platform, 'chat_type': _GROUP_TYPES[pair], 'group_id': group_id,
        })
    )
    dynamic_image = group.get('dynamic_image')
    return {
        'group_id': group_id,
        'platform': group['platform'],
        'push': group['push'],
        'dynamic_image': dynamic_image if type(dynamic_image) is bool else None,
        **{kind: _session_image_mode(group.get(kind)) for kind in config.LIVE_IMAGES},
        'at_all': group['at_all'],
        'used': quota['used'] if quota['date'] == today else 0,
        'last_at_live_time': quota['last_at_live_time'],
        'disabled': sid in disabled,
        'supported': supported,
    }


def _clean_nickname(value):
    if value is None:
        return ''
    text = ' '.join(str(value).split())
    return ''.join(ch for ch in text if ord(ch) >= 32 and ord(ch) != 127)[:64]


def _oliva_bot_name(bot_hash):
    core = sys.modules.get('OlivaDiceCore')
    if core is None:
        return ''
    try:
        custom = getattr(getattr(core, 'msgCustom', None), 'dictStrCustomDict', None)
        if not isinstance(custom, dict):
            return ''
        entry = custom.get(bot_hash)
        if not isinstance(entry, dict):
            return ''
        name = _clean_nickname(entry.get('strBotName'))
        return '' if name in ('', 'OlivaDice') else name
    except Exception:
        return ''


def _bot_nickname(bot_hash, info):
    bot_id = _clean_nickname(getattr(info, 'id', ''))
    with _bot_nick_lock:
        cached = _bot_nick_cache.get(bot_hash)
    if cached and cached[0] and cached[0] != bot_id:
        return cached[0], bot_id
    extends = getattr(info, 'extends', None)
    extends = extends if isinstance(extends, dict) else {}
    for candidate in (
        getattr(info, 'name', ''),
        getattr(info, 'nickname', ''),
        extends.get('name', ''),
        extends.get('nickname', ''),
        extends.get('remark', ''),
        _oliva_bot_name(bot_hash),
    ):
        nick = _clean_nickname(candidate)
        if nick and nick != bot_id:
            return nick, bot_id
    return '', bot_id


def _bot_list(bots):
    result = []
    for key, info in bots.items():
        pair = _bot_pair(info)
        nickname, bot_id = _bot_nickname(key, info)
        result.append({
            'hash': key,
            'id': bot_id,
            'nickname': nickname,
            'name': nickname or bot_id or '未命名 Bot',
            'sdk': pair[0],
            'platform': pair[1],
        })
    return result


def _fetch_bot_login_name(Proc, bot_info):
    if getattr(bot_info, 'enable', True) is False:
        return ''
    platform = getattr(bot_info, 'platform', None)
    if not isinstance(platform, dict) or not platform.get('sdk'):
        return ''
    content_api = getattr(OlivOS, 'contentAPI', None)
    api_mod = getattr(OlivOS, 'API', None)
    if content_api is None or api_mod is None or not hasattr(content_api, 'fake_sdk_event'):
        return ''
    try:
        raw_event = content_api.fake_sdk_event(
            bot_info, platform=platform, fakename=config.PLUGIN_NAME,
            plugin_namespace=config.PLUGIN_NAME, message_mode_tx='olivos_string',
        )
        event = api_mod.Event(raw_event, log_func=None, Proc=Proc)
        result = event.get_login_info(flag_log=False)
    except Exception:
        return ''
    if not isinstance(result, dict) or result.get('active') is not True:
        return ''
    data = result.get('data')
    return _clean_nickname(data.get('name')) if isinstance(data, dict) else ''


def _sync_bot_names(Proc, bots, *, force=False):
    now = time.monotonic()
    pending = []
    with _bot_nick_lock:
        for key in bots:
            cached = _bot_nick_cache.get(key)
            if force or cached is None:
                pending.append(key)
            else:
                ttl = _BOT_NICK_TTL if cached[0] else _BOT_NICK_RETRY_TTL
                if now - cached[1] >= ttl:
                    pending.append(key)
    if pending:
        pool = ThreadPoolExecutor(max_workers=min(8, len(pending)), thread_name_prefix='BiliBiliNotify-botnick')
        try:
            futures = {pool.submit(_fetch_bot_login_name, Proc, bots[key]): key for key in pending}
            done, _ = wait(futures, timeout=3.0)
            stamped = time.monotonic()
            with _bot_nick_lock:
                for future in done:
                    key = futures[future]
                    try:
                        nick = future.result()
                    except Exception:
                        nick = ''
                    _bot_nick_cache[key] = (nick, stamped)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    return {'ok': True, 'state': {'bots': _bot_list(bots)}}


def _state(bots, bot_hash):
    state = {
        'bots': _bot_list(bots),
        'bot_hash': bot_hash,
        'global': _global_view(),
        'bot': None,
        'capabilities': capabilities.snapshot(),
        'rooms': {},
        'groups': {},
        'status': None,
        'logs': store.recent_logs()[-20:],
    }
    if not bot_hash:
        return state
    today = date.today().isoformat()
    bot = store.bot_config(bot_hash)
    data = store.rooms(bot_hash)
    pair = _bot_pair(bots[bot_hash])
    state.update(
        bot={key: bot[key] for key in config.BOT_DEFAULT if key != 'configured_master_list'},
        # 命令名固定在代码里，不落盘：旧配置里残留的 command_name 不再影响解析与显示。

        rooms={uid: _view_room(bot_hash, uid, room) for uid, room in data['rooms'].items()},
        groups={
            sid: _view_group(sid, group, pair, bot['disabled_group_list'], today)
            for sid, group in data['groups'].items()
        },
        status=notify.status(bot_hash),
    )
    state['bot']['command_name'] = config.COMMAND_NAME
    return state


def _proxy(value):
    proxy = _text(value, '代理')
    if not proxy:
        return ''
    try:
        parsed = urlsplit(proxy)
        if (not any(char.isspace() for char in proxy) and parsed.scheme in ('http', 'https')
                and parsed.hostname and parsed.port != 0 and parsed.path in ('', '/') and not parsed.query
                and not parsed.fragment):
            return proxy
    except ValueError:
        raise _InvalidRequest('代理地址或端口无效。') from None
    raise _InvalidRequest('请输入 http://主机:端口 或 https://主机:端口 格式的代理，或清空以直连。')


def _whitelist(value):
    entries = []
    seen = set()
    for raw in _list(value, '白名单'):
        entry = _obj(raw, '白名单条目')
        platform = entry.get('platform')
        if platform not in ('qq', 'qqGuild'):
            raise _InvalidRequest('请选择 OneBot QQ 或 QQ 官方群作为白名单平台。')
        user_id = _id(entry.get('user_id'), platform, '白名单用户 ID')
        key = (platform, user_id.casefold())
        if key not in seen:
            entries.append({'platform': platform, 'user_id': user_id})
            seen.add(key)
    return entries


def _save_global(payload):
    changes = {}
    if 'user_agent' in payload:
        changes['user_agent'] = _text(payload['user_agent'], 'User-Agent')
        if any(ord(char) > 255 for char in changes['user_agent']):
            raise _InvalidRequest('请输入由 HTTP 请求头支持的字符组成的 User-Agent。')
    if 'proxy' in payload:
        changes['proxy'] = _proxy(payload['proxy'])
    if 'whitelist' in payload:
        changes['whitelist'] = _whitelist(payload['whitelist'])
    if 'log_to_file' in payload:
        changes['log_to_file'] = _bool(payload['log_to_file'], '文件日志')
    credentials = {}
    if 'cookie' in payload:
        cookie = _obj(payload['cookie'], 'Cookie')
        for key in config.GLOBAL_DEFAULT['cookie'].keys() & cookie.keys():
            if key == 'b_nut':
                credentials[key] = _int(cookie[key] if cookie[key] != '' else 0, key, 0)
            else:
                value = _text(cookie[key], key)
                if any(not 33 <= ord(char) <= 126 or char == ';' for char in value):
                    raise _InvalidRequest(f'请输入 {key} 的单个 Cookie 字段值。')
                credentials[key] = value
    changed_network = False
    with store.edit_global() as settings:
        updated_cookie = {**settings['cookie'], **credentials}
        if updated_cookie != settings['cookie'] or any(settings[key] != value for key, value in changes.items()):
            cookie_changed = updated_cookie != settings['cookie']
            changed_network = cookie_changed or (
                'proxy' in changes and changes['proxy'] != settings['proxy']
            )
            if cookie_changed and any(k in credentials for k in ('sessdata', 'bili_jct')):
                # 手动改写或清空登录态时解除旧的 active_account 绑定，交给同步重新识别。
                settings['active_account'] = ''
            settings.update(changes, cookie=updated_cookie,
                            meta={'updated_at': int(time.time()), 'updated_by': 'WebUI'})
    if changed_network:
        bili_api.reset_channel_state()


def _prefixes(value):
    prefixes = _list(value, '命令前缀')
    if any(not isinstance(item, str) or len(item) != 1 or item.isspace()
           or 0xD800 <= ord(item) <= 0xDFFF for item in prefixes):
        raise _InvalidRequest('每个命令前缀必须是单个非空白字符。')
    return list(dict.fromkeys(prefixes))


def _disabled_list(value):
    return list(dict.fromkeys(function.sid_for(_target(sid)) for sid in _list(value, '禁用群列表')))


def _word_list(value, label):
    values = _list(value, label)
    if len(values) > _MAX_WORDS:
        raise _InvalidRequest(f'{label}最多填写 {_MAX_WORDS} 项。')
    words = dict.fromkeys(_text(word.strip() if isinstance(word, str) else word, label) for word in values)
    if any(len(word) > _MAX_WORD_LENGTH or re.search(r'[\ud800-\udfff]', word) for word in words):
        raise _InvalidRequest(f'请用最多 {_MAX_WORD_LENGTH} 字的有效文本填写每个{label}条目。')
    return [word for word in words if word]


def _stats_changes(value):
    _require_feature('live_stats')
    stats = _obj(value, '直播数据统计与实时查询')
    changes = {key: _bool(stats[key], label) for key, label in _STATS_BOOLS.items() if key in stats}
    for key, (label, minimum, maximum) in _STATS_LIMITS.items():
        if key in stats:
            changes[key] = _int(stats[key], label, minimum, maximum)
    for feature, key, label in config.LIVE_IMAGES.values():
        if key in stats:
            changes[key] = _bool(stats[key], f'自动推送{label}')
            if changes[key]:
                _require_feature(feature)
    if changes.get('save_report_image') and not (capabilities.can('live_report') or capabilities.can('wordcloud')):
        _require_feature('live_report')
    for key, label in _WORD_LISTS.items():
        if key in stats:
            changes[key] = _word_list(stats[key], label)
    return changes


def _save_bot(payload, bot_hash):
    changes = {}
    if 'live_stats' in payload:
        changes['live_stats'] = _stats_changes(payload['live_stats'])
    if 'enable' in payload:
        changes['enable'] = _bool(payload['enable'], 'Bot 总开关')
    if 'prefix_list' in payload:
        changes['prefix_list'] = _prefixes(payload['prefix_list'])
    if 'poll' in payload:
        poll = _obj(payload['poll'], '轮询设置')
        changes['poll'] = {
            'live_seconds': _int(poll.get('live_seconds'), _POLL_LABELS['live_seconds'], 1),
            'dynamic_seconds': _int(poll.get('dynamic_seconds'), _POLL_LABELS['dynamic_seconds'], 1),
            'video_seconds': _int(poll.get('video_seconds'), _POLL_LABELS['video_seconds'], 1),
            'max_concurrent': _int(poll.get('max_concurrent'), _POLL_LABELS['max_concurrent'], 1, 32),
            **{key: _int(poll[key], _POLL_LABELS[key], 0, limit)
               for key, limit in _SOCKET_POLL_MAX.items() if key in poll},
        }
    if 'retry' in payload:
        retry = _obj(payload['retry'], '重试设置')
        changes['retry'] = {
            'max_times': _int(retry.get('max_times'), '重试次数', 0, 10),
            'interval_ms': _int(retry.get('interval_ms'), '重试间隔', 0, 60000),
        }
    if 'auto_follow' in payload:
        changes['auto_follow'] = _bool(payload['auto_follow'], '自动关注')
    if 'dynamic_source' in payload:
        source = payload['dynamic_source']
        if source not in ('follow', 'poll'):
            raise _InvalidRequest('请选择关注流触发（follow）或逐主播轮询（poll）。')
        changes['dynamic_source'] = source
    if 'at_all' in payload:
        at_all = _obj(payload['at_all'], '@全体设置')
        changes['at_all'] = {
            'daily_limit': _int(at_all.get('daily_limit'), '@全体每日配额', 0),
            'guild_at_once': _bool(at_all.get('guild_at_once'), 'QQ 官方群每次开播仅 @全体一次'),
        }
    if 'at_subscribers' in payload:
        subscribers = _obj(payload['at_subscribers'], '@订阅者')
        for kind in ('dynamic', 'video'):
            if kind in subscribers and _bool(subscribers[kind], config.LABELS[kind] + ' @订阅者'):
                raise _InvalidRequest('仅直播开播可 @订阅者。')
        changes['at_subscribers'] = dict.fromkeys(config.KINDS, False)
        changes['at_subscribers']['live'] = _bool(subscribers.get('live'), '开播 @订阅者')
    if 'push_default' in payload:
        changes['push_default'] = _flags(payload['push_default'], '新群推送默认设置')
    for key, label in _IMAGE_SETTINGS.items():
        if key in payload:
            changes[key] = _bool(payload[key], label)
            if changes[key]:
                _require_feature('dynamic_image')
    if 'send_interval_seconds' in payload:
        changes['send_interval_seconds'] = _int(payload['send_interval_seconds'], '连续发送间隔', 1)
    if 'disabled_group_list' in payload:
        changes['disabled_group_list'] = _disabled_list(payload['disabled_group_list'])
    with store.edit_bot(bot_hash) as settings:
        if 'live_stats' in changes:
            changes['live_stats'] = {**settings['live_stats'], **changes['live_stats']}
        if 'poll' in changes:
            poll = changes['poll']
            saved = settings['poll']
            # 兼容旧面板回传已保存的长连接设置；缺少依赖时仍可将其清零。
            if any(poll[key] and poll[key] != saved[key] for key in _SOCKET_POLL_MAX if key in poll):
                _require_feature('live_stats')
            changes['poll'] = {**saved, **poll}
        if any(settings[key] != value for key, value in changes.items()):
            settings.update(changes, meta={'updated_at': int(time.time())})


def _save_group(payload, bot_hash, bot_info):
    sid, target = _group_target(payload, bot_hash, bot_info, create=True)
    push = _flags(payload['push'], '群推送') if 'push' in payload else None
    at_all = _bool(payload['at_all'], '@全体') if 'at_all' in payload else None
    disabled = _bool(payload['disabled'], '禁用群') if 'disabled' in payload else None
    overrides = {}
    if 'dynamic_image' in payload:
        overrides['dynamic_image'] = _image_override(payload['dynamic_image'])
    for kind, (feature, _, label) in config.LIVE_IMAGES.items():
        if kind in payload:
            overrides[kind] = _session_image_override(payload[kind], feature, label)
    if overrides or push is not None or at_all is not None or sid not in store.rooms(bot_hash)['groups']:
        settings = store.bot_config(bot_hash)
        with store.edit_rooms(bot_hash) as data:
            group = function.ensure_group(data, settings, target)
            if push is not None:
                group['push'] = push
            if at_all is not None:
                group['at_all'] = at_all
            group.update(overrides)
    if disabled is not None:
        with store.edit_bot(bot_hash) as settings:
            disabled_sids = settings['disabled_group_list']
            if disabled and sid not in disabled_sids:
                disabled_sids.append(sid)
                settings['meta']['updated_at'] = int(time.time())
            elif not disabled and sid in disabled_sids:
                disabled_sids.remove(sid)
                settings['meta']['updated_at'] = int(time.time())


def _up_action(action, payload, Proc, bot_hash, bot_info):
    uid = _uid(payload.get('uid'))
    sid, target = _group_target(payload, bot_hash, bot_info) if 'sid' in payload else (None, None)
    # sid 缺省时管理本 Bot 的主播；指定 sid 时仅管理群里的目标及订阅者。
    if action == 'add_up':
        types = _flags(payload['types'], '主播类型') if 'types' in payload else None
        result, _, _ = function.add_up(bot_hash, uid, target, 'WebUI', types)
        if result == 'duplicate':
            raise _InvalidRequest('该群已关联此主播。' if sid else '此主播已添加到当前 Bot。')
        if result == 'missing':
            raise _InvalidRequest('未查到主播。请核对 UID，或先在「总账号」运行接口自检。')
    elif action == 'remove_up':
        if function.remove_up(bot_hash, uid, sid) is None:
            raise _InvalidRequest('未找到要移除的主播，请刷新后重试。')
    elif action == 'toggle_up':
        kind = _kind(payload)
        value = _bool(payload.get('value'), '主播开关')
        if sid is None:
            if not function.toggle_up(bot_hash, uid, kind, value):
                raise _InvalidRequest('主播已移除，请刷新后重试。')
        else:
            with store.edit_rooms(bot_hash) as data:
                group_target = data['rooms'].get(uid, {}).get('targets', {}).get(sid)
                if group_target is None:
                    raise _InvalidRequest('此群未关联该主播，请先关联。')
                group_target[kind] = value
    elif action in ('add_subscriber', 'remove_subscriber'):
        if target is None:
            raise _InvalidRequest('请先选择订阅者所在群。')
        user_id = _id(payload.get('user_id'), target['platform'], '订阅者 ID')
        if not function.set_subscriber(bot_hash, uid, sid, user_id, action == 'add_subscriber'):
            raise _InvalidRequest('此群未关联该主播，请先关联。')
    else:
        targets = None
        if sid is not None:
            linked = store.rooms(bot_hash)['rooms'].get(uid, {}).get('targets', {}).get(sid)
            if not linked:
                raise _InvalidRequest('此群未关联该主播，请先关联。')
            targets = (linked,)
        result = notify.test_push(Proc, bot_hash, uid, _kind(payload), targets)
        errors = {
            'missing': '主播已移除，请刷新后重试。',
            'empty': '请确认有可推送的内容、Bot 处于启用状态，并已关联启用的接收群。',
            'failed': '部分或全部测试推送失败，请查看「运行状态」中的日志。',
        }
        if result != 'ok':
            raise _InvalidRequest(errors[result])


def _cover(bot_hash, uid):
    cover_url = store.rooms(bot_hash)['rooms'].get(uid, {}).get('runtime', {}).get('last_cover')
    if not cover_url:
        raise _InvalidRequest('直播封面将在下一次成功检查后可用。')
    path = bili_api.download_image(cover_url)
    if path is None:
        raise _InvalidRequest('载入封面失败，请稍后再试。')
    try:
        image_type = _IMAGES.get(path.suffix.lower())
        if not image_type:
            raise _InvalidRequest('面板支持预览 JPEG、PNG、GIF、WebP、AVIF 与 BMP 封面。')
        with path.open('rb') as file:
            content = file.read(_MAX_PREVIEW + 1)
        # 回包会在宿主的事件缓冲中保留，限制单次预览体积。
        if len(content) > _MAX_PREVIEW:
            raise _InvalidRequest('封面超过 512 KiB；该上限仅适用于面板预览。')
        encoded = base64.b64encode(content).decode('ascii')
        return {'image': f'data:image/{image_type};base64,{encoded}'}
    except OSError:
        raise _InvalidRequest('读取封面缓存失败，请稍后再试。') from None
    finally:
        bili_api.release_image(path)


def _session_room(payload, bot_hash):
    uid = _uid(payload.get('uid'))
    room = store.rooms(bot_hash)['rooms'].get(uid)
    if room is None:
        raise _InvalidRequest('请在当前 Bot 的「主播管理」中选择已添加的主播。')
    return uid, room


def _list_sessions(payload, bot_hash):
    _require_feature('live_stats')
    uid, _ = _session_room(payload, bot_hash)
    hide_revenue = store.bot_config(bot_hash)['live_stats']['hide_revenue']
    rows = live_stats.list_sessions(uid, limit=10)
    return {'sessions': [
        {key: value for key, value in row.items() if key in _SESSION_FIELDS or (key == 'gold' and not hide_revenue)}
        for row in rows
    ]}


def _preview_session_image(payload, bot_hash):
    kind = payload.get('kind')
    if not isinstance(kind, str) or kind not in config.LIVE_IMAGES:
        raise _InvalidRequest('请选择直播报告或弹幕词云。')
    feature, _, label = config.LIVE_IMAGES[kind]
    _require_feature(feature)
    uid, room = _session_room(payload, bot_hash)
    session_id = _int(payload.get('session_id'), '场次 ID', 1, 2**63 - 1)
    detail = live_stats.session_detail(session_id, uid=uid, include_danmu=kind == 'cloud')
    if detail is None:
        raise _InvalidRequest('请展开此主播的历史场次，选择一场直播。')
    if kind == 'report':
        detail['avatar_url'] = room['runtime'].get('avatar_url', '')
    settings = store.bot_config(bot_hash)['live_stats']
    path = function.render_session_image(kind, detail, settings, archive_dir=None)
    if path is None:
        raise _InvalidRequest(f'当前场次暂无可预览的{label}。')
    try:
        with path.open('rb') as file:
            if file.seek(0, io.SEEK_END) > _MAX_SESSION_PREVIEW:
                raise _InvalidRequest('图片预览上限为 2 MiB，请选择其他场次。')
            file.seek(0)
            content = file.read(_MAX_SESSION_PREVIEW)
        if not content:
            raise _InvalidRequest(f'请重新生成{label}预览。')
        return {'image': 'data:image/png;base64,' + base64.b64encode(content).decode('ascii')}
    except OSError:
        raise _InvalidRequest('读取预览图片失败，请重新生成。') from None
    finally:
        sender.release_local_image(path)


def _qr_image(url):
    """渲染登录二维码并内联给前端。"""
    import qrcode

    buffer = io.BytesIO()
    if capabilities.can('dynamic_image'):
        qrcode.make(url).save(buffer)
        mime = 'image/png'
    else:
        from qrcode.image.svg import SvgPathFillImage

        qrcode.make(url, image_factory=SvgPathFillImage).save(buffer)
        mime = 'image/svg+xml'
    return f'data:{mime};base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def _qr_generate():
    _require_feature('qr_login')
    data, error = bili_api.qr_generate()
    if error:
        raise _InvalidRequest('申请二维码失败（%s）：%s' % (error[0], error[1]))
    url = str(data.get('url') or '')
    key = str(data.get('qrcode_key') or '')
    if not url or not key:
        raise _InvalidRequest('二维码接口返回格式异常。')
    return {'ok': True, 'state': {'qr': {'qrcode_key': key, 'image': _qr_image(url)}}}


def _qr_poll(payload):
    """轮询扫码状态；成功后写入凭据、拉取账号资料并加入多账号列表。"""
    key = payload.get('qrcode_key')
    if not isinstance(key, str) or not key or len(key) > 128:
        raise _InvalidRequest('缺少有效的二维码标识。')
    data, error = bili_api.qr_poll(key)
    if error:
        raise _InvalidRequest('查询扫码状态失败（%s）：%s' % (error[0], error[1]))
    code = data.get('code')
    if code != 0:
        return {'ok': True, 'state': {'qr': {'status': int(code) if isinstance(code, int) else -1,
                                             'message': str(data.get('message') or '')}}}
    pairs = bili_api.parse_login_cookie(str(data.get('url') or ''))
    if not pairs.get('sessdata'):
        raise _InvalidRequest('登录凭据返回异常（缺少 SESSDATA），请重新扫码。')
    now = int(time.time())
    with store.edit_global() as settings:
        settings['cookie']['sessdata'] = pairs['sessdata']
        settings['cookie']['bili_jct'] = pairs.get('bili_jct', '')
        # 旧指纹属于上一个会话，清掉让下一次请求重新领。
        settings['buvid_cache'] = {'cookie': '', 'fetched_at': 0.0}
        settings['meta'] = {'updated_at': now, 'updated_by': '扫码登录'}
    bili_api.reset_channel_state()

    profile, _ = bili_api.account_profile(quiet=True)
    raw_uid = (profile or {}).get('uid') or str(pairs.get('dede_user_id') or '').strip()
    uid = raw_uid.lstrip('0') if re.fullmatch(r'[0-9]{1,20}', raw_uid) and raw_uid.strip('0') else ''
    uname = (profile or {}).get('uname') or ''
    face = (profile or {}).get('face') or ''
    if uid:
        with store.edit_global() as settings:
            _upsert_account(
                settings, uid=uid, uname=uname, face=face,
                sessdata=pairs['sessdata'], bili_jct=pairs.get('bili_jct', ''), updated_at=now,
            )
            settings['active_account'] = uid
    if face:
        bili_api.avatar_data_uri(face, fetch=True)
    return {'ok': True, 'state': {'qr': {
        'status': 0, 'message': '登录成功', 'uid': uid, 'uname': uname,
    }}}


def _account_sync(bots, bot_hash):
    """同步当前登录账号的头像/昵称/UID，并预热已存账号头像缓存。"""
    account_notice = ''
    if bili_api.logged_in():
        profile, error = bili_api.account_profile(quiet=True)
        if profile:
            now = int(time.time())
            with store.edit_global() as settings:
                _upsert_account(
                    settings,
                    uid=profile['uid'],
                    uname=profile['uname'],
                    face=profile['face'],
                    sessdata=settings['cookie'].get('sessdata', ''),
                    bili_jct=settings['cookie'].get('bili_jct', ''),
                    updated_at=now,
                )
                settings['active_account'] = profile['uid']
        elif error and error[0] == -101:
            account_notice = '当前账号登录态已失效（-101），请重新扫码或切换其他账号。'
    for account in _clean_accounts(store.global_config().get('accounts')):
        if account.get('face'):
            bili_api.avatar_data_uri(account['face'], fetch=True)
    result = _state(bots, bot_hash)
    if account_notice:
        result['account_notice'] = account_notice
    return {'ok': True, 'state': result}


def _switch_account(payload):
    uid = _uid(payload.get('uid'))
    with store.edit_global() as settings:
        accounts = _clean_accounts(settings.get('accounts'))
        target = next((acc for acc in accounts if acc['uid'] == uid), None)
        if target is None:
            raise _InvalidRequest('未找到该已存账号，请刷新页面。')
        if not target.get('sessdata') or not target.get('bili_jct'):
            raise _InvalidRequest('该账号缺少完整登录凭据，请重新扫码登录。')
        settings['cookie']['sessdata'] = target['sessdata']
        settings['cookie']['bili_jct'] = target['bili_jct']
        settings['buvid_cache'] = {'cookie': '', 'fetched_at': 0.0}
        settings['active_account'] = uid
        settings['accounts'] = accounts
        settings['meta'] = {'updated_at': int(time.time()), 'updated_by': '切换账号'}
    bili_api.reset_channel_state()


def _remove_account(payload):
    uid = _uid(payload.get('uid'))
    cleared_active = False
    with store.edit_global() as settings:
        accounts = _clean_accounts(settings.get('accounts'))
        remaining = [acc for acc in accounts if acc['uid'] != uid]
        if len(remaining) == len(accounts):
            raise _InvalidRequest('未找到要移除的账号，请刷新页面。')
        settings['accounts'] = remaining
        if str(settings.get('active_account') or '').strip() == uid:
            settings['active_account'] = ''
            settings['cookie']['sessdata'] = ''
            settings['cookie']['bili_jct'] = ''
            settings['buvid_cache'] = {'cookie': '', 'fetched_at': 0.0}
            cleared_active = True
        settings['meta'] = {'updated_at': int(time.time()), 'updated_by': '移除账号'}
    if cleared_active:
        bili_api.reset_channel_state()


def dispatch(payload, Proc):
    """校验请求并返回显式构建的、安全可序列化的页面状态。"""
    payload = _obj(payload, '请求数据')
    action = payload.get('action')
    if not isinstance(action, str):
        raise _InvalidRequest('缺少有效的面板操作。')
    bots = _bot_map(Proc)
    bot_hash = payload.get('bot_hash', '')
    if not isinstance(bot_hash, str) or (bot_hash and bot_hash not in bots):
        raise _InvalidRequest('所选 Bot 已不可用，请刷新账号列表。')
    if not bot_hash:
        if action not in _GLOBAL_ACTIONS:
            raise _InvalidRequest('请先从面板上方选择一个 Bot。')
        bot_hash = next(iter(bots), '')
    if action == 'qr_generate':
        return _qr_generate()
    if action == 'qr_poll':
        return _qr_poll(payload)
    if action == 'account_sync':
        return _account_sync(bots, bot_hash)
    if action == 'sync_bot_names':
        force = _bool(payload.get('force', False), '强制刷新昵称')
        return _sync_bot_names(Proc, bots, force=force)
    if action == 'switch_account':
        _switch_account(payload)
    elif action == 'remove_account':
        _remove_account(payload)
    elif action == 'save_global':
        _save_global(payload)
    elif action == 'save_bot':
        _save_bot(payload, bot_hash)
    elif action == 'save_group':
        _save_group(payload, bot_hash, bots[bot_hash])
    elif action in ('add_up', 'remove_up', 'toggle_up', 'add_subscriber', 'remove_subscriber', 'test_push'):
        _up_action(action, payload, Proc, bot_hash, bots[bot_hash])
    elif action == 'refresh_buvid':
        _, error = bili_api.refresh_buvid()
        if error:
            raise _InvalidRequest(f'领取指纹失败（{error[0]}）：{error[1]}。请检查网络和代理设置。')
    elif action == 'probe_api':
        # 只返回请求层的安全摘要与分链状态，不返回接口响应体或任何凭据。
        kind = _kind(payload, (*config.KINDS, 'nav'))
        uid = _uid(payload.get('uid', '2'))
        mode = payload.get('mode', 'cascade')
        if mode not in ('cascade', 'full'):
            raise _InvalidRequest('请选择级联检查（cascade）或完整检查（full）。')
        bypass = _bool(payload.get('bypass_cooldown', True), '跳过冷却')
        room_id = ''
        if bot_hash:
            room = store.rooms(bot_hash)['rooms'].get(uid)
            if isinstance(room, dict):
                room_id = str(room.get('room_id') or '')
        probe = bili_api.probe(kind, uid, mode=mode, bypass_cooldown=bypass, room_id=room_id)
        return {'ok': True, 'state': probe}
    elif action == 'get_cover':
        return {'ok': True, 'state': _cover(bot_hash, _uid(payload.get('uid')))}
    elif action == 'list_sessions':
        return {'ok': True, 'state': _list_sessions(payload, bot_hash)}
    elif action == 'preview_session_image':
        return {'ok': True, 'state': _preview_session_image(payload, bot_hash)}
    elif action != 'get_state':
        raise _InvalidRequest('请刷新页面后选择有效的面板操作。')
    return {'ok': True, 'state': _state(bots, bot_hash)}


def handle_menu_event(plugin_event, Proc):
    data = getattr(plugin_event, 'data', None)
    if getattr(data, 'namespace', None) != config.PLUGIN_NAME:
        return
    context = getattr(data, 'webui', None)
    if not isinstance(context, dict):
        return
    request_id = context.get('request_id')
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        return
    try:
        if getattr(data, 'event', None) != config.WEBUI_EVENT:
            raise _InvalidRequest('未知的 WebUI 事件，请重新打开面板。')
        response = dispatch(getattr(data, 'payload', None), Proc)
    except _InvalidRequest as error:
        response = {'ok': False, 'error': str(error)}
    except store.StorageError:
        response = {'ok': False, 'error': '写入失败，检查目录权限，再刷新确认当前状态。'}
    except Exception as error:
        # 不记录 payload、异常原文、会话或凭据。
        store.log(Proc, f'WebUI 操作失败：{type(error).__name__}', level=3)
        response = {'ok': False, 'error': '面板操作失败，请刷新确认并查看「运行状态」的日志。'}
    try:
        if plugin_event.send('webui', request_id, response) is not True:
            store.log(Proc, 'WebUI 回包未能入队。', level=3)
    except Exception as error:
        store.log(Proc, f'WebUI 回包失败：{type(error).__name__}', level=3)
