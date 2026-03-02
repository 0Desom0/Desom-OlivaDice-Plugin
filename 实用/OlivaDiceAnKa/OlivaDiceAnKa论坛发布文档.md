- **名称**：`安价插件（OlivaDiceAnKa）`
- **作者**：`Desom-fu`
- **版本**：`1.0.0`
- **兼容版本**：`理论兼容所有 3.0 以上的 OlivOS 版本`
- **平台**：`理论全平台可用（在 QQ 部署测试）`
- **前置插件**：`OlivaDiceCore（建议 3.4.52 及以上）`

---

## 简介

本插件为 OlivOS 提供 **群聊安价管理** 功能，支持：

- 多安价并行管理（每群独立）
- 创建 / 切换 / 关闭当前活跃安价
- 选项增删、抽取（放回 / 不放回）
- 一次抽取多项（`draw` 多次）
- 抽取历史查询

---

## 下载

- ### 插件包（注意解压！！！）：
[upl-file uuid=请替换为实际上传后的uuid size=请填写实际大小]olivadiceanka.zip[/upl-file]

---

## 注意事项

- 本插件命令仅在 **群聊** 生效。
- 安价为“群 + 机器人”维度隔离，不同群互不影响。
- `on/create/new` 会将目标安价切换为当前活跃安价。
- `off` 仅关闭当前活跃状态（不删除安价）。
- `del/end` 会删除安价；`clr` 只清空选项不删除安价。
- `set` 的模糊切换支持推荐候选，按提示回复序号选择。

---

## 命令总览（前缀：`.anka` / `.安价` / `.ak`）

### 基础管理
- `.ak` / `.anka`：查看安价列表
- `.ak list`：查看安价列表
- `.ak on (安价名)` / `.ak create (安价名)` / `.ak new (安价名)`：创建或继续安价，并设为当前活跃
- `.ak off`：关闭当前活跃安价
- `.ak set [安价名]`：切换当前活跃安价（支持模糊推荐）
- `.ak del (安价名)` / `.ak end (安价名)`：删除安价

### 选项管理
- `.ak add (安价名) [选项内容]`：添加选项（可省略安价名，默认当前活跃）
- `.ak rm (安价名) [序号]`：按序号删除选项（从 1 开始）
- `.ak show (安价名)`：显示安价全部选项（可省略安价名，默认当前活跃）
- `.ak clr (安价名)`：清空安价选项（不删除安价）

### 抽取与历史
- `.ak draw (安价名) (次数) [不放回参数]`
  - 默认放回、默认 1 次
  - 次数范围：`1-100`
  - 不放回参数支持：`不放回 / nr / noreturn / remove / pop`
- `.ak his (安价名) (条数)` / `.ak 记录` / `.ak 历史`：查看抽取历史（默认 20，最大 100）

---

## 规则与实现说明

### 当前活跃安价
- 群内可以没有活跃安价。
- 无活跃安价时，`add/rm/clr/del/end/draw/show/his` 默认会提示“当前没有活跃安价”。
- 指定安价名时仍可对指定安价执行操作。

### `clr` 与 `del/end` 的区别
- `clr`：仅清空选项，不删除安价条目。
- `del/end`：删除安价条目本身。

### 多次抽取
- `draw` 支持一次多抽。
- 不放回模式下，抽中的选项会立即移除；若次数大于剩余选项数会报错。

---

## 规则入口

- 使用 `.help anka` / `.help 安价` / `.help ak` 查看帮助。

---

## 使用示例

```text
.ak on
.ak on 今日安价

.ak add 吃火锅
.ak add 今日安价 点奶茶

.ak show
.ak draw
.ak draw 3
.ak draw 今日安价 2 nr

.ak his
.ak his 今日安价 10

.ak clr 今日安价
.ak end 今日安价
```

---

## 默认回复模板（dictStrCustom）

> 插件支持通过自定义文本覆盖默认回复，键值可参考 [`dictStrCustom`](Desom-OlivaDice-Plugin/实用/OlivaDiceAnKa/msgCustom.py)。

常用键示例：

```python
dictStrCustom = {
    'strAnkaNoData': '本群暂无安价。你可以用 .anka create 创建。',
    'strAnkaNoActive': '当前没有活跃安价。你可以用 .anka on 开启一个。',
    'strAnkaListTitle': '本群安价列表：',
    'strAnkaListLine': '- {tAnkaName} (选项:{tAnkaCount}){tAnkaCurrent}{tAnkaActive}',

    'strAnkaCreateOn': '已创建/开启安价[{tAnkaName}]，并切换为当前安价。',
    'strAnkaOffSuccess': '已关闭当前活跃安价[{tAnkaName}]。',
    'strAnkaOffNoActive': '当前没有活跃安价可关闭。',
    'strAnkaSetUsage': '用法：.anka set [安价名字]',
    'strAnkaSetNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaSetRecommend': '请从推荐候选中选择要切换的安价\n{tSearchResult}',
    'strAnkaSetSuccess': '已切换当前安价为[{tAnkaName}]。',

    'strAnkaAddUsage': '用法：.anka add (安价名字) [选项内容]',
    'strAnkaOptionEmpty': '选项内容不能为空。',
    'strAnkaAddSuccess': '已向安价[{tAnkaName}]添加选项 #{tAnkaIndex}：{tAnkaOption}',

    'strAnkaRmUsage': '用法：.anka rm (安价名字) [第几个选项]',
    'strAnkaNotExist': '安价[{tAnkaName}]不存在。',
    'strAnkaNoOptionToRm': '安价[{tAnkaName}]没有可删除的选项。',
    'strAnkaRmIndexNotNumber': '删除序号必须是阿拉伯数字。',
    'strAnkaRmIndexOutOfRange': '序号超出范围，当前共有 {tAnkaCount} 个选项。',
    'strAnkaRmSuccess': '已从安价[{tAnkaName}]删除第{tAnkaIndex}个选项：{tAnkaOption}',

    'strAnkaEndNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaEndSuccess': '已删除安价[{tAnkaName}]。',
    'strAnkaClrSuccess': '已清空安价[{tAnkaName}]的全部选项。',

    'strAnkaDrawNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaNoOptionToDraw': '安价[{tAnkaName}]没有可抽取的选项。',
    'strAnkaDrawErrNoCount': '选项数量不足。',
    'strAnkaDrawErrOneDice': 'onedice异常：{tAnkaError}',
    'strAnkaDrawErrOneDiceResult': 'onedice结果异常。',
    'strAnkaDrawWithReturn': '安价[{tAnkaName}]抽取结果：#{tAnkaIndex} {tAnkaOption}',
    'strAnkaDrawNoReturn': '安价[{tAnkaName}]抽取结果（不放回）：#{tAnkaIndex} {tAnkaOption}\n已移除该选项，剩余 {tAnkaCount} 项。',
    'strAnkaDrawMultiTitle': '安价[{tAnkaName}]抽取结果（共{tAnkaDrawCount}次）：',
    'strAnkaDrawMultiLine': '{tAnkaHistoryNo}. #{tAnkaIndex} {tAnkaOption}',
    'strAnkaDrawMultiTailNoReturn': '已移除 {tAnkaDrawCount} 项，剩余 {tAnkaCount} 项。',

    'strAnkaHistoryUsage': '用法：.anka history (安价名字) (条数)',
    'strAnkaHistoryNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaNoHistory': '安价[{tAnkaName}]暂无抽取历史。',
    'strAnkaHistoryTitle': '安价[{tAnkaName}]抽取历史（显示最近{tAnkaHistoryShow}条 / 共{tAnkaHistoryTotal}条）：',
    'strAnkaHistoryLine': '{tAnkaHistoryNo}. [{tAnkaHistoryTime}] ({tAnkaHistoryMode}) #{tAnkaIndex} {tAnkaOption} - {tAnkaHistoryUser}',

    'strAnkaShowNotFound': '未找到安价[{tAnkaQueryName}]。',
    'strAnkaNoOptionToShow': '安价[{tAnkaName}]当前没有选项。',
    'strAnkaShowTitle': '安价[{tAnkaName}]选项列表（共{tAnkaCount}项）：',
    'strAnkaShowLine': '{tAnkaIndex}. {tAnkaOption}',

    'strAnkaListEmpty': '本群暂无安价。',
    'strAnkaUnknownSubCommand': '未知子命令。可用：create/on, off, set, add, rm, del/end/clr, draw, show, history, list'
}
```

---

## 安装

1. 将 `OlivaDiceAnKa.opk` 放入 OlivOS 插件目录：`YourOlivOSPath/plugin/app`。
2. 重载插件。

---

## 更新日志

### 2026.3.2 v1.0.0

- 首版论坛发布
