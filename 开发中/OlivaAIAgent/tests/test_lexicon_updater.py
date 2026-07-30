import copy
import os
import tempfile
import unittest
from unittest import mock

import OlivaAIAgent


class FakeResponse:
    def __init__(self, content=b'', status_code=200, headers=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size=65536):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start:start + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('HTTP %d' % self.status_code)

    def close(self):
        self.closed = True


class LexiconUpdaterTest(unittest.TestCase):
    def setUp(self):
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = copy.deepcopy(OlivaAIAgent.conf.gConf)
        self.temp_dir = tempfile.TemporaryDirectory()
        OlivaAIAgent.conf.dataPath = self.temp_dir.name

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        self.temp_dir.cleanup()

    @staticmethod
    def _content(prefix='测试词'):
        return ('\n'.join('%s%d' % (prefix, index) for index in range(30)) + '\n').encode()

    def test_first_download_validates_writes_and_reports_status(self):
        response = FakeResponse(
            self._content(),
            headers={'ETag': '"v1"', 'Last-Modified': 'Thu, 30 Jul 2026 00:00:00 GMT'},
        )
        with mock.patch.object(OlivaAIAgent.lexiconUpdater.requests, 'get', return_value=response):
            result = OlivaAIAgent.lexiconUpdater.checkAndUpdate()

        self.assertTrue(result['updated'])
        self.assertEqual(30, result['words'])
        self.assertTrue(os.path.isfile(result['path']))
        self.assertTrue(response.closed)

    def test_conditional_request_keeps_current_file_on_304(self):
        target = OlivaAIAgent.lexiconUpdater.lexiconPath()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as handle:
            handle.write(self._content())
        OlivaAIAgent.conf.atomicDump(
            {
                'source_url': OlivaAIAgent.lexiconUpdater.SOURCE_URL,
                'etag': '"v1"',
                'last_modified': 'Thu, 30 Jul 2026 00:00:00 GMT',
            },
            OlivaAIAgent.lexiconUpdater.metadataPath(),
        )
        response = FakeResponse(status_code=304)
        with mock.patch.object(
            OlivaAIAgent.lexiconUpdater.requests, 'get', return_value=response,
        ) as request:
            result = OlivaAIAgent.lexiconUpdater.checkAndUpdate()

        headers = request.call_args.kwargs['headers']
        self.assertEqual('"v1"', headers['If-None-Match'])
        self.assertEqual('current', result['result'])
        self.assertFalse(result['updated'])

    def test_invalid_download_never_overwrites_installed_file(self):
        target = OlivaAIAgent.lexiconUpdater.lexiconPath()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as handle:
            handle.write(self._content('旧词'))
        with open(target, 'rb') as handle:
            old_content = handle.read()
        response = FakeResponse(b'<html>gateway error</html>')
        with mock.patch.object(OlivaAIAgent.lexiconUpdater.requests, 'get', return_value=response):
            with self.assertRaises(ValueError):
                OlivaAIAgent.lexiconUpdater.checkAndUpdate()
        with open(target, 'rb') as handle:
            self.assertEqual(old_content, handle.read())

    def test_activate_config_preserves_existing_paths_without_duplicates(self):
        config = {'security': {'sensitive_word_files': ['existing.txt']}}
        target = OlivaAIAgent.lexiconUpdater.lexiconPath()
        OlivaAIAgent.lexiconUpdater.activateConfig(config, target)
        OlivaAIAgent.lexiconUpdater.activateConfig(config, target)

        self.assertTrue(config['security']['external_sensitive_words'])
        self.assertEqual(2, len(config['security']['sensitive_word_files']))


if __name__ == '__main__':
    unittest.main()
