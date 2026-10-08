"""开发机提示音生成工具；输出到 local_assets，不覆盖运行用音频。"""

import asyncio
import edge_tts
import subprocess
import os

# 使用工程根目录定位本地输出，运行位置改变也不会把音频散落到根目录。
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 工程根目录字符串。
OUTPUT_DIR = os.path.join(PROJECT_DIR, "local_assets")  # 新生成音频的本地保存目录。

# 生成语音的文本
TEXT = "你好呀，我是楠机"         # 要合成为语音的中文内容。
VOICE = "zh-CN-XiaoxuanNeural"    # edge-tts 使用的中文语音名称。

# 中间 MP3 文件：接收 TTS 输出，转换 WAV 后删除。
TEMP_MP3 = os.path.join(OUTPUT_DIR, "speech-temp.mp3")

# 最终 WAV 文件路径；改变文件名即可生成其他提示音。
OUTPUT_WAV = os.path.join(OUTPUT_DIR, "nanji.wav")

# 直接指定 FFmpeg 的实际位置
FFMPEG = r"C:\Users\HP\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"


async def main():
    """联网合成 TEXT，调用 FFmpeg 转换格式，保存 WAV 并删除中间 MP3。"""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("正在生成语音...")

    # 1. 微软 TTS
    communicate = edge_tts.Communicate(  # TTS 请求对象，负责合成并下载语音。
        text=TEXT,
        voice=VOICE,
        rate="+0%",      # 相对默认语速的增减百分比。
        volume="+0%",    # 相对默认音量的增减百分比。
        pitch="+0Hz"     # 相对默认音高的增减量，单位 Hz。
    )

    await communicate.save(TEMP_MP3)

    print("TTS 生成完成")

    # 2. 保留当前用户选择：48kHz / Stereo / 32-bit PCM
    # -y 允许覆盖生成文件；-ar 采样率 Hz；-ac 声道数；pcm_s32le 为有符号
    # 32-bit 小端 PCM 编码。这里只转换本地生成文件，不修改 sounds 中的运行音频。

    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-i", TEMP_MP3,
            "-ar", "48000",
            "-ac", "2",
            "-c:a", "pcm_s32le",
            OUTPUT_WAV
        ],
        check=True
    )

    # 3. 删除临时 MP3
    if os.path.exists(TEMP_MP3):
        os.remove(TEMP_MP3)

    print()
    print("生成成功")
    print(f"文件：{OUTPUT_WAV}")
    print("采样率：48000 Hz")
    print("声道：Stereo")
    print("格式：32-bit PCM")


if __name__ == "__main__":
    # edge-tts 使用异步接口，由 asyncio.run 创建事件循环并等待 main 完成。
    asyncio.run(main())
