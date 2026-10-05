import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if 'BiliShareInfo' not in sys.modules:
    sys.modules['BiliShareInfo'] = types.ModuleType('BiliShareInfo')

SPEC = importlib.util.spec_from_file_location('bili_share_info_main', ROOT / 'main.py')
main = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(main)

LIVE_CARD_MESSAGE = (
    '[OP:json,data={"ark_name":"图文H5","ark_type":"tuwen","fields":{'
    '"desc":"UP主：Oaildlo-房间号：177409","jump_url":"https://b23.tv/dBHsQQF",'
    '"tag":"哔哩哔哩","title":"冲刺周年庆"},"prompt":"[分享]冲刺周年庆"}]'
)
VIDEO_CARD_MESSAGE = (
    '[OP:json,data={"ark_name":"图文H5","ark_type":"tuwen","fields":{'
    '"desc":"拉瑞安工作室宣布《博德之门3》中国区价格降低",'
    '"jump_url":"https://b23.tv/ZkhJF2G","tag":"哔哩哔哩",'
    '"title":"拉瑞安工作室宣布《博德之门3》中国区价格降低"},'
    '"prompt":"【分享】拉瑞安工作室宣布《博德之门3》中国区价格降低"}]'
)


class TuwenCardTest(unittest.TestCase):
    def test_strip_keeps_share_brackets_inside_json(self):
        stripped = main.strip_non_parse_segments(LIVE_CARD_MESSAGE)
        self.assertEqual(stripped, LIVE_CARD_MESSAGE)
        self.assertIn('房间号：177409', stripped)
        self.assertIn('[分享]冲刺周年庆', stripped)

    def test_extract_live_json_card(self):
        card = main.extract_json_card(main.strip_non_parse_segments(LIVE_CARD_MESSAGE))
        self.assertIsInstance(card, dict)
        self.assertEqual(card.get('ark_type'), 'tuwen')
        self.assertEqual(card.get('fields', {}).get('jump_url'), 'https://b23.tv/dBHsQQF')
        self.assertEqual(main.get_title_hint(card), '冲刺周年庆')

    def test_extract_video_json_card(self):
        card = main.extract_json_card(main.strip_non_parse_segments(VIDEO_CARD_MESSAGE))
        self.assertIsInstance(card, dict)
        self.assertEqual(card.get('ark_type'), 'tuwen')
        self.assertEqual(card.get('fields', {}).get('jump_url'), 'https://b23.tv/ZkhJF2G')

    def test_room_hint_from_live_card(self):
        card = main.extract_json_card(LIVE_CARD_MESSAGE)
        self.assertEqual(main.extract_live_refs_from_card(card), [{'live_id': '177409'}])
        self.assertEqual(main.extract_live_refs_from_text('房间号：177409'), [])

    def test_live_url_paths(self):
        self.assertEqual(
            main.extract_live_ref_from_url('https://live.bilibili.com/h5/177409?broadcast_type=0'),
            {'live_id': '177409'},
        )
        self.assertEqual(
            main.extract_live_ref_from_url('https://live.bilibili.com/177409'),
            {'live_id': '177409'},
        )
        self.assertEqual(
            main.extract_live_ref_from_url('https://live.bilibili.com/blanc/177409'),
            {'live_id': '177409'},
        )

    def test_bangumi_pattern_requires_episode(self):
        self.assertIsNone(
            main.search_video_by_bangumi_pattern(
                '拉瑞安工作室宣布《博德之门3》中国区价格降低',
            )
        )

    def test_filter_enabled_media_refs(self):
        refs = [{'live_id': '177409'}, {'bvid': 'BV1mYHa6xEAj'}]
        self.assertEqual(
            main.filter_enabled_media_refs(refs, video_enable=True, live_enable=True),
            refs,
        )
        self.assertEqual(
            main.filter_enabled_media_refs(refs, video_enable=True, live_enable=False),
            [{'bvid': 'BV1mYHa6xEAj'}],
        )
        self.assertEqual(
            main.filter_enabled_media_refs(refs, video_enable=False, live_enable=True),
            [{'live_id': '177409'}],
        )

    def test_message_extracts_live_and_video_with_mocked_short_links(self):
        original_http_get_text = main.http_get_text

        def fake_http_get_text(url, allow_response_body=False):
            if 'dBHsQQF' in url:
                return 'https://live.bilibili.com/177409?broadcast_type=0', ''
            if 'ZkhJF2G' in url:
                return 'https://www.bilibili.com/video/BV1mYHa6xEAj/?p=1', ''
            return url, ''

        main.http_get_text = fake_http_get_text
        try:
            live_refs = main.extract_video_refs_from_message(
                main.strip_non_parse_segments(LIVE_CARD_MESSAGE),
                allow_title_search=False,
            )
            self.assertEqual(live_refs, [{'live_id': '177409'}])

            video_refs = main.extract_video_refs_from_message(
                main.strip_non_parse_segments(VIDEO_CARD_MESSAGE),
                allow_title_search=False,
            )
            self.assertEqual(video_refs, [{'bvid': 'BV1mYHa6xEAj'}])
        finally:
            main.http_get_text = original_http_get_text

    def test_same_message_dedupes_duplicate_refs(self):
        message = (
            'https://www.bilibili.com/video/BV178Y56REwN/ '
            'https://www.bilibili.com/video/BV178Y56REwN/'
        )
        refs = main.extract_video_refs_from_message(message, allow_title_search=False)
        self.assertEqual(refs, [{'bvid': 'BV178Y56REwN'}])

    def test_image_segments_still_stripped(self):
        message = '[OP:image,file=BV1234567890_thumb.png]看看这个'
        stripped = main.strip_non_parse_segments(message)
        self.assertNotIn('BV1234567890', stripped)
        self.assertIn('看看这个', stripped)


if __name__ == '__main__':
    unittest.main()
