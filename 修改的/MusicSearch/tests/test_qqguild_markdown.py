"""验证发送路由、链接按钮和外部接口失败时的行为，无需连接机器人。"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image


PLUGIN_DIR = Path(__file__).resolve().parents[1]


class MarkdownReplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # load 模块在导入时创建数据目录，限制到测试专用临时目录。
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)
                spec = importlib.util.spec_from_file_location(
                    'MusicSearch', PLUGIN_DIR / '__init__.py',
                    submodule_search_locations=[str(PLUGIN_DIR)],
                )
                package = importlib.util.module_from_spec(spec)
                sys.modules['MusicSearch'] = package
                spec.loader.exec_module(package)
                cls.module = package.main
                cls.processor = package.main.MusicSearchProcessor
                cls.real_cover_size = cls.processor.get_cover_size
            finally:
                os.chdir(original_cwd)

    def setUp(self):
        self.song = {
            'id': 186016,
            'name': '晴天',
            'singers': [{'name': '周杰伦'}],
            'duration': 269000,
            'album': '叶惠美',
            'picurl': 'https://p1.music.126.net/cover.jpg',
            'jumpurl': 'https://music.163.com/#/song?id=186016',
            'pay': True,
        }
        self.proc = SimpleNamespace(log=Mock())
        cover_probe = patch.object(self.processor, 'get_cover_size', return_value=(800, 800))
        self.cover_probe = cover_probe.start()
        self.addCleanup(cover_probe.stop)

    def event(self, *, is_group=True, extend=None, sdk='qqGuildv2_link'):
        return SimpleNamespace(
            platform={'sdk': sdk, 'platform': 'qqGuild'},
            plugin_info={'func_type': 'group_message' if is_group else 'private_message'},
            bot_info=SimpleNamespace(hash='test-bot'),
            data=SimpleNamespace(
                message='.点歌晴天', message_id='trigger-message',
                group_id='current-group', user_id='current-user', host_id=None,
                extend=extend if extend is not None else {'flag_from_qq': True},
            ),
            indeAPI=SimpleNamespace(
                hasAPI=Mock(return_value=True),
                create_markdown_message=Mock(return_value={'active': True}),
            ),
            reply=Mock(),
        )

    def test_song_information_and_public_jump_button(self):
        event = self.event()
        self.assertTrue(self.processor.reply_song_markdown(event, self.proc, self.song, True))
        payload = event.indeAPI.create_markdown_message.call_args.kwargs
        content = payload['markdown']['content']
        for text in ('晴天', '歌手：周杰伦　·　时长：04:29', '专辑：叶惠美', '歌曲 ID：186016', '付费歌曲'):
            self.assertIn(text, content)
        self.assertIn('![歌曲封面 #800px #800px](https://p1.music.126.net/cover.jpg)', content)
        self.assertIn('时长：04:29\n专辑：叶惠美\n歌曲 ID：186016', content)
        button = payload['keyboard']['content']['rows'][0]['buttons'][0]
        self.assertEqual('打开网易云音乐', button['render_data']['label'])
        self.assertEqual(0, button['action']['type'])
        self.assertEqual({'type': 2}, button['action']['permission'])
        self.assertEqual(self.song['jumpurl'], button['action']['data'])
        self.assertEqual('trigger-message', payload['msg_id'])
        event.reply.assert_not_called()

    def test_all_four_conversations_use_current_event_target(self):
        cases = [
            (True, {'flag_from_qq': True}, 'qq_group', 'current-group'),
            (False, {'flag_from_qq': True}, 'qq_private', 'current-user'),
            (True, {'flag_from_qq': False}, 'guild_channel', 'current-group'),
            (False, {'flag_from_qq': False, 'host_group_id': 'dm-guild'}, 'guild_private', 'dm-guild'),
        ]
        for is_group, extend, chat_type, chat_id in cases:
            with self.subTest(chat_type=chat_type):
                event = self.event(is_group=is_group, extend=extend)
                self.processor.reply_song_markdown(event, self.proc, self.song, is_group)
                payload = event.indeAPI.create_markdown_message.call_args.kwargs
                self.assertEqual(chat_type, payload['chat_type'])
                self.assertEqual(chat_id, payload['chat_id'])

    def test_missing_channel_private_host_falls_back_to_group_id(self):
        event = self.event(is_group=False, extend={'flag_from_qq': False, 'flag_from_direct': True})
        self.processor.reply_song_markdown(event, self.proc, self.song, False)
        payload = event.indeAPI.create_markdown_message.call_args.kwargs
        self.assertEqual('guild_private', payload['chat_type'])
        self.assertEqual('current-group', payload['chat_id'])

    def test_untrusted_names_cannot_inject_markdown_or_tags(self):
        self.song['name'] = '*测试*\n## 标题 <qqbot-at-everyone />'
        content = self.processor.build_song_markdown(self.song)[0]['content']
        self.assertIn(r'\*测试\* \#\# 标题 &lt;qqbot', content)
        self.assertNotIn('<qqbot-at-everyone', content)

    def test_missing_or_malformed_link_uses_song_id(self):
        for link in ('', 'javascript:alert(1)', 'https://', 'http://['):
            with self.subTest(link=link):
                self.song['jumpurl'] = link
                keyboard = self.processor.build_song_markdown(self.song)[1]
                action = keyboard['content']['rows'][0]['buttons'][0]['action']
                self.assertEqual('https://music.163.com/song?id=186016', action['data'])

    def test_no_link_or_id_omits_button(self):
        self.song.pop('id')
        self.song.pop('jumpurl')
        self.assertIsNone(self.processor.build_song_markdown(self.song)[1])

    def test_duration_formats_minutes_hours_and_unknown(self):
        for duration, expected in ((269000, '04:29'), (3661000, '1:01:01'), (None, '未知'), (0, '未知')):
            with self.subTest(duration=duration):
                self.assertEqual(expected, self.processor.format_duration(duration))

    def test_detail_fetch_matches_song_id_and_preserves_search_data(self):
        song = {key: value for key, value in self.song.items() if key not in ('duration', 'album')}
        response = io.BytesIO(json.dumps({
            'code': 200, 'songs': [
                {'id': 1, 'duration': 1000, 'album': {'name': '错误专辑'}},
                {'id': 186016, 'duration': 269000, 'album': {'name': '叶惠美'}},
            ],
        }).encode())
        with patch.object(self.module.urllib.request, 'urlopen', return_value=response) as request:
            result = self.processor.complete_song_details(song, self.proc)
        self.assertEqual(269000, result['duration'])
        self.assertEqual('叶惠美', result['album'])
        self.assertEqual(song['name'], result['name'])
        self.assertNotIn('duration', song)
        self.assertEqual(5, request.call_args.kwargs['timeout'])

    def test_detail_failure_still_sends_song_with_unknown_duration(self):
        self.song.pop('duration')
        for error in (urllib.error.URLError('unavailable'), ValueError('invalid JSON')):
            with self.subTest(error=type(error).__name__):
                event = self.event()
                with patch.object(self.module.urllib.request, 'urlopen', side_effect=error):
                    self.processor.reply_song_markdown(event, self.proc, self.song, True)
                content = event.indeAPI.create_markdown_message.call_args.kwargs['markdown']['content']
                self.assertIn('歌手：周杰伦　·　时长：未知', content)
                self.assertIn('晴天', content)
                event.reply.assert_not_called()

    def test_markdown_failures_return_text_and_link_without_card(self):
        for failure in ('unsupported', 'inactive', 'exception'):
            with self.subTest(failure=failure):
                event = self.event()
                if failure == 'unsupported':
                    event.indeAPI.hasAPI.return_value = False
                elif failure == 'inactive':
                    event.indeAPI.create_markdown_message.return_value = {'active': False}
                else:
                    event.indeAPI.create_markdown_message.side_effect = RuntimeError('send error')
                self.assertFalse(self.processor.reply_song_markdown(event, self.proc, self.song, True))
                text = event.reply.call_args.args[0]
                self.assertIn('04:29', text)
                self.assertIn('专辑：叶惠美\n歌曲 ID：186016', text)
                self.assertIn(self.song['jumpurl'], text)
                self.assertNotIn('[CQ:', text)

    def test_command_routes_qqguild_to_markdown_and_onebot_to_music_card(self):
        for sdk in ('qqGuildv2_link', 'onebot'):
            with self.subTest(sdk=sdk):
                event = self.event(sdk=sdk)
                with (
                    patch.object(self.processor, 'reload_config_for_bot'),
                    patch.object(self.processor, 'is_group_enabled', return_value=True),
                    patch.object(self.processor, 'is_enabled_for_context', return_value=True),
                    patch.object(self.processor, 'get_song_result', return_value={'code': 0, 'data': [self.song]}),
                    patch.object(self.module.urllib.request, 'urlopen') as network,
                ):
                    self.processor.handle_message(event, self.proc, True)
                network.assert_not_called()
                if sdk == 'onebot':
                    event.indeAPI.create_markdown_message.assert_not_called()
                    self.assertTrue(event.reply.call_args.args[0].startswith('[CQ:music,type=163,id=186016,'))
                else:
                    event.indeAPI.create_markdown_message.assert_called_once()
                    event.reply.assert_not_called()

    def test_album_label_is_retained_even_when_name_matches_title(self):
        self.song.update(name='Immaculate', album='Immaculate', pay=False)
        content = self.processor.build_song_markdown(self.song)[0]['content']
        self.assertEqual(2, content.count('Immaculate'))
        self.assertIn('专辑：Immaculate', content)

    def test_missing_or_invalid_cover_keeps_text_and_button(self):
        for cover in ('', None, 'file:///private.jpg', 'https://', 'http://['):
            with self.subTest(cover=cover):
                self.song['picurl'] = cover
                markdown, keyboard = self.processor.build_song_markdown(self.song)
                self.assertNotIn('![', markdown['content'])
                self.assertIn('歌手：周杰伦　·　时长：04:29', markdown['content'])
                self.assertIsNotNone(keyboard)

    def test_cover_url_cannot_insert_extra_markdown(self):
        self.song['picurl'] = 'https://example.com/cover(test).jpg\n<qqbot-at-everyone />'
        content = self.processor.build_song_markdown(self.song)[0]['content']
        self.assertNotIn('<qqbot-at-everyone', content)
        self.assertIn('cover%28test%29.jpg%0A%3Cqqbot-at-everyone%20/%3E', content)

    def test_cover_dimensions_match_landscape_portrait_and_square_image_headers(self):
        for image_format, size in (('JPEG', (960, 540)), ('PNG', (400, 900)), ('WEBP', (600, 600))):
            with self.subTest(image_format=image_format, size=size):
                image_bytes = io.BytesIO()
                Image.new('RGB', size).save(image_bytes, format=image_format)
                response = io.BytesIO(image_bytes.getvalue())
                with patch.object(self.module.urllib.request, 'urlopen', return_value=response):
                    measured_size = self.real_cover_size(self.song['picurl'])
                self.assertEqual(size, measured_size)
                self.cover_probe.return_value = measured_size
                markdown = self.processor.build_song_markdown(self.song)[0]['content']
                self.assertIn(f'#{size[0]}px #{size[1]}px', markdown)

    def test_unreadable_cover_does_not_invent_dimensions(self):
        for error in (urllib.error.URLError('unavailable'), ValueError('invalid header')):
            with self.subTest(error=type(error).__name__):
                with patch.object(self.module.urllib.request, 'urlopen', side_effect=error):
                    self.assertIsNone(self.real_cover_size(self.song['picurl']))
        with patch.object(self.module.urllib.request, 'urlopen', return_value=io.BytesIO(b'not an image')):
            self.assertIsNone(self.real_cover_size(self.song['picurl']))
        self.cover_probe.return_value = None
        markdown, keyboard = self.processor.build_song_markdown(self.song)
        self.assertIn('![歌曲封面](https://p1.music.126.net/cover.jpg)', markdown['content'])
        self.assertNotIn('px', markdown['content'])
        self.assertIsNotNone(keyboard)


if __name__ == '__main__':
    unittest.main()
