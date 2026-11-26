"""通过 OlivOS 菜单事件提供订阅推送管理面板。"""

import base64
import re
import time
from datetime import date
from urllib.parse import urlsplit

import OlivOS

from . import bili_api, config, function, notify, store

_GROUP_TYPES = {('onebot', 'qq'): 'group', ('qqGuildv2_link', 'qqGuild'): 'qq_group'}
_POLL_LABELS = {
    'live_seconds': '直播轮询间隔',
    'dynamic_seconds': '动态轮询间隔',
    'video_seconds': '视频轮询间隔',
    'max_concurrent': '最大并发请求数',
    'max_sockets': '直播间长连接上限',
    'live_relaxed_seconds': '长连接在线时的直播轮询间隔',
}
_IMAGES = {'.jpg': 'jpeg', '.png': 'png', '.gif': 'gif', '.webp': 'webp', '.avif': 'avif', '.bmp': 'bmp'}
_MAX_PREVIEW = 512 * 1024
_GLOBAL_ACTIONS = {'get_state', 'save_global', 'refresh_buvid', 'probe_api',
                   'qr_generate', 'qr_poll'}


class _InvalidRequest(ValueError):
    pass


def _obj(value, label):
    if not isinstance(value, dict):
        raise _InvalidRequest(f'{label}必须为对象。')
    return value


def _list(value, label):
    if not isinstance(value, list):
        raise _InvalidRequest(f'{label}必须为列表。')
    return value


def _text(value, label):
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise _InvalidRequest(f'{label}必须为不含控制字符的文本。')
    return value.strip()


def _bool(value, label):
    if type(value) is not bool:
        raise _InvalidRequest(f'{label}必须为布尔开关。')
    return value


def _int(value, label, minimum, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        span = f'{minimum} 至 {maximum} 的整数' if maximum is not None else f'不小于 {minimum} 的整数'
        raise _InvalidRequest(f'{label}必须为 {span}。')
    return value


def _flags(value, label):
    fields = _obj(value, label)
    return {kind: _bool(fields.get(kind), f'{label} · {config.LABELS[kind]}') for kind in config.KINDS}


def _kind(payload, choices=config.KINDS):
    kind = payload.get('kind')
    if kind not in choices:
        raise _InvalidRequest('请选择有效的推送或自检类型。')
    return kind


def _uid(value):
    uid = _text(value, '主播 UID')
    if not re.fullmatch(r'[0-9]{1,20}', uid) or not uid.strip('0'):
        raise _InvalidRequest('请输入有效的数字 UID，不是直播间号。')
    return uid.lstrip('0')


def _id(value, platform, label):
    text = _text(value, label)
    if platform == 'qq':
        if re.fullmatch(r'[0-9]{1,20}', text) and text.strip('0'):
            return text.lstrip('0')
        raise _InvalidRequest(f'{label}须为有效的 QQ 数字 ID。')
    if platform == 'qqGuild' and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', text):
        return text
    raise _InvalidRequest(f'{label}须为有效的 QQ 群平台 OpenID。')


def _bot_pair(bot_info):
    platform = getattr(bot_info, 'platform', {})
    return (platform.get('sdk', ''), platform.get('platform', '')) if isinstance(platform, dict) else ('', '')


def _target(value):
    sid = _text(value, '群标识')
    parts = sid.split('|')
    if len(parts) != 3 or tuple(parts[:2]) not in _GROUP_TYPES:
        raise _InvalidRequest('群标识格式为 SDK|平台|群 ID，如 onebot|qq|123456。')
    sdk, platform, group_id = parts
    group_id = _id(group_id, platform, '群 ID')
    return {'sdk': sdk, 'platform': platform, 'group_id': group_id, 'chat_type': _GROUP_TYPES[sdk, platform]}


def _group_matches(group, target):
    return all(group.get(key) == value for key, value in target.items())


def _group_target(payload, bot_hash, bot_info, *, create=False):
    target = _target(payload.get('sid'))
    sid = function.sid_for(target)
    if (target['sdk'], target['platform']) != _bot_pair(bot_info):
        raise _InvalidRequest('群的平台与所选 Bot 不匹配。')
    saved = store.rooms(bot_hash)['groups'].get(sid)
    if saved is not None:
        if not _group_matches(saved, target):
            raise _InvalidRequest('频道不支持群订阅，请选用 QQ 群。')
    elif not create:
        raise _InvalidRequest('群尚未登记，请先到「群订阅」添加。')
    elif target['chat_type'] == 'qq_group':
        # QQ 官方群与频道共用 SDK，只有宿主确认见过的 QQ 群才能新建。
        group = OlivOS.qqGuildv2SDK.qqStore.get_group(bot_hash, target['group_id'])
        if not group or group.get('state') != 'active':
            raise _InvalidRequest('未识别到此 QQ 群，请先在群内向 Bot 发送消息，再核对群 OpenID。')
    return sid, target


def _bot_map(Proc):
    data = getattr(Proc, 'Proc_data', {})
    bots = data.get('bot_info_dict', {}) if isinstance(data, dict) else {}
    if not isinstance(bots, dict):
        return {}
    return {
        key: value for key, value in bots.items()
        if isinstance(key, str) and re.fullmatch(r'[\w-]+', key, re.ASCII)
    }


def _global_view():
    settings = store.global_config()
    # 凭据只发布已配置状态；不发送原文、片段、缓存 Cookie 或代理地址。
    return {
        'cookie': {key: bool(settings['cookie'][key]) for key in config.GLOBAL_DEFAULT['cookie']},
        'user_agent': settings['user_agent'],
        'proxy': bool(settings['proxy']),
        'whitelist': settings['whitelist'],
        'buvid_cache': {
            'configured': bool(settings['buvid_cache']['cookie']),
            'fetched_at': settings['buvid_cache']['fetched_at'],
        },
        'log_to_file': settings['log_to_file'],
    }


def _view_room(bot_hash, uid, room):
    runtime = room['runtime']
    checks = {'live': runtime, **{kind: room[kind] for kind in ('dynamic', 'video')}}
    return {
        'uid': uid,
        'name': function.names.get((bot_hash, uid)) or f'UID {uid}',
        'room_id': room['room_id'],
        'enabled': {kind: room[kind]['enabled'] for kind in config.KINDS},
        'live_status': runtime['live_status'],
        'has_cover': bool(runtime['last_cover']),
        'last_checks': {kind: check['last_check_at'] for kind, check in checks.items()},
        'last_errors': {kind: check.get('last_error', '') for kind, check in checks.items()},
        'targets': {
            sid: {**{kind: target[kind] for kind in config.KINDS}, 'subscribers': target['subscribers']}
            for sid, target in room['targets'].items()
        },
    }


def _view_group(sid, group, pair, disabled, today):
    quota = group['at_quota']
    sdk, platform = pair
    group_id = group['group_id']
    supported = (
        (sdk, platform) in _GROUP_TYPES
        and sid == f'{sdk}|{platform}|{group_id}'
        and _group_matches(group, {
            'sdk': sdk, 'platform': platform, 'chat_type': _GROUP_TYPES[pair], 'group_id': group_id,
        })
    )
    return {
        'group_id': group_id,
        'platform': group['platform'],
        'push': group['push'],
        'at_all': group['at_all'],
        'used': quota['used'] if quota['date'] == today else 0,
        'last_at_live_time': quota['last_at_live_time'],
        'disabled': sid in disabled,
        'supported': supported,
    }


def _state(bots, bot_hash):
    state = {
        'bots': [
            {'hash': key, 'name': str(getattr(info, 'name', '') or getattr(info, 'id', '') or '未命名 Bot'),
             'sdk': _bot_pair(info)[0], 'platform': _bot_pair(info)[1]}
            for key, info in bots.items()
        ],
        'bot_hash': bot_hash,
        'global': _global_view(),
        'bot': None,
        'rooms': {},
        'groups': {},
        'status': None,
        'logs': store.recent_logs()[-20:],
    }
    if not bot_hash:
        return state
    today = date.today().isoformat()
    bot = store.bot_config(bot_hash)
    data = store.rooms(bot_hash)
    pair = _bot_pair(bots[bot_hash])
    state.update(
        bot={key: bot[key] for key in config.BOT_DEFAULT if key != 'configured_master_list'},
        # 命令名固定在代码里，不落盘：旧配置里残留的 command_name 不再影响解析与显示。

        rooms={uid: _view_room(bot_hash, uid, room) for uid, room in data['rooms'].items()},
        groups={
            sid: _view_group(sid, group, pair, bot['disabled_group_list'], today)
            for sid, group in data['groups'].items()
        },
        status=notify.status(bot_hash),
    )
    state['bot']['command_name'] = config.COMMAND_NAME
    return state


def _proxy(value):
    proxy = _text(value, '代理')
    if not proxy:
        return ''
    try:
        parsed = urlsplit(proxy)
        if (not any(char.isspace() for char in proxy) and parsed.scheme in ('http', 'https')
                and parsed.hostname and parsed.port != 0 and parsed.path in ('', '/') and not parsed.query
                and not parsed.fragment):
            return proxy
    except ValueError:
        raise _InvalidRequest('代理地址或端口无效。') from None
    raise _InvalidRequest('请输入 http://主机:端口 或 https://主机:端口 格式的代理，或清空以直连。')


def _whitelist(value):
    entries = []
    seen = set()
    for raw in _list(value, '白名单'):
        entry = _obj(raw, '白名单条目')
        platform = entry.get('platform')
        if platform not in ('qq', 'qqGuild'):
            raise _InvalidRequest('白名单平台只能是 OneBot QQ 或 QQ 官方群。')
        user_id = _id(entry.get('user_id'), platform, '白名单用户 ID')
        key = (platform, user_id.casefold())
        if key not in seen:
            entries.append({'platform': platform, 'user_id': user_id})
            seen.add(key)
    return entries


def _save_global(payload):
    changes = {}
    if 'user_agent' in payload:
        changes['user_agent'] = _text(payload['user_agent'], 'User-Agent')
        if any(ord(char) > 255 for char in changes['user_agent']):
            raise _InvalidRequest('User-Agent 只能包含 HTTP 请求头支持的字符。')
    if 'proxy' in payload:
        changes['proxy'] = _proxy(payload['proxy'])
    if 'whitelist' in payload:
        changes['whitelist'] = _whitelist(payload['whitelist'])
    if 'log_to_file' in payload:
        changes['log_to_file'] = _bool(payload['log_to_file'], '文件日志')
    credentials = {}
    if 'cookie' in payload:
        cookie = _obj(payload['cookie'], 'Cookie')
        for key in config.GLOBAL_DEFAULT['cookie'].keys() & cookie.keys():
            if key == 'b_nut':
                credentials[key] = _int(cookie[key] if cookie[key] != '' else 0, key, 0)
            else:
                value = _text(cookie[key], key)
                if any(not 33 <= ord(char) <= 126 or char == ';' for char in value):
                    raise _InvalidRequest(f'{key} 只接受单个 Cookie 字段值，不要粘贴整段 Cookie。')
                credentials[key] = value
    with store.edit_global() as settings:
        updated_cookie = {**settings['cookie'], **credentials}
        if updated_cookie != settings['cookie'] or any(settings[key] != value for key, value in changes.items()):
            settings.update(changes, cookie=updated_cookie,
                            meta={'updated_at': int(time.time()), 'updated_by': 'WebUI'})


def _prefixes(value):
    prefixes = _list(value, '命令前缀')
    if any(not isinstance(item, str) or len(item) != 1 or item.isspace()
           or 0xD800 <= ord(item) <= 0xDFFF for item in prefixes):
        raise _InvalidRequest('每个命令前缀必须是单个非空白字符。')
    return list(dict.fromkeys(prefixes))


def _disabled_list(value):
    return list(dict.fromkeys(function.sid_for(_target(sid)) for sid in _list(value, '禁用群列表')))


def _update_bot(bot_hash, changes):
    with store.edit_bot(bot_hash) as settings:
        if any(settings[key] != value for key, value in changes.items()):
            settings.update(changes, meta={'updated_at': int(time.time())})


def _save_bot(payload, bot_hash):
    changes = {}
    if 'enable' in payload:
        changes['enable'] = _bool(payload['enable'], 'Bot 总开关')
    if 'prefix_list' in payload:
        changes['prefix_list'] = _prefixes(payload['prefix_list'])
    if 'poll' in payload:
        poll = _obj(payload['poll'], '轮询设置')
        changes['poll'] = {
            'live_seconds': _int(poll.get('live_seconds'), _POLL_LABELS['live_seconds'], 1),
            'dynamic_seconds': _int(poll.get('dynamic_seconds'), _POLL_LABELS['dynamic_seconds'], 1),
            'video_seconds': _int(poll.get('video_seconds'), _POLL_LABELS['video_seconds'], 1),
            'max_concurrent': _int(poll.get('max_concurrent'), _POLL_LABELS['max_concurrent'], 1, 32),
            # 0 表示关闭长连接、完全用轮询
            'max_sockets': _int(poll.get('max_sockets'), _POLL_LABELS['max_sockets'], 0, 32),
            'live_relaxed_seconds': _int(poll.get('live_relaxed_seconds'),
                                         _POLL_LABELS['live_relaxed_seconds'], 0, 3600),
        }
    if 'retry' in payload:
        retry = payload['retry']
        if not isinstance(retry, dict):
            raise ValueError('重试必须是 JSON 对象')
        changes['retry'] = {
            'max_times': _int(retry.get('max_times'), '重试次数', 0, 10),
            'interval_ms': _int(retry.get('interval_ms'), '重试间隔', 0, 60000),
        }
    if 'auto_follow' in payload:
        changes['auto_follow'] = _bool(payload['auto_follow'], '自动关注')
    if 'dynamic_source' in payload:
        source = payload['dynamic_source']
        if source not in ('follow', 'poll'):
            raise _InvalidRequest('动态来源只能是 follow 或 poll。')
        changes['dynamic_source'] = source
    if 'at_all' in payload:
        at_all = _obj(payload['at_all'], '@全体设置')
        changes['at_all'] = {
            'daily_limit': _int(at_all.get('daily_limit'), '@全体每日配额', 0),
            'guild_at_once': _bool(at_all.get('guild_at_once'), 'QQ 官方群每次开播仅 @全体一次'),
        }
    if 'at_subscribers' in payload:
        subscribers = _obj(payload['at_subscribers'], '@订阅者')
        for kind in ('dynamic', 'video'):
            if kind in subscribers and _bool(subscribers[kind], config.LABELS[kind] + ' @订阅者'):
                raise _InvalidRequest('仅直播开播可 @订阅者。')
        changes['at_subscribers'] = dict.fromkeys(config.KINDS, False)
        changes['at_subscribers']['live'] = _bool(subscribers.get('live'), '开播 @订阅者')
    if 'push_default' in payload:
        changes['push_default'] = _flags(payload['push_default'], '新群推送默认设置')
    if 'send_interval_seconds' in payload:
        changes['send_interval_seconds'] = _int(payload['send_interval_seconds'], '连续发送间隔', 1)
    if 'disabled_group_list' in payload:
        changes['disabled_group_list'] = _disabled_list(payload['disabled_group_list'])
    _update_bot(bot_hash, changes)


def _save_group(payload, bot_hash, bot_info):
    sid, target = _group_target(payload, bot_hash, bot_info, create=True)
    push = _flags(payload['push'], '群推送') if 'push' in payload else None
    at_all = _bool(payload['at_all'], '@全体') if 'at_all' in payload else None
    disabled = _bool(payload['disabled'], '禁用群') if 'disabled' in payload else None
    if push is not None or at_all is not None or sid not in store.rooms(bot_hash)['groups']:
        settings = store.bot_config(bot_hash)
        with store.edit_rooms(bot_hash) as data:
            group = function.ensure_group(data, settings, target)
            if push is not None:
                group['push'] = push
            if at_all is not None:
                group['at_all'] = at_all
    if disabled is not None:
        with store.edit_bot(bot_hash) as settings:
            disabled_sids = settings['disabled_group_list']
            if disabled and sid not in disabled_sids:
                disabled_sids.append(sid)
                settings['meta']['updated_at'] = int(time.time())
            elif not disabled and sid in disabled_sids:
                disabled_sids.remove(sid)
                settings['meta']['updated_at'] = int(time.time())


def _up_action(action, payload, Proc, bot_hash, bot_info):
    uid = _uid(payload.get('uid'))
    sid, target = _group_target(payload, bot_hash, bot_info) if 'sid' in payload else (None, None)
    # sid 缺省时管理本 Bot 的主播；指定 sid 时仅管理群里的目标及订阅者。
    if action == 'add_up':
        types = _flags(payload['types'], '主播类型') if 'types' in payload else None
        result, _, _ = function.add_up(bot_hash, uid, target, 'WebUI', types)
        if result == 'duplicate':
            raise _InvalidRequest('该群已关联此主播。' if sid else '此主播已添加到当前 Bot。')
        if result == 'missing':
            raise _InvalidRequest('未查到主播。请核对 UID，或先在「总账号」运行接口自检。')
    elif action == 'remove_up':
        if function.remove_up(bot_hash, uid, sid) is None:
            raise _InvalidRequest('未找到要移除的主播，请刷新后重试。')
    elif action == 'toggle_up':
        kind = _kind(payload)
        value = _bool(payload.get('value'), '主播开关')
        if sid is None:
            if not function.toggle_up(bot_hash, uid, kind, value):
                raise _InvalidRequest('主播已移除，请刷新后重试。')
        else:
            with store.edit_rooms(bot_hash) as data:
                group_target = data['rooms'].get(uid, {}).get('targets', {}).get(sid)
                if group_target is None:
                    raise _InvalidRequest('此群未关联该主播，请先关联。')
                group_target[kind] = value
    elif action in ('add_subscriber', 'remove_subscriber'):
        if target is None:
            raise _InvalidRequest('请先选择订阅者所在群。')
        user_id = _id(payload.get('user_id'), target['platform'], '订阅者 ID')
        if not function.set_subscriber(bot_hash, uid, sid, user_id, action == 'add_subscriber'):
            raise _InvalidRequest('此群未关联该主播，请先关联。')
    else:
        targets = None
        if sid is not None:
            linked = store.rooms(bot_hash)['rooms'].get(uid, {}).get('targets', {}).get(sid)
            if not linked:
                raise _InvalidRequest('此群未关联该主播，请先关联。')
            targets = (linked,)
        result = notify.test_push(Proc, bot_hash, uid, _kind(payload), targets)
        errors = {
            'missing': '主播已移除，请刷新后重试。',
            'empty': '没有可推送的内容或接收群，请确认 Bot 已启用、已关联群且群未被禁用。',
            'failed': '测试推送未全部成功，请查看「运行状态」中的日志。',
        }
        if result != 'ok':
            raise _InvalidRequest(errors[result])


def _cover(bot_hash, uid):
    cover_url = store.rooms(bot_hash)['rooms'].get(uid, {}).get('runtime', {}).get('last_cover')
    if not cover_url:
        raise _InvalidRequest('暂未取得直播封面，请等待下一次成功检查。')
    path = bili_api.download_image(cover_url)
    if path is None:
        raise _InvalidRequest('无法载入封面，请稍后再试。')
    try:
        image_type = _IMAGES.get(path.suffix.lower())
        if not image_type:
            raise _InvalidRequest('此封面格式无法安全预览。')
        with path.open('rb') as file:
            content = file.read(_MAX_PREVIEW + 1)
        # 回包会在宿主的事件缓冲中保留，限制单次预览体积。
        if len(content) > _MAX_PREVIEW:
            raise _InvalidRequest('封面超过面板预览上限（512 KiB），不影响实际推送。')
        encoded = base64.b64encode(content).decode('ascii')
        return {'image': f'data:image/{image_type};base64,{encoded}'}
    except OSError:
        raise _InvalidRequest('无法读取封面缓存，请稍后再试。') from None
    finally:
        bili_api.release_image(path)


def _qr_image(url):
    """把登录地址渲染成二维码 PNG，直接内联给前端（不走外链）。"""
    try:
        import base64
        import io

        import qrcode
    except ImportError:
        raise _InvalidRequest('服务器缺少 qrcode 库，无法生成二维码；可以直接手填 Cookie。')
    image = qrcode.make(url)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def _qr_generate():
    data, error = bili_api.qr_generate()
    if error:
        raise _InvalidRequest('申请二维码失败（%s）：%s' % (error[0], error[1]))
    url = str(data.get('url') or '')
    key = str(data.get('qrcode_key') or '')
    if not url or not key:
        raise _InvalidRequest('二维码接口返回格式异常。')
    return {'ok': True, 'state': {'qr': {'qrcode_key': key, 'image': _qr_image(url)}}}


def _qr_poll(payload):
    """轮询扫码状态；成功后把凭据写进 global.json 并停用旧指纹缓存。"""
    key = payload.get('qrcode_key')
    if not isinstance(key, str) or not key or len(key) > 128:
        raise _InvalidRequest('缺少有效的二维码标识。')
    data, error = bili_api.qr_poll(key)
    if error:
        raise _InvalidRequest('查询扫码状态失败（%s）：%s' % (error[0], error[1]))
    code = data.get('code')
    if code != 0:
        return {'ok': True, 'state': {'qr': {'status': int(code) if isinstance(code, int) else -1,
                                             'message': str(data.get('message') or '')}}}
    pairs = bili_api.parse_login_cookie(str(data.get('url') or ''))
    if not pairs.get('sessdata'):
        raise _InvalidRequest('登录成功但没拿到 SESSDATA，请重试。')
    with store.edit_global() as settings:
        settings['cookie']['sessdata'] = pairs['sessdata']
        settings['cookie']['bili_jct'] = pairs.get('bili_jct', '')
        # 旧指纹属于上一个会话，清掉让下一次请求重新领。
        settings['buvid_cache'] = {'cookie': '', 'fetched_at': 0.0}
        settings['meta'] = {'updated_at': int(time.time()), 'updated_by': '扫码登录'}
    return {'ok': True, 'state': {'qr': {'status': 0, 'message': '登录成功',
                                         'uid': pairs.get('dede_user_id', '')}}}


def dispatch(payload, Proc):
    """校验请求并返回显式构建的、安全可序列化的页面状态。"""
    payload = _obj(payload, '请求数据')
    action = payload.get('action')
    if not isinstance(action, str):
        raise _InvalidRequest('缺少有效的面板操作。')
    bots = _bot_map(Proc)
    bot_hash = payload.get('bot_hash', '')
    if not isinstance(bot_hash, str) or (bot_hash and bot_hash not in bots):
        raise _InvalidRequest('所选 Bot 已不可用，请刷新账号列表。')
    if not bot_hash:
        if action not in _GLOBAL_ACTIONS:
            raise _InvalidRequest('请先从面板上方选择一个 Bot。')
        bot_hash = next(iter(bots), '')
    if action == 'qr_generate':
        return _qr_generate()
    if action == 'qr_poll':
        return _qr_poll(payload)
    if action == 'save_global':
        _save_global(payload)
    elif action == 'save_bot':
        _save_bot(payload, bot_hash)
    elif action == 'save_group':
        _save_group(payload, bot_hash, bots[bot_hash])
    elif action in ('add_up', 'remove_up', 'toggle_up', 'add_subscriber', 'remove_subscriber', 'test_push'):
        _up_action(action, payload, Proc, bot_hash, bots[bot_hash])
    elif action == 'refresh_buvid':
        _, error = bili_api.refresh_buvid()
        if error:
            raise _InvalidRequest(f'领取指纹失败（{error[0]}）：{error[1]}。请检查网络和代理设置。')
    elif action == 'probe_api':
        # 只返回请求层的安全摘要，不返回接口响应体。
        probe = bili_api.probe(_kind(payload, (*config.KINDS, 'nav')), _uid(payload.get('uid', '2')))
        return {'ok': True, 'state': {'code': probe['code'], 'summary': probe['summary']}}
    elif action == 'get_cover':
        return {'ok': True, 'state': _cover(bot_hash, _uid(payload.get('uid')))}
    elif action != 'get_state':
        raise _InvalidRequest('无法识别此面板操作，请刷新页面后重试。')
    return {'ok': True, 'state': _state(bots, bot_hash)}


def handle_menu_event(plugin_event, Proc):
    data = getattr(plugin_event, 'data', None)
    if getattr(data, 'namespace', None) != config.PLUGIN_NAME:
        return
    context = getattr(data, 'webui', None)
    if not isinstance(context, dict):
        return
    request_id = context.get('request_id')
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        return
    try:
        if getattr(data, 'event', None) != config.WEBUI_EVENT:
            raise _InvalidRequest('未知的 WebUI 事件，请重新打开面板。')
        response = dispatch(getattr(data, 'payload', None), Proc)
    except _InvalidRequest as error:
        response = {'ok': False, 'error': str(error)}
    except store.StorageError:
        response = {'ok': False, 'error': '写入失败，检查目录权限，再刷新确认当前状态。'}
    except Exception as error:
        # 不记录 payload、异常原文、会话或凭据。
        store.log(Proc, f'WebUI 操作失败：{type(error).__name__}', level=3)
        response = {'ok': False, 'error': '面板操作失败，请刷新确认并查看「运行状态」的日志。'}
    try:
        if plugin_event.send('webui', request_id, response) is not True:
            store.log(Proc, 'WebUI 回包未能入队。', level=3)
    except Exception as error:
        store.log(Proc, f'WebUI 回包失败：{type(error).__name__}', level=3)
