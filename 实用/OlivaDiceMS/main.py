# -*- encoding: utf-8 -*-
import OlivOS
import OlivaDiceCore
import OlivaDiceMS


class Event(object):
    def init(plugin_event, Proc):
        OlivaDiceMS.msgReply.unity_init(plugin_event, Proc)

    def init_after(plugin_event, Proc):
        OlivaDiceMS.msgReply.data_init(plugin_event, Proc)

    def private_message(plugin_event, Proc):
        OlivaDiceMS.msgReply.unity_reply(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        OlivaDiceMS.msgReply.unity_reply(plugin_event, Proc)

    def poke(plugin_event, Proc):
        pass
