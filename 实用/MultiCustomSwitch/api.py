"""GUI 与 WebUI 共用业务接口；下载只接收并校验 JSON 回复。"""

import json
import time
import uuid
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from . import files, resources, runtime
from .store import MAX_BYTES, InvalidInput, validate_replies

EVENT = 'MultiCustomSwitch_Request'
_TRANSFERS = {}
CHUNK = 192 * 1024
MAX_REQUEST_BYTES = MAX_BYTES * 6 + 65536


def download(url):
    if not isinstance(url, str) or len(url) > 4096:
        raise InvalidInput('下载链接格式无效。')
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise InvalidInput('请输入不带账号密码的 HTTP/HTTPS JSON 下载链接。')
    # 不持文件锁发起网络请求；不保存或回显下载链接。
    request = Request(url, headers={'User-Agent': 'MultiCustomSwitch/1.0', 'Accept': 'application/json'})
    try:
        with urlopen(request, timeout=15) as response:
            if urlsplit(response.geturl()).scheme not in ('http', 'https'):
                raise InvalidInput('下载链接发生了不支持的重定向。')
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InvalidInput('下载文件超过 8 MiB。')
        return validate_replies(json.loads(raw.decode('utf-8-sig')))
    except InvalidInput:
        raise
    except Exception as exc:
        raise InvalidInput('下载失败，或下载内容不是有效的自定义回复 JSON。') from exc


def dispatch(payload):
    if not isinstance(payload, dict):
        raise InvalidInput('请求必须是 JSON 对象。')
    store = runtime.STORE
    if store is None:
        raise InvalidInput(runtime.INIT_ERROR or '插件尚未初始化，请检查 OlivaDiceCore 是否成功加载。')
    op = payload.get('op')
    scope = payload.get('scope', 'unity')
    if op == 'accounts':
        return {
            'accounts': [
                {'hash': 'unity', 'label': 'unity 模板库'},
                *[
                    {'hash': bot, 'label': f'{info.platform["platform"]} · {info.id}'}
                    for bot, info in store.bots.items()
                ],
            ],
            'version': resources.VERSION,
        }
    if op == 'help':
        return {'markdown': resources.WRITER_HELP}
    store.check_scope(scope)
    if op == 'reload':
        store.reload(scope)
        op = 'state'
    if op == 'state':
        with files.LOCK:
            return {
                'replies': store.list_replies(scope),
                'config': dict(store.configs[scope]) if scope != 'unity' else None,
                'groups': dict(store.groups[scope]) if scope != 'unity' else {},
                'modules': store.modules(scope) if scope != 'unity' else [],
                'index_revision': store.index_revision(scope) if scope != 'unity' else None,
            }
    selection = payload.get('selection')
    baseline = payload.get('baseline') or None
    if op == 'snapshot':
        return store.snapshot(scope, selection, baseline)
    if op == 'edit':
        return store.edit(
            scope,
            selection,
            payload.get('key'),
            payload.get('value'),
            payload.get('revision'),
            reset=payload.get('reset') is True,
            baseline_bot=baseline,
            delete=payload.get('delete') is True,
        )
    if op == 'create':
        return store.clone(scope, payload.get('name'), payload.get('source_scope'), payload.get('source_selection'))
    if op == 'rename':
        return store.rename(scope, selection, payload.get('name'))
    if op == 'reindex':
        return {'replies': store.reindex(scope, payload.get('mapping'), payload.get('index_revision'))}
    if op == 'export':
        return {'data': store.values(scope, selection)}
    if op == 'import':
        return store.import_pack(scope, payload.get('name'), payload.get('data'), payload.get('conflict'))
    if op == 'download':
        # 返回校验后的内容供界面进行同名处理；只下载一次。
        return {'data': download(payload.get('url'))}
    if op == 'transfer':
        with files.LOCK:
            values = store.values(payload.get('source_scope'), payload.get('source_selection'))
            return store.import_pack(scope, payload.get('name'), values, payload.get('conflict'))
    if op == 'settings':
        return store.select(
            scope, model=payload.get('model'), enabled=payload.get('enabled'), group_hash=payload.get('group_hash')
        )
    if op == 'recover':
        return {'modules': store.modules(scope, payload.get('modules'))}
    raise InvalidInput('未知操作。')


def clear_transfers():
    with files.LOCK:
        _TRANSFERS.clear()


def bridge(payload, owner):
    """大回复通过分片消息桥传输；没有额外 HTTP 服务。"""
    if not isinstance(payload, dict):
        raise InvalidInput('请求格式无效。')
    with files.LOCK:
        now = time.monotonic()
        for key in list(_TRANSFERS):
            if now - _TRANSFERS[key]['created'] > 180:
                del _TRANSFERS[key]
    action = payload.get('transport')
    if action == 'upload_start':
        with files.LOCK:
            if len(_TRANSFERS) >= 16:
                raise InvalidInput('传输过多，请稍后重试。')
            token = uuid.uuid4().hex
            _TRANSFERS[token] = {'owner': owner, 'created': now, 'text': '', 'kind': 'upload'}
            return {'token': token}
    if action in ('upload_chunk', 'upload_finish', 'download_chunk'):
        with files.LOCK:
            token = payload.get('token')
            item = _TRANSFERS.get(token)
            if item is None or item['owner'] != owner:
                raise InvalidInput('传输不存在或已过期。')
            if action == 'upload_chunk':
                if item['kind'] != 'upload' or not isinstance(payload.get('text'), str):
                    raise InvalidInput('上传片段无效。')
                text = payload['text']
                if (
                    len(text.encode('utf-8')) > CHUNK * 3
                    or len((item['text'] + text).encode('utf-8')) > MAX_REQUEST_BYTES
                ):
                    del _TRANSFERS[token]
                    raise InvalidInput('上传内容过大。')
                if payload.get('offset') != len(item['text']):
                    raise InvalidInput('上传片段顺序错误。')
                item['text'] += text
                return {'received': len(item['text'])}
            if action == 'upload_finish':
                if item['kind'] != 'upload':
                    raise InvalidInput('传输类型无效。')
                request = json.loads(item['text'])
                del _TRANSFERS[token]
            else:
                offset = payload.get('offset')
                if item['kind'] != 'download' or type(offset) is not int or not 0 <= offset <= len(item['text']):
                    raise InvalidInput('下载片段无效。')
                text = item['text'][offset : offset + CHUNK]
                done = offset + len(text) >= len(item['text'])
                if done:
                    del _TRANSFERS[token]
                return {'text': text, 'done': done}
    else:
        request = payload
    result = dispatch(request)
    encoded = json.dumps(result, ensure_ascii=True)
    if len(encoded) <= CHUNK:
        return result
    with files.LOCK:
        if len(_TRANSFERS) >= 16 or len(encoded) > MAX_BYTES * 6:
            raise InvalidInput('返回内容过大或传输过多。')
        token = uuid.uuid4().hex
        _TRANSFERS[token] = {'owner': owner, 'created': now, 'text': encoded, 'kind': 'download'}
        return {'download_token': token}
