import logging
import os
from textwrap import dedent

from pyrogram.enums import ParseMode
from pyrogram.types import Message

from . import sysinfo
from .rate_limiter import catch_rate_limit
from .manage_path import vfs


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


async def bot_help(_, msg: Message):
    text = dedent(f"""
        /usage | show disk usage
        /cd __foldername__ | choose the subfolder where to download the files
        /cd | go to root foolder
        /autofolder | put downloads on a subfolder named after the forwarded original group
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply, text=text)


async def usage(_, msg: Message):
    u = sysinfo.disk_usage(vfs.__root)
    text = dedent(f"""
        Disk usage: __{u.used}__ / __{u.capacity}__ (__{u.percent}__)
        Free: __{u.free}__
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply,
                           text=text,
                           parse_mode=ParseMode.MARKDOWN)


async def change_folder(_, msg: Message):
    new_folder = ' '.join(msg.text.split()[1:])

    ok, err = vfs.cd(new_folder)
    if not ok:
        text = dedent(f"""
        {err}
        {vfs.get_current_dir_info()}""")
        await catch_rate_limit(msg.reply, text=text)
        return

    text = dedent(f"""
        Ok, send me files now and I will put it on this folder:
        {vfs.current_rel_path}
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply, text=text)


async def use_autofolder(_, msg: Message):
    vfs.autofolder = not vfs.autofolder
    text = dedent(f"""
        Use autofolder {'enabled' if vfs.autofolder else 'disabled'}
    """)
    logging.info(text)
    await catch_rate_limit(
        msg.reply,
        text=text
    )


async def create_folder(_, msg: Message):
    new_folder = ' '.join(msg.text.split()[1:])

    ok, err = vfs.mkdir(new_folder)

    if not ok:
        text = dedent(f"""
        {err}
        {vfs.get_current_dir_info()}""")
        await catch_rate_limit(msg.reply, text=text)
        return

    text = dedent(f"""
        Folder {new_folder} created:
        {vfs.get_current_dir_info()}
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply, text=text)
