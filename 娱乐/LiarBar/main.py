# -*- encoding: utf-8 -*-
'''
这里是对应的msgReply.py的事件处理器，所有回复全在msgReply.py中处理。
若需要修改插件NameSpace，请使用VSCode或其他软件全局替换将LiarBar替换为你的插件名称。
'''

import OlivOS
import LiarBar
import OlivaDiceCore


class Event(object):
    def init(plugin_event, Proc):
        LiarBar.msgReply.unity_init(plugin_event, Proc)

    def init_after(plugin_event, Proc):
        LiarBar.msgReply.data_init(plugin_event, Proc)

    def private_message(plugin_event, Proc):
        LiarBar.msgReply.unity_reply(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        LiarBar.msgReply.unity_reply(plugin_event, Proc)

    def poke(plugin_event, Proc):
        pass

    def menu(plugin_event, Proc):
        pass
