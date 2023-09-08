import re
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
from ..db import Chat
from .manager import enqueue_download
from .type import Download
from ..rate_limiter import catch_rate_limit
from ..manage_path import VirtualFileSystem


async def add_file(_, msg: Message, chat: Chat):
    vfs = VirtualFileSystem()
    ok, new_path = vfs.abs_cd(chat.current_dir)
    if not ok:
        text = ("There's a problem with saved current folder, change folder with /cd __foldername__ or create"
                " a new folder with /mkdir __foldername__.")
        await catch_rate_limit(msg.reply, text=text)
        return

    if chat.current_dir in ('/', '.', '') and not vfs.allow_root_folder and not chat.autofolder:
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

    if chat.autofolder and msg.forward_from_chat and msg.forward_from_chat.id < 0 and msg.forward_from_chat.title.strip() != '':
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

    try:
        media = getattr(msg, msg.media.value)
        caption = str(msg.caption) or ""
        if chat.autoname:
            filename = find_correct_filename(media.file_name, caption, msg.chat.title)
        else:
            if media.file_name is None:
                raise Exception('media.file_name is None, generating random filename')
            filename = vfs.cleanup_path_name(media.file_name)
    except Exception as e:
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
    await enqueue_download(Download(
        id=randint(1e9, 1e10 - 1),
        filename=filename,
        filepath=filepath,
        from_message=msg,
        added=time(),
        progress_message=waiting
    ))


def find_correct_filename(original_filename: str, caption: str, chat_title: str) -> str:
    file_extension = original_filename.split('.')[-1]
    ep, season = extract_numbers_from_title(caption)
    if ep is not None and season is not None:
        return format_filename(season, ep, file_extension)

    ep, season = extract_numbers_from_title(original_filename)
    if ep is not None and season is not None:
        return format_filename(season, ep, file_extension)

    return original_filename


def format_filename(season, episode, file_extension):
    season = str(season).rjust(2, '0')
    episode = str(episode).rjust(3, '0')
    return f'S{season}E{episode}.{file_extension}'


ep_regex = re.compile(r"Ep?(\d{1,4})\b")
s_regex = re.compile(r"S(\d{1,2})\b")


def extract_numbers_from_title(title):
    try:
        ep_match = ep_regex.search(title)
        s_match = s_regex.search(title)
        ep_number = int(ep_match.group(1))
        s_number = int(s_match.group(1))
        logging.debug(f'extract_numbers_from_title | s_number: {s_number} - ep_number: {ep_number}')
        return ep_number, s_number
    except:
        pass
    return None, None
