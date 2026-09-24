# MindLoop（启念）主版本

粉色 V2 App、本地语音识别、云端任务理解与硬件接入的主版本。**项目以本仓库的 `main` 为准**；功能定义、联调、演示和后续修复都在这里统一。

- **启动与配置：** [README-LIVE.md](README-LIVE.md)
- **改动、实测结果与当前边界：** [当前交接](HANDOFF-EVOMAP-2026-09-24.md)
- **硬件同学接入：** [输入、按键、震动和回执协议](hardware/PROTOCOL-LIVE.md)

安装依赖并配置自己的 `.env` 后，执行 `./start-live.command`，打开 `http://127.0.0.1:4173/phone-demo.html`。完整安装步骤在启动文档中；仓库不包含密钥、模型权重或用户数据库。

当前主版本已采用 EvoMap 的任务创建交互：创建任务时录音，停止后本地 Whisper 转写；可选当前单张画面先交给千问描述，再由 DeepSeek 结合目标拆解。K1/K2 与粉色 App 操作同一份任务。执行期间不持续采集或自动勾选。

昨天的连续录音、每5秒视觉、单/双/三击方案已原样保存在 `future-iteration` 分支（`f2a8e3e`），不随本次修改改变。当前差异和联调方式见 [EvoMap 交接](HANDOFF-EVOMAP-2026-09-24.md)。

本仓库由 [Ivy-forever18/mindloop](https://github.com/Ivy-forever18/mindloop) 的 `3a3a9b0` 基础继续开发，保留原 Git 历史。原吊坠模拟器与早期逻辑保留作诊断参考，说明归档在 [README-UPSTREAM.md](README-UPSTREAM.md)，与本次粉色 App 的实时接口分开。

## 分支关系

| 分支 | 定位 |
|---|---|
| [`main`](https://github.com/demifanholdon-ops/mindloop-demo/tree/main) | **唯一主版本**：前端、后端和硬件接入在这里整合；项目决策以此版本为准。 |
| [`reference-evomap`](https://github.com/demifanholdon-ops/mindloop-demo/tree/reference-evomap) | EvoMap 硬件与交互流程参考快照，保留来源仓库完整结构，不作为当前 App 主入口。 |
| [`history-backend`](https://github.com/demifanholdon-ops/mindloop-demo/tree/history-backend/backend) | Ivy 原后端历史参考；保留原仓库历史和目录，重点参考 `backend/`。 |
| [`future-iteration`](https://github.com/demifanholdon-ops/mindloop-demo/tree/future-iteration) | 昨天方案的原样存档：连续录音、每5秒视觉、原按键方案，留待后续迭代。 |

两个参考分支是独立快照，来源仓库更新不会自动合并到 `main`。需要采用的改动应先检查与当前主版本的兼容性，再选择性整合。参考版本与 `main` 有出入时，以 `main` 的当前实现和确认需求为准。

来源与快照提交见 [分支说明](BRANCHES.md)。
