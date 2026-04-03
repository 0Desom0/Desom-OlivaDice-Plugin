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
    'reply_bot_status': '当前 Bot：{bot_id}，Bot 开关：{bot_enable}。',
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
    'reply_bot_status': '【tplbot status】\n用于展示当前 Bot 的隔离配置状态。',
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

8. .tplecho 你好
普通回复，默认尝试写入日志。

9. .tplecho silent 你好
纯净回复，不主动调用日志记录钩子。

10. GUI 的 Bot 配置页
可直接编辑当前 Bot 的自定义回复词。

11. utils.send_message_force(...)
用于在没有当前消息事件对象时主动发消息。

12. poke 事件
模板已提供默认的戳一戳事件处理示例。''',
}


gui_description_text = '''这个模板的 GUI 故意保持轻量：
1. 主界面只保留“全局设置”和“Bot 配置”两个页签。
2. Bot 配置页内部提供 Bot 选择框，切换后所有按钮都会跟着切换到对应账号。
3. 回复词和设主列表通过 Bot 配置页按钮打开子窗口管理。
4. 如果当前 Bot 有群链且自己是从账号，界面会提示回复词实际读取的主账号。
5. 当前模板里 bot_config 与骰主列表不跟随 link；只有 storage、回复词与变量会切到 linked_bot_hash 对应文件夹。'''
