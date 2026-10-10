"""Proc 提供 AppID，名称与下载头像按 bot hash 保存，用户头像为最终图片兜底。"""

import hashlib
import json
import re
import secrets
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


def qq_avatar(appid, openid):
    """仅访问用户指定的 QQ 头像域名，不携带账号密钥；成功缓存一小时，失败缓存一分钟。"""
    if not openid or not appid.isdecimal():
        return b''
    key = (appid, openid)
    with _avatar_lock:
        now = time.monotonic()
        cached = _avatar_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        data = b''
        try:
            url = f'https://q.qlogo.cn/qqapp/{quote(appid, safe="")}/{quote(openid, safe="")}/0'
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
        _avatar_cache[key] = (time.monotonic() + (3600 if data else 60), data)
        _avatar_cache.move_to_end(key)
        while len(_avatar_cache) > 64:
            _avatar_cache.popitem(last=False)
        return data


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
    profile.avatar = qq_avatar(appid, profile.openid)
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
