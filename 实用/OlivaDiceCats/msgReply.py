# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore，写命令请跳转到第146行。
'''

import OlivOS
import OlivaDiceCats
import OlivaDiceCore

import copy
import re
import random

_RD_RECORD_CONTEXT = None

def _set_rd_record_context(plugin_event, user_id=None, platform=None, skill_value=None):
    global _RD_RECORD_CONTEXT
    try:
        _RD_RECORD_CONTEXT = {
            'botHash': plugin_event.bot_info.hash,
            'userId': str(user_id if user_id is not None else plugin_event.data.user_id),
            'platform': platform if platform is not None else plugin_event.platform['platform'],
            'skillValue': skill_value,
        }
    except Exception:
        _RD_RECORD_CONTEXT = None

def _save_rd_record(rd, user_id=None, platform=None, skill_value=None):
    try:
        if rd is None or getattr(rd, 'resError', None) is not None:
            return
        ctx = _RD_RECORD_CONTEXT
        if ctx is None:
            return
        OlivaDiceCore.onediceOverride.saveRDDataUser(
            data=rd,
            botHash=ctx['botHash'],
            userId=str(user_id if user_id is not None else ctx['userId']),
            platform=platform if platform is not None else ctx['platform'],
            skillValue=skill_value if skill_value is not None else ctx['skillValue'],
        )
    except Exception:
        pass


def _save_rd_record_detail(raw, detail, value, user_id=None, platform=None, skill_value=None):
    try:
        ctx = _RD_RECORD_CONTEXT
        if ctx is None:
            return
        user_id_real = str(user_id if user_id is not None else ctx['userId'])
        platform_real = platform if platform is not None else ctx['platform']
        bot_hash = ctx['botHash']
        OlivaDiceCore.userConfig.setUserConfigByKey(
            userConfigKey='RDRecord',
            userConfigValue=[str(detail)],
            botHash=bot_hash,
            userId=user_id_real,
            userType='user',
            platform=platform_real,
        )
        OlivaDiceCore.userConfig.setUserConfigByKey(
            userConfigKey='RDRecordRaw',
            userConfigValue=str(raw),
            botHash=bot_hash,
            userId=user_id_real,
            userType='user',
            platform=platform_real,
        )
        OlivaDiceCore.userConfig.setUserConfigByKey(
            userConfigKey='RDRecordInt',
            userConfigValue=value,
            botHash=bot_hash,
            userId=user_id_real,
            userType='user',
            platform=platform_real,
        )
        OlivaDiceCore.userConfig.setUserConfigByKey(
            userConfigKey='RDRecordSkillInt',
            userConfigValue=skill_value if skill_value is not None else ctx['skillValue'],
            botHash=bot_hash,
            userId=user_id_real,
            userType='user',
            platform=platform_real,
        )
        OlivaDiceCore.userConfig.writeUserConfigByUserHash(
            userHash=OlivaDiceCore.userConfig.getUserHash(userId=user_id_real, userType='user', platform=platform_real)
        )
    except Exception:
        pass

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
def get_difficulty_level(difficulty_value):
    """
    根据难度值返回对应的难度等级文本
    """
    if difficulty_value < 2:
        return "近乎自动成功"
    elif difficulty_value <= 4:
        return "极易"
    elif difficulty_value <= 6:
        return "容易"
    elif difficulty_value <= 8:
        return "稍易"
    elif difficulty_value <= 10:
        return "普通"
    elif difficulty_value <= 12:
        return "稍难"
    elif difficulty_value <= 14:
        return "困难"
    elif difficulty_value <= 16:
        return "极难"
    elif difficulty_value <= 18:
        return "近乎不可能"
    else:
        return "不可能（英勇行动）"
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

def parse_expression_and_params(expr_str, isMatchWordStart, getMatchWordStartRight, skipSpaceStart):
    """
    解析表达式开头的参数 b/p、u/d、l
    采用与狩魂者插件相同的解析逻辑
    返回: cleaned_expr, bonus_level, luck_modifier, luck_fixed
    """
    bonus_level = 0  # b/p参数影响成功等级
    luck_modifier = 0  # u/d参数影响幸运骰数量
    luck_fixed = None  # l参数固定幸运骰数量，优先级高于u/d
    tmp_reast_str = expr_str
    
    # 循环处理所有参数
    while tmp_reast_str:
        original_str = tmp_reast_str
        
        # 处理b参数（奖励等级）
        if isMatchWordStart(tmp_reast_str, 'b'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'b')
            # 检查是否有数字指定，只取一位
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                bonus_level += int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                bonus_level += 1  # 默认为1
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理p参数（惩罚等级）
        elif isMatchWordStart(tmp_reast_str, 'p'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'p')
            # 检查是否有数字指定，只取一位
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                bonus_level -= int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                bonus_level -= 1  # 默认为1
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理u参数（增加幸运骰）
        elif isMatchWordStart(tmp_reast_str, 'u'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'u')
            # 检查是否有数字指定，只取一位
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                luck_modifier += int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                luck_modifier += 1  # 默认为1
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理d参数（减少幸运骰）
        elif isMatchWordStart(tmp_reast_str, 'd'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'd')
            # 检查是否有数字指定，只取一位
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                luck_modifier -= int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            else:
                luck_modifier -= 1  # 默认为1
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 处理l参数（固定幸运骰数量）
        elif isMatchWordStart(tmp_reast_str, 'l'):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'l')
            # 检查是否有数字指定，只取一位
            if len(tmp_reast_str) > 0 and tmp_reast_str[0].isdigit():
                luck_fixed = max(1, min(5, int(tmp_reast_str[0])))  # 限制在1-5之间
                tmp_reast_str = tmp_reast_str[1:]
            else:
                luck_fixed = 1  # 默认为1
            # 移除可能的+号
            if len(tmp_reast_str) > 0 and tmp_reast_str[0] == '+':
                tmp_reast_str = tmp_reast_str[1:]
            continue
        
        # 如果没有匹配到任何参数，跳出循环
        if tmp_reast_str == original_str:
            break
    
    # 跳过空格并返回清理后的表达式
    cleaned_expr = skipSpaceStart(tmp_reast_str)
    
    return cleaned_expr, bonus_level, luck_modifier, luck_fixed

def get_pc_luck_value(plugin_event, user_id, tmp_hagID):
    """
    获取人物卡的幸运值
    """
    try:
        tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(user_id, plugin_event.platform['platform'])
        tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
        if tmp_pc_name:
            pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(tmp_pcHash, hagId=tmp_hagID)
            if pc_skills and '幸运' in pc_skills:
                return max(1, min(5, int(pc_skills['幸运'])))
    except:
        pass
    return 1  # 默认幸运值为1

def update_pc_luck_and_skill(plugin_event, user_id, tmp_hagID, luck_change, upgrade_points_change=1):
    """
    更新人物卡的幸运和升级点
    """
    try:
        tmp_pc_platform = plugin_event.platform['platform']
        tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(user_id, tmp_pc_platform)
        tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
        
        if not tmp_pc_name:
            return  # 没有人物卡就不更新
        
        # 更新幸运值
        if luck_change != 0:
            tmp_luck_old = OlivaDiceCore.pcCard.pcCardDataGetBySkillName(
                tmp_pcHash,
                '幸运',
                hagId=tmp_hagID
            )
            current_luck = int(tmp_luck_old) if tmp_luck_old is not None else 1
            new_luck = max(1, min(5, current_luck + int(luck_change)))
            
            OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
                tmp_pcHash,
                '幸运',
                new_luck,
                tmp_pc_name,
                hagId=tmp_hagID
            )
        
        # 更新升级点数
        if upgrade_points_change != 0:
            tmp_skill_old = OlivaDiceCore.pcCard.pcCardDataGetBySkillName(
                tmp_pcHash,
                '成长点',
                hagId=tmp_hagID
            )
            current_skill = int(tmp_skill_old) if tmp_skill_old is not None else 0
            new_skill = current_skill + int(upgrade_points_change)
            
            OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
                tmp_pcHash,
                '成长点',
                new_skill,
                tmp_pc_name,
                hagId=tmp_hagID
            )
    except:
        pass

def roll_luck_dice(luck_count, tmp_template_customDefault=None):
    """
    投掷幸运骰子，自动处理10/1的重投
    返回: (可选择骰子结果列表, 投掷过程详情列表, 大成功数量, 大失败数量, 是否需要手动选择, 确定的结果, 所有详情列表, 带序号的所有详情)
    """
    selectable_results = []  # 可以选择的骰子
    selectable_display_details = []  # 可选择骰子的显示详情（包含重投过程）
    all_details = []  # 所有骰子的详情（包括大成功/大失败）
    all_details_with_index = []  # 带序号的所有骰子详情
    critical_success_count = 0
    critical_failure_count = 0
    confirmed_result = None  # 如果有确定的大成功/大失败结果

    
    for i in range(luck_count):
        rd = OlivaDiceCore.onedice.RD('1d10', tmp_template_customDefault)
        rd.roll()
        _save_rd_record(rd)
        if rd.resError is None:
            original_result = int(rd.resInt)  # 保存原始结果
            result = original_result  # 用于选择的结果（保持原始值）
            detail_parts = [f"{original_result}"]
            is_critical = False
            
            # 检查是否需要重投
            if original_result == 10:
                # 重投检查大成功
                rd_reroll = OlivaDiceCore.onedice.RD('1d10', tmp_template_customDefault)
                rd_reroll.roll()
                _save_rd_record(rd_reroll)
                if rd_reroll.resError is None:
                    reroll_result = int(rd_reroll.resInt)
                    detail_parts.append(f"重投{reroll_result}")
                    if reroll_result == 10:
                        # 大成功，不参与选择
                        critical_success_count += 1
                        detail_parts.append("大成功")
                        is_critical = True
                        if confirmed_result is None:
                            confirmed_result = 10  # 记录一个大成功的结果用于计算
                    # 注意：即使重投不是10，选择时仍然使用原始的10
                else:
                    pass  # 重投失败，保持原值10
            elif original_result == 1:
                # 重投检查大失败
                rd_reroll = OlivaDiceCore.onedice.RD('1d10', tmp_template_customDefault)
                rd_reroll.roll()
                _save_rd_record(rd_reroll)
                if rd_reroll.resError is None:
                    reroll_result = int(rd_reroll.resInt)
                    detail_parts.append(f"重投{reroll_result}")
                    if reroll_result == 1:
                        # 大失败，不参与选择
                        critical_failure_count += 1
                        detail_parts.append("大失败")
                        is_critical = True
                        if confirmed_result is None:
                            confirmed_result = 1  # 记录一个大失败的结果用于计算
                    # 注意：即使重投不是1，选择时仍然使用原始的1
                else:
                    pass  # 重投失败，保持原值1
            
            # 生成显示字符串
            display_detail = ':'.join(detail_parts)
            all_details.append(display_detail)
            
            # 只有非大成功/大失败的骰子才参与选择
            if not is_critical:
                selectable_results.append(result)
                selectable_display_details.append(display_detail)
            
            # 生成带序号的显示字符串（所有骰子都按投掷顺序显示序号）
            all_details_with_index.append(f"[{i+1}] {display_detail}")
        else:
            # 投掷出错，默认为1并参与选择
            display_detail = "1"
            selectable_results.append(1)
            selectable_display_details.append(display_detail)
            all_details.append(display_detail)
            all_details_with_index.append(f"[{i+1}] {display_detail}")
    
    # 判断是否需要手动选择
    need_manual_selection = True
    if critical_success_count > critical_failure_count:
        # 大成功数量多，直接确定为大成功
        need_manual_selection = False
    elif critical_failure_count > critical_success_count:
        # 大失败数量多，直接确定为大失败
        need_manual_selection = False
    elif critical_success_count == critical_failure_count and (critical_success_count > 0):
        # 大成功和大失败数量相等且都大于0，需要手动选择
        need_manual_selection = True
    else:
        # 没有大成功/大失败，或者只有可选择的骰子，需要手动选择
        need_manual_selection = len(selectable_results) > 0
    
    return selectable_results, selectable_display_details, critical_success_count, critical_failure_count, need_manual_selection, confirmed_result, all_details, all_details_with_index

def determine_critical_result(critical_success_count, critical_failure_count):
    """
    根据大成功和大失败的数量确定最终结果类型
    返回: (结果类型, 幸运变化, 升级点变化)
    """
    if critical_success_count > critical_failure_count:
        # 最终结果为大成功：幸运+1，升级点+1
        return 'critical_success', 1, 1
    elif critical_failure_count > critical_success_count:
        # 最终结果为大失败：幸运-1，升级点+1
        return 'critical_failure', -1, 1
    else:
        # 数量相等或都为0，抵消：幸运和升级点都不变
        return None, 0, 0

def unity_init(plugin_event, Proc):
    # 这里是插件初始化，通常用于加载配置等
    pass

def data_init(plugin_event, Proc):
    # 这里是数据初始化，通常用于加载数据等
    OlivaDiceCats.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

def unity_reply(plugin_event, Proc):
    _set_rd_record_context(plugin_event)
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
        if isMatchWordStart(tmp_reast_str, ['catsa'], isCommand = True):
            # 解析@用户
            is_at, at_user_id, tmp_reast_str = parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin)
            if is_at and not at_user_id:
                return
                
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'catsa')
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')
            
            try:
                # 分离前式和后式，如果没有#则默认挑战难度为9
                if '#' in tmp_reast_str:
                    parts = tmp_reast_str.split('#', 1)
                    front_expr = parts[0].strip()
                    back_expr = parts[1].strip()
                else:
                    front_expr = tmp_reast_str.strip()
                    back_expr = '9'
                
                # 解析前式参数
                front_cleaned, front_bonus, front_luck_mod, front_luck_fixed = parse_expression_and_params(front_expr, isMatchWordStart, getMatchWordStartRight, skipSpaceStart)
                # 解析后式参数（后式中的参数效果相反）
                back_cleaned, back_bonus, back_luck_mod, back_luck_fixed = parse_expression_and_params(back_expr, isMatchWordStart, getMatchWordStartRight, skipSpaceStart)
                
                # 确定检定用户
                target_user_id = plugin_event.data.user_id
                
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
                
                # 设置挑战目标信息
                if is_at:
                    # 获取被@用户的人物卡名称，优先使用人物卡名称
                    challenge_target_name = None
                    at_pcHash = OlivaDiceCore.pcCard.getPcHash(at_user_id, plugin_event.platform['platform'])
                    at_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(at_pcHash, tmp_hagID)
                    
                    if at_pc_name:
                        challenge_target_name = at_pc_name
                    elif 'tUserName01' in dictTValue and dictTValue['tUserName01']:
                        challenge_target_name = dictTValue['tUserName01']
                    else:
                        challenge_target_name = f'用户{at_user_id}'
                    
                    dictTValue['tChallengeTarget'] = f'挑战[{challenge_target_name}]'
                else:
                    dictTValue['tChallengeTarget'] = ''
                
                # 获取人物卡技能数据和规则
                # 前式技能表（自己的技能）
                front_pcHash = OlivaDiceCore.pcCard.getPcHash(plugin_event.data.user_id, plugin_event.platform['platform'])
                front_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(front_pcHash, tmp_hagID)
                front_pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(front_pcHash, hagId=tmp_hagID) if front_pc_name else {}
                front_skill_valueTable = front_pc_skills.copy()
                
                # 后式技能表（@对方时用对方的技能，否则用自己的技能）
                if is_at:
                    back_pcHash = OlivaDiceCore.pcCard.getPcHash(at_user_id, plugin_event.platform['platform'])
                    back_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(back_pcHash, tmp_hagID)
                else:
                    back_pcHash = front_pcHash
                    back_pc_name = front_pc_name
                back_pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(back_pcHash, hagId=tmp_hagID) if back_pc_name else {}
                back_skill_valueTable = back_pc_skills.copy()
                
                # 通用技能表（用于显示和一般用途）
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
                if front_pc_name != None:
                    front_skill_valueTable.update(
                        OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                            pcHash = front_pcHash,
                            pcCardName = front_pc_name,
                            dataKey = 'mappingRecord',
                            resDefault = {}
                        )
                    )
                if back_pc_name != None:
                    back_skill_valueTable.update(
                        OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                            pcHash = back_pcHash,
                            pcCardName = back_pc_name,
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
                
                # 保存原始技能名（用于后续的技能更新）
                original_back_skill = None
                if back_cleaned and back_cleaned in back_skill_valueTable:
                    original_back_skill = back_cleaned
                
                # 计算前式结果（使用自己的技能）
                front_value = 0
                front_detail = "0"
                if front_cleaned:
                    # 使用replace_skills处理技能替换（前式用自己的技能）
                    front_expr, front_detail = replace_skills(front_cleaned.replace('=', '').replace(' ', ''), front_skill_valueTable, tmp_pcCardRule)
                    
                    # 使用RD处理前式表达式
                    rd_front = OlivaDiceCore.onedice.RD(front_expr, tmp_template_customDefault)
                    rd_front.roll()
                    _save_rd_record(rd_front)
                    if rd_front.resError is not None:
                        dictTValue['tRollPara'] = front_cleaned
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_front.resError, dictStrCustom, dictTValue)
                        dictTValue['tResult'] = f"错误的出值：{error_msg}"
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsaError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        return
                    front_value = rd_front.resInt
                    
                    # 显示处理
                    if rd_front.resDetail and rd_front.resDetail != str(rd_front.resInt):
                        if front_detail == rd_front.resDetail:
                            front_detail = f"{front_detail}={front_value}"
                        else:
                            front_detail = f"{front_detail}={rd_front.resDetail}={front_value}"
                    else:
                        if front_detail != str(front_value):
                            front_detail = f"{front_detail}={front_value}"
                        else:
                            front_detail = str(front_value)
                
                # 计算后式结果（@对方时用对方的技能，否则用自己的技能）
                back_value = 9  # 默认挑战难度为9
                back_detail = "9"
                if back_cleaned:
                    # 使用replace_skills处理技能替换（后式根据是否@对方选择技能表）
                    back_expr, back_detail = replace_skills(back_cleaned.replace('=', '').replace(' ', ''), back_skill_valueTable, tmp_pcCardRule)
                    
                    # 使用RD处理后式表达式
                    rd_back = OlivaDiceCore.onedice.RD(back_expr, tmp_template_customDefault)
                    rd_back.roll()
                    _save_rd_record(rd_back)
                    if rd_back.resError is not None:
                        dictTValue['tRollPara'] = back_cleaned
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_back.resError, dictStrCustom, dictTValue)
                        dictTValue['tResult'] = f"错误的挑战难度：{error_msg}"
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsaError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        return
                    back_value = rd_back.resInt
                    
                    # 显示处理
                    if rd_back.resDetail and rd_back.resDetail != str(rd_back.resInt):
                        if back_detail == rd_back.resDetail:
                            back_detail = f"{back_detail}={back_value}"
                        else:
                            back_detail = f"{back_detail}={rd_back.resDetail}={back_value}"
                    else:
                        if back_detail != str(back_value):
                            back_detail = f"{back_detail}={back_value}"
                        else:
                            back_detail = str(back_value)
                
                # 处理偶数挑战难度：偶数减1变奇数
                original_back_value = back_value
                if back_value % 2 == 0:  # 如果是偶数
                    back_value -= 1
                    if original_back_value != back_value:
                        back_detail = f"{back_detail}→{back_value}(偶数转奇数)"
                
                # 获取幸运值并计算幸运骰数量
                luck_value = get_pc_luck_value(plugin_event, target_user_id, tmp_hagID)
                
                # 确定最终幸运骰数量，l参数优先级最高
                final_luck_fixed = back_luck_fixed if back_luck_fixed is not None else front_luck_fixed
                if final_luck_fixed is not None:
                    final_luck_count = final_luck_fixed
                else:
                    total_luck_modifier = front_luck_mod - back_luck_mod  # 后式中的u/d效果相反
                    final_luck_count = max(1, min(5, luck_value + total_luck_modifier))
                
                # 投掷幸运骰
                luck_dice_results, luck_dice_display_details, critical_success_count, critical_failure_count, need_manual_selection, confirmed_result, all_details, all_details_with_index = roll_luck_dice(final_luck_count, tmp_template_customDefault)
                
                # .catsa指令的核心逻辑：自动选择最高值
                selected_dice = None
                selected_detail = None
                selected_index = 0
                critical_type = None
                luck_change = 0
                upgrade_points_change = 0
                
                # 处理大成功/大失败的逻辑
                if critical_success_count > critical_failure_count:
                    # 大成功数量多，直接确定为大成功
                    critical_type = 'critical_success'
                    luck_change = 1
                    upgrade_points_change = 1
                    selected_dice = confirmed_result if confirmed_result is not None else 10
                    selected_detail = f"幸运骰({selected_dice})"
                elif critical_failure_count > critical_success_count:
                    # 大失败数量多，直接确定为大失败
                    critical_type = 'critical_failure'
                    luck_change = -1
                    upgrade_points_change = 1
                    selected_dice = confirmed_result if confirmed_result is not None else 1
                    selected_detail = f"幸运骰({selected_dice})"
                elif critical_success_count == critical_failure_count and critical_success_count > 0:
                    # 大成功和大失败数量相等且都大于0，自动选择最高值（选择大成功）
                    critical_type = 'critical_success'
                    luck_change = 1
                    upgrade_points_change = 1
                    selected_dice = 10  # 大成功默认为10
                    selected_detail = f"幸运骰({selected_dice})"
                else:
                    # 没有大成功/大失败，自动选择最高值的普通骰子
                    if len(luck_dice_results) > 0:
                        # 找到最高值的索引
                        max_value = max(luck_dice_results)
                        max_index = luck_dice_results.index(max_value)
                        selected_dice = luck_dice_results[max_index]
                        selected_detail = f"幸运骰({luck_dice_display_details[max_index]})"
                        selected_index = max_index
                    else:
                        # 兜底情况（理论上不应该发生）
                        selected_dice = 5
                        selected_detail = "幸运骰(5)"
                
                # 格式化幸运骰显示（显示所有骰子详情，标注选择的是哪个）
                if len(all_details_with_index) > 0:
                    # 显示所有骰子详情（带序号），并标注选择的骰子
                    dice_display = []
                    first_critical_marked = False  # 标记是否已经标注过第一个大成功/大失败
                    
                    for i, display_detail in enumerate(all_details_with_index):
                        if critical_type and not first_critical_marked:
                            # 如果有大成功/大失败，标注第一个符合条件的
                            if critical_type == 'critical_success' and '大成功' in display_detail:
                                dice_display.append(f"{display_detail} ★自动选择★")
                                first_critical_marked = True
                            elif critical_type == 'critical_failure' and '大失败' in display_detail:
                                dice_display.append(f"{display_detail} ★自动选择★")
                                first_critical_marked = True
                            else:
                                dice_display.append(display_detail)
                        elif not critical_type and i < len(luck_dice_results) and i == selected_index:
                            # 普通情况，标注最高值
                            dice_display.append(f"{display_detail} ★自动选择★")
                        else:
                            dice_display.append(display_detail)
                    
                    dictTValue['tLuckDiceList'] = ' '.join(dice_display)
                    dictTValue['tLuckValue'] = str(final_luck_count)
                else:
                    # 没有可用的骰子结果（兜底情况）
                    dictTValue['tLuckDiceList'] = selected_detail
                    dictTValue['tLuckValue'] = str(final_luck_count)
                
                # 计算最终结果
                total_result = front_value + selected_dice
                success_level = total_result - back_value
                
                # 应用b/p参数
                final_bonus = front_bonus - back_bonus  # 后式中的b/p效果相反
                adjusted_success_level = success_level + final_bonus
                
                # 成功等级除以2并向下取整
                final_success_level = adjusted_success_level // 2
                
                # 构建成功等级计算过程显示
                success_level_process = f"{total_result}-{back_value}={success_level}"
                if final_bonus != 0:
                    bonus_sign = "+" if final_bonus >= 0 else ""
                    success_level_process += f"{bonus_sign}{final_bonus}={adjusted_success_level}"
                if adjusted_success_level != final_success_level:
                    success_level_process += f"÷2={final_success_level}"
                
                # 构建显示过程
                # 前式过程显示
                front_process = front_detail
                
                # 后式过程显示
                back_process = back_detail
                
                # 幸运骰显示（只显示结果，不显示投掷过程）
                luck_display = selected_detail
                
                # 重投信息处理（从幸运骰详情中提取）
                reroll_info = ""
                if critical_success_count > 0 or critical_failure_count > 0:
                    reroll_parts = []
                    if critical_success_count > 0:
                        reroll_parts.append(f"大成功×{critical_success_count}")
                    if critical_failure_count > 0:
                        reroll_parts.append(f"大失败×{critical_failure_count}")
                    reroll_info = f"重投结果: {', '.join(reroll_parts)}\n"

                # 获取难度等级文本
                total_difficulty_level = get_difficulty_level(total_result)
                back_difficulty_level = get_difficulty_level(back_value)
                
                # 设置显示值
                dictTValue['tFrontResult'] = front_process
                dictTValue['tLuckDiceResult'] = luck_display
                dictTValue['tTotalResult'] = f"{total_result}[{total_difficulty_level}]"
                dictTValue['tBackResult'] = f"{back_process}[{back_difficulty_level}]"
                dictTValue['tSuccessLevelInt'] = str(final_success_level)
                dictTValue['tSuccessLevelProcess'] = success_level_process
                dictTValue['tRerollInfo'] = reroll_info
                
                # 判断技能检定类型
                tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
                
                # 处理大成功/大失败
                if critical_type == 'critical_success':
                    tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
                elif critical_type == 'critical_failure':
                    tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_FAIL
                else:
                    # 正常检定结果
                    if final_success_level >= 0:
                        tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS
                    else:
                        tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
                
                # 获取技能检定结果文案
                dictTValue['tSkillCheckReasult'] = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(tmpSkillCheckType, dictStrCustom, dictTValue, tmp_pcHash, tmp_pc_name)
                
                # 更新人物卡的幸运值和升级点（只有在有变化时才更新）
                if luck_change != 0 or upgrade_points_change != 0:
                    update_pc_luck_and_skill(plugin_event, tmp_userID, tmp_hagID, luck_change, upgrade_points_change)
                
                # 根据是否为大成功/大失败选择不同的回复模板
                if critical_type == 'critical_success' or critical_type == 'critical_failure':
                    # 直接大成功/大失败，使用简化模板，显示所有骰子详情
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsaCriticalResult'], dictTValue)
                else:
                    # 正常检定或手动选择后的结果，使用完整模板
                    dictTValue['tSuccessLevel'] = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsSuccessLevel'], dictTValue)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsaResult'], dictTValue)

                _save_rd_record_detail(
                    raw='喵影奇谋自动检定',
                    detail=tmp_reply_str.strip() + '\n\n（无视后面的"="和数值）',
                    value=0,
                )
                
                replyMsg(plugin_event, tmp_reply_str)
                
            except Exception as e:
                dictTValue['tResult'] = str(e)
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsaError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
            
            return
        elif isMatchWordStart(tmp_reast_str, ['cats'], isCommand = True):
            # 检查是否有等待中的cats选择 - 如果有，阻止新的cats命令执行
            tmp_bothash = plugin_event.bot_info.hash
            tmp_hash = OlivaDiceCore.msgReplyModel.contextRegHash([None, plugin_event.data.user_id])
            if tmp_bothash in OlivaDiceCore.crossHook.dictReplyContextReg and tmp_hash in OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash]:
                del OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash][tmp_hash]
                # tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsInvalidSelection'], dictTValue)
                # replyMsg(plugin_event, tmp_reply_str)
                return
            # 解析@用户
            is_at, at_user_id, tmp_reast_str = parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin)
            if is_at and not at_user_id:
                return
                
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'cats')
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')
            
            try:
                # 分离前式和后式，如果没有#则默认挑战难度为9
                if '#' in tmp_reast_str:
                    parts = tmp_reast_str.split('#', 1)
                    front_expr = parts[0].strip()
                    back_expr = parts[1].strip()
                else:
                    front_expr = tmp_reast_str.strip()
                    back_expr = '9'
                
                # 解析前式参数
                front_cleaned, front_bonus, front_luck_mod, front_luck_fixed = parse_expression_and_params(front_expr, isMatchWordStart, getMatchWordStartRight, skipSpaceStart)
                # 解析后式参数（后式中的参数效果相反）
                back_cleaned, back_bonus, back_luck_mod, back_luck_fixed = parse_expression_and_params(back_expr, isMatchWordStart, getMatchWordStartRight, skipSpaceStart)
                
                # 确定检定用户
                target_user_id = plugin_event.data.user_id
                
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
                
                # 设置挑战目标信息
                if is_at:
                    # 获取被@用户的人物卡名称，优先使用人物卡名称
                    challenge_target_name = None
                    at_pcHash = OlivaDiceCore.pcCard.getPcHash(at_user_id, plugin_event.platform['platform'])
                    at_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(at_pcHash, tmp_hagID)
                    
                    if at_pc_name:
                        challenge_target_name = at_pc_name
                    elif 'tUserName01' in dictTValue and dictTValue['tUserName01']:
                        challenge_target_name = dictTValue['tUserName01']
                    else:
                        challenge_target_name = f'用户{at_user_id}'
                    
                    dictTValue['tChallengeTarget'] = f'挑战[{challenge_target_name}]'
                else:
                    dictTValue['tChallengeTarget'] = ''
                
                # 获取人物卡技能数据和规则
                # 前式技能表（自己的技能）
                front_pcHash = OlivaDiceCore.pcCard.getPcHash(plugin_event.data.user_id, plugin_event.platform['platform'])
                front_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(front_pcHash, tmp_hagID)
                front_pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(front_pcHash, hagId=tmp_hagID) if front_pc_name else {}
                front_skill_valueTable = front_pc_skills.copy()
                
                # 后式技能表（@对方时用对方的技能，否则用自己的技能）
                if is_at:
                    back_pcHash = OlivaDiceCore.pcCard.getPcHash(at_user_id, plugin_event.platform['platform'])
                    back_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(back_pcHash, tmp_hagID)
                else:
                    back_pcHash = front_pcHash
                    back_pc_name = front_pc_name
                back_pc_skills = OlivaDiceCore.pcCard.pcCardDataGetByPcName(back_pcHash, hagId=tmp_hagID) if back_pc_name else {}
                back_skill_valueTable = back_pc_skills.copy()
                
                # 通用技能表（用于显示和一般用途）
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
                if front_pc_name != None:
                    front_skill_valueTable.update(
                        OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                            pcHash = front_pcHash,
                            pcCardName = front_pc_name,
                            dataKey = 'mappingRecord',
                            resDefault = {}
                        )
                    )
                if back_pc_name != None:
                    back_skill_valueTable.update(
                        OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                            pcHash = back_pcHash,
                            pcCardName = back_pc_name,
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
                
                # 保存原始技能名（用于后续的技能更新）
                original_back_skill = None
                if back_cleaned and back_cleaned in back_skill_valueTable:
                    original_back_skill = back_cleaned
                
                # 计算前式结果（使用自己的技能）
                front_value = 0
                front_detail = "0"
                if front_cleaned:
                    # 使用replace_skills处理技能替换（前式用自己的技能）
                    front_expr, front_detail = replace_skills(front_cleaned.replace('=', '').replace(' ', ''), front_skill_valueTable, tmp_pcCardRule)
                    
                    # 使用RD处理前式表达式
                    rd_front = OlivaDiceCore.onedice.RD(front_expr, tmp_template_customDefault)
                    rd_front.roll()
                    _save_rd_record(rd_front)
                    if rd_front.resError is not None:
                        dictTValue['tRollPara'] = front_cleaned
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_front.resError, dictStrCustom, dictTValue)
                        dictTValue['tResult'] = f"错误的出值：{error_msg}"
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        return
                    front_value = rd_front.resInt
                    
                    # 显示处理
                    if rd_front.resDetail and rd_front.resDetail != str(rd_front.resInt):
                        if front_detail == rd_front.resDetail:
                            front_detail = f"{front_detail}={front_value}"
                        else:
                            front_detail = f"{front_detail}={rd_front.resDetail}={front_value}"
                    else:
                        if front_detail != str(front_value):
                            front_detail = f"{front_detail}={front_value}"
                        else:
                            front_detail = str(front_value)
                
                # 计算后式结果（@对方时用对方的技能，否则用自己的技能）
                back_value = 9  # 默认挑战难度为9
                back_detail = "9"
                if back_cleaned:
                    # 使用replace_skills处理技能替换（后式根据是否@对方选择技能表）
                    back_expr, back_detail = replace_skills(back_cleaned.replace('=', '').replace(' ', ''), back_skill_valueTable, tmp_pcCardRule)
                    
                    # 使用RD处理后式表达式
                    rd_back = OlivaDiceCore.onedice.RD(back_expr, tmp_template_customDefault)
                    rd_back.roll()
                    _save_rd_record(rd_back)
                    if rd_back.resError is not None:
                        dictTValue['tRollPara'] = back_cleaned
                        error_msg = OlivaDiceCore.msgReplyModel.get_SkillCheckError(rd_back.resError, dictStrCustom, dictTValue)
                        dictTValue['tResult'] = f"错误的挑战难度：{error_msg}"
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsError'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        return
                    back_value = rd_back.resInt
                    
                    # 显示处理
                    if rd_back.resDetail and rd_back.resDetail != str(rd_back.resInt):
                        if back_detail == rd_back.resDetail:
                            back_detail = f"{back_detail}={back_value}"
                        else:
                            back_detail = f"{back_detail}={rd_back.resDetail}={back_value}"
                    else:
                        if back_detail != str(back_value):
                            back_detail = f"{back_detail}={back_value}"
                        else:
                            back_detail = str(back_value)
                
                # 处理偶数挑战难度：偶数减1变奇数
                original_back_value = back_value
                if back_value % 2 == 0:  # 如果是偶数
                    back_value -= 1
                    if original_back_value != back_value:
                        back_detail = f"{back_detail}→{back_value}(偶数转奇数)"
                
                # 获取幸运值并计算幸运骰数量
                luck_value = get_pc_luck_value(plugin_event, target_user_id, tmp_hagID)
                
                # 确定最终幸运骰数量，l参数优先级最高
                final_luck_fixed = back_luck_fixed if back_luck_fixed is not None else front_luck_fixed
                if final_luck_fixed is not None:
                    final_luck_count = final_luck_fixed
                else:
                    total_luck_modifier = front_luck_mod - back_luck_mod  # 后式中的u/d效果相反
                    final_luck_count = max(1, min(5, luck_value + total_luck_modifier))
                
                # 投掷幸运骰
                luck_dice_results, luck_dice_display_details, critical_success_count, critical_failure_count, need_manual_selection, confirmed_result, all_details, all_details_with_index = roll_luck_dice(final_luck_count, tmp_template_customDefault)
                
                # 格式化幸运骰显示
                if need_manual_selection and len(luck_dice_results) > 0:
                    # 需要手动选择时，显示可选择的骰子（包含重投过程）
                    dice_display = []
                    for i, display_detail in enumerate(luck_dice_display_details):
                        dice_display.append(f"[{i+1}] {display_detail}")
                    dictTValue['tLuckDiceList'] = ' '.join(dice_display)
                    dictTValue['tLuckValue'] = str(len(luck_dice_results))
                else:
                    # 自动确定结果时，显示所有骰子详情（带序号）
                    dictTValue['tLuckDiceList'] = ' '.join(all_details_with_index)
                    dictTValue['tLuckValue'] = str(final_luck_count)
                
                # 确定是否需要手动选择
                selected_dice = None
                selected_detail = None
                selected_index = 0
                critical_type = None
                luck_change = 0
                upgrade_points_change = 0
                
                if not need_manual_selection:
                    # 自动确定结果：大成功数量不等于大失败数量
                    critical_type, luck_change, upgrade_points_change = determine_critical_result(critical_success_count, critical_failure_count)
                    
                    # 使用确定的结果（如果没有可选择骰子的话）
                    if confirmed_result is not None:
                        selected_dice = confirmed_result
                        selected_detail = f"幸运骰({confirmed_result})"
                    elif len(luck_dice_results) > 0:
                        # 如果还有可选择的骰子，选择第一个
                        selected_dice = luck_dice_results[0]
                        selected_detail = f"幸运骰({luck_dice_display_details[0]})"
                    else:
                        # 兜底情况
                        selected_dice = 5
                        selected_detail = "幸运骰(5)"
                else:
                    # 需要手动选择
                    if len(luck_dice_results) == 0:
                        # 没有可选择的骰子，可能所有都是大成功/大失败，按数量相等处理
                        critical_type, luck_change, upgrade_points_change = determine_critical_result(critical_success_count, critical_failure_count)
                        selected_dice = confirmed_result if confirmed_result is not None else 5
                        selected_detail = f"幸运骰({selected_dice})"
                    else:
                        # 显示幸运骰并等待选择
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsLuckDice'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        
                        # 等待用户选择
                        tmp_select = OlivaDiceCore.msgReplyModel.replyCONTEXT_regWait(
                            plugin_event = plugin_event,
                            flagBlock = 'allowCommand',
                            hash = OlivaDiceCore.msgReplyModel.contextRegHash([None, plugin_event.data.user_id])
                        )
                    
                        # 处理选择结果
                        if type(tmp_select) == str and tmp_select.isdigit():
                            tmp_select_int = int(tmp_select) - 1
                            if tmp_select_int >= 0 and tmp_select_int < len(luck_dice_results):
                                selected_index = tmp_select_int
                                if tmp_bothash in OlivaDiceCore.crossHook.dictReplyContextReg and tmp_hash in OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash]:
                                    del OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash][tmp_hash]
                            else:
                                # 无效输入，返回错误信息
                                if tmp_bothash in OlivaDiceCore.crossHook.dictReplyContextReg and tmp_hash in OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash]:
                                    del OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash][tmp_hash]
                                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsInvalidSelection'], dictTValue)
                                replyMsg(plugin_event, tmp_reply_str)
                                return
                        elif tmp_select == None:
                            # 超时情况
                            if tmp_bothash in OlivaDiceCore.crossHook.dictReplyContextReg and tmp_hash in OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash]:
                                del OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash][tmp_hash]
                            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsInvalidSelection'], dictTValue)
                            replyMsg(plugin_event, tmp_reply_str)
                            return
                        else:
                            # 无效输入
                            if tmp_bothash in OlivaDiceCore.crossHook.dictReplyContextReg and tmp_hash in OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash]:
                                del OlivaDiceCore.crossHook.dictReplyContextReg[tmp_bothash][tmp_hash]
                            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsInvalidSelection'], dictTValue)
                            replyMsg(plugin_event, tmp_reply_str)
                            return
                        
                        # 获取选择的骰子结果
                        selected_dice = luck_dice_results[selected_index]
                        selected_detail = f"幸运骰({luck_dice_display_details[selected_index]})"
                    
                    # 手动选择情况下，根据大成功/大失败的最终结果计算幸运和升级点变化
                    _, luck_change, upgrade_points_change = determine_critical_result(critical_success_count, critical_failure_count)
                
                # 计算最终结果
                total_result = front_value + selected_dice
                success_level = total_result - back_value
                
                # 应用b/p参数
                final_bonus = front_bonus - back_bonus  # 后式中的b/p效果相反
                adjusted_success_level = success_level + final_bonus
                
                # 成功等级除以2并向下取整
                final_success_level = adjusted_success_level // 2
                
                # 构建成功等级计算过程显示
                success_level_process = f"{total_result}-{back_value}={success_level}"
                if final_bonus != 0:
                    bonus_sign = "+" if final_bonus >= 0 else ""
                    success_level_process += f"{bonus_sign}{final_bonus}={adjusted_success_level}"
                if adjusted_success_level != final_success_level:
                    success_level_process += f"÷2={final_success_level}"
                
                # 构建显示过程
                # 前式过程显示
                front_process = front_detail
                
                # 后式过程显示
                back_process = back_detail
                
                # 幸运骰显示（只显示结果，不显示投掷过程）
                luck_display = selected_detail
                
                # 重投信息处理（从幸运骰详情中提取）
                reroll_info = ""
                if critical_success_count > 0 or critical_failure_count > 0:
                    reroll_parts = []
                    if critical_success_count > 0:
                        reroll_parts.append(f"大成功×{critical_success_count}")
                    if critical_failure_count > 0:
                        reroll_parts.append(f"大失败×{critical_failure_count}")
                    reroll_info = f"重投结果: {', '.join(reroll_parts)}\n"

                # 获取难度等级文本
                total_difficulty_level = get_difficulty_level(total_result)
                back_difficulty_level = get_difficulty_level(back_value)
                
                # 设置显示值
                dictTValue['tFrontResult'] = front_process
                dictTValue['tLuckDiceResult'] = luck_display
                dictTValue['tTotalResult'] = f"{total_result}[{total_difficulty_level}]"
                dictTValue['tBackResult'] = f"{back_process}[{back_difficulty_level}]"
                dictTValue['tSuccessLevelInt'] = str(final_success_level)
                dictTValue['tSuccessLevelProcess'] = success_level_process
                dictTValue['tRerollInfo'] = reroll_info
                
                # 判断技能检定类型
                tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
                
                # 处理大成功/大失败
                if critical_type == 'critical_success':
                    tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
                elif critical_type == 'critical_failure':
                    tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_FAIL
                else:
                    # 正常检定结果
                    if final_success_level >= 0:
                        tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS
                    else:
                        tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
                
                # 获取技能检定结果文案
                dictTValue['tSkillCheckReasult'] = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(tmpSkillCheckType, dictStrCustom, dictTValue, tmp_pcHash, tmp_pc_name)
                
                # 更新人物卡的幸运值和升级点（只有在有变化时才更新）
                if luck_change != 0 or upgrade_points_change != 0:
                    update_pc_luck_and_skill(plugin_event, tmp_userID, tmp_hagID, luck_change, upgrade_points_change)
                
                # 根据是否自动确定结果选择不同的回复模板
                if not need_manual_selection and (critical_type == 'critical_success' or critical_type == 'critical_failure'):
                    # 直接大成功/大失败，使用简化模板，显示所有骰子详情
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsCriticalResult'], dictTValue)
                else:
                    # 正常检定或手动选择后的结果，使用完整模板
                    dictTValue['tSuccessLevel'] = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsSuccessLevel'], dictTValue)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsResult'], dictTValue)

                _save_rd_record_detail(
                    raw='喵影奇谋检定',
                    detail=tmp_reply_str.strip() + '\n\n（无视后面的"="和数值）',
                    value=0,
                )
                
                replyMsg(plugin_event, tmp_reply_str)
                
            except Exception as e:
                dictTValue['tResult'] = str(e)
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCatsError'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
            
            return
