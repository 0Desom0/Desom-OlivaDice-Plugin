import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import quote, urlsplit

import OlivOS

from . import bili_api, config, message_custom, store

_QQ = 'qqGuildv2_link'
_LIMIT = 4000
_COVER = '{{cover}}'
_QQ_ALL = '<qqbot-at-everyone />'
_QQ_USER = r'<qqbot-at-user\s+id="([A-Za-z0-9_-]+)"\s*/>'
_TOKEN = re.compile(r'\[OP:[^\]\n]+\]|<qqbot-at-(?:everyone\s*/>|user\s+id="[^"\n]+"\s*/>)|\{\{cover\}\}')
_OP_INTRO = re.compile(r'\[(?=(?:OP|CQ):)', re.IGNORECASE)
_MD_PUNCT = re.compile(r'([\\`*_{}\[\]()#+\-.!|~])')
_MD_LABEL = re.compile(r'(?<!\\)\*\*([^*\n]+)\*\*')
_MD_ESCAPE = re.compile(r'\\([\\`*_{}\[\]()#+\-.!|~])')


def _http_url(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if any(char.isspace() or ord(char) < 32 for char in value) or '\\' in value:
        return ''
    try:
        url = urlsplit(value)
        if url.scheme in ('http', 'https') and url.hostname and url.username is None and url.password is None:
            return value
    except ValueError:
        pass
    return ''


def pick_first_image(candidates):
    """保留候选顺序，忽略空值和非 HTTP(S) 地址。"""
    return next((url for candidate in candidates if (url := _http_url(candidate))), '')


def _tokens(segments):
    for segment in segments:
        begin = 0
        for match in _TOKEN.finditer(segment):
            if begin < match.start():
                yield segment[begin:match.start()], False
            yield match[0], True
            begin = match.end()
        if begin < len(segment):
            yield segment[begin:], False


def split_segments(segments, limit=4000):
    """长文本可拆，OP、Markdown @ 与封面标记必须完整留在同一条。"""
    if limit <= 0:
        raise ValueError('limit must be positive')
    result, buffer = [], []
    size = 0
    for text, atomic in _tokens(segments):
        if atomic:
            if buffer and size + len(text) > limit:
                result.append(''.join(buffer))
                buffer, size = [], 0
            buffer.append(text)
            size += len(text)
        else:
            offset = 0
            while offset < len(text):
                if size >= limit:
                    result.append(''.join(buffer))
                    buffer, size = [], 0
                length = min(limit - size, len(text) - offset)
                buffer.append(text[offset:offset + length])
                size += length
                offset += length
    if buffer:
        result.append(''.join(buffer))
    return result


def mention_segments(sdk, user_ids):
    pattern = r'[A-Za-z0-9_-]{1,128}' if sdk == _QQ else r'[0-9]{1,32}'
    result = []
    seen = set()
    for user_id in user_ids:
        user_id = str(user_id)
        if user_id.lower() == 'all' or user_id in seen or not re.fullmatch(pattern, user_id):
            continue
        seen.add(user_id)
        if sdk == _QQ:
            result.append(f'<qqbot-at-user id="{user_id}" />')
        else:
            result.append(f'[OP:at,id={user_id}]')
    return result


def _plain_text(value):
    # OlivOS 的 OP 解析器没有文本转义入口；保留一般方括号，只打断指令开头。
    value = _OP_INTRO.sub('［', str(value) if value is not None else '')
    return value.translate(str.maketrans({'<': '＜', '>': '＞', '@': '＠'}))


def _markdown_text(value):
    value = _plain_text(value).replace('&', '&amp;')
    return _MD_PUNCT.sub(r'\\\1', value)


def _push_url(value):
    # OP 解析器按逗号和右方括号分割；提前百分号编码，避免 URL 产生附加参数。
    return quote(value, safe=':/?&=+#%@;_$~-')


def _render(kind, fields, sdk, image, at_all, subscribers, test):
    markdown = sdk == _QQ
    escape = _markdown_text if markdown else _plain_text
    values = {key: escape(fields.get(key, '')) for key in ('name', 'title', 'area', 'time')}
    values['body'] = escape(str(fields.get('body') or '')[:200])
    values['link'] = _push_url(_http_url(fields.get('link'))) or escape(fields.get('link', ''))
    values['image'] = image
    mentioned = mention_segments(sdk, subscribers) if kind == 'start' else []
    if markdown:
        values['at_all'] = _QQ_ALL + '\n' if kind == 'start' and at_all else ''
        values['subscribers'] = '\n'.join(mentioned)
        template = message_custom.MARKDOWN[kind]
    else:
        values['at_all'] = '[OP:at,id=all]\n' if kind == 'start' and at_all else ''
        values['subscribers'] = '\n' + ' '.join(mentioned) if mentioned else ''
        template = message_custom.OP[kind]
    prefix = message_custom.TEXT['test_prefix'] if test else ''
    return split_segments((prefix, template.format(**values).strip()), _LIMIT)


def _event(proc, bot_hash, target):
    proc_data = getattr(proc, 'Proc_data', None)
    bot_info_dict = proc_data.get('bot_info_dict') if isinstance(proc_data, dict) else None
    bot = bot_info_dict.get(bot_hash) if isinstance(bot_info_dict, dict) else None
    platform = bot.platform if bot is not None else {}
    if any(platform.get(key) != target.get(key) for key in ('sdk', 'platform')) or bot is None:
        raise ValueError('bot/target mismatch')
    # core/core/contentAPI.py: fake_sdk_event/get_Event_from_fake_SDK；core/core/API.py: Event。
    event = OlivOS.contentAPI.fake_sdk_event(
        bot, platform=platform, fakename=config.PLUGIN_NAME, plugin_namespace=config.PLUGIN_NAME,
        message_mode_tx='olivos_string',
    )
    return OlivOS.API.Event(event, log_func=proc.log, Proc=proc)


def _result_details(result):
    if not isinstance(result, dict):
        return 'error=未确认发送结果'
    details = result.get('data')
    details = details if isinstance(details, dict) else {}
    fields = []
    for key in ('http_status', 'error_code', 'retcode'):
        value = str(details.get(key, result.get(key, '')))
        if re.fullmatch(r'-?[0-9]{1,12}', value):
            fields.append(f'{key}={value}')
    # 平台错误文本可能带响应原文或地址，只记录是否有错误而不输出任意字符串。
    if details.get('error') or result.get('error'):
        fields.insert(0, 'error=适配器返回错误')
    return ' '.join(fields) or 'error=适配器未确认发送'


def _op_ok(result):
    if result is None or result is True:
        # core/core/API.py 的 OneBot Link/Host 分支入队后不返回确认值。
        return True
    if not isinstance(result, dict):
        return False
    status = result.get('status')
    if 'retcode' in result:
        code = result['retcode']
        return status != 'failed' and (code in (0, '0') or (status == 'async' and code in (1, '1')))
    return result.get('active') is True or status in ('ok', 'async')


def _qq_plain(event, chat_id, parts):
    # adapter/qqGuild/qqGuildv2SDKGroup.py: Event.send 会自动尝试 Markdown，降级必须显式关掉它。
    message = OlivOS.messageAPI.Message_templet('olivos_para', parts)
    return OlivOS.qqGuildv2SDK.event_action.send_qq_msg(
        event, chat_id, message, force_active=True, allow_markdown=False,
    )


def _plain_parts(chunk, path):
    # core/core/messageAPI.py: 用结构化段直接传本地图片和受信任的 @，不再解析正文。
    para = OlivOS.messageAPI.PARA
    parts = []
    for token, atomic in _tokens((chunk,)):
        if atomic and token == _COVER:
            if path is not None:
                parts.append(para.image(file=str(path.resolve())))
        elif atomic and token == _QQ_ALL:
            # 失败可能是平台不支持群 @全体；降级时只保留个人提醒。
            continue
        elif atomic and (user := re.fullmatch(_QQ_USER, token)):
            parts.append(para.at(id=user[1]))
        else:
            text = unescape(_MD_ESCAPE.sub(r'\1', _MD_LABEL.sub(r'\1', token)))
            parts.append(para.text(text))
    return parts


def _qq_ok(result):
    return isinstance(result, dict) and result.get('active') is True


def _qq_send(proc, event, chat_id, chunk, path, still_current):
    local_images = None
    if path is not None and _COVER in chunk:
        local_images = {'cover': Path(config.PLUGIN_NAME, 'covers', path.name).as_posix()}
    try:
        # adapter/qqGuild/qqGuildv2SDKCommon.py: inde_interface.create_markdown_message。
        result = event.indeAPI.create_markdown_message(
            chat_type='qq_group', chat_id=chat_id, markdown={'content': chunk},
            local_images=local_images, force_active=True, flag_log=False,
        )
    except Exception as error:
        store.log(proc, f'QQ Markdown 发送异常：{type(error).__name__}，尝试普通图文', level=3)
    else:
        if _qq_ok(result):
            if isinstance(result.get('data'), dict) and result['data'].get('markdown_fallback'):
                store.log(proc, 'QQ Markdown 上传失败，适配器已降级为普通图文', level=3)
            return True
        store.log(proc, f'QQ Markdown 发送失败：{_result_details(result)}，尝试普通图文', level=3)
    parts = _plain_parts(chunk, path)
    if not _current(still_current):
        return False
    result = _qq_plain(event, chat_id, parts)
    if not _qq_ok(result):
        store.log(proc, f'QQ 普通图文发送失败：{_result_details(result)}', level=3)
        return False
    return True


def _current(still_current):
    return still_current is None or still_current()


def _group_id(target):
    return str(target.get('group_id') or '')


def _supported(target):
    return _group_id(target) and (target.get('sdk') != _QQ or target.get('chat_type') == 'qq_group')


def send(proc, bot_hash, target, kind, fields, *, image='', at_all=False, subscribers=(), test=False,
         interval=3, still_current=None):
    if not _supported(target) or not _current(still_current):
        return False
    sdk = target['sdk']
    chat_id = _group_id(target)
    path = None
    try:
        event = _event(proc, bot_hash, target)
        image = _http_url(image) if kind != 'end' else ''
        image_segment = ''
        if sdk == _QQ and image:
            path = bili_api.download_image(image)
            image_segment = _COVER if path is not None else ''
        elif image:
            url = _push_url(image)
            if len(url) <= _LIMIT - len('[OP:image,file=]'):
                # 图片段后留一个空行：和官方 Markdown 的观感一致。
                image_segment = f'[OP:image,file={url}]\n\n'
        chunks = _render(kind, fields, sdk, image_segment, at_all, subscribers, test)
        for index, chunk in enumerate(chunks):
            if index:
                time.sleep(interval)
            if not _current(still_current):
                return False
            if sdk == _QQ:
                if not _qq_send(proc, event, chat_id, chunk, path, still_current):
                    return False
            else:
                # core/core/API.py: Event.send 主动队列接口，message_mode_tx 是 olivos_string。
                result = event.send('group', chat_id, chunk, flag_log=False)
                if not _op_ok(result):
                    store.log(proc, f'OP 推送失败：{_result_details(result)}', level=3)
                    return False
        return bool(chunks)
    except Exception as error:
        # 宿主适配器异常是外部边界；异常原文可能含响应内容或地址。
        store.log(proc, f'群推送异常：{type(error).__name__}', level=3)
        return False
    finally:
        if path is not None:
            bili_api.release_image(path)


def send_warning(proc, bot_hash, target, text, *, still_current=None):
    if not _supported(target) or not _current(still_current):
        return False
    try:
        event = _event(proc, bot_hash, target)
        chat_id = _group_id(target)
        text = _plain_text(text)
        if not _current(still_current):
            return False
        if target['sdk'] == _QQ:
            result = _qq_plain(event, chat_id, [OlivOS.messageAPI.PARA.text(text)])
            success = _qq_ok(result)
        else:
            result = event.send('group', chat_id, text, flag_log=False)
            success = _op_ok(result)
        if not success:
            store.log(proc, f'风控提醒发送失败：{_result_details(result)}', level=3)
        return success
    except Exception as error:
        store.log(proc, f'风控提醒发送异常：{type(error).__name__}', level=3)
        return False
