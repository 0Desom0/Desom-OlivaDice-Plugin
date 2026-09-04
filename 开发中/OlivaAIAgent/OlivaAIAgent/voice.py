# -*- encoding: utf-8 -*-
'''DashScope / OpenAI-compatible 语音合成与 OlivOS 语音消息发送。'''

import base64
import hashlib
import os
import re
import threading
import time
from urllib.parse import urlsplit

import requests

import OlivOS
import OlivaAIAgent

_FORMAT_EXTENSIONS = {
    'aac': '.aac',
    'flac': '.flac',
    'mp3': '.mp3',
    'ogg': '.ogg',
    'opus': '.opus',
    'pcm': '.pcm',
    'wav': '.wav',
}
_CONTENT_TYPE_FORMATS = {
    'audio/aac': 'aac',
    'audio/flac': 'flac',
    'audio/mpeg': 'mp3',
    'audio/mp3': 'mp3',
    'audio/ogg': 'ogg',
    'audio/opus': 'opus',
    'audio/wav': 'wav',
    'audio/wave': 'wav',
    'audio/x-wav': 'wav',
}
_DASHSCOPE_PROVIDER = 'dashscope_multimodal'
_OPENAI_PROVIDER = 'openai_compatible'
_MIMO_PROVIDER = 'mimo_tts'
_DASHSCOPE_DEFAULT_URL = (
    'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'
)
_MIMO_DEFAULT_URL = 'https://api.xiaomimimo.com/v1/chat/completions'
_MIMO_CLONE_MAX_B64 = 10 * 1024 * 1024
_MIMO_PRESET_VOICES = (
    'mimo_default',
    '冰糖',
    '茉莉',
    '苏打',
    '白桦',
    'Mia',
    'Chloe',
    'Milo',
    'Dean',
)
_MIMO_MODE_ALIASES = {
    'default': 'default',
    'tts': 'default',
    'preset': 'default',
    'clone': 'clone',
    'voiceclone': 'clone',
    'voice_clone': 'clone',
    'design': 'design',
    'create': 'design',
    'voicedesign': 'design',
    'voice_design': 'design',
}
_MIMO_MODE_MODELS = {
    'default': 'mimo-v2.5-tts',
    'clone': 'mimo-v2.5-tts-voiceclone',
    'design': 'mimo-v2.5-tts-voicedesign',
}
_MIMO_FORMATS = ('wav', 'mp3', 'pcm', 'pcm16')
_DASHSCOPE_VOICE_FALLBACKS = (
    'cherry', 'bella', 'serena', 'chelsie', 'ethan', 'vivian', 'moon', 'maia', 'katerina', 'ryan',
)
_PROVIDER_ALIASES = {
    'dashscope': _DASHSCOPE_PROVIDER,
    _DASHSCOPE_PROVIDER: _DASHSCOPE_PROVIDER,
    'openai': _OPENAI_PROVIDER,
    _OPENAI_PROVIDER: _OPENAI_PROVIDER,
    'mimo': _MIMO_PROVIDER,
    'mimo_tts': _MIMO_PROVIDER,
    'xiaomi_mimo': _MIMO_PROVIDER,
    'xiaomimimo': _MIMO_PROVIDER,
}
_VOICE_DEDUPE_CTX_KEY = '_oliva_ai_voice_texts'
_VOICE_SENT_CTX_KEY = '_oliva_ai_voice_sent'
_VOICE_CACHE_HARD_LIMIT = 10
_voiceDedupeLock = threading.Lock()
_SIMULATED_VOICE_PATTERNS = (
    re.compile(r'^\s*\[语音消息\]\s*(?P<text>.+?)\s*$', re.S),
    re.compile(r'^\s*\[语音[:：](?P<text>.+?)\]\s*$', re.S),
)


def _voiceTextKey(text):
    normalized = re.sub(r'\s+', ' ', str(text or '').strip())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _claimVoiceText(ctx, text):
    key = _voiceTextKey(text)
    with _voiceDedupeLock:
        sent_keys = ctx.setdefault(_VOICE_DEDUPE_CTX_KEY, set())
        if key in sent_keys:
            return False, key
        sent_keys.add(key)
    return True, key


def _releaseVoiceText(ctx, key):
    with _voiceDedupeLock:
        sent_keys = ctx.get(_VOICE_DEDUPE_CTX_KEY)
        if isinstance(sent_keys, set):
            sent_keys.discard(key)


def hasSentVoice(ctx):
    return isinstance(ctx, dict) and bool(ctx.get(_VOICE_SENT_CTX_KEY))


def _markVoiceSent(ctx):
    if isinstance(ctx, dict):
        ctx[_VOICE_SENT_CTX_KEY] = True


def simulatedVoiceText(text):
    '''提取模型用普通文字模拟的整条语音；普通正文中的媒体说明不处理。'''
    value = str(text or '')
    for pattern in _SIMULATED_VOICE_PATTERNS:
        matched = pattern.fullmatch(value)
        if matched is not None:
            content = str(matched.group('text') or '').strip()
            return content or None
    return None


def sendSimulatedVoice(ctx, text):
    '''把模型误写成文字标记的语音兜底转换为真实语音。'''
    content = simulatedVoiceText(text)
    if content is None or not getStatus()['ready']:
        return None
    OlivaAIAgent.conf.traceLog(
        ctx.get('Proc'),
        'voice.marker.converted',
        ctx.get('trace_id'),
        text_chars=len(content),
    )
    return sendVoice(
        ctx,
        content,
        instructions='自然、贴合当前语气地说出这句话，保持正常语速和清晰停顿。',
    )


def outputDir():
    path = os.path.join(OlivaAIAgent.conf.dataPath, 'voice')
    OlivaAIAgent.conf.releaseDir(path)
    return path


def getStatus():
    cfg = OlivaAIAgent.conf.get('voice', default={}) or {}
    enabled = bool(cfg.get('enabled', False))
    api_url = str(cfg.get('api_url', '')).strip()
    model = str(cfg.get('model', '')).strip()
    voice = str(cfg.get('voice', '')).strip()
    provider_value = str(cfg.get('provider', _DASHSCOPE_PROVIDER)).strip().lower()
    provider = _PROVIDER_ALIASES.get(provider_value, provider_value)
    mimo_mode = _resolveMimoMode(cfg) if provider == _MIMO_PROVIDER else ''
    clone_audio = str(cfg.get('clone_audio', '')).strip()
    design_prompt = str(cfg.get('design_prompt', '')).strip()
    response_format = str(cfg.get('response_format', 'mp3')).strip().lower()
    if provider == _MIMO_PROVIDER:
        api_url = _resolveMimoApiUrl(api_url)
        model = _MIMO_MODE_MODELS.get(mimo_mode) or model
        response_format = _resolveMimoFormat(response_format)
        if mimo_mode == 'default':
            voice = _resolveMimoPresetVoice(voice)
        elif mimo_mode == 'design' and not design_prompt:
            design_prompt = personaVoiceDesignPrompt()
    provider_ready = provider in [_DASHSCOPE_PROVIDER, _OPENAI_PROVIDER, _MIMO_PROVIDER]
    if provider == _DASHSCOPE_PROVIDER:
        provider_ready = provider_ready and bool(voice)
    elif provider == _MIMO_PROVIDER:
        if mimo_mode == 'clone':
            provider_ready = provider_ready and bool(clone_audio)
        elif mimo_mode == 'design':
            provider_ready = provider_ready and bool(design_prompt)
        else:
            provider_ready = provider_ready and bool(voice)
    return {
        'enabled': enabled,
        'ready': enabled and provider_ready and bool(api_url and model),
        'provider': provider,
        'api_url': api_url,
        'model': model,
        'voice': voice,
        'mimo_mode': mimo_mode,
        'clone_audio': clone_audio,
        'design_prompt': design_prompt,
        'language_type': str(cfg.get('language_type', 'Chinese')).strip(),
        'response_format': response_format,
        'optimize_text_preview': bool(cfg.get('optimize_text_preview', False)),
    }


def _cleanOldFiles():
    configured = int(OlivaAIAgent.conf.get('voice', 'max_files', default=_VOICE_CACHE_HARD_LIMIT))
    max_files = max(1, min(_VOICE_CACHE_HARD_LIMIT, configured))
    removed = 0
    try:
        directory = outputDir()
        entries = [
            os.path.join(directory, name)
            for name in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, name))
        ]
        entries.sort(key=lambda path: os.path.getmtime(path), reverse=True)
        for path in entries[max_files:]:
            try:
                os.remove(path)
                removed += 1
            except Exception:
                pass
    except Exception:
        return removed
    if removed:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'voice.cache.cleaned',
            removed=removed,
            retained=max_files,
        )
    return removed


def _normalizeFormat(value):
    fmt = str(value or '').strip().lower().lstrip('.')
    return {
        'mpeg': 'mp3',
        'mpeg3': 'mp3',
        'wave': 'wav',
        'x-wav': 'wav',
    }.get(fmt, fmt)


def _formatFromContentType(content_type):
    mime = str(content_type or '').split(';', 1)[0].strip().lower()
    return _CONTENT_TYPE_FORMATS.get(mime, '')


def _formatFromUrl(url):
    try:
        extension = os.path.splitext(urlsplit(str(url)).path)[1]
    except Exception:
        return ''
    fmt = _normalizeFormat(extension)
    return fmt if fmt in _FORMAT_EXTENSIONS else ''


def _formatFromBytes(content):
    if not isinstance(content, bytes):
        return ''
    if content.startswith(b'RIFF') and content[8:12] == b'WAVE':
        return 'wav'
    if content.startswith(b'fLaC'):
        return 'flac'
    if content.startswith(b'OggS'):
        return 'opus' if b'OpusHead' in content[:128] else 'ogg'
    if content.startswith(b'ID3'):
        return 'mp3'
    if len(content) >= 2 and content[0] == 0xFF:
        if content[1] & 0xF6 == 0xF0:
            return 'aac'
        if content[1] & 0xE0 == 0xE0:
            return 'mp3'
    return ''


def _saveAudio(content, response_format):
    if not isinstance(content, bytes) or not content:
        raise ValueError('语音接口没有返回音频数据')
    max_bytes = max(1024, int(OlivaAIAgent.conf.get('voice', 'max_bytes', default=15 * 1024 * 1024)))
    if len(content) > max_bytes:
        raise ValueError('语音文件超过大小限制（%d 字节）' % max_bytes)
    fmt = _normalizeFormat(response_format) or _formatFromBytes(content) or 'mp3'
    ext = _FORMAT_EXTENSIONS.get(fmt, '.mp3')
    digest = hashlib.sha256(content).hexdigest()[:16]
    path = os.path.join(outputDir(), 'voice_%d_%s%s' % (int(time.time()), digest, ext))
    try:
        with open(path, 'wb') as file_obj:
            file_obj.write(content)
    except Exception as e:
        raise OSError('语音文件保存失败: %s' % e) from e
    _cleanOldFiles()
    return path


def _decodeBase64(value):
    text = str(value or '').strip()
    if text.startswith('data:') and ',' in text:
        text = text.split(',', 1)[1]
    if len(text) < 16 or not re.fullmatch(r'[A-Za-z0-9+/=_-]+', text):
        return None
    try:
        return base64.b64decode(text + '=' * (-len(text) % 4), validate=False)
    except Exception:
        return None


def _findAudioValue(value):
    if isinstance(value, dict):
        for key in ('url', 'audio_url'):
            item = value.get(key)
            if isinstance(item, str) and item.startswith(('http://', 'https://')):
                return 'url', item, _formatFromUrl(item)
        for key in ('b64_json', 'base64', 'audio', 'data'):
            item = value.get(key)
            if isinstance(item, str):
                if item.startswith(('http://', 'https://')):
                    return 'url', item, _formatFromUrl(item)
                content = _decodeBase64(item)
                if content:
                    data_format = ''
                    if item.startswith('data:'):
                        data_format = _formatFromContentType(item[5:].split(';', 1)[0])
                    return 'bytes', content, data_format or _formatFromBytes(content)
        for item in value.values():
            found = _findAudioValue(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _findAudioValue(item)
            if found:
                return found
    return None


def _audioFromChatCompletion(data):
    if not isinstance(data, dict):
        return None
    choices = data.get('choices')
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get('message') or first.get('delta') or {}
    if not isinstance(message, dict):
        return None
    audio = message.get('audio')
    if not isinstance(audio, dict):
        return None
    raw = audio.get('data')
    if not isinstance(raw, str) or not raw.strip():
        return None
    content = _decodeBase64(raw)
    if not content:
        return None
    return content, _formatFromBytes(content)


def _audioFromResponse(response, timeout):
    content_type = str(response.headers.get('Content-Type', '')).lower()
    if content_type.startswith('audio/') or 'application/octet-stream' in content_type:
        return response.content, _formatFromContentType(content_type) or _formatFromBytes(response.content)
    try:
        data = response.json()
    except Exception as e:
        raise ValueError('语音接口返回的不是音频或有效 JSON') from e
    chat_audio = _audioFromChatCompletion(data)
    if chat_audio:
        return chat_audio
    found = _findAudioValue(data)
    if not found:
        if isinstance(data, dict):
            error_code = data.get('code') or data.get('status_code')
            error_message = data.get('message') or data.get('msg')
            if error_code or error_message:
                raise RuntimeError('语音接口返回错误 %s: %s' % (error_code or '-', error_message or '-'))
        raise ValueError('语音接口 JSON 中没有可用的音频 URL 或 Base64')
    kind, value, format_hint = found
    if kind == 'bytes':
        return value, format_hint or _formatFromBytes(value)
    download = requests.get(value, timeout=timeout)
    download.raise_for_status()
    download_type = str(download.headers.get('Content-Type', ''))
    audio_format = (
        _formatFromContentType(download_type)
        or format_hint
        or _formatFromUrl(value)
        or _formatFromBytes(download.content)
    )
    return download.content, audio_format


def _dashscopePayload(status, cfg, content, instructions):
    extra_body = cfg.get('extra_body', {})
    payload = dict(extra_body) if isinstance(extra_body, dict) else {}
    input_data = dict(payload.get('input')) if isinstance(payload.get('input'), dict) else {}
    parameters = dict(payload.get('parameters')) if isinstance(payload.get('parameters'), dict) else {}
    input_data.update({'text': content, 'voice': status['voice']})
    if status['language_type']:
        input_data['language_type'] = status['language_type']
    voice_instructions = str(instructions or '').strip()
    if voice_instructions and 'instruct' in status['model'].lower():
        parameters['instructions'] = voice_instructions
        parameters['optimize_instructions'] = bool(cfg.get('optimize_instructions', True))
    parameters['stream'] = False
    payload.update({
        'model': status['model'],
        'input': input_data,
        'parameters': parameters,
    })
    return payload


def _openaiPayload(status, cfg, content):
    payload = {
        'model': status['model'],
        'input': content,
        'response_format': status['response_format'],
    }
    if status['voice']:
        payload['voice'] = status['voice']
    speed = cfg.get('speed', 1.0)
    if speed not in [None, '']:
        payload['speed'] = float(speed)
    extra_body = cfg.get('extra_body', {})
    if isinstance(extra_body, dict):
        payload.update(extra_body)
    return payload


def _mimoModeFromModel(model):
    name = str(model or '').strip().lower().replace('-', '_')
    if 'voiceclone' in name or 'voice_clone' in name:
        return 'clone'
    if 'voicedesign' in name or 'voice_design' in name:
        return 'design'
    if 'mimo' in name and 'tts' in name:
        return 'default'
    return ''


def _resolveMimoMode(cfg):
    raw = str(cfg.get('mimo_mode', '') or '').strip().lower().replace('-', '_')
    if raw in _MIMO_MODE_ALIASES:
        return _MIMO_MODE_ALIASES[raw]
    return _mimoModeFromModel(cfg.get('model', '')) or 'default'


def _resolveMimoApiUrl(api_url):
    url = str(api_url or '').strip()
    if not url:
        return _MIMO_DEFAULT_URL
    normalized = url.rstrip('/')
    if normalized == _DASHSCOPE_DEFAULT_URL.rstrip('/'):
        return _MIMO_DEFAULT_URL
    if '/audio/speech' in normalized:
        return _MIMO_DEFAULT_URL
    return url


def _resolveMimoPresetVoice(voice):
    value = str(voice or '').strip()
    if value in _MIMO_PRESET_VOICES:
        return value
    if not value or value.lower() in _DASHSCOPE_VOICE_FALLBACKS:
        return '冰糖'
    return value


def _resolveMimoFormat(value):
    fmt = _normalizeFormat(value)
    if fmt == 'pcm':
        return 'wav'
    if fmt in _MIMO_FORMATS:
        return fmt
    return 'wav'


def personaVoiceDesignPrompt(system_prompt=''):
    '''根据当前人设生成 MIMO voicedesign 用的音色描述; 不把人设全文塞进接口.'''
    text = str(
        system_prompt
        or OlivaAIAgent.conf.get('prompt', 'system', default='')
        or ''
    )
    if any(token in text for token in ('芙萝妮娅', '小芙', 'Fronia', 'fronia')):
        return (
            '年轻少女声, 听起来大约十五六岁, 娇小但口齿清脆. '
            '音色偏亮、略带奶气和一点软乎乎的婴儿肥感, 不是幼齿童声, 也不是成熟御姐. '
            '语速偏快但不赶, 尾音常轻轻上扬或带一点拖腔, 活泼元气里夹着傲娇和得意, 偶尔故意嘴硬. '
            '说话像群聊里的狐娘, 咬字轻巧、口语化, 不播音腔也不夹子过头.'
        )
    if '女' in text or '少女' in text:
        return (
            '年轻女性声音, 口齿清晰, 语速自然偏快, 语气口语化, '
            '带一点亲近感, 不播音腔, 不做作.'
        )
    if '男' in text or '少年' in text:
        return (
            '年轻男性声音, 口齿清晰, 语速自然, 语气口语化, '
            '沉稳里带一点轻松, 不播音腔.'
        )
    return (
        '年轻清晰的中文口语声, 语速自然, 语气轻松亲近, '
        '适合即时通讯短句, 不播音腔也不机械.'
    )


def _pluginRoot():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cloneSearchRoots():
    plugin_root = _pluginRoot()
    config_path = str(getattr(OlivaAIAgent.conf, 'CONFIG_PATH', '') or '')
    roots = [
        os.getcwd(),
        plugin_root,
        os.path.dirname(os.path.abspath(config_path)) if config_path else '',
        OlivaAIAgent.conf.dataPath,
        os.path.join(OlivaAIAgent.conf.dataPath, 'voice'),
        os.path.join(plugin_root, 'tts_samples'),
        os.path.join(plugin_root, 'voice'),
    ]
    try:
        for name in os.listdir(plugin_root):
            path = os.path.join(plugin_root, name)
            if os.path.isdir(path) and name.startswith('试听'):
                roots.append(path)
    except Exception:
        pass
    seen = set()
    for root in roots:
        text = str(root or '').strip()
        if not text:
            continue
        key = os.path.normcase(os.path.abspath(text))
        if key in seen:
            continue
        seen.add(key)
        yield text


def resolveCloneAudioPath(value):
    '''把 clone_audio 解析成已存在的本地文件, 同时接受绝对路径和相对路径.'''
    text = str(value or '').strip().strip('"').strip("'")
    if not text or text.startswith('data:'):
        return ''
    candidates = []
    normalized = os.path.normpath(text)
    candidates.append(normalized)
    if not os.path.isabs(normalized):
        for root in _cloneSearchRoots():
            candidates.append(os.path.normpath(os.path.join(root, normalized)))
    seen = set()
    for path in candidates:
        if not path:
            continue
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(path):
            return os.path.abspath(path)
    return ''


def _cloneMime(path, content):
    ext = _normalizeFormat(os.path.splitext(str(path or ''))[1])
    fmt = ext if ext in ('mp3', 'wav') else (_formatFromBytes(content) or '')
    if fmt == 'mp3':
        return 'audio/mpeg'
    if fmt == 'wav':
        return 'audio/wav'
    raise ValueError('音色克隆只支持 mp3 或 wav 参考音频')


def _loadCloneVoice(cfg):
    value = str(cfg.get('clone_audio', '') or '').strip()
    if not value:
        raise ValueError('音色克隆需要配置 clone_audio (wav/mp3 路径或 data URL)')
    if value.startswith('data:') and ';base64,' in value:
        encoded = value.split(',', 1)[1]
        if len(encoded) > _MIMO_CLONE_MAX_B64:
            raise ValueError('音色克隆参考音频 Base64 超过 10MB 限制')
        return value
    path = resolveCloneAudioPath(value)
    if not path:
        content = _decodeBase64(value)
        if not content:
            raise ValueError('找不到音色克隆参考音频: %s' % value)
        mime = _cloneMime('', content)
        encoded = base64.b64encode(content).decode('ascii')
        if len(encoded) > _MIMO_CLONE_MAX_B64:
            raise ValueError('音色克隆参考音频 Base64 超过 10MB 限制')
        return 'data:%s;base64,%s' % (mime, encoded)
    try:
        with open(path, 'rb') as file_obj:
            content = file_obj.read()
    except Exception as e:
        raise OSError('读取音色克隆参考音频失败: %s' % e) from e
    if not content:
        raise ValueError('音色克隆参考音频为空')
    mime = _cloneMime(path, content)
    encoded = base64.b64encode(content).decode('ascii')
    if len(encoded) > _MIMO_CLONE_MAX_B64:
        raise ValueError('音色克隆参考音频 Base64 超过 10MB 限制')
    return 'data:%s;base64,%s' % (mime, encoded)


def _mimoUserContent(mode, cfg, instructions, design_prompt):
    performance = str(instructions or '').strip()
    if mode == 'design':
        design = str(design_prompt or '').strip() or personaVoiceDesignPrompt()
        if performance:
            return '%s\n\n本次朗读指导：%s' % (design, performance)
        return design
    return performance


def _mimoPayload(status, cfg, content, instructions):
    mode = status.get('mimo_mode') or 'default'
    extra_body = cfg.get('extra_body', {})
    payload = dict(extra_body) if isinstance(extra_body, dict) else {}
    messages = []
    user_content = _mimoUserContent(mode, cfg, instructions, status.get('design_prompt', ''))
    if user_content or mode == 'design':
        messages.append({'role': 'user', 'content': user_content})
    messages.append({'role': 'assistant', 'content': content})
    audio = {'format': status.get('response_format') or 'wav'}
    if mode == 'default':
        audio['voice'] = status.get('voice') or '冰糖'
    elif mode == 'clone':
        audio['voice'] = _loadCloneVoice(cfg)
    elif mode == 'design':
        if status.get('optimize_text_preview') or cfg.get('optimize_text_preview'):
            audio['optimize_text_preview'] = True
        audio.pop('voice', None)
    else:
        raise ValueError('不支持的小米 MIMO 语音模式: %s' % mode)
    payload.update({
        'model': status['model'],
        'messages': messages,
        'audio': audio,
        'stream': False,
    })
    return payload


def synthesize(text, instructions=''):
    status = getStatus()
    if not status['enabled']:
        raise RuntimeError('语音模型未启用')
    if not status['ready']:
        if status['provider'] == _MIMO_PROVIDER and status.get('mimo_mode') == 'clone':
            raise RuntimeError('小米 MIMO 音色克隆需要配置 clone_audio (wav/mp3 路径或 data URL)')
        if status['provider'] == _MIMO_PROVIDER and status.get('mimo_mode') == 'design':
            raise RuntimeError('小米 MIMO 音色设计需要配置 design_prompt 或可用的人设文本')
        raise RuntimeError('语音模型的接口类型、api_url、model 或 voice 配置不完整')
    cfg = OlivaAIAgent.conf.get('voice', default={}) or {}
    max_chars = max(1, int(cfg.get('max_chars', 500)))
    content = str(text or '').strip()
    if not content:
        raise ValueError('语音文本不能为空')
    if len(content) > max_chars:
        raise ValueError('语音文本超过 %d 字限制' % max_chars)
    headers = {'Content-Type': 'application/json'}
    api_key = str(cfg.get('api_key', '')).strip()
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
        if status['provider'] == _MIMO_PROVIDER:
            headers['api-key'] = api_key
    extra_headers = cfg.get('extra_headers', {})
    if isinstance(extra_headers, dict):
        headers.update({str(key): str(value) for key, value in extra_headers.items()})
    if status['provider'] == _DASHSCOPE_PROVIDER:
        payload = _dashscopePayload(status, cfg, content, instructions)
    elif status['provider'] == _OPENAI_PROVIDER:
        payload = _openaiPayload(status, cfg, content)
    elif status['provider'] == _MIMO_PROVIDER:
        payload = _mimoPayload(status, cfg, content, instructions)
    else:
        raise ValueError('不支持的语音接口类型: %s' % status['provider'])
    timeout = max(1.0, float(cfg.get('timeout_sec', 120)))
    response = requests.post(status['api_url'], headers=headers, json=payload, timeout=timeout)
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError('语音接口 HTTP %s: %s' % (response.status_code, str(response.text)[:300]))
    audio_content, audio_format = _audioFromResponse(response, timeout)
    fallback_format = ''
    if status['provider'] in [_OPENAI_PROVIDER, _MIMO_PROVIDER]:
        fallback_format = status['response_format']
    return _saveAudio(audio_content, audio_format or fallback_format)


def _messageIds(result):
    if not isinstance(result, dict):
        return []
    data = result.get('data') if isinstance(result.get('data'), dict) else {}
    values = list(data.get('message_ids') or [])
    if data.get('message_id') not in [None, '', '-1', -1]:
        values.insert(0, data['message_id'])
    return list(dict.fromkeys(str(item) for item in values if item not in [None, '', '-1', -1]))


def sendVoice(ctx, text, instructions=''):
    plugin_event = ctx.get('plugin_event')
    if plugin_event is None:
        return {'error': '当前上下文没有可用的消息事件，无法发送语音'}
    bot_info = getattr(plugin_event, 'bot_info', None)
    bot_hash = bot_info.hash if bot_info is not None else 'unity'
    text = OlivaAIAgent.replyStyle.cleanReplyText(text)
    if not text:
        return {'active': False, 'data': {'error': '语音内容清洗后为空'}}
    source = OlivaAIAgent.contentSafety.match(text, outgoing=True, bot_hash=bot_hash)
    if source is not None:
        OlivaAIAgent.conf.traceLog(
            ctx.get('Proc'),
            'security.content.blocked',
            ctx.get('trace_id'),
            direction='output',
            scene='voice',
            source=source,
        )
        return {'active': False, 'data': {'error': '该内容不在可发送的话题范围内'}}
    claimed, text_key = _claimVoiceText(ctx, text)
    if not claimed:
        OlivaAIAgent.conf.traceLog(
            ctx.get('Proc'),
            'voice.send.duplicate',
            ctx.get('trace_id'),
            text_chars=len(str(text or '')),
        )
        return {
            'active': True,
            'data': {
                'duplicate_skipped': True,
                'message': '相同语音已在本轮处理，不再重复生成或发送',
                'text_chars': len(str(text or '')),
            },
            'error': '',
        }
    status = getStatus()
    OlivaAIAgent.conf.traceLog(
        ctx.get('Proc'),
        'voice.send.start',
        ctx.get('trace_id'),
        instruction_chars=len(str(instructions or '')),
        model=status.get('model', ''),
        text_chars=len(str(text or '')),
    )
    try:
        path = synthesize(text, instructions=instructions)
        message = OlivOS.messageAPI.Message_templet(
            'olivos_para',
            [OlivOS.messageAPI.PARA.record(file=os.path.abspath(path))],
        )
        with OlivaAIAgent.coreLogger.messageHint('[语音:%s]' % str(text).strip()):
            result = plugin_event.reply(message)
        active = not isinstance(result, dict) or bool(result.get('active'))
        message_ids = _messageIds(result)
        message_indexes = OlivaAIAgent.ambient._sendResultMessageIndexes(result)
        if active:
            _markVoiceSent(ctx)
            OlivaAIAgent.identifiers.recordOutgoing(
                plugin_event,
                '[语音:%s]' % str(text)[:200],
                message_ids,
                message_indexes=message_indexes,
            )
            try:
                if ctx.get('func_type') == 'group_message' and ctx.get('group_id') not in [None, '']:
                    OlivaAIAgent.ambient.addSelfReply(
                        ctx.get('platform', ''),
                        ctx['group_id'],
                        str(text).strip(),
                        message_ids=message_ids,
                        message_indexes=message_indexes,
                        message_type='voice',
                    )
                    OlivaAIAgent.ambient.saveUserSession(
                        plugin_event,
                        ctx.get('session_user_text', ''),
                        [{
                            'message': '[语音:%s]' % str(text).strip(),
                            'message_ids': message_ids,
                            'message_indexes': message_indexes,
                        }],
                        bot_hash=ctx.get('bot_hash', bot_hash),
                    )
            except Exception:
                pass
        actual_format = os.path.splitext(path)[1].lstrip('.').lower()
        return {
            'active': active,
            'data': {
                'message_ids': message_ids,
                'message_indexes': message_indexes,
                'instruction_chars': len(str(instructions or '')),
                'text_chars': len(str(text)),
                'format': actual_format,
                'message': '语音已发送，本轮不再发送文字回复',
            },
            'error': '' if active else '平台返回发送失败',
        }
    except Exception as e:
        _releaseVoiceText(ctx, text_key)
        return {'error': '语音生成或发送失败: %s: %s' % (type(e).__name__, e)}
