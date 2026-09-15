# -*- encoding: utf-8 -*-
"""本地 WebUI 服务。默认 127.0.0.1:3738，地址和端口可改。"""

import logging
import os
import threading
import time
import webbrowser

from . import api_bridge
from . import config
from . import function
from . import help_docs
from . import utils

_lock = threading.RLock()
_server = None
_thread = None
_app = None


def normalize_host(host) -> str:
    text = utils.safe_str(host).strip()
    if not text:
        return config.webui_default_host
    return text


def normalize_port(port) -> int:
    try:
        value = int(port)
    except (TypeError, ValueError):
        return config.webui_default_port
    if value <= 0 or value > 65535:
        return config.webui_default_port
    return value


def get_webui_host() -> str:
    return normalize_host(utils.load_global_config().get('webui_host', config.webui_default_host))


def get_webui_port() -> int:
    return normalize_port(utils.load_global_config().get('webui_port', config.webui_default_port))


def get_browser_host() -> str:
    host = get_webui_host()
    if host in ['0.0.0.0', '::', '[::]', '*']:
        return '127.0.0.1'
    return host


def get_webui_url() -> str:
    return 'http://%s:%s' % (get_browser_host(), get_webui_port())


def is_enabled() -> bool:
    return bool(utils.load_global_config().get('webui_enable_switch', False))


def is_running() -> bool:
    with _lock:
        return _server is not None


def apply_settings(host, port, enabled: bool) -> dict:
    global_config = utils.load_global_config()
    global_config['webui_host'] = normalize_host(host)
    global_config['webui_port'] = normalize_port(port)
    global_config['webui_enable_switch'] = bool(enabled)
    utils.save_global_config(global_config)
    if enabled:
        if is_running():
            stop()
        return start()
    return stop()


def set_enabled(flag: bool) -> dict:
    return apply_settings(get_webui_host(), get_webui_port(), bool(flag))


def start() -> dict:
    global _server, _thread, _app
    with _lock:
        if _server is not None:
            return {'ok': True, 'running': True, 'url': get_webui_url(), 'message': 'WebUI 已在运行'}
        try:
            import flask  # noqa: F401
            from werkzeug.serving import make_server
        except Exception as exception_object:
            return {
                'ok': False,
                'running': False,
                'url': get_webui_url(),
                'message': '当前环境没有 Flask/Werkzeug：%s' % exception_object,
            }
        host = get_webui_host()
        port = get_webui_port()
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        last_error = None
        for attempt in range(2):
            try:
                _app = _create_app()
                _server = make_server(host, port, _app, threaded=True)
                _thread = threading.Thread(target=_server.serve_forever, daemon=True)
                _thread.start()
                utils.info_log(
                    utils.get_runtime_proc(),
                    'WebUI 已启动：%s （监听 %s:%s）' % (get_webui_url(), host, port),
                )
                return {'ok': True, 'running': True, 'url': get_webui_url(), 'message': 'WebUI 已启动'}
            except Exception as exception_object:
                last_error = exception_object
                _server = None
                _thread = None
                _app = None
                if attempt == 0:
                    time.sleep(0.5)
        return {
            'ok': False,
            'running': False,
            'url': get_webui_url(),
            'message': '启动失败：%s' % last_error,
        }


def stop() -> dict:
    global _server, _thread, _app
    with _lock:
        server = _server
        thread = _thread
        if server is None:
            return {'ok': True, 'running': False, 'url': get_webui_url(), 'message': 'WebUI 未在运行'}
        _server = None
        _thread = None
        _app = None
    try:
        server.shutdown()
    except Exception:
        pass
    try:
        server.server_close()
    except Exception:
        pass
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)
    utils.info_log(utils.get_runtime_proc(), 'WebUI 已停止')
    return {'ok': True, 'running': False, 'url': get_webui_url(), 'message': 'WebUI 已停止'}


def _schedule_restart() -> None:
    def worker():
        time.sleep(0.4)
        try:
            if is_running():
                stop()
            if is_enabled():
                start()
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()


def summarize_api_result(api_result) -> dict:
    items = []

    def add_item(label, result):
        if isinstance(result, dict) and 'active' in result:
            data = result.get('data', {}) if isinstance(result.get('data'), dict) else {}
            detail = utils.safe_str(
                data.get('error')
                or data.get('http_status')
                or ('成功' if result.get('active') else '失败'),
            )
            items.append({'label': label, 'ok': bool(result.get('active')), 'detail': detail})
            return True
        return False

    if isinstance(api_result, list):
        for index, result in enumerate(api_result):
            add_item('第 %s 批' % (index + 1), result)
    elif isinstance(api_result, dict):
        if not add_item('请求', api_result):
            for key, value in api_result.items():
                label = config.SCOPE_LABEL_DICT.get(key, utils.safe_str(key))
                if isinstance(value, list):
                    for index, result in enumerate(value):
                        add_item('%s 第 %s 批' % (label, index + 1), result)
                else:
                    add_item(label, value)
    success = len([item for item in items if item.get('ok')])
    return {
        'success': success,
        'failed': len(items) - success,
        'total': len(items),
        'items': items,
    }


def sync_from_config() -> dict:
    if is_enabled():
        return start()
    return stop()


def open_in_browser() -> None:
    try:
        webbrowser.open(get_webui_url())
    except Exception:
        pass


def _get_bots():
    Proc = utils.get_runtime_proc()
    bot_info_dict = {}
    if Proc is not None:
        bot_info_dict = getattr(Proc, 'Proc_data', {}).get('bot_info_dict', {})
    filtered = utils.filter_qqguildv2_bots(bot_info_dict)
    bots = []
    for bot_hash, bot_info in filtered.items():
        bots.append({
            'hash': utils.safe_str(bot_hash),
            'display': utils.get_bot_display_text(bot_hash, bot_info=bot_info),
            'id': utils.safe_str(getattr(bot_info, 'id', '')),
            'name': (
                utils.safe_str(getattr(bot_info, 'name', ''))
                or ('Bot ' + utils.safe_str(getattr(bot_info, 'id', '')))
            ),
        })
    bots.sort(key=lambda item: item['display'])
    return bots, filtered


def _get_bot_info(bot_hash: str):
    _bots, filtered = _get_bots()
    return filtered.get(utils.safe_str(bot_hash))


def _snapshot(bot_hash: str) -> dict:
    global_config = utils.load_global_config()
    bots, _filtered = _get_bots()
    if not bot_hash and bots:
        bot_hash = bots[0]['hash']
    bot_config = utils.load_bot_config(bot_hash) if bot_hash else utils.normalize_bot_config({})
    return {
        'url': get_webui_url(),
        'running': is_running(),
        'enabled': is_enabled(),
        'host': get_webui_host(),
        'port': get_webui_port(),
        'bind_host': get_webui_host(),
        'global_enable_switch': bool(global_config.get('global_enable_switch', True)),
        'global_debug_mode_switch': bool(global_config.get('global_debug_mode_switch', False)),
        'bots': bots,
        'current_bot_hash': bot_hash,
        'bot_enable_switch': bool(bot_config.get('bot_enable_switch', True)),
        'unified_panel_mode': bool(bot_config.get('unified_panel_mode', False)),
        'chat_current_scope': bot_config.get('chat_current_scope', config.SCOPE_C2C),
        'menu_draft': function.normalize_menu_draft(bot_config.get('menu_draft', {})),
        'panel_drafts': bot_config.get('panel_drafts', {}),
        'core_masters': utils.get_olivadice_master_id_list(bot_hash),
        'plugin_masters': utils.get_configured_master_list(bot_hash),
        'has_olivadice': utils.has_oliva_dice_core,
        'help_text': help_docs.get_help_markdown(),
        'field_hints': help_docs.FIELD_HINT_DICT,
        'scope_labels': config.SCOPE_LABEL_DICT,
        'menu_type_options': [{'value': item[0], 'label': item[1]} for item in help_docs.MENU_TYPE_OPTIONS],
        'sub_menu_type_options': [{'value': item[0], 'label': item[1]} for item in help_docs.SUB_MENU_TYPE_OPTIONS],
        'panel_item_type_options': [{'value': item[0], 'label': item[1]} for item in help_docs.PANEL_ITEM_TYPE_OPTIONS],
        'target_type_options': [{'value': item[0], 'label': item[1]} for item in help_docs.TARGET_TYPE_OPTIONS],
        'limits': {
            'menu_item_max': config.MENU_ITEM_MAX,
            'sub_menu_item_max': config.SUB_MENU_ITEM_MAX,
            'panel_item_max': config.PANEL_ITEM_MAX,
            'panel_max': config.PANEL_MAX_PER_BOT,
        },
    }


def _save_draft(bot_hash: str, payload: dict) -> dict:
    bot_config = utils.load_bot_config(bot_hash)
    if 'menu_draft' in payload:
        bot_config['menu_draft'] = function.normalize_menu_draft(payload.get('menu_draft', {}))
    if 'panel_drafts' in payload:
        panel_drafts = payload.get('panel_drafts', {})
        if isinstance(panel_drafts, dict):
            normalized = {}
            for scope in config.SCOPE_LIST:
                records = panel_drafts.get(scope, [])
                if not isinstance(records, list):
                    records = []
                normalized[scope] = [
                    function.normalize_panel_record(record, fallback_scope=scope) for record in records
                ]
            bot_config['panel_drafts'] = normalized
    if 'unified_panel_mode' in payload:
        bot_config['unified_panel_mode'] = bool(payload.get('unified_panel_mode'))
    if 'chat_current_scope' in payload:
        scope = utils.safe_str(payload.get('chat_current_scope'))
        if scope in config.SCOPE_LIST:
            bot_config['chat_current_scope'] = scope
    if 'bot_enable_switch' in payload:
        bot_config['bot_enable_switch'] = bool(payload.get('bot_enable_switch'))
    utils.save_bot_config(bot_hash, bot_config)
    return bot_config


def _pull_menu(bot_hash: str, bot_info) -> dict:
    result = api_bridge.fetch_global_menu(bot_info, utils.get_runtime_proc())
    if result.get('active'):
        response = api_bridge.get_response_data(result)
        bot_config = utils.load_bot_config(bot_hash)
        bot_config['menu_draft'] = function.normalize_menu_draft(
            response if isinstance(response, dict) else {},
        )
        utils.save_bot_config(bot_hash, bot_config)
    return result


def _pull_panels(bot_hash: str, bot_info, scopes) -> dict:
    if 'all' in (scopes or []):
        scopes = list(config.SCOPE_LIST)
    bot_config = utils.load_bot_config(bot_hash)
    results = {}
    for scope in scopes:
        if scope not in config.SCOPE_LIST:
            continue
        result = api_bridge.fetch_panel_list(bot_info, scope, utils.get_runtime_proc())
        results[scope] = result
        if not result.get('active'):
            continue
        response = api_bridge.get_response_data(result)
        records = response.get('records', []) if isinstance(response, dict) else []
        detailed = []
        for raw_record in records:
            panel_id = utils.safe_str(raw_record.get('panel_id', ''))
            if panel_id:
                detail = api_bridge.fetch_panel_detail(bot_info, panel_id, utils.get_runtime_proc())
                detail_data = api_bridge.get_response_data(detail)
                detailed.append(detail_data if isinstance(detail_data, dict) else raw_record)
            else:
                detailed.append(raw_record)
        bot_config['panel_drafts'][scope] = [
            function.normalize_panel_record(item, fallback_scope=scope) for item in detailed
        ]
    utils.save_bot_config(bot_hash, bot_config)
    return results


def _json_ok(data=None, message=''):
    from flask import jsonify
    return jsonify({'ok': True, 'message': message, 'data': data if data is not None else {}})


def _json_err(message: str, code=400):
    from flask import jsonify
    return jsonify({'ok': False, 'message': message, 'data': {}}), code


def _create_app():
    from flask import Flask, request, send_from_directory

    app = Flask(__name__)
    static_dir = os.path.dirname(os.path.abspath(__file__))

    @app.after_request
    def _no_store(response):
        if request.path in ['/', '/webui.html']:
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/')
    def index():
        return send_from_directory(static_dir, 'webui.html')

    @app.route('/api/state')
    def api_state():
        bot_hash = utils.safe_str(request.args.get('bot_hash', ''))
        return _json_ok(_snapshot(bot_hash))

    @app.route('/api/draft', methods=['POST'])
    def api_draft():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        if not bot_hash:
            return _json_err('缺少 bot_hash')
        _save_draft(bot_hash, payload)
        return _json_ok(_snapshot(bot_hash), '草稿已保存')

    @app.route('/api/global', methods=['POST'])
    def api_global():
        payload = request.get_json(silent=True) or {}
        old_host = get_webui_host()
        old_port = get_webui_port()
        global_config = utils.load_global_config()
        if 'global_enable_switch' in payload:
            global_config['global_enable_switch'] = bool(payload.get('global_enable_switch'))
        if 'global_debug_mode_switch' in payload:
            global_config['global_debug_mode_switch'] = bool(payload.get('global_debug_mode_switch'))
        if 'webui_host' in payload:
            global_config['webui_host'] = normalize_host(payload.get('webui_host'))
        if 'webui_port' in payload:
            global_config['webui_port'] = normalize_port(payload.get('webui_port'))
        utils.save_global_config(global_config)
        bind_changed = get_webui_host() != old_host or get_webui_port() != old_port
        message = '全局设置已保存'
        if bind_changed:
            message = '监听地址已更改，正在重启 WebUI。请用 %s 重新打开。' % get_webui_url()
            if is_enabled() or is_running():
                _schedule_restart()
        data = _snapshot(utils.safe_str(payload.get('bot_hash', '')))
        data['restarted'] = bind_changed
        return _json_ok(data, message)

    @app.route('/api/master', methods=['POST'])
    def api_master():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        op = utils.safe_str(payload.get('op', ''))
        master_id = utils.safe_str(payload.get('master_id', '')).strip()
        if not bot_hash:
            return _json_err('缺少 bot_hash')
        master_list = utils.get_configured_master_list(bot_hash)
        if op == 'add' and master_id and master_id not in master_list:
            master_list.append(master_id)
            utils.set_configured_master_list(bot_hash, master_list)
        elif op == 'del' and master_id:
            master_list = [item for item in master_list if item != master_id]
            utils.set_configured_master_list(bot_hash, master_list)
        else:
            return _json_err('操作无效')
        return _json_ok(_snapshot(bot_hash), '插件骰主已更新')

    @app.route('/api/menu/pull', methods=['POST'])
    def api_menu_pull():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        bot_info = _get_bot_info(bot_hash)
        if bot_info is None:
            return _json_err('请选择 qqGuildV2 Bot')
        result = _pull_menu(bot_hash, bot_info)
        data = _snapshot(bot_hash)
        data['api_result'] = result
        return _json_ok(data)

    @app.route('/api/menu/send', methods=['POST'])
    def api_menu_send():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        bot_info = _get_bot_info(bot_hash)
        if bot_info is None:
            return _json_err('请选择 qqGuildV2 Bot')
        _save_draft(bot_hash, payload)
        bot_config = utils.load_bot_config(bot_hash)
        items = bot_config.get('menu_draft', {}).get('items', [])
        errors = function.validate_menu_draft(items)
        if errors:
            return _json_err('校验失败：' + '；'.join(errors[:8]))
        result = api_bridge.send_global_menu(bot_info, items, utils.get_runtime_proc())
        version = api_bridge.extract_version(result)
        if result.get('active') and version is not None:
            bot_config['menu_draft']['version'] = version
            utils.save_bot_config(bot_hash, bot_config)
        data = _snapshot(bot_hash)
        data['api_result'] = result
        data['send_summary'] = summarize_api_result(result)
        return _json_ok(data)

    @app.route('/api/panel/pull', methods=['POST'])
    def api_panel_pull():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        bot_info = _get_bot_info(bot_hash)
        if bot_info is None:
            return _json_err('请选择 qqGuildV2 Bot')
        scopes = payload.get('scopes') or [payload.get('scope', config.SCOPE_C2C)]
        results = _pull_panels(bot_hash, bot_info, scopes)
        data = _snapshot(bot_hash)
        data['api_result'] = results
        return _json_ok(data)

    @app.route('/api/bootstrap', methods=['POST'])
    def api_bootstrap():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        bots, _filtered = _get_bots()
        if not bot_hash and bots:
            bot_hash = bots[0]['hash']
        bot_info = _get_bot_info(bot_hash) if bot_hash else None
        results = {}
        if bot_info is None:
            data = _snapshot(bot_hash)
            data['api_result'] = results
            return _json_ok(data, '没有可拉取的 qqGuildV2 Bot，已显示本地草稿')
        results['menu'] = _pull_menu(bot_hash, bot_info)
        results['panels'] = _pull_panels(bot_hash, bot_info, ['all'])
        data = _snapshot(bot_hash)
        data['api_result'] = results
        menu_ok = bool(results['menu'].get('active'))
        panel_ok = any(item.get('active') for item in results['panels'].values())
        if menu_ok or panel_ok:
            message = '已拉取平台当前配置'
        else:
            message = '平台拉取未成功，已显示本地草稿'
        return _json_ok(data, message)

    @app.route('/api/panel/send', methods=['POST'])
    def api_panel_send():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        bot_info = _get_bot_info(bot_hash)
        if bot_info is None:
            return _json_err('请选择 qqGuildV2 Bot')
        _save_draft(bot_hash, payload)
        bot_config = utils.load_bot_config(bot_hash)
        unified = bool(payload.get('unified_panel_mode', bot_config.get('unified_panel_mode', False)))
        scope = utils.safe_str(payload.get('scope', bot_config.get('chat_current_scope', config.SCOPE_C2C)))
        if scope not in config.SCOPE_LIST:
            scope = config.SCOPE_C2C
        panels = bot_config.get('panel_drafts', {}).get(scope, [])
        index = int(payload.get('panel_index', 0) or 0)
        if index < 0 or index >= len(panels):
            return _json_err('请先选择或新建指令面板')
        record = panels[index]
        errors = function.validate_panel_record(record)
        if errors:
            return _json_err('校验失败：' + '；'.join(errors[:8]))
        results = {}
        if unified:
            for one_scope in config.SCOPE_LIST:
                scoped = function.normalize_panel_record(record, fallback_scope=one_scope)
                scoped['scope'] = one_scope
                existing = bot_config['panel_drafts'].get(one_scope, [])
                if existing:
                    scoped['panel_id'] = existing[0].get('panel_id', '')
                if one_scope in [config.SCOPE_CHANNEL, config.SCOPE_DM]:
                    scoped['target_type'] = 'all'
                    scoped['user_openids'] = []
                    scoped['group_openids'] = []
                if scoped.get('panel_id'):
                    result = api_bridge.update_panel(bot_info, scoped, utils.get_runtime_proc())
                else:
                    result = api_bridge.create_panel(bot_info, scoped, utils.get_runtime_proc())
                results[one_scope] = result
                if result.get('active') and existing:
                    existing[0]['panel_id'] = api_bridge.extract_panel_id(result) or scoped.get('panel_id', '')
                    existing[0]['version'] = api_bridge.extract_version(result)
                    existing[0]['items'] = function.deepcopy_data(record.get('items', []))
                    existing[0]['remark'] = record.get('remark', '')
        else:
            if record.get('panel_id'):
                result = api_bridge.update_panel(bot_info, record, utils.get_runtime_proc())
            else:
                result = api_bridge.create_panel(bot_info, record, utils.get_runtime_proc())
            results[scope] = result
            if result.get('active'):
                panel_id = api_bridge.extract_panel_id(result)
                if panel_id:
                    record['panel_id'] = panel_id
                version = api_bridge.extract_version(result)
                if version is not None:
                    record['version'] = version
        utils.save_bot_config(bot_hash, bot_config)
        data = _snapshot(bot_hash)
        data['api_result'] = results
        data['send_summary'] = summarize_api_result(results)
        return _json_ok(data)

    @app.route('/api/panel/delete', methods=['POST'])
    def api_panel_delete():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        bot_info = _get_bot_info(bot_hash)
        if bot_info is None:
            return _json_err('请选择 qqGuildV2 Bot')
        panel_id = utils.safe_str(payload.get('panel_id', ''))
        if not panel_id:
            return _json_err('没有 panel_id')
        result = api_bridge.delete_panel(bot_info, panel_id, utils.get_runtime_proc())
        if result.get('active'):
            bot_config = utils.load_bot_config(bot_hash)
            for scope in config.SCOPE_LIST:
                records = bot_config.get('panel_drafts', {}).get(scope, [])
                bot_config['panel_drafts'][scope] = [
                    record for record in records if utils.safe_str(record.get('panel_id', '')) != panel_id
                ]
            utils.save_bot_config(bot_hash, bot_config)
        data = _snapshot(bot_hash)
        data['api_result'] = result
        data['send_summary'] = summarize_api_result(result)
        return _json_ok(data)

    @app.route('/api/panel/target', methods=['POST'])
    def api_panel_target():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        bot_info = _get_bot_info(bot_hash)
        if bot_info is None:
            return _json_err('请选择 qqGuildV2 Bot')
        _save_draft(bot_hash, payload)
        bot_config = utils.load_bot_config(bot_hash)
        scope = utils.safe_str(payload.get('scope', config.SCOPE_C2C))
        panels = bot_config.get('panel_drafts', {}).get(scope, [])
        index = int(payload.get('panel_index', 0) or 0)
        if index < 0 or index >= len(panels):
            return _json_err('请先选择指令面板')
        record = panels[index]
        op = utils.safe_str(payload.get('op', 'add'))
        if record.get('target_type') != 'specific' or not record.get('panel_id'):
            return _json_err('只有已提交的 specific 面板才能改关联对象')
        if scope == config.SCOPE_C2C:
            openids = record.get('user_openids', [])
        else:
            openids = record.get('group_openids', [])
        results = api_bridge.update_panel_targets(bot_info, record, op, openids, utils.get_runtime_proc())
        data = _snapshot(bot_hash)
        data['api_result'] = results
        data['send_summary'] = summarize_api_result(results)
        return _json_ok(data)

    @app.route('/api/example', methods=['POST'])
    def api_example():
        payload = request.get_json(silent=True) or {}
        bot_hash = utils.safe_str(payload.get('bot_hash', ''))
        kind = utils.safe_str(payload.get('kind', 'menu'))
        bot_config = utils.load_bot_config(bot_hash)
        if kind == 'menu':
            bot_config['menu_draft'] = {'items': function.example_menu_items(), 'version': None}
        else:
            scope = utils.safe_str(payload.get('scope', config.SCOPE_C2C))
            if scope not in config.SCOPE_LIST:
                scope = config.SCOPE_C2C
            records = bot_config.setdefault('panel_drafts', {}).setdefault(scope, [])
            if not records:
                records.append(function.empty_panel_record(scope))
            records[0]['items'] = function.example_panel_items()
            records[0]['remark'] = records[0].get('remark') or '示例面板'
        utils.save_bot_config(bot_hash, bot_config)
        return _json_ok(_snapshot(bot_hash), '已填入示例')

    return app
