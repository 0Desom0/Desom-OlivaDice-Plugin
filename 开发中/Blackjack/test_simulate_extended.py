#!/usr/bin/env python3
"""
扩展的端到端模拟测试：验证 21+3 类型、保险、双倍与分牌结算。
"""
import sys, os, importlib.util, types

# minimal shims
sys.modules['OlivaDiceCore'] = types.ModuleType('OlivaDiceCore')
sys.modules['OlivOS'] = types.ModuleType('OlivOS')

this_dir = os.path.dirname(__file__)
func_path = os.path.join(this_dir, 'function.py')
spec = importlib.util.spec_from_file_location('bjfunc', func_path)
bj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bj)

def test_settle_21_3_cases():
    print('== 21+3 直接判定测试 ==')
    dealer = 'SA'  # S A
    # 三种手牌示例（构造以匹配不同牌型）
    hands = {
        'straight': ['H2', 'D3',],
        'flush': ['H2', 'H5'],
        'three_kind': ['D6', 'S6'],
        'straight_flush': ['HQ', 'HJ'],
        'flush_three': ['C9', 'CA'],
    }
    for k, v in hands.items():
        matched, type_name, mult = bj.check_21_3(dealer, v)
        print(k, '=> matched:', matched, 'type:', type_name, 'mult:', mult)

def test_insurance_scenario():
    print('\n== 保险场景测试 ==')
    game = bj.blackjack_default()
    game['players'] = [{'seat_id':1,'user_id':'u1','nickname':'A','chips':500,'current_bet':100,'hand_cards':['H9','D7'],'status':'active', 'insurance_bet':50}]
    game['dealer_cards'] = ['SA','S9']
    # 结算保险
    ins = bj.settle_insurance(game)
    print('insurance results:', ins)

def test_double_and_settle():
    print('\n== 双倍与结算测试 ==')
    game = bj.blackjack_default()
    # 固定牌堆：确保玩家在 double 后手牌确定
    game['deck'] = ['D6','H9','H3','SK','H6','D5','S2'] + bj.new_deck()
    p1 = {'seat_id':1,'user_id':'u1','nickname':'A','chips':1000,'current_bet':100,'hand_cards':[],'status':'active'}
    game['players'] = [p1]
    bj.reset_for_new_round(game)
    # 手动发牌
    bj.deal_initial_cards(game)
    # 玩家 double（手动扣款）
    p1['chips'] -= 100
    bj.apply_double_down(game, 1)
    bj.dealer_play(game)
    res = bj.settle_round(game)
    print('settle result:', res['results'])

def test_split_scenario():
    print('\n== 分牌场景测试 ==')
    game = bj.blackjack_default()
    # 制造两张相同点数牌给玩家
    p = {'seat_id':1,'user_id':'u1','nickname':'A','chips':1000,'current_bet':100,'hand_cards':['D8','H8'],'status':'active'}
    game['players'] = [p]
    game['deck'] = ['C5','D2','S3','H4'] + bj.new_deck()
    # 执行分牌并扣款
    ok, reason = bj.apply_split(game, 1)
    if ok:
        p['chips'] -= 100
        # 模拟玩家两手停牌
        p['status'] = 'stand'
        bj.dealer_play(game)
        res = bj.settle_round(game)
        print('split settle:', res['results'])
    else:
        print('split failed:', reason)

if __name__ == '__main__':
    test_settle_21_3_cases()
    test_insurance_scenario()
    test_double_and_settle()
    test_split_scenario()
