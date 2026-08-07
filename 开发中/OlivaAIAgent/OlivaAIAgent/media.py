# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 入站音频/视频子系统。

媒体先被解析成当前消息中的占位符，再按配置路由：主后端明确声明支持时
保留为模型输入；否则调用独立的 OpenAI-compatible 识别模型并替换成事实摘要。
本模块不负责 TTS，避免入站识别和出站语音合成互相污染。
'''

import base64
import hashlib
import json
import mimetypes
import os
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests

import OlivaAIAgent


OP_AUDIO_PATTERN = re.compile(r'\[(?:CQ|OP):record,[^\]]+\]', re.IGNORECASE)
OP_VIDEO_PATTERN = re.compile(r'\[(?:CQ|OP):video,[^\]]+\]', re.IGNORECASE)
OP_FILE_PATTERN = re.compile(r'\[(?:CQ|OP):file,[^\]]+\]', re.IGNORECASE)
AUDIO_PLACEHOLDER_PATTERN = re.compile(r'\[\[OLIVA_AUDIO_([0-9]+)\]\]')
VIDEO_PLACEHOLDER_PATTERN = re.compile(r'\[\[OLIVA_VIDEO_([0-9]+)\]\]')
VIDEO_FILE_EXTENSIONS = frozenset({
    '3gp', 'avi', 'flv', 'm2ts', 'm4v', 'mkv', 'mov', 'mp4', 'mpeg', 'mpg', 'mts', 'ts', 'webm', 'wmv',
})
_result_cache = {}
_CACHE_TTL = 900
_MAX_CACHE = 256


def audioPlaceholder(index):
    return '[[OLIVA_AUDIO_%d]]' % int(index)


def videoPlaceholder(index):
    return '[[OLIVA_VIDEO_%d]]' % int(index)


def _parseParams(tag):
    inner = tag[tag.find(',') + 1:-1] if ',' in tag else ''
    params = {}
    for part in inner.split(','):
        if '=' in part:
            key, value = part.split('=', 1)
            params[key.strip().lower()] = value
    return params


def tagRef(tag):
    params = _parseParams(tag)
    value = params.get('url') or params.get('file') or ''
    return str(value).strip()


def _mediaConf():
    value = OlivaAIAgent.conf.get('media', default={}) or {}
    return value if isinstance(value, dict) else {}


def isEnabled(kind):
    '''返回某一类入站媒体是否启用；旧版 media.enable 不再参与判断。'''
    child = _mediaConf().get(kind)
    return bool(child.get('enable', False)) if isinstance(child, dict) else False


def _hasVideoExtension(value):
    text = unquote(str(value or '')).strip().lower()
    if not text:
        return False
    # QQ 文件下载地址常把真实文件名放在 fname 查询参数里，不能只看 URL path。
    for match in re.finditer(r'\.([a-z0-9]{2,8})(?=$|[?#&,/\\\]])', text):
        if match.group(1) in VIDEO_FILE_EXTENSIONS:
            return True
    return False


def isVideoFileData(value):
    '''按文件名、URL、路径或 MIME 判断 file 消息是否实际为视频。'''
    if isinstance(value, dict):
        values = [value.get(key) for key in ('name', 'file_name', 'url', 'file', 'path', 'content_type', 'mime')]
        if any(str(item or '').lower().startswith('video/') for item in values):
            return True
        return any(_hasVideoExtension(item) for item in values)
    return _hasVideoExtension(value)


def hasVideoFileTag(message):
    return any(isVideoFileData(match.group(0)) for match in OP_FILE_PATTERN.finditer(str(message or '')))


def _mainEnabled(kind):
    try:
        cfg = OlivaAIAgent.aiClient.getBackendConf()
        return cfg.get('wire', 'openai') == 'openai' and bool(cfg.get(kind, False))
    except Exception:
        return False


def _route(kind):
    cfg = _mediaConf()
    use_main = cfg.get('use_main', 'auto')
    if use_main in (True, 'true', 'True', 1) and _mainEnabled(kind):
        return 'main'
    if use_main == 'auto' and _mainEnabled(kind):
        return 'main'
    return 'independent'


def _independentConf(kind):
    value = _mediaConf().get(kind, {})
    return value if isinstance(value, dict) else {}


def _audioProvider(cfg):
    '''选择独立语音接口协议；auto 同时兼容 OpenAI 和百炼原生 ASR。'''
    provider = str(cfg.get('provider', 'auto') or 'auto').strip().lower()
    if provider in ('dashscope', 'dashscope_asr', 'dashscope_multimodal', 'qwen_audio'):
        return 'dashscope_asr'
    if provider in ('openai', 'openai_compatible', 'compatible'):
        return 'openai_compatible'
    model = str(cfg.get('model', '') or '').strip().lower()
    api_url = str(cfg.get('api_url', '') or '').strip().lower()
    if model == 'qwen-audio-3.0-asr-flash' or 'aigc/multimodal-generation/generation' in api_url:
        return 'dashscope_asr'
    return 'openai_compatible'


def _dashscopeAudioUrl(cfg):
    '''把旧百炼兼容地址迁移到 Qwen-Audio 原生端点；第三方地址不擅自改写。'''
    url = str(cfg.get('api_url', '') or '').strip()
    endpoint = '/api/v1/services/aigc/multimodal-generation/generation'
    if endpoint in url:
        return url
    lower = url.lower()
    if '/compatible-mode/v1' in lower and ('dashscope.aliyuncs.com' in lower or '.maas.aliyuncs.com' in lower):
        return url[:lower.index('/compatible-mode/v1')] + endpoint
    return url


def getStatus():
    enabled = any(isEnabled(kind) for kind in ('audio', 'video'))
    status = {'enabled': enabled, 'audio': {}, 'video': {}}
    for kind in ('audio', 'video'):
        kind_enabled = isEnabled(kind)
        route = _route(kind) if kind_enabled else 'disabled'
        independent = _independentConf(kind)
        if route == 'main':
            backend = OlivaAIAgent.aiClient.getBackendConf()
            ready = bool(backend.get('api_url') and backend.get('api_key') and backend.get('model'))
            model = backend.get('model', '')
        else:
            ready = bool(independent.get('api_url') and independent.get('api_key') and independent.get('model'))
            model = independent.get('model', '')
        status[kind] = {
            'enabled': kind_enabled,
            'ready': kind_enabled and ready,
            'route': route,
            'model': str(model or ''),
        }
    active = [status[kind] for kind in ('audio', 'video') if status[kind]['enabled']]
    status['ready'] = bool(active) and all(item.get('ready') for item in active)
    return status


def _safeFormat(kind, value):
    text = str(value or '').replace('\r', ' ').replace('\n', ' ').strip()
    text = text.replace(']', '】')
    limit = 500 if kind == 'audio' else 600
    return text[:limit] or '未识别成功'


def factFormat(kind, value):
    return '[语音:%s]' % _safeFormat(kind, value) if kind == 'audio' else '[视频:%s]' % _safeFormat(kind, value)


def _sourceKey(kind, ref):
    text = str(ref or '').strip()
    if text.startswith(('http://', 'https://')):
        parts = urlsplit(text)
        text = '%s://%s%s' % (parts.scheme.lower(), parts.netloc.lower(), parts.path)
    return hashlib.sha256((kind + '\0' + text).encode('utf-8')).hexdigest()


def _cacheGet(kind, ref):
    key = _sourceKey(kind, ref)
    item = _result_cache.get(key)
    if item and item[0] > time.time():
        return item[1]
    _result_cache.pop(key, None)
    return None


def _cachePut(kind, ref, value):
    if not value:
        return
    _result_cache[_sourceKey(kind, ref)] = (time.time() + _CACHE_TTL, value)
    while len(_result_cache) > _MAX_CACHE:
        _result_cache.pop(next(iter(_result_cache)))


def _refLabel(ref):
    text = str(ref or '')
    if text.startswith('data:'):
        return 'data-url'
    if text.startswith(('http://', 'https://')):
        path = unquote(urlsplit(text).path)
        return os.path.basename(path)[:80] or 'remote'
    return os.path.basename(text.replace('\\', '/'))[:80] or 'local'


def _readBytes(ref, max_bytes, trace_id, kind):
    value = str(ref or '').strip()
    if value.startswith('data:'):
        try:
            header, body = value.split(',', 1)
            if ';base64' not in header:
                return None, '', 'data_url_not_base64'
            content = base64.b64decode(body, validate=False)
            if len(content) > max_bytes:
                return None, '', 'too_large'
            return content, header[5:].split(';', 1)[0], ''
        except Exception as exc:
            return None, '', '%s: %s' % (type(exc).__name__, exc)
    if value.startswith('file://'):
        value = unquote(urlsplit(value).path)
        if re.match(r'^/[A-Za-z]:', value):
            value = value[1:]
    try:
        if value.startswith(('http://', 'https://')):
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'media.%s.download' % kind,
                trace_id,
                file=_refLabel(value),
            )
            response = requests.get(value, timeout=60, stream=True)
            response.raise_for_status()
            chunks = []
            total = 0
            if hasattr(response, 'iter_content'):
                for chunk in response.iter_content(65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        return None, '', 'too_large'
                    chunks.append(chunk)
            else:
                content = bytes(getattr(response, 'content', b''))
                if len(content) > max_bytes:
                    return None, '', 'too_large'
                chunks.append(content)
            content = b''.join(chunks)
            headers = getattr(response, 'headers', {}) or {}
            return content, headers.get('Content-Type', ''), ''
        path = Path(value)
        if not path.is_file():
            return None, '', 'file_missing'
        if path.stat().st_size > max_bytes:
            return None, '', 'too_large'
        return path.read_bytes(), mimetypes.guess_type(path.name)[0] or '', ''
    except Exception as exc:
        return None, '', '%s: %s' % (type(exc).__name__, exc)


def _dataUrl(kind, ref, mode, trace_id, max_bytes=None):
    if mode not in ('base64', 'data', 'data_url'):
        if not str(ref).startswith(('http://', 'https://', 'data:')):
            return _dataUrl(kind, ref, 'base64', trace_id)
        return str(ref), ''
    if max_bytes is None:
        try:
            max_bytes = max(1, int(_mediaConf().get('max_bytes', 52428800)))
        except (TypeError, ValueError):
            max_bytes = 52428800
    else:
        try:
            max_bytes = max(1, int(max_bytes))
        except (TypeError, ValueError):
            max_bytes = 52428800
    content, content_type, error = _readBytes(ref, max_bytes, trace_id, kind)
    if content is None:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'media.%s.failed' % kind,
            trace_id,
            file=_refLabel(ref),
            reason=error,
        )
        return None, ''
    if not content_type or not content_type.startswith(('audio/', 'video/')):
        guessed = mimetypes.guess_type(_refLabel(ref))[0]
        content_type = guessed or ('audio/mpeg' if kind == 'audio' else 'video/mp4')
    return 'data:%s;base64,%s' % (content_type.split(';')[0], base64.b64encode(content).decode('ascii')), content_type


def _formatFromMime(content_type, ref):
    mime = str(content_type or '').split(';', 1)[0].lower()
    known_formats = {
        'audio/aac': 'aac',
        'audio/flac': 'flac',
        'audio/mpeg': 'mp3',
        'audio/mp3': 'mp3',
        # QQ 语音常以 Ogg 容器承载 Opus；Qwen ASR 接口要求填写 opus。
        'audio/ogg': 'opus',
        'audio/opus': 'opus',
        'audio/wav': 'wav',
        'audio/x-wav': 'wav',
    }
    if mime in known_formats:
        return known_formats[mime]
    ext = mimetypes.guess_extension(mime) or Path(_refLabel(ref)).suffix.lower()
    return ext.lstrip('.') or ('mp3' if mime.startswith('audio/') else 'mp4')


def _extractModelText(data):
    try:
        content = data['choices'][0]['message'].get('content', '')
        if isinstance(content, list):
            content = ''.join(str(item.get('text', '')) for item in content if isinstance(item, dict))
        return str(content or '').strip()
    except Exception:
        return ''


def _parseResult(kind, text):
    value = str(text or '').strip()
    value = re.sub(r'^```(?:json)?\s*|\s*```$', '', value, flags=re.I).strip()
    try:
        data = json.loads(value)
        if isinstance(data, dict):
            for key in ('text', 'transcript', 'summary', 'content', 'description'):
                if str(data.get(key) or '').strip():
                    return _safeFormat(kind, data[key])
    except Exception:
        pass
    return _safeFormat(kind, value)


def _extractDashscopeAudioText(data):
    '''读取 Qwen-Audio-3.0-ASR-Flash 原生接口的文本字段。'''
    if not isinstance(data, dict):
        return ''
    output = data.get('output')
    if not isinstance(output, dict):
        return str(data.get('text') or '').strip()
    nested = output.get('output')
    sentence = nested.get('sentence') if isinstance(nested, dict) else None
    candidates = (
        output.get('text'),
        sentence.get('text') if isinstance(sentence, dict) else '',
        nested.get('text') if isinstance(nested, dict) else '',
        data.get('text'),
    )
    for value in candidates:
        if str(value or '').strip():
            return str(value).strip()
    return ''


def _callDashscopeAudio(ref, cfg, trace_id):
    '''调用 Qwen-Audio-3.0-ASR-Flash 的百炼原生同步接口。'''
    started = time.perf_counter()
    mode = str(cfg.get('mode', 'base64')).lower()
    # 该模型限制单文件 10 MB；Base64 会膨胀，编码传输时把原文件上限收紧到约 7.5 MB。
    configured_limit = cfg.get('max_bytes', 10 * 1024 * 1024)
    try:
        max_bytes = min(10 * 1024 * 1024, max(1, int(configured_limit)))
    except (TypeError, ValueError):
        max_bytes = 10 * 1024 * 1024
    if mode not in ('url', 'remote'):
        max_bytes = min(max_bytes, 10 * 1024 * 1024 * 3 // 4)
    prepared, content_type = _dataUrl(
        'audio',
        ref,
        mode,
        trace_id,
        max_bytes=max_bytes,
    )
    if not prepared:
        return None
    content = []
    prompt = str(cfg.get('prompt') or '').strip()
    if prompt:
        content.append({'type': 'input_text', 'text': prompt})
    # 原生接口要求完整 Data URL；不能像 OpenAI input_audio 一样剥掉头部。
    content.append({'type': 'input_audio', 'input_audio': {'data': prepared}})
    audio_format = str(cfg.get('format') or _formatFromMime(content_type, ref)).strip().lower()
    try:
        sample_rate = int(cfg.get('sample_rate', 16000))
    except (TypeError, ValueError):
        sample_rate = 16000
    payload = {
        'model': cfg.get('model', ''),
        'input': {
            'messages': [{
                'role': 'user',
                'content': content,
            }],
        },
        'parameters': {
            'format': audio_format or 'wav',
            'sample_rate': sample_rate,
        },
    }
    headers = {
        'Content-Type': 'application/json',
        'X-DashScope-SSE': 'disable',
    }
    if cfg.get('api_key'):
        headers['Authorization'] = 'Bearer ' + str(cfg['api_key'])
    url = _dashscopeAudioUrl(cfg)
    if not url:
        return None
    try:
        headers.update(cfg.get('extra_headers', {}) or {})
        payload.update(cfg.get('extra_body', {}) or {})
    except Exception:
        pass
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'media.audio.request',
        trace_id,
        file=_refLabel(ref),
        model=cfg.get('model', ''),
        mode=mode,
        format=audio_format,
        provider='dashscope_asr',
    )
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=int(cfg.get('timeout_sec', 120)),
        )
        if not 200 <= response.status_code < 300:
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'media.audio.result',
                trace_id,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                result='失败',
                status=response.status_code,
                error=str(response.text)[:300],
            )
            return None
        response_data = response.json()
        text = _extractDashscopeAudioText(response_data)
        result = _parseResult('audio', text)
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'media.audio.result',
            trace_id,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            result='成功' if result and result != '未识别成功' else '失败',
            text_chars=len(result or ''),
        )
        return result
    except Exception as exc:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'media.audio.result',
            trace_id,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            result='失败',
            error='%s: %s' % (type(exc).__name__, exc),
        )
        return None


def _callIndependent(kind, ref, cfg, trace_id):
    if kind == 'audio' and _audioProvider(cfg) == 'dashscope_asr':
        return _callDashscopeAudio(ref, cfg, trace_id)
    started = time.perf_counter()
    mode = str(cfg.get('mode', 'base64' if kind == 'audio' else 'url')).lower()
    prepared, content_type = _dataUrl(kind, ref, mode, trace_id)
    if not prepared:
        return None
    if kind == 'audio':
        if not prepared.startswith('data:'):
            prepared, content_type = _dataUrl(kind, ref, 'base64', trace_id)
            if not prepared:
                return None
        if prepared.startswith('data:'):
            audio_data = prepared.split(',', 1)[1]
        else:
            audio_data = prepared
        media_part = {
            'type': 'input_audio',
            'input_audio': {'data': audio_data, 'format': _formatFromMime(content_type, ref)},
        }
        prompt = cfg.get('prompt') or '请准确转写这段语音，只输出 JSON：{"text":"转写内容"}。不要补写没有听到的内容。'
    else:
        media_part = {'type': 'video_url', 'video_url': {'url': prepared}}
        prompt = cfg.get('prompt') or '请概括这段视频的可见内容、动作和可听到的对白，只输出 JSON：{"summary":"内容摘要"}。'
    url = str(cfg.get('api_url', '')).rstrip('/')
    if not url.endswith('/chat/completions'):
        url += '/chat/completions'
    payload = {
        'model': cfg.get('model', ''),
        'messages': [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': [{'type': 'text', 'text': prompt}, media_part]},
        ],
        'temperature': 0,
        'max_tokens': int(cfg.get('max_tokens', 1200)),
        'stream': False,
        'response_format': {'type': 'json_object'},
    }
    headers = {'Content-Type': 'application/json'}
    if cfg.get('api_key'):
        headers['Authorization'] = 'Bearer ' + str(cfg['api_key'])
    try:
        headers.update(cfg.get('extra_headers', {}) or {})
        payload.update(cfg.get('extra_body', {}) or {})
    except Exception:
        pass
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'media.%s.request' % kind,
        trace_id,
        file=_refLabel(ref),
        model=cfg.get('model', ''),
        mode=mode,
        provider='openai_compatible',
    )
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=int(cfg.get('timeout_sec', 120)),
        )
        if response.status_code != 200:
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'media.%s.result' % kind,
                trace_id,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                result='失败',
                status=response.status_code,
                error=str(response.text)[:300],
            )
            return None
        result = _parseResult(kind, _extractModelText(response.json()))
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'media.%s.result' % kind,
            trace_id,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            result='成功' if result and result != '未识别成功' else '失败',
            text_chars=len(result or ''),
        )
        return result
    except Exception as exc:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'media.%s.result' % kind,
            trace_id,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            result='失败',
            error='%s: %s' % (type(exc).__name__, exc),
        )
        return None


def _recognize(kind, ref, trace_id=None):
    cached = _cacheGet(kind, ref)
    if cached:
        return cached
    cfg = _independentConf(kind)
    if not cfg.get('api_url') or not cfg.get('api_key') or not cfg.get('model'):
        return factFormat(kind, '未识别成功')
    result = _callIndependent(kind, ref, cfg, trace_id)
    fact = factFormat(kind, result or '未识别成功')
    if result:
        _cachePut(kind, ref, fact)
    return fact


def _replace(text, pattern, facts, kind):
    had = pattern.search(str(text)) is not None

    def repl(match):
        index = int(match.group(1))
        return facts[index] if index < len(facts) else factFormat(kind, '未识别成功')

    output = pattern.sub(repl, str(text))
    if not had and facts:
        output = (output + ' ' + ' '.join(facts)).strip()
    return output


def translateIncoming(message, parsed, allow_network=True, trace_id=None):
    '''把当前消息的音频/视频段转为事实；主模型路由时保留媒体列表。'''
    if not isinstance(parsed, dict):
        return str(message or '')
    result = str(message or '')
    audio_index = 0
    video_index = 0

    def replace_audio_tag(_match):
        nonlocal audio_index
        placeholder = audioPlaceholder(audio_index)
        audio_index += 1
        return placeholder

    def replace_video_tag(_match):
        nonlocal video_index
        placeholder = videoPlaceholder(video_index)
        video_index += 1
        return placeholder

    result = OP_AUDIO_PATTERN.sub(replace_audio_tag, result)
    result = OP_VIDEO_PATTERN.sub(replace_video_tag, result)
    for kind, key, pattern in (
        ('audio', 'audio_urls', AUDIO_PLACEHOLDER_PATTERN),
        ('video', 'video_urls', VIDEO_PLACEHOLDER_PATTERN),
    ):
        refs = list(parsed.get(key) or [])[:4]
        if not isEnabled(kind):
            result = pattern.sub('[语音]' if kind == 'audio' else '[视频]', result)
            parsed[key] = []
            continue
        if not refs:
            continue
        route = _route(kind)
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'media.%s.route' % kind,
            trace_id,
            count=len(refs),
            route=route,
            model=(OlivaAIAgent.aiClient.getBackendConf() if route == 'main' else _independentConf(kind)).get('model', ''),
        )
        if route == 'main':
            result = _replace(result, pattern, [('[语音]' if kind == 'audio' else '[视频]')] * len(refs), kind)
            continue
        if not allow_network:
            continue
        facts = [_recognize(kind, ref, trace_id=trace_id) for ref in refs]
        result = _replace(result, pattern, facts, kind)
        parsed[key] = []
    return result


def prepareMainInputs(parsed, trace_id=None):
    '''为主模型准备音频/视频输入；音频默认转 data URL，视频默认保留远程 URL。'''
    if not isinstance(parsed, dict):
        return [], []
    audios = []
    videos = []
    for kind, key, target in (('audio', 'audio_urls', audios), ('video', 'video_urls', videos)):
        if not isEnabled(kind) or _route(kind) != 'main':
            continue
        mode = str(_mediaConf().get(kind, {}).get('main_mode', 'base64' if kind == 'audio' else 'url'))
        for ref in list(parsed.get(key) or [])[:4]:
            prepared, _ = _dataUrl(kind, ref, mode, trace_id)
            target.append(prepared or ref)
    return audios, videos


def prepareQuotedMedia(parsed, trace_id=None):
    quote = parsed.get('quote') if isinstance(parsed, dict) else None
    if not isinstance(quote, dict):
        return []
    facts = []
    for kind, key in (('audio', 'audio_urls'), ('video', 'video_urls')):
        if not isEnabled(kind) or _route(kind) == 'main':
            continue
        for ref in list(quote.get(key) or [])[:4]:
            facts.append(_recognize(kind, ref, trace_id=trace_id))
    return list(dict.fromkeys(facts))
