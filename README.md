# Jetson 离线唤醒与语音指令反馈

在 Jetson Orin Nano Super 上持续监听 I2S 麦克风。说“楠机楠机”唤醒，扬声器播放 `nanji.wav`（“你好呀，我是楠机”）；播完后可连续说指令，每条指令播放对应提示音。说“再见楠机”后播放 `goodbye.wav`，程序退出指令模式，重新等待“楠机楠机”。未唤醒时指令不会触发播放。识别与播放均在本机完成，运行时无需联网。

| 指令 | 提示音 |
| --- | --- |
| 拍照 | `takephoto.wav` |
| 录像 | `start_record.wav` |
| 停止录像 | `stop_record.wav` |
| 冻结 | `freeze.wav` |
| 测量 | `measure.wav` |
| 归零 | `reset.wav` |
| 再见楠机 | `goodbye.wav`，播放后重新等待唤醒 |

**当前只验证语音指令与反馈，不控制相机或录像，也不会保存照片。**

默认启动会明确显示“提示音演示模式”。既有 WAV 中的成功措辞仅用于演示；终端不再在没有相机动作时打印“拍照成功”。传入真实业务处理函数后，只有该函数确认动作完成，才播放对应提示音。

## 工程结构

根目录只保留启动入口、公开导入入口与说明；运行代码、工具和测试分别管理。

```text
photo_test/
├── main.py                  # 独立启动入口
├── __init__.py              # 供 ECSnake 导入的公开接口
├── __main__.py              # python -m photo_test 入口
├── voice_control/           # 运行代码
│   ├── __init__.py          # 统一导出业务接口
│   ├── controller.py        # 唤醒、监听、动作处理与停止
│   ├── config.py            # 统一指令、设备及资源路径
│   ├── command_handler.py   # 业务处理与完成结果契约
│   ├── kws_engine.py        # 模型检查及识别命令
│   ├── audio_capture.py     # 麦克风收音
│   └── audio_feedback.py    # 扬声器反馈
├── config/                  # 唤醒/指令/诊断关键词及 kws-left.asoundrc
├── sounds/                  # 当前运行使用的八个 WAV 提示音
├── tools/                   # photo_check、build_volume_meter、create_sounds
├── tests/                   # 无硬件回归测试
├── docs/                    # integration.md、volume_meter.md 和 history/
├── skills/                  # 项目背景与编码规范
├── README.md
└── .gitignore
```

`local_assets/` 保存本地生成的音频与诊断录音，已忽略提交；程序不会自动使用这里的提示音。`docs/history/` 是历史记录，旧命令以当前 README 为准。

## 环境与启动

Jetson 独立部署目录：

```text
~/Documents/voice/
├── photo_test/       # 本工程
├── sherpa-onnx/      # 模型、已编译程序及动态库
└── venv/             # 可选 Python 环境
```

需要 Python 3.10 或更新版本、ALSA 工具 `amixer`/`arecord`/`aplay`，以及已编译的 sherpa-onnx KWS。运行代码只使用 Python 标准库。

默认模型为 `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20`，模型目录位于 `sherpa-onnx/` 下，须包含 `tokens.txt` 和 encoder/decoder/joiner 的 `epoch-13-avg-2-chunk-16-left-64.onnx` 文件；可执行程序位于 `build/bin/`。启动时会检查这些文件。

```bash
cd ~/Documents/voice
git clone https://github.com/GoqiTea018/jetson-kws-photo-command-feedback.git photo_test
cd photo_test
python3 main.py --once        # 唤醒并处理一条指令后退出
python3 main.py               # 持续运行
```

如使用已有虚拟环境，将 `python3` 换为 `~/Documents/voice/venv/bin/python`。先说“楠机楠机”，问候语播完再说指令；唤醒一次即可连续使用，说“再见楠机”返回等待唤醒，按 `Ctrl+C` 停止。模型目前用“再见”的音素触发退出，因此单独说“再见”也可能退出指令模式。

默认收音设备是 `kws_left`，播放设备是 `hw:APE,0`。可以传入 `--sherpa-dir`、`--mic-device`、`--speaker-device`；全部选项用 `python3 main.py --help` 查看。从父目录也可使用 `python3 -m photo_test --once`。

## 诊断与开发工具

工具统一从项目根目录使用模块命令运行：

```bash
python3 -m tools.photo_check                              # 录音、拆分并检查“拍照”
python3 -m tools.photo_check --raw-wav /path/to/stereo.wav  # 重查双声道录音
python3 -m tools.photo_check --wav /path/to/mono.wav        # 检查单声道录音
python3 -m tools.build_volume_meter                       # 构建可选音量版 KWS
python3 main.py --volume-meter                            # 显示输入音量
```

音量工具详见 [音量诊断说明](docs/volume_meter.md)。提示音生成工具用 `python -m tools.create_sounds`，需要另外安装 `edge-tts`、配置脚本中的 FFmpeg 路径并联网生成；它不参与 Jetson 的离线运行。保留当前生成设置：48 kHz、双声道、32-bit PCM，输出到 `local_assets/`，确认播放效果后再决定是否替换 `sounds/`。

当前板卡的有效语音在左声道，`hw:APE,0` 直接读单声道会报错；`config/kws-left.asoundrc` 通过双声道硬件采集提供左声道单声道输入。单独检查：

```bash
amixer -c APE cset name='ADMAIF1 Mux' I2S2
ALSA_CONFIG_PATH="$PWD/config/kws-left.asoundrc" arecord -D kws_left -f S16_LE -r 16000 -c 1 -d 3 /tmp/photo-left.wav
amixer -c APE cset name='I2S2 Mux' ADMAIF1
aplay -D hw:APE,0 sounds/nanji.wav
```

## ECSnake 接入

将完整工程目录放入 ECSnake 根目录后，原公开接口保持可用：

```python
from photo_test import CommandResult, VoiceCommand, VoiceConfig, VoiceController
```

在工作线程运行 `VoiceController.run()`，退出时调用 `stop()`。业务处理函数必须等待实际完成后返回 `CommandResult`；失败或未确认结果不会播放成功提示音。Qt 线程要求、录像状态判断和多摄像头拍照条件见 [联动接口说明](docs/integration.md)。“归零”按用户确认保留接口，不接实际机械动作。

## 验证

```bash
python -m unittest discover -s tests -v
python -m compileall -q voice_control tools tests main.py __init__.py __main__.py
```

测试可在 Windows 上运行；真人语音识别、音频播放和实际照片保存仍需 Jetson 现场验收。模型、sherpa-onnx 编译程序和虚拟环境不包含在仓库中。

## Jetson Nano Super 接线

| Jetson Orin Nano Super | 模块 | 作用 |
|---|---|---|
| Pin 2 或 4 | VCC | 5V 供电 |
| Pin 6 | GND | 地 |
| Pin 12 | BCLK / SCK | I2S 位时钟 |
| Pin 35 | LRCLK / WS | 左右声道时钟 |
| Pin 40 | DIN | Jetson 输出到播放器 |
| Pin 38 | SD | 麦克风输出到 Jetson |
