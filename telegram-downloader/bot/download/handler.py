import asyncio
import re
import logging
import os
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
from ..rate_limiter import enqueue_message
from ..manage_path import VirtualFileSystem
from .animeunity import (
    ANIMEUNITY_URL_PATTERN,
    AnimeUnityError,
    extract_animeunity_url,
    resolve_animeunity_downloads,
    split_series_and_trailing_season,
)


ANIMEUNITY_URL_FILTER = ANIMEUNITY_URL_PATTERN


async def _resolve_base_path(
    vfs: VirtualFileSystem,
    msg: Message,
    chat: Chat,
    enforce_root_restriction: bool = True,
) -> str | None:
    ok, _ = vfs.abs_cd(chat.current_dir)
    if not ok:
        text = ("There's a problem with saved current folder, change folder with /cd __foldername__ or create"
                " a new folder with /mkdir __foldername__.")
        await enqueue_message(msg.reply, text=text)
        return None

    if enforce_root_restriction and chat.current_dir in ('/', '.', '') and not vfs.allow_root_folder and not chat.autofolder:
        folders, _ = vfs.ls()
        if len(folders) == 0:
            text = "You can't download in this folder, create a subfolder."
            await enqueue_message(msg.reply, text=text)
            return None
        await enqueue_message(
            msg.reply,
            text="Root folder selected, please select one of the subfolders or create a new one with /mkdir __folder__.",
            quote=True,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"{f}", callback_data=f"cd {f}") for f in folders
            ]])
        )
        return None

    if chat.autofolder and msg.forward_from_chat and msg.forward_from_chat.id < 0 and msg.forward_from_chat.title.strip() != '':
        ok, info = vfs.mkdir(msg.forward_from_chat.title)
        if not ok:
            text = dedent(f"""
                {info}
                {vfs.get_current_dir_info()}
            """)
            await enqueue_message(msg.reply, text=text)
            return None
        return os.path.normpath(os.path.join(vfs.current_rel_path, info))
    return os.path.normpath(vfs.current_rel_path)


def _build_unique_filename(filename: str, seen: set[str]) -> str:
    base, ext = os.path.splitext(filename)
    candidate = filename
    idx = 2
    while candidate.casefold() in seen:
        candidate = f"{base}_{idx}{ext}"
        idx += 1
    seen.add(candidate.casefold())
    return candidate


def _season_folder_name(season_number: int | None) -> str:
    if season_number is None or season_number <= 0:
        return "Season 01"
    return f"Season {season_number:02d}"


async def _enqueue_direct_url_download(
    msg: Message,
    filepath: str,
    filename: str,
    url: str,
    multipart_enabled: bool,
):
    waiting = None
    await enqueue_download(Download(
        id=randint(1_000_000_000, 9_999_999_999),
        filename=filename,
        filepath=filepath,
        from_message=msg,
        added=time(),
        source='direct_url',
        source_url=url,
        multipart_enabled=multipart_enabled,
        progress_message_future=waiting
    ))


def _episode_number_sort_key(value: str) -> tuple[int, float]:
    try:
        return (0, float(value))
    except Exception:
        return (1, 0.0)


def _format_episode_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value}".rstrip('0').rstrip('.')


async def add_file(_, msg: Message, chat: Chat):
    vfs = VirtualFileSystem()
    path = await _resolve_base_path(vfs, msg, chat)
    if path is None:
        return

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


async def add_animeunity_url(_, msg: Message, chat: Chat):
    anime_url = extract_animeunity_url(msg.text or "")
    if not anime_url:
        return

    vfs = VirtualFileSystem()
    path = await _resolve_base_path(vfs, msg, chat, enforce_root_restriction=False)
    if path is None:
        return

    try:
        anime_name, episodes = await asyncio.to_thread(resolve_animeunity_downloads, anime_url)
    except AnimeUnityError as exc:
        await enqueue_message(msg.reply, text=f"AnimeUnity error: {exc}", quote=True)
        return
    except Exception as exc:
        logging.exception(f'add_animeunity_url | {exc}')
        await enqueue_message(msg.reply, text=f"Unexpected error: {exc}", quote=True)
        return

    series_name, season_from_title = split_series_and_trailing_season(anime_name)
    folder_name = vfs.cleanup_path_name(series_name or anime_name) or "animeunity"
    ok, info = vfs.mkdir(folder_name)
    if not ok:
        text = dedent(f"""
            {info}
            {vfs.get_current_dir_info()}
        """)
        await enqueue_message(msg.reply, text=text, quote=True)
        return

    series_path = os.path.normpath(os.path.join(path, info))
    os.makedirs(vfs.relative_to_absolute_path(series_path), exist_ok=True)
    seen_names_by_season: dict[str, set[str]] = {}
    created_seasons: set[str] = set()
    queued = 0
    skipped_existing = 0
    queued_episode_numbers: list[str] = []
    for episode in episodes:
        season_folder = _season_folder_name(episode.season_number or season_from_title)
        season_path = os.path.normpath(os.path.join(series_path, season_folder))
        if season_path not in created_seasons:
            os.makedirs(vfs.relative_to_absolute_path(season_path), exist_ok=True)
            created_seasons.add(season_path)

        filename = vfs.cleanup_path_name(episode.filename) or f"episode-{episode.episode_number}.mp4"
        season_seen_names = seen_names_by_season.setdefault(season_path, set())
        filename = _build_unique_filename(filename, season_seen_names)
        filepath = os.path.normpath(os.path.join(season_path, filename))
        if isfile(vfs.relative_to_absolute_path(filepath)):
            skipped_existing += 1
            continue
        await _enqueue_direct_url_download(
            msg=msg,
            filepath=filepath,
            filename=filename,
            url=episode.download_url,
            multipart_enabled=bool(getattr(chat, "multipart", True)),
        )
        queued += 1
        queued_episode_numbers.append(episode.episode_number)

    if queued_episode_numbers:
        numeric_eps = []
        for ep_num in queued_episode_numbers:
            try:
                numeric_eps.append(float(ep_num))
            except Exception:
                continue
        if numeric_eps:
            episode_range = f"{_format_episode_number(min(numeric_eps))} - {_format_episode_number(max(numeric_eps))}"
        else:
            ordered = sorted(queued_episode_numbers, key=_episode_number_sort_key)
            episode_range = f"{ordered[0]} - {ordered[-1]}"
    else:
        episode_range = "-"

    summary = dedent(f"""
        Episodi di __{series_name or anime_name}__ aggiunti in coda.
        Range episodi: __{episode_range}__
        Stagioni: __{', '.join(sorted({os.path.basename(p) for p in created_seasons})) or 'Season 01'}__
        Destinazione: __{series_path}__
        Episodi in coda: __{queued}__
        File gia presenti saltati: __{skipped_existing}__
    """)
    await enqueue_message(msg.reply, text=summary, quote=True, parse_mode=ParseMode.MARKDOWN)


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
