# -*- encoding: utf-8 -*-
'''
OlivaAIAgent AI 后端客户端
- 支持 openai 兼容 (chat completions) / anthropic (messages) / custom (自选 wire 格式)
- 支持流式(SSE)与非流式
- 支持视觉、音频和视频输入
- 统一内部消息格式:
    {'role':'system','content':str}
    {'role':'user','content':str,'images':[url,...],'audios':[data_url,...],'videos':[url,...]}
    {'role':'assistant','content':str|None,'tool_calls':[{'id','name','arguments'}]}   # arguments 为 JSON 字符串
    {'role':'tool','tool_call_id':str,'name':str,'content':str}
返回统一结果:
    {'ok':bool, 'text':str, 'tool_calls':[{'id','name','arguments'}], 'error':str, 'usage':dict}
'''

import hashlib
import json
import threading
import time
import urllib.parse

import requests

import OlivaAIAgent


_cache_stats_lock = threading.Lock()
_cache_stats = {}
_cache_prefix_counts = {}


def _requestCacheKey(bc, messages, tools):
    '''生成不含正文/密钥的请求前缀观测键，便于按模型定位缓存效果。'''
    try:
        stable = {
            'wire': bc.get('wire', ''),
            'model': bc.get('model', ''),
            'system': [m.get('content', '') for m in messages if m.get('role') == 'system'][:1],
            'tools': tools or [],
        }
        raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]
    except Exception:
        return ''


def _observeCachePrefix(bc, cache_key):
    '''记录当前进程是否发过同一 system/tool 前缀，仅用于解释上游缓存日志。'''
    if not cache_key:
        return {}
    scope = '%s|%s|%s|%s' % (
        bc.get('_name', 'override'),
        bc.get('wire', ''),
        bc.get('model', ''),
        cache_key,
    )
    with _cache_stats_lock:
        previous = _cache_prefix_counts.get(scope, 0)
        _cache_prefix_counts[scope] = previous + 1
    return {
        'cache_prefix_seen': previous > 0,
        'cache_prefix_requests': previous + 1,
    }


def _recordCacheUsage(bc, usage, cache_key=''):
    cached = usage.get('cached_tokens')
    input_tokens = usage.get('input_tokens')
    if not isinstance(cached, int) or not isinstance(input_tokens, int) or input_tokens <= 0:
        return {}
    key = '%s|%s|%s|%s' % (
        bc.get('_name', 'override'),
        bc.get('wire', ''),
        bc.get('model', ''),
        cache_key or '*',
    )
    with _cache_stats_lock:
        stats = _cache_stats.setdefault(key, {'requests': 0, 'cached_tokens': 0, 'input_tokens': 0})
        stats['requests'] += 1
        stats['cached_tokens'] += cached
        stats['input_tokens'] += input_tokens
        return {
            'cache_rate': '%.1f%%' % (cached * 100.0 / input_tokens),
            'cache_rate_total': '%.1f%%' % (stats['cached_tokens'] * 100.0 / stats['input_tokens']),
            'cache_requests': stats['requests'],
        }


def _detectWire(bc):
    '''决定报文格式 wire: openai(chat/completions) / anthropic(messages) / responses(/v1/responses)。
    - 显式配置 wire 最优先；anthropic 后端恒为 anthropic。
    - 便捷自动识别：api_url 指向 .../responses 时自动走 Responses API 报文。'''
    wire = bc.get('wire')
    if wire in ('openai', 'anthropic', 'responses'):
        return wire
    url = str(bc.get('api_url', '')).split('?', 1)[0].rstrip('/').lower()
    if url.endswith('/responses'):
        return 'responses'
    return 'openai'


def getBackendConf():
    backend = OlivaAIAgent.conf.get('backend', default='openai')
    if backend not in ['openai', 'anthropic', 'custom']:
        backend = 'openai'
    bc = dict(OlivaAIAgent.conf.get(backend, default={}) or {})
    if backend == 'anthropic':
        bc['wire'] = 'anthropic'
    else:
        # openai / custom：尊重显式 wire，否则按 api_url 自动识别(支持 /responses)
        bc['wire'] = _detectWire(bc)
    bc['_name'] = backend
    return bc


def getAuxiliaryBackendConf(max_tokens=512, temperature=0.0):
    '''优先复用前置便宜模型处理路由、提炼和翻译；未配置时才回退主后端。'''
    ic = OlivaAIAgent.conf.get('ambient', 'intent_api', default={}) or {}
    if ic.get('enable') and ic.get('api_url') and ic.get('api_key'):
        bc = {
            'wire': _detectWire(ic),
            'api_url': ic.get('api_url', ''),
            'api_key': ic.get('api_key', ''),
            'model': ic.get('model', ''),
            'timeout_sec': ic.get('timeout', 45),
            'vision': False,
            '_name': 'intent',
        }
    else:
        bc = getBackendConf()
    bc = dict(bc)
    bc['stream'] = False
    bc['max_tokens'] = max(32, int(max_tokens))
    bc['temperature'] = float(temperature)
    return bc


def chat(messages, tools=None, backend_conf=None, force_no_stream=False,
         response_json=False, thinking_off=False, timeout_override=None, trace_id=None, purpose=None):
    '''执行一次模型调用。
    response_json=True 请求 JSON 输出；thinking_off=True 本次强制关闭思考；
    timeout_override 覆盖超时秒数。'''
    bc = backend_conf if backend_conf is not None else getBackendConf()
    opts = {'response_json': response_json, 'thinking_off': thinking_off, 'timeout_override': timeout_override}
    started = time.perf_counter()
    request_id = 'ai-%08x' % (time.time_ns() & 0xffffffff)
    image_count = sum(len(message.get('images') or []) for message in messages if isinstance(message, dict))
    audio_count = sum(len(message.get('audios') or []) for message in messages if isinstance(message, dict))
    video_count = sum(len(message.get('videos') or []) for message in messages if isinstance(message, dict))
    log_id = trace_id or request_id
    request_fields = {
        'backend': bc.get('_name', 'override'),
        'audios': audio_count,
        'images': image_count,
        'messages': len(messages),
        'model': bc.get('model', ''),
        'request_id': request_id,
        'response_json': response_json,
        'stream': bool(bc.get('stream', False)) and not force_no_stream,
        'tools': len(tools or []),
        'vision': bool(bc.get('vision', False)),
        'audio': bool(bc.get('audio', False)),
        'video': bool(bc.get('video', False)),
        'videos': video_count,
        'wire': bc.get('wire', ''),
    }
    first_system = next(
        (message.get('content', '') for message in messages if message.get('role') == 'system'),
        '',
    )
    cache_details = {
        'cache_system_chars': len(str(first_system)),
        'cache_tools': len(tools or []),
    }
    cache_key = _requestCacheKey(bc, messages, tools)
    cache_observation = _observeCachePrefix(bc, cache_key)
    if cache_key:
        request_fields['cache_key'] = cache_key
    request_fields.update(cache_details)
    request_fields.update(cache_observation)
    if purpose:
        request_fields['purpose'] = purpose
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'ai.request',
        log_id,
        **request_fields,
    )
    try:
        if not str(bc.get('api_key', '')) and not str(bc.get('api_url', '')):
            result = {'ok': False, 'text': '', 'tool_calls': [], 'error': '未配置 api_url/api_key，请编辑配置文件'}
        else:
            wire = bc.get('wire')
            if wire == 'anthropic':
                result = _chat_anthropic(bc, messages, tools, force_no_stream, opts)
            elif wire == 'responses':
                result = _chat_responses(bc, messages, tools, force_no_stream, opts)
            else:
                result = _chat_openai(bc, messages, tools, force_no_stream, opts)
    except requests.exceptions.Timeout:
        result = {'ok': False, 'text': '', 'tool_calls': [], 'error': '请求超时'}
    except Exception as e:
        result = {'ok': False, 'text': '', 'tool_calls': [], 'error': '%s: %s' % (type(e).__name__, e)}
    usage = _normalizeUsage(result.pop('_usage', None))
    result['usage'] = usage
    response_fields = {
        'elapsed_ms': int((time.perf_counter() - started) * 1000),
        'error': result.get('error', ''),
        'ok': result.get('ok', False),
        'request_id': request_id,
        'text_chars': len(result.get('text', '')),
        'tool_calls': len(result.get('tool_calls') or []),
    }
    response_fields.update(usage)
    response_fields.update(_recordCacheUsage(bc, usage, cache_key=cache_key))
    if cache_key:
        response_fields['cache_key'] = cache_key
    response_fields.update(cache_details)
    response_fields.update(cache_observation)
    if purpose:
        response_fields['purpose'] = purpose
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'ai.response',
        log_id,
        **response_fields,
    )
    return result


def _normalizeUsage(usage):
    '''统一 OpenAI、Anthropic、Responses 与 DeepSeek 的 token 用量字段。'''
    if not isinstance(usage, dict):
        return {}

    def first_int(*values):
        return next((value for value in values if isinstance(value, int)), None)

    input_details = usage.get('input_tokens_details') or {}
    prompt_details = usage.get('prompt_tokens_details') or {}
    input_tokens = first_int(usage.get('input_tokens'), usage.get('prompt_tokens'))
    output_tokens = first_int(usage.get('output_tokens'), usage.get('completion_tokens'))
    total_tokens = first_int(usage.get('total_tokens'))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    cached_tokens = first_int(
        usage.get('prompt_cache_hit_tokens'),
        usage.get('cache_read_input_tokens'),
        input_details.get('cached_tokens'),
        prompt_details.get('cached_tokens'),
    )
    cache_miss_tokens = first_int(usage.get('prompt_cache_miss_tokens'))
    cache_creation_tokens = first_int(usage.get('cache_creation_input_tokens'))
    result = {}
    for key, value in (
        ('input_tokens', input_tokens),
        ('output_tokens', output_tokens),
        ('total_tokens', total_tokens),
        ('cached_tokens', cached_tokens),
        ('cache_miss_tokens', cache_miss_tokens),
        ('cache_creation_tokens', cache_creation_tokens),
    ):
        if value is not None:
            result[key] = value
    return result


# ---------------- OpenAI 兼容 ----------------

def _audioPart(value):
    '''把 data URL 转成 Qwen/OpenAI-compatible input_audio；远程地址保留 audio_url 兼容形式。'''
    ref = str(value or '')
    if ref.startswith('data:') and ',' in ref:
        header, data = ref.split(',', 1)
        mime = header[5:].split(';', 1)[0].lower()
        formats = {
            'audio/aac': 'aac',
            'audio/flac': 'flac',
            'audio/mpeg': 'mp3',
            'audio/mp3': 'mp3',
            'audio/ogg': 'ogg',
            'audio/opus': 'opus',
            'audio/wav': 'wav',
            'audio/x-wav': 'wav',
        }
        return {'type': 'input_audio', 'input_audio': {'data': data, 'format': formats.get(mime, 'mp3')}}
    return {'type': 'audio_url', 'audio_url': {'url': ref}}


def _to_openai_messages(messages, vision, audio=False, video=False):
    res = []
    for m in messages:
        role = m.get('role')
        if role == 'user':
            images = m.get('images') or []
            audios = m.get('audios') or []
            videos = m.get('videos') or []
            if (vision and images) or (audio and audios) or (video and videos):
                content = [{'type': 'text', 'text': m.get('content', '')}]
                if vision:
                    for url in images[:4]:
                        content.append({'type': 'image_url', 'image_url': {'url': url}})
                if audio:
                    for value in audios[:4]:
                        content.append(_audioPart(value))
                if video:
                    for url in videos[:4]:
                        content.append({'type': 'video_url', 'video_url': {'url': url}})
                res.append({'role': 'user', 'content': content})
            else:
                res.append({'role': 'user', 'content': m.get('content', '')})
        elif role == 'assistant':
            item = {'role': 'assistant', 'content': m.get('content') or ''}
            if m.get('tool_calls'):
                item['tool_calls'] = [
                    {
                        'id': tc['id'],
                        'type': 'function',
                        'function': {'name': tc['name'], 'arguments': tc.get('arguments', '{}')},
                    }
                    for tc in m['tool_calls']
                ]
                if item['content'] == '':
                    item['content'] = None
            res.append(item)
        elif role == 'tool':
            res.append({
                'role': 'tool',
                'tool_call_id': m.get('tool_call_id', ''),
                'content': m.get('content', ''),
            })
        else:
            res.append({'role': 'system', 'content': m.get('content', '')})
    return res


def _apply_thinking(payload, bc, opts):
    '''应用 DeepSeek/兼容端的 thinking + reasoning_effort。
    官方 DeepSeek V4 默认开启思考，必须显式发送 disabled 才能避免隐藏推理 Token；
    其他严格 OpenAI 端仍只在明确 enabled 时发送扩展参数。'''
    configured = bc.get('thinking')
    thinking_type = 'disabled' if opts.get('thinking_off') else (
        configured.get('type') if isinstance(configured, dict) else None
    )
    try:
        host = urllib.parse.urlsplit(str(bc.get('api_url', ''))).hostname or ''
    except Exception:
        host = ''
    official_deepseek = host.lower() == 'api.deepseek.com'
    if thinking_type == 'enabled' or (thinking_type == 'disabled' and official_deepseek):
        payload['thinking'] = {'type': thinking_type}
    if thinking_type == 'enabled':
        payload['reasoning_effort'] = bc.get('reasoning_effort', 'high')


def _chat_openai(bc, messages, tools, force_no_stream, opts=None):
    opts = opts or {}
    payload = {
        'model': bc.get('model', ''),
        'messages': _to_openai_messages(
            messages,
            bool(bc.get('vision', False)),
            bool(bc.get('audio', False)),
            bool(bc.get('video', False)),
        ),
        'temperature': bc.get('temperature', 0.7),
        'max_tokens': bc.get('max_tokens', 2000),
    }
    if tools:
        payload['tools'] = [
            {'type': 'function', 'function': {'name': t['name'], 'description': t['desc'], 'parameters': t['params']}}
            for t in tools
        ]
    stream = bool(bc.get('stream', False)) and not force_no_stream
    if stream:
        payload['stream'] = True
    if opts.get('response_json') and not tools:
        payload['response_format'] = {'type': 'json_object'}
    _apply_thinking(payload, bc, opts)
    try:
        payload.update(bc.get('extra_body', {}) or {})
    except Exception:
        pass
    headers = {'Content-Type': 'application/json'}
    if str(bc.get('api_key', '')):
        headers['Authorization'] = 'Bearer ' + str(bc['api_key'])
    try:
        headers.update(bc.get('extra_headers', {}) or {})
    except Exception:
        pass
    timeout = int(opts.get('timeout_override') or bc.get('timeout_sec', 120))
    resp = requests.post(str(bc.get('api_url', '')), headers=headers, json=payload, timeout=timeout, stream=stream)
    if resp.status_code != 200:
        return {'ok': False, 'text': '', 'tool_calls': [],
                'error': 'HTTP %s: %s' % (resp.status_code, resp.text[:300])}
    if stream:
        return _parse_openai_stream(resp)
    return _parse_openai_response(resp.json())


def _parse_openai_response(data):
    try:
        msg = data['choices'][0]['message']
        text = msg.get('content') or ''
        if isinstance(text, list):  # 部分兼容端返回分段 content
            text = ''.join([p.get('text', '') for p in text if isinstance(p, dict)])
        tool_calls = []
        for tc in msg.get('tool_calls') or []:
            fn = tc.get('function', {})
            tool_calls.append({
                'id': tc.get('id', 'call_%d' % len(tool_calls)),
                'name': fn.get('name', ''),
                'arguments': fn.get('arguments', '{}'),
            })
        # 兼容旧式 function_call
        if not tool_calls and msg.get('function_call'):
            fc = msg['function_call']
            tool_calls.append({'id': 'call_0', 'name': fc.get('name', ''), 'arguments': fc.get('arguments', '{}')})
        return {
            'ok': True,
            'text': text,
            'tool_calls': tool_calls,
            'error': '',
            '_usage': data.get('usage'),
        }
    except Exception as e:
        return {'ok': False, 'text': '', 'tool_calls': [], 'error': '响应解析失败: %s | %s' % (e, str(data)[:300])}


def _parse_openai_stream(resp):
    text = ''
    tool_calls = {}
    usage = None
    try:
        resp.encoding = 'utf-8'   # SSE 恒为 UTF-8；无 charset 时 requests 会误按 ISO-8859-1 解码致中文乱码
    except Exception:
        pass
    try:
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if not line.startswith('data:'):
                continue
            data_str = line[len('data:'):].strip()
            if data_str == '[DONE]':
                break
            try:
                chunk = json.loads(data_str)
            except Exception:
                continue
            if isinstance(chunk, dict) and chunk.get('error'):
                # 流中途报错（200 头已发出，状态码守卫拦不到）：显式失败，不冒充成功
                return {'ok': False, 'text': text, 'tool_calls': [],
                        'error': '流式错误: %s' % str(chunk.get('error'))[:300]}
            if isinstance(chunk.get('usage'), dict):
                usage = chunk['usage']
            choices = chunk.get('choices') or []
            if len(choices) == 0:
                continue
            delta = choices[0].get('delta') or {}
            piece = delta.get('content')
            if isinstance(piece, str):
                text += piece
            for tc in delta.get('tool_calls') or []:
                idx = tc.get('index', 0)
                slot = tool_calls.setdefault(idx, {'id': '', 'name': '', 'arguments': ''})
                if tc.get('id'):
                    slot['id'] = tc['id']
                fn = tc.get('function') or {}
                if fn.get('name') and slot['name'] == '':
                    slot['name'] = fn['name']
                if fn.get('arguments'):
                    slot['arguments'] += fn['arguments']
        result_calls = []
        for idx in sorted(tool_calls.keys()):
            slot = tool_calls[idx]
            if slot['id'] == '':
                slot['id'] = 'call_%d' % idx
            if slot['arguments'] == '':
                slot['arguments'] = '{}'
            result_calls.append(slot)
        return {'ok': True, 'text': text, 'tool_calls': result_calls, 'error': '', '_usage': usage}
    except Exception as e:
        return {'ok': False, 'text': text, 'tool_calls': [], 'error': '流式解析失败: %s' % e}
    finally:
        try:
            resp.close()
        except Exception:
            pass


# ---------------- Anthropic ----------------

def _to_anthropic_payload(messages, vision):
    system_parts = []
    out = []

    def push_user_blocks(blocks):
        if len(out) > 0 and out[-1]['role'] == 'user' and isinstance(out[-1]['content'], list):
            out[-1]['content'].extend(blocks)
        else:
            out.append({'role': 'user', 'content': list(blocks)})

    for m in messages:
        role = m.get('role')
        if role == 'system':
            system_parts.append(m.get('content', ''))
        elif role == 'user':
            blocks = [{'type': 'text', 'text': m.get('content', '')}]
            if vision:
                for url in (m.get('images') or [])[:4]:
                    blocks.insert(0, {'type': 'image', 'source': {'type': 'url', 'url': url}})
            push_user_blocks(blocks)
        elif role == 'assistant':
            blocks = []
            if m.get('content'):
                blocks.append({'type': 'text', 'text': m['content']})
            for tc in m.get('tool_calls') or []:
                try:
                    tool_input = json.loads(tc.get('arguments', '{}'))
                except Exception:
                    tool_input = {}
                blocks.append({'type': 'tool_use', 'id': tc['id'], 'name': tc['name'], 'input': tool_input})
            if len(blocks) == 0:
                blocks.append({'type': 'text', 'text': ''})
            out.append({'role': 'assistant', 'content': blocks})
        elif role == 'tool':
            push_user_blocks([{
                'type': 'tool_result',
                'tool_use_id': m.get('tool_call_id', ''),
                'content': m.get('content', ''),
            }])
    # Anthropic 要求首条消息角色为 user；潜行历史可能以自己(assistant)开头，去掉前导 assistant
    while out and out[0]['role'] == 'assistant':
        out.pop(0)
    return '\n'.join([s for s in system_parts if s]), out


def _chat_anthropic(bc, messages, tools, force_no_stream, opts=None):
    opts = opts or {}
    system_text, msg_list = _to_anthropic_payload(messages, bool(bc.get('vision', True)))
    payload = {
        'model': bc.get('model', ''),
        'max_tokens': bc.get('max_tokens', 2000),
        'messages': msg_list,
    }
    if system_text:
        payload['system'] = system_text
    if bc.get('temperature') is not None:
        payload['temperature'] = bc.get('temperature')
    if tools:
        payload['tools'] = [
            {'name': t['name'], 'description': t['desc'], 'input_schema': t['params']}
            for t in tools
        ]
    stream = bool(bc.get('stream', False)) and not force_no_stream
    if stream:
        payload['stream'] = True
    try:
        payload.update(bc.get('extra_body', {}) or {})
    except Exception:
        pass
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': str(bc.get('api_key', '')),
        'anthropic-version': str(bc.get('anthropic_version', '2023-06-01')),
    }
    try:
        headers.update(bc.get('extra_headers', {}) or {})
    except Exception:
        pass
    timeout = int(opts.get('timeout_override') or bc.get('timeout_sec', 120))
    resp = requests.post(str(bc.get('api_url', '')), headers=headers, json=payload, timeout=timeout, stream=stream)
    if resp.status_code != 200:
        return {'ok': False, 'text': '', 'tool_calls': [],
                'error': 'HTTP %s: %s' % (resp.status_code, resp.text[:300])}
    if stream:
        return _parse_anthropic_stream(resp)
    return _parse_anthropic_response(resp.json())


def _parse_anthropic_response(data):
    try:
        text = ''
        tool_calls = []
        for block in data.get('content') or []:
            if block.get('type') == 'text':
                text += block.get('text', '')
            elif block.get('type') == 'tool_use':
                tool_calls.append({
                    'id': block.get('id', 'toolu_%d' % len(tool_calls)),
                    'name': block.get('name', ''),
                    'arguments': json.dumps(block.get('input', {}), ensure_ascii=False),
                })
        return {
            'ok': True,
            'text': text,
            'tool_calls': tool_calls,
            'error': '',
            '_usage': data.get('usage'),
        }
    except Exception as e:
        return {'ok': False, 'text': '', 'tool_calls': [], 'error': '响应解析失败: %s | %s' % (e, str(data)[:300])}


def _parse_anthropic_stream(resp):
    text = ''
    blocks = {}
    usage = {}
    try:
        resp.encoding = 'utf-8'
    except Exception:
        pass
    try:
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if not line.startswith('data:'):
                continue
            try:
                event = json.loads(line[len('data:'):].strip())
            except Exception:
                continue
            etype = event.get('type', '')
            if etype == 'error':
                return {'ok': False, 'text': text, 'tool_calls': [],
                        'error': '流式错误: %s' % str(event.get('error'))[:300]}
            if etype == 'message_start':
                usage.update((event.get('message') or {}).get('usage') or {})
            elif etype == 'message_delta':
                usage.update(event.get('usage') or {})
            elif etype == 'content_block_start':
                idx = event.get('index', 0)
                cb = event.get('content_block') or {}
                if cb.get('type') == 'tool_use':
                    blocks[idx] = {'kind': 'tool', 'id': cb.get('id', ''), 'name': cb.get('name', ''), 'json': ''}
                else:
                    blocks[idx] = {'kind': 'text'}
            elif etype == 'content_block_delta':
                idx = event.get('index', 0)
                delta = event.get('delta') or {}
                if delta.get('type') == 'text_delta':
                    text += delta.get('text', '')
                elif delta.get('type') == 'input_json_delta':
                    slot = blocks.setdefault(idx, {'kind': 'tool', 'id': 'toolu_%d' % idx, 'name': '', 'json': ''})
                    slot['json'] = slot.get('json', '') + delta.get('partial_json', '')
            elif etype == 'message_stop':
                break
        tool_calls = []
        for idx in sorted(blocks.keys()):
            slot = blocks[idx]
            if slot.get('kind') == 'tool':
                tool_calls.append({
                    'id': slot.get('id') or 'toolu_%d' % idx,
                    'name': slot.get('name', ''),
                    'arguments': slot.get('json') or '{}',
                })
        return {'ok': True, 'text': text, 'tool_calls': tool_calls, 'error': '', '_usage': usage}
    except Exception as e:
        return {'ok': False, 'text': text, 'tool_calls': [], 'error': '流式解析失败: %s' % e}
    finally:
        try:
            resp.close()
        except Exception:
            pass


# ---------------- OpenAI Responses API (/v1/responses) ----------------

def _to_responses_input(messages, vision, audio=False, video=False):
    '''内部统一消息 → Responses API 的 (instructions, input[])。
    - system → instructions(顶层)
    - user → {role:user, content:[input_text(+input_image)]}
    - assistant 文本 → {role:assistant, content:[output_text]}；工具调用 → {type:function_call, call_id,name,arguments}
    - tool 结果 → {type:function_call_output, call_id, output}'''
    instructions = []
    inp = []
    for m in messages:
        role = m.get('role')
        if role == 'system':
            instructions.append(str(m.get('content', '')))
        elif role == 'user':
            images = m.get('images') or []
            audios = m.get('audios') or []
            videos = m.get('videos') or []
            if (vision and images) or (audio and audios) or (video and videos):
                content = [{'type': 'input_text', 'text': str(m.get('content', ''))}]
                if vision:
                    for url in images[:4]:
                        content.append({'type': 'input_image', 'image_url': url, 'detail': 'auto'})
                if audio:
                    for value in audios[:4]:
                        part = _audioPart(value)
                        if part.get('type') == 'input_audio':
                            content.append(part)
                if video:
                    for url in videos[:4]:
                        content.append({'type': 'input_video', 'video_url': url})
                inp.append({'role': 'user', 'content': content})
            else:
                inp.append({'role': 'user', 'content': str(m.get('content', ''))})
        elif role == 'assistant':
            if m.get('content'):
                inp.append({'role': 'assistant',
                            'content': [{'type': 'output_text', 'text': str(m['content'])}]})
            for tc in m.get('tool_calls') or []:
                inp.append({'type': 'function_call', 'call_id': tc['id'],
                            'name': tc['name'], 'arguments': tc.get('arguments', '{}')})
        elif role == 'tool':
            inp.append({'type': 'function_call_output',
                        'call_id': m.get('tool_call_id', ''),
                        'output': str(m.get('content', ''))})
    return '\n'.join([s for s in instructions if s]), inp


def _chat_responses(bc, messages, tools, force_no_stream, opts=None):
    opts = opts or {}
    instructions, inp = _to_responses_input(
        messages,
        bool(bc.get('vision', False)),
        bool(bc.get('audio', False)),
        bool(bc.get('video', False)),
    )
    payload = {
        'model': bc.get('model', ''),
        'input': inp,
        'max_output_tokens': bc.get('max_tokens', 2000),
    }
    if instructions:
        payload['instructions'] = instructions
    if bc.get('temperature') is not None:
        payload['temperature'] = bc.get('temperature')
    if tools:
        # Responses 的工具是【扁平】结构：{type:function, name, description, parameters}
        payload['tools'] = [
            {'type': 'function', 'name': t['name'], 'description': t['desc'], 'parameters': t['params']}
            for t in tools
        ]
    thinking = bc.get('thinking')
    if not opts.get('thinking_off') and isinstance(thinking, dict) and thinking.get('type') == 'enabled':
        payload['reasoning'] = {'effort': bc.get('reasoning_effort', 'high')}
    if opts.get('response_json') and not tools:
        payload['text'] = {'format': {'type': 'json_object'}}
    stream = bool(bc.get('stream', False)) and not force_no_stream
    if stream:
        payload['stream'] = True
    try:
        payload.update(bc.get('extra_body', {}) or {})
    except Exception:
        pass
    headers = {'Content-Type': 'application/json'}
    if str(bc.get('api_key', '')):
        headers['Authorization'] = 'Bearer ' + str(bc['api_key'])
    try:
        headers.update(bc.get('extra_headers', {}) or {})
    except Exception:
        pass
    timeout = int(opts.get('timeout_override') or bc.get('timeout_sec', 120))
    resp = requests.post(str(bc.get('api_url', '')), headers=headers, json=payload, timeout=timeout, stream=stream)
    if resp.status_code != 200:
        return {'ok': False, 'text': '', 'tool_calls': [],
                'error': 'HTTP %s: %s' % (resp.status_code, resp.text[:300])}
    if stream:
        return _parse_responses_stream(resp)
    return _parse_responses(resp.json())


def _parse_responses(data):
    try:
        text = ''
        tool_calls = []
        for item in data.get('output') or []:
            it = item.get('type')
            if it == 'message':
                for part in item.get('content') or []:
                    if part.get('type') == 'output_text':
                        text += part.get('text', '')
            elif it == 'function_call':
                tool_calls.append({
                    'id': item.get('call_id') or item.get('id', 'call_%d' % len(tool_calls)),
                    'name': item.get('name', ''),
                    'arguments': item.get('arguments', '') or '{}',
                })
        # 兜底：部分实现提供 output_text 快捷聚合字段
        if not text and isinstance(data.get('output_text'), str):
            text = data['output_text']
        return {
            'ok': True,
            'text': text,
            'tool_calls': tool_calls,
            'error': '',
            '_usage': data.get('usage'),
        }
    except Exception as e:
        return {'ok': False, 'text': '', 'tool_calls': [], 'error': '响应解析失败: %s | %s' % (e, str(data)[:300])}


def _parse_responses_stream(resp):
    text = ''
    calls = {}      # output_index -> {id,name,arguments}
    final = None
    try:
        resp.encoding = 'utf-8'
    except Exception:
        pass
    try:
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if not line.startswith('data:'):
                continue
            ds = line[len('data:'):].strip()
            if ds == '[DONE]':
                break
            try:
                ev = json.loads(ds)
            except Exception:
                continue
            et = ev.get('type', '')
            if et == 'response.output_text.delta':
                d = ev.get('delta')
                if isinstance(d, str):
                    text += d
            elif et == 'response.output_item.added':
                item = ev.get('item') or {}
                if item.get('type') == 'function_call':
                    idx = ev.get('output_index', len(calls))
                    calls[idx] = {'id': item.get('call_id') or item.get('id', ''),
                                  'name': item.get('name', ''), 'arguments': ''}
            elif et == 'response.function_call_arguments.delta':
                slot = calls.get(ev.get('output_index'))
                if slot is not None:
                    slot['arguments'] += ev.get('delta', '')
            elif et in ('response.completed', 'response.incomplete'):
                final = ev.get('response')
            elif et == 'response.failed' or et == 'error' or et.endswith('.error'):
                err = (ev.get('response') or {}).get('error') or ev.get('error') or ev
                return {'ok': False, 'text': text, 'tool_calls': [], 'error': '流式错误: %s' % str(err)[:300]}
        # 优先用 completed 事件里的完整 output(权威)
        if isinstance(final, dict) and final.get('output'):
            parsed = _parse_responses(final)
            if parsed.get('ok'):
                return parsed
        result_calls = []
        for idx in sorted(calls.keys(), key=lambda x: (x is None, x)):
            slot = calls[idx]
            if not slot.get('id'):
                slot['id'] = 'call_%s' % idx
            if slot.get('arguments') == '':
                slot['arguments'] = '{}'
            result_calls.append(slot)
        usage = final.get('usage') if isinstance(final, dict) else None
        return {'ok': True, 'text': text, 'tool_calls': result_calls, 'error': '', '_usage': usage}
    except Exception as e:
        return {'ok': False, 'text': text, 'tool_calls': [], 'error': '流式解析失败: %s' % e}
    finally:
        try:
            resp.close()
        except Exception:
            pass
