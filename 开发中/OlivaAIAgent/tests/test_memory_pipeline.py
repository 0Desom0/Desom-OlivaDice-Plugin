# -*- encoding: utf-8 -*-

import copy
import tempfile
import unittest
from unittest import mock

import OlivaAIAgent


class ImmediateThread:
    def __init__(self, target, args=None, kwargs=None, **_options):
        self.target = target
        self.args = args or ()
        self.kwargs = kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class MemoryPipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_path = OlivaAIAgent.conf.dataPath
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.dataPath = self.temp_dir.name
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.conf.gConf['memory']['extraction_batch_size'] = 2
        OlivaAIAgent.ambient._history.clear()
        OlivaAIAgent.ambient._memory_state = {}
        OlivaAIAgent.ambient._memory_state_loaded = True
        OlivaAIAgent.ambient._memory_jobs.clear()

    def tearDown(self):
        OlivaAIAgent.conf.dataPath = self.old_data_path
        OlivaAIAgent.conf.gConf = self.old_conf
        OlivaAIAgent.ambient._history.clear()
        OlivaAIAgent.ambient._memory_state = {}
        OlivaAIAgent.ambient._memory_state_loaded = False
        OlivaAIAgent.ambient._memory_jobs.clear()
        self.temp_dir.cleanup()

    def test_batches_summary_without_enabling_vector_memory(self):
        extraction_result = {'summary_processed': True, 'vector_processed': False}
        with mock.patch.object(OlivaAIAgent.conf, 'isGroupHistoryMemory', return_value=True), \
                mock.patch.object(OlivaAIAgent.conf, 'isGroupLongMemory', return_value=False), \
                mock.patch.object(
                    OlivaAIAgent.knowledge,
                    'runMemoryExtraction',
                    return_value=extraction_result,
                ) as extraction, \
                mock.patch.object(OlivaAIAgent.ambient.threading, 'Thread', ImmediateThread):
            OlivaAIAgent.ambient.addToHistory(
                'qq',
                'group-1',
                'bot-1',
                'user-1',
                '甲',
                '第一条',
                message_id='message-1',
                reference_message_id='quoted-1',
                event_id='event-1',
                msg_idx='REFIDX_1',
                ref_msg_idx='REFIDX_0',
            )
            self.assertFalse(extraction.called)
            OlivaAIAgent.ambient.addToHistory(
                'qq', 'group-1', 'bot-1', 'user-2', '乙', '第二条', message_id='message-2',
            )

        extraction.assert_called_once()
        self.assertTrue(extraction.call_args.kwargs['record_summary'])
        self.assertFalse(extraction.call_args.kwargs['record_vector'])
        state = next(iter(OlivaAIAgent.ambient._memory_state.values()))
        self.assertEqual(2, state['summary_seq'])
        history = OlivaAIAgent.ambient.getHistory('qq', 'group-1')
        self.assertEqual('quoted-1', history[0]['reference_message_id'])
        self.assertEqual('event-1', history[0]['event_id'])
        self.assertEqual('REFIDX_1', history[0]['msg_idx'])
        self.assertEqual('REFIDX_0', history[0]['ref_msg_idx'])

    def test_failed_extraction_waits_for_next_message_before_retrying(self):
        with mock.patch.object(OlivaAIAgent.conf, 'isGroupHistoryMemory', return_value=True), \
                mock.patch.object(OlivaAIAgent.conf, 'isGroupLongMemory', return_value=False), \
                mock.patch.object(
                    OlivaAIAgent.knowledge,
                    'runMemoryExtraction',
                    return_value={'summary_processed': False, 'vector_processed': False},
                ) as extraction, \
                mock.patch.object(OlivaAIAgent.ambient.threading, 'Thread', ImmediateThread):
            OlivaAIAgent.ambient.addToHistory(
                'qq', 'group-1', 'bot-1', 'user-1', '甲', '第一条', message_id='message-1',
            )
            OlivaAIAgent.ambient.addToHistory(
                'qq', 'group-1', 'bot-1', 'user-2', '乙', '第二条', message_id='message-2',
            )

        extraction.assert_called_once()


if __name__ == '__main__':
    unittest.main()
