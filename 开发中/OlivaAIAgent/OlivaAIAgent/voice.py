# -*- encoding: utf-8 -*-
'''OpenAI-compatible 语音合成与 OlivOS 语音消息发送。'''

import base64
import hashlib
import os
import re
import time

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


def outputDir():
    path = os.path.join(OlivaAIAgent.conf.dataPath, 'voice')
    OlivaAIAgent.conf.releaseDir(path)
    return path


def getStatus():
    cfg = OlivaAIAgent.conf.get('voice', default={}) or {}
    enabled = bool(cfg.get('enabled', False))
    api_url = str(cfg.get('api_url', '')).strip()
    model = str(cfg.get('model', '')).strip()
    return {
        'enabled': enabled,
        'ready': enabled and bool(api_url and model),
        'api_url': api_url,
        'model': model,
        'voice': str(cfg.get('voice', '')).strip(),
        'response_format': str(cfg.get('response_format', 'mp3')).strip().lower(),
    }


def _cleanOldFiles():
    max_files = max(1, int(OlivaAIAgent.conf.get('voice', 'max_files', default=100)))
    try:
        entries = [
            os.path.join(outputDir(), name)
            for name in os.listdir(outputDir())
            if os.path.isfile(os.path.join(outputDir(), name))
        ]
        entries.sort(key=lambda path: os.path.getmtime(path), reverse=True)
        for path in entries[max_files:]:
            try:
                os.remove(path)
            except Exception:
                pass
    except Exception:
        pass


def _saveAudio(content, response_format):
    if not isinstance(content, bytes) or not content:
        raise ValueError('语音接口没有返回音频数据')
    max_bytes = max(1024, int(OlivaAIAgent.conf.get('voice', 'max_bytes', default=15 * 1024 * 1024)))
    if len(content) > max_bytes:
        raise ValueError('语音文件超过大小限制（%d 字节）' % max_bytes)
    fmt = str(response_format or 'mp3').lower()
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
                return 'url', item
        for key in ('b64_json', 'base64', 'audio', 'data'):
            item = value.get(key)
            if isinstance(item, str):
                if item.startswith(('http://', 'https://')):
                    return 'url', item
                content = _decodeBase64(item)
                if content:
                    return 'bytes', content
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


def _audioFromResponse(response, timeout):
    content_type = str(response.headers.get('Content-Type', '')).lower()
    if content_type.startswith('audio/') or 'application/octet-stream' in content_type:
        return response.content
    try:
        data = response.json()
    except Exception as e:
        raise ValueError('语音接口返回的不是音频或有效 JSON') from e
    found = _findAudioValue(data)
    if not found:
        raise ValueError('语音接口 JSON 中没有可用的音频 URL 或 Base64')
    kind, value = found
    if kind == 'bytes':
        return value
    download = requests.get(value, timeout=timeout)
    download.raise_for_status()
    return download.content


def synthesize(text):
    status = getStatus()
    if not status['enabled']:
        raise RuntimeError('语音模型未启用')
    if not status['ready']:
        raise RuntimeError('语音模型缺少 api_url 或 model')
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
    extra_headers = cfg.get('extra_headers', {})
    if isinstance(extra_headers, dict):
        headers.update({str(key): str(value) for key, value in extra_headers.items()})
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
    timeout = max(1.0, float(cfg.get('timeout_sec', 120)))
    response = requests.post(status['api_url'], headers=headers, json=payload, timeout=timeout)
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError('语音接口 HTTP %s: %s' % (response.status_code, str(response.text)[:300]))
    return _saveAudio(_audioFromResponse(response, timeout), status['response_format'])


def _messageIds(result):
    if not isinstance(result, dict):
        return []
    data = result.get('data') if isinstance(result.get('data'), dict) else {}
    values = list(data.get('message_ids') or [])
    if data.get('message_id') not in [None, '', '-1', -1]:
        values.insert(0, data['message_id'])
    return list(dict.fromkeys(str(item) for item in values if item not in [None, '', '-1', -1]))


def sendVoice(ctx, text):
    plugin_event = ctx.get('plugin_event')
    if plugin_event is None:
        return {'error': '当前上下文没有可用的消息事件，无法发送语音'}
    status = getStatus()
    OlivaAIAgent.conf.traceLog(
        ctx.get('Proc'),
        'voice.send.start',
        ctx.get('trace_id'),
        model=status.get('model', ''),
        text_chars=len(str(text or '')),
    )
    try:
        path = synthesize(text)
        message = OlivOS.messageAPI.Message_templet(
            'olivos_para',
            [OlivOS.messageAPI.PARA.record(file=os.path.abspath(path))],
        )
        result = plugin_event.reply(message)
        active = not isinstance(result, dict) or bool(result.get('active'))
        message_ids = _messageIds(result)
        if active:
            OlivaAIAgent.identifiers.recordOutgoing(
                plugin_event,
                '[语音消息:%s]' % str(text)[:200],
                message_ids,
            )
        return {
            'active': active,
            'data': {
                'message_ids': message_ids,
                'text_chars': len(str(text)),
                'format': status.get('response_format', ''),
            },
            'error': '' if active else '平台返回发送失败',
        }
    except Exception as e:
        return {'error': '语音生成或发送失败: %s: %s' % (type(e).__name__, e)}
