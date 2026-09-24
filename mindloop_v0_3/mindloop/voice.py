"""On-device PCM capture and local speech-to-text boundary."""

from array import array
import base64
from dataclasses import dataclass
import math
import os
from pathlib import Path
import sys
import wave


class VoiceInputError(RuntimeError):
    pass


@dataclass(frozen=True)
class CaptureResult:
    path: Path
    samples: int
    duration: float
    peak: int
    rms: int


class AudioCapture:
    """Reassembles ordered PCM events and writes a standard WAV file."""

    def __init__(self, min_duration=0.35, max_duration=15.5, min_rms=120):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.min_rms = min_rms
        self.active = False

    def start(self, event):
        sample_rate = int(event.get("sample_rate", 0))
        channels = int(event.get("channels", 0))
        sample_width = int(event.get("sample_width", 0))
        if (sample_rate, channels, sample_width) != (16000, 1, 2):
            raise VoiceInputError("不支持的音频格式")
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.data = bytearray()
        self.next_seq = 0
        self.active = True

    def add_chunk(self, event):
        if not self.active:
            raise VoiceInputError("未开始录音")
        seq = int(event.get("seq", -1))
        if seq != self.next_seq:
            self.active = False
            raise VoiceInputError(f"音频分块丢失：期望 {self.next_seq}，收到 {seq}")
        try:
            if "audio" in event:
                chunk = base64.b64decode(event["audio"], validate=True)
            else:
                chunk = bytes.fromhex(event.get("pcm", ""))
        except (TypeError, ValueError) as exc:
            self.active = False
            raise VoiceInputError("音频分块格式错误") from exc
        if not chunk or len(chunk) % self.sample_width:
            self.active = False
            raise VoiceInputError("音频分块长度错误")
        self.data.extend(chunk)
        self.next_seq += 1
        if len(self.data) / (self.sample_rate * self.sample_width) > self.max_duration:
            self.active = False
            raise VoiceInputError("录音超过最长时间")

    def finish(self, path):
        if not self.active:
            raise VoiceInputError("未开始录音")
        self.active = False
        samples = len(self.data) // self.sample_width
        duration = samples / self.sample_rate
        if duration < self.min_duration:
            raise VoiceInputError("录音太短，请至少说半秒")

        values = array("h")
        values.frombytes(self.data)
        if sys.byteorder != "little":
            values.byteswap()
        peak = max((abs(value) for value in values), default=0)
        rms = int(math.sqrt(sum(value * value for value in values) / samples)) if samples else 0
        if rms < self.min_rms:
            raise VoiceInputError("声音太小，请靠近设备再说一次")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(self.channels)
            output.setsampwidth(self.sample_width)
            output.setframerate(self.sample_rate)
            output.writeframes(self.data)
        return CaptureResult(path, samples, duration, peak, rms)


class MLXWhisperTranscriber:
    """Lazy local Whisper adapter; model downloads once and is then cached."""

    def __init__(self, model=None):
        self.model = model or os.getenv("MINDLOOP_WHISPER_MODEL", "mlx-community/whisper-base-mlx")

    def transcribe(self, audio_path):
        try:
            import mlx_whisper
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise VoiceInputError(f"本地语音识别不可用：{exc}") from exc
        try:
            # The model is installed during setup. Resolve it from the cache so
            # malformed or unavailable desktop proxy settings cannot break STT.
            model_path = snapshot_download(repo_id=self.model, local_files_only=True)
            result = mlx_whisper.transcribe(
                str(audio_path),
                path_or_hf_repo=model_path,
                language="zh",
                task="transcribe",
                initial_prompt="以下内容使用简体中文。",
                verbose=False,
            )
        except Exception as exc:
            raise VoiceInputError(f"本地语音识别失败：{exc}") from exc
        text = result.get("text", "").strip()
        if not text:
            raise VoiceInputError("没有识别到语音")
        return text
