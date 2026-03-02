# -*- encoding: utf-8 -*-
'''
安价插件事件处理器。
'''

import OlivOS
import OlivaDiceAnKa
import OlivaDiceCore


class Event(object):
    def init(plugin_event, Proc):
        OlivaDiceAnKa.msgReply.unity_init(plugin_event, Proc)

    def init_after(plugin_event, Proc):
        OlivaDiceAnKa.msgReply.data_init(plugin_event, Proc)

    def private_message(plugin_event, Proc):
        OlivaDiceAnKa.msgReply.unity_reply(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        OlivaDiceAnKa.msgReply.unity_reply(plugin_event, Proc)

    def poke(plugin_event, Proc):
        pass

    def menu(plugin_event, Proc):
        pass
