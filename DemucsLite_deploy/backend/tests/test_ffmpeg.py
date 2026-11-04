"""FFmpeg selection must work for both system and bundled installations."""
import os
import sys
import types
import unittest
from unittest.mock import patch

from app.config import resolve_ffmpeg_binary


class FFmpegSelectionTests(unittest.TestCase):
    def test_explicit_binary_takes_priority(self):
        with patch.dict(os.environ, {"FFMPEG_BINARY": "/custom/ffmpeg"}), \
                patch("app.config.shutil.which") as lookup:
            self.assertEqual(resolve_ffmpeg_binary(), "/custom/ffmpeg")
            lookup.assert_not_called()

    def test_system_binary_takes_priority_over_python_package(self):
        with patch.dict(os.environ, {"FFMPEG_BINARY": ""}), \
                patch("app.config.shutil.which", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(resolve_ffmpeg_binary(), "/usr/bin/ffmpeg")

    def test_uses_bundled_binary_when_missing_from_path(self):
        package = types.SimpleNamespace(get_ffmpeg_exe=lambda: "/venv/binaries/ffmpeg")
        with patch.dict(os.environ, {"FFMPEG_BINARY": ""}), \
                patch("app.config.shutil.which", return_value=None), \
                patch.dict(sys.modules, {"imageio_ffmpeg": package}):
            self.assertEqual(resolve_ffmpeg_binary(), "/venv/binaries/ffmpeg")

    def test_missing_optional_package_keeps_standard_decoder_error(self):
        with patch.dict(os.environ, {"FFMPEG_BINARY": ""}), \
                patch("app.config.shutil.which", return_value=None), \
                patch.dict(sys.modules, {"imageio_ffmpeg": None}):
            self.assertEqual(resolve_ffmpeg_binary(), "ffmpeg")
