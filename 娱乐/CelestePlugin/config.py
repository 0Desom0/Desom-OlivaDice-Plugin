# -*- encoding: utf-8 -*-
"""CelestePlugin 静态配置。"""

import os


plugin_name = 'CelestePlugin'
plugin_data_dir = os.path.join('plugin', 'data', plugin_name)
legacy_plugin_data_dir = os.path.join('plugin', 'data', 'CelesteSearch')

global_config_file_name = 'global_config.json'
bot_config_file_name = 'bot_config.json'
storage_folder_name = 'storage'

allowed_prefix_list = ['.', '。', '/']
root_command_name = 'clst'

search_api_url = 'https://maddie480.ovh/celeste/gamebanana-search'
info_api_url = 'https://maddie480.ovh/celeste/gamebanana-info'
random_map_url = 'https://maddie480.ovh/celeste/random-map'
database_url = 'https://everestapi.github.io/updatermirror/mod_search_database.yaml'
updater_url = 'https://everestapi.github.io/updatermirror/everest_update.yaml'
gamebanana_profile_url = 'https://gamebanana.com/apiv11/{item_type}/{item_id}/ProfilePage'

default_global_config = {
    'global_enable_switch': True,
    'global_debug_mode_switch': False,
    'api_timeout_seconds': 20,
    'database_cache_seconds': 21600,
    'profile_cache_seconds': 21600,
    'result_page_size': 8,
    'selection_timeout_seconds': 300,
    'description_max_length': 320,
    'credit_max_length': 180,
    'show_cover_image_switch': True,
    'random_max_count': 10,
    'random_category_name': 'Maps',
    'endless_category_name': 'Maps',
    'detail_download_component_limit': 6,
    'long_reply_chunk_size': 1800,
}

default_bot_config = {
    'bot_enable_switch': True,
    'disabled_group_list': [],
}
