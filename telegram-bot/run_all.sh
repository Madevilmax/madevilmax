#!/usr/bin/env bash
set -euo pipefail

# Load environment variables if .env exists
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/.env"
fi

# Activate local virtual environment when available so uvicorn/bot imports work
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/.venv/bin/activate"
fi

# Fallback defaults to guarantee startup
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-8366638655:AAH19tYpe_6Wjbe1S9VbFmScU02VftgXSdU}"
export ADMIN_USERNAMES="${ADMIN_USERNAMES:-@poznarev}"
export BASE_API_URL="${BASE_API_URL:-http://localhost:8000}"

cd "$SCRIPT_DIR"

# Pick python interpreter (prefer venv)
if [ -z "${PYTHON_BIN:-}" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "Python interpreter not found" >&2
    exit 1
  fi
fi

# Start API in the background
"$PYTHON_BIN" -m uvicorn api.web_api:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

echo "API started (pid=$API_PID) on http://0.0.0.0:8000"

trap 'echo "Stopping services..."; kill "$API_PID" "$BOT_PID" 2>/dev/null' INT TERM

# Start Telegram bot in the foreground so logs stay attached
"$PYTHON_BIN" bot/bot.py &
BOT_PID=$!

echo "Bot started (pid=$BOT_PID)"

wait "$API_PID" "$BOT_PID"
