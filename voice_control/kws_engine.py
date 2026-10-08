"""封装 sherpa-onnx 模型检查及命令构建，供实时监听和 WAV 检查共用。"""

import re
import subprocess
from pathlib import Path


MODEL_NAME = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"  # sherpa_dir 下的模型目录名。
MODEL_PARTS = ("encoder", "decoder", "joiner")  # 音频编码、解码和联合计算的三个模型部件。
MODEL_SUFFIX = "epoch-13-avg-2-chunk-16-left-64.onnx"  # 三个部件共用的文件名后缀。


def model_files(
    sherpa_dir: Path, keywords: Path, binary_name: str = "sherpa-onnx-keyword-spotter",
) -> tuple[Path, dict[str, Path], Path]:
    """检查可执行文件、模型部件和关键词词表，返回对应路径。

    sherpa_dir 是源码/构建/模型根目录，binary_name 是程序文件名。
    返回 (程序路径, {模型部件名: ONNX 路径}, tokens.txt 路径)。
    keywords 是关键词文件路径，不是识别结果集合。使用当前板卡的
    模型，不自动下载或替换模型；缺失文件/token 时在启动前明确报错。
    """
    model = sherpa_dir / MODEL_NAME  # 模型目录的完整路径。
    binary = sherpa_dir / "build/bin" / binary_name  # 要调用的 KWS 程序。
    parts = {part: model / f"{part}-{MODEL_SUFFIX}" for part in MODEL_PARTS}  # 部件名 -> ONNX 文件路径。
    tokens = model / "tokens.txt"  # 模型可识别的音素/符号词表文件。
    required = [binary, tokens, keywords, *parts.values()]  # 启动前必须存在的全部文件。
    missing = [str(path) for path in required if not path.is_file()]  # 缺失文件路径，用于报错。
    if missing:
        raise FileNotFoundError("缺少文件:\n" + "\n".join(missing))

    available = {line.split()[0] for line in tokens.read_text(encoding="utf-8").splitlines() if line.strip()}  # 词表已有 token 集合。
    # @ 后是显示名称，不属于模型 token；注释行不参与词表检查。
    required_tokens = {  # 当前关键词文件使用的 token 集合，不含 @ 后的中文显示名。
        token
        for line in keywords.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        for token in line.split("@", 1)[0].split()
    }
    missing_tokens = required_tokens - available  # 关键词需要但模型词表缺少的 token。
    if missing_tokens:
        raise ValueError(f"模型词表不包含关键词 token: {', '.join(sorted(missing_tokens))}")
    return binary, parts, tokens


def _keyword_command(sherpa_dir: Path, keywords: Path, binary_name: str) -> list[str]:
    """构建实时与 WAV 识别共用的程序和模型参数列表。

    三个参数与 model_files 相同；返回列表第一个元素是程序路径，后续
    元素是 --encoder 等命令行参数，输入 WAV/设备由调用方追加。
    """
    binary, parts, tokens = model_files(sherpa_dir, keywords, binary_name)
    return [
        str(binary),
        *(f"--{part}={parts[part]}" for part in MODEL_PARTS),
        f"--tokens={tokens}",
        f"--keywords-file={keywords}",
    ]


def recognize_photo(sherpa_dir: Path, keywords: Path, wav: Path) -> tuple[str, bool]:
    """单词诊断入口：返回原始日志和是否识别到拍照，不执行拍照。

    sherpa_dir：KWS 根目录；keywords：关键词文件；wav：输入 WAV 路径。
    返回 (output, found)，分别为完整输出文字和是否包含“拍照”事件。
    stdout/stderr 都可能包含 KWS 事件，因此合并检查；业务层实时
    指令转换统一在 config 中完成，这里只保留 WAV 诊断用途。
    """
    command = _keyword_command(sherpa_dir, keywords, "sherpa-onnx-keyword-spotter")
    result = subprocess.run(  # CompletedProcess 保存进程退出结果和输出。
        [*command, str(wav)],
        check=True,
        text=True,
        capture_output=True,
    )
    output = result.stdout + result.stderr  # 合并标准输出与错误输出的日志。
    found = bool(re.search(r'"keyword"\s*:\s*"拍照"', output))  # True 表示有目标识别事件。
    return output, found


def realtime_command(
    sherpa_dir: Path, keywords: Path, device: str, volume_meter: bool = False,
) -> list[str]:
    """仅构建监听命令，不启动子进程；生命周期由语音服务负责。

    sherpa_dir 和 keywords 为模型根目录与关键词文件路径；返回可以
    直接交给 subprocess.Popen 的参数列表，最后一个元素是输入设备。
    device 是提供给 KWS 的单声道输入设备；音量诊断仍使用同一条
    采集流，只切换到预先构建的 -volume 可执行文件。
    """
    binary_name = "sherpa-onnx-keyword-spotter-alsa" + ("-volume" if volume_meter else "")
    command = _keyword_command(sherpa_dir, keywords, binary_name)
    return [*command, device]
