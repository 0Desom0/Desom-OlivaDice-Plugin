from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import math
import re
import tempfile
import time
from pathlib import Path
from threading import Lock, local
from urllib.parse import parse_qsl, quote, urlsplit

import requests

from . import config, store

BASE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Accept-Encoding': 'identity',
    'Origin': 'https://www.bilibili.com',
    'Referer': 'https://www.bilibili.com/',
}
_API = 'https://api.bilibili.com'
_LIVE_API = 'https://api.live.bilibili.com'
_SPI = f'{_API}/x/frontend/finger/spi'
_LIVE = f'{_LIVE_API}/room/v1/Room/get_status_info_by_uids'
_LIVE_ROOM_INFO = f'{_LIVE_API}/room/v1/Room/get_info'
_MASTER = f'{_LIVE_API}/live_user/v1/Master/info'
_DYNAMIC = f'{_API}/x/polymer/web-dynamic/v1/feed/space'
_NAVNUM = f'{_API}/x/space/navnum'
_NAV = f'{_API}/x/web-interface/nav'
_VIDEO = f'{_API}/x/space/wbi/arc/search'
# 空间接口被 IP 风控时的降级通道：opus 动态流与搜索接口在机房 IP 上仍可用（2026-11-25 实测）。
_OPUS = f'{_API}/x/polymer/web-dynamic/v1/opus/feed/space'
_SEARCH = f'{_API}/x/web-interface/wbi/search/type'
_CARD = f'{_API}/x/web-interface/card'
_DANMU = f'{_LIVE_API}/xlive/web-room/v1/index/getDanmuInfo'
_DYNAMIC_NEW = 'https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/dynamic_new'
# 扫码登录（passport 域名，不走 api.bilibili.com 的空间风控）
_FEED_ALL = f'{_API}/x/polymer/web-dynamic/v1/feed/all'
_RELATION = f'{_API}/x/relation/modify'
_QR_GENERATE = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
_QR_POLL = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'
_ENDPOINTS = frozenset((_SPI, _LIVE, _LIVE_ROOM_INFO, _MASTER, _DYNAMIC, _NAVNUM, _NAV, _VIDEO, _OPUS,
                        _SEARCH, _CARD, _DANMU, _DYNAMIC_NEW, _FEED_ALL, _QR_GENERATE, _QR_POLL))
# 只有风控/未登录类错误才挂冷却；未命中某 UID 绝不冷却关注流。
_FALLBACK_CODES = (-412, -352, -403)
_FOLLOW_COOLDOWN_CODES = (-101, -412, -352, -403)
_NO_LOGIN = (-101, '未登录 B站账号，跳过关注流')
_RISK = (-412, 'B站风控，请在 WebUI 填写 Cookie 或检查网络出口')
_FORMAT = (-1, 'B站响应格式异常')
_LOCAL = (-2, '无法读取 B站请求配置')
_NETWORK = (-3, 'B站网络连接失败或超时')
_CHAIN_COOLDOWN = 60.0
_TZ_CN = timezone(timedelta(hours=8))
_BUVID_TTL = 86400
_NAME_TTL = 3600
_WBI_TTL = 3600
# B 站官方 mixinKeyEncTab（64 项）取前 32 位；与 StarBot/utils/wbi.py 一致。
# 之前从 BiliShareInfo 抄的 32 项表从第 27 位起是错的，签名会失配。
_WBI_TAB64 = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)
_WBI_INDICES = _WBI_TAB64[:32]
_IMAGE_DOMAINS = ('hdslb.com', 'biliimg.com', 'bilibili.com', 'bilivideo.com', 'bilivideo.cn')
_IMAGE_EXTENSIONS = {'jpeg': 'jpg', 'png': 'png', 'gif': 'gif', 'webp': 'webp', 'avif': 'avif', 'bmp': 'bmp'}
_MAX_IMAGE = 5 * 1024 * 1024
_buvid_lock = Lock()
_wbi_lock = Lock()
_wbi_cache = ('', 0)
_name_lock = Lock()
_name_cache = {}
_uid_cache = (0, 0.0)
_image_lock = Lock()
_image_leases = {}
_QUIET = local()


@contextmanager
def _quiet_requests():
    prev = getattr(_QUIET, 'active', False)
    _QUIET.active = True
    try:
        yield
    finally:
        _QUIET.active = prev


def _is_quiet(quiet):
    return bool(quiet or getattr(_QUIET, 'active', False))


def _failure(url, error):
    # 绝不记录响应原文、请求 URL 参数、代理或异常内容。
    store.log(None, f'B站接口 {urlsplit(url).path} 失败：code={error[0]} {error[1]}', level=3)
    return None, error


def _base_headers(settings):
    headers = BASE_HEADERS.copy()
    agent = settings['user_agent']
    if isinstance(agent, str) and agent and agent.isascii() and agent.isprintable():
        headers['User-Agent'] = agent
    return headers


def _fetch_json(url, *, params, settings, headers, timeout, retry, interval=5.0, allowed_codes=()):
    proxy = settings['proxy']
    proxies = {'https': proxy} if proxy else {}
    while True:
        try:
            with requests.Session() as client:
                client.trust_env = False
                with client.get(url, params=params, headers=headers, proxies=proxies, timeout=timeout,
                                allow_redirects=False) as response:
                    if response.status_code == 412:
                        return None, _RISK, retry
                    if not 200 <= response.status_code < 300:
                        status = response.status_code
                        # 5xx 是服务端临时故障，值得重试；4xx 与风控码重试只会加重封禁。
                        if status >= 500 and retry > 0:
                            retry -= 1
                            time.sleep(interval)
                            continue
                        return None, (status, f'B站返回 HTTP {status}'), retry
                    try:
                        payload = response.json()
                    except ValueError:
                        return None, _FORMAT, retry
                    if not isinstance(payload, dict) or type(payload.get('code')) is not int:
                        return None, _FORMAT, retry
                    code = payload['code']
                    if code == -412:
                        return None, _RISK, retry
                    if code != 0 and code not in allowed_codes:
                        return None, (code, 'B站接口返回错误'), retry
                    return payload.get('data'), None, retry
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
            if retry <= 0:
                return None, _NETWORK, retry
            retry -= 1
            time.sleep(interval)
        except (requests.RequestException, ValueError, TypeError, UnicodeError):
            return None, (-4, 'B站请求失败，请检查请求配置'), retry


def _cookie_value(value):
    text = str(value) if value is not None else ''
    if text and text.isascii() and text.isprintable() and not any(c in text for c in '; \t\"\\'):
        return text
    return ''


def _cache_values(cache):
    result = {}
    for item in cache['cookie'].split(';'):
        key, _, value = item.strip().partition('=')
        if key in ('buvid3', 'buvid4') and (value := _cookie_value(value)):
            result[key] = value
    return result


def _request_timeout(settings):
    http = settings.get('http')
    value = http.get('timeout') if isinstance(http, dict) else None
    return value if type(value) in (int, float) and 0 < value < float('inf') else config.HTTP_TIMEOUT


def _refresh_buvid(*, previous=None, quiet=False):
    silent = _is_quiet(quiet)
    with _buvid_lock:
        settings = store.global_config()
        cache = settings['buvid_cache']
        # 并发 412 只需一个 worker 重新领取；其它 worker 复用已更新的指纹。
        if previous is not None and cache != previous and len(_cache_values(cache)) == 2:
            return cache, None
        data, error, _ = _fetch_json(
            _SPI, params=None, settings=settings, headers=_base_headers(settings),
            timeout=_request_timeout(settings), retry=1,
        )
        if error:
            return (None, error) if silent else _failure(_SPI, error)
        values = [_cookie_value(data.get(key)) for key in ('b_3', 'b_4')] if isinstance(data, dict) else []
        if len(values) != 2 or not all(values):
            return (None, _FORMAT) if silent else _failure(_SPI, _FORMAT)
        fresh = {'cookie': f'buvid3={values[0]}; buvid4={values[1]}', 'fetched_at': int(time.time())}
        try:
            with store.edit_global() as updated:
                updated['buvid_cache'] = fresh
        except store.StorageError:
            store.log(None, 'B站设备指纹已领取，但写入缓存失败', level=3)
        return fresh, None


def refresh_buvid():
    """主动领取指纹；调用方不得把返回的缓存内容发给 WebUI。"""
    try:
        return _refresh_buvid()
    except store.StorageError:
        return _failure(_SPI, _LOCAL)


_TICKET_KEY = b'XgwSnGZ1p'
_TICKET_LOCK = Lock()
_TICKET = {'value': '', 'expires': 0.0}


def _web_ticket(settings, cache):
    """B站 web ticket（StarBot 同款），降低接口风控概率；TTL 通常 3 天，内存缓存。

    申请接口只接受 POST，GET 会 405。票据申请失败不影响请求本身，返回空串即可。
    """
    if _TICKET['value'] and time.time() < _TICKET['expires']:
        return _TICKET['value']
    with _TICKET_LOCK:
        if _TICKET['value'] and time.time() < _TICKET['expires']:
            return _TICKET['value']
        csrf = _cookie_value(settings['cookie'].get('bili_jct'))
        if not csrf:
            return ''
        stamp = int(time.time())
        sign = hmac.new(_TICKET_KEY, ('ts%d' % stamp).encode(), hashlib.sha256).hexdigest()
        url = (f'{_API}/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket'
               f'?key_id=ec02&hexsign={sign}&context[ts]={stamp}&csrf={csrf}')
        try:
            with requests.Session() as client:
                client.trust_env = False
                with client.post(url, headers=_base_headers(settings),
                                 timeout=_request_timeout(settings), allow_redirects=False) as response:
                    payload = response.json() if response.status_code == 200 else {}
        except (requests.RequestException, ValueError):
            return ''
        data = payload.get('data') if isinstance(payload, dict) else None
        ticket = str((data or {}).get('ticket') or '')
        if not ticket:
            return ''
        created = int((data or {}).get('created_at') or stamp)
        ttl = int((data or {}).get('ttl') or 3600)
        # 提前 10 分钟过期，避免边界时刻拿到失效票据。
        _TICKET['value'] = ticket
        _TICKET['expires'] = created + ttl - 600
        return ticket


def _request_headers(settings, cache):
    headers = _base_headers(settings)
    saved = settings['cookie']
    values = _cache_values(cache) if 0 <= time.time() - cache['fetched_at'] < _BUVID_TTL else {}
    for key in ('buvid3', 'buvid4'):
        if value := _cookie_value(saved[key]):
            values[key] = value
    values['b_nut'] = _cookie_value(saved['b_nut'] or int(cache['fetched_at'] or time.time()))
    for source, name in (('sessdata', 'SESSDATA'), ('bili_jct', 'bili_jct')):
        if value := _cookie_value(saved[source]):
            values[name] = value
    if ticket := _web_ticket(settings, cache):
        values['bili_ticket'] = ticket
        values['bili_ticket_expires'] = str(int(_TICKET['expires']) + 600)
    headers['Cookie'] = '; '.join(f'{key}={value}' for key, value in values.items())
    return headers


def request_json(url, *, params=None, timeout=None, retry=None, force_buvid=False, allowed_codes=(), quiet=False):
    """固定 B站接口，返回解包后的 data 或安全错误。"""
    silent = _is_quiet(quiet)
    if url not in _ENDPOINTS:
        return None, (-4, '未配置的 B站接口')
    try:
        settings = store.global_config()
        cache = settings['buvid_cache']
        timeout = _request_timeout(settings) if timeout is None else timeout
        policy = settings.get('retry') if isinstance(settings.get('retry'), dict) else {}
        if retry is None:
            # _int_field(None) 是 0，这里要区分「没配」和「配成 0」。
            raw_times = policy.get('max_times')
            retry = (config.BOT_DEFAULT['retry']['max_times'] if raw_times is None
                     else _int_field(raw_times))
        retry = max(0, min(10, retry))
        raw_interval = policy.get('interval_ms')
        interval = (config.BOT_DEFAULT['retry']['interval_ms'] if raw_interval is None
                    else _int_field(raw_interval)) / 1000.0
        interval = max(0.0, min(60.0, interval))
        if url == _SPI:
            headers = _base_headers(settings)
        else:
            saved = settings['cookie']
            manual = _cookie_value(saved['buvid3']) and _cookie_value(saved['buvid4'])
            valid_cache = 0 <= time.time() - cache['fetched_at'] < _BUVID_TTL and len(_cache_values(cache)) == 2
            if force_buvid or (not manual and not valid_cache):
                fresh, _ = _refresh_buvid(previous=None if force_buvid else cache, quiet=silent)
                if fresh:
                    cache = fresh
            headers = _request_headers(settings, cache)
        data, error, retries = _fetch_json(
            url, params=params, settings=settings, headers=headers, timeout=timeout, retry=retry,
            interval=interval, allowed_codes=allowed_codes,
        )
        if error == _RISK and url != _SPI:
            fresh, _ = _refresh_buvid(previous=cache, quiet=silent)
            data, error, _ = _fetch_json(
                url, params=params, settings=settings, headers=_request_headers(settings, fresh or cache),
                timeout=timeout, retry=retries, interval=interval, allowed_codes=allowed_codes,
            )
    except store.StorageError:
        return (None, _LOCAL) if silent else _failure(url, _LOCAL)
    if error:
        return (None, error) if silent else _failure(url, error)
    return data, None


def _shape(url, data, error, expected, *, quiet=False):
    if error:
        return None, error
    if not isinstance(data, expected):
        return (None, _FORMAT) if _is_quiet(quiet) else _failure(url, _FORMAT)
    return data, None


_CHANNEL_LABELS = {
    'live': {1: '批量直播状态', 2: '单间直播信息', 3: '弹幕长连接鉴权'},
    'dynamic': {1: '关注流（全部动态）', 2: '空间动态流', 3: 'Opus 动态流'},
    'video': {1: '关注流（视频投稿）', 2: '空间投稿 WBI', 3: 'WBI 搜索兜底'},
}
_CHANNEL_LOCK = Lock()
_chain_cooldowns = {}
_chain_faults = {}
_uid_chains = {}
_channel_state = {
    kind: {'overall': 'idle', 'active_chain': 0, 'active_label': '', 'updated_at': 0, 'note': ''}
    for kind in config.KINDS
}


def _cooldown_left(kind, index, now=None):
    current = time.time() if now is None else now
    with _CHANNEL_LOCK:
        until = _chain_cooldowns.get((kind, index), 0.0)
    return max(0, math.ceil(until - current)) if until > current else 0


def _set_cooldown(kind, index, seconds=_CHAIN_COOLDOWN):
    with _CHANNEL_LOCK:
        _chain_cooldowns[(kind, index)] = time.time() + seconds


def _clear_cooldown(kind, index):
    with _CHANNEL_LOCK:
        _chain_cooldowns.pop((kind, index), None)


def _mark_fault(kind, index, code, *, fallback_to=None):
    """只在故障状态发生切换时记一条摘要日志，避免每轮刷屏。"""
    label = _CHANNEL_LABELS.get(kind, {}).get(index, f'链 {index}')
    kind_name = config.LABELS.get(kind, kind)
    key = (kind, index)
    with _CHANNEL_LOCK:
        prev = _chain_faults.get(key)
        _chain_faults[key] = code
    if prev != code:
        extra = f'，已降级至链 {fallback_to}（{_CHANNEL_LABELS[kind][fallback_to]}）' if fallback_to else ''
        store.log(None, f'[{kind_name}] 链 {index}（{label}）失败（code={code}）{extra}', level=3)


def _clear_fault(kind, index):
    label = _CHANNEL_LABELS.get(kind, {}).get(index, f'链 {index}')
    kind_name = config.LABELS.get(kind, kind)
    key = (kind, index)
    with _CHANNEL_LOCK:
        prev = _chain_faults.pop(key, None)
    if prev is not None:
        store.log(None, f'[{kind_name}] 链 {index}（{label}）已恢复正常', level=2)


def _update_channel(kind, uid, *, overall, active_chain, note=''):
    label = _CHANNEL_LABELS.get(kind, {}).get(active_chain, '') if active_chain else ''
    now = int(time.time())
    with _CHANNEL_LOCK:
        _channel_state[kind] = {
            'overall': overall,
            'active_chain': active_chain,
            'active_label': label,
            'updated_at': now,
            'note': note,
        }
        if uid and active_chain:
            _uid_chains[(str(uid), kind)] = {
                'chain': active_chain, 'label': label, 'overall': overall, 'at': now,
            }


def uid_chain(uid, kind):
    with _CHANNEL_LOCK:
        info = _uid_chains.get((str(uid), kind))
    return dict(info) if info else None


def channel_health():
    """运行期各业务通道健康快照（纯安全摘要，零网络请求）。"""
    now = time.time()
    is_logged = logged_in()
    result = {}
    with _CHANNEL_LOCK:
        for kind in config.KINDS:
            snap = dict(_channel_state[kind])
            c1 = max(0, math.ceil(_chain_cooldowns.get((kind, 1), 0.0) - now))
            c2 = max(0, math.ceil(_chain_cooldowns.get((kind, 2), 0.0) - now))
            cooldown = max(c1, c2)
            note = snap.get('note', '')
            if not note:
                if kind in ('dynamic', 'video') and not is_logged:
                    note = '未登录，跳过关注流'
                elif c2 > 0:
                    code = _chain_faults.get((kind, 2))
                    note = f'链 2 冷却中（code={code}）' if code is not None else '链 2 冷却中'
                elif c1 > 0:
                    code = _chain_faults.get((kind, 1))
                    note = f'链 1 冷却中（code={code}）' if code is not None else '链 1 冷却中'
            snap['cooldown_left'] = cooldown
            snap['note'] = note
            result[kind] = snap
    return result


def reset_channel_state():
    """测试或重置凭据时清空内存通道状态与缓存。"""
    with _CHANNEL_LOCK:
        _chain_cooldowns.clear()
        _chain_faults.clear()
        _uid_chains.clear()
        for kind in config.KINDS:
            _channel_state[kind] = {
                'overall': 'idle', 'active_chain': 0, 'active_label': '', 'updated_at': 0, 'note': '',
            }
    with _FEED_LOCK:
        for entry in _feed_cache.values():
            entry.update(at=0.0, items=None)


def _parse_live_time(value):
    if isinstance(value, int):
        return max(0, value)
    text = str(value or '').strip()
    if not text or text.startswith('0000-00-00'):
        return 0
    if text.isdigit():
        return int(text)
    try:
        dt = datetime.strptime(text, '%Y-%m-%d %H:%M:%S').replace(tzinfo=_TZ_CN)
        return max(0, int(dt.timestamp()))
    except ValueError:
        return 0


def live_status(uids, *, quiet=False):
    uids = list(dict.fromkeys(map(str, uids)))
    if not uids:
        return {}, None
    data, error = request_json(_LIVE, params=[('uids[]', uid) for uid in uids], quiet=quiet)
    return _shape(_LIVE, data, error, dict, quiet=quiet)


def live_room_info(uid, room_id='', *, quiet=False):
    """直播链 2：按 room_id 查询单间直播信息，并归一化为与批量接口同构的字段。"""
    uid = str(uid)
    silent = _is_quiet(quiet)
    resolved_room = str(room_id or '').strip()
    if resolved_room == '0':
        resolved_room = ''
    uname = ''
    if not resolved_room:
        with _quiet_requests():
            master, error = master_info(uid)
        if error:
            return None, error
        resolved_room = str((master or {}).get('room_id') or '').strip()
        if resolved_room == '0':
            resolved_room = ''
        info = (master or {}).get('info') if isinstance(master, dict) else None
        if isinstance(info, dict):
            uname = str(info.get('uname') or '')
    if not resolved_room:
        return None, (-1, '该 UID 未开通直播间')
    data, error = request_json(_LIVE_ROOM_INFO, params={'room_id': resolved_room}, quiet=silent)
    data, error = _shape(_LIVE_ROOM_INFO, data, error, dict, quiet=silent)
    if error:
        return None, error
    if 'live_status' not in data:
        return (None, _FORMAT) if silent else _failure(_LIVE_ROOM_INFO, _FORMAT)
    return {
        'uid': _int_field(data.get('uid') or uid),
        'room_id': _int_field(data.get('room_id') or resolved_room),
        'uname': uname,
        'live_status': _int_field(data.get('live_status')),
        'live_time': _parse_live_time(data.get('live_time')),
        'title': str(data.get('title') or ''),
        'area_v2_name': str(data.get('area_name') or data.get('area_v2_name') or ''),
        'cover_from_user': _https(data.get('user_cover') or data.get('cover_from_user') or ''),
        'keyframe': _https(data.get('keyframe') or ''),
    }, None


def live_detail(uid, room_id=''):
    """运行期单主播直播查询：链 1 批量状态 → 链 2 单间直播信息。"""
    uid = str(uid)
    c1_error = None
    if _cooldown_left('live', 1) <= 0:
        with _quiet_requests():
            data, error = live_status((uid,))
        if error is None and isinstance(data, dict):
            payload = data.get(uid)
            if isinstance(payload, dict) and 'live_status' in payload:
                _clear_fault('live', 1)
                _update_channel('live', uid, overall='ok', active_chain=1)
                return payload, None
            c1_error = (-1, '直播接口未返回该主播状态')
        else:
            c1_error = error
            if error and error[0] in _FALLBACK_CODES:
                _set_cooldown('live', 1)
                _mark_fault('live', 1, error[0], fallback_to=2)
    else:
        c1_error = (-412, '链 1 冷却中')

    if _cooldown_left('live', 2) <= 0:
        payload, error = live_room_info(uid, room_id=room_id, quiet=True)
        if error is None and isinstance(payload, dict):
            _clear_fault('live', 2)
            note = f'链 1 异常（code={c1_error[0]}），已切链 2' if c1_error else '已切链 2'
            _update_channel('live', uid, overall='degraded', active_chain=2, note=note)
            return payload, None
        c2_error = error
        if error and error[0] in _FALLBACK_CODES:
            _set_cooldown('live', 2)
            _mark_fault('live', 2, error[0])
    else:
        c2_error = (-412, '链 2 冷却中')

    final_error = c1_error if (c1_error and c1_error[0] in _FALLBACK_CODES) else (c2_error or c1_error or _NETWORK)
    _update_channel('live', uid, overall='failed', active_chain=0, note=f'全链失败（code={final_error[0]}）')
    return None, final_error


_FEED_TTL = 5.0
_FEED_LOCK = Lock()
_feed_cache = {
    'all': {'at': 0.0, 'items': None},
    'video': {'at': 0.0, 'items': None},
}


def feed_all_cached(feed_type='all', max_age=_FEED_TTL, *, bypass_cache=False, quiet=False):
    """关注流短缓存：同一轮里多个主播共用一次请求（按类型独立缓存，持锁拉取避免并发重复）。"""
    bucket = 'video' if feed_type == 'video' else 'all'
    with _FEED_LOCK:
        entry = _feed_cache[bucket]
        if not bypass_cache and entry['items'] is not None and time.time() - entry['at'] < max_age:
            return entry['items'], None
        items, error = feed_all(page=1, feed_type=bucket, quiet=quiet)
        if items is not None:
            entry.update(at=time.time(), items=items)
        return items, error


def _feed_video_item(item):
    modules = item.get('modules') if isinstance(item.get('modules'), dict) else {}
    author = modules.get('module_author') if isinstance(modules.get('module_author'), dict) else {}
    dynamic = modules.get('module_dynamic') if isinstance(modules.get('module_dynamic'), dict) else {}
    major = dynamic.get('major') if isinstance(dynamic.get('major'), dict) else {}
    archive = major.get('archive') if isinstance(major.get('archive'), dict) else {}
    bvid = str(archive.get('bvid') or '').strip()
    if not bvid:
        return None
    return {
        'bvid': bvid,
        'title': _strip_markup(archive.get('title')),
        'pic': _https(archive.get('cover')),
        'created': _int_field(author.get('pub_ts')),
        'author': _strip_markup(author.get('name')),
    }


def _follow_feed_for_uid(uid, kind, *, bypass_cache=False, quiet=True):
    """动态/视频链 1：关注流。未登录直接默认失败；返回 (items, error, is_api_error)。"""
    if not logged_in():
        return None, _NO_LOGIN, False
    feed_type = 'video' if kind == 'video' else 'all'
    items, error = feed_all_cached(feed_type=feed_type, bypass_cache=bypass_cache, quiet=quiet)
    if error:
        return None, error, True
    target = str(uid)
    if kind == 'dynamic':
        # 剔除视频投稿动态，与 notify._entry_parts 口径一致，避免仅发视频时误判动态链 1 命中。
        mine = [
            item for item in items
            if isinstance(item, dict) and _item_uid(item) == target and item.get('type') != 'DYNAMIC_TYPE_AV'
        ]
        if mine:
            return mine, None, False
        return None, (0, '关注流最新一页未命中该 UID（未关注或近期无非视频动态）'), False
    av_items = [
        item for item in items
        if isinstance(item, dict) and _item_uid(item) == target and item.get('type') == 'DYNAMIC_TYPE_AV'
    ]
    converted = [entry for item in av_items if (entry := _feed_video_item(item)) is not None]
    converted.sort(key=lambda item: _int_field(item.get('created')), reverse=True)
    if converted:
        return converted, None, False
    return None, (0, '关注流视频页最新一页未命中该 UID（未关注或近期无投稿）'), False


def _space_dynamics(uid, *, quiet=True):
    data, error = request_json(
        _DYNAMIC, params={'host_mid': str(uid), 'offset': '', 'features': 'itemOpusStyle'}, quiet=quiet,
    )
    if isinstance(data, dict):
        # 空主页会省略 items；非列表则是接口结构异常，不当作空结果。
        items = data.get('items')
        if items is None:
            items = []
        if isinstance(items, list):
            return items, None
    return _shape(_DYNAMIC, None, error, list, quiet=quiet)


def dynamics(uid):
    """动态三级级联通道：链 1 关注流（仅登录）→ 链 2 空间动态流 → 链 3 Opus 动态流。"""
    uid = str(uid)
    c1_note = ''
    c1_err = None
    if _cooldown_left('dynamic', 1) <= 0:
        items, err, api_err = _follow_feed_for_uid(uid, 'dynamic', quiet=True)
        if items is not None:
            _clear_fault('dynamic', 1)
            _update_channel('dynamic', uid, overall='ok', active_chain=1)
            return items, None
        c1_err = err
        if api_err and err:
            if err[0] in _FOLLOW_COOLDOWN_CODES:
                _set_cooldown('dynamic', 1)
                _mark_fault('dynamic', 1, err[0], fallback_to=2)
            c1_note = f'链 1 失败（code={err[0]}）'
        elif not logged_in():
            c1_note = '未登录跳过关注流'
        else:
            _clear_fault('dynamic', 1)
            c1_note = '关注流未命中该 UID'
    else:
        c1_err = (-412, '链 1 冷却中')
        c1_note = '链 1 冷却中'

    c2_err = None
    if _cooldown_left('dynamic', 2) <= 0:
        items, err = _space_dynamics(uid, quiet=True)
        if err is None:
            _clear_fault('dynamic', 2)
            _update_channel('dynamic', uid, overall='degraded', active_chain=2, note=c1_note)
            return items, None
        c2_err = err
        if err[0] in _FALLBACK_CODES:
            _set_cooldown('dynamic', 2)
            _mark_fault('dynamic', 2, err[0], fallback_to=3)
    else:
        c2_err = (-412, '链 2 冷却中')

    items, c3_err = _opus_dynamics(uid, quiet=True)
    if c3_err is None:
        _clear_fault('dynamic', 3)
        note = '链 2 冷却中（-412）' if _cooldown_left('dynamic', 2) > 0 else (c1_note or '已切链 3')
        _update_channel('dynamic', uid, overall='degraded', active_chain=3, note=note)
        return items, None

    _mark_fault('dynamic', 3, c3_err[0])
    final_code = -412 if any(e and e[0] == -412 for e in (c1_err, c2_err, c3_err)) else c3_err[0]
    detail = f'动态三条通道均失败（链1={c1_err[0] if c1_err else 0}/链2={c2_err[0] if c2_err else 0}/链3={c3_err[0]}）'
    _update_channel('dynamic', uid, overall='failed', active_chain=0, note=detail)
    return None, (final_code, detail)


def logged_in():
    """是否具备可用的登录态（关注、关注流、个人接口都需要）。"""
    try:
        cookie = store.global_config()['cookie']
    except store.StorageError:
        return False
    return bool(_cookie_value(cookie.get('sessdata')) and _cookie_value(cookie.get('bili_jct')))


def follow_user(uid):
    """关注目标 UP（act=1）。会修改登录账号的关注列表，只在开启「自动关注」时调用。"""
    try:
        settings = store.global_config()
    except store.StorageError:
        return False, _LOCAL
    csrf = str(settings['cookie'].get('bili_jct') or '').strip()
    if not csrf:
        return False, (-1, '自动关注需要 bili_jct，请先扫码登录或填写 Cookie')
    headers = _request_headers(settings, settings['buvid_cache'])
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    headers['Referer'] = f'https://space.bilibili.com/{uid}'
    proxy = settings['proxy']
    proxies = {'https': proxy} if proxy else {}
    try:
        with requests.Session() as client:
            client.trust_env = False
            # act: 1 = 关注，2 = 取消关注，5 = 拉黑，6 = 取消拉黑。
            with client.post(_RELATION, data={'fid': str(uid), 'act': 1, 're_src': 11, 'csrf': csrf},
                             headers=headers, proxies=proxies, timeout=_request_timeout(settings),
                             allow_redirects=False) as response:
                payload = response.json() if response.content else {}
    except (requests.RequestException, ValueError):
        return False, _NETWORK
    if not isinstance(payload, dict):
        return False, _FORMAT
    code = payload.get('code')
    if code == 0:
        return True, None
    return False, (int(code) if isinstance(code, int) else -1, str(payload.get('message') or '关注失败'))


def feed_all(page=1, feed_type='all', *, quiet=False):
    """关注流：一次性返回所有已关注 UP 的最新动态或视频投稿（需要登录且已关注）。"""
    params = {
        'type': 'video' if feed_type == 'video' else 'all',
        'features': 'itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote,decorationCard,onlyfansAssetsV2,'
                    'forwardListHidden,ugcDelete,onlyfansQaCard,commentsNewVersion',
        'page': page,
    }
    data, error = request_json(_FEED_ALL, params=params, quiet=quiet)
    if error:
        return None, error
    items = data.get('items') if isinstance(data, dict) else None
    if not isinstance(items, list):
        return (None, _FORMAT) if quiet else _failure(_FEED_ALL, _FORMAT)
    return items, None


def _item_uid(item):
    modules = item.get('modules') if isinstance(item, dict) else None
    author = (modules or {}).get('module_author') or {}
    return str(author.get('mid') or author.get('uid') or '')


_OPUS_PAGE = 'https://www.bilibili.com/opus/{opus_id}'
_PUB_TIME = re.compile(r'pub_time\\?":\\?"([^"\\]{1,40})')


def opus_pub_time(opus_id):
    """opus 流不带发布时间，从 opus 页面补（只在真要推送时调用一次）。"""
    if not re.fullmatch(r'[0-9]{1,25}', str(opus_id)):
        return ''
    headers = {
        'User-Agent': BASE_HEADERS['User-Agent'],
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    try:
        with requests.Session() as client:
            client.trust_env = False
            with client.get(_OPUS_PAGE.format(opus_id=opus_id), headers=headers,
                            timeout=config.IMAGE_TIMEOUT, allow_redirects=False) as response:
                if response.status_code != 200:
                    return ''
                text = response.text
    except requests.RequestException:
        return ''
    match = _PUB_TIME.search(text)
    if not match:
        return ''
    # 「2026年11月26日 09:14」→「2026-11-26 09:14」，与其它推送保持同一写法。
    return re.sub(r'年|月', '-', match.group(1)).replace('日', '').strip()


def _opus_dynamics(uid, *, quiet=False):
    """空间动态流被风控时改读 opus 流；条目拉平成与原接口同构的结构。

    opus 条目不返回发布时间，统一用 opus_id（与动态 id_str 同源、单调递增）排序。
    """
    data, error = request_json(_OPUS, params={'host_mid': str(uid), 'page': 1}, quiet=quiet)
    if error:
        return None, error
    items = data.get('items') if isinstance(data, dict) else None
    if not isinstance(items, list):
        return (None, _FORMAT) if quiet else _failure(_OPUS, _FORMAT)
    return [_opus_item(item) for item in items if isinstance(item, dict)], None


def _opus_item(item):
    opus_id = str(item.get('opus_id') or '')
    cover = item.get('cover') if isinstance(item.get('cover'), dict) else {}
    return {
        'id_str': opus_id,
        'type': 'DYNAMIC_TYPE_OPUS',
        'modules': {
            'module_tag': {},
            'module_author': {'pub_ts': 0, 'name': ''},
            'module_dynamic': {
                'desc': {'text': str(item.get('content') or '')},
                'major': {'draw': {'items': [{'src': str(cover.get('url') or '')}]}},
            },
        },
    }


def navnum(uid, *, quiet=False):
    data, error = request_json(_NAVNUM, params={'mid': str(uid)}, quiet=quiet)
    return _shape(_NAVNUM, data, error, dict, quiet=quiet)


def master_info(uid, *, quiet=False):
    data, error = request_json(_MASTER, params={'uid': str(uid)}, quiet=quiet)
    return _shape(_MASTER, data, error, dict, quiet=quiet)


def resolve_up(uid):
    uid = str(uid)
    data, _ = live_status((uid,))
    live = data.get(uid) if data else None
    if isinstance(live, dict) and live:
        return live
    data, _ = master_info(uid)
    if not data:
        return None
    info = data.get('info')
    info = info if isinstance(info, dict) else {}
    if not info and not data.get('room_id'):
        return None
    return {'uid': uid, 'room_id': data.get('room_id'), 'uname': info.get('uname', ''), 'live_status': 0}


def _wbi_key(*, quiet=False):
    global _wbi_cache
    with _wbi_lock:
        key, fetched_at = _wbi_cache
        if key and time.monotonic() - fetched_at < _WBI_TTL:
            return key, None
        # 未登录时 nav 可能返回 -101，但 data.wbi_img 仍然有效。
        data, error = request_json(_NAV, allowed_codes=(-101,), quiet=quiet)
        if error:
            return None, error
        images = data.get('wbi_img') if isinstance(data, dict) else None
        if not isinstance(images, dict):
            return (None, _FORMAT) if quiet else _failure(_NAV, _FORMAT)
        try:
            original = ''.join(Path(urlsplit(images[name]).path).stem for name in ('img_url', 'sub_url'))
        except (KeyError, TypeError, ValueError):
            return (None, _FORMAT) if quiet else _failure(_NAV, _FORMAT)
        if len(original) <= max(_WBI_INDICES):
            return (None, _FORMAT) if quiet else _failure(_NAV, _FORMAT)
        key = ''.join(original[index] for index in _WBI_INDICES)
        _wbi_cache = (key, time.monotonic())
        return key, None


def _signed_query(params, key):
    params = {**params, 'wts': int(time.time())}
    pairs = []
    for name, value in sorted(params.items()):
        filtered = re.sub(r"[!'()*]", '', str(value))
        pairs.append(f'{quote(name, safe="")}={quote(filtered, safe="")}')
    query = '&'.join(pairs)
    signature = hashlib.md5(f'{query}{key}'.encode(), usedforsecurity=False).hexdigest()
    return f'{query}&w_rid={signature}'


def _space_videos(uid, *, quiet=True):
    key, error = _wbi_key(quiet=quiet)
    if error:
        return None, error
    data, error = request_json(
        _VIDEO, params=_signed_query({'mid': str(uid), 'ps': 5, 'pn': 1, 'order': 'pubdate'}, key), quiet=quiet,
    )
    listing = data.get('list') if isinstance(data, dict) else None
    items = listing.get('vlist') if isinstance(listing, dict) else None
    if error is None and isinstance(items, list):
        return items, None
    return _shape(_VIDEO, None, error, list, quiet=quiet)


def videos(uid):
    """视频三级级联通道：链 1 关注流（仅登录）→ 链 2 空间投稿 WBI → 链 3 WBI 搜索兜底。"""
    uid = str(uid)
    c1_note = ''
    c1_err = None
    if _cooldown_left('video', 1) <= 0:
        items, err, api_err = _follow_feed_for_uid(uid, 'video', quiet=True)
        if items is not None:
            _clear_fault('video', 1)
            _update_channel('video', uid, overall='ok', active_chain=1)
            return items, None
        c1_err = err
        if api_err and err:
            if err[0] in _FOLLOW_COOLDOWN_CODES:
                _set_cooldown('video', 1)
                _mark_fault('video', 1, err[0], fallback_to=2)
            c1_note = f'链 1 失败（code={err[0]}）'
        elif not logged_in():
            c1_note = '未登录跳过关注流'
        else:
            _clear_fault('video', 1)
            c1_note = '关注流未命中该 UID'
    else:
        c1_err = (-412, '链 1 冷却中')
        c1_note = '链 1 冷却中'

    c2_err = None
    if _cooldown_left('video', 2) <= 0:
        items, err = _space_videos(uid, quiet=True)
        if err is None:
            _clear_fault('video', 2)
            _update_channel('video', uid, overall='degraded', active_chain=2, note=c1_note)
            return items, None
        c2_err = err
        if err[0] in _FALLBACK_CODES:
            _set_cooldown('video', 2)
            _mark_fault('video', 2, err[0], fallback_to=3)
    else:
        c2_err = (-412, '链 2 冷却中')

    items, c3_err = _search_videos(uid, quiet=True)
    if c3_err is None:
        _clear_fault('video', 3)
        note = '链 2 冷却中（-412）' if _cooldown_left('video', 2) > 0 else (c1_note or '已切链 3')
        _update_channel('video', uid, overall='degraded', active_chain=3, note=note)
        return items, None

    _mark_fault('video', 3, c3_err[0])
    final_code = -412 if any(e and e[0] == -412 for e in (c1_err, c2_err, c3_err)) else c3_err[0]
    detail = f'视频三条通道均失败（链1={c1_err[0] if c1_err else 0}/链2={c2_err[0] if c2_err else 0}/链3={c3_err[0]}）'
    _update_channel('video', uid, overall='failed', active_chain=0, note=detail)
    return None, (final_code, detail)


def _up_name(uid, *, quiet=False):
    """取昵称用于搜索兜底；只放进程内缓存，不写入配置（昵称会变）。"""
    with _name_lock:
        cached = _name_cache.get(str(uid))
        if cached and time.monotonic() - cached[1] < _NAME_TTL:
            return cached[0]
    data, error = request_json(_CARD, params={'mid': str(uid)}, quiet=quiet)
    name = ''
    if error is None and isinstance(data, dict):
        card = data.get('card') if isinstance(data.get('card'), dict) else {}
        name = str(card.get('name') or '').strip()
    if name:
        with _name_lock:
            _name_cache[str(uid)] = (name, time.monotonic())
    return name


def _search_videos(uid, *, quiet=False):
    """空间投稿接口被风控时：UID→昵称→按发布时间搜索→用 mid 精确过滤。"""
    name = _up_name(uid, quiet=quiet)
    if not name:
        return None, (-1, '取不到该 UID 的昵称，无法用搜索兜底')
    key, error = _wbi_key(quiet=quiet)
    if error:
        return None, error
    params = _signed_query({'search_type': 'video', 'keyword': name, 'order': 'pubdate', 'page': 1}, key)
    data, error = request_json(_SEARCH, params=params, quiet=quiet)
    if error:
        return None, error
    result = data.get('result') if isinstance(data, dict) else None
    if not isinstance(result, list):
        return (None, _FORMAT) if quiet else _failure(_SEARCH, _FORMAT)
    hits = [item for item in result if isinstance(item, dict) and str(item.get('mid')) == str(uid)]
    hits.sort(key=lambda item: _int_field(item.get('pubdate')), reverse=True)
    return [{
        'bvid': str(item.get('bvid') or ''),
        'title': _strip_markup(item.get('title')),
        'pic': _https(str(item.get('pic') or '')),
        'created': _int_field(item.get('pubdate')),
        'author': _strip_markup(item.get('author')),
    } for item in hits], None


def _int_field(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _strip_markup(value):
    return re.sub(r'<[^>]*>', '', str(value or '')).replace('&quot;', '"').strip()


def _https(url):
    url = str(url or '').strip()
    return 'https:' + url if url.startswith('//') else url


def follow_max_ids():
    """关注流里每个 UID 的最新动态 id（只做「有没有新动态」的触发器）。

    `dynamic_svr/.../dynamic_new` 返回的是「当前登录账号关注的人」的动态，
    所以只有在配置了登录态且该账号关注了目标 UP 时才请求。
    """
    if not logged_in():
        return None, _NO_LOGIN
    data, error = request_json(_DYNAMIC_NEW, params={'type_list': 268435455}, quiet=True)
    if error:
        return None, error
    cards = data.get('cards') if isinstance(data, dict) else None
    if not isinstance(cards, list):
        return None, _FORMAT
    result = {}
    for card in cards:
        desc = card.get('desc') if isinstance(card, dict) else None
        if not isinstance(desc, dict):
            continue
        uid = str(desc.get('uid') or '')
        dynamic_id = _int_field(desc.get('dynamic_id'))
        if uid and dynamic_id:
            result[uid] = max(result.get(uid, 0), dynamic_id)
    return result, None


def danmu_info(room_id, *, quiet=False):
    """取直播间弹幕服务器信息（WebSocket 认证要用的 token 与 host 列表）。

    `getDanmuInfo` 不带 wbi 签名会返回 -352（实测 2026-11-25），签名后 code=0。
    """
    key, error = _wbi_key(quiet=quiet)
    if error:
        return None, error
    params = _signed_query({'id': str(room_id), 'type': 0, 'web_location': '444.8'}, key)
    data, error = request_json(_DANMU, params=params, quiet=quiet)
    return _shape(_DANMU, data, error, dict, quiet=quiet)


def qr_generate():
    """申请扫码登录二维码，返回 {url, qrcode_key}。"""
    data, error = request_json(_QR_GENERATE)
    return _shape(_QR_GENERATE, data, error, dict)


def qr_poll(qrcode_key):
    """轮询扫码状态；成功时 data['url'] 里带着 SESSDATA / bili_jct / DedeUserID。"""
    data, error = request_json(_QR_POLL, params={'qrcode_key': str(qrcode_key)})
    return _shape(_QR_POLL, data, error, dict)


def parse_login_cookie(callback_url):
    """从扫码成功的回跳地址里取出登录 Cookie。"""
    try:
        query = urlsplit(callback_url).query
    except (TypeError, ValueError):
        return {}
    fields = dict(parse_qsl(query, keep_blank_values=True))
    pairs = {}
    # 回跳地址里的 SESSDATA 是 URL 编码过的，DedeUserID 用来核对身份。
    if fields.get('SESSDATA'):
        pairs['sessdata'] = fields['SESSDATA']
    if fields.get('bili_jct'):
        pairs['bili_jct'] = fields['bili_jct']
    if fields.get('DedeUserID'):
        pairs['dede_user_id'] = fields['DedeUserID']
    return pairs


def login_uid():
    """当前登录账号的 UID（WebSocket 认证要用；匿名时返回 0）。"""
    global _uid_cache
    value, fetched_at = _uid_cache
    if value and time.monotonic() - fetched_at < _NAME_TTL:
        return value
    data, error = request_json(_NAV)
    uid = 0
    if error is None and isinstance(data, dict):
        uid = _int_field(data.get('mid'))
    if uid:
        _uid_cache = (uid, time.monotonic())
    return uid


def buvid_text():
    """当前可用的 buvid3 值（配置里手填的优先，其次自动领取的缓存）。"""
    try:
        settings = store.global_config()
    except store.StorageError:
        return ''
    value = _cookie_value(settings['cookie'].get('buvid3'))
    if value:
        return value
    cache = settings.get('buvid_cache') or {}
    match = re.search(r'buvid3=([^;]+)', str(cache.get('cookie') or ''))
    return match.group(1).strip() if match else ''


def _probe_step(index, step_id, label, url, *, status, code, summary, elapsed_ms=0):
    return {
        'index': index,
        'id': step_id,
        'label': label,
        'path': urlsplit(url).path,
        'status': status,
        'code': code,
        'summary': summary,
        'elapsed_ms': elapsed_ms,
    }


def _safe_error_summary(error):
    code, text = error
    if code == -412:
        return 'B站风控（-412）'
    if code == -101:
        return text if text and '未登录' in text else '登录态失效（-101），请重新登录'
    if code == -352:
        return '触发风控校验（-352）'
    if code == -403:
        return '接口拒绝访问（-403）'
    return str(text or f'接口返回错误（{code}）')


def _run_probe_step(index, step_id, label, url, runner, *, skip=False, skip_reason='已跳过（前链已成功）'):
    if skip:
        step = _probe_step(
            index, step_id, label, url, status='skipped', code=None, summary=skip_reason, elapsed_ms=0,
        )
        return step, None
    started = time.monotonic()
    ok, code, summary, extra = runner()
    elapsed = int(round((time.monotonic() - started) * 1000))
    step = _probe_step(
        index, step_id, label, url,
        status='ok' if ok else 'fail',
        code=code,
        summary=summary,
        elapsed_ms=elapsed,
    )
    return step, extra


def probe_chain(kind, uid, *, mode='cascade', bypass_cooldown=True, room_id=''):
    """分链条级联自检：链 1 失败进链 2，链 2 失败进链 3；任一链成功即整体可用。"""
    uid = str(uid)
    full_mode = mode == 'full'
    is_logged = logged_in()
    steps = []

    if kind == 'nav':
        def run_nav():
            with _quiet_requests():
                data, error = navnum(uid)
            if error:
                return False, error[0], _safe_error_summary(error), None
            video_cnt = data.get('video')
            opus_cnt = data.get('opus')
            video_text = video_cnt if type(video_cnt) is int else '未知'
            opus_text = opus_cnt if type(opus_cnt) is int else '未知'
            return True, 0, f'投稿数：{video_text}；动态数：{opus_text}', None

        step, _ = _run_probe_step(1, 'space_navnum', '空间统计 navnum', _NAVNUM, run_nav)
        steps.append(step)
    elif kind == 'dynamic':
        def run_d1():
            if not is_logged:
                return False, _NO_LOGIN[0], '未登录账号，跳过关注流', None
            if not bypass_cooldown and (left := _cooldown_left('dynamic', 1)) > 0:
                return False, -412, f'冷却中（剩余 {left}s）', None
            items, err, api_err = _follow_feed_for_uid(uid, 'dynamic', bypass_cache=True, quiet=True)
            if items is not None:
                _clear_cooldown('dynamic', 1)
                _clear_fault('dynamic', 1)
                return True, 0, f'返回 {len(items)} 条非视频动态', None
            if api_err and err:
                return False, err[0], _safe_error_summary(err), None
            _clear_cooldown('dynamic', 1)
            _clear_fault('dynamic', 1)
            return False, 0, err[1] if err else '关注流最新一页未命中该 UID', None

        def run_d2():
            if not bypass_cooldown and (left := _cooldown_left('dynamic', 2)) > 0:
                return False, -412, f'冷却中（剩余 {left}s）', None
            items, err = _space_dynamics(uid, quiet=True)
            if err is None:
                _clear_cooldown('dynamic', 2)
                _clear_fault('dynamic', 2)
                return True, 0, f'返回 {len(items)} 条动态', None
            return False, err[0], _safe_error_summary(err), None

        def run_d3():
            items, err = _opus_dynamics(uid, quiet=True)
            if err is None:
                _clear_fault('dynamic', 3)
                return True, 0, f'返回 {len(items)} 条动态', None
            return False, err[0], _safe_error_summary(err), None

        s1, _ = _run_probe_step(1, 'follow_feed', '关注流（全部动态）', _FEED_ALL, run_d1)
        steps.append(s1)
        s2, _ = _run_probe_step(
            2, 'space_dynamic', '空间动态流', _DYNAMIC, run_d2,
            skip=not full_mode and s1['status'] == 'ok',
        )
        steps.append(s2)
        s3, _ = _run_probe_step(
            3, 'opus_feed', 'Opus 动态流', _OPUS, run_d3,
            skip=not full_mode and any(step['status'] == 'ok' for step in steps),
        )
        steps.append(s3)
    elif kind == 'video':
        def run_v1():
            if not is_logged:
                return False, _NO_LOGIN[0], '未登录账号，跳过关注流', None
            if not bypass_cooldown and (left := _cooldown_left('video', 1)) > 0:
                return False, -412, f'冷却中（剩余 {left}s）', None
            items, err, api_err = _follow_feed_for_uid(uid, 'video', bypass_cache=True, quiet=True)
            if items is not None:
                _clear_cooldown('video', 1)
                _clear_fault('video', 1)
                return True, 0, f'返回 {len(items)} 条视频投稿', None
            if api_err and err:
                return False, err[0], _safe_error_summary(err), None
            _clear_cooldown('video', 1)
            _clear_fault('video', 1)
            return False, 0, err[1] if err else '关注流视频页最新一页未命中该 UID', None

        def run_v2():
            if not bypass_cooldown and (left := _cooldown_left('video', 2)) > 0:
                return False, -412, f'冷却中（剩余 {left}s）', None
            items, err = _space_videos(uid, quiet=True)
            if err is None:
                _clear_cooldown('video', 2)
                _clear_fault('video', 2)
                return True, 0, f'返回 {len(items)} 条视频', None
            return False, err[0], _safe_error_summary(err), None

        def run_v3():
            items, err = _search_videos(uid, quiet=True)
            if err is None:
                _clear_fault('video', 3)
                return True, 0, f'返回 {len(items)} 条视频', None
            return False, err[0], _safe_error_summary(err), None

        s1, _ = _run_probe_step(1, 'follow_video', '关注流（视频投稿）', _FEED_ALL, run_v1)
        steps.append(s1)
        s2, _ = _run_probe_step(
            2, 'space_video', '空间投稿 WBI', _VIDEO, run_v2,
            skip=not full_mode and s1['status'] == 'ok',
        )
        steps.append(s2)
        s3, _ = _run_probe_step(
            3, 'wbi_search', 'WBI 搜索兜底', _SEARCH, run_v3,
            skip=not full_mode and any(step['status'] == 'ok' for step in steps),
        )
        steps.append(s3)
    elif kind == 'live':
        resolved_room = str(room_id or '').strip()
        if resolved_room == '0':
            resolved_room = ''

        def ensure_room():
            nonlocal resolved_room
            if resolved_room:
                return resolved_room, None
            with _quiet_requests():
                master, err = master_info(uid)
            if err:
                return '', err
            value = str((master or {}).get('room_id') or '').strip()
            resolved_room = '' if value == '0' else value
            return resolved_room, None

        def run_l1():
            nonlocal resolved_room
            if not bypass_cooldown and (left := _cooldown_left('live', 1)) > 0:
                return False, -412, f'冷却中（剩余 {left}s）', None
            with _quiet_requests():
                data, err = live_status((uid,))
            if err:
                return False, err[0], _safe_error_summary(err), None
            payload = data.get(uid) if isinstance(data, dict) else None
            if not isinstance(payload, dict) or 'live_status' not in payload:
                return False, -1, '批量接口未返回该 UID 的直播间状态', None
            if not resolved_room and payload.get('room_id'):
                resolved_room = str(payload['room_id'])
            _clear_cooldown('live', 1)
            _clear_fault('live', 1)
            live_flag = '直播中' if _int_field(payload.get('live_status')) == 1 else '未开播'
            return True, 0, f'返回状态：{live_flag}', None

        def run_l2():
            if not bypass_cooldown and (left := _cooldown_left('live', 2)) > 0:
                return False, -412, f'冷却中（剩余 {left}s）', None
            rid, err = ensure_room()
            if err:
                return False, err[0], _safe_error_summary(err), None
            if not rid:
                return False, -1, '该 UID 无直播间', None
            payload, err = live_room_info(uid, room_id=rid, quiet=True)
            if err:
                return False, err[0], _safe_error_summary(err), None
            _clear_cooldown('live', 2)
            _clear_fault('live', 2)
            live_flag = '直播中' if _int_field(payload.get('live_status')) == 1 else '未开播'
            return True, 0, f'房间 {rid} · {live_flag}', None

        def run_l3():
            rid, err = ensure_room()
            if err:
                return False, err[0], _safe_error_summary(err), None
            if not rid:
                return False, -1, '该 UID 无直播间，无法检测弹幕鉴权', None
            data, err = danmu_info(rid, quiet=True)
            if err:
                return False, err[0], _safe_error_summary(err), None
            hosts = data.get('host_list') if isinstance(data, dict) else None
            if not isinstance(hosts, list) or not hosts or not data.get('token'):
                return False, _FORMAT[0], '弹幕鉴权响应缺少节点或令牌', None
            return True, 0, f'长连接鉴权通过（房间 {rid}，{len(hosts)} 个节点）', None

        s1, _ = _run_probe_step(1, 'live_batch', '批量直播状态', _LIVE, run_l1)
        steps.append(s1)
        s2, _ = _run_probe_step(
            2, 'live_room', '单间直播信息', _LIVE_ROOM_INFO, run_l2,
            skip=not full_mode and s1['status'] == 'ok',
        )
        steps.append(s2)
        s3, _ = _run_probe_step(
            3, 'live_danmu', '弹幕长连接鉴权', _DANMU, run_l3,
            skip=not full_mode and any(step['status'] == 'ok' for step in steps),
        )
        steps.append(s3)
    else:
        return {
            'kind': kind, 'uid': uid, 'mode': mode, 'overall': 'failed', 'success': False,
            'active_chain': 0, 'active_label': '', 'code': -4, 'summary': '未知的诊断接口',
            'checked_at': int(time.time()), 'logged_in': is_logged, 'steps': [],
        }

    first_ok = next((step for step in steps if step['status'] == 'ok'), None)
    checked_at = int(time.time())
    if first_ok is not None:
        active_chain = first_ok['index']
        active_label = first_ok['label']
        overall = 'ok' if active_chain == 1 else 'degraded'
        if kind == 'nav':
            summary = first_ok['summary']
        elif active_chain == 1:
            summary = f'主链正常（链 1 · {active_label}，{first_ok["summary"]}）'
        elif kind in ('dynamic', 'video') and not is_logged:
            summary = f'可用（链 {active_chain} · {active_label} · 未登录跳过关注流，{first_ok["summary"]}）'
        else:
            summary = f'降级可用（命中链 {active_chain} · {active_label}，{first_ok["summary"]}）'
        if kind in config.KINDS:
            note = '未登录跳过关注流' if (kind in ('dynamic', 'video') and not is_logged and active_chain > 1) else ''
            _update_channel(kind, uid, overall=overall, active_chain=active_chain, note=note)
        return {
            'kind': kind, 'uid': uid, 'mode': 'full' if full_mode else 'cascade',
            'overall': overall, 'success': True, 'active_chain': active_chain, 'active_label': active_label,
            'code': 0, 'summary': summary, 'checked_at': checked_at, 'logged_in': is_logged,
            'steps': steps, 'channels': channel_health(),
        }

    failed_steps = [step for step in steps if step['status'] == 'fail']
    codes = [step['code'] for step in failed_steps if isinstance(step['code'], int)]
    final_code = -412 if -412 in codes else (next((c for c in reversed(codes) if c != 0), -1))
    brief = ' / '.join(f'链{step["index"]}={step["code"]}' for step in failed_steps)
    summary = f'全链失败（{brief}）' if len(steps) > 1 else (failed_steps[0]['summary'] if failed_steps else '自检失败')
    if kind in config.KINDS:
        _update_channel(kind, uid, overall='failed', active_chain=0, note=summary)
    return {
        'kind': kind, 'uid': uid, 'mode': 'full' if full_mode else 'cascade',
        'overall': 'failed', 'success': False, 'active_chain': 0, 'active_label': '',
        'code': final_code, 'summary': summary, 'checked_at': checked_at, 'logged_in': is_logged,
        'steps': steps, 'channels': channel_health(),
    }


def probe(kind, uid, *, mode='cascade', bypass_cooldown=True, room_id=''):
    return probe_chain(kind, uid, mode=mode, bypass_cooldown=bypass_cooldown, room_id=room_id)


def _image_host_allowed(url):
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url) or '\\' in url:
        return False
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname or ''
        return (
            parsed.scheme in ('http', 'https') and parsed.username is None and parsed.password is None
            and parsed.port in (None, 80 if parsed.scheme == 'http' else 443)
            and any(hostname == domain or hostname.endswith('.' + domain) for domain in _IMAGE_DOMAINS)
        )
    except ValueError:
        return False


def _remove_file(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        store.log(None, '无法清理 B站封面临时文件', level=3)


def _download_cover(client, url, digest):
    temporary = None
    try:
        with client.get(url, headers={'Accept': 'image/*', 'Accept-Encoding': 'identity'}, stream=True,
                        timeout=config.IMAGE_TIMEOUT, allow_redirects=False) as response:
            if response.status_code != 200:
                return None
            content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if not content_type.startswith('image/') or not (subtype := content_type.removeprefix('image/')):
                return None
            extension = _IMAGE_EXTENSIONS.get(subtype, subtype)
            if not re.fullmatch(r'[a-z0-9]{1,10}', extension):
                return None
            if int(response.headers.get('Content-Length') or 0) > _MAX_IMAGE:
                return None
            config.IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=config.IMAGE_ROOT, suffix='.part', delete=False) as handle:
                temporary = Path(handle.name)
                size = 0
                for chunk in response.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > _MAX_IMAGE:
                        return None
                    handle.write(chunk)
            if not size:
                return None
            path = config.IMAGE_ROOT / f'{digest}.{extension}'
            with _image_lock:
                # 每个下载先写独立临时文件；已交付的同名封面绝不在发送期间被覆盖。
                if path not in _image_leases:
                    temporary.replace(path)
                    temporary = None
                _image_leases[path] = _image_leases.get(path, 0) + 1
                return path
    finally:
        if temporary is not None:
            _remove_file(temporary)


def download_image(url):
    """获取一次封面使用权；每次成功返回都必须成对调用 release_image。"""
    if not _image_host_allowed(url):
        return None
    digest = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()
    # 图片完全独立：不继承账户 Cookie、代理（包括环境代理）、认证或重定向。
    for attempt in range(3):
        try:
            with requests.Session() as client:
                client.trust_env = False
                path = _download_cover(client, url, digest)
            if path is not None:
                return path
        except (requests.RequestException, OSError, ValueError, UnicodeError):
            pass  # 只记录最终结果，异常文本可能含外部 URL。
        if attempt < 2:
            time.sleep(1)
    store.log(None, 'B站封面下载失败', level=3)
    return None


def release_image(path):
    """最后一个发送者结束后才删除同名图片。"""
    with _image_lock:
        count = _image_leases.get(path, 0)
        if count > 1:
            _image_leases[path] = count - 1
        elif count:
            del _image_leases[path]
            _remove_file(path)
