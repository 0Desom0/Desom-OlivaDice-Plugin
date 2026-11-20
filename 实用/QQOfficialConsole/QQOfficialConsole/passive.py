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

    def add(self, bot_hash, chat_type, chat_id, id_type, id_value, source_event=None,
            created_at=None, used_count=None, max_count=None, expire_at=None):
        if not id_value:
            raise ValueError('empty token')
        token = {
            'id_type': id_type,
            'id_value': id_value,
            'source_event': source_event,
            'created_at': int(created_at if created_at is not None else time.time()),
        }
        if used_count is not None:
            token['used_count'] = int(used_count)
        if max_count is not None:
            token['max_count'] = int(max_count)
        if expire_at is not None:
            token['expire_at'] = int(expire_at)
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            self.store._insert_token(db, chat_type, token)

    def import_from(self, bot_hash, chat_type, chat_id, source_chat_type, source_chat_id,
                    id_type, id_value, created_at=None):
        """把同一条凭据从别的会话复制过来（群消息私聊回复）。

        平台 2026-11-17 起群消息的 msg_id 也能用于发单聊消息，且与群内回复共用
        次数上限。复制时要连已用次数和到期时间一起带过来，否则私聊这边从 0 开始数，
        会比平台允许的多发。
        """
        with self.store.session(bot_hash, source_chat_type, source_chat_id) as db:
            row = db.execute(
                'SELECT * FROM passive_tokens WHERE id_type=? AND id_value=?',
                (id_type, str(id_value)),
            ).fetchone()
            source = dict(row) if row else None
        if source is None:
            self.add(
                bot_hash,
                chat_type,
                chat_id,
                id_type,
                id_value,
                'GROUP_MESSAGE_CREATE_SHARED',
                created_at=created_at,
            )
            return
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            db.execute(
                'DELETE FROM passive_tokens WHERE id_type=? AND id_value=?',
                (id_type, str(id_value)),
            )
        self.add(
            bot_hash,
            chat_type,
            chat_id,
            id_type,
            id_value,
            'GROUP_MESSAGE_CREATE_SHARED',
            created_at=source['created_at'],
            used_count=source['used_count'],
            max_count=source['max_count'],
            expire_at=source['expire_at'],
        )

    def candidates(self, bot_hash, chat_type, chat_id, now=None, limit=None):
        now = int(time.time() if now is None else now)
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            self.store._prune_tokens(db)
            rows = db.execute(
                'SELECT * FROM passive_tokens WHERE expire_at>? '
                'ORDER BY expire_at ASC, used_count ASC, created_at ASC',
                (now,),
            ).fetchall()
            cap = None if limit is None else int(limit)
            with self._guard:
                self._prune_used()
                return [
                    dict(row)
                    for row in rows
                    if row['used_count'] < (row['max_count'] if cap is None else min(row['max_count'], cap))
                    and (
                        row['used_count'] == 0
                        or self._key(bot_hash, chat_type, chat_id, row['id_type'], row['id_value'])
                        in self._used_here
                    )
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

    def status(self, bot_hash, chat_type, chat_id, now=None, limit=None):
        now = int(time.time() if now is None else now)
        rows = self.candidates(bot_hash, chat_type, chat_id, now, limit=limit)
        if not rows:
            return None
        token = dict(rows[0], remaining_seconds=max(0, rows[0]['expire_at'] - now))
        # 页面按 max_count 显示「被动 x/y」，这里给按群内角色收窄后的真实上限。
        if limit is not None:
            token['max_count'] = min(int(token['max_count']), int(limit))
        return token
