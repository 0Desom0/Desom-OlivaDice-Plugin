# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore，写命令请跳转到第183行。
'''

import OlivOS
import OlivaDiceDH
import OlivaDiceCore

import copy
import re
import os
import json

def unity_init(plugin_event, Proc):
    # 这里是插件初始化，通常用于加载配置等
    pass

def data_init(plugin_event, Proc):
    # 这里是数据初始化，通常用于加载数据等
    OlivaDiceDH.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

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
        
        '''到这里为止，前面的都不动，后面进行你写的命令处理'''
        
        # .dd/ddr 命令 - 二元骰检定/反应二元骰检定
        if isMatchWordStart(tmp_reast_str, ['dd'], isCommand = True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['dd'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            is_reaction = False
            if isMatchWordStart(tmp_reast_str, ['r'], isCommand = True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['r'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                is_reaction = True
            tmp_reply_str = processDDCommand(
                plugin_event, Proc, tmp_reast_str, dictTValue, dictStrCustom,
                tmp_hagID, flag_is_from_group, is_reaction=is_reaction
            )
            if tmp_reply_str != None:
                replyMsg(plugin_event, tmp_reply_str)
            return
        
        # .gm 命令 - GM管理
        elif isMatchWordStart(tmp_reast_str, ['gm'], isCommand = True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['gm'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reply_str = processGMCommand(
                plugin_event, Proc, tmp_reast_str, dictTValue, dictStrCustom,
                tmp_hagID, flag_is_from_group
            )
            if tmp_reply_str != None:
                replyMsg(plugin_event, tmp_reply_str)
            return
        
        # .cook 命令 - 烹饪游戏
        if isMatchWordStart(tmp_reast_str, ['cook'], isCommand = True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['cook'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reply_str = processCookCommand(
                plugin_event, Proc, tmp_reast_str, dictTValue, dictStrCustom,
                tmp_hagID, flag_is_from_group
            )
            if tmp_reply_str != None:
                replyMsg(plugin_event, tmp_reply_str)
            return


# ==================== 辅助函数 ====================

def getGroupHash(plugin_event):
    """获取群组的标准hash值"""
    if hasattr(plugin_event.data, 'host_id') and plugin_event.data.host_id is not None:
        # 有子频道的情况
        return OlivaDiceCore.userConfig.getUserHash(
            userId=plugin_event.data.group_id,
            userType='group',
            platform=plugin_event.platform['platform'],
            subId=plugin_event.data.host_id
        )
    else:
        # 纯群组的情况
        return OlivaDiceCore.userConfig.getUserHash(
            userId=plugin_event.data.group_id,
            userType='group',
            platform=plugin_event.platform['platform']
        )

def getDataPath(bot_hash, data_type, group_hash=None):
    """获取数据文件路径"""
    base_path = f'plugin/data/OlivaDiceDH/{bot_hash}'
    if data_type == 'gm':
        path = f'{base_path}/GameMaster'
        if group_hash:
            return f'{path}/{group_hash}.json'
        return path
    elif data_type == 'cook':
        path = f'{base_path}/Cook'
        if group_hash:
            return f'{path}/{group_hash}.json'
        return path
    return base_path

def loadData(file_path):
    """加载JSON数据"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def saveData(file_path, data):
    """保存JSON数据"""
    try:
        dir_path = os.path.dirname(file_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except:
        return False

def createDefaultPcCard(user_id, platform, user_name, tmp_hagID=None):
    """创建默认的匕首之心人物卡"""
    try:
        # 获取pcHash
        tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(user_id, platform)
        
        # 创建人物卡名称
        pc_name = f"{user_name}"
        
        # 设置希望上限（这会自动创建人物卡）
        OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
            pcHash=tmp_pcHash,
            skillName='希望上限',
            skillValue=6,
            pcCardName=pc_name,
            hagId=tmp_hagID
        )
        
        # 设置模板
        OlivaDiceCore.pcCard.pcCardDataSetTemplateKey(
            tmp_pcHash,
            pc_name,
            'dh'
        )
        
        # 切换到新建的人物卡
        OlivaDiceCore.pcCard.pcCardDataSetSelectionKeyLock(
            tmp_pcHash,
            pc_name,
            tmp_hagID
        )
        
        return pc_name
    except:
        return None

def getPcCardData(plugin_event, user_id=None, platform=None):
    """获取人物卡数据，使用OlivaDiceCore标准函数。如果没有人物卡则自动创建"""
    if user_id is None:
        user_id = plugin_event.data.user_id
    if platform is None:
        platform = plugin_event.platform['platform']
    
    # 使用OlivaDiceCore标准函数获取pcHash
    tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(
        user_id,
        platform
    )
    
    tmp_hagID = None
    if hasattr(plugin_event.data, 'host_id') and plugin_event.data.host_id is not None:
        if hasattr(plugin_event.data, 'group_id') and plugin_event.data.group_id is not None:
            tmp_hagID = f"{plugin_event.data.host_id}|{plugin_event.data.group_id}"
    elif hasattr(plugin_event.data, 'group_id') and plugin_event.data.group_id is not None:
        tmp_hagID = str(plugin_event.data.group_id)
    
    # 使用OlivaDiceCore标准函数获取当前选择的人物卡名称
    tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(
        tmp_pcHash,
        tmp_hagID
    )
    
    # 如果没有人物卡，自动创建一个
    if tmp_pc_name is None:
        user_name = plugin_event.data.sender['name'] if hasattr(plugin_event.data, 'sender') else str(user_id)
        tmp_pc_name = createDefaultPcCard(user_id, platform, user_name, tmp_hagID)
        
        if tmp_pc_name is None:
            return None, None, None, tmp_hagID
    
    # 使用OlivaDiceCore标准函数获取人物卡数据
    tmp_pc_data = OlivaDiceCore.pcCard.pcCardDataGetByPcName(
        tmp_pcHash,
        tmp_pc_name
    )
    
    return tmp_pc_data, tmp_pcHash, tmp_pc_name, tmp_hagID

def isTemplateSkill(tmp_pc_id, skill_name, tmp_hagID):
    """检查技能是否在人物卡模板的skill列表中"""
    try:
        # 获取人物卡模板
        tmp_pc_data = OlivaDiceCore.pcCard.pcCardDataGetByPcName(tmp_pc_id, None)
        if not tmp_pc_data:
            return False
        
        # 获取模板名称
        template_name = None
        if 'template' in tmp_pc_data:
            template_name = tmp_pc_data['template']
        
        if not template_name:
            template_name = 'dh'  # 默认使用dh模板
        
        # 获取模板数据
        template = OlivaDiceCore.pcCard.pcCardDataGetTemplateByKey(template_name)
        if not template or 'skill' not in template:
            return False
        
        # 检查技能是否在模板的skill列表中
        skill_dict = template['skill']
        for category, skills in skill_dict.items():
            if skill_name in skills:
                return True
        
        return False
    except:
        return False

def getSkillValue(tmp_pc_id, skill_name, tmp_hagID=None):
    """使用OlivaDiceCore标准函数从人物卡获取技能值"""
    try:
        # 直接使用OlivaDiceCore.pcCard.pcCardDataGetBySkillName
        skill_value = OlivaDiceCore.pcCard.pcCardDataGetBySkillName(
            pcHash=tmp_pc_id,
            skillName=skill_name,
            hagId=tmp_hagID
        )
        return skill_value
    except:
        return None

def setSkillValue(tmp_pc_id, skill_name, skill_value, tmp_pc_name=None, tmp_hagID=None):
    """使用OlivaDiceCore标准函数设置人物卡技能值"""
    try:
        # 如果没有提供人物卡名称，获取当前选择的人物卡
        if tmp_pc_name is None:
            tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(
                pcHash=tmp_pc_id,
                hagId=tmp_hagID
            )
            if tmp_pc_name is None:
                return False
        
        # 使用OlivaDiceCore.pcCard.pcCardDataSetBySkillName
        OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
            pcHash=tmp_pc_id,
            skillName=skill_name,
            skillValue=skill_value,
            pcCardName=tmp_pc_name,
            hagId=tmp_hagID
        )
        return True
    except:
        return False


# ==================== .dd / .ddr 命令处理 ====================

def processDDCommand(plugin_event, Proc, command_str, dictTValue, dictStrCustom, tmp_hagID, flag_is_from_group, is_reaction=False):
    """处理二元骰检定命令"""
    try:
        # 获取用户ID和平台信息
        user_id = plugin_event.data.user_id
        tmp_pc_platform = plugin_event.platform['platform']
        
        # 获取人物卡数据（如果没有会自动创建）
        pc_data, tmp_pc_id, tmp_pc_name, tmp_hagID = getPcCardData(plugin_event)
        if pc_data is None or tmp_pc_id is None or tmp_pc_name is None:
            dictTValue['tResult'] = '无法创建或获取人物卡'
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strDDError'], dictTValue)
        
        dictTValue['tName'] = tmp_pc_name
        
        # 解析命令
        result = parseDDCommand(command_str, tmp_pc_id, tmp_hagID, plugin_event, Proc, dictTValue)
        if 'error' in result:
            dictTValue['tResult'] = result['error']
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strDDError'], dictTValue)
        
        # 投掷希望骰和恐惧骰
        hope_dice_faces = result.get('hope_dice_faces', 12)
        fear_dice_faces = result.get('fear_dice_faces', 12)
        
        hope_rd = OlivaDiceCore.onedice.RD(f'1d{hope_dice_faces}')
        hope_rd.roll()
        if hope_rd.resError is not None:
            dictTValue['tResult'] = f'希望骰投掷失败: {hope_rd.resError}'
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strDDError'], dictTValue)
        
        fear_rd = OlivaDiceCore.onedice.RD(f'1d{fear_dice_faces}')
        fear_rd.roll()
        if fear_rd.resError is not None:
            dictTValue['tResult'] = f'恐惧骰投掷失败: {fear_rd.resError}'
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strDDError'], dictTValue)
        
        hope_roll = hope_rd.resInt
        fear_roll = fear_rd.resInt
        
        dictTValue['tHopeDice'] = str(hope_roll)
        dictTValue['tFearDice'] = str(fear_roll)
        
        # 获取当前希望值
        current_hope = getSkillValue(tmp_pc_id, '希望', tmp_hagID)
        if current_hope is None:
            current_hope = 0
        
        # ===== 第一阶段：预处理优势/劣势 =====
        # 统计所有优势和劣势的数量
        advantage_count = 0
        disadvantage_count = 0
        advantage_details = []
        disadvantage_details = []
        other_modifiers = []  # 非优势/劣势的修饰符
        
        for mod in result.get('modifiers', []):
            mod_type = mod['type']
            if mod_type == 'advantage':
                # 优势：value是正数，表示优势骰的数量
                num_dice = mod.get('num_dice', 1)  # 获取优势骰数量
                advantage_count += num_dice
                advantage_details.append(mod.get('detail', f'{num_dice}优势'))
            elif mod_type == 'disadvantage':
                # 劣势：value是负数，转换为正数统计
                num_dice = mod.get('num_dice', 1)  # 获取劣势骰数量
                disadvantage_count += num_dice
                disadvantage_details.append(mod.get('detail', f'{num_dice}劣势'))
            else:
                # 其他修饰符（属性、常量、骰子、经历等）
                other_modifiers.append(mod)
        
        # 优势和劣势抵消
        net_advantage = advantage_count - disadvantage_count
        
        # 构建优势/劣势详情文本
        adv_disadv_detail = []
        if advantage_count > 0:
            adv_disadv_detail.append(f'优势×{advantage_count}')
        if disadvantage_count > 0:
            adv_disadv_detail.append(f'劣势×{disadvantage_count}')
        
        # 掷优势/劣势骰
        advantage_modifier = 0
        if net_advantage > 0:
            # 剩余优势：掷骰取最大值
            dice_rolls = []
            for _ in range(net_advantage):
                rd = OlivaDiceCore.onedice.RD('1d6')
                rd.roll()
                if rd.resError is None:
                    dice_rolls.append(rd.resInt)
            if dice_rolls:
                advantage_modifier = max(dice_rolls)
                adv_disadv_detail.append(f'->({dice_rolls})优势+{advantage_modifier}')
        elif net_advantage < 0:
            # 剩余劣势：掷骰取最大值后取负
            dice_rolls = []
            for _ in range(-net_advantage):
                rd = OlivaDiceCore.onedice.RD('1d6')
                rd.roll()
                if rd.resError is None:
                    dice_rolls.append(rd.resInt)
            if dice_rolls:
                advantage_modifier = -max(dice_rolls)
                adv_disadv_detail.append(f'->({dice_rolls})劣势{advantage_modifier}')
        
        # ===== 第二阶段：消耗希望，处理其他修饰符 =====
        modifiers_detail = []
        total_modifier = advantage_modifier  # 从优势/劣势结果开始
        hope_consumed = 0  # 已消耗的希望
        skipped_modifiers = []  # 因希望不足而跳过的修饰符
        
        # 添加优势/劣势详情到输出
        if adv_disadv_detail:
            modifiers_detail.append(''.join(adv_disadv_detail))
        
        for mod in other_modifiers:
            mod_type = mod['type']
            mod_value = mod['value']
            mod_detail = mod.get('detail', '')
            mod_cost_hope = mod.get('cost_hope', False)  # 是否需要消耗希望
            
            # 检查是否需要消耗希望
            if mod_cost_hope:
                if current_hope - hope_consumed > 0:
                    # 有足够希望，消耗1点
                    hope_consumed += 1
                    total_modifier += mod_value
                    if mod_detail:
                        modifiers_detail.append(mod_detail)
                else:
                    # 希望不足，跳过此修饰符
                    skipped_modifiers.append(mod_detail if mod_detail else str(mod_value))
                    continue
            else:
                # 不需要消耗希望的修饰符
                if mod_type in ['attribute', 'constant', 'dice']:
                    total_modifier += mod_value
                    if mod_detail:
                        modifiers_detail.append(mod_detail)
        
        # 实际消耗希望
        if hope_consumed > 0:
            new_hope = current_hope - hope_consumed
            setSkillValue(tmp_pc_id, '希望', new_hope, tmp_pc_name, tmp_hagID)
            hope_max = getSkillValue(tmp_pc_id, '希望上限', tmp_hagID)
            
            dictTValue['tConsumed'] = str(hope_consumed)
            dictTValue['tOld'] = str(current_hope)
            dictTValue['tNew'] = str(new_hope)
            
            if hope_max is not None:
                dictTValue['tMax'] = str(hope_max)
                dictTValue['tHopeConsume'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strHopeConsume'], dictTValue
                )
            else:
                dictTValue['tHopeConsume'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strHopeConsumeNoMax'], dictTValue
                )
        else:
            dictTValue['tHopeConsume'] = ''
        
        # 如果有跳过的修饰符，发出警告
        if skipped_modifiers:
            dictTValue['tSkipped'] = '，'.join(skipped_modifiers)
            dictTValue['tHopeWarning'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strHopeWarning'], dictTValue
            )
        else:
            dictTValue['tHopeWarning'] = ''
        
        # 计算总点数 = 希望骰 + 恐惧骰 + 修饰符
        total = hope_roll + fear_roll + total_modifier
        
        # 构建修饰符详情文本
        if modifiers_detail:
            dictTValue['tModifiers'] = '，'.join(modifiers_detail)
            dictTValue['tModifiersDetail'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strModifiersDetail'], dictTValue
            )
        else:
            dictTValue['tModifiersDetail'] = ''
        
        # 判断检定结果
        result_texts = []
        hope_change = 0
        pressure_change = 0
        gm_fear_change = 0
        is_critical = False  # 标记是否大成功
        
        # 1. 大成功判定
        if hope_roll == fear_roll:
            is_critical = True
            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS
            result_texts.append(OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
                tmpSkillCheckType, dictStrCustom, dictTValue, tmp_pc_id, tmp_pc_name
            ))
            dictTValue['tTotalDisplay'] = f'*希望{total}*'
            if not is_reaction:
                hope_change = 1
                # 减少压力值
                current_pressure = getSkillValue(tmp_pc_id, '压力', tmp_hagID)
                if current_pressure is not None and current_pressure > 0:
                    pressure_change = -1
        
        # 2. 希望结果/恐惧结果判定
        elif hope_roll > fear_roll:
            # 希望结果 - 使用自定义文本
            result_texts.append(OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strHopeResult'], dictTValue
            ))
            dictTValue['tTotalDisplay'] = f'*希望{total}*'
            if not is_reaction:
                hope_change = 1
        
        else:  # hope_roll < fear_roll
            # 恐惧结果 - 使用自定义文本
            result_texts.append(OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strFearResult'], dictTValue
            ))
            dictTValue['tTotalDisplay'] = f'*恐惧{total}*'
            if not is_reaction:
                # 增加GM恐惧点
                gm_fear_change = updateGMFear(plugin_event, Proc, tmp_hagID, dictTValue, dictStrCustom)
        
        # 3. 成功/失败判定（如果有难度）- 大成功时不判定普通成功
        if 'difficulty' in result and not is_critical:
            difficulty = result['difficulty']
            if total > difficulty:
                tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS
                result_texts.append(OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
                    tmpSkillCheckType, dictStrCustom, dictTValue, tmp_pc_id, tmp_pc_name
                ))
            elif total < difficulty:
                tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
                result_texts.append(OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
                    tmpSkillCheckType, dictStrCustom, dictTValue, tmp_pc_id, tmp_pc_name
                ))
        
        # 更新人物卡数据（如果不是反应骰）
        # 注意：希望的消耗已经在前面处理过了，这里只处理增加
        if not is_reaction and (hope_change != 0 or pressure_change != 0):
            # 获取当前值（注意这里要重新获取，因为前面可能已经消耗过了）
            current_hope = getSkillValue(tmp_pc_id, '希望', tmp_hagID)
            hope_max = getSkillValue(tmp_pc_id, '希望上限', tmp_hagID)
            current_pressure = getSkillValue(tmp_pc_id, '压力', tmp_hagID)
            pressure_max = getSkillValue(tmp_pc_id, '压力上限', tmp_hagID)
            
            # 处理希望值增加
            if current_hope is not None and hope_change != 0:
                new_hope = current_hope + hope_change
                
                # 检查是否已达上限
                if hope_max is not None and current_hope >= hope_max and hope_change > 0:
                    # 希望点已达上限,不再增加
                    dictTValue['tOld'] = str(current_hope)
                    dictTValue['tMax'] = str(hope_max)
                    dictTValue['tHopeChange'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strHopeAlreadyMax'], dictTValue
                    )
                else:
                    # 限制范围
                    if hope_max is not None:
                        new_hope = min(new_hope, hope_max)
                    new_hope = max(0, new_hope)
                    
                    # 构建希望点变化文本（只显示增加部分，消耗已经在前面显示过了）
                    hope_detail_parts = []
                    if hope_change > 0:
                        hope_detail_parts.append(f"+{hope_change}({'关键成功' if hope_roll == fear_roll else '希望结果'})")
                    
                    hope_detail = ''.join(hope_detail_parts) if hope_detail_parts else ""
                    
                    dictTValue['tNew'] = str(new_hope)
                    dictTValue['tOld'] = str(current_hope)
                    dictTValue['tDetail'] = hope_detail
                    
                    if hope_max is not None:
                        dictTValue['tMax'] = str(hope_max)
                        dictTValue['tHopeChange'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strHopeChange'], dictTValue
                        )
                    else:
                        dictTValue['tHopeChange'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strHopeChangeNoMax'], dictTValue
                        )
                    
                    # 使用标准函数更新人物卡
                    setSkillValue(tmp_pc_id, '希望', new_hope, tmp_pc_name, tmp_hagID)
            
            if pressure_change != 0 and current_pressure is not None:
                new_pressure = current_pressure + pressure_change
                new_pressure = max(0, new_pressure)
                if pressure_max is not None:
                    new_pressure = min(new_pressure, pressure_max)
                
                if new_pressure == 0 and current_pressure == 0:
                    dictTValue['tPressureChange'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strPressureAlreadyZero'], dictTValue
                    )
                else:
                    dictTValue['tNew'] = str(new_pressure)
                    dictTValue['tOld'] = str(current_pressure)
                    dictTValue['tChange'] = f'{pressure_change:+d}'
                    
                    if pressure_max is not None:
                        dictTValue['tMax'] = str(pressure_max)
                        dictTValue['tPressureChange'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strPressureChange'], dictTValue
                        )
                    else:
                        dictTValue['tPressureChange'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strPressureChangeNoMax'], dictTValue
                        )
                
                # 使用标准函数更新人物卡
                setSkillValue(tmp_pc_id, '压力', new_pressure, tmp_pc_name, tmp_hagID)
            
            # 更新名片
            OlivaDiceCore.msgReply.trigger_auto_sn_update(plugin_event, user_id, tmp_pc_platform, tmp_hagID, dictTValue)
        
        # 设置最终结果文本
        dictTValue['tFinalResultText'] = '\n'.join(result_texts)
        
        # 设置挑战原因
        if result.get('reason'):
            dictTValue['tReason'] = result['reason']
            dictTValue['tChallengeReason'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strChallengeReason'], dictTValue
            )
        else:
            dictTValue['tChallengeReason'] = ''
        
        # 设置难度显示
        if 'difficulty' in result:
            dictTValue['tDifficulty'] = str(result['difficulty'])
            dictTValue['tDifficultyDisplay'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strDifficultyDisplay'], dictTValue
            )
        else:
            dictTValue['tDifficulty'] = ''
            dictTValue['tDifficultyDisplay'] = ''
        
        # 处理帮助者信息
        helper_messages = []
        if result.get('helpers'):
            for helper_info in result['helpers']:
                if helper_info['success']:
                    dictTValue['tHelperName'] = helper_info['name']
                    dictTValue['tHelperHopeCurrent'] = helper_info['hope_current']
                    dictTValue['tHelperHopeChange'] = helper_info['hope_change']
                    helper_messages.append(
                        OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strHelperSuccess'], dictTValue
                        )
                    )
                else:
                    dictTValue['tHelperName'] = helper_info['name']
                    if helper_info['reason'] == '未找到人物卡':
                        helper_messages.append(
                            OlivaDiceCore.msgCustomManager.formatReplySTR(
                                dictStrCustom['strHelperFailNoCard'], dictTValue
                            )
                        )
                    else:  # 希望点不足
                        helper_messages.append(
                            OlivaDiceCore.msgCustomManager.formatReplySTR(
                                dictStrCustom['strHelperFailNoHope'], dictTValue
                            )
                        )
        
        if helper_messages:
            dictTValue['tHelperInfo'] = ''.join(helper_messages)
        else:
            dictTValue['tHelperInfo'] = ''
        
        # 返回结果
        if is_reaction:
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strDDRResult'], dictTValue)
        else:
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strDDResult'], dictTValue)
    
    except Exception as e:
        dictTValue['tResult'] = str(e)
        return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strDDError'], dictTValue)

def parseDDCommand(command_str, tmp_pc_id, tmp_hagID, plugin_event, Proc, dictTValue):
    """解析DD命令参数"""
    # HTML实体解码 - 支持 &#91; -> [ 和 &#93; -> ]
    command_str = command_str.replace('&#91;', '[').replace('&#93;', ']')
    
    result = {
        'hope_dice_faces': 12,
        'fear_dice_faces': 12,
        'modifiers': [],
        'experience_cost': 0,
        'helpers': [],
        'reason': ''
    }
    
    # 解析消息中的@帮助者
    tmp_reast_str_para = OlivOS.messageAPI.Message_templet('old_string', command_str)
    at_user_ids = []
    new_command_str_parts = []
    
    for part in tmp_reast_str_para.data:
        if isinstance(part, OlivOS.messageAPI.PARA.at):
            at_user_id = part.data['id']
            # 检查是否是自己
            if str(at_user_id) != str(plugin_event.data.user_id):
                at_user_ids.append(at_user_id)
        else:
            if isinstance(part, OlivOS.messageAPI.PARA.text):
                new_command_str_parts.append(part.data['text'])
    
    # 移除@后的纯文本命令
    command_str = ''.join(new_command_str_parts).strip()
    
    # 处理帮助者（最多5人）
    for helper_user_id in at_user_ids[:5]:
        # 获取帮助者信息
        helper_name = OlivaDiceCore.msgReplyModel.get_user_name(plugin_event, helper_user_id)
        
        # 获取帮助者的人物卡
        helper_pc_data, helper_pc_id, helper_pc_name, _ = getPcCardData(
            plugin_event, 
            user_id=str(helper_user_id), 
            platform=plugin_event.platform['platform']
        )
        
        if helper_pc_data is None:
            # 帮助者没有人物卡，跳过
            result['helpers'].append({
                'name': helper_name,
                'success': False,
                'reason': '未找到人物卡'
            })
            continue
        
        # 检查帮助者的希望点
        helper_hope = getSkillValue(helper_pc_id, '希望', tmp_hagID)
        if helper_hope is None or helper_hope < 1:
            # 希望点不足
            result['helpers'].append({
                'name': helper_pc_name,
                'success': False,
                'reason': '希望点不足'
            })
            continue
        
        # 消耗帮助者的希望点
        helper_hope_max = getSkillValue(helper_pc_id, '希望上限', tmp_hagID)
        new_helper_hope = helper_hope - 1
        setSkillValue(helper_pc_id, '希望', new_helper_hope, helper_pc_name, tmp_hagID)
        
        # 更新帮助者名片 - 使用helper_user_id而不是helper_pc_id(pcHash)
        OlivaDiceCore.msgReply.trigger_auto_sn_update(
            plugin_event, str(helper_user_id), plugin_event.platform['platform'], tmp_hagID, dictTValue
        )
        
        # 添加一个优势骰作为帮助（只记录数量，不掷骰）
        result['modifiers'].append({
            'type': 'advantage',
            'value': 0,  # 占位，实际值在processDDCommand中计算
            'num_dice': 1,  # 1个优势骰
            'detail': f'{helper_pc_name}帮助',
            'cost_hope': False  # 帮助者的优势骰不消耗当前玩家的希望
        })
        
        # 记录成功的帮助
        if helper_hope_max is not None:
            hope_detail = f'{new_helper_hope}/{helper_hope_max}'
        else:
            hope_detail = str(new_helper_hope)
        
        result['helpers'].append({
            'name': helper_pc_name,
            'success': True,
            'hope_change': f'{helper_hope}-1={new_helper_hope}',
            'hope_current': hope_detail
        })
    
    # 使用正则表达式提取修饰符和原因
    # 先提取骰子面数(必须是纯数字/数字格式)
    dice_faces_match = re.search(r'(\d+/\d+|\d+/|/\d+)(?=\s|$|[\+\-#])', command_str)
    if dice_faces_match:
        dice_faces_str = dice_faces_match.group(1)
        command_str = command_str.replace(dice_faces_str, '', 1).strip()
        
        # 解析骰子面数
        match = re.match(r'^(\d*)/(\d*)$', dice_faces_str)
        if match:
            hope_faces, fear_faces = match.groups()
            if hope_faces:
                result['hope_dice_faces'] = int(hope_faces)
            if fear_faces:
                result['fear_dice_faces'] = int(fear_faces)
    
    # 提取所有修饰符 - 使用更精确的模式
    # 优先匹配无符号属性(后面跟+的)，给它们加上+号
    leadingattr_pattern = r'(?:^|\s)([^\s\+\-#\[]+)(?=\+)'
    leading_attrs = re.findall(leadingattr_pattern, command_str)
    for attr in leading_attrs:
        # 替换为带+的版本
        command_str = re.sub(r'(?:^|\s)' + re.escape(attr) + r'(?=\+)', ' +' + attr, command_str, count=1)
    
    # 提取所有修饰符
    # #\d+ - 难度值(#格式)
    # \[\d+\] - 难度值([N]格式)
    # [\+\-]\d+d\d+ - 带符号的骰子表达式(如+2d6)
    # (?:^|\s)\d+d\d+ - 开头的骰子表达式(如2d6)
    # [\+\-]\d*(?:优势?|劣势?|adv|dis)(?![\u4e00-\u9fa5\w])\d* - 带符号的优势/劣势
    # (?:^|\s)\d*(?:优势?|劣势?|adv|dis)(?![\u4e00-\u9fa5\w])\d* - 开头的优势/劣势
    # [\+\-]\d*(?:经历|exp)\d* - 带符号的经历
    # (?:^|\s)\d*(?:经历|exp)\d* - 开头的经历(如"经历 快速行动")
    # [\+\-]\d+ - 带符号的常量(如+3,-2)
    # [\+\-][^\s\+\-#\[]+ - 带符号的属性名
    modifier_pattern = r'#\d+|\[\d+\]|[\+\-]\d+d\d+|(?:^|\s)\d+d\d+|[\+\-]\d*(?:优势?|劣势?|adv|dis)(?![\u4e00-\u9fa5\w])\d*|(?:^|\s)\d*(?:优势?|劣势?|adv|dis)(?![\u4e00-\u9fa5\w])\d*|[\+\-]\d*(?:经历|exp)\d*|(?:^|\s)\d*(?:经历|exp)\d*|[\+\-]\d+|[\+\-][^\s\+\-#\[]+'
    
    modifiers_found = re.findall(modifier_pattern, command_str, re.I)
    
    # 过滤掉空字符串和只包含符号的项，并清理开头的空格
    modifiers_found = [m.strip() for m in modifiers_found if m and m.strip() not in ['+', '-', '']]
    
    # 剩余部分作为原因
    reason_str = command_str
    for mod in modifiers_found:
        reason_str = reason_str.replace(mod, '', 1)
    result['reason'] = reason_str.strip()
    
    modifier_parts = modifiers_found
    
    # 解析修饰符
    for part in modifier_parts:
        # 提取难度 - 支持 #10 和 [10] 两种格式
        if part.startswith('#'):
            try:
                result['difficulty'] = int(part[1:])
            except:
                pass
            continue
        elif part.startswith('[') and part.endswith(']'):
            try:
                result['difficulty'] = int(part[1:-1])
            except:
                pass
            continue
        
        # 解析修饰符
        mods = parseModifier(part, tmp_pc_id, tmp_hagID, result)
        if mods:
            result['modifiers'].extend(mods)
    
    return result

def parseModifier(mod_str, tmp_pc_id, tmp_hagID, result):
    """解析单个修饰符"""
    mods = []
    
    # 处理复合修饰符（如+力量+优势+5）
    # 分割成单个修饰符
    parts = re.split(r'(?=[+\-])', mod_str)
    parts = [p for p in parts if p]
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # 确定正负号
        sign = 1
        if part.startswith('+'):
            part = part[1:]
        elif part.startswith('-'):
            sign = -1
            part = part[1:]
        
        # 常量修饰符
        if part.isdigit():
            value = int(part) * sign
            mods.append({
                'type': 'constant',
                'value': value,
                'detail': f'{value:+d}',
                'cost_hope': False
            })
            continue
        
        # 骰子修饰符（如2d6）
        dice_match = re.match(r'^(\d*)d(\d+)$', part, re.I)
        if dice_match:
            num, faces = dice_match.groups()
            num = int(num) if num else 1
            faces = int(faces)
            
            rd = OlivaDiceCore.onedice.RD(f'{num}d{faces}')
            rd.roll()
            if rd.resError is None:
                roll_result = rd.resInt
                value = roll_result * sign
                
                mods.append({
                    'type': 'dice',
                    'value': value,
                    'detail': f'{value:+d}({num}d{faces})',
                    'cost_hope': False
                })
            continue
        
        # 优势/劣势骰 - 支持：优势、劣势、优、劣、adv、dis、2优势、优势3等
        # 注意：这里只记录数量，不掷骰（掷骰在processDDCommand中统一处理）
        # 逻辑：+优势=优势，-优势=劣势，+劣势=优势，-劣势=劣势
        # 特殊处理：劣势类无符号默认为劣势（-），而其他无符号默认为+
        adv_match = re.match(r'^(\d*)([优劣]势?|adv|dis|advantage|disadvantage)(\d*)$', part, re.I)
        if adv_match:
            num_before, adv_type, num_after = adv_match.groups()
            num = int(num_before or num_after or '1')
            
            is_advantage = adv_type.lower() in ['优势', '优', 'adv', 'advantage']
            is_disadvantage = adv_type.lower() in ['劣势', '劣', 'dis', 'disadvantage']
            
            # 特殊处理：劣势类无符号时默认为劣势（相当于sign=-1）
            effective_sign = sign
            if is_disadvantage and sign == 1:
                # 劣势类无符号时，默认为-（劣势）
                effective_sign = -1
            
            # 逻辑：+优势=优势，-优势=劣势，+劣势=优势，-劣势=劣势
            if is_advantage:
                # 优势关键字
                if effective_sign == 1:
                    # +优势 = 优势
                    final_type = 'advantage'
                else:
                    # -优势 = 劣势
                    final_type = 'disadvantage'
            else:
                # 劣势关键字
                if effective_sign == 1:
                    # +劣势 = 优势
                    final_type = 'advantage'
                else:
                    # -劣势 = 劣势
                    final_type = 'disadvantage'
            
            # 只记录数量，不掷骰
            if final_type == 'advantage':
                mods.append({
                    'type': 'advantage',
                    'value': 0,  # 占位，实际值在processDDCommand中计算
                    'num_dice': num,  # 优势骰数量
                    'detail': f'优势×{num}',
                    'cost_hope': False
                })
            else:
                mods.append({
                    'type': 'disadvantage',
                    'value': 0,  # 占位，实际值在processDDCommand中计算
                    'num_dice': num,  # 劣势骰数量
                    'detail': f'劣势×{num}',
                    'cost_hope': False
                })
            continue
        
        # 匿名经历修饰符
        exp_match = re.match(r'^(\d*)(经历|exp)(\d*)$', part, re.I)
        if exp_match:
            num_before, _, num_after = exp_match.groups()
            num = int(num_before or num_after or '2')  # 默认+2
            num = max(1, min(10, num))  # 限制1-10
            
            value = num * sign
            
            mods.append({
                'type': 'anonymous_exp',
                'value': value,
                'detail': f'{value:+d}(匿名经历)',
                'cost_hope': True  # 需要消耗希望
            })
            continue
        
        # 检查是否是技能/属性/经历
        skill_value = getSkillValue(tmp_pc_id, part, tmp_hagID)
        if skill_value is not None:
            value = skill_value * sign
            
            # 判断是模板技能还是自定义经历
            is_template_skill = isTemplateSkill(tmp_pc_id, part, tmp_hagID)
            
            if is_template_skill:
                # 模板中定义的技能/属性 - 不消耗希望
                mods.append({
                    'type': 'attribute',
                    'value': value,
                    'detail': f'{value:+d}({part})',
                    'cost_hope': False
                })
            else:
                # 自定义经历 - 消耗1点希望
                mods.append({
                    'type': 'experience',
                    'value': value,
                    'detail': f'{value:+d}({part}经历)',
                    'cost_hope': True  # 需要消耗希望
                })
            continue
    
    return mods

def updateGMFear(plugin_event, Proc, tmp_hagID, dictTValue, dictStrCustom):
    """更新GM恐惧点"""
    if not tmp_hagID:
        return 0
    
    try:
        # 获取群组标准hash
        group_hash = getGroupHash(plugin_event)
        
        # 加载GM数据
        gm_file = getDataPath(plugin_event.bot_info.hash, 'gm', group_hash)
        gm_data = loadData(gm_file)
        
        if not gm_data:
            return 0
        
        gm_fear_changes = []
        
        # 遍历所有GM
        for gm_hash, gm_info in gm_data.items():
            user_id = gm_info.get('user_id')
            platform = gm_info.get('platform')
            
            if not user_id or not platform:
                continue
            
            # 获取GM人物卡
            gm_pc_data, gm_pc_id, gm_pc_name, gm_hagID = getPcCardData(
                plugin_event, user_id=user_id, platform=platform
            )
            
            if gm_pc_data is None:
                continue
            
            # 获取当前恐惧点和上限
            current_fear = getSkillValue(gm_pc_id, '恐惧', gm_hagID)
            fear_max = getSkillValue(gm_pc_id, '恐惧上限', gm_hagID)
            
            if current_fear is not None:
                new_fear = current_fear + 1
                
                # 设置模板变量
                dictTValue['tGMName'] = gm_pc_name
                dictTValue['tGMFearOld'] = str(current_fear)
                dictTValue['tGMFearNew'] = str(min(new_fear, fear_max) if fear_max is not None else new_fear)
                
                if fear_max is not None:
                    dictTValue['tGMFearDisplay'] = f"{dictTValue['tGMFearNew']}/{fear_max}"
                    if new_fear > fear_max:
                        new_fear = fear_max
                        gm_fear_changes.append(
                            OlivaDiceCore.msgCustomManager.formatReplySTR(
                                dictStrCustom['strGMFearMax'], dictTValue
                            )
                        )
                    else:
                        gm_fear_changes.append(
                            OlivaDiceCore.msgCustomManager.formatReplySTR(
                                dictStrCustom['strGMFearIncrease'], dictTValue
                            )
                        )
                else:
                    dictTValue['tGMFearDisplay'] = str(new_fear)
                    gm_fear_changes.append(
                        OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strGMFearIncrease'], dictTValue
                        )
                    )
                
                # 更新GM人物卡
                setSkillValue(gm_pc_id, '恐惧', new_fear, gm_pc_name, gm_hagID)
                
                # 更新GM名片 - 使用user_id而不是gm_pc_id(pcHash)
                OlivaDiceCore.msgReply.trigger_auto_sn_update(plugin_event, user_id, platform, gm_hagID, dictTValue)
        
        if gm_fear_changes:
            dictTValue['tGMFearChange'] = ''.join(gm_fear_changes)
        
        return 1
    except:
        return 0


# ==================== .gm 命令处理 ====================

def processGMCommand(plugin_event, Proc, command_str, dictTValue, dictStrCustom, tmp_hagID, flag_is_from_group):
    """处理GM管理命令"""
    if not flag_is_from_group:
        return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strForGroupOnly'], dictTValue)
    
    try:
        # 导入标准命令处理函数
        isMatchWordStart = OlivaDiceCore.msgReply.isMatchWordStart
        getMatchWordStartRight = OlivaDiceCore.msgReply.getMatchWordStartRight
        skipSpaceStart = OlivaDiceCore.msgReply.skipSpaceStart
        
        # 获取群组标准hash
        group_hash = getGroupHash(plugin_event)
        
        # 加载GM数据
        gm_file = getDataPath(plugin_event.bot_info.hash, 'gm', group_hash)
        gm_data = loadData(gm_file)
        
        user_id = plugin_event.data.user_id
        platform = plugin_event.platform['platform']
        user_hash = OlivaDiceCore.userConfig.getUserHash(user_id, 'user', platform)
        
        # .gm del - 卸任GM
        if isMatchWordStart(command_str, ['del', 'delete', 'remove']):
            command_str = getMatchWordStartRight(command_str, ['del', 'delete', 'remove'])
            command_str = skipSpaceStart(command_str)
            
            if user_hash in gm_data:
                del gm_data[user_hash]
                saveData(gm_file, gm_data)
                dictTValue['tUserName'] = plugin_event.data.sender['name']
                return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strGMDel'], dictTValue)
            else:
                dictTValue['tResult'] = '你不是本群的GM'
                return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strGMError'], dictTValue)
        
        # .gm clr/clear - 清除所有GM
        elif isMatchWordStart(command_str, ['clr', 'clear']):
            command_str = getMatchWordStartRight(command_str, ['clr', 'clear'])
            command_str = skipSpaceStart(command_str)
            
            gm_data.clear()
            saveData(gm_file, gm_data)
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strGMClear'], dictTValue)
        
        # .gm - 设置GM
        else:
            # 使用群组hash前8位缩短长度
            group_hash_short = group_hash[:8]
            
            # 创建/获取GM人物卡 - 使用群号哈希缩短长度
            gm_card_name = f"{group_hash_short}_dhgm_{plugin_event.data.sender['name']}"
            
            # 获取用户pcHash
            tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(user_id, platform)
            
            # 检查人物卡是否存在
            pc_dict = OlivaDiceCore.pcCard.pcCardDataGetUserAll(tmp_pcHash)
            if gm_card_name not in pc_dict:
                # 创建新人物卡 - 通过设置一个技能来初始化
                OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
                    tmp_pcHash,
                    '恐惧',
                    0,
                    gm_card_name,
                    hagId=tmp_hagID
                )
                # 设置模板
                OlivaDiceCore.pcCard.pcCardDataSetTemplateKey(
                    tmp_pcHash,
                    gm_card_name,
                    'dhgm'
                )
            
            # 切换到GM人物卡 (使用群组锁定)
            OlivaDiceCore.pcCard.pcCardDataSetSelectionKeyLock(
                tmp_pcHash,
                gm_card_name,
                tmp_hagID
            )
            
            # 保存GM信息
            gm_data[user_hash] = {
                'user_id': user_id,
                'platform': platform,
                'group_id': plugin_event.data.group_id,
                'host_id': plugin_event.data.host_id if hasattr(plugin_event.data, 'host_id') else None
            }
            saveData(gm_file, gm_data)
            
            # 使用模板的自动名片更新
            OlivaDiceCore.msgReply.trigger_auto_sn_update(
                plugin_event, 
                user_id, 
                platform, 
                tmp_hagID, 
                dictTValue
            )
            
            dictTValue['tUserName'] = plugin_event.data.sender['name']
            dictTValue['tCardName'] = gm_card_name
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strGMSet'], dictTValue)
    
    except Exception as e:
        dictTValue['tResult'] = str(e)
        return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strGMError'], dictTValue)


# ==================== .cook 命令处理 ====================

def processCookCommand(plugin_event, Proc, command_str, dictTValue, dictStrCustom, tmp_hagID, flag_is_from_group):
    """处理烹饪游戏命令"""
    if not flag_is_from_group:
        return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strForGroupOnly'], dictTValue)
    
    try:
        # 导入标准命令处理函数
        isMatchWordStart = OlivaDiceCore.msgReply.isMatchWordStart
        getMatchWordStartRight = OlivaDiceCore.msgReply.getMatchWordStartRight
        skipSpaceStart = OlivaDiceCore.msgReply.skipSpaceStart
        
        # 获取群组标准hash
        group_hash = getGroupHash(plugin_event)
        
        cook_file = getDataPath(plugin_event.bot_info.hash, 'cook', group_hash)
        cook_data = loadData(cook_file)
        
        # .cook rm [骰面] - 移除骰子
        if isMatchWordStart(command_str, ['rm', 'remove']):
            if 'dice' not in cook_data:
                return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCookErrorNoGame'], dictTValue)
            
            # 获取rm后面的参数
            command_str = getMatchWordStartRight(command_str, ['rm', 'remove'])
            command_str = skipSpaceStart(command_str)
            
            # 解析要移除的骰面 - 支持 "10"、"d10"、"D10" 等格式
            face_str = command_str.strip().lower()
            
            # 移除可能的 'd' 或 'D' 前缀
            if face_str.startswith('d'):
                face_str = face_str[1:]
            
            # 尝试转换为数字
            try:
                face = int(face_str)
            except:
                return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCookErrorFormat'], dictTValue)
            
            # 检查是否有该骰面的未配对骰子
            unpaired = cook_data.get('unpaired', [])
            found = False
            for i, dice in enumerate(unpaired):
                if dice['faces'] == face:
                    removed_dice = unpaired.pop(i)
                    found = True
                    break
            
            if not found:
                available = list(set([d['faces'] for d in unpaired]))
                dictTValue['tRemoveFace'] = str(face)
                dictTValue['tAvailableFaces'] = ', '.join(['d' + str(f) for f in available])
                return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCookErrorNoDice'], dictTValue)
            
            # 重新投掷剩余骰子
            for dice in unpaired:
                rd = OlivaDiceCore.onedice.RD(f"1d{dice['faces']}")
                rd.roll()
                dice['value'] = rd.resInt
            
            # 配对
            paired, unpaired_new = pairDice(unpaired)
            score_add = sum([p['value'] for p in paired])
            cook_data['score'] += score_add
            cook_data['round'] += 1
            cook_data['unpaired'] = unpaired_new
            
            # 检查游戏是否结束
            if len(unpaired_new) <= 2:
                # 尝试最后配对
                if len(unpaired_new) == 2 and unpaired_new[0]['value'] == unpaired_new[1]['value']:
                    final_score = unpaired_new[0]['value']
                    cook_data['score'] += final_score
                    unpaired_new = []
                
                # 游戏结束
                final_score = cook_data['score']
                
                # 评价 - 使用自定义文本
                dictTValue['tFinalScore'] = str(final_score)
                if final_score < 4:
                    dictTValue['tScoreComment'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strCookScoreLow'], dictTValue
                    )
                elif final_score <= 10:
                    dictTValue['tScoreComment'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strCookScoreMid'], dictTValue
                    )
                else:
                    dictTValue['tScoreComment'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strCookScoreHigh'], dictTValue
                    )
                
                dictTValue['tRemovedDice'] = f"[d{removed_dice['faces']}:{removed_dice['value']}]"
                dictTValue['tRemainingCount'] = str(len(unpaired_new))
                dictTValue['tDiceList'] = ' '.join([f"[d{d['faces']}:{d['value']}]" for d in unpaired_new]) if unpaired_new else ''
                dictTValue['tRound'] = str(cook_data['round'])
                
                pair_result = []
                if paired:
                    dictTValue['tPairCount'] = str(len(paired))
                    pair_result.append(
                        OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strCookPairSuccess'], dictTValue
                        )
                    )
                    for p in paired:
                        dictTValue['tPairValue'] = str(p['value'])
                        pair_result.append(
                            OlivaDiceCore.msgCustomManager.formatReplySTR(
                                dictStrCustom['strCookPairDetail'], dictTValue
                            )
                        )
                else:
                    pair_result.append(
                        OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strCookPairNone'], dictTValue
                        )
                    )
                
                if unpaired_new:
                    dictTValue['tUnpairedCount'] = str(len(unpaired_new))
                    pair_result.append(
                        OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strCookUnpaired'], dictTValue
                        )
                    )
                    pair_result.append(' '.join([f"[d{d['faces']}:{d['value']}]" for d in unpaired_new]))
                else:
                    if len(cook_data.get('dice', [])) > 0:
                        pair_result.append(
                            OlivaDiceCore.msgCustomManager.formatReplySTR(
                                dictStrCustom['strCookAllUsed'], dictTValue
                            )
                        )
                
                dictTValue['tPairResult'] = '\n'.join(pair_result)
                
                # 清除游戏数据
                if tmp_hagID in cook_data:
                    del cook_data[tmp_hagID]
                saveData(cook_file, {})
                
                return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCookEnd'], dictTValue)
            
            # 游戏继续
            dictTValue['tRemovedDice'] = f"[d{removed_dice['faces']}:{removed_dice['value']}]"
            dictTValue['tRemainingCount'] = str(len(unpaired_new))
            dictTValue['tDiceList'] = ' '.join([f"[d{d['faces']}:{d['value']}]" for d in unpaired_new])
            dictTValue['tRound'] = str(cook_data['round'])
            
            pair_result = []
            if paired:
                dictTValue['tPairCount'] = str(len(paired))
                pair_result.append(
                    OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strCookPairSuccess'], dictTValue
                    )
                )
                for p in paired:
                    dictTValue['tPairValue'] = str(p['value'])
                    pair_result.append(
                        OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strCookPairDetail'], dictTValue
                        )
                    )
            else:
                pair_result.append(
                    OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strCookPairNone'], dictTValue
                    )
                )
            
            dictTValue['tUnpairedCount'] = str(len(unpaired_new))
            pair_result.append(
                OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strCookUnpaired'], dictTValue
                )
            )
            pair_result.append(' '.join([f"[d{d['faces']}:{d['value']}]" for d in unpaired_new]))
            
            dictTValue['tPairResult'] = '\n'.join(pair_result)
            dictTValue['tCurrentScore'] = str(cook_data['score'])
            
            available = list(set([d['faces'] for d in unpaired_new]))
            dictTValue['tAvailableFaces'] = ', '.join(['d' + str(f) for f in available])
            dictTValue['tNextStep'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strCookNextStep'], dictTValue
            )
            
            saveData(cook_file, cook_data)
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCookContinue'], dictTValue)
        
        # .cook [ndm]+[ndm]+... - 开始新游戏
        else:
            # 解析骰子
            dice_pattern = r'(\d*)d(\d+)'
            matches = re.findall(dice_pattern, command_str, re.I)
            
            if not matches:
                return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCookErrorFormat'], dictTValue)
            
            # 投掷所有骰子
            all_dice = []
            for num_str, faces_str in matches:
                num = int(num_str) if num_str else 1
                faces = int(faces_str)
                for _ in range(num):
                    rd = OlivaDiceCore.onedice.RD(f'1d{faces}')
                    rd.roll()
                    all_dice.append({
                        'faces': faces,
                        'value': rd.resInt
                    })
            
            # 配对
            paired, unpaired = pairDice(all_dice)
            score = sum([p['value'] for p in paired])
            
            # 保存游戏状态
            cook_data = {
                'dice': all_dice,
                'score': score,
                'round': 1,
                'unpaired': unpaired
            }
            saveData(cook_file, cook_data)
            
            # 构建输出
            dictTValue['tDiceList'] = ' '.join([f"[d{d['faces']}:{d['value']}]" for d in all_dice])
            dictTValue['tRound'] = '1'
            
            pair_result = []
            if paired:
                dictTValue['tPairCount'] = str(len(paired))
                pair_result.append(
                    OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strCookPairSuccess'], dictTValue
                    )
                )
                for p in paired:
                    dictTValue['tPairValue'] = str(p['value'])
                    pair_result.append(
                        OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strCookPairDetail'], dictTValue
                        )
                    )
            else:
                pair_result.append(
                    OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strCookPairNone'], dictTValue
                    )
                )
            
            if unpaired:
                dictTValue['tUnpairedCount'] = str(len(unpaired))
                pair_result.append(
                    OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strCookUnpaired'], dictTValue
                    )
                )
                pair_result.append(' '.join([f"[d{d['faces']}:{d['value']}]" for d in unpaired]))
            
            dictTValue['tPairResult'] = '\n'.join(pair_result)
            dictTValue['tCurrentScore'] = str(score)
            
            available = list(set([d['faces'] for d in unpaired]))
            dictTValue['tAvailableFaces'] = ', '.join(['d' + str(f) for f in available])
            dictTValue['tNextStep'] = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strCookNextStep'], dictTValue
            )
            
            return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCookStart'], dictTValue)
    
    except Exception as e:
        dictTValue['tErrorMsg'] = str(e)
        return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strCookError'], dictTValue)

def pairDice(dice_list):
    """配对骰子"""
    paired = []
    unpaired = []
    
    # 按值分组
    value_groups = {}
    for dice in dice_list:
        value = dice['value']
        if value not in value_groups:
            value_groups[value] = []
        value_groups[value].append(dice)
    
    # 配对
    for value, group in value_groups.items():
        pairs = len(group) // 2
        for _ in range(pairs):
            paired.append({'value': value})
        
        if len(group) % 2 == 1:
            unpaired.append(group[0])
    
    return paired, unpaired

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
