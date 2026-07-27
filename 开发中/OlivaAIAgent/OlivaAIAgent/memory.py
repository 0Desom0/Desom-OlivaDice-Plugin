# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 记忆管理
- 会话记录: 按 平台+群+用户 隔离的多轮对话 (sessions/)
- 用户记忆: 跨群跟随用户 (memory/user_*)
- 群记忆:   本群共享 (memory/group_*)
- 群滚动上下文: 内存中的最近群消息缓冲，用于自由唤醒与上下文注入
'''

import json
import os
import re
import threading
import time

import OlivaAIAgent

_lock = threading.RLock()

# {key: [msg, ...]}  msg 为内部格式 dict
_sessions = {}
_dirty_sessions = set()

# {'user|platform|id': [ {'time','content'}, ... ]}
_memories = {}
_dirty_memories = set()

# {(platform, group_id): [ {'time','user_id','name','text'}, ... ]}
_group_buffer = {}


def _safe_name(s):
    return re.sub(r'[^0-9A-Za-z_\-]', '_', str(s))


def _session_path(key):
    return OlivaAIAgent.conf.dataPath + '/sessions/' + _safe_name(key) + '.json'


def _memory_path(key):
    return OlivaAIAgent.conf.dataPath + '/memory/' + _safe_name(key) + '.json'


def sessionKey(platform, group_id, user_id):
    return '%s|%s|%s' % (str(platform), str(group_id), str(user_id))


def userMemKey(platform, user_id):
    return 'user|%s|%s' % (str(platform), str(user_id))


def groupMemKey(platform, group_id):
    return 'group|%s|%s' % (str(platform), str(group_id))


def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_json(path, data):
    try:
        OlivaAIAgent.conf.atomicDump(data, path)
    except Exception:
        pass


# ---------------- 会话 ----------------

def getSession(key):
    with _lock:
        if key not in _sessions:
            _sessions[key] = _load_json(_session_path(key), [])
        return list(_sessions[key])


def appendSession(key, msgs):
    max_rounds = OlivaAIAgent.conf.get('memory', 'max_rounds', default=16)
    keep = max(2, int(max_rounds)) * 2
    with _lock:
        if key not in _sessions:
            _sessions[key] = _load_json(_session_path(key), [])
        _sessions[key].extend(msgs)
        # 裁剪时保证不以 tool 消息开头（避免孤儿 tool 结果）
        data = _sessions[key][-keep:]
        while len(data) > 0 and data[0].get('role') in ['tool']:
            data = data[1:]
        _sessions[key] = data
        _dirty_sessions.add(key)
        _save_json(_session_path(key), _sessions[key])


def clearSession(key):
    with _lock:
        _sessions[key] = []
        _save_json(_session_path(key), [])


def clearGroupSessions(platform, group_id):
    '''清空某群所有人的会话'''
    prefix = '%s|%s|' % (str(platform), str(group_id))
    count = 0
    with _lock:
        for key in list(_sessions.keys()):
            if key.startswith(prefix):
                _sessions[key] = []
                _save_json(_session_path(key), [])
                count += 1
        # 磁盘上未加载的
        sess_dir = OlivaAIAgent.conf.dataPath + '/sessions'
        try:
            safe_prefix = _safe_name(prefix)
            for fn in os.listdir(sess_dir):
                if fn.startswith(safe_prefix) and fn.endswith('.json'):
                    _save_json(sess_dir + '/' + fn, [])
                    count += 1
        except Exception:
            pass
    return count


# ---------------- 长期记忆 ----------------

_memory_mtime = {}   # 长期记忆文件 mtime，用于热重载


def _touchMemMtime(key):
    try:
        _memory_mtime[key] = os.path.getmtime(_memory_path(key))
    except Exception:
        pass


def _getMem(key):
    with _lock:
        if key not in _memories:
            _memories[key] = _load_json(_memory_path(key), [])
            _touchMemMtime(key)
        return _memories[key]


def memAdd(key, content, limit):
    try:
        limit = int(limit)
    except Exception:
        limit = 40
    limit = max(1, limit)   # 防御非法上限：<=0 会把刚写入的记忆连同旧记忆全部弹空
    with _lock:
        mem = _getMem(key)
        mem.append({'time': time.strftime('%Y-%m-%d %H:%M'), 'content': str(content)[:500]})
        while len(mem) > limit:
            mem.pop(0)
        _save_json(_memory_path(key), mem)
        _touchMemMtime(key)
        return len(mem)


def memList(key):
    return list(_getMem(key))


def memDelete(key, index):
    with _lock:
        mem = _getMem(key)
        if 0 <= index < len(mem):
            item = mem.pop(index)
            _save_json(_memory_path(key), mem)
            _touchMemMtime(key)
            return item
    return None


def memClear(key):
    with _lock:
        _memories[key] = []
        _save_json(_memory_path(key), [])
        _touchMemMtime(key)


def hotReload():
    '''检测已缓存的长期记忆文件(user_/group_)是否被外部修改并重载。'''
    changed = []
    with _lock:
        keys = list(_memories.keys())
    for key in keys:
        try:
            p = _memory_path(key)
            m = os.path.getmtime(p) if os.path.exists(p) else 0.0
            if m > _memory_mtime.get(key, 0.0):
                data = _load_json(p, [])
                with _lock:
                    _memories[key] = data
                    _memory_mtime[key] = m
                changed.append('长期记忆')
        except Exception:
            pass
    return changed


def memFormat(key, title):
    mem = memList(key)
    if len(mem) == 0:
        return ''
    lines = ['%d. [%s] %s' % (i, m.get('time', ''), m.get('content', '')) for i, m in enumerate(mem)]
    return '【%s】\n%s\n' % (title, '\n'.join(lines))


# ---------------- 群滚动上下文 ----------------

def bufferAppend(platform, group_id, user_id, name, text):
    try:
        cap = int(OlivaAIAgent.conf.get('memory', 'context_buffer', default=20))
    except Exception:
        cap = 20
    cap = max(1, cap)   # 防御非法值：<=0 会在空列表上继续 pop 抛 IndexError，中断整条消息处理
    k = (str(platform), str(group_id))
    with _lock:
        buf = _group_buffer.setdefault(k, [])
        buf.append({
            'time': time.strftime('%H:%M'),
            'user_id': str(user_id),
            'name': str(name) if name else str(user_id),
            'text': str(text)[:300],
        })
        while len(buf) > cap:
            buf.pop(0)


def bufferGet(platform, group_id, limit=None):
    k = (str(platform), str(group_id))
    with _lock:
        buf = list(_group_buffer.get(k, []))
    if limit is not None:
        buf = buf[-int(limit):]
    return buf


def bufferFormat(platform, group_id, limit=None):
    buf = bufferGet(platform, group_id, limit)
    if len(buf) == 0:
        return ''
    lines = ['[%s] %s(%s): %s' % (m['time'], m['name'], m['user_id'], m['text']) for m in buf]
    return '\n'.join(lines)


# ---------------- 持久化 ----------------

def saveAll():
    with _lock:
        for key in list(_dirty_sessions):
            if key in _sessions:
                _save_json(_session_path(key), _sessions[key])
        _dirty_sessions.clear()
        for key in list(_dirty_memories):
            if key in _memories:
                _save_json(_memory_path(key), _memories[key])
        _dirty_memories.clear()
