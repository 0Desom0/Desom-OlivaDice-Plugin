"""独立 Tk 管理面板；全部业务与 WebUI 共用接口。"""

import json
import queue
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
except ImportError:
    tk = None

from . import api, files, resources, runtime

_WINDOW = None


class Manager:
    def __init__(self):
        self.root = tk.Toplevel() if tk._default_root is not None else tk.Tk()
        self.root.title(f'多自定义回复切换 {resources.VERSION}')
        self.root.geometry('1120x780')
        self.root.minsize(850, 600)
        self.scope = 'unity'
        self.selection = None
        self.snapshot = None
        self.entry = None
        self.queue = queue.Queue()
        self.accounts = api.dispatch({'op': 'accounts'})['accounts']
        self.labels = {item['label']: item['hash'] for item in self.accounts}
        self.scope_var = tk.StringVar(value=self.accounts[0]['label'])
        self.baseline_var = tk.StringVar(value='全部默认模块')
        self.pack_var = tk.StringVar()
        self.query = tk.StringVar()
        self.filter = tk.StringVar(value='全部')
        self.status = tk.StringVar()
        self._build()
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        self.poll_id = self.root.after(150, self.poll)

    def request(self, op, **data):
        return api.dispatch({'op': op, 'scope': self.scope, **data})

    def run(self, action):
        try:
            return action()
        except Exception as exc:
            messagebox.showerror('操作失败', str(exc), parent=self.root)
            return None

    def _build(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='回复库').pack(side='left')
        scopes = ttk.Combobox(top, textvariable=self.scope_var, values=list(self.labels), state='readonly', width=24)
        scopes.pack(side='left', padx=8)
        scopes.bind('<<ComboboxSelected>>', lambda event: self.run(self.change_scope))
        ttk.Label(top, text='unity 比较基线').pack(side='left')
        baseline = ttk.Combobox(
            top,
            textvariable=self.baseline_var,
            values=['全部默认模块', *list(self.labels)[1:]],
            state='readonly',
            width=24,
        )
        baseline.pack(side='left', padx=8)
        baseline.bind('<<ComboboxSelected>>', lambda event: self.run(self.load_pack))
        ttk.Button(top, text='编写帮助', command=self.help).pack(side='right')
        bar = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bar.pack(fill='x')
        packs = ttk.Combobox(bar, textvariable=self.pack_var, state='readonly', width=30)
        packs.pack(side='left', padx=(0, 8))
        packs.bind('<<ComboboxSelected>>', lambda event: self.run(self.change_pack))
        self.pack_combo = packs
        for title, method in [
            ('新建复制', lambda: self.copy_dialog(False)),
            ('从其他库导入', lambda: self.copy_dialog(True)),
            ('改名', self.rename),
            ('改序号', self.reindex),
            ('Bot/群设置', self.settings),
            ('恢复模块', self.modules),
        ]:
            ttk.Button(bar, text=title, command=lambda fn=method: self.run(fn)).pack(side='left', padx=2)
        imports = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        imports.pack(fill='x')
        for title, method in [
            ('导入 JSON', self.import_file),
            ('下载 JSON', self.download),
            ('导出 JSON', self.export_file),
            ('刷新文件', self.refresh),
        ]:
            ttk.Button(imports, text=title, command=lambda fn=method: self.run(fn)).pack(side='left', padx=2)
        ttk.Label(imports, textvariable=self.status).pack(side='left', padx=12)
        pane = ttk.Panedwindow(self.root, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left, weight=2)
        pane.add(right, weight=3)
        search = ttk.Frame(left)
        search.pack(fill='x', pady=(0, 6))
        ttk.Entry(search, textvariable=self.query).pack(side='left', fill='x', expand=True)
        ttk.Combobox(
            search, textvariable=self.filter, values=['全部', '已修改', '未修改'], state='readonly', width=10
        ).pack(side='left', padx=4)
        self.query.trace_add('write', lambda *args: self.render_entries())
        self.filter.trace_add('write', lambda *args: self.render_entries())
        self.tree = ttk.Treeview(left, columns=('state',), selectmode='browse')
        self.tree.heading('#0', text='回复键')
        self.tree.heading('state', text='状态')
        self.tree.column('#0', width=230)
        self.tree.column('state', width=75, stretch=False)
        scroll = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda event: self.choose_entry())
        self.key_var = tk.StringVar()
        self.note_var = tk.StringVar()
        ttk.Label(right, textvariable=self.key_var, font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w', padx=8)
        ttk.Label(right, textvariable=self.note_var, wraplength=520).pack(anchor='w', padx=8, pady=8)
        self.editor = scrolledtext.ScrolledText(right, wrap='word', undo=True, font=('Consolas', 11))
        self.editor.pack(fill='both', expand=True, padx=8)
        self.editor.bind('<<Modified>>', self.modified)
        buttons = ttk.Frame(right, padding=8)
        buttons.pack(fill='x')
        for title, method in [
            ('保存回复', self.save),
            ('恢复默认', self.reset),
            ('新增回复键', self.add_key),
            ('删除自定义键', self.delete),
        ]:
            ttk.Button(buttons, text=title, command=lambda fn=method: self.run(fn)).pack(side='left', padx=3)

    def baseline(self):
        return self.labels.get(self.baseline_var.get()) if self.scope == 'unity' else None

    def dirty(self):
        return self.entry is not None and (
            self.entry.get('new', False) or self.editor.get('1.0', 'end-1c') != self.entry['value']
        )

    def discard(self):
        return not self.dirty() or messagebox.askyesno('未保存', '放弃当前编辑框中未保存的改动？', parent=self.root)

    def modified(self, event=None):
        if self.editor.edit_modified():
            self.editor.edit_modified(False)
            self.status.set('未保存' if self.dirty() else '已保存')

    def change_scope(self):
        if not self.discard():
            self.scope_var.set(next(label for label, value in self.labels.items() if value == self.scope))
            return
        self.scope = self.labels[self.scope_var.get()]
        self.selection = None
        self.entry = None
        self.refresh()

    def refresh(self):
        if not self.discard():
            return
        state = self.request('reload')
        self.pack_map = {
            f'{item["selection"]}. {item["name"]}' if self.scope != 'unity' else item['name']: item['selection']
            for item in state['replies']
            if item['available']
        }
        self.pack_combo['values'] = list(self.pack_map)
        label = next(
            (key for key, value in self.pack_map.items() if value == self.selection), next(iter(self.pack_map), '')
        )
        self.pack_var.set(label)
        self.selection = self.pack_map.get(label)
        self.entry = None
        self.load_pack()

    def change_pack(self):
        if not self.discard():
            self.pack_var.set(next((key for key, value in self.pack_map.items() if value == self.selection), ''))
            return
        self.selection = self.pack_map.get(self.pack_var.get())
        self.entry = None
        self.load_pack()

    def load_pack(self):
        if not self.discard():
            return
        self.snapshot = (
            self.request('snapshot', selection=self.selection, baseline=self.baseline()) if self.selection else None
        )
        self.entry = None
        self.set_editor(None)
        self.render_entries()
        self.status.set('smp 只读' if self.snapshot and self.snapshot['readonly'] else '选择回复键进行编辑')

    def render_entries(self):
        if not hasattr(self, 'tree'):
            return
        self.tree.delete(*self.tree.get_children())
        if not self.snapshot:
            return
        for item in self.snapshot['entries']:
            query = self.query.get().casefold()
            if query not in f'{item["key"]} {item["value"]} {item["note"]}'.casefold():
                continue
            if self.filter.get() != '全部' and item['modified'] != (self.filter.get() == '已修改'):
                continue
            self.tree.insert(
                '', 'end', iid=item['key'], text=item['key'], values=('已修改' if item['modified'] else '未修改',)
            )

    def choose_entry(self):
        selected = self.tree.selection()
        if not selected or not self.snapshot or (self.entry and self.entry['key'] == selected[0]):
            return
        if not self.discard():
            if self.entry and self.tree.exists(self.entry['key']):
                self.tree.selection_set(self.entry['key'])
            return
        item = next(item for item in self.snapshot['entries'] if item['key'] == selected[0])
        self.set_editor(item)

    def set_editor(self, item):
        self.entry = item
        self.key_var.set(item['key'] if item else '未选择回复键')
        self.note_var.set(item['note'] if item else '')
        self.editor.configure(state='normal')
        self.editor.delete('1.0', 'end')
        if item:
            self.editor.insert('1.0', item['value'])
        self.editor.edit_modified(False)
        if not item or self.snapshot['readonly']:
            self.editor.configure(state='disabled')

    def edit(self, **options):
        if not self.entry or not self.snapshot:
            return
        key = self.entry['key']
        self.snapshot = self.request(
            'edit',
            selection=self.selection,
            key=key,
            value=self.editor.get('1.0', 'end-1c'),
            revision=self.snapshot['revision'],
            baseline=self.baseline(),
            **options,
        )
        item = next((item for item in self.snapshot['entries'] if item['key'] == key), None)
        self.set_editor(item)
        self.render_entries()
        self.status.set('已保存')

    def save(self):
        self.edit()

    def reset(self):
        if self.entry and messagebox.askyesno('恢复默认', '将当前回复恢复为所选模块的默认文本？', parent=self.root):
            self.edit(reset=True)

    def delete(self):
        if self.entry and messagebox.askyesno('删除键', '删除当前自定义回复键？内置键无法删除。', parent=self.root):
            self.edit(delete=True)

    def add_key(self):
        if not self.snapshot or self.snapshot['readonly'] or not self.discard():
            return
        key = simpledialog.askstring('新增回复键', '回复键名称', parent=self.root)
        if key:
            if any(item['key'] == key for item in self.snapshot['entries']):
                raise ValueError('回复键已存在。')
            self.set_editor({'key': key, 'value': '', 'note': '输入文本后保存新增回复键。', 'new': True})

    def collision(self, name):
        window = tk.Toplevel(self.root)
        window.title('同名回复')
        result = ['cancel']
        ttk.Label(window, text=f'已存在「{name}」，请选择导入方式。', padding=15).pack()
        buttons = ttk.Frame(window, padding=10)
        buttons.pack()
        for label, value in [('覆盖', 'overwrite'), ('创建为副本', 'copy'), ('取消导入', 'cancel')]:

            def choose(choice=value):
                result[0] = choice
                window.destroy()

            ttk.Button(buttons, text=label, command=choose).pack(side='left', padx=5)
        window.transient(self.root)
        window.grab_set()
        self.root.wait_window(window)
        return result[0]

    def import_data(self, name, data):
        if not self.discard():
            return
        result = self.request('import', name=name, data=data)
        if result.get('conflict'):
            result = self.request('import', name=name, data=data, conflict=self.collision(result['name']))
        if not result.get('cancelled'):
            self.selection = result['selection']
            self.entry = None
            self.refresh()

    def import_file(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('JSON 回复', '*.json')])
        if path:
            raw = files.read_bytes(path)
            if len(raw) > api.MAX_BYTES:
                raise ValueError('文件超过 8 MiB。')
            name = simpledialog.askstring('导入回复', '回复名称', initialvalue=Path(path).stem, parent=self.root)
            if name:
                self.import_data(name, json.loads(raw.decode('utf-8-sig')))

    def download(self):
        url = simpledialog.askstring('下载 JSON', 'HTTP/HTTPS JSON 下载链接', parent=self.root)
        if not url:
            return
        name = simpledialog.askstring('导入回复', '下载后使用的回复名称', parent=self.root)
        if not name:
            return
        target_scope = self.scope
        self.status.set('正在下载…')

        def work():
            try:
                self.queue.put((target_scope, name, api.download(url), None))
            except Exception as exc:
                self.queue.put((target_scope, name, None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                scope, name, data, error = self.queue.get_nowait()
                if error:
                    messagebox.showerror('下载失败', error, parent=self.root)
                elif scope != self.scope:
                    messagebox.showinfo('下载完成', '回复库已切换，请重新下载到所需库。', parent=self.root)
                else:
                    self.run(lambda name=name, data=data: self.import_data(name, data))
        except queue.Empty:
            pass
        self.poll_id = self.root.after(150, self.poll)

    def export_file(self):
        if self.selection is None or not self.discard():
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension='.json',
            initialfile=f'{self.pack_var.get()}.json',
            filetypes=[('JSON 回复', '*.json')],
        )
        if path:
            files.write_json(path, self.request('export', selection=self.selection)['data'])

    def copy_dialog(self, importing):
        if not self.discard():
            return
        window = tk.Toplevel(self.root)
        window.transient(self.root)
        window.grab_set()
        window.title('从其他库导入' if importing else '从已有回复新建')
        source = tk.StringVar(value=self.scope_var.get())
        selection = tk.StringVar()
        name = tk.StringVar()
        combo = ttk.Combobox(window, textvariable=source, values=list(self.labels), state='readonly', width=38)
        combo.pack(padx=16, pady=8)
        packs = ttk.Combobox(window, textvariable=selection, state='readonly', width=38)
        packs.pack(padx=16, pady=8)
        ttk.Label(window, text='目标回复名称').pack()
        ttk.Entry(window, textvariable=name, width=38).pack(padx=16, pady=8)
        choices = {}

        def load(event=None):
            choices.clear()
            items = api.dispatch({'op': 'state', 'scope': self.labels[source.get()]})['replies']
            choices.update(
                {f'{item["selection"]}. {item["name"]}': item['selection'] for item in items if item['available']}
            )
            packs['values'] = list(choices)
            selection.set(next(iter(choices), ''))

        def apply():
            if selection.get() not in choices:
                raise ValueError('请选择来源回复。')
            source_scope = self.labels[source.get()]
            source_selection = choices[selection.get()]
            if importing:
                values = api.dispatch({'op': 'export', 'scope': source_scope, 'selection': source_selection})['data']
                self.import_data(name.get(), values)
            else:
                result = self.request(
                    'create', name=name.get(), source_scope=source_scope, source_selection=source_selection
                )
                self.selection = result['selection']
                self.entry = None
                self.refresh()
            window.destroy()

        combo.bind('<<ComboboxSelected>>', lambda event: self.run(load))
        ttk.Button(window, text='导入' if importing else '创建', command=lambda: self.run(apply)).pack(pady=12)
        load()

    def rename(self):
        if self.selection is None or not self.discard():
            return
        name = simpledialog.askstring('改名', '新回复名称（同步重命名文件，保持序号）', parent=self.root)
        if name:
            result = self.request('rename', selection=self.selection, name=name)
            self.selection = result['selection']
            self.entry = None
            self.refresh()

    def reindex(self):
        if self.scope == 'unity':
            raise ValueError('unity 模板没有回复序号。')
        window = tk.Toplevel(self.root)
        window.transient(self.root)
        window.grab_set()
        window.title('更改序号（同步所有群引用）')
        variables = {}
        state = self.request('state')
        for row, item in enumerate(state['replies']):
            if item['selection'] < 3:
                continue
            ttk.Label(window, text=f'{item["selection"]}. {item["name"]}').grid(row=row, column=0, padx=12, pady=4)
            value = tk.StringVar(value=str(item['selection']))
            variables[str(item['selection'])] = value
            ttk.Entry(window, textvariable=value, width=10).grid(row=row, column=1, padx=12, pady=4)

        def apply():
            self.request(
                'reindex',
                mapping={old: value.get() for old, value in variables.items()},
                index_revision=state['index_revision'],
            )
            self.selection = None
            self.entry = None
            self.refresh()
            window.destroy()

        ttk.Button(window, text='保存并修正所有引用', command=lambda: self.run(apply)).grid(
            row=len(variables) + 3,
            column=0,
            columnspan=2,
            pady=12,
        )

    def settings(self):
        if self.scope == 'unity':
            raise ValueError('请先选择一个 bot。')
        state = self.request('state')
        window = tk.Toplevel(self.root)
        window.transient(self.root)
        window.grab_set()
        window.title('当前 Bot / 群设置')
        target = tk.StringVar(value='全局')
        enabled = tk.BooleanVar(value=state['config']['enabled'])
        model = tk.StringVar(value=str(state['config']['reply_model']))
        combo = ttk.Combobox(window, textvariable=target, values=['全局', *state['groups']], width=42, state='readonly')
        combo.pack(padx=16, pady=10)
        ttk.Checkbutton(window, text='开启插件（全局关闭时所有群均恢复 Core 回复）', variable=enabled).pack(padx=16)
        ttk.Label(window, text='回复序号').pack(pady=6)
        ttk.Combobox(
            window,
            textvariable=model,
            values=[str(item['selection']) for item in state['replies'] if item['available']],
            state='readonly',
        ).pack(padx=16)

        def change(event=None):
            config = state['config'] if target.get() == '全局' else state['groups'][target.get()]
            enabled.set(config['enabled'])
            model.set(str(config['reply_model']))

        def apply():
            self.request(
                'settings',
                model=model.get(),
                enabled=enabled.get(),
                group_hash=None if target.get() == '全局' else target.get(),
            )
            window.destroy()

        combo.bind('<<ComboboxSelected>>', change)
        ttk.Button(window, text='保存', command=lambda: self.run(apply)).pack(pady=12)

    def modules(self):
        if self.scope == 'unity':
            raise ValueError('请先选择要修改恢复模块的 bot；unity 只选择比较基线。')
        window = tk.Toplevel(self.root)
        window.transient(self.root)
        window.grab_set()
        window.title('Core 共用恢复模块')
        ttk.Label(window, text='每行一个模块名，按顺序覆盖同名键。保存到 Core 的原文件。', padding=12).pack()
        text = scrolledtext.ScrolledText(window, width=50, height=12)
        text.pack(padx=12)
        text.insert('1.0', '\n'.join(self.request('state')['modules']))

        def apply():
            self.request(
                'recover', modules=[line.strip() for line in text.get('1.0', 'end').splitlines() if line.strip()]
            )
            self.load_pack()
            window.destroy()

        ttk.Button(window, text='保存共用配置', command=lambda: self.run(apply)).pack(pady=12)

    def help(self):
        window = tk.Toplevel(self.root)
        window.title('自定义回复编写帮助')
        text = scrolledtext.ScrolledText(window, width=100, height=36, wrap='word')
        text.pack(fill='both', expand=True)
        text.insert('1.0', resources.WRITER_HELP)
        text.configure(state='disabled')

    def close(self):
        global _WINDOW
        if self.discard():
            self.root.after_cancel(self.poll_id)
            self.root.destroy()
            if _WINDOW is self:
                _WINDOW = None


def open_window():
    if runtime.STORE is None:
        raise ValueError(runtime.INIT_ERROR or '插件尚未初始化。')
    if tk is None:
        raise ValueError('当前 Python 没有 Tk 支持，请使用 WebUI 管理。')

    def show():
        global _WINDOW
        if _WINDOW is not None and _WINDOW.root.winfo_exists():
            _WINDOW.root.deiconify()
            _WINDOW.root.lift()
            return
        has_root = tk._default_root is not None
        _WINDOW = Manager()
        if not has_root:
            _WINDOW.root.mainloop()

    if tk._default_root is not None:
        tk._default_root.after(0, show)
    else:
        show()
