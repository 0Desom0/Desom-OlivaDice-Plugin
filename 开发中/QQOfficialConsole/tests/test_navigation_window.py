"""真实宿主内，长历史窗口与会话缓存的回归；平台消息全部为本地模拟。"""
import os

import pytest
from test_host_bridge import console as nav_console  # noqa: F401
from test_host_bridge import incoming
from test_mobile_readability import mobile_browser

pytestmark = pytest.mark.skipif(not os.environ.get('OLIVOS_WEBUI_BROWSER'), reason='Browser verification is opt-in')


def open_mobile_chat(driver, wait, name):
    from selenium.webdriver.common.by import By

    wait.until(lambda d: d.execute_script('return !switching && !olderLoading'))
    driver.find_element(By.ID, 'showChats').click()

    def attempt(d):
        if d.execute_script('return switching'):
            return False
        for row in d.find_elements(By.CSS_SELECTOR, '#chats .chat-item'):
            if row.find_element(By.TAG_NAME, 'strong').get_attribute('textContent') == name:
                row.click()
                return True
        return False

    wait.until(attempt)
    wait.until(lambda d: d.find_element(By.ID, 'chatTitle').text == name)
    wait.until(lambda d: d.execute_script('return chatReady && !switching'))


def load_previous_page(driver, wait):
    from selenium.webdriver.common.by import By

    driver.execute_script("document.querySelector('#messages').scrollTop = 0")
    wait.until(lambda d: d.execute_script('return !olderLoading && !switching'))
    first = driver.execute_script('return state.messages[0].id')
    driver.find_element(By.ID, 'historyOlder').click()
    wait.until(lambda d: d.execute_script('return state.messages[0].id') != first)
    wait.until(lambda d: d.execute_script('return !olderLoading'))


def test_reopening_long_history_window_returns_to_latest(nav_console):  # noqa: F811
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    for number in range(335):
        incoming(nav_console, 'alice', number, f'历史消息 {number:03d}')
    incoming(nav_console, 'bob', 0, '另一个会话')
    with mobile_browser(nav_console) as (driver, wait, _):
        open_mobile_chat(driver, wait, 'alice')
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '#messages .bubble')) == 30)
        for _ in range(11):
            load_previous_page(driver, wait)
        state = driver.execute_script('''
            const ids=state.messages.filter(m=>m.id>0).map(m=>m.id);
            return {size:ids.length, last:ids[ids.length-1], cursor:state.cursor};
        ''')
        assert state['size'] == 301 and state['last'] < state['cursor'], state
        assert '历史消息 000' in driver.find_elements(By.CSS_SELECTOR, '#messages .bubble')[0].text
        open_mobile_chat(driver, wait, 'bob')
        open_mobile_chat(driver, wait, 'alice')
        # 对最终可见消息验收，不能只检查滚动到了旧窗口底部。
        WebDriverWait(driver, 8).until(
            lambda d: '历史消息 334' in d.find_elements(By.CSS_SELECTOR, '#messages .bubble')[-1].text
        )


def test_full_history_window_alerts_new_message(nav_console):  # noqa: F811
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    for number in range(301):
        incoming(nav_console, 'alice', number, f'历史消息 {number:03d}')
    with mobile_browser(nav_console) as (driver, wait, _):
        open_mobile_chat(driver, wait, 'alice')
        for _ in range(10):
            load_previous_page(driver, wait)
        state = driver.execute_script('''
            const ids=state.messages.filter(m=>m.id>0).map(m=>m.id);
            const box=document.querySelector('#messages');
            return {size:ids.length, last:ids[ids.length-1], cursor:state.cursor,
                    below:box.scrollHeight-box.scrollTop-box.clientHeight};
        ''')
        assert state['size'] == 301 and state['last'] == state['cursor'] and state['below'] > 80, state
        incoming(nav_console, 'alice', 301, '新到消息 301')
        WebDriverWait(driver, 8).until(lambda d: '收到新消息' in d.find_element(By.ID, 'notice').text)
        driver.find_element(By.ID, 'historyLatest').click()
        wait.until(lambda d: '新到消息 301' in d.find_elements(By.CSS_SELECTOR, '#messages .bubble')[-1].text)


def test_old_window_bottom_still_alerts_on_new_message(nav_console):  # noqa: F811
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    for number in range(335):
        incoming(nav_console, 'alice', number, f'历史消息 {number:03d}')
    with mobile_browser(nav_console) as (driver, wait, _):
        open_mobile_chat(driver, wait, 'alice')
        for _ in range(11):
            load_previous_page(driver, wait)
        # 窗口底部不一定是全局最新：旧页挤掉了新页，但 cursor 仍记录原先最新的 id。
        state = driver.execute_script('''
            const box=document.querySelector('#messages');scrollIntent=false;box.scrollTop=box.scrollHeight;
            return {last:state.messages[state.messages.length-1].id,cursor:state.cursor,
                    below:box.scrollHeight-box.scrollTop-box.clientHeight};
        ''')
        assert state['last'] < state['cursor'] and state['below'] < 3, state
        incoming(nav_console, 'alice', 335, '新到消息 335')
        WebDriverWait(driver, 8).until(lambda d: '收到新消息' in d.find_element(By.ID, 'notice').text)
        driver.find_element(By.ID, 'historyLatest').click()
        wait.until(lambda d: '新到消息 335' in d.find_elements(By.CSS_SELECTOR, '#messages .bubble')[-1].text)
