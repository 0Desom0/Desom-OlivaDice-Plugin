"""插件自己的回复也遵循 Core 的模板变量机制。"""

dictStrCustom = {
    'strMcsResult': '{tMcsResult}',
    'strMcsRecommend': '请选择要切换的回复，发送候选序号（30 秒内）：\n{tSearchResult}',
    'strMcsNotFound': '没有找到对应回复，或选择无效。请用 .mcs list 查看可用回复。',
}
dictStrCustomNote = {
    'strMcsResult': 'MultiCustomSwitch 指令结果；{tMcsResult} 为结果正文。',
    'strMcsRecommend': 'MultiCustomSwitch 模糊匹配候选；{tSearchResult} 为候选列表。',
    'strMcsNotFound': 'MultiCustomSwitch 未匹配到回复或选择无效。',
}
COMMAND_HELP = """多自定义回复切换（MultiCustomSwitch）
.mcs [回复名或序号]：本群切换，仅群主/管理员
.mcs global [回复名或序号]：当前 bot 的全局默认切换，仅骰主
.mcs list：查看当前 bot 已加载的回复
.mcs show 或 .mcs：查看本群选择、开关及实际生效回复
.mcs on/off：本群开启/关闭，仅群主/管理员
.mcs global on/off：当前 bot 全局开启/关闭，仅骰主
.mcs help：显示本帮助

1 = default：Core 原有自定义回复，与官方 GUI/WebUI 共用数据。
2 = smp：Core 的全默认回复，Bot 名采用真实账号名称，只读。
3 及以上 = 当前 bot 已加载的自定义回复；unity 模板须先加载。

全局开关优先于群开关；关闭后恢复 1/default。
单独设置过的群保留自己的选择，其他群及私聊使用全局默认。
本插件不遵循 OlivaDiceCore 的群链；各群的回复选择与开关独立，不沿群链同步或继承。
名称未精确匹配时，按 .st set 的方式显示候选并等待选择。
候选序号仅用于当次选择，不是 .mcs list 中的回复序号。
global 的所有操作只作用于当前 bot。
命令按前缀贪婪匹配，可省略空格：.mcs3、.mcs回复名、.mcsglobal2、.mcsglobaloff。"""
