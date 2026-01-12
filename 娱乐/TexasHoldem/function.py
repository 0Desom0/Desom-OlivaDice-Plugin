# -*- encoding: utf-8 -*-

import os
import json
import random
import itertools
from typing import Dict, List, Optional, Tuple

import OlivaDiceCore
import OlivOS


# ----------------------------
# 数据持久化
# ----------------------------


def texas_default() -> dict:
    return {
        'version': 1,
        'state': 'idle',  # idle（空闲）| waiting（等待开局）| playing（游戏中）
        'base_stake': 1000,
        'bb': 10,
        'sb': 5,
        'players': [],  # 玩家列表（list[Player]）
        'join_order': [],  # 按加入顺序记录 seat_id（用于 quit/leave 兜底）
        'user_nicknames': {},  # 用户自定义昵称字典 {user_id: nickname}

        # 单手状态
        'hand_no': 0,
        'dealer_seat_id': None,  # 当前庄位 seat_id（跨手保留）
        'sb_seat_id': None,
        'bb_seat_id': None,

        'street': None,  # preflop|flop|turn|river|showdown
        'community_cards': [],
        'deck': [],

        'pot': 0,
        'dead_money': 0,  # 例如：leave/kick 罚没的剩余筹码

        'current_high': 0,  # 本街最高投入（当前需跟到的额度）
        'min_raise': 0,  # 最小加注增量（delta）

        'acting_seat_id': None,
        'need_action_seat_ids': [],

        'end_flag': False,
    }


def get_texas_data_path() -> str:
    texas_data_path = os.path.join('plugin', 'data', 'TexasHoldem')
    if not os.path.exists(texas_data_path):
        os.makedirs(texas_data_path)
    return texas_data_path


def get_redirected_bot_hash(bot_hash: str) -> str:
    """遵循 OlivaDiceCore 主从账号链接：从账号读写主账号目录。"""
    try:
        master = OlivaDiceCore.console.getMasterBotHash(bot_hash)
        if master:
            return str(master)
    except Exception:
        pass
    return bot_hash


def get_group_file_path(bot_hash: str, group_hash: str) -> str:
    texas_data_path = get_texas_data_path()
    bot_hash = get_redirected_bot_hash(bot_hash)
    bot_path = os.path.join(texas_data_path, bot_hash)
    if not os.path.exists(bot_path):
        os.makedirs(bot_path)
    return os.path.join(bot_path, f"{group_hash}.json")


def load_group_data(bot_hash: str, group_hash: str) -> dict:
    # 默认按“主从链接”后的 botHash 读取
    file_path = get_group_file_path(bot_hash, group_hash)
    default_data = texas_default()

    # 兜底：若当前 botHash 为从账号，且主账号目录里不存在，则尝试读取旧的从账号目录
    redirected_bot_hash = get_redirected_bot_hash(bot_hash)
    if redirected_bot_hash != bot_hash and not os.path.exists(file_path):
        texas_data_path = get_texas_data_path()
        legacy_bot_path = os.path.join(texas_data_path, bot_hash)
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


# ----------------------------
# 工具函数
# ----------------------------


def get_nickname(
    plugin_event,
    user_id: str,
    tmp_hagID: Optional[str] = None,
    fallback_prefix: str = '',
    bot_hash: Optional[str] = None,
    group_hash: Optional[str] = None,
) -> str:
    """
    获取用户昵称，优先级：文件中记录的昵称 -> 人物卡名称 -> QQ昵称
    """
    try:
        fallback_prefix = fallback_prefix or ''
        default_name = f"{fallback_prefix}{user_id}" if fallback_prefix else str(user_id)
        
        # 1. 优先尝试从文件中记录的昵称获取
        if bot_hash and group_hash:
            try:
                game_data = load_group_data(bot_hash, group_hash)
                user_nicknames = game_data.get('user_nicknames', {})
                if str(user_id) in user_nicknames:
                    stored_nickname = user_nicknames.get(str(user_id))
                    if stored_nickname and stored_nickname.strip():
                        return str(stored_nickname)
            except Exception:
                pass
        
        # 2. 其次使用人物卡名称
        tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(user_id, plugin_event.platform['platform'])
        tmp_pcName = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
        if tmp_pcName:
            return tmp_pcName

        # 3. QQ频道：若无人物卡名，则回退到人物卡hash
        if plugin_event.platform['platform'] == 'qqGuild':
            return f"{fallback_prefix}{tmp_pcHash}" if fallback_prefix else str(tmp_pcHash)

        # 4. 尝试从用户配置获取QQ昵称
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

        # 5. 尝试从平台API获取昵称
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


def set_user_nickname(bot_hash: str, group_hash: str, user_id: str, nickname: str) -> None:
    """
    在群组文件中设置用户自定义昵称
    """
    try:
        game_data = load_group_data(bot_hash, group_hash)
        if 'user_nicknames' not in game_data:
            game_data['user_nicknames'] = {}
        game_data['user_nicknames'][str(user_id)] = str(nickname)
        save_group_data(bot_hash, group_hash, game_data)
    except Exception:
        pass


def compute_blinds(base_stake: int) -> Tuple[int, int]:
    bb = int(base_stake * 0.01)
    sb = int(bb * 0.5)
    return bb, sb


def find_player(players: List[dict], seat_id: int) -> Optional[dict]:
    for p in players:
        if p.get('seat_id') == seat_id:
            return p
    return None


def list_seat_ids(players: List[dict], include_out: bool = False) -> List[int]:
    seat_ids = []
    for p in players:
        if not include_out and p.get('status') == 'out':
            continue
        seat_ids.append(int(p['seat_id']))
    return sorted(seat_ids)


def next_seat_in_order(seat_order: List[int], current: int) -> int:
    if not seat_order:
        raise ValueError('empty seat_order')
    if current not in seat_order:
        return seat_order[0]
    idx = seat_order.index(current)
    return seat_order[(idx + 1) % len(seat_order)]


def next_action_seat(game: dict, from_seat_id: int) -> Optional[int]:
    """获取下一个可行动的座位（仅限 active）。"""
    seat_order = list_seat_ids(game['players'], include_out=False)
    if not seat_order:
        return None
    cur = from_seat_id
    for _ in range(len(seat_order)):
        cur = next_seat_in_order(seat_order, cur)
        p = find_player(game['players'], cur)
        if p and p.get('status') == 'active':
            return cur
    return None


def active_in_hand(players: List[dict]) -> List[dict]:
    return [p for p in players if p.get('status') in ('active', 'allin', 'folded')]


def alive_players(players: List[dict]) -> List[dict]:
    return [p for p in players if p.get('status') != 'out']


def in_showdown_eligible(players: List[dict]) -> List[dict]:
    return [p for p in players if p.get('status') in ('active', 'allin')]


# ----------------------------
# 牌/牌型评估
# ----------------------------


RANKS = '23456789TJQKA'
SUITS = 'SHDC'
RANK_TO_VAL = {r: i + 2 for i, r in enumerate(RANKS)}
VAL_TO_RANK = {v: r for r, v in RANK_TO_VAL.items()}
SUIT_TO_ICON = {
    'S': '♠',
    'H': '♥️',
    'D': '♦️',
    'C': '♣️',
}


def new_deck() -> List[str]:
    return [s + r for s in SUITS for r in RANKS]


def shuffle_deck(deck: List[str]) -> None:
    random.shuffle(deck)


def card_to_text(card: str) -> str:
    suit = card[0]
    rank = card[1]
    rank_show = '10' if rank == 'T' else rank
    return f"[{SUIT_TO_ICON.get(suit, suit)}{rank_show}]"


def cards_to_text(cards: List[str]) -> str:
    return ' '.join(card_to_text(c) for c in cards)


def _rank_char_to_show(rank_char: str) -> str:
    if rank_char == 'T':
        return '10'
    return str(rank_char)


def _val_to_show(v: int) -> str:
    return _rank_char_to_show(VAL_TO_RANK.get(int(v), str(v)))


def format_best5_compact(category: int, tiebreak: Tuple[int, ...]) -> str:
    """把最佳 5 张牌格式化为紧凑点数串（不含花色），并按牌型规则排序。

    例如：
    - 三条 KKKQJ（而不是 KKKJQ）
    - 两对 AAQQK（大对在前）
    - 同花/高牌：按点数从大到小
    - 顺子/同花顺：按高张到低张（车轮顺子为 5432A）

    依赖 evaluate_5/evaluate_7 返回的 (category, tiebreak) 结构。
    """
    cat = int(category)
    tb = tuple(int(x) for x in tiebreak)

    vals: List[int]
    if cat in (9, 5):
        # 同花顺 / 顺子：tiebreak=(straight_high,)
        high = int(tb[0]) if tb else 0
        if high == 5:
            # 车轮顺子 A2345
            vals = [5, 4, 3, 2, 14]
        else:
            vals = [high, high - 1, high - 2, high - 3, high - 4]
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 8:
        # 四条：tiebreak=(quad, kicker)
        quad, kicker = tb
        vals = [quad, quad, quad, quad, kicker]
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 7:
        # 葫芦：tiebreak=(trip, pair)
        trip, pair = tb
        vals = [trip, trip, trip, pair, pair]
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 6:
        # 同花：tiebreak 为 5 张从大到小
        return ''.join(_val_to_show(v) for v in tb)

    if cat == 4:
        # 三条：tiebreak=(trip, k1, k2)
        trip = tb[0]
        kickers = list(tb[1:])
        vals = [trip, trip, trip] + kickers
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 3:
        # 两对：tiebreak=(pair_high, pair_low, kicker)
        ph, pl, kicker = tb
        vals = [ph, ph, pl, pl, kicker]
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 2:
        # 一对：tiebreak=(pair, k1, k2, k3)
        pair = tb[0]
        kickers = list(tb[1:])
        vals = [pair, pair] + kickers
        return ''.join(_val_to_show(v) for v in vals)

    if cat == 1:
        # 高牌：tiebreak 为 5 张从大到小
        return ''.join(_val_to_show(v) for v in tb)

    # 兜底
    return ''.join(_val_to_show(v) for v in tb)


def _card_rank_show(card: str) -> str:
    """把单张牌的点数统一为展示格式（T->10）。"""
    try:
        r = str(card)[1]
    except Exception:
        return ''
    return '10' if r == 'T' else str(r)


def _split_compact_ranks(compact: str) -> List[str]:
    """把紧凑点数串拆成点数 token 列表（支持 10）。"""
    s = str(compact or '')
    out: List[str] = []
    i = 0
    while i < len(s):
        if s.startswith('10', i):
            out.append('10')
            i += 2
        else:
            out.append(s[i])
            i += 1
    return out


def order_best5_by_compact(best5: List[str], compact: str) -> List[str]:
    """按 format_best5_compact 给出的点数顺序，对 best5 进行重排。
    说明：best5 本身包含正确的 5 张牌，但其顺序可能不符合展示规则。
    这里用 compact 的点数序列作为目标顺序，在 best5 中按点数逐个匹配取出。
    """
    try:
        tokens = _split_compact_ranks(compact)
        if not best5 or len(best5) != 5 or len(tokens) != 5:
            return list(best5) if best5 else []

        remaining = list(best5)
        ordered: List[str] = []
        for t in tokens:
            hit_idx = None
            for i, c in enumerate(remaining):
                if _card_rank_show(c) == t:
                    hit_idx = i
                    break
            if hit_idx is None:
                # 理论上不应发生；兜底返回原顺序
                return list(best5)
            ordered.append(remaining.pop(hit_idx))

        return ordered
    except Exception:
        return list(best5) if best5 else []


def hand_category_text(category: int) -> str:
    """把 evaluate_5/evaluate_7 的 category 转为可展示的牌型名。"""
    mapping = {
        9: '同花顺（Straight Flush）',
        8: '四条（Four of a Kind）',
        7: '葫芦（Full House）',
        6: '同花（Flush）',
        5: '顺子（Straight）',
        4: '三条（Three of a Kind）',
        3: '两对（Two Pair）',
        2: '一对（One Pair）',
        1: '高牌（High Card）',
    }
    return mapping.get(int(category), f'未知牌型({category})')


def _is_royal_flush(best5: List[str]) -> bool:
    """判断 best5 是否为皇家同花顺（10JQKA 且同花色）。"""
    if not best5 or len(best5) != 5:
        return False
    suits = [c[0] for c in best5 if isinstance(c, str) and len(c) >= 2]
    ranks = [c[1] for c in best5 if isinstance(c, str) and len(c) >= 2]
    if len(suits) != 5 or len(ranks) != 5:
        return False
    if len(set(suits)) != 1:
        return False
    return set(ranks) == set(['T', 'J', 'Q', 'K', 'A'])


def hand_type_text(category: int, best5: Optional[List[str]] = None) -> str:
    """把牌型 category（必要）+ best5（可选）转为展示文本。

    用于在同花顺中区分“皇家同花顺”。
    """
    cat = int(category)
    if cat == 9 and best5 and _is_royal_flush(list(best5)):
        return '皇家同花顺（Royal Flush）'
    return hand_category_text(cat)


def _is_straight(values_desc: List[int]) -> Optional[int]:
    """判断是否顺子；若是则返回顺子的高牌点数，否则返回 None。

    values_desc 必须为去重后的降序点数列表。
    """
    if len(values_desc) < 5:
        return None
    vals = values_desc
    # 车轮顺子
    if set([14, 5, 4, 3, 2]).issubset(set(vals)):
        return 5

    # 普通顺子
    for i in range(len(vals) - 4):
        window = vals[i:i + 5]
        if window[0] - window[4] == 4 and len(window) == 5:
            return window[0]
    return None


def evaluate_5(cards5: List[str]) -> Tuple[int, Tuple[int, ...]]:
    """评估 5 张牌。

    返回 (category, tiebreak_tuple)，越大越强。
    """
    vals = sorted([RANK_TO_VAL[c[1]] for c in cards5], reverse=True)
    suits = [c[0] for c in cards5]
    is_flush = len(set(suits)) == 1

    unique_vals = sorted(set(vals), reverse=True)
    straight_high = _is_straight(unique_vals)

    # 点数计数
    count_map: Dict[int, int] = {}
    for v in vals:
        count_map[v] = count_map.get(v, 0) + 1
    counts = sorted(((cnt, v) for v, cnt in count_map.items()), reverse=True)
    # 计数结果按（数量降序，点数降序）排序

    if is_flush and straight_high is not None:
        # 同花顺
        return 9, (straight_high,)

    if counts[0][0] == 4:
        quad_val = counts[0][1]
        kicker = max(v for v in vals if v != quad_val)
        return 8, (quad_val, kicker)

    if counts[0][0] == 3 and len(counts) > 1 and counts[1][0] == 2:
        trip = counts[0][1]
        pair = counts[1][1]
        return 7, (trip, pair)

    if is_flush:
        return 6, tuple(sorted(vals, reverse=True))

    if straight_high is not None:
        return 5, (straight_high,)

    if counts[0][0] == 3:
        trip = counts[0][1]
        kickers = sorted([v for v in vals if v != trip], reverse=True)
        return 4, (trip, *kickers)

    if counts[0][0] == 2 and len(counts) > 1 and counts[1][0] == 2:
        pair_high = max(counts[0][1], counts[1][1])
        pair_low = min(counts[0][1], counts[1][1])
        kicker = max(v for v in vals if v not in (pair_high, pair_low))
        return 3, (pair_high, pair_low, kicker)

    if counts[0][0] == 2:
        pair = counts[0][1]
        kickers = sorted([v for v in vals if v != pair], reverse=True)
        return 2, (pair, *kickers)

    return 1, tuple(sorted(vals, reverse=True))


def evaluate_7(cards7: List[str]) -> Tuple[int, Tuple[int, ...], List[str]]:
    best = None
    best_cards = None
    for comb in itertools.combinations(cards7, 5):
        cat, tb = evaluate_5(list(comb))
        key = (cat, tb)
        if best is None or key > best:
            best = key
            best_cards = list(comb)
    assert best is not None and best_cards is not None
    return best[0], best[1], best_cards


# ----------------------------
# 位置/行动顺序
# ----------------------------


def compute_positions(game: dict) -> dict:
    """根据当前 dealer_seat_id 与在场玩家，计算 dealer/sb/bb/utg 的 seat_id。"""
    seats = list_seat_ids(game['players'], include_out=False)
    if len(seats) < 2:
        return {'dealer': None, 'sb': None, 'bb': None, 'utg': None}

    dealer = game.get('dealer_seat_id')
    if dealer not in seats:
        dealer = seats[0]
        game['dealer_seat_id'] = dealer

    if len(seats) == 2:
        sb = dealer
        bb = next_seat_in_order(seats, dealer)
        utg = sb  # 单挑：翻牌前先行动的是按钮位
    else:
        sb = next_seat_in_order(seats, dealer)
        bb = next_seat_in_order(seats, sb)
        utg = next_seat_in_order(seats, bb)

    return {'dealer': dealer, 'sb': sb, 'bb': bb, 'utg': utg}


def first_to_act_postflop(game: dict, dealer: int) -> Optional[int]:
    seats = list_seat_ids(game['players'], include_out=False)
    if len(seats) < 2:
        return None
    if len(seats) == 2:
        # 单挑：翻牌后由大盲位先行动（但必须仍为 active；否则跳过 allin/folded）
        cur = dealer
        for _ in range(len(seats)):
            cur = next_seat_in_order(seats, cur)
            p = find_player(game['players'], cur)
            if p and p.get('status') == 'active':
                return cur
        return None
    # 3+：从庄左开始找第一个可行动的玩家（跳过已弃牌/已全压/已出局）
    cur = dealer
    for _ in range(len(seats)):
        cur = next_seat_in_order(seats, cur)
        p = find_player(game['players'], cur)
        if p and p.get('status') == 'active':
            return cur
        if p and p.get('status') == 'allin':
            continue
        if p and p.get('status') == 'folded':
            continue
    return None


def role_name_for_seat(game: dict, seat_id: int) -> str:
    # 仅对“仍在场（未出局）”玩家分配位置；已出局座位返回空
    seats = list_seat_ids(game['players'], include_out=False)
    if seat_id not in seats:
        return ''

    pos = compute_positions(game)
    dealer = pos.get('dealer')
    if dealer is None or dealer not in seats:
        return ''

    # 按庄位开始的顺时针顺序排列
    order = [int(dealer)]
    cur = int(dealer)
    for _ in range(len(seats) - 1):
        cur = int(next_seat_in_order(seats, cur))
        order.append(cur)

    # 2-10 人局标准位置映射（相对庄位）
    role_codes_by_n = {
        2: ['BTN/D+SB', 'BB'],
        3: ['BTN/D', 'SB', 'BB'],
        4: ['BTN/D', 'SB', 'BB', 'UTG'],
        5: ['BTN/D', 'SB', 'BB', 'UTG', 'CO'],
        6: ['BTN/D', 'SB', 'BB', 'UTG', 'MP', 'CO'],
        7: ['BTN/D', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'CO'],
        8: ['BTN/D', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'HJ', 'CO'],
        9: ['BTN/D', 'SB', 'BB', 'UTG', 'UTG+1', 'UTG+2', 'MP', 'HJ', 'CO'],
        10: ['BTN/D', 'SB', 'BB', 'UTG', 'UTG+1', 'UTG+2', 'MP1', 'MP2', 'HJ', 'CO'],
    }
    codes = role_codes_by_n.get(len(order))
    if not codes:
        return ''

    seat_to_role = {order[i]: codes[i] for i in range(min(len(order), len(codes)))}
    return seat_to_role.get(int(seat_id), '')


# ----------------------------
# 牌局流程辅助
# ----------------------------


def reset_for_new_hand(game: dict) -> None:
    game['hand_no'] = int(game.get('hand_no', 0)) + 1
    game['street'] = 'preflop'
    game['community_cards'] = []
    game['deck'] = new_deck()
    shuffle_deck(game['deck'])
    game['pot'] = 0
    game['dead_money'] = 0
    game['current_high'] = 0
    game['min_raise'] = int(game.get('bb', 0))
    game['acting_seat_id'] = None
    game['need_action_seat_ids'] = []

    for p in game['players']:
        if p.get('chips', 0) <= 0:
            p['status'] = 'out'
            p['chips'] = 0
        else:
            p['status'] = 'active'
        p['current_bet'] = 0
        p['total_bet'] = 0
        p['hand_cards'] = []
        p['last_action'] = ''


def deal_hole_cards(game: dict) -> None:
    for p in game['players']:
        if p.get('status') != 'out':
            p['hand_cards'] = [game['deck'].pop(), game['deck'].pop()]


def post_blind(game: dict, seat_id: int, amount: int) -> int:
    p = find_player(game['players'], seat_id)
    if not p or p.get('status') == 'out':
        return 0
    pay = min(int(p.get('chips', 0)), int(amount))
    p['chips'] -= pay
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay
    if p['chips'] == 0:
        p['status'] = 'allin'
    return pay


def init_betting_round(game: dict, first_actor_seat_id: Optional[int]) -> None:
    game['acting_seat_id'] = first_actor_seat_id
    need = []
    for sid in list_seat_ids(game['players'], include_out=False):
        p = find_player(game['players'], int(sid))
        if p and p.get('status') == 'active':
            need.append(int(sid))
    game['need_action_seat_ids'] = need


def next_pending_actor(game: dict, from_seat_id: int) -> Optional[int]:
    """在 need_action_seat_ids 中寻找下一个仍为 active 的座位。"""
    need = set(int(x) for x in game.get('need_action_seat_ids', []))
    if not need:
        return None
    seat_order = list_seat_ids(game['players'], include_out=False)
    if not seat_order:
        return None
    cur = from_seat_id
    for _ in range(len(seat_order)):
        cur = next_seat_in_order(seat_order, cur)
        if cur in need:
            p = find_player(game['players'], cur)
            if p and p.get('status') == 'active':
                return cur
    return None


def start_hand(game: dict) -> dict:
    """把 game 推进到新的一手，并返回本手的位置信息（dealer/sb/bb/utg）。"""
    reset_for_new_hand(game)

    pos = compute_positions(game)
    game['dealer_seat_id'] = pos['dealer']
    game['sb_seat_id'] = pos['sb']
    game['bb_seat_id'] = pos['bb']

    deal_hole_cards(game)

    # 盲注
    sb_paid = post_blind(game, pos['sb'], int(game['sb']))
    bb_paid = post_blind(game, pos['bb'], int(game['bb']))

    # 本街最高投入初始化为大盲注额
    game['current_high'] = max(sb_paid, bb_paid)
    game['min_raise'] = int(game['bb'])

    # 翻牌前的第一个行动者
    if len(list_seat_ids(game['players'], include_out=False)) == 2:
        first_actor = pos['sb']
    else:
        first_actor = pos['utg']

    init_betting_round(game, first_actor)

    # 记录盲注动作文本（用于面板显示）
    sb_p = find_player(game['players'], pos['sb'])
    if sb_p:
        sb_p['last_action'] = f"SB {sb_paid}"
    bb_p = find_player(game['players'], pos['bb'])
    if bb_p:
        bb_p['last_action'] = f"BB {bb_paid}"

    return pos


def can_check(game: dict, seat_id: int) -> bool:
    p = find_player(game['players'], seat_id)
    if not p:
        return False
    return int(p.get('current_bet', 0)) == int(game.get('current_high', 0))


def apply_fold(game: dict, seat_id: int) -> None:
    p = find_player(game['players'], seat_id)
    if not p:
        return
    p['status'] = 'folded'
    p['last_action'] = 'fold'
    if seat_id in game['need_action_seat_ids']:
        game['need_action_seat_ids'].remove(seat_id)


def apply_call_or_check(game: dict, seat_id: int) -> Tuple[str, int]:
    p = find_player(game['players'], seat_id)
    if not p:
        return 'invalid', 0

    gap = int(game['current_high']) - int(p.get('current_bet', 0))
    if gap <= 0:
        p['last_action'] = 'check'
        if seat_id in game['need_action_seat_ids']:
            game['need_action_seat_ids'].remove(seat_id)
        return 'check', 0

    pay = min(int(p.get('chips', 0)), gap)
    p['chips'] -= pay
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay

    if p['chips'] == 0:
        p['status'] = 'allin'
        p['last_action'] = f"allin {pay}"
    else:
        p['last_action'] = f"call {pay}"

    if seat_id in game['need_action_seat_ids']:
        game['need_action_seat_ids'].remove(seat_id)

    return 'call', pay


def apply_bet(game: dict, seat_id: int, amount: int) -> Tuple[bool, str]:
    p = find_player(game['players'], seat_id)
    if not p or p.get('status') != 'active':
        return False, 'invalid'

    if int(game.get('current_high', 0)) != 0:
        return False, 'not_allowed'

    bb = int(game.get('bb', 0))
    if amount < bb:
        return False, 'too_small'

    pay = min(int(p.get('chips', 0)), int(amount))
    p['chips'] -= pay
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay

    new_high = int(p['current_bet'])
    game['current_high'] = new_high
    game['min_raise'] = max(bb, int(amount))

    if p['chips'] == 0:
        p['status'] = 'allin'
        p['last_action'] = f"allin {pay}"
    else:
        p['last_action'] = f"bet {pay}"

    # 重新设置其它玩家的待行动列表
    need = []
    for sid in list_seat_ids(game['players'], include_out=False):
        if int(sid) == int(seat_id):
            continue
        q = find_player(game['players'], int(sid))
        if q and q.get('status') == 'active':
            need.append(int(sid))
    game['need_action_seat_ids'] = need
    return True, 'ok'


def apply_raise(game: dict, seat_id: int, raise_delta: int) -> Tuple[bool, str, int]:
    p = find_player(game['players'], seat_id)
    if not p or p.get('status') != 'active':
        return False, 'invalid', 0

    gap = int(game['current_high']) - int(p.get('current_bet', 0))
    if gap < 0:
        gap = 0

    min_raise = int(game.get('min_raise', 0))
    if raise_delta < min_raise:
        return False, 'too_small', 0

    need_total = gap + int(raise_delta)
    pay = min(int(p.get('chips', 0)), need_total)

    p['chips'] -= pay
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay

    new_high = int(p['current_bet'])
    if new_high > int(game['current_high']):
        actual_delta = new_high - int(game['current_high'])
        game['current_high'] = new_high
        # 仅当满足“完整加注”时才更新最小加注阈值
        if actual_delta >= min_raise:
            game['min_raise'] = actual_delta
            # 重新设置其它玩家的待行动列表
            need = []
            for sid in list_seat_ids(game['players'], include_out=False):
                if int(sid) == int(seat_id):
                    continue
                q = find_player(game['players'], int(sid))
                if q and q.get('status') == 'active':
                    need.append(int(sid))
            game['need_action_seat_ids'] = need
        else:
            if seat_id in game['need_action_seat_ids']:
                game['need_action_seat_ids'].remove(seat_id)
    else:
        if seat_id in game['need_action_seat_ids']:
            game['need_action_seat_ids'].remove(seat_id)

    if p['chips'] == 0:
        p['status'] = 'allin'
        p['last_action'] = f"allin {pay}"
    else:
        p['last_action'] = f"raise {pay}"

    return True, 'ok', pay


def apply_allin(game: dict, seat_id: int) -> Tuple[bool, str, int]:
    p = find_player(game['players'], seat_id)
    if not p or p.get('status') != 'active':
        return False, 'invalid', 0

    pay = int(p.get('chips', 0))
    if pay <= 0:
        return False, 'invalid', 0

    gap = int(game['current_high']) - int(p.get('current_bet', 0))
    if gap < 0:
        gap = 0

    p['chips'] = 0
    p['current_bet'] += pay
    p['total_bet'] += pay
    game['pot'] += pay
    p['status'] = 'allin'

    new_high = int(p['current_bet'])
    if new_high > int(game['current_high']):
        actual_delta = new_high - int(game['current_high'])
        min_raise = int(game.get('min_raise', 0))
        game['current_high'] = new_high
        if actual_delta >= min_raise:
            game['min_raise'] = actual_delta
            need = []
            for sid in list_seat_ids(game['players'], include_out=False):
                if int(sid) == int(seat_id):
                    continue
                q = find_player(game['players'], int(sid))
                if q and q.get('status') == 'active':
                    need.append(int(sid))
            game['need_action_seat_ids'] = need
        else:
            if seat_id in game['need_action_seat_ids']:
                game['need_action_seat_ids'].remove(seat_id)
    else:
        if seat_id in game['need_action_seat_ids']:
            game['need_action_seat_ids'].remove(seat_id)

    p['last_action'] = f"allin {pay}"
    return True, 'ok', pay


def is_betting_round_over(game: dict) -> bool:
    # 若仅剩 1 名仍在争夺底池的玩家（active/allin），本手等同结束
    eligible = [p for p in game['players'] if p.get('status') in ('active', 'allin')]
    if len(eligible) <= 1:
        return True

    # 否则仅当本街所有需要行动的 active 都已行动，下注轮才结束
    return len(game.get('need_action_seat_ids', [])) == 0


def advance_street(game: dict) -> None:
    street = game.get('street')
    if street == 'preflop':
        # 翻牌
        game['community_cards'] += [game['deck'].pop(), game['deck'].pop(), game['deck'].pop()]
        game['street'] = 'flop'
    elif street == 'flop':
        game['community_cards'].append(game['deck'].pop())
        game['street'] = 'turn'
    elif street == 'turn':
        game['community_cards'].append(game['deck'].pop())
        game['street'] = 'river'
    elif street == 'river':
        game['street'] = 'showdown'

    # 重置本街下注
    for p in game['players']:
        p['current_bet'] = 0
        p['last_action'] = '' if p.get('status') == 'active' else p.get('last_action', '')

    game['current_high'] = 0
    game['min_raise'] = int(game.get('bb', 0))

    # 若本局 active 少于 2 人，则后续不会再产生有效下注（对手无法回应）。
    # 这种情况下不再初始化行动位，交给上层流程直接补齐公共牌到摊牌。
    active_cnt = len([p for p in game.get('players', []) if p.get('status') == 'active'])
    if active_cnt < 2:
        game['acting_seat_id'] = None
        game['need_action_seat_ids'] = []
        return

    # 初始化新一轮下注
    dealer = game.get('dealer_seat_id')
    first_actor = None
    if game['street'] in ('flop', 'turn', 'river'):
        if dealer is not None:
            first_actor = first_to_act_postflop(game, int(dealer))
    game['acting_seat_id'] = first_actor
    need = []
    for sid in list_seat_ids(game['players'], include_out=False):
        p = find_player(game['players'], int(sid))
        if p and p.get('status') == 'active':
            need.append(int(sid))
    game['need_action_seat_ids'] = need


def fast_forward_to_showdown(game: dict) -> None:
    """按正常发牌流程将公共牌补齐到摊牌（最多 5 张）。

    用于“提前弃牌/只剩一人”等场景：虽然无需继续行动，但结算展示仍希望
    公共牌完整到 5 张。
    """
    max_steps = 10
    steps = 0
    while steps < max_steps and game.get('street') != 'showdown':
        st = game.get('street')
        if st not in ('preflop', 'flop', 'turn', 'river'):
            break
        advance_street(game)
        steps += 1


def award_single_winner(game: dict, winner_seat_id: int) -> None:
    p = find_player(game['players'], winner_seat_id)
    if not p:
        return
    p['chips'] += int(game.get('pot', 0))
    game['pot'] = 0


def build_side_pots(players: List[dict], dead_money: int = 0) -> List[dict]:
    contrib = []
    for p in players:
        tb = int(p.get('total_bet', 0))
        if tb > 0:
            contrib.append((int(p['seat_id']), tb, p.get('status')))

    if not contrib:
        if dead_money > 0:
            # 仅有死钱：直接作为奖池，给仍在争夺底池的玩家竞争
            elig = [int(p['seat_id']) for p in players if p.get('status') in ('active', 'allin')]
            return [{'amount': dead_money, 'eligible_seat_ids': elig}]
        return []

    # 取所有不同的投入层级
    levels = sorted(set(tb for _, tb, _ in contrib))
    pots = []
    prev = 0
    for lvl in levels:
        delta = lvl - prev
        if delta <= 0:
            continue
        seats_in_layer = [sid for sid, tb, _ in contrib if tb >= lvl]
        amount = delta * len(seats_in_layer)
        elig = [sid for sid, tb, st in contrib if tb >= lvl and st in ('active', 'allin')]
        pots.append({'amount': amount, 'eligible_seat_ids': elig})
        prev = lvl

    # 把死钱合并进主池（第一个奖池）
    if dead_money > 0:
        if pots:
            pots[0]['amount'] += int(dead_money)
        else:
            elig = [int(p['seat_id']) for p in players if p.get('status') in ('active', 'allin')]
            pots.append({'amount': int(dead_money), 'eligible_seat_ids': elig})

    return pots


def settle_showdown(game: dict) -> dict:
    """进行摊牌结算并返回结算结果（用于渲染）。"""
    eligible = in_showdown_eligible(game['players'])
    board = list(game.get('community_cards', []))
    
    if len(eligible) == 1:
        winner = int(eligible[0]['seat_id'])
        pot_amount = int(game.get('pot', 0))
        award_single_winner(game, winner)
        
        # 即使只有一个人赢，也要返回showdown类型以显示详细结算
        # 构建eval_map，包含所有有手牌的玩家（包括已弃牌的）
        eval_map: Dict[int, Tuple[int, Tuple[int, ...], List[str]]] = {}
        for p in game['players']:
            if p.get('hand_cards') and p.get('status') != 'out' and not p.get('left'):
                sid = int(p['seat_id'])
                cards7 = board + list(p.get('hand_cards', []))
                eval_map[sid] = evaluate_7(cards7)
        
        # 构建单赢家的分配结果
        distribution = [{'pot': pot_amount, 'winners': [winner]}]
        
        return {
            'type': 'showdown',
            'distribution': distribution,
            'eval': {str(sid): {'cat': eval_map[sid][0], 'best5': eval_map[sid][2]} for sid in eval_map},
            'refunds': [],
            'single_winner': True,  # 标记这是单赢家情况
        }

    eval_map: Dict[int, Tuple[int, Tuple[int, ...], List[str]]] = {}
    for p in eligible:
        sid = int(p['seat_id'])
        cards7 = board + list(p.get('hand_cards', []))
        eval_map[sid] = evaluate_7(cards7)

    pots = build_side_pots(game['players'], int(game.get('dead_money', 0)))
    distribution = []
    refunds = []

    for pot in pots[::-1]:
        amt = int(pot['amount'])
        elig_sids = [sid for sid in pot['eligible_seat_ids'] if sid in eval_map]
        if not elig_sids or amt <= 0:
            continue
        best_key = None
        winners = []
        for sid in elig_sids:
            key = (eval_map[sid][0], eval_map[sid][1])
            if best_key is None or key > best_key:
                best_key = key
                winners = [sid]
            elif key == best_key:
                winners.append(sid)

        share = amt // len(winners)
        rem = amt % len(winners)

        # 若该奖池层只有 1 个 eligible，说明是未被跟注的超额投入（应退款而非展示边池）
        if len(elig_sids) == 1 and len(winners) == 1:
            sid_only = int(winners[0])
            find_player(game['players'], sid_only)['chips'] += int(amt)
            refunds.append({'seat_id': sid_only, 'amount': int(amt)})
            continue

        for sid in winners:
            find_player(game['players'], sid)['chips'] += share
        if rem > 0:
            # 余数给座位号最小的赢家（保证确定性）
            sid0 = sorted(winners)[0]
            find_player(game['players'], sid0)['chips'] += rem

        distribution.append({'pot': amt, 'winners': sorted(winners)})

    # 底池已完全分配
    game['pot'] = 0

    return {
        'type': 'showdown',
        'distribution': distribution[::-1],
        'eval': {str(sid): {'cat': eval_map[sid][0], 'best5': eval_map[sid][2]} for sid in eval_map},
        'refunds': refunds,
    }


def rotate_dealer(game: dict) -> None:
    seats = list_seat_ids(game['players'], include_out=False)
    if len(seats) < 2:
        return
    dealer = game.get('dealer_seat_id')
    if dealer not in seats:
        game['dealer_seat_id'] = seats[0]
        return
    game['dealer_seat_id'] = next_seat_in_order(seats, int(dealer))


def remove_broke_players(game: dict) -> List[int]:
    removed = []
    for p in game['players']:
        if int(p.get('chips', 0)) <= 0:
            if p.get('status') != 'out':
                p['status'] = 'out'
                removed.append(int(p['seat_id']))
    return removed


def compact_players(game: dict) -> None:
    """移除已出局（out）的玩家（可选使用）。"""
    game['players'] = [p for p in game['players'] if p.get('status') != 'out']


def check_auto_end(game: dict) -> Optional[int]:
    alive = [p for p in game['players'] if p.get('status') != 'out' and int(p.get('chips', 0)) > 0]
    if len(alive) == 1:
        return int(alive[0]['seat_id'])
    return None


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
# 字符串解析辅助函数
# ----------------------------


def getNumberPara(data, reverse=False):
    """
    从字符串中分离出数字和非数字部分。
    
    Args:
        data: 输入字符串
        reverse: False时从左往右找数字，True时从右往左找数字
        
    Returns:
        [非数字部分, 数字部分] (当reverse=False)
        或 [数字部分, 非数字部分] (当reverse=True)
    """
    tmp_output_str_1 = ''
    tmp_output_str_2 = ''
    if len(data) > 0:
        flag_have_para = False
        tmp_offset = 0
        tmp_total_offset = 0
        while True:
            tmp_offset += 1
            if reverse:
                tmp_total_offset = len(data) - tmp_offset
            else:
                tmp_total_offset = tmp_offset - 1
            if not reverse and tmp_total_offset >= len(data):
                flag_have_para = True
                break
            if reverse and tmp_total_offset < 0:
                tmp_total_offset = 0
                flag_have_para = True
                break
            if data[tmp_total_offset].isdecimal():
                pass
            else:
                flag_have_para = True
                if reverse:
                    tmp_total_offset += 1
                break
        if flag_have_para:
            tmp_output_str_1 = data[:tmp_total_offset]
            tmp_output_str_2 = data[tmp_total_offset:]
    return [tmp_output_str_1, tmp_output_str_2]


def getToNumberPara(data):
    """
    从字符串中找到第一个数字或空格的位置，并分割字符串。
    
    Args:
        data: 输入字符串
        
    Returns:
        [数字/空格之前的部分, 数字/空格及之后的部分]
    """
    tmp_output_str_1 = ''
    tmp_output_str_2 = ''
    if len(data) > 0:
        flag_have_para = False
        tmp_offset = 0
        tmp_total_offset = 0
        while True:
            tmp_offset += 1
            tmp_total_offset = tmp_offset - 1
            if tmp_total_offset >= len(data):
                flag_have_para = True
                break
            if data[tmp_total_offset].isdecimal():
                flag_have_para = True
                break
            if data[tmp_total_offset] == ' ':
                flag_have_para = True
                break

        if flag_have_para:
            tmp_output_str_1 = data[:tmp_total_offset]
            tmp_output_str_2 = data[tmp_total_offset:]
        else:
            tmp_output_str_2 = data
    return [tmp_output_str_1, tmp_output_str_2]


# ----------------------------
# 消息发送辅助
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