# -*- encoding: utf-8 -*-

import OlivOS
import os
import json
import time
import re
from typing import Dict, List, Optional, Tuple

oliva_dice_core_available = False
try:
    import OlivaDiceCore
    oliva_dice_core_available = True
except Exception:
    oliva_dice_core_available = False

def replyMsg(plugin_event, message, at_user = False):
    if oliva_dice_core_available:
        host_id = None
        group_id = None
        user_id = None
        at_user_msg = ""
        try:
            tmp_name = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]['strBotName']
        except:
            tmp_name = "Bot"
        tmp_self_id = plugin_event.bot_info.id
        if 'host_id' in plugin_event.data.__dict__:
            host_id = plugin_event.data.host_id
        if 'group_id' in plugin_event.data.__dict__:
            group_id = plugin_event.data.group_id
        if 'user_id' in plugin_event.data.__dict__:
            user_id = plugin_event.data.user_id
        try:
            OlivaDiceCore.crossHook.dictHookFunc['msgHook'](
                plugin_event,
                'reply',
                {
                    'name': tmp_name,
                    'id': tmp_self_id
                },
                [host_id, group_id, user_id],
                str(message)
            )
        except:
            pass
        if at_user:
            at_para = OlivOS.messageAPI.PARA.at(str(user_id))
            at_user_msg = at_para.get_string_by_key('OP')
            return OlivaDiceCore.msgReply.pluginReply(plugin_event, f'{at_user_msg} ' + str(message))
        else:
            return OlivaDiceCore.msgReply.pluginReply(plugin_event, str(message))
    else:
        if at_user:
            uid = getattr(plugin_event.data, 'user_id', None)
            if uid:
                at_para = OlivOS.messageAPI.PARA.at(str(uid))
                return plugin_event.reply(at_para.get_string_by_key('OP') + " " + str(message))
        return plugin_event.reply(str(message))

DATA_PATH = os.path.join('plugin', 'data', 'QQGroupForward')

def get_redirected_bot_hash(bot_hash: str) -> str:
    """遵循 OlivaDiceCore 主从账号链接：从账号读写主账号目录。"""
    if oliva_dice_core_available:
        try:
            master = OlivaDiceCore.console.getMasterBotHash(bot_hash)
            if master:
                return str(master)
        except Exception:
            pass
    return bot_hash

def get_bot_conf_hash(bot_hash):
    # 首先处理主从账号重定向
    bot_hash = get_redirected_bot_hash(bot_hash)
    if oliva_dice_core_available:
        try:
            return OlivaDiceCore.userConfig.getConfHash(bot_hash)
        except:
            pass
    return bot_hash

def get_conf_dir(bot_hash):
    conf_hash = get_bot_conf_hash(bot_hash)
    path = os.path.join(DATA_PATH, conf_hash)
    os.makedirs(path, exist_ok=True)
    return path

def get_config_file(bot_hash):
    return os.path.join(get_conf_dir(bot_hash), 'config.json')

def get_edges_file(bot_hash):
    return os.path.join(get_conf_dir(bot_hash), 'edges.json')

COMMAND_PREFIXES = ('.群链', '。群链', '/群链')

# 全局命令别名定义，避免重复
COMMAND_ALIASES = {
    'global': ['全局', 'global', '总开关', '开关'],
    'pc_card': ['人物卡', '卡', 'pc', 'pccard'],
    'dedup': ['防刷', 'dedup', '去重'],
    'filter_bracket': ['括号过滤', '括号', '左括号过滤', '左括号', 'bracket', 'paren', 'parenthesis'],
    'filter_dot': ['句号过滤', '句号', '点过滤', '点', 'dot', 'prefix'],
    'help': ['帮助', 'help'],
    'list': ['列表', 'list'],
    'oneway': ['单向', 'oneway', 'one'],
    'bidirectional': ['双向', 'bidirectional', 'both', 'two'],
    'disconnect': ['断开', '删除', 'remove', 'del']
}

# 反向映射：别名 -> 标准命令名
_ALIAS_TO_CMD = {}
for cmd_name, aliases in COMMAND_ALIASES.items():
    for alias in aliases:
        _ALIAS_TO_CMD[alias] = cmd_name

# bot_hash -> (timestamp, {group_id: group_name})
_GROUP_LIST_CACHE: Dict[str, Tuple[float, Dict[str, str]]] = {}
_GROUP_LIST_TTL_SEC = 60


def _default_config() -> dict:
    return {
        # 全局开关（仅骰主可改）：关闭后不进行任何消息转发
        'global_enabled': True,
        # 是否使用人物卡显示（仅骰主可改）。需要 OlivaDiceCore。
        # 若未检测到 OlivaDiceCore，则即便为 True 也视为关闭。
        'pc_card_enabled': True,
        # 配置master：权限等同骰主（可管理群链、开关防刷等）
        'masters': [],
        # 防刷：同一条消息ID在短时间内只处理一次
        'dedup_enabled': True,
        'dedup_ttl_sec': 10,
        # 转发过滤：去除开头的 at 之后，以左括号开头的不转发（默认关闭；识别半角/全角）
        'filter_skip_leading_bracket_after_at': False,
        # 转发过滤：去除开头的 at 之后，以 . / 。 开头的不转发（默认关闭；识别半角/全角句号）
        'filter_skip_leading_dot_after_at': False,
    }


_LEADING_AT_CODE_RE = re.compile(r'^(?:\s*\[(?:OP|CQ):at,[^\]]+\]\s*)+', re.IGNORECASE)
_LEADING_AT_TEXT_RE = re.compile(r'^(?:\s*@[^\s\r\n]+\s*)+', re.IGNORECASE)


def _strip_leading_at(text: str) -> str:
    """去掉消息开头连续出现的 at（OP/CQ at 码或 @昵称 文本），用于做前缀过滤判断。"""
    if not isinstance(text, str):
        return ''
    s = text.lstrip()
    # 先去掉 [OP:at,...]/[CQ:at,...]
    s2 = _LEADING_AT_CODE_RE.sub('', s).lstrip()
    # 再去掉替换成文本后的 @xxx（有些平台会直接给明文 @）
    s3 = _LEADING_AT_TEXT_RE.sub('', s2).lstrip()
    return s3


def _should_skip_forward_by_prefix(cfg: dict, msg_text: str) -> bool:
    """根据配置判断是否因前缀规则而跳过转发。"""
    s = _strip_leading_at(msg_text)
    if not s:
        return False

    if bool(cfg.get('filter_skip_leading_bracket_after_at', False)):
        if s.startswith('(') or s.startswith('（'):
            return True

    if bool(cfg.get('filter_skip_leading_dot_after_at', False)):
        # 兼容半角句号 '.'、中文句号 '。'，顺手兼容全角点 '．'
        if s.startswith('.') or s.startswith('。') or s.startswith('．'):
            return True

    return False


def _load_config(bot_hash: str) -> dict:
    conf_file = get_config_file(bot_hash)

    # 兜底：若当前 bot_hash 为从账号，且主账号目录里不存在配置，则尝试读取旧的从账号目录
    redirected_hash = get_redirected_bot_hash(bot_hash)
    if redirected_hash != bot_hash and not os.path.exists(conf_file):
        legacy_conf = os.path.join(DATA_PATH, bot_hash, 'config.json')
        if os.path.exists(legacy_conf):
            conf_file = legacy_conf

    if not os.path.exists(conf_file):
        cfg = _default_config()
        _save_config(bot_hash, cfg)
        return cfg
    try:
        with open(conf_file, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError('config not dict')
    except Exception:
        cfg = _default_config()
        _save_config(bot_hash, cfg)
        return cfg

    # 补默认字段
    base = _default_config()
    changed = False
    for k, v in base.items():
        if k not in cfg:
            cfg[k] = v
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
    for legacy_key in ['version', 'enabled', 'edges']:
        if legacy_key in cfg:
            cfg.pop(legacy_key, None)
            changed = True

    if changed:
        _save_config(bot_hash, cfg)
    return cfg


def _save_config(bot_hash: str, cfg: dict) -> None:
    conf_file = get_config_file(bot_hash)
    with open(conf_file, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _load_edges(bot_hash: str) -> dict:
    edges_file = get_edges_file(bot_hash)

    # 兜底：若当前 bot_hash 为从账号，且主账号目录里不存在 edges，则尝试读取旧的从账号目录
    redirected_hash = get_redirected_bot_hash(bot_hash)
    if redirected_hash != bot_hash and not os.path.exists(edges_file):
        legacy_edges = os.path.join(DATA_PATH, bot_hash, 'edges.json')
        if os.path.exists(legacy_edges):
            edges_file = legacy_edges

    if not os.path.exists(edges_file):
        return {}
    try:
        with open(edges_file, 'r', encoding='utf-8') as f:
            edges = json.load(f)
        if not isinstance(edges, dict):
            return {}
        return edges
    except Exception:
        return {}


def _save_edges(bot_hash: str, edges: dict) -> None:
    edges_file = get_edges_file(bot_hash)
    with open(edges_file, 'w', encoding='utf-8') as f:
        json.dump(edges, f, ensure_ascii=False, indent=2)


def _norm_gid(gid) -> str:
    return str(gid).strip()


def _edge_list(edges: dict, src_gid: str) -> List[str]:
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


def _add_edge(edges: dict, src_gid: str, dst_gid: str) -> Tuple[bool, str]:
    if src_gid == dst_gid:
        return False, '不能连接同一个群。'
    out = _edge_list(edges, src_gid)
    if dst_gid in out:
        return False, '已存在该连接（不能重复连接）。'
    out.append(dst_gid)
    edges[src_gid] = out
    return True, '连接已添加。'


def _remove_edge(edges: dict, src_gid: str, dst_gid: str) -> bool:
    out = _edge_list(edges, src_gid)
    if dst_gid in out:
        out.remove(dst_gid)
        edges[src_gid] = out
        return True
    return False


def _is_bidirectional(edges: dict, a: str, b: str) -> bool:
    return b in _edge_list(edges, a) and a in _edge_list(edges, b)


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


def _get_member_name(plugin_event, group_id: str, user_id: str) -> str:
    """获取指定群成员的显示名称（名片或昵称）。"""
    try:
        gid = _norm_gid(group_id)
        uid = _norm_gid(user_id)
        res = plugin_event.get_group_member_list(gid)
        if res and isinstance(res, dict) and res.get('active') and 'data' in res:
            for m in res['data']:
                if str(m.get('id')) == uid:
                    return str(m.get('card') or m.get('name') or uid)
    except Exception:
        pass
    return str(user_id)

def _replace_at_with_text(plugin_event, group_id: str, text: str) -> str:
    """将文本中的 [OP:at,...] 或 [CQ:at,...] 替换为 @群名片。"""
    if not isinstance(text, str):
        return text
    
    # 支持 [OP:at,...] 和 [CQ:at,...] 两种格式
    pattern = r'\[(?:OP|CQ):at,([^\]]+)\]'
    
    member_map = None

    def do_replace(match):
        nonlocal member_map
        params_str = match.group(1)
        params = {}
        for pair in params_str.split(','):
            if '=' in pair:
                kv = pair.split('=', 1)
                if len(kv) == 2:
                    params[kv[0].strip()] = kv[1].strip()
        
        if 'name' in params and params['name']:
            return f"@{params['name']}"
        
        uid = params.get('id') or params.get('qq')
        if not uid:
            return "" # 无法识别的AT直接抹掉
        
        if member_map is None:
            member_map = {}
            try:
                res = plugin_event.get_group_member_list(_norm_gid(group_id))
                if res and isinstance(res, dict) and res.get('active') and 'data' in res:
                    for m in res['data']:
                        member_map[str(m.get('id'))] = str(m.get('card') or m.get('name'))
            except:
                pass
        
        name = member_map.get(str(uid), str(uid))
        return f"@{name}"

    return re.sub(pattern, do_replace, text)

def _get_user_display_name(plugin_event) -> str:
    # 优先用事件里带的name；其次尝试拉群成员名片
    try:
        if plugin_event.data.sender and 'name' in plugin_event.data.sender and plugin_event.data.sender['name']:
            return str(plugin_event.data.sender['name'])
    except Exception:
        pass

    return _get_member_name(plugin_event, plugin_event.data.group_id, plugin_event.data.user_id)


def _get_reply_context(plugin_event, msg: str) -> Tuple[str, str]:
    """
    解析消息中的回复 OP 码 [OP:reply,id=...]，并获取被回复的消息内容。
    返回 (处理后的消息, 上下文文本)。
    """
    if not isinstance(msg, str):
        return msg, ""
    
    src_gid = _norm_gid(plugin_event.data.group_id)
    
    # 匹配回复代码（支持 [OP:reply,...] 和 [CQ:reply,...] 两种格式）
    reply_pattern = r'\[(?:OP|CQ):reply,([^\]]+)\]'
    match = re.search(reply_pattern, msg)
    if not match:
        return msg, ""
    
    # 解析 reply_id
    params_str = match.group(1)
    reply_id = None
    for pair in params_str.split(','):
        if '=' in pair:
            kv = pair.split('=', 1)
            if kv[0].strip() == 'id':
                reply_id = kv[1].strip()
                break
    
    # 移除当前消息中的回复头
    msg_without_reply = re.sub(reply_pattern, '', msg).strip()
    
    if not reply_id:
        return msg_without_reply, ""

    context_text = ""
    try:
        res = plugin_event.get_msg(reply_id)
        if res and isinstance(res, dict) and res.get('active'):
            data = res.get('data', {})
            orig_raw = str(data.get('raw_message', ''))
            orig_sender = data.get('sender', {})
            orig_name = orig_sender.get('name') or orig_sender.get('id') or "未知"
            
            # 1. 彻底去掉原消息中的嵌套回复（回复中的回复）
            orig_raw_clean = re.sub(reply_pattern, '', orig_raw).strip()
            # 2. 将原消息中的 AT 替换为文本
            orig_raw_clean = _replace_at_with_text(plugin_event, src_gid, orig_raw_clean)
            
            if len(orig_raw_clean) > 100:
                orig_raw_clean = orig_raw_clean[:100] + "..."
            
            context_text = f"\n↳ 回复 {orig_name}: {orig_raw_clean}\n--------------------"
    except Exception:
        pass
        
    return msg_without_reply, context_text

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


def isMatchWordStart(data, key, ignoreCase=True, fullMatch=False, isCommand=False):
    tmp_output = False
    flag_skip = False
    tmp_data = data.strip()
    tmp_keys = [key] if isinstance(key, str) else key
    if isCommand and oliva_dice_core_available:
        if 'replyContextFliter' in OlivaDiceCore.crossHook.dictHookList:
            for k in tmp_keys:
                if k in OlivaDiceCore.crossHook.dictHookList['replyContextFliter']:
                    tmp_output = False
                    flag_skip = True
                    break
    if not flag_skip:
        if ignoreCase:
            tmp_data = tmp_data.lower()
            tmp_keys = [k.lower() for k in tmp_keys]
        # 按长度从长到短排序
        tmp_keys_sorted = sorted(tmp_keys, key=lambda x: len(x), reverse=True)
        for tmp_key in tmp_keys_sorted:
            if not fullMatch and len(tmp_data) >= len(tmp_key):
                if tmp_data[:len(tmp_key)] == tmp_key:
                    tmp_output = True
                    break
            elif fullMatch and tmp_data == tmp_key:
                tmp_output = True
                break
    return tmp_output

def getMatchWordStartRight(data, key, ignoreCase=True):
    tmp_output_str = ''
    tmp_data = data.strip()
    tmp_keys = [key] if isinstance(key, str) else key
    if ignoreCase:
        tmp_data = tmp_data.lower()
        tmp_keys = [k.lower() for k in tmp_keys]
    # 按长度从长到短排序
    tmp_keys_sorted = sorted(tmp_keys, key=lambda x: len(x), reverse=True)
    for tmp_key in tmp_keys_sorted:
        if len(tmp_data) >= len(tmp_key):
            if tmp_data[:len(tmp_key)] == tmp_key:
                tmp_output_str = data.strip()[len(tmp_key):]
                break
    return tmp_output_str

def _parse_command(text: str) -> Optional[Tuple[str, List[str]]]:
    if not isinstance(text, str):
        return None
    
    if not isMatchWordStart(text, COMMAND_PREFIXES, isCommand=True):
        return None
    
    rest = getMatchWordStartRight(text, COMMAND_PREFIXES).strip()
    if not rest:
        return ('help', [])
    
    # 从 COMMAND_ALIASES 中提取所有别名，按长度倒序排列（优先匹配长词）
    all_aliases = []
    for cmd_name, aliases in COMMAND_ALIASES.items():
        for alias in aliases:
            all_aliases.append(alias)
    
    matched_action = None
    # 找出匹配到的关键词（按长度倒序，以优先匹配如 "人物卡" 而非 "卡"）
    for a in sorted(all_aliases, key=len, reverse=True):
        if isMatchWordStart(rest, a):
            matched_action = a
            break
            
    if matched_action:
        # 获取二级动作之后的内容作为参数
        args_str = getMatchWordStartRight(rest, [matched_action]).strip()
        args = args_str.split() if args_str else []
        return (matched_action, args)
    
    # 如果没匹配到已知动作，回退到原有的空格分割逻辑
    parts = rest.split()
    if not parts:
        return ('help', [])
    return (parts[0], parts[1:])


class Event(object):
    _dedup_cache: Dict[str, float] = {}

    def init(plugin_event, Proc):
        pass

    def group_message(plugin_event, Proc):
        if plugin_event.platform.get('platform') != 'qq':
            return

        bot_hash = str(plugin_event.bot_info.hash)
        cfg = _load_config(bot_hash)
        edges = _load_edges(bot_hash)

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
            
            # 获取规范的命令名（通过反向映射）
            cmd_name = _ALIAS_TO_CMD.get(action, action)

            # 全局开关（仅骰主可用）
            if cmd_name == 'global':
                if not _is_dice_master(plugin_event, _norm_gid(plugin_event.data.user_id)):
                    replyMsg(plugin_event, '权限不足：仅骰主可开关全局转发。')
                    return
                if not args:
                    replyMsg(plugin_event, '用法：.群链 全局 开  /  .群链 全局 关  /  .群链 全局 状态')
                    return
                sub = str(args[0]).strip()
                if sub in ['开', 'on', '开启']:
                    cfg['global_enabled'] = True
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '全局转发已开启。')
                    return
                if sub in ['关', 'off', '关闭']:
                    cfg['global_enabled'] = False
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '全局转发已关闭。')
                    return
                if sub in ['状态', 'status']:
                    replyMsg(plugin_event, f"全局转发状态：{'开启' if cfg.get('global_enabled', True) else '关闭'}")
                    return
                replyMsg(plugin_event, '未知参数，用法：.群链 全局 开/关/状态')
                return

            # 人物卡显示开关（仅骰主可用；需要 OlivaDiceCore）
            if cmd_name == 'pc_card':
                if not _is_dice_master(plugin_event, _norm_gid(plugin_event.data.user_id)):
                    replyMsg(plugin_event, '权限不足：仅骰主可开关人物卡显示。')
                    return
                if not oliva_dice_core_available:
                    replyMsg(plugin_event, '无法使用：未检测到 OlivaDiceCore，人物卡显示不可用。')
                    return
                if not args:
                    replyMsg(plugin_event, '用法：.群链 人物卡 开  /  .群链 人物卡 关  /  .群链 人物卡 状态')
                    return
                sub = str(args[0]).strip()
                if sub in ['开', 'on', '开启']:
                    cfg['pc_card_enabled'] = True
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '人物卡显示已开启（全局）。')
                    return
                if sub in ['关', 'off', '关闭']:
                    cfg['pc_card_enabled'] = False
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '人物卡显示已关闭（全局）。')
                    return
                if sub in ['状态', 'status']:
                    replyMsg(plugin_event, f"人物卡显示状态：{'开启' if (cfg.get('pc_card_enabled', True) and oliva_dice_core_available) else '关闭'}")
                    return
                replyMsg(plugin_event, '未知参数，用法：.群链 人物卡 开/关/状态')
                return

            # 防刷开关（仅骰主/配置master可用）
            if cmd_name == 'dedup':
                if not _is_privileged_master(plugin_event, cfg):
                    replyMsg(plugin_event, '权限不足：仅骰主/配置master可开关防刷。')
                    return
                if not args:
                    replyMsg(plugin_event, '用法：.群链 防刷 开  /  .群链 防刷 关  /  .群链 防刷 状态')
                    return
                sub = str(args[0]).strip()
                if sub in ['开', 'on', '开启']:
                    cfg['dedup_enabled'] = True
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '防刷已开启。')
                    return
                if sub in ['关', 'off', '关闭']:
                    cfg['dedup_enabled'] = False
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '防刷已关闭。')
                    return
                if sub in ['状态', 'status']:
                    replyMsg(plugin_event, f"防刷状态：{'开启' if cfg.get('dedup_enabled', True) else '关闭'}（TTL={int(cfg.get('dedup_ttl_sec', 10) or 10)}秒）")
                    return
                replyMsg(plugin_event, '未知参数，用法：.群链 防刷 开/关/状态')
                return

            # 转发过滤：左括号前缀过滤（仅骰主/配置master可用）
            if cmd_name == 'filter_bracket':
                if not _is_privileged_master(plugin_event, cfg):
                    replyMsg(plugin_event, '权限不足：仅骰主/配置master可开关括号过滤。')
                    return
                if not args:
                    replyMsg(plugin_event, '用法：.群链 括号过滤 开  /  .群链 括号过滤 关  /  .群链 括号过滤 状态')
                    return
                sub = str(args[0]).strip()
                if sub in ['开', 'on', '开启']:
                    cfg['filter_skip_leading_bracket_after_at'] = True
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '括号过滤已开启：去除开头AT后，以（或(开头的消息不转发。')
                    return
                if sub in ['关', 'off', '关闭']:
                    cfg['filter_skip_leading_bracket_after_at'] = False
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '括号过滤已关闭。')
                    return
                if sub in ['状态', 'status']:
                    replyMsg(plugin_event, f"括号过滤状态：{'开启' if cfg.get('filter_skip_leading_bracket_after_at', False) else '关闭'}")
                    return
                replyMsg(plugin_event, '未知参数，用法：.群链 括号过滤 开/关/状态')
                return

            # 转发过滤：句号前缀过滤（仅骰主/配置master可用）
            if cmd_name == 'filter_dot':
                if not _is_privileged_master(plugin_event, cfg):
                    replyMsg(plugin_event, '权限不足：仅骰主/配置master可开关句号过滤。')
                    return
                if not args:
                    replyMsg(plugin_event, '用法：.群链 句号过滤 开  /  .群链 句号过滤 关  /  .群链 句号过滤 状态')
                    return
                sub = str(args[0]).strip()
                if sub in ['开', 'on', '开启']:
                    cfg['filter_skip_leading_dot_after_at'] = True
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '句号过滤已开启：去除开头AT后，以 . 或 。 开头的消息不转发。')
                    return
                if sub in ['关', 'off', '关闭']:
                    cfg['filter_skip_leading_dot_after_at'] = False
                    _save_config(bot_hash, cfg)
                    replyMsg(plugin_event, '句号过滤已关闭。')
                    return
                if sub in ['状态', 'status']:
                    replyMsg(plugin_event, f"句号过滤状态：{'开启' if cfg.get('filter_skip_leading_dot_after_at', False) else '关闭'}")
                    return
                replyMsg(plugin_event, '未知参数，用法：.群链 句号过滤 开/关/状态')
                return

            if not _can_manage(plugin_event, cfg):
                replyMsg(plugin_event, '权限不足：仅群主/群管/骰主/配置master可管理群链。')
                return

            src_gid = _norm_gid(plugin_event.data.group_id)

            if cmd_name == 'help':
                replyMsg(plugin_event, 
                    '群链命令：\n'
                    '1) .群链 单向 [对面群号]  （对面 -> 本群）\n'
                    '2) .群链 双向 [对面群号]  （双向互转）\n'
                    '3) .群链 断开 单向 [对面群号]\n'
                    '4) .群链 断开 双向 [对面群号]\n'
                    '5) .群链 列表\n'
                    '6) .群链 防刷 开/关/状态（仅骰主/配置master）\n'
                    '7) .群链 全局 开/关/状态（仅骰主，全局转发开关）\n'
                    '8) .群链 人物卡 开/关/状态（仅骰主，默认开；需OlivaDiceCore）\n'
                    '9) .群链 括号过滤 开/关/状态（仅骰主/配置master，默认关：去除开头AT后以（/(开头的不转发）\n'
                    '10) .群链 句号过滤 开/关/状态（仅骰主/配置master，默认关：去除开头AT后以./。开头的不转发）\n'
                    '说明：对面群必须在bot的群列表（bot已入群），且操作者本人也必须在对面群内。'
                )
                return

            if cmd_name == 'list':
                outgoing = _edge_list(edges, src_gid)

                incoming_srcs: List[str] = []
                try:
                    for s in list(edges.keys()):
                        ss = _norm_gid(s)
                        if not ss or ss == src_gid:
                            continue
                        if src_gid in _edge_list(edges, ss):
                            incoming_srcs.append(ss)
                except Exception:
                    incoming_srcs = []

                if not outgoing and not incoming_srcs:
                    replyMsg(plugin_event, '本群暂无已配置的转发连接。')
                    return

                lines: List[str] = []
                if incoming_srcs:
                    lines.append('【转发到本群（接收）】')
                    for s in incoming_srcs:
                        tag = '双向' if _is_bidirectional(edges, src_gid, s) else '单向←'
                        name = _get_group_name(plugin_event, s)
                        lines.append(f"- {tag} {name}({s})")

                if outgoing:
                    if lines:
                        lines.append('')
                    lines.append('【从本群转发出去（发送）】')
                    for dst in outgoing:
                        tag = '双向' if _is_bidirectional(edges, src_gid, dst) else '单向→'
                        dst_name = _get_group_name(plugin_event, dst)
                        lines.append(f"- {tag} {dst_name}({dst})")

                replyMsg(plugin_event, '本群转发连接：\n' + '\n'.join(lines))
                return

            if cmd_name == 'oneway':
                if not args:
                    replyMsg(plugin_event, '用法：.群链 单向 [对面群号]  （对面 -> 本群）')
                    return
                dst_gid = _norm_gid(args[0])
                if not dst_gid.isdecimal():
                    replyMsg(plugin_event, '对面群号格式不正确。')
                    return
                if not _group_exists_for_bot(plugin_event, dst_gid):
                    replyMsg(plugin_event, '连接失败：对面群不在bot的群列表（bot未入群或无法获取群成员）。')
                    return
                if not _user_in_group(plugin_event, dst_gid, _norm_gid(plugin_event.data.user_id)):
                    replyMsg(plugin_event, '连接失败：你本人不在对面群内（需要你也在对面群里）。')
                    return

                # 单向：对面 -> 本群
                ok, tip = _add_edge(edges, dst_gid, src_gid)
                if ok:
                    _save_edges(bot_hash, edges)
                    replyMsg(plugin_event, f"单向连接已配置：{dst_gid} -> {src_gid}")
                else:
                    replyMsg(plugin_event, tip)
                return

            if cmd_name == 'bidirectional':
                if not args:
                    replyMsg(plugin_event, '用法：.群链 双向 [目标群号]')
                    return
                dst_gid = _norm_gid(args[0])
                if not dst_gid.isdecimal():
                    replyMsg(plugin_event, '目标群号格式不正确。')
                    return
                if not _group_exists_for_bot(plugin_event, dst_gid):
                    replyMsg(plugin_event, '连接失败：目标群不在bot的群列表（bot未入群或无法获取群成员）。')
                    return
                if not _user_in_group(plugin_event, dst_gid, _norm_gid(plugin_event.data.user_id)):
                    replyMsg(plugin_event, '连接失败：你本人不在目标群内（需要你也在对面群里）。')
                    return

                # 双向连接限制：非骰主/配置master必须在两边都是群主/管理员
                if not _is_privileged_master(plugin_event, cfg):
                    try:
                        role_here = plugin_event.data.sender.get('role')
                    except Exception:
                        role_here = None
                    if role_here not in ['owner', 'admin']:
                        replyMsg(plugin_event, '连接失败：双向链接要求你在本群是群主/管理员（骰主/配置master可无视）。')
                        return
                    role_there = _get_user_role_in_group(plugin_event, dst_gid, _norm_gid(plugin_event.data.user_id))
                    if role_there not in ['owner', 'admin']:
                        replyMsg(plugin_event, '连接失败：双向链接要求你在目标群也是群主/管理员（骰主/配置master可无视）。')
                        return

                changed = False
                ok1, tip1 = _add_edge(edges, src_gid, dst_gid)
                if ok1:
                    changed = True
                ok2, _ = _add_edge(edges, dst_gid, src_gid)
                if ok2:
                    changed = True

                if changed:
                    _save_edges(bot_hash, edges)
                    replyMsg(plugin_event, '双向连接已配置。')
                else:
                    # 可能已存在双向或部分已存在
                    if _is_bidirectional(edges, src_gid, dst_gid):
                        replyMsg(plugin_event, '已存在双向连接（不能重复连接）。')
                    else:
                        replyMsg(plugin_event, '已存在单向连接，已补齐/或无需修改。')
                return

            if cmd_name == 'disconnect':
                # 默认按双向断开（兼容旧用法：.群链 断开 [群号]）
                mode = '双向'
                dst_gid = None

                if not args:
                    replyMsg(plugin_event, '用法：.群链 断开 单向 [目标群号]  或  .群链 断开 双向 [目标群号]')
                    return

                if len(args) == 1:
                    dst_gid = _norm_gid(args[0])
                else:
                    mode_arg = str(args[0]).strip()
                    # 使用反向映射检查二级命令
                    mode_cmd = _ALIAS_TO_CMD.get(mode_arg, mode_arg)
                    if mode_cmd == 'oneway':
                        mode = '单向'
                        dst_gid = _norm_gid(args[1])
                    elif mode_cmd == 'bidirectional':
                        mode = '双向'
                        dst_gid = _norm_gid(args[1])
                    else:
                        # 兼容奇怪输入：把第一个当群号
                        dst_gid = _norm_gid(args[0])

                if not dst_gid or not dst_gid.isdecimal():
                    replyMsg(plugin_event, '目标群号格式不正确。')
                    return

                changed = False
                if mode == '单向':
                    # 单向定义为：对面 -> 本群
                    if _remove_edge(edges, dst_gid, src_gid):
                        changed = True
                else:
                    if _remove_edge(edges, src_gid, dst_gid):
                        changed = True
                    if _remove_edge(edges, dst_gid, src_gid):
                        changed = True

                if changed:
                    _save_edges(bot_hash, edges)
                    replyMsg(plugin_event, '已断开连接。')
                else:
                    replyMsg(plugin_event, '未找到该连接。')
                return

            replyMsg(plugin_event, '未知子命令，发送“.群链”查看帮助。')
            return

        # 全局关闭时不进行转发（但仍允许使用命令开启）
        if not cfg.get('global_enabled', True):
            return

        # 转发
        src_gid = _norm_gid(plugin_event.data.group_id)
        targets = _edge_list(edges, src_gid)
        if not targets:
            return

        header = _format_forward_header(plugin_event, cfg)
        # 处理回复上下文
        msg_to_forward, reply_context = _get_reply_context(plugin_event, msg)

        # 前缀过滤：按配置跳过某些“命令/括号动作”类消息
        if _should_skip_forward_by_prefix(cfg, msg_to_forward):
            return

        # 将当前消息中的 AT 替换为文本
        msg_to_forward = _replace_at_with_text(plugin_event, src_gid, msg_to_forward)
        
        forward_text = header + reply_context + "\n" + msg_to_forward

        for dst_gid in targets:
            # 发送到目标群
            try:
                plugin_event.send('group', dst_gid, forward_text)
            except Exception:
                continue

    def private_message(plugin_event, Proc):
        return
