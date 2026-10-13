"""OlivOS 生命周期、命令入口与官方 WebUI 消息桥。"""

import hashlib
import traceback

from . import api, commands, gui, runtime
from .store import InvalidInput


def error_location(exc):
    return '\n'.join(
        f'{frame.filename}:{frame.lineno} in {frame.name}' for frame in traceback.extract_tb(exc.__traceback__)
    )


class Event:
    @staticmethod
    def init(plugin_event, Proc):
        pass

    @staticmethod
    def init_after(plugin_event, Proc):
        try:
            runtime.install(Proc)
            Proc.log(2, 'MultiCustomSwitch: 已接入 Core，自定义回复管理就绪。')
        except Exception as exc:
            runtime.uninstall()
            runtime.INIT_ERROR = f'初始化失败（{type(exc).__name__}），请查看 OlivOS 日志中的调用位置。'
            # 输出调用位置与异常类型，不记录配置内容、账号凭据或网络请求信息。
            Proc.log(4, f'MultiCustomSwitch: {runtime.INIT_ERROR}\n{error_location(exc)}')

    @staticmethod
    def group_message(plugin_event, Proc):
        commands.handle(plugin_event, Proc)

    @staticmethod
    def private_message(plugin_event, Proc):
        commands.handle(plugin_event, Proc)

    @staticmethod
    def save(plugin_event, Proc):
        api.clear_transfers()
        runtime.uninstall()

    @staticmethod
    def menu(plugin_event, Proc):
        if getattr(plugin_event.data, 'namespace', None) != 'MultiCustomSwitch':
            return
        context = getattr(plugin_event.data, 'webui', None)
        if not isinstance(context, dict):
            if getattr(plugin_event.data, 'event', None) == 'MultiCustomSwitch_Open':
                try:
                    gui.open_window()
                except Exception as exc:
                    Proc.log(
                        4,
                        f'MultiCustomSwitch: 桌面管理窗口无法打开（{type(exc).__name__}）。\n'
                        f'{runtime.INIT_ERROR or ""}\n{error_location(exc)}',
                    )
            return
        request_id = context.get('request_id')
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            return
        try:
            if plugin_event.data.event != api.EVENT:
                raise InvalidInput('未知的 WebUI 事件。')
            # 传输绑定当前登录会话的摘要；不保存或返回会话原文。
            owner = hashlib.sha256(str(context.get('session', '')).encode('utf-8')).hexdigest()
            response = {'ok': True, 'result': api.bridge(getattr(plugin_event.data, 'payload', None), owner)}
        except (InvalidInput, ValueError, OSError, UnicodeError) as exc:
            response = {'ok': False, 'error': str(exc)}
        except Exception:
            Proc.log(4, 'MultiCustomSwitch: 管理请求处理失败。')
            response = {'ok': False, 'error': '处理失败，请查看 OlivOS 日志。'}
        plugin_event.send('webui', request_id, response)
