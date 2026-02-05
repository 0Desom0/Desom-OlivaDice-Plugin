from __future__ import annotations

import datetime as _dt
import os
import platform
import subprocess
import time
from dataclasses import dataclass
from typing import Iterable, Optional
import psutil


_PREFIXES = ('.', '/', '。')
_COMMANDS = {'status', 'state', '状态', 'stat'}


@dataclass(frozen=True)
class StatusCommand:
    raw: str
    cmd: str


_last_net_sample: Optional[tuple[float, int, int]] = None


def parse_status_command(message: str, self_id: str) -> Optional[StatusCommand]:
    """解析 OlivOS 的消息文本；匹配时返回 StatusCommand。

    支持前缀：'.'、'/'、'。'。
    支持命令：status、state、状态。
    注意：如果外层已处理 @ 提取（CQ 或 Qingguo 格式），则无需重复剥离，这里只做前缀/命令匹配。
    """

    text = (message or '').strip()
    if not text:
        return None

    # 支持两种运行时模式：
    # - 如果存在 OlivaDiceCore（通常外层会先去掉前缀），则前缀是可选的；
    #   遇到前缀则去掉，未遇到前缀也可直接匹配命令。
    # - 如果不存在 OlivaDiceCore，则要求消息必须以前缀开头。
    # 检查 OlivaDiceCore 是否存在（避免实际导入导致未使用的导入警告）
    try:
        import importlib.util as _importlib_util
        _has_core = _importlib_util.find_spec('OlivaDiceCore') is not None
    except Exception:
        _has_core = False

    if _has_core:
        # 允许可选前缀
        if text and text[0] in _PREFIXES:
            after = text[1:].lstrip()
        else:
            after = text.lstrip()
    else:
        # 必须有前缀
        if not text or text[0] not in _PREFIXES:
            return None
        after = text[1:].lstrip()

    if not after:
        return None

    token = after.split(maxsplit=1)[0]
    cmd = _match_command_prefix(token)
    if cmd is not None:
        return StatusCommand(raw=message, cmd=cmd)
    return None


def _match_command_prefix(token: str) -> Optional[str]:
    """按前缀匹配命令。

    例如：token 为 'statusaaaa' 时会匹配到命令 'status'。
    优先匹配长度较长的命令以避免短命令抢占长命令。
    """

    if not token:
        return None

    token_lower = token.lower()
    for cmd in sorted(_COMMANDS, key=len, reverse=True):
        # 对 ASCII 命令使用小写比较，中文命令直接按原文比较
        if cmd.isascii():
            if token_lower.startswith(cmd):
                return cmd
        else:
            if token.startswith(cmd):
                return cmd
    return None


def build_status_report() -> str:
    lines: list[str] = []
    lines.append('系统状态报告')
    lines.append('====================')
    lines.append(f'时间: {_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.extend(_build_platform_lines())
    lines.extend(_build_cpu_lines())
    lines.extend(_build_temp_lines())
    lines.extend(_build_gpu_lines())
    lines.extend(_build_load_lines())
    lines.extend(_build_process_lines())
    lines.extend(_build_network_lines())
    lines.extend(_build_memory_lines())
    lines.extend(_build_disk_lines())
    return '\n'.join([ln for ln in lines if ln])


def _build_platform_lines() -> list[str]:
    os_name = platform.system()
    os_release = platform.release()
    os_version = platform.version()

    uptime = _get_uptime_seconds()
    uptime_text = _format_duration(uptime) if uptime is not None else '未知'

    return [
        f'系统: {os_name} {os_release}',
        f'系统版本: {os_version}' if os_version else '',
        f'系统运行时间: {uptime_text}',
    ]


def _build_cpu_lines() -> list[str]:
    logical = psutil.cpu_count(logical=True)
    physical = psutil.cpu_count(logical=False)
    total = psutil.cpu_percent(interval=0.2)
    per_cpu = psutil.cpu_percent(interval=None, percpu=True)

    freq_text = ''
    try:
        freq = psutil.cpu_freq()
        if freq is not None and freq.current:
            freq_text = f'，频率: {freq.current:.0f}MHz'
    except Exception:
        freq_text = ''

    topology = []
    if physical:
        topology.append(f'{physical}核')
    if logical:
        topology.append(f'{logical}线程')
    topo_text = f"({'/'.join(topology)})" if topology else ''

    per_cpu_text = _join_kv_percent(per_cpu, max_items=16)
    return [
        f'CPU使用率: {total:.1f}% {topo_text}{freq_text}',
        f'各线程: {per_cpu_text}' if per_cpu_text else '',
    ]


def _build_load_lines() -> list[str]:
    try:
        load1, load5, load15 = os.getloadavg()
    except Exception:
        return []
    return [f'负载: {load1:.2f}, {load5:.2f}, {load15:.2f} (1/5/15min)']


def _build_network_lines() -> list[str]:
    global _last_net_sample

    counters = psutil.net_io_counters()
    sent = int(getattr(counters, 'bytes_sent', 0))
    recv = int(getattr(counters, 'bytes_recv', 0))
    now = time.time()

    rate_text = ''
    if _last_net_sample is not None:
        last_t, last_sent, last_recv = _last_net_sample
        dt = now - last_t
        if dt >= 0.5:
            up_rate = max(0, sent - last_sent) / dt
            down_rate = max(0, recv - last_recv) / dt
            rate_text = f'，速率: ↑{_format_bytes(up_rate)}/s ↓{_format_bytes(down_rate)}/s'

    _last_net_sample = (now, sent, recv)

    return [f'网络: ↑{_format_bytes(sent)} ↓{_format_bytes(recv)}{rate_text}']


def _build_memory_lines() -> list[str]:
    vm = psutil.virtual_memory()
    used = int(vm.total - vm.available)
    percent = float(vm.percent)
    lines = [f'内存使用: {percent:.1f}% ({_format_bytes(used)}/{_format_bytes(int(vm.total))})']

    try:
        sm = psutil.swap_memory()
        if sm is not None and sm.total:
            lines.append(
                f'交换分区: {float(sm.percent):.1f}% ({_format_bytes(int(sm.used))}/{_format_bytes(int(sm.total))})'
            )
    except Exception:
        pass
    return lines


def _build_disk_lines() -> list[str]:
    lines: list[str] = []
    try:
        parts = psutil.disk_partitions(all=True)
    except Exception:
        return []

    seen: set[str] = set()
    for part in parts:
        mount = getattr(part, 'mountpoint', None)
        if not mount or mount in seen:
            continue
        seen.add(mount)

        # Windows: skip drives without media
        try:
            usage = psutil.disk_usage(mount)
        except Exception:
            continue

        total = int(usage.total)
        if total <= 0:
            continue

        used = int(usage.used)
        percent = float(usage.percent)
        device = getattr(part, 'device', '')
        label = device if device else mount
        lines.append(f'{label} ({mount}): {percent:.1f}% ({_format_bytes(used)}/{_format_bytes(total)})')

    return ['磁盘:'] + [f'  {ln}' for ln in lines[:20]] if lines else []


def _get_uptime_seconds() -> Optional[float]:
    try:
        boot = float(psutil.boot_time())
        return max(0.0, time.time() - boot)
    except Exception:
        return None


def _format_duration(seconds: float) -> str:
    seconds_i = int(seconds)
    days, rem = divmod(seconds_i, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    if days > 0:
        return f'{days}天{hours}小时{minutes}分钟'
    if hours > 0:
        return f'{hours}小时{minutes}分钟{sec}秒'
    if minutes > 0:
        return f'{minutes}分钟{sec}秒'
    return f'{sec}秒'


def _format_bytes(num: float) -> str:
    if num < 0:
        num = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    idx = 0
    val = float(num)
    while val >= 1024 and idx < len(units) - 1:
        val /= 1024
        idx += 1
    if idx == 0:
        return f'{int(val)}{units[idx]}'
    return f'{val:.2f}{units[idx]}'


def _join_kv_percent(values: Iterable[float], max_items: int) -> str:
    pairs: list[str] = []
    for i, v in enumerate(values, start=1):
        if i > max_items:
            pairs.append('...')
            break
        pairs.append(f'{i}:{float(v):.0f}%')
    return ' '.join(pairs)


def _build_process_lines() -> list[str]:
    try:
        proc_count = len(psutil.pids())
    except Exception:
        proc_count = None
    try:
        user_count = len(psutil.users())
    except Exception:
        user_count = None

    parts: list[str] = []
    if proc_count is not None:
        parts.append(f'进程数: {proc_count}')
    if user_count is not None:
        parts.append(f'在线用户: {user_count}')
    return ['，'.join(parts)] if parts else []


def _build_temp_lines() -> list[str]:
    # 如果 psutil 没有 sensors_temperatures 接口或调用失败，则返回空
    if not hasattr(psutil, 'sensors_temperatures'):
        return []

    try:
        temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
    except Exception:
        return []
    if not temps:
        return []

    # 优先查找常见的 CPU 温度传感器组
    prefer_keys = ('coretemp', 'k10temp', 'cpu_thermal', 'cpu-thermal', 'soc_thermal', 'acpitz')
    entries = None
    for k in prefer_keys:
        if k in temps and temps[k]:
            entries = temps[k]
            break
    if entries is None:
        # 回退：选择第一个非空的传感器组
        for v in temps.values():
            if v:
                entries = v
                break
    if not entries:
        return []

    values = [float(getattr(e, 'current', 0.0)) for e in entries if getattr(e, 'current', None) is not None]
    values = [v for v in values if v > 0]
    if not values:
        return []
    max_t = max(values)
    return [f'温度: {max_t:.1f}°C']


def _build_gpu_lines() -> list[str]:
    """尝试通过 nvidia-smi 获取 GPU 使用率与显存占用；不可用时返回空列表。"""

    try:
        proc = subprocess.run(
            [
                'nvidia-smi',
                '--query-gpu=utilization.gpu,memory.used,memory.total',
                '--format=csv,noheader,nounits',
            ],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except Exception:
        return []

    if proc.returncode != 0:
        return []
    out = (proc.stdout or '').strip()
    if not out:
        return []

    gpus: list[str] = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) != 3:
            continue
        try:
            util = float(parts[0])
            mem_used_mib = float(parts[1])
            mem_total_mib = float(parts[2])
        except Exception:
            continue
        mem_used = _format_bytes(mem_used_mib * 1024 * 1024)
        mem_total = _format_bytes(mem_total_mib * 1024 * 1024)
        gpus.append(f'{util:.1f}% ({mem_used}/{mem_total})')

    if not gpus:
        return []
    if len(gpus) == 1:
        return [f'GPU使用率: {gpus[0]}']
    joined = ' | '.join([f'GPU{i + 1}:{v}' for i, v in enumerate(gpus)])
    return [f'GPU使用率: {joined}']
