# MindLoop V0.3 Status

## 2026-09-24 nRF52840 firmware 0.8

- Removed the computer-only startup wording. The display now distinguishes automatic USB/S3 connection, an attached S3 gateway, and an Agent-ready link.
- Added `gateway_linked` and `agent_ready` to the ready handshake plus a `gateway_status` command for the future standalone S3 runtime.
- Compiled and flashed on the real nRF52840; the S3 automatically reconnected and received `gateway_linked=true, agent_ready=false`. The USB bridge then reconnected, reported firmware 0.8, and acknowledged display frame 1.
- This removes the nRF-side dependency and misleading startup state. Full computer-free voice/LLM operation still requires moving transcription and the cloud Agent runtime to the Wi-Fi-capable S3.

## 软件完成度
- [x] Task initiation Agent
- [x] Atomic action decomposition
- [x] STUCK shrink
- [x] HELP alternative
- [x] Haptic/light/voice intervention policy
- [x] Wearable simulator
- [x] Task initiation latency
- [x] Return-to-task time
- [x] Mac digital context V0
- [x] Attention drift V0
- [x] Voice input
- [x] Polished hackathon dashboard
- [x] Guided one-click demo
- [x] EvoMap Gene + Capsule builder
- [x] EvoMap hello integration
- [x] EvoMap validate integration
- [x] EvoMap publish integration with explicit confirmation
- [x] BLE adapter skeleton
- [x] Mac setup/run scripts

## Hardware P0
- [ ] XIAO BLE link
- [ ] Haptic driver
- [x] Button events
- [ ] IMU events
- [x] Display action

## Hardware P1
- [ ] Battery
- [ ] Enclosure / pendant
- [x] Onboard mic pipeline (USB)
- [ ] Optional physiological sensor

## 2026-09-22 hardware integration update

- USB identifies XIAO nRF52840 Plus; user confirms factory display works and no external hardware is connected.
- Added Arduino firmware: USB/BLE Nordic UART, 160x80 screen bitmap protocol, D6/D7 done/stuck and long-press help. No haptic/IMU implementation.
- Added Python hardware_bridge: Chinese rendering/pagination and feedback forwarding to existing Agent API.
- Compiled with Seeeduino nRF52 1.1.13, Seeed_GFX2 1.0.0 and ArduinoJson 7.4.3: flash 174788 bytes; static RAM 23712 bytes.
- Python 3.11 virtual environment installed; eleven Agent/session/rendering/protocol/mock bridge tests pass.
- Firmware installed and physically verified. USB handshake reports display ready. Device acknowledged Chinese action frames. User confirmed display and controls work. Hardware events recorded 2 done and 3 stuck feedback actions in Agent state.
- BLE service and advertising start successfully, but macOS Bluetooth is currently off, so end-to-end BLE transport is not yet tested; current verified transport is USB.
- Fixed local HTTP proxy leakage in hardware_bridge by disabling environment proxy use for the loopback Agent API.
- Fixed repeated stuck feedback producing nested `只做“只做…”` actions. Mock shrink now converges to `只输入标题的第一个字`; regression test added.
- `run_demo.command` now starts the Agent server, USB hardware bridge, and browser together.
- Initial manual UF2 failed because the generic nRF52 family ID was ignored. XIAO Plus requires `0x28860064`; documented for recovery.
- Official factory recovery image saved locally under firmware/recovery/factory.uf2.
- Completed-session navigation added and physically verified: completed K1 starts a new session; completed K2 reopens the final action. The screen and Dashboard show both choices. During active tasks, K1/K2 retain Done/Stuck behavior.
- Onboard microphone task input implemented in firmware 0.3: idle K1 toggles 16 kHz PCM capture, USB sends ordered base64 chunks, Mac MLX Whisper transcribes Chinese locally, and the transcript starts a task automatically. Hardware diagnostic captured 3.008 seconds in 376 continuous chunks with zero dropped bytes. Firmware reports microphone/display ready; 20 software tests pass. The local `whisper-base-mlx` model is installed and cached. BLE audio is not implemented.
- ESP32-S3 extension integrated for the official Seeed `XIAO_ESP32S3` board: additive USB JSON hello/ping protocol, five-second heartbeat, independent `mindloop.s3_bridge`, and `/api/hardware/s3` liveness state. `sheet.md` confirms the S3 is the wireless/context extension alongside the nRF52840 wearable, reSpeaker and RGB Matrix. Homebrew arm64 Arduino CLI fixed the x86_64 `xcrun` conflict; firmware compiled, flashed, and returned hello plus heartbeat on `/dev/cu.usbmodem1101`.
- S3 now also emits `context` and `drift` events; the bridge forwards them to `/api/hardware/s3`, and an active Agent session converts S3 `drift` into the existing intervention path. Firmware recompiled/flashed and direct serial verification returned all event types.
- reSpeaker Flex XVF3800 is connected and enumerated by macOS as USB audio: 6 input channels, 2 output channels, 16 kHz. Added `scripts/test_respeaker.py` and `sounddevice` dependency. Live capture now passes: 1600 frames, 6 channels at 16 kHz; script reports peak/RMS. Audio is not yet routed into Whisper/Agent; nRF52840 remains current task-voice path.

## 2026-09-23 board-to-board BLE transport

- Implemented S3 0.2 BLE Central using the existing nRF Nordic UART JSON protocol:
  service/name discovery, notification subscription, automatic hello, bounded
  USB JSON commands, 20-byte acknowledged BLE writes, notification reassembly,
  visible overflow errors and reconnect retries.
- `ble_send` wraps nRF commands; `wearable` wraps received ready/displayed/button
  events. Existing S3 hello/ping/context/drift/heartbeat remain available.
- Added build and bench acceptance instructions in firmware/xiao_esp32s3/README.md.
- No development-board USB ports were present during implementation; no firmware
  was flashed and board-to-board operation remains unverified.
- Next: attach both boards, flash S3, verify hello, K1/K2/long K2, display frames
  and reconnection. The Python S3 bridge still only reports liveness/context;
  routing wearable events to Agent and rendering via S3 remain to be implemented.
- IMU, DRV2605L/LRA, reSpeaker I2S and S3 Wi-Fi/ASR remain pending.
- Final Arduino compile passed with `esp32:esp32:XIAO_ESP32S3` (core 3.3.12):
  603652 bytes Flash (18%), 35288 bytes static RAM (10%). Build artifacts are
  in `/tmp/mindloop-s3-ble-build`; rebuild into firmware/build_s3 before using
  the README upload command.

## 2026-09-23 attached-board verification

- Both boards enumerated: nRF `/dev/cu.usbmodem1101` (2886:8064), S3
  `/dev/cu.usbmodem101` (303a:1001). Ports are session-specific.
- S3 0.2 flashed with verified flash hashes; USB hello reports mindloop-s3-0.2
  and heartbeats were received.
- nRF currently runs DASH096 dashboard (observed battery/IMU/mic serial logs),
  superseding the earlier assumption that MindLoop 0.3 remained installed.
- nRF MindLoop source recompiles successfully (178560 bytes flash, 33500 RAM).
  Serial DFU upload failed with `Timed out waiting for acknowledgement from
  device` even though Arduino CLI eventually returned exit 0. Do not count this
  as a successful upload. Manual 1200-baud touch removes USB temporarily, then
  returns application PID 8064; no bootloader volume was observed.
- Next physical step: double-click nRF RESET to enter bootloader, then retry
  uploading and verify the MindLoop ready response before BLE acceptance.

## 2026-09-23 BLE real-device milestone

- Manual double RESET entered XIAO-BOOT (USB PID 0064); nRF upload then returned
  `Device programmed`. MindLoop ready over USB confirmed display/microphone=true.
- S3 and nRF now complete real BLE hello and display-frame acknowledgement.
  `scripts/test_s3_ble.py --port /dev/cu.usbmodem101` passed with matching frame
  ID 790151303; measured full frame round trip 18.149 s (requires optimization).
- User confirmed the `MindLoop BLE OK` card is visible. S3 received k1/single
  and k2/single events, followed by k2/long seq=10. All three required gestures passed.
- Fixed two transport defects: discovery rejected service advertisements with
  missing scan-response name; nRF BLEUart truncated whole-line writes at the
  characteristic length. nRF now writes <=20-byte chunks with bounded retries
  for temporarily full notification queues, and disconnects on timeout.
- Added nRF `ble_status` command and a repeatable hardware acceptance script.
  Temporary scan logs removed. Final builds: S3 flash 603744 bytes / static RAM
  35288; nRF flash 193272 / static RAM 33508. Both flashed successfully.
## 2026-09-23 BLE frame-rate optimization

- Root cause of the 18.149 s measured frame round trip: nRF `reply()` hard-coded
  20-byte BLE chunks, so a 3,360-byte frame needed ~168 `notify` calls, each
  spinning in a 2 s stall loop. The Bluefruit `BLEUart` unbuffered `notify()`
  path already splits at the negotiated MTU (244-byte payload at the 247 MTU
  negotiated by the S3 central) and returns 0 when the SoftDevice hvn queue is
  full.
- Fix: `reply()` now passes the whole JSON line in one `uart.write()` and
  retries the full line until the notify completes or a 4 s deadline is hit.
  Library-level MTU splitting does the chunking; the retry loop handles
  backpressure.
- Logic-level verification (serial probe blocked by macOS port permission, so
  no live measurement): ~168 notify calls → 5 (97% fewer); worst case bounded
  from ~336 s to 4 s; nominal path ≈ 14 packets × 10 ms interval ≈ 140 ms per
  frame.
- Rebuilt: flash 194976 bytes (24%), global vars 58980 bytes (24.8%). All 30
  Python tests still pass. Firmware not yet flashed to the nRF (port access
  blocked this session).
- Still pending: flash + live re-measure of frame round trip, explicit
  reconnect test, Agent routing through S3 (bridge support exists, needs
  live run), reSpeaker/ASR/Wi-Fi and haptics.

## 2026-09-23 live re-measurement and real bottleneck (firmware 0.5)

- Serial access was re-granted (sandbox elevation). Ports had been re-numbered
  by macOS after replug: nRF = /dev/cu.usbmodem21301, S3 = /dev/cu.usbmodem21201.
  Do not hard-code 1101/101; enumerate with the VID/PID identity check the
  bridge already performs.
- Baseline on old firmware (mindloop-0.4, 20-byte reply): test_s3_ble.py frame
  round trip 2.284 s. USB-direct same frame: 1.89 s. Surprise: the reply()
  chunking was NOT the dominant cost — the screen blit was.
- Root cause #2: Seeed_GFX2 `drawBitmap()` is a per-pixel loop calling
  `drawPixel()` 160×80 = 12800 times, each a separate window+write bus
  transaction (~1.9 s). Fixed with a batch path: `setAddrWindow(0,0,160,80)` +
  per-row `pushPixels()` on a 160-entry RGB565 line buffer (white 0xFFFF /
  black 0x0000), one bulk write per row instead of 12800 single pixels.
- Firmware version bumped to mindloop-0.5 so the flashed build is verifiable.
  Upload: `arduino-cli upload --fqbn Seeeduino:nrf52:xiaonRF52840Plus --port
  /dev/cu.usbmodem21301 --input-dir firmware/build`.
- Measured after upload (firmware 0.5):
  - hello over S3 BLE: 30 ms (stable).
  - frame 1600 B over S3 BLE: 0.450 s (from 2.284 s → 5.1× faster).
  - frame 1600 B USB-direct: 59.5 ms (from 1.89 s → 31× faster; includes
    3200-hex parse + blit + reply).
- Remaining latency is transport-bound (USB 115200 baud ~286 ms for the
  3.3 KB frame body + BLE transfer), not firmware. Raising the S3/Nordic
  serial baud or shortening the JSON frame format would be the next lever.
- Added scripts/probe_s3_ble_latency.py: repeatable per-size latency probe
  (hello vs full frame) for future regression checks. Note: firmware rejects
  any frame whose hex is not exactly 3200 chars.
- Still pending: explicit reconnect test, Agent routing through S3 (bridge
  support exists, needs live run), reSpeaker/ASR/Wi-Fi and haptics.
