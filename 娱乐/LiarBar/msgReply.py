# -*- encoding: utf-8 -*-
'''
LiarBar 回复与命令处理。
命令统一要求前缀：.lb
出牌命令建议私聊 bot 发送（避免暴露手牌）。
'''

import random

import OlivOS
import OlivaDiceCore
import LiarBar


def unity_init(plugin_event, Proc):
    pass


def data_init(plugin_event, Proc):
    LiarBar.function.get_liarbar_data_path()
    LiarBar.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])


def unity_reply(plugin_event, Proc):
    OlivaDiceCore.userConfig.setMsgCount()
    dictTValue = OlivaDiceCore.msgCustom.dictTValue.copy()
    dictTValue['tUserName'] = plugin_event.data.sender.get('name', '')
    dictTValue['tName'] = plugin_event.data.sender.get('name', '')
    dictStrCustom = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]
    dictGValue = OlivaDiceCore.msgCustom.dictGValue
    dictTValue.update(dictGValue)
    dictTValue = OlivaDiceCore.msgCustomManager.dictTValueInit(plugin_event, dictTValue)

    valDict = {
        'dictTValue': dictTValue,
        'dictStrCustom': dictStrCustom,
        'tmp_platform': plugin_event.platform.get('platform'),
    }

    replyMsg = OlivaDiceCore.msgReply.replyMsg
    isMatchWordStart = OlivaDiceCore.msgReply.isMatchWordStart
    getMatchWordStartRight = OlivaDiceCore.msgReply.getMatchWordStartRight
    skipSpaceStart = OlivaDiceCore.msgReply.skipSpaceStart
    skipToRight = OlivaDiceCore.msgReply.skipToRight
    msgIsCommand = OlivaDiceCore.msgReply.msgIsCommand

    def fmt(key: str, extra: dict = None) -> str:
        tmp = dictTValue.copy()
        if extra:
            tmp.update(extra)
        try:
            return str(OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom.get(key, ''), tmp)).strip()
        except Exception:
            return ''

    # 解析命令
    tmp_reast_str = plugin_event.data.message
    flag_force_reply = False

    if isMatchWordStart(tmp_reast_str, '[CQ:reply,id='):
        tmp_reast_str = skipToRight(tmp_reast_str, ']')
        tmp_reast_str = tmp_reast_str[1:]

    [tmp_reast_str, flag_is_command] = msgIsCommand(
        tmp_reast_str,
        OlivaDiceCore.crossHook.dictHookList['prefix']
    )
    if not flag_is_command:
        return

    tmp_reast_str = skipSpaceStart(tmp_reast_str)

    # 统一要求 lb 前缀（最小改动风格）
    if not isMatchWordStart(tmp_reast_str, ['lb'], isCommand=True):
        return
    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['lb'])
    tmp_reast_str = skipSpaceStart(tmp_reast_str)

    # 平台/权限/群信息
    flag_is_from_group = plugin_event.plugin_info.get('func_type') == 'group_message'
    flag_is_from_private = plugin_event.plugin_info.get('func_type') == 'private_message'

    tmp_hagID = None
    if flag_is_from_group:
        if plugin_event.data.host_id is not None:
            tmp_hagID = '%s|%s' % (str(plugin_event.data.host_id), str(plugin_event.data.group_id))
        else:
            tmp_hagID = str(plugin_event.data.group_id)

    bot_hash = plugin_event.bot_info.hash
    user_hash = OlivaDiceCore.userConfig.getUserHash(
        plugin_event.data.user_id,
        'user',
        plugin_event.platform.get('platform')
    )

    # master / 群管理权限
    flag_is_from_master = OlivaDiceCore.ordinaryInviteManager.isInMasterList(
        plugin_event.bot_info.hash,
        user_hash
    )
    flag_is_group_admin = False
    if flag_is_from_group and 'role' in plugin_event.data.sender:
        if plugin_event.data.sender.get('role') in ['owner', 'admin', 'sub_admin']:
            flag_is_group_admin = True

    # 工具函数引用
    load_group_data = LiarBar.function.load_group_data
    save_group_data = LiarBar.function.save_group_data
    load_user_data = LiarBar.function.load_user_data
    save_user_data = LiarBar.function.save_user_data

    def group_hash_from_hag(tmp_hag: str) -> str:
        return OlivaDiceCore.userConfig.getUserHash(
            tmp_hag,
            'group',
            plugin_event.platform.get('platform')
        )

    def bind_user_to_group(group_hash: str):
        ud = load_user_data(bot_hash, user_hash)
        ud['last_group_hash'] = group_hash
        try:
            if flag_is_from_group:
                ud['last_group_id'] = str(plugin_event.data.group_id)
                ud['last_host_id'] = str(plugin_event.data.host_id) if plugin_event.data.host_id is not None else None
        except Exception:
            pass
        save_user_data(bot_hash, user_hash, ud)

    def get_bound_group_hash() -> str:
        ud = load_user_data(bot_hash, user_hash)
        return ud.get('last_group_hash')

    def get_bound_group_id_and_host_id() -> tuple:
        ud = load_user_data(bot_hash, user_hash)
        return ud.get('last_group_id'), ud.get('last_host_id')

    def get_best_hagID_for_nickname() -> str:
        if tmp_hagID is not None:
            return str(tmp_hagID)
        gid, hid = get_bound_group_id_and_host_id()
        if gid is None:
            return None
        if hid is not None:
            return '%s|%s' % (str(hid), str(gid))
        return str(gid)

    def refresh_player_nicknames(game: dict) -> None:
        hagID = get_best_hagID_for_nickname()
        for p in game.get('players', []) or []:
            uid = p.get('user_id')
            if uid is None:
                continue
            uid = str(uid)
            if not uid:
                continue
            p['nickname'] = LiarBar.function.get_nickname(plugin_event, uid, hagID)

    def get_group_game(group_hash: str) -> dict:
        game = load_group_data(bot_hash, group_hash)
        refresh_player_nicknames(game)
        return game

    def save_group_game(group_hash: str, game: dict) -> None:
        save_group_data(bot_hash, group_hash, game)

    def state_text(game: dict) -> str:
        st = game.get('state')
        if st == 'idle':
            return fmt('strLBStateIdle')
        if st == 'waiting':
            return fmt('strLBStateWaiting')
        if st == 'playing':
            return fmt('strLBStatePlaying')
        return str(st)

    def at_user(uid: str) -> str:
        try:
            return OlivOS.messageAPI.PARA.at(str(uid)).get_string_by_key('CQ')
        except Exception:
            return ''

    def can_manage() -> bool:
        return flag_is_from_master or flag_is_group_admin

    def ensure_group_only() -> bool:
        if not flag_is_from_group:
            replyMsg(plugin_event, fmt('strLBErrNotInGroup'), False)
            return False
        return True

    def build_status_board(game: dict, group_hash: str) -> str:
        seats = sorted([int(p.get('seat_id')) for p in game.get('players', [])])
        acting = game.get('turn_seat_id')

        header = fmt('strLBStatusHeader', {
            'tStateText': state_text(game),
            'tRealCardText': LiarBar.function.real_card_text(game.get('real_card'), dictStrCustom) if game.get('real_card') else '',
        })

        seat_lines = []
        for sid in seats:
            p = LiarBar.function.find_player(game, sid)
            if not p:
                continue
            turn_mark = ''
            if acting is not None and int(acting) == sid and p.get('status') == 'active':
                turn_mark = fmt('strLBTurnMark')
            seat_lines.append(fmt('strLBStatusSeatLine', {
                'tSeatId': str(sid),
                'tSeatName': str(p.get('nickname', '')),
                'tSeatAt': at_user(str(p.get('user_id'))),
                'tSeatStatusText': LiarBar.function.seat_status_text(p, dictStrCustom),
                'tSeatTurnMark': turn_mark,
                'tHandCount': str(len(p.get('hand', []))),
                'tAttempts': str(p.get('attempts', 0)),
            }))

        turn_line = ''
        cmd_hint = ''
        if acting is not None:
            p_turn = LiarBar.function.find_player(game, int(acting))
            if p_turn:
                turn_line = fmt('strLBStatusTurnLine', {
                    'tTurnSeatId': str(acting),
                    'tTurnName': str(p_turn.get('nickname', '')),
                    'tTurnStatusText': LiarBar.function.seat_status_text(p_turn, dictStrCustom),
                    'tTurnAt': at_user(str(p_turn.get('user_id'))),
                })

        if game.get('state') in ['idle', 'waiting']:
            cmd_hint = dictStrCustom.get('strLBCmdHintWaiting', '')
        else:
            cmd_hint = dictStrCustom.get('strLBCmdHintPlaying', '')

        cmd_line = fmt('strLBStatusCmdHint', {'tCmdHint': cmd_hint})

        return fmt('strLBStatusBoard', {
            'tHeader': header,
            'tSep': dictStrCustom.get('strLBStatusSeparator', '------------------------------'),
            'tSeatLines': '\n'.join(seat_lines),
            'tTurnLine': turn_line,
            'tCmdLine': cmd_line,
        })

    # ----------------------------
    # 指令实现
    # ----------------------------

    # .lb status
    if isMatchWordStart(tmp_reast_str, ['status'], isCommand=True):
        if not ensure_group_only():
            return
        gh = group_hash_from_hag(tmp_hagID)
        bind_user_to_group(gh)
        game = get_group_game(gh)
        replyMsg(plugin_event, build_status_board(game, gh).strip(), False)
        return

    # .lb list（无论开局与否：查看当前玩家/座位）
    if isMatchWordStart(tmp_reast_str, ['list', 'players', 'player', '列表', '玩家'], isCommand=True):
        if not ensure_group_only():
            return
        gh = group_hash_from_hag(tmp_hagID)
        bind_user_to_group(gh)
        game = get_group_game(gh)
        replyMsg(plugin_event, build_status_board(game, gh).strip(), False)
        return

    # .lb join
    if isMatchWordStart(tmp_reast_str, ['join'], isCommand=True):
        if not ensure_group_only():
            return
        gh = group_hash_from_hag(tmp_hagID)
        bind_user_to_group(gh)
        game = get_group_game(gh)

        max_players = int(dictGValue.get('gLBMaxPlayers', game.get('max_players', 6)))
        min_players = int(dictGValue.get('gLBMinPlayers', game.get('min_players', 2)))
        game['max_players'] = max_players
        game['min_players'] = min_players

        if game.get('state') == 'idle':
            game['state'] = 'waiting'

        if game.get('state') == 'playing':
            replyMsg(plugin_event, fmt('strLBErrAlreadyStarted'), False)
            return

        uid = str(plugin_event.data.user_id)

        # QQ 平台在 join 时用好友列表验证是否可私聊
        if not LiarBar.function.qq_is_friend(plugin_event, uid):
            replyMsg(plugin_event, fmt('strLBErrNeedFriendForPrivate'), False)
            return

        if LiarBar.function.find_player_by_user(game, uid):
            p_exist = LiarBar.function.find_player_by_user(game, uid)
            replyMsg(plugin_event, fmt('strLBJoinFailAlreadyIn', {
                'tName': str(p_exist.get('nickname', '')) if p_exist else '',
                'tAt': at_user(uid),
            }), False)
            return

        if len(game.get('players', [])) >= max_players:
            replyMsg(plugin_event, fmt('strLBErrRoomFull', {'tMaxPlayers': str(max_players)}), False)
            return

        seat_id = 1
        used = set([int(p.get('seat_id')) for p in game.get('players', [])])
        while seat_id in used:
            seat_id += 1

        p = {
            'seat_id': seat_id,
            'user_id': uid,
            'nickname': LiarBar.function.get_nickname(plugin_event, uid, get_best_hagID_for_nickname()),
            'status': 'active',
            'hand': [],
            'attempts': 0,
        }
        game['players'].append(p)
        game['join_order'].append(seat_id)

        save_group_game(gh, game)
        replyMsg(plugin_event, fmt('strLBJoinSuccess', {
            'tName': p['nickname'],
            'tAt': at_user(uid),
            'tSeatId': str(seat_id),
        }), False)
        return

    # .lb end（管理/群主/骰主）
    if isMatchWordStart(tmp_reast_str, ['exit', 'end', 'dismiss'], isCommand=True):
        if not ensure_group_only():
            return
        if not can_manage():
            replyMsg(plugin_event, fmt('strLBErrNoPermission'), False)
            return
        gh = group_hash_from_hag(tmp_hagID)
        bind_user_to_group(gh)
        game = LiarBar.function.liarbar_default()
        save_group_game(gh, game)
        replyMsg(plugin_event, fmt('strLBEndSuccess'), False)
        return

    # .lb leave（个人离场：开局前=退出房间；开局后=离场）
    if isMatchWordStart(tmp_reast_str, ['leave'], isCommand=True):
        if not ensure_group_only():
            return
        gh = group_hash_from_hag(tmp_hagID)
        bind_user_to_group(gh)
        game = get_group_game(gh)

        uid = str(plugin_event.data.user_id)
        p = LiarBar.function.find_player_by_user(game, uid)
        if not p or p.get('status') != 'active':
            replyMsg(plugin_event, fmt('strLBErrNotInGame'), False)
            return

        seat_id = int(p.get('seat_id'))

        # 开局前：直接移除
        if game.get('state') != 'playing':
            game['players'] = [x for x in game.get('players', []) if str(x.get('user_id')) != uid]
            game['join_order'] = [sid for sid in game.get('join_order', []) if int(sid) != seat_id]
            if len(game.get('players', [])) == 0:
                game = LiarBar.function.liarbar_default()
            save_group_game(gh, game)
            replyMsg(plugin_event, fmt('strLBExitSuccess', {
                'tSeatId': str(seat_id),
                'tSeatName': str(p.get('nickname', '')),
                'tSeatAt': at_user(str(p.get('user_id'))),
                'tSeatStatusText': fmt('strLBSeatStatusExit'),
            }), False)
            return

        # 开局后：标记离场
        p['status'] = 'left'
        p['hand'] = []

        # 若离场导致活人不足则结束
        alive = LiarBar.function.alive_seats(game)
        if len(alive) < 2:
            game = LiarBar.function.liarbar_default()
            save_group_game(gh, game)
            replyMsg(plugin_event, fmt('strLBLeaveSuccess', {
                'tSeatId': str(seat_id),
                'tSeatName': str(p.get('nickname', '')),
                'tSeatAt': at_user(str(p.get('user_id'))),
                'tSeatStatusText': fmt('strLBSeatStatusLeft'),
            }) + '\n' + fmt('strLBEndSuccess'), False)
            return

        # 调整回合
        if game.get('turn_seat_id') == seat_id:
            game['turn_seat_id'] = LiarBar.function.compute_next_turn_seat(game, seat_id)

        save_group_game(gh, game)
        replyMsg(plugin_event, fmt('strLBLeaveSuccess', {
            'tSeatId': str(seat_id),
            'tSeatName': str(p.get('nickname', '')),
            'tSeatAt': at_user(str(p.get('user_id'))),
            'tSeatStatusText': fmt('strLBSeatStatusLeft'),
        }), False)
        return

    # .lb start
    if isMatchWordStart(tmp_reast_str, ['start'], isCommand=True):
        if not ensure_group_only():
            return
        gh = group_hash_from_hag(tmp_hagID)
        bind_user_to_group(gh)
        game = get_group_game(gh)

        if game.get('state') == 'playing':
            replyMsg(plugin_event, fmt('strLBErrAlreadyStarted'), False)
            return

        max_players = int(dictGValue.get('gLBMaxPlayers', game.get('max_players', 6)))
        min_players = int(dictGValue.get('gLBMinPlayers', game.get('min_players', 2)))
        game['max_players'] = max_players
        game['min_players'] = min_players

        players = [p for p in game.get('players', []) if p.get('status') == 'active']
        if len(players) < min_players:
            replyMsg(plugin_event, fmt('strLBErrNeedMorePlayers', {'tMinPlayers': str(min_players)}), False)
            return

        # 发牌并开启回合
        hands, real_card = LiarBar.function.deal_round(len(players))
        for i, p in enumerate(players):
            p['hand'] = hands[i]
            p['attempts'] = int(p.get('attempts', 0))

        game['round_no'] = int(game.get('round_no', 0)) + 1
        game['real_card'] = real_card
        game['last_play'] = None
        game['last_seat_id'] = None
        game['state'] = 'playing'

        # 起手玩家：随机一个活人
        seats = [int(p.get('seat_id')) for p in players]
        game['turn_seat_id'] = random.choice(seats)

        save_group_game(gh, game)

        # @ 指令发起人 + @ 所有参与玩家（写入自定义回复，占位符 tAtAll；replyMsg 的 at 参数保持 False）
        at_user_ids = []
        seen_user_ids = set()
        sender_uid = str(plugin_event.data.user_id)
        if sender_uid and sender_uid not in seen_user_ids:
            seen_user_ids.add(sender_uid)
            at_user_ids.append(sender_uid)
        for p in players:
            uid = str(p.get('user_id'))
            if not uid or uid in seen_user_ids:
                continue
            seen_user_ids.add(uid)
            at_user_ids.append(uid)
        at_all_text = ''.join([at_user(uid) for uid in at_user_ids])

        # 私聊发牌（每人一条）
        for p in players:
            uid = str(p.get('user_id'))
            msg_lines = [
                fmt('strLBPrivateCardsHeader', {'tGroupId': str(plugin_event.data.group_id)}).strip(),
                fmt('strLBPrivateCardsLine', {'tHandText': LiarBar.function.count_hand_text(p.get('hand', []))}).strip(),
                fmt('strLBPrivateCardsFooter').strip(),
            ]
            try:
                LiarBar.function.sendMsgByEvent(
                    plugin_event,
                    '\n'.join([x for x in msg_lines if x]),
                    str(uid),
                    'private',
                    host_id=None
                )
            except Exception:
                pass

        # 开局公告
        p_turn = LiarBar.function.find_player(game, int(game.get('turn_seat_id')))
        start_text = fmt('strLBStartSuccess', {
            'tRealCardText': LiarBar.function.real_card_text(real_card, dictStrCustom),
            'tTurnSeatId': str(game.get('turn_seat_id')),
            'tTurnName': str(p_turn.get('nickname', '')) if p_turn else '',
            'tTurnAt': at_user(str(p_turn.get('user_id'))) if p_turn else '',
        })

        msg_parts = []
        deal_notice = fmt('strLBDealNotice', {'tAtAll': at_all_text})
        if deal_notice:
            msg_parts.append(deal_notice)
        if start_text:
            msg_parts.append(start_text)
        replyMsg(plugin_event, '\n'.join(msg_parts), False)
        return

    # .lb hand（群聊触发私聊）
    if isMatchWordStart(tmp_reast_str, ['hand','show','看牌'], isCommand=True):
        if not ensure_group_only():
            return
        gh = group_hash_from_hag(tmp_hagID)
        bind_user_to_group(gh)
        game = get_group_game(gh)
        if game.get('state') != 'playing':
            replyMsg(plugin_event, fmt('strLBErrNotStarted'), False)
            return

        uid = str(plugin_event.data.user_id)
        p = LiarBar.function.find_player_by_user(game, uid)
        if not p or p.get('status') != 'active':
            replyMsg(plugin_event, fmt('strLBErrNotInGame'), False)
            return

        msg_lines = [
            fmt('strLBPrivateCardsHeader', {'tGroupId': str(plugin_event.data.group_id)}).strip(),
            fmt('strLBPrivateCardsLine', {'tHandText': LiarBar.function.count_hand_text(p.get('hand', []))}).strip(),
            fmt('strLBPrivateCardsFooter').strip(),
        ]
        LiarBar.function.sendMsgByEvent(
            plugin_event,
            '\n'.join([x for x in msg_lines if x]),
            str(uid),
            'private',
            host_id=None
        )
        return

    # .lb doubt（群内）
    if isMatchWordStart(tmp_reast_str, ['doubt', '质疑'], isCommand=True):
        if not ensure_group_only():
            return
        gh = group_hash_from_hag(tmp_hagID)
        bind_user_to_group(gh)
        game = get_group_game(gh)
        if game.get('state') != 'playing':
            replyMsg(plugin_event, fmt('strLBErrNotStarted'), False)
            return

        uid = str(plugin_event.data.user_id)
        p_me = LiarBar.function.find_player_by_user(game, uid)
        if not p_me or p_me.get('status') != 'active':
            replyMsg(plugin_event, fmt('strLBErrNotInGame'), False)
            return

        if int(game.get('turn_seat_id') or -1) != int(p_me.get('seat_id')):
            replyMsg(plugin_event, fmt('strLBErrNotYourTurn'), False)
            return

        last_play = game.get('last_play')
        if not last_play or not last_play.get('cards'):
            replyMsg(plugin_event, fmt('strLBErrNoLastPlay'), False)
            return

        last_seat_id = int(last_play.get('seat_id'))
        p_last = LiarBar.function.find_player(game, last_seat_id)

        # 宣告
        replyMsg(plugin_event, fmt('strLBDoubtAnnounce', {
            'tDoubterSeatId': str(p_me.get('seat_id')),
            'tDoubterName': str(p_me.get('nickname', '')),
            'tDoubterAt': at_user(uid),
            'tLastSeatId': str(last_seat_id),
            'tLastName': str(p_last.get('nickname', '')) if p_last else '',
            'tLastAt': at_user(str(p_last.get('user_id'))) if p_last else '',
        }), False)

        real_card = game.get('real_card')
        last_cards = list(last_play.get('cards', []))

        # 恶魔牌：永真，且质疑触发群体惩罚
        if last_play.get('is_demon'):
            replyMsg(plugin_event, fmt('strLBDoubtReveal', {
                'tLastCardsText': str(last_cards),
                'tRealCardText': LiarBar.function.real_card_text(real_card, dictStrCustom),
                'tLastSeatId': str(last_seat_id),
                'tLastName': str(p_last.get('nickname', '')) if p_last else '',
                'tLastAt': at_user(str(p_last.get('user_id'))) if p_last else '',
            }), False)
            replyMsg(plugin_event, fmt('strLBDemonPunishHeader', {
                'tDoubterAt': at_user(uid),
                'tDoubterSeatId': str(p_me.get('seat_id')),
                'tDoubterName': str(p_me.get('nickname', '')),
                'tLastSeatId': str(last_seat_id),
                'tLastName': str(p_last.get('nickname', '')) if p_last else '',
                'tLastAt': at_user(str(p_last.get('user_id'))) if p_last else '',
            }), False)

            demon_player_uid = str(p_last.get('user_id')) if p_last else None

            # 除出牌者外，其他所有 active 玩家都自罚一枪（包括已出完牌者）
            for p in [x for x in game.get('players', []) if x.get('status') == 'active']:
                if demon_player_uid is not None and str(p.get('user_id')) == demon_player_uid:
                    continue
                replyMsg(plugin_event, fmt('strLBDemonPunishEach', {
                    'tTargetAt': at_user(str(p.get('user_id'))),
                    'tTargetSeatId': str(p.get('seat_id')),
                    'tTargetName': str(p.get('nickname', '')),
                }), False)
                attempts = int(p.get('attempts', 0))
                hit_blank = LiarBar.function.shot(attempts)
                p['attempts'] = attempts + 1
                if hit_blank:
                    replyMsg(plugin_event, fmt('strLBShootBlank', {
                        'tTargetAt': at_user(str(p.get('user_id'))),
                        'tTargetSeatId': str(p.get('seat_id')),
                        'tTargetName': str(p.get('nickname', '')),
                    }), False)
                else:
                    p['status'] = 'dead'
                    p['hand'] = []
                    replyMsg(plugin_event, fmt('strLBShootReal', {
                        'tTargetAt': at_user(str(p.get('user_id'))),
                        'tTargetSeatId': str(p.get('seat_id')),
                        'tTargetName': str(p.get('nickname', '')),
                    }), False)

        else:
            # 只要存在非真牌，则质疑成功
            success = False
            for c in last_cards:
                if c != real_card:
                    success = True
                    break

            replyMsg(plugin_event, fmt('strLBDoubtReveal', {
                'tLastCardsText': str(last_cards),
                'tRealCardText': LiarBar.function.real_card_text(real_card, dictStrCustom),
                'tLastSeatId': str(last_seat_id),
                'tLastName': str(p_last.get('nickname', '')) if p_last else '',
                'tLastAt': at_user(str(p_last.get('user_id'))) if p_last else '',
            }), False)

            if success:
                replyMsg(plugin_event, fmt('strLBDoubtSuccess', {
                    'tDoubterAt': at_user(uid),
                    'tDoubterSeatId': str(p_me.get('seat_id')),
                    'tDoubterName': str(p_me.get('nickname', '')),
                }), False)
                hit_player = p_last
            else:
                replyMsg(plugin_event, fmt('strLBDoubtFail', {
                    'tDoubterAt': at_user(uid),
                    'tDoubterSeatId': str(p_me.get('seat_id')),
                    'tDoubterName': str(p_me.get('nickname', '')),
                }), False)
                hit_player = p_me

            if hit_player:
                attempts = int(hit_player.get('attempts', 0))
                hit_blank = LiarBar.function.shot(attempts)
                hit_player['attempts'] = attempts + 1
                if hit_blank:
                    replyMsg(plugin_event, fmt('strLBShootBlank', {
                        'tTargetAt': at_user(str(hit_player.get('user_id'))),
                        'tTargetSeatId': str(hit_player.get('seat_id')),
                        'tTargetName': str(hit_player.get('nickname', '')),
                    }), False)
                else:
                    hit_player['status'] = 'dead'
                    hit_player['hand'] = []
                    replyMsg(plugin_event, fmt('strLBShootReal', {
                        'tTargetAt': at_user(str(hit_player.get('user_id'))),
                        'tTargetSeatId': str(hit_player.get('seat_id')),
                        'tTargetName': str(hit_player.get('nickname', '')),
                    }), False)

        # 检查是否只剩 1 人
        alive = LiarBar.function.alive_seats(game)
        if len(alive) < 2:
            if len(alive) == 1:
                win_sid = int(alive[0])
                p_win = LiarBar.function.find_player(game, win_sid)
                if p_win:
                    replyMsg(plugin_event, fmt('strLBGameOverWinner', {
                        'tWinSeatId': str(win_sid),
                        'tWinName': str(p_win.get('nickname', '')),
                        'tWinAt': at_user(str(p_win.get('user_id'))),
                    }), False)
                else:
                    replyMsg(plugin_event, fmt('strLBGameOverNoWinner'), False)
            else:
                # len(alive) == 0（理论上很少发生，但保底给一个提示）
                replyMsg(plugin_event, fmt('strLBGameOverNoWinner'), False)
            # 直接结束
            game = LiarBar.function.liarbar_default()
            save_group_game(gh, game)
            return

        # 开启新一轮：对仍 active 的玩家重新发 5 张，真牌重抽；起手随机
        active_players = [x for x in game.get('players', []) if x.get('status') == 'active']
        hands, real_card = LiarBar.function.deal_round(len(active_players))
        for i, p in enumerate(active_players):
            p['hand'] = hands[i]

        game['round_no'] = int(game.get('round_no', 0)) + 1
        game['real_card'] = real_card
        game['last_play'] = None
        game['last_seat_id'] = None
        game['turn_seat_id'] = random.choice([int(p.get('seat_id')) for p in active_players])

        save_group_game(gh, game)

        # 发牌提示 + 私聊
        at_all_text = ''.join([at_user(str(p.get('user_id'))) for p in active_players])
        for p in active_players:
            uid2 = str(p.get('user_id'))
            msg_lines = [
                fmt('strLBPrivateCardsHeader', {'tGroupId': str(plugin_event.data.group_id)}),
                fmt('strLBPrivateCardsLine', {'tHandText': LiarBar.function.count_hand_text(p.get('hand', []))}),
                fmt('strLBPrivateCardsFooter'),
            ]
            try:
                LiarBar.function.sendMsgByEvent(
                    plugin_event,
                    '\n'.join([x for x in msg_lines if x]),
                    str(uid2),
                    'private',
                    host_id=None
                )
            except Exception:
                pass

        p_turn = LiarBar.function.find_player(game, int(game.get('turn_seat_id')))
        start_text = fmt('strLBStartSuccess', {
            'tRealCardText': LiarBar.function.real_card_text(real_card, dictStrCustom),
            'tTurnSeatId': str(game.get('turn_seat_id')),
            'tTurnName': str(p_turn.get('nickname', '')) if p_turn else '',
            'tTurnAt': at_user(str(p_turn.get('user_id'))) if p_turn else '',
        })

        msg_parts = []
        deal_notice = fmt('strLBDealNotice', {'tAtAll': at_all_text})
        if deal_notice:
            msg_parts.append(deal_notice)
        if start_text:
            msg_parts.append(start_text)
        replyMsg(plugin_event, '\n'.join(msg_parts), False)
        return

    # （私聊）.lb play
    if isMatchWordStart(tmp_reast_str, ['play', '出牌'], isCommand=True):
        if not flag_is_from_private:
            replyMsg(plugin_event, fmt('strLBErrPlayInPrivate'), False)
            return

        gh = get_bound_group_hash()
        if not gh:
            replyMsg(plugin_event, fmt('strLBErrPlayInPrivate'), False)
            return

        game = get_group_game(gh)
        if game.get('state') != 'playing':
            replyMsg(plugin_event, fmt('strLBErrNotStarted'), False)
            return

        uid = str(plugin_event.data.user_id)
        p = LiarBar.function.find_player_by_user(game, uid)
        if not p or p.get('status') != 'active':
            replyMsg(plugin_event, fmt('strLBErrNotInGame'), False)
            return

        if int(game.get('turn_seat_id') or -1) != int(p.get('seat_id')):
            replyMsg(plugin_event, fmt('strLBErrNotYourTurn'), False)
            return

        # 解析参数
        tmp_reast_str2 = getMatchWordStartRight(tmp_reast_str, ['play', '出牌'])
        tmp_reast_str2 = skipSpaceStart(tmp_reast_str2)
        cards = LiarBar.function.parse_play_cards(tmp_reast_str2)
        if cards is None:
            replyMsg(plugin_event, fmt('strLBErrBadCards'), False)
            return

        if len(cards) == 0 or len(cards) > 3:
            replyMsg(plugin_event, fmt('strLBErrTooManyCards'), False)
            return

        is_demon = (len(cards) == 1 and cards[0] == 'Demon')
        if 'Demon' in cards and not is_demon:
            replyMsg(plugin_event, fmt('strLBErrDemonMustSingle'), False)
            return

        # 若其余所有玩家都已经出完牌：你不能出牌，只能质疑
        active_players = [x for x in game.get('players', []) if x.get('status') == 'active']
        finished = 0
        for x in active_players:
            if len(x.get('hand', [])) == 0:
                finished += 1
        if finished == len(active_players) - 1:
            replyMsg(plugin_event, fmt('strLBErrCannotPlayOnlyDoubt'), False)
            return

        # 校验持牌
        hand = list(p.get('hand', []))
        for c in cards:
            if c not in hand:
                replyMsg(plugin_event, fmt('strLBErrBadCards'), False)
                return
            hand.remove(c)
        p['hand'] = hand

        # 记录上家出牌
        game['last_play'] = {
            'seat_id': int(p.get('seat_id')),
            'cards': cards,
            'is_demon': bool(is_demon),
        }
        game['last_seat_id'] = int(p.get('seat_id'))

        # 轮到下家
        next_sid = LiarBar.function.compute_next_turn_seat(game, int(p.get('seat_id')))
        game['turn_seat_id'] = next_sid

        save_group_game(gh, game)

        # 私聊回执：剩余手牌
        replyMsg(plugin_event, fmt('strLBPrivateCardsLine', {
            'tHandText': LiarBar.function.count_hand_text(p.get('hand', []))
        }), False)

        # 群内广播
        bound_group_id, bound_host_id = get_bound_group_id_and_host_id()
        if bound_group_id:
            p_next = LiarBar.function.find_player(game, int(next_sid)) if next_sid is not None else None
            msg = fmt('strLBPlayBroadcast', {
                'tSeatId': str(p.get('seat_id')),
                'tName': str(p.get('nickname', '')),
                'tAt': at_user(str(p.get('user_id'))),
                'tCardCount': str(len(cards)),
                'tNextSeatId': str(next_sid) if next_sid is not None else '',
                'tNextName': str(p_next.get('nickname', '')) if p_next else '',
                'tNextAt': at_user(str(p_next.get('user_id'))) if p_next else '',
            })
            try:
                LiarBar.function.sendMsgByEvent(
                    plugin_event,
                    msg,
                    str(bound_group_id),
                    'group',
                    host_id=bound_host_id
                )
            except Exception:
                pass

        return

    # 未匹配命令：忽略
    return
