"""Jetson I2S microphone capture for the one-word KWS check."""

import array
import math
import subprocess
import sys
import wave
from pathlib import Path

if __package__:
    from .app_config import AUDIO_CARD, DMA_INTERFACE, I2S_INTERFACE
else:
    from app_config import AUDIO_CARD, DMA_INTERFACE, I2S_INTERFACE


def configure_capture_route() -> None:
    """将 I2S2 麦克风输入送往 ADMAIF1；与播放方向分开配置。"""
    subprocess.run(
        ["amixer", "-c", AUDIO_CARD, "cset", f"name={DMA_INTERFACE} Mux", I2S_INTERFACE],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def record_stereo(path: Path, device: str, seconds: int):
    """Record both I2S slots and display ALSA's live stereo VU meter."""
    print(f"开始录音 {seconds} 秒。请说‘拍照’，观察左/右声道音量条是否随声音变化。", flush=True)
    subprocess.run(
        [
            "arecord", "-D", device, "-f", "S16_LE", "-r", "48000",
            "-c", "2", "-V", "stereo", "-d", str(seconds), str(path),
        ],
        check=True,
    )


def split_channels(source: Path):
    """Save both I2S slots; the louder slot can be invalid digital noise."""
    with wave.open(str(source), "rb") as wav:
        if wav.getnchannels() != 2 or wav.getsampwidth() != 2:
            raise ValueError("录音必须是 16-bit 双声道 PCM WAV")
        rate = wav.getframerate()
        samples = array.array("h", wav.readframes(wav.getnframes()))

    if sys.byteorder != "little":
        samples.byteswap()
    # 双声道 PCM 按左、右交错排列；分别保留，不能只按响度挑选。
    left, right = samples[0::2], samples[1::2]
    if not left:
        raise ValueError("录音文件没有音频数据")

    def rms(channel):
        return math.sqrt(sum(value * value for value in channel) / len(channel))

    outputs = []
    for name, channel_samples in (("左", left), ("右", right)):
        destination = source.with_name(source.stem.removesuffix("-raw") + ("-left.wav" if name == "左" else "-right.wav"))
        level = rms(channel_samples)
        clipped = sum(abs(value) >= 32000 for value in channel_samples) / len(channel_samples)
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

    这里使用原始双声道设备，不使用实时监听的 kws_left；必须分别
    检查两条 I2S 数据槽，异常右声道可能比真实语音更响。
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    # 原始录音用于复查，拆分文件不覆盖原始双声道证据。
    raw = destination.with_name(destination.stem + "-raw.wav")
    configure_capture_route()
    record_stereo(raw, device, seconds)
    channels = split_channels(raw)
    print(f"原始双声道录音: {raw}")
    return channels
