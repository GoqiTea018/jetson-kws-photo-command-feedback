"""无硬件验证：业务完成前、失败时不能播放成功提示音。"""

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from voice_control.config import VoiceCommand, KEYWORD_COMMANDS, COMMAND_SOUNDS
from voice_control.command_handler import CommandResult
from voice_control.sound_effects import COMMAND_EFFECTS, SOUND_FILES
from voice_control.config import SOUNDS_DIR
from voice_control.controller import VoiceConfig, VoiceController


class CommandHandlerTests(unittest.TestCase):
    def test_empty_prompt_preserves_business_dispatch(self):
        for keyword, filename in COMMAND_SOUNDS.items():
            if filename:
                continue
            for success in (True, False):
                with self.subTest(keyword=keyword, success=success):
                    handler = Mock(return_value=CommandResult(success, "test"))
                    service = VoiceController(VoiceConfig(), handler)
                    with patch.object(service, "_play_sound") as play, redirect_stdout(io.StringIO()) as output:
                        service._handle_command(keyword, None)
                    handler.assert_called_once_with(KEYWORD_COMMANDS[keyword])
                    effect = COMMAND_EFFECTS.get(KEYWORD_COMMANDS[keyword])
                    if success and effect is not None and SOUND_FILES[effect]:
                        play.assert_called_once_with(SOUNDS_DIR / SOUND_FILES[effect])
                    else:
                        play.assert_not_called()
                    self.assertIn("指令执行成功" if success else "指令执行失败", output.getvalue())

    def test_empty_prompt_without_handler_reports_recognition(self):
        service = VoiceController(VoiceConfig())
        with patch.object(service, "_play_sound") as play, redirect_stdout(io.StringIO()) as output:
            service._handle_command("相册", None)
        play.assert_not_called()
        self.assertIn("已识别指令：相册", output.getvalue())

    def test_photo_completion_precedes_feedback(self):
        steps = []

        def handler(command):
            self.assertEqual(command, VoiceCommand.TAKE_PHOTO)
            steps.append("saved")
            return CommandResult(True)

        controller = VoiceController(VoiceConfig(), handler)
        with patch("voice_control.controller.play_audio", side_effect=lambda path, *args: steps.append("effect" if path.name == "01_uisfx_minimal.wav" else "voice")), redirect_stdout(io.StringIO()):
            controller._handle_command("拍照", Path("takephoto.wav"))
        self.assertEqual(steps, ["saved", "effect", "voice"])

    def test_failure_exception_or_unconfirmed_result_suppresses_feedback(self):
        for outcome in (CommandResult(False, "保存失败"), None, True, CommandResult("pending"), RuntimeError("超时")):
            with self.subTest(outcome=outcome):
                handler = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=outcome)
                controller = VoiceController(VoiceConfig(), handler)
                with patch("voice_control.controller.play_audio") as play, redirect_stdout(io.StringIO()) as output:
                    controller._handle_command("拍照", Path("takephoto.wav"))
                play.assert_not_called()
                self.assertIn("指令执行失败", output.getvalue())

    def test_sleep_never_reaches_business_handler(self):
        handler = Mock()
        controller = VoiceController(VoiceConfig(), handler)
        with patch("voice_control.controller.play_audio") as play, redirect_stdout(io.StringIO()):
            controller._handle_command("再见小南", Path("goodbye.wav"))
        handler.assert_not_called()
        play.assert_called_once()

    def test_failed_action_does_not_prevent_next_command(self):
        handler = Mock(side_effect=[CommandResult(False, "失败"), CommandResult(True)])
        controller = VoiceController(VoiceConfig(), handler)
        with patch("voice_control.controller.play_audio") as play, redirect_stdout(io.StringIO()):
            controller._handle_command("拍照", Path("takephoto.wav"))
            controller._handle_command("测量", Path("measure.wav"))
        self.assertEqual(play.call_count, 2)
        self.assertEqual(handler.call_args.args, (VoiceCommand.MEASURE,))


if __name__ == "__main__":
    unittest.main()
