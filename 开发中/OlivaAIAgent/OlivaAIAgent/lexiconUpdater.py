# -*- encoding: utf-8 -*-
'''选装政治敏感词库的安全下载、校验与更新状态管理。'''

import hashlib
import json
import os
from datetime import datetime

import requests

from OlivaAIAgent import conf


SOURCE_NAME = 'konsheng/Sensitive-lexicon 政治类型词库'
SOURCE_URL = (
    'https://raw.githubusercontent.com/konsheng/Sensitive-lexicon/'
    'master/Vocabulary/%E6%94%BF%E6%B2%BB%E7%B1%BB%E5%9E%8B.txt'
)
SOURCE_LICENSE = 'MIT'
TARGET_FILE = 'konsheng_politics.txt'
META_FILE = 'konsheng_politics.update.json'
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
MIN_WORDS = 20


def lexiconDir():
    return os.path.join(conf.dataPath, 'sensitive_words')


def lexiconPath():
    return os.path.join(lexiconDir(), TARGET_FILE)


def metadataPath():
    return os.path.join(lexiconDir(), META_FILE)


def _nowText():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _loadMetadata():
    try:
        with open(metadataPath(), 'r', encoding='utf-8-sig') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _wordCount(text):
    words = {
        line.strip()
        for line in str(text or '').replace('\r\n', '\n').split('\n')
        if line.strip() and not line.strip().startswith(('#', '//', ';'))
    }
    return len(words)


def _fileInfo(path):
    try:
        with open(path, 'rb') as handle:
            content = handle.read(MAX_DOWNLOAD_BYTES + 1)
        if len(content) > MAX_DOWNLOAD_BYTES:
            return {'sha256': '', 'words': 0}
        text = content.decode('utf-8-sig')
        return {
            'sha256': hashlib.sha256(content).hexdigest(),
            'words': _wordCount(text),
        }
    except Exception:
        return {'sha256': '', 'words': 0}


def getStatus():
    path = lexiconPath()
    metadata = _loadMetadata()
    info = _fileInfo(path) if os.path.isfile(path) else {'sha256': '', 'words': 0}
    return {
        'installed': bool(info['sha256'] and info['words'] >= MIN_WORDS),
        'path': os.path.abspath(path),
        'words': info['words'],
        'sha256': info['sha256'],
        'checked_at': str(metadata.get('checked_at') or ''),
        'updated_at': str(metadata.get('updated_at') or ''),
        'source': SOURCE_NAME,
        'source_url': SOURCE_URL,
        'license': SOURCE_LICENSE,
    }


def _requestHeaders(metadata, installed):
    headers = {'User-Agent': 'OlivaAIAgent-sensitive-lexicon-updater'}
    if installed and metadata.get('source_url') == SOURCE_URL:
        if metadata.get('etag'):
            headers['If-None-Match'] = str(metadata['etag'])
        if metadata.get('last_modified'):
            headers['If-Modified-Since'] = str(metadata['last_modified'])
    return headers


def _download(response):
    try:
        declared_size = int(response.headers.get('Content-Length', 0) or 0)
    except (TypeError, ValueError):
        declared_size = 0
    if declared_size > MAX_DOWNLOAD_BYTES:
        raise ValueError('远端词库超过 2 MiB 安全上限')
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_DOWNLOAD_BYTES:
            raise ValueError('远端词库超过 2 MiB 安全上限')
        chunks.append(chunk)
    return b''.join(chunks)


def _validate(content):
    if not content:
        raise ValueError('远端词库为空')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError as e:
        raise ValueError('远端词库不是有效 UTF-8 文本') from e
    if '\x00' in text or '<html' in text[:500].lower():
        raise ValueError('远端返回内容不是有效词库')
    words = _wordCount(text)
    if words < MIN_WORDS:
        raise ValueError('远端词库有效词数过少，已拒绝覆盖本地文件')
    return text, words


def _atomicWriteText(path, text):
    conf.releaseDir(os.path.dirname(path))
    temporary = '%s.tmp.%d' % (path, os.getpid())
    try:
        with open(temporary, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except Exception:
                pass
        os.replace(temporary, path)
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except Exception:
            pass


def checkAndUpdate(timeout=30):
    '''条件下载词库；返回 updated/current 状态，失败时保留原文件。'''
    target_path = lexiconPath()
    installed = getStatus()['installed']
    metadata = _loadMetadata()
    response = requests.get(
        SOURCE_URL,
        headers=_requestHeaders(metadata, installed),
        timeout=max(1, float(timeout)),
        stream=True,
    )
    try:
        if response.status_code == 304 and installed:
            metadata['checked_at'] = _nowText()
            conf.atomicDump(metadata, metadataPath())
            status = getStatus()
            status.update({'result': 'current', 'updated': False})
            return status
        response.raise_for_status()
        content = _download(response)
        text, words = _validate(content)
        new_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        old_hash = _fileInfo(target_path)['sha256'] if installed else ''
        updated = new_hash != old_hash
        if updated:
            _atomicWriteText(target_path, text)
        now_text = _nowText()
        new_metadata = {
            'source': SOURCE_NAME,
            'source_url': SOURCE_URL,
            'license': SOURCE_LICENSE,
            'etag': str(response.headers.get('ETag') or ''),
            'last_modified': str(response.headers.get('Last-Modified') or ''),
            'sha256': new_hash,
            'words': words,
            'checked_at': now_text,
            'updated_at': now_text if updated else str(metadata.get('updated_at') or now_text),
        }
        conf.atomicDump(new_metadata, metadataPath())
        status = getStatus()
        status.update({'result': 'updated' if updated else 'current', 'updated': updated})
        return status
    finally:
        try:
            response.close()
        except Exception:
            pass


def activateConfig(config, path=None):
    '''在配置副本中启用刚下载的词库，同时保留用户已有词库路径。'''
    if not isinstance(config, dict):
        raise ValueError('配置根节点必须是对象')
    target = os.path.abspath(path or lexiconPath())
    security = config.setdefault('security', {})
    files = security.get('sensitive_word_files', []) or []
    if isinstance(files, str):
        files = [files]
    files = [str(item) for item in files if str(item).strip()]
    known = {os.path.normcase(os.path.abspath(item)) for item in files}
    if os.path.normcase(target) not in known:
        files.append(target)
    security['external_sensitive_words'] = True
    security['sensitive_word_files'] = files
    return config
