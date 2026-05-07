# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore，写命令请跳转到第146行。
'''

import OlivOS
import jrlp
import OlivaDiceCore

import copy
import os
import json
import random
import time

# 定义数据存储路径
DATA_PATH = "plugin/data/jrlp"

def unity_init(plugin_event, Proc):
    # 这里是插件初始化，通常用于加载配置等
    # 创建数据存储目录
    if not os.path.exists(DATA_PATH):
        os.makedirs(DATA_PATH)

def data_init(plugin_event, Proc):
    # 这里是数据初始化，通常用于加载数据等
    jrlp.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

def get_today_str():
    return time.strftime('%Y-%m-%d', time.localtime())

def get_group_data_path(group_id):
    group_path = os.path.join(DATA_PATH, str(group_id))
    if not os.path.exists(group_path):
        os.makedirs(group_path)
    return group_path

def load_today_wife_records(group_id):
    """
    获取当前群今日的所有老婆记录
    """
    group_path = get_group_data_path(group_id)
    today = get_today_str()
    res = {}
    try:
        file_name_list = os.listdir(group_path)
    except Exception:
        return res

    for file_name in file_name_list:
        if not file_name.endswith('.json'):
            continue
        data_file = os.path.join(group_path, file_name)
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        if str(data.get('date', '')) != today:
            continue
        user_id = os.path.splitext(file_name)[0]
        wife_qq = str(data.get('qq', '')).strip()
        wife_name = str(data.get('name', '')).strip()
        if user_id != '' and wife_qq != '':
            res[str(user_id)] = {
                'qq': wife_qq,
                'name': wife_name
            }
    return res

def get_today_wife(group_id, user_id):
    """
    获取今日老婆
    """
    data = load_today_wife_records(group_id).get(str(user_id))
    if isinstance(data, dict):
        return data.get('qq'), data.get('name'), False
    return None, None, True

def save_today_wife(group_id, user_id, qq, name):
    """
    保存今日老婆数据
    """
    group_path = get_group_data_path(group_id)
    data_file = os.path.join(group_path, f"{user_id}.json")

    data = {
        'date': get_today_str(),
        'qq': str(qq),
        'name': name
    }

    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def build_group_member_name_map(group_member_list_data):
    res = {}
    if not isinstance(group_member_list_data, list):
        return res
    for member in group_member_list_data:
        if not isinstance(member, dict):
            continue
        user_id = str(member.get('user_id') or member.get('id') or member.get('qq') or '').strip()
        if user_id == '':
            continue
        name = str(member.get('card') or member.get('name') or member.get('nickname') or '').strip()
        if name != '':
            res[user_id] = name
    return res

def get_user_display_name(plugin_event, user_id, group_member_name_map = None):
    user_id = str(user_id).strip()
    if user_id == '':
        return '哎呀，没能成功获取用户名！'

    if isinstance(group_member_name_map, dict):
        user_name = str(group_member_name_map.get(user_id, '')).strip()
        if user_name != '':
            return user_name

    try:
        stranger_info = plugin_event.get_stranger_info(user_id = user_id)
        if stranger_info and isinstance(stranger_info, dict) and stranger_info.get('active'):
            stranger_info_data = stranger_info.get('data', {})
            if isinstance(stranger_info_data, dict):
                user_name = str(stranger_info_data.get('card') or stranger_info_data.get('nickname') or stranger_info_data.get('name') or '').strip()
                if user_name != '':
                    return user_name
    except Exception:
        pass

    return '哎呀，没能成功获取用户名！'

def get_reverse_wife_user_id(today_wife_records, user_id):
    user_id = str(user_id)
    for source_user_id in today_wife_records:
        if str(today_wife_records[source_user_id].get('qq', '')) == user_id:
            return str(source_user_id)
    return None

def get_pure_love_candidate_list(group_member_list_data, today_wife_records, user_id):
    paired_user_id_set = set()
    for source_user_id in today_wife_records:
        paired_user_id_set.add(str(source_user_id))
        target_user_id = str(today_wife_records[source_user_id].get('qq', '')).strip()
        if target_user_id != '':
            paired_user_id_set.add(target_user_id)

    user_id = str(user_id)
    res = []
    if not isinstance(group_member_list_data, list):
        return res

    for member in group_member_list_data:
        if not isinstance(member, dict):
            continue
        member_user_id = str(member.get('user_id') or member.get('id') or member.get('qq') or '').strip()
        if member_user_id == '':
            continue
        if member_user_id == user_id:
            continue
        if member_user_id in paired_user_id_set:
            continue
        res.append(member)
    return res

def reply_today_wife_result(plugin_event, replyMsg, dictStrCustom, dictTValue, wife_qq, wife_name, is_repeat = False):
    dictTValue['qq'] = str(wife_qq)
    dictTValue['name'] = wife_name

    if is_repeat:
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['jrlpRepeat'], dictTValue)
        if tmp_reply_str != None:
            replyMsg(plugin_event, tmp_reply_str)
        return

    url = f"https://q1.qlogo.cn/g?b=qq&nk={wife_qq}&s=640"
    if str(wife_qq) == str(plugin_event.base_info['self_id']):
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['jrlpRobot'], dictTValue)
    elif str(wife_qq) == str(plugin_event.data.user_id):
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['jrlpSelf'], dictTValue)
    else:
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['jrlpFirst'], dictTValue)

    if tmp_reply_str != None:
        replyMsg(plugin_event, f"[CQ:image,file={url}]" + tmp_reply_str)

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
    if tmp_at_str_sub != None:
        if isMatchWordStart(tmp_reast_str, tmp_at_str_sub):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, tmp_at_str_sub)
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            flag_force_reply = True
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
        # 今日老婆功能实现
        if isMatchWordStart(tmp_reast_str, ['今日老婆', 'jrlp'], isCommand = True):
            # 检查是否在群聊中使用
            if not flag_is_from_group:
                replyMsg(plugin_event, '该命令只能在群聊中使用')
                return
                
            user_id = plugin_event.data.user_id
            group_id = plugin_event.data.group_id
            # 获取群成员列表
            group_member_list = plugin_event.get_group_member_list(group_id)
            if not group_member_list or group_member_list["active"] == False:
                replyMsg(plugin_event, '获取群成员列表失败')
                return
            
            # 获取用户ID
            group_member_list_data = group_member_list["data"]
            group_member_name_map = build_group_member_name_map(group_member_list_data)
            pure_love_mode = str(dictStrCustom.get('jrlpMode', '0')).strip() == '1'
            
            # 检查是否已经抽取过今日老婆
            wife_qq, wife_name, is_first_draw = get_today_wife(group_id, user_id)
            
            if not is_first_draw and wife_qq and wife_name:
                # 今日已抽取，直接返回结果
                reply_today_wife_result(plugin_event, replyMsg, dictStrCustom, dictTValue, wife_qq, wife_name, is_repeat = True)
            else:
                # 首次抽取今日老婆
                if not group_member_list_data:
                    replyMsg(plugin_event, '群成员列表为空，无法抽取')
                    return

                if pure_love_mode:
                    today_wife_records = load_today_wife_records(group_id)
                    reverse_user_id = get_reverse_wife_user_id(today_wife_records, user_id)
                    if reverse_user_id != None:
                        wife_qq = str(reverse_user_id)
                        wife_name = get_user_display_name(plugin_event, wife_qq, group_member_name_map)
                    else:
                        pure_love_candidate_list = get_pure_love_candidate_list(group_member_list_data, today_wife_records, user_id)
                        if not pure_love_candidate_list:
                            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['jrlpNoAvailable'], dictTValue)
                            if tmp_reply_str != None:
                                replyMsg(plugin_event, tmp_reply_str)
                            return
                        chosen_member = random.choice(pure_love_candidate_list)
                        wife_qq = str(chosen_member.get('user_id') or chosen_member.get('id') or chosen_member.get('qq') or '')
                        wife_name = get_user_display_name(plugin_event, wife_qq, group_member_name_map)
                else:
                    chosen_member = random.choice(group_member_list_data)
                    wife_qq = str(chosen_member.get('user_id') or chosen_member.get('id') or chosen_member.get('qq') or '')
                    wife_name = get_user_display_name(plugin_event, wife_qq, group_member_name_map)

                # 保存抽取结果
                save_today_wife(group_id, user_id, wife_qq, wife_name)

                reply_today_wife_result(plugin_event, replyMsg, dictStrCustom, dictTValue, wife_qq, wife_name)
            return
