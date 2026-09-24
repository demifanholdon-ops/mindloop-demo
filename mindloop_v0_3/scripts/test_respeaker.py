"""Enumerate and validate reSpeaker Flex XVF3800 Core Audio device."""
import argparse
import json
import sys

import numpy as np
import sounddevice as sd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true", help="capture short audio test")
    args = parser.parse_args()
    devices = sd.query_devices()
    matches = [
        (i, d) for i, d in enumerate(devices)
        if "respeaker" in d["name"].lower() or "xvf3800" in d["name"].lower()
    ]
    if not matches:
        print(json.dumps({"ok": False, "reason": "reSpeaker_not_found"}))
        return 1
    index, device = matches[0]
    result = {
        "ok": True,
        "device_index": index,
        "name": device["name"],
        "input_channels": int(device["max_input_channels"]),
        "output_channels": int(device["max_output_channels"]),
        "default_samplerate": device["default_samplerate"],
        "sample_rate": 16000,
    }
    if args.capture:
        # Use blocking stream; caller can terminate process if Core Audio permission
        # prompt blocks. Enumeration remains a valid USB connectivity check.
        with sd.InputStream(device=index, samplerate=16000, channels=6, dtype="int16") as stream:
            data, _ = stream.read(1600)
        values = data.astype(np.int64)
        result.update({
            "captured_frames": len(data),
            "capture_channels": len(data[0]),
            "peak": int(np.max(np.abs(values))),
            "rms": int(np.sqrt(np.mean(values * values))),
        })
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
