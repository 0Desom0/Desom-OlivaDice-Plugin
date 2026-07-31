# -*- encoding: utf-8 -*-
'''便宜模型预处理集群：并行执行互相独立的窄任务。'''

import concurrent.futures
import json
import re

import OlivaAIAgent


def runCluster(tasks, Proc=None, trace_id=None):
    '''并行执行 {任务名: callable}；单项失败只返回 None，不影响其他任务。'''
    task_map = {str(name): func for name, func in (tasks or {}).items() if callable(func)}
    if not task_map:
        return {}
    OlivaAIAgent.conf.traceLog(
        Proc,
        'aux.cluster.started',
        trace_id,
        materials='、'.join(task_map),
        tasks=len(task_map),
    )
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(task_map))) as executor:
        futures = {executor.submit(func): name for name, func in task_map.items()}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = None
                OlivaAIAgent.conf.traceLog(
                    Proc,
                    'aux.cluster.task_failed',
                    trace_id,
                    error='%s: %s' % (type(e).__name__, e),
                    name=name,
                )
    OlivaAIAgent.conf.traceLog(
        Proc,
        'aux.cluster.done',
        trace_id,
        materials='、'.join(name for name, value in results.items() if value is not None) or '无',
        tasks=len(task_map),
    )
    return results


def _recentContext(history, limit=4):
    recent = []
    for item in list(history or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        recent.append({
            'sender': item.get('nickname') or item.get('role') or '',
            'text': item.get('message') or item.get('content') or '',
        })
    return recent


def _imageValue(raw, candidates=None):
    text = str(raw or '').strip()
    if not text:
        return ''
    match = re.search(r'\{.*\}', text, flags=re.S)
    candidate = match.group(0) if match else text
    try:
        data = json.loads(candidate)
    except Exception:
        data = None
    if isinstance(data, dict):
        for key in ('image', 'image_intent', 'intent', 'i'):
            if key in data:
                value = data.get(key)
                return str(value).strip() if value not in [None, False] else ''
    elif isinstance(data, str):
        return data.strip()
    low = text.lower().strip('` \t\r\n')
    if low in ('none', 'null', 'no', 'skip', '不用', '不发', '无'):
        return ''
    if re.search(r'不(?:适合|需要|建议).*(?:图片|表情)|无需.*(?:图片|表情)', text, re.I):
        return ''
    for file_name in (candidates or {}):
        if str(file_name) in text:
            return str(file_name)
    for data in (candidates or {}).values():
        if not isinstance(data, dict):
            continue
        for key in ('intent', 'content'):
            value = str(data.get(key, '')).strip()
            if value and value in text:
                return value
    labelled = re.search(
        r'(?:image(?:_intent)?|intent|图片|表情|意图)\s*[:：=]\s*["\']?([^\n"\'}]{1,160})',
        text,
        re.I,
    )
    if labelled:
        return labelled.group(1).strip(' `"\'。，,')
    plain = text.strip('` \t\r\n"\'')
    if '\n' not in plain and len(plain) <= 160:
        return plain
    return ''


def selectImageIntent(Proc, query_text, history, image_candidates, trace_id=None):
    '''独立判断本轮是否适合用缓存图片；失败返回空，主模型仍可自行选择。'''
    candidates = dict(image_candidates or {})
    if not candidates:
        return ''
    messages = [
        {
            'role': 'system',
            'content': (
                '你只负责判断当前对话是否适合发送候选图片。'
                '适合时只输出 {"image":"候选文件名或内容/意图关键词"}；'
                '不适合只输出 {"image":""}。不要回答消息，不要判断是否回复。'
            ),
        },
        {
            'role': 'user',
            'content': json.dumps(
                {
                    '当前消息': str(query_text or '')[:2000],
                    '最近上下文': _recentContext(history),
                    '候选图片': candidates,
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        result = OlivaAIAgent.aiClient.chat(
            messages,
            tools=None,
            backend_conf=OlivaAIAgent.aiClient.getAuxiliaryBackendConf(
                max_tokens=128,
                temperature=0.0,
            ),
            force_no_stream=True,
            response_json=True,
            thinking_off=True,
            timeout_override=30,
            trace_id=trace_id,
            purpose='图片判断',
        )
        if not result.get('ok'):
            raise ValueError(result.get('error', '图片判断失败'))
        image_ref = _imageValue(result.get('text', ''), candidates)[:160]
        OlivaAIAgent.conf.traceLog(
            Proc,
            'aux.image.result',
            trace_id,
            image_intent=image_ref or '无',
        )
        return image_ref
    except Exception as e:
        OlivaAIAgent.conf.traceLog(
            Proc,
            'aux.image.failed',
            trace_id,
            error='%s: %s' % (type(e).__name__, e),
            fallback='main',
        )
        return ''
