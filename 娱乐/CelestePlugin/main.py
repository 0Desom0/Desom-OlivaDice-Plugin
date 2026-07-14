# -*- encoding: utf-8 -*-
"""CelestePlugin 的 OlivOS 事件入口。"""

from . import message
from . import utils


class Event(object):
    """OlivOS 标准事件类。"""

    def init(plugin_event, Proc):
        utils.set_runtime_proc(Proc)
        message.handle_init(plugin_event, Proc)

    def init_after(plugin_event, Proc):
        utils.initialize_plugin(Proc)
        message.handle_init_after(plugin_event, Proc)

    def private_message(plugin_event, Proc):
        message.handle_private_message(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        message.handle_group_message(plugin_event, Proc)

    def heartbeat(plugin_event, Proc):
        message.handle_heartbeat(plugin_event, Proc)

    def save(plugin_event, Proc):
        message.handle_save(plugin_event, Proc)
