# -*- encoding: utf-8 -*-
'''
LiarBar 插件自定义回复与帮助文档。
所有用户可见文本尽量集中在此文件。
注意：避免在可见文本里使用竖线 | ，否则可能触发 OlivaDice 的随机分割回复机制。
'''

import OlivOS
import OlivaDiceCore
import LiarBar


dictStrCustomDict = {}


dictStrCustom = {
    # 通用/错误
    'strLBErrNotInGroup': '该指令仅支持在群聊中使用。',
    'strLBErrRoomNotFound': '本群未开局，请先使用：.lb join 加入，然后 .lb start 开始。',
    'strLBErrAlreadyStarted': '游戏已开始，无法执行该操作。',
    'strLBErrNotStarted': '当前未在进行[LiarBar]对局。',
    'strLBErrNoPermission': '权限不足，无法执行该操作。',
    'strLBErrNotYourTurn': '现在不是你的回合。',
    'strLBErrNotInGame': '你没有参与本群的本局游戏。',
    'strLBErrRoomFull': '加入失败：人数已满（最多[{tMaxPlayers}]人）。',
    'strLBErrNeedMorePlayers': '开始失败：至少需要[{tMinPlayers}]人。',
    'strLBErrNeedFriendForPrivate': '无法私聊发牌：QQ 平台需要先加 bot 好友。',
    'strLBErrPlayInPrivate': '出牌请私聊 bot 发送：.lb play [牌]（每次最多 3 张；恶魔牌仅能单张）。',
    'strLBErrBadCards': '出牌失败：请输入合法牌（A/Q/K/恶魔）。',
    'strLBErrTooManyCards': '出牌失败：单次最多出[3]张牌。',
    'strLBErrDemonMustSingle': '出牌失败：恶魔牌仅能单张打出。',
    'strLBErrNoLastPlay': '没有上家出牌，因此你现在无法质疑。',
    'strLBErrCannotPlayOnlyDoubt': '其余玩家都已出完牌，你不能再出牌了，只能质疑上家。',

    # 房间/入场
    'strLBJoinSuccess': '玩家[{tName}]{tAt}加入游戏：<座位{tSeatId}>。',
    'strLBJoinFailAlreadyIn': '加入失败：玩家[{tName}]{tAt}已在本局中。',
    'strLBExitSuccess': '已退出：[<座位{tSeatId}>{tSeatName}]{tSeatAt}（{tSeatStatusText}）。',
    'strLBLeaveSuccess': '已离场：[<座位{tSeatId}>{tSeatName}]{tSeatAt}（{tSeatStatusText}）。',
    'strLBEndSuccess': '已强制结束本局游戏。',

    # 开始/发牌
    'strLBStartSuccess': '游戏开始！已洗牌并发牌。\n本轮真牌为：{tRealCardText}\n请[<座位{tTurnSeatId}>{tTurnName}]{tTurnAt}最先出牌。',
    'strLBDealNotice': '发牌已完成，手牌将通过私聊发送；未收到可用：[.lb list]\n{tAtAll}',

    # 私聊手牌
    'strLBPrivateCardsHeader': '来自群: [{tGroupId}]',
    'strLBPrivateCardsLine': '你的手牌: {tHandText}',
    'strLBPrivateCardsFooter': '请在群内进行操作。',

    # 局势面板
    'strLBStatusHeader': 'LiarBar 状态: {tStateText} / 本轮真牌: {tRealCardText}',
    'strLBStatusSeparator': '------------------------------',
    'strLBStatusSeatLine': '座位{tSeatId}: {tSeatName}{tSeatAt}（{tSeatStatusText}）{tSeatTurnMark} / 手牌数: {tHandCount} / 开枪次数: {tAttempts}',
    'strLBStatusTurnLine': '轮到[<座位{tTurnSeatId}>{tTurnName}]{tTurnAt}（{tTurnStatusText}）行动',
    'strLBStatusCmdHint': '指令: {tCmdHint}',
    'strLBStatusBoard': '{tHeader}\n{tSep}\n{tSeatLines}\n{tSep}\n{tTurnLine}\n{tSep}\n{tCmdLine}',

    # 回合提示
    'strLBTurnMark': ' -> 当前回合',
    'strLBStateIdle': '空闲',
    'strLBStateWaiting': '等待开局',
    'strLBStatePlaying': '游戏中',

    # 牌/状态文本
    'strLBCardA': 'A',
    'strLBCardQ': 'Q',
    'strLBCardK': 'K',
    'strLBCardDemon': '恶魔',

    'strLBSeatStatusActive': '在局',
    'strLBSeatStatusDead': '淘汰',
    'strLBSeatStatusLeft': '离场',
    'strLBSeatStatusExit': '退出',
    'strLBSeatStatusFinished': '已出完牌',

    # 出牌/质疑
    'strLBPlayBroadcast': '[<座位{tSeatId}>{tName}]{tAt}已完成出牌，共计{tCardCount}张。\n请[<座位{tNextSeatId}>{tNextName}]{tNextAt}选择出牌或质疑上家。\n群内输入：.lb doubt 质疑上家。',
    'strLBDoubtAnnounce': 'Liar!\n[<座位{tDoubterSeatId}>{tDoubterName}]{tDoubterAt}质疑了他的上家[<座位{tLastSeatId}>{tLastName}]{tLastAt}',
    'strLBDoubtReveal': '上家[<座位{tLastSeatId}>{tLastName}]{tLastAt}出的牌是{tLastCardsText}，真牌是{tRealCardText}',
    'strLBDoubtSuccess': '[<座位{tDoubterSeatId}>{tDoubterName}]{tDoubterAt}的质疑成功了！',
    'strLBDoubtFail': '[<座位{tDoubterSeatId}>{tDoubterName}]{tDoubterAt}的质疑失败了！',

    # 开枪结果
    'strLBShootBlank': '[<座位{tTargetSeatId}>{tTargetName}]{tTargetAt}开了一枪，是空弹。即将洗牌开启新的一轮。',
    'strLBShootReal': '[<座位{tTargetSeatId}>{tTargetName}]{tTargetAt}开了一枪，是实弹，[<座位{tTargetSeatId}>{tTargetName}]{tTargetAt}被淘汰了！即将洗牌开启新的一轮。',

    # 恶魔牌
    'strLBDemonPunishHeader': '[<座位{tDoubterSeatId}>{tDoubterName}]{tDoubterAt}质疑了恶魔牌！\n除上家[<座位{tLastSeatId}>{tLastName}]{tLastAt}外，其他所有玩家都要接受惩罚：自罚一枪。',
    'strLBDemonPunishEach': '[<座位{tTargetSeatId}>{tTargetName}]{tTargetAt}需要自罚一枪。',

    # 结局
    'strLBGameOverWinner': '本局结束：胜者[<座位{tWinSeatId}>{tWinName}]{tWinAt}！',
    'strLBGameOverNoWinner': '本局结束：无人获胜。',

    # 指令提示
    'strLBCmdHintWaiting': '.lb join / .lb exit / .lb start / .lb status',
    'strLBCmdHintPlaying': '.lb status / .lb hand / .lb doubt / （私聊）.lb play [牌] / .lb leave / .lb end',
}


dictStrConst = {}

dictGValue = {
    'gLBMinPlayers': 2,
    'gLBMaxPlayers': 6,
}


dictTValue = {
    'tAt': '',
    'tName': '玩家',
    'tSeatId': '1',
    'tSeatName': '玩家',
    'tSeatAt': '',
    'tSeatStatusText': '在局',
    'tSeatTurnMark': '',
    'tHandCount': '5',
    'tAttempts': '0',

    'tStateText': '等待开局',
    'tRealCardText': 'A',
    'tAtAll': '',

    'tGroupId': '0',
    'tHandText': 'A x 2 / Q x 1 / K x 2',

    'tTurnSeatId': '1',
    'tTurnName': '玩家',
    'tTurnStatusText': '在局',
    'tTurnAt': '',

    'tCmdHint': '',

    'tMinPlayers': '2',
    'tMaxPlayers': '6',

    'tCardCount': '2',
    'tNextSeatId': '2',
    'tNextName': '玩家',
    'tNextAt': '',

    'tDoubterAt': '',
    'tLastAt': '',
    'tDoubterSeatId': '1',
    'tDoubterName': '玩家',
    'tLastSeatId': '2',
    'tLastName': '玩家',
    'tLastCardsText': '[A, Q]',

    'tTargetAt': '',
    'tTargetSeatId': '1',
    'tTargetName': '玩家',

    'tWinSeatId': '1',
    'tWinName': '玩家',
    'tWinAt': '',

    'tNoWinnerText': '无人获胜',
}


dictStrCustomNote = {
    'strLBErrNotInGroup': '【LiarBar】错误\n该指令仅支持群聊',
    'strLBErrRoomNotFound': '【LiarBar】错误\n未开局/未找到房间',
    'strLBErrAlreadyStarted': '【LiarBar】错误\n游戏已开始',
    'strLBErrNotStarted': '【LiarBar】错误\n未在游戏中',
    'strLBErrNoPermission': '【LiarBar】错误\n权限不足',
    'strLBErrNotYourTurn': '【LiarBar】错误\n不是你的回合',
    'strLBErrNotInGame': '【LiarBar】错误\n你未参与本局',
    'strLBErrRoomFull': '【LiarBar】错误\n房间已满',
    'strLBErrNeedMorePlayers': '【LiarBar】错误\n人数不足',
    'strLBErrNeedFriendForPrivate': '【LiarBar】错误\nQQ 平台需加好友才能私聊发牌',
    'strLBErrPlayInPrivate': '【LiarBar】提示\n出牌需要私聊',
    'strLBErrBadCards': '【LiarBar】错误\n出牌输入非法',
    'strLBErrTooManyCards': '【LiarBar】错误\n单次最多出 3 张',
    'strLBErrDemonMustSingle': '【LiarBar】错误\n恶魔牌仅能单张',
    'strLBErrNoLastPlay': '【LiarBar】错误\n无上家出牌',
    'strLBErrCannotPlayOnlyDoubt': '【LiarBar】规则\n仅剩你未出完牌时只能质疑',

    'strLBJoinSuccess': '【LiarBar】入场\n加入成功',
    'strLBJoinFailAlreadyIn': '【LiarBar】入场\n重复加入',
    'strLBExitSuccess': '【LiarBar】入场\n开局前退出',
    'strLBLeaveSuccess': '【LiarBar】操作\n开局后离场',
    'strLBEndSuccess': '【LiarBar】管理\n结束并销毁数据',

    'strLBStartSuccess': '【LiarBar】开局\n开始提示',
    'strLBDealNotice': '【LiarBar】开局\n发牌提示',

    'strLBPrivateCardsHeader': '【LiarBar】私聊\n来自哪个群',
    'strLBPrivateCardsLine': '【LiarBar】私聊\n手牌内容行',
    'strLBPrivateCardsFooter': '【LiarBar】私聊\n尾部提示',

    'strLBStatusHeader': '【LiarBar】局势\n顶部信息',
    'strLBStatusSeparator': '【LiarBar】局势\n分隔线',
    'strLBStatusSeatLine': '【LiarBar】局势\n座位行',
    'strLBStatusTurnLine': '【LiarBar】局势\n轮到谁',
    'strLBStatusCmdHint': '【LiarBar】局势\n指令提示',
    'strLBStatusBoard': '【LiarBar】局势\n整体模板',

    'strLBTurnMark': '【LiarBar】显示\n当前回合标记',
    'strLBStateIdle': '【LiarBar】术语\n状态：空闲',
    'strLBStateWaiting': '【LiarBar】术语\n状态：等待开局',
    'strLBStatePlaying': '【LiarBar】术语\n状态：游戏中',

    'strLBCardA': '【LiarBar】术语\n牌：A',
    'strLBCardQ': '【LiarBar】术语\n牌：Q',
    'strLBCardK': '【LiarBar】术语\n牌：K',
    'strLBCardDemon': '【LiarBar】术语\n牌：恶魔',

    'strLBSeatStatusActive': '【LiarBar】术语\n玩家状态：在局',
    'strLBSeatStatusDead': '【LiarBar】术语\n玩家状态：淘汰',
    'strLBSeatStatusLeft': '【LiarBar】术语\n玩家状态：离场',
    'strLBSeatStatusExit': '【LiarBar】术语\n玩家状态：退出（开局前）',
    'strLBSeatStatusFinished': '【LiarBar】术语\n玩家状态：已出完牌',

    'strLBPlayBroadcast': '【LiarBar】出牌\n群内广播模板',
    'strLBDoubtAnnounce': '【LiarBar】质疑\n质疑宣告',
    'strLBDoubtReveal': '【LiarBar】质疑\n翻牌展示',
    'strLBDoubtSuccess': '【LiarBar】质疑\n质疑成功',
    'strLBDoubtFail': '【LiarBar】质疑\n质疑失败',

    'strLBShootBlank': '【LiarBar】惩罚\n空弹提示',
    'strLBShootReal': '【LiarBar】惩罚\n实弹淘汰提示',

    'strLBDemonPunishHeader': '【LiarBar】恶魔牌\n质疑后果头',
    'strLBDemonPunishEach': '【LiarBar】恶魔牌\n逐个惩罚提示',

    'strLBGameOverWinner': '【LiarBar】结局\n胜者公告',
    'strLBGameOverNoWinner': '【LiarBar】结局\n无人获胜（0存活）',

    'strLBCmdHintWaiting': '【LiarBar】指令\n等待开局阶段提示',
    'strLBCmdHintPlaying': '【LiarBar】指令\n游戏中阶段提示',
}


dictHelpDocTemp = {
    'liarbar': '''【LiarBar 骗子酒馆】
【入场/开局】
.lb join           加入本群游戏（2-6人）
.lb leave          个人离场（开局前=退出房间；开局后=离场）
.lb start          开始游戏（至少2人）
.lb list           查看当前玩家/座位（未开局也可用）
.lb status         查看局势

【手牌/出牌】
.lb show           群聊触发，bot 私聊返回你的手牌（QQ 平台需加好友）
（私聊）.lb play [牌]  出牌（每次最多 3 张；例如：AAK 或 A Q K；恶魔牌仅能单张）

【质疑】
.lb doubt          质疑上家（仅轮到你时）

【结束】
.lb end            强制结束/解散（权限：管理员/群主/骰主）

规则：使用 .help liarbar_rule 查看。''',

    'liarbar_rule': '''【LiarBar 规则】
【牌与发牌】
- 每轮会随机一个“真牌”（A/Q/K）。
- 每名玩家获得 5 张手牌（牌面只会出现 A/Q/K/恶魔）。
- 牌堆里存在 Joker：发到手里会直接变成本轮真牌（等同真牌）。

【回合与出牌】
- 游戏开始后会随机一个玩家先手。
- 轮到你时：私聊 bot 使用 .lb play [牌] 出牌（每次 1-3 张）。
- 恶魔牌只能单张打出。
- 若其余玩家都已出完牌，仅剩你还有手牌：你不能再出牌，只能在群里质疑上家。

【质疑】
- 质疑只能针对“上家刚出的牌”，且仅在轮到你时才能质疑。
- 若上家出的牌中存在非真牌：质疑成功，上家受罚。
- 若上家出的牌全为真牌：质疑失败，质疑者受罚。

【受罚】
- 受罚者会自罚一枪：空弹则存活；实弹则淘汰。

【恶魔牌】
- 恶魔牌在任何时候都视为真牌。
- 若下家质疑了恶魔牌：除出牌者外，其他所有玩家都要自罚一枪（包括已出完牌者）。

指令入口：使用 .help liarbar 查看。''',

    '骗子纸牌': '&liarbar',
    '骗子酒馆': '&liarbar',
    '骗子纸牌规则': '&liarbar_rule',
    '骗子酒馆规则': '&liarbar_rule',
    'liarbar规则': '&liarbar_rule',
    'lb规则': '&liarbar_rule',
    'lairbar_rule': '&liarbar_rule',
    'lairbar规则': '&liarbar_rule',
    'lairbar': '&liarbar',
    'lb': '&liarbar',
}
