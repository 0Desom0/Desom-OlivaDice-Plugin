# -*- encoding: utf-8 -*-
"""CelestePlugin 默认帮助与提示文本。"""


help_text = '''【Celeste Mod 查询帮助】
触发前缀：.clst / 。clst / /clst

1. .clst 关键词
按标题搜索；也可使用 .clst 搜索 关键词。

2. .clst id 424541
按 GameBanana Mod ID 精确查询。只有使用 id 命令才会进行 ID 查询。
直接输入纯数字，例如 .clst 2020，会作为 Mod 标题关键词搜索。

3. .clst 作者 作者名
从 Celeste 社区数据库中按作者筛选。

4. .clst 分类 Maps
按主分类或子分类筛选，例如 Maps、Helpers、Campaign、Collab/Contest。

5. .clst 标签 English
按子分类及 GameBanana 标签查询。子分类结果完整；自由标签索引会随已查看详情逐步积累。

6. .clst 随机 [数量]
从 Maps 主分类中随机 1 至 10 个 Mod，例如 .clst 随机 5。

7. .clst today
每天固定随机一个 Maps 主分类的 Mod。

8. .clst 无尽 开始 [初始跳过次数]
Celeste Endless，只会抽取 Maps 分类；初始跳过次数为 0 至 10，默认 1。

9. .clst 无尽 通关 / 全收集 / 跳过 / 坏图 / 继续 / 撤销 / 状态 / 放弃 / 结束
普通通关得 1 分；全收集得 1 分并增加一次跳过；跳过消耗一次；坏图重抽不消耗。

10. .clst 无尽 记录 / .clst endless record
查看个人的上次无尽分数、最佳无尽分数和已记录局数。

11. .clst on / .clst off / .clst status
在当前群单独开启或关闭本插件，仅群主、群管或 OlivaDiceCore 骰主可用。

搜索列表出现后，可直接发送序号查看详情；也可发送“下一页”“上一页”“跳页3”。'''


endless_help_text = '''【Celeste Endless】
.clst 无尽 开始 [0-10]  开始新挑战
.clst 无尽 状态          查看当前进度和地图
.clst 无尽 继续          远端故障后重试抽取下一图
.clst 无尽 通关          记 1 分并抽取下一图
.clst 无尽 全收集        记 1 分、跳过次数 +1，并抽取下一图
.clst 无尽 跳过          消耗一次跳过；没有次数时挑战失败
.clst 无尽 坏图          免费重抽当前地图
.clst 无尽 撤销          撤销上一步操作
.clst 无尽 记录 / record 查看个人上次分数、最佳分数和记录局数
.clst 无尽 放弃          立即结束本局
.clst 无尽 结束          清除当前挑战状态'''
