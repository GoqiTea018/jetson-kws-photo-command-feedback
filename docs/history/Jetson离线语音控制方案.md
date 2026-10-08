> 历史阶段记录：文件名、目录与运行命令可能已过时。当前用法见 [README](../../README.md)。

# Jetson 离线语音控制方案

## 1. 当前目标

在 Jetson 上实现离线语音控制：

- I2S 麦克风持续采集语音
- 识别固定控制词
- 将识别结果转换为软件指令
- 触发对应功能
- 通过 I2S 扬声器播放提示音反馈

Jetson 已做 ALSA / I2S 软件配置。用户反馈已完成收放音共用时钟线接线，单次“拍照”识别也已跑通；当前要验证持续监听、终端提示和扬声器语音反馈。相机及其他控制硬件尚未全部到位。

---

## 2. 控制词

目标控制词：

- 拍照
- 开始录像
- 停止录像
- 冻结
- 测量
- 归零

后续可增加唤醒词，例如：

```text
小蛇小蛇 → 激活语音控制 → 执行具体指令
```

---

## 3. 技术方案

第一版采用 **离线关键词识别 KWS** 处理固定指令。

核心流程：

```text
I2S 麦克风
    ↓
ALSA 实时采集 PCM
    ↓
统一为 16 kHz / Mono
    ↓
sherpa-onnx KWS
    ↓
识别关键词
    ↓
指令映射
    ↓
执行软件功能
    ↓
播放 WAV 提示音
    ↓
I2S 扬声器
```

推荐模型：

```text
sherpa-onnx 中文/中英 KWS
```

特点：

- 完全离线
- 模型较小
- 支持自定义关键词
- 不需要重新训练模型
- 适合 Jetson 实时运行

当前使用的 `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20` 模型，其正式关键词配置应使用配套的 `tokens.txt`、`en.phone` 和 `text2token --tokens-type phone+ppinyin` 生成。本次单词测试先使用已核对模型词表的 `p āi zh ào @拍照`，且 KWS 程序已成功加载。GPU 版本已编译不等于实时识别已通过；实际运行方式和延迟以 Jetson 测试为准。

---

## 4. 指令映射

```python
COMMANDS = {
    "拍照": "TAKE_PHOTO",
    "开始录像": "START_VIDEO",
    "停止录像": "STOP_VIDEO",
    "冻结": "FREEZE",
    "测量": "MEASURE",
    "归零": "ZERO",
}
```

后续分别调用对应功能，例如：

```text
拍照 → camera.take_photo()
开始录像 → camera.start_record()
停止录像 → camera.stop_record()
冻结 → vision.freeze()
测量 → measurement.start()
归零 → measurement.zero()
```

---

## 5. 提示音方案

第一阶段运行时不启动 TTS，使用事先生成的 WAV。当前“拍照成功”使用本地中文系统语音生成，保存在 `photo_test/sounds/photo_success.wav`：

```text
sounds/
├── photo_success.wav
├── start_video.wav
├── stop_video.wav
├── freeze.wav
├── measure.wav
└── zero.wav
```

当前识别“拍照”后，终端打印 `识别到指令“拍照”`，通过 `aplay` 播放“拍照成功”。相机未接入时，这只是语音指令反馈，并不表示实际照片已保存。

为避免扬声器提示音被麦克风再次识别：

```text
识别指令
→ 停止本轮 KWS 麦克风监听
→ 输出指令提示
→ 播放提示音
→ 等待约 500 ms
→ 重新启动 KWS 监听
```

---

## 6. 项目结构建议

```text
voice/
├── main.py
├── audio_capture.py
├── kws_engine.py
├── command_handler.py
├── audio_feedback.py
├── models/
│   └── kws/
└── sounds/
```

---

## 7. 下一步

### 当前接线与分阶段测试

照片显示使用一块 MicroDeer「录音+功放模块」。此前的《Jetson_Orin_Nano_Super_I2S接线与检查说明》只列了这块模块的播放侧；结合照片上的收音侧丝印，信号对应如下：

| Jetson 40Pin | Jetson 信号 | MicroDeer 模块引脚 |
|---|---|---|
| Pin 12 | I2S2 SCLK / BCLK | 播放侧 BCLK、收音侧 SCK |
| Pin 35 | I2S2 FS / LRCLK | 播放侧 LRCLK、收音侧 WS |
| Pin 40 | I2S2 DOUT | 播放侧 DIN |
| Pin 38 | I2S2 DIN | 收音侧 SD |
| Pin 2 或 4 | 5V | VCC（用户确认模块可用 5V 供电） |
| Pin 6 | GND | GND |

`SCK` 是收音侧时钟脚，`SD` 是收音侧数据输出脚；照片中没有单独的 `SDK` 脚。用户表示已按表完成共用时钟及收放音接线。模块可接 5V 供电，不代表 I2S 信号脚是 5V 电平；仍需以模块资料核对电平。[NVIDIA Jetson 音频接口说明](https://docs.nvidia.com/jetson/archives/r38.2/DeveloperGuide/SD/Communications/AudioSetupAndDevelopment.html)

已通过 SSH 确认 Jetson 上有 KWS 可执行程序和模型，模型示例 WAV 能识别示例关键词。`photo_test/` 已传至 `~/Documents/voice/photo_test/`。首次真人录音中，旧代码按响度误选了右声道，右声道持续异常且有 3.3% 削波；原始录音的左声道交给 KWS 后识别出三次“拍照”。代码现已改为分别保存、检测左右声道，使用这段旧录音重跑成功；修复后的现场录音路径尚待复测。

### 第一步：单独验证 Jetson 收音与“拍照”识别

在当前收音接线下，用 `photo_test/main.py` 录制本人说“拍照”的 WAV，再交给 KWS 识别。录音期间显示 ALSA 实时音量条；结束后保留原始双声道录音，分别生成左右声道单声道 WAV，输出两声道 RMS、削波比例，并逐一检查“拍照”。不能按响度选声道：首次录音的右声道很响，但只有左声道含可识别语音。因此现阶段不依赖扬声器回放。验收：现场新录音由脚本输出 `[识别] 拍照（左声道）` 或对应的右声道结果。

```bash
cd ~/Documents/voice/photo_test
~/Documents/voice/venv/bin/python main.py
```

运行后在 8 秒录音窗口内清楚说两三次“拍照”。若需要重测已保存的双声道 WAV，可用 `main.py --raw-wav photo-test-raw.wav`；单声道文件可用 `main.py --wav /path/to/mono.wav`。

若录音失败，可先检查已识别的 `APE` 设备、路由和原始录音。播放侧接好以后再做回放验证：

```bash
arecord -l
aplay -l
amixer -c APE cget name="ADMAIF1 Mux"
```

本次 SSH 检查中该路由值为 `I2S2`；同一次真人录音的左声道已由 Jetson KWS 识别“拍照”，新版本脚本的现场录音流程仍需复测。

### 第二步：验证持续监听和“拍照成功”语音反馈

目标：

```text
持续运行时说“拍照”
→ Jetson 终端输出“识别到指令‘拍照’”
→ 扬声器播放“拍照成功”
```

`photo_test/live_photo.py` 已部署到 Jetson，使用现成 ALSA 实时 KWS 程序监听；识别后终止监听进程、播放提示音，随后重启监听。先用 `--once` 验证一次触发，再连续运行观察漏识别、重复触发和提示音回灌：

```bash
cd ~/Documents/voice/photo_test
~/Documents/voice/venv/bin/python live_photo.py --once
~/Documents/voice/venv/bin/python live_photo.py
```

### 第三步：加入提示音与指令模拟

实现：

```text
识别“拍照”
→ 输出指令
→ 播放 photo_success.wav
```

同时加入防重复触发和播放期间暂停识别机制，通过实际回放确认提示音不会造成重复触发。

### 第四步：接入实际功能

将关键词分别连接：

- 相机拍照
- 开始/停止录像
- 图像冻结
- 测量
- 归零

这一步等待相机及控制硬件到位，并需要确认“冻结、测量、归零”对应的实际程序接口。

### 第五步：稳定性优化

根据测试情况增加：

- 关键词阈值调整
- 唤醒词
- VAD 静音检测
- 必要时再加入完整 ASR 或 TTS

---

## 8. 第一阶段目标

用户反馈收放音接线和单次“拍照”识别已跑通；当前验证终端提示与语音反馈：

```text
Jetson 持续收音 → KWS 识别“拍照” → 终端提示 → 扬声器播放“拍照成功”
```

随后完成语音控制最小闭环：

```text
语音输入
→ 关键词识别
→ 指令触发
→ 提示音反馈
```

确认该闭环稳定后，再与完整控制系统集成。本地编写平台无关的指令逻辑和配置，经 SSH 传到 Jetson 的 `~/Documents/voice/` 应用子目录；录音、播放和实时识别在 Jetson 上验收，不覆盖已有的 `sherpa-onnx/` 和 `venv/`。
