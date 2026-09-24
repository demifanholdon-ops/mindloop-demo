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

## 当前默认流程：EvoMap

以 `lirc0618/EvoMap@63dd7ec` 的 K1/K2 与创建任务流程为准。

- 创建任务时才录音，最长15秒，手动结束或到时停止后一次转写，不自动重启、不按句提交。
- 可勾选“创建时使用当前画面”。浏览器只在创建时打开所选摄像头，取单张图后关闭；千问描述场景 → DeepSeek结合目标拆解。硬件录音期间网页可每2秒缓存一张图到本机，8秒失效；只有提交任务才发送云端。
- App保留粉色V2、全部步骤和任意多步勾选。硬件完成当前第一个未完成步骤，两者使用同一组任务/步骤ID。
- 无任务：K1单击开始录音，再单击结束；K2长按恢复最近暂存任务。
- 有任务：K1单击完成、双击撤回、长按暂存并新建；K2单击缩小当前动作、双击换方法。
- 已完成：K1单击回到新建待机；K2单击重做末步。三击不启用。
- 当前不连续识别步骤或偏离；定时视觉与连续语音接口默认关闭。提醒编辑/取消与App数据仍保留。

## 接硬件

```bash
.venv/bin/python scripts/hardware_gateway.py --serial /dev/cu.实际USB串口
```

nRF直连USB，使用EvoMap原有15秒固件，不刷连续/三击修改稿。LRCP USB摄像头可在App的摄像头选择框中选择并勾选画面辅助；网页需保持打开。若设备已有真实JPEG地址，可附加 `--camera-url http://实际设备/实际JPEG接口`，网关仅在创建任务时取一张。

硬件读串口、心跳与云端生成分开执行。语音停止后才提交；生成期间按键不变更进度。硬件未连到本机，真实按键、采集和马达仍需联调。当前网关面向nRF直连USB，尚未把S3独立联网模式接入本App。

## 保留的后续迭代

`future-iteration` 分支指向昨天原样代码 `f2a8e3e`，包含句末0.6秒切句、每5秒识别、单/双/三击方案及当时交接文档。当前主分支保留这些实现但默认关闭；开发测试可用 `LIVE_CONTINUOUS_MODE=1` 和网关 `--continuous`，正式演示不设置这两个选项。

## 验证

```bash
PYTHONPATH=backend MINDLOOP_LLM_PROVIDER=mock .venv/bin/python -m pytest backend -q -o asyncio_mode=auto
npm --prefix frontend-pink run check
npm --prefix frontend-pink test
```

测试模型用桩验证状态和事件幂等，不代表实体硬件成功。真实模型与浏览器验证结果见 `HANDOFF-EVOMAP-2026-09-24.md`。旧连续模式的样本延迟只适用于后续迭代分支，不能当成当前两阶段流程的延迟。
