# MindLoop 粉色 App × 本地处理 × 云端 × 硬件

这是独立仓库 [demifanholdon-ops/mindloop-demo](https://github.com/demifanholdon-ops/mindloop-demo) 的实时 Demo，源自 `Ivy-forever18/mindloop@3a3a9b0`。正式演示入口为粉色 V2；GitHub 原吊坠页面保留为独立旧版诊断页面，其 `/api/mindloop/*` 状态不与新 App 混用。此次统一入口全部使用 `/api/live/*`。

## 启动

本机已安装依赖、下载 Whisper base，并在被 Git 忽略的 `.env` 配置已有供应商凭据。双击 `start-live.command`，或在仓库执行：

```bash
./start-live.command
```

打开 **http://127.0.0.1:4173/phone-demo.html**，会进入 `/app/index.html?live=1`。只用本机统一浏览器，建议 Chrome。折叠的“实时陪伴”内可开启语音、摄像头，也可输入文字。原 V2 静态示例模式仍保留，实时模式不会读取或修改原浏览器演示存档。SQLite 位于 `data/live.sqlite3`，刷新、重启保留记录。

其他机器安装（Python 3.11/3.12）：

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python scripts/download_asr.py
# 新机器复制 .env.example 为 .env，再在本地填写密钥。
./start-live.command
```

依赖锁定参考 `requirements-live-lock.txt`（此次为 Intel macOS）。`models/`、`.env`、数据库、原始验证素材均不会提交。语音模型首次下载约 145 MB；启动后台预热。默认 CPU int8 本地识别；可显式设置 `ASR_PROVIDER=cloud`，该模式会将音频交给供应商文件转写 API，不能称为本地 ASR。

## 数据链路

- 录音：浏览器 AudioWorklet 或 nRF USB PCM → 16 kHz/单声道/16 bit → Mac 本地 WebRTC VAD → 句末约 600 ms 静音即切句 → 本地 faster-whisper → DeepSeek 语义判断 → SQLite → 粉色 App。连续录音不因切句而停止；单段最多 30 秒，无声不送模型。
- 图像：浏览器摄像头或硬件 JPEG 地址 → 每 5 秒采样 → 本机后端 → Qwen3-Omni 视觉模型 → 可见动作判定 → 相同任务/步骤 ID → App。每个会话最多一个识别请求，忙时仅保留最新待处理画面，避免累积过时画面。
- 本地“快处理”在演示电脑上运行，**不是把大模型装进 nRF/ESP32**。默认音频留本地做转写，文字发云端；开启视觉后选取的图片发云端。摄像头默认关闭。
- 硬件屏幕暂不纳入新交互；App 可任意勾选/撤销多个步骤，每个原子动作独立计数。
- 视觉不从静态文档推断持续写作：带时长的步骤要求连续活动证据满足时长，否则等待主动语音或 App 勾选。识别漏记允许存在。
- 提醒缺少日期/钟点会弹窗，不猜时间；可在 App 编辑时间（也用于推迟）或取消。每天提醒每个日期只入队一次。需服务持续运行；不是手机操作系统后台通知。
- 偏离：演示规则离开电脑有跨 ≥5秒的有效观察即可产生一组；其他独立偏离行为 10 分钟累计 3 次一组。同一连续行为不逐帧重复计数，回归只确认最近一次，按事件实际日期记日历。

## 明早接硬件

先保持 App 服务运行。nRF USB 串口和 S3 摄像头走同一后端：

```bash
.venv/bin/python scripts/hardware_gateway.py \
  --serial /dev/cu.实际USB串口 \
  --camera-url http://实际摄像头地址/实际JPEG接口
```

这里的串口和 URL 是占位说明，不是已发现的设备。只接摄像头也可仅给 `--camera-url`，网关即开始采样。两者一起接时，K1 单击开始/停止录音，双击开/关摄像头，三击确认最近一次回归；运行网关时默认开启语音监听。摄像头 HTTP 接口应直接返回真实 JPEG/PNG，建议 960×540，最大 200 万像素。Mac 主动从局域网设备取图，因此 App 服务无需开放到公网或绑定所有网卡。

ZIP 原 nRF 固件每 15 秒停止，网关可自动重启兼容，但会有短暂断点。`hardware/nrf_continuous/nrf_continuous.ino` 提供连续录音及三击事件修改稿；未连接开发板、未编译/烧录，明早由硬件同学使用现有板卡依赖核验。它没有凭空增加已验证的摄像头、灯或马达驱动。

完整协议与马达回执见 `hardware/PROTOCOL-LIVE.md`。ZIP 的原触觉短波形不等价于本次节奏，不能假装执行成功。已实现软件排队、领取、超时和确认回执；实际设备需实现 `haptic_pattern` 能力，Reminder 另需 `breathing_light`。

## 验证与隔离

`backend/test_live.py` 覆盖连续切句、30秒上限、任意多步、用户纠正优先、幂等、模型失败不改数据、关闭摄像头丢弃迟到结果、每日提醒、跨日回归、硬件回执和持续时长。前端含 PCM 重采样与末包 flush 测试。

```bash
.venv/bin/pip install -r requirements-test.txt
PYTHONPATH=backend MINDLOOP_LLM_PROVIDER=mock .venv/bin/python -m pytest backend -q -o asyncio_mode=auto
npm --prefix frontend-pink run check
npm --prefix frontend-pink test
```

真实供应商验证脚本 `probe_audio.py` / `probe_vision.py` **固定使用 4180 隔离服务并会修改其中名为“写报告”的测试任务**，不要改成正式演示端口直接运行。先用独立 `LIVE_DB_PATH` 启动 4180，在 App 创建“打开电脑、打开报告文档、写两分钟”三个步骤；语音探针读取本地合成的 `artifacts/utterance.wav`。这些脚本验证软件传输、模型和状态，不代表实体摄像头准确率或马达实测。

本次具体结果和边界见 `HANDOFF-LIVE-2026-09-24.md`。
