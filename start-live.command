#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo '请先执行 README-LIVE.md 中的安装命令。'
  exit 1
fi
export PYTHON_DOTENV_DISABLED=1
export MINDLOOP_DB_PATH="$PWD/data/legacy.sqlite3"
mkdir -p data
echo 'MindLoop 实时 Demo：http://127.0.0.1:4173/app/index.html?live=1'
exec .venv/bin/python -m uvicorn live_app:app --app-dir backend --host 127.0.0.1 --port 4173 --no-access-log
