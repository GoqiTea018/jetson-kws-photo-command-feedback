"""语音业务的公开接口；导入时不启动 ALSA、KWS 或相机。"""

from .config import VoiceCommand
from .command_handler import CommandHandler, CommandResult
from .controller import VoiceConfig, VoiceController

__all__ = ["VoiceCommand", "CommandHandler", "CommandResult", "VoiceConfig", "VoiceController"]
