# -*- encoding: utf-8 -*-

import copy
import json
import unittest
from unittest import mock

import OlivaAIAgent


class FakeWebResponse:
    def __init__(self, body, content_type='text/html; charset=utf-8', status_code=200, url='https://example.com'):
        self.body = body if isinstance(body, bytes) else body.encode('utf-8')
        self.headers = {'Content-Type': content_type}
        self.status_code = status_code
        self.encoding = 'utf-8'
        self.url = url
        self.closed = False

    def iter_content(self, chunk_size=65536):
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index:index + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('HTTP %d' % self.status_code)

    def close(self):
        self.closed = True


class WebToolsTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = copy.deepcopy(OlivaAIAgent.conf.gConf)
        OlivaAIAgent.conf.gConf = {
            'search': {
                'enabled': True,
                'allow_private_network': False,
                'fetch_url_max_chars': 5000,
                'fetch_url_max_bytes': 2 * 1024 * 1024,
            },
        }

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf

    def test_fetch_url_extracts_title_and_article_text(self):
        page = '''
        <html><head><title>测试页面</title><style>隐藏样式</style></head>
        <body><nav>导航不应进入正文</nav><main><h1>今日新闻</h1>
        <p>这是第一段中文正文，包含足够的信息供智能体阅读和引用。</p>
        <p>这是第二段正文，用来确认段落结构会得到保留。</p></main>
        <script>恶意脚本内容</script></body></html>
        '''
        response = FakeWebResponse(page)
        with mock.patch.object(OlivaAIAgent.tools, '_isPublicWebUrl', return_value=(True, '')), \
                mock.patch.object(OlivaAIAgent.tools.requests, 'get', return_value=response):
            result = OlivaAIAgent.tools._t_fetch({}, {'url': 'https://example.com/news'})
        self.assertTrue(result['active'])
        data = result['data']
        self.assertEqual('测试页面', data['title'])
        self.assertIn('今日新闻', data['content'])
        self.assertIn('第一段中文正文', data['content'])
        self.assertNotIn('导航不应进入正文', data['content'])
        self.assertNotIn('恶意脚本内容', data['content'])
        self.assertFalse(data['truncated'])
        self.assertTrue(response.closed)

    def test_fetch_url_returns_structured_json(self):
        response = FakeWebResponse(
            json.dumps({'name': '青果', 'items': [1, 2]}, ensure_ascii=False),
            content_type='application/json; charset=utf-8',
        )
        with mock.patch.object(OlivaAIAgent.tools, '_isPublicWebUrl', return_value=(True, '')), \
                mock.patch.object(OlivaAIAgent.tools.requests, 'get', return_value=response):
            result = OlivaAIAgent.tools._t_fetch({}, {'url': 'https://example.com/data.json'})
        self.assertIn('"name": "青果"', result['data']['content'])
        self.assertEqual('', result['data']['title'])

    def test_fetch_url_rejects_binary_content(self):
        response = FakeWebResponse(b'%PDF-data', content_type='application/pdf')
        with mock.patch.object(OlivaAIAgent.tools, '_isPublicWebUrl', return_value=(True, '')), \
                mock.patch.object(OlivaAIAgent.tools.requests, 'get', return_value=response):
            result = OlivaAIAgent.tools._t_fetch({}, {'url': 'https://example.com/file.pdf'})
        self.assertIn('不支持读取此内容类型', result['error'])
        self.assertTrue(response.closed)

    def test_private_network_is_rejected_by_default(self):
        with mock.patch.object(
            OlivaAIAgent.tools.socket,
            'getaddrinfo',
            return_value=[(None, None, None, None, ('127.0.0.1', 80))],
        ):
            allowed, reason = OlivaAIAgent.tools._isPublicWebUrl('http://localhost/admin')
        self.assertFalse(allowed)
        self.assertIn('局域网', reason)


if __name__ == '__main__':
    unittest.main()
