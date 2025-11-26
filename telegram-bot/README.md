# Telegram Bot and API

This project provides a simple task-tracking API built with FastAPI and a Telegram bot built on aiogram. The API stores data in a local SQLite database (`tasks.db`), and the bot communicates with the API over HTTP.

## Requirements
- Python 3.10 or newer
- Ability to create and activate a virtual environment (`python -m venv`)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## Quick start on a VPS
Use separate commands (each on its own line) to avoid shell syntax errors:

```bash
git clone https://github.com/Madevilmax/madevilmax.git
cd madevilmax/telegram-bot
python -m venv .venv
source .venv/bin/activate
pip install aiogram httpx fastapi uvicorn pydantic
```

## Running the API
Start the FastAPI app with uvicorn so the bot can reach it:

```bash
uvicorn api.web_api:app --host 0.0.0.0 --port 8000
```

The server initializes `tasks.db` automatically in the project directory.

## Running the Telegram bot
Set your bot token and run the bot:

```bash
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"  # без угловых скобок
python bot/bot.py
```

### Optional configuration
- `BASE_API_URL` in `bot/bot.py` defaults to `http://localhost:8000`. Change it if the API runs on a different host or port.
- `ADMIN_USERNAMES` and `EMPLOYEE_USERNAMES` can be provided as comma-separated environment variables before launching the bot.

### Adding an admin
- **Through the bot UI**: open the admin panel, choose **«Управление администраторами» → «Добавить администратора»**, и введите `@username`. Бот запишет его в `config.json`.
- **Через переменную окружения**: до запуска бота установите `ADMIN_USERNAMES="@admin1,@admin2"`. При первом старте значения запишутся в `config.json` и будут использованы далее.
- Список текущих администраторов хранится в `config.json` (создаётся автоматически рядом с ботом) и обновляется при добавлении/удалении через бот.
- В репозитории уже лежит базовый `config.json` с админом `@poznarev`, чтобы бот сразу стартовал с нужными правами.

### Запуск API и бота одной командой
- В корне проекта есть `.env` с готовыми переменными (включая `TELEGRAM_BOT_TOKEN="8366638655:AAH19tYpe_6Wjbe1S9VbFmScU02VftgXSdU"` и `ADMIN_USERNAMES="@poznarev"`). При необходимости отредактируйте токен и список админов.
- Скрипт `run_all.sh` поднимет и API, и бота. Пример:
  ```bash
  cd madevilmax/telegram-bot
  chmod +x run_all.sh  # один раз
  ./run_all.sh
  ```
  Скрипт читает `.env` (если нужно, отредактируйте его перед запуском) и запускает uvicorn на `0.0.0.0:8000`, а бот стартует следом.

## Process management
For production, run the API and bot under a process manager (`systemd`, `supervisor`, `tmux`, or `screen`) and ensure inbound traffic to the API port is allowed in your firewall or cloud security group.
