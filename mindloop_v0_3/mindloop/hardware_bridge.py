"""USB/BLE bridge: existing Agent HTTP API <-> MindLoop wearable.

Run one bridge only. Chinese text is rasterized on the Mac, preserving the
Agent's actual wording without a large firmware font or translation fallback.
"""
import argparse
import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from mindloop.voice import AudioCapture, MLXWhisperTranscriber, VoiceInputError

LOG = logging.getLogger("mindloop.hardware")
RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
RECOVERABLE_DEVICE_ERRORS = {"invalid_json", "wearable_write_failed", "ble_connect_failed", "ble_disconnected"}


def is_recoverable_device_error(reason):
    return reason in RECOVERABLE_DEVICE_ERRORS


def screen_copy(state, hint_page=0):
    if state.get("state") == "notice":
        return state["current_action"], "稍后自动返回"
    if state.get("state") == "voice_recording":
        return "正在听，请说出任务", "单K1 结束录音"
    if state.get("state") == "voice_generating":
        return "正在结合目标生成步骤…", "请稍候"
    if state.get("state") == "voice_transcribing":
        return "正在识别语音…", "请稍候"
    if state.get("state") == "voice_stopping":
        return "正在结束录音…", "请稍候"
    if state.get("state") == "voice_error":
        return state.get("voice_error", "语音输入失败"), "单K1 重新录音"
    if state.get("state") == "completed":
        return "任务完成", "K1 新任务 K2 重做末步"
    if state.get("state") == "idle":
        return "按 K1 开始语音输入", "长K2 恢复上次任务" if state.get("can_resume") else "再按 K1 结束并创建任务"
    hints = (
        "单K1 完成  单K2 卡住",
        "双K1 撤回  双K2 换法",
        "长K1 暂存并新建",
    )
    return state.get("current_action") or "等待任务", hints[hint_page % len(hints)]


def button_request(state, key, gesture):
    if state.get("state") == "idle":
        return ("/api/session/continue", None) if (key, gesture) == ("k2", "long") else (None, None)
    if state.get("state") == "completed":
        if (key, gesture) == ("k1", "single"):
            return "/api/session/new", None
        if (key, gesture) == ("k2", "single"):
            return "/api/session/continue", None
        return None, None
    requests = {
        ("k1", "single"): ("/api/feedback", {"feedback": "done"}),
        ("k1", "double"): ("/api/session/undo", None),
        ("k1", "long"): ("/api/session/new", None),
        ("k2", "single"): ("/api/feedback", {"feedback": "stuck"}),
        ("k2", "double"): ("/api/feedback", {"feedback": "help"}),

    }
    return requests.get((key, gesture), (None, None))


def button_gesture(event):
    if event.get("key") in {"k1", "k2"} and event.get("gesture") in {"single", "double", "long"}:
        return event["key"], event["gesture"]
    legacy = {
        "done": ("k1", "single"),
        "stuck": ("k2", "single"),
        "help": ("k2", "double"),
    }
    return legacy.get(event.get("value"), (None, None))


def voice_button_action(state, recording, key, gesture, transport):
    if recording in {"transcribing", "stopping", "generating"}:
        return "ignore"
    if recording is True or recording == "recording":
        return "stop" if (key, gesture) == ("k1", "single") else "ignore"
    if key != "k1" or gesture != "single":
        return None
    if state.get("state") != "idle":
        return None
    return "start" if transport in {"usb", "s3"} else "usb_only"


async def transcribe_capture(capture, transcriber):
    descriptor, name = tempfile.mkstemp(prefix="mindloop-", suffix=".wav")
    os.close(descriptor)
    path = Path(name)
    try:
        result = capture.finish(path)
        text = await asyncio.to_thread(transcriber.transcribe, path)
        return text, result
    finally:
        path.unlink(missing_ok=True)


def render_frame(state, font_path, page=0):
    font = ImageFont.truetype(font_path, 14)
    footer_font = ImageFont.truetype(font_path, 10)
    image = Image.new("1", (160, 80), 0)
    draw = ImageDraw.Draw(image)
    text, footer = screen_copy(state, page)
    lines, line = [], ""
    for char in text:
        if char == "\n" or draw.textlength(line + char, font=font) > 152:
            lines.append(line)
            line = "" if char == "\n" else char
        else:
            line += char
    if line or not lines:
        lines.append(line)
    pages = (len(lines) + 2) // 3
    page %= pages
    draw.text((4, 1), f"MindLoop {state.get('progress', {}).get('done', 0)}/{state.get('progress', {}).get('total', 0)}  {page+1}/{pages}", fill=1)
    for i, line in enumerate(lines[page*3:page*3+3]):
        draw.text((4, 16 + i*16), line, font=font, fill=1, anchor="lt")
    draw.text((4, 68), footer, font=footer_font, fill=1)
    return image.tobytes().hex()


class Link:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.buffer = bytearray()
        self.voice_buffer = bytearray()
        self.serial = None
        self.voice_serial = None
        self.client = None
        self.reader = None
        self.voice_reader = None
        self.transport = "usb"

    def receive(self, data, voice=False):
        buffer = self.voice_buffer if voice else self.buffer
        buffer.extend(data)
        while b"\n" in buffer:
            line, _, rest = buffer.partition(b"\n")
            buffer[:] = rest
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    if voice and event.get("event") not in {"audio_start", "audio_chunk", "audio_stop"}:
                        continue
                    if self.transport == "s3" and not voice:
                        kind = event.get("event")
                        if kind == "wearable":
                            event = event.get("payload")
                            if not isinstance(event, dict):
                                event = {"error": "invalid_wearable_payload"}
                        elif kind == "ble_disconnected":
                            event = {"event": "wearable_link", "connected": False}
                        elif kind == "ble_connected":
                            event = {"event": "wearable_link", "connected": True}
                        elif kind == "error":
                            event = {"error": event.get("reason", "s3_error")}
                        elif kind in {"hello", "heartbeat", "context", "drift"}:
                            event = {"event": "s3_status", "payload": event}
                        else:
                            continue
                    self.queue.put_nowait(event)
            except (ValueError, UnicodeError):
                LOG.debug("Ignoring non-JSON device output")
        if len(buffer) > 8192:
            buffer.clear()

    async def open(self, args):
        self.transport = args.transport
        if args.transport in {"usb", "s3"}:
            import serial
            from serial.tools.list_ports import comports
            identity = (0x303A, 0x1001) if self.transport == "s3" else (0x2886, 0x8064)
            ports = [p.device for p in comports() if (p.vid, p.pid) == identity]
            port = args.port or (ports[0] if len(ports) == 1 else None)
            if not port:
                raise RuntimeError("Specify --port: expected one connected XIAO")
            self.serial = serial.Serial(port, 115200, timeout=0.1, write_timeout=2)
            async def read():
                while True:
                    self.receive(await asyncio.to_thread(self.serial.read, 1024))
            self.reader = asyncio.create_task(read())
            LOG.info("USB connected: %s", port)
            if self.transport == "s3":
                voice_ports = [p.device for p in comports() if (p.vid, p.pid) == (0x2886, 0x8064)]
                if len(voice_ports) == 1:
                    self.voice_serial = serial.Serial(voice_ports[0], 115200, timeout=0.1, write_timeout=2)
                    async def read_voice():
                        while True:
                            self.receive(await asyncio.to_thread(self.voice_serial.read, 1024), voice=True)
                    self.voice_reader = asyncio.create_task(read_voice())
                    LOG.info("Wearable voice USB connected: %s", voice_ports[0])
                else:
                    LOG.warning("Wearable voice USB unavailable; expected one nRF52840 USB port")
        else:
            from bleak import BleakClient, BleakScanner
            target = args.address or await BleakScanner.find_device_by_name("MindLoop", timeout=10)
            if not target:
                raise RuntimeError("MindLoop BLE advertisement not found")
            self.client = BleakClient(target)
            await self.client.connect()
            await self.client.start_notify(TX, lambda _, data: self.receive(data))
            LOG.info("BLE connected")

    async def send(self, command):
        target = self.serial
        if self.transport == "s3" and command.get("cmd") == "record" and self.voice_serial:
            target = self.voice_serial
        elif self.transport == "s3":
            command = {"cmd": "ble_send", "payload": command}
        data = (json.dumps(command, separators=(",", ":")) + "\n").encode()
        if target:
            await asyncio.to_thread(target.write, data)
        else:
            for i in range(0, len(data), 20):
                await self.client.write_gatt_char(RX, data[i:i+20], response=True)

    async def close(self):
        if self.reader:
            self.reader.cancel()
            await asyncio.gather(self.reader, return_exceptions=True)
        if self.voice_reader:
            self.voice_reader.cancel()
            await asyncio.gather(self.voice_reader, return_exceptions=True)
        if self.serial:
            self.serial.close()
        if self.voice_serial:
            self.voice_serial.close()
        if self.client and self.client.is_connected:
            await self.client.disconnect()


async def wait_ready(link, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await link.send({"cmd": "hello"})
        attempt_end = min(deadline, time.monotonic() + 2)
        while time.monotonic() < attempt_end:
            if link.reader and link.reader.done():
                link.reader.result()
            try:
                event = await asyncio.wait_for(link.queue.get(), attempt_end - time.monotonic())
            except asyncio.TimeoutError:
                break
            if event.get("event") == "ready":
                if not event.get("display"):
                    raise RuntimeError(f"Display unavailable: {event}")
                return event
            if event.get("error") not in {None, "invalid_json", "wearable_write_failed", "ble_connect_failed", "ble_disconnected"}:
                raise RuntimeError(f"Handshake failed: {event}")
    raise TimeoutError("Wearable ready handshake timed out")


async def bridge(args):
    link = Link()
    transcription = None
    generation = None
    try:
        await link.open(args)
        ready = await wait_ready(link, 30 if getattr(args, "transport", "usb") == "s3" else 5)
        LOG.info("Firmware ready: %s; haptic=%s", ready.get("firmware"), ready.get("haptic"))
        last_frame, pending_id, frame_id = None, None, 0
        sent_at, page_started = 0.0, time.monotonic()
        last_action = None
        last_haptic = None
        haptic_ready = bool(ready.get("haptic"))
        wearable_connected = True
        capture = AudioCapture()
        transcriber = MLXWhisperTranscriber()
        voice_mode = None
        voice_error = None
        voice_error_until = 0.0
        transcription = None
        notice, notice_until = None, 0.0
        last_hello = time.monotonic()
        # The bridge talks to a local server. Ignore system HTTP proxy settings,
        # which can otherwise turn 127.0.0.1 requests into proxy 502 responses.
        async with httpx.AsyncClient(base_url=args.api, timeout=30, trust_env=False) as api:
            while True:
                if link.reader and link.reader.done():
                    link.reader.result()
                if link.client and not link.client.is_connected:
                    raise ConnectionError("BLE disconnected")
                while not link.queue.empty():
                    event = link.queue.get_nowait()
                    if event.get("event") == "s3_status":
                        response = await api.post("/api/hardware/s3", json=event["payload"])
                        response.raise_for_status()
                    elif event.get("event") == "wearable_link":
                        wearable_connected = bool(event.get("connected"))
                        if not wearable_connected:
                            pending_id = None
                        LOG.info("Wearable BLE %s; S3 will reconnect automatically", "connected" if wearable_connected else "disconnected")
                    elif event.get("event") == "ready":
                        was_connected = wearable_connected
                        wearable_connected = True
                        haptic_ready = bool(event.get("haptic"))
                        if not was_connected:
                            pending_id = None
                            last_frame = None
                            LOG.info("Wearable ready after reconnect: %s", event.get("firmware"))
                    elif event.get("event") == "button":
                        key, gesture = button_gesture(event)
                        if key is None:
                            LOG.warning("Unknown button event: %s", event)
                            continue
                        latest = await api.get("/api/state")
                        latest.raise_for_status()
                        voice_action = voice_button_action(
                            latest.json(), voice_mode,
                            key, gesture, getattr(args, "transport", "usb"),
                        )
                        if voice_action == "start":
                            await link.send({"cmd": "record", "action": "start"})
                            voice_mode = "recording"
                            voice_error = None
                            LOG.info("Voice recording requested")
                            continue
                        if voice_action == "stop":
                            await link.send({"cmd": "record", "action": "stop"})
                            voice_mode = "stopping"
                            LOG.info("Voice recording stop requested")
                            continue
                        if voice_action == "usb_only":
                            voice_mode, voice_error = "error", "请在电脑上输入任务"
                            voice_error_until = time.monotonic() + 4
                            continue
                        if voice_action == "ignore":
                            LOG.info("Button ignored during voice capture: %s %s", key, gesture)
                            continue
                        path, payload = button_request(latest.json(), key, gesture)
                        if path is None:
                            notice = "此操作不可用，请按屏幕提示"
                            notice_until = time.monotonic() + 2.5
                            continue
                        response = await api.post(path, json=payload)
                        if response.status_code in {400, 409, 502}:
                            notice = response.json().get("detail", "此操作暂不可用")
                            notice_until = time.monotonic() + 2.5
                        else:
                            response.raise_for_status()
                            LOG.info("Button -> Agent: %s %s (%s)", key, gesture, path)
                    elif event.get("event") == "audio_start":
                        try:
                            capture.start(event)
                            voice_mode = "recording"
                        except VoiceInputError as exc:
                            voice_mode, voice_error = "error", str(exc)
                            voice_error_until = time.monotonic() + 4
                    elif event.get("event") == "audio_chunk":
                        try:
                            capture.add_chunk(event)
                        except VoiceInputError as exc:
                            await link.send({"cmd": "record", "action": "stop"})
                            voice_mode, voice_error = "error", str(exc)
                            voice_error_until = time.monotonic() + 4
                    elif event.get("event") == "audio_stop":
                        if voice_mode == "error":
                            continue
                        if event.get("dropped", 0):
                            voice_mode, voice_error = "error", f"音频传输过载：丢失 {event['dropped']} 字节，请重试"
                            voice_error_until = time.monotonic() + 4
                        else:
                            voice_mode = "transcribing"
                            transcription = asyncio.create_task(transcribe_capture(capture, transcriber))
                    elif event.get("event") == "displayed" and event.get("id") == pending_id:
                        LOG.info("Display acknowledged frame %s", pending_id)
                        pending_id = None
                    elif event.get("error"):
                        reason = event["error"]
                        if is_recoverable_device_error(reason):
                            LOG.warning("Recoverable device error: %s", reason)
                            continue
                        raise RuntimeError(f"Device error: {reason}")
                if transcription and transcription.done():
                    try:
                        transcript, audio = transcription.result()
                        LOG.info(
                            "Voice captured %.2fs rms=%s peak=%s; transcript=%s",
                            audio.duration, audio.rms, audio.peak, transcript,
                        )
                        generation = asyncio.create_task(api.post("/api/session/start", json={"goal": transcript}, timeout=75))
                        voice_mode = "generating"
                    except (VoiceInputError, httpx.HTTPError) as exc:
                        LOG.warning("Voice input failed: %s", exc)
                        voice_mode, voice_error = "error", str(exc)
                        voice_error_until = time.monotonic() + 5
                    transcription = None
                if generation and generation.done():
                    try:
                        response = generation.result()
                        if response.status_code >= 400:
                            raise VoiceInputError(response.json().get("detail", "任务生成失败"))
                        voice_mode = None
                    except (VoiceInputError, httpx.HTTPError) as exc:
                        LOG.warning("Task generation failed: %s", exc)
                        voice_mode, voice_error = "error", str(exc)
                        voice_error_until = time.monotonic() + 5
                    generation = None
                if voice_mode == "error" and time.monotonic() >= voice_error_until:
                    voice_mode, voice_error = None, None
                if pending_id is not None and time.monotonic() - sent_at > (30 if getattr(args, "transport", "usb") == "s3" else 10):
                    raise TimeoutError("Display acknowledgement timed out")
                response = await api.get("/api/state")
                response.raise_for_status()
                state = response.json()
                haptic = state.get("intervention", {}).get("pattern") if state.get("intervention", {}).get("channel") == "haptic" else None
                if wearable_connected and haptic_ready and haptic and haptic != last_haptic:
                    await link.send({"cmd": "haptic", "pattern": haptic})
                    last_haptic = haptic
                elif not haptic:
                    last_haptic = None
                if notice and time.monotonic() < notice_until and not voice_mode:
                    state = dict(state, state="notice", current_action=notice)
                if voice_mode:
                    state = dict(state)
                    state["state"] = f"voice_{voice_mode}"
                    if voice_error:
                        state["voice_error"] = voice_error
                if state.get("current_action") != last_action:
                    last_action = state.get("current_action")
                    page_started = time.monotonic()
                frame = render_frame(state, args.font, int((time.monotonic()-page_started)/4))
                # A 160x80 frame is a 3,200-character BLE JSON payload. Do not
                # compete with 32 kB/s PCM capture; firmware shows Listening locally.
                suppress_frame = getattr(args, "transport", "usb") == "s3" and voice_mode in {"recording", "stopping"}
                if wearable_connected and not suppress_frame and frame != last_frame and pending_id is None:
                    frame_id += 1
                    await link.send({"cmd": "frame", "id": frame_id, "hex": frame})
                    pending_id, sent_at, last_frame = frame_id, time.monotonic(), frame
                if time.monotonic() - last_hello >= 2:
                    await link.send({"cmd": "hello"})
                    last_hello = time.monotonic()
                await asyncio.sleep(0.15)
    finally:
        if generation and not generation.done():
            generation.cancel()
            await asyncio.gather(generation, return_exceptions=True)
        if transcription and not transcription.done():
            transcription.cancel()
            await asyncio.gather(transcription, return_exceptions=True)
        await link.close()


async def run_bridge(args):
    while True:
        try:
            await bridge(args)
        except (OSError, RuntimeError, TimeoutError, httpx.HTTPError) as exc:
            LOG.warning("连接中断，2 秒后重试：%s", exc)
            await asyncio.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["usb", "ble", "s3"], default="usb")
    parser.add_argument("--port")
    parser.add_argument("--address")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--font", default=os.getenv("MINDLOOP_FONT", "/System/Library/Fonts/STHeiti Medium.ttc"))
    args = parser.parse_args()
    if not Path(args.font).is_file():
        parser.error("Set --font to a Chinese-capable .ttf/.ttc file")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(run_bridge(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
