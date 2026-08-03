# -*- encoding: utf-8 -*-
'''
吓我一跳我释放忍术！

原作者：凛素子
bilibili空间：https://space.bilibili.com/397472054
发布视频：https://www.bilibili.com/video/BV1CDMGzLEoN/
原koishi项目地址：https://github.com/rinsoko39/koishi-plugin-lex-ninjutsu

本插件移植：Desom-fu
配合蕾忍跑团插件使用更佳：https://forum.olivos.run/d/818
'''

import OlivOS
import OlivaDiceLexNinjutsu
import OlivaDiceCore
import json
import re
import random
import copy
import os
import time

import requests

# 禁用 SSL 警告
try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except:
    pass

# 尝试导入拼音库（可选依赖）
has_pinyin = False
try:
    from pypinyin import lazy_pinyin, Style
    has_pinyin = True
except ImportError:
    has_pinyin = False

# 全局变量，存储忍术数据
g_ninjutsu_data = {}

# 配置参数(默认值)
SOURCE_URL = "https://wsfrs.com"
DEFAULT_MATCH_LEVEL = 1  # 默认匹配等级：普通匹配（忽略标点）
DEFAULT_SEARCH_LIMIT = 10  # 默认搜索结果上限
DEFAULT_DESCRIPTION_PREVIEW_LIMIT = 50  # 默认描述预览字数上限

# 数据存储路径
DATA_DIR = "./plugin/data/OlivaDiceLexNinjutsu"
DATA_FILE = "ninjutsu_data.json"
AUDIO_DIR = "./data/audios/OlivaDiceLexNinjutsu"


def get_config_value(dictStrCustom, key, default_value):
    """从 dictStrCustom 回复词中获取配置值，如果无法转换为int则返回默认值"""
    try:
        value = int(dictStrCustom.get(key, default_value))
        return value
    except (ValueError, TypeError):
        return default_value


def get_match_level(dictStrCustom):
    """获取匹配等级配置，如果有pinyin库则默认为2"""
    default = 2 if has_pinyin else DEFAULT_MATCH_LEVEL
    return get_config_value(dictStrCustom, 'tMatchLevel', default)


def get_search_limit(dictStrCustom):
    """获取搜索结果上限配置"""
    return get_config_value(dictStrCustom, 'tSearchLimit', DEFAULT_SEARCH_LIMIT)


def get_description_preview_limit(dictStrCustom):
    """获取描述预览字数上限配置"""
    return get_config_value(dictStrCustom, 'tDescriptionPreviewLimit', DEFAULT_DESCRIPTION_PREVIEW_LIMIT)

def unity_init(plugin_event, Proc):
    # 插件初始化
    # 创建数据目录
    init_data_directory(Proc)
    # 加载本地数据
    load_ninjutsu_data(Proc)

def data_init(plugin_event, Proc):
    # 数据初始化，加载自定义回复
    OlivaDiceLexNinjutsu.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

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
    to_half_width = OlivaDiceCore.msgReply.to_half_width

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
        
        # 命令处理开始
        bot_hash = plugin_event.bot_info.hash
        
        # 主命令：.忍术
        if isMatchWordStart(tmp_reast_str, ['忍术', 'ninjutsu'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['忍术', 'ninjutsu'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')
            
            # 子命令：更新
            if isMatchWordStart(tmp_reast_str, ['更新', 'update']):
                if not flag_is_from_master:
                    return
                try:
                    count = update_ninjutsu_database(bot_hash, Proc)
                    dictTValue['tNinjutsuCount'] = str(count)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strNinjutsuUpdateComplete'], 
                        dictTValue
                    )
                    replyMsg(plugin_event, tmp_reply_str)
                except Exception as e:
                    dictTValue['tError'] = str(e)
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strNinjutsuUpdateError'], 
                        dictTValue
                    )
                    replyMsg(plugin_event, tmp_reply_str)
                return
            
            # 子命令：清空
            elif isMatchWordStart(tmp_reast_str, ['清空', 'clear']):
                if not flag_is_from_master:
                    return
                clear_ninjutsu_database(bot_hash, Proc)
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                    dictStrCustom['strNinjutsuClearComplete'], 
                    dictTValue
                )
                replyMsg(plugin_event, tmp_reply_str)
                return
            
            # 子命令：信息
            elif isMatchWordStart(tmp_reast_str, ['信息', 'info']):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['信息', 'info'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                tmp_reast_str = tmp_reast_str.rstrip(' ')
                
                if tmp_reast_str == '':
                    return
                
                # 获取配置参数
                match_level = get_match_level(dictStrCustom)
                search_limit = get_search_limit(dictStrCustom)
                description_preview_limit = get_description_preview_limit(dictStrCustom)
                
                ninjutsu = find_ninjutsu(bot_hash, tmp_reast_str, match_level)
                if ninjutsu is None:
                    search_results = search_ninjutsu(bot_hash, tmp_reast_str, search_limit, match_level)
                    if len(search_results) == 0:
                        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                            dictStrCustom['strNinjutsuNotFound'], 
                            dictTValue
                        )
                        replyMsg(plugin_event, tmp_reply_str)
                    else:
                        result_str = build_search_result_string(search_results, dictStrCustom, dictTValue, description_preview_limit)
                        replyMsg(plugin_event, result_str)
                else:
                    dictTValue['tNinjutsuName'] = ninjutsu['name']
                    dictTValue['tNinjutsuDescription'] = ninjutsu['description']
                    dictTValue['tNinjutsuUrl'] = f"{SOURCE_URL}/jutsus/{ninjutsu['id']}"
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strNinjutsuInfo'], 
                        dictTValue
                    )
                    replyMsg(plugin_event, tmp_reply_str)
                return
            
            # 子命令：释放
            elif isMatchWordStart(tmp_reast_str, ['释放', 'release']):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['释放', 'release'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                tmp_reast_str = tmp_reast_str.rstrip(' ')
                
                handle_ninjutsu_release(plugin_event, tmp_reast_str, bot_hash, dictStrCustom, dictTValue, replyMsg)
                return
            
            # 子命令：搜索
            elif isMatchWordStart(tmp_reast_str, ['搜索', 'search']):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['搜索', 'search'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                tmp_reast_str = tmp_reast_str.rstrip(' ')
                
                if tmp_reast_str == '':
                    return
                
                # 获取配置参数
                match_level = get_match_level(dictStrCustom)
                search_limit = get_search_limit(dictStrCustom)
                description_preview_limit = get_description_preview_limit(dictStrCustom)
                
                search_results = search_ninjutsu(bot_hash, tmp_reast_str, search_limit, match_level)
                if len(search_results) == 0:
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strNinjutsuSearchNoResult'], 
                        dictTValue
                    )
                    replyMsg(plugin_event, tmp_reply_str)
                else:
                    result_str = build_search_result_string(search_results, dictStrCustom, dictTValue, description_preview_limit)
                    replyMsg(plugin_event, result_str)
                return
            
            # 子命令：下载
            elif isMatchWordStart(tmp_reast_str, ['下载', 'download']):
                if not flag_is_from_master:
                    return
                
                handle_ninjutsu_download_all(plugin_event, bot_hash, dictStrCustom, dictTValue, replyMsg, Proc)
                return
            
            # 子命令：配置
            elif isMatchWordStart(tmp_reast_str, ['配置', 'config']):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['配置', 'config'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                tmp_reast_str = tmp_reast_str.rstrip(' ')
                
                # 如果没有参数，显示当前配置
                if tmp_reast_str == '':
                    match_level = get_match_level(dictStrCustom)
                    search_limit = get_search_limit(dictStrCustom)
                    description_preview_limit = get_description_preview_limit(dictStrCustom)
                    
                    match_level_name = ['严格匹配', '忽略标点匹配', '同音匹配'][min(match_level, 2)]
                    
                    tmp_dict = dictTValue.copy()
                    tmp_dict['tMatchLevel'] = f"{match_level} ({match_level_name})"
                    tmp_dict['tSearchLimit'] = str(search_limit)
                    tmp_dict['tDescriptionPreviewLimit'] = str(description_preview_limit)
                    
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strNinjutsuConfigInfo'], 
                        tmp_dict
                    )
                    replyMsg(plugin_event, tmp_reply_str)
                return
        
        # 别名：.释放忍术
        elif isMatchWordStart(tmp_reast_str, ['释放忍术'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['释放忍术'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
            tmp_reast_str = tmp_reast_str.rstrip(' ')
            
            handle_ninjutsu_release(plugin_event, tmp_reast_str, bot_hash, dictStrCustom, dictTValue, replyMsg)
            return


# 工具函数

def init_data_directory(Proc):
    """初始化数据目录"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        Proc.log(2, f"[OlivaDiceLexNinjutsu] 已创建数据目录: {DATA_DIR}")
    if not os.path.exists(AUDIO_DIR):
        os.makedirs(AUDIO_DIR)
        Proc.log(2, f"[OlivaDiceLexNinjutsu] 已创建音频目录: {AUDIO_DIR}")

def get_data_file_path():
    """获取数据文件完整路径"""
    return os.path.join(DATA_DIR, DATA_FILE)

def load_ninjutsu_data(Proc):
    """从本地JSON文件加载忍术数据"""
    global g_ninjutsu_data
    
    data_file_path = get_data_file_path()
    if os.path.exists(data_file_path):
        try:
            with open(data_file_path, 'r', encoding='utf-8') as f:
                g_ninjutsu_data = json.load(f)
            Proc.log(2, f"[OlivaDiceLexNinjutsu] 已从本地加载忍术数据")
        except Exception as e:
            Proc.log(2, f"[OlivaDiceLexNinjutsu] 加载数据失败: {str(e)}")
            g_ninjutsu_data = {}
    else:
        Proc.log(2, f"[OlivaDiceLexNinjutsu] 本地数据文件不存在，将在首次更新后创建")
        g_ninjutsu_data = {}

def save_ninjutsu_data(Proc):
    """保存忍术数据到本地JSON文件"""
    global g_ninjutsu_data
    
    data_file_path = get_data_file_path()
    try:
        with open(data_file_path, 'w', encoding='utf-8') as f:
            json.dump(g_ninjutsu_data, f, ensure_ascii=False, indent=2)
        Proc.log(2, f"[OlivaDiceLexNinjutsu] 已保存忍术数据到: {data_file_path}")
        return True
    except Exception as e:
        Proc.log(2, f"[OlivaDiceLexNinjutsu] 保存数据失败: {str(e)}")
        return False

def get_pinyin(text):
    """获取文本的拼音（如果拼音库可用）"""
    if has_pinyin:
        # 使用pypinyin获取拼音，不带音调
        pinyin_list = lazy_pinyin(text, style=Style.NORMAL)
        return ''.join(pinyin_list).lower()
    else:
        # 如果没有拼音库，返回原文本
        return text

def remove_punctuation(s):
    """移除字符串中的标点符号"""
    # 移除所有标点、符号和空白字符
    import string
    # 中文标点
    chinese_punctuation = '，。！？；：""''（）【】《》、·…—'
    # 所有要移除的字符
    all_punctuation = string.punctuation + chinese_punctuation + ' \t\n\r'
    # 创建翻译表
    translator = str.maketrans('', '', all_punctuation)
    return s.translate(translator)

def update_ninjutsu_database(bot_hash, Proc):
    """从忍法帖更新忍术数据"""
    global g_ninjutsu_data
    
    try:
        # 使用 requests 库
        # 先获取总数
        url = f"{SOURCE_URL}/api/jutsus"
        response = requests.get(url, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        total = data['pagination']['total']
        
        # 获取所有数据
        url_all = f"{SOURCE_URL}/api/jutsus?limit={total}"
        response = requests.get(url_all, timeout=30, verify=False)
        response.raise_for_status()
        data = response.json()
        jutsus = data['jutsus']
        
        # 存储到全局变量
        if bot_hash not in g_ninjutsu_data:
            g_ninjutsu_data[bot_hash] = {}
        
        g_ninjutsu_data[bot_hash] = {}
        for jutsu in jutsus:
            name_no_punct = remove_punctuation(jutsu['name'])
            jutsu_info = {
                'id': jutsu['id'],
                'name': jutsu['name'],
                'description': jutsu['description'],
                'nameNoPunctuation': name_no_punct,
                'namePinyin': get_pinyin(name_no_punct) if has_pinyin else ''
            }
            g_ninjutsu_data[bot_hash][jutsu['id']] = jutsu_info
        
        # 保存到本地文件
        save_ninjutsu_data(Proc)
        
        return len(jutsus)
    except Exception as e:
        raise Exception(f"网络请求失败或数据解析错误: {str(e)}")

def clear_ninjutsu_database(bot_hash, Proc):
    """清空忍术数据"""
    global g_ninjutsu_data
    if bot_hash in g_ninjutsu_data:
        g_ninjutsu_data[bot_hash] = {}
    # 保存到本地文件
    save_ninjutsu_data(Proc)

def find_ninjutsu(bot_hash, name, match_level=1):
    """查找忍术（支持严格匹配、忽略标点、同音匹配）
    
    Args:
        bot_hash: 机器人hash
        name: 忍术名称
        match_level: 匹配等级 (0=严格, 1=忽略标点, 2=同音)
    """
    global g_ninjutsu_data
    
    if bot_hash not in g_ninjutsu_data:
        return None
    
    name_no_punct = remove_punctuation(name)
    name_pinyin = get_pinyin(name_no_punct) if has_pinyin else ''
    
    # 1. 先尝试完全匹配（严格）
    for jutsu_id, jutsu in g_ninjutsu_data[bot_hash].items():
        if jutsu['name'] == name:
            return jutsu
    
    # 2. 如果匹配等级 >= 1，尝试忽略标点匹配（普通）
    if match_level >= 1:
        for jutsu_id, jutsu in g_ninjutsu_data[bot_hash].items():
            if jutsu['nameNoPunctuation'] == name_no_punct:
                return jutsu
    
    # 3. 如果匹配等级 >= 2，尝试同音匹配（如果拼音库可用）
    if match_level >= 2 and has_pinyin and name_pinyin:
        for jutsu_id, jutsu in g_ninjutsu_data[bot_hash].items():
            if jutsu.get('namePinyin', '') == name_pinyin:
                return jutsu
    
    return None

def search_ninjutsu(bot_hash, keyword, limit=10, match_level=1):
    """搜索忍术（支持普通搜索和同音搜索）
    
    Args:
        bot_hash: 机器人hash
        keyword: 搜索关键字
        limit: 结果数量上限
        match_level: 匹配等级 (0=严格, 1=忽略标点, 2=同音)
    """
    global g_ninjutsu_data
    
    if bot_hash not in g_ninjutsu_data:
        return []
    
    keyword_no_punct = remove_punctuation(keyword)
    keyword_pinyin = get_pinyin(keyword_no_punct) if has_pinyin else ''
    results = []
    seen_ids = set()
    
    for jutsu_id, jutsu in g_ninjutsu_data[bot_hash].items():
        # 在名称和描述中搜索（严格匹配）
        if keyword in jutsu['name'] or keyword in jutsu['description']:
            if jutsu_id not in seen_ids:
                results.append(jutsu)
                seen_ids.add(jutsu_id)
        # 如果匹配等级 >= 1，忽略标点搜索
        elif match_level >= 1 and keyword_no_punct in jutsu['nameNoPunctuation']:
            if jutsu_id not in seen_ids:
                results.append(jutsu)
                seen_ids.add(jutsu_id)
        # 如果匹配等级 >= 2，同音搜索（如果拼音库可用）
        elif match_level >= 2 and has_pinyin and keyword_pinyin and keyword_pinyin in jutsu.get('namePinyin', ''):
            if jutsu_id not in seen_ids:
                results.append(jutsu)
                seen_ids.add(jutsu_id)
        
        if len(results) >= limit:
            break
    
    return results[:limit]

def get_ninjutsu_audios(jutsu_id):
    """获取忍术的音频列表"""
    try:
        # 使用 requests 库
        url = f"{SOURCE_URL}/api/jutsus/{jutsu_id}/audios"
        response = requests.get(url, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        audios = data['audios']
        return [audio['audioUrl'] for audio in audios]
    except Exception as e:
        raise Exception(f"获取音频失败: {str(e)}")

def build_search_result_string(search_results, dictStrCustom, dictTValue, description_preview_limit=50):
    """构建搜索结果字符串"""
    result_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
        dictStrCustom['strNinjutsuSearchResultTitle'], 
        dictTValue
    )
    
    for jutsu in search_results:
        description = jutsu['description']
        # 限制描述长度
        if description_preview_limit > 0 and len(description) > description_preview_limit:
            description = description[:description_preview_limit] + '…'
        description = description.replace('\n', ' ')
        
        tmp_dict = dictTValue.copy()
        tmp_dict['tNinjutsuName'] = jutsu['name']
        tmp_dict['tNinjutsuDescription'] = description
        
        item_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
            dictStrCustom['strNinjutsuSearchResultItem'], 
            tmp_dict
        )
        result_str += item_str
    
    return result_str


def handle_ninjutsu_release(plugin_event, jutsu_name, bot_hash, dictStrCustom, dictTValue, replyMsg):
    """处理忍术释放逻辑"""
    if jutsu_name == '':
        return
    
    # 获取配置参数
    match_level = get_match_level(dictStrCustom)
    search_limit = get_search_limit(dictStrCustom)
    description_preview_limit = get_description_preview_limit(dictStrCustom)
    
    ninjutsu = find_ninjutsu(bot_hash, jutsu_name, match_level)
    if ninjutsu is None:
        search_results = search_ninjutsu(bot_hash, jutsu_name, search_limit, match_level)
        if len(search_results) == 0:
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strNinjutsuNotFound'], 
                dictTValue
            )
            replyMsg(plugin_event, tmp_reply_str)
        else:
            result_str = build_search_result_string(search_results, dictStrCustom, dictTValue, description_preview_limit)
            replyMsg(plugin_event, result_str)
    else:
        try:
            # 优先使用本地音频
            local_audio = check_local_audio(ninjutsu['id'])
            if local_audio:
                # 使用绝对路径,同时指定file和url参数
                audio_cq = f'[CQ:record,file=file:///{local_audio},url=file:///{local_audio}]'
                replyMsg(plugin_event, audio_cq)
            else:
                # 获取在线音频
                audios = get_ninjutsu_audios(ninjutsu['id'])
                if len(audios) == 0:
                    tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                        dictStrCustom['strNinjutsuNoAudio'], 
                        dictTValue
                    )
                    replyMsg(plugin_event, tmp_reply_str)
                else:
                    audio_url = random.choice(audios)
                    audio_cq = f'[CQ:record,file={audio_url},url={audio_url}]'
                    replyMsg(plugin_event, audio_cq)
        except Exception as e:
            dictTValue['tError'] = str(e)
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
                dictStrCustom['strNinjutsuNetworkError'], 
                dictTValue
            )
            replyMsg(plugin_event, tmp_reply_str)


def check_local_audio(jutsu_id):
    """检查本地是否有该忍术的音频文件"""
    jutsu_audio_dir = os.path.join(AUDIO_DIR, str(jutsu_id))
    if not os.path.exists(jutsu_audio_dir):
        return None
    
    # 查找音频文件(支持 mp3, wav, ogg, m4a 等格式)
    audio_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.silk', '.amr']
    for filename in os.listdir(jutsu_audio_dir):
        if any(filename.lower().endswith(ext) for ext in audio_extensions):
            # 返回绝对路径
            return os.path.abspath(os.path.join(jutsu_audio_dir, filename))
    
    return None


def download_audio_file(url, file_path, max_retries=3, Proc=None):
    """
    下载音频文件，支持重试和 SSL 错误处理
    
    Args:
        url: 音频文件URL
        file_path: 保存路径
        max_retries: 最大重试次数
        Proc: 日志对象
    
    Returns:
        bool: 下载是否成功
    """
    # 使用 requests 库
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                timeout=30,
                verify=False  # 忽略 SSL 证书验证
            )
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            return True
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 递增等待时间：2s, 4s, 6s
                if Proc:
                    Proc.log(2, f"[OlivaDiceLexNinjutsu] 下载失败，{wait_time}秒后重试 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                time.sleep(wait_time)
            else:
                if Proc:
                    Proc.log(2, f"[OlivaDiceLexNinjutsu] 下载失败，已达最大重试次数: {str(e)}")
                return False
        except Exception as e:
            if Proc:
                Proc.log(2, f"[OlivaDiceLexNinjutsu] 下载出错: {str(e)}")
            return False
    
    return False


def handle_ninjutsu_download_all(plugin_event, bot_hash, dictStrCustom, dictTValue, replyMsg, Proc):
    """处理全部忍术音频下载逻辑"""
    global g_ninjutsu_data
    
    try:
        # 检查忍术数据库
        if bot_hash not in g_ninjutsu_data or not g_ninjutsu_data[bot_hash]:
            tmp_reply_str = '请先使用 .忍术 更新 命令更新忍术数据库'
            replyMsg(plugin_event, tmp_reply_str)
            return
        
        ninjutsu_db = g_ninjutsu_data[bot_hash]
        
        # 发送开始消息
        dictTValue['tTotalJutsu'] = str(len(ninjutsu_db))
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
            dictStrCustom['strNinjutsuDownloadStart'], 
            dictTValue
        )
        replyMsg(plugin_event, tmp_reply_str)
        Proc.log(2, f"[OlivaDiceLexNinjutsu] 开始下载全部忍术音频，共 {len(ninjutsu_db)} 个忍术")
        
        # 统计变量
        success_count = 0  # 成功下载的忍术数
        fail_count = 0     # 失败的忍术数
        total_audio = 0    # 总音频文件数
        
        # 遍历所有忍术
        for jutsu_id, ninjutsu in ninjutsu_db.items():
            try:
                # 获取音频列表
                audios = get_ninjutsu_audios(jutsu_id)
                if len(audios) == 0:
                    Proc.log(2, f"[OlivaDiceLexNinjutsu] 忍术 {ninjutsu['name']} 无音频，跳过")
                    continue
                
                # 创建忍术专用目录
                jutsu_audio_dir = os.path.join(AUDIO_DIR, str(jutsu_id))
                if not os.path.exists(jutsu_audio_dir):
                    os.makedirs(jutsu_audio_dir)
                
                # 下载该忍术的所有音频文件
                jutsu_success = True
                jutsu_audio_count = 0
                for audio_path in audios:
                    try:
                        # 检查是否为绝对URL,如果是则直接使用,否则拼接SOURCE_URL
                        audio_url = audio_path if audio_path.startswith(('http://', 'https://')) else f"{SOURCE_URL}{audio_path}"
                        filename = os.path.basename(audio_path)
                        file_path = os.path.join(jutsu_audio_dir, filename)
                        
                        # 如果文件已存在，跳过
                        if os.path.exists(file_path):
                            Proc.log(2, f"[OlivaDiceLexNinjutsu] 文件已存在: {ninjutsu['name']}/{filename}")
                            total_audio += 1
                            jutsu_audio_count += 1
                            continue
                        
                        # 下载文件（使用重试机制）
                        if download_audio_file(audio_url, file_path, max_retries=3, Proc=Proc):
                            Proc.log(2, f"[OlivaDiceLexNinjutsu] 已下载: {ninjutsu['name']}/{filename}")
                            total_audio += 1
                            jutsu_audio_count += 1
                        else:
                            Proc.log(2, f"[OlivaDiceLexNinjutsu] 下载失败: {ninjutsu['name']}/{filename}")
                            jutsu_success = False
                        
                    except Exception as e:
                        Proc.log(2, f"[OlivaDiceLexNinjutsu] 下载异常 {ninjutsu['name']}/{audio_path}: {str(e)}")
                        jutsu_success = False
                
                # 统计该忍术下载结果（如果至少有一个音频成功就算成功）
                if jutsu_audio_count > 0:
                    success_count += 1
                    if not jutsu_success:
                        Proc.log(2, f"[OlivaDiceLexNinjutsu] 忍术 {ninjutsu['name']} 部分下载成功 ({jutsu_audio_count}/{len(audios)})")
                else:
                    fail_count += 1
                    
            except Exception as e:
                Proc.log(2, f"[OlivaDiceLexNinjutsu] 处理忍术 {ninjutsu['name']} 失败: {str(e)}")
                fail_count += 1
        
        # 发送完成消息
        dictTValue['tSuccessCount'] = str(success_count)
        dictTValue['tFailCount'] = str(fail_count)
        dictTValue['tTotalAudio'] = str(total_audio)
        dictTValue['tAudioDir'] = AUDIO_DIR
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
            dictStrCustom['strNinjutsuDownloadComplete'], 
            dictTValue
        )
        replyMsg(plugin_event, tmp_reply_str)
        Proc.log(2, f"[OlivaDiceLexNinjutsu] 下载完成，成功: {success_count}，失败: {fail_count}，总音频: {total_audio}")
        
    except Exception as e:
        Proc.log(2, f"[OlivaDiceLexNinjutsu] 下载过程出错: {str(e)}")
        dictTValue['tError'] = str(e)
        tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(
            dictStrCustom['strNinjutsuDownloadError'], 
            dictTValue
        )
        replyMsg(plugin_event, tmp_reply_str)

