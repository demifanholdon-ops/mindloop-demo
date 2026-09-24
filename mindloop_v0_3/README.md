> **最新团队/UI交接**：请先阅读 [2026-09-23 交接文档](docs/TEAM_UI_HANDOFF_2026-09-23.md)。本文部分历史版本和操作说明以最新交接为准。

# MindLoop V0.3 — Hackathon Demo Build

V0.3 已经可以在**没有真实硬件**的情况下完成比赛级软件 Demo。

核心闭环：

`Intent → Atomic Action → Low-interruption Intervention → Feedback → Metrics → Strategy Evolution`

## 新增内容

- 更接近最终产品的 Demo Dashboard
- 一键演示脚本
- Task Initiation Latency
- Return-to-task Time
- Drift intervention success rate
- Mac 前台 App / Window Context
- Wearable Simulator
- BLE Adapter 预留
- EvoMap GEP-A2A：
  - 本地 Gene + Capsule Bundle
  - `/a2a/hello` Node 注册
  - `/a2a/validate` 发布前验证
  - `/a2a/publish` 真实发布
  - 真实发布需要二次确认
- EvoMap `node_secret` 默认保存于：
  `~/.evomap/mindloop_node.json`
  不进入 Git 仓库

## Mac 最快运行

第一次：

```bash
cd mindloop_v0_3
./setup_mac.command
```

以后：

```bash
./run_demo.command
```

浏览器会自动打开：

```text
http://127.0.0.1:8000
```

## 不接任何 API 也可以 Demo

默认：

```env
AGENT_PROVIDER=mock
```

因此比赛现场即使：
- 无网络
- LLM API 挂掉
- EvoMap 暂时不可用

核心任务启动闭环仍然可以演示。

## 推荐评委 Demo

1. 用户说：“我要准备明天的项目汇报，但不知道从哪里开始。”
2. Agent 给一个原子动作。
3. 用户点 `STUCK`，动作进一步缩小。
4. 用户点 `DONE`，记录 Task Initiation Latency。
5. 模拟 Attention Drift，Wearable Simulator 触发双短震。
6. 用户重新专注，记录 Return-to-task Time。
7. 打开 EvoMap 区域，展示去身份化 Gene + Capsule。
8. 点击 Validate，证明共享策略符合 EvoMap GEP 结构。
9. 正式 Publish 只在队伍确认后执行。

## 任务完成后的操作

完成页会显示两个实体按键选项：

- 短按 K1：结束当前会话，返回“等待新任务”；然后在 Dashboard 输入或语音录入新目标。
- 短按 K2：重新打开刚完成任务的最后一步，继续当前任务。

Dashboard 也提供“新任务”和“继续已完成任务”按钮。任务进行中时，K1 仍表示 Done，K2 仍表示 Stuck。

## 板载麦克风输入任务

设备通过 USB 连接并处于“等待新任务”页时：

1. 单击 K1，屏幕显示“正在听”。
2. 对设备说出任务，例如“准备明天的项目汇报”。
3. 再单击 K1；Mac 本地 MLX Whisper 转写后自动创建任务。

录音最长 15 秒。模型首次安装时由 `setup_mac.command` 安装，首次识别会下载一次模型；之后使用本机缓存。可用 `MINDLOOP_WHISPER_MODEL` 更换模型。当前板载语音链路只支持 USB，BLE 仍可用于屏幕与按键。

## 硬件到手后的 P0

### ESP32-S3 扩展节点

ESP32-S3 作为独立扩展节点接入，不替换已经验证的 nRF52840 主设备。当前
固件提供 USB JSON 握手、心跳和 ping，后续可加入 IMU/Wi‑Fi 上报而不改变
Agent 闭环。编译与桥接：

```bash
CLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"
"$CLI" compile --fqbn esp32:esp32:XIAO_ESP32S3 \
  --output-dir firmware/build_s3 firmware/xiao_esp32s3
.venv/bin/python -m mindloop.s3_bridge --port /dev/cu.usbmodem1101
```

当前 S3 固件尚未刷写到设备；刷写前必须确认目标板型和恢复方式。

只替换设备层，不重写 Agent：

1. BLE
2. Haptic
3. DONE / STUCK / HELP buttons
4. IMU drift feature
5. Display current atomic action

文件：

```text
mindloop/ble_adapter.py
firmware/xiao_nrf52840/
```

## 产品边界

MindLoop 当前定位为认知辅助工具，不进行 ADHD、双相情感障碍或其他疾病诊断。
“Attention Drift”只表示当前行为/数字上下文可能偏离用户自己声明的任务目标。
