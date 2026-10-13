"""群链共享的 JSON 存储；全部文件操作置于同一 bot 的互斥锁内。"""

import errno
import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

if os.name == 'nt':
    import msvcrt
else:
    import fcntl

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_SAFE_KEY = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')


class StorageError(Exception):
    pass


def _key(value):
    value = str(value)
    if not _SAFE_KEY.fullmatch(value):
        raise StorageError('无效的数据目录标识')
    return value


@contextmanager
def _bot_lock(directory, timeout=10):
    lock_path = directory / '.lock'
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(str(directory.resolve()), threading.RLock())
    with lock:
        directory.mkdir(parents=True, exist_ok=True)
        with lock_path.open('a+b') as stream:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    stream.seek(0)
                    if os.name == 'nt':
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if time.monotonic() >= deadline:
                        raise StorageError('等待数据文件锁超时') from error
                    time.sleep(0.02)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _read(path, default):
    # 调用者必须持有 bot 锁；损坏的数据不会被默认值覆盖。
    try:
        with path.open('r', encoding='utf-8') as stream:
            data = json.load(stream)
    except FileNotFoundError:
        return dict(default)
    if not isinstance(data, dict):
        raise StorageError(f'{path.name} 必须为 JSON 对象')
    return data


def _write(path, data):
    # 固定旁路锁覆盖临时文件和替换操作，避免锁随 inode 替换失效。
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=4)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _boolean(data, name, default):
    value = data.get(name, default)
    if type(value) is not bool:
        raise StorageError(f'{name} 必须为布尔值')
    return value


class Storage:
    def __init__(self, core, root=None):
        self.core = core
        self.root = Path(root) if root is not None else Path('plugin') / 'data' / 'StatusHud'

    def linked_hash(self, bot_hash):
        return _key(self.core.userConfig.getRedirectedBotHash(str(bot_hash)))

    def _paths(self, bot_hash, user_id=None, platform=None):
        linked = self.linked_hash(bot_hash)
        directory = self.root / linked
        user_path = None
        if user_id is not None:
            user_hash = _key(self.core.userConfig.getUserHash(user_id, 'user', platform))
            user_path = directory / 'user' / f'{user_hash}.json'
        return directory, directory / 'config.json', user_path

    def initialize(self, bot_hash):
        try:
            directory, config_path, _ = self._paths(bot_hash)
            with _bot_lock(directory):
                (directory / 'user').mkdir(exist_ok=True)
                if not config_path.exists():
                    _write(config_path, {'global_enabled': False})
                else:
                    _boolean(_read(config_path, {}), 'global_enabled', False)
        except (OSError, ValueError, TypeError) as error:
            raise StorageError('初始化 HUD 数据失败') from error

    def status(self, bot_hash, user_id, platform):
        try:
            directory, config_path, user_path = self._paths(bot_hash, user_id, platform)
            with _bot_lock(directory):
                global_enabled = _boolean(_read(config_path, {}), 'global_enabled', False)
                user = _read(user_path, {})
                if 'enabled' in user:
                    enabled = _boolean(user, 'enabled', global_enabled)
                    source = 'user'
                else:
                    enabled, source = global_enabled, 'global'
                return {'enabled': enabled, 'source': source, 'global_enabled': global_enabled}
        except (OSError, ValueError, TypeError) as error:
            raise StorageError('读取 HUD 设置失败') from error

    def set_user(self, bot_hash, user_id, platform, enabled=None):
        try:
            directory, config_path, user_path = self._paths(bot_hash, user_id, platform)
            with _bot_lock(directory):
                user = _read(user_path, {})
                if enabled is None:
                    global_enabled = _boolean(_read(config_path, {}), 'global_enabled', False)
                    enabled = not _boolean(user, 'enabled', global_enabled)
                if type(enabled) is not bool:
                    raise StorageError('enabled 必须为布尔值')
                user['enabled'] = enabled
                _write(user_path, user)
                return enabled
        except (OSError, ValueError, TypeError) as error:
            raise StorageError('保存个人 HUD 设置失败') from error

    def set_global(self, bot_hash, enabled):
        try:
            directory, config_path, _ = self._paths(bot_hash)
            with _bot_lock(directory):
                config = _read(config_path, {})
                _boolean(config, 'global_enabled', False)
                if type(enabled) is not bool:
                    raise StorageError('global_enabled 必须为布尔值')
                config['global_enabled'] = enabled
                _write(config_path, config)
        except (OSError, ValueError, TypeError) as error:
            raise StorageError('保存全局 HUD 设置失败') from error
