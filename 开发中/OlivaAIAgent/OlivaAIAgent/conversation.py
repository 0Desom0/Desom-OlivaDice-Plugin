# -*- encoding: utf-8 -*-
'''群聊接话策略：线程归属、可选上下文隔离、工具门控与接话短日志。'''

import json
import os
import re
import threading
import time

import OlivaAIAgent

REASON_AT_ME = 'at_me'
REASON_NAMED = 'named'
REASON_THREAD = 'thread_continue'
REASON_CHITCHAT = 'chitchat'
REASON_PROBABILITY = 'probability'
REASON_INTERRUPT = 'interrupt'
REASON_HISTORY = 'history_short'
REASON_SLACK = 'slack'
REASON_FIRST_THINK = 'first_thinking'
REASON_MAIN_SKIP = 'main_skip'

REASON_ZH = {
    REASON_AT_ME: '提及我',
    REASON_NAMED: '点名',
    REASON_THREAD: '话题延续',
    REASON_CHITCHAT: '闲聊',
    REASON_PROBABILITY: '未过插话概率',
    REASON_INTERRUPT: '插入他人对话',
    REASON_HISTORY: '群聊历史不足',
    REASON_SLACK: '等待期间出现更新消息',
    REASON_FIRST_THINK: '前置判断不参与',
    REASON_MAIN_SKIP: '主模型不参与',
}

SEARCH_TOOLS = frozenset({'web_search', 'fetch_url'})
COMMAND_TOOLS = frozenset({'run_command'})

_thread_lock = threading.RLock()
_threads = {}
_budget_lock = threading.RLock()
_budget = {'date': '', 'usage': {}}


def _scopeKey(platform, group_id):
    return '%s|%s' % (platform, group_id)


def _affinityConf():
    value = OlivaAIAgent.conf.get('ambient', 'thread_affinity', default={}) or {}
    return value if isinstance(value, dict) else {}


def _isolationConf():
    value = OlivaAIAgent.conf.get('ambient', 'context_isolation', default={}) or {}
    return value if isinstance(value, dict) else {}


def affinityEnabled():
    return bool(_affinityConf().get('enable', True))


def isolationEnabled():
    return bool(_isolationConf().get('enable', False))


def interruptProbabilityScale():
    try:
        scale = float(_affinityConf().get('interrupt_probability_scale', 0.2))
    except (TypeError, ValueError):
        scale = 0.2
    return max(0.0, min(1.0, scale))


def _ttlSec():
    try:
        return max(15, int(_affinityConf().get('ttl_sec', 180)))
    except (TypeError, ValueError):
        return 180


def _userId(value):
    if value in [None, '', '-1', -1]:
        return ''
    return str(value)


def botAliases(plugin_event=None, self_id=None):
    names = []
    keywords = OlivaAIAgent.conf.get('trigger', 'keywords', default=[]) or []
    if isinstance(keywords, str):
        keywords = [keywords]
    names.extend(str(item).strip() for item in keywords if str(item).strip())
    if self_id not in [None, '']:
        try:
            display = OlivaAIAgent.memberDirectory.displayName(plugin_event, self_id)
        except Exception:
            display = None
        if display:
            names.append(str(display).strip())
    return list(dict.fromkeys(item for item in names if item))


def classifyReason(parsed, affinity=None, plugin_event=None, self_id=None):
    '''本地信号：at我 / 点名 / 话题延续 / 闲聊。'''
    parsed = parsed if isinstance(parsed, dict) else {}
    affinity = affinity if isinstance(affinity, dict) else {}
    if parsed.get('at_me') or parsed.get('reply_to_me'):
        return REASON_AT_ME
    text = str(parsed.get('text') or '')
    for alias in botAliases(plugin_event, self_id):
        if alias and alias in text:
            return REASON_NAMED
    if affinity.get('is_owner') or affinity.get('is_participant'):
        return REASON_THREAD
    if affinity.get('is_interrupt'):
        return REASON_CHITCHAT
    return REASON_CHITCHAT


def observeIncoming(platform, group_id, parsed, user_id, nickname=None, force=False, directed=False):
    '''根据当前消息更新本群对话线程，返回归属快照。'''
    parsed = parsed if isinstance(parsed, dict) else {}
    uid = _userId(user_id)
    nick = str(nickname or '').strip()
    now = time.time()
    ttl = _ttlSec()
    directed = bool(directed or parsed.get('at_me') or parsed.get('reply_to_me') or force)
    mentions = [
        _userId(item) for item in (parsed.get('at_list') or [])
        if _userId(item)
    ]
    key = _scopeKey(platform, group_id)
    with _thread_lock:
        state = dict(_threads.get(key) or {})
        owner_id = _userId(state.get('owner_id'))
        participants = [
            _userId(item) for item in (state.get('user_ids') or [])
            if _userId(item)
        ]
        stale = (now - float(state.get('updated_at') or 0)) > ttl
        if not affinityEnabled():
            owner_id = uid
            participants = [uid] if uid else []
            stale = False
        elif stale or not owner_id:
            owner_id = uid
            participants = [uid] if uid else []
        elif directed or uid == owner_id or uid in participants:
            if uid and uid not in participants:
                participants.append(uid)
            if directed and uid:
                owner_id = uid
        for mention in mentions:
            if mention not in participants:
                participants.append(mention)
        is_owner = bool(uid and uid == owner_id)
        is_participant = bool(uid and uid in participants)
        owner_active = (now - float(state.get('last_owner_at') or 0)) <= ttl
        bot_active = (now - float(state.get('last_bot_at') or 0)) <= ttl
        is_interrupt = bool(
            affinityEnabled()
            and uid
            and not is_owner
            and not is_participant
            and owner_id
            and owner_active
            and bot_active
        )
        if is_owner:
            state['last_owner_at'] = now
        if not is_interrupt:
            state['owner_id'] = owner_id
            state['user_ids'] = participants
            state['owner_name'] = nick if is_owner else state.get('owner_name', '')
            state['updated_at'] = now
            _threads[key] = state
        snapshot = {
            'owner_id': owner_id,
            'owner_name': state.get('owner_name', ''),
            'user_ids': list(participants),
            'is_owner': is_owner,
            'is_participant': is_participant,
            'is_interrupt': is_interrupt,
        }
    snapshot['reason'] = classifyReason(parsed, snapshot)
    return snapshot


def observeOutgoing(platform, group_id):
    now = time.time()
    key = _scopeKey(platform, group_id)
    with _thread_lock:
        state = dict(_threads.get(key) or {})
        state['last_bot_at'] = now
        state['updated_at'] = now
        _threads[key] = state


def clearThread(platform, group_id):
    with _thread_lock:
        _threads.pop(_scopeKey(platform, group_id), None)


def _isBotEntry(entry):
    return entry.get('nickname') is None and entry.get('user_id') in [None, '']


def _isThreadEntry(entry, participants):
    if _isBotEntry(entry):
        return True
    return _userId(entry.get('user_id')) in participants


def formatCrowdDigest(entries, limit=6):
    try:
        size = max(0, int(limit))
    except (TypeError, ValueError):
        size = 6
    if size <= 0:
        return ''
    parts = []
    for entry in list(entries or [])[-size:]:
        nick = entry.get('nickname') or '我'
        text = re.sub(r'\s+', ' ', str(entry.get('message') or '')).strip()[:40]
        if text:
            parts.append('%s:%s' % (nick, text))
    return ' / '.join(parts)


def splitContext(history, affinity=None):
    '''当前线程全文 + 其余近况摘要。隔离关闭时 thread 为空列表，调用方回退整段历史。'''
    history = list(history or [])
    if not isolationEnabled():
        return history, ''
    cfg = _isolationConf()
    try:
        thread_size = max(1, int(cfg.get('thread_history_size', 8)))
    except (TypeError, ValueError):
        thread_size = 8
    try:
        digest_size = max(0, int(cfg.get('crowd_digest_size', 6)))
    except (TypeError, ValueError):
        digest_size = 6
    affinity = affinity if isinstance(affinity, dict) else {}
    participants = set(_userId(item) for item in (affinity.get('user_ids') or []) if _userId(item))
    owner = _userId(affinity.get('owner_id'))
    if owner:
        participants.add(owner)
    if not participants:
        return history[-thread_size:], formatCrowdDigest(history[:-thread_size], digest_size)
    thread = [entry for entry in history if _isThreadEntry(entry, participants)][-thread_size:]
    thread_ids = {id(entry) for entry in thread}
    crowd = [entry for entry in history if id(entry) not in thread_ids]
    return thread, formatCrowdDigest(crowd, digest_size)


def parseParticipation(raw, fallback_reason=''):
    '''解析前置模型输出，返回 (NEXT|SKIP, reason_code)。'''
    text = str(raw or '').strip()
    value = None
    reason = ''
    match = re.search(r'\{.*\}', text, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
        except Exception:
            data = None
        if isinstance(data, dict):
            for key in ('d', 'decision', 'reply', 'should_reply', 'result'):
                if key in data:
                    value = data.get(key)
                    break
            for key in ('r', 'reason', 'code', 'signal'):
                if data.get(key) not in [None, '']:
                    reason = str(data.get(key)).strip()
                    break
    if isinstance(value, bool):
        decision = 'NEXT' if value else 'SKIP'
    else:
        target = str(value if value is not None else text).strip().upper()
        if re.search(r'\bSKIP\b|不回复|不参与|跳过|无需回复|不需要(?:回复|接话)?|保持沉默', target, re.I):
            decision = 'SKIP'
        elif re.search(r'\bNEXT\b|回复|参与|接话|需要回答', target, re.I):
            decision = 'NEXT'
        else:
            decision = 'NEXT'
    normalized = reason.lower().replace('-', '_')
    aliases = {
        'at': REASON_AT_ME,
        'atme': REASON_AT_ME,
        'mention': REASON_AT_ME,
        'name': REASON_NAMED,
        'named': REASON_NAMED,
        'call': REASON_NAMED,
        'thread': REASON_THREAD,
        'continue': REASON_THREAD,
        'thread_continue': REASON_THREAD,
        'chat': REASON_CHITCHAT,
        'chitchat': REASON_CHITCHAT,
        'idle': REASON_CHITCHAT,
    }
    reason_code = aliases.get(normalized, normalized if normalized in REASON_ZH else fallback_reason)
    return decision, reason_code or fallback_reason or REASON_CHITCHAT


def participationHint(parsed, affinity, directed=False):
    if directed or (isinstance(parsed, dict) and (parsed.get('at_me') or parsed.get('reply_to_me'))):
        return '本轮有明确的@你或引用你的定向信号。'
    if affinity.get('is_interrupt'):
        owner = affinity.get('owner_name') or affinity.get('owner_id') or '其他人'
        return '本轮没有定向信号，且当前正在与%s连着聊，这条是别人插话。' % owner
    if affinity.get('is_owner') or affinity.get('is_participant'):
        return '本轮没有定向信号，但是当前对话线程的延续。'
    return '本轮没有明确的@你或引用你的定向信号。'


def logDecision(
    Proc,
    trace_id,
    decision,
    reason='',
    history_count=0,
    tools=False,
    interrupted='',
    result=None,
    messages=None,
):
    reason_text = REASON_ZH.get(reason, reason or '未标注')
    parts = ['接话', str(decision), '原因=%s' % reason_text, '历史=%s' % int(history_count or 0)]
    parts.append('工具=%s' % ('开' if tools else '关'))
    if interrupted:
        parts.append('打断=%s' % interrupted)
    try:
        OlivaAIAgent.conf.log(Proc, 2, ' | '.join(parts))
    except Exception:
        pass
    fields = {
        'decision': decision,
        'reason': reason or reason_text,
        'history_count': int(history_count or 0),
        'tools_enabled': bool(tools),
    }
    if interrupted:
        fields['interrupted'] = interrupted
    if result is not None:
        fields['result'] = json.dumps(result, ensure_ascii=False) if isinstance(result, list) else str(result)
    if messages is not None:
        fields['messages'] = messages
    OlivaAIAgent.conf.traceLog(Proc, 'conversation.decision', trace_id, **fields)


def _toolFamily(name, mcp_item=None):
    tool_name = str(name or '')
    if tool_name in SEARCH_TOOLS:
        return 'search'
    if tool_name in COMMAND_TOOLS:
        return 'run_command'
    if mcp_item is not None:
        return 'mcp'
    try:
        if OlivaAIAgent.mcp.getToolItem(tool_name) is not None:
            return 'mcp'
    except Exception:
        pass
    return ''


def _groupAllowed(family, group_id):
    groups = OlivaAIAgent.conf.get('permissions', '%s_groups' % family, default=[]) or []
    if isinstance(groups, str):
        groups = [groups]
    allowed = [str(item).strip() for item in groups if str(item).strip()]
    if not allowed:
        return True
    return str(group_id) in allowed or 'all' in allowed


def _budgetPath():
    return os.path.join(OlivaAIAgent.conf.dataPath, 'tool_budget.json')


def _today():
    return time.strftime('%Y-%m-%d')


def _loadBudget():
    global _budget
    today = _today()
    if _budget.get('date') == today and isinstance(_budget.get('usage'), dict):
        return
    data = {'date': today, 'usage': {}}
    try:
        with open(_budgetPath(), 'r', encoding='utf-8') as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict) and loaded.get('date') == today and isinstance(loaded.get('usage'), dict):
            data = loaded
    except Exception:
        pass
    _budget = data


def _saveBudget():
    try:
        OlivaAIAgent.conf.releaseDir(os.path.dirname(_budgetPath()))
        OlivaAIAgent.conf.atomicDump(_budget, _budgetPath())
    except Exception:
        pass


def _dailyLimit(family):
    try:
        return max(0, int(OlivaAIAgent.conf.get('permissions', '%s_daily_limit' % family, default=0) or 0))
    except (TypeError, ValueError):
        return 0


def checkToolGate(name, ctx, consume=False):
    '''群白名单 + 每日次数。未配置限制时直接放行。'''
    family = _toolFamily(name)
    if not family:
        return True, ''
    group_id = ''
    if isinstance(ctx, dict):
        group_id = str(ctx.get('group_id') or '')
        if ctx.get('func_type') != 'group_message':
            return True, ''
    if not _groupAllowed(family, group_id):
        labels = {'search': '搜索', 'run_command': 'run_command', 'mcp': 'MCP'}
        return False, '本群未开放%s工具' % labels.get(family, family)
    limit = _dailyLimit(family)
    if limit <= 0:
        return True, ''
    key = '%s|%s' % (ctx.get('platform', ''), group_id)
    with _budget_lock:
        _loadBudget()
        usage = _budget.setdefault('usage', {}).setdefault(key, {})
        used = int(usage.get(family, 0) or 0)
        if used >= limit:
            return False, '本群今日%s次数已用完（%s/%s）' % (family, used, limit)
        if consume:
            usage[family] = used + 1
            _saveBudget()
    return True, ''


def filterToolNames(names, ctx):
    result = []
    for name in names or []:
        ok, _why = checkToolGate(name, ctx, consume=False)
        if ok:
            result.append(name)
    return result


def resetBudgetForTest():
    global _budget
    with _budget_lock:
        _budget = {'date': _today(), 'usage': {}}
    with _thread_lock:
        _threads.clear()
