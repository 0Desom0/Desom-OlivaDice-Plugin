# -*- encoding: utf-8 -*-
"""插件生命周期。配置走 WebUI，不再处理聊天命令。"""

from . import utils


def handle_init(plugin_event, Proc) -> None:
    utils.info_log(Proc, 'QQBotMenuPanel init 完成。')


def handle_init_after(plugin_event, Proc) -> None:
    try:
        from . import webui
        result = webui.sync_from_config()
        if result.get('running'):
            utils.info_log(Proc, 'WebUI 已启动：%s' % result.get('url'))
        elif result.get('message') and not result.get('ok'):
            utils.error_log(Proc, 'WebUI 启动失败：%s' % result.get('message'))
    except Exception as exception_object:
        utils.error_log(Proc, 'WebUI 同步失败：%s' % utils.exception_text(exception_object))
    utils.debug_log(Proc, 'QQBotMenuPanel init_after 已执行。', plugin_event=plugin_event)


def handle_save(plugin_event, Proc) -> None:
    try:
        from . import webui
        if webui.is_running():
            webui.stop()
            utils.info_log(Proc, '插件重载：WebUI 已断开，重载完成后会按开关重新连上。')
    except Exception as exception_object:
        utils.error_log(Proc, '重载前停止 WebUI 失败：%s' % utils.exception_text(exception_object))
    utils.debug_log(Proc, 'QQBotMenuPanel save 已执行。', plugin_event=plugin_event)
