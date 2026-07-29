# -*- encoding: utf-8 -*-
'''MCP 客户端：发现并调用 Streamable HTTP / stdio 服务端工具。'''

import copy
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time

import requests

import OlivaAIAgent

_lock = threading.RLock()
_refresh_lock = threading.Lock()
_tool_defs = []
_tool_map = {}
_server_status = []
_last_refresh = 0.0
_config_fingerprint = ''


def _mcpConfig():
    return OlivaAIAgent.conf.get('mcp', default={}) or {}


def _enabledServers():
    servers = _mcpConfig().get('servers', [])
    if not isinstance(servers, list):
        return []
    return [copy.deepcopy(item) for item in servers if isinstance(item, dict) and item.get('enabled', True)]


def _fingerprint():
    payload = {
        'enabled': bool(_mcpConfig().get('enabled', False)),
        'protocol_version': _mcpConfig().get('protocol_version', ''),
        'servers': _enabledServers(),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _timeout(server):
    value = server.get('timeout_sec', _mcpConfig().get('timeout_sec', 30))
    return max(1.0, float(value))


def _protocolVersion():
    return str(_mcpConfig().get('protocol_version', '2025-03-26') or '2025-03-26')


def _jsonRpcError(message):
    if isinstance(message, dict) and isinstance(message.get('error'), dict):
        error = message['error']
        raise RuntimeError('%s: %s' % (error.get('code', 'MCP'), error.get('message', '未知错误')))


def _sseMessages(text):
    messages = []
    data_lines = []
    for line in str(text or '').splitlines() + ['']:
        if line.startswith('data:'):
            data_lines.append(line[5:].lstrip())
        elif line == '' and data_lines:
            try:
                messages.append(json.loads('\n'.join(data_lines)))
            except Exception:
                pass
            data_lines = []
    return messages


class _HttpTransport:
    def __init__(self, server):
        self.server = server
        self.url = str(server.get('url', '')).strip()
        if not self.url:
            raise ValueError('Streamable HTTP 服务缺少 url')
        self.timeout = _timeout(server)
        self.session_id = None
        self.session = requests.Session()
        self.headers = {
            'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json',
            'MCP-Protocol-Version': _protocolVersion(),
        }
        headers = server.get('headers', {})
        if isinstance(headers, dict):
            self.headers.update({str(key): str(value) for key, value in headers.items()})

    def close(self):
        self.session.close()

    def _post(self, payload, request_id=None):
        headers = dict(self.headers)
        if self.session_id:
            headers['Mcp-Session-Id'] = self.session_id
        response = self.session.post(self.url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        session_id = response.headers.get('Mcp-Session-Id')
        if session_id:
            self.session_id = session_id
        if request_id is None or not str(response.text or '').strip():
            return None
        content_type = str(response.headers.get('Content-Type', '')).lower()
        if 'text/event-stream' in content_type or str(response.text).lstrip().startswith(('event:', 'data:')):
            candidates = _sseMessages(response.text)
        else:
            data = response.json()
            candidates = data if isinstance(data, list) else [data]
        for message in candidates:
            if (
                isinstance(message, dict)
                and str(message.get('id')) == str(request_id)
                and ('result' in message or 'error' in message)
            ):
                _jsonRpcError(message)
                return message.get('result', {})
        raise RuntimeError('MCP 响应中缺少请求 id=%s' % request_id)

    def request(self, request_id, method, params=None):
        payload = {'jsonrpc': '2.0', 'id': request_id, 'method': method}
        if params is not None:
            payload['params'] = params
        return self._post(payload, request_id=request_id)

    def notify(self, method, params=None):
        payload = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            payload['params'] = params
        self._post(payload)


class _StdioTransport:
    def __init__(self, server):
        command = str(server.get('command', '')).strip()
        if not command:
            raise ValueError('stdio 服务缺少 command')
        args = server.get('args', [])
        if not isinstance(args, list):
            raise ValueError('stdio args 必须是 JSON 数组')
        env = os.environ.copy()
        extra_env = server.get('env', {})
        if isinstance(extra_env, dict):
            env.update({str(key): str(value) for key, value in extra_env.items()})
        resolved_command = shutil.which(command, path=env.get('PATH')) or command
        kwargs = {
            'args': [resolved_command] + [str(item) for item in args],
            'cwd': str(server.get('cwd', '')).strip() or None,
            'env': env,
            'stdin': subprocess.PIPE,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True,
            'encoding': 'utf-8',
            'errors': 'replace',
            'bufsize': 1,
        }
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(**kwargs)
        self.timeout = _timeout(server)
        self.messages = queue.Queue()
        threading.Thread(target=self._readStdout, daemon=True).start()
        threading.Thread(target=self._drainStderr, daemon=True).start()

    def _readStdout(self):
        try:
            for line in self.process.stdout:
                try:
                    message = json.loads(line.strip())
                except Exception:
                    continue
                self.messages.put(message)
        except Exception:
            pass

    def _drainStderr(self):
        try:
            for _line in self.process.stderr:
                pass
        except Exception:
            pass

    def close(self):
        try:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=2)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass

    def _write(self, payload):
        if self.process.poll() is not None:
            raise RuntimeError('MCP stdio 进程已退出，退出码=%s' % self.process.returncode)
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
        self.process.stdin.flush()

    def request(self, request_id, method, params=None):
        payload = {'jsonrpc': '2.0', 'id': request_id, 'method': method}
        if params is not None:
            payload['params'] = params
        self._write(payload)
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('MCP stdio 请求超时: %s' % method)
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as e:
                raise TimeoutError('MCP stdio 请求超时: %s' % method) from e
            if (
                isinstance(message, dict)
                and str(message.get('id')) == str(request_id)
                and ('result' in message or 'error' in message)
            ):
                _jsonRpcError(message)
                return message.get('result', {})

    def notify(self, method, params=None):
        payload = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            payload['params'] = params
        self._write(payload)


def _openTransport(server):
    transport = str(server.get('transport', 'streamable_http')).strip().lower()
    if transport in {'streamable_http', 'http'}:
        return _HttpTransport(server)
    if transport == 'stdio':
        return _StdioTransport(server)
    raise ValueError('不支持的 MCP transport: %s' % transport)


def _initialize(transport):
    result = transport.request(
        1,
        'initialize',
        {
            'protocolVersion': _protocolVersion(),
            'capabilities': {},
            'clientInfo': {'name': 'OlivaAIAgent', 'version': '2.19.0'},
        },
    )
    transport.notify('notifications/initialized')
    return result if isinstance(result, dict) else {}


def _listTools(server):
    transport = _openTransport(server)
    try:
        initialize_result = _initialize(transport)
        tools = []
        cursor = None
        request_id = 2
        while True:
            params = {'cursor': cursor} if cursor else {}
            result = transport.request(request_id, 'tools/list', params)
            request_id += 1
            if not isinstance(result, dict):
                raise RuntimeError('MCP tools/list 返回格式无效')
            tools.extend(item for item in result.get('tools', []) if isinstance(item, dict))
            cursor = result.get('nextCursor')
            if not cursor:
                break
        return initialize_result, tools
    finally:
        transport.close()


def _callTool(server, remote_name, arguments):
    transport = _openTransport(server)
    try:
        _initialize(transport)
        return transport.request(2, 'tools/call', {'name': remote_name, 'arguments': arguments or {}})
    finally:
        transport.close()


def _slug(value, fallback):
    text = re.sub(r'[^A-Za-z0-9_-]+', '_', str(value or '')).strip('_')
    if text:
        return text
    digest = hashlib.sha1(str(value or fallback).encode('utf-8')).hexdigest()[:8]
    return '%s_%s' % (fallback, digest)


def _publicName(server_name, remote_name, occupied):
    base = 'mcp_%s_%s' % (_slug(server_name, 'server'), _slug(remote_name, 'tool'))
    base = base[:64]
    name = base
    if name in occupied:
        suffix = '_' + hashlib.sha1(('%s|%s' % (server_name, remote_name)).encode('utf-8')).hexdigest()[:6]
        name = base[:64 - len(suffix)] + suffix
    return name


def invalidate():
    global _tool_defs, _tool_map, _server_status, _last_refresh, _config_fingerprint
    with _lock:
        _tool_defs = []
        _tool_map = {}
        _server_status = []
        _last_refresh = 0.0
        _config_fingerprint = ''


def _refresh(force=True):
    '''连接已启用服务并重建动态工具目录。'''
    global _tool_defs, _tool_map, _server_status, _last_refresh, _config_fingerprint
    cfg = _mcpConfig()
    fingerprint = _fingerprint()
    with _lock:
        if not cfg.get('enabled', False):
            _tool_defs = []
            _tool_map = {}
            _server_status = []
            _last_refresh = time.time()
            _config_fingerprint = fingerprint
            return getStatus()
        ttl = max(1.0, float(cfg.get('refresh_interval_sec', 300)))
        if not force and fingerprint == _config_fingerprint and time.time() - _last_refresh < ttl:
            return getStatus()

    tool_defs = []
    tool_map = {}
    server_status = []
    occupied = set()
    for index, server in enumerate(_enabledServers()):
        server_name = str(server.get('name', '')).strip() or 'server_%d' % (index + 1)
        try:
            initialize_result, remote_tools = _listTools(server)
            for remote in remote_tools:
                remote_name = str(remote.get('name', '')).strip()
                if not remote_name:
                    continue
                public_name = _publicName(server_name, remote_name, occupied)
                occupied.add(public_name)
                schema = remote.get('inputSchema')
                if not isinstance(schema, dict):
                    schema = {'type': 'object', 'properties': {}}
                description = str(remote.get('description', '')).strip() or 'MCP 工具 %s' % remote_name
                tool_defs.append({'name': public_name, 'desc': '[MCP:%s] %s' % (server_name, description), 'params': schema})
                tool_map[public_name] = {
                    'server': copy.deepcopy(server),
                    'server_name': server_name,
                    'remote_name': remote_name,
                    'danger': bool(server.get('danger', True)),
                }
            server_info = initialize_result.get('serverInfo', {}) if isinstance(initialize_result, dict) else {}
            server_status.append({
                'name': server_name,
                'connected': True,
                'tools': len(remote_tools),
                'server_info': server_info,
                'error': '',
            })
            OlivaAIAgent.conf.log(
                OlivaAIAgent.conf.gProc,
                2,
                'MCP 连接完成 | 服务=%s | 工具=%d' % (server_name, len(remote_tools)),
            )
        except Exception as e:
            server_status.append({
                'name': server_name,
                'connected': False,
                'tools': 0,
                'server_info': {},
                'error': '%s: %s' % (type(e).__name__, e),
            })
            OlivaAIAgent.conf.log(
                OlivaAIAgent.conf.gProc,
                3,
                'MCP 连接失败 | 服务=%s | 错误=%s: %s' % (server_name, type(e).__name__, e),
            )
    with _lock:
        _tool_defs = tool_defs
        _tool_map = tool_map
        _server_status = server_status
        _last_refresh = time.time()
        _config_fingerprint = fingerprint
    return getStatus()


def refresh(force=True):
    with _refresh_lock:
        return _refresh(force=force)


def _ensureCatalog():
    cfg = _mcpConfig()
    if not cfg.get('enabled', False):
        with _lock:
            has_cached_tools = bool(_tool_defs or _tool_map or _server_status)
        if has_cached_tools:
            invalidate()
        return
    fingerprint = _fingerprint()
    ttl = max(1.0, float(cfg.get('refresh_interval_sec', 300)))
    with _lock:
        stale = fingerprint != _config_fingerprint or time.time() - _last_refresh >= ttl
    if stale:
        refresh(force=False)


def getToolDefs():
    _ensureCatalog()
    with _lock:
        return copy.deepcopy(_tool_defs)


def getToolItem(name):
    _ensureCatalog()
    with _lock:
        item = _tool_map.get(str(name))
        return copy.deepcopy(item) if isinstance(item, dict) else None


def execute(name, arguments, _ctx=None):
    item = getToolItem(name)
    if item is None:
        return {'error': '未知或已失效的 MCP 工具: %s' % name}
    result = _callTool(item['server'], item['remote_name'], arguments or {})
    return {
        'active': not bool(result.get('isError')) if isinstance(result, dict) else True,
        'data': {
            'server': item['server_name'],
            'tool': item['remote_name'],
            'result': result,
        },
    }


def getStatus():
    cfg = _mcpConfig()
    with _lock:
        return {
            'enabled': bool(cfg.get('enabled', False)),
            'servers': len(_enabledServers()),
            'connected': sum(1 for item in _server_status if item.get('connected')),
            'tools': len(_tool_defs),
            'updated_at': _last_refresh,
            'details': copy.deepcopy(_server_status),
        }


def testServer(server):
    initialize_result, tools = _listTools(copy.deepcopy(server))
    server_info = initialize_result.get('serverInfo', {}) if isinstance(initialize_result, dict) else {}
    return {'active': True, 'server_info': server_info, 'tools': len(tools)}
