# ECSnake 联动与语音接口

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
