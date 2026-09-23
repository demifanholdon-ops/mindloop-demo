"""Local CPU Whisper; no silent switch to a remote speech service."""
import asyncio
import io
import os
import time
from pathlib import Path


class LocalASR:
    def __init__(self):
        self.model = None
        self.lock = asyncio.Lock()
        self.path = os.getenv("LOCAL_ASR_MODEL", str(Path(__file__).resolve().parents[1] / "models/whisper-base"))

    def _load(self):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(self.path, device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)

    async def warmup(self):
        async with self.lock:
            if not self.model: await asyncio.to_thread(self._load)

    def _transcribe(self, wav):
        segments, _ = self.model.transcribe(io.BytesIO(wav), language="zh", beam_size=1,
                                            condition_on_previous_text=False, vad_filter=False,
                                            initial_prompt="以下是中文任务、提醒和完成情况。")
        return ''.join(s.text for s in segments).strip()

    async def transcribe(self, wav):
        start = time.perf_counter()
        await self.warmup()
        async with self.lock: text = await asyncio.to_thread(self._transcribe, wav)
        if not text: raise RuntimeError("没有识别到文字，请靠近麦克风再说一次")
        return text, round((time.perf_counter()-start)*1000)
