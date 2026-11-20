# -*- coding: utf-8 -*-
"""让用例优先跑在 OlivOS 源码树上，而不是 site-packages 里的旧版本。

本机 site-packages 长期停在 0.11.83，缺 get_qq_group_passive_limit、
_send_qq_api 等新接口；测试按仓库版 OlivOS 编写，这里把它插到 sys.path 最前。
设置环境变量 OLIVOS_SRC 可以显式指定 OlivOS 源码根目录。
"""

import os
import sys
from pathlib import Path

CANDIDATES = [os.environ.get('OLIVOS_SRC')]
PROJECTS = Path(__file__).resolve().parents[4]
CANDIDATES += [str(PROJECTS / 'pr-work' / 'OlivOS'), str(PROJECTS / 'OlivOS')]

for candidate in CANDIDATES:
    if not candidate:
        continue
    root = Path(candidate)
    if (root / 'OlivOS' / '__init__.py').exists():
        text = str(root)
        if text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)
        break
