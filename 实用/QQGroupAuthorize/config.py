"""统一配置：显示名、浏览器、全局骰主，以及按 bot hash 隔离的入群开关。"""

import copy
import json
import tempfile
import threading
from pathlib import Path

ROOT = Path('plugin/data/QQGroupAuthorize')
_lock = threading.RLock()
DEFAULT = {'svn': 0, 'browser_path': '', 'masters': [], 'bots': {}}
BOT_DEFAULT = {'name': '', 'auto_join': False}

# 与 HTML 一样在 import 时读入，OPK 临时目录清理后不再读取 app.json。
try:
    PLUGIN_SVN = json.loads((Path(__file__).parent / 'app.json').read_text(encoding='utf-8'))['svn']
    if type(PLUGIN_SVN) is not int or PLUGIN_SVN < 0:
        PLUGIN_SVN = None
except (OSError, UnicodeError, ValueError, KeyError, TypeError):
    PLUGIN_SVN = None


class ConfigError(ValueError):
    pass


def load():
    path = ROOT / 'config.json'
    if not path.exists():
        return copy.deepcopy(DEFAULT)
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ConfigError('无法读取插件 config.json，请检查文件权限和 JSON 格式。') from exc
    if (
        not isinstance(value, dict)
        or not isinstance(value.get('browser_path', ''), str)
        or not isinstance(value.get('masters', []), list)
        or not isinstance(value.get('bots', {}), dict)
        or any(not isinstance(item, str) or not item.strip() for item in value.get('masters', []))
    ):
        raise ConfigError('config.json 中 browser_path 必须为字符串，masters 为 ID 字符串列表，bots 为对象。')
    if type(value.get('svn', 0)) is not int or value.get('svn', 0) < 0:
        raise ConfigError('config.json 中 svn 必须为非负整数。')
    for item in value.get('bots', {}).values():
        if (
            not isinstance(item, dict)
            or not isinstance(item.get('name', ''), str)
            or not isinstance(item.get('auto_join', False), bool)
        ):
            raise ConfigError('config.json 中每个 bot 的 name 必须为字符串，auto_join 必须为布尔值。')
    for key, default in DEFAULT.items():
        value.setdefault(key, copy.deepcopy(default))
    return value


def save(value):
    temporary = None
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=ROOT,
            suffix='.tmp',
            mode='w',
            encoding='utf-8',
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
        temporary.replace(ROOT / 'config.json')
    except OSError as exc:
        raise ConfigError('无法保存插件 config.json，开关未改变。') from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def initialize(bots):
    with _lock:
        value = load()
        changed = not (ROOT / 'config.json').exists()
        for bot in bots:
            if bot.platform.get('sdk') == 'qqGuildv2_link' and str(bot.hash) not in value['bots']:
                value['bots'][str(bot.hash)] = copy.deepcopy(BOT_DEFAULT)
                changed = True
        if changed:
            save(value)


def auto_join_enabled(bot_hash):
    with _lock:
        item = load()['bots'].get(str(bot_hash), {})
        return isinstance(item, dict) and item.get('auto_join') is True


def set_auto_join(bot_hash, enabled):
    with _lock:
        value = load()
        item = value['bots'].setdefault(str(bot_hash), copy.deepcopy(BOT_DEFAULT))
        if not isinstance(item, dict):
            raise ConfigError('当前 bot 的配置必须为对象，开关未改变。')
        item['auto_join'] = bool(enabled)
        save(value)


def remember_name(bot_hash, name):
    with _lock:
        value = load()
        item = value['bots'].setdefault(str(bot_hash), copy.deepcopy(BOT_DEFAULT))
        if item.get('name') != name:
            item['name'] = name
            save(value)


def current_svn():
    if PLUGIN_SVN is None:
        raise ConfigError('无法读取当前插件 svn，请检查安装包 app.json。')
    return PLUGIN_SVN


def remember_render_svn(svn):
    with _lock:
        value = load()
        if value['svn'] < svn:
            value['svn'] = svn
            save(value)


def is_master(event):
    user_id = str(event.data.user_id)
    with _lock:
        if user_id in load()['masters']:
            return True
    try:
        import OlivaDiceCore

        user_hash = OlivaDiceCore.userConfig.getUserHash(user_id, 'user', event.platform['platform'])
        return OlivaDiceCore.ordinaryInviteManager.isInMasterList(event.bot_info.hash, user_hash) is True
    except Exception:
        return False
