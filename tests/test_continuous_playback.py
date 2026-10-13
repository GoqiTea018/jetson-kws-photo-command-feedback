"""持续音频模式：声道转换、播放流复用和失败后的设备回收。"""

import array
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from voice_control import controller
from voice_control.continuous_playback import ContinuousPlayback, prompt_pcm


class ContinuousPlaybackTests(unittest.TestCase):
    def test_downsample_preserves_channels_and_does_not_edit_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.wav"
            samples = array.array("h", [0, 900, 300, 1200, 600, 1500,
                                       -900, -300, -600, 0, -300, 300])
            with wave.open(str(path), "wb") as wav:
                wav.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
                wav.writeframes(samples.tobytes())
            original = path.read_bytes()
            self.assertEqual(list(array.array("h", prompt_pcm(path))), [300, 1200, -600, 0])
            self.assertEqual(path.read_bytes(), original)

    def test_short_pipe_writes_do_not_drop_samples(self):
        output = bytearray()

        class Pipe:
            def write(self, view):
                output.extend(view[:3])
                return min(3, len(view))

        player = ContinuousPlayback("hw:APE,0")
        from types import SimpleNamespace
        player._process = SimpleNamespace(stdin=Pipe())
        player._write(b"0123456789")
        self.assertEqual(output, b"0123456789")

    def test_controller_reuses_output_and_closes_it_on_failure(self):
        service = controller.VoiceController(controller.VoiceConfig(continuous_audio=True))
        with patch.object(controller, "ContinuousPlayback") as factory, patch.object(
            controller, "check_audio_connections"
        ) as check, patch.object(controller, "_run_listener", side_effect=RuntimeError("listener failed")):
            with self.assertRaisesRegex(RuntimeError, "listener failed"):
                service.run()
            factory.return_value.start.assert_called_once()
            factory.return_value.close.assert_called_once()
            check.assert_called_once_with("kws_left", "hw:APE,0", check_playback=False)
            self.assertIsNone(service._playback)


if __name__ == "__main__":
    unittest.main()
