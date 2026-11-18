# -*- encoding: utf-8 -*-
"""CelestePlugin 静态配置。

数据源统一为 WEGFan（celeste.weg.fan）镜像站：
- 搜索：/api/v2/submission/search
- 详情：/api/v2/submission/detail
- 下载：/api/v2/download/files/<站内文件 ID> 与 /api/v2/download/gamebanana-files/<GameBanana 文件 ID>
"""

import os


plugin_name = 'CelestePlugin'
plugin_data_dir = os.path.join('plugin', 'data', plugin_name)
legacy_plugin_data_dir = os.path.join('plugin', 'data', 'CelesteSearch')

global_config_file_name = 'global_config.json'
bot_config_file_name = 'bot_config.json'
storage_folder_name = 'storage'

allowed_prefix_list = ['.', '。', '/']
root_command_name = 'clst'

wegfan_origin = 'https://celeste.weg.fan'
wegfan_api_base = 'https://celeste.weg.fan/api/v2'
wegfan_search_path = '/submission/search'
wegfan_detail_path = '/submission/detail'
wegfan_gamebanana_file_url = f'{wegfan_api_base}/download/gamebanana-files/{{file_id}}'

# 本地索引：分节抓取 WEGFan 搜索列表，用于 GameBanana ID 反查、作者/分类检索与随机抽图。
wegfan_index_sections = ['Mod', 'Tool', 'Wip']
wegfan_index_page_size = 500
wegfan_index_max_pages = 60
wegfan_index_cache_name = 'wegfan_index'

# sort 取值来自 WEGFan 前端：new / updateAdded / updated / views / likes
wegfan_sort_default = 'updateAdded'

# WEGFan 作者要求：调用接口时用 User-Agent 注明是哪个 bot。
bot_user_agent = "Desom's Bot - Fronia (CelestePlugin)"

# 分类名 → categoryId（与 WEGFan 前端分类树一致），用于分类检索时直接走服务端过滤。
wegfan_categories = {
    'maps': 6800,
    'standalone': 6801,
    'campaign': 6802,
    'collab': 6803,
    'collab/contest': 6803,
    'contest': 6803,
    'multiplayer': 15667,
    'skins': 11181,
    'skin': 11181,
    'other/misc': 4632,
    'player': 11183,
    'collectibles': 16940,
    'helpers': 5081,
    'twitch integration': 4636,
    'assets': 15655,
    'audio': 15656,
    'graphics': 15657,
    'dialog': 4633,
    'translations': 14168,
    'ui': 2317,
    'mechanics': 4635,
    'effects': 1501,
    'ahorn plugin': 653,
    'lönn plugin': 1098,
    'lonn plugin': 1098,
    'mod installer': 1654,
}

default_global_config = {
    'global_enable_switch': True,
    'global_debug_mode_switch': False,
    'api_timeout_seconds': 20,
    'database_cache_seconds': 21600,
    'profile_cache_seconds': 21600,
    'search_cache_seconds': 300,
    'detail_cache_seconds': 600,
    'search_result_limit': 30,
    'slow_request_log_seconds': 3,
    'result_page_size': 8,
    'selection_timeout_seconds': 1800,
    'description_max_length': 320,
    'credit_max_length': 180,
    'show_cover_image_switch': True,
    'markdown_enable_switch': True,
    'reply_quote_switch': True,
    'random_max_count': 10,
    'detail_download_component_limit': 6,
    'long_reply_chunk_size': 1800,
}

default_bot_config = {
    'bot_enable_switch': True,
    'disabled_group_list': [],
}
