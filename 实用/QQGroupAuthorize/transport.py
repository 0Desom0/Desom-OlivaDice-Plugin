"""使用参考项目 qqGuildv2SDK 现有上传、消息序号与 HTTP 封装。"""

import base64

import OlivOS

BODY = (
    '## 本群的授权页已生成。\n\n'
    '**仅群主可完成授权**，需要手机 QQ 9.2.90 及以上。\n\n'
    '打开后：\n\n'
    '1. 消息范围选「获取群内全部消息」。\n'
    '2. 打开「机器人主动在群聊内发言」。\n'
    '3. 再点「同意授权」。\n\n'
    '打不开时按图中的第二部分：群成员列表 → 机器人资料页 → 右上角齿轮，手动设置。'
)
# 下方旧正文和按钮构造仅作停用代码保留；main 中的调用已注释。
MANUAL_GUIDE = (
    '仅群主可设置，需要手机 QQ 9.2.90 及以上。\n'
    '仅限手机 QQ，电脑端目前不可用；低于该版本，请群主先更新 QQ。\n'
    '群成员列表 →「机器人」分组 → 机器人资料页 → 右上角齿轮。\n'
    '也可从群聊页面右上角菜单 → 聊天信息 → 群机器人 → 当前机器人的「管理」进入设置。\n'
    '消息范围选「获取群内全部消息」，打开「机器人主动在群聊内发言」。'
)


def authorization_keyboard(group_id):
    # 官方回调按钮 action.type=1；点击后 interaction.type=11 由参考项目 SDK 应答。
    return {
        'content': {
            'rows': [
                {
                    'buttons': [
                        {
                            'id': 'QQGroupAuthorize',
                            'render_data': {'label': '群主点此授权', 'visited_label': '群主点此授权', 'style': 1},
                            'action': {
                                'type': 1,
                                'permission': {'type': 1},
                                'data': str(group_id),
                                # 文档要求此字段为字符串；留空，不注入版本判断或自定义版本提示。
                                'unsupport_tips': '',
                            },
                        }
                    ],
                }
            ],
        },
    }


class GroupReply:
    def __init__(self, event, group_id, message_id=None, *, event_id=None):
        if bool(message_id) == bool(event_id):
            raise ValueError('Provide exactly one passive message or event ID')
        self.event = event
        self.group_id = group_id
        self.message_id = message_id
        self.event_id = event_id
        self.sdk = OlivOS.qqGuildv2SDK
        self.quote = None
        # 聊天命令引用当前触发消息；入群事件没有用户消息，不构造引用。
        if message_id:
            resolver = getattr(getattr(self.sdk, 'qqGuildv2SDKCommon', None), '_resolve_qq_reference_msg_idx', None)
            quote = resolver(event, 'qq_group', group_id, message_id) if resolver else None
            extend = getattr(event.data, 'extend', {}) or {}
            self.quote = quote or extend.get('qq_msg_idx') or message_id

    def send(self, **payload):
        api = self.sdk.API.sendQQMessage(self.sdk.get_SDK_bot_info_from_Event(self.event))
        api.metadata.group_openid = self.group_id
        for name, value in payload.items():
            setattr(api.data, name, value)
        api.data.message_reference = {'message_id': self.quote} if self.quote else None
        # msg_id 保留原消息的被动凭据，REFIDX 仅用于可见引用；不前置 @，也不主动重发。
        error = self.sdk.event_action._prepare_qq_passive_message(
            self.event,
            api,
            'qq_group',
            self.group_id,
            self.message_id,
            self.event_id,
        )
        if error is not None:
            return False
        api.do_api()
        result = self.sdk.event_action._make_api_result(self.event, api, 'qq_group', self.group_id, 'send')
        return isinstance(result, dict) and result.get('active') is True

    def text(self, text):
        try:
            return self.send(msg_type=0, content=text)
        except Exception:
            return False

    def image(self, data):
        try:
            # base64 输入也支持缓存写盘失败时直接使用本次生成的 PNG。
            file_info = self.sdk.event_action.setResourceUploadFast(
                self.event,
                'base64://' + base64.b64encode(data).decode('ascii'),
                self.group_id,
                type_path='images',
                type_chat='qq_groups',
                flag_send_msg=False,
            )
            if not file_info:
                return False
            # 图片正文为空，不追加 @、文字说明或换行。
            return self.send(msg_type=7, content='', media={'file_info': file_info})
        except Exception:
            return False

    def authorization(self):
        # 预留的旧入口；当前命令流程不调用。恢复时需改为真实 QQ 授权链接。
        return self.send(
            msg_type=2,
            markdown={'content': BODY},
            keyboard=authorization_keyboard(self.group_id),
        )
