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
_bridge_local = threading.local()
_bridge_install_lock = threading.RLock()
_INSTALL_FLAG = '_oliva_ai_core_logger_installed'
_SNAPSHOT_FLAG = '_oliva_ai_event_snapshot'
_BRIDGE_FLAG = '_oliva_ai_msg_bridge_installed'


def enabled():
    return bool(OlivaAIAgent.conf.get('olivadice_logger', 'enabled', default=True))


def blockWhenLogOnEnabled():
    return bool(OlivaAIAgent.conf.get('olivadice_logger', 'block_when_log_on', default=False))


def _coreModule():
    """Import OlivaDiceCore only; logEnable read does not need Logger msgHook."""
    try:
        import OlivaDiceCore

        return OlivaDiceCore
    except Exception:
        return None


def _core():
    try:
        import OlivaDiceCore

        hook = OlivaDiceCore.crossHook.dictHookFunc.get('msgHook')
        if callable(hook):
            return OlivaDiceCore
    except Exception:
        pass
    return None


def _groupHagId(plugin_event):
    data = getattr(plugin_event, 'data', None)
    if data is None:
        return None
    group_id = getattr(data, 'group_id', None)
    if group_id in (None, ''):
        return None
    host_id = getattr(data, 'host_id', None)
    if host_id not in (None, ''):
        return '%s|%s' % (str(host_id), str(group_id))
    return str(group_id)


def isGroupLogOn(plugin_event):
    """Read OlivaDiceCore group logEnable (.log on / off). No Core => False."""
    core = _coreModule()
    if core is None:
        return False
    try:
        hag_id = _groupHagId(plugin_event)
        bot_hash = _botHash(plugin_event)
        if hag_id is None or bot_hash in (None, ''):
            return False
        platform = plugin_event.platform.get('platform') if isinstance(plugin_event.platform, dict) else None
        if not platform:
            return False
        return bool(
            core.userConfig.getUserConfigByKey(
                userId=hag_id,
                userType='group',
                platform=platform,
                userConfigKey='logEnable',
                botHash=bot_hash,
                default=False,
            )
        )
    except Exception:
        return False


def shouldBlockForLogOn(plugin_event):
    """When switch is on and group is logging, skip group AI / preflight."""
    return blockWhenLogOnEnabled() and isGroupLogOn(plugin_event)


def getStatus(Proc=None):
    core = _core()
    core_mod = _coreModule()
    plugins = OlivaAIAgent.conf.loadedPlugins(Proc or OlivaAIAgent.conf.gProc)
    logger_loaded = any(str(item).split('(', 1)[0] == 'OlivaDiceLogger' for item in plugins)
    logger_loaded = logger_loaded or 'OlivaDiceLogger' in sys.modules
    bridged = False
    if core is not None:
        bridged = bool(getattr(core.crossHook.dictHookFunc.get('msgHook'), _BRIDGE_FLAG, False))
    return {
        'enabled': enabled(),
        'core_ready': core is not None,
        'core_installed': core_mod is not None,
        'logger_loaded': logger_loaded,
        'active': enabled() and core is not None,
        'bridge_enabled': bridgeEnabled(),
        'bridge_installed': bridged,
        'block_when_log_on': blockWhenLogOnEnabled(),
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
    previous_skip = getattr(_bridge_local, 'skip', False)
    try:
        # 自己补记的消息不再经反向桥接写回历史，避免与 addSelfReply 重复。
        _bridge_local.skip = True
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
    finally:
        _bridge_local.skip = previous_skip


def bridgeEnabled():
    return bool(OlivaAIAgent.conf.get(
        'olivadice_logger', 'record_other_plugin_messages', default=True,
    ))


def _bridgeRecordable(func_type):
    '''只接同账号其他插件发往群聊的出站消息；recv 已由本插件事件入口记录。'''
    return str(func_type) in ('reply', 'send_group')


def _bridgeMessage(event, func_type, sender, targets, message):
    if getattr(_bridge_local, 'skip', False) or not bridgeEnabled():
        return False
    if not _bridgeRecordable(func_type) or event is None:
        return False
    group_id = targets[1] if isinstance(targets, (list, tuple)) and len(targets) > 1 else None
    if group_id in [None, '', '-1', -1]:
        return False
    try:
        platform = str(event.platform['platform'])
    except Exception:
        return False
    conf = OlivaAIAgent.conf
    if not conf.get('enable', 'global', default=True):
        return False
    if not conf.isWhitelisted(platform, group_id) or not conf.isGroupEnabled(platform, group_id):
        return False
    if not conf.isAmbientEnabled(platform, group_id):
        # 潜行关闭的群本来就不积累群上下文，这里保持一致，不单独留下骰子消息。
        return False
    text = readableMessage(event, message)
    if not text:
        return False
    bot_hash = _botHash(event) or 'unity'
    source_name = '骰系插件'
    if isinstance(sender, dict) and str(sender.get('name') or '').strip():
        source_name = '骰系插件(%s)' % str(sender['name']).strip()
    recorded = OlivaAIAgent.ambient.addPluginMessage(
        platform,
        group_id,
        bot_hash,
        text,
        source_name=source_name,
        user_id=sender.get('id') if isinstance(sender, dict) else None,
    )
    if recorded:
        # 群滚动缓冲同样补上，让显式 .ai 对话里的"最近群聊记录"也能看到骰点结果。
        try:
            OlivaAIAgent.memory.bufferAppend(
                platform,
                group_id,
                sender.get('id') if isinstance(sender, dict) else '',
                source_name,
                text,
            )
        except Exception:
            pass
        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            'logger.bridge.plugin_message',
            func_type=str(func_type),
            group_id=str(group_id),
            chars=len(text),
        )
    return recorded


def installMessageBridge():
    '''包一层 Core 的 msgHook：其他骰系插件发出的群消息也进潜行上下文，不改变原有日志行为。'''
    core = _core()
    if core is None:
        return False
    with _bridge_install_lock:
        hook = core.crossHook.dictHookFunc.get('msgHook')
        if not callable(hook) or getattr(hook, _BRIDGE_FLAG, False):
            return False

        def bridged(event, funcType, sender, dectData, message):
            # 先让原 hook（通常是 OlivaDiceLogger）正常记团日志，再补进本插件上下文。
            result = hook(event, funcType, sender, dectData, message)
            try:
                _bridgeMessage(event, funcType, sender, dectData, message)
            except Exception as e:
                OlivaAIAgent.conf.traceLog(
                    OlivaAIAgent.conf.gProc,
                    'logger.bridge.context_failed',
                    error='%s: %s' % (type(e).__name__, e),
                )
            return result

        setattr(bridged, _BRIDGE_FLAG, True)
        setattr(bridged, '_oliva_ai_original_hook', hook)
        core.crossHook.dictHookFunc['msgHook'] = bridged
        return True


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
