# MindLoop 分支与来源

截至2026-09-24，本仓库的 `main` 是项目唯一主版本，GitHub 默认分支也为 `main`。团队的前端、后端、硬件接入与演示以此版本为准。外部仓库仅作参考，不自动覆盖主版本。

| 分支 | 定位 | 来源／快照 |
|---|---|---|
| `main` | 主版本；开发与演示入口 | 本仓库维护和整合 |
| `reference-evomap` | 硬件及交互参考版本 | [lirc0618/EvoMap](https://github.com/lirc0618/EvoMap)，原始提交 `63dd7ec8c2af56d63a6bab1563ce97a9f93b07ef` |
| `history-backend` | 后端历史参考版本 | [Ivy-forever18/mindloop/backend](https://github.com/Ivy-forever18/mindloop/tree/main/backend)，原始提交 `3a3a9b0463fab61411b003b1373337d9399f769b` |
| `future-iteration` | 昨天完整方案原样保留，供后续迭代 | `f2a8e3e4d764671b79ed7fc78154917010b4ed08` |

## 使用约定

- 正式开发、修复、联调、演示使用 `main`。当前功能及交互说明见 `README-LIVE.md`。
- `reference-evomap` 保留 EvoMap 原始仓库结构与历史，供阅读硬件固件及其桥接代码。
- `history-backend` 保留 Ivy 原始仓库结构与历史；后端代码仍在 `backend/`，没有单独抽取或重写提交。
- `future-iteration` 未修改，包含连续句末上传、每5秒视觉识别及原按键方案。不要把当前简化演示的改动写入该存档分支。
- 两个参考分支是本次拉取的快照，不设为默认分支，也不自动合并；以后按具体需要选择性引入，并验证与主版本兼容。
- 本地 `origin` 指向自己的主仓库；`evomap` 和 `upstream` 分别指向两个来源仓库。本次只向自己的 `origin` 推送，没有修改队友仓库。
