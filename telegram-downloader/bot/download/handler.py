import asyncio
import logging
import os.path
from os.path import isfile
from random import choices, randint
from string import ascii_letters, digits
from time import time

from pyrogram.enums.parse_mode import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from .. import folder, BASE_FOLDER
from .manager import downloads
from .type import Download
from ..rate_limiter import catch_rate_limit


async def addFile(_, msg: Message):
    if folder.get() in ('', '.') and not folder.allow_root_folder:
        folders = folder.get_curdir_folders()
        if len(folders) == 0:
            ok, err = folder.mkdir('downloads')
            if not ok:
                await catch_rate_limit(msg.reply,
                                       text=err,
                                       parse_mode=ParseMode.MARKDOWN,
                                       )
                return
            folder.set('downloads')
        else:
            await catch_rate_limit(msg.reply,
                                   text="Root folder selected, please select one of the subfolders.",
                                   quote=True,
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[
                                       InlineKeyboardButton(f"{f}", callback_data=f"cd {f}") for f in folders
                                   ]])
                                   )
            return

    caption = msg.caption or ""
    if folder.autofolder() and msg.forward_from_chat.id < 0 and msg.forward_from_chat.title.strip() != '':
        foldername = folder.clean_folder_name(msg.forward_from_chat.title).strip().replace('  ', ' ')
        filename =  os.path.join(folder.get(), foldername )
    else:
        filename = folder.get()

    if caption[:1] == '>':
        filename = os.path.join( filename, caption[2:])
    else:
        try:
            media = getattr(msg, msg.media.value)
            filename = os.path.join(filename, media.file_name)
        except AttributeError:
            filename = os.path.join(filename, ''.join(choices(ascii_letters + digits, k=12)))
    if isfile(os.path.join(BASE_FOLDER, filename)):
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
