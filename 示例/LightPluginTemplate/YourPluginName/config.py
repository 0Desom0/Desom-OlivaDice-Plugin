# -*- encoding: utf-8 -*-
"""
插件的静态配置模块。

这里刻意只放“不会随着运行动态变化”的常量定义，避免把
动态读写逻辑混到 config.py 里，方便模板使用者理解职责边界：

1. 这里定义目录、文件名、默认配置结构。
2. 这里定义消息模式与兼容版本的静态说明。
3. 这里定义允许的命令前缀。

所有真正的读写、初始化、目录创建，都放在 utils.py 中完成。
"""

import os

plugin_name = 'YourPluginName'

# 菜单配置常量需要和 app.json 中的 menu_config 保持一致。
# 这里使用 namespace 前缀，是为了贴近官方最小模板的命名习惯，
# 避免不同插件之间的菜单事件字符串互相撞名。
menu_title_open_config = '打开插件配置'
menu_event_open_config = 'YourPluginName_Menu_001'

# 插件数据目录统一放在 plugin/data/YourPluginName/ 下。
# 注意这里不要使用 __file__ 反推真实磁盘路径，避免插件被临时复制到
# plugin/tmp 之类目录时把数据写到错误位置。
plugin_data_dir = os.path.join('plugin', 'data', plugin_name)

# 通用的静态文件与目录名称。
global_config_file_name = 'global_config.json'
bot_config_file_name = 'bot_config.json'
message_custom_file_name = 'message_custom.json'
message_variable_file_name = 'message_variable.json'
storage_folder_name = 'storage'

# 允许的命令前缀仅放静态常量。
allowed_prefix_list = ['.', '。', '/', '／']

# GUI 只做一个轻量的通用面板，因此标题也放在静态配置里。
gui_window_title = 'YourPluginName 设置面板'
gui_global_tab_title = '全局配置'
gui_bot_tab_title = 'Bot 配置'

# 全局配置只保留用户要求的两个开关。
# 这份配置位于 plugin/data/YourPluginName/global_config.json，
# 也就是所有 bot 共用同一份全局配置。
default_global_config = {
    'global_enable_switch': True,
    'global_debug_mode_switch': False,
}

# Bot 配置负责 bot 自己的基础开关信息。
# 这份配置仍固定保存在 plugin/data/YourPluginName/<raw_bot_hash>/bot_config.json。
# 当前模板里，bot_config 和 configured_master_list 都不跟随 link；
# 只有 storage、message_custom、message_variable 会按 linked_bot_hash 生效。
default_bot_config = {
    'bot_enable_switch': True,
    'configured_master_list': [],
}
