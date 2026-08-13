# -*- encoding: utf-8 -*-

import copy
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

import OlivaAIAgent


class FakeProc:
    def __init__(self):
        self.records = []

    def log(self, level, message, segments=None):
        self.records.append((level, message, segments))


class FakeEvent:
    def __init__(self):
        self.platform = {'platform': 'qqGuild', 'sdk': 'qqGuildv2_link'}
        self.data = SimpleNamespace(
            group_id='group-1',
            user_id='user-1',
            message_id='incoming-1',
        )


class FileStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        self.old_cleanup_day = OlivaAIAgent.conf._last_log_cleanup_day
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.conf._last_log_cleanup_day = ''
        OlivaAIAgent.memory._sessions.clear()

    def tearDown(self):
        OlivaAIAgent.memory._sessions.clear()
        OlivaAIAgent.conf._last_log_cleanup_day = self.old_cleanup_day
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        self.temp_dir.cleanup()

    def test_normal_log_is_written_to_daily_file_and_redacted(self):
        proc = FakeProc()
        OlivaAIAgent.conf.gConf['debug_log'] = False
        OlivaAIAgent.conf.log(
            proc,
            2,
            '请求 api_key=secret-value url=https://example.invalid/a?rkey=private-key '
            'audio=data:audio/wav;base64,QUJDRA==',
        )

        path = os.path.join(
            self.temp_dir.name,
            'logs',
            time.strftime('%Y-%m-%d') + '.log',
        )
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding='utf-8') as handle:
            content = handle.read()
        self.assertIn('[INFO] [OlivaAIAgent] 请求', content)
        self.assertIn('api_key=<已隐藏>', content)
        self.assertIn('rkey=<已隐藏>', content)
        self.assertIn('<媒体数据已隐藏>', content)
        self.assertNotIn('secret-value', content)
        self.assertNotIn('private-key', content)
        self.assertNotIn('QUJDRA', content)
        self.assertEqual(1, len(proc.records))

    def test_file_logging_switch_disables_disk_write_but_keeps_terminal(self):
        proc = FakeProc()
        OlivaAIAgent.conf.gConf['file_logging']['enable'] = False

        OlivaAIAgent.conf.log(proc, 3, '只进终端')

        self.assertEqual(1, len(proc.records))
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir.name, 'logs')))

    def test_expired_plugin_logs_are_removed_without_touching_other_files(self):
        log_dir = OlivaAIAgent.conf.logDir()
        os.makedirs(log_dir, exist_ok=True)
        old_log = os.path.join(log_dir, '2020-01-01.log')
        keep_file = os.path.join(log_dir, 'notes.txt')
        for path in (old_log, keep_file):
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('old')
            os.utime(path, (1, 1))
        OlivaAIAgent.conf.gConf['file_logging']['retention_days'] = 1
        OlivaAIAgent.conf._last_log_cleanup_day = ''

        OlivaAIAgent.conf.log(None, 2, '触发清理')

        self.assertFalse(os.path.exists(old_log))
        self.assertTrue(os.path.exists(keep_file))

    def test_unified_group_reply_is_saved_as_user_session_with_ids(self):
        event = FakeEvent()
        saved = OlivaAIAgent.ambient.saveUserSession(
            event,
            '帮我解释一下',
            [{
                'message': '解释内容',
                'message_ids': ['outgoing-1'],
                'message_indexes': ['index-1'],
                'reference_message_id': 'incoming-1',
            }],
            bot_hash='bot-hash',
        )

        key = OlivaAIAgent.memory.sessionKey('qqGuild', 'group-1', 'user-1')
        path = OlivaAIAgent.memory._session_path(key)
        self.assertTrue(saved)
        self.assertTrue(os.path.isfile(path))
        session = OlivaAIAgent.memory.getSession(key)
        self.assertEqual(['帮我解释一下', '解释内容'], [item['content'] for item in session])
        self.assertEqual('incoming-1', session[0]['message_id'])
        self.assertEqual('outgoing-1', session[1]['message_id'])
        self.assertEqual(['outgoing-1'], session[1]['message_ids'])
        self.assertEqual('index-1', session[1]['msg_idx'])
        self.assertEqual('incoming-1', session[1]['reference_message_id'])

    def test_skipped_reply_does_not_create_empty_session(self):
        event = FakeEvent()

        saved = OlivaAIAgent.ambient.saveUserSession(event, '没有回复', [], bot_hash='bot-hash')

        key = OlivaAIAgent.memory.sessionKey('qqGuild', 'group-1', 'user-1')
        self.assertFalse(saved)
        self.assertFalse(os.path.exists(OlivaAIAgent.memory._session_path(key)))

    def test_session_replaces_expiring_image_segments_with_stable_placeholders(self):
        event = FakeEvent()

        OlivaAIAgent.ambient.saveUserSession(
            event,
            '[OP:image,file=https://cdn.invalid/incoming.jpg]这张图',
            [{
                'message': '[OP:image,file=https://cdn.invalid/outgoing.jpg]',
                'message_ids': ['outgoing-image-1'],
                'message_indexes': [],
            }],
            bot_hash='bot-hash',
        )

        key = OlivaAIAgent.memory.sessionKey('qqGuild', 'group-1', 'user-1')
        session = OlivaAIAgent.memory.getSession(key)
        self.assertEqual('[图片]这张图', session[0]['content'])
        self.assertEqual('[图片]', session[1]['content'])
        self.assertNotIn('cdn.invalid', str(session))


if __name__ == '__main__':
    unittest.main()
