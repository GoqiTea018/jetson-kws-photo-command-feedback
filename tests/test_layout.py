"""目录整理后的资源契约：换工作目录不能改变配置与提示音位置。"""

import unittest
import os
import tempfile
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from voice_control import controller

from voice_control.config import (
    COMMAND_AUDIO_FILES, CONFIG_DIR, KEYWORD_COMMANDS, PROJECT_DIR, SOUNDS_DIR,
)


class ResourceLayoutTests(unittest.TestCase):
    def test_listener_paths_survive_a_different_working_directory(self):
        original_directory = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch.object(controller, "realtime_command", return_value=["kws"]) as build, patch.object(
                    controller, "configure_capture_route"
                ), patch.object(controller, "wait_for_keyword", side_effect=["楠机楠机", "拍照"]) as wait, patch.object(
                    controller, "play_audio"
                ) as play, redirect_stdout(io.StringIO()):
                    controller.VoiceController(controller.VoiceConfig(once=True)).run()
                self.assertEqual(build.call_args_list[0].args[1], CONFIG_DIR / "wake_keywords.txt")
                self.assertEqual(build.call_args_list[1].args[1], CONFIG_DIR / "command_keywords.txt")
                self.assertEqual(wait.call_args_list[0].args[2]["ALSA_CONFIG_PATH"], str(CONFIG_DIR / "kws-left.asoundrc"))
                self.assertEqual(play.call_args_list[0].args[0], SOUNDS_DIR / "nanji.wav")
                self.assertEqual(play.call_args_list[1].args[0], SOUNDS_DIR / "takephoto.wav")
            finally:
                os.chdir(original_directory)

    def test_runtime_resources_are_present_under_project(self):
        self.assertEqual(CONFIG_DIR, PROJECT_DIR / "config")
        self.assertEqual(SOUNDS_DIR, PROJECT_DIR / "sounds")
        for name in ("wake_keywords.txt", "command_keywords.txt", "photo_keywords.txt", "kws-left.asoundrc"):
            with self.subTest(name=name):
                self.assertTrue((CONFIG_DIR / name).is_file())
        for name in ("nanji.wav", *COMMAND_AUDIO_FILES.values()):
            with self.subTest(name=name):
                self.assertTrue((SOUNDS_DIR / name).is_file())

    def test_keyword_file_and_command_mapping_agree(self):
        keyword_text = (CONFIG_DIR / "command_keywords.txt").read_text(encoding="utf-8")
        keywords = {
            line.split("@", 1)[1].strip()
            for line in keyword_text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertEqual(keywords, set(KEYWORD_COMMANDS))


if __name__ == "__main__":
    unittest.main()
