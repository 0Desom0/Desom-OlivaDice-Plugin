# -*- encoding: utf-8 -*-

import os
import json
import random
from typing import List, Optional, Tuple

import OlivaDiceCore
import OlivOS


# ----------------------------
# 数据默认结构与持久化
# ----------------------------


def blackjack_default() -> dict:
    return {
        'version': 1,
        'state': 'idle',
        'base_stake': 100,
        'min_stake': 10,
        'max_stake': 10000,
        'game_mode': 'open',  # open|hidden
        'players': [],
        'join_order': [],
        'dealer_seat_id': None,
        'round_no': 0,
        'dealer_cards': [],
        'deck': [],
        'user_nicknames': {},
    }


def get_blackjack_data_path() -> str:
    blackjack_data_path = os.path.join('plugin', 'data', 'BlackJack')
    if not os.path.exists(blackjack_data_path):
        os.makedirs(blackjack_data_path)
    return blackjack_data_path


def get_redirected_bot_hash(bot_hash: str) -> str:
    try:
        master = OlivaDiceCore.console.getMasterBotHash(bot_hash)
        if master:
            return str(master)
    except Exception:
        pass
    return bot_hash


def get_group_file_path(bot_hash: str, group_hash: str) -> str:
    path = get_blackjack_data_path()
    bot_hash = get_redirected_bot_hash(bot_hash)
    bot_path = os.path.join(path, bot_hash)
    if not os.path.exists(bot_path):
        os.makedirs(bot_path)
    return os.path.join(bot_path, f"{group_hash}.json")


def load_group_data(bot_hash: str, group_hash: str) -> dict:
    file_path = get_group_file_path(bot_hash, group_hash)
    default_data = blackjack_default()

    redirected = get_redirected_bot_hash(bot_hash)
    if redirected != bot_hash and not os.path.exists(file_path):
        legacy_path = os.path.join(get_blackjack_data_path(), bot_hash, f"{group_hash}.json")
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
# 用户数据（筹码）持久化
# ----------------------------


def get_user_dir() -> str:
    p = os.path.join('plugin', 'data', 'BlackJack', 'user')
    if not os.path.exists(p):
        os.makedirs(p)
    return p


def get_user_file_path(user_hash: str) -> str:
    return os.path.join(get_user_dir(), f"{user_hash}.json")


def load_user_data(user_hash: str) -> dict:
    fp = get_user_file_path(user_hash)
    if os.path.exists(fp):
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception:
            pass
    return {'default_chips': 1000}


def save_user_data(user_hash: str, data: dict) -> None:
    fp = get_user_file_path(user_hash)
    try:
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def update_user_chips(user_hash: str, current_chips: int) -> None:
    if current_chips < 10:
        data = {'default_chips': 1000}
    else:
        data = {'default_chips': int(current_chips)}
    save_user_data(user_hash, data)


def get_user_default_chips(user_hash: str) -> int:
    data = load_user_data(user_hash)
    try:
        v = int(data.get('default_chips', 1000))
        return v
    except Exception:
        return 1000


# ----------------------------
# 牌堆与牌处理
# ----------------------------


RANKS = '23456789TJQKA'
SUITS = 'SHDC'
SUIT_ICON = {'S': '♠', 'H': '♥️', 'D': '♦️', 'C': '♣️'}

# 21+3 赔率映射（可配置）
BJ_21_3_CONFIG = {
    'straight': 10,
    'flush': 5,
    'three_kind': 25,
    'straight_flush': 25,
    'flush_three': 50,
}

def normalize_21_3_type(t: str) -> Optional[str]:
    """将用户输入的 21+3 类型（中/英）规范化为内部 key"""
    if not t:
        return None
    s = str(t).strip().lower()
    map_table = {
        '顺': 'straight', 'straight': 'straight','顺子': 'straight',
        '同花': 'flush', 'flush': 'flush',
        '三条': 'three_kind', '三张': 'three_kind', 'three_kind': 'three_kind',
        '同花顺': 'straight_flush', 'straight_flush': 'straight_flush',
        '同花三条': 'flush_three', 'flush_three': 'flush_three',
    }
    return map_table.get(s, None)


def new_deck(num_decks: int = 4) -> List[str]:
    return [s + r for _ in range(num_decks) for s in SUITS for r in RANKS]


def shuffle_deck(deck: List[str]) -> None:
    random.shuffle(deck)


def card_to_text(card: str) -> str:
    try:
        suit = card[0]
        rank = card[1]
    except Exception:
        return ''
    rank_show = '10' if rank == 'T' else rank
    return f"[{SUIT_ICON.get(suit, suit)}{rank_show}]"


def cards_to_text(cards: List[str]) -> str:
    return ' '.join(card_to_text(c) for c in (cards or []))


def card_rank_value(card: str) -> int:
    try:
        r = card[1]
    except Exception:
        return 0
    if r == 'A':
        return 1
    if r == 'T':
        return 10
    if r in 'JQK':
        return {'J': 11, 'Q': 12, 'K': 13}.get(r, 10)
    try:
        return int(r)
    except Exception:
        return 0


def card_suit(card: str) -> str:
    try:
        return card[0]
    except Exception:
        return ''


# ----------------------------
# 点数计算与判定
# ----------------------------


def get_card_value(card: str, ace_as_eleven: bool = True) -> int:
    try:
        r = card[1]
    except Exception:
        return 0
    if r == 'A':
        return 11 if ace_as_eleven else 1
    if r in 'TJQK':
        return 10
    try:
        return int(r)
    except Exception:
        return 0


def calculate_hand_value(cards: List[str]) -> Tuple[int, int, int]:
    # 返回 (hand_value, soft_value, hard_value)
    hard = 0
    soft = 0
    aces = 0
    for c in (cards or []):
        try:
            r = c[1]
        except Exception:
            continue
        if r == 'A':
            aces += 1
            hard += 1
            soft += 11
        elif r in 'TJQK':
            hard += 10
            soft += 10
        else:
            try:
                v = int(r)
            except Exception:
                v = 0
            hard += v
            soft += v

    # 如果软点数超过21，则将A从11调整为1
    value = soft
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1

    # 计算硬点数：把所有 A 作为 1 计算
    hard_value = 0
    for c in (cards or []):
        try:
            r = c[1]
        except Exception:
            continue
        if r == 'A':
            hard_value += 1
        elif r in 'TJQK':
            hard_value += 10
        else:
            try:
                hard_value += int(r)
            except Exception:
                pass

    soft_value = soft
    return int(value), int(soft_value), int(hard_value)


def is_blackjack(cards: List[str]) -> bool:
    if not cards or len(cards) != 2:
        return False
    ranks = [c[1] for c in cards]
    return ('A' in ranks) and any(r in ranks for r in 'TJQK')


def is_bust(value: int) -> bool:
    try:
        return int(value) > 21
    except Exception:
        return False


# ----------------------------
# 游戏流程基础实现（简化版）
# ----------------------------


def reset_for_new_round(game: dict) -> None:
    game['round_no'] = int(game.get('round_no', 0)) + 1
    game['dealer_cards'] = []
    game['deck'] = new_deck()
    shuffle_deck(game['deck'])


def deal_card(game: dict, target: str, seat_id: int = None) -> Optional[str]:
    if not game.get('deck'):
        game['deck'] = new_deck()
        shuffle_deck(game['deck'])
    if not game.get('deck'):
        return None
    card = game['deck'].pop(0)
    if target == 'dealer':
        game.setdefault('dealer_cards', []).append(card)
    elif target == 'player' and seat_id is not None:
        p = find_player(game.get('players', []), seat_id)
        if p is None:
            return None
        p.setdefault('hand_cards', []).append(card)
    return card


def draw_from_deck(game: dict) -> Optional[str]:
    # 从牌堆抽一张牌，但不追加到任何玩家手牌中
    if not game.get('deck'):
        game['deck'] = new_deck()
        shuffle_deck(game['deck'])
    if not game.get('deck'):
        return None
    return game['deck'].pop(0)


def deal_initial_cards(game: dict) -> None:
    # 按文档顺序发牌：玩家1第一张...庄家第二张暗牌
    players = [p for p in game.get('players', []) if p.get('status') != 'out']
    seat_ids = [int(p['seat_id']) for p in players]
    # 每人发一张，两轮
    for _ in range(2):
        for sid in seat_ids:
            deal_card(game, 'player', sid)
        # 庄家
        deal_card(game, 'dealer')


def apply_hit(game: dict, seat_id: int) -> Tuple[bool, str]:
    p = find_player(game.get('players', []), seat_id)
    if not p:
        return False, 'seat_not_found'
    card = deal_card(game, 'player', seat_id)
    if not card:
        return False, 'no_card'
    v, sv, hv = calculate_hand_value(p.get('hand_cards', []))
    p['hand_value'] = v
    # 标记玩家已执行动作（用于限制双倍/投降等仅首次动作）
    p['acted'] = True
    if is_bust(v):
        p['status'] = 'bust'
        return True, 'bust'
    if v == 21:
        p['status'] = 'blackjack'
        return True, 'blackjack'
    return True, 'ok'


def apply_stand(game: dict, seat_id: int) -> Tuple[bool, str]:
    p = find_player(game.get('players', []), seat_id)
    if not p:
        return False, 'seat_not_found'
    p['status'] = 'stand'
    p['acted'] = True
    return True, 'stand'


def apply_double_down(game: dict, seat_id: int) -> Tuple[bool, str]:
    # 简化：不检查筹码，直接翻倍下注并发一张牌然后停牌
    p = find_player(game.get('players', []), seat_id)
    if not p:
        return False, 'seat_not_found'
    try:
        p['current_bet'] = int(p.get('current_bet', 0)) * 2
    except Exception:
        p['current_bet'] = int(p.get('current_bet', 0))
    # 抽取一张牌后自动停牌
    card = deal_card(game, 'player', seat_id)
    v, sv, hv = calculate_hand_value(p.get('hand_cards', []))
    p['hand_value'] = v
    p['status'] = 'stand' if not is_bust(v) else 'bust'
    p['acted'] = True
    return True, 'double'


def apply_split(game: dict, seat_id: int) -> Tuple[bool, str]:
    # 占位实现：如果手牌为两张且点数相同，则拆为两手
    p = find_player(game.get('players', []), seat_id)
    if not p:
        return False, 'seat_not_found'
    hc = p.get('hand_cards', [])
    if len(hc) != 2:
        return False, 'cannot_split'
    # 判断点数
    v1 = get_card_value(hc[0], ace_as_eleven=False)
    v2 = get_card_value(hc[1], ace_as_eleven=False)
    if v1 != v2:
        return False, 'cannot_split'
    # 创建两个手牌结构（不使用 deal_card，以免重复写入主手）
    p['is_split'] = True
    p['split_hands'] = [[hc[0]], [hc[1]]]
    # 每手再发一张（直接从牌堆抽取）
    for hand in p['split_hands']:
        card = draw_from_deck(game)
        if card:
            hand.append(card)
    # 将当前手牌设置为第一手用于后续动作
    p['hand_cards'] = p['split_hands'][0]
    p['acted'] = True
    return True, 'split'


def apply_surrender(game: dict, seat_id: int) -> Tuple[bool, str]:
    p = find_player(game.get('players', []), seat_id)
    if not p:
        return False, 'seat_not_found'
    p['status'] = 'out'
    refund = int(p.get('current_bet', 0)) // 2
    p['refund'] = refund
    p['acted'] = True
    return True, 'surrender'


def apply_insurance(game: dict, seat_id: int, amount: int) -> Tuple[bool, str]:
    p = find_player(game.get('players', []), seat_id)
    if not p:
        return False, 'seat_not_found'
    p['insurance_bet'] = int(amount)
    return True, 'insurance'


def check_21_3(dealer_first_card: str, player_first_two: List[str]) -> Tuple[bool, str, int]:
    cards = [dealer_first_card] + player_first_two
    # 检查同花三条（点数相同且同花）
    if is_three_kind_21_3(cards) and is_flush_21_3(cards):
        return True, 'flush_three', 50
    if is_straight_21_3(cards) and is_flush_21_3(cards):
        return True, 'straight_flush', 25
    if is_three_kind_21_3(cards):
        return True, 'three_kind', 25
    if is_flush_21_3(cards):
        return True, 'flush', 5
    if is_straight_21_3(cards):
        return True, 'straight', 10
    return False, '', 0


def is_straight_21_3(cards: List[str]) -> bool:
    vals = []
    for c in cards:
        v = card_rank_value(c)
        if v == 1:
            vals.append(1)
            vals.append(14)
        else:
            vals.append(v)
    # 需要检查王牌可能的所有取值组合
    # 暴力穷举：尝试所有 A 的取值组合
    from itertools import product
    ranks_options = []
    for c in cards:
        if c[1] == 'A':
            ranks_options.append([1, 14])
        else:
            ranks_options.append([card_rank_value(c)])
    for choice in product(*ranks_options):
        s = sorted(choice)
        if s[0] + 1 == s[1] and s[1] + 1 == s[2]:
            return True
    return False


def is_flush_21_3(cards: List[str]) -> bool:
    suits = [card_suit(c) for c in cards]
    return len(set(suits)) == 1


def is_three_kind_21_3(cards: List[str]) -> bool:
    ranks = [card_rank_value(c) for c in cards]
    return len(set(ranks)) == 1


# ----------------------------
# 庄家行动
# ----------------------------


def dealer_can_hit(game: dict) -> bool:
    d_cards = game.get('dealer_cards', [])
    v, sv, hv = calculate_hand_value(d_cards)
    # 庄家必须在 <17 要牌，软17 可选（不强制）
    if v < 17:
        return True
    return False


def dealer_play(game: dict) -> None:
    # 简化：自动要牌直到 >=17
    while dealer_can_hit(game):
        deal_card(game, 'dealer')


# ----------------------------
# 结算（简化实现）
# ----------------------------


def settle_insurance(game: dict) -> List[dict]:
    results = []
    dealer_cards = game.get('dealer_cards', [])
    dealer_blackjack = is_blackjack(dealer_cards[:2])
    for p in game.get('players', []):
        ins = int(p.get('insurance_bet', 0))
        if ins <= 0:
            continue
        if dealer_blackjack:
            payout = ins * 2
            results.append({'seat_id': p.get('seat_id'), 'insurance_bet': ins, 'won': True, 'payout': payout})
        else:
            results.append({'seat_id': p.get('seat_id'), 'insurance_bet': ins, 'won': False, 'payout': 0})
    return results


def settle_21_3(dealer_first_card: str, player_hand: List[str], bet_type: str, bet_amount: int) -> dict:
    matched, type_name, mult = check_21_3(dealer_first_card, player_hand[:2])
    if matched and type_name == bet_type:
        payout = int(bet_amount) * int(mult)
        return {'matched': True, 'type': type_name, 'multiplier': mult, 'payout': payout}
    return {'matched': False, 'type': '', 'multiplier': 0, 'payout': 0}


def settle_round(game: dict) -> dict:
    # 非完整结算，仅返回结构化结果供上层使用
    dealer_cards = game.get('dealer_cards', [])
    dealer_value, dsf, dhf = calculate_hand_value(dealer_cards)
    dealer_status = 'stand' if not is_bust(dealer_value) else 'bust'
    dealer_first = dealer_cards[0] if dealer_cards else None

    insurance_results = settle_insurance(game)

    results = []
    for p in game.get('players', []):
        # 处理分牌后的多手牌结算
        if p.get('is_split'):
            split_results = []
            total_payout = 0
            bet_per_hand = int(p.get('current_bet', 0))
            for hand in p.get('split_hands', []):
                hv, sv, hv2 = calculate_hand_value(hand)
                status = 'bust' if is_bust(hv) else ('blackjack' if is_blackjack(hand) else p.get('status', ''))
                res = 'lose'
                payout = 0
                if status == 'bust':
                    res = 'lose'
                elif status == 'blackjack':
                    if not is_blackjack(dealer_cards[:2]):
                        res = 'win'
                        payout = int(bet_per_hand * 1.5)
                    else:
                        res = 'push'
                else:
                    if is_bust(dealer_value):
                        res = 'win'
                        payout = bet_per_hand
                    else:
                        if hv > dealer_value:
                            res = 'win'
                            payout = bet_per_hand
                        elif hv < dealer_value:
                            res = 'lose'
                        else:
                            res = 'push'

                # 平局（push）应退还该手的主注
                if res == 'push':
                    total_payout += int(bet_per_hand)
                else:
                    total_payout += int(payout)

                # 同时为此分牌手判断 21+3（基于其前两张牌）
                try:
                    player_first_two = hand[:2]
                    res21 = settle_21_3(dealer_first, hand, p.get('bet_21_3_type'), int(p.get('bet_21_3', 0))) if int(p.get('bet_21_3', 0)) > 0 else {'matched': False, 'payout': 0}
                except Exception:
                    res21 = {'matched': False, 'payout': 0}
                if res21.get('matched'):
                    total_payout += int(res21.get('payout', 0))

                split_results.append({'hand_cards': hand, 'hand_value': hv, 'status': status, 'result': res, 'payout': payout, '21_3_result': res21})

            # 更新筹码：假设主注在下注/分牌时已被扣除
            try:
                cur_chips = int(p.get('chips', 0))
            except Exception:
                cur_chips = 0
            cur_chips += int(total_payout)
            p['chips'] = cur_chips

            results.append({
                'seat_id': p.get('seat_id'),
                'is_split': True,
                'split_results': split_results,
                'bet_per_hand': bet_per_hand,
                'total_payout': total_payout,
                'bet_21_3': int(p.get('bet_21_3', 0)),
                'bet_21_3_type': p.get('bet_21_3_type'),
            })
        else:
            hand = p.get('hand_cards', [])
            hv, sv, hv2 = calculate_hand_value(hand)
            status = p.get('status', '')
            bet = int(p.get('current_bet', 0))
            res = 'lose'
            payout = 0
            if status == 'bust':
                res = 'lose'
            elif status == 'blackjack':
                if not is_blackjack(dealer_cards[:2]):
                    res = 'win'
                    payout = int(bet * 1.5)
                else:
                    res = 'push'
            else:
                if is_bust(dealer_value):
                    res = 'win'
                    payout = bet
                else:
                    if hv > dealer_value:
                        res = 'win'
                        payout = bet
                    elif hv < dealer_value:
                        res = 'lose'
                    else:
                        res = 'push'

            # 21+3
            bet_21 = int(p.get('bet_21_3', 0))
            bet_21_type = p.get('bet_21_3_type')
            res_21 = settle_21_3(dealer_first, hand, bet_21_type, bet_21) if bet_21 and bet_21_type else {'matched': False, 'payout': 0}

            # 应用筹码变化：假设主注在下注时已扣除
            try:
                cur_chips = int(p.get('chips', 0))
            except Exception:
                cur_chips = 0
            if res == 'push':
                cur_chips += int(bet)
            else:
                cur_chips += int(payout)
            p['chips'] = cur_chips

            results.append({
                'seat_id': p.get('seat_id'),
                'hand_cards': hand,
                'hand_value': hv,
                'status': status,
                'bet': bet,
                'result': res,
                'payout': payout,
                'bet_21_3': bet_21,
                'bet_21_3_type': bet_21_type,
                '21_3_result': res_21,
            })

    # 将保险赔付计入玩家筹码
    try:
        for ins in insurance_results:
            sid = ins.get('seat_id')
            payout = int(ins.get('payout', 0))
            for p in game.get('players', []):
                if int(p.get('seat_id')) == int(sid):
                    try:
                        p['chips'] = int(p.get('chips', 0)) + int(payout)
                    except Exception:
                        pass
                    break
    except Exception:
        pass

    # 更新玩家数据文件（default_chips）
    for p in game.get('players', []):
        try:
            user_hash = str(p.get('user_id'))
            update_user_chips(user_hash, int(p.get('chips', 0)))
        except Exception:
            pass

    return {
        'type': 'round_end',
        'dealer_cards': dealer_cards,
        'dealer_value': dealer_value,
        'dealer_status': dealer_status,
        'dealer_first_card': dealer_first,
        'insurance_results': insurance_results,
        'results': results,
        'refunds': [],
    }


# ----------------------------
# 工具函数
# ----------------------------


def find_player(players: List[dict], seat_id: int) -> Optional[dict]:
    for p in (players or []):
        try:
            if int(p.get('seat_id')) == int(seat_id):
                return p
        except Exception:
            continue
    return None


def get_nickname(
    plugin_event,
    user_id: str,
    tmp_hagID: Optional[str] = None,
    fallback_prefix: str = '',
    bot_hash: Optional[str] = None,
    group_hash: Optional[str] = None,
) -> str:
    try:
        return OlivaDiceCore.userConfig.getUserConfigByKey(
            userId=user_id,
            userType='user',
            platform=plugin_event.platform['platform'],
            userConfigKey='userName',
            botHash=plugin_event.bot_info.hash,
            default=str(user_id),
        )
    except Exception:
        return str(user_id)


def set_user_nickname(bot_hash: str, group_hash: str, user_id: str, nickname: str) -> None:
    try:
        game_data = load_group_data(bot_hash, group_hash)
        if 'user_nicknames' not in game_data:
            game_data['user_nicknames'] = {}
        game_data['user_nicknames'][str(user_id)] = str(nickname)
        save_group_data(bot_hash, group_hash, game_data)
    except Exception:
        pass


def qq_is_friend(plugin_event, user_id: str) -> bool:
    try:
        if plugin_event.platform['platform'].startswith('qq'):
            info = plugin_event.get_stranger_info(user_id)
            return bool(info.get('active'))
    except Exception:
        pass
    return False


def sendMsgByEvent(plugin_event, message, target_id, target_type, host_id=None):
    try:
        if target_type == 'group':
            return OlivOS.messageAPI.send_group_msg(target_id, message)
        else:
            return OlivOS.messageAPI.send_private_msg(target_id, message)
    except Exception:
        try:
            OlivOS.messageAPI.send_private_msg(target_id, message)
        except Exception:
            pass
    return None
