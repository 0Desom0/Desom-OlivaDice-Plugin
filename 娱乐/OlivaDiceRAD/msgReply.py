# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore，写命令请跳转到第183行。
'''

import OlivOS
import OlivaDiceRAD
import OlivaDiceCore

import copy


def unity_init(plugin_event, Proc):
    # 这里是插件初始化，通常用于加载配置等
    pass

def data_init(plugin_event, Proc):
    pass

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
        if isMatchWordStart(tmp_reast_str, ['rad','rcd'], isCommand = True):
            is_at, at_user_id, tmp_reast_str = parse_at_user(plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin)
            if is_at:
                if not at_user_id:
                    return
                dictTValue['tName'] = dictTValue['tUserName01']
            tmp_pc_id = at_user_id if at_user_id else plugin_event.data.user_id
            tmp_pc_platform = plugin_event.platform['platform']
            tmp_reply_str = ''
            tmp_reply_str_show = ''
            roll_times_count = 1
            flag_check_success = False
            flag_groupTemplate = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId = tmp_hagID,
                userType = 'group',
                platform = plugin_event.platform['platform'],
                userConfigKey = 'groupTemplate',
                botHash = plugin_event.bot_info.hash
            )
            flag_groupTemplateRule = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId = tmp_hagID,
                userType = 'group',
                platform = plugin_event.platform['platform'],
                userConfigKey = 'groupTemplateRule',
                botHash = plugin_event.bot_info.hash
            )
            if isMatchWordStart(tmp_reast_str, ['rad','rcd']):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['rad','rcd'])
            else:
                return
            flag_hide_roll = False
            if len(tmp_reast_str) > 0:
                if isMatchWordStart(tmp_reast_str, 'h'):
                    flag_hide_roll = True
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'h')
            if len(tmp_reast_str) > 2:
                tmp_reast_str_list_1 = tmp_reast_str.split('#')
                if len(tmp_reast_str_list_1) > 1:
                    if tmp_reast_str_list_1[0].isdecimal():
                        roll_times_count = int(tmp_reast_str_list_1[0])
                        if roll_times_count > 10:
                            roll_times_count = 10
                        tmp_reast_str = tmp_reast_str_list_1[1]
            # 处理奖励/惩罚骰（b/p）
            flag_bp_type = 0  # 0无 1奖励 2惩罚
            flag_bp_count = None
            if len(tmp_reast_str) > 0:
                if isMatchWordStart(tmp_reast_str, ['b','B']):
                    flag_bp_type = 1
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['b','B'])
                elif isMatchWordStart(tmp_reast_str, ['p','P']):
                    flag_bp_type = 2
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['p','P'])
                if flag_bp_type != 0 and len(tmp_reast_str) > 1:
                    if tmp_reast_str[0].isdecimal():
                        flag_bp_count = tmp_reast_str[0]
                        tmp_reast_str = tmp_reast_str[1:]
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            # 检查是否裸rad(无参数),允许通过,会使用随机值
            # if tmp_reast_str == '' or tmp_reast_str == None:
            #     if is_at:
            #         tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckNoneAtOther'], dictTValue)
            #     else:
            #         tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckNone'], dictTValue)
            #     OlivaDiceCore.msgReply.replyMsg(plugin_event, tmp_reply_str)
            #     return
            tmp_skill_name = None
            tmp_skill_value = None
            difficulty = None
            # 解析难度前缀（困难/极难/大成功）
            difficulty, tmp_reast_str = difficulty_analyze(tmp_reast_str)
            tmp_skill_value_str = None
            # 保存表达式信息，用于多次掷骰时重新计算
            tmp_expr_info = None
            # 标记是否强制指定了技能值（直接输入数字）
            flag_force_value = False
            if tmp_reast_str:
                op_list = op_list_get()
                # 检查是否直接以运算符开头 (如 +10, -5, *2等)
                if tmp_reast_str[0] in op_list:
                    # 直接是表达式，没有技能名
                    tmp_skill_name = None
                    expr_end = 0
                    in_dice = False
                    for i, char in enumerate(tmp_reast_str):
                        if char.isspace():
                            expr_end = i
                            break
                        if char.upper() == 'D':
                            in_dice = True
                        if not (char.isdigit() or char in op_list or char.upper() == 'D'):
                            if not in_dice:
                                expr_end = i
                                break
                    expr_str = tmp_reast_str[:expr_end] if expr_end > 0 else tmp_reast_str
                    tmp_reast_str = tmp_reast_str[len(expr_str):].strip()
                    
                    # 检查是否强制指定了基础值
                    base_value = None
                    if tmp_reast_str and tmp_reast_str[0].isdigit():
                        [base_value, tmp_reast_str] = OlivaDiceCore.msgReply.getNumberPara(tmp_reast_str)
                        base_value = int(base_value)
                        flag_force_value = True
                    
                    # 保存表达式信息
                    has_dice = "D" in expr_str.upper()
                    tmp_expr_info = {
                        'base_value': base_value,
                        'expr_str': expr_str,
                        'has_dice': has_dice,
                        'force_value': flag_force_value
                    }
                    
                    # 只有强制指定了base_value才在这里计算
                    if flag_force_value:
                        full_expr = f"{base_value}{expr_str}"
                        rd_para = OlivaDiceCore.onedice.RD(full_expr)
                        rd_para.roll()
                        if rd_para.resError is None:
                            tmp_skill_value = rd_para.resInt
                            if has_dice:
                                tmp_skill_value_str = f"{full_expr}={rd_para.resDetail}={tmp_skill_value}"
                            else:
                                tmp_skill_value_str = f"{full_expr}={tmp_skill_value}"
                else:
                    # 不是以运算符开头，可能有技能名
                    skill_end_pos = len(tmp_reast_str)
                    for i, char in enumerate(tmp_reast_str):
                        if char in op_list or char.isdigit():
                            skill_end_pos = i
                            break
                    tmp_skill_name = tmp_reast_str[:skill_end_pos].strip().upper() or None
                    tmp_reast_str = tmp_reast_str[skill_end_pos:].strip()
                    tmp_skill_name = tmp_reast_str[:skill_end_pos].strip().upper() or None
                    tmp_reast_str = tmp_reast_str[skill_end_pos:].strip()
                    
                    if not tmp_reast_str:
                        # 只有技能名，不读取技能卡值，使用随机值
                        tmp_skill_name = tmp_skill_name.split()[0] if tmp_skill_name else None
                        if tmp_skill_name:
                            tmp_skill_name = OlivaDiceCore.pcCard.fixName(tmp_skill_name, flagMode = 'skillName')
                        tmp_skill_value = None
                        tmp_skill_value_str = None
                    else:
                        if tmp_skill_name:
                            tmp_skill_name = OlivaDiceCore.pcCard.fixName(tmp_skill_name, flagMode = 'skillName')
                        # 检查是否有运算符
                        if tmp_reast_str[0] in op_list:
                            # 带运算表达式，不读取技能卡值
                            expr_end = 0
                            in_dice = False
                            for i, char in enumerate(tmp_reast_str):
                                if char.isspace():
                                    expr_end = i
                                    break
                                if char.upper() == 'D':
                                    in_dice = True
                                if not (char.isdigit() or char in op_list or char.upper() == 'D'):
                                    if not in_dice:
                                        expr_end = i
                                        break
                            expr_str = tmp_reast_str[:expr_end] if expr_end > 0 else tmp_reast_str
                            tmp_reast_str = tmp_reast_str[len(expr_str):].strip()
                            base_value = None
                            # 检查是否强制指定了基础值
                            if tmp_reast_str and tmp_reast_str[0].isdigit():
                                [base_value, tmp_reast_str] = OlivaDiceCore.msgReply.getNumberPara(tmp_reast_str)
                                base_value = int(base_value)
                                flag_force_value = True  # 强制指定了基础值
                            # 如果没有强制指定基础值，base_value保持为None，后续会使用随机值
                            
                            if base_value is not None or not flag_force_value:
                                # 保存表达式信息供多次掷骰使用
                                has_dice = "D" in expr_str.upper()
                                tmp_expr_info = {
                                    'base_value': base_value,  # 如果是None，多次掷骰时会每次重新随机
                                    'expr_str': expr_str,
                                    'has_dice': has_dice,
                                    'force_value': flag_force_value
                                }
                                # 只有强制指定了base_value才在这里计算
                                if flag_force_value:
                                    full_expr = f"{base_value}{expr_str}"
                                    rd_para = OlivaDiceCore.onedice.RD(full_expr)
                                    rd_para.roll()
                                    if rd_para.resError is None:
                                        tmp_skill_value = rd_para.resInt
                                        if has_dice:
                                            tmp_skill_value_str = (
                                                f"{full_expr}={rd_para.resDetail}={tmp_skill_value}"
                                            )
                                        else:
                                            tmp_skill_value_str = (
                                                f"{full_expr}={tmp_skill_value}"
                                            )
                        else:
                            # 指定数值
                            if tmp_reast_str[0].isdigit():
                                [tmp_skill_value, tmp_reast_str] = OlivaDiceCore.msgReply.getNumberPara(tmp_reast_str)
                                tmp_skill_value = int(tmp_skill_value)
                                tmp_skill_value_str = str(tmp_skill_value)
                                flag_force_value = True  # 强制指定了技能值
            # 删除从技能卡读取的逻辑，除非强制指定了值，否则都使用随机值
            # if tmp_skill_name and tmp_skill_value is None:
            #     tmp_skill_value = OlivaDiceCore.pcCard.pcCardDataGetBySkillName(...)
            tmp_pc_name_1 = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(
                OlivaDiceCore.pcCard.getPcHash(tmp_pc_id, tmp_pc_platform),
                tmp_hagID
            )
            if tmp_pc_name_1:
                dictTValue['tName'] = tmp_pc_name_1
            # 允许裸rad命令(tmp_skill_name和tmp_skill_value都为None时也能执行)
            # if tmp_skill_name != None or tmp_skill_value != None:
            if True:  # 总是执行掷骰逻辑
                tmp_Template = None
                tmp_TemplateRuleName = 'default'
                if tmp_pc_name_1 != None:
                    tmp_template_name = OlivaDiceCore.pcCard.pcCardDataGetTemplateKey(
                        OlivaDiceCore.pcCard.getPcHash(
                            tmp_pc_id,
                            tmp_pc_platform
                        ),
                        tmp_pc_name_1
                    )
                    if flag_groupTemplate != None:
                        tmp_template_name = flag_groupTemplate
                    if tmp_template_name != None:
                        tmp_Template = OlivaDiceCore.pcCard.pcCardDataGetTemplateByKey(tmp_template_name)
                    tmp_template_rule_name = OlivaDiceCore.pcCard.pcCardDataGetTemplateRuleKey(
                        OlivaDiceCore.pcCard.getPcHash(
                            tmp_pc_id,
                            tmp_pc_platform
                        ),
                        tmp_pc_name_1
                    )
                    if flag_groupTemplateRule != None:
                        tmp_template_rule_name = flag_groupTemplateRule
                    if tmp_template_rule_name != None:
                        tmp_TemplateRuleName = tmp_template_rule_name
                rd_para_str = '1D100'
                tmp_customDefault = None
                if tmp_Template != None:
                    if 'mainDice' in tmp_Template:
                        rd_para_str = tmp_Template['mainDice']
                    if 'customDefault' in tmp_Template:
                        tmp_customDefault = tmp_Template['customDefault']
                if flag_bp_type == 1:
                    rd_para_str = 'B'
                elif flag_bp_type == 2:
                    rd_para_str = 'P'
                if flag_bp_count != None:
                    rd_para_str += flag_bp_count
                flag_need_reply = False
                if roll_times_count == 1:
                    # 单次掷骰
                    # 如果有表达式且没有强制指定值，先随机基础值
                    current_skill_value = tmp_skill_value
                    # 标记是否为纯随机(没有任何表达式和指定值)
                    flag_pure_random = False
                    
                    if tmp_expr_info is not None and not tmp_expr_info['force_value']:
                        # 没有强制指定值，使用随机值
                        rd_para_base = OlivaDiceCore.onedice.RD('1D100')
                        rd_para_base.roll()
                        if rd_para_base.resError is None:
                            base_value = rd_para_base.resInt
                            full_expr = f"{base_value}{tmp_expr_info['expr_str']}"
                            rd_para_expr = OlivaDiceCore.onedice.RD(full_expr)
                            rd_para_expr.roll()
                            if rd_para_expr.resError is None:
                                current_skill_value = rd_para_expr.resInt
                                # 显示为 1D100+表达式=结果，不显示中间过程
                                tmp_skill_value_str = f"1D100{tmp_expr_info['expr_str']}={current_skill_value}"
                    elif tmp_skill_value is None:
                        # 没有指定值也没有表达式，使用随机值
                        flag_pure_random = True
                        rd_para_base = OlivaDiceCore.onedice.RD('1D100')
                        rd_para_base.roll()
                        if rd_para_base.resError is None:
                            current_skill_value = rd_para_base.resInt
                            tmp_skill_value_str = '1D100'  # 显示为1D100而不是具体数字
                    
                    rd_para = OlivaDiceCore.onedice.RD(rd_para_str, tmp_customDefault)
                    rd_para.roll()
                    if rd_para.resError == None:
                        if rd_para.resDetail == None or rd_para.resDetail == '':
                            dictTValue['tRollResult'] = '%s=%d' % (rd_para_str, rd_para.resInt)
                        else:
                            dictTValue['tRollResult'] = '%s=%s=%d' % (rd_para_str, rd_para.resDetail, rd_para.resInt)
                        dictRuleTempData = {
                            'roll': rd_para.resInt,
                            'skill': current_skill_value
                        }
                        OlivaDiceCore.onediceOverride.saveRDDataUser(
                            data = rd_para,
                            botHash = plugin_event.bot_info.hash,
                            userId = tmp_pc_id,
                            platform = tmp_pc_platform,
                            skillValue = current_skill_value
                        )
                        tmpSkillCheckType, tmpSkillThreshold = OlivaDiceCore.skillCheck.getSkillCheckByTemplate(
                            dictRuleTempData,
                            tmp_Template,
                            tmp_TemplateRuleName,
                            difficulty_prefix=difficulty
                        )
                        # 单次掷骰时显示技能值
                        skill_display = None
                        if tmp_expr_info is not None and not tmp_expr_info['force_value']:
                            # 如果有表达式但没有强制指定，显示完整计算过程
                            skill_display = tmp_skill_value_str
                        elif tmp_expr_info is not None:
                            # 如果有表达式且强制指定了值
                            skill_display = f"{tmp_expr_info['base_value']}{tmp_expr_info['expr_str']}={tmp_skill_value}"
                        else:
                            # 纯随机或强制指定值
                            if flag_pure_random:
                                # 纯随机显示1D100
                                skill_display = '1D100' if not difficulty else f'{tmpSkillThreshold}(1D100)'
                            else:
                                # 强制指定值
                                skill_display = tmp_skill_value_str if not difficulty else f'{tmpSkillThreshold}({tmp_skill_value_str})'
                        
                        # 如果有技能名,加上前缀
                        if tmp_skill_name:
                            dictTValue['tSkillValue'] = f"{tmp_skill_name}:{skill_display}"
                        else:
                            dictTValue['tSkillValue'] = skill_display
                        
                        if tmpSkillThreshold == None:
                            if tmp_expr_info is not None and not tmp_expr_info['force_value']:
                                skill_display = tmp_skill_value_str
                            elif tmp_expr_info is not None:
                                skill_display = f"{tmp_expr_info['base_value']}{tmp_expr_info['expr_str']}={tmp_skill_value}"
                            else:
                                skill_display = '1D100' if flag_pure_random else tmp_skill_value_str
                            
                            # 如果有技能名,加上前缀
                            if tmp_skill_name:
                                dictTValue['tSkillValue'] = f"{tmp_skill_name}:{skill_display}"
                            else:
                                dictTValue['tSkillValue'] = skill_display
                            tmpSkillThreshold = current_skill_value
                        # 如果是纯随机,直接显示 掷骰结果/技能值,不显示1D100=
                        if flag_pure_random:
                            dictTValue['tRollResult'] = '%s/%s' % (dictTValue['tRollResult'], tmpSkillThreshold)
                        else:
                            dictTValue['tRollResult'] = '%s/%s' % (dictTValue['tRollResult'], tmpSkillThreshold)
                        dictTValue['tSkillCheckReasult'] = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
                            tmpSkillCheckType, dictStrCustom, dictTValue,
                            pcHash=OlivaDiceCore.pcCard.getPcHash(tmp_pc_id, tmp_pc_platform),
                            pcCardName=tmp_pc_name_1,
                            user_id=tmp_pc_id, skill_name=tmp_skill_name,
                            platform=tmp_pc_platform, botHash=plugin_event.bot_info.hash, hagId=tmp_hagID
                        )
                        if tmpSkillCheckType in [
                            OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS,
                            OlivaDiceCore.skillCheck.resultType.SKILLCHECK_HARD_SUCCESS,
                            OlivaDiceCore.skillCheck.resultType.SKILLCHECK_EXTREME_HARD_SUCCESS,
                            OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
                        ]:
                            flag_check_success = True
                        flag_need_reply = True
                else:
                    flag_begin = True
                    tmp_tSkillCheckReasult = ''
                    # 多次掷骰时，tSkillValue显示表达式模板（不显示具体数值）
                    skill_display = None
                    if tmp_expr_info is not None:
                        if tmp_expr_info['force_value']:
                            # 强制指定了值，显示固定的表达式
                            skill_display = f"{tmp_expr_info['base_value']}{tmp_expr_info['expr_str']}"
                        else:
                            # 没有强制指定，显示随机表达式模板
                            skill_display = f"1D100{tmp_expr_info['expr_str']}"
                    elif tmp_skill_value is not None:
                        # 强制指定了固定值
                        skill_display = tmp_skill_value_str
                    else:
                        # 完全随机
                        skill_display = '1D100'
                    
                    # 如果有技能名,加上前缀
                    if tmp_skill_name:
                        dictTValue['tSkillValue'] = f"{tmp_skill_name}:{skill_display}"
                    else:
                        dictTValue['tSkillValue'] = skill_display
                    
                    for i in range(roll_times_count):
                        # 每次重新计算技能值
                        current_skill_value = tmp_skill_value
                        current_skill_display = None
                        
                        if tmp_expr_info is not None:
                            if tmp_expr_info['force_value']:
                                # 强制指定了基础值，每次使用相同的值计算
                                full_expr = f"{tmp_expr_info['base_value']}{tmp_expr_info['expr_str']}"
                                rd_para_expr = OlivaDiceCore.onedice.RD(full_expr)
                                rd_para_expr.roll()
                                if rd_para_expr.resError is None:
                                    current_skill_value = rd_para_expr.resInt
                                    current_skill_display = f"{tmp_expr_info['base_value']}{tmp_expr_info['expr_str']}"
                            else:
                                # 没有强制指定，每次随机基础值
                                rd_para_base = OlivaDiceCore.onedice.RD('1D100')
                                rd_para_base.roll()
                                if rd_para_base.resError is None:
                                    base_value = rd_para_base.resInt
                                    full_expr = f"{base_value}{tmp_expr_info['expr_str']}"
                                    rd_para_expr = OlivaDiceCore.onedice.RD(full_expr)
                                    rd_para_expr.roll()
                                    if rd_para_expr.resError is None:
                                        current_skill_value = rd_para_expr.resInt
                                        current_skill_display = full_expr
                        elif tmp_skill_value is None:
                            # 没有指定值也没有表达式，每次随机
                            rd_para_base = OlivaDiceCore.onedice.RD('1D100')
                            rd_para_base.roll()
                            if rd_para_base.resError is None:
                                current_skill_value = rd_para_base.resInt
                                current_skill_display = None  # 纯随机不显示计算过程
                        else:
                            # 强制指定了固定值
                            current_skill_display = str(current_skill_value)
                        
                        rd_para = OlivaDiceCore.onedice.RD(rd_para_str)
                        rd_para.roll()
                        if rd_para.resError == None:
                            # 构建掷骰结果显示
                            if flag_bp_type == 0:
                                tmp_tSkillCheckReasult += '%s=%d' % (rd_para_str, rd_para.resInt)
                            else:
                                tmp_tSkillCheckReasult += '%s=%s=%d' % (rd_para_str, rd_para.resDetail, rd_para.resInt)
                            
                            dictRuleTempData = {
                                'roll': rd_para.resInt,
                                'skill': current_skill_value
                            }
                            tmpSkillCheckType, tmpSkillThreshold = OlivaDiceCore.skillCheck.getSkillCheckByTemplate(
                                dictRuleTempData,
                                tmp_Template,
                                tmp_TemplateRuleName,
                                difficulty_prefix=difficulty
                            )
                            if tmpSkillThreshold == None:
                                tmpSkillThreshold = current_skill_value
                            # 在 /后面显示每次的技能值计算过程
                            # 如果是纯随机(current_skill_display为None)，直接显示数字不显示=
                            if current_skill_display:
                                tmp_tSkillCheckReasult += '/%s=%d ' % (current_skill_display, tmpSkillThreshold)
                            else:
                                tmp_tSkillCheckReasult += '/%s ' % tmpSkillThreshold
                            tmp_tSkillCheckReasult += OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
                                tmpSkillCheckType, dictStrCustom, dictTValue,
                                pcHash = OlivaDiceCore.pcCard.getPcHash(tmp_pc_id, tmp_pc_platform),
                                pcCardName = tmp_pc_name_1,
                                user_id=tmp_pc_id, skill_name=tmp_skill_name,
                                platform=tmp_pc_platform, botHash=plugin_event.bot_info.hash, hagId=tmp_hagID
                            )
                            if tmpSkillCheckType in [
                                OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS,
                                OlivaDiceCore.skillCheck.resultType.SKILLCHECK_HARD_SUCCESS,
                                OlivaDiceCore.skillCheck.resultType.SKILLCHECK_EXTREME_HARD_SUCCESS,
                                OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
                            ]:
                                flag_check_success = True
                            flag_need_reply = True
                            tmp_tSkillCheckReasult += '\n'
                        else:
                            flag_need_reply = False
                            break
                    dictTValue['tRollResult'] = tmp_tSkillCheckReasult.strip()
                    dictTValue['tSkillCheckReasult'] = ''
                if flag_check_success:
                    if tmp_pc_name_1 != None and tmp_skill_name != None:
                        tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(
                            tmp_pc_id,
                            tmp_pc_platform
                        )
                        tmp_enhanceList = OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                            tmp_pcHash,
                            tmp_pc_name_1,
                            'enhanceList',
                            []
                        )
                        tmp_template_name = OlivaDiceCore.pcCard.pcCardDataGetTemplateDataByKey(
                            tmp_pcHash,
                            tmp_pc_name_1,
                            'template',
                            'default'
                        )
                        tmp_skill_name_core = OlivaDiceCore.pcCard.pcCardDataSkillNameMapper(
                            tmp_pcHash,
                            tmp_skill_name,
                            hagId = tmp_hagID
                        )
                        tmp_skipEnhance_list = []
                        tmp_template = OlivaDiceCore.pcCard.pcCardDataGetTemplateByKey(tmp_template_name)
                        if 'skillConfig' in tmp_template:
                            if 'skipEnhance' in tmp_template['skillConfig']:
                                if type(tmp_template['skillConfig']['skipEnhance']):
                                    tmp_skipEnhance_list = tmp_template['skillConfig']['skipEnhance']
                        if flag_bp_type != 1:
                            if tmp_skill_name_core not in tmp_enhanceList and tmp_skill_name_core not in tmp_skipEnhance_list:
                                tmp_enhanceList.append(tmp_skill_name_core)
                        OlivaDiceCore.pcCard.pcCardDataSetTemplateDataByKey(
                            tmp_pcHash,
                            tmp_pc_name_1,
                            'enhanceList',
                            tmp_enhanceList
                        )
                if flag_need_reply:
                    if is_at:
                        if tmp_skill_name:
                            dictTValue['tSkillName'] = tmp_skill_name if not difficulty else f'{tmp_skill_name}({difficulty})'
                            if tmpSkillThreshold == None: dictTValue['tSkillName'] = tmp_skill_name
                            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckWithSkillNameAtOther'], dictTValue)
                            tmp_reply_str_show = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckHideShowWithSkillNameAtOther'], dictTValue)
                            if flag_hide_roll and flag_is_from_group:
                                dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckHideWithSkillNameAtOther'], dictTValue)
                        else:
                            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckAtOther'], dictTValue)
                            tmp_reply_str_show = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckHideShowAtOther'], dictTValue)
                            if flag_hide_roll and flag_is_from_group:
                                dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckHideAtOther'], dictTValue)
                        if flag_hide_roll and flag_is_from_group:
                            replyMsg(plugin_event, tmp_reply_str_show)
                            OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str)
                        else:
                            replyMsg(plugin_event, tmp_reply_str)
                    else:
                        if tmp_skill_name:
                            dictTValue['tSkillName'] = tmp_skill_name if not difficulty else f'{tmp_skill_name}({difficulty})'
                            if tmpSkillThreshold == None: dictTValue['tSkillName'] = tmp_skill_name
                            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckWithSkillName'], dictTValue)
                            tmp_reply_str_show = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckHideShowWithSkillName'], dictTValue)
                            if flag_hide_roll and flag_is_from_group:
                                dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckHideWithSkillName'], dictTValue)
                        else:
                            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheck'], dictTValue)
                            tmp_reply_str_show = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckHideShow'], dictTValue)
                            if flag_hide_roll and flag_is_from_group:
                                dictTValue['tGroupId'] = str(plugin_event.data.group_id)
                                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcSkillCheckHide'], dictTValue)
                        if flag_hide_roll and flag_is_from_group:
                            replyMsg(plugin_event, tmp_reply_str_show)
                            OlivaDiceCore.msgReply.replyMsgPrivateByEvent(plugin_event, tmp_reply_str)
                        else:
                            replyMsg(plugin_event, tmp_reply_str)
            # 阻止后续插件处理,避免与原有的 .ra 命令冲突
            plugin_event.set_block()

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
        if not (flag_is_from_group_admin or flag_is_from_master):
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strAtOtherPermissionDenied'], 
                dictTValue
            )
            OlivaDiceCore.msgReply.replyMsg(plugin_event, tmp_reply_str)
            return (True, None, None)  # 权限不足
    
    # 返回解析结果
    cleaned_message = ''.join(new_tmp_reast_str_parts).strip()
    return is_at, at_user_id, cleaned_message

def difficulty_analyze(res):
    difficulty = None
    if OlivaDiceCore.msgReply.isMatchWordStart(res, ['困难成功', '困难']):
        difficulty = '困难'
        res = OlivaDiceCore.msgReply.getMatchWordStartRight(res, ['困难成功', '困难']).strip()
    elif OlivaDiceCore.msgReply.isMatchWordStart(res, ['极难成功', '极限成功', '极难', '极限']):
        difficulty = '极难'
        res = OlivaDiceCore.msgReply.getMatchWordStartRight(res, ['极难成功', '极限成功', '极难', '极限']).strip()
    elif OlivaDiceCore.msgReply.isMatchWordStart(res, '大成功'):
        difficulty = '大成功'
        res = OlivaDiceCore.msgReply.getMatchWordStartRight(res, '大成功').strip()
    res = res.strip()
    return difficulty, res

def op_list_get():
    return ['+', '-', '*', '/', '^']
