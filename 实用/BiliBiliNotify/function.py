import re
import time
from urllib.parse import urlsplit

from . import bili_api, config, store

# 昵称只在本代进程中保存，不进入 JSON。
names = {}


def extract_uid(value):
    text = str(value).strip()
    if re.fullmatch(r'[0-9]+', text):
        return text.lstrip('0')
    try:
        parsed = urlsplit(text)
        if parsed.scheme not in ('http', 'https') or parsed.hostname != 'space.bilibili.com':
            return ''
    except ValueError:
        return ''
    match = re.fullmatch(r'/([0-9]+)/?', parsed.path)
    return match[1].lstrip('0') if match else ''


def sid_for(target):
    return '|'.join(target[key] for key in ('sdk', 'platform', 'group_id'))


def ensure_group(data, settings, target):
    sid = sid_for(target)
    group = data['groups'].get(sid)
    if group is None:
        group = {
            **target,
            'push': dict(settings['push_default']),
            'at_all': False,
            'at_quota': {'date': '', 'used': 0, 'last_at_live_time': 0},
            'first_seen_at': int(time.time()),
        }
        data['groups'][sid] = group
    return group


def _stamp(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _feed_baseline(uid, kind, bound_at):
    if kind == 'dynamic':
        items, error = bili_api.dynamics(uid)
        useful = [item for item in (items or ()) if item.get('type') != 'DYNAMIC_TYPE_AV'
                  and ((item.get('modules') or {}).get('module_tag') or {}).get('text') != '置顶']

        def stamp(item):
            return _stamp(((item.get('modules') or {}).get('module_author') or {}).get('pub_ts'))

        identity, last_key = 'id_str', 'last_id'
    else:
        useful, error = bili_api.videos(uid)

        def stamp(item):
            return _stamp(item.get('created'))

        identity, last_key = 'bvid', 'last_bvid'

    latest = max(useful or (), key=stamp, default=None)
    return {
        'enabled': True,
        last_key: str(latest.get(identity) or '') if latest else '',
        'last_ts': stamp(latest) if latest else bound_at if error else 0,
        'last_check_at': 0 if error else bound_at,
        'fail_count': 0,
    }


def _initial_room(uid, profile, types):
    now = time.time()
    room_id = str(profile.get('room_id') or '')
    if room_id == '0':
        room_id = ''
    room = {
        'uid': uid, 'room_id': room_id, 'resolved_at': now,
        'live': {'enabled': True},
        'dynamic': _feed_baseline(uid, 'dynamic', now),
        'video': _feed_baseline(uid, 'video', now),
        'runtime': {
            'live_status': _stamp(profile.get('live_status')), 'last_live_time': _stamp(profile.get('live_time')),
            'last_area_v2_name': str(profile.get('area_v2_name') or ''),
            'last_title': str(profile.get('title') or ''),
            'last_cover': str(profile.get('cover_from_user') or ''),
            'last_check_at': 0, 'last_error': '', 'fail_count': 0,
        },
        'targets': {},
    }
    if types is not None:
        for kind in config.KINDS:
            room[kind]['enabled'] = types[kind]
    return room


def add_up(bot_hash, uid, target=None, added_by='', types=None):
    sid = sid_for(target) if target else None
    room = store.rooms(bot_hash)['rooms'].get(uid)
    nickname = names.get((bot_hash, uid), '')
    if room is not None and (sid is None or sid in room['targets']):
        return 'duplicate', nickname, room['room_id']

    initial = None
    if room is None or not room['room_id']:
        # 网络不占持久化锁；提交前再核对是否有并发绑定。
        profile = bili_api.resolve_up(uid)
        if profile is None and room is None:
            return 'missing', '', ''
        if profile is not None:
            nickname = str(profile.get('uname') or '') or nickname
            if room is None:
                initial = _initial_room(uid, profile, types)
    else:
        profile = None

    settings = store.bot_config(bot_hash)
    with store.edit_rooms(bot_hash) as data:
        current = data['rooms'].get(uid)
        if current is None:
            if initial is None:
                return 'missing', '', ''
            current = data['rooms'][uid] = initial
        elif sid is None or sid in current['targets']:
            return 'duplicate', nickname, current['room_id']
        if profile is not None and not current['room_id']:
            room_id = str(profile.get('room_id') or '')
            if room_id and room_id != '0':
                current['room_id'] = room_id
                current['resolved_at'] = time.time()
        if target:
            ensure_group(data, settings, target)
            switches = dict.fromkeys(config.KINDS, True) if types is None else types
            current['targets'][sid] = {
                **target,
                **{kind: switches[kind] for kind in config.KINDS},
                'subscribers': [], 'added_by': added_by, 'added_at': time.time(),
            }
        room_id = current['room_id']
    if nickname:
        names[bot_hash, uid] = nickname
    return 'added', nickname, room_id


def remove_up(bot_hash, uid, sid=None):
    with store.edit_rooms(bot_hash) as data:
        room = data['rooms'].get(uid)
        if room is None:
            return None
        if sid is None:
            count = sum(len(target['subscribers']) for target in room['targets'].values())
            del data['rooms'][uid]
        else:
            target = room['targets'].pop(sid, None)
            if target is None:
                return None
            count = len(target['subscribers'])
    if sid is None:
        names.pop((bot_hash, uid), None)
    return count


def toggle_up(bot_hash, uid, kind, value, sid=None):
    with store.edit_rooms(bot_hash) as data:
        room = data['rooms'].get(uid)
        if room is None or (sid is not None and sid not in room['targets']):
            return False
        room[kind]['enabled'] = value
    return True


def set_subscriber(bot_hash, uid, sid, user_id, value):
    with store.edit_rooms(bot_hash) as data:
        room = data['rooms'].get(uid)
        if room is None or sid not in room['targets']:
            return False
        subscribers = room['targets'][sid]['subscribers']
        matches = [item for item in subscribers if item.casefold() == user_id.casefold()]
        if value and not matches:
            subscribers.append(user_id)
        elif not value and matches:
            subscribers[:] = [item for item in subscribers if item.casefold() != user_id.casefold()]
    return True
