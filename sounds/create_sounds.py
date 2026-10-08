"""开发机提示音生成工具；输出到 local_assets，不覆盖运行用音频。"""

import asyncio
import edge_tts
import subprocess
import os

# 使用工程根目录定位本地输出，运行位置改变也不会把音频散落到根目录。
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "local_assets")

# 生成语音的文本
TEXT = "你好呀，我是楠机"
VOICE = "zh-CN-XiaoxuanNeural"#xiaoxuan

#中间文件
TEMP_MP3 = os.path.join(OUTPUT_DIR, "speech-temp.mp3")

#生成的音频文件
OUTPUT_WAV = os.path.join(OUTPUT_DIR, "nanji.wav")

# 直接指定 FFmpeg 的实际位置
FFMPEG = r"C:\Users\HP\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"


async def main():

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("正在生成语音...")

    # 1. 微软 TTS
    communicate = edge_tts.Communicate(
        text=TEXT,
        voice=VOICE,
        rate="+0%",
        volume="+0%",
        pitch="+0Hz"
    )

    await communicate.save(TEMP_MP3)

    print("TTS 生成完成")

    # 2. 保留当前用户选择：48kHz / Stereo / 32-bit PCM

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
    asyncio.run(main())
