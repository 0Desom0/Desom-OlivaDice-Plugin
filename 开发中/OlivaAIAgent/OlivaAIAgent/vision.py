# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 视觉/图片子系统（移植并增强自刺客）
- OCR/视觉识别: 把消息中的 [CQ/OP:image] / mface 转成 [图片：内容；意图；类型] 事实摘要
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

import requests

import OlivaAIAgent

OP_IMAGE_PATTERN = re.compile(r'\[(?:CQ|OP):image,[^\]]+\]')
MFACE_PATTERN = re.compile(r'\[(?:CQ|OP):mface,[^\]]*\]')
IMAGE_CODE_PATTERN = re.compile(r'\[图片：[^\]]*\]')
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
    res = '[图片：未识别成功，不应回复；意图：不明；类型：不明]'
    if isinstance(data, dict) and 'content' in data and 'intent' in data and 'type' in data:
        c = str(data.get('content', '未识别成功')).strip()[:32]
        i = str(data.get('intent', '不明')).strip()[:32]
        t = str(data.get('type', '不明')).strip()[:32]
        res = '[图片：%s；意图：%s；类型：%s]' % (c, i, t)
    return res


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


def _looksLikeImage(b):
    '''魔数兜底：官机 CDN 可能不返回 image/* content-type，但内容确是图片。'''
    if not b or len(b) < 12:
        return False
    return (b[:3] == b'\xff\xd8\xff' or b[:8] == b'\x89PNG\r\n\x1a\n'
            or b[:6] in (b'GIF87a', b'GIF89a') or b[:2] == b'BM'
            or (b[:4] == b'RIFF' and b[8:12] == b'WEBP'))


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
    if not ctype.startswith('image/') and not _looksLikeImage(content):
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.download.rejected',
            trace_id,
            bytes=len(content),
            content_type=ctype or 'missing',
        )
        return None, None
    safe = _safeImageName(file_name, ctype)
    b = base64.b64encode(content).decode('utf-8')
    data_url = 'data:%s;base64,%s' % (_mimeOf(safe, ctype), b)
    # 存盘=最佳努力：文件名/磁盘问题绝不能让识别失败（官机 URL 曾因此报 SAVE ERR 并回退发原始URL致400）
    path = None
    try:
        p = os.path.join(imgDir(), safe)
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
        'vision.download.done',
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
                'vision.ocr.http_error',
                trace_id,
                body=str(r.text)[:300],
                elapsed_ms=int((time.perf_counter() - started) * 1000),
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
                'vision.ocr.success',
                trace_id,
                content=result['content'],
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                intent=result['intent'],
                type=result['type'],
            )
            return result
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.ocr.invalid_result',
            trace_id,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            response=content[:300],
        )
    except Exception as e:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.ocr.exception',
            trace_id,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            error='%s: %s' % (type(e).__name__, e),
        )
    return None


def _cachedOnly(bot_hash, file_name):
    '''只读缓存（持锁快照），不联网。命中返回 dict，否则 None。'''
    klock = OlivaAIAgent.knowledge._lock
    with klock:
        gc = OlivaAIAgent.knowledge.getMem(bot_hash)['全局'].get('图片缓存', {})
        v = gc.get(file_name) if isinstance(gc, dict) else None
        return dict(v) if isinstance(v, dict) else None


def _storeOcr(bot_hash, file_name, data, trace_id=None):
    '''把 OCR 结果写入持久图片缓存（持 knowledge._lock，与 saveMem 一致）。'''
    klock = OlivaAIAgent.knowledge._lock
    with klock:
        mem = OlivaAIAgent.knowledge.getMem(bot_hash)
        global_cache = mem['全局'].setdefault('图片缓存', {})
        global_cache.pop(file_name, None)
        global_cache[file_name] = data
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
    '''执行下载+OCR，返回 data 或 None。无网络配置直接 None。'''
    vc = _visionConf()
    if not (vc and image_url and vc.get('api_key') and vc.get('model')):
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'vision.ocr.skipped',
            trace_id,
            has_image_url=bool(image_url),
            reason='vision_disabled_or_incomplete',
        )
        return None
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.route',
        trace_id,
        file=_safeImageName(file_name),
        mode=vc.get('mode', 'base64'),
        model=vc.get('model', ''),
    )
    # base64 模式，或识别不了的官机/签名 URL：必须先下成 base64 再喂给识图模型
    if vc.get('mode', 'base64') == 'base64' or _isUnfetchableUrl(image_url):
        b64, _ = _downloadBase64(image_url, file_name, trace_id=trace_id)
        if not b64:
            # 关键：下载/转码失败时【不回退发原始URL】——官机 URL 第三方模型取不到会 400，宁可占位
            OlivaAIAgent.conf.traceLog(
                OlivaAIAgent.conf.gProc,
                'vision.ocr.skipped',
                trace_id,
                reason='download_or_transcode_failed',
            )
            return None
        return _callOcr(vc, b64, trace_id=trace_id)
    return _callOcr(vc, image_url, trace_id=trace_id)


def _pushGroupCache(group_id, file_name, data):
    qsize = int(OlivaAIAgent.conf.get('vision', 'queue_size', default=8))
    with _cache_lock:
        q = _imageCache.get(group_id)
        if q is None or q.maxlen != qsize:
            newq = deque(q or (), maxlen=qsize)
            _imageCache[group_id] = newq
            q = newq
        q.append((file_name, data))


def _bgIngest(bot_hash, group_id, file_name, image_url, trace_id=None):
    key = (str(bot_hash), str(file_name))
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
            data = _runOcr(file_name, image_url, trace_id=trace_id)
            if data is not None:
                _storeOcr(bot_hash, file_name, data, trace_id=trace_id)
                _pushGroupCache(group_id, file_name, data)
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
    data = _cachedOnly(bot_hash, file_name)
    OlivaAIAgent.conf.traceLog(
        OlivaAIAgent.conf.gProc,
        'vision.cache.lookup',
        trace_id,
        allow_network=allow_network,
        file=_safeImageName(file_name),
        hit=data is not None,
    )
    if data is None and allow_network:
        data = _runOcr(file_name, image_url, trace_id=trace_id)
        if data is not None:
            _storeOcr(bot_hash, file_name, data, trace_id=trace_id)
    if data is None:
        # 缓存未命中：非阻塞模式下后台识别，供后续引用；本次先返回占位
        if not allow_network and image_url and _visionConf():
            _bgIngest(bot_hash, group_id, file_name, image_url, trace_id=trace_id)
        data = _basicData(message_text, image_type=image_type, summary=summary)
    _pushGroupCache(group_id, file_name, data)
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
        fn = params.get('file')
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
        digest = hashlib.sha256(url_text.encode('utf-8')).hexdigest()[:20]
        file_name = 'remote_%s.jpg' % digest
        fact = _cacheData(
            bot_hash,
            group_id,
            file_name,
            url_text,
            '[远程图片]',
            '图片',
            allow_network=True,
            trace_id=trace_id,
        )
        facts.append(fact)
    return facts


def imageCacheMap(bot_hash):
    res = {}
    if bot_hash is not None:
        # 持锁快照，避免派发线程并发写入时 "dict changed size during iteration"
        with OlivaAIAgent.knowledge._lock:
            gc = OlivaAIAgent.knowledge.getMem(bot_hash)['全局'].get('图片缓存', {})
            snap = dict(gc) if isinstance(gc, dict) else {}
        for k, v in snap.items():
            if isinstance(v, dict):
                res[str(k)] = v
    with _cache_lock:
        snap_q = [list(q) for q in _imageCache.values()]
    for q in snap_q:
        for item in q:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], dict):
                res[str(item[0])] = item[1]
    return res


def groupImageCacheDict(group_id):
    res = {}
    with _cache_lock:
        items = list(_imageCache.get(group_id, []))
    for item in items:
        if isinstance(item, tuple) and len(item) >= 2:
            res[str(item[0])] = item[1]
    return res


def isEmojiData(d):
    if not isinstance(d, dict):
        return False
    target = '%s %s %s' % (d.get('type', ''), d.get('intent', ''), d.get('content', ''))
    return any(x in target for x in ('表情包', '梗图', 'mface', '表情', 'emoji'))


def resolveImageRef(image_ref, cache_map):
    '''把 AI 给的图片引用（文件名或关键词）解析为缓存里的真实文件名。'''
    image_ref = str(image_ref).strip()
    if image_ref in cache_map:
        return image_ref
    ref_low = image_ref.lower()
    best, best_score = None, 0
    for fn, data in cache_map.items():
        if not isinstance(data, dict):
            continue
        text = ('%s %s %s %s' % (fn, data.get('content', ''), data.get('intent', ''),
                                 data.get('type', ''))).lower()
        score = 0
        if ref_low and ref_low in text:
            score = len(ref_low) * 2
        else:
            common = set(ref_low) & set(text)
            score = len(common)
        if score > best_score:
            best_score, best = score, fn
    if best is not None and best_score >= max(2, len(ref_low) // 2):
        return best
    return None


def translateOutgoing(msg_list, bot_hash):
    '''把回复里的 [发图片:xxx] 转成真实 OP:image 标签，无法解析则删掉。'''
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
            fn = resolveImageRef(ref, cache_map)
            if fn is None:
                return ''
            path = os.path.abspath(os.path.join(directory, fn))
            if not path.startswith(directory + os.sep) or not os.path.exists(path):
                return ''
            # 与 app.json message_mode=old_string 对齐，用 CQ 码，OlivOS 才会解析成真实图片
            return '[CQ:image,file=file:///%s]' % path

        s = re.sub(r'\[发图片[:：](.+?)\]', repl, s)
        res.append(s)
    return res


def extractVisionFacts(message):
    facts = []
    for m in IMAGE_CODE_PATTERN.finditer(str(message)):
        cm = re.search(r'\[图片：([^；\]]+)', m.group(0))
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
    return {fn: cache_map[fn] for fn in selected if isinstance(cache_map.get(fn), dict)}


def cleanupImageCache():
    with _cache_lock:
        _imageCache.clear()
