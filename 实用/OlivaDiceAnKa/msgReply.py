# -*- encoding: utf-8 -*-
'''
安价插件回复处理。
''' 

import copy
import difflib
import json
import os
import time

import OlivOS
import OlivaDiceCore
import OlivaDiceAnKa


DATA_DIR = os.path.join('plugin', 'data', 'OlivaDiceAnKa')


def unity_init(plugin_event, Proc):
    _ensure_dir(DATA_DIR)


def data_init(plugin_event, Proc):
    OlivaDiceAnKa.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])


def _safe_str(v):
    try:
        return str(v)
    except Exception:
        return ''


def _ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def _load_json(path, default):
    try:
        if not os.path.exists(path):
            return copy.deepcopy(default)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception:
        return copy.deepcopy(default)


def _save_json(path, data):
    try:
        _ensure_dir(os.path.dirname(path))
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _get_bot_hash_with_link(plugin_event):
    bot_hash = ''
    try:
        bot_hash = _safe_str(plugin_event.bot_info.hash)
    except Exception:
        bot_hash = ''

    if bot_hash != '':
        try:
            master = OlivaDiceCore.console.getMasterBotHash(bot_hash)
            if master:
                return _safe_str(master)
        except Exception:
            pass
        return bot_hash

    try:
        self_id = _safe_str(plugin_event.base_info.get('self_id'))
        if self_id != '':
            return 'self_%s' % self_id
    except Exception:
        pass

    return 'unknown'


def _get_bot_dir(bot_hash):
    path = os.path.join(DATA_DIR, _safe_str(bot_hash))
    _ensure_dir(path)
    return path


def _get_data_path(bot_hash):
    return os.path.join(_get_bot_dir(bot_hash), 'anka_data.json')


def _load_all_data(bot_hash):
    data = _load_json(_get_data_path(bot_hash), default={})
    if type(data) is not dict:
        data = {}
    if 'groups' not in data or type(data['groups']) is not dict:
        data['groups'] = {}
    return data


def _save_all_data(bot_hash, data):
    return _save_json(_get_data_path(bot_hash), data)


def _get_hag_id(plugin_event):
    if plugin_event.plugin_info['func_type'] != 'group_message':
        return None
    host_id = None
    group_id = None
    try:
        host_id = plugin_event.data.host_id
    except Exception:
        host_id = None
    try:
        group_id = plugin_event.data.group_id
    except Exception:
        group_id = None
    if group_id is None:
        return None
    if host_id is not None:
        return '%s|%s' % (str(host_id), str(group_id))
    return str(group_id)


def _get_group_hash(plugin_event):
    hag_id = _get_hag_id(plugin_event)
    if hag_id is None:
        return None, None
    platform = plugin_event.platform['platform']
    try:
        group_hash = OlivaDiceCore.userConfig.getUserHash(hag_id, 'group', platform)
    except Exception:
        group_hash = hag_id
    return _safe_str(group_hash), hag_id


def _get_group_entry(data, group_hash, hag_id, platform):
    groups = data['groups']
    if group_hash not in groups or type(groups[group_hash]) is not dict:
        groups[group_hash] = {
            'group_hash': group_hash,
            'hag_id': hag_id,
            'platform': platform,
            'current': '',
            'ankas': {}
        }
    entry = groups[group_hash]
    if 'ankas' not in entry or type(entry['ankas']) is not dict:
        entry['ankas'] = {}
    if 'current' not in entry:
        entry['current'] = ''
    return entry


def _norm_name(name):
    s = _safe_str(name).strip()
    if s == '':
        s = 'default'
    return s


def _resolve_anka_name(ankas, query_name):
    if type(ankas) is not dict:
        return None
    q = _norm_name(query_name)
    if q in ankas:
        return q

    key_list = list(ankas.keys())
    if len(key_list) == 0:
        return None

    # 1) 前缀匹配
    prefix = []
    for k in key_list:
        if _safe_str(k).startswith(q):
            prefix.append(k)
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        return prefix[0]

    # 2) 包含匹配
    contain = []
    for k in key_list:
        if q in _safe_str(k):
            contain.append(k)
    if len(contain) == 1:
        return contain[0]
    if len(contain) > 1:
        return contain[0]

    # 3) 相似度匹配
    close_list = difflib.get_close_matches(q, key_list, n=1, cutoff=0.4)
    if len(close_list) > 0:
        return close_list[0]

    return None


def _is_draw_no_return(token):
    t = _safe_str(token).strip().lower()
    return t in ['不放回', 'nr', 'noreturn', 'remove', 'pop']


def _roll_index_by_onedice(max_count):
    if max_count <= 0:
        return None, '选项数量不足。'
    rd_expr = '1D%d' % int(max_count)
    rd = OlivaDiceCore.onedice.RD(rd_expr, None)
    rd.roll()
    if rd.resError is not None:
        return None, 'onedice异常：%s' % str(rd.resError)
    try:
        res_int = int(rd.resInt)
    except Exception:
        return None, 'onedice结果异常。'
    if res_int < 1:
        res_int = 1
    if res_int > max_count:
        res_int = max_count
    return res_int - 1, None


def _reply_group_only(replyMsg, plugin_event):
    tmp_reply = None
    try:
        tmp_reply = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash].get('strForGroupOnly')
    except Exception:
        tmp_reply = None
    if tmp_reply in [None, '']:
        tmp_reply = '此命令只能在群聊中使用'
    replyMsg(plugin_event, tmp_reply)


def _cmd_take_word(skipSpaceStart, text):
    t = skipSpaceStart(_safe_str(text))
    if t == '':
        return '', ''
    arr = t.split(None, 1)
    if len(arr) == 1:
        return arr[0], ''
    return arr[0], arr[1]


def _fmt(dictStrCustom, dictTValue, key):
    return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom[key], dictTValue)


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

    tmp_id_str = str(plugin_event.base_info['self_id'])
    tmp_id_str_sub = None
    if 'sub_self_id' in plugin_event.data.extend:
        if plugin_event.data.extend['sub_self_id'] != None:
            tmp_id_str_sub = str(plugin_event.data.extend['sub_self_id'])
    tmp_reast_str = plugin_event.data.message
    flag_force_reply = False
    flag_is_command = False
    flag_is_from_host = False
    flag_is_from_group = False

    if isMatchWordStart(tmp_reast_str, '[CQ:reply,id='):
        tmp_reast_str = skipToRight(tmp_reast_str, ']')
        tmp_reast_str = tmp_reast_str[1:]

    if flag_force_reply is False:
        tmp_reast_str_old = tmp_reast_str
        tmp_reast_obj = OlivOS.messageAPI.Message_templet('old_string', tmp_reast_str)
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

    [tmp_reast_str, flag_is_command] = msgIsCommand(tmp_reast_str, OlivaDiceCore.crossHook.dictHookList['prefix'])

    if flag_is_command:
        if plugin_event.plugin_info['func_type'] == 'group_message':
            if plugin_event.data.host_id != None:
                flag_is_from_host = True
            flag_is_from_group = True
        elif plugin_event.plugin_info['func_type'] == 'private_message':
            flag_is_from_group = False

        if flag_is_from_host and flag_is_from_group:
            tmp_hagID = '%s|%s' % (str(plugin_event.data.host_id), str(plugin_event.data.group_id))
        elif flag_is_from_group:
            tmp_hagID = str(plugin_event.data.group_id)
        else:
            tmp_hagID = None

        flag_hostEnable = True
        if flag_is_from_host:
            flag_hostEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId=plugin_event.data.host_id,
                userType='host',
                platform=plugin_event.platform['platform'],
                userConfigKey='hostEnable',
                botHash=plugin_event.bot_info.hash
            )
        flag_hostLocalEnable = True
        if flag_is_from_host:
            flag_hostLocalEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId=plugin_event.data.host_id,
                userType='host',
                platform=plugin_event.platform['platform'],
                userConfigKey='hostLocalEnable',
                botHash=plugin_event.bot_info.hash
            )
        flag_groupEnable = True
        if flag_is_from_group:
            if flag_is_from_host:
                if flag_hostEnable:
                    flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userId=tmp_hagID,
                        userType='group',
                        platform=plugin_event.platform['platform'],
                        userConfigKey='groupEnable',
                        botHash=plugin_event.bot_info.hash
                    )
                else:
                    flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userId=tmp_hagID,
                        userType='group',
                        platform=plugin_event.platform['platform'],
                        userConfigKey='groupWithHostEnable',
                        botHash=plugin_event.bot_info.hash
                    )
            else:
                flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                    userId=tmp_hagID,
                    userType='group',
                    platform=plugin_event.platform['platform'],
                    userConfigKey='groupEnable',
                    botHash=plugin_event.bot_info.hash
                )

        if not flag_hostLocalEnable and not flag_force_reply:
            return
        if not flag_groupEnable and not flag_force_reply:
            return

        if isMatchWordStart(tmp_reast_str, ['anka', 'ak', '安价'], isCommand=True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['anka', 'ak', '安价'])
            tmp_reast_str = skipSpaceStart(tmp_reast_str)

            if not flag_is_from_group:
                _reply_group_only(replyMsg, plugin_event)
                return

            bot_hash = _get_bot_hash_with_link(plugin_event)
            data = _load_all_data(bot_hash)
            group_hash, hag_id = _get_group_hash(plugin_event)
            if group_hash is None:
                _reply_group_only(replyMsg, plugin_event)
                return
            group_entry = _get_group_entry(data, group_hash, hag_id, plugin_event.platform['platform'])
            ankas = group_entry['ankas']
            current_name = _safe_str(group_entry.get('current', '')).strip()
            if current_name == '' or current_name not in ankas:
                current_name = None
            if current_name is not None:
                if type(ankas[current_name].get('options')) is not list:
                    ankas[current_name]['options'] = []
                if type(ankas[current_name].get('history')) is not list:
                    ankas[current_name]['history'] = []

            def _reply_anka_list(empty_key):
                name_list = list(ankas.keys())
                if len(name_list) == 0:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, empty_key))
                    return
                out = [_fmt(dictStrCustom, dictTValue, 'strAnkaListTitle')]
                for one_name in name_list:
                    one = ankas[one_name]
                    dictTValue['tAnkaName'] = _safe_str(one_name)
                    dictTValue['tAnkaCount'] = str(len(one.get('options', [])))
                    dictTValue['tAnkaCurrent'] = ' <- 当前' if one_name == current_name else ''
                    dictTValue['tAnkaActive'] = ' [编辑中]' if bool(one.get('active', False)) else ''
                    out.append(_fmt(dictStrCustom, dictTValue, 'strAnkaListLine'))
                replyMsg(plugin_event, '\n'.join(out))

            if tmp_reast_str in ['', None]:
                _reply_anka_list('strAnkaNoData')
                return

            if isMatchWordStart(tmp_reast_str, ['create', 'on', 'new'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['create', 'on', 'new'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                anka_name = _norm_name(tmp_reast_str)
                if anka_name not in ankas:
                    ankas[anka_name] = {'name': anka_name, 'active': True, 'options': [], 'history': [], 'create_ts': int(time.time())}
                else:
                    ankas[anka_name]['active'] = True
                    if type(ankas[anka_name].get('options')) is not list:
                        ankas[anka_name]['options'] = []
                    if type(ankas[anka_name].get('history')) is not list:
                        ankas[anka_name]['history'] = []
                group_entry['current'] = anka_name
                _save_all_data(bot_hash, data)
                dictTValue['tAnkaName'] = _safe_str(anka_name)
                replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaCreateOn'))
                return

            if isMatchWordStart(tmp_reast_str, ['off'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['off'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                if current_name is None:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaOffNoActive'))
                    return
                if current_name not in ankas:
                    group_entry['current'] = ''
                    _save_all_data(bot_hash, data)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaOffNoActive'))
                    return
                ankas[current_name]['active'] = False
                group_entry['current'] = ''
                _save_all_data(bot_hash, data)
                dictTValue['tAnkaName'] = _safe_str(current_name)
                replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaOffSuccess'))
                return

            if isMatchWordStart(tmp_reast_str, ['set'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['set'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                if tmp_reast_str in ['', None]:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaSetUsage'))
                    return
                set_query_name = _safe_str(tmp_reast_str).strip()
                hit_name = None

                # 先尝试精确匹配
                if set_query_name in ankas:
                    hit_name = set_query_name
                else:
                    # 再尝试使用核心的模糊搜索选择（与人物卡 set 逻辑一致）
                    dictTValue['tAnkaQueryName'] = set_query_name
                    hit_name = OlivaDiceCore.helpDoc.fuzzySearchAndSelect(
                        key_str=set_query_name,
                        item_list=list(ankas.keys()),
                        bot_hash=plugin_event.bot_info.hash,
                        plugin_event=plugin_event,
                        strRecommendKey='strAnkaSetRecommend',
                        strErrorKey='strAnkaSetNotFound',
                        dictStrCustom=dictStrCustom,
                        dictTValue=dictTValue
                    )
                    # 未选中时，返回（上面的函数会帮你发返回命令所以这里直接return就行）
                    if hit_name is None:
                        return

                group_entry['current'] = hit_name
                _save_all_data(bot_hash, data)
                dictTValue['tAnkaName'] = _safe_str(hit_name)
                replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaSetSuccess'))
                return

            if isMatchWordStart(tmp_reast_str, ['add'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['add'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                if tmp_reast_str in ['', None]:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaAddUsage'))
                    return
                word1, rest1 = _cmd_take_word(skipSpaceStart, tmp_reast_str)
                hit_name = _resolve_anka_name(ankas, word1)
                if hit_name is not None and _safe_str(rest1).strip() != '':
                    target_name = hit_name
                    option_text = _safe_str(rest1).strip()
                else:
                    target_name = current_name
                    option_text = _safe_str(tmp_reast_str).strip()
                if target_name is None:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoActive'))
                    return
                if target_name not in ankas:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNotExist'))
                    return
                if type(ankas[target_name].get('options')) is not list:
                    ankas[target_name]['options'] = []
                if type(ankas[target_name].get('history')) is not list:
                    ankas[target_name]['history'] = []
                if option_text == '':
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaOptionEmpty'))
                    return
                ankas[target_name]['options'].append(option_text)
                _save_all_data(bot_hash, data)
                dictTValue['tAnkaName'] = _safe_str(target_name)
                dictTValue['tAnkaIndex'] = str(len(ankas[target_name]['options']))
                dictTValue['tAnkaOption'] = _safe_str(option_text)
                replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaAddSuccess'))
                return

            if isMatchWordStart(tmp_reast_str, ['rm'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['rm'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                if tmp_reast_str in ['', None]:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaRmUsage'))
                    return
                word1, rest1 = _cmd_take_word(skipSpaceStart, tmp_reast_str)
                word2, _rest2 = _cmd_take_word(skipSpaceStart, rest1)
                target_name = current_name
                index_token = None
                if word2 != '':
                    hit_name = _resolve_anka_name(ankas, word1)
                    if hit_name is not None:
                        target_name = hit_name
                        index_token = word2
                    else:
                        index_token = word1
                else:
                    index_token = word1
                if target_name is None:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoActive'))
                    return
                if target_name not in ankas:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNotExist'))
                    return
                options = ankas[target_name].get('options', [])
                if type(options) is not list or len(options) == 0:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoOptionToRm'))
                    return
                if not _safe_str(index_token).isdigit():
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaRmIndexNotNumber'))
                    return
                idx = int(index_token) - 1
                if idx < 0 or idx >= len(options):
                    dictTValue['tAnkaCount'] = str(len(options))
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaRmIndexOutOfRange'))
                    return
                removed = options.pop(idx)
                ankas[target_name]['options'] = options
                _save_all_data(bot_hash, data)
                dictTValue['tAnkaName'] = _safe_str(target_name)
                dictTValue['tAnkaIndex'] = str(idx + 1)
                dictTValue['tAnkaOption'] = _safe_str(removed)
                replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaRmSuccess'))
                return

            if isMatchWordStart(tmp_reast_str, ['clr'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['clr'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                target_name = current_name
                if tmp_reast_str not in ['', None]:
                    hit_name = _resolve_anka_name(ankas, tmp_reast_str)
                    if hit_name is None:
                        dictTValue['tAnkaQueryName'] = _safe_str(tmp_reast_str).strip()
                        replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaEndNotFound'))
                        return
                    target_name = hit_name
                if target_name is None:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoActive'))
                    return
                if target_name not in ankas:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNotExist'))
                    return
                ankas[target_name]['options'] = []
                _save_all_data(bot_hash, data)
                dictTValue['tAnkaName'] = _safe_str(target_name)
                replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaClrSuccess'))
                return

            if isMatchWordStart(tmp_reast_str, ['del', 'end'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['del', 'end'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                target_name = current_name
                if tmp_reast_str not in ['', None]:
                    hit_name = _resolve_anka_name(ankas, tmp_reast_str)
                    if hit_name is None:
                        dictTValue['tAnkaQueryName'] = _safe_str(tmp_reast_str).strip()
                        replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaEndNotFound'))
                        return
                    target_name = hit_name
                if target_name is None:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoActive'))
                    return
                if target_name not in ankas:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNotExist'))
                    return

                # del/end：删除整个安价（不是仅结束编辑）
                del ankas[target_name]

                # 若删除的是当前安价，自动切换到剩余任意一个；若不存在则清空 current
                group_current = _safe_str(group_entry.get('current', '')).strip()
                if group_current == target_name:
                    if len(ankas) > 0:
                        group_entry['current'] = list(ankas.keys())[0]
                    else:
                        group_entry['current'] = ''

                _save_all_data(bot_hash, data)
                dictTValue['tAnkaName'] = _safe_str(target_name)
                replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaEndSuccess'))
                return

            if isMatchWordStart(tmp_reast_str, ['draw'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['draw'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                target_name = current_name
                no_return = False
                draw_count = 1
                if tmp_reast_str not in ['', None]:
                    token_list = _safe_str(tmp_reast_str).split()
                    flag_name_set = False
                    for token in token_list:
                        token_s = _safe_str(token).strip()
                        if token_s == '':
                            continue
                        if _is_draw_no_return(token_s):
                            no_return = True
                            continue
                        if token_s.isdigit():
                            draw_count = int(token_s)
                            continue
                        hit_name = _resolve_anka_name(ankas, token_s)
                        if hit_name is not None and not flag_name_set:
                            target_name = hit_name
                            flag_name_set = True
                            continue
                        dictTValue['tAnkaQueryName'] = token_s
                        replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaDrawNotFound'))
                        return
                if target_name is None:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoActive'))
                    return
                if target_name not in ankas:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNotExist'))
                    return
                options = ankas[target_name].get('options', [])
                if type(options) is not list or len(options) == 0:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoOptionToDraw'))
                    return

                if draw_count <= 0:
                    draw_count = 1
                if draw_count > 100:
                    draw_count = 100
                if no_return and draw_count > len(options):
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaDrawErrNoCount'))
                    return

                result_list = []
                history_list = ankas[target_name].get('history', [])
                if type(history_list) is not list:
                    history_list = []

                for _i in range(draw_count):
                    idx, err = _roll_index_by_onedice(len(options))
                    if err is not None:
                        if err.startswith('onedice异常：'):
                            dictTValue['tAnkaError'] = err.replace('onedice异常：', '', 1)
                            replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaDrawErrOneDice'))
                        elif err == 'onedice结果异常。':
                            replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaDrawErrOneDiceResult'))
                        else:
                            replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaDrawErrNoCount'))
                        return
                    chosen = options[idx]
                    result_list.append((int(idx + 1), _safe_str(chosen)))
                    history_list.append({
                        'ts': int(time.time()),
                        'index': int(idx + 1),
                        'option': _safe_str(chosen),
                        'mode': '不放回' if no_return else '放回',
                        'user_id': _safe_str(plugin_event.data.user_id),
                        'user_name': _safe_str(plugin_event.data.sender.get('name'))
                    })
                    if no_return:
                        options.pop(idx)

                if len(history_list) > 500:
                    history_list = history_list[-500:]
                ankas[target_name]['history'] = history_list
                if no_return:
                    ankas[target_name]['options'] = options

                dictTValue['tAnkaName'] = _safe_str(target_name)

                if draw_count == 1:
                    dictTValue['tAnkaIndex'] = str(result_list[0][0])
                    dictTValue['tAnkaOption'] = _safe_str(result_list[0][1])
                    _save_all_data(bot_hash, data)
                    if no_return:
                        dictTValue['tAnkaCount'] = str(len(options))
                        replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaDrawNoReturn'))
                        return
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaDrawWithReturn'))
                    return

                dictTValue['tAnkaDrawCount'] = str(draw_count)
                out = [_fmt(dictStrCustom, dictTValue, 'strAnkaDrawMultiTitle')]
                i = 1
                for item in result_list:
                    dictTValue['tAnkaHistoryNo'] = str(i)
                    dictTValue['tAnkaIndex'] = str(item[0])
                    dictTValue['tAnkaOption'] = _safe_str(item[1])
                    out.append(_fmt(dictStrCustom, dictTValue, 'strAnkaDrawMultiLine'))
                    i += 1
                if no_return:
                    dictTValue['tAnkaCount'] = str(len(options))
                    out.append(_fmt(dictStrCustom, dictTValue, 'strAnkaDrawMultiTailNoReturn'))
                _save_all_data(bot_hash, data)
                replyMsg(plugin_event, '\n'.join(out))
                return

            if isMatchWordStart(tmp_reast_str, ['get', 'his', '记录', '历史'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['get', 'his', '记录', '历史'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)

                target_name = current_name
                show_count = 20

                if tmp_reast_str not in ['', None]:
                    word1, rest1 = _cmd_take_word(skipSpaceStart, tmp_reast_str)
                    if _safe_str(word1).isdigit():
                        show_count = int(word1)
                    else:
                        hit_name = _resolve_anka_name(ankas, word1)
                        if hit_name is None:
                            dictTValue['tAnkaQueryName'] = _safe_str(word1).strip()
                            replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaHistoryNotFound'))
                            return
                        target_name = hit_name
                        word2, _rest2 = _cmd_take_word(skipSpaceStart, rest1)
                        if _safe_str(word2).isdigit():
                            show_count = int(word2)

                if target_name is None:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoActive'))
                    return

                if show_count <= 0:
                    show_count = 1
                if show_count > 100:
                    show_count = 100

                if target_name not in ankas:
                    dictTValue['tAnkaQueryName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaHistoryNotFound'))
                    return

                history_list = ankas[target_name].get('history', [])
                if type(history_list) is not list:
                    history_list = []
                if len(history_list) == 0:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoHistory'))
                    return

                show_list = history_list[-show_count:]
                show_list = list(reversed(show_list))

                dictTValue['tAnkaName'] = _safe_str(target_name)
                dictTValue['tAnkaHistoryShow'] = str(len(show_list))
                dictTValue['tAnkaHistoryTotal'] = str(len(history_list))

                out = [_fmt(dictStrCustom, dictTValue, 'strAnkaHistoryTitle')]
                i = 1
                for item in show_list:
                    ts_val = item.get('ts')
                    try:
                        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(ts_val)))
                    except Exception:
                        time_str = '未知时间'
                    dictTValue['tAnkaHistoryNo'] = str(i)
                    dictTValue['tAnkaHistoryTime'] = _safe_str(time_str)
                    dictTValue['tAnkaHistoryMode'] = _safe_str(item.get('mode', '放回'))
                    dictTValue['tAnkaIndex'] = str(item.get('index', 0))
                    dictTValue['tAnkaOption'] = _safe_str(item.get('option', ''))
                    user_name = _safe_str(item.get('user_name', ''))
                    user_id = _safe_str(item.get('user_id', ''))
                    if user_name != '' and user_id != '':
                        dictTValue['tAnkaHistoryUser'] = '%s(%s)' % (user_name, user_id)
                    elif user_name != '':
                        dictTValue['tAnkaHistoryUser'] = user_name
                    else:
                        dictTValue['tAnkaHistoryUser'] = user_id
                    out.append(_fmt(dictStrCustom, dictTValue, 'strAnkaHistoryLine'))
                    i += 1
                replyMsg(plugin_event, '\n'.join(out))
                return

            if isMatchWordStart(tmp_reast_str, ['show'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['show'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                target_name = current_name
                if tmp_reast_str not in ['', None]:
                    hit_name = _resolve_anka_name(ankas, tmp_reast_str)
                    if hit_name is None:
                        dictTValue['tAnkaQueryName'] = _safe_str(tmp_reast_str).strip()
                        replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaShowNotFound'))
                        return
                    target_name = hit_name
                if target_name is None:
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoActive'))
                    return
                if target_name not in ankas:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNotExist'))
                    return
                options = ankas[target_name].get('options', [])
                if type(options) is not list or len(options) == 0:
                    dictTValue['tAnkaName'] = _safe_str(target_name)
                    replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaNoOptionToShow'))
                    return
                out = []
                dictTValue['tAnkaName'] = _safe_str(target_name)
                dictTValue['tAnkaCount'] = str(len(options))
                out.append(_fmt(dictStrCustom, dictTValue, 'strAnkaShowTitle'))
                i = 1
                for option_this in options:
                    dictTValue['tAnkaIndex'] = str(i)
                    dictTValue['tAnkaOption'] = _safe_str(option_this)
                    out.append(_fmt(dictStrCustom, dictTValue, 'strAnkaShowLine'))
                    i += 1
                replyMsg(plugin_event, '\n'.join(out))
                return

            if isMatchWordStart(tmp_reast_str, ['list'], isCommand=True):
                tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['list'])
                tmp_reast_str = skipSpaceStart(tmp_reast_str)
                _reply_anka_list('strAnkaListEmpty')
                return

            replyMsg(plugin_event, _fmt(dictStrCustom, dictTValue, 'strAnkaUnknownSubCommand'))
            return

    return

