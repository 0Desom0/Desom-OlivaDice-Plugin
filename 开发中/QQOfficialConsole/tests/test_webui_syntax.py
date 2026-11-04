"""控制台页面脚本须能被 JavaScript 引擎解析。"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def test_inline_scripts_parse():
    node = shutil.which('node')
    if not node:
        pytest.skip('此检查需要 Node.js')
    html = (Path(__file__).resolve().parents[1] / 'QQOfficialConsole' / 'webui' / 'index.html').read_text(
        encoding='utf-8'
    )
    scripts = re.findall(r'<script(?:\s[^>]*)?>(.*?)</script\s*>', html, re.DOTALL | re.IGNORECASE)
    assert scripts, '页面未找到内联脚本'
    for script in scripts:
        result = subprocess.run([node, '--check'], input=script, text=True, capture_output=True, encoding='utf-8')
        assert result.returncode == 0, result.stderr[-3000:]
