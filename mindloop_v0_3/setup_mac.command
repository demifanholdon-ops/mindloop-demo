#!/bin/zsh
set -e
cd "$(dirname "$0")"
echo "[MindLoop] Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo
echo "[MindLoop] Setup complete."
echo "Run ./run_demo.command"
