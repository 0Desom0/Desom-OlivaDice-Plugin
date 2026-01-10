# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore，写命令请跳转到第183行。
'''

import OlivOS
import Buckshot
import OlivaDiceCore
import random
import threading

import copy
import time

active_game_monitors = {}

def unity_init(plugin_event, Proc):
    # 这里是插件初始化，通常用于加载配置等
    pass

def data_init(plugin_event, Proc):
    Buckshot.function.get_buckshot_data_path()
    # 这里是数据初始化，通常用于加载数据等
    Buckshot.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])


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

    replyMsg = Buckshot.function.replyMsg
    isMatchWordStart = OlivaDiceCore.msgReply.isMatchWordStart
    getMatchWordStartRight = OlivaDiceCore.msgReply.getMatchWordStartRight
    skipSpaceStart = OlivaDiceCore.msgReply.skipSpaceStart
    skipToRight = OlivaDiceCore.msgReply.skipToRight
    msgIsCommand = OlivaDiceCore.msgReply.msgIsCommand
    send_forward_text = Buckshot.function.send_forward_text

    tmp_at_str = OlivOS.messageAPI.PARA.at(plugin_event.base_info['self_id']).CQ()
    tmp_id_str = str(plugin_event.base_info['self_id'])
    tmp_at_str_sub = None
    tmp_id_str_sub = None
    if 'sub_self_id' in plugin_event.data.extend:
        if plugin_event.data.extend['sub_self_id'] != None:
            tmp_at_str_sub = OlivOS.messageAPI.PARA.at(plugin_event.data.extend['sub_self_id']).CQ()
            tmp_id_str_sub = str(plugin_event.data.extend['sub_self_id'])
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
        '''命令部分'''
        # 引入 function 里的函数
        load_group_data = Buckshot.function.load_group_data
        save_group_data = Buckshot.function.save_group_data
        load_user_data = Buckshot.function.load_user_data
        save_user_data = Buckshot.function.save_user_data
        get_buckshot_data_path = Buckshot.function.get_buckshot_data_path
        get_demon_file_path = Buckshot.function.get_demon_file_path
        get_user_path = Buckshot.function.get_user_path
        handle_game_end = Buckshot.function.handle_game_end
        death_mode = Buckshot.function.death_mode
        format_items = Buckshot.function.format_items
        calculate_interval = Buckshot.function.calculate_interval
        refersh_item = Buckshot.function.refersh_item
        get_random_item = Buckshot.function.get_random_item
        death_mode_damage = Buckshot.function.death_mode_damage
        shoot = Buckshot.function.shoot
        item_dic = Buckshot.function.item_dic
        item_dic1 = Buckshot.function.item_dic1
        item_dic2 = Buckshot.function.item_dic2
        get_nickname = Buckshot.function.get_nickname
        load = Buckshot.function.load
        turn_time = Buckshot.function.turn_time
        turn_limit = Buckshot.function.turn_limit
        death_turn = Buckshot.function.death_turn
        pangguang_turn = Buckshot.function.pangguang_turn
        item_effects = Buckshot.function.item_effects
        game_timeout_monitor = Buckshot.function.game_timeout_monitor
        try_resume_monitor_for_group = Buckshot.function.try_resume_monitor_for_group
        # 获取hash
        bot_hash = plugin_event.bot_info.hash
        user_hash = OlivaDiceCore.userConfig.getUserHash(
                        plugin_event.data.user_id,
                        'user',
                        plugin_event.platform['platform']
                    )
        group_hash = OlivaDiceCore.userConfig.getUserHash(
                        tmp_hagID,
                        'group',
                        plugin_event.platform['platform']
                    )
        group_id = group_hash
        if not isMatchWordStart(tmp_reast_str, ['bs'], isCommand=True):
            return
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['bs'])
        tmp_reast_str = skipSpaceStart(tmp_reast_str)
        if isMatchWordStart(tmp_reast_str, ['加入赌局','参加赌局'], isCommand = True):
            if not flag_is_from_group:
                return
            isEnd = try_resume_monitor_for_group(plugin_event, Proc, bot_hash, group_hash, tmp_hagID)
            if not isEnd:
                return
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['加入赌局','参加赌局'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            user_id = str(plugin_event.data.user_id)
            # 获取当前时间戳
            current_time = int(time.time())
            demon_data = load_group_data(bot_hash, group_hash)
            # 确保 'demon_data' 和 'group_id' 存在
            # 检查是否有冷却时间，如果没有设置，默认为 0
            demon_coldtime = demon_data.get('demon_coldtime', 0)
    
            # 检查全局冷却时间
            if current_time < demon_coldtime:
                remaining_time = demon_coldtime - current_time
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，恶魔轮盘处于冷却中，请晚点再来吧！\n剩余冷却时间：{remaining_time // 60}分钟{remaining_time % 60}秒。"
                replyMsg(plugin_event, msg, True)
                return
    
            # 检查游戏是否已经开始，如果已经开始，禁止其他玩家加入
            if demon_data['start']:
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，游戏已开始，暂无法加入，请等待游戏结束。"
                replyMsg(plugin_event, msg, True)
                return
    
            # 判断玩家是否为第一位或第二位加入
            if len(demon_data['pl']) == 0:
                # 第一位玩家加入
                demon_data['ready'] = True # 进入准备状态
                demon_data['pl'].append(user_id)
                demon_data['group_id'] = str(plugin_event.data.group_id)
                demon_data['turn_start_time'] = current_time # 记录等待开始时间
                # 写入数据
                save_group_data(bot_hash, group_hash, demon_data)
                
                # 启动超时监控线程
                if group_id not in active_game_monitors:
                    Proc.log(2, f"[{group_hash}]群组游戏已启动，开始超时监控。")
                    stop_event = threading.Event()
                    monitor_thread = threading.Thread(
                        target=game_timeout_monitor,
                        # 将关键信息传入线程，使其可以独立工作
                        args=(plugin_event, Proc, bot_hash, group_id, stop_event, tmp_hagID)
                    )
                    active_game_monitors[group_id] = {
                        'thread': monitor_thread,
                        'stop_event': stop_event
                    }
                    monitor_thread.daemon = True # 设置为守护线程，主程序退出时它也退出
                    monitor_thread.start()
    
                msg = f"玩家[{get_nickname(plugin_event, user_id, tmp_hagID)}]加入了游戏，等待第二位玩家加入。"
                replyMsg(plugin_event, msg, True)
    
            elif len(demon_data['pl']) == 1:
                # 第二位玩家加入前检查是否已经加入
                if str(user_id) in demon_data['pl']:
                    msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，你已经是第一位玩家了，无需重复加入！\n请等待第二位玩家加入。"
                    replyMsg(plugin_event, msg, True)
                    return
    
                # 第二位玩家加入，初始化完整的游戏
                demon_data['pl'].append(user_id)
                demon_data['ready'] = False # 取消准备状态
                demon_data['start'] = True # 游戏正式开始
                demon_data['group_id'] = str(plugin_event.data.group_id)
                add_max = 0
                # 膀胱加成
                pangguang_add = 0
                # 获取两个玩家的身份状态
                # 获取两个玩家的ID
                player_ids = [str(demon_data['pl'][i]) for i in range(2)]

                # 转换成 user_hash 并获取 identity_status
                identity_status_list = [
                    load_user_data(
                        bot_hash,
                        OlivaDiceCore.userConfig.getUserHash(
                            player_id,
                            'user', 
                            plugin_event.platform['platform']
                        )
                    ).get("identity_status", 0)
                    for player_id in player_ids
                ]
                
                # 如果两个玩家的身份状态不同
                if identity_status_list[0] != identity_status_list[1]:
                    identity_found = random.choice(identity_status_list)  # 随机选择一个状态，50% 概率选择其中一个
                else:
                    identity_found = identity_status_list[0]  # 如果两个状态相同，直接选择该状态
                # 更新身份状态
                demon_data['identity'] = identity_found
                idt_len = len(item_dic2)
                if identity_found == 1:
                    add_max = 2
                    idt_len = 0
                elif identity_found == 2:
                    add_max = 2
                    pangguang_add = 2
                    idt_len = 0
                # 设置玩家血量，随机生成血量值(放在上面后面好改)
                hp = random.randint(3 + max(int(add_max*2-1), 0) + max(int(pangguang_add*2-1), 0), 6+add_max*2 + pangguang_add*2)
                demon_data['hp'] = [hp, hp]
                # 设定轮数
                demon_data['game_turn'] = 1
                # 设定血量上限
                demon_data['hp_max'] = 6 + add_max*2 + pangguang_add*3
                # 设定道具上限
                demon_data['item_max'] = 6 + add_max + pangguang_add
                # 加载弹夹状态
                demon_data['clip'] = load(identity_found)
                # 设定无限叠加攻击默认值
                demon_data['add_atk'] = False
                # 随机决定先手玩家
                demon_data['turn_start_time'] = int(time.time())
                demon_data['turn'] = random.randint(0, 1)
                # 随机生成道具并分配给两位玩家
                player0 = str(demon_data['pl'][0])
                player1 = str(demon_data['pl'][1])
                item_msg, demon_data = refersh_item(plugin_event, identity_found, group_id, demon_data)
                # 发送初始化消息
                msg = "恶魔轮盘，开局!\n"
                msg += "- 本局模式："
                if identity_found == 1:
                    msg += "身份模式"
                elif identity_found == 2:
                    msg += "急速模式"
                else:
                    msg += "正常模式"

                msg += "\n\n"
                msg += item_msg
                msg += f"\n- 总弹数{str(len(demon_data['clip']))}，实弹数{str(demon_data['clip'].count(1))}"
                pid = demon_data['pl'][demon_data['turn']]
                pid_nickname = get_nickname(plugin_event, pid, tmp_hagID)
                turn_msg = f"当前是[{pid_nickname}]的回合"
                save_group_data(bot_hash, group_hash, demon_data)
                player_ids = [player0, player1]
                send_forward_text(plugin_event, player_ids, msg, True, f'\n{turn_msg}')
            else:
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，游戏已开始，无法加入！"
                replyMsg(plugin_event, msg, True)
                return
        elif isMatchWordStart(tmp_reast_str, ['开枪','射击'], isCommand = True):
            if not flag_is_from_group:
                return
            isEnd = try_resume_monitor_for_group(plugin_event, Proc, bot_hash, group_hash, tmp_hagID)
            if not isEnd:
                return
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['开枪','射击'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            user_id = str(plugin_event.data.user_id)
            args = str(tmp_reast_str).strip()
            demon_data = load_group_data(bot_hash, group_hash)
            player0 = str(demon_data['pl'][0])
            player1 = str(demon_data['pl'][1])
            player_turn = demon_data["turn"]
            msg = ''
            turn_msg = ''
            if demon_data["start"] == False:
                msg = "恶魔轮盘尚未开始！"
                replyMsg(plugin_event, msg, True)
                return
                
            if user_id not in demon_data['pl']:
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，你不在本局恶魔轮盘中！"
                replyMsg(plugin_event, msg, True)
                return
            
            if demon_data["pl"][player_turn] != user_id:
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，现在不是你的回合，请等待对方操作！"
                replyMsg(plugin_event, msg, True)
                return
            
            if args == "自己":
                stp = 0
                # 调用开枪函数
                msg, turn_msg = shoot(plugin_event, user_id, stp, group_hash, args)
                player_ids = [player0, player1]
                send_forward_text(plugin_event, player_ids, msg, True, f"\n{turn_msg}")
                return
            elif args == "对方":
                stp = 1
                # 调用开枪函数
                msg, turn_msg = shoot(plugin_event, user_id, stp, group_hash, args)
                player_ids = [player0, player1]
                send_forward_text(plugin_event, player_ids, msg, True, f"\n{turn_msg}")
                return
            else:
                msg = "指令错误！请输入[.开枪 自己]或者[.开枪 对方]来开枪哦！"
                replyMsg(plugin_event, msg, True)
                return
        elif isMatchWordStart(tmp_reast_str, ['使用道具'], isCommand = True):
            if not flag_is_from_group:
                return
            isEnd = try_resume_monitor_for_group(plugin_event, Proc, bot_hash, group_hash, tmp_hagID)
            if not isEnd:
                return
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['使用道具'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            user_id = str(plugin_event.data.user_id)
            args = tmp_reast_str.strip()
            demon_data = load_group_data(bot_hash, group_hash)
            player_turn = demon_data["turn"]
            player0 = str(demon_data['pl'][0])
            player1 = str(demon_data['pl'][1])
            add_max = 0
            pangguang_add = 0
            if demon_data["start"] == False:
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，恶魔轮盘尚未开始！"
                replyMsg(plugin_event, msg, True)
                return

            if user_id not in demon_data['pl']:
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，你不是本局玩家，只有当前局内玩家才能行动哦！"
                replyMsg(plugin_event, msg, True)
                return

            if demon_data["pl"][player_turn] != user_id:
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，现在不是你的回合，请等待[{get_nickname(plugin_event, demon_data['pl'][player_turn])}]行动！"
                replyMsg(plugin_event, msg, True)
                return
            identity_found = demon_data['identity'] 
            # 身份模式开了就更新dlc
            idt_len = len(item_dic2)
            if identity_found == 1:
                idt_len = 0
                add_max += 1
            elif identity_found == 2:
                idt_len = 0
                add_max += 1
                pangguang_add += 2

            # 提取数据
            player_items = demon_data[f"item_{player_turn}"]
            opponent_turn = (player_turn + 1) % len(demon_data['pl'])
            opponent_items = demon_data[f"item_{opponent_turn}"]

            # 道具名称匹配（忽略大小写）
            args_lower = args.lower()
            item_dic_lower = {key: value.lower() for key, value in item_dic.items()}  # 生成一个忽略大小写的字典

            if args_lower not in item_dic_lower.values():  # 检查输入的名称是否存在于 item_dic（忽略大小写）
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，你输入的道具[{args}]不存在，请确认后再使用！"
                replyMsg(plugin_event, msg, True)
                return

            # 查找玩家的道具中是否存在该道具
            try:
                # 遍历玩家的道具ID，找到第一个匹配的道具名称（忽略大小写）
                item_idx = next(i for i, item_id in enumerate(player_items) if item_dic[item_id].lower() == args_lower)
            except StopIteration:
                msg = f"[{get_nickname(plugin_event, user_id, tmp_hagID)}]，你并没有道具[{args}]，请确认后再使用！"
                replyMsg(plugin_event, msg, True)
                return

            # 提取数据
            item_id = player_items[item_idx]
            item_name = item_dic[item_id]
            hp_max = demon_data.get('hp_max')
            item_max = demon_data.get('item_max')
            pid_nickname = get_nickname(plugin_event, str(demon_data["pl"][player_turn]), tmp_hagID)
            msg = f"[{pid_nickname}]使用了道具：{item_name}\n\n"
            player_items.pop(item_idx)
            demon_data['turn_start_time'] = int(time.time()) # 更新回合时间

            if item_name == "桃":
                demon_data['hp'][player_turn] += 1
                if demon_data['hp'][player_turn] >= hp_max:
                    demon_data['hp'][player_turn] = hp_max
                msg += f"你的hp回复1点（最高恢复至体力上限）。\n当前hp：{demon_data['hp'][player_turn]}/{hp_max}\n"

            elif item_name == "医疗箱":
                demon_data['hp'][player_turn] += 2
                demon_data["hcf"] = 0
                demon_data["atk"] = 0
                if demon_data['hp'][player_turn] >= hp_max:
                    demon_data['hp'][player_turn] = hp_max
                demon_data['turn'] = (player_turn + 1) % len(demon_data['pl'])
                msg += f"你的hp回复2点（最高恢复至体力上限），但是代价是跳过本回合，而且对方的束缚将自动挣脱！\n当前hp：{demon_data['hp'][player_turn]}/{hp_max}\n"

            elif item_name == "放大镜":
                next_bullet = "实弹" if demon_data['clip'][-1] == 1 else "空弹"
                msg += f"下一颗子弹是：{next_bullet}！\n"

            elif item_name == "眼镜":
                if len(demon_data['clip']) > 1:
                    count_real_bullets = demon_data['clip'][-2:].count(1)
                    msg += f"前两颗子弹中有 {count_real_bullets} 颗实弹。\n"
                else:
                    msg += f"枪膛里只剩最后一颗子弹了，是{'实弹' if demon_data['clip'][-1] == 1 else '空弹'}！\n"

            elif item_name == "手铐":
                if demon_data['hcf'] == 0:
                    demon_data['hcf'] = 1
                    msg += "你成功拷住了对方！\n"
                else:
                    player_items.append(item_id)
                    msg += "不可使用！对方仍处于束缚状态！\n"

            elif item_name == "禁止卡":
                # 获取对方的回合编号
                if demon_data['hcf'] == 0:
                    add_turn = (random.randint(0,1)*2)
                    if add_turn == 0:
                        skip_turn = 1
                    else:
                        skip_turn = 2
                    demon_data['hcf'] = 1 + add_turn
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
                    demon_data['hp'][player_turn] += 1
                    if demon_data['hp'][player_turn] >= hp_max + 1:
                        demon_data['hp'][player_turn] = hp_max
                        player_items.append(1)
                        msg += f"但是由于你的体力已经到达上限，这点体力将转化为桃送给你。这个桃可暂时突破道具上限！\n"
                    msg += f"当前hp：{demon_data['hp'][player_turn]}/{hp_max}\n"
                elif randchoice <= 10:
                    demon_data['hp'][opponent_turn] -= 1
                    msg += f"你打开了欲望之盒，对对面造成了一点伤害！\n对方目前剩余hp为：{demon_data['hp'][opponent_turn]}\n"

            elif item_name == "无中生有":
                new_items = [get_random_item(identity_found, len(item_dic) - idt_len, user_id) for _ in range(2)]
                player_items.extend(new_items)  # 添加新道具
                new_items_names = [item_dic[item] for item in new_items]
                if demon_data["hcf"] <= 0:
                    demon_data["atk"] = 0
                    demon_data["hcf"] = 0
                    demon_data['turn'] = (player_turn + 1) % len(demon_data['pl'])
                    msg += f"你使用了无中生有，获得了道具：{', '.join(new_items_names)}\n代价是跳过了自己的回合!\n"
                elif demon_data["hcf"] >= 1:
                    demon_data["hcf"] -= 2
                    msg += f"你使用了无中生有，获得了道具：{', '.join(new_items_names)}\n代价是对方的束缚的回合将-1！\n"

            elif item_name == "小刀":
                if demon_data["add_atk"]:
                    demon_data['atk'] += 1
                    msg += f"你装备了小刀，由于受到烈弓的效果，这颗子弹的攻击力可以无限叠加！目前这颗子弹的攻击力为{demon_data['atk'] + 1}！\n"
                else:
                    demon_data['atk'] = 1
                    msg += "你装备了小刀，攻击力提升至两点！\n"

            elif item_name == "酒":
                if demon_data["add_atk"]:
                    demon_data['atk'] += 1
                    msg += f"你喝下了酒，由于受到烈弓的效果，这颗子弹的攻击力可以无限叠加！目前这颗子弹的攻击力为{demon_data['atk'] + 1}！\n"
                else:
                    demon_data['atk'] = 1
                    msg += "你喝下了酒，需不需要一把古锭刀？攻击力提升至两点！\n"

                if demon_data['hp'][player_turn] == 1:
                    demon_data['hp'][player_turn] += 1
                    msg += f"酒精振奋了你，hp恢复到2点！\n"

            elif item_name == "啤酒":
                if demon_data['clip']:
                    removed_bullet = demon_data['clip'].pop()
                    bullet_type = "实弹" if removed_bullet == 1 else "空弹"

                    msg += f"- 你退掉了一颗子弹，这颗子弹是：{bullet_type}\n"

                if not demon_data['clip'] or all(b == 0 for b in demon_data['clip']):
                    demon_data['clip'] = load(identity_found)
                    msg += "- 子弹已耗尽，重新装填！\n"
                    # 游戏轮数+1
                    demon_data['game_turn'] += 1
                    # 调用死斗模式伤害计算 (action_type=2)
                    damage_msg, demon_data = death_mode_damage(2, demon_data, group_id)
                    msg += damage_msg
                    # 获取死斗模式信息
                    death_msg, demon_data = death_mode(plugin_event, identity_found, group_id, demon_data)
                    msg += death_msg
                    msg += "\n"

                    # 获取刷新道具
                    item_msg, demon_data = refersh_item(plugin_event, identity_found, group_id, demon_data)
                    msg += item_msg

                    # 增加弹数消息，优化排版
                    msg += '\n- 本局总弹数为'+str(len(demon_data['clip']))+'，实弹数为'+str(demon_data['clip'].count(1))

            elif item_name == "刷新票":
                num_items = len(player_items)
                player_items.clear()
                player_items.extend([get_random_item(identity_found, len(item_dic) - idt_len, user_id) for _ in range(num_items)])
                new_items_names = [item_dic[item] for item in player_items]
                if len(new_items_names) == 0:
                    msg += f"哎呀！你在只有刷新票的情况用了刷新票，现在一个新道具都没有！\n"
                else:
                    msg += f"你刷新了你的所有道具，新道具为：{', '.join(new_items_names)}\n"

            elif item_name == "手套":
                demon_data['clip'] = load(identity_found)
                msg += f"你重新装填了子弹！新弹夹总数：{len(demon_data['clip'])} 实弹数：{demon_data['clip'].count(1)}\n"

            elif item_name == "骰子":
                random_hp = random.randint(1, 4)  # 生成一个随机的 hp 值
                if random_hp >= hp_max:
                    random_hp = hp_max
                demon_data['hp'][player_turn] = random_hp
                msg += "恶魔掷出骰子……骰子掷出了新的hp值：\n"
                msg += f"你的的 hp 已变更成：{random_hp}！\n"

            elif item_name == "天秤":
                len_player_items = len(player_items)
                len_opponent_items = len(opponent_items)
                if len_player_items >= len_opponent_items:
                    demon_data['hp'][opponent_turn] -= 1
                    msg += f"天秤的指针开始转动…… 检测到你的道具数量为：{len_player_items}，对面的道具数量为：{len_opponent_items}；\n由于{len_player_items}≥{len_opponent_items}，你成功对对方造成一点伤害！\n对方目前剩余hp为：{demon_data['hp'][opponent_turn]}\n"
                else:
                    demon_data['hp'][player_turn] += 1
                    if demon_data['hp'][player_turn] >= hp_max:
                        demon_data['hp'][player_turn] = hp_max
                    msg += f"天秤的指针开始转动…… 检测到你的道具数量为：{len_player_items}，对面的道具数量为：{len_opponent_items}；\n由于{len_player_items}<{len_opponent_items}，你回复一点体力（最高恢复至上限！）！\n你目前的hp为：{demon_data['hp'][player_turn]}\n"  

            elif item_name == "双转团":
                # 获取原始道具长度
                original_opponent_count = len(opponent_items)

                if len(opponent_items) < item_max:
                    opponent_items.append(item_id)  # 只有在对方道具少于 max_item 个时才获得双转团
                    msg += f"这件物品太“IDENTITY”了，对方十分感兴趣，所以拿走了这件物品！\n"
                else:
                    msg += f"这件物品太“IDENTITY”了，对方十分感兴趣，但是由于道具已满，没办法拿走这件物品，所以把双转团丢了！\n"

                # 获取新的道具列表（双转团转移后的状态）
                now_player_items = demon_data[f"item_{player_turn}"]
                now_opponent_items = demon_data[f"item_{opponent_turn}"]
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
                            demon_data['hp'][opponent_turn] -= 1
                            demon_data['hp'][player_turn] = current_hp
                            msg += f"但是一不小心摔了一跤，hp-1！\n- 当前对方hp：{demon_data['hp'][opponent_turn]}/{hp_max}\n"
                    else:
                        msg += f"- 对方还顺手拿走了你的【{random_item_name}】，但是由于物品栏已满，他遗憾的把这件道具丢了！\n"

                # 功能2：1/3概率扣自己1点血，1/3加一点血
                elif kou_second == 2:
                    demon_data['hp'][player_turn] -= 1
                    msg += f"你在丢双转团的时候太急了！人一旦急，就会更急，神就不会定，所以你一不小心把血条往左滑了一下，损失了1点hp！\n- 当前自己hp：{demon_data['hp'][player_turn]}/{hp_max}\n"

                elif kou_second == 3:
                    demon_data['hp'][player_turn] += 1
                    # 无法超过上限
                    if demon_data['hp'][player_turn] >= hp_max:
                        demon_data['hp'][player_turn] = hp_max
                    msg += f"你在丢双转团的时候太急了！人一旦急，就会更急，神就不会定，所以你一不小心把血条往右滑了一下，增加了1点hp！\n- 当前自己hp：{demon_data['hp'][player_turn]}/{hp_max}\n"

            elif item_name == "休养生息":
                if demon_data['hp'][opponent_turn] == hp_max:
                    demon_data['hp'][player_turn] += 1  # 只回 1 点血
                    msg += f"休养生息，备战待敌；止兵止战，休养生息。\n对方hp已满，你仅恢复了1点hp。\n"
                else:
                    demon_data['hp'][player_turn] += 2
                    demon_data['hp'][opponent_turn] += 1
                    msg += f"休养生息，备战待敌；止兵止战，休养生息。\n你恢复了2点hp，对方恢复了1点hp（最高恢复至上限）。\n"

                # 校准所有玩家血量不得超过hp上限
                for i in range(len(demon_data['hp'])):
                    demon_data['hp'][i] = min(demon_data['hp'][i], demon_data["hp_max"])

                # 追加体力信息
                msg += f"\n你的体力为 {demon_data['hp'][player_turn]}/{hp_max}\n"
                msg += f"对方的体力为 {demon_data['hp'][opponent_turn]}/{hp_max}\n"


            elif item_name == "玩具枪":
                randchoice = random.randint(1, 2)
                if randchoice == 1:
                    demon_data['hp'][opponent_turn] -= 1
                    msg += f"你使用了玩具枪，可没想到里面居然是真弹！你对对面造成了一点伤害！\n对方目前剩余hp为：{demon_data['hp'][opponent_turn]}\n"    
                else: 
                    msg += f"你使用了玩具枪，这确实是一个可以滋水的玩具水枪，无事发生。\n"

            elif item_name == "血刃":
                if demon_data['hp'][player_turn] == 1:
                    player_items.append(item_id)
                    msg +=f'你的血量无法支持你使用血刃！\n'
                else:
                    randchoice = random.randint(1, 5)
                    demon_data['hp'][player_turn] -= 1
                    new_items = [get_random_item(identity_found, len(item_dic) - idt_len, user_id) for _ in range(2)]
                    player_items.extend(new_items)  # 添加新道具
                    new_items_names = [item_dic[item] for item in new_items]
                    msg += f"你使用了血刃，献祭自己1盎司鲜血，祈祷，获得了道具：{', '.join(new_items_names)}\n你目前剩余hp为：{demon_data['hp'][player_turn]}/{hp_max}\n"    
                    if randchoice == 5:
                        msg += f"\n“血刃？你怎么会在这里？隔壁Desom-fu开发的抓玛德琳的工资不够你用的吗，还跑过来再就业？”"
                        msg += f"\n“唉，工作困难啊……抓玛德琳我太没存在感了，总是被人遗忘，必须要出来再就业了。”\n"

            elif item_name == "烈弓":
                demon_data['atk'] += 1
                demon_data['add_atk'] = True
                msg += f"你使用了烈弓，开始叠花色！烈弓解除了限制，并且伤害+1！现在酒和小刀的伤害可无限叠加！这颗子弹的攻击力可以无限叠加！目前这颗子弹的攻击力为{demon_data['atk'] + 1}！\n"

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
                demon_data['hp'][player_turn] += 3
                demon_data["hcf"] = 1
                demon_data["atk"] = 0
                if demon_data['hp'][player_turn] >= hp_max:
                    demon_data['hp'][player_turn] = hp_max
                demon_data['turn'] = (player_turn + 1) % len(demon_data['pl'])
                msg += f"你吃下了金苹果，因为太美味了，hp回复3点！但是由于过于美味，接下来你要好好回味这种味道，将直接跳过两个回合！不过对方的手铐和禁止卡也不能用了……\n当前hp：{demon_data['hp'][player_turn]}/{hp_max}\n"

            elif item_name == "铂金草莓":
                demon_data['hp'][player_turn] += 1
                hp_max += 1
                demon_data["hp_max"] = hp_max
                if demon_data['hp'][player_turn] >= hp_max:
                    demon_data['hp'][player_turn] = hp_max
                msg += f"因为是铂金草莓，所以能做到。吃下铂金草莓后，你的hp回复1点，并且双方的hp上限均+1！要不要尝试去拿一个9dp？\n当前hp：{demon_data['hp'][player_turn]}/{hp_max}\n当前hp上限：{hp_max}\n"        

            elif item_name == "肾上腺素":
                # 检查血量上限是否为1
                if demon_data["hp_max"] <= 1:
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
                    demon_data["hp_max"] = max(1, demon_data["hp_max"])  # 血量上限保护锁
                    demon_data["item_max"] = item_max
                    demon_data["hp_max"] = hp_max
                    new_hp_max = demon_data["hp_max"]
                    # 校准所有玩家血量不得超过hp上限
                    for i in range(len(demon_data['hp'])):
                        demon_data['hp'][i] = min(demon_data['hp'][i], demon_data["hp_max"])

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
                current_hp = demon_data['hp'][player_turn]
                current_hp_max = demon_data["hp_max"]
                # 判定是否禁止使用 TNT
                if current_hp_max <= 1 or current_hp <= 1 or (current_hp_max == 2 and current_hp == 2):
                    player_items.append(item_id)
                    msg += "你想引爆烈性TNT，但你的血量/血量上限已经过低，这样做无异于自杀！\n"
                else:
                    demon_data["hp_max"] -= 1
                    demon_data["hp_max"] = max(1, demon_data["hp_max"])  # 确保体力上限不会降到 0，虽然前面有判断了

                    # 校准所有玩家血量不得超过hp上限
                    for i in range(len(demon_data['hp'])):
                        demon_data['hp'][i] = min(demon_data['hp'][i], demon_data["hp_max"])

                    # 扣完上限调整血量后再扣血
                    demon_data['hp'][player_turn] -= 1
                    demon_data['hp'][opponent_turn] -= 1

                    msg += (
                        "你点燃了烈性TNT，产生了巨大的爆炸！\n"
                        f"- 双方HP上限 -1！\n- 当前HP上限：{demon_data['hp_max']}\n"
                        f"- 双方HP -1！\n- 你的HP：{demon_data['hp'][player_turn]}/{demon_data['hp_max']}\n- 对方HP：{demon_data['hp'][opponent_turn]}/{demon_data['hp_max']}\n"
                    )

            elif item_name == "墨镜":
                if len(demon_data['clip']) > 1:
                    first_bullet = demon_data['clip'][0]
                    last_bullet = demon_data['clip'][-1]
                    real_bullet_count = (first_bullet + last_bullet)  # 计算两个位置的实弹数量
                    msg += f"你戴上了墨镜，观察枪膛……\n第一颗和最后一颗子弹加起来，有{real_bullet_count}颗实弹！\n"
                else:
                    msg += f"枪膛里只剩最后一颗子弹了，是{'实弹' if demon_data['clip'][-1] == 1 else '空弹'}！\n"
            else:
                msg += "道具不存在或无法使用！\n"

            next_player_turn = demon_data['turn']  # 获取下一位玩家的 turn
            next_player_id = str(demon_data["pl"][next_player_turn])  # 下一位玩家的 ID
            next_nickname = get_nickname(plugin_event, next_player_id, tmp_hagID)
            msg += f"\n- 现在轮到[{next_nickname}]行动！"
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
            save_group_data(bot_hash, group_hash, demon_data)
            player_ids = [player0, player1]
            send_forward_text(plugin_event, player_ids, msg, True, f"\n现在轮到[{next_nickname}]行动！")
        elif isMatchWordStart(tmp_reast_str, ['查看局势','查询局势'], isCommand = True):
            if not flag_is_from_group:
                return
            isEnd = try_resume_monitor_for_group(plugin_event, Proc, bot_hash, group_hash, tmp_hagID)
            if not isEnd:
                return
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['查看局势','查询局势'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            user_id = str(plugin_event.data.user_id)
            demon_data = load_group_data(bot_hash, group_hash)
            if demon_data['start'] == False:
                msg = f'[{get_nickname(plugin_event, user_id, tmp_hagID)}]，当前并没有开始任何一局恶魔轮盘哦！'
                replyMsg(plugin_event, msg, True)
                return
            if user_id not in demon_data['pl']:
                msg = f'[{get_nickname(plugin_event, user_id, tmp_hagID)}]，只有当前局内玩家能查看局势哦！'
                replyMsg(plugin_event, msg, True)
                return
            # 生成玩家信息
            player0 = str(demon_data['pl'][0])
            player1 = str(demon_data['pl'][1])
            p0_nick_name = get_nickname(plugin_event, player0, tmp_hagID)
            p1_nick_name = get_nickname(plugin_event, player1, tmp_hagID)
            game_turn = demon_data.get('game_turn')
            hp_max = demon_data.get('hp_max')
            item_max = demon_data.get('item_max')
            hcf = demon_data.get('hcf')
            identity_found = demon_data['identity'] 
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
            # 生成血量信息
            hp0 = demon_data['hp'][0]
            hp1 = demon_data['hp'][1]
            atk = demon_data['atk']
            identity_found = demon_data['identity']
            # 步时信息
            elapsed = int(time.time()) - demon_data['turn_start_time']
            remaining_seconds = turn_time - elapsed # 计算剩余冷却时间, 全局变量，设定时间（秒）
            remaining_minutes = remaining_seconds // 60  # 剩余分钟数
            remaining_seconds = remaining_seconds % 60  # 剩余秒数
            msg = "- 本局模式："
            if identity_found == 1:
                # death_turn轮以后死斗模式显示
                if identity_found in turn_limit and demon_data['game_turn'] > turn_limit[identity_found]:
                    msg += '（死斗）'
                msg += "身份模式\n"
            elif identity_found == 2:
                # 1轮以后死斗模式显示
                if identity_found in turn_limit and demon_data['game_turn'] > turn_limit[identity_found]:
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
            msg += f"\n[{p0_nick_name}]\nhp：{hp0}/{hp_max}\n" + f"道具({len(items_0)}/{item_max})：" +f"\n{item_0}\n\n"
            msg += f"[{p1_nick_name}]\nhp：{hp1}/{hp_max}\n" + f"道具({len(items_1)}/{item_max})：" +f"\n{item_1}\n\n"
            msg += f"- 总弹数{str(len(demon_data['clip']))}，实弹数{str(demon_data['clip'].count(1))}"
            pid = demon_data['pl'][demon_data['turn']]
            pid_nickname = get_nickname(plugin_event, pid, tmp_hagID)
            turn_msg = f"当前是[{pid_nickname}]的回合"
            send_forward_text(plugin_event, [pid], msg, True, f'\n{turn_msg}')
        elif isMatchWordStart(tmp_reast_str, ['恶魔投降'], isCommand = True):
            if not flag_is_from_group:
                return
            isEnd = try_resume_monitor_for_group(plugin_event, Proc, bot_hash, group_hash, tmp_hagID)
            if not isEnd:
                return
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['恶魔投降'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            user_id = str(plugin_event.data.user_id)

            demon_data = load_group_data(bot_hash, group_hash)  # 加载恶魔数据

            # 判断玩家是否在游戏中
            if demon_data['start'] == False:
                msg = f'[{get_nickname(plugin_event, user_id, tmp_hagID)}]，当前并没有开始任何一局恶魔轮盘哦！'
                replyMsg(plugin_event, msg, True)
                return
            # 获取当前游戏的玩家信息
            players = demon_data['pl']  # 当前游戏中的两位玩家ID
            if user_id not in players:
                msg = f'[{get_nickname(plugin_event, user_id, tmp_hagID)}]，只有当前局内玩家能投降哦！'
                replyMsg(plugin_event, msg, True)
                return

            # 确定投降的玩家和获胜的玩家
            loser = user_id
            winner = str(players[1] if loser == players[0] else players[0])
            loser_nickname = get_nickname(plugin_event, loser, tmp_hagID)
            end_msg, demon_data = handle_game_end(
                plugin_event,
                group_id=str(group_id),
                winner=winner,
                prefix_msg=f"玩家[{loser_nickname}]已投降。\n游戏结束，",
                demon_data=demon_data
            )
            save_group_data(bot_hash, group_hash, demon_data)

            # 发送投降结果消息
            replyMsg(plugin_event, end_msg, True)
            return
        # 恶魔道具查询功能：展示指定道具的效果
        elif isMatchWordStart(tmp_reast_str, ['恶魔道具'], isCommand = True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['恶魔道具'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            user_id = str(plugin_event.data.user_id)
            # 去除前后空格，处理用户输入
            prop_name = tmp_reast_str.strip().lower()

            if prop_name == "": # 没有输入默认all
                prop_name = 'all'
            if prop_name == "all":  # 如果是查询所有道具
                # 构建所有道具的效果信息
                all_effects = "\n".join([f"-【{prop}】：{effect}" for prop, effect in item_effects.items()])
                send_forward_text(plugin_event, [user_id], all_effects, False, "", True)
                return
            else:  # 查询指定道具
                # 创建一个忽略大小写的映射字典
                lower_to_original = {key.lower(): key for key in item_effects.keys()}

                # 查找原始名称
                original_name = lower_to_original.get(prop_name)

                if original_name:
                    # 使用原始名称查询效果
                    effect = item_effects[original_name]
                    replyMsg(plugin_event, f"道具【{original_name}】效果：\n{effect}", True)
                    return
                else:
                    # 没找到匹配项
                    msg = f"未找到名为【{prop_name}】的道具，\n请检查道具名称是否正确！"
                    replyMsg(plugin_event, msg, True)
                    return
        elif isMatchWordStart(tmp_reast_str, ['切换身份','切换恶魔模式','切换模式'], isCommand = True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['切换身份','切换恶魔模式','切换模式'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.lower().strip()
            user_id = str(plugin_event.data.user_id)
            user_hash = OlivaDiceCore.userConfig.getUserHash(
                            user_id,
                            'user',
                            plugin_event.platform['platform']
                        )
            user_data = load_user_data(bot_hash, user_hash)
            if str(tmp_reast_str) == '0':
                user_data['identity_status'] = 0
                save_user_data(bot_hash, user_hash, user_data)
                tmp_reply_str = "已将你的默认恶魔模式切换为：普通模式！"
            elif str(tmp_reast_str) == '1':
                user_data['identity_status'] = 1
                save_user_data(bot_hash, user_hash, user_data)
                tmp_reply_str = "已将你的默认恶魔模式切换为：身份模式！"
            elif str(tmp_reast_str) == '2':
                user_data['identity_status'] = 2
                save_user_data(bot_hash, user_hash, user_data)
                tmp_reply_str = "已将你的默认恶魔模式切换为：极速模式！"
            else:
                tmp_reply_str = "请输入正确的模式序号！\n请使用命令[.切换身份 0/1/2]\n0：普通模式\n1：身份模式\n2：极速模式"
            replyMsg(plugin_event, tmp_reply_str, True)
            return      
        elif isMatchWordStart(tmp_reast_str, ['查看战绩','恶魔战绩'], isCommand = True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['查看战绩','恶魔战绩'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            user_id = str(plugin_event.data.user_id)
            user_hash = OlivaDiceCore.userConfig.getUserHash(
                            user_id,
                            'user',
                            plugin_event.platform['platform']
                        )
            Proc.log(2, user_hash)
            user_data = load_user_data(bot_hash, user_hash)
            total_games = user_data.get('total_games', 0)
            wins = user_data.get('win_times', 0)
            identity_status = user_data.get('identity_status', 0)
            if identity_status == 0:
                identity_status_msg = "普通模式"
            elif identity_status == 1:
                identity_status_msg = "身份模式"
            elif identity_status == 2:
                identity_status_msg = "极速模式"
            else:
                identity_status_msg = "未知模式"
            losses = total_games - wins
            win_rate = (wins / total_games * 100) if total_games > 0 else 0.0
            longest_win_streak = user_data.get('longest_win_streak', 0)
            current_win_streak = user_data.get('current_win_streak', 0)

            stats_message = (
                f"你的恶魔轮盘战绩：\n"
                f"- 身份状态: {identity_status_msg}\n"
                f"- 总游戏局数: {total_games}\n"
                f"- 胜利局数: {wins}\n"
                f"- 失败局数: {losses}\n"
                f"- 胜率: {win_rate:.2f}%\n"
                f"- 最长连胜: {longest_win_streak}\n"
                f"- 当前连胜: {current_win_streak}"
            )

            replyMsg(plugin_event, stats_message, True)
            return
        elif isMatchWordStart(tmp_reast_str, ['结束赌局','强制结束赌局','结束本局赌局'], isCommand = True):
            # 仅允许管理员、群主或骰主使用此命令
            if not flag_is_from_group:
                return
            isEnd = try_resume_monitor_for_group(plugin_event, Proc, bot_hash, group_hash, tmp_hagID)
            if not isEnd:
                return
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['结束赌局','强制结束赌局','结束本局赌局'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            user_id = str(plugin_event.data.user_id)

            # 权限判断：群主/管理员 或 群主/管理员 标记 或 是骰主
            is_permission = False
            if flag_is_from_group and flag_is_from_group_admin:
                is_permission = True
            if flag_is_from_host and plugin_event.data.host_id is not None and str(plugin_event.data.host_id) == user_id:
                is_permission = True
            if flag_is_from_master:
                is_permission = True

            if not is_permission:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strAtOtherPermissionDenied'], 
                    dictTValue
                )
                replyMsg(plugin_event, tmp_reply_str, True)
                return

            # 加载并重置群组数据
            demon_data = load_group_data(bot_hash, group_hash)

            # 停止超时监控线程（如果存在）
            try:
                if group_hash in active_game_monitors:
                    monitor_info = active_game_monitors[group_hash]
                    monitor_info['stop_event'].set()
                    # 不立即删除，让线程自行退出并清理（线程中会检查 stop_event）
                    del active_game_monitors[group_hash]
            except Exception:
                pass

            # 重置为默认状态并保留冷却时间为当前时间（避免立刻重开）
            new_demon = Buckshot.function.demon_default()
            new_demon['demon_coldtime'] = int(time.time())
            save_group_data(bot_hash, group_hash, new_demon)

            replyMsg(plugin_event, '本局赌局已被强制结束并重置为默认状态。', True)
            return