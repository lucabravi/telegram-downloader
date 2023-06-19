import asyncio
import logging
from os.path import isfile
from random import choices, randint
from string import ascii_letters, digits
from time import time

from pyrogram.enums.parse_mode import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from .. import folder
from .manager import downloads
from .type import Download
from ..rate_limiter import catch_rate_limit


async def addFile(_, msg: Message):
    caption = msg.caption or ""

    if folder.autofolder() and msg.forward_from_chat.id < 0 and msg.forward_from_chat.title.strip() != '':
        foldername = "".join(
            c for c in msg.forward_from_chat.title if c.isalnum() or c in folder.keepcharacters).strip()
        filename = foldername + '/'
    else:
        filename = folder.get() + '/'

    if caption[:1] == '>':
        filename += caption[2:]
    else:
        try:
            media = getattr(msg, msg.media.value)
            filename += media.file_name
        except AttributeError:
            filename += ''.join(choices(ascii_letters + digits, k=12))
    if isfile(filename):
        text = "File already exists!"
        logging.info(text)
        await catch_rate_limit(msg.reply, text=text, quote=True)
        return
    text = f"File __{filename}__ added to list."
    logging.info(text)
    waiting = await catch_rate_limit(msg.reply, text=text,
                                     quote=True,
                                     parse_mode=ParseMode.MARKDOWN)
    downloads.append(Download(
        id=randint(1e9, 1e10 - 1),
        filename=filename,
        from_message=msg,
        added=time(),
        progress_message=waiting
    ))
