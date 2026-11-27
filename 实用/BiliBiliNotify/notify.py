from bisect import bisect_left
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from itertools import islice
from random import uniform
import sqlite3
from threading import Condition, Event, Lock, Thread
from time import sleep, time

from . import bili_api, capabilities, config, dynamic_render, function, live_stats, livesocket, sender, store
from .message_custom import TEXT
from .render_base import archive_generated_png

_QUEUE_LIMIT = 256
_WORKER_LIMIT = 32
_RESULTS_PER_TICK = 8
_RISK_THRESHOLD = 3
_NOTICE_COOLDOWN = 6 * 60 * 60
_DETAIL_COOLDOWN = 600
_SEEN_LIMIT = 32
_KINDS = config.KINDS
_WATCHER_SYNC_SECONDS = 30
_MAINTAIN_SECONDS = 5
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


def _same_scale(earlier, later):
    """判断两个时间戳是否同一口径（雪花 id 与秒级时间戳混用时差好几个数量级）。"""
    if not earlier or not later:
        return True
    return max(earlier, later) / min(earlier, later) < 1000


def _fresh_entries(kind, state, records):
    """按发布时间返回未见条目，不改变入参。连发多少条就推多少条。

    只有「口径变了」时才不下发（源切换导致所有历史都比上次新），
    这时静默重建基线，而不是把历史当新动态推出去。
    """
    since = _int(state.get('last_ts'))
    seen = set(state.get('seen_ids') or ())
    seen.add(str(state.get(_LAST_IDS[kind]) or ''))
    fresh = []
    for stamp, identity, item in records:
        if stamp > since and identity not in seen:
            seen.add(identity)
            fresh.append(item)
    if fresh and since and not _same_scale(since, records[-1][0]):
        return []
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


def _format_duration(seconds):
    seconds = _int(seconds)
    if seconds < 0:
        return ''
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = ((hours, '小时'), (minutes, '分'), (secs, '秒'))
    return ''.join(f'{value}{unit}' for value, unit in parts if value) or '0秒'


def _live_end_duration(room, uid, runtime, ended_at, *, use_stats=False):
    started_at = 0
    if use_stats and (store.ROOT / 'stats.db').is_file():
        try:
            session = live_stats.room_summary(uid, str(room.get('room_id') or '')).get('session')
            if (isinstance(session, dict) and session.get('status') in ('live', 'pending_end')
                    and _int(session.get('start_at')) > 0):
                session_end = _int(session.get('end_at'))
                if not session_end or abs(session_end - ended_at) <= 60:
                    started_at = _int(session.get('start_at'))
        except Exception:
            started_at = 0
    if started_at <= 0:
        started_at = _int(runtime.get('last_live_time'))
    if started_at <= 0 or ended_at < started_at:
        return ''
    return _format_duration(ended_at - started_at)


def _live_fields(room, uid, runtime, payload, kind, stamp, *, use_stats=False):
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
        fields['duration'] = _live_end_duration(room, uid, runtime, _int(stamp), use_stats=use_stats)
    return fields


def _first_field(items, key):
    first = items[0] if items else None
    return first.get(key) if isinstance(first, dict) else first if isinstance(first, str) else ''


def _feed_author(kind, item):
    if kind == 'video':
        return str(item.get('author') or '')
    modules = item.get('modules') or {}
    return str((modules.get('module_author') or {}).get('name') or '')


def _live_share_cover(major):
    info = dynamic_render.live_share_info(major)
    return info.get('cover') or info.get('keyframe') or ''


def _major_images(major):
    """按动态类型取配图：图文 draw / opus、视频 archive、专栏 article。参考 StarBot。

    不再拿作者头像兜底 —— 没图就发不带图的消息。
    """
    draw = major.get('draw') or {}
    opus = major.get('opus') or {}
    archive = major.get('archive') or {}
    article = major.get('article') or {}
    return (
        _first_field(draw.get('items'), 'src'),
        _first_field(opus.get('pics'), 'url'),
        str(archive.get('cover') or ''),
        _first_field(article.get('covers'), 'url'),
        _live_share_cover(major),
    )


def _orig_text(orig):
    """原动态的一句话概要：视频标题 / 专栏标题 / opus 正文 / 普通动态正文。"""
    modules = orig.get('modules') or {}
    dynamic = modules.get('module_dynamic') or {}
    major = dynamic.get('major') or {}
    archive = major.get('archive') or {}
    article = major.get('article') or {}
    opus = major.get('opus') or {}
    for text in (
        str(archive.get('title') or ''),
        str(article.get('title') or ''),
        str((opus.get('summary') or {}).get('text') or ''),
        str((dynamic.get('desc') or {}).get('text') or ''),
    ):
        if text:
            return text[:40]
    return ''


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
    opus = major.get('opus') or {}
    # 转发动态自己没有配图，图片和正文都要看被转发的原动态。
    orig = item.get('orig') if isinstance(item.get('orig'), dict) else {}
    orig_modules = orig.get('modules') or {}
    orig_dynamic = orig_modules.get('module_dynamic') or {}
    orig_major = orig_dynamic.get('major') or {}
    image = sender.pick_first_image([
        *(_major_images(major)),
        *(_major_images(orig_major)),
    ])
    body = (dynamic.get('desc') or {}).get('text') or (opus.get('summary') or {}).get('text') or ''
    if item.get('type') == 'DYNAMIC_TYPE_FORWARD' and orig:
        orig_author = str((orig_modules.get('module_author') or {}).get('name') or '')
        detail = _orig_text(orig)
        if detail:
            note = f'转发 {orig_author}：{detail}' if orig_author else f'转发：{detail}'
            body = f'{body}｜{note}' if body else note
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
    raw_item: object = None


def _request(uid, kind, room_id=''):
    if kind == 'live':
        return bili_api.live_detail(uid, room_id=room_id)
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


@contextmanager
def _card_cache():
    cards = {}
    try:
        yield cards
    finally:
        for path in cards.values():
            if path is not None:
                sender.release_local_image(path)


def _render_card(proc, job, sid, notice, settings):
    try:
        item = notice.raw_item
        modules = item.get('modules') or {}
        author = modules.get('module_author') or {}
        if not author.get('pub_ts') and not author.get('pub_time') and notice.fields.get('time'):
            # Opus 补采时间由 _feed_fields 获取；保持原始条目不变。
            item = {**item, 'modules': {**modules, 'module_author': {**author, 'pub_time': notice.fields['time']}}}
        archive = config.DATA_ROOT / 'dynamics' if settings.get('save_dynamic_image') else None
        return dynamic_render.render_dynamic_card(
            item, fallback_name=notice.fields['name'], link=notice.fields['link'], archive_dir=archive,
        )
    except Exception as error:
        _send_log(proc, job, sid, notice.kind, f'卡片渲染失败：{type(error).__name__}: {error}，回退图文')
        return None


def _send_notice(proc, job, sid, target, group, settings, notice, cards, *, still_current,
                 at_all=False, subscribers=(), test=False):
    override = group.get('dynamic_image')
    enabled = settings.get('dynamic_image') if override is None else override
    if (notice.kind == 'dynamic' and notice.raw_item is not None and enabled
            and capabilities.can('dynamic_image')):
        key = id(notice)
        if key not in cards:
            cards[key] = _render_card(proc, job, sid, notice, settings)
        path = cards[key]
        if path is not None and sender.send(proc, job.bot, target, notice.kind, notice.fields, local_image=path,
                                            test=test, still_current=still_current):
            return True
    return sender.send(proc, job.bot, target, notice.kind, notice.fields, image=notice.image, test=test,
                       at_all=at_all, subscribers=subscribers, interval=_interval(settings),
                       still_current=still_current)


def _session_image_key(kind, stats):
    if kind == 'report':
        return kind, stats['hide_revenue']
    return kind, stats['wordcloud_limit'], tuple(stats['wordcloud_stopwords']), tuple(stats['wordcloud_words'])


class _Engine:
    def __init__(self, proc, accounts, on_session_finalized=None):
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
        self.watch_routes = {}
        self.stats_ingest_lock = Lock()
        self.stats_fan_jobs = {}
        self.stats_cleanup_day = None
        self.finalized_sessions = deque()
        self.finalizing = False
        self.on_session_finalized = self._push_session_images if on_session_finalized is None else on_session_finalized
        self.watcher_sync_at = 0.0
        self.follow_seen = {}
        self.follow_sync_at = {}
        # 三个阶段共享容量；查完但未落盘或发完的任务仍占槽与去重名额。
        self.pending = set()
        self.running = 0
        self.executor = ThreadPoolExecutor(max_workers=_WORKER_LIMIT, thread_name_prefix='BiliBiliNotify')
        self.dispatcher = Thread(target=self._dispatch, name='BiliBiliNotify-dispatch', daemon=True)
        self.dispatcher.start()
        # 维护线程：建连/收连与关注流同步都要发网络请求，绝不能放在宿主 tick 里，
        # 否则 tick 会卡住 30 秒以上，宿主报「task already pending or running」并跳过。
        self.maintainer = Thread(target=self._maintain, name='BiliBiliNotify-maintain', daemon=True)
        self.maintainer.start()

    def close(self):
        with self.condition:
            self.closed.set()
            watchers = list(self.watchers.values())
            self.watchers.clear()
            self.watch_routes = {}
            self.polls.clear()
            self.results.clear()
            self.applies.clear()
            self.finalized_sessions.clear()
            self.condition.notify_all()
        for watcher in watchers:
            watcher.stop()
        self.dispatcher.join()
        self.maintainer.join(timeout=1.0)
        # 旧代只等已经进入的持久化事务，不等失联 API 或节流等待。
        with self.write_lock:
            with self.stats_ingest_lock:
                pass  # 排空关停信号发出前已经进入的事件入队操作。
            try:
                live_stats.close()  # 刷盘并停止事件写线程。
            except (OSError, sqlite3.Error) as error:
                store.log(self.proc, f'直播统计关停刷盘失败：{type(error).__name__}', 3)

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
            self.condition.notify()

    def _maintain(self):
        """后台维护：每 5 秒看一次，具体节奏由 _sync_* 各自节流。

        绝不持 self.condition 做网络请求或启停长连接，避免阻塞 1 秒一次的宿主 bili_tick。
        """
        while not self.closed.wait(_MAINTAIN_SECONDS):
            try:
                if self.closed.is_set():
                    return
                sender.reap_local_images()
                self._sync_watchers()
                self._maintain_stats()
                self._sync_follow(time())
            except Exception as error:  # noqa: BLE001 - 维护线程不能因为一次异常退出
                store.log(self.proc, f'维护线程异常：{type(error).__name__}', level=3)

    def _maintain_stats(self):
        with self.stats_ingest_lock:
            if self.closed.is_set():
                return
            live_stats.flush()
        if self.closed.is_set() or not (store.ROOT / 'stats.db').exists():
            return
        # 快照请求与封账均在后台进行，维护期间仍可接收事件和派发轮询。
        while not self.closed.is_set():
            with self.write_lock:
                if not self.stats_fan_jobs or self.closed.is_set():
                    break
                session_id = next(iter(self.stats_fan_jobs))
                uid = self.stats_fan_jobs.pop(session_id)
            count, error = bili_api.fans_count(uid)
            if not error:
                with self.write_lock:
                    if not self.closed.is_set():
                        live_stats.set_fans_start(session_id, count)
        if self.closed.is_set():
            return
        finalized = live_stats.finalize_due(fans_fetcher=bili_api.fans_count)
        if finalized:
            with self.condition:
                if not self.closed.is_set():
                    self.finalized_sessions.extend(finalized)
                    self.condition.notify()
        today = date.today()
        if self.stats_cleanup_day != today and not self.closed.is_set():
            retention = max((settings['live_stats']['danmu_retention_days'] for bot in self.accounts
                             if _stats_enabled(settings := store.bot_config(bot))), default=0)
            if retention:
                with self.stats_ingest_lock:
                    if not self.closed.is_set():
                        live_stats.cleanup_danmu(retention)
                        self.stats_cleanup_day = today

    def _run_finalized(self, session_id):
        try:
            if not self.closed.is_set():
                self.on_session_finalized(session_id)
        except Exception as error:
            store.log(self.proc, f'场次 {session_id} 封账回调异常：{type(error).__name__}', 3)
        finally:
            with self.condition:
                self.finalizing = False
                self.running -= 1
                self.condition.notify()

    def _session_target(self, job, sid, added_at, kind, detail):
        if self.closed.is_set() or job.bot not in _bots(self.proc):
            return None
        feature, setting, _ = config.LIVE_IMAGES[kind]
        settings = store.bot_config(job.bot)
        if not _stats_enabled(settings) or not capabilities.can(feature):
            return None
        stats = settings['live_stats']
        if detail['duration'] < stats['min_report_minutes'] * 60 or detail['danmu'] < stats['min_report_danmu']:
            return None
        _, group, target = _active_target(store.rooms(job.bot), job, sid, added_at)
        if target is None or not _group_allowed(settings, target):
            return None
        override = group.get(kind)
        if not (override if type(override) is bool else stats[setting]):
            return None
        return settings, target

    def _push_session_images(self, session_id):
        kinds = [kind for kind, (feature, _, _) in config.LIVE_IMAGES.items() if capabilities.can(feature)]
        if not kinds:
            return
        detail = live_stats.session_detail(session_id, include_danmu=False)
        if detail is None:
            return
        uid = detail['uid']
        issued_at = time()
        bots = _bots(self.proc)
        rooms = [(bot, room) for bot in self.accounts if bot in bots
                 and (room := store.rooms(bot)['rooms'].get(uid)) is not None]
        detail['avatar_url'] = next((url for _, room in rooms if (url := room['runtime'].get('avatar_url'))), '')
        archive_dir = config.DATA_ROOT / 'reports' / uid
        archived = set()
        attempted = False
        with _card_cache() as cards:
            for bot, room in rooms:
                job = _Job(bot, uid, 'live', room.get('resolved_at'), issued_at)
                for sid, added in _targets(room, job):
                    for kind in kinds:
                        current = self._session_target(job, sid, added, kind, detail)
                        if current is None:
                            continue
                        settings, _ = current
                        stats = settings['live_stats']
                        key = _session_image_key(kind, stats)
                        if key not in cards:
                            try:
                                if kind == 'cloud' and 'danmu_rows' not in detail:
                                    detail['danmu_rows'] = live_stats.finalized_danmu_rows(session_id)
                                cards[key] = function.render_session_image(kind, detail, stats)
                            except Exception as error:
                                _send_log(
                                    self.proc, job, sid, kind,
                                    f'场次 {session_id} 渲染失败：{type(error).__name__}: {error}',
                                )
                                cards[key] = None
                        path = cards[key]
                        if path is None:
                            continue
                        if attempted and self.closed.wait(_interval(settings)):
                            return
                        current = self._session_target(job, sid, added, kind, detail)
                        if current is None or _session_image_key(kind, current[0]['live_stats']) != key:
                            continue
                        settings, target = current
                        if settings['live_stats']['save_report_image'] and key not in archived:
                            archive_generated_png(path, archive_dir)
                            archived.add(key)

                        def still_current():
                            latest = self._session_target(job, sid, added, kind, detail)
                            return latest is not None and _session_image_key(kind, latest[0]['live_stats']) == key

                        label = config.LIVE_IMAGES[kind][2]
                        name = detail['uname'] or function.names.get((bot, uid)) or f'UID {uid}'
                        caption = TEXT['session_image_caption'].format(label=label, name=' '.join(name.splitlines()))
                        sent = sender.send_local_image(
                            self.proc, bot, target, path, caption, still_current=still_current,
                        )
                        attempted = True
                        if not sent and still_current():
                            _send_log(self.proc, job, sid, kind, f'场次 {session_id} 图片发送失败')

    def _watch_log(self, message):
        store.log(self.proc, message, 3)

    def _sync_watchers(self):
        """补齐/回收直播间长连接。30 秒最多跑一次，socket 启停全在锁外。"""
        now = time()
        if now - self.watcher_sync_at < _WATCHER_SYNC_SECONDS:
            return
        self.watcher_sync_at = now
        available = capabilities.can('live_stats')
        limit = 0
        wanted = {}
        stats_bots = set()
        for bot in tuple(self.accounts):
            settings = store.bot_config(bot)
            if not settings.get('enable', True):
                continue
            stats_enabled = _stats_enabled(settings)
            if stats_enabled:
                stats_bots.add(bot)
            limit = max(limit, _int(settings['poll'].get('max_sockets'),
                                    config.BOT_DEFAULT['poll'].get('max_sockets', 0)))
            for uid, room in (store.rooms(bot)['rooms'] or {}).items():
                if not room.get('room_id') or not (room.get('live') or {}).get('enabled'):
                    continue
                if not stats_enabled and not any(target.get('live') for target in room['targets'].values()):
                    continue
                wanted.setdefault(str(room['room_id']), []).append((bot, uid))
        wanted = dict(islice(wanted.items(), max(0, limit))) if available else {}
        for key in [key for key in self.follow_seen if key[0] not in self.accounts]:
            self.follow_seen.pop(key, None)
        to_stop = []
        to_start = []
        with self.condition:
            if self.closed.is_set():
                return
            self.watch_routes = {
                room_id: (tuple(routes), tuple((bot, uid) for bot, uid in routes if bot in stats_bots))
                for room_id, routes in wanted.items()
            }
            for room_id in self.watchers.keys() - wanted.keys():
                to_stop.append(self.watchers.pop(room_id))
            for room_id, (_, stats_routes) in self.watch_routes.items():
                watcher = self.watchers.get(room_id)
                on_message = (lambda msg, rid=room_id: self._watch_message(rid, msg)) if stats_routes else None
                if watcher is None:
                    watcher = livesocket.LiveWatcher(
                        room_id, lambda kind, rid=room_id: self._watch_transition(rid),
                        self._watch_log, on_message=on_message,
                    )
                    self.watchers[room_id] = watcher
                    to_start.append(watcher)
                else:
                    watcher.on_message = on_message
        for watcher in to_stop:
            watcher.stop()
        for watcher in to_start:
            if self.closed.is_set():
                watcher.stop()
            else:
                watcher.start()

    def _watch_transition(self, room_id):
        for bot, uid in self.watch_routes.get(room_id, ((), ()))[0]:
            self._trigger(bot, uid, 'live')

    def _watch_message(self, room_id, msg):
        # 全 Bot 共用一个房间流；同一礼物、弹幕和观众事件只入队一次，优先选择已确认开播的路由。
        chosen = None
        for bot, uid in self.watch_routes.get(room_id, ((), ()))[1]:
            if not _stats_enabled(store.bot_config(bot)):
                continue
            room = store.rooms(bot)['rooms'].get(uid)
            if room is None or str(room['room_id']) != room_id or not room['live']['enabled']:
                continue
            runtime = room['runtime']
            active = runtime.get('live_status') == 1
            if chosen is None or active:
                chosen = (bot, uid, runtime, active)
                if active:
                    break
        if chosen is None:
            return
        bot, uid, runtime, active = chosen
        with self.stats_ingest_lock:
            if not self.closed.is_set():
                live_stats.record_event(
                    uid, room_id, msg, uname=function.names.get((bot, uid), ''),
                    title=runtime.get('last_title', ''), area=runtime.get('last_area_v2_name', ''),
                    active=active,
                )

    def _sync_follow(self, now):
        """关注流触发：一条请求知道「关注的人里谁发了新动态」，详情仍走 opus。

        未关注的目标 UP 不在 cards 里，自动继续用逐 UP 轮询，不影响功能。
        网络请求全程在 self.condition 锁外执行，避免阻塞宿主 tick。
        """
        due_bots = []
        for bot in tuple(self.accounts):
            settings = store.bot_config(bot)
            if not settings.get('enable', True) or settings.get('dynamic_source') != 'follow':
                continue
            seconds = max(30, _int(settings['poll'].get('dynamic_seconds'), 600))
            if now - self.follow_sync_at.get(bot, 0) < seconds:
                continue
            self.follow_sync_at[bot] = now
            due_bots.append(bot)
        if not due_bots or self.closed.is_set():
            return
        # follow_max_ids 查的是全局共享 SESSDATA 的关注流，一轮最多只发一次请求。
        ids, error = bili_api.follow_max_ids()
        if error or not isinstance(ids, dict) or self.closed.is_set():
            return
        for bot in due_bots:
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
            watched = str(room['room_id']) in self.watchers
            if key in self.pending or not _due(settings, room, kind, now, watched=watched):
                continue
            self.polls.append(_Job(bot, uid, kind, room.get('resolved_at'), now))
            self.pending.add(key)
            account.cursor = uid, kind_index
            account.queued += 1
            budget -= 1
            if not budget:
                break

    def _take(self):
        # 渲染与分群节流共享工作池；一次仅处理一个封账场次，给轮询保留容量。
        if self.finalized_sessions and not self.finalizing:
            self.finalizing = True
            self.running += 1
            return self._run_finalized, (self.finalized_sessions.popleft(),)
        # 优先处理已经拉到的数据；限额降低时，在途工作自然完成，不再超额启动。
        for queue, applying in ((self.applies, True), (self.polls, False)):
            for index, work in enumerate(queue):
                job = work.job if applying else work
                account = self.accounts[job.bot]
                if account.limit == 0:
                    del queue[index]
                    self.pending.remove(job.key)
                    account.queued -= 1
                    return None, ()
                if account.running < account.limit:
                    del queue[index]
                    account.running += 1
                    self.running += 1
                    return self._work, (job, work if applying else None)
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
                work, args = selection
                if work is not None:
                    self.executor.submit(work, *args)
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
        payload, error = _request(job.uid, job.kind, room_id=str(room.get('room_id') or ''))
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
                notices, nickname, backoff, risk = _record(data, room, result, self._record_live_stats)
        if nickname and self._is_mounted(job, store.rooms(job.bot)['rooms'].get(job.uid)):
            function.names[job.bot, job.uid] = nickname
        if result.error:
            code, message = result.error
            store.log(self.proc, f'bot={job.bot} uid={job.uid} kind={job.kind} code={code} {message} '
                      f'backoff={backoff}s', 3)
        if notices or risk:
            self._deliver(job, tuple(_targets(room, job)), notices, risk)

    def _record_live_stats(self, room, result, action, live_status, live_time, nickname):
        job = result.job
        settings = store.bot_config(job.bot)
        room_id = str(room.get('room_id') or result.payload.get('room_id') or '')
        if not room_id or room_id == '0' or not capabilities.can('live_stats') or not _stats_enabled(settings):
            return False
        grace = settings['live_stats']['reconnect_grace_seconds']
        for bot in self.accounts:
            if bot != job.bot and str(store.rooms(bot)['rooms'].get(job.uid, {}).get('room_id')) == room_id:
                other = store.bot_config(bot)
                if _stats_enabled(other):
                    grace = max(grace, other['live_stats']['reconnect_grace_seconds'])
        try:
            if action == 'end':
                live_stats.on_live_end(room_id, end_at=result.checked_at, grace_seconds=grace)
            elif live_status == 1:
                meta = {'uname': nickname or function.names.get((job.bot, job.uid), ''),
                        'title': str(result.payload.get('title') or ''),
                        'area': str(result.payload.get('area_v2_name') or ''),
                        'observed_at': result.checked_at, 'grace_seconds': grace}
                if action == 'start':
                    session_id, resumed = live_stats.on_live_start(job.uid, room_id, start_at=live_time, **meta)
                    if session_id and not resumed:
                        self.stats_fan_jobs[session_id] = job.uid
                    return resumed
                live_stats.ensure_active_session(job.uid, room_id, start_at=live_time, **meta)
        except (OSError, sqlite3.Error) as error:
            store.log(self.proc, f'直播统计状态写入失败：{type(error).__name__}', 3)
        return False

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
        with _card_cache() as cards:
            self._deliver_notices(job, destinations, notices, warning, cards)

    def _deliver_notices(self, job, destinations, notices, warning, cards):
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
                        at_all = False
                        if kind == 'start' and group.get('at_all'):
                            # 锁外查询机器人在群内的管理权限；非管理或无法确认时跳过 @全体 且不扣配额。
                            if not sender.bot_is_group_admin(self.proc, job.bot, target):
                                _send_log(self.proc, job, sid, kind, 'at_all_not_admin')
                            elif not still_current():
                                continue
                            else:
                                at_all = bool(self._claim(job, sid, added_at, notice))
                                current = self._target(job, sid, added_at)
                                if current is None:
                                    continue
                                settings, group, target = current
                                at_all = bool(at_all and group.get('at_all'))
                                if group.get('at_all') and not at_all and target.get('sdk') == 'onebot':
                                    _send_log(self.proc, job, sid, kind, 'at_all_quota_exhausted')
                        mention = kind == 'start' and settings.get('at_subscribers', {}).get('live', True)
                        subscribers = target.get('subscribers', ()) if mention else ()
                        success = _send_notice(self.proc, job, sid, target, group, settings, notice, cards,
                                               at_all=at_all, subscribers=subscribers, still_current=still_current)
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


def _record(data, room, result, record_stats=None):
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
    if kind == 'live':
        notices, nickname = _record_live(room, state, result, record_stats)
    else:
        notices, nickname = _record_feed(state, result)
    return notices, nickname, 0, False


def _record_live(room, state, result, record_stats=None):
    payload = result.payload
    uid = result.job.uid
    nickname = str(payload.get('uname') or '')
    action = live_transition(state, payload)
    live_status = _int(payload.get('live_status'))
    live_time = _int(payload.get('live_time'))
    if not live_time and live_status == 1:
        live_time = (_int(state.get('last_live_time')) if action != 'start' else 0) or result.checked_at
    resumed = record_stats(room, result, action, live_status, live_time, nickname) if record_stats else False
    cover = _live_cover(payload)
    # 参考 StarBot：断流宽限内续接同一场次，只发送首次开播提醒。
    if action and not (action == 'start' and resumed):
        fields = _live_fields(
            room, uid, state, payload, action, live_time or result.checked_at, use_stats=bool(record_stats),
        )
        fields['name'] = nickname or function.names.get((result.job.bot, uid)) or f'UID {uid}'
        notices = (_Notice(action, fields, cover if action != 'end' else '', live_time),)
    else:
        notices = ()
    state.update(live_status=live_status, last_live_time=live_time,
                 last_area_v2_name=str(payload.get('area_v2_name') or ''), last_title=str(payload.get('title') or ''),
                 last_cover=cover)
    if avatar := sender.pick_first_image((payload.get('face'),)):
        state['avatar_url'] = avatar
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
        notices.append(_Notice(kind, fields, image, raw_item=item if kind == 'dynamic' else None))
    return notices, latest_name


def _stats_enabled(settings):
    return settings['enable'] and settings['live_stats']['enabled']


_lifecycle = Lock()
_engine = None


def start(Proc, *, on_session_finalized=None):
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
            # 参考 StarBot：间隔低于 10 秒时提醒，太密容易被 B 站临时封接口。
            for kind in ('live', 'dynamic', 'video'):
                seconds = _int(settings['poll'].get(f'{kind}_seconds'), 0)
                if 0 < seconds < 10:
                    store.log(Proc, '轮询间隔 %s_seconds=%s 低于 10 秒，可能触发 B站风控'
                              % (kind, settings['poll'].get(f'{kind}_seconds')), level=3)
        _engine = _Engine(Proc, accounts, on_session_finalized) if accounts else None


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
             'backing_off': any(backoff.values()), 'kind_backoff': backoff,
             'channels': bili_api.channel_health(), 'logged_in': bili_api.logged_in()}
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
    raw_item = None
    try:
        payload, error = _request(uid, kind, room_id=str(room.get('room_id') or ''))
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
            item = items[-1][2]
            nickname, fields, image = _feed_fields(kind, item)
            if kind == 'dynamic':
                raw_item = item
    except Exception as error:
        store.log(Proc, f'bot={bot_hash} uid={uid} kind={kind} 测试请求异常：{type(error).__name__}', 3)
        return 'failed'
    fields['name'] = nickname or function.names.get((bot_hash, uid)) or f'UID {uid}'
    job = _Job(bot_hash, uid, kind, room.get('resolved_at'))
    notice = _Notice(action, fields, image, raw_item=raw_item)
    with _card_cache() as cards:
        return _test_deliver(Proc, job, notice, destinations, explicit, cards)


def _test_deliver(Proc, job, notice, destinations, explicit, cards):
    bot_hash = job.bot
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
            settings = store.bot_config(bot_hash)
            group = store.rooms(bot_hash)['groups'].get(sid, {})
            success = _send_notice(Proc, job, sid, target, group, settings, notice, cards,
                                   test=True, still_current=still_current)
        except Exception as error:
            _send_log(Proc, job, sid, notice.kind, f'测试发送异常：{type(error).__name__}')
            failed = True
        else:
            sent = sent or success
            if not success and still_current():
                _send_log(Proc, job, sid, notice.kind, '测试发送失败')
                failed = True
    return 'failed' if failed else 'ok' if sent else 'empty'
