"""HTML 导入时驻留内存，浏览器截图保存无损 PNG。"""

import base64
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from . import config
from .resources import read_json

WIDTH = 1560
HEIGHT = 2130
SCALE = 1.5
IMAGE_SIZE = (round(WIDTH * SCALE), round(HEIGHT * SCALE))
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_render_lock = threading.Lock()

# OPK 解包目录在加载结束后会被清理，不能到第一次命令时才读取 __file__ 旁的资源。
try:
    TEMPLATE = (Path(__file__).parent / 'authorization.html').read_text(encoding='utf-8')
except (OSError, UnicodeError):
    TEMPLATE = ''


@dataclass
class ImageResult:
    data: bytes = b''
    path: Path | None = None
    warning: str = ''
    cached: bool = False


def font_stack(platform=None):
    platform = platform or sys.platform
    if platform == 'win32':
        return '"Microsoft YaHei", "Microsoft YaHei UI", "SimHei", sans-serif'
    if platform == 'darwin':
        return '"PingFang SC", "Heiti SC", "Hiragino Sans GB", sans-serif'
    return '"Noto Sans CJK SC", "WenQuanYi Micro Hei", "Droid Sans Fallback", sans-serif'


def page_html(profile):
    if not TEMPLATE:
        raise RuntimeError('HTML template unavailable')
    if profile.avatar:
        uri = f'data:{profile.avatar_mime};base64,' + base64.b64encode(profile.avatar).decode('ascii')
        avatar = f'<img class="avatar" src="{uri}" alt="机器人头像">'
    else:
        avatar = f'<span class="avatar placeholder">{html.escape(profile.name[0])}</span>'
    data = {
        '{{BOT_NAME}}': html.escape(profile.name),
        '{{APPID}}': html.escape(profile.appid),
        '{{AVATAR}}': avatar,
        '{{ACCENT}}': profile.color,
        '{{FONT_STACK}}': font_stack(),
    }
    # 一次替换，用户名称内形如 {{APPID}} 的文本也不得被二次解释。
    return re.sub(r'\{\{[A-Z_]+\}\}', lambda match: data.get(match[0], match[0]), TEMPLATE)


def find_browser(explicit=''):
    candidates = [explicit] if explicit else []
    if sys.platform == 'win32':
        for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            folder = os.environ.get(key)
            if folder:
                candidates.extend(
                    [
                        str(Path(folder) / 'Google/Chrome/Application/chrome.exe'),
                        str(Path(folder) / 'Microsoft/Edge/Application/msedge.exe'),
                        str(Path(folder) / 'Chromium/Application/chrome.exe'),
                    ]
                )
    elif sys.platform == 'darwin':
        for folder in (Path('/Applications'), Path.home() / 'Applications'):
            candidates.extend(
                str(folder / app / 'Contents/MacOS' / binary)
                for app, binary in (
                    ('Google Chrome.app', 'Google Chrome'),
                    ('Microsoft Edge.app', 'Microsoft Edge'),
                    ('Chromium.app', 'Chromium'),
                    ('Brave Browser.app', 'Brave Browser'),
                )
            )
    for name in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable', 'microsoft-edge', 'msedge'):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise FileNotFoundError('Chromium browser unavailable')


def render_png(document, browser_path=''):
    from PIL import Image

    browser = find_browser(browser_path)
    with tempfile.TemporaryDirectory(prefix='QQGroupAuthorize-') as temporary:
        folder = Path(temporary)
        page = folder / 'authorization.html'
        shot = folder / 'authorization.png'
        page.write_text(document, encoding='utf-8')
        command = [
            browser,
            '--headless=new',
            '--disable-gpu',
            '--hide-scrollbars',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
            '--disable-background-networking',
            '--run-all-compositor-stages-before-draw',
            f'--force-device-scale-factor={SCALE}',
            '--virtual-time-budget=1500',
            f'--user-data-dir={folder / "browser-profile"}',
            f'--window-size={WIDTH},{HEIGHT}',
            f'--screenshot={shot}',
            page.as_uri(),
        ]
        # Linux 的 root 用户无法启动默认 Chromium 沙箱；仅本地静态页面使用这一兼容开关。
        if sys.platform.startswith('linux') and hasattr(os, 'geteuid') and os.geteuid() == 0:
            command.insert(1, '--no-sandbox')
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=25,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            check=False,
        )
        if result.returncode != 0 or not shot.is_file():
            raise RuntimeError('Browser screenshot failed')
        with Image.open(shot) as source:
            output = BytesIO()
            # 1.5 倍像素直接保留，PNG 只做无损体积优化，避免文字再次损失清晰度。
            image = source.convert('RGB')
            if image.size != IMAGE_SIZE:
                raise RuntimeError('Unexpected screenshot dimensions')
            image.save(output, format='PNG', optimize=True)
        return output.getvalue()


def read_cache(path):
    try:
        from PIL import Image

        data = path.read_bytes()
        if not data.startswith(PNG_SIGNATURE):
            return b''
        with Image.open(BytesIO(data)) as image:
            if image.size != IMAGE_SIZE:
                return b''
            image.verify()
        return data
    except Exception:
        return b''


def guide_image(profile):
    with _render_lock:
        current_svn = config.current_svn()
        needs_upgrade = current_svn > config.load()['svn']
        document = page_html(profile)
        digest = hashlib.sha256((f'PNG:{IMAGE_SIZE}:' + document).encode('utf-8')).hexdigest()[:24]
        destination = profile.folder / 'authorization.png'
        metadata_path = profile.folder / 'authorization.cache.json'
        metadata = read_json(metadata_path)
        cached = read_cache(destination) if not needs_upgrade and metadata.get('document_sha256') == digest else b''
        if cached and hashlib.sha256(cached).hexdigest() == metadata.get('image_sha256'):
            return ImageResult(cached, destination, cached=True)
        try:
            data = render_png(document, profile.browser_path)
        except Exception as exc:
            return ImageResult(warning=f'HTML 渲染或 PNG 保存失败（{type(exc).__name__}），使用文字指引。')
        temporary = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            temporary.replace(destination)
            metadata = {'document_sha256': digest, 'image_sha256': hashlib.sha256(data).hexdigest()}
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                suffix='.tmp',
                mode='w',
                encoding='utf-8',
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(metadata, stream)
            temporary.replace(metadata_path)
        except OSError:
            return ImageResult(data, warning='PNG 缓存写入失败，直接发送本次生成的图片。')
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        # 缓存落盘成功才确认版本，避免生成/写盘失败后误把旧图片当新版复用。
        try:
            config.remember_render_svn(current_svn)
        except config.ConfigError:
            return ImageResult(data, destination, warning='图片已生成，但 config.json 的 svn 写入失败，下次会重试。')
        return ImageResult(data, destination)
