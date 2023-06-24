import asyncio
import logging
import os
from os import mkdir
from textwrap import dedent

from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from . import BASE_FOLDER, DL_FOLDER, folder, sysinfo
from .rate_limiter import catch_rate_limit


async def start(_, msg: Message):
    text = dedent("""
        Hello!
        Send me a file and I will download it to my server.
        If you need help send /help
    """)
    logging.info(text)
    await catch_rate_limit(
        msg.reply,
        text=text)


async def usage(_, msg: Message):
    u = sysinfo.diskUsage(DL_FOLDER)
    text = dedent(f"""
        Disk usage: __{u.used}__ / __{u.capacity}__ (__{u.percent}__)
        Free: __{u.free}__
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply,
                           text=text,
                           parse_mode=ParseMode.MARKDOWN)


async def bot_help(_, msg: Message):
    text = dedent(f"""
        /usage | show disk usage
        /cd __foldername__ | choose the subfolder where to download the files
        /cd | go to root foolder
        /autofolder | put downloads on a subfolder named after the forwarded original group
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply, text=text)


async def use_autofolder(_, msg: Message):
    folder.set('')
    folder.autofolder(not folder.autofolder())
    text = dedent(f"""
        Use autofolder {'enabled' if folder.autofolder() else 'disabled'}
    """)
    logging.info(text)
    await  catch_rate_limit(
        msg.reply,
        text=text
    )


async def use_folder(_, msg: Message):
    newFolder = ' '.join(msg.text.split()[1:])

    if newFolder in ['..', '', '\'']:
        folder.set('')
        await catch_rate_limit(msg.reply, text="I'm in the root folder")
        return

    if '..' in newFolder:
        text = "Two dots is not allowed on the folder name!"
        logging.info(text)
        await catch_rate_limit(
            msg.reply,
            text=text,
        )
        return

    ok, err = folder.mkdir(newFolder)
    if not ok:
        logging.warning(err)
        await catch_rate_limit(msg.reply, text=err)
        return

    folder.set(os.path.join(folder.get(), newFolder))
    text = dedent(f"""
        Ok, send me files now and I will put it on this folder:
        {folder.get()}
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply, text=text)
