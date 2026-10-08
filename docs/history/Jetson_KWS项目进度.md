> 历史阶段记录：文件名、目录与运行命令可能已过时。当前用法见 [README](../../README.md)。

# Jetson 离线语音控制项目

## 1. 项目目标

在 Jetson Orin Nano Super 上实现离线语音控制：

```text
I2S 麦克风
→ KWS 关键词识别
→ 指令映射
→ 执行功能
→ I2S 扬声器提示音反馈
```

计划识别指令：

- 拍照
- 开始录像
- 停止录像
- 冻结
- 测量
- 归零

## 2. 当前目录

```text
~/Documents/voice/
├── sherpa-onnx/     # sherpa-onnx 源码、编译结果、KWS 模型
├── venv/            # Python 虚拟环境
└── test_voice.py    # 当前音频测试脚本
```

## 3. 当前进度

按当前记录已完成（硬件与 GPU 编译细节尚未在本次检查中全部复核）：

- Jetson Orin Nano Super 环境确认
- CUDA 12.6 / cuDNN 9 配置确认
- Python 3.10 虚拟环境创建
- sherpa-onnx 源码下载
- sherpa-onnx GPU 版本编译
- KWS 可执行程序生成；本次通过 SSH 确认文件存在，并用模型示例 WAV 检测到示例关键词
- ALSA / I2S 软件配置已有记录；本次确认 `APE` 录音设备及 `ADMAIF1 Mux = I2S2`。真人录音的左声道已由 KWS 识别出“拍照”
- 中文 KWS 模型下载并解压

当前模型：

```text
sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20
```

第一版计划使用：

```text
encoder-epoch-13-avg-2-chunk-16-left-64.onnx
decoder-epoch-13-avg-2-chunk-16-left-64.onnx
joiner-epoch-13-avg-2-chunk-16-left-64.onnx
```

## 4. 下一步任务

当前接线状态：使用一块 MicroDeer「录音+功放模块」，同板上有播放端 `LRCLK/BCLK/DIN` 和收音端 `WS/SCK/SD`。用户表示已按完整收放音接线图接好，并确认 VCC 可接 5V；麦克风“拍照”单次测试已跑通。完整收放音接线由用户完成，本次尚未从现场验证同时收放时的音质或提示音是否能听到。5V 供电能力不等于 I2S 信号脚可承受 5V，信号电平仍需核对模块资料。

本次已完成的软件准备：

1. 在 Jetson 上使用模型自带的示例 WAV 和关键词文件，确认 KWS 可执行程序能识别示例关键词。
2. 本地编写 `photo_test/`，包含录音、双声道拆分、KWS 调用和“拍照”关键词配置，已通过 SSH 传到 `~/Documents/voice/photo_test/`。关键词 `p āi zh ào @拍照` 的 token 均存在于当前模型词表。
3. 首次真人录音失败的原因已定位：旧代码按 RMS 选中了右声道（RMS 16287.8，削波约 3.3%），它几乎全程为异常信号；左声道 RMS 435.2、无削波。把同一次录音的左声道交给 Jetson KWS 后识别到三次“拍照”。已修复代码为分别保存和检测两声道，并用旧原始 WAV 重跑得到 `[识别] 拍照（左声道）`。新代码的现场录音路径仍需再跑一次确认。
4. 用户反馈单次“拍照”识别已跑通。新增 `photo_test/live_photo.py`：调用 Jetson 现有 ALSA 实时 KWS 程序持续监听，检测到“拍照”后打印 `识别到指令“拍照”`，停止监听并播放中文语音 `sounds/photo_success.wav`，播完恢复监听。提示音由本地已有中文系统语音生成并传到 Jetson；Jetson `aplay` 播放命令返回成功。真人触发后的终端提示及扬声器发声仍待现场闭环验收。

当前下一步：

1. 在 Jetson 运行 `cd ~/Documents/voice/photo_test && ~/Documents/voice/venv/bin/python live_photo.py --once`，说“拍照”，检查终端是否打印指定提示、扬声器是否能听到“拍照成功”，且只触发一次。
2. 单次闭环通过后运行 `~/Documents/voice/venv/bin/python live_photo.py` 持续监听；多次说词，观察是否漏识别、重复触发或提示音回灌。
3. 稳定后再扩展其余五词；相机及其他控制硬件到位后逐项接入真实功能。

本地先编写可移植的指令逻辑和配置；需要设备的录音、播放和实时识别在 Jetson 上验证。通过 SSH 传输源码、关键词文件和提示音到 `~/Documents/voice/` 的应用子目录，保留已有的 `sherpa-onnx/` 与 `venv/`，不要传输本地虚拟环境。

建议后续代码结构：

```text
voice/
├── kws_test.py
├── audio_capture.py
├── command_handler.py
├── main.py
├── models/
└── sounds/
```

## 5. 当前阶段目标

用户反馈单次“拍照”识别已跑通；当前验收目标为持续监听后的语音反馈闭环：

```text
说“拍照” → 终端输出“识别到指令‘拍照’” → 扬声器说“拍照成功”
```

随后完成多次触发的稳定性验收：

```text
连续运行中多次说“拍照”
→ 每次只触发一次
→ 播放提示音时不重新触发
```

目前的“拍照成功”只是语音反馈，尚未调用相机拍照。相机及其他控制功能要在硬件到位后集成。
