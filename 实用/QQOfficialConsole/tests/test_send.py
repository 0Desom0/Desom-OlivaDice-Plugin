"""发送行为回归：真实 OlivOS SDK，仅将 QQ HTTP 传输替换为进程内响应。"""
import base64
import json
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import OlivOS
import pytest
from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as sdk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from QQOfficialConsole import errors, media, passive, send, store


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bot = OlivOS.API.bot_info_T(id=int(uuid.uuid4().int % 10**12), platform_sdk='qqGuildv2_link',
                                platform_platform='qqGuild', platform_model='public')
    event = SimpleNamespace(bot_info=bot, data=SimpleNamespace(extend={}))
    database = store.Store(tmp_path / 'db')
    pool = passive.PassivePool(database)
    attachments = media.MediaManager(tmp_path)
    calls = []
    replies = []

    def request(method, url, **kwargs):
        data = kwargs.get('data')
        if isinstance(data, str):
            data = json.loads(data)
        calls.append((method, url, data))
        if url.endswith('/prepare'):
            status, body = 200, {'upload_id': 'upload', 'presigned_url': 'https://local.invalid/upload'}
        elif url == 'https://local.invalid/upload':
            status, body = 200, {}
        elif url.endswith('/complete'):
            status, body = 200, {'image_id': 'temporary', 'url': 'https://local.invalid/image'}
        elif method == 'DELETE':
            status, body = 200, {}
        else:
            status, body = replies.pop(0) if replies else (200, {'id': 'sent', 'ext_info': {'ref_idx': 'REFIDX_sent'}})
        return SimpleNamespace(status_code=status, text=json.dumps(body), headers={'ETag': '0123456789abcdef'})

    monkeypatch.setattr(sdk, 'getTokenNow', lambda bot_info: 'local-token')
    monkeypatch.setattr(sdk.req, 'request', request)
    sender = send.Sender(event, pool, attachments)
    state = SimpleNamespace(bot=bot, event=event, pool=pool, media=attachments, sender=sender,
                            calls=calls, replies=replies)
    yield state
    database.close()


def payload(h, **kw):
    return {'bot_hash': h.bot.hash, 'chat_type': 'qq_group', 'chat_id': 'group',
            'kind': 'text', 'text': 'hello', **kw}


def upload(h):
    image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/aXcAAAAASUVORK5CYII=')
    ident = h.media.begin('pixel.png', len(image), 'image/png', h.bot.hash)['upload_id']
    h.media.chunk(ident, 0, base64.b64encode(image).decode(), h.bot.hash)
    return ident, Path(h.media.resolve(ident, h.bot.hash))


def sent_requests(h):
    return [(url, body) for method, url, body in h.calls
            if method == 'POST' and (url.endswith('/messages') or url.endswith('/stream_messages'))]


def card(**content):
    return {'type': 'tuwen', 'content': {
        'title': '标题', 'description': '描述', 'url': 'https://example.com/',
        'pic_url': 'https://example.com/image.png', **content}}


def test_card_group_passive_retry_quote_keyboard(harness):
    h = harness
    h.pool.add(h.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    h.event.data.group_id = 'group'
    h.event.data.extend = {'qq_message_id': 'original', 'qq_msg_idx': 'REFIDX_original'}
    keyboard = {'content': {'rows': [{'buttons': [{'action': {'permission': {'type': 2}}}]}]}}
    h.replies.extend([(400, {'code': 40034024, 'message': 'expired'}), (200, {'id': 'sent'})])
    result = h.sender.send(payload(h, kind='card', card=card(), quote_id='original', keyboard=keyboard))
    assert result['ok'] and result['channel'] == 'active'
    requests = sent_requests(h)
    assert len(requests) == 2
    for url, body in requests:
        assert url.endswith('/groups/group/messages')
        assert body['msg_type'] == 8 and body['card'] == card()
        assert body['message_reference'] == {'message_id': 'REFIDX_original'}
        assert body['keyboard'] == keyboard
    assert requests[0][1]['msg_id'] == 'token' and requests[0][1]['msg_seq'] == 1
    assert 'msg_id' not in requests[1][1]


def test_card_private_ordinary_post(harness):
    h = harness
    h.pool.add(h.bot.hash, 'qq_private', 'user', 'event_id', 'event')
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user', kind='card', card=card()))
    assert result['ok'] and result['channel'] == 'passive'
    url, body = sent_requests(h)[0]
    assert url.endswith('/users/user/messages')
    assert body['msg_type'] == 8 and body['card'] == card() and body['event_id'] == 'event'


def test_card_private_active_default_type_quote_keyboard(harness):
    h = harness
    keyboard = {'id': 'template'}
    value = card()
    del value['type']
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user', kind='card',
                                   card=value, quote_id='REFIDX_original', keyboard=keyboard))
    assert result['ok'] and result['channel'] == 'active'
    url, body = sent_requests(h)[0]
    assert url.endswith('/users/user/messages')
    assert body['msg_type'] == 8 and body['card'] == card()
    assert body['message_reference'] == {'message_id': 'REFIDX_original'}
    assert body['keyboard'] == keyboard
    assert 'type' not in value


@pytest.mark.parametrize('content', [
    {'title': 'x', 'description': 'y'},
    {'title': 'x' * 50, 'description': 'y' * 200,
     'url': 'https://a/' + 'x' * 1014, 'pic_url': 'https://b/' + 'x' * 1014},
])
def test_card_sdk_boundaries_accepted(harness, content):
    result = harness.sender.send(payload(harness, kind='card', card=card(**content)))
    assert result['ok']
    assert sent_requests(harness)[0][1]['card'] == card(**content)


@pytest.mark.parametrize('content', [
    {'title': ''}, {'title': 'x' * 51}, {'title': None},
    {'description': ''}, {'description': 'x' * 201}, {'description': 1},
    {'url': ''}, {'url': 'http://example.com'}, {'url': 'https://'},
    {'url': 'https://a/' + 'x' * 1015}, {'url': None},
    {'pic_url': ''}, {'pic_url': 'http://example.com/image'}, {'pic_url': 'https://'},
    {'pic_url': 'https://a/' + 'x' * 1015}, {'pic_url': None},
])
def test_card_sdk_invalid_content_has_no_http(harness, content):
    result = harness.sender.send(payload(harness, kind='card', card=card(**content)))
    assert not result['ok'] and result['keyword'] == '图文卡片参数错误'
    assert not harness.calls


@pytest.mark.parametrize('invalid', [None, {}, {'type': 'other', 'content': {}},
                                    {'type': 'tuwen', 'content': None}])
def test_card_invalid_shape_has_no_http(harness, invalid):
    result = harness.sender.send(payload(harness, kind='card', card=invalid))
    assert not result['ok'] and result['keyword'] == '图文卡片参数错误'
    assert not harness.calls


def test_card_invalid_keyboard_quote_and_uploaded_image(harness):
    h = harness
    result = h.sender.send(payload(h, kind='card', card=card(), keyboard={'content': {'rows': 'bad'}}))
    assert result['keyword'] == '键盘参数错误'
    result = h.sender.send(payload(h, kind='card', card=card(), quote_id='unmapped'))
    assert result['keyword'] == '引用ID无效'
    ident, path = upload(h)
    result = h.sender.send(payload(h, kind='card', card=card(), images=[{'upload_id': ident}]))
    assert result['keyword'] == '图文卡片不支持上传图片' and not path.exists()
    assert not h.calls


def test_card_http_failure_does_not_retry_unrelated_error(harness):
    h = harness
    h.pool.add(h.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    h.replies.append((400, {'code': 40034006, 'message': 'blocked'}))
    result = h.sender.send(payload(h, kind='card', card=card()))
    assert not result['ok'] and result['keyword'] == '内容违规'
    assert len(sent_requests(h)) == 1
    assert len(h.pool.candidates(h.bot.hash, 'qq_group', 'group')) == 1


def test_passive_pool_retries_invalid_credentials_then_active(harness):
    h = harness
    now = int(time.time())
    h.pool.add(h.bot.hash, 'qq_group', 'group', 'msg_id', 'first', created_at=now - 2)
    h.pool.add(h.bot.hash, 'qq_group', 'group', 'event_id', 'second', created_at=now - 1)
    h.replies.extend([(400, {'code': 40034024, 'message': 'expired'}),
                      (400, {'code': 40034025, 'message': 'expired'}),
                      (200, {'id': 'sent'})])
    result = h.sender.send(payload(h))
    assert result['ok'] and result['channel'] == 'active' and result['message_id'] == 'sent'
    bodies = [body for _, body in sent_requests(h)]
    assert bodies[0]['msg_id'] == 'first' and bodies[0]['msg_seq'] == 1
    assert bodies[1]['event_id'] == 'second'
    assert 'msg_id' not in bodies[2] and 'event_id' not in bodies[2]
    assert h.pool.candidates(h.bot.hash, 'qq_group', 'group') == []


def test_passive_unrelated_error_does_not_retry(harness):
    h = harness
    h.pool.add(h.bot.hash, 'qq_group', 'group', 'msg_id', 'token')
    h.replies.append((400, {'code': 40034006, 'message': 'blocked'}))
    result = h.sender.send(payload(h))
    assert not result['ok'] and result['keyword'] == '内容违规'
    assert len(sent_requests(h)) == 1
    assert len(h.pool.candidates(h.bot.hash, 'qq_group', 'group')) == 1


def test_force_active_bypasses_available_token(harness):
    h = harness
    h.pool.add(h.bot.hash, 'qq_group', 'group', 'msg_id', 'unused')
    result = h.sender.send(payload(h, force_active=True))
    assert result['ok'] and result['channel'] == 'active'
    assert 'msg_id' not in sent_requests(h)[0][1]
    assert h.pool.candidates(h.bot.hash, 'qq_group', 'group')[0]['used_count'] == 0


@pytest.mark.parametrize('status,code,fallback', [(400, 22006, True), (400, 40007, False),
                                                    (429, 50002, False), (500, 50001, False)])
def test_private_stream_fallback_policy(harness, status, code, fallback):
    h = harness
    h.replies.append((status, {'code': code, 'message': 'stream failure'}))
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user', force_active=True,
                                   is_wakeup=True))
    requests = sent_requests(h)
    assert requests[0][0].endswith('/users/user/stream_messages')
    assert requests[0][1]['content_raw'] == 'hello'
    assert requests[0][1]['content_type'] == 'text' and requests[0][1]['is_wakeup'] is True
    assert len(requests) == (2 if fallback else 1)
    assert result['ok'] is fallback
    if fallback:
        assert requests[1][0].endswith('/users/user/messages')
        assert requests[1][1]['content'] == 'hello' and result['channel'] == 'active'
    else:
        assert result['error_code'] == code and result['channel'] == 'stream'


def test_private_stream_success(harness):
    h = harness
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user', kind='markdown',
                                   markdown='**hello**'))
    assert result['ok'] and result['channel'] == 'stream'
    assert result['ref_idx'] == 'REFIDX_sent'
    assert sent_requests(h)[0][1]['content_type'] == 'markdown'

def test_private_stream_transport_error_does_not_fallback(harness, monkeypatch):
    h = harness
    attempts = []

    def offline(method, url, **kwargs):
        attempts.append(url)
        raise OSError('offline')

    monkeypatch.setattr(sdk.req, 'request', offline)
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user'))
    assert not result['ok'] and result['channel'] == 'stream'
    assert len(attempts) == 1 and attempts[0].endswith('/users/user/stream_messages')


@pytest.mark.parametrize('status,deleted', [(200, True), (400, True), (500, False)])
def test_image_remote_and_local_cleanup(harness, status, deleted):
    h = harness
    ident, path = upload(h)
    h.replies.append((status, {'id': 'sent'} if status == 200 else {'code': 22006, 'message': 'no'}))
    result = h.sender.send(payload(h, kind='markdown', markdown='picture {{img_a}}',
                                   images=[{'upload_id': ident, 'marker': 'img_a'}]))
    assert result['ok'] is (status == 200)
    assert not path.exists()
    image = h.sender.sent_images[0]
    assert image['marker'] == 'img_a' and image['mime'] == 'image/png'
    assert base64.b64decode(h.media.read_sent_chunk(image, 0, 30)['data_b64']).startswith(b'\x89PNG')
    assert any(url.endswith('/prepare') for _, url, _ in h.calls)
    assert any(url == 'https://local.invalid/upload' for _, url, _ in h.calls)
    assert any(url.endswith('/complete') for _, url, _ in h.calls)
    assert any(method == 'DELETE' and url.endswith('/temporary/delete') for method, url, _ in h.calls) is deleted
    body = sent_requests(h)[0][1]
    assert 'https://local.invalid/image' in body['markdown']['content']


def test_invalid_image_request_cleans_temp_without_network(harness):
    h = harness
    ident, path = upload(h)
    result = h.sender.send(payload(h, kind='markdown', markdown='no marker',
                                   images=[{'upload_id': ident, 'marker': 'img_a'}]))
    assert result['keyword'] == '图片标记无效' and not path.exists()
    assert not h.calls


def test_at_conversion_and_everyone_confirmation(harness):
    h = harness
    result = h.sender.send(payload(h, at=[{'id': 'alice_1'}]))
    assert result['ok']
    body = sent_requests(h)[0][1]
    assert body['msg_type'] == 2 and body['markdown']['content'] == 'hello ' + sdk.markdown_tag.at_user('alice_1')
    result = h.sender.send(payload(h, at=[{'id': 'all'}]))
    assert result['keyword'] == '无权限或未确认@全体'
    result = h.sender.send(payload(h, at=[{'id': 'all'}], at_all_confirmed=True))
    assert result['ok'] and '<qqbot-at-everyone />' in sent_requests(h)[-1][1]['markdown']['content']
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user', text='<qqbot-at-everyone />',
                                   at_all_confirmed=True))
    assert result['keyword'] == '无权限或未确认@全体'


def test_long_text_is_not_blocked_locally(harness):
    # QQ 官方机器人没有 3000 字上限：带 @ 标签展开后的长正文也照常发出。
    h = harness
    assert h.sender.send(payload(h, text='界' * 3000))['ok']
    assert h.sender.send(payload(h, text='界' * 3001))['ok']
    tag = sdk.markdown_tag.at_user('alice')
    assert h.sender.send(payload(h, text='x' * (2999 - len(tag)), at=[{'id': 'alice'}]))['ok']
    assert h.sender.send(payload(h, text='x' * (3000 - len(tag)), at=[{'id': 'alice'}]))['ok']
    assert len(sent_requests(h)) == 4


def test_quote_resolution_and_rejection(harness):
    h = harness
    h.event.data.group_id = 'group'
    h.event.data.extend = {'qq_message_id': 'original', 'qq_msg_idx': 'REFIDX_original'}
    result = h.sender.send(payload(h, quote_id='original'))
    assert result['ok']
    assert sent_requests(h)[0][1]['message_reference'] == {'message_id': 'REFIDX_original'}
    result = h.sender.send(payload(h, quote_id='unmapped'))
    assert result['keyword'] == '引用ID无效'
    result = h.sender.send(payload(h, quote_id='REFIDX_original', at=[{'id': 'alice'}]))
    assert result['keyword'] == '请将引用转换为Markdown引用块'
    assert len(sent_requests(h)) == 1


def test_errors_sanitize_and_pending_review():
    result = errors.result({'active': True, 'data': {'pending_review': True,
        'response': {'data': {'ext_info': {'ref_idx': 'REFIDX_1'}}}}}, 'active')
    assert result['keyword'] == '审核中' and result['ref_idx'] == 'REFIDX_1'
    assert result['pending_review'] and result['channel'] == 'active'
    result = errors.result({'active': False, 'data': {'error_code': '40034006', 'error': 'secret'}})
    assert result['keyword'] == '内容违规' and result['error_code'] == 40034006
    assert 'message' not in result


def test_long_markdown_stream_reuses_one_passive_sequence(harness):
    h = harness
    h.pool.add(h.bot.hash, 'qq_private', 'user', 'msg_id', 'incoming')
    h.replies.extend([(200, {'id': 'stream-1', 'ext_info': {'ref_idx': 'REFIDX_first'}}),
                      (200, {}), (200, {'ext_info': {'ref_idx': 'REFIDX_final'}})])
    content = '文' * 1201
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user',
                                   kind='markdown', markdown=content))
    bodies = [body for _, body in sent_requests(h)]
    assert result['ok'] and result['channel'] == 'stream'
    assert result['message_id'] == 'stream-1' and result['ref_idx'] == 'REFIDX_final'
    assert [body['index'] for body in bodies] == [0, 1, 2]
    assert [body['input_state'] for body in bodies] == [1, 1, 10]
    assert all(body['input_mode'] == 'append' and body['msg_id'] == 'incoming'
               and body['msg_seq'] == 1 for body in bodies)
    assert 'stream_msg_id' not in bodies[0]
    assert all(body['stream_msg_id'] == 'stream-1' for body in bodies[1:])
    assert ''.join(body['content_raw'] for body in bodies) == content
    assert h.pool.candidates(h.bot.hash, 'qq_private', 'user')[0]['used_count'] == 1


@pytest.mark.parametrize('response', [(400, {'code': 22006, 'message': 'rejected'}),
                                      (500, {'code': 50001, 'message': 'unknown'})])
def test_partial_stream_failure_never_falls_back(harness, response):
    h = harness
    h.replies.extend([(200, {'id': 'stream-1', 'ext_info': {'ref_idx': 'REFIDX_first'}}), response])
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user',
                                   kind='markdown', markdown='x' * 1001))
    assert not result['ok'] and result['channel'] == 'stream' and result['stream_started']
    assert result['message_id'] == 'stream-1' and result['ref_idx'] == 'REFIDX_first'
    assert len(sent_requests(h)) == 2
    assert all(url.endswith('/stream_messages') for url, _ in sent_requests(h))


def test_stream_missing_first_id_does_not_fallback(harness):
    h = harness
    h.replies.append((200, {}))
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user',
                                   kind='markdown', markdown='x' * 501))
    assert not result['ok'] and result['stream_started']
    assert result['channel'] == 'stream' and result['message_id'] is None
    assert len(sent_requests(h)) == 1


def test_partial_stream_transport_failure_keeps_first_id(harness, monkeypatch):
    h = harness
    request = sdk.req.request
    attempts = []

    def offline_after_first(method, url, **kwargs):
        attempts.append(url)
        if len(attempts) == 2:
            raise OSError('offline')
        return request(method, url, **kwargs)

    monkeypatch.setattr(sdk.req, 'request', offline_after_first)
    result = h.sender.send(payload(h, chat_type='qq_private', chat_id='user',
                                   kind='markdown', markdown='x' * 501))
    assert not result['ok'] and result['stream_started'] and result['channel'] == 'stream'
    assert result['message_id'] == 'sent' and result['ref_idx'] == 'REFIDX_sent'
    assert len(attempts) == 2 and all(url.endswith('/stream_messages') for url in attempts)
