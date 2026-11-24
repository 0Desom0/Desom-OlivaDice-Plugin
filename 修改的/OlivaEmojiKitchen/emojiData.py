# -*- encoding: utf-8 -*-
'''
@File      :   emojiData.py
@Author    :   lunzhiPenxil仑质 & 地窖上的松
@Contact   :   lunzhipenxil@gmail.com
@License   :   AGPL
@Copyright :   (C) 2020-2021, OlivOS-Team
@Desc      :   数据层。emoji 表与组合日期不再硬编码，改为读取
               plugin/data/OlivaEmojiKitchen/emojiData.json；
               该文件由定时任务每日自上游 metadata 生成，本模块按文件
               mtime 热加载，数据更新后无需重启插件。
'''

import json
import os
import sys
import threading

NAMESPACE = 'OlivaEmojiKitchen'
DATA_FILE_NAME = 'emojiData.json'

# 与 gstatic 图片路径一致的拼接模板：{date}/{u-left}/{u-left}_{u-right}.png
BASE_URL = 'https://www.gstatic.com/android/keyboard/emojikitchen/%s/%s/%s_%s.png'

# 单个 emoji 可能的最长码点序列（ZWJ 组合），用于前缀匹配上限
MAX_SEQUENCE = 16

# variation selector-16，用户输入常带、数据里可省
_VS16 = 0xFE0F

_lock = threading.RLock()
_cache = {
    'path': None,
    'version': None,
    'data': None,
}


def _candidate_paths():
    '''按优先级给出可能的数据文件路径。'''
    seen = set()
    roots = []
    env_root = os.environ.get('OLIVOS_ROOT')
    if env_root:
        roots.append(env_root)
    try:
        roots.append(os.getcwd())
    except OSError:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        roots.append(here)
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    # opk 插件加载后自身目录会被回收，退而用 OlivOS 包位置推断实例根目录
    olivos_module = sys.modules.get('OlivOS')
    olivos_file = getattr(olivos_module, '__file__', None) if olivos_module else None
    if olivos_file:
        roots.append(os.path.dirname(os.path.dirname(os.path.abspath(olivos_file))))
    for root in roots:
        path = os.path.join(root, 'plugin', 'data', NAMESPACE, DATA_FILE_NAME)
        path = os.path.normpath(path)
        if path in seen:
            continue
        seen.add(path)
        yield path


def _locate():
    for path in _candidate_paths():
        if os.path.isfile(path):
            return path
    return None


def _load(path):
    with open(path, 'r', encoding='utf-8') as fp:
        raw = json.load(fp)
    if not isinstance(raw, dict) or raw.get('schema') != 2:
        raise ValueError('emojiData.json schema 不受支持')
    emoji = raw.get('emoji') or {}
    combinations = raw.get('combinations') or {}
    if not isinstance(emoji, dict) or not isinstance(combinations, dict):
        raise ValueError('emojiData.json 结构异常')

    index = {}
    for codepoint, info in emoji.items():
        try:
            parts = tuple(int(item, 16) for item in str(codepoint).split('-'))
        except (TypeError, ValueError):
            continue
        normalized = tuple(item for item in parts if item != _VS16)
        if normalized and normalized not in index:
            index[normalized] = codepoint

    return {
        'emoji': emoji,
        'index': index,
        'combinations': combinations,
        'generated_at': raw.get('generated_at') or '',
        'emoji_count': len(emoji),
        'combination_count': len(combinations),
    }


def get_data():
    '''返回当前数据（按 mtime 热加载）；数据文件缺失或损坏时返回 None。'''
    path = _locate()
    if path is None:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    version = (stat.st_mtime_ns, stat.st_size)
    with _lock:
        if _cache['path'] == path and _cache['version'] == version and _cache['data'] is not None:
            return _cache['data']
        try:
            data = _load(path)
        except Exception:
            # 读取失败时宁可继续用上一份有效数据
            if _cache['path'] == path:
                return _cache['data']
            return None
        _cache['path'] = path
        _cache['version'] = version
        _cache['data'] = data
        return data


def find_emojis(message):
    '''在字符串中找出所有受支持的 emoji。

    返回 [(start, end, codepoint_str), ...]，start/end 为原字符串下标。
    匹配时忽略 variation selector，取最长前缀，保证 ZWJ 组合不被拆散。
    '''
    data = get_data()
    if not data:
        return []
    index = data['index']
    if not index:
        return []

    codepoints = [ord(item) for item in message]
    length_total = len(codepoints)
    found = []
    cursor = 0
    while cursor < length_total:
        limit = min(MAX_SEQUENCE, length_total - cursor)
        hit = None
        for length in range(limit, 0, -1):
            normalized = tuple(
                item for item in codepoints[cursor:cursor + length]
                if item != _VS16
            )
            if normalized and normalized in index:
                hit = (length, index[normalized])
                break
        if hit is not None:
            found.append((cursor, cursor + hit[0], hit[1]))
            cursor += hit[0]
        else:
            cursor += 1
    return found


def _url_part(codepoint):
    return 'u' + str(codepoint).replace('-', '-u')


def build_url(date, codepoint_left, codepoint_right):
    left = _url_part(codepoint_left)
    return BASE_URL % (date, left, left, _url_part(codepoint_right))


def resolve_url(codepoint_a, codepoint_b):
    '''查组合日期并拼出图片地址；不支持的组合返回 None。

    组合表里每对只存一个方向（方向决定图片里谁是左主体），
    所以先按原顺序查，再按交换顺序查。
    '''
    data = get_data()
    if not data:
        return None
    combinations = data['combinations']
    date = combinations.get(codepoint_a + '|' + codepoint_b)
    if date:
        return build_url(date, codepoint_a, codepoint_b)
    date = combinations.get(codepoint_b + '|' + codepoint_a)
    if date:
        return build_url(date, codepoint_b, codepoint_a)
    return None
