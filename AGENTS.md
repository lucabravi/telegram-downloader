# AGENTS

Project: Telegram downloader bot (Pyrogram).

Quick context
- Source code lives in `telegram-downloader/`.
- Entry point: `python -m bot` from `telegram-downloader/`.
- Requirements file: `telegram-downloader/requirements.txt`.
- SQLite DB path: `/db/database_file.db`.
- Downloads root default: `/data` (env `DOWNLOAD_FOLDER`).

Docker
- Dockerfile lives in repo root; build uses context `./telegram-downloader`.
- Compose mounts `/db` for SQLite and `/data` for downloads.

Env vars
- Required: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `BOT_TOKEN`, `ADMINS`.
- Optional: `ALLOW_ROOT_FOLDER`, `DOWNLOAD_FOLDER`.

How it works
- All commands are admin-only via `ADMINS` checks.
- Virtual FS is rooted at `DOWNLOAD_FOLDER` and prevents escaping the root.
- `/mkdir` sanitizes names and returns the relative path created.
- `/ls` lists directories/files alphabetically (case-insensitive).
- Downloads are queued; the manager runs up to `max_concurrent_transmissions`.
- Each download keeps a single “origin” message for start/finish status.
- A single per-chat status message summarizes all active downloads.

Rate limiting
- `catch_rate_limit` applies a local 3 msgs/second throttle and handles FloodWait.
- A message queue guarantees delivery of “must-send” messages without blocking downloads.
- Status message is edited when still last; otherwise it is deleted and re-sent.

Logging
- Pyrogram INFO logs are suppressed; warnings/errors still show.
- Download status is logged to console on each status update.
- The “Max downloads running” log is throttled.

Notes
- Python target is 3.14 in Docker.
- Pyrogram import requires an event loop setup in `telegram-downloader/bot/__init__.py`.
- Avoid committing secrets from `.env` or `docker-compose.yml`.
