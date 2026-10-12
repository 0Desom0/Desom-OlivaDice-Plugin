import hashlib
import importlib.util
import json
import multiprocessing
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_storage():
    path = Path(__file__).resolve().parents[1] / 'StatusHud/storage.py'
    spec = importlib.util.spec_from_file_location('statushud_storage_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UserConfig:
    @staticmethod
    def getRedirectedBotHash(bot_hash):
        return bot_hash

    @staticmethod
    def getUserHash(user_id, user_type, platform):
        return hashlib.md5(f'{user_id}{user_type}{platform}'.encode()).hexdigest()


def toggle_worker(root, count):
    module = load_storage()
    storage = module.Storage(SimpleNamespace(userConfig=UserConfig()), root)
    for _ in range(count):
        storage.set_user('bot', '1', 'qq')


@pytest.fixture
def data(tmp_path):
    module = load_storage()
    storage = module.Storage(SimpleNamespace(userConfig=UserConfig()), tmp_path / 'StatusHud')
    return module, storage


def test_parallel_toggle_is_one_read_modify_write(data):
    _, storage = data
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: storage.set_user('bot', '1', 'qq'), range(100)))
    assert storage.status('bot', '1', 'qq') == {
        'enabled': True, 'source': 'user', 'global_enabled': True,
    }


def test_cross_process_toggle_does_not_lose_updates(data):
    _, storage = data
    context = multiprocessing.get_context('spawn')
    processes = [context.Process(target=toggle_worker, args=(storage.root, 25)) for _ in range(4)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            pytest.fail('文件锁测试进程超时')
        assert process.exitcode == 0
    assert storage.status('bot', '1', 'qq')['enabled']


def test_missing_user_and_english_json_keys(data):
    module, storage = data
    storage.initialize('bot')
    storage.status('bot', '1', 'qq')
    assert not list((storage.root / 'bot/user').iterdir())
    storage.set_user('bot', '1', 'qq', False)
    with module._bot_lock(storage.root / 'bot'):
        with (storage.root / 'bot/config.json').open(encoding='utf-8') as stream:
            assert json.load(stream) == {'global_enabled': True}
        with next((storage.root / 'bot/user').glob('*.json')).open(encoding='utf-8') as stream:
            assert json.load(stream) == {'enabled': False}
        assert not list((storage.root / 'bot').rglob('*.tmp'))


@pytest.mark.parametrize('contents', ['{broken', '[]', '{"global_enabled":"false"}'])
def test_corrupt_config_is_never_overwritten(data, contents):
    module, storage = data
    storage.initialize('bot')
    path = storage.root / 'bot/config.json'
    with module._bot_lock(storage.root / 'bot'):
        path.write_text(contents, encoding='utf-8')
    with pytest.raises(module.StorageError):
        storage.set_global('bot', False)
    with module._bot_lock(storage.root / 'bot'):
        assert path.read_text(encoding='utf-8') == contents


def test_failed_atomic_replace_keeps_previous_data_and_releases_lock(data, monkeypatch):
    module, storage = data
    storage.set_user('bot', '1', 'qq', True)
    original = module.os.replace
    def fail_replace(*args):
        raise OSError('simulated replace failure')
    monkeypatch.setattr(module.os, 'replace', fail_replace)
    with pytest.raises(module.StorageError):
        storage.set_user('bot', '1', 'qq', False)
    monkeypatch.setattr(module.os, 'replace', original)
    assert storage.status('bot', '1', 'qq')['enabled']
    storage.set_user('bot', '1', 'qq', False)
    assert not storage.status('bot', '1', 'qq')['enabled']


def test_path_traversal_is_rejected(data):
    module, storage = data
    with pytest.raises(module.StorageError):
        storage.initialize('../outside')
