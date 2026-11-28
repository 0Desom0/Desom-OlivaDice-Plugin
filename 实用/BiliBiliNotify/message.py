from datetime import date
from math import ceil
from threading import Lock
import time

from . import capabilities, config, function, live_stats, notify, sender, store, utils
from .message_custom import TEXT

TOP_ALIASES = {'主播': 'up', '帮助': 'help', '推送': 'push', '全体': 'atall', '状态': 'status', '测试': 'test'}
UP_ALIASES = {
    '主播添加': 'add', '主播删除': 'del', '主播列表': 'list',
    '直播': 'live', '动态': 'dynamic', '视频': 'video',
    '订阅': 'sub', '取消订阅': 'unsub', '我的订阅': 'subs',
}
UP_ACTIONS = frozenset(UP_ALIASES.values())
KINDS_BY_LABEL = {label: kind for kind, label in config.LABELS.items()}
HELP_ALIASES = {'订阅': 'sub', '推送': 'push', '统计': 'stats'}
OVERRIDE_VALUES = {'on': True, 'off': False, 'auto': None, '默认': None}
ON_OFF = {'on': True, 'off': False}
MANAGED = {'add', 'del', 'live', 'dynamic', 'video', 'push', 'dynamic_img', 'session_push', 'atall', 'test'}
SESSION_IMAGE_ALIASES = {'直播报告': 'report', '词云': 'cloud', '弹幕词云': 'cloud'}
STATS_ALIASES = {'房间统计': 'room', '个人统计': 'me', '绑定': 'bind', '排行': 'rank', **SESSION_IMAGE_ALIASES}
STATS_ACTIONS = frozenset(STATS_ALIASES.values())
RANK_FIELDS = {'danmu': 'danmu', 'gift': 'gift_gold', 'sc': 'sc_gold', 'box': 'box_profit',
               'entry': 'entry', 'like': 'like'}
RANK_ALIASES = {'弹幕': 'danmu', '礼物': 'gift', '盲盒': 'box', '进场': 'entry', '进房': 'entry', '点赞': 'like'}
RANK_SCOPES = {'本场': 'session', 'session': 'session', '总榜': 'total', 'total': 'total'}
PAID_RANKS = frozenset(('gift', 'sc', 'box'))
SESSION_SCOPES = {'live': 'stats_live_scope', 'pending_end': 'stats_pending_scope', 'ended': 'stats_recent_scope'}

_stats_lock = Lock()
_stats_last = {}
_stats_pending = set()


def _parse_stats(action, argument):
    feature = config.LIVE_IMAGES[action][0] if action in config.LIVE_IMAGES else 'live_stats'
    if not capabilities.can(feature):
        return None, (), False
    argument = argument.strip()
    if action == 'room' or action in config.LIVE_IMAGES:
        return action, (_unquote(argument),), True
    if action == 'me' and argument.startswith('"'):
        name, quote, room = argument[1:].partition('"')
        complete = bool(quote and name.strip() and (not room or room[0].isspace()))
        return action, (name.strip(), _unquote(room.strip())), complete
    first, rest = utils.split_first_token(argument)
    if action == 'me':
        return action, (first, _unquote(rest)), True
    if action == 'bind':
        return action, (first,), bool(first and not rest)
    dimension = RANK_ALIASES.get(first, first.lower())
    token, remainder = utils.split_first_token(rest)
    scope = RANK_SCOPES.get(token.lower())
    return action, (dimension, scope or 'session', _unquote(remainder if scope else rest)), dimension in RANK_FIELDS


def _unquote(value):
    return value[1:-1].strip() if len(value) >= 2 and value.startswith('"') and value.endswith('"') else value


def parse_action(argument):
    """使用模板切词器逐级拆主动作、up 子动作、UID 和 on/off。"""
    action, rest = utils.split_first_token(argument)
    action = TOP_ALIASES.get(action, action.lower())
    action = STATS_ALIASES.get(action, action)
    if action in STATS_ACTIONS:
        return _parse_stats(action, rest)
    if action == 'up':
        action, rest = utils.split_first_token(rest)
        action = UP_ALIASES.get(action, action.lower())
        if action not in UP_ACTIONS:
            return '', (), False
    elif action in UP_ALIASES:
        action = UP_ALIASES[action]
    elif action not in ('help', 'push', 'atall', 'status', 'test', ''):
        return '', (), False

    first, rest = utils.split_first_token(rest)
    second, excess = utils.split_first_token(rest)
    if action == 'push' and (first.lower() == 'dynamic_img' or first == '动态图片'):
        if not capabilities.can('dynamic_image'):
            return None, (), False
        return 'dynamic_img', (second.lower(),), bool(second and not excess)
    if action == 'push' and (kind := SESSION_IMAGE_ALIASES.get(first, first.lower())) in config.LIVE_IMAGES:
        if not capabilities.can(config.LIVE_IMAGES[kind][0]):
            return None, (), False
        return 'session_push', (kind, second.lower()), bool(second and not excess)
    if action == 'help' and first:
        section = HELP_ALIASES.get(first, first.lower())
        if section == 'stats' and not capabilities.can('live_stats'):
            return None, (), False
        return action, (section,), section in ('sub', 'push', 'stats') and not second
    if action in config.KINDS or action == 'push':
        return action, (first, second), bool(first and second and not excess)
    if action in ('add', 'del', 'sub', 'unsub', 'atall', 'test'):
        return action, (first,), bool(first and not second)
    if action in ('', 'help', 'list', 'subs', 'status'):
        return action or 'help', (), not first
    return '', (), False


def _image_help(prefix, section):
    return ''.join(TEXT[f'help_{section}_{kind}'].format(prefix=prefix)
                   for kind, (feature, _, _) in config.LIVE_IMAGES.items() if capabilities.can(feature))


def _help(prefix, section=''):
    if section == 'sub':
        return TEXT['help_sub'].format(prefix=prefix)
    if section == 'push':
        image = TEXT['help_dynamic_image'].format(prefix=prefix) if capabilities.can('dynamic_image') else ''
        return TEXT['help_push'].format(prefix=prefix, dynamic_image=image, session_images=_image_help(prefix, 'push'))
    if section == 'stats' and capabilities.can('live_stats'):
        return TEXT['help_stats'].format(prefix=prefix, session_images=_image_help(prefix, 'stats'))
    stats = TEXT['help_stats_entry'].format(prefix=prefix) if capabilities.can('live_stats') else ''
    return TEXT['help'].format(prefix=prefix, stats=stats)


def _safe_text(value):
    return value.replace('[', '［').replace('<', '＜').replace('\r', ' ').replace('\n', ' ')


def _identity(uid, room_id, name=''):
    if name:
        name = _safe_text(name)
        room = TEXT['identity_room'].format(room_id=room_id) if room_id else ''
        return TEXT['identity'].format(name=name, uid=uid, room=room)
    return TEXT['uid_room'].format(uid=uid, room_id=room_id) if room_id else TEXT['uid'].format(uid=uid)


def _switch(value):
    return TEXT['enabled' if value else 'disabled']


def _summary(switches, separator, template):
    return separator.join(TEXT[template].format(label=config.LABELS[kind], state=_switch(switches[kind]))
                          for kind in config.KINDS)


def _elapsed(timestamp):
    if not timestamp:
        return TEXT['never']
    elapsed = max(0, int(time.time() - timestamp))
    if elapsed < 60:
        return TEXT['seconds_ago'].format(count=elapsed)
    return TEXT['minutes_ago'].format(count=elapsed // 60)


def _status(bot_hash, data, group, count, limit):
    checks = notify.status(bot_hash)['last_checks']
    quota = group['at_quota']
    used = quota['used'] if quota['date'] == date.today().isoformat() else 0
    if group['sdk'] == 'qqGuildv2_link':
        used, limit = int(bool(quota['last_at_live_time'])), 1
    return TEXT['status'].format(
        total=len(data['rooms']), local=count, used=used, limit=limit,
        checks='\n'.join(TEXT['last_check'].format(label=config.LABELS[kind], elapsed=_elapsed(checks.get(kind)))
                         for kind in config.KINDS),
    )


def _overview(action, args, bot_hash, sid, user_id, settings, target, prefix):
    if action == 'help':
        return _help(prefix, *args)
    data = store.rooms(bot_hash)
    local = [(uid, room) for uid, room in data['rooms'].items() if sid in room['targets']]
    if action == 'status':
        group = data['groups'].get(sid)
        return _status(bot_hash, data, group or {'sdk': target['sdk'], 'at_quota': {
            'date': '', 'used': 0, 'last_at_live_time': 0,
        }}, len(local), settings['at_all']['daily_limit'])
    if action == 'subs':
        subscribed = [_identity(uid, room['room_id']) for uid, room in local
                      if user_id in room['targets'][sid]['subscribers']]
        return '\n'.join([TEXT['subs_head'].format(count=len(subscribed)),
                          *(TEXT['subs_item'].format(identity=item) for item in subscribed)])
    if not local:
        return TEXT['list_empty'].format(prefix=prefix)
    lines = [TEXT['list_head'].format(count=len(local))]
    for index, (uid, room) in enumerate(local, 1):
        configured = room['targets'][sid]
        effective = {kind: room[kind]['enabled'] and configured[kind] for kind in config.KINDS}
        lines.append(TEXT['list_item'].format(
            index=index, identity=_identity(uid, room['room_id'], function.names.get((bot_hash, uid), '')),
            switches=_summary(effective, ' ', 'switch_set'), count=len(configured['subscribers']),
        ))
    return '\n'.join(lines)


def _group_switch(action, args, bot_hash, target, settings, prefix, plugin_event=None):
    if action in ('dynamic_img', 'session_push'):
        requested = args[-1]
        if requested not in OVERRIDE_VALUES:
            return False, _help(prefix, 'push')
        value = OVERRIDE_VALUES[requested]
        field = 'dynamic_image' if action == 'dynamic_img' else args[0]
        with store.edit_rooms(bot_hash) as data:
            function.ensure_group(data, settings, target)[field] = value
        state = 'auto' if value is None else 'on' if value else 'off'
        if action == 'dynamic_img':
            return True, TEXT[f'dynamic_image_{state}']
        return True, TEXT[f'session_push_{state}'].format(label=config.LIVE_IMAGES[field][2])
    if action == 'push':
        kind = KINDS_BY_LABEL.get(args[0], args[0].lower())
        if kind not in config.KINDS:
            return False, _help(prefix, 'push')
    value = ON_OFF.get(args[-1].lower())
    if value is None:
        return False, _help(prefix, 'push')
    with store.edit_rooms(bot_hash) as data:
        group = function.ensure_group(data, settings, target)
        if action == 'push':
            group['push'][kind] = value
        else:
            group['at_all'] = value
    if action == 'push':
        state = TEXT['switch_on' if value else 'switch_off']
        return True, TEXT['push_toggle'].format(label=config.LABELS[kind], state=state)
    if not value:
        return True, TEXT['atall_off']
    at_all = settings['at_all']
    qq = TEXT['atall_qq_once' if at_all['guild_at_once'] else 'atall_qq_any']
    reply = TEXT['atall_on'].format(limit=at_all['daily_limit'], qq=qq)
    if plugin_event is not None and not sender.event_bot_is_group_admin(
        plugin_event, target['group_id'], sdk=target['sdk'],
    ):
        reply += '\n' + TEXT['atall_not_admin_hint']
    return True, reply


def _up_command(action, args, bot_hash, target, user_id, prefix, Proc):
    uid = function.extract_uid(args[0])
    if not uid:
        return False, TEXT['bad_uid'].format(prefix=prefix)
    sid = function.sid_for(target)
    missing = TEXT['subscription_missing'].format(uid=uid)
    if action == 'add':
        status, name, room_id = function.add_up(bot_hash, uid, target, user_id)
        if status == 'missing':
            return False, TEXT['up_missing'].format(uid=uid)
        if status == 'duplicate':
            return False, TEXT['duplicate']
        group = store.rooms(bot_hash)['groups'][sid]
        at_all = _switch(group['at_all'])
        if not group['at_all']:
            at_all += TEXT['at_all_hint'].format(prefix=prefix)
        return True, TEXT['added'].format(identity=_identity(uid, room_id, name), at_all=at_all,
                                          switches=_summary(group['push'], ' · ', 'switch_summary'))
    if action == 'del':
        count = function.remove_up(bot_hash, uid, sid)
        return (False, missing) if count is None else (True, TEXT['removed'].format(uid=uid, count=count))
    if action in config.KINDS:
        value = ON_OFF.get(args[1].lower())
        if value is None:
            return False, _help(prefix, 'sub')
        if not function.toggle_up(bot_hash, uid, action, value, sid):
            return False, missing
        return True, TEXT['up_toggle'].format(uid=uid, label=config.LABELS[action],
                                              state=TEXT['switch_on' if value else 'switch_off'])
    if action in ('sub', 'unsub'):
        if not function.set_subscriber(bot_hash, uid, sid, user_id, action == 'sub'):
            return False, missing
        return True, TEXT['subscribed' if action == 'sub' else 'unsubscribed'].format(uid=uid)
    # 测试推送不改检测状态和配额，由当前 Bot 主动发给命令所在群。
    status = notify.test_push(Proc, bot_hash, uid, 'live', targets=(target,))
    if status == 'ok':
        return True, ''
    if status == 'missing':
        return False, missing
    return False, TEXT['test_empty' if status == 'empty' else 'test_failed']


def _streamer_name(bot_hash, uid):
    return function.names.get((bot_hash, uid)) or live_stats.cached_name(uid)


def _match_streamers(bot_hash, local, selector):
    if not selector:
        return tuple(local)
    uid = function.extract_uid(selector)
    if uid in local:
        return (uid,)
    key = selector.casefold()
    return tuple(uid for uid in local if key in _streamer_name(bot_hash, uid).casefold())


def _duration(seconds):
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = ((hours, '小时'), (minutes, '分'), (seconds, '秒'))
    return ''.join(f'{value}{unit}' for value, unit in parts if value) or '0秒'


def _gold(value):
    # 金瓜子保留至千分之一元，避免浮点舍入或截断。
    yuan, fraction = divmod(abs(value), 1000)
    digits = f'{fraction:03d}'
    return f'{"-" if value < 0 else ""}¥{yuan}.{digits[:2] if fraction % 10 == 0 else digits}'


def _revenue(data):
    return TEXT['stats_revenue'].format(**{
        key: _gold(data[key]) for key in ('gold', 'gift_gold', 'sc_gold', 'guard_gold')
    })


def _room_stats(uid, room_id, name, hide_revenue):
    summary = live_stats.room_summary(uid, room_id)
    session, total = summary['session'], summary['total']
    identity = _identity(uid, room_id, name or (session['uname'] if session else ''))
    lines = [TEXT['stats_room_head'].format(identity=identity)]
    if session is None:
        return False, '\n'.join([*lines, TEXT['stats_empty_room']])
    scope = TEXT[SESSION_SCOPES[session['status']]]
    lines.append(TEXT['stats_session_duration'].format(scope=scope, duration=_duration(session['duration'])))
    for key in ('title', 'area'):
        if session[key]:
            lines.append(TEXT[f'stats_{key}'].format(**{key: _safe_text(session[key])}))
    lines.extend(TEXT[key].format(**session) for key in ('stats_danmu', 'stats_interactions', 'stats_peaks'))
    if not hide_revenue:
        lines.append(_revenue(session))
    average = f"{total['avg_danmu']:.2f}".rstrip('0').rstrip('.')
    lines.extend((
        TEXT['stats_total_duration'].format(sessions=total['sessions'], duration=_duration(total['duration'])),
        TEXT['stats_room_total'].format(danmu=total['danmu'], avg_danmu=average),
    ))
    if not hide_revenue:
        lines.append(_revenue(total))
    return True, '\n'.join(lines)


def _user_stats(uid, viewer, identity, hide_revenue):
    viewer_uid = function.extract_uid(viewer)
    summary = live_stats.user_summary(uid, user_uid=viewer_uid, user_name='' if viewer_uid else viewer)
    if summary is None:
        return False, TEXT['stats_empty_user']
    lines = [TEXT['stats_user_head'].format(viewer=_identity(summary['uid'], '', summary['uname']), identity=identity)]
    for key in ('session', 'total'):
        data = summary[key] or {}
        if key == 'session' and data:
            scope = TEXT[SESSION_SCOPES[data['status']]]
        else:
            scope = TEXT[f'stats_{key}_scope']
        lines.append(TEXT['stats_user_activity'].format(
            scope=scope, danmu=data.get('danmu', 0), entry=data.get('entry', 0), like=data.get('like', 0),
        ))
        if data and not hide_revenue:
            lines.extend((_revenue(data), TEXT['stats_box_profit'].format(profit=_gold(data['box_profit']))))
        ranks = summary['ranks'][key]
        positions = []
        for dimension, field in RANK_FIELDS.items():
            if hide_revenue and dimension in PAID_RANKS:
                continue
            if rank := ranks.get(field):
                positions.append(TEXT['stats_user_rank'].format(label=TEXT[f'stats_rank_{dimension}'], position=rank))
        if positions:
            lines.append(TEXT['stats_user_ranks'].format(ranks=' · '.join(positions)))
    return True, '\n'.join(lines)


def _rank_stats(uid, dimension, scope, identity):
    rows = live_stats.room_ranking(uid, dimension, scope=scope, limit=10)
    lines = [TEXT['stats_rank_head'].format(
        identity=identity, scope=TEXT[f'stats_rank_{scope}'], label=TEXT[f'stats_rank_{dimension}'],
    )]
    if not rows:
        return False, '\n'.join([*lines, TEXT['stats_empty_rank']])
    lines.extend(TEXT['stats_rank_item'].format(
        index=index, identity=_identity(row['uid'], '', row['uname']),
        value=_gold(row['value']) if dimension in PAID_RANKS else row['value'],
    ) for index, row in enumerate(rows, 1))
    return True, '\n'.join(lines)


def _image_stats(kind, uid, room, settings, Proc, bot_hash, target):
    session_id = live_stats.current_session_id(uid, room['room_id'])
    if session_id is None:
        return False, TEXT['stats_empty_session_image']
    detail = live_stats.session_detail(session_id, include_danmu=kind == 'cloud')
    if detail is None:
        return False, TEXT['stats_empty_session_image']
    detail['avatar_url'] = room['runtime'].get('avatar_url', '')
    try:
        path = function.render_session_image(kind, detail, settings)
    except Exception as error:
        store.log(Proc, f'直播资料图片渲染失败：{type(error).__name__}: {error}', 3)
        return False, TEXT['stats_image_failed']
    if path is None:
        return False, TEXT['stats_empty_cloud' if kind == 'cloud' else 'stats_image_failed']
    try:
        success = sender.send_local_image(Proc, bot_hash, target, path, '')
        return success, '' if success else TEXT['stats_image_failed']
    finally:
        sender.release_local_image(path)


def _lookup_stats(action, args, bot_hash, target, user_id, prefix, settings, Proc):
    sid = function.sid_for(target)
    local = {uid: room for uid, room in store.rooms(bot_hash)['rooms'].items() if sid in room['targets']}
    hide_revenue = settings['hide_revenue']
    if not local:
        return False, TEXT['list_empty'].format(prefix=prefix)
    selector = args[-1]
    matches = None
    if action == 'me':
        viewer = args[0]
        if not viewer or not selector:
            bound = live_stats.get_bound_uid(target['platform'], user_id)
            if bound and viewer and not selector:
                # 单参数匹配本群主播时，绑定账号作为观众；双参数可显式指定两者。
                if matches := _match_streamers(bot_hash, local, viewer):
                    viewer, selector = bound, viewer
                else:
                    matches = None
            viewer = viewer or bound
        if not viewer:
            return False, TEXT['stats_bind_hint'].format(prefix=prefix)
    if matches is None:
        matches = _match_streamers(bot_hash, local, selector)
    if not matches:
        return False, TEXT['stats_streamer_hint'].format(prefix=prefix)
    if len(matches) > 1:
        key = 'stats_streamer_ambiguous' if selector else 'stats_streamer_choose'
        choices = '、'.join(matches[:5])
        if len(matches) > 5:
            choices += TEXT['stats_more_streamers'].format(count=len(matches))
        return False, TEXT[key].format(choices=choices)
    uid = matches[0]
    room_id = local[uid]['room_id']
    if action in config.LIVE_IMAGES:
        return _image_stats(action, uid, local[uid], settings, Proc, bot_hash, target)
    name = _streamer_name(bot_hash, uid)
    if action == 'room':
        return _room_stats(uid, room_id, name, hide_revenue)
    identity = _identity(uid, room_id, name)
    if action == 'me':
        return _user_stats(uid, viewer, identity, hide_revenue)
    dimension, scope, _ = args
    return _rank_stats(uid, dimension, scope, identity)


def _stats_command(action, args, bot_hash, target, user_id, settings, prefix, Proc):
    if not settings['enabled']:
        return TEXT['stats_disabled']
    if action == 'bind':
        if not user_id:
            return TEXT['stats_bind_sender']
        uid = function.extract_uid(args[0])
        if not uid:
            return TEXT['stats_bind_uid'].format(prefix=prefix)
        live_stats.bind_user(target['platform'], user_id, uid)
        return TEXT['stats_bound'].format(uid=uid, prefix=prefix)
    hide_revenue = settings['hide_revenue']
    if action == 'rank' and hide_revenue and args[0] in PAID_RANKS:
        return TEXT['stats_private_revenue']
    key = bot_hash, function.sid_for(target)
    with _stats_lock:
        last = _stats_last.get(key)
        if last is not None:
            seconds = ceil(settings['query_cooldown_seconds'] - (time.monotonic() - last))
            if seconds > 0:
                return TEXT['stats_cooldown'].format(seconds=seconds)
        if key in _stats_pending:
            return TEXT['stats_pending']
        _stats_pending.add(key)
    success = False
    try:
        success, text = _lookup_stats(action, args, bot_hash, target, user_id, prefix, settings, Proc)
        return text
    finally:
        with _stats_lock:
            if success:
                _stats_last[key] = time.monotonic()
            _stats_pending.remove(key)


@utils.log_exception('handle_message')
def handle_message(plugin_event, Proc):
    config_bot_hash = utils.ensure_runtime_storage_by_event(plugin_event, Proc)
    if not utils.check_core_group_enable(plugin_event):
        return
    original_message_text = utils.get_message_text_from_event(plugin_event)
    cleaned_message_text = utils.strip_reply_segment(original_message_text)
    at_item_list, remaining_after_at = utils.parse_at_segments(cleaned_message_text, allow_multi=True)
    if at_item_list and not utils.is_force_reply_to_current_bot(at_item_list, plugin_event):
        return
    settings = store.bot_config(config_bot_hash)
    command_info = utils.parse_command(remaining_after_at, prefix_list=settings['prefix_list'], allow_no_prefix=False)
    if not command_info['is_command'] or command_info['command_name'] != config.COMMAND_NAME:
        return
    if not settings['enable'] or utils.is_group_disabled(plugin_event):
        return

    prefix = command_info['prefix']
    action, args, complete = parse_action(command_info['command_argument'])
    if action is None:
        return

    if plugin_event.plugin_info.get('func_type') == 'private_message':
        if getattr(plugin_event.data, 'extend', {}).get('chat_type') != 'guild_private':
            utils.reply_message(plugin_event, TEXT['private'])
        return
    target = utils.target_from_event(plugin_event)
    if not target:  # qqGuildv2 频道及无群 ID 事件一律不响应。
        return

    if not complete:
        section = (
            'stats' if action in STATS_ACTIONS
            else 'push' if action in ('push', 'dynamic_img', 'session_push') else ''
        )
        utils.reply_message(plugin_event, _help(prefix, section))
        return
    if action in MANAGED and not utils.sender_can_manage(plugin_event):
        utils.reply_message(plugin_event, TEXT['denied'])
        return

    sid = function.sid_for(target)
    user_id = utils.get_sender_id_from_event(plugin_event)
    if action in STATS_ACTIONS:
        text = _stats_command(
            action, args, config_bot_hash, target, user_id, settings['live_stats'], prefix, Proc,
        )
        if text:
            utils.reply_message(plugin_event, text)
        return
    if action in ('help', 'list', 'subs', 'status'):
        success, text = True, _overview(action, args, config_bot_hash, sid, user_id, settings, target, prefix)
    elif action in ('push', 'dynamic_img', 'session_push', 'atall'):
        success, text = _group_switch(action, args, config_bot_hash, target, settings, prefix, plugin_event)
    else:
        success, text = _up_command(action, args, config_bot_hash, target, user_id, prefix, Proc)
    if success and sid not in store.rooms(config_bot_hash)['groups']:
        with store.edit_rooms(config_bot_hash) as data:
            function.ensure_group(data, settings, target)
    if text:
        utils.reply_message(plugin_event, text)
