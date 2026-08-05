# -*- encoding: utf-8 -*-
'''qqGuildv2 QQ 群/C2C 被动回复凭据轮换。'''

import threading
import time


_TTL_SECONDS = 300.0
_MAX_USES = {
    'qq_group': 5,
    'qq_private': 4,
}
_INSTALL_FLAG = '_oliva_ai_passive_reply_installed'
_lock = threading.RLock()
_credentials = {}
_sequence = 0


def _clean(value):
    if value in [None, '', '-1', -1]:
        return None
    return str(value)


def _context(plugin_event):
    try:
        sdk = str(plugin_event.platform.get('sdk', '')).lower()
        if 'qqguildv2' not in sdk:
            return None
        func_type = str(getattr(plugin_event, 'plugin_info', {}).get('func_type', ''))
        if func_type not in ['group_message', 'private_message']:
            return None
        data = plugin_event.data
        extend = getattr(data, 'extend', None)
        if not isinstance(extend, dict) or not extend.get('flag_from_qq', False):
            return None
        flag_direct = bool(extend.get('flag_from_direct', False))
        chat_type = 'qq_private' if flag_direct else 'qq_group'
        chat_id = data.user_id if flag_direct else data.group_id
        chat_id = _clean(chat_id)
        if chat_id is None:
            return None
        bot_info = getattr(plugin_event, 'bot_info', None)
        bot_hash = _clean(getattr(bot_info, 'hash', None)) or 'unity'
        self_id = _clean(getattr(plugin_event, 'base_info', {}).get('self_id'))
        if self_id is not None and _clean(getattr(data, 'user_id', None)) == self_id:
            return None
        message_id = _clean(extend.get('reply_msg_id')) or _clean(
            getattr(data, 'message_id', None),
        )
        return {
            'key': (bot_hash, chat_type, chat_id),
            'bot_hash': bot_hash,
            'chat_type': chat_type,
            'chat_id': chat_id,
            'message_id': message_id,
            'max_uses': _MAX_USES[chat_type],
        }
    except Exception:
        return None


def _prune(now):
    empty_keys = []
    for key, items in _credentials.items():
        expired = [
            message_id
            for message_id, item in items.items()
            if now - item['seen_at'] >= _TTL_SECONDS
        ]
        for message_id in expired:
            items.pop(message_id, None)
        if not items:
            empty_keys.append(key)
    for key in empty_keys:
        _credentials.pop(key, None)


def registerIncoming(plugin_event):
    '''登记当前入站消息；频道消息、机器人出站事件和其他 SDK 不参与。'''
    global _sequence
    context = _context(plugin_event)
    if context is None or context['message_id'] is None:
        return context
    now = time.monotonic()
    with _lock:
        _prune(now)
        _sequence += 1
        items = _credentials.setdefault(context['key'], {})
        current = items.get(context['message_id'])
        if current is None:
            items[context['message_id']] = {
                'seen_at': now,
                'order': _sequence,
                'uses': 0,
            }
        else:
            current['seen_at'] = now
            current['order'] = _sequence
    return context


def _sdkUses(plugin_event, context, message_id):
    '''读取 OlivOS 已登记的 SDK 序号，不写入 SDK 状态。'''
    try:
        import OlivOS

        sdk = OlivOS.qqGuildv2SDK
        event_action = sdk.event_action
        key = event_action._get_reply_seq_key(
            plugin_event,
            context['chat_type'],
            context['chat_id'],
            message_id,
        )
        now = time.monotonic()
        with sdk.sdkMsgidinfoLock:
            cache_data = sdk.sdkMsgidinfo.get(key)
            if cache_data is None or now - cache_data['created_at'] >= _TTL_SECONDS:
                return 0
            return max(0, int(cache_data.get('seq', 0)))
    except Exception:
        return 0


def _reserve(plugin_event, context):
    now = time.monotonic()
    with _lock:
        _prune(now)
        items = _credentials.get(context['key'], {})
        candidates = sorted(
            (
                (item['seen_at'], item['order'], message_id, item)
                for message_id, item in items.items()
                if (
                    item['uses'] + _sdkUses(plugin_event, context, message_id)
                    < context['max_uses']
                )
            ),
            reverse=True,
        )
        if not candidates:
            return None
        _seen_at, _order, message_id, item = candidates[0]
        item['uses'] += 1
        return {
            'message_id': message_id,
            'use': item['uses'],
            'max_uses': context['max_uses'],
        }


def _addUses(context, message_id, count):
    if count <= 0:
        return
    with _lock:
        item = _credentials.get(context['key'], {}).get(str(message_id))
        if item is not None:
            item['uses'] = min(context['max_uses'], item['uses'] + int(count))


def _markExhausted(context, message_id):
    with _lock:
        item = _credentials.get(context['key'], {}).get(str(message_id))
        if item is not None:
            item['uses'] = context['max_uses']


def _resultMessageCount(result):
    if not isinstance(result, dict):
        return 1
    data = result.get('data') if isinstance(result.get('data'), dict) else {}
    message_ids = data.get('message_ids')
    if isinstance(message_ids, list) and message_ids:
        return len(message_ids)
    if data.get('message_id') not in [None, '', '-1', -1]:
        return 1
    return 1


def _hasPassiveFallback(value, visited=None):
    if visited is None:
        visited = set()
    if isinstance(value, list):
        return any(_hasPassiveFallback(item, visited) for item in value)
    if not isinstance(value, dict) or id(value) in visited:
        return False
    visited.add(id(value))
    if value.get('passive_fallback') not in [None, {}, []]:
        return True
    if value.get('passive_fallbacks'):
        return True
    return any(_hasPassiveFallback(item, visited) for item in value.values())


def _trace(event, context, selected=None, active=False, reason=None, trace_id=None):
    try:
        import OlivaAIAgent

        OlivaAIAgent.conf.traceLog(
            OlivaAIAgent.conf.gProc,
            event,
            trace_id,
            active=active,
            chat_id=context['chat_id'],
            chat_type=context['chat_type'],
            message_id=None if selected is None else selected['message_id'],
            reason=reason,
            use=None if selected is None else selected['use'],
        )
    except Exception:
        pass


def _withExtend(plugin_event, message_id, disabled, callback):
    data = getattr(plugin_event, 'data', None)
    old_extend = getattr(data, 'extend', None)
    if data is None or not isinstance(old_extend, dict):
        return callback()
    extend = dict(old_extend)
    if disabled:
        extend.pop('reply_msg_id', None)
        extend['qq_passive_reply_disabled'] = True
    else:
        extend['reply_msg_id'] = str(message_id)
        extend.pop('qq_passive_reply_disabled', None)
    data.extend = extend
    try:
        return callback()
    finally:
        data.extend = old_extend


def sendWithCredentials(
    plugin_event,
    passive_sender,
    active_sender,
    trace_id=None,
):
    '''选择一个可用凭据发送；所有候选耗尽后才调用 active_sender。'''
    context = _context(plugin_event)
    if context is None:
        return passive_sender(None)
    # 直接调用 Markdown 等插件入口时可能尚未经过 main.Event；只在未安装 wrapper
    # 的事件上登记一次，避免后台任务每次发送都刷新旧消息的五分钟有效期。
    if not getattr(plugin_event, _INSTALL_FLAG, False):
        registerIncoming(plugin_event)
    selected = _reserve(plugin_event, context)
    if selected is None:
        _trace(
            'message.passive_reply.active_fallback',
            context,
            active=True,
            reason='no_recent_credential',
            trace_id=trace_id,
        )
        return active_sender()

    if selected['message_id'] != context.get('message_id'):
        _trace(
            'message.passive_reply.rollover',
            context,
            selected=selected,
            reason='current_credential_exhausted',
            trace_id=trace_id,
        )
    result = passive_sender(selected['message_id'])
    _addUses(
        context,
        selected['message_id'],
        _resultMessageCount(result) - 1,
    )
    if _hasPassiveFallback(result):
        _markExhausted(context, selected['message_id'])
        _trace(
            'message.passive_reply.platform_fallback',
            context,
            selected=selected,
            active=True,
            reason='platform_rejected_credential',
            trace_id=trace_id,
        )
    return result


def _replyArgs(args, kwargs):
    flag_log = kwargs.get('flag_log', args[0] if len(args) >= 1 else True)
    remote = kwargs.get('remote', args[1] if len(args) >= 2 else False)
    return bool(flag_log), bool(remote)


def install(plugin_event, register=True):
    '''包装当前 OlivaAIAgent 事件的 reply，不改变其他插件或 OlivOS。'''
    context = registerIncoming(plugin_event) if register else _context(plugin_event)
    if context is None or getattr(plugin_event, _INSTALL_FLAG, False):
        return plugin_event
    original_reply = plugin_event.reply
    original_send = plugin_event.send

    def wrapped_reply(message, *args, **kwargs):
        flag_log, remote = _replyArgs(args, kwargs)
        if remote:
            return original_reply(message, *args, **kwargs)

        def passive_sender(message_id):
            return _withExtend(
                plugin_event,
                message_id,
                False,
                lambda: original_reply(message, *args, **kwargs),
            )

        def active_sender():
            if context['chat_type'] == 'qq_private':
                return original_send(
                    'private',
                    context['chat_id'],
                    message,
                    flag_log=flag_log,
                )
            return original_send(
                'group',
                context['chat_id'],
                message,
                flag_log=flag_log,
            )

        return sendWithCredentials(plugin_event, passive_sender, active_sender)

    plugin_event.reply = wrapped_reply
    setattr(plugin_event, _INSTALL_FLAG, True)
    return plugin_event


def prepareClone(plugin_event):
    '''事件浅克隆后重绑 wrapper，避免闭包继续操作原事件。'''
    # coreLogger 已经先把 clone 的 reply 绑定为新的日志 wrapper；这里只移除
    # passive 标记，再把新的被动 wrapper 叠在日志 wrapper 外面。
    for name in (_INSTALL_FLAG,):
        try:
            delattr(plugin_event, name)
        except Exception:
            pass
    return install(plugin_event, register=False)


def sendMarkdown(plugin_event, sender, kwargs, trace_id=None):
    '''让 qqGuildv2 Markdown 与普通 reply 共用同一组被动凭据。'''
    base_kwargs = dict(kwargs)

    def passive_sender(message_id):
        call_kwargs = dict(base_kwargs)
        if message_id is not None:
            call_kwargs['msg_id'] = str(message_id)
        return sender(**call_kwargs)

    def active_sender():
        return _withExtend(
            plugin_event,
            None,
            True,
            lambda: sender(**base_kwargs),
        )

    return sendWithCredentials(
        plugin_event,
        passive_sender,
        active_sender,
        trace_id=trace_id,
    )


def resetForTests():
    global _sequence
    with _lock:
        _credentials.clear()
        _sequence = 0
