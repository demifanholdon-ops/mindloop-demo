#!/usr/bin/env python
"""Profile MindLoop S3->BLE->nRF round-trip latency by payload size.

Splits the frame path into pieces so we can tell whether the 2.2 s delay
observed in test_s3_ble.py is a transport-bandwidth problem (delay ~ payload
size) or a fixed per-operation cost (delay flat across sizes, e.g. drawBitmap
or a slow handshake).

Usage (from mindloop_v0_3):
    .venv/bin/python scripts/probe_s3_ble_latency.py --port /dev/cu.usbmodem21201
"""
import argparse
import json
import time
import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    with serial.Serial(args.port, 115200, timeout=0.25) as link:
        def send(payload):
            link.write((json.dumps({"cmd": "ble_send", "payload": payload}) + "\n").encode())

        def wait_for(predicate, timeout, label):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                raw = link.readline()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except (ValueError, UnicodeError):
                    continue
                if predicate(event):
                    return event
            raise TimeoutError(f"{label}: no response in {timeout}s")

        def hello_rtt():
            started = time.monotonic()
            send({"cmd": "hello"})
            wait_for(lambda e: e.get("event") == "wearable" and
                     e.get("payload", {}).get("event") == "ready", 30, "hello")
            return time.monotonic() - started

        def frame_rtt(hexlen, frame_id):
            started = time.monotonic()
            send({"cmd": "frame", "id": frame_id, "hex": "00" * hexlen})
            wait_for(lambda e: e.get("event") == "wearable" and
                     e.get("payload", {}).get("event") == "displayed" and
                     e["payload"].get("id") == frame_id, 30, "frame")
            return time.monotonic() - started

        # warm-up / handshake
        hello_rtt()

        print(f"{'payload':>10} {'repeat':>6} {'rtt_s':>8}")
        # hello is a small message: transport fixed-cost baseline
        for i in range(args.repeats):
            print(f"{'hello':>10} {i+1:>6} {hello_rtt():8.3f}")

        # frames must be exactly 1600 bytes (3200 hex chars) per firmware
        for i in range(args.repeats):
            print(f"{'frame:1600B':>10} {i+1:>6} {frame_rtt(1600, i):8.3f}")


if __name__ == "__main__":
    main()
