"""使用 OlivOS 核心消息桥和临时数据验证接入；QQ 平台调用全部替身化。"""

import base64
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
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

import OlivOS
import pytest

from OlivOS.webUI import resourceAPI

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
    resources, pages = resourceAPI.declaration(root, manifest)
    loader.plugin_models_dict = {
        NAMESPACE: dict(manifest, model=module, webui_root=str(root), webui_resources=resources, webui_config=pages),
    }
    loader.sendPluginList(ready=True)
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
        resources = panel.loader.plugin_models_dict[NAMESPACE]['webui_resources']
        cached = resourceAPI.build_cache(panel.host.root, root, NAMESPACE, resources)
        shutil.rmtree(root)
        panel.loader.plugin_models_dict[NAMESPACE]['webui_root'] = cached
        panel.loader.sendPluginList(ready=True)
        panel.host.consume(panel.host.Proc_info.control_queue.get_nowait())
    client = panel.host.app.test_client()
    endpoint = f'/plugin/{NAMESPACE}/webui/index.html'
    assert client.get(endpoint).status_code == 401
    client.post('/api/login', headers={'X-Auth-Token': panel.host.token})
    response = client.get(endpoint, follow_redirects=True)
    assert response.status_code == 200
    assert response.data == (PLUGIN / 'webui/index.html').read_bytes()
    response.close()
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


def test_selected_scopes_persist_and_unified_send_subset(panel):
    saved = request(panel, 'draft', chat_selected_scopes=['group', 'c2c', 'group', 'nope'])
    assert saved['data']['chat_selected_scopes'] == ['c2c', 'group']
    assert panel.module.function.scopes_allow_specific(['c2c', 'group'])
    assert not panel.module.function.scopes_allow_specific(['c2c', 'channel'])

    assert request(panel, 'example', kind='panel', scope='c2c')['ok']
    panel.calls.clear()
    response = request(
        panel, 'panel/send',
        scope='c2c',
        panel_index=0,
        unified_panel_mode=True,
        scopes=['c2c', 'group'],
        chat_selected_scopes=['c2c', 'group'],
    )
    assert response['ok']
    create_scopes = [
        kwargs.get('scope') for method, kwargs in panel.calls
        if method == 'create_qq_command_panel'
    ]
    assert create_scopes == ['c2c', 'group']


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


def png_bytes(color='#4060c0'):
    output = BytesIO()
    Image.new('RGB', (32, 32), color).save(output, format='PNG')
    return output.getvalue()


def test_help_markdown_stays_in_memory_after_sidecar_gone(panel, monkeypatch):
    docs = panel.module.help_docs
    text = docs.get_help_markdown()
    assert 'QQ 自定义菜单与指令面板' in text
    assert '读取 `help.md` 失败' not in text
    assert request(panel, 'state')['data']['help_text'] == text

    original_open = open

    def deny_help_md(path, *args, **kwargs):
        if os.path.basename(str(path)) == 'help.md':
            raise FileNotFoundError(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr('builtins.open', deny_help_md)
    assert docs.get_help_markdown() == text
    assert request(panel, 'state')['data']['help_text'] == text


def test_page_marks_panel_id_readonly_and_hides_empty_editors():
    html = (PLUGIN / 'webui/index.html').read_text(encoding='utf-8')
    assert 'id="panelId" readonly' in html
    assert 'data-action="copy-panel-id"' in html
    assert 'id="menuEditor" hidden' in html
    assert 'id="itemEditor" hidden' in html
    assert 'flex-wrap: nowrap' in html
    assert 'overflow-x: auto' in html
    assert 'id="botAvatar"' in html
    assert 'id="botMiniAvatar"' in html
    assert 'linear-gradient(180deg, #9fd2ff, #4aa7ff)' in html
    assert 'refresh_avatar' in html
    assert '--topbar-control-bg' in html
    assert 'id="scopePicks"' in html
    assert 'id="targetSpecificBox"' in html
    assert 'id="groupOpenidBox"' in html
    assert '至少保留一个' in html
    assert "getElement('panelId').addEventListener('input'" not in html


def avatar_response(data):
    response = Mock()
    response.status_code = 200
    response.headers = {'Content-Length': str(len(data))}
    response.iter_content.return_value = [data]
    response.raise_for_status = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


def current_bot(response, panel):
    return next(item for item in response['bots'] if item['hash'] == panel.bot.hash)


def test_local_avatar_uses_only_bot_folder_file(panel, monkeypatch):
    data_dir = Path('plugin/data/QQBotMenuPanel')
    bot_dir = data_dir / panel.bot.hash
    other_dir = data_dir / 'other-bot'
    bot_dir.mkdir(parents=True, exist_ok=True)
    other_dir.mkdir(parents=True, exist_ok=True)
    panel.module.utils._avatar_cache.clear()
    monkeypatch.setattr(
        panel.module.utils.requests, 'get',
        Mock(side_effect=AssertionError('Unexpected avatar network')),
    )

    (data_dir / 'avatar.png').write_bytes(png_bytes('#4060c0'))
    (data_dir / (panel.bot.hash + '.png')).write_bytes(png_bytes('#111111'))
    (other_dir / 'avatar.png').write_bytes(png_bytes('#222222'))
    bot = current_bot(request(panel, 'state')['data'], panel)
    assert bot['avatar'] == ''

    own = png_bytes('#c05040')
    (bot_dir / 'avatar.png').write_bytes(own)
    bot = current_bot(request(panel, 'state')['data'], panel)
    raw = base64.b64decode(bot['avatar'].split(',', 1)[1])
    assert raw == panel.module.utils.normalize_avatar(own)
    assert (data_dir / 'avatar.png').read_bytes() == png_bytes('#4060c0')
    assert (data_dir / (panel.bot.hash + '.png')).read_bytes() == png_bytes('#111111')


def test_online_avatar_writes_bot_folder_png_and_ignores_root_avatar(panel, monkeypatch):
    data_dir = Path('plugin/data/QQBotMenuPanel')
    data_dir.mkdir(parents=True, exist_ok=True)
    shared = png_bytes('#4060c0')
    (data_dir / 'avatar.png').write_bytes(shared)
    bot_config = panel.module.utils.load_bot_config(panel.bot.hash)
    bot_config['bot_openid'] = 'BOT_OPENID'
    panel.module.utils.save_bot_config(panel.bot.hash, bot_config)
    panel.module.utils._avatar_cache.clear()
    online = png_bytes('#c05040')
    download = Mock(return_value=avatar_response(online))
    monkeypatch.setattr(panel.module.utils.requests, 'get', download)

    bot = current_bot(request(panel, 'state')['data'], panel)
    assert bot['avatar'].startswith('data:image/png;base64,')
    download.assert_called_once()
    assert download.call_args[0][0] == 'https://q.qlogo.cn/qqapp/%s/BOT_OPENID/0' % panel.bot.id
    cached = data_dir / panel.bot.hash / 'avatar.png'
    assert cached.read_bytes() == panel.module.utils.normalize_avatar(online)
    assert (data_dir / 'avatar.png').read_bytes() == shared
    current_bot(request(panel, 'state')['data'], panel)
    assert download.call_count == 1


def test_refresh_avatar_retries_online_fetch(panel, monkeypatch):
    data_dir = Path('plugin/data/QQBotMenuPanel')
    data_dir.mkdir(parents=True, exist_ok=True)
    bot_config = panel.module.utils.load_bot_config(panel.bot.hash)
    bot_config['bot_openid'] = 'BOT_OPENID'
    panel.module.utils.save_bot_config(panel.bot.hash, bot_config)
    panel.module.utils._avatar_cache.clear()
    first = png_bytes('#c05040')
    second = png_bytes('#20a060')
    download = Mock(side_effect=[avatar_response(first), avatar_response(second)])
    monkeypatch.setattr(panel.module.utils.requests, 'get', download)

    bot = current_bot(request(panel, 'state')['data'], panel)
    first_uri = bot['avatar']
    assert download.call_count == 1
    current_bot(request(panel, 'state')['data'], panel)
    assert download.call_count == 1

    bot = current_bot(request(panel, 'bootstrap', refresh_avatar=True)['data'], panel)
    assert download.call_count == 2
    assert bot['avatar'] != first_uri
    cached = data_dir / panel.bot.hash / 'avatar.png'
    assert cached.read_bytes() == panel.module.utils.normalize_avatar(second)


def test_group_message_remembers_bot_openid(panel, monkeypatch):
    monkeypatch.setattr(
        panel.module.utils.requests, 'get',
        Mock(side_effect=AssertionError('Unexpected avatar network')),
    )
    event = SimpleNamespace(
        platform={'sdk': 'qqGuildv2_link'},
        bot_info=panel.bot,
        data=SimpleNamespace(extend={'sub_self_open_id': 'EVENT_OPENID'}),
    )
    panel.module.main.Event.group_message(event, panel.loader)
    assert panel.module.utils.load_bot_config(panel.bot.hash)['bot_openid'] == 'EVENT_OPENID'


def test_no_bots_still_allows_global_settings(panel):
    panel.loader.Proc_data['bot_info_dict'].clear()
    response = request(panel, '', payload={'action': 'state'})
    assert response['data']['bots'] == []
    assert request(panel, '', payload={'action': 'global', 'global_debug_mode_switch': True})['ok']
    assert request(panel, '', payload={'action': 'bootstrap'})['ok']


@pytest.mark.skipif(not os.environ.get('OLIVOS_WEBUI_BROWSER'), reason='Browser verification is opt-in')
def test_browser_in_host_sandbox(panel):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select
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
        driver_path = os.environ.get('OLIVOS_CHROMEDRIVER')
        chrome_service = Service(executable_path=driver_path) if driver_path else None
        driver = webdriver.Chrome(options=options, service=chrome_service)
        wait = WebDriverWait(driver, 15)
        driver.get(f"http://127.0.0.1:{host.config['port']}")
        driver.find_element(By.ID, 'token').send_keys(host.token)
        driver.find_element(By.CSS_SELECTOR, '#login-form button').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#plugin-links .plugin-link-entry'))
        driver.find_element(By.CSS_SELECTOR, '#plugin-links .plugin-link-entry').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#plugin-frame-container iframe'))
        driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, '#plugin-frame-container iframe'))
        wait.until(lambda d: d.execute_script('return state && state.menu_draft.items.length > 0'))
        wait.until(lambda d: d.execute_script('return pendingRequests.size === 0'))
        screenshots = Path(os.environ.get('OLIVOS_WEBUI_SCREENSHOTS', host.root / 'screenshots'))
        screenshots.mkdir(parents=True, exist_ok=True)
        identity = driver.execute_script('window.themeTestIdentity = Math.random(); return window.themeTestIdentity')

        def theme(mode, system, dark):
            driver.switch_to.default_content()
            driver.execute_cdp_cmd('Emulation.setEmulatedMedia', {
                'features': [{'name': 'prefers-color-scheme', 'value': system}],
            })
            Select(driver.find_element(By.CSS_SELECTOR, 'aside [data-theme-select]')).select_by_value(mode)
            driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, '#plugin-frame-container iframe'))
            wait.until(lambda d: d.execute_script("return matchMedia('(prefers-color-scheme: dark)').matches") == dark)
            expected = 'rgb(25, 31, 40)' if dark else 'rgb(243, 244, 246)'
            wait.until(lambda d: d.execute_script('return getComputedStyle(document.body).backgroundColor') == expected)
            assert driver.execute_script('return window.themeTestIdentity') == identity
            assert driver.execute_script('return state.menu_draft.items.length > 0')

        def screenshot(name):
            driver.switch_to.default_content()
            driver.save_screenshot(str(screenshots / name))
            driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, '#plugin-frame-container iframe'))

        theme('light', 'dark', False)
        screenshot('qqmenu-light.png')
        theme('dark', 'light', True)
        screenshot('qqmenu-dark.png')
        for tab in ('menu', 'panel', 'browse', 'settings', 'help'):
            driver.find_element(By.CSS_SELECTOR, f'.tabs button[data-tab="{tab}"]').click()
            wait.until(lambda d: d.find_element(By.ID, 'tab-' + tab).is_displayed())
            color = driver.execute_script(
                'return getComputedStyle(document.querySelector(arguments[0])).backgroundColor', f'#tab-{tab} .card')
            assert color == 'rgb(36, 46, 59)'
        screenshot('qqmenu-dark-help.png')
        theme('system', 'light', False)
        theme('system', 'dark', True)
        driver.execute_script('showTab("menu"); sendMenu()')
        assert driver.find_element(By.ID, 'confirmModal').is_displayed()
        assert driver.execute_script(
            'return getComputedStyle(document.querySelector("#confirmModal .modal-card")).backgroundColor') == \
            'rgb(36, 46, 59)'
        screenshot('qqmenu-dark-confirm.png')
        driver.find_element(By.ID, 'confirmCancel').click()
        driver.execute_script('showTab("panel"); fillExample("panel")')
        wait.until(lambda d: d.execute_script('return pendingRequests.size === 0 && currentPanel() !== null'))
        screenshot('qqmenu-dark-panel.png')
        driver.switch_to.default_content()
        driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
            'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': False,
        })
        driver.save_screenshot(str(screenshots / 'qqmenu-dark-mobile.png'))
        driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
            'width': 1440, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False,
        })
        driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, '#plugin-frame-container iframe'))
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
        errors = [entry for entry in driver.get_log('browser')
                  if entry['level'] == 'SEVERE' and entry.get('source') == 'javascript']
        assert not errors, f'{len(errors)} browser errors'
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(host.root / 'failure.png'))
        raise
    finally:
        if driver is not None:
            driver.quit()
        stopped.set()
        worker.join(timeout=2)
        host.on_terminate()
        service.join(timeout=5)
    assert not service.is_alive()
