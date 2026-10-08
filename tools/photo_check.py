"""诊断工具：现场录音或读取 WAV，分别检查声道中的“拍照”关键词。"""

import argparse
from pathlib import Path

# 支持项目根目录的 tools.photo_check 和父目录的 photo_test.tools.photo_check。
if __package__ and "." in __package__:
    from ..voice_control.config import CAPTURE_DEVICE, CONFIG_DIR, DEFAULT_SHERPA_DIR, PROJECT_DIR
    from ..voice_control.audio_capture import capture_for_kws, split_channels
    from ..voice_control.kws_engine import recognize_photo
else:
    from voice_control.config import CAPTURE_DEVICE, CONFIG_DIR, DEFAULT_SHERPA_DIR, PROJECT_DIR
    from voice_control.audio_capture import capture_for_kws, split_channels
    from voice_control.kws_engine import recognize_photo


def main():
    """解析输入来源并检查关键词；返回退出码 0（识别到）或 1（未识别到）。"""
    parser = argparse.ArgumentParser(description="在 Jetson 上测试关键词‘拍照’")
    parser.add_argument("--sherpa-dir", type=Path, default=DEFAULT_SHERPA_DIR)
    source = parser.add_mutually_exclusive_group()  # --wav 与 --raw-wav 不可同时指定。
    source.add_argument("--wav", type=Path, help="使用已有的单声道 WAV")
    source.add_argument("--raw-wav", type=Path, help="重新检查已有的双声道录音")
    parser.add_argument("--device", default=CAPTURE_DEVICE, help="ALSA 录音设备")
    parser.add_argument("--seconds", type=int, default=8, help="现场录音秒数")
    args = parser.parse_args()  # 录音设备、时长、输入文件和模型目录参数。
    if args.seconds <= 0:
        parser.error("--seconds 必须大于 0")

    if args.wav or args.raw_wav:
        wav = (args.wav or args.raw_wav).expanduser().resolve()  # 用户指定的输入文件绝对路径。
        if not wav.is_file():
            parser.error(f"WAV 不存在: {wav}")
        channels = split_channels(wav) if args.raw_wav else [("指定文件", wav)]  # 待识别的 (显示名, 路径) 列表。
    else:
        wav = PROJECT_DIR / "local_assets" / "photo-test.wav"
        channels = capture_for_kws(wav, args.device, args.seconds)

    keywords = CONFIG_DIR / "photo_keywords.txt"  # 仅含“拍照”的关键词文件路径。
    for name, channel_wav in channels:
        print(f"正在检查{name}声道: {channel_wav}")
        # name 是当前声道显示名，channel_wav 是输入路径；output 是日志，found 是匹配结果。
        output, found = recognize_photo(args.sherpa_dir.expanduser().resolve(), keywords, channel_wav)
        for line in output.splitlines():
            if '"keyword"' in line:
                print(line)
        if found:
            print(f"[识别] 拍照（{name}声道）")
            return 0
    print("[识别] 两个声道均未检测到‘拍照’")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
