# OlivaAIAgent v2 — AI 全能群聊插件（OlivOS / 青果）

一个插件，两种形态，且都比市面同类更强：

- **全接口 Agent 模式**（`.ai` / @机器人触发）：不再内置任何手写 OlivOS 原生接口工具；启动时自动内省 `Event`、`Proc`、全部 adapter SDK 及其 `indeAPI` 并写入内存目录。所有原生操作统一按真实签名发现和调用。另可**执行 OlivaDice 官方指令**（`.r/.ra/.sc/.st/.coc/.draw/.init/.jrrp/.log` 等，事件重注入真实走骰系，不伪造）并使用联网、记忆和定时提醒。
- **潜行群友模式**（按群开启，`.ai stealth on`）：完整复刻并增强"群聊刺客"——伪装成群友、读全部群消息、**自行择机插话**，带节律控制、前置判定、知识库、技能库、用户侧写、视觉识图、表情包、前缀缓存优化。而且潜行 AI 还能被 @/前缀随时切到全权限 Agent，甚至潜行本身可选开工具（骰点/查询）。

> 相比"群聊刺客"：刺客有的（下列全部）本插件都有且更强，此外还独有全接口调用、真实骰点执行、Anthropic 后端、三级权限管控、`.ai` 指令体系；技能库在缺少 `rank_bm25/jieba` 时自动降级为纯 Python 而非报错，无需任何 pip 依赖即可运行。

## 潜行模式 = 刺客全功能 + 增强

| 刺客功能 | 本插件 | 增强点 |
|---|---|---|
| 择机插话（读全部消息自行决定） | ✅ | 同 |
| SlackableFairLock 礼貌节律（连发只回最后一条） | ✅ | 同 |
| DynamicQueue 前缀缓存历史 | ✅ | 同 |
| first_thinking 便宜模型前置判定 | ✅ | 同（intent_api 可独立配置） |
| DeepSeek 思考模式（thinking + reasoning_effort） | ✅ | 三后端通用 |
| 静态知识库 + 动态知识自动记录 + 模糊检索 | ✅ | LCS+编辑距离，LRU 淘汰 |
| 用户侧写（心理画像，跨群） | ✅ | 同 |
| 群前情提要（滚动总结） | ✅ | 同 |
| 后台记忆提炼线程 | ✅ | 同 |
| Codex 技能库（SKILL.md，BM25 检索） | ✅ | **BM25 缺失自动降级纯 Python** |
| 视觉识图（OCR→摘要，图片缓存） | ✅ | 可复用主后端或独立视觉模型 |
| 表情包主动发送（[发图片:] 模糊解析） | ✅ | 同 |
| 视觉否认纠偏 | ✅ | 同 |
| 概率/关键词/@触发、忽略前缀 | ✅ | 同 |
| 多条消息 + 拟人打字节奏 | ✅ | 同 |
| reply_wash 去括号动作 | ✅ | 同 |
| 每群历史持久化、热重载、缓存命中日志 | ✅ | 同 |
| —（刺客无） | ✅ 潜行也能调工具/骰点 | **独有** |

## 统一管线 + 缓存优化（v2.5）

**触发之后两边不再分开，永远合一。** 群里一旦触发——`.ai` 前缀、@机器人、命中关键词、还是潜行自行插话——都走**同一条请求**，这条请求同时带上潜行的人设/群历史/知识/技能/视觉/记忆 与 全权限 Agent 的全部工具与骰点。不再"要么潜行要么 Agent"。
- 潜行**开启**的群：`.ai`/@/关键词 → 强制回复 + 全部工具；普通闲聊按概率自行插话；同时记录群滚动历史作上下文。
- 潜行**关闭**的群 = 纯助手模式（v2.6）：**只有 `.ai` / 前缀触发**，@、关键词、概率一律不触发，也不再静默采集群消息。关掉潜行 = 安静的助手，只有你显式 `.ai` 叫它才应答。
- 私聊同样合一：套用同一人设 + 全部工具。

**固定内容前置，缓存命中更高。** 提示词按"稳定→易变"排布：人设、规则、平台说明、已加载插件、骰系速查、固定记忆等**稳定内容放在最前面作为前缀**；时间、检索到的知识/侧写/前情提要、图片缓存、当前消息等**易变内容放到历史之后的尾部**。配合前缀缓存历史队列（DynamicQueue，增长到上限再批量换代），连续请求的公共前缀最大化，DeepSeek/OpenAI 前缀缓存命中率显著提升、省 token。（`.ai status` 里开 `debug_log` 可看到 CACHE 命中率日志。）

## OlivOS 接口 / SDK 全自动内省（v2.11）

插件已经删除 `send_msg`、`delete_msg`、`get_group_info`、`set_group_ban`、`list_plugins`、群文件等全部手写 OlivOS 原生包装。模型执行任何 OlivOS 操作时，都先调用 `olivos_discover` 查询启动阶段写入内存的目录，再把目录返回的精确路径交给 `olivos_call`：

- `event.*`：当前 `plugin_event` 的公开接口；
- `proc.*`：当前插件进程的公开接口，例如 `proc.get_plugin_list`；
- `inde.*`：当前协议的独立接口，优先级最高；
- `sdk.<模块>.*`：所有已加载 adapter SDK 中由该 SDK 自己定义的公开函数，以及无需实例化即可调用的类方法。

SDK、Event、Proc 和所有已加载 SDK 的 `indeAPI` 元数据在 `init_after` 一次性扫描并常驻内存；初始化之后才出现的未知 `indeAPI` 类型会在首次使用时补入。目录不保存旧事件对象，每次执行仍绑定当前消息事件。目录包含真实签名、docstring、所属模块、当前适配器标识和自动注入参数；`target_event`、`plugin_event`、`Proc` 会自动注入。私有成员、导入进 SDK 的外部 callable、以及必须先构造并保存实例的有状态方法不会进入目录。

以本地 `qqGuildv2` 为例，搜 `markdown` 会自动命中：

```text
inde.create_markdown_message(chat_type, chat_id, markdown, ...)
sdk.qqGuildv2SDK.event_action.create_markdown_message(target_event, chat_type, chat_id, markdown, ...)
```

因此以后 OlivOS 新增公开 SDK 方法，插件重载后就能直接发现，不需要再修改 `tools.py`。`olivos_call` 是唯一的 OlivOS 原生调用入口，**所有调用**统一受 `.ai admin` 三级高危权限控制；目录查询本身不执行操作。

## 能调用整个插件生态（不止骰核，v2.4）

AI 可以自由使用 OlivOS 上**已加载的所有插件**的功能，不局限于 OlivaDiceCore：

- **`run_command` 分发给全部已加载插件**（按优先级，谁能处理谁响应），因为这些规则/功能插件都用标准的 `group_message` 事件入口。已实测覆盖：OlivaDiceCore（`.r/.ra/.sc/.st/.coc`）、**OlivaDiceLogger**（`.log` 跑团日志）、**OlivaDiceJoy**（`.jrrp`）、**OlivaDiceMaster**、**OlivaDiceOdyssey**、**OlivaStoryCore**（`.story`），以及第三方规则插件如 **OlivaDiceShouHun（守婚）**、**OlivaDiceSanchi（三尺）**、FuRule 等——只要它挂载了消息事件，`run_command` 就能触达。
- **撤回 / 禁言 / 发公告 / 发群文件 / 设精华 / 表情回应 / 群管理…** 全部从内存目录查找 `event.*`、`inde.*` 或 `sdk.*` 的真实接口，不存在对应的固定 AI 工具名。
- **AI 知道有哪些插件**：系统提示里注入当前已加载插件清单；需要主动查询时，通过 `proc.get_plugin_list` 获取。不确定指令语法时，用 `run_command` 执行 `.help` 或 `.help 指令名`。

一句话：**能自由读取并调用 OlivOS 里装载的所有插件功能**——骰系全家桶、第三方规则插件、以及 QQ 侧的撤回/禁言/公告/文件等原生能力，都在射程内。高危动作仍受三级角色门槛与骰系自身权限双重约束。

## 权限、平台、去重、热重载（v2.2）

**权限管理**：两套独立且都正确。
- **OlivaDice 官方指令**（经 `run_command`）：由**骰系自己**判权——`run_command` 把发起人身份（user_id / platform / `sender.role`）原样重注入，OlivaDice 重新计算 `flag_is_from_master`（masterList）和 `flag_is_from_group_admin`（owner/admin/sub_admin）。所以需要骰主权限的只有骰主能用，需要群管/群主的只有群管/群主/骰主能用，普通人无法通过 AI 越权，也无法伪造身份。
- **OlivOS 原生接口调用**：唯一入口 `olivos_call` 始终走三级角色门槛 `.ai admin role everyone/group_admin/master`，并叠加全局开关和每群开关；`olivos_discover` 只读目录，不受此限。`run_command` 仍由骰系自己判权。（旧配置 `master_only:true` 会自动迁移。）

**平台/SDK 感知**：AI 的系统提示里会注入当前 `平台 / SDK / 模型` 和平台特性说明。OlivOS 会按事件平台**自动把发送路由到对应适配器**（AI 不用关心底层 SDK），但 AI 被告知了自己在哪个平台，从而不会在不支持的平台用其专属格式（比如别在 Telegram 用 QQ 的 CQ 码）。

**潜行 vs AI 模式：整合而非二选一**（v2.3）。潜行开启的群里，当消息**被@或命中关键词**（统一的 `trigger.keywords`）时，会触发"整合请求"——**一次** AI 调用同时带上潜行的人设/群上下文/知识/技能/视觉，又启用全权限 Agent 的**全部工具与骰点**，并强制回复（跳过概率/前置判定），产出一条回复。既不会两个模式各回一条，也不用二选一，两边能力合到一起用。开关：`ambient.integrate_hard_trigger`（默认开）。普通闲聊（无@无关键词）仍走轻量潜行判定。

**统一触发关键词**：只有一项 `trigger.keywords`，潜行开/关都用它触发，命中即强制回复，配一处两边通用。每条消息仍按（bot|群|消息id）去重，重复投递只处理一次。

**热重载**：`config.json`、`groups.json`、群记忆（`ambient_memory_*.json`）、静态知识库、Agent 长期记忆，只要文件被外部修改，下一条消息进来时会按 mtime 自动载入内存（最多每 2 秒检查一次），无需重启或手动 `.ai reload`。

## 记忆互通（两种模式共享）

全权限 Agent 与潜行模式的长期记忆**双向打通**，共用一套知识：

- 潜行模式自动积累的 **知识点 / 用户侧写 / 群前情提要**，Agent 会自动注入到系统提示，也能用工具主动查：`kb_search`（查知识库）、`kb_user_note`（查某人侧写）、`kb_group_brief`（查群前情提要）、`kb_save`（写入共享知识库）。
- Agent 里 `.ai mem` / `memory_save` 记的 **用户跨群长期记忆 / 本群共享记忆**，潜行 AI 也会读到并纳入上下文。

实现上各自的写入仍落在原生存储（Agent → `sessions/`+`memory/`，潜行 → `ambient_memory_*.json`），但两边读取时都读取合集——所以数据不会互相覆盖、结构不冲突，却能彼此看见。

## 定时提醒 / 定时主动消息（v2.7）

让 AI 真正“到点主动来找你”，而不是被动回复。对某人说「三小时后提醒我喝水」「12:52 给我发开会」，AI 会调用 `schedule_reminder` 工具**真的创建一个定时任务**；到了那个时间点，把你当时要提醒的内容交给 AI 生成一句自然的话，然后**主动推送**给你（群里会顺带 @ 你）。

- **主动推送，不是被动回复**：官机（QQ 频道 v2 / qqGuildv2）的被动回复有 5 分钟 / 5 次限制，几小时后的提醒用被动回复必然超时失败。本功能发送前会清掉事件里的被动回复 token（`reply_msg_id`），让 OlivOS 走**主动发送**（OlivOS 的 qqGuildv2 适配器自带被动/主动回退），所以隔多久都能发出来。
- **相对 / 绝对时间都支持**：`delay_seconds`（“3小时后”=10800）或 `at_time`（`12:52` / `09:00:00` / `2026-07-27 09:00` / `07-27 09:00`）。`HH:MM` 若已过则自动顺延到明天。
- **持久化 + 重启恢复**：任务写入 `reminders.json`，插件重载 / OlivOS 重启后自动重新挂起未到期任务，不丢。重启后该 bot 收到任一消息即恢复推送能力；到点时若暂时没有可用发送器会自动重试。
- **配额与管理**：每人每 bot 默认最多 20 个待触发提醒、全局 500 个、最远 30 天；AI 可用 `list_reminders` 查、`cancel_reminder`（按编号，仅能取消自己的）取消。
- 触发的提醒只发到**设定时所在的会话**（群或私聊），不能指定其它目标，避免滥用。

配置见 `config.json` 的 `reminder` 段（`enable` / `max_per_user` / `max_total` / `max_horizon_days` 等）。

## 官机图片识别健壮性（v2.7）

修复官机（QQ 群 / 频道）下图片识别的两类失败：

- **文件名非法导致存盘崩溃**：官机图片 URL 形如 `.../download?appid=1407&fileid=...&rkey=...&spec=0`，直接拿来当文件名会因含 `?&=` 且超长而 `SAVE ERR: No such file or directory`。现已彻底清洗文件名（去查询串、非法字符替换为 `_`、限长、按 content-type 补扩展名）。
- **存盘失败连累识别 / 回退发原始 URL 致 400**：过去下载成功但存盘失败就整体失败，并回退把官机原始 URL 直接发给识图模型 → `400 unsupported image url`（第三方模型取不到 QQ 的签名 URL）。现在**下载与存盘解耦**：只要下到图就一定产出 base64（存盘仅为“发表情包”复用，失败不影响识别）；且对官机 / 签名 URL（`multimedia.nt.qq` / `rkey=` / `gchat.qpic` 等）强制先下成 base64 再识别，下载失败时**绝不回退发原始 URL**（宁可占位也不 400）。content-type 缺失时用图片魔数兜底判定。

## 多bot / 群链主账号 / 私聊骰主限定（v2.9）

- **群链（主账号数据共享）**：像 OlivaDiceCore 一样读取骰系的主从账号关系——**从账号连接后，把本插件的数据（知识/用户侧写/群前情提要等记忆）自动写入 / 读取主账号**，让链接的多个 bot 共享同一份记忆。用的正是骰系的 `getRedirectedBotHash` 重定向（黑名单项如群开关仍按各 bot 独立），与骰系数据归属一致。无链的独立 bot 数据各自隔离。开关 `groupchain.enable`（默认开）。
- **多bot**：数据本就按 bot 隔离（知识按 bot、记忆按平台+用户/群），配合群链即可让"同一主账号下的多 bot"共享、不同主账号相互独立。`.ai status` 会显示本 bot 是否已并入某主账号。
- **骰主判定跨链**：主账号上登记的骰主，在其从账号上也被认作骰主（`isMaster`/`getMasters` 沿主从链取并集）。
- **私聊 / 单聊（默认仅骰主）**：
  - `trigger.private_chat`（默认 `true`）——私聊**总开关**：`false` 则私聊完全不可用（含 `.ai` 指令）。
  - `trigger.private_master_only`（默认 `true`）——`true` 时私聊**只有骰主能用**（非骰主直接忽略、不回复不泄露）；`false` 则所有人可私聊（仍受总开关约束）。
  - 私聊与群聊**记忆共享**：用户长期记忆按"平台+用户"存储（与群/私聊场景无关），加上群链的知识/侧写共享，骰主在私聊里聊的与群里是同一份长期记忆。

## 视觉自动路由 + 统一触发关键词（v2.8）

- **视觉自动路由**：`vision.use_main` 默认改为 `"auto"`——**主后端支持视觉（其 `vision:true`，如 GPT-4o/Claude）就直接用主模型识图，主模型是纯文本（如 DeepSeek）就自动改用下面单独配的 OCR 视觉模型**。不用再手动判断，也可显式写 `true`/`false` 强制。
- **统一触发关键词**：只有一项 `trigger.keywords`——潜行开 / 关都用它触发（命中即强制回复），关键词配一处两边通用（不再有 `wake_words`/`reply_keywords` 分开两处）。

## 图片当轮识别 + 全过程 Logger（v2.12）

- 群聊在 `vision.sync_ocr:false` 时，会把整条图片消息交给独立后台线程：先下载、识图并生成事实摘要，再继续本轮 AI 回复。这样不阻塞 OlivOS 消息总线，同时不会再让本轮回复只拿到“未识别成功”的占位；`true` 才会直接在消息总线线程识图。
- 私聊与 `.ai` 附图也走同一视觉子系统。主后端是纯文本模型时，图片会先由独立视觉模型转成 `[图片：内容；意图；类型]`，然后把摘要而不是原始图片 URL 交给主模型。
- `debug_log:true` 时，OlivOS Logger 会输出带同一 `id` 的 `TRACE`：消息接收/路由、图片下载、视觉路由、OCR 请求与结果、模型请求、工具调用、发送和会话保存均可串联查看。API Key、token、Authorization、Base64/data URL 会自动遮蔽，长字段会截断。
- 启动后会打印一条不含密钥的视觉状态，例如 `视觉配置: enabled=True ready=True route=independent model=kimi-k2.6 mode=base64`。识图失败时可按同一个 `id` 查 `vision.download.failed`、`vision.ocr.http_error`、`vision.ocr.invalid_result` 或 `vision.ocr.exception`。

## 支持 OpenAI Responses API（v2.7.1）

除 `chat/completions`（openai wire）与 `messages`（anthropic wire）外，新增 **`responses` wire**，对接 OpenAI 的 `/v1/responses` 接口（GPT-5 / o 系列等新模型偏好的统一接口）。

- **零配置识别**：把 `api_url` 指向 `.../responses`（如 `https://api.openai.com/v1/responses`）即自动走 Responses 报文；也可在后端段显式写 `"wire": "responses"` 强制。
- **完整对接**：内部消息自动转 `input` 数组（system→`instructions`、图片→`input_image`、工具调用→`function_call`、工具结果→`function_call_output`）；工具用扁平结构；`max_output_tokens`；思考模型走 `reasoning.effort`；流式解析 `response.output_text.delta` / `response.function_call_arguments.delta`，并以 `response.completed` 的完整 output 为权威；流中途 `response.failed` 不冒充成功。
- 全接口工具循环、骰点、视觉识图在 responses wire 下与原有 wire 完全一致。

## 稳健性与安全修复（v2.6.3）

一轮多 agent 代码审查（9 维度并行审 + 逐条对抗验证）后修复的确认问题：

- **显式请求必回**：`.ai`/@/关键词（force）不再被节律锁的"让位"机制在忙群里静默丢弃。
- **消息总线不卡**：视觉 OCR/下载默认移出消息派发线程（未命中的图后台识别），慢图不再阻塞全 bot 的骰点等功能（`vision.sync_ocr` 可切回同步）。
- **并发安全**：视觉图片缓存（dict/deque）跨线程读写全部加锁并快照迭代，消除 `RuntimeError` 掉回复；知识/侧写/群总结写入统一持锁。
- **数据不损坏**：所有持久化（配置/群开关/会话/记忆/潜行历史/图片缓存）改为原子写（临时文件 + `os.replace`），进程中途被杀或并发写不再截断损坏文件。
- **配置不丢**：`config.json` 解析失败时**不再用默认配置覆写**用户文件（API Key 等保住），改为备份为 `.bad` 并用默认值在内存里跑；读取兼容 BOM。
- **权限**：`send_forward_msg` 补齐跨目标三级门槛（不能再绕过管控跨群发消息）；`hotReload` 补上 `_migrate`，旧式 `master_only` 配置热载后不再被降权为所有人可用。
- **模型调用**：`thinking` 参数仅在 enabled 时下发（严格官方 OpenAI 端不再因未知参数 400）；流式响应中途的 error 事件不再冒充成功；SSE 强制 UTF-8 解码（修中文乱码）。
- **会话不中毒**：私聊会话不再持久化图片 CDN URL（过期后逐轮重放会让整会话每次 400）。
- **其它**：`.ai clear group` 一并清群统一管线上下文；非法 `context_buffer`/记忆上限做夹取防御（不再 `IndexError` 或清空）；技能检索缓存加上限（防长跑内存泄漏）；`extra_dirs` 误配字符串不再按字符展开建垃圾目录；移除失联的"自由唤醒"死代码（其职能已并入潜行统一管线）。

回归测试 9 套共 **259 项全绿**，打包后 OPK 亦通过端到端加载验证。

## 安装

1. 将 `OlivaAIAgent.opk` 放入 OlivOS 的 `plugin/app/`（或整个文件夹放入）
2. 启动一次，自动生成 `plugin/data/OlivaAIAgent/config.json`
3. 填 `openai.api_key`（默认后端 openai 兼容，示例指向 DeepSeek），`.ai reload`
4. `.ai 你好` 测试全接口模式；`.ai stealth on` 在某群开启潜行模式

### 依赖（核心零额外依赖）

- **核心运行：无需安装任何非 OlivOS 自带的库。** 所有网络请求走 `requests`（OlivOS 已内置），其余仅用 Python 标准库。**不需要 `openai` / `anthropic` 库**——三种后端全是 `requests` 直连；`openai` 只是官方 SDK，本插件不用它也能调 OpenAI 兼容接口。
- **可选增强（不装自动降级，绝不报错）**：
  - `jieba` + `rank_bm25`：技能库（SKILL.md）检索升级为中文分词 + BM25 精排；不装则退回纯 Python 词频/子串匹配。
  - `PyYAML`：解析 SKILL.md 的 YAML frontmatter；不装则用内置极简解析器 `_mini_yaml`。
  - `translators`：①把**外文（不含中文）提问**自动翻成中文，帮外语群友命中中文技能库；②免费翻译**纯外文技能**的元数据（见下节）；③把中文提问顺带翻成英文去匹配英文正文。不装则各项自动跳过或改走 AI 后端。
  - 一次装齐（可选）：`pip install jieba rank_bm25 pyyaml translators`。装或不装都能跑，`.ai status` 的技能引擎会显示 `BM25`/`lite`（`+译` = translators 可用；`+译(AI后端)` = 用你配置的模型翻外文技能元数据）。

#### 英文技能库（SKILL.md 是英文）要不要翻译 / openai？

**都不用。** 两点原因：

1. **模型直读英文**：命中的英文 SKILL.md 片段是作为上下文注入给模型的，DeepSeek/GPT/Claude/Qwen 都能直接读英文规则、用中文回答，不需要任何翻译库或 `openai` SDK。
2. **检索靠 frontmatter 关键词**：中文提问要命中英文技能，靠的是该技能 frontmatter 里的中文 `keywords/triggers/aliases`（可中英混写），本插件对声明关键词有额外加权。英文提问则纯词法即可命中英文正文。

`translators` 只补一个**反向**冷门场景：群友用**英文提问**、而技能库是**中文**时，把英文提问翻成中文再匹配。中文提问永远不翻译。所以：英文技能 + 中文群友 = 开箱即用，零额外依赖；只有"英文群友 + 中文技能"才需要装 `translators`（装了自动生效，不装自动跳过）。

#### 纯外文技能（frontmatter 连中文关键词都没有）也自动桥接（v2.6.2）

第三方英文/外文 SKILL.md 直接丢进 `skills/` 即可，**不需要手动加中文关键词**。索引构建时自动检测"元数据完全无中文"的技能，把 技能名/描述/keywords/全部章节标题 翻成中文并入检索词表（后台线程执行，不阻塞消息）；结果按内容哈希**永久缓存**到 `skills_translation_cache.json`，跨重启零成本、内容没变就永不重翻。翻译渠道按序：

1. 装了 `translators` → 用它（免费、无 token 消耗）；
2. 没装但配置了 API Key → 用你的 AI 后端一次性翻（每个技能一个小请求，缓存后不再花钱；开关 `skills.translate_meta_use_llm`）；
3. 都没有 → 仍可手动 frontmatter 中文关键词；且只要检索判定该技能相关，即使正文与提问词法零重叠，也会**保底注入该技能开头片段**，绝不空手而归。

另外装了 `translators` 时，中文提问还会自动翻成英文一并检索（`skills.translate_query_to_foreign`，默认开），直接命中英文正文段落。命中的英文片段照旧原文注入——模型直读英文、中文作答。

> 对比"刺客"：它把 `translators`、`openai` 写死为硬依赖（`import` 在模块顶层，缺库直接崩），且**没有**外文技能元数据翻译——纯英文技能在刺客里只能靠英文提问命中。本插件全部可选 + 优雅降级 + 三层桥接，中文提问零开销。

## 关键配置（config.json 分段）

```jsonc
{
  "backend": "openai",              // openai / anthropic / custom
  "openai": {
    "api_url": "https://api.deepseek.com/v1/chat/completions",
    "api_key": "sk-xxx", "model": "deepseek-v4-flash",  // 或 deepseek-v4-pro；旧名 deepseek-chat/reasoner 已弃用
    "thinking": {"type": "disabled"},   // 改 {"type":"enabled"} 开思考(= 旧 reasoner)
    "reasoning_effort": "high"          // high / max
  },
  "anthropic": { "api_url": "...", "api_key": "", "model": "claude-sonnet-4-20250514" },

  "trigger": { "keywords": ["骰娘"] },   // ← 统一触发关键词(潜行开/关都用它，配一处即可)

  "ambient": {                       // ← 潜行模式（刺客同款+增强）
    "personality": "冷静温和的群友人设…",
    "reply_probability": 1.0,        // 随机插话概率(建议连同 first_thinking 一起调)
    "history_size": 8,
    "prompt_cache_optimized": true,  // DeepSeek 前缀缓存优化
    "prompt_cache_history_size": 32,
    "slack_time": 5, "slack_cooldown_time": 30,   // 节律：连发只回最后一条
    "first_thinking": false,         // 便宜模型前置判定 NEXT/SKIP
    "intent_api": { "enable": false, "api_url": "...", "api_key": "", "model": "Qwen/Qwen2.5-7B-Instruct" },
    "record_knowledge": true,        // 自动记知识点
    "allow_tools": false             // ← 独有：潜行也能骰点/查询
  },
  "vision": {                        // 视觉识图（把图转文字摘要）
    "enable": false, "use_main": "auto",   // auto=主模型支持视觉就用主模型，否则用下面独立 OCR 模型
    "api_url": "https://api.siliconflow.cn/v1/chat/completions",
    "api_key": "", "model": "Pro/moonshotai/Kimi-K2-Instruct", "mode": "base64"
  },
  "skills": { "enable": true, "max_matches": 2 },   // SKILL.md 放 data/OlivaAIAgent/skills/
  "knowledge": { "cache_max": 0 }                   // 静态知识放 data/OlivaAIAgent/Knowledge/*.json
}
```

## 指令

| 指令 | 说明 | 权限 |
|---|---|---|
| `.ai <内容>` | 与全接口 AI 对话（可骰点+全接口） | 所有人 |
| `.ai clear` / `.ai mem` / `.ai status` | 清对话 / 看记忆 / 看状态 | 所有人 |
| `.ai on/off`、`.ai global on/off` | 本群/全局开关 | 骰主 |
| `.ai stealth on/off` | 本群潜行（群友融入）模式；**off = 纯助手，仅 `.ai` 触发**，@/关键词/概率均不触发 | 骰主 |
| `.ai stealth think on/off` | 潜行前置判定开关 | 骰主 |
| `.ai stealth tools on/off` | 潜行是否可调工具/骰点 | 骰主 |
| `.ai admin [global/masteronly] on/off` | 高危接口全局开关 / 旧式仅骰主开关（推荐用 `.ai admin role master`） | 骰主 |
| `.ai wl on/off/add/del/list` | 白名单 | 骰主 |
| `.ai skills reload` / `.ai kb reload` | 重建技能索引 / 重载知识库 | 骰主 |
| `.ai model <名>` / `.ai reload` | 切模型 / 重载配置 | 骰主 |

## 数据目录 `plugin/data/OlivaAIAgent/`

- `config.json` / `groups.json` — 配置与每群开关
- `Knowledge/*.json` — 手动维护的静态知识库 `{关键词: 内容}`
- `skills/<名>/SKILL.md` — Codex 技能/规则书（支持 frontmatter 的 name/description/aliases/keywords/triggers + references/ 资料）
- `Image/` — 视觉缓存图片；`ambient_history/` — 每群潜行历史；`ambient_memory_*.json` — 知识/侧写/总结/图片缓存；`sessions/` `memory/` — 全接口模式对话与长期记忆

## 说明

- `app.json` UTF-8 无 BOM；优先级 30000，运行于 OlivaDiceCore(20000) 之后
- 所有 AI 调用在后台线程，不阻塞消息总线；潜行模式用节律锁，连发消息只回最后一条
- 潜行的高危接口调用同样受三级权限管控；`run_command` 以发起用户身份重注入，不越权
- 与其他 AI 插件（如刺客/ChatGPT）同装时请错开触发词与潜行群，避免双回复
