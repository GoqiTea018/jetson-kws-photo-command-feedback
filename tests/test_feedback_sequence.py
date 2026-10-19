"""检查业务结果、音效与语音之间的事件顺序。"""

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from voice_control.command_handler import CommandResult
from voice_control.controller import VoiceConfig, VoiceController
from voice_control.sound_effects import SOUND_FILES, SoundEvent


class FeedbackSequenceTests(unittest.TestCase):
    def test_success_order_for_each_event_in_both_playback_modes(self):
        cases = {
            "拍照": ["effect", "voice"],
            "录像": ["voice", "effect"],
            "停止录像": ["effect", "voice"],
            "冻结画面": ["effect", "voice"],
            "测量": ["voice", "effect"],
            "开启检测": ["voice", "effect"],
            "停止检测": ["voice", "effect"],
        }
        for keyword, expected in cases.items():
            for continuous in (False, True):
                with self.subTest(keyword=keyword, continuous=continuous):
                    steps = []

                    def handle(command):
                        steps.append("completed")
                        return CommandResult(True)

                    def play(path, *args):
                        steps.append("voice" if path.name == "voice.wav" else "effect")

                    service = VoiceController(VoiceConfig(continuous_audio=continuous), handle)
                    if continuous:
                        service._playback = Mock()
                        service._playback.play.side_effect = play
                    with patch("voice_control.controller.play_audio", side_effect=play), patch(
                        "voice_control.sound_effects.ContinuousPlayback"
                    ) as extra_player, redirect_stdout(io.StringIO()):
                        service._handle_command(keyword, Path("voice.wav"))
                    self.assertEqual(steps, ["completed", *expected])
                    extra_player.assert_not_called()

    def test_empty_effect_still_plays_success_voice(self):
        service = VoiceController(VoiceConfig(), Mock(return_value=CommandResult(True)))
        with patch.dict(SOUND_FILES, {SoundEvent.TAKE_PHOTO: ""}), patch.object(
            service, "_play_sound"
        ) as play, redirect_stdout(io.StringIO()):
            service._handle_command("拍照", Path("voice.wav"))
        play.assert_called_once_with(Path("voice.wav"))

    def test_missing_voice_still_plays_effect_after_success(self):
        service = VoiceController(VoiceConfig(), Mock(return_value=CommandResult(True)))
        with patch.object(service, "_play_sound") as play, redirect_stdout(io.StringIO()):
            service._handle_command("开启检测", None)
        self.assertEqual(play.call_count, 1)
        self.assertEqual(play.call_args.args[0].parent.name, "start_detection")

    def test_reset_completion_keeps_start_effect_unbound(self):
        service = VoiceController(VoiceConfig(), Mock(return_value=CommandResult(True)))
        with patch.object(service, "_play_sound") as play, redirect_stdout(io.StringIO()):
            service._handle_command("复位", Path("reset.wav"))
        play.assert_called_once_with(Path("reset.wav"))


if __name__ == "__main__":
    unittest.main()
