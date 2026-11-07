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
# 群聊 @全体成员：平台下发的是 <qqbot-at-everyone /> 标签，旧占位 <@all>/<@everyone> 与
# mentions 里的 all/everyone 条目也都认。
_AT_EVERYONE_RE = re.compile(r'<qqbot-at-everyone\s*/?>|<@!?\s*(?:all|everyone)\s*>', re.IGNORECASE)
_EVERYONE_IDS = ('all', 'everyone')
_EVERYONE_TEXT = '@全体成员'


def _strip_face_tags(text):
    """剥离 QQ 原始表情标签；SDK 的正则优先，宿主缺失时本地兜底。"""
    try:
        from OlivOS.adapter.qqGuild.qqGuildv2SDKCommon import _strip_qq_face_tags
        stripped, _ = _strip_qq_face_tags(text)
        return stripped
    except Exception:
        return _FACE_RE.sub('', text)


def _render_text(text, raw, at_spans=None):
    """@ 占位符替换成 mentions 里的昵称；@全体成员显示成固定文案；表情标签替换为 [表情]。

    at_spans 可选：收集这条消息里由 at 占位符生成的显示文案，随 content_json 交给前端。
    前端据此精确高亮，不必靠「@ 后面一路吃到空白」猜范围——中文消息里
    「@某人，今晚开团」没有空格，猜范围会把后半句也一起染上颜色。
    """
    def everyone(_match):
        if at_spans is not None:
            at_spans.append(_EVERYONE_TEXT)
        return _EVERYONE_TEXT

    text = _AT_EVERYONE_RE.sub(everyone, text)
    mentions = raw.get('mentions')
    if isinstance(mentions, list):
        names = {}
        for item in mentions:
            if isinstance(item, dict):
                ident = str(item.get('id') or item.get('member_openid') or '')
                name = item.get('username') or item.get('nick')
                if ident and isinstance(name, str) and name:
                    names[ident] = name

        def replace(match):
            ident = match.group(1).strip()
            label = (
                _EVERYONE_TEXT if ident.lower() in _EVERYONE_IDS
                else '@' + names.get(ident, '成员')
            )
            if at_spans is not None:
                at_spans.append(label)
            return label

        # QQ 正文里的 @ 占位符是 <@member_openid>；已知的换成昵称，未知的退化成「@成员」，
        # @全体成员占位（all/everyone）换成固定文案，绝不把原始 <@...> 标记漏给用户。
        # 占位符里不含斜杠/反斜杠/空白：别人发的 <@//xxx/> 这类路径是假 at，原样保留。
        text = re.sub(r'<@!?\s*([^<>\s/\\]+)>', replace, text)
    stripped = _strip_face_tags(text)
    if stripped != text and _FACE_RE.search(text):
        text = _FACE_RE.sub('[表情]', text)
    return text.strip()


def _at_everyone(raw):
    """这条消息是不是 @ 了全体成员：看正文标签，也看 mentions 里的全体占位。"""
    if _AT_EVERYONE_RE.search(str(raw.get('content') or '')):
        return True
    mentions = raw.get('mentions')
    if isinstance(mentions, list):
        for item in mentions:
            if isinstance(item, dict) and (
                str(item.get('id') or item.get('member_openid') or '').strip().lower() in _EVERYONE_IDS
            ):
                return True
    return False


# —— 合并转发（聊天记录）——
# 官方把「聊天记录」当成 message_type=102 下发，正文是一段纯文本：
#   [某某的聊天记录]
#   === 消息 1 ===
#   [发送者] 某某
#   [消息内容] 正文
#   [附件1] 类型:图片 文件名:… 尺寸:… 大小:… URL:…
# 这里把它还原成前端要的卡片结构；图片只记下标，前端仍走代理下载（CDN 链接会过期）。
_FORWARD_MESSAGE_RE = re.compile(r'^(?P<indent>[ \t]*)===\s*消息\s+\d+\s*===\s*$', re.M)
_FORWARD_ATTACH_RE = re.compile(r'^[ \t]*\[附件\d+\][ \t]*(.*)$', re.M)
_FORWARD_FIELD_RE = re.compile(r'\[(?:消息内容|发送者|消息类型|关联消息|附件\d+)\]')
_FORWARD_LIMIT = 100        # 一次转发最多收 100 条，别让一条消息把数据库撑爆
_FORWARD_TEXT_LIMIT = 4000  # 单条正文上限
_FORWARD_IMAGE_LIMIT = 40   # 单条转发最多缓存 40 张图
_IMAGE_MIMES = {'png': 'image/png', 'gif': 'image/gif', 'webp': 'image/webp'}


def _split_forward_blocks(text):
    """按「=== 消息 N ===」切块，只认最外层缩进（嵌套转发会缩进一层）。"""
    matches = list(_FORWARD_MESSAGE_RE.finditer(text))
    if not matches:
        return []
    indent = min(len(match.group('indent').expandtabs(4)) for match in matches)
    matches = [item for item in matches if len(item.group('indent').expandtabs(4)) == indent]
    blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end():end].strip()
        if block:
            blocks.append(block)
    return blocks


def _forward_field(block, name):
    """取 [发送者]/[消息内容] 的值；值可以换行，遇到下一个字段就收住。"""
    match = re.search(r'(?m)^[ \t]*\[%s\][ \t]*(.*)$' % re.escape(name), block)
    if match is None:
        return None
    lines = [match.group(1)]
    for line in block[match.end():].splitlines():
        stripped = line.strip()
        if _FORWARD_FIELD_RE.match(stripped) or stripped.startswith(('===', '---')):
            break
        lines.append(stripped)
    value = '\n'.join(lines).strip()
    return value if value else None


def _forward_attachment(text):
    """把 [附件N] 那行还原成和平台下发一致的附件结构；没有 URL 就当作拿不到。"""
    found = re.search(r'URL:\s*(\S+)', text)
    if found is None:
        return None
    url = found.group(1)
    if url.startswith('//'):
        url = 'https:' + url
    elif url.startswith('multimedia.nt.qq.com.cn/'):
        url = 'https://' + url
    kind = re.search(r'类型:\s*([^\s]+)', text)
    kind = (kind.group(1) if kind else '').lower()
    name = re.search(r'文件名:\s*(.*?)(?=\s+(?:尺寸|大小|URL):|$)', text)
    name = name.group(1).strip() if name else ''
    suffix = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if '图片' in kind or 'image' in kind:
        content_type = _IMAGE_MIMES.get(suffix, 'image/jpeg')
    elif '视频' in kind or 'video' in kind:
        content_type = 'video/mp4'
    elif '语音' in kind or '音频' in kind or 'audio' in kind:
        content_type = 'audio/silk'
    else:
        content_type = 'application/octet-stream'
    item = {'url': url, 'content_type': content_type}
    if name:
        item['filename'] = name
    size = re.search(r'大小:\s*([^\s]+)', text)
    if size:
        item['size'] = size.group(1)
    dimension = re.search(r'尺寸:\s*(\d+)\s*[xX×]\s*(\d+)', text)
    if dimension:
        item['width'] = int(dimension.group(1))
        item['height'] = int(dimension.group(2))
    return item


def _forward_payload(raw):
    """解析合并转发的正文；不是合并转发返回 None。

    返回 {'title', 'messages', 'images'}：messages 里图片段的 attachment
    是 images 里的下标，最终写入时还要加上原有附件的数量。
    """
    elements = raw.get('msg_elements')
    texts = []
    if isinstance(elements, list):
        for element in elements:
            if isinstance(element, dict) and isinstance(element.get('content'), str):
                texts.append(element['content'])
    if not texts and isinstance(raw.get('content'), str):
        texts.append(raw['content'])
    content = '\n'.join(texts)
    blocks = _split_forward_blocks(content)
    if not blocks:
        return None
    try:
        msg_type = int(raw.get('message_type') or 0)
    except (TypeError, ValueError):
        msg_type = 0
    # 别人手打「=== 消息 1 ===」不该变成卡片：要么平台标了 102，要么真带发送者字段。
    if msg_type != 102 and '[发送者]' not in content:
        return None

    title = ''
    head = content.split('===', 1)[0].strip()
    if head.startswith('[') and head.endswith(']'):
        title = head[1:-1].strip()

    images = []
    messages = []
    for block in blocks[:_FORWARD_LIMIT]:
        item = {'name': (_forward_field(block, '发送者') or '')[:64], 'segments': []}
        body = _forward_field(block, '消息内容')
        if body:
            item['segments'].append({'type': 'text', 'text': body[:_FORWARD_TEXT_LIMIT]})
        for match in _FORWARD_ATTACH_RE.finditer(block):
            # 附件描述可能折成好几行，读到下一个 [字段] 或分隔线为止。
            parts = [match.group(1).strip()]
            for line in block[match.end():].splitlines():
                stripped = line.strip()
                if _FORWARD_FIELD_RE.match(stripped) or stripped.startswith(('===', '---')):
                    break
                parts.append(stripped)
            attachment = _forward_attachment(' '.join(part for part in parts if part))
            if attachment is None:
                continue
            kind = attachment['content_type']
            if kind.startswith('image/'):
                if len(images) >= _FORWARD_IMAGE_LIMIT:
                    item['segments'].append({'type': 'text', 'text': '[图片]'})
                    continue
                item['segments'].append({'type': 'image', 'attachment': len(images)})
                images.append(attachment)
            elif kind.startswith('video/'):
                item['segments'].append({'type': 'video'})
            elif kind.startswith('audio/'):
                item['segments'].append({'type': 'audio'})
            else:
                item['segments'].append({'type': 'file', 'name': attachment.get('filename') or '文件'})
        if item['segments']:
            messages.append(item)
    if not messages:
        return None
    return {'title': title[:80], 'messages': messages, 'images': images}


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
    attachments = raw.get('attachments') or []
    forward = _forward_payload(raw)
    at_spans = []
    if forward is None:
        text = _render_text(str(raw.get('content') or ''), raw, at_spans)
    else:
        # 合并转发的正文是「=== 消息 N ===」那种文本块，直接显示会糊一屏；
        # 气泡里只写 [聊天记录]，真正的内容放进 content_json.forward 给前端画卡片。
        text = '[聊天记录]'
    msg_kind = 'forward' if forward is not None else ('media' if attachments else 'text')
    # 只记录真正由 at 占位符生成的文案；没有 at 的消息保持原来的 content_json 结构。
    content_data = {'text': text, 'attachments': list(attachments)}
    if forward is not None:
        # 转发里的图片接在原有附件后面，图片下标整体后移。
        offset = len(attachments)
        for item in forward['messages']:
            for segment in item['segments']:
                if segment['type'] == 'image':
                    segment['attachment'] += offset
        content_data['attachments'] = list(attachments) + forward['images']
        content_data['forward'] = {'title': forward['title'], 'messages': forward['messages']}
    if at_spans:
        content_data['at'] = at_spans
    message = {
        'direction': 'in',
        'platform_message_id': str(msg_id) if msg_id else None,
        'ref_idx': extend.get('qq_msg_idx'),
        'reply_to': extend.get('qq_reference_message_id'),
        'sender_id': sender_id,
        'sender_name': name,
        'msg_kind': msg_kind,
        'content_text': text,
        'content_json': content_data,
        'created_at': created,
        'is_mention': group and _at_bot(extend, event, raw),
        'is_everyone': group and _at_everyone(raw),
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
