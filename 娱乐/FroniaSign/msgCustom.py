# -*- encoding: utf-8 -*-
'''
这里写你的自定义回复
'''

import OlivOS
import OlivaDiceCore
import FroniaSign

dictStrCustomDict = {}

dictStrCustom = {
    'strSignResult': '【签到】\n{tSignText}\n[{tUserName}]获得了灵币{tCoinDelta}个！\n当前灵币：{tCoinTotal}\n今日人品：{tJrrpResult}',
    'strSignAlready': '【签到】\n哎呀，[{tUserName}]今天已经签到过了呢！是这时候签到的：{tLastSignTime}\n当前灵币：{tCoinTotal}\n今日人品：{tJrrpResult}',
    'strCoinInfo': '【灵币】\n当前灵币：{tCoinTotal}',
    'strCoinRankGroup': '【本群灵币排行】\n{tRankList}\n\n小芙查到了[{tUserName}]的排名：{tSelfRank} / {tRankTotal}（{tCoinTotal}）',
    'strCoinRankGlobal': '【灵币总榜】\n{tRankList}\n\n小芙查到了[{tUserName}]的排名：{tSelfRank} / {tRankTotal}（{tCoinTotal}）',
    'strQdBindOk': '【绑定】\nQQ {tQdTargetQq} 已经并进你的账号啦~\n本次转入灵币：{tQdDelta}\n当前灵币：{tCoinTotal}',
    'strQdBindDup': '【绑定】\nQQ {tQdTargetQq} 已经被绑定过了哦，不能重复绑定~',
    'strQdBindSelf': '【绑定】\n不能把自己绑给自己啦，小芙可不吃这套~',
    'strQdBindOwner': '【绑定】\nQQ {tQdTargetQq} 名下还挂着别的绑定呢，先让它解绑再说~',
    'strQdUnbindOk': '【解绑】\n已解除 QQ {tQdTargetQq} 的绑定\n退回灵币：{tQdRefund}\n它从现在开始独立记账~',
    'strQdUnbindNone': '【解绑】\nQQ {tQdTargetQq} 没有绑定记录哦，是不是记错了？',
    'strQdUnbindDeny': '【解绑】\n这条绑定不是你建的，解不掉呢~',
    'strQdUsage': '【绑定】\n用法：\n.qdbind <QQ号> 把该 QQ 号的灵币并入你的账号\n.qdunbind <QQ号> 解除绑定',
}

dictStrConst = {
}

dictGValue = {
}

dictTValue = {
    'tSignText': '',
    'tCoinDelta': '0',
    'tCoinTotal': '0',
    'tJrrpResult': '0',
    'tLastSignTime': '',
    'tRankList': '',
    'tSelfRank': '-',
    'tRankTotal': '0',
    'tQdTargetQq': '',
    'tQdDelta': '0',
    'tQdRefund': '0'
}

dictStrCustomNote = {
    'strSignResult': '【签到】命令\n签到获得灵币与今日人品',
    'strSignAlready': '【签到】命令\n重复签到提示',
    'strCoinInfo': '【灵币】命令\n查询自己的灵币数量',
    'strCoinRankGroup': '【灵币排行】命令\n查看本群灵币排行',
    'strCoinRankGlobal': '【灵币总榜】命令\n查看全局灵币排行',
    'strQdBindOk': '【绑定】命令\n绑定成功，数据已并入',
    'strQdBindDup': '【绑定】命令\n该 QQ 号已被绑定过',
    'strQdBindSelf': '【绑定】命令\n不能绑定自己',
    'strQdBindOwner': '【绑定】命令\n目标账号名下还有绑定',
    'strQdUnbindOk': '【解绑】命令\n解除绑定成功，退回当初并入的灵币',
    'strQdUnbindNone': '【解绑】命令\n该 QQ 号没有绑定记录',
    'strQdUnbindDeny': '【解绑】命令\n无权解除他人的绑定',
    'strQdUsage': '【绑定】命令\n用法提示',
}

dictHelpDocTemp = {
    'FroniaSign': '''【FroniaSign】
.签到 / .打卡 进行签到（每天一次）
.灵币 查询自己的灵币
.灵币排行 查看本群灵币排行（仅群聊）
.灵币总榜 查看灵币总榜
.qdbind <QQ号> 把该 QQ 号的灵币并入你的账号（每个 QQ 只能绑一次；QQ 号按 OneBot/QQ 平台识别）
.qdunbind <QQ号> 解除绑定，并入的灵币退回原号
''',
}
