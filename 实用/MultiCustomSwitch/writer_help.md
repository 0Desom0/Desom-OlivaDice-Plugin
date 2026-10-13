# MultiCustomSwitch 自定义回复编写帮助

## 回复库与内置序号

每个回复 JSON 是一个对象：键为 Core 的回复项名称，值为字符串。例如：

```json
{
    "strBotName": "青果",
    "strRoll": "{tName} 掷出了 {tRollResult}"
}
```

变量以实际回复项提供的说明为准。可以从已有回复复制，再修改其中的文本。

1/default 是 Core 原有回复，与 OlivaDiceWebUI、OlivaDiceNativeGUI、Core 的 `.str` 共用内存与
`plugin/data/OlivaDice/<bot_hash>/console/customReply.json`，修改后其他面板刷新即可看到。
2/smp 是 `OlivaDiceCore.msgCustomManager.getDictStrCustomDefault()` 汇总的全默认回复，只读。
其 Bot 名来自账号登录信息；登录接口暂不可用时显示账号 ID。
自定义回复序号必须 >=3，序号可不连续。

## 默认、修改状态与恢复模块

自定义文件没有包含的键从 smp 补齐，不从 default 的自定义文本补齐。
保存回复项时，与 smp 完全相同的项可以从文件中省略。`{}` 表示全部使用默认回复的模板。
外部导入同样接受 `{}`，与 Core 的空修改项文件兼容；它代表全默认模板。

“已修改”表示当前文本不同于恢复模块提供的源码默认文本；没有默认文本的额外回复项也算已修改。
“未保存”表示编辑框中尚未保存的改动，和“已修改”是两种不同状态。
本插件与官方 WebUI 一样，按文本比较，不只根据 customReply.json 是否含有该键判断。

bot 的恢复模块直接读取并写入 Core 数据目录中同一份 `console/recover_model.json`：

```json
{"modules": ["OlivaDiceCore", "OlivaDiceJoy", "OlivaDiceMaster"]}
```

模块按列表顺序覆盖同名键；未加载的模块不导入。清空模块列表采用官方默认的六模块列表。
unity 可选择某个 bot 的恢复模块作为比较基线；不选择时使用 Core 的完整默认集合。
恢复模块仅影响编辑界面的默认比较与恢复操作，不改变 smp 的全默认集合。

## 模板格式

- `{tName}` 等变量由对应命令注入；未识别的变量保留原样。请参考回复项说明。
- `|` 分隔多条随机回复，Core 随机选取其中一条。
- `{OR}` 或 `{DEVIDE}` 用于输出字面上的竖线。
- `{牌堆名}` 在不是已知变量时尝试抽取牌堆，由 Core 处理。
- JSON 的 `\n` 表示实际换行；在编辑框直接换行即可。
- 花括号内的转义，如 `{\f}`，仍按 Core 的 `processEscapeSequences()` 处理。
- 空字符串是有效回复文本；不要把字符串换成数组、数字、布尔值或嵌套对象。
- 本插件不运行导入内容中的 Python 或 JavaScript。回复格式化仍由 Core 和其已有 hook 完成。

## 图片消息

自定义回复中的图片使用 `[CQ:image,file=图片地址]`，其中 `CQ` 必须大写。例如：

```text
检定成功！[CQ:image,file=https://example.com/success.png]
```

将示例地址换成可直接访问的图片链接；实际发送由所接入的消息协议处理。
Core 与本插件使用 `old_string` 消息模式，解析 CQ 码。
`[OP:image,...]` 属于 `olivos_string` 模式，在当前回复流程中会被当作普通文字。

## 程心自定义解析

回复内容支持程心的 `【……】` 语法，须满足以下条件：

- 已安装并加载 OlivaDiceJoy 和 ChanceCustom（程心自定义）。
- 在当前 bot 的官方设置中，将 `joyEnableCCPK` 设为 `1`，开启回复词的程心解析。

例如，可在回复编辑框中填写：

```text
【发送者昵称】，你的幸运数字是【随机数1>=<100】！
```

本插件切换后的回复仍经过 Core 的正常格式化流程，其中 Joy 通过 `msgFormatHook`
调用程心解析器；无需在 MultiCustomSwitch 中另行启用。未开启上述设置时不会执行程心解析。
程心解析后发送图片仍使用 `[CQ:image,file=...]`。

## 新建、导入、下载与共享

新建必须从 default、smp、当前回复或其他库的任意回复复制。不会创建没有来源的空回复。
unity 只保存模板，在 unity 中新建或修改不会自动加载到 bot。
使用“从其他库导入”，将 unity 或另一个 bot 的回复复制到当前库；反向操作可导出到 unity。
各库也可从本地 JSON 导入，或从 HTTP/HTTPS JSON 链接下载。下载先校验回复结构，再导入。
导入同名回复时选择“覆盖 / 创建为副本 / 取消导入”；覆盖保留原序号和所有群引用。
新建、改名以及导入都禁止同一文件夹内出现重名，包括 Windows 下仅大小写不同的名称。

导出得到包含完整生效文本的普通 Core 回复 JSON，可用于官方面板导入。
可导出 default 或 smp。导入名为 default 的回复时，覆盖会修改 Core 原始回复；
导入名为 smp 的回复也显示重名选项，但覆盖会明确拒绝，须创建为副本或取消。
unity 没有内置序号，可以保存名为 default 或 smp 的模板。

## 目录与序号维护

```text
plugin/data/MultiCustomSwitch/
├── unity/
│   └── 回复名.json
└── <bot_hash>/
    ├── config.json
    ├── custom_list.json
    ├── 回复名.json
    └── group/
        └── <group_hash>.json
```

`custom_list.json` 是序号到文件名（不含 `.json`）的映射：

```json
{"3": "温柔青果", "7": "简洁回复"}
```

改名时同步重命名回复文件及列表记录，保留序号；不需要修改群文件。
修改序号时提供完整序号表，可一次交换两个序号。插件遍历所有群文件并同步全局默认序号，
保证它们仍指向同一套回复。原文件无效时中止操作，避免错误改写引用。
群 hash 与 Core 一致：聊天消息直接使用 Core 的 `msgReply.getHagIDFromMsg()` 获取群标识，
普通群为 `str(group_id)`，频道群为 `host_id|group_id`，再调用
`userConfig.getUserHash(userId=群标识, userType='group', platform=消息平台)`，不传 `subId`。
同一群、同一平台在不同 bot 下的群 hash 相同，配置由外层 bot_hash 目录隔离；私聊不使用群 hash。

`config.json` 与群文件都使用：

```json
{"reply_model": 1, "enabled": true}
```

首次安装全局和群默认开启，默认序号 1。没有群文件的群继承全局回复。
第一次本群切换或设置开关会创建群文件，记录当时的回复和本群开关；之后保留群的单独设置。
全局回复仅改变未单独设置群的默认回复，私聊使用全局回复。
全局开关与群开关都开启时才使用选定回复；任一个关闭时恢复 Core 原有回复。
本插件不遵循 OlivaDiceCore 的群链。即使两个群已在 Core 中关联，本插件的回复选择与开关
仍按当前 bot、当前实际群独立保存，不沿群链同步或继承。没有单独设置的群仍继承本 bot 的全局设置。
命令头按模板的前缀贪婪匹配方式解析，不需要空格，例如 `.mcs 3`、`.mcs 回复名`、
`.mcs global 2`、`.mcs global off`。`global` 优先被识别为全局子命令；命令关键字优先于同名回复。
