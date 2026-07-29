# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 视觉/图片子系统（移植并增强自刺客）
- OCR/视觉识别: 把消息中的 [CQ/OP:image] / mface 原位转成 [图片:识图结果]
- 图片缓存: 按群保留最近若干张图（内容/意图/类型），供 AI 引用与"发表情包"
- 表情包主动发送: AI 输出 [发图片:关键词] → 模糊匹配缓存里的真实图片文件发出
- 视觉否认纠偏: 已有有效摘要时若模型说"看不到图"，自动纠正
- 支持独立视觉后端(ocr_api)或复用主后端(vision=true)
'''

import base64
import hashlib
import json
import os
import re
import threading
import time
from collections import deque
from difflib import SequenceMatcher

import requests

import OlivaAIAgent

OP_IMAGE_PATTERN = re.compile(r'\[(?:CQ|OP):image,[^\]]+\]')
MFACE_PATTERN = re.compile(r'\[(?:CQ|OP):mface,[^\]]*\]')
IMAGE_CODE_PATTERN = re.compile(r'\[图片[:：][^\]]*\]')
IMAGE_PLACEHOLDER_PATTERN = re.compile(r'\[\[OLIVA_IMAGE_([0-9]+)\]\]')
VISION_DENIAL_PATTERN = re.compile(
    r'(看不到|看不见|无法(查看|识别|看到|读取)|不能识图|不会识图|没有图片|图片打不开|发不了图|还没.*识图)')

# group_id -> deque[(file_name, data_dict)]
_imageCache = {}
# 保护 _imageCache 的跨线程读写（派发线程写入 vs 潜行工作线程迭代）。
# 对 knowledge 记忆里的“图片缓存”子字典则统一用 knowledge._lock 保护。
_cache_lock = threading.RLock()
_ingesting = set()          # 正在后台识别的 (bot_hash, file_name)，避免重复排队
_ingest_lock = threading.Lock()


def imgDir():
    d = OlivaAIAgent.conf.dataPath + '/Image'
    OlivaAIAgent.conf.releaseDir(d)
    return d


def imgcode_format(data=None):
    content = '未识别成功'
    if isinstance(data, dict):
        content = str(data.get('content') or content)
    content = re.sub(r'[\r\n]+', ' ', content).replace(']', '】').strip()[:160]
    return '[图片:%s]' % (content or '未识别成功')


def imagePlaceholder(index):
    return '[[OLIVA_IMAGE_%d]]' % int(index)


def placeImageFacts(message, facts):
    '''按消息段顺序把识图结果放回图片原位；无占位符时兼容旧路径追加到末尾。'''
    text = str(message)
    fact_list = [str(item) for item in (facts or []) if str(item).strip()]
    had_placeholder = IMAGE_PLACEHOLDER_PATTERN.search(text) is not None

    def repl(match):
        index = int(match.group(1))
        return fact_list[index] if index < len(fact_list) else '[图片]'

    text = IMAGE_PLACEHOLDER_PATTERN.sub(repl, text)
    if not had_placeholder and fact_list and not any(fact in text for fact in fact_list):
        text = (text + ' ' + ' '.join(fact_list)).strip()
    return text


def _parseParams(tag):
    inner = tag[tag.find(',') + 1:-1] if ',' in tag else ''
    params = {}
    for part in inner.split(','):
        if '=' in part:
            k, v = part.split('=', 1)
            params[k] = v
    return params


def _basicData(message_text, image_type='图片', summary=None):
    content = summary if summary else '未识别成功'
    return {'content': str(content)[:32], 'intent': '不明', 'type': image_type}


def _mainVisionCapable():
    '''主后端是否声明支持视觉(该后端配置里的 vision 开关)。'''
    try:
        return bool(OlivaAIAgent.aiClient.getBackendConf().get('vision', False))
    except Exception:
        return False


def _visionConf():
    '''返回视觉识别配置: {api_url, api_key, model, mode, wire}，未启用返回 None。
    use_main: "auto"(默认)=主后端支持视觉就直接用主模型识图，不支持就用下面单独配的 OCR 模型；
    也可显式写 true / false 强制。'''
    oc = OlivaAIAgent.conf.get('vision', default={}) or {}
    if not oc.get('enable', False):
        return None
    use_main = oc.get('use_main', 'auto')
    if use_main == 'auto' or use_main is None:
        use_main = _mainVisionCapable()   # 主模型支持视觉→走主；否则→走独立 OCR
    if use_main:
        bc = OlivaAIAgent.aiClient.getBackendConf()
        return {'api_url': bc.get('api_url', ''), 'api_key': bc.get('api_key', ''),
                'model': bc.get('model', ''), 'mode': oc.get('mode', 'url'), 'wire': bc.get('wire', 'openai')}
    return {'api_url': oc.get('api_url', ''), 'api_key': oc.get('api_key', ''),
            'model': oc.get('model', ''), 'mode': oc.get('mode', 'base64'), 'wire': 'openai'}


def getVisionStatus():
    '''返回不含密钥的视觉路由状态，供初始化日志和诊断使用。'''
    vc = _visionConf()
    if vc is None:
        return {'enabled': False, 'ready': False, 'route': 'disabled', 'model': '', 'mode': ''}
    route = 'main' if _mainVisionCapable() and (
        OlivaAIAgent.conf.get('vision', 'use_main', default='auto') in ('auto', None, True)
    ) else 'independent'
    return {
        'enabled': True,
        'ready': bool(vc.get('api_url') and vc.get('api_key') and vc.get('model')),
        'route': route,
        'model': str(vc.get('model', '')),
        'mode': str(vc.get('mode', 'base64')),
        'wire': str(vc.get('wire', 'openai')),
    }


_ILLEGAL_FN = re.compile(r'[^0-9A-Za-z._-]')
_MIME_BY_EXT = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp'}
_EXT_BY_MIME = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif',
                'image/webp': '.webp', 'image/bmp': '.bmp'}
_VALID_EXT = set(_MIME_BY_EXT)
_STABLE_IMAGE_NAME = re.compile(r'^img_[0-9a-f]{20}\.(?:jpg|jpeg|png|gif|webp|bmp)$')
_VOLATILE_URL_PARAMS = {
    'authkey', 'expire', 'expires', 'rkey', 'sig', 'signature', 'token',
    'ts', 'timestamp',
}


def _looksLikeImage(b):
    '''魔数兜底：官机 CDN 可能不返回 image/* content-type，但内容确是图片。'''
    if not b or len(b) < 12:
        return False
    return (b[:3] == b'\xff\xd8\xff' or b[:8] == b'\x89PNG\r\n\x1a\n'
            or b[:6] in (b'GIF87a', b'GIF89a') or b[:2] == b'BM'
            or (b[:4] == b'RIFF' and b[8:12] == b'WEBP'))


def _mimeFromBytes(content):
    if not content:
        return ''
    if content[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if content[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if content[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if content[:2] == b'BM':
        return 'image/bmp'
    if len(content) >= 12 and content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'image/webp'
    return ''


def _sourceId(file_name, image_url=None):
    '''生成不含短期鉴权参数的来源指纹，供重启后定位同一张远程图片。'''
    source = str(image_url or file_name or '').strip()
    try:
        if source.startswith(('http://', 'https://')):
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

            parts = urlsplit(source)
            query = sorted([
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if key.lower() not in _VOLATILE_URL_PARAMS
            ])
            source = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ''))
    except Exception:
        pass
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def _stableImageName(content, content_type='', fallback_name=''):
    mime = _mimeFromBytes(content)
    if not mime:
        mime = (content_type or '').split(';')[0].strip().lower()
        if mime == 'image/jpg':
            mime = 'image/jpeg'
    ext = _EXT_BY_MIME.get(mime)
    if ext is None:
        fallback_ext = os.path.splitext(_safeImageName(fallback_name))[1].lower()
        ext = fallback_ext if fallback_ext in _VALID_EXT else '.jpg'
    digest = hashlib.sha256(content).hexdigest()[:20]
    return 'img_%s%s' % (digest, ext)


def _isStableImageName(file_name):
    return bool(_STABLE_IMAGE_NAME.fullmatch(str(file_name or '')))


def _imageFileExists(file_name):
    if not _isStableImageName(file_name):
        return False
    directory = os.path.abspath(imgDir())
    path = os.path.abspath(os.path.join(directory, str(file_name)))
    return path.startswith(directory + os.sep) and os.path.isfile(path)


def _publicImageData(data):
    if not isinstance(data, dict):
        return data
    return {key: value for key, value in data.items() if not str(key).startswith('_')}


def _dataSourceIds(data):
    if not isinstance(data, dict):
        return set()
    result = {str(item) for item in data.get('_source_ids', []) if str(item)} \
        if isinstance(data.get('_source_ids'), list) else set()
    if data.get('_source_id'):
        result.add(str(data['_source_id']))
    return result


def _safeImageName(file_name, content_type=''):
    '''从 file/url 生成【合法】本地文件名：取 basename、去查询串、非法字符替换、限长、补扩展名。
    官机图片 URL 形如 .../download?appid=1407&fileid=...&rkey=... ，直接当文件名会因含 ?&= 且超长而存盘报错。'''
    name = str(file_name or '').replace('\\', '/').split('/')[-1]
    name = name.split('?', 1)[0].split('#', 1)[0]        # 去查询串/锚点
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in _VALID_EXT:
        ct = (content_type or '').split(';')[0].strip().lower()
        ext = _EXT_BY_MIME.get(ct, '.jpg')
    stem = _ILLEGAL_FN.sub('_', stem).strip('._')[:80]
    if not stem:
        stem = 'img_%d' % int(time.time())
    return stem + ext


def _mimeOf(name, content_type=''):
    m = _MIME_BY_EXT.get(os.path.splitext(name)[1].lower())
    if m:
        return m
    ct = (content_type or '').split(';')[0].strip().lower()
    return ct if ct.startswith('image/') else 'image/jpeg'


def _downloadBase64(url, file_name, trace_id=None):
    '''下载图片 → base64 data URL。存盘失败【不影响】base64（存盘仅为“发表情包”复用）。
    返回 (data_url_or_None, local_path_or_None)。'''
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.download.start',
        trace_id,
        file=_safeImageName(file_name),
    )
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        content = r.content
    except Exception as e:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.download.failed',
            trace_id,
            error='%s: %s' % (type(e).__name__, e),
        )
        return None, None
    ctype = r.headers.get('Content-Type', '')
    detected_mime = _mimeFromBytes(content)
    header_mime = ctype.split(';')[0].strip().lower()
    if header_mime == 'image/jpg':
        header_mime = 'image/jpeg'
    actual_mime = detected_mime or (header_mime if header_mime in _EXT_BY_MIME else '')
    if not actual_mime:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.download.failed',
            trace_id,
            bytes=len(content),
            content_type=ctype or 'missing',
            reason='not_image',
        )
        return None, None
    safe = _stableImageName(content, actual_mime, file_name)
    b = base64.b64encode(content).decode('utf-8')
    data_url = 'data:%s;base64,%s' % (actual_mime, b)
    # 存盘=最佳努力：文件名/磁盘问题绝不能让识别失败（官机 URL 曾因此报 SAVE ERR 并回退发原始URL致400）
    path = None
    try:
        p = os.path.join(imgDir(), safe)
        if not os.path.exists(p):
            with open(p, 'wb') as f:
                f.write(content)
        path = p
    except Exception as e:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.file_save.failed',
            trace_id,
            error='%s: %s' % (type(e).__name__, e),
        )
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.download',
        trace_id,
        bytes=len(content),
        content_type=ctype or _mimeOf(safe),
        file=safe,
        saved=path is not None,
    )
    return data_url, path


_OCR_PROMPT = '''# 任务：识别图片并输出严格 JSON
- content: 尽量完整描述图片内容(≤160字,单行)，保留人物/物体/动作/环境/可见文字/选项
- intent: 图片可能表达的意图(≤32字)
- type: 类型，优先从"表情包、梗图、截图、照片、插画、普通图片"中选
- 只输出 {"content":"...","intent":"...","type":"..."}，无 Markdown 无解释'''


def _callOcr(vc, image_url, trace_id=None):
    started = time.perf_counter()
    try:
        url = vc['api_url'].rstrip('/')
        if not url.endswith('/chat/completions'):
            url = url + '/chat/completions'
        headers = {'Content-Type': 'application/json'}
        if vc.get('api_key'):
            headers['Authorization'] = 'Bearer ' + str(vc['api_key'])
        payload = {
            'model': vc['model'],
            'messages': [
                {'role': 'system', 'content': _OCR_PROMPT},
                {'role': 'user', 'content': [
                    {'type': 'text', 'text': '识别这张图片并按要求输出 JSON。'},
                    {'type': 'image_url', 'image_url': {'url': image_url}},
                ]},
            ],
            'max_tokens': 2048, 'stream': False,
            'response_format': {'type': 'json_object'},
        }
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.ocr.request',
            trace_id,
            image_chars=len(str(image_url)),
            mode=vc.get('mode', 'base64'),
            model=vc.get('model', ''),
            wire=vc.get('wire', 'openai'),
        )
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'vision.ocr.result',
                trace_id,
                body=str(r.text)[:300],
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                result='失败',
                status=r.status_code,
            )
            return None
        content = r.json()['choices'][0]['message']['content'].strip()
        obj = json.loads(content)
        if isinstance(obj, dict) and all(isinstance(obj.get(k), str) and obj.get(k).strip()
                                         for k in ('content', 'intent', 'type')):
            result = {'content': obj['content'].strip()[:160], 'intent': obj['intent'].strip()[:32],
                      'type': obj['type'].strip()[:32]}
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'vision.ocr.result',
                trace_id,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                result='成功',
                type=result['type'],
            )
            return result
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.ocr.result',
            trace_id,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            reason='invalid_response',
            result='失败',
        )
    except Exception as e:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.ocr.result',
            trace_id,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            error='%s: %s' % (type(e).__name__, e),
            result='失败',
        )
    return None


def _cachedOnly(bot_hash, file_name, image_url=None):
    '''只读缓存（持锁快照），返回 (memory键, 数据, 来源指纹)。'''
    source_id = _sourceId(file_name, image_url)
    klock = OlivaAIAgent.knowledge._lock
    with klock:
        gc = OlivaAIAgent.knowledge.getMem(bot_hash)['全局'].get('图片缓存', {})
        snap = dict(gc) if isinstance(gc, dict) else {}
    for candidate in (str(file_name or ''), str(image_url or '')):
        value = snap.get(candidate)
        if isinstance(value, dict):
            return candidate, dict(value), source_id
    for key, value in reversed(list(snap.items())):
        if isinstance(value, dict) and source_id in _dataSourceIds(value):
            return str(key), dict(value), source_id
    return None, None, source_id


def _storeOcr(bot_hash, file_name, data, trace_id=None, source_id=None, old_keys=None):
    '''把 OCR 结果写入持久图片缓存（持 knowledge._lock，与 saveMem 一致）。'''
    if not _isStableImageName(file_name):
        raise ValueError('图片缓存键不是稳定的本地文件名: %s' % _safeImageName(file_name))
    stored_data = dict(data)
    klock = OlivaAIAgent.knowledge._lock
    with klock:
        mem = OlivaAIAgent.knowledge.getMem(bot_hash)
        global_cache = mem['全局'].setdefault('图片缓存', {})
        source_ids = _dataSourceIds(global_cache.get(file_name)) | _dataSourceIds(stored_data)
        if source_id:
            source_ids.add(str(source_id))
        stored_data.pop('_source_id', None)
        if source_ids:
            stored_data['_source_ids'] = sorted(source_ids)
        for old_key in old_keys or ():
            if old_key != file_name:
                global_cache.pop(old_key, None)
        global_cache.pop(file_name, None)
        global_cache[file_name] = stored_data
        cap = int(OlivaAIAgent.conf.get('vision', 'persist_cache_max', default=300))
        if cap > 0 and len(global_cache) > cap:
            for k in list(global_cache)[:len(global_cache) - cap]:
                global_cache.pop(k, None)
    try:
        OlivaAIAgent.knowledge.saveMem(bot_hash)
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.cache.persisted',
            trace_id,
            file=_safeImageName(file_name),
        )
    except Exception as e:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.cache.persist_failed',
            trace_id,
            error='%s: %s' % (type(e).__name__, e),
        )


def _isUnfetchableUrl(url):
    '''官机/QQ 内部/签名 URL：第三方识图模型多半取不到（会 400 unsupported image url），需本地下成 base64。'''
    u = str(url or '').lower()
    return ('multimedia.nt.qq' in u or 'rkey=' in u or 'gchat.qpic' in u
            or 'download?appid' in u or 'multimedia.nt.qq.com' in u or 'qpic.cn' in u)


def _runOcr(file_name, image_url, trace_id=None):
    '''执行一次下载和 OCR，返回 (data或None, 实际本地文件名或None)。'''
    vc = _visionConf()
    if not (vc and image_url and vc.get('api_key') and vc.get('model')):
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.ocr.skipped',
            trace_id,
            has_image_url=bool(image_url),
            reason='vision_disabled_or_incomplete',
        )
        return None, None
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.route',
        trace_id,
        file=_safeImageName(file_name),
        mode=vc.get('mode', 'base64'),
        model=vc.get('model', ''),
    )
    # 无论识图后端用 URL 还是 base64，都先落盘一次，保证 memory 中的文件名重启后仍可发送。
    b64, local_path = _downloadBase64(image_url, file_name, trace_id=trace_id)
    if not b64 or not local_path:
        # 关键：下载/转码失败时不回退官机签名 URL，避免第三方模型返回 400。
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.ocr.skipped',
            trace_id,
            reason='download_or_transcode_failed',
        )
        return None, None
    image_input = b64 if vc.get('mode', 'base64') == 'base64' or _isUnfetchableUrl(image_url) else image_url
    return _callOcr(vc, image_input, trace_id=trace_id), os.path.basename(local_path)


def _pushGroupCache(group_id, file_name, data):
    qsize = int(OlivaAIAgent.conf.get('vision', 'queue_size', default=8))
    with _cache_lock:
        q = _imageCache.get(group_id)
        if q is None or q.maxlen != qsize:
            newq = deque(q or (), maxlen=qsize)
            _imageCache[group_id] = newq
            q = newq
        kept = [item for item in q if not (isinstance(item, tuple) and item and item[0] == file_name)]
        q = deque(kept, maxlen=qsize)
        q.append((file_name, data))
        _imageCache[group_id] = q


def _bgIngest(bot_hash, group_id, file_name, image_url, trace_id=None, cached_key=None, cached_data=None):
    source_id = _sourceId(file_name, image_url)
    key = (str(bot_hash), source_id)
    with _ingest_lock:
        if key in _ingesting:
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'vision.background.duplicate',
                trace_id,
                file=_safeImageName(file_name),
            )
            return
        _ingesting.add(key)

    def _work():
        try:
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'vision.background.start',
                trace_id,
                file=_safeImageName(file_name),
            )
            if cached_data is not None:
                _, local_path = _downloadBase64(image_url, file_name, trace_id=trace_id)
                data = dict(cached_data)
                local_name = os.path.basename(local_path) if local_path else None
            else:
                data, local_name = _runOcr(file_name, image_url, trace_id=trace_id)
            if data is not None and local_name is not None:
                _storeOcr(
                    bot_hash,
                    local_name,
                    data,
                    trace_id=trace_id,
                    source_id=source_id,
                    old_keys=[cached_key] if cached_key else None,
                )
                _pushGroupCache(group_id, local_name, data)
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'vision.background.done',
                trace_id,
                success=data is not None,
            )
        except Exception as e:
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'vision.background.exception',
                trace_id,
                error='%s: %s' % (type(e).__name__, e),
            )
        finally:
            with _ingest_lock:
                _ingesting.discard(key)
    threading.Thread(target=_work, daemon=True).start()


def _cacheData(bot_hash, group_id, file_name, image_url, message_text, image_type, summary=None, allow_network=True,
               trace_id=None):
    '''把一张图片转成事实摘要并入群缓存。
    allow_network=False 时不在本线程做下载/OCR（避免阻塞消息总线），改为后台识别、本次先用占位摘要。'''
    cache_key, data, source_id = _cachedOnly(bot_hash, file_name, image_url)
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.cache.lookup',
        trace_id,
        allow_network=allow_network,
        file=_safeImageName(cache_key or file_name),
        hit=data is not None,
    )
    local_name = None
    if data is not None and _imageFileExists(cache_key) and source_id in _dataSourceIds(data):
        local_name = cache_key
    if data is not None and local_name is None and image_url:
        if allow_network:
            _, local_path = _downloadBase64(image_url, file_name, trace_id=trace_id)
            local_name = os.path.basename(local_path) if local_path else None
            if local_name:
                _storeOcr(
                    bot_hash,
                    local_name,
                    data,
                    trace_id=trace_id,
                    source_id=source_id,
                    old_keys=[cache_key] if cache_key else None,
                )
        elif _visionConf():
            _bgIngest(
                bot_hash,
                group_id,
                file_name,
                image_url,
                trace_id=trace_id,
                cached_key=cache_key,
                cached_data=data,
            )
    if data is None and allow_network:
        data, local_name = _runOcr(file_name, image_url, trace_id=trace_id)
        if data is not None and local_name is not None:
            _storeOcr(bot_hash, local_name, data, trace_id=trace_id, source_id=source_id)
    if data is None:
        # 缓存未命中：非阻塞模式下后台识别，供后续引用；本次先返回占位
        if not allow_network and image_url and _visionConf():
            _bgIngest(bot_hash, group_id, file_name, image_url, trace_id=trace_id)
        data = _basicData(message_text, image_type=image_type, summary=summary)
    runtime_name = local_name or ('img_%s.jpg' % source_id[:20])
    _pushGroupCache(group_id, runtime_name, data)
    return imgcode_format(data)


def translateIncoming(message, group_id, bot_hash, allow_network=True, trace_id=None):
    '''把消息里的 image/mface 标签替换为事实摘要。无图直接返回原文。
    allow_network=False：不在本线程做下载/OCR（保护消息总线不被阻塞），未命中的图后台识别。'''
    res = str(message)
    if '[OP:image' not in res and '[CQ:image' not in res and ':mface,' not in res:
        return res
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.translate.start',
        trace_id,
        allow_network=allow_network,
        group_id=group_id,
    )

    def proc_image(m):
        original = m.group(0)
        params = _parseParams(original)
        fn = params.get('file') or params.get('url')
        if not fn:
            return imgcode_format()
        image_url = params.get('url') or (fn if str(fn).startswith(('http://', 'https://')) else None)
        return _cacheData(
            bot_hash,
            group_id,
            fn,
            image_url,
            original,
            '图片',
            allow_network=allow_network,
            trace_id=trace_id,
        )

    def proc_mface(m):
        original = m.group(0)
        params = _parseParams(original)
        fn = params.get('file') or params.get('emoji_id') or ('mface_%d' % int(time.time()))
        summary = params.get('summary')
        image_url = params.get('url') or (fn if str(fn).startswith(('http://', 'https://')) else None)
        return _cacheData(bot_hash, group_id, fn, image_url, summary or original, '表情包',
                          summary=summary, allow_network=allow_network, trace_id=trace_id)

    res = OP_IMAGE_PATTERN.sub(proc_image, res)
    res = MFACE_PATTERN.sub(proc_mface, res)
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.translate.done',
        trace_id,
        facts=len(IMAGE_CODE_PATTERN.findall(res)),
    )
    return res


def describeImages(image_urls, group_id, bot_hash, trace_id=None):
    '''识别已解析出的图片 URL；用于消息字符串未保留 CQ/OP 标签的兼容路径。'''
    facts = []
    for image_url in list(image_urls or [])[:4]:
        url_text = str(image_url)
        fact = _cacheData(
            bot_hash,
            group_id,
            url_text,
            url_text,
            '[远程图片]',
            '图片',
            allow_network=True,
            trace_id=trace_id,
        )
        facts.append(fact)
    return facts


def ensureImageFacts(codes, image_urls, group_id, bot_hash, trace_id=None):
    '''补全图片摘要，但同一流程已经识别失败时不重复请求。'''
    facts = [str(item) for item in (codes or []) if str(item).strip()]
    images = list(dict.fromkeys(str(item) for item in (image_urls or []) if str(item).strip()))[:4]
    if not images:
        return facts
    if facts:
        if all('未识别成功' in fact for fact in facts):
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'vision.ocr.repeat_skipped',
                trace_id,
                images=len(images),
                reason='本轮已识别失败',
            )
        return facts
    return describeImages(images, group_id, bot_hash, trace_id=trace_id)


def imageCacheMap(bot_hash):
    res = {}
    if bot_hash is not None:
        # 持锁快照，避免派发线程并发写入时 "dict changed size during iteration"
        with OlivaAIAgent.knowledge._lock:
            gc = OlivaAIAgent.knowledge.getMem(bot_hash)['全局'].get('图片缓存', {})
            snap = dict(gc) if isinstance(gc, dict) else {}
        for k, v in snap.items():
            if isinstance(v, dict) and _imageFileExists(str(k)):
                res[str(k)] = v
    with _cache_lock:
        snap_q = [list(q) for q in _imageCache.values()]
    for q in snap_q:
        for item in q:
            if (isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], dict)
                    and _imageFileExists(str(item[0]))):
                res[str(item[0])] = item[1]
    return res


def groupImageCacheDict(group_id):
    res = {}
    with _cache_lock:
        items = list(_imageCache.get(group_id, []))
    for item in items:
        if isinstance(item, tuple) and len(item) >= 2:
            res[str(item[0])] = _publicImageData(item[1])
    return res


def isEmojiData(d):
    if not isinstance(d, dict):
        return False
    target = '%s %s %s' % (d.get('type', ''), d.get('intent', ''), d.get('content', ''))
    return any(x in target for x in ('表情包', '梗图', 'mface', '表情', 'emoji'))


def resolveImageRef(image_ref, cache_map, trace_id=None):
    '''按刺客的字段权重和模糊评分，把图片引用解析为缓存中的真实文件名。'''
    image_ref = str(image_ref).strip()
    if image_ref in cache_map:
        _logImageMatch(image_ref, image_ref, 1000, trace_id)
        return image_ref
    fixed_name = _normalizeImageFileNameRef(image_ref, cache_map)
    if fixed_name is not None:
        _logImageMatch(image_ref, fixed_name, 900, trace_id)
        return fixed_name
    normalized_ref = _normalizeImageLookupText(image_ref)
    if not normalized_ref:
        _logImageMiss(image_ref, '引用内容为空', trace_id)
        return None
    requested_ext = _getImageRefExt(image_ref)
    candidates = []
    for file_name, image_data in cache_map.items():
        if not isinstance(image_data, dict):
            continue
        score = _scoreImageLookup(normalized_ref, image_ref, requested_ext, file_name, image_data)
        if score > 0:
            candidates.append((score, file_name))
    if not candidates:
        _logImageMiss(image_ref, '没有候选图片', trace_id)
        return None
    candidates.sort(reverse=True)
    best_score, best_file_name = candidates[0]
    if best_score < 100:
        _logImageMiss(image_ref, '最高评分不足', trace_id, score=best_score)
        return None
    if len(candidates) >= 2 and candidates[1][0] == best_score:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.send.ambiguous',
            trace_id,
            candidate=_safeImageName(best_file_name),
            reference=image_ref,
            score=best_score,
            second_candidate=_safeImageName(candidates[1][1]),
        )
    _logImageMatch(image_ref, best_file_name, best_score, trace_id)
    return best_file_name


def _logImageMatch(image_ref, file_name, score, trace_id=None):
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.send.match',
        trace_id,
        file=_safeImageName(file_name),
        reference=image_ref,
        score=score,
    )


def _logImageMiss(image_ref, reason, trace_id=None, score=None):
    fields = {'reference': image_ref, 'reason': reason}
    if score is not None:
        fields['score'] = score
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.send.not_matched',
        trace_id,
        **fields,
    )


def _normalizeImageFileNameRef(image_ref, cache_map):
    if not isinstance(image_ref, str):
        return None
    image_ref = image_ref.strip()
    fixed_ref = re.sub(r'(\.[a-z0-9]{2,5})\1$', r'\1', image_ref, flags=re.IGNORECASE)
    if fixed_ref in cache_map:
        return fixed_ref
    ref_stem = os.path.splitext(fixed_ref)[0].lower()
    if not ref_stem:
        return None
    candidates = [
        file_name
        for file_name in cache_map
        if os.path.splitext(file_name)[0].lower() == ref_stem
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        requested_ext = _getImageRefExt(fixed_ref)
        for file_name in candidates:
            if os.path.splitext(file_name)[1].lower().lstrip('.') == requested_ext:
                return file_name
    return None


def _scoreImageLookup(normalized_ref, image_ref, requested_ext, file_name, image_data):
    score = 0
    normalized_file_name = _normalizeImageLookupText(file_name)
    if normalized_ref == normalized_file_name:
        score = max(score, 300)
    elif normalized_ref in normalized_file_name or normalized_file_name in normalized_ref:
        score = max(score, 180)
    else:
        score = max(score, _scoreFuzzyImageText(normalized_ref, normalized_file_name, 180))
    for key, value_score in (('content', 160), ('intent', 120), ('type', 80)):
        value = image_data.get(key, '')
        if not isinstance(value, str):
            continue
        normalized_value = _normalizeImageLookupText(value)
        if not normalized_value:
            continue
        if normalized_ref == normalized_value:
            score = max(score, value_score + 80)
        elif normalized_ref in normalized_value or normalized_value in normalized_ref:
            score = max(score, value_score)
        else:
            score = max(score, _scoreFuzzyImageText(normalized_ref, normalized_value, value_score))
    file_stem = os.path.splitext(file_name)[0].lower()
    ref_stem = os.path.splitext(image_ref.strip())[0].lower()
    if ref_stem and file_stem == ref_stem:
        score += 90
    file_ext = os.path.splitext(file_name)[1].lower().lstrip('.')
    if requested_ext and file_ext == requested_ext:
        score += 60
    elif file_ext == 'gif':
        score += 20
    return score


def _scoreFuzzyImageText(normalized_ref, normalized_value, max_score):
    if not normalized_ref or not normalized_value:
        return 0
    min_len = min(len(normalized_ref), len(normalized_value))
    max_len = max(len(normalized_ref), len(normalized_value))
    if min_len < 2:
        return 0
    if min_len / max_len < _imageFuzzyLengthRateLimit(min_len):
        return 0
    if min_len == 2 and max_len <= 3:
        same_position_count = sum(
            1 for ref_char, value_char in zip(normalized_ref, normalized_value) if ref_char == value_char
        )
        if same_position_count >= 1:
            return int(max_score * 0.75)
    ratio = SequenceMatcher(None, normalized_ref, normalized_value).ratio()
    long_text_score = _scoreLongFuzzyImageText(normalized_ref, normalized_value, max_score)
    if ratio < _imageFuzzyRatioThreshold(min_len):
        return long_text_score
    return max(int(max_score * ratio), long_text_score)


def _imageFuzzyLengthRateLimit(min_len):
    if min_len >= 16:
        return 0.25
    if min_len >= 10:
        return 0.32
    if min_len >= 6:
        return 0.40
    return 0.45


def _imageFuzzyRatioThreshold(min_len):
    if min_len >= 24:
        return 0.48
    if min_len >= 16:
        return 0.54
    if min_len >= 10:
        return 0.60
    if min_len >= 6:
        return 0.68
    return 0.74


def _scoreLongFuzzyImageText(normalized_ref, normalized_value, max_score):
    min_len = min(len(normalized_ref), len(normalized_value))
    if min_len < 8:
        return 0
    ref_chunks = _imageTextChunks(normalized_ref)
    value_chunks = _imageTextChunks(normalized_value)
    if not ref_chunks or not value_chunks:
        return 0
    common_chunks = ref_chunks & value_chunks
    if len(common_chunks) < 3:
        return 0
    chunk_cover = len(common_chunks) / min(len(ref_chunks), len(value_chunks))
    ref_chunk_cover = len(common_chunks) / len(ref_chunks)
    ref_chars = set(normalized_ref)
    value_chars = set(normalized_value)
    char_cover = len(ref_chars & value_chars) / min(len(ref_chars), len(value_chars))
    if chunk_cover < 0.18 and char_cover < 0.50:
        return 0
    score_rate = 0.46 + chunk_cover * 0.35 + ref_chunk_cover * 0.12 + char_cover * 0.12
    if min_len >= 16:
        score_rate += 0.05
    if min_len >= 24:
        score_rate += 0.04
    return int(max_score * min(score_rate, 0.95))


def _imageTextChunks(text):
    return {text[index:index + 2] for index in range(0, max(len(text) - 1, 0))}


def _getImageRefExt(data):
    if not isinstance(data, str):
        return ''
    ext = os.path.splitext(data.strip())[1].lower().lstrip('.')
    if re.fullmatch(r'[a-z0-9]{2,5}', ext):
        return ext
    return ''


def _normalizeImageLookupText(data):
    if not isinstance(data, str):
        return ''
    res = data.strip().lower()
    res = re.sub(r'\.[a-z0-9]{2,5}$', '', res)
    res = re.sub(r'表情包|图片|照片|文件|发图片|发送|来一张|一张|这个|那个', '', res)
    return re.sub(r'[\s\[\]【】()（）:：,，.。;；"“”\'‘’_-]+', '', res)


def translateOutgoing(msg_list, bot_hash, trace_id=None):
    '''把回复里的 [发图片:xxx] 转成真实 CQ:image 标签，无法解析则删掉。'''
    res = []
    cache_map = imageCacheMap(bot_hash)
    directory = os.path.abspath(imgDir())
    for i in msg_list:
        if not isinstance(i, str):
            continue
        s = re.sub(r'\[发图片\]', '', i)
        s = re.sub(r'\[图片[:：].*?\]', '', s)

        def repl(m):
            ref = m.group(1).strip()
            fn = resolveImageRef(ref, cache_map, trace_id=trace_id)
            if fn is None:
                return ''
            path = os.path.abspath(os.path.join(directory, fn))
            if not path.startswith(directory + os.sep) or not os.path.exists(path):
                OlivaAIAgent.conf.traceLog(
                    OlivaAIAgent.conf.gProc,
                    'vision.send.file_missing',
                    trace_id,
                    file=_safeImageName(fn),
                )
                return ''
            # 与 app.json message_mode=old_string 对齐，用 CQ 码，OlivOS 才会解析成真实图片
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'vision.send.translated',
                trace_id,
                file=_safeImageName(fn),
            )
            return '[CQ:image,file=file:///%s]' % path

        s = re.sub(r'\[发图片[:：](.+?)\]', repl, s)
        res.append(s)
    return res


def extractVisionFacts(message):
    facts = []
    for m in IMAGE_CODE_PATTERN.finditer(str(message)):
        cm = re.search(r'\[图片[:：]([^；\]]+)', m.group(0))
        if not cm:
            continue
        c = cm.group(1).strip()
        if c and '未识别成功' not in c and c not in facts:
            facts.append(c)
    return facts


def repairVisionDenial(reply_list, history):
    if not isinstance(reply_list, list) or not isinstance(history, list):
        return reply_list
    latest = history[-1] if history else {}
    facts = extractVisionFacts(latest.get('message', '') if isinstance(latest, dict) else '')
    if not facts:
        return reply_list
    prefix = '我看到了：%s。' % facts[-1]
    out = []
    for item in reply_list:
        if isinstance(item, str) and VISION_DENIAL_PATTERN.search(item):
            out.append(prefix)
        else:
            out.append(item)
    return out


def emojiIntentCache(bot_hash, group_id, max_size):
    '''给前置判定模型看的表情包候选（内容/意图，供它挑一个关键词）。'''
    cache_map = imageCacheMap(bot_hash)
    with _cache_lock:
        current = [str(item[0]) for item in list(_imageCache.get(group_id, [])) if isinstance(item, tuple)]
    if max_size <= 0:
        return {}
    cur_cand, glob_cand = [], []
    for fn, data in cache_map.items():
        if not isEmojiData(data):
            continue
        (cur_cand if fn in current else glob_cand).append(fn)
    import random
    random.shuffle(cur_cand)
    random.shuffle(glob_cand)
    selected = cur_cand + glob_cand[:max_size]
    return {fn: _publicImageData(cache_map[fn]) for fn in selected if isinstance(cache_map.get(fn), dict)}


def cleanupImageCache():
    with _cache_lock:
        _imageCache.clear()
