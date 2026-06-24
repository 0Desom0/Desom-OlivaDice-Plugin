# -*- encoding: utf-8 -*-
"""
自定义消息与自定义变量定义模块。

这个文件只放“模板默认提供的文案内容”与“这些文案在 GUI 中如何说明”。
所有数据读写都交给 utils.py 处理，保证 message_custom.py 只是一个
默认值来源，而不是配置读写中心。

注意：
这里定义的是“默认内容”。
真正运行时：
- bot_config 与 configured_master_list 都按原始 bot 单独保存。
- storage、message_custom.json、message_variable.json
    会统一落到对应的 linked_bot_hash 目录里。
- 因此模板里的主从 bot 会共享主账号目录中的 storage、回复词与变量。
"""


default_custom_message_dict = {
    'reply_ping': '收到来自 {user_name} 的测试消息，当前 Bot 为 {bot_id}。',
    'reply_poke': '戳一戳收到，当前 Bot 为 {bot_id}。',
    'reply_help_hint': '可使用 {prefix}tplhelp 查看模板帮助。',
    'reply_permission_denied': '权限不足：只有 OlivaDiceCore 骰主或本插件配置骰主可以执行该操作。',
    'reply_global_status': '全局启用：{global_enable}，调试模式：{global_debug}。',
    'reply_global_usage_debug': '用法：.tplglobal debug on 或 .tplglobal debug off',
    'reply_global_usage': '用法：.tplglobal status/on/off/debug on/debug off',
    'reply_bot_status': '当前 Bot：{bot_id}，Bot 开关：{bot_enable}。',
    'reply_bot_master_list': '当前本插件配置骰主列表：{master_list}。',
    'reply_bot_master_updated': '已更新本插件配置骰主列表：{master_list}。',
    'reply_bot_usage': '用法：.tplbot status/on/off 或 .tplbot master list/add/del [用户ID]',
    'reply_group_status': '当前群（{group_id}）在本插件中处于：{group_disable_status}状态。',
    'reply_group_disabled': '已在当前群（{group_id}）禁用本插件命令。',
    'reply_group_enabled': '已在当前群（{group_id}）重新启用本插件命令。',
    'reply_group_not_in_group': '当前不在群聊场景中，无法执行群级操作。',
    'reply_group_list': '当前 Bot 的群禁用列表：{group_disable_list}。',
    'reply_group_list_empty': '当前 Bot 没有任何群禁用。',
    'reply_group_add_done': '已将 {target_groups} 加入群禁用列表。',
    'reply_group_del_done': '已将 {target_groups} 从群禁用列表移除。',
    'reply_group_usage_add': '用法：.tplgroup add [群号]',
    'reply_group_usage_del': '用法：.tplgroup del [群号]',
    'reply_group_usage': '用法：.tplgroup status/on/off/list/add [群号]/del [群号]',
    'reply_echo': '{echo_text}',
}


default_custom_variable_dict = {
    'template_name': '轻量级插件模板',
    'template_prefix_example': '.tplhelp',
}


custom_message_note_dict = {
    'reply_ping': '【tplping】示例命令\n用于演示最基础的自定义回复格式化。',
    'reply_poke': '【poke 事件】\n用于演示收到戳一戳事件后的默认回复。',
    'reply_help_hint': '【无指令命中时的提示】\n用于提醒用户查看帮助。',
    'reply_permission_denied': '【权限不足】\n模板中所有需要骰主权限的命令都会复用这条文案。',
    'reply_global_status': '【tplglobal status】\n用于展示全局开关与调试模式状态。',
    'reply_global_usage_debug': '【tplglobal debug 用法提示】\ndebug 子命令参数缺失时的用法提示。',
    'reply_global_usage': '【tplglobal 总用法提示】\n未知子命令时的用法提示。',
    'reply_bot_status': '【tplbot status】\n用于展示当前 Bot 的隔离配置状态。',
    'reply_bot_master_list': '【tplbot master list】\n展示当前本插件配置骰主列表。',
    'reply_bot_master_updated': '【tplbot master add/del 成功】\n更新骰主列表后的统一回复。',
    'reply_bot_usage': '【tplbot 总用法提示】\n未知子命令时的用法提示。',
    'reply_group_status': '【tplgroup status】\n用于展示当前群在本插件中的启用/禁用状态。',
    'reply_group_disabled': '【tplgroup off 成功】\n在当前群禁用本插件命令后的回复。',
    'reply_group_enabled': '【tplgroup on 成功】\n在当前群重新启用本插件命令后的回复。',
    'reply_group_not_in_group': '【tplgroup 非群聊场景】\n私聊等非群聊场景下执行群级操作时的提示。',
    'reply_group_list': '【tplgroup list 有内容】\n展示当前 Bot 的群级禁用列表。',
    'reply_group_list_empty': '【tplgroup list 无内容】\n当前 Bot 没有任何群级禁用时的提示。',
    'reply_group_add_done': '【tplgroup add 成功】\n将指定群加入禁用列表后的回复。',
    'reply_group_del_done': '【tplgroup del 成功】\n将指定群从禁用列表移除后的回复。',
    'reply_group_usage_add': '【tplgroup add 用法提示】\n参数缺失时的用法提示。',
    'reply_group_usage_del': '【tplgroup del 用法提示】\n参数缺失时的用法提示。',
    'reply_group_usage': '【tplgroup 总用法提示】\n未知子命令时的用法提示。',
    'reply_echo': '【tplecho】示例命令\n用于演示可选是否写入 OlivaDiceLogger 的回复封装。',
}


help_document_dict = {
    'template_help': '''【轻量级插件模板帮助】
1. .tplhelp
查看模板帮助。

2. .tplping
演示最基础的回复词格式化。

3. .tplglobal status/on/off/debug on/debug off
演示全局配置的读写。

4. .tplbot status/on/off
演示 Bot 级隔离配置。

5. .tplbot master list
查看本插件配置骰主。

6. .tplbot master add 123456
添加本插件配置骰主。

7. .tplbot master del 123456
删除本插件配置骰主。

8. .tplgroup status
查看当前群在本插件中的启用/禁用状态。（骰主/群主/群管）

9. .tplgroup off
在当前群禁用本插件命令（仅影响普通命令，管理命令不受影响）。（骰主/群主/群管）

10. .tplgroup on
在当前群重新启用本插件命令。（骰主/群主/群管）

11. .tplgroup list
查看当前 Bot 的群级禁用列表。（骰主/群主/群管）

12. .tplgroup add 群号
将指定群加入禁用列表。（仅骰主）

13. .tplgroup del 群号
将指定群从禁用列表移除。（仅骰主）

14. .tplecho 你好
普通回复，默认尝试写入日志。

15. .tplecho silent 你好
纯净回复，不主动调用日志记录钩子。

16. GUI 的 Bot 配置页
可直接编辑当前 Bot 的自定义回复词。

17. utils.send_message_force(...)
用于在没有当前消息事件对象时主动发消息。

18. poke 事件
模板已提供默认的戳一戳事件处理示例。''',
}


gui_description_text = '''这个模板的 GUI 故意保持轻量：
1. 主界面只保留“全局设置”和“Bot 配置”两个页签。
2. Bot 配置页内部提供 Bot 选择框，切换后所有按钮都会跟着切换到对应账号。
3. 回复词和设主列表通过 Bot 配置页按钮打开子窗口管理。
4. 如果当前 Bot 有群链且自己是从账号，界面会提示回复词实际读取的主账号。
5. 当前模板里 bot_config 与骰主列表不跟随 link；只有 storage、回复词与变量会切到 linked_bot_hash 对应文件夹。'''
