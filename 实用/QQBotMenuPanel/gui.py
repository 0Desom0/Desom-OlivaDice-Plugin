# -*- encoding: utf-8 -*-
"""桌面 GUI 只保留 WebUI 开关、地址和端口。真正的配置面板在浏览器里。"""

import tkinter
from tkinter import messagebox
from tkinter import ttk

from . import config
from . import help_docs
from . import utils
from . import webui

dict_color_context = {
    'color_001': '#00A0EA',
    'color_002': '#BBE9FF',
    'color_003': '#40C3FF',
    'color_004': '#FFFFFF',
    'color_005': '#000000',
    'color_006': '#80D7FF',
}


class QQBotMenuPanelGui(object):
    def __init__(self, bot_info_dict=None, current_bot_hash: str = '', Proc=None):
        self.bot_info_dict = bot_info_dict if isinstance(bot_info_dict, dict) else {}
        self.current_bot_hash = utils.safe_str(current_bot_hash)
        self.Proc = Proc
        self.root = None
        self._syncing = False

    def create_root_window(self):
        if tkinter._default_root is None:
            return tkinter.Tk()
        return tkinter.Toplevel()

    def create_native_button(self, parent_widget, text, command, width=12):
        button_widget = tkinter.Button(
            parent_widget,
            text=text,
            command=command,
            bd=0,
            activebackground=dict_color_context['color_002'],
            activeforeground=dict_color_context['color_001'],
            bg=dict_color_context['color_003'],
            fg=dict_color_context['color_004'],
            relief='groove',
            height=2,
            width=width,
        )
        button_widget.bind('<Enter>', lambda _event: button_widget.configure(bg=dict_color_context['color_006']))
        button_widget.bind('<Leave>', lambda _event: button_widget.configure(bg=dict_color_context['color_003']))
        return button_widget

    def create_form_label(self, parent_widget, text, width=8):
        return tkinter.Label(
            parent_widget,
            text=text,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 11, 'bold'),
            width=width,
            anchor='w',
        )

    def handle_combobox_mousewheel(self, _event) -> str:
        return 'break'

    def start(self) -> None:
        self.root = self.create_root_window()
        self.root.title(config.gui_window_title)
        self.root.geometry('580x420')
        self.root.minsize(540, 380)
        self.root.configure(bg=dict_color_context['color_001'])
        self.root.resizable(False, False)

        self.webui_enable_var = tkinter.StringVar(value=help_docs.bool_to_choice(webui.is_enabled()))
        self.host_var = tkinter.StringVar(value=webui.get_webui_host())
        self.port_var = tkinter.StringVar(value=str(webui.get_webui_port()))
        self.status_var = tkinter.StringVar(value='')

        page = tkinter.Frame(self.root, bg=dict_color_context['color_001'])
        page.pack(fill=tkinter.BOTH, expand=True, padx=18, pady=16)

        title_label = tkinter.Label(
            page,
            text='WebUI 开关',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 14, 'bold'),
            anchor='w',
        )
        title_label.pack(fill=tkinter.X)

        hint_label = tkinter.Label(
            page,
            text='配置面板请在浏览器打开。本窗口负责开关、地址和端口。\n'
                 '默认 127.0.0.1:3738。需要局域网或外部访问可改成 0.0.0.0。',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 10),
            justify='left',
            anchor='w',
        )
        hint_label.pack(fill=tkinter.X, pady=(8, 12))

        switch_row = tkinter.Frame(page, bg=dict_color_context['color_001'])
        switch_row.pack(fill=tkinter.X, pady=(0, 8))
        self.create_form_label(switch_row, 'WebUI').pack(side=tkinter.LEFT)
        switch_box = ttk.Combobox(
            switch_row,
            textvariable=self.webui_enable_var,
            values=help_docs.option_labels(help_docs.BOOL_OPTIONS),
            state='readonly',
            width=16,
        )
        switch_box.pack(side=tkinter.LEFT)
        switch_box.bind('<MouseWheel>', self.handle_combobox_mousewheel)

        host_row = tkinter.Frame(page, bg=dict_color_context['color_001'])
        host_row.pack(fill=tkinter.X, pady=(0, 8))
        self.create_form_label(host_row, '地址').pack(side=tkinter.LEFT)
        tkinter.Entry(host_row, textvariable=self.host_var, width=28).pack(
            side=tkinter.LEFT, fill=tkinter.X, expand=True,
        )

        port_row = tkinter.Frame(page, bg=dict_color_context['color_001'])
        port_row.pack(fill=tkinter.X, pady=(0, 8))
        self.create_form_label(port_row, '端口').pack(side=tkinter.LEFT)
        tkinter.Entry(port_row, textvariable=self.port_var, width=16).pack(side=tkinter.LEFT)

        status_label = tkinter.Label(
            page,
            textvariable=self.status_var,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 10),
            justify='left',
            anchor='nw',
        )
        status_label.pack(fill=tkinter.BOTH, expand=True, pady=(4, 10))

        button_row = tkinter.Frame(page, bg=dict_color_context['color_001'])
        button_row.pack(fill=tkinter.X, side=tkinter.BOTTOM)
        self.create_native_button(button_row, '应用设置', self.apply_switch, width=12).pack(
            side=tkinter.LEFT, padx=(0, 8),
        )
        self.create_native_button(button_row, '打开浏览器', self.open_browser, width=12).pack(
            side=tkinter.LEFT, padx=(0, 8),
        )
        self.create_native_button(button_row, '刷新状态', self.refresh_status, width=12).pack(
            side=tkinter.LEFT, padx=(0, 8),
        )
        self.create_native_button(button_row, '关闭窗口', self.root.destroy, width=12).pack(side=tkinter.RIGHT)

        self.refresh_status()
        self.root.mainloop()

    def apply_switch(self) -> None:
        if self._syncing:
            return
        enabled = help_docs.choice_to_bool(self.webui_enable_var.get())
        result = webui.apply_settings(self.host_var.get(), self.port_var.get(), enabled)
        self.refresh_status(result)
        if not result.get('ok'):
            messagebox.showerror(config.gui_window_title, result.get('message') or 'WebUI 设置失败')
            self.refresh_status()
            return
        if enabled and result.get('running'):
            webui.open_in_browser()

    def refresh_status(self, result=None) -> None:
        if result is None:
            result = {
                'ok': True,
                'running': webui.is_running(),
                'url': webui.get_webui_url(),
                'message': '当前状态',
            }
        enabled_text = '开启' if webui.is_enabled() else '关闭'
        running_text = '运行中' if result.get('running') else '未运行'
        self.status_var.set(
            '开关：%s\n运行：%s\n监听：%s:%s\n打开：%s\n说明：%s'
            % (
                enabled_text,
                running_text,
                webui.get_webui_host(),
                webui.get_webui_port(),
                result.get('url') or webui.get_webui_url(),
                result.get('message') or '',
            ),
        )
        self._syncing = True
        try:
            self.webui_enable_var.set(help_docs.bool_to_choice(webui.is_enabled()))
            self.host_var.set(webui.get_webui_host())
            self.port_var.set(str(webui.get_webui_port()))
        finally:
            self._syncing = False

    def open_browser(self) -> None:
        if not webui.is_running():
            messagebox.showinfo(config.gui_window_title, 'WebUI 还没开。先把开关打到「开启 True」并应用设置。')
            return
        webui.open_in_browser()


def open_config_window(bot_info_dict=None, current_bot_hash: str = '', Proc=None) -> None:
    gui_instance = QQBotMenuPanelGui(
        bot_info_dict=bot_info_dict,
        current_bot_hash=current_bot_hash,
        Proc=Proc,
    )
    gui_instance.start()


def handle_menu_event(plugin_event, Proc) -> None:
    try:
        event_name = utils.safe_str(getattr(plugin_event.data, 'event', ''))
        namespace_name = utils.safe_str(getattr(plugin_event.data, 'namespace', ''))
        if namespace_name == config.plugin_name and event_name == config.menu_event_open_config:
            bot_info_dict = getattr(Proc, 'Proc_data', {}).get('bot_info_dict', {})
            open_config_window(
                bot_info_dict=bot_info_dict,
                current_bot_hash=utils.get_raw_bot_hash_from_event(plugin_event),
                Proc=Proc,
            )
    except Exception as exception_object:
        utils.error_log(Proc, f'打开 GUI 失败：{utils.exception_text(exception_object)}')
