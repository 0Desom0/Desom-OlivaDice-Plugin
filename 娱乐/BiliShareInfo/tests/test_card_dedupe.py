import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if 'BiliShareInfo' not in sys.modules:
    sys.modules['BiliShareInfo'] = types.ModuleType('BiliShareInfo')

SPEC = importlib.util.spec_from_file_location('bili_share_info_main_dedupe', ROOT / 'main.py')
main = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(main)


def build_miniapp_card(title, preview='https://qq.ugcimg.cn/v1/abc/e9vf2tsqr6j29hl2kodb3vahlc'):
    return {
        'ark_name': '小程序',
        'ark_type': 'miniapp',
        'fields': {
            'preview': preview,
            'source': '哔哩哔哩',
            'title': title,
        },
        'prompt': f'[QQ小程序]{title}',
    }


class CardDedupeTest(unittest.TestCase):
    """同一张分享卡片会同时以「消息内 JSON 卡片」和「QQ 官方 ARK 卡片」出现。

    两条来源若各自反查一次，B 站接口抖动时会出现「一次成功、一次失败」，
    于是先回正确的视频、再补一条解析失败。这里锁住「只查一次」的行为。
    """

    def setUp(self):
        self._origin = {
            'search': main.search_video_by_card_comparison,
            'live': main.extract_live_refs_from_card,
            'find': main.find_video_refs,
            'bangumi': main.search_video_by_bangumi_pattern,
            'reply': main.reply_message,
        }
        main.extract_live_refs_from_card = lambda *args, **kwargs: []
        main.find_video_refs = lambda *args, **kwargs: []
        main.search_video_by_bangumi_pattern = lambda title_hint: None
        self.search_call_count = 0
        self.notice_token = main.gParseNoticeContext.set({})
        self.card_token = main.gCardParseResultContext.set({})

    def tearDown(self):
        main.gParseNoticeContext.reset(self.notice_token)
        main.gCardParseResultContext.reset(self.card_token)
        main.search_video_by_card_comparison = self._origin['search']
        main.extract_live_refs_from_card = self._origin['live']
        main.find_video_refs = self._origin['find']
        main.search_video_by_bangumi_pattern = self._origin['bangumi']
        main.reply_message = self._origin['reply']

    def stub_search(self, result):
        def fake_search(card_data, title_hint, preview_ocr_enable=True, retry_count=0):
            self.search_call_count += 1
            return result

        main.search_video_by_card_comparison = fake_search

    def parse_card(self, card):
        ref_list = []
        main.add_video_refs_from_card(
            card,
            ref_list,
            set(),
            {},
            'QQ官机ARK卡片#1',
        )
        return ref_list

    def test_same_card_only_searched_once(self):
        self.stub_search({'bvid': 'BV1b4nU6rEhh'})
        card = build_miniapp_card('零云之声RIDEZERO复活了')

        first_ref_list = self.parse_card(card)
        second_ref_list = self.parse_card(dict(card))

        self.assertEqual(self.search_call_count, 1)
        self.assertEqual(first_ref_list, [{'bvid': 'BV1b4nU6rEhh'}])
        self.assertEqual(second_ref_list, [{'bvid': 'BV1b4nU6rEhh'}])

    def test_failed_card_retries_once_for_second_source_only(self):
        self.stub_search(None)
        card = build_miniapp_card('零云之声RIDEZERO复活了')

        self.parse_card(card)
        self.parse_card(dict(card))
        self.parse_card(dict(card))

        # 两个来源各给一次机会，第三条来源不再重复请求
        self.assertEqual(self.search_call_count, 2)
        notice_dict = main.gParseNoticeContext.get()
        self.assertEqual(len(notice_dict), 1)

    def test_first_source_failure_is_revoked_by_second_source_success(self):
        """复现 2026-10-26 20:02 的事故：先失败后成功，不能既发视频又报失败。"""
        reply_list = []
        main.reply_message = lambda plugin_event, message: reply_list.append(message)
        results = [None, {'bvid': 'BV1b4nU6rEhh'}]

        def fake_search(card_data, title_hint, preview_ocr_enable=True, retry_count=0):
            self.search_call_count += 1
            return results[min(self.search_call_count, len(results)) - 1]

        main.search_video_by_card_comparison = fake_search
        card = build_miniapp_card('零云之声RIDEZERO复活了')

        first_ref_list = self.parse_card(card)
        second_ref_list = self.parse_card(dict(card))
        main.send_parse_failure_notice(object())

        self.assertEqual(first_ref_list, [])
        self.assertEqual(second_ref_list, [{'bvid': 'BV1b4nU6rEhh'}])
        self.assertEqual(reply_list, [])
        self.assertEqual(main.gParseNoticeContext.get(), {})

    def test_no_failure_notice_when_card_resolved(self):
        self.stub_search({'bvid': 'BV1b4nU6rEhh'})
        card = build_miniapp_card('零云之声RIDEZERO复活了')

        self.parse_card(card)

        self.assertEqual(main.gParseNoticeContext.get(), {})

    def test_successful_parse_discards_earlier_notice(self):
        card_key = main.build_card_parse_key(build_miniapp_card('零云之声RIDEZERO复活了'))
        main.add_parse_notice('B站解析失败：假装找不到', main.build_card_notice_key(card_key))
        self.assertEqual(len(main.gParseNoticeContext.get()), 1)

        main.store_card_parse_result(card_key, [{'bvid': 'BV1b4nU6rEhh'}])

        self.assertEqual(main.gParseNoticeContext.get(), {})

    def test_notice_keys_dedupe_same_reason(self):
        main.add_parse_notice('同一条提示', 'k1')
        main.add_parse_notice('同一条提示', 'k1')
        main.add_parse_notice('另一条提示', 'k2')

        self.assertEqual(
            list(main.gParseNoticeContext.get().values()),
            ['同一条提示', '另一条提示'],
        )

    def test_send_skips_when_all_notices_discarded(self):
        reply_list = []
        main.reply_message = lambda plugin_event, message: reply_list.append(message)
        card_key = main.build_card_parse_key(build_miniapp_card('零云之声RIDEZERO复活了'))
        main.add_parse_notice('B站解析失败：假装找不到', main.build_card_notice_key(card_key))
        main.store_card_parse_result(card_key, [{'bvid': 'BV1b4nU6rEhh'}])

        main.send_parse_failure_notice(object())

        self.assertEqual(reply_list, [])


class CardSearchRetryTest(unittest.TestCase):
    def test_retries_once_after_empty_result(self):
        if not hasattr(main, 'CARD_SEARCH_RETRY_LIMIT'):
            self.skipTest('旧版本没有重试常量')
        self.assertEqual(main.CARD_SEARCH_RETRY_LIMIT, 1)
        self.assertLessEqual(main.CARD_SEARCH_RETRY_DELAY_SECONDS, 5)


if __name__ == '__main__':
    unittest.main()
