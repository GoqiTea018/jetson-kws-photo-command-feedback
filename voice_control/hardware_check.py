"""启动前检查 I2S 引脚配置、麦克风输入和扬声器输出。"""

import array
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from .audio_capture import configure_capture_route
from .config import AUDIO_CARD, CONFIG_DIR, DMA_INTERFACE, I2S_INTERFACE, PROJECT_MIC_DEVICES


def _run(command: list[str], env: dict[str, str] | None = None) -> str:
    """执行检查命令并返回日志；超时或非零退出转换为含原因的 RuntimeError。

    command 是不经过 shell 的参数列表；env 为可选子进程环境。
    10 秒超时用于避免设备无法传输数据时卡住启动流程。
    """
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"设备检查无法完成（{command[0]}）：{error}") from error
    if result.returncode:
        raise RuntimeError(f"设备检查失败（{command[0]}）：\n{result.stderr.strip() or result.stdout.strip()}")
    return result.stdout + result.stderr


def check_audio_connections(mic_device: str, speaker_device: str, check_playback: bool = True) -> None:
    """检查音频配置及数据通路，无返回值；明确的配置/设备错误阻止启动。

    mic_device 和 speaker_device 是 ALSA 输入、输出名称，由入口传入。
    工程的左、右、混合输入均检查 I2S2，并录制一秒单声道 PCM；所有设备均尝试
    在 check_playback=True 时播放一秒静音；持续模式已有输出流时跳过此项。
    临时 WAV 在检查结束后删除，不播放提示音。
    无输入信号时提示检查供电和接线；设备无法打开时显示错误原因。
    """
    if not sys.platform.startswith("linux"):
        raise RuntimeError("音频连接检查需要在 Jetson/Linux 上运行。")
    missing = [name for name in ("amixer", "arecord", "aplay") if not shutil.which(name)]
    if missing:
        raise RuntimeError(f"缺少 ALSA 工具：{', '.join(missing)}；请安装 alsa-utils。")
    print("正在检查音频设备……", flush=True)
    # 列举设备的命令失败时输出 ALSA 原因；实际指定设备由后续打开检查。
    _run(["arecord", "-l"])
    _run(["aplay", "-l"])
    env = None  # 其他输入沿用系统配置；工程设备加载双声道采集路由。
    if mic_device in PROJECT_MIC_DEVICES:
        _check_i2s_pins()
        env = {**os.environ, "ALSA_CONFIG_PATH": str(CONFIG_DIR / "kws-left.asoundrc")}
    try:
        configure_capture_route()  # 沿用已有封装：将 I2S2 输入送往 ADMAIF1。
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"无法设置麦克风路由：{error}") from error
    with tempfile.TemporaryDirectory(prefix="voice-hardware-") as directory:
        recording = Path(directory) / "input.wav"  # 一秒诊断录音，仅用于检查输入数据。
        _run(["arecord", "-q", "-D", mic_device, "-f", "S16_LE", "-r", "16000",
              "-c", "1", "-d", "1", str(recording)], env)
        with wave.open(str(recording), "rb") as audio:
            samples = array.array("h", audio.readframes(audio.getnframes()))
        if sys.byteorder != "little":
            samples.byteswap()
        if not samples:
            raise RuntimeError("麦克风没有返回音频数据，请检查 I2S 时钟和设备配置。")
        peak = max(abs(value) for value in samples)  # 录音样本的最大绝对幅度。
        if peak == 0:
            print("未检测到麦克风信号，请检查供电和接线。", flush=True)
    if check_playback:
        _run(["amixer", "-c", AUDIO_CARD, "cset", f"name={I2S_INTERFACE} Mux", DMA_INTERFACE])
        _run(["aplay", "-q", "-D", speaker_device, "-t", "raw", "-f", "S16_LE",
              "-r", "48000", "-c", "2", "-d", "1", "/dev/zero"])


def _check_i2s_pins() -> None:
    """读取当前设备树，检查 Pin 12/35/38/40 的 I2S2 配置。

    无参数和返回值；已知复用错误阻止启动，缺失或不可读时提示无法确认。
    四个引脚分别用于时钟、声道时钟、麦克风输入和扬声器输出。
    """
    tree = Path("/sys/firmware/devicetree/base")  # 内核公开的当前设备树。
    incorrect = []  # 收集确实读取到、但未设置为 I2S2 的引脚。
    unreadable = []  # 无法查询的引脚汇总为一条提示。
    for pin, signal in ((12, "BCLK"), (35, "LRCLK"), (38, "麦克风 SD"), (40, "播放 DIN")):
        try:
            nodes = list(tree.glob(f"**/exp-header-pinmux/hdr40-pin{pin}/nvidia,function"))
            functions = [node.read_bytes().rstrip(b"\x00").decode("ascii") for node in nodes]
        except (OSError, UnicodeError):
            unreadable.append(str(pin))
            continue
        if not functions:
            unreadable.append(str(pin))
        elif any(function != "i2s2" for function in functions):
            incorrect.append(f"Pin {pin} ({signal})={','.join(functions)}")
    if incorrect:
        raise RuntimeError("引脚复用错误：" + "；".join(incorrect)
                           + "。请通过 Jetson-IO 启用 I2S2，并重启 Jetson。")
    if unreadable:
        print(f"无法读取引脚 {', '.join(unreadable)} 的配置，请确认已启用 I2S2。", flush=True)
