# MindLoop（启念）EvoMap 联调 Demo

粉色 V2 App、本地语音识别、云端任务理解与硬件接入的联调版本。

- **启动与配置：** [README-LIVE.md](README-LIVE.md)
- **改动、实测结果与当前边界：** [晨间交接](HANDOFF-LIVE-2026-09-24.md)
- **硬件同学接入：** [输入、按键、震动和回执协议](hardware/PROTOCOL-LIVE.md)

安装依赖并配置自己的 `.env` 后，执行 `./start-live.command`，打开 `http://127.0.0.1:4173/phone-demo.html`。完整安装步骤在启动文档中；仓库不包含密钥、模型权重或用户数据库。

当前默认以 EvoMap 的旧流程为准：创建任务时录音，停止后本地 Whisper 转写；可选当前单张画面先交给千问描述，再由 DeepSeek 结合目标拆解。K1/K2 与粉色 App 操作同一份任务。执行期间不持续采集或自动勾选。

昨天的连续录音、每5秒视觉、单/双/三击方案已原样保存在 `future-iteration` 分支（`f2a8e3e`），不随本次修改改变。当前差异和联调方式见 [EvoMap 交接](HANDOFF-EVOMAP-2026-09-24.md)。

本仓库由 [Ivy-forever18/mindloop](https://github.com/Ivy-forever18/mindloop) 的 `3a3a9b0` 基础继续开发，保留原 Git 历史。原吊坠模拟器与早期逻辑保留作诊断参考，说明归档在 [README-UPSTREAM.md](README-UPSTREAM.md)，与本次粉色 App 的实时接口分开。
