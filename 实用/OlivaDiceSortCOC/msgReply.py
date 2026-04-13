# -*- encoding: utf-8 -*-
'''
这里写你的回复。注意插件前置：OlivaDiceCore，写命令请跳转到第146行。
'''

import OlivOS
import OlivaDiceSortCOC
import OlivaDiceCore

import copy
import json
import requests
import os

# 全局变量存储Proc对象
globalProc = None

def unity_init(plugin_event, Proc):
    global globalProc
    globalProc = Proc

def data_init(plugin_event, Proc):
    global globalProc
    globalProc = Proc
    OlivaDiceSortCOC.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

def get_account_config(plugin_event):
    """从Proc对象获取账号配置，根据当前bot的hash匹配对应账号，失败时返回None"""
    global globalProc
    if globalProc is None:
        return None
    
    try:
        # 获取当前bot的hash
        bot_hash = plugin_event.bot_info.hash
        
        # 从Proc中获取bot信息
        bot_info_dict = globalProc.Proc_data.get('bot_info_dict', {})
        if bot_hash not in bot_info_dict:
            return None
        
        bot_info = bot_info_dict[bot_hash]
        post_info = bot_info.post_info
        
        # 检查必要的字段是否存在
        if post_info.host is None or post_info.port == -1 or post_info.access_token is None:
            return None
        
        # 构建server_config字典
        server_config = {
            'host': post_info.host,
            'port': post_info.port,
            'access_token': post_info.access_token
        }
        
        return server_config
    except Exception as e:
        print(f"从Proc获取账号配置失败: {e}")
        return None

def create_forward_node(user_id, nickname, content):
    """创建转发消息节点"""
    return {
        "type": "node",
        "data": {
            "user_id": str(user_id),
            "nickname": nickname,
            "content": content
        }
    }

def normalize_pc_card_template(tmp_pcCardTemplate, tmp_pcCardTemplateName):
    """兼容错误入参，确保后续总能按模板字典读取字段。"""
    if isinstance(tmp_pcCardTemplate, str):
        if tmp_pcCardTemplateName == "COC7":
            tmp_pcCardTemplateName = tmp_pcCardTemplate
        tmp_pcCardTemplate = OlivaDiceCore.pcCard.pcCardDataGetTemplateByKey(tmp_pcCardTemplate)

    if not isinstance(tmp_pcCardTemplate, dict):
        return {'showName': {}}

    if not isinstance(tmp_pcCardTemplate.get('showName'), dict):
        tmp_pcCardTemplate = copy.deepcopy(tmp_pcCardTemplate)
        tmp_pcCardTemplate['showName'] = {}

    return tmp_pcCardTemplate

def generate_sorted_message(sorted_list, title, tmp_pcCardTemplate, use_luck_in_total=True, tmp_pcCardTemplateName="COC7"):
    """生成排序后的回复消息"""
    tmp_pcCardTemplate = normalize_pc_card_template(tmp_pcCardTemplate, tmp_pcCardTemplateName)
    message = f"{title}"
    for i, item in enumerate(sorted_list):
        if i > 0:
            message += '\n\n'
        else:
            message += '\n'
        res = item['data']
        original_index = item['index']
        total_value = item['total_with_luck'] if use_luck_in_total else item['total_without_luck']
        count = 0
        total_skills = len(res)
        for j, (skill, value) in enumerate(res.items()):
            skill_name = tmp_pcCardTemplate['showName'].get(skill, skill)
            message += f"{skill_name}: {value}  "
            count += 1
            if count % 3 == 0 and j < total_skills - 1:
                message += "\n"
        total_without_luck = item['total_without_luck']
        total_with_luck = item['total_with_luck']
        # COC7特定计算
        if tmp_pcCardTemplateName in ['COC7']:
            # 计算HP
            if 'CON' in res and 'SIZ' in res:
                hp = (res['CON'] + res['SIZ']) // 10
                message += f'\nHP: {hp}'
            # 计算体格
            build = OlivaDiceCore.skillCheck.getSpecialSkill('体格', tmp_pcCardTemplateName, res)
            if build:
                message += f'  体格: {build}'
            db = OlivaDiceCore.skillCheck.getSpecialSkill('DB', tmp_pcCardTemplateName, res)
            if db:
                message += f'  DB: {db}'
        if 'LUC' in res:
            efficiency = 100 * total_without_luck / total_with_luck if total_with_luck > 0 else 0
            message += f"\n共计: {total_without_luck}/{total_with_luck}  {efficiency:.2f}%"
        else:
            message += f"\n共计: {total_without_luck}"
        i += 1
    return message

def send_forward_message(plugin_event, messages, server_config):
    """发送转发消息"""
    forward_data = {
        "Type": "Http",
        "Host": server_config["host"].replace("http://", "").replace("https://", ""),
        "Port": server_config["port"],
        "AccessToken": server_config["access_token"]
    }
    
    if plugin_event.plugin_info['func_type'] == 'group_message':
        api_url = f"http://{forward_data['Host']}:{forward_data['Port']}/send_group_forward_msg"
        payload = {
            "group_id": plugin_event.data.group_id,
            "messages": messages
        }
    else:
        api_url = f"http://{forward_data['Host']}:{forward_data['Port']}/send_private_forward_msg"
        payload = {
            "user_id": plugin_event.data.user_id,
            "messages": messages
        }
    
    headers = {
        "Authorization": f"Bearer {forward_data['AccessToken']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            api_url,
            data=json.dumps(payload),
            headers=headers
        )
        return response.status_code == 200
    except Exception:
        return False

def send_normal_message(plugin_event, dictTValue, dictStrCustom, tmp_pcCardTemplate, tmp_pcCardTemplateName, sorted_by_total_with_luck, sorted_by_total_without_luck):
    """发送普通消息"""
    replyMsg = OlivaDiceCore.msgReply.replyMsg
    msg_by_total = generate_sorted_message(sorted_by_total_with_luck, "\n【含运排序(从高到低)】", tmp_pcCardTemplate, True, tmp_pcCardTemplateName)
    dictTValue['tPcTempName'] = tmp_pcCardTemplateName
    dictTValue['tPcInitResult'] = msg_by_total
    send_msg_total = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcInit'], dictTValue)

    msg_by_efficiency = generate_sorted_message(sorted_by_total_without_luck, "\n【不含运排序(从高到低)】", tmp_pcCardTemplate, False, tmp_pcCardTemplateName)
    dictTValue['tPcInitResult'] = msg_by_efficiency
    send_msg_efficiency = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcInit'], dictTValue)

    replyMsg(plugin_event, send_msg_total)
    replyMsg(plugin_event, send_msg_efficiency)

def process_coc_command(plugin_event, dictTValue, dictStrCustom, tmp_reast_str):
    """处理coc命令"""
    replyMsg = OlivaDiceCore.msgReply.replyMsg
    isMatchWordStart = OlivaDiceCore.msgReply.isMatchWordStart
    getMatchWordStartRight = OlivaDiceCore.msgReply.getMatchWordStartRight
    skipSpaceStart = OlivaDiceCore.msgReply.skipSpaceStart
    tmp_reply_str = ''
    tmp_pcCardTemplateName = 'default'
    
    if isMatchWordStart(tmp_reast_str, 'coc6'):
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'coc6')
        tmp_pcCardTemplateName = 'COC6'
    elif isMatchWordStart(tmp_reast_str, 'coc'):
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'coc')
        tmp_pcCardTemplateName = 'COC7'
        
    tmp_roll_count = 1
    tmp_roll_count_str = None
    tmp_pcCardTemplate = OlivaDiceCore.pcCard.pcCardDataGetTemplateByKey(tmp_pcCardTemplateName)
    tmp_res_list = []
    tmp_reast_str = skipSpaceStart(tmp_reast_str)
    
    if len(tmp_reast_str) > 0:
        [tmp_roll_count_str, tmp_reast_str] = OlivaDiceCore.msgReply.getNumberPara(tmp_reast_str)
    if tmp_roll_count_str == '':
        tmp_roll_count_str = None
    if tmp_roll_count_str != None:
        if tmp_roll_count_str.isdecimal():
            tmp_roll_count = int(tmp_roll_count_str)
            
    if tmp_roll_count > 0 and tmp_roll_count <= 10:
        tmp_res_list = []
        tmp_range_list = range(0, tmp_roll_count)
        for tmp_i in tmp_range_list:
            tmp_res_list_node = {}
            for tmp_pcCardTemplate_skill_this in tmp_pcCardTemplate['init']:
                tmp_skill_rd_this = OlivaDiceCore.onedice.RD(tmp_pcCardTemplate['init'][tmp_pcCardTemplate_skill_this])
                tmp_skill_rd_this.roll()
                if tmp_skill_rd_this.resError == None:
                    tmp_res_list_node[tmp_pcCardTemplate_skill_this] = tmp_skill_rd_this.resInt
            tmp_res_list.append(tmp_res_list_node)

        res_list_with_total = []
        for i, res in enumerate(tmp_res_list):
            total_with_luck = sum(res.values())
            total_without_luck = sum(v for k, v in res.items() if k != 'LUC')
            res_list_with_total.append({
                'index': i + 1,
                'data': res,
                'total_with_luck': total_with_luck,
                'total_without_luck': total_without_luck
            })

        if len(res_list_with_total) > 1:
            sorted_by_total_with_luck = sorted(res_list_with_total, 
                                             key=lambda x: x['total_with_luck'], 
                                             reverse=True)
            sorted_by_total_without_luck = sorted(res_list_with_total, 
                                                key=lambda x: x['total_without_luck'], 
                                                reverse=True)
            
            platform = plugin_event.platform['platform']
            if platform != 'qq':
                send_normal_message(plugin_event, dictTValue, dictStrCustom, tmp_pcCardTemplate, tmp_pcCardTemplateName, sorted_by_total_with_luck, sorted_by_total_without_luck)
                plugin_event.set_block()
                return
                
            server_config = get_account_config(plugin_event)
            if server_config is None:
                replyMsg(plugin_event, "无法获取账号配置，请检查Bot配置是否正确")
                plugin_event.set_block()
                return
                
            messages = []
            content_with_luck = generate_sorted_message(sorted_by_total_with_luck, "\n【含运排序(从高到低)】", tmp_pcCardTemplate, True, tmp_pcCardTemplateName)
            dictTValue['tPcTempName'] = tmp_pcCardTemplateName
            dictTValue['tPcInitResult'] = content_with_luck
            send_msg_with_luck = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcInit'], dictTValue)
            messages.append(create_forward_node(plugin_event.bot_info.id, OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]['strBotName'], send_msg_with_luck))
            
            content_without_luck = generate_sorted_message(sorted_by_total_without_luck, "\n【不含运排序(从高到低)】", tmp_pcCardTemplate, False, tmp_pcCardTemplateName)
            dictTValue['tPcTempName'] = tmp_pcCardTemplateName
            dictTValue['tPcInitResult'] = content_without_luck
            send_msg_without_luck = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcInit'], dictTValue)
            messages.append(create_forward_node(plugin_event.bot_info.id, OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]['strBotName'], send_msg_without_luck))

            if not send_forward_message(plugin_event, messages, server_config):
                send_normal_message(plugin_event, dictTValue, dictStrCustom, tmp_pcCardTemplate, tmp_pcCardTemplateName, sorted_by_total_with_luck, sorted_by_total_without_luck)
                
            plugin_event.set_block()
            return
        else:
            tmp_msg = generate_sorted_message(res_list_with_total, "", tmp_pcCardTemplate, True, tmp_pcCardTemplateName)
            dictTValue['tPcTempName'] = tmp_pcCardTemplateName
            dictTValue['tPcInitResult'] = tmp_msg
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcInit'], dictTValue)
            replyMsg(plugin_event, tmp_reply_str)
            plugin_event.set_block()
            return
    else:
        dictTValue['tPcTempName'] = tmp_pcCardTemplateName
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPcInitErrorRange'], dictTValue)
        replyMsg(plugin_event, tmp_reply_str)
        plugin_event.set_block()
        return

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
                
        if not flag_hostLocalEnable and not flag_force_reply:
            return
            
        if not flag_groupEnable and not flag_force_reply:
            return
            
        if isMatchWordStart(tmp_reast_str, ['coc6','coc'], isCommand = True):
            process_coc_command(plugin_event, dictTValue, dictStrCustom, tmp_reast_str)