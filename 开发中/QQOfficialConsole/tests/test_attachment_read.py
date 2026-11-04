"""入站图片附件：服务端代下载 + 分片读取（沙箱 CSP 不允许前端直连外链）。"""
import base64
import importlib
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import OlivOS
import pytest
from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as sdk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PNG = b'\x89PNG\r\n\x1a\n' + b'x' * 64


@pytest.fixture
def console(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in list(sys.modules):
        if name == 'QQOfficialConsole' or name.startswith('QQOfficialConsole.'):
            monkeypatch.delitem(sys.modules, name)
    importlib.import_module('QQOfficialConsole')
    from QQOfficialConsole import media, passive, roster, store, webui
    monkeypatch.setattr(sdk, 'getTokenNow', lambda bot_info: 'local-token')
    bot = OlivOS.API.bot_info_T(id=int(uuid.uuid4().int % 10**12), platform_sdk='qqGuildv2_link',
                                platform_platform='qqGuild', platform_model='public')
    proc = SimpleNamespace(Proc_data={'bot_info_dict': {bot.hash: bot}}, log=lambda *args, **kwargs: None)
    database = store.Store(tmp_path / 'db')
    pool = passive.PassivePool(database)
    members = roster.Roster(database)
    images = media.MediaManager(tmp_path)
    bridge = webui.Bridge(database, pool, members, images, proc)
    state = SimpleNamespace(bot=bot, store=database, bridge=bridge, downloads=[],
                            response=(200, PNG, 'image/png'))

    def request(method, url, **kwargs):
        parts = urlsplit(url)
        if parts.path.endswith('/bot_state'):
            return SimpleNamespace(status_code=200,
                                   text=json.dumps({'member_role': 'member'}), headers={},
                                   content=b'')
        state.downloads.append((method, url, kwargs.get('headers')))
        status, content, ctype = state.response
        return SimpleNamespace(status_code=status, content=content,
                               headers={'Content-Type': ctype}, text='',
                               iter_content=lambda chunk_size: (content[i:i+chunk_size]
                                                                 for i in range(0, len(content), chunk_size)),
                               close=lambda: None)

    monkeypatch.setattr(sdk.req, 'request', request)
    yield state
    bridge.close()
    database.close()


def store_incoming(c, attachments, msg_id='m1'):
    return c.store.add_message(c.bot.hash, 'qq_group', 'g', {
        'direction': 'in', 'platform_message_id': msg_id, 'sender_id': 'u1', 'sender_name': '某人',
        'msg_kind': 'media', 'content_text': '', 'content_json': {'text': '', 'attachments': attachments},
        'created_at': 1700000000,
    })


def read(c, message_id, attachment=0, index=0):
    return c.bridge.handle('QQOfficialConsole_AttachmentRead', {
        'bot_hash': c.bot.hash, 'chat_type': 'qq_group', 'chat_id': 'g',
        'message_id': message_id, 'attachment': attachment, 'index': index,
    })


def test_incoming_attachment_served_with_auth_and_cached(console):
    c = console
    url = 'https://multimedia.nt.qq.com.cn/download?appid=1407&fileid=abc&rkey=xyz'
    local_id = store_incoming(c, [{'url': url, 'content_type': 'image/png', 'size': len(PNG)}])
    result = read(c, local_id)
    assert result['ok'] and result['mime'] == 'image/png' and result['complete']
    assert base64.b64decode(result['data_b64']) == PNG
    # 服务端代下载必须带 QQBot 鉴权头
    assert len(c.downloads) == 1
    method, fetched, headers = c.downloads[0]
    assert method == 'GET' and fetched == url
    assert headers['Authorization'] == 'QQBot local-token'
    # 第二次读取走缓存，不再触发下载
    again = read(c, local_id)
    assert again['ok'] and base64.b64decode(again['data_b64']) == PNG
    assert len(c.downloads) == 1


def test_chunked_read_large_attachment(console):
    c = console
    big = b'\x89PNG\r\n\x1a\n' + b'y' * (300 * 1024)
    c.response = (200, big, 'image/png')
    url = 'https://multimedia.nt.qq.com.cn/download?fileid=big'
    local_id = store_incoming(c, [{'url': url, 'content_type': 'image/png', 'size': len(big)}])
    first = read(c, local_id, index=0)
    assert first['ok'] and first['total_chunks'] == 2 and not first['complete']
    second = read(c, local_id, index=1)
    assert second['ok'] and second['complete']
    assert base64.b64decode(first['data_b64']) + base64.b64decode(second['data_b64']) == big


def test_expired_or_failed_download_reports_failure(console):
    c = console
    c.response = (403, b'', 'text/plain')
    url = 'https://multimedia.nt.qq.com.cn/download?fileid=gone&rkey=expired'
    local_id = store_incoming(c, [{'url': url, 'content_type': 'image/jpeg'}])
    result = read(c, local_id)
    assert not result['ok'] and result['keyword'] == '图片已过期或无法加载'


def test_non_image_content_rejected(console):
    c = console
    c.response = (200, b'not-an-image-at-all', 'text/html')
    url = 'https://multimedia.nt.qq.com.cn/download?fileid=evil'
    local_id = store_incoming(c, [{'url': url, 'content_type': 'image/png'}])
    result = read(c, local_id)
    assert not result['ok']


def test_invalid_reference_rejected(console):
    c = console
    local_id = store_incoming(c, [{'url': 'https://multimedia.nt.qq.com.cn/download?fileid=a',
                                   'content_type': 'image/png'}])
    assert not read(c, local_id, attachment=5)['ok']
    assert not read(c, 999999)['ok']
    # 出站消息不走该通道
    out_id = c.store.add_message(c.bot.hash, 'qq_group', 'g', {
        'direction': 'out', 'platform_message_id': 'o1', 'msg_kind': 'text', 'content_text': 'hi',
        'content_json': {'text': 'hi', 'attachments': [{'url': 'https://x.invalid/a.png'}]},
        'created_at': 1700000000,
    }, unread=False)
    assert not read(c, out_id)['ok']


@pytest.mark.parametrize('url', [
    'https://127.0.0.1/private',
    'https://multimedia.nt.qq.com.cn.evil.example/download',
    'http://multimedia.nt.qq.com.cn/download',
    'https://evil.example@multimedia.nt.qq.com.cn/download',
    'https://multimedia.nt.qq.com.cn:444/download',
])
def test_attachment_untrusted_urls_never_receive_token(console, url):
    local_id = store_incoming(console, [{'url': url, 'content_type': 'image/png'}])
    assert not read(console, local_id)['ok']
    assert console.downloads == []


def test_voice_attachment_not_served_as_image(console):
    c = console
    url = 'https://multimedia.nt.qq.com.cn/download?fileid=voice'
    local_id = store_incoming(c, [{'url': url, 'content_type': 'voice'}])
    result = read(c, local_id)
    assert not result['ok']
