"""静态帮助在导入时注入内存，支持 OPK 解包目录随后被删除。"""

import json
from pathlib import Path

from . import files

_ROOT = Path(__file__).parent
VERSION = json.loads(files.read_bytes(_ROOT / 'app.json'))['version']
WRITER_HELP = files.read_bytes(_ROOT / 'writer_help.md').decode('utf-8')
