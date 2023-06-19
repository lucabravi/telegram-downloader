import asyncio
import logging
import time

from pyrogram.errors import FloodWait


async def catch_rate_limit(function, wait=True, *args, **kwargs):
    while True:
        try:
            av = await function(*args, **kwargs)
            return av
        except FloodWait as e:
            logging.error(f'catch_rate_limit - {e}')
            if not wait:
                break
            await asyncio.sleep(e.value)


def sync_catch_rate_limit(function, wait=True, *args, **kwargs):
    while True:
        try:
            av = function(*args, **kwargs)
            return av
        except FloodWait as e:
            logging.error(f'catch_rate_limit - {e}')
            if not wait:
                break
            time.sleep(e.value)

