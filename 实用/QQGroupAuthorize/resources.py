"""Proc 提供 AppID，名称与下载头像按 bot hash 保存，用户头像为最终图片兜底。"""

import hashlib
import json
import re
import secrets
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests

from . import config
from .config import ROOT

PALETTE = ('#2864b4', '#277c71', '#a65632', '#78539d', '#a04462', '#346b82')
AVATAR_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')
MAX_AVATAR_BYTES = 4 * 1024 * 1024
_avatar_cache = OrderedDict()
_avatar_lock = threading.Lock()

# /users/@me 结果按 bot 缓存：成功一小时，没拿到 avatar 时一分钟后再试。
SELF_PROFILE_TTL = 3600
SELF_PROFILE_RETRY_TTL = 60
_self_profile_cache = OrderedDict()
_self_profile_lock = threading.Lock()


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def prepare_resources():
    ROOT.mkdir(parents=True, exist_ok=True)
    return ROOT


@dataclass
class BotProfile:
    bot_hash: str
    name: str
    appid: str
    folder: Path
    avatar: bytes = b''
    avatar_mime: str = ''
    color: str = '#2864b4'
    browser_path: str = ''
    openid: str = ''


def normalize_avatar(data):
    from PIL import Image, ImageOps

    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 16_000_000:
            raise ValueError('Avatar dimensions exceeded')
        image = ImageOps.exif_transpose(source).convert('RGBA')
        image.thumbnail((256, 256))
        output = BytesIO()
        image.save(output, format='PNG')
    return output.getvalue()


def avatar_url(value):
    """接受 http/https 头像地址，统一升级成 https；其他值一律视为无效。"""
    text = str(value or '').strip()
    lower = text.lower()
    if lower.startswith('https://'):
        return text
    if lower.startswith('http://'):
        return 'https://' + text[len('http://'):]
    return ''


def download_avatar(url):
    """只访问头像地址本身，不携带账号密钥；成功缓存一小时，失败缓存一分钟。"""
    url = avatar_url(url)
    if not url:
        return b''
    with _avatar_lock:
        now = time.monotonic()
        cached = _avatar_cache.get(url)
        if cached and cached[0] > now:
            return cached[1]
        data = b''
        try:
            with requests.get(url, timeout=(3, 5), stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Unexpected avatar response')
                if int(response.headers.get('Content-Length', '0')) > MAX_AVATAR_BYTES:
                    raise ValueError('Avatar response exceeded')
                body = bytearray()
                deadline = now + 10
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body) > MAX_AVATAR_BYTES or time.monotonic() > deadline:
                        raise ValueError('Avatar download exceeded')
                data = normalize_avatar(bytes(body))
        except Exception:
            # 404、超时、无效图片均按同样顺序回退，不影响指引图。
            pass
        _avatar_cache[url] = (time.monotonic() + (3600 if data else 60), data)
        _avatar_cache.move_to_end(url)
        while len(_avatar_cache) > 64:
            _avatar_cache.popitem(last=False)
        return data


def qq_avatar(appid, openid):
    """旧接口兜底：用 AppID + OpenID 拼 qlogo 地址，缺 OpenID 时直接放弃。"""
    if not openid or not str(appid).isdecimal():
        return b''
    return download_avatar(
        f'https://q.qlogo.cn/qqapp/{quote(str(appid), safe="")}/{quote(str(openid), safe="")}/0'
    )


def _sdk_module():
    try:
        import OlivOS

        return getattr(OlivOS, 'qqGuildv2SDK', None)
    except Exception:
        return None


def sdk_self_profile(bot_hash):
    """OlivOS qqGuildv2 SDK 已缓存的 /users/@me 结果，命中时可省一次请求。"""
    cache = None
    common = sys.modules.get('OlivOS.adapter.qqGuild.qqGuildv2SDKCommon')
    if common is not None:
        cache = getattr(common, 'sdkSelfInfo', None)
    if not isinstance(cache, dict):
        cache = getattr(_sdk_module(), 'sdkSelfInfo', None)
    if not isinstance(cache, dict):
        return {}
    profile = cache.get(str(bot_hash))
    return dict(profile) if isinstance(profile, dict) else {}


def fetch_self_profile(bot_info):
    """GET /users/@me：机器人自身资料，avatar 就是可直接下载的头像地址。

    借 OlivOS qqGuildv2 SDK 自带的 API 对象发请求，插件不接触 access_token；
    没有可用令牌时直接返回空字典，不发无效请求。
    """
    access_token = str(
        getattr(getattr(bot_info, 'post_info', None), 'access_token', '') or ''
    ).strip()
    if not access_token:
        return {}
    sdk = _sdk_module()
    if sdk is None:
        return {}
    try:
        sdk_bot_info = sdk.get_SDK_bot_info_from_Plugin_bot_info(bot_info)
        api_object = sdk.API.getMe(sdk_bot_info)
        api_object.do_api('GET')
        if getattr(api_object, 'res_code', None) != 200 or not api_object.res:
            return {}
        payload = json.loads(api_object.res)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def self_profile(bot_info=None):
    """机器人自身资料：优先 GET /users/@me，其次 SDK 里缓存的同一份结果。"""
    key = str(getattr(bot_info, 'hash', '') or '')
    if key:
        with _self_profile_lock:
            cached = _self_profile_cache.get(key)
            if cached and cached[0] > time.monotonic():
                return dict(cached[1])
    profile = sdk_self_profile(key) if key else {}
    if not avatar_url(profile.get('avatar', '')):
        fetched = fetch_self_profile(bot_info)
        if fetched:
            profile = fetched
    profile = dict(profile) if isinstance(profile, dict) else {}
    if key:
        ttl = SELF_PROFILE_TTL if avatar_url(profile.get('avatar', '')) else SELF_PROFILE_RETRY_TTL
        with _self_profile_lock:
            _self_profile_cache[key] = (time.monotonic() + ttl, profile)
            while len(_self_profile_cache) > 32:
                _self_profile_cache.popitem(last=False)
    return dict(profile)


def self_avatar(bot_info, openid=''):
    """头像优先取 /users/@me 给出的地址，拿不到再退回旧的 AppID + OpenID。"""
    data = download_avatar(self_profile(bot_info).get('avatar', ''))
    if data:
        return data
    return qq_avatar(getattr(bot_info, 'id', ''), openid)


def avatar_basename(bot_hash):
    key = str(bot_hash)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,96}', key):
        key = hashlib.sha256(key.encode('utf-8')).hexdigest()
    return key


def cache_avatar(bot_hash, data):
    """只写当前 bot 的缓存文件，绝不覆盖根目录用户的 avatar。"""
    destination = ROOT / (avatar_basename(bot_hash) + '.png')
    temporary = None
    try:
        if destination.is_file() and destination.read_bytes() == data:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(destination)
    except OSError:
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def local_avatar(stem='avatar'):
    try:
        files = {path.name.lower(): path for path in ROOT.iterdir() if path.is_file()}
    except OSError:
        return b''
    for suffix in AVATAR_SUFFIXES:
        candidate = files.get(stem.lower() + suffix)
        if candidate is None:
            continue
        try:
            if candidate.stat().st_size <= MAX_AVATAR_BYTES:
                return normalize_avatar(candidate.read_bytes())
        except Exception:
            continue
    return b''


def theme_color(avatar, fallback):
    if not avatar:
        return fallback
    try:
        import colorsys
        from io import BytesIO

        from PIL import Image, ImageOps

        with Image.open(BytesIO(avatar)) as source:
            sample = ImageOps.exif_transpose(source).convert('RGBA')
            sample.thumbnail((80, 80))
            pixels = [rgb[:3] for rgb in sample.getdata() if rgb[3] > 180]
        buckets = {}
        for rgb in pixels:
            hue, light, saturation = colorsys.rgb_to_hls(*(part / 255 for part in rgb))
            # 排除近白背景与近黑文字，以有辨识度的色块为主色。
            if 0.15 < light < 0.9 and saturation > 0.18:
                key = tuple(part // 32 for part in rgb)
                buckets.setdefault(key, []).append((hue, light, saturation))
        if not buckets:
            # 纯灰头像也使用头像本身的色相，不换成随机彩色。
            if not pixels:
                return fallback
            gray = round(sum(pixels[len(pixels) // 2]) / 3)
            gray = min(110, max(70, gray))
            return f'#{gray:02x}{gray:02x}{gray:02x}'
        samples = max(buckets.values(), key=len)
        hue, light, saturation = samples[len(samples) // 2]
        rgb = colorsys.hls_to_rgb(hue, min(0.43, max(0.31, light)), min(0.7, max(0.35, saturation)))
        return '#' + ''.join(f'{round(part * 255):02x}' for part in rgb)
    except Exception:
        return fallback


def bot_profile(event, proc):
    # 只按事件的 bot hash 匹配 Proc 已加载账号，不能拿 sub_self_id/OpenID 替代 AppID。
    bot = proc.Proc_data['bot_info_dict'].get(event.bot_info.hash)
    if bot is None or bot.platform.get('sdk') != 'qqGuildv2_link':
        raise ValueError('Bot not registered in Proc')
    appid = str(bot.id)
    try:
        prepare_resources()
    except OSError:
        pass
    options = config.load()
    name = None
    try:
        import OlivaDiceCore

        name = OlivaDiceCore.msgCustom.dictStrCustomDict.get(bot.hash, {}).get('strBotName')
    except Exception:
        pass
    if not isinstance(name, str) or not name.strip() or name == 'Bot':
        try:
            info = event.get_login_info()
            name = info.get('data', {}).get('name') if info.get('active') else None
        except Exception:
            name = None
    if isinstance(name, str) and name.strip() and name != 'Bot':
        name = name.strip()
        try:
            config.remember_name(bot.hash, name)
        except config.ConfigError:
            pass
    else:
        name = options['bots'].get(str(bot.hash), {}).get('name', '').strip() or f'QQ 机器人 {bot.id}'
    profile = BotProfile(str(bot.hash), name.strip()[:80], appid, ROOT)
    browser = options['browser_path']
    if isinstance(browser, str):
        profile.browser_path = browser
    openid = (getattr(event.data, 'extend', {}) or {}).get('sub_self_open_id')
    profile.openid = str(openid).strip() if openid is not None else ''
    profile.avatar = self_avatar(bot, profile.openid)
    if profile.avatar:
        cache_avatar(bot.hash, profile.avatar)
    else:
        profile.avatar = local_avatar(avatar_basename(bot.hash)) or local_avatar()
    if profile.avatar:
        profile.avatar_mime = 'image/png'
    saved = read_json(ROOT / 'theme.json').get('color')
    profile.color = saved if saved in PALETTE else secrets.choice(PALETTE)
    if saved not in PALETTE:
        try:
            ROOT.mkdir(parents=True, exist_ok=True)
            (ROOT / 'theme.json').write_text(json.dumps({'color': profile.color}), encoding='utf-8')
        except OSError:
            pass
    profile.color = theme_color(profile.avatar, profile.color)
    return profile
