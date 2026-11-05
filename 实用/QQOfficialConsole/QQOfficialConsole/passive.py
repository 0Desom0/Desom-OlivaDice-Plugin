"""被动回复凭据的持久化，以及按会话串行的发送锁。"""

import threading
import time
from contextlib import contextmanager


class PassivePool:
    def __init__(self, store):
        self.store = store
        self._guard = threading.Lock()
        self._locks = {}
        # SDK 的 sequence 状态只在进程内有效。即便库里的计数很低，也绝不复用
        # 本凭据池创建之前就已经被消费过的凭据。
        self._used_here = {}

    def _prune_used(self):
        now = time.time()
        for key, expiry in list(self._used_here.items()):
            if expiry <= now:
                del self._used_here[key]

    @staticmethod
    def _key(bot_hash, chat_type, chat_id, id_type=None, id_value=None):
        return (str(bot_hash), chat_type, str(chat_id), id_type, str(id_value) if id_value is not None else None)

    @contextmanager
    def send_lock(self, bot_hash, chat_type, chat_id):
        key = self._key(bot_hash, chat_type, chat_id)[:3]
        with self._guard:
            entry = self._locks.get(key)
            if entry is None:
                entry = [threading.RLock(), 0]
                self._locks[key] = entry
            entry[1] += 1  # 把等待者也算进去，避免还有人在等锁时把条目替换掉。
        try:
            with entry[0]:
                yield
        finally:
            with self._guard:
                entry[1] -= 1
                if entry[1] == 0:
                    del self._locks[key]

    def add(self, bot_hash, chat_type, chat_id, id_type, id_value, source_event=None, created_at=None):
        if not id_value:
            raise ValueError('empty token')
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            self.store._insert_token(
                db,
                chat_type,
                {
                    'id_type': id_type,
                    'id_value': id_value,
                    'source_event': source_event,
                    'created_at': int(created_at if created_at is not None else time.time()),
                },
            )

    def candidates(self, bot_hash, chat_type, chat_id, now=None):
        now = int(time.time() if now is None else now)
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            self.store._prune_tokens(db)
            rows = db.execute(
                'SELECT * FROM passive_tokens WHERE expire_at>? AND used_count<max_count '
                'ORDER BY expire_at ASC, used_count ASC, created_at ASC',
                (now,),
            ).fetchall()
            with self._guard:
                self._prune_used()
                return [
                    dict(row)
                    for row in rows
                    if row['used_count'] == 0
                    or self._key(bot_hash, chat_type, chat_id, row['id_type'], row['id_value']) in self._used_here
                ]

    def mark_used(self, bot_hash, chat_type, chat_id, id_type, id_value):
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            changed = db.execute(
                'UPDATE passive_tokens SET used_count=used_count+1 '
                'WHERE id_type=? AND id_value=? AND used_count<max_count',
                (id_type, str(id_value)),
            ).rowcount
            if changed:
                row = db.execute(
                    'SELECT expire_at,used_count,max_count FROM passive_tokens WHERE id_type=? AND id_value=?',
                    (id_type, str(id_value)),
                ).fetchone()
                with self._guard:
                    self._prune_used()
                    key = self._key(bot_hash, chat_type, chat_id, id_type, id_value)
                    if row['used_count'] < row['max_count'] and row['expire_at'] > time.time():
                        self._used_here[key] = row['expire_at']
                    else:
                        self._used_here.pop(key, None)
            return bool(changed)

    def invalidate(self, bot_hash, chat_type, chat_id, id_type, id_value):
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            changed = db.execute(
                'UPDATE passive_tokens SET used_count=max_count WHERE id_type=? AND id_value=?',
                (id_type, str(id_value)),
            ).rowcount
            with self._guard:
                self._prune_used()
                self._used_here.pop(self._key(bot_hash, chat_type, chat_id, id_type, id_value), None)
            return bool(changed)

    def status(self, bot_hash, chat_type, chat_id, now=None):
        now = int(time.time() if now is None else now)
        rows = self.candidates(bot_hash, chat_type, chat_id, now)
        if not rows:
            return None
        return dict(rows[0], remaining_seconds=max(0, rows[0]['expire_at'] - now))
