"""验证发送路由、链接按钮和外部接口失败时的行为，无需连接机器人。"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event as ThreadEvent
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
                # 单元测试不启动宿主、不读取真实机器人配置。
                fake_olivos = SimpleNamespace(API=SimpleNamespace(Event=SimpleNamespace(button_click=object)))
                with patch.dict(sys.modules, {'OlivOS': fake_olivos}):
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
        button_storage = tempfile.TemporaryDirectory(prefix='MusicSearch-button-test-')
        self.addCleanup(button_storage.cleanup)
        storage_patch = patch.object(self.module.voice.load, 'data_dir', button_storage.name)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
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
                send_message=Mock(return_value={'active': True}),
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
        self.assertEqual('打开链接', button['render_data']['label'])
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

    def test_voice_button_uses_callback_on_supported_host(self):
        event = self.event()
        self.processor.reply_song_markdown(event, self.proc, self.song, True)
        buttons = event.indeAPI.create_markdown_message.call_args.kwargs['keyboard']['content']['rows'][0]['buttons']
        self.assertEqual(2, len(buttons))
        self.assertEqual('MusicSearch_voice', buttons[1]['id'])
        self.assertEqual('发送音乐', buttons[1]['render_data']['label'])
        self.assertEqual(1, buttons[1]['action']['type'])
        self.assertRegex(buttons[1]['action']['data'], r'^MusicSearch:voice:186016:[0-9a-f]{32}$')

    def test_old_host_uses_auto_send_command_button(self):
        event = self.event()
        with patch.object(self.module.OlivOS.API, 'Event', SimpleNamespace()):
            self.processor.reply_song_markdown(event, self.proc, self.song, True)
        button = event.indeAPI.create_markdown_message.call_args.kwargs['keyboard']['content']['rows'][0]['buttons'][1]
        self.assertEqual(2, button['action']['type'])
        self.assertEqual('.点歌语音 186016', button['action']['data'])
        self.assertTrue(button['action']['enter'])

    def test_channel_does_not_show_unsupported_voice_button(self):
        event = self.event(extend={'flag_from_qq': False})
        self.processor.reply_song_markdown(event, self.proc, self.song, True)
        buttons = event.indeAPI.create_markdown_message.call_args.kwargs['keyboard']['content']['rows'][0]['buttons']
        self.assertEqual(['music_open'], [button['id'] for button in buttons])

    def test_voice_button_payload_is_filtered_and_respects_switches(self):
        event = self.event()
        event.plugin_info['func_type'] = 'button_click'
        event.data.button_id = 'MusicSearch_voice'
        event.data.button_data = 'MusicSearch:voice:186016'
        for enabled, expected_calls in ((True, 1), (False, 0)):
            with (
                self.subTest(enabled=enabled),
                patch.object(self.processor, 'reload_config_for_bot'),
                patch.object(self.processor, 'config', {'enabled': True}),
                patch.object(self.processor, 'is_group_enabled', return_value=enabled),
                patch.object(self.processor, 'is_enabled_for_context', return_value=True),
                patch.object(self.module.voice, 'send_song') as sender,
            ):
                self.module.Event.button_click(event, self.proc)
                self.assertEqual(expected_calls, sender.call_count)
        event.data.button_data = 'MusicSearch:voice:https://example.com/private'
        with patch.object(self.module.voice, 'send_song') as sender:
            self.module.Event.button_click(event, self.proc)
        sender.assert_not_called()

    def test_callback_can_use_namespaced_data_when_platform_omits_button_id(self):
        event = self.event()
        event.plugin_info['func_type'] = 'button_click'
        event.data.button_id = None
        event.data.button_data = 'MusicSearch:voice:186016'
        with (
            patch.object(self.processor, 'reload_config_for_bot'),
            patch.object(self.processor, 'config', {'enabled': True}),
            patch.object(self.processor, 'is_group_enabled', return_value=True),
            patch.object(self.processor, 'is_enabled_for_context', return_value=True),
            patch.object(self.module.voice, 'send_song') as sender,
        ):
            self.module.Event.button_click(event, self.proc)
        sender.assert_called_once_with(self.processor, event, self.proc, '186016', True)

    def test_voice_command_does_not_search_as_song_name(self):
        event = self.event()
        event.data.message = '.点歌语音 186016'
        with (
            patch.object(self.processor, 'reload_config_for_bot'),
            patch.object(self.processor, 'config', {'enabled': True}),
            patch.object(self.processor, 'is_group_enabled', return_value=True),
            patch.object(self.processor, 'is_enabled_for_context', return_value=True),
            patch.object(self.module.voice, 'send_song') as sender,
            patch.object(self.processor, 'get_song_result') as search,
        ):
            self.processor.handle_message(event, self.proc, True)
        sender.assert_called_once_with(self.processor, event, self.proc, '186016', True)
        search.assert_not_called()

    def test_local_music_bytes_sent_then_temporary_file_removed(self):
        event = self.event()
        event.plugin_info['func_type'] = 'button_click'
        event.data.extend.update(event_id='click-interaction', flag_from_direct=False)
        event.data.message_id = 'old-card-message'
        music = b'ID3' + b'\x00' * 30
        response = io.BytesIO(music)
        response.headers = {'Content-Length': str(len(music))}
        captured_paths = []

        def check_uploaded_file(**kwargs):
            from urllib.parse import unquote, urlsplit
            uri = kwargs['message'][len('[OP:record,file='):-1]
            parsed = urlsplit(uri)
            path_text = unquote(parsed.path)
            if os.name == 'nt' and path_text.startswith('/'):
                path_text = path_text[1:]
            audio_path = Path(path_text)
            self.assertEqual(music, audio_path.read_bytes())
            self.assertEqual('click-interaction', kwargs['event_id'])
            self.assertNotIn('reply_msg_id', kwargs)
            self.assertFalse(kwargs['flag_log'])
            captured_paths.append(audio_path)
            return {'active': True}

        event.indeAPI.send_message.side_effect = check_uploaded_file
        with (
            patch.object(self.processor, 'search_music', return_value={
                'code': 0, 'data': [{'id': 186016, 'url': 'https://example.com/music.mp3'}],
            }),
            patch.object(self.module.voice.urllib.request, 'urlopen', return_value=response),
        ):
            self.module.voice.send_song(self.processor, event, self.proc, '186016', True)
        self.assertEqual(1, len(captured_paths))
        self.assertFalse(captured_paths[0].parent.exists())

    def test_voice_command_reply_uses_current_user_message(self):
        event = self.event(is_group=False, extend={'flag_from_qq': True, 'flag_from_direct': True})
        self.module.voice.send(event, 'qq_private', 'current-user', '[OP:record,file=file:///test.mp3]')
        payload = event.indeAPI.send_message.call_args.kwargs
        self.assertEqual('trigger-message', payload['reply_msg_id'])
        self.assertNotIn('event_id', payload)

    def test_download_rejects_pages_oversized_and_truncated_audio(self):
        scenarios = [
            (b'<html>error</html>', {}, '不是受支持的音频'),
            (b'ID3', {'Content-Length': str(21 * 1024 * 1024)}, '超过'),
            (b'ID3', {'Content-Length': '100'}, '不完整'),
        ]
        for data, headers, reason in scenarios:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temp_dir:
                response = io.BytesIO(data)
                response.headers = headers
                with patch.object(self.module.voice.urllib.request, 'urlopen', return_value=response):
                    with self.assertRaisesRegex(self.module.voice.VoiceError, reason):
                        self.module.voice.download_audio('https://example.com/music.mp3', temp_dir, {})

    def test_audio_without_download_url_returns_clear_error(self):
        event = self.event()
        with (
            patch.object(self.processor, 'search_music', return_value={
                'code': 0, 'data': [{'id': 186016, 'url': None}],
            }),
            patch.object(self.module.voice, 'download_audio') as download,
        ):
            self.module.voice.send_song(self.processor, event, self.proc, '186016', True)
        download.assert_not_called()
        self.assertIn('没有可下载', event.indeAPI.send_message.call_args.kwargs['message'])

    def test_voice_upload_failure_removes_temporary_file(self):
        event = self.event()
        event.indeAPI.send_message.return_value = {'active': False}
        paths = []

        def download(_url, directory, _headers):
            path = Path(directory) / 'music.mp3'
            path.write_bytes(b'ID3')
            paths.append(path)
            return path

        with (
            patch.object(self.processor, 'search_music', return_value={
                'code': 0, 'data': [{'id': 186016, 'url': 'https://example.com/music.mp3'}],
            }),
            patch.object(self.module.voice, 'download_audio', side_effect=download),
        ):
            self.module.voice.send_song(self.processor, event, self.proc, '186016', True)
        self.assertFalse(paths[0].parent.exists())
        self.assertIn('上传或发送失败', event.indeAPI.send_message.call_args.kwargs['message'])

    def test_button_claim_is_atomic_across_concurrent_clicks(self):
        event = self.event()
        payload = self.module.voice.callback_data(186016)
        token = payload.rsplit(':', 1)[1]
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(
                lambda _: self.module.voice.claim_button(event, payload, token), range(8),
            ))
        self.assertEqual(1, sum(result is not None for result in results))
        self.module.voice.finish_button(next(result for result in results if result is not None), False)

    def test_same_button_cannot_be_used_by_another_user_or_after_reload(self):
        event = self.event()
        payload = self.module.voice.callback_data(186016)
        token = payload.rsplit(':', 1)[1]
        button_key = self.module.voice.claim_button(event, payload, token)
        self.assertTrue(button_key)
        self.module.voice.finish_button(button_key, True)
        event.data.user_id = 'another-user'
        event.data.extend['event_id'] = 'different-interaction'
        self.assertFalse(self.module.voice.claim_button(event, payload, token))
        self.assertFalse(self.module.voice.claim_button(event, payload, token))
        # 在新模块实例中只复用磁盘数据，不共享原模块的内存。
        spec = importlib.util.spec_from_file_location('MusicSearch.voice_reload', PLUGIN_DIR / 'voice.py')
        reloaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reloaded)
        self.assertFalse(reloaded.claim_button(event, payload, token))
        new_payload = self.module.voice.callback_data(186016)
        self.assertNotEqual(payload, new_payload)
        new_key = reloaded.claim_button(event, new_payload, new_payload.rsplit(':', 1)[1])
        self.assertTrue(new_key)
        reloaded.finish_button(new_key, False)

    def test_failed_music_attempt_allows_same_button_to_retry(self):
        event = self.event()
        event.plugin_info['func_type'] = 'button_click'
        event.data.button_id = 'MusicSearch_voice'
        event.data.button_data = self.module.voice.callback_data(186016)
        event.data.extend['event_id'] = 'first-interaction'
        with (
            patch.object(self.processor, 'reload_config_for_bot'),
            patch.object(self.processor, 'config', {'enabled': True}),
            patch.object(self.processor, 'is_group_enabled', return_value=True),
            patch.object(self.processor, 'is_enabled_for_context', return_value=True),
            patch.object(self.processor, 'search_music', return_value={
                'code': 0, 'data': [{'id': 186016, 'url': None}],
            }),
        ):
            self.module.Event.button_click(event, self.proc)
            event.data.extend['event_id'] = 'second-interaction'
            self.module.Event.button_click(event, self.proc)
        self.assertEqual(2, event.indeAPI.send_message.call_count)
        # 错误提示即便成功发出，也不会将音乐按钮记为成功。
        self.assertIn('没有可下载', event.indeAPI.send_message.call_args.kwargs['message'])

    def test_running_button_ignores_repeat_clicks_then_success_blocks_future_clicks(self):
        event = self.event()
        event.plugin_info['func_type'] = 'button_click'
        event.data.button_id = 'MusicSearch_voice'
        event.data.button_data = self.module.voice.callback_data(186016)
        event.data.extend['event_id'] = 'first-interaction'
        started, release = ThreadEvent(), ThreadEvent()

        def send_music(*args):
            started.set()
            self.assertTrue(release.wait(5))
            return True

        with (
            patch.object(self.processor, 'reload_config_for_bot'),
            patch.object(self.processor, 'config', {'enabled': True}),
            patch.object(self.processor, 'is_group_enabled', return_value=True),
            patch.object(self.processor, 'is_enabled_for_context', return_value=True),
            patch.object(self.module.voice, 'send_song', side_effect=send_music) as sender,
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first = executor.submit(self.module.Event.button_click, event, self.proc)
            try:
                self.assertTrue(started.wait(5))
                for _ in range(5):
                    self.module.Event.button_click(event, self.proc)
                sender.assert_called_once()
            finally:
                release.set()
            first.result(timeout=5)
            self.module.Event.button_click(event, self.proc)
            sender.assert_called_once()

    def test_unexpected_button_processing_exception_releases_running_slot(self):
        event = self.event()
        event.plugin_info['func_type'] = 'button_click'
        event.data.button_id = 'MusicSearch_voice'
        event.data.button_data = self.module.voice.callback_data(186016)
        with (
            patch.object(self.processor, 'reload_config_for_bot'),
            patch.object(self.processor, 'config', {'enabled': True}),
            patch.object(self.processor, 'is_group_enabled', return_value=True),
            patch.object(self.processor, 'is_enabled_for_context', return_value=True),
            patch.object(self.module.voice, 'send_song', side_effect=[RuntimeError('unexpected'), True]) as sender,
        ):
            self.module.Event.button_click(event, self.proc)
            self.module.Event.button_click(event, self.proc)
            self.module.Event.button_click(event, self.proc)
        self.assertEqual(2, sender.call_count)

    def test_local_music_success_and_upload_failure_return_correct_result(self):
        event = self.event()

        def download(_url, directory, _headers):
            path = Path(directory) / 'music.mp3'
            path.write_bytes(b'ID3')
            return path

        with (
            patch.object(self.processor, 'search_music', return_value={
                'code': 0, 'data': [{'id': 186016, 'url': 'https://example.com/music.mp3'}],
            }),
            patch.object(self.module.voice, 'download_audio', side_effect=download),
        ):
            self.assertIs(True, self.module.voice.send_song(self.processor, event, self.proc, '186016', True))
            event.indeAPI.send_message.return_value = {'active': False}
            self.assertIs(False, self.module.voice.send_song(self.processor, event, self.proc, '186016', True))

    def test_manual_voice_command_can_be_repeated(self):
        event = self.event()
        event.data.message = '.点歌语音 186016'
        with (
            patch.object(self.processor, 'reload_config_for_bot'),
            patch.object(self.processor, 'config', {'enabled': True}),
            patch.object(self.processor, 'is_group_enabled', return_value=True),
            patch.object(self.processor, 'is_enabled_for_context', return_value=True),
            patch.object(self.module.voice, 'send_song') as sender,
            patch.object(self.module.voice, 'claim_button') as claim,
        ):
            self.processor.handle_message(event, self.proc, True)
            self.processor.handle_message(event, self.proc, True)
        self.assertEqual(2, sender.call_count)
        claim.assert_not_called()

    def test_mp3_ogg_and_wav_are_downloaded_without_transcoding(self):
        headers = [
            (b'ID3' + b'\x00' * 16, '.mp3'),
            (b'OggS' + b'\x00' * 16, '.ogg'),
            (b'RIFF\x00\x00\x00\x00WAVE' + b'\x00' * 16, '.wav'),
        ]
        for data, extension in headers:
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as temp_dir:
                response = io.BytesIO(data)
                response.headers = {'Content-Length': str(len(data))}
                with patch.object(self.module.voice.urllib.request, 'urlopen', return_value=response):
                    path = self.module.voice.download_audio('https://example.com/audio', temp_dir, {})
                self.assertEqual(extension, path.suffix)
                self.assertEqual(data, path.read_bytes())


if __name__ == '__main__':
    unittest.main()
