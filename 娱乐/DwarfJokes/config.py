# -*- encoding: utf-8 -*-
"""DwarfJokes 静态配置。"""

import os

plugin_name = 'DwarfJokes'

menu_title_open_config = '打开插件配置'
menu_event_open_config = 'DwarfJokes_Menu_001'
webui_event = 'DwarfJokes_WebUI_Config'

# 运行时数据目录固定写到 OlivOS 工作目录下的 plugin/data，不使用 __file__。
plugin_data_dir = os.path.join('plugin', 'data', plugin_name)

global_config_file_name = 'global_config.json'
bot_config_file_name = 'bot_config.json'
message_custom_file_name = 'message_custom.json'
message_variable_file_name = 'message_variable.json'
storage_folder_name = 'storage'
joke_pack_file_name = 'DwarfJokesPack.json'
joke_pack_seed_folder_name = 'Data'

allowed_prefix_list = ['.', '。', '/', '／']

# 导入导出与回复词长度上限，GUI 与 WebUI 共用。
json_import_max_keys = 5000
message_custom_key_max_length = 200
message_custom_value_max_length = 32768

# 主命令按长度由 parse_command 贪婪匹配，长词优先。
primary_command_names = ['dwarfjokes', '矮人笑话', 'dwarf', '矮人']

# 子命令同样走贪婪匹配；admin 比 add 更长，因此 adminadd 会先命中 admin。
subcommand_names = [
    'admin',
    '添加',
    'add',
    '删除',
    'del',
    'rm',
    '展示',
    'list',
    'show',
    '帮助',
    'help',
]
admin_action_names = ['添加', 'add', '删除', 'del', 'rm']
add_command_names = ['添加', 'add']
delete_command_names = ['删除', 'del', 'rm']
list_command_names = ['展示', 'list', 'show']
help_command_names = ['帮助', 'help']

draw_count_min = 1
draw_count_max = 10
joke_text_max_length = 4000
# OlivaDiceCore 帮助文档把 rank < 1000 当作“足够像”，但那是给短词条用的。
# 笑话正文更长且普遍含“矮人”，1000 会把不同笑话误判为重复。
# 实测：完全匹配/子串为 0，近义改写约 1-4，不同笑话通常 > 100。
joke_duplicate_rank_gate = 50

gui_window_title = 'DwarfJokes 设置面板'
gui_global_tab_title = '全局配置'
gui_bot_tab_title = 'Bot 配置'
gui_joke_tab_title = '笑话合集'

default_global_config = {
    'global_enable_switch': True,
    'global_debug_mode_switch': False,
}

default_bot_config = {
    'bot_enable_switch': True,
    'configured_master_list': [],
    'configured_admin_list': [],
    'disabled_group_list': [],
}
