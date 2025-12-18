import logging
import os.path
from ..util import dedent
from time import ctime, time
from typing import List

from pyrogram.enums import ParseMode
from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                            InlineKeyboardMarkup)

from .. import app
from ..rate_limiter import catch_rate_limit
from ..util import human_readable
from .type import Download
from ..manage_path import VirtualFileSystem, BASE_FOLDER
import asyncio

running: int = 0
# List of downloads to stop
stop: List[int] = []

download_queue = asyncio.Queue()


async def run():
    global running
    logging.info('Starting download manager...')

    while True:
        tasks = []
        for _ in range(app.max_concurrent_transmissions - running):
            try:
                download = await download_queue.get()
                logging.info(f"Dequeued download id={download.id} path={download.filepath} | queue size={download_queue.qsize()}")
                if download.filename in [f.get_name() for f in tasks]:
                    text = f'File "{download.filename}" already present in download queue'
                    logging.info(text)
                    await catch_rate_limit(
                        download.progress_message.edit, wait=True, text=dedent(text), parse_mode=ParseMode.MARKDOWN
                    )
                    continue

                task = asyncio.create_task(download_file(download), name=download.filepath)
                tasks.append(task)
                logging.info(f'Started task for id={download.id} ({download.filepath}) | running before start={running}')
                running += 1
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logging.error(e)
                break

        logging.info(f'Max downloads running: {running}')
        await asyncio.gather(*tasks)
        await asyncio.sleep(1)


async def enqueue_download(download: Download):
    await download_queue.put(download)
    logging.info(f"Enqueued download id={download.id} path={download.filepath} | queue size={download_queue.qsize()}")


async def download_file(download: Download):
    global running

    file_path = os.path.join(BASE_FOLDER, download.filepath)
    if os.path.exists(file_path):
        text = f"""
            File with same name ({download.filepath}) already present in current download directory.
            Retry changing folder
        """
        logging.info(text)
        await catch_rate_limit(
            download.progress_message.edit, wait=True, text=dedent(text), parse_mode=ParseMode.MARKDOWN
        )
        running -= 1
        return

    logging.info(f"Starting download id={download.id} -> {file_path}")
    await catch_rate_limit(download.progress_message.edit, wait=False, text=f"Downloading __{download.filepath}__...",
                           parse_mode=ParseMode.MARKDOWN)
    download.started = time()
    # result = await app.download_media(
    result = app.download_media(
        message=download.from_message,
        file_name=file_path,
        progress=progress,
        progress_args=tuple([download]),
        block=False,
    )
    await result


async def progress(received: int, total: int, download: Download):
    global running
    if received == total:
        speed = human_readable(download.size / (download.last_call - download.started))
        text = f"""
                    File downloaded:
                    __{download.filepath}__ 

                    Started at __{ctime(download.started)}__ 
                    Finished at __{ctime(download.last_call)}__
                    Average download speed: __{speed}/s__
                """
        logging.info(text)
        running -= 1
        await catch_rate_limit(download.progress_message.edit, wait=True, text=dedent(text),
                               parse_mode=ParseMode.MARKDOWN)
        logging.info(f"Completed download id={download.id} ({download.filepath}) | elapsed={download.last_call - download.started:.2f}s")
        return

    # This function is called every time that 1MB is downloaded
    if download.id in stop:
        stop.remove(download.id)
        running -= 1
        text = f"Download of __{download.filepath}__ stopped!"
        logging.info(text)
        await catch_rate_limit(download.progress_message.edit,
                               wait=True,
                               text=text,
                               parse_mode=ParseMode.MARKDOWN,
                               )
        await app.stop_transmission()
        logging.info(f"Stopped download id={download.id} ({download.filepath})")
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
    text = f"""
        Downloading: __{download.filepath}__

        Downloaded __{human_readable(received)}__ of __{human_readable(total)}__ (__{percent:.2f}%__)
        Current download speed: __{human_readable(speed)}/s__
        Average download speed: __{human_readable(avg_speed)}/s__  
    """
    logging.debug(text)
    await catch_rate_limit(
        download.progress_message.edit,
        wait=False,
        text=dedent(text),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Stop", callback_data=f"stop {download.id}")
        ]])
    )
    download.last_update = now
    download.last_call = now


async def stopDownload(_, callback: CallbackQuery, chat):
    id = int(callback.data.split()[-1])
    stop.append(id)
    text = "Stopping download..."
    logging.info(text)
    await callback.answer(text)


async def cd(_, callback: CallbackQuery, chat):
    vfs = VirtualFileSystem()
    ok, cur_path = vfs.abs_cd(chat.current_dir)
    if not ok:
        text = ("There was a problem moving to the destination folder.")
        await catch_rate_limit(callback.message.reply, text=text)
        return

    new_folder = callback.data[3:].strip()
    ok, info = vfs.cd(new_folder)
    if not ok:
        await catch_rate_limit(
            callback.message.reply,
            text=info,
            parse_mode=ParseMode.MARKDOWN
        )
        await catch_rate_limit(
            callback.answer,
            text=info
        )

    await chat.update_current_dir(vfs.current_rel_path)
    text = dedent(f"""
    Changed current folder to __{vfs.current_rel_path}__
    Share the media again to start download
    """)
    logging.info(text)
    await catch_rate_limit(
        callback.message.reply,
        text=text,
        parse_mode=ParseMode.MARKDOWN
    )
    await catch_rate_limit(
        callback.answer,
        text=text
    )
