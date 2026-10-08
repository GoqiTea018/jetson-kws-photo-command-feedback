"""离线语音控制的公开接口；导入时不启动硬件或识别进程。"""

from .app_config import VoiceCommand
from .command_handler import CommandHandler, CommandResult
from .live_photo import VoiceConfig, VoiceController

__all__ = ["VoiceCommand", "CommandHandler", "CommandResult", "VoiceConfig", "VoiceController"]
