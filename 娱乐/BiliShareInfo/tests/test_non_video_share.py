import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if 'BiliShareInfo' not in sys.modules:
    sys.modules['BiliShareInfo'] = types.ModuleType('BiliShareInfo')

SPEC = importlib.util.spec_from_file_location('bili_share_info_main', ROOT / 'main.py')
main = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(main)


OPUS_ID = '1265015100211724289'
OPUS_FINAL_URL = f'https://m.bilibili.com/opus/{OPUS_ID}?share_source=QQ'
ARTICLE_FINAL_URL = 'https://www.bilibili.com/read/cv40000000'
DYNAMIC_AUTHOR = '冿冿唻口罗'
DYNAMIC_TEXT = '啊——小英雄你怎么又又被抓了～～\n这副可怜巴巴不知道自己接下来要遭遇些什么的样子真是美味\n夜宵就吃这个了'
DYNAMIC_IMAGE = 'http://i0.hdslb.com/bfs/new_dyn/29eb8a98dda1234fb14aa50cf82d7748370754748.png'
ARTICLE_IMAGE = 'https://i0.hdslb.com/bfs/article/a34bcecbedc09015154709c3c025494b.jpg'

DYNAMIC_DRAW_PAYLOAD = {
    'code': 0,
    'data': {
        'item': {
            'type': 'DYNAMIC_TYPE_DRAW',
            'modules': {
                'module_author': {'name': DYNAMIC_AUTHOR, 'mid': 370754748},
                'module_dynamic': {
                    'major': {
                        'type': 'MAJOR_TYPE_OPUS',
                        'opus': {
                            'title': None,
                            'summary': {'text': DYNAMIC_TEXT},
                            'pics': [{'url': DYNAMIC_IMAGE}],
                        },
                    },
                },
            },
        },
    },
}
DYNAMIC_AV_PAYLOAD = {
    'code': 0,
    'data': {
        'item': {
            'type': 'DYNAMIC_TYPE_AV',
            'modules': {
                'module_author': {'name': '某个UP主'},
                'module_dynamic': {
                    'major': {'archive': {'bvid': 'BV1FoxQ6jECN', 'aid': 123456}},
                },
            },
        },
    },
}
ARTICLE_PAYLOAD = {
    'code': 0,
    'data': {
        'title': '三国杀武将技能评析（张郃）',
        'summary': '山包张郃/国战张郃，<b>料敌机先</b>巧变：你可以弃置一张手牌，跳过一个阶段。',
        'author': {'mid': 21078571, 'name': '这就是秋夜'},
        'origin_image_urls': [ARTICLE_IMAGE],
    },
}

# 正文里塞一个别人的 BV：修复前会被当成这次分享的视频。
BODY_WITH_FOREIGN_BV = '<html><body>相关推荐 BV1mYxi62EqP</body></html>'


class ClassifyUrlTest(unittest.TestCase):
    def test_opus_link(self):
        kind, payload = main.classify_bilibili_share_url(OPUS_FINAL_URL)
        self.assertEqual(kind, 'opus')
        self.assertEqual(payload['opus_id'], OPUS_ID)

    def test_t_bilibili_dynamic_link(self):
        kind, payload = main.classify_bilibili_share_url(
            f'https://t.bilibili.com/{OPUS_ID}?tab=2'
        )
        self.assertEqual(kind, 'opus')
        self.assertEqual(payload['opus_id'], OPUS_ID)

    def test_article_link(self):
        kind, payload = main.classify_bilibili_share_url(ARTICLE_FINAL_URL)
        self.assertEqual(kind, 'article')
        self.assertEqual(payload['article_id'], '40000000')

    def test_mobile_article_link(self):
        kind, payload = main.classify_bilibili_share_url(
            'https://www.bilibili.com/read/mobile?id=123456'
        )
        self.assertEqual(kind, 'article')
        self.assertEqual(payload['article_id'], '123456')

    def test_video_link_stays_video(self):
        kind, ref = main.classify_bilibili_share_url(
            'https://www.bilibili.com/video/BV1FoxQ6jECN?spm_id_from=333'
        )
        self.assertEqual(kind, 'video')
        self.assertEqual(ref, {'bvid': 'BV1FoxQ6jECN'})

    def test_non_bilibili_host(self):
        self.assertIsNone(main.classify_bilibili_share_url('https://example.com/opus/1'))

    def test_extract_urls_keeps_t_bilibili(self):
        url_list = main.extract_urls(f'看这个 https://t.bilibili.com/{OPUS_ID} 哈哈')
        self.assertIn(f'https://t.bilibili.com/{OPUS_ID}', url_list)


class ResolveOpusTest(unittest.TestCase):
    def setUp(self):
        main.gApiCache.clear()
        self.non_video_key_set = set()
        self.preview_map = {}
        self.tokens = [
            main.gNonVideoUrlContext.set(self.non_video_key_set),
            main.gNonVideoPreviewContext.set(self.preview_map),
        ]

    def tearDown(self):
        main.gNonVideoUrlContext.reset(self.tokens[0])
        main.gNonVideoPreviewContext.reset(self.tokens[1])

    def test_draw_dynamic_is_not_video_and_registers_preview(self):
        with mock.patch.object(
            main, 'http_get_text', return_value=(OPUS_FINAL_URL, BODY_WITH_FOREIGN_BV)
        ), mock.patch.object(
            main, 'http_get_json_text', return_value=main.json.dumps(DYNAMIC_DRAW_PAYLOAD)
        ):
            result = main.resolve_video_ref_from_url('https://b23.tv/AIHAqqX')
        self.assertIsNone(result)
        self.assertIn(f'm.bilibili.com/opus/{OPUS_ID}', self.non_video_key_set)
        self.assertIn('b23.tv/AIHAqqX', self.non_video_key_set)
        preview = self.preview_map[f'opus:{OPUS_ID}']
        self.assertEqual(preview['kind'], '动态')
        self.assertEqual(preview['author'], DYNAMIC_AUTHOR)
        self.assertEqual(preview['title'], '啊——小英雄你怎么又又被抓了～～')
        self.assertIn('夜宵就吃这个了', preview['summary'])
        self.assertEqual(preview['image_list'], [DYNAMIC_IMAGE])

    def test_av_dynamic_returns_its_video(self):
        with mock.patch.object(
            main, 'http_get_text', return_value=(OPUS_FINAL_URL, BODY_WITH_FOREIGN_BV)
        ), mock.patch.object(
            main, 'http_get_json_text', return_value=main.json.dumps(DYNAMIC_AV_PAYLOAD)
        ):
            result = main.resolve_video_ref_from_url('https://b23.tv/AIHAqqX')
        self.assertEqual(result, {'bvid': 'BV1FoxQ6jECN'})
        self.assertEqual(self.non_video_key_set, set())
        self.assertEqual(self.preview_map, {})

    def test_article_link_registers_preview_and_does_not_scan_body(self):
        json_mock = mock.Mock(return_value=main.json.dumps(ARTICLE_PAYLOAD))
        with mock.patch.object(
            main, 'http_get_text', return_value=(ARTICLE_FINAL_URL, BODY_WITH_FOREIGN_BV)
        ), mock.patch.object(main, 'http_get_json_text', json_mock):
            result = main.resolve_video_ref_from_url('https://b23.tv/cvShort')
        self.assertIsNone(result)
        self.assertIn('www.bilibili.com/read/cv40000000', self.non_video_key_set)
        self.assertIn('x/article/view?id=40000000', json_mock.call_args[0][0])
        preview = self.preview_map['article:40000000']
        self.assertEqual(preview['kind'], '专栏')
        self.assertEqual(preview['title'], '三国杀武将技能评析（张郃）')
        self.assertEqual(preview['author'], '这就是秋夜')
        self.assertNotIn('<b>', preview['summary'])
        self.assertEqual(preview['image_list'], [ARTICLE_IMAGE])


class PreviewFormatTest(unittest.TestCase):
    def test_split_title_and_summary(self):
        title, summary = main.split_preview_title_and_summary('', DYNAMIC_TEXT)
        self.assertEqual(title, '啊——小英雄你怎么又又被抓了～～')
        self.assertTrue(summary.startswith('这副可怜巴巴'))

    def test_format_dynamic_reply_has_image_title_author_and_summary(self):
        preview = {
            'kind': '动态',
            'title': '今天的晚饭',
            'author': '某个UP主',
            'summary': '夜宵就吃这个了',
            'image_list': [DYNAMIC_IMAGE],
        }
        reply = main.format_non_video_preview_reply(preview)
        self.assertTrue(reply.startswith(f'[OP:image,file={DYNAMIC_IMAGE}]'))
        self.assertIn('这是动态：今天的晚饭', reply)
        self.assertIn('UP主：某个UP主', reply)
        self.assertIn('夜宵就吃这个了', reply)

    def test_format_without_image(self):
        preview = {
            'kind': '专栏',
            'title': '无图专栏',
            'author': '某个UP主',
            'summary': '',
            'image_list': [],
        }
        reply = main.format_non_video_preview_reply(preview)
        self.assertTrue(reply.startswith('这是专栏：无图专栏'))
        self.assertNotIn('[OP:image', reply)


class CardSkipTest(unittest.TestCase):
    CARD = {
        'tag': '哔哩哔哩',
        'fields': {
            'desc': '冿冿唻口罗',
            'jump_url': 'https://b23.tv/AIHAqqX?share_medium=android&share_source=qq',
            'title': '啊——小英雄你怎么又又被抓了～～(º﹃º ) 这副可怜巴巴不…',
        },
    }

    def setUp(self):
        self.non_video_key_set = {'b23.tv/AIHAqqX', f'm.bilibili.com/opus/{OPUS_ID}'}
        self.notice_dict = {}
        self.card_map = {}
        self.preview_map = {}
        self.tokens = [
            main.gNonVideoUrlContext.set(self.non_video_key_set),
            main.gParseNoticeContext.set(self.notice_dict),
            main.gCardParseResultContext.set(self.card_map),
            main.gNonVideoPreviewContext.set(self.preview_map),
        ]

    def tearDown(self):
        main.gNonVideoUrlContext.reset(self.tokens[0])
        main.gParseNoticeContext.reset(self.tokens[1])
        main.gCardParseResultContext.reset(self.tokens[2])
        main.gNonVideoPreviewContext.reset(self.tokens[3])

    def test_non_video_card_skips_title_search_and_notice(self):
        video_ref_list = []
        with mock.patch.object(main, 'extract_live_refs_from_card', return_value=[]), \
                mock.patch.object(main, 'find_video_refs', return_value=[]), \
                mock.patch.object(main, 'search_video_by_card_comparison') as search_mock:
            main.add_video_refs_from_card(
                self.CARD,
                video_ref_list,
                set(),
                {},
                'JSON卡片',
            )
        search_mock.assert_not_called()
        self.assertEqual(video_ref_list, [])
        self.assertEqual(self.notice_dict, {})

    def test_video_card_still_searches_title_when_no_non_video_mark(self):
        self.non_video_key_set.clear()
        with mock.patch.object(main, 'extract_live_refs_from_card', return_value=[]), \
                mock.patch.object(main, 'find_video_refs', return_value=[]), \
                mock.patch.object(main, 'search_video_by_bangumi_pattern', return_value=None), \
                mock.patch.object(
                    main, 'search_video_by_card_comparison', return_value={'bvid': 'BV1FoxQ6jECN'}
                ) as search_mock:
            main.add_video_refs_from_card(
                self.CARD,
                [],
                set(),
                {},
                'JSON卡片',
            )
        search_mock.assert_called_once()
        self.assertEqual(self.notice_dict, {})


if __name__ == '__main__':
    unittest.main()
