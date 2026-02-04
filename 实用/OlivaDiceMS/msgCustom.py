# -*- encoding: utf-8 -*-
import OlivOS
import OlivaDiceCore
import OlivaDiceMS


dictStrCustomDict = {}


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


dictStrConst = {
    'MS_PANIC_TABLE': [
        '肾上腺素激增：之后 {2D10} 分钟内所有投骰带有 [+]，压力减少 {1D5}。',
        '紧张：获得 1 压力。',
        '神经质：获得 1 压力，所有近距乘组获得 2 压力。',
        '不知所措：之后 {1D10} 分钟内所有投骰带有 [-]，压力下限提升 1。',
        '懦弱：获得一项新状态：必须通过一次恐惧豁免才能参与暴力行为，否则就会逃跑。',
        '受惊：获得一项新状态：恐惧症：在遭遇恐惧源时得要通过一次恐惧豁免 [-]，否则获得 1D5 压力。',
        '梦魇：获得一项新状态：难以安睡，休息豁免带有 [-]。',
        '失去自信：获得一项新状态：选择一项技能，失去此技能的奖励。',
        '泄气：获得一项新状态：只要有近距乘员豁免失败，获得 1 压力。',
        '时日无多：获得一项新状态：感觉自己受到诅咒，厄运缠身。所有关键成功变成关键失败。',
        '多疑：之后一周内，每当有人加入你的团体（即使他们只离开了很短的时间），通过一次恐惧豁免，否则获得 1 压力。',
        '作祟：获得一项新状态：有些东西开始会在晚上造访，包括梦中或视线边缘，很快对方就会开始提出要求。',
        '作死：之后 24 小时里，只要遭遇陌生人或是已知敌人，你必须通过一次理智豁免，否则立刻发起攻击。',
        '预知异象：角色立刻体验一次关于将临恐怖或是可怖事件的激烈幻觉/异象。压力下限提升 +2。',
        '紧张症：{2D10} 分钟里变得毫无反应，呆若木鸡。减少 {1D10} 压力。',
        '狂暴：之后 {1D10} 小时内，所有伤害投骰带有 [+]。所有乘组获得 1 压力。',
        '沦陷：获得一项新状态：进行一次带有 [-] 的惊恐检定。',
        '复合问题：按照此惊恐表投骰两次。压力下限提升 1。',
        '心脏病发/短路（仿生人）：损伤上限降低 1。{1D10} 小时内所有投骰带有 [-]。压力下限提升 1。',
        '退场：投个新角色来参加游戏。'
    ]
}


dictGValue = {
}


dictTValue = {
    'tMSResult': '',
    'tRMTitle': '检定',
    'tDiceProcess': '',
    'tSkillName': '',
    'tSkillValue': '0',
    'tSkillShow': '',
    'tSkillCheckReasult': '',
    'tStressChange': '',
    'tExtra': '',
    'tResult': '',

    'tStressOld': '0',
    'tStressNew': '0',
    'tStressOverflow': '0',
    'tStressMinNote': '',

    'tD10Result': '0',
    'tDeathText': '',

    'tD20Result': '0',
    'tStressShow': '0',
    'tPanicEffect': '',
}


dictStrCustomNote = {
    'strMSGenerate': '【.ms】指令\n母舰人物作成',
    'strMSGenerateAtOther': '【.ms】代骰\n代他人母舰人物作成',
    'strMSGenerateError': '【.ms】指令\n人物作成错误',

    'strRMResult': '【.rm】指令\n检定结果',
    'strRMResultAtOther': '【.rm】代骰\n代骰检定结果',
    'strRMResultWithSkillName': '【.rm】指令\n检定结果（带技能名）',
    'strRMResultWithSkillNameAtOther': '【.rm】代骰\n代骰检定结果（带技能名）',
    'strRMDeathResult': '【.rm 死亡】指令\n死亡豁免',
    'strRMDeathResultAtOther': '【.rm 死亡】代骰\n死亡豁免',
    'strMSDeathSave0': '【.rm 死亡】文本\n死亡豁免（D10=0）',
    'strMSDeathSave1to4': '【.rm 死亡】文本\n死亡豁免（D10=1-4）',
    'strMSDeathSave5plus': '【.rm 死亡】文本\n死亡豁免（D10≥5）',
    'strRMError': '【.rm】指令\n检定错误',

    'strStressNone': '【压力】文本\n无变化',
    'strStressAdd': '【压力】文本\n失败增加',
    'strStressAddMax': '【压力】文本\n达到上限（含溢出提示）',
    'strStressReduce': '【压力】文本\n休息成功减少',
    'strStressMinNote': '【压力】文本\n已达下限提示',

    'strMPResult': '【.mp】指令\n惊恐检定结果',
    'strMPResultAtOther': '【.mp】代骰\n代骰惊恐检定结果',
    'strMPError': '【.mp】指令\n惊恐检定错误',
}


dictHelpDocTemp = {
    '母舰': '''【母舰模块 - 总帮助】

本模块提供《母舰 Mothership》规则的检定与人物作成功能。

指令：
• .ms - 人物作成
• .rm - 属性/豁免检定（含休息/死亡，可选b/p参数）
• .mp - 惊恐检定

建议每个群初始化：
• .set temp ms

建议每位玩家录卡后进行初始化：
• .sn
• .sn auto on''',

    'ms': '''【母舰人物作成】

.ms [次数]

默认1次，最多10次。
也可@他人代骰（需权限）。

注意：为避免与其他插件的 `.ms` 命令冲突，本插件仅在以下情况才响应 `.ms`：
• 当前群模板为 ms（建议先 `.set temp ms`）
• 或当前人物卡模板为 ms
否则将不处理该命令。''',

    'rm': '''【母舰属性/豁免检定】

.rm [bN/pN] <属性/豁免/表达式>

特殊：
• .rm [bN/pN] 休息
• .rm 死亡

说明：
• b/p 为可选参数：b取高（kh），p取低（kl）；不带数字默认2骰，b2/p2为3骰，以此类推
• 压力>20时会产生检定减值（压力-20）
• 失败自动+1压力；休息成功按D100个位数减压（不低于下限）

休息豁免规则：
• 仅在当前群模板为 ms，或目标人物卡模板为 ms 时可用（否则不响应，避免命令冲突）
• 阈值取人物卡模板 skill→“豁免”列表中数值最低的一项（即“最差豁免”）''',

    'mp': '''【母舰惊恐检定】

.mp

投1d20，与当前压力比较：
• 得数 > 压力：成功
• 得数 ≤ 压力：失败并查惊恐表''',

    'mothership': '&母舰',
    'MS': '&母舰',
}
