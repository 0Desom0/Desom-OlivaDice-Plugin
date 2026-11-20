# -*- encoding: utf-8 -*-
"""列表页排版：提示语必须留在正文里，翻页按钮必须挂在消息上。"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = '_iwanna_search_page_test'


class FakeMarkdownApi:
    """记录 create_markdown_message 的 payload，不发网络请求。"""

    def __init__(self):
        self.payloads = []

    def install(self, event):
        def create_markdown_message(**kwargs):
            self.payloads.append(kwargs)
            return {'active': True, 'data': {'message_ids': ['m1']}}

        event.indeAPI = types.SimpleNamespace(
            create_markdown_message=create_markdown_message,
            send_message=lambda *args, **kwargs: {'active': True, 'data': {}},
            event=event,
        )

    @property
    def last_markdown(self):
        return self.payloads[-1]['markdown']['content']

    @property
    def last_keyboard(self):
        return self.payloads[-1].get('keyboard')


def build_event(api, message_id='msg-1'):
    event = types.SimpleNamespace(
        data=types.SimpleNamespace(
            user_id='user-1', group_id='group-1', message_id=message_id,
            message='.iw I wanna be the adventurer', webui=None, extend={},
        ),
        plugin_info={'func_type': 'group_message', 'namespace': 'IWannaSearch'},
        bot_info=types.SimpleNamespace(id='bot-1', hash='bot-hash'),
        platform={'sdk': 'qqGuildv2_link', 'platform': 'qqGuild', 'model': 'public'},
        base_info={'self_id': 'bot-1'},
        log_func=lambda *args, **kwargs: None,
    )
    event.reply = lambda *args, **kwargs: {'active': True, 'data': {}}
    api.install(event)
    return event


def build_results(count):
    return [
        {'id': str(9000 + index), 'title': 'I Wanna Be The Adventurer %d' % index,
         'url': '', 'page_url': ''}
        for index in range(1, count + 1)
    ]


def keyboard_labels(keyboard):
    if not keyboard:
        return []
    return [
        button['render_data']['label']
        for row in keyboard['content']['rows']
        for button in row['buttons']
    ]


def keyboard_actions(keyboard):
    if not keyboard:
        return []
    return [button['action']['data'] for row in keyboard['content']['rows'] for button in row['buttons']]


class IWannaListPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules_patch = patch.dict(sys.modules, {'OlivOS': types.ModuleType('OlivOS')})
        cls.modules_patch.start()
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_DIR / '__init__.py')
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        cls.message = package.main.message

    @classmethod
    def tearDownClass(cls):
        cls.modules_patch.stop()

    def session(self, index=1, count=20):
        return {'results': build_results(count), 'count': count, 'page_size': 8, 'page_index': index}

    def test_markdown_page_keeps_prompt_and_page_buttons(self):
        api = FakeMarkdownApi()
        event = build_event(api)
        self.message.reply_result_page(event, self.session(index=1))

        content = api.last_markdown
        self.assertIn('当前页数：2/3', content)
        # 列表下面必须有「输入序号」提示，不能只剩按钮。
        self.assertIn('输入序号', content)
        self.assertIn('end/结束', content)
        self.assertEqual(['上一页', '下一页', '跳页'], keyboard_labels(api.last_keyboard))
        self.assertEqual(['iw:pg:prev', 'iw:pg:next', '.iw 跳页 '], keyboard_actions(api.last_keyboard))

    def test_first_page_has_no_prev_and_last_page_has_no_next(self):
        api = FakeMarkdownApi()
        event = build_event(api)
        self.message.reply_result_page(event, self.session(index=0))
        self.assertEqual(['下一页', '跳页'], keyboard_labels(api.last_keyboard))

        api = FakeMarkdownApi()
        event = build_event(api)
        self.message.reply_result_page(event, self.session(index=2))
        self.assertEqual(['上一页', '跳页'], keyboard_labels(api.last_keyboard))

    def test_single_page_list_keeps_input_prompt(self):
        api = FakeMarkdownApi()
        event = build_event(api)
        self.message.reply_result_page(event, {'results': build_results(3), 'count': 3,
                                               'page_size': 8, 'page_index': 0})

        content = api.last_markdown
        self.assertIn('输入对应序号', content)
        self.assertNotIn('当前页数', content)
        self.assertIsNone(api.last_keyboard)

    def test_jump_page_keeps_page_buttons(self):
        api = FakeMarkdownApi()
        event = build_event(api)
        session = self.session(index=0)
        with patch.object(self.message, 'reply_result_page') as recorder:
            handled = self.message.handle_jump_page_input(event, session, '3')
        self.assertTrue(handled)
        self.assertEqual(2, session['page_index'])
        recorder.assert_called_once_with(event, session)

    def test_jump_page_out_of_range_does_not_move_page(self):
        api = FakeMarkdownApi()
        event = build_event(api)
        session = self.session(index=0)
        with patch.object(self.message.utils, 'reply_message', Mock()):
            handled = self.message.handle_jump_page_input(event, session, '9')
        self.assertTrue(handled)
        self.assertEqual(0, session['page_index'])


if __name__ == '__main__':
    unittest.main()
