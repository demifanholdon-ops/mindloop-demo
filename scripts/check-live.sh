#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=backend PYTHON_DOTENV_DISABLED=1 MINDLOOP_LLM_PROVIDER=mock .venv/bin/python -m pytest backend -q -o asyncio_mode=auto
npm --prefix frontend-pink run check
npm --prefix frontend-pink test
