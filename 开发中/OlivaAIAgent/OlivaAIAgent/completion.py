# -*- encoding: utf-8 -*-
'''Detect and repair replies that promise work without delivering it.'''

import json
import re


COMPLETION_GUARD_PROMPT = '''# 当前轮任务交付规则
- 用户要求创作、整理、分析、查询或执行时，能在当前轮完成的内容必须立即完成并交付。
- 不要只说“马上做”“稍等”“稍后发”“已经整理好”，也不要把尚未发送的结果说成已经完成。
- 除非真实工具已经成功创建了对应内容，否则不得声称结果放在文件、文件夹、后台、草稿或其他位置。
- 需要多个步骤时，在当前请求内继续调用工具或继续生成，直到给出实际结果；进度话术不是最终答案。
- 确实缺少必要信息时，直接提出最少的澄清问题；确实失败时如实说明，不得虚构完成。'''


_FUTURE_ACTION_PATTERNS = (
    re.compile(
        r'(?:这就|马上|稍后|待会儿?|等会儿?|随后|一会儿后).{0,20}'
        r'(?:发|贴|给|写|整理|生成|制作|查|找|处理|补|继续)',
        re.I,
    ),
    re.compile(
        r'(?:^|[，,。.!！?？~～])\s*(?:好的?[呀啊~～，, ]*)?'
        r'(?:请)?(?:稍等(?:一下|一会儿?|片刻)?|等我.{0,12}|给我一点时间|先等等)',
        re.I,
    ),
    re.compile(
        r'别急.{0,30}(?:发|贴|给|写|整理|生成|制作|查|找|处理|补|继续)',
        re.I,
    ),
    re.compile(r'(?:正在|还在)(?:帮你)?(?:生成|整理|写|制作|查询|查找|处理)', re.I),
    re.compile(r'(?:生成|整理|制作|查询|处理|准备)中(?:呢|啦|了|\.\.\.|…)?', re.I),
)

_FAKE_LOCATION_PATTERN = re.compile(
    r'(?:已经|都|刚才)?(?:帮你)?(?:放|存|写|整理|保存).{0,18}'
    r'(?:文件夹|文件|文档|后台|草稿|数据库).{0,10}(?:里|中|好了|完了)',
    re.I,
)

_COMPLETION_ONLY_PATTERN = re.compile(
    r'(?:已经|都|刚才)?(?:帮.{0,6})?'
    r'(?:生成|整理|准备|写|做|弄|搞|理)(?:出来)?(?:完|好)(?:了|啦|咯|呢)?',
    re.I,
)

_LIST_ITEM_PATTERN = re.compile(r'(?m)^\s*(?:[-*]|\d+[.、]|[一二三四五六七八九十]+[、.])\s*\S+')

_READ_ONLY_TOOLS = {
    'fetch_url',
    'kb_group_brief',
    'kb_search',
    'kb_user_note',
    'list_reminders',
    'memory_list',
    'olivos_discover',
    'web_search',
}


def _visibleText(reply_text):
    text = str(reply_text or '')
    text = re.sub(r'\[(?:OP|CQ):[^\]]*\]', ' ', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()


def _hasDeliveredContent(reply_text):
    raw = str(reply_text or '').strip()
    visible = _visibleText(raw)
    if len(visible) >= 240:
        return True
    if len(_LIST_ITEM_PATTERN.findall(raw)) >= 2:
        return True
    if re.search(r'[:：]\s*\S.{20,}', raw, re.S):
        return True
    return False


def needsContinuation(reply_text, action_performed=False):
    '''Return True when a terminal reply only postpones or pretends to finish work.'''
    text = _visibleText(reply_text)
    if not text:
        return False
    if action_performed:
        return False
    if any(pattern.search(text) for pattern in _FUTURE_ACTION_PATTERNS):
        return True
    if _FAKE_LOCATION_PATTERN.search(text):
        return True
    return bool(_COMPLETION_ONLY_PATTERN.search(text) and not _hasDeliveredContent(reply_text))


def toolCompletedAction(tool_name, tool_result):
    '''Treat successful mutating/sending tools as real delivery, but not read-only lookups.'''
    if str(tool_name or '') in _READ_ONLY_TOOLS:
        return False
    try:
        parsed = tool_result if isinstance(tool_result, dict) else json.loads(str(tool_result or ''))
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict) and parsed.get('active') is True


def continuationPrompt(json_reply=False):
    prompt = (
        '【未完成任务自动续行】你上一条回复只有进度、承诺或完成声明，没有实际交付用户所需结果。'
        '现在继续执行最近一项明确任务：能直接用文字完成就立即给出完整内容；需要外部操作就调用现有工具；'
        '缺少必要信息才提出一个最少的澄清问题。不要重复进度话术，不要再次声称“稍后发”或虚构保存位置。'
    )
    if json_reply:
        prompt += ' 最终仍只输出严格 JSON：{"r":["实际结果"]}；需要多条消息时放入多个数组元素。'
    return prompt


def exhaustedReply():
    return '刚才没有真正完成你的请求。请再发一次具体要我直接输出的内容，我会直接给结果。'
