# -*- encoding: utf-8 -*-
"""OlivOS 事件入口。"""

from . import message
from . import utils


class Event(object):
    """OlivOS 标准事件类。"""

    def init(plugin_event, Proc):
        """插件初始化入口。"""
        utils.set_runtime_proc(Proc)
        utils.initialize_plugin(Proc)
        message.handle_init(plugin_event, Proc)

    def init_after(plugin_event, Proc):
        """所有插件初始化后的入口。"""
        message.handle_init_after(plugin_event, Proc)

    def private_message(plugin_event, Proc):
        """私聊消息入口。"""
        message.handle_private_message(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        """群聊消息入口。"""
        message.handle_group_message(plugin_event, Proc)

    def save(plugin_event, Proc):
        """保存事件入口。"""
        message.handle_save(plugin_event, Proc)

