"""本地文件系统中的图片上传、表情与临时文件行为。"""
import base64
import importlib.util
import os
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / 'QQOfficialConsole' / 'media.py'
SPEC = importlib.util.spec_from_file_location('qqconsole_media_test', MODULE_PATH)
media = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(media)

PNG = b'\x89PNG\r\n\x1a\n' + b'local image bytes'


@pytest.fixture
def manager(tmp_path):
    return media.MediaManager(tmp_path)


def encoded(data):
    return base64.b64encode(data).decode('ascii')


def upload(manager, data=PNG, bot='bot-a', name='image.png'):
    ident = manager.begin(name, len(data), bot_hash=bot)['upload_id']
    for index, start in enumerate(range(0, len(data), media.CHUNK_SIZE)):
        result = manager.chunk(ident, index, encoded(data[start:start + media.CHUNK_SIZE]), bot)
    assert result['complete'] and result['received'] == len(data)
    return ident


def temp_files(manager):
    return set(manager.temp.iterdir())


def test_chunked_upload_order_and_abort(manager):
    data = PNG + b'x' * media.CHUNK_SIZE
    ident = manager.begin('test.png', len(data), 'image/png', 'bot-a')['upload_id']
    with pytest.raises(ValueError):
        manager.chunk(ident, 1, encoded(data[:media.CHUNK_SIZE]), 'bot-a')
    first = manager.chunk(ident, 0, encoded(data[:media.CHUNK_SIZE]), 'bot-a')
    assert first == {'upload_id': ident, 'complete': False, 'received': media.CHUNK_SIZE}
    with pytest.raises(ValueError):
        manager.resolve(ident, 'bot-a')
    last = manager.chunk(ident, 1, encoded(data[media.CHUNK_SIZE:]), 'bot-a')
    assert last['complete'] and last['received'] == len(data)
    assert Path(manager.resolve(ident, 'bot-a')).read_bytes() == data
    manager.abort(ident, 'bot-a')
    assert not temp_files(manager)


@pytest.mark.parametrize(('name', 'data'), [
    ('fake.png', b'not an image'),
    ('wrong.jpg', PNG),
    ('fake.webp', b'RIFFxxxxNOT!'),
])
def test_invalid_magic_discards_upload(manager, name, data):
    ident = manager.begin(name, len(data), bot_hash='bot-a')['upload_id']
    with pytest.raises(ValueError, match='格式'):
        manager.chunk(ident, 0, encoded(data), 'bot-a')
    assert not temp_files(manager)
    with pytest.raises(ValueError):
        manager.resolve(ident, 'bot-a')


def test_size_limit_inclusive_and_oversize_rejected(manager):
    with pytest.raises(ValueError, match='过大'):
        manager.begin('large.png', media.MAX_SIZE + 1, bot_hash='bot-a')
    assert not temp_files(manager)
    data = PNG + b'x' * (media.MAX_SIZE - len(PNG))
    ident = upload(manager, data)
    assert Path(manager.resolve(ident, 'bot-a')).stat().st_size == media.MAX_SIZE
    manager.abort(ident, 'bot-a')
    assert not temp_files(manager)


def test_overrun_chunk_discards_partial_upload(manager):
    ident = manager.begin('image.png', len(PNG), bot_hash='bot-a')['upload_id']
    with pytest.raises(ValueError, match='过大'):
        manager.chunk(ident, 0, encoded(PNG + b'x'), 'bot-a')
    assert not temp_files(manager)


def test_uploads_are_isolated_between_bots(manager):
    ident = manager.begin('image.png', len(PNG), bot_hash='bot-a')['upload_id']
    with pytest.raises(ValueError):
        manager.chunk(ident, 0, encoded(PNG), 'bot-b')
    manager.chunk(ident, 0, encoded(PNG), 'bot-a')
    for operation in (
        lambda: manager.resolve(ident, 'bot-b'),
        lambda: manager.abort(ident, 'bot-b'),
        lambda: manager.save(ident, 'stolen', 'bot', 'bot-b'),
        lambda: manager.sending([ident], 'bot-b').__enter__(),
    ):
        with pytest.raises(ValueError):
            operation()
    assert Path(manager.resolve(ident, 'bot-a')).read_bytes() == PNG
    manager.abort(ident, 'bot-a')


def test_emoji_persists_rename_select_delete_and_bot_isolation(manager, tmp_path):
    ident = upload(manager)
    emoji = manager.save(ident, '原名称', 'bot', 'bot-a')
    manager.abort(ident, 'bot-a')
    assert not temp_files(manager)
    emoji_id = emoji['id']
    reopened = media.MediaManager(tmp_path)
    assert reopened.list_emojis('bot', 'bot-a') == [emoji]
    assert reopened.list_emojis('bot', 'bot-b') == []
    for operation in (
        lambda: reopened.use_emoji(emoji_id, 'bot', 'bot-b'),
        lambda: reopened.rename_emoji(emoji_id, 'stolen', 'bot', 'bot-b'),
        lambda: reopened.delete_emoji(emoji_id, 'bot', 'bot-b'),
    ):
        with pytest.raises(ValueError):
            operation()
    renamed = reopened.rename_emoji(emoji_id, '新名称', 'bot', 'bot-a')
    assert renamed['name'] == '新名称'
    assert media.MediaManager(tmp_path).list_emojis('bot', 'bot-a') == [renamed]
    selected = reopened.use_emoji(emoji_id, 'bot', 'bot-a')['upload_id']
    with reopened.sending([selected], 'bot-a') as paths:
        assert Path(paths[0]).read_bytes() == PNG
    assert not temp_files(reopened)
    assert reopened.list_emojis('bot', 'bot-a') == [renamed]
    selected_again = reopened.use_emoji(emoji_id, 'bot', 'bot-a')['upload_id']
    reopened.abort(selected_again, 'bot-a')
    reopened.delete_emoji(emoji_id, 'bot', 'bot-a')
    assert reopened.list_emojis('bot', 'bot-a') == []
    with pytest.raises(ValueError):
        reopened.use_emoji(emoji_id, 'bot', 'bot-a')
    assert not temp_files(reopened)


def test_global_emoji_can_be_selected_by_other_bot(manager):
    ident = upload(manager)
    emoji_id = manager.save(ident, 'global', 'global', 'bot-a')['id']
    manager.abort(ident, 'bot-a')
    assert manager.list_emojis('global', 'bot-b')[0]['id'] == emoji_id
    selected = manager.use_emoji(emoji_id, 'global', 'bot-b')['upload_id']
    with manager.sending([selected], 'bot-b') as paths:
        assert Path(paths[0]).read_bytes() == PNG
    assert not temp_files(manager)


def test_emoji_chunk_read_and_failed_selection_cleanup(manager):
    data = PNG + b'x' * media.CHUNK_SIZE
    ident = upload(manager, data)
    emoji_id = manager.save(ident, 'large', 'bot', 'bot-a')['id']
    manager.abort(ident, 'bot-a')
    first = manager.read_emoji_chunk(emoji_id, 'bot', 'bot-a', 0)
    second = manager.read_emoji_chunk(emoji_id, 'bot', 'bot-a', 1)
    assert first['mime'] == 'image/png' and first['size'] == len(data)
    assert not first['complete'] and second['complete']
    assert base64.b64decode(first['data_b64']) + base64.b64decode(second['data_b64']) == data
    with pytest.raises(ValueError):
        manager.read_emoji_chunk(emoji_id, 'bot', 'bot-a', 2)
    image = next(manager.emoji.rglob(emoji_id + '.png'))
    image.write_bytes(b'invalid image')
    with pytest.raises(ValueError, match='格式'):
        manager.use_emoji(emoji_id, 'bot', 'bot-a')
    assert not temp_files(manager)


@pytest.mark.parametrize('fails', [False, True], ids=['success', 'failure'])
def test_send_always_removes_temp_files(manager, fails):
    ids = [upload(manager), upload(manager)]
    paths = [Path(manager.resolve(ident, 'bot-a')) for ident in ids]

    def send():
        with manager.sending(ids, 'bot-a') as claimed:
            assert [Path(path) for path in claimed] == paths
            assert all(path.is_file() for path in paths)
            with pytest.raises(ValueError):
                manager.abort(ids[0], 'bot-a')
            if fails:
                raise RuntimeError('simulated send failure')

    if fails:
        with pytest.raises(RuntimeError, match='simulated send failure'):
            send()
    else:
        send()
    assert not temp_files(manager)
    for ident in ids:
        with pytest.raises(ValueError):
            manager.resolve(ident, 'bot-a')


def test_cleanup_removes_only_stale_untracked_temp_files(manager):
    ident = upload(manager)
    active = Path(manager.resolve(ident, 'bot-a'))
    stale = manager.temp / 'stale.png'
    fresh = manager.temp / 'fresh.png'
    stale.write_bytes(PNG)
    fresh.write_bytes(PNG)
    os.utime(stale, (1, 1))
    os.utime(active, (1, 1))
    manager.cleanup(max_age=3600)
    assert not stale.exists()
    assert active.exists() and fresh.exists()
    manager.abort(ident, 'bot-a')


def test_sent_images_chunk_restart_expiry_and_cleanup_scope(manager, tmp_path):
    data = PNG + b'x' * media.CHUNK_SIZE
    ident = upload(manager, data)
    with manager.sending([ident], 'bot-a') as paths:
        image = manager.persist_sent(paths, [{'marker': 'img_a'}])[0]
    assert not temp_files(manager)
    reopened = media.MediaManager(tmp_path)
    chunks = [reopened.read_sent_chunk(image, i, 30) for i in range(2)]
    assert b''.join(base64.b64decode(chunk['data_b64']) for chunk in chunks) == data
    assert chunks[0]['total_chunks'] == 2
    for index in (-1, 2, True):
        with pytest.raises(ValueError):
            reopened.read_sent_chunk(image, index, 30)
    stored = reopened.sent / (image['image_id'] + '.png')
    unrelated = reopened.sent / 'unrelated.png'
    unrelated.write_bytes(PNG)
    os.utime(stored, (1, 1))
    reopened.cleanup_sent(30)
    assert not stored.exists() and unrelated.exists()
    with pytest.raises(ValueError, match='失效'):
        reopened.read_sent_chunk(image, 0, 30)


def test_sent_copy_failure_removes_partial_files(manager, monkeypatch):
    first, second = upload(manager), upload(manager)
    original = media.shutil.copyfileobj
    calls = []

    def fail_second(source, destination):
        calls.append(1)
        if len(calls) == 2:
            raise OSError('private path')
        original(source, destination)

    monkeypatch.setattr(media.shutil, 'copyfileobj', fail_second)
    with pytest.raises(ValueError, match='图片上传失败'):
        with manager.sending([first, second], 'bot-a') as paths:
            manager.persist_sent(paths, [{}, {}])
    assert not temp_files(manager) and not list(manager.sent.iterdir())


def test_sent_read_expires_and_rejects_symlink(manager, tmp_path):
    ident = upload(manager)
    with manager.sending([ident], 'bot-a') as paths:
        image = manager.persist_sent(paths, [{}])[0]
    path = manager.sent / (image['image_id'] + '.png')
    os.utime(path, (1, 1))
    with pytest.raises(ValueError, match='失效'):
        manager.read_sent_chunk(image, 0, 30)
    assert not path.exists()
    outside = tmp_path / 'outside.png'
    outside.write_bytes(PNG)
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip('symlink creation unavailable')
    with pytest.raises(ValueError, match='失效'):
        manager.read_sent_chunk(image, 0, 30)
    manager.cleanup_sent(30)
    assert outside.read_bytes() == PNG and path.is_symlink()
