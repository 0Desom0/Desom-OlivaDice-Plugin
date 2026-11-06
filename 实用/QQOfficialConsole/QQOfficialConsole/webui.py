"""WebUI 请求分发；凭据与宿主路径绝不经过消息桥。"""

import base64
import binascii
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import OlivOS
from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as sdkCommon

from . import errors, media as media_module
from .send import Sender

# 群名接口的频控/永久失败错误码（code 与 err_code 两种形态都列上）
_GROUP_INFO_RATE_LIMIT_CODES = {40034100, 50002, 50055002}
_GROUP_INFO_PERMANENT_CODES = {11253, 11255, 40011028, 40012010}
_GROUP_INFO_RATE_LIMIT_DELAY = 120
_GROUP_INFO_RETRY_DELAY = 60
# 群信息接口官方限额：每机器人 30 次/分钟。按滑动窗口放行，不假设固定间隔。
_GROUP_INFO_WINDOW_LIMIT = 30
_GROUP_INFO_WINDOW_SECONDS = 60.0
# running 任务租约：超过这个时长仍未完成（进程卡死/异常）才允许回收，避免抢走进行中的请求。
_GROUP_INFO_RUNNING_LEASE = 300
# 入站图片只允许从 QQ 多媒体域名代下载，避免桥接接口被当成带鉴权的代理
_ATTACHMENT_HOSTS = {'multimedia.nt.qq.com.cn'}


class Bridge:
    def __init__(self, store, pool, roster, media, Proc):
        self.store, self.pool, self.roster, self.media, self.Proc = store, pool, roster, media, Proc
        self._request_lock = threading.Lock()
        self._last_request_page = 0.0
        self._jobs_lock = threading.Lock()
        self._jobs = {}
        self._closed = threading.Event()
        self._cache_lock = threading.Lock()
        self._cache_dir = Path(store.root) / 'view-cache'
        # 图片与聊天记录的定期清理共用一把锁：改设置时立即清一次，不能和后台线程撞车。
        self._retention_lock = threading.RLock()
        # 手动 VACUUM 只允许一个在跑：重复点击不该排队把库反复重写。
        self._vacuum_lock = threading.Lock()
        self._retention_stop = threading.Event()
        self._retention_worker = threading.Thread(
            target=self._retention_loop, name='QQOfficialConsole-retention', daemon=True
        )
        self._retention_worker.start()
        self._attachment_lock = threading.Lock()
        self._group_info_lock = threading.Lock()
        self._group_info_pump_locks = {}
        self._group_info_recovered = set()
        self._group_info_sent = {}
        self._group_info_wake = threading.Event()
        self._group_info_worker = threading.Thread(
            target=self._group_info_loop, name='QQOfficialConsole-group-info', daemon=True
        )
        self._group_info_worker.start()
        # 机器人自己的昵称/头像：GET /users/@me，成功缓存 1 小时，失败冷却 1 分钟。
        self._self_lock = threading.Lock()
        self._self_cache = {}

    def _group_info_loop(self):
        while not self._closed.is_set():
            self._group_info_wake.wait(30)
            self._group_info_wake.clear()
            if self._closed.is_set():
                break
            try:
                for bot_hash in self._bots():
                    if self._closed.is_set():
                        break
                    self.pump_group_info(limit=_GROUP_INFO_WINDOW_LIMIT, bot_hash=bot_hash)
            except Exception:
                pass

    def wake_group_info(self):
        self._group_info_wake.set()

    def _incoming_image(self, bot, chat_type, chat_id, message_id, attachment, index):
        """仅代理本会话入站消息中的 QQ CDN 图片，绝不接受前端传入的 URL。"""
        if (type(message_id) is not int or message_id <= 0 or type(attachment) is not int
                or attachment < 0 or type(index) is not int or index < 0):
            return errors.failure('图片已过期或无法加载')
        rows = self.store.get_messages_by_ids(bot, chat_type, chat_id, [message_id])
        if not rows or rows[0].get('direction') != 'in':
            return errors.failure('图片已过期或无法加载')
        try:
            payload = json.loads(rows[0].get('content_json') or '{}')
            item = payload['attachments'][attachment]
            if not isinstance(item, dict) or not str(item.get('content_type', '')).lower().startswith('image/'):
                return errors.failure('图片已过期或无法加载')
            url = item['url']
            if not isinstance(url, str) or len(url) > 8192:
                return errors.failure('图片已过期或无法加载')
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('multimedia.nt.qq.com.cn/'):
                url = 'https://' + url
            parsed = urlsplit(url)
            if (parsed.scheme != 'https' or parsed.hostname not in _ATTACHMENT_HOSTS
                    or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443)):
                return errors.failure('图片已过期或无法加载')
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return errors.failure('图片已过期或无法加载')
        key = self.media.inbound_key(bot, url)
        retention = self.store.get_settings()['image_retention_days']
        # 同一张图只下载一次，避免滚动/并发请求放大到 CDN。
        with self._attachment_lock:
            path = self.media.inbound_path(key)
            chunk = self.media.read_inbound_chunk(path, index, retention) if path else None
            if chunk:
                return {'ok': True, 'keyword': '成功', **chunk}
            if path and index:
                return errors.failure('图片已过期或无法加载')
            try:
                event = self._event(bot)
                sdk_bot = OlivOS.qqGuildv2SDK.get_SDK_bot_info_from_Event(event)
                token = sdkCommon.getTokenNow(sdk_bot)
                if not token:
                    return errors.failure('图片已过期或无法加载')
                response = sdkCommon.req.request(
                    'GET', url, headers={'Authorization': 'QQBot ' + token},
                    timeout=(5, 20), allow_redirects=False, stream=True,
                )
                try:
                    if response.status_code != 200:
                        return errors.failure('图片已过期或无法加载')
                    parts, size = [], 0
                    for part in response.iter_content(chunk_size=65536):
                        if part:
                            size += len(part)
                            if size > media_module.MAX_SIZE:
                                return errors.failure('图片已过期或无法加载')
                            parts.append(part)
                    path = self.media.save_inbound(key, b''.join(parts))
                finally:
                    response.close()
                chunk = self.media.read_inbound_chunk(path, index, retention) if path else None
                return {'ok': True, 'keyword': '成功', **chunk} if chunk else errors.failure('图片已过期或无法加载')
            except Exception:
                return errors.failure('图片已过期或无法加载')

    def fetch_group_name(self, bot_hash, group_openid):
        """调用官方群信息接口；返回 (result, body)。"""
        bot = self._bots().get(bot_hash)
        if bot is None:
            return errors.failure('机器人无效'), {}
        try:
            event = self._event(bot_hash)
            sdk_bot = OlivOS.qqGuildv2SDK.get_SDK_bot_info_from_Event(event)
            token = sdkCommon.getTokenNow(sdk_bot)
            if not token:
                result = errors.failure('机器人令牌暂时不可用')
                result['retryable'] = True
                return result, {}
            host = str(OlivOS.qqGuildv2SDK.sdkAPIHost.get('default') or 'https://api.bot.qq.com')
            if '://' not in host:
                host = 'https://' + host
            url = host.rstrip('/') + '/v2/groups/%s/info' % group_openid
            response = sdkCommon.req.request(
                'GET', url, headers={'Authorization': 'QQBot ' + token}, timeout=(5, 20),
            )
            status = getattr(response, 'status_code', 0)
            try:
                payload = json.loads(getattr(response, 'text', None) or '{}')
            except (ValueError, TypeError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
            if not isinstance(data, dict):
                data = {}
            code = payload.get('code', payload.get('err_code'))
            try:
                code = int(code) if code is not None else None
            except (TypeError, ValueError):
                code = None
            ok = status == 200 and code in (None, 0)
            if ok:
                result = {'ok': True, 'keyword': '成功', 'http_status': status, 'error_code': None}
            else:
                result = errors.failure(errors.CODES.get(code, '无接口权限') if code else '无接口权限')
                result['error_code'] = code
                result['http_status'] = status
            return result, data
        except Exception:
            result = errors.failure('群信息暂时获取失败')
            result['retryable'] = True
            return result, {}

    def bot_self(self, bot_hash):
        """GET /users/@me 取机器人自己的昵称与头像；失败返回 None。

        页面显示「机器人」太笼统，官方这个接口能拿到真实昵称。
        成功缓存 1 小时，失败冷却 1 分钟，避免每开一次会话就请求一次。
        """
        now = time.time()
        with self._self_lock:
            cached = self._self_cache.get(bot_hash)
            if cached and now - cached[0] < (3600 if cached[1] else 60):
                return cached[1]
        info = None
        if bot_hash in self._bots():
            try:
                event = self._event(bot_hash)
                sdk_bot = OlivOS.qqGuildv2SDK.get_SDK_bot_info_from_Event(event)
                token = sdkCommon.getTokenNow(sdk_bot)
                if token:
                    host = str(OlivOS.qqGuildv2SDK.sdkAPIHost.get('default') or 'https://api.bot.qq.com')
                    if '://' not in host:
                        host = 'https://' + host
                    response = sdkCommon.req.request(
                        'GET',
                        host.rstrip('/') + '/users/@me',
                        headers={'Authorization': 'QQBot ' + token},
                        timeout=(5, 20),
                    )
                    payload = json.loads(getattr(response, 'text', None) or '{}')
                    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
                    name = data.get('username') or data.get('nick') or ''
                    avatar = data.get('avatar') or ''
                    if isinstance(name, str) and name.strip():
                        info = {
                            'name': name.strip()[:64],
                            'avatar': avatar if isinstance(avatar, str) else '',
                        }
            except Exception:
                info = None
        with self._self_lock:
            self._self_cache[bot_hash] = (now, info)
        return info

    def _group_info_bot_lock(self, bot_hash):
        """同一机器人同时只允许一个 pump，防止并发调用把 running 任务重新回收。"""
        with self._group_info_lock:
            return self._group_info_pump_locks.setdefault(bot_hash, threading.Lock())

    def _group_info_window_ready(self, bot_hash, now):
        """官方限额为每机器人 30 次/分钟，按滑动窗口判断而不是强制平滑间隔。"""
        with self._group_info_lock:
            history = [
                stamp for stamp in self._group_info_sent.get(bot_hash, ())
                if now - stamp < _GROUP_INFO_WINDOW_SECONDS
            ]
            self._group_info_sent[bot_hash] = history
            return len(history) < _GROUP_INFO_WINDOW_LIMIT

    def _group_info_note_request(self, bot_hash, now):
        with self._group_info_lock:
            self._group_info_sent.setdefault(bot_hash, []).append(now)

    def pump_group_info(self, limit=5, bot_hash=None):
        """按入群时间 FIFO 处理群名队列；队首冷却或窗口用尽时不越过、不补发。"""
        bots = [bot_hash] if bot_hash else list(self._bots())
        for key in bots:
            if self._closed.is_set():
                return
            with self._group_info_bot_lock(key):
                if key not in self._group_info_recovered:
                    # 仅进程启动后首次处理时恢复上次崩溃残留的 running 任务；之后不再回收，
                    # 否则并发 pump 会把另一个线程正在请求的任务重新抢走。
                    self.store.recover_group_info_jobs(key)
                    self._group_info_recovered.add(key)
                else:
                    # 后续只回收超出租约的 running 任务，让卡死任务自愈又不抢占在途请求。
                    self.store.recover_group_info_jobs(key, stale_after=_GROUP_INFO_RUNNING_LEASE)
                processed = 0
                while processed < max(1, int(limit)):
                    if self._closed.is_set():
                        return
                    now = time.monotonic()
                    if not self._group_info_window_ready(key, now):
                        break
                    claimed = self.store.claim_group_info_jobs(key)
                    if not claimed:
                        break
                    group_openid = claimed[0]
                    self._group_info_note_request(key, now)
                    result, body = self.fetch_group_name(key, group_openid)
                    name = body.get('group_name')
                    if result['ok'] and isinstance(name, str) and name.strip():
                        self.store.upsert_chat(key, 'qq_group', group_openid, display_name=name.strip()[:255])
                        self.store.complete_group_info_job(key, group_openid)
                    else:
                        code = result.get('error_code')
                        status = result.get('http_status')
                        if code in _GROUP_INFO_PERMANENT_CODES:
                            self.store.fail_group_info_job(key, group_openid, code)
                        elif status == 429 or code in _GROUP_INFO_RATE_LIMIT_CODES:
                            self.store.requeue_group_info_job(
                                key, group_openid, _GROUP_INFO_RATE_LIMIT_DELAY, max_attempts=None
                            )
                        elif result.get('retryable') or (isinstance(status, int) and 500 <= status < 600):
                            self.store.requeue_group_info_job(
                                key, group_openid, _GROUP_INFO_RETRY_DELAY, max_attempts=None
                            )
                        else:
                            self.store.requeue_group_info_job(key, group_openid, _GROUP_INFO_RETRY_DELAY)
                    processed += 1

    def backfill_group_names(self):
        """启动补齐：给已有会话但没有群名的群入队（机器人离线期间被拉进群时兜底）。"""
        for bot_hash in self._bots():
            for group_openid in self.store.list_group_info_targets(bot_hash):
                self.store.enqueue_group_info(bot_hash, group_openid)
        self.wake_group_info()

    def _retention_loop(self):
        """启动时先清一次过期图片；之后每小时按保留策略清图片和聊天记录。

        聊天记录故意不在启动时清：插件刚起来先别动历史数据，改设置时
        SaveSettings 会立即按新期限清一次，后台每小时再跑一轮。
        """
        try:
            with self._retention_lock:
                self.media.cleanup_sent(self.store.get_settings()['image_retention_days'])
        except Exception:
            pass
        while not self._retention_stop.wait(3600):
            try:
                self.run_retention()
            except Exception:
                pass

    def _clear_view_cache(self):
        """清掉会话页缓存：消息被清理后，缓存里可能还留着已经不存在的记录。"""
        with self._cache_lock:
            if not self._cache_dir.is_dir():
                return
            for path in self._cache_dir.iterdir():
                if path.suffix in ('.json', '.part') and not path.is_symlink() and path.is_file():
                    path.unlink(missing_ok=True)

    def run_retention(self):
        """按当前设置执行一次保留策略：后台线程和保存设置共用同一套逻辑。"""
        with self._retention_lock:
            settings = self.store.get_settings()
            self.media.cleanup_sent(settings['image_retention_days'])
            result = {'deleted': 0, 'chats': 0, 'failed': 0}
            for bot_hash in self._bots():
                try:
                    pruned = self.store.prune_messages(bot_hash, settings['message_retention_days'])
                except Exception:
                    result['failed'] += 1
                    continue
                result['deleted'] += pruned['deleted']
                result['chats'] += pruned['chats']
                result['failed'] += pruned.get('failed', 0)
            if result['deleted']:
                self._clear_view_cache()
            return result

    def close(self):
        self._closed.set()
        self._group_info_wake.set()
        self._retention_stop.set()
        self._retention_worker.join(timeout=5)
        self._group_info_worker.join(timeout=2)
        with self._jobs_lock:
            threads = [job['thread'] for job in self._jobs.values() if job.get('thread')]
        deadline = time.monotonic() + 2
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))

    def _refresh_requests(self, key, job):
        bot, chat_id = key
        result = None
        try:
            event = self._event(bot)
            result = self._admin(event, bot, 'qq_group', chat_id)
            if result is None:
                with self._jobs_lock:
                    job['authorized'] = True
                requests, cursor, seen = [], None, set()
                truncated = False
                for _ in range(40):
                    with self._request_lock:
                        delay = max(0, 2 - (time.monotonic() - self._last_request_page))
                        if self._closed.wait(delay) or job['cancel'].is_set():
                            return
                        self._last_request_page = time.monotonic()
                        raw = event.indeAPI.get_qq_group_join_request_list(chat_id, cursor=cursor, limit=50)
                    if self._closed.is_set() or job['cancel'].is_set():
                        return
                    result = self._result(raw)
                    if not result['ok']:
                        break
                    body = self._body(raw)
                    entries = body.get('list')
                    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
                        result = errors.failure('申请列表无效')
                        break
                    for entry in entries:
                        entry = dict(entry)
                        stamp = entry.get('apply_at')
                        if isinstance(stamp, str):
                            try:
                                entry['apply_at'] = int(
                                    datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
                                )
                            except ValueError:
                                entry['apply_at'] = None
                        entry['verify_json'] = entry.get('verify_info')
                        requests.append(entry)
                    cursor = body.get('next_cursor')
                    if not cursor:
                        break
                    if cursor in seen:
                        truncated = True
                        break
                    seen.add(cursor)
                else:
                    truncated = bool(cursor)
                if result and result['ok']:
                    with self._jobs_lock:
                        if self._closed.is_set() or job['cancel'].is_set():
                            return
                        self.roster.refresh_requests(bot, chat_id, requests, complete=not truncated)
                    result = {'ok': True, 'keyword': '成功', 'truncated': truncated}
        except Exception:
            result = errors.failure('申请刷新失败')
        finally:
            with self._jobs_lock:
                if self._jobs.get(key) is job:
                    job['result'] = result or errors.failure('申请刷新已取消')
                    job['finished'] = time.monotonic()

    def _join_request_list(self, bot, chat_id, refresh):
        key = (bot, chat_id)
        with self._jobs_lock:
            now = time.monotonic()
            for old_key, old in list(self._jobs.items()):
                if old.get('finished') is not None and now - old['finished'] >= 300:
                    del self._jobs[old_key]
            job = self._jobs.get(key)
            if refresh and (job is None or job.get('finished') is not None):
                if self._closed.is_set():
                    return errors.failure('插件正在关闭')
                if len(self._jobs) >= 16:
                    return errors.failure('刷新任务过多')
                job = {'cancel': threading.Event()}
                thread = threading.Thread(target=self._refresh_requests, args=(key, job), daemon=True)
                job['thread'] = thread
                self._jobs[key] = job
                thread.start()
            refreshing = bool(job and job.get('finished') is None)
            result = job.get('result') if job and not refreshing else None
            if result is not None:
                del self._jobs[key]
        if result and not result['ok']:
            return result
        return {
            'ok': True, 'keyword': '成功', 'refreshing': refreshing,
            'truncated': bool(result and result.get('truncated')),
            'requests': self.roster.list_requests(bot, chat_id, limit=2000)
            if not refreshing or job.get('authorized') else [],
        }

    def _view_cache_chunk(self, bot, chat_type, chat_id, payload, put):
        if not self.store.get_chat(bot, chat_type, chat_id):
            return errors.failure('会话不存在')
        index = payload.get('index')
        if type(index) is not int or index < 0:
            raise ValueError()
        key = json.dumps([bot, chat_type, chat_id], ensure_ascii=False, separators=(',', ':'))
        name = hashlib.sha256(key.encode('utf-8')).hexdigest()
        chunk_size = 192 * 1024
        with self._cache_lock:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            target = self._cache_dir / (name + '.json')
            staging = self._cache_dir / (name + '.part')
            now = time.time()
            for path in self._cache_dir.iterdir():
                if path.suffix not in ('.json', '.part') or path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                if now - stat.st_mtime >= 1800:
                    path.unlink(missing_ok=True)
            if not put:
                if target.is_symlink() or not target.is_file():
                    return {'ok': True, 'keyword': '成功', 'found': False}
                size = target.stat().st_size
                if index * chunk_size >= size:
                    return errors.failure('缓存无效')
                with target.open('rb') as file:
                    file.seek(index * chunk_size)
                    data = file.read(chunk_size)
                return {
                    'ok': True,
                    'keyword': '成功',
                    'found': True,
                    'data_b64': base64.b64encode(data).decode('ascii'),
                    'complete': index * chunk_size + len(data) == size,
                }
            encoded = payload.get('data_b64')
            complete = payload.get('complete')
            if not isinstance(encoded, str) or len(encoded) > 4 * ((chunk_size + 2) // 3) or type(complete) is not bool:
                raise ValueError()
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                raise ValueError() from None
            if not data or len(data) > chunk_size or (not complete and len(data) != chunk_size):
                raise ValueError()
            if staging.is_symlink() or target.is_symlink():
                return errors.failure('缓存无效')
            if index and (not staging.is_file() or staging.stat().st_size != index * chunk_size):
                return errors.failure('缓存分片无效')
            try:
                with staging.open('wb' if index == 0 else 'ab') as file:
                    file.write(data)
                if complete:
                    os.replace(staging, target)
            except OSError:
                return errors.failure('缓存写入失败')
            return {'ok': True, 'keyword': '成功'}

    def _bots(self):
        bots = self.Proc.Proc_data.get('bot_info_dict', {})
        return {
            str(key): bot for key, bot in bots.items() if getattr(bot, 'platform', {}).get('sdk') == 'qqGuildv2_link'
        }

    def _event(self, bot_hash):
        bot = self._bots().get(bot_hash)
        if bot is None:
            raise ValueError('机器人无效')
        return OlivOS.API.Event(
            OlivOS.contentAPI.fake_sdk_event(bot_info=bot, fakename='QQOfficialConsole'), self.Proc.log
        )

    @staticmethod
    def _body(raw):
        data = raw.get('data') or {}
        response = data.get('response') or {}
        if isinstance(response, dict) and isinstance(response.get('data'), dict):
            response = response['data']
        return response if isinstance(response, dict) else {}

    @staticmethod
    def _result(raw):
        if not isinstance(raw, dict):
            return errors.failure('无接口权限')
        result = errors.result(raw)
        # SDK 的错误文本可能夹带 HTTP 细节或凭据，不能整包回给页面。
        result.pop('message', None)
        return result

    def _role(self, event, bot, chat_id):
        try:
            raw = OlivOS.qqGuildv2SDK.event_action.get_qq_group_bot_state(event, chat_id)
        except Exception:
            raw = None
        result = self._result(raw)
        body = self._body(raw) if isinstance(raw, dict) else {}
        fields = {}
        if result['ok'] and body.get('member_role') not in ('member', 'admin', 'owner'):
            # 响应成功但角色缺失不能沿用旧管理员权限执行写操作。
            result = errors.failure('无法确认机器人身份')
        if result['ok']:
            fields['self_role'] = body['member_role']
            proactive = body.get('allow_proactive_msg')
            if isinstance(proactive, bool):
                fields['allow_proactive'] = proactive
            openid = body.get('member_openid')
            if isinstance(openid, str) and openid.strip():
                fields['bot_openid'] = openid.strip()[:255]
            fields['role_updated_at'] = int(time.time())
        with self._jobs_lock:
            if self._closed.is_set():
                return errors.failure('插件正在关闭'), self.store.get_chat(bot, 'qq_group', chat_id) or {'self_role': None}
            chat = self.store.upsert_chat(bot, 'qq_group', chat_id, **fields)
        return result, chat

    def kick_group_member(self, bot_hash, group_openid, member_openid, blacklist=False):
        """把成员移出群聊，返回桥接结果。

        SDK 的 set_qq_group_batch_remove_members 在当前版本会调用未导入的
        `_do_qq_group_api_request`（`from ... import *` 不带下划线开头的名字）而直接
        NameError，所以这里用同一个 API 对象自己发请求，并守同一套 30 QPM 窗口。
        """
        op_key = 'group_batch_remove_members'
        # 和 SDK 一致：11253 之后进冷却期，冷却期间别再撞接口。
        denied = getattr(sdkCommon, '_check_qq_group_api_denied', None)
        if callable(denied) and denied(op_key):
            return errors.failure('无接口权限')
        acquire = getattr(sdkCommon, '_acquire_qq_group_api_rate', None)
        if callable(acquire) and not acquire(op_key):
            return errors.failure('操作过于频繁')
        try:
            event = self._event(bot_hash)
            sdk_bot = OlivOS.qqGuildv2SDK.get_SDK_bot_info_from_Event(event)
            api = OlivOS.qqGuildv2SDK.API.setQQGroupBatchRemoveMembers(sdk_bot)
            api.metadata.group_openid = str(group_openid)
            api.data.member_openids = [str(member_openid)]
            api.data.add_to_member_blacklist = bool(blacklist)
            api.do_api('POST')
            status = getattr(api, 'res_code', None)
            try:
                payload = json.loads(getattr(api, 'res', None) or '{}')
            except (ValueError, TypeError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            code = payload.get('code', payload.get('err_code'))
            try:
                code = int(code) if code is not None else None
            except (TypeError, ValueError):
                code = None
            if isinstance(status, int) and 200 <= status < 300 and code in (None, 0):
                return {'ok': True, 'keyword': '成功', 'error_code': None}
            # 11253 = 内邀白名单没开，和 SDK 一样记冷却，别每次点击都撞一次接口。
            if code == getattr(sdkCommon, 'qqGroupApiDeniedCode', 11253):
                marker = getattr(sdkCommon, '_mark_qq_group_api_denied', None)
                if callable(marker):
                    marker(op_key)
            result = errors.failure(errors.CODES.get(code, '无接口权限') if code else '无接口权限')
            result['error_code'] = code
            return result
        except Exception:
            return errors.failure('移出失败')

    def _admin(self, event, bot, chat_type, chat_id):
        if chat_type != 'qq_group':
            return errors.failure('无管理员权限')
        result, chat = self._role(event, bot, chat_id)
        if not result['ok']:
            return result
        if chat['self_role'] not in ('admin', 'owner'):
            return errors.failure('无管理员权限')
        return None

    def handle(self, event_name, payload):
        try:
            if (
                not isinstance(event_name, str)
                or not event_name.startswith('QQOfficialConsole_')
                or not isinstance(payload, dict)
            ):
                return errors.failure('参数无效')
            return self._handle(event_name[len('QQOfficialConsole_') :], payload)
        except ValueError as exc:
            keyword = '图片类型不支持' if str(exc) == '图片格式不支持' else str(exc)
            allowed = {
                '机器人无效',
                '图片已失效',
                '图片上传失败',
                '图片过大',
                '图片类型不支持',
                '图片正在发送',
                '图片清理失败',
                '图片名称无效',
                '表情已失效',
                '表情范围无效',
                '缩略图不可用',
                '上传数量已达上限',
                '待发送图片数量已达上限',
            }
            return errors.failure(keyword if keyword in allowed else '参数无效')
        except Exception:
            return errors.failure('操作失败')

    def _handle(self, action, p):
        ok = {'ok': True, 'keyword': '成功'}
        if action == 'Bootstrap':
            bots = [
                {'hash': key, 'id': str(getattr(bot, 'id', '')), 'unread': self.store.unread_total(key),
                 'mention_unread': self.store.mention_total(key)}
                for key, bot in self._bots().items()
            ]
            return dict(ok, bots=bots, settings=self.store.get_settings())
        if action == 'SaveSettings':
            values = p.get('settings', {})
            if not isinstance(values, dict):
                raise ValueError()
            global_values = {
                k: values[k]
                for k in (
                    'send_key',
                    'last_bot_hash',
                    'poll_interval_ms',
                    'image_retention_days',
                    'message_retention_days',
                    'notify_mention',
                    'notify_everyone',
                    'show_help',
                    'anti_recall',
                )
                if k in values
            }
            if 'send_key' in global_values and global_values['send_key'] not in ('enter_send', 'ctrl_enter_send'):
                raise ValueError()
            for key in ('notify_mention', 'notify_everyone', 'show_help', 'anti_recall'):
                if key in global_values and type(global_values[key]) is not bool:
                    raise ValueError()
            if (
                'last_bot_hash' in global_values
                and global_values['last_bot_hash'] not in self._bots()
                and global_values['last_bot_hash'] != ''
            ):
                raise ValueError()
            if 'poll_interval_ms' in global_values:
                global_values['poll_interval_ms'] = max(1000, min(60000, int(global_values['poll_interval_ms'])))
            for key in ('image_retention_days', 'message_retention_days'):
                if key in global_values:
                    days = global_values[key]
                    # 0 = 永久保留，不自动删除；上限 10 年，避免前端传进离谱数字。
                    if type(days) is not int or not 0 <= days <= 3650:
                        raise ValueError()
            local = {
                k: values[k]
                for k in ('view_limit_enabled', 'view_limit_mode', 'view_limit_count', 'view_limit_days')
                if k in values
            }
            if local:
                bot = p.get('bot_hash')
                if bot not in self._bots():
                    raise ValueError('机器人无效')
                if 'view_limit_mode' in local and local['view_limit_mode'] not in ('count', 'days'):
                    raise ValueError()
                if 'view_limit_enabled' in local and type(local['view_limit_enabled']) is not bool:
                    raise ValueError()
                for key in ('view_limit_count', 'view_limit_days'):
                    if key in local:
                        local[key] = max(1, min(100000, int(local[key])))
                self.store.set_settings(local, bot)
            with self._retention_lock:
                self.store.set_settings(global_values)
                if 'image_retention_days' in global_values:
                    self.media.cleanup_sent(global_values['image_retention_days'])
                if 'message_retention_days' in global_values:
                    # 立刻按新期限清一次，别让用户等下一个整点。
                    removed = 0
                    for bot_hash in self._bots():
                        removed += self.store.prune_messages(
                            bot_hash, global_values['message_retention_days']
                        )['deleted']
                    if removed:
                        self._clear_view_cache()
            return dict(ok, settings=self.store.get_settings())
        if action == 'Vacuum':
            # 全局维护动作，不需要 bot_hash；和每小时清理互斥，避免一边删一边整库重写。
            if not self._vacuum_lock.acquire(blocking=False):
                return errors.failure('回收正在进行中')
            try:
                with self._retention_lock:
                    return dict(ok, vacuum=self.store.vacuum_databases())
            finally:
                self._vacuum_lock.release()
        bot = p.get('bot_hash')
        if not isinstance(bot, str) or bot not in self._bots():
            raise ValueError('机器人无效')
        if action == 'GetSettings':
            return dict(ok, settings=self.store.get_settings(bot))
        if action == 'BotSelf':
            info = self.bot_self(bot)
            if not info:
                return errors.failure('机器人资料暂时不可用')
            return dict(ok, name=info['name'], avatar=info.get('avatar') or '')
        if action == 'FetchChatName':
            # 点开没显示群名/昵称的会话时自动补一次：群聊入队、单聊查成员缓存。
            chat_type = str(p.get('chat_type') or '')
            chat_id = str(p.get('chat_id') or '')
            if chat_type not in ('qq_group', 'qq_private') or not chat_id:
                return errors.failure('会话无效')
            state = self.store.ensure_chat_name(bot, chat_type, chat_id)
            if state['status'] == 'queued':
                self.wake_group_info()
            return dict(ok, **state)
        if action == 'ListChats':
            chats = self.store.list_chats(bot, bool(p.get('include_hidden')))
            status = self.store.group_info_status(bot)
            for chat in chats:
                flag = status.get(chat['chat_id']) if chat.get('chat_type') == 'qq_group' else None
                if flag:
                    chat['group_info_status'] = flag
            return dict(
                ok,
                chats=chats,
                unread={key: self.store.unread_total(key) for key in self._bots()},
                mention_unread={key: self.store.mention_total(key) for key in self._bots()},
            )
        if action == 'SearchGlobal':
            return dict(
                ok,
                **self.store.search_global(
                    bot, str(p.get('query') or p.get('keyword') or ''), bool(p.get('include_hidden'))
                ),
            )
        if action == 'UploadBegin':
            return dict(ok, **self.media.begin(p.get('name'), p.get('size'), p.get('mime') or '', bot))
        if action == 'UploadChunk':
            return dict(ok, **self.media.chunk(p.get('upload_id'), p.get('index'), p.get('data_b64'), bot))
        if action == 'UploadAbort':
            self.media.abort(p.get('upload_id'), bot)
            return ok
        if action.startswith('Sticker'):
            scope, ident = p.get('scope'), p.get('id')
            if action == 'StickerList':
                return dict(ok, stickers=self.media.list_emojis(scope, bot))
            if action == 'StickerSave':
                sticker = self.media.save(p.get('upload_id'), p.get('name'), scope, bot)
                self.media.abort(p.get('upload_id'), bot)
                return dict(ok, sticker=sticker)
            if action == 'StickerRename':
                return dict(ok, sticker=self.media.rename_emoji(ident, p.get('name'), scope, bot))
            if action == 'StickerDelete':
                self.media.delete_emoji(ident, scope, bot)
                return ok
            if action == 'StickerSelect':
                return dict(ok, **self.media.use_emoji(ident, scope, bot))
            if action == 'StickerRead':
                return dict(ok, **self.media.read_emoji_chunk(ident, scope, bot, p.get('index', 0)))
            return errors.failure('未知操作')
        chat_type, chat_id = p.get('chat_type'), p.get('chat_id')
        if chat_type not in ('qq_group', 'qq_private') or not isinstance(chat_id, str) or not chat_id.strip():
            return errors.failure('未选目标')
        if action == 'AttachmentRead':
            return self._incoming_image(bot, chat_type, chat_id, p.get('message_id'),
                                        p.get('attachment'), p.get('index', 0))
        if action == 'MessageImageRead':
            message_id, image_id = p.get('message_id'), p.get('image_id')
            if type(message_id) is not int or message_id <= 0 or not isinstance(image_id, str):
                raise ValueError('图片已失效')
            rows = self.store.get_messages_by_ids(bot, chat_type, chat_id, [message_id])
            if not rows or rows[0].get('direction') != 'out':
                raise ValueError('图片已失效')
            try:
                content = json.loads(rows[0]['content_json'])
                images = content.get('images', [])
                image = next(item for item in images if isinstance(item, dict) and item.get('image_id') == image_id)
            except (TypeError, ValueError, KeyError, AttributeError, StopIteration):
                raise ValueError('图片已失效') from None
            with self._retention_lock:
                return dict(
                    ok,
                    **self.media.read_sent_chunk(
                        image, p.get('index', 0), self.store.get_settings()['image_retention_days'],
                    ),
                )
        if action == 'MentionTarget':
            return dict(ok, **self.store.mention_target(bot, chat_type, chat_id))
        if action == 'UnreadState':
            # 打开会话时会话内全部会标为已读，所以前端必须在这之前取一次快照。
            return dict(ok, **self.store.unread_target(bot, chat_type, chat_id))
        if action in ('CachePut', 'CacheGet'):
            if 'index' in p:
                return self._view_cache_chunk(bot, chat_type, chat_id, p, action == 'CachePut')
            return errors.failure('缓存分片无效')
        if action == 'AddChat':
            chat = self.store.upsert_chat(bot, chat_type, chat_id, hidden=0)
            if chat_type == 'qq_group':
                self.store.enqueue_group_info(bot, chat_id)
                self.wake_group_info()
            return dict(ok, chat=chat)
        if action == 'SetRemark':
            remark = p.get('remark')
            if not isinstance(remark, str) or len(remark) > 255:
                raise ValueError()
            return dict(ok, chat=self.store.upsert_chat(bot, chat_type, chat_id, remark=remark))
        if action == 'ChatAction':
            if p.get('action') == 'read':
                if p.get('all') is True:
                    self.store.mark_read_all(bot, chat_type, chat_id)
                    return dict(ok, chat=self.store.get_chat(bot, chat_type, chat_id))
                ids = p.get('visible_ids')
                if not isinstance(ids, list) or len(ids) > 500 or any(type(x) is not int or x <= 0 for x in ids):
                    raise ValueError()
                self.store.mark_read_visible(bot, chat_type, chat_id, ids)
                return dict(ok, chat=self.store.get_chat(bot, chat_type, chat_id))
            # mute = 屏蔽本群：消息照收，但不计未读、不提醒 @（见 store.add_message）。
            field = {'pin': 'pinned', 'hide': 'hidden', 'mute': 'muted'}.get(p.get('action'))
            if field is None or type(p.get('value')) is not bool:
                raise ValueError()
            value = int(p['value'])
            return dict(ok, chat=self.store.upsert_chat(bot, chat_type, chat_id, **{field: value}))
        if action == 'PullMessages':
            ids = p.get('snapshot_ids')
            if ids is not None:
                if not isinstance(ids, list) or len(ids) > 500 or any(type(x) is not int or x <= 0 for x in ids):
                    raise ValueError()
                return dict(ok, messages=self.store.get_messages_by_ids(bot, chat_type, chat_id, ids))
            before, after, around = (
                p.get('before_id', p.get('before')),
                p.get('after_id', p.get('after')),
                p.get('around_id'),
            )
            limit = max(1, min(100, int(p.get('limit', 50))))
            if around is not None:
                around = int(around)
                older = self.store.list_messages(bot, chat_type, chat_id, before=around, limit=max(1, limit // 2))
                newer = self.store.list_messages(bot, chat_type, chat_id, after=around - 1, limit=limit - len(older))
                rows = (older + newer)[-limit:]
            else:
                rows = self.store.list_messages(
                    bot,
                    chat_type,
                    chat_id,
                    before=before,
                    after=after,
                    limit=limit,
                    initial=before is None and after is None,
                )
            if chat_type == 'qq_group' and before is None and after is None and around is None:
                chat = self.store.get_chat(bot, chat_type, chat_id)
                if not chat or time.time() - (chat.get('role_updated_at') or 0) >= 600:
                    self._role(self._event(bot), bot, chat_id)
            response = dict(ok, messages=rows)
            if 'change_cursor' in p:
                cursor = p['change_cursor']
                if cursor is not None and (type(cursor) is not int or cursor < 0):
                    raise ValueError()
                changes = self.store.message_changes(bot, chat_type, chat_id, after=cursor, limit=200)
                response.update(
                    changes=changes['changes'], change_cursor=changes['cursor'], change_reset=changes['reset']
                )
            return response
        if action == 'SearchChat':
            return dict(
                ok,
                messages=self.store.search_messages(
                    bot,
                    chat_type,
                    chat_id,
                    str(p.get('query') or p.get('keyword') or ''),
                    start=p.get('start_at'),
                    end=p.get('end_at'),
                    only_self=bool(p.get('only_self')),
                    include_failed=bool(p.get('include_failed', True)),
                    include_recalled=bool(p.get('include_recalled', True)),
                    limit=min(100, int(p.get('limit', 50))),
                    before=p.get('before_id'),
                ),
            )
        if action == 'PassiveStatus':
            return dict(ok, token=self.pool.status(bot, chat_type, chat_id))
        if action == 'ListMembers' and not p.get('refresh'):
            return dict(ok, members=self.roster.list_members(bot, chat_type, chat_id, str(p.get('query') or '')))
        event = self._event(bot)
        if action == 'RefreshRole':
            if chat_type != 'qq_group':
                raise ValueError()
            result, chat = self._role(event, bot, chat_id)
            return dict(result, chat=chat)
        if action == 'RefreshGroupName':
            if chat_type != 'qq_group':
                raise ValueError()
            # 手动刷新只入队，由唯一 worker 走同一条 FIFO 与限速，绝不越过队首冷却。
            self.store.enqueue_group_info(bot, chat_id)
            self.wake_group_info()
            chat = dict(self.store.get_chat(bot, chat_type, chat_id) or {})
            status = self.store.group_info_status(bot).get(str(chat_id)) or 'queued'
            chat['group_info_status'] = status
            return dict(ok, queued=True, group_info_status=status, keyword='排队获取中', chat=chat)
        if action == 'Send':
            text = str(p.get('text') or '') + str(p.get('markdown') or '')
            at_all = bool(re.search(r'<qqbot-at-everyone\b', text, re.I)) or any(
                isinstance(x, dict) and x.get('id') == 'all' for x in (p.get('at') or [])
            )
            payload = dict(p)
            sender = Sender(event, self.pool, self.media)
            if at_all:
                denied = (
                    errors.failure('请确认@全体')
                    if p.get('at_all_confirmed') is not True
                    else self._admin(event, bot, chat_type, chat_id)
                )
                if denied:
                    images = p.get('images')
                    if isinstance(images, list):
                        for image in images:
                            if isinstance(image, dict) and isinstance(image.get('upload_id'), str):
                                try:
                                    self.media.abort(image['upload_id'], bot)
                                except (ValueError, OSError):
                                    pass
                    result = denied
                else:
                    result = sender.send(payload)
            else:
                result = sender.send(payload)
            kind = p.get('kind', 'text')
            content = p.get('markdown') if kind == 'markdown' else p.get('text')
            content = content if isinstance(content, str) else ''
            card = p.get('card') if isinstance(p.get('card'), dict) else {}
            result['local_id'] = self.store.add_message(
                bot,
                chat_type,
                chat_id,
                {
                    'direction': 'out',
                    'platform_message_id': result.get('message_id'),
                    'ref_idx': result.get('ref_idx'),
                    'reply_to': p.get('quote_id'),
                    'sender_id': str(getattr(event.bot_info, 'id', '')),
                    'sender_name': '机器人',
                    'msg_kind': kind if kind in ('text', 'markdown', 'card') else 'unknown',
                    'content_text': content
                    if kind != 'card'
                    else str((card.get('content') if isinstance(card.get('content'), dict) else {}).get('title') or ''),
                    'content_json': {'text': content, 'card': card, 'has_image': bool(p.get('images')),
                                     'images': sender.sent_images},
                    'send_channel': result.get('channel'),
                    'error_code': result.get('error_code'),
                    'keyword': None if result.get('ok') and not result.get('pending_review') else result.get('keyword'),
                },
                unread=False,
            )
            result['images'] = sender.sent_images
            return result
        if action == 'Recall':
            # 官方接口只支持群聊消息撤回；单聊既不显示入口，这里也直接拒绝，不去打平台接口。
            if chat_type != 'qq_group':
                return errors.failure('单聊不支持撤回')
            message_id = p.get('platform_message_id') or p.get('message_id')
            if not isinstance(message_id, str) or not message_id:
                raise ValueError()
            with self.store.session(bot, chat_type, chat_id) as db:
                row = db.execute(
                    'SELECT * FROM messages WHERE platform_message_id=? ORDER BY id DESC LIMIT 1', (message_id,)
                ).fetchone()
                row = dict(row) if row else None
            if not row or row['recalled']:
                return errors.failure('消息不存在')
            if time.time() - row['created_at'] > 120:
                return errors.failure('撤回超时')
            if row['direction'] != 'out':
                denied = self._admin(event, bot, chat_type, chat_id)
                if denied:
                    return denied
            result = Sender(event, self.pool, self.media).recall(dict(p, message_id=message_id))
            if result['ok']:
                self.store.recall_message(bot, chat_type, chat_id, message_id)
            return result
        if action == 'JoinRequestList':
            if chat_type != 'qq_group':
                return errors.failure('无管理员权限')
            with self._jobs_lock:
                job = self._jobs.get((bot, chat_id))
            chat = self.store.get_chat(bot, chat_type, chat_id)
            if not p.get('refresh') and job is None and (not chat or chat.get('self_role') not in ('admin', 'owner')):
                return errors.failure('无管理员权限')
            return self._join_request_list(bot, chat_id, bool(p.get('refresh')))
        if action not in ('ListMembers', 'Admin', 'JoinRequestList', 'JoinRequestAct'):
            return errors.failure('未知操作')
        denied = self._admin(event, bot, chat_type, chat_id)
        if denied:
            return denied
        if action == 'ListMembers':
            cursor, seen = None, set()
            for _ in range(40):
                raw = OlivOS.qqGuildv2SDK.event_action.get_qq_group_member_list(event, chat_id, cursor)
                result = self._result(raw)
                if not result['ok']:
                    return result
                body = self._body(raw)
                for member in body.get('members', body.get('list', [])):
                    member_id = member.get('member_openid')
                    if member_id:
                        self.roster.upsert_member(
                            bot,
                            chat_type,
                            chat_id,
                            member_id,
                            member.get('name') or member.get('username'),
                            member.get('member_role'),
                        )
                cursor = body.get('next_cursor')
                if not cursor or cursor in seen:
                    break
                seen.add(cursor)
            return dict(ok, members=self.roster.list_members(bot, chat_type, chat_id))
        if action == 'Admin':
            operation = p.get('action')
            if operation == 'restrict_query':
                raw = event.indeAPI.get_qq_group_restrict_chat_setting(chat_id)
            elif operation == 'restrict_set':
                member = p.get('member_openid')
                duration = int(p.get('duration', 0))
                if not isinstance(member, str) or not member or duration < 0:
                    raise ValueError()
                raw = OlivOS.qqGuildv2SDK.event_action.set_qq_group_member_mute(event, chat_id, member, duration)
            elif operation == 'kick':
                # 官方批量移除接口（单次最多 20 人），这里一次只踢一个。
                # 权限已在前面统一过 _admin：普通成员拿不到这一步。
                member = p.get('member_openid')
                if not isinstance(member, str) or not member.strip():
                    raise ValueError()
                result = self.kick_group_member(
                    bot, chat_id, member.strip(), bool(p.get('add_to_member_blacklist'))
                )
                if result['ok']:
                    # 踢成功就把本地成员缓存里那一行删掉，资料卡不再显示这个人。
                    self.roster.remove_member(bot, chat_type, chat_id, member.strip())
                    result['message'] = '成员已移出群聊'
                return result
            else:
                raise ValueError()
            result = self._result(raw)
            if result['ok']:
                result['data'] = self._body(raw)
                if operation == 'restrict_query':
                    result['message'] = str(result['data'])[:1000]
            return result
        if action == 'JoinRequestAct':
            with self._jobs_lock:
                active_job = self._jobs.get((bot, chat_id))
                if active_job and active_job.get('finished') is None:
                    active_job['cancel'].set()
            op, request_id, member = p.get('op'), p.get('join_request_id'), p.get('member_openid')
            if (
                op not in ('approve', 'decline')
                or not isinstance(request_id, str)
                or not request_id
                or not isinstance(member, str)
                or not member
            ):
                raise ValueError()
            with self.store.session(bot, chat_type, chat_id) as db:
                found = db.execute(
                    "SELECT 1 FROM join_requests WHERE join_request_id=? AND member_openid=? AND status='pending'",
                    (request_id, member),
                ).fetchone()
            if not found:
                return errors.failure('申请已失效')
            raw = event.indeAPI.approve_qq_group_join_request(
                chat_id,
                member,
                op,
                join_request_id=request_id,
                reject_reason=p.get('reject_reason') or None,
                add_to_member_blacklist=bool(p.get('add_to_member_blacklist')),
            )
            result = self._result(raw)
            if result['ok']:
                self.roster.set_request_status(bot, chat_id, request_id, 'approved' if op == 'approve' else 'declined')
            return result
