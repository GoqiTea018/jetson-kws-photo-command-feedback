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

if __package__:
    from .app_config import (
        COMMAND_SOUNDS, DEFAULT_SHERPA_DIR, MIC_DEVICE, PLAYBACK_SETTLE_SECONDS,
        PROJECT_DIR, SLEEP_KEYWORD, SPEAKER_DEVICE, WAKE_KEYWORD,
        KEYWORD_COMMANDS, VoiceCommand,
    )
    from .command_handler import CommandHandler, CommandResult
    from .audio_capture import configure_capture_route
    from .audio_feedback import play_audio
    from .kws_engine import realtime_command
else:  # 保持 python main.py / live_photo.py 的原有启动方式。
    from app_config import (
        COMMAND_SOUNDS, DEFAULT_SHERPA_DIR, MIC_DEVICE, PLAYBACK_SETTLE_SECONDS,
        PROJECT_DIR, SLEEP_KEYWORD, SPEAKER_DEVICE, WAKE_KEYWORD,
        KEYWORD_COMMANDS, VoiceCommand,
    )
    from command_handler import CommandHandler, CommandResult
    from audio_capture import configure_capture_route
    from audio_feedback import play_audio
    from kws_engine import realtime_command


KEYWORD_EVENT_PATTERN = re.compile(r'\{[^{}]*"keyword"\s*:\s*"([^"]+)"[^{}]*\}')


class ListenerStopped(Exception):
    """主动停止监听的内部控制信号，不表示识别或业务失败。"""


def wait_for_keyword(
    command: list[str], keywords: Collection[str], env: Mapping[str, str] | None = None,
    stop_event: Event | None = None,
) -> str:
    """等待 KWS 事件并释放麦克风；Linux 管道轮询允许无语音时停止。

    stop_event 由服务拥有，调用方只应通过 VoiceController.stop() 设置。
    无论识别成功、主动停止或读取异常，finally 都负责回收子进程。
    """
    if stop_event is not None and stop_event.is_set():
        raise ListenerStopped
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )
    # 保留原始字节，避免读取边界截断中文 UTF-8 或跨块的 JSON 事件。
    recent = b""
    volume_pending = b""
    show_volume = env is not None and "SHERPA_KWS_VOLUME" in env
    try:
        while True:
            if stop_event is not None:
                if stop_event.is_set():
                    raise ListenerStopped
                # Jetson/Linux 支持 select 监听管道；避免 os.read 无限阻塞，
                # 使主应用在没有识别到关键词时也可结束语音服务。
                if not select.select([process.stderr], [], [], 0.1)[0]:
                    continue
            chunk = os.read(process.stderr.fileno(), 4096)
            if not chunk:
                detail = recent.decode("utf-8", errors="replace")[-1200:]
                raise RuntimeError(f"实时 KWS 意外退出:\n{detail}")
            if show_volume:
                # 只转发完整的音量行；跨块的日志保留到下一次读取。
                volume_pending += chunk
                lines = volume_pending.split(b"\n")
                volume_pending = lines.pop()[-16000:]
                for line in lines:
                    if line.startswith(b"[volume]"):
                        print(line.decode("utf-8", errors="replace"), flush=True)
            recent = (recent + chunk)[-16000:]
            matches = [
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
    """单个语音服务的运行参数；默认值沿用当前 Jetson 的已用配置。"""

    sherpa_dir: Path = DEFAULT_SHERPA_DIR
    mic_device: str = MIC_DEVICE
    speaker_device: str = SPEAKER_DEVICE
    once: bool = False
    volume_meter: bool = False


class VoiceController:
    """封装监听生命周期，业务处理函数由调用方传入。

    run() 是阻塞调用，应放在 ECSnake 的工作线程中。每次识别后先释放
    麦克风，再等待业务完成并播放反馈，防止提示音被再次识别。
    不传 command_handler 时仅演示提示音，不表示执行了相机或机械动作。
    """

    def __init__(self, config: VoiceConfig, command_handler: CommandHandler | None = None):
        self.config = config
        self.command_handler = command_handler
        self._stop_event = Event()

    def stop(self) -> None:
        """可跨线程请求停止；当前业务调用或音频播放完成后再退出。

        正在等待关键词时最多约 100 ms 发现停止请求，然后回收 KWS。
        业务处理函数自身必须设置超时；stop() 不强行中断相机操作。
        """
        self._stop_event.set()

    def _handle_command(self, keyword: str, sound_path: Path) -> None:
        """休眠是语音内部指令；真实业务只在确认成功后播放对应音频。"""
        voice_command = KEYWORD_COMMANDS[keyword]
        if voice_command != VoiceCommand.SLEEP and self.command_handler is not None:
            try:
                result = self.command_handler(voice_command)
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
    """命令行只负责解析参数；应用集成时直接使用 VoiceController。"""
    parser = argparse.ArgumentParser(description="先用‘楠机楠机’唤醒，再识别指令并播放语音提示")
    parser.add_argument("--sherpa-dir", type=Path, default=DEFAULT_SHERPA_DIR)
    parser.add_argument("--mic-device", default=MIC_DEVICE)
    parser.add_argument("--speaker-device", default=SPEAKER_DEVICE)
    parser.add_argument("--once", action="store_true", help="识别并播放一次后退出，便于验收")
    parser.add_argument("--volume-meter", action="store_true", help="同时打印 KWS 输入音量，需先运行 build_volume_meter.py")
    args = parser.parse_args(argv)
    controller = VoiceController(VoiceConfig(**vars(args)))
    try:
        controller.run()
    except FileNotFoundError as error:
        parser.error(str(error))


def _run_listener(controller: VoiceController) -> None:
    """保持原有唤醒/指令双循环；不在此模块导入 ECSnake 或 Qt。"""
    config = controller.config

    root = PROJECT_DIR
    greeting = root / "sounds/nanji.wav"
    sounds = {keyword: root / "sounds" / filename for keyword, filename in COMMAND_SOUNDS.items()}
    sherpa_dir = config.sherpa_dir.expanduser().resolve()
    # 未启用音量时，继续调用原版可执行文件与原有参数。
    meter_options = {"volume_meter": True} if config.volume_meter else {}
    wake_command = realtime_command(sherpa_dir, root / "wake_keywords.txt", config.mic_device, **meter_options)
    command_listener_command = realtime_command(sherpa_dir, root / "command_keywords.txt", config.mic_device, **meter_options)
    # 仅虚拟左声道设备加载项目 ALSA 配置；显式设备沿用系统配置。
    env = None
    if config.mic_device == MIC_DEVICE:
        env = {**os.environ, "ALSA_CONFIG_PATH": str(root / "kws-left.asoundrc")}
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
