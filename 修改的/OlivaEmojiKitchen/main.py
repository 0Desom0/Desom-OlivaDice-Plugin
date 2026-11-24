# -*- encoding: utf-8 -*-
'''
@File      :   main.py
@Author    :   lunzhiPenxil仑质
@Contact   :   lunzhipenxil@gmail.com
@License   :   AGPL
@Copyright :   (C) 2020-2021, OlivOS-Team
@Desc      :   插件事件入口。数据每天 04:00 由 OlivOS 插件定时任务刷新，
               启动时若数据缺失或过期会在后台补一次。
'''

import OlivOS
import OlivaEmojiKitchen

# 定时任务依赖 OlivOS 1.0.5 起才有的 scheduleAPI。老核心没有这个模块时降级成空装饰器，
# 由 emojiUpdater 的看门狗线程按「数据过期」兜底，插件本身仍能正常加载。
_cron = getattr(getattr(OlivOS, 'scheduleAPI', None), 'cron', None)
if _cron is None:
    def _cron(*args, **kwargs):
        def wrap(callback):
            return callback
        return wrap


class Event(object):
    def init(plugin_event, Proc):
        # 看门狗常驻：数据缺失/过期时补一次，之后每 15 分钟检查一次
        OlivaEmojiKitchen.emojiUpdater.start_watchdog()

    @staticmethod
    @_cron(id='emoji_data_update', hour=4, minute=0)
    def emoji_data_update(Proc):
        # 宿主调度时区凌晨 4:00（conf/plugin_schedule.json，默认系统时区）
        OlivaEmojiKitchen.emojiUpdater.update(force=True)

    def private_message(plugin_event, Proc):
        OlivaEmojiKitchen.msgReply.unity_reply(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        OlivaEmojiKitchen.msgReply.unity_reply(plugin_event, Proc)
