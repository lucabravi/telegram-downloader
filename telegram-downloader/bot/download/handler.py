import asyncio
import logging
import os.path
from os.path import isfile
from random import choices, randint
from string import ascii_letters, digits
from ..util import dedent
from time import time

from pyrogram.enums.parse_mode import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from .. import BASE_FOLDER
from .manager import downloads
from .type import Download
from ..rate_limiter import catch_rate_limit
from ..manage_path import vfs


async def addFile(_, msg: Message):
    if vfs.current_rel_path == '.' and not vfs.allow_root_folder and not vfs.autofolder:
        folders, files = vfs.ls()
        if len(folders) == 0:
            text = "You can't download in this folder, create a subfolder."
            await catch_rate_limit(msg.reply,
                                   text=text)
            return
        # else:
        #     text = dedent(f"""
        #     Root folder selected, please:
        #     - go to a subfolder ( /cd __folder__ )
        #     available folders: ["{'",'.join(folders)}"]
        #     - enable autofolder ( /autofolder )
        #     - create a new folder ( /mkdir __folder__)
        #     """)
        #     await catch_rate_limit(msg.reply,
        #                            text=text)
        #     return
        else:
            await catch_rate_limit(msg.reply,
                                   text="Root folder selected, please select one of the subfolders or create a new one with /mkdir __folder__.",
                                   quote=True,
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[
                                       InlineKeyboardButton(f"{f}", callback_data=f"cd {f}") for f in folders
                                   ]])
                                   )
            return

    caption = str(msg.caption) or ""
    if vfs.autofolder and msg.forward_from_chat and  msg.forward_from_chat.id < 0 and msg.forward_from_chat.title.strip() != '':
        ok, info = vfs.mkdir(msg.forward_from_chat.title)
        if not ok:
            text = dedent(f"""
                {info}
                {vfs.get_current_dir_info()}
            """)
            await catch_rate_limit(msg.reply, text=text)
            return
        path = os.path.join(vfs.current_rel_path, info)
    else:
        path = vfs.current_rel_path

    if caption[:1] == '>':
        filename = vfs.cleanup_path_name(caption[2:])
        filepath = os.path.join(path, filename)
    else:
        try:
            media = getattr(msg, msg.media.value)
            filename = vfs.cleanup_path_name(media.file_name)
            filepath = os.path.join(path, filename)
        except AttributeError:
            filename = ''.join(choices(ascii_letters + digits, k=12))
            filepath = os.path.join(path, filename)

    if isfile(vfs.relative_to_absolute_path(filepath)):
        text = f"File with the same name ({filename}) already exists!"
        logging.info(text)
        await catch_rate_limit(msg.reply, text=text, quote=True)
        return
    text = f"File __{filepath}__ added to list."
    logging.info(text)
    waiting = await catch_rate_limit(msg.reply, text=text,
                                     quote=True,
                                     parse_mode=ParseMode.MARKDOWN)
    downloads.append(Download(
        id=randint(1e9, 1e10 - 1),
        filename=filename,
        filepath=filepath,
        from_message=msg,
        added=time(),
        progress_message=waiting
    ))
