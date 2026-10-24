"""QQ 官方机器人 Markdown 兼容层。

判定口径对齐 OlivOS 的图文 Markdown 通路：只有 qqGuildv2 的 QQ 群 / C2C 才走
Markdown；旧版 OlivOS 没有``create_markdown_message``、或图文消息没有
``local_images``/``allow_markdown`` 能力时，一律抛 :class:`NotApplicable`，
由调用方保留既有的『』文本注入方案。
"""

import inspect

# 群聊 / 单聊的 Markdown 由手机客户端渲染，只认标准语法：标题、粗体、斜体、
# 删除线、链接、图片、列表、引用、分割线。HTML 的 <font> 只有桌面端 QQNT 认，
# 因此这里改用块引用：全客户端一致生效，视觉上同样把状态栏压成「附注」级别。
HUD_PREFIX = '> '

_AT_ALL = '<qqbot-at-everyone />'
_IMAGE_NAME = 'hud_image_%d'


class NotApplicable(Exception):
    """当前版本、会话或消息结构不能安全使用 Markdown。"""


class Content:
    """待发送的 Markdown 内容。"""

    __slots__ = ('text', 'quote_id', 'local_images')

    def __init__(self, text, quote_id=None, local_images=None):
        self.text = text
        self.quote_id = quote_id
        self.local_images = local_images or {}


def api_available(event):
    """OlivOS 是否提供 Markdown 发送接口（旧版没有该方法）。"""
    api = getattr(event, 'indeAPI', None)
    has_api = getattr(api, 'hasAPI', None)
    if api is None or not callable(has_api):
        return False
    try:
        return bool(has_api('create_markdown_message'))
    except Exception:
        return False


def _is_qq(event):
    platform = getattr(event, 'platform', None)
    return isinstance(platform, dict) and platform.get('sdk') == 'qqGuildv2_link'


def _extend(event):
    extend = getattr(getattr(event, 'data', None), 'extend', None)
    return extend if isinstance(extend, dict) else None


def chat_context(event):
    """被动回复的会话标识；与 OlivOS 图文 Markdown 一致，仅 QQ 群 / C2C。"""
    if not _is_qq(event):
        return None
    extend = _extend(event)
    if extend is None or not extend.get('flag_from_qq', False):
        return None
    func_type = getattr(event, 'plugin_info', {}).get('func_type')
    direct = bool(extend.get('flag_from_direct', func_type == 'private_message'))
    if direct:
        chat_id = getattr(event.data, 'user_id', None)
        chat_type = 'qq_private'
    else:
        chat_id = getattr(event.data, 'group_id', None)
        chat_type = 'qq_group'
    if chat_id is None or str(chat_id) == '':
        return None
    return chat_type, str(chat_id)


def send_context(event, send_type, target_id, host_id):
    """主动发送的会话标识；带 host 的频道发送不在此列。"""
    if host_id is not None or not _is_qq(event):
        return None
    extend = _extend(event)
    if extend is None or not extend.get('flag_from_qq', False):
        return None
    if send_type == 'group':
        chat_type = 'qq_group'
    elif send_type == 'private':
        chat_type = 'qq_private'
    else:
        return None
    if target_id is None or str(target_id) == '':
        return None
    return chat_type, str(target_id)


def mixed_supported(olivos):
    """OlivOS 是否具备图文自动转 Markdown（send_qq_msg 的 allow_markdown 通路）。"""
    action = getattr(getattr(olivos, 'qqGuildv2SDK', None), 'event_action', None)
    if action is None:
        return False
    if hasattr(action, '_send_markdown_mixed_message'):
        return True
    sender = getattr(action, 'send_qq_msg', None)
    if sender is None:
        return False
    try:
        return 'allow_markdown' in inspect.signature(sender).parameters
    except (TypeError, ValueError):
        return False


def local_image_supported(event):
    """create_markdown_message 是否支持 local_images（图文 Markdown 的上传入口）。"""
    func = getattr(getattr(event, 'indeAPI', None), 'create_markdown_message', None)
    try:
        return 'local_images' in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _at_tag(olivos, para):
    tags = getattr(getattr(olivos, 'qqGuildv2SDK', None), 'markdown_tag', None)
    if tags is not None:
        try:
            # 不传可选参数，兼容各版本 at_para 的签名差异。
            return tags.at_para(para)
        except Exception as error:
            raise NotApplicable('at 段无法转换为 Markdown') from error
    user_id = str(para.data.get('id', ''))
    if user_id == 'all':
        return _AT_ALL
    if user_id == '':
        return ''
    return f'<qqbot-at-user id="{user_id}" />'


def _image_resource(para):
    """取图片段的资源字符串，取值口径与 OlivOS 的 ``_get_message_resource`` 一致。

    ``local_images`` 只接受路径 / URL / base64 字符串：直接传消息段对象会被
    ``str()`` 成字典字面量，随后当成不存在的本地文件读取，OlivOS 只能静默
    退回普通图文（HUD 的 font 标签会原样显示）。
    """
    data = getattr(para, 'data', None)
    if not isinstance(data, dict):
        return None
    for key in ('path', 'url', 'file'):
        value = data.get(key)
        if value is None:
            continue
        value = str(value)
        if value not in ('', 'None'):
            return value
    return None


def degraded(result):
    """OlivOS 素材上传失败后自行退回普通图文时的原因，未降级返回 None。"""
    data = result.get('data') if isinstance(result, dict) else None
    if not isinstance(data, dict):
        return None
    reason = data.get('markdown_fallback')
    return str(reason) if reason else None


def _hud_block(lines):
    # 只把尖括号转义掉，避免状态栏里的 < > 被当成 HTML 标签；
    # 不动 & —— 手机端不解析 HTML 实体时会把 &amp; 原样显示出来。
    return '\n'.join(f'{HUD_PREFIX}{line.replace("<", "&lt;").replace(">", "&gt;")}' for line in lines)


def _compose(lines, body):
    block = _hud_block(lines)
    # QQ 的 Markdown 里单 \n 不产生换行；块引用必须用空行收尾，
    # 否则正文会被懒续行并进引用块，整段跟着变成引用样式。
    return f'{block}\n\n{body}' if body else block


def _as_templet(olivos, event, message, mode=None):
    if isinstance(message, olivos.messageAPI.Message_templet):
        return message
    if mode is None:
        mode = getattr(event, 'plugin_info', {}).get('message_mode_tx', 'old_string')
    return olivos.messageAPI.Message_templet(mode, message)


def build(olivos, event, lines, message):
    """构造 Markdown 内容；不能安全转换时抛 NotApplicable。

    文本/at 直接进入 Markdown；图片仅在版本支持 ``local_images`` 且具备图文
    自动转 Markdown 时以占位符形式带上，其余消息段一律保留原通路。
    """
    templet = _as_templet(olivos, event, message)
    if not templet.active:
        raise NotApplicable('消息无法解析')
    parts = []
    quote_id = None
    local_images = {}
    for para in templet.data:
        if isinstance(para, olivos.messageAPI.PARA.text):
            parts.append(str(para.data.get('text', '')))
        elif isinstance(para, olivos.messageAPI.PARA.at):
            parts.append(_at_tag(olivos, para))
        elif isinstance(para, olivos.messageAPI.PARA.reply):
            if quote_id is None:
                value = para.data.get('id')
                if value is not None and str(value) != '':
                    quote_id = str(value)
        elif isinstance(para, olivos.messageAPI.PARA.image):
            if not (local_image_supported(event) and mixed_supported(olivos)):
                raise NotApplicable('当前 OlivOS 不支持图文 Markdown')
            resource = _image_resource(para)
            if resource is None:
                raise NotApplicable('图片段没有可上传的资源')
            name = _IMAGE_NAME % len(local_images)
            local_images[name] = resource
            parts.append('{{' + name + '}}')
        else:
            raise NotApplicable('Markdown 不支持该消息段')
    if local_images and quote_id is not None:
        # 与 OlivOS 图文 Markdown 一致：带引用的图文不转 Markdown。
        raise NotApplicable('带引用的图文消息不走 Markdown')
    body = ''.join(parts)
    if body.strip() == '':
        raise NotApplicable('没有可发送的文本段')
    return Content(_compose(lines, body), quote_id, local_images)


def build_core(olivos, event, lines, message):
    """按 Core 的 markdown 通路拆分文本与媒体，返回 (Content, 媒体消息或 None)。"""
    templet = _as_templet(olivos, event, message, 'old_string')
    if not templet.active:
        raise NotApplicable('消息无法解析')
    parts = []
    plain_parts = []
    quote_id = None
    for para in templet.data:
        if isinstance(para, olivos.messageAPI.PARA.at):
            parts.append(_at_tag(olivos, para))
        elif isinstance(para, olivos.messageAPI.PARA.text):
            parts.append(str(para.data.get('text', '')))
        elif isinstance(para, olivos.messageAPI.PARA.reply):
            if quote_id is None:
                value = para.data.get('id')
                if value is not None and str(value) != '':
                    quote_id = str(value)
        else:
            # 图片、表情等媒体继续走普通消息通道，与 Core 原实现一致。
            plain_parts.append(para)
    body = ''.join(parts)
    if body.strip() == '' and quote_id is not None:
        plain_parts.insert(0, olivos.messageAPI.PARA.reply(id=quote_id))
    media = None
    if plain_parts:
        media = olivos.messageAPI.Message_templet('olivos_para', plain_parts)
    return Content(_compose(lines, body), quote_id, {}), media


def send(event, context, content, active=False):
    """发送 Markdown；失败或接口不识别参数时返回 None，由调用方回退。"""
    kwargs = {
        'chat_type': context[0],
        'chat_id': context[1],
        'markdown': {'content': content.text},
    }
    if content.local_images:
        kwargs['local_images'] = content.local_images
    if content.quote_id and not active:
        # 主动发送不复用当前事件的引用；跨会话引用也可能被平台拒绝。
        kwargs['quote_msg_id'] = content.quote_id
    if active:
        # Event.send 是主动发送语义，不复用当前事件的被动回复凭据。
        kwargs['force_active'] = True
    # 被动回复不显式传 msg_id：交给适配层按事件解析 msg_id/event_id，
    # 与普通消息通路一致，也遵循 qq_passive_reply_disabled 等会话开关。
    result = event.indeAPI.create_markdown_message(**kwargs)
    if isinstance(result, dict) and result.get('active', False):
        return result
    return None
