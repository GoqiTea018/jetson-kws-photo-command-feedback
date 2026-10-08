"""语音业务的公开接口；导入时不启动 ALSA、KWS 或相机。"""

from .config import VoiceCommand
from .command_handler import CommandHandler, CommandResult
from .controller import VoiceConfig, VoiceController

# 包对外提供的五个名称；调用方无需知道各类具体存放在哪个模块。
__all__ = ["VoiceCommand", "CommandHandler", "CommandResult", "VoiceConfig", "VoiceController"]
