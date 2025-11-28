# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore，写命令请跳转到第XXX行。
'''

import OlivOS
import OlivaDiceTA
import OlivaDiceCore

import copy
import re
import random
import os
import json

def to_half_width(res):
    """
    将字符串中的全角符号转换为半角符号
    """
    result = []
    for char in res:
        code = ord(char)
        # 全角空格
        if code == 0x3000:
            code = 0x0020
        # 全角字符（除空格外）
        elif 0xFF01 <= code <= 0xFF5E:
            code -= 0xFEE0
        result.append(chr(code))
    return ''.join(result)
def get_ta_data_path():
    """获取TA插件数据存储路径"""
    ta_data_path = os.path.join('plugin', 'data', 'OlivaDiceTA')
    if not os.path.exists(ta_data_path):
        os.makedirs(ta_data_path)
    return ta_data_path

def get_chaos_file_path(bot_hash, group_hash):
    """获取群组混沌值文件路径"""
    ta_data_path = get_ta_data_path()
    bot_path = os.path.join(ta_data_path, bot_hash)
    if not os.path.exists(bot_path):
        os.makedirs(bot_path)
    return os.path.join(bot_path, f"{group_hash}.json")

def load_group_data(bot_hash, group_hash):
    """加载群组数据"""
    file_path = get_chaos_file_path(bot_hash, group_hash)
    default_data = {
        'chaos': 0,
        'reality_fail': 0
    }
    
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保数据格式正确
                if isinstance(data, dict) and 'chaos' in data and 'reality_fail' in data:
                    return data
        except:
            pass
    
    return default_data

def save_group_data(bot_hash, group_hash, data):
    """保存群组数据"""
    file_path = get_chaos_file_path(bot_hash, group_hash)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin):
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
            tmp_userName01 = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId = at_user_id,
                userType = 'user',
                platform = plugin_event.platform['platform'],
                userConfigKey = 'userName',
                botHash = plugin_event.bot_info.hash
            )
            plres = plugin_event.get_stranger_info(at_user_id)
            if plres['active']:
                dictTValue['tUserName01'] = plres['data']['name']
            else:
                dictTValue['tUserName01'] = tmp_userName01
            is_at = True
        else:
            if isinstance(part, OlivOS.messageAPI.PARA.text):
                new_tmp_reast_str_parts.append(part.data['text'])
    
    # 返回解析结果
    cleaned_message = ''.join(new_tmp_reast_str_parts).strip()
    return is_at, at_user_id, cleaned_message

def parse_ta_parameters(expr_str, isMatchWordStart, getMatchWordStartRight, skipSpaceStart):
    """
    解析TA检定参数: c, f, b数字, p数字
    返回: cleaned_expr, no_chaos, no_fail, bonus_dice, penalty_dice
    """
    no_chaos = False  # c参数
    no_fail = False   # f参数
    bonus_dice = 0    # b参数，强制改为3的骰子数
    penalty_dice = 0  # p参数，强制改为非3的骰子数
    tmp_reast_str = expr_str
    
    # 循环处理所有参数
    while tmp_reast_str:
        original_str = tmp_reast_str
        
        # 处理c参数（不增加混沌值）
        if isMatchWordStart(tmp_reast_str, 'c'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'c')
            no_chaos = True
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            continue
        
        # 处理f参数（不增加现实改写失败次数）
        elif isMatchWordStart(tmp_reast_str, 'f'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'f')
            no_fail = True
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            continue
        
        # 处理b参数（奖励骰子）
        elif isMatchWordStart(tmp_reast_str, 'b'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'b')
            # 检查是否有数字指定
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                bonus_dice += int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                bonus_dice += 1  # 默认为1
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            continue
        
        # 处理p参数（惩罚骰子）
        elif isMatchWordStart(tmp_reast_str, 'p'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'p')
            # 检查是否有数字指定
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                penalty_dice += int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                penalty_dice += 1  # 默认为1
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            continue
        
        # 如果没有匹配到任何参数，跳出循环
        if tmp_reast_str == original_str:
            break
    
    # 跳过空格并返回清理后的表达式
    cleaned_expr = skipSpaceStart(tmp_reast_str)
    
    return cleaned_expr, no_chaos, no_fail, bonus_dice, penalty_dice

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

def calculate_burnout(skill_value, reality_fail_count, is_reality_alter):
    """
    计算过载值
    skill_value: 技能值
    reality_fail_count: 现实改写失败次数
    is_reality_alter: 是否为现实改写检定(.tr)
    """
    # 技能过载：技能值<=0时产生过载
    skill_burnout = 0 if skill_value > 0 else 1
    
    # 现实改写失败过载：只在.tr检定时生效
    fail_burnout = reality_fail_count if is_reality_alter else 0
    
    total_burnout = skill_burnout + fail_burnout
    return total_burnout, skill_burnout, fail_burnout

def roll_ta_dice(bonus_dice=0, penalty_dice=0, tmp_template_customDefault=None):
    """
    投掷三角机构骰子 (6D4)
    bonus_dice: 强制改为3的非3骰子数量
    penalty_dice: 强制改为非3的3骰子数量
    返回: (原始骰子结果, 修改后骰子结果, 显示详情, 三的数量, 修改详情)
    """
    # 投掷3D6
    original_dice = []
    for i in range(6):
        rd = OlivaDiceCore.onedice.RD('1d4', tmp_template_customDefault)
        rd.roll()
        if rd.resError is None:
            original_dice.append(int(rd.resInt))
        else:
            original_dice.append(1)  # 出错时默认为1
    
    # 复制用于修改
    modified_dice = original_dice.copy()
    modifications = []
    
    # 应用b参数：将非3改为3
    non_three_indices = [i for i, val in enumerate(modified_dice) if val != 3]
    bonus_applied = min(bonus_dice, len(non_three_indices))
    for i in range(bonus_applied):
        idx = non_three_indices[i]
        original_val = modified_dice[idx]
        modified_dice[idx] = 3
        modifications.append(f"3({original_val})")
    
    # 应用p参数：将3改为非3
    three_indices = [i for i, val in enumerate(modified_dice) if val == 3]
    penalty_applied = min(penalty_dice, len(three_indices))
    penalty_chaos = 0
    for i in range(penalty_applied):
        idx = three_indices[i]
        # 随机选择一个1-6但不是3的数字
        new_val = random.choice([1, 2, 4])
        modified_dice[idx] = new_val
        modifications.append(f"{new_val}(3)")
        penalty_chaos += 1  # 每个被强制改为非3的骰子增加1点混沌值
    
    # 计算3的数量
    three_count = sum(1 for val in modified_dice if val == 3)
    
    # 生成显示详情
    if modifications:
        # 有修改时，显示修改详情
        dice_display = []
        mod_index = 0
        for i, (orig, mod) in enumerate(zip(original_dice, modified_dice)):
            if orig != mod:
                dice_display.append(modifications[mod_index])
                mod_index += 1
            else:
                dice_display.append(str(mod))
        display_detail = '[' + ', '.join(dice_display) + ']'
    else:
        # 无修改时，显示原始结果
        display_detail = '[' + ', '.join(map(str, original_dice)) + ']'
    
    return original_dice, modified_dice, display_detail, three_count, penalty_chaos

def apply_burnout(dice_results, burnout_count):
    """
    应用过载效果：将指定数量的3改为非3
    返回: (修改后的骰子结果, 被过载的数量, 过载产生的混沌值)
    """
    if burnout_count <= 0:
        return dice_results, 0, 0
    
    modified_dice = dice_results.copy()
    three_indices = [i for i, val in enumerate(modified_dice) if val == 3]
    burned_count = min(burnout_count, len(three_indices))
    
    for i in range(burned_count):
        idx = three_indices[i]
        # 随机选择一个1-6但不是3的数字
        modified_dice[idx] = random.choice([1, 2, 4, 5, 6])
    
    # 过载产生混沌值：每个被过载的骰子产生1点混沌值
    burnout_chaos = burned_count
    
    return modified_dice, burned_count, burnout_chaos

def determine_ta_result(three_count):
    """
    根据3的数量确定检定结果（仅用于非特殊情况）
    返回: 结果类型 ('failure', 'success')
    注意：真正的大成功（三重升华）需要在调用处单独判断
    """
    if three_count == 0:
        return 'failure'
    else:
        return 'success'

def calculate_chaos_generation(three_count_original, three_count_before_burnout, burnout_count, penalty_count, is_true_triple_ascension, is_triangle_stability):
    """
    计算混沌值生成
    three_count_original: 初始骰子的3的个数
    three_count_before_burnout: 过载前（b/p修改后）骰子的3的个数
    burnout_count: 过载次数（无论是否燃掉3，每个过载都加1点）
    penalty_count: p参数次数
    is_true_triple_ascension: 是否为真正的三重升华（初始骰子就有三个3）
    is_triangle_stability: 是否为三角稳定（最终刚好是3个3但初始不是）
    """
    # 三重升华不产生混沌值
    if is_true_triple_ascension:
        return 0
    
    # 三角稳定不产生混沌值
    if is_triangle_stability:
        return 0
    
    # 其他情况：混沌值 = 6 - 过载前3的个数 + 过载次数 + p参数次数
    # 注意：过载次数无论是否真的燃掉3，每个过载都加1点
    chaos_value = 6 - three_count_before_burnout + burnout_count + penalty_count
    return max(0, chaos_value)

def unity_init(plugin_event, Proc):
    # 这里是插件初始化，通常用于加载配置等
    pass

def data_init(plugin_event, Proc):
    # 这里是数据初始化，通常用于加载数据等
    # 创建TA插件数据存储文件夹
    get_ta_data_path()
    OlivaDiceTA.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

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
    tmp_reast_str = to_half_width(tmp_reast_str)
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
    
    # 检查是否为命令
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
        
        # 判断消息来源类型
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
            
        # 检查插件是否启用
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
            
        # TA/TR 检定命令
        if isMatchWordStart(tmp_reast_str, ['ta', 'tr'], isCommand = True):
            try:
                is_reality_alter = tmp_reast_str.lower().startswith('tr')
                
                # 解析@用户
                is_at, at_user_id, tmp_reast_str = parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin)
                if is_at and not at_user_id:
                    return
                
                # 移除命令前缀
                if isMatchWordStart(tmp_reast_str, 'tr'):
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'tr')
                else:
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'ta')
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                tmp_reast_str = tmp_reast_str.rstrip(' ')
                
                # 检查是否为多次投掷格式 (.ta3#技能)
                roll_times = 1
                if '#' in tmp_reast_str:
                    # 检查#前是否有数字
                    parts = tmp_reast_str.split('#', 1)
                    front_part = parts[0].strip()
                    skill_part = parts[1].strip() if len(parts) > 1 else ''
                    
                    # 尝试从命令后面解析数字
                    match = re.match(r'^(\d+)(.*)$', front_part)
                    if match:
                        roll_times = int(match.group(1))
                        roll_times = max(1, min(10, roll_times))  # 限制1-10次
                        remaining_params = match.group(2).strip()
                        # 重新组合表达式
                        tmp_reast_str = remaining_params + ' ' + skill_part if remaining_params else skill_part
                    else:
                        tmp_reast_str = front_part + ' ' + skill_part
                
                # 解析参数
                cleaned_expr, no_chaos, no_fail, bonus_dice, penalty_dice = parse_ta_parameters(
                    tmp_reast_str, isMatchWordStart, getMatchWordStartRight, skipSpaceStart
                )
                
                # 确定检定用户
                target_user_id = at_user_id if is_at else plugin_event.data.user_id
                
                # 获取人物卡信息
                tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(target_user_id, plugin_event.platform['platform'])
                tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
                
                if tmp_pc_name:
                    dictTValue['tName'] = tmp_pc_name
                else:
                    res = plugin_event.get_stranger_info(user_id = target_user_id)
                    if res != None and res['active']:
                        dictTValue['tName'] = res['data']['name']
                    else:
                        dictTValue['tName'] = f'用户{target_user_id}'
                
                # 获取技能数据
                pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(tmp_pcHash, hagId=tmp_hagID) if tmp_pc_name else {}
                skill_valueTable = pc_skills.copy()
                
                tmp_pcCardRule = 'default'
                tmp_pcCardRule_new = OlivaDiceCore.pcCard.pcCardDataGetTemplateKey(tmp_pcHash, tmp_pc_name)
                if tmp_pcCardRule_new != None:
                    tmp_pcCardRule = tmp_pcCardRule_new
                
                # 添加映射记录
                if tmp_pc_name != None:
                    skill_valueTable.update(
                        OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                            pcHash = tmp_pcHash,
                            pcCardName = tmp_pc_name,
                            dataKey = 'mappingRecord',
                            resDefault = {}
                        )
                    )
                
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
                
                # 计算技能值（为1就代表裸放无过载）
                skill_value = 1
                skill_detail = "1"
                if cleaned_expr:
                    # 使用replace_skills处理技能替换
                    skill_expr, skill_detail = replace_skills(
                        cleaned_expr.replace('=', '').replace(' ', ''), 
                        skill_valueTable, 
                        tmp_pcCardRule
                    )
                    
                    # 使用RD处理技能表达式
                    rd_skill = OlivaDiceCore.onedice.RD(skill_expr, tmp_template_customDefault)
                    rd_skill.roll()
                    if rd_skill.resError is not None:
                        dictTValue['tRollPara'] = cleaned_expr
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_skill.resError, dictStrCustom, dictTValue)
                        dictTValue['tResult'] = f"错误的技能值：{error_msg}"
                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        return
                    skill_value = rd_skill.resInt
                    
                    # 显示处理
                    if rd_skill.resDetail and rd_skill.resDetail != str(rd_skill.resInt):
                        if skill_detail == rd_skill.resDetail:
                            skill_detail = f"{skill_detail}={skill_value}"
                        else:
                            skill_detail = f"{skill_detail}={rd_skill.resDetail}={skill_value}"
                    else:
                        if skill_detail != str(skill_value):
                            skill_detail = f"{skill_detail}={skill_value}"
                        else:
                            skill_detail = str(skill_value)
                
                # 获取群组数据
                bot_hash = plugin_event.bot_info.hash
                if tmp_hagID:
                    group_hash = OlivaDiceCore.userConfig.getUserHash(
                        tmp_hagID,
                        'group',
                        plugin_event.platform['platform']
                    )
                else:
                    group_hash = tmp_pcHash
                group_data = load_group_data(bot_hash, group_hash)
                
                # 执行检定
                if roll_times == 1:
                    # 单次检定
                    # 计算过载
                    total_burnout, skill_burnout, fail_burnout = calculate_burnout(
                        skill_value, 
                        group_data['reality_fail'], 
                        is_reality_alter
                    )
                    
                    # 投掷骰子
                    original_dice, modified_dice, dice_display, three_count_raw, penalty_chaos = roll_ta_dice(
                        bonus_dice, penalty_dice, tmp_template_customDefault
                    )
                    
                    # three_count_raw 是 b/p 修改后、过载前的3的个数
                    three_count_before_burnout = three_count_raw
                    
                    # 应用过载
                    final_dice, burned_count, burnout_chaos = apply_burnout(modified_dice, total_burnout)
                    three_count_final = sum(1 for val in final_dice if val == 3)
                    
                    # 过载次数：无论是否真的燃掉3，每个过载都加1点混沌值
                    # 所以使用 total_burnout 而不是 burned_count
                    actual_burnout_count = total_burnout
                    
                    # 更新骰子显示
                    # 检查是否有任何修改（b/p/过载）
                    has_modifications = (bonus_dice > 0 or penalty_dice > 0 or burned_count > 0)
                    
                    if has_modifications:
                        # 有修改时显示：原始值 → 最终值
                        original_display = '[' + ', '.join(map(str, original_dice)) + ']'
                        
                        # 生成最终值显示（包含过载标记）
                        final_parts = []
                        for i, (orig_val, mod_val, final_val) in enumerate(zip(original_dice, modified_dice, final_dice)):
                            if mod_val == 3 and final_val != 3:  # 被过载的
                                final_parts.append(f"{final_val}(3:过载)")
                            elif orig_val != mod_val:  # 被b/p修改的
                                if mod_val == 3:  # b参数
                                    final_parts.append(f"3({orig_val})")
                                else:  # p参数
                                    final_parts.append(f"{mod_val}(3:过载)")
                            else:
                                final_parts.append(str(final_val))
                        
                        final_display = '[' + ', '.join(final_parts) + ']'
                        dice_display = f"{original_display} → {final_display}"
                    else:
                        # 无修改时只显示原始结果
                        dice_display = '[' + ', '.join(map(str, original_dice)) + ']'
                    
                    # 判断结果类型
                    three_count_original = sum(1 for val in original_dice if val == 3)
                    is_true_triple_ascension = (three_count_original == 3)
                    is_triangle_stability = (three_count_final == 3 and not is_true_triple_ascension)  # 改写后刚好是3个3但初始不是
                    
                    # 确定最终结果类型
                    if is_true_triple_ascension:
                        result_type = 'critical_success'  # 三重升华 -> 大成功
                    elif is_triangle_stability:
                        result_type = 'triangle_stability'  # 三角稳定 -> 特殊成功
                    else:
                        result_type = determine_ta_result(three_count_final)  # 其他情况按正常规则
                    
                    # 计算混沌值变化
                    # 使用过载前的3的个数来计算混沌值，过载次数无论是否燃掉3都加1点
                    chaos_generation = calculate_chaos_generation(
                        three_count_original,
                        three_count_before_burnout,  # 过载前（b/p修改后）的3的个数
                        actual_burnout_count,  # 过载次数（无论是否燃掉3，每个过载都加1点）
                        penalty_dice,  # p参数次数
                        is_true_triple_ascension, 
                        is_triangle_stability
                    )
                    
                    # 计算现实改写失败变化（只有.tr命令且失败时才会产生现实改写失败）
                    fail_generation = 1 if (is_reality_alter and result_type == 'failure') else 0
                    
                    # 应用参数限制
                    if no_chaos:
                        chaos_generation = 0
                    if no_fail:
                        fail_generation = 0
                    
                    # 更新群组数据
                    old_chaos = group_data['chaos']
                    old_fail = group_data['reality_fail']
                    if chaos_generation > 0 or fail_generation > 0:
                        group_data['chaos'] += chaos_generation
                        group_data['reality_fail'] += fail_generation
                        save_group_data(bot_hash, group_hash, group_data)
                    
                    # 设置回复变量
                    dictTValue['tDiceResult'] = dice_display
                    display_burnout = total_burnout + penalty_dice  # 将p参数也算入过载显示
                    dictTValue['tBurnout'] = f"过载: {display_burnout}次" if display_burnout > 0 else ""
                    
                    # 获取技能检定结果文案
                    tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
                    if result_type == 'critical_success':
                        tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
                    elif result_type == 'triangle_stability':
                        tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS  # 三角稳定显示为成功
                    elif result_type == 'success':
                        tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS
                    else:
                        tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
                    
                    dictTValue['tSkillCheckReasult'] = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
                        tmpSkillCheckType, dictStrCustom, dictTValue, tmp_pcHash, tmp_pc_name
                    )
                    
                    # 添加特殊说明
                    if result_type == 'critical_success' and is_true_triple_ascension:
                        dictTValue['tSkillCheckReasult'] += "【三重升华】"
                    elif result_type == 'triangle_stability':
                        dictTValue['tSkillCheckReasult'] += "【三角稳定】"
                    
                    # 混沌值变化信息
                    chaos_change_info = ""
                    if chaos_generation > 0:
                        chaos_change_info += f"混沌值+{chaos_generation}: {old_chaos}->{group_data['chaos']}"
                    if fail_generation > 0:
                        chaos_change_info += f"现实改写失败+{fail_generation}: {old_fail}->{group_data['reality_fail']}"
                    dictTValue['tChaosChange'] = chaos_change_info
                    
                    # 发送回复
                    if is_at:
                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAResultAtOther'], dictTValue)
                    else:
                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAResult'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                
                else:
                    # 多次检定
                    results = []
                    total_chaos_generation = 0
                    total_fail_generation = 0
                    
                    for i in range(roll_times):
                        # 重新获取群组数据（因为可能在循环中发生变化）
                        group_data = load_group_data(bot_hash, group_hash)
                        
                        # 计算过载
                        total_burnout, skill_burnout, fail_burnout = calculate_burnout(
                            skill_value, 
                            group_data['reality_fail'], 
                            is_reality_alter
                        )
                        
                        # 投掷骰子
                        original_dice, modified_dice, dice_display, three_count_raw, penalty_chaos = roll_ta_dice(
                            bonus_dice, penalty_dice, tmp_template_customDefault
                        )
                        
                        # three_count_raw 是 b/p 修改后、过载前的3的个数
                        three_count_before_burnout = three_count_raw
                        
                        # 应用过载
                        final_dice, burned_count, burnout_chaos = apply_burnout(modified_dice, total_burnout)
                        three_count_final = sum(1 for val in final_dice if val == 3)
                        
                        # 过载次数：无论是否真的燃掉3，每个过载都加1点混沌值
                        # 所以使用 total_burnout 而不是 burned_count
                        actual_burnout_count = total_burnout
                        
                        # 更新骰子显示
                        # 检查是否有任何修改（b/p/过载）
                        has_modifications = (bonus_dice > 0 or penalty_dice > 0 or burned_count > 0)
                        
                        if has_modifications:
                            # 有修改时显示：原始值 → 最终值
                            original_display = '[' + ', '.join(map(str, original_dice)) + ']'
                            
                            # 生成最终值显示（包含过载标记）
                            final_parts = []
                            for j, (orig_val, mod_val, final_val) in enumerate(zip(original_dice, modified_dice, final_dice)):
                                if mod_val == 3 and final_val != 3:  # 被过载的
                                    final_parts.append(f"{final_val}(3:过载)")
                                elif orig_val != mod_val:  # 被b/p修改的
                                    if mod_val == 3:  # b参数
                                        final_parts.append(f"3({orig_val})")
                                    else:  # p参数
                                        final_parts.append(f"{mod_val}(3:过载)")
                                else:
                                    final_parts.append(str(final_val))
                            
                            final_display = '[' + ', '.join(final_parts) + ']'
                            dice_display = f"{original_display} -> {final_display}"
                        else:
                            # 无修改时只显示原始结果
                            dice_display = '[' + ', '.join(map(str, original_dice)) + ']'
                        
                        # 判断结果类型
                        three_count_original = sum(1 for val in original_dice if val == 3)
                        is_true_triple_ascension = (three_count_original == 3)  # 初始就是3个3
                        is_triangle_stability = (three_count_final == 3 and not is_true_triple_ascension)  # 改写后刚好是3个3但初始不是
                        
                        # 确定最终结果类型
                        if is_true_triple_ascension:
                            result_type = 'critical_success'  # 三重升华 -> 大成功
                        elif is_triangle_stability:
                            result_type = 'triangle_stability'  # 三角稳定 -> 特殊成功
                        else:
                            result_type = determine_ta_result(three_count_final)  # 其他情况按正常规则
                        
                        # 计算混沌值变化
                        # 使用过载前的3的个数来计算混沌值，过载次数无论是否燃掉3都加1点
                        chaos_generation = calculate_chaos_generation(
                            three_count_original,
                            three_count_before_burnout,  # 过载前（b/p修改后）的3的个数
                            actual_burnout_count,  # 过载次数（无论是否燃掉3，每个过载都加1点）
                            penalty_dice,  # p参数次数
                            is_true_triple_ascension, 
                            is_triangle_stability
                        )
                        
                        # 计算现实改写失败变化（只有.tr命令且失败时才会产生现实改写失败）
                        fail_generation = 1 if (is_reality_alter and result_type == 'failure') else 0
                        
                        # 应用参数限制
                        if no_chaos:
                            chaos_generation = 0
                        if no_fail:
                            fail_generation = 0
                        
                        # 累计变化
                        total_chaos_generation += chaos_generation
                        total_fail_generation += fail_generation
                        
                        # 立即更新群组数据（为下次检定做准备）
                        if chaos_generation > 0 or fail_generation > 0:
                            group_data['chaos'] += chaos_generation
                            group_data['reality_fail'] += fail_generation
                            save_group_data(bot_hash, group_hash, group_data)
                        
                        # 获取结果文案
                        tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
                        if result_type == 'critical_success':
                            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
                        elif result_type == 'triangle_stability':
                            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS  # 三角稳定显示为成功
                        elif result_type == 'success':
                            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS
                        
                        result_text = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
                            tmpSkillCheckType, dictStrCustom, dictTValue, tmp_pcHash, tmp_pc_name
                        )
                        
                        if result_type == 'critical_success' and is_true_triple_ascension:
                            result_text += "【三重升华】"
                        elif result_type == 'triangle_stability':
                            result_text += "【三角稳定】"
                        
                        display_burnout = total_burnout + penalty_dice  # 将p参数也算入过载显示
                        burnout_text = f"过载{display_burnout}" if display_burnout > 0 else "无过载"
                        results.append(f"第{i+1}次: {dice_display} {burnout_text} {result_text}")
                    
                    # 设置多次检定回复变量
                    dictTValue['tRollTimes'] = str(roll_times)
                    dictTValue['tMultiResults'] = '\n'.join(results)
                    
                    # 总变化信息
                    chaos_change_info = ""
                    if total_chaos_generation > 0 or total_fail_generation > 0:
                        final_group_data = load_group_data(bot_hash, group_hash)
                        old_chaos = final_group_data['chaos'] - total_chaos_generation
                        old_fail = final_group_data['reality_fail'] - total_fail_generation
                        
                        if total_chaos_generation > 0:
                            chaos_change_info += f"总混沌值+{total_chaos_generation}: {old_chaos}→{final_group_data['chaos']}"
                        if total_fail_generation > 0:
                            chaos_change_info += f"总现实改写失败+{total_fail_generation}: {old_fail}→{final_group_data['reality_fail']}"
                    
                    dictTValue['tChaosChange'] = chaos_change_info
                    
                    # 发送回复
                    if is_at:
                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAResultMultiAtOther'], dictTValue)
                    else:
                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAResultMulti'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                
            except Exception as e:
                dictTValue['tResult'] = str(e)
                tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
            
            return
        
        # CS/TCS 混沌值管理命令
        if isMatchWordStart(tmp_reast_str, 'tcs', isCommand = True):
            try:
                # 获取用户hash用于私聊存储
                tmp_pcHash = OlivaDiceCore.userConfig.getUserHash(
                    plugin_event.data.user_id,
                    'user',
                    plugin_event.platform['platform']
                )
                
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'tcs')
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                
                # 检查是否有st子命令
                is_set_command = False
                if isMatchWordStart(tmp_reast_str, 'st'):
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'st')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)
                    is_set_command = True
                
                # 获取群组数据
                bot_hash = plugin_event.bot_info.hash
                if tmp_hagID:
                    group_hash = OlivaDiceCore.userConfig.getUserHash(
                        tmp_hagID,
                        'group',
                        plugin_event.platform['platform']
                    )
                else:
                    group_hash = tmp_pcHash
                group_data = load_group_data(bot_hash, group_hash)
                
                # 获取人物卡信息用于表达式解析
                tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
                pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(tmp_pcHash, hagId=tmp_hagID) if tmp_pc_name else {}
                skill_valueTable = pc_skills.copy()
                
                tmp_pcCardRule = 'default'
                tmp_pcCardRule_new = OlivaDiceCore.pcCard.pcCardDataGetTemplateKey(tmp_pcHash, tmp_pc_name)
                if tmp_pcCardRule_new != None:
                    tmp_pcCardRule = tmp_pcCardRule_new
                
                # 添加映射记录
                if tmp_pc_name != None:
                    skill_valueTable.update(
                        OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                            pcHash = tmp_pcHash,
                            pcCardName = tmp_pc_name,
                            dataKey = 'mappingRecord',
                            resDefault = {}
                        )
                    )
                
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
                
                if not tmp_reast_str:
                    # 显示当前混沌值
                    dictTValue['tChaosValue'] = str(group_data['chaos'])
                    tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strCSShow'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                else:
                    # 修改混沌值
                    try:
                        if is_set_command:
                            # 设置混沌值 - 支持骰子表达式
                            if tmp_reast_str.isdigit():
                                # 纯数字
                                new_value = int(tmp_reast_str)
                                expr_detail = tmp_reast_str
                            else:
                                # 骰子表达式或技能引用
                                skill_expr, skill_detail = replace_skills(tmp_reast_str, skill_valueTable, tmp_pcCardRule)
                                rd_chaos = OlivaDiceCore.onedice.RD(skill_expr, tmp_template_customDefault)
                                rd_chaos.roll()
                                if rd_chaos.resError is not None:
                                    dictTValue['tResult'] = f"无效的表达式: {tmp_reast_str}"
                                    tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                                    replyMsg(plugin_event, tmp_reply_str)
                                    return
                                new_value = rd_chaos.resInt
                                # 生成表达式详情
                                if rd_chaos.resDetail and rd_chaos.resDetail != str(new_value):
                                    if skill_detail == rd_chaos.resDetail:
                                        expr_detail = f"{skill_detail}={new_value}"
                                    else:
                                        expr_detail = f"{skill_detail}={rd_chaos.resDetail}={new_value}"
                                else:
                                    if skill_detail != str(new_value):
                                        expr_detail = f"{skill_detail}={new_value}"
                                    else:
                                        expr_detail = str(new_value)
                            new_value = max(0, new_value)  # 不允许负数
                        else:
                            # 增减混沌值 (无符号/负号表示消耗，+号表示增加)
                            if tmp_reast_str.startswith('+'):
                                # +表达式表示增加
                                expr_str = tmp_reast_str[1:]
                                if expr_str.isdigit():
                                    change_value = int(expr_str)
                                    expr_detail = f"+{expr_str}"
                                else:
                                    skill_expr, skill_detail = replace_skills(expr_str, skill_valueTable, tmp_pcCardRule)
                                    rd_chaos = OlivaDiceCore.onedice.RD(skill_expr, tmp_template_customDefault)
                                    rd_chaos.roll()
                                    if rd_chaos.resError is not None:
                                        dictTValue['tResult'] = f"无效的表达式: {tmp_reast_str}"
                                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                                        replyMsg(plugin_event, tmp_reply_str)
                                        return
                                    change_value = rd_chaos.resInt
                                    # 生成表达式详情
                                    if rd_chaos.resDetail and rd_chaos.resDetail != str(change_value):
                                        if skill_detail == rd_chaos.resDetail:
                                            expr_detail = f"+{skill_detail}=+{change_value}"
                                        else:
                                            expr_detail = f"+{skill_detail}=+{rd_chaos.resDetail}=+{change_value}"
                                    else:
                                        if skill_detail != str(change_value):
                                            expr_detail = f"+{skill_detail}=+{change_value}"
                                        else:
                                            expr_detail = f"+{change_value}"
                                new_value = group_data['chaos'] + change_value
                            elif tmp_reast_str.startswith('-'):
                                # -表达式表示减少
                                expr_str = tmp_reast_str[1:]
                                if expr_str.isdigit():
                                    change_value = int(expr_str)
                                    expr_detail = f"-{expr_str}"
                                else:
                                    skill_expr, skill_detail = replace_skills(expr_str, skill_valueTable, tmp_pcCardRule)
                                    rd_chaos = OlivaDiceCore.onedice.RD(skill_expr, tmp_template_customDefault)
                                    rd_chaos.roll()
                                    if rd_chaos.resError is not None:
                                        dictTValue['tResult'] = f"无效的表达式: {tmp_reast_str}"
                                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                                        replyMsg(plugin_event, tmp_reply_str)
                                        return
                                    change_value = rd_chaos.resInt
                                    # 生成表达式详情
                                    if rd_chaos.resDetail and rd_chaos.resDetail != str(change_value):
                                        if skill_detail == rd_chaos.resDetail:
                                            expr_detail = f"-{skill_detail}=-{change_value}"
                                        else:
                                            expr_detail = f"-{skill_detail}=-{rd_chaos.resDetail}=-{change_value}"
                                    else:
                                        if skill_detail != str(change_value):
                                            expr_detail = f"-{skill_detail}=-{change_value}"
                                        else:
                                            expr_detail = f"-{change_value}"
                                new_value = max(0, group_data['chaos'] - change_value)
                            else:
                                # 无符号表达式表示减少（消耗）
                                if tmp_reast_str.isdigit():
                                    change_value = int(tmp_reast_str)
                                    expr_detail = tmp_reast_str
                                else:
                                    skill_expr, skill_detail = replace_skills(tmp_reast_str, skill_valueTable, tmp_pcCardRule)
                                    rd_chaos = OlivaDiceCore.onedice.RD(skill_expr, tmp_template_customDefault)
                                    rd_chaos.roll()
                                    if rd_chaos.resError is not None:
                                        dictTValue['tResult'] = f"无效的表达式: {tmp_reast_str}"
                                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                                        replyMsg(plugin_event, tmp_reply_str)
                                        return
                                    change_value = rd_chaos.resInt
                                    # 生成表达式详情
                                    if rd_chaos.resDetail and rd_chaos.resDetail != str(change_value):
                                        if skill_detail == rd_chaos.resDetail:
                                            expr_detail = f"-{skill_detail}={change_value}"
                                        else:
                                            expr_detail = f"-{skill_detail}={rd_chaos.resDetail}={change_value}"
                                    else:
                                        if skill_detail != str(change_value):
                                            expr_detail = f"-{skill_detail}={change_value}"
                                        else:
                                            expr_detail = str(change_value)
                                new_value = max(0, group_data['chaos'] - change_value)
                        
                        old_value = group_data['chaos']
                        group_data['chaos'] = new_value
                        save_group_data(bot_hash, group_hash, group_data)
                        
                        dictTValue['tOldChaos'] = str(old_value)
                        dictTValue['tNewChaos'] = str(new_value)
                        # 添加表达式详情（如果有的话）
                        if 'expr_detail' in locals() and expr_detail != str(new_value) and not tmp_reast_str.isdigit():
                            dictTValue['tExprDetail'] = f" ({expr_detail})"
                        else:
                            dictTValue['tExprDetail'] = ""
                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strCSChange'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        
                    except ValueError:
                        dictTValue['tResult'] = f"无效的数值: {tmp_reast_str}"
                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        
            except Exception as e:
                dictTValue['tResult'] = str(e)
                tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
            
            return
        
        # TFS 现实改写失败管理命令
        if isMatchWordStart(tmp_reast_str, 'tfs', isCommand = True):
            try:
                # 获取用户hash用于私聊存储
                tmp_pcHash = OlivaDiceCore.userConfig.getUserHash(
                    plugin_event.data.user_id,
                    'user',
                    plugin_event.platform['platform']
                )
                
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'tfs')
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                # 获取群组数据
                bot_hash = plugin_event.bot_info.hash
                if tmp_hagID:
                    group_hash = OlivaDiceCore.userConfig.getUserHash(
                        tmp_hagID,
                        'group',
                        plugin_event.platform['platform']
                    )
                else:
                    group_hash = tmp_pcHash
                group_data = load_group_data(bot_hash, group_hash)
                
                # 获取人物卡信息用于表达式解析
                tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
                pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(tmp_pcHash, hagId=tmp_hagID) if tmp_pc_name else {}
                skill_valueTable = pc_skills.copy()
                
                tmp_pcCardRule = 'default'
                tmp_pcCardRule_new = OlivaDiceCore.pcCard.pcCardDataGetTemplateKey(tmp_pcHash, tmp_pc_name)
                if tmp_pcCardRule_new != None:
                    tmp_pcCardRule = tmp_pcCardRule_new
                
                # 添加映射记录
                if tmp_pc_name != None:
                    skill_valueTable.update(
                        OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                            pcHash = tmp_pcHash,
                            pcCardName = tmp_pc_name,
                            dataKey = 'mappingRecord',
                            resDefault = {}
                        )
                    )
                
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
                
                if not tmp_reast_str:
                    # 显示当前现实改写失败次数
                    dictTValue['tFailValue'] = str(group_data['reality_fail'])
                    tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strFSShow'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                else:
                    # 修改现实改写失败次数
                    try:
                        # 增减现实改写失败次数 (无符号/负号表示消耗，+号表示增加)
                        if tmp_reast_str.startswith('+'):
                            # +表达式表示增加
                            expr_str = tmp_reast_str[1:]
                            if expr_str.isdigit():
                                change_value = int(expr_str)
                                expr_detail = f"+{expr_str}"
                            else:
                                skill_expr, skill_detail = replace_skills(expr_str, skill_valueTable, tmp_pcCardRule)
                                rd_fail = OlivaDiceCore.onedice.RD(skill_expr, tmp_template_customDefault)
                                rd_fail.roll()
                                if rd_fail.resError is not None:
                                    dictTValue['tResult'] = f"无效的表达式: {tmp_reast_str}"
                                    tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                                    replyMsg(plugin_event, tmp_reply_str)
                                    return
                                change_value = rd_fail.resInt
                                # 生成表达式详情
                                if rd_fail.resDetail and rd_fail.resDetail != str(change_value):
                                    if skill_detail == rd_fail.resDetail:
                                        expr_detail = f"+{skill_detail}=+{change_value}"
                                    else:
                                        expr_detail = f"+{skill_detail}=+{rd_fail.resDetail}=+{change_value}"
                                else:
                                    if skill_detail != str(change_value):
                                        expr_detail = f"+{skill_detail}=+{change_value}"
                                    else:
                                        expr_detail = f"+{change_value}"
                            new_value = group_data['reality_fail'] + change_value
                        elif tmp_reast_str.startswith('-'):
                            # -表达式表示减少
                            expr_str = tmp_reast_str[1:]
                            if expr_str.isdigit():
                                change_value = int(expr_str)
                                expr_detail = f"-{expr_str}"
                            else:
                                skill_expr, skill_detail = replace_skills(expr_str, skill_valueTable, tmp_pcCardRule)
                                rd_fail = OlivaDiceCore.onedice.RD(skill_expr, tmp_template_customDefault)
                                rd_fail.roll()
                                if rd_fail.resError is not None:
                                    dictTValue['tResult'] = f"无效的表达式: {tmp_reast_str}"
                                    tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                                    replyMsg(plugin_event, tmp_reply_str)
                                    return
                                change_value = rd_fail.resInt
                                # 生成表达式详情
                                if rd_fail.resDetail and rd_fail.resDetail != str(change_value):
                                    if skill_detail == rd_fail.resDetail:
                                        expr_detail = f"-{skill_detail}=-{change_value}"
                                    else:
                                        expr_detail = f"-{skill_detail}=-{rd_fail.resDetail}=-{change_value}"
                                else:
                                    if skill_detail != str(change_value):
                                        expr_detail = f"-{skill_detail}=-{change_value}"
                                    else:
                                        expr_detail = f"-{change_value}"
                            new_value = max(0, group_data['reality_fail'] - change_value)
                        else:
                            # 无符号表达式表示设置
                            if tmp_reast_str.isdigit():
                                new_value = int(tmp_reast_str)
                                expr_detail = tmp_reast_str
                            else:
                                # 骰子表达式或技能引用
                                skill_expr, skill_detail = replace_skills(tmp_reast_str, skill_valueTable, tmp_pcCardRule)
                                rd_fail = OlivaDiceCore.onedice.RD(skill_expr, tmp_template_customDefault)
                                rd_fail.roll()
                                if rd_fail.resError is not None:
                                    dictTValue['tResult'] = f"无效的表达式: {tmp_reast_str}"
                                    tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                                    replyMsg(plugin_event, tmp_reply_str)
                                    return
                                new_value = rd_fail.resInt
                                # 生成表达式详情
                                if rd_fail.resDetail and rd_fail.resDetail != str(new_value):
                                    if skill_detail == rd_fail.resDetail:
                                        expr_detail = f"{skill_detail}={new_value}"
                                    else:
                                        expr_detail = f"{skill_detail}={rd_fail.resDetail}={new_value}"
                                else:
                                    if skill_detail != str(new_value):
                                        expr_detail = f"{skill_detail}={new_value}"
                                    else:
                                        expr_detail = str(new_value)
                            new_value = max(0, new_value)  # 不允许负数
                        
                        old_value = group_data['reality_fail']
                        group_data['reality_fail'] = new_value
                        save_group_data(bot_hash, group_hash, group_data)
                        
                        dictTValue['tOldFail'] = str(old_value)
                        dictTValue['tNewFail'] = str(new_value)
                        # 添加表达式详情（如果有的话）
                        if 'expr_detail' in locals() and expr_detail != str(new_value) and not tmp_reast_str.isdigit():
                            dictTValue['tExprDetail'] = f" ({expr_detail})"
                        else:
                            dictTValue['tExprDetail'] = ""
                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strFSChange'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        
                    except ValueError:
                        dictTValue['tResult'] = f"无效的数值: {tmp_reast_str}"
                        tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        
            except Exception as e:
                dictTValue['tResult'] = str(e)
                tmp_reply_str = OlivaDiceTA.msgCustomManager.formatReplySTR(dictStrCustom['strTAError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
            
            return