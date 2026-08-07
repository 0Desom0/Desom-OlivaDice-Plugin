# -*- encoding: utf-8 -*-
'''把本插件的出站消息补入 OlivaDiceCore msgHook，供 OlivaDiceLogger 记录。'''

import contextlib
import copy
import inspect
import os
import re
import sys
import threading
from urllib.parse import unquote, urlparse

import OlivOS
import OlivaAIAgent

_hint_local = threading.local()
_INSTALL_FLAG = '_oliva_ai_core_logger_installed'
_SNAPSHOT_FLAG = '_oliva_ai_event_snapshot'


def enabled():
    return bool(OlivaAIAgent.conf.get('olivadice_logger', 'enabled', default=True))


def _core():
    try:
        import OlivaDiceCore

        hook = OlivaDiceCore.crossHook.dictHookFunc.get('msgHook')
        if callable(hook):
            return OlivaDiceCore
    except Exception:
        pass
    return None


def getStatus(Proc=None):
    core = _core()
    plugins = OlivaAIAgent.conf.loadedPlugins(Proc or OlivaAIAgent.conf.gProc)
    logger_loaded = any(str(item).split('(', 1)[0] == 'OlivaDiceLogger' for item in plugins)
    logger_loaded = logger_loaded or 'OlivaDiceLogger' in sys.modules
    return {
        'enabled': enabled(),
        'core_ready': core is not None,
        'logger_loaded': logger_loaded,
        'active': enabled() and core is not None,
    }


@contextlib.contextmanager
def messageHint(text):
    '''给媒体发送提供可读日志正文；仅影响当前线程中的下一次发送。'''
    old = getattr(_hint_local, 'text', None)
    _hint_local.text = str(text)
    try:
        yield
    finally:
        if old is None:
            try:
                del _hint_local.text
            except AttributeError:
                pass
        else:
            _hint_local.text = old


def _hint():
    return getattr(_hint_local, 'text', None)


def _sendSucceeded(result):
    return not isinstance(result, dict) or bool(result.get('active', False))


def _botHash(plugin_event):
    bot_info = getattr(plugin_event, 'bot_info', None)
    return getattr(bot_info, 'hash', None) if bot_info is not None else None


def _imageDescription(plugin_event, file_ref):
    try:
        parsed = urlparse(str(file_ref or ''))
        path = unquote(parsed.path) if parsed.scheme else unquote(str(file_ref or ''))
        file_name = os.path.basename(path.replace('\\', '/'))
        data = OlivaAIAgent.vision.imageCacheMap(_botHash(plugin_event)).get(file_name, {})
        if isinstance(data, dict):
            content = str(data.get('content') or data.get('intent') or '').strip()
            if content:
                return content.replace(']', '】')[:160]
    except Exception:
        pass
    return '图片'


def readableMessage(plugin_event, message, hint=None):
    '''把出站消息转成团日志可读文本，不写入图片/音频本地路径。'''
    if hint not in [None, '']:
        return str(hint)
    try:
        if isinstance(message, OlivOS.messageAPI.Message_templet):
            message_obj = message
            raw = message.get('olivos_string')
        else:
            raw = str(message)
            mode = 'olivos_string' if '[OP:' in raw else 'old_string'
            message_obj = OlivOS.messageAPI.Message_templet(mode, raw)
        parts = []
        for para in message_obj.data:
            if isinstance(para, OlivOS.messageAPI.PARA.reply):
                continue
            if isinstance(para, OlivOS.messageAPI.PARA.text):
                parts.append(str(para.data.get('text', '')))
            elif isinstance(para, OlivOS.messageAPI.PARA.image):
                ref = para.data.get('file') or para.data.get('url') or ''
                parts.append('[图片：%s]' % _imageDescription(plugin_event, ref))
            elif isinstance(para, OlivOS.messageAPI.PARA.record):
                parts.append('[语音:语音消息]')
            elif isinstance(para, OlivOS.messageAPI.PARA.video):
                parts.append('[视频:视频消息]')
            else:
                try:
                    parts.append(para.get_string_by_key('OP'))
                except Exception:
                    parts.append(str(para))
        result = ''.join(parts).strip()
        if result:
            return result
    except Exception:
        raw = str(message)
    raw = re.sub(r'\[(?:CQ|OP):reply[^\]]*\]', '', str(raw), flags=re.I)
    raw = re.sub(
        r'\[(?:CQ|OP):image[^\]]*\]',
        lambda match: '[图片：%s]' % _imageDescription(
            plugin_event,
            (re.search(r'(?:file|url)=([^,\]]+)', match.group(0), re.I) or [None, ''])[1],
        ),
        raw,
        flags=re.I,
    )
    raw = re.sub(r'\[(?:CQ|OP):record[^\]]*\]', '[语音:语音消息]', raw, flags=re.I)
    raw = re.sub(r'\[(?:CQ|OP):video[^\]]*\]', '[视频:视频消息]', raw, flags=re.I)
    return raw.strip()


def _sender(core, plugin_event):
    bot_info = getattr(plugin_event, 'bot_info', None)
    bot_hash = getattr(bot_info, 'hash', None)
    bot_id = getattr(bot_info, 'id', -1)
    name = getattr(bot_info, 'name', '') or 'Bot'
    try:
        name = core.msgCustom.dictStrCustomDict[bot_hash]['strBotName']
    except Exception:
        pass
    return {'name': str(name), 'id': bot_id}


def _eventTargets(plugin_event):
    data = getattr(plugin_event, 'data', None)
    return [
        getattr(data, 'host_id', None),
        getattr(data, 'group_id', None),
        getattr(data, 'user_id', None),
    ]


def record(plugin_event, message, func_type='reply', targets=None, hint=None):
    if not enabled():
        return False
    core = _core()
    if core is None or plugin_event is None:
        return False
    log_text = readableMessage(plugin_event, message, hint=hint)
    if not log_text:
        return False
    try:
        core.crossHook.dictHookFunc['msgHook'](
            plugin_event,
            str(func_type),
            _sender(core, plugin_event),
            list(targets) if targets is not None else _eventTargets(plugin_event),
            log_text,
        )
        return True
    except Exception as e:
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'logger.bridge.failed',
            error='%s: %s' % (type(e).__name__, e),
        )
        return False


def _recordReply(plugin_event, message, result):
    if _sendSucceeded(result):
        record(plugin_event, message, func_type='reply', hint=_hint())


def _recordSend(plugin_event, send_type, target_id, message, host_id, result):
    if not _sendSucceeded(result):
        return
    if str(send_type) == 'group':
        targets = [host_id, target_id, None]
        record(plugin_event, message, func_type='send_group', targets=targets, hint=_hint())
    elif str(send_type) == 'private':
        targets = [host_id, None, target_id]
        record(plugin_event, message, func_type='send_private', targets=targets, hint=_hint())


def install(plugin_event):
    '''包装当前事件的 reply/send；发送行为不变，只在成功后调用 Core 的 msgHook。'''
    if plugin_event is None or getattr(plugin_event, _INSTALL_FLAG, False):
        return plugin_event
    original_reply = plugin_event.reply
    original_send = plugin_event.send

    def wrapped_reply(message, *args, **kwargs):
        result = original_reply(message, *args, **kwargs)
        _recordReply(plugin_event, message, result)
        return result

    def wrapped_send(send_type, target_id, message, host_id=None, *args, **kwargs):
        result = original_send(send_type, target_id, message, host_id, *args, **kwargs)
        _recordSend(plugin_event, send_type, target_id, message, host_id, result)
        return result

    plugin_event.reply = wrapped_reply
    plugin_event.send = wrapped_send
    setattr(plugin_event, _INSTALL_FLAG, True)
    return plugin_event


def prepareClone(plugin_event):
    '''copy.copy 后移除复制来的闭包，再按克隆事件重新包装。'''
    for name in ('reply', 'send', _INSTALL_FLAG):
        try:
            delattr(plugin_event, name)
        except Exception:
            pass
    return install(plugin_event)


def snapshotEvent(plugin_event):
    '''冻结后台任务所需的事件上下文，避免后续插件分发改写当前插件信息。'''
    if plugin_event is None or getattr(plugin_event, _SNAPSHOT_FLAG, False):
        return plugin_event
    passive_reply_installed = bool(getattr(
        plugin_event,
        '_oliva_ai_passive_reply_installed',
        False,
    ))
    try:
        snapshot = copy.copy(plugin_event)
    except Exception:
        return plugin_event

    for name in ('plugin_info', 'platform', 'base_info'):
        value = getattr(plugin_event, name, None)
        if isinstance(value, dict):
            setattr(snapshot, name, dict(value))

    data = getattr(plugin_event, 'data', None)
    if data is not None:
        try:
            snapshot.data = copy.copy(data)
            for name in ('sender', 'extend'):
                value = getattr(data, name, None)
                if isinstance(value, dict):
                    setattr(snapshot.data, name, dict(value))
        except Exception:
            pass

    inde_api = getattr(plugin_event, 'indeAPI', None)
    if inde_api is not None:
        try:
            snapshot.indeAPI = copy.copy(inde_api)
            if hasattr(snapshot.indeAPI, 'event'):
                snapshot.indeAPI.event = snapshot
        except Exception:
            pass

    setattr(snapshot, _SNAPSHOT_FLAG, True)
    if not callable(getattr(snapshot, 'reply', None)) or not callable(getattr(snapshot, 'send', None)):
        return snapshot
    snapshot = prepareClone(snapshot)
    if passive_reply_installed:
        snapshot = OlivaAIAgent.passiveReply.prepareClone(snapshot)
    return snapshot


def _toolCallValues(ctx, path, args, kwargs):
    '''按真实接口签名还原参数名，兼容模型使用位置参数调用发送接口。'''
    values = dict(kwargs) if isinstance(kwargs, dict) else {}
    try:
        target = OlivaAIAgent.introspection._resolve(ctx, path)
        call_args, call_kwargs, error, _normalized = OlivaAIAgent.introspection._prepare_call(
            ctx,
            target,
            args if isinstance(args, list) else [],
            values,
        )
        if error is None:
            bound = inspect.signature(target).bind(*call_args, **call_kwargs)
            values = dict(bound.arguments)
    except Exception:
        pass
    return values


def _toolCallMessage(values, args):
    markdown = values.get('markdown')
    if isinstance(markdown, dict) and markdown.get('content') not in [None, '']:
        return markdown.get('content')
    for key in ('message', 'content', 'text', 'msg'):
        if values.get(key) not in [None, '']:
            return values.get(key)

    positional = args if isinstance(args, list) else []
    for value in reversed(positional):
        if isinstance(value, dict):
            for key in ('content', 'message', 'text', 'msg'):
                if value.get(key) not in [None, '']:
                    return value.get(key)
    chat_types = {'group', 'private', 'qq_group', 'qq_private', 'guild_channel', 'guild_private'}
    for value in reversed(positional):
        if isinstance(value, str) and value.strip() and value.strip().lower() not in chat_types:
            return value
    return None


def _toolCallTargets(ctx, plugin_event, values):
    chat_type = str(
        values.get('chat_type') or values.get('send_type') or values.get('target_type') or '',
    ).lower()
    chat_id = values.get('chat_id') or values.get('target_id')
    if values.get('group_id') not in [None, '']:
        chat_type = 'group'
        chat_id = values.get('group_id')
    elif values.get('user_id') not in [None, '']:
        chat_type = 'private'
        chat_id = values.get('user_id')
    elif values.get('channel_id') not in [None, '']:
        chat_type = 'group'
        chat_id = values.get('channel_id')
    if chat_id in [None, '', 'current', 'CURRENT_CHANNEL']:
        current = OlivaAIAgent.introspection.current_chat_context(ctx)
        chat_type = str(current.get('chat_type', chat_type)).lower()
        chat_id = current.get('chat_id')
    host_id = values.get('host_id')
    if host_id in [None, '']:
        host_id = getattr(getattr(plugin_event, 'data', None), 'host_id', None)
    if 'private' in chat_type:
        return 'send_private', [host_id, None, chat_id]
    return 'send_group', [host_id, chat_id, None]


def _toolResultMessageIds(result):
    '''递归提取工具发送结果中的真实消息 ID，兼容 SDK 合并/嵌套响应。'''
    try:
        return OlivaAIAgent.ambient._sendResultMessageIds(result)
    except Exception:
        return []


def _toolResultMessageIndexes(result):
    try:
        return OlivaAIAgent.ambient._sendResultMessageIndexes(result)
    except Exception:
        return []


def _toolReferenceId(values):
    if not isinstance(values, dict):
        return None
    for key in ('quote_msg_id', 'reference_message_id', 'reply_msg_id'):
        value = values.get(key)
        if value not in [None, '', '-1', -1]:
            return str(value)
    reference = values.get('message_reference')
    if isinstance(reference, dict) and reference.get('message_id') not in [None, '', '-1', -1]:
        return str(reference['message_id'])
    return None


def _recordToolOutgoing(ctx, plugin_event, values, message, result):
    '''把 AI 通过运行时接口直接发送的消息写入插件注册表和潜行历史。'''
    message_ids = _toolResultMessageIds(result)
    message_indexes = _toolResultMessageIndexes(result)
    if not message_ids and not message_indexes:
        return
    reference_id = _toolReferenceId(values)
    OlivaAIAgent.identifiers.recordOutgoing(
        plugin_event,
        message,
        message_ids,
        reference_message_id=reference_id,
        message_indexes=message_indexes,
    )
    try:
        func_type, targets = _toolCallTargets(ctx, plugin_event, values)
        if (
            not ctx.get('_record_tool_outgoing_history')
            or func_type != 'send_group'
            or str(targets[1]) != str(getattr(plugin_event.data, 'group_id', ''))
        ):
            return
        OlivaAIAgent.ambient.addSelfReply(
            plugin_event.platform.get('platform', ''),
            plugin_event.data.group_id,
            str(message),
            message_ids=message_ids,
            message_indexes=message_indexes,
        )
    except Exception:
        pass


def recordToolCall(ctx, path, args, kwargs, result):
    '''记录绕过 Event.send/reply 的运行时消息接口，主要覆盖 Markdown。'''
    if not isinstance(result, dict) or not result.get('active'):
        return False
    path_low = str(path).lower()
    values = _toolCallValues(ctx, path, args, kwargs)
    message = _toolCallMessage(values, args)
    if message in [None, ''] or (
        path_low not in ('event.reply', 'event.send')
        and not any(word in path_low for word in ('message', 'markdown', 'send'))
    ):
        return False
    plugin_event = ctx.get('plugin_event') if isinstance(ctx, dict) else None
    if plugin_event is None:
        return False
    _recordToolOutgoing(ctx, plugin_event, values, message, result)
    if path_low in ('event.reply', 'event.send'):
        return False
    func_type, targets = _toolCallTargets(ctx, plugin_event, values)
    return record(plugin_event, message, func_type=func_type, targets=targets)
