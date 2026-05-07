# -*- encoding: utf-8 -*-
'''
这里写你的自定义回复
'''

import OlivOS
import OlivaDiceCore
import jrlp

dictStrCustomDict = {}

dictStrCustom = {
    'jrlpMode': '0',
    'jrlpFirst': '让小芙瞧瞧，[{tUserName}]今天的群老婆是：\n{name}({qq})',
    'jrlpRepeat': '[{tUserName}]今天已经有老婆啦，不要太贪心哦！\n你的今日老婆是：{name}({qq})',
    'jrlpRobot': '让小芙瞧瞧，[{tUserName}]今天的群老婆是：\n{name}({qq})\n哇，你抽到了小芙！今天小芙就是你的老婆了~',
    'jrlpSelf': '让小芙瞧瞧，[{tUserName}]今天的群老婆是：\n{name}({qq})\n哇，你的今日老婆居然是自己诶！',
    'jrlpNoAvailable': '[{tUserName}]今天已经没有可抽取的对象啦，明天再来试试吧~'
}

dictStrConst = {
}

dictGValue = {
}

dictTValue = {
}

dictStrCustomNote = {
    'jrlpMode': '【配置参数】纯爱模式开关\n0=普通模式；1=纯爱模式；其他=按普通模式处理',
    'jrlpFirst': '【今日老婆】首次抽取\n首次抽取今日老婆时的回复',
    'jrlpRepeat': '【今日老婆】重复查看\n重复查看今日老婆时的回复',
    'jrlpSelf': '【今日老婆】抽到自己\n普通模式抽到自己时的回复',
    'jrlpRobot': '【今日老婆】抽到机器人\n抽到机器人自己时的回复',
    'jrlpNoAvailable': '【今日老婆】无可抽取对象\n纯爱模式下没有可抽取对象时的回复'
}

dictHelpDocTemp = {
    '今日老婆': '''【今日老婆帮助】
查看今天的群老婆，
每日只能抽取一次，重复使用将显示同一个人。
可在自定义回复中将 jrlpMode 设为 1 以启用纯爱模式。'''
}