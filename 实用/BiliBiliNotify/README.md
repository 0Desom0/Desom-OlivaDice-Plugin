# BiliBiliNotify · B站订阅推送

OlivOS 插件：B 站**直播开播 / 切换分区 / 下播**、**新动态**、**新视频**的群订阅推送。
按群、按主播两级开关；开播可 @ 全体（带配额）与 @ 订阅群友；QQ 官方机器人用 Markdown 卡片推送。

- namespace：`BiliBiliNotify`
- 版本：1.0.0
- 许可：MIT
- 依赖：OlivOS（含 `webui_config` 与 `scheduleAPI`）、`requests`；OlivaDiceCore 可选
  动态图片用 Pillow，直播统计用 websocket-client（优先 Brotli，兼容 zlib），扫码用 qrcode；沿用 OlivOS 核心依赖。
  直播报告与词云同样使用 Pillow；词云内置分词，可选 `jieba` 增强中文分词。

## 安装

把 `BiliBiliNotify.opk` 放进 `<OlivOS>/plugin/app/`（或任意子目录），重载插件即可。
数据目录：`plugin/data/BiliBiliNotify/`。

安装后打开 WebUI → 插件页面 → **B站订阅推送面板**。

## 命令

前缀默认 `.` `。` `/` `／`（WebUI 可增删），主命令 `bpush`。

| 命令 | 说明 |
|---|---|
| `.bpush up add <UID>` | 添加主播（只填 UID，房间号自动解析） |
| `.bpush up del <UID>` | 从本群移除 |
| `.bpush up list` | 本群主播清单 |
| `.bpush up live <UID> <on\|off>` | 分主播：直播检测开关 |
| `.bpush up dynamic <UID> <on\|off>` | 分主播：动态检测开关 |
| `.bpush up video <UID> <on\|off>` | 分主播：视频检测开关 |
| `.bpush up sub <UID>` | 订阅开播提醒（开播时 @ 你） |
| `.bpush up unsub <UID>` | 取消订阅 |
| `.bpush up subs` | 查看自己在本群的订阅 |
| `.bpush push <live\|dynamic\|video> <on\|off>` | 本群群级推送开关 |
| `.bpush push dynamic_img <on\|off\|auto>` | 本群动态图片 / 文字 / 跟随本账号（需 Pillow） |
| `.bpush push <report\|cloud> <on\|off\|auto>` | 分群开启、关闭或继承本账号的下播报告 / 词云推送 |
| `.bpush atall <on\|off>` | 本群开播 @全体 开关 |
| `.bpush status` | 运行状态 |
| `.bpush test <UID>` | 立即拉一次并推送测试消息 |
| `.bpush help` / `.bpush help sub` / `.bpush help push` | 命令总览 / 订阅管理 / 群推送设置 |
| `.bpush help stats` / `.bpush help 统计` | 直播统计帮助（需 websocket-client） |
| `.bpush room [主播]` / `.bpush 房间统计 [主播]` | 当前或最近一场直播及历史累计 |
| `.bpush me [B站UID或昵称] [主播]` / `.bpush 个人统计 …` | 观众互动与排行；省略观众时查询自己的绑定 UID |
| `.bpush bind <B站UID>` / `.bpush 绑定 <B站UID>` | 为当前聊天账号保存 B 站 UID |
| `.bpush rank <弹幕\|礼物\|SC\|盲盒\|进场\|点赞> [本场\|总榜] [主播]` / `.bpush 排行 …` | 互动榜前 10 名，默认本场 |
| `.bpush report [主播]` / `.bpush 直播报告 [主播]` | 查看当前或最近一场的直播报告长图 |
| `.bpush cloud [主播]` / `.bpush 词云 [主播]` | 查看当前或最近一场的弹幕词云 |

管理权限：群主 / 管理员 / 骰主（读 OlivaDiceCore 骰主列表）/ WebUI 白名单。

直播统计命令向全体群成员开放；查询对象限本群订阅的主播。单主播可省略主播参数，多主播可填写 UID 或昵称关键词。
同群的房间、个人、排行、报告和词云查询默认共用 10 秒冷却；绑定后可直接查询个人统计。

## 推送规则

一条推送要同时满足三层：

```
群开关 groups.<群>.push.<类型>
AND 群对这个主播的订阅 targets.<群>.<类型>
AND 主播开关 rooms.<UID>.<类型>.enabled
```

- 首次添加主播时把「最新动态 / 最新视频」记为当前值，**不会把历史刷一遍**。
- 动态跳过投稿动态（`DYNAMIC_TYPE_AV`，避免与视频重复）与置顶动态。
- 动态默认发送文字和首图。「本账号 → 推送与提醒」可开启图片卡片，「群订阅 → 动态图片」可覆盖本账号默认。
- 图片卡片附原动态直达链接；生成或发送失败时回退文字和首图。可在「本账号」开启存档，副本写入 `plugin/data/BiliBiliNotify/dynamics/`。
- 下播场次封账后，直播报告与词云分条发送给已关联群。两项默认开启，群可分别覆盖；默认门槛为直播至少 3 分钟且弹幕至少 5 条，设为 0 时放开对应门槛。
- @全体：OneBot 每群每天默认 10 次（WebUI 可改）；QQ 官方群每次开播只 @ 一次。
- @订阅者只作用于开播，不截断；过长时按 `[OP:...]` 段不拆分的原则自动分条。

## WebUI

五个页签：**总账号**（Cookie / UA / 代理 / 白名单 / 接口自检）、**本账号**（开关与轮询间隔）、
**主播管理**、**群订阅**、**运行状态**。

在「本账号 → 直播数据统计与实时查询」设置采集、断流宽限（默认 120 秒）、群查询冷却与弹幕原文保留（默认 30 天）。
宽限期内重新开播接续同一场次并省略重复开播推送。启用营收隐私后，群统计、报告图和历史预览均隐藏金额与付费榜。
互动数据来自有效的直播间长连接，采集范围受主播直播检测开关和长连接上限影响。

可调整词云词数、热词和停用词，列表以换行或逗号分隔。「主播管理 → 历史场次」列出最近 10 场，可按场预览报告与词云。
报告、词云及对应群命令需要 Pillow 与 websocket-client；文字弹幕原文到期后仍可查看报告。

## 关于 B 站风控

插件内置 buvid3/buvid4 设备指纹、PC 浏览器 UA、Origin/Referer 与 wbi 签名，普通网络下无需任何配置。
若所在出口 IP 被 B 站风控（表现为 `code=-412 request was banned`），直播接口通常仍可用，但动态/视频会失败：

1. 在 WebUI「总账号」里填 `SESSDATA` 与 `bili_jct`（网页登录后从浏览器 Cookie 复制）；
2. 或换一个出口 IP；
3. 面板顶部会出现风控提示，群内只提示一次（6 小时冷却）。

## 数据

```
plugin/data/BiliBiliNotify/
├── global.json                     # 总账号：Cookie / UA / 代理 / 白名单
├── stats.db                        # 跨 Bot 共享的场次、互动汇总、文字弹幕和聊天账号绑定
├── reports/<uid>/                  # 可选存档：下播直播报告与弹幕词云
└── accounts/<bot_hash>/
    ├── config.json                 # 本账号：开关、轮询间隔、@全体配额
    ├── rooms.json                  # 主播 + 群订阅 + 订阅者 + 运行游标
    └── persist_error.log           # 读写异常记录
```

JSON 写入采用「临时文件 → fsync → 备份 → 原子替换」；读取失败会将原文件归档为 `.corrupt-<时间戳>`。
统计数据采用 SQLite WAL，事件每 5 秒或 50 条批量提交，查询前同步刷盘。弹幕原文到期清理，历史聚合与排行榜保留。

## 支持平台

- OneBot / QQ：普通图文（OP 段）
- QQ 官方机器人（qqGuildv2）**群聊**：Markdown 卡片
- qqGuildv2 频道：不支持（不订阅、不推送、不响应命令）
