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

## 已验证的硬件与软件

- Jetson 的 ALSA 声卡为 `APE`，录音和播放设备均使用设备 0；I2S 接口为 `I2S2`。
- `ADMAIF1 Mux = I2S2` 用于收音；`I2S2 Mux = ADMAIF1` 用于播放。
- 当前麦克风的有效语音位于双声道录音的左声道。`hw:APE,0` 单声道读取会报 `Input/output error`；16 kHz 双声道读取正常。
- `kws-left.asoundrc` 强制硬件按双声道采集，只把左声道提供给 sherpa-onnx 的实时 KWS 程序。
- `test_voice.py` 可用的播放参数是 48 kHz、16 位、双声道、`hw:APE,0`。`sounds/photo_success_48k_stereo.wav` 已按这些参数在板上播放，现场确认能听到声音。
- 真人“拍照”已被实时 KWS 识别；改用新语音文件后的完整“识别 → 播放 → 恢复监听”循环仍需现场复测。

这些配置针对当前板卡和接线。更换声卡、I2S 接口或麦克风时，需检查 `audio_capture.py`、`audio_feedback.py` 和 `kws-left.asoundrc` 中的设备与路由。

## 准备环境

推荐目录结构：

```text
~/Documents/voice/
├── photo_test/       # 本仓库
├── sherpa-onnx/      # 已编译的 sherpa-onnx 及模型
└── venv/             # 可选；这些 Python 脚本只用标准库
```

需要安装 ALSA 工具 `amixer`、`arecord`、`aplay`。`sherpa-onnx/build/bin/` 下需要已有 `sherpa-onnx-keyword-spotter-alsa` 和 `sherpa-onnx-keyword-spotter`，并将模型 `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20` 放在 `sherpa-onnx/` 下。模型目录需要 `tokens.txt` 和 `encoder`、`decoder`、`joiner` 的 `epoch-13-avg-2-chunk-16-left-64.onnx` 文件。程序启动时会检查这些文件。

从 GitHub 克隆：

```bash
cd ~/Documents/voice
git clone https://github.com/611bbking/jetson-kws-photo-command-feedback.git photo_test
cd photo_test
```

如果使用现有的 `~/Documents/voice/venv/`，下面的命令可直接复制；否则把 Python 路径换成 `python3`。

## 运行

先验证一次唤醒、识别与播放：

```bash
cd ~/Documents/voice/photo_test
~/Documents/voice/venv/bin/python main.py --once
```

启动后终端显示等待唤醒词。先说“楠机楠机”，终端显示 `识别到唤醒词“楠机楠机”，播放问候语`，并播放 `nanji.wav`。看到 `问候语播放完成，请说指令` 后说上表中的任一指令；终端会打印识别结果，扬声器播放对应文件。`--once` 完成一次后退出。通过后持续运行：

```bash
~/Documents/voice/venv/bin/python main.py
```

持续运行时唤醒一次即可连续使用指令；说“再见楠机”后必须重新唤醒。按 `Ctrl+C` 停止。默认麦克风设备是 `kws_left`，播放设备是 `hw:APE,0`；可通过 `--mic-device`、`--speaker-device` 覆盖。若 sherpa-onnx 位于其他目录，传入 `--sherpa-dir /path/to/sherpa-onnx`。

当前 KWS 模型用“再见”的音素触发“再见楠机”指令，因此单独说“再见”也可能退出指令模式。

## 单独检查收音与播放

当前板卡的原始双声道收音：

```bash
amixer -c APE cset name='ADMAIF1 Mux' I2S2
arecord -D hw:APE,0 -f S16_LE -r 16000 -c 2 -d 3 /tmp/photo-stereo.wav
```

检查左声道虚拟设备：

```bash
ALSA_CONFIG_PATH="$PWD/kws-left.asoundrc" arecord -D kws_left -f S16_LE -r 16000 -c 1 -d 3 /tmp/photo-left.wav
```

使用脚本录制双声道、分别保存左右声道并进行一次性 KWS 检查：

```bash
~/Documents/voice/venv/bin/python photo_check.py
```

单独播放当前提示音：

```bash
amixer -c APE cset name='I2S2 Mux' ADMAIF1
aplay -D hw:APE,0 sounds/nanji.wav
aplay -D hw:APE,0 sounds/takephoto.wav
```

如果 `aplay` 正常退出却听不到声音，先比较实际播放格式和已能发声的 `test_voice.py`。旧的 `sounds/photo_success.wav` 是 22.05 kHz 单声道，不能作为当前板卡的播放验收文件。

## 文件与工作流程

| 文件 | 作用 |
| --- | --- |
| `main.py` | 启动实时唤醒与指令监听。 |
| `live_photo.py` | 唤醒后持续监听指令；识别“再见楠机”后重新等待唤醒。 |
| `app_config.py` | 统一中文关键词、英文业务指令、音频文件及硬件默认参数。 |
| `command_handler.py` | 业务处理接口与完成结果，不依赖 Qt 或相机。 |
| `__init__.py`、`__main__.py` | 独立包导入及 `python -m photo_test` 入口。 |
| `photo_check.py` | 原有的一次性“拍照”录音检查。 |
| `kws_engine.py` | 组合 sherpa-onnx 的模型、关键词与实时识别命令；也支持已有 WAV 的识别。 |
| `audio_capture.py` | 设置收音路由，提供一次性录音与左右声道检查。 |
| `kws-left.asoundrc` | 把 APE 的双声道硬件输入映射为左声道单声道。 |
| `audio_feedback.py` | 设置播放路由，调用 `aplay` 播放提示音。 |
| `photo_keywords.txt` | 当前模型的“拍照”关键词 token：`p āi zh ào @拍照`。 |
| `command_keywords.txt` | 六条功能指令及“再见楠机”的 KWS 关键词 token。 |
| `wake_keywords.txt` | 当前模型的“楠机楠机”关键词 token：`n án j ī n án j ī @楠机楠机`。 |
| `sounds/photo_success.wav` | 最初由本地中文系统语音预先生成的文件；具体语音引擎和声音未记录。 |
| `sounds/photo_success_48k_stereo.wav` | 之前已在板上验证的 48 kHz、16 位双声道语音文件。 |
| `sounds/nanji.wav` | 唤醒后播放的问候语。 |
| `sounds/takephoto.wav` | 识别“拍照”后播放的提示音。 |
| `sounds/start_record.wav`、`sounds/stop_record.wav` | 识别“录像”或“停止录像”后播放的提示音。 |
| `sounds/freeze.wav`、`sounds/measure.wav`、`sounds/reset.wav` | 识别“冻结”“测量”“归零”后播放的提示音。 |
| `sounds/goodbye.wav` | 识别“再见楠机”后播放的提示音。 |

“拍照成功”是在运行前生成的固定语音，Jetson 运行时不调用文字转语音服务。播放文件由原始语音转换得到：

```bash
ffmpeg -i sounds/photo_success.wav -ar 48000 -ac 2 -c:a pcm_s16le sounds/photo_success_48k_stereo.wav
```

模型、编译后的 sherpa-onnx 和 Python 虚拟环境不包含在本仓库中。硬件录音、播放与真人触发需要在 Jetson 上验收。

## 封装接口与命名

Python 变量、函数使用 `snake_case`，类使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`。KWS 中文关键词通过 `KEYWORD_COMMANDS` 转换为 `VoiceCommand`；业务层无需解析中文，也无需知道音频文件名。录像统一使用 `recording`；项目音频仍使用原文件名，不需要重新生成或部署 WAV。

把完整 `photo_test/` 目录放在 ECSnake 根目录下，可通过包名导入，避免与 ECSnake 的 `main.py`、配置等顶层模块冲突：

```python
from photo_test import CommandResult, VoiceCommand, VoiceConfig, VoiceController

def handle_command(command: VoiceCommand) -> CommandResult:
    # 这里只演示接口。未接入的业务必须返回失败，不能假装执行成功。
    return CommandResult(False, f"业务尚未接入：{command.value}")

voice_controller = VoiceController(VoiceConfig(), command_handler=handle_command)
# 在专用工作线程中调用 voice_controller.run()；不要阻塞 Qt GUI 主线程。
# 主应用退出时调用 voice_controller.stop()，随后等待工作线程结束。
```

`run()` 持续执行“唤醒 → 识别 → 业务处理 → 反馈”；`stop()` 可以跨线程调用。无关键词时通过 Linux 管道轮询检查停止请求，随后回收 KWS 进程；已经开始的业务调用和播放会等待其结束。业务处理必须提供超时，不能无限等待。一个实例只运行在一个线程中，停止后重新启动需要新建实例。

命令行保持 `python main.py`；从父目录也可执行 `python -m photo_test --once`。实时音频依赖 Jetson/Linux 的 ALSA 与管道轮询，Windows 用于开发和无硬件测试。

## ECSnake dev 联动检查

本次核对的是 [ECSnake dev](https://github.com/DarkBlueFox/ECSnake/tree/dev)，提交 `ef7efa34c0fe23c4864caa23bb2697696eec6ac3`。这里只准备语音侧的接口，尚未安装 Qt 适配层或验证联动。

| 语音业务指令 | ECSnake 当前入口或信号 | 联动约束 |
| --- | --- | --- |
| `take_photo` | `MainWindow._on_take_photo()` / `CameraView.take_photo()`；`photo_saved_signal(str)`、`photo_failed_signal()` | 请求异步执行，方法返回不代表完成；需等保存结果。 |
| `start_recording` / `stop_recording` | 界面 `toggle_recording()`；相机线程 `start_recording()`、`stop_recording()`；`recording_status_signal(bool)` | 两条指令须先判断状态，不能都直接调用 toggle。 |
| `freeze` | `MainWindow._on_freeze_clicked()` | 当前为切换行为；语音究竟表示冻结还是切换需联动时确认。 |
| `measure` | `MainWindow._on_measure_clicked()` | 方法返回不等于测量结果已生成，需要适配完成结果。 |
| `reset` | 存在设置零点和回零流程 | 用户已确认先保留接口，不接实际机械动作。 |
| `sleep` | 本服务内部处理 | 播放退出提示后回到等待唤醒，不发送业务指令。 |

Qt 适配层应从语音工作线程发出 queued signal，在 GUI 线程调用界面入口；语音线程等待完成/失败结果或超时后返回 `CommandResult`。失败、异常以及 `None` 等未确认结果不会播放成功提示音，服务会继续监听。当前没有失败提示音，失败原因只打印到终端。

拍照还存在两项未确认条件：多摄像头要按“任一成功”还是“全部成功”判定；当前 ECSnake 相机保存代码没有检查 `cv2.imwrite()` 的布尔返回值。因此仅收到 `photo_saved_signal` 仍不足以严格确认写入成功，真正接入时须检查写入结果，并确认本次请求对应的文件。适配层还应关联本次请求，避免将其他按钮触发的保存事件当作语音拍照结果。本次不推断这些业务规则，也不修改 ECSnake 仓库。

根目录的 `Jetson离线语音控制方案.md` 和 `Jetson_KWS项目进度.md` 保留阶段记录，其中旧的 `main.py --raw-wav` 用法现应改为 `photo_check.py --raw-wav`；当前关键词是“录像”、唤醒词是“楠机楠机”，音频文件名以本 README 和 `app_config.py` 为准。

无硬件验证：

```bash
python -m unittest -v
python -m compileall -q .
```

测试覆盖唤醒门控、连续指令、退出重唤醒、跨块日志、业务完成后反馈、失败抑制反馈和主动停止的进程回收。语音识别率、现场播放和实际照片保存仍需 Jetson 联动验收。
