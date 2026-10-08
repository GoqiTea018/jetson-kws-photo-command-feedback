"""离线语音控制的公开接口；导入时不启动硬件或识别进程。"""

from .voice_control import CommandHandler, CommandResult, VoiceCommand, VoiceConfig, VoiceController

__all__ = ["VoiceCommand", "CommandHandler", "CommandResult", "VoiceConfig", "VoiceController"]
