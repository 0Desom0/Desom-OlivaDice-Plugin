"""按事件隔离 OneDice 调用，使用原发送通路插入 HUD；不修改 Core 源文件。"""

import inspect
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps

from .commands import is_command

_MISSING = object()
_STATE_ATTRIBUTE = '_statushud_message_state'
_TARGET_MODULES = frozenset({
    'OlivaDiceCore.msgReply', 'OlivaDiceCore.msgReplyModel',
    'OlivaDiceShouHun.msgReply', 'OlivaDiceSanchi.msgReply', 'OlivaDiceMS.msgReply', 'OlivaDiceTA.msgReply',
})
_NOTICE_KEYS = frozenset({
    'strShHideShow', 'strShHideShowAtOther',
    'strTQHideShow', 'strTQHideShowMore', 'strTQHideShowAtOther', 'strTQHideShowAtOtherMore',
    'strTQAHideShow', 'strTQAHideShowAtOther',
})


@dataclass(frozen=True)
class Target:
    user_id: str
    platform: str
    hag_id: str | None


@dataclass
class MessageState:
    owner: object
    bot_hash: str
    default_target: Target
    rolls: dict = field(default_factory=dict)
    confirmed: set = field(default_factory=set)
    notices: list = field(default_factory=list)
    sent: dict = field(default_factory=dict)
    lock: object = field(default_factory=threading.RLock)


@dataclass
class Invocation:
    state: MessageState
    event: object
    proxy_target: Target | None = None


class HookManager:
    def __init__(self, olivos, core, proc, storage, sn_provider):
        self.olivos = olivos
        self.core = core
        self.proc = proc
        self.storage = storage
        self.sn_provider = sn_provider
        self.active = False
        self.patches = []
        self.state_lock = threading.RLock()
        self.current = ContextVar('StatusHud.invocation', default=None)
        self.roll_depth = ContextVar('StatusHud.roll_depth', default=0)
        self.suppress = ContextVar('StatusHud.suppress_notice', default=False)

    def log(self, message, error=None):
        # 不记录原消息、sn、人物卡内容或异常中可能包含的私有数据。
        detail = f'（{type(error).__name__}）' if error is not None else ''
        try:
            self.proc.log(4, f'StatusHud：{message}{detail}', [('StatusHud', 'default')])
        except Exception:
            pass

    def _patch(self, owner, name, wrapper):
        previous = vars(owner).get(name, _MISSING)
        setattr(owner, name, wrapper)
        self.patches.append((owner, name, previous, wrapper))

    def install(self):
        old = getattr(self.proc, '_statushud_hook_manager', None)
        if old is not None and old is not self:
            old.uninstall()
        self.active = True
        self._install_router()
        self._install_roll()
        self._install_proxy()
        self._install_save_record()
        self._install_notice_formatter()
        self._install_notice()
        self._install_outputs()
        self._install_markdown()
        self.proc._statushud_hook_manager = self

    def uninstall(self):
        self.active = False
        for owner, name, previous, wrapper in reversed(self.patches):
            # 其他插件已包裹本函数时保留其包装，本管理器停用后仅转交原函数。
            if getattr(owner, name, None) is wrapper:
                if previous is _MISSING:
                    delattr(owner, name)
                else:
                    setattr(owner, name, previous)
        self.patches.clear()
        if getattr(self.proc, '_statushud_hook_manager', None) is self:
            delattr(self.proc, '_statushud_hook_manager')

    def _state(self, event):
        if not self.active or event.plugin_info.get('func_type') not in ('group_message', 'private_message'):
            return None
        with self.state_lock:
            existing = getattr(event, _STATE_ATTRIBUTE, None)
            if existing is not None and existing.owner is self:
                return existing
            if not is_command(event, self.olivos, self.core):
                return None
            hag_id = None
            if event.plugin_info['func_type'] == 'group_message':
                group_id = str(event.data.group_id)
                host_id = getattr(event.data, 'host_id', None)
                hag_id = f'{host_id}|{group_id}' if host_id is not None else group_id
            target = Target(str(event.data.user_id), event.platform['platform'], hag_id)
            state = MessageState(self, str(event.bot_info.hash), target)
            setattr(event, _STATE_ATTRIBUTE, state)
            return state

    def _context(self, event=None):
        if not self.active:
            return None
        invocation = self.current.get()
        if event is None:
            return invocation
        if invocation is not None and str(event.bot_info.hash) == invocation.state.bot_hash:
            # 同一处理调用中的合成 Event 仍属于原指令；跨消息通过 ContextVar 隔离。
            return invocation
        state = getattr(event, _STATE_ATTRIBUTE, None)
        if state is not None and state.owner is self:
            return Invocation(state, event)
        return None

    def _install_router(self):
        original = self.proc.plugin_event_router

        @wraps(original)
        def route(plugin_event, plugin_model, plugin_name):
            if not self.active:
                return original(plugin_event, plugin_model, plugin_name)
            try:
                state = self._state(plugin_event)
            except Exception as error:
                self.log('建立消息上下文失败，继续原处理', error)
                state = None
            token = self.current.set(Invocation(state, plugin_event) if state is not None else None)
            try:
                return original(plugin_event, plugin_model, plugin_name)
            finally:
                self.current.reset(token)

        self._patch(self.proc, 'plugin_event_router', route)

    def _stack_context(self):
        # 支持携带原 Event 的工作线程；不把某个用户的状态放在线程全局变量中。
        frame = inspect.currentframe()
        try:
            for _ in range(80):
                if frame is None:
                    break
                for name in ('plugin_event', 'event'):
                    event = frame.f_locals.get(name)
                    if isinstance(event, self.olivos.API.Event):
                        state = self._state(event)
                        if state is not None:
                            return Invocation(state, event)
                frame = frame.f_back
        finally:
            del frame
        return None

    def _roll_target(self, invocation, rd):
        # 读取已核对的处理变量；不按任意 at 猜测代投，也不依赖插件的全局骰点记录。
        frame = inspect.currentframe()
        try:
            for _ in range(80):
                if frame is None:
                    break
                module = frame.f_globals.get('__name__')
                if module in _TARGET_MODULES:
                    values = frame.f_locals
                    user_id = None
                    if frame.f_code.co_name in ('team_r', 'team_ra', 'team_sc', 'team_st'):
                        user_id = values.get('member_id')
                    if module == 'OlivaDiceSanchi.msgReply':
                        if values.get('rd_my') is rd:
                            user_id = values.get('my_pc_id')
                        elif values.get('rd_other') is rd:
                            user_id = values.get('other_pc_id')
                    if user_id is None and module in ('OlivaDiceMS.msgReply', 'OlivaDiceTA.msgReply'):
                        user_id = values.get('target_user_id')
                    if user_id is None:
                        user_id = values.get('tmp_pc_id')
                    if user_id is not None:
                        default = invocation.state.default_target
                        platform = values.get('tmp_pc_platform', default.platform)
                        hag_id = values.get('tmp_hagID', default.hag_id)
                        return Target(str(user_id), platform, hag_id), True
                frame = frame.f_back
        finally:
            del frame
        return invocation.proxy_target or invocation.state.default_target, invocation.proxy_target is not None

    def _install_roll(self):
        rd_class = self.core.onedice.RD
        original = rd_class.roll

        @wraps(original)
        def roll(rd, *args, **kwargs):
            if not self.active:
                return original(rd, *args, **kwargs)
            try:
                invocation = self._context() or self._stack_context()
                if invocation is not None and self.roll_depth.get() == 0:
                    target, confirmed = self._roll_target(invocation, rd)
                    with invocation.state.lock:
                        invocation.state.rolls[id(rd)] = (rd, target)
                        if confirmed:
                            invocation.state.confirmed.add(id(rd))
            except Exception as error:
                self.log('记录 OneDice 调用失败，继续原骰点', error)
                invocation = self._context()
            token = self.roll_depth.set(self.roll_depth.get() + 1)
            context_token = self.current.set(invocation)
            try:
                return original(rd, *args, **kwargs)
            finally:
                self.current.reset(context_token)
                self.roll_depth.reset(token)

        self._patch(rd_class, 'roll', roll)

    def _install_proxy(self):
        original = self.core.msgReply.parse_at_user

        @wraps(original)
        def parse_at(plugin_event, *args, **kwargs):
            result = original(plugin_event, *args, **kwargs)
            invocation = self._context(plugin_event)
            if invocation is not None and result[0] and result[1] is not None:
                default = invocation.state.default_target
                invocation.proxy_target = Target(str(result[1]), default.platform, default.hag_id)
            return result

        self._patch(self.core.msgReply, 'parse_at_user', parse_at)

    def _install_save_record(self):
        original = self.core.onediceOverride.saveRDDataUser
        signature = inspect.signature(original)

        @wraps(original)
        def save_record(*args, **kwargs):
            # 第三方若使用 Core 骰点记录接口，可以取得其实际 userId。
            if self.active:
                try:
                    invocation = self._context() or self._stack_context()
                    values = signature.bind(*args, **kwargs).arguments
                    if invocation is not None and str(values['botHash']) == invocation.state.bot_hash:
                        rd = values['data']
                        with invocation.state.lock:
                            if id(rd) in invocation.state.rolls and id(rd) not in invocation.state.confirmed:
                                target = Target(
                                    str(values['userId']), values['platform'], invocation.state.default_target.hag_id,
                                )
                                invocation.state.rolls[id(rd)] = (rd, target)
                except Exception as error:
                    self.log('同步骰点目标失败，继续原记录', error)
            return original(*args, **kwargs)

        self._patch(self.core.onediceOverride, 'saveRDDataUser', save_record)

    def _notice_template(self, data):
        frame = inspect.currentframe()
        try:
            for _ in range(80):
                if frame is None:
                    break
                if frame.f_globals.get('__name__') in _TARGET_MODULES:
                    values = frame.f_locals
                    if values.get('flag_hide') and values.get('flag_is_from_group'):
                        templates = values.get('dictStrCustom', {})
                        if any(key in templates and data == templates[key] for key in _NOTICE_KEYS):
                            return True
                frame = frame.f_back
        finally:
            del frame
        return False

    def _install_notice_formatter(self):
        original = self.core.msgCustomManager.formatReplySTR

        @wraps(original)
        def format_reply(data, *args, **kwargs):
            # 格式化仅执行一次，兼容自定义回复、随机分支和变量展开。
            result = original(data, *args, **kwargs)
            if self.active:
                try:
                    invocation = self._context() or self._stack_context()
                    if invocation is not None and self._notice_template(data) and isinstance(result, str):
                        with invocation.state.lock:
                            invocation.state.notices.append(result)
                except Exception as error:
                    self.log('标记暗骰提示失败，继续原格式化', error)
            return result

        self._patch(self.core.msgCustomManager, 'formatReplySTR', format_reply)

    def _hidden_notice(self, event, message):
        if event.plugin_info.get('func_type') != 'group_message' or not isinstance(message, str):
            return False
        invocation = self._context(event)
        if invocation is not None:
            with invocation.state.lock:
                if any(message.rstrip(' ') == notice.rstrip(' ') for notice in invocation.state.notices):
                    return True
        frame = inspect.currentframe()
        try:
            for _ in range(80):
                if frame is None:
                    break
                if frame.f_globals.get('__name__') in ('OlivaDiceCore.msgReply', 'OlivaDiceCore.msgReplyModel'):
                    values = frame.f_locals
                    if (
                        values.get('plugin_event') is event
                        and values.get('flag_hide_roll')
                        and values.get('flag_is_from_group')
                        and values.get('tmp_reply_str_show') == message
                    ):
                        return True
                frame = frame.f_back
        finally:
            del frame
        return False

    def _install_notice(self):
        original = self.core.msgReply.replyMsg

        @wraps(original)
        def reply(plugin_event, message, *args, **kwargs):
            suppressed = self.suppress.get()
            if self.active and self._context(plugin_event) is not None:
                suppressed = suppressed or self._hidden_notice(plugin_event, message)
            token = self.suppress.set(suppressed)
            try:
                return original(plugin_event, message, *args, **kwargs)
            finally:
                self.suppress.reset(token)

        self._patch(self.core.msgReply, 'replyMsg', reply)

    def _prepare(self, event, message, route, string_channel=None):
        invocation = self._context(event)
        if invocation is None or self.suppress.get():
            return message
        state = invocation.state
        with state.lock:
            targets = dict.fromkeys(target for _, target in state.rolls.values())
            sent = state.sent.setdefault(route, set())
            lines, selected = [], []
            for target in targets:
                if target in sent:
                    continue
                try:
                    if not self.storage.status(state.bot_hash, target.user_id, target.platform)['enabled']:
                        continue
                    text = self.sn_provider.get(target.user_id, target.platform, target.hag_id)
                    if text:
                        lines.append(text)
                        selected.append(target)
                except Exception as error:
                    self.log('读取 HUD 失败，保留原结果', error)
            if not lines:
                return message
            try:
                hud = '\n'.join(lines)
                hud = self.core.censorAPI.doCensorReplaceOlivOSSafe(botHash=state.bot_hash, msg=hud)
                if not hud.strip():
                    return message
                if isinstance(message, self.olivos.messageAPI.Message_templet):
                    original = message
                else:
                    original = self.olivos.messageAPI.Message_templet(
                        event.plugin_info.get('message_mode_tx', 'old_string'), message,
                    )
                if not original.active:
                    return message
                channel = string_channel or event.plugin_info.get('message_mode_rx')
                if channel in ('old_string', 'olivos_string'):
                    hud = hud.replace('&', '&amp;').replace('[', '&#91;').replace(']', '&#93;')
                hud = '\n'.join(f'『{line}』' for line in hud.splitlines()) + '\n\n'
                result = self.olivos.messageAPI.Message_templet(
                    'olivos_para', [self.olivos.messageAPI.PARA.text(hud), *original.data],
                )
                sent.update(selected)
                return result
            except Exception as error:
                self.log('拼接 HUD 失败，保留原结果', error)
                return message

    @staticmethod
    def _reply_route(event):
        host_id = getattr(event.data, 'host_id', None)
        if event.plugin_info.get('func_type') == 'group_message':
            return 'group', str(event.data.group_id), str(host_id)
        return 'private', str(event.data.user_id), str(host_id)

    def _deliver(self, original, event, message, route, args, kwargs):
        try:
            decorated = self._prepare(event, message, route) if self.active else message
        except Exception as error:
            self.log('HUD 发送接入失败，保留原结果', error)
            decorated = message
        return original(event, decorated, *args, **kwargs)

    def _install_outputs(self):
        event_class = self.olivos.API.Event
        original_reply = event_class.reply
        original_send = event_class.send

        @wraps(original_reply)
        def reply(event, message, *args, **kwargs):
            remote = args[1] if len(args) > 1 else kwargs.get('remote', False)
            if not self.active or remote:
                return original_reply(event, message, *args, **kwargs)
            try:
                route = self._reply_route(event)
            except (AttributeError, KeyError):
                return original_reply(event, message, *args, **kwargs)
            return self._deliver(original_reply, event, message, route, args, kwargs)

        @wraps(original_send)
        def send(event, send_type, target_id, message, *args, **kwargs):
            remote = args[2] if len(args) > 2 else kwargs.get('remote', False)
            if send_type not in ('private', 'group') or not self.active or remote:
                return original_send(event, send_type, target_id, message, *args, **kwargs)
            host_id = args[0] if args else kwargs.get('host_id')
            route = send_type, str(target_id), str(host_id)
            try:
                decorated = self._prepare(event, message, route)
            except Exception as error:
                self.log('HUD 主动发送接入失败，保留原结果', error)
                decorated = message
            return original_send(event, send_type, target_id, decorated, *args, **kwargs)

        self._patch(event_class, 'reply', reply)
        self._patch(event_class, 'send', send)

    def _install_markdown(self):
        # 此通路直接调用 indeAPI，必须在 Core 的 Markdown 入口补充。
        original = getattr(self.core.msgReply, '_replyMsgMarkdownQQGuildv2', None)
        if original is None:
            return

        @wraps(original)
        def markdown(plugin_event, message):
            decorated = message
            if self.active:
                decorated = self._prepare(plugin_event, message, self._reply_route(plugin_event), 'old_string')
            if isinstance(decorated, self.olivos.messageAPI.Message_templet):
                decorated = decorated.get('old_string')
            return original(plugin_event, decorated)

        self._patch(self.core.msgReply, '_replyMsgMarkdownQQGuildv2', markdown)
