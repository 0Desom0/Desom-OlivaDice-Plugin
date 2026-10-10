# 获取主动授权

基于 OlivOS 官方原生模板，独立运行，仅处理 qqGuildV2 的 QQ 群消息。手动命令生成并发送一张设置说明图；可由骰主为当前 bot 开启自身入群自动发图，默认关闭。授权跳转按钮继续注释停用，不做 GUI / WebUI。

## 使用

根命令统一为中文 `授权`、英文 `auth`，子命令为 `全消息/allmsg`、`帮助/help`、`入群/join`。前缀均支持 `.`、`/`、`。`：

| 功能 | 中文 | 英文 | 权限 |
| --- | --- | --- | --- |
| 发设置图 | `.授权 全消息` | `.auth allmsg` | 任何群成员 |
| 帮助 | `.授权 帮助` | `.auth help` | 任何群成员 |
| 开启入群自动发图 | `.授权 入群 开` | `.auth join on` | 骰主 |
| 关闭入群自动发图 | `.授权 入群 关` | `.auth join off` | 骰主 |
| 查看开关 | `.授权 入群 状态` | `.auth join status` | 骰主 |

help 正文提供中英文对照，示例使用空格便于阅读；空格可省略，仍按关键词匹配。

命令参考轻量插件模板，**逐层按最长关键词优先匹配，再处理右侧余文，不用空格分词**。根命令、子命令、参数间的空格可省略，也可以保留。例如 `.授权入群开` / `.授权 入群 开`、`.authjoinon` / `.auth join on` / `.authjoin on` 均有效。

中文根命令后使用中文子命令，英文根命令后使用英文子命令；入群参数可用 `开/on`、`关/off`、`状态/status`。英文大小写不敏感。仅有 `.授权` / `.auth` 时显示帮助；没有参数的 `.授权入群` / `.authjoin` 查询状态。发图和帮助不接受尾随参数，入群参数只匹配完整余文，避免 `.authjoinonward` 等文本误修改开关。

原 `.allmessage`、`.授权全消息 帮助`、`.authjoin help` 不再作为命令别名；帮助统一为 `.授权帮助` / `.authhelp`。不接受群号或 bot 参数，命令仅在 QQ 群聊生效，通过消息来自哪个 bot 决定操作对象。

成功时只回复 **一张 PNG 图片**，引用用户发送命令的当前消息，不前置 @。原消息 ID 保留为被动回复凭据，图片正文为空，不追加文字或换行，也不发送 Markdown / 授权按钮。所有命令的帮助、开关结果、权限与错误提示，以及图片失败后的文字指引，都引用当前命令消息，不 @ 发送者。

同一张 PNG 合并两条手动设置路径。原成员列表路线完整保留（包括资料页 QQbot 背景和控件）：

1. 群成员列表 →「机器人」分组，找到当前机器人。
2. 进入机器人资料页，点击右上角齿轮。
3. 消息范围选「获取群内全部消息」，打开「机器人主动在群聊内发言」。

如果群成员列表不好找，也可以从群机器人页面进入：群聊右上角菜单 →「聊天信息」→ 群主点击「群机器人」→ 当前 bot 最右侧的「管理」→ 同样的两项设置。图中的群机器人列表只显示当前 bot 的头像和名称，不显示其他机器人、状态小字或简介。

保留白色界面、原参考图的红框 / 红圈 / 操作提示，动态填入 bot 名称、AppID 与头像；不显示机器人简介。只有群主能完成设置，说明图顶部用加大红字强调「仅限手机 QQ 9.2.90 及以上」「电脑端目前不可用」，并写明「低于该版本，请群主先更新 QQ」。help 和文字降级同步保留这些静态操作说明。插件不检测或校验 QQ 客户端版本，也不添加点击时的自定义版本提示。

## 骰主权限与入群自动发送

权限是两者的并集：

- 已加载 OlivaDiceCore 时，调用 `OlivaDiceCore.userConfig.getUserHash` 和 `OlivaDiceCore.ordinaryInviteManager.isInMasterList` 检查当前 bot 的 Core 骰主；插件全局 `masters` 也有效。
- 没有 Core 时，使用插件全局 `masters`。QQ 群主或管理员身份本身不授予开关权限。

所有可编辑配置统一使用 `plugin/data/QQGroupAuthorize/config.json`。首次加载为每个 qqGuildV2 bot 创建兜底名称和默认关闭的入群开关：

```json
{
  "svn": 0,
  "browser_path": "",
  "masters": ["YOUR_GROUP_MEMBER_OPENID"],
  "bots": {
    "ACTUAL_BOT_HASH": {"name": "", "auto_join": false}
  }
}
```

示例中的占位符请替换为真实字段。`masters` 在插件内全局生效，填的是 QQ 官方群消息 `user_id` / 成员 OpenID 字符串，通常不是 QQ 号。`.authhelp` 会在末尾显示当前用户 ID，方便复制到配置。不同机器人对应的 OpenID 可能不同，可以将所需 ID 都放进同一个列表。Core 骰主沿用 Core 当前 bot 的 masterList，不修改其配置。

开关保存于 `bots[bot_hash].auto_join`，默认 false，不随 unity 或主从 bot 重定向。开启意味着**该 bot 在任何新加入的 QQ 群**都自动发图，其他 bot 不变；不会对已经加入的群补发。配置按请求读取，可直接编辑后生效。更新保留其他 bot 和无关配置字段，写盘失败或 JSON 损坏时不报告开关已改变、不覆盖损坏文件，自动发图按失败关闭处理。

参考 Core `ordinaryInviteManager.unity_group_member_increase` 的自身入群判断，在 OlivOS `Event.group_member_increase` 中仅处理 `GROUP_ADD_ROBOT`，同时确认 `user_id` 是当前 bot。普通成员入群、私聊、频道及其他平台均不自动发图。

QQ 入群事件携带 `event_id` 时沿用 SDK 的被动事件回复额度发送图片；没有命令发送者，因此不 @ 机器人自身，也不伪造可见引用。未提供事件凭据时不改为主动发送，记录原因。不会 `set_block()` 拦截入群事件，Core 原有欢迎与入群记录继续执行。图片或缓存失败用同一 event_id 发手动文字指引；重复入群投递去重，短时间换 ID 的重复通知也去重。

没有修改 Core 或 OlivOS 主项目；实现依据来自本地 Core `ordinaryInviteManager.py` / `msgEvent.py` 和 QQ SDK 的 `GROUP_ADD_ROBOT` 映射。发送成功仍取决于 QQ 平台接受事件回复，离线测试不代表真实入群发送已验收。

## 清晰度和缓存

页面只显示手动流程，减少此前两部分内容带来的缩放。HTML 逻辑尺寸为 **1560 × 2130**，浏览器按 **1.5 倍像素**截图，输出 **2340 × 3195 PNG**。关键文字与界面字样已放大，背景和操作控件均完整显示。保存只做无损 PNG 优化，没有 WebP 转码、JPEG 压缩或调色板减色。

当前无头像示例约 550 KiB，实际体积随头像与系统字体变化。有效缓存直接复用，不重新启动浏览器。内容摘要包含名称、Proc AppID、头像、主色、字体、HTML 和输出像素尺寸；同时校验图片摘要。每个 bot 各自生成 `auth_<bot_hash>.png`，不会因为共用目录发出上一台 bot 的图。

顶层 `svn` 由插件管理，表示成功生成并保存图片的插件修订号。缺少字段时按 **0** 读取；第一次发图，或当前 `app.json` 的 svn 大于保存值时，即使内容摘要相同，也强制重新生成 PNG。图片与缓存落盘成功后写入当前 svn，保留其他配置字段。生成、缓存写盘失败时不提前提高 svn；svn 写入失败仍可发送已生成图片，下次继续重试。相同 svn 复用有效缓存；运行旧插件时不降低配置中的 svn。检查在需要发图时执行，不在加载阶段主动启动浏览器。

当前 svn 在 import 阶段从安装包 app.json 读入内存，OlivOS 清理解包目录后仍能核对，避免硬编码修订号与清单不一致。

相对路径均基于 OlivOS 启动工作目录：

```text
plugin/data/QQGroupAuthorize/
├── avatar.png                  # 用户提供的最终图片兜底，不被在线下载覆盖
├── <bot_hash>.png              # 在线头像下载缓存；读取时也支持其他常见后缀
├── auth_<bot_hash>.png         # 当前 bot 的生成图
├── auth_<bot_hash>.cache.json  # 当前 bot 的页面内容与图片摘要
├── config.json                 # 共用浏览器、全局骰主、按 bot 保存的 name 与入群开关
└── theme.json                  # 首字占位头像使用的随机色
```

旧版 WebP、共用 `authorization.png` 和 bot hash / unity 子目录中的旧文件不会自动删除或迁移；新版本不再读取它们。

## Bot 信息与头像

AppID 使用事件 bot hash，从 `Proc.Proc_data['bot_info_dict']` 匹配已加载账号，读取其 `id`。不把群 OpenID、bot OpenID 或 AppID 混用。找不到 Proc 对应账号时降级成文字指引。

头像顺序：

1. 群事件有 `extend['sub_self_open_id']` 时，使用 `https://q.qlogo.cn/qqapp/<Proc AppID>/<OpenID>/0` 获取在线头像；成功即把规范化 PNG 写入资源目录的 `<bot_hash>.png`。
2. 在线获取失败、图片无效或 OpenID 缺失时，读取同目录中以当前 bot hash 命名的图片。
3. 当前 bot 的图片也不可用时，读取用户提供的 `avatar` 图片，这是最终图片兜底。
4. 所有头像都不可用时，以名称首字生成占位头像。

bot hash 图片与用户 `avatar` 均支持 png / jpg / jpeg / webp / gif / bmp，后缀大小写均可，按列出顺序查找有效图片；无效图片会继续尝试后面的后缀。自动下载统一保存为真实 PNG，不把 PNG 内容套用其他后缀。缓存直接用 bot hash 命名，不创建头像子目录，不读取其他 bot 的头像。

在线头像按 AppID / OpenID 缓存在内存一小时，失败冷却一分钟；新的有效头像会更新当前 bot 的下载缓存，数据未变化时不重复写盘。不会覆盖用户的 `avatar.png` 或其他后缀文件。下载缓存写入失败时仍使用本次已取得的头像，不影响发图。头像根据主要颜色调整主色，灰度头像使用灰色；页面居中圆形裁切，不修改用户头像文件。

名称先取已加载 Core 的当前 bot 名称，再尝试 QQ 自身账号名称。取得有效名称时显示它，并写入 `config.json` 的 `bots[bot_hash].name`；获取失败才读取对应 bot 保存的 `name`，最后回退到带 AppID 的默认名。自动生成的默认名不会写成缓存。不同 bot 的 name 独立，名字变更会更新保存值；名称或头像缓存写入失败时依然使用本次数据。所有显示文字均做 HTML 转义。

`browser_path` 是同一 config.json 中的全局浏览器路径，空字符串表示自动查找；`masters` 也是全局的，`name` 与 `auto_join` 按实际 bot hash 保存。

**没有旧配置兼容或迁移逻辑。** 不再读取或生成 settings.json，也不读取旧版全局 bot_name。显示、权限、开关只使用本文中的统一字段。运行目录内已有旧文件不会自动删除；需要的兜底名称请在对应 bot 条目的 name 中配置。

## 安装与跨平台

把 `QQGroupAuthorize.opk` 放入 OlivOS 的 `plugin/app/`，按已有流程加载；也可直接使用源码目录。没有自动部署或修改运行中的客户端配置。

运行环境为 Python 3.11，使用提供的青果主项目 qqGuildV2 SDK。第三方运行依赖仅为 **OlivOS 已有的 Pillow 和 requests**；无新增包、无 Playwright / Selenium 运行依赖。

HTML 截图使用本机已有 Chrome、Edge、Chromium 或支持的 Chromium 系浏览器，不下载浏览器，不使用用户浏览器资料，不启动可见窗口，单次最长等待 25 秒。

| 系统 | 浏览器查找 | 字体优先顺序 |
| --- | --- | --- |
| Windows | Program Files / Program Files (x86) / LocalAppData | Microsoft YaHei → Microsoft YaHei UI → SimHei |
| macOS | /Applications 与 ~/Applications | PingFang SC → Heiti SC → Hiragino Sans GB |
| Linux | PATH 中的 Chromium / Chrome / Edge | Noto Sans CJK SC → WenQuanYi Micro Hei → Droid Sans Fallback |

继续回退到系统 sans-serif。Linux 需要已有中文字体，不自动安装软件；root 启动本地静态页面时使用 Chromium 所需的 `--no-sandbox`。HTML 禁止脚本及外部资源，头像以内嵌图片提供。

## OPK 与降级

源码 HTML 与 `renderer.py` 同级，在 import 阶段读入内存。OlivOS 清理解包目录后，渲染仍从内存把页面写入新的短期目录。临时浏览器目录用完清理。

| 情况 | 行为 |
| --- | --- |
| 无浏览器、HTML 不可用、截图超时、PNG 保存失败 | 引用当前命令消息并被动回复一条手动设置文字（入群事件无引用） |
| 缓存损坏或摘要不符 | 重新生成，失败时文字降级 |
| 缓存不可写 | 直接从内存发送本次生成的 PNG |
| 图片上传或发送失败 | 尝试引用当前命令消息并被动回复手动设置文字（入群事件无引用） |
| 被动额度用尽或请求拒绝 | 记录失败，不改为主动发送 |

正常只发送一张图；失败替代回复可能消耗额外被动额度，仍沿用 SDK 序号限制。聊天命令回复使用 at_sender=False、quote_reply=True 的语义：msg_id 保留触发消息的被动凭据，message_reference 使用 SDK 解析的当前消息 REFIDX，不添加 @ 或 OP/CQ reply 文本。用户引用着另一条消息发命令时，回复仍引用这次命令消息，不引用用户先前选择的消息。入群事件则只携带 event_id，没有可见引用，也不 @ 机器人自身。旧版事件缺少 REFIDX 时保留当前消息 ID 交给平台处理，不伪造引用成功。

## 停用的按钮授权入口

`main.py` 的第二条发送流程已注释，`transport.py` 中旧正文和按钮函数仅作为停用实现保留，当前任何命令都不会调用。HTML 中已移除按钮授权部分，也不订阅或处理按钮互动。

用户提供了客户端授权跳转形式：

```text
https://club.vip.qq.com/transfer?open_kuikly_info=<URL 编码的 JSON>
```

JSON 包含 `page_name=ai_group_service_agreement_pop_page`、真实 `groupCode`、机器人 `botUin`、`botUid` 和 `screen=1`。这只是用户提供的后续参考，当前不生成、不访问或发送此地址；不能把群 OpenID 当实际群号，也不能把 bot OpenID / AppID 当 botUin / botUid。待具备正确身份数据且用户要求恢复时再实现链接按钮。

## 源码与验证

```text
QQGroupAuthorize/
├── __init__.py
├── app.json                    # UTF-8，无 BOM
├── main.py                     # 中英文命令、帮助、入群事件、发图与降级
├── config.py                   # 全局骰主与每 bot 的入群开关
├── transport.py                # 被动发送、命令引用且不 @，入群无引用，保留停用入口
├── resources.py                # Proc AppID、在线/本地头像、共用设置
├── renderer.py                 # 内存 HTML、跨平台字体、清晰 PNG 与缓存
├── authorization.html          # 手动设置三步图
├── preview/authorization.png   # 演示图
├── tests/test_plugin.py
└── tools/build_opk.py
```

从源码目录执行 `python tools/build_opk.py`。包内所有八个运行文件直接在根层，**没有文件夹、没有 README**；测试、预览、缓存及账号数据不进包。脚本检查 app.json 无 BOM。

离线测试使用 OlivOS 测试依赖 pytest，网络边界全部替换，不访问真实账号或发送真实群消息。覆盖手动单张图、中英文命令与帮助、骰主权限并集、按 bot 开关与默认关闭、配置损坏/写入失败、自身入群 event_id 回复与去重、非自身/非 QQ 群排除、图片失败降级、Proc AppID、头像优先级、PNG 缓存与解包资源删除后的内存读取。

Windows 已用真实浏览器生成并检查 PNG；macOS / Linux 的字体和浏览器查找已离线核对，尚未实机运行。群主手动设置权限仍需在目标群验收。

参考：[官方原生模板](https://github.com/OlivOS-Team/OlivOSPluginTemplate)、本地主项目 qqGuildV2 SDK，以及用户提供的实机截图和授权链接研究。
