"""封装 sherpa-onnx 模型检查及命令构建，供实时监听和 WAV 检查共用。"""

import re
import subprocess
from pathlib import Path


MODEL_NAME = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
MODEL_PARTS = ("encoder", "decoder", "joiner")
MODEL_SUFFIX = "epoch-13-avg-2-chunk-16-left-64.onnx"


def model_files(
    sherpa_dir: Path, keywords: Path, binary_name: str = "sherpa-onnx-keyword-spotter",
) -> tuple[Path, dict[str, Path], Path]:
    """检查可执行文件、模型部件和关键词词表，返回已验证的路径。

    keywords 是关键词文件路径，不是识别结果集合。使用当前板卡已用
    模型，不自动下载或替换模型；缺失文件/token 时在启动前明确报错。
    """
    model = sherpa_dir / MODEL_NAME
    binary = sherpa_dir / "build/bin" / binary_name
    parts = {part: model / f"{part}-{MODEL_SUFFIX}" for part in MODEL_PARTS}
    tokens = model / "tokens.txt"
    required = [binary, tokens, keywords, *parts.values()]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少文件:\n" + "\n".join(missing))

    available = {line.split()[0] for line in tokens.read_text(encoding="utf-8").splitlines() if line.strip()}
    # @ 后是显示名称，不属于模型 token；注释行不参与词表检查。
    required_tokens = {
        token
        for line in keywords.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        for token in line.split("@", 1)[0].split()
    }
    missing_tokens = required_tokens - available
    if missing_tokens:
        raise ValueError(f"模型词表不包含关键词 token: {', '.join(sorted(missing_tokens))}")
    return binary, parts, tokens


def _keyword_command(sherpa_dir: Path, keywords: Path, binary_name: str) -> list[str]:
    """封装两种识别入口共有的模型参数；输入 WAV/设备由调用方追加。"""
    binary, parts, tokens = model_files(sherpa_dir, keywords, binary_name)
    return [
        str(binary),
        *(f"--{part}={parts[part]}" for part in MODEL_PARTS),
        f"--tokens={tokens}",
        f"--keywords-file={keywords}",
    ]


def recognize_photo(sherpa_dir: Path, keywords: Path, wav: Path) -> tuple[str, bool]:
    """单词诊断入口：返回原始日志和是否识别到拍照，不执行拍照。

    stdout/stderr 都可能包含 KWS 事件，因此合并检查；业务层实时
    指令转换统一在 app_config 中完成，这里只保留 WAV 诊断用途。
    """
    command = _keyword_command(sherpa_dir, keywords, "sherpa-onnx-keyword-spotter")
    result = subprocess.run(
        [*command, str(wav)],
        check=True,
        text=True,
        capture_output=True,
    )
    output = result.stdout + result.stderr
    found = bool(re.search(r'"keyword"\s*:\s*"拍照"', output))
    return output, found


def realtime_command(
    sherpa_dir: Path, keywords: Path, device: str, volume_meter: bool = False,
) -> list[str]:
    """仅构建监听命令，不启动子进程；生命周期由语音服务负责。

    device 是提供给 KWS 的单声道输入设备；音量诊断仍使用同一条
    采集流，只切换到预先构建的 -volume 可执行文件。
    """
    binary_name = "sherpa-onnx-keyword-spotter-alsa" + ("-volume" if volume_meter else "")
    command = _keyword_command(sherpa_dir, keywords, binary_name)
    return [*command, device]
