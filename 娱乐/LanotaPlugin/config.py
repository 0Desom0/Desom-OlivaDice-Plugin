# -*- encoding: utf-8 -*-
"""LanotaPlugin 静态配置。"""

import os
from pathlib import Path

plugin_name = 'LanotaPlugin'
package_dir = Path(__file__).resolve().parent

plugin_data_dir = os.path.join('plugin', 'data', plugin_name)
asset_data_dir = package_dir / 'Data'

global_config_file_name = 'global_config.json'
bot_config_file_name = 'bot_config.json'
user_data_file_name = 'UserData.json'
song_list_file_name = 'song_list.json'
song_alias_file_name = 'song_alias.json'
song_table_file_name = 'song_table.json'
excel_table_folder_name = 'excel_table'
excel_table_extension_list = ['.xlsx', '.xlsm']
font_file_name = 'fonts.ttf'

allowed_prefix_list = ['.', '。', '/', '／']
image_cache_limit = 40
image_max_chars = 100

api_base_url = 'https://lanota.fandom.com'
api_url = f'{api_base_url}/api.php'
api_timeout_seconds = 15

default_global_config = {
    'global_enable_switch': True,
    'global_debug_mode_switch': False,
    'send_as_image': True,
    'alias_groups': [
        '1037559220',
        '767569571',
    ],
}

default_bot_config = {
    'bot_enable_switch': True,
    'configured_master_list': [],
    'disabled_group_list': [],
}
