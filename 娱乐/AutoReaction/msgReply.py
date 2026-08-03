# -*- encoding: utf-8 -*-
'''
QQ号检测表情回复插件
前置插件：OlivaDiceCore
功能：当检测到指定QQ号发送消息时，自动回复多个指定表情
支持三种表情API接口自动切换
'''

import OlivOS
import OlivaDiceCore
import json
import os
import requests
from pathlib import Path

# 全局变量存储Proc对象
globalProc = None

# 数据存储路径（基础路径）
BASE_DATA_PATH = "plugin/data/AutoReaction"

def get_data_path(bot_hash):
    """根据bot_hash获取数据存储路径"""
    return os.path.join(BASE_DATA_PATH, bot_hash)

def get_old_data_path():
    """获取旧版本的数据存储路径（用于兼容性迁移）"""
    return BASE_DATA_PATH

def get_config_file(bot_hash):
    """获取配置文件路径"""
    return os.path.join(get_data_path(bot_hash), "config.json")

def get_whitelist_file(bot_hash):
    """获取白名单文件路径"""
    return os.path.join(get_data_path(bot_hash), "whitelist.json")

def get_protocol_file(bot_hash):
    """获取协议文件路径"""
    return os.path.join(get_data_path(bot_hash), "protocol.json")

def ensure_data_dir(bot_hash):
    """确保数据目录存在"""
    data_path = get_data_path(bot_hash)
    Path(data_path).mkdir(parents=True, exist_ok=True)

def load_json_file(file_path, default={}):
    """加载JSON文件"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"加载文件 {file_path} 失败: {e}")
    return default

def save_json_file(file_path, data):
    """保存JSON文件"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"保存文件 {file_path} 失败: {e}")
        return False

def unity_init(plugin_event, Proc):
    """初始化配置"""
    global globalProc
    globalProc = Proc
    
    # 遍历所有bot进行初始化
    if 'bot_info_dict' in Proc.Proc_data:
        for bot_hash in Proc.Proc_data['bot_info_dict']:
            init_for_bot(bot_hash, Proc)
    
    # 兼容性迁移：如果有旧数据，迁移到新格式
    migrate_old_data(Proc)

def init_for_bot(bot_hash, Proc):
    """为单个bot初始化数据文件"""
    ensure_data_dir(bot_hash)
    
    config_file = get_config_file(bot_hash)
    whitelist_file = get_whitelist_file(bot_hash)
    protocol_file = get_protocol_file(bot_hash)
    
    # 初始化默认配置文件
    if not os.path.exists(config_file):
        default_config = {
            "target_users": {}
        }
        save_json_file(config_file, default_config)
    
    # 初始化白名单文件
    if not os.path.exists(whitelist_file):
        default_whitelist = {
            "whitelist_groups": []
        }
        save_json_file(whitelist_file, default_whitelist)
    
    # 初始化协议文件
    if not os.path.exists(protocol_file):
        default_protocol = {
            "protocol": 1  # 默认使用Lagrange协议
        }
        save_json_file(protocol_file, default_protocol)

def migrate_old_data(Proc):
    """兼容性迁移：将旧版本的数据迁移到新格式（按hash分目录）"""
    old_data_path = get_old_data_path()
    old_config_file = os.path.join(old_data_path, "config.json")
    old_whitelist_file = os.path.join(old_data_path, "whitelist.json")
    old_protocol_file = os.path.join(old_data_path, "protocol.json")
    
    # 检查是否存在旧数据文件
    has_old_data = False
    old_config = None
    old_whitelist = None
    old_protocol = None
    
    # 读取旧数据
    if os.path.exists(old_config_file):
        try:
            old_config = load_json_file(old_config_file)
            if old_config:
                has_old_data = True
        except:
            pass
    
    if os.path.exists(old_whitelist_file):
        try:
            old_whitelist = load_json_file(old_whitelist_file)
            if old_whitelist:
                has_old_data = True
        except:
            pass
    
    if os.path.exists(old_protocol_file):
        try:
            old_protocol = load_json_file(old_protocol_file)
            if old_protocol:
                has_old_data = True
        except:
            pass
    
    # 如果有旧数据，迁移到所有bot
    if has_old_data and 'bot_info_dict' in Proc.Proc_data:
        for bot_hash in Proc.Proc_data['bot_info_dict']:
            config_file = get_config_file(bot_hash)
            whitelist_file = get_whitelist_file(bot_hash)
            protocol_file = get_protocol_file(bot_hash)
            
            # 迁移配置文件
            if old_config and not os.path.exists(config_file):
                save_json_file(config_file, old_config)
                Proc.log(2, f"[AutoReaction] 已为 {bot_hash} 迁移配置文件")
            
            # 迁移白名单文件
            if old_whitelist and not os.path.exists(whitelist_file):
                save_json_file(whitelist_file, old_whitelist)
                Proc.log(2, f"[AutoReaction] 已为 {bot_hash} 迁移白名单文件")
            
            # 迁移协议文件
            if old_protocol and not os.path.exists(protocol_file):
                save_json_file(protocol_file, old_protocol)
                Proc.log(2, f"[AutoReaction] 已为 {bot_hash} 迁移协议文件")
        
        # 迁移完成后，删除旧文件
        try:
            if os.path.exists(old_config_file):
                os.remove(old_config_file)
            if os.path.exists(old_whitelist_file):
                os.remove(old_whitelist_file)
            if os.path.exists(old_protocol_file):
                os.remove(old_protocol_file)
            Proc.log(2, "[AutoReaction] 已删除旧数据文件")
        except Exception as e:
            Proc.log(4, f"[AutoReaction] 删除旧数据文件失败: {e}")

def data_init(plugin_event, Proc):
    """数据初始化"""
    global globalProc
    globalProc = Proc

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

def get_protocol(bot_hash):
    """获取当前使用的协议"""
    protocol_file = get_protocol_file(bot_hash)
    protocol_data = load_json_file(protocol_file)
    return protocol_data.get("protocol", 1)  # 默认为1

def send_reaction_v1(plugin_event, server_config, message_id, reaction_code):
    """Lagrange表情API接口: /set_group_reaction"""
    forward_data = {
        "Type": "Http",
        "Host": server_config["host"].replace("http://", "").replace("https://", ""),
        "Port": server_config["port"],
        "AccessToken": server_config["access_token"]
    }
    
    api_url = f"http://{forward_data['Host']}:{forward_data['Port']}/set_group_reaction"
    payload = {
        "group_id": plugin_event.data.group_id,
        "message_id": message_id,
        "code": reaction_code,
        "is_add": True
    }
    
    headers = {
        "Authorization": f"Bearer {forward_data['AccessToken']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            api_url,
            data=json.dumps(payload),
            headers=headers,
            timeout=5
        )
        return response.status_code == 200
    except Exception:
        return False

def send_reaction_v2(plugin_event, server_config, message_id, reaction_code):
    """NapCat表情API接口: /set_msg_emoji_like (数字ID)"""
    forward_data = {
        "Type": "Http",
        "Host": server_config["host"].replace("http://", "").replace("https://", ""),
        "Port": server_config["port"],
        "AccessToken": server_config["access_token"]
    }
    
    api_url = f"http://{forward_data['Host']}:{forward_data['Port']}/set_msg_emoji_like"
    payload = {
        "message_id": message_id,
        "emoji_id": reaction_code,
        "set": True
    }
    
    headers = {
        "Authorization": f"Bearer {forward_data['AccessToken']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            api_url,
            data=json.dumps(payload),
            headers=headers,
            timeout=5
        )
        return response.status_code == 200
    except (ValueError, Exception):
        return False

def send_reaction_v3(plugin_event, server_config, message_id, reaction_code):
    """LLOneBot表情API接口: /set_msg_emoji_like (字符串ID)"""
    forward_data = {
        "Type": "Http",
        "Host": server_config["host"].replace("http://", "").replace("https://", ""),
        "Port": server_config["port"],
        "AccessToken": server_config["access_token"]
    }
    
    api_url = f"http://{forward_data['Host']}:{forward_data['Port']}/set_msg_emoji_like"
    payload = {
        "message_id": message_id,
        "emoji_id": reaction_code
    }
    
    headers = {
        "Authorization": f"Bearer {forward_data['AccessToken']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            api_url,
            data=json.dumps(payload),
            headers=headers,
            timeout=5
        )
        return response.status_code == 200
    except Exception:
        return False

def send_reactions(plugin_event, server_config, message_id, reaction_codes):
    """根据设置的协议发送表情"""
    protocol = get_protocol(plugin_event.bot_info.hash)
    for code in reaction_codes:
        if protocol == 1:
            if not send_reaction_v1(plugin_event, server_config, message_id, code):
                return False
        elif protocol == 2:
            if not send_reaction_v2(plugin_event, server_config, message_id, code):
                return False
        elif protocol == 3:
            if not send_reaction_v3(plugin_event, server_config, message_id, code):
                return False
        else:
            # 默认使用协议1
            if not send_reaction_v1(plugin_event, server_config, message_id, code):
                return False
    return True

def handle_admin_command(plugin_event, dictTValue, dictStrCustom, tmp_reast_str):
    """处理骰主管理命令"""
    replyMsg = OlivaDiceCore.msgReply.replyMsg
    isMatchWordStart = OlivaDiceCore.msgReply.isMatchWordStart
    getMatchWordStartRight = OlivaDiceCore.msgReply.getMatchWordStartRight
    skipSpaceStart = OlivaDiceCore.msgReply.skipSpaceStart
    
    bot_hash = plugin_event.bot_info.hash
    config_file = get_config_file(bot_hash)
    whitelist_file = get_whitelist_file(bot_hash)
    protocol_file = get_protocol_file(bot_hash)
    
    # 加载配置
    config = load_json_file(config_file)
    whitelist = load_json_file(whitelist_file)
    
    # 设置协议
    if isMatchWordStart(tmp_reast_str, ['回应设置协议'], isCommand=True):
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['回应设置协议'])
        tmp_reast_str = skipSpaceStart(tmp_reast_str)
        
        if not tmp_reast_str.strip():
            # 显示当前协议选项
            replyMsg(plugin_event, 
                "当前支持的协议:\n"
                "1：Lagrange\n"
                "2：NapCat\n"
                "3：LLOneBot/LLTwoBot\n\n"
                "当前使用的协议: " + str(get_protocol(bot_hash)) + "\n"
                "请输入 .回应设置协议 对应序号 来设置对应的协议"
            )
            return True
        
        try:
            protocol_num = int(tmp_reast_str.strip())
            if protocol_num in [1, 2, 3]:
                protocol_data = {"protocol": protocol_num}
                save_json_file(protocol_file, protocol_data)
                replyMsg(plugin_event, f"已设置使用协议 {protocol_num}")
            else:
                replyMsg(plugin_event, "协议序号无效，请输入1、2或3")
        except ValueError:
            replyMsg(plugin_event, "请输入有效的协议序号(1、2或3)")
        return True
    
    # 添加白名单群组
    if isMatchWordStart(tmp_reast_str, ['回应添加白名单群组'], isCommand=True):
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['回应添加白名单群组'])
        tmp_reast_str = skipSpaceStart(tmp_reast_str)
        group_id = tmp_reast_str.strip()
        
        if group_id and group_id not in whitelist["whitelist_groups"]:
            whitelist["whitelist_groups"].append(group_id)
            save_json_file(whitelist_file, whitelist)
            replyMsg(plugin_event, f"已添加群组 {group_id} 到白名单")
        else:
            replyMsg(plugin_event, "群组ID无效或已在白名单中")
        return True
    
    # 移除白名单群组
    if isMatchWordStart(tmp_reast_str, ['回应移除白名单群组'], isCommand=True):
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['回应移除白名单群组'])
        tmp_reast_str = skipSpaceStart(tmp_reast_str)
        group_id = tmp_reast_str.strip()
        
        if group_id and group_id in whitelist["whitelist_groups"]:
            whitelist["whitelist_groups"].remove(group_id)
            save_json_file(whitelist_file, whitelist)
            replyMsg(plugin_event, f"已从白名单移除群组 {group_id}")
        else:
            replyMsg(plugin_event, "群组ID无效或不在白名单中")
        return True
    
    # 添加目标用户
    if isMatchWordStart(tmp_reast_str, ['回应添加用户'], isCommand=True):
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['回应添加用户'])
        tmp_reast_str = skipSpaceStart(tmp_reast_str)
        parts = tmp_reast_str.split(maxsplit=1)
        
        if len(parts) >= 2:
            qq_id = parts[0].strip()
            emojis = parts[1].strip().split()
            
            if qq_id and emojis:
                config["target_users"][qq_id] = emojis
                save_json_file(config_file, config)
                replyMsg(plugin_event, f"已为用户 {qq_id} 添加表情: {' '.join(emojis)}")
            else:
                replyMsg(plugin_event, "命令格式错误，应为: 回应添加用户 QQ号 表情1 表情2 ...")
        else:
            replyMsg(plugin_event, "命令格式错误，应为: 回应添加用户 QQ号 表情1 表情2 ...")
        return True
    
    # 移除目标用户
    if isMatchWordStart(tmp_reast_str, ['回应移除用户'], isCommand=True):
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['回应移除用户'])
        tmp_reast_str = skipSpaceStart(tmp_reast_str)
        qq_id = tmp_reast_str.strip()
        
        if qq_id and qq_id in config["target_users"]:
            del config["target_users"][qq_id]
            save_json_file(config_file, config)
            replyMsg(plugin_event, f"已移除目标用户 {qq_id}")
        else:
            replyMsg(plugin_event, "用户ID无效或不是目标用户")
        return True
    
    # 为用户添加表情
    if isMatchWordStart(tmp_reast_str, ['回应添加表情'], isCommand=True):
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['回应添加表情'])
        tmp_reast_str = skipSpaceStart(tmp_reast_str)
        parts = tmp_reast_str.split(maxsplit=1)
        
        if len(parts) >= 2:
            qq_id = parts[0].strip()
            emojis = parts[1].strip().split()
            
            if qq_id and emojis and qq_id in config["target_users"]:
                config["target_users"][qq_id].extend(emojis)
                save_json_file(config_file, config)
                replyMsg(plugin_event, f"已为用户 {qq_id} 添加表情: {' '.join(emojis)}")
            else:
                replyMsg(plugin_event, "用户ID无效或不是目标用户")
        else:
            replyMsg(plugin_event, "命令格式错误，应为: 回应添加表情 QQ号 表情1 表情2 ...")
        return True
    
    # 为用户移除表情
    if isMatchWordStart(tmp_reast_str, ['回应移除表情'], isCommand=True):
        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['回应移除表情'])
        tmp_reast_str = skipSpaceStart(tmp_reast_str)
        parts = tmp_reast_str.split(maxsplit=1)
        
        if len(parts) >= 2:
            qq_id = parts[0].strip()
            emojis = parts[1].strip().split()
            
            if qq_id and emojis and qq_id in config["target_users"]:
                for emoji in emojis:
                    if emoji in config["target_users"][qq_id]:
                        config["target_users"][qq_id].remove(emoji)
                save_json_file(config_file, config)
                replyMsg(plugin_event, f"已为用户 {qq_id} 移除表情: {' '.join(emojis)}")
            else:
                replyMsg(plugin_event, "用户ID无效或不是目标用户")
        else:
            replyMsg(plugin_event, "命令格式错误，应为: 回应移除表情 QQ号 表情1 表情2 ...")
        return True
    
    # 查看当前配置
    if isMatchWordStart(tmp_reast_str, ['回应查看配置'], isCommand=True):
        whitelist_groups = "\n".join(whitelist["whitelist_groups"]) or "无"
        target_users = "\n".join([f"{k}: {' '.join(v)}" for k, v in config["target_users"].items()]) or "无"
        current_protocol = get_protocol(bot_hash)
        
        replyMsg(plugin_event, 
            f"白名单群组:\n{whitelist_groups}\n\n"
            f"目标用户及表情:\n{target_users}\n\n"
            f"当前使用的协议: {current_protocol}\n"
            f"(1：Lagrange, 2：NapCat, 3：LLOneBot/LLTwoBot)"
        )
        return True
    
    return False

def unity_reply(plugin_event, Proc):
    # 初始化消息处理
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

    def is_master(plugin_event):
        """检查是否是骰骰主"""
        return OlivaDiceCore.ordinaryInviteManager.isInMasterList(
            plugin_event.bot_info.hash,
            OlivaDiceCore.userConfig.getUserHash(
                plugin_event.data.user_id,
                'user',
                plugin_event.platform['platform']
            )
        )
    
    # 处理骰骰主命令
    if flag_is_command and is_master(plugin_event):
        if handle_admin_command(plugin_event, dictTValue, dictStrCustom, tmp_reast_str):
            plugin_event.set_block()
            return
    
    # 检查是否是群消息
    if plugin_event.plugin_info['func_type'] == 'group_message':
        bot_hash = plugin_event.bot_info.hash
        config_file = get_config_file(bot_hash)
        whitelist_file = get_whitelist_file(bot_hash)
        
        # 加载配置
        config = load_json_file(config_file)
        whitelist = load_json_file(whitelist_file)
        
        # 检查是否在白名单群组中
        group_id = str(plugin_event.data.group_id)
        if "whitelist_groups" in whitelist and group_id not in whitelist["whitelist_groups"]:
            return
        
        # 获取发送者QQ号
        sender_id = str(plugin_event.data.user_id)
        
        # 检查是否是目标用户
        if "target_users" in config and sender_id in config["target_users"]:
            # 获取账号配置
            server_config = get_account_config(plugin_event)
            if server_config is None:
                replyMsg(plugin_event, "无法获取账号配置，请检查Bot配置是否正确")
                return
                
            # 发送表情回应
            reaction_codes = config["target_users"][sender_id]
            message_id = plugin_event.data.message_id
            
            if not send_reactions(plugin_event, server_config, message_id, reaction_codes):
                replyMsg(plugin_event, f"检测到目标用户 {sender_id}，但表情回应发送失败")
