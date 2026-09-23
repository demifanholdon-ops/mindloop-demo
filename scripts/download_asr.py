"""Fetch a public local ASR model; no audio or credentials are uploaded."""
import os
from pathlib import Path
from huggingface_hub import snapshot_download

root = Path(__file__).resolve().parents[1]
snapshot_download("Systran/faster-whisper-base", local_dir=root / "models/whisper-base",
                  allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
print("Local Whisper base is available.")
