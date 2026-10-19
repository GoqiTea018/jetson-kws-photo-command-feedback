# Jetson 离线唤醒与语音指令反馈

在 Jetson Orin Nano Super 上持续监听 I2S 麦克风。说“小南小南”唤醒，扬声器播放 `xiaonan.wav`（“你好呀，我是楠机”）；播完后可连续说指令（拍照、录像、停止录像、复位、冻结画面、测量），已配置提示音的指令播放对应音频。说“再见小南”后播放 `goodbye.wav`，程序退出指令模式，重新等待“小南小南”。未唤醒时指令不会触发播放。识别与播放均在本机完成，运行时无需联网。

| 指令 | 提示音 |
| --- | --- |
| 拍照 | `takephoto.wav` |
| 录像 | `start_record.wav` |
| 停止录像 | `stop_record.wav` |
| 冻结画面 | `freeze.wav` |
| 测量 | `measure.wav` |
| 复位 | `reset.wav` |
| 相册 | `PhotoAlbum.wav` |
| 菜单 | `menu_open.wav` |
| 日间 | `day_mode.wav` |
| 夜间 | `night_mode.wav` |
| 开启检测 | `detection_start.wav` |
| 停止检测 | `detection_stop.wav` |
| 查看告警 | `alerts_open.wav` |
| 增加速度 | `speed_up.wav` |
| 降低速度 | `speed_down.wav` |
| 再见小南 | `goodbye.wav`，播放后重新等待唤醒 |

新增指令的提示音可在 `voice_control/config.py` 的 `COMMAND_AUDIO_FILES` 中填写，例如 `VoiceCommand.OPEN_ALBUM: "album.wav"`，并把音频放入 `sounds/`。保留 `""` 时，指令照常识别并传给业务处理函数，跳过提示音播放。

默认运行提供语音指令识别与提示音反馈；相机、录像等功能暂时还没有接入。

## 工程结构

```text
photo_test/
├── main.py                  # 启动入口
├── __init__.py              # 供 ECSnake 导入的公开接口
├── __main__.py              # python -m photo_test 入口
├── voice_control/           # 运行代码
│   ├── __init__.py          # 接口
│   ├── controller.py        # 唤醒、监听、动作处理与停止
│   ├── config.py            # 统一指令、设备及资源路径
│   ├── command_handler.py   # 业务处理与完成结果契约
│   ├── kws_engine.py        # 模型检查及识别命令
│   ├── audio_capture.py     # 麦克风收音
│   └── audio_feedback.py    # 扬声器反馈
├── config/                  # 唤醒/指令/诊断关键词及 kws-left.asoundrc
├── sounds/                  # WAV 格式提示音及 create_sounds.py 生成中文语音脚本
├── tools/                   # photo_check、build_volume_meter 诊断工具
├── tests/                   # 无硬件回归测试
├── docs/                    # 代码说明、联动说明、音量说明及 history/
├── skills/                  # 项目背景与编码规范
├── README.md
└── .gitignore
```

`local_assets/` 保存本地生成的音频与诊断录音，已忽略提交；程序不会自动使用这里的提示音。`docs/history/` 是历史记录，旧命令以当前 README 为准。

类的职责、变量含义、函数参数与调用流程见 [代码说明文档](docs/代码说明.md)。

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

如使用已有虚拟环境，将 `python3` 换为 `~/Documents/voice/venv/bin/python`。先说“小南小南”，问候语播完再说指令；唤醒一次即可连续使用，说“再见小南”返回等待唤醒，按 `Ctrl+C` 停止。退出口令词表使用完整的“再见小南”音素。

默认收音设备是 `kws_left`，播放设备是 `hw:APE,0`。可以传入 `--sherpa-dir`、`--mic-device`、`--speaker-device`；全部选项用 `python3 main.py --help` 查看。从父目录也可使用 `python3 -m photo_test --once`。

启动时自动检查音频设备和 I2S2 配置。未检测到麦克风信号时，请检查供电和接线；设备错误时会显示原因。检查完成后，说“小南小南”开始使用。

## 诊断与开发工具

工具统一从项目根目录使用模块命令运行：

```bash
python3 -m tools.photo_check                              # 录音、拆分并检查“拍照”
python3 -m tools.photo_check --raw-wav /path/to/stereo.wav  # 重查双声道录音
python3 -m tools.photo_check --wav /path/to/mono.wav        # 检查单声道录音
python3 -m tools.build_volume_meter                       # 构建可选音量版 KWS
python3 main.py --volume-meter                            # 显示输入音量
```

音量工具详见 [音量诊断说明](docs/volume_meter.md)。提示音生成脚本位于 `sounds/create_sounds.py`，若运行 `python sounds/create_sounds.py`生成自定义的声音，需要另外安装 `edge-tts`、配置脚本中的 FFmpeg 路径并联网生成。生成wav设置：48 kHz、双声道、32-bit PCM，输出到 `local_assets/`。

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

在工作线程运行 `VoiceController.run()`，退出时调用 `stop()`。业务处理函数必须等待实际完成后返回 `CommandResult`；失败或未确认结果不会播放成功提示音。Qt 线程要求、录像状态判断和多摄像头拍照条件见 [联动接口说明](docs/integration.md)。“复位”操作留接口，不接实际机械动作。

## 开发测试

```bash
python -m unittest discover -s tests -v
python -m compileall -q voice_control tools tests main.py __init__.py __main__.py
```

开发测试可在 Windows 上运行。模型、sherpa-onnx 编译程序和虚拟环境不包含在仓库中。

## Jetson Nano 接线

| Jetson Orin Nano Super | 模块 | 作用 |
|---|---|---|
| Pin 2 或 4 | VCC | 5V 供电 |
| Pin 6 | GND | 地 |
| Pin 12 | BCLK / SCK | I2S 位时钟 |
| Pin 35 | LRCLK / WS | 左右声道时钟 |
| Pin 40 | DIN | Jetson 输出到播放器 |
| Pin 38 | SD | 麦克风输出到 Jetson |


## 输入声道

硬件按双声道采集，KWS 接收单声道。`python3 main.py --mic-device kws_left` 选左声道；`--mic-device kws_right` 选右声道；`--mic-device kws_mix` 将两路各乘 0.5 后混合。只有两路都含有效语音时才使用混合模式。切换前停止现有监听程序，避免占用设备。

硬件始终按双声道采集，送入 KWS 前选择或合成为单声道。用 `python3 main.py --mic-device kws_right` 选择右声道，或用 `python3 main.py --mic-device kws_mix` 将左右声道各乘 0.5 后混合。两路都含正常语音时才使用混合模式；若一路为噪声或削波信号，应选择有效的另一声道。切换前先停止正在运行的监听程序，避免设备占用。

`python3 main.py` 默认启用持续音频模式，与 `python3 main.py --continuous-audio` 效果相同。此模式持续输出静音，提示音转换为 16 kHz 后通过同一个播放流输出，收放音使用相同的硬件采样率；原 WAV 不变。运行过程中减少设备启停，首次启动和最终退出仍可能产生瞬态。支持工程的左、右、混合输入和 `hw:APE,0` 输出。ECSnake 接入时设置 `VoiceConfig(continuous_audio=True)`，并在退出时调用 `stop()`，等待 `run()` 返回以释放设备。

## 迁移到另一台 Jetson（2026-10-19 gem 快照）

最新代码及提示音来自 gem 的 `/home/gem/Documents/voice/photo_test`。
完整迁移步骤、I2S 接线/引脚配置、依赖安装和验收命令见
[Jetson 迁移指南](docs/jetson-migration.md)。

仓库包含指令词表、ALSA 左右声道路由、全部当前使用的 WAV、事件音效，以及
[gem I2S2 overlay 源码与二进制](deployment/gem-r39.2.1/)。
KWS 程序、动态库和模型使用官方固定版本下载，不重复上传大文件。
已逐文件核对，官方包中的 44 个程序/动态库和 24 个模型配套文件与 gem 的 SHA256 全部一致。
新机完成上文的系统依赖安装和 `git clone` 后执行以下命令；若已有 `sherpa-onnx/`，先改名备份再解压。

```bash
cd ~/Documents/voice
curl -fL -O https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/sherpa-onnx-v1.13.8-linux-aarch64-shared-cpu.tar.bz2
curl -fL -O https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2
sha256sum -c photo_test/deployment/gem-r39.2.1/UPSTREAM-SHA256SUMS
mkdir -p sherpa-onnx/build
tar -xjf sherpa-onnx-v1.13.8-linux-aarch64-shared-cpu.tar.bz2 -C sherpa-onnx/build --strip-components=1
tar -xjf sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2 -C sherpa-onnx
```

运行时使用 Python 标准库；无需复制旧机器的虚拟环境。
