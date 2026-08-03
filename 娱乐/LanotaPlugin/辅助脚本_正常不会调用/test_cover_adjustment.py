# -*- encoding: utf-8 -*-
"""曲绘纵向校正与缓存的离线回归测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_PARENT))

from LanotaPlugin import crawler  # noqa: E402
from LanotaPlugin import message  # noqa: E402
from LanotaPlugin import utils  # noqa: E402

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, 'Pillow unavailable')
class CoverAdjustmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / 'CoverArt'
        self.seed_dir = self.root / 'SeedCoverArt'
        self.adjusted_dir = self.runtime_dir / 'Adjusted'
        self.runtime_dir.mkdir()
        self.seed_dir.mkdir()
        self.adjusted_dir.mkdir()
        self.patchers = [
            patch.object(utils, 'get_cover_art_dir', return_value=str(self.runtime_dir)),
            patch.object(utils, 'get_seed_cover_art_dir', return_value=str(self.seed_dir)),
            patch.object(utils, 'get_adjusted_cover_art_dir', return_value=str(self.adjusted_dir)),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def create_image(path: Path, size: tuple[int, int]) -> None:
        Image.new('RGB', size, '#3a7ca5').save(path, format='PNG')

    def test_1024_by_512_cover_is_stretched_to_576(self) -> None:
        source_path = self.runtime_dir / 'normal.png'
        self.create_image(source_path, (1024, 512))

        display_path = Path(crawler.prepare_cover_for_display(str(source_path)))

        self.assertEqual(display_path.parent, self.adjusted_dir)
        with Image.open(display_path) as display_image:
            self.assertEqual(display_image.size, (1024, 576))

    def test_double_size_cover_uses_the_same_multiplier(self) -> None:
        source_path = self.runtime_dir / 'chapter8.png'
        self.create_image(source_path, (2048, 1024))

        display_path = Path(crawler.prepare_cover_for_display(str(source_path)))

        with Image.open(display_path) as display_image:
            self.assertEqual(display_image.size, (2048, 1152))

    def test_non_two_to_one_cover_uses_original(self) -> None:
        source_path = self.runtime_dir / 'square.png'
        self.create_image(source_path, (512, 512))

        display_path = crawler.prepare_cover_for_display(str(source_path))

        self.assertEqual(Path(display_path), source_path)
        self.assertFalse((self.adjusted_dir / source_path.name).exists())

    def test_existing_adjusted_cover_is_not_rewritten(self) -> None:
        source_path = self.runtime_dir / 'cached.png'
        adjusted_path = self.adjusted_dir / source_path.name
        self.create_image(source_path, (1024, 512))
        self.create_image(adjusted_path, (10, 10))

        display_path = crawler.prepare_cover_for_display(str(source_path))

        self.assertEqual(Path(display_path), adjusted_path)
        with Image.open(adjusted_path) as display_image:
            self.assertEqual(display_image.size, (10, 10))

    def test_song_cover_entry_points_return_adjusted_paths(self) -> None:
        source_path = self.runtime_dir / 'entry.png'
        self.create_image(source_path, (1024, 512))
        with patch.object(crawler, 'get_cached_cover_paths', return_value=[str(source_path)]):
            cover_paths = crawler.ensure_song_covers({'chapter': 'test'})
            first_cover_path = crawler.ensure_song_cover({'chapter': 'test'})

        expected_path = self.adjusted_dir / source_path.name
        self.assertEqual([Path(path) for path in cover_paths], [expected_path])
        self.assertEqual(Path(first_cover_path), expected_path)

    def test_batch_adjustment_skips_cached_and_non_two_to_one_files(self) -> None:
        self.create_image(self.runtime_dir / 'new.png', (1024, 512))
        self.create_image(self.runtime_dir / 'cached.png', (1024, 512))
        self.create_image(self.runtime_dir / 'square.png', (512, 512))
        self.create_image(self.adjusted_dir / 'cached.png', (1024, 576))

        result = crawler.run_cover_adjustment()

        self.assertEqual(result['total'], 3)
        self.assertEqual(result['adjusted'], 1)
        self.assertEqual(result['cached'], 1)
        self.assertEqual(result['unchanged'], 1)
        self.assertEqual(result['failed'], 0)

    def test_batch_command_rejects_plugin_admin_who_is_not_core_master(self) -> None:
        event = object()
        with (
            patch.object(message.utils, 'sender_has_master_permission', return_value=True),
            patch.object(message.utils, 'sender_is_core_master', return_value=False),
            patch.object(message, 'reply_text') as reply_text,
            patch.object(message.crawler, 'run_cover_adjustment') as run_cover_adjustment,
        ):
            message.handle_cover(event, 'resize')

        run_cover_adjustment.assert_not_called()
        self.assertIn('只有 OlivaDiceCore 骰主', reply_text.call_args.args[1])

    def test_batch_command_allows_core_master(self) -> None:
        event = object()
        result = {
            'total': 0,
            'adjusted': 0,
            'cached': 0,
            'unchanged': 0,
            'failed': 0,
            'cover_dir': str(self.adjusted_dir),
        }
        with (
            patch.object(message.utils, 'sender_has_master_permission', return_value=True),
            patch.object(message.utils, 'sender_is_core_master', return_value=True),
            patch.object(message, 'reply_text') as reply_text,
            patch.object(message.crawler, 'run_cover_adjustment', return_value=result) as run_cover_adjustment,
        ):
            message.handle_cover(event, 'resize')

        run_cover_adjustment.assert_called_once()
        self.assertEqual(reply_text.call_count, 2)


if __name__ == '__main__':
    unittest.main()
