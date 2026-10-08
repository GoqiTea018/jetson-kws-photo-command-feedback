"""在 Jetson 构建带音量日志的 KWS 副本，保留原源码和原可执行文件。"""
import argparse
import shutil
import subprocess
from pathlib import Path

if __package__ and "." in __package__:
    from ..voice_control.config import DEFAULT_SHERPA_DIR
else:
    from voice_control.config import DEFAULT_SHERPA_DIR

METER_CODE = r"""
    // 统计识别使用的同一份单声道数据，不修改样本、不另开 ALSA 设备。
    if (show_volume) {
      for (float sample : samples) {
        sum_squares += static_cast<double>(sample) * sample;
        peak = std::max(peak, std::abs(sample));
        clipped += std::abs(sample) >= 32000.0f / 32768.0f;
      }
      sample_count += samples.size();
      if (sample_count >= expected_sample_rate / 2) {
        const double rms = std::sqrt(sum_squares / sample_count);
        const double dbfs = rms > 0 ? 20 * std::log10(rms) : -INFINITY;
        fprintf(stderr, "[volume] RMS=%.1f%% peak=%.1f%% dBFS=%.1f clip=%.2f%%\n",
                rms * 100, peak * 100, dbfs, 100.0 * clipped / sample_count);
        fflush(stderr);
        sum_squares = 0;
        peak = 0;
        sample_count = clipped = 0;
      }
    }
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sherpa-dir", type=Path, default=DEFAULT_SHERPA_DIR)
    args = parser.parse_args()
    sherpa_dir = args.sherpa_dir.expanduser().resolve()
    source = sherpa_dir / "sherpa-onnx/csrc/sherpa-onnx-keyword-spotter-alsa.cc"
    binary = sherpa_dir / "build/bin/sherpa-onnx-keyword-spotter-alsa"
    destination = binary.with_name(binary.name + "-volume")
    original_source = source.read_bytes()
    # 使用独立备份，失败时也恢复原版；不覆盖原版 KWS 的日常使用入口。
    backup = binary.with_name(binary.name + ".volume-backup")
    if backup.exists():
        raise RuntimeError(f"备份已存在，请先检查: {backup}")
    text = original_source.decode("utf-8")
    anchor = "    const std::vector<float> &samples = alsa.Read(chunk);"
    if text.count(anchor) != 1 or text.count("  while (!stop) {") != 1:
        raise RuntimeError("KWS 源码版本不匹配，未进行修改")
    text = text.replace("#include <algorithm>", "#include <algorithm>\n#include <cmath>")
    text = text.replace("  while (!stop) {", """  // 环境变量启用日志；默认识别行为保持不变。
  const bool show_volume = std::getenv("SHERPA_KWS_VOLUME") != nullptr;
  double sum_squares = 0;
  float peak = 0;
  int64_t sample_count = 0, clipped = 0;
  while (!stop) {""")
    text = text.replace(anchor, anchor + METER_CODE)
    shutil.copy2(binary, backup)
    try:
        source.write_text(text, encoding="utf-8")
        subprocess.run(["cmake", "--build", str(sherpa_dir / "build"),
                        "--target", "sherpa-onnx-keyword-spotter-alsa", "-j2"], check=True)
        shutil.copy2(binary, destination)
    finally:
        source.write_bytes(original_source)
        shutil.copy2(backup, binary)
        backup.unlink()
    print(f"音量显示专用程序: {destination}")


if __name__ == "__main__":
    main()
