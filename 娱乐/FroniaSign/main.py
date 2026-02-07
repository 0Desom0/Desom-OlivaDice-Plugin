# -*- encoding: utf-8 -*-
'''
这里是对应的msgReply.py的事件处理器，所有回复全在msgReply.py中处理。
若需要修改插件NameSpace，请使用VSCode或其他软件全局替换将FroniaSign替换为你的插件名称。
'''

import OlivOS
import FroniaSign
import OlivaDiceCore

class Event(object):
    def init(plugin_event, Proc):
        # 初始化插件时调用
        # 这里可以进行一些全局的初始化工作，比如加载配置文件、初始化数据
        FroniaSign.msgReply.unity_init(plugin_event, Proc)

    def init_after(plugin_event, Proc):
        # 在所有插件初始化完成后调用
        # 这里可以进行一些依赖于其他插件的初始化工作
        FroniaSign.msgReply.data_init(plugin_event, Proc)

    def private_message(plugin_event, Proc):
        # 私聊消息处理
        FroniaSign.msgReply.unity_reply(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        # 群聊消息处理
        FroniaSign.msgReply.unity_reply(plugin_event, Proc)

    def poke(plugin_event, Proc):
        # 戳一戳事件处理
        # 这里可以添加戳一戳的处理逻辑
        pass
    
    def menu(plugin_event, Proc):
        # 菜单事件处理
        # 这里可以添加菜单事件的处理逻辑
        # if plugin_event.data.namespace == 'FroniaSign':
        #     if plugin_event.data.event == 'FroniaSign_Menu_001':
        #         pass
        #     elif plugin_event.data.event == 'FroniaSign_Menu_002':
        #         pass
        pass