# -*- encoding: utf-8 -*-
"""国服 Lanota 客户端 Community gRPC 查询备用适配层。

该接口来自国服客户端，查询方法目前无需 Portal Token。这里仅实现公开的
SearchPlayer/GetPlayerSongRecord，使用最小 protobuf wire parser，避免在插件
目录中生成和维护一整套随客户端版本变化的 protobuf 文件。
"""

from __future__ import annotations

import math
import struct
import threading
from typing import Any, Iterator

try:
    import grpc

    GRPC_AVAILABLE = True
except Exception:
    grpc = None
    GRPC_AVAILABLE = False


GRPC_HOST = 'cn01.svr-lanota-prod.gmzon.com:5001'
UNKNOWN = '暂无法获取'
DIFFICULTY_NAMES = ('Whisper', 'Acoustic', 'Ultra', 'Master')
RANK_NAMES = ('L', 'S', 'A', 'B', 'C', 'D')
channel_lock = threading.RLock()
community_channel = None


class ChinaGrpcError(RuntimeError):
    """备用 gRPC 查询失败。"""


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift >= 70:
            break
    raise ValueError('protobuf varint 无效。')


def _iter_fields(data: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    offset = 0
    while offset < len(data):
        tag, offset = _read_varint(data, offset)
        field_number = tag >> 3
        wire_type = tag & 0x07
        if field_number <= 0:
            raise ValueError('protobuf 字段编号无效。')
        if wire_type == 0:
            value, offset = _read_varint(data, offset)
        elif wire_type == 1:
            end = offset + 8
            if end > len(data):
                raise ValueError('protobuf fixed64 字段越界。')
            value = data[offset:end]
            offset = end
        elif wire_type == 2:
            length, offset = _read_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ValueError('protobuf 长度字段越界。')
            value = data[offset:end]
            offset = end
        elif wire_type == 5:
            end = offset + 4
            if end > len(data):
                raise ValueError('protobuf fixed32 字段越界。')
            value = data[offset:end]
            offset = end
        else:
            raise ValueError(f'暂不支持 protobuf wire type {wire_type}。')
        yield field_number, wire_type, value


def _encode_varint(value: int) -> bytes:
    value = max(0, int(value))
    output = bytearray()
    while value > 0x7F:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def _encode_string(field_number: int, value: str) -> bytes:
    encoded = str(value).encode('utf-8')
    return _encode_varint(field_number << 3 | 2) + _encode_varint(len(encoded)) + encoded


def _decode_text(value: int | bytes) -> str:
    if not isinstance(value, bytes):
        return ''
    return value.decode('utf-8', errors='replace').strip()


def _decode_float(value: int | bytes) -> float | None:
    if not isinstance(value, bytes) or len(value) != 4:
        return None
    result = struct.unpack('<f', value)[0]
    return result if math.isfinite(result) else None


def _parse_profile(data: bytes) -> dict[str, Any]:
    profile: dict[str, Any] = {}
    for field, wire, value in _iter_fields(data):
        if field == 1 and wire == 2:
            profile['nanoId'] = _decode_text(value)
        elif field == 2 and wire == 2:
            profile['username'] = _decode_text(value)
        elif field == 3 and wire == 2:
            profile['avatarId'] = _decode_text(value)
        elif field == 4 and wire == 5:
            profile['rating'] = _decode_float(value)
        elif field == 5 and wire == 0:
            profile['notalium'] = int(value)
        elif field == 6 and wire == 0:
            profile['totalScore'] = int(value)
    return profile


def _parse_search_response(data: bytes) -> list[dict[str, Any]]:
    result = []
    for field, wire, value in _iter_fields(data):
        if field == 1 and wire == 2:
            result.append(_parse_profile(value))
    return result


def _parse_chart_record(data: bytes) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for field, wire, value in _iter_fields(data):
        if field == 1 and wire == 2:
            record['songId'] = _decode_text(value)
        elif field == 2 and wire == 0:
            record['difficulty'] = int(value)
        elif field == 3 and wire == 0:
            record['score'] = int(value)
        elif field == 4 and wire == 0:
            record['clear'] = int(value)
    return record


def _parse_record_response(data: bytes) -> list[dict[str, Any]]:
    result = []
    for field, wire, value in _iter_fields(data):
        if field == 1 and wire == 2:
            result.append(_parse_chart_record(value))
    return result


def _call(method: str, payload: bytes, timeout: float) -> bytes:
    global community_channel
    if not GRPC_AVAILABLE or grpc is None:
        raise ChinaGrpcError('缺少 grpcio 依赖。')
    with channel_lock:
        if community_channel is None:
            community_channel = grpc.secure_channel(GRPC_HOST, grpc.ssl_channel_credentials())
        channel = community_channel
    try:
        grpc.channel_ready_future(channel).result(timeout=max(1.0, float(timeout)))
        rpc = channel.unary_unary(
            f'/lanota_services.Community/{method}',
            request_serializer=lambda value: value,
            response_deserializer=lambda value: value,
        )
        return rpc(payload, timeout=max(1.0, float(timeout)))
    except Exception as exception_object:
        with channel_lock:
            if community_channel is channel:
                community_channel = None
                try:
                    channel.close()
                except Exception:
                    pass
        raise ChinaGrpcError(f'国服备用 API 请求失败：{exception_object}') from exception_object


def _query_profile(nano_id: str, timeout: float) -> dict[str, Any]:
    payload = _encode_varint(8) + _encode_varint(0) + _encode_string(2, nano_id)
    profiles = _parse_search_response(_call('SearchPlayer', payload, timeout))
    target = nano_id.casefold()
    for profile in profiles:
        if str(profile.get('nanoId', '')).casefold() == target:
            return profile
    if profiles:
        return profiles[0]
    raise ChinaGrpcError('备用 API 没有找到对应的国服玩家。')


def _query_records(nano_id: str, timeout: float) -> list[dict[str, Any]]:
    payload = _encode_string(1, nano_id)
    return _parse_record_response(_call('GetPlayerSongRecord', payload, timeout))


def _unknown_rank_counts() -> dict[str, str]:
    return {rank: UNKNOWN for rank in RANK_NAMES}


def rank_from_score(score: Any) -> str | None:
    """按 Portal 前端公开阈值由整数分数推导 Rank。"""
    try:
        score_value = int(score)
    except (TypeError, ValueError):
        return None
    if not 0 <= score_value <= 1_000_000:
        return None
    if score_value >= 980_000:
        return 'L'
    if score_value >= 950_000:
        return 'S'
    if score_value >= 900_000:
        return 'A'
    if score_value >= 700_000:
        return 'B'
    if score_value >= 600_000:
        return 'C'
    return 'D'


def _build_stats(records: list[dict[str, Any]], *, records_available: bool) -> dict[str, Any]:
    clear_counts: dict[str, int | str] = {str(index): 0 for index in range(6)}
    clear_by_diff: dict[str, dict[str, int | str]] = {}
    rank_counts: dict[str, int | str] = {rank: 0 for rank in RANK_NAMES}
    rank_by_diff: dict[str, dict[str, int | str]] = {}
    difficulty_breakdown: list[dict[str, int | str]] = []
    for record in records:
        clear = str(record.get('clear', ''))
        difficulty = str(record.get('difficulty', ''))
        if clear.isdigit():
            clear_counts[clear] = int(clear_counts.get(clear, 0)) + 1
        row = clear_by_diff.setdefault(difficulty, {str(index): 0 for index in range(6)})
        if clear.isdigit():
            row[clear] = int(row.get(clear, 0)) + 1
        rank = rank_from_score(record.get('score'))
        rank_row = rank_by_diff.setdefault(difficulty, {name: 0 for name in RANK_NAMES})
        if rank:
            rank_counts[rank] = int(rank_counts.get(rank, 0)) + 1
            rank_row[rank] = int(rank_row.get(rank, 0)) + 1
    if not records_available:
        for key in clear_counts:
            clear_counts[key] = UNKNOWN
        clear_by_diff = {str(index): {str(clear): UNKNOWN for clear in range(6)} for index in range(4)}
        rank_counts = _unknown_rank_counts()
        rank_by_diff = {str(index): _unknown_rank_counts() for index in range(4)}
        difficulty_breakdown = [
            {'difficulty': index, 'count': UNKNOWN, 'total': UNKNOWN}
            for index in range(4)
        ]
    else:
        difficulty_breakdown = [
            {
                'difficulty': index,
                'count': sum(1 for row in records if row.get('difficulty') == index),
                'total': UNKNOWN,
            }
            for index in range(4)
        ]
        for index in range(4):
            clear_by_diff.setdefault(str(index), {str(clear): 0 for clear in range(6)})
            rank_by_diff.setdefault(str(index), {name: 0 for name in RANK_NAMES})
    return {
        'totalSongsPlayed': len(records) if records_available else UNKNOWN,
        'totalCharts': UNKNOWN,
        'clearCounts': clear_counts,
        'rankCounts': rank_counts,
        'difficultyBreakdown': difficulty_breakdown,
        'clearByDiff': clear_by_diff,
        'rankByDiff': rank_by_diff,
    }


def _build_player_data(profile: dict[str, Any], records: list[dict[str, Any]], *, records_available: bool) -> dict[str, Any]:
    nano_id = str(profile.get('nanoId', '') or '')
    raw_rating = profile.get('rating')
    player = {
        'nanoId': nano_id,
        'username': profile.get('username') or UNKNOWN,
        'avatarId': profile.get('avatarId') or 'av_default',
        'rating': round(float(raw_rating), 2) if raw_rating is not None else UNKNOWN,
        'notalium': profile.get('notalium') if profile.get('notalium') is not None else UNKNOWN,
        'totalScore': profile.get('totalScore') if profile.get('totalScore') is not None else UNKNOWN,
    }
    return {
        '_portal_region': 'china',
        '_api_fallback': True,
        '_api_fallback_notice': '现已切换备用 API，部分字段暂无法获取；如需查询完整信息请联系管理员更新 Token。',
        'player': player,
        'stats': _build_stats(records, records_available=records_available),
        'songs': [
            {
                'songId': row.get('songId', ''),
                'difficulty': row.get('difficulty'),
                'score': row.get('score'),
                'clear': row.get('clear'),
            }
            for row in records
        ],
    }


def get_player(nano_id: str, timeout: float = 15) -> dict[str, Any]:
    """查询玩家卡片数据；资料成功但成绩失败时仍返回部分资料。"""
    clean_id = str(nano_id or '').strip()
    if not clean_id:
        raise ChinaGrpcError('好友码为空。')
    profile = _query_profile(clean_id, timeout)
    records = []
    records_available = True
    try:
        records = _query_records(clean_id, timeout)
    except Exception:
        records_available = False
    return _build_player_data(profile, records, records_available=records_available)


def get_compare(nano_id: str, timeout: float = 15) -> dict[str, Any]:
    """查询逐谱面成绩并转换为 Portal compare 兼容结构。"""
    clean_id = str(nano_id or '').strip()
    if not clean_id:
        raise ChinaGrpcError('好友码为空。')
    profile = _query_profile(clean_id, timeout)
    records = _query_records(clean_id, timeout)
    player_data = _build_player_data(profile, records, records_available=True)
    return {
        '_portal_region': 'china',
        '_api_fallback': True,
        '_api_fallback_notice': player_data['_api_fallback_notice'],
        'friend': player_data['player'],
        'songs': [
            {
                'songId': row.get('songId', ''),
                'difficulty': row.get('difficulty'),
                'friendScore': row.get('score'),
                'friendClear': row.get('clear'),
                'friendRank': rank_from_score(row.get('score')),
            }
            for row in records
        ],
    }


__all__ = [
    'ChinaGrpcError',
    'GRPC_AVAILABLE',
    'UNKNOWN',
    'get_compare',
    'get_player',
    'rank_from_score',
]
