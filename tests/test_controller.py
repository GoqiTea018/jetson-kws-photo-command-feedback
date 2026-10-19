"""Hardware-free checks for wake gating and event parsing."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from threading import Event
from unittest.mock import MagicMock, patch

from voice_control import controller
from voice_control.sound_effects import COMMAND_EFFECTS, VOICE_FIRST_COMMANDS


class ControllerTests(unittest.TestCase):
    def setUp(self):
        # CLI 默认使用持续播放；测试中模拟该输出流，避免访问声卡。
        playback_patch = patch.object(controller, "ContinuousPlayback")
        playback = playback_patch.start().return_value
        playback.play.side_effect = lambda sound: controller.play_audio(sound, controller.SPEAKER_DEVICE)
        self.addCleanup(playback_patch.stop)
        check_patch = patch.object(controller, "check_audio_connections")
        check_patch.start()
        self.addCleanup(check_patch.stop)

    def test_stop_without_keyword_releases_listener(self):
        process = MagicMock()
        process.poll.return_value = None
        stop_event = Event()

        def poll(*args):
            stop_event.set()
            return [], [], []

        with patch.object(controller.subprocess, "Popen", return_value=process), patch.object(
            controller.select, "select", side_effect=poll
        ), patch.object(controller.os, "read") as read:
            with self.assertRaises(controller.ListenerStopped):
                controller.wait_for_keyword(["kws"], {"小南小南"}, stop_event=stop_event)
        read.assert_not_called()
        process.terminate.assert_called_once()
        process.stderr.close.assert_called_once()

    def test_listener_kills_process_if_terminate_times_out(self):
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [controller.subprocess.TimeoutExpired("kws", 3), 0]
        with patch.object(controller.subprocess, "Popen", return_value=process), patch.object(
            controller.os, "read", return_value='{"keyword":"拍照"}'.encode("utf-8")
        ):
            self.assertEqual(controller.wait_for_keyword(["kws"], {"拍照"}), "拍照")
        process.kill.assert_called_once()
        process.stderr.close.assert_called_once()

    def test_command_event_does_not_satisfy_wake_listener(self):
        process = MagicMock()
        process.stderr.fileno.return_value = 3
        process.poll.return_value = None
        with patch.object(controller.subprocess, "Popen", return_value=process), patch.object(
            controller.os, "read", side_effect=[
                '{"keyword":"拍照"}'.encode("utf-8"),
                '{"keyword":"小南小南"}'.encode("utf-8"),
            ]
        ) as read:
            result = controller.wait_for_keyword(["kws"], {"小南小南"})
        self.assertEqual(result, "小南小南")
        self.assertEqual(read.call_count, 2)
        process.terminate.assert_called_once()

    def test_volume_lines_cross_chunks_without_interfering_with_keyword(self):
        process = MagicMock()
        process.stderr.fileno.return_value = 3
        process.poll.return_value = None
        chunks = [
            b"[volume] RMS=1.0% peak=",
            b"2.0% dBFS=-40.0 clip=0.00%\n",
            '{"keyword":"拍照"}'.encode("utf-8"),
        ]
        with patch.object(controller.subprocess, "Popen", return_value=process), patch.object(
            controller.os, "read", side_effect=chunks
        ), redirect_stdout(io.StringIO()) as output:
            keyword = controller.wait_for_keyword(["kws"], {"拍照"}, {"SHERPA_KWS_VOLUME": "1"})
        self.assertEqual(keyword, "拍照")
        self.assertEqual(output.getvalue(), "[volume] RMS=1.0% peak=2.0% dBFS=-40.0 clip=0.00%\n")
        process.terminate.assert_called_once()

    def test_longer_command_wins_when_events_arrive_together(self):
        process = MagicMock()
        process.stderr.fileno.return_value = 3
        process.poll.return_value = None
        events = '{"keyword":"录像"}\n{"keyword":"停止录像"}'.encode("utf-8")
        with patch.object(controller.subprocess, "Popen", return_value=process), patch.object(
            controller.os, "read", return_value=events
        ):
            result = controller.wait_for_keyword(["kws"], controller.COMMAND_SOUNDS)
        self.assertEqual(result, "停止录像")

    def test_wake_precedes_each_command_and_playback(self):
        for keyword, filename in controller.COMMAND_SOUNDS.items():
            with self.subTest(keyword=keyword):
                steps = []

                def wait(command, keywords, env, stop_event=None):
                    if "小南小南" in keywords:
                        steps.append(("wait", "小南小南"))
                        return "小南小南"
                    steps.append(("wait", "command"))
                    return keyword

                def play(sound, device):
                    steps.append(("play", sound.name))

                with patch.object(sys, "argv", ["main.py", "--once"]), patch.object(
                    controller, "realtime_command", side_effect=lambda directory, keywords, device: keywords.name
                ), patch.object(controller, "configure_capture_route"), patch.object(
                    controller, "wait_for_keyword", side_effect=wait
                ), patch.object(controller, "play_audio", side_effect=play):
                    with redirect_stdout(io.StringIO()) as output:
                        controller.main()

                expected = [
                    ("wait", "小南小南"),
                    ("play", "xiaonan.wav"),
                    ("wait", "command"),
                ]
                command = controller.KEYWORD_COMMANDS[keyword]
                effect = COMMAND_EFFECTS.get(command)
                if effect is not None and command not in VOICE_FIRST_COMMANDS:
                    expected.append(("play", "01_uisfx_minimal.wav"))
                if filename:
                    expected.append(("play", filename))
                if effect is not None and command in VOICE_FIRST_COMMANDS:
                    expected.append(("play", "01_uisfx_minimal.wav"))
                self.assertEqual(steps, expected)
                self.assertIn(f"识别到指令“{keyword}”", output.getvalue())

    def test_one_wake_accepts_multiple_commands(self):
        steps = []
        commands = iter(("拍照", "测量"))

        def wait(command, keywords, env, stop_event=None):
            if "小南小南" in keywords:
                steps.append("wake")
                return "小南小南"
            try:
                keyword = next(commands)
            except StopIteration:
                raise KeyboardInterrupt
            steps.append(keyword)
            return keyword

        def play(sound, device):
            steps.append(sound.name)

        with patch.object(sys, "argv", ["main.py"]), patch.object(
            controller, "realtime_command", side_effect=lambda directory, keywords, device: keywords.name
        ), patch.object(controller, "configure_capture_route"), patch.object(
            controller, "wait_for_keyword", side_effect=wait
        ), patch.object(controller, "play_audio", side_effect=play), patch.object(
            controller.time, "sleep"
        ):
            with redirect_stdout(io.StringIO()) as output:
                controller.main()

        self.assertEqual(steps, ["wake", "xiaonan.wav", "拍照", "01_uisfx_minimal.wav", "takephoto.wav", "测量", "measure.wav", "01_uisfx_minimal.wav"])
        self.assertEqual(output.getvalue().count("继续监听指令"), 2)

    def test_goodbye_returns_to_wake_listener(self):
        steps = []
        commands = iter(("拍照", "再见小南", "测量"))
        wake_count = 0

        def wait(command, keywords, env, stop_event=None):
            nonlocal wake_count
            if "小南小南" in keywords:
                wake_count += 1
                steps.append("wake")
                return "小南小南"
            try:
                keyword = next(commands)
            except StopIteration:
                raise KeyboardInterrupt
            steps.append(keyword)
            return keyword

        with patch.object(sys, "argv", ["main.py"]), patch.object(
            controller, "realtime_command", side_effect=lambda directory, keywords, device: keywords.name
        ), patch.object(controller, "configure_capture_route"), patch.object(
            controller, "wait_for_keyword", side_effect=wait
        ), patch.object(controller, "play_audio", side_effect=lambda sound, device: steps.append(sound.name)), patch.object(
            controller.time, "sleep"
        ):
            with redirect_stdout(io.StringIO()) as output:
                controller.main()

        self.assertEqual(wake_count, 2)
        self.assertEqual(steps, [
            "wake", "xiaonan.wav", "拍照", "01_uisfx_minimal.wav", "takephoto.wav",
            "再见小南", "goodbye.wav", "wake", "xiaonan.wav", "测量", "measure.wav", "01_uisfx_minimal.wav",
        ])
        self.assertIn("已退出指令模式，重新等待唤醒", output.getvalue())


if __name__ == "__main__":
    unittest.main()
