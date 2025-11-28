# -*- encoding: utf-8 -*-
'''
@File      :   msgReply.py
@Author    :   Desom-fu
@Contact   :   desom233@outlook.com
@License   :   AGPL
@Copyright :   (C) 2020-2025, OlivOS-Team
@Desc      :   None
'''

import OlivOS
import OlivaDiceShouHun
import OlivaDiceCore

import hashlib
import time
import traceback
import re
from functools import wraps
import copy

def parse_sh_parameters(expr_str, isMatchWordStart, getMatchWordStartRight, skipSpaceStart, parse_m_h=True):
    """
    解析 sh 命令中的参数 b/p、m、x、h、s、kh/kl、a
    可以无视参数位置顺序
    参数:
        expr_str: 要解析的表达式字符串
        parse_m_h: 是否解析 m 和 h 参数（默认 True）。后式调用时设为 False
    返回: cleaned_expr, b_count, p_count, m_flag, x_value, x_flag, h_flag, x_modifier, s_count, s_fixed_values, kh_kl_type, kh_kl_num, a_flag
    """
    b_count = 0  # b参数（奖励等级）
    p_count = 0  # p参数（惩罚等级）
    m_flag = False  # m参数（去除默认d20）
    x_value = None  # x参数指定的D20点数
    x_flag = False  # 是否有x参数
    x_modifier = None  # x参数的修饰符（'u'向上修正，'d'向下修正）
    h_flag = False  # h参数（暗骰）
    s_count = 1  # s参数（d20数量，默认为1）
    s_fixed_values = []  # s参数中的固定值列表
    kh_kl_type = None  # kh/kl类型：None/'kh'/'kl'
    kh_kl_num = None  # kh/kl的数字，如kh2中的2
    a_flag = False  # a参数（1和2都视为大失败）
    tmp_reast_str = expr_str
    
    # 循环处理所有参数
    while tmp_reast_str:
        original_str = tmp_reast_str
        
        # 处理h参数（暗骰）- 仅在 parse_m_h=True 时解析
        if parse_m_h and isMatchWordStart(tmp_reast_str, 'h'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'h')
            h_flag = True
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理a参数（1和2都视为大失败）
        elif isMatchWordStart(tmp_reast_str, 'a'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'a')
            a_flag = True
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理b参数（奖励等级）
        elif isMatchWordStart(tmp_reast_str, 'b'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'b')
            # 检查是否有数字指定，只取一位
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                b_count += int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                b_count += 1  # 默认为1
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理p参数（惩罚等级）
        elif isMatchWordStart(tmp_reast_str, 'p'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'p')
            # 检查是否有数字指定，只取一位
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                p_count += int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                p_count += 1  # 默认为1
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理m参数（去除默认d20）- 仅在 parse_m_h=True 时解析
        elif parse_m_h and isMatchWordStart(tmp_reast_str, 'm'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'm')
            m_flag = True
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理s参数（d20数量，支持固定值和kh/kl）
        elif isMatchWordStart(tmp_reast_str, 's'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 's')
            # s参数后必须跟数字
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                # 提取连续的数字
                num_str = ''
                i = 0
                while i < len(tmp_reast_str) and tmp_reast_str[i].isdigit():
                    num_str += tmp_reast_str[i]
                    i += 1
                s_count = int(num_str)
                s_count = max(1, s_count)  # 最小为1
                tmp_reast_str = tmp_reast_str[len(num_str):]
                
                # 检查是否有kh或kl
                if len(tmp_reast_str) >= 2 and tmp_reast_str[0:2].lower() in ['kh', 'kl']:
                    kh_kl_type = tmp_reast_str[0:2].lower()
                    tmp_reast_str = tmp_reast_str[2:]
                    
                    # 检查kh/kl后是否有数字
                    if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                        kh_kl_num_str = ''
                        j = 0
                        while j < len(tmp_reast_str) and tmp_reast_str[j].isdigit():
                            kh_kl_num_str += tmp_reast_str[j]
                            j += 1
                        kh_kl_num = int(kh_kl_num_str)
                        tmp_reast_str = tmp_reast_str[len(kh_kl_num_str):]
                
                # 检查是否有固定值括号
                elif len(tmp_reast_str) > 0 and tmp_reast_str[0] == '(':
                    # 找到匹配的右括号
                    paren_count = 1
                    j = 1
                    while j < len(tmp_reast_str) and paren_count > 0:
                        if tmp_reast_str[j] == '(':
                            paren_count += 1
                        elif tmp_reast_str[j] == ')':
                            paren_count -= 1
                        j += 1
                    
                    if paren_count == 0:
                        # 提取括号内容
                        paren_content = tmp_reast_str[1:j-1]
                        # 解析固定值（支持逗号、分号、空格分隔）
                        fixed_values = []
                        # 先按逗号分割，再按分号分割，最后按空格分割
                        for separator in [',', ';', ' ']:
                            if separator in paren_content:
                                for val_str in paren_content.split(separator):
                                    val_str = val_str.strip()
                                    if val_str.isdigit():
                                        fixed_values.append(int(val_str))
                                break
                        else:
                            # 如果没有分隔符，尝试直接解析单个数字
                            paren_content = paren_content.strip()
                            if paren_content.isdigit():
                                fixed_values.append(int(paren_content))
                        s_fixed_values = fixed_values
                        tmp_reast_str = tmp_reast_str[j:]
            
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理x参数（指定D20点数，支持u/d修饰符）
        elif isMatchWordStart(tmp_reast_str, 'x'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'x')
            # x参数后必须跟数字
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                # 提取连续的数字
                num_str = ''
                i = 0
                while i < len(tmp_reast_str) and tmp_reast_str[i].isdigit():
                    num_str += tmp_reast_str[i]
                    i += 1
                x_value = int(num_str)
                x_value = max(0, x_value)  # 最小为0
                x_flag = True
                tmp_reast_str = tmp_reast_str[len(num_str):]
                
                # 检查u/d修饰符
                if len(tmp_reast_str) > 0:
                    if tmp_reast_str[0].lower() == 'u':
                        x_modifier = 'u'
                        tmp_reast_str = tmp_reast_str[1:]
                    elif tmp_reast_str[0].lower() == 'd':
                        x_modifier = 'd'
                        tmp_reast_str = tmp_reast_str[1:]
            
            # 如果有u/d修饰符，移除可能的+号（因为不需要额外表达式）
            if x_modifier and len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            # 如果没有u/d修饰符，也兼容移除+号
            elif len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 如果没有匹配到任何参数，跳出循环
        if tmp_reast_str == original_str:
            break
    
    # 跳过空格并返回清理后的表达式
    cleaned_expr = skipSpaceStart(tmp_reast_str)
    
    return cleaned_expr, b_count, p_count, m_flag, x_value, x_flag, h_flag, x_modifier, s_count, s_fixed_values, kh_kl_type, kh_kl_num, a_flag

def unity_init(plugin_event, Proc):
    pass

def data_init(plugin_event, Proc):
    OlivaDiceShouHun.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

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
        if isMatchWordStart(tmp_reast_str, 'sh', isCommand = True):
            is_at, at_user_id, tmp_reast_str = OlivaDiceCore.msgReply.parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin)
            if is_at and not at_user_id:
                return
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'sh')
        else:
            return
        # 默认tName是人物卡名
        if True:
            tmp_pc_id = at_user_id if at_user_id else plugin_event.data.user_id
            tmp_pc_platform = plugin_event.platform['platform']
            tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(
                tmp_pc_id,
                tmp_pc_platform
            )
            tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(
                tmp_pcHash,
                tmp_hagID
            )
            tmp_pcCardRule = 'default'
            tmp_pcCardRule_new = OlivaDiceCore.pcCard.pcCardDataGetTemplateKey(tmp_pcHash, tmp_pc_name)
            if tmp_pcCardRule_new != None:
                tmp_pcCardRule = tmp_pcCardRule_new
            if tmp_pc_name != None:
                dictTValue['tName'] = tmp_pc_name
            else:
                res = plugin_event.get_stranger_info(user_id = tmp_pc_id)
                if res != None:
                    dictTValue['tName'] = res['data']['name']
                else:
                    dictTValue['tName'] = f'用户{tmp_pc_id}'
            pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(tmp_pcHash, hagId=tmp_hagID) if tmp_pc_name else {}
            skill_valueTable = pc_skills.copy()
            if tmp_pc_name != None:
                skill_valueTable.update(
                    OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                        pcHash = tmp_pcHash,
                        pcCardName = tmp_pc_name,
                        dataKey = 'mappingRecord',
                        resDefault = {}
                    )
                )
            
            # 分割前后表达式（用#分隔），h参数会在解析函数中处理
            parts = tmp_reast_str.split('#')
            front_part = parts[0].strip() if len(parts) > 0 else ''
            back_part = parts[1].strip() if len(parts) > 1 else '10'
            
            # 使用新的参数解析函数处理前式（包括h参数和kh/kl参数）
            front_part, flag_bp_count, flag_p_count, flag_no_default_d20, x_dice_value, is_x, flag_hide, x_modifier, s_count, s_fixed_values, kh_kl_type, kh_kl_num, a_flag = parse_sh_parameters(
                front_part, isMatchWordStart, getMatchWordStartRight, skipSpaceStart
            )
            
            # 确定奖励/惩罚类型
            flag_bp_type = 0  # 0无 1奖励 2惩罚
            if flag_bp_count > 0 and flag_p_count > 0:
                # 两者都有，取净值
                if flag_bp_count > flag_p_count:
                    flag_bp_type = 1
                    flag_bp_count = flag_bp_count - flag_p_count
                elif flag_p_count > flag_bp_count:
                    flag_bp_type = 2
                    flag_bp_count = flag_p_count - flag_bp_count
                else:
                    flag_bp_type = 0
                    flag_bp_count = 0
            elif flag_bp_count > 0:
                flag_bp_type = 1
            elif flag_p_count > 0:
                flag_bp_type = 2
                flag_bp_count = flag_p_count
            
            # 使用新的参数解析函数处理后式（后式不解析 m 和 h 参数，也不解析kh/kl）
            back_part, back_flag_bp_count, back_flag_p_count, _, back_x_dice_value, is_back_x, _, back_x_modifier, _, _, _, _, back_a_flag = parse_sh_parameters(
                back_part, isMatchWordStart, getMatchWordStartRight, skipSpaceStart, parse_m_h=False
            )
            
            # 确定后式的奖励/惩罚类型
            back_flag_bp_type = 0
            if back_flag_bp_count > 0 and back_flag_p_count > 0:
                if back_flag_bp_count > back_flag_p_count:
                    back_flag_bp_type = 1
                    back_flag_bp_count = back_flag_bp_count - back_flag_p_count
                elif back_flag_p_count > back_flag_bp_count:
                    back_flag_bp_type = 2
                    back_flag_bp_count = back_flag_p_count - back_flag_bp_count
                else:
                    back_flag_bp_type = 0
                    back_flag_bp_count = 0
            elif back_flag_bp_count > 0:
                back_flag_bp_type = 1
            elif back_flag_p_count > 0:
                back_flag_bp_type = 2
                back_flag_bp_count = back_flag_p_count
            
            # 处理前式表达式
            front_expr = front_part
            front_expr_str = front_part
            back_expr_str = back_part if back_part else '10'
            
            # 处理~参数（将计算结果加到人物卡shm）
            shm_add_value = None
            shm_add_expr = None
            shm_add_expr_str = None
            if front_expr and '~' in front_expr:
                front_parts = front_expr.split('~', 1)
                front_expr = front_parts[0].strip() if front_parts[0].strip() else None
                front_expr_str = front_expr
                shm_add_expr_str = front_parts[1].strip() if len(front_parts) > 1 and front_parts[1].strip() else None
                if shm_add_expr_str:
                    # 技能替换
                    shm_add_expr, _ = replace_skills(shm_add_expr_str.replace('=', '').replace(' ', ''), skill_valueTable, tmp_pcCardRule)
            
            # 确定 dice_20 的值（考虑kh/kl参数）
            force_dice_expr = None
            if kh_kl_type:
                # 有kh/kl参数，构造完整的骰子表达式
                if kh_kl_num is not None:
                    force_dice_expr = f"{s_count}d20{kh_kl_type}{kh_kl_num}"
                else:
                    force_dice_expr = f"{s_count}d20{kh_kl_type}"
            
            # 确定 dice_20 的值
            dice_20 = '1D20'  # 默认值
            has_kh_kl = False  # 标记是否有kh/kl修饰符
            
            # s参数优先级高于x但低于m
            if not flag_no_default_d20:  # m参数优先级最高
                if s_count > 1:
                    # s参数指定多个d20
                    dice_20 = f"{s_count}D20"
                elif is_x and x_dice_value is not None:
                    # x参数指定固定值
                    if x_modifier:  # 有u/d修饰符，使用1D20
                        dice_20 = '1D20'
                    else:  # 无修饰符，使用固定值
                        dice_20 = str(x_dice_value)
            else:
                # m参数去除默认d20
                dice_20 = '0'
            
            if not back_expr_str:
                back_expr_str = '10'
            
            # 出值解析
            if front_expr:
                # 处理表达式中的 Xd20kh/kl（只有在没有s参数且没有x参数且没有force_dice_expr时才处理）
                if s_count == 1 and not is_x and not force_dice_expr:
                    # 0. 优先匹配 Xd20kh/kl 格式
                    match_xd20_kh_kl = re.match(r'^(\d*)[dD]20(kh|kl)(\d*)', front_expr, re.IGNORECASE)
                    if match_xd20_kh_kl:
                        # 提取完整的骰子表达式（如 6d20kh2, 3d20kl）
                        x_str = match_xd20_kh_kl.group(1)
                        kh_or_kl = match_xd20_kh_kl.group(2).lower()
                        kh_kl_count_str = match_xd20_kh_kl.group(3)
                        x = int(x_str) if x_str else 1
                        
                        # 设置force_dice_expr和相关参数
                        s_count = x
                        kh_kl_type = kh_or_kl
                        kh_kl_num = int(kh_kl_count_str) if kh_kl_count_str else None
                        
                        if kh_kl_num is not None:
                            force_dice_expr = f"{x}d20{kh_or_kl}{kh_kl_num}"
                        else:
                            force_dice_expr = f"{x}d20{kh_or_kl}"
                        
                        # 移除这部分，保留后续表达式
                        front_expr = front_expr[len(match_xd20_kh_kl.group(0)):].strip()
                        front_expr_str = front_expr if front_expr else None
                    # 1. 匹配 Xd20+任何符号（包括+-*/）
                    elif re.match(r'^(\d*)[dD]20\s*[+\-*/]\s*', front_expr, re.IGNORECASE):
                        match_xd20_plus = re.match(r'^(\d*)[dD]20\s*[+\-*/]\s*', front_expr, re.IGNORECASE)
                        # 处理 X（D20 视为 1D20）
                        x_str = match_xd20_plus.group(1)
                        x = int(x_str) if x_str else 1  # 无数字时默认为1
                        dice_20 = f"{x}D20"
                        # 移除 Xd20 部分，保留符号和后续表达式
                        symbol_match = re.search(r'[+\-*/]', front_expr[len(match_xd20_plus.group(1)) + (2 if x_str else 3):])
                        if symbol_match:
                            symbol_pos = len(match_xd20_plus.group(1)) + (2 if x_str else 3) + symbol_match.start()
                            front_expr = front_expr[symbol_pos:].strip()
                        front_expr_str = front_expr if front_expr else None
                    else:
                        # 2. 如果不是 Xd20+符号，继续其他逻辑
                        # 匹配纯 Xd20 或 D20
                        match_pure_xd20 = re.match(r'^(\d*)[dD]20\b', front_expr, re.IGNORECASE)
                        if match_pure_xd20:
                            x_str = match_pure_xd20.group(1)
                            x = int(x_str) if x_str else 1  # D20 视为 1D20
                            dice_20 = f"{x}D20"
                            front_expr = front_expr[len(match_pure_xd20.group(0)):].strip()
                            front_expr_str = front_expr if front_expr else None
                        else:
                            # 3. 检查是否以符号开头（+/-/*///），如果是则保持原样
                            match_symbol_start = re.match(r'^[+\-*/]', front_expr)
                            if match_symbol_start:
                                # 前式以符号开头，保持原样
                                front_expr_str = front_expr
            
            # 处理挑战值的固定d20（使用解析出的 back_x_dice_value）
            back_fixed_d20 = 0
            back_fixed_display = ''
            if is_back_x and back_x_dice_value is not None:
                back_fixed_d20 = max(1, back_x_dice_value)
                if 1 <= back_fixed_d20 <= 20:
                    back_fixed_display = f"1D20({back_fixed_d20})"
                else:
                    back_fixed_display = f"固定值({back_fixed_d20})"
            
            # 获取模板配置
            tmp_template_name = 'default'
            tmp_template_customDefault = None
            if flag_is_from_group:
                tmp_groupTemplate = OlivaDiceCore.userConfig.getUserConfigByKey(
                    userId = tmp_hagID,
                    userType = 'group',
                    platform = plugin_event.platform['platform'],
                    userConfigKey = 'groupTemplate',
                    botHash = plugin_event.bot_info.hash
                )
                if tmp_groupTemplate != None:
                    tmp_template_name = tmp_groupTemplate
            tmp_template = OlivaDiceCore.pcCard.pcCardDataGetTemplateByKey(tmp_template_name)
            if tmp_template != None and 'customDefault' in tmp_template:
                tmp_template_customDefault = tmp_template['customDefault']
            
            # 计算前项 (1D20 + 前项表达式)
            # D20 或指定点数（现在总是需要掷骰，除非m参数）
            # 如果有kh/kl修饰符，手动处理骰子并构建详细显示
            if force_dice_expr:
                # 手动骰多个d20并处理kh/kl
                all_d20_rolls = []
                for i in range(s_count):
                    rd_single = OlivaDiceCore.onedice.RD('1D20', tmp_template_customDefault)
                    rd_single.roll()
                    if rd_single.resError != None:
                        dictTValue['tRollPara'] = '1D20'
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_single.resError, dictStrCustom, dictTValue)
                        dictTValue['tResult'] = f"错误的骰子：{error_msg}"
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str.strip())
                        return
                    all_d20_rolls.append(rd_single.resInt)
                
                # 根据kh/kl类型选择骰子
                sorted_rolls = sorted(all_d20_rolls, reverse=(kh_kl_type == 'kh'))
                keep_count = kh_kl_num if kh_kl_num else 1
                keep_count = min(keep_count, len(sorted_rolls))
                
                selected_rolls = sorted_rolls[:keep_count]
                discarded_rolls = sorted_rolls[keep_count:]
                
                # 计算结果（求和）
                result_sum = sum(selected_rolls)
                
                # 构建显示字符串 {选中的 <| 丢弃的}
                selected_str = ', '.join(map(str, selected_rolls))
                if discarded_rolls:
                    discarded_str = ', '.join(map(str, discarded_rolls))
                    detail_display = f"{{{selected_str} <| {discarded_str}}}"
                else:
                    detail_display = f"{{{selected_str}}}"
                
                # 创建模拟的rd_d20对象
                rd_d20 = type('obj', (object,), {})()
                rd_d20.resInt = result_sum
                rd_d20.resError = None
                rd_d20.resDetailData = None
                rd_d20.resDetail = None
                
                # 保存结果
                original_d20 = result_sum
                # 对于kh/kl，只用选中的结果来判断大成功/大失败
                d20_results = selected_rolls
                d20_detail_str = f"{force_dice_expr}={detail_display}({result_sum})"
            elif s_count > 1:
                # 多个d20的情况
                d20_results = []
                d20_details = []
                total_d20 = 0
                
                for i in range(s_count):
                    if i < len(s_fixed_values):
                        # 使用固定值
                        fixed_value = s_fixed_values[i]
                        d20_results.append(fixed_value)
                        d20_details.append(f"D20#{i+1}({fixed_value})")
                        total_d20 += fixed_value
                    else:
                        # 随机掷骰
                        rd_d20_single = OlivaDiceCore.onedice.RD('1D20', tmp_template_customDefault)
                        rd_d20_single.roll()
                        if rd_d20_single.resError != None:
                            dictTValue['tRollPara'] = front_expr_str
                            error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_d20_single.resError, dictStrCustom, dictTValue)
                            dictTValue['tResult'] = f"错误的指定点数：{error_msg}"
                            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShError'], dictTValue)
                            replyMsg(plugin_event, tmp_reply_str.strip())
                            return
                        d20_results.append(rd_d20_single.resInt)
                        d20_details.append(f"D20#{i+1}({rd_d20_single.resInt})")
                        total_d20 += rd_d20_single.resInt
                
                # 创建模拟的rd_d20对象
                rd_d20 = type('obj', (object,), {})()
                rd_d20.resInt = total_d20
                rd_d20.resError = None
                rd_d20.resDetailData = None
                rd_d20.resDetail = f"[{'+'.join(map(str, d20_results))}]"
                
                # 保存原始d20结果和详细信息
                original_d20 = total_d20
                d20_detail_str = f"{s_count}D20"+ "{" + f"{'+'.join(map(str, d20_results))}" + "}" + f"({total_d20})"
            else:
                # 单个d20的情况
                rd_d20 = OlivaDiceCore.onedice.RD(dice_20, tmp_template_customDefault)
                rd_d20.roll()
                if rd_d20.resError != None:
                    dictTValue['tRollPara'] = front_expr_str
                    error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_d20.resError, dictStrCustom, dictTValue)
                    dictTValue['tResult'] = f"错误的指定点数：{error_msg}"
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShError'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str.strip())
                    return
                
                # 保存原始d20结果
                original_d20 = rd_d20.resInt
                d20_results = [rd_d20.resInt]  # 为了兼容多个d20的逻辑
                d20_detail_str = f"{dice_20}={rd_d20.resInt}"
            
            # 应用 x 修饰符（u/d）
            if is_x and x_modifier and x_dice_value is not None:
                if x_modifier == 'u':  # 向上修正：如果骰点低于指定值，修正为指定值
                    if rd_d20.resInt < x_dice_value:
                        rd_d20.resInt = x_dice_value
                elif x_modifier == 'd':  # 向下修正：如果骰点高于指定值，修正为指定值
                    if rd_d20.resInt > x_dice_value:
                        rd_d20.resInt = x_dice_value

            if front_expr:
                # 检查是否为符号开头的表达式（如 +5, -4, *3d6 等）
                symbol_prefix_match = re.match(r'^([+\-*/])\s*(.*)$', front_expr)
                if symbol_prefix_match and not flag_no_default_d20:
                    # 符号开头的情况：将d20的结果与符号表达式结合
                    symbol = symbol_prefix_match.group(1)
                    expr_after_symbol = symbol_prefix_match.group(2)
                    
                    # 构造完整的表达式，将d20和符号表达式组合
                    combined_expr = f"{rd_d20.resInt}{symbol}{expr_after_symbol}"
                    
                    # 技能替换
                    combined_expr, front_detail = replace_skills(combined_expr.replace('=', '').replace(' ', ''), skill_valueTable, tmp_pcCardRule)
                    rd_combined = OlivaDiceCore.onedice.RD(combined_expr, tmp_template_customDefault)
                    rd_combined.roll()
                    if rd_combined.resError != None:
                        dictTValue['tRollPara'] = front_expr_str
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_combined.resError, dictStrCustom, dictTValue)
                        dictTValue['tResult'] = f"错误的出值：{error_msg}"
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str.strip())
                        return
                    
                    front_result = rd_combined.resInt
                    # 构造显示信息
                    if rd_combined.resDetail and rd_combined.resDetail != str(rd_combined.resInt):
                        front_detail = f"1D20{symbol}{expr_after_symbol}={rd_combined.resDetail}={front_result}"
                    else:
                        front_detail = f"1D20{symbol}{expr_after_symbol}={front_result}"
                else:
                    # 非符号开头的情况或有m参数的情况
                    # 技能替换
                    front_expr, front_detail = replace_skills(front_expr.replace('=', '').replace(' ', ''), skill_valueTable, tmp_pcCardRule)
                    rd_front = OlivaDiceCore.onedice.RD(front_expr, tmp_template_customDefault)
                    rd_front.roll()
                    if rd_front.resError != None:
                        dictTValue['tRollPara'] = front_expr_str
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_front.resError, dictStrCustom, dictTValue)
                        dictTValue['tResult'] = f"错误的出值：{error_msg}"
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str.strip())
                        return
                    # 现在总是有d20（除非m参数）
                    front_result = rd_d20.resInt + rd_front.resInt
                    base_front_str = f"{front_detail}={rd_d20.resInt}+{rd_front.resDetail}={front_result}"
                    if not rd_front.resDetail:
                        base_front_str = f"{front_detail}={front_result}"
                        if front_result != rd_d20.resInt:
                            base_front_str = f"{front_detail}={rd_d20.resInt}+{rd_front.resInt}={front_result}"
                    if flag_no_default_d20:
                        # m参数去除默认d20
                        front_result = rd_front.resInt
                        # 如果有详细掷骰过程，显示完整计算
                        if rd_front.resDetail and rd_front.resDetail != str(rd_front.resInt):
                            front_detail = f"{front_detail}={rd_front.resDetail}={rd_front.resInt}"
                        else:
                            if str(front_detail) == str(rd_front.resInt):
                                front_detail = rd_front.resInt
                            else:
                                front_detail = f"{front_detail}={rd_front.resInt}"
                    elif is_x and x_modifier:
                        # 有x修饰符，显示修正信息
                        if rd_d20.resInt != original_d20:
                            modifier_text = f"修正{x_modifier.upper()}{x_dice_value}"
                            front_detail = f"1D20({original_d20}->{rd_d20.resInt},{modifier_text})+{base_front_str}"
                        else:
                            front_detail = f"1D20+{base_front_str}"
                    elif is_x:
                        front_detail = f"1D20+{base_front_str}" if 1 <= rd_d20.resInt <= 20 else f"固定值({dice_20})+{base_front_str}"
                    elif force_dice_expr:
                        # 有kh/kl的情况，使用force_dice_expr的显示
                        front_detail = f"{d20_detail_str}+{base_front_str}"
                    elif s_count > 1:
                        # 多个d20的情况
                        front_detail = f"{d20_detail_str}+{base_front_str}"
                    else:
                        front_detail = f"{dice_20}+{base_front_str}"
            else:
                front_result = rd_d20.resInt
                if flag_no_default_d20:
                    # m参数去除默认d20，直接为0
                    front_result = 0
                    front_detail = "0"
                elif is_x and x_modifier:
                    # 有x修饰符，显示修正信息
                    if rd_d20.resInt != original_d20:
                        modifier_text = f"修正{x_modifier.upper()}{x_dice_value}"
                        front_detail = f"1D20({original_d20}->{rd_d20.resInt},{modifier_text})={front_result}"
                    else:
                        front_detail = f"1D20={front_result}"
                elif is_x:
                    front_detail = f"1D20={front_result}" if 1 <= rd_d20.resInt <= 20 else f"固定值({dice_20})={front_result}"
                elif force_dice_expr:
                    # 有kh/kl的情况，使用force_dice_expr的显示
                    front_detail = f"{d20_detail_str}={front_result}"
                elif s_count > 1:
                    # 多个d20的情况
                    front_detail = f"{d20_detail_str}={front_result}"
                else:
                    front_detail = f"{dice_20}={front_result}"
            
            # 处理~参数，计算要添加到shm的值，并加到前式结果
            if shm_add_expr:
                # 获取~表达式的显示细节
                shm_add_expr_display, shm_add_detail = replace_skills(shm_add_expr_str.replace('=', '').replace(' ', ''), skill_valueTable, tmp_pcCardRule)
                rd_shm = OlivaDiceCore.onedice.RD(shm_add_expr, tmp_template_customDefault)
                rd_shm.roll()
                if rd_shm.resError != None:
                    dictTValue['tRollPara'] = shm_add_expr_str
                    error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_shm.resError, dictStrCustom, dictTValue)
                    dictTValue['tResult'] = f"错误的shm增加值：{error_msg}"
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShError'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str.strip())
                    return
                shm_add_value = rd_shm.resInt
                
                # 将~表达式的结果加到前式结果中
                old_front_result = front_result
                front_result += shm_add_value
                
                # 更新front_detail显示，添加~部分
                if rd_shm.resDetail and rd_shm.resDetail != str(shm_add_value):
                    shm_display = f"{shm_add_detail}={rd_shm.resDetail}={shm_add_value}"
                else:
                    shm_display = f"{shm_add_detail}={shm_add_value}"
                
                front_detail = f"{front_detail}+({shm_display})={front_result}"

            # 计算后项
            # 处理技能名和表达式
            back_expr, back_detail = replace_skills(back_expr_str.replace('=', '').replace(' ', ''), skill_valueTable, tmp_pcCardRule)
            if not back_expr:
                back_expr = '0' if is_back_x else '10'
            rd_back = OlivaDiceCore.onedice.RD(back_expr, tmp_template_customDefault)
            rd_back.roll()
            
            if rd_back.resError != None:
                dictTValue['tRollPara'] = back_expr_str
                error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_back.resError, dictStrCustom, dictTValue)
                dictTValue['tResult'] = f"错误的挑战值：{error_msg}"
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str.strip())
                return
            
            back_result = rd_back.resInt
            if is_back_x:
                back_result += back_fixed_d20
            # 显示处理
            if rd_back.resDetail and rd_back.resDetail != str(rd_back.resInt):
                if back_detail == rd_back.resDetail:
                    back_detail = f"{back_detail}={back_result - back_fixed_d20 if is_back_x else back_result}"
                else:
                    back_detail = f"{back_detail}={rd_back.resDetail}={back_result - back_fixed_d20 if is_back_x else back_result}"
            else:
                back_detail = back_result - back_fixed_d20 if is_back_x else back_result
            # 挑战值固定D20的显示
            if is_back_x:
                if back_expr != '0':
                    back_detail = f"{back_detail}+({back_fixed_display})={back_result}"
                else:
                    if 1 <= back_fixed_d20 <= 20:
                        back_fixed_display = f"1D20={back_fixed_d20}"
                    else:
                        back_fixed_display = f"固定值({back_fixed_d20})={back_fixed_d20}"
                    back_detail = back_fixed_display

            # 判断结果
            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
            success_level = 0
            b_bouns = 0
            p_bouns = 0
            b_b_bouns = 0
            b_p_bouns = 0
            front_great_success = 0
            front_great_fail = 0
            back_great_success = 0
            back_great_fail = 0

            # 调用d20计算函数来计算成功等级奖励
            d20_challenge_bonus, back_great_success, back_great_fail, back_d20_time, _ = calculate_d20_success_level(rd_back, a_flag)
            
            # 固定值的成功等级判断
            if is_back_x:
                if back_fixed_d20 <= (2 if a_flag else 1):
                    d20_challenge_bonus += 1
                    back_great_fail += 1
                elif back_fixed_d20 >= 20:
                    d20_challenge_bonus -= 1
                    back_great_success += 1
                back_d20_time += 1
            
            if front_result > back_result:
                tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS
                # 计算成功等级
                success_level = max(1, (front_result - back_result + 4) // 5)  # 向上取整
                # 获取初始成功等级
                original_success_level = success_level
                
                # 处理奖励/惩罚等级
                if flag_bp_type == 1:
                    b_bouns = flag_bp_count
                    success_level += b_bouns
                elif flag_bp_type == 2:
                    p_bouns = flag_bp_count
                    success_level -= p_bouns
                # 处理对方奖励/惩罚等级
                if back_flag_bp_type == 1:
                    b_b_bouns = back_flag_bp_count
                    success_level -= b_b_bouns
                elif back_flag_bp_type == 2:
                    b_p_bouns = back_flag_bp_count
                    success_level += b_p_bouns

                # 处理大成功/大失败（多个d20独立计算）
                if not flag_no_default_d20:
                    if s_count > 1:
                        # 多个d20的情况，检查每个d20
                        for i, d20_val in enumerate(d20_results):
                            if d20_val >= 20:
                                front_great_success += 1
                            elif d20_val <= (2 if a_flag else 1):
                                front_great_fail += 1
                        
                        # 新的显示逻辑：比较大成功和大失败的数量
                        if front_great_success > front_great_fail:
                            # 大成功更多，设为大成功
                            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
                        elif front_great_fail > front_great_success:
                            # 大失败更多，设为大失败
                            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_FAIL
                        # 如果相等，不改变结果类型，让挑战值决定成功失败
                    else:
                        # 单个d20的情况
                        if rd_d20.resInt >= 20:
                            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
                            front_great_success = 1
                        elif rd_d20.resInt <= (2 if a_flag else 1):
                            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_FAIL
                            front_great_fail = 1
                
                # 应用大成功/大失败的奖励（净效果）
                net_great_effect = front_great_success - front_great_fail
                success_level += net_great_effect
            else:
                # 失败的情况，也需要检查大失败
                if not flag_no_default_d20:
                    if s_count > 1:
                        # 多个d20的情况，检查每个d20
                        for i, d20_val in enumerate(d20_results):
                            if d20_val >= 20:
                                front_great_success += 1
                            elif d20_val <= (2 if a_flag else 1):
                                front_great_fail += 1
                        
                        # 如果有大失败，设为大失败
                        if front_great_fail > front_great_success:
                            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_FAIL
                        elif front_great_success > front_great_fail:
                            # 虽然失败，但大成功更多，仍显示失败（不改变结果）
                            pass
                    else:
                        # 单个d20的情况
                        if rd_d20.resInt <= (2 if a_flag else 1):
                            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_FAIL
                            front_great_fail = 1
                        elif rd_d20.resInt >= 20:
                            # 虽然骰出20但失败了，仍显示失败（不改变结果）
                            front_great_success = 1
            
            success_level += d20_challenge_bonus
            success_level = max(0, success_level)
            
            # 构建回复
            front_detail = format_long_dice_rolls(front_detail)
            back_detail = format_long_dice_rolls(back_detail)
            dictTValue['tFrontResult'] = front_detail
            dictTValue['tBackResult'] = back_detail
            dictTValue['tSkillCheckReasult'] = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(tmpSkillCheckType, dictStrCustom, dictTValue, tmp_pcHash, tmp_pc_name)
            
            # 添加成功等级
            if front_result > back_result:
                if success_level <= 0:
                    if tmpSkillCheckType in [
                        OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS, 
                        OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
                        ]:
                        dictTValue['tSkillCheckReasult'] = '' # 成功等级小于等于0平手，不显示成功文案
                # 构建计算过程字符串
                calc_steps = []
                # 显示大成功/大失败的净效果
                net_great_effect = front_great_success - front_great_fail
                if net_great_effect != 0:
                    effect_str = ""
                    if front_great_success > 0 and front_great_fail > 0:
                        effect_str = f"(大成功×{front_great_success}-大失败×{front_great_fail})"
                    elif front_great_success > 0:
                        effect_str = f"(大成功{'x'+str(front_great_success) if s_count > 1 else ''})"
                    elif front_great_fail > 0:
                        effect_str = f"(大失败{'x'+str(front_great_fail) if s_count > 1 else ''})"

                    prefix = "+" if net_great_effect > 0 else ""
                    calc_steps.append(f"{prefix}{net_great_effect}{effect_str}")
                else:
                    if front_great_success > 0 and front_great_fail > 0:
                        calc_steps.append(f"+0(大成功×{front_great_success}-大失败×{front_great_fail})")
                
                if b_bouns > 0:
                    calc_steps.append(f"+{b_bouns}(奖励等级)")
                if p_bouns > 0:
                    calc_steps.append(f"-{p_bouns}(惩罚等级)")
                if b_b_bouns > 0:
                    calc_steps.append(f"-{b_b_bouns}(挑战奖励等级)")
                if b_p_bouns > 0:
                    calc_steps.append(f"+{b_p_bouns}(挑战惩罚等级)")
                if d20_challenge_bonus != 0:
                    if back_d20_time >= 2:
                        calc_steps.append(f"{d20_challenge_bonus:+}(挑战大成功/大失败)")  # 自动显示+/-符号
                    else:
                        # 单个d20时根据具体结果显示
                        if back_great_success > 0:
                            calc_steps.append(f"{d20_challenge_bonus:+}(挑战大成功)")
                        elif back_great_fail > 0:
                            calc_steps.append(f"{d20_challenge_bonus:+}(挑战大失败)")
                        else:
                            # 理论上不会走到这里，但可以作为保护
                            calc_steps.append(f"{d20_challenge_bonus:+}(挑战调整)")
                # 只有存在计算步骤时才显示过程
                if calc_steps:
                    success_text = str(original_success_level) + "".join(calc_steps) + f"={success_level}"
                else:
                    success_text = str(success_level)

                dictTValue['tSuccessLevelInt'] = success_text
                dictTValue['tSuccessLevel'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strShSuccessLevel'], 
                    dictTValue
                )
            else:
                dictTValue['tSuccessLevel'] = ''
            
            # 更新人物卡shm值
            if shm_add_value is not None and tmp_pc_name:
                # 获取当前shm值
                current_shm = OlivaDiceCore.pcCard.pcCardDataGetBySkillName(
                    tmp_pcHash,
                    'SHM',
                    hagId=tmp_hagID
                )
                current_shm_value = int(current_shm) if current_shm is not None else 0
                new_shm_value = current_shm_value + shm_add_value
                
                # 更新shm值
                OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
                    tmp_pcHash,
                    'SHM',
                    new_shm_value,
                    tmp_pc_name,
                    hagId=tmp_hagID
                )
                
                # 自动更新群名片
                OlivaDiceCore.msgReply.trigger_auto_sn_update(
                    plugin_event,
                    tmp_pc_id,
                    tmp_pc_platform,
                    tmp_hagID,
                    dictTValue
                )
                
                # 添加shm更新信息到回复中
                dictTValue['tShmOld'] = current_shm_value
                dictTValue['tShmAddValue'] = shm_add_value
                dictTValue['tShmNew'] = new_shm_value
                dictTValue['tShmAdd'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strShShmAdd'], 
                    dictTValue
                )
            else:
                dictTValue['tShmAdd'] = ''
            
            # 根据是否暗骰选择回复方式
            if is_at:
                if flag_hide and flag_is_from_group:
                    dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShHideAtOther'], dictTValue)
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShHideShowAtOther'], dictTValue))
                    OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str.strip())
                else:
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShResultAtOther'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str.strip())
            else:
                if flag_hide and flag_is_from_group:
                    dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShHide'], dictTValue)
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShHideShow'], dictTValue))
                    OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str.strip())
                else:
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShResult'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str.strip())

def format_long_dice_rolls(detail_string):
    """
    当每一次掷骰细节超过100个时，花括号内只显示第一个和最后一个，中间用+...+来表示。
    """
    # 确保处理的是字符串类型
    if not isinstance(detail_string, str):
        return detail_string

    def replacer(match):
        # 获取花括号内的完整内容，例如 "2+1+1+..."
        content = match.group(1)
        rolls = content.split('+')
        if len(rolls) > 100:
            return f"{{{rolls[0]}+...+{rolls[-1]}}}"
        else:
            return match.group(0)
    return re.sub(r'\{([^\}]+)\}', replacer, detail_string)

def replace_skills(expr_str, skill_valueTable, tmp_pcCardRule):
    """
    使用 getExpression 函数替换技能名，并将 0dX 替换为 0
    处理括号内结果≤0的情况，如 (力量-5)d4 当力量≤5时
    """
    if not expr_str:
        return expr_str, expr_str
    # 使用 getExpression 处理表达式
    [processed_expr, expr_show] = OlivaDiceCore.msgReply.getExpression(
        data=expr_str,
        reverse=False,
        valueTable=skill_valueTable,
        pcCardRule=tmp_pcCardRule,
        flagDynamic=True,
        ruleMode='default'
    )
    [processed_detail, expr_show_2] = OlivaDiceCore.msgReply.getExpression(
        data=expr_str,
        reverse=False,
        valueTable=skill_valueTable,
        pcCardRule=tmp_pcCardRule,
        flagDynamic=False,
        ruleMode='default'
    )
    if expr_show != expr_show_2:
        processed_detail = processed_expr
    replaced_expr = processed_expr
    replaced_detail = processed_detail
    # 处理 getExpression 的特殊格式（如 {技能名}）
    if '{' in replaced_detail and '}' in replaced_detail:
        # 提取所有变量
        vars = re.findall(r'\{([^}]+)\}', replaced_detail)
        for var in vars:
            if var in skill_valueTable:
                # 替换为技能名(值)格式
                replaced_detail = replaced_detail.replace(
                    f'{{{var}}}',
                    f'{var}({skill_valueTable[var]})'
                )
    # 处理括号内结果≤0的情况，如 (力量-5)d4
    replaced_expr = handle_negative_dice(replaced_expr)
    return replaced_expr, replaced_detail

def handle_negative_dice(expr_str):
    """
    处理表达式中括号内计算结果≤0的骰子表达式
    例如：(3-5)d4 -> 先计算括号内=-2，然后替换为0
    例如：((3)-3)d4 -> 先计算括号内=0，然后替换为0
    支持嵌套括号
    """
    if not expr_str:
        return expr_str
    
    def find_matching_paren(s, start_pos):
        """
        从 start_pos 开始找到匹配的右括号位置
        处理嵌套括号
        """
        count = 1
        pos = start_pos + 1
        while pos < len(s) and count > 0:
            if s[pos] == '(':
                count += 1
            elif s[pos] == ')':
                count -= 1
            pos += 1
        return pos - 1 if count == 0 else -1
    
    # 反复处理，直到没有可替换的内容
    max_iterations = 20  # 防止无限循环
    iteration = 0
    
    while iteration < max_iterations:
        changed = False
        i = 0
        
        while i < len(expr_str):
            # 查找 ( 后跟随的内容，然后是 )d 或 )D
            if expr_str[i] == '(':
                # 找到匹配的右括号
                close_pos = find_matching_paren(expr_str, i)
                
                if close_pos != -1 and close_pos + 1 < len(expr_str):
                    # 检查右括号后是否跟着 d 或 D
                    if expr_str[close_pos + 1].lower() == 'd':
                        # 找到骰子面数
                        dice_match = re.match(r'd(\d+)\b', expr_str[close_pos + 1:], re.IGNORECASE)
                        if dice_match:
                            # 提取括号内容
                            paren_content = expr_str[i + 1:close_pos]
                            dice_sides = dice_match.group(1)
                            
                            try:
                                # 只允许数字、运算符、空格和括号（包括乘方^）
                                safe_expr = paren_content.strip()
                                if re.match(r'^[\d\s+\-*/().^]+$', safe_expr):
                                    # 将 ^ 转换为 Python 的 ** 运算符
                                    eval_expr = safe_expr.replace('^', '**')
                                    # 计算表达式
                                    result = eval(eval_expr)
                                    
                                    if result <= 0:
                                        # 替换整个 (...)dX 为 0
                                        end_pos = close_pos + 1 + len(dice_match.group(0))
                                        expr_str = expr_str[:i] + '0' + expr_str[end_pos:]
                                        changed = True
                                        break  # 重新开始扫描
                            except:
                                # 计算失败，跳过
                                pass
            i += 1
        
        if not changed:
            break
        iteration += 1
    # 处理 0dX
    expr_str = re.sub(r'(?:\b0|\(0\))[dD]\d+\b', '0', expr_str)
    return expr_str

def calculate_d20_success_level(rd_object, a_flag=False):
    """
    计算挑战值中d20的大成功/大失败：大成功-1，大失败+1
    同时返回所有d20的骰点值列表
    a_flag: 是否将1和2都视为大失败
    """
    if not rd_object or not rd_object.resDetailData:
        return 0, 0, 0, 0, []

    bonus = 0
    great_success = 0
    great_fail = 0
    d20_time = 0
    d20_rolls = []  # 存储所有d20的骰点值
    
    # 使用一个栈(list)来进行深度优先遍历，以处理复杂的嵌套表达式
    nodes_to_visit = list(rd_object.resDetailData)

    while nodes_to_visit:
        node = nodes_to_visit.pop()

        # 如果节点是列表，将其所有元素添加到待访问栈中
        if isinstance(node, list):
            nodes_to_visit.extend(node)
            continue

        # 如果节点是字典，检查其内容
        if isinstance(node, dict):
            # 检查这是否是一个骰点(d)操作的节点
            if 'key' in node and isinstance(node['key'], dict) and node['key'].get('op') == 'd':
                # 检查骰子的面数是否为20
                if node['key'].get('r') == 20:
                    # 检查并获取骰点结果
                    if 'result' in node and isinstance(node['result'], list) and len(node['result']) > 0:
                        dice_rolls = node['result'][0]
                        if isinstance(dice_rolls, list):
                            for roll in dice_rolls:
                                if isinstance(roll, int):
                                    d20_time += 1
                                    d20_rolls.append(roll)  # 保存骰点值
                                    if roll <= (2 if a_flag else 1):
                                        bonus += 1
                                        great_fail += 1
                                    elif roll >= 20:
                                        bonus -= 1
                                        great_success += 1
            
            # 为了处理嵌套结构（如括号内的表达式），将字典中的所有子字典或列表也加入待访问栈
            for value in node.values():
                if isinstance(value, (dict, list)):
                    nodes_to_visit.append(value)
    return bonus, great_success, great_fail, d20_time, d20_rolls