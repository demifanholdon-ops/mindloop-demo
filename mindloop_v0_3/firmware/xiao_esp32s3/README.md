# MindLoop ESP32-S3 BLE Central (0.2)

S3 scans for Nordic UART (accepting `MindLoop` or a missing scan-response name), connects, subscribes to
notifications and sends the nRF52840 JSON `hello`. It forwards wearable events
to USB. This is the first board-to-board transport milestone; Wi-Fi, ASR,
reSpeaker I2S and autonomous Agent calls are not implemented.

Build from `mindloop_v0_3` with ESP32 core 3.3.12 and ArduinoJson 7.4.3:

```sh
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 \
  --output-dir firmware/build_s3 firmware/xiao_esp32s3
# Replace PORT with the S3 port identified by arduino-cli board list.
arduino-cli upload --fqbn esp32:esp32:XIAO_ESP32S3 \
  --port PORT --input-dir firmware/build_s3
```

Implementation follows the installed ESP32 BLE client API and
[Espressif BLE documentation](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ble.html).

## USB protocol (115200, newline-delimited JSON)

Existing `hello`, `ping`, `context`, `drift`, and five-second `heartbeat`
remain supported. `wifi`/`ble` in hello describe capabilities, not connectivity.
Use `ble_connected`/`ble_disconnected` and the wearable `ready` reply to verify
connection and application readiness respectively.

Send a command to the wearable:

```json
{"cmd":"ble_send","payload":{"cmd":"hello"}}
```

Receive its response (fields abbreviated here):

```json
{"event":"wearable","payload":{"event":"ready","display":true}}
{"event":"wearable","payload":{"event":"button","key":"k1","gesture":"single","seq":1}}
```

A `frame` payload uses the existing nRF protocol: `cmd`, `id`, and 3200 lowercase
hex characters representing a 160x80 monochrome bitmap. Only the wearable's
`displayed` event acknowledges drawing. USB input is limited to 4095 bytes;
serialized wearable payloads to 3599 bytes. BLE writes use acknowledged chunks up to the negotiated MTU minus 3
(maximum 244 bytes); a 23-byte MTU falls back to 20-byte chunks. Notifications are reassembled into lines and queued for USB;
overflow and invalid JSON are reported explicitly.

Use `python -m mindloop.hardware_bridge --transport s3` (or double-click
`run_s3.command`) for Agent feedback and Chinese frame rendering through S3.
During active tasks K1 single = DONE, K2 single = STUCK, K2 long = HELP.
The bridge also forwards S3 heartbeat/context/drift to the API. Do not run the
older `s3_bridge` alongside it: both would contend for the same USB port.
BLE disconnect or missing display acknowledgement stops the bridge visibly;
restart it after the wearable reconnects. The S3 firmware reconnects itself.

The Agent and Chinese rendering still run on Mac. Current configuration uses
the local mock Agent; voice over S3, cloud LLM, haptics and autonomous operation
are not validated by this bridge milestone.

## Haptic bench diagnostics (DRV2605L)

Firmware 0.4 adds explicit diagnostic commands for a DRV2605L on the XIAO
default I²C bus (GPIO5/6). Nothing drives the motor unless `haptic` is sent.

```json
{"cmd":"i2c_scan"}
{"cmd":"i2c_read","addr":24,"reg":0,"length":4}
{"cmd":"haptic","action":"status"}
{"cmd":"haptic","action":"play","pattern":"short","motor":"erm"}
{"cmd":"haptic","action":"rtp","level":100,"motor":"lra"}
{"cmd":"haptic","action":"stop"}
```

`i2c_scan` now also reports `addresses_hex`, `drv_present` and, when the driver
acknowledges, `drv_registers` (status/device_id/mode/library/feedback).
`i2c_read` returns Wire errors or the raw bytes; `read_error: 100` means the
address was not acknowledged or returned too few bytes. `haptic` initialises
the driver, reports the registers it read back, and only then plays a waveform
(`pattern`: short/double_soft/success/init) or drives real-time playback
(`rtp`). `motor: erm` writes the ERM feedback path with library 1; `motor: lra`
writes 0xB6 with library 6. Everything else in the protocol is unchanged.

Wire the driver's VIN to 3V3 rather than 5V_IN: the DRV2605L logic thresholds
scale with its own supply, so at 5V a 3.3V I²C bus is marginal. The Flex 2x10
header labelled `X0Dxx`/`X1Dxx` is the *External XVF3800 IO* header, whose pins
belong to the XVF3800 (XMOS port names), not to the XIAO; the XIAO I²C bus is
the row labelled `I2C_SDA`/`I2C_SCL`.

## Bench acceptance (pending)

1. Power the nRF running existing 0.3 firmware; connect S3 USB and open serial.
   Stop other BLE clients so the nRF is available to S3. Stop `s3_bridge` before
   opening its serial port in another program.
2. Expect `ble_connected`, followed by `wearable` with `payload.event=ready`.
   A wearable `invalid_json` error may precede ready: the connection sends a
   newline first to terminate any incomplete command left by the previous link.
3. Send the hello example above; expect another wearable `ready`.
4. Press K1/K2 and hold K2 for at least 800 ms. Expect corresponding
   `button` events: k1/single, k2/single, k2/long (Done/Stuck/Help during tasks).
5. Send a valid `frame`; expect `displayed` with matching ID and inspect screen.
6. Power-cycle nRF; expect disconnect, reconnect and a new ready event.
7. Disconnect nRF and send `ble_send`; expect `wearable_write_failed`.

Discovery scans take two seconds and retry after three seconds. Connection
attempts have a five-second timeout; USB handling may pause during discovery.
Use one MindLoop peripheral for this bench test. Audio over BLE is unsupported.

## Repeatable bench test

```sh
.venv/bin/python scripts/test_s3_ble.py --port /dev/cu.usbmodem101
# Also wait for physical k1 single / k2 single / k2 long:
.venv/bin/python scripts/test_s3_ble.py --port /dev/cu.usbmodem101 --buttons
```

The test asserts wearable ready/display=true and a matching display-frame ID.
It changes the screen to an English BLE test card. Screen appearance and physical
button gestures require the operator; an acknowledgement alone is not visual proof.
Use one Nordic UART peripheral nearby: discovery is service-based and is not pairing.
