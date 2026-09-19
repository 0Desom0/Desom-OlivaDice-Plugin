"""使用 OlivOS 核心消息桥和临时数据验证接入；QQ 平台调用全部替身化。"""

import importlib
import json
import os
import queue
import shutil
import socket
import threading
import uuid
import webbrowser
import zipfile
from pathlib import Path
from types import SimpleNamespace

import OlivOS
import pytest

PLUGIN = Path(__file__).resolve().parents[1]
NAMESPACE = 'QQBotMenuPanel'


@pytest.fixture
def panel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(PLUGIN.parent))
    module = importlib.import_module(NAMESPACE)
    monkeypatch.setattr(module.utils, 'runtime_proc', None)
    monkeypatch.setattr(module.utils, 'has_oliva_dice_core', False)
    bot = OlivOS.API.bot_info_T(
        id=10001, platform_sdk='qqGuildv2_link', platform_platform='qqGuild', platform_model='public',
    )
    host = OlivOS.webUI.serverAPI.server(
        root_path=tmp_path, rx_queue=queue.Queue(), control_queue=queue.Queue(),
        bot_info_dict={bot.hash: bot},
    )
    loader = OlivOS.pluginAPI.shallow(control_queue=host.Proc_info.control_queue, bot_info_dict={bot.hash: bot})
    root = tmp_path / 'plugin/app' / NAMESPACE
    shutil.copytree(PLUGIN, root, ignore=shutil.ignore_patterns('__pycache__', 'tests'))
    manifest = json.loads((PLUGIN / 'app.json').read_text(encoding='utf-8'))
    loader.plugin_models_call_list = [NAMESPACE]
    loader.plugin_models_dict = {NAMESPACE: dict(manifest, model=module, webui_root=str(root))}
    loader.sendPluginList()
    while not host.Proc_info.control_queue.empty():
        host.consume(host.Proc_info.control_queue.get_nowait())
    calls = []

    def platform_api(bot_info, method_name, Proc=None, **kwargs):
        calls.append((method_name, kwargs))
        if method_name == 'get_qq_global_menu':
            response = {'items': module.function.example_menu_items(), 'version': 1}
        elif method_name == 'get_qq_command_panel_list':
            response = {'records': [], 'is_end': True}
        else:
            response = {'panel_id': 'panel-test', 'version': 2}
        return {'active': True, 'data': {'response': response, 'http_status': 200}}

    monkeypatch.setattr(module.api_bridge, 'call_bot_api', platform_api)
    result = SimpleNamespace(host=host, loader=loader, module=module, bot=bot, calls=calls)
    yield result
    host.on_terminate()


def request(panel, action, *, event=NAMESPACE + '_WebUI', payload=None, **values):
    session = panel.host.new_session()
    request_id = uuid.uuid4().hex
    if payload is None:
        payload = dict(action=action, bot_hash=panel.bot.hash, **values)
    panel.loader.run_plugin(OlivOS.API.Control.packet('send', {'data': {
        'action': 'plugin_menu', 'namespace': NAMESPACE, 'event': event,
        'webui': {'request_id': request_id, 'session': session, 'payload': payload},
    }}))
    while not panel.host.Proc_info.control_queue.empty():
        panel.host.consume(panel.host.Proc_info.control_queue.get_nowait())
    replies = [item for item in panel.host.snapshot('events', session=session) if item['type'] == 'plugin_reply']
    assert len(replies) == 1
    assert replies[0]['request_id'] == request_id
    assert not any(item['type'] == 'plugin_reply' for item in panel.host.snapshot('events', session='other'))
    assert session not in json.dumps(replies[0]['payload'])
    return replies[0]['payload']


@pytest.mark.parametrize('packed', [False, True])
def test_host_mount_requires_login_and_supports_opk(panel, packed):
    manifest = (PLUGIN / 'app.json').read_bytes()
    assert not manifest.startswith(b'\xef\xbb\xbf')
    if packed:
        archive = panel.host.root / (NAMESPACE + '.opk')
        with zipfile.ZipFile(archive, 'w') as package:
            for source in PLUGIN.rglob('*'):
                if source.is_file() and '__pycache__' not in source.parts and 'tests' not in source.parts:
                    package.write(source, source.relative_to(PLUGIN).as_posix())
        root = panel.host.root / 'plugin/tmp' / NAMESPACE
        with zipfile.ZipFile(archive) as package:
            package.extractall(root)
        panel.loader.plugin_models_dict[NAMESPACE]['webui_root'] = str(root)
        panel.loader.sendPluginList()
        panel.host.consume(panel.host.Proc_info.control_queue.get_nowait())
    client = panel.host.app.test_client()
    endpoint = f'/plugin/{NAMESPACE}/index.html'
    assert client.get(endpoint).status_code == 401
    client.post('/api/login', headers={'X-Auth-Token': panel.host.token})
    response = client.get(endpoint, follow_redirects=True)
    assert response.status_code == 200
    assert response.data == (PLUGIN / 'webui/index.html').read_bytes()
    assert "connect-src 'none'" in response.headers['Content-Security-Policy']
    assert panel.host.plugin_pages[0]['namespace'] == NAMESPACE


def test_old_enabled_config_never_starts_listener_or_browser(panel, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Plugin must not bind a socket or open a browser')

    panel.module.utils.save_global_config({'webui_enable_switch': True, 'webui_host': '0.0.0.0', 'webui_port': 3738})
    monkeypatch.setattr(socket.socket, 'bind', forbidden)
    monkeypatch.setattr(webbrowser, 'open', forbidden)
    panel.module.main.Event.init(None, panel.loader)
    panel.module.main.Event.init_after(None, panel.loader)
    panel.module.main.Event.save(None, panel.loader)
    response = request(panel, 'state')
    assert response['ok']
    assert 'port' not in response['data']
    panel.loader.run_plugin(OlivOS.API.Control.packet('send', {'data': {
        'action': 'plugin_menu', 'namespace': NAMESPACE, 'event': NAMESPACE + '_Menu_001',
    }}))
    assert panel.host.Proc_info.control_queue.empty()


def test_drafts_settings_masters_and_bootstrap(panel):
    assert request(panel, 'bootstrap')['ok']
    assert len(panel.calls) == 5
    assert request(panel, 'draft', menu_draft={'items': []}, bot_enable_switch=False)['ok']
    response = request(panel, 'state')['data']
    assert response['menu_draft']['items'] == []
    assert response['bot_enable_switch'] is False
    assert request(panel, 'global', global_debug_mode_switch=True)['data']['global_debug_mode_switch'] is True
    assert request(panel, 'master', op='add', master_id='10002')['data']['plugin_masters'] == ['10002']
    assert request(panel, 'master', op='del', master_id='10002')['data']['plugin_masters'] == []
    assert request(panel, 'example', kind='menu')['data']['menu_draft']['items']


def test_menu_and_panel_platform_actions(panel):
    assert request(panel, 'menu/pull')['ok']
    response = request(panel, 'menu/send')
    assert response['data']['send_summary']['success'] == 1
    assert response['data']['menu_draft']['version'] == 2
    assert request(panel, 'panel/pull', scopes=['all'])['ok']
    assert request(panel, 'example', kind='panel', scope='c2c')['ok']
    response = request(panel, 'panel/send', scope='c2c', panel_index=0)
    record = response['data']['panel_drafts']['c2c'][0]
    assert record['panel_id'] == 'panel-test'
    assert record['version'] == 2
    assert request(panel, 'panel/send', scope='c2c', panel_index=0)['ok']
    record['target_type'] = 'specific'
    record['user_openids'] = ['test-openid']
    response = request(panel, 'panel/target', scope='c2c', panel_index=0, op='add', panel_drafts={'c2c': [record]})
    assert response['data']['send_summary']['success'] == 1
    assert request(panel, 'panel/delete', panel_id='panel-test')['data']['panel_drafts']['c2c'] == []
    methods = [method for method, _kwargs in panel.calls]
    assert 'create_qq_command_panel' in methods
    assert 'set_qq_command_panel' in methods
    assert 'set_qq_command_panel_target' in methods
    assert 'delete_qq_command_panel' in methods


@pytest.mark.parametrize('payload', [
    [], {'action': []}, {'action': 'unknown'}, {'action': 'draft'},
    {'action': 'draft', 'bot_hash': '../escape'}, {'action': 'state', 'bot_hash': []},
])
def test_bad_requests_return_errors_without_platform_calls(panel, payload):
    assert request(panel, '', payload=payload)['ok'] is False
    assert panel.calls == []


def test_unknown_event_and_handler_failure_return_errors(panel, monkeypatch):
    assert request(panel, 'state', event='unknown')['ok'] is False

    def fail(_payload):
        raise OSError('test-only detail')

    monkeypatch.setitem(panel.module.webui._HANDLERS, 'state', fail)
    response = request(panel, 'state')
    assert response['ok'] is False
    assert 'test-only detail' not in response['message']


def test_no_bots_still_allows_global_settings(panel):
    panel.loader.Proc_data['bot_info_dict'].clear()
    response = request(panel, '', payload={'action': 'state'})
    assert response['data']['bots'] == []
    assert request(panel, '', payload={'action': 'global', 'global_debug_mode_switch': True})['ok']
    assert request(panel, '', payload={'action': 'bootstrap'})['ok']


@pytest.mark.skipif(not os.environ.get('OLIVOS_WEBUI_BROWSER'), reason='Browser verification is opt-in')
def test_browser_in_host_sandbox(panel):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    host = panel.host
    host.config['port'] = 0
    service = threading.Thread(target=host.run, daemon=True)
    service.start()
    stopped = threading.Event()

    def bus():
        while not stopped.is_set():
            try:
                packet = host.Proc_info.control_queue.get(timeout=.1)
            except queue.Empty:
                continue
            if packet.key.get('data', {}).get('action') == 'plugin_menu':
                panel.loader.run_plugin(packet)
            else:
                host.consume(packet)

    worker = threading.Thread(target=bus, daemon=True)
    worker.start()
    options = webdriver.ChromeOptions()
    for option in ['--headless=new', '--no-first-run', '--disable-background-networking', '--window-size=1440,1000']:
        options.add_argument(option)
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    driver = None
    try:
        assert host.ready.wait(5) and host.error is None
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 15)
        driver.get(f"http://127.0.0.1:{host.config['port']}")
        driver.find_element(By.ID, 'token').send_keys(host.token)
        driver.find_element(By.CSS_SELECTOR, '#login-form button').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#plugin-links button'))
        driver.find_element(By.CSS_SELECTOR, '#plugin-links button').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#plugin-frame-container iframe'))
        driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, '#plugin-frame-container iframe'))
        wait.until(lambda d: d.execute_script('return state && state.menu_draft.items.length > 0'))
        wait.until(lambda d: d.execute_script('return pendingRequests.size === 0'))
        driver.execute_script('showTab("settings"); document.getElementById("botEnable").value = "false"; saveGlobal()')
        wait.until(lambda d: d.execute_script('return state.bot_enable_switch === false && pendingRequests.size === 0'))
        driver.execute_script('sendMenu()')
        assert driver.find_element(By.ID, 'confirmModal').is_displayed()
        count = len(panel.calls)
        driver.find_element(By.ID, 'confirmCancel').click()
        assert len(panel.calls) == count
        driver.execute_script('sendMenu(); finishConfirm(true)')
        wait.until(lambda d: d.find_element(By.ID, 'resultModal').is_displayed())
        assert any(method == 'set_qq_global_menu' for method, _kwargs in panel.calls)
        driver.execute_script('closeModal(); showTab("panel"); fillExample("panel")')
        wait.until(lambda d: d.execute_script('return pendingRequests.size === 0 && currentPanel() !== null'))
        driver.execute_script('sendPanel(); finishConfirm(true)')
        wait.until(lambda d: d.find_element(By.ID, 'resultModal').is_displayed())
        driver.execute_script('closeModal(); deleteRemote(); finishConfirm(true)')
        wait.until(lambda d: d.find_element(By.ID, 'resultModal').is_displayed())
        driver.execute_script('closeModal(); api("unknown")')
        wait.until(lambda d: '未知' in d.find_element(By.ID, 'resultBox').text)
        stopped.set()
        worker.join(timeout=2)
        driver.execute_script('''
            const originalTimeout = window.setTimeout;
            window.setTimeout = (callback, delay) => originalTimeout(callback, delay === 120000 ? 500 : delay);
            api("state", {bot_hash: botHash});
        ''')
        assert not driver.find_element(By.ID, 'botSelect').is_enabled()
        wait.until(lambda d: '超时' in d.find_element(By.ID, 'resultBox').text)
        assert driver.find_element(By.ID, 'botSelect').is_enabled()
        errors = [entry for entry in driver.get_log('browser') if entry['level'] == 'SEVERE']
        assert not errors, f'{len(errors)} browser errors'
    finally:
        if driver is not None:
            driver.quit()
        stopped.set()
        worker.join(timeout=2)
        host.on_terminate()
        service.join(timeout=5)
    assert not service.is_alive()
