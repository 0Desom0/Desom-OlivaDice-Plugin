"""把「机器人自己发出的消息」也记进会话库。

QQ 官方机器人的接口不会回吐机器人自己发过的消息，OlivOS 的 qqGuildv2 适配器
也不产生 `group_message_sent` / `private_message_sent` 事件，所以只能包一层
统一发送方法 `OlivOS.core.core.API.Event._Event__send`：

- 它是 `send()` / `reply()` / 分段发送最终都会落到的那一层；
- 发送成功后再落库，失败的不记（避免把没发出去的内容当成历史）。

本插件自己的发送在 `webui.Bridge._handle('Send')` 里已经写过库，这里按插件名
跳过，避免同一条消息出现两次。
"""

import logging
import os
import re
import time

import OlivOS

from . import errors

_log = logging.getLogger('QQOfficialConsole')

# 状态挂在 OlivOS 模块上而不是本模块上：插件重载会重建本模块，但类上的 wrapper
# 还在，重载后只要把新状态换进这个槽位即可，不必重复包装。
_STATE_KEY = '_qqconsole_send_state'
_HOOK_FLAG = '_qqconsole_send_hook'
_CHAT_TYPES = {'group': 'qq_group', 'private': 'qq_private'}
# 本插件自己写库（webui.Bridge 的 Send 分支），包装层要跳过它，否则同一条消息记两次。
# 用 namespace 判定最稳：插件显示名是中文，不跟着改。
_SELF_NAMESPACES = ('QQOfficialConsole',)
# 判断一段文本“像不像 markdown”：有这些标记才按 markdown 渲染，
# 否则普通插件发的日志式纯文本会被误解析成列表/标题。
_MARKDOWN_HINT = re.compile(
    r'(\*\*[^*\n]+\*\*|`[^`\n]+`|^#{1,3}\s+|^\s*[-*+]\s+|^\s*\d+\.\s+|^>\s?|\[[^\]\n]+\]\(https?://)',
    re.M,
)


# describe() 会把图片/文件段压成占位符文字，判断“有没有正文”时要排除它们。
_SILENT_TEXT = {'[图片]', '[文件]', '[表情]'}
# 轻量诊断：装没装上、每次跳过是什么原因，都记到 data/send-hook.state 里。
_DIAG = {'calls': 0, 'saved': 0, 'skip': {}}


def message_kind(text, images):
    """决定这条消息在控制台里按什么类型记。

    QQ 官方适配器把「文本 + 图片」当 markdown 混排发送（msg_type=2），
    纯文本是 msg_type=0；这里跟着平台的实际行为走，控制台才和群里一致。
    """
    plain = (text or '').strip()
    if plain in _SILENT_TEXT:
        plain = ''
    if images:
        return 'markdown' if plain else 'media'
    if _MARKDOWN_HINT.search(plain):
        return 'markdown'
    return 'text'


def state():
    return getattr(OlivOS, _STATE_KEY, None)


def _trace(text):
    """把钩子状态写到插件 data 目录，方便重载后核对（覆盖写，只留最后一次）。

    路径按本文件位置推，不用 os.getcwd()：OlivOS 的工作目录未必是安装目录，
    用 cwd 拼会把文件写到别处、看起来像「钩子没装上」。
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.normpath(os.path.join(here, os.pardir, os.pardir, os.pardir, 'data', 'QQOfficialConsole'))
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, 'send-hook.state'), 'w', encoding='utf-8') as handle:
            handle.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), text))
    except Exception:
        pass


def _flush_diag():
    _trace('calls=%d saved=%d skip=%s' % (_DIAG['calls'], _DIAG['saved'], _DIAG['skip']))


def _note(reason):
    _DIAG['skip'][reason] = _DIAG['skip'].get(reason, 0) + 1


def install(holder):
    """安装发送钩子。holder 即 main._initialise() 的 (database, pool, ...) 元组。

    挂点是 qqGuildv2 所有发送的最终出口 `event_action_common._send_qq_api`：
    OlivaDice 这类插件直接调 SDK，不经过 `Event.__send`，挂在那里会漏记。
    """
    setattr(OlivOS, _STATE_KEY, holder)
    _restore_legacy_hook()
    from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as common  # 延迟导入，避免加载顺序问题

    target = common.event_action_common
    if getattr(target, _HOOK_FLAG, False):
        _log.info('发送记录钩子已在位（沿用上次的包装），未重复安装')
        _trace('hook already installed (skip)')
        return
    original = target._send_qq_api

    def send_api(*args, **kwargs):
        result = original(*args, **kwargs)
        try:
            _DIAG['calls'] += 1
            if len(args) >= 4:
                record_api(args[0], args[1], args[2], args[3], result)
            _flush_diag()
        except Exception:
            # 记录失败绝不能影响正常发送。
            _log.exception('记录机器人发出的消息失败')
        return result

    target._send_qq_api = staticmethod(send_api)
    setattr(target, _HOOK_FLAG, True)
    _log.info('发送记录钩子已安装：event_action_common._send_qq_api（其他插件发出的消息也会写进会话库）')
    _trace('hook installed on event_action_common._send_qq_api')


def _restore_legacy_hook():
    """还原旧版挂在 Event._Event__send 上的包装，避免同一条消息被记两次。"""
    try:
        from OlivOS.core.core.API import Event

        if not getattr(Event, _HOOK_FLAG, False):
            return
        current = getattr(Event, '_Event__send', None)
        freevars = getattr(getattr(current, '__code__', None), 'co_freevars', ())
        if 'original' not in freevars:
            return
        closure = getattr(current, '__closure__', None) or ()
        original = closure[freevars.index('original')].cell_contents
        if callable(original):
            setattr(Event, '_Event__send', original)
            setattr(Event, _HOOK_FLAG, False)
            _log.warning('已还原旧挂点 Event._Event__send（避免重复记录）')
    except Exception:
        _log.exception('还原旧发送钩子失败')


def detach():
    """插件卸载/重载时先断开，避免包装层写到已经关闭的数据库。"""
    setattr(OlivOS, _STATE_KEY, None)


def _plugin_identity(event):
    info = getattr(event, 'plugin_info', None)
    if not isinstance(info, dict):
        return '', ''
    return str(info.get('name') or ''), str(info.get('namespace') or '')


def _para_text(para):
    """把单个消息段压成可读文本。"""
    kind = getattr(para, 'type', None)
    data = getattr(para, 'data', None)
    if not isinstance(data, dict):
        data = {}
    if kind == 'text':
        return str(data.get('text') or '')
    if kind == 'at':
        name = data.get('name') or data.get('id') or ''
        return '@' + str(name) if name else '@'
    if kind in ('image', 'mface'):
        return '[图片]'
    if kind == 'face':
        return '[表情]'
    if kind == 'file':
        return '[文件]'
    if kind in ('json', 'card'):
        return '[卡片]'
    if kind == 'reply':
        return ''
    return ''


def describe(message):
    """把任意插件传进来的 message 压成 (文本, kind, 图片列表)。"""
    if isinstance(message, str):
        text = message.strip()
        return text, 'text', []
    if isinstance(message, (list, tuple)):
        parts = []
        images = []
        for para in message:
            if isinstance(para, str):
                parts.append(para)
                continue
            parts.append(_para_text(para))
            if getattr(para, 'type', None) == 'image':
                data = getattr(para, 'data', None)
                if isinstance(data, dict):
                    images.append({'url': data.get('url') or data.get('file')})
        text = ''.join(parts).strip()
        return text, ('media' if images else 'text'), images
    data = getattr(message, 'data', None)
    if isinstance(data, (list, tuple)):
        return describe(list(data))
    text = getattr(message, 'text', None)
    return (str(text).strip() if isinstance(text, str) else ''), 'text', []


def bot_name(bot_hash):
    """bot 自己的昵称：SDK 调过 /users/@me 后会缓存在 sdkSelfInfo 里。"""
    try:
        from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as common

        info = common.sdkSelfInfo.get(bot_hash) or {}
        if isinstance(info, dict):
            name = info.get('username') or info.get('nick')
            if isinstance(name, str) and name.strip():
                return name.strip()
    except Exception:
        pass
    return '机器人'


def _duplicate(database, bot, chat_type, chat_id, message_id, text, now):
    """同一条消息可能因重试/分段被多次经过这里，落库前先查重。"""
    with database.session(bot, chat_type, chat_id) as db:
        if message_id:
            row = db.execute(
                "SELECT id FROM messages WHERE direction='out' AND platform_message_id=? LIMIT 1",
                (str(message_id),),
            ).fetchone()
        else:
            # 没有 message_id 时退化成「5 秒内同文本」，宁可少记也不要重复记。
            row = db.execute(
                "SELECT id FROM messages WHERE direction='out' AND content_text=? AND created_at>=? LIMIT 1",
                (text, now - 5),
            ).fetchone()
    return row is not None


def api_payload(api_obj):
    """从 SDK 的 api_templet 里取出 (文本, kind, 图片列表)。"""
    data = getattr(api_obj, 'data', None)
    if data is None:
        return '', 'text', []
    msg_type = getattr(data, 'msg_type', 0)
    if msg_type == 2:
        markdown = getattr(data, 'markdown', None)
        markdown = markdown if isinstance(markdown, dict) else {}
        content = markdown.get('content')
        if isinstance(content, str) and content.strip():
            return content, 'markdown', []
        # 模板型 markdown（只有 template_id + params）没有可读正文。
        return '[Markdown 模板消息]', 'markdown', []
    if msg_type == 7:
        text = str(getattr(data, 'content', '') or '').strip()
        return text, ('markdown' if text else 'media'), [{'file_info': True}]
    text = str(getattr(data, 'content', '') or '').strip()
    return text, message_kind(text, []), []


def record_api(target_event, api_obj, chat_type, chat_id, raw_result):
    """发送出口钩子的落库逻辑：只记成功的、非本插件的群/单聊消息。"""
    holder = state()
    if not holder:
        _note('no_state')
        return
    plugin, namespace = _plugin_identity(target_event)
    if namespace in _SELF_NAMESPACES:
        _note('self')
        return
    if chat_type not in ('qq_group', 'qq_private'):
        _note('chat_type:' + str(chat_type))
        return
    chat_id = str(chat_id or '')
    bot = getattr(getattr(target_event, 'bot_info', None), 'hash', None)
    if not bot or not chat_id:
        _note('no_bot_or_chat')
        return
    if not isinstance(raw_result, dict):
        _note('result_not_dict')
        return
    result = errors.result(raw_result)
    if not result.get('ok'):
        _note('not_ok:' + str(result.get('keyword')))
        return
    text, kind, images = api_payload(api_obj)
    if not text and not images:
        _note('empty_text')
        return
    message_id = result.get('message_id')
    now = int(time.time())
    database = holder[0]
    if _duplicate(database, bot, chat_type, chat_id, message_id, text, now):
        _note('duplicate')
        return
    content: dict = {'text': text, 'source': 'plugin', 'plugin': plugin or namespace}
    if images:
        content['images'] = images
    database.add_message(
        bot,
        chat_type,
        chat_id,
        {
            'direction': 'out',
            'platform_message_id': str(message_id) if message_id else None,
            'sender_name': bot_name(bot),
            'msg_kind': kind,
            'content_text': text,
            'content_json': content,
            'created_at': now,
            'send_channel': result.get('channel'),
        },
        unread=False,
    )
    _DIAG['saved'] += 1
