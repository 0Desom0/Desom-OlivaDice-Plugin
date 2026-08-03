# -*- encoding: utf-8 -*-
'''
背包插件回复处理
'''

import OlivOS
import OlivaDiceBackpack
import OlivaDiceCore
import json
import os
import random
import hashlib
import time


def unity_init(plugin_event, Proc):
    # 插件初始化
    pass

def init_config_for_bot(bot_hash, default_config, old_config=None):
    """为单个bot初始化配置文件"""
    config_path = os.path.join('plugin', 'data', 'OlivaDiceBackpack', bot_hash)
    if not os.path.exists(config_path):
        os.makedirs(config_path)
    
    json_path = os.path.join(config_path, 'config.json')
    
    # 如果有旧配置，优先使用旧配置
    if old_config is not None and not os.path.exists(json_path):
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(old_config, f, ensure_ascii=False, indent=4)
    # 如果json文件不存在，则创建并写入默认值
    elif not os.path.exists(json_path):
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=4)

def data_init(plugin_event, Proc):
    # 默认配置
    default_config = {
        "shop_items": {
            "道具盲盒": {
                "price": 10000,
                "description": "随机获得各种道具的神秘盒子"
            }
        },
        "admin_users": {},
        "blindbox_config": {
            "prizes": [
                {
                    "name": "道具盲盒",
                    "weight": 20,
                    "message": "套娃！"
                },
                {
                    "name": "空！",
                    "weight": 80,
                    "message": "谢谢惠顾，欢迎下次再来哦~"
                }
            ]
        }
    }
    
    # 兼容性检测：检查旧的文件路径
    old_json_path = os.path.join('plugin', 'data', 'OlivaDiceBackpack', 'config.json')
    old_config = None
    if os.path.exists(old_json_path):
        try:
            # 读取旧文件内容
            with open(old_json_path, 'r', encoding='utf-8') as f:
                old_config = json.load(f)
        except Exception as e:
            print(f"读取旧配置文件失败: {e}")
    
    # 遍历所有bot进行初始化
    if 'bot_info_dict' in Proc.Proc_data:
        for bot_hash in Proc.Proc_data['bot_info_dict']:
            init_config_for_bot(bot_hash, default_config, old_config)
    
    # 删除旧文件（在所有bot都迁移完成后）
    if old_config is not None:
        try:
            os.remove(old_json_path)
        except Exception as e:
            print(f"删除旧配置文件失败: {e}")
    
    # 数据初始化
    OlivaDiceBackpack.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

def load_config(bot_hash):
    """加载配置文件"""
    config_path = os.path.join('plugin', 'data', 'OlivaDiceBackpack', bot_hash, 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_config(bot_hash, config_data):
    """保存配置文件"""
    config_path = os.path.join('plugin', 'data', 'OlivaDiceBackpack', bot_hash, 'config.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        return True
    except:
        return False

def get_user_hash(user_id, platform):
    """获取用户hash"""
    return OlivaDiceCore.userConfig.getUserHash(user_id, 'user', platform)

def get_user_data_path(bot_hash, user_hash):
    """获取用户数据文件路径"""
    user_dir = os.path.join('plugin', 'data', 'OlivaDiceBackpack', bot_hash, 'user')
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return os.path.join(user_dir, f'{user_hash}.json')

def load_user_data(bot_hash, user_id, platform, auto_init=False):
    """加载用户数据
    
    Args:
        bot_hash: bot的hash值
        user_id: 用户ID
        platform: 平台
        auto_init: 如果为True且文件不存在，则自动创建并初始化用户数据文件
    """
    user_hash = get_user_hash(user_id, platform)
    user_data_path = get_user_data_path(bot_hash, user_hash)
    
    # 检查文件是否存在
    if not os.path.exists(user_data_path):
        # 创建默认数据
        default_data = {
            'contribution': 0,
            'inventory': {},
            'collections': {}
        }
        
        # 如果auto_init为True，则自动创建文件
        if auto_init:
            try:
                with open(user_data_path, 'w', encoding='utf-8') as f:
                    json.dump(default_data, f, ensure_ascii=False, indent=4)
            except:
                pass
        
        return default_data
    
    # 文件存在，读取数据
    try:
        with open(user_data_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {
            'contribution': 0,
            'inventory': {},
            'collections': {}
        }

def save_user_data(bot_hash, user_id, platform, user_data):
    """保存用户数据"""
    user_hash = get_user_hash(user_id, platform)
    user_data_path = get_user_data_path(bot_hash, user_hash)
    try:
        with open(user_data_path, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
        return True
    except:
        return False

def get_user_name(plugin_event, user_id):
    """获取用户名称"""
    user_name = OlivaDiceCore.userConfig.getUserConfigByKey(
        userId = user_id,
        userType = 'user',
        platform = plugin_event.platform['platform'],
        userConfigKey = 'userName',
        botHash = plugin_event.bot_info.hash
    )
    # 没获取到再用api获取
    if user_name == None:
        plres = plugin_event.get_stranger_info(user_id)
        if plres != None and 'active' in plres and plres['active']:
            user_name = plres['data']['name']
        else:
            user_name = f'用户{user_id}'
    return user_name

def parse_at_user(plugin_event, tmp_reast_str):
    """
    解析消息中的@用户
    返回: is_at, at_user_id, cleaned_message_str
    """
    tmp_reast_str_para = OlivOS.messageAPI.Message_templet('old_string', tmp_reast_str)
    at_user_id = None
    new_tmp_reast_str_parts = []
    is_at = False
    
    for part in tmp_reast_str_para.data:
        if isinstance(part, OlivOS.messageAPI.PARA.at):
            at_user_id = part.data['id']
            is_at = True
        else:
            if isinstance(part, OlivOS.messageAPI.PARA.text):
                new_tmp_reast_str_parts.append(part.data['text'])
    
    # 返回解析结果
    cleaned_message = ''.join(new_tmp_reast_str_parts).strip()
    return is_at, at_user_id, cleaned_message

def check_permission(plugin_event):
    """检查权限（包括授权用户）"""
    flag_is_from_group_admin = False
    flag_is_from_master = False
    flag_is_from_admin_user = False
    
    if plugin_event.plugin_info['func_type'] == 'group_message':
        if 'role' in plugin_event.data.sender:
            if plugin_event.data.sender['role'] in ['owner', 'admin']:
                flag_is_from_group_admin = True
    
    flag_is_from_master = OlivaDiceCore.ordinaryInviteManager.isInMasterList(
        plugin_event.bot_info.hash,
        OlivaDiceCore.userConfig.getUserHash(
            plugin_event.data.user_id,
            'user',
            plugin_event.platform['platform']
        )
    )
    
    # 检查是否为授权用户
    config = load_config(plugin_event.bot_info.hash)
    admin_users = config.get('admin_users', {})
    user_hash = OlivaDiceCore.userConfig.getUserHash(
        plugin_event.data.user_id,
        'user',
        plugin_event.platform['platform']
    )
    # 兼容新旧格式
    if isinstance(admin_users, dict):
        if user_hash in admin_users:
            flag_is_from_admin_user = True
    elif isinstance(admin_users, list):
        if user_hash in admin_users:
            flag_is_from_admin_user = True
    
    return flag_is_from_group_admin or flag_is_from_master or flag_is_from_admin_user

def check_master_permission(plugin_event):
    """检查是否为骰主"""
    return OlivaDiceCore.ordinaryInviteManager.isInMasterList(
        plugin_event.bot_info.hash,
        OlivaDiceCore.userConfig.getUserHash(
            plugin_event.data.user_id,
            'user',
            plugin_event.platform['platform']
        )
    )

def format_inventory(inventory):
    """格式化背包内容"""
    if not inventory:
        return "无物品"
    
    items = []
    for item, count in inventory.items():
        items.append(f"{item} x{count}")
    
    return "\n".join(items)

def format_shop_list(shop_items):
    """格式化商店列表"""
    if not shop_items:
        return "无商品"
    
    items = []
    for item, info in shop_items.items():
        items.append(f"{item} - {info['price']}贡献值 ({info['description']})")
    
    return "\n".join(items)

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
        
        # 此频道关闭时中断处理
        if not flag_hostLocalEnable and not flag_force_reply:
            return
        # 此群关闭时中断处理
        if not flag_groupEnable and not flag_force_reply:
            return
        
        '''命令处理开始'''
        if isMatchWordStart(tmp_reast_str, ['bag'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['bag'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            
            # 用户第一次使用bag命令时，自动初始化用户数据文件
            load_user_data(plugin_event.bot_info.hash, plugin_event.data.user_id, plugin_event.platform['platform'], auto_init=True)
            
            # 贡献值命令
            if isMatchWordStart(tmp_reast_str, ['贡献值'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['贡献值'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)

                # 查询贡献值
                if not tmp_reast_str.strip():
                    # 查询自己的贡献值
                    user_data = load_user_data(plugin_event.bot_info.hash, plugin_event.data.user_id, plugin_event.platform['platform'])
                    dictTValue['tContribution'] = str(user_data['contribution'])
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strContributionQuery'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                # 增加/减少/扣除贡献值
                if isMatchWordStart(tmp_reast_str, '增加'):
                    if not check_permission(plugin_event):
                        replyMsg(plugin_event, dictStrCustom['strPermissionDenied'])
                        return

                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '增加')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)

                    # 解析数量和@用户
                    is_at, at_user_id, cleaned_message = parse_at_user(plugin_event, tmp_reast_str)

                    if not is_at or not at_user_id:
                        replyMsg(plugin_event, dictStrCustom['strNoTarget'])
                        return

                    # 提取数量
                    import re
                    numbers = re.findall(r'\d+', cleaned_message)
                    if not numbers:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    amount = int(numbers[0])
                    if amount <= 0:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    user_data = load_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'])
                    user_data['contribution'] += amount
                    save_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'], user_data)

                    dictTValue['tTargetName'] = get_user_name(plugin_event, at_user_id)
                    dictTValue['tAmount'] = str(amount)
                    dictTValue['tContribution'] = str(user_data['contribution'])
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strContributionAdd'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                elif isMatchWordStart(tmp_reast_str, '减少'):
                    if not check_permission(plugin_event):
                        replyMsg(plugin_event, dictStrCustom['strPermissionDenied'])
                        return

                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '减少')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)

                    # 解析数量和@用户
                    is_at, at_user_id, cleaned_message = parse_at_user(plugin_event, tmp_reast_str)

                    if not is_at or not at_user_id:
                        replyMsg(plugin_event, dictStrCustom['strNoTarget'])
                        return

                    # 提取数量
                    import re
                    numbers = re.findall(r'\d+', cleaned_message)
                    if not numbers:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    amount = int(numbers[0])
                    if amount <= 0:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    user_data = load_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'])
                    user_data['contribution'] -= amount
                    if user_data['contribution'] < 0:
                        user_data['contribution'] = 0
                    save_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'], user_data)

                    dictTValue['tTargetName'] = get_user_name(plugin_event, at_user_id)
                    dictTValue['tAmount'] = str(amount)
                    dictTValue['tContribution'] = str(user_data['contribution'])
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strContributionReduce'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                elif isMatchWordStart(tmp_reast_str, '扣除'):
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '扣除')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)

                    # 提取数量
                    import re
                    numbers = re.findall(r'\d+', tmp_reast_str)
                    if not numbers:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    amount = int(numbers[0])
                    if amount <= 0:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    user_data = load_user_data(plugin_event.bot_info.hash, plugin_event.data.user_id, plugin_event.platform['platform'])
                    if user_data['contribution'] < amount:
                        dictTValue['tRequired'] = str(amount)
                        dictTValue['tCurrent'] = str(user_data['contribution'])
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strContributionInsufficient'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        return

                    user_data['contribution'] -= amount
                    save_user_data(plugin_event.bot_info.hash, plugin_event.data.user_id, plugin_event.platform['platform'], user_data)

                    dictTValue['tAmount'] = str(amount)
                    dictTValue['tContribution'] = str(user_data['contribution'])
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strContributionDeduct'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                else:
                    # 最后检查是否为查询他人贡献值
                    is_at, at_user_id, cleaned_message = parse_at_user(plugin_event, tmp_reast_str)

                    if is_at and at_user_id:
                        # 查询他人的贡献值
                        if not check_permission(plugin_event):
                            replyMsg(plugin_event, dictStrCustom['strPermissionDenied'])
                            return

                        user_data = load_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'])
                        dictTValue['tTargetName'] = get_user_name(plugin_event, at_user_id)
                        dictTValue['tContribution'] = str(user_data['contribution'])
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strContributionQueryOther'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        return
                    else:
                        replyMsg(plugin_event, dictStrCustom['strInvalidCommand'])
                        return

            # 背包命令
            elif isMatchWordStart(tmp_reast_str, ['背包'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['背包'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)

                # 查询背包
                if not tmp_reast_str.strip():
                    # 查询自己的背包
                    user_data = load_user_data(plugin_event.bot_info.hash, plugin_event.data.user_id, plugin_event.platform['platform'])
                    inventory_text = format_inventory(user_data['inventory'])
                    dictTValue['tInventory'] = inventory_text
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strInventoryQuery'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                # 添加/删除物品
                if isMatchWordStart(tmp_reast_str, '添加'):
                    if not check_permission(plugin_event):
                        replyMsg(plugin_event, dictStrCustom['strPermissionDenied'])
                        return

                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '添加')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)

                    # 解析物品名、数量和@用户
                    is_at, at_user_id, cleaned_message = parse_at_user(plugin_event, tmp_reast_str)

                    if not is_at or not at_user_id:
                        replyMsg(plugin_event, dictStrCustom['strNoTarget'])
                        return

                    # 提取物品名和数量
                    import re
                    parts = cleaned_message.split()
                    if len(parts) < 2:
                        replyMsg(plugin_event, dictStrCustom['strInvalidCommand'])
                        return

                    item_name = parts[0]
                    try:
                        amount = int(parts[1])
                    except:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    if amount <= 0:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    user_data = load_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'])
                    if item_name not in user_data['inventory']:
                        user_data['inventory'][item_name] = 0
                    user_data['inventory'][item_name] += amount
                    save_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'], user_data)

                    dictTValue['tTargetName'] = get_user_name(plugin_event, at_user_id)
                    dictTValue['tItem'] = item_name
                    dictTValue['tAmount'] = str(amount)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strItemAdd'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                elif isMatchWordStart(tmp_reast_str, '删除'):
                    if not check_permission(plugin_event):
                        replyMsg(plugin_event, dictStrCustom['strPermissionDenied'])
                        return

                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '删除')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)

                    # 解析物品名、数量和@用户
                    is_at, at_user_id, cleaned_message = parse_at_user(plugin_event, tmp_reast_str)

                    if not is_at or not at_user_id:
                        replyMsg(plugin_event, dictStrCustom['strNoTarget'])
                        return

                    # 提取物品名和数量
                    import re
                    parts = cleaned_message.split()
                    if len(parts) < 2:
                        replyMsg(plugin_event, dictStrCustom['strInvalidCommand'])
                        return

                    item_name = parts[0]
                    try:
                        amount = int(parts[1])
                    except:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    if amount <= 0:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    user_data = load_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'])
                    if item_name not in user_data['inventory'] or user_data['inventory'][item_name] < amount:
                        dictTValue['tTargetName'] = get_user_name(plugin_event, at_user_id)
                        dictTValue['tItem'] = item_name
                        dictTValue['tCurrent'] = str(user_data['inventory'].get(item_name, 0))
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strItemNotEnough'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        return

                    user_data['inventory'][item_name] -= amount
                    if user_data['inventory'][item_name] <= 0:
                        del user_data['inventory'][item_name]
                    save_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'], user_data)

                    dictTValue['tTargetName'] = get_user_name(plugin_event, at_user_id)
                    dictTValue['tItem'] = item_name
                    dictTValue['tAmount'] = str(amount)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strItemRemove'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                # 全体发放/删除
                elif isMatchWordStart(tmp_reast_str, '全体发放'):
                    if not check_permission(plugin_event):
                        replyMsg(plugin_event, dictStrCustom['strPermissionDenied'])
                        return

                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '全体发放')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)

                    # 提取物品名和数量
                    import re
                    parts = tmp_reast_str.split()
                    if len(parts) < 2:
                        replyMsg(plugin_event, dictStrCustom['strInvalidCommand'])
                        return

                    item_name = parts[0]
                    try:
                        amount = int(parts[1])
                    except:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    if amount <= 0:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    # 获取群成员列表
                    if plugin_event.plugin_info['func_type'] == 'group_message':
                        try:
                            member_list = plugin_event.get_group_member_list(plugin_event.data.group_id)
                            if member_list and 'data' in member_list:
                                for member in member_list['data']:
                                    user_id = member['user_id']
                                    user_data = load_user_data(plugin_event.bot_info.hash, user_id, plugin_event.platform['platform'])
                                    if item_name not in user_data['inventory']:
                                        user_data['inventory'][item_name] = 0
                                    user_data['inventory'][item_name] += amount
                                    save_user_data(plugin_event.bot_info.hash, user_id, plugin_event.platform['platform'], user_data)
                        except:
                            pass
                        
                    dictTValue['tItem'] = item_name
                    dictTValue['tAmount'] = str(amount)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strGlobalItemAdd'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                elif isMatchWordStart(tmp_reast_str, '全体删除'):
                    if not check_permission(plugin_event):
                        replyMsg(plugin_event, dictStrCustom['strPermissionDenied'])
                        return

                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '全体删除')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)

                    # 提取物品名和数量
                    import re
                    parts = tmp_reast_str.split()
                    if len(parts) < 2:
                        replyMsg(plugin_event, dictStrCustom['strInvalidCommand'])
                        return

                    item_name = parts[0]
                    try:
                        amount = int(parts[1])
                    except:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    if amount <= 0:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                    skip_count = 0
                    # 获取群成员列表
                    if plugin_event.plugin_info['func_type'] == 'group_message':
                        try:
                            member_list = plugin_event.get_group_member_list(plugin_event.data.group_id)
                            if member_list and 'data' in member_list:
                                for member in member_list['data']:
                                    user_id = member['user_id']
                                    user_data = load_user_data(plugin_event.bot_info.hash, user_id, plugin_event.platform['platform'])
                                    if item_name not in user_data['inventory'] or user_data['inventory'][item_name] < amount:
                                        skip_count += 1
                                        continue
                                    user_data['inventory'][item_name] -= amount
                                    if user_data['inventory'][item_name] <= 0:
                                        del user_data['inventory'][item_name]
                                    save_user_data(plugin_event.bot_info.hash, user_id, plugin_event.platform['platform'], user_data)
                        except:
                            pass
                        
                    dictTValue['tItem'] = item_name
                    dictTValue['tAmount'] = str(amount)
                    dictTValue['tSkipCount'] = str(skip_count)
                    if skip_count > 0:
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strGlobalItemRemoveSkip'], dictTValue)
                    else:
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strGlobalItemRemove'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                else:
                    # 最后检查是否为查询他人背包
                    is_at, at_user_id, cleaned_message = parse_at_user(plugin_event, tmp_reast_str)

                    if is_at and at_user_id:
                        # 查询他人的背包
                        if not check_permission(plugin_event):
                            replyMsg(plugin_event, dictStrCustom['strPermissionDenied'])
                            return

                        user_data = load_user_data(plugin_event.bot_info.hash, at_user_id, plugin_event.platform['platform'])
                        inventory_text = format_inventory(user_data['inventory'])
                        dictTValue['tTargetName'] = get_user_name(plugin_event, at_user_id)
                        dictTValue['tInventory'] = inventory_text
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strInventoryQueryOther'], dictTValue)
                        replyMsg(plugin_event, tmp_reply_str)
                        return
                    else:
                        replyMsg(plugin_event, dictStrCustom['strInvalidCommand'])
                        return

            # 商店命令
            elif isMatchWordStart(tmp_reast_str, ['商店'], isCommand=True):
                config = load_config(plugin_event.bot_info.hash)
                shop_items = config.get('shop_items', {})
                shop_text = format_shop_list(shop_items)
                dictTValue['tShopList'] = shop_text
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strShopList'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return

            # 购买命令
            elif isMatchWordStart(tmp_reast_str, ['购买'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['购买'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)

                # 提取物品名和数量
                import re
                parts = tmp_reast_str.split()
                if len(parts) < 1:
                    replyMsg(plugin_event, dictStrCustom['strInvalidCommand'])
                    return

                item_name = parts[0]
                amount = 1
                if len(parts) > 1:
                    try:
                        amount = int(parts[1])
                    except:
                        replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                        return

                if amount <= 0:
                    replyMsg(plugin_event, dictStrCustom['strInvalidAmount'])
                    return

                config = load_config(plugin_event.bot_info.hash)
                shop_items = config.get('shop_items', {})

                if item_name not in shop_items:
                    dictTValue['tItem'] = item_name
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strItemNotInShop'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                total_cost = shop_items[item_name]['price'] * amount
                user_data = load_user_data(plugin_event.bot_info.hash, plugin_event.data.user_id, plugin_event.platform['platform'])

                if user_data['contribution'] < total_cost:
                    dictTValue['tRequired'] = str(total_cost)
                    dictTValue['tCurrent'] = str(user_data['contribution'])
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strContributionInsufficient'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                user_data['contribution'] -= total_cost
                if item_name not in user_data['inventory']:
                    user_data['inventory'][item_name] = 0
                user_data['inventory'][item_name] += amount
                save_user_data(plugin_event.bot_info.hash, plugin_event.data.user_id, plugin_event.platform['platform'], user_data)

                dictTValue['tItem'] = item_name
                dictTValue['tAmount'] = str(amount)
                dictTValue['tCost'] = str(total_cost)
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPurchaseSuccess'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return

            # 使用命令
            elif isMatchWordStart(tmp_reast_str, ['使用'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['使用'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)

                # 提取物品名（剩余的就是物品名+参数）
                if not tmp_reast_str.strip():
                    replyMsg(plugin_event, dictStrCustom['strInvalidCommand'])
                    return

                # 直接取第一个词作为物品名
                parts = tmp_reast_str.split()
                item_name = parts[0]
                
                user_data = load_user_data(plugin_event.bot_info.hash, plugin_event.data.user_id, plugin_event.platform['platform'])

                if item_name not in user_data['inventory'] or user_data['inventory'][item_name] <= 0:
                    dictTValue['tItem'] = item_name
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strItemNotInInventory'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                # 处理道具盲盒
                if item_name == '道具盲盒':
                    # 盲盒系统，提取后续参数（单抽/五连/十连）
                    handle_blindbox(plugin_event, Proc, '道具盲盒', user_data, dictTValue, dictStrCustom, replyMsg, tmp_reast_str)
                    return

                # 其他道具暂时无法使用
                dictTValue['tItem'] = item_name
                dictTValue['tReason'] = '该道具暂无使用功能'
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strItemNotUsable'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return

            # 权限管理命令
            elif isMatchWordStart(tmp_reast_str, ['权限'], isCommand=True):
                if not check_master_permission(plugin_event):
                    replyMsg(plugin_event, dictStrCustom['strOnlyMasterCanGrant'])
                    return

                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['权限'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)

                # 授予权限
                if isMatchWordStart(tmp_reast_str, '授予'):
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '授予')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)

                    # 解析@用户
                    is_at, at_user_id, cleaned_message = parse_at_user(plugin_event, tmp_reast_str)

                    if not is_at or not at_user_id:
                        replyMsg(plugin_event, dictStrCustom['strNoTarget'])
                        return

                    # 获取用户hash
                    user_hash = OlivaDiceCore.userConfig.getUserHash(
                        at_user_id,
                        'user',
                        plugin_event.platform['platform']
                    )

                    # 获取用户名
                    user_name = get_user_name(plugin_event, at_user_id)

                    # 加载配置
                    config = load_config(plugin_event.bot_info.hash)
                    if 'admin_users' not in config:
                        config['admin_users'] = {}

                    # 添加到授权列表（存储为字典，包含user_id和user_name）
                    if user_hash not in config['admin_users']:
                        config['admin_users'][user_hash] = {
                            'user_id': str(at_user_id),
                            'user_name': user_name,
                            'platform': plugin_event.platform['platform']
                        }
                        save_config(plugin_event.bot_info.hash, config)

                    dictTValue['tTargetName'] = user_name
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPermissionGranted'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                # 撤销权限
                elif isMatchWordStart(tmp_reast_str, '撤销'):
                    tmp_reast_str = getMatchWordStartRight(tmp_reast_str, '撤销')
                    tmp_reast_str = skipSpaceStart(tmp_reast_str)

                    # 解析@用户
                    is_at, at_user_id, cleaned_message = parse_at_user(plugin_event, tmp_reast_str)

                    if not is_at or not at_user_id:
                        replyMsg(plugin_event, dictStrCustom['strNoTarget'])
                        return

                    # 获取用户hash
                    user_hash = OlivaDiceCore.userConfig.getUserHash(
                        at_user_id,
                        'user',
                        plugin_event.platform['platform']
                    )

                    # 加载配置
                    config = load_config(plugin_event.bot_info.hash)
                    if 'admin_users' not in config:
                        config['admin_users'] = {}

                    # 从授权列表移除
                    if user_hash in config['admin_users']:
                        del config['admin_users'][user_hash]
                        save_config(plugin_event.bot_info.hash, config)

                    dictTValue['tTargetName'] = get_user_name(plugin_event, at_user_id)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPermissionRevoked'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                # 列表权限
                elif isMatchWordStart(tmp_reast_str, '列表'):
                    # 加载配置
                    config = load_config(plugin_event.bot_info.hash)
                    admin_users = config.get('admin_users', {})

                    if not admin_users:
                        replyMsg(plugin_event, dictStrCustom['strPermissionListEmpty'])
                        return

                    # 格式化显示：用户名 (user_id) [hash]
                    admin_list_lines = []
                    for user_hash, user_info in admin_users.items():
                        if isinstance(user_info, dict):
                            # 新格式：包含详细信息
                            user_name = user_info.get('user_name', '未知')
                            user_id = user_info.get('user_id', '未知')
                            platform = user_info.get('platform', '未知')
                            admin_list_lines.append(f"- {user_name} (ID:{user_id}) [{user_hash}]")
                        else:
                            # 旧格式兼容：只有hash
                            admin_list_lines.append(f"- {user_hash}")

                    admin_list_text = "\n".join(admin_list_lines)

                    dictTValue['tAdminList'] = admin_list_text
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPermissionList'], dictTValue)
                    replyMsg(plugin_event, tmp_reply_str)
                    return

                else:
                    replyMsg(plugin_event, dictStrCustom['strInvalidCommand'])
                    return
        
            else:
                OlivaDiceCore.msgReply.replyMsgLazyHelpByEvent(plugin_event, 'bag')

def handle_blindbox(plugin_event, Proc, item_name, user_data, dictTValue, dictStrCustom, replyMsg, full_command_str):
    """处理盲盒系统"""
    # 用户输入命令映射：默认单抽
    COMMAND_MAP = {
        "": "单抽",
        "单抽": "单抽",
        "五连抽": "五连抽",
        "五连": "五连抽",
        "十连抽": "十连抽",
        "十连": "十连抽",
        "模拟一万连": "模拟一万连",
    }
    
    # 从完整命令中提取参数（跳过"道具盲盒"这个词）
    parts = full_command_str.split()
    if len(parts) > 1:
        suffix = parts[1]  # 获取"道具盲盒"后面的参数
    else:
        suffix = ""  # 默认单抽
    
    user_choice = COMMAND_MAP.get(suffix)
    
    if not user_choice:
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strBlindboxInvalidCommand'], dictTValue)
        replyMsg(plugin_event, tmp_reply_str)
        return
    
    # 加载盲盒配置
    config = load_config(plugin_event.bot_info.hash)
    blindbox_config = config.get('blindbox_config', {})
    prizes = blindbox_config.get('prizes', [])
    
    # 检查概率配置
    total_weight = sum(prize['weight'] for prize in prizes)
    if abs(total_weight - 100.0) > 0.01:
        dictTValue['tTotal'] = str(total_weight)
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strBlindboxWeightError'], dictTValue)
        replyMsg(plugin_event, tmp_reply_str)
        return
    
    def draw_prize():
        """随机抽奖，返回奖品对象"""
        prize_list = []
        for prize in prizes:
            prize_list.append(prize)
        weights = [p['weight'] for p in prize_list]
        return random.choices(prize_list, weights=weights, k=1)[0]
    
    def add_to_inventory(user_data, item, count=1):
        """将道具加入库存"""
        if item not in user_data['inventory']:
            user_data['inventory'][item] = 0
        user_data['inventory'][item] += count
    
    def process_prize(prize_obj, user_data):
        """
        处理单次抽奖，返回 (显示文案, 特殊文案)
        """
        item_name = prize_obj['name']
        special_msg = prize_obj.get('message', '')
        
        # 直接加入库存
        add_to_inventory(user_data, item_name, 1)
        
        return item_name, special_msg if special_msg else None
    
    # 模拟一万连抽（仅限骰主权限）
    if user_choice == "模拟一万连":
        if not OlivaDiceCore.ordinaryInviteManager.isInMasterList(
            plugin_event.bot_info.hash,
            OlivaDiceCore.userConfig.getUserHash(
                plugin_event.data.user_id,
                'user',
                plugin_event.platform['platform']
            )
        ):
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strPermissionDenied'], dictTValue)
            replyMsg(plugin_event, tmp_reply_str)
            return
        
        sim_results = [draw_prize()['name'] for _ in range(10000)]
        sim_summary = {}
        for p in sim_results:
            sim_summary[p] = sim_summary.get(p, 0) + 1
        
        sim_msg = "\n".join(f"{k} x{v}" for k, v in sim_summary.items())
        dictTValue['tResult'] = sim_msg
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strBlindboxSimulation'], dictTValue)
        replyMsg(plugin_event, tmp_reply_str)
        return
    
    # 确定抽奖次数
    draw_count = 1 if user_choice == "单抽" else (5 if user_choice == "五连抽" else 10)
    
    if user_data['inventory'].get('道具盲盒', 0) < draw_count:
        dictTValue['tCount'] = str(draw_count)
        dictTValue['tType'] = user_choice
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strBlindboxNotEnough'], dictTValue)
        replyMsg(plugin_event, tmp_reply_str)
        return
    
    # 执行抽奖
    result_summary = {}  # 格式：{物品名: {"count": 数量, "msg": 特殊文案}}
    for _ in range(draw_count):
        prize_obj = draw_prize()
        item_name, special_msg = process_prize(prize_obj, user_data)
        if item_name not in result_summary:
            result_summary[item_name] = {"count": 0, "msg": special_msg}
        result_summary[item_name]["count"] += 1
    
    user_data['inventory']['道具盲盒'] -= draw_count
    save_user_data(plugin_event.bot_info.hash, plugin_event.data.user_id, plugin_event.platform['platform'], user_data)
    
    # 生成输出文案
    output_lines = []
    
    for item_name, info in result_summary.items():
        output_lines.append(f"· {item_name} x {info['count']}")
        if info["msg"]:
            output_lines.append(info["msg"])
    
    output_msg = "\n".join(output_lines)
    dictTValue['tResult'] = output_msg
    if draw_count == 1:
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strBlindboxDraw'], dictTValue)
    else:
        dictTValue['tCount'] = str(draw_count)
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strBlindboxDrawMultiple'], dictTValue)
    replyMsg(plugin_event, tmp_reply_str)
