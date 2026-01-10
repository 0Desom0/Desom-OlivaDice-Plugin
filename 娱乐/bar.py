from nonebot.adapters.onebot.v11 import MessageSegment, Message
from nonebot.adapters.onebot.v11 import GROUP, PRIVATE
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, PrivateMessageEvent
from nonebot import on_command, on_fullmatch, get_bots
from nonebot.params import CommandArg
from nonebot.log import logger

#导入定时任务库
from nonebot import require
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

#加载文件操作系统
import json
#加载读取系统时间相关
import datetime
import math
#加载数学算法相关
import random
import time
#加载KID档案信息
from .kidjd import *
from .config import *
from .list1 import *
from .list2 import *
from .list3 import *
#加载商店信息和商店交互
from .collection import collections
from .function import *
from .event import *
from .pvp import *
from .whitelist import whitelist_rule

__all__ = [
    "rule",
    "guess",
    "demon_default"
]

user_path = Path() / "data" / "UserList" / "UserData.json"
bar_path = Path() / "data" / "UserList" / "bar.json"
demon_path = Path() / "data" / "UserList" / "demon.json"
#酒馆游戏的规则
rule = on_command('rule', permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@rule.handle()
async def rule_handle(bot: Bot, event: GroupMessageEvent, arg: Message = CommandArg()):
    game_type = str(arg) #获取玩家玩的是哪一个游戏
    if game_type == '1':
        await rule.finish("游戏1：骗子纸牌(4人)\n"+
                          "游戏开始时系统会为每人的左轮里装入一发实弹，会随机在第1~6发中，赌命。\n"+
                          "一旦自己被实弹击中，则自己被淘汰。反之若仅自己存活到最后，则自己获得胜利。\n"+
                          "每轮开始时会从QKA中指定一张牌为真牌，每人将随机获得5张牌，然后所有人将按照顺序随意出牌，但每回合最多出3张。\n"+
                          "初始牌堆包含： Q × 6， K × 6， A × 6， Joker × 2，其中Joker牌将在每轮开始前自动变为本局真牌\n"+
                          "所有人出牌除非受到质疑，牌是不会亮出给任何人看的，大可吹牛，但你的下家可以质疑你。\n"+
                          "如果你出的牌中包含非真牌，则认定为下家质疑成功，你需要朝自己开一枪，反之则下家朝自己开一枪。\n"+
                          "当仅剩你没出完牌时，你将无法出牌，只能质疑上家。\n"+
                          "这场游戏的赢家只会有1个，祝你好运吧~\n"+
                          "输入/play 1游玩此游戏\n"+
                          "--------------\n"+
                          "竞猜模式：\n"+
                          "在每局游戏开始后，若你未参与本场游戏且场上此时剩余人数为4人，你将可以选择一名玩家进行竞猜。\n"+
                          "在游戏结束后，若你竞猜的玩家赢得了本场游戏胜利，所有竞猜本玩家的用户将瓜分竞猜其他玩家的刺儿。\n"+
                          "每场游戏你只能竞猜一个人。\n"+
                          "输入/竞猜 qq号/刺儿数量 进行竞猜", at_sender=False)
    elif game_type == '2':
        await rule.finish("游戏2：预言大师(1人)\n"+
                          "游戏开始时系统会为你从54张扑克牌中随机抽取一张，你要做的就是猜测这一张牌\n"+
                          "你的猜测将会是范围制的，你可以猜这张牌是否大于7？小于7？亦或是猜测这张牌的花色？\n"+
                          "如果猜对了，你将根据所猜范围的大小而获得不同程度的奖励，\n祝你好运吧~\n"+
                          "输入/play 2游玩此游戏", at_sender=False)
    elif game_type == '3':
        await rule.finish(
            "游戏3：恶魔轮盘du(2人)\n" +
            "本游戏入场费为125刺儿\n" +
            "游戏开始时，双方的血量在区间内随机（上限为6），并且都可以获得等量道具，然后由随机一人开始\n" +
            "在枪里面有不定量的子弹，实弹空弹随机\n" +
            "你可以向自己开枪，也可以向对方开枪，向自己开枪后无论是否实弹下一回合都是你行动\n" +
            "如果你向对方开枪，无论是否实弹都是对方行动\n" +
            "在回合内，每个人都可以使用道具，道具内容可以使用 /恶魔道具 查看\n" +
            "获胜的一方将获得350刺儿奖励~\n" +
            "使用 /恶魔帮助 指令可以查看所有的指令~ \n" +
            "输入 /play 3 游玩此游戏"
        )
    elif game_type == '4':
        await rule.finish(
            "游戏4：UNO - Color Chaos(4人)\n" +
            "游戏开始时，每人将会获得7张随机颜色，随机属性的牌\n" +
            "游戏开始时系统会随机指定一张牌为初始牌，下家只能出与上家颜色相同或者属性相同的牌\n"+
            "当然，部分牌是可以指定颜色或者变成随机属性的牌。也有部分牌可以对你的下家造成或多或少的影响。\n"+
            "如果此时你无牌可出，你可以输入/跳过 来抽一张牌并跳过当前回合\n"+
            "当有人打完了手中的所有牌时，他将获得胜利。当抽牌堆没有可抽的牌时，剩余牌数最少的玩家将获得胜利。\n"+
            "输入 /play 4 游玩此游戏"
        )
    else:
        await rule.finish("请输入正确的游戏编号，例如/rule 1", at_sender=True)


#地下酒馆，玩游戏的判定
play = on_command('play', permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@play.handle()
async def play_handle(bot: Bot, event: GroupMessageEvent, arg: Message = CommandArg()):
    # 打开文件
    data = {}
    with open(user_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    user_id = event.get_user_id() #获取玩家id(qq号)
    lc = data[user_id]['lc'] #获取玩家猎场号
    game_type = str(arg) #获取玩家玩的是哪一个游戏
    group_id = str(event.group_id)
    nick_name = event.sender.nickname
    current_time = int(time.time())  # 当前时间戳
    '''
    1: Liar's bar be like.
    2: 猜扑克牌，非常的简单
    3: 恶魔轮盘赌
    4: UNO牌的改版
    '''
    
    if (lc != '-1'):
        await play.finish("你现在不在地下酒馆，无法进行游戏", at_sender=True)
    
    #判断该群是否为地下黑市
    group = event.group_id
    if group != 781029876:
        await play.finish("地下酒馆建立于黑市之中，只有来到了黑市才可进行游玩。黑市群群号请参见公告", at_sender=True)

    bar_data = {}
    with open(bar_path, 'r', encoding='utf-8') as f:
        bar_data = json.load(f)
    
    demon_data = open_data(demon_path)

    #如果该用户不在酒馆名单中，则先创建(注册)
    if not user_id in bar_data:
        bar_data[user_id] = {}
        bar_data[user_id]['status'] = 'nothing'

    if bar_data[user_id]['status'] != 'nothing':
        await play.finish("你已经在玩其他游戏了", at_sender=True)

    if game_type == '1':
        #验证是否可以发送私信
        try:
            response = await bot.send_private_msg(user_id = int(user_id), message = "发送私信功能检验中")
            message_id = response["message_id"]
            # 撤回消息
            await bot.delete_msg(message_id=message_id)
        except:
            await play.finish("请先添加bot为好友再开始游戏", at_sender=True)

        max_player = 4 #玩家上限数


        #判定是否是第一次运行此游戏
        if not 'game1' in bar_data:
            bar_data['game1'] = []
        try:
            start = bar_data['game1_start']
        except:
            start = False
        #判定是否满人 or 游戏已开始
        if (len(bar_data['game1']) == max_player) or start:
            await play.finish("这个游戏房间已经满了，请先等等吧。", at_sender=True)
        #判断是否有足够刺儿
        if not 'spike' in data[user_id]:
            data[user_id]['spike'] = 0
        
        if data[user_id]['spike'] < 100:
            await play.finish("你需要有至少100刺儿才能进来玩哦", at_sender=True)
        else:
            data[user_id]['spike'] -= 100
        
        #没满就将此玩家加入到房间列表中
        bar_data[user_id]['game']='1'
        bar_data[user_id]['status'] = 'playing'
        bar_data['game1'].append(str(user_id))
        player_index = bar_data['game1'].index(str(user_id))+1

        #再次判定是否满人
        if len(bar_data['game1']) == max_player:
            await play.send(f"加入成功！你的位置是{player_index}，满{max_player}人后将开始游戏", at_sender=True)
            await play.send(f"游戏开始了。如想提前强制结束请找管理员", at_sender=False)
            
            #先发牌
            deal_result = deal_card(bar_data, max_player)

            card_keep = deal_result[0]
            real_card = deal_result[1]

            bar_data['real_card'] = real_card
            bar_data['user_card'] = card_keep
            bar_data[user_id]['last_card']=[]
            bar_data['attempts']=[0] * max_player
            await play.send("发牌已完成，各自的牌组已私信至各位玩家，Joker牌已自动变更为本轮的真牌。未收到的玩家请向bot发送/看牌", at_sender=False)

            for i in range(max_player):
                #私信各个玩家各自的牌
                show_id = bar_data['game1'][i]
                index = bar_data['game1'].index(str(show_id))
                player_card = bar_data['user_card'][index]
                msg_text = "A × "+str(player_card.count('A'))+"\n"+"Q × "+str(player_card.count('Q'))+"\n"+"K × "+str(player_card.count('K'))
                await bot.send_private_msg(user_id = int(show_id), message = f"你的卡牌列表是：\n{msg_text}")
        else:
            #写入主数据表
            with open(user_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            with open(bar_path, 'w', encoding='utf-8') as f:
                json.dump(bar_data, f, indent=4)
            await play.finish(f"加入成功！你的位置是{player_index}，满{max_player}人后将开始游戏", at_sender=True)
        bar_data['guess'] = [0,0,0,0]
        bar_data['guess_all'] = 0
        bar_data['game1_start'] = True
        bar_data['max_player'] = max_player
        bar_data['current_player'] = 0 #存储为，当前该第{index}名玩家出牌
        
        #写入主数据表
        with open(user_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        with open(bar_path, 'w', encoding='utf-8') as f:
            json.dump(bar_data, f, indent=4)
        await play.finish(message = f"本场真牌为 {real_card}\n请"+MessageSegment.at(bar_data['game1'][0])+" 最先出牌\n私信bot输入/出牌 想要出的牌进行出牌，每次最多出3张牌，每张牌之间不要留空格。\n"+
                          "例如：\n/出牌 AAA √\n/出牌 A Q K ×", at_sender=False)
    
    if game_type == '2':
        if data[user_id]['spike'] < 50:
            await play.finish("你需要有至少50刺儿才能进来玩哦", at_sender=True)
        else:
            data[user_id]['spike'] -= 50

        #将玩家添加至二号房间
        bar_data[user_id]['game']='2'
        bar_data[user_id]['status'] = 'playing'

        

        #写入主数据表
        with open(user_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        with open(bar_path, 'w', encoding='utf-8') as f:
            json.dump(bar_data, f, indent=4)

        await play.finish("发牌已完成，请选择如下指令中的一条进行猜测。\n"+
                          "输入/猜测 大于7/小于7 以猜测该牌是否大于7/小于7\n"+
                          "输入/猜测 梅花/方块/黑桃/红桃 以猜测该牌的花色\n"+
                          "输入/猜测 (任意三个连续数字，用/分隔，如10/J/Q) 以猜测该牌是否在此范围内，\n两张王牌均不计作任何大于/小于7的点数，不可被范围猜测\n"+
                          "输入/猜测 王牌 以猜测该牌是否为王牌", at_sender=True)
            
    if game_type == '3':
        # 获取当前时间戳
        current_time = int(time.time())

        # 确保 'demon_data' 和 'group_id' 存在
        # 初始化 group_id 中的游戏数据
        if group_id not in demon_data:
            demon_data[group_id] = demon_default
            save_data(demon_path, demon_data)
        # 检查是否有冷却时间，如果没有设置，默认为 0
        demon_coldtime = demon_data[group_id].get('demon_coldtime', 0)

        # 检查全局冷却时间
        if current_time < demon_coldtime:
            remaining_time = demon_coldtime - current_time
            await play.finish(
                f"恶魔轮盘du处于冷却中，请晚点再来吧！剩余冷却时间：{remaining_time // 60}分钟{remaining_time % 60}秒。",
                at_sender=True
            )

        # 检查游戏是否已经开始，如果已经开始，禁止其他玩家加入
        if demon_data[group_id]['start']:
            await play.finish("游戏已开始，无法加入！")
        if data[user_id]['spike'] < 125:
            await play.finish("你需要有至少125刺儿才能进来玩哦", at_sender=True)
        else:
            data[user_id]['spike'] -= 125
        # 将玩家添加至“游戏”状态
        bar_data[user_id]['game'] = '2'
        bar_data[user_id]['status'] = 'demon'
        # 判断玩家是否为第一位或第二位加入
        if len(demon_data[group_id]['pl']) == 0:
            # 第一位玩家加入
            demon_data[group_id]['pl'].append(user_id)
            demon_data[group_id]['turn_start_time'] = current_time
            # 写入数据
            save_data(full_path, data)
            save_data(bar_path, bar_data)
            save_data(demon_path, demon_data)
            await play.finish(f"玩家 {nick_name} 加入游戏，等待第二位玩家加入。", at_sender=True)

        elif len(demon_data[group_id]['pl']) == 1:
            # 第二位玩家加入前检查是否已经加入
            if user_id in demon_data[group_id]['pl']:
                await play.finish(f"你已经加入了游戏，无需重复加入！", at_sender=True)
            # 第二位玩家加入，初始化游戏
            demon_data[group_id]['pl'].append(user_id)
            # 游戏开始标志
            demon_data[group_id]['start'] = True
            add_max = 0
            # 膀胱加成
            pangguang_add = 0
            # 获取两个玩家的身份状态
            player_ids = [str(demon_data[group_id]['pl'][i]) for i in range(2)]
            identity_status_list = [data.get(player_id, {}).get("identity_status", 0) for player_id in player_ids]

            # 如果两个玩家的身份状态不同
            if identity_status_list[0] != identity_status_list[1]:
                identity_found = random.choice(identity_status_list)  # 随机选择一个状态，50% 概率选择其中一个
            else:
                identity_found = identity_status_list[0]  # 如果两个状态相同，直接选择该状态
            # 更新身份状态
            demon_data[group_id]['identity'] = identity_found
            idt_len = len(item_dic2)
            if identity_found == 1:
                add_max = 2
                idt_len = 0
            elif identity_found in [2,999]:
                add_max = 2
                pangguang_add = 2
                idt_len = 0
            # 设置玩家血量，随机生成血量值(放在上面后面好改)
            hp = random.randint(3 + max(int(add_max*2-1), 0) + pangguang_add, 6+add_max*2 + pangguang_add)
            demon_data[group_id]['hp'] = [hp, hp]
            # 设定轮数
            demon_data[group_id]['game_turn'] = 1
            # 设定血量上限
            demon_data[group_id]['hp_max'] = 6 + add_max*2 + pangguang_add
            # 设定道具上限
            demon_data[group_id]['item_max'] = 6 + add_max + pangguang_add
            # 加载弹夹状态
            demon_data[group_id]['clip'] = load()
            # 设定无限叠加攻击默认值
            demon_data[group_id]['add_atk'] = False
            # 随机决定先手玩家
            demon_data[group_id]['turn_start_time'] = int(time.time())
            demon_data[group_id]['turn'] = random.randint(0, 1)
            # 随机生成道具并分配给两位玩家
            player0 = str(demon_data[group_id]['pl'][0])
            player1 = str(demon_data[group_id]['pl'][1])
            # 跑团状态指定第一个玩家先手，全局变量可随便改
            if int(player0) == kp_pl:
                demon_data[group_id]['turn'] = 0
            item_msg, demon_data = refersh_item(identity_found, group_id, demon_data)
            # 发送初始化消息
            msg = "恶魔轮盘du，开局!\n"
            msg += "- 本局模式："
            if identity_found == 1:
                msg += "身份模式"
            elif identity_found in [2,999]:
                msg += "急速模式"
            else:
                msg += "正常模式"
            msg += "\n\n"
            msg += item_msg
            msg += f"\n- 总弹数{str(len(demon_data[group_id]['clip']))}，实弹数{str(demon_data[group_id]['clip'].count(1))}\n"
            pid = demon_data[group_id]['pl'][demon_data[group_id]['turn']]
            msg += "- 当前是"+ MessageSegment.at(pid) + "的回合"
            save_data(full_path, data)
            save_data(bar_path, bar_data)
            save_data(demon_path, demon_data)
            await play.finish(msg)
        else:
            await play.finish("游戏已开始，无法再次加入！")
    if game_type == '4':
        #验证是否可以发送私信
        try:
            response = await bot.send_private_msg(user_id = int(user_id), message = "发送私信功能检验中")
            message_id = response["message_id"]
            # 撤回消息
            await bot.delete_msg(message_id=message_id)
        except:
            await play.finish("请先添加bot为好友再开始游戏", at_sender=True)

        max_player = 4 #玩家上限数


        #判定是否是第一次运行此游戏
        if not 'game4' in bar_data:
            bar_data['game4'] = []
        try:
            start = bar_data['game4_start']
        except:
            start = False
        #判定是否满人 or 游戏已开始
        if (len(bar_data['game4']) == max_player) or start:
            await play.finish("这个游戏房间已经满了，请先等等吧。", at_sender=True)
        
        #没满就将此玩家加入到房间列表中
        bar_data[user_id]['game']='4'
        bar_data[user_id]['status'] = 'playing'
        bar_data['game4'].append(str(user_id))
        player_index = bar_data['game4'].index(str(user_id))+1
        

        #再次判定是否满人
        if len(bar_data['game4']) == max_player:
            await play.send(f"加入成功！你的位置是{player_index}，满{max_player}人后将开始游戏", at_sender=True)
            await play.send(f"游戏开始了。如想提前强制结束请找管理员", at_sender=False)

            #先发牌
            deal_result = deal_card4(max_player)

            card_keep = deal_result[0]
            draw_card = deal_result[1]
            start_card = deal_result[2]

            bar_data['user_card4'] = card_keep #此变量存储所有玩家当前手里的牌
            bar_data['current_card4'] = start_card #此变量储存的是上一张被打出的牌
            bar_data['draw_card4'] = draw_card #此变量存储的是未被打出的牌堆
            await play.send("发牌已完成，各自的牌组已私信至各位玩家", at_sender=False)

            for i in range(max_player):
                #私信各个玩家各自的牌
                show_id = bar_data['game4'][i]
                index = bar_data['game4'].index(str(show_id))
                player_card = bar_data['user_card4'][index]
                y_card = []
                b_card = []
                p_card = []
                g_card = []
                u_card = []
                #规定有颜色的牌的排序
                sort_order = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, '冰冻': 10, '反转': 11, '铲子': 12}
                universal_order = {'扭蛋': 0, '电枪': 1, '香蕉': 2}
                for card in player_card:
                    if card[1] == '黄':
                        y_card.append(card[0])
                    elif card[1] == '蓝':
                        b_card.append(card[0])
                    elif card[1] == '紫':
                        p_card.append(card[0])
                    elif card[1] == '绿':
                        g_card.append(card[0])
                    elif card[1] == 'Any':
                        u_card.append(card[0])
                    else:
                        raise KeyError("Not a valid color")
                #对列表进行排序
                y_card = sorted(y_card, key=lambda x: sort_order.get(x, float('inf')))
                b_card = sorted(b_card, key=lambda x: sort_order.get(x, float('inf')))
                p_card = sorted(p_card, key=lambda x: sort_order.get(x, float('inf')))
                g_card = sorted(g_card, key=lambda x: sort_order.get(x, float('inf')))
                u_card = sorted(u_card, key=lambda x: universal_order.get(x, float('inf')))
                msg_text = (
                    "黄色: "+str(y_card)+"\n"+
                    "蓝色: "+str(b_card)+"\n"+
                    "紫色: "+str(p_card)+"\n"+
                    "绿色: "+str(g_card)+"\n"+
                    "任意牌: "+str(u_card)
                )
                await bot.send_private_msg(user_id = int(show_id), message = f"你的卡牌列表是：\n{msg_text}")
        else:
            #写入数据表
            with open(bar_path, 'w', encoding='utf-8') as f:
                json.dump(bar_data, f, indent=4)
            await play.finish(f"加入成功！你的位置是{player_index}，满{max_player}人后将开始游戏", at_sender=True)
        bar_data['guess'] = [0,0,0,0]
        bar_data['guess_all'] = 0
        bar_data['game1_start'] = True
        bar_data['max_player4'] = max_player
        bar_data['current_player4'] = 0 #存储为，当前该第{index}名玩家出牌
        
        #写入主数据表
        with open(bar_path, 'w', encoding='utf-8') as f:
            json.dump(bar_data, f, indent=4)
        await play.finish(message = f"请"+MessageSegment.at(bar_data['game4'][0])+" 最先出牌\n输入/出牌 想要出的牌进行出牌，每次仅能出1张牌\n"+
                          "出牌格式如下:\n"+
                          "/出牌 绿7  即可打出绿色的7\n"+
                          "/出牌 蓝冰枪  即可打出蓝色的冰枪\n"+
                          "/出牌 紫电枪  即可打出电枪，并规定其为紫色\n"+
                          "/出牌 扭蛋  即可打出扭蛋牌，并将其变为随机的数字牌\n"+
                          f"当前卡牌为:{start_card[1]}色的{start_card[0]}", at_sender=False)

    


playcard = on_command('出牌', permission=PRIVATE, priority=3, block=True)
@playcard.handle()
async def playcard_handle(bot: Bot, event: PrivateMessageEvent, arg: Message = CommandArg()):
    # 打开文件
    data = {}
    with open(user_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    user_id = event.get_user_id() #获取玩家id(qq号)
    lc = data[user_id]['lc'] #获取玩家猎场号

    bar_data = {}
    with open(bar_path, 'r', encoding='utf-8') as f:
        bar_data = json.load(f)
    
    try:
        player_in_game1 = bar_data["game1"]
    except:
        player_in_game1 = []
    
    try:
        max_player = bar_data['max_player']
    except:
        max_player = 1000
    
    #首先判断是否离开了酒馆
    if (lc != '-1'):
        await playcard.finish("你现在不在地下酒馆，无法进行游戏")
    
    #是否参与了游戏
    if str(user_id) not in player_in_game1:
        await playcard.finish("你似乎没有参与本场游戏呢~")
    
    #如果人数不足，则直接结束，无法出牌
    if len(player_in_game1) < max_player:
        await playcard.finish("游戏似乎没有开始呢~")
    
    #是否是自己出牌的轮次
    current_player = int(bar_data['current_player'])
    player_index = int(bar_data['game1'].index(str(user_id)))

    if current_player == player_index:
        card_play = str(arg).replace(" ", "")
        player_card = bar_data["user_card"][player_index]
        last_card = []
        #判定牌数
        if len(card_play)>3 or len(card_play)==0:
            await playcard.finish("请输入正确的牌数，单次出牌最多出3张")
        card_play = list(card_play)

        #若其余所有玩家都已经出完了所有牌，你将无法出牌
        all_cards = bar_data["user_card"]
        finished = 0
        for i in all_cards:
            if i == []:
                finished += 1
        if finished == max_player -1:
            await playcard.finish("其余所有玩家都已经出完牌了，你不能出牌了")

        #判定牌是否合法
        for card in card_play:
            try:
                card = card.upper()
            except:
                card = 'CARD'
            #输入是否合法
            if card not in ['Q', 'K', 'A']:
                await playcard.finish("请输入正确的牌")
            #是否持有此牌
            if card in player_card:
                player_card.remove(card)
                last_card.append(card)
            else:
                await playcard.finish(f"你没有足够的{card}")
        
        #出牌成功则写入文件
        bar_data['user_card'][player_index] = player_card
        bar_data['last_card'] = last_card

        msg_text = "A × "+str(player_card.count('A'))+"\n"+"Q × "+str(player_card.count('Q'))+"\n"+"K × "+str(player_card.count('K'))
        group_id = 781029876  # 群号
        cur_qq = int(bar_data['game1'][current_player])
        bar_data['last_player'] = bar_data['current_player']
        #转换到下一位玩家
        if bar_data['current_player'] == max_player-1:
            bar_data['current_player'] = 0
        else:
            bar_data['current_player'] += 1
        current_player = int(bar_data['current_player'])

        #如果下家卡牌为空，则顺延
        while bar_data["user_card"][current_player] == []:
            #转换到下一位玩家
            if bar_data['current_player'] == max_player-1:
                bar_data['current_player'] = 0
            else:
                bar_data['current_player'] += 1
            current_player = bar_data['current_player']

        current_player = int(bar_data['current_player'])
        next_qq = int(bar_data['game1'][current_player])
        num_of_cards = len(card_play)
        
        await bot.send_group_msg(
            group_id=group_id,
            message=MessageSegment.at(cur_qq) + f"已完成出牌，共计{num_of_cards}张。\n请" + MessageSegment.at(next_qq) + "选择出牌或质疑上家。\n群内输入/质疑 以质疑上家\n私信bot输入/出牌 想要出的牌进行出牌，每次最多出3张牌，每张牌之间不要留空格\n"+
            "例如：\n/出牌 AAA √\n/出牌 A Q K ×"
        )
        #写入主数据表
        with open(user_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        with open(bar_path, 'w', encoding='utf-8') as f:
            json.dump(bar_data, f, indent=4)
        await playcard.finish(f"出牌成功，现在你剩余：\n{msg_text}")
    else:
        await playcard.finish("还没轮到你出牌哦，先等等吧")

doubt = on_fullmatch('/质疑', permission=GROUP, priority=2, block=True, rule=whitelist_rule)
@doubt.handle()
async def doubt_handle(bot: Bot, event: GroupMessageEvent):
    # 打开文件
    data = {}
    with open(user_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    user_id = event.get_user_id() #获取玩家id(qq号)
    lc = data[user_id]['lc'] #获取玩家猎场号

    bar_data = {}
    with open(bar_path, 'r', encoding='utf-8') as f:
        bar_data = json.load(f)
    
    try:
        player_in_game1 = bar_data["game1"]
    except:
        player_in_game1 = []

    try:
        max_player = bar_data['max_player']
    except:
        max_player = 1000
    
    #首先判断是否离开了酒馆
    if (lc != '-1'):
        await doubt.finish("你现在不在地下酒馆，无法进行游戏")
    
    #是否参与了游戏
    if str(user_id) not in player_in_game1:
        await doubt.finish("你似乎没有参与本场游戏呢~")
    
    #如果人数不足，则直接结束，无法出牌
    if len(player_in_game1) < max_player:
        await doubt.finish("游戏似乎没有开始呢~")
    
    #是否是自己出牌的轮次
    current_player = int(bar_data['current_player'])
    player_index = int(bar_data['game1'].index(str(user_id)))

    if current_player == player_index:
        cur_qq = int(bar_data['game1'][current_player])
        #获取上一位玩家
        last_player = bar_data['last_player']

        last_qq = int(bar_data['game1'][last_player])
        #如果没有上家出牌，则无法质疑
        if (not "last_card" in bar_data):
            await doubt.finish("没有上家，因此你现在无法质疑。")
        if (len(bar_data["last_card"])==0):
            await doubt.finish("没有上家，因此你现在无法质疑。")
        
        await doubt.send(message="Liar!\n"+MessageSegment.at(cur_qq)+"质疑了他的上家"+MessageSegment.at(last_qq))
        last_card = bar_data['last_card']
        real_card = bar_data['real_card']
        #只要上家出的牌存在非真牌，则质疑成功
        for card in last_card:
            if card != real_card:
                await doubt.send(message=f"上家出的牌是{last_card}，真牌是 {real_card}\n"+MessageSegment.at(cur_qq)+"的质疑成功了！")
                success = True
                break
        else:
            await doubt.send(message=f"上家出的牌是{last_card}，真牌是 {real_card}\n"+MessageSegment.at(cur_qq)+"的质疑失败了！")
            success = False
        
        #裁决环节
        if success:
            hit_obj = last_player
        else:
            hit_obj = current_player
            
        attempts = bar_data['attempts'][hit_obj]
        hit = shot(attempts)
        bar_data['attempts'][hit_obj]+=1

        cur_qq = int(bar_data['game1'][hit_obj])

        #逃过一劫
        if hit:
            await doubt.send(message=MessageSegment.at(cur_qq)+"开了一枪，是空弹。即将洗牌开启新的一轮", at_sender=False)
        #在劫难逃
        else:
            max_player -=1
            await doubt.send(message=MessageSegment.at(cur_qq)+"开了一枪，是实弹，"+MessageSegment.at(cur_qq)+"被淘汰了！即将洗牌开启新的一轮", at_sender=False)
            #将被淘汰的玩家从列表里移除
            out_player_id = bar_data['game1'][hit_obj]
            bar_data[out_player_id]['status'] = 'nothing'
            bar_data['game1'].remove(out_player_id)
            del bar_data['attempts'][hit_obj]

            #竞猜列表也移除
            bar_data['guess_all'] += bar_data['guess'][hit_obj]
            del bar_data['guess'][hit_obj]
    
        #如果剩余玩家仅剩1人，游戏结束
        if max_player == 1:
            winner_id = bar_data['game1'][0]
            bar_data[winner_id]['status'] = 'nothing'
            bar_data['game1_start'] = False
            bar_data['game1'] = []

            #给赢家发刺儿
            spike = 350
            data[winner_id]['spike'] += spike

            #竞猜统计环节
            for user in data:
                try:
                    data[user]['spike'] += math.floor((data[user]['guess_point']/bar_data['guess'][0]) * bar_data['guess_all'] * 0.9)
                    data[user]["guess_user"] = "0"
                    guess_success = True
                except:
                    guess_success = False
            await doubt.send("本局竞猜奖励已发放，请自行通过/ck查看", at_sender=False)
            #写入主数据表
            with open(user_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            with open(bar_path, 'w', encoding='utf-8') as f:
                json.dump(bar_data, f, indent=4)
            await doubt.finish(message = "恭喜"+MessageSegment.at(winner_id)+f"赢得了本场游戏的胜利，获得{spike}刺儿！", at_sender=False)

        #反之则开启新一轮
        #先发牌
        deal_result = deal_card(bar_data, max_player)

        card_keep = deal_result[0]
        real_card = deal_result[1]

        bar_data['real_card'] = real_card
        bar_data['user_card'] = card_keep
        await play.send("发牌已完成，各自的牌组已私信至各位玩家，Joker牌已自动变更为本轮的真牌。未收到的玩家请向bot发送/看牌", at_sender=False)

        for i in range(max_player):
            #私信各个玩家各自的牌
            show_id = bar_data['game1'][i]
            index = bar_data['game1'].index(str(show_id))
            player_card = bar_data['user_card'][index]
            msg_text = "A × "+str(player_card.count('A'))+"\n"+"Q × "+str(player_card.count('Q'))+"\n"+"K × "+str(player_card.count('K'))
            await bot.send_private_msg(user_id = int(show_id), message = f"你的卡牌列表是：\n{msg_text}")
        
        #对于质疑后的新一轮，起始玩家将随机
        current_player = random.randint(1, max_player)-1

        bar_data['max_player'] = max_player
        bar_data['current_player'] = current_player
        bar_data['last_card'] = []
        #写入主数据表
        with open(user_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        with open(bar_path, 'w', encoding='utf-8') as f:
            json.dump(bar_data, f, indent=4)
        await doubt.finish(message = f"本场真牌为：{real_card}\n请"+MessageSegment.at(bar_data['game1'][current_player])+" 最先出牌\n私信bot输入/出牌 想要出的牌进行出牌，每次最多出3张牌，每张牌之间不要留空格。\n"+
                          "例如：\n/出牌 AAA √\n/出牌 A Q K ×", at_sender=False)

    else:
        await doubt.finish("还没轮到你质疑哦，先等等吧", at_sender=True)


playcard = on_command('看牌', permission=PRIVATE, priority=1, block=True)
@playcard.handle()
async def playcard_handle(bot: Bot, event: PrivateMessageEvent, arg: Message = CommandArg()):
    # 打开文件
    data = {}
    with open(user_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    user_id = event.get_user_id() #获取玩家id(qq号)
    lc = data[user_id]['lc'] #获取玩家猎场号

    bar_data = {}
    with open(bar_path, 'r', encoding='utf-8') as f:
        bar_data = json.load(f)

    try:
        player_in_game1 = bar_data["game1"]
    except:
        player_in_game1 = []
    
    try:
        max_player = bar_data['max_player']
    except:
        max_player = 1000
    
    #首先判断是否离开了酒馆
    if (lc != '-1'):
        await doubt.finish("你现在不在地下酒馆，无法进行游戏")
    
    #如果人数不足，则直接结束，无法出牌
    if len(player_in_game1) < max_player:
        await doubt.finish("游戏似乎没有开始呢~")
    
    player_index = int(bar_data['game1'].index(str(user_id)))
    player_card = bar_data['user_card'][player_index]
    real_card = bar_data["real_card"]
    msg_text = "A × "+str(player_card.count('A'))+"\n"+"Q × "+str(player_card.count('Q'))+"\n"+"K × "+str(player_card.count('K'))+f"\n本场真牌为 {real_card}"
    await playcard.finish(message = f"现在你剩余：\n{msg_text}")

guess = on_command('猜测', permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@guess.handle()
async def guess_handle(bot: Bot, event: GroupMessageEvent, arg: Message = CommandArg()):
    # 打开文件
    data = {}
    with open(user_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    user_id = event.get_user_id() #获取玩家id(qq号)
    lc = data[user_id]['lc'] #获取玩家猎场号

    bar_data = {}
    with open(bar_path, 'r', encoding='utf-8') as f:
        bar_data = json.load(f)

    #首先判断是否离开了酒馆
    if (lc != '-1'):
        await guess.finish("你现在不在地下酒馆，无法进行游戏")
    #再判断是否开始了游戏
    try:
        game_type = bar_data[user_id]['game']
        game_status = bar_data[user_id]['status']
        
    except:
        game_type = "-1"
        game_status = "-1"
    
    if  game_type == '2' and game_status =='playing':
        pass
    else:
        await guess.finish("你似乎没有参与本场游戏呢~")

    #选定抽到的牌
    card_collection = []
    for i in range(1,14):
        for _ in range(4):
            card_collection.append(i)
    card_collection.append(14)
    card_collection.append(15)
    card_value = random.choice(card_collection)
    card_type = random.choice(["梅花","方块","黑桃","红桃"])
    #对于特殊的数值，予以特殊的名字
    if card_value == 1:
        card_name = "A"
    elif card_value == 11:
        card_name = "J"
    elif card_value == 12:
        card_name = "Q"
    elif card_value == 13:
        card_name = "K"
    elif card_value == 14:
        card_type = "黑白"
        card_name = "Joker"
    elif card_value == 15:
        card_value = 14
        card_type = "彩色"
        card_name = "Joker"
    else:
        card_name = str(card_value)

    guess_type = str(arg).split("/")
    if len(guess_type) != 1 and len(guess_type) != 3:
        await guess.finish(message = "请输入一个正确的猜测值", at_sender=True)
    elif len(guess_type) == 1:
        guess_type = guess_type[0]
        if guess_type == "大于7":
            spike = 90
            if card_value > 7 and card_value < 14: #这里写小于14是为了判定王牌为负
                data[user_id]['spike'] += spike
                msg_text = f"你抽到的牌是{card_type}{card_name}，点数大于7，你的猜测成功了！获得{spike}刺儿奖励。"
            else:
                msg_text = f"你抽到的牌是{card_type}{card_name}，点数小于等于7，你的猜测失败了！"
        elif guess_type == "小于7":
            spike = 90
            if card_value < 7:
                data[user_id]['spike'] += spike
                msg_text = f"你抽到的牌是{card_type}{card_name}，点数小于7，你的猜测成功了！获得{spike}刺儿奖励。"
            else:
                msg_text = f"你抽到的牌是{card_type}{card_name}，点数大于等于7，你的猜测失败了！"
        elif guess_type in ["梅花","方块","黑桃","红桃"]:
            spike = 190
            if card_type == guess_type:
                data[user_id]['spike'] += spike
                msg_text = f"你抽到的牌是{card_type}{card_name}，你的猜测成功了！获得{spike}刺儿奖励。"
            else:
                msg_text = f"你抽到的牌是{card_type}{card_name}，你的猜测失败了！"
        elif guess_type == "王牌":
            spike = 1300
            if card_value >= 14:
                data[user_id]['spike'] += spike
                msg_text = f"你抽到的牌是{card_type}{card_name}，你的猜测成功了！获得{spike}刺儿奖励。"
            else:
                msg_text = f"你抽到的牌是{card_type}{card_name}，你的猜测失败了！"
        else:
            await guess.finish(message = "请输入一个正确的猜测值", at_sender=True)
    elif len(guess_type) == 3:
        spike = 210
        #处理特殊牌值
        available_type = ["a","2","3","4","5","6","7","8","9","10","j","q","k"]
        for i in range(len(guess_type)):
            if guess_type[i].lower() not in available_type:
                await guess.finish(message = "请输入一个正确的牌值", at_sender=True)
            if guess_type[i].lower() == "a":
                guess_type[i] = 1
            elif guess_type[i].lower() == "j":
                guess_type[i] = 11
            elif guess_type[i].lower() == "q":
                guess_type[i] = 12
            elif guess_type[i].lower() == "k":
                guess_type[i] = 13
            else:
                guess_type[i] = int(guess_type[i])
        if guess_type[0]+1==guess_type[1]==guess_type[2]-1:
            if card_value in guess_type:
                data[user_id]['spike'] += spike
                msg_text = f"你抽到的牌是{card_type}{card_name}，你的猜测成功了！获得410刺儿奖励。"
            else:
                msg_text = f"你抽到的牌是{card_type}{card_name}，你的猜测失败了！"
        else:
            await guess.finish(message = "你输入的三个数字不是连续数字，请重新输入", at_sender=True)


    #写入主数据表
    bar_data[user_id]['status'] = 'nothing'

    with open(user_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    with open(bar_path, 'w', encoding='utf-8') as f:
        json.dump(bar_data, f, indent=4)
    await guess.finish(message = msg_text, at_sender=True)

guess2 = on_command('竞猜', permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@guess2.handle()
async def guess2_handle(bot: Bot, event: GroupMessageEvent, arg: Message = CommandArg()):
    # 打开文件
    data = {}
    with open(user_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    user_id = event.get_user_id() #获取玩家id(qq号)
    lc = data[user_id]['lc'] #获取玩家猎场号

    bar_data = {}
    with open(bar_path, 'r', encoding='utf-8') as f:
        bar_data = json.load(f)
    
    #判断自己是否参与了游戏
    if user_id in bar_data['game1']:
        await guess2.finish("你参与了骗子纸牌游戏，不能竞猜哦~")

    try:
        start = bar_data['game1_start']
    except:
        start = False
    #判断是否开始
    if not start:
        await guess2.finish("骗子纸牌游戏似乎没有开始哦~", at_sender=True)

    #判断游戏人数
    if len(bar_data['game1'])!=4:
        await guess2.finish("本场游戏已经进行一段时间了，不能再竞猜了。")
    #判断竞猜对象
    if "guess_user" in data[user_id]:
        data[user_id]['guess_user'] = "0"
    if data[user_id]['guess_user'] != arg[0] and data[user_id]['guess_user'] != "0":
        await guess2.finish("你已经有竞猜对象，不能竞猜其他人了", at_sender=True)

    #判断是否离开了酒馆
    if (lc != '-1'):
        await guess2.finish("你现在不在地下酒馆，无法进行游戏")

    
    arg = str(arg).split("/")

    if arg[0] in bar_data['game1']:
        u_qq = arg[0]
    else:
        await guess2.finish("未找到该玩家信息", at_sender=True)

    try:
        spike_add = int(arg[1])
    except:
        await guess2.finish("请输入正确的刺儿数量", at_sender=True)

    if spike_add > data[user_id]["spike"]:
        await guess2.finish(f"你没有这么多刺儿，目前你只有{data[user_id]["spike"]}刺儿", at_sender=True)
    #初始化竞猜点数
    if not "guess" in bar_data:
        bar_data["guess"]=[0,0,0,0]
    if not "guess_point" in data[user_id]:
        data[user_id]["guess_point"] = 0
    
    u_index = int(bar_data['game1'].index(u_qq))
    bar_data["guess"][u_index] += spike_add
    data[user_id]["guess_point"] += spike_add
    data[user_id]["guess_user"] = "0"

    with open(user_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    with open(bar_path, 'w', encoding='utf-8') as f:
        json.dump(bar_data, f, indent=4)
    await guess2.finish("竞猜成功！你向"+MessageSegment.at(bar_data['game1'][u_index])+f"支持了{spike_add}刺儿，你现在一共向其投入了{data[user_id]["guess_point"]}刺儿", at_sender=True)

#这个是p4的群聊出牌
playcard4 = on_command('出牌', permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@playcard4.handle()
async def playcard4_handle(bot: Bot, event: GroupMessageEvent,  arg: Message = CommandArg()):
    # 打开文件
    user_id = event.get_user_id()
    bar_data = {}
    with open(bar_path, 'r', encoding='utf-8') as f:
        bar_data = json.load(f)
    
    try:
        player_in_game4 = bar_data["game4"]
    except:
        player_in_game4 = []
    
    try:
        max_player = bar_data['max_player4']
    except:
        max_player = 1000
    
    #是否参与了游戏
    if str(user_id) not in player_in_game4:
        await playcard4.finish("你似乎没有参与本场游戏呢~")
    
    #如果人数不足，则直接结束，无法出牌
    if len(player_in_game4) < max_player:
        await playcard4.finish("游戏似乎没有开始呢~")
    
    #是否是自己出牌的轮次
    current_player = int(bar_data['current_player4'])
    player_index = int(bar_data['game4'].index(str(user_id)))

    if current_player == player_index:
        card_play = str(arg).replace(" ", "")
        player_card = bar_data["user_card4"][player_index]
        last_card = bar_data["current_card4"]

        #判定牌是否合法
        #这个列表里的牌不受限制
        unlimit_card = ['扭蛋']
        #这个列表里存储变任意颜色可控的牌
        universal_card = ['电枪', '香蕉']

        

        #对所有不需要规定颜色的牌进行特殊的判定
        if card_play == '扭蛋':
            if ['扭蛋', 'Any'] in player_card:
                #player_card.remove(['扭蛋', 'Any'])
                rnd_color = random.choice(['黄','蓝','紫','绿'])
                rnd_number = str(random.randint(0,9))
                last_card = [rnd_number, rnd_color]
                card_play = ['扭蛋', 'Any']
            else:
                await playcard4.finish(f"你没有扭蛋牌")
        else:
            # 将输入格式转换为存储格式
            if card_play[0] not in ['黄','蓝','紫','绿']:
                await playcard4.finish("请输入一个合法的颜色(黄/蓝/紫/绿)")
            card_play = [card_play[1:], card_play[0]]
        

        #对任意牌进行处理
        if (card_play[0] in universal_card):
            if [card_play[0], 'Any'] in player_card:
                player_card.remove([card_play[0], 'Any'])
                last_card = card_play
            else:
                await playcard4.finish(f"你没有{card_play[0]}")
        #对扭蛋牌进行处理
        elif (card_play[0] in unlimit_card):
            if [card_play[0], 'Any'] in player_card:
                player_card.remove([card_play[0], 'Any'])
            else:
                await playcard4.finish(f"你没有{card_play[0]}")
        else:
            # 非任意牌则查询是否持有此牌
            if not card_play in player_card:
                await playcard4.finish(f"你没有{card_play[1]}色的{card_play[0]}")
        
        # 是否可出此牌
        # 判断是否是不受限制的牌/可变颜色的牌
        if card_play[0] not in universal_card and card_play[0] not in unlimit_card:
            #判断花色/种类是否都不符合
            if card_play[0] != last_card[0] and card_play[1] != last_card[1]:
                await playcard4.finish(f"你不能出这张牌，上一张牌是{last_card[1]}色的{last_card[0]}")
            player_card.remove(card_play)
            last_card = card_play
            
        
        #出牌成功则写入文件
        bar_data['user_card4'][player_index] = player_card
        bar_data['current_card4'] = last_card

        cur_qq = int(bar_data['game4'][current_player])

        #转换到下一位玩家
        current_player += 1
        current_player = current_player % max_player
        bar_data['current_player4'] = current_player

        #处理特殊道具牌的效果
        if card_play[0] == '冰枪':
            current_player += 1
        elif card_play[0] == '铲子':
            draw_list = bar_data['draw_card4']
            stop_color = card_play[1]
            current_color = ''
            card_get = 0
            for _ in range(2):
                bar_data['user_card4'][current_player].append(draw_list[0])
                current_color = draw_list[0][1]
                card_get += 1
                del draw_list[0]
                if len(draw_list) == 0:
                    break
            await playcard4.send(message = "恭喜"+MessageSegment.at(bar_data['game4'][current_player])+f"一共获得了2张牌！", at_sender=False)
            '''
            由于牌组变化，因此要给当前玩家发送消息
            '''
            y_card = []
            b_card = []
            p_card = []
            g_card = []
            u_card = []
            #规定有颜色的牌的排序
            sort_order = {'0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '冰枪': 10, '反转': 11, '铲子': 12}
            universal_order = {'扭蛋': 0, '电枪': 1, '香蕉': 2}
            curPlayer_card = bar_data['user_card4'][current_player]
            for card in curPlayer_card:
                if card[1] == '黄':
                    y_card.append(card[0])
                elif card[1] == '蓝':
                    b_card.append(card[0])
                elif card[1] == '紫':
                    p_card.append(card[0])
                elif card[1] == '绿':
                    g_card.append(card[0])
                elif card[1] == 'Any':
                    u_card.append(card[0])
                else:
                    raise KeyError("Not a valid color")
            #对列表进行排序
            y_card = sorted(y_card, key=lambda x: sort_order.get(x, float('inf')))
            b_card = sorted(b_card, key=lambda x: sort_order.get(x, float('inf')))
            p_card = sorted(p_card, key=lambda x: sort_order.get(x, float('inf')))
            g_card = sorted(g_card, key=lambda x: sort_order.get(x, float('inf')))
            u_card = sorted(u_card, key=lambda x: universal_order.get(x, float('inf')))
            msg_text = (
                "黄色: "+str(y_card)+"\n"+
                "蓝色: "+str(b_card)+"\n"+
                "紫色: "+str(p_card)+"\n"+
                "绿色: "+str(g_card)+"\n"+
                "任意牌: "+str(u_card)
            )
            await bot.send_private_msg(user_id = int(bar_data['game4'][current_player]), message = f"你的牌组发生了变化，最新牌组如下：\n{msg_text}")

            current_player += 1
        elif card_play[0] == '电枪':
            draw_list = bar_data['draw_card4']
            stop_color = card_play[1]
            current_color = ''
            card_get = 0
            while current_color != 'Any' and current_color != stop_color:
                bar_data['user_card4'][current_player].append(draw_list[0])
                current_color = draw_list[0][1]
                card_get += 1
                del draw_list[0]
                if len(draw_list) == 0:
                    break
            await playcard4.send(message = "恭喜"+MessageSegment.at(bar_data['game4'][current_player])+f"一共获得了{card_get}张牌！", at_sender=False)
            '''
            由于牌组变化，因此要给当前玩家发送消息
            '''
            y_card = []
            b_card = []
            p_card = []
            g_card = []
            u_card = []
            #规定有颜色的牌的排序
            sort_order = {'0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '冰枪': 10, '反转': 11, '铲子': 12}
            universal_order = {'扭蛋': 0, '电枪': 1, '香蕉': 2}
            curPlayer_card = bar_data['user_card4'][current_player]
            for card in curPlayer_card:
                if card[1] == '黄':
                    y_card.append(card[0])
                elif card[1] == '蓝':
                    b_card.append(card[0])
                elif card[1] == '紫':
                    p_card.append(card[0])
                elif card[1] == '绿':
                    g_card.append(card[0])
                elif card[1] == 'Any':
                    u_card.append(card[0])
                else:
                    raise KeyError("Not a valid color")
            #对列表进行排序
            y_card = sorted(y_card, key=lambda x: sort_order.get(x, float('inf')))
            b_card = sorted(b_card, key=lambda x: sort_order.get(x, float('inf')))
            p_card = sorted(p_card, key=lambda x: sort_order.get(x, float('inf')))
            g_card = sorted(g_card, key=lambda x: sort_order.get(x, float('inf')))
            u_card = sorted(u_card, key=lambda x: universal_order.get(x, float('inf')))
            msg_text = (
                "黄色: "+str(y_card)+"\n"+
                "蓝色: "+str(b_card)+"\n"+
                "紫色: "+str(p_card)+"\n"+
                "绿色: "+str(g_card)+"\n"+
                "任意牌: "+str(u_card)
            )
            await bot.send_private_msg(user_id = int(bar_data['game4'][current_player]), message = f"你的牌组发生了变化，最新牌组如下：\n{msg_text}")

            current_player += 1
        elif card_play[0] == '反转':
            bar_data["game4"].reverse()
            bar_data["user_card4"].reverse()
            #current_player = max_player - (current_player % max_player) -1
            await playcard4.send(message = "反转成功")
            #写入主数据表
            with open(bar_path, 'w', encoding='utf-8') as f:
                json.dump(bar_data, f, indent=4)
        
        #处理之后再取余一次，防止报错
        current_player = current_player % max_player
        bar_data['current_player4'] = current_player

        current_player = int(bar_data['current_player4'])

        next_qq = int(bar_data['game4'][current_player])

        #若自身出完了所有牌，则提前判定
        if len(player_card) == 0:
            bar_data['game4_start'] = False
            for user in bar_data['game4']:
                bar_data[str(user)]["status"] = 'nothing'
            bar_data['game4'] = []
            bar_data['user_card4'] = []
            #写入主数据表
            with open(bar_path, 'w', encoding='utf-8') as f:
                json.dump(bar_data, f, indent=4)
            await playcard4.finish(message = "恭喜"+MessageSegment.at(user_id)+f"出完了所有牌，赢得了本场游戏的胜利！", at_sender=False)
        
        #若剩余牌堆里没有牌了，则直接判定
        draw_list = bar_data['draw_card4']
        if len(draw_list) == 0:
            counts=[]
            for cards in bar_data['user_card4']:
                counts.append(len(cards))
            winner_index = counts.index(min(counts))
            bar_data['game4_start'] = False
            for user in bar_data['game4']:
                bar_data[str(user)]["status"] = 'nothing'
            bar_data['game4'] = []
            bar_data['user_card4'] = []
            #写入主数据表
            with open(bar_path, 'w', encoding='utf-8') as f:
                json.dump(bar_data, f, indent=4)
            await playcard4.finish(message = "牌堆已经空了！恭喜"+MessageSegment.at(bar_data['game4'][winner_index])+f"剩余牌数最少，赢得了本场游戏的胜利！", at_sender=False)


        await playcard4.send(
            message=MessageSegment.at(cur_qq) + f"已完成出牌，\n请" + MessageSegment.at(next_qq) + "进行出牌。\n"+
            "出牌格式如下:\n"+
            "/出牌 绿7  即可打出绿色的7\n"+
            "/出牌 蓝冰枪  即可打出蓝色的冰枪\n"+
            "/出牌 紫电枪  即可打出电枪，并规定其为紫色\n"+
            "/出牌 扭蛋  即可打出扭蛋牌，并将其变为随机的数字牌\n"+
            f"当前卡牌为:{last_card[1]}色的{last_card[0]}", at_sender=False)
        
        y_card = []
        b_card = []
        p_card = []
        g_card = []
        u_card = []
        #规定有颜色的牌的排序
        sort_order = {'0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '冰枪': 10, '反转': 11, '铲子': 12}
        universal_order = {'扭蛋': 0, '电枪': 1, '香蕉': 2}
        for card in player_card:
            if card[1] == '黄':
                y_card.append(card[0])
            elif card[1] == '蓝':
                b_card.append(card[0])
            elif card[1] == '紫':
                p_card.append(card[0])
            elif card[1] == '绿':
                g_card.append(card[0])
            elif card[1] == 'Any':
                u_card.append(card[0])
            else:
                raise KeyError("Not a valid color")
        #对列表进行排序
        y_card = sorted(y_card, key=lambda x: sort_order.get(x, float('inf')))
        b_card = sorted(b_card, key=lambda x: sort_order.get(x, float('inf')))
        p_card = sorted(p_card, key=lambda x: sort_order.get(x, float('inf')))
        g_card = sorted(g_card, key=lambda x: sort_order.get(x, float('inf')))
        u_card = sorted(u_card, key=lambda x: universal_order.get(x, float('inf')))
        msg_text = (
            "黄色: "+str(y_card)+"\n"+
            "蓝色: "+str(b_card)+"\n"+
            "紫色: "+str(p_card)+"\n"+
            "绿色: "+str(g_card)+"\n"+
            "任意牌: "+str(u_card)
        )
        #写入主数据表
        with open(bar_path, 'w', encoding='utf-8') as f:
            json.dump(bar_data, f, indent=4)
        await bot.send_private_msg(user_id = int(user_id), message = f"出牌成功，现在你剩余：\n{msg_text}")
        if len(player_card) == 1:
            await playcard4.finish("只剩1张牌了，请注意。",at_sender=True)
        else:
            await playcard4.finish()
    else:
        await playcard4.finish("还没轮到你出牌哦，先等等吧")

drawcard4 = on_command('跳过', permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@drawcard4.handle()
async def drawcard4_handle(bot: Bot, event: GroupMessageEvent,  arg: Message = CommandArg()):
    # 打开文件
    user_id = event.get_user_id()
    bar_data = {}
    with open(bar_path, 'r', encoding='utf-8') as f:
        bar_data = json.load(f)
    
    try:
        player_in_game4 = bar_data["game4"]
    except:
        player_in_game4 = []
    
    try:
        max_player = bar_data['max_player4']
    except:
        max_player = 1000
    
    #是否参与了游戏
    if str(user_id) not in player_in_game4:
        await drawcard4.finish("你似乎没有参与本场游戏呢~")
    
    #如果人数不足，则直接结束，无法出牌
    if len(player_in_game4) < max_player:
        await drawcard4.finish("游戏似乎没有开始呢~")
    
    #是否是自己出牌的轮次
    current_player = int(bar_data['current_player4'])
    player_index = int(bar_data['game4'].index(str(user_id)))

    if current_player == player_index:
        draw_list = bar_data['draw_card4']
        bar_data['user_card4'][current_player].append(draw_list[0])
        del draw_list[0]
        cur_qq = int(bar_data['game4'][current_player])

        #若剩余牌堆里没有牌了，则直接判定
        if len(draw_list) == 0:
            counts=[]
            for cards in bar_data['user_card4']:
                counts.append(len(cards))
            winner_index = counts.index(min(counts))
            bar_data['game4_start'] = False
            for user in bar_data['game4']:
                bar_data[str(user)]["status"] = 'nothing'
            bar_data['game4'] = []
            bar_data['user_card4'] = []
            await drawcard4.finish(message = "牌堆已经空了！恭喜"+MessageSegment.at(bar_data['game4'][winner_index])+f"剩余牌数最少，赢得了本场游戏的胜利！", at_sender=False)


        '''
        由于牌组变化，因此要给当前玩家发送消息
        '''
        y_card = []
        b_card = []
        p_card = []
        g_card = []
        u_card = []
        #规定有颜色的牌的排序
        sort_order = {'0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '冰冻': 10, '反转': 11, '铲子': 12}
        universal_order = {'扭蛋': 0, '电枪': 1, '香蕉': 2}
        curPlayer_card = bar_data['user_card4'][current_player]
        for card in curPlayer_card:
            if card[1] == '黄':
                y_card.append(card[0])
            elif card[1] == '蓝':
                b_card.append(card[0])
            elif card[1] == '紫':
                p_card.append(card[0])
            elif card[1] == '绿':
                g_card.append(card[0])
            elif card[1] == 'Any':
                u_card.append(card[0])
            else:
                raise KeyError("Not a valid color")
        #对列表进行排序
        y_card = sorted(y_card, key=lambda x: sort_order.get(x, float('inf')))
        b_card = sorted(b_card, key=lambda x: sort_order.get(x, float('inf')))
        p_card = sorted(p_card, key=lambda x: sort_order.get(x, float('inf')))
        g_card = sorted(g_card, key=lambda x: sort_order.get(x, float('inf')))
        u_card = sorted(u_card, key=lambda x: universal_order.get(x, float('inf')))
        msg_text = (
            "黄色: "+str(y_card)+"\n"+
            "蓝色: "+str(b_card)+"\n"+
            "紫色: "+str(p_card)+"\n"+
            "绿色: "+str(g_card)+"\n"+
            "任意牌: "+str(u_card)
        )
        await bot.send_private_msg(user_id = int(user_id), message = f"你的牌组发生了变化，最新牌组如下：\n{msg_text}")

        current_player += 1
        current_player = current_player % max_player
        bar_data['current_player4'] = current_player
        next_qq = int(bar_data['game4'][current_player])

        last_card = bar_data["current_card4"]
        #写入主数据表
        with open(bar_path, 'w', encoding='utf-8') as f:
            json.dump(bar_data, f, indent=4)
        await drawcard4.finish(
            message=MessageSegment.at(cur_qq) + f"已跳过本回合，\n请" + MessageSegment.at(next_qq) + "进行出牌。\n"+
            "出牌格式如下:\n"+
            "/出牌 绿7  即可打出绿色的7\n"+
            "/出牌 蓝冰枪  即可打出蓝色的冰枪\n"+
            "/出牌 紫电枪  即可打出电枪，并规定其为紫色\n"+
            "/出牌 扭蛋  即可打出扭蛋牌，并将其变为随机的数字牌\n"+
            f"当前卡牌为:{last_card[1]}色的{last_card[0]}", at_sender=False)
    else:
        await drawcard4.finish("还没轮到你跳过哦，先等等吧")


#------用于游戏的一些函数------
def shot(attempts) -> bool:
            '''
            开枪时的判定，返回一个布尔值
            True代表本枪为空弹
            False代表本枪为实弹
            '''
            rnd_number=random.randint(1,6)
            if (attempts+1) >= rnd_number:
                return False
            else:
                return True
            
def deal_card(bar_data, max_player) -> list:

    card_list = ['A'] * 6 + ['Q'] * 6 + ['K'] * 6 + ['Joker'] * 2
            
    #发牌阶段
    real_card = random.choice(['A', 'Q', 'K'])
    card_keep = []
    for i in range(max_player):
        card_keep.append([])
        for _ in range(5):
            select_card = random.choice(card_list)
            card_list.remove(select_card)
            if select_card == 'Joker':
                select_card = real_card
            card_keep[i].append(select_card)
    
    return [card_keep, real_card]

def deal_card4(max_player) -> list:
    '''
    p4的发牌系统，只在游戏开局应用
    每张牌存储为列表格式：[数字, 颜色]
    若为万能牌则颜色存储为'Any'
    返回的列表有3个元素，
    第一个元素为每个玩家所分到的牌，
    第二个元素为剩余牌堆，
    第三个元素为第一张牌(不会是道具牌/万能牌)
    '''

    # 定义UNO牌的颜色
    colors = ['黄', '蓝', '紫', '绿']

    # 定义UNO牌的数字（0-9）
    numbers = list(range(10))  # 0-9

    # 定义道具牌的列表
    tools = ['冰枪', '反转', '铲子']

    #定义万能牌的列表
    #若添加新道具，则修改此列表
    universal = [['扭蛋', 4], ['电枪', 2]]#, ['香蕉', 1]

    # 创建一个空列表来存储所有的牌
    card_list = []

    for color in colors:
        # 添加数字牌
        for number in numbers:
            card_list.append([str(number), color])
            if number != '0':  # 每个数字牌（除了0）有两张
                card_list.append([str(number), color])
        # 添加道具牌
        for tool in tools:
            card_list.append([tool, color])
            card_list.append([tool, color])
    # 添加万能牌
    for u in universal:
        for _ in range (u[1]):
            card_list.append([u[0], 'Any'])
    
    # 规定起始牌
    # 筛选出所有数字牌
    number_cards = [card for card in card_list if card[0] in ['0','1','2','3','4','5','6','7','8','9']]

    # 随机抽取一张数字牌
    start_card = random.choice(number_cards)
    
    # 发牌阶段
    card_keep = []
    for i in range(max_player):
        card_keep.append([])
        for _ in range(7):
            select_card = random.choice(card_list)
            card_list.remove(select_card)
            card_keep[i].append(select_card)
    
    random.shuffle(card_list)
    return [card_keep, card_list, start_card]

# “游戏3”：恶魔赌局
# demon道具列表及相关函数
item_dic1 = {
    1: "桃",
    2: "医疗箱",
    3: "放大镜",
    4: "眼镜",
    5: "手铐",
    6: "欲望之盒",
    7: "无中生有",
    8: "小刀",
    9: "酒",
    10: "啤酒",
    11: "刷新票",
    12: "手套",
    13: '骰子',
    14: "禁止卡",
    15: '墨镜',
    }
# 身份模式道具列表
item_dic2 = { 
    16: '双转团',
    17: '天秤', 
    18: '休养生息',
    19: '玩具枪',
    20: '烈弓',
    21: '血刃',
    22: '黑洞',
    23: '金苹果',
    24: '铂金草莓',
    25: '肾上腺素',
    26: '烈性TNT',
    }

item_dic = item_dic1 | item_dic2

# demon_default
demon_default = {
    "pl": [],
    "hp": [],
    "item_0": [],
    "item_1": [],
    'hcf': 0,
    'clip': [],
    'turn': 0,
    'atk': 0,
    'hp_max': 0,
    'item_max': 0,
    'game_turn': 1,
    'add_atk': False,
    'start': False,
    'identity': 0,
    'demon_coldtime': int(time.time()),
    'turn_start_time': int(time.time())
}

# 定义身份模式死斗回合数方便更改
death_turn = 12
pangguang_turn = 5

# 定义不同状态对应的轮数限制
turn_limit = {
    1: death_turn,  # "死斗模式" 开启的轮数限制
    2: pangguang_turn,    # "膀胱模式" 开启的轮数限制
    999: pangguang_turn    # "跑团专用999模式" 开启的轮数限制
}

# 设定kp必定先手
kp_pl = 1234567890

# 定义道具效果的字典
item_effects = {
    "桃": "回复1点hp",
    "医疗箱": "回复2点hp，但跳过你的这一回合，并且对方的所有束缚解除！",
    "放大镜": "观察下一颗子弹的种类",
    "眼镜": "观察下两颗子弹的种类，但顺序未知",
    "手铐": "跳过对方下一回合（不可重复使用/与禁止卡一同使用）",
    "禁止卡": "跳过对方下1~2（随机）个回合，对方获得禁止卡（若对方道具已达6个上限，将不会获得禁止卡）",
    "欲望之盒": "50%抽取一个道具，30%恢复一点血量（若血量达到上限将赠与一个本轮无视道具上限的桃），20%对对方造成一点伤害",
    "无中生有": "抽取两个道具，然后跳过回合，对方若有束缚，束缚的回合-1！并且无中生有生成的道具直到本轮实弹耗尽前可以超出上限（本轮实弹耗尽后超出上限的道具会消失）！",
    "小刀": "伤害变为2（注：同时使用多个小刀或酒会导致浪费！）",
    "酒": "伤害变为2，同时若hp等于1时，回复1hp（注：同时使用多个小刀或酒会导致浪费！）",
    "啤酒": "退掉下一发子弹（若退掉的是最后一发子弹，进行道具的刷新）",
    "刷新票": "使用后，重新抽取和剩余道具数量相等的道具",
    "手套": "重新换弹，不进行道具刷新",
    "骰子": "你的hp变为1到4的随机值",
    "墨镜": "观察第一颗和最后一颗子弹的种类，但顺序未知",
    "双转团": "（该道具为“身份”模式专属道具）把这个道具转移到对方道具栏里，若对方道具已达上限则丢弃本道具；另外还有概率触发特殊效果？可能会掉血，可能会回血，可能会送给对方道具……但由于其富含identity，可能有其他的非play3游戏内的效果？",
    "天秤": "（该道具为“身份”模式专属道具）如果你的道具数量≥对方道具数量，你对对方造成一点伤害；你的道具数量<对方道具数量，你回一点血",
    "休养生息": "（该道具为“身份”模式专属道具）自己的hp恢复2，对方的hp恢复1，不跳回合；若对面为满血，则只回一点体力。",
    "玩具枪": "（该道具为“身份”模式专属道具）1/2的概率无事发生，1/2的概率对对面造成1点伤害",
    "烈弓": "（该道具为“身份”模式专属道具）使用烈弓后，下一发子弹伤害+1，且伤害类道具（小刀、酒、烈弓）的加伤效果可以无限叠加！",
    "血刃": "（该道具为“身份”模式专属道具）可以扣自己1点血，获得两个道具！并且获得的道具直到本轮实弹耗尽前可以超出上限（本轮实弹耗尽后超出上限的道具会消失）",
    "黑洞": "（该道具为“身份”模式专属道具）召唤出黑洞，随机夺取对方的任意一个道具！\n如果对方没有道具，黑洞将在沉寂中回到你的身边。",
    "金苹果": "（该道具为“身份”模式专属道具）金苹果可以让你回复3点hp！但是作为代价你会跳过接下来的两个回合！不过对面的手铐和禁止卡也似乎不能使用了……",
    "铂金草莓": "（该道具为“身份”模式专属道具）因为是铂金草莓，所以能做到！自己回复1点hp，并且双方各加1点hp上限！",
    "肾上腺素": "（该道具为“身份”模式专属道具）双方的hp上限-1，道具上限+1，并且使用者获得一个新道具！如果你们的hp上限为1，无法使用该道具！",
    "烈性TNT": "（该道具为“身份”模式专属道具）双方的hp上限-1，hp各-1！注意，是先扣hp上限，然后再扣hp！另外，如果使用后会自杀，则无法使用该道具！",
}

help_msg = f"""
输入 /开枪 自己/对方 -|- 向自己/对方开枪
输入 /查看局势 -|- 查看当前局势
输入 /恶魔道具 道具名/all -|- 查看道具的使用说明
输入 /恶魔投降 -|- 进行投降
输入 /使用道具 道具名 -|- 使用道具"""

# 奖励设置
jiangli = 350

# 全局变量——事件（单位s）
turn_time = 600

#特殊user_id增加bet2权重（为跑团而生的一个东西（（（）
special_users = {
    '123456': {19: 1000, 21: 3},
    '789101': {22: 4}
}

# 定义权重表
def get_random_item(identity_found, normal_mode_limit, user_id):
    """根据模式返回一个随机道具"""
    
    item_count = len(item_dic)  # 道具总数
    normal_mode_items = [] # 普通模式需要增加权重的道具（暂无）
    identity_mode_items = [3] # 身份模式需要增加权重的道具（放大镜）
    
    # 动态生成权重表
    weights = {i: 0 for i in range(1, item_count + 1)}  # 初始化所有道具权重为0
    
    if identity_found == 0:
        # 普通模式：前 normal_mode_limit 个道具权重设为1，其他保持0
        for i in range(1, normal_mode_limit + 1):
            weights[i] = 1
    elif identity_found in [1,2]:
        # 身份模式：所有道具启用，部分稀有道具权重设为2
        for i in range(1, item_count + 1):
            weights[i] = 1
        for i in identity_mode_items:
            weights[i] = 2  # 增加稀有道具的出现概率
    
    # 特殊用户指定道具加成
    if user_id in special_users:
        for item_id, bonus in special_users[user_id].items():
            if 1 <= item_id <= len(item_dic):  # 确保道具ID合法
                weights[item_id] += bonus  

    # 生成候选列表（按照权重扩展）
    valid_items = [i for i in weights if weights[i] > 0]
    item_choices = [i for i in valid_items for _ in range(weights[i])]

    return random.choice(item_choices)

# 上弹函数
def load():
    """上弹，1代表实弹，0代表空弹"""
    clip_size = random.randint(2, 8)  # 随机生成弹夹容量
    if clip_size == 2:
        # 如果总弹数为2，强制设置一个实弹
        clip = [0, 1]
        random.shuffle(clip)  # 随机打乱弹夹顺序
    else:
        bullets = random.randint(1, clip_size // 2 + 1)  # 随机生成实弹数量
        clip = [0] * clip_size
        bullet_positions = random.sample(range(clip_size), bullets)  # 确定实弹位置
        for pos in bullet_positions:
            clip[pos] = 1
    return clip

# 游戏结束函数
def handle_game_end(
    group_id: str,
    winner: str,
    prefix_msg: str,
    bar_data: dict,
    demon_data: dict
):
    """处理游戏结束的公共逻辑（使用全局变量）"""
    user_data = open_data(full_path)
    
    players = demon_data[group_id]['pl']
    player0 = str(players[0])
    player1 = str(players[1])
    
    # 发放奖励
    user_data[winner]['spike'] += jiangli
    
    # 构建基础消息
    msg = prefix_msg + "恭喜" + MessageSegment.at(str(winner)) + (
        f'胜利！恭喜获得{jiangli}刺儿！'
    )
    
    rnd= random.randint(1,100)
    if rnd<=5:
        #判断是否开辟藏品栏
        if(not 'collections' in user_data[str(winner)]):
            user_data[str(winner)]['collections'] = {}
        #判断是否有爆破师徽章
        if(not '爆破师徽章' in user_data[str(winner)]['collections']):
            user_data[str(winner)]['collections']['爆破师徽章'] = 1
            msg += MessageSegment.at(str(winner))+'\n似乎发现了桌子底下有一个还在发光的徽章，似乎是之前的玩家留下来的。\n输入 /藏品 爆破师徽章 以查看具体效果'
    elif rnd <= 25:
        #判断是否开辟藏品栏
        if(not 'collections' in user_data[str(winner)]):
            user_data[str(winner)]['collections'] = {}
        #是否已经持有藏品"身份徽章"
        #如果没有，则添加
        if(not '身份徽章' in user_data[str(winner)]['collections']):
            user_data[str(winner)]['collections']['身份徽章'] = 1
            msg += f"\n\n游戏结束时，你意外从桌子底下看到了一个亮闪闪的徽章，上面写着“identity”，你感到十分疑惑，便捡了起来。输入/藏品 身份徽章 以查看具体效果"    
    
    # 更新玩家状态
    for player in [player0, player1]:
        bar_data[player]['game'] = '1'
        bar_data[player]['status'] = 'nothing'
    
    # 膀胱模式检测
    game_turn = demon_data[group_id]['game_turn']
    if game_turn > death_turn:
        if any(user_data[p].get('pangguang', 0) == 0 for p in [player0, player1]):
            msg += f"\n- 你们已经打了{demon_data[group_id]['game_turn']}轮，超过{death_turn}轮了……这股膀胱的怨念射入身份徽章里面！现在你们的身份徽章已解锁极速模式！就算暂时没有身份徽章以后也能直接切换！请使用 /use 身份徽章/2 切换！"
        for p in [player0, player1]:
            user_data[p]['pangguang'] = 1
    
    # 重置游戏数据
    demon_data[group_id] = demon_default.copy()
    demon_data[group_id]['demon_coldtime'] = int(time.time()) + 300
    
    # 统一保存数据
    save_data(full_path, user_data)
    
    return msg, bar_data, demon_data

# 死斗函数
def death_mode(identity_found, group_id, demon_data):
    '''判断是否开启死斗模式：根据不同的状态和轮数进行血量上限扣减，保存状态后最后返回msg'''
    player0 = str(demon_data[group_id]['pl'][0])
    player1 = str(demon_data[group_id]['pl'][1])
    msg = ''
    
    if identity_found in turn_limit and demon_data[group_id]['game_turn'] > turn_limit[identity_found]:
        msg += f'\n- 轮数大于{turn_limit[identity_found]}，死斗模式开启！\n'
        
        # HP 上限减少
        if identity_found in [1,2] and demon_data[group_id]["hp_max"] > 1:
            demon_data[group_id]["hp_max"] -= 1
            new_hp_max = demon_data[group_id]["hp_max"]
            msg += f'- {new_hp_max+1}>1，扣1点hp上限，当前hp上限：{new_hp_max}\n'
            
            # 校准所有玩家血量不得超过 hp 上限
            for i in range(len(demon_data[group_id]["hp"])):
                demon_data[group_id]["hp"][i] = min(demon_data[group_id]["hp"][i], demon_data[group_id]["hp_max"])

        # 额外扣除 1 点道具上限，并随机删除 1-2 个道具
        if identity_found in [1,2]:
            if demon_data[group_id]["item_max"] > 6:
                demon_data[group_id]["item_max"] -= 1  # 扣 1 点道具上限（最低仍为 6）
                new_item_max = demon_data[group_id]["item_max"]
                msg += f'- {new_item_max+1}>6，扣1点道具上限，当前道具上限：{demon_data[group_id]["item_max"]}\n'

            remove_random = random.randint(1, 2)
            
            # 计算可删除的道具数量
            remove_count0 = min(remove_random, len(demon_data[group_id]['item_0'])) if demon_data[group_id]['item_0'] else 0
            remove_count1 = min(remove_random, len(demon_data[group_id]['item_1'])) if demon_data[group_id]['item_1'] else 0

            # 随机选择要删除的道具
            removed_items_0 = random.sample(demon_data[group_id]['item_0'], remove_count0) if remove_count0 else []
            removed_items_1 = random.sample(demon_data[group_id]['item_1'], remove_count1) if remove_count1 else []

            # 逐个删除选定的道具实例
            for item in removed_items_0:
                demon_data[group_id]['item_0'].remove(item)

            for item in removed_items_1:
                demon_data[group_id]['item_1'].remove(item) 

            # 记录被删除的道具名称
            removed_names_0 = [item_dic.get(i, "未知道具") for i in removed_items_0]
            removed_names_1 = [item_dic.get(i, "未知道具") for i in removed_items_1]

            # 记录删除的信息
            if removed_names_0:
                msg += '- '+ MessageSegment.at(player0) + f'失去了{remove_count0}个道具：{"、".join(removed_names_0)}！\n'
            if removed_names_1:
                msg += '- '+ MessageSegment.at(player1) + f'失去了{remove_count1}个道具：{"、".join(removed_names_1)}！\n'

        # 跑团专用999模式，额外扣2点HP上限
        elif identity_found == 999 and demon_data[group_id]["hp_max"] > 1:
            old_hp_max = demon_data[group_id]["hp_max"]
            demon_data[group_id]["hp_max"] -= 2
            if demon_data[group_id]["hp_max"] <= 1:
                demon_data[group_id]["hp_max"] = 1
            new_hp_max = demon_data[group_id]["hp_max"]
            msg += f'- {old_hp_max}>1，扣2点hp上限，当前hp上限：{new_hp_max}\n'

            # 校准所有玩家血量不得超过hp上限
            for i in range(len(demon_data[group_id]["hp"])):
                demon_data[group_id]["hp"][i] = min(demon_data[group_id]["hp"][i], demon_data[group_id]["hp_max"])
    
    return msg, demon_data

# 计算随机函数
def calculate_interval(game_turn_add, add_max, pangguang_add):
    # 计算下限
    lower_bound = 1 + (add_max // 2) + (game_turn_add * (pangguang_add // 3))
    
    # 计算上限
    upper_bound = 3 + (add_max // 2) + (game_turn_add * (pangguang_add // 2))
    
    # 确保下限不超过上限
    if lower_bound > upper_bound:
        lower_bound = upper_bound
    
    return lower_bound, upper_bound

# 刷新道具函数
def refersh_item(identity_found, group_id, demon_data):
    idt_len = len(item_dic2)
    add_max = 0
    pangguang_add = 0
    game_turn_add = 0
    msg = ''
    if identity_found == 1:
        idt_len = 0
        add_max = 2
        pangguang_add = 5
    elif identity_found in [2,999]:
        idt_len = 0
        add_max = 2
        pangguang_add = 2
    game_turn_cal = demon_data[group_id]["game_turn"]

    if game_turn_cal == 1:
        game_turn_add = 1

    lower, upper = calculate_interval(game_turn_add, add_max, pangguang_add)
    player0 = str(demon_data[group_id]['pl'][0])
    player1 = str(demon_data[group_id]['pl'][1])
    hp0 = demon_data[group_id]["hp"][0]
    hp1 = demon_data[group_id]["hp"][1]
    # 重新获取hp_max
    hp_max = demon_data.get(group_id, {}).get('hp_max')
    item_max = demon_data.get(group_id, {}).get('item_max')
    for i in range(random.randint(lower, upper)):
        demon_data[group_id]['item_0'].append(get_random_item(identity_found, len(item_dic) - idt_len, player0))
        demon_data[group_id]['item_1'].append(get_random_item(identity_found, len(item_dic) - idt_len, player1))
    # 检查并限制道具数量上限为max
    demon_data[group_id]['item_0'] = demon_data[group_id]['item_0'][:item_max]  # 截取前max个道具
    demon_data[group_id]['item_1'] = demon_data[group_id]['item_1'][:item_max]  # 截取前max个道具
    # 生成道具信息
    item_0 = ", ".join(item_dic.get(i, "未知道具") for i in demon_data[group_id]['item_0'])
    item_1 = ", ".join(item_dic.get(i, "未知道具") for i in demon_data[group_id]['item_1'])
    # 获取玩家道具信息
    items_0 = demon_data[group_id]['item_0']  # 玩家0道具列表
    items_1 = demon_data[group_id]['item_1']  # 玩家1道具列表
    if len(items_0) == 0:
        item_0 = "你目前没有道具哦！"
    if len(items_1) == 0:
        item_1 = "你目前没有道具哦！"
    msg += MessageSegment.at(player0) + f"\nhp：{hp0}/{hp_max}\n" + f"道具({len(items_0)}/{item_max})：" +f"\n{item_0}\n\n"
    msg += MessageSegment.at(player1) + f"\nhp：{hp1}/{hp_max}\n" + f"道具({len(items_1)}/{item_max})：" +f"\n{item_1}\n"

    return msg, demon_data

# 开枪函数
async def shoot(stp, group_id, message,args):
    demon_data = open_data(demon_path)
    user_data = open_data(full_path)
    bar_data = open_data(bar_path)
    hp_max = demon_data.get(group_id, {}).get('hp_max')
    item_max = demon_data.get(group_id, {}).get('item_max')
    clip = demon_data.get(group_id, {}).get('clip')
    hp = demon_data.get(group_id, {}).get('hp')
    pl = demon_data.get(group_id, {}).get('turn')
    player0 = str(demon_data[group_id]['pl'][0])
    player1 = str(demon_data[group_id]['pl'][1])
    identity_found = demon_data[group_id]['identity'] 
    add_max = 0
    pangguang_add = 0
    # 身份模式开了就更新dlc
    idt_len = len(item_dic2)
    if identity_found == 1:
        idt_len = 0
        add_max += 1
    elif identity_found in [2,999]:
        idt_len = 0
        add_max += 1
        pangguang_add += 2
    msg = ""
    if clip[-1] == 1:
        atk = demon_data[group_id]['atk']
        hp[pl-stp] -= 1 + atk
        demon_data[group_id]['atk'] = 0
        demon_data[group_id]['add_atk'] = False
        if atk != 0:
            msg += f"\n- 这颗子弹伤害为……{atk+1}点！"
        if atk in [3, 4]:
            msg += '\n- 癫狂屠戮！'
        if atk >= 5:
            msg += '\n- 无双，万军取首！'
        msg += f'\n- 你开枪了，子弹 *【击中了】* {args}！{args}剩余hp：{str(hp[pl-stp])}/{hp_max}\n'
    else:
        demon_data[group_id]['atk'] = 0
        demon_data[group_id]['add_atk'] = False
        msg += f'\n- 你开枪了，子弹未击中{args}！{args}剩余hp：{str(hp[pl-stp])}/{hp_max}\n'
    del clip[-1]
    
    if len(clip) == 0 or clip.count(1) == 0:
        msg += '- 子弹用尽，重新换弹，道具更新！\n'
        # 游戏轮数+1
        demon_data[group_id]['game_turn'] += 1
        # 获取死斗模式信息
        death_msg, demon_data = death_mode(identity_found, group_id, demon_data)
        msg += f'- 当前轮数：{demon_data[group_id]['game_turn']}\n'
        msg += death_msg
        # 增加换行，优化排版
        msg += "\n"
        clip = load()
        # 获取刷新道具
        item_msg, demon_data = refersh_item(identity_found, group_id, demon_data)
        msg += item_msg
        # 增加换行，优化排版
        msg += "\n"
    
    if demon_data[group_id]['hcf'] < 0 and stp != 0:
        demon_data[group_id]['hcf'] = 0
        out_pl = demon_data[group_id]['pl'][demon_data[group_id]['turn']-1]
        msg += "- "+MessageSegment.at(str(out_pl)) + "已挣脱束缚！\n"
    if demon_data[group_id]['hcf'] == 0 or stp == 0:
        pl += stp
        pl = pl%2   
    else:
        demon_data[group_id]['hcf'] -= 2
    hcf = demon_data.get(group_id, {}).get('hcf')
    if hcf != 0:
        msg += f"- 当前对方剩余束缚回合数：{(hcf+1)//2}\n"
    demon_data[group_id]['turn'] = pl
    demon_data[group_id]['clip'] = clip
    demon_data[group_id]['hp'] = hp
    # 刷新时间
    demon_data[group_id]['turn_start_time'] = int(time.time())
    if demon_data[group_id]['hp'][0] <= 0: 
        winner = demon_data[group_id]['pl'][1]
        end_msg, bar_data, demon_data = handle_game_end(
            group_id=str(group_id),
            winner=winner,
            prefix_msg="- 游戏结束！",
            bar_data=bar_data,
            demon_data=demon_data
        )
        msg += end_msg
    elif demon_data[group_id]['hp'][1] <= 0:
        winner = demon_data[group_id]['pl'][0]
        end_msg, bar_data, demon_data = handle_game_end(
            group_id=str(group_id),
            winner=winner,
            prefix_msg="- 游戏结束！",
            bar_data=bar_data,
            demon_data=demon_data
        )
        msg += end_msg
    else:
        pid = demon_data[group_id]['pl'][demon_data[group_id]['turn']]
        msg += '- 本局总弹数为'+str(len(demon_data[group_id]['clip']))+'，实弹数为'+str(demon_data[group_id]['clip'].count(1))+"\n" + "- 当前是"+ MessageSegment.at(pid) + "的回合"
    save_data(bar_path, bar_data)
    save_data(demon_path, demon_data)
    await message.finish(msg, at_sender = True)

# 开枪命令
fire = on_command("开枪",aliases={"射击"}, permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@fire.handle()
async def fire_handle(bot: Bot, event: GroupMessageEvent, arg: Message = CommandArg()):
    group_id = str(event.group_id)
    if await check_timeout(group_id):
        return
    user_id = str(event.user_id)
    args = str(arg).strip()
    demon_data = open_data(demon_path)
    player_turn = demon_data[group_id]["turn"]
    
    if demon_data[group_id]["start"] == False:
        await fire.finish("恶魔轮盘du尚未开始！",at_sender = True)
        
    if user_id not in demon_data[group_id]['pl']:
        await fire.finish("只有当前局内玩家能行动哦！",at_sender = True)

    if demon_data[group_id]["pl"][player_turn] != user_id:
        await fire.finish("现在不是你的回合，请等待对方操作！",at_sender = True)
    
    if args == "自己":
        stp = 0
        # 调用开枪函数
        await shoot(stp,group_id,fire,args)
    elif args == "对方":
        stp = 1
        # 调用开枪函数
        await shoot(stp,group_id,fire,args)
    else:
        await fire.finish("指令错误！请输入 </开枪 自己> 或者 </开枪 对方> 来开枪哦！",at_sender = True)

# 使用道具
prop_demon = on_command("使用",aliases={"使用道具"}, permission=GROUP, priority=1, block=True, rule=whitelist_rule)

@prop_demon.handle()
async def prop_demon_handle(bot: Bot, event: GroupMessageEvent, arg: Message = CommandArg()):
    group_id = str(event.group_id)
    if await check_timeout(group_id):
        return
    user_id = str(event.user_id)
    args = str(arg).strip()
    user_data = open_data(full_path)
    bar_data = open_data(bar_path)
    demon_data = open_data(demon_path)
    player_turn = demon_data[group_id]["turn"]
    add_max = 0
    pangguang_add = 0
    if demon_data[group_id]["start"] == False:
        await prop_demon.finish("恶魔轮盘du尚未开始！", at_sender=True)

    if user_id not in demon_data[group_id]['pl']:
        await prop_demon.finish("只有当前局内玩家能行动哦！", at_sender=True)

    if demon_data[group_id]["pl"][player_turn] != user_id:
        await prop_demon.finish("现在不是你的回合，请等待对方操作！", at_sender=True)
    identity_found = demon_data[group_id]['identity'] 
    # 身份模式开了就更新dlc
    idt_len = len(item_dic2)
    if identity_found == 1:
        idt_len = 0
        add_max += 1
    elif identity_found in [2,999]:
        idt_len = 0
        add_max += 1
        pangguang_add += 2
    
    # 提取数据
    player_items = demon_data[group_id][f"item_{player_turn}"]
    opponent_turn = (player_turn + 1) % len(demon_data[group_id]['pl'])
    opponent_items = demon_data[group_id][f"item_{opponent_turn}"]

    # 道具名称匹配（忽略大小写）
    args_lower = args.lower()
    item_dic_lower = {key: value.lower() for key, value in item_dic.items()}  # 生成一个忽略大小写的字典

    if args_lower not in item_dic_lower.values():  # 检查输入的名称是否存在于 item_dic（忽略大小写）
        await prop_demon.finish("你输入的道具不存在，请确认后再使用！")

    # 查找玩家的道具中是否存在该道具
    try:
        # 遍历玩家的道具ID，找到第一个匹配的道具名称（忽略大小写）
        item_idx = next(i for i, item_id in enumerate(player_items) if item_dic[item_id].lower() == args_lower)
    except StopIteration:
        await prop_demon.finish("你并没有这个道具，请确认后再使用！", at_sender=True)

    # 提取数据
    item_id = player_items[item_idx]
    item_name = item_dic[item_id]
    hp_max = demon_data.get(group_id, {}).get('hp_max')
    item_max = demon_data.get(group_id, {}).get('item_max')
    msg = MessageSegment.at(str(demon_data[group_id]["pl"][player_turn])) + f"使用了道具：{item_name}\n\n"
    player_items.pop(item_idx)
    demon_data[group_id]['turn_start_time'] = int(time.time()) # 更新回合时间
    
    if item_name == "桃":
        demon_data[group_id]["hp"][player_turn] += 1
        if demon_data[group_id]["hp"][player_turn] >= hp_max:
            demon_data[group_id]["hp"][player_turn] = hp_max
        msg += f"你的hp回复1点（最高恢复至体力上限）。\n当前hp：{demon_data[group_id]['hp'][player_turn]}/{hp_max}\n"

    elif item_name == "医疗箱":
        demon_data[group_id]["hp"][player_turn] += 2
        demon_data[group_id]["hcf"] = 0
        demon_data[group_id]["atk"] = 0
        if demon_data[group_id]["hp"][player_turn] >= hp_max:
            demon_data[group_id]["hp"][player_turn] = hp_max
        demon_data[group_id]['turn'] = (player_turn + 1) % len(demon_data[group_id]['pl'])
        msg += f"你的hp回复2点（最高恢复至体力上限），但是代价是跳过本回合，而且对方的束缚将自动挣脱！\n当前hp：{demon_data[group_id]['hp'][player_turn]}/{hp_max}\n"

    elif item_name == "放大镜":
        next_bullet = "实弹" if demon_data[group_id]['clip'][-1] == 1 else "空弹"
        msg += f"下一颗子弹是：{next_bullet}！\n"

    elif item_name == "眼镜":
        if len(demon_data[group_id]['clip']) > 1:
            count_real_bullets = demon_data[group_id]['clip'][-2:].count(1)
            msg += f"前两颗子弹中有 {count_real_bullets} 颗实弹。\n"
        else:
            msg += f"枪膛里只剩最后一颗子弹了，是{'实弹' if demon_data[group_id]['clip'][-1] == 1 else '空弹'}！\n"

    elif item_name == "手铐":
        if demon_data[group_id]['hcf'] == 0:
            demon_data[group_id]['hcf'] = 1
            msg += "你成功拷住了对方！\n"
        else:
            player_items.append(item_id)
            msg += "不可使用！对方仍处于束缚状态！\n"

    elif item_name == "禁止卡":
        # 获取对方的回合编号
        if demon_data[group_id]['hcf'] == 0:
            add_turn = (random.randint(0,1)*2)
            if add_turn == 0:
                skip_turn = 1
            else:
                skip_turn = 2
            demon_data[group_id]['hcf'] = 1 + add_turn
            if len(opponent_items) < item_max:
                opponent_items.append(item_id)  # 只有在对方道具少于 max_item 个时才增加禁止卡
                msg += f"你成功禁止住了对方！禁止了{skip_turn}个回合，但同时对方也获得了一张禁止卡！\n"
            else:
                msg += f"你成功禁止住了对方！禁止了{skip_turn}个回合，但对方道具已满，并未获得这张禁止卡！\n"
        else:
            player_items.append(item_id)
            msg += "不可使用！对方仍处于束缚状态！\n"

    elif item_name == "欲望之盒":
        randchoice = random.randint(1, 10)
        if randchoice <= 5:
            new_item = get_random_item(identity_found, len(item_dic) - idt_len, user_id)
            player_items.append(new_item)
            new_item_name = item_dic[new_item]
            msg += f"你打开了欲望之盒，获得了道具：{new_item_name}\n"
        elif randchoice <= 8:
            msg += f"你打开了欲望之盒，恢复了1点体力\n"
            demon_data[group_id]["hp"][player_turn] += 1
            if demon_data[group_id]["hp"][player_turn] >= hp_max + 1:
                demon_data[group_id]["hp"][player_turn] = hp_max
                player_items.append(1)
                msg += f"但是由于你的体力已经到达上限，这点体力将转化为桃送给你。这个桃无视道具上限，但只有这轮有效。\n"
            msg += f"当前hp：{demon_data[group_id]['hp'][player_turn]}/{hp_max}\n"
        elif randchoice <= 10:
            demon_data[group_id]["hp"][opponent_turn] -= 1
            msg += f"你打开了欲望之盒，对对面造成了一点伤害！\n对方目前剩余hp为：{demon_data[group_id]['hp'][opponent_turn]}\n"

    elif item_name == "无中生有":
        new_items = [get_random_item(identity_found, len(item_dic) - idt_len, user_id) for _ in range(2)]
        player_items.extend(new_items)  # 添加新道具
        new_items_names = [item_dic[item] for item in new_items]
        if demon_data[group_id]["hcf"] <= 0:
            demon_data[group_id]["atk"] = 0
            demon_data[group_id]["hcf"] = 0
            demon_data[group_id]['turn'] = (player_turn + 1) % len(demon_data[group_id]['pl'])
            msg += f"你使用了无中生有，获得了道具：{', '.join(new_items_names)}\n代价是跳过了自己的回合!\n"
        elif demon_data[group_id]["hcf"] >= 1:
            demon_data[group_id]["hcf"] -= 2
            msg += f"你使用了无中生有，获得了道具：{', '.join(new_items_names)}\n代价是对方的束缚的回合将-1！\n"

    elif item_name == "小刀":
        if demon_data[group_id]["add_atk"]:
            demon_data[group_id]['atk'] += 1
            msg += f"你装备了小刀，由于受到烈弓的效果，这颗子弹的攻击力可以无限叠加！目前这颗子弹的攻击力为{demon_data[group_id]['atk'] + 1}！\n"
        else:
            demon_data[group_id]['atk'] = 1
            msg += "你装备了小刀，攻击力提升至两点！\n"

    elif item_name == "酒":
        if demon_data[group_id]["add_atk"]:
            demon_data[group_id]['atk'] += 1
            msg += f"你喝下了酒，由于受到烈弓的效果，这颗子弹的攻击力可以无限叠加！目前这颗子弹的攻击力为{demon_data[group_id]['atk'] + 1}！\n"
        else:
            demon_data[group_id]['atk'] = 1
            msg += "你喝下了酒，需不需要一把古锭刀？攻击力提升至两点！\n"

        if demon_data[group_id]['hp'][player_turn] == 1:
            demon_data[group_id]['hp'][player_turn] += 1
            msg += f"酒精振奋了你，hp恢复到2点！\n"

    elif item_name == "啤酒":
        if demon_data[group_id]['clip']:
            removed_bullet = demon_data[group_id]['clip'].pop()
            bullet_type = "实弹" if removed_bullet == 1 else "空弹"
            msg += f"- 你退掉了一颗子弹，这颗子弹是：{bullet_type}\n"
        if not demon_data[group_id]['clip'] or all(b == 0 for b in demon_data[group_id]['clip']):
            demon_data[group_id]['clip'] = load()
            msg += "- 子弹已耗尽，重新装填！\n\n"
            # 游戏轮数+1
            demon_data[group_id]['game_turn'] += 1
            # 获取死斗模式信息
            death_msg, demon_data = death_mode(identity_found, group_id, demon_data)
            msg += death_msg
            
            # 获取刷新道具
            item_msg, demon_data = refersh_item(identity_found, group_id, demon_data)
            msg += item_msg
            
            # 增加弹数消息，优化排版
            msg += '\n- 本局总弹数为'+str(len(demon_data[group_id]['clip']))+'，实弹数为'+str(demon_data[group_id]['clip'].count(1))
            
    elif item_name == "刷新票":
        num_items = len(player_items)
        player_items.clear()
        player_items.extend([get_random_item(identity_found, len(item_dic) - idt_len, user_id) for _ in range(num_items)])
        new_items_names = [item_dic[item] for item in player_items]
        msg += f"你刷新了你的所有道具，新道具为：{', '.join(new_items_names)}\n"

    elif item_name == "手套":
        demon_data[group_id]['clip'] = load()
        msg += f"你重新装填了子弹！新弹夹总数：{len(demon_data[group_id]['clip'])} 实弹数：{demon_data[group_id]['clip'].count(1)}\n"

    elif item_name == "骰子":
        random_hp = random.randint(1, 4)  # 生成一个随机的 hp 值
        if random_hp >= hp_max:
            random_hp = hp_max
        demon_data[group_id]["hp"][player_turn] = random_hp
        msg += "恶魔掷出骰子……骰子掷出了新的hp值：\n"
        msg += f"你的的 hp 已变更成：{random_hp}！\n"
        
    elif item_name == "天秤":
        len_player_items = len(player_items)
        len_opponent_items = len(opponent_items)
        if len_player_items >= len_opponent_items:
            demon_data[group_id]["hp"][opponent_turn] -= 1
            msg += f"天秤的指针开始转动…… 检测到你的道具数量为：{len_player_items}，对面的道具数量为：{len_opponent_items}；\n由于{len_player_items}≥{len_opponent_items}，你成功对对方造成一点伤害！\n对方目前剩余hp为：{demon_data[group_id]['hp'][opponent_turn]}\n"
        else:
            demon_data[group_id]["hp"][player_turn] += 1
            if demon_data[group_id]["hp"][player_turn] >= hp_max:
                demon_data[group_id]["hp"][player_turn] = hp_max
            msg += f"天秤的指针开始转动…… 检测到你的道具数量为：{len_player_items}，对面的道具数量为：{len_opponent_items}；\n由于{len_player_items}<{len_opponent_items}，你回复一点体力（最高恢复至上限！）！\n你目前的hp为：{demon_data[group_id]['hp'][player_turn]}\n"  

    elif item_name == "双转团":
        # 获取原始道具长度
        original_opponent_count = len(opponent_items)

        if len(opponent_items) < item_max:
            opponent_items.append(item_id)  # 只有在对方道具少于 max_item 个时才获得双转团
            msg += f"这件物品太“IDENTITY”了，对方十分感兴趣，所以拿走了这件物品！\n"
        else:
            msg += f"这件物品太“IDENTITY”了，对方十分感兴趣，但是由于道具已满，没办法拿走这件物品，所以把双转团丢了！\n"

        # 获取新的道具列表（双转团转移后的状态）
        now_player_items = demon_data[group_id][f"item_{player_turn}"]
        now_opponent_items = demon_data[group_id][f"item_{opponent_turn}"]
        # 首先 1/4 触发事件
        kou_first = random.randint(1, 4)
        kou_second = 0
        if kou_first == 1:
            kou_second = random.randint(1, 3)
        # 功能1：1/3概率转移随机道具
        if kou_second == 1 and len(now_player_items) > 0:  # 确保玩家还有道具
            random_idx = random.randint(0, len(now_player_items)-1)
            random_item_id = player_items.pop(random_idx)
            random_item_name = item_dic[random_item_id]
            # 检查转移后的道具栏状态
            if len(now_opponent_items) < item_max:
                opponent_items.append(random_item_id)
                msg += f"- 对方还顺手拿走了你的【{random_item_name}】！\n"
                # 1/2扣对面一点血
                if random.randint(1, 2) == 1:
                    demon_data[group_id]["hp"][opponent_turn] -= 1
                    demon_data[group_id]["hp"][player_turn] = current_hp
                    msg += f"但是一不小心摔了一跤，hp-1！\n- 当前对方hp：{demon_data[group_id]["hp"][opponent_turn]}/{hp_max}\n"
            else:
                msg += f"- 对方还顺手拿走了你的【{random_item_name}】，但是由于物品栏已满，他遗憾的把这件道具丢了！\n"

        # 功能2：1/3概率扣自己1点血，1/3加一点血
        elif kou_second == 2:
            demon_data[group_id]["hp"][player_turn] -= 1
            msg += f"你在丢双转团的时候太急了！人一旦急，就会更急，神就不会定，所以你一不小心把血条往左滑了一下，损失了1点hp！\n- 当前自己hp：{demon_data[group_id]["hp"][player_turn]}/{hp_max}\n"
        
        elif kou_second == 3:
            demon_data[group_id]["hp"][player_turn] += 1
            # 无法超过上限
            if demon_data[group_id]["hp"][player_turn] >= hp_max:
                demon_data[group_id]["hp"][player_turn] = hp_max
            msg += f"你在丢双转团的时候太急了！人一旦急，就会更急，神就不会定，所以你一不小心把血条往右滑了一下，增加了1点hp！\n- 当前自己hp：{demon_data[group_id]["hp"][player_turn]}/{hp_max}\n"
        
        # 功能3：对方初始已满时获得徽章
        if original_opponent_count >= item_max:
            #判断是否开辟藏品栏
            if(not 'collections' in user_data[str(user_id)]):
                user_data[str(user_id)]['collections'] = {}
            #是否已经持有藏品"身份徽章"
            #如果没有，则添加
            if(not '身份徽章' in user_data[str(user_id)]['collections']):
                user_data[str(user_id)]['collections']['身份徽章'] = 1
                #写入文件
                save_data(full_path, user_data)
                msg += f"\n你在丢双转团的时候，意外从这个东西身上看到了一个亮闪闪的徽章，上面写着“identity”，你感到十分疑惑，便捡了起来。输入.cp 身份徽章 以查看具体效果\n"
    
    elif item_name == "休养生息":
        if demon_data[group_id]["hp"][opponent_turn] == hp_max:
            demon_data[group_id]["hp"][player_turn] += 1  # 只回 1 点血
            msg += f"休养生息，备战待敌；止兵止战，休养生息。\n对方hp已满，你仅恢复了1点hp。\n"
        else:
            demon_data[group_id]["hp"][player_turn] += 2
            demon_data[group_id]["hp"][opponent_turn] += 1
            msg += f"休养生息，备战待敌；止兵止战，休养生息。\n你恢复了2点hp，对方恢复了1点hp（最高恢复至上限）。\n"
        
        # 校准所有玩家血量不得超过hp上限
        for i in range(len(demon_data[group_id]["hp"])):
            demon_data[group_id]["hp"][i] = min(demon_data[group_id]["hp"][i], demon_data[group_id]["hp_max"])

        # 追加体力信息
        msg += f"\n你的体力为 {demon_data[group_id]['hp'][player_turn]}/{hp_max}\n"
        msg += f"对方的体力为 {demon_data[group_id]['hp'][opponent_turn]}/{hp_max}\n"

    
    elif item_name == "玩具枪":
        randchoice = random.randint(1, 2)
        if randchoice == 1:
            demon_data[group_id]["hp"][opponent_turn] -= 1
            msg += f"你使用了玩具枪，可没想到里面居然是真弹！你对对面造成了一点伤害！\n对方目前剩余hp为：{demon_data[group_id]['hp'][opponent_turn]}\n"    
        else: 
            msg += f"你使用了玩具枪，这确实是一个可以滋水的玩具水枪，无事发生。\n"
    
    elif item_name == "血刃":
        if demon_data[group_id]["hp"][player_turn] == 1:
            player_items.append(item_id)
            msg +=f'你的血量无法支持你使用血刃！\n'
        else:
            randchoice = random.randint(1, 5)
            demon_data[group_id]["hp"][player_turn] -= 1
            new_items = [get_random_item(identity_found, len(item_dic) - idt_len, user_id) for _ in range(2)]
            player_items.extend(new_items)  # 添加新道具
            new_items_names = [item_dic[item] for item in new_items]
            msg += f"你使用了血刃，献祭自己1盎司鲜血，祈祷，获得了道具：{', '.join(new_items_names)}\n你目前剩余hp为：{demon_data[group_id]['hp'][player_turn]}/{hp_max}\n"    
            if randchoice == 5:
                msg += f"\n“血刃？你怎么会在这里？0猎的工资不够你用的吗，还跑过来再就业？”"
                msg += f"\n“唉，工作困难啊……抓玛德琳我太没存在感了，总是被人遗忘，必须要出来再就业了。”\n"
    
    elif item_name == "烈弓":
        demon_data[group_id]['atk'] += 1
        demon_data[group_id]['add_atk'] = True
        msg += f"你使用了烈弓，开始叠花色！烈弓解除了限制，并且伤害+1！现在酒和小刀的伤害可无限叠加！这颗子弹的攻击力可以无限叠加！目前这颗子弹的攻击力为{demon_data[group_id]['atk'] + 1}！\n"
    
    elif item_name == "黑洞":
        if opponent_items:  # 对方有道具
            # 随机选择对方道具
            stolen_idx = random.randint(0, len(opponent_items) - 1)
            stolen_item_id = opponent_items.pop(stolen_idx)
            stolen_item_name = item_dic[stolen_item_id]

            player_items.append(stolen_item_id)  # 抢夺道具

            msg += (f"你召唤出黑洞！\n"
                    f"空间开始剧烈扭曲……\n"
                    f"对方的【{stolen_item_name}】被黑洞吞噬，送进你的背包！\n")
        else:
            # 如果对方没有道具，黑洞会重新回到玩家背包
            player_items.append(item_id)
            msg += "你召唤出黑洞！然而对方空无一物，黑洞在无尽的沉寂中回到了你的手中。\n"

    elif item_name == "金苹果":
        demon_data[group_id]["hp"][player_turn] += 3
        demon_data[group_id]["hcf"] = 1
        demon_data[group_id]["atk"] = 0
        if demon_data[group_id]["hp"][player_turn] >= hp_max:
            demon_data[group_id]["hp"][player_turn] = hp_max
        demon_data[group_id]['turn'] = (player_turn + 1) % len(demon_data[group_id]['pl'])
        msg += f"你吃下了金苹果，因为太美味了，hp回复3点！但是由于过于美味，接下来你要好好回味这种味道，将直接跳过两个回合！不过对方的手铐和禁止卡也不能用了……\n当前hp：{demon_data[group_id]['hp'][player_turn]}/{hp_max}\n"
    
    elif item_name == "铂金草莓":
        demon_data[group_id]["hp"][player_turn] += 1
        hp_max += 1
        demon_data[group_id]["hp_max"] = hp_max
        if demon_data[group_id]["hp"][player_turn] >= hp_max:
            demon_data[group_id]["hp"][player_turn] = hp_max
        msg += f"因为是铂金草莓，所以能做到。吃下铂金草莓后，你的hp回复1点，并且双方的hp上限均+1！要不要尝试去拿一个9dp？\n当前hp：{demon_data[group_id]['hp'][player_turn]}/{hp_max}\n当前hp上限：{hp_max}\n"        
    
    elif item_name == "肾上腺素":
        # 检查血量上限是否为1
        if demon_data[group_id]["hp_max"] <= 1:
            player_items.append(item_id) 
            msg += "你想使用肾上腺素，但是血量上限已经过低，你无法承受这种后果！\n"
        else:
            # 增加使用者的道具
            new_item = get_random_item(identity_found, len(item_dic) - idt_len, user_id)
            player_items.append(new_item)
            new_item_name = item_dic[new_item]
            # 调整hp上限和道具上限
            hp_max -= 1
            item_max += 1
            demon_data[group_id]["hp_max"] = max(1, demon_data[group_id]["hp_max"])  # 血量上限保护锁
            demon_data[group_id]["item_max"] = item_max
            demon_data[group_id]["hp_max"] = hp_max
            new_hp_max = demon_data[group_id]["hp_max"]
            # 校准所有玩家血量不得超过hp上限
            for i in range(len(demon_data[group_id]["hp"])):
                demon_data[group_id]["hp"][i] = min(demon_data[group_id]["hp"][i], demon_data[group_id]["hp_max"])
                    
            msg += (
                f"你注射了肾上腺素！心跳如雷，时间仿佛放慢，力量在血管中沸腾！\n"
                f"- 双方道具上限 +1！\n"
                f"- 你获得了新道具：{new_item_name}\n"
                f"- 当前道具上限：{item_max}\n\n"
                f"然而，一丝生命力被悄然抽离……对手也感到一阵莫名的心悸。\n"
                f"- 双方HP上限 -1！\n"
                f"- 当前HP上限：{hp_max}\n"
            )
    elif item_name == "烈性TNT":
        # 获取当前 HP 和 HP 上限
        current_hp = demon_data[group_id]["hp"][player_turn]
        current_hp_max = demon_data[group_id]["hp_max"]
        # 判定是否禁止使用 TNT
        if current_hp_max <= 1 or current_hp <= 1 or (current_hp_max == 2 and current_hp == 2):
            player_items.append(item_id)
            msg += "你想引爆烈性TNT，但你的血量/血量上限已经过低，这样做无异于自杀！\n"
        else:
            demon_data[group_id]["hp_max"] -= 1
            demon_data[group_id]["hp_max"] = max(1, demon_data[group_id]["hp_max"])  # 确保体力上限不会降到 0，虽然前面有判断了

            # 校准所有玩家血量不得超过hp上限
            for i in range(len(demon_data[group_id]["hp"])):
                demon_data[group_id]["hp"][i] = min(demon_data[group_id]["hp"][i], demon_data[group_id]["hp_max"])
            
            # 扣完上限调整血量后再扣血
            demon_data[group_id]["hp"][player_turn] -= 1
            demon_data[group_id]["hp"][opponent_turn] -= 1

            msg += (
                "你点燃了烈性TNT，产生了巨大的爆炸！\n"
                f"- 双方HP上限 -1！\n- 当前HP上限：{demon_data[group_id]['hp_max']}\n"
                f"- 双方HP -1！\n- 你的HP：{demon_data[group_id]['hp'][player_turn]}/{demon_data[group_id]['hp_max']}\n- 对方HP：{demon_data[group_id]['hp'][opponent_turn]}/{demon_data[group_id]['hp_max']}\n"
            )
            
    elif item_name == "墨镜":
        if len(demon_data[group_id]['clip']) > 1:
            first_bullet = demon_data[group_id]['clip'][0]
            last_bullet = demon_data[group_id]['clip'][-1]
            real_bullet_count = (first_bullet + last_bullet)  # 计算两个位置的实弹数量
            msg += f"你戴上了墨镜，观察枪膛……\n第一颗和最后一颗子弹加起来，有{real_bullet_count}颗实弹！\n"
        else:
            msg += f"枪膛里只剩最后一颗子弹了，是{'实弹' if demon_data[group_id]['clip'][-1] == 1 else '空弹'}！\n"
    else:
        msg += "道具不存在或无法使用！\n"

    next_player_turn = demon_data[group_id]['turn']  # 获取下一位玩家的 turn
    next_player_id = str(demon_data[group_id]["pl"][next_player_turn])  # 下一位玩家的 ID
    msg += "\n- 现在轮到" + MessageSegment.at(str(next_player_id)) + "行动！"
    if demon_data[group_id]['hp'][0] <= 0: 
        winner = demon_data[group_id]['pl'][1]
        end_msg, bar_data, demon_data = handle_game_end(
            group_id=str(group_id),
            winner=winner,
            prefix_msg="- 游戏结束！",
            bar_data=bar_data,
            demon_data=demon_data
        )
        msg += end_msg
    elif demon_data[group_id]['hp'][1] <= 0:
        winner = demon_data[group_id]['pl'][0]
        end_msg, bar_data, demon_data = handle_game_end(
            group_id=str(group_id),
            winner=winner,
            prefix_msg="- 游戏结束！",
            bar_data=bar_data,
            demon_data=demon_data
        )
        msg += end_msg
    save_data(demon_path, demon_data)
    save_data(bar_path, bar_data)
    await prop_demon.finish(msg)

# 查看局势
check = on_fullmatch('/查看局势', permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@check.handle()
async def check_handle(event: GroupMessageEvent):
    group_id = str(event.group_id)
    if await check_timeout(group_id):
        return
    user_id = str(event.user_id)
    demon_data = open_data(demon_path)
    if demon_data[group_id]['start'] == False:
        await check.finish("当前并没有开始任何一句恶魔轮盘du哦！",at_sender = True)
    if user_id not in demon_data[group_id]['pl']:
        await check.finish("只有当前局内玩家能查看局势哦！",at_sender = True)
    # 生成玩家信息
    player0 = str(demon_data[group_id]['pl'][0])
    player1 = str(demon_data[group_id]['pl'][1])
    game_turn = demon_data.get(group_id, {}).get('game_turn')
    hp_max = demon_data.get(group_id, {}).get('hp_max')
    item_max = demon_data.get(group_id, {}).get('item_max')
    hcf = demon_data.get(group_id, {}).get('hcf')
    identity_found = demon_data[group_id]['identity'] 
    # 生成道具信息
    item_0 = ", ".join(item_dic.get(i, "未知道具") for i in demon_data[group_id]['item_0'])
    item_1 = ", ".join(item_dic.get(i, "未知道具") for i in demon_data[group_id]['item_1'])
    # 获取玩家道具信息
    items_0 = demon_data[group_id]['item_0']  # 玩家0道具列表
    items_1 = demon_data[group_id]['item_1']  # 玩家1道具列表
    if len(items_0) == 0:
        item_0 = "你目前没有道具哦！"
    if len(items_1) == 0:
        item_1 = "你目前没有道具哦！"
    # 生成血量信息
    hp0 = demon_data[group_id]['hp'][0]
    hp1 = demon_data[group_id]['hp'][1]
    atk = demon_data[group_id]['atk']
    identity_found = demon_data[group_id]['identity']
    # 步时信息
    elapsed = int(time.time()) - demon_data[group_id]['turn_start_time']
    remaining_seconds = turn_time - elapsed # 计算剩余冷却时间, 全局变量，设定时间（秒）
    remaining_minutes = remaining_seconds // 60  # 剩余分钟数
    remaining_seconds = remaining_seconds % 60  # 剩余秒数
    msg = "- 本局模式："
    if identity_found == 1:
        # death_turn轮以后死斗模式显示
        if identity_found in turn_limit and demon_data[group_id]['game_turn'] > turn_limit[identity_found]:
            msg += '（死斗）'
        msg += "身份模式\n"
    elif identity_found in [2,999]:
        # 1轮以后死斗模式显示
        if identity_found in turn_limit and demon_data[group_id]['game_turn'] > turn_limit[identity_found]:
            msg += '（死斗）'
        msg += "急速模式\n"
    else:
        msg += "正常模式\n"
    msg += f"- 本步剩余时间：{remaining_minutes}分{remaining_seconds}秒\n"
    msg += f"- 当前轮数：{game_turn}\n"
    if hcf != 0:
        msg += f"- 当前对方剩余束缚回合数：{(hcf+1)//2}\n"
    if atk > 0:
        msg += f"- 本颗子弹伤害为：{atk+1}点\n"
    msg += '\n' + MessageSegment.at(player0) + f"\nhp：{hp0}/{hp_max}\n" + f"道具({len(items_0)}/{item_max})：" +f"\n{item_0}\n\n"
    msg += MessageSegment.at(player1) + f"\nhp：{hp1}/{hp_max}\n" + f"道具({len(items_1)}/{item_max})：" +f"\n{item_1}\n\n"
    msg += f"- 总弹数{str(len(demon_data[group_id]['clip']))}，实弹数{str(demon_data[group_id]['clip'].count(1))}\n"
    pid = demon_data[group_id]['pl'][demon_data[group_id]['turn']]
    msg += "- 当前是"+ MessageSegment.at(pid) + "的回合"
    await check.finish(msg)

# 恶魔投降指令：随时投降
demon_surrender = on_command("恶魔投降", permission=GROUP, priority=1, block=True)

@demon_surrender.handle()
async def demon_surrender_handle(event: Event):
    group_id = str(event.group_id)  # 获取群组ID
    player_id = str(event.user_id)  # 获取发出投降指令的玩家ID
    
    demon_data = open_data(demon_path)  # 加载恶魔数据
    bar_data = open_data(bar_path)  # 加载bar数据

    # 判断玩家是否在游戏中
    if demon_data[group_id]['start'] == False:
        await demon_surrender.finish("当前没有进行中的游戏！", at_sender=True)
    # 获取当前游戏的玩家信息
    players = demon_data[group_id]['pl']  # 当前游戏中的两位玩家ID
    if player_id not in players:
        await demon_surrender.finish("你当前不在游戏中，无法投降！", at_sender=True)

    # 确定投降的玩家和获胜的玩家
    loser = player_id
    winner = str(players[1] if loser == players[0] else players[0])
    end_msg, bar_data, demon_data = handle_game_end(
        group_id=str(group_id),
        winner=winner,
        prefix_msg=f"玩家"+MessageSegment.at(loser)+"已投降。\n游戏结束，",
        bar_data=bar_data,
        demon_data=demon_data
    )

    save_data(bar_path, bar_data)
    save_data(demon_path, demon_data)

    # 发送投降结果消息
    await demon_surrender.finish(end_msg)

# 恶魔道具查询功能：展示指定道具的效果
prop_demon_query = on_command("恶魔道具", permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@prop_demon_query.handle()
async def prop_demon_query_handle(bot: Bot, event: Event, arg: Message = CommandArg()):
    # 去除前后空格，处理用户输入
    prop_name = str(arg).strip().lower()

    if prop_name == "": # 没有输入默认all
        prop_name = 'all'
    if prop_name == "all":  # 如果是查询所有道具
        # 构建所有道具的效果信息
        all_effects = "\n".join([f"-【{prop}】：{effect}" for prop, effect in item_effects.items()])
        
        # 构建转发的消息内容
        msg_list = [
            {
                "type": "node",
                "data": {
                    "name": "全部恶魔道具",
                    "uin": event.self_id,
                    "content": all_effects
                }
            }
        ]
        # 转发全部道具效果消息
        await bot.call_api("send_group_forward_msg", group_id=event.group_id, messages=msg_list)
        await prop_demon_query.finish()
    else:  # 查询指定道具
        # 创建一个忽略大小写的映射字典
        lower_to_original = {key.lower(): key for key in item_effects.keys()}

        # 查找原始名称
        original_name = lower_to_original.get(prop_name)

        if original_name:
            # 使用原始名称查询效果
            effect = item_effects[original_name]
            await prop_demon_query.finish(f"\n道具【{original_name}】的效果是：\n{effect}", at_sender=True)
        else:
            # 没找到匹配项
            await prop_demon_query.finish(f"未找到名为【{prop_name}】的道具，请检查道具名称是否正确！", at_sender=True)

# 恶魔帮助
prop_demon_help = on_fullmatch('/恶魔帮助', permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@prop_demon_help.handle()
async def prop_demon_help_handle():
    await prop_demon_help.finish(help_msg,at_sender = True)

# 超时检查
async def check_timeout(group_id):
    demon_data = open_data(demon_path)
    bar_data = open_data(bar_path)
    bots = get_bots()
    if not bots:
        logger.error("没有可用的Bot实例，无法检测play3！")
        return
    bot = list(bots.values())[0]  # 获取第一个 Bot 实例
    # 确保 'demon_data' 和 'group_id' 存在
    # 初始化 group_id 中的游戏数据
    if group_id not in demon_data:
        demon_data[group_id] = demon_default
    elapsed = int(time.time()) - demon_data[group_id]['turn_start_time']
    if elapsed > turn_time:  # 全局变量，设定时间（秒）
        # 判断游戏是否开始
        if demon_data[group_id]['start']:
            # 获取双方玩家
            player_turn = demon_data[group_id]["turn"]
            opponent_turn = (player_turn + 1) % len(demon_data[group_id]['pl'])
            player = demon_data[group_id]['pl'][player_turn]
            non_current_player = demon_data[group_id]['pl'][opponent_turn]
            
            end_msg, bar_data, demon_data = handle_game_end(
                group_id=str(group_id),
                winner=non_current_player,
                prefix_msg="回合超时！当前回合玩家"+MessageSegment.at(player)+"自动判负！",
                bar_data=bar_data,
                demon_data=demon_data
            )
            msg = end_msg
            save_data(demon_path, demon_data)
            save_data(bar_path, bar_data)
            # 发送通知
            await bot.send_group_msg(
                group_id=group_id,
                message=msg
            )
            return True
        else:
            # 判断是否有人
            if len(demon_data[group_id]['pl']) == 1:
                user_data = open_data(full_path)
                player = demon_data[group_id]['pl'][0]
                # 退还刺儿
                user_data[str(player)]['spike'] += 125 
                # 移除玩家游戏状态
                bar_data[player]['game'] = '1'
                bar_data[player]['status'] = 'nothing'
                # 重置游戏
                demon_data[group_id] = demon_default
                save_data(demon_path, demon_data)
                save_data(full_path, user_data)
                save_data(bar_path, bar_data)
                # 发送通知
                await bot.send_group_msg(
                    group_id=group_id,
                    message=f"由于长时间无第二人进入恶魔轮盘du，现已向"+ MessageSegment.at(player) + "返还125刺儿的门票费并重置游戏。"
                )
                return True
    return False

# 30s检测是不是回合超时
@scheduler.scheduled_job("interval", seconds=30)
async def check_all_games():
    demon_data = open_data(demon_path)
    for group_id in list(demon_data.keys()):
        if isinstance(group_id, str) and group_id.isdigit():
            await check_timeout(group_id)


UNO_help_msg = f"""
每次你只能出一张牌，这个牌必须和上一张牌是同一类别或同一颜色(万能牌除外)
当有人出完所有的牌后他将获得胜利
当牌堆被摸空后，剩余牌数最少的人获得胜利
-------------------
以下是特殊牌的介绍：
扭蛋：在打出这张牌后，最后一张牌将变为随机颜色的数字牌
电枪：你需要指定这张牌的颜色，它不必与上一张牌颜色相同，指定完成后将给下家随机数量的随机牌
香蕉：没写，也暂时不会出现在牌堆里
-------------------
以下是道具牌的介绍：
铲子：在打出这张牌后，下家将获得2张随机的牌，暂时不可叠加
冰枪：在打出这张牌后，你的下家本回合无法行动
反转：在打出这张牌后，出牌顺序将以自己为中心翻转
"""

# UNO帮助
UNO_help = on_command('UNO帮助',aliases={"uno帮助"}, permission=GROUP, priority=1, block=True, rule=whitelist_rule)
@UNO_help.handle()
async def UNO_help_handle():
    await UNO_help.finish(UNO_help_msg,at_sender = True)

