# -*- encoding: utf-8 -*-
"""只通过 OlivOS 暴露的 indeAPI 调用官方菜单/面板能力。"""

import OlivOS

from . import config
from . import function
from . import utils

REQUIRED_API_LIST = [
    'get_qq_global_menu',
    'set_qq_global_menu',
    'get_qq_command_panel_list',
    'create_qq_command_panel',
    'get_qq_command_panel',
    'set_qq_command_panel',
    'delete_qq_command_panel',
    'set_qq_command_panel_target',
]


def make_local_error(operation: str, error: str) -> dict:
    return {
        'active': False,
        'data': {
            'operation': operation,
            'http_status': None,
            'error_code': None,
            'error': error,
            'response': None,
        },
    }


def create_bot_event(bot_info, Proc=None):
    """用 fake_sdk_event 构造带 indeAPI 的 OlivOS Event。"""
    Proc = Proc or utils.get_runtime_proc()
    if bot_info is None:
        return None
    try:
        log_func = Proc.log if Proc is not None and hasattr(Proc, 'log') else None
        return OlivOS.API.Event(
            OlivOS.contentAPI.fake_sdk_event(
                bot_info=bot_info,
                fakename=config.plugin_name,
                plugin_namespace=config.plugin_name,
            ),
            log_func,
            Proc=Proc,
        )
    except Exception as exception_object:
        utils.error_log(Proc, f'构造 Bot 事件失败：{utils.exception_text(exception_object)}')
        return None


def get_missing_api_list(plugin_event) -> list:
    missing_list = []
    inde_api = getattr(plugin_event, 'indeAPI', None)
    if inde_api is None:
        return list(REQUIRED_API_LIST)
    for api_name in REQUIRED_API_LIST:
        if not hasattr(inde_api, 'hasAPI') or not inde_api.hasAPI(api_name):
            missing_list.append(api_name)
    return missing_list


def call_bot_api(bot_info, method_name: str, Proc=None, **kwargs):
    """确认当前 OlivOS 已暴露接口后再调用，绝不直连官方 HTTP。"""
    plugin_event = create_bot_event(bot_info, Proc=Proc)
    if plugin_event is None:
        return make_local_error(method_name, '无法构造 OlivOS 事件')
    if not utils.is_qqguildv2_event(plugin_event):
        return make_local_error(method_name, '当前 Bot 不是 qqGuildV2')
    inde_api = getattr(plugin_event, 'indeAPI', None)
    if inde_api is None:
        return make_local_error(method_name, '当前事件没有 indeAPI')
    if not inde_api.hasAPI(method_name):
        return make_local_error(
            method_name,
            f'OlivOS 尚未暴露接口 {method_name}，请先更新青果主项目中的 qqGuildv2SDK',
        )
    try:
        method = getattr(inde_api, method_name)
        result = method(**kwargs)
        if isinstance(result, dict):
            return result
        return make_local_error(method_name, f'接口返回了非标准结果：{utils.safe_str(result)}')
    except Exception as exception_object:
        return make_local_error(method_name, utils.exception_text(exception_object))


def get_response_data(result: dict):
    if not isinstance(result, dict):
        return None
    data = result.get('data', {})
    if not isinstance(data, dict):
        return None
    return data.get('response', None)


def fetch_global_menu(bot_info, Proc=None) -> dict:
    return call_bot_api(bot_info, 'get_qq_global_menu', Proc=Proc)


def send_global_menu(bot_info, items, Proc=None) -> dict:
    payload = function.build_menu_payload(items)
    return call_bot_api(bot_info, 'set_qq_global_menu', Proc=Proc, menu=payload)


def fetch_panel_list(bot_info, scope: str, Proc=None) -> dict:
    records = []
    cursor = None
    last_result = None
    for _ in range(20):
        last_result = call_bot_api(
            bot_info,
            'get_qq_command_panel_list',
            Proc=Proc,
            scope=scope,
            cursor=cursor,
            limit=50,
        )
        if not last_result.get('active', False):
            return last_result
        response = get_response_data(last_result)
        page_records = []
        next_cursor = ''
        is_end = True
        if isinstance(response, dict):
            page_records = response.get('records', [])
            next_cursor = utils.safe_str(response.get('next_cursor', ''))
            is_end = bool(response.get('is_end', True))
        if isinstance(page_records, list):
            records.extend(page_records)
        if is_end or not next_cursor:
            break
        cursor = next_cursor
    if isinstance(last_result, dict):
        last_result.setdefault('data', {})
        last_result['data']['records'] = records
        response = last_result['data'].get('response', {})
        if isinstance(response, dict):
            response = dict(response)
            response['records'] = records
            last_result['data']['response'] = response
    return last_result


def fetch_panel_detail(bot_info, panel_id: str, Proc=None) -> dict:
    return call_bot_api(bot_info, 'get_qq_command_panel', Proc=Proc, panel_id=panel_id)


def create_panel(bot_info, record: dict, Proc=None) -> dict:
    record = function.normalize_panel_record(record)
    kwargs = {
        'scope': record['scope'],
        'panel': function.build_panel_payload(record),
        'target_type': record['target_type'],
    }
    if record['target_type'] == 'specific':
        if record['scope'] == config.SCOPE_C2C:
            kwargs['user_openids'] = record['user_openids'][:config.OPENID_PER_REQUEST_MAX]
        if record['scope'] == config.SCOPE_GROUP:
            kwargs['group_openids'] = record['group_openids'][:config.OPENID_PER_REQUEST_MAX]
    return call_bot_api(bot_info, 'create_qq_command_panel', Proc=Proc, **kwargs)


def update_panel(bot_info, record: dict, Proc=None) -> dict:
    record = function.normalize_panel_record(record)
    return call_bot_api(
        bot_info,
        'set_qq_command_panel',
        Proc=Proc,
        panel_id=record['panel_id'],
        panel=function.build_panel_payload(record),
    )


def delete_panel(bot_info, panel_id: str, Proc=None) -> dict:
    return call_bot_api(bot_info, 'delete_qq_command_panel', Proc=Proc, panel_id=panel_id)


def update_panel_targets(bot_info, record: dict, op: str, openids: list, Proc=None) -> list:
    record = function.normalize_panel_record(record)
    results = []
    for chunk in function.chunk_list(openids, config.OPENID_PER_REQUEST_MAX):
        kwargs = {
            'panel_id': record['panel_id'],
            'op': op,
        }
        if record['scope'] == config.SCOPE_C2C:
            kwargs['user_openids'] = chunk
        elif record['scope'] == config.SCOPE_GROUP:
            kwargs['group_openids'] = chunk
        else:
            results.append(make_local_error('set_qq_command_panel_target', '当前场景不支持关联对象'))
            break
        results.append(call_bot_api(bot_info, 'set_qq_command_panel_target', Proc=Proc, **kwargs))
    return results


def extract_panel_id(result: dict) -> str:
    response = get_response_data(result)
    if isinstance(response, dict):
        return utils.safe_str(response.get('panel_id', ''))
    return ''


def extract_version(result: dict):
    response = get_response_data(result)
    if isinstance(response, dict):
        return response.get('version', None)
    return None
