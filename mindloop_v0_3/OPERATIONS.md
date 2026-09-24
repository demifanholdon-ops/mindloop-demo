> **最新团队/UI交接**：请先阅读 [2026-09-23 交接文档](docs/TEAM_UI_HANDOFF_2026-09-23.md)。本文部分历史版本和操作说明以最新交接为准。

# MindLoop V0.3 操作手册

## 1. 设备角色

- **XIAO nRF52840 Plus**：主穿戴设备；屏幕、K1/K2、板载麦克风、USB/BLE。
- **XIAO ESP32-S3**：扩展节点；当前提供 USB hello、heartbeat、context、drift 事件。
- **Mac Agent**：FastAPI、Dashboard、任务拆解、反馈、漂移干预和 EvoMap。

当前比赛现场的稳定链路是 USB。BLE 已有协议骨架，但不要把 BLE 作为现场唯一链路。

## 2. 一键启动主 Demo

```bash
cd /Users/lirc/VSCode/EvoMap/mindloop_v0_3
./run_demo.command
```

脚本会启动 Agent、nRF52840 USB bridge 和浏览器。只运行一个 nRF bridge；如果设备重连，先关闭旧 bridge 再启动。

## 3. 启动 S3 扩展节点

另开终端：

```bash
cd /Users/lirc/VSCode/EvoMap/mindloop_v0_3
.venv/bin/python -m mindloop.s3_bridge --port /dev/cu.usbmodem1101
```

验证节点：

```bash
curl -s http://127.0.0.1:8000/api/state | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["s3_node"])'
```

应看到 `online: true`、`firmware: mindloop-s3-0.1` 和最近事件。

## 4. Demo 操作流程

1. 在 Dashboard 输入：`我要准备明天的项目汇报，但不知道怎么开始`。
2. 设备显示一个最小动作。
3. K1 单击表示 Done；K2 单击表示 Stuck；K2 双击请求换一种方法。
4. 空闲时 K1 单击开始/结束板载语音录音，Mac 使用 MLX Whisper 转写并自动创建任务。
5. 任务完成页：K1 开新任务，K2 继续最后一步。
6. 运行 `context`/`drift` 事件可演示 S3 到 Agent 的漂移干预链路。

## 5. 直接测试 S3 协议

```bash
cd /Users/lirc/VSCode/EvoMap/mindloop_v0_3
.venv/bin/python - <<'PY'
import serial, time
with serial.Serial('/dev/cu.usbmodem1101', 115200, timeout=.7) as s:
    time.sleep(1); s.reset_input_buffer()
    for cmd in ('hello', 'context', 'drift'):
        s.write((f'{{"cmd":"{cmd}"}}\\n').encode()); s.flush(); time.sleep(.3)
        while s.in_waiting: print(s.readline().decode().strip())
PY
```

只有在 Agent 有活动任务时，`drift` 才会切换任务状态并触发干预。

## 6. 重新编译/刷写 S3

必须使用 Apple Silicon 原生 Homebrew CLI，不要使用 Arduino IDE 内置的 x86_64 CLI：

```bash
CLI=/opt/homebrew/bin/arduino-cli
cd /Users/lirc/VSCode/EvoMap
"$CLI" compile --fqbn esp32:esp32:XIAO_ESP32S3 \
  --output-dir mindloop_v0_3/firmware/build_s3 \
  mindloop_v0_3/firmware/xiao_esp32s3
"$CLI" upload --fqbn esp32:esp32:XIAO_ESP32S3 \
  --port /dev/cu.usbmodem1101 \
  --input-dir mindloop_v0_3/firmware/build_s3
```

如果端口消失，重新插拔 USB；如果进入 bootloader，按两次 Reset 后重试。

## 7. 故障排查

- `Address already in use`：`lsof -nP -iTCP:8000 -sTCP:LISTEN`，关闭旧 uvicorn。
- `ESP32-S3 heartbeat timeout`：确认端口、USB 线和 S3 已运行固件；只保留一个 S3 bridge。
- nRF 屏幕无响应：确认没有第二个 bridge 占用串口，重启 `run_demo.command`。
- 编译出现 `libxcrun ... need x86_64`：改用 `/opt/homebrew/bin/arduino-cli`。
- 设备恢复：不要给 S3 使用 nRF52840 的 UF2；S3 使用 Arduino CLI/esptool 刷写。

## 8. 当前边界

S3 的 `context` 和 `drift` 目前是协议/演示事件，尚未接入真实 IMU、摄像头或 Sense 麦克风。nRF52840 的板载麦克风 USB 链路是当前真实语音输入方案。

## 9. 验收命令

```bash
cd /Users/lirc/VSCode/EvoMap/mindloop_v0_3
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m py_compile mindloop/*.py
```

预期：20 项测试通过，且 Python 编译检查无输出错误。

## 10. reSpeaker Flex XVF3800 测试

识别结果：macOS 已枚举 `reSpeaker Flex XVF3800 L16K6Ch`，Seeed Studio，USB，6 输入通道，2 输出通道，16 kHz。

安装依赖并枚举：

```bash
cd /Users/lirc/VSCode/EvoMap/mindloop_v0_3
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/test_respeaker.py
```

预期 JSON：`ok: true`、`input_channels: 6`、`sample_rate: 16000`。

采集测试（0.1 秒，6 通道）：

```bash
.venv/bin/python scripts/test_respeaker.py --capture
```

实测已通过：1600 帧、6 通道。脚本还报告 `peak`、`rms`；对着设备说话时两者应明显大于 0。

若采集命令无返回，检查 macOS「系统设置 → 隐私与安全性 → 麦克风」是否允许 Terminal、VS Code 或 Python；重新授权后重启终端。设备枚举成功不等于应用已有麦克风权限。
