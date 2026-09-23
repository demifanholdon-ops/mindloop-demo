"""Continuous PCM segmentation: sentence-end silence / 30 s cap, never stops capture."""
import io
import math
import struct
import wave
from collections import deque


def wav_bytes(pcm):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    return out.getvalue()


class Segmenter:
    """20 ms frames; 600 ms endpoint. WebRTC VAD when available, energy guard always."""
    def __init__(self, silence_ms=600, max_ms=30000):
        self.tail = bytearray()
        self.pre = deque(maxlen=10)
        self.current = bytearray()
        self.speech_frames = self.silence_frames = 0
        self.silence_limit = silence_ms // 20
        self.max_bytes = max_ms * 32
        try:
            import webrtcvad
            self.vad = webrtcvad.Vad(2)
        except ImportError:
            self.vad = None

    def voiced(self, frame):
        samples = struct.unpack('<320h', frame)
        rms = math.sqrt(sum(x*x for x in samples) / 320)
        return rms >= 180 and (self.vad is None or self.vad.is_speech(frame, 16000))

    def feed(self, pcm):
        self.tail.extend(pcm)
        output = []
        while len(self.tail) >= 640:
            frame = bytes(self.tail[:640]); del self.tail[:640]
            speech = self.voiced(frame)
            if not self.current:
                if not speech:
                    self.pre.append(frame); continue
                self.current.extend(b''.join(self.pre)); self.pre.clear()
            self.current.extend(frame)
            if speech:
                self.speech_frames += 1; self.silence_frames = 0
            else:
                self.silence_frames += 1
            if self.silence_frames >= self.silence_limit or len(self.current) >= self.max_bytes:
                item = self.finish("silence" if self.silence_frames >= self.silence_limit else "max_window")
                if item: output.append(item)
        return output

    def finish(self, reason="stop"):
        if reason == "stop" and self.current:
            self.current.extend(self.tail)
        data = bytes(self.current)
        valid = self.speech_frames >= 10
        self.current.clear(); self.speech_frames = self.silence_frames = 0
        if reason == "stop": self.tail.clear()
        return {"wav": wav_bytes(data), "duration_ms": len(data) // 32,
                "endpoint_ms": 600 if reason == "silence" else 0, "reason": reason} if valid else None
