from bisect import bisect_left
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from random import uniform
from threading import Condition, Event, Lock, Thread
from time import sleep, time

from . import bili_api, config, function, livesocket, sender, store
from .message_custom import TEXT

_QUEUE_LIMIT = 256
_WORKER_LIMIT = 32
_RESULTS_PER_TICK = 8
_RISK_THRESHOLD = 3
_NOTICE_COOLDOWN = 6 * 60 * 60
_DETAIL_COOLDOWN = 600
_SEEN_LIMIT = 32
_KINDS = config.KINDS
_WATCHER_SYNC_SECONDS = 30
_IDS = {'dynamic': 'id_str', 'video': 'bvid'}
_LAST_IDS = {'dynamic': 'last_id', 'video': 'last_bvid'}
_NAV_KEYS = {'dynamic': 'opus', 'video': 'video'}


def _bots(proc):
    """宿主注入的账号表可能缺失或不是字典，缺省按空表处理。"""
    proc_data = getattr(proc, 'Proc_data', None)
    bots = proc_data.get('bot_info_dict') if isinstance(proc_data, dict) else None
    return bots if isinstance(bots, dict) else {}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def live_transition(runtime, payload):
    was_live = _int(runtime.get('live_status')) == 1
    is_live = _int(payload.get('live_status')) == 1
    if is_live != was_live:
        return 'start' if is_live else 'end'
    if is_live and (runtime.get('last_area_v2_name') or '') != (payload.get('area_v2_name') or ''):
        return 'area'
    return ''


def _entry_parts(kind, item):
    if kind == 'dynamic':
        modules = item.get('modules') or {}
        if item.get('type') == 'DYNAMIC_TYPE_AV' or (modules.get('module_tag') or {}).get('text') == '置顶':
            return 0, ''
        # 优先用 id_str：动态 id 与 opus_id 同源且单调递增，opus 降级通道没有 pub_ts。
        stamp = _int(item.get(_IDS[kind])) or (modules.get('module_author') or {}).get('pub_ts')
    else:
        stamp = item.get('created')
    return _int(stamp), str(item.get(_IDS[kind]) or '')


def _ordered_entries(kind, items):
    records = [(*_entry_parts(kind, item), item) for item in items]
    return sorted((record for record in records if record[0] > 0 and record[1]), key=lambda record: record[:2])


def new_entries(kind, state, items):
    """按发布时间返回未见条目，不改变入参。首次静默建档由调用方控制。"""
    return _fresh_entries(kind, state, _ordered_entries(kind, items))


# 一次最多补发几条：动态 id 是雪花号、旧记录可能是秒级时间戳，
# 口径不一致时长连接/降级通道会让历史条目全部「比上次新」，只补最新一条即可。
_CATCHUP_LIMIT = 3


def _fresh_entries(kind, state, records):
    since = _int(state.get('last_ts'))
    seen = set(state.get('seen_ids') or ())
    seen.add(str(state.get(_LAST_IDS[kind]) or ''))
    fresh = []
    for stamp, identity, item in records:
        if stamp > since and identity not in seen:
            seen.add(identity)
            fresh.append(item)
    if len(fresh) > _CATCHUP_LIMIT:
        # 只推最新的，其余记为已见，避免把陈年动态一口气刷出来。
        fresh = fresh[-1:]
    return fresh


def _group_allowed(settings, target):
    sdk = target.get('sdk', '')
    chat_type = target.get('chat_type', 'group')
    if (sdk == 'qqGuildv2_link' and chat_type != 'qq_group') or (sdk != 'qqGuildv2_link' and chat_type != 'group'):
        return False
    disabled = settings.get('disabled_group_list', ())
    sid = '|'.join(str(target.get(key, '')) for key in ('sdk', 'platform', 'group_id'))
    return sid not in disabled and str(target.get('group_id', '')) not in disabled


def eligible(settings, group, room, target, kind):
    return bool(
        settings.get('enable', True)
        and group.get('push', {}).get(kind)
        and room.get(kind, {}).get('enabled')
        and target.get(kind)
        and _group_allowed(settings, target)
    )


def consume_at_all(group, settings, live_time, day=None):
    """按群占用配额；仅对事务中的可写群记录或测试副本调用。"""
    if not group.get('at_all'):
        return False
    quota = group.setdefault('at_quota', {})
    options = settings.get('at_all', {})
    if group.get('sdk') == 'qqGuildv2_link':
        session = _int(live_time, str(live_time))
        previous = quota.get('last_at_live_time')
        if options.get('guild_at_once', True) and _int(previous, str(previous)) == session:
            return False
        quota['last_at_live_time'] = session
        return True
    today = date.today().isoformat() if day is None else day
    if quota.get('date') != today:
        quota.update(date=today, used=0)
    used = _int(quota.get('used'))
    if used >= _int(options.get('daily_limit'), 10):
        return False
    quota['used'] = used + 1
    return True


def _state(room, kind):
    return room.get('runtime' if kind == 'live' else kind, {})


def _backoff(state):
    failures = _int(state.get('fail_count'))
    return min(60 * 2 ** min(failures, 4), 600) if failures > 0 else 0


def _due(settings, room, kind, now, watched=False):
    if not room.get(kind, {}).get('enabled'):
        return False
    state = _state(room, kind)
    seconds = _int(settings['poll'].get(f'{kind}_seconds'), config.BOT_DEFAULT['poll'][f'{kind}_seconds'])
    if watched and kind == 'live':
        # 长连接已经在推事件，轮询只当安全网，可以放宽。
        relaxed = _int(settings['poll'].get('live_relaxed_seconds'),
                       config.BOT_DEFAULT['poll'].get('live_relaxed_seconds', 0))
        if relaxed > 0:
            seconds = max(seconds, relaxed)
    last_check = _int(state.get('last_check_at'))
    return not last_check or now - last_check >= max(seconds, _backoff(state))


def _limit(settings):
    return max(1, min(_WORKER_LIMIT, _int(settings['poll'].get('max_concurrent'), 3)))


def _risk_count(data, kind):
    return _int(data.get('risk', {}).get(kind))


def _clock(stamp):
    stamp = _int(stamp)
    try:
        return datetime.fromtimestamp(stamp).strftime('%Y-%m-%d %H:%M:%S') if stamp else ''
    except (OSError, OverflowError, ValueError):
        return ''


def _live_cover(payload):
    return sender.pick_first_image(payload.get(key) for key in ('cover_from_user', 'keyframe', 'system_cover'))


def _live_fields(room, uid, runtime, payload, kind, stamp):
    room_id = room.get('room_id')
    link = f'https://live.bilibili.com/{room_id}' if room_id else f'https://space.bilibili.com/{uid}'
    fields = {
        'title': str(payload.get('title') or runtime.get('last_title') or ''),
        'area': str(payload.get('area_v2_name') or runtime.get('last_area_v2_name') or ''),
        'time': _clock(_int(payload.get('live_time')) or stamp),
        'link': link,
    }
    if kind == 'end':
        fields['area'] = runtime.get('last_area_v2_name') or fields['area']
        fields['title'] = runtime.get('last_title') or fields['title']
    return fields


def _first_field(items, key):
    return items[0].get(key) if items else ''


def _feed_author(kind, item):
    if kind == 'video':
        return str(item.get('author') or '')
    modules = item.get('modules') or {}
    return str((modules.get('module_author') or {}).get('name') or '')


def _feed_fields(kind, item):
    stamp, identity = _entry_parts(kind, item)
    if kind == 'video':
        fields = {'title': str(item.get('title') or ''), 'time': _clock(stamp),
                  'link': f'https://www.bilibili.com/video/{identity}'}
        return str(item.get('author') or ''), fields, sender.pick_first_image((item.get('pic'),))
    modules = item.get('modules') or {}
    author = modules.get('module_author') or {}
    dynamic = modules.get('module_dynamic') or {}
    major = dynamic.get('major') or {}
    draw = major.get('draw') or {}
    opus = major.get('opus') or {}
    image = sender.pick_first_image((_first_field(draw.get('items'), 'src'), _first_field(opus.get('pics'), 'url'),
                                     author.get('face')))
    body = (dynamic.get('desc') or {}).get('text') or (opus.get('summary') or {}).get('text') or ''
    # stamp 是雪花 id 时不能当时刻用，发布时间以 pub_ts 为准。
    published = _int(author.get('pub_ts')) or stamp
    clock = _clock(published)
    if not clock and identity:
        # opus 降级通道没有 pub_ts，从 opus 页面补一次发布时间。
        clock = bili_api.opus_pub_time(identity)
    return str(author.get('name') or ''), {
        'body': str(body)[:200], 'time': clock, 'link': f'https://t.bilibili.com/{identity}',
    }, image


def _initialized(kind, state):
    # 只有真的记录过基线（last_id 或 last_ts）才算建档完成。
    # 之前把 last_check_at 也算进来，导致「查过但一次都没成功推送」的主播
    # 在第一次拿到数据时把整批历史当成新动态推出去。
    if not (state.get(_LAST_IDS[kind]) or state.get('last_ts')):
        return False
    return state.get('initialized', True)


@dataclass(frozen=True, slots=True)
class _Job:
    bot: str
    uid: str
    kind: str
    mount: object
    issued_at: float = 0

    @property
    def key(self):
        return self.bot, self.uid, self.kind


@dataclass(slots=True)
class _Result:
    job: _Job
    checked_at: int
    payload: object = None
    error: tuple | None = None
    detail: bool = True
    nav_count: int | None = None


@dataclass(slots=True)
class _Account:
    limit: int
    ticks: int = 0
    cursor: tuple = ('', -1)
    running: int = 0
    queued: int = 0


@dataclass(slots=True)
class _Notice:
    kind: str
    fields: dict
    image: str
    live_time: int = 0


def _request(uid, kind):
    if kind == 'live':
        data, error = bili_api.live_status((uid,))
        if error is not None:
            return None, error
        payload = data.get(uid)
        if not payload or 'live_status' not in payload:
            return None, (-1, '直播接口未返回该主播状态')
        return payload, None
    return (bili_api.dynamics if kind == 'dynamic' else bili_api.videos)(uid)


def _targets(room, job):
    for sid, target in room.get('targets', {}).items():
        added = target.get('added_at')
        if added is None or added <= job.issued_at:
            yield sid, added


def _active_target(data, job, sid, added_at):
    room = data['rooms'].get(job.uid)
    if room is None or room.get('resolved_at') != job.mount:
        return None, None, None
    target = room.get('targets', {}).get(sid)
    if target is None or target.get('added_at') != added_at:
        return room, None, None
    return room, data['groups'].get(sid, {}), target


def _send_log(proc, job, sid, kind, detail):
    store.log(proc, f'bot={job.bot} uid={job.uid} sid={sid} kind={kind} {detail}', 3)


class _Engine:
    def __init__(self, proc, accounts):
        self.proc = proc
        self.accounts = accounts
        self.order = deque(accounts)
        self.condition = Condition()
        self.closed = Event()
        self.write_lock = Lock()
        self.polls = deque()
        self.results = deque()
        self.applies = deque()
        self.watchers = {}
        self.watcher_sync_at = 0.0
        self.follow_seen = {}
        self.follow_sync_at = {}
        # 三个阶段共享容量；查完但未落盘或发完的任务仍占槽与去重名额。
        self.pending = set()
        self.running = 0
        self.executor = ThreadPoolExecutor(max_workers=_WORKER_LIMIT, thread_name_prefix='BiliBiliNotify')
        self.dispatcher = Thread(target=self._dispatch, name='BiliBiliNotify-dispatch', daemon=True)
        self.dispatcher.start()

    def close(self):
        self._close_watchers()
        with self.condition:
            self.closed.set()
            self.polls.clear()
            self.results.clear()
            self.applies.clear()
            self.condition.notify_all()
        self.dispatcher.join()
        # 旧代只等已经进入的持久化事务，不等失联 API 或节流等待。
        with self.write_lock:
            return

    def _is_mounted(self, job, room):
        return (not self.closed.is_set() and job.bot in _bots(self.proc) and room is not None
                and room.get('resolved_at') == job.mount and room.get(job.kind, {}).get('enabled')
                and store.bot_config(job.bot).get('enable', True))

    def schedule(self):
        now = time()
        bots = _bots(self.proc)
        with self.condition:
            if self.closed.is_set():
                return
            for _ in range(min(_RESULTS_PER_TICK, len(self.results))):
                self.applies.append(self.results.popleft())
            for bot in self.order:
                account = self.accounts[bot]
                settings = store.bot_config(bot)
                account.ticks += 1
                account.limit = _limit(settings) if bot in bots and settings.get('enable', True) else 0
                if account.limit and len(self.pending) < _QUEUE_LIMIT:
                    self._enqueue(bot, account, settings, store.rooms(bot)['rooms'], now)
            self.order.rotate(-1)
            self._sync_watchers()
            self._sync_follow(now)
            self.condition.notify()

    def _watch_log(self, message):
        store.log(self.proc, message, 3)

    def _sync_watchers(self):
        """补齐/回收直播间长连接。调用方持 self.condition，30 秒最多跑一次。"""
        now = time()
        if now - self.watcher_sync_at < _WATCHER_SYNC_SECONDS:
            return
        self.watcher_sync_at = now
        limit = 0
        wanted = {}
        for bot in self.order:
            settings = store.bot_config(bot)
            if not settings.get('enable', True):
                continue
            limit = max(limit, _int(settings['poll'].get('max_sockets'),
                                    config.BOT_DEFAULT['poll'].get('max_sockets', 0)))
            for uid, room in (store.rooms(bot)['rooms'] or {}).items():
                if not room.get('room_id') or not (room.get('live') or {}).get('enabled'):
                    continue
                # 只有真的会推送的直播间才值得占一条长连接。
                if not any(target.get('live') for target in (room.get('targets') or {}).values()):
                    continue
                wanted[(bot, uid)] = str(room['room_id'])
        for key in [key for key in self.follow_seen if key[0] not in self.accounts]:
            self.follow_seen.pop(key, None)
        for key in list(self.watchers):
            watcher, room_id = self.watchers[key]
            if key not in wanted or wanted[key] != room_id:
                watcher.stop()
                del self.watchers[key]
        if limit <= 0:
            return
        for (bot, uid), room_id in wanted.items():
            if len(self.watchers) >= limit:
                break
            if (bot, uid) in self.watchers:
                continue
            watcher = livesocket.LiveWatcher(
                room_id, lambda kind, b=bot, u=uid: self._trigger(b, u, 'live'), self._watch_log)
            watcher.start()
            self.watchers[(bot, uid)] = (watcher, room_id)

    def _sync_follow(self, now):
        """关注流触发：一条请求知道「关注的人里谁发了新动态」，详情仍走 opus。

        未关注的目标 UP 不在 cards 里，自动继续用逐 UP 轮询，不影响功能。
        """
        for bot in self.order:
            settings = store.bot_config(bot)
            if not settings.get('enable', True) or settings.get('dynamic_source') != 'follow':
                continue
            seconds = max(30, _int(settings['poll'].get('dynamic_seconds'), 600))
            if now - self.follow_sync_at.get(bot, 0) < seconds:
                continue
            self.follow_sync_at[bot] = now
            ids, error = bili_api.follow_max_ids()
            if error or not isinstance(ids, dict):
                continue
            for uid in list((store.rooms(bot)['rooms'] or {})):
                dynamic_id = ids.get(uid)
                if not dynamic_id:
                    continue
                key = bot, uid
                previous = self.follow_seen.get(key)
                self.follow_seen[key] = dynamic_id
                # 首次只记基线，避免把已有动态当成新的推一遍。
                if previous is not None and dynamic_id > previous:
                    self._trigger(bot, uid, 'dynamic')

    def _close_watchers(self):
        for watcher, _ in self.watchers.values():
            watcher.stop()
        self.watchers.clear()

    def _trigger(self, bot, uid, kind):
        """长连接事件触发的即时检查：绕过轮询间隔，但仍走同一条状态机。"""
        with self.condition:
            if self.closed.is_set() or bot not in self.accounts:
                return
            account = self.accounts[bot]
            if account.limit == 0:
                return
            key = bot, uid, kind
            if key in self.pending or len(self.pending) >= _QUEUE_LIMIT:
                return
            room = store.rooms(bot)['rooms'].get(uid)
            if room is None or not self._is_mounted(_Job(bot, uid, kind, room.get('resolved_at'), time()), room):
                return
            self.polls.append(_Job(bot, uid, kind, room.get('resolved_at'), time()))
            self.pending.add(key)
            account.queued += 1
            self.condition.notify()

    def _enqueue(self, bot, account, settings, rooms, now):
        budget = min(account.limit, 2 * account.limit - account.queued, _QUEUE_LIMIT - len(self.pending))
        if not rooms or budget <= 0:
            return
        uids = sorted(rooms)
        previous_uid, previous_kind = account.cursor
        index = bisect_left(uids, previous_uid)
        if index < len(uids) and uids[index] == previous_uid:
            index += 1
        width = len(uids)
        index += max(0, previous_kind) * width
        size = width * len(_KINDS)
        for offset in range(size):
            kind_index, room_index = divmod((index + offset) % size, width)
            uid, kind = uids[room_index], _KINDS[kind_index]
            room = rooms[uid]
            key = bot, uid, kind
            if key in self.pending or not _due(settings, room, kind, now, watched=(bot, uid) in self.watchers):
                continue
            self.polls.append(_Job(bot, uid, kind, room.get('resolved_at'), now))
            self.pending.add(key)
            account.cursor = uid, kind_index
            account.queued += 1
            budget -= 1
            if not budget:
                break

    def _take(self):
        # 优先处理已经拉到的数据；限额降低时，在途工作自然完成，不再超额启动。
        for queue, applying in ((self.applies, True), (self.polls, False)):
            for index, work in enumerate(queue):
                job = work.job if applying else work
                account = self.accounts[job.bot]
                if account.limit == 0:
                    del queue[index]
                    self.pending.remove(job.key)
                    account.queued -= 1
                    return job, None, False
                if account.running < account.limit:
                    del queue[index]
                    account.running += 1
                    self.running += 1
                    return job, work if applying else None, True
        return None

    def _dispatch(self):
        try:
            while True:
                with self.condition:
                    while not self.closed.is_set():
                        selection = self._take() if self.running < _WORKER_LIMIT else None
                        if selection is not None:
                            break
                        self.condition.wait()
                    else:
                        return
                job, result, run = selection
                if run:
                    self.executor.submit(self._work, job, result)
        finally:
            self.executor.shutdown(wait=False, cancel_futures=True)

    def _work(self, job, result):
        outcome = None
        try:
            if result is None:
                try:
                    outcome = self._poll(job)
                except Exception as error:
                    outcome = _Result(job, int(time()), error=(-1, f'请求任务异常：{type(error).__name__}'))
            else:
                self._apply(result)
        except Exception as error:
            store.log(self.proc, f'bot={job.bot} uid={job.uid} kind={job.kind} 工作者异常：{type(error).__name__}', 3)
        finally:
            with self.condition:
                account = self.accounts[job.bot]
                if outcome is not None and not self.closed.is_set():
                    self.results.append(outcome)
                else:
                    self.pending.remove(job.key)
                    account.queued -= 1
                account.running -= 1
                self.running -= 1
                self.condition.notify()

    def _poll(self, job):
        data = store.rooms(job.bot)
        room = data['rooms'].get(job.uid)
        if not self._is_mounted(job, room):
            return None
        nav_count = None
        if job.kind != 'live' and _risk_count(data, job.kind) >= _RISK_THRESHOLD:
            nav, error = bili_api.navnum(job.uid)
            if not self._is_mounted(job, store.rooms(job.bot)['rooms'].get(job.uid)):
                return None
            if error is None:
                nav_count = _int(nav.get(_NAV_KEYS[job.kind]), -1)
                if nav_count < 0:
                    nav_count, error = None, (-1, '空间计数缺少所需字段')
            state = _state(room, job.kind)
            previous = state.get('nav_count')
            changed = nav_count is not None and previous is not None and nav_count != previous
            # 计数不变也要试探恢复；动态条数不总能反映内容变化。
            last_detail = _int(state.get('detail_check_at'))
            cooldown_due = not last_detail or time() - last_detail >= _DETAIL_COOLDOWN
            if not changed and not cooldown_due:
                return _Result(job, int(time()), error=error, detail=False, nav_count=nav_count)
        payload, error = _request(job.uid, job.kind)
        return _Result(job, int(time()), payload, error, nav_count=nav_count)

    def _apply(self, result):
        job = result.job
        with self.write_lock:
            if self.closed.is_set():
                return
            with store.edit_rooms(job.bot) as data:
                room = data['rooms'].get(job.uid)
                if not self._is_mounted(job, room):
                    return
                # 先持久化游标再发送；热重载不会将已观察的事件重新群发。
                notices, nickname, backoff, risk = _record(data, room, result)
        if nickname and self._is_mounted(job, store.rooms(job.bot)['rooms'].get(job.uid)):
            function.names[job.bot, job.uid] = nickname
        if result.error:
            code, message = result.error
            store.log(self.proc, f'bot={job.bot} uid={job.uid} kind={job.kind} code={code} {message} '
                      f'backoff={backoff}s', 3)
        if notices or risk:
            self._deliver(job, tuple(_targets(room, job)), notices, risk)

    def _target(self, job, sid, added_at, warning=False):
        data = store.rooms(job.bot)
        room, group, target = _active_target(data, job, sid, added_at)
        if target is None or not self._is_mounted(job, room):
            return None
        settings = store.bot_config(job.bot)
        if warning and _risk_count(data, job.kind) < _RISK_THRESHOLD:
            return None
        return (settings, group, target) if eligible(settings, group, room, target, job.kind) else None

    def _claim(self, job, sid, added_at, notice):
        with self.write_lock:
            if self.closed.is_set():
                return False
            with store.edit_rooms(job.bot) as data:
                room, group, target = _active_target(data, job, sid, added_at)
                if target is None or not self._is_mounted(job, room):
                    return False
                settings = store.bot_config(job.bot)
                if not eligible(settings, group, room, target, job.kind):
                    return False
                if notice is None:
                    now = int(time())
                    last_warning = _int(group.get('last_412_notice_at'))
                    if (_risk_count(data, job.kind) < _RISK_THRESHOLD
                            or (last_warning and now - last_warning < _NOTICE_COOLDOWN)):
                        return False
                    group['last_412_notice_at'] = now
                    return True
                return consume_at_all(group, settings, notice.live_time)

    def _deliver(self, job, destinations, notices, warning):
        if warning:
            notices = (None,)
        last_notice = -1
        failed = sent = 0
        for index, notice in enumerate(notices):
            for sid, added_at in destinations:
                current = self._target(job, sid, added_at, warning)
                if current is None:
                    continue
                if warning:
                    last_warning = _int(current[1].get('last_412_notice_at'))
                    if last_warning and time() - last_warning < _NOTICE_COOLDOWN:
                        continue
                interval = _interval(current[0])
                delay = interval if last_notice != index else max(0, uniform(interval - 1, interval + 1))
                if last_notice >= 0 and self.closed.wait(delay):
                    return

                def still_current(sid=sid, added_at=added_at):
                    return self._target(job, sid, added_at, warning) is not None

                current = self._target(job, sid, added_at, warning)
                if current is None:
                    continue
                settings, group, target = current
                kind = 'risk_warning' if warning else notice.kind
                try:
                    if warning:
                        if not self._claim(job, sid, added_at, None) or not still_current():
                            continue
                        success = sender.send_warning(
                            self.proc, job.bot, target, TEXT['risk_warning'], still_current=still_current,
                        )
                    else:
                        at_all = kind == 'start' and group.get('at_all') and self._claim(job, sid, added_at, notice)
                        current = self._target(job, sid, added_at)
                        if current is None:
                            continue
                        settings, group, target = current
                        at_all = bool(at_all and group.get('at_all'))
                        if kind == 'start' and group.get('at_all') and not at_all and target.get('sdk') == 'onebot':
                            _send_log(self.proc, job, sid, kind, 'at_all_quota_exhausted')
                        mention = kind == 'start' and settings.get('at_subscribers', {}).get('live', True)
                        subscribers = target.get('subscribers', ()) if mention else ()
                        success = sender.send(self.proc, job.bot, target, kind, notice.fields, image=notice.image,
                                              at_all=at_all, subscribers=subscribers, interval=_interval(settings),
                                              still_current=still_current)
                except Exception as error:
                    _send_log(self.proc, job, sid, kind, f'发送异常：{type(error).__name__}')
                    failed += 1
                else:
                    if success:
                        sent += 1
                    elif still_current():
                        _send_log(self.proc, job, sid, kind, '发送失败')
                        failed += 1
                last_notice = index
        if failed:
            store.log(self.proc, f'bot={job.bot} uid={job.uid} kind={job.kind} 推送汇总：成功 {sent}，失败 {failed}', 3)


def _interval(settings):
    return max(0, _int(settings.get('send_interval_seconds'), 3))


def _record(data, room, result):
    job = result.job
    kind = job.kind
    state = room.setdefault('runtime' if kind == 'live' else kind, {})
    if kind != 'live':
        state['initialized'] = _initialized(kind, state)
        if result.nav_count is not None:
            state['nav_count'] = result.nav_count
        if result.detail:
            state['detail_check_at'] = result.checked_at
    state['last_check_at'] = result.checked_at
    risk = False
    if result.detail:
        is_412 = result.error is not None and result.error[0] in (-412, 412)
        streak = _risk_count(data, kind) + 1 if is_412 else 0
        if is_412 or kind in data.get('risk', {}):
            data.setdefault('risk', {})[kind] = streak
        risk = streak >= _RISK_THRESHOLD
    if result.error:
        state.update(fail_count=_int(state.get('fail_count')) + 1, last_error=f'{result.error[0]} {result.error[1]}')
        return (), '', _backoff(state), risk
    if not result.detail:
        return (), '', 0, False
    state.update(fail_count=0, last_error='')
    notices, nickname = _record_live(room, state, result) if kind == 'live' else _record_feed(state, result)
    return notices, nickname, 0, False


def _record_live(room, state, result):
    payload = result.payload
    uid = result.job.uid
    nickname = str(payload.get('uname') or '')
    action = live_transition(state, payload)
    live_status = _int(payload.get('live_status'))
    live_time = _int(payload.get('live_time'))
    if not live_time and live_status == 1:
        live_time = (_int(state.get('last_live_time')) if action != 'start' else 0) or result.checked_at
    cover = _live_cover(payload)
    if action:
        fields = _live_fields(room, uid, state, payload, action, live_time or result.checked_at)
        fields['name'] = nickname or function.names.get((result.job.bot, uid)) or f'UID {uid}'
        notices = (_Notice(action, fields, cover if action != 'end' else '', live_time),)
    else:
        notices = ()
    state.update(live_status=live_status, last_live_time=live_time,
                 last_area_v2_name=str(payload.get('area_v2_name') or ''), last_title=str(payload.get('title') or ''),
                 last_cover=cover)
    return notices, nickname


def _record_feed(state, result):
    bot, uid, kind = result.job.key
    records = _ordered_entries(kind, result.payload or ())[-5:]
    fresh = _fresh_entries(kind, state, records) if state['initialized'] else ()
    state['initialized'] = True
    if records:
        stamp, identity, _ = records[-1]
        if stamp > _int(state.get('last_ts')):
            state.update({_LAST_IDS[kind]: identity, 'last_ts': stamp})
        seen = list(dict.fromkeys([*(state.get('seen_ids') or ()), *(identity for _, identity, _ in records)]))
        state['seen_ids'] = seen[-_SEEN_LIMIT:]
    notices = []
    latest_name = _feed_author(kind, records[-1][2]) if records else ''
    for item in fresh:
        name, fields, image = _feed_fields(kind, item)
        fields['name'] = name or latest_name or function.names.get((bot, uid)) or f'UID {uid}'
        notices.append(_Notice(kind, fields, image))
    return notices, latest_name


_lifecycle = Lock()
_engine = None


def start(Proc):
    global _engine
    with _lifecycle:
        if _engine is not None:
            if _engine.proc is Proc:
                return
            _engine.close()
        accounts = {}
        proc_data = getattr(Proc, 'Proc_data', None)
        bot_info_dict = proc_data.get('bot_info_dict') if isinstance(proc_data, dict) else None
        for bot_hash in list(bot_info_dict) if isinstance(bot_info_dict, dict) else ():
            store.load_bot(bot_hash)
            settings = store.bot_config(bot_hash)
            accounts[bot_hash] = _Account(_limit(settings) if settings.get('enable', True) else 0)
        _engine = _Engine(Proc, accounts) if accounts else None


def stop(Proc):
    global _engine
    with _lifecycle:
        if _engine is not None and _engine.proc is Proc:
            engine, _engine = _engine, None
            engine.close()


def tick(Proc):
    engine = _engine
    if engine is not None and engine.proc is Proc:
        # 仅访问 start 预载的已发布快照；调度回调不加载新 Bot 或做任何 I/O。
        engine.schedule()


def status(bot_hash):
    data = store.rooms(bot_hash)
    checks = dict.fromkeys(_KINDS, 0)
    backoff = dict.fromkeys(_KINDS, False)
    now = time()
    for room in data['rooms'].values():
        for kind in _KINDS:
            state = _state(room, kind)
            last_check = _int(state.get('last_check_at'))
            checks[kind] = max(checks[kind], last_check)
            if room.get(kind, {}).get('enabled') and now - last_check < _backoff(state):
                backoff[kind] = True
    streak = max(_risk_count(data, kind) for kind in _KINDS)
    stats = {'ticks': 0, 'workers': 0, 'queue': 0, 'running': 0, 'last_checks': checks,
             'blocked': streak >= _RISK_THRESHOLD, 'count_412': streak,
             'backing_off': any(backoff.values()), 'kind_backoff': backoff}
    engine = _engine
    if engine is not None:
        with engine.condition:
            account = engine.accounts.get(bot_hash)
            if account is not None:
                stats.update(ticks=account.ticks, workers=account.limit, queue=account.queued - account.running,
                             running=account.running)
    return stats


def test_push(Proc, bot_hash, uid, kind, targets=None):
    room = store.rooms(bot_hash)['rooms'].get(uid)
    if room is None or bot_hash not in _bots(Proc):
        return 'missing'
    explicit = targets is not None
    destinations = tuple((function.sid_for(target), target) for target in targets) if explicit else tuple(
        room.get('targets', {}).items())
    settings = store.bot_config(bot_hash)
    if not settings.get('enable', True) or not any(_group_allowed(settings, target) for _, target in destinations):
        return 'empty'
    try:
        payload, error = _request(uid, kind)
        if error:
            code, message = error
            store.log(Proc, f'bot={bot_hash} uid={uid} kind={kind} 测试请求失败 code={code} {message}', 3)
            return 'failed'
        if kind == 'live':
            action = 'start' if _int(payload.get('live_status')) == 1 else 'end'
            fields = _live_fields(room, uid, {}, payload, action, int(time()))
            image = _live_cover(payload) if action == 'start' else ''
            nickname = str(payload.get('uname') or '')
        else:
            items = _ordered_entries(kind, payload or ())
            if not items:
                return 'empty'
            action = kind
            nickname, fields, image = _feed_fields(kind, items[-1][2])
    except Exception as error:
        store.log(Proc, f'bot={bot_hash} uid={uid} kind={kind} 测试请求异常：{type(error).__name__}', 3)
        return 'failed'
    fields['name'] = nickname or function.names.get((bot_hash, uid)) or f'UID {uid}'
    job = _Job(bot_hash, uid, kind, room.get('resolved_at'))
    sent, failed, attempted = False, False, False
    for sid, target in destinations:
        added_at = target.get('added_at')

        def still_current(sid=sid, target=target, added_at=added_at):
            data = store.rooms(bot_hash)
            mounted, _, current = _active_target(data, job, sid, added_at)
            settings = store.bot_config(bot_hash)
            return bool(bot_hash in _bots(Proc) and mounted is not None
                        and (explicit or current is not None) and settings.get('enable', True)
                        and _group_allowed(settings, target))

        if not still_current():
            continue
        interval = _interval(store.bot_config(bot_hash))
        if attempted:
            sleep(max(0, uniform(interval - 1, interval + 1)))
            if not still_current():
                continue
        attempted = True
        try:
            success = sender.send(Proc, bot_hash, target, action, fields, image=image, test=True, interval=interval,
                                  still_current=still_current)
        except Exception as error:
            _send_log(Proc, job, sid, action, f'测试发送异常：{type(error).__name__}')
            failed = True
        else:
            sent = sent or success
            if not success and still_current():
                _send_log(Proc, job, sid, action, '测试发送失败')
                failed = True
    return 'failed' if failed else 'ok' if sent else 'empty'
