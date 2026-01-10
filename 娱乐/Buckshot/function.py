import Buckshot
import OlivaDiceCore
import OlivOS
import os
import random
import json
import time
import requests
import threading

# 恶魔轮盘赌默认数据
def demon_default():
    return {
    'group_id': "",
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
    'ready': False,
    'start': False,
    'identity': 0,
    'demon_coldtime': int(time.time()),
    'turn_start_time': int(time.time())
}
    
def user_default():
    return {
        'identity_status': 0,
        'win_times': 0,
        'total_games': 0,
        'longest_win_streak': 0,
        'current_win_streak': 0,
    }
    
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

# 定义身份模式死斗回合数方便更改
death_turn = 10
pangguang_turn = 3

# 定义每回合的时间
turn_time = 600

# 定义不同状态对应的轮数限制
turn_limit = {
    1: death_turn,  # "死斗模式" 开启的轮数限制
    2: pangguang_turn,    # "膀胱模式" 开启的轮数限制
    999: pangguang_turn    # "跑团专用999模式" 开启的轮数限制
}

# 定义道具效果的字典
item_effects = {
    "桃": "回复1点hp",
    "医疗箱": "回复2点hp，但跳过你的这一回合，并且对方的所有束缚解除！",
    "放大镜": "观察下一颗子弹的种类",
    "眼镜": "观察下两颗子弹的种类，但顺序未知",
    "手铐": "跳过对方下一回合（不可重复使用/与禁止卡一同使用）",
    "禁止卡": "跳过对方下1~2（随机）个回合，对方获得禁止卡（若对方道具已达上限，将不会获得禁止卡）",
    "欲望之盒": "50%抽取一个道具，30%恢复一点血量（若血量达到上限将赠与一个本轮实弹耗尽前无视道具上限的桃），20%对对方造成一点伤害",
    "无中生有": "抽取两个道具，然后跳过回合，对方若有束缚，束缚的回合-1！并且无中生有生成的道具直到本轮实弹耗尽前可以超出上限（本轮实弹耗尽后超出上限的道具会消失）！",
    "小刀": "伤害变为2（注：同时使用多个小刀或酒会导致浪费！）",
    "酒": "伤害变为2，同时若hp等于1时，回复1hp（注：同时使用多个小刀或酒会导致浪费！）",
    "啤酒": "退掉下一发子弹（若退掉的是最后一发子弹，进行道具的刷新）",
    "刷新票": "使用后，重新抽取和剩余道具数量相等的道具",
    "手套": "重新换弹，不进行道具刷新",
    "骰子": "你的hp变为1到4的随机值",
    "墨镜": "观察第一颗和最后一颗子弹的种类，但顺序未知",
    "双转团": "（该道具为“身份”模式专属道具）把这个道具转移到对方道具栏里，若对方道具已达上限则丢弃本道具；另外还有概率触发特殊效果？可能会掉血，可能会回血，可能会送给对方道具……",
    "天秤": "（该道具为“身份”模式专属道具）如果你的道具数量≥对方道具数量，你对对方造成一点伤害；你的道具数量<对方道具数量，你回一点血",
    "休养生息": "（该道具为“身份”模式专属道具）自己的hp恢复2，对方的hp恢复1，不跳回合；若对面为满血，则只回一点体力。",
    "玩具枪": "（该道具为“身份”模式专属道具）1/2的概率无事发生，1/2的概率对对面造成1点伤害",
    "烈弓": "（该道具为“身份”模式专属道具）使用烈弓后，下一发子弹伤害+1，且伤害类道具（小刀、酒、烈弓）的加伤效果可以无限叠加！",
    "血刃": "（该道具为“身份”模式专属道具）可以扣除自己1点hp，获得两个道具！并且获得的道具直到本轮实弹耗尽前可以超出上限（本轮实弹耗尽后超出上限的道具会消失）",
    "黑洞": "（该道具为“身份”模式专属道具）召唤出黑洞，随机夺取对方的任意一个道具！如果对方没有道具，黑洞将在沉寂中回到你的身边。",
    "金苹果": "（该道具为“身份”模式专属道具）金苹果可以让你回复3点hp！但是作为代价你会跳过接下来的两个回合！不过对面的手铐和禁止卡也似乎不能使用了……",
    "铂金草莓": "（该道具为“身份”模式专属道具）因为是铂金草莓，所以能做到！自己回复1点hp，并且双方各加1点hp上限！",
    "肾上腺素": "（该道具为“身份”模式专属道具）双方的hp上限-1，道具上限+1，并且使用者获得一个新道具！如果你们的hp上限为1，无法使用该道具！",
    "烈性TNT": "（该道具为“身份”模式专属道具）双方的hp上限-1，hp各-1！注意，是先扣hp上限，然后再扣hp！另外，如果使用后会自杀，则无法使用该道具！",
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

    # 生成候选列表（按照权重扩展）
    valid_items = [i for i in weights if weights[i] > 0]
    item_choices = [i for i in valid_items for _ in range(weights[i])]

    return random.choice(item_choices)

# 特殊扣血逻辑
def death_mode_damage(action_type: int, demon_data: dict, group_id: str):
    """
    处理死斗模式特殊扣血逻辑
    :param action_type: 0=开枪自己, 1=开枪对方, 2=使用道具
    :param demon_data: 游戏数据字典
    :param group_id: 群组ID
    :return: (消息内容, 更新后的demon_data)
    """
    msg = ""
    # identity_found = demon_data['identity']
    
    # # 检查是否处于死斗模式
    # if identity_found not == 2:
    #     return "", demon_data
    
    # current_turn = demon_data['turn']
    # player_idx = current_turn
    # opponent_idx = (current_turn + 1) % 2
    # hp = demon_data['hp']
    # hp_max = demon_data['hp_max']
    # # damage = random.randint(1, 2)
    # damage = 1
    
    # # 开枪自己 (action_type=0)
    # if action_type == 0 and random.randint(1, 4) == 1:
    #     original_hp = hp[opponent_idx]
    #     hp[opponent_idx] = max(1, hp[opponent_idx] - damage)
    #     msg = (
    #         f"\n- 你开枪自己的冲击波震伤了对方，造成{damage}点伤害！"
    #         f"\n- 对方HP: {original_hp} → {hp[opponent_idx]}（最低为1）\n"
    #     )
    
    # # 开枪对方 (action_type=1)
    # elif action_type == 1 and random.randint(1, 4) == 1:
    #     original_hp = hp[player_idx]
    #     hp[player_idx] = max(1, hp[player_idx] - damage)
    #     msg = (
    #         f"\n- 你的攻击过于激进，受到子弹冲击波的{damage}点反噬伤害！"
    #         f"\n- 自己HP: {original_hp} → {hp[player_idx]}（最低为1）\n"
    #     )
    
    # # 使用道具 (action_type=2) - 道具特殊处理
    # elif action_type == 2:
    #     # 啤酒移除最后一颗实弹的强制扣血
    #     if (demon_data.get('last_action') == 'beer' and 
    #         demon_data.get('last_bullet') == 1 and
    #         all(b == 0 for b in demon_data['clip'])):
            
    #         original_hp_player = hp[player_idx]
    #         original_hp_opponent = hp[opponent_idx]
    #         hp[player_idx] = max(1, hp[player_idx] - 1)
    #         hp[opponent_idx] = max(1, hp[opponent_idx] - 1)
    #         msg = (
    #             "\n- 最后一颗实弹被清除！"
    #             f"\n- 自己HP: {original_hp_player} → {hp[player_idx]}（最低为1）"
    #             f"\n- 对方HP: {original_hp_opponent} → {hp[opponent_idx]}（最低为1）"
    #             f"\n- 实弹卸下的冲击波震得双方各掉1点HP！"
    #         )
    
    # # 更新数据
    # demon_data['hp'] = hp
    return msg, demon_data

# 上弹函数
def load(identity_found):
    """上弹，1代表实弹，0代表空弹"""
    # # 根据identity_found值决定弹夹容量和实弹数量
    # if identity_found == 2:
    #     clip_size = random.randint(3, 8)  # 弹夹容量3-8
    #     # 确保至少2个实弹，最多不超过弹夹容量-1（至少留一个空弹）
    #     bullets = random.randint(2, clip_size // 2 + 1)  # 随机生成实弹数量
    # else:
    #     clip_size = random.randint(2, 8)  # 默认弹夹容量2-8
    #     if clip_size == 2:
    #         # 如果总弹数为2，强制设置一个实弹
    #         clip = [0, 1]
    #         random.shuffle(clip)  # 随机打乱弹夹顺序
    #         return clip
    #     else:
    #         bullets = random.randint(1, clip_size // 2 + 1)  # 随机生成实弹数量
    
    # 定义实弹数量及其概率（1发40%，2发30%，3发10%，4发10%，5发10%）
    bullet_options = [1, 2, 3, 4, 5]
    bullet_weights = [0.4, 0.3, 0.1, 0.1, 0.1]
    
    # 使用加权随机选择实弹数量
    bullets = random.choices(bullet_options, weights=bullet_weights, k=1)[0]
    
    # 计算弹夹最小容量(实弹*2-1)，最大为8
    min_clip_size = bullets * 2 - 1
    clip_size = random.randint(min_clip_size, 8) if min_clip_size <= 8 else 8
    
    # 特殊情况处理：如果clip_size为1，固定为1实弹1空弹
    if clip_size == 1:
        clip = [0, 1]
        random.shuffle(clip)
        return clip
    
    # 生成弹夹
    clip = [0] * clip_size
    bullet_positions = random.sample(range(clip_size), bullets)  # 随机生成实弹位置
    for pos in bullet_positions:
        clip[pos] = 1
    return clip

# # 以下为旧上弹逻辑，暂时保留
# def load(identity_found):
#     """上弹，1代表实弹，0代表空弹"""
#     # # 根据identity_found值决定弹夹容量和实弹数量
#     # if identity_found == 2:
#     #     clip_size = random.randint(3, 8)  # 弹夹容量3-8
#     #     # 确保至少2个实弹，最多不超过弹夹容量-1（至少留一个空弹）
#     #     bullets = random.randint(2, clip_size // 2 + 1)  # 随机生成实弹数量
#     # else:
#     #     clip_size = random.randint(2, 8)  # 默认弹夹容量2-8
#     #     if clip_size == 2:
#     #         # 如果总弹数为2，强制设置一个实弹
#     #         clip = [0, 1]
#     #         random.shuffle(clip)  # 随机打乱弹夹顺序
#     #         return clip
#     #     else:
#     #         bullets = random.randint(1, clip_size // 2 + 1)  # 随机生成实弹数量
#     clip_size = random.randint(2, 8)  # 默认弹夹容量2-8
#     if clip_size == 2:
#         # 如果总弹数为2，强制设置一个实弹
#         clip = [0, 1]
#         random.shuffle(clip)  # 随机打乱弹夹顺序
#         return clip
#     else:
#         bullets = random.randint(1, clip_size // 2 + 1)  # 随机生成实弹数量
    
#     # 生成弹夹
#     clip = [0] * clip_size
#     bullet_positions = random.sample(range(clip_size), bullets)  # 确定实弹位置
#     for pos in bullet_positions:
#         clip[pos] = 1
#     return clip

def get_buckshot_data_path():
    """获取恶魔轮盘赌插件数据存储路径"""
    buckshot_data_path = os.path.join('plugin', 'data', 'Buckshot')
    if not os.path.exists(buckshot_data_path):
        os.makedirs(buckshot_data_path)
    return buckshot_data_path


def get_redirected_bot_hash(bot_hash: str) -> str:
    """遵循 OlivaDiceCore 主从账号链接：从账号读写主账号目录。"""
    try:
        master = OlivaDiceCore.console.getMasterBotHash(bot_hash)
        if master:
            return str(master)
    except Exception:
        pass
    return bot_hash

def get_demon_file_path(bot_hash, group_hash):
    """获取群组恶魔轮盘赌路径"""
    buckshot_data_path = get_buckshot_data_path()
    bot_hash = get_redirected_bot_hash(str(bot_hash))
    bot_path = os.path.join(buckshot_data_path, bot_hash, 'group')
    if not os.path.exists(bot_path):
        os.makedirs(bot_path)
    return os.path.join(bot_path, f"{group_hash}.json")

def get_user_path(bot_hash, user_hash):
    """获取用户路径"""
    buckshot_data_path = get_buckshot_data_path()
    bot_hash = get_redirected_bot_hash(str(bot_hash))
    bot_path = os.path.join(buckshot_data_path, bot_hash, 'user')
    if not os.path.exists(bot_path):
        os.makedirs(bot_path)
    return os.path.join(bot_path, f"{user_hash}.json")
def load_group_data(bot_hash, group_hash):
    """加载群组数据"""
    file_path = get_demon_file_path(bot_hash, group_hash)
    default_data = demon_default()

    redirected_bot_hash = get_redirected_bot_hash(str(bot_hash))
    if redirected_bot_hash != str(bot_hash) and not os.path.exists(file_path):
        buckshot_data_path = get_buckshot_data_path()
        legacy_bot_path = os.path.join(buckshot_data_path, str(bot_hash), 'group')
        legacy_path = os.path.join(legacy_bot_path, f"{group_hash}.json")
        if os.path.exists(legacy_path):
            file_path = legacy_path
    
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保数据格式正确
                if isinstance(data, dict) and all(key in data for key in default_data.keys()):
                    return data
        except (IOError, json.JSONDecodeError) as e:
            print(f"加载群组数据时出错: {e}")
            pass
    
    return default_data

def save_group_data(bot_hash, group_hash, data):
    """保存群组数据"""
    file_path = get_demon_file_path(bot_hash, group_hash)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass
    
def load_user_data(bot_hash, user_hash):
    """加载用户数据"""
    file_path = get_user_path(bot_hash, user_hash)
    default_data = user_default()

    redirected_bot_hash = get_redirected_bot_hash(str(bot_hash))
    if redirected_bot_hash != str(bot_hash) and not os.path.exists(file_path):
        buckshot_data_path = get_buckshot_data_path()
        legacy_bot_path = os.path.join(buckshot_data_path, str(bot_hash), 'user')
        legacy_path = os.path.join(legacy_bot_path, f"{user_hash}.json")
        if os.path.exists(legacy_path):
            file_path = legacy_path
    
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保数据格式正确
                if isinstance(data, dict) and all(key in data for key in default_data.keys()):
                    return data
        except (IOError, json.JSONDecodeError) as e:
            # 记录日志以便调试
            print(f"加载用户数据时出错: {e}")
            pass
        
    return default_data

def save_user_data(bot_hash, user_hash, data):
    """保存用户数据"""
    file_path = get_user_path(bot_hash, user_hash)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def get_nickname(plugin_event, user_id, tmp_hagID = None):
    """获取用户昵称"""
    try:
        # 如果是 QQ 频道平台,优先使用人物卡名称
        if plugin_event.platform['platform'] == 'qqGuild':
            tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(user_id, plugin_event.platform['platform'])
            tmp_pcName = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
            if tmp_pcName:
                return tmp_pcName
            # 如果没有人物卡名称,返回默认格式
            return f"用户{tmp_pcHash}"
        # 其他平台保持原有逻辑
        pid_nickname = OlivaDiceCore.userConfig.getUserConfigByKey(
            userId=user_id,
            userType='user',
            platform=plugin_event.platform['platform'],
            userConfigKey='userName',
            botHash=plugin_event.bot_info.hash,
            default=f"用户{user_id}"
        )
        if pid_nickname != f"用户{user_id}" or pid_nickname != "用户":
            return pid_nickname
        tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(user_id, plugin_event.platform['platform'])
        tmp_pcName = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
        if tmp_pcName:
            return tmp_pcName
        plres = plugin_event.get_stranger_info(user_id)
        if plres['active']:
            pid_nickname = plres['data']['name']
            if pid_nickname != f"用户{user_id}" or pid_nickname != "用户":
                if pid_nickname == "用户":
                    return f"用户{user_id}"
                return pid_nickname
            else:
                return f"用户{user_id}"
        return f"用户{user_id}"
    except:
        return f"用户{user_id}"
    
def handle_game_end(
    plugin_event,
    group_id: str,
    winner: str,
    prefix_msg: str,
    demon_data: dict
):
    """处理游戏结束的公共逻辑"""
    group_hash = group_id
    if group_hash in Buckshot.msgReply.active_game_monitors:
        Buckshot.msgReply.active_game_monitors[group_hash]['stop_event'].set()
        # del Buckshot.msgReply.active_game_monitors[group_hash] # 可以在线程自己结束时清理
    players = demon_data['pl']
    player0 = str(players[0])
    player1 = str(players[1])
    
    player0_hash = OlivaDiceCore.userConfig.getUserHash(
                        player0,
                        'user',
                        plugin_event.platform['platform']
                    )
    player1_hash = OlivaDiceCore.userConfig.getUserHash(
                        player1,
                        'user',
                        plugin_event.platform['platform']
                    )
    
    winner_nick_name = get_nickname(plugin_event, winner, group_id)
    
    player0_data = load_user_data(plugin_event.bot_info.hash, player0_hash)
    player1_data = load_user_data(plugin_event.bot_info.hash, player1_hash)
    
    player0_data['total_games'] += 1
    player1_data['total_games'] += 1
    
    # 初始化连胜数据
    winner_streak = 0
    
    # 更新连胜数据
    if str(winner) == str(player0):
        player0_data['win_times'] += 1
        player0_data['current_win_streak'] += 1
        player0_data['longest_win_streak'] = max(
            player0_data['longest_win_streak'], 
            player0_data['current_win_streak']
        )
        # 获取胜利方连胜
        winner_streak = player0_data['current_win_streak']
        # 重置失败方的连胜
        player1_data['current_win_streak'] = 0
        
    elif str(winner) == str(player1):
        player1_data['win_times'] += 1
        player1_data['current_win_streak'] += 1
        player1_data['longest_win_streak'] = max(
            player1_data['longest_win_streak'], 
            player1_data['current_win_streak']
        )
        # 获取胜利方连胜
        winner_streak = player1_data['current_win_streak']
        # 重置失败方的连胜
        player0_data['current_win_streak'] = 0

    # 统一保存数据
    save_user_data(plugin_event.bot_info.hash, player0_hash, player0_data)
    save_user_data(plugin_event.bot_info.hash, player1_hash, player1_data)
        
    # 构建基础消息
    msg = prefix_msg + f"恭喜[{winner_nick_name}]胜利！当前连胜局数：{winner_streak}"
    
    # 重置游戏数据
    demon_data = demon_default()
    demon_data['demon_coldtime'] = int(time.time()) + 60
    
    return msg, demon_data

# 死斗函数
def death_mode(plugin_event, identity_found, group_id, demon_data):
    '''判断是否开启死斗模式：根据不同的状态和轮数进行血量上限扣减，保存状态后最后返回msg'''
    player0 = str(demon_data['pl'][0])
    player1 = str(demon_data['pl'][1])
    p0_nick_name = get_nickname(plugin_event, player0, group_id)
    p1_nick_name = get_nickname(plugin_event, player1, group_id)
    msg = ''
    
    if identity_found in turn_limit and demon_data['game_turn'] > turn_limit[identity_found]:
        msg += f'\n- 轮数大于{turn_limit[identity_found]}，死斗模式开启！\n'
        
        # HP 上限减少
        if identity_found in [1,2] and demon_data["hp_max"] > 1:
            demon_data["hp_max"] -= 1
            new_hp_max = demon_data["hp_max"]
            msg += f'- {new_hp_max+1}>1，扣1点hp上限，当前hp上限：{new_hp_max}\n'
            
            # 校准所有玩家血量不得超过 hp 上限
            for i in range(len(demon_data["hp"])):
                demon_data["hp"][i] = min(demon_data["hp"][i], demon_data["hp_max"])

        # 额外扣除 1 点道具上限，并随机删除 1-2 个道具
        if identity_found in [1,2]:
            if demon_data["item_max"] > 6:
                demon_data["item_max"] -= 1  # 扣 1 点道具上限（最低仍为 6）
                new_item_max = demon_data["item_max"]
                msg += f'- {new_item_max+1}>6，扣1点道具上限，当前道具上限：{demon_data["item_max"]}\n'

            # remove_random = random.randint(1, 2)
            remove_random = 1
            
            # 计算可删除的道具数量
            remove_count0 = min(remove_random, len(demon_data['item_0'])) if demon_data['item_0'] else 0
            remove_count1 = min(remove_random, len(demon_data['item_1'])) if demon_data['item_1'] else 0

            # 随机选择要删除的道具
            removed_items_0 = random.sample(demon_data['item_0'], remove_count0) if remove_count0 else []
            removed_items_1 = random.sample(demon_data['item_1'], remove_count1) if remove_count1 else []

            # 逐个删除选定的道具实例
            for item in removed_items_0:
                demon_data['item_0'].remove(item)

            for item in removed_items_1:
                demon_data['item_1'].remove(item) 

            # 记录被删除的道具名称
            removed_names_0 = [item_dic.get(i, "未知道具") for i in removed_items_0]
            removed_names_1 = [item_dic.get(i, "未知道具") for i in removed_items_1]

            # 记录删除的信息
            if removed_names_0:
                msg += f'- [{p0_nick_name}]失去了{remove_count0}个道具：{"、".join(removed_names_0)}！\n'
            if removed_names_1:
                msg += f'- [{p1_nick_name}]失去了{remove_count1}个道具：{"、".join(removed_names_1)}！\n'
    
    return msg, demon_data

# 生成道具信息，每四个道具加入一个换行符
def format_items(items, item_dict):
    item_list = [item_dict.get(i, "未知道具") for i in items]
    formatted_items = []
    for i in range(0, len(item_list), 4):
        chunk = item_list[i:i+4]
        formatted_items.append(", ".join(chunk))
    return "\n".join(formatted_items)

# 计算随机函数
def calculate_interval(game_turn_add, identity_found):
    # 设置默认值
    lower_bound = 1
    upper_bound = 3
        
    # 根据不同的模式计算道具刷新上下限
    # 普通模式
    if identity_found == 0:
        lower_bound = 1 + game_turn_add
        upper_bound = 3 + game_turn_add

    # 身份模式
    elif identity_found == 1:
        lower_bound = 1 + game_turn_add*2
        upper_bound = 3 + game_turn_add*2
        
    # 极速模式
    elif identity_found == 2:
        lower_bound = 3 + game_turn_add
        upper_bound = 5 + game_turn_add
    
    return lower_bound, upper_bound

# 刷新道具函数
def refersh_item(plugin_event, identity_found, group_id, demon_data):
    idt_len = len(item_dic2)
    # add_max = 0
    # pangguang_add = 0
    game_turn_add = 0
    msg = ''

    # 查看是否开局
    game_turn_cal = demon_data["game_turn"]
    # 查看是否开局
    if game_turn_cal == 1:
        game_turn_add = 1

    # 从函数中获取道具刷新上下限
    lower, upper = calculate_interval(game_turn_add, identity_found)
    player0 = str(demon_data['pl'][0])
    player1 = str(demon_data['pl'][1])
    p0_nick_name = get_nickname(plugin_event, player0, group_id)
    p1_nick_name = get_nickname(plugin_event, player1, group_id)
    hp0 = demon_data["hp"][0]
    hp1 = demon_data["hp"][1]
    # 重新获取hp_max
    hp_max = demon_data.get('hp_max')
    item_max = demon_data.get('item_max')
    for i in range(random.randint(lower, upper)):
        demon_data['item_0'].append(get_random_item(identity_found, len(item_dic) - idt_len, player0))
        demon_data['item_1'].append(get_random_item(identity_found, len(item_dic) - idt_len, player1))
    # 检查并限制道具数量上限为max
    demon_data['item_0'] = demon_data['item_0'][:item_max]  # 截取前max个道具
    demon_data['item_1'] = demon_data['item_1'][:item_max]  # 截取前max个道具
    # 生成道具信息
    item_0 = format_items(demon_data['item_0'], item_dic)
    item_1 = format_items(demon_data['item_1'], item_dic)

    # 获取玩家道具信息
    items_0 = demon_data['item_0']  # 玩家0道具列表
    items_1 = demon_data['item_1']  # 玩家1道具列表
    if len(items_0) == 0:
        item_0 = "你目前没有道具哦！"
    if len(items_1) == 0:
        item_1 = "你目前没有道具哦！"
    msg += f"[{p0_nick_name}]\nhp：{hp0}/{hp_max}\n" + f"道具({len(items_0)}/{item_max})：" +f"\n{item_0}\n\n"
    msg += f"[{p1_nick_name}]\nhp：{hp1}/{hp_max}\n" + f"道具({len(items_1)}/{item_max})：" +f"\n{item_1}\n"

    return msg, demon_data

# 开枪函数
def shoot(plugin_event, user_id, stp, group_id, args):
    demon_data = load_group_data(plugin_event.bot_info.hash, group_id)
    hp_max = demon_data.get('hp_max')
    item_max = demon_data.get('item_max')
    clip = demon_data.get('clip')
    hp = demon_data.get('hp')
    pl = demon_data.get('turn')
    player0 = str(demon_data['pl'][0])
    player1 = str(demon_data['pl'][1])
    identity_found = demon_data['identity'] 
    add_max = 0
    pangguang_add = 0
    # 身份模式开了就更新dlc
    idt_len = len(item_dic2)
    if identity_found == 1:
        idt_len = 0
        add_max += 1
    elif identity_found == 2:
        idt_len = 0
        add_max += 1
        pangguang_add += 2
    msg = ""
    if clip[-1] == 1:
        atk = demon_data['atk']
        hp[pl-stp] -= 1 + atk
        demon_data['atk'] = 0
        demon_data['add_atk'] = False
        if atk != 0:
            msg += f"- 这颗子弹的伤害为……{atk+1}点！\n"
        if atk in [3, 4]:
            msg += '- 癫狂屠戮！\n'
        if atk >= 5:
            msg += '- 无双，万军取首！\n'
        msg += f'- 你开枪了，子弹 *【击中了】* {args}！\n- {args}剩余hp：{str(hp[pl-stp])}/{hp_max}\n'
    else:
        demon_data['atk'] = 0
        demon_data['add_atk'] = False
        msg += f'- 你开枪了，子弹未击中{args}！\n- {args}剩余hp：{str(hp[pl-stp])}/{hp_max}\n'
    del clip[-1]
    
    if len(clip) == 0 or clip.count(1) == 0:
        msg += '- 子弹用尽，重新换弹，道具更新！\n'
        # 游戏轮数+1
        demon_data['game_turn'] += 1
        msg += f'- 当前轮数：{demon_data["game_turn"]}\n'
        # 调用死斗模式伤害计算 (stp=0是开枪自己，1是开枪对方)
        damage_msg, demon_data = death_mode_damage(stp, demon_data, group_id)
        msg += damage_msg
        # 获取死斗模式信息
        death_msg, demon_data = death_mode(plugin_event, identity_found, group_id, demon_data)
        msg += death_msg
        # 增加换行，优化排版
        msg += "\n"
        clip = load(identity_found)
        # 获取刷新道具
        item_msg, demon_data = refersh_item(plugin_event, identity_found, group_id, demon_data)
        msg += item_msg
        # 增加换行，优化排版
        msg += "\n"
    
    if demon_data['hcf'] < 0 and stp != 0:
        demon_data['hcf'] = 0
        out_pl = demon_data['pl'][demon_data['turn']-1]
        out_nickname = get_nickname(plugin_event, out_pl, group_id)
        msg += f"- [{out_nickname}]已挣脱束缚！\n"
    if demon_data['hcf'] == 0 or stp == 0:
        pl += stp
        pl = pl%2   
    else:
        demon_data['hcf'] -= 2
    hcf = demon_data.get('hcf')
    if hcf != 0:
        msg += f"- 当前对方剩余束缚回合数：{(hcf+1)//2}\n"
    demon_data['turn'] = pl
    demon_data['clip'] = clip
    demon_data['hp'] = hp
    # 刷新时间
    demon_data['turn_start_time'] = int(time.time())
    # 初始化turn_msg
    turn_msg = ''
    if demon_data['hp'][0] <= 0: 
        winner = demon_data['pl'][1]
        end_msg, demon_data = handle_game_end(
            plugin_event,
            group_id=str(group_id),
            winner=winner,
            prefix_msg="- 游戏结束！",
            demon_data=demon_data
        )
        msg += end_msg
    elif demon_data['hp'][1] <= 0:
        winner = demon_data['pl'][0]
        end_msg, demon_data = handle_game_end(
            plugin_event,
            group_id=str(group_id),
            winner=winner,
            prefix_msg="- 游戏结束！",
            demon_data=demon_data
        )
        msg += end_msg
    else:
        pid = demon_data['pl'][demon_data['turn']]
        pid_nickname = get_nickname(plugin_event, pid, group_id)
        msg += '- 本局总弹数为'+str(len(demon_data['clip']))+'，实弹数为'+str(demon_data['clip'].count(1))
        turn_msg = f"当前是[{pid_nickname}]的回合"
    save_group_data(plugin_event.bot_info.hash, group_id, demon_data)
    return msg, turn_msg
    
# 超时检查
# 新增：超时监控线程的执行函数
def game_timeout_monitor(plugin_event, Proc, bot_hash, group_hash, stop_event, hagID):
    """
    游戏超时监控线程，能处理“等待中”和“游戏中”两种状态。
    """
    # 引用需要用到的函数
    load_group_data = Buckshot.function.load_group_data
    save_group_data = Buckshot.function.save_group_data
    handle_game_end = Buckshot.function.handle_game_end
    get_nickname = Buckshot.function.get_nickname
    demon_default = Buckshot.function.demon_default
    sendMsgByEvent = Buckshot.function.sendMsgByEvent
    turn_time = Buckshot.function.turn_time

    while not stop_event.wait(1.0):  # 每秒检查一次，直到 stop_event 被设置
        try:
            demon_data = load_group_data(bot_hash, group_hash)
            players = demon_data.get('pl', [])
            is_started = demon_data.get('start', False)

            # 状态一：等待超时 (游戏未开始，且只有1名玩家)
            if not is_started and len(players) == 1:
                elapsed = int(time.time()) - demon_data.get('turn_start_time', int(time.time()))
                
                if elapsed > turn_time:
                    player_id = players[0]
                    pl_nickname = get_nickname(plugin_event, player_id, hagID)
                    
                    # 准备超时消息
                    msg = f"等待其他玩家加入超时！玩家[{pl_nickname}]自动退出游戏，游戏已重置。"
                    
                    # 获取原始的 group_id 用于发送消息
                    target_group_id = plugin_event.data.group_id
                    # 重置游戏数据并保存
                    save_group_data(bot_hash, group_hash, demon_default())
                    
                    Proc.log(2, f"[{group_hash}]群组游戏因等待其他玩家加入超时被强制结束。")
                    if target_group_id:
                        sendMsgByEvent(plugin_event, msg, target_group_id, 'group')
                    break # 任务完成，退出线程

            # 状态二：游戏中回合超时 (游戏已开始)
            elif is_started:
                elapsed = int(time.time()) - demon_data.get('turn_start_time', int(time.time()))
                if elapsed > turn_time:
                    player_turn = demon_data["turn"]
                    loser_id = players[player_turn]
                    winner_id = players[(player_turn + 1) % len(players)]
                    loser_nickname = get_nickname(plugin_event, loser_id, hagID)
                    
                    # 调用游戏结束处理函数，它会处理数据并返回最终消息
                    end_msg, final_demon_data = handle_game_end(
                        plugin_event,
                        group_id=str(group_hash),
                        winner=winner_id,
                        prefix_msg=f"回合操作超时！当前回合玩家[{loser_nickname}]被自动判负！\n",
                        demon_data=demon_data
                    )
                    
                    # 保存游戏结束后的数据
                    save_group_data(bot_hash, group_hash, final_demon_data)
                    
                    Proc.log(2, f"[{group_hash}]群组游戏因玩家超时被强制结束。")
                    
                    # 发送游戏结束消息
                    target_group_id = plugin_event.data.group_id
                    if target_group_id:
                         sendMsgByEvent(plugin_event, end_msg, target_group_id, 'group')
                    
                    break # 任务完成，退出线程
            
            # 状态三：无效状态 (例如玩家退出了), 线程也应退出
            elif not is_started and len(players) != 1:
                break

        except Exception as e:
            # 记录异常，防止线程意外崩溃
            Proc.log(2, f"[线程意外崩溃], 错误: {str(e)}")
            break
            
    # 线程结束时，确保从全局监控字典中移除自己，释放资源
    if group_hash in Buckshot.msgReply.active_game_monitors:
        del Buckshot.msgReply.active_game_monitors[group_hash]

def try_resume_monitor_for_group(plugin_event, Proc, bot_hash, group_hash, hagID):
    """
    在玩家触发命令时检查并（若合适）为指定群组创建游戏超时监控线程。

    行为：
    - 如果存档不存在或没有进行中的游戏则返回 True。
    - 如果游戏已超时，则执行对应的超时结束逻辑并返回 False（不创建线程）。
    - 如果游戏未超时且当前没有监控线程，则创建并启动监控线程，返回 True。
    """
    active_game_monitors = Buckshot.msgReply.active_game_monitors
    game_timeout_monitor = Buckshot.function.game_timeout_monitor

    try:
        # 读取存档数据
        demon_data = load_group_data(bot_hash, group_hash)
        # 如果存档为空或没有玩家，直接返回
        players = demon_data.get('pl', [])
        if not players:
            return True

        is_started = demon_data.get('start', False)
        is_ready = demon_data.get('ready', False)
        turn_time_local = turn_time
        elapsed = int(time.time()) - demon_data.get('turn_start_time', int(time.time()))

        # 情况一：等待超时（未开始，且仅有1名玩家）
        if not is_started and len(players) == 1:
            if elapsed > turn_time_local:
                player_id = players[0]
                pl_nickname = get_nickname(plugin_event, player_id, hagID)
                msg = f"等待其他玩家加入超时！玩家[{pl_nickname}]自动退出游戏，游戏已重置。"
                save_group_data(bot_hash, group_hash, demon_default())
                Proc.log(2, f"[{group_hash}] 群组游戏因等待其他玩家加入超时被重置（触发恢复检查）。")
                target_group_id = getattr(plugin_event.data, 'group_id', None)
                if target_group_id:
                    sendMsgByEvent(plugin_event, msg, target_group_id, 'group')
                return False
            else:
                # 未超时：创建监控线程
                if group_hash in active_game_monitors:
                    return True
                stop_event = threading.Event()
                monitor_thread = threading.Thread(
                    target=game_timeout_monitor,
                    args=(plugin_event, Proc, bot_hash, group_hash, stop_event, hagID)
                )
                active_game_monitors[group_hash] = {
                    'thread': monitor_thread,
                    'stop_event': stop_event
                }
                monitor_thread.daemon = True
                monitor_thread.start()
                Proc.log(2, f"[Buckshot] 为群组 {group_hash} 启动超时监控（等待状态，未超时）。")
                return True

        # 情况二：游戏中回合超时（游戏已开始）
        if is_started:
            if elapsed > turn_time_local:
                player_turn = demon_data.get('turn', 0)
                # 保护性判断
                if player_turn >= len(players):
                    player_turn = player_turn % max(1, len(players))
                loser_id = players[player_turn]
                winner_id = players[(player_turn + 1) % len(players)]
                loser_nickname = get_nickname(plugin_event, loser_id, hagID)

                end_msg, final_demon_data = handle_game_end(
                    plugin_event,
                    group_id=str(group_hash),
                    winner=winner_id,
                    prefix_msg=f"回合操作超时！当前回合玩家[{loser_nickname}]被自动判负！\n",
                    demon_data=demon_data
                )
                save_group_data(bot_hash, group_hash, final_demon_data)
                Proc.log(2, f"[{group_hash}] 群组游戏因玩家超时被强制结束（触发恢复检查）。")
                target_group_id = getattr(plugin_event.data, 'group_id', None)
                if target_group_id:
                    sendMsgByEvent(plugin_event, end_msg, target_group_id, 'group')
                return False
            else:
                # 游戏未超时，若尚无监控则创建
                if group_hash in active_game_monitors:
                    return True
                stop_event = threading.Event()
                monitor_thread = threading.Thread(
                    target=game_timeout_monitor,
                    args=(plugin_event, Proc, bot_hash, group_hash, stop_event, hagID)
                )
                active_game_monitors[group_hash] = {
                    'thread': monitor_thread,
                    'stop_event': stop_event
                }
                monitor_thread.daemon = True
                monitor_thread.start()
                Proc.log(2, f"[Buckshot] 为群组 {group_hash} 启动超时监控（游戏中，未超时）。")
                return True

        # 其余情况（既没开始也不处于等待单人状态）不创建监控
        return False
    except Exception as e:
        Proc.log(2, f"[Buckshot] 在尝试为群组 {group_hash} 恢复监控时出错: {str(e)}")
        return False

def replyMsg(plugin_event, message, at_user = False):
    host_id = None
    group_id = None
    user_id = None
    at_user_msg = ""
    tmp_name = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]['strBotName']
    tmp_self_id = plugin_event.bot_info.id
    if 'host_id' in plugin_event.data.__dict__:
        host_id = plugin_event.data.host_id
    if 'group_id' in plugin_event.data.__dict__:
        group_id = plugin_event.data.group_id
    if 'user_id' in plugin_event.data.__dict__:
        user_id = plugin_event.data.user_id
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
    if at_user:
        at_para = OlivOS.messageAPI.PARA.at(str(user_id))
        at_user_msg = at_para.get_string_by_key('CQ')
    return OlivaDiceCore.msgReply.pluginReply(plugin_event, f'{at_user_msg} ' + str(message))

def sendMsgByEvent(plugin_event, message, target_id, target_type, host_id = None):
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
    return OlivaDiceCore.msgReply.pluginSend(plugin_event, target_type, target_id, message, host_id = host_id)

def send_forward_text(plugin_event, user_ids, message, at_users=True, additional_msg="", is_forward=False):
    """
    发送合并转发消息，如果不是QQ平台则正常发送
    :param plugin_event: 插件事件对象
    :param user_ids: 用户ID列表，用于@用户
    :param message: 要发送的消息内容
    :param at_users: 是否@用户
    :param additional_msg: 附加消息
    """
    # QQ 转发开关（来自自定义回复 dictStrCustom）：'0'=开启合并转发；'1'=非转发；其他=按0处理
    is_forward_effective = is_forward
    if plugin_event.platform.get('platform') == 'qq':
        try:
            mode_raw = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash].get('strBSQQForwardDetect', '0')
            mode = int(str(mode_raw).strip())
        except Exception:
            mode = 0
        if mode == 1:
            is_forward_effective = False
        else:
            is_forward_effective = True

    # 检查平台，如果不是QQ平台或未启用转发则正常发送
    if plugin_event.platform.get('platform') != 'qq' or not is_forward_effective:
        # 构建@用户的消息
        at_msg = ""
        if at_users and user_ids:
            for user_id in user_ids:
                at_para = OlivOS.messageAPI.PARA.at(str(user_id))
                at_msg += at_para.get_string_by_key('CQ') + " "
        
        # 发送完整消息
        full_msg = at_msg + additional_msg + "\n" + message if at_msg else additional_msg + "\n" + message
        replyMsg(plugin_event, full_msg, False)
        return
    
    # QQ平台处理合并转发
    server_config = get_account_config(plugin_event)
    if server_config is None:
        # 如果无法获取服务器配置，也正常发送
        at_msg = ""
        if at_users and user_ids:
            for user_id in user_ids:
                at_para = OlivOS.messageAPI.PARA.at(str(user_id))
                at_msg += at_para.get_string_by_key('CQ') + " "
        
        full_msg = at_msg + additional_msg + "\n" + message if at_msg else additional_msg + "\n" + message
        replyMsg(plugin_event, full_msg, False)
        return
    
    # 首先发送@消息
    if at_users and user_ids:
        at_msg = ""
        for user_id in user_ids:
            at_para = OlivOS.messageAPI.PARA.at(str(user_id))
            at_msg += at_para.get_string_by_key('CQ') + " "
        if at_msg:
            replyMsg(plugin_event, at_msg + additional_msg, False)
    
    # 然后发送合并转发消息
    messages = []
    bot_name = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]['strBotName']
    
    # 直接创建转发节点
    messages.append(create_forward_node(plugin_event.bot_info.id, bot_name, message))
    
    # 发送合并转发
    if plugin_event.plugin_info['func_type'] == 'group_message':
        api_url = f"http://{server_config['host'].replace('http://', '').replace('https://', '')}:{server_config['port']}/send_group_forward_msg"
        payload = {
            "group_id": plugin_event.data.group_id,
            "messages": messages
        }
    else:
        api_url = f"http://{server_config['host'].replace('http://', '').replace('https://', '')}:{server_config['port']}/send_private_forward_msg"
        payload = {
            "user_id": plugin_event.data.user_id,
            "messages": messages
        }
    
    headers = {
        "Authorization": f"Bearer {server_config['access_token']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            api_url,
            data=json.dumps(payload),
            headers=headers
        )
    except Exception:
        # 如果转发失败，正常发送消息
        replyMsg(plugin_event, message, False)

def get_account_config(plugin_event):
    """从 conf/account.json 读取账号配置"""
    config_path = os.path.join('conf', 'account.json')
    try:
        if not os.path.exists(config_path):
            return None
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        if 'account' not in config_data or not config_data['account']:
            return None
        
        current_bot_id = str(plugin_event.bot_info.id)
        for account_config in config_data['account']:
            if 'id' in account_config and str(account_config['id']) == current_bot_id:
                if 'server' not in account_config:
                    return None
                    
                server_config = account_config['server']
                required_fields = ['host', 'port', 'access_token']
                for field in required_fields:
                    if field not in server_config:
                        return None
                return server_config
        return None
    except Exception:
        return None

def create_forward_node(user_id, nickname, content):
    """创建转发消息节点"""
    return {
        "type": "node",
        "data": {
            "user_id": str(user_id),
            "nickname": nickname,
            "content": content
        }
    }