# -*- encoding: utf-8 -*-
'''
@File      :   msgReply.py
@Author    :   Desom-fu
@Contact   :   desom233@outlook.com
@License   :   AGPL
@Copyright :   (C) 2020-2025, OlivOS-Team
@Desc      :   None
'''

import OlivOS
import OlivaDiceCore
import OlivaDiceShouHun

dictStrCustomDict = {}

dictStrCustom = {
    'strShResult': '[{tName}]进行狩魂者检定:\n出值: {tFrontResult}\n挑战值: {tBackResult} {tSkillCheckReasult} {tSuccessLevel}{tShmAdd}',
    'strShHideShow': '[{tName}]进行了暗狩魂者检定',
    'strShHide': '于群[{tGroupId}]中[{tName}]进行狩魂者暗检定:\n出值: {tFrontResult}\n挑战值: {tBackResult} {tSkillCheckReasult} {tSuccessLevel}{tShmAdd}',
    'strShResultAtOther': '[{tUserName}]帮[{tName}]进行狩魂者检定:\n出值: {tFrontResult}\n挑战值: {tBackResult} {tSkillCheckReasult} {tSuccessLevel}{tShmAdd}',
    'strShHideShowAtOther': '[{tUserName}]帮[{tName}]进行了狩魂者暗检定',
    'strShHideAtOther': '于群[{tGroupId}]中[{tUserName}]帮[{tName}]进行暗狩魂者检定:\n出值: {tFrontResult}\n挑战值: {tBackResult} {tSkillCheckReasult} {tSuccessLevel}{tShmAdd}',
    'strShSuccessLevel': '成功等级: {tSuccessLevelInt}',
    'strShShmAdd': '\nshm: {tShmOld}+{tShmAddValue}={tShmNew}',
    'strShError': '狩魂者检定错误: {tResult}\n查询正确检定指令请使用.help sh查看\n录卡规则请使用.help shst查看'
}

dictStrConst = {
}

dictGValue = {
}

dictTValue = {
}

dictStrCustomNote = {
    'strShResult': '【.sh】指令\n进行狩魂者检定',
    'strShHideShow': '【.sh】指令\n进行暗狩魂者检定回复词（群内）',
    'strShHide': '【.sh】指令\n进行暗狩魂者检定回复词（结果）',
    'strShResultAtOther': '【.sh】代骰指令\n代他人进行狩魂者检定',
    'strShHideShowAtOther': '【.sh】代骰指令\n代他人进行暗狩魂者检定回复词（群内）',
    'strShHideAtOther': '【.sh】代骰指令\n代他人进行暗狩魂者检定回复词（结果）',
    'strShSuccessLevel': '【.sh】指令\n成功等级',
    'strShShmAdd': '【.sh】指令\nshm增加显示',
    'strShError': '【.sh】指令\n检定错误'
}

dictHelpDocTemp = {
    '狩魂者': '''【狩魂者模块 - 总帮助】

本模块提供《鬼喊抓鬼》狩魂者跑团规则的检定系统。

检定指令：
• .sh - 狩魂者检定

详细帮助：
• .help sh - 查看狩魂者检定详细说明
• .help shst - 查看人物卡录入帮助''',

    'sh': '''【狩魂者检定】
.sh(a)(h)(m)(s数字(固定值)kh/kl)(b/p数字)(x数字u/d+)(掷骰表达式)(~掷骰表达式)(#)(a)(s数字(固定值)kh/kl)(b/p数字)(x数字u/d+)(掷骰表达式)

参数说明：
- h：暗骰
- m：移除默认 D20
- s数量(固定值)(kh/kl)：设置 D20 数量与固定值（可设多个，用逗号分隔），并用 kh（取最高）或 kl（取最低）修饰。
- b/p数字：加/减成功等级（默认1）
- x数字(u/d)：指定 1D20 固定值，可选是否向上/向下修正
- a: D20 中的 1 和 2 均视为大失败
- ~ 表达式：将计算结果累加到前式结果及人物卡 shm 属性
- #：分隔前式与后式
- 技能名：自动替换为对应属性值

参数优先级：m > s > x > 表达式D20

检定规则：
- 出式默认带有1D20（可用m参数去除）
- 如果没有#分割，默认挑战值为10
- 成功等级 = (前式-后式)/5 向上取整
- D20大成功/大失败会影响成功等级
- 使用s参数指定多个D20时，每个D20单独计算大成功/大失败
- 挑战值中的D20和固定值也会影响成功等级

示例：
- .shp2x15+4d4+3d6#b1d20+2d4
- .shx10u+灵能力d4#15
- .shh9d4~3d6#15
- .shs5(15,20)
- .shas2kh+5d4''',

    'shst':'''【狩魂者跑团数据录入帮助文档】
1、将骰子拉入群聊后，请先使用[.set temp shouhun]，让本群套用狩魂者模板（只需输入一次，其他人无需再输入）
2、玩家在填写完角色卡并审核通过后，将附表“信息总览表与检定公式”中的.st数据复制粘贴，输入群内，这样就完成了基础数据的录入。
3、玩家输入[.sn]或者[.sn template]，改变名片格式。
4、玩家输入[.sn auto on]，让名片数据能够自动变化。''',

    'shouhun': '&sh',
    '狩魂': '&狩魂者',
    '鬼喊': '&狩魂者',
    '鬼喊抓鬼': '&狩魂者',
}
