#!/bin/zsh
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[MindLoop] .venv not found. Running setup first..."
  ./setup_mac.command
fi

source .venv/bin/activate

echo "[MindLoop] Starting at http://127.0.0.1:8000"
uvicorn mindloop.app:app --host 127.0.0.1 --port 8000 &
server_pid=$!
bridge_pid=""

cleanup() {
  [ -z "$bridge_pid" ] || kill "$bridge_pid" 2>/dev/null || true
  kill "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in {1..30}; do
  curl --noproxy '*' -fsS http://127.0.0.1:8000/health >/dev/null && break
  sleep 0.2
done

if [ "${MINDLOOP_NO_HARDWARE:-0}" != "1" ]; then
  python -m mindloop.hardware_bridge --transport "${MINDLOOP_TRANSPORT:-usb}" &
  bridge_pid=$!
fi

open "http://127.0.0.1:8000"
wait "$server_pid"
