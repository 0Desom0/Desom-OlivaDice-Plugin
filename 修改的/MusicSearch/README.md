# 点歌插件 (MusicSearch)

基于第三方网易云音乐 API 的 OlivOS 点歌插件，支持搜索歌曲并返回 CQ 码音乐消息。站内已经有人做了程心包的点歌功能了，我只是想写一个插件版的练练手。程心包版本指路：[【程心包】网易云点歌](https://forum.olivos.run/d/372)。***以及这个文档大部分也是AI生成的，凑合看吧(/- v-)/***

## 功能特性

- **快速点歌**：通过简单的指令搜索并点歌
- **网易云音乐**：基于网易云音乐 API，曲库丰富
- **智能返回**：自动取搜索结果的第一条
- **完善的错误处理**：友好的错误提示
- **调试支持**：可配置的调试日志输出

## 安装方法

1. 将 `MusicSearch` 文件夹复制到 OlivOS 的 `plugin/app/` 目录下
2. 重启 OlivOS 即可使用

## 使用方法

### 基本用法

在群聊或私聊中发送以下格式的消息：

```
.点歌歌曲名称
。点歌歌曲名称
```

例如：
```
.点歌爱不会绝迹
。点歌晴天
```

### 返回结果

qqGuildv2（QQ 官方机器人）返回原生 Markdown 消息：顶部显示 `picurl` 提供的封面，读取图片头中的真实宽高填入 Markdown，不固定正方形、不缩放或裁剪。读取尺寸失败时省略宽高声明，由客户端按自然尺寸显示；缺少有效封面地址时仅展示文字。下方显示歌名，信息区保留全部字段标签：歌手与时长同一行，专辑和歌曲 ID 各一行，字段间不加空段落。专辑名与歌名相同时仍保留，缺失字段显示“未知”。“打开链接”按钮跳转到歌曲页面，所有人均可点击。付费歌曲会附带播放权限提示。

### 发送音乐语音（QQ 群 / QQ 私聊）

“发送音乐”按钮先按歌曲 ID 重新获取有效音频链接，将音乐下载到本机临时目录，再通过 OlivOS 的本地 `record` 消息上传语音（`file_type=3`），并以 `media.file_info` 发送。不会把远程音频链接直接交给 QQ 拉取。支持 MP3、OGG、WAV 和 SILK 原始音频，不额外转码；完成或失败后清理临时文件。

当前青果源码支持 `Event.button_click`：按钮为回调类型，SDK 自动应答，插件使用此次互动的 `event_id` 被动回复。同一按钮同时只运行一次处理过程，期间所有用户的重复点击直接忽略。只有音乐语音成功发送后，按钮才永久失效；下载、上传或发送失败会释放占用，允许重新点击。成功状态保存在 `plugin/data/MusicSearch/voice_buttons.sqlite3`，重载或重启后仍生效。重新点歌生成的新按钮可独立使用。不支持该事件的旧宿主改为指令按钮，点击自动发送 `.点歌语音 歌曲ID`。指令按钮和手动指令不限制重复使用，例如 `.点歌语音 569870607`。

语音和点歌共用全局、本群及 OlivaDiceCore 开关。歌曲无可下载链接（如无付费权限）会提示原因；下载上限 20 MiB，避免 QQ 将语音降级为文件，下载总等待上限约 60 秒。频道与频道私信暂不展示语音按钮，因为当前 OlivOS 对应发送链路未实现语音上传。

官方依据：[消息按钮](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/trans/msg-btn.html)、[按钮回调事件](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/interaction_create.html)、[富媒体消息](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/rich-media.html)、[群聊上传](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_files.post.html)。

封面尺寸识别复用 OlivOS 已有的 Pillow 依赖，每次最多读取 256 KiB 图片头，请求超时为 5 秒。

时长和专辑由网易云歌曲详情接口补充，详情请求失败时仍展示搜索结果，时长显示“未知”。Markdown 接口不可用或发送失败时，改为文字信息和歌曲链接。QQ 群、QQ 私聊、频道和频道私信均按当前事件发送。

其他已支持的平台继续返回 CQ 码音乐消息，包含以下信息：
- 歌曲标题
- 歌手信息
- 歌曲封面
- 跳转链接
- 音频链接

### 错误提示

- **未输入歌曲名称**：提示"请输入歌曲名称，例如：【.点歌爱不会绝迹】或【。点歌爱不会绝迹】"
- **搜索失败**：提示"搜索失败，请稍后重试"或具体错误信息
- **未查询到对应歌曲**：提示"未查询到对应歌曲"

## 配置说明

插件配置文件位于 `plugin/data/MusicSearch/data/config.json`，首次运行会自动创建。

### 配置项

```json
{
  "enabled": true,
  "debug_mode": false
}
```

- **enabled**：是否启用插件（true/false）
- **debug_mode**：是否开启调试模式（true/false）

### 配置热更新

修改配置文件后，无需重启 OlivOS，下次使用时会自动加载新配置。

## 技术细节

### API 接口

使用第三方 API：`https://oiapi.net/api/Music_163`

qqGuildv2 额外使用 `https://music.163.com/api/song/detail/` 获取歌曲详情（`id` 与 `ids` 参数），其 `duration` 字段单位为毫秒。无需新增配置项或第三方依赖；OlivOS 需支持 `indeAPI.create_markdown_message`。

### 请求参数

- **name**：歌曲名称（必填）

### 返回格式

```json
{
  "code": 0,
  "message": "搜索成功",
  "data": [
    {
      "name": "歌曲名称",
      "picurl": "封面图片URL",
      "id": 歌曲ID,
      "jumpurl": "跳转链接",
      "singers": [
        {
          "name": "歌手名称",
          "id": 歌手ID
        }
      ]
    }
  ]
}
```

### CQ 码格式

```
[CQ:music,type=163,url=跳转链接,audio=音频链接,title=歌曲名,image=封面图,content=歌手]
```

## 日志输出

插件使用 ">>>" 格式的日志记录，便于调试和追踪：

- `>>> 点歌插件已初始化` - 插件初始化成功
- `>>> 正在搜索歌曲: xxx` - 开始搜索歌曲
- `>>> 成功返回歌曲: xxx` - 成功返回歌曲
- `>>> 未查询到对应歌曲: xxx` - 未找到歌曲
- `>>> [调试] xxx` - 调试信息（需开启 debug_mode）

## 文件结构

```
MusicSearch/
├── app.json          # 插件配置文件
├── __init__.py       # 插件入口
├── load.py           # 配置加载模块
├── main.py           # 核心功能模块
├── voice.py          # 按钮回调/指令触发的音乐下载与语音发送
└── README.md         # 说明文档
```

## 作者

👤 夏里白雪(XiaLiBaiXue@outlook.com)

## 版本

v0.1.0

## 许可证

本插件遵循 OlivOS 插件开发规范。
