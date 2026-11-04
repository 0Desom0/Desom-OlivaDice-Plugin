"""Chunked image uploads and persistent, bot-scoped emoji storage."""

import base64
import binascii
import hashlib
import io
import json
import os
import re
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

CHUNK_SIZE = 256 * 1024
MAX_SIZE = 10 * 1024 * 1024
MAX_ACTIVE_UPLOADS = 4
MAX_PENDING_PER_BOT = 36
UPLOAD_IDLE_SECONDS = 3600
_ID = re.compile(r'^[0-9a-f]{32}$')
_EXTENSIONS = {'png': 'png', 'jpg': 'jpg', 'jpeg': 'jpg', 'gif': 'gif', 'webp': 'webp'}
_MIMES = {'png': 'image/png', 'jpg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp'}


def _safe_io(function):
    """Never expose host filesystem paths to bridge clients."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except OSError:
            raise ValueError('图片上传失败') from None

    return wrapped


def _image_type(header):
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if header.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if header.startswith((b'GIF87a', b'GIF89a')):
        return 'gif'
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'webp'
    return None


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('图片已失效')
    return value


def _name(value):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 255
        or any(c in value for c in ('/', '\\', ':', '\x00'))
        or value in ('.', '..')
    ):
        raise ValueError('图片名称无效')
    return value.strip()


class MediaManager:
    """All identifiers are generated locally; no API accepts filesystem paths or URLs.

    root is the OlivOS working directory. Uploads belong to a bot until consumed;
    emoji files are never consumed when a temporary copy is selected.
    """

    def __init__(self, root=None):
        root = Path(root if root is not None else os.getcwd()).resolve()
        self.temp = root / 'plugin' / 'data' / 'image' / 'temp' / 'QQOfficialConsole'
        self.emoji = root / 'plugin' / 'data' / 'image' / 'QQOfficialConsole' / 'emoji'
        self.sent = root / 'plugin' / 'data' / 'QQOfficialConsole' / 'sent-images'
        self.temp.mkdir(parents=True, exist_ok=True)
        self.emoji.mkdir(parents=True, exist_ok=True)
        self.sent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._uploads = {}
        self._claimed = set()

    @staticmethod
    def _bot(bot_hash):
        if not isinstance(bot_hash, str) or not bot_hash:
            raise ValueError('机器人无效')
        return bot_hash

    def _scope_dir(self, scope, bot_hash):
        self._bot(bot_hash)
        if scope == 'global':
            return self.emoji / 'global'
        if scope == 'bot':
            return self.emoji / 'bot' / hashlib.sha256(bot_hash.encode('utf-8')).hexdigest()
        raise ValueError('表情范围无效')

    def _upload(self, upload_id, bot_hash, complete=False):
        _id(upload_id)
        self._bot(bot_hash)
        item = self._uploads.get(upload_id)
        if item is None or item['bot'] != bot_hash or (complete and not item['complete']):
            raise ValueError('图片已失效')
        return item

    def _reserve_upload(self, bot_hash, receiving):
        self._bot(bot_hash)
        cutoff = time.monotonic() - UPLOAD_IDLE_SECONDS
        for upload_id, item in list(self._uploads.items()):
            if upload_id not in self._claimed and item['touched'] < cutoff:
                self._discard(upload_id)
        if sum(item['bot'] == bot_hash for item in self._uploads.values()) >= MAX_PENDING_PER_BOT:
            raise ValueError('待发送图片数量已达上限')
        if receiving and sum(not item['complete'] for item in self._uploads.values()) >= MAX_ACTIVE_UPLOADS:
            raise ValueError('上传数量已达上限')

    @_safe_io
    def begin(self, name, size, mime='', bot_hash=''):
        self._bot(bot_hash)
        name = _name(name)
        ext = _EXTENSIONS.get(name.rsplit('.', 1)[-1].lower()) if '.' in name else None
        if ext is None:
            raise ValueError('图片格式不支持')
        if type(size) is not int or size <= 0:
            raise ValueError('图片上传失败')
        if size > MAX_SIZE:
            raise ValueError('图片过大')
        if mime and mime not in (_MIMES[ext], 'application/octet-stream'):
            raise ValueError('图片格式不支持')
        with self._lock:
            self._reserve_upload(bot_hash, receiving=True)
            upload_id = uuid.uuid4().hex
            path = self.temp / (upload_id + '.' + ext)
            with path.open('xb'):
                pass
            self._uploads[upload_id] = {
                'path': path,
                'bot': bot_hash,
                'size': size,
                'received': 0,
                'index': 0,
                'ext': ext,
                'complete': False,
                'touched': time.monotonic(),
            }
            return {'upload_id': upload_id}

    @_safe_io
    def chunk(self, upload_id, index, data_b64, bot_hash=''):
        with self._lock:
            item = self._upload(upload_id, bot_hash)
            if upload_id in self._claimed or item['complete'] or type(index) is not int or index != item['index']:
                raise ValueError('图片上传失败')
            if not isinstance(data_b64, str) or len(data_b64) > ((CHUNK_SIZE + 2) // 3) * 4:
                raise ValueError('图片上传失败')
            try:
                data = base64.b64decode(data_b64, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError('图片上传失败') from None
            remaining = item['size'] - item['received']
            if not data or len(data) > CHUNK_SIZE or len(data) > remaining:
                self._discard(upload_id)
                raise ValueError('图片过大' if len(data) > remaining else '图片上传失败')
            try:
                with item['path'].open('ab') as f:
                    f.write(data)
                item['received'] += len(data)
                item['index'] += 1
                item['touched'] = time.monotonic()
                if item['received'] == item['size']:
                    with item['path'].open('rb') as f:
                        detected = _image_type(f.read(12))
                    if detected != item['ext'] or item['path'].stat().st_size != item['size']:
                        self._discard(upload_id)
                        raise ValueError('图片格式不支持')
                    item['complete'] = True
            except OSError:
                self._discard(upload_id)
                raise
            return {'upload_id': upload_id, 'complete': item['complete'], 'received': item['received']}

    def _discard(self, upload_id):
        item = self._uploads.pop(upload_id, None)
        if item is not None:
            item['path'].unlink(missing_ok=True)

    @_safe_io
    def abort(self, upload_id, bot_hash=''):
        with self._lock:
            self._upload(upload_id, bot_hash)
            if upload_id in self._claimed:
                raise ValueError('图片正在发送')
            self._discard(upload_id)

    delete = abort

    @_safe_io
    def resolve(self, upload_id, bot_hash=''):
        with self._lock:
            item = self._upload(upload_id, bot_hash, complete=True)
            if upload_id in self._claimed or not item['path'].is_file():
                raise ValueError('图片已失效')
            return str(item['path'].resolve())

    @contextmanager
    def sending(self, upload_ids, bot_hash=''):
        if (
            not isinstance(upload_ids, (list, tuple))
            or any(not isinstance(value, str) for value in upload_ids)
            or len(set(upload_ids)) != len(upload_ids)
        ):
            raise ValueError('图片已失效')
        with self._lock:
            paths = [self.resolve(upload_id, bot_hash) for upload_id in upload_ids]
            self._claimed.update(upload_ids)
        try:
            yield paths
        finally:
            failed = False
            with self._lock:
                for upload_id in upload_ids:
                    try:
                        self._discard(upload_id)
                    except OSError:
                        failed = True
                    finally:
                        self._claimed.discard(upload_id)
            if failed:
                raise ValueError('图片清理失败') from None

    @_safe_io
    def cleanup(self, max_age=3600):
        cutoff = time.time() - max_age
        with self._lock:
            active = {item['path'] for item in self._uploads.values()}
            for path in self.temp.iterdir():
                if path not in active and not path.is_symlink() and path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)

    @_safe_io
    def persist_sent(self, paths, images):
        """复制已认领的临时图片，使用随机标识，绝不复用临时文件。"""
        saved = []
        metadata = []
        with self._lock:
            try:
                for source, image in zip(paths, images, strict=True):
                    source = Path(source)
                    with source.open('rb') as stream:
                        ext = _image_type(stream.read(12))
                    if ext not in _MIMES:
                        raise ValueError('图片格式不支持')
                    ident = uuid.uuid4().hex
                    destination = self.sent / (ident + '.' + ext)
                    saved.append(destination)
                    with source.open('rb') as src, destination.open('xb') as dst:
                        shutil.copyfileobj(src, dst)
                    metadata.append({
                        'image_id': ident,
                        'marker': image.get('marker'),
                        'mime': _MIMES[ext],
                        'size': destination.stat().st_size,
                    })
                return metadata
            except Exception:
                for destination in saved:
                    destination.unlink(missing_ok=True)
                raise

    @_safe_io
    def read_sent_chunk(self, image, index, retention_days):
        ident = _id(image.get('image_id'))
        mime = image.get('mime')
        ext = next((key for key, value in _MIMES.items() if value == mime), None)
        if ext is None or type(index) is not int or index < 0:
            raise ValueError('图片已失效')
        path = self.sent / (ident + '.' + ext)
        with self._lock:
            if path.is_symlink() or not path.is_file():
                raise ValueError('图片已失效')
            stat = path.stat()
            if stat.st_mtime <= time.time() - retention_days * 86400:
                path.unlink(missing_ok=True)
                raise ValueError('图片已失效')
            total = (stat.st_size + CHUNK_SIZE - 1) // CHUNK_SIZE
            if index >= total or stat.st_size != image.get('size'):
                raise ValueError('图片已失效')
            with path.open('rb') as stream:
                stream.seek(index * CHUNK_SIZE)
                data = stream.read(CHUNK_SIZE)
        return {'image_id': ident, 'index': index, 'total_chunks': total, 'size': stat.st_size,
                'mime': mime, 'data_b64': base64.b64encode(data).decode('ascii')}

    @_safe_io
    def cleanup_sent(self, retention_days):
        cutoff = time.time() - retention_days * 86400
        with self._lock:
            for path in self.sent.iterdir():
                if (re.fullmatch(r'[0-9a-f]{32}\.(?:png|jpg|gif|webp)', path.name)
                        and not path.is_symlink() and path.is_file() and path.stat().st_mtime <= cutoff):
                    path.unlink(missing_ok=True)

    def _metadata(self, emoji_id, scope, bot_hash):
        _id(emoji_id)
        directory = self._scope_dir(scope, bot_hash)
        meta_path = directory / (emoji_id + '.json')
        try:
            if meta_path.is_symlink():
                raise ValueError('表情已失效')
            with meta_path.open('r', encoding='utf-8') as f:
                meta = json.load(f)
            ext = meta['ext']
            if ext not in _MIMES or meta['id'] != emoji_id or not isinstance(meta['name'], str):
                raise ValueError('表情已失效')
            path = directory / (emoji_id + '.' + ext)
            if path.is_symlink() or not path.is_file():
                raise ValueError('表情已失效')
            return directory, meta, path
        except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
            raise ValueError('表情已失效') from None

    @staticmethod
    def _write_meta(directory, meta):
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / (uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False)
            os.replace(temporary, directory / (meta['id'] + '.json'))
        finally:
            temporary.unlink(missing_ok=True)

    @_safe_io
    def save(self, upload_id, name, scope, bot_hash):
        name = _name(name)
        with self._lock:
            item = self._upload(upload_id, bot_hash, complete=True)
            if upload_id in self._claimed:
                raise ValueError('图片正在发送')
            directory = self._scope_dir(scope, bot_hash)
            directory.mkdir(parents=True, exist_ok=True)
            emoji_id = uuid.uuid4().hex
            path = directory / (emoji_id + '.' + item['ext'])
            meta = {'id': emoji_id, 'name': name, 'ext': item['ext']}
            try:
                with item['path'].open('rb') as source, path.open('xb') as destination:
                    shutil.copyfileobj(source, destination)
                self._write_meta(directory, meta)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return {'id': emoji_id, 'name': name, 'scope': scope}

    @_safe_io
    def list_emojis(self, scope, bot_hash):
        with self._lock:
            directory = self._scope_dir(scope, bot_hash)
            if not directory.exists():
                return []
            result = []
            for path in directory.glob('*.json'):
                if not _ID.fullmatch(path.stem):
                    continue
                try:
                    _, meta, _ = self._metadata(path.stem, scope, bot_hash)
                except ValueError:
                    continue
                result.append({'id': meta['id'], 'name': meta['name'], 'scope': scope})
            return sorted(result, key=lambda item: (item['name'].casefold(), item['id']))

    @_safe_io
    def thumbnail(self, emoji_id, scope, bot_hash):
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError:
            raise ValueError('缩略图不可用') from None
        with self._lock:
            _, _, path = self._metadata(emoji_id, scope, bot_hash)
            try:
                with Image.open(path) as image:
                    image.seek(0)
                    image.thumbnail((96, 96))
                    image = image.convert('RGB')
                    output = io.BytesIO()
                    image.save(output, format='JPEG', quality=70, optimize=True)
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
                raise ValueError('缩略图不可用') from None
            return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')

    @_safe_io
    def rename_emoji(self, emoji_id, name, scope, bot_hash):
        name = _name(name)
        with self._lock:
            directory, meta, _ = self._metadata(emoji_id, scope, bot_hash)
            meta['name'] = name
            self._write_meta(directory, meta)
            return {'id': emoji_id, 'name': name, 'scope': scope}

    @_safe_io
    def delete_emoji(self, emoji_id, scope, bot_hash):
        with self._lock:
            directory, _, path = self._metadata(emoji_id, scope, bot_hash)
            (directory / (emoji_id + '.json')).unlink()
            path.unlink(missing_ok=True)

    @_safe_io
    def use_emoji(self, emoji_id, scope, bot_hash):
        with self._lock:
            self._reserve_upload(bot_hash, receiving=False)
            _, meta, source = self._metadata(emoji_id, scope, bot_hash)
            size = source.stat().st_size
            if not 0 < size <= MAX_SIZE:
                raise ValueError('图片已失效')
            upload_id = uuid.uuid4().hex
            destination = self.temp / (upload_id + '.' + meta['ext'])
            try:
                with source.open('rb') as src, destination.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                with destination.open('rb') as f:
                    if _image_type(f.read(12)) != meta['ext']:
                        raise ValueError('图片格式不支持')
                self._uploads[upload_id] = {
                    'path': destination,
                    'bot': self._bot(bot_hash),
                    'size': size,
                    'received': size,
                    'index': 0,
                    'ext': meta['ext'],
                    'complete': True,
                    'touched': time.monotonic(),
                }
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            return {'upload_id': upload_id}

    @_safe_io
    def read_emoji_chunk(self, emoji_id, scope, bot_hash, index=0):
        if type(index) is not int or index < 0:
            raise ValueError('表情已失效')
        with self._lock:
            _, meta, path = self._metadata(emoji_id, scope, bot_hash)
            size = path.stat().st_size
            if not 0 < size <= MAX_SIZE or index * CHUNK_SIZE >= size:
                raise ValueError('表情已失效')
            with path.open('rb') as f:
                f.seek(index * CHUNK_SIZE)
                data = f.read(CHUNK_SIZE)
            return {
                'id': emoji_id,
                'index': index,
                'data_b64': base64.b64encode(data).decode('ascii'),
                'mime': _MIMES[meta['ext']],
                'size': size,
                'complete': (index * CHUNK_SIZE + len(data) == size),
            }
