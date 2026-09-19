# -*- encoding: utf-8 -*-
"""OlivOS 事件入口。"""

from . import message, utils, webui


class Event(object):
    def init(plugin_event, Proc):
        utils.set_runtime_proc(Proc)
        utils.initialize_plugin(Proc)
        message.handle_init(plugin_event, Proc)

    def init_after(plugin_event, Proc):
        message.handle_init_after(plugin_event, Proc)

    def save(plugin_event, Proc):
        message.handle_save(plugin_event, Proc)

    def menu(plugin_event, Proc):
        webui.handle_menu_event(plugin_event, Proc)
