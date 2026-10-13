"""通过真实宿主登录、沙箱页面与消息桥验证账号及内置回复；不打印认证信息。"""

import argparse
import json
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--browser', required=True)
    parser.add_argument('--driver', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    report = json.loads((output / 'host-report.json').read_text(encoding='utf-8'))
    sandbox = Path(report['sandbox'])
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = 'localhost,127.0.0.1'
    options = webdriver.ChromeOptions()
    options.binary_location = args.browser
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1440,1100')
    options.add_argument('--disable-gpu')
    checks = []
    driver = webdriver.Chrome(service=Service(args.driver), options=options)
    wait = WebDriverWait(driver, 25)
    try:
        driver.get(report['url'])
        wait.until(lambda browser: browser.find_element(By.ID, 'token').is_displayed())
        driver.find_element(By.ID, 'token').send_keys((sandbox / 'conf/webui_token.txt').read_text(encoding='utf-8'))
        driver.find_element(By.CSS_SELECTOR, '#login-form button[type="submit"]').click()
        wait.until(lambda browser: browser.find_element(By.ID, 'shell').is_displayed())
        entry = wait.until(lambda browser: browser.find_element(
            By.CSS_SELECTOR, '.plugin-link-entry[data-plugin-namespace="MultiCustomSwitch"]'
        ))
        entry.click()
        frame = wait.until(lambda browser: browser.find_element(
            By.CSS_SELECTOR, 'iframe[src*="/plugin/MultiCustomSwitch/"]'
        ))
        driver.switch_to.frame(frame)
        wait.until(lambda browser: browser.execute_script('return state !== null && !busy;'))
        selector = Select(driver.find_element(By.ID, 'scope'))
        assert len(selector.options) == report['account_count'] + 1
        checks.append('真实账号列表通过宿主消息桥载入')
        for index in range(1, len(selector.options)):
            selector.select_by_index(index)
            wait.until(lambda browser: browser.execute_script('return !busy && selection === 1 && snapshot !== null;'))
            assert driver.execute_script('return state.replies.map(row => row.selection);') == [1, 2]
            assert len(driver.find_elements(By.CSS_SELECTOR, '#entries button')) > 0
        checks.append('两个账号均提供 default 与 smp 及回复内容')
        key = driver.execute_script('return snapshot.entries.find(row => row.key === "strRoll").value;')
        scope = driver.execute_script('return scope;')
        query = driver.find_element(By.ID, 'query')
        query.send_keys('strRoll')
        driver.find_element(By.CSS_SELECTOR, '#entries button').click()
        editor = driver.find_element(By.ID, 'text')
        assert editor.is_enabled()
        editor.clear()
        editor.send_keys('D 盘真实 WebUI 保存验证')
        driver.find_element(By.ID, 'save').click()
        wait.until(
            lambda browser: browser.execute_script('return !busy && active.value === "D 盘真实 WebUI 保存验证";')
        )
        path = sandbox / 'plugin/data/OlivaDice' / scope / 'console/customReply.json'
        assert json.loads(path.read_text(encoding='utf-8'))['strRoll'] == 'D 盘真实 WebUI 保存验证'
        checks.append('default 可编辑且写入 Core 原始文件')
        driver.save_screenshot(str(output / 'webui-default.png'))
        editor.clear()
        editor.send_keys(key)
        driver.find_element(By.ID, 'save').click()
        wait.until(lambda browser: browser.execute_script('return !busy;'))
        Select(driver.find_element(By.ID, 'pack')).select_by_value('2')
        wait.until(lambda browser: browser.execute_script('return !busy && snapshot.readonly;'))
        assert not editor.is_enabled() and not driver.find_element(By.ID, 'save').is_enabled()
        checks.append('smp 只读，编辑和保存按钮均禁用')
        driver.save_screenshot(str(output / 'webui-smp.png'))
        driver.find_element(By.ID, 'help').click()
        wait.until(lambda browser: '群链' in browser.find_element(By.ID, 'help-content').get_attribute('textContent'))
        checks.append('OPK 清理后帮助内容仍可加载')
        assert driver.execute_script('return $("help-content").scrollTop === 0 && $("help-dialog").scrollTop === 0;')
        driver.save_screenshot(str(output / 'webui-help-top.png'))
        driver.execute_script('$("help-content").scrollTop = $("help-content").scrollHeight;')
        assert driver.execute_script('return $("help-content").scrollTop > 0;')
        close = driver.find_element(By.ID, 'help-close')
        assert close.is_displayed() and close.text == '×'
        assert close.rect['y'] < driver.find_element(By.ID, 'help-content').rect['y']
        driver.save_screenshot(str(output / 'webui-help-scrolled.png'))
        close.click()
        wait.until(lambda browser: browser.execute_script('return !$("help-dialog").open;'))
        checks.append('帮助右上角叉号在滚动后仍可关闭')
        driver.find_element(By.ID, 'help').click()
        wait.until(lambda browser: browser.execute_script('return !busy && $("help-dialog").open;'))
        assert driver.execute_script('return $("help-content").scrollTop === 0 && $("help-dialog").scrollTop === 0;')
        checks.append('帮助首次及再次打开均从顶部显示')
        driver.find_element(By.ID, 'help-close').click()
        result = {'ok': True, 'checks': checks}
        (output / 'browser-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        driver.quit()
        (output / 'browser-done').touch()


if __name__ == '__main__':
    main()
