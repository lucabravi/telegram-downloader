# AGENTS

Project: Telegram downloader bot (Pyrogram).

Quick context
- Source code lives in `telegram-downloader/`.
- Entry point: `python -m bot` from `telegram-downloader/`.
- Requirements file: `telegram-downloader/requirements.txt`.
- SQLite DB path in code: `/db/database_file.db`.
- Downloads path default: `/data` (env `DOWNLOAD_FOLDER`).

Docker
- Build from repo root with context `./telegram-downloader` and Dockerfile in root.
- Compose mounts `/db` for SQLite and `/data` for downloads.

Env vars
- Required: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `BOT_TOKEN`, `ADMINS`.
- Optional: `ALLOW_ROOT_FOLDER`, `DOWNLOAD_FOLDER`.

Notes
- Python target is 3.14 in Docker.
- Pyrogram import requires an event loop setup in `telegram-downloader/bot/__init__.py`.
- Avoid committing secrets from `.env` or `docker-compose.yml`.
