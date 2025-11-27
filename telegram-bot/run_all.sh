#!/usr/bin/env bash
set -euo pipefail

# Load environment variables if .env exists
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/.env"
fi

# Fallback defaults to guarantee startup
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-8366638655:AAH19tYpe_6Wjbe1S9VbFmScU02VftgXSdU}"
export ADMIN_USERNAMES="${ADMIN_USERNAMES:-@poznarev}"
export BASE_API_URL="${BASE_API_URL:-http://localhost:8000}"

cd "$SCRIPT_DIR"

# Start API in the background
uvicorn api.web_api:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

echo "API started (pid=$API_PID) on http://0.0.0.0:8000"

trap 'echo "Stopping services..."; kill "$API_PID" "$BOT_PID" 2>/dev/null' INT TERM

# Start Telegram bot in the foreground so logs stay attached
python bot/bot.py &
BOT_PID=$!

echo "Bot started (pid=$BOT_PID)"

wait "$API_PID" "$BOT_PID"
