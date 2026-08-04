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
cover_index_file_name = 'cover_index.json'
cover_art_folder_name = 'CoverArt'
adjusted_cover_art_folder_name = 'Adjusted'
excel_table_folder_name = 'excel_table'
excel_table_extension_list = ['.xlsx', '.xlsm']
font_file_name = 'fonts.ttf'
portal_font_file_name_list = ('Kawoszeh.ttf', '千图雪花体.ttf')

# Firebase Web API Key 来自 Portal 前端公开配置，不是登录时实时生成的秘密；站点迁移项目时可在运行配置覆盖。
lanota_portal_api_base_url = 'https://noxygames.com/lanota/portal/api'
lanota_portal_firebase_api_key = 'AIzaSyCIxTfcSRdfzdkCuUe8f0HeJrS8LHUp0Ng'
lanota_portal_asset_base_url = 'https://noxygames.com/lanota/portal'
lanota_portal_china_api_base_url = 'https://lanota.gmzon.com/portal/api'
lanota_portal_china_asset_base_url = 'https://lanota.gmzon.com/portal'
lanota_portal_china_app_scheme = 'lanotagames-cn'
lanota_portal_china_login_timeout_seconds = 120
lanota_portal_china_poll_interval_seconds = 2
lanota_portal_browser_path = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
lanota_portal_connect_timeout_seconds = 10
lanota_portal_timeout_seconds = 25
lanota_portal_template_file_name = 'lanota_portal_user.html'
lanota_portal_china_template_file_name = 'lanota_portal_user_china.html'
lanota_portal_song_template_file_name = 'lanota_portal_song.html'
lanota_portal_b30_template_file_name = 'lanota_portal_b30.html'
# 歌曲卡片通过数据中的区域标签动态区分国际服/国服，共用一份模板，避免部署时漏装副本。
lanota_portal_china_song_template_file_name = 'lanota_portal_song.html'
lanota_portal_screenshot_width = 1200
lanota_portal_b30_screenshot_width = 1320
lanota_portal_screenshot_height = 1360
lanota_portal_song_screenshot_height = 1600
lanota_portal_b30_screenshot_height = 2660
lanota_portal_device_scale_factor = 2

allowed_prefix_list = ['.', '。', '/', '／']
image_cache_limit = 40
image_max_chars = 100
search_image_max_chars = 38
text_image_min_chars = 120
b30_cooldown_seconds = 300
ocr_max_images_per_message = 12
ocr_image_max_bytes = 30 * 1024 * 1024

# 搜索结果分页配置
result_page_size = 10  # 每页显示的结果数
selection_timeout_seconds = 3600  # 选择会话超时时间（秒）

api_base_url = 'https://lanota.fandom.com'
api_url = f'{api_base_url}/api.php'
api_timeout_seconds = 15
cover_download_timeout_seconds = 60
cover_download_max_bytes = 20 * 1024 * 1024
cover_download_workers = 6

default_global_config = {
    'global_enable_switch': True,
    'global_debug_mode_switch': False,
    'configured_master_list': [],
    'alias_groups': [
        '1037559220',
        '767569571',
    ],
    # 真实账号信息只填写到运行期 plugin/data/LanotaPlugin/global_config.json。
    'wiki_sync_username': '',
    'wiki_sync_bot_password': '',
    'wiki_sync_edit_summary': 'Sync song list from individual song pages via MediaWiki API',
    'send_cover_art': True,
    'download_cover_on_demand': True,
    # Portal 登录账号；不把真实凭据写入插件源码。
    'lanota_portal_email': '',
    'lanota_portal_password': '',
    'lanota_portal_firebase_api_key': lanota_portal_firebase_api_key,
    'lanota_portal_browser_path': lanota_portal_browser_path,
    'lanota_portal_device_scale_factor': lanota_portal_device_scale_factor,
}

default_bot_config = {
    'bot_enable_switch': True,
    'send_as_image': True,
    'plain_text_mode': False,
    'song_card_html_enable': True,
    'disabled_group_list': [],
}
