import asyncio
import logging
import time
from datetime import datetime

from pyrogram.errors import FloodWait

last_messages = []
last_block = datetime.now()
last_block_seconds = 0


async def catch_rate_limit(function, wait=True, *args, **kwargs):
    global last_block, last_block_seconds

    while True:
        if not wait and (datetime.now() - last_block).total_seconds() <= last_block_seconds + 2:
            return None
        if wait and len(last_messages) >= 3 and (datetime.now() - last_messages[-3]).total_seconds() <= 1:
            await asyncio.sleep(2)
            continue
        elif not wait and (datetime.now() - last_messages[-3]).total_seconds() <= 1:
            return None

        last_messages.append(datetime.now())
        if len(last_messages) > 3:
            last_messages.pop(0)

        try:
            av = await function(*args, **kwargs)
            return av
        except FloodWait as e:
            logging.warning(f'async catch_rate_limit - {e}')
            last_block = datetime.now()
            last_block_seconds = e.value
            if not wait:
                await asyncio.sleep(2)
                break
            await asyncio.sleep(e.value)


def sync_catch_rate_limit(function, wait=True, *args, **kwargs):
    global last_block, last_block_seconds
    while True:
        if not wait and (datetime.now() - last_block).total_seconds() <= last_block_seconds + 2:
            return None
        if wait and len(last_messages) >= 3 and (datetime.now() - last_messages[-3]).total_seconds() <= 1:
            time.sleep(2)
            continue
        elif not wait and (datetime.now() - last_messages[-3]).total_seconds() <= 1:
            return None

        last_messages.append(datetime.now())
        if len(last_messages) > 3:
            last_messages.pop(0)

        try:
            av = function(*args, **kwargs)
            return av
        except FloodWait as e:
            logging.warning(f'sync catch_rate_limit - {e}')
            last_block = datetime.now()
            last_block_seconds = e.value
            if not wait:
                break
            time.sleep(e.value)
