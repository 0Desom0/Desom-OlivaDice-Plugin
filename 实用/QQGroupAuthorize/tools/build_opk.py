"""只打包运行所需文件，不混入缓存、测试或开发者账号数据。"""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

SOURCE = Path(__file__).resolve().parents[1]
FILES = ('__init__.py', 'app.json', 'main.py', 'transport.py', 'resources.py', 'renderer.py', 'config.py')


def build():
    raw = (SOURCE / 'app.json').read_bytes()
    if raw.startswith(b'\xef\xbb\xbf'):
        raise ValueError('app.json must be UTF-8 without BOM')
    manifest = json.loads(raw.decode('utf-8'))
    destination = SOURCE / (manifest['namespace'] + '.opk')
    with ZipFile(destination, 'w', compression=ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(SOURCE / name, name)
        archive.write(SOURCE / 'authorization.html', 'authorization.html')
    print(destination)


if __name__ == '__main__':
    build()
