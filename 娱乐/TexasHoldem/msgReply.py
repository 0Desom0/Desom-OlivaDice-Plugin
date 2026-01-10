# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore
'''

import OlivOS
import TexasHoldem
import OlivaDiceCore

import copy

def unity_init(plugin_event, Proc):
    # 这里是插件初始化，通常用于加载配置等
    pass

def data_init(plugin_event, Proc):
    # 这里是数据初始化，通常用于加载数据等
    TexasHoldem.function.get_texas_data_path()
    TexasHoldem.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

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
        '''命令部分'''

        # 引入核心逻辑模块里的函数
        load_group_data = TexasHoldem.function.load_group_data
        save_group_data = TexasHoldem.function.save_group_data
        texas_default = TexasHoldem.function.texas_default
        compute_blinds = TexasHoldem.function.compute_blinds
        get_nickname = TexasHoldem.function.get_nickname
        cards_to_text = TexasHoldem.function.cards_to_text
        hand_type_text = TexasHoldem.function.hand_type_text
        evaluate_7 = TexasHoldem.function.evaluate_7
        format_best5_compact = TexasHoldem.function.format_best5_compact
        order_best5_by_compact = TexasHoldem.function.order_best5_by_compact
        role_name_for_seat = TexasHoldem.function.role_name_for_seat
        start_hand = TexasHoldem.function.start_hand
        apply_fold = TexasHoldem.function.apply_fold
        apply_call_or_check = TexasHoldem.function.apply_call_or_check
        apply_bet = TexasHoldem.function.apply_bet
        apply_raise = TexasHoldem.function.apply_raise
        apply_allin = TexasHoldem.function.apply_allin
        is_betting_round_over = TexasHoldem.function.is_betting_round_over
        advance_street = TexasHoldem.function.advance_street
        settle_showdown = TexasHoldem.function.settle_showdown
        rotate_dealer = TexasHoldem.function.rotate_dealer
        remove_broke_players = TexasHoldem.function.remove_broke_players
        compact_players = TexasHoldem.function.compact_players
        check_auto_end = TexasHoldem.function.check_auto_end
        find_player = TexasHoldem.function.find_player
        next_pending_actor = TexasHoldem.function.next_pending_actor
        sendMsgByEvent = TexasHoldem.function.sendMsgByEvent

        sender_name = get_nickname(
            plugin_event,
            str(plugin_event.data.user_id),
            tmp_hagID,
            dictStrCustom.get('strTHUserFallbackPrefix', ''),
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

        def group_hash_from_hag(tmp_hag: str) -> str:
            return OlivaDiceCore.userConfig.getUserHash(
                tmp_hag,
                'group',
                plugin_event.platform['platform']
            )

        def street_text(game: dict) -> str:
            st = game.get('street')
            if st == 'preflop':
                return dictStrCustom['strTHStreetPreflop']
            if st == 'flop':
                return dictStrCustom['strTHStreetFlop']
            if st == 'turn':
                return dictStrCustom['strTHStreetTurn']
            if st == 'river':
                return dictStrCustom['strTHStreetRiver']
            if st == 'showdown':
                return dictStrCustom['strTHStreetShowdown']
            return ''

        def role_text_from_code(code: str) -> str:
            if code == 'BTN/D+SB':
                return dictStrCustom['strTHRoleDealerSB']
            if code == 'BTN/D':
                return dictStrCustom['strTHRoleDealer']
            if code == 'SB':
                return dictStrCustom['strTHRoleSB']
            if code == 'BB':
                return dictStrCustom['strTHRoleBB']
            if code == 'UTG':
                return dictStrCustom['strTHRoleUTG']
            if code == 'UTG+1':
                return dictStrCustom['strTHRoleUTG1']
            if code == 'UTG+2':
                return dictStrCustom['strTHRoleUTG2']
            if code == 'MP':
                return dictStrCustom['strTHRoleMP']
            if code == 'MP1':
                return dictStrCustom['strTHRoleMP1']
            if code == 'MP2':
                return dictStrCustom['strTHRoleMP2']
            if code == 'HJ':
                return dictStrCustom['strTHRoleHJ']
            if code == 'CO':
                return dictStrCustom['strTHRoleCO']
            return ''

        def action_text_from_last(last_action: str) -> str:
            if not last_action:
                return ''
            parts = str(last_action).split(' ')
            if len(parts) == 2 and parts[0] in ['SB', 'BB', 'call', 'bet', 'raise', 'allin']:
                try:
                    amount = int(parts[1])
                except Exception:
                    amount = 0
                if parts[0] == 'SB':
                    return fmt('strTHActionBlindSB', {'tAmount': str(amount)})
                if parts[0] == 'BB':
                    return fmt('strTHActionBlindBB', {'tAmount': str(amount)})
                if parts[0] == 'call':
                    return fmt('strTHActionCall', {'tAmount': str(amount)})
                if parts[0] == 'bet':
                    return fmt('strTHActionBet', {'tAmount': str(amount)})
                if parts[0] == 'raise':
                    return fmt('strTHActionRaise', {'tAmount': str(amount)})
                if parts[0] == 'allin':
                    return fmt('strTHActionAllinAmount', {'tAmount': str(amount)})
            if parts[0] == 'check':
                return fmt('strTHActionCheck')
            if parts[0] == 'fold':
                return fmt('strTHActionFold')
            return str(last_action)

        def build_status_board(game: dict, tmp_hag: str) -> str:
            # 头部/公共牌
            pot = int(game.get('pot', 0))
            min_raise = int(game.get('min_raise', 0))
            current_high = int(game.get('current_high', 0))
            min_call = current_high

            header = fmt('strTHStatusHeader', {
                'tPot': str(pot),
                'tMinRaise': str(min_raise),
                'tMinCall': str(min_call),
            })

            cc = game.get('community_cards', [])
            community = fmt('strTHStatusCommunity', {
                'tCommunityCards': cards_to_text(cc) if cc else '',
                'tStreetText': street_text(game),
            })

            # 座位信息行
            seats = sorted([int(p['seat_id']) for p in game.get('players', [])])
            acting = game.get('acting_seat_id')
            seat_blocks = []
            for sid in seats:
                p = find_player(game['players'], sid)
                if not p:
                    continue
                role_code = role_name_for_seat(game, sid)
                role_text = role_text_from_code(role_code)

                turn_mark = ''
                if acting is not None and int(acting) == sid and p.get('status') == 'active':
                    turn_mark = fmt('strTHTurnMark')

                # 动作显示
                if p.get('status') == 'folded':
                    action_text = fmt('strTHSeatActionFolded')
                elif p.get('status') == 'allin':
                    action_text = fmt('strTHSeatActionAllin')
                elif acting is not None and int(acting) == sid and p.get('status') == 'active':
                    need_call = max(0, int(game.get('current_high', 0)) - int(p.get('current_bet', 0)))
                    can_check_now = need_call == 0
                    # 下注仅在翻牌后且无人下注（本街 current_high==0）时可用
                    can_bet_now = (game.get('street') != 'preflop') and int(game.get('current_high', 0)) == 0
                    opt_check = fmt('strTHPendingOptCheckOK') if can_check_now else fmt('strTHPendingOptCheckNO')
                    opt_bet = fmt('strTHPendingOptBetOK') if can_bet_now else fmt('strTHPendingOptBetNO')
                    opt_call = fmt('strTHPendingOptCall', {'tNeedCall': str(need_call)})
                    last_action = str(p.get('last_action', '')).strip()
                    is_blind_only = last_action.startswith('SB ') or last_action.startswith('BB ')
                    if is_blind_only:
                        action_text = fmt('strTHSeatActionPendingBlind', {
                            'tNeedCall': str(need_call),
                            'tOptCheck': opt_check,
                            'tOptBet': opt_bet,
                            'tOptCall': opt_call,
                            'tBlindText': action_text_from_last(last_action),
                        })
                    else:
                        action_text = fmt('strTHSeatActionPending', {
                            'tNeedCall': str(need_call),
                            'tOptCheck': opt_check,
                            'tOptBet': opt_bet,
                            'tOptCall': opt_call,
                        })
                else:
                    last_action = str(p.get('last_action', '')).strip()
                    if last_action:
                        act_txt = action_text_from_last(last_action)
                        if last_action.startswith('SB ') or last_action.startswith('BB '):
                            action_text = fmt('strTHSeatActionNoneBlind', {'tBlindText': act_txt})
                        else:
                            action_text = fmt('strTHSeatActionText', {'tActionText': act_txt})
                    else:
                        action_text = fmt('strTHSeatActionNone')

                line1 = fmt('strTHStatusSeatLine1', {
                    'tSeatId': str(sid),
                    'tSeatName': str(p.get('nickname', '')),
                    'tSeatRoleText': role_text,
                    'tSeatTurnMark': turn_mark,
                })
                line2 = fmt('strTHStatusSeatLine2', {
                    'tSeatChips': str(p.get('chips', 0)),
                    'tSeatActionText': action_text,
                })
                seat_blocks.append(line1 + '\n' + line2)

            seat_lines = '\n\n'.join(seat_blocks)

            # 轮到谁行动
            turn_line = ''
            cmd_hint = ''
            if acting is not None:
                p_turn = find_player(game['players'], int(acting))
                can_check_now = False
                can_bet_now = False
                if p_turn:
                    role_code = role_name_for_seat(game, int(acting))
                    role_text = role_text_from_code(role_code)
                    at_cq = OlivOS.messageAPI.PARA.at(str(p_turn.get('user_id'))).get_string_by_key('CQ')
                    turn_line = fmt('strTHStatusTurnLine', {
                        'tTurnSeatId': str(acting),
                        'tTurnName': str(p_turn.get('nickname', '')),
                        'tTurnRoleText': role_text,
                        'tTurnAt': at_cq,
                    })
                    if p_turn.get('status') == 'active':
                        need_call = max(0, int(game.get('current_high', 0)) - int(p_turn.get('current_bet', 0)))
                        can_check_now = need_call == 0
                        # 下注仅在翻牌后且无人下注（本街 current_high==0）时可用
                        can_bet_now = (game.get('street') != 'preflop') and int(game.get('current_high', 0)) == 0
                if game.get('street') == 'preflop':
                    if can_check_now:
                        cmd_hint = dictStrCustom.get('strTHCmdHintPreflopCheck', dictStrCustom['strTHCmdHintPreflop'])
                    else:
                        cmd_hint = dictStrCustom['strTHCmdHintPreflop']
                else:
                    if can_check_now and can_bet_now:
                        cmd_hint = dictStrCustom.get('strTHCmdHintPostflopCheckBet', dictStrCustom.get('strTHCmdHintPostflopCheck', dictStrCustom['strTHCmdHintPostflop']))
                    elif can_check_now and (not can_bet_now):
                        cmd_hint = dictStrCustom.get('strTHCmdHintPostflopCheck', dictStrCustom['strTHCmdHintPostflop'])
                    elif (not can_check_now) and can_bet_now:
                        cmd_hint = dictStrCustom.get('strTHCmdHintPostflopBet', dictStrCustom['strTHCmdHintPostflop'])
                    else:
                        cmd_hint = dictStrCustom['strTHCmdHintPostflop']

            cmd_line = fmt('strTHStatusCmdHint', {'tCmdHint': cmd_hint})

            return fmt('strTHStatusBoard', {
                'tHeader': header,
                'tCommunity': community,
                'tSep': dictStrCustom['strTHStatusSeparator'],
                'tSeatLines': seat_lines,
                'tTurnLine': turn_line,
                'tCmdLine': cmd_line,
            })

        def send_private_cards_for_user(game: dict, tmp_hag: str, user_id: str) -> None:
            # 可能对应多个座位（例如多开/同群多号等）
            lines = []
            header = fmt('strTHPrivateCardsHeader', {'tGroupId': str(plugin_event.data.group_id)})
            lines.append(header)

            seat_blocks = []
            for p in game.get('players', []):
                if str(p.get('user_id')) != str(user_id):
                    continue
                if not p.get('hand_cards'):
                    continue
                sid = int(p['seat_id'])
                role_code = role_name_for_seat(game, sid)
                role_text = role_text_from_code(role_code)
                seat_line = fmt('strTHPrivateCardsSeatLine', {
                    'tSeatId': str(sid),
                    'tRoleText': role_text,
                })
                cards_line = fmt('strTHPrivateCardsCardsLine', {
                    'tHandCards': cards_to_text(p['hand_cards']),
                })
                seat_blocks.append('\n'.join([s for s in [seat_line, cards_line] if s]))

            if seat_blocks:
                # 多个座位块之间多一个空行，便于阅读
                lines.append('\n\n'.join(seat_blocks))

            lines.append(fmt('strTHPrivateCardsFooter'))
            msg = '\n'.join([s for s in lines if s])
            host_id = plugin_event.data.host_id if 'host_id' in plugin_event.data.__dict__ else None
            sendMsgByEvent(plugin_event, msg, str(user_id), 'private', host_id=host_id)

        def handle_hand_end_and_maybe_continue(game: dict, bot_hash: str, group_hash: str, tmp_hag: str, settlement: dict) -> None:
            lines = []

            # 先缓存本局各座位的位置文本：后面 remove_broke_players 会把玩家标记为 out，
            # 而 role_name_for_seat 默认不包含 out，导致“破产出局”位置显示为空。
            seat_role_text_map = {}
            for p in game.get('players', []):
                if p.get('left'):
                    continue
                try:
                    sid = int(p.get('seat_id'))
                except Exception:
                    continue
                try:
                    role_code = role_name_for_seat(game, sid)
                    seat_role_text_map[sid] = role_text_from_code(role_code)
                except Exception:
                    seat_role_text_map[sid] = ''

            if settlement.get('type') == 'single':
                win_sid = settlement.get('winner_seat_ids', [None])[0]
                pwin = find_player(game['players'], int(win_sid)) if win_sid is not None else None
                if pwin:
                    lines.append(fmt('strTHHandEndSingle', {
                        'tWinSeatId': str(win_sid),
                        'tWinName': str(pwin.get('nickname', '')),
                        'tWinAmount': str(settlement.get('amount', 0)),
                    }))
            else:
                lines.append(fmt('strTHHandEndShowdownHeader'))

                # 摊牌明细：按需求顺序输出
                # 1) 先显示公共牌
                board = list(game.get('community_cards', []))
                lines.append(fmt('strTHShowdownBoardLine', {
                    'tBoardCards': cards_to_text(board),
                }))

                # 公共牌与“摊牌明细”之间空一行
                lines.append('')

                # 2) 再逐座位显示底牌与凑出来的最佳 5 张
                lines.append(fmt('strTHShowdownRevealHeader'))
                show_players = [
                    p for p in game.get('players', [])
                    if p.get('status') != 'out' and not p.get('left') and p.get('hand_cards')
                ]
                for p in sorted(show_players, key=lambda x: int(x.get('seat_id', 0))):
                    sid = int(p.get('seat_id', 0))
                    role_text = seat_role_text_map.get(sid, '')
                    hand_cards = list(p.get('hand_cards', []))
                    fold_mark = '（已弃牌）' if p.get('status') == 'folded' else ''

                    cat, tb, best5 = evaluate_7(board + hand_cards)

                    lines.append(fmt('strTHShowdownSeatHoleLine', {
                        'tSeatId': str(sid),
                        'tSeatName': str(p.get('nickname', '')),
                        'tSeatRoleText': role_text,
                        'tFoldMark': fold_mark,
                        'tHandCards': cards_to_text(hand_cards),
                    }))
                    if p.get('status') != 'folded':
                        compact = format_best5_compact(int(cat), tb)
                        best5_ordered = order_best5_by_compact(list(best5), compact)
                        lines.append(fmt('strTHShowdownSeatMadeLine', {
                            'tSeatId': str(sid),
                            'tSeatName': str(p.get('nickname', '')),
                            'tSeatRoleText': role_text,
                            'tBest5': cards_to_text(list(best5_ordered)),
                        }))
                        lines.append(fmt('strTHShowdownSeatTypeLine', {
                            'tSeatId': str(sid),
                            'tSeatName': str(p.get('nickname', '')),
                            'tSeatRoleText': role_text,
                            'tHandType': hand_type_text(int(cat), list(best5)),
                        }))

                    # 座位块之间空一行，便于阅读
                    lines.append('')

                dist = settlement.get('distribution', [])
                refunds = settlement.get('refunds', []) or []
                pot_cnt = len(dist)

                # 双人局：按需求不显示“边池”，统一标记为“主池”
                alive_cnt = len([
                    p for p in game.get('players', [])
                    if p.get('status') != 'out' and not p.get('left')
                ])
                is_heads_up = alive_cnt <= 2
                for idx, d in enumerate(dist, start=1):
                    if is_heads_up:
                        pot_label = '主池'
                    else:
                        if pot_cnt <= 1:
                            pot_label = '底池'
                        else:
                            pot_label = '主池' if idx == 1 else f'边池{idx - 1}'
                    winners_txt = []
                    winners = list(d.get('winners', []))
                    pot_amount = int(d.get('pot', 0))
                    if winners:
                        share = pot_amount // len(winners)
                        rem = pot_amount % len(winners)
                        sid0 = min(int(x) for x in winners)
                        for sid in winners:
                            pp = find_player(game['players'], int(sid))
                            role_text = seat_role_text_map.get(int(sid), '')
                            win_amt = int(share)
                            if rem > 0 and int(sid) == int(sid0):
                                win_amt += int(rem)
                            winners_txt.append(fmt('strTHWinnerSeatName', {
                                'tSeatId': str(sid),
                                'tSeatName': str(pp.get('nickname', '')) if pp else '',
                                'tSeatRoleText': role_text,
                                'tWinAmount': str(win_amt),
                            }))
                    lines.append(fmt('strTHHandEndPotLine', {
                        'tPotIndex': str(idx),
                        'tPotLabel': pot_label,
                        'tPotAmount': str(pot_amount),
                        'tWinnersText': dictStrCustom['strTHWinnersSep'].join(winners_txt),
                    }))

                # 奖池明细与“破产出局”之间空一行
                if dist:
                    lines.append('')

                # 未被跟注退款展示
                if refunds:
                    for r in refunds:
                        try:
                            sid = int(r.get('seat_id'))
                        except Exception:
                            continue
                        amt = int(r.get('amount', 0))
                        if amt <= 0:
                            continue
                        pp = find_player(game['players'], sid)
                        role_text = seat_role_text_map.get(int(sid), '')
                        lines.append(fmt('strTHRefundLine', {
                            'tSeatId': str(sid),
                            'tSeatName': str(pp.get('nickname', '')) if pp else '',
                            'tSeatRoleText': role_text,
                            'tRefundAmount': str(amt),
                        }))
                    lines.append('')

            # 破产出局提示
            out_seats = remove_broke_players(game)
            for sid in out_seats:
                pp = find_player(game['players'], int(sid))
                role_text = seat_role_text_map.get(int(sid), '')
                lines.append(fmt('strTHBrokeOut', {
                    'tSeatId': str(sid),
                    'tSeatName': str(pp.get('nickname', '')) if pp else '',
                    'tSeatRoleText': role_text,
                }))

            # 结算信息一次性发出（避免拆成多条消息）
            if lines:
                replyMsg(plugin_event, '\n'.join([s for s in lines if s is not None]).rstrip())

            # 破产座位：直接从桌上移除（不再出现在下一手面板里）
            if out_seats:
                compact_players(game)

            # 移除本手已离场/被踢出的玩家
            game['players'] = [p for p in game.get('players', []) if not p.get('left')]

            auto_winner = check_auto_end(game)
            if auto_winner is not None:
                pwin = find_player(game['players'], int(auto_winner))
                if pwin:
                    reply_custom('strTHGameOnlyOneLeft', {
                        'tWinSeatId': str(auto_winner),
                        'tWinName': str(pwin.get('nickname', '')),
                    })
                # 重置房间
                new_data = texas_default()
                save_group_data(bot_hash, group_hash, new_data)
                return

            if game.get('end_flag'):
                # 最终排行
                ranking = sorted(
                    [p for p in game.get('players', []) if not p.get('left')],
                    key=lambda x: int(x.get('chips', 0)),
                    reverse=True,
                )
                lines = [fmt('strTHFinalRankingHeader')]
                for i, p in enumerate(ranking, start=1):
                    lines.append(fmt('strTHFinalRankingLine', {
                        'tRankNo': str(i),
                        'tSeatId': str(p.get('seat_id')),
                        'tSeatName': str(p.get('nickname', '')),
                        'tSeatChips': str(p.get('chips', 0)),
                    }))
                replyMsg(plugin_event, '\n'.join(lines))
                new_data = texas_default()
                save_group_data(bot_hash, group_hash, new_data)
                return

            # 继续下一手
            rotate_dealer(game)
            start_hand(game)
            save_group_data(bot_hash, group_hash, game)
            # 自动私聊发牌：按 user_id 去重发送（同一用户多个座位合并到一条私聊）
            sent_user_ids = set()
            for p in game.get('players', []):
                if p.get('status') == 'out':
                    continue
                uid = str(p.get('user_id'))
                if not uid or uid in sent_user_ids:
                    continue
                sent_user_ids.add(uid)
                send_private_cards_for_user(game, tmp_hag, uid)
            replyMsg(plugin_event, build_status_board(game, tmp_hag))

        # 仅处理本插件指令前缀
        if not isMatchWordStart(tmp_reast_str, ['dz', 'th'], isCommand=True):
            return

        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['dz', 'th'])
        tmp_reast_str = skipSpaceStart(tmp_reast_str)

        bot_hash = plugin_event.bot_info.hash
        if not flag_is_from_group:
            reply_custom('strTHErrNotInGroup')
            return
        group_hash = group_hash_from_hag(tmp_hagID)
        game = load_group_data(bot_hash, group_hash)

        # ----------------------------
        # 通用指令：无论开局与否
        # ----------------------------
        if isMatchWordStart(tmp_reast_str, ['list', 'players', 'player', '列表', '玩家'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['list', 'players', 'player', '列表', '玩家'])
            replyMsg(plugin_event, build_status_board(game, tmp_hagID))
            return

        # ----------------------------
        # 开局前指令
        # ----------------------------
        if isMatchWordStart(tmp_reast_str, ['create', '建局', '创建'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['create', '建局', '创建'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str).strip()

            if game.get('state') == 'playing':
                reply_custom('strTHErrAlreadyPlaying')
                return

            base = 1000
            if tmp_reast_str:
                try:
                    base = int(tmp_reast_str.split()[0])
                except Exception:
                    reply_custom('strTHErrInvalidNumber')
                    return
            if base < 1000 or base % 1000 != 0:
                reply_custom('strTHCreateFailStake')
                return
            bb, sb = compute_blinds(base)

            new_data = texas_default()
            new_data['state'] = 'waiting'
            new_data['base_stake'] = int(base)
            new_data['bb'] = int(bb)
            new_data['sb'] = int(sb)
            save_group_data(bot_hash, group_hash, new_data)
            reply_custom('strTHCreateSuccess', {
                'tBaseStake': str(base),
                'tBB': str(bb),
                'tSB': str(sb),
            })
            return

        if isMatchWordStart(tmp_reast_str, ['join', '加入'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['join', '加入'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str).strip()

            if game.get('state') == 'idle':
                reply_custom('strTHErrRoomNotFound')
                return
            if game.get('state') == 'playing':
                reply_custom('strTHErrAlreadyPlaying')
                return

            # QQ 平台在 join 时用好友列表验证是否可私聊
            user_id = str(plugin_event.data.user_id)
            if not TexasHoldem.function.qq_is_friend(plugin_event, user_id):
                reply_custom('strTHErrNeedFriendForPrivate')
                return

            base = int(game.get('base_stake', 1000))
            chips = base
            if tmp_reast_str:
                try:
                    chips = int(tmp_reast_str.split()[0])
                except Exception:
                    reply_custom('strTHErrInvalidNumber')
                    return
            if chips < base or chips % 1000 != 0:
                reply_custom('strTHJoinFailChips')
                return

            used = set(int(p['seat_id']) for p in game.get('players', []))
            seat_id = None
            for i in range(1, 11):
                if i not in used:
                    seat_id = i
                    break
            if seat_id is None:
                reply_custom('strTHJoinFailFull')
                return

            nickname = get_nickname(
                plugin_event,
                user_id,
                tmp_hagID,
                dictStrCustom.get('strTHUserFallbackPrefix', ''),
            )
            game['players'].append({
                'seat_id': int(seat_id),
                'user_id': user_id,
                'nickname': nickname,
                'chips': int(chips),
                'status': 'active',
                'current_bet': 0,
                'total_bet': 0,
                'hand_cards': [],
                'last_action': '',
            })
            game['join_order'].append(int(seat_id))
            if game.get('dealer_seat_id') is None:
                game['dealer_seat_id'] = int(seat_id)

            save_group_data(bot_hash, group_hash, game)
            reply_custom('strTHJoinSuccess', {
                'tName': nickname,
                'tSeatId': str(seat_id),
                'tChips': str(chips),
            })
            return

        if isMatchWordStart(tmp_reast_str, ['quit', '退出'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['quit', '退出'])
            if game.get('state') != 'waiting':
                reply_custom('strTHErrActionNotAllowed')
                return
            user_id = str(plugin_event.data.user_id)
            # 按加入顺序逆序移除（后加入的先退出）
            seat_to_remove = None
            for sid in reversed(game.get('join_order', [])):
                p = find_player(game.get('players', []), int(sid))
                if p and str(p.get('user_id')) == user_id:
                    seat_to_remove = int(sid)
                    break
            if seat_to_remove is None:
                reply_custom('strTHQuitFailNoSeat')
                return

            game['players'] = [p for p in game['players'] if int(p.get('seat_id')) != seat_to_remove]
            game['join_order'] = [sid for sid in game.get('join_order', []) if int(sid) != seat_to_remove]
            if len(game.get('players', [])) == 0:
                game['dealer_seat_id'] = None
            elif int(game.get('dealer_seat_id') or 0) == seat_to_remove:
                # 庄位离开：取当前最小座位号作为庄位兜底
                game['dealer_seat_id'] = min(int(p['seat_id']) for p in game['players'])

            save_group_data(bot_hash, group_hash, game)
            reply_custom('strTHQuitSuccess', {'tSeatId': str(seat_to_remove)})
            return

        if isMatchWordStart(tmp_reast_str, ['dismiss', '解散'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['dismiss', '解散'])
            if game.get('state') != 'waiting':
                reply_custom('strTHErrActionNotAllowed')
                return
            # 权限：1号位玩家 / 管理员 / 骰主
            seat1 = find_player(game.get('players', []), 1)
            user_id = str(plugin_event.data.user_id)
            if not (flag_is_from_group_admin or flag_is_from_master or (seat1 and str(seat1.get('user_id')) == user_id)):
                reply_custom('strTHErrNoPermission')
                return
            new_data = texas_default()
            save_group_data(bot_hash, group_hash, new_data)
            reply_custom('strTHDismissSuccess')
            return

        if isMatchWordStart(tmp_reast_str, ['start', '开始'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['start', '开始'])
            if game.get('state') != 'waiting':
                if game.get('state') == 'playing':
                    reply_custom('strTHErrAlreadyPlaying')
                else:
                    reply_custom('strTHErrRoomNotFound')
                return
            if len(game.get('players', [])) < 2:
                reply_custom('strTHStartFailNeedPlayers')
                return

            # 确保盲注与底注对应
            bb, sb = compute_blinds(int(game.get('base_stake', 1000)))
            game['bb'] = int(bb)
            game['sb'] = int(sb)

            game['state'] = 'playing'
            start_hand(game)
            save_group_data(bot_hash, group_hash, game)

            at_user_ids = []
            seen_user_ids = set()

            sender_uid = str(plugin_event.data.user_id)
            if sender_uid and sender_uid not in seen_user_ids:
                seen_user_ids.add(sender_uid)
                at_user_ids.append(sender_uid)

            for p in game.get('players', []):
                if p.get('status') == 'out':
                    continue
                uid = str(p.get('user_id'))
                if not uid or uid in seen_user_ids:
                    continue
                seen_user_ids.add(uid)
                at_user_ids.append(uid)

            at_all_text = ''
            for uid in at_user_ids:
                try:
                    at_all_text += OlivOS.messageAPI.PARA.at(uid).get_string_by_key('CQ')
                except Exception:
                    pass

            reply_custom('strTHStartSuccess', {'tAtAll': at_all_text}, at_user=False)
            # 自动私聊发牌：按 user_id 去重发送（同一用户多个座位合并到一条私聊）
            sent_user_ids = set()
            for p in game.get('players', []):
                if p.get('status') == 'out':
                    continue
                uid = str(p.get('user_id'))
                if not uid or uid in sent_user_ids:
                    continue
                sent_user_ids.add(uid)
                send_private_cards_for_user(game, tmp_hagID, uid)
            replyMsg(plugin_event, build_status_board(game, tmp_hagID))
            return

        # ----------------------------
        # 对局中指令
        # ----------------------------
        if isMatchWordStart(tmp_reast_str, ['info', '局势'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['info', '局势'])
            if game.get('state') != 'playing':
                reply_custom('strTHErrNotPlaying')
                return
            replyMsg(plugin_event, build_status_board(game, tmp_hagID))
            return

        if isMatchWordStart(tmp_reast_str, ['cards', '看牌', 'hand', 'show'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['cards', '看牌', 'hand', 'show'])
            if game.get('state') != 'playing':
                reply_custom('strTHCardsFailNotDealt')
                return
            user_id = str(plugin_event.data.user_id)
            send_private_cards_for_user(game, tmp_hagID, user_id)
            return

        if isMatchWordStart(tmp_reast_str, ['end', '结束'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['end', '结束'])
            if game.get('state') != 'playing':
                reply_custom('strTHErrNotPlaying')
                return
            game['end_flag'] = True
            save_group_data(bot_hash, group_hash, game)
            reply_custom('strTHEndFlagSet')
            return

        if isMatchWordStart(tmp_reast_str, ['stop', 'halt', '强制结束'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['stop', 'halt', '强制结束'])
            if not (flag_is_from_group_admin or flag_is_from_master):
                reply_custom('strTHErrNoPermission')
                return
            new_data = texas_default()
            save_group_data(bot_hash, group_hash, new_data)
            reply_custom('strTHStopSuccess')
            return

        if isMatchWordStart(tmp_reast_str, ['kick', '踢'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['kick', '踢'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str).strip()
            if not (flag_is_from_group_admin or flag_is_from_master):
                reply_custom('strTHErrNoPermission')
                return
            if game.get('state') != 'playing':
                reply_custom('strTHErrNotPlaying')
                return
            try:
                seat_id = int(tmp_reast_str.split()[0])
            except Exception:
                reply_custom('strTHErrInvalidSeat')
                return
            p = find_player(game.get('players', []), int(seat_id))
            if not p:
                reply_custom('strTHErrInvalidSeat')
                return
            # 先缓存展示用信息（避免后续把玩家标记为 out 导致位置计算为空）
            seat_name = str(p.get('nickname', ''))
            role_code = role_name_for_seat(game, int(seat_id))
            role_text = role_text_from_code(role_code)
            turn_mark = ''
            if int(game.get('acting_seat_id') or 0) == int(seat_id) and p.get('status') == 'active':
                turn_mark = fmt('strTHTurnMark')

            # 剩余筹码罚没进底池；保留已投入记录以保证边池结算正确
            forfeit_stack = int(p.get('chips', 0))
            game['pot'] += forfeit_stack
            game['dead_money'] = int(game.get('dead_money', 0)) + forfeit_stack

            p['chips'] = 0
            p['status'] = 'out'
            p['hand_cards'] = []
            p['left'] = True
            game['need_action_seat_ids'] = [
                sid for sid in game.get('need_action_seat_ids', []) if int(sid) != int(seat_id)
            ]
            game['join_order'] = [sid for sid in game.get('join_order', []) if int(sid) != int(seat_id)]

            # 如果被踢的是当前行动位：先置空，再在下方重新找可行动座位
            if int(game.get('acting_seat_id') or 0) == int(seat_id):
                # 寻找下一个可行动座位
                game['acting_seat_id'] = None
                # 从待行动列表中移除该座位
                game['need_action_seat_ids'] = [sid for sid in game.get('need_action_seat_ids', []) if int(sid) != int(seat_id)]
                game['acting_seat_id'] = next_pending_actor(game, int(seat_id))

            save_group_data(bot_hash, group_hash, game)
            reply_custom('strTHKickSuccess', {
                'tSeatId': str(seat_id),
                'tSeatName': seat_name,
                'tSeatRoleText': role_text,
                'tSeatTurnMark': turn_mark,
                'tForfeit': str(forfeit_stack),
            })
            # 若仍可继续则展示更新后的局势面板
            if game.get('state') == 'playing' and len(game.get('players', [])) >= 1:
                replyMsg(plugin_event, build_status_board(game, tmp_hagID))
            return

        # 动作指令（必须在对局中）
        if game.get('state') != 'playing':
            return

        acting = game.get('acting_seat_id')
        if acting is None:
            return
        p_act = find_player(game.get('players', []), int(acting))
        if not p_act:
            return
        if str(p_act.get('user_id')) != str(plugin_event.data.user_id):
            reply_custom('strTHErrNotYourTurn')
            return

        # 弃牌
        if isMatchWordStart(tmp_reast_str, ['fold', '弃', '弃牌'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['fold', '弃', '弃牌'])
            if isMatchWordStart(tmp_reast_str, ['弃'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['弃'])
            apply_fold(game, int(acting))

            # 弃牌公开底牌
            if p_act.get('hand_cards'):
                role_code = role_name_for_seat(game, int(acting))
                role_text = role_text_from_code(role_code)
                reply_custom('strTHFoldReveal', {
                    'tSeatId': str(acting),
                    'tSeatName': str(p_act.get('nickname', '')),
                    'tSeatRoleText': role_text,
                    'tHandCards': cards_to_text(list(p_act.get('hand_cards', []))),
                })

        # 跟注
        elif isMatchWordStart(tmp_reast_str, ['call', '跟', '跟注'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['call', '跟', '跟注'])
            if isMatchWordStart(tmp_reast_str, ['跟'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['跟'])
            apply_call_or_check(game, int(acting))

        # 过牌
        elif isMatchWordStart(tmp_reast_str, ['check', '过', '过牌'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['check', '过', '过牌'])
            if isMatchWordStart(tmp_reast_str, ['过'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['过'])
            # 需要跟注为 0 时，过牌与跟注等价
            apply_call_or_check(game, int(acting))

        # 下注（本街首次投入）
        elif isMatchWordStart(tmp_reast_str, ['bet', '下', '下注'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['bet', '下', '下注'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str).strip()
            if isMatchWordStart(tmp_reast_str, ['下'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['下'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str).strip()
            try:
                amt = int(tmp_reast_str.split()[0])
            except Exception:
                reply_custom('strTHErrInvalidNumber')
                return
            ok, reason = apply_bet(game, int(acting), int(amt))
            if not ok:
                if reason == 'too_small':
                    reply_custom('strTHErrBetTooSmall', {'tBB': str(game.get('bb', 0))})
                else:
                    reply_custom('strTHErrActionNotAllowed')
                return

        # 加注
        elif isMatchWordStart(tmp_reast_str, ['raise', '加', '加注'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['raise', '加', '加注'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str).strip()
            if isMatchWordStart(tmp_reast_str, ['加'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['加'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str).strip()
            delta = None
            if tmp_reast_str:
                try:
                    delta = int(tmp_reast_str.split()[0])
                except Exception:
                    reply_custom('strTHErrInvalidNumber')
                    return
            if delta is None:
                delta = int(game.get('min_raise', 0))
            ok, reason, _ = apply_raise(game, int(acting), int(delta))
            if not ok:
                if reason == 'too_small':
                    reply_custom('strTHErrRaiseTooSmall', {'tMinRaise': str(game.get('min_raise', 0))})
                else:
                    reply_custom('strTHErrActionNotAllowed')
                return

        # 全压
        elif isMatchWordStart(tmp_reast_str, ['allin', '全压', '梭哈', '全', 'all in'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['allin', '全压', '梭哈', '全', 'all in'])
            if isMatchWordStart(tmp_reast_str, ['全'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['全'])
            apply_allin(game, int(acting))

        # 离场（本手弃掉剩余筹码并离开）
        elif isMatchWordStart(tmp_reast_str, ['leave', '离场'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['leave', '离场'])
            seat_id = int(acting)
            p = find_player(game.get('players', []), seat_id)
            if not p:
                reply_custom('strTHErrSeatNotFoundForUser')
                return

            # 先缓存展示用信息（避免后续把玩家标记为 out 导致位置计算为空）
            seat_name = str(p.get('nickname', ''))
            role_code = role_name_for_seat(game, int(seat_id))
            role_text = role_text_from_code(role_code)
            turn_mark = fmt('strTHTurnMark')

            forfeit_stack = int(p.get('chips', 0))
            game['pot'] += forfeit_stack
            game['dead_money'] = int(game.get('dead_money', 0)) + forfeit_stack
            p['chips'] = 0
            p['status'] = 'out'
            p['hand_cards'] = []
            p['left'] = True
            game['join_order'] = [sid for sid in game.get('join_order', []) if int(sid) != seat_id]
            game['acting_seat_id'] = None
            game['need_action_seat_ids'] = [sid for sid in game.get('need_action_seat_ids', []) if int(sid) != seat_id]
            game['acting_seat_id'] = next_pending_actor(game, seat_id)
            save_group_data(bot_hash, group_hash, game)
            reply_custom('strTHLeaveSuccess', {
                'tSeatId': str(seat_id),
                'tSeatName': seat_name,
                'tSeatRoleText': role_text,
                'tSeatTurnMark': turn_mark,
                'tForfeit': str(forfeit_stack),
            })
            # 离场后可能立刻满足结束条件
            if len([p for p in game.get('players', []) if p.get('status') in ('active', 'allin')]) <= 1:
                settlement = settle_showdown(game)
                handle_hand_end_and_maybe_continue(game, bot_hash, group_hash, tmp_hagID, settlement)
                return
            replyMsg(plugin_event, build_status_board(game, tmp_hagID))
            return
        else:
            return

        # 动作后：推进行动位 / 推进街道 / 进入摊牌
        # 确保行动位会前进：若仍有人需要行动则选下一个
        if is_betting_round_over(game):
            # 若仅剩 1 名仍在争夺底池的玩家，则立刻结算
            if len([p for p in game.get('players', []) if p.get('status') in ('active', 'allin')]) <= 1:
                settlement = settle_showdown(game)
                handle_hand_end_and_maybe_continue(game, bot_hash, group_hash, tmp_hagID, settlement)
                return

            if game.get('street') != 'showdown':
                advance_street(game)

            # 若本局已无人可行动（全部为 allin 或 folded），则自动补齐公共牌直到摊牌
            # 否则会出现 acting 为空、指令为空的“卡住面板”。
            while game.get('street') != 'showdown':
                active_cnt = len([p for p in game.get('players', []) if p.get('status') == 'active'])
                allin_cnt = len([p for p in game.get('players', []) if p.get('status') == 'allin'])

                # 只剩 0 个 active：肯定无需行动，直接补牌
                if active_cnt == 0:
                    advance_street(game)
                    continue

                # 有人 allin 且只剩 1 个 active：也无需继续行动，直接补牌到摊牌
                if allin_cnt > 0 and active_cnt <= 1:
                    advance_street(game)
                    continue

                break
            if game.get('street') == 'showdown':
                settlement = settle_showdown(game)
                handle_hand_end_and_maybe_continue(game, bot_hash, group_hash, tmp_hagID, settlement)
                return

            # 下注轮结束并推进街道后，acting_seat_id 已在 advance_street 内正确初始化
        else:
            # 下一个行动位（下注轮未结束）
            game['acting_seat_id'] = next_pending_actor(game, int(acting))

        save_group_data(bot_hash, group_hash, game)
        replyMsg(plugin_event, build_status_board(game, tmp_hagID))
        return