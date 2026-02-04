# -*- encoding: utf-8 -*-
import OlivOS
import OlivaDiceCore
import OlivaDiceMS

import copy
import json
import os
import random
import re


def unity_init(plugin_event, Proc):
    pass


def data_init(plugin_event, Proc):
    OlivaDiceMS.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])


def _load_local_ms_template():
    try:
        tmp_path = os.path.join(os.path.dirname(__file__), '人物卡模板', 'ms.json')
        with open(tmp_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if type(data) is dict and 'ms' in data and type(data['ms']) is dict:
            return data['ms']
        return None
    except:
        return None


def _get_hag_id(plugin_event):
    tmp_hagID = None
    if plugin_event.plugin_info['func_type'] == 'group_message':
        if hasattr(plugin_event.data, 'host_id') and plugin_event.data.host_id != None:
            tmp_hagID = '%s|%s' % (str(plugin_event.data.host_id), str(plugin_event.data.group_id))
        else:
            tmp_hagID = str(plugin_event.data.group_id)
    return tmp_hagID


def _get_target_pc(plugin_event, tmp_hagID, target_user_id, dictTValue):
    tmp_pc_platform = plugin_event.platform['platform']
    tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(target_user_id, tmp_pc_platform)
    tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)

    tmp_pcCardRule = 'default'
    tmp_pcCardRule_new = OlivaDiceCore.pcCard.pcCardDataGetTemplateKey(tmp_pcHash, tmp_pc_name)
    if tmp_pcCardRule_new != None:
        tmp_pcCardRule = tmp_pcCardRule_new

    if tmp_pc_name != None:
        dictTValue['tName'] = tmp_pc_name
    else:
        res = plugin_event.get_stranger_info(user_id = target_user_id)
        if res != None and res.get('active'):
            dictTValue['tName'] = res['data']['name']
        else:
            dictTValue['tName'] = f'用户{target_user_id}'

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

    return {
        'pcHash': tmp_pcHash,
        'pcName': tmp_pc_name,
        'pcRule': tmp_pcCardRule,
        'skillTable': skill_valueTable,
        'platform': tmp_pc_platform,
        'userId': target_user_id,
    }


def _safe_int(val, default=0):
    try:
        if val is None:
            return default
        if type(val) in [int]:
            return int(val)
        return int(str(val))
    except:
        return default


def _pc_get_skill_int(pcHash, hagId, skillName: str, default: int = 0) -> int:
    """按 OlivaDiceCore 的人物卡逻辑获取技能值（不存在时按模板默认值/0）。"""
    try:
        v = OlivaDiceCore.pcCard.pcCardDataGetBySkillName(
            pcHash,
            str(skillName),
            hagId=hagId
        )
        return _safe_int(v, default=default)
    except Exception:
        return default


def _is_plain_skill_name(text: str) -> bool:
    try:
        s = str(text).strip()
        if s == '':
            return False
        # 仅允许中英文/下划线：出现数字或运算符则视为表达式
        return re.match(r'^[A-Za-z_\u4e00-\u9fff]+$', s) is not None
    except Exception:
        return False


def _is_ms_save_skill(skill_name: str, ms_template: dict) -> bool:
    try:
        if type(ms_template) is not dict:
            return False
        skill_def = ms_template.get('skill')
        if type(skill_def) is not dict:
            return False
        save_list = skill_def.get('豁免')
        if type(save_list) is not list:
            return False
        s = str(skill_name).strip()
        if s == '':
            return False
        for k in save_list:
            if str(k).strip() == s:
                return True
        return False
    except Exception:
        return False


def _roll(expr, customDefault=None):
    rd = OlivaDiceCore.onedice.RD(expr, customDefault)
    rd.roll()
    return rd


def _format_rd_roll_text(expr: str, rd) -> str:
    res_int = getattr(rd, 'resInt', None)
    res_detail = getattr(rd, 'resDetail', None)

    # 统一用大写 D（显示更清晰）
    try:
        expr_show = re.sub(r'(?i)(\d+)d(\d+)', r'\1D\2', str(expr))
    except Exception:
        expr_show = str(expr)

    # 对齐展示
    if res_detail not in [None, '']:
        detail = str(res_detail).strip()
        try:
            expr_lower = str(expr).lower()
            if expr_lower.endswith('kh') or expr_lower.endswith('kl'):
                m = re.match(r'^\{([^}]*)\}(?:\([^)]*\))?$', detail)
                inner = m.group(1) if m else detail
                nums = [int(x) for x in re.findall(r'-?\d+', inner)]
                if nums:
                    kept = int(res_int) if res_int is not None else (max(nums) if expr_lower.endswith('kh') else min(nums))
                    remaining = nums.copy()
                    # 移除一个 kept（处理重复值）
                    for i, v in enumerate(remaining):
                        if v == kept:
                            remaining.pop(i)
                            break
                    if remaining:
                        detail = '{%d <| %s}' % (kept, ', '.join(str(x) for x in remaining))
                    else:
                        detail = '{%d}' % kept
        except Exception:
            pass

        if res_int is None:
            return '%s=%s' % (expr_show, detail)
        return '%s=%s=%d' % (expr_show, detail, int(res_int))

    if res_int is None:
        return str(expr_show)
    return '%s=%d' % (expr_show, int(res_int))


def _format_rd_final_only(expr: str, rd) -> str:
    """用于表达式技能值展示：只显示 expr=结果，不展开 resDetail。"""
    res_int = getattr(rd, 'resInt', None)
    try:
        expr_show = re.sub(r'(?i)(\d+)d(\d+)', r'\1D\2', str(expr))
    except Exception:
        expr_show = str(expr)
    if res_int is None:
        return str(expr_show)
    return '%s=%d' % (expr_show, int(res_int))


def _eval_inline_dice(text: str, customDefault=None) -> str:
    if text is None:
        return ''
    text = str(text)

    def _replace(m):
        inner = m.group(1)
        try:
            rd = _roll(str(inner).strip(), customDefault)
            if rd.resError is not None:
                return m.group(0)
            return str(rd.resInt)
        except Exception:
            return m.group(0)

    # 仅处理不嵌套的大括号段
    return re.sub(r'\{([^{}]+)\}', _replace, text)


def _format_d100_display(d100_int):
    if d100_int == 100 or d100_int == 0:
        return '00'
    return str(d100_int)


def _ms_skillcheck_type(roll_value, skill_value, ms_template):
    dictRuleTempData = {
        'roll': int(roll_value),
        'skill': int(skill_value)
    }
    tmpSkillCheckType, tmpSkillThreshold = OlivaDiceCore.skillCheck.getSkillCheckByTemplate(
        dictRuleTempData,
        ms_template,
        'default'
    )
    return tmpSkillCheckType


def _ms_rank(roll_value, skill_value, ms_template):
    tmpSkillCheckType = _ms_skillcheck_type(roll_value, skill_value, ms_template)
    if tmpSkillCheckType == OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_SUCCESS:
        return 2, tmpSkillCheckType
    if tmpSkillCheckType == OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS:
        return 1, tmpSkillCheckType
    if tmpSkillCheckType == OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_FAIL:
        return -2, tmpSkillCheckType
    return -1, tmpSkillCheckType


def _handle_stress_change(plugin_event, pc_info, dictTValue, dictStrCustom, is_failure, is_rest, d100_value):
    skill_table = pc_info['skillTable']
    pcHash = pc_info['pcHash']
    pcName = pc_info['pcName']
    tmp_hagID = pc_info.get('hagId')

    def _try_auto_sn_update():
        try:
            OlivaDiceCore.msgReply.trigger_auto_sn_update(
                plugin_event,
                pc_info.get('userId'),
                pc_info.get('platform'),
                tmp_hagID,
                dictTValue
            )
        except Exception:
            pass

    stress = _pc_get_skill_int(pcHash, tmp_hagID, '压力', default=0)
    stress_min = _pc_get_skill_int(pcHash, tmp_hagID, '压力下限', default=2)
    stress_max = _pc_get_skill_int(pcHash, tmp_hagID, '压力上限', default=20)

    # 未录入压力时，按下限初始化
    if stress == 0:
        stress = stress_min

    dictTValue['tStressOld'] = str(stress)
    dictTValue['tStressNew'] = str(stress)
    dictTValue['tStressOverflow'] = '0'
    dictTValue['tStressMinNote'] = ''

    if is_rest and (not is_failure):
        reduce_val = int(d100_value) % 10
        stress_clamped = min(stress, stress_max)
        new_stress = stress_clamped - reduce_val
        if new_stress < stress_min:
            new_stress = stress_min
            dictTValue['tStressMinNote'] = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strStressMinNote'], dictTValue)
        dictTValue['tStressOld'] = str(stress_clamped)
        dictTValue['tStressNew'] = str(new_stress)
        # 写回人物卡
        if pcName != None:
            OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
                pcHash = pcHash,
                skillName = '压力',
                skillValue = new_stress,
                pcCardName = pcName,
                hagId = tmp_hagID
            )
            _try_auto_sn_update()
        return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strStressReduce'], dictTValue)

    if not is_failure:
        return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strStressNone'], dictTValue)

    new_stress = stress + 1
    if pcName != None:
        OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
            pcHash = pcHash,
            skillName = '压力',
            skillValue = new_stress,
            pcCardName = pcName,
            hagId = tmp_hagID
        )
        _try_auto_sn_update()

    if stress < stress_max:
        dictTValue['tStressNew'] = str(new_stress)
        return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strStressAdd'], dictTValue)

    # 到达/超过上限时：显示20→20，但仍累计溢出
    dictTValue['tStressOld'] = str(stress_max)
    dictTValue['tStressNew'] = str(stress_max)
    dictTValue['tStressOverflow'] = str(max(0, new_stress - stress_max))
    return OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strStressAddMax'], dictTValue)


def _draw_panic(d20_value, customDefault=None):
    PANIC_TABLE = OlivaDiceMS.msgCustom.dictStrConst.get('MS_PANIC_TABLE', [])
    idx = int(d20_value) - 1
    if idx < 0:
        idx = 0
    if idx >= len(PANIC_TABLE):
        idx = len(PANIC_TABLE) - 1

    text = '\n\n惊恐效果:\n'
    text += PANIC_TABLE[idx]

    # 复合问题：额外两次
    if idx == 17:
        text += '\n复合惊恐效果：\n'
        for _ in range(2):
            die = random.randint(0, len(PANIC_TABLE) - 1)
            text += PANIC_TABLE[die] + '\n'
    return _eval_inline_dice(text.rstrip('\n'), customDefault)


def _ms_generate_once(customDefault=None):
    def _roll_int(expr: str) -> int:
        rd = _roll(expr, customDefault)
        if getattr(rd, 'resError', None) is not None:
            raise Exception(str(rd.resError))
        if getattr(rd, 'resInt', None) is None:
            raise Exception('onedice返回空结果：%s' % expr)
        return int(rd.resInt)

    # 4项(25+2D10), 3项(10+2D10)
    stats = []
    for _ in range(4):
        stats.append(25 + _roll_int('2D10'))
    for _ in range(3):
        stats.append(10 + _roll_int('2D10'))

    hp = _roll_int('1D10') + 10
    cr = _roll_int('2D10') * 10
    total = int(sum(stats))

    return {
        '力量': stats[0],
        '速度': stats[1],
        '智力': stats[2],
        '战斗': stats[3],
        '理智': stats[4],
        '恐惧': stats[5],
        '身体': stats[6],
        '生命值': hp,
        '信用点': cr,
        '合计': total
    }


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

    tmp_reast_str = plugin_event.data.message
    flag_force_reply = False
    flag_is_command = False
    flag_is_from_host = False
    flag_is_from_group = False
    flag_is_from_group_admin = False
    flag_is_from_group_sub_admin = False
    flag_is_from_group_have_admin = False
    flag_is_from_master = False

    if isMatchWordStart(tmp_reast_str, '[CQ:reply,id='):
        tmp_reast_str = skipToRight(tmp_reast_str, ']')
        tmp_reast_str = tmp_reast_str[1:]

    [tmp_reast_str, flag_is_command] = msgIsCommand(
        tmp_reast_str,
        OlivaDiceCore.crossHook.dictHookList['prefix']
    )

    if not flag_is_command:
        return

    tmp_hagID = _get_hag_id(plugin_event)
    valDict['tmp_hagID'] = tmp_hagID
    valDict['tmp_userID'] = plugin_event.data.user_id

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
        if hasattr(plugin_event.data, 'host_id') and plugin_event.data.host_id != None:
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

    # 群/频道启用检查（沿用核心逻辑）
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
        tmp_group_key = tmp_hagID
        if flag_is_from_host:
            if flag_hostEnable:
                flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                    userId = tmp_group_key,
                    userType = 'group',
                    platform = plugin_event.platform['platform'],
                    userConfigKey = 'groupEnable',
                    botHash = plugin_event.bot_info.hash
                )
            else:
                flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                    userId = tmp_group_key,
                    userType = 'group',
                    platform = plugin_event.platform['platform'],
                    userConfigKey = 'groupWithHostEnable',
                    botHash = plugin_event.bot_info.hash
                )
        else:
            flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId = tmp_group_key,
                userType = 'group',
                platform = plugin_event.platform['platform'],
                userConfigKey = 'groupEnable',
                botHash = plugin_event.bot_info.hash
            )

    if not flag_hostLocalEnable and not flag_force_reply:
        return
    if not flag_groupEnable and not flag_force_reply:
        return

    # 选择母舰模板（用于skillCheck规则与d100定制）
    ms_template = OlivaDiceCore.pcCardData.dictPcCardTemplateDefault.get('ms')
    if ms_template == None:
        ms_template = _load_local_ms_template()
    if ms_template == None:
        ms_template = OlivaDiceCore.pcCardData.dictPcCardTemplateDefault.get('default')
    ms_customDefault = ms_template.get('customDefault') if type(ms_template) is dict else None

    def _allow_ms_command_for_context(target_user_id: int = None) -> bool:
        tmp_platform = plugin_event.platform['platform']
        if target_user_id is None:
            target_user_id = plugin_event.data.user_id

        # 1) 群模板为 ms 时允许
        if plugin_event.plugin_info['func_type'] == 'group_message' and tmp_hagID is not None:
            try:
                for userConfigKey in ['groupTemplateRule', 'groupTemplate']:
                    group_template = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userConfigKey = userConfigKey,
                        botHash = plugin_event.bot_info.hash,
                        userId = tmp_hagID,
                        userType = 'group',
                        platform = tmp_platform
                    )
                    if group_template is not None and str(group_template).strip().lower() in ['ms', '母舰', 'mothership']:
                        return True
            except Exception:
                pass

        # 2) 目标用户选中的人物卡模板为 ms 时允许（代骰时按目标用户判定）
        try:
            tmp_pcHash = OlivaDiceCore.pcCard.getPcHash(target_user_id, tmp_platform)
            tmp_pc_name = OlivaDiceCore.pcCard.pcCardDataGetSelectionKey(tmp_pcHash, tmp_hagID)
            if tmp_pc_name is not None:
                tmp_temp = OlivaDiceCore.pcCard.pcCardDataGetTemplateKey(tmp_pcHash, tmp_pc_name)
                if tmp_temp is not None and str(tmp_temp).strip().lower() in ['ms', '母舰', 'mothership']:
                    return True
        except Exception:
            pass
        return False

    # ===== .ms =====
    if _allow_ms_command_for_context() and isMatchWordStart(tmp_reast_str, 'ms', isCommand = True):
        is_at, at_user_id, tmp_reast_str = OlivaDiceCore.msgReply.parse_at_user(
            plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin
        )
        if is_at and not at_user_id:
            plugin_event.set_block()
            return

        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'ms')
        tmp_reast_str = skipSpaceStart(tmp_reast_str).rstrip(' ')

        if tmp_reast_str in ['', None]:
            times = 1
        elif tmp_reast_str.lower() == 'help':
            try:
                OlivaDiceCore.msgReply.replyMsgLazyHelpByEvent(plugin_event, 'ms')
                plugin_event.set_block()
            except Exception:
                pass
            return
        else:
            if tmp_reast_str.isdecimal():
                times = int(tmp_reast_str)
            else:
                dictTValue['tResult'] = '次数必须为正整数。'
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMSGenerateError'], dictTValue))
                plugin_event.set_block()
                return

        if times <= 0 or times > 10:
            dictTValue['tResult'] = '最多只能生成10次。'
            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMSGenerateError'], dictTValue))
            plugin_event.set_block()
            return

        target_user_id = at_user_id if at_user_id else plugin_event.data.user_id
        pc_info = _get_target_pc(plugin_event, tmp_hagID, target_user_id, dictTValue)
        pc_info['hagId'] = tmp_hagID

        results = []
        try:
            for _ in range(times):
                one = _ms_generate_once(ms_customDefault)
                results.append(
                    f"力量:{one['力量']} 速度:{one['速度']} 智力:{one['智力']}\n"
                    f"战斗:{one['战斗']} 理智:{one['理智']} 恐惧:{one['恐惧']}\n"
                    f"身体:{one['身体']} 生命值:{one['生命值']} 信用点:{one['信用点']}\n"
                    f"[{one['合计']}]"
                )
        except Exception as e:
            dictTValue['tResult'] = f'人物作成掷骰失败：{e}'
            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMSGenerateError'], dictTValue))
            plugin_event.set_block()
            return

        dictTValue['tMSResult'] = ('\n\n'.join(results)).strip()

        if at_user_id:
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMSGenerateAtOther'], dictTValue)
        else:
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMSGenerate'], dictTValue)
        replyMsg(plugin_event, tmp_reply_str)
        plugin_event.set_block()
        return

    # ===== .rm（支持可选 b/p 前缀参数） =====
    if isMatchWordStart(tmp_reast_str, 'rm', isCommand = True):
        is_at, at_user_id, tmp_reast_str = OlivaDiceCore.msgReply.parse_at_user(
            plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin
        )
        if is_at and not at_user_id:
            return

        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'rm')
        tmp_reast_str = skipSpaceStart(tmp_reast_str).rstrip(' ')

        if isMatchWordStart(tmp_reast_str, 'help', isCommand = True):
            OlivaDiceCore.msgReply.replyMsgLazyHelpByEvent(plugin_event, 'rm')
            plugin_event.set_block()
            return

        # b/p 可选参数
        flag_bp_type = 0
        flag_bp_count = 1
        if len(tmp_reast_str) >= 1:
            if tmp_reast_str[0].lower() == 'b':
                flag_bp_type = 1
                tmp_reast_str = tmp_reast_str[1:]
            elif tmp_reast_str[0].lower() == 'p':
                flag_bp_type = 2
                tmp_reast_str = tmp_reast_str[1:]
        if flag_bp_type != 0:
            if len(tmp_reast_str) >= 1 and tmp_reast_str[0].isdigit():
                flag_bp_count = int(tmp_reast_str[0])
                tmp_reast_str = tmp_reast_str[1:]
            tmp_reast_str = skipSpaceStart(tmp_reast_str).rstrip(' ')

        # 若无参数（不包括 b/p 前缀本身）则弹出 help
        if tmp_reast_str == '' or tmp_reast_str is None:
            try:
                OlivaDiceCore.msgReply.replyMsgLazyHelpByEvent(plugin_event, 'rm')
            except Exception:
                pass
            plugin_event.set_block()
            return

        # b/p 前缀标记
        bp_mark = ''
        if flag_bp_type == 1:
            bp_mark = '[+%d]' % flag_bp_count if flag_bp_count != 1 else '[+]'
        elif flag_bp_type == 2:
            bp_mark = '[-%d]' % flag_bp_count if flag_bp_count != 1 else '[-]'

        # 休息豁免仅在母舰规则启用（避免检查冲突）
        target_user_id = at_user_id if at_user_id else plugin_event.data.user_id
        if isinstance(tmp_reast_str, str) and tmp_reast_str.startswith('休息') and (not _allow_ms_command_for_context(target_user_id)):
            plugin_event.set_block()
            return

        pc_info = _get_target_pc(plugin_event, tmp_hagID, target_user_id, dictTValue)
        pc_info['hagId'] = tmp_hagID

        skill_table = pc_info['skillTable']
        pcHash = pc_info['pcHash']
        pcName = pc_info['pcName']

        # 死亡豁免
        if tmp_reast_str == '死亡':
            rd_expr = '1D10'
            rd = _roll(rd_expr, ms_customDefault)
            if rd.resError is not None:
                dictTValue['tResult'] = str(rd.resError)
                replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMError'], dictTValue))
                plugin_event.set_block()
                return

            d10 = int(rd.resInt)
            dictTValue['tDiceProcess'] = _format_rd_roll_text(rd_expr, rd)
            if d10 == 0:
                wake_minutes = int(_roll('2D10', ms_customDefault).resInt)
                hp_loss = int(_roll('1D5', ms_customDefault).resInt)
                death_text_raw = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMSDeathSave0'], dictTValue)
                death_text_raw = death_text_raw.replace('{2D10}', str(wake_minutes)).replace('{1D5}', str(hp_loss))
                dictTValue['tDeathText'] = _eval_inline_dice(death_text_raw, ms_customDefault)

                # 生命值上限永久减少，并触发自动群名片更新
                if pcName is not None:
                    cur_hpmax = _pc_get_skill_int(pcHash, tmp_hagID, '生命值上限', default=0)
                    if cur_hpmax == 0:
                        cur_hp = _pc_get_skill_int(pcHash, tmp_hagID, '生命值', default=0)
                        cur_hpmax = cur_hp
                    new_hpmax = cur_hpmax - hp_loss
                    if new_hpmax < 0:
                        new_hpmax = 0
                    OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
                        pcHash = pcHash,
                        skillName = '生命值上限',
                        skillValue = new_hpmax,
                        pcCardName = pcName,
                        hagId = tmp_hagID
                    )
                    cur_hp = _pc_get_skill_int(pcHash, tmp_hagID, '生命值', default=0)
                    if cur_hp > new_hpmax:
                        OlivaDiceCore.pcCard.pcCardDataSetBySkillName(
                            pcHash = pcHash,
                            skillName = '生命值',
                            skillValue = new_hpmax,
                            pcCardName = pcName,
                            hagId = tmp_hagID
                        )
                    try:
                        OlivaDiceCore.msgReply.trigger_auto_sn_update(
                            plugin_event,
                            target_user_id,
                            pc_info['platform'],
                            tmp_hagID,
                            dictTValue
                        )
                    except Exception:
                        pass

            elif d10 <= 4:
                rounds = int(_roll('1D5', ms_customDefault).resInt)
                death_text_raw = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMSDeathSave1to4'], dictTValue)
                death_text_raw = death_text_raw.replace('{1D5}', str(rounds))
                dictTValue['tDeathText'] = _eval_inline_dice(death_text_raw, ms_customDefault)
            else:
                dictTValue['tDeathText'] = _eval_inline_dice(
                    OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMSDeathSave5plus'], dictTValue),
                    ms_customDefault
                )

            if at_user_id:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMDeathResultAtOther'], dictTValue)
            else:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMDeathResult'], dictTValue)
            replyMsg(plugin_event, tmp_reply_str)
            plugin_event.set_block()
            return

        # 获取检定值（数字/表达式/技能）
        def _get_worst_save(pcHash, hagId, ms_template: dict):
            try:
                if type(ms_template) is dict:
                    skill_def = ms_template.get('skill')
                    if type(skill_def) is dict:
                        save_list = skill_def.get('豁免')
                        if type(save_list) is list and len(save_list) > 0:
                            worst_name = None
                            worst_val = None
                            for k in save_list:
                                v = _pc_get_skill_int(pcHash, hagId, str(k), default=0)
                                if worst_val is None or v < worst_val:
                                    worst_val = int(v)
                                    worst_name = str(k)
                            if worst_val is None:
                                return (None, 0)
                            return (worst_name, int(worst_val))
            except Exception:
                pass
            return (None, 0)

        is_rest = False
        val_raw = tmp_reast_str
        skill_name_for_result = val_raw
        parsed_expr_skill_name = None
        parsed_expr_value_text = None
        rest_save_name = None

        if isinstance(val_raw, str) and val_raw.startswith('休息'):
            is_rest = True

        if val_raw == '休息':
            rest_save_name, check_value = _get_worst_save(pcHash, tmp_hagID, ms_template)
            if rest_save_name not in [None, '']:
                skill_name_for_result = str(rest_save_name)
        else:
            if val_raw.isdecimal():
                check_value = int(val_raw)
            else:
                # 技能名用 pcCard 取值；表达式仍走 core 的 expression 解析
                if _is_plain_skill_name(val_raw):
                    check_value = _pc_get_skill_int(pcHash, tmp_hagID, val_raw, default=0)
                else:
                    # 完全参考 core `.ra`：形如“技能名+10/技能名-1D5”等，先取技能值再计算
                    op_list = []
                    try:
                        op_list = OlivaDiceCore.msgReplyModel.op_list_get()
                    except Exception:
                        op_list = ['+', '-', '*', '/', '%', '^']

                    tmp_skill_name = None
                    tmp_expr_suffix = None
                    try:
                        skill_end_pos = len(val_raw)
                        for i, ch in enumerate(val_raw):
                            if ch in op_list or ch.isdigit():
                                skill_end_pos = i
                                break
                        tmp_skill_name = val_raw[:skill_end_pos].strip()
                        tmp_expr_suffix = val_raw[skill_end_pos:].strip()
                    except Exception:
                        tmp_skill_name = None
                        tmp_expr_suffix = None

                    if tmp_skill_name and tmp_expr_suffix and tmp_expr_suffix[0] in op_list:
                        # 休息+X：休息代表最差豁免值，不查“休息”本身
                        if tmp_skill_name == '休息':
                            rest_save_name, base_value = _get_worst_save(pcHash, tmp_hagID, ms_template)
                            if rest_save_name not in [None, '']:
                                skill_name_for_result = str(rest_save_name)
                        else:
                            base_value = _pc_get_skill_int(pcHash, tmp_hagID, tmp_skill_name, default=0)
                        full_expr = f"{int(base_value)}{tmp_expr_suffix}"
                        rd_skill = _roll(full_expr, ms_customDefault)
                        if rd_skill.resError is not None:
                            dictTValue['tResult'] = str(rd_skill.resError)
                            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMError'], dictTValue))
                            plugin_event.set_block()
                            return
                        check_value = int(rd_skill.resInt)
                        # 显示/结果：优先用休息对应的最差豁免技能名
                        if tmp_skill_name == '休息' and rest_save_name not in [None, '']:
                            parsed_expr_skill_name = str(rest_save_name)
                        else:
                            skill_name_for_result = str(tmp_skill_name)
                            parsed_expr_skill_name = str(tmp_skill_name)
                        parsed_expr_value_text = _format_rd_final_only(full_expr, rd_skill)
                    else:
                        [processed_expr, expr_show] = OlivaDiceCore.msgReply.getExpression(
                            data = val_raw,
                            reverse = False,
                            valueTable = skill_table,
                            pcCardRule = pc_info['pcRule'],
                            flagDynamic = True,
                            ruleMode = 'default'
                        )
                        if processed_expr in [None, '']:
                            dictTValue['tResult'] = '表达式解析失败'
                            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMError'], dictTValue))
                            plugin_event.set_block()
                            return
                        rd_skill = _roll(processed_expr, ms_customDefault)
                        if rd_skill.resError is not None:
                            dictTValue['tResult'] = str(rd_skill.resError)
                            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMError'], dictTValue))
                            plugin_event.set_block()
                            return
                        check_value = int(rd_skill.resInt)

        # 压力惩罚
        cStress = _pc_get_skill_int(pcHash, tmp_hagID, '压力', default=0)
        stress_min = _pc_get_skill_int(pcHash, tmp_hagID, '压力下限', default=2)
        if cStress == 0:
            cStress = stress_min
        penalty = max(0, cStress - 20)
        final_check = max(0, int(check_value) - penalty)

        tmp_skill_name = None
        tmp_skill_value_show = None
        if is_rest:
            tmp_skill_name = rest_save_name if rest_save_name not in [None, ''] else '休息'
            tmp_skill_value_show = parsed_expr_value_text if parsed_expr_value_text not in [None, ''] else str(final_check)
        elif parsed_expr_skill_name is not None:
            tmp_skill_name = parsed_expr_skill_name
            tmp_skill_value_show = parsed_expr_value_text if parsed_expr_value_text not in [None, ''] else str(final_check)
        elif isinstance(val_raw, str) and (not val_raw.isdecimal()):
            tmp_skill_name = val_raw
            tmp_skill_value_show = str(final_check)
        dictTValue['tSkillName'] = '' if tmp_skill_name is None else str(tmp_skill_name)
        dictTValue['tSkillValue'] = str(final_check) if tmp_skill_value_show is None else str(tmp_skill_value_show)
        dictTValue['tSkillShow'] = (
            ('%s:%s' % (dictTValue['tSkillName'], dictTValue['tSkillValue']))
            if dictTValue['tSkillName'] not in ['', None]
            else dictTValue['tSkillValue']
        )

        # 掷骰（展示格式严格对齐 core onedice：expr[=detail]=int）
        rd_main_expr = '1D100'
        if type(ms_template) is dict and 'mainDice' in ms_template:
            rd_main_expr = ms_template.get('mainDice', '1D100')

        rd_expr = rd_main_expr
        if flag_bp_type != 0:
            # b/p 转换为取低/取高：默认2骰，b2/p2为3骰...
            dice_num = max(2, int(flag_bp_count) + 1)
            # 按要求：b=kh，p=kl
            rd_expr = '%dD100%s' % (dice_num, 'kh' if flag_bp_type == 1 else 'kl')

        dice_rd = _roll(rd_expr, ms_customDefault)
        if dice_rd.resError is not None:
            dictTValue['tResult'] = str(dice_rd.resError)
            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMError'], dictTValue))
            plugin_event.set_block()
            return

        final_dice = int(dice_rd.resInt)
        process_text = '%s/%d' % (_format_rd_roll_text(rd_expr, dice_rd), final_check)
        if bp_mark:
            process_text = '%s %s' % (bp_mark, process_text)

        # 结果判定（用skillCheck）
        tmpSkillCheckType = _ms_skillcheck_type(final_dice, final_check, ms_template)
        dictTValue['tSkillCheckReasult'] = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
            tmpSkillCheckType,
            dictStrCustom,
            dictTValue,
            pcHash = pcHash,
            pcCardName = pcName,
            user_id = target_user_id,
            skill_name = skill_name_for_result,
            platform = pc_info['platform'],
            botHash = plugin_event.bot_info.hash,
            hagId = tmp_hagID
        )

        is_failure = tmpSkillCheckType in [
            OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL,
            OlivaDiceCore.skillCheck.resultType.SKILLCHECK_GREAT_FAIL
        ]

        dictTValue['tStressChange'] = _handle_stress_change(
            plugin_event,
            pc_info,
            dictTValue,
            dictStrCustom,
            is_failure,
            is_rest,
            final_dice
        )

        dictTValue['tDiceProcess'] = process_text
        dictTValue['tExtra'] = ''

        if is_rest:
            dictTValue['tRMTitle'] = '休息豁免'
        else:
            title_skill = parsed_expr_skill_name if parsed_expr_skill_name not in [None, ''] else val_raw
            if _is_plain_skill_name(title_skill):
                dictTValue['tRMTitle'] = f"{title_skill}{'豁免' if _is_ms_save_skill(title_skill, ms_template) else '检定'}"
            else:
                dictTValue['tRMTitle'] = f"[{val_raw}]检定"

        has_skill_name = dictTValue.get('tSkillName') not in ['', None]

        if at_user_id:
            if has_skill_name:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMResultWithSkillNameAtOther'], dictTValue)
            else:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMResultAtOther'], dictTValue)
        else:
            if has_skill_name:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMResultWithSkillName'], dictTValue)
            else:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strRMResult'], dictTValue)

        replyMsg(plugin_event, tmp_reply_str)
        plugin_event.set_block()
        return

    # ===== .mp =====
    if isMatchWordStart(tmp_reast_str, 'mp', isCommand = True):
        is_at, at_user_id, tmp_reast_str = OlivaDiceCore.msgReply.parse_at_user(
            plugin_event, tmp_reast_str, valDict, flag_is_from_group_admin
        )
        if is_at and not at_user_id:
            return

        tmp_reast_str = getMatchWordStartRight(tmp_reast_str, 'mp')
        tmp_reast_str = skipSpaceStart(tmp_reast_str).rstrip(' ')

        if tmp_reast_str.lower() == 'help':
            try:
                OlivaDiceCore.msgReply.replyMsgLazyHelpByEvent(plugin_event, 'mp')
            except Exception:
                pass
            return

        target_user_id = at_user_id if at_user_id else plugin_event.data.user_id
        pc_info = _get_target_pc(plugin_event, tmp_hagID, target_user_id, dictTValue)
        pc_info['hagId'] = tmp_hagID
        skill_table = pc_info['skillTable']

        rd_expr = '1D20'
        rd = _roll(rd_expr, ms_customDefault)
        if rd.resError is not None:
            dictTValue['tResult'] = str(rd.resError)
            replyMsg(plugin_event, OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMPError'], dictTValue))
            return

        d20 = int(rd.resInt)
        stress = _pc_get_skill_int(pc_info['pcHash'], tmp_hagID, '压力', default=0)
        stress_min = _pc_get_skill_int(pc_info['pcHash'], tmp_hagID, '压力下限', default=2)
        stress_max = _pc_get_skill_int(pc_info['pcHash'], tmp_hagID, '压力上限', default=20)
        if stress == 0:
            stress = stress_min
        stress_show = min(stress, stress_max)

        dictTValue['tDiceProcess'] = '%s/%d' % (_format_rd_roll_text(rd_expr, rd), stress_show)
        dictTValue['tPanicEffect'] = ''

        if d20 > stress_show:
            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_SUCCESS
            dictTValue['tSkillCheckReasult'] = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
                tmpSkillCheckType,
                dictStrCustom,
                dictTValue,
                pcHash = pc_info['pcHash'],
                pcCardName = pc_info['pcName']
            )
        else:
            tmpSkillCheckType = OlivaDiceCore.skillCheck.resultType.SKILLCHECK_FAIL
            dictTValue['tSkillCheckReasult'] = OlivaDiceCore.msgReplyModel.get_SkillCheckResult(
                tmpSkillCheckType,
                dictStrCustom,
                dictTValue,
                pcHash = pc_info['pcHash'],
                pcCardName = pc_info['pcName']
            )
            dictTValue['tPanicEffect'] = _draw_panic(d20, ms_customDefault)

        if at_user_id:
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMPResultAtOther'], dictTValue)
        else:
            tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strMPResult'], dictTValue)
        replyMsg(plugin_event, tmp_reply_str)
        return

    return
