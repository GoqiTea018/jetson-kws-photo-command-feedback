"""与相机、Qt 和 ALSA 无关的业务结果契约，供 ECSnake 适配层使用。"""

from dataclasses import dataclass
from typing import Protocol

from .config import VoiceCommand


@dataclass(frozen=True)
class CommandResult:
    """动作最终结果，不能用“请求已发送”替代成功。

    success=True 表示适配层已确认动作完成；拍照应确认文件保存成功。
    message 用于终端说明失败原因，不会自动转换成语音。
    dataclass 自动生成初始化函数；frozen=True 禁止修改已创建结果的字段。
    示例：CommandResult(False, "相机未连接")。
    """

    success: bool           # True：动作实际完成；False：未完成或失败。
    message: str = ""       # 业务处理函数提供的说明文字，默认为空字符串。


class CommandHandler(Protocol):
    """在语音工作线程中执行并等待最终结果的可调用接口。

    ECSnake 的适配层应通过 Qt queued signal 将请求送到 GUI 线程，
    在语音线程等待完成/失败信号并设置超时，最后返回 CommandResult。
    不可在 GUI 线程阻塞等待，也不可从语音线程直接操作 Qt 控件。
    未实现的动作应返回失败；不要将 take_photo() 的 None 当作成功。

    Protocol 描述接口形式，不实现相机操作。普通函数或定义了 __call__
    的对象都可作为处理函数，调用形式为 handler(VoiceCommand.TAKE_PHOTO)。
    """

    def __call__(self, command: VoiceCommand) -> CommandResult:
        """接收一个业务动作 command，返回动作最终结果 CommandResult。"""
        ...
