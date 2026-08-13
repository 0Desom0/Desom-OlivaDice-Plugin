# -*- encoding: utf-8 -*-
'''Shared outgoing reply style cleanup.'''

import re


_HIDDEN_REASONING_BLOCK = re.compile(
    r'<(?:think|thinking|analysis|reasoning)>.*?</(?:think|thinking|analysis|reasoning)>',
    re.I | re.S,
)
_INTERNAL_DELIBERATION_PATTERNS = (
    re.compile(r'\b(?:internal|dynamic) context\b', re.I),
    re.compile(r'\b(?:last|latest|final) (?:visible )?(?:new )?message (?:in|from|at) (?:the )?history\b', re.I),
    re.compile(r'\bcurrent (?:message|speaker)\b.{0,80}\b(?:listed|internal|identity|sender|from)\b', re.I | re.S),
    re.compile(r'\b(?:task|system) (?:header|prompt|says|instruction)\b', re.I),
    re.compile(r'\b(?:best|better) to respond(?: in character)?\b', re.I),
    re.compile(r'\bpresumably (?:the )?trigger message\b', re.I),
    re.compile(r'(?:当前发言者身份|内部上下文|动态上下文|系统提示词|任务头部)'),
    re.compile(r'(?:历史|上下文)(?:记录)?(?:里|中|末尾|最后).{0,20}(?:消息|发言者).{0,20}(?:是谁|身份|显示|来自)'),
    re.compile(r'(?:当前|最新)(?:实质)?(?:消息|内容).{0,60}(?:历史|转发|引用)'),
    re.compile(r'(?:历史|转发|引用).{0,60}(?:当前|最新)(?:消息|内容)'),
    re.compile(r'(?:按|根据)当前任务.{0,30}(?:触发|回应|回复)'),
    re.compile(r'我(?:是|现在).{0,25}(?:被触发|收到的是).{0,25}(?:回应|回复|当前消息)'),
    re.compile(r'我(?:可以|应该|需要|最好).{0,30}(?:自然回应|回应一下|回复一下|回个话)'),
    re.compile(r'(?:^|\n)\s*输出\s*JSON\s*[。.!]?\s*$', re.I),
)
_SELF_ACTION_FIRST_CLAUSE = re.compile(
    r'''^\s*(?:小芙|芙萝妮娅(?:Fronia)?|本姑娘|本小姐|我)\s*'''
    r'''(?:刚才|先|又|轻轻地?|微微地?)?'''
    r'''(?:看(?:了|了一眼|了眼)|瞄(?:了|了一眼|了眼)|扫(?:了|了一眼)|'''
    r'''盯着|望向|看向|低头|抬头|侧耳|眨了眨眼|'''
    r'''尾巴|耳朵|眼神|神态|心里|心想|心理|动作)'''
    r'''[^，,~～。！？!?\n]*(?:[，,~～。！？!?])\s*''',
    re.I,
)
_FOLLOWUP_ACTION_CLAUSE = re.compile(
    r'''^\s*(?:小芙|芙萝妮娅(?:Fronia)?|我)?\s*'''
    r'''(?:的)?(?:尾巴|耳朵|眼神|神态|嘴角|心里|心想|心理|动作)'''
    r'''[^，,~～。！？!?\n]*(?:[，,~～。！？!?])\s*''',
    re.I,
)
_STANDALONE_ACTION = re.compile(
    r'''^\s*(?:尾巴|耳朵|眼神|神态|心里|心想|心理|动作)'''
    r'''.*?(?:[~～。！？!?]|$)\s*$''',
    re.I,
)


def containsInternalDeliberation(text):
    '''Detect model self-checks about private prompt/context before sending.'''
    value = str(text or '').strip()
    if not value:
        return False
    return any(pattern.search(value) for pattern in _INTERNAL_DELIBERATION_PATTERNS)


def cleanReplyText(text):
    '''Remove explicit self-directed stage directions while preserving content.'''
    value = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    value = _HIDDEN_REASONING_BLOCK.sub('', value).strip()
    if containsInternalDeliberation(value):
        return ''
    cleaned = _SELF_ACTION_FIRST_CLAUSE.sub('', value, count=1)
    if cleaned != value:
        value = cleaned.lstrip()
        for _ in range(3):
            cleaned = _FOLLOWUP_ACTION_CLAUSE.sub('', value, count=1)
            if cleaned == value:
                break
            value = cleaned.lstrip()
    lines = []
    for line in value.split('\n'):
        if _STANDALONE_ACTION.fullmatch(line):
            continue
        lines.append(line.rstrip())
    return '\n'.join(lines).strip()


def cleanReplyParts(parts):
    '''Clean a sequence of outgoing text parts and discard empty actions.'''
    result = []
    for part in parts or []:
        cleaned = cleanReplyText(part)
        if cleaned:
            result.append(cleaned)
    return result
