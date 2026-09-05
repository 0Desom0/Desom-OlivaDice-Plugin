# -*- encoding: utf-8 -*-

import base64
import copy
import json
import os
import tempfile
import unittest
from unittest import mock

import OlivOS
import OlivaAIAgent


def _tiny_wav():
    data = b'\x00\x00'
    return (
        b'RIFF'
        + (36 + len(data)).to_bytes(4, 'little')
        + b'WAVEfmt '
        + (16).to_bytes(4, 'little')
        + (1).to_bytes(2, 'little')
        + (1).to_bytes(2, 'little')
        + (8000).to_bytes(4, 'little')
        + (16000).to_bytes(4, 'little')
        + (2).to_bytes(2, 'little')
        + (16).to_bytes(2, 'little')
        + b'data'
        + len(data).to_bytes(4, 'little')
        + data
    )


class FakeHttpResponse:
    def __init__(self, data=None, content=b'', content_type='application/json', status_code=200):
        self._data = data
        self.content = content
        self.status_code = status_code
        self.headers = {'Content-Type': content_type}
        self.text = '' if data is None else json.dumps(data, ensure_ascii=False)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code < 200 or self.status_code >= 300:
            raise RuntimeError('HTTP %s' % self.status_code)


class FakeVoiceEvent:
    def reply(self, message):
        return {'active': True, 'data': {'message_id': 'mimo-voice-1'}}


class MimoTtsTest(unittest.TestCase):
    def setUp(self):
        self.old_conf = OlivaAIAgent.conf.gConf
        OlivaAIAgent.conf.gConf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        OlivaAIAgent.conf.gConf['debug_log'] = False
        OlivaAIAgent.conf.gConf['prompt']['system'] = (
            '芙萝妮娅 / Fronia，自称小芙。活泼元气的狐娘，口语化，傲娇嘴硬。'
        )
        OlivaAIAgent.conf.gConf['voice'].update({
            'enabled': True,
            'provider': 'mimo_tts',
            'api_url': 'https://api.xiaomimimo.com/v1/chat/completions',
            'api_key': 'mimo-test-key',
            'mimo_mode': 'default',
            'voice': '冰糖',
            'response_format': 'wav',
            'timeout_sec': 30,
        })

    def tearDown(self):
        OlivaAIAgent.conf.gConf = self.old_conf

    def _mimoAudioResponse(self, audio_bytes=None):
        payload = audio_bytes if audio_bytes is not None else _tiny_wav()
        return FakeHttpResponse(data={
            'id': 'mimo-completion-1',
            'object': 'chat.completion',
            'choices': [{
                'index': 0,
                'finish_reason': 'stop',
                'message': {
                    'role': 'assistant',
                    'content': '',
                    'audio': {
                        'id': '979a91904f9a4143928d9e1f54837b4f',
                        'data': base64.b64encode(payload).decode('ascii'),
                        'expires_at': None,
                        'transcript': None,
                    },
                },
            }],
        })

    def test_default_mode_posts_chat_completions_payload(self):
        event = FakeVoiceEvent()
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(OlivaAIAgent.voice, 'outputDir', return_value=directory), \
                mock.patch.object(OlivaAIAgent.voice, '_cleanOldFiles', return_value=0), \
                mock.patch.object(
                    OlivaAIAgent.voice.requests,
                    'post',
                    return_value=self._mimoAudioResponse(),
                ) as post, \
                mock.patch.object(OlivaAIAgent.identifiers, 'recordOutgoing'):
            result = OlivaAIAgent.voice.sendVoice(
                {'plugin_event': event, 'Proc': None, 'trace_id': 'mimo-default'},
                '主人, 今晚开团吗',
                'Brisk, a little smug and pleased.',
            )

        self.assertTrue(result['active'])
        self.assertEqual('wav', result['data']['format'])
        request = post.call_args.kwargs
        self.assertEqual(
            'https://api.xiaomimimo.com/v1/chat/completions',
            post.call_args.args[0],
        )
        self.assertEqual('mimo-test-key', request['headers']['api-key'])
        self.assertEqual('Bearer mimo-test-key', request['headers']['Authorization'])
        self.assertEqual({
            'model': 'mimo-v2.5-tts',
            'messages': [
                {'role': 'user', 'content': 'Brisk, a little smug and pleased.'},
                {'role': 'assistant', 'content': '主人, 今晚开团吗'},
            ],
            'audio': {'format': 'wav', 'voice': '冰糖'},
            'stream': False,
        }, request['json'])

    def test_clone_mode_embeds_reference_audio_as_data_url(self):
        wav_bytes = _tiny_wav()
        with tempfile.TemporaryDirectory() as directory:
            reference = os.path.join(directory, 'ref.wav')
            with open(reference, 'wb') as file_obj:
                file_obj.write(wav_bytes)
            OlivaAIAgent.conf.gConf['voice']['mimo_mode'] = 'clone'
            OlivaAIAgent.conf.gConf['voice']['clone_audio'] = reference
            with mock.patch.object(OlivaAIAgent.voice, 'outputDir', return_value=directory), \
                    mock.patch.object(OlivaAIAgent.voice, '_cleanOldFiles', return_value=0), \
                    mock.patch.object(
                        OlivaAIAgent.voice.requests,
                        'post',
                        return_value=self._mimoAudioResponse(wav_bytes),
                    ) as post:
                path = OlivaAIAgent.voice.synthesize('这绝对不是小芙的问题~', '自然地朗读。')

            request = post.call_args.kwargs
            self.assertEqual('mimo-v2.5-tts-voiceclone', request['json']['model'])
            self.assertEqual(
                [
                    {'role': 'user', 'content': '自然地朗读。'},
                    {'role': 'assistant', 'content': '这绝对不是小芙的问题~'},
                ],
                request['json']['messages'],
            )
            voice_value = request['json']['audio']['voice']
            self.assertTrue(voice_value.startswith('data:audio/wav;base64,'))
            decoded = base64.b64decode(voice_value.split(',', 1)[1])
            self.assertEqual(wav_bytes, decoded)
            self.assertTrue(os.path.isfile(path))

    def test_design_mode_uses_persona_prompt_and_rejects_voice_field(self):
        OlivaAIAgent.conf.gConf['voice']['mimo_mode'] = 'design'
        OlivaAIAgent.conf.gConf['voice']['design_prompt'] = ''
        OlivaAIAgent.conf.gConf['voice']['optimize_text_preview'] = True
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(OlivaAIAgent.voice, 'outputDir', return_value=directory), \
                mock.patch.object(OlivaAIAgent.voice, '_cleanOldFiles', return_value=0), \
                mock.patch.object(
                    OlivaAIAgent.voice.requests,
                    'post',
                    return_value=self._mimoAudioResponse(),
                ) as post:
            OlivaAIAgent.voice.synthesize('耳朵和尾巴不许碰', 'Tense and bristling, still clearly articulated.')

        payload = post.call_args.kwargs['json']
        self.assertEqual('mimo-v2.5-tts-voicedesign', payload['model'])
        self.assertNotIn('voice', payload['audio'])
        self.assertTrue(payload['audio']['optimize_text_preview'])
        user_content = payload['messages'][0]['content']
        self.assertIn('年轻少女声', user_content)
        self.assertIn('Performance instructions: Tense and bristling, still clearly articulated.', user_content)
        self.assertEqual('耳朵和尾巴不许碰', payload['messages'][1]['content'])

    def test_clone_without_reference_is_not_ready(self):
        OlivaAIAgent.conf.gConf['voice']['mimo_mode'] = 'clone'
        OlivaAIAgent.conf.gConf['voice']['clone_audio'] = ''
        status = OlivaAIAgent.voice.getStatus()
        self.assertFalse(status['ready'])
        with self.assertRaisesRegex(RuntimeError, 'clone_audio'):
            OlivaAIAgent.voice.synthesize('测试')

    def test_dashscope_default_url_is_rewritten_for_mimo(self):
        OlivaAIAgent.conf.gConf['voice']['api_url'] = (
            'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'
        )
        OlivaAIAgent.conf.gConf['voice']['voice'] = 'Cherry'
        status = OlivaAIAgent.voice.getStatus()
        self.assertEqual('https://api.xiaomimimo.com/v1/chat/completions', status['api_url'])
        self.assertEqual('mimo-v2.5-tts', status['model'])
        self.assertEqual('冰糖', status['voice'])
        self.assertTrue(status['ready'])

    def test_mimo_drops_user_message_when_instructions_copy_spoken_text(self):
        line = '哇，这位金发的小姐姐看着好可爱！这是哪家公会的新队员吗？长得真标致~'
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(OlivaAIAgent.voice, 'outputDir', return_value=directory), \
                mock.patch.object(OlivaAIAgent.voice, '_cleanOldFiles', return_value=0), \
                mock.patch.object(
                    OlivaAIAgent.voice.requests,
                    'post',
                    return_value=self._mimoAudioResponse(),
                ) as post:
            OlivaAIAgent.voice.synthesize(line + line, line)

        payload = post.call_args.kwargs['json']
        self.assertEqual(
            [{'role': 'assistant', 'content': line}],
            payload['messages'],
        )

    def test_create_alias_maps_to_design_mode(self):
        OlivaAIAgent.conf.gConf['voice']['mimo_mode'] = 'create'
        status = OlivaAIAgent.voice.getStatus()
        self.assertEqual('design', status['mimo_mode'])
        self.assertEqual('mimo-v2.5-tts-voicedesign', status['model'])

    def test_clone_audio_accepts_absolute_and_relative_paths(self):
        wav_bytes = _tiny_wav()
        plugin_root = OlivaAIAgent.voice._pluginRoot()
        listen_dir = os.path.join(plugin_root, '试听_路径解析测试')
        os.makedirs(listen_dir, exist_ok=True)
        try:
            absolute = os.path.join(listen_dir, 'ref_abs.wav')
            with open(absolute, 'wb') as file_obj:
                file_obj.write(wav_bytes)
            relative_name = os.path.join('试听_路径解析测试', 'ref_abs.wav')
            self.assertEqual(os.path.abspath(absolute), OlivaAIAgent.voice.resolveCloneAudioPath(absolute))
            self.assertEqual(
                os.path.abspath(absolute),
                OlivaAIAgent.voice.resolveCloneAudioPath('"%s"' % relative_name.replace('\\', '/')),
            )
            OlivaAIAgent.conf.gConf['voice']['mimo_mode'] = 'clone'
            OlivaAIAgent.conf.gConf['voice']['clone_audio'] = relative_name
            with tempfile.TemporaryDirectory() as directory, \
                    mock.patch.object(OlivaAIAgent.voice, 'outputDir', return_value=directory), \
                    mock.patch.object(OlivaAIAgent.voice, '_cleanOldFiles', return_value=0), \
                    mock.patch.object(
                        OlivaAIAgent.voice.requests,
                        'post',
                        return_value=self._mimoAudioResponse(wav_bytes),
                    ) as post:
                OlivaAIAgent.voice.synthesize('相对路径克隆。', '自然地朗读。')
            voice_value = post.call_args.kwargs['json']['audio']['voice']
            self.assertTrue(voice_value.startswith('data:audio/wav;base64,'))
        finally:
            try:
                os.remove(os.path.join(listen_dir, 'ref_abs.wav'))
                os.rmdir(listen_dir)
            except Exception:
                pass

    def test_persona_design_prompt_detects_fronia(self):
        prompt = OlivaAIAgent.voice.personaVoiceDesignPrompt()
        self.assertIn('年轻少女声', prompt)
        self.assertIn('傲娇', prompt)


if __name__ == '__main__':
    unittest.main()
