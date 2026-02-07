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
    'tRankTotal': '0'
}

dictStrCustomNote = {
    'strSignResult': '【签到】命令\n签到获得灵币与今日人品',
    'strSignAlready': '【签到】命令\n重复签到提示',
    'strCoinInfo': '【灵币】命令\n查询自己的灵币数量',
    'strCoinRankGroup': '【灵币排行】命令\n查看本群灵币排行',
    'strCoinRankGlobal': '【灵币总榜】命令\n查看全局灵币排行',
}

dictHelpDocTemp = {
    'FroniaSign': '''【FroniaSign】
.签到 / .打卡 进行签到（每天一次）
.灵币 查询自己的灵币
.灵币排行 查看本群灵币排行（仅群聊）
.灵币总榜 查看灵币总榜
''',
}
