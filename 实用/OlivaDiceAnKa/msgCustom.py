# -*- encoding: utf-8 -*-
'''
安价插件自定义文本。
'''

import OlivOS
import OlivaDiceCore
import OlivaDiceAnKa

dictStrCustomDict = {}

dictStrCustom = {
    'strAnkaNoData': '本群暂无安价。你可以用 .anka create 创建。',
    'strAnkaNoActive': '当前没有活跃安价。你可以用 .anka on 开启一个。',
    'strAnkaListTitle': '本群安价列表：',
    'strAnkaListLine': '- {tAnkaName} (选项:{tAnkaCount}){tAnkaCurrent}{tAnkaActive}',

    'strAnkaCreateOn': '已创建/开启安价[{tAnkaName}]，并切换为当前安价。',
    'strAnkaOffSuccess': '已关闭当前活跃安价[{tAnkaName}]。',
    'strAnkaOffNoActive': '当前没有活跃安价可关闭。',
    'strAnkaSetUsage': '用法：.anka set [安价名字]',
    'strAnkaSetNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaSetRecommend': '请从推荐候选中选择要切换的安价\n{tSearchResult}',
    'strAnkaSetSuccess': '已切换当前安价为[{tAnkaName}]。',

    'strAnkaAddUsage': '用法：.anka add (安价名字) [选项内容]',
    'strAnkaOptionEmpty': '选项内容不能为空。',
    'strAnkaAddSuccess': '已向安价[{tAnkaName}]添加选项 #{tAnkaIndex}：{tAnkaOption}',

    'strAnkaRmUsage': '用法：.anka rm (安价名字) [第几个选项]',
    'strAnkaNotExist': '安价[{tAnkaName}]不存在。',
    'strAnkaNoOptionToRm': '安价[{tAnkaName}]没有可删除的选项。',
    'strAnkaRmIndexNotNumber': '删除序号必须是阿拉伯数字。',
    'strAnkaRmIndexOutOfRange': '序号超出范围，当前共有 {tAnkaCount} 个选项。',
    'strAnkaRmSuccess': '已从安价[{tAnkaName}]删除第{tAnkaIndex}个选项：{tAnkaOption}',

    'strAnkaEndNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaEndSuccess': '已删除安价[{tAnkaName}]。',
    'strAnkaClrSuccess': '已清空安价[{tAnkaName}]的全部选项。',

    'strAnkaDrawNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaNoOptionToDraw': '安价[{tAnkaName}]没有可抽取的选项。',
    'strAnkaDrawErrNoCount': '选项数量不足。',
    'strAnkaDrawErrOneDice': 'onedice异常：{tAnkaError}',
    'strAnkaDrawErrOneDiceResult': 'onedice结果异常。',
    'strAnkaDrawWithReturn': '安价[{tAnkaName}]抽取结果：#{tAnkaIndex} {tAnkaOption}',
    'strAnkaDrawNoReturn': '安价[{tAnkaName}]抽取结果（不放回）：#{tAnkaIndex} {tAnkaOption}\n已移除该选项，剩余 {tAnkaCount} 项。',
    'strAnkaDrawMultiTitle': '安价[{tAnkaName}]抽取结果（共{tAnkaDrawCount}次）：',
    'strAnkaDrawMultiLine': '{tAnkaHistoryNo}. #{tAnkaIndex} {tAnkaOption}',
    'strAnkaDrawMultiTailNoReturn': '已移除 {tAnkaDrawCount} 项，剩余 {tAnkaCount} 项。',

    'strAnkaHistoryUsage': '用法：.anka history (安价名字) (条数)',
    'strAnkaHistoryNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaNoHistory': '安价[{tAnkaName}]暂无抽取历史。',
    'strAnkaHistoryTitle': '安价[{tAnkaName}]抽取历史（显示最近{tAnkaHistoryShow}条 / 共{tAnkaHistoryTotal}条）：',
    'strAnkaHistoryLine': '{tAnkaHistoryNo}. [{tAnkaHistoryTime}] ({tAnkaHistoryMode}) #{tAnkaIndex} {tAnkaOption} - {tAnkaHistoryUser}',

    'strAnkaShowNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaNoOptionToShow': '安价[{tAnkaName}]当前没有选项。',
    'strAnkaShowTitle': '安价[{tAnkaName}]选项列表（共{tAnkaCount}项）：',
    'strAnkaShowLine': '{tAnkaIndex}. {tAnkaOption}',

    'strAnkaListEmpty': '本群暂无安价。',
    'strAnkaUnknownSubCommand': '未知子命令。可用：create/on, off, set, add, rm, del/end/clr, draw, show, history, list'
}

dictStrConst = {
}

dictGValue = {
}

dictTValue = {
    'tAnkaName': 'default',
    'tAnkaQueryName': 'default',
    'tAnkaCount': '0',
    'tAnkaCurrent': '',
    'tAnkaActive': '',
    'tAnkaIndex': '1',
    'tAnkaOption': '',
    'tAnkaError': '',
    'tAnkaHistoryNo': '1',
    'tAnkaHistoryTime': '1970-01-01 00:00:00',
    'tAnkaHistoryMode': '放回',
    'tAnkaHistoryUser': '玩家',
    'tAnkaHistoryTotal': '0',
    'tAnkaHistoryShow': '0',
    'tAnkaDrawCount': '1'
}

dictStrCustomNote = {
    'strAnkaNoData': '【.anka】指令\n当前群没有安价时的提示',
    'strAnkaNoActive': '【.anka 通用】指令\n当前没有活跃安价时的提示',
    'strAnkaListTitle': '【.anka / .anka list】指令\n安价列表标题',
    'strAnkaListLine': '【.anka / .anka list】指令\n安价列表明细',
    'strAnkaCreateOn': '【.anka create / .anka on】指令\n创建或开启安价后的提示',
    'strAnkaOffSuccess': '【.anka off】指令\n关闭当前活跃安价成功提示',
    'strAnkaOffNoActive': '【.anka off】指令\n没有活跃安价可关闭时的提示',
    'strAnkaSetUsage': '【.anka set】指令\n切换安价命令用法提示',
    'strAnkaSetNotFound': '【.anka set】指令\n未找到目标安价时的提示',
    'strAnkaSetRecommend': '【.anka set】指令\n模糊匹配推荐提示',
    'strAnkaSetSuccess': '【.anka set】指令\n切换安价成功提示',
    'strAnkaAddUsage': '【.anka add】指令\n添加选项命令用法提示',
    'strAnkaOptionEmpty': '【.anka add】指令\n选项内容为空时的提示',
    'strAnkaAddSuccess': '【.anka add】指令\n添加选项成功提示',
    'strAnkaRmUsage': '【.anka rm】指令\n删除选项命令用法提示',
    'strAnkaNotExist': '【安价通用】提示\n目标安价不存在时的提示',
    'strAnkaNoOptionToRm': '【.anka rm】指令\n没有可删除选项时的提示',
    'strAnkaRmIndexNotNumber': '【.anka rm】指令\n删除序号不是阿拉伯数字时的提示',
    'strAnkaRmIndexOutOfRange': '【.anka rm】指令\n删除序号越界时的提示',
    'strAnkaRmSuccess': '【.anka rm】指令\n删除选项成功提示',
    'strAnkaEndNotFound': '【.anka del / end / clr】指令\n未找到目标安价时的提示',
    'strAnkaEndSuccess': '【.anka del / end】指令\n删除安价成功提示',
    'strAnkaClrSuccess': '【.anka clr】指令\n清空安价选项成功提示',
    'strAnkaDrawNotFound': '【.anka draw】指令\n未找到目标安价时的提示',
    'strAnkaNoOptionToDraw': '【.anka draw】指令\n没有可抽取选项时的提示',
    'strAnkaDrawErrNoCount': '【.anka draw】指令\n选项数量不足时的提示',
    'strAnkaDrawErrOneDice': '【.anka draw】指令\nonedice掷骰异常提示',
    'strAnkaDrawErrOneDiceResult': '【.anka draw】指令\nonedice结果异常提示',
    'strAnkaDrawWithReturn': '【.anka draw】指令\n放回抽取结果提示',
    'strAnkaDrawNoReturn': '【.anka draw】指令\n不放回抽取结果提示',
    'strAnkaDrawMultiTitle': '【.anka draw】指令\n多次抽取结果标题',
    'strAnkaDrawMultiLine': '【.anka draw】指令\n多次抽取结果明细',
    'strAnkaDrawMultiTailNoReturn': '【.anka draw】指令\n多次不放回抽取尾部提示',
    'strAnkaHistoryUsage': '【.anka history】指令\n查看历史命令用法提示',
    'strAnkaHistoryNotFound': '【.anka history】指令\n未找到目标安价时的提示',
    'strAnkaNoHistory': '【.anka history】指令\n没有历史记录时的提示',
    'strAnkaHistoryTitle': '【.anka history】指令\n历史记录标题',
    'strAnkaHistoryLine': '【.anka history】指令\n历史记录明细',
    'strAnkaShowNotFound': '【.anka show】指令\n未找到目标安价时的提示',
    'strAnkaNoOptionToShow': '【.anka show】指令\n没有可展示选项时的提示',
    'strAnkaShowTitle': '【.anka show】指令\n选项列表标题',
    'strAnkaShowLine': '【.anka show】指令\n选项列表明细',
    'strAnkaListEmpty': '【.anka list】指令\n安价列表为空时的提示',
    'strAnkaUnknownSubCommand': '【.anka】指令\n子命令不存在时的提示'
}

dictHelpDocTemp = {
    'anka': '''【安价插件】
前缀可以是 .anka 或 .安价 或 .ak
.anka create/on (安价名字)
    创建安价并切换为当前活跃安价；已存在则继续该安价。不填名字默认 default。
.anka off
    关闭当前活跃安价。
.anka set [安价名字]
    切换当前安价，支持模糊匹配。
.anka add (安价名字) [选项内容]
    向指定安价（或当前安价）添加选项。
.anka rm (安价名字) [第几个选项]
    删除指定序号选项（从 1 开始）。
.anka del/end (安价名字)
    删除指定安价。
.anka clr (安价名字)
    清空指定安价的选项，不删除该安价。
.anka draw (安价名字) (次数) [不放回参数]
    抽取选项。默认放回、默认1次；支持“不放回/nr/noreturn/remove/pop”。
.anka show (安价名字)
    查看安价所有选项。
.anka his (安价名字) (条数)
    查看安价抽取历史；条数可选，默认20。
.anka list
    查看本群安价列表。''',
    '安价': '&anka',
    'ak': '&anka'
}
