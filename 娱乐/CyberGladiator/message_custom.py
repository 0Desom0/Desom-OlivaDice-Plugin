# -*- encoding: utf-8 -*-
"""赛博角斗场默认回复词与说明。"""


default_custom_message_dict = {
    'reply_help_hint': '可使用 {prefix}角斗帮助 或 {prefix}决斗帮助 查看赛博角斗场帮助。',
    'reply_permission_denied': '权限不足：只有群主、群管、OlivaDiceCore 骰主或本插件配置骰主可以执行该操作。',
    'reply_global_permission_denied': '权限不足：只有 OlivaDiceCore 骰主或本插件配置骰主可以执行全局开关操作。',
    'reply_config_permission_denied': '权限不足：只有 OlivaDiceCore 骰主或本插件配置骰主可以执行 Bot 级角斗配置操作。',
    'reply_group_only': '赛博角斗场只支持在群聊中使用。',
    'reply_plugin_disabled': '本群的赛博角斗场目前已关闭，如需恢复请使用 {prefix}角斗开启。',
    'reply_battle_locked': '当前本群角斗仍在进行中，结束前不能录入、开始、退出或清空。',
    'reply_room_joined': '{user_display_name} 已进入角斗场（序号 {entry_index}），当前人数：{waiting_count}',
    'reply_room_updated': '{user_display_name} 的第 {entry_index} 条角斗设定已更新，当前人数：{waiting_count}',
    'reply_room_full': '当前角斗场已满员，最多允许 {max_participants} 名角斗士候场。',
    'reply_room_not_enough': '当前候场人数不足 2 人，无法开始角斗。',
    'reply_room_starting': '角斗推演中，请稍候...',
    'reply_battle_finished': '本次角斗推演结束。',
    'reply_room_query_empty': '本群当前没有待开始的角斗记录。',
    'reply_room_query_header': '当前本群共有 {waiting_count} 名角斗士候场：',
    'reply_room_query_item': '{entry_index}. {user_display_name}\n设定：{input_text}',
    'reply_gladiator_status': '本群当前模式：{battle_mode}\n本群当前状态：{battle_progress}\n本群当前角色数：{waiting_count}\n普通模式字数限制：{normal_input_limit_text}\n神战模式字数限制：{god_war_input_limit_text}\n',
    'reply_room_removed': '已移除第 {entry_index} 条角斗记录，当前人数：{waiting_count}',
    'reply_room_removed_all': '已移除你名下的全部 {removed_count} 条角斗记录，当前人数：{waiting_count}',
    'reply_room_cleared': '本群角斗列表已清空。',
    'reply_invalid_index': '序号无效，请输入 1 到 {waiting_count} 之间的数字。',
    'reply_self_not_in_room': '你当前不在候场列表中，无需退出。',
    'reply_update_no_entry': '你当前没有可更新的候场记录，请先使用 {prefix}角斗加入 添加设定。',
    'reply_update_need_index': '你当前有 {self_entry_count} 条候场记录，请使用 {prefix}角斗更新 序号 新设定 来指定要更新的那一条。',
    'reply_update_not_owner': '你只能更新你自己的候场记录，请检查序号。',
    'reply_stop_requested': '已收到强制停止指令，本次角斗已立刻停止，群锁定已解除，候场也已清空。',
    'reply_stop_not_running': '当前本群没有正在进行中的角斗，无需停止。',
    'reply_close_success': '本群的赛博角斗场已关闭。',
    'reply_open_success': '本群的赛博角斗场已开启。',
    'reply_already_closed': '本群的赛博角斗场已经处于关闭状态。',
    'reply_already_open': '本群的赛博角斗场已经处于开启状态。',
    'reply_global_close_success': '赛博角斗场全局开关已关闭。',
    'reply_global_open_success': '赛博角斗场全局开关已开启。',
    'reply_global_already_closed': '赛博角斗场全局开关已经处于关闭状态。',
    'reply_global_already_open': '赛博角斗场全局开关已经处于开启状态。',
    'reply_config_status': '当前 Bot 配置：切片等待 {delay_min_seconds} 到 {delay_max_seconds} 秒；普通模式设定字数上限 {normal_input_limit_text}；神战模式设定字数上限 {god_war_input_limit_text}。',
    'reply_delay_config_status': '当前 Bot 的切片播报等待时间为 {delay_min_seconds} 到 {delay_max_seconds} 秒。',
    'reply_delay_config_updated': '当前 Bot 的切片播报等待时间已更新为 {delay_min_seconds} 到 {delay_max_seconds} 秒。',
    'reply_delay_config_invalid': '等待时间配置格式错误，请使用 {prefix}角斗配置 等待 10 20，且两个值都必须是大于 0 的整数，并满足最小值不大于最大值。',
    'reply_input_limit_status': '当前 Bot 的设定字数上限：普通模式 {normal_input_limit_text}；神战模式 {god_war_input_limit_text}。',
    'reply_input_limit_updated': '{mode_name}模式的设定字数上限已更新为 {input_limit_text}。',
    'reply_input_limit_invalid': '字数限制配置格式错误，请使用 {prefix}角斗配置 字数 普通 1000 或 {prefix}角斗配置 字数 神战 1000；数值必须是大于等于 0 的整数，0 表示不限制。',
    'reply_input_limit_exceeded': '{mode_name}模式设定超出上限。当前字符数：{current_length_text}；允许上限：{input_limit_text}。计数规则：全角/中文按 1，半角/数字按 0.5，空格不计。',
    'reply_god_war_status': '神战当前实际状态：{god_war_mode}。全局默认模式：{god_war_total_mode}；本群单独配置：{god_war_group_override_mode}；本群配置结果：{god_war_group_mode}。',
    'reply_god_war_group_enabled': '本群的神战模式已单独开启，并会覆盖全局默认模式。后续本群 .角斗开始 / .决斗开始 将使用神战 prompt。',
    'reply_god_war_group_disabled': '本群的神战模式已单独关闭，并会覆盖全局默认模式。后续本群 .角斗开始 / .决斗开始 将恢复普通模式。',
    'reply_god_war_group_already_enabled': '本群的神战模式开关已经处于开启状态。',
    'reply_god_war_group_already_disabled': '本群的神战模式开关已经处于关闭状态。',
    'reply_god_war_global_enabled': '神战全局默认模式已设置为开启。未单独配置的群会默认进入神战模式。',
    'reply_god_war_global_disabled': '神战全局默认模式已设置为关闭。未单独配置的群会默认使用普通模式。',
    'reply_god_war_global_already_enabled': '神战全局默认模式已经处于开启状态。',
    'reply_god_war_global_already_disabled': '神战全局默认模式已经处于关闭状态。',
    'reply_god_war_invalid': '神战命令格式错误，请使用 {prefix}角斗神战 开启、{prefix}角斗神战 关闭、{prefix}角斗神战 全局 开启 或 {prefix}角斗神战 全局 关闭。',
    'reply_missing_api_config': '当前 Bot 未配置完整的 API 信息，请在 bot_config.json 中补充 api_url、api_key 和 model。',
    'reply_battle_failed': '角斗推演失败：{error_message}',
    'reply_unknown_command': '未识别的角斗/决斗指令，可使用 {prefix}角斗帮助 查看帮助。',
}


default_custom_variable_dict = {
    'template_name': '赛博角斗场',
    'template_prefix_example': '.角斗帮助 / .决斗帮助',
}


custom_message_note_dict = {
    'reply_help_hint': '【帮助提示】\n未命中具体子命令时提示用户查看帮助。',
    'reply_permission_denied': '【权限不足】\n清空、停止、关闭、开启等管理操作统一使用这条文案。',
    'reply_global_permission_denied': '【全局权限不足】\n关闭/开启 全局 时，仅骰主与配置骰主使用。',
    'reply_config_permission_denied': '【Bot 配置权限不足】\n角斗配置命令只允许骰主与配置骰主使用。',
    'reply_group_only': '【群聊限制】\n私聊中触发角斗指令时使用。',
    'reply_plugin_disabled': '【群级关闭】\n本群关闭插件后，普通指令会使用这条文案。',
    'reply_battle_locked': '【进行中锁定】\n角斗进行时，录入、开始、退出、清空会被拦截。',
    'reply_room_joined': '【角斗加入】\n每次加入都新增一条候场记录时使用。',
    'reply_room_updated': '【角斗更新】\n更新自己某一条候场记录时使用。',
    'reply_room_full': '【角斗录入】\n候场已满 4 人时使用。',
    'reply_room_not_enough': '【角斗开始】\n候场不足 2 人时使用。',
    'reply_room_starting': '【角斗开始】\n开始调用大模型前的提示。',
    'reply_battle_finished': '【角斗开始】\n整场推演正常结束后的收尾提示。',
    'reply_room_query_empty': '【查询角斗】\n当前群没有候场数据时使用。',
    'reply_room_query_header': '【查询角斗】\n列表头部文案。',
    'reply_room_query_item': '【查询角斗】\n每个候场条目的展示模板。',
    'reply_gladiator_status': '【角斗状态】\n查询本群状态',
    'reply_room_removed': '【角斗退出】\n按序号删除某条记录后的文案。',
    'reply_room_removed_all': '【角斗退出】\n不带序号时，退出自己全部候场记录后的文案。',
    'reply_room_cleared': '【角斗清空】\n清空候场列表后的文案。',
    'reply_invalid_index': '【角斗退出】\n传入序号无效时使用。',
    'reply_self_not_in_room': '【角斗退出】\n未带序号但自己不在候场时使用。',
    'reply_update_no_entry': '【角斗更新】\n当前没有自己的候场记录时使用。',
    'reply_update_need_index': '【角斗更新】\n自己有多条候场记录但未带序号时使用。',
    'reply_update_not_owner': '【角斗更新】\n试图更新别人的候场记录时使用。',
    'reply_stop_requested': '【角斗停止】\n运行中收到强制停止指令后，立即停止并解除锁定时使用。',
    'reply_stop_not_running': '【角斗停止】\n当前没有进行中的角斗时使用。',
    'reply_close_success': '【角斗关闭】\n本群停用插件后的文案。',
    'reply_open_success': '【角斗开启】\n本群恢复插件后的文案。',
    'reply_already_closed': '【角斗关闭】\n重复关闭时使用。',
    'reply_already_open': '【角斗开启】\n重复开启时使用。',
    'reply_global_close_success': '【角斗关闭 全局】\n成功关闭全局开关后的文案。',
    'reply_global_open_success': '【角斗开启 全局】\n成功开启全局开关后的文案。',
    'reply_global_already_closed': '【角斗关闭 全局】\n全局已关闭时使用。',
    'reply_global_already_open': '【角斗开启 全局】\n全局已开启时使用。',
    'reply_config_status': '【角斗配置】\n不带参数时，同时展示等待时间与普通/神战设定字数上限。',
    'reply_delay_config_status': '【角斗配置 等待】\n查询当前 Bot 的切片播报等待区间时使用。',
    'reply_delay_config_updated': '【角斗配置 等待】\n成功保存当前 Bot 的切片播报等待区间时使用。',
    'reply_delay_config_invalid': '【角斗配置 等待】\n参数格式错误时使用。',
    'reply_input_limit_status': '【角斗配置 字数】\n查询普通/神战设定字数上限时使用。',
    'reply_input_limit_updated': '【角斗配置 字数】\n成功保存普通或神战设定字数上限时使用。',
    'reply_input_limit_invalid': '【角斗配置 字数】\n参数格式错误时使用。',
    'reply_input_limit_exceeded': '【角斗加入 / 角斗更新】\n录入或更新的设定超出当前模式字数上限时使用。',
    'reply_god_war_status': '【角斗神战】\n查询全局默认模式、本群单独配置、本群结果与最终生效状态时使用。',
    'reply_god_war_group_enabled': '【角斗神战 开启】\n成功把本群神战模式单独开启并覆盖全局默认模式时使用。',
    'reply_god_war_group_disabled': '【角斗神战 关闭】\n成功把本群神战模式单独关闭并覆盖全局默认模式时使用。',
    'reply_god_war_group_already_enabled': '【角斗神战 开启】\n本群神战开关重复开启时使用。',
    'reply_god_war_group_already_disabled': '【角斗神战 关闭】\n本群神战开关重复关闭时使用。',
    'reply_god_war_global_enabled': '【角斗神战 全局 开启】\n成功把神战全局默认模式设为开启时使用。',
    'reply_god_war_global_disabled': '【角斗神战 全局 关闭】\n成功把神战全局默认模式设为关闭时使用。',
    'reply_god_war_global_already_enabled': '【角斗神战 全局 开启】\n神战全局默认模式重复开启时使用。',
    'reply_god_war_global_already_disabled': '【角斗神战 全局 关闭】\n神战全局默认模式重复关闭时使用。',
    'reply_god_war_invalid': '【角斗神战】\n神战命令参数错误时使用。',
    'reply_missing_api_config': '【API 配置缺失】\n未填写 api_url、api_key、model 时使用。',
    'reply_battle_failed': '【角斗开始】\n调用 API 或播报失败时使用。',
    'reply_unknown_command': '【未知角斗指令】\n已识别到角斗前缀但子命令不合法时使用。',
}


help_document_dict = {
    'gladiator_help': '''【赛博角斗场帮助】
1. .角斗录入 [设定文本] / .决斗录入 [设定文本]
兼容旧命令，等价于“角斗加入”，每次都会新增一条候场记录。

2. .角斗加入 [设定文本] / .决斗加入 [设定文本]
加入一条新的角斗设定。不写设定时，会自动用本群群名片生成默认设定。同一个人可以多次加入，直到候场满员。

3. .角斗更新 [设定文本] / .决斗更新 [设定文本]
如果你当前只有 1 条候场记录，则直接更新那一条。

4. .角斗更新 [序号] [设定文本] / .决斗更新 [序号] [设定文本]
如果你当前有多条候场记录，则必须带序号更新，而且只能更新你自己的记录。

5. .角斗查询 / .决斗查询
查看本群候场人数、序号和每位角斗士的设定文本。QQ 环境下会按“每个角色一条”打包成合并转发。

6. .角斗状态 / .决斗状态
查看本群当前角斗模式（普通/神战）、当前是否进行中，以及当前角色数量。

7. .角斗退出 [序号] / .决斗退出 [序号]
带序号时按候场顺序删除对应记录；不带序号时会把你名下的全部候场记录一起退出。

8. .角斗开始 / .决斗开始
候场至少 2 人时开始推演，系统会生成面板、固定 10 轮骰序列并调用大模型。进行中会锁定录入、开始、退出、清空。

9. .角斗清空 / .决斗清空
清空本群候场列表，仅群主、群管、OlivaDiceCore 骰主或本插件配置骰主可用。

10. .角斗停止 / .决斗停止
强制停止当前角斗，后续播报不再发送，并清空候场。仅管理权限可用。

11. .角斗关闭 [本群/全局] / .决斗关闭 [本群/全局]
默认关闭本群赛博角斗场，仅群主、群管、骰主可用。若参数为“全局”，则关闭全局开关，仅骰主与配置骰主可用。

12. .角斗开启 [本群/全局] / .决斗开启 [本群/全局]
默认重新开启本群赛博角斗场，仅群主、群管、骰主可用。若参数为“全局”，则开启全局开关，仅骰主与配置骰主可用。

13. .角斗配置 / .决斗配置
查看当前 Bot 的切片等待时间与普通/神战设定字数上限。仅骰主与配置骰主可用。

14. .角斗配置 等待 [最小秒数] [最大秒数] / .决斗配置 等待 [最小秒数] [最大秒数]
查看或修改当前 Bot 的每段播报等待时间。不带秒数时返回当前配置；设置成功后会写入当前 Bot 的 bot_config.json。仅骰主与配置骰主可用。

15. .角斗配置 字数 [普通/神战] [上限] / .决斗配置 字数 [普通/神战] [上限]
查看或修改当前 Bot 的设定字数上限。0 表示不限制；全角/中文按 1，半角/数字按 0.5，空格不计。仅骰主与配置骰主可用。

16. .角斗神战 [开启/关闭] / .决斗神战 [开启/关闭]
切换本群的神战单独配置，本群设置优先级高于全局默认模式。不带参数时可查看全局默认模式、本群单独配置、本群开关与实际生效状态。群主、群管、OlivaDiceCore 骰主与本插件配置骰主可用。

17. .角斗神战 全局 [开启/关闭] / .决斗神战 全局 [开启/关闭]
切换神战全局默认模式，仅骰主与配置骰主可用。

18. .角斗帮助 / .决斗帮助
查看本帮助文档。''',
}


gui_description_text = '''赛博角斗场 GUI 继续保持轻量结构：
1. 主界面仍然只有“全局配置”和“Bot 配置”两个页签。
2. Bot 配置页可切换账号，并直接打开当前 Bot 的配置目录与回复目录。
3. 回复词仍通过子窗口编辑，方便在 GUI 中改所有用户可见文案。
4. 每个 Bot 的 API、模型、普通/神战提示词和切片等待区间配置保存在对应 bot_config.json 中。'''
