# -*- encoding: utf-8 -*-
"""B 站直播间 WebSocket：状态通知与 JSON 事件流。

参考 StarBot：按包头递归拆分压缩帧，优先协商 Brotli。
"""

import json
import socket
import struct
import threading
import time
import zlib

try:
    import brotli
except ImportError:
    brotli = None

try:
    import websocket
except ImportError:
    websocket = None

from . import bili_api, capabilities, store

# B 站弹幕服务器会拒绝没有浏览器 UA 的握手（实测 websocket-client 默认 UA 被直接断开）。
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
# protover=1 兼容 zlib 帧，protover=3 支持 Brotli。
_PROTOVER = 3 if brotli is not None else 1
_BINARY_OPCODE = 2  # RFC 6455 二进制帧

_HEADER = struct.Struct('>IHHII')  # 包长 / 头长 / 协议版本 / 操作码 / 序号
_OP_HEARTBEAT = 2
_OP_HEARTBEAT_REPLY = 3
_OP_MESSAGE = 5
_OP_AUTH = 7
_OP_AUTH_REPLY = 8
_HEARTBEAT_SECONDS = 30
_RECV_TIMEOUT = 40
_RETRY_MIN = 3
_RETRY_MAX = 60
_MAX_PACKET_DEPTH = 8
_MAX_DECOMPRESSED = 4 * 1024 * 1024
_WANTED = {'LIVE': 'live', 'PREPARING': 'end', 'ROOM_CLOSE': 'end'}


def _decompress_brotli(body):
    decompressor = getattr(brotli, 'Decompressor', None)
    if callable(decompressor):
        stream = decompressor()
        try:
            decoded = stream.process(body, output_buffer_limit=_MAX_DECOMPRESSED)
        except TypeError:
            decoded = brotli.decompress(body)
        else:
            if not stream.is_finished() or len(decoded) > _MAX_DECOMPRESSED:
                return None
            return decoded
    decoded = brotli.decompress(body)
    return decoded if len(decoded) <= _MAX_DECOMPRESSED else None


def _decompress_zlib(body):
    stream = zlib.decompressobj()
    decoded = stream.decompress(body, _MAX_DECOMPRESSED)
    if stream.unconsumed_tail or len(decoded) > _MAX_DECOMPRESSED:
        return None
    return decoded


def parse_packet(data):
    """解包 JSON 事件，忽略无效包和无法解压的正文。"""
    messages = []
    _parse_packet(data, messages, 0)
    return messages


def _parse_packet(data, messages, depth):
    if depth >= _MAX_PACKET_DEPTH:
        return
    offset = 0
    total = len(data)
    while offset + _HEADER.size <= total:
        packet_len, header_len, version, operation, _ = _HEADER.unpack_from(data, offset)
        if not _HEADER.size <= header_len <= packet_len <= total - offset:
            break
        body = data[offset + header_len:offset + packet_len]
        offset += packet_len
        if operation != _OP_MESSAGE or not body:
            continue
        if version == 3:
            if brotli is None:
                continue
            try:
                decoded = _decompress_brotli(body)
            except brotli.error:
                continue
            if decoded is not None:
                _parse_packet(decoded, messages, depth + 1)
            continue
        if version in (1, 2):
            try:
                decoded = _decompress_zlib(body)
            except zlib.error:
                pass  # 部分 v1 消息仍是明文 JSON。
            else:
                if decoded is not None:
                    _parse_packet(decoded, messages, depth + 1)
                continue
        try:
            message = json.loads(body)
        except (UnicodeError, ValueError, RecursionError):
            continue
        if isinstance(message, dict):
            messages.append(message)


def wanted_events(messages):
    """从一批消息里挑出开播/下播事件，返回 ('live'|'end') 列表（去重保序）。"""
    events = []
    for message in messages:
        cmd = str(message.get('cmd') or '')
        # 弹幕类消息的 cmd 会带后缀（如 DANMU_MSG:4:0:2:2:2:0），状态类没有。
        name = cmd.split(':', 1)[0]
        event = _WANTED.get(name)
        if event and event not in events:
            events.append(event)
    return events


class LiveWatcher(threading.Thread):
    """单个直播间的长连接监听线程。

    - 收到 LIVE / PREPARING / ROOM_CLOSE 时调用 `on_event(kind)`；
    - 每条 JSON 对象均交给可选的 `on_message(msg)`；
    - 断线按 3→60 秒指数退避重连；
    - `stop()` 后线程在 1 次接收超时内退出（宿主 save 时调用）。
    """

    def __init__(self, room_id, on_event, log=None, on_message=None):
        super().__init__(daemon=True, name='bili-live-%s' % room_id)
        self.room_id = str(room_id)
        self.on_event = on_event
        self.on_message = on_message
        self.log = log or (lambda *args, **kwargs: None)
        self._stop_event = threading.Event()
        self._socket = None
        self._lock = threading.Lock()
        self.last_event_at = 0.0
        self.fail_count = 0

    def stop(self):
        self._stop_event.set()
        with self._lock:
            sock = self._socket
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def _auth_payload(self, token, buvid, uid):
        payload = {
            # 认证包的 uid 要与 cookie 一致，实测传 0 时服务端握手后立即断开。
            'uid': uid, 'roomid': int(self.room_id),
            'protover': _PROTOVER, 'platform': 'web',
            'type': 2, 'key': token,
        }
        if buvid:
            payload['buvid'] = buvid
        return json.dumps(payload).encode('utf-8')

    def _send(self, operation, body=b''):
        packet = _HEADER.pack(_HEADER.size + len(body), _HEADER.size, 1, operation, 1) + body
        with self._lock:
            sock = self._socket
        if sock is None:
            raise ConnectionError('socket closed')
        sock.send(packet, opcode=_BINARY_OPCODE)

    def _resolve(self):
        """拿 token 与可用 host；失败返回 None。"""
        info, error = bili_api.danmu_info(self.room_id)
        if error or not isinstance(info, dict):
            self.log('直播间 %s 取弹幕服务器失败：%s' % (self.room_id, error))
            return None
        token = str(info.get('token') or '')
        hosts = info.get('host_list') or []
        host = ''
        for item in hosts:
            if isinstance(item, dict) and item.get('host'):
                host = str(item['host'])
                break
        if not token or not host:
            self.log('直播间 %s 弹幕信息缺少 token/host' % self.room_id)
            return None
        return host, token

    def _wait_stop(self, seconds):
        return self._stop_event.wait(seconds)

    def _dispatch_messages(self, messages):
        seen = set()
        for msg in messages:
            event = _WANTED.get(str(msg.get('cmd') or '').split(':', 1)[0])
            if event and event not in seen:
                seen.add(event)
                self.last_event_at = time.time()
                self._call(self.on_event, event)
            if self.on_message is not None:
                self._call(self.on_message, msg)

    def _call(self, callback, value):
        try:
            callback(value)
        except Exception as error:  # 插件回调失败不影响长连接与后续消息。
            self.log('直播间 %s 事件回调异常：%s' % (self.room_id, type(error).__name__))

    def run(self):
        if websocket is None or not capabilities.can('live_stats'):
            return

        delay = _RETRY_MIN
        while not self._stop_event.is_set():
            resolved = self._resolve()
            if resolved is None:
                if self._wait_stop(delay):
                    return
                delay = min(delay * 2, _RETRY_MAX)
                continue
            host, token = resolved
            # 认证包必须在握手后尽快发出：这里提前把 uid/buvid 取好，避免在 socket 上做 HTTP。
            buvid = bili_api.buvid_text()
            uid = bili_api.login_uid()
            try:
                sock = websocket.create_connection(
                    'wss://%s/sub' % host, timeout=_RECV_TIMEOUT,
                    header={'User-Agent': _UA, 'Origin': 'https://live.bilibili.com'},
                )
                with self._lock:
                    self._socket = sock
                # 认证包同样要套 16 字节包头（_send 负责），裸发 JSON 会被服务端判成非法帧直接断开。
                self._send(_OP_AUTH, self._auth_payload(token, buvid, uid))
                self.fail_count = 0
                delay = _RETRY_MIN
                heartbeat = threading.Thread(target=self._heartbeat, daemon=True)
                heartbeat.start()
                while not self._stop_event.is_set():
                    try:
                        frame = sock.recv()
                    except (websocket.WebSocketTimeoutException, socket.timeout):
                        self.log('直播间 %s 长连接接收超时，准备重连' % self.room_id)
                        break
                    if frame is None:
                        break
                    if isinstance(frame, str):
                        continue
                    self._dispatch_messages(parse_packet(frame))
            except Exception as error:
                self.fail_count += 1
                self.log('直播间 %s 长连接异常：%s' % (self.room_id, type(error).__name__))
            finally:
                with self._lock:
                    sock, self._socket = self._socket, None
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
            if self._stop_event.is_set():
                return
            if self._wait_stop(delay):
                return
            delay = min(delay * 2, _RETRY_MAX)

    def _heartbeat(self):
        while not self._stop_event.is_set():
            if self._wait_stop(_HEARTBEAT_SECONDS):
                return
            try:
                self._send(_OP_HEARTBEAT)
            except Exception:
                return


def buvid_cookie():
    """给认证包用的 buvid3 值（没有就留空，B 站允许匿名）。"""
    try:
        settings = store.global_config()
    except Exception:
        return ''
    return str(settings.get('cookie', {}).get('buvid3') or '')
