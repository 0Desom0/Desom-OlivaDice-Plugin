# -*- encoding: utf-8 -*-
"""B 站直播间 WebSocket 监听。

只做一件事：感知「开播 / 下播」两个事件，用来把推送从「等下一次轮询」提前到「秒级」。
协议用 protover=1（zlib + JSON），不引入 protobuf。

参考：https://github.com/Starlwr/StarBot （core/live.py，protover=3 + protobuf）
      https://github.com/SocialSisterYi/bilibili-API-collect （直播间信息流协议）
"""

import json
import socket
import struct
import threading
import time
import zlib

import websocket

from . import bili_api, store

# B 站弹幕服务器会拒绝没有浏览器 UA 的握手（实测 websocket-client 默认 UA 被直接断开）。
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
# protover=1 是 zlib+JSON（parse_packet 能直接解），2/3 需要 protobuf。
# 实测 2026-11-25：protover=0 会被服务端握手后立刻断开。
_PROTOVER = 1

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
_CLOSE_STATES = {'LIVE', 'PREPARING', 'ROOM_CLOSE'}
_WANTED = {'LIVE': 'live', 'PREPARING': 'end', 'ROOM_CLOSE': 'end'}


def parse_packet(data):
    """把一个 TCP 帧拆成消息列表；zlib 压缩的正文会再递归拆一层。

    Returns:
        list[dict] -- 解析成功的 JSON 消息；无法解析的片段被忽略。
    """
    messages = []
    offset = 0
    total = len(data)
    while offset + _HEADER.size <= total:
        packet_len, header_len, version, operation, _ = _HEADER.unpack_from(data, offset)
        if packet_len < header_len or offset + packet_len > total:
            break
        body = data[offset + header_len:offset + packet_len]
        offset += packet_len
        if version == 1 and body:
            try:
                messages.extend(parse_packet(zlib.decompress(body)))
                continue
            except zlib.error:
                pass  # 认证回包(op=8)的正文是明文 JSON，不是 zlib
        if operation == _OP_MESSAGE and body:
            try:
                message = json.loads(body.decode('utf-8', 'ignore'))
            except (UnicodeDecodeError, ValueError):
                continue
            if isinstance(message, dict):
                messages.append(message)
    return messages


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
    - 断线按 3→60 秒指数退避重连；
    - `stop()` 后线程在 1 次接收超时内退出（宿主 save 时调用）。
    """

    def __init__(self, room_id, on_event, log=None):
        super().__init__(daemon=True, name='bili-live-%s' % room_id)
        self.room_id = str(room_id)
        self.on_event = on_event
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
        sock.send(packet, opcode=websocket.ABNF.OPCODE_BINARY)

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

    def run(self):
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
                    for event in wanted_events(parse_packet(frame)):
                        self.last_event_at = time.time()
                        try:
                            self.on_event(event)
                        except Exception as error:  # 回调是插件内部逻辑，异常不能断连接
                            self.log('直播间 %s 事件回调异常：%s' % (self.room_id, type(error).__name__))
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
