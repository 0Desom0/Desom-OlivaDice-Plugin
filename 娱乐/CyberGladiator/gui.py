# -*- encoding: utf-8 -*-
"""
轻量级通用 GUI 模块。

这版 GUI 继续保持双页签结构，但 Bot 配置页会允许切换当前 Bot：
1. 主界面保留“全局设置”和“Bot 配置”两个页签。
2. Bot 配置页内可切换当前 Bot，并根据选择同步刷新按钮行为。
3. 回复词和骰主列表通过子窗口管理，避免主界面过重。

同时继续保持职责边界：
- GUI 只负责展示、编辑与调用 utils.py 的存储接口。
- 不在 GUI 里编排消息解析逻辑。
"""

import os
import tkinter
from tkinter import messagebox
from tkinter import scrolledtext
from tkinter import ttk

from . import config
from . import function
from . import message_custom
from . import utils


dict_color_context = {
    'color_001': '#00A0EA',
    'color_002': '#BBE9FF',
    'color_003': '#40C3FF',
    'color_004': '#FFFFFF',
    'color_005': '#000000',
    'color_006': '#80D7FF',
    'color_007': '#FFD447',
    'color_008': '#FFBF00',
    'color_009': '#114B5F',
}


class TemplatePluginGui(object):
    """模板通用 GUI。"""

    def __init__(self, bot_info_dict=None, current_bot_hash: str = '', Proc=None):
        self.bot_info_dict = bot_info_dict if isinstance(bot_info_dict, dict) else {}
        self.current_bot_hash = utils.safe_str(current_bot_hash)
        self.Proc = Proc
        self.root = None

        self.bot_selector_var = None
        self.global_enable_var = None
        self.global_debug_var = None
        self.bot_enable_var = None
        self.bot_api_url_var = None
        self.bot_api_key_var = None
        self.bot_model_var = None
        self.bot_timeout_var = None
        self.bot_temperature_var = None
        self.bot_delay_min_var = None
        self.bot_delay_max_var = None
        self.bot_forward_switch_var = None
        self.bot_god_war_switch_var = None
        self.system_prompt_summary_var = None
        self.user_prompt_summary_var = None
        self.god_war_system_prompt_summary_var = None
        self.bot_info_var = None
        self.linked_hint_var = None
        self.frame_bot_container = None
        self.bot_scroll_canvas = None
        self.active_scroll_canvas = None

        self.bot_display_value_list = []
        self.bot_display_to_hash_dict = {}

    def create_root_window(self):
        """创建窗口对象。"""
        if tkinter._default_root is None:
            return tkinter.Tk()
        return tkinter.Toplevel()

    def calculate_window_geometry(self) -> str:
        """统一窗口尺寸。"""
        return '780x640'

    def build_bot_selector_mapping(self) -> None:
        """生成 Bot 选择下拉框映射。"""
        self.bot_display_value_list = []
        self.bot_display_to_hash_dict = {}

        for raw_bot_hash, bot_info in self.bot_info_dict.items():
            display_text = self.get_bot_display_text(raw_bot_hash, bot_info=bot_info)
            self.bot_display_value_list.append(display_text)
            self.bot_display_to_hash_dict[display_text] = utils.safe_str(raw_bot_hash)

        self.bot_display_value_list.sort()
        if self.current_bot_hash not in self.bot_info_dict and self.bot_display_value_list:
            self.current_bot_hash = self.bot_display_to_hash_dict[self.bot_display_value_list[0]]

        for display_text, raw_bot_hash in self.bot_display_to_hash_dict.items():
            if raw_bot_hash == self.current_bot_hash:
                self.bot_selector_var.set(display_text)
                break

        if not self.bot_display_value_list:
            self.bot_selector_var.set('当前未检测到 Bot')
            self.current_bot_hash = ''

    def init_notebook(self) -> None:
        """初始化 NativeGUI 风格页签。"""
        style = ttk.Style(self.root)
        try:
            style.element_create('Plain.Notebook.tab', 'from', 'default')
        except Exception:
            pass
        style.layout(
            'TNotebook.Tab',
            [
                (
                    'Plain.Notebook.tab',
                    {
                        'children': [
                            (
                                'Notebook.padding',
                                {
                                    'side': 'top',
                                    'children': [
                                        (
                                            'Notebook.focus',
                                            {
                                                'side': 'top',
                                                'children': [('Notebook.label', {'side': 'top', 'sticky': ''})],
                                                'sticky': 'nswe',
                                            },
                                        )
                                    ],
                                    'sticky': 'nswe',
                                },
                            )
                        ],
                        'sticky': 'nswe',
                    },
                )
            ],
        )
        style.configure(
            'TNotebook',
            background=dict_color_context['color_001'],
            borderwidth=0,
            relief=tkinter.FLAT,
            padding=[-1, 1, -3, -3],
            tabmargins=[5, 5, 0, 0],
        )
        style.configure(
            'TNotebook.Tab',
            background=dict_color_context['color_006'],
            foreground=dict_color_context['color_001'],
            padding=4,
            borderwidth=0,
            font=('等线', 12, 'bold'),
        )
        style.map(
            'TNotebook.Tab',
            background=[('selected', dict_color_context['color_004']), ('!selected', dict_color_context['color_003'])],
            foreground=[('selected', dict_color_context['color_003']), ('!selected', dict_color_context['color_004'])],
        )

        self.notebook = ttk.Notebook(self.root, style='TNotebook')
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.notebook.grid(row=0, column=0, sticky='nsew', padx=(15, 15), pady=(15, 15))

    def create_native_button(
        self,
        parent_widget,
        text,
        command,
        width=12,
        bg_color=None,
        hover_color=None,
        fg_color=None,
        font=None,
    ):
        """创建 NativeGUI 风格按钮。"""
        final_bg_color = bg_color or dict_color_context['color_003']
        final_hover_color = hover_color or dict_color_context['color_006']
        final_fg_color = fg_color or dict_color_context['color_004']
        button_widget = tkinter.Button(
            parent_widget,
            text=text,
            command=command,
            bd=0,
            activebackground=final_hover_color,
            activeforeground=final_fg_color,
            bg=final_bg_color,
            fg=final_fg_color,
            relief='groove',
            height=2,
            width=width,
            font=font or ('等线', 10, 'bold'),
        )
        button_widget.bind('<Enter>', lambda _event: button_widget.configure(bg=final_hover_color))
        button_widget.bind('<Leave>', lambda _event: button_widget.configure(bg=final_bg_color))
        return button_widget

    def create_save_button(self, parent_widget, text, command, width=16):
        """创建更显眼的保存按钮。"""
        return self.create_native_button(
            parent_widget,
            text,
            command,
            width=width,
            bg_color=dict_color_context['color_007'],
            hover_color=dict_color_context['color_008'],
            fg_color=dict_color_context['color_009'],
            font=('等线', 11, 'bold'),
        )

    def create_page_root(self):
        """创建统一蓝底页面。"""
        frame_widget = tkinter.Frame(self.notebook, bg=dict_color_context['color_001'], borderwidth=0)
        return frame_widget

    def create_scrollable_page(self):
        """创建带纵向滚动条的页面。"""
        page_widget = self.create_page_root()
        page_widget.grid_rowconfigure(0, weight=1)
        page_widget.grid_columnconfigure(0, weight=1)

        canvas_widget = tkinter.Canvas(
            page_widget,
            bg=dict_color_context['color_001'],
            highlightthickness=0,
            borderwidth=0,
            yscrollincrement=24,
        )
        scrollbar_widget = ttk.Scrollbar(
            page_widget,
            orient='vertical',
            command=canvas_widget.yview,
        )
        canvas_widget.configure(yscrollcommand=scrollbar_widget.set)

        canvas_widget.grid(row=0, column=0, sticky='nsew')
        scrollbar_widget.grid(row=0, column=1, sticky='ns')

        content_widget = tkinter.Frame(canvas_widget, bg=dict_color_context['color_001'], borderwidth=0)
        content_window_id = canvas_widget.create_window((0, 0), window=content_widget, anchor='nw')

        def sync_scroll_region(_event=None):
            canvas_widget.configure(scrollregion=canvas_widget.bbox('all'))

        def sync_content_width(event):
            canvas_widget.itemconfigure(content_window_id, width=event.width)

        content_widget.bind('<Configure>', sync_scroll_region)
        canvas_widget.bind('<Configure>', sync_content_width)

        return page_widget, content_widget, canvas_widget

    def bind_scroll_canvas_widgets(self, widget, canvas_widget) -> None:
        """为页面中的控件递归绑定鼠标滚轮焦点。"""
        widget.bind(
            '<Enter>',
            lambda _event, target_canvas=canvas_widget: self.set_active_scroll_canvas(target_canvas),
            add='+',
        )
        widget.bind(
            '<Leave>',
            lambda _event, target_canvas=canvas_widget: self.clear_active_scroll_canvas(target_canvas),
            add='+',
        )
        for child_widget in widget.winfo_children():
            self.bind_scroll_canvas_widgets(child_widget, canvas_widget)

    def set_active_scroll_canvas(self, canvas_widget) -> None:
        """记录当前应响应滚轮的滚动页面。"""
        self.active_scroll_canvas = canvas_widget

    def clear_active_scroll_canvas(self, canvas_widget) -> None:
        """离开页面时清理滚轮目标。"""
        if self.active_scroll_canvas == canvas_widget:
            self.active_scroll_canvas = None

    def handle_mousewheel(self, event) -> str | None:
        """把全局滚轮事件转发到当前活动页面。"""
        if self.active_scroll_canvas is None:
            return None

        delta_value = getattr(event, 'delta', 0)
        if delta_value:
            scroll_units = int(-delta_value / 120)
            if scroll_units == 0:
                scroll_units = -1 if delta_value > 0 else 1
        elif getattr(event, 'num', None) == 4:
            scroll_units = -1
        elif getattr(event, 'num', None) == 5:
            scroll_units = 1
        else:
            return None

        self.active_scroll_canvas.yview_scroll(scroll_units, 'units')
        return 'break'

    def handle_combobox_mousewheel(self, event) -> str:
        """禁止下拉框被滚轮改值，同时尽量保留页面滚动。"""
        return self.handle_mousewheel(event) or 'break'

    def init_string_vars(self) -> None:
        """初始化界面变量。"""
        self.bot_selector_var = tkinter.StringVar(value='')
        self.global_enable_var = tkinter.StringVar(value='True')
        self.global_debug_var = tkinter.StringVar(value='False')
        self.bot_enable_var = tkinter.StringVar(value='True')
        self.bot_api_url_var = tkinter.StringVar(value='')
        self.bot_api_key_var = tkinter.StringVar(value='')
        self.bot_model_var = tkinter.StringVar(value='')
        self.bot_timeout_var = tkinter.StringVar(value='180')
        self.bot_temperature_var = tkinter.StringVar(value='0.9')
        self.bot_delay_min_var = tkinter.StringVar(value=str(config.default_segment_delay_min_seconds))
        self.bot_delay_max_var = tkinter.StringVar(value=str(config.default_segment_delay_max_seconds))
        self.bot_forward_switch_var = tkinter.StringVar(value='False')
        self.bot_god_war_switch_var = tkinter.StringVar(value='False')
        self.system_prompt_summary_var = tkinter.StringVar(value='')
        self.user_prompt_summary_var = tkinter.StringVar(value='')
        self.god_war_system_prompt_summary_var = tkinter.StringVar(value='')
        self.bot_info_var = tkinter.StringVar(value='当前未检测到 Bot')
        self.linked_hint_var = tkinter.StringVar(value='')

    def get_current_bot_info(self):
        """获取当前被选中的 bot_info。"""
        return self.bot_info_dict.get(self.current_bot_hash)

    def get_bot_display_text(self, bot_hash: str, bot_info=None) -> str:
        """把 bot 信息格式化成 GUI 下拉框使用的显示文本。"""
        bot_info = bot_info or self.bot_info_dict.get(bot_hash)
        if bot_info is None:
            return utils.safe_str(bot_hash) or '未知 Bot'

        platform_name = utils.safe_str(getattr(bot_info, 'platform', {}).get('platform', 'qq'))
        bot_id = utils.safe_str(getattr(bot_info, 'id', '未知Bot'))
        bot_name = utils.safe_str(getattr(bot_info, 'name', ''))
        if bot_name:
            return f'{platform_name} | {bot_name} | {bot_id}'
        return f'{platform_name} | {bot_id}'

    def get_current_runtime_bot_hash(self) -> str:
        """获取当前 Bot 在 linked 目录侧真正生效的 linked_bot_hash。"""
        if not self.current_bot_hash:
            return ''
        return utils.get_linked_bot_hash(self.current_bot_hash)

    def get_current_config_bot_hash(self) -> str:
        """获取当前 Bot 用于 bot_config 读写的原始 bot hash。"""
        if not self.current_bot_hash:
            return ''
        return utils.get_config_bot_hash(self.current_bot_hash)

    def get_current_bot_data_dir(self) -> str:
        """获取当前 bot_config 所在目录绝对路径。"""
        config_bot_hash = self.get_current_config_bot_hash()
        if not config_bot_hash:
            return os.path.abspath(config.plugin_data_dir)
        return os.path.abspath(utils.get_config_bot_root_dir(config_bot_hash))

    def open_path(self, target_path: str) -> None:
        """打开目录。"""
        try:
            os.startfile(os.path.abspath(target_path))
        except Exception:
            messagebox.showinfo('路径', os.path.abspath(target_path))

    def create_labeled_combobox(self, parent_widget, row_index: int, label_text: str, variable) -> ttk.Combobox:
        """创建一行标签加布尔选择框。"""
        label_widget = tkinter.Label(
            parent_widget,
            text=label_text,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 11, 'bold'),
            anchor='w',
        )
        label_widget.grid(row=row_index, column=0, sticky='nsew', padx=(20, 20), pady=(12, 0))

        combobox_widget = ttk.Combobox(parent_widget, textvariable=variable, state='readonly', values=('True', 'False'))
        combobox_widget.grid(row=row_index + 1, column=0, sticky='nsew', padx=(20, 20), pady=(4, 0))
        combobox_widget.bind('<MouseWheel>', self.handle_combobox_mousewheel, add='+')
        combobox_widget.bind('<Button-4>', self.handle_combobox_mousewheel, add='+')
        combobox_widget.bind('<Button-5>', self.handle_combobox_mousewheel, add='+')
        return combobox_widget

    def create_labeled_entry(
        self,
        parent_widget,
        row_index: int,
        label_text: str,
        variable,
        show: str = '',
    ):
        """创建一行标签加输入框。"""
        label_widget = tkinter.Label(
            parent_widget,
            text=label_text,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 11, 'bold'),
            anchor='w',
        )
        label_widget.grid(row=row_index, column=0, sticky='nsew', padx=(20, 20), pady=(12, 0))

        entry_widget = tkinter.Entry(parent_widget, textvariable=variable, show=show)
        entry_widget.grid(row=row_index + 1, column=0, sticky='nsew', padx=(20, 20), pady=(4, 0))
        return entry_widget

    def summarize_text(self, text_value: str, empty_text: str) -> str:
        """把长文本压成一行摘要，避免主界面过长。"""
        normalized_text = ' '.join(utils.safe_str(text_value).strip().split())
        if not normalized_text:
            return empty_text
        if len(normalized_text) > 80:
            normalized_text = normalized_text[:77] + '...'
        return f'已配置：{normalized_text}'

    def build_current_bot_config_from_form(self) -> dict:
        """从当前界面读取并校验 Bot 配置。"""
        try:
            request_timeout_seconds = int(utils.safe_str(self.bot_timeout_var.get()).strip())
            if request_timeout_seconds <= 0:
                raise ValueError()
        except Exception as err:
            raise ValueError('请求超时必须是大于 0 的整数。') from err

        try:
            temperature = float(utils.safe_str(self.bot_temperature_var.get()).strip())
        except Exception as err:
            raise ValueError('Temperature 必须是数字。') from err

        try:
            delay_min_seconds = int(utils.safe_str(self.bot_delay_min_var.get()).strip())
            delay_max_seconds = int(utils.safe_str(self.bot_delay_max_var.get()).strip())
        except Exception as err:
            raise ValueError('切片等待时间必须填写整数。') from err

        if delay_min_seconds <= 0 or delay_max_seconds <= 0:
            raise ValueError('切片等待时间必须是大于 0 的整数。')
        if delay_max_seconds < delay_min_seconds:
            raise ValueError('切片等待最大值不能小于最小值。')

        return {
            'bot_enable_switch': self.str_to_bool(self.bot_enable_var.get()),
            'api_url': utils.safe_str(self.bot_api_url_var.get()).strip(),
            'api_key': utils.safe_str(self.bot_api_key_var.get()).strip(),
            'model': utils.safe_str(self.bot_model_var.get()).strip(),
            'request_timeout_seconds': request_timeout_seconds,
            'temperature': temperature,
            'segment_delay_min_seconds': delay_min_seconds,
            'segment_delay_max_seconds': delay_max_seconds,
            'qq_forward_message_switch': self.str_to_bool(self.bot_forward_switch_var.get()),
            'god_war_enable_switch': self.str_to_bool(self.bot_god_war_switch_var.get()),
            'system_prompt': self.get_bot_system_prompt_text(),
            'god_war_system_prompt': self.get_bot_god_war_system_prompt_text(),
            'user_prompt_prefix': self.get_bot_user_prompt_prefix_text(),
        }

    def test_bot_api_from_form(self) -> None:
        """使用当前界面里的 Bot 配置进行一次轻量 API 测试。"""
        config_bot_hash = self.get_current_config_bot_hash()
        if not config_bot_hash:
            messagebox.showwarning('提示', '当前没有可操作的 Bot。')
            return

        try:
            current_bot_config = self.build_current_bot_config_from_form()
        except ValueError as err:
            messagebox.showwarning('提示', str(err))
            return

        if not function.api_config_dict_is_ready(current_bot_config):
            messagebox.showwarning('提示', '请先填写完整的 API 地址、API Key 和模型名称。')
            return

        try:
            self.root.config(cursor='watch')
            self.root.update_idletasks()
            result = function.test_chat_api_with_bot_config(current_bot_config)
        except Exception as err:
            messagebox.showerror('提示', f'测试调用发生异常：{err}')
            return
        finally:
            self.root.config(cursor='')
            self.root.update_idletasks()

        response_text = utils.safe_str(result.get('response_text', '')).strip()
        if len(response_text) > 300:
            response_text = response_text[:300] + '...'

        message_text = ''
        if result.get('ok'):
            message_text = 'API 测试成功。'
            if result.get('status_code'):
                message_text += f'\nHTTP 状态：{result.get("status_code")}'
            if response_text:
                message_text += f'\n\n返回内容：\n{response_text}'
            messagebox.showinfo('提示', message_text)
            return

        message_text = 'API 测试失败。'
        if result.get('status_code'):
            message_text += f'\nHTTP 状态：{result.get("status_code")}'
        error_message = utils.safe_str(result.get('error_message', '')).strip()
        if error_message:
            message_text += f'\n错误信息：{error_message}'
        if response_text:
            message_text += f'\n\n返回内容：\n{response_text}'
        messagebox.showerror('提示', message_text)

    def init_frame_global(self) -> None:
        """全局配置页。"""
        self.frame_global = self.create_page_root()
        self.frame_global.grid_columnconfigure(0, weight=1)

        self.create_labeled_combobox(self.frame_global, 0, '全局启用', self.global_enable_var)
        self.create_labeled_combobox(self.frame_global, 2, '全局调试模式', self.global_debug_var)

        button_frame = tkinter.Frame(self.frame_global, bg=dict_color_context['color_001'])
        button_frame.grid(row=4, column=0, sticky='nsew', padx=(20, 20), pady=(40, 0))
        self.create_save_button(button_frame, '保存全局设置', self.save_global_config_from_form, width=16).pack(
            side=tkinter.LEFT, padx=(0, 8)
        )
        self.create_native_button(
            button_frame,
            '打开总目录',
            lambda: self.open_path(config.plugin_data_dir),
            width=14,
        ).pack(side=tkinter.LEFT, padx=(0, 8))
        self.create_native_button(button_frame, '刷新', self.refresh_all_views, width=10).pack(
            side=tkinter.LEFT, padx=(0, 8)
        )
        self.create_native_button(button_frame, '关闭窗口', lambda: self.root.destroy(), width=12).pack(side=tkinter.RIGHT)

        hint_label = tkinter.Label(
            self.frame_global,
            text='提示：修改任何配置后，都需要点击黄色“保存”按钮才会真正生效。',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_007'],
            font=('等线', 10, 'bold'),
        )
        hint_label.grid(row=5, column=0, sticky='nsew', padx=(20, 20), pady=(18, 0))

    def init_frame_bot(self) -> None:
        """Bot 配置页。"""
        self.frame_bot_container, self.frame_bot, self.bot_scroll_canvas = self.create_scrollable_page()
        self.frame_bot.grid_columnconfigure(0, weight=1)

        selector_label = tkinter.Label(
            self.frame_bot,
            text='选择 Bot',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 11, 'bold'),
            anchor='w',
        )
        selector_label.grid(row=0, column=0, sticky='nsew', padx=(20, 20), pady=(14, 0))

        self.bot_selector = ttk.Combobox(self.frame_bot, textvariable=self.bot_selector_var, state='readonly')
        self.bot_selector.grid(row=1, column=0, sticky='nsew', padx=(20, 20), pady=(4, 0))
        self.bot_selector['values'] = tuple(self.bot_display_value_list)
        self.bot_selector.bind('<<ComboboxSelected>>', lambda _event: self.handle_bot_selected())
        self.bot_selector.bind('<MouseWheel>', self.handle_combobox_mousewheel, add='+')
        self.bot_selector.bind('<Button-4>', self.handle_combobox_mousewheel, add='+')
        self.bot_selector.bind('<Button-5>', self.handle_combobox_mousewheel, add='+')

        title_label = tkinter.Label(
            self.frame_bot,
            textvariable=self.bot_info_var,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 12, 'bold'),
            justify='left',
            anchor='w',
            wraplength=620,
        )
        title_label.grid(row=2, column=0, sticky='nsew', padx=(20, 20), pady=(12, 0))

        hint_label = tkinter.Label(
            self.frame_bot,
            textvariable=self.linked_hint_var,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 10),
            justify='left',
            anchor='w',
            wraplength=620,
        )
        hint_label.grid(row=3, column=0, sticky='nsew', padx=(20, 20), pady=(6, 0))

        self.create_labeled_combobox(self.frame_bot, 4, '当前 Bot 启用', self.bot_enable_var)

        self.create_labeled_entry(self.frame_bot, 6, 'API 地址', self.bot_api_url_var)
        self.create_labeled_entry(self.frame_bot, 8, 'API Key', self.bot_api_key_var, show='*')
        self.create_labeled_entry(self.frame_bot, 10, '模型名称', self.bot_model_var)
        self.create_labeled_entry(self.frame_bot, 12, '请求超时（秒）', self.bot_timeout_var)
        self.create_labeled_entry(self.frame_bot, 14, 'Temperature', self.bot_temperature_var)
        self.create_labeled_entry(self.frame_bot, 16, '切片等待最小值（秒）', self.bot_delay_min_var)
        self.create_labeled_entry(self.frame_bot, 18, '切片等待最大值（秒）', self.bot_delay_max_var)
        self.create_labeled_combobox(self.frame_bot, 20, 'QQ 合并转发播报', self.bot_forward_switch_var)
        self.create_labeled_combobox(self.frame_bot, 22, '神战模式开关', self.bot_god_war_switch_var)

        prompt_frame = tkinter.Frame(self.frame_bot, bg=dict_color_context['color_001'])
        prompt_frame.grid(row=24, column=0, sticky='nsew', padx=(20, 20), pady=(18, 0))
        prompt_frame.grid_columnconfigure(0, weight=1)

        tkinter.Label(
            prompt_frame,
            text='系统提示词',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 11, 'bold'),
            anchor='w',
        ).grid(row=0, column=0, sticky='nsew')
        tkinter.Label(
            prompt_frame,
            textvariable=self.system_prompt_summary_var,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 10),
            justify='left',
            anchor='w',
            wraplength=620,
        ).grid(row=1, column=0, sticky='nsew', pady=(4, 0))

        system_prompt_button_frame = tkinter.Frame(prompt_frame, bg=dict_color_context['color_001'])
        system_prompt_button_frame.grid(row=2, column=0, sticky='w', pady=(8, 0))
        self.create_native_button(
            system_prompt_button_frame,
            '编辑系统提示词',
            self.open_system_prompt_editor,
            width=16,
        ).pack(side=tkinter.LEFT, padx=(0, 8))
        self.create_native_button(
            system_prompt_button_frame,
            '恢复默认系统提示词',
            self.reset_system_prompt_to_default,
            width=18,
        ).pack(side=tkinter.LEFT)

        tkinter.Label(
            prompt_frame,
            text='用户前置提示词',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 11, 'bold'),
            anchor='w',
        ).grid(row=3, column=0, sticky='nsew', pady=(16, 0))
        tkinter.Label(
            prompt_frame,
            textvariable=self.user_prompt_summary_var,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 10),
            justify='left',
            anchor='w',
            wraplength=620,
        ).grid(row=4, column=0, sticky='nsew', pady=(4, 0))

        user_prompt_button_frame = tkinter.Frame(prompt_frame, bg=dict_color_context['color_001'])
        user_prompt_button_frame.grid(row=5, column=0, sticky='w', pady=(8, 0))
        self.create_native_button(
            user_prompt_button_frame,
            '编辑用户前置提示词',
            self.open_user_prompt_editor,
            width=18,
        ).pack(side=tkinter.LEFT, padx=(0, 8))
        self.create_native_button(
            user_prompt_button_frame,
            '清空用户前置提示词',
            self.clear_user_prompt_prefix,
            width=18,
        ).pack(side=tkinter.LEFT)

        tkinter.Label(
            prompt_frame,
            text='神战系统提示词',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 11, 'bold'),
            anchor='w',
        ).grid(row=6, column=0, sticky='nsew', pady=(16, 0))
        tkinter.Label(
            prompt_frame,
            textvariable=self.god_war_system_prompt_summary_var,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 10),
            justify='left',
            anchor='w',
            wraplength=620,
        ).grid(row=7, column=0, sticky='nsew', pady=(4, 0))

        god_war_system_prompt_button_frame = tkinter.Frame(prompt_frame, bg=dict_color_context['color_001'])
        god_war_system_prompt_button_frame.grid(row=8, column=0, sticky='w', pady=(8, 0))
        self.create_native_button(
            god_war_system_prompt_button_frame,
            '编辑神战系统提示词',
            self.open_god_war_system_prompt_editor,
            width=18,
        ).pack(side=tkinter.LEFT, padx=(0, 8))
        self.create_native_button(
            god_war_system_prompt_button_frame,
            '恢复默认神战提示词',
            self.reset_god_war_system_prompt_to_default,
            width=18,
        ).pack(side=tkinter.LEFT)

        button_frame_top = tkinter.Frame(self.frame_bot, bg=dict_color_context['color_001'])
        button_frame_top.grid(row=25, column=0, sticky='nsew', padx=(20, 20), pady=(20, 0))
        self.create_save_button(button_frame_top, '保存 Bot 设置', self.save_bot_config_from_form, width=16).pack(
            side=tkinter.LEFT, padx=(0, 8)
        )
        self.create_native_button(button_frame_top, '测试调用 API', self.test_bot_api_from_form, width=14).pack(
            side=tkinter.LEFT, padx=(0, 8)
        )
        self.create_native_button(button_frame_top, '刷新', self.refresh_all_views, width=10).pack(
            side=tkinter.LEFT, padx=(0, 8)
        )
        self.create_native_button(
            button_frame_top,
            '打开配置目录',
            lambda: self.open_path(self.get_current_bot_data_dir()),
            width=14,
        ).pack(side=tkinter.RIGHT)

        bot_save_hint_label = tkinter.Label(
            self.frame_bot,
            text='提示：这里修改的任何 Bot 配置、提示词和开关，都需要点击黄色“保存 Bot 设置”后才生效。',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_007'],
            font=('等线', 10, 'bold'),
            justify='left',
            anchor='w',
            wraplength=620,
        )
        bot_save_hint_label.grid(row=20, column=0, sticky='nsew', padx=(20, 20), pady=(12, 0))
        bot_save_hint_label.grid_configure(row=26)

        button_frame_bottom = tkinter.Frame(self.frame_bot, bg=dict_color_context['color_001'])
        button_frame_bottom.grid(row=27, column=0, sticky='nsew', padx=(20, 20), pady=(14, 20))
        self.create_native_button(button_frame_bottom, '编辑回复词', self.open_reply_manager_dialog, width=12).pack(
            side=tkinter.LEFT, padx=(0, 8)
        )
        self.create_native_button(button_frame_bottom, '恢复默认回复', self.reset_all_reply, width=14).pack(
            side=tkinter.LEFT, padx=(0, 8)
        )
        self.create_native_button(button_frame_bottom, '编辑骰主列表', self.open_master_manager_dialog, width=14).pack(
            side=tkinter.LEFT, padx=(0, 8)
        )
        self.create_native_button(
            button_frame_bottom,
            '打开回复目录',
            lambda: self.open_path(self.get_current_reply_data_dir()),
            width=14,
        ).pack(side=tkinter.RIGHT)

        self.bind_scroll_canvas_widgets(self.frame_bot, self.bot_scroll_canvas)
        self.bind_scroll_canvas_widgets(self.bot_scroll_canvas, self.bot_scroll_canvas)

    def get_selected_tree_value(self, tree_widget, value_index: int = 0) -> str:
        """获取当前树表选中项的某个值。"""
        selection_list = tree_widget.selection()
        if not selection_list:
            return ''
        value_tuple = tree_widget.item(selection_list[0], 'values')
        if len(value_tuple) <= value_index:
            return ''
        return utils.safe_str(value_tuple[value_index])

    def str_to_bool(self, bool_text: str) -> bool:
        """把界面字符串转换为布尔值。"""
        return utils.safe_str(bool_text).strip().lower() in ['1', 'true', 'yes', 'on']

    def get_current_reply_data_dir(self) -> str:
        """获取当前 bot 的 linked 运行期目录绝对路径。"""
        reply_bot_hash = self.get_current_runtime_bot_hash()
        if not reply_bot_hash:
            return os.path.abspath(config.plugin_data_dir)
        return os.path.abspath(utils.get_reply_bot_root_dir(reply_bot_hash))

    def open_text_editor_dialog(self, title_text: str, note_text: str, initial_text: str, save_callback) -> None:
        """打开统一文本编辑弹窗。"""
        dialog_window = tkinter.Toplevel(self.root)
        dialog_window.title(title_text)
        dialog_window.geometry('760x540')
        dialog_window.minsize(680, 480)
        dialog_window.configure(bg=dict_color_context['color_001'])
        dialog_window.grid_rowconfigure(1, weight=1)
        dialog_window.grid_columnconfigure(0, weight=1)

        note_label = tkinter.Label(
            dialog_window,
            text=note_text,
            justify='left',
            anchor='w',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 10),
        )
        note_label.grid(row=0, column=0, sticky='nsew', padx=(15, 15), pady=(15, 8))

        editor_widget = scrolledtext.ScrolledText(dialog_window, wrap='word')
        editor_widget.grid(row=1, column=0, sticky='nsew', padx=(15, 15), pady=(0, 8))
        editor_widget.insert('1.0', initial_text)

        button_frame = tkinter.Frame(dialog_window, bg=dict_color_context['color_001'])
        button_frame.grid(row=2, column=0, sticky='nsew', padx=(15, 15), pady=(0, 15))

        def save_action():
            save_callback(editor_widget.get('1.0', tkinter.END).rstrip('\n'))
            dialog_window.destroy()

        self.create_save_button(button_frame, '保存', save_action, width=12).pack(side=tkinter.RIGHT)
        self.create_native_button(button_frame, '取消', dialog_window.destroy).pack(side=tkinter.RIGHT, padx=(0, 5))

    def open_reply_manager_dialog(self) -> None:
        """打开回复词管理窗口。"""
        runtime_bot_hash = self.get_current_runtime_bot_hash()
        if not runtime_bot_hash:
            messagebox.showwarning('提示', '当前没有可编辑的 Bot。')
            return

        dialog_window = tkinter.Toplevel(self.root)
        dialog_window.title(f'{config.plugin_name} - 回复词管理')
        dialog_window.geometry('920x560')
        dialog_window.minsize(840, 500)
        dialog_window.configure(bg=dict_color_context['color_001'])
        dialog_window.grid_rowconfigure(0, weight=1)
        dialog_window.grid_columnconfigure(0, weight=1)

        reply_tree = ttk.Treeview(dialog_window)
        reply_tree['show'] = 'headings'
        reply_tree['columns'] = ('KEY', 'NOTE', 'DATA')
        reply_tree.column('KEY', width=160)
        reply_tree.column('NOTE', width=280)
        reply_tree.column('DATA', width=420)
        reply_tree.heading('KEY', text='条目')
        reply_tree.heading('NOTE', text='说明')
        reply_tree.heading('DATA', text='内容')
        reply_tree.grid(row=0, column=0, sticky='nsew', padx=(15, 0), pady=(15, 0))

        reply_scrollbar = ttk.Scrollbar(dialog_window, orient='vertical', command=reply_tree.yview)
        reply_tree.configure(yscrollcommand=reply_scrollbar.set)
        reply_scrollbar.grid(row=0, column=1, sticky='nsw', padx=(0, 15), pady=(15, 0))

        def refresh_reply_tree() -> None:
            reply_tree.delete(*reply_tree.get_children())
            custom_message_dict = utils.load_bot_message_custom(runtime_bot_hash)
            for message_key in utils.get_bot_message_key_list(runtime_bot_hash):
                reply_tree.insert(
                    '',
                    tkinter.END,
                    values=(
                        message_key,
                        utils.get_message_note_text(message_key).replace('\n', ' / '),
                        utils.safe_str(custom_message_dict.get(message_key, '')),
                    ),
                )

        def edit_selected_reply() -> None:
            message_key = self.get_selected_tree_value(reply_tree, 0)
            if not message_key:
                messagebox.showwarning('提示', '请先选择一条回复词。')
                return
            custom_message_dict = utils.load_bot_message_custom(runtime_bot_hash)
            self.open_text_editor_dialog(
                title_text=f'编辑回复词 - {message_key}',
                note_text=utils.get_message_note_text(message_key),
                initial_text=custom_message_dict.get(message_key, ''),
                save_callback=lambda new_text: self.save_reply_text(
                    runtime_bot_hash,
                    message_key,
                    new_text,
                    refresh_reply_tree,
                ),
            )

        def reset_or_delete_selected_reply() -> None:
            message_key = self.get_selected_tree_value(reply_tree, 0)
            if not message_key:
                messagebox.showwarning('提示', '请先选择一条回复词。')
                return

            if message_key in message_custom.default_custom_message_dict:
                if not messagebox.askyesno('确认', f'确定要把回复词 {message_key} 恢复为默认值吗？'):
                    return
                utils.reset_bot_message_custom_value(runtime_bot_hash, message_key)
                refresh_reply_tree()
                messagebox.showinfo('提示', f'回复词 {message_key} 已恢复为默认值。')
                return

            if not messagebox.askyesno('确认', f'确定要删除回复词 {message_key} 的自定义内容吗？'):
                return
            custom_message_dict = utils.load_bot_message_custom(runtime_bot_hash)
            custom_message_dict.pop(message_key, None)
            utils.save_bot_message_custom(runtime_bot_hash, custom_message_dict)
            refresh_reply_tree()
            messagebox.showinfo('提示', f'回复词 {message_key} 已删除。')

        def reset_all_reply() -> None:
            self.reset_all_reply_with_callback(refresh_callback=refresh_reply_tree)

        def show_reply_context_menu(event) -> None:
            row_id = reply_tree.identify_row(event.y)
            if not row_id:
                return
            reply_tree.selection_set(row_id)
            reply_tree.focus(row_id)
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()

        context_menu = tkinter.Menu(dialog_window, tearoff=False)
        context_menu.add_command(label='编辑', command=edit_selected_reply)
        context_menu.add_command(label='恢复/删除', command=reset_or_delete_selected_reply)

        button_frame = tkinter.Frame(dialog_window, bg=dict_color_context['color_001'])
        button_frame.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=(15, 15), pady=(10, 15))
        button_frame.grid_columnconfigure(1, weight=1)

        button_left_frame = tkinter.Frame(button_frame, bg=dict_color_context['color_001'])
        button_left_frame.grid(row=0, column=0, sticky='w')
        self.create_native_button(button_left_frame, '恢复默认回复', reset_all_reply, width=14).grid(
            row=0, column=0, padx=(0, 8)
        )
        self.create_native_button(button_left_frame, '刷新', refresh_reply_tree, width=10).grid(row=0, column=1)

        button_right_frame = tkinter.Frame(button_frame, bg=dict_color_context['color_001'])
        button_right_frame.grid(row=0, column=2, sticky='e')
        self.create_native_button(button_right_frame, '恢复/删除', reset_or_delete_selected_reply, width=12).grid(
            row=0, column=0, padx=(0, 10)
        )
        self.create_native_button(button_right_frame, '编辑', edit_selected_reply, width=10).grid(row=0, column=1)

        reply_tree.bind('<Double-1>', lambda _event: edit_selected_reply())
        reply_tree.bind('<Button-3>', show_reply_context_menu)
        refresh_reply_tree()

    def save_reply_text(
        self,
        runtime_bot_hash: str,
        message_key: str,
        message_text: str,
        refresh_callback=None,
    ) -> None:
        """保存回复词文本。"""
        if not runtime_bot_hash:
            return
        utils.set_bot_message_custom_value(runtime_bot_hash, message_key, message_text)
        if callable(refresh_callback):
            refresh_callback()
        messagebox.showinfo('提示', f'回复词 {message_key} 已保存。')

    def reset_all_reply(self) -> None:
        """恢复当前 Bot 的全部默认回复词。"""
        self.reset_all_reply_with_callback(refresh_callback=None)

    def reset_all_reply_with_callback(self, refresh_callback=None) -> None:
        """恢复当前 Bot 的全部默认回复词，并在需要时刷新子窗口。"""
        runtime_bot_hash = self.get_current_runtime_bot_hash()
        if not runtime_bot_hash:
            messagebox.showwarning('提示', '当前没有可操作的 Bot。')
            return
        if not messagebox.askyesno('确认', '确定要把当前 Bot 的全部回复词恢复为默认值吗？'):
            return
        utils.save_bot_message_custom(runtime_bot_hash, message_custom.default_custom_message_dict)
        if callable(refresh_callback):
            refresh_callback()
        messagebox.showinfo('提示', '当前 Bot 的回复词已恢复为模板默认值。')

    def update_prompt_summary_vars(self) -> None:
        """刷新提示词摘要显示。"""
        self.system_prompt_summary_var.set(
            self.summarize_text(self.get_bot_system_prompt_text(), '未配置系统提示词')
        )
        self.user_prompt_summary_var.set(
            self.summarize_text(self.get_bot_user_prompt_prefix_text(), '当前为空，将直接使用参赛名单')
        )
        self.god_war_system_prompt_summary_var.set(
            self.summarize_text(self.get_bot_god_war_system_prompt_text(), '未配置神战系统提示词')
        )

    def get_bot_system_prompt_text(self) -> str:
        """从当前界面状态读取系统提示词。"""
        return utils.safe_str(getattr(self, '_bot_system_prompt_text', config.SYSTEM_PROMPT))

    def set_bot_system_prompt_text(self, text_value: str) -> None:
        """更新当前界面缓存的系统提示词。"""
        self._bot_system_prompt_text = utils.safe_str(text_value)
        self.update_prompt_summary_vars()

    def get_bot_user_prompt_prefix_text(self) -> str:
        """从当前界面状态读取用户前置提示词。"""
        return utils.safe_str(getattr(self, '_bot_user_prompt_prefix_text', ''))

    def set_bot_user_prompt_prefix_text(self, text_value: str) -> None:
        """更新当前界面缓存的用户前置提示词。"""
        self._bot_user_prompt_prefix_text = utils.safe_str(text_value)
        self.update_prompt_summary_vars()

    def get_bot_god_war_system_prompt_text(self) -> str:
        """从当前界面状态读取神战系统提示词。"""
        return utils.safe_str(getattr(self, '_bot_god_war_system_prompt_text', config.GOD_WAR_SYSTEM_PROMPT))

    def set_bot_god_war_system_prompt_text(self, text_value: str) -> None:
        """更新当前界面缓存的神战系统提示词。"""
        self._bot_god_war_system_prompt_text = utils.safe_str(text_value)
        self.update_prompt_summary_vars()

    def open_system_prompt_editor(self) -> None:
        """编辑当前 Bot 的系统提示词。"""
        self.open_text_editor_dialog(
            title_text='编辑系统提示词',
            note_text='这里编辑当前 Bot 的 system_prompt，将写回 bot_config.json。',
            initial_text=self.get_bot_system_prompt_text(),
            save_callback=self.set_bot_system_prompt_text,
        )

    def reset_system_prompt_to_default(self) -> None:
        """恢复默认系统提示词。"""
        if not messagebox.askyesno('确认', '确定要恢复为默认系统提示词吗？'):
            return
        self.set_bot_system_prompt_text(config.SYSTEM_PROMPT)

    def open_user_prompt_editor(self) -> None:
        """编辑当前 Bot 的用户前置提示词。"""
        self.open_text_editor_dialog(
            title_text='编辑用户前置提示词',
            note_text='这里的文本会插入到参赛名单之前，适合补充自定义裁判风格或规则。',
            initial_text=self.get_bot_user_prompt_prefix_text(),
            save_callback=self.set_bot_user_prompt_prefix_text,
        )

    def clear_user_prompt_prefix(self) -> None:
        """清空用户前置提示词。"""
        if not messagebox.askyesno('确认', '确定要清空当前 Bot 的用户前置提示词吗？'):
            return
        self.set_bot_user_prompt_prefix_text('')

    def open_god_war_system_prompt_editor(self) -> None:
        """编辑当前 Bot 的神战系统提示词。"""
        self.open_text_editor_dialog(
            title_text='编辑神战系统提示词',
            note_text='这里编辑当前 Bot 的 god_war_system_prompt，神战模式开启后会优先使用它。',
            initial_text=self.get_bot_god_war_system_prompt_text(),
            save_callback=self.set_bot_god_war_system_prompt_text,
        )

    def reset_god_war_system_prompt_to_default(self) -> None:
        """恢复默认神战系统提示词。"""
        if not messagebox.askyesno('确认', '确定要恢复为默认神战系统提示词吗？'):
            return
        self.set_bot_god_war_system_prompt_text(config.GOD_WAR_SYSTEM_PROMPT)

    def open_master_manager_dialog(self) -> None:
        """打开骰主列表管理窗口。"""
        config_bot_hash = self.get_current_config_bot_hash()
        if not config_bot_hash:
            messagebox.showwarning('提示', '当前没有可操作的 Bot。')
            return

        dialog_window = tkinter.Toplevel(self.root)
        dialog_window.title(f'{config.plugin_name} - 骰主列表')
        dialog_window.geometry('520x460')
        dialog_window.minsize(460, 400)
        dialog_window.configure(bg=dict_color_context['color_001'])
        dialog_window.grid_rowconfigure(1, weight=1)
        dialog_window.grid_columnconfigure(0, weight=1)

        entry_var = tkinter.StringVar()
        top_frame = tkinter.Frame(dialog_window, bg=dict_color_context['color_001'])
        top_frame.grid(row=0, column=0, sticky='nsew', padx=(15, 15), pady=(15, 10))

        tkinter.Label(
            top_frame,
            text='输入用户 ID 后点击添加：',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 10),
        ).pack(side=tkinter.LEFT, padx=(0, 8))
        tkinter.Entry(top_frame, textvariable=entry_var, width=22).pack(side=tkinter.LEFT, padx=(0, 8))

        master_tree = ttk.Treeview(dialog_window, selectmode='extended')
        master_tree['show'] = 'headings'
        master_tree['columns'] = ('MASTER_ID',)
        master_tree.column('MASTER_ID', width=240)
        master_tree.heading('MASTER_ID', text='骰主ID')
        master_tree.grid(row=1, column=0, sticky='nsew', padx=(15, 0), pady=(0, 0))

        master_scrollbar = ttk.Scrollbar(dialog_window, orient='vertical', command=master_tree.yview)
        master_tree.configure(yscrollcommand=master_scrollbar.set)
        master_scrollbar.grid(row=1, column=1, sticky='nsw', padx=(0, 15))

        def refresh_master_tree() -> None:
            master_tree.delete(*master_tree.get_children())
            for master_id in utils.get_configured_master_list(config_bot_hash):
                master_tree.insert('', tkinter.END, values=(master_id,))

        def add_master() -> None:
            new_master_list = utils.normalize_id_list(entry_var.get())
            if not new_master_list:
                messagebox.showwarning('提示', '请输入有效的数字 ID。')
                return
            configured_master_list = utils.get_configured_master_list(config_bot_hash)
            for master_id in new_master_list:
                if master_id not in configured_master_list:
                    configured_master_list.append(master_id)
            utils.set_configured_master_list(config_bot_hash, configured_master_list)
            entry_var.set('')
            refresh_master_tree()

        def delete_selected_master() -> None:
            selected_id_set = set()
            for selection_item in master_tree.selection():
                value_tuple = master_tree.item(selection_item, 'values')
                if value_tuple:
                    selected_id_set.add(utils.safe_str(value_tuple[0]))
            if not selected_id_set:
                messagebox.showwarning('提示', '请先选择要删除的骰主。')
                return
            configured_master_list = [
                master_id
                for master_id in utils.get_configured_master_list(config_bot_hash)
                if master_id not in selected_id_set
            ]
            utils.set_configured_master_list(config_bot_hash, configured_master_list)
            refresh_master_tree()

        button_frame = tkinter.Frame(dialog_window, bg=dict_color_context['color_001'])
        button_frame.grid(row=2, column=0, columnspan=2, sticky='nsew', padx=(15, 15), pady=(10, 15))
        self.create_native_button(button_frame, '添加', add_master).pack(side=tkinter.LEFT, padx=(0, 6))
        self.create_native_button(button_frame, '删除', delete_selected_master).pack(side=tkinter.LEFT, padx=(0, 6))
        self.create_native_button(button_frame, '刷新', refresh_master_tree).pack(side=tkinter.RIGHT, padx=(0, 6))
        self.create_native_button(button_frame, '关闭', dialog_window.destroy).pack(side=tkinter.RIGHT)

        refresh_master_tree()

    def refresh_global_view(self) -> None:
        """刷新全局配置页。"""
        global_config = utils.load_global_config()
        self.global_enable_var.set(str(bool(global_config.get('global_enable_switch', True))))
        self.global_debug_var.set(str(bool(global_config.get('global_debug_mode_switch', False))))

    def refresh_bot_view(self) -> None:
        """刷新 Bot 配置页。"""
        bot_info = self.get_current_bot_info()
        config_bot_hash = self.get_current_config_bot_hash()
        reply_bot_hash = self.get_current_runtime_bot_hash()
        if bot_info is None or not config_bot_hash:
            self.bot_info_var.set('当前未检测到 Bot')
            self.bot_enable_var.set(str(bool(config.default_bot_config.get('bot_enable_switch', True))))
            self.bot_api_url_var.set(utils.safe_str(config.default_bot_config.get('api_url', '')))
            self.bot_api_key_var.set(utils.safe_str(config.default_bot_config.get('api_key', '')))
            self.bot_model_var.set(utils.safe_str(config.default_bot_config.get('model', '')))
            self.bot_timeout_var.set(str(config.default_bot_config.get('request_timeout_seconds', 180)))
            self.bot_temperature_var.set(str(config.default_bot_config.get('temperature', 0.9)))
            self.bot_delay_min_var.set(str(config.default_bot_config.get('segment_delay_min_seconds', 10)))
            self.bot_delay_max_var.set(str(config.default_bot_config.get('segment_delay_max_seconds', 20)))
            self.bot_forward_switch_var.set(
                str(bool(config.default_bot_config.get('qq_forward_message_switch', False)))
            )
            self.bot_god_war_switch_var.set(
                str(bool(config.default_bot_config.get('god_war_enable_switch', False)))
            )
            self.set_bot_system_prompt_text(config.default_bot_config.get('system_prompt', config.SYSTEM_PROMPT))
            self.set_bot_god_war_system_prompt_text(
                config.default_bot_config.get('god_war_system_prompt', config.GOD_WAR_SYSTEM_PROMPT)
            )
            self.set_bot_user_prompt_prefix_text(config.default_bot_config.get('user_prompt_prefix', ''))
            self.linked_hint_var.set('')
            return

        bot_display_text = self.get_bot_display_text(self.current_bot_hash, bot_info=bot_info)
        bot_config = utils.load_bot_config(config_bot_hash)
        delay_min_seconds, delay_max_seconds = function.get_segment_delay_range_from_bot_config(bot_config)
        self.bot_info_var.set(
            f'当前 Bot：{bot_display_text}'
        )
        self.bot_enable_var.set(str(bool(bot_config.get('bot_enable_switch', True))))
        self.bot_api_url_var.set(utils.safe_str(bot_config.get('api_url', '')))
        self.bot_api_key_var.set(utils.safe_str(bot_config.get('api_key', '')))
        self.bot_model_var.set(utils.safe_str(bot_config.get('model', '')))
        self.bot_timeout_var.set(str(bot_config.get('request_timeout_seconds', 180)))
        self.bot_temperature_var.set(str(bot_config.get('temperature', 0.9)))
        self.bot_delay_min_var.set(str(delay_min_seconds))
        self.bot_delay_max_var.set(str(delay_max_seconds))
        self.bot_forward_switch_var.set(str(bool(bot_config.get('qq_forward_message_switch', False))))
        self.bot_god_war_switch_var.set(str(bool(bot_config.get('god_war_enable_switch', False))))
        self.set_bot_system_prompt_text(bot_config.get('system_prompt', config.SYSTEM_PROMPT))
        self.set_bot_god_war_system_prompt_text(
            bot_config.get('god_war_system_prompt', config.GOD_WAR_SYSTEM_PROMPT)
        )
        self.set_bot_user_prompt_prefix_text(bot_config.get('user_prompt_prefix', ''))

        if reply_bot_hash and reply_bot_hash != config_bot_hash:
            linked_bot_info = self.bot_info_dict.get(reply_bot_hash)
            if linked_bot_info is not None:
                linked_bot_text = self.get_bot_display_text(reply_bot_hash, bot_info=linked_bot_info)
                self.linked_hint_var.set(
                    f'当前账号为从账号，主账号为：{linked_bot_text}'
                )
            else:
                self.linked_hint_var.set(
                    f'当前账号为从账号，主账号 hash 为：{reply_bot_hash}'
                )
        else:
            self.linked_hint_var.set('')

    def save_global_config_from_form(self) -> None:
        """保存全局配置。"""
        global_config = utils.load_global_config()
        global_config['global_enable_switch'] = self.str_to_bool(self.global_enable_var.get())
        global_config['global_debug_mode_switch'] = self.str_to_bool(self.global_debug_var.get())
        utils.save_global_config(global_config)
        messagebox.showinfo('提示', '全局设置已保存。')
        self.refresh_global_view()

    def save_bot_config_from_form(self) -> None:
        """保存当前 Bot 配置。"""
        config_bot_hash = self.get_current_config_bot_hash()
        if not config_bot_hash:
            messagebox.showwarning('提示', '当前没有可操作的 Bot。')
            return

        try:
            current_bot_config = self.build_current_bot_config_from_form()
        except ValueError as err:
            messagebox.showwarning('提示', str(err))
            return

        bot_config = utils.load_bot_config(config_bot_hash)
        bot_config.update(current_bot_config)
        utils.save_bot_config(config_bot_hash, bot_config)
        messagebox.showinfo('提示', 'Bot 设置已保存。')
        self.refresh_bot_view()

    def refresh_all_views(self) -> None:
        """刷新全部页面。"""
        self.refresh_global_view()
        self.refresh_bot_view()

    def handle_bot_selected(self) -> None:
        """切换 Bot 配置页中的当前 Bot。"""
        selected_display_text = self.bot_selector_var.get()
        self.current_bot_hash = self.bot_display_to_hash_dict.get(selected_display_text, '')
        self.refresh_bot_view()

    def start(self) -> None:
        """启动 GUI。"""
        self.root = self.create_root_window()
        self.root.title(config.gui_window_title)
        self.root.geometry(self.calculate_window_geometry())
        self.root.minsize(720, 560)
        self.root.resizable(width=True, height=True)
        self.root.configure(bg=dict_color_context['color_001'])
        self.init_string_vars()
        self.build_bot_selector_mapping()
        self.root.bind_all('<MouseWheel>', self.handle_mousewheel, add='+')
        self.root.bind_all('<Button-4>', self.handle_mousewheel, add='+')
        self.root.bind_all('<Button-5>', self.handle_mousewheel, add='+')

        self.init_notebook()

        self.init_frame_global()
        self.init_frame_bot()

        self.notebook.add(self.frame_global, text='全局设置')
        self.notebook.add(self.frame_bot_container, text='Bot 配置')

        self.refresh_all_views()
        self.root.mainloop()


def open_config_window(bot_info_dict=None, current_bot_hash: str = '', Proc=None) -> None:
    """对外暴露一个简单函数，方便外部事件入口直接调用。"""
    gui_instance = TemplatePluginGui(bot_info_dict=bot_info_dict, current_bot_hash=current_bot_hash, Proc=Proc)
    gui_instance.start()


def handle_menu_event(plugin_event, Proc) -> None:
    """菜单事件入口。"""
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
        utils.error_log(Proc, f'打开 GUI 失败：{type(exception_object).__name__}: {exception_object}')
