"""音效事件的选音、路径解析与播放器生命周期检查。"""

import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from voice_control import sound_effects
from voice_control.continuous_playback import prompt_pcm
from voice_control.sound_effects import SOUND_FILES, SoundEffects, SoundEvent


class SoundEffectsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.sound = self.folder / "selected.wav"
        with wave.open(str(self.sound), "wb") as wav:
            wav.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\x10\x00\x20\x00" * 480)

    def test_all_ten_unselected_events_skip_hardware(self):
        self.assertEqual(len(SoundEvent), 10)
        self.assertEqual(set(SOUND_FILES), set(SoundEvent))
        with patch.dict(SOUND_FILES, {event: "" for event in SoundEvent}), patch.object(
            sound_effects, "ContinuousPlayback"
        ) as factory:
            with SoundEffects() as effects:
                for event in SoundEvent:
                    with self.subTest(event=event):
                        self.assertFalse(effects.play(event))
            factory.assert_not_called()

    def test_selected_events_reuse_stream_and_release_it_once(self):
        with patch.dict(SOUND_FILES, {event: str(self.sound) for event in SoundEvent}), patch.object(
            sound_effects, "ContinuousPlayback"
        ) as factory:
            player = factory.return_value
            player.play.side_effect = prompt_pcm
            effects = SoundEffects(device="test-device")
            with effects:
                for event in SoundEvent:
                    self.assertTrue(effects.play(event.value))
            effects.close()
            factory.assert_called_once_with("test-device")
            player.start.assert_called_once()
            self.assertEqual(player.play.call_count, 10)
            player.close.assert_called_once()

    def test_relative_path_uses_sounds_directory_after_changing_cwd(self):
        player = Mock()
        original = os.getcwd()
        try:
            os.chdir(self.folder.parent)
            with patch.object(sound_effects, "SOUNDS_DIR", self.folder), patch.dict(
                SOUND_FILES, {SoundEvent.TAKE_PHOTO: "selected.wav"}
            ):
                effects = SoundEffects(playback=player)
                self.assertTrue(effects.play(SoundEvent.TAKE_PHOTO))
                player.play.assert_called_once_with(self.sound)
        finally:
            os.chdir(original)

    def test_shared_stream_is_used_and_closed_by_its_owner(self):
        player = Mock()
        with patch.dict(SOUND_FILES, {SoundEvent.STARTUP: str(self.sound)}), patch.object(
            sound_effects, "ContinuousPlayback"
        ) as factory:
            with SoundEffects(playback=player) as effects:
                self.assertTrue(effects.play(SoundEvent.STARTUP))
            factory.assert_not_called()
            player.play.assert_called_once_with(self.sound)
            player.start.assert_not_called()
            player.close.assert_not_called()

    def test_missing_selected_file_reports_path_before_starting_stream(self):
        missing = self.folder / "missing.wav"
        with patch.dict(SOUND_FILES, {SoundEvent.SHUTDOWN: str(missing)}), patch.object(
            sound_effects, "ContinuousPlayback"
        ) as factory:
            with self.assertRaises(FileNotFoundError) as result:
                SoundEffects().play(SoundEvent.SHUTDOWN)
            self.assertIn(str(missing), str(result.exception))
            factory.assert_not_called()

    def test_playback_failure_releases_owned_stream_on_context_exit(self):
        with patch.dict(SOUND_FILES, {SoundEvent.FREEZE: str(self.sound)}), patch.object(
            sound_effects, "ContinuousPlayback"
        ) as factory:
            factory.return_value.play.side_effect = RuntimeError("播放失败")
            with self.assertRaisesRegex(RuntimeError, "播放失败"):
                with SoundEffects() as effects:
                    effects.play(SoundEvent.FREEZE)
            factory.return_value.close.assert_called_once()

    def test_failed_start_can_be_retried(self):
        with patch.dict(SOUND_FILES, {SoundEvent.START_RESET: str(self.sound)}), patch.object(
            sound_effects, "ContinuousPlayback"
        ) as factory:
            failed, ready = Mock(), Mock()
            failed.start.side_effect = RuntimeError("启动失败")
            factory.side_effect = [failed, ready]
            with SoundEffects() as effects:
                with self.assertRaisesRegex(RuntimeError, "启动失败"):
                    effects.play(SoundEvent.START_RESET)
                self.assertTrue(effects.play(SoundEvent.START_RESET))
            ready.start.assert_called_once()
            ready.play.assert_called_once_with(self.sound)
            ready.close.assert_called_once()

    def test_unknown_event_reports_error(self):
        with self.assertRaises(ValueError):
            SoundEffects().play("unknown_event")


if __name__ == "__main__":
    unittest.main()
