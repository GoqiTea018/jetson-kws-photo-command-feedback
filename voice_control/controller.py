"""实时语音入口与可导入服务：先唤醒，再执行指令，最后播放反馈。"""

import argparse
import os
import re
import select
import subprocess
import time
from dataclasses import dataclass
from collections.abc import Collection, Mapping
from pathlib import Path
from threading import Event

from .config import (
    COMMAND_SOUNDS, DEFAULT_SHERPA_DIR, MIC_DEVICE, PLAYBACK_SETTLE_SECONDS,
    CONFIG_DIR, SOUNDS_DIR, SLEEP_KEYWORD, SPEAKER_DEVICE,
    WAKE_KEYWORD, KEYWORD_COMMANDS, VoiceCommand,
)
from .command_handler import CommandHandler, CommandResult
from .audio_capture import configure_capture_route
from .audio_feedback import play_audio
from .kws_engine import realtime_command


# 从 KWS 日志的 JSON 事件中提取 keyword 字段；第 1 个捕获组是中文关键词。
KEYWORD_EVENT_PATTERN = re.compile(r'\{[^{}]*"keyword"\s*:\s*"([^"]+)"[^{}]*\}')


class ListenerStopped(Exception):
    """主动停止监听的内部控制信号，不表示识别或业务失败。"""


def wait_for_keyword(
    command: list[str], keywords: Collection[str], env: Mapping[str, str] | None = None,
    stop_event: Event | None = None,
) -> str:
    """等待 KWS 事件并释放麦克风；Linux 管道轮询允许无语音时停止。

    参数：command 为可执行程序与参数组成的列表，不经过 shell；
    keywords 为本轮允许返回的中文关键词集合；env 为子进程环境变量，
    None 表示继承当前环境；stop_event 为跨线程停止标记。
    返回：匹配到的中文关键词字符串，例如“拍照”。
    stop_event 由服务拥有，调用方通过 VoiceController.stop() 设置。
    无论识别成功、主动停止或读取异常，finally 都负责回收子进程。
    """
    if stop_event is not None and stop_event.is_set():
        raise ListenerStopped
    process = subprocess.Popen(  # KWS 子进程对象，用于读取日志和回收麦克风。
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )
    # 保留原始字节，避免读取边界截断中文 UTF-8 或跨块的 JSON 事件。
    recent = b""          # 最近最多 16000 字节日志，用于查找完整关键词事件。
    volume_pending = b""  # 尚未以换行结束的音量日志字节，等待下一块补齐。
    show_volume = env is not None and "SHERPA_KWS_VOLUME" in env  # 是否转发音量日志。
    try:
        while True:
            if stop_event is not None:
                if stop_event.is_set():
                    raise ListenerStopped
                # Jetson/Linux 支持 select 监听管道；避免 os.read 无限阻塞，
                # 使主应用在没有识别到关键词时也可结束语音服务。
                if not select.select([process.stderr], [], [], 0.1)[0]:
                    continue
            # chunk 是一次读取的原始字节块；4096 是读取上限，不是音频帧数。
            chunk = os.read(process.stderr.fileno(), 4096)
            if not chunk:
                detail = recent.decode("utf-8", errors="replace")[-1200:]  # 末尾日志供定位退出原因。
                raise RuntimeError(f"实时 KWS 意外退出:\n{detail}")
            if show_volume:
                # 只转发完整的音量行；跨块的日志保留到下一次读取。
                volume_pending += chunk
                lines = volume_pending.split(b"\n")  # 拆出的完整行及末尾未完成行。
                volume_pending = lines.pop()[-16000:]
                for line in lines:
                    if line.startswith(b"[volume]"):
                        print(line.decode("utf-8", errors="replace"), flush=True)
            recent = (recent + chunk)[-16000:]
            matches = [  # 当前日志块中同时符合事件格式与允许词集合的关键词。
                event.group(1)
                for event in KEYWORD_EVENT_PATTERN.finditer(recent.decode("utf-8", errors="ignore"))
                if event.group(1) in keywords
            ]
            if matches:
                # 同批事件中优先完整长词，避免“停止录像”被“录像”抢先命中。
                return max(matches, key=len)
    finally:
        # 先回收监听进程、释放麦克风，再允许调用方播放提示音。
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stderr.close()


@dataclass(frozen=True)
class VoiceConfig:
    """语音服务的参数容器，不负责收音、播放或执行业务。

    dataclass 自动生成构造函数，可用 VoiceConfig(once=True) 修改某项配置；
    frozen=True 表示实例创建后配置不可变，避免运行中被其他线程改写。
    """

    sherpa_dir: Path = DEFAULT_SHERPA_DIR  # sherpa-onnx 程序与模型所在的根目录。
    mic_device: str = MIC_DEVICE          # 实时 KWS 使用的 ALSA 输入设备名称。
    speaker_device: str = SPEAKER_DEVICE  # aplay 使用的 ALSA 输出设备名称。
    once: bool = False                    # True：处理一条指令后退出；False：持续监听。
    volume_meter: bool = False            # True：使用音量版 KWS 并打印输入音量。


class VoiceController:
    """封装监听生命周期，业务处理函数由调用方传入。

    职责：管理等待唤醒、连续指令、业务结果反馈和停止请求。
    音频路由交给 audio_capture/audio_feedback，识别命令交给 kws_engine，
    拍照等实际业务交给 command_handler，类本身不实现相机驱动。
    run() 是阻塞调用，应放在 ECSnake 的工作线程中。每次识别后先释放
    麦克风，再等待业务完成并播放反馈，防止提示音被再次识别。
    不传 command_handler 时仅演示提示音，不表示执行了相机或机械动作。
    """

    def __init__(self, config: VoiceConfig, command_handler: CommandHandler | None = None):
        """config 是运行参数；command_handler 是接收 VoiceCommand 的业务函数。"""
        self.config = config                  # 本实例的路径、设备和运行模式。
        self.command_handler = command_handler  # None 表示只演示语音反馈。
        self._stop_event = Event()             # 初始未设置；stop() 设置后各监听循环退出。

    def stop(self) -> None:
        """可跨线程请求停止；当前业务调用或音频播放完成后再退出。

        正在等待关键词时最多约 100 ms 发现停止请求，然后回收 KWS。
        业务处理函数自身必须设置超时；stop() 不强行中断相机操作。
        """
        self._stop_event.set()

    def _handle_command(self, keyword: str, sound_path: Path) -> None:
        """处理中文 keyword，使用 sound_path 播放该动作的反馈；不返回业务结果。

        休眠是语音内部指令；其他动作传给业务函数，确认成功后才播放音频。
        前缀 _ 表示内部方法，调用方应通过 run() 启动完整流程。
        """
        voice_command = KEYWORD_COMMANDS[keyword]  # 中文识别词转换后的业务枚举。
        if voice_command != VoiceCommand.SLEEP and self.command_handler is not None:
            try:
                result = self.command_handler(voice_command)  # 业务最终结果，含 success/message。
                if not isinstance(result, CommandResult) or type(result.success) is not bool:
                    raise TypeError("业务处理函数必须返回 CommandResult，success 必须是 bool")
            except Exception as error:
                # 业务失败不终止语音服务，也不播放已有的成功提示音。
                print(f"指令执行失败：{keyword}：{error}", flush=True)
                return
            if not result.success:
                print(f"指令执行失败：{keyword}：{result.message}", flush=True)
                return
            play_audio(sound_path, self.config.speaker_device)
            print(f"指令执行成功：{keyword}", flush=True)
        else:
            play_audio(sound_path, self.config.speaker_device)
            print(f"提示音播放完成：{keyword}", flush=True)

    def run(self) -> None:
        """持续监听；Ctrl+C/stop() 退出，once 模式处理一条指令后返回。

        一个实例只在一个工作线程运行；停止后新建实例才能重新启动。
        """
        _run_listener(self)


def main(argv: list[str] | None = None) -> None:
    """命令行入口，解析参数后创建并运行 VoiceController。

    argv 是命令行参数列表；None 表示读取启动命令中的参数。
    ECSnake 集成时直接创建 VoiceController，无需调用这个命令行入口。
    """
    parser = argparse.ArgumentParser(description="先用‘楠机楠机’唤醒，再识别指令并播放语音提示")
    parser.add_argument("--sherpa-dir", type=Path, default=DEFAULT_SHERPA_DIR)
    parser.add_argument("--mic-device", default=MIC_DEVICE)
    parser.add_argument("--speaker-device", default=SPEAKER_DEVICE)
    parser.add_argument("--once", action="store_true", help="识别并播放一次后退出，便于验收")
    parser.add_argument("--volume-meter", action="store_true", help="同时打印 KWS 输入音量，需先运行 python -m tools.build_volume_meter")
    args = parser.parse_args(argv)  # argparse.Namespace 保存各命令行选项的值。
    # vars(args) 把参数对象转换成字典，字段名与 VoiceConfig 一一对应。
    controller = VoiceController(VoiceConfig(**vars(args)))
    try:
        controller.run()
    except FileNotFoundError as error:
        parser.error(str(error))


def _run_listener(controller: VoiceController) -> None:
    """服务内部的状态循环：外层等待唤醒，内层连续处理指令。

    controller 是拥有配置、业务函数与停止标记的服务实例。
    睡眠指令只结束内层循环；stop()/Ctrl+C 结束整个监听流程。
    """
    config = controller.config  # 本轮运行使用的不可变配置对象。

    greeting = SOUNDS_DIR / "nanji.wav"  # 唤醒问候语的完整路径。
    sounds = {keyword: SOUNDS_DIR / filename for keyword, filename in COMMAND_SOUNDS.items()}  # 中文指令 -> 完整音频路径。
    sherpa_dir = config.sherpa_dir.expanduser().resolve()  # 展开 ~，转换为绝对路径。
    # 未启用音量时，继续调用原版可执行文件与原有参数。
    meter_options = {"volume_meter": True} if config.volume_meter else {}  # 可选命令构建参数。
    # 两个列表分别加载唤醒词和指令词文件；每次只启动其中一个监听进程。
    wake_command = realtime_command(sherpa_dir, CONFIG_DIR / "wake_keywords.txt", config.mic_device, **meter_options)
    command_listener_command = realtime_command(sherpa_dir, CONFIG_DIR / "command_keywords.txt", config.mic_device, **meter_options)
    # 仅虚拟左声道设备加载项目 ALSA 配置；显式设备沿用系统配置。
    env = None  # KWS 子进程的环境；需要额外配置时复制 os.environ，避免修改主程序环境。
    if config.mic_device == MIC_DEVICE:
        env = {**os.environ, "ALSA_CONFIG_PATH": str(CONFIG_DIR / "kws-left.asoundrc")}
    if config.volume_meter:
        env = {**(env if env is not None else os.environ), "SHERPA_KWS_VOLUME": "1"}
    for sound in (greeting, *sounds.values()):
        if not sound.is_file():
            raise FileNotFoundError(f"提示音不存在: {sound}")

    if controller.command_handler is None:
        print("提示音演示模式：不会执行相机或机械动作；音频内容不代表业务成功。", flush=True)

    try:
        while not controller._stop_event.is_set():
            configure_capture_route()
            print("等待唤醒词‘楠机楠机’；按 Ctrl+C 退出。", flush=True)
            wait_for_keyword(wake_command, {WAKE_KEYWORD}, env, controller._stop_event)
            if controller._stop_event.is_set():
                return
            print("识别到唤醒词“楠机楠机”，播放问候语", flush=True)
            play_audio(greeting, config.speaker_device)
            print("问候语播放完成，请说指令", flush=True)
            # 内层循环维持唤醒状态；退出指令返回外层重新等待唤醒。
            while not controller._stop_event.is_set():
                configure_capture_route()
                keyword = wait_for_keyword(command_listener_command, KEYWORD_COMMANDS, env, controller._stop_event)
                if controller._stop_event.is_set():
                    return
                print(f"识别到指令“{keyword}”", flush=True)
                controller._handle_command(keyword, sounds[keyword])
                if config.once:
                    return
                time.sleep(PLAYBACK_SETTLE_SECONDS)
                if keyword == SLEEP_KEYWORD:
                    print("已退出指令模式，重新等待唤醒", flush=True)
                    break
                print("继续监听指令……", flush=True)
    except (KeyboardInterrupt, ListenerStopped):
        print("\n已停止监听")


if __name__ == "__main__":
    main()
