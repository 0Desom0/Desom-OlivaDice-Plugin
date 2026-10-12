"""仅打包源码与必要资源，检查 OPK 清单与 UTF-8 无 BOM。"""

import argparse
import hashlib
import json
import threading
import zipfile
from pathlib import Path

LOCK = threading.RLock()


def build(destination=None):
    root = Path(__file__).resolve().parents[1]
    destination = Path(destination or root.with_suffix('.opk')).resolve()
    with LOCK:
        manifest_bytes = (root / 'app.json').read_bytes()
        if manifest_bytes.startswith(b'\xef\xbb\xbf'):
            raise ValueError('app.json 存在 UTF-8 BOM，不能打包。')
        manifest = json.loads(manifest_bytes.decode('utf-8'))
        if manifest['namespace'] != 'MultiCustomSwitch':
            raise ValueError('插件命名空间不匹配。')
        included = sorted(root.glob('*.py')) + [root / 'app.json', root / 'writer_help.md', root / 'README.md']
        included += sorted(path for path in (root / 'webui').rglob('*') if path.is_file())
        required = {'app.json', '__init__.py', 'writer_help.md', 'webui/index.html'}
        names = {path.relative_to(root).as_posix() for path in included}
        if not required <= names:
            raise ValueError(f'缺少必要文件：{required - names}')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in included:
                archive.write(path, path.relative_to(root).as_posix())
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() is not None:
                raise ValueError('OPK 完整性检查失败。')
            if set(archive.namelist()) != names:
                raise ValueError('OPK 文件清单不匹配。')
        return destination, hashlib.sha256(destination.read_bytes()).hexdigest(), len(included)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    arguments = parser.parse_args()
    path, digest, count = build(arguments.output)
    print(f'{path}\n{count} files; SHA-256 {digest}; app.json UTF-8 no BOM')
