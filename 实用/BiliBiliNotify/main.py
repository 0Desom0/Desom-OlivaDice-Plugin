from OlivOS.core.core import scheduleAPI

from . import message, notify, store, webui


def _bot_hashes(Proc):
    """宿主注入的账号表可能缺失或不是字典，缺省按空表处理。"""
    proc_data = getattr(Proc, 'Proc_data', None)
    bot_info_dict = proc_data.get('bot_info_dict') if isinstance(proc_data, dict) else None
    return list(bot_info_dict) if isinstance(bot_info_dict, dict) else []


class Event:
    @staticmethod
    def init(plugin_event, Proc):
        # 宿主注册并缓存 app.json 声明的 WebUI，解包清理后不读源码目录。
        try:
            store.global_config()
            for bot_hash in _bot_hashes(Proc):
                store.load_bot(bot_hash)
        except Exception as error:  # 磁盘不可写时也要让插件加载完成，运行期再报错
            store.log(Proc, f'初始化读取配置失败：{type(error).__name__}', level=3)

    @staticmethod
    def init_after(plugin_event, Proc):
        notify.start(Proc)

    @staticmethod
    def group_message(plugin_event, Proc):
        message.handle_message(plugin_event, Proc)

    @staticmethod
    def private_message(plugin_event, Proc):
        message.handle_message(plugin_event, Proc)

    @staticmethod
    def menu(plugin_event, Proc):
        webui.handle_menu_event(plugin_event, Proc)

    @staticmethod
    def save(plugin_event, Proc):
        notify.stop(Proc)

    @staticmethod
    @scheduleAPI.interval('bili_tick', seconds=1, run_on_start=True)  # core/core/scheduleAPI.py
    def bili_tick(Proc):
        # 宿主 scheduler 只投递；网络、落盘与发送都交给工作线程。
        notify.tick(Proc)
