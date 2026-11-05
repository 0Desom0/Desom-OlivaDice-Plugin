# -*- encoding: utf-8 -*-
'''
这里写你的自定义回复
'''

import OlivOS
import OlivaDiceCore
import OlivaDiceDH

dictStrCustomDict = {}

dictStrCustom = {
    # .dd 命令相关
    'strDDResult': '[{tName}]{tChallengeReason}进行二元骰检定{tDifficultyDisplay}\n希望骰: {tHopeDice} 恐惧骰: {tFearDice}\n{tModifiersDetail}{tHopeConsume}{tHopeWarning}总点数: {tTotalDisplay}\n{tHelperInfo}{tHopeChange}{tGMFearChange}{tPressureChange}{tFinalResultText}',
    'strChallengeReason': '因为[{tReason}]',
    'strDifficultyDisplay': '，难度: {tDifficulty}',
    'strDDError': '二元骰检定错误: {tResult}\n请通过.help dd查看正确检定格式',
    
    # 检定结果文本
    'strHopeResult': '希望战胜了恐惧！光明指引着前路。|勇气驱散了阴霾，希望之光照亮道路！|内心的光芒战胜了黑暗，前进的道路清晰可见！',
    'strFearResult': '恐惧笼罩了希望...阴霾降临。|黑暗的阴影遮蔽了光明，困难重重...|努力的尝试只带来了恐惧...前路变得模糊不清...',
    
    # 修饰符和希望消耗相关
    'strModifiersDetail': '修饰符: {tModifiers}\n',
    'strHopeConsume': '消耗希望: {tConsumed}({tOld}-{tConsumed}={tNew}/{tMax})\n',
    'strHopeConsumeNoMax': '消耗希望: {tConsumed}({tOld}-{tConsumed}={tNew})\n',
    'strHopeWarning': '[警告] 希望不足,跳过修饰符: {tSkipped}\n',
    'strHopeChange': '希望点: {tNew} ({tNew}/{tMax}) = {tOld}{tDetail}\n',
    'strHopeChangeNoMax': '希望点: {tNew} = {tOld}{tDetail}\n',
    'strHopeAlreadyMax': '希望点: {tOld} ({tOld}/{tMax})(已达上限)\n',
    'strPressureChange': '压力: {tNew} ({tNew}/{tMax}) = {tOld}{tChange}\n',
    'strPressureChangeNoMax': '压力: {tNew} = {tOld}{tChange}\n',
    'strPressureAlreadyZero': '压力已为0\n',
    
    # 帮助者相关
    'strHelperSuccess': '[{tHelperName}]提供帮助! 希望点: {tHelperHopeCurrent}={tHelperHopeChange}\n',
    'strHelperFailNoCard': '[{tHelperName}]无法帮助: 未找到人物卡\n',
    'strHelperFailNoHope': '[{tHelperName}]无法帮助: 希望点不足\n',
    
    # .ddr 命令相关
    'strDDRResult': '[{tName}]{tChallengeReason}进行反应二元骰检定{tDifficultyDisplay}\n希望骰: {tHopeDice} 恐惧骰: {tFearDice}\n{tModifiersDetail}{tHopeConsume}{tHopeWarning}总点数: {tTotalDisplay}\n{tHelperInfo}{tFinalResultText}',
    
    # GM恐惧点变化
    'strGMFearIncrease': '[{tGMName}]的恐惧点: {tGMFearNew}({tGMFearDisplay})={tGMFearOld}+1(恐惧结果)\n',
    'strGMFearMax': '[{tGMName}]的恐惧点: {tGMFearNew}({tGMFearDisplay})={tGMFearOld}+1(已达上限)\n',
    
    # GM管理命令相关
    'strGMSet': '已设置[{tUserName}]为本群GM\n人物卡已切换至: {tCardName}',
    'strGMDel': '已卸任[{tUserName}]的本群GM职位',
    'strGMClear': '已清除本群所有GM记录',
    'strGMError': 'GM管理错误: {tResult}',
    
    # Cook游戏相关
    'strCookStart': '【烹饪开始！】\n出目：\n{tDiceList}\n-----------------\n【第{tRound}轮】\n{tPairResult}\n当前风味：{tCurrentScore}分\n-----------------\n{tNextStep}',
    'strCookContinue': '已移除：{tRemovedDice}\n剩余{tRemainingCount}颗骰子重新投掷：\n{tDiceList}\n-----------------\n【第{tRound}轮】\n{tPairResult}\n当前风味：{tCurrentScore}分（累计）\n-----------------\n{tNextStep}',
    'strCookEnd': '已移除：{tRemovedDice}\n剩余{tRemainingCount}颗骰子重新投掷：\n{tDiceList}\n-----------------\n【第{tRound}轮】\n{tPairResult}\n-----------------\n最终风味：{tFinalScore}分\n{tScoreComment}',
    'strCookError': '错误警告：{tErrorMsg}',
    
    # Cook评价（使用|分隔）
    'strCookScoreLow': '感觉分量有点少...|嗯...很独特的味道...|不管结果怎样，辛苦了...',
    'strCookScoreMid': '🎉 大餐完成了！|🎉 佳肴出炉！|🎉 烹饪大功告成！',
    'strCookScoreHigh': '🌟 杰作！这简直是艺术品！|🌟 完美的料理！太棒了！|🌟 真是美味！堪称大师之作！',
    
    # Cook配对结果
    'strCookPairSuccess': '✓ 配对成功：{tPairCount}组',
    'strCookPairDetail': '• ({tPairValue}, {tPairValue}) → +{tPairValue}分',
    'strCookPairNone': '✓ 配对成功：0组',
    'strCookUnpaired': '✗ 未配对：{tUnpairedCount}颗',
    'strCookAllUsed': '✗ 配对失败，骰子已用尽',
    
    # Cook错误和提示
    'strCookErrorFormat': '参数格式错误\n正确格式：\n  • .cook [ndm]+[ndm]+... - 开始新游戏\n  • .cook [dm]+[dm]+... - dm视为1dm\n  • .cook rm [骰面] - 移除骰子',
    'strCookErrorNoGame': '当前群组没有进行中的烹饪游戏\n请先使用 .cook [ndm]+... 开始游戏',
    'strCookErrorNoDice': '未配对的骰子中没有 d{tRemoveFace}\n可移除的骰面：{tAvailableFaces}',
    'strCookNextStep': '使用 .cook rm [骰面] 移除骰子继续\n可移除：{tAvailableFaces}',
}

dictStrConst = {
}

dictGValue = {
}

dictTValue = {
    'tHopeDice': '0',
    'tFearDice': '0',
    'tModifiersDetail': '',
    'tTotalDisplay': '',
    'tDifficulty': '',
    'tDifficultyDisplay': '',
    'tHopeChange': '',
    'tGMFearChange': '',
    'tPressureChange': '',
    'tFinalResultText': '',
    'tChallengeReason': '',
    'tReason': '',
    'tHelperInfo': '',
    'tHelperName': '',
    'tHelperHopeCurrent': '',
    'tHelperHopeChange': '',
    'tGMName': '',
    'tGMFearOld': '0',
    'tGMFearNew': '0',
    'tGMFearDisplay': '',
    'tResult': '',
    'tCardName': '',
    'tDiceList': '',
    'tRound': '1',
    'tPairResult': '',
    'tPairCount': '0',
    'tPairValue': '0',
    'tUnpairedCount': '0',
    'tCurrentScore': '0',
    'tNextStep': '',
    'tRemovedDice': '',
    'tRemainingCount': '0',
    'tFinalScore': '0',
    'tScoreComment': '',
    'tErrorMsg': '',
    'tGroupId': '',
    'tRemoveFace': '',
    'tAvailableFaces': '',
}

dictStrCustomNote = {
    'strDDResult': '【.dd】指令\n二元骰检定结果',
    'strDDError': '【.dd】指令\n检定错误提示',
    'strDifficultyDisplay': '【.dd/.ddr】指令\n难度显示',
    'strHopeResult': '【.dd】指令\n希望结果文本',
    'strFearResult': '【.dd】指令\n恐惧结果文本',
    'strHelperSuccess': '【.dd】指令\n帮助成功提示',
    'strHelperFailNoCard': '【.dd】指令\n帮助失败-无人物卡',
    'strHelperFailNoHope': '【.dd】指令\n帮助失败-希望点不足',
    'strDDRResult': '【.ddr】指令\n反应二元骰检定结果',
    'strGMFearIncrease': '【.dd】指令\nGM恐惧点增加',
    'strGMFearMax': '【.dd】指令\nGM恐惧点达上限',
    'strChallengeReason': '【.dd/.ddr】指令\n挑战原因文本',
    'strGMSet': '【.gm】指令\n设置GM成功',
    'strGMDel': '【.gm】指令\n卸任GM成功',
    'strGMClear': '【.gm】指令\n清除GM成功',
    'strGMError': '【.gm】指令\nGM管理错误',
    'strCookStart': '【.cook】指令\n烹饪游戏开始',
    'strCookContinue': '【.cook】指令\n烹饪游戏继续',
    'strCookEnd': '【.cook】指令\n烹饪游戏结束',
    'strCookError': '【.cook】指令\n烹饪游戏错误',
    'strCookScoreLow': '【.cook】指令\n低分评价',
    'strCookScoreMid': '【.cook】指令\n中等评价',
    'strCookScoreHigh': '【.cook】指令\n高分评价',
    'strCookPairSuccess': '【.cook】指令\n配对成功',
    'strCookPairDetail': '【.cook】指令\n配对详情',
    'strCookPairNone': '【.cook】指令\n无配对',
    'strCookUnpaired': '【.cook】指令\n未配对骰子',
    'strCookAllUsed': '【.cook】指令\n骰子用尽',
    'strCookErrorFormat': '【.cook】指令\n参数格式错误',
    'strCookErrorNoGame': '【.cook】指令\n无进行中游戏',
    'strCookErrorNoDice': '【.cook】指令\n无此骰面',
    'strCookNextStep': '【.cook】指令\n下一步提示',
    'strModifiersDetail': '【.dd】指令\n修饰符详情',
    'strHopeConsume': '【.dd】指令\n希望消耗显示',
    'strHopeConsumeNoMax': '【.dd】指令\n希望消耗显示(无上限)',
    'strHopeWarning': '【.dd】指令\n希望不足警告',
    'strHopeChange': '【.dd】指令\n希望变化显示',
    'strHopeChangeNoMax': '【.dd】指令\n希望变化显示(无上限)',
    'strHopeAlreadyMax': '【.dd】指令\n希望已达上限提示',
    'strPressureChange': '【.dd】指令\n压力变化显示',
    'strPressureChangeNoMax': '【.dd】指令\n压力变化显示(无上限)',
    'strPressureAlreadyZero': '【.dd】指令\n压力已为0提示',
}

dictHelpDocTemp = {
    '匕首之心': '''【匕首之心模块 - 总帮助】

本模块提供Daggerheart跑团规则的检定系统。

可用命令：
• .dd - 二元骰检定
• .ddr - 反应二元骰检定
• .gm - GM管理
• .cook - 烹饪游戏

详细帮助：
• .help dd - 查看二元骰检定详细说明
• .help ddr - 查看反应二元骰详细说明
• .help gm - 查看GM管理详细说明
• .help cook - 查看烹饪游戏详细说明
• .help dhst - 查看本插件使用说明''',

    'dd': '''【二元骰检定】
支持新版本Core时，Markdown回复中的骰点结果会按代码保护。
.dd [n/m] [修饰符...] [原因]

参数说明：
- n/m：希望骰n面/恐惧骰m面（默认12/12）
- 修饰符类型：
  • ±属性名：使用角色属性值
  • ±经历名：使用具名经历（消耗1点希望）
  • ±经历[N]/±[N]经历：匿名经历（默认+2，消耗1点希望）
  • ±[N]优势/±[N]adv：优势骰（投N个d6取最高）
  • ±[N]劣势/±[N]dis：劣势骰（投N个d6取最低，取负）
  • ±[N]dM：额外骰子
  • ±N：常量修饰符
  • @玩家名：玩家帮助增加优势骰（消耗帮助者1点希望，最多5人）
  • #[N] 或 [N]：设定难度

检定结果：
- 希望骰 = 恐惧骰：大成功（希望+1，压力-1）
- 希望骰 > 恐惧骰：希望结果（希望+1）
- 希望骰 < 恐惧骰：恐惧结果（GM恐惧+1）
- 总点数 > 难度：成功
- 总点数 < 难度：失败

示例：
.dd +敏捷 推门
.dd 12/20 +力量+优势 #15
.dd +锻造-劣势 @Alice [12] 修理武器''',

    'ddr': '''【反应二元骰检定】
.ddr [n/m] [修饰符...] [原因]

说明：与.dd命令相同，但不增加/减少希望/恐惧点，大成功也不减少压力值。
主要用于反应性检定，只消耗希望但不获得希望。

参数格式和规则与.dd完全相同。''',

    'gm': '''【GM管理】
.gm          - 设置当前用户为本群GM
.gm del      - 卸任当前用户的本群GM职位
.gm clr/clear - 清除本群所有GM记录

说明：
- 设置为GM后会自动创建/切换至名为"gm_dh_用户名"的人物卡
- 人物卡自动套用"dhgm"模板
- 当玩家投出恐惧结果时，GM恐惧点自动+1
- GM恐惧点存储在GM人物卡的技能中''',

    'cook': '''【烹饪游戏】
支持新版本Core时，Markdown回复中的骰点结果会按代码保护。
.cook [ndm]+[ndm]+...  - 开始新游戏
.cook rm [骰面]         - 移除骰子

游戏规则：
1. 投掷所有骰子
2. 相同点数的骰子可以两两配对得分
3. 配对成功得分 = 骰子点数
4. 未配对的骰子可以移除一个，剩余骰子重新投掷
5. 剩余 ≤2 个骰子时游戏结束

得分评价：
- < 4分：低分评价
- 4-10分：中等评价
- > 10分：高分评价

示例：
.cook 3d6+6d2
.cook rm 6
.cook rm 2''',

    'dhst':'''【匕首之心跑团数据录入帮助文档】
1、将骰子拉入群聊后，请先使用[.set temp dh]，让本群套用模板（只需输入一次，其他人无需再输入）
2、让GM和玩家均输入[.sn auto on]，让双方名片数据能够自动变化。
3、GM请使用命令[.gm]添加自身为本群GM，一个群内可以有多个GM
4、玩家在填写完角色卡并审核通过后，输入这样的命令：[.st 人物名-技能名1技能值1技能名2技能值2技能名3技能值3……]录入数据。
5、玩家输入[.sn]或者[.sn template]，改变名片格式。''',

    'dh': '&匕首之心',
    'Daggerheart': '&匕首之心',
    '匕心': '&匕首之心',
}
