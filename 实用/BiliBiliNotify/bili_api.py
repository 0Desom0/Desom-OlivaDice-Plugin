import hashlib
import re
import tempfile
import time
from pathlib import Path
from threading import Lock
from urllib.parse import quote, urlsplit

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
_ENDPOINTS = frozenset((_SPI, _LIVE, _MASTER, _DYNAMIC, _NAVNUM, _NAV, _VIDEO, _OPUS,
                        _SEARCH, _CARD, _DANMU, _DYNAMIC_NEW))
# 只有风控类错误才换通道；网络失败与格式异常直接回报，避免把故障当成「没内容」。
_FALLBACK_CODES = (-412, -352, -403)
_RISK = (-412, 'B站风控，请在 WebUI 填写 Cookie 或检查网络出口')
_FORMAT = (-1, 'B站响应格式异常')
_LOCAL = (-2, '无法读取 B站请求配置')
_NETWORK = (-3, 'B站网络连接失败或超时')
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


def _fetch_json(url, *, params, settings, headers, timeout, retry, allowed_codes=()):
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
            time.sleep(1)
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


def _refresh_buvid(*, previous=None):
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
            return _failure(_SPI, error)
        values = [_cookie_value(data.get(key)) for key in ('b_3', 'b_4')] if isinstance(data, dict) else []
        if len(values) != 2 or not all(values):
            return _failure(_SPI, _FORMAT)
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
    headers['Cookie'] = '; '.join(f'{key}={value}' for key, value in values.items())
    return headers


def request_json(url, *, params=None, timeout=None, retry=1, force_buvid=False, allowed_codes=()):
    """固定 B站接口，返回解包后的 data 或安全错误。"""
    if url not in _ENDPOINTS:
        return None, (-4, '未配置的 B站接口')
    try:
        settings = store.global_config()
        cache = settings['buvid_cache']
        timeout = _request_timeout(settings) if timeout is None else timeout
        retry = min(1, max(0, retry))
        if url == _SPI:
            headers = _base_headers(settings)
        else:
            saved = settings['cookie']
            manual = _cookie_value(saved['buvid3']) and _cookie_value(saved['buvid4'])
            valid_cache = 0 <= time.time() - cache['fetched_at'] < _BUVID_TTL and len(_cache_values(cache)) == 2
            if force_buvid or (not manual and not valid_cache):
                fresh, _ = _refresh_buvid(previous=None if force_buvid else cache)
                if fresh:
                    cache = fresh
            headers = _request_headers(settings, cache)
        data, error, retries = _fetch_json(
            url, params=params, settings=settings, headers=headers, timeout=timeout, retry=retry,
            allowed_codes=allowed_codes,
        )
        if error == _RISK and url != _SPI:
            fresh, _ = _refresh_buvid(previous=cache)
            data, error, _ = _fetch_json(
                url, params=params, settings=settings, headers=_request_headers(settings, fresh or cache),
                timeout=timeout, retry=retries, allowed_codes=allowed_codes,
            )
    except store.StorageError:
        return _failure(url, _LOCAL)
    return _failure(url, error) if error else (data, None)


def _shape(url, data, error, expected):
    if error:
        return None, error
    if not isinstance(data, expected):
        return _failure(url, _FORMAT)
    return data, None


def live_status(uids):
    uids = list(dict.fromkeys(map(str, uids)))
    if not uids:
        return {}, None
    data, error = request_json(_LIVE, params=[('uids[]', uid) for uid in uids])
    return _shape(_LIVE, data, error, dict)


def dynamics(uid):
    data, error = request_json(_DYNAMIC, params={'host_mid': str(uid), 'offset': '', 'features': 'itemOpusStyle'})
    if isinstance(data, dict):
        # 空主页会省略 items；非列表则是接口结构异常，不当作空结果。
        items = data.get('items')
        if items is None:
            items = []
        if isinstance(items, list):
            return items, None
    if error is None or error[0] not in _FALLBACK_CODES:
        return _shape(_DYNAMIC, None, error, list)
    return _opus_dynamics(uid)


def _opus_dynamics(uid):
    """空间动态流被风控时改读 opus 流；条目拉平成与原接口同构的结构。

    opus 条目不返回发布时间，统一用 opus_id（与动态 id_str 同源、单调递增）排序。
    """
    data, error = request_json(_OPUS, params={'host_mid': str(uid), 'page': 1})
    if error:
        return None, error
    items = data.get('items') if isinstance(data, dict) else None
    if not isinstance(items, list):
        return _failure(_OPUS, _FORMAT)
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


def navnum(uid):
    data, error = request_json(_NAVNUM, params={'mid': str(uid)})
    return _shape(_NAVNUM, data, error, dict)


def master_info(uid):
    data, error = request_json(_MASTER, params={'uid': str(uid)})
    return _shape(_MASTER, data, error, dict)


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


def _wbi_key():
    global _wbi_cache
    with _wbi_lock:
        key, fetched_at = _wbi_cache
        if key and time.monotonic() - fetched_at < _WBI_TTL:
            return key, None
        # 未登录时 nav 可能返回 -101，但 data.wbi_img 仍然有效。
        data, error = request_json(_NAV, allowed_codes=(-101,))
        if error:
            return None, error
        images = data.get('wbi_img') if isinstance(data, dict) else None
        if not isinstance(images, dict):
            return _failure(_NAV, _FORMAT)
        try:
            original = ''.join(Path(urlsplit(images[name]).path).stem for name in ('img_url', 'sub_url'))
        except (KeyError, TypeError, ValueError):
            return _failure(_NAV, _FORMAT)
        if len(original) <= max(_WBI_INDICES):
            return _failure(_NAV, _FORMAT)
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


def videos(uid):
    key, error = _wbi_key()
    if error:
        return None, error
    data, error = request_json(_VIDEO, params=_signed_query({'mid': uid, 'ps': 5, 'pn': 1, 'order': 'pubdate'}, key))
    listing = data.get('list') if isinstance(data, dict) else None
    items = listing.get('vlist') if isinstance(listing, dict) else None
    if error is None and isinstance(items, list):
        return items, None
    if error is None or error[0] not in _FALLBACK_CODES:
        return _shape(_VIDEO, None, error, list)
    return _search_videos(uid)


def _up_name(uid):
    """取昵称用于搜索兜底；只放进程内缓存，不写入配置（昵称会变）。"""
    with _name_lock:
        cached = _name_cache.get(str(uid))
        if cached and time.monotonic() - cached[1] < _NAME_TTL:
            return cached[0]
    data, error = request_json(_CARD, params={'mid': str(uid)})
    name = ''
    if error is None and isinstance(data, dict):
        card = data.get('card') if isinstance(data.get('card'), dict) else {}
        name = str(card.get('name') or '').strip()
    if name:
        with _name_lock:
            _name_cache[str(uid)] = (name, time.monotonic())
    return name


def _search_videos(uid):
    """空间投稿接口被风控时：UID→昵称→按发布时间搜索→用 mid 精确过滤。"""
    name = _up_name(uid)
    if not name:
        return None, (-1, '空间接口被风控，且取不到该 UID 的昵称，无法用搜索兜底')
    key, error = _wbi_key()
    if error:
        return None, error
    params = _signed_query({'search_type': 'video', 'keyword': name, 'order': 'pubdate', 'page': 1}, key)
    data, error = request_json(_SEARCH, params=params)
    if error:
        return None, error
    result = data.get('result') if isinstance(data, dict) else None
    if not isinstance(result, list):
        return _failure(_SEARCH, _FORMAT)
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
    所以只有在配置了 SESSDATA 且该账号关注了目标 UP 时才有数据。
    """
    data, error = request_json(_DYNAMIC_NEW, params={'type_list': 268435455})
    if error:
        return None, error
    cards = data.get('cards') if isinstance(data, dict) else None
    if not isinstance(cards, list):
        return _failure(_DYNAMIC_NEW, _FORMAT)
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


def danmu_info(room_id):
    """取直播间弹幕服务器信息（WebSocket 认证要用的 token 与 host 列表）。

    `getDanmuInfo` 不带 wbi 签名会返回 -352（实测 2026-11-25），签名后 code=0。
    """
    key, error = _wbi_key()
    if error:
        return None, error
    params = _signed_query({'id': str(room_id), 'type': 0, 'web_location': '444.8'}, key)
    data, error = request_json(_DANMU, params=params)
    return _shape(_DANMU, data, error, dict)


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


def probe(kind, uid):
    fetch = {'live': lambda value: live_status((value,)), 'dynamic': dynamics, 'video': videos, 'nav': navnum}
    if kind not in fetch:
        return {'code': -4, 'summary': '未知的诊断接口'}
    data, error = fetch[kind](uid)
    if error:
        return {'code': error[0], 'summary': error[1]}
    if kind == 'nav':
        video, opus = data.get('video'), data.get('opus')
        video = video if type(video) is int else '未知'
        opus = opus if type(opus) is int else '未知'
        summary = f'投稿数：{video}；动态数：{opus}'
    elif kind == 'live':
        summary = f'返回 {len(data)} 个直播状态'
    else:
        summary = f'返回 {len(data)} 条记录'
    return {'code': 0, 'summary': summary}


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
