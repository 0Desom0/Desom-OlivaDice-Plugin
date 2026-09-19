# -*- encoding: utf-8 -*-
"""插件生命周期。页面由 OlivOS WebUI 注册和托管。"""

from . import utils


def handle_init(plugin_event, Proc) -> None:
    utils.info_log(Proc, 'QQBotMenuPanel init 完成。')


def handle_init_after(plugin_event, Proc) -> None:
    utils.set_runtime_proc(Proc)
    utils.info_log(Proc, '请在 OlivOS WebUI → 插件页面 → QQ菜单与指令面板 中打开配置。')


def handle_save(plugin_event, Proc) -> None:
    utils.debug_log(Proc, 'QQBotMenuPanel save 已执行。', plugin_event=plugin_event)
