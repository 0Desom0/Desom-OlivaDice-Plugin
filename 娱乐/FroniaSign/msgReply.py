# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore，写命令请跳转到第183行。
'''

import OlivOS
import FroniaSign
import OlivaDiceCore

import copy
import os
import json
import time
import random
import hashlib
import re
from datetime import datetime


has_OlivaAIAgent = False
try:
    import OlivaAIAgent
    has_OlivaAIAgent = True
except Exception:
    has_OlivaAIAgent = False

base_data_path = os.path.join('plugin', 'data', 'FroniaSign')

MASTER_UIDS = ['121096913', '2946244126']
MAX_BIND_DEPTH = 8
# 绑定目标一律按 OneBot 平台名计算 user_hash。
# 依据：OlivOS 各 OneBot 系适配器（onebotV11/OPQBot/milky/red）统一为 {'sdk': 'onebot', 'platform': 'qq'}；
# 而 qqGuildv2 的用户标识是 openid / member_openid（见 OlivOS adapter/qqGuild/qqGuildv2SDKGroup.py），
# 纯数字 QQ 号不可能来自 qqGuild。若不固定平台，在官方机器人会话里执行 .qdbind 会算出 qqGuild 前缀的 hash，
# 与目标 QQ 平时在 OneBot 群里的 hash 对不上，绑定会静默失效。
QQ_ONEBOT_PLATFORM = 'qq'
SPECIAL_UIDS = {
    '3948837959': 'Fhloy',
    '3928744142': 'Foxeline'
}


def _safe_str(x):
    try:
        return str(x)
    except Exception:
        return ''


def _get_bot_hash(plugin_event):
    bot_hash = _safe_str(plugin_event.bot_info.hash)
    return _get_redirected_bot_hash(bot_hash)


def _get_redirected_bot_hash(bot_hash):
    """遵循 OlivaDiceCore 主从账号链接：从账号读写主账号目录。"""
    try:
        master = OlivaDiceCore.console.getMasterBotHash(bot_hash)
        if master:
            return _safe_str(master)
    except Exception:
        pass
    return _safe_str(bot_hash)


def _get_user_hash(plugin_event):
    try:
        return _safe_str(
            OlivaDiceCore.userConfig.getUserHash(
                userId=plugin_event.data.user_id,
                userType='user',
                platform=plugin_event.platform['platform']
            )
        )
    except Exception:
        return _safe_str(plugin_event.data.user_id)


def _calc_user_hash_by_user_id(user_id, platform):
    try:
        return _safe_str(
            OlivaDiceCore.userConfig.getUserHash(
                userId=user_id,
                userType='user',
                platform=platform
            )
        )
    except Exception:
        return _safe_str(user_id)


def _get_group_member_user_hash_set(plugin_event, group_id):
    """返回当前群成员的 user_hash 集合；失败返回 None。"""
    try:
        group_member_list = plugin_event.get_group_member_list(group_id)
        if not group_member_list or group_member_list.get('active') is False:
            return None
        members = group_member_list.get('data', [])
        if not isinstance(members, list):
            return None
        platform = plugin_event.platform.get('platform', None)
        if not platform:
            return None
        out = set()
        for m in members:
            if not isinstance(m, dict):
                continue
            uid = m.get('user_id')
            if uid is None:
                uid = m.get('id')
            if uid is None:
                uid = m.get('qq')
            if uid is None:
                continue
            out.add(_calc_user_hash_by_user_id(uid, platform))
        return out
    except Exception:
        return None


def _ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def _get_bot_dir(bot_hash):
    path = os.path.join(base_data_path, bot_hash)
    _ensure_dir(path)
    return path


def _get_user_dir(bot_hash, user_hash):
    path = os.path.join(_get_bot_dir(bot_hash), user_hash)
    _ensure_dir(path)
    return path


def _load_json(path, default=None):
    if default is None:
        default = {}
    try:
        if not os.path.exists(path):
            return copy.deepcopy(default)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return copy.deepcopy(default)
    except Exception:
        return copy.deepcopy(default)


def _save_json(path, data):
    try:
        _ensure_dir(os.path.dirname(path))
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _load_user_data(bot_hash, user_hash, user_id):
    user_dir = _get_user_dir(bot_hash, user_hash)
    user_file = os.path.join(user_dir, 'user.json')
    data = _load_json(user_file, default={})
    if 'anima_coin' not in data:
        data['anima_coin'] = 0
    if 'groups' not in data or not isinstance(data.get('groups'), list):
        data['groups'] = []
    if 'user_ids' not in data or not isinstance(data.get('user_ids'), list):
        data['user_ids'] = []
    return data


def _save_user_data(bot_hash, user_hash, data):
    user_dir = _get_user_dir(bot_hash, user_hash)
    user_file = os.path.join(user_dir, 'user.json')
    return _save_json(user_file, data)


# ====== QQ 号绑定（.qdbind / .qdunbind）======
# binds.json 结构：{"binds": {"<被绑 user_hash>": {"owner": "<归属 user_hash>", "qq": "被绑QQ",
#                  "owner_qq": "操作者QQ", "bound_at": 时间戳}}}
# 语义：被绑 QQ 号的签到数据并入归属账号；被绑账号不再单独出现在排行榜里。

def _get_bind_file(bot_hash):
    return os.path.join(_get_bot_dir(bot_hash), 'binds.json')


def _load_binds(bot_hash):
    data = _load_json(_get_bind_file(bot_hash), default={})
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get('binds'), dict):
        data['binds'] = {}
    return data


def _save_binds(bot_hash, data):
    return _save_json(_get_bind_file(bot_hash), data)


def _resolve_account_hash(bot_hash, user_hash, binds=None):
    """沿绑定链上溯到真正的记账账号；带防环与深度保护，异常时返回入参。"""
    try:
        if binds is None:
            binds = _load_binds(bot_hash).get('binds', {})
        cur = _safe_str(user_hash)
        seen = set()
        for _ in range(MAX_BIND_DEPTH):
            rec = binds.get(cur)
            if not isinstance(rec, dict):
                break
            owner = _safe_str(rec.get('owner', ''))
            if not owner or owner == cur or owner in seen:
                break
            seen.add(cur)
            cur = owner
        return cur
    except Exception:
        return _safe_str(user_hash)


def _extract_target_qq(text):
    """从命令参数里提取 QQ 号：支持 @某人 的 CQ 码，也支持直接写数字。"""
    s = _safe_str(text)
    m = re.search(r'\[CQ:at,[^\]]*?qq=(\d+)', s)
    if m:
        return m.group(1)
    m = re.search(r'(\d{4,12})', s)
    if m:
        return m.group(1)
    return ''


def _touch_user_identity(data, plugin_event):
    uid = _safe_str(plugin_event.data.user_id)
    name = _safe_str(plugin_event.data.sender.get('name', ''))
    data['last_user_id'] = uid
    if name:
        data['last_name'] = name
    if uid and uid not in data.get('user_ids', []):
        data['user_ids'].append(uid)


def _touch_user_group(data, group_id):
    if group_id and group_id not in data.get('groups', []):
        data['groups'].append(group_id)


def _calc_jrrp(plugin_event):
    try:
        jrrp_mode = OlivaDiceCore.console.getConsoleSwitchByHash(
            'differentJrrpMode',
            plugin_event.bot_info.hash
        )
    except Exception:
        jrrp_mode = 0
    hash_tmp = hashlib.new('md5')
    hash_tmp.update(str(time.strftime('%Y-%m-%d', time.localtime())).encode(encoding='UTF-8'))
    hash_tmp.update(str(plugin_event.data.user_id).encode(encoding='UTF-8'))
    if jrrp_mode == 1:
        hash_tmp.update(str(plugin_event.bot_info.hash).encode(encoding='UTF-8'))
    return int(int(hash_tmp.hexdigest(), 16) % 100) + 1


def _get_ai_persona_prompt(group_id=None):
    """从 OlivaAIAgent 自动读取人设：prompt.system，群聊再叠加 prompt.group_persona。
    具体读取逻辑收在 OlivaAIAgent.conf.getPersonaPrompt 里，这里只做容错调用。"""
    if not has_OlivaAIAgent:
        return ''
    try:
        return str(OlivaAIAgent.conf.getPersonaPrompt(group_id=group_id) or '').strip()
    except Exception:
        return ''


def _ai_backend_ready():
    """OlivaAIAgent 是否已配置可用后端（api_url / api_key 至少有一个）。"""
    if not has_OlivaAIAgent:
        return False
    try:
        return OlivaAIAgent.conf.getChatBackend() is not None
    except Exception:
        return False


def _call_ai(messages, response_json=False, timeout=60):
    """签到相关的 AI 请求统一走 OlivaAIAgent 后端（与 .ai 同一份模型配置）。
    返回 (ok, text)；任何异常都返回 (False, '')，由调用方回退本地文案。"""
    if not has_OlivaAIAgent:
        return False, ''
    # 后端未配置 api_url/api_key 时直接短路，省掉一次注定失败的调用与 prompt 构造
    if not _ai_backend_ready():
        return False, ''
    try:
        res = OlivaAIAgent.aiClient.chat(
            messages=messages,
            force_no_stream=True,
            response_json=response_json,
            timeout_override=timeout,
        )
    except Exception:
        return False, ''
    if not isinstance(res, dict) or not res.get('ok'):
        return False, ''
    return True, str(res.get('text') or '')


def _clean_plain_text(text):
    if text is None:
        return ''
    s = str(text)
    # 去掉代码块/markdown
    s = s.replace('```', '')
    s = re.sub(r'^\s{0,3}#{1,6}\s*', '', s, flags=re.MULTILINE)
    s = s.replace('**', '').replace('*', '').replace('`', '')
    s = s.replace('> ', '')
    # 清理多余空行
    s = "\n".join([line.strip() for line in s.split('\n') if line.strip()])
    return s.strip()


def _truncate_200(text):
    s = _clean_plain_text(text)
    if len(s) <= 200:
        return s
    return s[:200].rstrip()


def _get_pc_name(plugin_event, hag_id=None):
    try:
        pc_hash = OlivaDiceCore.pcCard.getPcHash(plugin_event.data.user_id, plugin_event.platform['platform'])
        pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(pc_hash, hag_id)
        if pc_name is not None:
            pc_name = str(pc_name).strip()
        if pc_name:
            return pc_name
    except Exception:
        pass
    return None


def _build_name_tag(plugin_event, hag_id=None):
    """构造给模型用的名称串：昵称<人物卡>(QQ号)，便于模型按规则称呼。"""
    uid = _safe_str(plugin_event.data.user_id)
    sender_name = _safe_str(plugin_event.data.sender.get('name', '')).strip()
    pc_name = _get_pc_name(plugin_event, hag_id=hag_id)
    if pc_name and sender_name:
        if pc_name == sender_name:
            return f"{sender_name}({uid})"
        return f"{sender_name}<{pc_name}>({uid})"
    if sender_name:
        return f"{sender_name}({uid})"
    return f"({uid})"


def _get_call_name_from_tag(name_tag):
    """优先取 <> 里的称呼，否则取括号前昵称。"""
    s = _safe_str(name_tag)
    m = re.search(r'<([^<>]{1,40})>', s)
    if m:
        return m.group(1).strip()
    # 取 (qq) 之前的部分
    s2 = re.sub(r'\([^\)]*\)\s*$', '', s).strip()
    # 再去掉可能残留的 <> 段
    s2 = re.sub(r'<[^<>]*>', '', s2).strip()
    return s2 if s2 else '你'


def _fallback_coin_by_hour(hour):
    # 更偏向“起床时间”（6-9）高一些
    if 6 <= hour <= 9:
        return random.randint(24, 30)
    if 10 <= hour <= 13:
        return random.randint(18, 26)
    if 14 <= hour <= 18:
        return random.randint(14, 22)
    if 19 <= hour <= 23:
        return random.randint(10, 18)
    return random.randint(10, 16)


def _fallback_sign_text(name, now_dt, coin_delta, jrrp):
    hour = now_dt.hour
    call_name = str(name).strip() if str(name).strip() else '你'
    base_prefix = "小芙用平板连上主人的数据库，签到记录已经写入啦~"

    morning = [
        f"{base_prefix}\n(尾巴轻轻一摆)\n早安呀。今天也请把节奏慢慢找回来~",
        f"{base_prefix}\n(把爪机扣在桌上)\n起床时间签到更划算呢~别赖床啦。",
        f"{base_prefix}\n(狐耳抖了抖)\n早上的空气很清爽，适合从一件小事开始。",
        f"{base_prefix}\n(伸了个小懒腰)\n今天就从一口水和一个目标开始吧~",
    ]
    noon = [
        f"{base_prefix}\n(晃了晃平板)\n午间补能完成~记得吃点甜的也行。",
        f"{base_prefix}\n(尾巴左右摆动)\n中午啦，中场休息一下再继续冲~",
        f"{base_prefix}\n(眯起眼笑)\n把午后的麻烦先丢给未来的自己一会儿~",
        f"{base_prefix}\n(用爪机点了点)\n签到成功。接下来就看你怎么把好运用掉啦~",
    ]
    afternoon = [
        f"{base_prefix}\n(把枫叶吊坠U盘晃了晃)\n下午也要稳住节奏，别被困意偷袭~",
        f"{base_prefix}\n(狐耳竖起)\n继续走吧。一步一步来就很厉害了。",
        f"{base_prefix}\n(尾巴尖轻抖)\n我把今日的份额给你记上了，可别偷懒呀~",
        f"{base_prefix}\n(眨眨眼)\n嗯哼，签到完成。接下来轮到你发光了~",
    ]
    evening = [
        f"{base_prefix}\n(把定制爪机别回尾巴)\n辛苦啦。今晚就对自己好一点~",
        f"{base_prefix}\n(狐耳微微炸毛又收回去)\n忙到现在还记得签到，很乖呢~",
        f"{base_prefix}\n(轻轻哼了一声)\n今天也算是好好活过的一天，奖励收下~",
        f"{base_prefix}\n(尾巴绕了个小圈)\n夜晚适合收尾，不适合自责。去休息吧~",
    ]
    late = [
        f"{base_prefix}\n(小声)\n这么晚/这么早还醒着呀……先把自己照顾好。",
        f"{base_prefix}\n(狐耳贴下去一点)\n别熬太狠啦，我会担心的。",
        f"{base_prefix}\n(尾巴把自己裹紧一点)\n签到完成。答应我，能睡就睡~",
    ]

    if 6 <= hour <= 9:
        pick = random.choice(morning)
    elif 10 <= hour <= 13:
        pick = random.choice(noon)
    elif 14 <= hour <= 18:
        pick = random.choice(afternoon)
    elif 19 <= hour <= 23:
        pick = random.choice(evening)
    else:
        pick = random.choice(late)

    # 末尾再自然称呼一次（避免首句直接点名）
    tail = f"\n\n{call_name}，今天也加油喔~"
    return _truncate_200(pick + tail)


def _try_ai_sign(plugin_event, now_dt, jrrp, extra_text='', name_tag=''):
    """一次调用主模型出结果：同一次请求返回 {"coins": 整数, "text": "签到短句"}。

    人设与后端均取自 OlivaAIAgent（人设 → prompt.system + prompt.group_persona，
    后端 → config.json 的 backend 段）。任何失败都返回 None，由调用方回退本地文案。
    text 允许为空：此时调用方只对文案做本地回退，灵币仍沿用模型给的值。"""
    if not has_OlivaAIAgent:
        return None
    try:
        hour = now_dt.hour
        time_str = now_dt.strftime('%Y-%m-%d %H:%M')
        uid = _safe_str(plugin_event.data.user_id)
        is_master = uid in MASTER_UIDS
        who = SPECIAL_UIDS.get(uid, '')
        group_id = _safe_str(getattr(plugin_event.data, 'group_id', None)) if plugin_event.plugin_info['func_type'] == 'group_message' else None
        persona = _get_ai_persona_prompt(group_id=group_id)

        sys_prompt = (
            (persona + "\n\n" if persona else "")
            + "本次任务：一次给出签到结果，包含本次发放的灵币与一段签到回应短句。\n"
            + "【灵币 coins】必须是 10-30 的整数；早上 6-9 点更容易给高数值。\n"
            + "【签到=早安】签到就是早安的意思，是用户向你问候。\n"
            + "【不同时间段的回应】\n"
            + "- 早上6-9点：回复早安，温暖问候新的一天开始\n"
            + "- 中午/下午（10-18点）：可以善意调侃起晚了（如太阳晒屁股了、睡到现在才醒之类）\n"
            + "- 晚上19-23点：提醒今天才来打卡，也许该早点休息\n"
            + "- 深夜/凌晨：关心为什么这么晚/这么早还醒着，提醒注意休息\n"
            + "【回应风格】100字以内，以符合人设的自然口吻回复，就像朋友间的日常问候；不要提及你是AI。\n"
            + "系统会单独展示灵币数量与今日人品，短句里不要重复输出 coins 数字。\n"
            + "只输出 JSON，且仅包含 coins（整数）与 text（字符串）两个字段，不要输出任何其它内容。\n"
            + "输出示例：{\"coins\": 20, \"text\": \"早安呀，今天也要好好过~\"}"
        )
        user_prompt = (
            f"用户名称：{_safe_str(name_tag)}\n"
            f"当前时间：{time_str}（{hour}点）\n"
            f"今日人品：{jrrp}\n"
            f"用户补充：{_safe_str(extra_text).strip()}\n"
            f"是否主人：{str(is_master)}\n"
            f"特殊身份：{who}\n"
            "请输出 JSON。"
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ]
        # 一次调用拿全部结果，response_format={"type":"json_object"} 兜底
        ok, answer_text = _call_ai(messages, response_json=True)
        if not ok or not answer_text:
            return None
        m = re.search(r'\{[\s\S]*\}', str(answer_text))
        if not m:
            return None
        obj = json.loads(m.group(0))
        if not isinstance(obj, dict):
            return None
        coins = int(obj.get('coins'))
        if coins < 10:
            coins = 10
        elif coins > 30:
            coins = 30
        # 短句可能为空/格式异常，_truncate_200 内部已做清洗，空串交由调用方回退
        text = _truncate_200(obj.get('text', ''))
        return {'coins': coins, 'text': text}
    except Exception:
        return None


def _get_stranger_name(plugin_event, user_id):
    """通过 get_stranger_info 获取陌生人的昵称。"""
    try:
        uid_str = _safe_str(user_id).strip()
        if not uid_str:
            return None
        result = plugin_event.get_stranger_info(uid_str)
        if result and isinstance(result, dict) and result.get('active'):
            data = result.get('data', {})
            if isinstance(data, dict):
                nickname = _safe_str(data.get('nickname') or data.get('name') or '').strip()
                if nickname:
                    return nickname
    except Exception:
        pass
    return None


def _get_member_name_from_list(group_member_list, user_id):
    """从群成员列表中获取指定用户的显示名称（名片或昵称）。"""
    try:
        uid_str = _safe_str(user_id)
        if not group_member_list or not isinstance(group_member_list, dict):
            return None
        if not group_member_list.get('active'):
            return None
        members = group_member_list.get('data', [])
        if not isinstance(members, list):
            return None
        for m in members:
            if not isinstance(m, dict):
                continue
            mid = m.get('user_id') or m.get('id') or m.get('qq')
            if _safe_str(mid) == uid_str:
                return _safe_str(m.get('card') or m.get('name') or '').strip()
    except Exception:
        pass
    return None


def _get_all_user_entries(bot_hash):
    """返回 [(user_hash, data_dict)]，扫描所有用户数据。
    已被绑定进其它账号的 user_hash 不再单独列出，避免排行榜出现重复的同一个人。"""
    entries = []
    bot_dir = _get_bot_dir(bot_hash)
    try:
        bound_hashes = set(_load_binds(bot_hash).get('binds', {}).keys())
    except Exception:
        bound_hashes = set()
    try:
        for name in os.listdir(bot_dir):
            p = os.path.join(bot_dir, name)
            if os.path.isdir(p):
                if name in bound_hashes:
                    continue
                # 结构：<user_hash>/user.json
                user_file = os.path.join(p, 'user.json')
                data = _load_json(user_file, default=None)
                if isinstance(data, dict) and not data.get('merged_into'):
                    entries.append((name, data))
    except Exception:
        pass
    return entries


def _format_rank_list(sorted_items, top_n=10, group_member_list=None, plugin_event=None, is_global_rank=False):
    """格式化排行榜列表。
    
    Args:
        sorted_items: 排序后的用户数据列表 [(user_hash, data_dict)]
        top_n: 显示前N名
        group_member_list: 群成员列表（用于群榜获取实时昵称）
        plugin_event: plugin_event 对象（用于总榜获取陌生人信息）
        is_global_rank: 是否为总榜（总榜会调用 get_stranger_info）
    """
    lines = []
    for idx, (user_hash, data) in enumerate(sorted_items[:top_n], start=1):
        coins = int(data.get('anima_coin', 0) or 0)
        
        # 优先使用 last_name
        name = _safe_str(data.get('last_name', '')).strip()
        
        # 如果是群榜且提供了群成员列表，尝试从中获取实时昵称
        if not name and group_member_list:
            user_id = _safe_str(data.get('last_user_id', '')).strip()
            if user_id:
                member_name = _get_member_name_from_list(group_member_list, user_id)
                if member_name:
                    name = member_name
        
        # 如果是总榜且有 plugin_event，尝试通过 get_stranger_info 获取昵称
        if not name and is_global_rank and plugin_event:
            user_id = _safe_str(data.get('last_user_id', '')).strip()
            if user_id:
                stranger_name = _get_stranger_name(plugin_event, user_id)
                if stranger_name:
                    name = stranger_name
        
        # 最后回退到 last_user_id 或 user_hash
        if not name:
            name = _safe_str(data.get('last_user_id', '')).strip() or user_hash
        
        lines.append(f"{idx}. {name} - {coins}")
    if not lines:
        return '（暂无数据）'
    return '\n'.join(lines)


def _calc_rank(sorted_items, self_user_hash, self_data):
    total = len(sorted_items)
    self_rank = '-'
    for idx, (user_hash, data) in enumerate(sorted_items, start=1):
        if user_hash == self_user_hash:
            self_rank = str(idx)
            break
    if self_data is None:
        self_coins = 0
    else:
        self_coins = int(self_data.get('anima_coin', 0) or 0)
    return total, self_rank, self_coins

def unity_init(plugin_event, Proc):
    # 这里是插件初始化，通常用于加载配置等
    pass

def data_init(plugin_event, Proc):
    # 这里是数据初始化，通常用于加载数据等
    FroniaSign.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

def unity_reply(plugin_event, Proc):
    OlivaDiceCore.userConfig.setMsgCount()
    dictTValue = OlivaDiceCore.msgCustom.dictTValue.copy()
    dictTValue['tUserName'] = plugin_event.data.sender['name']
    dictTValue['tName'] = plugin_event.data.sender['name']
    dictStrCustom = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]
    dictGValue = OlivaDiceCore.msgCustom.dictGValue
    dictTValue.update(dictGValue)
    dictTValue = OlivaDiceCore.msgCustomManager.dictTValueInit(plugin_event, dictTValue)

    valDict = {}
    valDict['dictTValue'] = dictTValue
    valDict['dictStrCustom'] = dictStrCustom
    valDict['tmp_platform'] = plugin_event.platform['platform']

    replyMsg = OlivaDiceCore.msgReply.replyMsg
    isMatchWordStart = OlivaDiceCore.msgReply.isMatchWordStart
    getMatchWordStartRight = OlivaDiceCore.msgReply.getMatchWordStartRight
    skipSpaceStart = OlivaDiceCore.msgReply.skipSpaceStart
    skipToRight = OlivaDiceCore.msgReply.skipToRight
    msgIsCommand = OlivaDiceCore.msgReply.msgIsCommand

    tmp_at_str = OlivOS.messageAPI.PARA.at(plugin_event.base_info['self_id']).CQ()
    tmp_id_str = str(plugin_event.base_info['self_id'])
    tmp_at_str_sub = None
    tmp_id_str_sub = None
    tmp_id_str_sub_open = None
    if 'sub_self_id' in plugin_event.data.extend:
        if plugin_event.data.extend['sub_self_id'] != None:
            tmp_at_str_sub = OlivOS.messageAPI.PARA.at(plugin_event.data.extend['sub_self_id']).CQ()
            tmp_id_str_sub = str(plugin_event.data.extend['sub_self_id'])
    if 'sub_self_open_id' in plugin_event.data.extend:
        if plugin_event.data.extend['sub_self_open_id'] != None:
            tmp_id_str_sub_open = str(plugin_event.data.extend['sub_self_open_id'])
    tmp_command_str_1 = '.'
    tmp_command_str_2 = '。'
    tmp_command_str_3 = '/'
    tmp_reast_str = plugin_event.data.message
    flag_force_reply = False
    flag_is_command = False
    flag_is_from_host = False
    flag_is_from_group = False
    flag_is_from_group_admin = False
    flag_is_from_group_have_admin = False
    flag_is_from_master = False
    if isMatchWordStart(tmp_reast_str, '[CQ:reply,id='):
        tmp_reast_str = skipToRight(tmp_reast_str, ']')
        tmp_reast_str = tmp_reast_str[1:]
    if flag_force_reply is False:
        tmp_reast_str_old = tmp_reast_str
        tmp_reast_obj = OlivOS.messageAPI.Message_templet(
            'old_string',
            tmp_reast_str
        )
        tmp_at_list = []
        for tmp_reast_obj_this in tmp_reast_obj.data:
            tmp_para_str_this = tmp_reast_obj_this.CQ()
            if type(tmp_reast_obj_this) is OlivOS.messageAPI.PARA.at:
                tmp_at_list.append(str(tmp_reast_obj_this.data['id']))
                tmp_reast_str = tmp_reast_str.lstrip(tmp_para_str_this)
            elif type(tmp_reast_obj_this) is OlivOS.messageAPI.PARA.text:
                if tmp_para_str_this.strip(' ') == '':
                    tmp_reast_str = tmp_reast_str.lstrip(tmp_para_str_this)
                else:
                    break
            else:
                break
        if tmp_id_str in tmp_at_list:
            flag_force_reply = True
        if tmp_id_str_sub in tmp_at_list:
            flag_force_reply = True
        if tmp_id_str_sub_open in tmp_at_list:
            flag_force_reply = True
        if 'all' in tmp_at_list:
            flag_force_reply = True
        if flag_force_reply is True:
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
        else:
            tmp_reast_str = tmp_reast_str_old
    [tmp_reast_str, flag_is_command] = msgIsCommand(
        tmp_reast_str,
        OlivaDiceCore.crossHook.dictHookList['prefix']
    )
    if flag_is_command:
        tmp_hostID = None
        tmp_hagID = None
        tmp_userID = plugin_event.data.user_id
        valDict['tmp_userID'] = tmp_userID
        tmp_list_hit = []
        flag_is_from_master = OlivaDiceCore.ordinaryInviteManager.isInMasterList(
            plugin_event.bot_info.hash,
            OlivaDiceCore.userConfig.getUserHash(
                plugin_event.data.user_id,
                'user',
                plugin_event.platform['platform']
            )
        )
        valDict['flag_is_from_master'] = flag_is_from_master
        if plugin_event.plugin_info['func_type'] == 'group_message':
            if plugin_event.data.host_id != None:
                flag_is_from_host = True
            flag_is_from_group = True
        elif plugin_event.plugin_info['func_type'] == 'private_message':
            flag_is_from_group = False
        if flag_is_from_group:
            if 'role' in plugin_event.data.sender:
                flag_is_from_group_have_admin = True
                if plugin_event.data.sender['role'] in ['owner', 'admin']:
                    flag_is_from_group_admin = True
                elif plugin_event.data.sender['role'] in ['sub_admin']:
                    flag_is_from_group_admin = True
                    flag_is_from_group_sub_admin = True
        if flag_is_from_host and flag_is_from_group:
            tmp_hagID = '%s|%s' % (str(plugin_event.data.host_id), str(plugin_event.data.group_id))
        elif flag_is_from_group:
            tmp_hagID = str(plugin_event.data.group_id)
        flag_hostEnable = True
        if flag_is_from_host:
            flag_hostEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId = plugin_event.data.host_id,
                userType = 'host',
                platform = plugin_event.platform['platform'],
                userConfigKey = 'hostEnable',
                botHash = plugin_event.bot_info.hash
            )
        flag_hostLocalEnable = True
        if flag_is_from_host:
            flag_hostLocalEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId = plugin_event.data.host_id,
                userType = 'host',
                platform = plugin_event.platform['platform'],
                userConfigKey = 'hostLocalEnable',
                botHash = plugin_event.bot_info.hash
            )
        flag_groupEnable = True
        if flag_is_from_group:
            if flag_is_from_host:
                if flag_hostEnable:
                    flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userId = tmp_hagID,
                        userType = 'group',
                        platform = plugin_event.platform['platform'],
                        userConfigKey = 'groupEnable',
                        botHash = plugin_event.bot_info.hash
                    )
                else:
                    flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userId = tmp_hagID,
                        userType = 'group',
                        platform = plugin_event.platform['platform'],
                        userConfigKey = 'groupWithHostEnable',
                        botHash = plugin_event.bot_info.hash
                    )
            else:
                flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                    userId = tmp_hagID,
                    userType = 'group',
                    platform = plugin_event.platform['platform'],
                    userConfigKey = 'groupEnable',
                    botHash = plugin_event.bot_info.hash
                )
        #此频道关闭时中断处理
        if not flag_hostLocalEnable and not flag_force_reply:
            return
        #此群关闭时中断处理
        if not flag_groupEnable and not flag_force_reply:
            return
        '''到这里为止，前面的都不动，后面进行你写的命令处理，以下则为.testcommand为例子，可以按照这里进行对应修改。'''
        # ====== FroniaSign: QQ 号绑定 / 解绑 ======
        if isMatchWordStart(tmp_reast_str, ['qdbind', 'qd绑定', '绑定qq'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['qdbind', 'qd绑定', '绑定qq'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')

            target_qq = _extract_target_qq(tmp_reast_str)
            dictTValue['tQdTargetQq'] = target_qq or _safe_str(tmp_reast_str).strip()
            if not target_qq:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strQdUsage'], dictTValue)
                if tmp_reply_str is not None:
                    replyMsg(plugin_event, tmp_reply_str)
                return

            bot_hash = _get_bot_hash(plugin_event)
            self_qq = _safe_str(plugin_event.data.user_id)
            # 目标是 QQ 号 → 固定按 OneBot 平台算 hash，避免在 qqGuildv2 会话里绑错账号
            target_hash = _calc_user_hash_by_user_id(target_qq, QQ_ONEBOT_PLATFORM)

            binds_data = _load_binds(bot_hash)
            binds = binds_data.get('binds', {})
            root_hash = _resolve_account_hash(bot_hash, _get_user_hash(plugin_event), binds)

            if target_hash == root_hash or target_hash == self_qq:
                key = 'strQdBindSelf'
            elif target_hash in binds:
                # 唯一性：被绑定过的 QQ 号不能再次绑定
                key = 'strQdBindDup'
            elif any(
                isinstance(_rec, dict) and _safe_str(_rec.get('owner', '')) == target_hash
                for _rec in binds.values()
            ):
                key = 'strQdBindOwner'
            else:
                # 合并：把被绑账号的灵币与身份并进归属账号
                owner_data = _load_user_data(bot_hash, root_hash, self_qq)
                target_data = _load_user_data(bot_hash, target_hash, target_qq)
                delta = int(target_data.get('anima_coin', 0) or 0)
                owner_data['anima_coin'] = int(owner_data.get('anima_coin', 0) or 0) + delta
                for _uid in (target_data.get('user_ids', []) or []):
                    _uid = _safe_str(_uid)
                    if _uid and _uid not in owner_data['user_ids']:
                        owner_data['user_ids'].append(_uid)
                if target_qq and target_qq not in owner_data['user_ids']:
                    owner_data['user_ids'].append(target_qq)
                for _gid in (target_data.get('groups', []) or []):
                    _gid = _safe_str(_gid)
                    if _gid and _gid not in owner_data['groups']:
                        owner_data['groups'].append(_gid)
                _touch_user_identity(owner_data, plugin_event)
                if flag_is_from_group:
                    _touch_user_group(owner_data, _safe_str(plugin_event.data.group_id))
                _save_user_data(bot_hash, root_hash, owner_data)

                # 被绑账号清空并打上归属标记（数据已并入归属账号，不再单独计榜）
                # 保留昵称等身份字段，便于将来解绑后排行榜仍能显示昵称
                merged_target = {
                    'anima_coin': 0,
                    'groups': list(target_data.get('groups', []) or []),
                    'user_ids': list(target_data.get('user_ids', []) or []),
                    'merged_into': root_hash,
                    'merged_at': int(time.time()),
                }
                if _safe_str(target_data.get('last_user_id', '')):
                    merged_target['last_user_id'] = _safe_str(target_data.get('last_user_id', ''))
                if _safe_str(target_data.get('last_name', '')):
                    merged_target['last_name'] = _safe_str(target_data.get('last_name', ''))
                if target_qq and target_qq not in merged_target['user_ids']:
                    merged_target['user_ids'].append(target_qq)
                _save_user_data(bot_hash, target_hash, merged_target)
                binds[target_hash] = {
                    'owner': root_hash,
                    'qq': target_qq,
                    'owner_qq': self_qq,
                    'bound_at': int(time.time()),
                    # 并入时的灵币数额：解绑时按此额从归属账号扣回、退还给被解绑号
                    'merged_coin': delta,
                }
                binds_data['binds'] = binds
                _save_binds(bot_hash, binds_data)

                dictTValue['tQdDelta'] = str(delta)
                dictTValue['tCoinTotal'] = str(int(owner_data.get('anima_coin', 0) or 0))
                key = 'strQdBindOk'

            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom[key], dictTValue)
            if tmp_reply_str is not None:
                replyMsg(plugin_event, tmp_reply_str)
            return

        if isMatchWordStart(tmp_reast_str, ['qdunbind', 'qd解绑', '解绑qq'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['qdunbind', 'qd解绑', '解绑qq'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')

            target_qq = _extract_target_qq(tmp_reast_str)
            dictTValue['tQdTargetQq'] = target_qq or _safe_str(tmp_reast_str).strip()
            if not target_qq:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strQdUsage'], dictTValue)
                if tmp_reply_str is not None:
                    replyMsg(plugin_event, tmp_reply_str)
                return

            bot_hash = _get_bot_hash(plugin_event)
            self_qq = _safe_str(plugin_event.data.user_id)
            # 目标是 QQ 号 → 固定按 OneBot 平台算 hash，避免在 qqGuildv2 会话里绑错账号
            target_hash = _calc_user_hash_by_user_id(target_qq, QQ_ONEBOT_PLATFORM)

            binds_data = _load_binds(bot_hash)
            binds = binds_data.get('binds', {})
            rec = binds.get(target_hash)

            if not isinstance(rec, dict):
                key = 'strQdUnbindNone'
            else:
                root_hash = _resolve_account_hash(bot_hash, _get_user_hash(plugin_event), binds)
                is_master_user = bool(flag_is_from_master) or (self_qq in MASTER_UIDS)
                if _safe_str(rec.get('owner', '')) != root_hash and not is_master_user:
                    key = 'strQdUnbindDeny'
                else:
                    owner_hash = _safe_str(rec.get('owner', ''))
                    merged_coin = int(rec.get('merged_coin', 0) or 0)

                    # 反向拆账：从归属账号扣回当初并入的等额灵币，退还给被解绑号
                    # （未记录并入额的历史数据 merged_coin=0，退 0，行为同旧版；余额不足时按实际余额退）
                    refund = 0
                    if owner_hash and merged_coin > 0:
                        owner_data = _load_user_data(bot_hash, owner_hash, '')
                        owner_coin = int(owner_data.get('anima_coin', 0) or 0)
                        refund = merged_coin if owner_coin >= merged_coin else max(owner_coin, 0)
                        owner_data['anima_coin'] = owner_coin - refund
                        _save_user_data(bot_hash, owner_hash, owner_data)

                    binds.pop(target_hash, None)
                    binds_data['binds'] = binds
                    _save_binds(bot_hash, binds_data)

                    target_data = _load_user_data(bot_hash, target_hash, target_qq)
                    target_data.pop('merged_into', None)
                    target_data.pop('merged_at', None)
                    target_data['anima_coin'] = refund
                    _save_user_data(bot_hash, target_hash, target_data)

                    dictTValue['tQdRefund'] = str(refund)
                    key = 'strQdUnbindOk'

            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom[key], dictTValue)
            if tmp_reply_str is not None:
                replyMsg(plugin_event, tmp_reply_str)
            return

        # ====== FroniaSign: 签到/灵币/排行 ======
        if isMatchWordStart(tmp_reast_str, ['签到', '打卡', 'sign', '早安', '早'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['签到', '打卡', 'sign', '早安', '早'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')

            extra_text = tmp_reast_str

            bot_hash = _get_bot_hash(plugin_event)
            # 若当前 QQ 号已被绑定，签到记账落在归属账号上
            user_hash = _resolve_account_hash(bot_hash, _get_user_hash(plugin_event))
            group_id = None
            if flag_is_from_group:
                group_id = _safe_str(plugin_event.data.group_id)

            data = _load_user_data(bot_hash, user_hash, plugin_event.data.user_id)
            _touch_user_identity(data, plugin_event)
            if group_id:
                _touch_user_group(data, group_id)

            today = time.strftime('%Y-%m-%d', time.localtime())
            now_ts = int(time.time())
            now_dt = datetime.fromtimestamp(now_ts)
            jrrp_int = _calc_jrrp(plugin_event)

            dictTValue['tJrrpResult'] = str(jrrp_int)
            dictTValue['tCoinTotal'] = str(int(data.get('anima_coin', 0) or 0))

            if _safe_str(data.get('last_sign_date', None)) == today:
                dictTValue['tLastSignTime'] = _safe_str(data.get('last_sign_time', ''))
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strSignAlready'], dictTValue)
                if tmp_reply_str is not None:
                    replyMsg(plugin_event, tmp_reply_str)
                return

            name_tag = _build_name_tag(plugin_event, hag_id=tmp_hagID)
            call_name = _get_call_name_from_tag(name_tag)

            ai_res = _try_ai_sign(plugin_event, now_dt, jrrp_int, extra_text=extra_text, name_tag=name_tag)
            if ai_res and isinstance(ai_res, dict):
                coin_delta = int(ai_res.get('coins', 0) or 0)
                sign_text = _safe_str(ai_res.get('text', '')).strip()
            else:
                coin_delta = _fallback_coin_by_hour(now_dt.hour)
                sign_text = _fallback_sign_text(call_name, now_dt, coin_delta, jrrp_int)
            if coin_delta < 10:
                coin_delta = 10
            if coin_delta > 30:
                coin_delta = 30
            if not sign_text:
                sign_text = _fallback_sign_text(call_name, now_dt, coin_delta, jrrp_int)

            data['last_sign_date'] = today
            data['last_sign_ts'] = now_ts
            data['last_sign_time'] = now_dt.strftime('%H:%M:%S')
            data['last_coin_delta'] = coin_delta
            data['last_sign_text'] = sign_text
            data['anima_coin'] = int(data.get('anima_coin', 0) or 0) + int(coin_delta)
            _save_user_data(bot_hash, user_hash, data)

            dictTValue['tSignText'] = sign_text
            dictTValue['tCoinDelta'] = str(coin_delta)
            dictTValue['tCoinTotal'] = str(int(data.get('anima_coin', 0) or 0))
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strSignResult'], dictTValue)
            if tmp_reply_str is not None:
                replyMsg(plugin_event, tmp_reply_str)
            return

        # 注意：'灵币' 是 '灵币排行'/'灵币总榜' 的前缀，必须排除这两类，否则会被本分支抢先匹配
        if (
            not isMatchWordStart(tmp_reast_str, ['灵币排行', '灵币总榜'], isCommand=True)
            and isMatchWordStart(tmp_reast_str, ['查询灵币', '灵币查询', '灵币', 'coin'], isCommand=True)
        ):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['灵币查询', '灵币', 'coin'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')

            bot_hash = _get_bot_hash(plugin_event)
            user_hash = _resolve_account_hash(bot_hash, _get_user_hash(plugin_event))
            data = _load_user_data(bot_hash, user_hash, plugin_event.data.user_id)
            _touch_user_identity(data, plugin_event)
            if flag_is_from_group:
                _touch_user_group(data, _safe_str(plugin_event.data.group_id))
            _save_user_data(bot_hash, user_hash, data)

            dictTValue['tCoinTotal'] = str(int(data.get('anima_coin', 0) or 0))
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCoinInfo'], dictTValue)
            if tmp_reply_str is not None:
                replyMsg(plugin_event, tmp_reply_str)
            return

        if isMatchWordStart(tmp_reast_str, ['灵币总榜', '总榜', 'globalrank'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['灵币总榜', '总榜', 'globalrank'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')

            bot_hash = _get_bot_hash(plugin_event)
            user_hash = _resolve_account_hash(bot_hash, _get_user_hash(plugin_event))
            self_data = _load_user_data(bot_hash, user_hash, plugin_event.data.user_id)
            _touch_user_identity(self_data, plugin_event)
            if flag_is_from_group:
                _touch_user_group(self_data, _safe_str(plugin_event.data.group_id))
            _save_user_data(bot_hash, user_hash, self_data)

            items = _get_all_user_entries(bot_hash)
            # 统一字段
            norm_items = []
            for uh, d in items:
                if not isinstance(d, dict):
                    continue
                if 'anima_coin' not in d:
                    continue
                norm_items.append((uh, d))
            norm_items.sort(key=lambda x: int(x[1].get('anima_coin', 0) or 0), reverse=True)

            dictTValue['tRankList'] = _format_rank_list(norm_items, top_n=10, plugin_event=plugin_event, is_global_rank=True)
            total, self_rank, self_coins = _calc_rank(norm_items, user_hash, self_data)
            dictTValue['tRankTotal'] = str(total)
            dictTValue['tSelfRank'] = str(self_rank)
            dictTValue['tCoinTotal'] = str(self_coins)

            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCoinRankGlobal'], dictTValue)
            if tmp_reply_str is not None:
                replyMsg(plugin_event, tmp_reply_str)
            return

        if isMatchWordStart(tmp_reast_str, ['灵币排行', '排行', 'rank'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['灵币排行', '排行', 'rank'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')

            if not flag_is_from_group:
                replyMsg(plugin_event, '【灵币排行】仅群聊可用。')
                return

            bot_hash = _get_bot_hash(plugin_event)
            group_id = _safe_str(plugin_event.data.group_id)
            user_hash = _resolve_account_hash(bot_hash, _get_user_hash(plugin_event))
            self_data = _load_user_data(bot_hash, user_hash, plugin_event.data.user_id)
            _touch_user_identity(self_data, plugin_event)

            # 按 jrlp 的方式：实时拉群成员列表 -> 转 hash -> 逐个比对
            group_member_list = plugin_event.get_group_member_list(group_id)
            if not group_member_list or not isinstance(group_member_list, dict) or group_member_list.get('active') is False:
                replyMsg(plugin_event, '获取群成员列表失败')
                return
            
            # 从群成员列表构建 user_hash 集合
            platform = plugin_event.platform.get('platform', None)
            group_user_hash_set = set()
            if platform:
                members = group_member_list.get('data', [])
                for m in members:
                    if not isinstance(m, dict):
                        continue
                    uid = m.get('user_id') or m.get('id') or m.get('qq')
                    if uid:
                        group_user_hash_set.add(_calc_user_hash_by_user_id(uid, platform))

            _touch_user_group(self_data, group_id)
            _save_user_data(bot_hash, user_hash, self_data)

            items = _get_all_user_entries(bot_hash)
            norm_items = []
            for uh, d in items:
                if not isinstance(d, dict):
                    continue
                if 'anima_coin' not in d:
                    continue
                if uh in group_user_hash_set:
                    norm_items.append((uh, d))
            # 确保自己在榜里（即使还没被记录到groups，也至少可见）
            if not any(uh == user_hash for uh, _ in norm_items):
                norm_items.append((user_hash, self_data))
            norm_items.sort(key=lambda x: int(x[1].get('anima_coin', 0) or 0), reverse=True)

            dictTValue['tRankList'] = _format_rank_list(norm_items, top_n=10, group_member_list=group_member_list)
            total, self_rank, self_coins = _calc_rank(norm_items, user_hash, self_data)
            dictTValue['tRankTotal'] = str(total)
            dictTValue['tSelfRank'] = str(self_rank)
            dictTValue['tCoinTotal'] = str(self_coins)

            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCoinRankGroup'], dictTValue)
            if tmp_reply_str is not None:
                replyMsg(plugin_event, tmp_reply_str)
            return

        # 模板演示命令已移除
