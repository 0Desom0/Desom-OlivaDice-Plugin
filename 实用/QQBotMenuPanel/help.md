# QQ 自定义菜单与指令面板

对照文档：[QQ 机器人开放平台 · 自定义菜单与指令面板](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/menu-panel/)

本插件不直接请求官方 HTTP，一律通过 OlivOS 的 qqGuildV2 `indeAPI`。

配置集成在 OlivOS 自带的 WebUI 中：

- 登录 OlivOS WebUI，在侧栏「插件页面」打开「QQ菜单与指令面板」
- 页面共用 OlivOS 的访问地址、端口和登录认证
- 需要支持 `webui_config` 和插件消息桥的 OlivOS 核心
- 插件不再启动独立网页服务，也不会自动打开浏览器

打开页面时会先拉取平台当前菜单和四个场景的指令面板。发送后会弹出成功几个、失败几个。

更新后重载插件，再从侧栏打开页面。旧版的保存钩子会停止独立服务并释放端口；若旧进程仍占用端口，重启 OlivOS。
原有草稿和骰主配置沿用，旧的 WebUI 开关、地址和端口字段不再生效。没有侧栏入口时请先更新 OlivOS 核心。

---

## 两种能力

### 自定义菜单 custom menu

展示在机器人单聊窗口底部，只支持 C2C（消息列表单聊）。

- 设置后对所有用户生效，不能按用户区分
- 最多 10 个菜单项，按列表顺序从左到右展示

### 指令面板 command panel

输入 `/` 或 `@机器人` 时拉起。

支持四个场景：

- `c2c` / 消息列表（单聊）
- `group` / QQ 群
- `channel` / QQ 频道文字子频道
- `dm` / 频道私信

限制：一个机器人最多 20 个指令面板，一个面板最多 20 个元素。

---

## 自定义菜单字段

| 字段 | 含义 |
| --- | --- |
| `items` | 菜单项列表。最多 10 个，从左到右展示 |
| `name` | 按钮名称。最多 10 个字符，一个中文汉字算 2 个字符 |
| `type` | `switch` 开关 / `send_message` 发送消息 / `link` 链接跳转 / `menu` 含子菜单的折叠项 |
| `send_message` | 仅 `send_message` 有效。用户点击后该文本会自动填入聊天输入框 |
| `link` | 仅 `link` 有效。必须以 `https://` 开头 |
| `switch.switch_id` | 仅 `switch` 有效。打开后消息 ext 会携带 `switch_id=1` |
| `switch.default` | 开关初始状态。`true` 默认打开，`false` 默认关闭 |
| `sub_menu_items` | 仅 `type=menu` 有效。最多 5 个，不能再嵌套。子项只允许 `send_message` 或 `link` |

子项 `name` 最多 14 个字符，约 7 个中文汉字。

---

## 指令面板字段

| 字段 | 含义 |
| --- | --- |
| `scope` | 生效场景：`c2c` / `group` / `channel` / `dm` |
| `target_type` | `all` 对该场景所有用户或群生效；`specific` 仅指定对象。频道和频道私信只能 `all` |
| `user_openids` | 仅 c2c 且 `specific`。一次最多 20 个 |
| `group_openids` | 仅 group 且 `specific`。一次最多 20 个 |
| `panel_id` | 平台返回的面板编号，修改 / 删除 / 查详情都要用它 |
| `panel.items` | 面板元素，最多 20 个 |
| `panel.items.name` | command 时点击后填入输入框；link 时只用于展示。最多 14 个字符 |
| `panel.items.desc` | 展示给用户的描述。最多 30 个字符 |
| `panel.items.type` | `command` 指令 / `link` 链接跳转 |
| `panel.items.only_admin` | `true` 时仅频道 / 群管理员可点击 |
| `panel.items.link` | 仅 `type=link` 有效 |
| `panel.remark` | 开发者备注，不对用户展示，最多 255 个字符 |
| `panel.version` | 面板版本号 |
| `op` | 修改关联对象：`add` 添加，`del` 移除 |

---

## WebUI 怎么用

1. **自定义菜单**：编辑底部按钮。右侧预览对照官方单聊快捷菜单：灰底、圆角胶囊、输入框、语音 / 图片 / 相机 / 表情 / 加号。
2. **指令面板**：顶部场景页签顺序与官方一致：QQ频道 / 频道私信 / QQ群 / 消息列表。右侧是灰色顶栏手机框。
3. **指令浏览**：把当前草稿里的每一条指令摊平搜索。无右侧预览时编辑区铺满。
4. **全局设置**：开关、只读的 OlivaDiceCore 全局骰主、本插件骰主。
5. 先看预览，确认无误后再点「确认发送到平台」。发送后会显示 OlivOS 返回的 `active` / HTTP 状态 / 错误 / `response`。

右侧预览可以点：

- **发送消息**：模拟填入输入框
- **链接**：把地址填进输入框预览
- **开关**：预览打开 / 关闭（打开为浅蓝底 + 蓝点）
- **子菜单**：展开二级项

---

## 权限与数据

- **全局骰主**：来自 OlivaDiceCore 的 `masterList`，只读
- **插件骰主**：保存在本插件 `bot_config.json` 的 `configured_master_list`，可在全局设置页编辑

数据目录：`plugin/data/QQBotMenuPanel/`
