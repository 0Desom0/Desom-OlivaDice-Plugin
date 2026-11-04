"""SQLite persistence for the console. All database access is serialized per Store."""

import hashlib
import json
import re
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path


def safe_id(value):
    value = str(value)
    if value and re.fullmatch(r'[A-Za-z0-9_-]+', value) and value not in ('.', '..'):
        return value
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _json(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(',', ':'))


_META = """
CREATE TABLE IF NOT EXISTS chats (
 chat_type TEXT NOT NULL, chat_id TEXT NOT NULL, safe_id TEXT NOT NULL,
 remark TEXT, display_name TEXT, bot_openid TEXT, self_role TEXT, allow_proactive INTEGER,
 role_updated_at INTEGER, last_message_at INTEGER, last_preview TEXT,
 unread INTEGER NOT NULL DEFAULT 0, mention_unread INTEGER NOT NULL DEFAULT 0,
 mention_version INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0,
 pinned INTEGER NOT NULL DEFAULT 0, left_group INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL,
 PRIMARY KEY(chat_type, chat_id));
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS group_info_jobs (
 group_openid TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending',
 enqueued_at INTEGER NOT NULL, next_at INTEGER NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0, error_code INTEGER, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS group_info_jobs_fifo ON group_info_jobs(status, enqueued_at);
"""
_CHAT = """
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, direction TEXT NOT NULL,
 platform_message_id TEXT, ref_idx TEXT, reply_to TEXT, sender_id TEXT,
 sender_name TEXT, msg_kind TEXT NOT NULL, content_text TEXT, content_json TEXT,
 created_at INTEGER NOT NULL, send_channel TEXT, error_code INTEGER, keyword TEXT,
 recalled INTEGER NOT NULL DEFAULT 0, raw_event_json TEXT, is_unread INTEGER NOT NULL DEFAULT 0,
 is_mention INTEGER NOT NULL DEFAULT 0, mention_unread INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS messages_created ON messages(created_at);
CREATE INDEX IF NOT EXISTS messages_platform ON messages(platform_message_id);
CREATE UNIQUE INDEX IF NOT EXISTS messages_incoming_unique ON messages(platform_message_id)
 WHERE direction='in' AND platform_message_id IS NOT NULL AND platform_message_id<>'';
CREATE TABLE IF NOT EXISTS session_state (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS message_changes (seq INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS messages_record_change AFTER UPDATE OF
 platform_message_id,ref_idx,reply_to,sender_id,sender_name,msg_kind,content_text,content_json,
 send_channel,error_code,keyword,recalled,raw_event_json,is_mention,mention_unread ON messages BEGIN
 INSERT INTO message_changes(message_id) VALUES (NEW.id);
 DELETE FROM message_changes WHERE seq <= (SELECT seq FROM sqlite_sequence WHERE name='message_changes') - 10000;
END;
CREATE TABLE IF NOT EXISTS members (member_openid TEXT PRIMARY KEY, name TEXT, role TEXT,
 last_seen_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS passive_tokens (id_type TEXT NOT NULL, id_value TEXT NOT NULL,
 expire_at INTEGER NOT NULL, used_count INTEGER NOT NULL DEFAULT 0, max_count INTEGER NOT NULL,
 created_at INTEGER NOT NULL, source_event TEXT, PRIMARY KEY(id_type,id_value));
CREATE INDEX IF NOT EXISTS passive_tokens_expiry ON passive_tokens(expire_at, used_count, created_at);
CREATE TABLE IF NOT EXISTS join_requests (join_request_id TEXT PRIMARY KEY, member_openid TEXT NOT NULL,
 username TEXT, apply_at INTEGER, apply_source TEXT, invited_by TEXT, bot INTEGER NOT NULL DEFAULT 0,
 risk_tips TEXT, verify_json TEXT, status TEXT NOT NULL DEFAULT 'pending', fetched_at INTEGER NOT NULL);
"""
_MESSAGE_FIELDS = (
    'direction',
    'platform_message_id',
    'ref_idx',
    'reply_to',
    'sender_id',
    'sender_name',
    'msg_kind',
    'content_text',
    'content_json',
    'created_at',
    'send_channel',
    'error_code',
    'keyword',
    'recalled',
    'raw_event_json',
    'is_unread',
    'is_mention',
    'mention_unread',
)
_CHAT_FIELDS = frozenset(
    (
        'remark',
        'display_name',
        'bot_openid',
        'self_role',
        'allow_proactive',
        'role_updated_at',
        'last_message_at',
        'last_preview',
        'unread',
        'hidden',
        'pinned',
        'left_group',
    )
)


class Store:
    def __init__(self, root='plugin/data/QQOfficialConsole', max_open=8, idle_seconds=60):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_open = max(1, int(max_open))
        self.idle_seconds = idle_seconds
        self.lock = threading.RLock()
        self._sessions = OrderedDict()
        self._meta = OrderedDict()
        self._global = self._open(
            self.root / 'global.sqlite3',
            'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);',
        )
        self._stop = threading.Event()
        self._reaper = threading.Thread(target=self._reap_idle, name='QQOfficialConsole-db-reaper', daemon=True)
        self._reaper.start()

    @staticmethod
    def _open(path, schema):
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript(schema)
        return db

    def _bot_path(self, bot_hash):
        return self.root / safe_id(bot_hash)

    def _get_meta(self, bot_hash):
        key = str(bot_hash)
        now = time.monotonic()
        self._expire_meta(now, exclude=key)
        if key in self._meta:
            db, _ = self._meta.pop(key)
        else:
            db = self._open(self._bot_path(key) / 'meta.sqlite3', _META)
            if 'left_group' not in {row['name'] for row in db.execute('PRAGMA table_info(chats)')}:
                db.execute('ALTER TABLE chats ADD COLUMN left_group INTEGER NOT NULL DEFAULT 0')
                db.commit()
            if 'bot_openid' not in {row['name'] for row in db.execute('PRAGMA table_info(chats)')}:
                db.execute('ALTER TABLE chats ADD COLUMN bot_openid TEXT')
                db.commit()
            if 'mention_unread' not in {row['name'] for row in db.execute('PRAGMA table_info(chats)')}:
                db.execute('ALTER TABLE chats ADD COLUMN mention_unread INTEGER NOT NULL DEFAULT 0')
                db.commit()
            if 'mention_version' not in {row['name'] for row in db.execute('PRAGMA table_info(chats)')}:
                db.execute('ALTER TABLE chats ADD COLUMN mention_version INTEGER NOT NULL DEFAULT 0')
                db.commit()
        self._meta[key] = (db, now)
        while len(self._meta) > self.max_open:
            _, (old, _) = self._meta.popitem(last=False)
            old.close()
        return db

    def _expire_meta(self, now, exclude=None):
        for key, (db, touched) in list(self._meta.items()):
            if key != exclude and now - touched >= self.idle_seconds:
                db.close()
                del self._meta[key]

    def _get_session(self, bot_hash, chat_type, chat_id):
        if chat_type not in ('qq_group', 'qq_private'):
            raise ValueError('invalid chat_type')
        key = (str(bot_hash), chat_type, str(chat_id))
        now = time.monotonic()
        self._expire(now, exclude=key)
        if key in self._sessions:
            db, _ = self._sessions.pop(key)
        else:
            path = self._bot_path(bot_hash) / 'msg' / chat_type / (safe_id(chat_id) + '.sqlite3')
            db = self._open(path, _CHAT)
            columns = {row['name'] for row in db.execute('PRAGMA table_info(messages)')}
            if 'is_unread' not in columns:
                db.execute('ALTER TABLE messages ADD COLUMN is_unread INTEGER NOT NULL DEFAULT 0')
                meta = self._get_meta(bot_hash)
                row = meta.execute(
                    'SELECT unread FROM chats WHERE chat_type=? AND chat_id=?', (chat_type, str(chat_id))
                ).fetchone()
                count = max(0, int(row['unread'])) if row else 0
                db.execute(
                    "UPDATE messages SET is_unread=1 WHERE id IN "
                    "(SELECT id FROM messages WHERE direction='in' ORDER BY id DESC LIMIT ?)",
                    (count,),
                )
                db.commit()
            if 'is_mention' not in columns:
                db.execute('ALTER TABLE messages ADD COLUMN is_mention INTEGER NOT NULL DEFAULT 0')
            if 'mention_unread' not in columns:
                db.execute('ALTER TABLE messages ADD COLUMN mention_unread INTEGER NOT NULL DEFAULT 0')
            db.execute('CREATE INDEX IF NOT EXISTS messages_mention_unread ON messages(mention_unread, id)')
            db.execute('DROP TRIGGER IF EXISTS messages_record_change')
            db.executescript('''CREATE TRIGGER messages_record_change AFTER UPDATE OF
                platform_message_id,ref_idx,reply_to,sender_id,sender_name,msg_kind,content_text,content_json,
                send_channel,error_code,keyword,recalled,raw_event_json,is_mention,mention_unread ON messages BEGIN
                INSERT INTO message_changes(message_id) VALUES (NEW.id);
                DELETE FROM message_changes WHERE seq <=
                    (SELECT seq FROM sqlite_sequence WHERE name='message_changes') - 10000;
                END;''')
        self._sessions[key] = (db, now)
        while len(self._sessions) > self.max_open:
            _, (old, _) = self._sessions.popitem(last=False)
            old.close()
        return db

    def _expire(self, now, exclude=None):
        for key, (db, touched) in list(self._sessions.items()):
            if key != exclude and now - touched >= self.idle_seconds:
                db.close()
                del self._sessions[key]

    @contextmanager
    def session(self, bot_hash, chat_type, chat_id):
        """Hold the store lock and a transaction for a session database."""
        with self.lock:
            db = self._get_session(bot_hash, chat_type, chat_id)
            with db:
                yield db

    @contextmanager
    def meta(self, bot_hash):
        with self.lock:
            db = self._get_meta(bot_hash)
            with db:
                yield db

    @contextmanager
    def _settings_db(self, bot_hash):
        if bot_hash is None:
            with self.lock, self._global:
                yield self._global
        else:
            with self.meta(bot_hash) as db:
                yield db

    def close_idle(self):
        with self.lock:
            self._expire(time.monotonic())
            self._expire_meta(time.monotonic())

    def _reap_idle(self):
        while not self._stop.wait(max(0.1, min(10, self.idle_seconds))):
            self.close_idle()

    def save(self):
        with self.lock:
            for db in [
                self._global,
                *(item[0] for item in self._meta.values()),
                *(item[0] for item in self._sessions.values()),
            ]:
                db.commit()
                db.execute('PRAGMA wal_checkpoint(PASSIVE)')
            self.close_idle()

    def close(self):
        self._stop.set()
        self._reaper.join()
        with self.lock:
            for db in [
                self._global,
                *(item[0] for item in self._meta.values()),
                *(item[0] for item in self._sessions.values()),
            ]:
                db.close()
            self._sessions.clear()
            self._meta.clear()

    def get_settings(self, bot_hash=None):
        defaults = (
            {'send_key': 'enter_send', 'last_bot_hash': '', 'poll_interval_ms': 1000, 'image_retention_days': 30}
            if bot_hash is None
            else {
                'view_limit_enabled': False,
                'view_limit_mode': 'count',
                'view_limit_count': 100,
                'view_limit_days': 30,
            }
        )
        with self._settings_db(bot_hash) as db:
            for row in db.execute('SELECT key,value FROM settings'):
                try:
                    defaults[row['key']] = json.loads(row['value'])
                except (ValueError, TypeError):
                    defaults[row['key']] = row['value']
        return defaults

    def set_settings(self, values, bot_hash=None):
        with self._settings_db(bot_hash) as db:
            db.executemany(
                'INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                [(str(k), _json(v)) for k, v in values.items()],
            )

    def upsert_chat(self, bot_hash, chat_type, chat_id, **fields):
        if chat_type not in ('qq_group', 'qq_private') or not str(chat_id):
            raise ValueError('invalid chat')
        if set(fields) - _CHAT_FIELDS:
            raise ValueError('invalid chat fields')
        now = int(time.time())
        with self.meta(bot_hash) as db:
            db.execute(
                'INSERT OR IGNORE INTO chats(chat_type,chat_id,safe_id,updated_at) VALUES(?,?,?,?)',
                (chat_type, str(chat_id), safe_id(chat_id), now),
            )
            if fields:
                sql = ','.join(k + '=?' for k in fields)
                db.execute(
                    'UPDATE chats SET ' + sql + ',updated_at=? WHERE chat_type=? AND chat_id=?',
                    (*fields.values(), now, chat_type, str(chat_id)),
                )
            return dict(
                db.execute('SELECT * FROM chats WHERE chat_type=? AND chat_id=?', (chat_type, str(chat_id))).fetchone()
            )

    def get_chat(self, bot_hash, chat_type, chat_id):
        with self.meta(bot_hash) as db:
            row = db.execute(
                'SELECT * FROM chats WHERE chat_type=? AND chat_id=?', (chat_type, str(chat_id))
            ).fetchone()
            return dict(row) if row else None

    def list_chats(self, bot_hash, include_hidden=False):
        with self.meta(bot_hash) as db:
            rows = db.execute(
                'SELECT * FROM chats '
                + ('' if include_hidden else 'WHERE hidden=0 ')
                + 'ORDER BY pinned DESC, COALESCE(last_message_at,0) DESC, updated_at DESC'
            ).fetchall()
            return [dict(row) for row in rows]

    def enqueue_group_info(self, bot_hash, group_openid, enqueued_at=None):
        """把群名获取任务按入群时间排队；重复入队保持原顺序。"""
        enqueued_at = int(time.time() if enqueued_at is None else enqueued_at)
        with self.meta(bot_hash) as db:
            db.execute(
                "INSERT INTO group_info_jobs(group_openid,status,enqueued_at,updated_at) "
                "VALUES(?,'pending',?,?) "
                "ON CONFLICT(group_openid) DO UPDATE SET "
                "status=CASE WHEN group_info_jobs.status IN ('done','failed') THEN 'pending' "
                "ELSE group_info_jobs.status END, "
                "enqueued_at=CASE WHEN group_info_jobs.status IN ('done','failed') THEN excluded.enqueued_at "
                "ELSE group_info_jobs.enqueued_at END, "
                "next_at=CASE WHEN group_info_jobs.status IN ('done','failed') THEN 0 "
                "ELSE group_info_jobs.next_at END, "
                "attempts=CASE WHEN group_info_jobs.status IN ('done','failed') THEN 0 "
                "ELSE group_info_jobs.attempts END, "
                "updated_at=excluded.updated_at",
                (str(group_openid), enqueued_at, enqueued_at),
            )

    def claim_group_info_jobs(self, bot_hash, limit=1, now=None):
        """严格 FIFO：队首仍在冷却时不越过它；一次只领取一条。"""
        now = int(time.time() if now is None else now)
        with self.meta(bot_hash) as db:
            row = db.execute(
                "SELECT group_openid,next_at FROM group_info_jobs "
                "WHERE status='pending' ORDER BY enqueued_at, rowid LIMIT 1"
            ).fetchone()
            if not row or row['next_at'] > now:
                return []
            group_openid = row['group_openid']
            db.execute("UPDATE group_info_jobs SET status='running',updated_at=? WHERE group_openid=?",
                       (now, group_openid))
            return [group_openid]

    def recover_group_info_jobs(self, bot_hash):
        """加载时恢复上次进程异常中断的任务。"""
        with self.meta(bot_hash) as db:
            db.execute("UPDATE group_info_jobs SET status='pending' WHERE status='running'")

    def complete_group_info_job(self, bot_hash, group_openid, now=None):
        now = int(time.time() if now is None else now)
        with self.meta(bot_hash) as db:
            db.execute(
                "UPDATE group_info_jobs SET status='done', error_code=NULL, updated_at=? WHERE group_openid=?",
                (now, str(group_openid)),
            )

    def requeue_group_info_job(self, bot_hash, group_openid, delay_seconds, now=None, max_attempts=5):
        """失败重试：冷却后重新排队；超过次数上限标记为 failed。"""
        now = int(time.time() if now is None else now)
        with self.meta(bot_hash) as db:
            row = db.execute(
                'SELECT attempts FROM group_info_jobs WHERE group_openid=?', (str(group_openid),)
            ).fetchone()
            attempts = int(row['attempts']) + 1 if row else 1
            status = 'failed' if attempts >= max_attempts else 'pending'
            db.execute(
                'UPDATE group_info_jobs SET status=?, attempts=?, next_at=?, updated_at=? WHERE group_openid=?',
                (status, attempts, now + max(0, int(delay_seconds)) if status == 'pending' else now, now,
                 str(group_openid)),
            )

    def fail_group_info_job(self, bot_hash, group_openid, error_code=None, now=None):
        """永久性失败（群已注销、无权限等）：直接标记 failed，不再重试。"""
        now = int(time.time() if now is None else now)
        with self.meta(bot_hash) as db:
            db.execute(
                'UPDATE group_info_jobs SET status=\'failed\', error_code=?, updated_at=? WHERE group_openid=?',
                (error_code, now, str(group_openid)),
            )

    def group_info_job(self, bot_hash, group_openid):
        with self.meta(bot_hash) as db:
            row = db.execute(
                'SELECT * FROM group_info_jobs WHERE group_openid=?', (str(group_openid),)
            ).fetchone()
            return dict(row) if row else None

    def group_info_status(self, bot_hash):
        """未完成的任务映射 {group_openid: 'queued'|'running'|'failed'}。"""
        with self.meta(bot_hash) as db:
            return {
                row['group_openid']: ('queued' if row['status'] == 'pending' else row['status'])
                for row in db.execute("SELECT group_openid,status FROM group_info_jobs WHERE status<>'done'")
            }

    def list_group_info_targets(self, bot_hash):
        """回填候选：有会话记录、未离群、还没有群名的群。"""
        with self.meta(bot_hash) as db:
            return [
                row['chat_id'] for row in db.execute(
                    "SELECT chat_id FROM chats WHERE chat_type='qq_group' AND left_group=0 "
                    "AND (display_name IS NULL OR display_name='') ORDER BY updated_at"
                )
            ]

    def unread_total(self, bot_hash):
        with self.meta(bot_hash) as db:
            return db.execute('SELECT COALESCE(SUM(unread),0) FROM chats').fetchone()[0]

    def mention_total(self, bot_hash):
        with self.meta(bot_hash) as db:
            return db.execute('SELECT COALESCE(SUM(mention_unread),0) FROM chats').fetchone()[0]

    def mention_target(self, bot_hash, chat_type, chat_id):
        with self.session(bot_hash, chat_type, chat_id) as db:
            row = db.execute('SELECT id FROM messages WHERE mention_unread=1 ORDER BY id LIMIT 1').fetchone()
            if row is None:
                return {'message_id': None, 'newer_count': 0}
            message_id = row['id']
            count = db.execute('SELECT COUNT(*) FROM messages WHERE id>?', (message_id,)).fetchone()[0]
            return {'message_id': message_id, 'newer_count': count}

    def _mark_read(self, bot_hash, chat_type, chat_id, predicate, args):
        with self.lock:
            with self.session(bot_hash, chat_type, chat_id) as db:
                db.execute('UPDATE messages SET is_unread=0,mention_unread=0 WHERE '
                           '(is_unread=1 OR mention_unread=1) AND ' + predicate, args)
                remaining = db.execute('SELECT COUNT(*) FROM messages WHERE is_unread=1').fetchone()[0]
                mentions = db.execute('SELECT COUNT(*) FROM messages WHERE mention_unread=1').fetchone()[0]
            with self.meta(bot_hash) as db:
                db.execute(
                    'UPDATE chats SET unread=?,mention_unread=? WHERE chat_type=? AND chat_id=?',
                    (remaining, mentions, chat_type, str(chat_id))
                )
            return remaining

    def mark_read(self, bot_hash, chat_type, chat_id, through_id):
        return self._mark_read(bot_hash, chat_type, chat_id, 'id<=?', (int(through_id),))

    def mark_read_all(self, bot_hash, chat_type, chat_id):
        """点进会话时清掉全部未读和 @ 提示。"""
        return self._mark_read(bot_hash, chat_type, chat_id, '1', ())

    def mark_read_visible(self, bot_hash, chat_type, chat_id, ids):
        ids = list(dict.fromkeys(int(value) for value in ids))
        if len(ids) > 500:
            raise ValueError('at most 500 message ids')
        if not ids:
            return self._mark_read(bot_hash, chat_type, chat_id, '0', ())
        return self._mark_read(bot_hash, chat_type, chat_id, 'id IN (' + ','.join('?' for _ in ids) + ')', ids)

    def add_message(self, bot_hash, chat_type, chat_id, message, member=None, token=None, unread=True):
        """Insert a message, upgrading duplicate inbound messages when an explicit mention arrives."""
        data = dict(message)
        data.setdefault('created_at', int(time.time()))
        data.setdefault('msg_kind', 'unknown')
        for key in ('content_json', 'raw_event_json'):
            if data.get(key) is not None:
                data[key] = _json(data[key])
        if data.get('raw_event_json'):
            data['raw_event_json'] = data['raw_event_json'][:16384]
        data['is_unread'] = int(bool(unread and data['direction'] == 'in'))
        data['is_mention'] = int(bool(data.get('is_mention') and data['direction'] == 'in'))
        data['mention_unread'] = data['is_mention'] * data['is_unread']
        fields = [k for k in _MESSAGE_FIELDS if k in data]
        with self.lock:
            with self.session(bot_hash, chat_type, chat_id) as db:
                sql = (
                    'INSERT OR IGNORE INTO messages('
                    + ','.join(fields)
                    + ') VALUES('
                    + ','.join('?' for _ in fields)
                    + ')'
                )
                cursor = db.execute(sql, [data[k] for k in fields])
                if not cursor.rowcount:
                    if data['is_mention'] and data.get('platform_message_id'):
                        previous = db.execute(
                            "SELECT is_unread FROM messages WHERE direction='in' AND platform_message_id=? "
                            "AND is_mention=0", (data['platform_message_id'],),
                        ).fetchone()
                        if previous:
                            db.execute(
                                "UPDATE messages SET is_mention=1,mention_unread=is_unread "
                                "WHERE direction='in' AND platform_message_id=? AND is_mention=0",
                                (data['platform_message_id'],),
                            )
                            if previous['is_unread']:
                                with self.meta(bot_hash) as meta:
                                    meta.execute(
                                        'UPDATE chats SET mention_unread=mention_unread+1, '
                                        'mention_version=mention_version+1 WHERE chat_type=? AND chat_id=?',
                                        (chat_type, str(chat_id)),
                                    )
                    return None
                local_id = cursor.lastrowid
                if member and member.get('member_openid'):
                    db.execute(
                        """INSERT INTO members(member_openid,name,role,last_seen_at) VALUES(?,?,?,?)
                        ON CONFLICT(member_openid) DO UPDATE SET name=COALESCE(NULLIF(excluded.name,''),members.name),
                        role=COALESCE(NULLIF(excluded.role,''),members.role),last_seen_at=MAX(members.last_seen_at,excluded.last_seen_at)""",
                        (
                            member['member_openid'],
                            member.get('name'),
                            member.get('role'),
                            member.get('last_seen_at', data['created_at']),
                        ),
                    )
                if token and token.get('id_value'):
                    self._insert_token(db, chat_type, token, data['created_at'])
            self.upsert_chat(bot_hash, chat_type, chat_id)
            with self.meta(bot_hash) as db:
                preview = str(
                    data.get('content_text')
                    or (
                        '[图片]'
                        if data.get('msg_kind') == 'media'
                        else '[卡片]'
                        if data.get('msg_kind') == 'card'
                        else ''
                    )
                )[:200]
                db.execute(
                    """UPDATE chats SET last_preview=CASE WHEN last_message_at IS NULL OR last_message_at<=?
                    THEN ? ELSE last_preview END, last_message_at=MAX(COALESCE(last_message_at,0),?),
                    unread=unread+?, mention_unread=mention_unread+?, mention_version=mention_version+?,
                    hidden=CASE WHEN ? THEN 0 ELSE hidden END, updated_at=?
                    WHERE chat_type=? AND chat_id=?""",
                    (
                        data['created_at'],
                        preview,
                        data['created_at'],
                        int(bool(unread and data['direction'] == 'in')),
                        data['mention_unread'],
                        data['mention_unread'],
                        int(data['direction'] == 'in'),
                        int(time.time()),
                        chat_type,
                        str(chat_id),
                    ),
                )
            return local_id

    @staticmethod
    def _prune_tokens(db):
        db.execute(
            'DELETE FROM passive_tokens WHERE rowid IN '
            '(SELECT rowid FROM passive_tokens WHERE expire_at<=? ORDER BY expire_at LIMIT 64)',
            (int(time.time()),),
        )

    @staticmethod
    def _insert_token(db, chat_type, token, created_at=None):
        created_at = int(token.get('created_at', created_at or time.time()))
        ttl, maximum = (300, 5) if chat_type == 'qq_group' else (3600, 4)
        if token['id_type'] not in ('msg_id', 'event_id'):
            raise ValueError('invalid token type')
        Store._prune_tokens(db)
        db.execute(
            'INSERT OR IGNORE INTO passive_tokens(id_type,id_value,expire_at,used_count,max_count,created_at,'
            'source_event) VALUES(?,?,?,?,?,?,?)',
            (
                token['id_type'],
                str(token['id_value']),
                int(token.get('expire_at', created_at + ttl)),
                int(token.get('used_count', 0)),
                int(token.get('max_count', maximum)),
                created_at,
                token.get('source_event'),
            ),
        )

    def get_messages_by_ids(self, bot_hash, chat_type, chat_id, ids):
        ids = list(dict.fromkeys(int(value) for value in ids))
        if len(ids) > 500:
            raise ValueError('at most 500 message ids')
        if not ids:
            return []
        with self.session(bot_hash, chat_type, chat_id) as db:
            return [
                dict(row)
                for row in db.execute(
                    'SELECT * FROM messages WHERE id IN (' + ','.join('?' for _ in ids) + ') ORDER BY id', ids
                )
            ]

    def message_changes(self, bot_hash, chat_type, chat_id, after=None, limit=200):
        with self.session(bot_hash, chat_type, chat_id) as db:
            high = db.execute("SELECT seq FROM sqlite_sequence WHERE name='message_changes'").fetchone()
            high = int(high[0]) if high else 0
            if after is None:
                return {'changes': [], 'cursor': high, 'reset': False}
            after = max(0, int(after))
            first = db.execute('SELECT MIN(seq) FROM message_changes').fetchone()[0]
            if after > high or (first is not None and after < first - 1):
                return {'changes': [], 'cursor': high, 'reset': True}
            rows = db.execute(
                'SELECT c.seq, m.* FROM message_changes c JOIN messages m ON m.id=c.message_id '
                'WHERE c.seq>? ORDER BY c.seq LIMIT ?',
                (after, max(1, min(int(limit), 1000))),
            ).fetchall()
            changes = []
            for row in rows:
                message = dict(row)
                cursor = message.pop('seq')
                changes.append({'cursor': cursor, 'message': message})
            return {'changes': changes, 'cursor': changes[-1]['cursor'] if changes else after, 'reset': False}

    def update_message(self, bot_hash, chat_type, chat_id, local_id, **fields):
        allowed = set(_MESSAGE_FIELDS) - {'direction', 'created_at', 'is_unread'}
        if not fields or set(fields) - allowed:
            raise ValueError('invalid message fields')
        for key in ('content_json', 'raw_event_json'):
            if key in fields and fields[key] is not None:
                fields[key] = _json(fields[key])
        with self.session(bot_hash, chat_type, chat_id) as db:
            return db.execute(
                'UPDATE messages SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?',
                (*fields.values(), local_id),
            ).rowcount

    def recall_message(self, bot_hash, chat_type, chat_id, platform_message_id):
        with self.session(bot_hash, chat_type, chat_id) as db:
            return db.execute(
                'UPDATE messages SET recalled=1 WHERE platform_message_id=? OR ref_idx=?',
                (platform_message_id, platform_message_id),
            ).rowcount

    def get_message(self, bot_hash, chat_type, chat_id, local_id):
        with self.session(bot_hash, chat_type, chat_id) as db:
            row = db.execute('SELECT * FROM messages WHERE id=?', (local_id,)).fetchone()
            return dict(row) if row else None

    def list_messages(self, bot_hash, chat_type, chat_id, before=None, after=None, limit=50, initial=False):
        limit = max(1, min(int(limit), 1000))
        clauses, args = [], []
        if before is not None:
            clauses.append('id<?')
            args.append(int(before))
        if after is not None:
            clauses.append('id>?')
            args.append(int(after))
        if initial and before is None and after is None:
            settings = self.get_settings(bot_hash)
            if settings['view_limit_enabled']:
                if settings['view_limit_mode'] == 'days':
                    clauses.append('created_at>=?')
                    args.append(int(time.time()) - max(0, int(settings['view_limit_days'])) * 86400)
                elif settings['view_limit_mode'] == 'count':
                    limit = min(limit, max(1, int(settings['view_limit_count'])))
        order = 'ASC' if after is not None else 'DESC'
        sql = (
            'SELECT * FROM messages'
            + (' WHERE ' + ' AND '.join(clauses) if clauses else '')
            + ' ORDER BY id '
            + order
            + ' LIMIT ?'
        )
        with self.session(bot_hash, chat_type, chat_id) as db:
            rows = [dict(row) for row in db.execute(sql, (*args, limit))]
        return rows if after is not None else list(reversed(rows))

    def search_messages(
        self,
        bot_hash,
        chat_type,
        chat_id,
        query='',
        start=None,
        end=None,
        only_self=False,
        include_failed=True,
        include_recalled=True,
        limit=50,
        before=None,
        _db=None,
    ):
        clauses, args = [], []
        for word in query.split():
            word = word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("(content_text LIKE ? ESCAPE '\\' OR sender_name LIKE ? ESCAPE '\\')")
            args.extend(('%' + word + '%', '%' + word + '%'))
        for value, condition in ((start, 'created_at>=?'), (end, 'created_at<=?'), (before, 'id<?')):
            if value is not None:
                clauses.append(condition)
                args.append(int(value))
        if only_self:
            clauses.append("direction='out'")
        if not include_failed:
            clauses.append("error_code IS NULL AND (keyword IS NULL OR keyword='')")
        if not include_recalled:
            clauses.append('recalled=0')
        sql = (
            'SELECT * FROM messages'
            + (' WHERE ' + ' AND '.join(clauses) if clauses else '')
            + ' ORDER BY id DESC LIMIT ?'
        )
        if _db is not None:
            return [dict(row) for row in _db.execute(sql, (*args, max(1, min(int(limit), 1000))))]
        with self.session(bot_hash, chat_type, chat_id) as db:
            return [dict(row) for row in db.execute(sql, (*args, max(1, min(int(limit), 1000))))]

    def search_global(self, bot_hash, query, include_hidden=False):
        words = query.casefold().split()
        chats = self.list_chats(bot_hash, include_hidden)
        matching = [
            chat
            for chat in chats
            if all(
                any(word in str(chat.get(k) or '').casefold() for k in ('remark', 'display_name', 'chat_id'))
                for word in words
            )
        ]
        messages = []
        for chat in sorted(chats, key=lambda row: row['last_message_at'] or 0, reverse=True):
            remaining = 100 - len(messages)
            if not remaining:
                break
            path = self._bot_path(bot_hash) / 'msg' / chat['chat_type'] / (chat['safe_id'] + '.sqlite3')
            if not path.exists():
                continue
            with self.lock:
                db = self._open(path, _CHAT)
                try:
                    rows = self.search_messages(
                        bot_hash, chat['chat_type'], chat['chat_id'], query, limit=min(20, remaining), _db=db
                    )
                finally:
                    db.close()
            messages.extend(dict(row, chat_type=chat['chat_type'], chat_id=chat['chat_id']) for row in rows)
        return {'chats': matching, 'messages': messages}
