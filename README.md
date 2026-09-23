# MindLoop（启念）实时 Demo

粉色 V2 App、本地语音识别、云端任务理解与硬件接入的联调版本。

- **启动与配置：** [README-LIVE.md](README-LIVE.md)
- **改动、实测结果与当前边界：** [晨间交接](HANDOFF-LIVE-2026-09-24.md)
- **硬件同学接入：** [输入、按键、震动和回执协议](hardware/PROTOCOL-LIVE.md)

安装依赖并配置自己的 `.env` 后，执行 `./start-live.command`，打开 `http://127.0.0.1:4173/phone-demo.html`。完整安装步骤在启动文档中；仓库不包含密钥、模型权重或用户数据库。

语音经本地 VAD 和 Whisper 转写后交给 DeepSeek；图像每5秒采样，交给 Qwen3-Omni 结合任务判断，统一更新 App。软件链路已用测试素材和真实模型验证；实体摄像头接口、马达与呼吸灯仍需硬件联调，详见交接文档。

本仓库由 [Ivy-forever18/mindloop](https://github.com/Ivy-forever18/mindloop) 的 `3a3a9b0` 基础继续开发，保留原 Git 历史。原吊坠模拟器与早期逻辑保留作诊断参考，说明归档在 [README-UPSTREAM.md](README-UPSTREAM.md)，与本次粉色 App 的实时接口分开。
