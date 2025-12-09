# -*- encoding: utf-8 -*-
'''
这里写你的自定义回复
'''

import OlivOS
import OlivaDiceCore
import OlivaDiceTA

dictStrCustomDict = {}

dictStrCustom = {
    'strTAResult': '[{tName}]进行三角机构检定\n骰子: {tDiceResult}\n{tBurnout}{tThreeCount}{tSkillCheckReasult}{tChaosChange}',
    'strTAResultMulti': '[{tName}]进行{tRollTimes}次三角机构检定\n{tMultiResults}{tChaosChange}',
    'strTAResultAtOther': '[{tUserName}]帮[{tName}]进行三角机构检定\n骰子: {tDiceResult}\n{tBurnout}{tThreeCount}{tSkillCheckReasult}{tChaosChange}',
    'strTAResultMultiAtOther': '[{tUserName}]帮[{tName}]进行{tRollTimes}次三角机构检定\n{tMultiResults}{tChaosChange}',
    'strTAError': '三角机构检定错误: {tResult}\n请通过.help ta查看正确检定格式',
    'strTAInvalidSelection': '输入了无效的选项或超时，请重新投掷',
    'strCSShow': '当前群组混沌值: {tChaosValue}',
    'strCSChange': '混沌值: {tOldChaos} -> {tNewChaos}{tExprDetail}',
    'strFSShow': '当前群组现实改写失败次数: {tFailValue}',
    'strFSChange': '现实改写失败次数: {tOldFail} -> {tNewFail}{tExprDetail}',
    'strThreeCount': '本次骰出了{tThreeNum}个3\n',
    'strThreeCountWithBurnout': '本次投出了{tThreeBefore}个3，过载{tBurnoutNum}个，剩下{tThreeAfter}个3\n',
    'strChaosChange': '\n混沌值+{tChaosGen}: {tOldChaos}->{tNewChaos}',
    'strFailChange': '\n现实改写失败+{tFailGen}: {tOldFail}->{tNewFail}',
    'strD6Bonus': '\nD6增益: {tD6Result}{tD6Effect}',
    'strTAResultSimple': '[{tName}]进行D10三角检定\nD10: {tD10Result}\n{tSkillCheckReasult}{tChaosChange}',
    'strTAResultSimpleAtOther': '[{tUserName}]帮[{tName}]进行D10三角检定\nD10: {tD10Result}\n{tSkillCheckReasult}{tChaosChange}',
    'strTRAResult': '[{tName}]进行D20资质检定: {tSkillName}\n{tDiceExpr}\n{tSkillCheckReasult}{tChaosChange}',
    'strTRAResultAtOther': '[{tUserName}]帮[{tName}]进行D20资质检定: {tSkillName}\n{tDiceExpr}\n{tSkillCheckReasult}{tChaosChange}',
    'strTRAResultMulti': '[{tName}]进行{tRollTimes}次D20资质检定: {tSkillName}\n{tMultiResults}{tChaosChange}',
    'strTRAResultMultiAtOther': '[{tUserName}]帮[{tName}]进行{tRollTimes}次D20资质检定: {tSkillName}\n{tMultiResults}{tChaosChange}',
    'strTRAError': 'D20检定错误: {tResult}\n请通过.help tra查看正确检定格式',
}

dictStrConst = {
}

dictGValue = {
}

dictTValue = {
    'tDiceResult': '0',
    'tBurnout': '',
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
    'tExprDetail': '',
    'tThreeCount': '',
    'tThreeNum': '0',
    'tChaosGen': '0',
    'tFailGen': '0',
    'tD6Result': '',
    'tD6Effect': '',
    'tD10Result': '',
    'tD20Result': '',
    'tAptitude': '0',
    'tTotalResult': '0',
    'tSkillName': ''
}

dictStrCustomNote = {
    'strTAResult': '【.ta/.tr】指令\n进行三角机构检定',
    'strTAResultMulti': '【.ta/.tr】指令\n进行多次三角机构检定',
    'strTAResultAtOther': '【.ta/.tr】指令\n代骰三角机构检定',
    'strTAResultMultiAtOther': '【.ta/.tr】指令\n代骰多次三角机构检定',
    'strTAError': '【.ta/.tr】指令\n检定错误提示',
    'strTAInvalidSelection': '【.ta/.tr】指令\n无效选择提示',
    'strCSShow': '【.tcs】指令\n显示混沌值',
    'strCSChange': '【.tcs】指令\n混沌值变化',
    'strFSShow': '【.tcs】指令\n显示现实改写失败次数',
    'strFSChange': '【.tcs】指令\n现实改写失败次数变化',
    'strThreeCount': '【.ta/.tr】指令\n显示本次骰出的3的数量',
    'strThreeCountWithBurnout': '【.ta/.tr】指令\n显示本次投出的3、过载和剩余的3的数量(有过载时)',
    'strChaosChange': '【.ta/.tr/.tra】指令\n混沌值变化提示',
    'strFailChange': '【.tr】指令\n现实改写失败变化提示',
    'strD6Bonus': '【.ta/.tr】指令\ng参数D6增益显示',
    'strTAResultSimple': '【.ta/.tr】指令\ns参数D10检定结果',
    'strTAResultSimpleAtOther': '【.ta/.tr】指令\ns参数代骰D10检定结果',
    'strTRAResult': '【.tra】指令\nD20检定结果',
    'strTRAResultAtOther': '【.tra】指令\n代骰D20检定结果',
    'strTRAResultMulti': '【.tra】指令\n多次D20检定结果',
    'strTRAResultMultiAtOther': '【.tra】指令\n代骰多次D20检定结果',
    'strTRAError': '【.tra】指令\nD20检定错误提示'
}

dictHelpDocTemp = {
    'ta': '''【三角机构检定】
.ta(c)(g)(s)(b数字)(p数字)(资质/数值) (@其他人)
.tr(c)(f)(g)(s)(b数字)(p数字)(资质/数值) (@其他人)
.ta数字#资质/数值 (@其他人) - 多次投掷

参数说明：
- c：不增加混沌值
- f：不增加现实改写失败次数（仅.tr有效，.ta本身就不产生失败）
- g：额外投掷D6增益骰，D6=3增加1个3，D6=6增加2个3，其他结果增加1点混沌
- s：D10检定模式，用1D10代替6D4，结果决定3的个数和混沌值
- b数字：强制将数字个非3的骰子改为3
- p数字：强制将数字个3的骰子改为非3并增加混沌值（过载增加，可以燃掉g参数的3）
- 资质/数值：资质称或数值，默认为0（无过载检定）
- @其他人：代其他人投掷

参数组合：
- g和s可以同时使用（D10+D6增益）
- 过载会燃掉所有3（包括D6增益的3）

命令区别：
- .ta：普通检定，不产生现实改写失败
- .tr：现实改写检定，失败时会增加现实改写失败次数

例子：
.ta 专注 - 使用专注技能检定
.ta g 专注 - 额外投掷D6增益骰
.ta s - 使用D10检定模式
.ta sg - D10模式+D6增益
.ta3#专注@张三 - 代张三进行3次专注检定''',

    'tcs': '''【混沌值消耗】
.tcs - 查看当前混沌值
.tcs 数值 - 消耗指定数值的混沌值
.tcs +/-数值 - 增减混沌值
.tcs st 数值 - 设置混沌值''',

    'tfs': '''【现实改写失败管理】
.tfs - 查看当前现实改写失败次数
.tfs +/-数值 - 增减失败次数''',

    'tra': '''【D20检定】
.tra(c)(资质/数值) (@其他人)
.tra数字#(c)(资质/数值) (@其他人) - 多次投掷

检定规则：
- 投掷D20 + 资质点数，总数>10为成功
- 成功不增加混沌值
- 失败增加D20骰出点数的混沌值

特殊判定：
- D20=3 - 三重升华（大成功），不增加混沌
- D20=7 - 必定失败（无论总数多少）

参数说明：
- c：失败也不增加混沌值
- 资质/数值：资质或数值，默认为0

例子：
.tra 专注 - 使用专注技能进行D20检定
.tra c 10 - 失败不增加混沌，资质为10
.tra @张三 - 代张三进行D20检定
.tra3#专注 - 进行3次专注D20检定''',

    '三角机构': '''【三角机构TRPG系统指令汇总】

检定指令：
.ta(c)(g)(s)(b数字)(p数字)(资质/数值) (@其他人) - 普通检定
.tr(c)(f)(g)(s)(b数字)(p数字)(资质/数值) (@其他人) - 现实改写检定
.tra(c)(资质/数值) (@其他人) - D20检定
.ta数字#资质/数值 (@其他人) - 多次检定
.tra数字#资质/数值 (@其他人) - 多次D20检定

数据管理：
.tcs - 混沌值管理（查看/消耗/修改）
.tfs - 现实改写失败管理
.tcsst 数值 - 设置混沌值

参数说明：
- c：不增加混沌值
- f：不增加现实改写失败次数（仅.tr有效）
- g：额外投掷D6增益骰（可与s同时使用，过载可燃掉增益的3）
- s：D10检定模式（1D10代替6D4，可与g同时使用）
- b数字：强制将数字个非3的骰子改为3
- p数字：强制将数字个3的骰子改为非3并增加混沌值

详细帮助：
.help ta - 查看检定详细说明
.help tra - 查看D20检定说明
.help tcs - 查看混沌值消耗说明
.help tfs - 查看现实改写失败说明''',

    'tr': '&ta',

    '三角机构st':'''【三角机构跑团数据录入帮助文档】
1、将骰子拉入群聊后，请先使用[.set temp ta]，让本群套用三角机构模板（只需输入一次，其他人无需再输入）
2、玩家在填写完角色卡并审核通过后，录入属性，按照这样的格式：[.st 人物名-属性1数值1属性2数值2……]这样就完成了基础数据的录入。
3、玩家输入[.sn]或者[.sn template]，改变名片格式。
4、玩家输入[.sn auto on]，让名片数据能够自动变化。（三角机构只有名字无需.sn auto on）''',

    'tast': '&三角机构st'
}