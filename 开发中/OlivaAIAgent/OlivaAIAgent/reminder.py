# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 定时提醒 / 定时主动消息
- AI 可用工具 schedule_reminder 设定“N秒后 / 某时刻”触发的提醒
- 到点后：把用户当时要提醒的内容喂给 AI 生成一条自然的提醒话术，然后【主动推送】给用户
- 主动推送而非被动回复：清掉事件里的被动回复 token(reply_msg_id)，OlivOS 会走主动发送
  （官机 qqGuildv2 的被动回复有 5 分钟/5 次限制，几小时后的提醒必须主动发，否则超时失败）
- 任务持久化到 reminders.json；插件重载/重启后自动重挂起未到期任务
- 发送器按 bot 隔离：每条进来的消息都会刷新该 bot 的“可发送事件”，重启后收到任一消息即可恢复推送能力
'''

import copy
import json
import os
import threading
import time
import traceback
from datetime import datetime, timedelta

import OlivaAIAgent

_lock = threading.RLock()
_jobs = {}          # job_id -> job dict
_timers = {}        # job_id -> threading.Timer
_senders = {}       # bot_hash -> 最近一条可用于主动发送的 plugin_event
_counter = [0]


def _path():
    return os.path.join(OlivaAIAgent.conf.dataPath, 'reminders.json')


def _enabled():
    return bool(OlivaAIAgent.conf.get('reminder', 'enable', default=True))


def _nextId():
    with _lock:
        _counter[0] += 1
        return 'rmd%d_%d' % (int(time.time() * 1000), _counter[0])


# ---------------- 发送器登记 ----------------

def registerSender(plugin_event):
    '''每条进来的消息都登记该 bot 的可发送事件，供到点主动推送使用。'''
    try:
        bot_hash = plugin_event.bot_info.hash if plugin_event.bot_info else 'unity'
        _senders[str(bot_hash)] = plugin_event
    except Exception:
        pass


def _cloneActive(pe, send_type, target_id, host_id):
    '''浅克隆事件用于【主动发送】：保留 bot_info/platform/plugin_info 引用(维持连线)，
    但去掉 data.extend 里的被动回复 token，使 OlivOS 走主动推送(qqGuildv2 自带被动/主动回退)。'''
    ev = copy.copy(pe)
    try:
        if pe.data is not None:
            ev.data = copy.copy(pe.data)
            ext = getattr(ev.data, 'extend', None)
            if isinstance(ext, dict):
                ext = dict(ext)
                ext.pop('reply_msg_id', None)   # 关键：清被动 token → 主动发送
                ext.pop('event_id', None)
                ev.data.extend = ext
    except Exception:
        pass
    return ev


# ---------------- 时间解析 ----------------

def parseFireTs(delay_seconds=None, at_time=None, now=None):
    '''把 相对秒数 / 绝对时间串 解析为触发的 epoch 秒。无法解析返回 None。'''
    base = datetime.now() if now is None else datetime.fromtimestamp(now)
    if delay_seconds is not None and str(delay_seconds) != '':
        try:
            d = float(delay_seconds)
            if d < 0:
                return None
            return (base + timedelta(seconds=d)).timestamp()
        except Exception:
            return None
    if at_time is None or str(at_time).strip() == '':
        return None
    s = str(at_time).strip().replace('/', '-').replace('：', ':').replace('  ', ' ')
    fmts_full = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H']
    for f in fmts_full:
        try:
            return datetime.strptime(s, f).timestamp()
        except Exception:
            pass
    # 无年份的 月-日 时:分
    for f in ['%m-%d %H:%M:%S', '%m-%d %H:%M']:
        try:
            dt = datetime.strptime(s, f).replace(year=base.year)
            if dt < base:
                dt = dt.replace(year=base.year + 1)
            return dt.timestamp()
        except Exception:
            pass
    # 纯时刻 HH:MM[:SS] → 今天该时刻，已过则明天
    for f in ['%H:%M:%S', '%H:%M']:
        try:
            t = datetime.strptime(s, f)
            dt = base.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0)
            if dt <= base:
                dt = dt + timedelta(days=1)
            return dt.timestamp()
        except Exception:
            pass
    return None


def fmtTs(ts):
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(ts)


# ---------------- 任务存储 ----------------

def _persist():
    with _lock:
        data = list(_jobs.values())
    try:
        OlivaAIAgent.conf.atomicDump(data, _path())
    except Exception:
        pass


def _load():
    try:
        p = _path()
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            if isinstance(data, list):
                return [j for j in data if isinstance(j, dict) and 'id' in j and 'fire_ts' in j]
    except Exception:
        pass
    return []


def schedule(bot_hash, platform, send_type, target_id, host_id, content,
             requester_id, requester_name, fire_ts):
    '''登记一个提醒任务并挂起定时器。返回 job。'''
    job = {
        'id': _nextId(),
        'bot_hash': str(bot_hash),
        'platform': str(platform),
        'send_type': send_type,
        'target_id': str(target_id) if target_id is not None else None,
        'host_id': str(host_id) if host_id not in (None, '') else None,
        'content': str(content),
        'requester_id': str(requester_id) if requester_id is not None else None,
        'requester_name': str(requester_name) if requester_name else None,
        'fire_ts': float(fire_ts),
        'created_ts': time.time(),
        'retry': 0,
    }
    with _lock:
        _jobs[job['id']] = job
    _persist()
    _arm(job)
    return job


def _arm(job, now=None):
    now = time.time() if now is None else now
    grace = float(OlivaAIAgent.conf.get('reminder', 'grace_seconds', default=5))
    delay = max(0.0, float(job['fire_ts']) - now)
    if delay <= 0:
        delay = grace   # 逾期(如重启后)：给几秒让发送器登记
    jid = job['id']
    with _lock:
        old = _timers.pop(jid, None)
        if old is not None:
            try:
                old.cancel()
            except Exception:
                pass
        t = threading.Timer(delay, _fire, args=(jid,))
        t.daemon = True
        _timers[jid] = t
        t.start()


def loadAndReschedule():
    '''init_after 调用：载入持久化任务并重新挂起定时器。'''
    if not _enabled():
        return 0
    jobs = _load()
    with _lock:
        _jobs.clear()
        for j in jobs:
            j.setdefault('retry', 0)
            _jobs[j['id']] = j
        current = list(_jobs.values())
    for j in current:
        _arm(j)
    return len(current)


def saveAll():
    _persist()


# ---------------- 触发 ----------------

def _clean(text):
    t = str(text).strip()
    if len(t) >= 2 and t[0] in '"“\'' and t[-1] in '"”\'':
        t = t[1:-1].strip()
    return t


def _generateReply(job):
    '''把用户当时要提醒的内容喂给 AI，生成一条自然的主动提醒话术。AI 不可用时兜底纯文本。'''
    conf = OlivaAIAgent.conf
    content = job.get('content', '')
    persona = str(conf.get('ambient', 'personality', default='')).strip() or '你是群里的AI助手，说话自然亲切'
    who = job.get('requester_name') or ''
    sys_prompt = (
        '# 角色设定\n%s\n\n'
        '# 现在的任务\n现在到了用户此前预约的提醒时间点。用户当时请你到这个时间来提醒的内容是：「%s」。\n'
        '请用你自己的口吻，像突然想起来一样，主动、自然地把这条提醒发给对方%s。要求：简短亲切、口语化；'
        '不要暴露你是定时任务或系统；不要复述“你让我提醒你”之类机械措辞；只输出要发送的那句话本身，不要任何解释或引号。'
        % (persona, content, ('（对方是 %s）' % who) if who else '')
    )
    try:
        res = OlivaAIAgent.aiClient.chat(
            [{'role': 'system', 'content': sys_prompt},
             {'role': 'user', 'content': '（时间到了，请生成这条主动提醒消息）'}],
            tools=None, force_no_stream=True, thinking_off=True)
        if res.get('ok') and str(res.get('text', '')).strip():
            return _clean(res['text'])
    except Exception:
        pass
    return '⏰ 提醒：%s' % content


def _activeSend(job, text):
    '''用该 bot 的最近事件主动推送。无可用发送器返回 False。'''
    pe = _senders.get(str(job.get('bot_hash')))
    if pe is None:
        return False
    msg = str(text)
    # 群里 @ 一下提醒对象，确保被看到
    if job.get('send_type') == 'group' and job.get('requester_id'):
        msg = '[CQ:at,qq=%s] %s' % (job['requester_id'], msg)
    try:
        ev = _cloneActive(pe, job['send_type'], job['target_id'], job.get('host_id'))
        ev.send(job['send_type'], job['target_id'], msg, host_id=job.get('host_id'))
        return True
    except Exception:
        OlivaAIAgent.conf.log(OlivaAIAgent.conf.gProc, 3, '提醒主动发送失败:\n' + traceback.format_exc())
        return False


def _fire(job_id):
    with _lock:
        job = _jobs.get(job_id)
        _timers.pop(job_id, None)
    if not job:
        return
    try:
        text = _generateReply(job)
        ok = _activeSend(job, text)
    except Exception:
        OlivaAIAgent.conf.log(OlivaAIAgent.conf.gProc, 3, '提醒触发异常:\n' + traceback.format_exc())
        ok = False
    if ok:
        with _lock:
            _jobs.pop(job_id, None)
        _persist()
        OlivaAIAgent.conf.debugLog(OlivaAIAgent.conf.gProc, '提醒已推送: %s' % job.get('content', '')[:40])
        return
    # 没有可用发送器(如刚重启还没收到该 bot 消息)：短延时重试，直到某条消息登记了发送器
    max_retry = int(OlivaAIAgent.conf.get('reminder', 'no_sender_max_retry', default=60))
    retry_gap = float(OlivaAIAgent.conf.get('reminder', 'no_sender_retry_seconds', default=20))
    with _lock:
        cur = _jobs.get(job_id)
        if cur is None:
            return
        cur['retry'] = int(cur.get('retry', 0)) + 1
        if cur['retry'] > max_retry:
            _jobs.pop(job_id, None)
            _persist()
            OlivaAIAgent.conf.log(OlivaAIAgent.conf.gProc, 3,
                                  '提醒放弃(长时间无可用发送器): %s' % cur.get('content', '')[:40])
            return
        t = threading.Timer(retry_gap, _fire, args=(job_id,))
        t.daemon = True
        _timers[job_id] = t
        t.start()


# ---------------- 查询 / 取消 ----------------

def listJobs(bot_hash=None, requester_id=None, send_type=None, target_id=None):
    with _lock:
        jobs = list(_jobs.values())
    out = []
    for j in jobs:
        if bot_hash is not None and str(j.get('bot_hash')) != str(bot_hash):
            continue
        if requester_id is not None and str(j.get('requester_id')) != str(requester_id):
            continue
        if send_type is not None and j.get('send_type') != send_type:
            continue
        if target_id is not None and str(j.get('target_id')) != str(target_id):
            continue
        out.append(j)
    out.sort(key=lambda x: x.get('fire_ts', 0))
    return out


def cancel(job_id):
    with _lock:
        job = _jobs.pop(job_id, None)
        t = _timers.pop(job_id, None)
    if t is not None:
        try:
            t.cancel()
        except Exception:
            pass
    if job is not None:
        _persist()
    return job


def countForUser(bot_hash, requester_id):
    return len(listJobs(bot_hash=bot_hash, requester_id=requester_id))


def total():
    with _lock:
        return len(_jobs)


def _resetForTest():
    '''仅测试用：清空内存状态与定时器。'''
    with _lock:
        for t in _timers.values():
            try:
                t.cancel()
            except Exception:
                pass
        _timers.clear()
        _jobs.clear()
        _senders.clear()
