"""真实宿主中的手机尺寸、可读性和消息导航回归。"""
import os
import queue
import threading
import time
from contextlib import contextmanager

import pytest
from test_host_bridge import incoming

pytest_plugins = ['test_host_bridge']


@contextmanager
def mobile_browser(console, width=390, height=844):
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

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
    options.binary_location = os.environ['OLIVOS_CHROME_BINARY']
    for arg in ('--headless=new', '--no-first-run', '--disable-background-networking'):
        options.add_argument(arg)
    driver = None
    try:
        assert host.ready.wait(10) and host.error is None
        driver = webdriver.Chrome(options=options, service=Service(executable_path=os.environ['OLIVOS_CHROMEDRIVER']))
        driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
            'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': True,
        })
        wait = WebDriverWait(driver, 30, ignored_exceptions=(StaleElementReferenceException,))
        driver.get(f"http://127.0.0.1:{host.config['port']}/")
        wait.until(lambda d: d.find_element(By.ID, 'login').is_displayed())
        ticket_url = host.local_action({'action': 'open'})['url']
        driver.execute_script('location.hash = new URL(arguments[0]).hash', ticket_url)
        wait.until(lambda d: d.find_element(By.ID, 'shell').is_displayed())
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#plugin-links .plugin-link-entry'))
        driver.find_element(By.CSS_SELECTOR, '#plugin-links .plugin-link-entry').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#plugin-frame-container iframe'))
        iframe = driver.find_element(By.CSS_SELECTOR, '#plugin-frame-container iframe')
        frame_rect = iframe.rect
        driver.switch_to.frame(iframe)
        yield driver, wait, frame_rect
    finally:
        if driver is not None:
            driver.quit()
        stopped.set()
        worker.join(timeout=5)
        host.on_terminate()
        service.join(timeout=5)
        assert not service.is_alive()


@pytest.mark.skipif(not os.environ.get('OLIVOS_WEBUI_BROWSER'), reason='浏览器回归验证需手动开启')
def test_mobile_message_text_is_readable_and_frame_fills_screen(console):
    from selenium.webdriver.common.by import By

    for number in range(8):
        incoming(console, 'alice', number, f'消息 {number} 测试中文的可读性')
    with mobile_browser(console) as (driver, wait, frame):
        wait.until(lambda d: d.find_element(By.ID, 'showChats').is_displayed())
        driver.find_element(By.ID, 'showChats').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#chats .chat-item'))[0].click()
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '#messages .bubble')) == 8)
        layout = driver.execute_script('''
          const q=s=>document.querySelector(s), rect=s=>q(s).getBoundingClientRect().toJSON();
          return {width:innerWidth,height:innerHeight,app:rect('#app'),messages:rect('#messages'),
            composer:rect('#composer'),bodySize:parseFloat(getComputedStyle(document.body).fontSize),
            bubbleSize:parseFloat(getComputedStyle(q('.bubble')).fontSize),
            send:rect('#send'),hasHorizontalOverflow:document.documentElement.scrollWidth>innerWidth};
        ''')
        print('MOBILE_GEOMETRY', layout, 'HOST_FRAME', frame)
        assert frame['width'] >= 380 and frame['height'] >= 740
        assert layout['bubbleSize'] >= 16, layout
        assert layout['send']['height'] >= 44, layout
        assert layout['messages']['height'] >= 300, layout
        assert not layout['hasHorizontalOverflow'], layout


@pytest.mark.skipif(not os.environ.get('OLIVOS_WEBUI_BROWSER'), reason='浏览器回归验证需手动开启')
def test_narrow_view_keeps_long_names_and_controls_in_bounds(console):
    from selenium.webdriver.common.by import By

    from test_host_bridge import bridge

    long_name = '非常长的群名超出屏幕宽度' * 8
    incoming(console, 'alice', 1, '窄屏消息')
    assert bridge(console, 'SetRemark', chat_type='qq_private', chat_id='alice', remark=long_name)['ok']
    with mobile_browser(console, width=320, height=568) as (driver, wait, _):
        wait.until(lambda d: d.find_element(By.ID, 'showChats').is_displayed())
        driver.find_element(By.ID, 'showChats').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#chats .chat-item'))[0].click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#messages .bubble'))
        metrics = driver.execute_script('''
          const b=s=>document.querySelector(s).getBoundingClientRect().toJSON();
          return {width:innerWidth, height:innerHeight, title:b('#chatTitle'),info:b('#showInfo'),
            message:b('#messages'), send:b('#send'), composer:b('#composer'), older:b('#historyOlder'),
            latest:b('#historyLatest'), overflow:document.documentElement.scrollWidth>innerWidth};
        ''')
        print('NARROW_METRICS', metrics)
        assert not metrics['overflow'], metrics
        assert metrics['title']['right'] <= metrics['info']['left'] + 1, metrics
        assert metrics['message']['height'] >= 180, metrics
        assert 0 <= metrics['send']['left'] < metrics['send']['right'] <= metrics['width'], metrics
        assert metrics['send']['bottom'] <= metrics['height'] + 1, metrics
        for name in ('older', 'latest'):
            button = metrics[name]
            assert button['width'] >= 44 and button['height'] >= 44, metrics
            assert 0 <= button['left'] < button['right'] <= metrics['width'], metrics
            assert metrics['message']['top'] <= button['top'] < button['bottom'] <= metrics['message']['bottom'], (
                metrics
            )


@pytest.mark.skipif(not os.environ.get('OLIVOS_WEBUI_BROWSER'), reason='浏览器回归验证需手动开启')
def test_mobile_click_older_pages_and_return_latest(console):
    from selenium.webdriver.common.by import By

    for number in range(65):
        incoming(console, 'alice', number, f'第 {number:02d} 条：' + '历史消息可读性测试 ' * 5)
    with mobile_browser(console) as (driver, wait, _):
        wait.until(lambda d: d.find_element(By.ID, 'showChats').is_displayed())
        driver.find_element(By.ID, 'showChats').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#chats .chat-item'))[0].click()
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '#messages .bubble')) == 30)
        assert '第 64 条' in driver.find_elements(By.CSS_SELECTOR, '#messages .bubble')[-1].text
        older = driver.find_element(By.ID, 'historyOlder')
        newer = driver.find_element(By.ID, 'historyLatest')
        assert older.is_displayed() and newer.is_displayed()
        assert older.rect['height'] >= 44 and newer.rect['height'] >= 44
        older.click()  # 滚到当前加载区顶部
        wait.until(lambda d: d.execute_script("return document.querySelector('#messages').scrollTop") < 3)
        older.click()  # 请求上一页
        wait.until(lambda d: any('第 05 条' in b.text for b in d.find_elements(By.CSS_SELECTOR, '#messages .bubble')))
        older.click()  # 请求最早剩余的消息
        wait.until(lambda d: any('第 00 条' in b.text for b in d.find_elements(By.CSS_SELECTOR, '#messages .bubble')))
        # 到最早一条之后，内联「加载更早消息」按钮必须消失，↑ 给出提示。
        wait.until(lambda d: not any(
            e.text == '加载更早消息' for e in d.find_elements(By.CSS_SELECTOR, '#messages button')))
        driver.find_element(By.ID, 'historyOlder').click()
        # 第一次点击可能只是滚到顶部；重复点击直到出现「已经是最早的消息」提示。
        def notice_shown(d):
            if '已经是最早的消息' in d.find_element(By.ID, 'notice').text:
                return True
            d.find_element(By.ID, 'historyOlder').click()
            return False

        wait.until(notice_shown)
        incoming(console, 'alice', 65, '第 65 条：阅读旧消息时新收到的消息')
        # 停留在旧窗口时收到新消息，轮询必须给出「有新消息」提示，且只提示一次不刷屏。
        wait.until(lambda d: '收到新消息' in d.find_element(By.ID, 'notice').text)
        driver.execute_script('window.__noticeCount=0;const real=notice;notice=t=>{window.__noticeCount++;return real(t)}')
        time.sleep(2.5)  # 至少跨过两个轮询周期
        assert driver.execute_script('return window.__noticeCount') == 0
        newer.click()
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '#messages .bubble')) == 30)
        wait.until(lambda d: '第 65 条' in d.find_elements(By.CSS_SELECTOR, '#messages .bubble')[-1].text)
        near_bottom = driver.execute_script('''const e=document.querySelector('#messages');
          return e.scrollHeight-e.scrollTop-e.clientHeight < 3''')
        assert near_bottom
