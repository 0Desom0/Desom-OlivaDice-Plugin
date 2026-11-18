# -*- encoding: utf-8 -*-
"""CelestePlugin 默认帮助与提示文本。"""


help_text = '''【CelestePlugin 帮助】
数据源：WEGFan 镜像（celeste.weg.fan）
前缀：.clst / 。clst / /clst

【Mod 查询】
.clst <关键词>             按标题搜索；纯数字也按标题处理
.clst id <数字>            按 GameBanana ID 精确查询
.clst 作者 <名称>          按投稿者查询（WEGFan 本地索引）
.clst 分类 <名称>          按主分类或子分类查询
.clst 标签 <名称>          按子分类、标题与简介关键词查询

搜索列表可直接回复序号；翻页使用：下一页 / 上一页 / 跳页3。

【地图推荐】
.clst 随机 [1-10]         从 WEGFan 本地索引随机抽图；多个只显示概要，单个展示完整简介
.clst today               今日 Mod，每人每天随机一图，当天固定不变
.clst 更新                骰主限定：手动重建 WEGFan 本地索引

【Celeste Endless】
.clst 无尽 帮助            查看玩法、操作和个人记录命令

【当前群开关】
.clst status / on / off
群主、群管或骰主可修改开关。'''


endless_help_text = '''【Celeste Endless 帮助】
地图从 WEGFan 镜像抽取，每次抽图都会展示封面。

【开始与查看】
.clst 无尽 开始 /start [0-10]  开始挑战，默认 1 次跳过
.clst 无尽 状态 /status        查看分数、跳过次数和当前地图
.clst 无尽 详情 /detail        查看当前地图完整 Mod 信息

【结算当前地图】
.clst 无尽 通关 /clear         分数 +1，并抽取下一图
.clst 无尽 全收集 /fc          分数 +1、跳过次数 +1，并抽取下一图
.clst 无尽 跳过 /skip          消耗 1 次跳过；次数不足则本局失败
.clst 无尽 坏图 /reroll        免费重抽，不计分也不消耗跳过

【挑战管理】
.clst 无尽 继续 /continue      抽图失败后重新请求下一图
.clst 无尽 撤销 /undo          撤销上一步操作
.clst 无尽 放弃 /giveup        立即失败并记录本局分数
.clst 无尽 结束 /end           主动结束、记录分数并清除进度
.clst 无尽 记录 /record        查看上次、最佳分数和记录局数'''
