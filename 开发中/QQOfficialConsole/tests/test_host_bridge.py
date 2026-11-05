"""真实 OlivOS WebUI 消息桥回归；所有平台调用均在进程内模拟。"""
import base64
import importlib
import json
import os
import queue
import shutil
import sys
import threading
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace

import OlivOS
import pytest
from OlivOS.webUI import resourceAPI


PLUGIN = Path(__file__).resolve().parents[1] / 'QQOfficialConsole'
NAMESPACE = 'QQOfficialConsole'


@pytest.fixture(params=[False, True], ids=['directory', 'opk-cleaned'])
def console(request, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'plugin' / ('tmp' if request.param else 'app') / NAMESPACE
    if request.param:
        archive = tmp_path / 'console.opk'
        with zipfile.ZipFile(archive, 'w') as package:
            for source in PLUGIN.rglob('*'):
                if source.is_file() and '__pycache__' not in source.parts:
                    package.write(source, source.relative_to(PLUGIN))
        with zipfile.ZipFile(archive) as package:
            package.extractall(root)
    else:
        shutil.copytree(PLUGIN, root, ignore=shutil.ignore_patterns('__pycache__'))
    monkeypatch.syspath_prepend(str(root.parent))
    # 每次均从实际测试目录导入，避免不同参数共享模块状态。
    for name in list(sys.modules):
        if name == NAMESPACE or name.startswith(NAMESPACE + '.'):
            monkeypatch.delitem(sys.modules, name)
    module = importlib.import_module(NAMESPACE)
    manifest = json.loads((root / 'app.json').read_text(encoding='utf-8'))
    manifest.setdefault('menu_config', None)
    bot = OlivOS.API.bot_info_T(id=10001, platform_sdk='qqGuildv2_link',
                                platform_platform='qqGuild', platform_model='public')
    host = OlivOS.webUI.serverAPI.server(root_path=tmp_path, rx_queue=queue.Queue(),
        control_queue=queue.Queue(), bot_info_dict={bot.hash: bot})
    loader = OlivOS.pluginAPI.shallow(control_queue=host.Proc_info.control_queue,
                                      bot_info_dict={bot.hash: bot})
    resources, pages = resourceAPI.declaration(root, manifest)
    if request.param:
        cached = resourceAPI.build_cache(tmp_path, root, NAMESPACE, resources)
        shutil.rmtree(root)
        root = cached
    loader.plugin_models_call_list = [NAMESPACE]
    loader.plugin_models_dict = {NAMESPACE: dict(manifest, model=module, webui_root=str(root),
                                                  webui_resources=resources, webui_config=pages)}
    loader.sendPluginList(ready=True)
    while not host.Proc_info.control_queue.empty():
        host.consume(host.Proc_info.control_queue.get_nowait())
    calls = []

    def fake_dispatch(event, api, chat_type, chat_id, msg_id, event_id, **kwargs):
        calls.append((api, chat_type, chat_id, msg_id, event_id))
        api.res_code = 200
        return {'active': True, 'data': {'message_id': 'sent-1', 'response': {}}}

    monkeypatch.setattr(OlivOS.qqGuildv2SDK.event_action, '_send_qq_api', fake_dispatch)
    yield SimpleNamespace(host=host, loader=loader, module=module, bot=bot, calls=calls)
    module.main.Event.save(None, loader)
    host.on_terminate()


def bridge(console, action, **values):
    session = console.host.new_session()
    request_id = uuid.uuid4().hex
    payload = {'bot_hash': console.bot.hash, **values}
    console.loader.run_plugin(OlivOS.API.Control.packet('send', {'data': {
        'action': 'plugin_menu', 'namespace': NAMESPACE, 'event': NAMESPACE + '_' + action,
        'webui': {'request_id': request_id, 'session': session, 'payload': payload},
    }}))
    while not console.host.Proc_info.control_queue.empty():
        console.host.consume(console.host.Proc_info.control_queue.get_nowait())
    replies = [event for event in console.host.snapshot('events', session=session)
               if event['type'] == 'plugin_reply']
    assert len(replies) == 1
    assert replies[0]['request_id'] == request_id
    assert not [event for event in console.host.snapshot('events', session='other')
                if event['type'] == 'plugin_reply']
    return replies[0]['payload']


def incoming(console, chat, number, content=None):
    raw = {'id': f'{chat}-{number}', 'content': content if content is not None else f'{chat} message {number}',
           'timestamp': 1700000000 + number}
    event = SimpleNamespace(platform={'sdk': 'qqGuildv2_link'}, bot_info=console.bot,
        data=SimpleNamespace(user_id=chat, sender={'nickname': chat},
                             extend={'flag_from_qq': True, 'qq_event_data': raw}),
        sdk_event=SimpleNamespace(payload=SimpleNamespace(data=SimpleNamespace(t='C2C_MESSAGE_CREATE'))))
    console.module.main.Event.private_message(event, console.loader)


def test_sidebar_resources_and_bootstrap(console):
    assert not (PLUGIN / 'app.json').read_bytes().startswith(b'\xef\xbb\xbf')
    assert any(page['namespace'] == NAMESPACE for page in console.host.plugin_pages)
    client = console.host.app.test_client()
    assert client.get(f'/plugin/{NAMESPACE}/webui/index.html').status_code == 401
    client.post('/api/login', headers={'X-Auth-Token': console.host.new_browser_token()})
    response = client.get(f'/plugin/{NAMESPACE}/webui/index.html', follow_redirects=True)
    assert response.status_code == 200
    assert response.data == (PLUGIN / 'webui' / 'index.html').read_bytes()
    response.close()
    result = bridge(console, 'Bootstrap')
    assert result['ok'] and any(bot['hash'] == console.bot.hash for bot in result['bots'])


def test_incoming_switch_and_thirty_message_pages(console):
    for number in range(65):
        incoming(console, 'alice', number)
    for number in range(3):
        incoming(console, 'bob', number)
    chats = bridge(console, 'ListChats')
    assert chats['ok']
    assert {'alice', 'bob'} <= {chat['chat_id'] for chat in chats['chats']}
    target = {'chat_type': 'qq_private', 'chat_id': 'alice', 'limit': 30}
    latest = bridge(console, 'PullMessages', **target)['messages']
    assert len(latest) == 30
    bob = bridge(console, 'PullMessages', chat_type='qq_private', chat_id='bob', limit=30)['messages']
    assert len(bob) == 3 and all(row['content_text'].startswith('bob ') for row in bob)
    older = bridge(console, 'PullMessages', before_id=latest[0]['id'], **target)['messages']
    assert len(older) == 30
    oldest = bridge(console, 'PullMessages', before_id=older[0]['id'], **target)['messages']
    assert len(oldest) == 5
    assert len({row['id'] for row in latest + older + oldest}) == 65
    assert all(row['content_text'].startswith('alice ') for row in latest + older + oldest)
    again = bridge(console, 'PullMessages', **target)['messages']
    assert [row['id'] for row in again] == [row['id'] for row in latest]


def test_send_3000_and_3001(console):
    incoming(console, 'alice', 1)
    target = {'chat_type': 'qq_private', 'chat_id': 'alice', 'kind': 'text', 'force_active': True}
    result = bridge(console, 'Send', text='x' * 3000, **target)
    assert result['ok'], result
    assert len(console.calls) == 1
    result = bridge(console, 'Send', text='x' * 3001, **target)
    assert not result['ok'] and result['keyword'] == '字符过多'
    assert len(console.calls) == 1
    messages = bridge(console, 'PullMessages', chat_type='qq_private', chat_id='alice')['messages']
    assert any(row['direction'] == 'out' and row['content_text'] == 'x' * 3000 for row in messages)


@pytest.mark.skipif(not os.environ.get('OLIVOS_WEBUI_BROWSER'), reason='Browser verification is opt-in')
def test_browser_multibyte_cache_survives_switch(console):
    """通过真实宿主、可见页面操作和磁盘缓存验证 UTF-8 分片往返。"""
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    expected = [f'{number:02d}：' + '中文😀汉字🚀' * 350 for number in range(30)]
    for number, text in enumerate(expected):
        incoming(console, 'alice', number, text)
    incoming(console, 'bob', 0, '另一个会话')
    host = console.host
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
                console.loader.run_plugin(packet)
            else:
                host.consume(packet)

    worker = threading.Thread(target=bus, daemon=True)
    worker.start()
    options = webdriver.ChromeOptions()
    if os.environ.get('OLIVOS_CHROME_BINARY'):
        options.binary_location = os.environ['OLIVOS_CHROME_BINARY']
    for option in ('--headless=new', '--no-first-run', '--disable-background-networking', '--window-size=1440,1000'):
        options.add_argument(option)
    driver = None
    try:
        assert host.ready.wait(10) and host.error is None
        path = os.environ.get('OLIVOS_CHROMEDRIVER')
        driver = webdriver.Chrome(options=options, service=Service(executable_path=path) if path else None)
        wait = WebDriverWait(driver, 30, ignored_exceptions=(StaleElementReferenceException,))
        # 先完成宿主页脚本初始化，再触发一次性票据的 hashchange 登录；避免首屏加载时序竞争。
        driver.get(f"http://127.0.0.1:{host.config['port']}/")
        wait.until(lambda d: d.find_element(By.ID, 'login').is_displayed())
        ticket_url = host.local_action({'action': 'open'})['url']
        driver.execute_script('location.hash = new URL(arguments[0]).hash', ticket_url)
        wait.until(lambda d: d.find_element(By.ID, 'shell').is_displayed())
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#plugin-links .plugin-link-entry'))
        driver.find_element(By.CSS_SELECTOR, '#plugin-links .plugin-link-entry').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#plugin-frame-container iframe'))
        driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, '#plugin-frame-container iframe'))

        def chat_button(name):
            return next((element for element in driver.find_elements(By.CSS_SELECTOR, '#chats .chat-item')
                         if element.find_element(By.TAG_NAME, 'strong').text == name), None)

        def click_chat(name):
            # 页面在 switching 期间会拒绝切换（真实用户会看到提示后再点一次），
            # 所以测试也必须重复点击直到标题变化，单次点击会随机输给轮询重绘的竞态。
            def attempt(d):
                if d.find_element(By.ID, 'chatTitle').text == name:
                    return True
                if d.execute_script('return switching'):
                    return False
                button = chat_button(name)
                if button:
                    button.click()
                return False
            wait.until(attempt)

        click_chat('alice')
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '#messages .message .bubble')) == 30)
        original = driver.execute_script("return [...document.querySelectorAll('#messages .message .bubble')].map(x=>x.textContent)")
        assert original == expected
        click_chat('bob')
        cache_dir = host.root / 'plugin/data/QQOfficialConsole/view-cache'
        files = list(cache_dir.glob('*.json'))
        assert len(files) == 1
        data = files[0].read_bytes()
        assert len(data) > 192 * 1024
        assert data[192 * 1024] & 0xc0 == 0x80  # 分片边界确实切在 UTF-8 多字节字符中。
        cached = json.loads(data)
        assert [item['content_text'] for item in cached['messages']] == expected
        click_chat('alice')
        wait.until(lambda d: d.find_element(By.ID, 'chatTitle').text == 'alice')
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '#messages .message .bubble')) == 30)
        restored = driver.execute_script("return [...document.querySelectorAll('#messages .message .bubble')].map(x=>x.textContent)")
        assert restored == expected
    finally:
        if driver is not None:
            driver.quit()
        stopped.set()
        worker.join(timeout=5)
        host.on_terminate()
        service.join(timeout=5)
        assert not service.is_alive()


@pytest.mark.skipif(not os.environ.get('OLIVOS_WEBUI_BROWSER'), reason='Browser verification is opt-in')
def test_browser_mention_near_far_and_other_bot(console, monkeypatch):
    """群消息由宿主入口入库，通过页面点击及滚轮验证 @ 定位和跨账号隔离。"""
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select, WebDriverWait

    other = OlivOS.API.bot_info_T(id=10002, platform_sdk='qqGuildv2_link',
                                  platform_platform='qqGuild', platform_model='public')
    console.loader.Proc_data['bot_info_dict'][other.hash] = other
    monkeypatch.setattr(OlivOS.qqGuildv2SDK.event_action, 'get_qq_group_bot_state',
                        lambda *a, **k: {'active': True, 'data': {'response': {'member_role': 'member'}}})

    def group(bot, chat, count, mention):
        for n in range(count):
            raw = {'id': f'{chat}-{n}', 'content': f'{chat} message {n:03d}', 'timestamp': 1700000000 + n}
            event = SimpleNamespace(platform={'sdk': 'qqGuildv2_link'}, bot_info=bot,
                data=SimpleNamespace(group_id=chat, user_id='sender', sender={'nickname': 'sender'},
                    extend={'flag_from_qq': True, 'qq_event_data': raw}),
                sdk_event=SimpleNamespace(payload=SimpleNamespace(data=SimpleNamespace(
                    t='GROUP_AT_MESSAGE_CREATE' if n == mention else 'GROUP_MESSAGE_CREATE'))))
            console.module.main.Event.group_message(event, console.loader)
        console.module.main._state[0].upsert_chat(bot.hash, 'qq_group', chat, display_name=chat)

    group(console.bot, 'near', 70, 10)
    group(console.bot, 'far', 380, 3)
    group(other, 'other', 60, 0)
    host = console.host
    host.config['port'] = 0
    service = threading.Thread(target=host.run, daemon=True)
    service.start()
    stopped = threading.Event()
    block_poll = threading.Event()
    poll_arrived = threading.Event()
    release_poll = threading.Event()

    def bus():
        while not stopped.is_set():
            try:
                packet = host.Proc_info.control_queue.get(timeout=.1)
            except queue.Empty:
                continue
            if packet.key.get('data', {}).get('action') == 'plugin_menu':
                if block_poll.is_set() and packet.key.get('data', {}).get('event') == NAMESPACE + '_ListChats':
                    poll_arrived.set()
                    release_poll.wait(10)
                console.loader.run_plugin(packet)
            else:
                host.consume(packet)

    worker = threading.Thread(target=bus, daemon=True)
    worker.start()
    options = webdriver.ChromeOptions()
    if os.environ.get('OLIVOS_CHROME_BINARY'):
        options.binary_location = os.environ['OLIVOS_CHROME_BINARY']
    for option in ('--headless=new', '--no-first-run', '--disable-background-networking', '--window-size=1440,1000'):
        options.add_argument(option)
    driver = None
    try:
        assert host.ready.wait(10) and host.error is None
        path = os.environ.get('OLIVOS_CHROMEDRIVER')
        driver = webdriver.Chrome(options=options, service=Service(executable_path=path) if path else None)
        wait = WebDriverWait(driver, 30, ignored_exceptions=(StaleElementReferenceException,))
        driver.get(f"http://127.0.0.1:{host.config['port']}/")
        wait.until(lambda d: d.find_element(By.ID, 'login').is_displayed())
        driver.execute_script('location.hash = new URL(arguments[0]).hash', host.local_action({'action': 'open'})['url'])
        wait.until(lambda d: d.find_element(By.ID, 'shell').is_displayed())
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#plugin-links .plugin-link-entry'))[0].click()
        frame = wait.until(lambda d: next((f for f in d.find_elements(By.CSS_SELECTOR, '#plugin-frame-container iframe') if f.is_displayed()), None))
        driver.switch_to.frame(frame)
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '#bots option')) == 2)
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#chats .chat-item'))
        def select_expected_bot(d):
            element = d.find_element(By.ID, 'bots')
            if element.get_attribute('value') != console.bot.hash:
                Select(element).select_by_value(console.bot.hash)
            return element.get_attribute('value') == console.bot.hash

        wait.until(select_expected_bot)

        def click_chat(name):
            menu = driver.find_element(By.ID, 'showChats')
            if menu.is_displayed():
                menu.click()

            def attempt(d):
                if d.find_element(By.ID, 'chatTitle').text == name:
                    return True
                if d.execute_script('return switching'):
                    return False
                for row in d.find_elements(By.CSS_SELECTOR, '#chats .chat-item'):
                    if row.find_element(By.TAG_NAME, 'strong').get_attribute('textContent') == name:
                        row.click()
                        return False
                return False

            wait.until(attempt)

        def shown():
            return driver.execute_script("return [...document.querySelectorAll('#messages .message .bubble')].map(e=>e.textContent)")

        database = console.module.main._state[0]
        for chat, count in (('near', 70), ('far', 380)):
            assert database.get_chat(console.bot.hash, 'qq_group', chat)['mention_unread'] == 1
            click_chat(chat)
            wait.until(lambda d: len(shown()) == 30)
            assert shown() == [f'{chat} message {n:03d}' for n in range(count - 30, count)]
            wait.until(lambda d: database.get_chat(console.bot.hash, 'qq_group', chat)['unread'] == 0)
            assert database.get_chat(console.bot.hash, 'qq_group', chat)['mention_unread'] == 0
            assert database.mention_target(console.bot.hash, 'qq_group', chat)['message_id'] is None
            assert not driver.find_element(By.ID, 'jumpMention').is_displayed()
            assert database.get_chat(other.hash, 'qq_group', 'other')['mention_unread'] == 1
            wait.until(lambda d: '@我 1' in d.execute_script(
                "return [...document.querySelectorAll('#bots option')]"
                ".find(o=>o.value===arguments[0])?.textContent || ''", other.hash))
        # 缓存恢复时依旧定位最新消息，不恢复旧的滚动位置。
        click_chat('near')
        wait.until(lambda d: shown() == [f'near message {n:03d}' for n in range(40, 70)])
        assert driver.execute_script(
            "const b=document.getElementById('messages');return b.scrollHeight-b.scrollTop-b.clientHeight<3")
        assert all(e.text == '群' for e in driver.find_elements(By.CSS_SELECTOR, '#chats .avatar'))
    finally:
        release_poll.set()
        if driver is not None:
            driver.quit()
        stopped.set()
        worker.join(timeout=5)
        host.on_terminate()
        service.join(timeout=5)
        assert not service.is_alive()


@pytest.mark.parametrize('upload_ok', [True, False])
def test_sent_image_bridge_is_scoped_and_survives_send(console, monkeypatch, upload_ok):
    monkeypatch.setattr(OlivOS.qqGuildv2SDK.event_action, 'setResourceUploadFast',
                        lambda *args: 'file-info' if upload_ok else None)
    data = b'\x89PNG\r\n\x1a\n' + b'x' * (256 * 1024 + 1)
    begin = bridge(console, 'UploadBegin', name='test.png', size=len(data), mime='image/png')
    ident = begin['upload_id']
    for index, start in enumerate(range(0, len(data), 256 * 1024)):
        assert bridge(console, 'UploadChunk', upload_id=ident, index=index,
                      data_b64=base64.b64encode(data[start:start + 256 * 1024]).decode())['ok']
    target = {'chat_type': 'qq_private', 'chat_id': 'alice'}
    sent = bridge(console, 'Send', **target, kind='text', text='', images=[{'upload_id': ident}])
    assert sent['ok'] is upload_ok
    assert len(sent['images']) == 1 and sent['images'][0]['marker'] is None
    image = sent['images'][0]
    rows = bridge(console, 'PullMessages', **target)['messages']
    row = next(row for row in rows if row['id'] == sent['local_id'])
    assert json.loads(row['content_json'])['images'] == sent['images']
    params = dict(target, message_id=sent['local_id'], image_id=image['image_id'])
    chunks = [bridge(console, 'MessageImageRead', **params, index=index) for index in range(2)]
    assert all(chunk['ok'] and chunk['total_chunks'] == 2 for chunk in chunks)
    assert b''.join(base64.b64decode(chunk['data_b64']) for chunk in chunks) == data
    for changes in ({'chat_id': 'bob'}, {'chat_type': 'qq_group'}, {'message_id': sent['local_id'] + 1},
                    {'image_id': '../secret'}, {'index': -1}):
        assert not bridge(console, 'MessageImageRead', **dict(params, **changes))['ok']
    other = OlivOS.API.bot_info_T(id=10002, platform_sdk='qqGuildv2_link',
                                  platform_platform='qqGuild', platform_model='public')
    console.loader.Proc_data['bot_info_dict'][other.hash] = other
    assert not bridge(console, 'MessageImageRead', **params, bot_hash=other.hash)['ok']
    assert not bridge(console, 'MessageImageRead', **params, bot_hash='unknown')['ok']
    assert not bridge(console, 'UploadAbort', upload_id=ident)['ok']


def test_image_retention_setting_and_immediate_cleanup(console):
    assert bridge(console, 'Bootstrap')['settings']['image_retention_days'] == 30
    for value in (0, 3651, True, '30'):
        assert not bridge(console, 'SaveSettings', settings={'image_retention_days': value})['ok']
    image_dir = Path('plugin/data/QQOfficialConsole/sent-images')
    stale = image_dir / ('a' * 32 + '.png')
    stale.write_bytes(b'\x89PNG\r\n\x1a\n')
    os.utime(stale, (1, 1))
    result = bridge(console, 'SaveSettings', settings={'image_retention_days': 7})
    assert result['ok'] and result['settings']['image_retention_days'] == 7
    assert not stale.exists()
