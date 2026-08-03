# -*- encoding: utf-8 -*-
import OlivOS
import OlivaDicePuke
import OlivaDiceCore

import os
import json
import re
import traceback


# ================= 扑克牌管理模块 =================

import datetime
import os

DATA_PATH = "plugin/data/Puke"
BACKUP_PATH = os.path.join(DATA_PATH, "Backup")
SUITS = ["黑桃", "红心", "梅花", "方片"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
JOKERS = ["小王", "大王"]
ALIAS_MAP = {"草花": "梅花", "红桃": "红心"}
FULL_DECK_DISPLAY = [f"{suit}{rank}" for suit in SUITS for rank in RANKS] + JOKERS

class PukeManager:
    def __init__(self):
        self.data_path = DATA_PATH
        self.backup_path = BACKUP_PATH
        self.full_deck = FULL_DECK_DISPLAY
        self.suit_order = ["黑桃", "红心", "梅花", "方片", "王"]
        self.rank_order_map = {rank: i for i, rank in enumerate(RANKS)}
        self.joker_order_map = {joker: i for i, joker in enumerate(JOKERS)}
        self.EMOJI_MAP = {
            "黑桃": "♠️", "红心": "♥️", "红桃": "♥️", "梅花": "♣️", "草花": "♣️", "方片": "♦️",
            "大王": "🃏", "小王": "🃏", "王": "🃏"
        }

    def init_path(self):
        os.makedirs(self.data_path, exist_ok=True)
        os.makedirs(self.backup_path, exist_ok=True)

    def get_user_file_path(self, user_id):
        return os.path.join(self.data_path, f"{user_id}.json")

    def load_user_data(self, user_id):
        file_path = self.get_user_file_path(user_id)
        if not os.path.exists(file_path):
            return self.reset_deck(user_id)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保新添加的random_pool字段存在
                if 'random_pool' not in data:
                    data['random_pool'] = []
                    self.save_user_data(user_id, data)
                return data
        except (json.JSONDecodeError, IOError):
            return self.reset_deck(user_id)
    
    def save_user_data(self, user_id, data):
        file_path = self.get_user_file_path(user_id)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    
    def backup_user_data(self, user_id, data):
        # 确保用户备份目录存在
        user_backup_dir = os.path.join(self.backup_path, user_id)
        os.makedirs(user_backup_dir, exist_ok=True)
        
        # 生成备份文件名
        now = datetime.datetime.now()
        backup_filename = f"{user_id}_{now.strftime('%Y%m%d_%H%M%S')}.json"
        backup_path = os.path.join(user_backup_dir, backup_filename)
        
        # 保存备份数据
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def draw_cards(self, user_id, num_to_draw=5):
        data = self.load_user_data(user_id)
        deck = data['deck']
        
        # 清空随机池
        data['random_pool'] = []
        
        if not deck:
            return {"status": "error", "reason": "deck_empty"}
        if num_to_draw > len(deck):
            return {"status": "error", "reason": "not_enough_cards", "deck_count": len(deck)}

        drawn_cards = []
        for _ in range(num_to_draw):
            deck_size = len(deck)
            if deck_size == 0: break
            
            rd = OlivaDiceCore.onedice.RD(f'1d{deck_size}')
            rd.roll()
            index = rd.resInt - 1
            
            card = deck.pop(index)
            drawn_cards.append(card)
        
        # 将抽到的牌放入随机池
        data['random_pool'] = drawn_cards
        self.save_user_data(user_id, data)
        self.backup_user_data(user_id, data)
        
        return {
            "status": "success", 
            "drawn_cards": drawn_cards, 
            "deck_count": len(deck),
            "random_pool": drawn_cards
        }

    def draw_specific_cards(self, user_id, card_names):
        data = self.load_user_data(user_id)
        deck = data['deck']
        
        # 不再清空随机池
        
        if not deck:
            return {"status": "error", "reason": "deck_empty"}
            
        normalized_cards = []
        invalid_cards = []
        
        for card in card_names:
            original_card = card
            for alias, standard in ALIAS_MAP.items():
                if card.startswith(alias):
                    card = card.replace(alias, standard)
                    break
            
            if card in JOKERS:
                normalized_cards.append(card)
            else:
                valid = False
                for suit in SUITS:
                    if card.startswith(suit) and card[len(suit):] in RANKS:
                        valid = True
                        normalized_cards.append(card)
                        break
                if not valid:
                    invalid_cards.append(original_card)
        
        if invalid_cards:
            return {"status": "error", "reason": "invalid_cards", "invalid_cards": invalid_cards}
        
        drawn_cards = []
        not_found_cards = []
        
        for card in normalized_cards:
            if card in deck:
                deck.remove(card)
                drawn_cards.append(card)
            else:
                not_found_cards.append(card)
        
        # 将抽到的牌放入手牌
        data['hand'].extend(drawn_cards)
        self.save_user_data(user_id, data)
        self.backup_user_data(user_id, data)
        
        if not_found_cards:
            if drawn_cards:
                return {
                    "status": "partial",
                    "drawn_cards": drawn_cards,
                    "not_found_cards": not_found_cards,
                    "deck_count": len(deck)
                }
            else:
                return {
                    "status": "not_found",
                    "not_found_cards": not_found_cards,
                    "deck_count": len(deck)
                }
        
        return {
            "status": "success",
            "drawn_cards": drawn_cards,
            "deck_count": len(deck)
        }

    def reset_deck(self, user_id):
        new_data = {
            "deck": self.full_deck.copy(),
            "hand": [],
            "random_pool": []
        }
        self.save_user_data(user_id, new_data)
        return new_data

    def add_to_random_pool(self, user_id, card_names):
        data = self.load_user_data(user_id)
        deck = data['deck']
        random_pool = data['random_pool']
        
        normalized_cards = []
        invalid_cards = []
        duplicate_cards = []
        
        for card in card_names:
            original_card = card
            for alias, standard in ALIAS_MAP.items():
                if card.startswith(alias):
                    card = card.replace(alias, standard)
                    break
            
            if card in JOKERS:
                if card in random_pool:
                    duplicate_cards.append(card)
                else:
                    normalized_cards.append(card)
            else:
                valid = False
                for suit in SUITS:
                    if card.startswith(suit) and card[len(suit):] in RANKS:
                        valid = True
                        if card in random_pool:
                            duplicate_cards.append(card)
                        else:
                            normalized_cards.append(card)
                        break
                if not valid:
                    invalid_cards.append(original_card)
        
        if invalid_cards:
            return {"status": "error", "reason": "invalid_cards", "invalid_cards": invalid_cards}
        
        if duplicate_cards:
            return {"status": "error", "reason": "duplicate_cards", "duplicate_cards": duplicate_cards}
        
        added_cards = []
        for card in normalized_cards:
            if card in deck:
                deck.remove(card)
                added_cards.append(card)
        
        data['random_pool'].extend(added_cards)
        self.save_user_data(user_id, data)
        
        return {
            "status": "success",
            "added_cards": added_cards,
            "deck_count": len(deck)
        }

    def end_round(self, user_id):
        data = self.load_user_data(user_id)
        
        # 只将手牌中的牌放回牌堆，随机池直接清空
        cards_to_return = data['hand']
        data['deck'].extend(cards_to_return)
        
        # 清空手牌和随机池
        data['hand'] = []
        data['random_pool'] = []
        
        self.save_user_data(user_id, data)
        self.backup_user_data(user_id, data)
        
        return {
            "status": "success",
            "returned_cards": cards_to_return,
            "deck_count": len(data['deck'])
        }

    def clr_round(self, user_id):
        data = self.load_user_data(user_id)
        
        # 清空手牌和随机池
        data['hand'] = []
        data['random_pool'] = []
        
        self.save_user_data(user_id, data)
        self.backup_user_data(user_id, data)
        
        return {
            "status": "success",
            "deck_count": len(data['deck'])
        }

    def get_random_pool_display(self, user_id):
        data = self.load_user_data(user_id)
        random_pool = data['random_pool']
        
        if not random_pool:
            return None
        
        formatted_cards = [self._format_card_display(card) for card in random_pool]
        return formatted_cards

    def get_hand_display(self, user_id):
        data = self.load_user_data(user_id)
        hand = data['hand']
        
        if not hand:
            return "你还没有抽任何牌。"

        categorized_hand = {"黑桃": [], "红心": [], "梅花": [], "方片": [], "王": []}
        for card in hand:
            if card in self.joker_order_map:
                categorized_hand["王"].append(card)
            else:
                for suit_name in SUITS:
                    if card.startswith(suit_name):
                        categorized_hand[suit_name].append(card.replace(suit_name, ''))
                        break
        
        for suit, items in categorized_hand.items():
            if suit == "王":
                categorized_hand[suit] = [self._format_card_display(c) for c in sorted(items, key=lambda r: self.joker_order_map[r])]
            else:
                items.sort(key=lambda r: self.rank_order_map[r])
        
        return categorized_hand
    
    def get_hand_flat_display(self, user_id):
        data = self.load_user_data(user_id)
        hand = data['hand']
        
        if not hand:
            return []

        formatted_cards = [self._format_card_display(card) for card in hand]
        return formatted_cards

    def get_deck_display(self, user_id):
        data = self.load_user_data(user_id)
        deck = data['deck']

        if not deck:
            return None

        categorized_deck = {"黑桃": [], "红心": [], "梅花": [], "方片": [], "王": []}
        for card in deck:
            if card in self.joker_order_map:
                categorized_deck["王"].append(card)
            else:
                for suit_name in SUITS:
                    if card.startswith(suit_name):
                        categorized_deck[suit_name].append(card.replace(suit_name, ''))
                        break
        
        for suit, items in categorized_deck.items():
            if suit == "王":
                categorized_deck[suit] = [self._format_card_display(c) for c in sorted(items, key=lambda r: self.joker_order_map[r])]
            else:
                items.sort(key=lambda r: self.rank_order_map[r])
        
        return categorized_deck

    def change_card(self, user_id, card_in_hand, card_in_deck):
        data = self.load_user_data(user_id)
        hand = data['hand']
        deck = data['deck']

        # 牌名标准化
        def normalize(card):
            for alias, standard in ALIAS_MAP.items():
                if card.startswith(alias):
                    card = card.replace(alias, standard)
                    break
            return card

        card_in_hand = normalize(card_in_hand)
        card_in_deck = normalize(card_in_deck)

        # 检查手牌和牌库是否存在
        if card_in_hand not in hand:
            return {"status": "error", "reason": "not_in_hand", "card": card_in_hand}
        if card_in_deck not in deck:
            return {"status": "error", "reason": "not_in_deck", "card": card_in_deck}

        # 交换
        hand.remove(card_in_hand)
        deck.append(card_in_hand)
        deck.remove(card_in_deck)
        hand.append(card_in_deck)

        self.save_user_data(user_id, data)
        return {
            "status": "success",
            "hand_card": card_in_hand,
            "deck_card": card_in_deck
        }

    def remove_from_hand(self, user_id, card_names):
        data = self.load_user_data(user_id)
        hand = data['hand']
        deck = data['deck']
        
        normalized_cards = []
        invalid_cards = []
        not_in_hand = []
        returned_cards = []
        
        for card in card_names:
            original_card = card
            for alias, standard in ALIAS_MAP.items():
                if card.startswith(alias):
                    card = card.replace(alias, standard)
                    break
            if card in JOKERS:
                normalized_cards.append(card)
            else:
                valid = False
                for suit in SUITS:
                    if card.startswith(suit) and card[len(suit):] in RANKS:
                        valid = True
                        normalized_cards.append(card)
                        break
                if not valid:
                    invalid_cards.append(original_card)
        
        if invalid_cards:
            return {"status": "error", "reason": "invalid_cards", "invalid_cards": invalid_cards}
        
        for card in normalized_cards:
            if card in hand:
                hand.remove(card)
                deck.append(card)
                returned_cards.append(card)
            else:
                not_in_hand.append(card)
        
        self.save_user_data(user_id, data)
        
        if not_in_hand:
            if returned_cards:
                return {
                    "status": "partial",
                    "returned_cards": returned_cards,
                    "not_in_hand": not_in_hand,
                    "deck_count": len(deck)
                }
            else:
                return {
                    "status": "not_found",
                    "not_in_hand": not_in_hand,
                    "deck_count": len(deck)
                }
        return {
            "status": "success",
            "returned_cards": returned_cards,
            "deck_count": len(deck)
        }

    def _format_card_display(self, card_text):
        if card_text in self.joker_order_map:
            return f"{self.EMOJI_MAP.get(card_text, '')}{card_text}"
        for suit, emoji in self.EMOJI_MAP.items():
            if card_text.startswith(suit):
                return card_text.replace(suit, emoji)
        return card_text

# 实例化管理器
puke_manager = PukeManager()

def unity_init(plugin_event, Proc):
    pass

def data_init(plugin_event, Proc):
    OlivaDicePuke.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])
    puke_manager.init_path()

def unity_reply(plugin_event, Proc):
    OlivaDiceCore.userConfig.setMsgCount()
    dictTValue = OlivaDiceCore.msgCustom.dictTValue.copy()
    dictTValue['tUserName'] = plugin_event.data.sender['name']
    dictTValue['tName'] = plugin_event.data.sender['name']
    dictStrCustom = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]
    dictGValue = OlivaDiceCore.msgCustom.dictGValue
    dictTValue.update(dictGValue)
    dictTValue = OlivaDiceCore.msgCustomManager.dictTValueInit(plugin_event, dictTValue)

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
    tmp_id_str_sub_open = None
    if 'sub_self_id' in plugin_event.data.extend:
        if plugin_event.data.extend['sub_self_id'] != None:
            tmp_at_str_sub = OlivOS.messageAPI.PARA.at(plugin_event.data.extend['sub_self_id']).CQ()
            tmp_id_str_sub = str(plugin_event.data.extend['sub_self_id'])
    if 'sub_self_open_id' in plugin_event.data.extend:
        if plugin_event.data.extend['sub_self_open_id'] != None:
            tmp_id_str_sub_open = str(plugin_event.data.extend['sub_self_open_id'])
    tmp_command_str_1 = '.'
    tmp_command_str_2 = '。'
    tmp_command_str_3 = '/'
    tmp_reast_str = plugin_event.data.message
    tmp_reast_str = OlivaDiceCore.msgReply.to_half_width(tmp_reast_str)
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
        if tmp_id_str_sub_open in tmp_at_list:
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
        tmp_hagID = None
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
            
        # .puke 指令
        user_id = plugin_event.data.user_id
        tmp_pc_platform = plugin_event.platform['platform']
        tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(
            user_id,
            tmp_pc_platform
        )
        tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(
            tmp_pcHash,
            tmp_hagID
        )
        if tmp_pc_name:
            dictTValue['tName'] = tmp_pc_name
        # .puke指令部分
        if isMatchWordStart(tmp_reast_str, 'puke', isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'puke')
            tmp_reast_str = skipSpaceStart(tmp_reast_str)

            # hand 指令 - 查看手牌
            if isMatchWordStart(tmp_reast_str, 'hand', isCommand=True):
                data = puke_manager.load_user_data(tmp_pcHash)
                hand = data['hand']
                if not hand:
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeShowEmpty'], dictTValue))
                    return

                # 格式化手牌
                formatted_cards = [puke_manager._format_card_display(card) for card in hand]
                dictTValue['tHandCards'] = '、'.join(formatted_cards)
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeShowSuit'], dictTValue))
                return

            # ck 指令 - 查看手牌和随机池
            elif isMatchWordStart(tmp_reast_str, ['ck','check','showdown','showhand'], isCommand=True):
                hand_cards = puke_manager.get_hand_flat_display(tmp_pcHash)
                random_pool = puke_manager.get_random_pool_display(tmp_pcHash)

                hand_display = '、'.join(hand_cards) if hand_cards else '无'
                random_pool_display = '、'.join(random_pool) if random_pool else '无'
                
                dictTValue['tHandCards'] = hand_display
                dictTValue['tRandomPool'] = random_pool_display
                
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeCheck'], dictTValue))
                return

            # deck 指令 - 查看当前牌堆
            elif isMatchWordStart(tmp_reast_str, ['deck','table'], isCommand=True):
                categorized_deck = puke_manager.get_deck_display(tmp_pcHash)
                deck_count = len(puke_manager.load_user_data(tmp_pcHash)['deck'])

                if not categorized_deck:
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDeckEmpty'], dictTValue))
                    return

                dictTValue['tDeckCount'] = str(deck_count)
                header = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDeckHeader'], dictTValue)
                display_parts = [header]
                empty_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeShowEmpty'], dictTValue)

                for suit in puke_manager.suit_order:
                    cards = categorized_deck[suit]
                    card_str = ' '.join(cards) if cards else empty_str
                    emoji = puke_manager.EMOJI_MAP.get(suit, '')
                    dictTValue['tSuit'] = f"{emoji}{suit}"
                    dictTValue['tCards'] = card_str
                    display_parts.append(OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDeckSuit'], dictTValue))

                replyMsg(plugin_event, "".join(display_parts))
                return

            # pool 指令 - 查看随机池
            elif isMatchWordStart(tmp_reast_str, ['pool','show','random'], isCommand=True):
                random_pool = puke_manager.get_random_pool_display(tmp_pcHash)

                if random_pool is None:
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeRandomPoolEmpty'], dictTValue))
                    return

                header = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeRandomPoolHeader'], dictTValue)
                replyMsg(plugin_event, f"{header}\n{'、'.join(random_pool)}")
                return

            # add 指令 - 添加牌到手牌
            elif isMatchWordStart(tmp_reast_str, 'add', isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'add')
                tmp_reast_str = skipSpaceStart(tmp_reast_str)

                if not tmp_reast_str:
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeAddCardNeedSpecify'], dictTValue))
                    return

                card_names = re.split(r'[,，\s]+', tmp_reast_str.strip())
                card_names = [name for name in card_names if name]

                result = puke_manager.draw_specific_cards(tmp_pcHash, card_names)

                if result['status'] == 'error':
                    if result['reason'] == 'invalid_cards':
                        dictTValue['tInvalidCard'] = '、'.join(result['invalid_cards'])
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeInvalidCard'], dictTValue))
                    return

                if result['status'] == 'not_found':
                    formatted_cards_to_add = '、'.join([puke_manager._format_card_display(card) for card in result['not_found_cards']])
                    dictTValue['tCardsToAdd'] = formatted_cards_to_add
                    dictTValue['tDeckCount'] = str(result['deck_count'])
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeAddCardNotFound'], dictTValue))
                    return

                added_cards_with_emoji = [puke_manager._format_card_display(card) for card in result.get('drawn_cards', [])]
                
                if result['status'] == 'partial':
                    not_found_cards_with_emoji = [puke_manager._format_card_display(card) for card in result.get('not_found_cards', [])]
                    dictTValue['tAddedCards'] = '、'.join(added_cards_with_emoji)
                    dictTValue['tNotFoundCards'] = '、'.join(not_found_cards_with_emoji)
                    dictTValue['tDeckCount'] = str(result['deck_count'])
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeAddCardPartial'], dictTValue))
                    return
                
                dictTValue['tAddedCards'] = '、'.join(added_cards_with_emoji)
                dictTValue['tDeckCount'] = str(result['deck_count'])
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeAddCard'], dictTValue))
                return

            # end 指令 - 结束本轮抽牌
            elif isMatchWordStart(tmp_reast_str, 'end', isCommand=True):
                result = puke_manager.end_round(tmp_pcHash)
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeEnd'], dictTValue))
                return
                
            # clr 指令 - 清空随机池和手牌池
            elif isMatchWordStart(tmp_reast_str, ['clr','clear'], isCommand=True):
                result = puke_manager.clr_round(tmp_pcHash)
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeClr'], dictTValue))
                return

            # reset 指令
            elif isMatchWordStart(tmp_reast_str, 'reset', isCommand=True):
                puke_manager.reset_deck(tmp_pcHash)
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeReset'], dictTValue))
                return

            elif isMatchWordStart(tmp_reast_str, 'change', isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'change')
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                tmp_reast_str = tmp_reast_str.upper()
                card_names = re.split(r'[,，\s]+', tmp_reast_str.strip())
                card_names = [name for name in card_names if name]
                if len(card_names) != 2:
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeChangeNeedSpecify'], dictTValue))
                    return
                cardA, cardB = card_names
                result = puke_manager.change_card(tmp_pcHash, cardA, cardB)
                dictTValue['tHandCard'] = puke_manager._format_card_display(cardA)
                dictTValue['tDeckCard'] = puke_manager._format_card_display(cardB)
                if result['status'] == 'success':
                    replyMsg(plugin_event, dictStrCustom['strPukeChangeSuccess'].format(**dictTValue))
                elif result['reason'] == 'not_in_hand':
                    replyMsg(plugin_event, dictStrCustom['strPukeChangeNotInHand'].format(**dictTValue))
                elif result['reason'] == 'not_in_deck':
                    replyMsg(plugin_event, dictStrCustom['strPukeChangeNotInDeck'].format(**dictTValue))
                return

            # rm/del/delete/remove 指令 - 从手牌移除指定牌放回牌堆
            elif isMatchWordStart(tmp_reast_str, ['rm','del','delete','remove','back'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['rm','del','delete','remove','back'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                if not tmp_reast_str:
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeRemoveCardNeedSpecify'], dictTValue))
                    return
                card_names = re.split(r'[,，\s]+', tmp_reast_str.strip())
                card_names = [name for name in card_names if name]
                result = puke_manager.remove_from_hand(tmp_pcHash, card_names)
                if result['status'] == 'error':
                    if result['reason'] == 'invalid_cards':
                        dictTValue['tInvalidCard'] = '、'.join(result['invalid_cards'])
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeInvalidCard'], dictTValue))
                    return
                if result['status'] == 'not_found':
                    dictTValue['tCardsToRemove'] = '、'.join([puke_manager._format_card_display(card) for card in result['not_in_hand']])
                    dictTValue['tDeckCount'] = str(result['deck_count'])
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeRemoveCardNotInHand'], dictTValue))
                    return
                if result['status'] == 'partial':
                    dictTValue['tRemovedCards'] = '、'.join([puke_manager._format_card_display(card) for card in result['returned_cards']])
                    dictTValue['tNotInHand'] = '、'.join([puke_manager._format_card_display(card) for card in result['not_in_hand']])
                    dictTValue['tDeckCount'] = str(result['deck_count'])
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeRemoveCardPartial'], dictTValue))
                    return
                dictTValue['tRemovedCards'] = '、'.join([puke_manager._format_card_display(card) for card in result['returned_cards']])
                dictTValue['tDeckCount'] = str(result['deck_count'])
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeRemoveCard'], dictTValue))
                return

            # 抽牌指令
            else:
                tmp_reast_str = tmp_reast_str.upper()
                # 尝试解析为数字
                if tmp_reast_str and tmp_reast_str.isdigit():
                    num_to_draw = int(tmp_reast_str)
                    if not (1 <= num_to_draw <= 54):
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeInvalidNumber'], dictTValue))
                        return

                    result = puke_manager.draw_cards(tmp_pcHash, num_to_draw)

                    if result['status'] == 'error':
                        if result['reason'] == 'not_enough_cards':
                            dictTValue['tDrawCount'] = str(num_to_draw)
                            dictTValue['tDeckCount'] = str(result['deck_count'])
                            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDrawError'], dictTValue))
                        elif result['reason'] == 'deck_empty':
                            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDeckEmpty'], dictTValue))
                        return

                    drawn_cards_with_emoji = [puke_manager._format_card_display(card) for card in result['drawn_cards']]
                    random_pool_with_emoji = [puke_manager._format_card_display(card) for card in result['random_pool']]

                    dictTValue['tDrawCount'] = str(num_to_draw)
                    dictTValue['tDrawnCards'] = '、'.join(drawn_cards_with_emoji)
                    dictTValue['tRandomPool'] = '、'.join(random_pool_with_emoji)
                    dictTValue['tDeckCount'] = str(result['deck_count'])
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDraw'], dictTValue))
                    return

                # 如果不是数字，尝试解析为指定牌名
                elif tmp_reast_str:
                    card_names = re.split(r'[,，\s]+', tmp_reast_str.strip())
                    card_names = [name for name in card_names if name]

                    if not card_names:
                        # 如果没有指定牌名，默认抽5张
                        num_to_draw = 5
                        result = puke_manager.draw_cards(tmp_pcHash, num_to_draw)

                        if result['status'] == 'error':
                            if result['reason'] == 'not_enough_cards':
                                dictTValue['tDrawCount'] = str(num_to_draw)
                                dictTValue['tDeckCount'] = str(result['deck_count'])
                                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDrawError'], dictTValue))
                            elif result['reason'] == 'deck_empty':
                                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDeckEmpty'], dictTValue))
                            return

                        drawn_cards_with_emoji = [puke_manager._format_card_display(card) for card in result['drawn_cards']]
                        random_pool_with_emoji = [puke_manager._format_card_display(card) for card in result['random_pool']]

                        dictTValue['tDrawCount'] = str(num_to_draw)
                        dictTValue['tDrawnCards'] = '、'.join(drawn_cards_with_emoji)
                        dictTValue['tRandomPool'] = '、'.join(random_pool_with_emoji)
                        dictTValue['tDeckCount'] = str(result['deck_count'])
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDraw'], dictTValue))
                        return

                    # 尝试抽取指定牌
                    result = puke_manager.draw_specific_cards(tmp_pcHash, card_names)

                    if result['status'] == 'error':
                        if result['reason'] == 'invalid_cards':
                            dictTValue['tInvalidCard'] = '、'.join(result['invalid_cards'])
                            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeInvalidCard'], dictTValue))
                        elif result['reason'] == 'deck_empty':
                            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDeckEmpty'], dictTValue))
                        return

                    formatted_cards_to_draw = '、'.join([puke_manager._format_card_display(card) for card in card_names])

                    if result['status'] == 'not_found':
                        dictTValue['tCardsToDraw'] = formatted_cards_to_draw
                        dictTValue['tDeckCount'] = str(result['deck_count'])
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDrawSpecificNotFound'], dictTValue))
                        return

                    drawn_cards_with_emoji = [puke_manager._format_card_display(card) for card in result.get('drawn_cards', [])]
                    not_found_cards_with_emoji = [puke_manager._format_card_display(card) for card in result.get('not_found_cards', [])]

                    if result['status'] == 'partial':
                        dictTValue['tCardsToDraw'] = formatted_cards_to_draw
                        dictTValue['tDrawnCards'] = '、'.join(drawn_cards_with_emoji)
                        dictTValue['tNotFoundCards'] = '、'.join(not_found_cards_with_emoji)
                        dictTValue['tDeckCount'] = str(result['deck_count'])
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDrawSpecificPartial'], dictTValue))
                        return

                    if result['status'] == 'success':
                        dictTValue['tCardsToDraw'] = formatted_cards_to_draw
                        dictTValue['tDrawnCards'] = '、'.join(drawn_cards_with_emoji)
                        dictTValue['tDeckCount'] = str(result['deck_count'])
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDrawSpecific'], dictTValue))
                        return

                # 默认情况：抽5张牌
                deck_count = len(puke_manager.load_user_data(tmp_pcHash)['deck'])
                num_to_draw = min(5, deck_count)
                result = puke_manager.draw_cards(tmp_pcHash, num_to_draw)

                if result['status'] == 'error':
                    if result['reason'] == 'not_enough_cards':
                        dictTValue['tDrawCount'] = str(num_to_draw)
                        dictTValue['tDeckCount'] = str(result['deck_count'])
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDrawError'], dictTValue))
                    elif result['reason'] == 'deck_empty':
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDeckEmpty'], dictTValue))
                    return

                drawn_cards_with_emoji = [puke_manager._format_card_display(card) for card in result['drawn_cards']]
                random_pool_with_emoji = [puke_manager._format_card_display(card) for card in result['random_pool']]

                dictTValue['tDrawCount'] = str(num_to_draw)
                dictTValue['tDrawnCards'] = '、'.join(drawn_cards_with_emoji)
                dictTValue['tRandomPool'] = '、'.join(random_pool_with_emoji)
                dictTValue['tDeckCount'] = str(result['deck_count'])
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPukeDraw'], dictTValue))
                return
