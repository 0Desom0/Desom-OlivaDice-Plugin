# -*- encoding: utf-8 -*-
'''
Blackjack 消息模板，依据 21点 开发文档定义初始文本
'''

import OlivOS
import OlivaDiceCore
import Blackjack

dictStrCustomDict = {}

dictStrCustom = {
    'strBJErrNotInGroup': '该指令仅支持在群聊中使用。',
    'strBJErrRoomNotFound': '本群未建局，请先使用：.bj 创建 [底注]（默认100）。',
    'strBJErrAlreadyPlaying': '游戏已开始，无法进行该操作。',
    'strBJErrNotPlaying': '当前未在进行21点游戏。',
    'strBJErrNoPermission': '权限不足，无法执行该操作。',
    'strBJErrInvalidNumber': '参数错误：请输入合法数字。',
    'strBJErrInvalidSeat': '座位号无效。',
    'strBJErrNotYourTurn': '现在不是你的回合。',
    'strBJErrNotEnoughChips': '筹码不足。',
    'strBJErrBetTooSmall': '下注金额过小，最小下注为[{tMinStake}]。',
    'strBJErrBetTooLarge': '下注金额过大，最大下注为[{tMaxStake}]。',
    'strBJErrActionNotAllowed': '当前无法执行该操作。',
    'strBJErrCannotDouble': '无法双倍下注（仅第一次要牌后可用）。',
    'strBJErrCannotSplit': '无法分牌（手牌必须为两张且点数相同）。',
    'strBJErrCannotSurrender': '无法投降（仅第一次行动可用）。',
    'strBJErrCannotInsurance': '无法购买保险（仅庄家明牌为A时可用）。',
    'strBJErrInsuranceTooLarge': '保险金额不能超过主注的一半。',
    'strBJErrInvalid21_3Type': '21+3类型无效，请选择：顺/同花/三条/同花顺/同花三条。',
    'strBJErrSetChipsInvalid': '设置的筹码金额无效，必须>=10。',

    'strBJCreateSuccess': '已创建21点房间，基础下注[{tBaseStake}]，最小下注[{tMinStake}]，最大下注[{tMaxStake}]，模式：{tGameMode}。\n使用 .bj 加入 [人物名] [筹码] 加入游戏（第一个加入的玩家为庄家）。',
    'strBJJoinSuccess': '玩家[{tName}]加入游戏：<座位{tSeatId}>，携带筹码 {tChips}{tIsDealer}。',
    'strBJJoinAsDealer': '（庄家）',
    'strBJQuitSuccess': '玩家[{tName}]已退出：<座位{tSeatId}>。',
    'strBJDismissSuccess': '房间已解散。',
    'strBJStartSuccess': '游戏开始！已发牌。\n请使用[.bj 下注]进行下注（可同时下21+3注），然后使用[.bj 看牌]查看手牌（将通过私聊发送）\n{tAtAll}',

    'strBJStatusHeader': '底注: {tBaseStake} ‖ 最小下注: {tMinStake} ‖ 最大下注: {tMaxStake} ‖ 模式: {tGameMode}',
    'strBJStatusDealer': '庄家[{tDealerName}]手牌: {tDealerCards}（点数: {tDealerValue}）',
    'strBJStatusSeparator': '------------------------------',
    'strBJStatusSeatLine1': '座位{tSeatId}: {tSeatName}',
    'strBJStatusSeatLine2': '筹码: {tSeatChips} ‖ 主注: {tSeatBet} ‖ 保险: {tInsuranceBet} ‖ 21+3: {t21_3Bet} ‖ {tSeatStatus}',
    'strBJStatusTurnLine': '轮到[<座位{tTurnSeatId}>{tTurnName}]{tTurnAt}行动',
    'strBJStatusCmdHint': '指令: {tCmdHint}',
    'strBJStatusBoard': '{tHeader}\n{tDealer}\n{tSep}\n{tSeatLines}\n{tSep}\n{tTurnLine}\n{tSep}\n{tCmdLine}',

    'strBJHitSuccess': '[<座位{tSeatId}>{tSeatName}]要牌：{tNewCard}，当前点数：{tHandValue}',
    'strBJStandSuccess': '[<座位{tSeatId}>{tSeatName}]停牌，最终点数：{tHandValue}',
    'strBJDoubleSuccess': '[<座位{tSeatId}>{tSeatName}]双倍下注：{tNewCard}，最终点数：{tHandValue}',
    'strBJSplitSuccess': '[<座位{tSeatId}>{tSeatName}]分牌：第一手{tHand1Cards}，第二手{tHand2Cards}',
    'strBJSurrenderSuccess': '[<座位{tSeatId}>{tSeatName}]投降，收回一半下注：{tRefund}',
    'strBJInsuranceSuccess': '[<座位{tSeatId}>{tSeatName}]购买保险：{tInsuranceAmount}',
    'strBJInsuranceWin': '[<座位{tSeatId}>{tSeatName}]保险赔付：{tPayout}（庄家21点）',
    'strBJInsuranceLose': '[<座位{tSeatId}>{tSeatName}]保险失效（庄家不是21点）',
    'strBJ21_3Win': '[<座位{tSeatId}>{tSeatName}]21+3中奖：{tType}（{tMultiplier}倍），获得{tPayout}',
    'strBJBust': '[<座位{tSeatId}>{tSeatName}]爆牌（点数：{tHandValue}）',
    'strBJBlackjack': '[<座位{tSeatId}>{tSeatName}]21点！',

    'strBJRoundEndHeader': '本局结束：',
    'strBJRoundDealerCards': '庄家手牌: {tDealerCards}，点数：{tDealerValue}',
    'strBJRoundResultLine': '[<座位{tSeatId}>{tSeatName}] 手牌:{tHandCards} 点数:{tHandValue} {tResultText} {tPayout}',
    'strBJRound21_3Result': '[<座位{tSeatId}>{tSeatName}] 21+3: {t21_3Result}',
    'strBJRoundInsuranceResult': '[<座位{tSeatId}>{tSeatName}] 保险: {tInsuranceResult}',
    'strBJResultWin': '获胜',
    'strBJResultLose': '失败',
    'strBJResultPush': '平局',
    'strBJResultBlackjack': '21点（1.5倍）',
    'strBJResultBust': '爆牌',

    'strBJPrivateCardsHeader': '来自群: [{tGroupId}]',
    'strBJPrivateCardsSeatLine': '座位: {tSeatId}号 - {tSeatName}',
    'strBJPrivateCardsCardsLine': '手牌: {tHandCards}',
    'strBJPrivateCardsValueLine': '点数: {tHandValue}',
    'strBJPrivateCardsFooter': '请在群内进行操作。',
    'strBJErrCannotPM': '无法私聊发送手牌，请先添加机器人为好友或允许私聊。',

    'strBJSetChipsSuccess': '已设置默认入局筹码为 {tChips}。下次加入游戏时将使用此筹码。',
    'strBJMyChipsInfo': '你的筹码信息：\n默认入局筹码：{tDefaultChips}',
    'strBJChipsReset': '你的筹码低于10，已重置为1000。',
}


dictStrConst = {}


dictGValue = {}


dictTValue = {'tTempleResult': ''}


dictStrCustomNote = {}


dictHelpDocTemp = {'Blackjack Help': '21点 插件帮助'}
