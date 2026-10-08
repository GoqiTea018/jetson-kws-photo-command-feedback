"""Hardware-free checks for wake gating and event parsing."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from threading import Event
from unittest.mock import MagicMock, patch

import live_photo


class LivePhotoTests(unittest.TestCase):
    def test_stop_without_keyword_releases_listener(self):
        process = MagicMock()
        process.poll.return_value = None
        stop_event = Event()

        def poll(*args):
            stop_event.set()
            return [], [], []

        with patch.object(live_photo.subprocess, "Popen", return_value=process), patch.object(
            live_photo.select, "select", side_effect=poll
        ), patch.object(live_photo.os, "read") as read:
            with self.assertRaises(live_photo.ListenerStopped):
                live_photo.wait_for_keyword(["kws"], {"楠机楠机"}, stop_event=stop_event)
        read.assert_not_called()
        process.terminate.assert_called_once()
        process.stderr.close.assert_called_once()

    def test_listener_kills_process_if_terminate_times_out(self):
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [live_photo.subprocess.TimeoutExpired("kws", 3), 0]
        with patch.object(live_photo.subprocess, "Popen", return_value=process), patch.object(
            live_photo.os, "read", return_value='{"keyword":"拍照"}'.encode("utf-8")
        ):
            self.assertEqual(live_photo.wait_for_keyword(["kws"], {"拍照"}), "拍照")
        process.kill.assert_called_once()
        process.stderr.close.assert_called_once()

    def test_command_event_does_not_satisfy_wake_listener(self):
        process = MagicMock()
        process.stderr.fileno.return_value = 3
        process.poll.return_value = None
        with patch.object(live_photo.subprocess, "Popen", return_value=process), patch.object(
            live_photo.os, "read", side_effect=[
                '{"keyword":"拍照"}'.encode("utf-8"),
                '{"keyword":"楠机楠机"}'.encode("utf-8"),
            ]
        ) as read:
            result = live_photo.wait_for_keyword(["kws"], {"楠机楠机"})
        self.assertEqual(result, "楠机楠机")
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
        with patch.object(live_photo.subprocess, "Popen", return_value=process), patch.object(
            live_photo.os, "read", side_effect=chunks
        ), redirect_stdout(io.StringIO()) as output:
            keyword = live_photo.wait_for_keyword(["kws"], {"拍照"}, {"SHERPA_KWS_VOLUME": "1"})
        self.assertEqual(keyword, "拍照")
        self.assertEqual(output.getvalue(), "[volume] RMS=1.0% peak=2.0% dBFS=-40.0 clip=0.00%\n")
        process.terminate.assert_called_once()

    def test_longer_command_wins_when_events_arrive_together(self):
        process = MagicMock()
        process.stderr.fileno.return_value = 3
        process.poll.return_value = None
        events = '{"keyword":"录像"}\n{"keyword":"停止录像"}'.encode("utf-8")
        with patch.object(live_photo.subprocess, "Popen", return_value=process), patch.object(
            live_photo.os, "read", return_value=events
        ):
            result = live_photo.wait_for_keyword(["kws"], live_photo.COMMAND_SOUNDS)
        self.assertEqual(result, "停止录像")

    def test_wake_precedes_each_command_and_playback(self):
        for keyword, filename in live_photo.COMMAND_SOUNDS.items():
            with self.subTest(keyword=keyword):
                steps = []

                def wait(command, keywords, env, stop_event=None):
                    if "楠机楠机" in keywords:
                        steps.append(("wait", "楠机楠机"))
                        return "楠机楠机"
                    steps.append(("wait", "command"))
                    return keyword

                def play(sound, device):
                    steps.append(("play", sound.name))

                with patch.object(sys, "argv", ["main.py", "--once"]), patch.object(
                    live_photo, "realtime_command", side_effect=lambda directory, keywords, device: keywords.name
                ), patch.object(live_photo, "configure_capture_route"), patch.object(
                    live_photo, "wait_for_keyword", side_effect=wait
                ), patch.object(live_photo, "play_audio", side_effect=play):
                    with redirect_stdout(io.StringIO()) as output:
                        live_photo.main()

                self.assertEqual(steps, [
                    ("wait", "楠机楠机"),
                    ("play", "nanji.wav"),
                    ("wait", "command"),
                    ("play", filename),
                ])
                self.assertIn(f"识别到指令“{keyword}”", output.getvalue())

    def test_one_wake_accepts_multiple_commands(self):
        steps = []
        commands = iter(("拍照", "测量"))

        def wait(command, keywords, env, stop_event=None):
            if "楠机楠机" in keywords:
                steps.append("wake")
                return "楠机楠机"
            try:
                keyword = next(commands)
            except StopIteration:
                raise KeyboardInterrupt
            steps.append(keyword)
            return keyword

        def play(sound, device):
            steps.append(sound.name)

        with patch.object(sys, "argv", ["main.py"]), patch.object(
            live_photo, "realtime_command", side_effect=lambda directory, keywords, device: keywords.name
        ), patch.object(live_photo, "configure_capture_route"), patch.object(
            live_photo, "wait_for_keyword", side_effect=wait
        ), patch.object(live_photo, "play_audio", side_effect=play), patch.object(
            live_photo.time, "sleep"
        ):
            with redirect_stdout(io.StringIO()) as output:
                live_photo.main()

        self.assertEqual(steps, ["wake", "nanji.wav", "拍照", "takephoto.wav", "测量", "measure.wav"])
        self.assertEqual(output.getvalue().count("继续监听指令"), 2)

    def test_goodbye_returns_to_wake_listener(self):
        steps = []
        commands = iter(("拍照", "再见楠机", "测量"))
        wake_count = 0

        def wait(command, keywords, env, stop_event=None):
            nonlocal wake_count
            if "楠机楠机" in keywords:
                wake_count += 1
                steps.append("wake")
                return "楠机楠机"
            try:
                keyword = next(commands)
            except StopIteration:
                raise KeyboardInterrupt
            steps.append(keyword)
            return keyword

        with patch.object(sys, "argv", ["main.py"]), patch.object(
            live_photo, "realtime_command", side_effect=lambda directory, keywords, device: keywords.name
        ), patch.object(live_photo, "configure_capture_route"), patch.object(
            live_photo, "wait_for_keyword", side_effect=wait
        ), patch.object(live_photo, "play_audio", side_effect=lambda sound, device: steps.append(sound.name)), patch.object(
            live_photo.time, "sleep"
        ):
            with redirect_stdout(io.StringIO()) as output:
                live_photo.main()

        self.assertEqual(wake_count, 2)
        self.assertEqual(steps, [
            "wake", "nanji.wav", "拍照", "takephoto.wav",
            "再见楠机", "goodbye.wav", "wake", "nanji.wav", "测量", "measure.wav",
        ])
        self.assertIn("已退出指令模式，重新等待唤醒", output.getvalue())


if __name__ == "__main__":
    unittest.main()
