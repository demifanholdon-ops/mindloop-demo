import tempfile
import unittest
from unittest.mock import patch
import wave
from pathlib import Path

from mindloop.voice import AudioCapture, MLXWhisperTranscriber, VoiceInputError


class AudioCaptureTests(unittest.TestCase):
    def test_pcm_chunks_become_a_valid_mono_16khz_wav(self):
        capture = AudioCapture(min_duration=0)
        capture.start({"sample_rate": 16000, "channels": 1, "sample_width": 2})
        capture.add_chunk({"seq": 0, "audio": "AQACAP9/AIA="})

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "speech.wav"
            result = capture.finish(path)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.readframes(4), bytes.fromhex("01000200ff7f0080"))
        self.assertEqual(result.samples, 4)
        self.assertGreater(result.peak, 32000)

    def test_missing_chunk_is_rejected_instead_of_transcribing_corrupt_audio(self):
        capture = AudioCapture(min_duration=0)
        capture.start({"sample_rate": 16000, "channels": 1, "sample_width": 2})
        with self.assertRaisesRegex(VoiceInputError, "音频分块丢失"):
            capture.add_chunk({"seq": 2, "pcm": "0000"})

    def test_too_short_recording_is_rejected(self):
        capture = AudioCapture(min_duration=0.5)
        capture.start({"sample_rate": 16000, "channels": 1, "sample_width": 2})
        capture.add_chunk({"seq": 0, "pcm": "0100" * 100})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(VoiceInputError, "录音太短"):
                capture.finish(Path(directory) / "short.wav")

    def test_silence_is_rejected_before_whisper_can_hallucinate(self):
        capture = AudioCapture(min_duration=0)
        capture.start({"sample_rate": 16000, "channels": 1, "sample_width": 2})
        capture.add_chunk({"seq": 0, "pcm": "0000" * 16000})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(VoiceInputError, "声音太小"):
                capture.finish(Path(directory) / "silence.wav")


class TranscriberTests(unittest.TestCase):
    def test_model_loading_failure_is_recoverable(self):
        transcriber = MLXWhisperTranscriber("missing/model")
        with patch("huggingface_hub.snapshot_download", side_effect=ValueError("bad proxy")):
            with self.assertRaisesRegex(VoiceInputError, "本地语音识别"):
                transcriber.transcribe("missing.wav")


if __name__ == "__main__":
    unittest.main()
