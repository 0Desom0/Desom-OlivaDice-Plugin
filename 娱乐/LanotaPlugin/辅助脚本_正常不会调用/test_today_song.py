# -*- encoding: utf-8 -*-
"""个人今日乐曲稳定性与用户隔离回归测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PLUGIN_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_PARENT))

from LanotaPlugin import function  # noqa: E402
from LanotaPlugin import message  # noqa: E402
from LanotaPlugin import utils  # noqa: E402


class TodaySongTest(unittest.TestCase):
    def setUp(self) -> None:
        self.songs = [
            {'id': index, 'chapter': f'Event-{index}', 'title': f'Song {index}'}
            for index in range(1, 7)
        ]
        self.user_data = {}

    def get_today_song(self, user_id: str):
        with (
            patch.object(function, 'get_today_seed', return_value=20260814),
            patch.object(function, 'load_song_data', return_value=self.songs),
            patch.object(function, 'load_user_data', return_value=self.user_data),
            patch.object(function, 'save_user_data', return_value=True),
        ):
            return function.get_user_today_song(user_id, 'linked-bot')

    def test_same_user_gets_same_song_for_the_whole_day(self) -> None:
        first = self.get_today_song('string-user-a')
        second = self.get_today_song('string-user-a')
        self.assertEqual(first['chapter'], second['chapter'])

    def test_different_string_user_ids_get_different_available_songs(self) -> None:
        first = self.get_today_song('string-user-a')
        second = self.get_today_song('string-user-b')
        self.assertNotEqual(first['chapter'], second['chapter'])

    def test_legacy_duplicate_is_reassigned_for_later_user(self) -> None:
        self.user_data.update({
            'alice': {
                'today_date': 20260814,
                'today_chapter': 'Event-1',
                'today_identity_hash': 'alice',
            },
            'bob': {
                'today_date': 20260814,
                'today_chapter': 'Event-1',
                'today_identity_hash': 'bob',
            },
        })
        alice_song = self.get_today_song('alice')
        bob_song = self.get_today_song('bob')
        self.assertEqual(alice_song['chapter'], 'Event-1')
        self.assertNotEqual(bob_song['chapter'], 'Event-1')
        self.assertEqual(self.get_today_song('bob')['chapter'], bob_song['chapter'])

    def test_numeric_today_cache_is_ignored_and_hash_gets_a_fresh_result(self) -> None:
        self.user_data['2000'] = {
            'today_date': 20260814,
            'today_chapter': 'Event-3',
            'other_data': 'kept',
        }
        expected_song = self.songs[
            function._today_song_start_index(20260814, 'core-user-hash', len(self.songs))
        ]
        song = self.get_today_song('core-user-hash')
        self.assertEqual(song, expected_song)
        self.assertIn('core-user-hash', self.user_data)
        self.assertEqual(self.user_data['core-user-hash']['today_chapter'], song['chapter'])
        self.assertEqual(self.user_data['core-user-hash']['today_identity_hash'], 'core-user-hash')
        self.assertEqual(self.user_data['2000']['today_chapter'], 'Event-3')
        self.assertEqual(self.user_data['2000']['other_data'], 'kept')

    def test_song_collision_is_allowed_only_after_catalog_is_exhausted(self) -> None:
        self.songs = self.songs[:2]
        assigned = [self.get_today_song(f'user-{index}')['chapter'] for index in range(3)]
        self.assertEqual(len(set(assigned[:2])), 2)
        self.assertIn(assigned[2], {'Event-1', 'Event-2'})

    def test_help_describes_per_user_daily_behavior(self) -> None:
        help_text = '\n'.join(message.help_categories['daily']['commands'])
        self.assertIn('每人每天固定', help_text)
        self.assertIn('互不重复', help_text)

    @staticmethod
    def make_event(user_id='2000', platform='qq'):
        return SimpleNamespace(
            data=SimpleNamespace(user_id=user_id),
            platform={'platform': platform},
        )

    def test_core_user_hash_is_used_when_available(self) -> None:
        get_user_hash = Mock(return_value='core-user-hash')
        core = SimpleNamespace(userConfig=SimpleNamespace(getUserHash=get_user_hash))
        event = self.make_event()
        with (
            patch.object(utils, 'has_oliva_dice_core', True),
            patch.object(utils, 'OlivaDiceCore', core, create=True),
        ):
            user_hash = utils.get_user_hash_from_event(event)
        self.assertEqual(user_hash, 'core-user-hash')
        get_user_hash.assert_called_once_with('2000', 'user', 'qq')

    def test_fallback_identity_is_hashed_instead_of_using_numeric_id(self) -> None:
        event = self.make_event()
        with patch.object(utils, 'has_oliva_dice_core', False):
            first_hash = utils.get_user_hash_from_event(event)
            second_hash = utils.get_user_hash_from_event(event)
            other_platform_hash = utils.get_user_hash_from_event(self.make_event(platform='discord'))
        self.assertEqual(first_hash, second_hash)
        self.assertNotEqual(first_hash, '2000')
        self.assertEqual(len(first_hash), 64)
        self.assertNotEqual(first_hash, other_platform_hash)

    def test_today_handler_passes_user_hash_instead_of_numeric_id(self) -> None:
        event = self.make_event()
        song = self.songs[0]
        with (
            patch.object(message.utils, 'get_sender_id_from_event', return_value='2000'),
            patch.object(message.utils, 'get_user_hash_from_event', return_value='core-user-hash'),
            patch.object(message.utils, 'get_bot_hash_from_event', return_value='linked-bot'),
            patch.object(message.utils, 'get_sender_name_from_event', return_value='Player'),
            patch.object(message.function, 'get_user_today_song', return_value=song) as get_today_song,
            patch.object(message, 'reply_song_detail'),
        ):
            message.handle_today(event)
        get_today_song.assert_called_once_with('core-user-hash', 'linked-bot')


if __name__ == '__main__':
    unittest.main()
