# -*- encoding: utf-8 -*-
'''
这里写你的自定义回复
'''

import OlivOS
import OlivaDiceCore
import OlivaDiceCats

dictStrCustomDict = {}

dictStrCustom = {
    'strCatsResult': '[{tName}]进行喵影奇谋检定{tChallengeTarget}\n{tRerollInfo}出值: {tFrontResult}+{tLuckDiceResult}={tTotalResult}\n挑战难度: {tBackResult} {tSkillCheckReasult}\n{tSuccessLevel}',
    'strCatsCriticalResult': '[{tName}]进行喵影奇谋检定{tChallengeTarget}\n幸运骰({tLuckValue}个): {tLuckDiceList}\n{tSkillCheckReasult}',
    'strCatsLuckDice': '幸运骰({tLuckValue}个): {tLuckDiceList}\n请选择1-{tLuckValue}：',
    'strCatsError': '喵影奇谋检定错误: {tResult}\n请通过.help cats查看正确检定格式；录卡规则请通过.help catsst查看',
    'strCatsInvalidSelection': '输入了无效的选项或超时，请重新投掷',
    'strCatsSuccessLevel': '成功等级: {tSuccessLevelProcess}',
    'strCatsaResult': '[{tName}]进行喵影奇谋检定{tChallengeTarget}（自动最高值）\n幸运骰({tLuckValue}个): {tLuckDiceList}\n{tRerollInfo}出值: {tFrontResult}+{tLuckDiceResult}={tTotalResult}\n挑战难度: {tBackResult} {tSkillCheckReasult}\n{tSuccessLevel}',
    'strCatsaCriticalResult': '[{tName}]进行喵影奇谋检定{tChallengeTarget}（自动最高值）\n幸运骰({tLuckValue}个): {tLuckDiceList}\n{tSkillCheckReasult}',
    'strCatsaError': '喵影奇谋检定错误: {tResult}\n请通过.help catsa查看正确检定格式；录卡规则请通过.help catsst查看'
}

dictStrConst = {
}

dictGValue = {
}

dictTValue = {
    'tFrontResult': '0',
    'tLuckDiceResult': '0',  
    'tTotalResult': '0',
    'tBackResult': '0',
    'tSkillCheckReasult': '',
    'tSuccessLevel': '',
    'tSuccessLevelInt': '0',
    'tSuccessLevelProcess': '',
    'tLuckValue': '1',
    'tLuckDiceList': '',
    'tRerollInfo': '',
    'tResult': '',
    'tChallengeTarget': ''
}

dictStrCustomNote = {
    'strCatsResult': '【.cats】指令\n进行喵影奇谋检定，显示挑战目标',
    'strCatsCriticalResult': '【.cats】指令\n直接大成功/大失败结果',
    'strCatsLuckDice': '【.cats】指令\n显示幸运骰并等待选择',
    'strCatsError': '【.cats】指令\n检定错误或超时提示',
    'strCatsInvalidSelection': '【.cats】指令\n无效选择提示',
    'strCatsSuccessLevel': '【.cats】指令\n成功等级',
    'strCatsaResult': '【.catsa】指令\n进行喵影奇谋检定（自动选择最高值），显示挑战目标',
    'strCatsaCriticalResult': '【.catsa】指令\n直接大成功/大失败结果（自动选择最高值）',
    'strCatsaError': '【.catsa】指令\n检定错误提示'
}

dictHelpDocTemp = {
    '喵影奇谋': '''【喵影奇谋模块 - 总帮助】

本模块提供喵影奇谋跑团规则的检定系统，支持以下功能：

检定指令：
• .cats - 标准喵影奇谋检定（需手动选择幸运骰）
• .catsa - 自动最高值检定（自动选择最高值幸运骰）

详细帮助：
• .help cats - 查看.cats指令详细说明
• .help catsa - 查看.catsa指令详细说明  
• .help catsst - 查看人物卡录入帮助''',
    'cats': '''【喵影奇谋检定】
支持新版本Core时，Markdown回复中的骰点结果会按代码保护。
.cats(b/p数字)(u/d数字)(l数字)(前式)#(b/p数字)(u/d数字)(l数字)(挑战难度)(@其他人)

参数说明：
- 前式：可以是数字或表达式，如10、2d6+10等
- 挑战难度：目标数值或表达式
- @其他人：后式使用他人人物卡中的技能值
- b/p数字：加减的成功等级  
- u/d数字：加减幸运骰的数目（最多5个最少1个）
- l数字：固定幸运骰数目（优先级高于u/d，以最近的l参数为准）

例子：
.cats u1 爪击+1#9
.cats l3 肉垫*2#5+抚摸*2@其他人
.cats b1 u2 侦查#11

检定规则：
1. 根据人物卡幸运属性投掷1-5个d10（可通过参数调整）
2. 若投出10重投，重投出10为大成功；若投出1重投，重投出1为大失败
3. 多个大成功/大失败按数量多的决定结果，相等时可手动选择
4. 挑战难度若为偶数则自动减1变为奇数
5. 前式+选择的d10结果与挑战难度对比，计算基础成功等级
6. 成功等级计算：(基础成功等级+b/p修正)÷2向下取整
7. 最终大成功时幸运+1升级点+1，大失败时幸运-1升级点+1，抵消时均不变
8. 若无挑战难度，则默认为9''',

    'catsa': '''【喵影奇谋检定（自动最高值）】
支持新版本Core时，Markdown回复中的骰点结果会按代码保护。
.catsa(b/p数字)(u/d数字)(l数字)(前式)#(b/p数字)(u/d数字)(l数字)(挑战难度)(@其他人)

说明：与.cats指令完全相同，但自动选择最高值的幸运骰，无需手动选择。

参数说明：
- 前式：可以是数字或表达式，如10、2d6+10等
- 挑战难度：目标数值或表达式
- @其他人：后式使用他人人物卡中的技能值
- b/p数字：加减的成功等级  
- u/d数字：加减幸运骰的数目（最多5个最少1个）
- l数字：固定幸运骰数目（优先级高于u/d，以最近的l参数为准）

例子：
.catsa u1 爪击+1#9
.catsa l3 肉垫*2#5+抚摸*2@其他人
.catsa b1 u2 侦查#11

检定规则：
1. 根据人物卡幸运属性投掷1-5个d10（可通过参数调整）
2. 若投出10重投，重投出10为大成功；若投出1重投，重投出1为大失败
3. 多个大成功/大失败按数量多的决定结果，大成功/大失败数量相等时自动选择最高值
4. 自动选择所有幸运骰中的最高值（不包括大成功/大失败的骰子）
5. 其余规则与.cats指令相同''',

    'catsst': '''【喵影奇谋跑团数据录入帮助文档】
1、将骰子拉入群聊后，请先使用[.set temp cats]，让本群套用喵影奇谋模板（只需输入一次，其他人无需再输入）
2、玩家在填写完角色卡并审核通过后，将附表“猫猫卡”中的.st数据复制粘贴，输入群内，这样就完成了基础数据的录入。
3、玩家输入[.sn]或者[.sn template]，改变名片格式。
4、玩家输入[.sn auto on]，让名片数据能够自动变化。''',
}
