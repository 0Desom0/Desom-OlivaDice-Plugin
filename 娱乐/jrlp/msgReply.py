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

def _is_qqguild_event(plugin_event):
    """判断当前事件是否属于 qqGuild 平台（含 qqGuildv2_link 与 qqGuild_link）。"""
    try:
        platform = plugin_event.platform
        if not isinstance(platform, dict):
            return False
        sdk = str(platform.get('sdk', '')).strip().lower()
        plat = str(platform.get('platform', '')).strip().lower()
    except Exception:
        return False
    return plat == 'qqguild' or sdk in ('qqguildv2_link', 'qqguild_link')


def _get_bot_self_ids(plugin_event):
    """收集当前机器人在本事件中的所有自身 ID（AppID / self_id / sub_self_id / sub_self_open_id）。"""
    ids = set()
    base_info = getattr(plugin_event, 'base_info', None)
    if isinstance(base_info, dict):
        val = base_info.get('self_id')
        if val is not None and str(val).strip() != '':
            ids.add(str(val).strip())
    bot_info = getattr(plugin_event, 'bot_info', None)
    if bot_info is not None:
        val = getattr(bot_info, 'id', None)
        if val is not None and str(val).strip() != '':
            ids.add(str(val).strip())
    data = getattr(plugin_event, 'data', None)
    extend = getattr(data, 'extend', None) if data is not None else None
    if isinstance(extend, dict):
        for key in ('sub_self_id', 'sub_self_open_id'):
            val = extend.get(key)
            if val is not None and str(val).strip() != '':
                ids.add(str(val).strip())
    return ids


def _get_qqguild_self_avatar_info(plugin_event):
    """读取 qqGuildv2 机器人自身的真实 OpenID 与（可选）getMe 头像地址。"""
    self_open_id = ''
    self_avatar_url = ''
    data = getattr(plugin_event, 'data', None)
    extend = getattr(data, 'extend', None) if data is not None else None
    if isinstance(extend, dict):
        val = extend.get('sub_self_open_id')
        if val is not None and str(val).strip() != '':
            self_open_id = str(val).strip()

    bot_info = getattr(plugin_event, 'bot_info', None)
    bot_hash = str(getattr(bot_info, 'hash', '') or '').strip()
    if bot_hash != '':
        if self_open_id == '':
            proc = getattr(plugin_event, 'Proc', None)
            proc_data = getattr(proc, 'Proc_data', None) if proc is not None else None
            if isinstance(proc_data, dict):
                openid_map = proc_data.get('qqGuildv2_self_openid')
                if isinstance(openid_map, dict):
                    val = openid_map.get(bot_hash)
                    if val is not None and str(val).strip() != '':
                        self_open_id = str(val).strip()

        qq_sdk = getattr(OlivOS, 'qqGuildv2SDK', None)
        qq_common = getattr(qq_sdk, 'qqGuildv2SDKCommon', None) if qq_sdk is not None else None
        if self_open_id == '':
            for container in (qq_sdk, qq_common):
                openid_map = getattr(container, 'sdkSubSelfOpenInfo', None)
                if isinstance(openid_map, dict):
                    val = openid_map.get(bot_hash)
                    if val is not None and str(val).strip() != '':
                        self_open_id = str(val).strip()
                        break
        for container in (qq_sdk, qq_common):
            self_map = getattr(container, 'sdkSelfInfo', None)
            if isinstance(self_map, dict):
                info = self_map.get(bot_hash)
                if isinstance(info, dict):
                    avatar = str(info.get('avatar') or '').strip()
                    if avatar.startswith(('http://', 'https://')):
                        self_avatar_url = avatar
                        break

    return self_open_id, self_avatar_url


def build_avatar_url(plugin_event, user_id):
    """按平台生成头像地址：官方机器人用 AppID+OpenID，其余沿用 QQ 号接口。"""
    target_id = str(user_id).strip()
    try:
        sdk = str(plugin_event.platform.get('sdk', '')).strip().lower()
    except Exception:
        sdk = ''
    if sdk == 'qqguildv2_link':
        raw_appid = getattr(getattr(plugin_event, 'bot_info', None), 'id', None)
        appid = str(raw_appid).strip() if raw_appid is not None else ''
        non_openid_self_ids = set()
        if appid != '':
            non_openid_self_ids.add(appid)
        base_info = getattr(plugin_event, 'base_info', None)
        if isinstance(base_info, dict):
            val = base_info.get('self_id')
            if val is not None and str(val).strip() != '':
                non_openid_self_ids.add(str(val).strip())
        data = getattr(plugin_event, 'data', None)
        extend = getattr(data, 'extend', None) if data is not None else None
        if isinstance(extend, dict):
            val = extend.get('sub_self_id')
            if val is not None and str(val).strip() != '':
                non_openid_self_ids.add(str(val).strip())

        # 抽到机器人自身时，成员列表里的 user_id 可能是 AppID 或 sub_self_id 而非 OpenID；
        # 直接拼 qqapp/{appid}/{appid}/0 会返回默认企鹅图，需改用机器人自身的 OpenID。
        if target_id != '' and target_id in non_openid_self_ids:
            self_open_id, self_avatar_url = _get_qqguild_self_avatar_info(plugin_event)
            if appid.isdecimal() and self_open_id != '' and self_open_id not in non_openid_self_ids:
                return f'https://q.qlogo.cn/qqapp/{appid}/{self_open_id}/0'
            if self_avatar_url != '':
                return self_avatar_url

        # 官方机器人下 user_id 即 openid，AppID 为纯数字；任一缺失则回退旧接口
        if appid.isdecimal() and target_id != '':
            return f'https://q.qlogo.cn/qqapp/{appid}/{target_id}/0'
    return f'https://q1.qlogo.cn/g?b=qq&nk={target_id}&s=640'


def reply_today_wife_result(plugin_event, replyMsg, dictStrCustom, dictTValue, wife_qq, wife_name, is_repeat = False):
    dictTValue['qq'] = str(wife_qq)
    dictTValue['name'] = wife_name

    if is_repeat:
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['jrlpRepeat'], dictTValue)
        if tmp_reply_str != None:
            replyMsg(plugin_event, tmp_reply_str)
        return

    url = build_avatar_url(plugin_event, wife_qq)
    wife_id_str = str(wife_qq).strip()
    if wife_id_str in _get_bot_self_ids(plugin_event):
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['jrlpRobot'], dictTValue)
    elif wife_id_str == str(plugin_event.data.user_id).strip():
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['jrlpSelf'], dictTValue)
    else:
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['jrlpFirst'], dictTValue)

    if tmp_reply_str != None:
        sep = '\n' if _is_qqguild_event(plugin_event) else ''
        replyMsg(plugin_event, f"[CQ:image,file={url}]{sep}" + tmp_reply_str)

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
