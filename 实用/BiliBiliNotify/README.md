# BiliBiliNotify · B站订阅推送

OlivOS 插件：B 站**直播开播 / 切换分区 / 下播**、**新动态**、**新视频**的群订阅推送。
按群、按主播两级开关；开播可 @ 全体（带配额）与 @ 订阅群友；QQ 官方机器人用 Markdown 卡片推送。

- namespace：`BiliBiliNotify`
- 版本：1.0.0
- 许可：MIT
- 依赖：OlivOS（含 `webui_config` 与 `scheduleAPI`）、`requests`；OlivaDiceCore 可选

## 安装

把 `BiliBiliNotify.opk` 放进 `<OlivOS>/plugin/app/`（或任意子目录），重载插件即可。
数据目录：`plugin/data/BiliBiliNotify/`。

安装后打开 WebUI → 插件页面 → **B站订阅推送面板**。

## 命令

前缀默认 `.` `。` `/` `／`（WebUI 可增删），主命令 `bili`。

| 命令 | 说明 |
|---|---|
| `.bili up add <UID>` | 添加主播（只填 UID，房间号自动解析） |
| `.bili up del <UID>` | 从本群移除 |
| `.bili up list` | 本群主播清单 |
| `.bili up live <UID> <on\|off>` | 分主播：直播检测开关 |
| `.bili up dynamic <UID> <on\|off>` | 分主播：动态检测开关 |
| `.bili up video <UID> <on\|off>` | 分主播：视频检测开关 |
| `.bili up sub <UID>` | 订阅开播提醒（开播时 @ 你） |
| `.bili up unsub <UID>` | 取消订阅 |
| `.bili up subs` | 查看自己在本群的订阅 |
| `.bili push <live\|dynamic\|video> <on\|off>` | 本群群级推送开关 |
| `.bili atall <on\|off>` | 本群开播 @全体 开关 |
| `.bili status` | 运行状态 |
| `.bili test <UID>` | 立即拉一次并推送测试消息 |
| `.bili help` | 帮助 |

权限：群主 / 管理员 / 骰主（读 OlivaDiceCore 骰主列表）/ WebUI 白名单。

## 推送规则

一条推送要同时满足三层：

```
群开关 groups.<群>.push.<类型>
AND 群对这个主播的订阅 targets.<群>.<类型>
AND 主播开关 rooms.<UID>.<类型>.enabled
```

- 首次添加主播时把「最新动态 / 最新视频」记为当前值，**不会把历史刷一遍**。
- 动态跳过投稿动态（`DYNAMIC_TYPE_AV`，避免与视频重复）与置顶动态。
- 消息带图时只发第一张：直播用封面，动态用首图，视频用封面。
- @全体：OneBot 每群每天默认 10 次（WebUI 可改）；QQ 官方群每次开播只 @ 一次。
- @订阅者只作用于开播，不截断；过长时按 `[OP:...]` 段不拆分的原则自动分条。

## WebUI

五个页签：**总账号**（Cookie / UA / 代理 / 白名单 / 接口自检）、**本账号**（开关与轮询间隔）、
**主播管理**、**群订阅**、**运行状态**。

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
└── accounts/<bot_hash>/
    ├── config.json                 # 本账号：开关、轮询间隔、@全体配额
    ├── rooms.json                  # 主播 + 群订阅 + 订阅者 + 运行游标
    └── persist_error.log           # 读写异常记录
```

所有写入均为「临时文件 → fsync → 备份 → 原子替换」；读取失败会把原文件归档成 `.corrupt-<时间戳>` 再回落默认值。

## 支持平台

- OneBot / QQ：普通图文（OP 段）
- QQ 官方机器人（qqGuildv2）**群聊**：Markdown 卡片
- qqGuildv2 频道：不支持（不订阅、不推送、不响应命令）
