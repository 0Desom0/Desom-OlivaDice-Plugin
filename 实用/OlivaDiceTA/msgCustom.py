# -*- encoding: utf-8 -*-
'''
这里写你的自定义回复
'''

import OlivOS
import OlivaDiceCore
import OlivaDiceTA

dictStrCustomDict = {}

dictStrCustom = {
    'strTAResult': '[{tName}]进行三角机构检定\n骰子: {tDiceResult}\n{tBurnout}{tSkillCheckReasult}\n{tChaosChange}',
    'strTAResultMulti': '[{tName}]进行{tRollTimes}次三角机构检定\n{tMultiResults}\n{tChaosChange}',
    'strTAResultAtOther': '[{tUserName}]帮[{tName}]进行三角机构检定\n骰子: {tDiceResult}\n{tBurnout}{tSkillCheckReasult}\n{tChaosChange}',
    'strTAResultMultiAtOther': '[{tUserName}]帮[{tName}]进行{tRollTimes}次三角机构检定\n{tMultiResults}\n{tChaosChange}',
    'strTAError': '三角机构检定错误: {tResult}\n请通过.help ta查看正确检定格式',
    'strTAInvalidSelection': '输入了无效的选项或超时，请重新投掷',
    'strCSShow': '当前群组混沌值: {tChaosValue}',
    'strCSChange': '混沌值: {tOldChaos} -> {tNewChaos}{tExprDetail}',
    'strFSShow': '当前群组现实改写失败次数: {tFailValue}',
    'strFSChange': '现实改写失败次数: {tOldFail} -> {tNewFail}{tExprDetail}',
}

dictStrConst = {
}

dictGValue = {
}

dictTValue = {
    'tDiceResult': '0',
    'tBurnout': '0',
    'tSkillCheckReasult': '',
    'tChaosChange': '',
    'tChaosValue': '0',
    'tOldChaos': '0',
    'tNewChaos': '0',
    'tFailValue': '0',
    'tOldFail': '0',
    'tNewFail': '0',
    'tResult': '',
    'tRollTimes': '1',
    'tMultiResults': '',
    'tExprDetail': ''
}

dictStrCustomNote = {
    'strTAResult': '【.ta/.tr】指令\n进行三角机构检定',
    'strTAResultMulti': '【.ta/.tr】指令\n进行多次三角机构检定',
    'strTAResultAtOther': '【.ta/.tr】指令\n代投三角机构检定',
    'strTAResultMultiAtOther': '【.ta/.tr】指令\n代投多次三角机构检定',
    'strTAError': '【.ta/.tr】指令\n检定错误提示',
    'strTAInvalidSelection': '【.ta/.tr】指令\n无效选择提示',
    'strCSShow': '【.tcs】指令\n显示混沌值',
    'strCSChange': '【.tcs】指令\n混沌值变化',
    'strFSShow': '【.tfs】指令\n显示现实改写失败次数',
    'strFSChange': '【.tfs】指令\n现实改写失败次数变化'
}

dictHelpDocTemp = {
    'ta': '''【三角机构检定】
.ta(c)(b数字)(p数字)(技能名/数值) (@其他人)
.tr(c)(f)(b数字)(p数字)(技能名/数值) (@其他人)
.ta数字#技能名/数值 (@其他人) // 多次投掷

参数说明：
- c：不增加混沌值
- f：不增加现实改写失败次数（仅.tr有效，.ta本身就不产生失败）
- b数字：强制将数字个非3的骰子改为3
- p数字：强制将数字个3的骰子改为非3并增加混沌值（燃尽增加）
- 技能名/数值：技能名称或数值，默认为0（无燃尽检定）
- @其他人：代其他人投掷

命令区别：
- .ta：普通检定，不产生现实改写失败
- .tr：现实改写检定，失败时会增加现实改写失败次数

例子：
.ta 专注        // 使用专注技能检定
.ta c b2 10     // 不增加混沌，强制2个非3改为3，检定数值10
.tr p1 侦查     // 现实改写检定，强制1个3改为非3
.ta3#专注@张三  // 代张三进行3次专注检定''',

    'tcs': '''【混沌值消耗】
.tcs            // 查看当前混沌值
.tcs 数值       // 消耗指定数值的混沌值
.tcs +/-数值    // 增减混沌值
.tcsst 数值     // 设置混沌值''',

    'tfs': '''【现实改写失败管理】
.tfs            // 查看当前现实改写失败次数
.tfs +/-数值    // 增减失败次数''',

    '三角机构': '''【三角机构TRPG系统指令汇总】

检定指令：
.ta(c)(b数字)(p数字)(技能名/数值) (@其他人)           // 普通检定
.tr(c)(f)(b数字)(p数字)(技能名/数值) (@其他人)       // 现实改写检定
.ta数字#技能名/数值 (@其他人)                        // 多次检定

数据管理：
.tcs              // 混沌值管理（查看/消耗/修改）
.tfs              // 现实改写失败管理
.tcsst 数值       // 设置混沌值

参数说明：
- c：不增加混沌值
- f：不增加现实改写失败次数（仅.tr有效）
- b数字：强制将数字个非3的骰子改为3
- p数字：强制将数字个3的骰子改为非3并增加混沌值

详细帮助：
.help ta/tr       // 查看检定详细说明
.help tcs         // 查看混沌值消耗说明
.help tfs         // 查看现实改写失败说明''',

    'tr': '&ta',

    '三角机构st':'''【三角机构跑团数据录入帮助文档】
1、将骰子拉入群聊后，请先使用[.set temp ta]，让本群套用三角机构模板（只需输入一次，其他人无需再输入）
2、玩家在填写完角色卡并审核通过后，录入属性，按照这样的格式：[.st 人物名-属性1数值1属性2数值2……]这样就完成了基础数据的录入。
3、玩家输入[.sn]或者[.sn template]，改变名片格式。
4、玩家输入[.sn auto on]，让名片数据能够自动变化。（三角机构只有名字无需.sn auto on）''',

    'tast': '&三角机构st'
}