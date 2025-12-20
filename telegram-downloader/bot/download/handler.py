import re
import logging
import os.path
from os.path import isfile
from random import choices, randint
from string import ascii_letters, digits
from typing import Tuple

from ..util import dedent
from time import time

from pyrogram.enums.parse_mode import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from ..db import Chat
from .manager import enqueue_download
from .type import Download
from ..rate_limiter import catch_rate_limit, enqueue_message
from ..manage_path import VirtualFileSystem


async def add_file(_, msg: Message, chat: Chat):
    vfs = VirtualFileSystem()
    ok, new_path = vfs.abs_cd(chat.current_dir)
    if not ok:
        text = ("There's a problem with saved current folder, change folder with /cd __foldername__ or create"
                " a new folder with /mkdir __foldername__.")
        await enqueue_message(msg.reply, text=text)
        return

    if chat.current_dir in ('/', '.', '') and not vfs.allow_root_folder and not chat.autofolder:
        folders, files = vfs.ls()
        if len(folders) == 0:
            text = "You can't download in this folder, create a subfolder."
            await enqueue_message(msg.reply,
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
            await enqueue_message(msg.reply,
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
            await enqueue_message(msg.reply, text=text)
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
        logging.error(f'Error getting filename: {e}')
        filename = ''.join(choices(ascii_letters + digits, k=12))

    filepath = os.path.join(path, filename)

    if isfile(vfs.relative_to_absolute_path(filepath)):
        text = f"File with the same name ({filename}) already exists!"
        logging.info(text)
        await enqueue_message(msg.reply, text=text, quote=True)
        return
    text = f"File __{filepath}__ added to list."
    logging.info(text)
    waiting = await enqueue_message(msg.reply, text=text,
                                    quote=True,
                                    parse_mode=ParseMode.MARKDOWN)
    await enqueue_download(Download(
        id=randint(1_000_000_000, 9_999_999_999),
        filename=filename,
        filepath=filepath,
        from_message=msg,
        added=time(),
        progress_message_future=waiting
    ))


def find_correct_filename(original_filename: str, caption: str, chat_title: str) -> str:
    file_extension = original_filename.split('.')[-1] if original_filename is not None else 'mp4'
    season_capt, ep_capt, is_ova_capt = extract_numbers_from_title(caption)
    if ep_capt is not None and season_capt is not None:
        return format_filename(season_capt, ep_capt, is_ova_capt, file_extension)

    season_ofi, ep_ofi, is_ova_ofi = extract_numbers_from_title(original_filename)
    if ep_ofi is not None and season_ofi is not None:
        return format_filename(season_ofi, ep_ofi, is_ova_ofi, file_extension)

    if ep_capt is not None:
        return format_filename('1', ep_capt, is_ova_capt, file_extension)
    
    return original_filename


def format_filename(season: int, episode: int, is_ova: bool, file_extension: str) -> str:
    season = str(season).rjust(2, '0')
    episode = str(episode).rjust(3, '0')
    if is_ova:
        return f'S{season}OVA{episode}.{file_extension}'
    else:
        return f'S{season}E{episode}.{file_extension}'


ep_regex = re.compile(r"Ep?(\d{1,4})\b")
ova_regex = re.compile(r"OVA?(\d{1,4})\b")
s_regex = re.compile(r"S(\d{1,2})\b")


def extract_numbers_from_title(title) -> Tuple[int | None, int | None, bool]:
    try:
        s_match = s_regex.search(title)
        ep_match = ep_regex.search(title)
        ova_match = ova_regex.search(title)

        # Check if none of the three matches are found
        if not s_match and not ep_match and not ova_match:
            logging.info(f'{s_match} - {ep_match} - {ova_match}')
            raise Exception("No information about season, episode, or OVA found in the title")

        # Check if at least one of episode number or OVA number is present
        if not (ep_match or ova_match):
            raise Exception("You must provide at least the episode number or the OVA number")

        s_number = int(s_match.group(1)) if s_match else None
        ep_number = int(ep_match.group(1)) if ep_match else None
        ova_number = int(ova_match.group(1)) if ova_match else None

        logging.info(
            f'extract_numbers_from_title | s_number: {s_number} - ep_number: {ep_number} - ova_number: {ova_number}')
        return s_number, ep_number or ova_number, ova_number is not None
    except Exception as e:
        logging.warn(f'extract_numbers_from_title | {e}')
    return None, None, False
