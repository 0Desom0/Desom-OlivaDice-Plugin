# -*- encoding: utf-8 -*-
"""QQ 官方机器人自定义菜单与指令面板插件的静态配置。"""

import os

plugin_name = 'QQBotMenuPanel'
plugin_display_name = 'QQ菜单与指令面板'

webui_event = 'QQBotMenuPanel_WebUI'

plugin_data_dir = os.path.join('plugin', 'data', plugin_name)
global_config_file_name = 'global_config.json'
bot_config_file_name = 'bot_config.json'
message_custom_file_name = 'message_custom.json'

qqguildv2_sdk = 'qqGuildv2_link'

SCOPE_C2C = 'c2c'
SCOPE_GROUP = 'group'
SCOPE_CHANNEL = 'channel'
SCOPE_DM = 'dm'
SCOPE_LIST = [SCOPE_C2C, SCOPE_GROUP, SCOPE_CHANNEL, SCOPE_DM]

SCOPE_LABEL_DICT = {
    SCOPE_C2C: '消息列表（单聊）',
    SCOPE_GROUP: 'QQ 群',
    SCOPE_CHANNEL: 'QQ 频道',
    SCOPE_DM: '频道私信',
}

MENU_ITEM_TYPE_LABEL_DICT = {
    'send_message': '发送消息',
    'link': '链接跳转',
    'switch': '开关',
    'menu': '子菜单',
}

PANEL_ITEM_TYPE_LABEL_DICT = {
    'command': '指令',
    'link': '链接跳转',
}

TARGET_TYPE_LABEL_DICT = {
    'all': '全局生效',
    'specific': '指定对象',
}

# 官方文档限制。
MENU_ITEM_MAX = 10
MENU_NAME_WIDTH_MAX = 10
SUB_MENU_ITEM_MAX = 5
SUB_MENU_NAME_WIDTH_MAX = 14
PANEL_ITEM_MAX = 20
PANEL_NAME_WIDTH_MAX = 14
PANEL_DESC_WIDTH_MAX = 30
PANEL_REMARK_MAX = 255
PANEL_MAX_PER_BOT = 20
OPENID_PER_REQUEST_MAX = 20
LINK_PREFIX = 'https://'

default_global_config = {
    'global_enable_switch': True,
    'global_debug_mode_switch': False,
}

default_bot_config = {
    'bot_enable_switch': True,
    'configured_master_list': [],
    'disabled_group_list': [],
    'unified_panel_mode': False,
    'chat_current_scope': SCOPE_C2C,
    'menu_draft': {
        'items': [],
        'version': None,
    },
    'panel_drafts': {
        SCOPE_C2C: [],
        SCOPE_GROUP: [],
        SCOPE_CHANNEL: [],
        SCOPE_DM: [],
    },
    'last_api_result': None,
}
