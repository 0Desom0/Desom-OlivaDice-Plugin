from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
import json
import os
import re
import shutil
from threading import RLock
import time

from . import config

ROOT = config.DATA_ROOT
LOCK = RLock()
_snapshots = {}
_recent = deque(maxlen=20)
_log_lock = RLock()


class StorageError(OSError):
    pass


def _account_file(bot_hash, filename):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', bot_hash):
        raise StorageError('无效的 Bot hash')
    return ROOT / 'accounts' / bot_hash / filename


def _write(path, value):
    temp = path.with_name(path.name + '.tmp')
    backup = path.with_name(path.name + '.bak')
    backup_temp = backup.with_name(backup.name + '.tmp')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temp.open('w', encoding='utf-8', newline='\n') as file:
            json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write('\n')
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            # 先更新备份，再替换主文件；失败时原路径始终保留完整 JSON。
            shutil.copyfile(path, backup_temp)
            os.replace(backup_temp, backup)
        os.replace(temp, path)
    except (OSError, ValueError, TypeError) as error:
        for leftover in (temp, backup_temp):
            try:
                leftover.unlink(missing_ok=True)
            except OSError as cleanup_error:
                _persist_error(path, '清理临时文件', cleanup_error)
        _persist_error(path, '写入', error)
        raise StorageError('写入失败，检查目录权限') from error


def _persist_error(path, action, error, archived=None):
    archive_note = f' -> {archived.name}' if archived else ''
    line = f'{datetime.now().isoformat(timespec="seconds")} {path.name} {action}: {type(error).__name__}{archive_note}'
    with _log_lock:
        _recent.append(line)
        try:
            with (path.parent / 'persist_error.log').open('a', encoding='utf-8') as file:
                file.write(line + '\n')
        except OSError as log_error:
            _recent.append(f'persist_error.log 写入失败：{type(log_error).__name__}')


def _defaults(value, default):
    # 仅填补已知配置字段，主播和群的开放式映射保持原样。
    for key, fallback in default.items():
        if key not in value:
            value[key] = deepcopy(fallback)
        elif isinstance(fallback, dict):
            if not isinstance(value[key], dict):
                raise ValueError(f'{key} 必须是 JSON 对象')
            _defaults(value[key], fallback)
        elif type(fallback) is float and type(value[key]) in (int, float):
            continue
        elif type(value[key]) is not type(fallback):
            raise ValueError(f'{key} 类型不符')
    return value


def _load(path, default):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('JSON 根节点必须是对象')
        return _defaults(value, default)
    except FileNotFoundError:
        value = deepcopy(default)
    except (ValueError, UnicodeError) as error:
        archived = path.with_name(f'{path.name}.corrupt-{time.time_ns()}')
        try:
            os.replace(path, archived)
        except OSError as archive_error:
            _persist_error(path, '归档', archive_error)
            raise StorageError('无法归档损坏的配置') from archive_error
        _persist_error(path, '读取', error, archived)
        value = deepcopy(default)
    except OSError as error:
        _persist_error(path, '读取', error)
        raise StorageError('读取失败，检查目录权限') from error
    _write(path, value)
    return value


def _snapshot(path, default):
    # 已发布的快照只读，写事务提交后整体替换，tick 不等待磁盘锁。
    cached = _snapshots.get(path)
    if cached is not None:
        return cached
    with LOCK:
        if path not in _snapshots:
            _snapshots[path] = _load(path, default)
        return _snapshots[path]


@contextmanager
def _edit(path, default):
    with LOCK:
        previous = _snapshot(path, default)
        working = deepcopy(previous)
        yield working
        if working != previous:
            _write(path, working)
            _snapshots[path] = working


def global_config():
    return _snapshot(ROOT / config.GLOBAL_FILE, config.GLOBAL_DEFAULT)


def bot_config(bot_hash):
    return _snapshot(_account_file(bot_hash, config.BOT_FILE), config.BOT_DEFAULT)


def rooms(bot_hash):
    return _snapshot(_account_file(bot_hash, config.ROOMS_FILE), config.ROOMS_DEFAULT)


def load_bot(bot_hash):
    bot_config(bot_hash)
    rooms(bot_hash)


def edit_global():
    return _edit(ROOT / config.GLOBAL_FILE, config.GLOBAL_DEFAULT)


def edit_bot(bot_hash):
    return _edit(_account_file(bot_hash, config.BOT_FILE), config.BOT_DEFAULT)


def edit_rooms(bot_hash):
    return _edit(_account_file(bot_hash, config.ROOMS_FILE), config.ROOMS_DEFAULT)


def recent_logs():
    with _log_lock:
        return list(_recent)


def log(proc, msg, level=2):
    # core/core/API.py: Proc_templet.log。调用方只传摘要，不传响应体、凭据或异常原文。
    if proc is not None:
        proc.log(level, f'[{config.DISPLAY_NAME}] {msg}')
    with _log_lock:
        line = f'{datetime.now().isoformat(timespec="seconds")} {msg}'
        _recent.append(line)
        if not _snapshots.get(ROOT / config.GLOBAL_FILE, {}).get('log_to_file'):
            return
        path = ROOT / 'logs' / f'notify-{date.today():%Y%m%d}.log'
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as file:
                file.write(line + '\n')
        except OSError as error:
            _recent.append(f'通知日志写入失败：{type(error).__name__}')
