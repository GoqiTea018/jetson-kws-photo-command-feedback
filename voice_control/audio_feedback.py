"""仅负责 I2S 播放；业务是否成功由 command_handler 判断。"""

import subprocess
from pathlib import Path

from .config import AUDIO_CARD, DMA_INTERFACE, I2S_INTERFACE


def play_audio(sound_path: Path, device: str) -> None:
    """同步播放 WAV，aplay 成功退出后返回；不代表业务动作完成。

    调用前须释放 KWS 麦克风。播放设备 device 与录音设备独立配置，
    路由参数继续取 config，避免在业务代码重复硬件常量。
    """
    if not sound_path.is_file():
        raise FileNotFoundError(f"提示音不存在: {sound_path}")

    # 播放方向与收音相反：把 ADMAIF1 输出送往 I2S2。
    subprocess.run(
        ["amixer", "-c", AUDIO_CARD, "cset", f"name={I2S_INTERFACE} Mux", DMA_INTERFACE],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(["aplay", "-D", device, str(sound_path)], check=True)
