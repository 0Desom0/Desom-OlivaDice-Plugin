# -*- encoding: utf-8 -*-
"""CelestePlugin 默认帮助与提示文本。"""


help_text = '''【CelestePlugin 帮助】
前缀：.clst / 。clst / /clst（中英文命令都能用）

【查询 Query】      .clst 帮助 查询
【推荐 Picks】      .clst 帮助 推荐
【挑图池 Pools】    .clst 帮助 池子
【无尽 Endless】    .clst 帮助 无尽
【管理 Manage】     .clst 帮助 管理

也可以直接点消息下面的按钮。'''


help_topic_plain = {
    'query': '''【查询 Query】
.clst <关键词> / keyword      标题搜索
.clst id <数字>               按 GameBanana ID 精确查询 / exact lookup
.clst 作者 <名称> / author    按投稿者查询
.clst 分类 <名称> / category  按主分类、子分类查询
.clst 标签 <名称> / tag       按子分类、标题与简介查询
翻页：.clst 上一页 / .clst 下一页 / .clst 跳页 3
搜索列表可直接回复序号看详情。''',
    'picks': '''【推荐 Picks】
.clst 随机 [1-10] / random    全库随机抽图；多个只显示概要
.clst 发现 / pools            六个挑图池总入口
.clst today                   今日 Mod，每人每天随机一图，当天固定
.clst 更新 / update           骰主限定：手动重建本地索引''',
    'pools': '''【挑图池 Pools】
.clst 发现 / pools            挑图池总入口（显示每个池子多少张）
.clst 新图|老图|热门|冷门|好图|烂图 [1-10]
      / new|old|hot|cold|good|bad   在对应池子里随机抽图
池子里张数不够时按实际数量给。''',
    'endless': '''【无尽挑战 Endless】
.clst 无尽 开始 / endless start [0-10]   开始挑战
.clst 无尽 状态 / endless status         查看分数、跳过与当前地图
.clst 无尽 详情 / endless detail         当前地图完整信息
.clst 无尽 帮助 / endless help           完整玩法与结算命令''',
    'manage': '''【群管理 Manage】
.clst status                  查看本群开关
.clst on / off                开启 / 关闭插件
.clst 更新 / update           骰主限定：手动重建本地索引
群主、群管或骰主可修改开关。''',
}


def help_topic_text(topic: str) -> str:
    """纯文本回退：按分类给对应说明，拿不到就回首页。"""
    return help_topic_plain.get(topic, help_text)


endless_help_text = '''【Celeste Endless 帮助】
地图从 WEGFan 镜像抽取，每次抽图都会展示封面；中英文命令都能用。

【开始与查看 Start & Status】
.clst 无尽 开始 / endless start [0-10]   开始挑战，默认 1 次跳过
.clst 无尽 状态 / endless status         查看分数、跳过次数和当前地图
.clst 无尽 详情 / endless detail         查看当前地图完整 Mod 信息

【结算当前地图 Settle】
.clst 无尽 通关 / endless clear          分数 +1，并抽取下一图
.clst 无尽 全收集 / endless fc           分数 +1、跳过次数 +1，并抽取下一图
.clst 无尽 跳过 / endless skip           消耗 1 次跳过；次数不足则本局失败
.clst 无尽 坏图 / endless reroll         免费重抽，不计分也不消耗跳过

【挑战管理 Manage】
.clst 无尽 继续 / endless continue       抽图失败后重新请求下一图
.clst 无尽 撤销 / endless undo           撤销上一步操作
.clst 无尽 放弃 / endless giveup         立即失败并记录本局分数
.clst 无尽 结束 / endless end            主动结束、记录分数并清除进度
.clst 无尽 记录 / endless record         查看上次、最佳分数和记录局数'''
