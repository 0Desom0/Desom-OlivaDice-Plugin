# -*- encoding: utf-8 -*-

import json
import re

import OlivaAIAgent


PLANNING_ROLE_PROMPT = '''【当前阶段职责：规划与工具执行】
- 本阶段只负责理解请求、判断是否需要工具、执行工具并形成候选回复草稿；不负责最终输出格式
- 需要工具时直接调用工具；工具结果返回后继续完成任务，不能只承诺“稍后处理”
- 不需要继续调用工具时，在 content 中给出可直接发给用户的候选回复草稿
- 不要输出 JSON 回复信封；不要讲解输出格式；候选草稿不能包含分析过程、内部上下文核对或思考独白
- 本阶段内容不会直接发送给用户，后续有独立的最终回复整理阶段'''


FINAL_JSON_ROLE_PROMPT = '''【当前阶段职责：最终回复 JSON 整理】
你是整个流程唯一允许产出用户可见回复的阶段。只完成最终回复，不做工具规划，也不调用工具。
- 根据当前对话、已有工具结果和候选草稿，整理出真正要发给用户的内容
- 丢弃候选草稿中的分析、推理、自我核对、格式说明和过程话术；不得把它们改写后发给用户
- 最终只能输出一个严格 JSON 对象，且只能有键 "r"
- "r" 必须是字符串数组；每个元素是一条要发送的消息；不回复时输出空数组
- 正确格式只有 {"r":["内容1","内容2"]} 或 {"r":[]}
- JSON 前后不能有代码块、解释、思考、前缀、后缀或任何其他字符'''


FINAL_JSON_REPAIR_PROMPT = '''【最终回复格式/内部过程泄漏修正】上一次输出不是合格的最终回复 JSON，或仍含内部分析过程。立即重新整理。
只能输出一个严格 JSON 对象，结构必须是 {"r":["回复内容"]} 或 {"r":[]}；对象只能有 "r" 键，数组元素只能是字符串，JSON 前后不要输出任何文字。'''


def _unwrapKnownGatewayBody(text):
    '''只剥离已知 Tesla.Env 传输包装，内部正文仍按严格 JSON 校验。'''
    if 'Tesla.Env' not in text and re.search(r'\bbody\s*:', text) is None:
        return None
    matched = re.search(r'\bbody\s*:\s*("(?:\\.|[^"\\])*")', text, re.S)
    if matched is None:
        return None
    try:
        body = json.loads(matched.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return body if isinstance(body, str) else None


def parseStrictEnvelope(value):
    '''只接受完整且唯一的 {"r": [str, ...]} JSON 对象。'''
    raw = str(value or '').strip()
    if not raw:
        return None
    wrapped_body = _unwrapKnownGatewayBody(raw)
    if wrapped_body is not None:
        raw = wrapped_body.strip()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or set(payload) != {'r'}:
        return None
    replies = payload.get('r')
    if not isinstance(replies, list) or not all(isinstance(item, str) for item in replies):
        return None
    return list(replies)


def dumpEnvelope(replies):
    '''把内部回复数组规范为可重新严格解析的 JSON。'''
    safe_replies = list(replies or [])
    if not all(isinstance(item, str) for item in safe_replies):
        raise TypeError('reply envelope only accepts strings')
    return json.dumps({'r': safe_replies}, ensure_ascii=False, separators=(',', ':'))


def _hasInternalDeliberation(replies):
    return any(
        OlivaAIAgent.replyStyle.containsInternalDeliberation(item)
        for item in replies
        if str(item).strip()
    )


def _canonicalizeCandidate(value, relaxed_parser=None):
    '''将安全的兼容输出本地规范成严格 JSON；含内部过程时拒绝兜底。'''
    raw = str(value or '').strip()
    if not raw:
        return dumpEnvelope([])
    replies = parseStrictEnvelope(raw)
    if replies is None and relaxed_parser is not None:
        try:
            replies = relaxed_parser(raw)
        except Exception:
            replies = None
    if replies is None:
        # 纯正文可以作为单条回复；疑似损坏的结构化输出不能整段发送。
        if raw.startswith(('{', '[', '｛', '［')) or 'Tesla.Env' in raw:
            return None
        replies = [raw]
    if not isinstance(replies, list) or not all(isinstance(item, str) for item in replies):
        return None
    if _hasInternalDeliberation(replies):
        return None
    return dumpEnvelope(replies)


def finalize(
    messages,
    Proc=None,
    trace_id=None,
    purpose='最终回复整理',
    draft=None,
    max_attempts=2,
    relaxed_parser=None,
):
    '''执行无工具最终整理；成功只返回经严格 JSON 复验的字符串数组。'''
    convo = list(messages or [])
    if draft is not None and (
        not convo
        or convo[-1].get('role') != 'assistant'
        or str(convo[-1].get('content', '')) != str(draft)
    ):
        convo.append({'role': 'assistant', 'content': str(draft)})
    convo.append({'role': 'system', 'content': FINAL_JSON_ROLE_PROMPT})
    attempts = max(1, int(max_attempts or 1))
    candidates = []
    for attempt in range(1, attempts + 1):
        try:
            result = OlivaAIAgent.aiClient.chat(
                convo,
                tools=None,
                force_no_stream=True,
                response_json=True,
                thinking_off=True,
                trace_id=trace_id,
                purpose='%s第%d次' % (purpose, attempt),
            )
        except Exception as exc:
            OlivaAIAgent.conf.traceLog(
                Proc,
                'final_reply.request.failed',
                trace_id,
                attempt=attempt,
                error='%s: %s' % (type(exc).__name__, exc),
                purpose=purpose,
            )
            continue
        if not result.get('ok'):
            OlivaAIAgent.conf.traceLog(
                Proc,
                'final_reply.request.failed',
                trace_id,
                attempt=attempt,
                error=result.get('error', ''),
                purpose=purpose,
            )
            continue
        raw = str(result.get('text', '') or '')
        candidates.append(raw)
        replies = parseStrictEnvelope(raw)
        if replies is not None and not _hasInternalDeliberation(replies):
            OlivaAIAgent.conf.traceLog(
                Proc,
                'final_reply.json.accepted',
                trace_id,
                attempt=attempt,
                messages=len(replies),
                purpose=purpose,
            )
            return replies
        OlivaAIAgent.conf.traceLog(
            Proc,
            'final_reply.json.rejected',
            trace_id,
            attempt=attempt,
            internal=bool(replies is not None and _hasInternalDeliberation(replies)),
            purpose=purpose,
            text=raw[:300],
        )
        convo.append({'role': 'assistant', 'content': raw})
        convo.append({'role': 'system', 'content': FINAL_JSON_REPAIR_PROMPT})

    # 兼容少数不支持 response_format 的网关，但最终仍先规范成严格 JSON 再解析。
    if draft is not None:
        candidates.append(draft)
    for candidate in candidates:
        canonical = _canonicalizeCandidate(candidate, relaxed_parser=relaxed_parser)
        if canonical is None:
            continue
        replies = parseStrictEnvelope(canonical)
        if replies is None or _hasInternalDeliberation(replies):
            continue
        OlivaAIAgent.conf.traceLog(
            Proc,
            'final_reply.local_normalized',
            trace_id,
            messages=len(replies),
            purpose=purpose,
        )
        return replies
    return None
