# -*- encoding: utf-8 -*-
"""官方文档字段校验、草稿归一化与请求体组装。"""

import copy
import re
import uuid

from . import config

OPENID_SPLIT_PATTERN = re.compile(r'[\s,;，；]+')


def safe_str(value) -> str:
    try:
        return '' if value is None else str(value)
    except Exception:
        return ''


def qq_char_width(text) -> int:
    """官方计数：一个中文汉字算 2 个字符，ASCII 算 1。"""
    width = 0
    for char in safe_str(text):
        width += 1 if ord(char) <= 0x7F else 2
    return width


def new_local_id() -> str:
    return 'local_' + uuid.uuid4().hex[:12]


def parse_openid_list(text) -> list:
    result = []
    for item in OPENID_SPLIT_PATTERN.split(safe_str(text).strip()):
        item = item.strip()
        if item and item not in result:
            result.append(item)
    return result


def join_openid_list(openid_list) -> str:
    if not isinstance(openid_list, list):
        return ''
    return '\n'.join([safe_str(item) for item in openid_list if safe_str(item)])


def empty_menu_item(item_type: str = 'send_message') -> dict:
    return {
        'name': '',
        'type': item_type,
        'send_message': '',
        'link': '',
        'switch': {
            'switch_id': '',
            'default': False,
        },
        'sub_menu_items': [],
    }


def empty_sub_menu_item(item_type: str = 'send_message') -> dict:
    return {
        'name': '',
        'type': item_type,
        'send_message': '',
        'link': '',
    }


def empty_panel_item(item_type: str = 'command') -> dict:
    return {
        'name': '',
        'desc': '',
        'type': item_type,
        'only_admin': False,
        'link': '',
    }


def empty_panel_record(scope: str = config.SCOPE_C2C) -> dict:
    target_type = 'all'
    if scope in [config.SCOPE_C2C, config.SCOPE_GROUP]:
        target_type = 'all'
    return {
        'local_id': new_local_id(),
        'panel_id': '',
        'scope': scope,
        'target_type': target_type,
        'remark': '',
        'version': None,
        'items': [],
        'user_openids': [],
        'group_openids': [],
        'created_at': '',
        'updated_at': '',
        'dirty': True,
    }


def example_menu_items() -> list:
    return [
        {
            'name': '发送消息',
            'type': 'send_message',
            'send_message': '/help',
            'link': '',
            'switch': {'switch_id': '', 'default': False},
            'sub_menu_items': [],
        },
        {
            'name': '跳转链接',
            'type': 'link',
            'send_message': '',
            'link': 'https://q.qq.com',
            'switch': {'switch_id': '', 'default': False},
            'sub_menu_items': [],
        },
        {
            'name': '开关按钮',
            'type': 'switch',
            'send_message': '',
            'link': '',
            'switch': {'switch_id': 'demo_switch', 'default': True},
            'sub_menu_items': [],
        },
        {
            'name': '更多菜单',
            'type': 'menu',
            'send_message': '',
            'link': '',
            'switch': {'switch_id': '', 'default': False},
            'sub_menu_items': [
                {
                    'name': '设置',
                    'type': 'send_message',
                    'send_message': '/settings',
                    'link': '',
                },
                {
                    'name': '文档',
                    'type': 'link',
                    'send_message': '',
                    'link': 'https://bot.q.qq.com',
                },
            ],
        },
    ]


def example_panel_items() -> list:
    return [
        {
            'name': '/bot',
            'desc': '机器人版本号',
            'type': 'command',
            'only_admin': False,
            'link': '',
        },
        {
            'name': '/help',
            'desc': '查看帮助内容后可精准查询',
            'type': 'command',
            'only_admin': False,
            'link': '',
        },
        {
            'name': '/status',
            'desc': '查询当前状态',
            'type': 'command',
            'only_admin': False,
            'link': '',
        },
        {
            'name': '/draw',
            'desc': '随机抽卡',
            'type': 'command',
            'only_admin': False,
            'link': '',
        },
        {
            'name': '更多服务',
            'desc': '打开服务页面',
            'type': 'link',
            'only_admin': False,
            'link': 'https://q.qq.com',
        },
    ]


def normalize_switch(raw_switch) -> dict:
    if not isinstance(raw_switch, dict):
        raw_switch = {}
    return {
        'switch_id': safe_str(raw_switch.get('switch_id', '')),
        'default': bool(raw_switch.get('default', False)),
    }


def normalize_sub_menu_item(raw_item) -> dict:
    if not isinstance(raw_item, dict):
        raw_item = {}
    item_type = safe_str(raw_item.get('type', 'send_message'))
    if item_type not in ['send_message', 'link']:
        item_type = 'send_message'
    return {
        'name': safe_str(raw_item.get('name', '')),
        'type': item_type,
        'send_message': safe_str(raw_item.get('send_message', '')),
        'link': safe_str(raw_item.get('link', '')),
    }


def normalize_menu_item(raw_item) -> dict:
    if not isinstance(raw_item, dict):
        raw_item = {}
    item_type = safe_str(raw_item.get('type', 'send_message'))
    if item_type not in ['send_message', 'link', 'switch', 'menu']:
        item_type = 'send_message'
    sub_items = raw_item.get('sub_menu_items', [])
    if not isinstance(sub_items, list):
        sub_items = []
    return {
        'name': safe_str(raw_item.get('name', '')),
        'type': item_type,
        'send_message': safe_str(raw_item.get('send_message', '')),
        'link': safe_str(raw_item.get('link', '')),
        'switch': normalize_switch(raw_item.get('switch', {})),
        'sub_menu_items': [normalize_sub_menu_item(item) for item in sub_items],
    }


def normalize_panel_item(raw_item) -> dict:
    if not isinstance(raw_item, dict):
        raw_item = {}
    item_type = safe_str(raw_item.get('type', 'command'))
    if item_type not in ['command', 'link']:
        item_type = 'command'
    return {
        'name': safe_str(raw_item.get('name', '')),
        'desc': safe_str(raw_item.get('desc', '')),
        'type': item_type,
        'only_admin': bool(raw_item.get('only_admin', False)),
        'link': safe_str(raw_item.get('link', '')),
    }


def normalize_panel_record(raw_record, fallback_scope: str = config.SCOPE_C2C) -> dict:
    if not isinstance(raw_record, dict):
        raw_record = {}
    panel = raw_record.get('panel', raw_record)
    if not isinstance(panel, dict):
        panel = {}
    items = panel.get('items', raw_record.get('items', []))
    if not isinstance(items, list):
        items = []
    scope = safe_str(raw_record.get('scope', fallback_scope)) or fallback_scope
    target_type = safe_str(raw_record.get('target_type', 'all')) or 'all'
    if scope in [config.SCOPE_CHANNEL, config.SCOPE_DM]:
        target_type = 'all'
    if target_type not in ['all', 'specific']:
        target_type = 'all'
    user_openids = raw_record.get('user_openids', [])
    group_openids = raw_record.get('group_openids', [])
    if not isinstance(user_openids, list):
        user_openids = []
    if not isinstance(group_openids, list):
        group_openids = []
    return {
        'local_id': safe_str(raw_record.get('local_id', '')) or new_local_id(),
        'panel_id': safe_str(raw_record.get('panel_id', '')),
        'scope': scope,
        'target_type': target_type,
        'remark': safe_str(panel.get('remark', raw_record.get('remark', ''))),
        'version': raw_record.get('version', panel.get('version', None)),
        'items': [normalize_panel_item(item) for item in items],
        'user_openids': [safe_str(item) for item in user_openids if safe_str(item)],
        'group_openids': [safe_str(item) for item in group_openids if safe_str(item)],
        'created_at': safe_str(raw_record.get('created_at', '')),
        'updated_at': safe_str(raw_record.get('updated_at', '')),
        'dirty': bool(raw_record.get('dirty', False)),
    }


def normalize_menu_draft(raw_draft) -> dict:
    if not isinstance(raw_draft, dict):
        raw_draft = {}
    menu = raw_draft.get('menu', raw_draft)
    if not isinstance(menu, dict):
        menu = {}
    items = menu.get('items', raw_draft.get('items', []))
    if not isinstance(items, list):
        items = []
    return {
        'items': [normalize_menu_item(item) for item in items],
        'version': raw_draft.get('version', menu.get('version', None)),
    }


def build_menu_item_payload(item: dict) -> dict:
    item = normalize_menu_item(item)
    payload = {
        'name': item['name'],
        'type': item['type'],
    }
    if item['type'] == 'send_message':
        payload['send_message'] = item['send_message']
    elif item['type'] == 'link':
        payload['link'] = item['link']
    elif item['type'] == 'switch':
        payload['switch'] = {
            'switch_id': item['switch']['switch_id'],
            'default': bool(item['switch']['default']),
        }
    elif item['type'] == 'menu':
        sub_payload = []
        for sub_item in item['sub_menu_items'][:config.SUB_MENU_ITEM_MAX]:
            sub_item = normalize_sub_menu_item(sub_item)
            one = {
                'name': sub_item['name'],
                'type': sub_item['type'],
            }
            if sub_item['type'] == 'send_message':
                one['send_message'] = sub_item['send_message']
            elif sub_item['type'] == 'link':
                one['link'] = sub_item['link']
            sub_payload.append(one)
        payload['sub_menu_items'] = sub_payload
    return payload


def build_menu_payload(items) -> dict:
    if not isinstance(items, list):
        items = []
    return {
        'items': [build_menu_item_payload(item) for item in items[:config.MENU_ITEM_MAX]],
    }


def build_panel_item_payload(item: dict) -> dict:
    item = normalize_panel_item(item)
    payload = {
        'name': item['name'],
        'desc': item['desc'],
        'type': item['type'],
        'only_admin': bool(item['only_admin']),
    }
    if item['type'] == 'link':
        payload['link'] = item['link']
    return payload


def build_panel_payload(record: dict) -> dict:
    record = normalize_panel_record(record)
    payload = {
        'items': [build_panel_item_payload(item) for item in record['items'][:config.PANEL_ITEM_MAX]],
        'remark': record['remark'][:config.PANEL_REMARK_MAX],
    }
    if record.get('version') not in [None, '']:
        try:
            payload['version'] = int(record['version'])
        except (TypeError, ValueError):
            pass
    return payload


def _check_link(link: str, field_name: str, errors: list) -> None:
    if not link:
        errors.append(f'{field_name} 缺少跳转链接')
        return
    if not link.startswith(config.LINK_PREFIX):
        errors.append(f'{field_name} 的链接必须以 {config.LINK_PREFIX} 开头')


def validate_sub_menu_item(item: dict, index: int) -> list:
    errors = []
    prefix = f'子菜单第 {index + 1} 项'
    item = normalize_sub_menu_item(item)
    if not item['name']:
        errors.append(f'{prefix} 缺少名称')
    elif qq_char_width(item['name']) > config.SUB_MENU_NAME_WIDTH_MAX:
        errors.append(f'{prefix} 名称超过 {config.SUB_MENU_NAME_WIDTH_MAX} 个字符（中文按 2 计）')
    if item['type'] == 'send_message' and not item['send_message']:
        errors.append(f'{prefix} 缺少发送内容')
    if item['type'] == 'link':
        _check_link(item['link'], prefix, errors)
    if item['type'] not in ['send_message', 'link']:
        errors.append(f'{prefix} 类型只能是 send_message 或 link')
    return errors


def validate_menu_item(item: dict, index: int) -> list:
    errors = []
    prefix = f'菜单第 {index + 1} 项'
    item = normalize_menu_item(item)
    if not item['name']:
        errors.append(f'{prefix} 缺少名称')
    elif qq_char_width(item['name']) > config.MENU_NAME_WIDTH_MAX:
        errors.append(f'{prefix} 名称超过 {config.MENU_NAME_WIDTH_MAX} 个字符（中文按 2 计）')
    if item['type'] == 'send_message' and not item['send_message']:
        errors.append(f'{prefix} 缺少发送内容')
    if item['type'] == 'link':
        _check_link(item['link'], prefix, errors)
    if item['type'] == 'switch':
        if not item['switch']['switch_id']:
            errors.append(f'{prefix} 缺少 switch_id')
    if item['type'] == 'menu':
        sub_items = item['sub_menu_items']
        if len(sub_items) == 0:
            errors.append(f'{prefix} 子菜单不能为空')
        if len(sub_items) > config.SUB_MENU_ITEM_MAX:
            errors.append(f'{prefix} 子菜单最多 {config.SUB_MENU_ITEM_MAX} 个')
        for sub_index, sub_item in enumerate(sub_items):
            errors.extend(validate_sub_menu_item(sub_item, sub_index))
    if item['type'] not in ['send_message', 'link', 'switch', 'menu']:
        errors.append(f'{prefix} 类型不合法')
    return errors


def validate_menu_draft(items) -> list:
    errors = []
    if not isinstance(items, list):
        return ['菜单项必须是列表']
    if len(items) > config.MENU_ITEM_MAX:
        errors.append(f'自定义菜单最多 {config.MENU_ITEM_MAX} 项')
    for index, item in enumerate(items):
        errors.extend(validate_menu_item(item, index))
    return errors


def validate_panel_item(item: dict, index: int) -> list:
    errors = []
    prefix = f'面板第 {index + 1} 项'
    item = normalize_panel_item(item)
    if not item['name']:
        errors.append(f'{prefix} 缺少名称')
    elif qq_char_width(item['name']) > config.PANEL_NAME_WIDTH_MAX:
        errors.append(f'{prefix} 名称超过 {config.PANEL_NAME_WIDTH_MAX} 个字符（中文按 2 计）')
    if qq_char_width(item['desc']) > config.PANEL_DESC_WIDTH_MAX:
        errors.append(f'{prefix} 描述超过 {config.PANEL_DESC_WIDTH_MAX} 个字符（中文按 2 计）')
    if item['type'] == 'link':
        _check_link(item['link'], prefix, errors)
    if item['type'] not in ['command', 'link']:
        errors.append(f'{prefix} 类型只能是 command 或 link')
    return errors


def validate_panel_record(record: dict) -> list:
    errors = []
    record = normalize_panel_record(record)
    if record['scope'] not in config.SCOPE_LIST:
        errors.append('生效场景只能是 c2c/group/channel/dm')
    if record['target_type'] not in ['all', 'specific']:
        errors.append('作用范围只能是 all 或 specific')
    if record['scope'] in [config.SCOPE_CHANNEL, config.SCOPE_DM] and record['target_type'] != 'all':
        errors.append('QQ 频道和频道私信只支持全局配置（target_type=all）')
    if record['target_type'] == 'specific' and record['scope'] not in [config.SCOPE_C2C, config.SCOPE_GROUP]:
        errors.append('只有消息列表和 QQ 群支持指定对象')
    if record['target_type'] == 'specific':
        if record['scope'] == config.SCOPE_C2C and not record['user_openids']:
            errors.append('指定用户生效时至少需要一个 user_openid')
        if record['scope'] == config.SCOPE_GROUP and not record['group_openids']:
            errors.append('指定群生效时至少需要一个 group_openid')
    if len(record['remark']) > config.PANEL_REMARK_MAX:
        errors.append(f'面板备注最多 {config.PANEL_REMARK_MAX} 个字符')
    if len(record['items']) == 0:
        errors.append('指令面板至少需要一个元素')
    if len(record['items']) > config.PANEL_ITEM_MAX:
        errors.append(f'一个指令面板最多 {config.PANEL_ITEM_MAX} 个元素')
    for index, item in enumerate(record['items']):
        errors.extend(validate_panel_item(item, index))
    return errors


def chunk_list(value_list, size: int) -> list:
    if not isinstance(value_list, list):
        return []
    return [value_list[index:index + size] for index in range(0, len(value_list), size)]


def summarize_menu(items) -> str:
    names = []
    for item in items or []:
        name = safe_str(item.get('name', ''))
        item_type = safe_str(item.get('type', ''))
        names.append(f'{name}({item_type})' if name else item_type)
    return '、'.join(names) if names else '（空菜单）'


def summarize_panel(record: dict) -> str:
    record = normalize_panel_record(record)
    remark = record['remark'] or '未备注'
    panel_id = record['panel_id'] or '未提交'
    return (
        f'{remark} | {config.SCOPE_LABEL_DICT.get(record["scope"], record["scope"])} | '
        f'{record["target_type"]} | {len(record["items"])} 项 | {panel_id}'
    )


def flatten_commands(menu_draft: dict, panel_drafts: dict) -> list:
    """把当前草稿里的每个指令摊平成浏览列表。"""
    rows = []
    for index, item in enumerate(normalize_menu_draft(menu_draft)['items']):
        rows.append({
            'source': '自定义菜单',
            'scope': config.SCOPE_C2C,
            'panel_id': '',
            'index': index,
            'name': item['name'],
            'type': item['type'],
            'desc': item.get('send_message') or item.get('link') or item['switch']['switch_id'],
            'only_admin': False,
        })
        if item['type'] == 'menu':
            for sub_index, sub_item in enumerate(item['sub_menu_items']):
                rows.append({
                    'source': '自定义菜单/子菜单',
                    'scope': config.SCOPE_C2C,
                    'panel_id': '',
                    'index': index,
                    'sub_index': sub_index,
                    'name': sub_item['name'],
                    'type': sub_item['type'],
                    'desc': sub_item.get('send_message') or sub_item.get('link'),
                    'only_admin': False,
                })
    if not isinstance(panel_drafts, dict):
        panel_drafts = {}
    for scope in config.SCOPE_LIST:
        for panel in panel_drafts.get(scope, []):
            panel = normalize_panel_record(panel, fallback_scope=scope)
            for index, item in enumerate(panel['items']):
                rows.append({
                    'source': '指令面板',
                    'scope': scope,
                    'panel_id': panel['panel_id'],
                    'local_id': panel['local_id'],
                    'index': index,
                    'name': item['name'],
                    'type': item['type'],
                    'desc': item['desc'] or item.get('link', ''),
                    'only_admin': item['only_admin'],
                })
    return rows


def deepcopy_data(value):
    return copy.deepcopy(value)
