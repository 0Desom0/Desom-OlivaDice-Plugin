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

        # 处理 .bj / .21 命令
        if isMatchWordStart(tmp_reast_str, ['bj', '21', '21点'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['bj', '21', '21点'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            parts = tmp_reast_str.strip().split()
            cmd = parts[0] if parts else ''

            # 创建房间: .bj 创建 [底注] [模式]
            if cmd in ['创建', 'create']:
                base = 100
                mode = 'open'
                if len(parts) >= 2:
                    try:
                        base = int(parts[1])
                    except Exception:
                        base = 100
                if len(parts) >= 3:
                    if parts[2] in ['hidden', '手持']:
                        mode = 'hidden'
                game = blackjack_default()
                game['base_stake'] = int(base)
                game['min_stake'] = int(max(10, int(base)//10))
                game['max_stake'] = int(base * 100)
                game['game_mode'] = mode
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJCreateSuccess', {'tBaseStake': str(game['base_stake']), 'tMinStake': str(game['min_stake']), 'tMaxStake': str(game['max_stake']), 'tGameMode': game['game_mode']})
                return

            # 加入: .bj 加入 [名称] [筹码]
            if cmd in ['加入', 'join']:
                game = load_group_data(bot_hash, group_hash)
                if game is None:
                    reply_custom('strBJErrRoomNotFound')
                    return
                name = sender_name
                chips = None
                if len(parts) >= 2:
                    name = parts[1]
                if len(parts) >= 3:
                    try:
                        chips = int(parts[2])
                    except Exception:
                        chips = None
                if chips is None:
                    userhash = OlivaDiceCore.userConfig.getUserHash(plugin_event.data.user_id, 'user', plugin_event.platform['platform'])
                    chips = get_user_default_chips(userhash)
                # assign seat id
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
                    # first joiner becomes dealer
                    player['is_dealer'] = True
                    game['dealer_seat_id'] = None
                game.setdefault('players', []).append(player)
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJJoinSuccess', {'tName': name, 'tSeatId': str(seat_id), 'tChips': str(chips), 'tIsDealer': (dictStrCustom.get('strBJJoinAsDealer') if player['is_dealer'] else '')})
                return

            # 开始: .bj 开始
            if cmd in ['开始', 'start']:
                game = load_group_data(bot_hash, group_hash)
                if not game or not game.get('players'):
                    reply_custom('strBJErrRoomNotFound')
                    return
                # init deck and deal
                reset_for_new_round(game)
                deal_initial_cards(game)
                game['state'] = 'playing'
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJStartSuccess', {'tAtAll': ''})
                return

            # 下注: .bj 下注 [金额] [21+3类型] [21+3金额]
            if cmd in ['下注', '下']:
                game = load_group_data(bot_hash, group_hash)
                if not game:
                    reply_custom('strBJErrRoomNotFound')
                    return
                # find player
                p = None
                for pl in game.get('players', []):
                    if str(pl.get('user_id')) == str(plugin_event.data.user_id):
                        p = pl
                        break
                if not p:
                    reply_custom('strBJErrNotInGroup')
                    return
                if len(parts) >= 2:
                    try:
                        amt = int(parts[1])
                    except Exception:
                        reply_custom('strBJErrInvalidNumber')
                        return
                    p['current_bet'] = amt
                # optional 21+3
                if len(parts) >= 4:
                    p['bet_21_3_type'] = parts[2]
                    try:
                        p['bet_21_3'] = int(parts[3])
                    except Exception:
                        p['bet_21_3'] = 0
                save_group_data(bot_hash, group_hash, game)
                reply_custom('strBJStatusBoard')
                return

            # 看牌: .bj 看牌
            if cmd in ['看牌', 'cards']:
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
                # send private
                try:
                    sendMsgByEvent(plugin_event, msg, plugin_event.data.user_id, 'private')
                except Exception:
                    reply_custom('strBJErrNotInGroup')
                return

            # 局势: .bj 局势
            if cmd in ['局势', 'status']:
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

            # 未识别子命令
            reply_custom('strBJErrInvalidNumber')
            return