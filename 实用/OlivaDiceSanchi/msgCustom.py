# -*- encoding: utf-8 -*-
'''
_______________________    _________________________________________
__  __ \__  /____  _/_ |  / /__    |__  __ \___  _/_  ____/__  ____/
_  / / /_  /  __  / __ | / /__  /| |_  / / /__  / _  /    __  __/   
/ /_/ /_  /____/ /  __ |/ / _  ___ |  /_/ /__/ /  / /___  _  /___   
\____/ /_____/___/  _____/  /_/  |_/_____/ /___/  \____/  /_____/   

@File      :   msgCustom.py
@Author    :   lunzhiPenxil仑质
@Contact   :   lunzhipenxil@gmail.com
@License   :   AGPL
@Copyright :   (C) 2020-2021, OlivOS-Team
@Desc      :   None
'''

import OlivOS
import OlivaDiceCore
import OlivaDiceSanchi

dictStrCustomDict = {}

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

dictStrConst = {
}

dictGValue = {
}

dictTValue = {
    # .tq 占卜相关
    'tExprShow': '',
    'tOriginalNumber': '3',
    'tNumber': '3',
    'tTime': '1',
    'tResult': '',
    'tYinNumber': '0',
    'tYangNumber': '0',
    'tTransformText': '',
    'tExtraCoinsText': '',
    'tAllExtraCoinsText': '',
    'tBPText': '',
    
    # .tqa 检定相关
    'tAttrResult': '0',
    'tDifficultyResult': '0',
    'tCoinsResult': '阴、阴、阴',
    'tYangCount': '0',
    'tRequiredYang': '1',
    'tLevelDesc': '检定',
    'tExtraDifficultyText': '',
    'tSuccessText': '失败',
    
    # .tqav 对抗相关
    'tMyAttrResult': '0',
    'tMyAttrValue': '0',
    'tMyCoinsResult': '阴、阴、阴',
    'tMyYangCount': '0',
    'tMyTotal': '0',
    'tMyTransformText': '',
    'tOtherAttrResult': '0',
    'tOtherAttrValue': '0',
    'tOtherCoinsResult': '阴、阴、阴',
    'tOtherYangCount': '0',
    'tOtherTotal': '0',
    'tOtherTransformText': '',
    'tContestResult': '平手',
    
    # .摇卦 命数卦象相关
    'tHexagramNum': '',
    'tHexagramName': '',
    'tHexagramDesc': '',
    'tUpperBagua': '',
    'tLowerBagua': '', 
    'tCoinResults': '',
    'tAttributes': '',
    'tFluctuationResults': '',
    'tLifespan': '2',
    'tSpecial': '',
    'tTraits': '',
    'tNameExamples': '',
    
    # 错误处理
    'tRollPara': '',
    'tResult': '',
    
    # .投签 因果执念相关
    'tPastIdentity': '',
    'tPastIdentityDesc': '',
    'tCoinsPastIdentity': '',
    'tPastTragedy': '',
    'tPastTragedyDesc': '',
    'tCoinsPastTragedy': '',
    'tCurrentGoal': '',
    'tCurrentGoalDesc': '',
    'tCoinsCurrentGoal': '',
    'tOfficialPosition': '',
    'tOfficialPositionDesc': '',
    'tLuckyPoints': '',
    'tCoinsLuckyPoints': '',
    'tLuckyPointsCount': '',
}

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

dictHelpDocTemp = {
    'sanchi': '''【三尺之下】

本系统包含以下功能模块：
• .tq - 铜钱占卜
• .tqa - 三尺之下检定  
• .tqav - 三尺之下对抗
• .摇卦 - 命数摇卦
• .投签 - 因果执念投签

详细使用方法请输入：
.help tq    - 查看铜钱占卜详情
.help tqa   - 查看检定系统详情
.help tqav  - 查看对抗系统详情
.help 摇卦  - 查看命数摇卦详情
.help 投签  - 查看因果执念投签详情
.help sanchist - 查看三尺之下跑团数据录入帮助''',

    'tq': '''【三尺之下铜钱占卜】
.tq(h)(b/p/u/d数字)(次数)#(铜钱数量或表达式)

参数说明：
- h：暗骰
- b/p数字：优势/劣势转换数量，二者会先相互抵消
- u/d数字：增加/减少铜钱数量
- 次数：投掷次数（最多10次）
- 铜钱数量：3-100枚，支持表达式和技能名

例子：
.tq 5        # 投掷5枚铜钱
.tq b2 火   # 2个优势转换，铜钱数量为火技能值
.tq u2 3#p1 水+5  # 增加2枚铜钱，3次投掷，1个劣势转换，每次投掷水+5枚铜钱
.tq d1 b1 4   # 减少1枚铜钱，1个优势转换，投掷4枚铜钱

占卜结果：
- 每枚铜钱显示阴爻或阳爻
- 统计阴爻和阳爻总数
- 支持优势/劣势转换和铜钱数量调整''',

    'tqa': '''【三尺之下检定】
.tqa(h)(b/p/u/d数字)(属性表达式)#(难度表达式)(@其他人)

检定规则：
- 难度 < 属性：1个阳爻成功（简单检定）
- 难度 = 属性：2个阳爻成功（标准检定）  
- 难度 > 属性，差值≤2：3个阳爻成功（困难检定）
- 难度 > 属性，差值>2：3个阳爻成功且自动增加劣势（极难检定）

参数说明：
- h：暗骰检定
- b/p数字：优势/劣势转换数量，二者会先相互抵消
- u/d数字：增加/减少铜钱数量（基础3枚）
- @其他人：代替他人进行检定（需要管理员及以上权限）

例子：
.tqa 火#5      # 火检定，难度5
.tqa b1 金+3#6 # 优势检定，金+3对抗难度6
.tqa u1 水#5 @张三  # 增加1枚铜钱，暗骰代骰检定
.tqa d1 b2 木#8  # 减少1枚铜钱，2个优势转换，木属性检定''',

    'tqav': '''【三尺之下对抗】
.tqav(b/p/u/d数字)(自己属性)#(b/p/u/d数字)(对方属性)@对方

对抗规则：
- 双方各投3枚铜钱，计算阳爻数量
- 阳爻数量+属性值=最终对抗值
- 数值高者获胜，相等为平手

参数说明：
- b/p数字：为对应属性添加优势/劣势，二者会先相互抵消
- u/d数字：增加/减少铜钱数量（基础3枚）
- 必须@对方进行对抗
- 支持属性表达式计算

例子：
.tqav 火#土 @张三     # 自己火对抗张三土
.tqav b1 水+2#p1 金+1 @李四  # 优势水+2对抗李四劣势金+1
.tqav u1 火#d1 土 @王五  # 自己增加1枚铜钱，对方减少1枚铜钱

对抗显示：
- 双方属性值和铜钱结果
- 详细的计算过程
- 最终胜负结果''',

    '摇卦': '''【命数摇卦】
.摇卦

摇卦功能：
- 投掷六枚铜钱生成六十四卦之一
- 自动计算五行属性（金、木、水、火、土）
- 自动进行波动属性检定（如"2-3"格式属性）
- 显示完整的卦象信息和角色特质

卦象信息包含：
- 卦名和卦象描述
- 上卦下卦的八卦组合
- 五行属性分配
- 角色寿数和特殊能力
- 性格特质和姓名范例

波动检定：
- 阴爻：取低值（如"2-3"取2）
- 阳爻：取高值（如"2-3"取3）''',

    '投签': '''【因果执念投签】
.投签

投签功能：
- 投掷三次三枚铜钱，分别决定：
  - 【凡世身份】-加入解厄楼前赖以谋生的身份
  - 【动机】-成为寻缘客的原因
  - 【执念】-难以割舍的牵绊
- 投掷一次d3决定三官官职
- 最后投掷一次三枚铜钱决定吉点数量

投签规则：
- 每一部分都投掷三枚铜钱
- 正面视为“正/阳”，反面视为“反/阴”
- 按三枚铜钱的先后顺序对应规则书中的八种结果（同时等同于D8的1-8）

凡世身份：
- 正正正 / D8=1：知识阶层
- 正正反 / D8=2：土地依存
- 正反正 / D8=3：技术人员
- 正反反 / D8=4：商业贸易
- 反正正 / D8=5：医药相关
- 反正反 / D8=6：法律相关
- 反反正 / D8=7：艺术相关
- 反反反 / D8=8：旁门九流

动机：
- 正正正 / D8=1：这是我的责任。
- 正正反 / D8=2：偿还我的因果。
- 正反正 / D8=3：我受够了被动的恐惧。
- 正反反 / D8=4：这是我毕生追求的“真相”。
- 反正正 / D8=5：为了自保。
- 反正反 / D8=6：拯救所爱之人。
- 反反正 / D8=7：这将赋予我生命新的意义与方向。
- 反反反 / D8=8：我的才能能更广阔的舞台上发挥作用。

执念：
- 正正正 / D8=1：挥之不去的恐惧。
- 正正反 / D8=2：对力量的贪恋。
- 正反正 / D8=3：拯救的妄欲。
- 正反反 / D8=4：过度的共情。
- 反正正 / D8=5：无法忘怀的仇恨。
- 反正反 / D8=6：职业惯性。
- 反反正 / D8=7：（肉体或心灵上）的成瘾性慰藉。
- 反反反 / D8=8：未竟的诺言。

三官官职：
- 1：天官 - 隶属于天官府
- 2：地官 - 隶属于地官府
- 3：水官 - 隶属于水官府

吉点数量：
- 投掷三枚铜钱，阳爻数量即为吉点数量''',

    'sanchist': '''【三尺之下跑团数据录入帮助文档】
1、将骰子拉入群聊后，请先使用[.set temp sanchi]，让本群套用三尺之下模板（只需输入一次，其他人无需再输入）
2、玩家在填写完角色卡并审核通过后，将.st数据复制粘贴，输入群内，这样就完成了基础数据的录入。
3、玩家输入[.sn]或者[.sn template]，改变名片格式。
4、玩家输入[.sn auto on]，让名片数据能够自动变化。
''',
    '三尺': '&sanchi',
    '三尺之下': '&sanchi'
}
