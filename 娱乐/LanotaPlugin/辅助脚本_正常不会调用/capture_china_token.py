# -*- encoding: utf-8 -*-
"""通过 ADB/Chrome DevTools 捕获本人设备上的国服 Portal Token。

使用前：
1. 手机开启开发者选项和 USB 调试，并允许当前电脑调试。
2. 安装依赖：python -m pip install websocket-client
3. 运行本脚本，然后在手机中从游戏打开国服 Portal 并完成登录。

脚本只连接本机 ADB 转发端口，不上传 Token。捕获后会先请求 /api/me
验证，再写入 plugin/data/LanotaPlugin/portal_auth_china.json。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    import websocket
except Exception:
    websocket = None


PORTAL_ORIGIN = 'https://lanota.gmzon.com'
PORTAL_ME_URL = f'{PORTAL_ORIGIN}/portal/api/me'
TOKEN_KEY = 'lanota.portal.chinaToken'
USER_KEY = 'lanota.portal.chinaUser'
DEFAULT_OUTPUT = Path('plugin/data/LanotaPlugin/portal_auth_china.json')
DEVTOOLS_SOCKET_PATTERN = re.compile(r'@?([A-Za-z0-9_.:-]*devtools_remote[A-Za-z0-9_.:-]*)\s*$')
JWT_PATTERN = re.compile(rb'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}')
ROOT_STORAGE_PACKAGES = [
    'com.android.chrome',
    'com.microsoft.emmx',
    'com.gmzon.taptap.lanota',
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='从本人 Android 浏览器捕获国服 Lanota Portal Token。')
    parser.add_argument('--adb', default='', help='adb.exe 路径；默认自动搜索 PATH 和 C:\\Android\\adb.exe。')
    parser.add_argument('--serial', default='', help='ADB 设备序列号；只连接一台设备时可省略。')
    parser.add_argument('--timeout', type=int, default=180, help='等待 Token 的秒数，默认 180。')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT), help='认证 JSON 输出路径。')
    parser.add_argument('--no-write', action='store_true', help='只验证 Token，不写入文件。')
    parser.add_argument('--no-root-scan', action='store_true', help='禁用 root Local Storage 文件扫描。')
    parser.add_argument('--skip-verify', action='store_true', help='跳过 /api/me 在线验证，不推荐。')
    parser.add_argument('--print-token', action='store_true', help='在终端打印完整 Token，可能泄露登录凭据。')
    parser.add_argument('--verbose', action='store_true', help='显示 DevTools 探测错误。')
    return parser.parse_args()


def find_adb(configured_path: str) -> str:
    candidates = [
        configured_path,
        shutil.which('adb') or '',
        os.environ.get('ADB_PATH', ''),
        r'C:\Android\adb.exe',
        str(Path.home() / 'AppData/Local/Android/Sdk/platform-tools/adb.exe'),
    ]
    for candidate in candidates:
        clean_path = os.path.expandvars(os.path.expanduser(str(candidate or '').strip().strip('"')))
        if clean_path and os.path.isfile(clean_path):
            return os.path.abspath(clean_path)
    raise FileNotFoundError('未找到 adb.exe，请使用 --adb 指定路径。')


def adb_command(adb_path: str, serial: str, arguments: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    command = [adb_path]
    if serial:
        command.extend(['-s', serial])
    command.extend(arguments)
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        errors='replace',
        timeout=timeout,
        check=False,
    )


def adb_binary_command(
    adb_path: str,
    serial: str,
    arguments: list[str],
    timeout: int = 15,
) -> subprocess.CompletedProcess:
    command = [adb_path]
    if serial:
        command.extend(['-s', serial])
    command.extend(arguments)
    return subprocess.run(
        command,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def select_device(adb_path: str, configured_serial: str) -> str:
    result = adb_command(adb_path, '', ['devices'], timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f'执行 adb devices 失败：{result.stderr.strip()}')
    devices = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == 'device':
            devices.append(parts[0])
    if configured_serial:
        if configured_serial not in devices:
            raise RuntimeError(f'指定设备 {configured_serial} 未连接或未授权。')
        return configured_serial
    if not devices:
        raise RuntimeError('没有检测到已授权的 Android 设备，请确认 USB 调试授权。')
    if len(devices) > 1:
        raise RuntimeError(f'检测到多台设备，请使用 --serial 指定：{", ".join(devices)}')
    return devices[0]


def parse_devtools_sockets(text: str) -> set[str]:
    sockets = set()
    for line in str(text or '').splitlines():
        matched = DEVTOOLS_SOCKET_PATTERN.search(line)
        if matched:
            sockets.add(matched.group(1))
    return sockets


def discover_devtools_sockets(adb_path: str, serial: str) -> list[str]:
    sockets = {'chrome_devtools_remote'}
    normal_result = adb_command(adb_path, serial, ['shell', 'cat', '/proc/net/unix'])
    sockets.update(parse_devtools_sockets(normal_result.stdout))
    root_result = adb_command(adb_path, serial, ['shell', 'su', '-c', 'cat /proc/net/unix'])
    sockets.update(parse_devtools_sockets(root_result.stdout))
    return sorted(sockets)


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        return int(listener.getsockname()[1])


def add_forward(adb_path: str, serial: str, socket_name: str) -> int | None:
    port = get_free_port()
    result = adb_command(
        adb_path,
        serial,
        ['forward', f'tcp:{port}', f'localabstract:{socket_name}'],
    )
    if result.returncode != 0:
        return None
    return port


def remove_forward(adb_path: str, serial: str, port: int) -> None:
    try:
        adb_command(adb_path, serial, ['forward', '--remove', f'tcp:{port}'], timeout=5)
    except Exception:
        pass


def read_json_url(url: str, timeout: float = 2.0) -> Any:
    request = urllib.request.Request(url, headers={'Host': 'localhost'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def list_targets(port: int) -> list[dict[str, Any]]:
    for path in ['/json/list', '/json']:
        try:
            data = read_json_url(f'http://127.0.0.1:{port}{path}')
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except Exception:
            continue
    return []


def local_websocket_url(remote_url: str, port: int) -> str:
    parsed = urlsplit(remote_url)
    return urlunsplit((parsed.scheme, f'127.0.0.1:{port}', parsed.path, parsed.query, parsed.fragment))


def cdp_request(connection, request_id: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    connection.send(json.dumps({'id': request_id, 'method': method, 'params': params or {}}))
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = json.loads(connection.recv())
        if response.get('id') == request_id:
            return response
    raise TimeoutError(f'等待 CDP {method} 响应超时。')


def read_token_from_target(target: dict[str, Any], port: int) -> dict[str, str] | None:
    target_url = str(target.get('url', '') or '')
    if 'lanota.gmzon.com' not in target_url:
        return None
    websocket_url = str(target.get('webSocketDebuggerUrl', '') or '')
    if not websocket_url:
        return None
    connection = websocket.create_connection(
        local_websocket_url(websocket_url, port),
        timeout=3,
        suppress_origin=True,
    )
    try:
        cdp_request(connection, 1, 'Runtime.enable')
        expression = (
            "JSON.stringify({"
            f"token:localStorage.getItem('{TOKEN_KEY}'),"
            f"user:localStorage.getItem('{USER_KEY}'),"
            'href:location.href})'
        )
        response = cdp_request(
            connection,
            2,
            'Runtime.evaluate',
            {'expression': expression, 'returnByValue': True},
        )
        value = response.get('result', {}).get('result', {}).get('value')
        if not value:
            return None
        data = json.loads(value)
        token = str(data.get('token', '') or '').strip()
        if not token:
            return None
        return {
            'token': token,
            'user': str(data.get('user', '') or ''),
            'href': str(data.get('href', '') or target_url),
        }
    finally:
        connection.close()


def decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        payload_text = token.split('.')[1]
        payload_text += '=' * (-len(payload_text) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_text.encode('ascii')).decode('utf-8'))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def discover_root_storage_files(adb_path: str, serial: str) -> list[str]:
    roots = ' '.join(f'/data/user/0/{package_name}' for package_name in ROOT_STORAGE_PACKAGES)
    command = f'find {roots} -type f 2>/dev/null'
    result = adb_command(adb_path, serial, ['shell', 'su', '-c', command], timeout=20)
    if result.returncode != 0 and not result.stdout:
        return []
    storage_files = []
    for raw_path in result.stdout.splitlines():
        file_path = raw_path.strip()
        normalized_path = file_path.replace('\\', '/').casefold()
        if not file_path:
            continue
        if '/local storage/leveldb/' in normalized_path or '/localstorage/' in normalized_path:
            storage_files.append(file_path)
    return storage_files


def extract_jwt_candidates(raw_data: bytes) -> set[str]:
    candidates = set()
    for source_data in [raw_data, raw_data.replace(b'\x00', b'')]:
        for matched in JWT_PATTERN.finditer(source_data):
            try:
                token = matched.group(0).decode('ascii')
            except UnicodeDecodeError:
                continue
            payload = decode_jwt_payload(token)
            if payload.get('exp'):
                candidates.add(token)
    return candidates


def scan_root_storage(
    adb_path: str,
    serial: str,
    rejected_tokens: set[str],
    verbose: bool,
) -> str | None:
    for file_path in discover_root_storage_files(adb_path, serial):
        quoted_path = "'" + file_path.replace("'", "'\\''") + "'"
        result = adb_binary_command(
            adb_path,
            serial,
            ['exec-out', 'su', '-c', f'cat {quoted_path}'],
            timeout=15,
        )
        if result.returncode != 0 or not result.stdout:
            continue
        for token in extract_jwt_candidates(result.stdout):
            if token in rejected_tokens:
                continue
            try:
                verify_token(token)
                return token
            except Exception as exception_object:
                rejected_tokens.add(token)
                if verbose:
                    print(f'已忽略无效 JWT [{file_path}]：{type(exception_object).__name__}: {exception_object}')
    return None


def parse_user(user_text: str) -> dict[str, Any]:
    try:
        data = json.loads(user_text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def verify_token(token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        PORTAL_ME_URL,
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'User-Agent': 'LanotaPlugin-ChinaTokenCapture/1.0',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exception_object:
        raise PermissionError(f'国服 Portal 拒绝 Token：HTTP {exception_object.code}') from exception_object
    if not isinstance(data, dict):
        raise RuntimeError('国服 /api/me 返回了无法识别的数据。')
    return data


def save_token(output_path: Path, token: str, user_text: str, verified_user: dict[str, Any]) -> Path:
    payload = decode_jwt_payload(token)
    stored_user = parse_user(user_text)
    uid = (
        stored_user.get('uid')
        or verified_user.get('uid')
        or payload.get('uid')
        or payload.get('sub')
        or ''
    )
    token_data = {
        'china_token': token,
        'uid': str(uid),
        'expires_at': int(payload.get('exp', 0) or 0),
        'saved_at': int(time.time()),
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.is_file():
        backup_path = output_path.with_suffix(output_path.suffix + '.bak')
        shutil.copy2(output_path, backup_path)
    temporary_path = output_path.with_suffix(output_path.suffix + '.tmp')
    temporary_path.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary_path, output_path)
    return output_path


def masked_token(token: str) -> str:
    if len(token) <= 20:
        return '*' * len(token)
    return f'{token[:10]}...{token[-8:]}'


def finish_capture(args: argparse.Namespace, captured: dict[str, str]) -> int:
    token = captured['token']
    verified_user = {} if args.skip_verify else verify_token(token)
    print(f'已捕获并验证国服 Token：{masked_token(token)}')
    print(f'来源：{captured["href"]}')
    if args.print_token:
        print(f'完整 Token：{token}')
    if not args.no_write:
        output_path = save_token(Path(args.output), token, captured.get('user', ''), verified_user)
        print(f'已写入：{output_path}')
        print('重新加载 LanotaPlugin 后可执行 .la china status 和 .la user。')
    return 0


def capture_token(args: argparse.Namespace) -> int:
    if websocket is None:
        raise RuntimeError('缺少 websocket-client，请执行：python -m pip install websocket-client')
    adb_path = find_adb(args.adb)
    serial = select_device(adb_path, args.serial)
    print(f'已连接设备：{serial}')
    print('请在手机中从游戏打开国服 Portal 并完成登录，正在等待 Token...')

    forwards: dict[str, int] = {}
    rejected_tokens: set[str] = set()
    deadline = time.monotonic() + max(10, args.timeout)
    last_socket_refresh = 0.0
    last_root_scan = 0.0
    try:
        while time.monotonic() < deadline:
            if time.monotonic() - last_socket_refresh >= 2:
                for socket_name in discover_devtools_sockets(adb_path, serial):
                    if socket_name in forwards:
                        continue
                    port = add_forward(adb_path, serial, socket_name)
                    if port is not None:
                        forwards[socket_name] = port
                        if args.verbose:
                            print(f'已转发 DevTools：{socket_name} -> 127.0.0.1:{port}')
                last_socket_refresh = time.monotonic()

            for socket_name, port in list(forwards.items()):
                for target in list_targets(port):
                    try:
                        captured = read_token_from_target(target, port)
                    except Exception as exception_object:
                        if args.verbose:
                            print(f'DevTools 读取失败 [{socket_name}]：{type(exception_object).__name__}: {exception_object}')
                        continue
                    if not captured:
                        continue
                    return finish_capture(args, captured)

            if not args.no_root_scan and time.monotonic() - last_root_scan >= 2:
                root_token = scan_root_storage(
                    adb_path,
                    serial,
                    rejected_tokens,
                    args.verbose,
                )
                if root_token:
                    return finish_capture(
                        args,
                        {
                            'token': root_token,
                            'user': '',
                            'href': 'root Local Storage LevelDB',
                        },
                    )
                last_root_scan = time.monotonic()
            time.sleep(0.5)
    finally:
        for port in forwards.values():
            remove_forward(adb_path, serial, port)
    raise TimeoutError(
        '等待 Token 超时。请确认登录页面由 Chrome 或可调试 WebView 打开；'
        '可加 --verbose 查看 DevTools socket 探测结果。'
    )


def main() -> int:
    args = parse_args()
    try:
        return capture_token(args)
    except KeyboardInterrupt:
        print('\n已取消。')
        return 130
    except Exception as exception_object:
        print(f'失败：{type(exception_object).__name__}: {exception_object}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
