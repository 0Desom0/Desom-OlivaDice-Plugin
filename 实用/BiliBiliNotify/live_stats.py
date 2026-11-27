"""B 站直播统计：Socket 仅投递，后台批量写入，查询读取已提交的快照。"""

import base64
import json
import logging
import re
import sqlite3
import threading
import time
from collections import OrderedDict, deque
from contextlib import closing, contextmanager
from decimal import Decimal, InvalidOperation
from itertools import islice

from . import store

_BATCH_SIZE = 50
_BATCH_SECONDS = 5
_NAME_CACHE_SIZE = 4096
_MAX_EVENT_NUMBER = (1 << 53) - 1
_LOG = logging.getLogger(__name__)
_COMMANDS = {
    'DANMU_MSG', 'SEND_GIFT', 'SUPER_CHAT_MESSAGE', 'GUARD_BUY',
    'INTERACT_WORD', 'INTERACT_WORD_V2', 'ENTRY_EFFECT', 'LIKE_INFO_V3_CLICK',
    'LIKE_INFO_V3_UPDATE', 'ONLINE_RANK_COUNT', 'WATCHED_CHANGE',
}
_METRICS = (
    'danmu', 'text_danmu', 'emoticon_danmu', 'gold', 'gift_gold', 'gift_count', 'free_count',
    'box_count', 'box_cost', 'box_payout', 'box_profit', 'sc_gold', 'sc_count',
    'guard_gold', 'guard_count', 'guard_months', 'entry', 'follow', 'share', 'like',
)
_RANKS = {
    'danmu': 'danmu', 'gift': 'gift_gold', 'sc': 'sc_gold', 'guard': 'guard_gold',
    'box': 'box_profit', 'entry': 'entry', 'like': 'like', 'gold': 'gold',
}
_RANK_FIELDS = tuple(_RANKS.values())
_METRIC_COLUMNS = ','.join(f'{field} INTEGER NOT NULL DEFAULT 0' for field in _METRICS)
_SCHEMA = f'''
CREATE TABLE IF NOT EXISTS live_sessions (
    id INTEGER PRIMARY KEY,
    uid TEXT NOT NULL,
    room_id TEXT NOT NULL,
    uname TEXT NOT NULL,
    title TEXT NOT NULL,
    area TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('live', 'pending_end', 'ended')),
    start_at REAL NOT NULL,
    end_at REAL,
    pending_end_at REAL,
    finalize_at REAL,
    transition_at REAL NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    resumed INTEGER NOT NULL DEFAULT 0,
    fans_start INTEGER,
    fans_end INTEGER,
    {_METRIC_COLUMNS},
    online_peak INTEGER NOT NULL DEFAULT 0,
    watched_peak INTEGER NOT NULL DEFAULT 0,
    like_offset INTEGER NOT NULL DEFAULT 0,
    like_clicks INTEGER NOT NULL DEFAULT 0,
    like_base INTEGER,
    like_high INTEGER
);
CREATE INDEX IF NOT EXISTS live_sessions_room ON live_sessions (room_id, id DESC);
CREATE INDEX IF NOT EXISTS live_sessions_uid ON live_sessions (uid, id DESC);
CREATE INDEX IF NOT EXISTS live_sessions_due ON live_sessions (finalize_at) WHERE status = 'pending_end';
CREATE UNIQUE INDEX IF NOT EXISTS live_sessions_one_live ON live_sessions (room_id) WHERE status = 'live';
CREATE TABLE IF NOT EXISTS session_minutes (
    session_id INTEGER NOT NULL REFERENCES live_sessions(id),
    minute INTEGER NOT NULL,
    danmu INTEGER NOT NULL DEFAULT 0,
    gold INTEGER NOT NULL DEFAULT 0,
    online_peak INTEGER NOT NULL DEFAULT 0,
    entry INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, minute)
);
CREATE TABLE IF NOT EXISTS session_users (
    session_id INTEGER NOT NULL REFERENCES live_sessions(id),
    uid TEXT NOT NULL,
    uname TEXT NOT NULL,
    {_METRIC_COLUMNS},
    PRIMARY KEY (session_id, uid)
);
CREATE TABLE IF NOT EXISTS session_gifts (
    session_id INTEGER NOT NULL REFERENCES live_sessions(id),
    gift_id TEXT NOT NULL,
    gift_name TEXT NOT NULL,
    coin_type TEXT NOT NULL,
    box_id TEXT NOT NULL,
    box_name TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    gold INTEGER NOT NULL DEFAULT 0,
    box_cost INTEGER NOT NULL DEFAULT 0,
    box_payout INTEGER NOT NULL DEFAULT 0,
    box_profit INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, gift_id, gift_name, coin_type, box_id, box_name)
);
CREATE TABLE IF NOT EXISTS session_guards (
    session_id INTEGER NOT NULL REFERENCES live_sessions(id),
    uid TEXT NOT NULL,
    uname TEXT NOT NULL,
    guard_level INTEGER NOT NULL,
    start_time INTEGER NOT NULL,
    end_time INTEGER NOT NULL,
    months INTEGER NOT NULL,
    gold INTEGER NOT NULL,
    op_type INTEGER,
    PRIMARY KEY (session_id, uid, guard_level, start_time)
);
CREATE TABLE IF NOT EXISTS session_danmu (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES live_sessions(id),
    uid TEXT NOT NULL,
    text TEXT NOT NULL,
    happened_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS session_danmu_session ON session_danmu (session_id, id);
CREATE INDEX IF NOT EXISTS session_danmu_age ON session_danmu (happened_at);
CREATE TABLE IF NOT EXISTS user_bindings (
    platform TEXT NOT NULL,
    user_id TEXT NOT NULL,
    bili_uid TEXT NOT NULL,
    PRIMARY KEY (platform, user_id)
);
PRAGMA user_version = 1;
'''

_db_lock = threading.RLock()
_queue_lock = threading.Condition()
_buffers = {}
_worker = None
_cache_lock = threading.Lock()
_names = OrderedDict()


def _db_path():
    return store.ROOT / 'stats.db'


def _clock(now):
    return time.time() if now is None else float(now)


def _integer(value, default=0):
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (ValueError, TypeError, OverflowError):
        return default
    if (isinstance(value, float) and value != number) or not 0 <= number <= _MAX_EVENT_NUMBER:
        return default
    return number


def _uid(value):
    value = str(value) if isinstance(value, (str, int)) else ''
    return value.lstrip('0') if value.isascii() and value.isdigit() else ''


def _map(value):
    return value if isinstance(value, dict) else {}


def _seq(value):
    return value if isinstance(value, (list, tuple)) else ()


def _at(seq, index, default=None):
    return seq[index] if len(seq) > index else default


def _text(value):
    if not isinstance(value, str):
        return ''
    if _SURROGATE.search(value):
        return _SURROGATE.sub('\ufffd', value)
    return value


_SURROGATE = re.compile(r'[\ud800-\udfff]')
_ENTRY_NAME = re.compile(r'<%([^<>]+)%>')


def _name(value):
    value = _text(value).strip()
    return '' if '*' in value or '＊' in value else value


def _cache_name(path, uid, uname):
    # 参考 StarBot：使用事件里公开的昵称，避免额外调用个人空间接口。
    if uid and uname:
        key = (path, uid)
        with _cache_lock:
            _names[key] = uname
            _names.move_to_end(key)
            if len(_names) > _NAME_CACHE_SIZE:
                _names.popitem(last=False)


def cached_name(uid):
    """返回当前数据目录中进程最近见过的公开昵称，未知时为空。"""
    key = (_db_path(), _uid(uid))
    with _cache_lock:
        return _names.get(key, '')


@contextmanager
def _database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        if db.execute('PRAGMA user_version').fetchone()[0] == 0:
            db.execute('PRAGMA journal_mode = WAL')
            db.executescript('BEGIN;\n' + _SCHEMA + '\nCOMMIT;')
        yield db


def record_event(uid, room_id, msg, *, uname='', title='', area='', now=None, active=None):
    """仅入队；active=True 可在没有该房间历史时补建中途加入的场次。"""
    global _worker
    if active is False or not isinstance(msg, dict):
        return
    cmd = msg.get('cmd')
    if not isinstance(cmd, str) or cmd.partition(':')[0] not in _COMMANDS:
        return
    uid, room_id = _uid(uid), _uid(room_id)
    if not uid or not room_id:
        return
    path = _db_path()
    item = (time.monotonic(), uid, room_id, msg, uname, title, area, _clock(now), active is True)
    with _queue_lock:
        queue = _buffers.get(path)
        if queue is None:
            queue = _buffers[path] = deque()
        queue.append(item)
        if _worker is None:
            stop = threading.Event()
            thread = threading.Thread(target=_writer, args=(stop,), name='BiliBiliNotify-stats', daemon=True)
            thread.start()
            _worker = (thread, stop)
        if len(queue) in (1, _BATCH_SIZE):
            _queue_lock.notify()


def _writer(stop):
    retry_at = {}
    while not stop.is_set():
        with _queue_lock:
            now = time.monotonic()
            ready = None
            wait = None
            for path, queue in _buffers.items():
                due = now if len(queue) >= _BATCH_SIZE else queue[0][0] + _BATCH_SECONDS
                due = max(due, retry_at.get(path, 0))
                if due <= now:
                    ready = path
                    break
                delay = due - now
                wait = delay if wait is None else min(wait, delay)
            if ready is None:
                if not stop.is_set():
                    _queue_lock.wait(wait)
                continue
        try:
            with _db_lock:
                if not stop.is_set():
                    _drain(ready, limit=_BATCH_SIZE)
        except Exception:
            # 回滚后队列原样保留，显式 flush 会把同一错误交给调用方。
            if ready not in retry_at:
                _LOG.exception('直播统计批量写入失败（数据保留待重试）')
            retry_at[ready] = time.monotonic() + _BATCH_SECONDS
        else:
            retry_at.pop(ready, None)


def _drain(path, db=None, *, limit=None):
    # 调用方持有 _db_lock；SQLite 改动和提交期间接收端仍可入队。
    with _queue_lock:
        queue = _buffers.get(path)
        remaining = len(queue) if queue else 0
    if not remaining:
        return
    if limit is not None:
        remaining = min(remaining, limit)
    if db is None:
        with _database(path) as db:
            _drain(path, db, limit=remaining)
        return
    while remaining:
        size = min(_BATCH_SIZE, remaining)
        with _queue_lock:
            batch = tuple(islice(queue, size))
        with db:
            rooms = {}
            for event in batch:
                _apply_event(db, path, rooms, event)
        with _queue_lock:
            for _ in batch:
                queue.popleft()
            if not queue:
                del _buffers[path]
        remaining -= size


def flush():
    """提交此数据目录中调用前已入队的事件；写入失败时保留缓冲并抛出异常。"""
    with _db_lock:
        _drain(_db_path())


def close():
    """关闭监听后刷盘并停止后台线程；下次收到事件时重新启动。"""
    global _worker
    flush()
    with _queue_lock:
        if _worker is None:
            return
        thread, stop = _worker
        _worker = None
        stop.set()
        _queue_lock.notify_all()
    thread.join()


@contextmanager
def _access(path=None):
    path = _db_path() if path is None else path
    with _db_lock, _database(path) as db:
        _drain(path, db)
        with db:
            yield db


def _wire_varint(raw, pos):
    number = 0
    for shift in range(0, 70, 7):
        if pos == len(raw):
            raise ValueError('truncated varint')
        byte = raw[pos]
        pos += 1
        if shift == 63 and byte > 1:
            raise ValueError('varint overflow')
        number |= (byte & 127) << shift
        if byte < 128:
            return number, pos
    raise ValueError('invalid varint')


def decode_interact_v2(payload):
    """从 data.pb 提取 uid、uname、msg_type；无效载荷返回空字典。"""
    # 参考 StarBot（兼容思路）；字段号 1 / 2 / 5 来自 BAC 公开的 V2 包样本：
    # https://goooler.github.io/bilibili-API-collect/docs/live/message_stream.html#用户交互消息v2-interact-word-v2
    if not isinstance(payload, (str, bytes)) or len(payload) > 65536:
        return {}
    try:
        raw = base64.b64decode(payload, validate=True)
        pos = 0
        out = {'uid': 0, 'uname': '', 'msg_type': 0}
        while pos < len(raw):
            tag, pos = _wire_varint(raw, pos)
            field, wire = divmod(tag, 8)
            if not field:
                return {}
            if wire == 0:
                value, pos = _wire_varint(raw, pos)
                if field == 1:
                    out['uid'] = value
                elif field == 5:
                    out['msg_type'] = value
                continue
            if wire == 2:
                size, pos = _wire_varint(raw, pos)
            elif wire in (1, 5):
                size = 8 if wire == 1 else 4
            else:
                return {}
            end = pos + size
            if end > len(raw):
                return {}
            if field == 2 and wire == 2:
                out['uname'] = raw[pos:end].decode('utf-8')
            pos = end
        return out if out['msg_type'] in (1, 2, 3) else {}
    except ValueError:
        return {}


def _create_session(db, uid, room_id, name, title, area, start_at, observed_at, fans_start=None):
    return db.execute(
        '''INSERT INTO live_sessions
           (uid, room_id, uname, title, area, status, start_at, transition_at, fans_start)
           VALUES (?, ?, ?, ?, ?, 'live', ?, ?, ?)''',
        (uid, room_id, name, title, area, start_at, observed_at, fans_start),
    ).lastrowid


def _latest_room(db, room_id):
    return db.execute('SELECT * FROM live_sessions WHERE room_id = ? ORDER BY id DESC LIMIT 1',
                      (room_id,)).fetchone()


def on_live_start(uid, room_id, *, uname='', title='', area='', start_at=None, fans_start=None,
                  grace_seconds=120, observed_at=None):
    """返回 (场次 ID, 是否续场)；早于最新下播的观测返回 (None, False)。"""
    uid, room_id = _uid(uid), _uid(room_id)
    if not uid or not room_id:
        raise ValueError('需要有效的主播 UID 和直播间 ID')
    observed = _clock(start_at if observed_at is None else observed_at)
    started = min(_clock(start_at), observed) if start_at is not None else observed
    name, title, area = _name(uname), _text(title), _text(area)
    fans = _integer(fans_start, None)
    path = _db_path()
    with _access(path) as db:
        current = _latest_room(db, room_id)
        if current is not None:
            if current['status'] == 'live':
                if observed >= current['transition_at']:
                    db.execute(
                        '''UPDATE live_sessions SET uname = COALESCE(NULLIF(?, ''), uname),
                           title = COALESCE(NULLIF(?, ''), title), area = COALESCE(NULLIF(?, ''), area),
                           fans_start = COALESCE(fans_start, ?) WHERE id = ?''',
                        (name, title, area, fans, current['id']),
                    )
                    _cache_name(path, uid, name)
                return current['id'], bool(current['resumed'])
            if observed < current['end_at']:
                return None, False
            # 参考 StarBot：只在下播时记录的宽限期内续场，历史待封账场次保留给 finalize_due。
            if (current['status'] == 'pending_end' and grace_seconds > 0
                    and current['end_at'] < current['finalize_at']
                    and observed <= min(current['finalize_at'], current['end_at'] + grace_seconds)):
                db.execute(
                    '''UPDATE live_sessions SET status = 'live', end_at = NULL, pending_end_at = NULL,
                       finalize_at = NULL, transition_at = ?, revision = revision + 1, resumed = 1,
                       like_offset = "like", like_clicks = 0, like_base = NULL, like_high = NULL,
                       uname = COALESCE(NULLIF(?, ''), uname), title = COALESCE(NULLIF(?, ''), title),
                       area = COALESCE(NULLIF(?, ''), area) WHERE id = ?''',
                    (observed, name, title, area, current['id']),
                )
                _cache_name(path, uid, name)
                return current['id'], True
            if started <= current['end_at']:
                started = observed
        sid = _create_session(db, uid, room_id, name, title, area, started, observed, fans)
        _cache_name(path, uid, name)
        return sid, False


def ensure_active_session(uid, room_id, *, uname='', title='', area='', start_at=None,
                          observed_at=None, grace_seconds=120):
    """根据已确认的直播状态补建场次，或返回已在采集的场次 ID。"""
    sid, _ = on_live_start(uid, room_id, uname=uname, title=title, area=area, start_at=start_at,
                           observed_at=observed_at, grace_seconds=grace_seconds)
    return sid


def set_fans_start(session_id, count):
    """附上异步获取的开播粉丝快照，保留最先写入的有效值。"""
    count = _integer(count, None)
    if count is None or session_id is None:
        return
    with _access() as db:
        db.execute('UPDATE live_sessions SET fans_start = ? WHERE id = ? AND fans_start IS NULL',
                   (count, session_id))


def on_live_end(room_id, *, end_at=None, grace_seconds=120):
    """停止当前场次采集并进入待封账；重复下播保持原来的截止时间。"""
    ended = _clock(end_at)
    with _access() as db:
        db.execute(
            '''UPDATE live_sessions SET status = 'pending_end', end_at = ?, pending_end_at = ?,
               finalize_at = ?, transition_at = ?, revision = revision + 1
               WHERE room_id = ? AND status = 'live' AND transition_at <= ?''',
            (ended, ended, ended + max(0, grace_seconds), ended, _uid(room_id), ended),
        )


def finalize_due(now=None, *, fans_fetcher=None):
    """返回本次新封账的场次 ID；可选 fans_fetcher(uid) -> (count, error)。"""
    now = _clock(now)
    path = _db_path()
    with _access(path) as db:
        due = db.execute(
            '''SELECT id, uid, revision FROM live_sessions
               WHERE status = 'pending_end' AND finalize_at < ? ORDER BY finalize_at, id''', (now,),
        ).fetchall()
    count_by_uid = {}
    if fans_fetcher is not None:
        # 抓取期间允许续场；写回时用 revision 验证是同一轮待封账。
        for row in due:
            uid = row['uid']
            if uid not in count_by_uid:
                count, error = fans_fetcher(uid)
                count_by_uid[uid] = _integer(count, None) if error is None else None
    finalized = []
    if due:
        with _access(path) as db:
            for row in due:
                sid = row['id']
                changed = db.execute(
                    '''UPDATE live_sessions SET status = 'ended', fans_end = ?, pending_end_at = NULL,
                       finalize_at = NULL WHERE id = ? AND status = 'pending_end' AND revision = ?''',
                    (count_by_uid.get(row['uid']), sid, row['revision']),
                ).rowcount
                if changed:
                    finalized.append(sid)
    return finalized


def cleanup_danmu(retention_days, *, now=None):
    """删除超出保留期限的文字语料，互动计数与排行榜保留。"""
    with _access() as db:
        return db.execute('DELETE FROM session_danmu WHERE happened_at < ?',
                          (_clock(now) - max(0, retention_days) * 86400,)).rowcount


def _identity(data, uid=None, name=None):
    user = _map(data.get('uinfo'))
    base = _map(user.get('base'))
    if data.get('is_mystery') or base.get('is_mystery'):
        return '', ''
    uid = _uid(uid or data.get('uid') or user.get('uid'))
    name = _name(name or data.get('uname') or data.get('username') or base.get('name')) if uid else ''
    return uid, name


def _add(db, table, keys, metrics, uname=None):
    fields = tuple(metrics)
    values = (*keys.values(), *metrics.values())
    changes = [f'{field} = MAX({table}.{field}, excluded.{field})' if field == 'online_peak'
               else f'{field} = {table}.{field} + excluded.{field}' for field in fields]
    if uname is not None:
        fields += ('uname',)
        values += (uname,)
        changes.append(f"uname = COALESCE(NULLIF(excluded.uname, ''), {table}.uname)")
    db.execute(f'''INSERT INTO {table} ({','.join((*keys, *fields))}) VALUES ({','.join('?' for _ in values)})
                   ON CONFLICT ({','.join(keys)}) DO UPDATE SET {','.join(changes)}''', values)


def _credit(db, sid, ts, user, metrics):
    db.execute(f"UPDATE live_sessions SET {','.join(f'{field} = {field} + ?' for field in metrics)} WHERE id = ?",
               (*metrics.values(), sid))
    uid, name = user
    if uid:
        _add(db, 'session_users', {'session_id': sid, 'uid': uid}, metrics, name)
    trend = {key: metrics[key] for key in ('danmu', 'gold', 'entry') if key in metrics}
    if trend:
        _add(db, 'session_minutes', {'session_id': sid, 'minute': int(ts // 60) * 60}, trend)


def _danmu(db, sid, ts, msg):
    info = _seq(msg.get('info'))
    if len(info) < 3:
        return ('', ''), {}
    head, author = _seq(info[0]), _seq(info[2])
    detail = _map(_at(head, 15))
    public_user = _map(detail.get('user'))
    uid, name = _identity({'uinfo': public_user}, _at(author, 0), _at(author, 1))
    extra = detail.get('extra')
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except ValueError:
            extra = None
    extra = _map(extra)
    emoticon = (_integer(_at(head, 12)) == 1 or bool(msg.get('emoticon')) or bool(detail.get('emoticon'))
                or bool(extra.get('emoticon_unique')))
    text = _text(info[1])
    if text.strip() and not emoticon:
        db.execute('INSERT INTO session_danmu (session_id, uid, text, happened_at) VALUES (?, ?, ?, ?)',
                   (sid, uid, text, ts))
    return (uid, name), {'danmu': 1, 'emoticon_danmu' if emoticon else 'text_danmu': 1}


def _gift(db, sid, data):
    num = _integer(data.get('num'))
    if not num:
        return {}
    coin_type = _text(data.get('coin_type'))
    total = _integer(data.get('total_coin'), _integer(_integer(data.get('price')) * num))
    blind = _map(data.get('blind_gift'))
    gift_id = _uid(data.get('giftId') or data.get('gift_id'))
    gift_name = _text(data.get('giftName') or data.get('gift_name'))
    box_id = _uid(blind.get('original_gift_id'))
    box_name = _text(blind.get('original_gift_name'))
    cost = _integer(_integer(blind.get('original_gift_price')) * num)
    # 参考 StarBot：盲盒爆出价值单列；付费营收按金瓜子实际投入计算。
    gold = (cost if blind else total) if coin_type == 'gold' else 0
    payout = total if blind else 0
    _add(db, 'session_gifts',
         {'session_id': sid, 'gift_id': gift_id, 'gift_name': gift_name, 'coin_type': coin_type,
          'box_id': box_id, 'box_name': box_name},
         {'count': num, 'gold': gold, 'box_cost': cost, 'box_payout': payout, 'box_profit': payout - cost})
    return {'gift_count': num, 'gift_gold': gold, 'gold': gold, 'free_count': num if coin_type != 'gold' else 0,
            'box_count': num if blind else 0, 'box_cost': cost, 'box_payout': payout, 'box_profit': payout - cost}


def _sc_gold(price):
    try:
        exact = Decimal(str(price)) * 1000
        if exact.is_finite() and 0 <= exact <= _MAX_EVENT_NUMBER and exact == exact.to_integral_value():
            return int(exact)
    except (InvalidOperation, ArithmeticError):
        pass
    return 0


def _guard(db, sid, user, ts, data):
    uid, name = user
    level = _integer(data.get('guard_level'))
    months = _integer(data.get('num'), 1)
    if level not in (1, 2, 3) or not months:
        return {}
    start = _integer(data.get('start_time'), int(ts))
    end = _integer(data.get('end_time'))
    gold = _integer(data.get('total_coin'), _integer(_integer(data.get('price')) * months))
    changed = db.execute(
        '''INSERT INTO session_guards (session_id, uid, uname, guard_level, start_time, end_time, months, gold, op_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (session_id, uid, guard_level, start_time) DO NOTHING''',
        (sid, uid, name, level, start, end, months, gold, _integer(data.get('op_type'), None)),
    ).rowcount
    return {'guard_count': 1, 'guard_months': months, 'guard_gold': gold, 'gold': gold} if changed else {}


def _like(db, sid, *, clicks=None, counter=None):
    if clicks is not None:
        db.execute('''UPDATE live_sessions SET like_clicks = like_clicks + ?,
                      "like" = like_offset + MAX(like_clicks + ?, COALESCE(like_high - like_base, 0)) WHERE id = ?''',
                   (clicks, clicks, sid))
    if counter is not None:
        # 首个累计样本覆盖此前收到的点击；保留这些点击作为偏移量，再比较后续两种增量。
        seeded = db.execute('''UPDATE live_sessions SET like_base = ?, like_high = ?,
                               like_offset = "like", like_clicks = 0 WHERE id = ? AND like_base IS NULL''',
                            (counter, counter, sid)).rowcount
        if not seeded:
            db.execute('''UPDATE live_sessions SET like_high = ?,
                          "like" = like_offset + MAX(like_clicks, ? - like_base)
                          WHERE id = ? AND like_high < ?''', (counter, counter, sid, counter))


def _apply_event(db, path, rooms, event):
    _, streamer, room, msg, name, title, area, ts, warm = event
    cmd = msg['cmd'].partition(':')[0]
    if room not in rooms:
        row = _latest_room(db, room)
        rooms[room] = (row['id'], row['uid'], row['transition_at']) if row and row['status'] == 'live' else (
            () if row else None
        )
    current = rooms[room]
    if current is None and warm:
        sid = _create_session(db, streamer, room, _name(name), _text(title), _text(area), ts, ts)
        current = rooms[room] = (sid, streamer, ts)
        _cache_name(path, streamer, _name(name))
    if not current or streamer != current[1] or ts < current[2]:
        return
    sid = current[0]
    data = _map(msg.get('data'))
    user = _identity(data)
    metrics = {}
    if cmd == 'DANMU_MSG':
        user, metrics = _danmu(db, sid, ts, msg)
    elif cmd == 'SEND_GIFT':
        metrics = _gift(db, sid, data)
    elif cmd == 'SUPER_CHAT_MESSAGE':
        user = _identity(data, name=_map(data.get('user_info')).get('uname'))
        gold = _sc_gold(data.get('price'))
        metrics = {'sc_count': 1, 'sc_gold': gold, 'gold': gold}
    elif cmd == 'GUARD_BUY':
        metrics = _guard(db, sid, user, ts, data)
    elif cmd in ('INTERACT_WORD', 'INTERACT_WORD_V2'):
        if cmd == 'INTERACT_WORD_V2':
            data = decode_interact_v2(data.get('pb'))
            user = _identity(data)
        field = {1: 'entry', 2: 'follow', 3: 'share'}.get(_integer(data.get('msg_type')))
        if field:
            metrics = {field: 1}
    elif cmd == 'ENTRY_EFFECT':
        if user[0] and not user[1]:
            match = _ENTRY_NAME.search(_text(data.get('copy_writing_v2') or data.get('copy_writing')))
            if match:
                user = user[0], _name(match[1])
        metrics = {'entry': 1}
    elif cmd == 'LIKE_INFO_V3_CLICK':
        clicks = _integer(data.get('like_count'), 1)
        _like(db, sid, clicks=clicks)
        if user[0] and clicks:
            _add(db, 'session_users', {'session_id': sid, 'uid': user[0]}, {'like': clicks}, user[1])
    elif cmd == 'LIKE_INFO_V3_UPDATE':
        _like(db, sid, counter=_integer(data.get('click_count'), None))
    elif cmd in ('ONLINE_RANK_COUNT', 'WATCHED_CHANGE'):
        online = cmd == 'ONLINE_RANK_COUNT'
        value = _integer(data.get('count' if online else 'num'), None)
        if value is not None:
            col = 'online_peak' if online else 'watched_peak'
            db.execute(f'UPDATE live_sessions SET {col} = MAX({col}, ?) WHERE id = ?', (value, sid))
            if online:
                _add(db, 'session_minutes', {'session_id': sid, 'minute': int(ts // 60) * 60}, {'online_peak': value})
    _cache_name(path, *user)
    if metrics:
        _credit(db, sid, ts, user, metrics)


def _scope_session(db, uid, room_id=''):
    sql = 'SELECT * FROM live_sessions WHERE uid = ?'
    params = (uid,)
    if room_id:
        sql += ' AND room_id = ?'
        params += (room_id,)
    return db.execute(sql + " ORDER BY (status = 'live') DESC, id DESC LIMIT 1", params).fetchone()


def _counts(db, condition, args):
    return dict(db.execute(
        f'''SELECT COUNT(DISTINCT CASE WHEN u.entry > 0 THEN u.uid END) AS unique_entry,
                   COUNT(DISTINCT u.uid) AS interactors
            FROM session_users u JOIN live_sessions s ON s.id = u.session_id WHERE {condition}''', args,
    ).fetchone())


def _session_dict(db, row, now):
    if row is None:
        return None
    result = {key: row[key] for key in (
        'id', 'uid', 'room_id', 'uname', 'title', 'area', 'status', 'start_at', 'end_at', 'pending_end_at',
        'fans_start', 'fans_end', 'online_peak', 'watched_peak', *_METRICS,
    )}
    stopped = row['end_at'] if row['end_at'] is not None else now
    result['duration'] = max(0, int(stopped - row['start_at']))
    result['danmu_per_minute'] = result['danmu'] * 60 / result['duration'] if result['duration'] else 0.0
    starts, ends = result['fans_start'], result['fans_end']
    result['fans_delta'] = ends - starts if starts is not None and ends is not None else None
    result.update(_counts(db, 's.id = ?', (row['id'],)))
    return result


def list_sessions(uid, limit=10):
    """按开播时间倒序返回场次摘要，互动人数按场次去重。"""
    uid, limit = _uid(uid), max(0, int(limit))
    if not uid or not limit:
        return []
    now = _clock(None)
    with _access() as db:
        return [dict(row) for row in db.execute(
            '''SELECT s.id, s.room_id, s.uname, s.title, s.area, s.status, s.start_at, s.end_at,
                      CAST(MAX(0, COALESCE(s.end_at, ?) - s.start_at) AS INTEGER) AS duration,
                      s.danmu, s.gold, s.online_peak,
                      (SELECT COUNT(*) FROM session_users u WHERE u.session_id = s.id) AS interactors
               FROM live_sessions s WHERE s.uid = ? ORDER BY s.start_at DESC, s.id DESC LIMIT ?''',
            (now, uid, limit),
        )]


def current_session_id(uid, room_id=''):
    """优先选择正在采集的场次，其次最近一场。"""
    with _access() as db:
        row = _scope_session(db, _uid(uid), _uid(room_id))
        return row['id'] if row is not None else None


def room_summary(uid, room_id='', *, now=None):
    """返回 {'session': 当前或最近场次/None, 'total': 同范围历史与实时汇总}。"""
    uid, room_id = _uid(uid), _uid(room_id)
    now = _clock(now)
    condition = 's.uid = ?'
    args = (uid,)
    if room_id:
        condition += ' AND s.room_id = ?'
        args += (room_id,)
    sums = ','.join(f'COALESCE(SUM(s.{field}), 0) AS {field}' for field in _METRICS)
    with _access() as db:
        session = _session_dict(db, _scope_session(db, uid, room_id), now)
        total = dict(db.execute(
            f'''SELECT COUNT(*) AS sessions, {sums},
                       COALESCE(SUM(CAST(MAX(0, COALESCE(s.end_at, ?) - s.start_at) AS INTEGER)), 0) AS duration,
                       COALESCE(MAX(s.online_peak), 0) AS online_peak, COALESCE(MAX(s.watched_peak), 0) AS watched_peak
                FROM live_sessions s WHERE {condition}''', (now, *args),
        ).fetchone())
        total['avg_danmu'] = total['danmu'] / total['sessions'] if total['sessions'] else 0.0
        total['danmu_per_minute'] = total['danmu'] * 60 / total['duration'] if total['duration'] else 0.0
        total.update(_counts(db, condition, args))
        return {'session': session, 'total': total}


def _user_cte(room_uid, sid=None):
    if sid is not None:
        return 'users AS (SELECT * FROM session_users WHERE session_id = ?)', (sid,)
    sums = ','.join(f'SUM(u.{field}) AS {field}' for field in _METRICS)
    return f'''totals AS (
                   SELECT u.uid, {sums}, MAX(CASE WHEN u.uname <> '' THEN s.id END) AS name_sid
                   FROM live_sessions s JOIN session_users u ON s.id = u.session_id
                   WHERE s.uid = ? GROUP BY u.uid
               ), users AS (
                   SELECT totals.*, COALESCE(u.uname, '') AS uname FROM totals
                   LEFT JOIN session_users u ON u.session_id = totals.name_sid AND u.uid = totals.uid
               )''', (room_uid,)


def _ranking(db, room_uid, field, sid, limit):
    cte, params = _user_cte(room_uid, sid)
    where = 'box_count > 0' if field == 'box_profit' else f'{field} > 0'
    return [dict(row) for row in db.execute(
        f'''WITH {cte} SELECT uid, uname, {field} AS value FROM users
            WHERE {where} ORDER BY value DESC, uid LIMIT ?''', (*params, limit),
    )]


def room_ranking(room_uid, dimension, scope='session', limit=10):
    """排名记录为 {'uid', 'uname', 'value'}；scope 为 session 或 total。"""
    field = _RANKS.get(dimension, dimension)
    if field not in _RANK_FIELDS:
        raise ValueError('未知排行榜维度')
    if scope not in ('session', 'total'):
        raise ValueError('未知排行榜范围')
    room_uid = _uid(room_uid)
    with _access() as db:
        session = _scope_session(db, room_uid) if scope == 'session' else None
        if scope == 'session' and session is None:
            return []
        return _ranking(db, room_uid, field, session['id'] if session else None, max(0, int(limit)))


def _viewer(db, room_uid, uid, sid=None):
    cte, params = _user_cte(room_uid, sid)
    order = {field: f'{field} DESC' for field in _RANK_FIELDS}
    order['box_profit'] = '(box_count > 0) DESC, box_profit DESC'
    ranks = ','.join(f'RANK() OVER (ORDER BY {sort}) AS rank_{field}' for field, sort in order.items())
    row = db.execute(
        f'WITH {cte}, ranked AS (SELECT *, {ranks} FROM users) SELECT * FROM ranked WHERE uid = ?', (*params, uid),
    ).fetchone()
    if row is None:
        return None, {}
    return (
        {field: row[field] for field in ('uid', 'uname', *_METRICS)},
        {field: row[f'rank_{field}'] for field in _RANK_FIELDS
         if row['box_count' if field == 'box_profit' else field]},
    )


def _viewer_uid(db, room_uid, name):
    name = name.strip().casefold()
    if not name:
        return ''
    cte, params = _user_cte(room_uid)
    exact, partial = [], []
    for row in db.execute(f"WITH {cte} SELECT uid, uname FROM users WHERE uname <> ''", params):
        candidate = row['uname'].casefold()
        if name == candidate:
            exact.append(row['uid'])
        elif name in candidate:
            partial.append(row['uid'])
    matches = exact or partial
    return matches[0] if len(matches) == 1 else ''


def user_summary(room_uid, user_uid='', user_name=''):
    """返回观众本场与累计数据及分维度名次；无匹配或昵称歧义时返回 None。"""
    room_uid = _uid(room_uid)
    with _access() as db:
        uid = _uid(user_uid) if user_uid else _viewer_uid(db, room_uid, user_name)
        if not uid:
            return None
        total, total_ranks = _viewer(db, room_uid, uid)
        if total is None:
            return None
        session = _scope_session(db, room_uid)
        current, current_ranks = _viewer(db, room_uid, uid, session['id']) if session else (None, {})
        if current is not None:
            current.update(session_id=session['id'], status=session['status'])
        return {'uid': uid, 'uname': total['uname'], 'session': current, 'total': total,
                'ranks': {'session': current_ranks, 'total': total_ranks}}


def _danmu_rows(db, session_id):
    return [dict(item) for item in db.execute(
        'SELECT uid, text, happened_at FROM session_danmu WHERE session_id = ? ORDER BY id', (session_id,),
    )]


def finalized_danmu_rows(session_id):
    """读已封账场次的语料，长查询经 WAL 快照读取，独立于采集写锁。"""
    with _database(_db_path()) as db:
        return _danmu_rows(db, session_id)


def session_detail(session_id, *, uid=None, now=None, include_danmu=True):
    """场次详情，支持校验所属主播；仅词云需要读取弹幕原文。"""
    with _access() as db:
        row = db.execute('SELECT * FROM live_sessions WHERE id = ?', (session_id,)).fetchone()
        if row is None or (uid is not None and row['uid'] != _uid(uid)):
            return None
        result = _session_dict(db, row, _clock(now))
        for key, fields, order in (
            ('minutes', 'minute, danmu, gold, online_peak, entry', 'minute'),
            ('gifts', '*', 'count DESC, gift_id, gift_name'),
            ('guards', '*', 'start_time, uid'),
        ):
            rows = db.execute(f'SELECT {fields} FROM session_{key} WHERE session_id = ? ORDER BY {order}',
                              (session_id,))
            result[key] = [dict(item) for item in rows]
        if include_danmu:
            result['danmu_rows'] = _danmu_rows(db, session_id)
        result['guard_levels'] = {1: 0, 2: 0, 3: 0}
        for guard in result['guards']:
            level = guard['guard_level']
            if level in result['guard_levels']:
                result['guard_levels'][level] += guard['months']
        result['rankings'] = {key: _ranking(db, row['uid'], field, session_id, 10) for key, field in _RANKS.items()}
        has_activity = row['like_clicks'] > 0 or any(result[key] for key in (
            'interactors', 'danmu', 'gift_count', 'sc_count', 'guard_count', 'entry', 'follow', 'share',
        ))
        result['all_anonymous'] = has_activity and not db.execute(
            "SELECT 1 FROM session_users WHERE session_id = ? AND uname <> '' LIMIT 1", (session_id,),
        ).fetchone()
        return result


def bind_user(platform, chat_user_id, bili_uid):
    """按聊天平台及用户 ID 绑定本人 B 站 UID，返回绑定值。"""
    bili_uid = _uid(bili_uid)
    if not platform or not chat_user_id or not bili_uid:
        raise ValueError('需要聊天平台、用户 ID 与有效的 B 站 UID')
    with _access() as db:
        db.execute('''INSERT INTO user_bindings (platform, user_id, bili_uid) VALUES (?, ?, ?)
                      ON CONFLICT (platform, user_id) DO UPDATE SET bili_uid = excluded.bili_uid''',
                   (str(platform), str(chat_user_id), bili_uid))
    return bili_uid


def get_bound_uid(platform, chat_user_id):
    """返回绑定 UID；未绑定时为空字符串。"""
    with _access() as db:
        row = db.execute('SELECT bili_uid FROM user_bindings WHERE platform = ? AND user_id = ?',
                         (str(platform), str(chat_user_id))).fetchone()
        return row['bili_uid'] if row else ''
