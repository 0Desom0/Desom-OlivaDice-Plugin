# -*- encoding: utf-8 -*-
'''插件内消息标识注册表：持久化消息 ID、引用 ID 与平台索引，不修改 OlivOS。'''

import hashlib
import os
import sqlite3
import threading
import time

import OlivaAIAgent

_lock = threading.RLock()
_initialized_path = None
_last_cleanup = 0.0


def _dbPath():
    return os.path.join(OlivaAIAgent.conf.dataPath, 'message_registry.sqlite3')


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
                CREATE TABLE IF NOT EXISTS messages (
                    record_key TEXT PRIMARY KEY,
                    bot_hash TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    chat_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    message_id TEXT,
                    message_index TEXT,
                    reference_message_id TEXT,
                    reference_index TEXT,
                    event_id TEXT,
                    sender_id TEXT,
                    sender_name TEXT,
                    content TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_message_registry_id
                ON messages(bot_hash, platform, chat_type, scope_id, message_id, updated_at DESC)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_message_registry_index
                ON messages(bot_hash, platform, chat_type, scope_id, message_index, updated_at DESC)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_message_registry_recent
                ON messages(bot_hash, platform, chat_type, scope_id, updated_at DESC)
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


def eventContext(plugin_event):
    platform_data = getattr(plugin_event, 'platform', {})
    platform = str(platform_data.get('platform', '') if isinstance(platform_data, dict) else '')
    func_type = str(getattr(plugin_event, 'plugin_info', {}).get('func_type', ''))
    data = getattr(plugin_event, 'data', None)
    if func_type in ['group_message', 'group_message_sent']:
        chat_type = 'group'
        scope_id = getattr(data, 'group_id', None)
    else:
        chat_type = 'private'
        scope_id = getattr(data, 'user_id', None)
    bot_info = getattr(plugin_event, 'bot_info', None)
    bot_hash = getattr(bot_info, 'hash', None) if bot_info is not None else None
    if bot_hash in [None, '']:
        bot_hash = str(getattr(plugin_event, 'base_info', {}).get('self_id', 'unity'))
    return {
        'bot_hash': str(bot_hash),
        'platform': platform,
        'chat_type': chat_type,
        'scope_id': str(scope_id if scope_id not in [None, ''] else 'unknown'),
    }


def _recordKey(context, direction, message_id, message_index, event_id):
    identity = message_id or event_id or message_index or ('%.9f' % time.time())
    raw = '\x1f'.join([
        context['bot_hash'],
        context['platform'],
        context['chat_type'],
        context['scope_id'],
        str(direction),
        str(identity),
    ])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _clean(value):
    return None if value in [None, '', '-1', -1] else str(value)


def _retentionCutoff():
    retention = max(1.0, float(OlivaAIAgent.conf.get(
        'message_registry', 'retention_days', default=7,
    )))
    return time.time() - retention * 86400.0


def _cleanup(conn):
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < 300:
        return
    conn.execute('DELETE FROM messages WHERE updated_at < ?', (_retentionCutoff(),))
    limit = max(100, int(OlivaAIAgent.conf.get('message_registry', 'max_records', default=50000)))
    count = int(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0])
    if count > limit:
        conn.execute('''
            DELETE FROM messages WHERE record_key IN (
                SELECT record_key FROM messages ORDER BY updated_at ASC LIMIT ?
            )
        ''', (count - limit,))
    conn.commit()
    _last_cleanup = now


def record(
    plugin_event,
    direction,
    message_id=None,
    message_index=None,
    reference_message_id=None,
    reference_index=None,
    event_id=None,
    sender_id=None,
    sender_name=None,
    content=None,
    content_max_chars=None,
):
    '''登记一条收发消息；至少有一种平台标识时才写入。'''
    identifiers = [message_id, message_index, reference_message_id, reference_index, event_id]
    if all(item in [None, '', '-1', -1] for item in identifiers):
        return
    context = eventContext(plugin_event)
    try:
        max_chars = max(128, int(OlivaAIAgent.conf.get(
            'message_registry', 'content_max_chars', default=4096,
        )))
    except (TypeError, ValueError):
        max_chars = 4096
    if content_max_chars is not None:
        try:
            max_chars = max(max_chars, max(128, int(content_max_chars)))
        except (TypeError, ValueError):
            pass
    content = str(content or '')[:max_chars]
    now = time.time()
    values = {
        'record_key': _recordKey(context, direction, message_id, message_index, event_id),
        **context,
        'direction': str(direction),
        'message_id': _clean(message_id),
        'message_index': _clean(message_index),
        'reference_message_id': _clean(reference_message_id),
        'reference_index': _clean(reference_index),
        'event_id': _clean(event_id),
        'sender_id': _clean(sender_id),
        'sender_name': _clean(sender_name),
        'content': content,
        'created_at': now,
        'updated_at': now,
    }
    try:
        with _lock:
            conn = _connect()
            try:
                _cleanup(conn)
                conn.execute('''
                    INSERT INTO messages (
                        record_key, bot_hash, platform, chat_type, scope_id, direction,
                        message_id, message_index, reference_message_id, reference_index,
                        event_id, sender_id, sender_name, content, created_at, updated_at
                    ) VALUES (
                        :record_key, :bot_hash, :platform, :chat_type, :scope_id, :direction,
                        :message_id, :message_index, :reference_message_id, :reference_index,
                        :event_id, :sender_id, :sender_name, :content, :created_at, :updated_at
                    )
                    ON CONFLICT(record_key) DO UPDATE SET
                        message_id=COALESCE(excluded.message_id, messages.message_id),
                        message_index=COALESCE(excluded.message_index, messages.message_index),
                        reference_message_id=COALESCE(
                            excluded.reference_message_id, messages.reference_message_id
                        ),
                        reference_index=COALESCE(excluded.reference_index, messages.reference_index),
                        event_id=COALESCE(excluded.event_id, messages.event_id),
                        sender_id=COALESCE(excluded.sender_id, messages.sender_id),
                        sender_name=COALESCE(excluded.sender_name, messages.sender_name),
                        content=CASE WHEN excluded.content='' THEN messages.content ELSE excluded.content END,
                        updated_at=excluded.updated_at
                ''', values)
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        OlivaAIAgent.conf.log(OlivaAIAgent.conf.gProc, 3, '消息标识注册失败: %s' % e)


def recordIncoming(plugin_event, parsed):
    sender = getattr(getattr(plugin_event, 'data', None), 'sender', {})
    sender = sender if isinstance(sender, dict) else {}
    bot_hash = eventContext(plugin_event)['bot_hash']
    forward_storage_limit = None
    if int(parsed.get('forward_count') or 0) > 0:
        forward_storage_limit = OlivaAIAgent.conf.get(
            'forward', 'storage_max_chars', default=20000,
        )
    record(
        plugin_event,
        'incoming',
        message_id=parsed.get('message_id'),
        message_index=parsed.get('msg_idx'),
        reference_message_id=parsed.get('reference_message_id'),
        reference_index=parsed.get('ref_msg_idx'),
        event_id=parsed.get('event_id'),
        sender_id=getattr(getattr(plugin_event, 'data', None), 'user_id', None),
        sender_name=sender.get('nickname') or sender.get('name'),
        content=OlivaAIAgent.contentSafety.hiddenForMemory(parsed.get('text'), bot_hash=bot_hash),
        content_max_chars=forward_storage_limit,
    )


def updateIncomingContent(plugin_event, parsed, content):
    '''媒体识别完成后，用原消息标识幂等刷新注册表正文。'''
    if not isinstance(parsed, dict) or str(content or '').strip() == '':
        return
    sender = getattr(getattr(plugin_event, 'data', None), 'sender', {})
    sender = sender if isinstance(sender, dict) else {}
    bot_hash = eventContext(plugin_event)['bot_hash']
    forward_storage_limit = None
    if int(parsed.get('forward_count') or 0) > 0:
        forward_storage_limit = OlivaAIAgent.conf.get(
            'forward', 'storage_max_chars', default=20000,
        )
    record(
        plugin_event,
        'incoming',
        message_id=parsed.get('message_id'),
        message_index=parsed.get('msg_idx'),
        reference_message_id=parsed.get('reference_message_id'),
        reference_index=parsed.get('ref_msg_idx'),
        event_id=parsed.get('event_id'),
        sender_id=getattr(getattr(plugin_event, 'data', None), 'user_id', None),
        sender_name=sender.get('nickname') or sender.get('name'),
        content=OlivaAIAgent.contentSafety.hiddenForMemory(content, bot_hash=bot_hash),
        content_max_chars=forward_storage_limit,
    )


def recordOutgoing(
    plugin_event,
    content,
    message_ids,
    reference_message_id=None,
    message_indexes=None,
):
    ids = list(dict.fromkeys(
        str(item) for item in (message_ids or []) if item not in [None, '', '-1', -1]
    ))
    indexes = list(dict.fromkeys(
        str(item) for item in (message_indexes or []) if item not in [None, '', '-1', -1]
    ))
    for position in range(max(len(ids), len(indexes))):
        record(
            plugin_event,
            'outgoing',
            message_id=ids[position] if position < len(ids) else None,
            message_index=indexes[position] if position < len(indexes) else None,
            reference_message_id=reference_message_id,
            content=content,
        )


def _find(plugin_event, message_id=None, message_index=None):
    context = eventContext(plugin_event)
    if message_id not in [None, '']:
        field = 'message_id'
        value = str(message_id)
    elif message_index not in [None, '']:
        field = 'message_index'
        value = str(message_index)
    else:
        return None
    try:
        conn = _connect()
        try:
            row = conn.execute('''
                SELECT * FROM messages
                WHERE bot_hash=? AND platform=? AND chat_type=? AND scope_id=?
                      AND %s=? AND updated_at>=?
                ORDER BY updated_at DESC LIMIT 1
            ''' % field, (
                context['bot_hash'],
                context['platform'],
                context['chat_type'],
                context['scope_id'],
                value,
                _retentionCutoff(),
            )).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    return dict(row) if row is not None else None


def getByMessageId(plugin_event, message_id):
    return _find(plugin_event, message_id=message_id)


def getByMessageIndex(plugin_event, message_index):
    return _find(plugin_event, message_index=message_index)


def normalizeReferenceId(plugin_event, reference_id, current_message_id=None, reference_index=None):
    '''补齐 Milky 会话内 seq；或用插件持久化的 QQ ref_msg_idx 还原 message_id。'''
    reference_id = _clean(reference_id)
    sdk = getattr(plugin_event, 'platform', {}).get('sdk', '')
    if reference_id is not None:
        if 'milky' in str(sdk).lower() and '|' not in reference_id:
            current_parts = str(current_message_id or '').split('|')
            if len(current_parts) == 3 and current_parts[0] in ['friend', 'group', 'temp']:
                return '%s|%s|%s' % (current_parts[0], current_parts[1], reference_id)
        return reference_id
    indexed = getByMessageIndex(plugin_event, reference_index)
    if indexed is not None and indexed.get('message_id') not in [None, '']:
        return str(indexed['message_id'])
    return None


def recent(plugin_event, limit=12, include_content=True):
    context = eventContext(plugin_event)
    try:
        conn = _connect()
        try:
            rows = conn.execute('''
                SELECT direction, message_id, message_index, reference_message_id,
                       reference_index, event_id, content
                FROM messages
                WHERE bot_hash=? AND platform=? AND chat_type=? AND scope_id=? AND updated_at>=?
                ORDER BY updated_at DESC LIMIT ?
            ''', (
                context['bot_hash'],
                context['platform'],
                context['chat_type'],
                context['scope_id'],
                _retentionCutoff(),
                max(1, int(limit)),
            )).fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    result = []
    for row in reversed(rows):
        item = {
            '方向': '机器人发送' if row['direction'] == 'outgoing' else '用户发送',
            '消息ID': row['message_id'],
            '消息索引': row['message_index'],
            '引用消息ID': row['reference_message_id'],
            '引用索引': row['reference_index'],
            '事件ID': row['event_id'],
        }
        if include_content:
            item['内容摘要'] = str(row['content'] or '')[:160]
        result.append({key: value for key, value in item.items() if value not in [None, '']})
    return result
