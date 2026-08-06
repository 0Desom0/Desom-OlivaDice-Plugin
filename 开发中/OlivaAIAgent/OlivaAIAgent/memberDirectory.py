# -*- encoding: utf-8 -*-
'''群成员昵称目录：记录启用群内出现的成员，并为字面 @昵称 提供反查。'''

import os
import re
import sqlite3
import threading
import time

import OlivOS
import OlivaAIAgent

_lock = threading.RLock()
_initialized_path = None
_INVALID_ALIASES = {'', '[]', 'Nobody', 'unknown', '用户', '未知用户'}


def _dbPath():
    return os.path.join(OlivaAIAgent.conf.dataPath, 'group_members.sqlite3')


def initialize():
    global _initialized_path
    path = _dbPath()
    with _lock:
        if _initialized_path == path and os.path.exists(path):
            return
        OlivaAIAgent.conf.releaseDir(os.path.dirname(path))
        conn = sqlite3.connect(path, timeout=15)
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS members (
                    bot_hash TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    nickname TEXT,
                    name TEXT,
                    card TEXT,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (bot_hash, platform, group_id, user_id)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS member_aliases (
                    bot_hash TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (bot_hash, platform, group_id, user_id, alias)
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_member_alias_lookup
                ON member_aliases(bot_hash, platform, group_id, alias)
            ''')
            conn.commit()
            _initialized_path = path
        finally:
            conn.close()


def _connect():
    initialize()
    conn = sqlite3.connect(_dbPath(), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _eventContext(plugin_event):
    platform_data = getattr(plugin_event, 'platform', {})
    platform = str(platform_data.get('platform', '') if isinstance(platform_data, dict) else '')
    data = getattr(plugin_event, 'data', None)
    group_id = getattr(data, 'group_id', None)
    bot_info = getattr(plugin_event, 'bot_info', None)
    bot_hash = getattr(bot_info, 'hash', None) if bot_info is not None else None
    if bot_hash in [None, '']:
        bot_hash = getattr(plugin_event, 'base_info', {}).get('self_id', 'unity')
    return str(bot_hash), platform, str(group_id or '')


def _cleanAlias(value, user_id=''):
    alias = re.sub(r'[\r\n\t]+', ' ', str(value or '')).strip()
    if alias in _INVALID_ALIASES or alias == str(user_id) or len(alias) > 80:
        return ''
    return alias


def recordIncoming(plugin_event):
    '''登记当前群消息发送者；调用方负责保证该群已启用。'''
    data = getattr(plugin_event, 'data', None)
    user_id = str(getattr(data, 'user_id', '') or '').strip()
    bot_hash, platform, group_id = _eventContext(plugin_event)
    if not user_id or not group_id:
        return False
    sender = getattr(data, 'sender', {})
    sender = sender if isinstance(sender, dict) else {}
    names = {
        key: _cleanAlias(sender.get(key), user_id)
        for key in ('nickname', 'name', 'card')
    }
    aliases = list(dict.fromkeys(value for value in names.values() if value))
    now = time.time()
    try:
        with _lock:
            conn = _connect()
            try:
                conn.execute('''
                    INSERT INTO members (
                        bot_hash, platform, group_id, user_id,
                        nickname, name, card, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(bot_hash, platform, group_id, user_id) DO UPDATE SET
                        nickname=COALESCE(NULLIF(excluded.nickname, ''), members.nickname),
                        name=COALESCE(NULLIF(excluded.name, ''), members.name),
                        card=COALESCE(NULLIF(excluded.card, ''), members.card),
                        updated_at=excluded.updated_at
                ''', (
                    bot_hash,
                    platform,
                    group_id,
                    user_id,
                    names['nickname'],
                    names['name'],
                    names['card'],
                    now,
                ))
                conn.executemany('''
                    INSERT INTO member_aliases (
                        bot_hash, platform, group_id, user_id, alias, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(bot_hash, platform, group_id, user_id, alias) DO UPDATE SET
                        updated_at=excluded.updated_at
                ''', [
                    (bot_hash, platform, group_id, user_id, alias, now)
                    for alias in aliases
                ])
                conn.commit()
            finally:
                conn.close()
        return True
    except Exception as e:
        OlivaAIAgent.conf.log(OlivaAIAgent.conf.gProc, 3, '群成员目录登记失败: %s' % e)
        return False


def _localAliases(plugin_event):
    bot_hash, platform, group_id = _eventContext(plugin_event)
    if not group_id:
        return []
    try:
        with _lock:
            conn = _connect()
            try:
                rows = conn.execute('''
                    SELECT DISTINCT alias FROM member_aliases
                    WHERE bot_hash=? AND platform=? AND group_id=?
                    ORDER BY LENGTH(alias) DESC, updated_at DESC
                ''', (bot_hash, platform, group_id)).fetchall()
            finally:
                conn.close()
        return [str(row['alias']) for row in rows]
    except Exception:
        return []


def _resolveFromLocal(plugin_event, nickname):
    bot_hash, platform, group_id = _eventContext(plugin_event)
    if not group_id:
        return None
    try:
        with _lock:
            conn = _connect()
            try:
                rows = conn.execute('''
                    SELECT DISTINCT user_id FROM member_aliases
                    WHERE bot_hash=? AND platform=? AND group_id=? AND alias=? COLLATE NOCASE
                ''', (bot_hash, platform, group_id, nickname)).fetchall()
            finally:
                conn.close()
        return list(dict.fromkeys(str(row['user_id']) for row in rows))
    except Exception:
        return []


def _olivosCacheEntries(plugin_event):
    '''只读 QQGuild 适配器缓存，并限定为当前 bot、当前群。'''
    sdk = str(getattr(plugin_event, 'platform', {}).get('sdk', '')).lower()
    if 'qqguildv2' not in sdk:
        return []
    adapter = getattr(OlivOS, 'qqGuildv2SDK', None)
    cache = getattr(adapter, 'sdkUserInfo', None)
    if not isinstance(cache, dict):
        return []
    bot_hash, _platform, group_id = _eventContext(plugin_event)
    lock = getattr(adapter, 'sdkUserInfoLock', None)

    def snapshot():
        return list(cache.items())

    try:
        entries = snapshot() if lock is None else None
        if lock is not None:
            with lock:
                entries = snapshot()
    except Exception:
        return []
    result = []
    seen = set()
    for key, record in entries or []:
        if not isinstance(key, tuple) or len(key) < 2 or str(key[0]) != bot_hash:
            continue
        if not isinstance(record, dict):
            continue
        if str(record.get('chat_type') or '') not in ['', 'qq_group']:
            continue
        record_group = str(record.get('chat_id') or '')
        if record_group and record_group != group_id:
            continue
        alias = _cleanAlias(record.get('name'))
        user_id = str(
            record.get('member_openid')
            or record.get('user_openid')
            or record.get('id')
            or key[1]
            or ''
        ).strip()
        item_key = (alias.casefold(), user_id)
        if alias and user_id and item_key not in seen:
            seen.add(item_key)
            result.append((alias, user_id))
    return result


def _resolveFromOlivOSCache(plugin_event, nickname):
    target = str(nickname or '').strip().casefold()
    user_ids = list(dict.fromkeys(
        user_id
        for alias, user_id in _olivosCacheEntries(plugin_event)
        if alias.casefold() == target
    ))
    return user_ids[0] if len(user_ids) == 1 else None


def _currentSenderMatch(plugin_event, nickname):
    data = getattr(plugin_event, 'data', None)
    user_id = str(getattr(data, 'user_id', '') or '').strip()
    sender = getattr(data, 'sender', {})
    if not user_id or not isinstance(sender, dict):
        return None
    target = str(nickname or '').strip().casefold()
    aliases = {
        _cleanAlias(sender.get(key), user_id).casefold()
        for key in ('nickname', 'name', 'card')
    }
    return user_id if target and target in aliases else None


def resolveNickname(plugin_event, nickname):
    '''按 OlivOS 缓存、本地目录、当前事件发送者的顺序反查唯一用户。'''
    nickname = _cleanAlias(nickname)
    if not nickname:
        return None
    cached = _resolveFromOlivOSCache(plugin_event, nickname)
    if cached:
        return cached
    local_ids = _resolveFromLocal(plugin_event, nickname)
    if local_ids:
        return local_ids[0] if len(local_ids) == 1 else None
    return _currentSenderMatch(plugin_event, nickname)


def knownAliases(plugin_event):
    aliases = [alias for alias, _user_id in _olivosCacheEntries(plugin_event)]
    aliases.extend(_localAliases(plugin_event))
    data = getattr(plugin_event, 'data', None)
    sender = getattr(data, 'sender', {})
    user_id = str(getattr(data, 'user_id', '') or '')
    if isinstance(sender, dict):
        aliases.extend(_cleanAlias(sender.get(key), user_id) for key in ('nickname', 'name', 'card'))
    return sorted(
        {alias for alias in aliases if alias},
        key=lambda value: (len(value), value),
        reverse=True,
    )


def normalizeLiteralMentions(plugin_event, text):
    '''把文本中的可唯一反查 @昵称 转成标准 OP at；邮箱和未知昵称保持原样。'''
    result = str(text or '')
    for alias in knownAliases(plugin_event):
        user_id = resolveNickname(plugin_event, alias)
        if not user_id:
            continue
        pattern = re.compile(
            rf'(?<![A-Za-z0-9_.%+\-])[@＠]{re.escape(alias)}(?![\w.\-])',
            re.I,
        )
        result = pattern.sub('[OP:at,id=%s]' % user_id, result)
    return result
