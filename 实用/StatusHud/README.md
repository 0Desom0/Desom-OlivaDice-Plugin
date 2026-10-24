# StatusHud

为指令处理过程中实际调用过 OlivaDiceCore OneDice `RD.roll()` 的回复结果添加当前人物卡的 `sn` 文本。QQ 官方机器人（qqGuildV2）支持 Markdown 时优先主动发送 Markdown 消息：状态栏使用块引用弱化显示，与结果之间空一行，且不加 `『』`；其余情况沿用既有文本注入，每人一行 `『』`，最后一条后接两个换行再接原回复。

## 安装

依赖 OlivOS 与 OlivaDiceCore。已用本次提供的 Core 3.5.1（svn 1201）源码验证，Python 3.11。

把 `StatusHud.opk` 放入 OlivOS 的 `plugin/app/`，然后重载插件；或复制完整 `StatusHud/` 源码目录到 `plugin/app/StatusHud/`。两种安装方式选择一种，避免重复加载。

本插件没有 WebUI。默认优先级为 19000，先于 Core 的 20000；若手动设置过插件优先级，请保持 StatusHud 的命令入口先于 Core。

## 命令

| 指令 | 功能 | 权限 |
| --- | --- | --- |
| `.hud help` | 详细帮助 | 所有人 |
| `.hud on` | 保存个人开启设置 | 所有人 |
| `.hud off` | 保存个人关闭设置 | 所有人 |
| `.hud` | 将当前有效状态取反，保存为个人设置 | 所有人 |
| `.hud show` | 查看有效状态、设置来源和全局默认 | 所有人 |
| `.hud global on/off` | 设置群链共享的全局默认 | 当前 bot 的 Core 骰主 |

前缀支持 `.`、`。`、`/`；命令忽略大小写，并按轻量模板方式支持 `.hudon`、`.hudglobaloff` 连写。

## 状态与显示

- 首次全局默认关闭。没有个人设置的用户跟随全局；个人 on/off 始终优先。已有保存的全局设置保留；需要关闭原有全局默认时由骰主执行 `.hud global off`。
- 全局默认和个人设置都通过 Core 的 `getRedirectedBotHash` 跟随 link。权限检查仍使用当前实际 bot 的 Core 骰主列表。
- 检测实际的 `roll()` 调用，因此纯计算及骰点错误回复同样适用；没有调用 roll 的指令保留原回复。
- 代投读取 Core 已解析的实际目标，不根据任意 at 猜测。权限不足的代投提示不加；普通 `.r` 中的 at 不会被当成代投。
- 暗骰群内提示保持原样；发起人收到的私聊结果和每位旁观者收到的结果均添加同一目标的 HUD。发送目标保持 Core 原行为。
- 同一消息中，同一用户的 HUD 在每个接收位置只添加一次；多次 roll、递归 roll 或分页不会重复。
- 团队结果显示各位开启 HUD 且有有效 sn 的成员，每人一条 `『sn』`，条目之间一个换行；最后一条后两个换行再接结果。若一个插件逐个发送不同成员的结果，各用户在自己的第一条结果前显示一次。
- sn 按当前群绑定的人物卡读取，优先使用群名片、全局名片、人物卡模板 snTitle、default 模板 snTitle。即使没有手动执行过 .sn，只要模板能生成有效内容，也会显示。
- 私聊使用全局选中的人物卡及全局名片。sn 中的换行折为空格；没有当前人物卡或没有有效 sn 时保留原回复。
- sn 的属性取发送时的内存快照；读取 HUD 不执行 .sn、不更新群名片、不补写人物卡默认属性。
- **Markdown 优先**：qqGuildV2 的 QQ 群 / C2C 且适配层提供 `create_markdown_message` 时，插件直接发送一条 Markdown 消息，状态栏用 `> ` 块引用压成附注样式，HUD 与结果之间空一行，并去掉首尾 `『』`。Markdown 发送失败、接口不可用或消息结构不受支持时，整条消息回退到上面的 `『』` 文本方案，不保留引用样式和空行处理。

## 数据目录

以下 botHash 指 link 解析后的共享 botHash；userHash 使用 Core 的 `getUserHash(user_id, 'user', platform)`。

```text
plugin/data/StatusHud/
└── {botHash}/
    ├── .lock
    ├── config.json
    └── user/
        └── {userHash}.json
```

`config.json` 默认内容：

```json
{"global_enabled": false}
```

个人文件仅在手动设置时创建：

```json
{"enabled": false}
```

全部 JSON 读取、创建、修改、临时文件写入及替换由 bot 级线程锁和操作系统文件锁保护。锁文件固定不替换；JSON 用同目录临时文件、fsync 和原子替换保存。损坏的配置不会自动覆盖，HUD 读取失败时继续发送原结果并记录不含消息内容的错误日志。

## 接入边界

本插件通过可恢复的运行时包装接入，不修改 Core 或 OlivOS 源文件。覆盖 Core 回复、其他插件使用 `plugin_event.reply/send` 的回复，以及 Core QQGuildV2 Markdown 通路。

携带原 Event 的工作线程也可关联骰点与发送。已对本地 OlivaDiceShouHun（sh）、OlivaDiceSanchi（tq）、OlivaDiceMS（ms）、Core（ra）、OlivaDiceTA（ta）的真实处理链做回归验证，覆盖普通结果、代投和已实现的暗骰。sh/tq 暗骰群内提示保持原样。

这些已核对的插件从实际处理变量确认目标，优先于可能使用发起人上下文的骰点记录接口。其他第三方代投若调用 Core 的 `parse_at_user` 或 `saveRDDataUser`，使用接口确认的目标。自行实现代投且不提供目标信息的第三方，无法从 OneDice 对象中取得其目标；此时按事件发起人处理。直接调用协议 SDK、其他独立 OneDice 副本、未携带原 Event 的后台任务不属于这些接入通路。

Core 的代投和暗骰识别使用已核对的处理变量；升级 Core 后若其内部处理结构改变，需要重新核验。卸载恢复仍由本插件直接持有的包装；其他插件后来包装了同一个函数时，保留其包装，并使旧 StatusHud 包装停用。

Markdown 通路单独实现于 `markdown.py`，判定与 OlivOS 图文自动转 Markdown 一致：

- 仅 `qqGuildv2_link` 的 `qq_group` / `qq_private`；频道消息不加 Markdown，沿用原格式。
- 文本使用 `indeAPI.create_markdown_message`；被动回复交由适配层按事件解析 `msg_id`/`event_id`，主动发送（`Event.send`）使用 `force_active`。
- 状态栏样式用 Markdown 的块引用（`> sn`）。QQ 官方文档给出的「支持格式」只有标题、粗体/下划线粗体/斜体/删除线、链接、图片、有序与无序列表、列表嵌套、块引用、分割线，**没有颜色也没有字号**；HTML 的 `<font>` 属于频道渲染器的能力，群聊 / 单聊会连同标签原样输出。块引用在桌面端与手机端一致生效，视觉上把状态栏压到「附注」级别。卡片内容只把尖括号转义成 `&lt;`/`&gt;`，`&` 保持原样（手机端不解析实体，转义后反而会显示成 `&amp;`）。
- HUD 与正文之间用空行（`\n\n`）分隔。QQ 的 Markdown 里单个 `\n` 不产生换行，块引用后若只留单换行，正文会被懒续行并进引用块、整段跟着变成引用样式。
- 图片等媒体仅在适配层同时支持 `local_images` 与 `allow_markdown`（即具备图文自动转 Markdown）时才转 Markdown；旧版 OlivOS 没有该能力时图文保持普通消息。`local_images` 每项传资源字符串（`path`/`url`/`file` 依次取第一个非空值），由适配层上传素材并把 `{{hud_image_N}}` 替换成 `![... #宽px #高px](url)`；传消息段对象会被 `str()` 成字典字面量、按本地文件读取而必然失败。
- 素材上传失败时 OlivOS 会自行退回普通图文（结果里带 `markdown_fallback`），此时消息已发出，本插件只在日志留下原因、不再补发；带引用的图文按适配层口径不转 Markdown。
- 接管 Core 的 `_replyMsgMarkdownQQGuildv2`：先按新格式发送；失败时调用 `pluginReply`，由 `Event.reply` 注入 `『』` 文本 HUD，避免重复发送。
- Markdown 构造失败（引用回复、表情等不支持的段）不视为发送失败，直接沿用原 Markdown 文本格式或普通文本注入。

## 验证

测试目录为插件内的 `StatusHud_tests/`，不打入 OPK。以下命令在 `StatusHud/` 源码目录执行。`--confcutdir` 避免 pytest 在离线替身装载前导入插件包和真实宿主。使用真实 Core/OneDice 与 OlivOS 消息解析源码，宿主和远端发送使用离线替身。

```powershell
python -B -m pytest StatusHud_tests --confcutdir=StatusHud_tests -q -p no:cacheprovider --core-source "<OlivaDiceCore 仓库目录>" --olivos-source "<OlivOS 仓库目录>"
python -B -m ruff check . --select E,W,F,I,B,C4,UP --config 'lint.pycodestyle.max-line-length=120'
```

测试覆盖命令、群链、个人优先级、权限、代投、暗骰与旁观者、私聊、多人结果、分页、第三方发送、并发、重载、损坏数据和 OPK 解包目录清理后的首次使用；另覆盖 Markdown 成功、发送失败回退、旧版无接口与图文兼容。manifest 为 UTF-8 无 BOM。
