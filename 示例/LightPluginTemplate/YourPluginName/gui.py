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
from . import message_custom
from . import utils


dict_color_context = {
    'color_001': '#00A0EA',
    'color_002': '#BBE9FF',
    'color_003': '#40C3FF',
    'color_004': '#FFFFFF',
    'color_005': '#000000',
    'color_006': '#80D7FF',
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
        self.bot_info_var = None
        self.linked_hint_var = None

        self.bot_display_value_list = []
        self.bot_display_to_hash_dict = {}

    def create_root_window(self):
        """创建窗口对象。"""
        if tkinter._default_root is None:
            return tkinter.Tk()
        return tkinter.Toplevel()

    def calculate_window_geometry(self) -> str:
        """统一窗口尺寸。"""
        return '760x460'

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

    def create_native_button(self, parent_widget, text, command, width=12):
        """创建 NativeGUI 风格按钮。"""
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

    def create_page_root(self):
        """创建统一蓝底页面。"""
        frame_widget = tkinter.Frame(self.notebook, bg=dict_color_context['color_001'], borderwidth=0)
        return frame_widget

    def init_string_vars(self) -> None:
        """初始化界面变量。"""
        self.bot_selector_var = tkinter.StringVar(value='')
        self.global_enable_var = tkinter.StringVar(value='True')
        self.global_debug_var = tkinter.StringVar(value='False')
        self.bot_enable_var = tkinter.StringVar(value='True')
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
        return combobox_widget

    def init_frame_global(self) -> None:
        """全局配置页。"""
        self.frame_global = self.create_page_root()
        self.frame_global.grid_columnconfigure(0, weight=1)

        self.create_labeled_combobox(self.frame_global, 0, '全局启用', self.global_enable_var)
        self.create_labeled_combobox(self.frame_global, 2, '全局调试模式', self.global_debug_var)

        button_frame = tkinter.Frame(self.frame_global, bg=dict_color_context['color_001'])
        button_frame.grid(row=4, column=0, sticky='nsew', padx=(20, 20), pady=(40, 0))
        self.create_native_button(button_frame, '保存全局设置', self.save_global_config_from_form, width=16).pack(
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
            text='提示：修改后点击保存按钮生效。',
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 10),
        )
        hint_label.grid(row=5, column=0, sticky='nsew', padx=(20, 20), pady=(18, 0))

    def init_frame_bot(self) -> None:
        """Bot 配置页。"""
        self.frame_bot = self.create_page_root()
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

        title_label = tkinter.Label(
            self.frame_bot,
            textvariable=self.bot_info_var,
            bg=dict_color_context['color_001'],
            fg=dict_color_context['color_004'],
            font=('等线', 12, 'bold'),
            justify='left',
            anchor='w',
            wraplength=700,
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
            wraplength=700,
        )
        hint_label.grid(row=3, column=0, sticky='nsew', padx=(20, 20), pady=(6, 0))

        self.create_labeled_combobox(self.frame_bot, 4, '当前 Bot 启用', self.bot_enable_var)

        button_frame_top = tkinter.Frame(self.frame_bot, bg=dict_color_context['color_001'])
        button_frame_top.grid(row=6, column=0, sticky='nsew', padx=(20, 20), pady=(18, 0))
        self.create_native_button(button_frame_top, '保存 Bot 设置', self.save_bot_config_from_form, width=16).pack(
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

        button_frame_bottom = tkinter.Frame(self.frame_bot, bg=dict_color_context['color_001'])
        button_frame_bottom.grid(row=7, column=0, sticky='nsew', padx=(20, 20), pady=(14, 0))
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

        self.create_native_button(button_frame, '保存', save_action).pack(side=tkinter.RIGHT)
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
            self.linked_hint_var.set('')
            return

        bot_display_text = self.get_bot_display_text(self.current_bot_hash, bot_info=bot_info)
        bot_config = utils.load_bot_config(config_bot_hash)
        self.bot_info_var.set(
            f'当前 Bot：{bot_display_text}'
        )
        self.bot_enable_var.set(str(bool(bot_config.get('bot_enable_switch', True))))

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
        bot_config = utils.load_bot_config(config_bot_hash)
        bot_config['bot_enable_switch'] = self.str_to_bool(self.bot_enable_var.get())
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
        self.root.minsize(720, 430)
        self.root.resizable(width=True, height=True)
        self.root.configure(bg=dict_color_context['color_001'])
        self.init_string_vars()
        self.build_bot_selector_mapping()

        self.init_notebook()

        self.init_frame_global()
        self.init_frame_bot()

        self.notebook.add(self.frame_global, text='全局设置')
        self.notebook.add(self.frame_bot, text='Bot 配置')

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
