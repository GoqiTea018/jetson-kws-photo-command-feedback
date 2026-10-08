"""集中管理资源路径、硬件名称和指令映射。

controller 读取这些配置安排监听和反馈；audio_capture/audio_feedback
读取路由名称控制收放音；KWS 模型文件名另由 kws_engine 管理。
"""
from pathlib import Path
from enum import Enum

# 以本文件位置定位工程，不依赖启动程序时终端所在的目录。
PROJECT_DIR = Path(__file__).resolve().parent.parent  # 工程根目录，Path 对象。
CONFIG_DIR = PROJECT_DIR / "config"                 # 关键词与 ALSA 配置目录。
SOUNDS_DIR = PROJECT_DIR / "sounds"                 # 运行时播放的 WAV 目录。
DEFAULT_SHERPA_DIR = Path("~/Documents/voice/sherpa-onnx").expanduser()  # KWS 构建与模型根目录。

# device 是 ALSA 设备标识，不是麦克风或扬声器的物理引脚编号。
MIC_DEVICE = "kws_left"          # 实时识别输入：双声道硬件中的左声道。
SPEAKER_DEVICE = "hw:APE,0"       # 播放输出：APE 声卡的设备 0。
CAPTURE_DEVICE = "plughw:APE,0"   # 诊断录音输入：保留原始双声道。
AUDIO_CARD = "APE"               # amixer 操作的声卡名称。
I2S_INTERFACE = "I2S2"            # 麦克风/功放连接的 I2S 音频接口。
DMA_INTERFACE = "ADMAIF1"         # ALSA 音频流与 I2S 之间的 AHUB 路由端点。

WAKE_KEYWORD = "楠机楠机"         # 从等待状态进入指令监听的关键词。
SLEEP_KEYWORD = "再见楠机"        # 退出指令模式，重新等待唤醒；不结束程序。
PLAYBACK_SETTLE_SECONDS = 0.5     # 播放结束后再开始下一轮监听的等待时间，单位：秒。


class VoiceCommand(str, Enum):
    """业务动作枚举，将识别词与具体相机/机械实现分开。

    成员名用于代码比较，例如 VoiceCommand.TAKE_PHOTO；成员的 .value
    是英文字符串，例如 "take_photo"，可用于日志或业务消息。
    str, Enum 表示每个成员既有枚举身份，也兼容字符串值。
    """

    TAKE_PHOTO = "take_photo"            # 请求拍照。
    START_RECORDING = "start_recording"  # 请求开始录像。
    STOP_RECORDING = "stop_recording"    # 请求停止录像。
    FREEZE = "freeze"                    # 请求处理画面冻结。
    MEASURE = "measure"                  # 请求测量。
    RESET = "reset"  # 仅保留语义，具体机械动作须在 ECSnake 侧确认。
    SLEEP = "sleep"                      # 语音服务内部的退出指令模式动作。


# 中文识别结果 -> 英文业务动作；新增指令时还需更新关键词文件。
KEYWORD_COMMANDS = {
    "拍照": VoiceCommand.TAKE_PHOTO,
    "录像": VoiceCommand.START_RECORDING,
    "停止录像": VoiceCommand.STOP_RECORDING,
    "冻结": VoiceCommand.FREEZE,
    "测量": VoiceCommand.MEASURE,
    "归零": VoiceCommand.RESET,
    SLEEP_KEYWORD: VoiceCommand.SLEEP,
}
# 业务动作 -> WAV 文件名；完整路径由 SOUNDS_DIR 与文件名拼接。
COMMAND_AUDIO_FILES = {
    VoiceCommand.TAKE_PHOTO: "takephoto.wav",
    VoiceCommand.START_RECORDING: "start_record.wav",
    VoiceCommand.STOP_RECORDING: "stop_record.wav",
    VoiceCommand.FREEZE: "freeze.wav",
    VoiceCommand.MEASURE: "measure.wav",
    VoiceCommand.RESET: "reset.wav",
    VoiceCommand.SLEEP: "goodbye.wav",
}
# 中文识别结果 -> WAV 文件名，供监听服务预先检查音频文件是否存在。
# 从业务映射生成，避免维护两套关键词表。
COMMAND_SOUNDS = {
    keyword: COMMAND_AUDIO_FILES[command]
    for keyword, command in KEYWORD_COMMANDS.items()
}
