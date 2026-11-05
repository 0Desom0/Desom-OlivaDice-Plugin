"""群资料页的异步群名刷新提示和状态同步。"""
import os
import time
from types import SimpleNamespace

import pytest
from test_mobile_readability import mobile_browser

pytest_plugins = ['test_host_bridge']


@pytest.mark.skipif(not os.environ.get('OLIVOS_WEBUI_BROWSER'), reason='浏览器回归验证需手动开启')
def test_group_info_view_tracks_asynchronous_refresh(console, monkeypatch):
    from selenium.webdriver.common.by import By
    from OlivOS import qqGuildv2SDK

    monkeypatch.setattr(qqGuildv2SDK.event_action, 'get_qq_group_bot_state',
                        lambda *a, **k: {'active': True, 'data': {'response': {'member_role': 'member'}}})
    raw = {'id': 'group-msg-1', 'content': '群消息', 'timestamp': int(time.time())}
    event = SimpleNamespace(
        platform={'sdk': 'qqGuildv2_link'}, bot_info=console.bot,
        data=SimpleNamespace(group_id='group1', user_id='u1', sender={'nickname': '成员'},
                             extend={'flag_from_qq': True, 'qq_event_data': raw}),
        sdk_event=SimpleNamespace(payload=SimpleNamespace(data=SimpleNamespace(t='GROUP_MESSAGE_CREATE'))),
    )
    console.module.main.Event.group_message(event, console.loader)
    database, _, _, _, bridge = console.module.main._state
    database.upsert_chat(console.bot.hash, 'qq_group', 'group1', display_name='旧群名')
    monkeypatch.setattr(bridge, 'wake_group_info', lambda: None)
    with mobile_browser(console) as (driver, wait, _):
        wait.until(lambda d: d.find_element(By.ID, 'showChats').is_displayed())
        driver.find_element(By.ID, 'showChats').click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#chats .chat-item'))[0].click()
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#messages .bubble'))
        driver.find_element(By.ID, 'showInfo').click()
        wait.until(lambda d: '旧群名' in d.find_element(By.ID, 'rightBody').text)
        next(e for e in driver.find_elements(By.CSS_SELECTOR, '#rightBody button') if e.text == '刷新群名').click()
        wait.until(lambda d: '排队获取中' in d.find_element(By.ID, 'rightBody').text)
        assert '群名刷新已排队' in driver.find_element(By.ID, 'notice').text
        database.upsert_chat(console.bot.hash, 'qq_group', 'group1', display_name='更新后群名')
        database.complete_group_info_job(console.bot.hash, 'group1')
        wait.until(lambda d: '更新后群名' in d.find_element(By.ID, 'rightBody').text)
        assert '排队获取中' not in driver.find_element(By.ID, 'rightBody').text
