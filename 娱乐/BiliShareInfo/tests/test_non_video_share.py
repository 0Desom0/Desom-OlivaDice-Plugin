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
DYNAMIC_DRAW_PAYLOAD = {
    'code': 0,
    'data': {'item': {'type': 'DYNAMIC_TYPE_DRAW', 'modules': {}}},
}
DYNAMIC_AV_PAYLOAD = {
    'code': 0,
    'data': {
        'item': {
            'type': 'DYNAMIC_TYPE_AV',
            'modules': {
                'module_dynamic': {
                    'major': {'archive': {'bvid': 'BV1FoxQ6jECN', 'aid': 123456}},
                },
            },
        },
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
        self.assertEqual(main.classify_bilibili_share_url(ARTICLE_FINAL_URL)[0], 'article')

    def test_mobile_article_link(self):
        kind, _ = main.classify_bilibili_share_url(
            'https://www.bilibili.com/read/mobile?id=123456'
        )
        self.assertEqual(kind, 'article')

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
        self.token = main.gNonVideoUrlContext.set(self.non_video_key_set)

    def tearDown(self):
        main.gNonVideoUrlContext.reset(self.token)

    def test_draw_dynamic_is_not_video_and_body_is_not_scanned(self):
        with mock.patch.object(
            main, 'http_get_text', return_value=(OPUS_FINAL_URL, BODY_WITH_FOREIGN_BV)
        ), mock.patch.object(
            main, 'http_get_json_text', return_value=main.json.dumps(DYNAMIC_DRAW_PAYLOAD)
        ):
            result = main.resolve_video_ref_from_url('https://b23.tv/AIHAqqX')
        self.assertIsNone(result)
        self.assertIn(f'm.bilibili.com/opus/{OPUS_ID}', self.non_video_key_set)
        self.assertIn('b23.tv/AIHAqqX', self.non_video_key_set)

    def test_av_dynamic_returns_its_video(self):
        with mock.patch.object(
            main, 'http_get_text', return_value=(OPUS_FINAL_URL, BODY_WITH_FOREIGN_BV)
        ), mock.patch.object(
            main, 'http_get_json_text', return_value=main.json.dumps(DYNAMIC_AV_PAYLOAD)
        ):
            result = main.resolve_video_ref_from_url('https://b23.tv/AIHAqqX')
        self.assertEqual(result, {'bvid': 'BV1FoxQ6jECN'})
        self.assertEqual(self.non_video_key_set, set())

    def test_article_link_does_not_scan_body(self):
        with mock.patch.object(
            main, 'http_get_text', return_value=(ARTICLE_FINAL_URL, BODY_WITH_FOREIGN_BV)
        ):
            result = main.resolve_video_ref_from_url('https://b23.tv/cvShort')
        self.assertIsNone(result)
        self.assertIn('www.bilibili.com/read/cv40000000', self.non_video_key_set)


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
        self.tokens = [
            main.gNonVideoUrlContext.set(self.non_video_key_set),
            main.gParseNoticeContext.set(self.notice_dict),
            main.gCardParseResultContext.set(self.card_map),
        ]

    def tearDown(self):
        main.gNonVideoUrlContext.reset(self.tokens[0])
        main.gParseNoticeContext.reset(self.tokens[1])
        main.gCardParseResultContext.reset(self.tokens[2])

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
