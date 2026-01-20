#+#+#+#+----------------------------------------------
# -*- encoding: utf-8 -*-
'''
TexasHoldem 插件自定义回复与帮助文档。
'''

import OlivOS
import OlivaDiceCore
import TexasHoldem

dictStrCustomDict = {}

dictStrCustom = {
    # 发送模式（防风控）：1=纯文本；0/其它=转图片发送
    'strTHSendMode': '0',
    # 图片样式（颜色使用十六进制 #RRGGBB 或 #RRGGBBAA）
    'strTHImgBgStart': '#F7DBFF',
    'strTHImgBgEnd': '#FFFFFF',
    'strTHImgTextDark': '#111827',
    'strTHImgTextLight': '#F9FAFB',
    'strTHImgFontSize': '18',
    'strTHImgMaxWidth': '860',
    'strTHImgPadding': '26',
    'strTHImgLineSpacing': '10',
    # 文字描边宽度（像素）。建议 1-3；0 表示不描边
    'strTHImgStrokeWidth': '2',
    'strTHImgCacheLimit': '60',

    # 通用/错误
    'strTHErrNotInGroup': '该指令仅支持在群聊中使用。',
    'strTHErrRoomNotFound': '本群未建局，请先使用：.dz 创建 [基础筹码]（默认1000）。',
    'strTHErrAlreadyPlaying': '游戏已开始，无法进行该操作。',
    'strTHErrNotPlaying': '当前未在进行德州扑克对局。',
    'strTHErrNoPermission': '权限不足，无法执行该操作。',
    'strTHErrInvalidNumber': '参数错误：请输入合法数字。',
    'strTHErrInvalidSeat': '座位号无效（仅支持 1-10 且必须存在该座位）。',
    'strTHErrNotYourTurn': '现在不是你的回合。',
    'strTHErrSeatNotFoundForUser': '你当前没有可操作的座位。',
    'strTHErrActionNotAllowed': '当前阶段不允许使用该指令。',
    'strTHErrRaiseTooSmall': '加注金额不足，最小加注为[{tMinRaise}]。',
    'strTHErrBetTooSmall': '下注金额不足，最小下注为[{tBB}]。',

    # 建局/入场
    'strTHCreateSuccess': '已创建德州扑克房间，基础筹码[{tBaseStake}]，小盲注[{tSB}]，大盲注[{tBB}]。\n使用 .dz 加入 [人物名] [筹码] 加入游戏。',
    'strTHCreateFailStake': '创建失败：基础筹码必须是[1000]的倍数，且 >= 1000。',
    'strTHCreateFailRoomExists': '创建失败：本群已有房间，请先解散或等待游戏结束。',
    'strTHJoinSuccess': '玩家[{tName}]加入游戏：<座位{tSeatId}>，携带筹码 {tChips}。',
    'strTHJoinFailChips': '加入失败：入场筹码必须 > 大盲注[{tBB}]。',
    'strTHJoinFailFull': '加入失败：座位已满（最多10人）。',
    'strTHQuitSuccess': '玩家[{tName}]已退出：<座位{tSeatId}>。',
    'strTHQuitFailNoSeat': '玩家[{tName}]退出失败：你没有可退出的座位。',
    'strTHDismissSuccess': '房间已解散。',
    'strTHStartFailNeedPlayers': '开始失败：至少需要2名玩家。',
    'strTHStartSuccess': '游戏开始！已发牌并扣除盲注。\n请使用[.dz 看牌]查看手牌（将通过私聊发送）\n{tAtAll}',

    # 私聊看牌
    'strTHPrivateCardsHeader': '来自群: [{tGroupId}]',
    'strTHPrivateCardsSeatLine': '座位: {tSeatId}号 - {tSeatName}（{tRoleText}）',
    'strTHPrivateCardsCardsLine': '底牌: {tHandCards}',
    'strTHPrivateCardsFooter': '请在群内进行操作。',
    'strTHCardsFailNotDealt': '看牌失败：当前未发牌或本局未开始。',
    'strTHErrNeedFriendForPrivate': '无法私聊发牌：QQ 平台需要先加 bot 好友。',

    # 操作/离场/踢人/强制结束/结束开关
    'strTHLeaveSuccess': '已离场：座位{tSeatId}: {tSeatName}（{tSeatRoleText}）{tSeatTurnMark}，筹码[{tForfeit}]充公进入底池。',
    'strTHKickSuccess': '已踢出：座位{tSeatId}: {tSeatName}（{tSeatRoleText}）{tSeatTurnMark}，筹码[{tForfeit}]充公进入底池。',
    'strTHStopSuccess': '已强制结束并销毁本群德州扑克数据（不结算）。',
    'strTHEndFlagSet': '已开启结束开关：本手在“最后仅剩一人（其余弃牌）”或“摊牌比牌”结算后，将进行最终结算并结束游戏（不会自动开始下一手）。',
    'strTHEndFlagUnset': '已关闭结束开关：游戏将继续进行，本手结束后会自动开始下一手。',
    # 局势面板
    'strTHStatusHeader': '底池:{tPot} ‖ 最小加注:{tMinRaise} ‖ 最小下注/跟注:{tMinCall}',
    'strTHStatusCommunity': '公共牌: {tCommunityCards} {tStreetText}',
    'strTHStatusSeparator': '------------------------------',
    'strTHStatusSeatLine1': '座位{tSeatId}: {tSeatName}（{tSeatRoleText}）{tSeatTurnMark}',
    'strTHStatusSeatLine2': '筹码:{tSeatChips} ‖ {tSeatActionText}',
    'strTHStatusTurnLine': '轮到[<座位{tTurnSeatId}>{tTurnName}]（{tTurnRoleText}）{tTurnAt}行动',
    'strTHStatusCmdHint': '指令: {tCmdHint}',
    'strTHStatusBoard': '{tHeader}\n{tCommunity}\n{tSep}\n{tSeatLines}\n{tSep}\n{tTurnLine}\n{tSep}\n{tCmdLine}',

    # 街名
    'strTHStreetPreflop': '（翻牌前/Pre-Flop）',
    'strTHStreetFlop': '（翻牌圈/Flop）',
    'strTHStreetTurn': '（转牌圈/Turn）',
    'strTHStreetRiver': '（河牌圈/River）',
    'strTHStreetShowdown': '（摊牌/Showdown）',
    # 位置/角色
    'strTHRoleDealer': '庄家/BTN/D',
    'strTHRoleDealerSB': '庄家/BTN/D（小盲位/SB）',
    'strTHRoleSB': '小盲位/SB',
    'strTHRoleBB': '大盲位/BB',
    'strTHRoleUTG': '枪口位/UTG',
    'strTHRoleUTG1': '枪口+1/UTG+1',
    'strTHRoleUTG2': '枪口+2/UTG+2',
    'strTHRoleMP': '中间位/MP',
    'strTHRoleMP1': '中间位1/MP1',
    'strTHRoleMP2': '中间位2/MP2',
    'strTHRoleHJ': '劫持位/HJ',
    'strTHRoleCO': '关煞位/CO',

    # 座位动作显示
    'strTHSeatActionPending': '⚪ 待行动（{tOptCheck} / {tOptBet} / {tOptCall}）',
    'strTHSeatActionPendingBlind': '⚪ 待行动（暂未行动；已投{tBlindText}；{tOptCheck} / {tOptBet} / {tOptCall}）',
    'strTHSeatActionNone': '⚪ 行动: 暂未行动',
    'strTHSeatActionNoneBlind': '⚪ 行动: 暂未行动（已投{tBlindText}）',
    'strTHSeatActionFolded': '🔴 已弃牌',
    'strTHSeatActionAllin': '🔴 全压（All-in）',
    'strTHSeatActionText': '🔴 行动: {tActionText}',

    # 待行动选项
    'strTHPendingOptCheckOK': '过牌',
    'strTHPendingOptCheckNO': '过牌（不可用）',
    'strTHPendingOptBetOK': '下注',
    'strTHPendingOptBetNO': '下注（不可用）',
    'strTHPendingOptCall': '跟注 {tNeedCall}',

    # 显示细节
    'strTHTurnMark': ' -> 当前回合',
    'strTHWinnersSep': ' ‖ ',
    'strTHWinnerSeatName': '[<座位{tSeatId}>{tSeatName}]（{tSeatRoleText}）赢得{tWinAmount}',

    # 动作文本
    'strTHActionBlindSB': '小盲 {tAmount}',
    'strTHActionBlindBB': '大盲 {tAmount}',
    'strTHActionCheck': '过牌',
    'strTHActionCall': '跟注 {tAmount}',
    'strTHActionBet': '下注 {tAmount}',
    'strTHActionRaise': '加注 {tAmount}',
    'strTHActionAllinAmount': '全压 {tAmount}',
    'strTHActionFold': '弃牌',

    # 回合结果/结算
    'strTHHandEndSingle': '本局结束：[<座位{tWinSeatId}>{tWinName}]获胜，赢得底池{tWinAmount}。',
    'strTHHandEndShowdownHeader': '本局结束：进入摊牌结算。',
    'strTHShowdownRevealHeader': '摊牌明细：',
    'strTHShowdownRevealLine': '[<座位{tSeatId}>{tSeatName}]（{tSeatRoleText}）底牌:{tHandCards} ‖ 牌型:{tHandType} ‖ 最佳5张:{tBest5}',
    'strTHShowdownRevealFoldedLine': '[<座位{tSeatId}>{tSeatName}]（{tSeatRoleText}）弃牌|底牌:{tHandCards}',
    'strTHShowdownBoardLine': '公共牌: {tBoardCards}',
    'strTHShowdownSeatHoleLine': '[<座位{tSeatId}>{tSeatName}]（{tSeatRoleText}）{tFoldMark} 底牌:{tHandCards}',
    'strTHShowdownSeatMadeLine': '凑牌:{tBest5}',
    'strTHShowdownSeatTypeLine': '牌型:{tHandType}',
    'strTHHandEndPotLine': '奖池{tPotIndex}（{tPotLabel}）: {tPotAmount} -> 赢家: {tWinnersText}',
    'strTHRefundLine': '未被跟注：退还 [<座位{tSeatId}>{tSeatName}]（{tSeatRoleText}）{tRefundAmount}',
    'strTHFoldReveal': '[<座位{tSeatId}>{tSeatName}]（{tSeatRoleText}）弃牌，亮出底牌：{tHandCards}',
    'strTHBrokeOut': '[<座位{tSeatId}>{tSeatName}]（{tSeatRoleText}）破产出局。',
    'strTHGameOnlyOneLeft': '剩余唯一玩家：[<座位{tWinSeatId}>{tWinName}]，游戏结束。',
    'strTHFinalRankingHeader': '游戏结束，筹码排行：',
    'strTHFinalRankingLine': '{tRankNo}. [<座位{tSeatId}>{tSeatName}]:{tSeatChips}',

    # 指令提示
    'strTHCmdHintPreflop': '.dz 跟 / .dz 加 [数值] / .dz 弃 / .dz 全压',
    'strTHCmdHintPreflopCheck': '.dz 过 / .dz 跟 / .dz 加 [数值] / .dz 弃 / .dz 全压',
    'strTHCmdHintPostflop': '.dz 下 [数值] / .dz 跟 / .dz 加 [数值] / .dz 弃 / .dz 全压',
    'strTHCmdHintPostflopCheck': '.dz 过 / .dz 下 [数值] / .dz 跟 / .dz 加 [数值] / .dz 弃 / .dz 全压',
    'strTHCmdHintPostflopCheckBet': '.dz 过 / .dz 下 [数值] / .dz 跟 / .dz 加 [数值] / .dz 弃 / .dz 全压',
    'strTHCmdHintPostflopBet': '.dz 下 [数值] / .dz 跟 / .dz 加 [数值] / .dz 弃 / .dz 全压',
}


dictStrConst = {}

dictGValue = {}


dictTValue = {
    'tBaseStake': '1000',
    'tBB': '10',
    'tSB': '5',
    'tSeatId': '1',
    'tChips': '1000',

    'tGroupId': '0',
    'tRoleText': '庄家/BTN/D',
    'tHandCards': '[♥️红桃A] [♠️黑桃K]',
    'tHandType': '同花顺（Straight Flush）',
    'tBest5': '[♣️梅花A] [♥️红桃K] [♦️方片Q] [♠️黑桃J] [♠️黑桃10]',
    'tBoardCards': '[♣️梅花A] [♥️红桃K] [♦️方片Q] [♠️黑桃J] [♠️黑桃10]',
    'tFoldMark': '（已弃牌）',

    'tPot': '0',
    'tMinRaise': '0',
    'tMinCall': '0',
    'tCommunityCards': '[]',
    'tStreetText': '(翻牌前/Pre-Flop)',
    'tHeader': '',
    'tCommunity': '',
    'tSep': '------------------------------',
    'tSeatLines': '',
    'tTurnLine': '',
    'tCmdLine': '',

    'tSeatName': '玩家',
    'tSeatRoleText': '庄家/BTN/D',
    'tSeatTurnMark': '',
    'tSeatChips': '0',
    'tSeatActionText': '⚪ 行动: 暂未行动',
    'tNeedCall': '0',
    'tActionText': '下注 0',
    'tAmount': '0',

    'tOptCheck': '过牌',
    'tOptBet': '下注',
    'tOptCall': '跟注 0',

    'tBlindText': '小盲 5',

    'tTurnSeatId': '1',
    'tTurnName': '玩家',
    'tTurnRoleText': '庄家/BTN/D',
    'tTurnAt': '',
    'tAtAll': '',
    'tCmdHint': '',

    'tWinSeatId': '1',
    'tWinName': '玩家',
    'tWinAmount': '0',

    'tRefundAmount': '0',

    'tPotIndex': '1',
    'tPotLabel': '主池',
    'tPotAmount': '0',
    'tWinnersText': '座位1 玩家',

    'tRankNo': '1',
    'tSeatIdRank': '1',
    'tSeatNameRank': '玩家',
    'tSeatChipsRank': '0',
    'tForfeit': '0',
}


dictStrCustomNote = {
    'strTHSendMode': '【德州扑克】发送模式\n1=发送纯文本；0/其他=把文本渲染成图片并用CQ码发送（用于规避群风控）',
    'strTHImgBgStart': '【德州扑克】图片\n渐变背景起始色（#RRGGBB 或 #RRGGBBAA）',
    'strTHImgBgEnd': '【德州扑克】图片\n渐变背景结束色（#RRGGBB 或 #RRGGBBAA）',
    'strTHImgTextDark': '【德州扑克】图片\n浅色背景下的文字颜色',
    'strTHImgTextLight': '【德州扑克】图片\n深色背景下的文字颜色',
    'strTHImgFontSize': '【德州扑克】图片\n默认字体字号',
    'strTHImgMaxWidth': '【德州扑克】图片\n图片最大宽度（像素）',
    'strTHImgPadding': '【德州扑克】图片\n内边距（像素）',
    'strTHImgLineSpacing': '【德州扑克】图片\n行间距（像素）',
    'strTHImgStrokeWidth': '【德州扑克】图片\n文字描边宽度（像素；0=不描边；建议 1-3）',
    'strTHImgCacheLimit': '【德州扑克】图片\n缓存文件保留数量（超过会自动清理旧图）',

    # 通用/错误
    'strTHErrNotInGroup': '【德州扑克】错误提示\n该指令仅支持在群聊中使用',
    'strTHErrRoomNotFound': '【德州扑克】错误提示\n本群未建局/未找到房间',
    'strTHErrAlreadyPlaying': '【德州扑克】错误提示\n游戏已开始，无法执行该操作',
    'strTHErrNotPlaying': '【德州扑克】错误提示\n当前未在进行德州扑克对局',
    'strTHErrNoPermission': '【德州扑克】错误提示\n权限不足',
    'strTHErrInvalidNumber': '【德州扑克】错误提示\n参数数字非法',
    'strTHErrInvalidSeat': '【德州扑克】错误提示\n座位号无效',
    'strTHErrNotYourTurn': '【德州扑克】错误提示\n不是你的回合',
    'strTHErrSeatNotFoundForUser': '【德州扑克】错误提示\n你没有可操作的座位',
    'strTHErrActionNotAllowed': '【德州扑克】错误提示\n当前阶段不允许该操作',
    'strTHErrRaiseTooSmall': '【德州扑克】错误提示\n加注不足（小于最小加注）',
    'strTHErrBetTooSmall': '【德州扑克】错误提示\n下注不足（小于大盲/最小下注）',

    # 建局/入场
    'strTHCreateSuccess': '【德州扑克】建局\n创建房间成功提示',
    'strTHCreateFailStake': '【德州扑克】建局\n创建房间失败（基础筹码不合法）',
    'strTHCreateFailRoomExists': '【德州扑克】建局\n创建房间失败（房间已存在）',
    'strTHJoinSuccess': '【德州扑克】入场\n加入游戏成功提示',
    'strTHJoinFailChips': '【德州扑克】入场\n加入失败（入场筹码不合法）',
    'strTHJoinFailFull': '【德州扑克】入场\n加入失败（座位已满）',
    'strTHQuitSuccess': '【德州扑克】入场\n退出座位成功提示（仅开局前）',
    'strTHQuitFailNoSeat': '【德州扑克】入场\n退出失败（无可退出座位）',
    'strTHDismissSuccess': '【德州扑克】建局\n解散房间成功提示（仅开局前）',
    'strTHStartFailNeedPlayers': '【德州扑克】开局\n开始失败（人数不足）',
    'strTHStartSuccess': '【德州扑克】开局\n游戏开始提示（已发牌/扣盲注）',

    # 私聊看牌
    'strTHPrivateCardsHeader': '【德州扑克】看牌私聊\n私聊消息头（显示来自哪个群）',
    'strTHPrivateCardsSeatLine': '【德州扑克】看牌私聊\n座位信息行',
    'strTHPrivateCardsCardsLine': '【德州扑克】看牌私聊\n底牌展示行',
    'strTHPrivateCardsFooter': '【德州扑克】看牌私聊\n私聊消息尾',
    'strTHCardsFailNotDealt': '【德州扑克】看牌\n看牌失败（未发牌/未开始）',
    'strTHErrNeedFriendForPrivate': '【德州扑克】私聊\nQQ 平台需加好友才能私聊发牌',

    # 操作/离场/踢人/强制结束/结束开关
    'strTHLeaveSuccess': '【德州扑克】操作\n离场成功提示（含座位详情/罚没筹码）',
    'strTHKickSuccess': '【德州扑克】管理\n踢人成功提示（含座位详情/罚没筹码）',
    'strTHStopSuccess': '【德州扑克】管理\n强制结束成功提示（不结算）',
    'strTHEndFlagSet': '【德州扑克】全局\n开启结束开关提示',
    'strTHEndFlagUnset': '【德州扑克】全局\n关闭结束开关提示',

    # 局势面板（使用标记语法的文本）
    'strTHStatusHeader': '【德州扑克】局势面板\n顶部信息（底池/最小加注/最小下注或跟注）',
    'strTHStatusCommunity': '【德州扑克】局势面板\n公共牌与街名行',
    'strTHStatusSeparator': '【德州扑克】局势面板\n分隔线',
    'strTHStatusSeatLine1': '【德州扑克】局势面板\n座位信息第一行（座位/昵称/位置/回合标记）',
    'strTHStatusSeatLine2': '【德州扑克】局势面板\n座位信息第二行（筹码/动作）',
    'strTHStatusTurnLine': '【德州扑克】局势面板\n轮到谁行动提示行',
    'strTHStatusCmdHint': '【德州扑克】局势面板\n底部指令提示行',
    'strTHStatusBoard': '【德州扑克】局势面板\n整体模板（拼装用）',

    # 街名
    'strTHStreetPreflop': '【德州扑克】术语\n街名：翻牌前',
    'strTHStreetFlop': '【德州扑克】术语\n街名：翻牌圈',
    'strTHStreetTurn': '【德州扑克】术语\n街名：转牌圈',
    'strTHStreetRiver': '【德州扑克】术语\n街名：河牌圈',
    'strTHStreetShowdown': '【德州扑克】术语\n街名：摊牌',

    # 位置/角色
    'strTHRoleDealer': '【德州扑克】术语\n位置：庄家（BTN）',
    'strTHRoleDealerSB': '【德州扑克】术语\n位置：两人局庄家兼小盲位（BTN+SB）',
    'strTHRoleSB': '【德州扑克】术语\n位置：小盲位（SB）',
    'strTHRoleBB': '【德州扑克】术语\n位置：大盲位（BB）',
    'strTHRoleUTG': '【德州扑克】术语\n位置：枪口位（UTG）',
    'strTHRoleUTG1': '【德州扑克】术语\n位置：枪口+1（UTG+1）',
    'strTHRoleUTG2': '【德州扑克】术语\n位置：枪口+2（UTG+2）',
    'strTHRoleMP': '【德州扑克】术语\n位置：中间位（MP）',
    'strTHRoleMP1': '【德州扑克】术语\n位置：中间位1（MP1）',
    'strTHRoleMP2': '【德州扑克】术语\n位置：中间位2（MP2）',
    'strTHRoleHJ': '【德州扑克】术语\n位置：劫持位（HJ）',
    'strTHRoleCO': '【德州扑克】术语\n位置：关煞位（CO）',

    # 座位动作显示
    'strTHSeatActionPending': '【德州扑克】动作显示\n当前行动位“待行动”文本',
    'strTHSeatActionPendingBlind': '【德州扑克】动作显示\n当前行动位“待行动（已投盲注）”文本',
    'strTHSeatActionNone': '【德州扑克】动作显示\n本轮暂未行动',
    'strTHSeatActionNoneBlind': '【德州扑克】动作显示\n仅投盲注但尚未行动（例如小盲/大盲刚扣盲注）',
    'strTHSeatActionFolded': '【德州扑克】动作显示\n已弃牌',
    'strTHSeatActionAllin': '【德州扑克】动作显示\n全压',
    'strTHSeatActionText': '【德州扑克】动作显示\n动作模板',

    # 待行动选项
    'strTHPendingOptCheckOK': '【德州扑克】待行动选项\n过牌（可用）',
    'strTHPendingOptCheckNO': '【德州扑克】待行动选项\n过牌（不可用）',
    'strTHPendingOptBetOK': '【德州扑克】待行动选项\n下注（可用）',
    'strTHPendingOptBetNO': '【德州扑克】待行动选项\n下注（不可用）',
    'strTHPendingOptCall': '【德州扑克】待行动选项\n跟注选项（含需跟注金额）',

    # 显示细节
    'strTHTurnMark': '【德州扑克】显示细节\n当前回合标记',
    'strTHWinnersSep': '【德州扑克】显示细节\n多赢家拼接分隔符',
    'strTHWinnerSeatName': '【德州扑克】显示细节\n赢家座位名显示模板',

    # 动作文本
    'strTHActionBlindSB': '【德州扑克】动作文本\n小盲下注显示',
    'strTHActionBlindBB': '【德州扑克】动作文本\n大盲下注显示',
    'strTHActionCheck': '【德州扑克】动作文本\n过牌显示',
    'strTHActionCall': '【德州扑克】动作文本\n跟注显示',
    'strTHActionBet': '【德州扑克】动作文本\n下注显示',
    'strTHActionRaise': '【德州扑克】动作文本\n加注显示',
    'strTHActionAllinAmount': '【德州扑克】动作文本\n全压显示（带金额）',
    'strTHActionFold': '【德州扑克】动作文本\n弃牌显示',

    # 回合结果/结算
    'strTHHandEndSingle': '【德州扑克】结算\n剩一人直接获胜结算提示',
    'strTHHandEndShowdownHeader': '【德州扑克】结算\n进入摊牌结算提示',
    'strTHShowdownRevealHeader': '【德州扑克】结算\n摊牌明细标题（展示每人牌型）',
    'strTHShowdownRevealLine': '【德州扑克】结算\n摊牌明细行（展示每人底牌/牌型/最佳5张）',
    'strTHShowdownRevealFoldedLine': '【德州扑克】结算\n摊牌明细行（未进入摊牌的玩家，例如已弃牌，也展示底牌）',
    'strTHShowdownBoardLine': '【德州扑克】结算\n摊牌明细-公共牌显示行',
    'strTHShowdownSeatHoleLine': '【德州扑克】结算\n摊牌明细-座位底牌行',
    'strTHShowdownSeatMadeLine': '【德州扑克】结算\n摊牌明细-座位凑牌/牌型行',
    'strTHShowdownSeatTypeLine': '【德州扑克】结算\n摊牌明细-座位牌型行',
    'tFoldMark': '【德州扑克】占位符\n摊牌明细中弃牌标记（默认：已弃牌则为“（已弃牌）”，否则为空）',
    'strTHHandEndPotLine': '【德州扑克】结算\n奖池分配明细行',
    'strTHRefundLine': '【德州扑克】结算\n未被跟注金额退款展示行',
    'tPotLabel': '【德州扑克】占位符\n奖池标签（无边池时为“底池”；有边池时为“主池/边池1/边池2…”）',
    'strTHFoldReveal': '【德州扑克】对局公开信息\n玩家弃牌后公开其底牌',
    'strTHBrokeOut': '【德州扑克】结算\n破产出局提示',
    'strTHGameOnlyOneLeft': '【德州扑克】结算\n最终只剩一人时游戏结束提示',
    'strTHFinalRankingHeader': '【德州扑克】结算\n最终排行标题',
    'strTHFinalRankingLine': '【德州扑克】结算\n最终排行明细行',

    # 指令提示
    'strTHCmdHintPreflop': '【德州扑克】局势面板\n翻牌前可用指令提示',
    'strTHCmdHintPreflopCheck': '【德州扑克】局势面板\n翻牌前可用指令提示（可过牌）',
    'strTHCmdHintPostflop': '【德州扑克】局势面板\n翻牌后可用指令提示',
    'strTHCmdHintPostflopCheck': '【德州扑克】局势面板\n翻牌后可用指令提示（可过牌）',
    'strTHCmdHintPostflopCheckBet': '【德州扑克】局势面板\n翻牌后可用指令提示（可过牌 + 可下注）',
    'strTHCmdHintPostflopBet': '【德州扑克】局势面板\n翻牌后可用指令提示（可下注）',
}


dictHelpDocTemp = {
    'texas': '''【德州扑克】
前缀：.dz 或 .th
【建局/入场】
.dz 创建 [基础筹码]（默认1000，必须为1000倍数）
.dz 加入 [人物名] [携带筹码]（默认=基础筹码，必须>大盲注；允许同一QQ多次加入占不同座位）（若没有人物名为空，则优先使用人物卡名称，再使用QQ昵称）
.dz 退出（仅开局前；若同一QQ多个座位，按后加入先退出）
.dz 开始（至少2人；发牌并扣盲注，进入游戏）
.dz 解散（仅开局前；权限：座位1玩家/管理员/群主/骰主）

【回合操作】
.dz 看牌（群聊触发，Bot 私聊返回手牌）
.dz 跟
.dz 过
.dz 下 [数值]（翻牌后且无人下注时）
.dz 加 [数值]（可不带数字，默认=最小加注）
.dz 全压
.dz 弃
.dz 离场（强行弃牌+净身出户，筹码充公入池并移除座位）

【全局】
.dz list（查看当前玩家/座位）
.dz 局势（查看当前局面）
.dz 结束（开启结束开关，本手结束后结算并结束）
.dz 踢 [座位号]（权限：管理员/群主/骰主；逻辑同离场）
.dz stop（权限：管理员/群主/骰主；立即停止，不结算）

规则：使用 .help texas_rule 查看。
牌型比较：使用 .help texas_rank 查看。''',

    'texas_rule': '''【德州扑克 规则】
【一手牌的流程】
- 每手开始会收取小盲/大盲，然后每名在局玩家获得 2 张底牌（底牌仅自己可见，会私聊发送）。
- 从翻牌前开始行动：依次进行翻牌前（Pre-Flop）/ 翻牌（Flop）/ 转牌（Turn）/ 河牌（River）四轮下注。
- 每轮下注中，轮到你时可执行：过牌/下注/跟注/加注/弃牌/全压；可用指令会在 .dz 局势 中提示。

【公共牌与摊牌】
- Flop 翻出 3 张公共牌；Turn 再翻 1 张；River 再翻 1 张。
- 若在任意阶段其余玩家都弃牌：最后未弃牌玩家直接赢得底池。
- 若多人进入摊牌：用“2 张底牌 + 5 张公共牌”组合成最大 5 张牌型，比大小分配底池（含边池）。

【筹码与结算】
- 下注进入底池；全压可能产生边池，摊牌时分别结算。

指令入口：使用 .help texas 查看。
牌型比较：使用 .help texas_rank 查看。''',

    'texas_rank': '''【德州扑克 牌型比较】
说明：摊牌时用“2 张底牌 + 5 张公共牌”可组成的最大 5 张牌型来比较大小；花色不参与大小比较。

【牌型从大到小】
1. 同花顺（Straight Flush）：同一花色的顺子
2. 四条（Four of a Kind）：四张同点数
3. 葫芦（Full House）：三条 + 一对
4. 同花（Flush）：五张同花色（不要求连续）
5. 顺子（Straight）：五张连续点数（不要求同花）
6. 三条（Three of a Kind）：三张同点数
7. 两对（Two Pair）：两个对子
8. 一对（One Pair）：一个对子
9. 高牌（High Card）：以上都不是

【比较规则（同牌型时）】
- 先比该牌型的“核心点数”，大者胜。
- 若核心点数相同，再依次比踢脚牌（kicker）从大到小。
- 顺子按最高张比大小；A2345 视为最小顺子（A 当作 1）。
- 同花按五张牌从大到小逐张比较。

指令入口：使用 .help texas 查看。
规则：使用 .help texas_rule 查看。''',

    '德州扑克': '&texas',
    '德州': '&texas',
    '德州扑克规则': '&texas_rule',
    '德州规则': '&texas_rule',
    'dz规则': '&texas_rule',
    'th规则': '&texas_rule',
    '德州扑克牌型': '&texas_rank',
    '德州牌型': '&texas_rank',
    '德州牌型比较': '&texas_rank',
    'dz牌型': '&texas_rank',
    'th牌型': '&texas_rank',
    'dz': '&texas',
    'th': '&texas',
}
