import asyncio
from os import mkdir
from textwrap import dedent

from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from . import BASE_FOLDER, DL_FOLDER, folder, sysinfo
from .rate_limiter import catch_rate_limit


async def start(_, msg: Message):
    await catch_rate_limit(
        msg.reply,
        text=dedent("""
                Hello!
                Send me a file and I will download it to my server.
                If you need help send /help
            """))


async def usage(_, msg: Message):
    u = sysinfo.diskUsage(DL_FOLDER)
    await catch_rate_limit(msg.reply,
                           text=dedent(f"""
                           Disk usage: __{u.used}__ / __{u.capacity}__ (__{u.percent}__)
                           Free: __{u.free}__"""),
                           parse_mode=ParseMode.MARKDOWN)


async def botHelp(_, msg: Message):
    await catch_rate_limit(msg.reply, text=dedent(f"""
    /usage | show disk usage
    /cd __foldername__ | choose the subfolder where to download the files
    /cd .. | go to root foolder
    """))


async def use_folder(_, msg: Message):
    newFolder = ' '.join(msg.text.split()[1:])
    print(newFolder)

    if newFolder == '..' or '':
        folder.set('.')
        await catch_rate_limit(msg.reply, text="I'm in the root folder")
        return

    if '..' in newFolder:
        await catch_rate_limit(
            msg.reply,
            text="Two dots is not allowed on the folder name!",
        )
        return
    try:
        mkdir(BASE_FOLDER + '/' + newFolder)
    except FileExistsError:
        pass
    except Exception as err:
        await catch_rate_limit(msg.reply, text=f"Failed to create folder: {err}")
        return
    folder.set(newFolder)
    await catch_rate_limit(msg.reply, text="Ok, send me files now and I will put it on this folder.")


