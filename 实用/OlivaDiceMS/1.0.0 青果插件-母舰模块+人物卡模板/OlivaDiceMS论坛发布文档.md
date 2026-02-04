- **名称**：`母舰模块（Mothership）`
- **作者**：`Desom-fu`
- **版本**：`1.0.0`
- **兼容版本**：`理论兼容所有 3.0 以上的 OlivOS 版本`
- **平台**：`理论全平台可用（在 QQ 部署测试）`
- **前置插件**：`OlivaDiceCore（3.4.52版本及以上）`

---

## 简介

本插件为 OlivOS 提供 **母舰 TRPG（Mothership）** 规则支持：

- 人物作成（`.ms`）
- 属性/技能检定与豁免（`.rm`）
- 休息豁免（从模板豁免里取最低项）
- 死亡豁免（`.rm 死亡`）
- 惊恐检定与惊恐表（`.mp`）
- 压力自动增减（失败+1；休息成功按 D100 个位减压，且不会低于下限）

---

## 下载

- ### 插件包（注意解压！！！）：
[upl-file uuid=e73ea117-94b5-4215-b253-67ddc4754aac size=13kB]olivadicems.zip[/upl-file]

- ###人物卡模板（注意解压！！！）：
[upl-file uuid=99d17dfc-ffb4-4069-afc3-2aebee73eeb0 size=1kB]ms.zip[/upl-file]

---

## 注意事项

- 本插件依赖人物卡数据：建议先选择或创建人物卡，并确保模板为 `ms`。
- 为避免与其他规则插件命令冲突：
  - `.ms` 仅在“群模板为 ms”或“目标人物卡模板为 ms”时生效。
  - `.rm 休息` / `.rm 休息+...` 仅在母舰模板启用时生效。

---

## 命令总览（前缀：.ms / .rm / .mp）

### 人物作成
- `.ms`：生成 1 次人物作成
- `.ms [次数]`：生成多次（1-10）
- `.ms help`：查看帮助

### 检定 / 豁免（母舰）
- `.rm [技能名]`：按技能值进行检定（例如 `.rm 力量`）
- `.rm [数值]`：直接用数值检定（例如 `.rm 35`）
- `.rm [技能名]+[修正]`：支持表达式（例如 `.rm 力量+10` / `.rm 力量+1d6`）
- `.rm 休息`：休息豁免（自动使用模板豁免中**最低**的那一项）
- `.rm 休息+[修正]`：先取最差豁免值，再计算修正（例如 `.rm 休息+10`）
- `.rm 死亡`：死亡豁免（按母舰规则表输出后果，并在需要时自动写回生命值上限/生命值）

### 优势/劣势（b/p）
- `.rmb [检定]`：优势（等价 2D100kh）
- `.rmp [检定]`：劣势（等价 2D100kl）
- `.rmb2 [检定]`：优势 2（等价 3D100kh；数字越大骰子越多）
- `.rmp2 [检定]`：劣势 2（等价 3D100kl）

> 说明：b/p 会在掷骰表达式中使用 `kh/kl`，并在掷骰过程里显示 `[+] / [-]` 标记。

### 惊恐
- `.mp`：惊恐检定（1D20 对抗当前压力；失败则抽惊恐表）
- `.mp help`：查看帮助

---

## 规则与实现说明

### 压力惩罚
- 检定时若压力 $>20$，检定值会扣除 $压力-20$（最低为 0）。

### 压力变化
- 失败：压力 +1
- 休息成功：压力减少 `D100` 的个位数（即 `D100 % 10`），且不低于“压力下限”。
- 压力上限：超过上限时仍累计溢出（显示/记录行为与 core 对齐）。

### 休息豁免
- `休息` 不是人物卡技能；它代表“模板豁免列表中的最低值”。
- 因此 `.rm 休息+10` 的含义是：`(最差豁免值)+10`。

---

## 规则入口

- 使用 `.help rm` / `.help ms` / `.help mp` 查看对应指令帮助。

---

## 使用示例

```text
.ms
.ms 3

.rm 力量
.rm 力量+10
.rm 力量+1d6

.rm 休息
.rm 休息+10

.rmb 力量
.rmp2 力量

.mp
.rm 死亡
```

---

## 默认回复模板（dictStrCustom）

> 以下为本插件默认的回复模板键与内容（可在 OlivaDice 的自定义文本中按 key 覆盖）。

```python
dictStrCustom = {
    # ===== .ms =====
    'strMSGenerate': '[{tName}]的母舰人物作成：\n{tMSResult}',
    'strMSGenerateAtOther': '[{tUserName}]帮[{tName}]进行母舰人物作成：\n{tMSResult}',
    'strMSGenerateError': '母舰人物作成错误：{tResult}',

    # ===== .rm =====
    'strRMResult': '[{tName}]进行[{tRMTitle}]的[{tSkillValue}]检定: {tDiceProcess}{tSkillCheckReasult}{tStressChange}{tExtra}',
    'strRMResultAtOther': '[{tUserName}]帮[{tName}]进行[{tRMTitle}]的[{tSkillValue}]检定: {tDiceProcess}{tSkillCheckReasult}{tStressChange}{tExtra}',
    'strRMResultWithSkillName': '[{tName}]进行[{tRMTitle}]的[{tSkillName}:{tSkillValue}]检定: {tDiceProcess}{tSkillCheckReasult}{tStressChange}{tExtra}',
    'strRMResultWithSkillNameAtOther': '[{tUserName}]帮[{tName}]进行[{tRMTitle}]的[{tSkillName}:{tSkillValue}]检定: {tDiceProcess}{tSkillCheckReasult}{tStressChange}{tExtra}',
    'strRMDeathResult': '[{tName}]的死亡豁免：\n{tDiceProcess}\n{tDeathText}',
    'strRMDeathResultAtOther': '[{tUserName}]帮[{tName}]进行死亡豁免：\n{tDiceProcess}\n{tDeathText}',
    'strMSDeathSave0': '你失去意识。你会在 {2D10} 分钟内醒来，生命值上限永久-{1D5}。',
    'strMSDeathSave1to4': '你失去意识，生命垂危。若是不加干预，你会在 {1D5} 轮内死亡。',
    'strMSDeathSave5plus': '你已经死了。投一个新角色。',
    'strRMError': '母舰检定错误：{tResult}\n请使用.help rm查看帮助。',

    # ===== 压力变化 =====
    'strStressNone': '',
    'strStressAdd': '\n压力：{tStressOld}->{tStressNew}',
    'strStressAddMax': '\n压力：20->20 (已达上限，溢出值{tStressOverflow}点，将自动转化为检定减值)',
    'strStressReduce': '\n压力减少：{tStressOld}->{tStressNew}{tStressMinNote}',
    'strStressMinNote': ' (已达下限)',

    # ===== .mp =====
    'strMPResult': '[{tName}]的惊恐检定：{tDiceProcess} {tSkillCheckReasult}{tPanicEffect}',
    'strMPResultAtOther': '[{tUserName}]帮[{tName}]进行惊恐检定：{tDiceProcess} {tSkillCheckReasult}{tPanicEffect}',
    'strMPError': '惊恐检定错误：{tResult}\n请使用.help mp查看帮助。',
}
```

---

## 安装

1. 将 `OlivaDiceMS.opk` 放入 OlivOS 插件目录：`YourOlivOSPath/plugin/app`。
2. 将人物卡模板 `ms.json` 放入 `YourOlivOSPath/plugin/app/OlivaDice/unity/template`。
3. 重载插件。

---

## 更新日志

### 2026.2.4 v1.0.0

- 初版发布