# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore，写命令请跳转到第183行。
'''

import OlivOS
import Blackjack
import OlivaDiceCore

import copy

def unity_init(plugin_event, Proc):
    # 这里是插件初始化，通常用于加载配置等
    pass

def data_init(plugin_event, Proc):
    # 这里是数据初始化，通常用于加载数据等
    Blackjack.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

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
        '''到这里为止，前面的都不动，下面处理 .bj (21点) 命令'''
            # 引入 Blackjack 核心函数
        load_group_data = Blackjack.function.load_group_data
        save_group_data = Blackjack.function.save_group_data
        blackjack_default = Blackjack.function.blackjack_default
        get_nickname = Blackjack.function.get_nickname
        find_player = Blackjack.function.find_player
        reset_for_new_round = Blackjack.function.reset_for_new_round
        deal_initial_cards = Blackjack.function.deal_initial_cards
        deal_card = Blackjack.function.deal_card
        cards_to_text = Blackjack.function.cards_to_text
        calculate_hand_value = Blackjack.function.calculate_hand_value
        get_user_default_chips = Blackjack.function.get_user_default_chips
        apply_hit = Blackjack.function.apply_hit
        apply_stand = Blackjack.function.apply_stand
        apply_double_down = Blackjack.function.apply_double_down
        apply_split = Blackjack.function.apply_split
        apply_surrender = Blackjack.function.apply_surrender
        apply_insurance = Blackjack.function.apply_insurance
        qq_is_friend = Blackjack.function.qq_is_friend
        settle_round = Blackjack.function.settle_round
        settle_insurance = Blackjack.function.settle_insurance
        check_21_3 = Blackjack.function.check_21_3
        sendMsgByEvent = Blackjack.function.sendMsgByEvent

        def group_hash_from_hag(tmp_hag: str) -> str:
            return OlivaDiceCore.userConfig.getUserHash(
                tmp_hag,
                'group',
                plugin_event.platform['platform']
            )

        bot_hash = plugin_event.bot_info.hash
        group_hash = group_hash_from_hag(tmp_hagID) if tmp_hagID else None

        sender_name = get_nickname(
            plugin_event,
            str(plugin_event.data.user_id),
            tmp_hagID,
            dictStrCustom.get('strBJUserFallbackPrefix', ''),
            bot_hash,
            group_hash,
        )
        dictTValue['tName'] = sender_name

        def fmt(key: str, extra: dict = None) -> str:
            tmp = dictTValue.copy()
            if extra:
                tmp.update(extra)
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom.get(key, ''), tmp)

        def reply_custom(key: str, extra: dict = None, at_user: bool = False) -> None:
            msg = fmt(key, extra)
            if msg is not None:
                replyMsg(plugin_event, msg, at_user)

            # 处理 .bj / .21 命令（逐层匹配，支持 '分'+'牌' 等形式）
        if isMatchWordStart(tmp_reast_str, ['bj', '21点', '21'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['bj', '21点', '21'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)

            # 创建房间：.bj 创建 [底注] [模式]
            if isMatchWordStart(tmp_reast_str, ['创建', 'create'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['创建', 'create'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                parts = tmp_reast_str.strip().split()
                base = 100
                mode = 'open'
                if len(parts) >= 1:
                    try:
                        base = int(parts[0])
                    except Exception:
                        base = 100
                if len(parts) >= 2:
                    if parts[1] in ['hidden', '手持']:
                        mode = 'hidden'
                game = blackjack_default()
                game['base_stake'] = int(base)
                game['min_stake'] = int(max(10, int(base)//10))
                game['max_stake'] = int(base * 100)
                game['game_mode'] = mode
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJCreateSuccess', {'tBaseStake': str(game['base_stake']), 'tMinStake': str(game['min_stake']), 'tMaxStake': str(game['max_stake']), 'tGameMode': game['game_mode']})
                return

            # 加入：.bj 加入 [名称] [筹码]
            if isMatchWordStart(tmp_reast_str, ['加入', 'join'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['加入', 'join'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                parts = tmp_reast_str.strip().split()
                game = load_group_data(bot_hash, group_hash)
                if game is None:
                    reply_custom('strBJErrRoomNotFound')
                    return
                name = sender_name
                chips = None
                if len(parts) >= 1:
                    name = parts[0]
                if len(parts) >= 2:
                    try:
                        chips = int(parts[1])
                    except Exception:
                        chips = None
                if chips is None:
                    userhash = OlivaDiceCore.userConfig.getUserHash(plugin_event.data.user_id, 'user', plugin_event.platform['platform'])
                    chips = get_user_default_chips(userhash)
                # 分配座位号
                seat_id = 1
                existing = [int(p['seat_id']) for p in game.get('players', [])]
                while seat_id in existing:
                    seat_id += 1
                player = {
                    'seat_id': seat_id,
                    'user_id': str(plugin_event.data.user_id),
                    'nickname': name,
                    'chips': int(chips),
                    'is_dealer': False,
                    'status': 'active',
                    'hand_cards': [],
                    'current_bet': 0,
                    'insurance_bet': 0,
                    'bet_21_3': 0,
                    'bet_21_3_type': None,
                }
                if not game.get('players'):
                    # 第一个加入的玩家成为庄家
                    player['is_dealer'] = True
                    game['dealer_seat_id'] = None
                game.setdefault('players', []).append(player)
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJJoinSuccess', {'tName': name, 'tSeatId': str(seat_id), 'tChips': str(chips), 'tIsDealer': (dictStrCustom.get('strBJJoinAsDealer') if player['is_dealer'] else '')})
                return

            # 开始：.bj 开始
            if isMatchWordStart(tmp_reast_str, ['开始', 'start'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['开始', 'start'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                game = load_group_data(bot_hash, group_hash)
                if not game or not game.get('players'):
                    reply_custom('strBJErrRoomNotFound')
                    return
                # 初始化牌堆并发牌
                reset_for_new_round(game)
                deal_initial_cards(game)
                game['state'] = 'playing'
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJStartSuccess', {'tAtAll': ''})
                return

            # 下注：.bj 下注 [金额] [21+3类型] [21+3金额]
            if isMatchWordStart(tmp_reast_str, ['下注', '下'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['下注', '下'])
                if isMatchWordStart(tmp_reast_str, ['注'], isCommand=True):
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['注'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                parts = tmp_reast_str.strip().split()
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                # 查找玩家
                p = None
                for pl in game.get('players', []):
                    if str(pl.get('user_id')) == str(plugin_event.data.user_id):
                        p = pl
                        break
                if not p:
                    reply_custom('strBJErrNotInGroup')
                    return
                if len(parts) >= 1:
                    try:
                        amt = int(parts[0])
                    except Exception:
                        reply_custom('strBJErrInvalidNumber')
                        return
                    # 校验下注金额
                    if amt < int(game.get('min_stake', 10)):
                        reply_custom('strBJErrBetTooSmall', {'tMinStake': str(game.get('min_stake'))})
                        return
                    if amt > int(game.get('max_stake', 10000)):
                        reply_custom('strBJErrBetTooLarge', {'tMaxStake': str(game.get('max_stake'))})
                    if int(p.get('chips', 0)) < amt:
                        reply_custom('strBJErrNotEnoughChips')
                        return
                    # 立即扣除玩家筹码
                    p['chips'] = int(p.get('chips', 0)) - int(amt)
                    p['current_bet'] = int(amt)
                # 可选的 21+3 下注
                if len(parts) >= 2:
                    # 标准化 21+3 类型输入
                    norm = Blackjack.function.normalize_21_3_type(parts[1])
                    if not norm:
                        reply_custom('strBJErrInvalid21_3Type')
                        return
                    p['bet_21_3_type'] = norm
                    try:
                        bet21 = int(parts[2]) if len(parts) >= 3 else 0
                    except Exception:
                        bet21 = 0
                    if bet21 > 0:
                        if int(p.get('chips', 0)) < bet21:
                            reply_custom('strBJErrNotEnoughChips')
                            return
                        p['chips'] = int(p.get('chips', 0)) - int(bet21)
                        p['bet_21_3'] = int(bet21)
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJStatusBoard')
                return

            # 看牌：.bj 看牌 或 .bj 看 牌
            if isMatchWordStart(tmp_reast_str, ['看牌', '看', 'cards'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['看牌', '看', 'cards'])
                if isMatchWordStart(tmp_reast_str, ['牌'], isCommand=True):
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['牌'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                p = None
                for pl in game.get('players', []):
                    if str(pl.get('user_id')) == str(plugin_event.data.user_id):
                        p = pl
                        break
                if not p:
                    reply_custom('strBJErrNotInGroup')
                    return
                # 私聊手牌
                msg = fmt('strBJPrivateCardsHeader', {'tGroupId': str(plugin_event.data.group_id)}) + '\n'
                msg += fmt('strBJPrivateCardsSeatLine', {'tSeatId': str(p.get('seat_id')), 'tSeatName': p.get('nickname')}) + '\n'
                msg += fmt('strBJPrivateCardsCardsLine', {'tHandCards': cards_to_text(p.get('hand_cards', []))}) + '\n'
                hv, sv, hv2 = calculate_hand_value(p.get('hand_cards', []))
                msg += fmt('strBJPrivateCardsValueLine', {'tHandValue': str(hv)}) + '\n'
                msg += fmt('strBJPrivateCardsFooter')
                # 发送私聊（在 QQ 平台先检查是否为好友）
                try:
                    platform = plugin_event.platform.get('platform', '')
                    if platform.startswith('qq'):
                        if not qq_is_friend(plugin_event, str(plugin_event.data.user_id)):
                            reply_custom('strBJErrCannotPM')
                            return
                    sendMsgByEvent(plugin_event, msg, plugin_event.data.user_id, 'private')
                except Exception:
                    reply_custom('strBJErrNotInGroup')
                return

            # 局势：.bj 局势
            if isMatchWordStart(tmp_reast_str, ['局势', 'status'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['局势', 'status'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                header = fmt('strBJStatusHeader', {'tBaseStake': str(game.get('base_stake')), 'tMinStake': str(game.get('min_stake')), 'tMaxStake': str(game.get('max_stake')), 'tGameMode': game.get('game_mode')})
                dealer = ''
                dealer_cards = game.get('dealer_cards', [])
                dealer_value = ''
                if dealer_cards:
                    dv, s, h = calculate_hand_value(dealer_cards)
                    dealer = cards_to_text(dealer_cards)
                    dealer_value = str(dv)
                seat_lines = []
                for p in game.get('players', []):
                    line1 = fmt('strBJStatusSeatLine1', {'tSeatId': str(p.get('seat_id')), 'tSeatName': p.get('nickname')})
                    line2 = fmt('strBJStatusSeatLine2', {'tSeatChips': str(p.get('chips', 0)), 'tSeatBet': str(p.get('current_bet', 0)), 'tInsuranceBet': str(p.get('insurance_bet', 0)), 't21_3Bet': str(p.get('bet_21_3', 0)), 'tSeatStatus': p.get('status', '')})
                    seat_lines.append(line1 + '\n' + line2)
                board = fmt('strBJStatusBoard', {'tHeader': header, 'tDealer': fmt('strBJStatusDealer', {'tDealerName': '', 'tDealerCards': dealer, 'tDealerValue': dealer_value}), 'tSep': fmt('strBJStatusSeparator'), 'tSeatLines': '\n'.join(seat_lines), 'tTurnLine': '', 'tCmdLine': fmt('strBJStatusCmdHint', {'tCmdHint': ''})})
                replyMsg(plugin_event, board)
                return

            # 加注：.bj 加注 [金额] 或 .bj 加 注
            if isMatchWordStart(tmp_reast_str, ['加注', '加'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['加注', '加'])
                if isMatchWordStart(tmp_reast_str, ['注'], isCommand=True):
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['注'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                parts = tmp_reast_str.strip().split()
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                p = None
                for pl in game.get('players', []):
                    if str(pl.get('user_id')) == str(plugin_event.data.user_id):
                        p = pl
                        break
                if not p:
                    reply_custom('strBJErrNotInGroup')
                    return
                if len(parts) < 1:
                    reply_custom('strBJErrInvalidNumber')
                    return
                try:
                    add = int(parts[0])
                except Exception:
                    reply_custom('strBJErrInvalidNumber')
                    return
                if int(p.get('chips', 0)) < add:
                    reply_custom('strBJErrNotEnoughChips')
                    return
                p['chips'] = int(p.get('chips', 0)) - add
                p['current_bet'] = int(p.get('current_bet', 0)) + add
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJStatusBoard')
                return

            # 双倍：.bj 双倍
            if isMatchWordStart(tmp_reast_str, ['双倍', 'double'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['双倍', 'double'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                p = None
                for pl in game.get('players', []):
                    if str(pl.get('user_id')) == str(plugin_event.data.user_id):
                        p = pl
                        break
                if not p:
                    reply_custom('strBJErrNotInGroup')
                    return
                # 仅在玩家首轮且手牌为两张时允许双倍
                if int(p.get('current_bet', 0)) <= 0:
                    reply_custom('strBJErrActionNotAllowed')
                    return
                if p.get('acted'):
                    reply_custom('strBJErrCannotDouble')
                    return
                hand = p.get('hand_cards', [])
                if len(hand) != 2:
                    reply_custom('strBJErrCannotDouble')
                    return
                orig = int(p.get('current_bet', 0))
                if int(p.get('chips', 0)) < orig:
                    reply_custom('strBJErrNotEnoughChips')
                    return
                # 扣除等额筹码（作为翻倍第二份下注）
                p['chips'] = int(p.get('chips', 0)) - orig
                ok, reason = apply_double_down(game, p.get('seat_id'))
                if not ok:
                    # 回滚（操作失败时退回筹码）
                    p['chips'] = int(p.get('chips', 0)) + orig
                    reply_custom('strBJErrActionNotAllowed')
                    return
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJDoubleSuccess', {'tSeatId': str(p.get('seat_id')), 'tSeatName': p.get('nickname'), 'tNewCard': cards_to_text([p.get('hand_cards')[-1]]) if p.get('hand_cards') else '', 'tHandValue': str(p.get('hand_value', ''))})
                return

            # 分牌：.bj 分牌 或 .bj 分 牌
            if isMatchWordStart(tmp_reast_str, ['分牌', '分', 'split'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['分牌', '分', 'split'])
                if isMatchWordStart(tmp_reast_str, ['牌'], isCommand=True):
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['牌'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                p = None
                for pl in game.get('players', []):
                    if str(pl.get('user_id')) == str(plugin_event.data.user_id):
                        p = pl
                        break
                if not p:
                    reply_custom('strBJErrNotInGroup')
                    return
                bet = int(p.get('current_bet', 0))
                if bet <= 0:
                    reply_custom('strBJErrCannotSplit')
                    return
                if int(p.get('chips', 0)) < bet:
                    reply_custom('strBJErrNotEnoughChips')
                    return
                # 仅在未执行过动作且手牌为两张且点数相同的情况下允许分牌
                if p.get('acted'):
                    reply_custom('strBJErrCannotSplit')
                    return
                hc = p.get('hand_cards', [])
                if len(hc) != 2:
                    reply_custom('strBJErrCannotSplit')
                    return
                v1 = Blackjack.function.get_card_value(hc[0], ace_as_eleven=False)
                v2 = Blackjack.function.get_card_value(hc[1], ace_as_eleven=False)
                if v1 != v2:
                    reply_custom('strBJErrCannotSplit')
                    return
                ok, reason = apply_split(game, p.get('seat_id'))
                if not ok:
                    reply_custom('strBJErrCannotSplit')
                    return
                # 为新手牌扣除相同的主注（失败时上文已回滚）
                p['chips'] = int(p.get('chips', 0)) - bet
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJSplitSuccess', {'tSeatId': str(p.get('seat_id')), 'tSeatName': p.get('nickname'), 'tHand1Cards': cards_to_text(p.get('split_hands', [])[0]), 'tHand2Cards': cards_to_text(p.get('split_hands', [])[1])})
                return

            # 投降：.bj 投降
            if isMatchWordStart(tmp_reast_str, ['投降', 'surrender'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['投降', 'surrender'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                p = None
                for pl in game.get('players', []):
                    if str(pl.get('user_id')) == str(plugin_event.data.user_id):
                        p = pl
                        break
                if not p:
                    reply_custom('strBJErrNotInGroup')
                    return
                # 仅允许在玩家首轮动作之前投降
                if p.get('acted'):
                    reply_custom('strBJErrCannotSurrender')
                    return
                ok, reason = apply_surrender(game, p.get('seat_id'))
                if not ok:
                    reply_custom('strBJErrCannotSurrender')
                    return
                # 立即退还一半下注
                refund = int(p.get('refund', 0))
                p['chips'] = int(p.get('chips', 0)) + int(refund)
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJSurrenderSuccess', {'tSeatId': str(p.get('seat_id')), 'tSeatName': p.get('nickname'), 'tRefund': str(refund)})
                return

            # 保险：.bj 保险 [金额]
            if isMatchWordStart(tmp_reast_str, ['保险', 'insurance'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['保险', 'insurance'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                parts = tmp_reast_str.strip().split()
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                p = None
                for pl in game.get('players', []):
                    if str(pl.get('user_id')) == str(plugin_event.data.user_id):
                        p = pl
                        break
                if not p:
                    reply_custom('strBJErrNotInGroup')
                    return
                dealer_cards = game.get('dealer_cards', [])
                if not dealer_cards or len(dealer_cards) < 1 or dealer_cards[0][1] != 'A':
                    reply_custom('strBJErrCannotInsurance')
                    return
                amt = None
                if len(parts) >= 1:
                    try:
                        amt = int(parts[0])
                    except Exception:
                        amt = None
                if amt is None:
                    amt = int(p.get('current_bet', 0)) // 2
                if amt > int(p.get('current_bet', 0)) // 2:
                    reply_custom('strBJErrInsuranceTooLarge')
                    return
                if int(p.get('chips', 0)) < amt:
                    reply_custom('strBJErrNotEnoughChips')
                    return
                p['chips'] = int(p.get('chips', 0)) - int(amt)
                apply_insurance(game, p.get('seat_id'), amt)
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJInsuranceSuccess', {'tSeatId': str(p.get('seat_id')), 'tSeatName': p.get('nickname'), 'tInsuranceAmount': str(amt)})
                return

            # 退出：.bj 退出（仅开局前）
            if isMatchWordStart(tmp_reast_str, ['退出', 'quit'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['退出', 'quit'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                if game.get('state') == 'playing':
                    reply_custom('strBJErrAlreadyPlaying')
                    return
                # 将玩家从房间移除
                new_players = [pl for pl in game.get('players', []) if str(pl.get('user_id')) != str(plugin_event.data.user_id)]
                game['players'] = new_players
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJQuitSuccess', {'tName': sender_name, 'tSeatId': ''})
                return

            # 解散：.bj 解散（庄家或管理员）
            if isMatchWordStart(tmp_reast_str, ['解散', 'dismiss'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['解散', 'dismiss'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                # 权限：仅允许首位加入者或群/机器人管理员操作
                allowed = False
                if game.get('players'):
                    first = game['players'][0]
                    if str(first.get('user_id')) == str(plugin_event.data.user_id):
                        allowed = True
                if not allowed and not flag_is_from_master and not flag_is_from_group_admin:
                    reply_custom('strBJErrNoPermission')
                    return
                save_group_data(bot_hash, group_hash, blackjack_default())
                reply_custom('strBJDismissSuccess')
                return

            # 强制结束：.bj 强制结束（管理员）
            if isMatchWordStart(tmp_reast_str, ['强制结束', 'stop', 'halt'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['强制结束', 'stop', 'halt'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                if not flag_is_from_master and not flag_is_from_group_admin:
                    reply_custom('strBJErrNoPermission')
                    return
                save_group_data(bot_hash, group_hash, blackjack_default())
                reply_custom('strBJDismissSuccess')
                return

            # 未识别子命令
            reply_custom('strBJErrInvalidNumber')
            return