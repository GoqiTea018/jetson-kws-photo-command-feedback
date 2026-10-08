"""麦克风输入模块：配置 I2S 路由，并提供诊断录音与声道拆分。"""

import array
import math
import subprocess
import sys
import wave
from pathlib import Path

from .config import AUDIO_CARD, DMA_INTERFACE, I2S_INTERFACE


def configure_capture_route() -> None:
    """将 I2S2 麦克风输入送往 ADMAIF1；与播放方向分开配置。"""
    subprocess.run(
        ["amixer", "-c", AUDIO_CARD, "cset", f"name={DMA_INTERFACE} Mux", I2S_INTERFACE],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def record_stereo(path: Path, device: str, seconds: int):
    """录制 48 kHz、16-bit PCM、双声道 WAV，并显示 ALSA 音量条。

    path：录音文件路径；device：ALSA 输入设备名；seconds：录音时长，单位秒。
    同步等待 arecord 完成，无返回值；设备或写入错误由 subprocess 抛出。
    """
    print(f"开始录音 {seconds} 秒。请说‘拍照’，观察左/右声道音量条是否随声音变化。", flush=True)
    subprocess.run(
        [
            "arecord", "-D", device, "-f", "S16_LE", "-r", "48000",
            "-c", "2", "-V", "stereo", "-d", str(seconds), str(path),
        ],
        check=True,
    )


def split_channels(source: Path):
    """将 source 指定的 16-bit 双声道 WAV 拆成两个单声道文件。

    返回 [("左", 左声道路径), ("右", 右声道路径)]，保持原始采样率。
    RMS 和削波比例用于观察输入，不能据此把更响的声道认定为有效语音。
    """
    with wave.open(str(source), "rb") as wav:
        if wav.getnchannels() != 2 or wav.getsampwidth() != 2:
            raise ValueError("录音必须是 16-bit 双声道 PCM WAV")
        rate = wav.getframerate()  # 原 WAV 采样率，单位 Hz。
        samples = array.array("h", wav.readframes(wav.getnframes()))  # 有符号 16-bit PCM 样本数组。

    if sys.byteorder != "little":
        # WAV 样本为小端；在大端主机上先调整字节顺序，再按数值计算。
        samples.byteswap()
    # 双声道 PCM 按左、右交错排列；分别保留，不能只按响度挑选。
    left, right = samples[0::2], samples[1::2]  # 偶数位置是左声道，奇数位置是右声道。
    if not left:
        raise ValueError("录音文件没有音频数据")

    def rms(channel):
        """计算一个声道样本的均方根幅度，单位为 PCM 数值，不是分贝。"""
        return math.sqrt(sum(value * value for value in channel) / len(channel))

    outputs = []  # 保存声道显示名称与输出路径，供 photo_check 逐个识别。
    for name, channel_samples in (("左", left), ("右", right)):
        destination = source.with_name(source.stem.removesuffix("-raw") + ("-left.wav" if name == "左" else "-right.wav"))
        level = rms(channel_samples)  # 当前声道 RMS 幅度。
        clipped = sum(abs(value) >= 32000 for value in channel_samples) / len(channel_samples)  # 近满量程样本占比，范围 0~1。
        print(f"{name}声道 RMS={level:.1f}，削波比例={clipped:.1%}；文件: {destination}")
        with wave.open(str(destination), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(channel_samples.tobytes())
        outputs.append((name, destination))
    return outputs


def capture_for_kws(destination: Path, device: str, seconds: int) -> list[tuple[str, Path]]:
    """诊断录音：保留双声道原始文件，返回左右声道名称及单声道路径。

    destination 是输出文件的基准名，例如 photo-test.wav；实际生成
    photo-test-raw.wav、photo-test-left.wav 和 photo-test-right.wav。
    device 是录音设备名称；seconds 是录音时长，单位秒。
    这里使用原始双声道设备，不使用实时监听的 kws_left；必须分别
    检查两条 I2S 数据槽，异常右声道可能比真实语音更响。
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    # 原始录音用于复查，拆分文件不覆盖原始双声道证据。
    raw = destination.with_name(destination.stem + "-raw.wav")  # 原始双声道文件路径。
    configure_capture_route()
    record_stereo(raw, device, seconds)
    channels = split_channels(raw)  # [(声道名称, 单声道 WAV 路径), ...]。
    print(f"原始双声道录音: {raw}")
    return channels
