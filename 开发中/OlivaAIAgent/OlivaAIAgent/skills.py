# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 技能库子系统（Codex Skills 检索，移植并增强自刺客 skillManagerV3）
- 递归扫描 data/OlivaAIAgent/skills/ 下的 SKILL.md（含 frontmatter: name/description/aliases/keywords/triggers）
- 引用的 references/ assets/ 资料一并纳入，按 Markdown 标题切段
- 检索: 若安装了 rank_bm25 + jieba 则用 BM25；否则回退到纯 Python 词频/子串打分（无需任何 pip 依赖）
- 命中片段注入到对话上下文，让 AI 依据规则书/资料回答
比刺客更强: BM25 缺失时自动降级而非报错，且检索词表可扩展。
'''

import hashlib
import json
import os
import re
import threading
import time

import OlivaAIAgent

try:
    import jieba
    _HAS_JIEBA = True
except Exception:
    jieba = None
    _HAS_JIEBA = False

try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except Exception:
    BM25Okapi = None
    _HAS_BM25 = False

try:
    import translators as _translators
    _HAS_TRANSLATORS = True
except Exception:
    _translators = None
    _HAS_TRANSLATORS = False

_translation_cache = {}
_pcache = None                  # 持久翻译缓存(跨重启)，惰性加载
_pcache_lock = threading.Lock()
_pending_lock = threading.Lock()
_pending_foreign = []           # 待翻译元数据的纯外文技能名
_build_gen = 0                  # 索引代数：重建后旧翻译线程自动作废
_AUTO_ASYNC = True              # 构建后自动后台翻译(测试可关以保证确定性)

_REF_RE = re.compile(r'`?((?:references?|assets)/[^`\s)]+\.(?:md|txt))`?', re.I)
_HEAD_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.M)
_LATIN_RE = re.compile(r'[a-z][a-z0-9_.+/-]*', re.I)
_CJK_RE = re.compile(r'[㐀-鿿]')
_SPACE_RE = re.compile(r'\s+')

_index = {}
_query_cache = {}


def _llmReady():
    '''是否可用已配置的 AI 后端做一次性翻译(api_key 已填)。'''
    try:
        backend = str(OlivaAIAgent.conf.get('backend', default='openai'))
        return str(OlivaAIAgent.conf.get(backend, 'api_key', default='')) != ''
    except Exception:
        return False


def _pcachePath():
    return os.path.join(OlivaAIAgent.conf.dataPath, 'skills_translation_cache.json')


def _pcacheLoad():
    global _pcache
    with _pcache_lock:
        if _pcache is None:
            try:
                with open(_pcachePath(), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                _pcache = data if isinstance(data, dict) else {}
            except Exception:
                _pcache = {}
        return _pcache


def _pcacheGet(key):
    return _pcacheLoad().get(key)


def _pcacheSet(key, val):
    cache = _pcacheLoad()
    with _pcache_lock:
        cache[key] = val
        try:
            os.makedirs(os.path.dirname(_pcachePath()), exist_ok=True)
            with open(_pcachePath(), 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)
        except Exception:
            pass


def backendName():
    base = 'BM25' if (_HAS_BM25 and _HAS_JIEBA) else 'lite(纯Python)'
    if _HAS_TRANSLATORS:
        base += '+译'
    elif OlivaAIAgent.conf.get('skills', 'translate_skill_meta', default=True) \
            and OlivaAIAgent.conf.get('skills', 'translate_meta_use_llm', default=True) \
            and _llmReady():
        base += '+译(AI后端)'
    return base


def _translateForeignQuery(text):
    '''把"外文(不含中文)提问"翻成中文，帮外语群友命中中文技能库。
    - 仅在装了 translators 且开关开启时生效；未装/未开 → 返回 '' 自动跳过(不报错、不联网)。
    - 含中文的提问永不翻译(中文提问直接匹配中文技能/frontmatter 关键词)。
    - 英文技能库无需本功能：模型直读英文、检索靠 frontmatter 关键词。本功能只补"外文提问→中文技能"这一反向场景。'''
    if not _HAS_TRANSLATORS:
        return ''
    if not OlivaAIAgent.conf.get('skills', 'translate_foreign_query', default=True):
        return ''
    text = str(text or '')
    if _CJK_RE.search(text) or not _LATIN_RE.search(text):
        return ''
    key = text.strip()[:200]
    if key in _translation_cache:
        return _translation_cache[key]
    cached = _pcacheGet('q:' + key)
    if isinstance(cached, str):
        _translation_cache[key] = cached
        return cached
    to_lang = str(OlivaAIAgent.conf.get('skills', 'translate_to', default='zh'))
    from_lang = str(OlivaAIAgent.conf.get('skills', 'translate_from', default='auto'))
    backend = str(OlivaAIAgent.conf.get('skills', 'translate_backend', default='bing'))
    timeout = float(OlivaAIAgent.conf.get('skills', 'translate_timeout', default=2.0))
    box = []

    def _worker():
        try:
            box.append(_translators.translate_text(
                text, translator=backend, from_language=from_lang,
                to_language=to_lang, timeout=timeout) or '')
        except Exception:
            box.append('')

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    th.join(max(0.1, timeout))
    out = box[0] if box else ''
    _translation_cache[key] = out
    _capCache(_translation_cache, 4000)
    if out:
        _pcacheSet('q:' + key, out)
    return out


def _translateQueryToForeign(text):
    '''中文提问 → 外文(默认英文)，帮中文群友命中"纯外文技能"的英文正文。
    仅当 装了 translators + 开关开启 + 索引里确有外文技能 时才触发；否则零开销跳过。'''
    if not _HAS_TRANSLATORS:
        return ''
    if not OlivaAIAgent.conf.get('skills', 'translate_query_to_foreign', default=True):
        return ''
    text = str(text or '')
    if not _CJK_RE.search(text):
        return ''
    if not any(e.get('_foreign') for e in _index.values()):
        return ''
    key = 'q2:' + text.strip()[:200]
    if key in _translation_cache:
        return _translation_cache[key]
    cached = _pcacheGet(key)
    if isinstance(cached, str):
        _translation_cache[key] = cached
        return cached
    to_lang = str(OlivaAIAgent.conf.get('skills', 'translate_query_to', default='en'))
    backend = str(OlivaAIAgent.conf.get('skills', 'translate_backend', default='bing'))
    timeout = float(OlivaAIAgent.conf.get('skills', 'translate_timeout', default=2.0))
    box = []

    def _worker():
        try:
            box.append(_translators.translate_text(
                text, translator=backend, from_language='auto',
                to_language=to_lang, timeout=timeout) or '')
        except Exception:
            box.append('')

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    th.join(max(0.1, timeout))
    out = box[0] if box else ''
    _translation_cache[key] = out
    _capCache(_translation_cache, 4000)
    if out:
        _pcacheSet(key, out)
    return out


def _translateSkillMeta(name, description, metaterms, headings):
    '''纯外文技能的 元数据(名/描述/关键词/章节标题) → 中文。按内容哈希永久缓存(跨重启零成本)。
    渠道1: translators 库(免费无 token)；渠道2: 已配置的 AI 后端(一次性小请求)；都没有 → None。'''
    headings = [h for h in dict.fromkeys(str(x) for x in headings) if h][:40]
    src_lines = [str(name), str(description), str(metaterms)] + headings
    key = 'm:' + hashlib.md5('\n'.join(src_lines).encode('utf-8')).hexdigest()
    cached = _pcacheGet(key)
    if isinstance(cached, dict):
        return cached
    result = None
    if _HAS_TRANSLATORS:
        try:
            to_lang = str(OlivaAIAgent.conf.get('skills', 'translate_to', default='zh'))
            backend = str(OlivaAIAgent.conf.get('skills', 'translate_backend', default='bing'))
            timeout = max(5.0, float(OlivaAIAgent.conf.get('skills', 'translate_timeout', default=2.0)))
            out = _translators.translate_text(
                '\n'.join(src_lines), translator=backend, from_language='auto',
                to_language=to_lang, timeout=timeout) or ''
            lines = [ln.strip() for ln in out.split('\n')]
            hmap = {}
            if len(lines) == len(src_lines):
                hmap = {h: z for h, z in zip(headings, lines[3:]) if z}
            if out.strip():
                result = {'meta_zh': ' '.join(lines[:3]) if len(lines) >= 3 else out.strip(),
                          'headings_zh': hmap}
        except Exception:
            result = None
    if result is None \
            and OlivaAIAgent.conf.get('skills', 'translate_meta_use_llm', default=True) \
            and _llmReady():
        try:
            numbered = '\n'.join('%d|%s' % (i + 1, ln) for i, ln in enumerate(src_lines))
            timeout = float(OlivaAIAgent.conf.get('skills', 'translate_meta_llm_timeout', default=30.0))
            resp = OlivaAIAgent.aiClient.chat(
                [{'role': 'system',
                  'content': '你是翻译器。把用户给出的技能库元数据逐行翻译成简体中文，'
                             '严格保持"序号|译文"格式且行数与输入一致，不要输出任何解释。'},
                 {'role': 'user', 'content': numbered}],
                force_no_stream=True, thinking_off=True, timeout_override=timeout)
            text = str(resp.get('text', '')) if (resp and resp.get('ok')) else ''
            mapping = {}
            for m in re.finditer(r'^\s*(\d+)\s*\|\s*(.*?)\s*$', text, re.M):
                mapping[int(m.group(1))] = m.group(2)
            if mapping:
                meta_zh = ' '.join(mapping.get(i, '') for i in (1, 2, 3)).strip()
                hmap = {h: mapping[i + 4] for i, h in enumerate(headings)
                        if (i + 4) in mapping and mapping[i + 4]}
                result = {'meta_zh': meta_zh, 'headings_zh': hmap}
        except Exception:
            result = None
    if result is not None:
        _pcacheSet(key, result)
    return result


def _applyMetaZh(entry, tr):
    '''把翻译结果并入检索词表：route tokens、declared 加权、每个 chunk 的中文标题。'''
    hz = tr.get('headings_zh') or {}
    entry['zh_meta'] = str(tr.get('meta_zh', ''))
    for c in entry['chunks']:
        z = hz.get(c['heading'])
        if z:
            c['zh_heading'] = z
    zh_join = '%s %s' % (entry['zh_meta'], ' '.join(hz.values()))
    entry['route_tokens'] = list(dict.fromkeys(entry['route_tokens'] + _tokens(zh_join)))
    if _HAS_BM25:
        cdocs = [_tokens('%s %s %s' % (c['heading'], c.get('zh_heading', ''), c['text']))
                 for c in entry['chunks']]
        entry['_chunk_docs'] = cdocs
        entry['_chunk_bm25'] = BM25Okapi(cdocs) if cdocs and any(cdocs) else None


def _rebuildRouteBM25():
    if not _HAS_BM25 or not _index:
        return
    entries = list(_index.values())
    docs = [e['route_tokens'] for e in entries]
    route = BM25Okapi(docs) if any(docs) else None
    for e in entries:
        e['_route_bm25'] = route
        e['_route_entries'] = entries


def _processPending(gen):
    '''翻译待处理的纯外文技能元数据并应用；索引重建(代数变化)则自动作废。返回应用数。'''
    done = 0
    while True:
        with _pending_lock:
            if gen != _build_gen or not _pending_foreign:
                break
            name = _pending_foreign.pop(0)
        entry = _index.get(name)
        if entry is None:
            continue
        try:
            tr = _translateSkillMeta(entry['name'], entry['description'],
                                     entry['metadata_terms'],
                                     [c['heading'] for c in entry['chunks']])
        except Exception:
            tr = None
        if tr and gen == _build_gen:
            _applyMetaZh(entry, tr)
            done += 1
    if done:
        _rebuildRouteBM25()
        _query_cache.clear()
        OlivaAIAgent.conf.debugLog(OlivaAIAgent.conf.gProc,
                                   '[Skills] 外文技能元数据翻译并入索引: %d 个' % done)
    return done


def translateForeignMetaNow():
    '''同步处理全部待翻译外文技能(手动/测试用)；平时由构建后的后台线程自动完成。'''
    return _processPending(_build_gen)


def _read(path):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return f.read()
    except Exception:
        return ''


def _frontmatter(text):
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n?', text, re.S)
    if not m:
        return {}, text
    meta = {}
    # 极简 YAML: key: value / key: [a, b] / 多行 list（- item）
    try:
        import yaml
        meta = yaml.safe_load(m.group(1)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = _mini_yaml(m.group(1))
    return meta, text[m.end():]


def _mini_yaml(block):
    res = {}
    cur_key = None
    for line in block.splitlines():
        if not line.strip():
            continue
        m = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
        if m:
            cur_key = m.group(1).strip()
            val = m.group(2).strip()
            if val.startswith('[') and val.endswith(']'):
                res[cur_key] = [x.strip().strip('"\'') for x in val[1:-1].split(',') if x.strip()]
            elif val:
                res[cur_key] = val.strip('"\'')
            else:
                res[cur_key] = []
        elif line.lstrip().startswith('-') and cur_key is not None:
            item = line.lstrip()[1:].strip().strip('"\'')
            if isinstance(res.get(cur_key), list):
                res[cur_key].append(item)
            else:
                res[cur_key] = [item]
    return res


def _tokens(text):
    normalized = _SPACE_RE.sub(' ', str(text or '').lower()).strip()
    tokens = []
    if _HAS_JIEBA:
        tokens = [t.strip() for t in jieba.cut_for_search(normalized) if t.strip()]
    tokens.extend(_LATIN_RE.findall(normalized))
    base = [t for t in tokens if len(t) > 1 or _CJK_RE.search(t)]
    shingles = []
    for run in re.findall(r'[㐀-鿿]+', normalized):
        shingles.extend(
            run[i:i + size]
            for size in range(2, min(6, len(run)) + 1)
            for i in range(len(run) - size + 1))
    return list(dict.fromkeys(base + shingles))


def _metadata_terms(meta):
    values = []
    for key in ('aliases', 'keywords', 'triggers'):
        v = meta.get(key)
        if isinstance(v, str):
            values.append(v)
        elif isinstance(v, list):
            values.extend(str(x) for x in v)
    return ' '.join(values)


def _sections(path, text, skill_name):
    headings = list(_HEAD_RE.finditer(text))
    base = os.path.basename(path)
    if not headings:
        return [{'skill': skill_name, 'source': base, 'heading': base, 'text': text.strip(), 'level': 0}]
    result = []
    prefix = text[:headings[0].start()].strip()
    if prefix:
        result.append({'skill': skill_name, 'source': base, 'heading': base, 'text': prefix, 'level': 0})
    for i, h in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        content = text[h.start():end].strip()
        if content:
            result.append({'skill': skill_name, 'source': base, 'heading': h.group(2).strip(),
                           'text': content, 'level': len(h.group(1))})
    return result


def _capCache(d, cap):
    '''把 dict 裁剪到 cap 条（丢最早插入的），防止长期运行内存无界增长。'''
    if len(d) > cap:
        for k in list(d)[:len(d) - cap]:
            d.pop(k, None)


def _skillDirs():
    roots = [OlivaAIAgent.conf.dataPath + '/skills']
    extra = OlivaAIAgent.conf.get('skills', 'extra_dirs', default=[]) or []
    if isinstance(extra, str):          # 误配成字符串时不要按字符展开（否则会 mkdir 出一堆单字母垃圾目录）
        extra = [extra]
    roots.extend(extra)
    return [os.path.abspath(os.path.expanduser(str(r))) for r in roots if str(r).strip()]


def buildIndex():
    global _index
    result = {}
    for sdir in _skillDirs():
        OlivaAIAgent.conf.releaseDir(sdir)
        if not os.path.isdir(sdir):
            continue
        for root, dirs, files in os.walk(sdir):
            dirs.sort()
            if 'SKILL.md' not in files:
                continue
            skill_path = os.path.join(root, 'SKILL.md')
            raw = _read(skill_path)
            meta, body = _frontmatter(raw)
            name = str(meta.get('name') or os.path.basename(root))
            if name in result:
                continue
            sources = [skill_path]
            for rel in _REF_RE.findall(body):
                cand = os.path.abspath(os.path.join(root, rel.replace('/', os.sep)))
                if os.path.isfile(cand) and cand not in sources:
                    sources.append(cand)
            chunks = [c for s in sources for c in _sections(s, _read(s), name)]
            description = str(meta.get('description') or '')
            metaterms = _metadata_terms(meta)
            headings = ' '.join(c['heading'] for c in chunks)
            route_text = '%s %s %s %s %s' % (name, description, metaterms, headings, body)
            entry = {
                'name': name, 'description': description, 'metadata_terms': metaterms,
                'chunks': chunks, 'route_tokens': _tokens(route_text),
            }
            if _HAS_BM25:
                cdocs = [_tokens('%s %s' % (c['heading'], c['text'])) for c in chunks]
                entry['_chunk_bm25'] = BM25Okapi(cdocs) if cdocs and any(cdocs) else None
                entry['_chunk_docs'] = cdocs
            result[name] = entry
    if _HAS_BM25:
        docs = [e['route_tokens'] for e in result.values()]
        route_bm25 = BM25Okapi(docs) if result and any(docs) else None
        for e in result.values():
            e['_route_bm25'] = route_bm25
            e['_route_entries'] = list(result.values())
    _index = result
    _query_cache.clear()
    # 纯外文技能(元数据/标题完全无中文)：标记并排队翻译元数据，让中文提问也能命中
    global _build_gen
    with _pending_lock:
        _build_gen += 1
        gen = _build_gen
        del _pending_foreign[:]
        do_meta = bool(OlivaAIAgent.conf.get('skills', 'translate_skill_meta', default=True))
        limit = int(OlivaAIAgent.conf.get('skills', 'translate_meta_max_per_build', default=30))
        for name, e in result.items():
            probe = '%s %s %s %s' % (e['name'], e['description'], e['metadata_terms'],
                                     ' '.join(c['heading'] for c in e['chunks']))
            if probe.strip() and not _CJK_RE.search(probe):
                e['_foreign'] = True   # 始终标记外文技能，供 translate_query_to_foreign 独立使用
                if do_meta and len(_pending_foreign) < limit:
                    _pending_foreign.append(name)
    if _pending_foreign and _AUTO_ASYNC:
        threading.Thread(target=_processPending, args=(gen,), daemon=True).start()
    return result


def _historyWindow(history, size):
    return list(history or [])[-max(1, int(size)):]


def _rankDocsLite(query_tokens, documents):
    '''纯 Python 词频打分（BM25 缺失时的回退）。'''
    if not query_tokens or not documents:
        return [0.0] * len(documents)
    qset = set(query_tokens)
    scores = []
    for doc in documents:
        dset = set(doc)
        overlap = len(qset & dset)
        # 加权：长词/中文子串命中更值钱
        weight = sum(1.5 if (len(t) >= 2) else 1.0 for t in (qset & dset))
        scores.append(float(overlap) + weight)
    return scores


def _rankDocs(query_tokens, documents, bm25=None):
    if _HAS_BM25 and bm25 is not None and query_tokens:
        return [float(s) for s in bm25.get_scores(query_tokens)]
    return _rankDocsLite(query_tokens, documents)


def selectSkills(history, bot_hash, size, max_matches, match_rate):
    entries = list(_index.values())
    if not entries:
        return []
    window = _historyWindow(history, size)
    query_text = '\n'.join(str(e.get('message', '')) for e in window if e.get('message'))
    latest = next((str(e.get('message', '')) for e in reversed(window) if e.get('message')), query_text)
    translated = _translateForeignQuery(latest)
    to_foreign = _translateQueryToForeign(latest)
    query_tokens = _tokens('%s\n%s\n%s\n%s' % (query_text, latest, translated, to_foreign))
    docs = [e['route_tokens'] for e in entries]
    route_bm25 = entries[0].get('_route_bm25') if _HAS_BM25 else None
    lexical = _rankDocs(query_tokens, docs, route_bm25)
    for i, e in enumerate(entries):
        declared = set(_tokens('%s %s %s %s' % (
            e['name'], e['description'], e['metadata_terms'], e.get('zh_meta', ''))))
        lexical[i] += len(set(query_tokens) & declared) * 1.5
    best = max(lexical, default=0.0)
    absolute = max(0.25, float(match_rate) * 10.0)
    floor = max(2.0, absolute) if _HAS_BM25 else max(1.5, absolute * 0.3)
    ranked = sorted(
        ({'skill': e['name'], 'score': s}
         for e, s in zip(entries, lexical) if s >= floor and s >= best * 0.82),
        key=lambda x: (-x['score'], x['skill']))
    return ranked[:max(1, int(max_matches))]


def _rankChunks(query_tokens, chunks, bm25, priority_tokens):
    docs = [_tokens('%s %s %s' % (c['heading'], c.get('zh_heading', ''), c['text'])) for c in chunks]
    scores = _rankDocs(query_tokens, docs, bm25)
    qset = set(query_tokens)
    pset = set(priority_tokens or [])
    ranked = []
    for c, score in zip(chunks, scores):
        if score <= 0:
            continue
        heading_tokens = set(_tokens('%s %s' % (c['heading'], c.get('zh_heading', ''))))
        heading_overlap = len(qset & heading_tokens)
        adjusted = score + heading_overlap * 200.0
        nt = c['text'].lower()
        adjusted += sum(1 for t in qset if len(t) >= 2 and t in nt) * 30.0
        adjusted += sum(1000.0 for t in pset if len(t) >= 2 and t in nt)
        lines = c['text'].splitlines()
        line_count = max(1, len(lines))
        list_ratio = sum(ln.lstrip().startswith(('-', '*', '|')) for ln in lines) / line_count
        if list_ratio > 0.65 and heading_overlap == 0:
            adjusted *= 0.55
        if len(c['text']) < 40 and heading_overlap == 0:
            adjusted *= 0.65
        if c.get('level') == 1 and heading_overlap == 0:
            adjusted *= 0.35
        ranked.append({**c, 'score': adjusted})
    ranked.sort(key=lambda x: (-x['score'], x['source'], x['heading']))
    return ranked


def getContext(history, bot_hash):
    if not OlivaAIAgent.conf.get('skills', 'enable', default=True):
        return ''
    if not _index:
        return ''
    size = OlivaAIAgent.conf.get('memory', 'context_buffer', default=20)
    max_matches = OlivaAIAgent.conf.get('skills', 'max_matches', default=2)
    max_chars = int(OlivaAIAgent.conf.get('skills', 'max_chars', default=2000))
    match_rate = OlivaAIAgent.conf.get('skills', 'match_rate', default=0.12)
    window = _historyWindow(history, size)
    latest = next((str(e.get('message', '')) for e in reversed(window) if e.get('message')), '')
    cache_key = '%s|%s' % (bot_hash, latest[:120])
    cached = _query_cache.get(cache_key)
    if cached and time.time() - cached[0] <= 900:
        return cached[1]
    selections = selectSkills(history, bot_hash, size, max_matches, match_rate)
    if not selections:
        _query_cache[cache_key] = (time.time(), '')
        _capCache(_query_cache, 2000)
        return ''
    latest_tokens = {t for t in _tokens(latest) if len(t) >= 2}
    focus = [latest]
    for e in reversed(window[:-1]):
        msg = str(e.get('message', ''))
        if latest_tokens & set(_tokens(msg)):
            focus.append(msg)
        if len(focus) >= 4:
            break
    priority = _tokens('\n'.join(reversed(focus)))
    translated = _translateForeignQuery(latest)
    to_foreign = _translateQueryToForeign(latest)
    query_tokens = _tokens('%s\n%s\n%s\n%s' % (latest, latest, translated, to_foreign))
    chunks = [c for sel in selections for c in _index[sel['skill']]['chunks']]
    bm25 = _index[selections[0]['skill']].get('_chunk_bm25') if (len(selections) == 1 and _HAS_BM25) else None
    ranked = _rankChunks(query_tokens, chunks, bm25, priority)
    if ranked:
        floor = ranked[0]['score'] * 0.18
        ranked = [c for c in ranked if c['score'] >= floor]
    if not ranked and chunks:
        # 外文技能保底：路由已判定该技能相关，但正文与提问词法零重叠(如中文提问+纯英文正文、
        # 且无任何翻译渠道)时，按文档顺序注入首选技能的开头片段，绝不空手而归
        ranked = [dict(c, score=1.0) for c in _index[selections[0]['skill']]['chunks'][:4]]
    chosen, used, seen = [], 0, set()
    for c in ranked:
        content = c['text'].strip()
        fp = re.sub(r'\s+', ' ', content).strip().lower()[:500]
        if not fp or fp in seen:
            continue
        seen.add(fp)
        if chosen and used + len(content) > max_chars:
            continue
        if not chosen and len(content) > max_chars:
            content = content[:max_chars].rstrip()
        chosen.append({**c, 'text': content})
        used += len(content)
        if used >= max_chars or len(chosen) >= 4:
            break
    blocks = ['[Skill: %s | Section: %s]\n%s' % (c['skill'], c['heading'], c['text']) for c in chosen]
    context = '\n\n'.join(blocks)
    _query_cache[cache_key] = (time.time(), context)
    _capCache(_query_cache, 2000)
    OlivaAIAgent.conf.debugLog(OlivaAIAgent.conf.gProc,
                               '[Skills %s] sel=%s chunks=%d chars=%d'
                               % (backendName(), [s['skill'] for s in selections], len(chosen), len(context)))
    return context
