"""从事件中学到的成员表，以及入群申请缓存。"""

import json
import time


class Roster:
    def __init__(self, store):
        self.store = store

    def upsert_member(self, bot_hash, chat_type, chat_id, member_openid, name=None, role=None, last_seen_at=None):
        if not member_openid:
            raise ValueError('empty member_openid')
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            db.execute(
                """INSERT INTO members(member_openid,name,role,last_seen_at) VALUES(?,?,?,?)
                ON CONFLICT(member_openid) DO UPDATE SET name=COALESCE(NULLIF(excluded.name,''),members.name),
                role=COALESCE(NULLIF(excluded.role,''),members.role),last_seen_at=MAX(members.last_seen_at,excluded.last_seen_at)""",
                (str(member_openid), name, role, int(time.time() if last_seen_at is None else last_seen_at)),
            )

    def remove_member(self, bot_hash, chat_type, chat_id, member_openid):
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            return bool(db.execute('DELETE FROM members WHERE member_openid=?', (str(member_openid),)).rowcount)

    def list_members(self, bot_hash, chat_type, chat_id, query=''):
        with self.store.session(bot_hash, chat_type, chat_id) as db:
            members = [
                dict(row) for row in db.execute('SELECT * FROM members ORDER BY last_seen_at DESC, member_openid')
            ]
        words = query.casefold().split()
        return [
            row
            for row in members
            if all(word in ((row['name'] or '') + ' ' + row['member_openid']).casefold() for word in words)
        ]

    def refresh_requests(self, bot_hash, chat_id, requests, fetched_at=None, complete=True):
        """保存本次抓到的申请；只有完整刷新后，才把没再见到的待处理记录标记为已失效。"""
        fetched_at = int(time.time() if fetched_at is None else fetched_at)
        with self.store.session(bot_hash, 'qq_group', chat_id) as db:
            ids = set()
            for request in requests:
                request_id = str(request.get('join_request_id') or '')
                member_id = str(request.get('member_openid') or '')
                if not request_id or not member_id:
                    raise ValueError('join request requires join_request_id and member_openid')
                ids.add(request_id)
                verify = request.get('verify_json')
                if verify is not None and not isinstance(verify, str):
                    verify = json.dumps(verify, ensure_ascii=False, separators=(',', ':'))
                db.execute(
                    """INSERT INTO join_requests(join_request_id,member_openid,username,apply_at,apply_source,
                    invited_by,bot,risk_tips,verify_json,status,fetched_at)
                    VALUES(?,?,?,?,?,?,?,?,?,'pending',?) ON CONFLICT(join_request_id) DO UPDATE SET
                    member_openid=excluded.member_openid,username=excluded.username,apply_at=excluded.apply_at,
                    apply_source=excluded.apply_source,invited_by=excluded.invited_by,bot=excluded.bot,
                    risk_tips=excluded.risk_tips,verify_json=excluded.verify_json,status='pending',fetched_at=excluded.fetched_at""",
                    (
                        request_id,
                        member_id,
                        request.get('username'),
                        request.get('apply_at'),
                        request.get('apply_source'),
                        request.get('invited_by'),
                        int(bool(request.get('bot'))),
                        request.get('risk_tips'),
                        verify,
                        fetched_at,
                    ),
                )
            if complete:
                # 不能靠时间戳比较：两次刷新可能落在同一秒内。
                for row in db.execute("SELECT join_request_id FROM join_requests WHERE status='pending'").fetchall():
                    if row['join_request_id'] not in ids:
                        db.execute(
                            "UPDATE join_requests SET status='gone' WHERE join_request_id=?", (row['join_request_id'],)
                        )
        return len(ids)

    def list_requests(self, bot_hash, chat_id, status='pending', limit=50, offset=0):
        with self.store.session(bot_hash, 'qq_group', chat_id) as db:
            sql = 'SELECT * FROM join_requests'
            args = []
            if status is not None:
                sql += ' WHERE status=?'
                args.append(status)
            sql += ' ORDER BY apply_at DESC, join_request_id LIMIT ? OFFSET ?'
            args.extend((max(1, min(int(limit), 2000)), max(0, int(offset))))
            return [dict(row) for row in db.execute(sql, args)]

    def set_request_status(self, bot_hash, chat_id, join_request_id, status):
        if status not in ('pending', 'approved', 'declined', 'gone'):
            raise ValueError('invalid request status')
        with self.store.session(bot_hash, 'qq_group', chat_id) as db:
            return bool(
                db.execute(
                    'UPDATE join_requests SET status=? WHERE join_request_id=?', (status, str(join_request_id))
                ).rowcount
            )
