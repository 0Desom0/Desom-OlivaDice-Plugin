import importlib.util
import io
import json
import sys
import time
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if 'BiliShareInfo' not in sys.modules:
    sys.modules['BiliShareInfo'] = types.ModuleType('BiliShareInfo')

SPEC = importlib.util.spec_from_file_location('bili_share_info_buvid', ROOT / 'main.py')
main = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(main)

main.HTTP_MIN_REQUEST_INTERVAL_SECONDS = 0
main.HTTP_RETRY_BASE_DELAY_SECONDS = 0


class FakeResponse(io.BytesIO):
    def __init__(self, payload, url):
        super().__init__(json.dumps(payload).encode('utf-8'))
        self._url = url

    def geturl(self):
        return self._url

    def getcode(self):
        return 200


class BuvidCookieTest(unittest.TestCase):
    def setUp(self):
        self.real_urlopen = urllib.request.urlopen
        self.cookie_seen_in_request = []
        self.spi_calls = 0
        self.request_calls = 0
        self.buvid_counter = 0
        main.gBuvidCookie = ''
        main.gBuvidCookieTime = 0.0
        main.gApiCache.clear()
        main.gExtraCookieMtime = -1.0
        main.gExtraCookieText = ''
        main.DATA_ROOT = str(ROOT / 'tests' / '_no_cookie_file_here')

    def tearDown(self):
        urllib.request.urlopen = self.real_urlopen
        main.urllib.request.urlopen = self.real_urlopen

    def install_fake_urlopen(self, fail_first_view=0):
        def fake_urlopen(request, *args, **kwargs):
            url = getattr(request, 'full_url', str(request))
            cookie = (getattr(request, 'headers', {}) or {}).get('Cookie', '')
            if 'finger/spi' in url:
                self.spi_calls += 1
                self.assertFalse(cookie, 'spi 请求不应携带 Cookie，否则会递归')
                self.buvid_counter += 1
                return FakeResponse(
                    {
                        'code': 0,
                        'data': {
                            'b_3': f'B3-{self.buvid_counter}-infoc',
                            'b_4': f'B4-{self.buvid_counter}',
                        },
                    },
                    url,
                )
            self.request_calls += 1
            self.cookie_seen_in_request.append(cookie)
            if not cookie or self.request_calls <= fail_first_view:
                raise urllib.error.HTTPError(url, 412, 'Precondition Failed', {}, None)
            return FakeResponse(
                {'code': 0, 'data': {'bvid': 'BV1xx411c7mD', 'title': '测试视频'}},
                url,
            )

        urllib.request.urlopen = fake_urlopen
        main.urllib.request.urlopen = fake_urlopen

    def test_headers_carry_buvid_cookie(self):
        self.install_fake_urlopen()
        headers = main.get_http_headers()
        self.assertIn('buvid3=B3-1-infoc', headers.get('Cookie', ''))
        self.assertIn('buvid4=B4-1', headers.get('Cookie', ''))
        self.assertEqual(self.spi_calls, 1)
        # 第二次取头部走缓存，不再请求 spi
        main.get_http_headers()
        self.assertEqual(self.spi_calls, 1)

    def test_fetch_works_with_buvid_cookie(self):
        self.install_fake_urlopen()
        info = main.fetch_video_info({'aid': '115376377694318'})
        self.assertIsNotNone(info)
        self.assertEqual(info.get('bvid'), 'BV1xx411c7mD')
        self.assertTrue(self.cookie_seen_in_request)
        self.assertIn('buvid3=', self.cookie_seen_in_request[0])

    def test_412_refreshes_buvid_once_and_retries(self):
        self.install_fake_urlopen(fail_first_view=1)
        main.gBuvidCookie = 'buvid3=stale; buvid4=stale'
        main.gBuvidCookieTime = time.time()
        info = main.fetch_video_info({'bvid': 'BV1xx411c7mD'})
        self.assertIsNotNone(info)
        self.assertEqual(self.spi_calls, 1)
        self.assertEqual(self.request_calls, 2)
        self.assertIn('buvid3=B3-1-infoc', main.gBuvidCookie)

    def test_blocked_notice_mentions_412(self):
        token = main.gHttpBlockedContext.set([])
        try:
            main.mark_http_blocked('HTTP 412')
            notice = main.build_fetch_failure_notice({'aid': '1'})
            self.assertIn('412', notice)
            self.assertNotIn('被B站限流', notice)
        finally:
            main.gHttpBlockedContext.reset(token)


if __name__ == '__main__':
    unittest.main()
