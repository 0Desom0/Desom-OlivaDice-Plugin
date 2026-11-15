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
    path = Path(__file__).resolve().parents[1] / 'storage.py'
    spec = importlib.util.spec_from_file_location('statushud_storage_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UserConfig:
    """替身 Core：只实现 StatusHud 用到的两个接口。"""

    auto_sn = False
    sn_auto_calls = 0

    @classmethod
    def getRedirectedBotHash(cls, bot_hash):
        return bot_hash

    @staticmethod
    def getUserHash(user_id, user_type, platform):
        return hashlib.md5(f'{user_id}{user_type}{platform}'.encode()).hexdigest()

    @classmethod
    def getUserConfigByKey(cls, userId, userType, platform, userConfigKey, botHash):
        assert userConfigKey == 'autoSnEnabled'
        cls.sn_auto_calls += 1
        return cls.auto_sn


def toggle_worker(root, count):
    module = load_storage()
    storage = module.Storage(SimpleNamespace(userConfig=UserConfig()), root)
    for _ in range(count):
        storage.set_user('bot', '1', 'qq')


@pytest.fixture
def data(tmp_path):
    module = load_storage()
    UserConfig.auto_sn = False
    UserConfig.sn_auto_calls = 0
    storage = module.Storage(SimpleNamespace(userConfig=UserConfig()), tmp_path / 'StatusHud')
    return module, storage


def test_parallel_toggle_is_one_read_modify_write(data):
    _, storage = data
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: storage.set_user('bot', '1', 'qq'), range(100)))
    assert storage.status('bot', '1', 'qq') == {
        'enabled': False, 'hud_enabled': False, 'sn_auto_enabled': False, 'mode': 3, 'source': 'user',
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
    assert not storage.status('bot', '1', 'qq')['enabled']


def test_missing_user_and_english_json_keys(data):
    module, storage = data
    storage.initialize('bot')
    storage.status('bot', '1', 'qq')
    assert not list((storage.root / 'bot/user').iterdir())
    storage.set_user('bot', '1', 'qq', False)
    with module._bot_lock(storage.root / 'bot'):
        with (storage.root / 'bot/config.json').open(encoding='utf-8') as stream:
            assert json.load(stream) == {'mode': 3}
        with next((storage.root / 'bot/user').glob('*.json')).open(encoding='utf-8') as stream:
            assert json.load(stream) == {'enabled': False}
        assert not list((storage.root / 'bot').rglob('*.tmp'))


@pytest.mark.parametrize('contents', ['{broken', '[]', '{"global_enabled":"false"}', '{"mode":0}'])
def test_corrupt_config_is_never_overwritten(data, contents):
    module, storage = data
    storage.initialize('bot')
    path = storage.root / 'bot/config.json'
    with module._bot_lock(storage.root / 'bot'):
        path.write_text(contents, encoding='utf-8')
    with pytest.raises(module.StorageError):
        storage.set_global('bot', 2)
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


@pytest.mark.parametrize('config', [None, {}])
def test_default_mode_when_config_or_flag_is_missing(data, config):
    module, storage = data
    directory = storage.root / 'bot'
    if config is not None:
        with module._bot_lock(directory):
            (directory / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    assert storage.status('bot', '1', 'qq') == {
        'enabled': False, 'hud_enabled': False, 'sn_auto_enabled': False, 'mode': 3, 'source': 'mode',
    }
    assert storage.set_user('bot', '1', 'qq')
    storage.initialize('bot')
    assert storage.status('bot', '1', 'qq')['enabled']
    assert not storage.status('bot', '2', 'qq')['enabled']


@pytest.mark.parametrize('saved_mode', [1, 2, 3])
def test_initialize_preserves_saved_mode_and_personal_overrides(data, saved_mode):
    _, storage = data
    storage.set_global('bot', saved_mode)
    storage.set_user('bot', '1', 'qq', True)
    storage.set_user('bot', '2', 'qq', False)
    storage.initialize('bot')
    assert storage.status('bot', '3', 'qq')['hud_enabled'] is (saved_mode == 1)
    assert storage.status('bot', '3', 'qq')['mode'] == saved_mode
    assert storage.status('bot', '1', 'qq')['enabled']
    assert not storage.status('bot', '2', 'qq')['enabled']


@pytest.mark.parametrize('legacy,mode', [(True, 1), (False, 2)])
def test_legacy_boolean_global_is_migrated(data, legacy, mode):
    module, storage = data
    directory = storage.root / 'bot'
    with module._bot_lock(directory):
        (directory / 'config.json').write_text(json.dumps({'global_enabled': legacy}), encoding='utf-8')
    assert storage.status('bot', '1', 'qq')['mode'] == mode
    with module._bot_lock(directory):
        with (directory / 'config.json').open(encoding='utf-8') as stream:
            assert json.load(stream) == {'mode': mode}
    storage.set_global('bot', 3)
    with module._bot_lock(directory):
        with (directory / 'config.json').open(encoding='utf-8') as stream:
            assert json.load(stream) == {'mode': 3}


@pytest.mark.parametrize('mode,sn_auto,personal,enabled', [
    (3, False, None, False),
    (3, True, None, True),
    (3, True, False, True),
    (3, True, True, True),
    (3, False, True, True),
    (2, True, None, False),
    (1, False, None, True),
])
def test_mode_and_sn_auto_resolution(data, mode, sn_auto, personal, enabled):
    _, storage = data
    storage.set_global('bot', mode)
    if personal is not None:
        storage.set_user('bot', '1', 'qq', personal)
    UserConfig.auto_sn = sn_auto
    status = storage.status('bot', '1', 'qq')
    assert status['enabled'] is enabled
    assert status['mode'] == mode
    assert status['sn_auto_enabled'] is (sn_auto if mode == 3 else False)


def test_sn_auto_is_only_read_in_mode_three(data):
    _, storage = data
    storage.set_global('bot', 1)
    storage.status('bot', '1', 'qq')
    assert UserConfig.sn_auto_calls == 0
    storage.set_global('bot', 3)
    storage.status('bot', '1', 'qq')
    assert UserConfig.sn_auto_calls == 1


def test_sn_auto_read_failure_falls_back_to_off(data):
    _, storage = data
    storage.set_global('bot', 3)

    class Broken(UserConfig):
        @classmethod
        def getUserConfigByKey(cls, userId, userType, platform, userConfigKey, botHash):
            raise KeyError('configNote')

    storage.core = SimpleNamespace(userConfig=Broken())
    logs = []
    storage.log = lambda message, error=None: logs.append(message)
    assert storage.status('bot', '1', 'qq')['enabled'] is False
    assert logs and 'sn auto' in logs[0]


@pytest.mark.parametrize('mode', [0, 4, True, '3', None])
def test_global_mode_rejects_invalid_values(data, mode):
    module, storage = data
    with pytest.raises(module.StorageError):
        storage.set_global('bot', mode)
