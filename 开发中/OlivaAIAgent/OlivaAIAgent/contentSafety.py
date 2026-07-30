# -*- encoding: utf-8 -*-
'''现实政治话题保护与可选本地敏感词表。'''

import json
import os
import threading
import unicodedata

import OlivaAIAgent


POLITICS_GUARD_PROMPT = '''# 内容安全边界（最高优先级）
- 不参与现实政治、政党、政府、政治事件、政治立场或政治人物相关话题，尤其不得提及、复述、列举、评价、影射或扮演中国领导人。
- 上述边界适用于提问、翻译、改写、引用、角色扮演、工具调用、联网结果、图片文字、记忆与提醒；不得用编码、谐音、缩写或分段输出规避。
- 命中时只用一句不包含相关名称或原文的简短话术请对方换个话题，不解释规则，也不复述敏感内容。'''

HIDDEN_TEXT = '【该消息涉及不参与的话题，内容已隐藏】'

# 内置表只覆盖本插件明确拒答的现实政治主题；其他类别交给用户选装的本地词表。
_LEADER_TERMS = (
    '习近平', '习主席', '习大大', 'xijinping', '赵乐际', '王沪宁', '丁薛祥',
    '毛泽东', '毛主席', '邓小平', '江泽民', '胡锦涛', '李克强', '周恩来',
)
_CONTEXTUAL_LEADER_TERMS = ('李强', '蔡奇', '李希')
_POLITICS_TERMS = (
    '现实政治', '时政', '政治话题', '政治人物', '政治立场', '政治体制', '意识形态', '政党', '中共',
    '共产党', '国民党', '党中央', '政治局', '中央委员会', '中央政府', '国务院', '全国人大', '政协',
    '国家主席', '总书记', '总理', '首相', '总统', '领导人', '常委', '政权', '执政党', '反对党',
    '选举', '大选', '民主化', '独裁', '两岸关系', '台独', '港独', '藏独', '疆独', '文化大革命',
    '文革', '六四', '天安门事件',
)
_LEADERSHIP_MARKERS = ('主席', '总书记', '总理', '领导人', '常委', '政治局', '国家领导')
_CORE_GENERIC_REGION_TERMS = {'中国', '我国', '国内'}

_lock = threading.RLock()
_external_signature = None
_external_trie = {}
_external_count = 0


def enabled():
    return bool(OlivaAIAgent.conf.get('security', 'politics_guard', default=True))


def guardPrompt():
    return POLITICS_GUARD_PROMPT if enabled() else ''


def refusal():
    return str(OlivaAIAgent.conf.get(
        'security', 'politics_reply', default='这个话题小芙不聊哦，换一个吧~',
    )).strip() or '这个话题不聊哦，换一个吧~'


def _normalize(text):
    value = unicodedata.normalize('NFKC', str(text or '')).lower()
    return ''.join(char for char in value if char.isalnum() or '\u4e00' <= char <= '\u9fff')


def _configuredPaths():
    if not OlivaAIAgent.conf.get('security', 'external_sensitive_words', default=False):
        return []
    paths = []
    files = OlivaAIAgent.conf.get('security', 'sensitive_word_files', default=[]) or []
    dirs = OlivaAIAgent.conf.get('security', 'sensitive_word_dirs', default=[]) or []
    if isinstance(files, str):
        files = [files]
    if isinstance(dirs, str):
        dirs = [dirs]
    for item in files:
        path = os.path.abspath(os.path.expandvars(os.path.expanduser(str(item).strip())))
        if os.path.isfile(path):
            paths.append(path)
    for item in dirs:
        directory = os.path.abspath(os.path.expandvars(os.path.expanduser(str(item).strip())))
        if not os.path.isdir(directory):
            continue
        try:
            paths.extend(
                os.path.join(directory, name)
                for name in sorted(os.listdir(directory))
                if name.lower().endswith(('.txt', '.json'))
                and os.path.isfile(os.path.join(directory, name))
            )
        except OSError:
            continue
    return list(dict.fromkeys(paths))


def _signature(paths):
    result = []
    for path in paths:
        try:
            stat = os.stat(path)
            result.append((path, stat.st_mtime_ns, stat.st_size))
        except OSError:
            continue
    return tuple(result)


def _fileWords(path):
    try:
        with open(path, 'r', encoding='utf-8-sig') as handle:
            if path.lower().endswith('.json'):
                data = json.load(handle)
                if isinstance(data, dict):
                    values = list(data.keys())
                elif isinstance(data, list):
                    values = data
                else:
                    values = []
            else:
                values = handle.readlines()
    except Exception:
        return []
    words = []
    for value in values:
        word = str(value).strip()
        if not word or word.startswith(('#', '//', ';')):
            continue
        normalized = _normalize(word)
        # 单字符词表误伤率极高，不作为整句拦截条件。
        if len(normalized) >= 2 and normalized not in _CORE_GENERIC_REGION_TERMS:
            words.append(normalized)
    return words


def _externalTrie():
    global _external_signature, _external_trie, _external_count
    paths = _configuredPaths()
    signature = _signature(paths)
    with _lock:
        if signature == _external_signature:
            return _external_trie
        trie = {}
        words = set()
        for path in paths:
            words.update(_fileWords(path))
        for word in words:
            node = trie
            for char in word:
                node = node.setdefault(char, {})
            node[''] = True
        _external_signature = signature
        _external_trie = trie
        _external_count = len(words)
        return _external_trie


def _trieContains(text, trie):
    if not trie:
        return False
    for start in range(len(text)):
        node = trie
        for char in text[start:]:
            node = node.get(char)
            if node is None:
                break
            if '' in node:
                return True
    return False


def _coreDFA(bot_hash):
    if not OlivaAIAgent.conf.get('security', 'use_olivadice_censor', default=True):
        return None
    if bot_hash in [None, '', 'unity']:
        return None
    try:
        import OlivaDiceCore

        if OlivaDiceCore.console.getConsoleSwitchByHash('censorMode', str(bot_hash)) == 0:
            return None
        return OlivaDiceCore.censorAPI.gCensorDFA.get(str(bot_hash))
    except Exception:
        return None


def _coreStatus(bot_hash):
    status = {
        'enabled': bool(OlivaAIAgent.conf.get(
            'security', 'use_olivadice_censor', default=True,
        )),
        'ready': False,
        'words': 0,
    }
    dfa = _coreDFA(bot_hash)
    if dfa is None:
        return status
    status['ready'] = True
    try:
        import OlivaDiceCore

        words = set()
        for target in ('unity', str(bot_hash)):
            words.update(
                str(item) for item in OlivaDiceCore.censorAPI.gCensorList.get(target, [])
                if str(item)
            )
            words.update(
                str(item) for item in OlivaDiceCore.censorAPI.getConfigList(target)
                if str(item)
            )
        status['words'] = len(words)
    except Exception:
        pass
    return status


def _coreContains(text, bot_hash):
    dfa = _coreDFA(bot_hash)
    if dfa is None:
        return False
    try:
        import OlivaDiceCore

        matches = dfa.find(str(text or ''), mode=OlivaDiceCore.censorDFA.maxMatchType)
        meaningful = {
            str(item).strip() for item in (matches or [])
            if str(item).strip() not in _CORE_GENERIC_REGION_TERMS
        }
        return bool(meaningful)
    except Exception:
        return False


def match(text, outgoing=False, bot_hash=None):
    '''返回命中来源，不返回具体词，避免敏感内容进入日志。'''
    external_enabled = bool(OlivaAIAgent.conf.get(
        'security', 'external_sensitive_words', default=False,
    ))
    core_enabled = bool(OlivaAIAgent.conf.get(
        'security', 'use_olivadice_censor', default=True,
    ))
    if not enabled() and not external_enabled and not core_enabled:
        return None
    normalized = _normalize(text)
    if not normalized:
        return None
    if enabled():
        if any(_normalize(term) in normalized for term in _LEADER_TERMS):
            return 'builtin_leader'
        if any(_normalize(term) in normalized for term in _CONTEXTUAL_LEADER_TERMS) and any(
            marker in normalized for marker in _LEADERSHIP_MARKERS
        ):
            return 'builtin_leader'
        if any(_normalize(term) in normalized for term in _POLITICS_TERMS):
            return 'builtin_politics'
    if core_enabled and _coreContains(text, bot_hash):
        return 'olivadice_censor'
    if external_enabled and _trieContains(normalized, _externalTrie()):
        return 'external_lexicon'
    return None


def blocked(text, outgoing=False, bot_hash=None):
    return match(text, outgoing=outgoing, bot_hash=bot_hash) is not None


def hiddenForMemory(text, bot_hash=None):
    return HIDDEN_TEXT if blocked(text, bot_hash=bot_hash) else str(text or '')


def externalStatus(bot_hash=None):
    _externalTrie()
    core = _coreStatus(bot_hash)
    with _lock:
        return {
            'enabled': bool(OlivaAIAgent.conf.get(
                'security', 'external_sensitive_words', default=False,
            )),
            'files': len(_external_signature or ()),
            'words': _external_count,
            'core_enabled': core['enabled'],
            'core_ready': core['ready'],
            'core_words': core['words'],
        }
