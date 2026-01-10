# -*- encoding: utf-8 -*-

import os
import json
import random
from typing import Dict, List, Optional, Tuple

import OlivaDiceCore
import OlivOS


def liarbar_default() -> dict:
    return {
        'version': 1,
        'state': 'idle',  # idle|waiting|playing
        'players': [],
        'join_order': [],
        'min_players': 2,
        'max_players': 6,

        'round_no': 0,
        'real_card': None,  # A/Q/K
        'turn_seat_id': None,
        'last_play': None,  # {'seat_id':int,'cards':list[str],'is_demon':bool}
        'last_seat_id': None,
    }


def get_nickname(
    plugin_event,
    user_id: str,
    tmp_hagID: Optional[str] = None,
    fallback_prefix: str = '',
) -> str:
    try:
        fallback_prefix = fallback_prefix or ''
        default_name = f"{fallback_prefix}{user_id}" if fallback_prefix else str(user_id)
        # 优先使用人物卡名称
        tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(user_id, plugin_event.platform['platform'])
        tmp_pcName = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
        if tmp_pcName:
            return tmp_pcName

        # QQ频道：若无人物卡名，则回退到人物卡hash
        if plugin_event.platform['platform'] == 'qqGuild':
            return f"{fallback_prefix}{tmp_pcHash}" if fallback_prefix else str(tmp_pcHash)

        pid_nickname = OlivaDiceCore.userConfig.getUserConfigByKey(
            userId=user_id,
            userType='user',
            platform=plugin_event.platform['platform'],
            userConfigKey='userName',
            botHash=plugin_event.bot_info.hash,
            default=default_name,
        )
        if pid_nickname and pid_nickname != default_name and pid_nickname != fallback_prefix:
            return pid_nickname

        plres = plugin_event.get_stranger_info(user_id)
        if plres.get('active'):
            pid_nickname = plres['data']['name']
            if pid_nickname == fallback_prefix and fallback_prefix:
                return default_name
            if pid_nickname and pid_nickname != default_name and pid_nickname != fallback_prefix:
                return pid_nickname
            return default_name
        return default_name
    except Exception:
        return f"{fallback_prefix}{user_id}" if fallback_prefix else str(user_id)


# ----------------------------
# 数据持久化（主从链接重定向）
# ----------------------------


def get_liarbar_data_path() -> str:
    data_path = os.path.join('plugin', 'data', 'LiarBar')
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    return data_path


def get_redirected_bot_hash(bot_hash: str) -> str:
    try:
        master = OlivaDiceCore.console.getMasterBotHash(bot_hash)
        if master:
            return str(master)
    except Exception:
        pass
    return bot_hash


def get_group_file_path(bot_hash: str, group_hash: str) -> str:
    data_path = get_liarbar_data_path()
    bot_hash = get_redirected_bot_hash(bot_hash)
    bot_path = os.path.join(data_path, bot_hash)
    if not os.path.exists(bot_path):
        os.makedirs(bot_path)
    return os.path.join(bot_path, f"{group_hash}.json")


def load_group_data(bot_hash: str, group_hash: str) -> dict:
    file_path = get_group_file_path(bot_hash, group_hash)
    default_data = liarbar_default()

    redirected = get_redirected_bot_hash(bot_hash)
    if redirected != bot_hash and not os.path.exists(file_path):
        data_path = get_liarbar_data_path()
        legacy_bot_path = os.path.join(data_path, bot_hash)
        legacy_path = os.path.join(legacy_bot_path, f"{group_hash}.json")
        if os.path.exists(legacy_path):
            file_path = legacy_path

    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and all(k in data for k in default_data.keys()):
                    return data
        except (IOError, json.JSONDecodeError):
            pass

    return default_data


def save_group_data(bot_hash: str, group_hash: str, data: dict) -> None:
    file_path = get_group_file_path(bot_hash, group_hash)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_user_file_path(bot_hash: str, user_hash: str) -> str:
    data_path = get_liarbar_data_path()
    bot_hash = get_redirected_bot_hash(bot_hash)
    bot_path = os.path.join(data_path, bot_hash, 'user')
    if not os.path.exists(bot_path):
        os.makedirs(bot_path)
    return os.path.join(bot_path, f"{user_hash}.json")


def load_user_data(bot_hash: str, user_hash: str) -> dict:
    file_path = get_user_file_path(bot_hash, user_hash)
    default_data = {
        'last_group_hash': None,
        'last_group_id': None,
        'last_host_id': None,
    }

    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and all(k in data for k in default_data.keys()):
                    return data
        except (IOError, json.JSONDecodeError):
            pass

    return default_data


def save_user_data(bot_hash: str, user_hash: str, data: dict) -> None:
    file_path = get_user_file_path(bot_hash, user_hash)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ----------------------------
# 规则与工具
# ----------------------------


def shot(attempts: int) -> bool:
    """开枪判定：True 空弹；False 实弹（被淘汰）。逻辑对齐 bar.py。"""
    rnd_number = random.randint(1, 6)
    return not ((attempts + 1) >= rnd_number)


def build_deck(include_demon: bool = True) -> List[str]:
    deck = ['A'] * 6 + ['Q'] * 6 + ['K'] * 6 + ['Joker'] * 2
    if include_demon:
        deck += ['Demon'] * 1
    return deck


def deal_round(num_players: int) -> Tuple[List[List[str]], str]:
    deck = build_deck(include_demon=True)
    real_card = random.choice(['A', 'Q', 'K'])

    hands: List[List[str]] = []
    for _ in range(num_players):
        hand: List[str] = []
        for _ in range(5):
            select_card = random.choice(deck)
            deck.remove(select_card)
            if select_card == 'Joker':
                select_card = real_card
            hand.append(select_card)
        hands.append(hand)

    return hands, real_card


def normalize_card_token(token: str) -> Optional[str]:
    t = str(token).strip()
    if not t:
        return None
    up = t.upper()
    if up in ['A', 'Q', 'K']:
        return up
    if t in ['恶魔', '魔', 'D', 'DEMON', 'demon', 'Demon']:
        return 'Demon'
    return None


def parse_play_cards(text: str) -> Optional[List[str]]:
    raw = str(text).strip()
    if not raw:
        return []

    # 允许：AAK 或 A Q K 或 A,Q,K
    raw = raw.replace(',', ' ').replace('，', ' ')
    parts = [p for p in raw.split(' ') if p != '']

    tokens: List[str] = []
    if len(parts) == 1:
        # 可能是连写：AAK
        s = parts[0]
        # 如果包含“恶魔”，按整体处理
        if s in ['恶魔', '魔', 'DEMON', 'demon', 'Demon']:
            tokens = [s]
        else:
            tokens = list(s)
    else:
        tokens = parts

    cards: List[str] = []
    for tok in tokens:
        c = normalize_card_token(tok)
        if c is None:
            return None
        cards.append(c)
    return cards


def count_hand_text(hand: List[str]) -> str:
    a = hand.count('A')
    q = hand.count('Q')
    k = hand.count('K')
    d = hand.count('Demon')
    parts = []
    if a:
        parts.append(f"A x {a}")
    if q:
        parts.append(f"Q x {q}")
    if k:
        parts.append(f"K x {k}")
    if d:
        parts.append(f"恶魔 x {d}")
    return ' / '.join(parts) if parts else '（空）'


def find_player(game: dict, seat_id: int) -> Optional[dict]:
    for p in game.get('players', []):
        if int(p.get('seat_id', -1)) == int(seat_id):
            return p
    return None


def find_player_by_user(game: dict, user_id: str) -> Optional[dict]:
    for p in game.get('players', []):
        if str(p.get('user_id')) == str(user_id):
            return p
    return None


def alive_seats(game: dict) -> List[int]:
    seats = []
    for p in game.get('players', []):
        if p.get('status') == 'active':
            seats.append(int(p.get('seat_id')))
    return sorted(seats)


def finished_count(game: dict) -> int:
    c = 0
    for p in game.get('players', []):
        if p.get('status') == 'active' and len(p.get('hand', [])) == 0:
            c += 1
    return c


def compute_next_turn_seat(game: dict, from_seat_id: int) -> Optional[int]:
    seats = alive_seats(game)
    if not seats:
        return None
    if int(from_seat_id) not in seats:
        return seats[0]

    idx = seats.index(int(from_seat_id))
    for step in range(1, len(seats) + 1):
        sid = seats[(idx + step) % len(seats)]
        p = find_player(game, sid)
        if not p:
            continue
        # 若该玩家牌已出完：仍可成为“行动位”用于质疑，但不能出牌。
        return sid
    return seats[0]


def real_card_text(card: str, dictStrCustom: dict) -> str:
    if card == 'A':
        return dictStrCustom.get('strLBCardA', 'A')
    if card == 'Q':
        return dictStrCustom.get('strLBCardQ', 'Q')
    if card == 'K':
        return dictStrCustom.get('strLBCardK', 'K')
    return str(card)


def seat_status_text(p: dict, dictStrCustom: dict) -> str:
    if p.get('status') != 'active':
        if p.get('status') == 'dead':
            return dictStrCustom.get('strLBSeatStatusDead', '淘汰')
        if p.get('status') == 'left':
            return dictStrCustom.get('strLBSeatStatusLeft', '离场')
        return str(p.get('status'))
    if len(p.get('hand', [])) == 0:
        return dictStrCustom.get('strLBSeatStatusFinished', '已出完牌')
    return dictStrCustom.get('strLBSeatStatusActive', '在局')


def qq_is_friend(plugin_event, user_id: str) -> bool:
    """仅 QQ 平台使用好友列表验证是否可私聊。"""
    try:
        if plugin_event.platform.get('platform') != 'qq':
            return True
    except Exception:
        return True

    try:
        friend_res = plugin_event.get_friend_list()
        if not isinstance(friend_res, dict):
            return False
        friend_items = friend_res.get('data')
        if not isinstance(friend_items, list):
            return False

        target = str(user_id)
        for u in friend_items:
            if not isinstance(u, dict):
                continue
            uid = u.get('id')
            if uid is None:
                continue
            if str(uid) == target:
                return True

        return False
    except Exception:
        return False


# ----------------------------
# 消息发送辅助（与其它插件风格一致）
# ----------------------------


def sendMsgByEvent(plugin_event, message, target_id, target_type, host_id=None):
    group_id = None
    user_id = None
    tmp_name = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]['strBotName']
    tmp_self_id = plugin_event.bot_info.id
    if target_type == 'private':
        user_id = target_id
    elif target_type == 'group':
        group_id = target_id
    OlivaDiceCore.crossHook.dictHookFunc['msgHook'](
        plugin_event,
        'send_%s' % target_type,
        {
            'name': tmp_name,
            'id': tmp_self_id
        },
        [host_id, group_id, user_id],
        str(message)
    )
    return OlivaDiceCore.msgReply.pluginSend(plugin_event, target_type, target_id, message, host_id=host_id)
