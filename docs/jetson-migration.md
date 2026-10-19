# Jetson 语音控制迁移指南

## 已采集的部署基线

2026-10-19 从 gem 读取：Jetson Orin Nano，设备树 compatible 为
`nvidia,p3768-0000+p3767-0003`；Ubuntu 24.04.4 LTS、Jetson Linux R39.2.1、
aarch64、Python 3.12.3。语音工程在 `~/Documents/voice/photo_test`，依赖在同级
`sherpa-onnx`。sherpa-onnx 1.13.8（11afbd00），ONNX Runtime 1.28.2。

运行依赖包完整保留 gem 的 sherpa-onnx 目录，包括 `build/bin`、`build/lib` 和
`sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20` 模型。逐文件 SHA256 见
[清单](../deployment/gem-r39.2.1/runtime-manifest.json)。使用的是 chunk-16-left-64
浮点 ONNX encoder、decoder、joiner 和 tokens.txt。上游项目为
[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)，预编译包来自其官方 linux-aarch64 shared CPU 发行版。

## 1. 安装并取得工程和运行依赖

在新 Jetson 执行：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv alsa-utils libasound2-dev device-tree-compiler curl
mkdir -p ~/Documents/voice
cd ~/Documents/voice
git clone https://github.com/GoqiTea018/jetson-kws-photo-command-feedback.git photo_test
curl -fL -o gem-kws-runtime-20261019-linux-aarch64.tar.gz \
  https://github.com/GoqiTea018/jetson-kws-photo-command-feedback/releases/download/gem-runtime-20261019/gem-kws-runtime-20261019-linux-aarch64.tar.gz
sha256sum -c photo_test/deployment/gem-r39.2.1/SHA256SUMS
tar -xzf gem-kws-runtime-20261019-linux-aarch64.tar.gz
ldd sherpa-onnx/build/bin/sherpa-onnx-keyword-spotter-alsa
sherpa-onnx/build/bin/sherpa-onnx-version
```

`ldd` 各项应解析到实际库，`build/lib` 应与 `build/bin` 一起保留。依赖包面向
Linux aarch64；不同系统版本若报 GLIBC/GLIBCXX 版本错误，在目标系统编译匹配的
sherpa-onnx 并沿用模型与词表。目标机器已有 `sherpa-onnx` 时，先将旧目录改名备份再解压。

应用运行只需 Python 标准库。可选虚拟环境：

```bash
python3 -m venv ~/Documents/voice/venv
```

`edge-tts` 和 FFmpeg 用于重新生成提示音，现有 WAV 可直接播放。
`--volume-meter` 使用额外编译的程序，构建步骤见 [音量工具说明](volume_meter.md)。

## 2. 接线与 I2S2 引脚

| Jetson 40-pin | 音频模块 |
| --- | --- |
| 2/4 | VCC（当前模块 5V） |
| 6 | GND |
| 12 | BCLK/SCK |
| 35 | LRCLK/WS |
| 38 | 模块 SD，麦克风输出到 Jetson |
| 40 | 模块 DIN，Jetson 输出到播放器 |

按模块规格核对供电和信号电平。

先用目标机器的 `sudo /opt/nvidia/jetson-io/jetson-io.py` 配置 40-pin I2S2，
保存启动配置并重启。仓库保存了 gem 实际使用的
[DTBO](../deployment/gem-r39.2.1/jetson-io-hdr40-user-custom.dtbo) 和
[可编辑 DTS](../deployment/gem-r39.2.1/jetson-io-hdr40-user-custom.dts)。
其关键值为四个引脚 `function=i2s2`、`gpio-mode=1`；12/35/40 的 tristate=0，
38 的 tristate=1；12/35/38 的 enable-input=1，40 的 enable-input=0。

相同 p3768+p3767 板卡和 R39.2.1 系统可使用保存的 overlay：

```bash
cd ~/Documents/voice/photo_test
sudo cp /boot/extlinux/extlinux.conf /boot/extlinux/extlinux.conf.before-voice
sudo cp deployment/gem-r39.2.1/jetson-io-hdr40-user-custom.dtbo /boot/
sudo nano /boot/extlinux/extlinux.conf
```

在 Jetson-IO 生成的活动启动条目（gem 是 `DEFAULT JetsonIO`）中，将该 overlay
加入现有 `OVERLAYS` 行，保留其他 overlay：

```text
OVERLAYS /boot/jetson-io-hdr40-user-custom.dtbo
```

保留目标机自己的 FDT、根分区标识和内核参数；不同板卡/BSP 使用目标机生成的
配置并对照 DTS 调整引脚。修改后 `sudo reboot`。原始启动条目和备份用于恢复。

## 3. ALSA 路由和权限

```bash
amixer -c APE cset name='ADMAIF1 Mux' I2S2
amixer -c APE cset name='I2S2 Mux' ADMAIF1
sudo alsactl store
```

gem 读取到的路由正是上述值。`config/kws-left.asoundrc` 已在仓库；程序选择
`kws_left`、`kws_right` 或 `kws_mix` 时会自动设置 `ALSA_CONFIG_PATH`，无需改全局
`~/.asoundrc`。默认左声道，扬声器 `hw:APE,0`。若音频设备访问被拒绝，执行
`sudo usermod -aG audio "$USER"` 后重新登录；应用以普通用户运行。

## 4. 检查收音、放音和启动

确认没有其他语音监听程序占用设备，边说话边录制：

```bash
cd ~/Documents/voice/photo_test
ALSA_CONFIG_PATH="$PWD/config/kws-left.asoundrc" \
  arecord -D kws_left -r 16000 -f S16_LE -c 1 -d 3 /tmp/voice-check.wav
aplay -D hw:APE,0 sounds/xiaonan.wav
python3 - <<'PY'
import array, wave
with wave.open('/tmp/voice-check.wav') as w:
    samples = array.array('h', w.readframes(w.getnframes()))
print('peak:', max(map(abs, samples), default=0))
print('nonzero samples:', sum(x != 0 for x in samples))
PY
python3 -m unittest discover -q
python3 main.py --once
python3 main.py
```

检查有非零采样且能听到问候语，再说“小南小南”、指令和“再见小南”验收。
全零采样先检查接线、供电、overlay 和引脚状态。切换声道可用
`python3 main.py --mic-device kws_right`。

默认持续输出流在空闲时发送静音，提示音共用同一输出流，减少反复开关音频设备的爆破音。
当前唤醒音为 `xiaonan.wav`，所有指令 WAV、事件音效和词表均随仓库提供。
相机等业务动作通过 CommandHandler 接口接入，见 [联动说明](integration.md)。

本次迁移快照使用手动 `python3 main.py` 启动；gem 用户级服务列表未发现
voice/kws/snake 服务。新机启动、收放音和识别闭环应按以上步骤完成验收。
