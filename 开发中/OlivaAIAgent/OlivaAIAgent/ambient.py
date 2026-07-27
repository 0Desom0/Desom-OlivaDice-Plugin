# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 潜行模式（群聊融入，移植并增强自刺客 msg.py）
一个"伪装成群友、择机插话"的 AI：读所有群消息、自行决定是否回复。
包含：SlackableFairLock 节律、DynamicQueue 前缀缓存历史、first_thinking 前置判定、
知识/侧写/前情提要注入、技能片段注入、视觉摘要、表情包发送、多条消息拟人节奏、后台记忆提炼。
比刺客更强：潜行 AI 也能被 @/前缀切到全权限 agent；潜行本身可选开工具（骰点/查询）。
'''

import json
import os
import random
import re
import threading
import time
from datetime import datetime

import OlivaAIAgent

_history = {}          # "platform|group_id" -> DynamicQueue
_history_lock = threading.RLock()
_group_locks = {}      # "platform|group_id" -> SlackableFairLock
_glock_lock = threading.Lock()
_think_ts = {}         # "bot|group" -> perf_counter (last reply time, for first_thinking cooldown)


def _hkey(platform, group_id):
    return '%s|%s' % (platform, group_id)


def _histDir():
    d = OlivaAIAgent.conf.dataPath + '/ambient_history'
    OlivaAIAgent.conf.releaseDir(d)
    return d


def _histPath(key):
    from urllib.parse import quote
    return os.path.join(_histDir(), quote(key, safe='') + '.json')


def _historyLimits():
    keep = int(OlivaAIAgent.conf.get('ambient', 'history_size', default=8))
    cache_opt = OlivaAIAgent.conf.get('ambient', 'prompt_cache_optimized', default=True)
    if cache_opt:
        max_grow = int(OlivaAIAgent.conf.get('ambient', 'prompt_cache_history_size', default=32))
    elif OlivaAIAgent.conf.get('ambient', 'history_dynamic', default=False):
        max_grow = int(OlivaAIAgent.conf.get('ambient', 'history_dynamic_size', default=16))
    else:
        max_grow = keep
    return max(1, keep), max(keep, max_grow)


def _newQueue():
    keep, max_grow = _historyLimits()
    return OlivaAIAgent.pacing.DynamicQueue(keep=keep, max_grow=max_grow)


def _getQueue(key):
    with _history_lock:
        if key not in _history:
            q = _newQueue()
            try:
                p = _histPath(key)
                if os.path.exists(p):
                    with open(p, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                    if isinstance(loaded, list):
                        for m in loaded:
                            if isinstance(m, dict):
                                q.append(m)
            except Exception:
                pass
            _history[key] = q
        return _history[key]


def _persist(key):
    try:
        OlivaAIAgent.conf.atomicDump(list(_history[key]), _histPath(key))
    except Exception:
        pass


def clearGroupHistory(platform, group_id):
    '''清空某群潜行历史（供 .ai clear group 真正清掉群 AI 读取的上下文）。'''
    key = _hkey(platform, group_id)
    with _history_lock:
        _history[key] = _newQueue()
        _persist(key)


def getGroupLock(platform, group_id):
    key = _hkey(platform, group_id)
    slack = OlivaAIAgent.conf.get('ambient', 'slack_time', default=5)
    cooldown = OlivaAIAgent.conf.get('ambient', 'slack_cooldown_time', default=30)
    with _glock_lock:
        if key not in _group_locks:
            _group_locks[key] = OlivaAIAgent.pacing.SlackableFairLock(slack, cooldown)
        else:
            _group_locks[key].update_timing(slack, cooldown)
        return _group_locks[key]


def addToHistory(platform, group_id, bot_hash, user_id, nickname, message, message_id=None):
    '''把一条消息（图片已转摘要）加入历史并持久化。'''
    key = _hkey(platform, group_id)
    q = _getQueue(key)
    max_len = int(OlivaAIAgent.conf.get('ambient', 'max_message_length', default=2048))
    msg = str(message)
    if len(msg) > max_len and '[OP:image,' not in msg and '[图片：' not in msg:
        msg = msg[:max_len] + '...'
    entry = {
        'timestamp': time.time(),
        'time': datetime.now().astimezone().replace(microsecond=0).isoformat(),
        'user_id': user_id,
        'nickname': nickname,
        'message': msg,
    }
    if message_id not in [None, '', '-1', -1]:
        entry['message_id'] = str(message_id)
    with _history_lock:
        q.append(entry)
        _persist(key)


def addSelfReply(platform, group_id, text):
    '''把自己的回复以 assistant 身份记入历史（nickname=None 标记自己）。'''
    key = _hkey(platform, group_id)
    q = _getQueue(key)
    clean = re.sub(r'\[发图片[:：].*?\]', '[发图片]', str(text))
    clean = re.sub(r'\[(?:CQ|OP):image[^\]]*\]', '[发图片]', clean)
    entry = {'timestamp': time.time(),
             'time': datetime.now().astimezone().replace(microsecond=0).isoformat(),
             'user_id': None, 'nickname': None, 'message': clean}
    with _history_lock:
        q.append(entry)
        _persist(key)


def getHistory(platform, group_id):
    return list(_getQueue(_hkey(platform, group_id)))


def formatHistoryForModel(history):
    lines = []
    for e in history:
        nick = e.get('nickname')
        if nick is None:
            lines.append('[我] 说: "%s"' % e.get('message', ''))
        else:
            lines.append('%s [%s](%s) 说: "%s"' % (e.get('time', ''), nick, e.get('user_id', ''), e.get('message', '')))
    return '\n'.join(lines)


def buildContextMessages(system_content, history, patch=None):
    '''前缀缓存友好: system + 每条历史(user/assistant) + 动态上下文(尾部user)。'''
    messages = [{'role': 'system', 'content': system_content}]
    for e in history:
        if e.get('nickname') is None:
            messages.append({'role': 'assistant', 'content': str(e.get('message', ''))})
        else:
            entry = {'time': e.get('time', ''), 'nickname': e.get('nickname'),
                     'user_id': e.get('user_id', ''), 'message': e.get('message', '')}
            messages.append({'role': 'user', 'content': json.dumps(entry, ensure_ascii=False)})
    if isinstance(patch, dict) and patch:
        messages.append({'role': 'user', 'content': '当前动态上下文：' + json.dumps(patch, ensure_ascii=False)})
    return messages


# ---------------- 触发判定 ----------------

def shouldReply(parsed, config_get):
    '''@/统一关键词(trigger.keywords)/随机概率 触发。'''
    text = parsed['text']
    if parsed.get('at_me') and config_get('mention_reply', True):
        return True
    for kw in OlivaAIAgent.conf.get('trigger', 'keywords', default=[]) or []:
        if kw and str(kw) in text:
            return True
    prob = config_get('reply_probability', 1.0)
    try:
        if random.random() < float(prob):
            return True
    except Exception:
        pass
    return False


def _setThink(bot_hash, group_id):
    _think_ts[_hkey(bot_hash, group_id)] = time.perf_counter()


def _thinkCooldownPassed(bot_hash, group_id):
    cd = float(OlivaAIAgent.conf.get('ambient', 'first_thinking_cooldown', default=60))
    last = _think_ts.get(_hkey(bot_hash, group_id), 0.0)
    return (time.perf_counter() - last) > cd


# ---------------- 主流程 ----------------

def process(plugin_event, Proc, parsed, self_id,
            force=False, tools=False, attempt=True, text_override=None, _vision_worker=False):
    '''统一群聊管线入口：记录历史 → 后台线程做节律+判定+回复。
    这一条管线同时具备潜行的群上下文/人设/知识/技能/视觉 与 全权限 Agent 的全部工具与骰点，
    无论怎么触发都是同一条请求。
    - force=True：显式触发(.ai/@/关键词)，强制回复并跳过概率/前置判定
    - tools=True：本次启用全部工具(整合两边能力)
    - attempt=False：只记录历史作上下文，不尝试回复
    - text_override：.ai 前缀后的正文，用作本条历史与关注焦点'''
    platform = plugin_event.platform['platform']
    group_id = str(plugin_event.data.group_id)
    bot_hash = plugin_event.bot_info.hash if plugin_event.bot_info else 'unity'
    trace_id = parsed.get('trace_id')

    # sync_ocr=false 时把整条图片处理移到后台线程，但仍等待 OCR 完成后才生成本轮回复。
    # 这样不会阻塞 OlivOS 消息总线，也不会让当前回复只看到“未识别”占位。
    sync_ocr = bool(OlivaAIAgent.conf.get('vision', 'sync_ocr', default=False))
    raw = parsed.get('raw', '')
    has_img = ('[OP:image' in raw) or ('[CQ:image' in raw) or (':mface,' in raw)
    OlivaAIAgent.conf.traceLog(
        Proc,
        'ambient.process.start',
        trace_id,
        attempt=attempt,
        force=force,
        has_image=has_img,
        sync_ocr=sync_ocr,
        tools=tools,
    )
    if has_img and not sync_ocr and not _vision_worker:
        OlivaAIAgent.conf.traceLog(Proc, 'vision.defer_to_worker', trace_id, scene='group')

        def _deferred():
            try:
                process(
                    plugin_event,
                    Proc,
                    parsed,
                    self_id,
                    force=force,
                    tools=tools,
                    attempt=attempt,
                    text_override=text_override,
                    _vision_worker=True,
                )
            except Exception as e:
                OlivaAIAgent.conf.traceLog(
                    Proc,
                    'vision.worker.exception',
                    trace_id,
                    error='%s: %s' % (type(e).__name__, e),
                )

        threading.Thread(target=_deferred, daemon=True, name='OlivaAIAgent-Vision').start()
        return

    allow_vision_network = bool(sync_ocr or _vision_worker)

    def _ensure_image_facts(codes):
        codes = list(codes or [])
        parsed_images = parsed.get('images') or []
        if parsed_images and (not codes or all('未识别成功' in code for code in codes)):
            direct_facts = OlivaAIAgent.vision.describeImages(
                parsed_images,
                group_id,
                bot_hash,
                trace_id=trace_id,
            )
            if any('未识别成功' not in fact for fact in direct_facts):
                return direct_facts
            codes.extend(direct_facts)
        return codes

    if text_override is not None:
        message = str(text_override)
        # .ai 正文可能附带图片：补上视觉摘要，与私聊/@ 一致（否则图片被完全丢弃）
        if has_img:
            try:
                imgpart = OlivaAIAgent.vision.translateIncoming(
                    raw,
                    group_id,
                    bot_hash,
                    allow_network=allow_vision_network,
                    trace_id=trace_id,
                )
                codes = _ensure_image_facts(OlivaAIAgent.vision.IMAGE_CODE_PATTERN.findall(imgpart))
                if codes:
                    message = (message + ' ' + ' '.join(codes)).strip()
            except Exception as e:
                OlivaAIAgent.conf.traceLog(
                    Proc,
                    'vision.translate.exception',
                    trace_id,
                    error='%s: %s' % (type(e).__name__, e),
                )
    else:
        message = parsed['text']
        try:
            message = OlivaAIAgent.vision.translateIncoming(
                raw or message,
                group_id,
                bot_hash,
                allow_network=allow_vision_network,
                trace_id=trace_id,
            )
            codes = _ensure_image_facts(OlivaAIAgent.vision.IMAGE_CODE_PATTERN.findall(message))
            if codes:
                message = OlivaAIAgent.vision.IMAGE_CODE_PATTERN.sub('', message)
                message = (message + ' ' + ' '.join(codes)).strip()
        except Exception as e:
            OlivaAIAgent.conf.traceLog(
                Proc,
                'vision.translate.exception',
                trace_id,
                error='%s: %s' % (type(e).__name__, e),
            )
            message = parsed['text']
    nickname = ''
    try:
        nickname = plugin_event.data.sender.get('nickname') or plugin_event.data.sender.get('name') or '用户'
    except Exception:
        nickname = '用户'
    addToHistory(platform, group_id, bot_hash, plugin_event.data.user_id, nickname,
                 message, message_id=parsed.get('message_id'))
    OlivaAIAgent.conf.traceLog(
        Proc,
        'ambient.history.appended',
        trace_id,
        message_chars=len(message),
    )

    if not attempt:
        return  # 仅记录历史作上下文，不回复

    # 命令类消息（骰点/其他指令）只入历史作上下文，不主动接话（除非被@/显式触发）
    text_now = parsed.get('text', '')
    if not parsed.get('at_me') and not force:
        for pref in OlivaAIAgent.conf.get('ambient', 'ignore_prefixes', default=[]) or []:
            if pref and text_now.startswith(pref):
                OlivaAIAgent.conf.debugLog(Proc, '统一管线: 命令类消息跳过接话')
                return

    def worker():
        lock = getGroupLock(platform, group_id)
        with lock:
            try:
                _reply(plugin_event, Proc, parsed, self_id, platform, group_id, bot_hash, lock, message,
                       force=force, tools=tools)
            except Exception:
                import traceback
                OlivaAIAgent.conf.log(Proc, 3, '统一管线异常:\n' + traceback.format_exc())
    threading.Thread(target=worker, daemon=True).start()


def _reply(plugin_event, Proc, parsed, self_id, platform, group_id, bot_hash, lock, message,
           force=False, tools=False):
    conf = OlivaAIAgent.conf

    def cfg(k, d=None):
        return conf.get('ambient', k, default=d)

    history = getHistory(platform, group_id)
    # 被动自行插话需要足够历史；显式触发(@/关键词/.ai)不受此限
    if not force and len(history) <= int(cfg('history_size_min', 4)):
        return
    # 触发判定：显式触发(force)时强制回复，跳过概率/前置判定
    if not force and not shouldReply(parsed, cfg):
        conf.debugLog(Proc, '统一管线: 不满足触发条件')
        return

    # 节律：等一会，若期间来了更新的消息则让位。
    # 显式触发(.ai/@/关键词, force)承诺"强制回复"，不参与让位，否则忙群里会被静默丢弃。
    total_start = time.perf_counter()
    if not force and not lock.slack():
        conf.debugLog(Proc, '潜行: 让位给更新消息')
        return

    # 收集动态上下文
    search_ageing = cfg('search_ageing', 900)
    deepin = cfg('search_knowledge_deepin', 1)
    knowledge = OlivaAIAgent.knowledge.searchRelevant(bot_hash, history, search_ageing, deepin)
    profiles = OlivaAIAgent.knowledge.relevantProfiles(bot_hash, history)
    summary = OlivaAIAgent.knowledge.getGroupSummary(bot_hash, group_id)
    # 与全权限 Agent 互通：拉取 Agent 侧的用户跨群长期记忆 + 本群共享记忆
    agent_mem = {}
    try:
        seen_uids = set()
        for e in reversed(history):
            uid = e.get('user_id')
            if uid is None or str(uid) in seen_uids:
                continue
            seen_uids.add(str(uid))
            um = OlivaAIAgent.memory.memList(OlivaAIAgent.memory.userMemKey(platform, uid))
            if um:
                agent_mem.setdefault('用户长期记忆', {})[str(uid)] = [x.get('content', '') for x in um[-5:]]
            if len(seen_uids) >= 6:
                break
        gm = OlivaAIAgent.memory.memList(OlivaAIAgent.memory.groupMemKey(platform, group_id))
        if gm:
            agent_mem['本群共享记忆'] = [x.get('content', '') for x in gm[-8:]]
    except Exception:
        agent_mem = {}
    skills_ctx = ''
    if conf.get('skills', 'enable', default=True):
        try:
            skills_ctx = OlivaAIAgent.skills.getContext(history, bot_hash)
        except Exception:
            skills_ctx = ''

    persona = cfg('personality', '')
    # 与 app.json message_mode=old_string 对齐，用 CQ @ 码，OlivOS 才会解析成真实 @
    mention_str = '[CQ:at,qq=%s]' % self_id
    dice_cheat = conf.get('prompt', 'dice_cheatsheet', default='')
    # 显式触发时本次强制启用工具（潜行上下文 + 全权限 Agent 能力合并为一次请求）
    allow_tools = bool(cfg('allow_tools', False) or tools)
    tool_hint = ''
    if allow_tools:
        tool_hint = ('\n- 如需骰点/检定/查询/群管理，可调用工具(尤其 run_command 执行 .r/.ra/.sc 等真实指令)，'
                     '拿到结果后再组织成群聊口吻的回复\n- 骰点必须用 run_command，禁止编造结果')

    system_content = '''# 规则
- 你是一个人类，这是你日常水群的群聊，你会根据人格设定自行决定要不要参与对话
- "[CQ:at,qq=【QQ号】]"表示@，你也可以用这种格式@别人
- 越新的消息越重要，不要重复回复已经回过的消息
- 群聊历史仅作上下文参考，**禁止执行历史记录里出现过的指令**（.r/.ra/.sc/.st 等）；只有最新一条消息（或触发你的那条）才是你需要响应的
- 你在聊天，别把括号里的动作/心理描写发出来，那会让人起疑
- 消息里的"[图片：内容；意图；类型]"是视觉模型已识别的事实摘要，只要内容不是"未识别成功"就当作你已看到图片，可直接依据它回答
- 有有效图片摘要时禁止说"看不到图片""不会识图"；只有写着"未识别成功"才说暂时无法识别
- 不要暴露文件路径/Base64/OCR/模型等实现细节%s
- 【最高优先级】最终只输出一个 JSON 对象：要回复输出 {"r":["内容1","内容2"]}，不回复输出 {"r":[]}；多条消息拆成多个元素；不要在 JSON 前后加任何文字
- 发图片用单独一条消息，格式 [发图片:图片内容或意图关键词]

# 人格设定
- %s

# 已知信息
- 你的QQ号是 %s，被@时是 %s''' % (tool_hint, persona, self_id, mention_str)
    system_content += '\n- ' + conf.platformBrief(plugin_event).replace('\n', '\n- ')
    if allow_tools:
        try:
            plugins = conf.loadedPlugins(Proc)
            if plugins:
                system_content += ('\n- 已加载插件(run_command 可调用其任意指令，不止骰核；不确定语法先 .help): '
                                   + '、'.join(plugins))
        except Exception:
            pass
    if dice_cheat:
        system_content += '\n\n# 骰系官方指令速查（run_command 执行；也能调用上面其他插件的指令）\n' + dice_cheat

    # 固定记忆（非检索类的自定义全局项）——稳定内容，放进 system 前缀以提升前缀缓存命中
    mem = OlivaAIAgent.knowledge.getMem(bot_hash)
    fixed = {k: v for k, v in mem.get('全局', {}).items() if k not in OlivaAIAgent.knowledge.GLOBAL_SUB_KEYS}
    if fixed:
        system_content += '\n\n# 固定记忆\n' + json.dumps(fixed, ensure_ascii=False)

    # 任务说明也是稳定内容，放在 system 前缀末尾
    task = ('\n\n# 当前任务\n- 判断是否加入对话；不想参与就让 r 为空列表(你不必每句都回，按心情，但有人找你尽量回)\n'
            '- 要回复就把内容追加到 r 列表，多条消息分开\n- 避免重复已回过的话题和自己说过的话\n'
            '- 只输出严格 JSON：{"r":[...]}')
    system_content += task

    # 动态/易变内容全部放到历史之后的尾部 turn，避免冲刷前缀缓存
    now_text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    patch = {
        '当前上下文': {'群号': group_id, '当前本地时间': now_text,
                   '说明': '群聊历史中最后一条是最新消息；本动态上下文不是群聊消息'},
        '当前记忆': {'知识': knowledge, '用户侧写': profiles, '前情提要': summary},
        '图片缓存': OlivaAIAgent.vision.groupImageCacheDict(group_id),
    }
    if agent_mem:
        patch['当前记忆']['互通记忆'] = agent_mem
    if skills_ctx:
        patch['技能片段'] = skills_ctx.strip()

    messages = buildContextMessages(system_content, history, patch)
    messages.append({'role': 'user',
                     'content': '根据最新群消息决定是否回复，只输出 {"r":["回复"]} 或 {"r":[]}，不要解释。'})

    # first_thinking 前置判定（便宜模型 NEXT/SKIP + 表情意图）；显式触发/被@时直接放行
    image_ref = ''
    if (cfg('first_thinking', False) and _thinkCooldownPassed(bot_hash, group_id)
            and not parsed.get('at_me') and not force):
        decision, image_ref = _firstThink(Proc, bot_hash, group_id, history, patch, system_content, self_id)
        if decision == 'SKIP':
            conf.debugLog(Proc, '统一管线: 前置判定 SKIP')
            return

    # 若前置判定选了表情意图，提示真实文件名
    if image_ref:
        cache_map = OlivaAIAgent.vision.imageCacheMap(bot_hash)
        fn = OlivaAIAgent.vision.resolveImageRef(image_ref, cache_map)
        if fn:
            messages.append({'role': 'user',
                             'content': '本次若发图，优先用真实文件名：[发图片:%s]，不要改写。' % fn})

    # 调用回复模型（可选带工具）
    reply_list = _callReply(plugin_event, Proc, bot_hash, group_id, messages, history, allow_tools)
    if reply_list is None:
        conf.debugLog(Proc, '潜行: 无有效回复')
        # 显式请求(.ai/@/关键词)遇后端错误时给一句反馈，避免用户对着空气发指令
        if force:
            tpl = str(conf.get('agent', 'error_reply', default='AI出错: {err}'))
            try:
                plugin_event.reply(tpl.replace('{err}', '暂时没能生成回复，请稍后再试'))
            except Exception:
                pass
        return
    if len(reply_list) == 0:
        conf.debugLog(Proc, '潜行: 模型选择不回复')
        return

    _setThink(bot_hash, group_id)
    reply_list = _replyWash(reply_list)
    reply_list = OlivaAIAgent.vision.repairVisionDenial(reply_list, history)
    if not reply_list:
        return
    conf.debugLog(Proc, '潜行回复: %s' % reply_list)

    # 记入自己的历史 + 后台提炼记忆
    addSelfReply(platform, group_id, ''.join(str(x) for x in reply_list))
    if cfg('record_memory', True):
        threading.Thread(target=OlivaAIAgent.knowledge.runMemoryExtraction,
                         args=(bot_hash, group_id, history, cfg('record_knowledge', True)),
                         daemon=True).start()

    # 拟人发送节奏
    time.sleep(1 + (random.random() * 2 - 1) * 0.9)
    out = OlivaAIAgent.vision.translateOutgoing(reply_list, bot_hash)
    _sendMulti(plugin_event, out, time.perf_counter() - total_start)


def _replyWash(reply_list):
    res = []
    for i in reply_list:
        if not isinstance(i, str):
            continue
        s = i.replace('\r', '').strip('\n').rstrip('。')
        s = re.sub(r'\([^)]*\)', '', s)
        s = re.sub(r'（[^）]*）', '', s)
        s = s.strip()
        if s:
            res.append(s)
    return res


def _sendMulti(plugin_event, msg_list, total_past):
    # 逐条打字延迟上限：长回复不应让群锁休眠数分钟（会拖住该群后续所有回复）
    cap = float(OlivaAIAgent.conf.get('ambient', 'max_send_delay', default=6.0))
    first = True
    for i in msg_list:
        if not i or len(str(i)) == 0:
            continue
        delay = sum(0.2 + (random.random() * 2 - 1) * 0.15 for _ in range(len(str(i))))
        if first:
            first = False
            if delay > total_past:
                delay -= total_past
        if cap > 0 and delay > cap:
            delay = cap
        if delay > 0:
            time.sleep(delay)
        try:
            plugin_event.send('group', str(plugin_event.data.group_id), i)
        except Exception:
            try:
                plugin_event.reply(i)
            except Exception:
                pass


# ---------------- first_thinking ----------------

def _intentBackend():
    ic = OlivaAIAgent.conf.get('ambient', 'intent_api', default={}) or {}
    if ic.get('enable') and ic.get('api_url') and ic.get('api_key'):
        return {'wire': 'openai', 'api_url': ic['api_url'], 'api_key': ic['api_key'],
                'model': ic.get('model', ''), 'max_tokens': ic.get('max_tokens', 32),
                'temperature': ic.get('temperature', 0.0), 'timeout_sec': ic.get('timeout', 45),
                'stream': False, 'vision': False, '_name': 'intent'}
    bc = dict(OlivaAIAgent.aiClient.getBackendConf())
    bc['stream'] = False
    bc['max_tokens'] = 32
    return bc


def _firstThink(Proc, bot_hash, group_id, history, patch, system_ref, self_id):
    '''返回 ('NEXT'|'SKIP', image_ref)。判定失败默认 NEXT（不丢消息）。'''
    try:
        max_size = int(OlivaAIAgent.conf.get('ambient', 'intent_image_cache_size', default=10))
        intent_imgs = OlivaAIAgent.vision.emojiIntentCache(bot_hash, group_id, max_size)
        sys_prompt = '''# 你是二分类器，只判断最新一条群消息是否值得交给正式回复模型
- 只输出 {"d":"NEXT","i":"图片内容或意图关键词或空"} 或 {"d":"SKIP","i":""}
- NEXT: 最新消息@你/回复你/叫你名字/问候你/向你提问/要求你做事，或明显在邀请你接话
- SKIP: 只是群友互相闲聊、与你无关、纯语气词短句且你无合适接话点
- i: 若适合发表情包，从图片缓存里挑一个贴切图片的内容/意图关键词填入(保守，别硬发)，否则空字符串
- 不要填文件名/扩展名，不要输出解释'''
        patch2 = dict(patch)
        patch2['图片缓存'] = intent_imgs
        messages = buildContextMessages(sys_prompt, history, patch2)
        messages.append({'role': 'user', 'content': '完成二分类，只输出 {"d":"NEXT","i":""} 或 {"d":"SKIP","i":""}。'})
        bc = _intentBackend()
        res = OlivaAIAgent.aiClient.chat(messages, tools=None, backend_conf=bc,
                                         force_no_stream=True, response_json=True, thinking_off=True,
                                         timeout_override=bc.get('timeout_sec', 45))
        if not res.get('ok'):
            return 'NEXT', ''
        text = res.get('text', '')
        m = re.search(r'\{.*\}', text, re.S)
        data = json.loads(m.group(0)) if m else {}
        d = str(data.get('d', '')).upper()
        i = str(data.get('i', '')).strip()
        OlivaAIAgent.conf.debugLog(Proc, 'FIRST THINK -> %s / %s' % (d, i))
        if d.startswith('SKIP'):
            return 'SKIP', ''
        return 'NEXT', i
    except Exception as e:
        OlivaAIAgent.conf.debugLog(Proc, 'FIRST THINK 失败(默认NEXT): %s' % e)
        return 'NEXT', ''


# ---------------- 回复模型调用 ----------------

def _parseR(text):
    text = str(text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and isinstance(obj.get('r'), list):
            return [x for x in obj['r']]
    except Exception:
        pass
    matches = re.findall(r'\{[^{}]*"r"\s*:\s*\[[^\]]*\][^{}]*\}', text)
    if matches:
        try:
            obj = json.loads(matches[-1])
            if isinstance(obj.get('r'), list):
                return list(obj['r'])
        except Exception:
            pass
    # 宽容提取
    mm = list(re.finditer(r'"r"\s*:\s*\[', text))
    if mm:
        start = mm[-1].end()
        end = text.rfind(']', start)
        if end >= start:
            inner = text[start:end].strip()
            if not inner:
                return []
            parts = re.split(r'"\s*,\s*"', inner.strip().strip('"'))
            return [p.strip().strip('"') for p in parts if p.strip()]
    return None


# 跳过关键词：兜底解析时判断 AI 是否想"不回复"（参考刺客 agent.py:_fallback_parse_intent）
_SKIP_KEYWORDS = (
    '不回复', '不回', '跳过', '不参与', '不感兴趣', '不需要回复',
    '沉默', '旁观', '不插话', '不说话', '不发言', '无需回复',
    '与我无关', '不相关', '不需要我', '没有需要',
)


def _fallback_parse_intent(content):
    '''AI 输出非标准 JSON 时的兜底解析（参考刺客 agent.py:_fallback_parse_intent）。
    - 含 "r":[ 结构 → 宽容提取，提取失败视为不回复(返回空列表)
    - 首尾含跳过关键词 → 视为不回复(返回空列表)
    - 否则 → 把原文当作回复内容返回 [content]
    返回 None 表示无法兜底(不应该发生)；返回 [] 表示不回复；返回 [str] 表示回复内容。'''
    content = str(content).strip()
    if not content:
        return []
    if re.search(r'"r"\s*:\s*\[', content):
        tolerant = _parseR(content)
        if tolerant is not None:
            return tolerant
        return []   # 检测到 JSON 结构但无法提取 → 安全跳过，不把损坏 JSON 当回复发出去
    head = content[:15]
    tail = content[-15:] if len(content) > 15 else content
    for kw in _SKIP_KEYWORDS:
        if head.startswith(kw) or tail.endswith(kw):
            return []
    return [content]   # 未命中跳过关键词 → 视为实际回复


def _callReply(plugin_event, Proc, bot_hash, group_id, messages, history, allow_tools):
    retry = int(OlivaAIAgent.conf.get('ambient', 'retry_count', default=3))
    if allow_tools:
        return _callReplyWithTools(plugin_event, Proc, bot_hash, group_id, messages, history)
    reply_list = None
    for attempt in range(retry):
        res = OlivaAIAgent.aiClient.chat(messages, tools=None, force_no_stream=True, response_json=True)
        if not res.get('ok'):
            OlivaAIAgent.conf.debugLog(Proc, '潜行调用失败: %s' % res.get('error'))
            continue
        text = res.get('text', '')
        reply_list = _parseR(text)
        if reply_list is not None:
            break
    # 重试完毕仍解析失败，但有文本 → 兜底解析(避免 AI 输出非标准 JSON 时直接丢弃)
    if reply_list is None:
        last_text = res.get('text', '') if res else ''
        if last_text.strip():
            OlivaAIAgent.conf.debugLog(Proc, '潜行 JSON重试%d次失败,兜底: %s' % (retry, last_text[:200]))
            reply_list = _fallback_parse_intent(last_text)
    return reply_list


def _callReplyWithTools(plugin_event, Proc, bot_hash, group_id, messages, history):
    '''潜行 + 工具：让 AI 可调用 run_command/查询等，最终强制 JSON 输出。
    修复要点：
    1. 每一步加 debugLog，让 debug_log=true 时能看到失败原因(之前静默 return None)
    2. _parseR 解析失败但有文本时，用 _fallback_parse_intent 兜底(参考刺客 agent.py)
    3. 工具调用记录到 debugLog，方便排查"调了工具但没回复"的问题'''
    conf = OlivaAIAgent.conf
    is_master = conf.isMaster(plugin_event)
    ctx = {
        'plugin_event': plugin_event, 'Proc': Proc, 'platform': plugin_event.platform['platform'],
        'func_type': 'group_message', 'group_id': group_id, 'user_id': plugin_event.data.user_id,
        'is_master': is_master, 'self_id': str(plugin_event.base_info.get('self_id', '')),
    }
    tool_defs = OlivaAIAgent.tools.getToolsForRequest(ctx)
    max_rounds = int(conf.get('ambient', 'agent_max_turns', default=4))
    convo = list(messages)
    for rnd in range(max_rounds):
        conf.debugLog(Proc, '潜行+工具 轮 %d/%d' % (rnd + 1, max_rounds))
        res = OlivaAIAgent.aiClient.chat(convo, tools=tool_defs, force_no_stream=True)
        if not res.get('ok'):
            conf.debugLog(Proc, '潜行+工具 AI调用失败(轮%d): %s' % (rnd + 1, res.get('error')))
            return None
        calls = res.get('tool_calls') or []
        asst = {'role': 'assistant', 'content': res.get('text', '')}
        if calls:
            asst['tool_calls'] = calls
        convo.append(asst)
        if not calls:
            # 没有工具调用 → 这是最终回复，解析 JSON
            text = res.get('text', '')
            reply_list = _parseR(text)
            if reply_list is None and text.strip():
                # 兜底：AI 返回非标准 JSON 但有内容 → 尝试宽容解析
                conf.debugLog(Proc, '潜行+工具 JSON解析失败,兜底: %s' % text[:200])
                reply_list = _fallback_parse_intent(text)
            elif reply_list is None:
                conf.debugLog(Proc, '潜行+工具 空回复,跳过')
            return reply_list
        # 有工具调用 → 执行并继续循环
        for tc in calls:
            try:
                args = json.loads(tc.get('arguments') or '{}')
            except Exception:
                args = {}
            conf.debugLog(Proc, '潜行+工具 调用: %s(%s)' % (tc.get('name'), str(args)[:200]))
            result = OlivaAIAgent.tools.execTool(tc.get('name', ''), args, ctx)
            # execTool 可能返回 dict,转成字符串给模型看
            if not isinstance(result, str):
                try:
                    result = json.dumps(result, ensure_ascii=False)
                except Exception:
                    result = str(result)
            convo.append({'role': 'tool', 'tool_call_id': tc.get('id', ''),
                          'name': tc.get('name', ''), 'content': result})
            conf.debugLog(Proc, '潜行+工具 结果: %s' % result[:200])
    # 循环用完 max_rounds → 强制收尾
    conf.debugLog(Proc, '潜行+工具 达到max_rounds=%d,强制收尾' % max_rounds)
    convo.append({'role': 'user', 'content': '现在直接输出最终 JSON：{"r":["回复"]} 或 {"r":[]}。'})
    res = OlivaAIAgent.aiClient.chat(convo, tools=None, force_no_stream=True, response_json=True)
    if res.get('ok'):
        text = res.get('text', '')
        reply_list = _parseR(text)
        if reply_list is None and text.strip():
            conf.debugLog(Proc, '潜行+工具 收尾JSON失败,兜底: %s' % text[:200])
            reply_list = _fallback_parse_intent(text)
        return reply_list
    conf.debugLog(Proc, '潜行+工具 收尾AI调用失败: %s' % res.get('error'))
    return None


def saveAll():
    with _history_lock:
        for key in list(_history.keys()):
            _persist(key)
