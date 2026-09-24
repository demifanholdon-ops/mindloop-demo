# 硬件联调协议（2026-09-24）

已阅读 ZIP 的 `docs/TEAM_UI_HANDOFF_2026-09-23.md`。其中实测 nRF 麦克风可用、马达 `haptic=false`；该包未提供摄像头出图实现。下面为本次新增网关与接口，不能当成旧固件已有能力。

## 当前版本说明

当前默认使用EvoMap任务创建采集。nRF音频开始后在网关累积，收到audio_stop才一次提交 `/api/live/legacy/task`（16kHz PCM16 base64，最多15秒）；不自动重启录音。可附image为当前JPEG或use_camera读取App最近8秒缓存。浏览器本地缓存 `/api/live/legacy/frame` 不调用模型；任务提交时才走千问场景描述→DeepSeek拆解。所有云端失败保留原任务。

下面连续音频、5秒图像与连续固件说明为保留接口，仅启用后续迭代模式时适用。正式联调使用EvoMap固件，旧按键按当前交接，不烧三击修改稿。

## 保留的输入接口

1. nRF USB 保留逐行 JSON：`audio_start` `{sample_rate:16000,channels:1,sample_width:2}`；`audio_chunk` `{seq:0,audio:"base64 PCM"}`，seq 连续递增；`audio_stop` `{dropped:0}`。音频为有符号小端 PCM16。发现丢帧明确报错，不伪造连续语音。新版连续固件取消15秒停止；原版可由网关自动重启。
2. 当前按键：`{"event":"button","key":"k1或k2","gesture":"single|double|long"}`。映射以EvoMap为准，详见当前交接；三击方案在future-iteration分支。网关把事件发送 `/api/live/legacy/button`，返回录音控制或更新同一份App步骤。
3. 摄像头由独立 S3 提供 HTTP JPEG/PNG。网关 `--camera-url` 每5秒取一帧，不依赖旧S3的5000ms心跳。硬件也可通过同一电脑上的转发器 POST 图像，不能把裸二进制、黑屏或心跳当成画面。
4. 语音入口 WebSocket `/api/live/audio`：二进制 PCM（每包≤2秒，建议100ms），控制 `{"type":"flush"}` 切当前句不停连接，`{"type":"stop"}` 停止并等待最后结果。服务返回 ready/sentence/processing/result/error/stopped。前置转写在电脑上，非MCU上。
5. 图像先 POST `/api/live/camera/start` 得 session_id，再 POST `/api/live/image`：`{event_id,session_id,captured_at:带时区ISO时间,image:"data:image/jpeg;base64,..."}`，最后 POST `/api/live/camera/stop` `{session_id}`。event_id 重试保持相同；识别中返回429、过期会话409、无效图片422、模型失败502。只有成功结果改变进度。

## 输出与真实回执

网关每3秒 POST `/api/live/device/heartbeat`：

```json
{"device_id":"usb-demo","capabilities":{"microphone":true,"haptic_pattern":true,"breathing_light":false}}
```

这些能力必须来自设备 `ready` 的真实声明；原 `haptic:true` 不够，因为仅支持短波形，不能冒充固定节奏。15秒无心跳即视为离线。

网关 POST `/api/live/device/next` `{device_id}`，服务器一次只领取一条，保持排队顺序。偏离的输出示例：

```json
{"cmd":"haptic_pattern","id":"cmd_...","pattern_ms":[2000,2000,2000,2000,2000],"light":"off"}
```

数组表示：震2秒、停2秒、震2秒、停2秒、震2秒。Reminder 使用相同节奏加 `light:"breathing"`；当前无扬声器，不调用TTS。没有对应能力时保持未执行，不用一个短振动偷换整组动作。

设备需**整组动作真正结束**后回：

```json
{"event":"haptic_done","id":"cmd_..."}
```

失败回 `haptic_failed` 和同一 id。网关再 POST `/api/live/device/commands/{id}/ack` `{device_id,executed:true|false,error:null|"原因"}`。收到命令不等于已完成。网关20秒未收到成功回执记失败；服务端30秒仍未确认记执行未知并释放队列，不自动重播可能已经振过的组。

`nrf_continuous.ino` 只改连续录音与三击，**尚未实现或验证这个新的持续震动/呼吸灯协议**。硬件同学明早需要根据真实驱动和接线补齐，不能把软件队列通过视为马达通过。

## 后续迭代硬件核验清单（不作为当前按键/采集流程）

- 提供实际USB串口、S3真实JPEG URL；核对手机/摄像头画面来源。
- 编译烧录连续录音与三击补丁；测试连续说两句、录音超过15秒、最后一句停止时不丢尾音。
- 修复既有 `haptic=false`，核对马达和灯实际能力；按上面新增命令+回执接入。
- 实拍“打开工具/文档 → App 勾选”，离开工作场景5秒规则；确认三击/“我回归了”只落最近一次。
- 记录“实际拍摄→判定→马达开始”的真实延迟。现有软件样本不包含S3传图、蓝牙、马达驱动或真实摄像头识别误差。
