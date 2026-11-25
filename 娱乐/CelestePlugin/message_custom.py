# -*- encoding: utf-8 -*-
"""CelestePlugin 默认帮助与提示文本。"""


help_text = '''【CelestePlugin 帮助】
数据源：WEGFan 镜像（celeste.weg.fan）
前缀：.clst / 。clst / /clst（中英文命令都能用）

【Mod 查询 Query】
.clst <关键词> / keyword      标题搜索
.clst id <数字>               按 GameBanana ID 精确查询 / exact lookup
.clst 作者 <名称> / author    按投稿者查询
.clst 分类 <名称> / category  按主分类、子分类查询
.clst 标签 <名称> / tag       按子分类、标题与简介查询

搜索列表可直接回复序号；翻页使用：下一页 / 上一页 / 跳页3。

【地图推荐 Picks】
.clst 随机 [1-10] / random    全库随机抽图；多个只显示概要
.clst 发现 / pools            六个挑图池总入口（新图/老图 · 热门/冷门 · 好图/烂图）
.clst 新图|老图|热门|冷门|好图|烂图 [1-10]
      / new|old|hot|cold|good|bad   在对应池子里随机抽图
.clst today                   今日 Mod，每人每天随机一图，当天固定不变
.clst 更新 / update           骰主限定：手动重建 WEGFan 本地索引

【Celeste Endless】
.clst 无尽 开始 / endless start    开始挑战
.clst 无尽 帮助 / endless help     查看玩法、操作和个人记录命令

【当前群开关 Group Switch】
.clst status / on / off
群主、群管或骰主可修改开关。'''


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
