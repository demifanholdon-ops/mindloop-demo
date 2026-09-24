# MindLoop（启念）｜EvoTavern 深圳站黑客松项目交接

> 队伍名 / 项目名暂定：**MindLoop（启念）**  
> 赛道：**具身与穿戴硬件｜CYBERBODY**  
> 项目定位：**面向执行功能困难与高认知负荷人群的 AI 可穿戴认知辅助系统**  
> 核心原则：**不做疾病诊断，做“感知—决策—行动—反馈—学习”的认知辅助闭环。**

---

## 1. 一句话介绍

MindLoop 是一个可穿戴 AI Cognitive Companion：当用户“知道要做什么，但启动不了”或注意力开始漂移时，设备通过按键/语音、IMU 与数字上下文感知用户状态，Agent 将模糊目标拆成一个可以立刻执行的最小动作，再通过震动、灯光或语音低干扰地推动用户开始行动，并根据“有效 / 卡住 / 完成”的反馈持续学习个人最有效的启动策略。

**核心不是提醒，而是帮助用户从“想做”进入“正在做”。**

---

## 2. 为什么做

### 目标人群

首批用户聚焦：

- 成人 ADHD / ADHD 特征明显的人群，尤其是任务启动困难、注意力漂移明显的人群；
- 创业者、科研人员、程序员、设计师、创作者等高认知负荷人群；
- 任何存在“目标明确但难以启动、容易分心、任务切换困难”的用户。

### 关键痛点

传统 Todo、日历和提醒器知道“什么时候提醒”，但不知道：

- 用户为什么还没有开始；
- 当前目标是不是太大、太模糊；
- 用户现在处于什么场景和行为状态；
- 什么样的提醒对这个人真正有效；
- 提醒之后用户有没有真的行动。

MindLoop 的差异在于：**从 Reminder 变成 Cognitive Action Agent。**

---

## 3. 比赛 MVP：只做两个场景

### 场景 A｜任务启动困难【主 Demo，必须完成】

完整闭环：

```text
用户卡住
  ↓
长按按键 / 语音表达任务
“我要准备明天的汇报，但不知道怎么开始”
  ↓
Agent 理解 Intent
  ↓
任务原子化
“先打开昨天的 PPT”
  ↓
可穿戴设备：轻震 + 屏幕/灯光提示
  ↓
用户行动
  ↓
按键反馈：完成 / 还是卡住
  ↓
Agent 给下一步或进一步缩小动作
  ↓
记录这次策略是否有效
```

关键产品设计：**一次只显示当前一步，不一次性甩给用户十几个 Todo。**

### 场景 B｜注意力漂移【辅助 Demo】

```text
当前 Intent：写论文 / 做 PPT
        +
PC 数字行为：离开目标应用 / 高频切换
        +
IMU：频繁小动作 / 状态变化
        ↓
Attention Drift Score
        ↓
轻震提醒
        ↓
用户回到任务
```

原则：**Minimum Intervention**。能灯光解决就不震动，能震动解决就不语音。

---

## 4. 暂不作为比赛核心的能力

这些方向保留在 Roadmap，不允许拖累 MVP：

- 生理信号：PPG / HR / HRV / SpO₂ / EDA；
- 低功耗摄像头与场景识别；
- 丢三落四 / 物品回溯；
- 长期情绪相关模式学习；
- 全天候 Always-on 超低功耗优化；
- 自研 PCB。

如果主闭环提前完成，再选一个作为展示扩展。

---

## 5. 产品形态

第一版定位为 **可变佩戴的 Cognitive Node**，优先做：

**胸针 / 挂件 / 项链 / 衣领夹**。

原因：麦克风、按钮、屏幕/灯光、IMU 和震动都适合放在胸前或衣领；外观也比“医疗手环”更符合认知辅助产品定位。

长期产品可以演化为：

```text
Pendant / Clip：环境 Context + Agent 交互
                 +
Watch / Ring：生理状态
                 ↓
统一 Cognitive Agent
```

---

## 6. 系统架构

```text
                 Human Intent
                      │
        ┌─────────────▼─────────────┐
        │     Cognitive Agent       │
        │  Intent / Task / Memory   │
        └─────────────┬─────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
     Context       Behavior      Physiology
   Mic / PC      IMU / App        Optional
        └─────────────┼─────────────┘
                      ▼
              Cognitive State
        Start / Focus / Drift / Stuck
                      │
                      ▼
             Intervention Policy
                      │
             ┌────────┼────────┐
             ▼        ▼        ▼
            LED     Haptic    Voice
                      │
                      ▼
                 Human Action
                      │
                Button Feedback
             Done / Stuck / Effective
                      │
                      ▼
             Personal Strategy Memory
                      │
           validated strategy only
                      ▼
                    EvoMap
              Gene / Capsule sharing
```

---

## 7. Agent 逻辑

Agent 的输入：

```text
Intent + 当前 Context + 行为状态 + 历史反馈
```

Agent 的核心任务不是聊天，而是决定：

1. 用户目前卡在哪里；
2. 当前任务是否太大；
3. 下一步最小可行动作是什么；
4. 现在是否应该干预；
5. 用什么强度干预；
6. 该策略对这个用户是否有效。

### 按键交互建议

- **单击**：完成 / 下一步；
- **双击**：还是卡住；
- **长按**：开始语音描述当前任务或问题。

### EvoMap 接入

EvoMap 作为“群体经验进化层”，不是核心执行依赖。

个人侧先学习：

> 对用户 A，大任务启动时，“只给一个物理动作 + 单次轻震”是否有效？

经过多次验证后，将去身份化策略整理为可复用 Gene / Capsule，再由其他 Agent 继承和验证。

**比赛优先级：先确保本地 Agent 闭环跑通，再接 EvoMap。**

---

## 8. 硬件方案

### A. 现场官方资源中，我们优先使用

| 设备 | 官方支持数量 | 我们用途 | 优先级 |
|---|---:|---|---|
| **XIAO 0.96'' IPS Display (nRF52840)** | 5 | 可穿戴主设备 | ★★★★★ |
| **reSpeaker Flex Circular / Linear** | 各 5 | 桌面语音输入、VAD/降噪 | ★★★★☆ |
| **XIAO ESP32-S3** | 10 | Wi-Fi / BLE 扩展节点或备份主控 | ★★★☆☆ |
| **USB Camera** | 2 | 可选场景识别 Demo | ★★☆☆☆ |
| **6×10 WS2812 RGB Matrix for XIAO** | 5 | 展台状态可视化 | ★★☆☆☆ |

### B. XIAO 0.96'' nRF52840 已经集成

- nRF52840 主控；
- BLE 5.4；
- 0.96'' 80×160 IPS 屏幕；
- LSM6DS3 六轴 IMU；
- PDM 数字麦克风；
- 2 个实体按键；
- 3.7V LiPo 电池接口与电量检测。

因此比赛版**无需再单独采购 IMU、麦克风、按键和显示屏**。

### C. 必须提前自备

| 硬件 | 数量 | 参考预算 | 备注 |
|---|---:|---:|---|
| **DRV2605L 成品触觉驱动模块** | 2 | ¥40–140 | 优先 Qwiic/STEMMA/Grove/成品板，不买裸芯片 |
| **LRA Coin Vibration Motor** | 2 | ¥20–50 | 搭配 DRV2605L |
| **3.7V LiPo 500–1000mAh 成品电池** | 2 | ¥40–80 | 注意 JST 插头兼容性 |
| USB 数据线 / 转接线 | 多根 | ¥20–50 | 必须带备用 |
| 挂绳 / 磁吸夹 / 胸针外壳 | 2 套 | ¥20–100 | 建议提前 3D 打印或购买现成外壳 |
| RJ45 → USB-C/USB 网卡 | 1 | ¥30–100 | 官方强烈建议携带有线网转接头 |

**建议自备预算：约 ¥150–400；买双份关键模块防止损坏。**

### D. 可选硬件

- MAX30102 成品模块：PPG / HR / SpO₂ 展示；
- GSR / EDA 模块：长期生理状态研究；
- 摄像头：环境 Context，仅在主功能完成后加入。

---

## 9. 开发平台

### Wearable Firmware

建议：

```text
VS Code
└─ PlatformIO / Arduino
   └─ XIAO nRF52840 Plus
```

首要 Firmware 功能：

- BLE 双向通信；
- IMU 采集；
- 双按键事件；
- 屏幕状态显示；
- 震动控制；
- 电池状态；
- 麦克风触发（如果时间允许）。

### PC / Agent

```text
Python 3.11+
FastAPI / WebSocket
BLE：Bleak
LLM：EvoMap API / 其他模型 API
ASR：云端或本地语音转文字
```

原则：**重模型放 PC / 云端，穿戴端负责低功耗感知和交互。**

---

## 10. 数据与隐私原则

我们不是医疗诊断设备，不输出“你有 ADHD”“你现在焦虑/躁狂”等判断。

比赛展示统一表述为：

- 任务启动状态；
- 注意力漂移；
- 高唤醒/行为变化模式；
- 用户反馈后的个性化策略。

建议采用 **Event-driven sensing**：

- IMU / 按键低功耗常开；
- 麦克风由用户触发或 VAD 触发；
- 摄像头只在事件发生时短时启用；
- 尽量保存结构化语义，不长期保存原始音视频；
- EvoMap 只上传去身份化、已验证的策略，不上传个人原始数据。

---

## 11. 比赛 Demo 脚本

### 90 秒版本

**Step 1｜用户表达困难**  
用户长按设备：
> “我要开始做明天的汇报，但我现在完全不知道从哪开始。”

**Step 2｜Agent 决策**  
系统识别目标过大，只生成一个原子动作：
> “先打开昨天的 PPT。”

**Step 3｜实体干预**  
挂件轻震一次，屏幕显示当前动作。

**Step 4｜用户执行**  
用户完成后单击按钮。

**Step 5｜下一步**  
Agent：
> “新建第一页，只写标题。”

**Step 6｜个性化**  
系统记录：此次“原子动作 + 轻震”成功推动用户启动。

**Step 7｜EvoMap**  
展示这类经过验证的策略如何被整理为去身份化经验，让其他 Agent 继承验证。

评委需要在 1–2 分钟内看懂：

> **AI 不只是提醒用户，而是在现实世界里真正推动用户完成第一步。**

---

## 12. 衡量指标

比赛版优先记录 4 个指标：

| 指标 | 含义 |
|---|---|
| Task Initiation Latency | 从表达目标到真正开始行动的时间 |
| Intervention Success Rate | 干预后成功开始 / 回到任务的比例 |
| Return-to-task Time | 注意力漂移后恢复任务所需时间 |
| False Intervention Rate | 用户正常工作却被误打扰的比例 |

加上主观反馈：**有效 / 卡住 / 完成**。

---

## 13. 队员分工建议

| 角色 | 主要任务 | 必须交付 |
|---|---|---|
| **A｜硬件 / Firmware** | XIAO、BLE、IMU、按键、屏幕、震动、电池 | 穿戴端稳定可用 |
| **B｜Agent / Backend** | ASR、任务原子化、状态机、策略记忆、EvoMap | Agent API + 闭环 |
| **C｜PC / Context / 前端** | BLE 客户端、PC 行为、Dashboard、Demo UI | 可视化和 Context |
| **D｜产品 / Demo / Pitch** | 用户流程、外壳、海报、GitHub README、路演 | 评审材料与现场体验 |

如果只有 2–3 人：A 独立负责硬件，B/C 合并，D 由全员共同承担。

---

## 14. 时间计划

### 9/20｜赛前必须完成

- 确定 MindLoop MVP，不再扩需求；
- 准备 DRV2605L、LRA、电池、线材、外壳；
- 安装 VS Code / PlatformIO / Python 环境；
- 创建 GitHub 仓库及基础 README；
- 注册并检查 EvoMap 账号/API；
- 准备 RJ45 转接头；
- 提前写好 Agent 的 Atomic Task Prompt 与 Demo 测试用例。

### Day 1｜9/21

目标：**硬件与 Agent 分别能独立工作。**

- 确认主控；
- BLE 通信；
- 按键 / 屏幕 / 震动；
- Agent 能把模糊任务拆成一个原子动作；
- 20:00 前完成组队与赛道确认。

### Day 2｜9/22

目标：**核心闭环跑通。**

```text
Button / Voice → Agent → Atomic Action → BLE → Haptic → Feedback
```

16:00–17:00 参加具身与穿戴硬件 Workshop，拿导师反馈。

### Day 3｜9/23

目标：**从工程原型变成产品 Demo。**

- Attention Drift 辅助场景；
- EvoMap 集成；
- 外壳与佩戴；
- 真实用户测试；
- 修 bug；
- 完成海报、GitHub、项目介绍、演示脚本。

### Day 4｜9/24

官方 **11:00 作品封板**。建议内部截止设为 **09:30**。

- 09:30：停止加功能；
- 10:00：最终提交检查；
- 11:00：官方封板；
- 13:00–16:00：游园评审；
- 每位评委约 7 分钟，按 **4 分钟介绍 + 3 分钟问答**准备。

---

## 15. 开发优先级 / Stop Rule

### P0｜没有这些，不算完成

```text
Wearable 可运行
+ Button / Voice 输入
+ Agent 原子任务拆解
+ BLE 双向通信
+ Haptic / Display 输出
+ Done / Stuck 反馈
```

### P1｜完成 P0 后再做

- Attention Drift；
- 个人策略 Memory；
- EvoMap Gene / Capsule；
- 展台 Dashboard。

### P2｜有大量余量才做

- 摄像头；
- PPG / HRV；
- 丢物品；
- 情绪相关长期建模；
- 自研 PCB。

**Stop Rule：P0 没跑稳之前，禁止增加新传感器。**

---

## 16. 项目最终价值表达

不要说：

> “我们做了一个 ADHD 监测手环。”

统一表达：

> **MindLoop 是一个面向执行功能与高认知负荷场景的具身 AI Cognitive Companion。它理解用户想做什么、现在卡在哪里，并把任务缩小成可以立即执行的一步，再通过可穿戴设备用最低干扰的方式推动用户真正行动。**

---

## 19. 2026-09-22 最新交接：XIAO ESP32-S3 已接入

### 已完成

- 已依据 `sheet.md` 确认硬件关系：nRF52840 是主穿戴设备，XIAO ESP32-S3 是无线/上下文扩展节点，reSpeaker 与 RGB Matrix 是后续扩展。
- XIAO ESP32-S3 使用官方 FQBN `esp32:esp32:XIAO_ESP32S3`。
- 修复 Apple Silicon 工具链：使用 `/opt/homebrew/bin/arduino-cli`，避开 Arduino IDE 内置 x86_64 CLI 调用 `xcrun` 的架构错误。
- S3 固件已编译、刷写并实测 USB `hello`、5 秒 `heartbeat`、`context`、`drift`。
- 新增 `mindloop.s3_bridge`，将 S3 事件转发到 Agent 的 `/api/hardware/s3`。
- Agent 会记录 S3 在线状态；活动任务收到 `drift` 时进入漂移状态并执行现有干预策略。
- Python 代码检查通过，原有 20 项测试通过。

### 代码入口

- S3 固件：`mindloop_v0_3/firmware/xiao_esp32s3/xiao_esp32s3.ino`
- S3 协议说明：`mindloop_v0_3/firmware/xiao_esp32s3/README.md`
- S3 桥接：`mindloop_v0_3/mindloop/s3_bridge.py`
- Agent S3 接口：`mindloop_v0_3/mindloop/app.py` 的 `/api/hardware/s3`
- 操作手册：`mindloop_v0_3/OPERATIONS.md`

### 当前限制与下一步

- S3 的 context/drift 仍是演示协议事件，尚未接入真实 IMU、摄像头或 Sense 麦克风。
- 比赛现场继续优先使用 nRF52840 USB 主链路；S3 作为加分项展示，避免阻塞 P0。
- 下一步优先级：真实传感器事件 → S3 bridge → `/api/hardware/s3` → Attention Drift；然后再评估 Wi‑Fi/BLE 和 reSpeaker。

核心关键词：

**Intent-aware · Context-aware · Body-aware · Action-oriented · Self-evolving**

---

## 17. 官方比赛约束

- 赛道：具身与穿戴硬件 / CYBERBODY；
- 官方要求可穿戴/日常硬件让观众能够现场戴上、拿起、使用；自主行动作品应体现“感知—决策—行动”闭环；
- 9 月 21 日 20:00：组队与命题原则上锁定；
- 9 月 24 日 11:00：作品封板、提交系统关闭；
- 9 月 24 日 13:00–16:00：现场游园评审；
- 评审前需准备：项目介绍、GitHub/官网、成员信息、赛道信息及可运行 Demo；
- 官方明确建议自带项目所需硬件和开发环境，不应把现场库存作为唯一保障。

---

## 18. 参考资料

1. 《EvoTavern 进化酒馆黑客松｜深圳站选手指南》（官方选手指南，队内已上传）
2. 《矽递科技 Seeed Studio 具身智能及穿戴硬件赛道设备支持清单》（官方现场硬件清单，队内已上传）
3. Seeed Studio XIAO 0.96'' IPS Display (nRF52840) Wiki  
   https://wiki.seeedstudio.com/getting_started_0.96_inch_display_nrf52840/
4. Seeed Studio reSpeaker XVF3800 Wiki  
   https://wiki.seeedstudio.com/respeaker_xvf3800_introduction/
5. EvoMap Developer Docs / GEP  
   https://evomap.ai/dev/docs

---

### 当前一句话决策

> **比赛只要把“用户卡住 → Agent 给一个最小动作 → 穿戴设备推动用户行动 → 用户反馈 → Agent 学习”这条闭环做稳，我们的项目就成立。其余能力全部是加分项。**
