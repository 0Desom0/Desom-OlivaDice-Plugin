# -*- encoding: utf-8 -*-
'''
OlivOS 运行时接口内省。

目录来源：当前 Event、Proc、当前平台 indeAPI，以及 OlivOS 已加载的适配器 SDK。
调用器只接受目录中真实存在的公开 callable，避免把导入到 SDK 的外部模块函数误暴露出去。
'''

import inspect
import re
import sys
import threading

import OlivOS


_VALID_SCOPES = {'all', 'event', 'proc', 'inde', 'current_sdk', 'sdk'}
_AUTO_CONTEXT = {
    'target_event': 'plugin_event',
    'plugin_event': 'plugin_event',
    'Proc': 'Proc',
    'proc': 'Proc',
}
_CACHE_LOCK = threading.RLock()
_SDK_ROOT_CACHE = {}
_SDK_CATALOG_CACHE = []
_OBJECT_CATALOG_CACHE = {
    'event': {},
    'proc': {},
    'inde': {},
}
_INITIALIZED = False


def _safe_signature(target):
    try:
        return str(inspect.signature(target))
    except (TypeError, ValueError):
        return '(...)'


def _summary(target):
    try:
        doc = inspect.getdoc(target) or ''
    except Exception:
        doc = ''
    for line in doc.splitlines():
        line = line.strip()
        if line:
            return line[:240]
    return 'OlivOS 源码中可调用的运行时接口（源码未提供 docstring）'


def _context_parameters(target):
    try:
        return [name for name in inspect.signature(target).parameters if name in _AUTO_CONTEXT]
    except (TypeError, ValueError):
        return []


def _entry(path, target, scope, current_adapter=False):
    return {
        'path': path,
        'signature': _safe_signature(target),
        'summary': _summary(target),
        'scope': scope,
        'module': getattr(target, '__module__', type(target).__module__),
        'current_adapter': bool(current_adapter),
        'auto_context': _context_parameters(target),
    }


def _is_visible(name):
    return bool(name) and not name.startswith('_')


def _scan_sdk_roots():
    roots = {}
    for name, value in vars(OlivOS).items():
        if not name.lower().endswith('sdk') or not inspect.ismodule(value):
            continue
        module_name = getattr(value, '__name__', '')
        if module_name.startswith('OlivOS.adapter.'):
            roots[name] = value
    # 兼容运行中才加载、尚未重新导出到 OlivOS 顶层的新适配器 SDK。
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith('OlivOS.adapter.') or not inspect.ismodule(module):
            continue
        short_name = module_name.rsplit('.', 1)[-1]
        if not short_name.lower().endswith('sdk'):
            continue
        root_name = short_name
        if root_name in roots and roots[root_name] is not module:
            root_name = module_name.removeprefix('OlivOS.adapter.').replace('.', '_')
        roots[root_name] = module
    return roots


def _cached_object_catalog(target, prefix, scope, current_adapter=False):
    if target is None:
        return []
    target_type = type(target)
    with _CACHE_LOCK:
        cached = _OBJECT_CATALOG_CACHE[scope].get(target_type)
        if cached is None:
            cached = list(
                _iter_object_callables(
                    target,
                    prefix,
                    scope,
                    current_adapter=current_adapter,
                )
            )
            _OBJECT_CATALOG_CACHE[scope][target_type] = cached
        return [dict(item) for item in cached]


def initialize(plugin_event=None, Proc=None, force=False):
    '''初始化并缓存接口元数据；缓存不保存具体事件对象。'''
    global _INITIALIZED, _SDK_ROOT_CACHE, _SDK_CATALOG_CACHE
    with _CACHE_LOCK:
        if force or not _INITIALIZED:
            roots = _scan_sdk_roots()
            sdk_catalog = []
            for root_name, module in sorted(roots.items()):
                sdk_catalog.extend(_iter_sdk_callables(root_name, module, False))
            _SDK_ROOT_CACHE = roots
            _SDK_CATALOG_CACHE = sdk_catalog
            for scope_cache in _OBJECT_CATALOG_CACHE.values():
                scope_cache.clear()
            _INITIALIZED = True

        if plugin_event is not None:
            _cached_object_catalog(plugin_event, 'event', 'event')
            _cached_object_catalog(getattr(plugin_event, 'indeAPI', None), 'inde', 'inde', current_adapter=True)
            # 已加载 SDK 的 inde_interface 也在初始化阶段全部写入缓存；只缓存元数据，不保留临时实例。
            for module in _SDK_ROOT_CACHE.values():
                inde_type = getattr(module, 'inde_interface', None)
                if not inspect.isclass(inde_type):
                    continue
                try:
                    inde_object = inde_type(plugin_event, 'all')
                except Exception:
                    continue
                _cached_object_catalog(inde_object, 'inde', 'inde', current_adapter=True)
        if Proc is not None:
            _cached_object_catalog(Proc, 'proc', 'proc')

        return {
            'sdk_interfaces': len(_SDK_CATALOG_CACHE),
            'sdk_modules': len(_SDK_ROOT_CACHE),
            'event_types': len(_OBJECT_CATALOG_CACHE['event']),
            'proc_types': len(_OBJECT_CATALOG_CACHE['proc']),
            'inde_types': len(_OBJECT_CATALOG_CACHE['inde']),
        }


def _normalized_sdk_name(value):
    value = re.sub(r'[^a-z0-9]+', '', str(value).lower())
    for suffix in ('linkserver', 'pollserver', 'sdk', 'link', 'poll'):
        if value.endswith(suffix):
            value = value[:-len(suffix)]
    return value


def _current_sdk_roots(plugin_event, roots):
    current = set()
    sdk_event = getattr(plugin_event, 'sdk_event', None)
    event_module = getattr(type(sdk_event), '__module__', '')
    for root_name, module in roots.items():
        module_name = getattr(module, '__name__', '')
        if event_module == module_name or event_module.startswith(module_name + '.'):
            current.add(root_name)

    if current:
        return current

    try:
        sdk_name = plugin_event.platform.get('sdk', '')
    except Exception:
        sdk_name = ''
    sdk_token = _normalized_sdk_name(sdk_name)
    if not sdk_token:
        return current
    for root_name in roots:
        root_token = _normalized_sdk_name(root_name)
        if root_token and (root_token == sdk_token or root_token in sdk_token or sdk_token in root_token):
            current.add(root_name)
    return current


def _iter_object_callables(target, prefix, scope, current_adapter=False):
    for name in sorted(dir(target)):
        if not _is_visible(name):
            continue
        try:
            value = getattr(target, name)
        except Exception:
            continue
        if callable(value):
            yield _entry('%s.%s' % (prefix, name), value, scope, current_adapter=current_adapter)


def _iter_class_callables(cls, prefix, module_name, current_adapter, depth=0):
    if depth > 3:
        return
    for name, raw_value in sorted(vars(cls).items()):
        if not _is_visible(name):
            continue
        path = '%s.%s' % (prefix, name)
        if inspect.isclass(raw_value):
            if getattr(raw_value, '__module__', '') == module_name:
                yield from _iter_class_callables(
                    raw_value,
                    path,
                    module_name,
                    current_adapter,
                    depth=depth + 1,
                )
            continue

        is_bound_descriptor = isinstance(raw_value, (staticmethod, classmethod))
        function = raw_value.__func__ if is_bound_descriptor else raw_value
        if not inspect.isfunction(function) or getattr(function, '__module__', '') != module_name:
            continue
        if not is_bound_descriptor:
            try:
                parameters = list(inspect.signature(function).parameters.values())
            except (TypeError, ValueError):
                parameters = []
            if parameters and parameters[0].name in {'self', 'cls'}:
                # 这类方法需要先构造并保存 SDK 对象，不能作为无状态 function call 安全调用。
                continue
        try:
            target = getattr(cls, name)
        except Exception:
            continue
        yield _entry(path, target, 'sdk', current_adapter=current_adapter)


def _iter_sdk_callables(root_name, module, current_adapter):
    module_name = getattr(module, '__name__', '')
    prefix = 'sdk.%s' % root_name
    for name, value in sorted(vars(module).items()):
        if not _is_visible(name):
            continue
        path = '%s.%s' % (prefix, name)
        if inspect.isfunction(value) and getattr(value, '__module__', '') == module_name:
            yield _entry(path, value, 'sdk', current_adapter=current_adapter)
        elif inspect.isclass(value) and getattr(value, '__module__', '') == module_name:
            yield from _iter_class_callables(value, path, module_name, current_adapter)


def _catalog(ctx, scope='all'):
    if scope not in _VALID_SCOPES:
        raise ValueError('scope 必须是 all/event/proc/inde/current_sdk/sdk')
    plugin_event = ctx.get('plugin_event')
    if plugin_event is None:
        raise ValueError('当前没有 plugin_event 上下文')
    Proc = ctx.get('Proc')
    initialize(plugin_event=plugin_event, Proc=Proc)

    entries = []
    if scope in {'all', 'event'}:
        entries.extend(_cached_object_catalog(plugin_event, 'event', 'event'))

    if scope in {'all', 'proc'} and Proc is not None:
        entries.extend(_cached_object_catalog(Proc, 'proc', 'proc'))

    inde_api = getattr(plugin_event, 'indeAPI', None)
    if scope in {'all', 'inde'} and inde_api is not None:
        entries.extend(_cached_object_catalog(inde_api, 'inde', 'inde', current_adapter=True))

    if scope in {'all', 'current_sdk', 'sdk'}:
        with _CACHE_LOCK:
            roots = dict(_SDK_ROOT_CACHE)
            sdk_catalog = [dict(item) for item in _SDK_CATALOG_CACHE]
        current_roots = _current_sdk_roots(plugin_event, roots)
        for item in sdk_catalog:
            root_name = item['path'].split('.', 2)[1]
            item['current_adapter'] = root_name in current_roots
            if scope == 'current_sdk' and not item['current_adapter']:
                continue
            entries.append(item)

    # 同一路径只保留一项；排序让当前平台的 indeAPI / SDK 优先出现。
    unique = {item['path']: item for item in entries}
    return sorted(
        unique.values(),
        key=lambda item: (
            {
                'inde': 0,
                'event': 1,
                'proc': 2,
                'sdk': 3 if item['current_adapter'] else 4,
            }.get(item['scope'], 9),
            item['path'].lower(),
        ),
    )


def _query_tokens(query):
    return [token for token in re.split(r'[\s,，。/]+', str(query).strip().lower()) if token]


def _match_score(item, tokens):
    path = item['path'].lower()
    leaf = path.rsplit('.', 1)[-1]
    haystack = ' '.join([path, item['signature'].lower(), item['summary'].lower(), item['module'].lower()])
    if tokens and not all(token in haystack for token in tokens):
        return None
    score = 20 if item['current_adapter'] else 0
    score += {'inde': 60, 'event': 40, 'proc': 35, 'sdk': 0}.get(item['scope'], 0)
    for token in tokens:
        if token == leaf:
            score += 100
        elif token in leaf:
            score += 50
        elif token in path:
            score += 25
        else:
            score += 5
    return score


def discover(ctx, query='', scope='all', limit=12):
    '''检索运行时接口目录；返回值只包含元数据，不执行接口。'''
    entries = _catalog(ctx, scope=scope)
    tokens = _query_tokens(query)
    matches = []
    for item in entries:
        score = _match_score(item, tokens)
        if score is not None:
            matches.append((score, item))
    matches.sort(key=lambda pair: (-pair[0], pair[1]['path'].lower()))

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 12
    limit = max(1, min(limit, 60))
    counts = {}
    for item in entries:
        counts[item['scope']] = counts.get(item['scope'], 0) + 1

    plugin_event = ctx['plugin_event']
    platform = getattr(plugin_event, 'platform', {})
    with _CACHE_LOCK:
        roots = dict(_SDK_ROOT_CACHE)
    current_roots = sorted(_current_sdk_roots(plugin_event, roots))
    return {
        'active': True,
        'data': {
            'platform': platform,
            'current_sdk_modules': current_roots,
            'catalog_counts': counts,
            'matched': len(matches),
            'returned': min(limit, len(matches)),
            'interfaces': [item for _score, item in matches[:limit]],
            'usage': (
                '从 interfaces[].path 原样选择路径交给 olivos_call；优先使用 inde，其次 event/proc，最后 sdk。'
                'auto_context 中的参数会由调用器注入，不要自行伪造。'
            ),
        },
    }


def current_chat_context(ctx):
    '''从当前事件的标准字段推导发送目标；qqGuildv2 同时覆盖 QQ 群/C2C 与频道/频道私信。'''
    plugin_event = ctx.get('plugin_event')
    data = getattr(plugin_event, 'data', None)
    extend = getattr(data, 'extend', None)
    extend = extend if isinstance(extend, dict) else {}
    func_type = str(
        ctx.get('func_type')
        or getattr(plugin_event, 'plugin_info', {}).get('func_type', '')
    )
    group_id = ctx.get('group_id') or getattr(data, 'group_id', None)
    user_id = ctx.get('user_id') or getattr(data, 'user_id', None)
    host_id = extend.get('host_group_id') or getattr(data, 'host_id', None)
    flag_direct = bool(extend.get('flag_from_direct', func_type == 'private_message'))

    # qqGuildv2 在 Event.data.extend 中明确标记消息来自 QQ 群/C2C 还是频道。
    if 'flag_from_qq' in extend:
        flag_from_qq = bool(extend.get('flag_from_qq'))
        if flag_from_qq:
            return {
                'chat_type': 'qq_private' if flag_direct else 'qq_group',
                'chat_id': user_id if flag_direct else group_id,
            }
        return {
            'chat_type': 'guild_private' if flag_direct else 'guild_channel',
            'chat_id': (host_id or group_id) if flag_direct else group_id,
        }

    try:
        platform_name = str(plugin_event.platform.get('platform', '')).lower()
    except Exception:
        platform_name = ''
    if platform_name == 'qqguild':
        if host_id:
            return {
                'chat_type': 'guild_private' if flag_direct else 'guild_channel',
                'chat_id': (host_id or group_id) if flag_direct else group_id,
            }
        return {
            'chat_type': 'qq_private' if flag_direct else 'qq_group',
            'chat_id': user_id if flag_direct else group_id,
        }
    return {
        'chat_type': 'private' if flag_direct else 'group',
        'chat_id': user_id if flag_direct else group_id,
    }


def prompt_chat_context_summary(ctx):
    '''生成当前会话的可调用上下文提示，阻止模型编造 CURRENT_CHANNEL 一类占位符。'''
    chat_context = current_chat_context(ctx)
    chat_type = chat_context.get('chat_type')
    chat_id = chat_context.get('chat_id')
    if not chat_type or chat_id in [None, '']:
        return ''
    return (
        '当前会话发送参数（由事件运行时推导）：chat_type=%s，chat_id=%s。'
        '接口签名包含 chat_type/chat_id 时必须使用这两个真实值，或分别传 '
        '{"$ctx":"chat_type"}/{"$ctx":"chat_id"}；禁止填写 CURRENT_CHANNEL 等占位符。'
    ) % (chat_type, chat_id)


def prompt_interface_summary(ctx, limit=40, max_chars=6000):
    '''把当前事件真实 indeAPI 的公开接口压缩成提示词摘要，不执行任何接口。'''
    result = discover(ctx, query='', scope='inde', limit=limit)
    interfaces = result.get('data', {}).get('interfaces', [])
    lines = []
    used_chars = 0
    for item in interfaces:
        line = '%s%s' % (item.get('path', ''), item.get('signature', '(...)'))
        if not line.strip() or used_chars + len(line) > max_chars:
            break
        lines.append(line)
        used_chars += len(line) + 1
    return '\n'.join(lines)


def _context_value(ctx, name):
    plugin_event = ctx.get('plugin_event')
    data = getattr(plugin_event, 'data', None)
    chat_context = current_chat_context(ctx)
    values = {
        'plugin_event': plugin_event,
        'event': plugin_event,
        'Proc': ctx.get('Proc'),
        'proc': ctx.get('Proc'),
        'bot_info': getattr(plugin_event, 'bot_info', None),
        'sdk_event': getattr(plugin_event, 'sdk_event', None),
        'data': data,
        'inde_api': getattr(plugin_event, 'indeAPI', None),
        'platform': getattr(plugin_event, 'platform', None),
        'group_id': ctx.get('group_id'),
        'user_id': ctx.get('user_id'),
        'self_id': ctx.get('self_id'),
        'host_id': getattr(data, 'host_id', None),
        'control_queue': getattr(plugin_event, 'plugin_info', {}).get('control_queue'),
        'chat_type': chat_context.get('chat_type'),
        'chat_id': chat_context.get('chat_id'),
    }
    if name not in values:
        raise ValueError('未知上下文占位符: %s' % name)
    return values[name]


def _convert_value(ctx, value):
    if isinstance(value, list):
        return [_convert_value(ctx, item) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {'$ctx'}:
        return _context_value(ctx, str(value['$ctx']))
    if set(value) == {'$olivos_message'}:
        spec = value['$olivos_message']
        if not isinstance(spec, dict):
            raise ValueError('$olivos_message 必须是对象')
        mode = str(spec.get('mode', 'olivos_string'))
        return OlivOS.messageAPI.Message_templet(mode_rx=mode, data_raw=spec.get('data', ''))
    return {key: _convert_value(ctx, item) for key, item in value.items()}


def _resolve(ctx, path):
    parts = str(path).split('.')
    if len(parts) < 2 or any(not _is_visible(part) for part in parts):
        raise ValueError('接口路径格式无效或包含私有成员')
    plugin_event = ctx['plugin_event']
    if parts[0] == 'event':
        target = plugin_event
        attrs = parts[1:]
    elif parts[0] == 'inde':
        target = getattr(plugin_event, 'indeAPI', None)
        attrs = parts[1:]
        if target is None:
            raise ValueError('当前平台没有 indeAPI')
    elif parts[0] == 'proc':
        target = ctx.get('Proc')
        attrs = parts[1:]
        if target is None:
            raise ValueError('当前没有 Proc 上下文')
    elif parts[0] == 'sdk' and len(parts) >= 3:
        with _CACHE_LOCK:
            roots = dict(_SDK_ROOT_CACHE)
        if parts[1] not in roots:
            raise ValueError('SDK 模块未加载: %s' % parts[1])
        target = roots[parts[1]]
        attrs = parts[2:]
    else:
        raise ValueError('接口路径必须以 event./proc./inde./sdk. 开头')
    for name in attrs:
        target = getattr(target, name)
    if not callable(target):
        raise ValueError('目标不是 callable: %s' % path)
    return target


def _prepare_call(ctx, target, args, kwargs):
    call_args = [_convert_value(ctx, item) for item in args]
    call_kwargs = {key: _convert_value(ctx, value) for key, value in kwargs.items()}
    normalized_context = {}
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return call_args, call_kwargs, None, normalized_context

    parameters = list(signature.parameters.values())
    parameter_names = {parameter.name for parameter in parameters}
    target_module = str(getattr(target, '__module__', '')).lower()
    if {'chat_type', 'chat_id'} <= parameter_names and 'qqguildv2sdk' in target_module:
        chat_context = current_chat_context(ctx)
        current_type = chat_context.get('chat_type')
        current_id = chat_context.get('chat_id')
        valid_types = {'qq_group', 'qq_private', 'guild_channel', 'guild_private'}
        supplied_type = str(call_kwargs.get('chat_type', '')).strip().lower()
        if current_type in valid_types and supplied_type not in valid_types:
            call_kwargs['chat_type'] = current_type
            normalized_context['chat_type'] = current_type
        supplied_id = str(call_kwargs.get('chat_id', '')).strip()
        placeholder_id = supplied_id.lower() in {
            '', 'current', 'current_chat', 'current_channel', 'current_group',
            '当前会话', '当前频道', '当前群',
        }
        if current_id not in [None, ''] and placeholder_id:
            call_kwargs['chat_id'] = current_id
            normalized_context['chat_id'] = current_id

    if call_args:
        leading_context = []
        for parameter in parameters:
            if parameter.kind not in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD):
                break
            context_name = _AUTO_CONTEXT.get(parameter.name)
            if context_name is None:
                break
            context_value = _context_value(ctx, context_name)
            if call_args and call_args[0] is context_value:
                break
            leading_context.append(context_value)
        call_args = leading_context + call_args

    try:
        bound = signature.bind_partial(*call_args, **call_kwargs)
    except TypeError as e:
        return None, None, '参数预绑定失败: %s' % e, normalized_context
    for parameter in parameters:
        if parameter.name in bound.arguments or parameter.name not in _AUTO_CONTEXT:
            continue
        call_kwargs[parameter.name] = _context_value(ctx, _AUTO_CONTEXT[parameter.name])
    try:
        signature.bind(*call_args, **call_kwargs)
    except TypeError as e:
        return None, None, '参数不符合 %s: %s' % (signature, e), normalized_context
    return call_args, call_kwargs, None, normalized_context


def invoke(ctx, path, args=None, kwargs=None):
    '''调用 discover 返回的公开接口路径。权限判定由外层 olivos_call 工具统一执行。'''
    args = [] if args is None else args
    kwargs = {} if kwargs is None else kwargs
    if not isinstance(args, list):
        return {'active': False, 'data': {'error': 'args 必须是数组'}}
    if not isinstance(kwargs, dict):
        return {'active': False, 'data': {'error': 'kwargs 必须是对象'}}

    catalog = {item['path']: item for item in _catalog(ctx, scope='all')}
    if path not in catalog:
        return {
            'active': False,
            'data': {
                'error': '路径不在当前运行时公开接口目录中，请先用 olivos_discover 获取精确路径',
                'path': path,
            },
        }
    target = _resolve(ctx, path)
    call_args, call_kwargs, error, normalized_context = _prepare_call(ctx, target, args, kwargs)
    if error is not None:
        return {
            'active': False,
            'data': {
                'error': error,
                'path': path,
                'signature': catalog[path]['signature'],
            },
        }
    result = target(*call_args, **call_kwargs)
    active = result.get('active', True) if isinstance(result, dict) else True
    data = {
        'interface': path,
        'result': result if result is not None else '已执行（接口无返回值）',
    }
    if normalized_context:
        data['normalized_context'] = normalized_context
    return {
        'active': bool(active),
        'data': data,
    }
