# -*- encoding: utf-8 -*-
"""IWannaSearch 静态配置。"""

import os

plugin_name = 'IWannaSearch'

menu_title_open_config = '打开插件配置'
menu_event_open_config = 'IWannaSearch_Menu_001'

plugin_data_dir = os.path.join('plugin', 'data', plugin_name)

global_config_file_name = 'global_config.json'
bot_config_file_name = 'bot_config.json'
message_custom_file_name = 'message_custom.json'
message_variable_file_name = 'message_variable.json'
storage_folder_name = 'storage'

allowed_prefix_list = ['.', '。', '/']

api_default_base_url = 'https://fangame-archive.com'
api_timeout_seconds = 12
result_page_size = 10
selection_timeout_seconds = 300

gui_window_title = 'IWannaSearch 设置面板'
gui_global_tab_title = '全局配置'
gui_bot_tab_title = 'Bot 配置'

default_global_config = {
    'global_enable_switch': True,
    'global_debug_mode_switch': False,
    'api_base_url': api_default_base_url,
    'api_timeout_seconds': api_timeout_seconds,
    'result_page_size': result_page_size,
    'selection_timeout_seconds': selection_timeout_seconds,
}

default_bot_config = {
    'bot_enable_switch': True,
    'configured_master_list': [],
    'merge_forward_enabled': True,
}
