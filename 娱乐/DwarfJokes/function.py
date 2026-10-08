# -*- encoding: utf-8 -*-
"""矮人笑话合集的读写、抽选、重复度检验与贪婪命令匹配。"""

import os
import random
import re
import shutil
import threading
from typing import Any, Dict, Iterable, List, Optional

from . import config
from . import utils

function_module_note = '矮人笑话合集管理模块。'

try:
    import OlivaDiceCore
except Exception:
    OlivaDiceCore = None

draw_count_pattern = re.compile(r'^-?\d+$')
joke_pack_lock = threading.RLock()
joke_pack_cache = {
    'path': '',
    'mtime': None,
    'jokes': [],
}


def match_greedy_command(
    source_text: str,
    command_name: Any,
    ignore_case: bool = True,
) -> Dict[str, Any]:
    """用模板 parse_command 做无前缀贪婪匹配，不按空格切词。"""
    return utils.parse_command(
        source_text,
        prefix_list=[],
        allow_no_prefix=True,
        command_name=command_name,
        ignore_case=ignore_case,
    )


def parse_draw_count(argument_text: str) -> Optional[int]:
    """纯数字参数才视为抽取条数；超出 1-10 时夹紧。"""
    stripped_text = utils.safe_str(argument_text).strip()
    if not draw_count_pattern.fullmatch(stripped_text):
        return None
    try:
        draw_count = int(stripped_text)
    except Exception:
        return None
    if draw_count > config.draw_count_max:
        return config.draw_count_max
    if draw_count < config.draw_count_min:
        return config.draw_count_min
    return draw_count


def get_bundled_joke_pack_path() -> str:
    """插件自带的种子合集，只读，位于插件目录 Data/ 下。"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        config.joke_pack_seed_folder_name,
        config.joke_pack_file_name,
    )


def get_joke_pack_path() -> str:
    """运行时全局合集路径：plugin/data/DwarfJokes/DwarfJokesPack.json。"""
    utils.ensure_folder(config.plugin_data_dir)
    return os.path.join(config.plugin_data_dir, config.joke_pack_file_name)


def get_local_recommend_rank(word1_in: str, word2_in: str, gate_rank: int = 1000, rate: float = 1.0) -> int:
    """复刻 OlivaDiceCore.helpDoc.getRecommendRank，无 Core 时作为回退。"""
    word1 = word1_in.lower()
    word2 = word2_in.lower()
    if not word1 or not word2:
        return gate_rank + 1
    if len(word1) > len(word2):
        word1, word2 = word2, word1

    len1 = len(word1)
    len2 = len(word2)
    if word2.find(word1) != -1:
        return 0

    prev_lcs = [0] * (len1 + 1)
    prev_ed = list(range(len1 + 1))
    for j in range(1, len2 + 1):
        ch2 = word2[j - 1]
        cur_lcs = [0] * (len1 + 1)
        cur_ed = [0] * (len1 + 1)
        cur_ed[0] = j
        for i in range(1, len1 + 1):
            if word1[i - 1] == ch2:
                cur_lcs[i] = prev_lcs[i - 1] + 1
                cur_ed[i] = prev_ed[i - 1]
            else:
                cur_lcs[i] = max(prev_lcs[i], cur_lcs[i - 1])
                cur_ed[i] = min(prev_ed[i - 1], prev_ed[i], cur_ed[i - 1]) + 1
        prev_lcs = cur_lcs
        prev_ed = cur_ed

    i_rank_1 = prev_lcs[len1]
    i_rank_2 = prev_ed[len1]
    i_rank = len2 * (len1 - i_rank_1) + i_rank_2 + 1
    i_rank = (i_rank * i_rank) // len1 // len2
    if i_rank >= int(len1 * len2 * rate):
        i_rank += gate_rank
    return i_rank


def get_recommend_rank(word1: str, word2: str) -> int:
    """优先调用 OlivaDiceCore 的帮助文档参考度算法。"""
    if OlivaDiceCore is not None:
        try:
            return int(OlivaDiceCore.helpDoc.getRecommendRank(word1, word2))
        except Exception:
            pass
    return get_local_recommend_rank(word1, word2)


def normalize_joke_item(raw_item: Any) -> Optional[Dict[str, Any]]:
    """把合集条目清洗成统一结构，无法识别时丢弃。"""
    if not isinstance(raw_item, dict):
        return None
    try:
        joke_id = int(raw_item.get('id'))
    except Exception:
        return None
    if joke_id < 1:
        return None
    text = utils.safe_str(raw_item.get('text', '')).strip()
    if not text:
        return None
    return {
        'id': joke_id,
        'text': text,
        'original_en': utils.safe_str(raw_item.get('original_en', '')),
        'category': utils.safe_str(raw_item.get('category', '')),
        'platform': utils.safe_str(raw_item.get('platform', '')),
        'source_url': utils.safe_str(raw_item.get('source_url', '')),
        'note': utils.safe_str(raw_item.get('note', '')),
    }


def make_joke_item(joke_id: int, text: str) -> Dict[str, Any]:
    """命令新增条目：只写入 text，其余字段留空。"""
    return {
        'id': int(joke_id),
        'text': utils.safe_str(text).strip(),
        'original_en': '',
        'category': '',
        'platform': '',
        'source_url': '',
        'note': '',
    }


def normalize_joke_list(raw_data: Any) -> List[Dict[str, Any]]:
    """合集必须是列表；重复 id 保留先出现的一条。"""
    if not isinstance(raw_data, list):
        return []
    joke_list = []
    seen_id_set = set()
    for raw_item in raw_data:
        joke_item = normalize_joke_item(raw_item)
        if joke_item is None:
            continue
        if joke_item['id'] in seen_id_set:
            continue
        seen_id_set.add(joke_item['id'])
        joke_list.append(joke_item)
    joke_list.sort(key=lambda item: item['id'])
    return joke_list


def get_next_joke_id(joke_list: Iterable[Dict[str, Any]]) -> int:
    """优先填补空缺序号，再继续自增。"""
    used_id_set = set()
    for joke_item in joke_list:
        try:
            used_id_set.add(int(joke_item['id']))
        except Exception:
            continue
    candidate = 1
    while candidate in used_id_set:
        candidate += 1
    return candidate


def copy_seed_joke_pack(Proc=None) -> bool:
    """运行时合集不存在时，从插件 Data 目录搬运种子文件。"""
    runtime_path = get_joke_pack_path()
    if os.path.exists(runtime_path):
        return True
    seed_path = get_bundled_joke_pack_path()
    try:
        if os.path.isfile(seed_path):
            shutil.copy2(seed_path, runtime_path)
            utils.info_log(Proc, f'已从插件种子合集复制 DwarfJokesPack.json 到 {runtime_path}')
            return True
    except Exception as exception_object:
        utils.error_log(Proc, f'复制矮人笑话种子合集失败：{type(exception_object).__name__}')
    return utils.save_json_file(runtime_path, [])


def ensure_joke_pack_initialized(Proc=None) -> str:
    """保证运行时全局合集文件存在，并返回路径。"""
    runtime_path = get_joke_pack_path()
    copy_seed_joke_pack(Proc)
    if not os.path.exists(runtime_path):
        utils.save_json_file(runtime_path, [])
    return runtime_path


def load_joke_pack(force_reload: bool = False) -> List[Dict[str, Any]]:
    """读取全局笑话合集，按文件修改时间做内存缓存。"""
    runtime_path = ensure_joke_pack_initialized()
    with joke_pack_lock:
        mtime = None
        try:
            mtime = os.path.getmtime(runtime_path)
        except Exception:
            mtime = None
        cache_hit = (
            not force_reload
            and joke_pack_cache['path'] == runtime_path
            and joke_pack_cache['mtime'] == mtime
            and isinstance(joke_pack_cache['jokes'], list)
        )
        if cache_hit:
            return [dict(item) for item in joke_pack_cache['jokes']]

        raw_data = utils.read_json_file(runtime_path, [])
        joke_list = normalize_joke_list(raw_data)
        joke_pack_cache['path'] = runtime_path
        joke_pack_cache['mtime'] = mtime
        joke_pack_cache['jokes'] = [dict(item) for item in joke_list]
        return [dict(item) for item in joke_list]


def save_joke_pack(joke_list: List[Dict[str, Any]]) -> bool:
    """保存合集并刷新缓存。"""
    runtime_path = get_joke_pack_path()
    normalized_list = normalize_joke_list(joke_list)
    saved = utils.save_json_file(runtime_path, normalized_list)
    if not saved:
        return False
    with joke_pack_lock:
        mtime = None
        try:
            mtime = os.path.getmtime(runtime_path)
        except Exception:
            mtime = None
        joke_pack_cache['path'] = runtime_path
        joke_pack_cache['mtime'] = mtime
        joke_pack_cache['jokes'] = [dict(item) for item in normalized_list]
    return True


def get_joke_pack_summary() -> Dict[str, Any]:
    """给 GUI / WebUI 用的合集摘要，不回传全部正文。"""
    joke_list = load_joke_pack()
    joke_id_list = [int(item['id']) for item in joke_list]
    return {
        'count': len(joke_list),
        'next_id': get_next_joke_id(joke_list),
        'max_id': max(joke_id_list) if joke_id_list else 0,
        'path': os.path.abspath(get_joke_pack_path()),
        'duplicate_rank_gate': config.joke_duplicate_rank_gate,
    }


def get_joke_by_id(joke_id: int) -> Optional[Dict[str, Any]]:
    """按序号取一条笑话。"""
    for joke_item in load_joke_pack():
        if int(joke_item['id']) == int(joke_id):
            return dict(joke_item)
    return None


def find_duplicate_joke(
    joke_text: str,
    joke_list: Optional[List[Dict[str, Any]]] = None,
    exclude_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    按 OlivaDiceCore 帮助文档参考度打分。
    分数越低越像；低于 joke_duplicate_rank_gate（默认 50）判定为重复。
    """
    source_text = utils.safe_str(joke_text).strip()
    if not source_text:
        return None
    current_list = joke_list if isinstance(joke_list, list) else load_joke_pack()
    best_match = None
    for joke_item in current_list:
        try:
            joke_id = int(joke_item['id'])
        except Exception:
            continue
        if exclude_id is not None and joke_id == int(exclude_id):
            continue
        existing_text = utils.safe_str(joke_item.get('text', '')).strip()
        if not existing_text:
            continue
        rank = get_recommend_rank(source_text, existing_text)
        if rank >= config.joke_duplicate_rank_gate:
            continue
        if (
            best_match is None
            or rank < best_match['rank']
            or (rank == best_match['rank'] and joke_id < best_match['id'])
        ):
            best_match = {
                'id': joke_id,
                'rank': rank,
                'text': existing_text,
            }
    return best_match


def add_joke(joke_text: str) -> Dict[str, Any]:
    """新增笑话：填补空缺序号，并做重复度检验。"""
    text = utils.safe_str(joke_text).strip()
    if not text:
        return {'ok': False, 'reason': 'empty'}
    if len(text) > config.joke_text_max_length:
        return {
            'ok': False,
            'reason': 'too_long',
            'max_length': config.joke_text_max_length,
        }

    with joke_pack_lock:
        joke_list = load_joke_pack(force_reload=True)
        duplicate = find_duplicate_joke(text, joke_list)
        if duplicate is not None:
            return {
                'ok': False,
                'reason': 'duplicate',
                'id': duplicate['id'],
                'rank': duplicate['rank'],
                'count': len(joke_list),
            }
        joke_id = get_next_joke_id(joke_list)
        joke_list.append(make_joke_item(joke_id, text))
        if not save_joke_pack(joke_list):
            return {'ok': False, 'reason': 'save_failed'}
        return {
            'ok': True,
            'id': joke_id,
            'count': len(joke_list),
            'text': text,
        }


def delete_joke(joke_id: Any) -> Dict[str, Any]:
    """按序号删除笑话，空出来的序号留给后续新增填补。"""
    try:
        target_id = int(joke_id)
    except Exception:
        return {'ok': False, 'reason': 'invalid_id'}
    if target_id < 1:
        return {'ok': False, 'reason': 'invalid_id'}

    with joke_pack_lock:
        joke_list = load_joke_pack(force_reload=True)
        remaining_list = [item for item in joke_list if int(item['id']) != target_id]
        if len(remaining_list) == len(joke_list):
            return {
                'ok': False,
                'reason': 'missing',
                'id': target_id,
                'count': len(joke_list),
            }
        if not save_joke_pack(remaining_list):
            return {'ok': False, 'reason': 'save_failed', 'id': target_id}
        return {
            'ok': True,
            'id': target_id,
            'count': len(remaining_list),
        }


def draw_jokes(draw_count: int = 1) -> Dict[str, Any]:
    """随机抽取指定条数，同一轮不重复。"""
    try:
        normalized_count = int(draw_count)
    except Exception:
        normalized_count = config.draw_count_min
    if normalized_count > config.draw_count_max:
        normalized_count = config.draw_count_max
    if normalized_count < config.draw_count_min:
        normalized_count = config.draw_count_min

    joke_list = load_joke_pack()
    if not joke_list:
        return {'ok': False, 'reason': 'empty_pack', 'count': 0, 'jokes': []}
    sample_size = min(normalized_count, len(joke_list))
    selected_list = random.sample(joke_list, sample_size)
    selected_list.sort(key=lambda item: item['id'])
    return {
        'ok': True,
        'requested': normalized_count,
        'count': len(joke_list),
        'jokes': selected_list,
    }


def format_joke_line(joke_item: Dict[str, Any], with_index: bool = False, index: int = 1) -> str:
    """把一条笑话格式化成回复文本。"""
    joke_id = joke_item.get('id', '?')
    joke_text = utils.safe_str(joke_item.get('text', '')).strip()
    if with_index:
        return f'{index}. [#{joke_id}] {joke_text}'
    return f'【矮人笑话 #{joke_id}】\n{joke_text}'


def format_draw_result(draw_result: Dict[str, Any]) -> str:
    """组织抽选结果回复。"""
    joke_list = draw_result.get('jokes') or []
    if not joke_list:
        return '当前没有可抽取的矮人笑话。'
    if len(joke_list) == 1:
        return format_joke_line(joke_list[0])
    line_list = [
        format_joke_line(joke_item, with_index=True, index=index)
        for index, joke_item in enumerate(joke_list, start=1)
    ]
    return f'【矮人笑话 x{len(joke_list)}】\n' + '\n'.join(line_list)
