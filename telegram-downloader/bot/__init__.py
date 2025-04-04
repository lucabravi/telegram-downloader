from os import getenv, mkdir

from dotenv import load_dotenv
from pyrogram import Client

load_dotenv()

ADMINS = getenv('ADMINS').split()
BASE_FOLDER = getenv('DOWNLOAD_FOLDER', '/data')

try:
    mkdir(BASE_FOLDER)
except FileExistsError:
    pass

import logging

logging.basicConfig(
    level=getenv('DEBUG_LEVEL', 'INFO'),
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

app = Client(
    name=__name__,
    api_id=int(getenv('TELEGRAM_API_ID')),
    api_hash=getenv('TELEGRAM_API_HASH'),
    bot_token=getenv('BOT_TOKEN'),
    max_concurrent_transmissions=int(getenv('DOWNLOAD_WORKERS', '3'))
)
