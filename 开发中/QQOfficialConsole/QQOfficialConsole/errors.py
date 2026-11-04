"""QQ 官方控制台发送错误关键词。"""

CODES = {
    22006: '类型不匹配',
    304004: '无ARK权限',
    304036: '无Markdown权限',
    304061: '内容无效',
    304080: '文件无效',
    304103: '回复过期',
    305007: '键盘参数错误',
    340069: '消息类型无效',
    40007: '流式前缀冲突',
    40034006: '内容违规',
    40034008: 'Markdown空值',
    40034009: 'Markdown含换行',
    40034011: 'Markdown无效',
    40034005: '回复过期',
    40034024: 'msg_id无效',
    40034025: 'event_id无效',
    40034026: 'event_id无效',
    40034027: 'event_id无效',
    40034029: '键盘超限',
    40034100: '主动频控',
    40034101: '非群成员',
    40034105: '主动无权限',
    40034124: 'Markdown无效',
    40034127: '无Markdown权限',
    40034128: '被动次数超限',
    40054002: '机器人被禁言',
    40054003: '非群成员',
    40054004: '无好友关系',
    40054005: '消息去重',
    40054007: '消息过长',
    40054018: '消息过长',
    40054010: '不允许URL',
    40054013: '用户拒收',
    40054016: '机器人已下线',
    40061001: '撤回参数无效',
    40062003: '无撤回权限',
    40064004: '撤回超时',
    50001: '流式内部错误',
    50002: '流式频控',
    50055001: '发送异常',
    50055002: '发送异常',
    11253: '无接口权限',
}

LOCAL = {
    'chat_id is required': '未选目标',
    'force_active cannot be combined with msg_id or event_id': '主动被动冲突',
    'message recall window exceeded': '撤回超时',
    'message recall rate limit exceeded': '撤回频控',
    'passive reply count exceeded': '被动次数超限',
    'passive reply sequence cache is full': '被动次数超限',
    'passive event reply count exceeded': '被动次数超限',
    'passive event reply cache is full': '被动次数超限',
}


def result(raw, channel=None):
    """将 SDK universal_result 转换成桥接结果，不暴露原始响应。"""
    data = raw.get('data') or {}
    code = data.get('error_code')
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        pass
    ok = bool(raw.get('active'))
    pending = bool(data.get('pending_review'))
    error = str(data.get('error') or '')
    keyword = ('审核中' if pending else '成功') if ok else CODES.get(code, LOCAL.get(error, '未知错误'))
    response = data.get('response')
    response = response if isinstance(response, dict) else {}
    nested = response.get('data') if isinstance(response.get('data'), dict) else response
    ext = nested.get('ext_info') if isinstance(nested.get('ext_info'), dict) else {}
    output = {
        'ok': ok,
        'keyword': keyword,
        'error_code': code,
        'message_id': data.get('message_id'),
        'ref_idx': ext.get('ref_idx'),
        'channel': channel,
        'pending_review': pending,
    }
    if not ok and keyword == '未知错误' and error:
        output['message'] = error[:1000]
    return output


def failure(keyword, message=None):
    data = {
        'ok': False,
        'keyword': keyword,
        'error_code': None,
        'message_id': None,
        'ref_idx': None,
        'channel': None,
        'pending_review': False,
    }
    if message:
        data['message'] = str(message)[:1000]
    return data
