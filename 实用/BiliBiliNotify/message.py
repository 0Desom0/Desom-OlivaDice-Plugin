from datetime import date
import time

from . import config, function, notify, store, utils
from .message_custom import TEXT

TOP_ALIASES = {'主播': 'up', '帮助': 'help', '推送': 'push', '全体': 'atall', '状态': 'status', '测试': 'test'}
UP_ALIASES = {
    '主播添加': 'add', '主播删除': 'del', '主播列表': 'list',
    '直播': 'live', '动态': 'dynamic', '视频': 'video',
    '订阅': 'sub', '取消订阅': 'unsub', '我的订阅': 'subs',
}
UP_ACTIONS = frozenset(UP_ALIASES.values())
KINDS_BY_LABEL = {label: kind for kind, label in config.LABELS.items()}
ON_OFF = {'on': True, 'off': False}
MANAGED = {'add', 'del', 'live', 'dynamic', 'video', 'push', 'atall', 'test'}


def parse_action(argument):
    """使用模板切词器逐级拆主动作、up 子动作、UID 和 on/off。"""
    action, rest = utils.split_first_token(argument)
    action = TOP_ALIASES.get(action, action.lower())
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
    if action in config.KINDS or action == 'push':
        return action, (first, second), bool(first and second and not excess)
    if action in ('add', 'del', 'sub', 'unsub', 'atall', 'test'):
        return action, (first,), bool(first and not second)
    if action in ('', 'help', 'list', 'subs', 'status'):
        return action or 'help', (), not first
    return '', (), False


def _identity(uid, room_id, name=''):
    if name:
        name = name.replace('[', '［').replace('<', '＜').replace('\r', ' ').replace('\n', ' ')
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


def _overview(action, bot_hash, sid, user_id, settings, target, prefix):
    if action == 'help':
        return TEXT['help'].format(prefix=prefix)
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


def _group_switch(action, args, bot_hash, target, settings, prefix):
    if action == 'push':
        kind = KINDS_BY_LABEL.get(args[0], args[0].lower())
        if kind not in config.KINDS:
            return False, TEXT['help'].format(prefix=prefix)
    value = ON_OFF.get(args[-1].lower())
    if value is None:
        return False, TEXT['help'].format(prefix=prefix)
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
    return True, TEXT['atall_on'].format(limit=at_all['daily_limit'], qq=qq)


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
            return False, TEXT['help'].format(prefix=prefix)
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

    if plugin_event.plugin_info.get('func_type') == 'private_message':
        if getattr(plugin_event.data, 'extend', {}).get('chat_type') != 'guild_private':
            utils.reply_message(plugin_event, TEXT['private'])
        return
    target = utils.target_from_event(plugin_event)
    if not target:  # qqGuildv2 频道及无群 ID 事件一律不响应。
        return

    prefix = command_info['prefix']
    action, args, complete = parse_action(command_info['command_argument'])
    if not complete:
        utils.reply_message(plugin_event, TEXT['help'].format(prefix=prefix))
        return
    if action in MANAGED and not utils.sender_can_manage(plugin_event):
        utils.reply_message(plugin_event, TEXT['denied'])
        return

    sid = function.sid_for(target)
    user_id = utils.get_sender_id_from_event(plugin_event)
    if action in ('help', 'list', 'subs', 'status'):
        success, text = True, _overview(action, config_bot_hash, sid, user_id, settings, target, prefix)
    elif action in ('push', 'atall'):
        success, text = _group_switch(action, args, config_bot_hash, target, settings, prefix)
    else:
        success, text = _up_command(action, args, config_bot_hash, target, user_id, prefix, Proc)
    if success and sid not in store.rooms(config_bot_hash)['groups']:
        with store.edit_rooms(config_bot_hash) as data:
            function.ensure_group(data, settings, target)
    if text:
        utils.reply_message(plugin_event, text)
