import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if 'BiliShareInfo' not in sys.modules:
    sys.modules['BiliShareInfo'] = types.ModuleType('BiliShareInfo')

SPEC = importlib.util.spec_from_file_location('bili_share_info_main_cardmatch', ROOT / 'main.py')
main = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(main)


def build_candidate(bvid, title, author):
    return {
        'bvid': bvid,
        'aid': 1,
        'title': title,
        'author': author,
        'play': 100,
        'video_review': 1,
        'like': 1,
        '_search_rank': 1,
        '_search_source': 'title_api_2',
    }


class UserSearchFallbackTest(unittest.TestCase):
    """wbi 的 search/type 对 bili_user 常常 code=0 但结果为空。

    2026-10-26 的错视频事故里，预览图 OCR 明明读到了 UP 主「无火的余镜」，
    却因为只认这个接口而查不到 mid，最后退回同名盲选回了别人的《艹》。
    """

    def setUp(self):
        self._origin_fetch = main.http_get_json_text
        self._origin_extract = main.extract_bili_user_search_results
        self.requested_url_list = []

    def tearDown(self):
        main.http_get_json_text = self._origin_fetch
        main.extract_bili_user_search_results = self._origin_extract

    def test_falls_back_to_next_api_when_first_is_empty(self):
        def fake_fetch(url, referer='https://www.bilibili.com/', include_origin=True, user_agent=None):
            self.requested_url_list.append(url)
            if 'search/all/v2' in url:
                return '{"code": 0, "data": {"result": [{"type": "bili_user"}]}}'
            return '{"code": 0, "data": {"result": []}}'

        main.http_get_json_text = fake_fetch
        main.extract_bili_user_search_results = lambda data: (
            [{'mid': '3461564246001918', 'uname': '无火的余镜'}] if data.get('data', {}).get('result') else []
        )

        candidates = main.fetch_bili_user_search_candidates(
            '无火的余镜',
            {'search_type': 'bili_user', 'keyword': '无火的余镜', 'page': 1, 'page_size': 20},
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['mid'], '3461564246001918')
        self.assertGreaterEqual(len(self.requested_url_list), 2)

    def test_returns_empty_when_every_api_is_empty(self):
        main.http_get_json_text = lambda *args, **kwargs: '{"code": 0, "data": {"result": []}}'
        main.extract_bili_user_search_results = lambda data: []

        candidates = main.fetch_bili_user_search_candidates(
            '无火的余镜',
            {'search_type': 'bili_user', 'keyword': '无火的余镜', 'page': 1, 'page_size': 20},
        )

        self.assertEqual(candidates, [])


class ShortTitleGuardTest(unittest.TestCase):
    """短标题（「艹」这种一个字）同名视频极多，不能靠标题猜。"""

    def test_ambiguous_short_title_without_metadata_gives_up(self):
        candidate_list = [
            build_candidate('BV1Hi4y1s7nD', '艹', '蜜雪冰城曼波站'),
            build_candidate('BV1NaYteaEWr', '艹', '无火的余镜'),
        ]
        self.assertIsNone(
            main.choose_card_search_result('艹', {}, candidate_list)
        )

    def test_short_title_conflicting_metadata_gives_up(self):
        candidate_list = [build_candidate('BV1Hi4y1s7nD', '艹', '蜜雪冰城曼波站')]
        preview_metadata = {'owner': '无火的余镜', 'view': 88000, 'danmaku': 26, 'like': 4086}

        self.assertIsNone(
            main.choose_card_search_result('艹', preview_metadata, candidate_list)
        )

    def test_long_title_still_matches_single_candidate(self):
        candidate_list = [build_candidate('BV1RgnH6qEwG', '⚡️人类的爱ai⚡️大肥鱼小课堂 DSH', '卡布奇诺ultra')]

        selected = main.choose_card_search_result(
            '⚡️人类的爱ai⚡️大肥鱼小课堂 DSH',
            {},
            candidate_list,
        )

        self.assertEqual(selected, {'bvid': 'BV1RgnH6qEwG'})


if __name__ == '__main__':
    unittest.main()
