# -*- encoding: utf-8 -*-
'''SQLite 长期事实记忆与 OpenAI-compatible embedding 检索。'''

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
from collections import OrderedDict

import requests

import OlivaAIAgent

_lock = threading.RLock()
_initialized_path = None
_embedding_cache = OrderedDict()
_failure_until = 0.0
_last_error = ''


def _dbPath():
    return os.path.join(OlivaAIAgent.conf.dataPath, 'semantic_memory.sqlite3')


def _connect():
    initialize()
    conn = sqlite3.connect(_dbPath(), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    '''建立事实表；可在插件初始化和首次读写时重复安全调用。'''
    global _initialized_path
    path = _dbPath()
    with _lock:
        if _initialized_path == path and os.path.exists(path):
            return
        OlivaAIAgent.conf.releaseDir(os.path.dirname(path))
        conn = sqlite3.connect(path, timeout=15)
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS facts (
                    id TEXT PRIMARY KEY,
                    bot_hash TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    content TEXT NOT NULL,
                    keywords TEXT NOT NULL DEFAULT '[]',
                    source_message_id TEXT,
                    source_reference_id TEXT,
                    source_event_id TEXT,
                    source_time TEXT,
                    embedding TEXT,
                    embedding_model TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_facts_scope
                ON facts(bot_hash, platform, scope_type, scope_id, updated_at DESC)
            ''')
            conn.commit()
            _initialized_path = path
        finally:
            conn.close()


def _embeddingConf():
    conf = OlivaAIAgent.conf
    return {
        'api_url': str(conf.get('semantic_memory', 'embedding_api_url', default='') or '').strip(),
        'api_key': str(conf.get('semantic_memory', 'embedding_api_key', default='') or '').strip(),
        'model': str(conf.get('semantic_memory', 'embedding_model', default='') or '').strip(),
        'timeout': float(conf.get('semantic_memory', 'embedding_timeout_sec', default=30)),
        'headers': dict(conf.get('semantic_memory', 'embedding_extra_headers', default={}) or {}),
    }


def _embeddingUrl(api_url):
    url = str(api_url or '').rstrip('/')
    if not url:
        return ''
    if url.lower().endswith('/embeddings'):
        return url
    return url + '/embeddings'


def embeddingReady():
    bc = _embeddingConf()
    return bool(bc['api_url'] and bc['model'])


def getStatus():
    bc = _embeddingConf()
    with _lock:
        error = _last_error
        backing_off = time.monotonic() < _failure_until
    return {
        'ready': bool(bc['api_url'] and bc['model']),
        'model': bc['model'],
        'mode': 'vector' if bc['api_url'] and bc['model'] and not backing_off else 'keyword',
        'backing_off': backing_off,
        'last_error': error,
    }


def _cachePut(key, vector):
    limit = max(0, int(OlivaAIAgent.conf.get('semantic_memory', 'cache_size', default=256)))
    if limit <= 0:
        return
    with _lock:
        _embedding_cache.pop(key, None)
        _embedding_cache[key] = vector
        while len(_embedding_cache) > limit:
            _embedding_cache.popitem(last=False)


def embedTexts(texts):
    '''批量生成向量。未配置或退避期内返回与输入等长的 None 列表。'''
    global _failure_until, _last_error
    values = [str(item or '').strip() for item in texts]
    result = [None] * len(values)
    bc = _embeddingConf()
    if not bc['api_url'] or not bc['model']:
        return result
    now = time.monotonic()
    with _lock:
        if now < _failure_until:
            return result
        missing = []
        missing_indices = []
        for index, value in enumerate(values):
            key = (bc['model'], value)
            if key in _embedding_cache:
                result[index] = list(_embedding_cache[key])
                _embedding_cache.move_to_end(key)
            elif value:
                missing.append(value)
                missing_indices.append(index)
    if not missing:
        return result
    headers = {'Content-Type': 'application/json'}
    if bc['api_key']:
        headers['Authorization'] = 'Bearer ' + bc['api_key']
    headers.update(bc['headers'])
    try:
        response = requests.post(
            _embeddingUrl(bc['api_url']),
            headers=headers,
            json={'model': bc['model'], 'input': missing},
            timeout=bc['timeout'],
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError('embedding 响应缺少 data 数组')
        vectors = {}
        for offset, row in enumerate(rows):
            if not isinstance(row, dict) or not isinstance(row.get('embedding'), list):
                continue
            index = row.get('index', offset)
            if isinstance(index, int) and 0 <= index < len(missing):
                vectors[index] = [float(item) for item in row['embedding']]
        for offset, original_index in enumerate(missing_indices):
            vector = vectors.get(offset)
            if vector:
                result[original_index] = vector
                _cachePut((bc['model'], values[original_index]), vector)
        with _lock:
            _last_error = ''
    except Exception as e:
        backoff = max(1.0, float(OlivaAIAgent.conf.get(
            'semantic_memory', 'failure_backoff_sec', default=300,
        )))
        with _lock:
            _failure_until = time.monotonic() + backoff
            _last_error = '%s: %s' % (type(e).__name__, e)
        OlivaAIAgent.conf.log(OlivaAIAgent.conf.gProc, 3, '长期记忆 embedding 暂不可用，降级关键词检索: %s' % e)
    return result


def _factId(bot_hash, platform, group_id, subject, content):
    raw = '\x1f'.join([str(bot_hash), str(platform), str(group_id), str(subject), str(content)])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _cleanKeywords(value):
    if isinstance(value, str):
        value = re.split(r'[,，、;；\s]+', value)
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip()[:32] for item in value if str(item).strip()))[:12]


def upsertFacts(bot_hash, platform, group_id, facts, source=None):
    '''写入事实并尽力补齐向量；embedding 失败仍保留事实供关键词检索。'''
    source = source if isinstance(source, dict) else {}
    clean = []
    for fact in facts or []:
        if not isinstance(fact, dict):
            continue
        subject = str(fact.get('subject') or fact.get('s') or '').strip()[:128]
        content = str(fact.get('content') or fact.get('fact') or fact.get('c') or '').strip()[:2000]
        if not content or OlivaAIAgent.conf.isPersonaMutationText('%s %s' % (subject, content)):
            continue
        if not subject:
            subject = content[:32]
        clean.append({
            'subject': subject,
            'content': content,
            'keywords': _cleanKeywords(fact.get('keywords') or fact.get('k')),
            'source_message_id': fact.get('source_message_id') or source.get('message_id'),
            'source_reference_id': fact.get('source_reference_id') or source.get('reference_message_id'),
            'source_event_id': fact.get('source_event_id') or source.get('event_id'),
            'source_time': fact.get('source_time') or source.get('time'),
        })
    if not clean:
        return 0
    model = _embeddingConf()['model']
    vectors = embedTexts(['%s: %s' % (item['subject'], item['content']) for item in clean])
    now = time.time()
    data_bot_hash = OlivaAIAgent.conf.dataBotHash(bot_hash)
    conn = _connect()
    try:
        for item, vector in zip(clean, vectors):
            fact_id = _factId(data_bot_hash, platform, group_id, item['subject'], item['content'])
            conn.execute('''
                INSERT INTO facts (
                    id, bot_hash, platform, scope_type, scope_id, subject, content, keywords,
                    source_message_id, source_reference_id, source_event_id, source_time,
                    embedding, embedding_model, created_at, updated_at
                ) VALUES (?, ?, ?, 'group', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    keywords=excluded.keywords,
                    source_message_id=COALESCE(excluded.source_message_id, facts.source_message_id),
                    source_reference_id=COALESCE(excluded.source_reference_id, facts.source_reference_id),
                    source_event_id=COALESCE(excluded.source_event_id, facts.source_event_id),
                    source_time=COALESCE(excluded.source_time, facts.source_time),
                    embedding=COALESCE(excluded.embedding, facts.embedding),
                    embedding_model=COALESCE(excluded.embedding_model, facts.embedding_model),
                    updated_at=excluded.updated_at
            ''', (
                fact_id, str(data_bot_hash), str(platform), str(group_id), item['subject'], item['content'],
                json.dumps(item['keywords'], ensure_ascii=False),
                _noneString(item['source_message_id']), _noneString(item['source_reference_id']),
                _noneString(item['source_event_id']), _noneString(item['source_time']),
                json.dumps(vector) if vector else None, model if vector else None, now, now,
            ))
        conn.commit()
    finally:
        conn.close()
    return len(clean)


def _noneString(value):
    return None if value in [None, '', '-1', -1] else str(value)


def _tokens(text):
    value = str(text or '').lower()
    result = set(re.findall(r'[a-z0-9_]{2,}', value))
    for chunk in re.findall(r'[\u4e00-\u9fff]+', value):
        if len(chunk) <= 8:
            result.add(chunk)
        result.update(chunk[index:index + 2] for index in range(max(0, len(chunk) - 1)))
    return result


def _cosine(left, right):
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    lnorm = math.sqrt(sum(item * item for item in left))
    rnorm = math.sqrt(sum(item * item for item in right))
    if lnorm <= 0 or rnorm <= 0:
        return 0.0
    return dot / (lnorm * rnorm)


def searchFacts(bot_hash, platform, group_id, query, top_k=None):
    '''检索本群长期事实；有向量时混合 cosine/关键词/时效，失败时纯关键词降级。'''
    query = str(query or '').strip()
    if not query:
        return []
    limit = max(1, int(top_k or OlivaAIAgent.conf.get('semantic_memory', 'top_k', default=6)))
    fetch_limit = max(limit, int(OlivaAIAgent.conf.get(
        'semantic_memory', 'max_scope_facts', default=2000,
    )))
    conn = _connect()
    try:
        rows = conn.execute('''
            SELECT * FROM facts
            WHERE bot_hash=? AND platform=? AND scope_type='group' AND scope_id=?
            ORDER BY updated_at DESC LIMIT ?
        ''', (str(OlivaAIAgent.conf.dataBotHash(bot_hash)), str(platform), str(group_id), fetch_limit)).fetchall()
    finally:
        conn.close()
    if not rows:
        return []
    query_vector = embedTexts([query])[0]
    current_model = _embeddingConf()['model']
    query_tokens = _tokens(query)
    minimum = float(OlivaAIAgent.conf.get('semantic_memory', 'min_score', default=0.25))
    now = time.time()
    found = []
    for row in rows:
        try:
            vector = json.loads(row['embedding']) \
                if row['embedding'] and row['embedding_model'] == current_model else None
        except Exception:
            vector = None
        keywords = []
        try:
            keywords = json.loads(row['keywords'])
        except Exception:
            pass
        fact_tokens = _tokens('%s %s %s' % (row['subject'], row['content'], ' '.join(keywords)))
        overlap = len(query_tokens & fact_tokens)
        keyword_score = overlap / math.sqrt(max(1, len(query_tokens) * len(fact_tokens)))
        age_days = max(0.0, now - float(row['updated_at'])) / 86400.0
        recency = 1.0 / (1.0 + age_days / 180.0)
        if query_vector and vector:
            vector_score = max(0.0, _cosine(query_vector, vector))
            score = 0.8 * vector_score + 0.15 * keyword_score + 0.05 * recency
            if score < minimum and overlap <= 0:
                continue
        else:
            if overlap <= 0:
                continue
            vector_score = None
            score = 0.9 * keyword_score + 0.1 * recency
        found.append({
            'subject': row['subject'],
            'content': row['content'],
            'keywords': keywords,
            'score': round(score, 4),
            'vector_score': None if vector_score is None else round(vector_score, 4),
            'source_message_id': row['source_message_id'],
            'source_reference_id': row['source_reference_id'],
            'source_event_id': row['source_event_id'],
            'source_time': row['source_time'],
        })
    found.sort(key=lambda item: item['score'], reverse=True)
    return found[:limit]


def countFacts(bot_hash=None, platform=None, group_id=None):
    clauses = []
    params = []
    if bot_hash is not None:
        clauses.append('bot_hash=?')
        params.append(str(OlivaAIAgent.conf.dataBotHash(bot_hash)))
    if platform is not None:
        clauses.append('platform=?')
        params.append(str(platform))
    if group_id is not None:
        clauses.append('scope_id=?')
        params.append(str(group_id))
    sql = 'SELECT COUNT(*) FROM facts'
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)
    conn = _connect()
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()
