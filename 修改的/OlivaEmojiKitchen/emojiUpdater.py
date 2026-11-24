# -*- encoding: utf-8 -*-
'''
@File      :   emojiUpdater.py
@Author    :   lunzhiPenxil仑质
@Contact   :   lunzhipenxil@gmail.com
@License   :   AGPL
@Copyright :   (C) 2020-2026, OlivOS-Team
@Desc      :   数据更新器。由插件内的 OlivOS 定时任务每天 04:00 触发，
               从上游 emoji-kitchen 拉取 metadata.json，重建成
               plugin/data/OlivaEmojiKitchen/emojiData.json。

               上游 metadata 约 99MB（gzip 传输约 9MB），解析后按
               「组合 left|right -> 日期」压缩成约 3.9MB，emojiData 模块
               按文件 mtime 热加载，所以更新完下一条消息就生效。

               两层保障：
               * 定时任务：OlivOS >= 1.0.5 的 scheduleAPI，每天 04:00 精确触发。
               * 看门狗线程：数据超过 FRESH_HOURS 就补更新。老核心没有
                 scheduleAPI 时由它兜底，新核心上也能兜住某天定时任务失败。

               回退：写入前先按时间戳备份旧文件（与主数据同目录，保留 BACKUP_KEEP 份），
               新文件写完会回读校验，不通过就自动恢复上一份备份。
'''

import gzip
import io
import json
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime

import requests as req

import OlivaEmojiKitchen.emojiData as emojiData

# 上游地址，按顺序降级
SOURCES = [
    'https://raw.githubusercontent.com/xsalazar/emoji-kitchen-backend/main/app/metadata.json',
    'https://emojikitchen.dev/metadata.json',
    'https://cdn.jsdelivr.net/gh/xsalazar/emoji-kitchen-backend@main/app/metadata.json',
]

MIN_EMOJI = 200
MIN_COMBINATIONS = 100000
MAX_SHRINK_RATIO = 0.80

# 数据超过这个小时数就算过期；定时任务与看门狗共用同一个口径
FRESH_HOURS = 24
# 看门狗检查间隔
WATCH_INTERVAL_SECONDS = 15 * 60

HTTP_TIMEOUT = (10, 180)
CHUNK_SIZE = 256 * 1024
LOG_KEEP_LINES = 200

BACKUP_PREFIX = 'emojiData_'
BACKUP_KEEP = 3

_lock = threading.Lock()
_watch_stop = threading.Event()
_watch_thread = None


# ---------------------------------------------------------------- 路径与日志

def data_dir():
    '''定位 plugin/data/OlivaEmojiKitchen，优先用插件同级的 data 目录。'''
    for path in emojiData._candidate_paths():
        directory = os.path.dirname(path)
        # <root>/plugin/data/OlivaEmojiKitchen -> 上两级是 <root>/plugin
        plugin_root = os.path.dirname(os.path.dirname(directory))
        if os.path.isdir(os.path.join(plugin_root, 'app')):
            return directory
    return os.path.join(os.getcwd(), 'plugin', 'data', emojiData.NAMESPACE)


def target_path():
    return os.path.join(data_dir(), emojiData.DATA_FILE_NAME)


def _log_path():
    return os.path.join(data_dir(), 'update.log')


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _record(entry):
    '''追加一行 JSON 到 update.log，保留最近 LOG_KEEP_LINES 行。'''
    try:
        path = _log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lines = []
        if os.path.isfile(path):
            try:
                with io.open(path, 'r', encoding='utf-8') as fp:
                    lines = fp.read().splitlines()
            except OSError:
                lines = []
        entry = dict(entry, time=_now_iso())
        lines.append(json.dumps(entry, ensure_ascii=False))
        lines = lines[-LOG_KEEP_LINES:]
        temporary = path + '.tmp'
        with io.open(temporary, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write('\n'.join(lines) + '\n')
        os.replace(temporary, path)
    except Exception:
        pass


def _is_fresh(path, hours=FRESH_HOURS):
    try:
        return (time.time() - os.path.getmtime(path)) < hours * 3600
    except OSError:
        return False


# ---------------------------------------------------------------- 备份与回退

def _list_backups():
    '''备份和主数据放在同一个目录，按文件名前缀区分。'''
    directory = data_dir()
    if not os.path.isdir(directory):
        return []
    items = []
    for name in os.listdir(directory):
        if not name.startswith(BACKUP_PREFIX) or not name.endswith('.json'):
            continue
        path = os.path.join(directory, name)
        try:
            items.append((path, os.path.getmtime(path)))
        except OSError:
            continue
    items.sort(key=lambda item: os.path.basename(item[0]), reverse=True)
    return items


def _prune_backups(keep=BACKUP_KEEP):
    '''参照 OlivaDiceMaster 的 manageBackupCount：按时间排序，只留最近 keep 份。'''
    removed = []
    for path, _mtime in _list_backups()[keep:]:
        try:
            os.remove(path)
            removed.append(os.path.basename(path))
        except OSError:
            continue
    return removed


def _backup_current(target):
    '''把当前数据复制成同目录下的 emojiData_YYYY-mm-dd_HH-MM-SS.json。'''
    if not os.path.isfile(target):
        return None
    try:
        name = BACKUP_PREFIX + datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.json'
        destination = os.path.join(data_dir(), name)
        # copyfile 不继承源文件 mtime，备份时间就是落盘时间
        shutil.copyfile(target, destination)
        _prune_backups()
        return destination
    except Exception:
        return None


def _restore(target, backup_path):
    if not backup_path or not os.path.isfile(backup_path):
        return False
    try:
        shutil.copy2(backup_path, target)
        return True
    except Exception:
        return False


def _verify_file(path):
    '''回读校验：能解析、schema 对、条数够。'''
    try:
        with io.open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except Exception as exc:
        return False, '无法解析: %s' % exc
    if not isinstance(data, dict) or data.get('schema') != 2:
        return False, 'schema 不匹配'
    emoji_count = len(data.get('emoji') or {})
    combinations = len(data.get('combinations') or {})
    if emoji_count < MIN_EMOJI:
        return False, 'emoji 数量不足: %d' % emoji_count
    if combinations < MIN_COMBINATIONS:
        return False, '组合数量不足: %d' % combinations
    return True, ''


# ---------------------------------------------------------------- 抓取与重建

def _download(url, path):
    with req.get(url, timeout=HTTP_TIMEOUT, stream=True) as response:
        if response.status_code != 200:
            raise RuntimeError('HTTP %s' % response.status_code)
        size = 0
        with open(path, 'wb') as output:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    output.write(chunk)
                    size += len(chunk)
    return size


def _load_json(path):
    '''读取下载结果；个别网络栈不会替我们解 gzip，这里兜一下。'''
    with open(path, 'rb') as probe:
        head = probe.read(2)
    if head == b'\x1f\x8b':
        with gzip.open(path, 'rt', encoding='utf-8') as fp:
            return json.load(fp)
    with io.open(path, 'r', encoding='utf-8') as fp:
        return json.load(fp)


def _build(metadata):
    '''把上游 metadata 压成插件用的两张表。'''
    source_data = metadata.get('data') or {}
    emoji_map = {}
    for codepoint, item in source_data.items():
        if not isinstance(item, dict):
            continue
        emoji_map[codepoint] = [item.get('alt') or '', item.get('emoji') or '']

    combinations = {}
    for item in source_data.values():
        if not isinstance(item, dict):
            continue
        for records in (item.get('combinations') or {}).values():
            if not isinstance(records, list) or not records:
                continue
            record = None
            for candidate in records:
                if isinstance(candidate, dict) and candidate.get('isLatest'):
                    record = candidate
                    break
            if record is None:
                record = records[0]
            if not isinstance(record, dict):
                continue
            left = record.get('leftEmojiCodepoint')
            right = record.get('rightEmojiCodepoint')
            date = record.get('date')
            if not left or not right or not date:
                continue
            key = left + '|' + right
            if key not in combinations:
                combinations[key] = str(date)
    return emoji_map, combinations


def _previous_counts(path):
    try:
        with io.open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        return len(data.get('combinations') or {}), len(data.get('emoji') or {})
    except (OSError, ValueError):
        return 0, 0


def _write_atomic(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.emojiData-', suffix='.json.tmp', dir=os.path.dirname(path))
    try:
        with io.open(handle, 'w', encoding='utf-8', newline='\n') as fp:
            json.dump(payload, fp, ensure_ascii=False, separators=(',', ':'))
            fp.write('\n')
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------- 对外入口

def update(force=False):
    '''抓取上游并重建数据文件。返回 True/False，细节写 update.log。'''
    target = target_path()
    if not force and _is_fresh(target):
        return True
    if not _lock.acquire(blocking=False):
        # 另一个更新在跑；数据若已新鲜就当成功，别刷噪音日志
        if _is_fresh(target):
            return True
        _record({'ok': False, 'error': '已有更新在进行中，本次跳过'})
        return False

    temporary = None
    started = time.time()
    try:
        old_combinations, _old_emoji = _previous_counts(target)
        url = None
        metadata = None
        last_error = None
        for candidate in SOURCES:
            try:
                handle, temporary = tempfile.mkstemp(prefix='.metadata-', suffix='.json', dir=tempfile.gettempdir())
                os.close(handle)
                size = _download(candidate, temporary)
                metadata = _load_json(temporary)
                if not isinstance(metadata, dict) or 'data' not in metadata:
                    raise ValueError('metadata 结构不符合预期')
                url, raw_size = candidate, size
                break
            except Exception as exc:
                last_error = '%s: %s' % (candidate, exc)
                metadata = None
                continue
        if metadata is None:
            raise RuntimeError('所有数据源都失败: %s' % last_error)

        emoji_map, combinations = _build(metadata)
        metadata = None

        if len(emoji_map) < MIN_EMOJI:
            raise RuntimeError('emoji 数量异常: %d' % len(emoji_map))
        if len(combinations) < MIN_COMBINATIONS:
            raise RuntimeError('组合数量异常: %d' % len(combinations))
        if old_combinations and len(combinations) < old_combinations * MAX_SHRINK_RATIO:
            raise RuntimeError('组合数从 %d 缩到 %d，疑似上游异常，未覆盖'
                               % (old_combinations, len(combinations)))

        payload = {
            'schema': 2,
            'generated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'source': url,
            'source_bytes': raw_size,
            'emoji_count': len(emoji_map),
            'combination_count': len(combinations),
            'emoji': emoji_map,
            'combinations': combinations,
        }

        # 写之前先留一份旧数据，写坏了好回退（参照 OlivaDiceMaster 的备份做法）
        backup_path = _backup_current(target)
        try:
            _write_atomic(target, payload)
        except Exception as exc:
            restored = _restore(target, backup_path)
            raise RuntimeError('写入失败（%s），%s' % (
                exc, '已回退到上一份备份' if restored else '没有可用备份'))

        verified, detail = _verify_file(target)
        if not verified:
            restored = _restore(target, backup_path)
            raise RuntimeError('新数据校验失败（%s），%s' % (
                detail, '已回退到上一份备份' if restored else '且没有可用备份'))

        _record({
            'ok': True,
            'source': url,
            'source_bytes': raw_size,
            'emoji': len(emoji_map),
            'combinations': len(combinations),
            'previous_combinations': old_combinations,
            'file_bytes': os.path.getsize(target),
            'backup': os.path.basename(backup_path) if backup_path else None,
            'seconds': round(time.time() - started, 1),
        })
        return True
    except Exception as exc:
        _record({'ok': False, 'error': str(exc), 'seconds': round(time.time() - started, 1)})
        return False
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        _lock.release()


# ---------------------------------------------------------------- 看门狗

def _watchdog_loop():
    '''低频检查：数据超过 FRESH_HOURS 就补更新。

    不依赖 scheduleAPI，老核心（没有定时任务）也能按天刷新；
    新核心上定时任务某天失败时，这里会补上。
    '''
    while not _watch_stop.is_set():
        try:
            if not _is_fresh(target_path()):
                update(force=False)
        except Exception:
            pass
        if _watch_stop.wait(WATCH_INTERVAL_SECONDS):
            break


def start_watchdog():
    '''幂等启动看门狗线程；插件每次加载都会调用，重复调用不会起第二个。'''
    global _watch_thread
    if _watch_thread is not None and _watch_thread.is_alive():
        return _watch_thread
    _watch_stop.clear()
    _watch_thread = threading.Thread(target=_watchdog_loop, name='emoji-data-watchdog', daemon=True)
    _watch_thread.start()
    return _watch_thread


def stop_watchdog():
    _watch_stop.set()


def ensure_fresh_async():
    '''兼容旧调用：启动补偿交给看门狗线程，第一次循环就会检查。'''
    return start_watchdog()
