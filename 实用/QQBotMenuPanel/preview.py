# -*- encoding: utf-8 -*-
"""仿 QQ 客户端的自定义菜单 / 指令面板实时预览。"""

import tkinter

from . import config
from . import function

PHONE_WIDTH = 340
PHONE_HEIGHT = 600

COLOR_CHAT_BG = '#ededed'
COLOR_HEADER = '#ffffff'
COLOR_TEXT = '#111111'
COLOR_SUBTEXT = '#8a8a8a'
COLOR_GREEN = '#95ec69'
COLOR_WHITE = '#ffffff'
COLOR_BLUE = '#0099ff'
COLOR_DIVIDER = '#e5e5e5'
COLOR_SWITCH_ON = '#07c160'
COLOR_SWITCH_OFF = '#e5e5e5'
COLOR_HINT = '#ff8c00'
COLOR_INPUT = '#ffffff'
COLOR_PANEL_SHADOW = '#d0d0d0'
COLOR_ADMIN = '#ff6a00'


class QQScenePreview(object):
    """手机 QQ 对话窗预览，配置改动后立即重绘。"""

    def __init__(self, parent_widget):
        self.scope = config.SCOPE_C2C
        self.mode = 'menu'
        self.bot_name = '官方机器人'
        self.menu_items = []
        self.panel_items = []
        self.panel_remark = ''
        self.input_text = ''
        self.status_hint = '配置改动会立即反映到这里'
        self.expanded_menu_index = None
        self.switch_preview_state = {}
        self.hit_regions = []

        self.canvas = tkinter.Canvas(
            parent_widget,
            width=PHONE_WIDTH,
            height=PHONE_HEIGHT,
            bg='#d8d8d8',
            highlightthickness=0,
        )
        self.canvas.bind('<Button-1>', self.handle_click)

    def pack(self, **kwargs):
        self.canvas.pack(**kwargs)

    def grid(self, **kwargs):
        self.canvas.grid(**kwargs)

    def set_state(
        self,
        scope=None,
        mode=None,
        bot_name=None,
        menu_items=None,
        panel_items=None,
        panel_remark=None,
        input_text=None,
        status_hint=None,
    ):
        if scope is not None:
            self.scope = scope
        if mode is not None:
            self.mode = mode
        if bot_name is not None:
            self.bot_name = bot_name or '官方机器人'
        if menu_items is not None:
            self.menu_items = [function.normalize_menu_item(item) for item in menu_items]
        if panel_items is not None:
            self.panel_items = [function.normalize_panel_item(item) for item in panel_items]
        if panel_remark is not None:
            self.panel_remark = function.safe_str(panel_remark)
        if input_text is not None:
            self.input_text = function.safe_str(input_text)
        if status_hint is not None:
            self.status_hint = function.safe_str(status_hint)
        self.render()

    def handle_click(self, event) -> None:
        for region in reversed(self.hit_regions):
            if region['x1'] <= event.x <= region['x2'] and region['y1'] <= event.y <= region['y2']:
                self._apply_hit(region)
                self.render()
                return

    def _apply_hit(self, region) -> None:
        kind = region.get('kind')
        payload = region.get('payload', {})
        if kind == 'menu_send':
            self.input_text = function.safe_str(payload.get('send_message', ''))
            self.status_hint = '点击后会把文本填入输入框：' + self.input_text
        elif kind == 'menu_link':
            self.status_hint = '点击后将跳转：' + function.safe_str(payload.get('link', ''))
        elif kind == 'menu_switch':
            switch_id = function.safe_str(payload.get('switch_id', ''))
            current = self.switch_preview_state.get(switch_id, bool(payload.get('default', False)))
            self.switch_preview_state[switch_id] = not current
            self.status_hint = (
                f'开关 {switch_id} 预览为 '
                + ('打开（消息 ext 将带 ' + switch_id + '=1）' if not current else '关闭')
            )
        elif kind == 'menu_fold':
            index = payload.get('index')
            self.expanded_menu_index = None if self.expanded_menu_index == index else index
        elif kind == 'panel_command':
            self.input_text = function.safe_str(payload.get('name', ''))
            self.status_hint = '点击指令后填入输入框：' + self.input_text
        elif kind == 'panel_link':
            self.status_hint = '点击后将在浏览器打开：' + function.safe_str(payload.get('link', ''))

    def render(self) -> None:
        canvas = self.canvas
        canvas.delete('all')
        self.hit_regions = []
        width = PHONE_WIDTH
        height = PHONE_HEIGHT
        canvas.create_rectangle(8, 8, width - 8, height - 8, fill=COLOR_CHAT_BG, outline='#c8c8c8')
        self._draw_status_bar()
        self._draw_header()
        self._draw_chat_bubbles()
        input_top = self._draw_input_bar()
        menu_top = input_top
        if self.scope == config.SCOPE_C2C and self.menu_items:
            menu_top = self._draw_menu_bar(input_top)
        if self.mode == 'panel':
            self._draw_command_panel(menu_top)
        if self.expanded_menu_index is not None:
            self._draw_submenu_popup(menu_top)
        self._draw_footer_hint()

    def _draw_status_bar(self) -> None:
        self.canvas.create_rectangle(8, 8, PHONE_WIDTH - 8, 30, fill='#f7f7f7', outline='')
        self.canvas.create_text(24, 19, text='9:41', fill=COLOR_TEXT, font=('微软雅黑', 8), anchor='w')
        self.canvas.create_text(
            PHONE_WIDTH - 24,
            19,
            text='QQ',
            fill=COLOR_SUBTEXT,
            font=('微软雅黑', 8),
            anchor='e',
        )

    def _draw_header(self) -> None:
        self.canvas.create_rectangle(8, 30, PHONE_WIDTH - 8, 78, fill=COLOR_HEADER, outline='')
        self.canvas.create_line(8, 78, PHONE_WIDTH - 8, 78, fill=COLOR_DIVIDER)
        title, subtitle = self._header_texts()
        self.canvas.create_oval(20, 40, 56, 70, fill='#4ea1ff', outline='')
        self.canvas.create_text(38, 55, text='机', fill=COLOR_WHITE, font=('微软雅黑', 10, 'bold'))
        self.canvas.create_text(66, 48, text=title, fill=COLOR_TEXT, font=('微软雅黑', 11, 'bold'), anchor='w')
        self.canvas.create_text(66, 66, text=subtitle, fill=COLOR_SUBTEXT, font=('微软雅黑', 8), anchor='w')

    def _header_texts(self):
        if self.scope == config.SCOPE_GROUP:
            return '测试群聊', 'QQ 群 · 指令面板预览'
        if self.scope == config.SCOPE_CHANNEL:
            return '# 文字子频道', 'QQ 频道 · 指令面板预览'
        if self.scope == config.SCOPE_DM:
            return '频道私信', '来自某个频道的私信会话'
        return self.bot_name, '消息列表 · 单聊自定义菜单'

    def _draw_chat_bubbles(self) -> None:
        self.canvas.create_rectangle(18, 92, 250, 132, fill=COLOR_WHITE, outline='')
        self.canvas.create_text(
            30,
            112,
            text='你好，我是机器人助手。',
            fill=COLOR_TEXT,
            font=('微软雅黑', 9),
            anchor='w',
        )
        self.canvas.create_rectangle(110, 144, 322, 184, fill=COLOR_GREEN, outline='')
        self.canvas.create_text(
            310,
            164,
            text='看一下底部菜单/指令面板',
            fill=COLOR_TEXT,
            font=('微软雅黑', 9),
            anchor='e',
        )

    def _draw_input_bar(self) -> int:
        top = 534
        self.canvas.create_rectangle(8, top, PHONE_WIDTH - 8, PHONE_HEIGHT - 8, fill=COLOR_INPUT, outline='')
        self.canvas.create_line(8, top, PHONE_WIDTH - 8, top, fill=COLOR_DIVIDER)
        placeholder = self.input_text or ('/' if self.mode == 'panel' else '输入消息...')
        color = COLOR_TEXT if self.input_text else COLOR_SUBTEXT
        self.canvas.create_oval(18, top + 16, 42, top + 40, outline='#bbbbbb')
        self.canvas.create_rectangle(50, top + 14, 250, top + 42, fill='#f3f3f3', outline='')
        self.canvas.create_text(58, top + 28, text=placeholder[:18], fill=color, font=('微软雅黑', 9), anchor='w')
        self.canvas.create_rectangle(258, top + 14, 322, top + 42, fill=COLOR_BLUE, outline='')
        self.canvas.create_text(290, top + 28, text='发送', fill=COLOR_WHITE, font=('微软雅黑', 9, 'bold'))
        return top

    def _draw_menu_bar(self, input_top: int) -> int:
        rows = self._chunk(self.menu_items, 4)
        row_height = 46
        bar_height = 10 + row_height * max(len(rows), 1)
        top = input_top - bar_height
        self.canvas.create_rectangle(8, top, PHONE_WIDTH - 8, input_top, fill='#fafafa', outline='')
        self.canvas.create_line(8, top, PHONE_WIDTH - 8, top, fill=COLOR_DIVIDER)
        self.canvas.create_text(
            20,
            top + 10,
            text='自定义菜单',
            fill=COLOR_SUBTEXT,
            font=('微软雅黑', 8),
            anchor='w',
        )
        y = top + 16
        for row_index, row in enumerate(rows):
            x = 16
            cell_width = 76
            for item_index, item in enumerate(row):
                global_index = row_index * 4 + item_index
                self._draw_menu_chip(x, y, x + cell_width, y + 32, item, global_index)
                x += cell_width + 4
            y += row_height - 8
        return top

    def _draw_menu_chip(self, x1, y1, x2, y2, item, index) -> None:
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=COLOR_WHITE, outline='#dcdcdc')
        name = item.get('name', '') or item.get('type', '')
        item_type = item.get('type', '')
        if item_type == 'switch':
            switch_id = item.get('switch', {}).get('switch_id', '')
            default_on = bool(item.get('switch', {}).get('default', False))
            is_on = self.switch_preview_state.get(switch_id, default_on)
            knob_color = COLOR_SWITCH_ON if is_on else COLOR_SWITCH_OFF
            self.canvas.create_text(x1 + 6, (y1 + y2) / 2, text=name[:4], fill=COLOR_TEXT, font=('微软雅黑', 8), anchor='w')
            self.canvas.create_oval(x2 - 20, y1 + 8, x2 - 6, y2 - 8, fill=knob_color, outline='')
            self._add_hit(x1, y1, x2, y2, 'menu_switch', item.get('switch', {}))
        elif item_type == 'menu':
            self.canvas.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=(name[:4] + '▾'),
                fill=COLOR_TEXT,
                font=('微软雅黑', 8),
            )
            self._add_hit(x1, y1, x2, y2, 'menu_fold', {'index': index})
        elif item_type == 'link':
            self.canvas.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=(name[:4] + '↗'),
                fill=COLOR_BLUE,
                font=('微软雅黑', 8),
            )
            self._add_hit(x1, y1, x2, y2, 'menu_link', item)
        else:
            self.canvas.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=name[:5],
                fill=COLOR_TEXT,
                font=('微软雅黑', 8),
            )
            self._add_hit(x1, y1, x2, y2, 'menu_send', item)

    def _draw_submenu_popup(self, menu_top: int) -> None:
        if self.expanded_menu_index is None:
            return
        if self.expanded_menu_index >= len(self.menu_items):
            return
        item = self.menu_items[self.expanded_menu_index]
        sub_items = item.get('sub_menu_items', [])
        if not sub_items:
            return
        height = 28 + 28 * len(sub_items)
        top = max(86, menu_top - height - 8)
        left = 70
        right = PHONE_WIDTH - 24
        self.canvas.create_rectangle(left, top, right, top + height, fill=COLOR_WHITE, outline='#d0d0d0')
        self.canvas.create_text(
            left + 10,
            top + 14,
            text=item.get('name', '子菜单'),
            fill=COLOR_SUBTEXT,
            font=('微软雅黑', 8),
            anchor='w',
        )
        y = top + 26
        for sub_item in sub_items:
            self.canvas.create_text(
                left + 12,
                y + 10,
                text=sub_item.get('name', ''),
                fill=COLOR_TEXT,
                font=('微软雅黑', 9),
                anchor='w',
            )
            kind = 'menu_link' if sub_item.get('type') == 'link' else 'menu_send'
            self._add_hit(left, y, right, y + 24, kind, sub_item)
            y += 28

    def _draw_command_panel(self, bottom: int) -> None:
        items = self.panel_items[:config.PANEL_ITEM_MAX]
        row_height = 42
        card_height = 36 + row_height * max(len(items), 1) + 8
        top = max(90, bottom - card_height - 8)
        left = 16
        right = PHONE_WIDTH - 16
        self.canvas.create_rectangle(
            left + 2,
            top + 4,
            right + 2,
            top + card_height + 4,
            fill=COLOR_PANEL_SHADOW,
            outline='',
        )
        self.canvas.create_rectangle(left, top, right, top + card_height, fill=COLOR_WHITE, outline='')
        title = '指令面板'
        if self.panel_remark:
            title = title + ' · ' + self.panel_remark[:10]
        self.canvas.create_text(left + 12, top + 16, text=title, fill=COLOR_TEXT, font=('微软雅黑', 10, 'bold'), anchor='w')
        self.canvas.create_text(
            right - 12,
            top + 16,
            text=config.SCOPE_LABEL_DICT.get(self.scope, self.scope),
            fill=COLOR_SUBTEXT,
            font=('微软雅黑', 8),
            anchor='e',
        )
        y = top + 32
        if not items:
            self.canvas.create_text(left + 12, y + 16, text='当前还没有指令', fill=COLOR_SUBTEXT, font=('微软雅黑', 9), anchor='w')
            return
        for item in items:
            self.canvas.create_line(left + 10, y, right - 10, y, fill=COLOR_DIVIDER)
            name = item.get('name', '') or '未命名'
            desc = item.get('desc', '') or (item.get('link', '') if item.get('type') == 'link' else '')
            self.canvas.create_text(left + 12, y + 20, text=name[:8], fill=COLOR_TEXT, font=('微软雅黑', 10), anchor='w')
            if item.get('only_admin'):
                self.canvas.create_text(left + 92, y + 20, text='管理员', fill=COLOR_ADMIN, font=('微软雅黑', 8), anchor='w')
            right_text = ('↗ ' + desc[:10]) if item.get('type') == 'link' else desc[:12]
            self.canvas.create_text(
                right - 12,
                y + 20,
                text=right_text,
                fill=COLOR_SUBTEXT,
                font=('微软雅黑', 8),
                anchor='e',
            )
            kind = 'panel_link' if item.get('type') == 'link' else 'panel_command'
            self._add_hit(left, y, right, y + row_height, kind, item)
            y += row_height

    def _draw_footer_hint(self) -> None:
        if self.status_hint:
            self.canvas.create_text(
                PHONE_WIDTH / 2,
                86,
                text=self.status_hint[:28],
                fill=COLOR_HINT,
                font=('微软雅黑', 8),
            )

    def _add_hit(self, x1, y1, x2, y2, kind, payload) -> None:
        self.hit_regions.append({
            'x1': x1,
            'y1': y1,
            'x2': x2,
            'y2': y2,
            'kind': kind,
            'payload': payload,
        })

    def _chunk(self, value_list, size):
        return [value_list[index:index + size] for index in range(0, len(value_list), size)]
