# -*- encoding: utf-8 -*-
"""
纯净事件入口模块。

1. 只做事件入口。
2. 不在这里写消息解析。
3. 不在这里写具体业务。
4. 所有消息处理统一转交给 message.py。
5. 所有初始化统一转交给 utils.py。
"""

from . import gui
from . import message
from . import utils
from . import webui


class Event(object):
    """OlivOS 识别的标准事件类。"""

    def init(plugin_event, Proc):
        """插件初始化入口"""
        utils.set_runtime_proc(Proc)
        utils.initialize_plugin(Proc)
        message.handle_init(plugin_event, Proc)

    def init_after(plugin_event, Proc):
        """插件数据初始化入口。"""
        utils.ensure_webui_assets(Proc)
        message.handle_init_after(plugin_event, Proc)

    def private_message(plugin_event, Proc):
        """私聊消息入口"""
        message.handle_private_message(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        """群聊消息入口"""
        message.handle_group_message(plugin_event, Proc)

    def menu(plugin_event, Proc):
        """菜单事件入口"""
        if getattr(getattr(plugin_event, 'data', None), 'webui', None) is not None:
            webui.handle_menu_event(plugin_event, Proc)
        else:
            gui.handle_menu_event(plugin_event, Proc)

