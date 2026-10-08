"""共享的词、路径和当前 Jetson 音频参数；模型参数由 kws_engine 管理。"""
from pathlib import Path
from enum import Enum

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_SHERPA_DIR = Path("~/Documents/voice/sherpa-onnx").expanduser()
MIC_DEVICE = "kws_left"
SPEAKER_DEVICE = "hw:APE,0"
CAPTURE_DEVICE = "plughw:APE,0"
AUDIO_CARD = "APE"
I2S_INTERFACE = "I2S2"
DMA_INTERFACE = "ADMAIF1"
WAKE_KEYWORD = "楠机楠机"
SLEEP_KEYWORD = "再见楠机"
PLAYBACK_SETTLE_SECONDS = 0.5


class VoiceCommand(str, Enum):
    """业务层使用的稳定指令名；中文关键词仅用于 KWS 和界面显示。"""

    TAKE_PHOTO = "take_photo"
    START_RECORDING = "start_recording"
    STOP_RECORDING = "stop_recording"
    FREEZE = "freeze"
    MEASURE = "measure"
    RESET = "reset"  # 仅保留语义，具体机械动作须在 ECSnake 侧确认。
    SLEEP = "sleep"


KEYWORD_COMMANDS = {
    "拍照": VoiceCommand.TAKE_PHOTO,
    "录像": VoiceCommand.START_RECORDING,
    "停止录像": VoiceCommand.STOP_RECORDING,
    "冻结": VoiceCommand.FREEZE,
    "测量": VoiceCommand.MEASURE,
    "归零": VoiceCommand.RESET,
    SLEEP_KEYWORD: VoiceCommand.SLEEP,
}
COMMAND_AUDIO_FILES = {
    VoiceCommand.TAKE_PHOTO: "takephoto.wav",
    VoiceCommand.START_RECORDING: "start_record.wav",
    VoiceCommand.STOP_RECORDING: "stop_record.wav",
    VoiceCommand.FREEZE: "freeze.wav",
    VoiceCommand.MEASURE: "measure.wav",
    VoiceCommand.RESET: "reset.wav",
    VoiceCommand.SLEEP: "goodbye.wav",
}
# 保留原有导入入口；由统一业务映射生成，避免维护两套关键词表。
COMMAND_SOUNDS = {
    keyword: COMMAND_AUDIO_FILES[command]
    for keyword, command in KEYWORD_COMMANDS.items()
}
