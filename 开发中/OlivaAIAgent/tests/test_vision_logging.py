# -*- encoding: utf-8 -*-

import copy
import json
import os
import tempfile
import unittest
from unittest import mock

import OlivaAIAgent


class FakeProc:
    def __init__(self):
        self.records = []

    def log(self, level, message, segments=None):
        self.records.append((level, message, segments))


class FakeResponse:
    status_code = 200
    text = ''

    def json(self):
        content = json.dumps(
            {'content': '一只白色狐狸站在雪地里', 'intent': '展示图片', 'type': '插画'},
            ensure_ascii=False,
        )
        return {'choices': [{'message': {'content': content}}]}


class FakeErrorResponse:
    status_code = 400
    text = '{"error":"unsupported image format"}'


class FakeImageResponse:
    status_code = 200

    def __init__(self, content, content_type):
        self.content = content
        self.headers = {'Content-Type': content_type}

    def raise_for_status(self):
        return None


class FakeBotInfo:
    hash = 'bot-hash'


class FakeData:
    group_id = 'group-1'
    user_id = 'user-1'


class FakeEvent:
    platform = {'platform': 'qqGuild', 'sdk': 'qqGuildv2_link', 'model': 'public'}
    data = FakeData()
    bot_info = FakeBotInfo()


class VisionLoggingTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = copy.deepcopy(OlivaAIAgent.conf.gConf)
        self.old_proc = OlivaAIAgent.conf.gProc
        self.proc = FakeProc()
        OlivaAIAgent.conf.gProc = self.proc
        OlivaAIAgent.conf.gConf = {
            'backend': 'openai',
            'openai': {'vision': False, 'api_url': 'https://api.deepseek.com/v1/chat/completions'},
            'vision': {
                'enable': True,
                'use_main': 'auto',
                'api_url': 'https://api.moonshot.cn/v1/chat/completions',
                'api_key': 'secret-key',
                'model': 'kimi-k2.6',
                'mode': 'base64',
            },
            'debug_log': True,
        }

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.conf.gProc = self.old_proc

    def test_config_routes_to_independent_vision(self):
        status = OlivaAIAgent.vision.getVisionStatus()
        self.assertTrue(status['enabled'])
        self.assertTrue(status['ready'])
        self.assertEqual('independent', status['route'])
        self.assertEqual('kimi-k2.6', status['model'])
        self.assertEqual('base64', status['mode'])

    def test_ocr_success_is_logged_without_image_data(self):
        vc = OlivaAIAgent.vision._visionConf()
        with mock.patch.object(OlivaAIAgent.vision.requests, 'post', return_value=FakeResponse()):
            result = OlivaAIAgent.vision._callOcr(
                vc,
                'data:image/jpeg;base64,VERY_LONG_IMAGE_DATA',
                trace_id='trace-1',
            )
        self.assertEqual('一只白色狐狸站在雪地里', result['content'])
        logs = '\n'.join(record[1] for record in self.proc.records)
        self.assertIn('图片识别请求', logs)
        self.assertIn('图片识别成功', logs)
        self.assertNotIn('VERY_LONG_IMAGE_DATA', logs)
        self.assertNotIn('secret-key', logs)

    def test_ocr_http_error_is_logged(self):
        vc = OlivaAIAgent.vision._visionConf()
        with mock.patch.object(OlivaAIAgent.vision.requests, 'post', return_value=FakeErrorResponse()):
            result = OlivaAIAgent.vision._callOcr(
                vc,
                'data:image/jpeg;base64,ERROR_IMAGE_DATA',
                trace_id='trace-http-error',
            )
        self.assertIsNone(result)
        logs = '\n'.join(record[1] for record in self.proc.records)
        self.assertIn('图片识别接口错误', logs)
        self.assertIn('状态码=400', logs)
        self.assertIn('unsupported image format', logs)
        self.assertNotIn('ERROR_IMAGE_DATA', logs)
        self.assertNotIn('secret-key', logs)

    def test_private_agent_uses_vision_summary_not_main_image(self):
        ctx = {
            'Proc': self.proc,
            'func_type': 'private_message',
            'group_id': None,
            'user_id': 'user-1',
        }
        parsed = {
            'trace_id': 'trace-2',
            'raw': '[CQ:image,file=test.jpg,url=https://example.invalid/test.jpg]',
            'images': ['https://example.invalid/test.jpg'],
        }
        with mock.patch.object(
            OlivaAIAgent.vision,
            'translateIncoming',
            return_value='[图片:一只白色狐狸]',
        ):
            text, images = OlivaAIAgent.msgReply._prepareAgentVision(
                FakeEvent(),
                ctx,
                '这是什么？[[OLIVA_IMAGE_0]]你看到了吗？',
                parsed,
            )
        self.assertEqual('这是什么？[图片:一只白色狐狸]你看到了吗？', text)
        self.assertEqual([], images)

    def test_failed_summary_does_not_retry_same_image(self):
        failed = '[图片:未识别成功]'
        with mock.patch.object(OlivaAIAgent.vision, 'describeImages') as describe:
            facts = OlivaAIAgent.vision.ensureImageFacts(
                [failed],
                ['https://example.invalid/test.jpg'],
                'group-1',
                'bot-hash',
                trace_id='trace-no-repeat',
            )
        self.assertEqual([failed], facts)
        describe.assert_not_called()
        logs = '\n'.join(record[1] for record in self.proc.records)
        self.assertIn('已跳过重复图片识别', logs)
        self.assertIn('原因=本轮已识别失败', logs)

    def test_missing_summary_uses_parsed_image_once(self):
        expected = ['[图片:一只白色狐狸]']
        with mock.patch.object(OlivaAIAgent.vision, 'describeImages', return_value=expected) as describe:
            facts = OlivaAIAgent.vision.ensureImageFacts(
                [],
                ['https://example.invalid/test.jpg'],
                'group-1',
                'bot-hash',
                trace_id='trace-fallback',
            )
        self.assertEqual(expected, facts)
        describe.assert_called_once_with(
            ['https://example.invalid/test.jpg'],
            'group-1',
            'bot-hash',
            trace_id='trace-fallback',
        )

    def test_image_format_contains_only_result(self):
        result = OlivaAIAgent.vision.imgcode_format({
            'content': '一只白色狐狸站在雪地里',
            'intent': '展示图片',
            'type': '插画',
        })
        self.assertEqual('[图片:一只白色狐狸站在雪地里]', result)

    def test_old_image_fact_format_remains_readable(self):
        message = '[图片：一只橘猫；意图：卖萌；类型：照片]'
        self.assertEqual(['一只橘猫'], OlivaAIAgent.vision.extractVisionFacts(message))

    def test_assassin_image_score_matches_content_and_rejects_weak_overlap(self):
        cache = {
            'fox.gif': {'content': '白色小狐狸捂脸哭泣', 'intent': '无奈卖萌', 'type': '表情包'},
            'cat.png': {'content': '橘猫趴在桌上睡觉', 'intent': '困倦', 'type': '照片'},
        }
        self.assertEqual('fox.gif', OlivaAIAgent.vision.resolveImageRef('狐狸捂脸哭泣', cache))
        self.assertIsNone(OlivaAIAgent.vision.resolveImageRef('火箭升空', cache))
        logs = '\n'.join(record[1] for record in self.proc.records)
        self.assertIn('发送图片匹配成功', logs)
        self.assertIn('发送图片未匹配', logs)

    def test_assassin_image_score_repairs_repeated_extension(self):
        cache = {'reaction.gif': {'content': '无奈', 'intent': '吐槽', 'type': '表情包'}}
        self.assertEqual('reaction.gif', OlivaAIAgent.vision.resolveImageRef('reaction.gif.gif', cache))

    def test_translate_outgoing_creates_real_cq_image_segment(self):
        cache = {'fox.gif': {'content': '狐狸捂脸', 'intent': '无奈', 'type': '表情包'}}
        with tempfile.TemporaryDirectory() as directory:
            image_path = os.path.join(directory, 'fox.gif')
            with open(image_path, 'wb') as image_file:
                image_file.write(b'GIF89a')
            with mock.patch.object(OlivaAIAgent.vision, 'imageCacheMap', return_value=cache), \
                    mock.patch.object(OlivaAIAgent.vision, 'imgDir', return_value=directory):
                result = OlivaAIAgent.vision.translateOutgoing(
                    ['[发图片:狐狸捂脸]'],
                    'bot-hash',
                    trace_id='trace-send-image',
                )
        self.assertEqual(1, len(result))
        self.assertTrue(result[0].startswith('[CQ:image,file=file:///'))
        self.assertTrue(result[0].endswith('fox.gif]'))
        logs = '\n'.join(record[1] for record in self.proc.records)
        self.assertIn('已生成图片消息段', logs)
        self.assertIn('编号=trace-send-image', logs)

    def test_download_uses_content_hash_and_real_gif_extension(self):
        content = b'GIF89a' + b'\x00' * 32
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(OlivaAIAgent.vision, 'imgDir', return_value=directory), \
                mock.patch.object(
                    OlivaAIAgent.vision.requests,
                    'get',
                    return_value=FakeImageResponse(content, 'application/octet-stream'),
                ):
            data_url, path = OlivaAIAgent.vision._downloadBase64(
                'https://multimedia.nt.qq.com.cn/download?appid=1&fileid=gif&rkey=temporary',
                'download',
            )
            self.assertTrue(data_url.startswith('data:image/gif;base64,'))
            self.assertRegex(os.path.basename(path), r'^img_[0-9a-f]{20}\.gif$')
            with open(path, 'rb') as image_file:
                self.assertEqual(content, image_file.read())

    def test_different_download_images_do_not_overwrite_each_other(self):
        first = FakeImageResponse(b'\xff\xd8\xffFIRST_IMAGE', 'image/jpeg')
        second = FakeImageResponse(b'\xff\xd8\xffSECOND_IMAGE', 'image/jpeg')
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(OlivaAIAgent.vision, 'imgDir', return_value=directory), \
                mock.patch.object(OlivaAIAgent.vision.requests, 'get', side_effect=[first, second]):
            _, first_path = OlivaAIAgent.vision._downloadBase64(
                'https://multimedia.nt.qq.com.cn/download?appid=1&fileid=first',
                'download',
            )
            _, second_path = OlivaAIAgent.vision._downloadBase64(
                'https://multimedia.nt.qq.com.cn/download?appid=1&fileid=second',
                'download',
            )
        self.assertNotEqual(first_path, second_path)
        self.assertNotEqual(os.path.basename(first_path), os.path.basename(second_path))

    def test_legacy_url_memory_migrates_without_repeating_ocr(self):
        image_url = (
            'https://multimedia.nt.qq.com.cn/download?appid=1&fileid=same-image&rkey=temporary'
        )
        memory = {
            '全局': {
                '图片缓存': {
                    image_url: {'content': '旧记录中的白色狐狸', 'intent': '卖萌', 'type': '表情包'},
                },
            },
        }
        content = b'GIF89a' + b'\x01' * 32
        OlivaAIAgent.vision.cleanupImageCache()
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(OlivaAIAgent.vision, 'imgDir', return_value=directory), \
                mock.patch.object(OlivaAIAgent.knowledge, 'getMem', return_value=memory), \
                mock.patch.object(OlivaAIAgent.knowledge, 'saveMem') as save_memory, \
                mock.patch.object(
                    OlivaAIAgent.vision.requests,
                    'get',
                    return_value=FakeImageResponse(content, 'image/gif'),
                ) as download, \
                mock.patch.object(OlivaAIAgent.vision, '_callOcr') as call_ocr:
            fact = OlivaAIAgent.vision._cacheData(
                'bot-hash',
                'group-1',
                image_url,
                image_url,
                '[图片]',
                '表情包',
                allow_network=True,
            )
            keys = list(memory['全局']['图片缓存'])
            self.assertEqual('[图片:旧记录中的白色狐狸]', fact)
            self.assertEqual(1, len(keys))
            self.assertRegex(keys[0], r'^img_[0-9a-f]{20}\.gif$')
            self.assertTrue(os.path.isfile(os.path.join(directory, keys[0])))
            self.assertIn('_source_ids', memory['全局']['图片缓存'][keys[0]])
            save_memory.assert_called_once_with('bot-hash')
            download.assert_called_once()
            call_ocr.assert_not_called()

            # 模拟插件重启：运行时群队列消失，仍可只靠落盘 memory 找图并生成图片消息段。
            OlivaAIAgent.vision.cleanupImageCache()
            cache_map = OlivaAIAgent.vision.imageCacheMap('bot-hash')
            self.assertIn(keys[0], cache_map)
            outgoing = OlivaAIAgent.vision.translateOutgoing(['[发图片:白色狐狸]'], 'bot-hash')
            self.assertEqual(1, len(outgoing))
            self.assertIn(keys[0], outgoing[0])

            # 再次收到同一来源时直接命中，不再下载，也不再识图。
            download.reset_mock()
            OlivaAIAgent.vision._cacheData(
                'bot-hash',
                'group-1',
                image_url.replace('rkey=temporary', 'rkey=renewed'),
                image_url.replace('rkey=temporary', 'rkey=renewed'),
                '[图片]',
                '表情包',
                allow_network=True,
            )
            download.assert_not_called()
            call_ocr.assert_not_called()

    def test_sync_ocr_false_defers_group_vision_to_worker(self):
        parsed = {
            'trace_id': 'trace-3',
            'raw': '[CQ:image,file=test.jpg,url=https://example.invalid/test.jpg]',
            'images': ['https://example.invalid/test.jpg'],
            'text': '',
        }
        thread = mock.Mock()
        with mock.patch.object(OlivaAIAgent.ambient.threading, 'Thread', return_value=thread) as thread_factory:
            OlivaAIAgent.ambient.process(FakeEvent(), self.proc, parsed, 'bot-1', force=True, tools=True)
        thread_factory.assert_called_once()
        self.assertEqual('OlivaAIAgent-Vision', thread_factory.call_args.kwargs['name'])
        thread.start.assert_called_once()

    def test_trace_log_redacts_sensitive_fields(self):
        OlivaAIAgent.conf.traceLog(
            self.proc,
            'test.stage',
            'trace-4',
            api_key='top-secret',
            image='data:image/png;base64,IMAGE_SECRET',
        )
        message = self.proc.records[-1][1]
        self.assertIn('api_key=<已隐藏>', message)
        self.assertIn('<图片数据:', message)
        self.assertNotIn('top-secret', message)
        self.assertNotIn('IMAGE_SECRET', message)


if __name__ == '__main__':
    unittest.main()
