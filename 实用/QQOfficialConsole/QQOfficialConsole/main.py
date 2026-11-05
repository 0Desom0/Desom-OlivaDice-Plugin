"""QQ 官方机器人控制台的宿主事件入口。"""

import datetime
import logging
import re
import threading
import time

from . import media, outgoing, passive, roster, store, webui

_log = logging.getLogger('QQOfficialConsole')
_guard = threading.RLock()
_state = None
_FACE_RE = re.compile(r'<faceType\s*=\s*[^,>]+(?:,[^>]*)?\s*/?>')


def _strip_face_tags(text):
    """剥离 QQ 原始表情标签；SDK 的正则优先，宿主缺失时本地兜底。"""
    try:
        from OlivOS.adapter.qqGuild.qqGuildv2SDKCommon import _strip_qq_face_tags
        stripped, _ = _strip_qq_face_tags(text)
        return stripped
    except Exception:
        return _FACE_RE.sub('', text)


def _render_text(text, raw):
    """@ 占位符替换成 mentions 里的昵称；表情标签替换为 [表情]。"""
    mentions = raw.get('mentions')
    if isinstance(mentions, list):
        names = {}
        for item in mentions:
            if isinstance(item, dict):
                ident = str(item.get('id') or item.get('member_openid') or '')
                name = item.get('username') or item.get('nick')
                if ident and isinstance(name, str) and name:
                    names[ident] = name
        # QQ 正文里的 @ 占位符是 <@member_openid>；已知的换成昵称，未知的退化成「@成员」，
        # 绝不把原始 <@...> 标记漏给用户。
        text = re.sub(r'<@([^<>]+)>', lambda m: '@' + names.get(m.group(1).strip(), '成员'), text)
    stripped = _strip_face_tags(text)
    if stripped != text and _FACE_RE.search(text):
        text = _FACE_RE.sub('[表情]', text)
    return text.strip()


def _initialise(proc):
    global _state
    with _guard:
        if _state is None:
            database = store.Store()
            pool = passive.PassivePool(database)
            members = roster.Roster(database)
            images = media.MediaManager()
            images.cleanup()
            _state = (database, pool, members, images, webui.Bridge(database, pool, members, images, proc))
            # 挂「其他插件发出的消息」记录钩子：qqGuildv2 所有发送的最终出口。
            outgoing.install(_state)
        return _state


def _valid(event):
    return bool(
        event
        and getattr(event, 'platform', {}).get('sdk') == 'qqGuildv2_link'
        and getattr(getattr(event, 'bot_info', None), 'hash', None)
    )


def _raw(event):
    extend = getattr(event.data, 'extend', {}) or {}
    data = extend.get('qq_event_data')
    if isinstance(data, dict):
        return data
    packet = getattr(getattr(getattr(event, 'sdk_event', None), 'payload', None), 'data', None)
    data = getattr(packet, 'd', None)
    return data if isinstance(data, dict) else {}


def _event_type(event):
    packet = getattr(getattr(getattr(event, 'sdk_event', None), 'payload', None), 'data', None)
    return getattr(packet, 't', None)


def _at_bot(extend, event, raw):
    """这条群消息是不是 @ 了机器人。

    OliviaDice 这套官方适配器不一定给 `qq_at_bot`：有的群把「@机器人」当成普通
    GROUP_MESSAGE_CREATE 下发，只在 mentions 里带 `is_you: true`。
    两条路都要认，否则那些群的「@我」永远统计不到、跳转也找不到目标。
    """
    if extend.get('qq_at_bot') is True:
        return True
    if _event_type(event) == 'GROUP_AT_MESSAGE_CREATE':
        return True
    mentions = (raw or {}).get('mentions')
    if isinstance(mentions, list):
        for item in mentions:
            if isinstance(item, dict) and item.get('is_you') is True:
                return True
    return False


def _timestamp(value):
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())
        except ValueError:
            pass
    return int(time.time())


def _incoming(event, proc, group):
    if not _valid(event):
        return
    data = event.data
    extend = getattr(data, 'extend', {}) or {}
    if not extend.get('flag_from_qq'):
        return
    raw = _raw(event)
    bot = event.bot_info.hash
    kind = 'qq_group' if group else 'qq_private'
    chat_id = str(getattr(data, 'group_id' if group else 'user_id', '') or '')
    if not chat_id:
        return
    sender = getattr(data, 'sender', {}) or {}
    sender_id = str(getattr(data, 'user_id', '') or '')
    name = sender.get('nickname') or sender.get('name') or sender_id
    created = _timestamp(raw.get('timestamp'))
    msg_id = raw.get('id') or getattr(data, 'message_id', None)
    text = _render_text(str(raw.get('content') or ''), raw)
    attachments = raw.get('attachments') or []
    msg_kind = 'media' if attachments else 'text'
    message = {
        'direction': 'in',
        'platform_message_id': str(msg_id) if msg_id else None,
        'ref_idx': extend.get('qq_msg_idx'),
        'reply_to': extend.get('qq_reference_message_id'),
        'sender_id': sender_id,
        'sender_name': name,
        'msg_kind': msg_kind,
        'content_text': text,
        'content_json': {'text': text, 'attachments': attachments},
        'created_at': created,
        'is_mention': group and _at_bot(extend, event, raw),
        'raw_event_json': raw,
    }
    member = (
        {'member_openid': sender_id, 'name': name, 'role': sender.get('role'), 'last_seen_at': created}
        if sender_id
        else None
    )
    token = (
        {'id_type': 'msg_id', 'id_value': str(msg_id), 'source_event': _event_type(event), 'created_at': created}
        if msg_id
        else None
    )
    database = _initialise(proc)[0]
    database.add_message(bot, kind, chat_id, message, member=member, token=token)
    if not group and name and name != sender_id:
        database.upsert_chat(bot, kind, chat_id, display_name=name)


def _member_event(event, proc, increase):
    if not _valid(event) or not (getattr(event.data, 'extend', {}) or {}).get('flag_from_qq'):
        return
    database, pool, members, _, bridge = _initialise(proc)
    bot = event.bot_info.hash
    group = str(getattr(event.data, 'group_id', '') or '')
    if not group:
        return
    typ = _event_type(event)
    fields = {'left_group': int(typ == 'GROUP_DEL_ROBOT')} if typ in ('GROUP_ADD_ROBOT', 'GROUP_DEL_ROBOT') else {}
    database.upsert_chat(bot, 'qq_group', group, **fields)
    raw = _raw(event)
    if typ == 'GROUP_ADD_ROBOT':
        database.enqueue_group_info(bot, group, enqueued_at=_timestamp(raw.get('timestamp')))
        bridge.wake_group_info()
    event_id = (getattr(event.data, 'extend', {}) or {}).get('event_id')
    if typ in ('GROUP_ADD_ROBOT', 'GROUP_MEMBER_ADD') and event_id:
        pool.add(bot, 'qq_group', group, 'event_id', str(event_id), typ, _timestamp(raw.get('timestamp')))
    user = str(getattr(event.data, 'user_id', '') or '')
    if typ == 'GROUP_MEMBER_REMOVE' and user:
        members.remove_member(bot, 'qq_group', group, user)
    elif typ == 'GROUP_MEMBER_ADD' and user:
        members.upsert_member(bot, 'qq_group', group, user)


def _button(event, proc):
    if not _valid(event):
        return
    ext = getattr(event.data, 'extend', {}) or {}
    typ, chat, event_id = ext.get('chat_type'), ext.get('chat_id'), ext.get('event_id')
    if typ not in ('qq_group', 'qq_private') or not chat or not event_id:
        return
    database, pool, _, _, _ = _initialise(proc)
    bot = event.bot_info.hash
    database.upsert_chat(bot, typ, str(chat))
    pool.add(bot, typ, str(chat), 'event_id', str(event_id), 'INTERACTION_CREATE')


def _recall(event, proc, group):
    if not _valid(event) or not (getattr(event.data, 'extend', {}) or {}).get('flag_from_qq'):
        return
    chat = getattr(event.data, 'group_id' if group else 'user_id', None)
    message_id = getattr(event.data, 'message_id', None)
    if chat and message_id:
        _initialise(proc)[0].recall_message(
            event.bot_info.hash, 'qq_group' if group else 'qq_private', str(chat), str(message_id)
        )


def _safe(action, *args):
    try:
        action(*args)
    except Exception:
        _log.exception('控制台事件处理失败')


class Event:
    def init(plugin_event, Proc):
        pass

    def init_after(plugin_event, Proc):
        _safe(_initialise, Proc)
        try:
            _initialise(Proc)[4].backfill_group_names()
        except Exception:
            _log.exception('控制台群名回填失败')

    def group_message(plugin_event, Proc):
        _safe(_incoming, plugin_event, Proc, True)

    def private_message(plugin_event, Proc):
        _safe(_incoming, plugin_event, Proc, False)

    def button_click(plugin_event, Proc):
        _safe(_button, plugin_event, Proc)

    def group_member_increase(plugin_event, Proc):
        _safe(_member_event, plugin_event, Proc, True)

    def group_member_decrease(plugin_event, Proc):
        _safe(_member_event, plugin_event, Proc, False)

    def group_message_recall(plugin_event, Proc):
        _safe(_recall, plugin_event, Proc, True)

    def private_message_recall(plugin_event, Proc):
        _safe(_recall, plugin_event, Proc, False)

    def menu(plugin_event, Proc):
        if getattr(plugin_event.data, 'namespace', None) != 'QQOfficialConsole':
            return
        context = getattr(plugin_event.data, 'webui', None)
        if not isinstance(context, dict):
            return
        request_id = context.get('request_id')
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            return
        try:
            response = _initialise(Proc)[4].handle(
                getattr(plugin_event.data, 'event', ''), getattr(plugin_event.data, 'payload', None)
            )
        except Exception:
            _log.exception('控制台网页请求失败')
            response = {'ok': False, 'keyword': '未知错误'}
        plugin_event.send('webui', request_id, response)

    def save(plugin_event, Proc):
        global _state
        with _guard:
            if _state is not None:
                try:
                    outgoing.detach()
                    _state[4].close()
                    _state[0].save()
                    _state[0].close()
                except Exception:
                    _log.exception('控制台保存失败')
                _state = None
