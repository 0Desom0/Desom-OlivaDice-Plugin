# 多自定义回复切换（MultiCustomSwitch）

为同一个骰子在不同群使用不同回复风格，提供独立 WebUI 和桌面 GUI。
强依赖 **OlivaDiceCore**，已验证本机 Core 3.5.1 源码与 `D:\OlivOS` 中的 Core 3.5.0 OPK。
沿用强依赖 Core 的规则插件模板与生命周期，回复库和界面业务共用实现。

## 安装与入口

将打包的 `MultiCustomSwitch.opk` 放入 OlivOS 的 `plugin/app/`，然后重载插件。
也可以将本目录以 `plugin/app/MultiCustomSwitch/` 文件夹形式安装。
OPK 包根目录直接包含 `app.json`，不能再套一层同名目录。

- 聊天指令：`.mcs help`。
- WebUI：宿主侧栏“插件页面 → 多自定义回复切换 → 回复管理”。
- GUI：托盘插件菜单“多自定义回复切换”。
- 编写帮助：[writer_help.md](writer_help.md)，在导入时独立加载进内存，两个界面均可查看。

需要支持 `plugin_event_router(event, plugin_model, plugin_name)` 的 OlivOS 宿主。
Core 有 `getDictStrCustomDefault()` 时直接调用；3.5.0 缺少该辅助函数时，按同样的已加载模块顺序汇总默认回复。
WebUI 使用宿主插件消息桥和静态资源缓存；
不额外启动网络服务，不需要 Node.js、npm 或第三方前端依赖。
GUI 使用 Python 自带 Tk；无 Tk 的服务器仍可使用聊天指令及 WebUI。
首次进入 unity 模板库时，尚未导入模板则回复列表为空；在“回复库”中选择具体 bot 即可查看 1/default 和 2/smp。
若使用 1.0.0 时提示“插件尚未初始化”，请替换为 1.0.3 OPK 并重载插件；不需要为此修改 Core 源码。
WebUI 编写帮助渲染 Markdown 标题、列表、代码块、行内代码、强调和链接，不依赖外网资源。
帮助使用右上角叉号关闭，滚动文档时关闭按钮保持可见，每次打开均从顶部显示。

## 指令

| 指令 | 作用 | 权限 |
| --- | --- | --- |
| `.mcs [回复名或序号]` | 本群选择回复 | 群主/管理员/当前 bot 的骰主 |
| `.mcs global [回复名或序号]` | 当前 bot 的全局默认回复 | 骰主 |
| `.mcs list` | 当前 bot 可用回复列表 | 所有人 |
| `.mcs show` / `.mcs` | 本群选择、开关与实际生效回复 | 所有人 |
| `.mcs on/off` | 本群开关 | 群主/管理员/当前 bot 的骰主 |
| `.mcs global on/off` | 当前 bot 的全局开关 | 骰主 |
| `.mcs help` | 指令帮助，明确说明 1/default 与 2/smp | 所有人 |

命令头按轻量模板的规则做前缀贪婪匹配，无需空格，例如 `.mcs3`、`.mcs简洁回复`、
`.mcsglobal2`、`.mcsglobaloff`；也接受 Core 配置中的命令前缀和大小写形式。
精确名称未命中时，直接调用 Core `.st set` 使用的 `fuzzySearchAndSelect()`，
发送推荐列表并等待数字选择。候选编号是当次搜索编号，不是自定义回复的固定序号。

1/default 与官方面板共用 Core 的原始回复；2/smp 是 Core 全默认回复，只读，Bot 名使用账号登录名。
登录接口暂不可用时 smp 显示账号 ID，不使用三字母 `Bot` 占位名。
自定义回复序号从 3 开始，可不连续、可交换；`unity` 中的模板必须先导入 bot。

## 设置与数据

所有 global 操作只影响当前 bot。全局开关先于群开关；任一个关闭即恢复 Core 原始回复。
全局回复只影响没有群文件的群及私聊。本群第一次修改回复或开关后创建群文件，
记录当时的回复序号及独立开关，之后保留本群设置。
首次安装全局开关开启，默认序号 1；未单独设置的群默认开启并继承全局。
本插件不遵循 OlivaDiceCore 的群链；各群的回复选择与开关独立，不沿群链同步或继承。
群 hash 直接使用 Core 的消息群标识与 `getUserHash()` 实现，配置按 bot_hash 分目录保存。

```text
plugin/data/MultiCustomSwitch/
├── unity/                         # 仅模板，无自定义序号
│   └── 回复名.json
└── <bot_hash>/
    ├── config.json                # {"reply_model": 1, "enabled": true}
    ├── custom_list.json           # {"3": "回复名", "7": "另一套回复"}
    ├── 回复名.json                # 普通 Core 回复对象，可只含修改项
    └── group/
        └── <group_hash>.json      # {"reply_model": 3, "enabled": true}
```

default、recover_model 不在插件目录另存副本，直接使用：

```text
plugin/data/OlivaDice/<bot_hash>/console/customReply.json
plugin/data/OlivaDice/<bot_hash>/console/recover_model.json
```

默认回复基于 Core `msgCustomManager.py` 的 `getDictStrCustomDefault()`；自定义文件缺失的键补 smp。
修改状态参照 WebUI `service.replies()` 的文本比较；恢复模块列表参照 `gui_parity.recover_modules()`，
按顺序组合已加载模块的默认回复。unity 可选择 bot 的恢复模块作比较基线。

两个界面支持复制新建、逐项编辑、已修改筛选、未保存提示、改名、改序号、导入导出、
JSON 链接下载、跨 bot / unity 导入及同名三选一处理。smp 不允许覆盖；可创建为副本。
改名同步重命名 JSON 文件与列表记录，保留序号；改序号同步全部群文件及全局默认。

## 并发与兼容方式

`runtime.py` 在内存中包装宿主已有事件路由，并用 `ContextVar` 为每次插件回调选择独立回复字典。
不向磁盘修改 OlivOS、Core 或官方界面源码。官方管理事件、Core `.str` 与保存函数继续访问
原始字典；卸载时撤销包装并保留期间发生的原始回复修改。

所有插件文件操作共用一把 `RLock`。Core 回复管理函数、已加载 WebUI 的 `service.LOCK`、
NativeGUI 的文件上下文接入同一锁。模糊搜索等待、消息发送及网络下载不持文件锁。
线程锁只覆盖本 OlivOS 进程；外部编辑后需刷新，避免其他独立进程同时管理同一数据目录。

官方面板与本插件互改 default 时，刷新即可显示；本插件保存时检查回复版本，拒绝过期编辑。
如出现异常，可用 `.mcsglobaloff` 临时恢复 Core 原始回复。彻底回退可卸载本插件并重载；
保留插件数据目录即可之后恢复配置。覆盖用户模板前如需保留旧内容，请先导出 JSON。

## 本地验证与打包

测试放在本目录的 `MultiCustomSwitch_tests/`，不进入 OPK。测试加载本机真实 Core/WebUI 函数，
替换宿主 SDK、账号登录与消息出口，在独立临时目录验证数据及事件行为。
另有真实 Tk 编辑器操作、HTTP JSON 下载校验与 OPK 清理后的首次命令测试。
浏览器检查使用已有 Chrome/Selenium，在沙箱 iframe 中运行页面并提供合成宿主消息桥。
这些检查不代表已连接实际 QQ 机器人验证。

另使用 `D:\OlivOS` 的 Python、宿主加载器及已安装 OPK，在独立测试目录验证了实际账号列表、
托盘菜单打开 GUI、default 与官方面板双向保存、smp 只读，以及真实宿主 WebUI 登录、页面缓存和消息桥。
测试只读取账号 ID 与平台用于生成相同 bot_hash，不连接消息协议，不改动实例原有回复及群配置。

```powershell
Push-Location 实用/MultiCustomSwitch/MultiCustomSwitch_tests
python -m pytest . -q --confcutdir=.
Pop-Location
ruff check 实用/MultiCustomSwitch --config 实用/MultiCustomSwitch/.ruff.toml
python 实用/MultiCustomSwitch/tools/build_opk.py
```

打包脚本检查 `app.json` 为 UTF-8 无 BOM，并验证 WebUI 入口及独立 Markdown 帮助已入包。
生成同级 `MultiCustomSwitch.opk`；不自动部署、提交或推送。
