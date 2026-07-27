# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 节律与匹配核心（移植/增强自刺客插件）
- SlackableFairLock: 礼貌节律公平锁。一串消息连发时，只对最后一条动手，避免逐条刷屏。
- DynamicQueue: 前缀缓存友好的历史队列。增长到上限再批量换代，最大化 DeepSeek/OpenAI 前缀缓存命中。
- get_recommendRank / peak_up_recommendMatch: LCS+编辑距离模糊匹配，用于知识库/侧写检索。
纯 Python 实现，无第三方依赖。
'''

import functools
import threading
import time

_gPeakUpCache = {}


class SlackableFairLock:
    '''礼貌节律公平锁：按取锁顺序服务，可松弛等待，出现竞争者立即中断松弛。'''

    def __init__(self, slack_time, cooldown_time):
        self._lock = threading.Lock()
        self._cond_acquire = threading.Condition(self._lock)
        self._cond_slack = threading.Condition(self._lock)
        self._next_ticket = 0
        self._serving = 0
        self._held = False
        self._count = 0
        self._first_timestamp = None
        self._slack_count = 1
        self._slack_time = float(slack_time)
        self._cooldown_time = float(cooldown_time)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def update_timing(self, slack_time, cooldown_time):
        with self._lock:
            self._slack_time = float(slack_time)
            self._cooldown_time = float(cooldown_time)

    def acquire(self):
        with self._lock:
            if self._first_timestamp is None:
                self._first_timestamp = time.perf_counter()
            my_ticket = self._next_ticket
            self._next_ticket += 1
            self._count += 1
            self._cond_slack.notify_all()
            while my_ticket != self._serving:
                self._cond_acquire.wait()
            self._held = True

    def release(self):
        with self._lock:
            if not self._held:
                return
            self._held = False
            self._serving += 1
            self._count -= 1
            self._tryReset()
            self._cond_acquire.notify_all()

    def slack(self):
        '''松弛等待：若期间有新竞争者到来则返回 False（应让位），否则返回 True（可动手）。'''
        with self._lock:
            if not self._held:
                return True
            remaining = self._getRemaining()
            if remaining > 0:
                self._cond_slack.wait(timeout=remaining)
            res = self._isLast()
            if not res:
                self._slack_count *= 2
            return res

    def _tryReset(self):
        if self._count == 0:
            self._next_ticket = 0
            self._serving = 0
            self._first_timestamp = None
            self._slack_count = 1

    def locked(self):
        with self._lock:
            return self._held

    def _isLast(self):
        return self._count <= 1

    def isLast(self):
        with self._lock:
            return self._isLast()

    def _getRemaining(self):
        if self._first_timestamp is None:
            return 0.0
        now = time.perf_counter()
        return float(min(
            max(0, self._slack_time - (now - self._first_timestamp)),
            max(0, self._cooldown_time - (now - self._first_timestamp)) / self._slack_count,
        ))

    def getRemaining(self):
        with self._lock:
            return self._getRemaining()


class DynamicQueue:
    '''前缀缓存友好历史：增长到 max_grow，再批量裁剪到 keep，循环往复，使连续请求前缀稳定。'''

    def __init__(self, keep, max_grow):
        self.max_grow = max(1, int(max_grow))
        self.keep = max(1, int(keep))
        if self.max_grow < self.keep:
            self.max_grow = self.keep
        self.queue = []

    def append(self, item):
        if len(self.queue) >= self.max_grow:
            keep_count = max(0, self.keep - 1)
            self.queue = self.queue[-keep_count:] if keep_count > 0 else []
        self.queue.append(item)

    def __len__(self):
        return len(self.queue)

    def __iter__(self):
        return iter(self.queue)

    def __getitem__(self, index):
        return self.queue[index]

    def to_list(self):
        return list(self.queue)


@functools.lru_cache(maxsize=50000)
def get_recommendRank(word1_in, word2_in, gate_rank=1000, rate=0.1):
    '''LCS + 编辑距离综合排名，越小越相关。移植自刺客 tools.get_recommendRank。'''
    word1 = word1_in.lower()
    word2 = word2_in.lower()
    if not word1 or not word2:
        return gate_rank + 1
    if len(word1) > len(word2):
        return gate_rank + 2
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
    iRank_1 = prev_lcs[len1]
    iRank_2 = prev_ed[len1]
    iRank = len2 * (len1 - iRank_1) + iRank_2 + 1
    iRank = (iRank * iRank) // len1 // len2
    if iRank >= int(len1 * len2 * rate):
        iRank += gate_rank
    return iRank


def get_recommendMatch(rank, gate_rank=1000):
    return rank < gate_rank


def peak_up_recommendMatch(target, dictMap, dictName, ageing, rate=1.0, matchedList=None, father=None):
    '''对 dictMap 的键做模糊匹配，命中则返回子字典。带 bigram 预筛与结果缓存。'''
    timestamp = int(time.perf_counter())
    res = {}
    res_key_list = []
    matchedList_this = matchedList if isinstance(matchedList, list) else []
    if dictName not in _gPeakUpCache:
        _gPeakUpCache[dictName] = {}
    for k in list(_gPeakUpCache[dictName].keys()):
        if timestamp - _gPeakUpCache.get(dictName, {}).get(k, {}).get('timestamp', 0) >= ageing:
            _gPeakUpCache[dictName].pop(k, None)
    if isinstance(dictMap, dict):
        dictMap_key_list = list(dictMap.keys())
        if target in _gPeakUpCache[dictName]:
            res_key_list = _gPeakUpCache.get(dictName, {}).get(target, {}).get('keylist', None)
        else:
            target_lower = target.lower()
            target_bigrams = set()
            if len(target_lower) >= 2:
                for i in range(len(target_lower) - 1):
                    target_bigrams.add(target_lower[i:i + 2])
            for k in dictMap_key_list:
                if k not in matchedList_this:
                    if target_bigrams:
                        k_lower = k.lower()
                        if len(k_lower) >= 2:
                            has_overlap = False
                            for i in range(len(k_lower) - 1):
                                if k_lower[i:i + 2] in target_bigrams:
                                    has_overlap = True
                                    break
                            if not has_overlap:
                                continue
                    rank = get_recommendRank(k, target, rate=rate)
                    if get_recommendMatch(rank):
                        res_key_list.append(k)
        if not isinstance(res_key_list, list):
            res_key_list = []
        else:
            _gPeakUpCache[dictName][target] = {'timestamp': timestamp, 'keylist': res_key_list}
        for k in res_key_list:
            if k in dictMap:
                res[k] = dictMap[k]
    return res


def clear_peakup_cache():
    _gPeakUpCache.clear()
