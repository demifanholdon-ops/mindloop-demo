# MindLoop XIAO firmware

Current firmware: **0.8**. Current controls and limitations: [Interaction guide](../../docs/INTERACTION.md). Older descriptions below are superseded by this guide.


Target: XIAO nRF52840 Plus + 0.96-inch IPS; no external hardware.
Dependencies: Seeeduino nRF52 1.1.13, Seeed_GFX2 1.0.0, ArduinoJson 7.4.3.
Official pin map and recovery: https://wiki.seeedstudio.com/getting_started_0.96_inch_display_nrf52840/

- LCD: CS D2, DC D3, SCK D8, MOSI D10, reset D17 (38), backlight D18 (37).
- KEY1/D6 and KEY2/D7 report single, double and >=800 ms long gestures. Debounce: 30 ms.
- USB 115200; BLE Nordic UART, name MindLoop.
- Onboard PDM microphone: DATA D1, CLK D0, mono PCM16 at 16 kHz. Voice audio currently uses USB only.
- DRV2605L haptic commands are implemented; readiness depends on I2C initialization. IMU/battery are not implemented.

Button meaning depends on session state. On the idle screen, K1 single starts/stops voice task input. During a task, K1 single is done, K2 single is stuck, and K2 long is help. On the completed screen, K1 starts a new session and K2 reopens the final action. The Mac bridge performs state-aware routing.

## Build / upload

From `mindloop_v0_3`, activate `.venv` first (Seeed tools require `python`).
CLI on this Mac: `/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli`.
Use that absolute path in place of `arduino-cli` below if not in PATH.

```sh
source .venv/bin/activate
arduino-cli compile --fqbn Seeeduino:nrf52:xiaonRF52840Plus --library firmware/vendor/Seeed_GFX2-1.0.0 --output-dir firmware/build firmware/xiao_nrf52840
arduino-cli upload --fqbn Seeeduino:nrf52:xiaonRF52840Plus --port /dev/cu.usbmodem1101 --input-dir firmware/build
```

Vendor source: https://github.com/Seeed-Studio/Seeed_GFX2/archive/refs/tags/v1.0.0.zip (extract into ignored firmware/vendor/).
Install JSON library: `arduino-cli lib install ArduinoJson@7.4.3`.
Official factory recovery image saved at ignored `firmware/recovery/factory.uf2`. Double-click reset and copy it to NRF52BOOT to restore. This is the vendor image, not a readback of this unit.

The XIAO Plus bootloader uses UF2 family ID `0x28860064`. It ignores a generic `NRF52` UF2. Use Arduino CLI serial DFU for normal updates after the app is running.

## Run

Normal one-click run starts the server, USB bridge, and browser:
```sh
./run_demo.command
```

Manual run, terminal 1, from `mindloop_v0_3`:
```sh
.venv/bin/python -m uvicorn mindloop.app:app --host 127.0.0.1 --port 8000
```
Terminal 2:
```sh
.venv/bin/python -m mindloop.hardware_bridge --transport usb
# Alternative, after stopping USB bridge:
.venv/bin/python -m mindloop.hardware_bridge --transport ble
```

Open http://127.0.0.1:8000 and start a task. Chinese actions render on the Mac, then go to the screen. Long text paginates every four seconds. Buttons call the existing Agent feedback endpoint. Screen redraws with the resulting action.

Only run ONE bridge. Disconnect/missing display acknowledgements fail visibly; restart after reconnecting. BLE may require macOS Bluetooth permission. Existing dashboard vibration remains simulation; no motor is connected.

## Protocol

Newline-delimited JSON, max line 3599 bytes.
- Host `{"cmd":"hello"}` -> ready event with firmware, dimensions, display status, haptic=false.
- Host `{"cmd":"frame","id":1,"hex":"..."}`: 1600 monochrome bytes, 3200 lowercase hex characters, 160x80 row-major/MSB first.
- Device `{"event":"displayed","id":1}` acknowledges completed draw call, not visual inspection.
- Host `{"cmd":"record","action":"start|stop"}` controls microphone capture over USB.
- Device sends `audio_start`, ordered base64 `audio_chunk`, then `audio_stop` with its dropped-byte count.
- Device `{"event":"button","key":"k1","gesture":"single","seq":1}`.
- Unsupported or invalid commands return error JSON.

BLE service: 6e400001-b5a3-f393-e0a9-e50e24dcca9e; host writes ...0002, subscribes ...0003. Bridge uses 20-byte acknowledged writes and reassembles notifications.

Tests: `.venv/bin/python -m unittest discover -s tests -v`.

BLE output is explicitly split into 20-byte writes, including button events; failed writes disconnect to prevent partial JSON lines being reused. `{"cmd":"ble_status"}` reports BLE initialization, advertising start/current state and connection count.

BLE now configures BANDWIDTH_MAX and prefers 7.5–15 ms connection intervals. The S3 Central requests MTU 247 and the same interval; actual negotiated performance is measured with scripts/test_s3_ble.py.
