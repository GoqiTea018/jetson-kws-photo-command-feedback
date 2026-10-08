"""与相机、Qt 和 ALSA 无关的业务结果契约，供 ECSnake 适配层使用。"""

from dataclasses import dataclass
from typing import Protocol

if __package__:
    from .app_config import VoiceCommand
else:
    from app_config import VoiceCommand


@dataclass(frozen=True)
class CommandResult:
    """动作最终结果，不能用“请求已发送”替代成功。

    success=True 表示适配层已确认动作完成；拍照应确认文件保存成功。
    message 用于终端说明失败原因，不会自动转换成语音。
    """

    success: bool
    message: str = ""


class CommandHandler(Protocol):
    """在语音工作线程中执行并等待最终结果的可调用接口。

    ECSnake 的适配层应通过 Qt queued signal 将请求送到 GUI 线程，
    在语音线程等待完成/失败信号并设置超时，最后返回 CommandResult。
    不可在 GUI 线程阻塞等待，也不可从语音线程直接操作 Qt 控件。
    未实现的动作应返回失败；不要将 take_photo() 的 None 当作成功。
    """

    def __call__(self, command: VoiceCommand) -> CommandResult:
        ...
