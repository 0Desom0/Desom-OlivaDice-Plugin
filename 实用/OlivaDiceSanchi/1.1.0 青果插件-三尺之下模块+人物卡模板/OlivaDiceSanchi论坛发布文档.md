# 三尺之下模块（三尺之下跑团专用插件+人物卡模板）

- **名称**​：三尺之下模块
- ​**作者**​：Desom-fu
- ​**版本**​：1.1.0
- ​**兼容版本**​：理论兼容所有版本，但仅在最新版本测试过
- ​**平台**​：理论支持全平台（仅在 QQ 部署测试过）
- ​**操作系统**​：理论支持全系统（仅在 Windows Server 2019 上部署过）
- **前置插件**：OlivaDiceCore
- ​**三尺之下跑团官方群**：1035721236

---

## 注意事项

### 一定要使用最新版OlivaDice（3.4.52及以上版本），否则会无法使用！

- 下载完毕后建议打开`OlivaDice 设置面板`的自定义回复，在回复词中的`配置恢复模块`里面新增一行`OlivaDiceSanchi`（注意大小写要完全一致!）

---

## 下载

- ###### ​**插件包（记得解压！）** ​:
[upl-file uuid=875698dd-96fe-4117-bbfa-18e2ccfd9353 size=59kB]olivadicesanchi.zip[/upl-file]

- ###### **三尺之下青果专用人物卡模板（解压！）** :
[upl-file uuid=2ee5a623-1d8c-4d3a-a9ad-83712e9bedca size=2kB]sanchi.zip[/upl-file]

---

## 更新日志
## 2026.3.24 V1.1.0更新
- 投签追至最新规则书版本1.2

## 2025.11.11 V1.0.5更新
- 追至最新版本ovo构建版
- 更改构建版本

## 2025.11.6 v1.0.4更新：
- 修复tqav无法使用的bug
- 修复劣势骰有时没有添加硬币的bug
- ovo核心插件推进至最新构建版

## 2025.10.15 人物卡模板更新
- 如题

## 2025.10.13 v1.0.3更新：
- 修复一些掷骰bug，推进到最新构建版olivadicecore

## 2025.10.3 更新：
- 优化人物卡模板

## 2025.9.26 v1.0.2 更新：
- 上传最新构建的dice和gui
- 新增`.投签`功能
- 优化人物卡模板

## 2025.9.22 v1.0.1 更新：
- 向上兼容暂未更新的新版OlivOS-0.11.66(186)-玄铁古剑及以上的版本，向上兼容at回复，若不更新这个版本暂时可以无视，不过建议更新
- 优化人物卡模板

## 2025.9.20 v1.0.0发布：
- 三尺之下插件发布
- 支持完整的三尺之下铜钱卦系统
- 支持优势/劣势转换机制和铜钱调整
- 支持六爻摇卦功能，自动生成角色属性
- 包含64卦完整数据库和五行属性系统
- 支持三尺之下检定和对抗系统
- 自动寿数计算和属性波动检定

---

## 使用方法

1. 下载插件包并且解压后，将插件放到 `YourOlivOSPath\plugin\app` 这个路径里
2. 下载人物卡模板并且解压后，将人物卡模板放到 `YourOlivOSPath\plugin\data\OlivaDice\unity\extend\template` 这个路径里
3. 重载插件
4. 可在GUI里面自定义回复

---

## 命令详解

### .tq - 铜钱占卜
```
.tq(h)(b/p/u/d数字)(次数)#(铜钱数量或表达式)

参数说明：
- h：暗骰
- b/p数字：优势/劣势转换数量
- u/d数字：增加/减少铜钱数量
- 次数：投掷次数（最多10次）
- 铜钱数量：3-100枚，支持表达式和技能名

例子：
.tq 5        # 投掷5枚铜钱
.tq b2 火   # 2个优势转换，铜钱数量为火技能值
.tq u2 3#p1 水+5  # 增加2枚铜钱，3次投掷，1个劣势转换，每次投掷水+5枚铜钱
.tq d1 b1 4   # 减少1枚铜钱，1个优势转换，投掷4枚铜钱
```

### .tqa - 三尺之下检定
```
.tqa(h)(b/p/u/d数字)(属性表达式)#(难度表达式)(@其他人)

检定规则：
- 难度 < 属性：1个阳爻成功（简单检定）
- 难度 = 属性：2个阳爻成功（标准检定）  
- 难度 > 属性，差值≤2：3个阳爻成功（困难检定）
- 难度 > 属性，差值>2：3个阳爻成功且自动增加劣势（极难检定）

成功类型：
- 难度≤3：普通成功
- 难度4-6：困难成功
- 难度≥7：极难成功

参数说明：
- h：暗骰检定
- b/p数字：优势/劣势转换数量
- u/d数字：增加/减少铜钱数量（基础3枚）
- @其他人：代替他人进行检定（需要管理员及以上权限）

例子：
.tqa 火#5      # 火检定，难度5
.tqa b1 金+3#6 # 优势检定，金+3对抗难度6
.tqa u1 水#5 @张三  # 增加1枚铜钱，暗骰代骰检定
.tqa d1 b2 木#8  # 减少1枚铜钱，2个优势转换，木属性检定
```

### .tqav - 三尺之下对抗
```
.tqav(b/p/u/d数字)(自己属性)#(b/p/u/d数字)(对方属性)@对方

对抗规则：
- 双方各投3枚铜钱，计算阳爻数量
- 阳爻数量+属性值=最终对抗值
- 数值高者获胜，相等为平手

参数说明：
- b/p数字：为对应属性添加优势/劣势
- u/d数字：增加/减少铜钱数量（基础3枚）
- 必须@对方进行对抗
- 支持属性表达式计算

例子：
.tqav 火#土 @张三     # 自己火对抗张三土
.tqav b1 水+2#p1 金+1 @李四  # 优势水+2对抗李四劣势金+1
.tqav u1 火#d1 土 @王五  # 自己增加1枚铜钱，对方减少1枚铜钱
```

### .摇卦 - 命数摇卦
```
.摇卦

摇卦功能：
- 投掷六枚铜钱生成六十四卦之一
- 自动计算五行属性（包括波动属性检定）
- 显示卦象信息、角色特质、寿数等
- 提供角色创建参考

波动检定：
- 阴爻：取低值（如"2-3"取2）
- 阳爻：取高值（如"2-3"取3）

寿数计算：
- 乾为天卦：固定寿数3
- 坤为地卦：固定寿数1
- 其他卦：五行属性之和9→寿数1，10→寿数2，11→寿数3
```

### 6. 投签 - 命格投签
```
.投签

投签功能：
- 投掷三次三枚铜钱，分别决定：
  - 【凡尘记忆】-曾经的身份
  - 【横遭祸事】-发生的变故
  - 【执念生根】-如今的目标
- 投掷一次D3决定三官官职
- 最后投掷一次三枚铜钱决定吉点数量

凡尘记忆：
- 三阴爻：流离失所 - 居无定所之人
- 一阳爻：孤守一方 - 老旧建筑的看守人  
- 二阳爻：市井乡民 - 普通的城镇百姓/打工人
- 三阳爻：行业翘楚 - 专精某一领域的匠人

横遭祸事：
- 三阴爻：恶鬼缠身 - 被孤魂野鬼纠缠，危及性命
- 一阳爻：横遭祸事 - 亲朋好友被异灵迫害
- 二阳爻：家族蒙尘 - 家族祠堂突然出现异变
- 三阳爻：见证神迹 - 偶然之间看见了超越认知的存在

执念生根：
- 三阴爻：血海深仇 - 向异灵复仇，以牙还牙以血还血
- 一阳爻：明心证道 - 寻觅自身存在的意义
- 二阳爻：铲奸除恶 - 铲除所有害人的异灵
- 三阳爻：生死相托 - 完成亡者的遗愿和嘱托

三官官职：
- 1：天官 - 隶属于天官府
- 2：地官 - 隶属于地官府
- 3：水官 - 隶属于水官府

吉点数量：
- 投掷三枚铜钱，阳爻数量即为吉点数量
```

---

## 使用示例

### 1. 基础铜钱占卜

**命令**​：
```
.tq 5
```

**回复**​：
```
[张三]进行占卜，掷出5枚铜钱，结果为: 阴、阳、阴、阳、阳
阴: 2次；阳: 3次
```

### 2. 优势劣势转换

**命令**​：
```
.tq b2p1 火
```

**回复**​：
```
[张三]进行占卜，掷出火(3)枚铜钱，结果为: 阳(阴)、阳、阴(阳)、阴(劣势)
阴: 2次；阳: 2次（优势2/劣势1转换）
```

### 3. 三尺之下检定

**命令**​：
```
.tqa 火#15
```

**回复**​：
```
[张三]进行三尺之下检定
属性：火(3) 难度：15
困难检定（需要3个阳爻）
铜钱：阳、阴、阳、阳
阳爻：3个（需要3个）→困难成功
```

### 4. 对抗检定

**命令**​：
```
.tqav 火#土 @李四
```

**回复**​：
```
对抗检定：
张三：火(3)
铜钱：阳、阳、阴 → 阳爻2个
总计：2+3=5

李四：土(2)
铜钱：阳、阴、阴 → 阳爻1个
总计：1+2=3

结果：张三获胜
```

### 5. 摇卦

**命令**​：
```
.摇卦
```

**回复**​：
```
[张三] 摇卦占卜完成：
━━━ 卦 象 结 果 ━━━
第27卦 山雷颐
颐养天年，无饥无忧；顺势而为，修身养性。
━━━ 卦 象 属 性 ━━━
上卦：艮（☶）土
下卦：震（☳）木
━━━ 五 行 属 性 ━━━
金: 2；木: 3；水: 2；火: 2；土: 2
━━━ 波 动 检 定 ━━━
木为2-3，投掷结果为阳爻，取高值3
━━━ 角 色 信 息 ━━━
寿数：2
特殊能力：【养生】：你的恢复能力格外出众
角色特质：善于保养身体，懂得进退
姓名范例：颐真、养心
```

---

### 6. 投签

**命令**​：
```
.投签
```

**回复**​：
```
[李四] 的投签结果：
━━━ 因 果 执 念 ━━━
【凡世身份】- 加入解厄楼前赖以谋生的身份
投钱：阴、阳、阴
[法律相关]
身份子项：
1. 军伍相关
2. 警察
3. 律政相关（律师、法务顾问、普法人员）
4. 司法相关（法官、检察官、监狱相关）
【动机】- 成为寻缘客的原因
投钱：阳、阳、阴
偿还我的因果。
【执念】- 难以割舍的牵绊
投钱：阳、阳、阳
挥之不去的恐惧。
━━━ 三 官 官 职 ━━━
官职：水官 - 隶属于水官府
━━━ 吉 点 数 量 ━━━
投钱：阴、阳、阳
吉点：2个
```

## 注意事项

##### 数据录入方法：

1、将骰子拉入群聊后，请先使用[.set temp sanchi]，让本群套用三尺之下模板（只需输入一次，其他人无需再输入）
2、玩家可使用[.摇卦]命令自动生成初始角色属性，或手动设置五行属性值。
3、玩家输入[.sn]或者[.sn template]，改变名片格式。
4、玩家输入[.sn auto on]，让名片数据能够自动变化。

---

## 默认回复模板（dictStrCustom）

> 以下为本插件默认的回复模板键与内容（可在 OlivaDice 的自定义文本中按 key 覆盖）。

```python
dictStrCustom = {
    # .tq 铜钱卦占卜相关消息
    'strTQResult': '[{tName}]进行占卜[{tExprShow}]，掷出{tOriginalNumber}枚铜钱{tExtraCoinsText}，结果为: {tResult}\n阴: {tYinNumber}次；阳: {tYangNumber}次{tTransformText}',
    'strTQResultMore': '[{tName}]进行占卜[{tExprShow}]，掷了{tTime}次，每次掷出{tOriginalNumber}枚铜钱{tAllExtraCoinsText}，结果为: \n{tResult}\n总和次数：阴: {tYinNumber}次；阳: {tYangNumber}次{tBPText}',
    'strTQError': '三尺之下占卜错误: {tResult}\n请使用[.help r]查看掷骰帮助，或使用[.help onedice]查看先进的OneDice标准。\n请通过.help sanchi查看正确占卜格式',
    'strTQHide': '[{tName}]在群({tGroupId})中进行暗中占卜{tExprShow}：\n掷出{tOriginalNumber}枚铜钱{tExtraCoinsText}，结果为: {tResult}\n阴: {tYinNumber}次；阳: {tYangNumber}次{tTransformText}',
    'strTQHideShow': '[{tName}]进行暗中占卜',
    'strTQHideMore': '[{tName}]在群({tGroupId})中进行暗中占卜{tExprShow}：\n掷了{tTime}次，每次掷出{tOriginalNumber}枚铜钱{tAllExtraCoinsText}，结果为: \n{tResult}\n总和次数：阴: {tYinNumber}次；阳: {tYangNumber}次{tBPText}',
    'strTQHideShowMore': '[{tName}]进行暗中占卜',
    'strTQAtOther': '为[{tName}]进行占卜{tExprShow}，掷出{tOriginalNumber}枚铜钱{tExtraCoinsText}，结果为: {tResult}\n阴: {tYinNumber}次；阳: {tYangNumber}次{tTransformText}',
    'strTQAtOtherMore': '为[{tName}]进行占卜{tExprShow}，掷了{tTime}次，每次掷出{tOriginalNumber}枚铜钱{tAllExtraCoinsText}，结果为: \n{tResult}\n总和次数：阴: {tYinNumber}次；阳: {tYangNumber}次{tBPText}',
    'strTQHideAtOther': '[{tName}]在群({tGroupId})中的暗中占卜结果{tExprShow}：\n掷出{tOriginalNumber}枚铜钱{tExtraCoinsText}，结果为: {tResult}\n阴: {tYinNumber}次；阳: {tYangNumber}次{tTransformText}',
    'strTQHideShowAtOther': '为[{tName}]进行暗中占卜',
    'strTQHideAtOtherMore': '[{tName}]在群({tGroupId})中的暗中占卜结果{tExprShow}：\n掷了{tTime}次，每次掷出{tOriginalNumber}枚铜钱{tAllExtraCoinsText}，结果为: \n{tResult}\n总和次数：阴: {tYinNumber}次；阳: {tYangNumber}次{tBPText}',
    'strTQHideShowAtOtherMore': '为[{tName}]进行暗中占卜',
    
    # .tqa 三尺之下检定相关消息
    'strTQAResult': '[{tName}]进行三尺之下检定\n属性：{tAttrResult} 难度：{tDifficultyResult}\n{tLevelDesc}{tExtraDifficultyText}\n铜钱：{tCoinsResult}{tTransformText}\n阳爻：{tYangCount}个 {tSuccessText}',
    'strTQAHideShow': '[{tName}]进行了暗三尺之下检定',
    'strTQAHide': '于群[{tGroupId}]中[{tName}]进行三尺之下暗检定:\n属性：{tAttrResult} 难度：{tDifficultyResult}\n{tLevelDesc}{tExtraDifficultyText}\n铜钱：{tCoinsResult}{tTransformText}\n阳爻：{tYangCount}个 {tSuccessText}',
    'strTQAAtOther': '[{tUserName}]帮[{tName}]进行三尺之下检定:\n属性：{tAttrResult} 难度：{tDifficultyResult}\n{tLevelDesc}{tExtraDifficultyText}\n铜钱：{tCoinsResult}{tTransformText}\n阳爻：{tYangCount}个 {tSuccessText}',
    'strTQAHideShowAtOther': '[{tUserName}]帮[{tName}]进行了暗三尺之下检定',
    'strTQAHideAtOther': '于群[{tGroupId}]中[{tUserName}]帮[{tName}]进行三尺之下暗检定:\n属性：{tAttrResult} 难度：{tDifficultyResult}\n{tLevelDesc}{tExtraDifficultyText}\n铜钱：{tCoinsResult}{tTransformText}\n阳爻：{tYangCount}个 {tSuccessText}',
    'strTQAError': '三尺之下检定错误: {tResult}\n请使用[.help r]查看掷骰帮助，或使用[.help onedice]查看先进的OneDice标准。\n请通过.help sanchi查看正确检定格式',
    'strTQAFormatError': 'tqa命令格式错误，需要用#分隔属性和难度\n正确格式: .tqa 属性#难度',
    
    # .tqav 三尺之下对抗相关消息  
    'strTQAVResult': '对抗检定：\n{tName}：{tMyAttrResult}{tMyTransformText}\n铜钱：{tMyCoinsResult} → 阳爻{tMyYangCount}个\n总计：{tMyYangCount}+{tMyAttrValue}={tMyTotal}\n\n{tName01}：{tOtherAttrResult}{tOtherTransformText}\n铜钱：{tOtherCoinsResult} → 阳爻{tOtherYangCount}个\n总计：{tOtherYangCount}+{tOtherAttrValue}={tOtherTotal}\n\n结果：{tContestResult}',
    'strTQAVError': '三尺之下对抗错误: {tResult}\n请使用[.help r]查看掷骰帮助，或使用[.help onedice]查看先进的OneDice标准。\n请通过.help sanchi查看正确对抗格式',
    'strTQAVNoAtError': 'tqav命令必须@对方才能使用\n正确格式: .tqav 自己属性#对方属性 @对方',
    'strTQAVFormatError': 'tqav命令格式错误，需要用#分隔自己和对方的参数\n正确格式: .tqav 自己属性#对方属性 @对方',
    
    # .摇卦 命数卦象相关消息
    'strHexagramResult': '''[{tUserName}] 摇卦占卜完成：
━━━ 卦 象 结 果 ━━━
{tHexagramNum} {tHexagramName}
{tHexagramDesc}
━━━ 卦 象 属 性 ━━━
上卦：{tUpperBagua}
下卦：{tLowerBagua}
━━━ 五 行 属 性 ━━━
{tAttributes}
━━━ 波 动 检 定 ━━━
{tFluctuationResults}
━━━ 角 色 信 息 ━━━
寿数：{tLifespan}
特殊能力：{tSpecial}
角色特质：{tTraits}
姓名范例：{tNameExamples}''',
    
    'strHexagramError': '摇卦失败：{tError}\n请重新尝试摇卦命令',
    
    # 通用错误消息
    'strCoinRollError': '铜钱投掷出错',
    'strMyExprError': '自己的表达式解析错误: {tResult}',
    'strOtherExprError': '对方的表达式解析错误: {tResult}',
    'strAttrExprError': '属性表达式解析错误: {tResult}',
    'strDifficultyExprError': '难度表达式解析错误: {tResult}',
    
    # .投签 因果执念相关消息
    'strDivinationResult': '''[{tUserName}] 投签完成：
━━━ 因 果 执 念 ━━━
【凡世身份】- 加入解厄楼前赖以谋生的身份
{tPastIdentity}
【动机】- 成为寻缘客的原因
{tPastTragedy}
【执念】- 难以割舍的牵绊
{tCurrentGoal}
━━━ 三 官 官 职 ━━━
{tOfficialPosition}
━━━ 吉 点 数 量 ━━━
{tLuckyPoints}''',

    'strDivinationError': '投签失败：{tError}\n请重新尝试投签命令',

    # 投签各部分详细描述
    'strPastIdentity': '投钱：{tCoinsPastIdentity}\n{tPastIdentityDesc}',
    'strPastTragedy': '投钱：{tCoinsPastTragedy}\n{tPastTragedyDesc}',
    'strCurrentGoal': '投钱：{tCoinsCurrentGoal}\n{tCurrentGoalDesc}',
    'strOfficialPosition': '官职：{tOfficialPositionDesc}',
    'strLuckyPoints': '投钱：{tCoinsLuckyPoints}\n吉点：{tLuckyPointsCount}个'
}
```

## 回复模板说明
```python
dictStrCustomNote = {
    # .tq 铜钱卦占卜相关
    'strTQResult': '【.tq】指令\n占卜结果',
    'strTQResultMore': '【.tq】指令\n多次占卜结果',
    'strTQError': '【.tq】指令\n占卜错误',
    'strTQHide': '【.tq】指令\n暗骰占卜结果',
    'strTQHideShow': '【.tq】指令\n暗骰占卜提示',
    'strTQHideMore': '【.tq】指令\n暗骰多次占卜结果',
    'strTQHideShowMore': '【.tq】指令\n暗骰多次占卜提示',
    'strTQAtOther': '【.tq】指令\n代骰占卜结果',
    'strTQAtOtherMore': '【.tq】指令\n代骰多次占卜结果',
    'strTQHideAtOther': '【.tq】指令\n暗骰代骰占卜结果',
    'strTQHideShowAtOther': '【.tq】指令\n暗骰代骰占卜提示',
    'strTQHideAtOtherMore': '【.tq】指令\n暗骰代骰多次占卜结果',
    'strTQHideShowAtOtherMore': '【.tq】指令\n暗骰代骰多次占卜提示',
    
    # .tqa 三尺之下检定相关
    'strTQAResult': '【.tqa】指令\n三尺之下检定结果',
    'strTQAHideShow': '【.tqa】指令\n暗三尺之下检定提示',
    'strTQAHide': '【.tqa】指令\n暗三尺之下检定结果',
    'strTQAAtOther': '【.tqa】指令\n代骰三尺之下检定结果',
    'strTQAHideShowAtOther': '【.tqa】指令\n暗代骰三尺之下检定提示',
    'strTQAHideAtOther': '【.tqa】指令\n暗代骰三尺之下检定结果',
    'strTQAError': '【.tqa】指令\n三尺之下检定错误',
    'strTQAFormatError': '【.tqa】指令\n格式错误',
    
    # .tqav 三尺之下对抗相关
    'strTQAVResult': '【.tqav】指令\n三尺之下对抗结果',
    'strTQAVError': '【.tqav】指令\n三尺之下对抗错误',
    'strTQAVNoAtError': '【.tqav】指令\n未@对方错误',
    'strTQAVFormatError': '【.tqav】指令\n格式错误',
    
    # .摇卦 命数卦象相关
    'strHexagramResult': '【.摇卦】指令\n摇卦占卜结果显示',
    'strHexagramError': '【.摇卦】指令\n摇卦失败错误',

    # .投签 因果执念相关
    'strDivinationResult': '【.投签】指令\n投签结果显示',
    'strDivinationError': '【.投签】指令\n投签失败错误',
    'strPastIdentity': '【.投签】\n凡世身份部分',
    'strPastTragedy': '【.投签】\n动机部分',
    'strCurrentGoal': '【.投签】\n执念部分',
    'strOfficialPosition': '【.投签】\n三官官职部分',
    'strLuckyPoints': '【.投签】\n吉点数量部分',
    
    # 通用错误
    'strCoinRollError': '【三尺通用】\n铜钱投掷错误',
    'strMyExprError': '【三尺通用】\n自己表达式错误',
    'strOtherExprError': '【三尺通用】\n对方表达式错误',
    'strAttrExprError': '【三尺通用】\n属性表达式错误',
    'strDifficultyExprError': '【三尺通用】\n难度表达式错误'
}
```

---

## 常见问题

**Q：什么是优势/劣势转换？**
A：优势(b)将阴爻转为阳爻，劣势(p)将阳爻转为阴爻并增加额外铜钱。系统会智能处理转换顺序，确保不浪费优势。

**Q：摇卦生成的属性如何使用？**
A：摇卦会自动生成金、木、水、火、土五行属性，可直接用于tqa/tqav检定。波动属性会根据投掷结果自动确定最终值。

**Q：寿数是如何计算的？**
A：乾坤二卦有固定寿数，其他卦根据五行属性总和计算：9→1，10→2，11→3。

**Q：检定的成功等级有什么作用？**
A：根据难度数值显示不同成功类型：≤3为普通成功，4-6为困难成功，≥7为极难成功，帮助DM判断行动效果。

---

## 联系与反馈

如有问题或建议，请联系作者：Desom-fu

---

## 截图示例
![Image description](https://forum.olivos.run/assets/files/2025-09-20/1758353225-91152-image.png)
![Image description](https://forum.olivos.run/assets/files/2025-09-20/1758353419-774482-image.png)
![Image description](https://forum.olivos.run/assets/files/2025-09-20/1758353438-830279-image.png)
