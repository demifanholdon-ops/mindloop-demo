"""USB bridge for the ESP32-S3 extension node.

The bridge is intentionally independent of the nRF52840 hardware bridge. It
validates the node transport and exposes its liveness to the existing Agent.
"""
import argparse
import asyncio
import json
import logging
import time

import httpx
import serial

LOG = logging.getLogger("mindloop.s3")


async def run(port: str, api: str):
    link = serial.Serial(port, 115200, timeout=0.2)
    link.write(b'{"cmd":"hello"}\n')
    last_event = time.monotonic()
    try:
        while True:
            raw = await asyncio.to_thread(link.readline)
            if not raw:
                if time.monotonic() - last_event > 15:
                    raise RuntimeError("ESP32-S3 heartbeat timeout")
                continue
            try:
                event = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                LOG.warning("invalid S3 frame: %r", raw)
                continue
            last_event = time.monotonic()
            LOG.info("S3 event: %s", event)
            if event.get("event") == "hello":
                LOG.info("ESP32-S3 ready: %s", event)
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
                    response = await client.post(f"{api}/api/hardware/s3", json=event)
                    response.raise_for_status()
            except httpx.HTTPError as exc:
                LOG.warning("Agent S3 status update failed: %s", exc)
    finally:
        link.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/cu.usbmodem1101")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(args.port, args.api))


if __name__ == "__main__":
    main()
