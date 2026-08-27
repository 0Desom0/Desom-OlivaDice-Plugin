# OlivaAIAgent v2.23.0 — AI 全能群聊插件（OlivOS / 青果）

一个插件，两种形态，且都比市面同类更强：

- **全接口 Agent 模式**（群前缀 / 群关键词触发；潜行开启后也可由 @ 或引用触发）：不再内置任何手写 OlivOS 原生接口工具；启动时自动内省 `Event`、`Proc`、全部 adapter SDK 及其 `indeAPI` 并写入内存目录。所有原生操作统一按真实签名发现和调用。另可**执行 OlivaDice 官方指令**（`.r/.ra/.sc/.st/.coc/.draw/.init/.jrrp/.log` 等，事件重注入真实走骰系，不伪造）并使用联网、记忆和定时提醒。
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
| 入站语音/视频理解（转写与摘要） | ✅ | 主模型明确支持时直读，否则自动走独立模型 |
| 表情包主动发送（[发图片:] 模糊解析） | ✅ | 同 |
| 视觉否认纠偏 | ✅ | 同 |
| 概率/关键词/@触发、忽略前缀 | ✅ | 同 |
| 多条消息 + 拟人打字节奏 | ✅ | 同 |
| reply_wash 去括号动作 | ✅ | 同 |
| 每群历史持久化、热重载、缓存命中日志 | ✅ | 同 |
| —（刺客无） | ✅ 潜行也能调工具/骰点 | **独有** |

## 统一管线 + 缓存优化（v2.5）

**触发之后两边不再分开，永远合一。** 群里一旦触发——`.ai` 前缀、@机器人、命中关键词、还是潜行自行插话——都走**同一条请求**，这条请求同时带上潜行的人设/群历史/知识/技能/视觉/记忆 与 全权限 Agent 的全部工具与骰点。不再"要么潜行要么 Agent"。
- 潜行**开启**的群：`.ai`/关键词直接要求主模型回复；@/引用机器人跳过概率并进入小模型判定；普通闲聊按概率自行插话；同时记录群滚动历史作上下文。
- 潜行**关闭**的群只响应本群前缀和关键词；明确 @、引用机器人与普通消息均不触发，也不会为普通消息调用记忆模型。
- 私聊同样合一：套用同一人设 + 全部工具。

**固定内容前置，缓存命中更高。** 提示词按"稳定→易变"排布：人设、规则、平台说明、已加载插件、骰系速查、固定记忆等放在最前面；时间、摘要/记忆、检索结果、消息 ID、图片缓存和当前消息都放到历史之后，避免任一动态字段变化时冲掉已有历史缓存。群历史与普通 Agent 会话都采用“增长到上限再批量换代”，避免满额后每轮滑窗冲掉整段前缀。（开启 `debug_log` 后，模型响应日志会显示输入、输出、总 token 及缓存命中 token。）

**任务交付会自动续行。** 普通 Agent 与潜行群聊都会在终止前检查回复是否只是“稍等、马上发、已经整理好”之类的进度承诺，或虚构结果已放入文件夹但没有真正交付。命中后不发送这条空承诺，而是在同一请求内继续生成或调用工具；`agent.max_auto_continuations` 控制任务承诺续行次数。若模型输出的是内部规划而非最终结果，即使没有 `tool_calls` 也会继续下一轮，并计入 `ambient.agent_max_turns` 或 `agent.max_tool_rounds` 的 Agent 轮次上限。

## OlivOS 接口 / SDK 全自动内省（v2.11）

插件已经删除 `send_msg`、`delete_msg`、`get_group_info`、`set_group_ban`、`list_plugins`、群文件等全部手写 OlivOS 原生包装。模型执行任何 OlivOS 操作时，都先调用 `olivos_discover` 查询启动阶段写入内存的目录，再把目录返回的精确路径交给 `olivos_call`：

- `event.*`：当前 `plugin_event` 的公开接口；
- `proc.*`：当前插件进程的公开接口，例如 `proc.get_plugin_list`；
- `inde.*`：当前协议的独立接口，优先级最高；
- `sdk.<模块>.*`：所有已加载 adapter SDK 中由该 SDK 自己定义的公开函数，以及无需实例化即可调用的类方法。

SDK、Event、Proc 和所有已加载 SDK 的 `indeAPI` 元数据在 `init_after` 一次性扫描并常驻内存；初始化之后才出现的未知 `indeAPI` 类型会在首次使用时补入。目录不保存旧事件对象，每次执行仍绑定当前消息事件。目录包含真实签名、docstring、所属模块、当前适配器标识和自动注入参数；`target_event`、`plugin_event`、`Proc` 会自动注入。私有成员、导入进 SDK 的外部 callable、以及必须先构造并保存实例的有状态方法不会进入目录。

每次请求还会把当前 `plugin_event.indeAPI` 的精简公开接口清单从内存目录自动注入系统提示。模型不能再凭训练知识直接声称“平台不支持”：当前清单已有的接口可直接按精确路径调用，未列出的能力必须先用 `olivos_discover` 查证，只有目录不存在或真实接口返回不支持时才能判定不可用。该清单来自当前协议对象，不是按平台名称写死。

调用签名中出现 `chat_type/chat_id` 时，插件会从当前事件上下文生成真实参数。qqGuildv2 公域连接同时承载 QQ 群/C2C 和频道消息：插件依据事件里的 `flag_from_qq/flag_from_direct` 自动选择 `qq_group`、`qq_private`、`guild_channel` 或 `guild_private`，并注入当前真实目标 ID。模型误填 `guild`、`channel`、`CURRENT_CHANNEL` 等值时，调用器也会纠正为当前事件参数，不再让 SDK 因猜错场景而拒绝。

以本地 `qqGuildv2` 为例，搜 `markdown` 会自动命中：

```text
inde.create_markdown_message(chat_type, chat_id, markdown, ...)
sdk.qqGuildv2SDK.event_action.create_markdown_message(target_event, chat_type, chat_id, markdown, ...)
```

qqGuildv2 中包含 `@` 用户的回复应使用 Markdown 格式发送。模型会优先选择 `inde.create_markdown_message`；如果普通最终回复仍带有 OP/CQ at 段或 `<qqbot-at-user>` 标签，插件会复用 SDK 的 at 转换并自动改走 Markdown，专用接口失败时才退回原普通发送链路。

因此以后 OlivOS 新增公开 SDK 方法，插件重载后就能直接发现，不需要再修改 `tools.py`。`olivos_call` 是唯一的 OlivOS 原生调用入口，**所有调用**统一受 `.ai admin` 三级高危权限控制；目录查询本身不执行操作。

## 能调用整个插件生态（不止骰核，v2.4）

AI 可以自由使用 OlivOS 上**已加载的所有插件**的功能，不局限于 OlivaDiceCore：

- **`run_command` 分发给全部已加载插件**（按优先级，谁能处理谁响应），因为这些规则/功能插件都用标准的 `group_message` 事件入口。已实测覆盖：OlivaDiceCore（`.r/.ra/.sc/.st/.coc`）、**OlivaDiceLogger**（`.log` 跑团日志）、**OlivaDiceJoy**（`.jrrp`）、**OlivaDiceMaster**、**OlivaDiceOdyssey**、**OlivaStoryCore**（`.story`），以及第三方规则插件如 **OlivaDiceShouHun（守婚）**、**OlivaDiceSanchi（三尺）**、FuRule 等——只要它挂载了消息事件，`run_command` 就能触达。
- **撤回 / 禁言 / 发公告 / 发群文件 / 设精华 / 表情回应 / 群管理…** 全部从内存目录查找 `event.*`、`inde.*` 或 `sdk.*` 的真实接口，不存在对应的固定 AI 工具名。
- **AI 知道有哪些插件**：系统提示里注入当前已加载插件清单；需要主动查询时，通过 `proc.get_plugin_list` 获取。不确定指令语法时，用 `run_command` 执行 `.help` 或 `.help 指令名`。

一句话：**能自由读取并调用 OlivOS 里装载的所有插件功能**——骰系全家桶、第三方规则插件、以及 QQ 侧的撤回/禁言/公告/文件等原生能力，都在射程内。高危动作仍受三级角色门槛与骰系自身权限双重约束。

### OlivaDiceLogger 出站记录兼容（v2.20.12）

检测到 `OlivaDiceCore` 时，插件会把自己成功发出的内容送入 Core 与 `replyMsg` 相同的 `crossHook.msgHook`，由 `OlivaDiceLogger` 按当前开团状态写入团日志；不会再次调用 `replyMsg`，所以不会重复发送。普通文本和 Markdown 原样记录，主动图片记录为 `[图片：内容]`（优先使用视觉缓存说明，不写本地路径），语音记录为 `[语音:内容]`（使用合成时已有的文本，不做语音转写）。定时提醒及通过 `olivos_call` 发出的 Markdown 也会记录。

GUI 新增“OlivaDice 团日志”分类，`olivadice_logger.enabled` 默认 `true`；没有 Core 时自动不工作，关闭开关后也只停止补记，不影响消息发送。运行维护页会显示 Core/Logger 检测状态。实际是否落盘仍由 OlivaDiceLogger 的 `.log` 开团状态决定。

`olivadice_logger.record_other_plugin_messages` 默认 `true`，是同一个 `msgHook` 的反向用法：插件会在 Core 的 hook 外再包一层（原 hook 照常先执行，团日志行为不变），把骰系插件经 `replyMsg`/`sendMsgByEvent` 发到群里的消息补进潜行历史与群滚动缓冲，AI 因此知道刚才骰出了什么。这类条目在历史里的发言者为 `骰系插件(机器人名)`，按群内第三方发言注入而非 AI 自己的 assistant 轮次，系统提示已要求不冒充、不复述、不当成待回答的提问。`recv` 事件跳过（本插件事件入口已记录），私聊方向跳过，插件自身补记的消息通过线程标记跳过，不会与 `addSelfReply` 重复。只覆盖走 OlivaDiceCore 发送的插件，直接调用 OlivOS 接口的第三方插件捕获不到；仅在该群潜行开启时记录。

## 权限、平台、去重、热重载（v2.2）

**权限管理**：两套独立且都正确。
- **OlivaDice 官方指令**（经 `run_command`）：由**骰系自己**判权——`run_command` 把发起人身份（user_id / platform / `sender.role`）原样重注入，OlivaDice 重新计算 `flag_is_from_master`（masterList）和 `flag_is_from_group_admin`（owner/admin/sub_admin）。所以需要骰主权限的只有骰主能用，需要群管/群主的只有群管/群主/骰主能用，普通人无法通过 AI 越权，也无法伪造身份。
- **OlivOS 原生接口调用**：唯一入口 `olivos_call` 始终走三级角色门槛 `.ai admin role everyone/group_admin/master`，并叠加全局开关和每群开关；`olivos_discover` 只读目录，不受此限。`run_command` 仍由骰系自己判权。（旧配置 `master_only:true` 会自动迁移。）

**平台/SDK 感知**：AI 的系统提示里会注入当前 `平台 / SDK / 模型` 和平台特性说明。OlivOS 会按事件平台**自动把发送路由到对应适配器**（AI 不用关心底层 SDK），但 AI 被告知了自己在哪个平台，从而不会在不支持的平台使用 QQ 专属消息段。插件对外发送统一使用 OP 码。

**潜行 vs AI 模式：整合而非二选一**（v2.3）。群关键词始终可触发整合请求并直接跳过小模型；只有本群潜行开启后，@机器人和引用机器人回复才会跳过概率、进入前置小模型，`NEXT` 后再调用主模型。普通闲聊也只有潜行开启后才会进入概率门。整合请求同时带上人设、群上下文、知识、技能、视觉和 Agent 工具；开关为 `ambient.integrate_hard_trigger`（默认开）。

**统一触发项**：`trigger.prefix` / `trigger.keywords` 是所有群共用的全局值，不再提供群级覆盖。关键词不受潜行开关影响，命中即强制回复。每条消息仍按（bot|群|消息id）去重，重复投递只处理一次。

**统一群资格与开关**：`groups.json` 是唯一群列表。白名单模式开启时，只有表中存在的平台/群记录可用；关闭时所有群都有资格。获得资格后仍要经过群开关：群开关关闭会禁用该群全部 AI 入口，潜行关闭则只保留该群前缀和关键词。骰主的 `.ai on`、`.ai global on`、`.ai wl ...` 恢复命令例外，但不会调用模型。

**热重载**：`config.json`、`groups.json`、群记忆（`ambient_memory_*.json`）、静态知识库、Agent 长期记忆，只要文件被外部修改，下一条消息进来时会按 mtime 自动载入内存（最多每 2 秒检查一次），无需重启或手动 `.ai reload`。

## 记忆互通（两种模式共享）

全权限 Agent 与潜行模式的长期记忆**双向打通**，共用一套知识：

- 潜行模式自动积累的 **知识点 / 用户侧写 / 群前情提要**，Agent 会自动注入到系统提示，也能用工具主动查：`kb_search`（查知识库）、`kb_user_note`（查某人侧写）、`kb_group_brief`（查群前情提要）、`kb_save`（写入共享知识库）。
- Agent 里 `.ai mem` / `memory_save` 记的 **用户跨群长期记忆 / 本群共享记忆**，潜行 AI 也会读到并纳入上下文。

实现上各自的写入仍落在原生存储（当前用户与 AI 的实际问答 → `sessions/`，手动记忆 → `memory/`，群公共历史/侧写 → `ambient_history/`+`ambient_memory_*.json`）。统一群聊管线在真正发送回复后也会更新该用户的 session；后续定向触发时，仅在相同内容已经滚出当前群历史窗口后补充注入，避免重复占用 Token。

### 群滚动摘要与长期事实记忆（v2.17）

- `.ai memory history on/off`：按群控制滚动摘要，默认开。每新增 `memory.extraction_batch_size` 条已进入 AI 管线的记录才后台更新一次；潜行关闭时普通消息完全静默，不会为其调用摘要/事实模型。
- `.ai memory long on/off`：按群控制长期事实，默认开。事实写入 `semantic_memory.sqlite3`，包含来源消息 ID、引用 ID、事件 ID和时间。
- 长期事实分两种作用域：不带 `user_id` 的写成 `scope=group`，只在本群召回；后台提炼时判定为个人事实（长期偏好、身份、习惯、人物卡归属等）并带上真实 `user_id` 的写成 `scope=user`，**跟着这个人在所有群和私聊召回**，其他人检索不到。群聊里两种作用域一起检索并按分数合并去重；私聊只召回该用户自己的跨群事实。模型编造的 `user_id` 会被本批聊天记录校验掉，注入时该条会带 `scope`/`user_id` 字段告诉模型这是个人事实。
- `semantic_memory.embedding_*`：独立配置 OpenAI-compatible `/embeddings`。配置可用时按 cosine 相似度、关键词和时效混合排序；未配置或接口失败时自动降级关键词检索，并有失败退避，不会每条消息持续请求坏端点。
- `.ai memory status` / `.ai status`：查看两项群开关及当前是“向量就绪”还是“关键词降级”。开关写入 `groups.json`，无需改全局配置。

### 消息 ID 与引用 ID（插件内实现）

- 当前消息 ID、引用消息 ID、事件 ID、`msg_idx/ref_msg_idx`、出站消息 ID 和出站 `ref_idx` 统一写入 `message_registry.sqlite3`，默认保留 7 天。
- QQ 群/C2C 在 OlivOS 重启后若只给出 `ref_msg_idx`，插件会用自己的持久化注册表恢复被引用消息 ID 或机器人出站正文。
- 本轮引用会作为最后一条当前用户消息传入模型，格式为 `[引用上文:引用正文] 当前文字`，不会只埋在滚动历史里；引用正文决定“这个/那个/大纲/背景”等指代。正文无法恢复时会标记为未能读取，让机器人简短说明看不到该回复后继续处理当前文字。
- Milky 的 reply 段若只有会话内 `message_seq`，插件会利用当前完整消息 ID 补成 `scene|peer_id|seq` 后再调用 `get_msg`。
- 上述引用恢复位于 OlivaAIAgent；平台从未向机器人上报过且注册表没有记录的消息仍无法恢复。

### MCP 工具与语音回复（v2.20）

- GUI 新增“MCP 服务”分类，支持 Streamable HTTP 和 stdio；连接后远端工具以 `mcp_<服务>_<工具>` 动态加入 Agent，服务可单独设置 `danger` 并复用现有三级权限管控。运行维护页可手动刷新工具目录。
- GUI 的“语音模型”默认直连阿里云百炼 `MultiModalConversation` 原生 HTTP 接口，使用 `qwen3-tts-instruct-flash`、`Cherry` 和非流式输出；同时保留 OpenAI `/audio/speech` 兼容模式。启用后模型会看到 `send_voice` 工具，可根据语境自行决定发送语音；单次回复内相同文本只会合成并发送一次，内容不同的分段仍可分别发送。只要本轮已有语音成功发送，就不会再补发模型最终文字。
- 阿里云模式支持 `language_type`、`instructions` 与 `optimize_instructions`。每次 `instructions` 都由主模型在调用 `send_voice` 时根据当前上下文动态生成，只描述本次语速、情绪、音量、停顿和语调，不写入配置或记忆，也不是第二套人格提示词；接口返回的临时音频 URL 会立即下载，并按 URL、Content-Type 或音频头识别真实格式。
- 原生请求体与官方 `dashscope.MultiModalConversation.call(..., stream=False)` 等价，但继续使用插件已有的 `requests` 直连，无需额外安装 `dashscope` SDK。
- 语音与潜行不维护第二套提示词，全部继续使用唯一的 `prompt.system`。本地语音缓存位于 `voice/`，最多保留 10 个文件；配置为更小值时按较小值淘汰，旧配置中的更大数值会自动迁移为 10。
- `qqGuildv2` 被 @ 判定兼容 `GROUP_AT_MESSAGE_CREATE`、`sub_self_id` 和群机器人 `sub_self_open_id`，与 MessageRecall 的官机处理方式一致。
- 配套 OlivOS `qqGuildv2SDK` 会在单个被动消息 ID 达到回复上限后，依次轮换同一会话 5 分钟内仍有额度的入站消息 ID；全部候选耗尽或被平台拒绝后才改用主动消息。

## 定时提醒 / 定时主动消息（v2.7）

让 AI 真正“到点主动来找你”，而不是被动回复。对某人说「三小时后提醒我喝水」「12:52 给我发开会」，主模型会在调用 `schedule_reminder` 的同一轮写好自然的最终提醒话术并创建定时任务；到了那个时间点直接**主动推送**给你（群里会顺带 @ 你），不会再额外请求主模型或辅助模型。

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

## 视觉自动路由 + 群级触发关键词（v2.8）

- **视觉自动路由**：`vision.use_main` 默认改为 `"auto"`——**主后端支持视觉（其 `vision:true`，如 GPT-4o/Claude）就直接用主模型识图，主模型是纯文本（如 DeepSeek）就自动改用下面单独配的 OCR 视觉模型**。不用再手动判断，也可显式写 `true`/`false` 强制。
- **统一触发关键词**：所有群共用 `trigger.keywords`，潜行开 / 关都用它触发（命中即强制回复），不再保留群级关键词以及 `wake_words`/`reply_keywords` 两套重复配置。

## 图片当轮识别 + 全过程 Logger（v2.12）

- 群聊在 `vision.sync_ocr:false` 时，会把整条图片消息交给独立后台线程：先下载、识图并生成事实摘要，再继续本轮 AI 回复。这样不阻塞 OlivOS 消息总线，同时不会再让本轮回复只拿到“未识别成功”的占位；`true` 才会直接在消息总线线程识图。
- 私聊与 `.ai` 附图也走同一视觉子系统。主后端是纯文本模型时，图片会先由独立视觉模型原位转成 `[图片:识图结果]`，然后把摘要而不是原始图片 URL 交给主模型；已写盘的旧格式仍兼容。
- 前置模型与主回复模型共享同一批表情缓存候选。前置模型可以提出图片建议，主模型也能独立决定采用、改选或不发；显式 Agent/私聊主模型同样可从缓存选择图片。最终的 `[发图片:...]` 会经过同一套字段权重与模糊评分，转换成与 `olivos_string` 模式一致的真实 `[OP:image,...]` 图片消息段。
- `debug_log:true` 时，OlivOS Logger 会输出带同一“编号”的中文关键流程日志：前置判断、模型及 token 用量、命中的技能/知识资料、工具调用、本轮回复或跳过决定均可串联查看；普通群消息接收及“未开启潜行”不再逐条刷屏。API Key、token、Authorization、Base64/data URL 会自动遮蔽，长字段会截断。
- 图片识别日志精简为“图片下载”“图片识别请求”“图片识别结果”三类；缓存查询、路由选择、后台转交、摘要转换和缓存落盘不再逐步刷屏。失败结果仍保留状态码和简短错误。

## 入站语音与视频理解（v2.23）

- 支持 OlivOS 的 `[OP:record,...]` / `[OP:video,...]`（并兼容 CQ 格式），这两类消息不检查后缀，优先读取 `url`，再回退 `file`。QQ 把媒体作为 `[OP:file,...]` 上报时，音频结合 `audio/*` MIME 和 `.ogg/.opus/.mp3/.wav/.m4a/.flac` 等后缀判断，视频结合 `video/*` MIME、`name`、URL 查询参数和路径后缀判断；视频覆盖标准库已知类型，并补充 MP4、MKV、MOV、WebM、AVI、FLV、RMVB、M2TS、MXF、HEVC 等常见封装与码流格式。
- 入站语音和视频分别由 `media.audio.enable`、`media.video.enable` 控制，GUI 中也是两个独立开关。旧的 `media.enable` 已废弃，加载时会删除且不会读取或继承其值。
- `media.use_main:"auto"` 会分别检查当前 OpenAI-compatible 主后端的 `audio:true` / `video:true`。声明支持时把媒体作为当前用户消息的一部分直接交给主模型；不支持时自动调用 `media.audio` / `media.video` 中的独立模型。
- 独立识别会把结果原位写成 `[语音:转写内容]` 或 `[视频:内容摘要]`，再进入潜行历史、引用上下文和正式回复模型。失败时只留下“未识别成功”，不会把签名 URL 或 Base64 写进模型历史。
- 音频默认下载并以 `input_audio` Base64 发送，视频默认使用 `video_url`，可按接口要求把 `mode` 改成 `base64`。QQ 音频没有扩展名或 CDN MIME 缺失时会按 Ogg/WAV/MP3 等文件头自动判断；使用 Qwen Omni 时建议 `mode=base64` 且 `format` 留空。媒体大小受 `media.max_bytes` 限制，慢请求默认移到后台线程。
- `qqGuildv2_link` 的 `qq_attachments` 中，只有 `content_type=audio` 且带 `asr_refer_text` 或 `voice_wav_url` 的附件会进入 QQ 官方语音特判；官方转写开关默认开启，直接采用官方文本，不按 URL 匹配普通文件。官方结果为空或关闭开关时改用 `voice_wav_url`，格式跟随 URL 后缀，没有后缀默认 `wav`。普通 `[OP:file]` 即使是音频后缀也不使用官方转写。
- `qwen3.5-omni-flash` / 其他 Qwen Omni 兼容模式要求流式请求；插件会自动使用 `stream=true`、收集 SSE 文本，并省略可能不兼容的 `response_format`。普通 OpenAI-compatible 音频模型仍使用非流式 JSON 请求。
- 独立语音的 `provider` 支持 `auto`、`openai_compatible` 和 `dashscope_asr`。`qwen-audio-3.0-asr-flash` 使用百炼原生同步接口：`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`；`auto` 会按模型名或接口地址自动选择。原生接口保留完整 Data URL，并解析 `output.text` / `output.output.sentence.text`。
- 原生 ASR 的 `format` 必须与实际音频一致；Base64 模式留空可根据 MIME 自动判断，URL 模式没有文件扩展名时会回退为 `mp3`，应手动填写实际格式。QQ 常见 `audio/ogg` 会按 `opus` 发送；官方示例中的 `wav` 不能直接套用到所有 QQ 语音。
- `debug_log:true` 时会记录媒体下载、识别请求和识别结果；日志只包含文件短名、模型、耗时、状态和摘要长度，不记录完整 CDN URL、API Key 或媒体数据。

使用 `qwen-audio-3.0-asr-flash` 时，独立语音配置示例：

```json
"audio": {
  "enable": true,
  "api_url": "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
  "api_key": "",
  "model": "qwen-audio-3.0-asr-flash",
  "provider": "auto",
  "mode": "base64"
}
```

该模型的单文件上限为 10 MB（Base64 模式会按编码膨胀预留空间），适合 5 分钟以内音频。主模型全模态路由仍由 `media.use_main` 和主后端的 `audio/video` 能力开关控制，不受独立 ASR 协议影响。

## 合并转发与引用展开（v2.22）

- 收到 `[OP:forward,id=...]` 时会调用 `plugin_event.get_forward_msg()`，按发送者和节点顺序整理为模型可读文本；兼容 OneBot V11、Milky 与 QQ Guild V2 的节点结构及嵌套转发。
- 引用合并转发时按 `reply -> get_msg -> forward -> get_forward_msg` 两阶段读取；只在转发接口失败时使用 `raw_message` 保留文本兜底。
- 展开后的转发正文与普通消息一样持久化到 `message_registry.sqlite3`，默认最多保存 20000 字（`forward.storage_max_chars`）。后续引用优先读本地展开文本，不再重复请求平台。
- GUI 新增“合并转发”分类，分别控制节点内图片、语音、视频是否识别。三项默认关闭：只保留 `[图片]` / `[语音]` / `[视频]` 占位，清洗 URL、本地路径与 Base64；开启后复用普通消息的媒体识别流程。
- `debug_log:true` 时记录转发收到、读取开始、成功/失败、节点数与摘要字符数，不输出节点媒体资源。

## 主模型 Token 优化

- 每条消息可并行启动多个窄职责辅助判断：参与判断只判 `NEXT/SKIP`，图片判断只给图片建议，工具路由只选工具；显式 Agent 无需参与判断，只并行图片与工具任务。
- 小模型输出不依赖严格 JSON：参与、图片和工具分别兼容字段别名、直接文本、数组、工具名与 `NONE` 等格式；工具首次无法解析会用短提示再判一次，之后才回退全量工具。
- 正式回复只携带本轮相关工具；任一辅助子任务失败只回退自己的部分，不影响其他判断或主模型能力。
- 后台记忆提炼和技能元数据翻译走辅助模型；辅助模型只提供内部结构化结果，绝不生成用户可见的最终回复。定时提醒措辞由主模型在创建任务的既有工具轮中一并写好，到点直接发送，不增加模型调用。
- 主模型只读取配置的常态历史窗口，额外缓存窗口继续供前置判定与后台记忆使用；协议接口、消息 ID、骰系速查和插件列表也只在对应工具入选时注入。
- DeepSeek V4 官方接口会按 `thinking.type` 显式关闭默认思考，避免短回复产生大量不可见推理 Token。

## 前置检索：把工具决策链下放给便宜模型（v2.21）

配好 `ambient.intent_api` 前置模型后，`research` 段默认接管整条只读检索链：

- **规划**（`research.planResearch`）：前置模型判断本轮要不要联网、把口语问题改写成 1~2 条精确搜索词，并判断是否需要查共享知识库、长期记忆列表、已有提醒。与工具路由、图片建议、参与判断同在 `preflight.runCluster` 里并行。
- **执行**（`research.runResearch`）：插件用 `tools.execToolRaw` 直接跑 `web_search`/`fetch_url`/`kb_search`/`memory_list`/`list_reminders`，保留权限与内容安全检查，但不做 `tool_result_max_chars` 裸截。
- **压缩**（`research.summarizeResearch`）：结果压成 ≤`summary_max_chars` 的结论 + 来源 URL 注入主模型。Tavily 自带 `answer` 时默认直接采用，省掉这次模型调用。
- 被代跑的工具从本轮工具列表摘掉（在 `_TOOL_FAMILIES` 家族扩展之后摘，不会被成对加回），提示词注明"已由前置模型完成，不必重复调用工具"。

省的是主模型的重复往返：原来一次联网要花掉"出 tool_call → 工具结果回灌 → 再组织答案 → JSON 收尾"三四次完整 prompt，现在主模型只跑一轮。

**只下放只读、可重试、无副作用的调用。** 骰点 `run_command`、OlivOS 接口 `olivos_call`、写库 `memory_save`/`kb_save`、发语音 `send_voice` 仍由主模型决定——这些参数错了会真的骰错检定或产生副作用。

**回退语义与既有约定一致（前置失败不削能力）**：规划失败/非 JSON → 整条链放弃，工具原样留给主模型；搜索无结果 → 联网工具放回主模型；压缩失败 → 退 Tavily `answer` → 再退原始摘要限长。`mode=auto` 时没配前置模型就完全退回主模型自调工具，而不是用主模型多做两次小调用（那样通常更贵）。

长期事实注入也顺带瘦身：`semantic.promptFacts` 只保留主题、内容、跟人跨群标记和来源消息 ID，`score`/`vector_score`/`source_event_id` 等排序字段不再进提示词。

## 人设锁定与提示注入防护（v2.13）

- `prompt.system` 是机器人身份、性格、语气、称呼习惯与行为边界的唯一全局配置来源。用户可以提出正常问题、操作和一次性输出格式要求，但不能用“以后改成文言文”“每次先叫昵称”“忘掉原人设”等话术永久改写机器人。
- 防护同时覆盖最新消息、历史、引用、用户侧写、群总结、长期记忆、知识库、技能、网页、图片文字和工具结果；这些内容均作为不可信数据使用，不能覆盖系统人设。
- `memory_save`、`kb_save` 会拒绝人格控制内容；后台知识/侧写/群总结提炼在提示阶段与落盘阶段各过滤一次。升级前已经写入的数据也会在注入模型前过滤，不必立即手工删除。
- `ambient.first_thinking` 处理普通潜行消息及定向触发：普通消息先通过 `reply_probability` 概率门，命中后调用前置模型；被 @ 或引用机器人消息会跳过概率，直接交给前置模型判断。前置模型返回 `SKIP` 时不进入主模型，返回 `NEXT` 时主模型必须回应。只有关键词和 `.ai` 跳过前置判断并直接要求主模型回应。
- 只有表情包、没有文字的消息走单独的 `ambient.standalone_emoji_reply_probability`（默认 0.05）：识图结果照常写入上下文供后续理解，但默认不专门接话；被 @、引用、命中关键词或 `.ai` 触发时不受此概率限制，前置模型与主模型也会把表情包含义纳入语境后自然回应，不复述识图摘要。

## 现实政治话题保护（v2.20.11）

- `security.politics_guard` 默认开启：现实政治、政治事件、政治人物及国内领导人相关内容不会交给模型讨论；“中国”“我国”“国内”等普通地域表达不会单独触发。`.ai`、关键词、@、引用和私聊会回复配置的简短婉拒语，普通潜行消息保持静默。
- `security.use_olivadice_censor` 默认开启：OlivaDiceCore 可用且当前 bot 的 `censorMode` 开启时，直接复用 Core 已合并的全局/当前 bot DFA 词表；Core 不存在时自动降级，不增加硬依赖。
- 命中消息只以“内容已隐藏”占位进入群历史，且不会写入会话、长期记忆、知识、侧写、群摘要、向量事实或提醒。模型文字、语音、工具和定时主动消息发送前仍会二次检查。
- 可选本地词表：打开 `security.external_sensitive_words`，再在 `sensitive_word_files` 填 `.txt`/`.json` 文件，或在 `sensitive_word_dirs` 填目录。文本格式一行一词，JSON 支持字符串数组或以词为键的对象；自动热加载，不需要额外 Python 依赖，也不会自动联网下载。
- GUI“内容与人设安全”和“运行维护”都提供词库下载/更新按钮，并显示同一份安装状态；从固定 HTTPS 地址安装 [konsheng/Sensitive-lexicon](https://github.com/konsheng/Sensitive-lexicon) 的 `Vocabulary/政治类型.txt`（MIT），以后点击会通过 ETag/Last-Modified 自动检测更新。下载内容通过大小、UTF-8 和最小词数校验后才原子替换，失败时保留旧文件。
- 大型全量词库误伤更多，不建议无选择地全部启用。`ToolGood.Words`（Apache-2.0）性能很好但主要面向 .NET，不作为本插件依赖。

## 支持 OpenAI Responses API（v2.7.1）

除 `chat/completions`（openai wire）与 `messages`（anthropic wire）外，新增 **`responses` wire**，对接 OpenAI 的 `/v1/responses` 接口（GPT-5 / o 系列等新模型偏好的统一接口）。

- **零配置识别**：把 `api_url` 指向 `.../responses`（如 `https://api.openai.com/v1/responses`）即自动走 Responses 报文；也可在后端段显式写 `"wire": "responses"` 强制。
- **完整对接**：内部消息自动转 `input` 数组（system→`instructions`、图片→`input_image`、工具调用→`function_call`、工具结果→`function_call_output`）；工具用扁平结构；`max_output_tokens`；思考模型走 `reasoning.effort`；流式解析 `response.output_text.delta` / `response.function_call_arguments.delta`，并以 `response.completed` 的完整 output 为权威；流中途 `response.failed` 不冒充成功。
- 全接口工具循环、骰点、视觉识图在 responses wire 下与原有 wire 完全一致。

## 稳健性与安全修复（v2.6.3）

一轮多 agent 代码审查（9 维度并行审 + 逐条对抗验证）后修复的确认问题：

- **定向请求不丢失**：`.ai`/@/引用机器人/关键词不再被概率或节律锁的“让位”机制静默丢弃；@/引用仍可由前置小模型决定 `SKIP`。
- **消息总线不卡**：视觉 OCR/下载默认移出消息派发线程（未命中的图后台识别），慢图不再阻塞全 bot 的骰点等功能（`vision.sync_ocr` 可切回同步）。
- **并发安全**：视觉图片缓存（dict/deque）跨线程读写全部加锁并快照迭代，消除 `RuntimeError` 掉回复；知识/侧写/群总结写入统一持锁。
- **数据不损坏**：所有持久化（配置/群开关/会话/记忆/潜行历史/图片缓存）改为原子写（临时文件 + `os.replace`），进程中途被杀或并发写不再截断损坏文件。
- **配置不丢**：`config.json` 解析失败时**不再用默认配置覆写**用户文件（API Key 等保住），改为备份为 `.bad` 并用默认值在内存里跑；读取兼容 BOM。
- **权限**：`send_forward_msg` 补齐跨目标三级门槛（不能再绕过管控跨群发消息）；`hotReload` 补上 `_migrate`，旧式 `master_only` 配置热载后不再被降权为所有人可用。
- **模型调用**：官方 DeepSeek V4 默认开启思考，配置 `thinking:disabled` 时会显式关闭，避免短回复仍产生大量隐藏推理 Token；其他严格 OpenAI 端不会收到 disabled 扩展参数。流式响应中途的 error 事件不再冒充成功；SSE 强制 UTF-8 解码（修中文乱码）。
- **会话不中毒**：私聊会话不再持久化图片 CDN URL（过期后逐轮重放会让整会话每次 400）。
- **其它**：`.ai clear group` 一并清群统一管线上下文；非法 `context_buffer`/记忆上限做夹取防御（不再 `IndexError` 或清空）；技能检索缓存加上限（防长跑内存泄漏）；`extra_dirs` 误配字符串不再按字符展开建垃圾目录；移除失联的"自由唤醒"死代码（其职能已并入潜行统一管线）。

插件自带回归测试当前已超过 **170 项**，覆盖配置迁移、群路由、Core/Logger 出站桥接、内容安全、词库更新、辅助判断集群、非 JSON 兜底、消息引用、语音、MCP、视觉和记忆等关键路径。

## 统一设置面板（v2.18）

OlivOS 托盘菜单选择“打开设置面板”，即可在一个窗口完成全部配置：

- “全部配置”按功能分类覆盖其余 `config.json` 运行字段，布尔值、枚举、数值和 JSON 列表分别使用对应控件；API Key 默认遮蔽。
- “群级设置”集中管理插件全局启用、白名单模式、新群默认开关、全局前缀/关键词，以及 `groups.json` 中每群的插件开关、潜行、高危工具和记忆覆盖。前缀/关键词不再提供群级覆盖；同一群 ID 也只保留一条记录。独立的“全局启用”和“群白名单”分类已移除。
- “运行维护”可查看当前模型、工具、技能、向量、视觉和提醒状态，并重建技能索引或重载静态知识库。
- 保存后立即更新插件内存并原子写盘；原配置文件仍可手工编辑和热重载。

全局提示词已统一为唯一字段 `prompt.system`。升级时旧 `ambient.personality` 与 `prompt.append` 会自动合并进去；旧 `ambient.enabled_groups` 和 `whitelist.groups` 都会迁移到 `groups.json`，旧权限布尔字段也会转换并移除。迁移过程保留原内容。

## 安装

1. 将 `OlivaAIAgent.opk` 放入 OlivOS 的 `plugin/app/`（或整个文件夹放入）
2. 启动后从 OlivOS 托盘菜单选择“打开设置面板”
3. 在“OpenAI / 千问兼容”中填写 API Key 与模型，点击“保存并应用”
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
    "reasoning_effort": "high",         // high / max
    "vision": false, "audio": false, "video": false // 主模型确实支持对应输入时才开启
  },
  "anthropic": { "api_url": "...", "api_key": "", "model": "claude-sonnet-4-20250514" },

  "prompt": { "system": "系统规则与统一人设……" }, // ← 全局提示词只配置这一处

  "trigger": { "keywords": ["骰娘"] },   // ← 所有群共用的关键词

  "security": {
    "politics_guard": true,
    "politics_reply": "这个话题小芙不聊哦，换一个吧~",
    "use_olivadice_censor": true,      // 跟随当前 bot 的 OlivaDiceCore 敏感词
    "external_sensitive_words": false,
    "sensitive_word_files": [],          // 可选本地 txt/json 词表
    "sensitive_word_dirs": []            // 可选本地词表目录
  },

  "memory": {
    "max_rounds": 8,                  // Agent 常态历史 8 轮
    "prompt_cache_max_rounds": 16,    // 缓存增长到 16 轮后回落
    "history_summary_default": true,   // 新群默认开启滚动摘要
    "long_term_default": true,         // 新群默认开启长期事实
    "extraction_batch_size": 8         // 累积多少条新记录后提炼
  },
  "semantic_memory": {
    "embedding_api_url": "https://api.openai.com/v1", // 自动追加 /embeddings；也可填完整路径
    "embedding_api_key": "",
    "embedding_model": "qwen3.7-text-embedding",
    "top_k": 6
  },
  "mcp": {
    "enabled": true,
    "servers": [
      {"name":"remote", "transport":"streamable_http", "url":"https://example.com/mcp", "headers":{}, "danger":true},
      {"name":"local", "transport":"stdio", "command":"npx", "args":["-y", "@example/mcp-server"], "env":{}, "danger":true}
    ]
  },
  "voice": {
    "enabled": false,
    "provider": "dashscope_multimodal",
    "api_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
    "api_key": "", "model": "qwen3-tts-instruct-flash", "voice": "Cherry",
    "language_type": "Chinese", "optimize_instructions": true
  },

  "ambient": {                       // ← 潜行模式（刺客同款+增强）
    "reply_probability": 1.0,        // 随机插话概率(建议连同 first_thinking 一起调)
    "standalone_emoji_reply_probability": 0.05,   // 纯表情包消息的插话概率(照旧识图入上下文)
    "history_size": 8,
    "prompt_cache_optimized": true,  // DeepSeek 前缀缓存优化
    "prompt_cache_history_size": 16,
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
  "media": {                         // 入站语音/视频识别
    "use_main": "auto", "sync_media": false,
    "max_bytes": 52428800,
    "audio": {
      "enable": false,
      "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
      "api_key": "", "model": "qwen3-asr-flash", "provider": "auto", "mode": "base64"
    },
    "video": {
      "enable": false,
      "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
      "api_key": "", "model": "qwen-vl-max", "mode": "url"
    }
  },
  "forward": {                       // 合并转发媒体；正文始终展开
    "image": false, "audio": false, "video": false, "storage_max_chars": 20000
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
| `.ai memory status` | 查看本群滚动摘要、长期事实与向量状态 | 所有人 |
| `.ai memory history on/off` / `.ai memory long on/off` | 独立控制本群滚动摘要 / 长期事实 | 骰主 |
| `.ai on/off`、`.ai global on/off` | 本群/全局开关 | 骰主 |
| `.ai stealth on/off` | 本群潜行（群友融入）模式；**off 时只有本群前缀和关键词触发**，@、引用和普通消息均静默 | 骰主 |
| `.ai stealth think on/off` | 潜行前置判定开关 | 骰主 |
| `.ai stealth tools on/off` | 潜行是否可调工具/骰点 | 骰主 |
| `.ai admin [global/masteronly] on/off` | 高危接口全局开关 / 旧式仅骰主开关（推荐用 `.ai admin role master`） | 骰主 |
| `.ai wl on/off/add/del/list` | 白名单模式与统一群列表；add 会加入群级设置并启用，del 会移除群设置 | 骰主 |
| `.ai skills reload` / `.ai kb reload` | 重建技能索引 / 重载知识库 | 骰主 |
| `.ai model <名>` / `.ai reload` | 切模型 / 重载配置 | 骰主 |

## 数据目录 `plugin/data/OlivaAIAgent/`

- `config.json` / `groups.json` — 全局配置与统一群列表/每群覆盖
- `Knowledge/*.json` — 手动维护的静态知识库 `{关键词: 内容}`
- `skills/<名>/SKILL.md` — Codex 技能/规则书（支持 frontmatter 的 name/description/aliases/keywords/triggers + references/ 资料）
- `Image/` — 视觉缓存图片；`voice/` — AI 生成语音缓存；`ambient_history/` — 每群公共历史；`ambient_memory_*.json` — 知识/侧写/滚动摘要；`semantic_memory.sqlite3` — 长期事实与向量；`message_registry.sqlite3` — 消息 ID、引用及正文；`memory_extraction_state.json` — 提炼水位；`sessions/` — 按平台、群和用户保存实际 AI 问答；`memory/` — 手动长期记忆；`logs/` — 按天保存脱敏后的插件运行日志

`logs/` 默认启用，每日文件名为 `YYYY-MM-DD.log`。`file_logging.retention_days` 控制保留天数，`max_file_mb` 控制单文件轮转上限；`debug_log` 只决定是否产生详细流程记录，不影响启动信息和错误日志落盘。GUI“维护工具”中可以直接打开会话和日志目录。

## 说明

- `app.json` UTF-8 无 BOM；优先级 30000，运行于 OlivaDiceCore(20000) 之后
- 所有 AI 调用在后台线程，不阻塞消息总线；潜行模式用节律锁，连发消息只回最后一条
- 潜行的高危接口调用同样受三级权限管控；`run_command` 以发起用户身份重注入，不越权
- 与其他 AI 插件（如刺客/ChatGPT）同装时请错开触发词与潜行群，避免双回复
