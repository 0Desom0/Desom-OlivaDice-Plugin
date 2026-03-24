# -*- encoding: utf-8 -*-
'''
_______________________    _________________________________________
__  __ \__  /____  _/_ |  / /__    |__  __ \___  _/_  ____/__  ____/
_  / / /_  /  __  / __ | / /__  /| |_  / / /__  / _  /    __  __/   
/ /_/ /_  /____/ /  __ |/ / _  ___ |  /_/ /__/ /  / /___  _  /___   
\____/ /_____/___/  _____/  /_/  |_/_____/ /___/  \____/  /_____/   

@File      :   msgReply.py
@Author    :   lunzhiPenxil仑质
@Contact   :   lunzhipenxil@gmail.com
@License   :   AGPL
@Copyright :   (C) 2020-2021, OlivOS-Team
@Desc      :   None
'''

import OlivOS
import OlivaDiceSanchi
import OlivaDiceCore

# 导入卦象数据
from . import hexagramData

import hashlib
import time
import traceback
from functools import wraps
import copy
import re
import random


def parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin, need_check_permission = True):
    """
    解析消息中的@用户并检查权限
    返回: is_at, at_user_id, cleaned_message_str
    """
    flag_is_from_master = valDict['flag_is_from_master']
    dictTValue = valDict['dictTValue']
    dictStrCustom = valDict['dictStrCustom']
    tmp_reast_str_para = OlivOS.messageAPI.Message_templet('old_string', tmp_reast_str)
    at_user_id = None
    new_tmp_reast_str_parts = []
    is_at = False
    
    for part in tmp_reast_str_para.data:
        if isinstance(part, OlivOS.messageAPI.PARA.at):
            at_user_id = part.data['id']
            tmp_userName01 = OlivaDiceCore.msgReplyModel.get_user_name(plugin_event, at_user_id)
            dictTValue['tUserName01'] = tmp_userName01
            is_at = True
        else:
            if isinstance(part, OlivOS.messageAPI.PARA.text):
                new_tmp_reast_str_parts.append(part.data['text'])
    
    if is_at:
        if plugin_event.platform['platform'] in ['qqGuild']:
            # QQ频道平台直接返回解析结果，不进行权限检查
            cleaned_message = ''.join(new_tmp_reast_str_parts).strip()
            return is_at, at_user_id, cleaned_message
        # 检查发送者是否为管理员或群主
        if not (flag_is_from_group_admin or flag_is_from_master) and need_check_permission:
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strAtOtherPermissionDenied'], 
                dictTValue
            )
            OlivaDiceCore.msgReply.replyMsg(plugin_event, tmp_reply_str)
            return (True, None, None)  # 权限不足
    
    # 返回解析结果
    cleaned_message = ''.join(new_tmp_reast_str_parts).strip()
    return is_at, at_user_id, cleaned_message
def replace_skills(expr_str, skill_valueTable, tmp_pcCardRule):
    """
    使用 getExpression 函数替换技能名，并将 0dX 替换为 0
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

def parse_bp_parameters(expr_str):
    """
    解析表达式中的b/p/u/d参数
    返回: cleaned_expr, b_count, p_count, u_count, d_count
    """
    isMatchWordStart = OlivaDiceCore.msgReply.isMatchWordStart
    getMatchWordStartRight = OlivaDiceCore.msgReply.getMatchWordStartRight
    skipSpaceStart = OlivaDiceCore.msgReply.skipSpaceStart
    
    b_count = 0  # b参数（阴转阳）
    p_count = 0  # p参数（阳转阴+铜钱）
    u_count = 0  # u参数（增加铜钱）
    d_count = 0  # d参数（减少铜钱）
    tmp_reast_str = expr_str
    
    # 循环处理所有参数
    while tmp_reast_str:
        original_str = tmp_reast_str
        
        # 处理b参数（阴转阳）
        if isMatchWordStart(tmp_reast_str, 'b'):
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
        
        # 处理p参数（阳转阴+铜钱）
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
        
        # 处理u参数（增加铜钱）
        elif isMatchWordStart(tmp_reast_str, 'u'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'u')
            # 检查是否有数字指定，只取一位
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                u_count += int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                u_count += 1  # 默认为1
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理d参数（减少铜钱）
        elif isMatchWordStart(tmp_reast_str, 'd'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'd')
            # 检查是否有数字指定，只取一位
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                d_count += int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                d_count += 1  # 默认为1
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 如果没有匹配到任何参数，跳出循环
        if tmp_reast_str == original_str:
            break
    
    # 跳过空格并返回清理后的表达式
    cleaned_expr = skipSpaceStart(tmp_reast_str)
    
    return cleaned_expr, b_count, p_count, u_count, d_count

def roll_three_coins_with_bp(b_count, p_count, u_count=0, d_count=0):
    """
    投掷三枚铜钱并应用b/p/u/d转换
    返回: (转换后的结果列表, 阳的个数, 转换说明列表, 额外增加的铜钱数)
    """
    # 计算实际投掷的铜钱数量（基础3枚 + u增加 - d减少，但至少1枚）
    base_coins = 3
    actual_coins = max(1, base_coins + u_count - d_count)
    
    # b/p相互抵消后，只保留单一方向转换
    b_count, p_count = normalize_bp_counts(b_count, p_count)

    # 投掷铜钱
    rd = OlivaDiceCore.onedice.RD(f'{actual_coins}d2')
    rd.roll()
    if rd.resError is not None:
        return None, 0, [], 0
    
    # 基础投掷结果
    results = []
    for res in rd.resMetaTuple:
        if res == 1:
            results.append('阴')
        else:
            results.append('阳')
    
    # 应用b/p转换
    results, transformations, extra_coins = apply_bp_transformations(results, b_count, p_count)
    
    # 添加u/d参数的说明
    if u_count > 0 or d_count > 0:
        ud_desc = []
        if u_count > 0:
            ud_desc.append(f"增加{u_count}枚铜钱")
        if d_count > 0:
            ud_desc.append(f"减少{d_count}枚铜钱")
        transformations.insert(0, f"铜钱调整：{'+'.join(ud_desc)}，实际投掷{actual_coins}枚")
    
    # 计算阳的个数
    yang_count = sum(1 for r in results if r.startswith('阳'))
    
    return results, yang_count, transformations, extra_coins

def normalize_bp_counts(b_count, p_count):
    """
    规范化b/p数量：二者相互抵消，最终只保留一种
    返回: (normalized_b_count, normalized_p_count)
    """
    net_count = b_count - p_count

    if net_count > 0:
        return net_count, 0
    if net_count < 0:
        return 0, abs(net_count)
    return 0, 0

def roll_divination_coins():
    """
    投签专用：投掷三枚铜钱并返回正反顺序对应的序号
    返回: (铜钱显示列表, 序号)
    """
    coins_display = []
    coins_binary = []

    for i in range(3):
        rd = OlivaDiceCore.onedice.RD('1D2')
        rd.roll()
        if rd.resError is not None:
            raise Exception("投掷铜钱失败")

        coin_result = rd.resMetaTuple[0]
        if coin_result == 1:
            coins_display.append("阴")
            coins_binary.append(0)
        else:
            coins_display.append("阳")
            coins_binary.append(1)

    divination_index = hexagramData.get_divination_index_by_coins(coins_binary)
    if divination_index is None:
        raise Exception("投签结果解析失败")

    return coins_display, divination_index

def determine_tqa_success(attr_value, difficulty, yang_count):
    """
    根据三尺之下规则判断tqa检定是否成功
    返回: (是否成功, 成功等级描述)
    """
    diff = difficulty - attr_value
    
    if diff < 0:  # 难度 < 属性值
        required_yang = 1
        level_desc = "[一阳爻]"
    elif diff == 0:  # 难度 = 属性值
        required_yang = 2
        level_desc = "[二阳爻]"
    elif diff <= 2:  # 难度 > 属性值，差值≤2
        required_yang = 3
        level_desc = "[三阳爻]"
    else:  # 难度 > 属性值，差值>2
        required_yang = 3
        level_desc = "[三阳爻（劣势）]"
    
    success = yang_count >= required_yang
    return success, level_desc, required_yang

def apply_bp_transformations(results, b_count, p_count):
    """
    应用b/p转换到铜钱卦结果
    b_count: 阴转阳的数量
    p_count: 阳转阴的数量（同时增加劣势铜钱数）
    返回: (转换后的结果列表, 转换说明列表, 额外增加的铜钱数)

    规则：
    - b和p先相互抵消，最终只保留单一方向
    - 所有转换仅基于初始投掷结果，不进行连环/套娃转换
    """
    b_count, p_count = normalize_bp_counts(b_count, p_count)

    if b_count <= 0 and p_count <= 0:
        return results, [], 0
    
    # 复制结果以避免修改原数组
    new_results = results.copy()
    transformations = []
    extra_coins = 0
    
    if b_count > 0:
        yin_indices = [i for i, r in enumerate(new_results) if r == '阴']
        actual_b = min(b_count, len(yin_indices))
        if actual_b > 0:
            selected_yin = random.sample(yin_indices, actual_b)
            for idx in selected_yin:
                new_results[idx] = '阳(阴)'
                transformations.append(f"位置{idx+1}: 阴→阳")

    elif p_count > 0:
        yang_indices = [i for i, r in enumerate(new_results) if r == '阳']
        actual_p = min(p_count, len(yang_indices))
        if actual_p > 0:
            selected_yang = random.sample(yang_indices, actual_p)
            for idx in selected_yang:
                new_results[idx] = '阴(阳)'
                transformations.append(f"位置{idx+1}: 阳→阴")

        for i in range(p_count):
            extra_coins += 1
            coin_result = random.choice(['阴', '阳'])
            new_results.append(f'{coin_result}(劣势)')

    return new_results, transformations, extra_coins

def unity_init(plugin_event, Proc):
    pass

def data_init(plugin_event, Proc):
    OlivaDiceSanchi.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

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
        if isMatchWordStart(tmp_reast_str, 'tqav', isCommand = True):
            # tqav命令必须at对方才能进行
            is_at, at_user_id, tmp_reast_str = parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin, need_check_permission = False)
            if not is_at or not at_user_id:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAVNoAtError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return
            
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'tqav')
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            
            # 获取自己和对方的人物卡信息
            my_pc_id = plugin_event.data.user_id
            other_pc_id = at_user_id
            tmp_pc_platform = plugin_event.platform['platform']
            
            # 自己的人物卡
            my_pcHash = OlivaDiceCore.pcCard.getPcHash(my_pc_id, tmp_pc_platform)
            my_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(my_pcHash, tmp_hagID)
            my_pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(my_pcHash, hagId=tmp_hagID) if my_pc_name else {}
            my_skill_valueTable = my_pc_skills.copy()
            
            # 对方的人物卡
            other_pcHash = OlivaDiceCore.pcCard.getPcHash(other_pc_id, tmp_pc_platform)
            other_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(other_pcHash, tmp_hagID)
            other_pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(other_pcHash, hagId=tmp_hagID) if other_pc_name else {}
            other_skill_valueTable = other_pc_skills.copy()
            
            # 获取人物卡规则
            tmp_pcCardRule = 'default'
            if my_pc_name:
                tmp_pcCardRule_new = OlivaDiceCore.pcCard.pcCardDataGetTemplateKey(my_pcHash, my_pc_name)
                if tmp_pcCardRule_new:
                    tmp_pcCardRule = tmp_pcCardRule_new
            
            # 设置名称
            if my_pc_name:
                dictTValue['tName'] = my_pc_name
            else:
                res = plugin_event.get_stranger_info(user_id=my_pc_id)
                dictTValue['tName'] = res['data']['name'] if res else f'用户{my_pc_id}'
            
            if other_pc_name:
                dictTValue['tName01'] = other_pc_name
            else:
                res = plugin_event.get_stranger_info(user_id=other_pc_id)
                dictTValue['tName01'] = res['data']['name'] if res else f'用户{other_pc_id}'
            
            # 解析参数格式：(b/p数字)(表达式)#(b/p数字)(表达式)
            if '#' not in tmp_reast_str:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAVFormatError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return
            
            parts = tmp_reast_str.split('#', 1)
            my_part = parts[0].strip()
            other_part = parts[1].strip()
            
            # 解析自己的参数
            my_part_cleaned, my_b_count, my_p_count, my_u_count, my_d_count = parse_bp_parameters(my_part)
            # 解析对方的参数
            other_part_cleaned, other_b_count, other_p_count, other_u_count, other_d_count = parse_bp_parameters(other_part)
            my_b_count, my_p_count = normalize_bp_counts(my_b_count, my_p_count)
            other_b_count, other_p_count = normalize_bp_counts(other_b_count, other_p_count)
            
            # 计算自己的属性值
            my_value = 0
            my_expr_show = "0"
            if my_part_cleaned:
                try:
                    my_processed_expr, my_expr_show = replace_skills(my_part_cleaned, my_skill_valueTable, tmp_pcCardRule)
                    rd_my = OlivaDiceCore.onedice.RD(my_processed_expr)
                    rd_my.roll()
                    if rd_my.resError is None:
                        my_value = int(rd_my.resInt)
                        # 构建详细显示过程
                        if rd_my.resDetail and rd_my.resDetail != str(rd_my.resInt):
                            if my_expr_show == rd_my.resDetail:
                                my_expr_show = f"{my_expr_show}={my_value}"
                            else:
                                my_expr_show = f"{my_expr_show}={rd_my.resDetail}={my_value}"
                        else:
                            if my_expr_show != str(my_value):
                                my_expr_show = f"{my_expr_show}={my_value}"
                except Exception as e:
                    dictTValue['tRollPara'] = my_part_cleaned
                    if 'rd_my' in locals() and hasattr(rd_my, 'resError') and rd_my.resError:
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_my.resError, dictStrCustom, dictTValue) if hasattr(OlivaDiceCore.msgReplyModel, 'get_SkillCheckError') else str(rd_my.resError)
                    else:
                        error_msg = str(e)
                    dictTValue['tResult'] = error_msg
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMyExprError'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return
            
            # 计算对方的属性值
            other_value = 0
            other_expr_show = "0"
            if other_part_cleaned:
                try:
                    other_processed_expr, other_expr_show = replace_skills(other_part_cleaned, other_skill_valueTable, tmp_pcCardRule)
                    rd_other = OlivaDiceCore.onedice.RD(other_processed_expr)
                    rd_other.roll()
                    if rd_other.resError is None:
                        other_value = int(rd_other.resInt)
                        # 构建详细显示过程
                        if rd_other.resDetail and rd_other.resDetail != str(rd_other.resInt):
                            if other_expr_show == rd_other.resDetail:
                                other_expr_show = f"{other_expr_show}={other_value}"
                            else:
                                other_expr_show = f"{other_expr_show}={rd_other.resDetail}={other_value}"
                        else:
                            if other_expr_show != str(other_value):
                                other_expr_show = f"{other_expr_show}={other_value}"
                except Exception as e:
                    dictTValue['tRollPara'] = other_part_cleaned
                    if 'rd_other' in locals() and hasattr(rd_other, 'resError') and rd_other.resError:
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_other.resError, dictStrCustom, dictTValue) if hasattr(OlivaDiceCore.msgReplyModel, 'get_SkillCheckError') else str(rd_other.resError)
                    else:
                        error_msg = str(e)
                    dictTValue['tResult'] = error_msg
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strOtherExprError'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return
            
            # 双方投掷铜钱
            my_results, my_yang_count, my_transformations, my_extra_coins = roll_three_coins_with_bp(my_b_count, my_p_count, my_u_count, my_d_count)
            other_results, other_yang_count, other_transformations, other_extra_coins = roll_three_coins_with_bp(other_b_count, other_p_count, other_u_count, other_d_count)
            
            if my_results is None or other_results is None:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCoinRollError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return
            
            # 计算最终对抗值
            my_total = my_yang_count + my_value
            other_total = other_yang_count + other_value
            
            # 判断胜负
            if my_total > other_total:
                result_desc = f"{dictTValue['tName']}获胜"
            elif my_total < other_total:
                result_desc = f"{dictTValue['tName01']}获胜"
            else:
                result_desc = "平手"
            
            # 设置模板变量
            dictTValue['tMyAttrResult'] = my_expr_show
            dictTValue['tMyAttrValue'] = str(my_value)
            dictTValue['tMyCoinsResult'] = '、'.join(my_results)
            dictTValue['tMyYangCount'] = str(my_yang_count)
            dictTValue['tMyTotal'] = str(my_total)
            dictTValue['tMyTransformText'] = f"（优势{my_b_count}/劣势{my_p_count}转换）" if (my_b_count > 0 or my_p_count > 0) else ""
            
            dictTValue['tOtherAttrResult'] = other_expr_show
            dictTValue['tOtherAttrValue'] = str(other_value)
            dictTValue['tOtherCoinsResult'] = '、'.join(other_results)
            dictTValue['tOtherYangCount'] = str(other_yang_count)
            dictTValue['tOtherTotal'] = str(other_total)
            dictTValue['tOtherTransformText'] = f"（优势{other_b_count}/劣势{other_p_count}转换）" if (other_b_count > 0 or other_p_count > 0) else ""
            
            dictTValue['tContestResult'] = result_desc
            
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAVResult'], dictTValue)
            replyMsg(plugin_event, tmp_reply_str)
            return
            
        elif isMatchWordStart(tmp_reast_str, 'tqa', isCommand = True):
            is_at, at_user_id, tmp_reast_str = parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin)
            if is_at and not at_user_id:
                return
            
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'tqa')
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            
            # 获取人物卡信息
            tmp_pc_id = at_user_id if at_user_id else plugin_event.data.user_id
            tmp_pc_platform = plugin_event.platform['platform']
            tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(tmp_pc_id, tmp_pc_platform)
            tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
            
            # 获取人物卡规则
            tmp_pcCardRule = 'default'
            tmp_pcCardRule_new = OlivaDiceCore.pcCard.pcCardDataGetTemplateKey(tmp_pcHash, tmp_pc_name)
            if tmp_pcCardRule_new:
                tmp_pcCardRule = tmp_pcCardRule_new
            
            if tmp_pc_name:
                dictTValue['tName'] = tmp_pc_name
            else:
                res = plugin_event.get_stranger_info(user_id=tmp_pc_id)
                dictTValue['tName'] = res['data']['name'] if res else f'用户{tmp_pc_id}'
            
            # 获取技能数据
            pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(tmp_pcHash, hagId=tmp_hagID) if tmp_pc_name else {}
            skill_valueTable = pc_skills.copy()
            if tmp_pc_name:
                skill_valueTable.update(
                    OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                        pcHash=tmp_pcHash,
                        pcCardName=tmp_pc_name,
                        dataKey='mappingRecord',
                        resDefault={}
                    )
                )
            
            # 解析h参数（暗骰）
            flag_hide = False
            if isMatchWordStart(tmp_reast_str, 'h'):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'h')
                flag_hide = True
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            
            # 解析b/p/u/d参数
            tmp_reast_str, b_count, p_count, u_count, d_count = parse_bp_parameters(tmp_reast_str)
            
            # 解析表达式和难度
            if '#' not in tmp_reast_str:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAFormatError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return
            
            parts = tmp_reast_str.split('#', 1)
            attr_part = parts[0].strip()
            difficulty_part = parts[1].strip()
            
            # 计算属性值
            attr_value = 0
            attr_expr_show = "0"
            if attr_part:
                try:
                    attr_processed_expr, attr_expr_show = replace_skills(attr_part, skill_valueTable, tmp_pcCardRule)
                    rd_attr = OlivaDiceCore.onedice.RD(attr_processed_expr)
                    rd_attr.roll()
                    if rd_attr.resError is None:
                        attr_value = int(rd_attr.resInt)
                        # 构建详细显示过程
                        if rd_attr.resDetail and rd_attr.resDetail != str(rd_attr.resInt):
                            if attr_expr_show == rd_attr.resDetail:
                                attr_expr_show = f"{attr_expr_show}={attr_value}"
                            else:
                                attr_expr_show = f"{attr_expr_show}={rd_attr.resDetail}={attr_value}"
                        else:
                            if attr_expr_show != str(attr_value):
                                attr_expr_show = f"{attr_expr_show}={attr_value}"
                    else:
                        raise ValueError("属性表达式解析错误")
                except Exception as e:
                    dictTValue['tRollPara'] = attr_part
                    if hasattr(rd_attr, 'resError') and rd_attr.resError:
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_attr.resError, dictStrCustom, dictTValue) if hasattr(OlivaDiceCore.msgReplyModel, 'get_SkillCheckError') else str(rd_attr.resError)
                    else:
                        error_msg = str(e)
                    dictTValue['tResult'] = error_msg
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strAttrExprError'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return
            
            # 计算难度值
            difficulty_value = 3  # 默认难度
            difficulty_expr_show = "3"
            if difficulty_part:
                try:
                    difficulty_processed_expr, difficulty_expr_show = replace_skills(difficulty_part, skill_valueTable, tmp_pcCardRule)
                    rd_difficulty = OlivaDiceCore.onedice.RD(difficulty_processed_expr)
                    rd_difficulty.roll()
                    if rd_difficulty.resError is None:
                        difficulty_value = int(rd_difficulty.resInt)
                        # 构建详细显示过程
                        if rd_difficulty.resDetail and rd_difficulty.resDetail != str(rd_difficulty.resInt):
                            if difficulty_expr_show == rd_difficulty.resDetail:
                                difficulty_expr_show = f"{difficulty_expr_show}={difficulty_value}"
                            else:
                                difficulty_expr_show = f"{difficulty_expr_show}={rd_difficulty.resDetail}={difficulty_value}"
                        else:
                            if difficulty_expr_show != str(difficulty_value):
                                difficulty_expr_show = f"{difficulty_expr_show}={difficulty_value}"
                    else:
                        raise ValueError("难度表达式解析错误")
                except Exception as e:
                    dictTValue['tRollPara'] = difficulty_part
                    if hasattr(rd_difficulty, 'resError') and rd_difficulty.resError:
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_difficulty.resError, dictStrCustom, dictTValue) if hasattr(OlivaDiceCore.msgReplyModel, 'get_SkillCheckError') else str(rd_difficulty.resError)
                    else:
                        error_msg = str(e)
                    dictTValue['tResult'] = error_msg
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strDifficultyExprError'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return
            
            # 判断是否需要劣势检定
            diff = difficulty_value - attr_value
            need_extra_disadvantage = diff > 2
            if need_extra_disadvantage:
                p_count += 1  # 自动增加一个劣势
            b_count, p_count = normalize_bp_counts(b_count, p_count)
            
            # 投掷铜钱
            results, yang_count, transformations, extra_coins = roll_three_coins_with_bp(b_count, p_count, u_count, d_count)
            if results is None:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCoinRollError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return
            
            # 判断检定结果
            success, level_desc, required_yang = determine_tqa_success(attr_value, difficulty_value, yang_count)
            
            # 成功/失败文案
            if success:
                if difficulty_value <= 3:
                    # 普通成功
                    tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS
                elif difficulty_value <= 6:
                    # 困难成功  
                    tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_HARD_SUCCESS
                else:
                    # 极难成功
                    tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_EXTREME_HARD_SUCCESS
            else:
                tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
            
            success_text = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(tmpSkillCheckType, dictStrCustom, dictTValue, tmp_pcHash, tmp_pc_name)
            
            # 构建显示消息
            coins_display = '、'.join(results)
            transform_text = ""
            if b_count > 0 or p_count > 0:
                transform_parts = []
                if b_count > 0:
                    transform_parts.append(f"优势{b_count}")
                if p_count > 0:
                    transform_parts.append(f"劣势{p_count}")
                transform_text = f"（{'/'.join(transform_parts)}转换）"
            
            extra_difficulty_text = ""
            if need_extra_disadvantage:
                extra_difficulty_text = "（差值>2，自动增加劣势）"
            
            dictTValue['tAttrResult'] = attr_expr_show
            dictTValue['tDifficultyResult'] = difficulty_expr_show
            dictTValue['tCoinsResult'] = coins_display
            dictTValue['tYangCount'] = str(yang_count)
            dictTValue['tRequiredYang'] = str(required_yang)
            dictTValue['tLevelDesc'] = level_desc
            dictTValue['tTransformText'] = transform_text
            dictTValue['tExtraDifficultyText'] = extra_difficulty_text
            dictTValue['tSuccessText'] = success_text
            
            # 根据是否暗骰和代骰选择回复方式
            if is_at:
                if flag_hide and flag_is_from_group:
                    dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAHideAtOther'], dictTValue)
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAHideShowAtOther'], dictTValue))
                    OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str)
                else:
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAAtOther'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
            else:
                if flag_hide and flag_is_from_group:
                    dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAHide'], dictTValue)
                    replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAHideShow'], dictTValue))
                    OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str)
                else:
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strTQAResult'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
            return
            
        elif isMatchWordStart(tmp_reast_str, '摇卦', isCommand = True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '摇卦')
            
            # 摇卦功能实现
            # 投掷六枚铜钱生成卦象
            coins_result = []
            for i in range(6):
                rd = OlivaDiceCore.onedice.RD('1d2')
                rd.roll()
                if rd.resError is not None:
                    dictTValue['tError'] = '投掷铜钱失败'
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strHexagramError'], 
                        dictTValue
                    )
                    replyMsg(plugin_event, tmp_reply_str)
                    return
                
                # 1为阴爻(反面)，2为阳爻(正面)
                coin_result = 0 if rd.resMetaTuple[0] == 1 else 1
                coins_result.append(coin_result)
            
            # 获取卦象编号
            hexagram_num = hexagramData.get_hexagram_by_coins(coins_result)
            if hexagram_num is None:
                dictTValue['tError'] = '卦象生成失败'
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strHexagramError'], 
                    dictTValue
                )
                replyMsg(plugin_event, tmp_reply_str)
                return
            
            # 解析波动属性
            hex_data = hexagramData.hexagram_data[hexagram_num]
            attributes = hex_data["attributes"]
            final_attributes = {}
            fluctuation_results = []
            
            for attr_name, attr_value in attributes.items():
                attr_info = hexagramData.resolve_attribute_fluctuation(attr_value)
                
                if attr_info["type"] == "fixed":
                    # 固定属性，直接使用
                    final_attributes[attr_name] = attr_info["value"]
                else:
                    # 波动属性，需要投掷铜钱
                    rd = OlivaDiceCore.onedice.RD('1d2')
                    rd.roll()
                    if rd.resError is not None:
                        dictTValue['tError'] = '五行属性检定失败'
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strHexagramError'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, tmp_reply_str)
                        return
                    
                    # 1为阴爻(取低值)，2为阳爻(取高值)
                    if rd.resMetaTuple[0] == 1:  # 阴爻
                        final_value = attr_info["low"]
                        result_desc = f"{attr_name}为{attr_value}，投掷结果为阴爻，取低值{final_value}"
                    else:  # 阳爻
                        final_value = attr_info["high"]
                        result_desc = f"{attr_name}为{attr_value}，投掷结果为阳爻，取高值{final_value}"
                    
                    final_attributes[attr_name] = final_value
                    fluctuation_results.append(result_desc)
            
            # 获取上下卦信息
            upper_bagua = hexagramData.get_bagua_info(hex_data["upper"])
            lower_bagua = hexagramData.get_bagua_info(hex_data["lower"])
            
            # 生成铜钱显示（从下到上）
            coin_display = []
            for i in range(6):
                if coins_result[i] == 0:
                    coin_display.append("-- （阴爻）")
                else:
                    coin_display.append("— （阳爻）")
            
            # 填充模板变量
            # tUserName 已在 unity_reply 函数开始时设置
            dictTValue['tHexagramNum'] = f"第{hexagram_num}卦"
            dictTValue['tHexagramName'] = hex_data["name"]
            dictTValue['tHexagramDesc'] = hex_data["description"]
            dictTValue['tUpperBagua'] = f"{upper_bagua['name']}（{upper_bagua['symbol']}）{upper_bagua['element']}"
            dictTValue['tLowerBagua'] = f"{lower_bagua['name']}（{lower_bagua['symbol']}）{lower_bagua['element']}"
            
            # # 生成铜钱结果显示 - 注释掉没用
            # coin_result_lines = []
            # for i, display in enumerate(coin_display):
            #     coin_result_lines.append(f"第{i+1}枚: {display}")
            # dictTValue['tCoinResults'] = '\n'.join(coin_result_lines)
            
            # 生成最终五行属性
            attr_lines = []
            for attr_name, attr_value in final_attributes.items():
                attr_lines.append(f"{attr_name}: {attr_value}")
            dictTValue['tAttributes'] = '；'.join(attr_lines)
            
            # 生成波动检定结果
            if fluctuation_results:
                dictTValue['tFluctuationResults'] = '\n'.join(fluctuation_results)
            else:
                dictTValue['tFluctuationResults'] = "本卦无波动属性"
            
            # 添加特殊能力和特质信息
            if hex_data.get("special"):
                dictTValue['tSpecial'] = hex_data["special"]
            else:
                dictTValue['tSpecial'] = "无特殊能力"
            
            # 计算寿数
            if hex_data.get("lifespan") is not None:
                # 乾为天卦和坤为地卦有固定寿数
                dictTValue['tLifespan'] = str(hex_data["lifespan"])
            else:
                # 其他卦根据五行属性之和计算寿数
                attr_sum = sum(final_attributes.values())
                if attr_sum <= 9:
                    calculated_lifespan = 1
                elif attr_sum == 10:
                    calculated_lifespan = 2
                elif attr_sum >= 11:
                    calculated_lifespan = 3
                else:
                    # 异常情况，使用默认值
                    calculated_lifespan = 2
                dictTValue['tLifespan'] = str(calculated_lifespan)
            
            dictTValue['tTraits'] = hex_data.get("traits", "")
            dictTValue['tNameExamples'] = "、".join(hex_data.get("name_examples", []))
            
            # 发送回复
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strHexagramResult'], 
                dictTValue
            )
            replyMsg(plugin_event, tmp_reply_str)
            return
            
        elif isMatchWordStart(tmp_reast_str, '投签', isCommand = True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '投签')

            # 投签功能实现
            try:
                # 1. 凡世身份
                past_identity_coins, past_identity_index = roll_divination_coins()
                past_identity_desc = hexagramData.mortal_identity_dict.get(past_identity_index)
                if past_identity_desc is None:
                    raise Exception("凡世身份解析失败")

                # 2. 动机
                past_tragedy_coins, past_tragedy_index = roll_divination_coins()
                past_tragedy_desc = hexagramData.motivation_dict.get(past_tragedy_index)
                if past_tragedy_desc is None:
                    raise Exception("动机解析失败")

                # 3. 执念
                current_goal_coins, current_goal_index = roll_divination_coins()
                current_goal_desc = hexagramData.obsession_dict.get(current_goal_index)
                if current_goal_desc is None:
                    raise Exception("执念解析失败")

                # 4. 三官官职 - d3决定
                rd_official = OlivaDiceCore.onedice.RD('1D3')
                rd_official.roll()
                if rd_official.resError is not None:
                    raise Exception("投掷官职失败")

                official_position = rd_official.resInt
                if official_position == 1:
                    official_position_desc = "天官 - 隶属于天官府"
                elif official_position == 2:
                    official_position_desc = "地官 - 隶属于地官府"
                else:  # 3
                    official_position_desc = "水官 - 隶属于水官府"

                # 5. 吉点数量 - 最后投掷三枚铜钱
                lucky_points_coins = []
                lucky_points_yang = 0
                for i in range(3):
                    rd = OlivaDiceCore.onedice.RD('1d2')
                    rd.roll()
                    if rd.resError is not None:
                        raise Exception("投掷铜钱失败")
                    coin_result = rd.resMetaTuple[0]
                    if coin_result == 1:
                        lucky_points_coins.append("阴")
                    else:
                        lucky_points_coins.append("阳")
                        lucky_points_yang += 1

                # 设置模板变量
                dictTValue['tPastIdentity'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strPastIdentity'], 
                    {
                        'tCoinsPastIdentity': '、'.join(past_identity_coins),
                        'tPastIdentityDesc': past_identity_desc
                    }
                )

                dictTValue['tPastTragedy'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strPastTragedy'], 
                    {
                        'tCoinsPastTragedy': '、'.join(past_tragedy_coins),
                        'tPastTragedyDesc': past_tragedy_desc
                    }
                )

                dictTValue['tCurrentGoal'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strCurrentGoal'], 
                    {
                        'tCoinsCurrentGoal': '、'.join(current_goal_coins),
                        'tCurrentGoalDesc': current_goal_desc
                    }
                )

                dictTValue['tOfficialPosition'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strOfficialPosition'], 
                    {
                        'tOfficialPositionDesc': official_position_desc
                    }
                )

                dictTValue['tLuckyPoints'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strLuckyPoints'], 
                    {
                        'tCoinsLuckyPoints': '、'.join(lucky_points_coins),
                        'tLuckyPointsCount': str(lucky_points_yang)
                    }
                )

                # 发送回复
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strDivinationResult'], 
                    dictTValue
                )
                replyMsg(plugin_event, tmp_reply_str)

            except Exception as e:
                dictTValue['tError'] = str(e)
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strDivinationError'], 
                    dictTValue
                )
                replyMsg(plugin_event, tmp_reply_str)
            return
        elif isMatchWordStart(tmp_reast_str, 'tq', isCommand = True):
            is_at, at_user_id, tmp_reast_str = parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin)
            if is_at and not at_user_id:
                return
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'tq')
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            # 默认tName是人物卡名
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
            # 获取人物卡规则
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
            # 获取技能数据
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
            
            # 1. 首先解析h参数（暗骰）
            flag_hide = False
            if isMatchWordStart(tmp_reast_str, 'h'):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'h')
                flag_hide = True
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            
            # 2. 解析次数#铜钱数格式和b/p参数
            tq_number = 3  # 默认3
            tq_times = 1
            expr_show = None
            b_count = 0
            p_count = 0
            u_count = 0
            d_count = 0
            
            if tmp_reast_str:
                if '#' in tmp_reast_str:
                    parts = tmp_reast_str.split('#', 1)
                    front_part = parts[0].strip()
                    back_part = parts[1].strip()
                    
                    # 处理前半部分（次数）
                    if front_part:
                        if front_part.isdigit():
                            tq_times = int(front_part)
                        else:
                            # 前半部分是表达式，按1次处理
                            tq_times = 1
                    
                    # 在后半部分解析b/p/u/d参数
                    back_part, b_count, p_count, u_count, d_count = parse_bp_parameters(back_part)
                    
                    # 处理后半部分剩余的（铜钱数）
                    if back_part:
                        if back_part.isdigit():
                            tq_number = int(back_part)
                        else:
                            # 后半部分是表达式，需要解析
                            try:
                                processed_expr, expr_show = replace_skills(back_part, skill_valueTable, tmp_pcCardRule)
                                rd = OlivaDiceCore.onedice.RD(processed_expr)
                                rd.roll()
                                if rd.resError is None:
                                    tq_number = max(1, min(100, int(rd.resInt)))
                                    # 构建详细显示过程
                                    if rd.resDetail and rd.resDetail != str(rd.resInt):
                                        if expr_show == rd.resDetail:
                                            expr_show = f"{expr_show}={tq_number}"
                                        else:
                                            expr_show = f"{expr_show}={rd.resDetail}={tq_number}"
                                    else:
                                        if expr_show != str(tq_number):
                                            expr_show = f"{expr_show}={tq_number}"
                                        else:
                                            expr_show = str(tq_number)
                                else:
                                    raise ValueError("表达式解析错误")
                            except Exception as e:
                                dictTValue['tRollPara'] = back_part
                                if hasattr(rd, 'resError') and rd.resError:
                                    error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd.resError, dictStrCustom, dictTValue) if hasattr(OlivaDiceCore.msgReplyModel, 'get_SkillCheckError') else str(rd.resError)
                                else:
                                    error_msg = str(e)
                                dictTValue['tResult'] = error_msg
                                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                                    dictStrCustom['strTQError'], 
                                    dictTValue
                                )
                                replyMsg(plugin_event, tmp_reply_str)
                                return
                else:
                    # 没有#号的情况，在整个字符串中解析b/p/u/d参数
                    tmp_reast_str, b_count, p_count, u_count, d_count = parse_bp_parameters(tmp_reast_str)
                    
                    if tmp_reast_str:
                        if tmp_reast_str.isdigit():
                            tq_number = int(tmp_reast_str)
                        else:
                            # 是表达式，需要解析
                            try:
                                processed_expr, expr_show = replace_skills(tmp_reast_str, skill_valueTable, tmp_pcCardRule)
                                rd = OlivaDiceCore.onedice.RD(processed_expr)
                                rd.roll()
                                if rd.resError is None:
                                    tq_number = max(1, min(100, int(rd.resInt)))
                                    # 构建详细显示过程
                                    if rd.resDetail and rd.resDetail != str(rd.resInt):
                                        if expr_show == rd.resDetail:
                                            expr_show = f"{expr_show}={tq_number}"
                                        else:
                                            expr_show = f"{expr_show}={rd.resDetail}={tq_number}"
                                    else:
                                        if expr_show != str(tq_number):
                                            expr_show = f"{expr_show}={tq_number}"
                                        else:
                                            expr_show = str(tq_number)
                                else:
                                    raise ValueError("表达式解析错误")
                            except Exception as e:
                                dictTValue['tRollPara'] = tmp_reast_str
                                if hasattr(rd, 'resError') and rd.resError:
                                    error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd.resError, dictStrCustom, dictTValue) if hasattr(OlivaDiceCore.msgReplyModel, 'get_SkillCheckError') else str(rd.resError)
                                else:
                                    error_msg = str(e)
                                dictTValue['tResult'] = error_msg
                                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                                    dictStrCustom['strTQError'], 
                                    dictTValue
                                )
                                replyMsg(plugin_event, tmp_reply_str)
                                return
            
            # 限制次数
            if tq_times > 10:
                tq_times = 10
            
            # 应用u/d参数调整铜钱数量
            tq_number = max(1, tq_number + u_count - d_count)
            b_count, p_count = normalize_bp_counts(b_count, p_count)
            
            # 校验铜钱数
            if tq_number < 1 or tq_number > 100:
                dictTValue['tResult'] = f"铜钱数量{tq_number}超出范围，请使用1-100之间的数值"
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strTQError'], 
                    dictTValue
                )
                replyMsg(plugin_event, tmp_reply_str)
                return
            # 校验次数
            if tq_times < 1 or tq_times > 10:
                dictTValue['tResult'] = f"投掷次数{tq_times}超出范围，请使用1-10之间的数值"
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strTQError'], 
                    dictTValue
                )
                replyMsg(plugin_event, tmp_reply_str)
                return
            # 多次铜钱卦
            if tq_times == 1:
                yin_count = 0
                yang_count = 0
                rd = OlivaDiceCore.onedice.RD(f'{tq_number}d2')
                rd.roll()
                if rd.resError is not None:
                    dictTValue['tRollPara'] = f'{tq_number}d2'
                    error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd.resError, dictStrCustom, dictTValue) if hasattr(OlivaDiceCore.msgReplyModel, 'get_SkillCheckError') else str(rd.resError)
                    dictTValue['tResult'] = f"铜钱投掷错误: {error_msg}"
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strTQError'], 
                        dictTValue
                    )
                    replyMsg(plugin_event, tmp_reply_str)
                    return
                # 基础投掷结果
                result = []
                for res in rd.resMetaTuple:
                    if res == 1:
                        result.append('阴')
                        yin_count += 1
                    else:
                        result.append('阳')
                        yang_count += 1
                
                # 应用b/p转换
                result, transformations, extra_coins = apply_bp_transformations(result, b_count, p_count)
                
                # 重新计算阴阳数量
                final_yin_count = 0
                final_yang_count = 0
                for res in result:
                    if res.startswith('阴'):
                        final_yin_count += 1
                    elif res.startswith('阳'):
                        final_yang_count += 1
                
                # 设置显示参数
                dictTValue['tNumber'] = str(tq_number + extra_coins)
                dictTValue['tOriginalNumber'] = str(tq_number)
                dictTValue['tYinNumber'] = str(final_yin_count)
                dictTValue['tYangNumber'] = str(final_yang_count)
                dictTValue['tResult'] = '、'.join(result)
                
                # 设置表达式显示
                if expr_show:
                    dictTValue['tExprShow'] = f'{expr_show}+{extra_coins}={str(tq_number + extra_coins)}' if extra_coins > 0 else expr_show
                else:
                    dictTValue['tExprShow'] = f'{tq_number}+{extra_coins}={str(tq_number + extra_coins)}' if extra_coins > 0 else str(tq_number)
                
                # 设置额外铜钱显示
                if extra_coins > 0:
                    dictTValue['tExtraCoinsText'] = f'，劣势转换增加{extra_coins}枚'
                else:
                    dictTValue['tExtraCoinsText'] = ''
                
                # 设置转换过程显示
                transform_info = []
                if b_count > 0:
                    transform_info.append(f'优势{b_count}')
                if p_count > 0:
                    transform_info.append(f'劣势{p_count}')
                if transform_info:
                    dictTValue['tTransformText'] = f'（{"/".join(transform_info)}转换）'
                else:
                    dictTValue['tTransformText'] = ''
                # 根据是否暗骰和代骰选择回复方式
                if is_at:
                    if flag_hide and flag_is_from_group:
                        dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQHideAtOther'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQHideShowAtOther'], 
                            dictTValue
                        ))
                        OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str)
                    else:
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQAtOther'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, tmp_reply_str)
                else:
                    if flag_hide and flag_is_from_group:
                        dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQHide'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQHideShow'], 
                            dictTValue
                        ))
                        OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str)
                    else:
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQResult'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, tmp_reply_str)
                return
            else:
                result_list = []
                all_yin_count = 0
                all_yang_count = 0
                all_extra_coins = 0
                for i in range(tq_times):
                    yin_count = 0
                    yang_count = 0
                    rd = OlivaDiceCore.onedice.RD(f'{tq_number}d2')
                    rd.roll()
                    if rd.resError is not None:
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd.resError, dictStrCustom, dictTValue) if hasattr(OlivaDiceCore.msgReplyModel, 'get_SkillCheckError') else str(rd.resError)
                        result_list.append(f'第{i+1}次：铜钱卦出错 - {error_msg}')
                        continue
                    # 基础投掷结果
                    result = []
                    for res in rd.resMetaTuple:
                        if res == 1:
                            result.append('阴')
                            yin_count += 1
                        else:
                            result.append('阳')
                            yang_count += 1
                    
                    # 应用b/p转换
                    result, transformations, extra_coins = apply_bp_transformations(result, b_count, p_count)
                    all_extra_coins += extra_coins
                    
                    # 重新计算阴阳数量
                    final_yin_count = 0
                    final_yang_count = 0
                    for res in result:
                        if res.startswith('阴'):
                            final_yin_count += 1
                            all_yin_count += 1
                        elif res.startswith('阳'):
                            final_yang_count += 1
                            all_yang_count += 1
                    
                    # 构建结果字符串
                    result_str = f'第{i+1}次：' + '、'.join(result) + f'（阴:{final_yin_count} 阳:{final_yang_count}）'
                    if transformations:
                        result_str += f' [{", ".join(transformations)}]'
                    result_list.append(result_str)
                
                dictTValue['tTime'] = str(tq_times)
                dictTValue['tNumber'] = str(tq_number + all_extra_coins)
                dictTValue['tOriginalNumber'] = str(tq_number)
                dictTValue['tYinNumber'] = str(all_yin_count)
                dictTValue['tYangNumber'] = str(all_yang_count)
                dictTValue['tResult'] = '\n'.join(result_list)
                
                # 设置表达式显示
                if expr_show:
                    dictTValue['tExprShow'] = f'{expr_show}+{extra_coins}={str(tq_number + extra_coins)}' if extra_coins > 0 else expr_show
                else:
                    dictTValue['tExprShow'] = f'{tq_number}+{extra_coins}={str(tq_number + extra_coins)}' if extra_coins > 0 else str(tq_number)
                
                # 设置所有额外铜钱显示
                if all_extra_coins > 0:
                    dictTValue['tAllExtraCoinsText'] = f'，劣势转换总共增加{all_extra_coins}枚'
                else:
                    dictTValue['tAllExtraCoinsText'] = ''
                
                # 设置b/p参数显示
                bp_info = []
                if b_count > 0:
                    bp_info.append(f'优势{b_count}')
                if p_count > 0:
                    bp_info.append(f'劣势{p_count}')
                if bp_info:
                    dictTValue['tBPText'] = f'（每次{"/".join(bp_info)}转换）'
                else:
                    dictTValue['tBPText'] = ''
                # 根据是否暗骰和代骰选择回复方式
                if is_at:
                    if flag_hide and flag_is_from_group:
                        dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQHideAtOtherMore'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQHideShowAtOtherMore'], 
                            dictTValue
                        ))
                        OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str)
                    else:
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQAtOtherMore'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, tmp_reply_str)
                else:
                    if flag_hide and flag_is_from_group:
                        dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQHideMore'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQHideShowMore'], 
                            dictTValue
                        ))
                        OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str)
                    else:
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strTQResultMore'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, tmp_reply_str)
                return
