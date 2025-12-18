from os import getenv, mkdir

from dotenv import load_dotenv
from pyrogram import Client

load_dotenv()


def _get_env(name: str, cast=str, default=None, allow_empty: bool = False):
    """
    Fetch an env var, optionally casting it, and fail with a clear message if missing/invalid.
    """
    raw = getenv(name) if default is None else getenv(name, default)
    if not allow_empty and (raw is None or raw == ''):
        raise RuntimeError(f"Missing required environment variable: {name}. Add it to your .env or environment.")
    if raw is None:
        return None
    if cast is None:
        return raw
    try:
        return cast(raw)
    except Exception as exc:
        raise RuntimeError(f"Invalid value for {name}: {raw!r}. Expected type {cast.__name__}.") from exc


ADMINS = (_get_env('ADMINS', default='', allow_empty=True) or '').split()
BASE_FOLDER = _get_env('DOWNLOAD_FOLDER', default='/data', allow_empty=False)

try:
    mkdir(BASE_FOLDER)
except FileExistsError:
    pass

import logging

logging.basicConfig(
    level=_get_env('DEBUG_LEVEL', default='INFO', allow_empty=False),
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

app = Client(
    name=__name__,
    api_id=_get_env('TELEGRAM_API_ID', cast=int),
    api_hash=_get_env('TELEGRAM_API_HASH'),
    bot_token=_get_env('BOT_TOKEN'),
    max_concurrent_transmissions=_get_env('DOWNLOAD_WORKERS', cast=int, default='3'),
)
