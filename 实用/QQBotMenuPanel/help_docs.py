# -*- encoding: utf-8 -*-
"""内置帮助文档与官方字段中文对照。说明以 QQ 机器人开放平台文档为准。"""

import os

from . import config

BOOL_OPTIONS = [
    ('True', '开启 True'),
    ('False', '关闭 False'),
]

MENU_TYPE_OPTIONS = [
    ('send_message', '发送消息 send_message'),
    ('link', '链接跳转 link'),
    ('switch', '开关 switch'),
    ('menu', '子菜单 menu'),
]

SUB_MENU_TYPE_OPTIONS = [
    ('send_message', '发送消息 send_message'),
    ('link', '链接跳转 link'),
]

PANEL_ITEM_TYPE_OPTIONS = [
    ('command', '指令 command'),
    ('link', '链接跳转 link'),
]

TARGET_TYPE_OPTIONS = [
    ('all', '全局生效 all'),
    ('specific', '指定对象 specific'),
]


def option_labels(option_list):
    return tuple(item[1] for item in option_list)


def choice_label(option_list, value, default=''):
    text = str(value)
    for item_value, item_label in option_list:
        if item_value == text:
            return item_label
    return default or (option_list[0][1] if option_list else text)


def choice_value(option_list, label, default=''):
    text = str(label)
    for item_value, item_label in option_list:
        if item_label == text or item_value == text:
            return item_value
    return default or (option_list[0][0] if option_list else text)


def bool_to_choice(flag) -> str:
    return choice_label(BOOL_OPTIONS, 'True' if flag in [True, 'True', 'true', '1'] else 'False')


def choice_to_bool(label) -> bool:
    return choice_value(BOOL_OPTIONS, label, 'False') == 'True'


FIELD_HINT_DICT = {
    'menu_name': '名称 name：按钮上显示的文字。最多 10 个字符，一个中文汉字算 2 个字符。',
    'menu_type': (
        '类型 type：按钮点击后的行为。'
        'switch=开关；send_message=发送消息；link=链接跳转；menu=含子菜单的折叠项。'
    ),
    'menu_send': '发送内容 send_message：仅 send_message 有效。用户点击后该文本会自动填入聊天输入框。',
    'menu_link': '链接 link：仅 link 有效。用户点击后跳转到该地址，必须以 https:// 开头。',
    'menu_switch_id': (
        '开关标识 switch_id：仅 switch 有效。用户打开开关后，消息 ext 会携带 “switch_id=1”；'
        '关闭后不会携带该标识。'
    ),
    'menu_switch_default': '开关默认 default：仅 switch 有效。true 表示默认打开，false 表示默认关闭。',
    'sub_name': '子菜单名称 name：最多 14 个字符，约 7 个中文汉字。二级菜单不能再嵌套子菜单。',
    'sub_type': '子菜单类型 type：只支持 send_message（发送消息）和 link（链接跳转），不支持 menu。',
    'panel_remark': '备注 remark：给开发者自己看的标记，最多 255 个字符，不会展示给用户。',
    'panel_id': '面板 ID panel_id：平台返回的面板编号。后续修改、删除、查详情、改关联对象都要用它。',
    'target_type': (
        '作用范围 target_type：all=对该场景下所有用户/群生效；specific=仅对指定用户/群生效。'
        '只有消息列表和 QQ 群支持 specific；频道和频道私信只能 all。'
    ),
    'openid': (
        '关联对象 openid：c2c 填用户 openid，group 填群 openid。'
        '创建时可带最多 20 个，之后用「修改关联对象」增删，详情最多 1000 个。'
    ),
    'panel_item_name': (
        '元素名称 name：type=command 时，用户点击后该内容会填入聊天输入框；'
        'type=link 时仅用于面板展示。最多 14 个字符，约 7 个中文汉字。'
    ),
    'panel_item_desc': '元素描述 desc：补充说明该指令或链接的功能，会展示给用户。最多 30 个字符，约 15 个中文汉字。',
    'panel_item_type': '元素类型 type：command=指令；link=链接跳转。',
    'panel_item_link': '跳转链接 link：仅 type=link 时有效。用户点击后在浏览器中打开该地址。',
    'panel_item_admin': '仅管理员 only_admin：true 时仅频道/群管理员可点击，false 时所有用户可点击。',
    'scope': (
        '生效场景 scope：c2c=消息列表单聊；group=QQ 群；channel=文字子频道；dm=频道私信。'
        '自定义菜单只在 c2c 生效。'
    ),
}


def get_help_markdown() -> str:
    help_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'help.md')
    try:
        with open(help_path, 'r', encoding='utf-8') as help_file:
            return help_file.read()
    except Exception:
        return '# 帮助文档\n\n读取 `help.md` 失败。'


def menu_type_label(value: str) -> str:
    return choice_label(MENU_TYPE_OPTIONS, value, value)


def panel_item_type_label(value: str) -> str:
    return choice_label(PANEL_ITEM_TYPE_OPTIONS, value, value)


def target_type_label(value: str) -> str:
    return choice_label(TARGET_TYPE_OPTIONS, value, value)


def scope_label(value: str) -> str:
    return config.SCOPE_LABEL_DICT.get(value, value)
