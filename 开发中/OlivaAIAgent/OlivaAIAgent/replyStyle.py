# -*- encoding: utf-8 -*-
'''Shared outgoing reply style cleanup.'''

import re


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


def cleanReplyText(text):
    '''Remove explicit self-directed stage directions while preserving content.'''
    value = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
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
