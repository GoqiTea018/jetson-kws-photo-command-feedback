"""无硬件验证：业务完成前、失败时不能播放成功提示音。"""

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from app_config import VoiceCommand
from command_handler import CommandResult
from live_photo import VoiceConfig, VoiceController


class CommandHandlerTests(unittest.TestCase):
    def test_photo_completion_precedes_feedback(self):
        steps = []

        def handler(command):
            self.assertEqual(command, VoiceCommand.TAKE_PHOTO)
            steps.append("saved")
            return CommandResult(True)

        controller = VoiceController(VoiceConfig(), handler)
        with patch("live_photo.play_audio", side_effect=lambda *args: steps.append("feedback")), redirect_stdout(io.StringIO()):
            controller._handle_command("拍照", Path("takephoto.wav"))
        self.assertEqual(steps, ["saved", "feedback"])

    def test_failure_exception_or_unconfirmed_result_suppresses_feedback(self):
        for outcome in (CommandResult(False, "保存失败"), None, True, CommandResult("pending"), RuntimeError("超时")):
            with self.subTest(outcome=outcome):
                handler = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=outcome)
                controller = VoiceController(VoiceConfig(), handler)
                with patch("live_photo.play_audio") as play, redirect_stdout(io.StringIO()) as output:
                    controller._handle_command("拍照", Path("takephoto.wav"))
                play.assert_not_called()
                self.assertIn("指令执行失败", output.getvalue())

    def test_sleep_never_reaches_business_handler(self):
        handler = Mock()
        controller = VoiceController(VoiceConfig(), handler)
        with patch("live_photo.play_audio") as play, redirect_stdout(io.StringIO()):
            controller._handle_command("再见楠机", Path("goodbye.wav"))
        handler.assert_not_called()
        play.assert_called_once()

    def test_failed_action_does_not_prevent_next_command(self):
        handler = Mock(side_effect=[CommandResult(False, "失败"), CommandResult(True)])
        controller = VoiceController(VoiceConfig(), handler)
        with patch("live_photo.play_audio") as play, redirect_stdout(io.StringIO()):
            controller._handle_command("拍照", Path("takephoto.wav"))
            controller._handle_command("测量", Path("measure.wav"))
        self.assertEqual(play.call_count, 1)
        self.assertEqual(handler.call_args.args, (VoiceCommand.MEASURE,))


if __name__ == "__main__":
    unittest.main()
