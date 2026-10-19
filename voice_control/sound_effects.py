"""按功能事件播放非语音音效，默认使用第一版 minimal 候选。"""

from enum import Enum
from collections.abc import Callable
from pathlib import Path

from .config import SOUNDS_DIR, SPEAKER_DEVICE, VoiceCommand
from .continuous_playback import ContinuousPlayback


class SoundEvent(str, Enum):
    """业务完成或设备状态变化时使用的音效事件。"""

    TAKE_PHOTO = "takephoto"              # 照片保存完成。
    STARTUP = "startup"                   # 设备初始化完成。
    SHUTDOWN = "shutdown"                 # 关机流程关闭音频设备前。
    START_RECORDING = "start_record"      # 录像启动成功。
    STOP_RECORDING = "stop_record"        # 录像文件保存完成。
    FREEZE = "freeze"                     # 画面进入冻结状态。
    MEASURE_COMPLETE = "measure"          # 测量结果生成完成。
    START_DETECTION = "start_detection"   # 检测模块启动成功。
    STOP_DETECTION = "stop_detection"     # 检测模块停止成功。
    START_RESET = "reset_started"         # 控制器接受并开始执行复位。


# 相对路径以 sounds/ 为起点，也可填写 WAV 的绝对路径。
# 空字符串表示该事件等待选音，调用时跳过播放。
SOUND_FILES: dict[SoundEvent, str] = {
    SoundEvent.TAKE_PHOTO: "tones/candidates/takephoto/01_uisfx_minimal.wav",  # 拍照。
    SoundEvent.STARTUP: "tones/candidates/startup/01_uisfx_minimal.wav",  # 开机。
    SoundEvent.SHUTDOWN: "tones/candidates/shutdown/01_uisfx_minimal.wav",  # 关机。
    SoundEvent.START_RECORDING: "tones/candidates/start_record/01_uisfx_minimal.wav",  # 开始录像。
    SoundEvent.STOP_RECORDING: "tones/candidates/stop_record/01_uisfx_minimal.wav",  # 结束录像。
    SoundEvent.FREEZE: "tones/candidates/freeze/01_uisfx_minimal.wav",  # 冻结画面。
    SoundEvent.MEASURE_COMPLETE: "tones/candidates/measure/01_uisfx_minimal.wav",  # 测量完成。
    SoundEvent.START_DETECTION: "tones/candidates/start_detection/01_uisfx_minimal.wav",  # 开始检测。
    SoundEvent.STOP_DETECTION: "tones/candidates/stop_detection/01_uisfx_minimal.wav",  # 停止检测。
    SoundEvent.START_RESET: "tones/candidates/reset_started/01_uisfx_minimal.wav",  # 开始复位。
}


# 已有完成结果的动作由语音控制器自动触发；None 表示等待实际状态回调接入。
COMMAND_EFFECTS: dict[VoiceCommand, SoundEvent | None] = {
    VoiceCommand.TAKE_PHOTO: SoundEvent.TAKE_PHOTO,
    VoiceCommand.START_RECORDING: SoundEvent.START_RECORDING,
    VoiceCommand.STOP_RECORDING: SoundEvent.STOP_RECORDING,
    VoiceCommand.FREEZE: SoundEvent.FREEZE,
    VoiceCommand.MEASURE: SoundEvent.MEASURE_COMPLETE,
    VoiceCommand.START_DETECTION: SoundEvent.START_DETECTION,
    VoiceCommand.STOP_DETECTION: SoundEvent.STOP_DETECTION,
    VoiceCommand.RESET: None,  # 开始复位等待控制器报告开始状态。
}

# 开始录像、测量与检测先播报状态，再播放确认音；停止录像等动作先播短音。
VOICE_FIRST_COMMANDS = {
    VoiceCommand.START_RECORDING,
    VoiceCommand.MEASURE,
    VoiceCommand.START_DETECTION,
    VoiceCommand.STOP_DETECTION,
}


class SoundEffects:
    """管理音效播放和输出流生命周期。

    默认在首次播放已选音效时启动持续输出流，后续事件共用该流。
    playback 可传入主程序已启动的 ContinuousPlayback，统一播放输出。
    play 可传入同步播放函数，沿用语音控制器当前的音频输出方式。
    play() 等待播放完成，适合在业务工作线程中调用。
    """

    def __init__(
        self, playback: ContinuousPlayback | None = None,
        device: str = SPEAKER_DEVICE,
        play: Callable[[Path], None] | None = None,
    ):
        self._playback = playback
        self._play_callback = play  # 可复用语音控制器的同步播放入口。
        self._owns_playback = playback is None and play is None
        self._device = device

    def play(self, event: SoundEvent | str) -> bool:
        """播放事件音效；播完返回 True，尚未选音返回 False。

        event 接受 SoundEvent 或对应的事件 ID，例如 "takephoto"。
        已配置文件的读取、格式和设备错误交给调用方处理。
        """
        event = SoundEvent(event)
        filename = SOUND_FILES[event]
        if not filename:
            return False
        sound_path = Path(filename)
        if not sound_path.is_absolute():
            sound_path = SOUNDS_DIR / sound_path
        if not sound_path.is_file():
            raise FileNotFoundError(f"音效文件不存在：{sound_path}")

        if self._play_callback is not None:
            self._play_callback(sound_path)
            return True

        if self._playback is None:
            player = ContinuousPlayback(self._device)
            player.start()
            self._playback = player
        self._playback.play(sound_path)
        return True

    def close(self) -> None:
        """释放本类创建的输出流；共享输出流由主程序统一回收。"""
        if self._owns_playback and self._playback is not None:
            self._playback.close()
            self._playback = None

    def __enter__(self) -> "SoundEffects":
        """进入 with 代码块，返回当前音效实例。"""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """离开 with 代码块时释放本类持有的输出流。"""
        self.close()
