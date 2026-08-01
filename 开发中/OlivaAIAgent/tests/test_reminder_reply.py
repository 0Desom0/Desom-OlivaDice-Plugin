# -*- encoding: utf-8 -*-

import unittest
from types import SimpleNamespace
from unittest import mock

import OlivaAIAgent


class ReminderReplyTest(unittest.TestCase):
    def test_schedule_tool_persists_main_model_final_text(self):
        event = SimpleNamespace(
            bot_info=SimpleNamespace(hash='bot-1'),
            data=SimpleNamespace(host_id=None, sender={'nickname': '用户'}),
        )
        ctx = {
            'plugin_event': event,
            'func_type': 'private_message',
            'platform': 'qq',
            'group_id': None,
            'user_id': 'user-1',
        }
        with mock.patch.object(OlivaAIAgent.reminder, 'parseFireTs', return_value=200.0), \
                mock.patch.object(OlivaAIAgent.tools.time, 'time', return_value=100.0), \
                mock.patch.object(OlivaAIAgent.reminder, 'total', return_value=0), \
                mock.patch.object(OlivaAIAgent.reminder, 'countForUser', return_value=0), \
                mock.patch.object(
                    OlivaAIAgent.reminder,
                    'schedule',
                    return_value={'id': 'reminder-1'},
                ) as schedule:
            result = OlivaAIAgent.tools._t_schedule_reminder(
                ctx,
                {'content': '喝水', 'final_text': '该喝水啦~', 'delay_seconds': 100},
            )

        self.assertTrue(result['active'])
        self.assertEqual('该喝水啦~', schedule.call_args.kwargs['final_text'])

    def test_saved_main_model_text_is_sent_without_another_model_call(self):
        job = {
            'content': '喝水',
            'final_text': '该补充水分啦~',
            'bot_hash': 'bot-1',
        }
        with mock.patch.object(OlivaAIAgent.aiClient, 'chat') as chat:
            text = OlivaAIAgent.reminder._generateReply(job)
        self.assertEqual('该补充水分啦~', text)
        chat.assert_not_called()

    def test_old_job_uses_deterministic_fallback_without_model_call(self):
        job = {'content': '喝水', 'bot_hash': 'bot-1'}
        with mock.patch.object(OlivaAIAgent.contentSafety, 'blocked', return_value=False), \
                mock.patch.object(OlivaAIAgent.aiClient, 'chat') as chat:
            text = OlivaAIAgent.reminder._generateReply(job)
        self.assertEqual('提醒：喝水', text)
        chat.assert_not_called()


if __name__ == '__main__':
    unittest.main()
