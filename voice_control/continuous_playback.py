"""持续输出 16 kHz 双声道 PCM，空闲时发送静音，避免反复启停 I2S。"""

import array
import queue
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from threading import Event, Thread

from .config import AUDIO_CARD, DMA_INTERFACE, I2S_INTERFACE


def prompt_pcm(path: Path) -> bytes:
    """读取 16-bit 双声道提示音；48 kHz 每三个样本取平均，转换到 16 kHz。

    仅转换内存数据，不改动原 WAV。当前项目提示音为 48 kHz，
    转换后保留原时长，语音播放带宽降为 8 kHz。
    """
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 2 or wav.getsampwidth() != 2:
            raise RuntimeError(f"持续播放需要 16-bit 双声道 WAV：{path}")
        rate = wav.getframerate()
        data = wav.readframes(wav.getnframes())
    if rate == 16000:
        return data
    if rate != 48000:
        raise RuntimeError(f"持续播放只支持 16/48 kHz 提示音：{path}")
    samples = array.array("h", data)
    if sys.byteorder != "little":
        samples.byteswap()
    output = array.array("h")
    for i in range(0, len(samples) - 5, 6):
        output.extend((sum(samples[i:i + 6:2]) // 3,
                       sum(samples[i + 1:i + 6:2]) // 3))
    if sys.byteorder != "little":
        output.byteswap()
    return output.tobytes()


class ContinuousPlayback:
    """一个 aplay 进程播放所有提示音；队列完成事件供业务线程同步等待。"""

    CHUNK_BYTES = 1280  # 16 kHz、16-bit、双声道的 20 ms 数据。

    def __init__(self, device: str):
        self.device = device
        self._requests = queue.Queue()
        self._stop = Event()
        self._error = None
        self._process = None
        self._thread = None
        self._log = None
        self._cache = {}

    def start(self) -> None:
        subprocess.run(["amixer", "-c", AUDIO_CARD, "cset",
                        f"name={I2S_INTERFACE} Mux", DMA_INTERFACE],
                       check=True, stdout=subprocess.DEVNULL)
        self._log = tempfile.TemporaryFile()
        try:
            self._process = subprocess.Popen(
                ["aplay", "-q", "-D", self.device, "-t", "raw", "-f", "S16_LE",
                 "-r", "16000", "-c", "2", "-B", "80000", "-F", "20000"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=self._log, bufsize=0, pipesize=4096,
            )
            self._thread = Thread(target=self._pump, daemon=True)
            self._thread.start()
            time.sleep(0.3)  # 先建立静音输出，再开始录音检查或 KWS。
            self._check()
        except BaseException:
            self.close()
            raise

    def _write(self, data: bytes) -> None:
        # 原始管道可能短写；全部送入 aplay 后才继续。
        view = memoryview(data)
        while view and not self._stop.is_set():
            written = self._process.stdin.write(view)
            if not written:
                raise RuntimeError("持续音频输出管道已关闭")
            view = view[written:]

    def _pump(self) -> None:
        silence = bytes(self.CHUNK_BYTES)
        done = None
        try:
            while not self._stop.is_set():
                try:
                    pcm, done = self._requests.get_nowait()
                except queue.Empty:
                    self._write(silence)
                    continue
                for i in range(0, len(pcm), self.CHUNK_BYTES):
                    self._write(pcm[i:i + self.CHUNK_BYTES])
                # 250 ms 静音超过管道 + ALSA 缓冲时长，确保提示音已实际播完。
                for _ in range(13):
                    self._write(silence)
                done.set()
                done = None
        except Exception as error:
            if not self._stop.is_set():
                self._error = error
                print(f"持续音频输出失败：{error}", file=sys.stderr, flush=True)
        finally:
            if done is not None:
                done.set()

    def _check(self) -> None:
        if self._error is not None or self._process.poll() is not None:
            self._log.seek(0)
            detail = self._log.read().decode(errors="replace").strip()
            raise RuntimeError(f"持续音频输出失败：{detail or self._error}")

    def play(self, path: Path) -> None:
        self._check()
        if path not in self._cache:
            self._cache[path] = prompt_pcm(path)
        done = Event()
        self._requests.put((self._cache[path], done))
        while not done.wait(0.1):
            self._check()
        self._check()

    def close(self) -> None:
        self._stop.set()
        if self._process is not None:
            if self._process.poll() is None:
                self._process.terminate()  # 先解除管道写入阻塞，再等待线程退出。
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            if self._thread is not None:
                self._thread.join(timeout=3)
            self._process.stdin.close()
        if self._log is not None:
            self._log.close()
