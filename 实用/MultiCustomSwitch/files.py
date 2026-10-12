"""同进程的可重入文件锁与可恢复的批量写入。"""

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

LOCK = threading.RLock()


@contextmanager
def locked_open(*args, **kwargs):
    # Core / NativeGUI 的原实现使用 with open；锁随文件上下文释放。
    with LOCK, open(*args, **kwargs) as stream:
        yield stream


def read_bytes(path):
    with LOCK:
        return Path(path).read_bytes()


def read_json(path, default=None):
    with LOCK:
        if not Path(path).is_file():
            return default
        return json.loads(read_bytes(path).decode('utf-8-sig'))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=4) + '\n').encode('utf-8')


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.mcs-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_json(path, value):
    with LOCK:
        _write(path, json_bytes(value))


def transaction(changes):
    """锁内提交；任一写入失败时恢复本次涉及的所有文件。"""
    with LOCK:
        previous = {Path(path): read_bytes(path) if Path(path).is_file() else None for path in changes}
        completed = []
        try:
            for path, data in changes.items():
                path = Path(path)
                completed.append(path)
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    _write(path, data)
        except Exception:
            for path in reversed(completed):
                data = previous[path]
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    _write(path, data)
            raise
