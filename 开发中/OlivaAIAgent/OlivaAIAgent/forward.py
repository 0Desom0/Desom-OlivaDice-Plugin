# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 合并转发读取与清洗。

正文通过 OlivOS get_forward_msg 展开。节点中的媒体默认只保留类型占位，
只有 forward 配置显式开启后才会交给现有图片、语音和视频识别管线。
'''

import re

import OlivOS
import OlivaAIAgent


MAX_DEPTH = 4
MAX_NODES = 100
MAX_TEXT_CHARS = 16000
MAX_MEDIA_ITEMS = 4
FORWARD_TAG_PATTERN = re.compile(r'\[(?:CQ|OP):forward,[^\]]*\bid=([^,\]]+)', re.I)
CHAT_RECORD_PLACEHOLDER_PATTERN = re.compile(r'^\s*\[(?:聊天记录|合并转发|转发消息)\]\s*$', re.I)
SENDER_METADATA_PATTERN = re.compile(r'^\s*\[发送者\]\s*(.*?)\s*$', re.I)


def _configEnabled(kind):
    return bool(OlivaAIAgent.conf.get('forward', kind, default=False))


def _newState():
    return {
        'images': [],
        'audio_urls': [],
        'video_urls': [],
        'image_count': 0,
        'audio_count': 0,
        'video_count': 0,
        'node_count': 0,
        'forward_count': 0,
        'failed_count': 0,
        'truncated': False,
    }


def _trace(stage, trace_id=None, **fields):
    try:
        OlivaAIAgent.conf.traceLog(OlivaAIAgent.conf.gProc, stage, trace_id, **fields)
    except Exception:
        pass


def _idLabel(forward_id):
    return re.sub(r'[\r\n\t]+', ' ', str(forward_id or '')).strip()[:96]


def _first(data, *keys):
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value not in [None, '']:
            return value
    return None


def _mediaPlaceholder(state, kind, ref):
    count_key = {'image': 'image_count', 'audio': 'audio_count', 'video': 'video_count'}[kind]
    list_key = {'image': 'images', 'audio': 'audio_urls', 'video': 'video_urls'}[kind]
    state[count_key] += 1
    fallback = {'image': '[图片]', 'audio': '[语音]', 'video': '[视频]'}[kind]
    if not _configEnabled(kind):
        return fallback
    value = str(ref or '').strip()
    if not value:
        return fallback
    if kind == 'image' and not value.startswith(('http://', 'https://')):
        return fallback
    target = state[list_key]
    if value in target:
        index = target.index(value)
    elif len(target) < MAX_MEDIA_ITEMS:
        target.append(value)
        index = len(target) - 1
    else:
        return fallback
    if kind == 'image':
        return OlivaAIAgent.vision.imagePlaceholder(index)
    if kind == 'audio':
        return OlivaAIAgent.media.audioPlaceholder(index)
    return OlivaAIAgent.media.videoPlaceholder(index)


def _messageSegments(content):
    if content is None:
        return []
    if isinstance(content, OlivOS.messageAPI.Message_templet):
        return list(content.data)
    if isinstance(content, (list, tuple)):
        return list(content)
    if isinstance(content, str):
        mode = 'olivos_string' if '[OP:' in content else 'old_string'
        message = OlivOS.messageAPI.Message_templet(mode, content)
        return list(message.data) if message.active else [content]
    if isinstance(content, dict):
        if content.get('type') not in [None, '']:
            return [content]
        nested = _first(
            content,
            'message',
            'segments',
            'content',
            'raw_message',
            'messages',
            'nodes',
            'msg_elements',
        )
        if nested is not None:
            return _messageSegments(nested)
    return [content]


def _nodeData(node):
    if isinstance(node, OlivOS.messageAPI.PARA.node):
        raw = node.data
    elif isinstance(node, dict):
        raw = node
    else:
        return {}
    if str(raw.get('type') or '').lower() == 'node' and isinstance(raw.get('data'), dict):
        return raw['data']
    return raw


def _inlineMessages(data, include_content=False):
    if not isinstance(data, dict):
        return None
    keys = ['messages', 'nodes', 'msg_elements', 'message_chain']
    if include_content:
        keys.append('content')
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return None


def _plainNodeText(node):
    '''只读取纯文本节点，用于识别平台生成的“聊天记录”结构标记。'''
    data = _nodeData(node)
    content = _first(data, 'content', 'message', 'segments', 'raw_message')
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, OlivOS.messageAPI.Message_templet):
        segments = list(content.data)
    elif isinstance(content, (list, tuple)):
        segments = list(content)
    else:
        return None
    if len(segments) != 1:
        return None
    segment = segments[0]
    if isinstance(segment, OlivOS.messageAPI.PARA.text):
        return str(segment.data.get('text', '')).strip()
    if isinstance(segment, dict) and str(segment.get('type') or '').lower() == 'text':
        data = segment.get('data') if isinstance(segment.get('data'), dict) else {}
        return str(_first(data, 'text', 'content') or '').strip()
    return None


def _isDuplicateSenderMetadata(node, plain_text):
    match = SENDER_METADATA_PATTERN.fullmatch(str(plain_text or ''))
    if match is None:
        return False
    sender_name, _, _, _ = _nodeFields(node)
    return bool(str(sender_name or '').strip() == match.group(1).strip())


def _inlineForward(plugin_event, messages, state, trace_id, depth, stack, budget):
    state['forward_count'] += 1
    if depth > MAX_DEPTH:
        state['failed_count'] += 1
        return '[合并转发:嵌套层级过深]'
    content = _formatNodes(plugin_event, messages, state, trace_id, depth, stack, budget)
    return '[合并转发:\n%s\n]' % (content or '[空转发]')


def _paraText(para, plugin_event, state, trace_id, depth, stack, budget):
    if isinstance(para, OlivOS.messageAPI.PARA.text):
        return str(para.data.get('text', ''))
    if isinstance(para, OlivOS.messageAPI.PARA.at):
        name = para.data.get('name') or para.data.get('id') or ''
        return '@%s' % name if name else ''
    if isinstance(para, OlivOS.messageAPI.PARA.image):
        return _mediaPlaceholder(state, 'image', para.data.get('url') or para.data.get('file'))
    if isinstance(para, OlivOS.messageAPI.PARA.record):
        return _mediaPlaceholder(state, 'audio', para.data.get('url') or para.data.get('file'))
    if isinstance(para, OlivOS.messageAPI.PARA.video):
        return _mediaPlaceholder(state, 'video', para.data.get('url') or para.data.get('file'))
    if isinstance(para, OlivOS.messageAPI.PARA.forward):
        inline_messages = _inlineMessages(para.data, include_content=True)
        if inline_messages is not None:
            return _inlineForward(
                plugin_event,
                inline_messages,
                state,
                trace_id,
                depth + 1,
                stack,
                budget,
            )
        return _expandInto(
            plugin_event,
            para.data.get('id'),
            state,
            trace_id,
            depth + 1,
            stack,
            budget,
        )
    if isinstance(para, OlivOS.messageAPI.PARA.reply):
        return '[引用消息]'
    if isinstance(para, OlivOS.messageAPI.PARA.node):
        return _parseNode(
            plugin_event,
            para.data,
            state,
            trace_id,
            depth,
            stack,
            budget,
        )
    if str(getattr(para, 'type', '') or '').lower() == 'file':
        file_kind = OlivaAIAgent.media.fileMediaKind(para.data)
        if file_kind == 'video':
            return _mediaPlaceholder(
                state,
                'video',
                para.data.get('url') or para.data.get('file') or para.data.get('path'),
            )
        if file_kind == 'audio':
            return _mediaPlaceholder(
                state,
                'audio',
                para.data.get('url') or para.data.get('file') or para.data.get('path'),
            )
        name = para.data.get('name') or '文件'
        return '[文件:%s]' % str(name)[:120]
    try:
        kind = str(getattr(para, 'type', '') or '')
        if kind in {'face', 'mface'}:
            return '[表情]'
        if kind in {'json', 'xml', 'share'}:
            return '[卡片消息]'
        return para.OP()
    except Exception:
        return ''


def _dictText(segment, plugin_event, state, trace_id, depth, stack, budget):
    segment_type = str(segment.get('type') or '').lower()
    data = segment.get('data') if isinstance(segment.get('data'), dict) else {}
    if segment_type == 'text':
        return str(_first(data, 'text', 'content') or '')
    if segment_type in {'at', 'mention', 'mention_all'}:
        if segment_type == 'mention_all':
            return '@全体成员'
        name = _first(data, 'name', 'nickname', 'user_name', 'qq', 'id', 'user_id')
        return '@%s' % name if name not in [None, ''] else ''
    if segment_type in {'image', 'mface'}:
        return _mediaPlaceholder(state, 'image', _first(data, 'url', 'temp_url', 'file', 'resource_id'))
    if segment_type in {'record', 'audio', 'voice'}:
        return _mediaPlaceholder(state, 'audio', _first(data, 'url', 'temp_url', 'file', 'resource_id'))
    if segment_type == 'video':
        return _mediaPlaceholder(state, 'video', _first(data, 'url', 'temp_url', 'file', 'resource_id'))
    if segment_type == 'forward':
        inline_messages = _inlineMessages(data, include_content=True)
        if inline_messages is not None:
            return _inlineForward(
                plugin_event,
                inline_messages,
                state,
                trace_id,
                depth + 1,
                stack,
                budget,
            )
        return _expandInto(
            plugin_event,
            _first(data, 'id', 'forward_id'),
            state,
            trace_id,
            depth + 1,
            stack,
            budget,
        )
    if segment_type == 'node':
        return _parseNode(plugin_event, data, state, trace_id, depth, stack, budget)
    if segment_type == 'reply':
        quoted = _first(data, 'segments', 'content', 'message')
        if quoted is not None:
            content = _parseContent(plugin_event, quoted, state, trace_id, depth, stack, budget)
            return '[引用上文:%s]' % (content or '未能读取')
        return '[引用消息]'
    if segment_type == 'file':
        file_kind = OlivaAIAgent.media.fileMediaKind(data)
        if file_kind == 'video':
            return _mediaPlaceholder(
                state,
                'video',
                _first(data, 'url', 'temp_url', 'file', 'path', 'resource_id'),
            )
        if file_kind == 'audio':
            return _mediaPlaceholder(
                state,
                'audio',
                _first(data, 'url', 'temp_url', 'file', 'path', 'resource_id'),
            )
        return '[文件:%s]' % str(_first(data, 'name', 'file_name') or '文件')[:120]
    if segment_type in {'face', 'market_face'}:
        return '[表情]'
    if segment_type in {'json', 'xml', 'light_app', 'share'}:
        return '[卡片消息]'
    nested = _first(data, 'content', 'message', 'segments')
    if nested is not None:
        return _parseContent(plugin_event, nested, state, trace_id, depth, stack, budget)
    return '[%s消息]' % segment_type if segment_type else ''


def _parseContent(plugin_event, content, state, trace_id, depth, stack, budget):
    parts = []
    for segment in _messageSegments(content):
        try:
            if isinstance(segment, OlivOS.messageAPI.PARA_templet):
                text = _paraText(segment, plugin_event, state, trace_id, depth, stack, budget)
            elif isinstance(segment, dict):
                text = _dictText(segment, plugin_event, state, trace_id, depth, stack, budget)
            else:
                text = str(segment or '')
            if text:
                parts.append(text)
        except Exception:
            continue
    return ''.join(parts).strip()


def _nodeFields(node):
    if isinstance(node, OlivOS.messageAPI.PARA.node):
        raw = node.data
    elif isinstance(node, OlivOS.messageAPI.Message_templet):
        return None, None, node, None
    else:
        raw = node if isinstance(node, dict) else {}
    if str(raw.get('type') or '').lower() == 'node' and isinstance(raw.get('data'), dict):
        data = raw['data']
    else:
        data = raw
    sender = data.get('sender') if isinstance(data.get('sender'), dict) else {}
    if not sender and isinstance(data.get('author'), dict):
        sender = data['author']
    name = _first(data, 'name', 'nickname', 'username', 'sender_name', 'sender_nick')
    if name in [None, '']:
        name = _first(sender, 'nickname', 'username', 'name', 'sender_name')
    user_id = _first(data, 'uin', 'user_id', 'sender_id', 'member_openid', 'user_openid')
    if user_id in [None, '']:
        user_id = _first(sender, 'user_id', 'id', 'uin', 'member_openid', 'user_openid')
    content = _first(data, 'content', 'message', 'segments', 'raw_message')
    message_id = _first(data, 'id', 'message_id')
    return name, user_id, content, message_id


def _fetchNodeMessage(plugin_event, message_id):
    if message_id in [None, '', '-1', -1]:
        return None, None, None
    try:
        result = plugin_event.get_msg(message_id)
        if not isinstance(result, dict) or not result.get('active'):
            return None, None, None
        data = result.get('data') if isinstance(result.get('data'), dict) else {}
        sender = data.get('sender') if isinstance(data.get('sender'), dict) else {}
        content = data.get('message')
        if content in [None, '']:
            content = data.get('raw_message')
        return (
            content,
            _first(sender, 'nickname', 'name'),
            _first(sender, 'user_id', 'id'),
        )
    except Exception:
        return None, None, None


def _parseNode(plugin_event, node, state, trace_id, depth, stack, budget):
    name, user_id, content, message_id = _nodeFields(node)
    if content is None and message_id not in [None, '', '-1', -1]:
        content, fetched_name, fetched_id = _fetchNodeMessage(plugin_event, message_id)
        name = name or fetched_name
        user_id = user_id or fetched_id
    body = _parseContent(plugin_event, content, state, trace_id, depth, stack, budget)
    sender = str(name or '').strip() or ('用户' if user_id in [None, ''] else '用户(%s)' % str(user_id)[-12:])
    return '%s: %s' % (sender[:120], body or '[空消息]')


def _looksLikeSegments(messages):
    if not messages:
        return False
    segment_types = {
        'text', 'at', 'mention', 'mention_all', 'image', 'mface', 'record', 'audio',
        'voice', 'video', 'reply', 'forward', 'file', 'face', 'market_face', 'json',
        'xml', 'light_app', 'share',
    }
    return all(isinstance(item, dict) and str(item.get('type') or '').lower() in segment_types for item in messages)


def _formatNodes(plugin_event, messages, state, trace_id, depth, stack, budget):
    if _looksLikeSegments(messages):
        messages = [{'name': '用户', 'content': messages}]
    lines = []
    for index, node in enumerate(messages):
        plain_text = _plainNodeText(node)
        if plain_text is not None and _isDuplicateSenderMetadata(node, plain_text):
            _trace('message.forward.sender_metadata_skipped', trace_id, depth=depth)
            continue
        if budget['nodes'] >= MAX_NODES:
            state['truncated'] = True
            lines.append('[后续节点已截断]')
            break
        budget['nodes'] += 1
        state['node_count'] += 1
        if plain_text is not None and CHAT_RECORD_PLACEHOLDER_PATTERN.fullmatch(plain_text):
            data = _nodeData(node)
            inline_messages = _inlineMessages(data)
            if inline_messages is not None:
                lines.append(_inlineForward(
                    plugin_event,
                    inline_messages,
                    state,
                    trace_id,
                    depth + 1,
                    stack,
                    budget,
                ))
                continue
            # QQ 官方等实现可能已把内层节点平铺在该标记之后，此时标记本身不是聊天内容。
            if index + 1 < len(messages):
                _trace('message.forward.nested_flattened', trace_id, depth=depth)
                continue
            _, _, _, message_id = _nodeFields(node)
            if message_id not in [None, '', '-1', -1]:
                expanded = _expandInto(
                    plugin_event,
                    message_id,
                    state,
                    trace_id,
                    depth + 1,
                    stack,
                    budget,
                )
                if expanded != '[合并转发:未能读取]':
                    lines.append(expanded)
                    continue
            lines.append('[嵌套合并转发:未能读取]')
            continue
        lines.append(_parseNode(plugin_event, node, state, trace_id, depth, stack, budget))
    return '\n'.join(line for line in lines if line)


def _expandInto(plugin_event, forward_id, state, trace_id, depth, stack, budget):
    state['forward_count'] += 1
    label = _idLabel(forward_id)
    _trace('message.forward.received', trace_id, depth=depth, forward_id=label)
    if not label:
        state['failed_count'] += 1
        _trace('message.forward.failed', trace_id, depth=depth, reason='missing_id')
        return '[合并转发:未能读取]'
    if depth > MAX_DEPTH:
        state['failed_count'] += 1
        _trace('message.forward.failed', trace_id, depth=depth, forward_id=label, reason='max_depth')
        return '[合并转发:嵌套层级过深]'
    if label in stack:
        state['failed_count'] += 1
        _trace('message.forward.failed', trace_id, depth=depth, forward_id=label, reason='cycle')
        return '[合并转发:循环引用]'
    stack.add(label)
    _trace('message.forward.fetch', trace_id, depth=depth, forward_id=label)
    try:
        result = plugin_event.get_forward_msg(str(forward_id))
        if not isinstance(result, dict) or not result.get('active'):
            raise ValueError('inactive')
        data = result.get('data') if isinstance(result.get('data'), dict) else {}
        messages = data.get('messages')
        if not isinstance(messages, list):
            raise ValueError('messages_not_list')
        content = _formatNodes(plugin_event, messages, state, trace_id, depth, stack, budget)
        block = '[合并转发:\n%s\n]' % (content or '[空转发]')
        if len(block) > MAX_TEXT_CHARS:
            block = block[:MAX_TEXT_CHARS] + '\n[合并转发内容过长，已截断]\n]'
            state['truncated'] = True
        _trace(
            'message.forward.resolved',
            trace_id,
            depth=depth,
            forward_id=label,
            nodes=len(messages),
            text_chars=len(block),
        )
        return block
    except Exception as exc:
        state['failed_count'] += 1
        _trace(
            'message.forward.failed',
            trace_id,
            depth=depth,
            forward_id=label,
            reason='%s: %s' % (type(exc).__name__, exc),
        )
        return '[合并转发:未能读取]'
    finally:
        stack.discard(label)


def expand(plugin_event, forward_id, trace_id=None):
    '''读取一条合并转发，返回纯文本与允许识别的媒体引用。'''
    state = _newState()
    text = _expandInto(plugin_event, forward_id, state, trace_id, 0, set(), {'nodes': 0})
    state['text'] = text
    return state


def mergeInto(result, images, audio_urls, video_urls):
    '''把局部媒体占位索引重定位到当前整条消息。'''
    text = str(result.get('text') or '')

    def merge(pattern, local_items, target, placeholder, fallback):
        def replace(match):
            index = int(match.group(1))
            if index >= len(local_items):
                return fallback
            value = local_items[index]
            if value in target:
                target_index = target.index(value)
            elif len(target) < MAX_MEDIA_ITEMS:
                target.append(value)
                target_index = len(target) - 1
            else:
                return fallback
            return placeholder(target_index)
        return pattern.sub(replace, text)

    text = merge(
        OlivaAIAgent.vision.IMAGE_PLACEHOLDER_PATTERN,
        list(result.get('images') or []),
        images,
        OlivaAIAgent.vision.imagePlaceholder,
        '[图片]',
    )

    def mergeMedia(source, pattern, local_items, target, placeholder, fallback):
        def replace(match):
            index = int(match.group(1))
            if index >= len(local_items):
                return fallback
            value = local_items[index]
            if value in target:
                target_index = target.index(value)
            elif len(target) < MAX_MEDIA_ITEMS:
                target.append(value)
                target_index = len(target) - 1
            else:
                return fallback
            return placeholder(target_index)
        return pattern.sub(replace, source)

    text = mergeMedia(
        text,
        OlivaAIAgent.media.AUDIO_PLACEHOLDER_PATTERN,
        list(result.get('audio_urls') or []),
        audio_urls,
        OlivaAIAgent.media.audioPlaceholder,
        '[语音]',
    )
    return mergeMedia(
        text,
        OlivaAIAgent.media.VIDEO_PLACEHOLDER_PATTERN,
        list(result.get('video_urls') or []),
        video_urls,
        OlivaAIAgent.media.videoPlaceholder,
        '[视频]',
    )
