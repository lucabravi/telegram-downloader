import logging
import os.path
from textwrap import dedent
from time import ctime, time, sleep
from typing import List

from pyrogram.enums import ParseMode
from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                            InlineKeyboardMarkup)

from .. import app, BASE_FOLDER
from ..rate_limiter import catch_rate_limit, sync_catch_rate_limit
from ..util import humanReadable
from .type import Download
from threading import Thread

downloads: List[Download] = []
running: int = 0
# List of downloads to stop
stop: List[int] = []


def run():
    global running
    while True:
        for download in downloads:
            try:
                if running == 3:
                    break
                Thread(target=downloadFile, args=(download,)).start()
                running += 1
                downloads.remove(download)
            except Exception as e:
                logging.error(e)
        sleep(1)


def downloadFile(d: Download):
    global running

    file_path = BASE_FOLDER + '/' + d.filename
    if os.path.exists(file_path):
        sync_catch_rate_limit(
            d.progress_message.edit, wait=True, text=dedent(f"""
            File with same name ({d.filename}) already present in current download directory.
            Retry changing folder"""), parse_mode=ParseMode.MARKDOWN
        )
        running -= 1
        return

    sync_catch_rate_limit(d.progress_message.edit, wait=False, text=f"Downloading __{d.filename}__...",
                          parse_mode=ParseMode.MARKDOWN)
    d.started = time()
    result = app.download_media(
        message=d.from_message,
        file_name=BASE_FOLDER + '/' + d.filename,
        progress=progress,
        progress_args=tuple([d])
    )
    if isinstance(result, str):
        speed = humanReadable(d.size / (d.last_call - d.started))
        sync_catch_rate_limit(d.progress_message.edit, wait=True, text=dedent(f"""
                    File __{d.filename}__ downloaded.
    
                    Downloaded started at __{ctime(d.started)}__ and finished at __{ctime(d.last_call)}__
                    It's an average speed of __{speed}/s__
                """), parse_mode=ParseMode.MARKDOWN)
    running -= 1


async def progress(received: int, total: int, download: Download):
    # This function is called every time that 1MB is downloaded
    if download.id in stop:
        await catch_rate_limit(download.progress_message.edit,
                               wait=False,
                               text=f"Download of __{download.filename}__ stopped!",
                               parse_mode=ParseMode.MARKDOWN,
                               )
        await app.stop_transmission()
        stop.remove(download.id)
        return
    # Only update download progress if the last update is 1 second old
    # : This avoid flood on networks that is more than 1MB/s speed
    now = time()
    if download.last_update != 0 and (time() - download.last_update) < 1:
        download.size = total
        download.last_call = now
        return
    percent = received / total * 100
    if download.last_call == 0:
        download.last_call = now - 1
    speed = (1024 ** 2) / (now - download.last_call)
    avg_speed = received / (now - download.started)
    await catch_rate_limit(
        download.progress_message.edit,
        wait=False,
        text=dedent(f'''
                Downloading: __{download.filename}__
    
                Downloaded __{humanReadable(received)}__ of __{humanReadable(total)}__ (__{percent:.2f}%__)
                __{humanReadable(speed)}/s__ or __{humanReadable(avg_speed)}/s__ average since start
            '''),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Stop", callback_data=f"stop {download.id}")
        ]])
    )
    download.last_update = now
    download.last_call = now


async def stopDownload(_, callback: CallbackQuery):
    id = int(callback.data.split()[-1])
    stop.append(id)
    await callback.answer("Stopping...")
