"""QQ 群/C2C 发送；凭据池和临时图片通过构造参数注入。"""

import re
from contextlib import nullcontext
from types import SimpleNamespace

import OlivOS
from OlivOS.adapter.qqGuild.qqGuildv2SDKCommon import _resolve_qq_reference_msg_idx

from . import errors


class StreamMessage(OlivOS.qqGuildv2SDK.api_templet):
    def __init__(self, bot_info, chat_id):
        super().__init__()
        sdk = OlivOS.qqGuildv2SDK
        self.bot_info = bot_info
        self.host = sdk.sdkAPIHost['default']
        self.route = sdk.sdkAPIRoute['qq_users'] + '/{openid}/stream_messages'
        self.metadata = SimpleNamespace(openid=str(chat_id))
        self.data = SimpleNamespace(
            input_mode='append',
            input_state=10,
            index=0,
            content_type=None,
            content_raw=None,
            event_id=None,
            msg_id=None,
            msg_seq=None,
            stream_msg_id=None,
            is_wakeup=None,
        )


class Sender:
    """event 是对应 bot 的 fake API Event；pool/media 可独立注入。"""

    def __init__(self, event, pool=None, media=None):
        self.event = event
        self.sent_images = []
        self.pool = pool
        self.media = media
        self.sdk = OlivOS.qqGuildv2SDK
        self.action = self.sdk.event_action

    def _api(self, chat_type, chat_id):
        bot = self.sdk.get_SDK_bot_info_from_Event(self.event)
        if chat_type == 'qq_group':
            api = self.sdk.API.sendQQMessage(bot)
            api.metadata.group_openid = str(chat_id)
        else:
            api = self.sdk.API.sendQQDirectMessage(bot)
            api.metadata.openid = str(chat_id)
        return api

    def _dispatch(self, api, chat_type, chat_id, token):
        msg_id = token['id_value'] if token and token['id_type'] == 'msg_id' else None
        event_id = token['id_value'] if token and token['id_type'] == 'event_id' else None
        # 明确禁止 SDK 提前回退主动；失败交由本模块换下一条凭据。
        return self.action._send_qq_api(
            self.event,
            api,
            chat_type,
            chat_id,
            msg_id,
            event_id,
            allow_active_fallback=False,
        )

    def _tokens(self, bot_hash, chat_type, chat_id, force):
        if force or self.pool is None:
            return []
        return self.pool.candidates(bot_hash, chat_type, chat_id)

    def _attempt(self, payload, make_api, stream=False, stream_parts=None):
        bot_hash = payload['bot_hash']
        chat_type, chat_id = payload['chat_type'], payload['chat_id']
        lock = self.pool.send_lock(bot_hash, chat_type, chat_id) if self.pool else nullcontext()
        with lock:
            tokens = self._tokens(bot_hash, chat_type, chat_id, payload.get('force_active', False))
            for token in [*tokens, None]:
                api = make_api()
                if token and not self.pool.mark_used(
                    bot_hash,
                    chat_type,
                    chat_id,
                    token['id_type'],
                    token['id_value'],
                ):
                    continue
                raw = self._dispatch(api, chat_type, chat_id, token)
                channel = 'stream' if stream else ('passive' if token else 'active')
                result = errors.result(raw, channel)
                if result['ok']:
                    if stream_parts and len(stream_parts) > 1:
                        return self._finish_stream(payload, make_api, api, result, stream_parts)
                    return result, api.res_code
                data = raw.get('data') or {}
                local = data.get('error') or ''
                code = result['error_code']
                invalid = code in {
                    304103,
                    40034005,
                    40034024,
                    40034025,
                    40034026,
                    40034027,
                    40034031,
                    40034128,
                    40054005,
                }
                invalid = invalid or local in {
                    'passive reply count exceeded',
                    'passive reply sequence cache is full',
                    'passive event reply count exceeded',
                    'passive event reply cache is full',
                }
                if token and invalid:
                    self.pool.invalidate(bot_hash, chat_type, chat_id, token['id_type'], token['id_value'])
                    continue
                return result, api.res_code
        return errors.failure('未知错误'), None

    def _finish_stream(self, payload, make_api, first_api, first_result, parts):
        """同一条流只消耗一次被动凭据和 SDK 消息序号。"""
        message_id = first_result['message_id']
        ref_idx = first_result['ref_idx']
        if not message_id:
            result = errors.failure('发送异常', '流式首片未返回消息ID')
            result.update(channel='stream', ref_idx=ref_idx, stream_started=True)
            return result, first_api.res_code
        for index, part in enumerate(parts[1:], 1):
            try:
                api = make_api()
                api.data.index = index
                api.data.input_state = 10 if index == len(parts) - 1 else 1
                api.data.content_raw = part
                api.data.stream_msg_id = message_id
                api.data.msg_id = first_api.data.msg_id
                api.data.event_id = first_api.data.event_id
                api.data.msg_seq = first_api.data.msg_seq
                api.do_api()
                raw = self.action._make_api_result(
                    self.event, api, payload['chat_type'], payload['chat_id'], 'send',
                )
                result = errors.result(raw, 'stream')
            except Exception:
                result = errors.failure('发送异常')
                result.update(channel='stream', message_id=message_id, ref_idx=ref_idx, stream_started=True)
                return result, None
            result['message_id'] = message_id
            result['ref_idx'] = result['ref_idx'] or ref_idx
            ref_idx = result['ref_idx']
            if not result['ok']:
                result['stream_started'] = True
                return result, api.res_code
        return result, api.res_code

    def send(self, payload):
        self.sent_images = []
        try:
            return self._send(payload)
        except ValueError as exc:
            text = str(exc)
            known = {'图片已失效', '图片类型不支持', '图片过大', '图片上传失败'}
            return errors.failure(text if text in known else '参数无效', None if text in known else text)
        except Exception:
            return errors.failure('发送异常')
        finally:
            # abort 在同一把锁下检查所有权与占用状态，已消费或被其他发送占用的附件不受影响。
            if self.media is not None and isinstance(payload, dict):
                bot_hash = payload.get('bot_hash')
                images = payload.get('images')
                if bot_hash == self.event.bot_info.hash and isinstance(images, list):
                    ids = {
                        item.get('upload_id')
                        for item in images
                        if isinstance(item, dict) and isinstance(item.get('upload_id'), str)
                    }
                    for upload_id in ids:
                        try:
                            self.media.abort(upload_id, bot_hash)
                        except (ValueError, OSError):
                            pass

    def _send(self, payload):
        chat_type = payload.get('chat_type')
        chat_id = payload.get('chat_id')
        bot_hash = payload.get('bot_hash')
        if not chat_id:
            return errors.failure('未选目标')
        if chat_type not in ('qq_group', 'qq_private') or str(bot_hash) != str(self.event.bot_info.hash):
            return errors.failure('参数无效')
        kind = payload.get('kind', 'text')
        if kind not in ('text', 'markdown', 'card'):
            return errors.failure('消息类型无效')
        original_kind = kind
        images = payload.get('images') or []
        if not isinstance(images, list) or any(not isinstance(x, dict) or not x.get('upload_id') for x in images):
            return errors.failure('图片已失效')
        ids = [x['upload_id'] for x in images]
        if len(set(ids)) != len(ids) or len(images) > (9 if kind == 'markdown' else 1):
            return errors.failure('图片数量错误')
        if images and self.media is None:
            return errors.failure('图片已失效')
        quote_id = payload.get('quote_id')
        if quote_id and not isinstance(quote_id, str):
            return errors.failure('引用ID无效')
        if kind == 'card':
            if images:
                return errors.failure('图文卡片不支持上传图片')
            error, card = self.action._validate_card_message(payload.get('card'))
            if error:
                return errors.failure('图文卡片参数错误', error)
            keyboard = payload.get('keyboard')
            error = self.action._validate_keyboard_permissions(keyboard, chat_type)
            if error:
                return errors.failure('键盘参数错误', error)
            if quote_id and not quote_id.startswith('REFIDX_'):
                quote_id = _resolve_qq_reference_msg_idx(self.event, chat_type, chat_id, quote_id)
                if not isinstance(quote_id, str) or not quote_id.startswith('REFIDX_'):
                    return errors.failure('引用ID无效', '无法将消息ID映射为引用索引')

            def card_api():
                api = self._api(chat_type, chat_id)
                api.data.msg_type = 8
                api.data.card = card
                api.data.keyboard = keyboard
                if quote_id:
                    api.data.message_reference = {'message_id': quote_id}
                return api

            return self._attempt(payload, card_api)[0]
        text = payload.get('markdown' if kind == 'markdown' else 'text', '')
        if not isinstance(text, str):
            return errors.failure('参数无效')
        at = payload.get('at') or []
        if not isinstance(at, list):
            return errors.failure('参数无效')
        tags = []
        for item in at:
            if not isinstance(item, dict) or not item.get('id'):
                return errors.failure('参数无效')
            identity = str(item['id'])
            if identity == 'all':
                if chat_type != 'qq_group' or not payload.get('at_all_confirmed'):
                    return errors.failure('无权限或未确认@全体')
                tags.append('<qqbot-at-everyone />')
            elif re.fullmatch(r'[A-Za-z0-9_-]+', identity):
                tags.append(self.sdk.markdown_tag.at_user(identity))
            else:
                return errors.failure('参数无效')
        if chat_type == 'qq_private' and re.search(r'<qqbot-at-everyone\s*/>', text, re.I):
            return errors.failure('无权限或未确认@全体')
        if re.search(r'<qqbot-at-everyone\s*/>', text, re.I) and not payload.get('at_all_confirmed'):
            return errors.failure('无权限或未确认@全体')
        if tags:
            text += (' ' if text else '') + ' '.join(tags)
            kind = 'markdown'
        if re.search(r'<qqbot-at-(?:user\b[^>]*|everyone\s*)/\s*>', text, re.I):
            kind = 'markdown'
        if quote_id and (kind == 'markdown' or (images and text.strip())):
            return errors.failure('请将引用转换为Markdown引用块')
        if quote_id and not quote_id.startswith('REFIDX_'):
            quote_id = _resolve_qq_reference_msg_idx(self.event, chat_type, chat_id, quote_id)
            if not isinstance(quote_id, str) or not quote_id.startswith('REFIDX_'):
                return errors.failure('引用ID无效', '无法将消息ID映射为引用索引')
        # 图片只允许通过上传标记，禁止任何 Markdown 图片语法和 HTML 图片。
        if re.search(r'!\s*\[', text) or re.search(r'<\s*img\b', text, re.I):
            return errors.failure('不支持图片URL')
        markers = []
        if images and original_kind == 'markdown':
            for image in images:
                marker = image.get('marker')
                if not isinstance(marker, str) or not re.fullmatch(r'img_[A-Za-z0-9_]+', marker):
                    return errors.failure('图片标记无效')
                if marker in markers or '{{' + marker + '}}' not in text:
                    return errors.failure('图片标记无效')
                markers.append(marker)
        # 正文长度不再本地拦截：QQ 官方机器人没有 3000 字上限，超长与否交给平台判定。
        if not text.strip() and not images:
            return errors.failure('内容为空')
        keyboard = payload.get('keyboard')
        error = self.action._validate_keyboard_permissions(keyboard, chat_type)
        if error:
            return errors.failure('键盘参数错误', error)
        if images and original_kind == 'text' and not text.strip() and keyboard is not None:
            return errors.failure('纯图片不支持键盘')
        context = self.media.sending(ids, bot_hash) if images else nullcontext([])
        with context as paths:
            if images:
                metadata = images if original_kind == 'markdown' else [{} for _ in images]
                self.sent_images = self.media.persist_sent(paths, metadata)
            if images and original_kind == 'text' and not text.strip():
                resource = self.action.setResourceUploadFast(
                    self.event,
                    paths[0],
                    chat_id,
                    'images',
                    'qq_groups' if chat_type == 'qq_group' else 'qq_users',
                )
                if not resource:
                    return errors.failure('图片上传失败')

                def make_api():
                    api = self._api(chat_type, chat_id)
                    api.data.msg_type = 7
                    api.data.media = {'file_info': resource}
                    if quote_id:
                        api.data.message_reference = {'message_id': quote_id}
                    return api

                return self._attempt(payload, make_api)[0]
            if images and original_kind == 'text':
                kind = 'markdown'
                markers = ['img_0']
                text += '\n{{img_0}}'
            uploaded = []
            if images:
                local_images = dict(zip(markers, paths, strict=True))
                replacements, uploaded, error = self.action._upload_markdown_images(self.event, local_images)
                if error:
                    if uploaded:
                        self.action._delete_markdown_images(self.event, uploaded)
                    return errors.failure('图片上传失败', error)
                text = self.action._replace_markdown_image_markers(text, replacements)
            cleanup_uploaded = False
            try:

                def ordinary():
                    api = self._api(chat_type, chat_id)
                    api.data.keyboard = keyboard
                    if quote_id:
                        api.data.message_reference = {'message_id': quote_id}
                    if kind == 'markdown':
                        api.data.msg_type = 2
                        api.data.markdown = {'content': text}
                    else:
                        api.data.msg_type = 0
                        api.data.content = text
                    return api

                if chat_type == 'qq_private' and not images and keyboard is None and not quote_id:
                    parts = [text[i:i + 500] for i in range(0, len(text), 500)] if kind == 'markdown' else [text]

                    def stream_api():
                        bot = self.sdk.get_SDK_bot_info_from_Event(self.event)
                        api = StreamMessage(bot, chat_id)
                        api.data.content_type = 'markdown' if kind == 'markdown' else 'text'
                        api.data.content_raw = parts[0]
                        api.data.input_state = 1 if len(parts) > 1 else 10
                        api.data.is_wakeup = True if payload.get('is_wakeup') is True else None
                        return api

                    result, status = self._attempt(payload, stream_api, stream=True, stream_parts=parts)
                    if (result['ok'] or result.get('stream_started') or result['error_code'] in (40007, 50002)
                            or status is None or status >= 500):
                        return result
                result, status = self._attempt(payload, ordinary)
                cleanup_uploaded = result['ok'] or (status is not None and status < 500)
                return result
            finally:
                if uploaded and cleanup_uploaded:
                    self.action._delete_markdown_images(self.event, uploaded)

    def recall(self, payload):
        try:
            if str(payload.get('bot_hash')) != str(self.event.bot_info.hash):
                return errors.failure('参数无效')
            chat_type, chat_id = payload.get('chat_type'), payload.get('chat_id')
            if chat_type not in ('qq_group', 'qq_private'):
                return errors.failure('参数无效')
            raw = self.action.delete_message(self.event, chat_type, chat_id, payload.get('message_id'))
            return errors.result(raw)
        except Exception:
            return errors.failure('撤回失败')
