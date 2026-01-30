# -*- encoding: utf-8 -*-

import OlivOS
import os
import json
import time
from typing import Dict, List, Optional, Tuple

oliva_dice_core_available = False
try:
    import OlivaDiceCore
    oliva_dice_core_available = True
except Exception:
    oliva_dice_core_available = False

DATA_PATH = os.path.join('plugin', 'data', 'QQGroupForward')
DEFAULT_FILE = os.path.join(DATA_PATH, 'default.json')

COMMAND_PREFIXES = ('.群链', '。群链', '/群链')

# bot_hash -> (timestamp, {group_id: group_name})
_GROUP_LIST_CACHE: Dict[str, Tuple[float, Dict[str, str]]] = {}
_GROUP_LIST_TTL_SEC = 60


def _ensure_dirs() -> None:
    os.makedirs(DATA_PATH, exist_ok=True)


def _default_config() -> dict:
    return {
        # 全局开关（仅骰主可改）：关闭后不进行任何消息转发
        'global_enabled': True,
        # 是否使用人物卡显示（仅骰主可改）。需要 OlivaDiceCore。
        # 若未检测到 OlivaDiceCore，则即便为 True 也视为关闭。
        'pc_card_enabled': True,
        # 有向边：src_group_id -> [dst_group_id, ...]
        'edges': {},
        # 配置master：权限等同骰主（可管理群链、开关防刷等）
        'masters': [],
        # 防刷：同一条消息ID在短时间内只处理一次
        'dedup_enabled': True,
        'dedup_ttl_sec': 10,
    }


def _load_config() -> dict:
    _ensure_dirs()
    if not os.path.exists(DEFAULT_FILE):
        cfg = _default_config()
        _save_config(cfg)
        return cfg
    try:
        with open(DEFAULT_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError('config not dict')
    except Exception:
        cfg = _default_config()
        _save_config(cfg)
        return cfg

    # 补默认字段
    base = _default_config()
    changed = False
    for k, v in base.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    if 'edges' not in cfg or not isinstance(cfg.get('edges'), dict):
        cfg['edges'] = {}
        changed = True

    # 规范 masters
    if 'masters' not in cfg or not isinstance(cfg.get('masters'), list):
        cfg['masters'] = []
        changed = True
    else:
        cleaned = []
        seen = set()
        for x in cfg.get('masters', []):
            xs = str(x).strip()
            if not xs or xs in seen:
                continue
            seen.add(xs)
            cleaned.append(xs)
        if cleaned != cfg.get('masters', []):
            cfg['masters'] = cleaned
            changed = True

    # 清理历史字段（不再需要）
    for legacy_key in ['version', 'enabled']:
        if legacy_key in cfg:
            cfg.pop(legacy_key, None)
            changed = True

    if changed:
        _save_config(cfg)
    return cfg


def _save_config(cfg: dict) -> None:
    _ensure_dirs()
    with open(DEFAULT_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _norm_gid(gid) -> str:
    return str(gid).strip()


def _edge_list(cfg: dict, src_gid: str) -> List[str]:
    edges = cfg.get('edges', {})
    lst = edges.get(src_gid, [])
    if not isinstance(lst, list):
        lst = []
    # 去重保持顺序
    seen = set()
    out = []
    for x in lst:
        xs = _norm_gid(x)
        if not xs or xs in seen:
            continue
        seen.add(xs)
        out.append(xs)
    edges[src_gid] = out
    return out


def _add_edge(cfg: dict, src_gid: str, dst_gid: str) -> Tuple[bool, str]:
    if src_gid == dst_gid:
        return False, '不能连接同一个群。'
    out = _edge_list(cfg, src_gid)
    if dst_gid in out:
        return False, '已存在该连接（不能重复连接）。'
    out.append(dst_gid)
    cfg['edges'][src_gid] = out
    return True, '连接已添加。'


def _remove_edge(cfg: dict, src_gid: str, dst_gid: str) -> bool:
    out = _edge_list(cfg, src_gid)
    if dst_gid in out:
        out.remove(dst_gid)
        cfg['edges'][src_gid] = out
        return True
    return False


def _is_bidirectional(cfg: dict, a: str, b: str) -> bool:
    return b in _edge_list(cfg, a) and a in _edge_list(cfg, b)


def _is_dice_master(plugin_event, user_id: str) -> bool:
    if not oliva_dice_core_available:
        return False
    try:
        user_hash = OlivaDiceCore.userConfig.getUserHash(
            user_id,
            'user',
            plugin_event.platform['platform']
        )
        return bool(OlivaDiceCore.ordinaryInviteManager.isInMasterList(
            plugin_event.bot_info.hash,
            user_hash
        ))
    except Exception:
        return False


def _is_config_master(cfg: dict, user_id: str) -> bool:
    try:
        masters = cfg.get('masters', [])
        if not isinstance(masters, list):
            return False
        return str(user_id) in [str(x).strip() for x in masters]
    except Exception:
        return False


def _is_privileged_master(plugin_event, cfg: dict, user_id: Optional[str] = None) -> bool:
    uid = _norm_gid(user_id if user_id is not None else getattr(plugin_event.data, 'user_id', ''))
    if not uid:
        return False
    return _is_dice_master(plugin_event, uid) or _is_config_master(cfg, uid)


def _can_manage(plugin_event, cfg: dict) -> bool:
    # 允许：群主、群管、骰主、配置master
    try:
        role = plugin_event.data.sender.get('role')
        if role in ['owner', 'admin', 'sub_admin']:
            return True
    except Exception:
        pass

    if _is_privileged_master(plugin_event, cfg):
        return True

    return False


def _group_member_list(plugin_event, group_id: str) -> Optional[list]:
    try:
        res = plugin_event.get_group_member_list(group_id)
        if res and isinstance(res, dict) and res.get('active') and isinstance(res.get('data'), list):
            return res['data']
    except Exception:
        pass
    return None


def _group_exists_for_bot(plugin_event, group_id: str) -> bool:
    # 通过拉取群成员列表来验证 bot 是否在群里
    return _group_member_list(plugin_event, group_id) is not None


def _user_in_group(plugin_event, group_id: str, user_id: str) -> bool:
    members = _group_member_list(plugin_event, group_id)
    if not members:
        return False
    uid = str(user_id)
    for m in members:
        if isinstance(m, dict) and str(m.get('id')) == uid:
            return True
    return False


def _get_user_role_in_group(plugin_event, group_id: str, user_id: str) -> Optional[str]:
    members = _group_member_list(plugin_event, group_id)
    if not members:
        return None
    uid = str(user_id)
    for m in members:
        if isinstance(m, dict) and str(m.get('id')) == uid:
            role = m.get('role')
            return str(role) if role is not None else None
    return None


def _get_group_name(plugin_event, group_id: str) -> str:
    # 尽力获取群名；获取不到就用群号
    gid = str(group_id)

    # 1) 优先尝试 group_info
    try:
        if hasattr(plugin_event, 'get_group_info'):
            res = plugin_event.get_group_info(gid)
            if res and isinstance(res, dict) and res.get('active') and isinstance(res.get('data'), dict):
                name = res['data'].get('name') or res['data'].get('group_name')
                if name:
                    return str(name)
    except Exception:
        pass

    # 2) 再尝试 group_list（带缓存）
    try:
        bot_hash = str(plugin_event.bot_info.hash)
    except Exception:
        bot_hash = 'default'

    now = time.time()
    cache_item = _GROUP_LIST_CACHE.get(bot_hash, (0, {}))
    ts = cache_item[0] if isinstance(cache_item, tuple) and len(cache_item) == 2 else 0
    mp = cache_item[1] if isinstance(cache_item, tuple) and len(cache_item) == 2 and isinstance(cache_item[1], dict) else {}

    if (now - float(ts)) > float(_GROUP_LIST_TTL_SEC) or not mp:
        mp2: Dict[str, str] = {}
        try:
            if hasattr(plugin_event, 'get_group_list'):
                res = plugin_event.get_group_list()
                if res and isinstance(res, dict) and res.get('active') and isinstance(res.get('data'), list):
                    for g in res['data']:
                        if not isinstance(g, dict):
                            continue
                        gid_this = str(g.get('id') or g.get('group_id') or '').strip()
                        name_this = g.get('name') or g.get('group_name')
                        if gid_this and name_this:
                            mp2[gid_this] = str(name_this)
        except Exception:
            mp2 = {}
        _GROUP_LIST_CACHE[bot_hash] = (now, mp2)
        mp = mp2

    if isinstance(mp, dict):
        name = mp.get(gid)
        if name:
            return str(name)

    return gid


def _get_hag_id(plugin_event) -> str:
    try:
        host_id = getattr(plugin_event.data, 'host_id', None)
    except Exception:
        host_id = None
    try:
        group_id = getattr(plugin_event.data, 'group_id', None)
    except Exception:
        group_id = None

    gid = _norm_gid(group_id)
    hid = _norm_gid(host_id) if host_id is not None else ''
    if hid:
        return f"{hid}|{gid}"
    return gid


def _get_pc_card_name(plugin_event) -> Optional[str]:
    if not oliva_dice_core_available:
        return None
    try:
        uid = _norm_gid(plugin_event.data.user_id)
        pc_hash = OlivaDiceCore.pcCard.getPcHash(uid, plugin_event.platform['platform'])
        hag_id = _get_hag_id(plugin_event)
        name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(pc_hash, hag_id)
        if name is None:
            return None
        name = str(name).strip()
        return name if name else None
    except Exception:
        return None


def _get_user_display_name(plugin_event) -> str:
    # 优先用事件里带的name；其次尝试拉群成员名片
    try:
        if plugin_event.data.sender and 'name' in plugin_event.data.sender and plugin_event.data.sender['name']:
            return str(plugin_event.data.sender['name'])
    except Exception:
        pass

    try:
        gid = _norm_gid(plugin_event.data.group_id)
        uid = _norm_gid(plugin_event.data.user_id)
        res = plugin_event.get_group_member_list(gid)
        if res and isinstance(res, dict) and res.get('active') and 'data' in res:
            for m in res['data']:
                if str(m.get('id')) == uid:
                    return str(m.get('card') or m.get('name') or uid)
    except Exception:
        pass

    return _norm_gid(getattr(plugin_event.data, 'user_id', ''))


def _format_forward_header(plugin_event, cfg: dict) -> str:
    src_gid = _norm_gid(plugin_event.data.group_id)
    src_name = _get_group_name(plugin_event, src_gid)

    uid = _norm_gid(plugin_event.data.user_id)
    uname = _get_user_display_name(plugin_event)

    # 人物卡显示（需要 OlivaDiceCore）
    pc_enabled = bool(cfg.get('pc_card_enabled', True)) and oliva_dice_core_available
    if pc_enabled:
        pc_name = _get_pc_card_name(plugin_event) or uname
        return f"[{src_name}({src_gid}) - {pc_name}[{uname}]({uid})]"

    # 默认：群信息 + 昵称
    return f"[{src_name}({src_gid}) - {uname}({uid})]"


def _parse_command(text: str) -> Optional[Tuple[str, List[str]]]:
    if not isinstance(text, str):
        return None
    s = text.strip()
    hit = None
    for p in COMMAND_PREFIXES:
        if s.startswith(p):
            hit = p
            break
    if not hit:
        return None
    rest = s[len(hit):].strip()
    if not rest:
        return ('help', [])
    parts = rest.split()
    return (parts[0], parts[1:])


class Event(object):
    _dedup_cache: Dict[str, float] = {}

    def init(plugin_event, Proc):
        _load_config()

    def group_message(plugin_event, Proc):
        if plugin_event.platform.get('platform') != 'qq':
            return

        cfg = _load_config()

        # 不转发bot自身消息
        try:
            self_id = str(plugin_event.base_info.get('self_id'))
        except Exception:
            self_id = None
        try:
            bot_id = str(plugin_event.bot_info.id)
        except Exception:
            bot_id = None
        uid = _norm_gid(getattr(plugin_event.data, 'user_id', ''))
        if uid and ((self_id and uid == self_id) or (bot_id and uid == bot_id)):
            return

        msg = getattr(plugin_event.data, 'message', None)
        if not isinstance(msg, str) or not msg.strip():
            return

        # 去重（可开关）：防止某些实现重复触发
        if cfg.get('dedup_enabled', True):
            try:
                mid = str(getattr(plugin_event.data, 'message_id', ''))
            except Exception:
                mid = ''
            ttl = int(cfg.get('dedup_ttl_sec', 10) or 10)
            if mid:
                now = time.time()
                # 清理
                for k in list(Event._dedup_cache.keys()):
                    if now - Event._dedup_cache[k] > ttl:
                        Event._dedup_cache.pop(k, None)
                if mid in Event._dedup_cache:
                    return
                Event._dedup_cache[mid] = now

        # 命令
        cmd = _parse_command(msg)
        if cmd is not None:
            action, args = cmd

            # 全局开关（仅骰主可用）
            if action in ['全局', 'global', '总开关', '开关']:
                if not _is_dice_master(plugin_event, _norm_gid(plugin_event.data.user_id)):
                    plugin_event.reply('权限不足：仅骰主可开关全局转发。')
                    return
                if not args:
                    plugin_event.reply('用法：.群链 全局 开  /  .群链 全局 关  /  .群链 全局 状态')
                    return
                sub = str(args[0]).strip()
                if sub in ['开', 'on', '开启']:
                    cfg['global_enabled'] = True
                    _save_config(cfg)
                    plugin_event.reply('全局转发已开启。')
                    return
                if sub in ['关', 'off', '关闭']:
                    cfg['global_enabled'] = False
                    _save_config(cfg)
                    plugin_event.reply('全局转发已关闭。')
                    return
                if sub in ['状态', 'status']:
                    plugin_event.reply(f"全局转发状态：{'开启' if cfg.get('global_enabled', True) else '关闭'}")
                    return
                plugin_event.reply('未知参数，用法：.群链 全局 开/关/状态')
                return

            # 人物卡显示开关（仅骰主可用；需要 OlivaDiceCore）
            if action in ['人物卡', '卡', 'pc', 'pccard']:
                if not _is_dice_master(plugin_event, _norm_gid(plugin_event.data.user_id)):
                    plugin_event.reply('权限不足：仅骰主可开关人物卡显示。')
                    return
                if not oliva_dice_core_available:
                    plugin_event.reply('无法使用：未检测到 OlivaDiceCore，人物卡显示不可用。')
                    return
                if not args:
                    plugin_event.reply('用法：.群链 人物卡 开  /  .群链 人物卡 关  /  .群链 人物卡 状态')
                    return
                sub = str(args[0]).strip()
                if sub in ['开', 'on', '开启']:
                    cfg['pc_card_enabled'] = True
                    _save_config(cfg)
                    plugin_event.reply('人物卡显示已开启（全局）。')
                    return
                if sub in ['关', 'off', '关闭']:
                    cfg['pc_card_enabled'] = False
                    _save_config(cfg)
                    plugin_event.reply('人物卡显示已关闭（全局）。')
                    return
                if sub in ['状态', 'status']:
                    plugin_event.reply(f"人物卡显示状态：{'开启' if (cfg.get('pc_card_enabled', True) and oliva_dice_core_available) else '关闭'}")
                    return
                plugin_event.reply('未知参数，用法：.群链 人物卡 开/关/状态')
                return

            # 防刷开关（仅骰主/配置master可用）
            if action in ['防刷', 'dedup', '去重']:
                if not _is_privileged_master(plugin_event, cfg):
                    plugin_event.reply('权限不足：仅骰主/配置master可开关防刷。')
                    return
                if not args:
                    plugin_event.reply('用法：.群链 防刷 开  /  .群链 防刷 关  /  .群链 防刷 状态')
                    return
                sub = str(args[0]).strip()
                if sub in ['开', 'on', '开启']:
                    cfg['dedup_enabled'] = True
                    _save_config(cfg)
                    plugin_event.reply('防刷已开启。')
                    return
                if sub in ['关', 'off', '关闭']:
                    cfg['dedup_enabled'] = False
                    _save_config(cfg)
                    plugin_event.reply('防刷已关闭。')
                    return
                if sub in ['状态', 'status']:
                    plugin_event.reply(f"防刷状态：{'开启' if cfg.get('dedup_enabled', True) else '关闭'}（TTL={int(cfg.get('dedup_ttl_sec', 10) or 10)}秒）")
                    return
                plugin_event.reply('未知参数，用法：.群链 防刷 开/关/状态')
                return

            if not _can_manage(plugin_event, cfg):
                plugin_event.reply('权限不足：仅群主/群管/骰主/配置master可管理群链。')
                return

            src_gid = _norm_gid(plugin_event.data.group_id)

            if action in ['help', '帮助']:
                plugin_event.reply(
                    '群链命令：\n'
                    '1) .群链 单向 [对面群号]  （对面 -> 本群）\n'
                    '2) .群链 双向 [对面群号]  （双向互转）\n'
                    '3) .群链 断开 单向 [对面群号]\n'
                    '4) .群链 断开 双向 [对面群号]\n'
                    '5) .群链 列表\n'
                    '6) .群链 防刷 开/关/状态（仅骰主/配置master）\n'
                    '7) .群链 全局 开/关/状态（仅骰主，全局转发开关）\n'
                    '8) .群链 人物卡 开/关/状态（仅骰主，默认开；需OlivaDiceCore）\n'
                    '说明：对面群必须在bot的群列表（bot已入群），且操作者本人也必须在对面群内。'
                )
                return

            if action in ['列表', 'list']:
                outgoing = _edge_list(cfg, src_gid)

                incoming_srcs: List[str] = []
                try:
                    edges = cfg.get('edges', {})
                    if isinstance(edges, dict):
                        for s in list(edges.keys()):
                            ss = _norm_gid(s)
                            if not ss or ss == src_gid:
                                continue
                            if src_gid in _edge_list(cfg, ss):
                                incoming_srcs.append(ss)
                except Exception:
                    incoming_srcs = []

                if not outgoing and not incoming_srcs:
                    plugin_event.reply('本群暂无已配置的转发连接。')
                    return

                lines: List[str] = []
                if incoming_srcs:
                    lines.append('【转发到本群（接收）】')
                    for s in incoming_srcs:
                        tag = '双向' if _is_bidirectional(cfg, src_gid, s) else '单向←'
                        name = _get_group_name(plugin_event, s)
                        lines.append(f"- {tag} {name}({s})")

                if outgoing:
                    if lines:
                        lines.append('')
                    lines.append('【从本群转发出去（发送）】')
                    for dst in outgoing:
                        tag = '双向' if _is_bidirectional(cfg, src_gid, dst) else '单向→'
                        dst_name = _get_group_name(plugin_event, dst)
                        lines.append(f"- {tag} {dst_name}({dst})")

                plugin_event.reply('本群转发连接：\n' + '\n'.join(lines))
                return

            if action in ['单向', 'oneway', 'one']:
                if not args:
                    plugin_event.reply('用法：.群链 单向 <对面群号>  （对面 -> 本群）')
                    return
                dst_gid = _norm_gid(args[0])
                if not dst_gid.isdecimal():
                    plugin_event.reply('对面群号格式不正确。')
                    return
                if not _group_exists_for_bot(plugin_event, dst_gid):
                    plugin_event.reply('连接失败：对面群不在bot的群列表（bot未入群或无法获取群成员）。')
                    return
                if not _user_in_group(plugin_event, dst_gid, _norm_gid(plugin_event.data.user_id)):
                    plugin_event.reply('连接失败：你本人不在对面群内（需要你也在对面群里）。')
                    return

                # 单向：对面 -> 本群
                ok, tip = _add_edge(cfg, dst_gid, src_gid)
                if ok:
                    _save_config(cfg)
                    plugin_event.reply(f"单向连接已配置：{dst_gid} -> {src_gid}")
                else:
                    plugin_event.reply(tip)
                return

            if action in ['双向', 'bidirectional', 'both', 'two']:
                if not args:
                    plugin_event.reply('用法：.群链 双向 <目标群号>')
                    return
                dst_gid = _norm_gid(args[0])
                if not dst_gid.isdecimal():
                    plugin_event.reply('目标群号格式不正确。')
                    return
                if not _group_exists_for_bot(plugin_event, dst_gid):
                    plugin_event.reply('连接失败：目标群不在bot的群列表（bot未入群或无法获取群成员）。')
                    return
                if not _user_in_group(plugin_event, dst_gid, _norm_gid(plugin_event.data.user_id)):
                    plugin_event.reply('连接失败：你本人不在目标群内（需要你也在对面群里）。')
                    return

                # 双向连接限制：非骰主/配置master必须在两边都是群主/管理员
                if not _is_privileged_master(plugin_event, cfg):
                    try:
                        role_here = plugin_event.data.sender.get('role')
                    except Exception:
                        role_here = None
                    if role_here not in ['owner', 'admin']:
                        plugin_event.reply('连接失败：双向链接要求你在本群是群主/管理员（骰主/配置master可无视）。')
                        return
                    role_there = _get_user_role_in_group(plugin_event, dst_gid, _norm_gid(plugin_event.data.user_id))
                    if role_there not in ['owner', 'admin']:
                        plugin_event.reply('连接失败：双向链接要求你在目标群也是群主/管理员（骰主/配置master可无视）。')
                        return

                changed = False
                ok1, tip1 = _add_edge(cfg, src_gid, dst_gid)
                if ok1:
                    changed = True
                ok2, _ = _add_edge(cfg, dst_gid, src_gid)
                if ok2:
                    changed = True

                if changed:
                    _save_config(cfg)
                    plugin_event.reply('双向连接已配置。')
                else:
                    # 可能已存在双向或部分已存在
                    if _is_bidirectional(cfg, src_gid, dst_gid):
                        plugin_event.reply('已存在双向连接（不能重复连接）。')
                    else:
                        plugin_event.reply('已存在单向连接，已补齐/或无需修改。')
                return

            if action in ['断开', '删除', 'remove', 'del']:
                # 默认按双向断开（兼容旧用法：.群链 断开 <群号>）
                mode = '双向'
                dst_gid = None

                if not args:
                    plugin_event.reply('用法：.群链 断开 单向 <目标群号>  或  .群链 断开 双向 <目标群号>')
                    return

                if len(args) == 1:
                    dst_gid = _norm_gid(args[0])
                else:
                    mode_arg = str(args[0]).strip()
                    if mode_arg in ['单向', 'oneway', 'one']:
                        mode = '单向'
                        dst_gid = _norm_gid(args[1])
                    elif mode_arg in ['双向', 'bidirectional', 'both', 'two']:
                        mode = '双向'
                        dst_gid = _norm_gid(args[1])
                    else:
                        # 兼容奇怪输入：把第一个当群号
                        dst_gid = _norm_gid(args[0])

                if not dst_gid or not dst_gid.isdecimal():
                    plugin_event.reply('目标群号格式不正确。')
                    return

                changed = False
                if mode == '单向':
                    # 单向定义为：对面 -> 本群
                    if _remove_edge(cfg, dst_gid, src_gid):
                        changed = True
                else:
                    if _remove_edge(cfg, src_gid, dst_gid):
                        changed = True
                    if _remove_edge(cfg, dst_gid, src_gid):
                        changed = True

                if changed:
                    _save_config(cfg)
                    plugin_event.reply('已断开连接。')
                else:
                    plugin_event.reply('未找到该连接。')
                return

            plugin_event.reply('未知子命令，发送“.群链”查看帮助。')
            return

        # 全局关闭时不进行转发（但仍允许使用命令开启）
        if not cfg.get('global_enabled', True):
            return

        # 转发
        src_gid = _norm_gid(plugin_event.data.group_id)
        targets = _edge_list(cfg, src_gid)
        if not targets:
            return

        header = _format_forward_header(plugin_event, cfg)
        forward_text = header + "\n" + msg

        for dst_gid in targets:
            # 发送到目标群
            try:
                plugin_event.send('group', dst_gid, forward_text)
            except Exception:
                continue

    def private_message(plugin_event, Proc):
        return
