#!/usr/bin/env python3
"""
Simple simulation to exercise core Blackjack functions without messaging layer.
"""
import sys
import os
import importlib.util
import types

# 为离线模拟提供最小的 OlivaDiceCore / OlivOS 模块替身，使得可以独立导入 function.py
sys.modules['OlivaDiceCore'] = types.ModuleType('OlivaDiceCore')
sys.modules['OlivOS'] = types.ModuleType('OlivOS')

this_dir = os.path.dirname(__file__)
func_path = os.path.join(this_dir, 'function.py')
spec = importlib.util.spec_from_file_location('bjfunc', func_path)
bj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bj)

def simple_run():
    bot, group = 'testbot', 'testgroup'
    game = bj.blackjack_default()
    game['base_stake'] = 100
    # 添加两个玩家用于模拟
    p1 = {'seat_id':1,'user_id':'u1','nickname':'A','chips':1000,'current_bet':0,'hand_cards':[],'status':'active'}
    p2 = {'seat_id':2,'user_id':'u2','nickname':'B','chips':1000,'current_bet':0,'hand_cards':[],'status':'active'}
    game['players'] = [p1,p2]
    bj.reset_for_new_round(game)
    bj.deal_initial_cards(game)
    # 玩家进行下注
    p1['current_bet']=100; p1['chips']-=100
    p2['current_bet']=100; p2['chips']-=100
    # 若可能，模拟玩家1执行双倍操作
    if len(p1['hand_cards'])==2 and p1['chips']>=p1['current_bet']:
        p1['chips']-=p1['current_bet']
        bj.apply_double_down(game, 1)
    # 庄家执行要牌逻辑
    bj.dealer_play(game)
    res = bj.settle_round(game)
    print('Dealer:', bj.cards_to_text(game.get('dealer_cards',[])))
    for r in res['results']:
        print(r)

if __name__ == '__main__':
    simple_run()
