# BiliBiliNotify 实施与验收记录

## 规格取舍

- 任务书禁止写任何 README，优先于文件树中的 `README.md`；插件独立说明见本报告。
- 命令采用计划书 §6 的 `.bili up sub <uid>`、`.bili up subs`、`.bili up live <uid> <on|off>`，不保留附录旧写法。
- 订阅者按段分消息发送而不截断；仅开播时可 @ 订阅者。前缀可增删任何单个非空白字符，可清空以停用命令。
- 原子写先用同目录临时文件更新 `.bak`，再原子替换主文件；备份步骤不会让主文件短暂消失。已提交的内存快照随写入替换。
- WBI 签名的置换表采用任务书明确指定的本地 BiliShareInfo 源码；计划书 §8.6 列出的下标与该引用实现不一致。
- OlivOS 定时回调使用外层 `@staticmethod`；每个 Bot 的 `poll.max_concurrent` 独立生效，所有 Bot 共用最多 32 个工作槽和 256 个待处理任务。
- WebUI 的群登记与关联沿用现有 action：`save_group` 可只传 `sid`，`add_up` / `remove_up` / `toggle_up` 可选 `sid`。QQ 官方群仅可登记宿主识别到的群。

## 数据和部署

运行时依赖 OlivOS 与 `requests`；OlivaDiceCore 可选。需要宿主支持 `webui_config` 与 `scheduleAPI`。MIT 许可。

- `plugin/data/BiliBiliNotify/global.json`：全局配置，面板只显示凭据配置状态。
- `plugin/data/BiliBiliNotify/accounts/<bot_hash>/`：机器人账号配置、主播和群数据。
- QQ 官方群的临时封面位于 `data/images/BiliBiliNotify/covers/`，发送结束后清理。频道不响应命令、不接收推送。
- 安装时将源码目录打为 OPK，`app.json` 位于压缩包根，文件名为 `BiliBiliNotify.opk`。本任务不部署、不启动或重载宿主。

入门：在群内执行 `.bili up add <UID>`（需要管理权限），成员用 `.bili up sub <UID>` 接收开播提醒。群开关用 `.bili push <live|dynamic|video> <on|off>`，主播检测开关用 `.bili up <live|dynamic|video> <UID> <on|off>`，全量命令见 `.bili help`。

## 文件清单

| 文件 | 行数 |
|---|---:|
| `LICENSE` | 21 |
| `RUN_REPORT.md` | 193 |
| `__init__.py` | 1 |
| `app.json` | 30 |
| `bili_api.py` | 415 |
| `config.py` | 43 |
| `function.py` | 190 |
| `main.py` | 38 |
| `message.py` | 223 |
| `message_custom.py` | 71 |
| `notify.py` | 756 |
| `sender.py` | 311 |
| `store.py` | 180 |
| `tests/fake_bili.py` | 43 |
| `tests/selftest.py` | 287 |
| `utils.py` | 440 |
| `webui.py` | 503 |
| `webui/index.html` | 1272 |

## 任务书 §7：四条命令的实际输出

在插件目录运行；`./*.py` 和 `.` 分别展开为插件目录的 Python 源文件及插件目录。`$ …` 为实际命令，`[exit …]` 由采集脚本印出，之间是未改写的命令输出。编译和 flake8 成功时自身无输出。

```text
$ py -3.12 -m py_compile ./*.py
[exit 0]

$ py -3.12 -m flake8 --max-line-length=120 .
[exit 0]

$ py -3.12 tests/selftest.py
[PASS] 命令解析
[PASS] UID 两级绑定与群订阅
[PASS] 权限
[PASS] 存储原子性与损坏归档
[PASS] 直播状态机
[PASS] 动态去重及过滤
[PASS] 视频去重
[PASS] @全体配额
[PASS] @订阅者去重与分段
[PASS] 首图选择
[PASS] 三重开关真值表
[PASS] 清单与文件结构
全部通过 (12/12)
[exit 0]

$ python -c "print(open('app.json','rb').read(1))"
b'{'
[exit 0]
```

初次验收发现模板正则常量漏移植，并有 flake8 样式错误；已修复。首次执行的原始命令输出如下：

<details>
<summary>首次执行</summary>

```text
$ py -3.12 -m py_compile ./*.py
[exit 0]

$ py -3.12 -m flake8 --max-line-length=120 .
.\notify.py:204:41: E128 continuation line under-indented for visual indent
.\notify.py:460:33: E127 continuation line over-indented for visual indent
.\utils.py:1:1: F401 're' imported but unused
.\utils.py:13:1: E303 too many blank lines (3)
.\utils.py:37:1: E303 too many blank lines (3)
.\utils.py:61:1: E303 too many blank lines (3)
.\utils.py:128:25: F821 undefined name 'reply_segment_pattern'
.\utils.py:255:22: F821 undefined name 'at_segment_pattern'
.\utils.py:372:1: E303 too many blank lines (3)
.\webui.py:127:121: E501 line too long (121 > 120 characters)
.\webui.py:278:121: E501 line too long (121 > 120 characters)
[exit 1]

$ py -3.12 tests/selftest.py
[FAIL] 命令解析
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 87, in test_commands
    self.assertIn(f'{prefix}bili up', replies[0])
AssertionError: '.bili up' not found in '处理失败，请稍后重试。'
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 87, in test_commands
    self.assertIn(f'{prefix}bili up', replies[0])
AssertionError: '.bili up' not found in '处理失败，请稍后重试。'
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 87, in test_commands
    self.assertIn(f'{prefix}bili up', replies[0])
AssertionError: '。bili up' not found in '处理失败，请稍后重试。'
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 87, in test_commands
    self.assertIn(f'{prefix}bili up', replies[0])
AssertionError: '。bili up' not found in '处理失败，请稍后重试。'
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 87, in test_commands
    self.assertIn(f'{prefix}bili up', replies[0])
AssertionError: '/bili up' not found in '处理失败，请稍后重试。'
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 87, in test_commands
    self.assertIn(f'{prefix}bili up', replies[0])
AssertionError: '/bili up' not found in '处理失败，请稍后重试。'
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 87, in test_commands
    self.assertIn(f'{prefix}bili up', replies[0])
AssertionError: '／bili up' not found in '处理失败，请稍后重试。'
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 87, in test_commands
    self.assertIn(f'{prefix}bili up', replies[0])
AssertionError: '／bili up' not found in '处理失败，请稍后重试。'
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 88, in test_commands
    self.assertFalse(self.command('bili help'))
AssertionError: ['处理失败，请稍后重试。'] is not false
[FAIL] UID 两级绑定与群订阅
Traceback (most recent call last):
  File "C:\Users\Administrator\projects\Desom-OlivaDice-Plugin\实用\BiliBiliNotify\tests\selftest.py", line 103, in test_binding
    self.assertIn('没查到 UID 1024', self.command('.bili up add 1024', 'owner')[0])
AssertionError: '没查到 UID 1024' not found in '处理失败，请稍后重试。'
[PASS] 权限
[PASS] 存储原子性与损坏归档
[PASS] 直播状态机
[PASS] 动态去重及过滤
[PASS] 视频去重
[PASS] @全体配额
[PASS] @订阅者去重与分段
[PASS] 首图选择
[PASS] 三重开关真值表
[PASS] 清单与文件结构
失败：命令解析、UID 两级绑定与群订阅
[exit 1]

$ python -c "print(open('app.json','rb').read(1))"
b'{'
[exit 0]
```

</details>

## 补充验收

- 抽取内联脚本，经管道交给 `node --check`；运行本地技能的 `package_opk.py . --check-only`，未生成压缩包。

```text
node --check: [exit 0]
[manifest] name=B站订阅推送 namespace=BiliBiliNotify version=1.0.0 message_mode=olivos_string
[ok] BiliBiliNotify looks packable (18 files)
package_opk: [exit 0]
```

- 模拟 OlivOS 生命周期，调用实际 tick 和工作池，B站接口和发送出口用桩：

```text
worker smoke: start -> exactly one push, quota=1; 3 x 412 -> red status + notice; 4th -> cooldown
```

- 真实 Edge 浏览器加载 sandbox iframe，使用与宿主相同的表单与脚本权限。`postMessage` 经本地测试桥进入实际 `handle_menu_event`，未启动 OlivOS：

```text
WebUI smoke: 5 tabs, bot polling save 10 -> 17 persisted, group subscriber persisted, credentials masked, desktop/mobile
```

## 已知限制

- 未请求 B 站、未部署到 OlivOS，也未向 OneBot 或 QQ 官方平台发送真消息。OneBot 有些适配器只回报入队，插件无法由此确认已送达。
- 计划书记载本机出口的动态和视频接口曾被 412 拦截；这次没有重测。刷新指纹重试仍失败时，`navnum` 只检测计数变化，不能补齐细节。面板的 Cookie 或网络出口需由使用者在部署环境确认。
- 推送游标与 @ 配额在发送前持久化，防止重载后重复群发或超额；发送失败有日志，不自动重播已经观察到的事件。
- 本机 PATH 未发现 Prettier，未安装工具。HTML 保留展开与关键中文注释，内联 JavaScript 已通过语法检查，且在 Edge 实际运行。
