import logging
import math
import os
import os.path
import shutil
from ..util import dedent
from time import ctime, time
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import requests

from pyrogram.enums import ParseMode
from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                            InlineKeyboardMarkup)

from .. import app
from ..rate_limiter import catch_rate_limit, enqueue_message, last_sent_message_id
from ..util import human_readable
from .type import Download
from ..manage_path import VirtualFileSystem, BASE_FOLDER
import asyncio

running: int = 0
# List of downloads to stop
stop: List[int] = []

download_queue = asyncio.Queue()
active_downloads: dict[int, dict[int, Download]] = {}
chat_download_stats: dict[int, dict[str, int]] = {}
status_messages = {}
last_status_text = {}
STATUS_INTERVAL = 5
RUNNING_LOG_INTERVAL = 10
_last_running_log = 0.0
DIRECT_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DIRECT_DOWNLOAD_MIN_MULTIPART_SIZE = 32 * 1024 * 1024
DIRECT_DOWNLOAD_TARGET_PART_SIZE = 64 * 1024 * 1024
DIRECT_DOWNLOAD_MAX_PARTS = 4


def _get_chat_downloads(chat_id: int) -> dict[int, Download]:
    return active_downloads.setdefault(chat_id, {})


def _get_chat_stats(chat_id: int) -> dict[str, int]:
    return chat_download_stats.setdefault(chat_id, {"completed": 0, "failed": 0, "stopped": 0})


def _format_status(downloads: list[Download]) -> str:
    lines = ["Downloading:"]
    for download in downloads:
        total = download.last_total or download.size
        received = download.last_received
        lines.append(download.filepath)
        if total > 0:
            lines.append(
                f"Progress: {human_readable(received)} of {human_readable(total)} ({download.last_percent:.2f}%)"
            )
        else:
            lines.append(f"Progress: {human_readable(received)} (starting or unknown total size)")
        lines.append(
            f"Download speed: {human_readable(download.last_speed)}/s | Average: {human_readable(download.last_avg_speed)}/s"
        )
        lines.append("")
    return "\n".join(lines).strip()


def _try_set_progress_message(download: Download):
    if download.progress_message is not None:
        return
    future = download.progress_message_future
    if future is None:
        return
    if future.done():
        try:
            message = future.result()
            if message is not None:
                download.progress_message = message
        except Exception:
            pass


async def _enqueue_edit_when_ready(download: Download, **kwargs):
    _try_set_progress_message(download)
    if download.progress_message is not None:
        await enqueue_message(download.progress_message.edit, **kwargs)
        return

    future = download.progress_message_future
    if future is None:
        return

    async def _wait_and_edit():
        try:
            message = await future
            if message is None:
                return
            download.progress_message = message
            await enqueue_message(message.edit, **kwargs)
        except Exception as exc:
            logging.error(f'progress_message_wait | {exc}')

    asyncio.create_task(_wait_and_edit())


async def _clear_chat_download_state_if_idle(chat_id: int):
    downloads = active_downloads.get(chat_id)
    if downloads is None:
        return
    if downloads:
        return
    active_downloads.pop(chat_id, None)
    stats = chat_download_stats.pop(chat_id, {"completed": 0, "failed": 0, "stopped": 0})
    old = status_messages.pop(chat_id, None)
    last_status_text.pop(chat_id, None)
    if old:
        await catch_rate_limit(old.delete, wait=False)
        await asyncio.sleep(2)
    summary = (
        f"Downloads completed.\n"
        f"Completed: {stats['completed']} | Failed: {stats['failed']} | Stopped: {stats['stopped']}"
    )
    await enqueue_message(app.send_message, chat_id=chat_id, text=summary)


async def _finalize_download(download: Download, text: str, outcome: str = "completed"):
    if download.finalized:
        return
    download.finalized = True
    await _enqueue_edit_when_ready(
        download,
        text=dedent(text),
        parse_mode=ParseMode.MARKDOWN
    )
    chat_id = download.from_message.chat.id
    stats = _get_chat_stats(chat_id)
    if outcome in stats:
        stats[outcome] += 1
    downloads = _get_chat_downloads(chat_id)
    downloads.pop(download.id, None)
    await _clear_chat_download_state_if_idle(chat_id)


class _DirectDownloadStopped(Exception):
    pass


def _update_direct_download_stats(download: Download, total: int, received: int, delta_bytes: int):
    now = time()
    elapsed = max(now - download.started, 1e-6)
    delta_time = max(now - download.last_call, 1e-6) if download.last_call else elapsed

    download.last_received = received
    download.last_total = total
    download.size = total
    download.last_speed = delta_bytes / delta_time
    download.last_avg_speed = received / elapsed
    download.last_percent = (received / total * 100) if total > 0 else 0
    download.last_call = now
    download.last_update = now


def _probe_byte_range_support(url: str, headers: dict) -> bool:
    probe_headers = dict(headers)
    probe_headers["Range"] = "bytes=0-1"
    try:
        with requests.get(url, headers=probe_headers, stream=True, timeout=20) as probe:
            return probe.status_code == 206 and "Content-Range" in probe.headers
    except Exception:
        return False


def _validate_expected_size(file_path: str, expected_size: int) -> tuple[bool, str | None]:
    if expected_size <= 0:
        return True, None
    try:
        actual_size = os.path.getsize(file_path)
    except OSError as exc:
        return False, f"unable to read final file size: {exc}"
    if actual_size != expected_size:
        return False, f"size mismatch (expected {expected_size} bytes, got {actual_size} bytes)"
    return True, None


def _download_direct_url_single_stream(
    download: Download,
    file_path: str,
    headers: dict,
    response: requests.Response | None = None,
    total_hint: int = 0,
) -> tuple[str, str | None]:
    request_cm = requests.get(download.source_url, headers=headers, stream=True, timeout=30) if response is None else None

    try:
        if response is None:
            response = request_cm.__enter__()
            response.raise_for_status()

        total = int(response.headers.get("Content-Length", 0) or total_hint or 0)
        if total > 0:
            download.size = total
            download.last_total = total

        received = 0
        with open(file_path, "wb") as output:
            for chunk in response.iter_content(chunk_size=DIRECT_DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue
                if download.id in stop:
                    raise _DirectDownloadStopped()

                output.write(chunk)
                received += len(chunk)
                _update_direct_download_stats(download, total, received, len(chunk))

        finish = time()
        download.last_call = finish
        download.last_update = finish
        download.last_received = received
        if total <= 0:
            download.last_total = received
            download.size = received
            download.last_percent = 100
        else:
            ok, error = _validate_expected_size(file_path, total)
            if not ok:
                return "error", error
        return "completed", None
    except _DirectDownloadStopped:
        return "stopped", None
    except Exception as exc:
        return "error", str(exc)
    finally:
        if request_cm is not None:
            request_cm.__exit__(None, None, None)


def _download_direct_url_multipart(
    download: Download,
    file_path: str,
    headers: dict,
    total: int,
) -> tuple[str, str | None]:
    total_parts = min(
        DIRECT_DOWNLOAD_MAX_PARTS,
        max(2, math.ceil(total / DIRECT_DOWNLOAD_TARGET_PART_SIZE)),
    )
    part_size = math.ceil(total / total_parts)
    ranges: list[tuple[int, int, int]] = []
    start = 0
    part_idx = 0
    while start < total:
        end = min(start + part_size - 1, total - 1)
        ranges.append((part_idx, start, end))
        start = end + 1
        part_idx += 1

    bytes_lock = Lock()
    shared_received = {"value": 0}
    part_files = [f"{file_path}.part{idx}" for idx, _, _ in ranges]

    def worker(idx: int, start_byte: int, end_byte: int):
        part_path = f"{file_path}.part{idx}"
        range_headers = dict(headers)
        range_headers["Range"] = f"bytes={start_byte}-{end_byte}"
        with requests.get(download.source_url, headers=range_headers, stream=True, timeout=30) as response:
            response.raise_for_status()
            if response.status_code != 206:
                raise RuntimeError(f"Range not honored for part {idx}, status={response.status_code}")

            with open(part_path, "wb") as output:
                for chunk in response.iter_content(chunk_size=DIRECT_DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    if download.id in stop:
                        raise _DirectDownloadStopped()
                    output.write(chunk)
                    with bytes_lock:
                        shared_received["value"] += len(chunk)
                        _update_direct_download_stats(
                            download=download,
                            total=total,
                            received=shared_received["value"],
                            delta_bytes=len(chunk),
                        )

    try:
        with ThreadPoolExecutor(max_workers=len(ranges)) as executor:
            futures = [executor.submit(worker, idx, start_byte, end_byte) for idx, start_byte, end_byte in ranges]
            for future in as_completed(futures):
                future.result()

        with open(file_path, "wb") as output:
            for part_path in part_files:
                with open(part_path, "rb") as part:
                    shutil.copyfileobj(part, output, length=DIRECT_DOWNLOAD_CHUNK_SIZE)
                try:
                    os.remove(part_path)
                except OSError:
                    pass

        ok, error = _validate_expected_size(file_path, total)
        if not ok:
            return "error", error

        finish = time()
        download.last_call = finish
        download.last_update = finish
        download.last_received = total
        download.last_total = total
        download.size = total
        download.last_percent = 100
        return "completed", None
    except _DirectDownloadStopped:
        return "stopped", None
    except Exception as exc:
        return "error", str(exc)
    finally:
        for part_path in part_files:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass


def _download_direct_url_sync(download: Download, file_path: str) -> tuple[str, str | None]:
    if not download.source_url:
        return "error", "missing source_url for direct download"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Connection": "keep-alive",
    }

    try:
        with requests.get(download.source_url, headers=headers, stream=True, timeout=30) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0) or 0)
            accept_ranges = (response.headers.get("Accept-Ranges") or "").lower()
            can_multipart = (
                download.multipart_enabled
                and
                total >= DIRECT_DOWNLOAD_MIN_MULTIPART_SIZE
                and "bytes" in accept_ranges
                and _probe_byte_range_support(download.source_url, headers)
            )

            if can_multipart:
                logging.info(
                    f"Using multipart direct download id={download.id} parts<={DIRECT_DOWNLOAD_MAX_PARTS} total={total}"
                )
                response.close()
                status, error = _download_direct_url_multipart(
                    download=download,
                    file_path=file_path,
                    headers=headers,
                    total=total,
                )
                if status != "error":
                    return status, error
                logging.warning(f"Multipart failed for {download.filepath}, fallback to single stream: {error}")
                return _download_direct_url_single_stream(
                    download=download,
                    file_path=file_path,
                    headers=headers,
                    total_hint=total,
                )

            return _download_direct_url_single_stream(
                download=download,
                file_path=file_path,
                headers=headers,
                response=response,
                total_hint=total,
            )
    except Exception as exc:
        return "error", str(exc)


async def status_loop():
    while True:
        await asyncio.sleep(STATUS_INTERVAL)
        for chat_id, downloads in list(active_downloads.items()):
            if not downloads:
                old = status_messages.pop(chat_id, None)
                last_status_text.pop(chat_id, None)
                if old:
                    await catch_rate_limit(old.delete, wait=False)
                continue

            current = status_messages.get(chat_id)
            last_sent = last_sent_message_id.get(chat_id)
            should_resend = current is None or (last_sent is not None and current.id != last_sent)
            text = _format_status(list(downloads.values()))
            if not text:
                continue
            if not should_resend and text == last_status_text.get(chat_id):
                continue

            if should_resend:
                if current:
                    await catch_rate_limit(current.delete, wait=False)
                    await asyncio.sleep(2)
                message = await catch_rate_limit(
                    app.send_message,
                    wait=False,
                    chat_id=chat_id,
                    text=text
                )
                if message is None:
                    continue
                status_messages[chat_id] = message
                last_status_text[chat_id] = text
            else:
                await catch_rate_limit(current.edit, wait=False, text=text)
                last_status_text[chat_id] = text
            logging.info(f"Download status for chat {chat_id}:\n{text}")


async def run():
    global running
    logging.info('Starting download manager...')
    active_tasks: set[asyncio.Task] = set()

    while True:
        deferred_due_to_active = False
        queue_scan_limit = download_queue.qsize()
        scanned = 0
        while len(active_tasks) < app.max_concurrent_transmissions and scanned < queue_scan_limit:
            try:
                download = download_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            except Exception as exc:
                logging.error(f'run|get_nowait | {exc}')
                break

            scanned += 1
            logging.info(f"Dequeued download id={download.id} path={download.filepath} | queue size={download_queue.qsize()}")
            if download.filepath in {task.get_name() for task in active_tasks}:
                # Keep the job in queue; do not drop it if another task is writing the same path.
                await download_queue.put(download)
                deferred_due_to_active = True
                logging.info(
                    f'Deferred download id={download.id} path={download.filepath} because same path is currently active'
                )
                continue

            task = asyncio.create_task(download_file(download), name=download.filepath)
            active_tasks.add(task)
            logging.info(f'Started task for id={download.id} ({download.filepath}) | running before start={len(active_tasks) - 1}')

        global _last_running_log
        now = time()
        running = len(active_tasks)
        if now - _last_running_log >= RUNNING_LOG_INTERVAL:
            logging.info(f'Max downloads running: {running}')
            _last_running_log = now

        if not active_tasks:
            if deferred_due_to_active:
                await asyncio.sleep(0.2)
                continue
            await asyncio.sleep(0.5)
            continue

        done, _ = await asyncio.wait(
            active_tasks,
            timeout=1.0,
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            active_tasks.discard(task)
            try:
                task.result()
            except Exception as exc:
                logging.exception(f'download task failed ({task.get_name()}): {exc}')
        running = len(active_tasks)


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
        await _enqueue_edit_when_ready(
            download,
            text=dedent(text),
            parse_mode=ParseMode.MARKDOWN
        )
        running -= 1
        return

    logging.info(f"Starting download id={download.id} -> {file_path}")
    chat_id = download.from_message.chat.id
    _get_chat_downloads(chat_id)[download.id] = download
    await _enqueue_edit_when_ready(
        download,
        text=f"Downloading __{download.filepath}__...",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Stop", callback_data=f"stop {download.id}")
        ]])
    )
    download.started = time()
    if download.source == 'direct_url':
        status, error = await asyncio.to_thread(_download_direct_url_sync, download, file_path)
        running -= 1

        if status == "completed":
            elapsed = max(download.last_call - download.started, 1e-6)
            speed = human_readable(download.last_received / elapsed)
            text = f"""
                File downloaded:
                __{download.filepath}__ 

                Started at __{ctime(download.started)}__ 
                Finished at __{ctime(download.last_call)}__
                Average download speed: __{speed}/s__
            """
            logging.info(text)
            await _finalize_download(download, text, outcome="completed")
            logging.info(f"Completed direct download id={download.id} ({download.filepath}) | elapsed={elapsed:.2f}s")
            return

        if status == "stopped":
            if download.id in stop:
                stop.remove(download.id)
            try:
                os.remove(file_path)
            except OSError:
                pass
            text = f"Download of __{download.filepath}__ stopped!"
            logging.info(text)
            await _finalize_download(download, text, outcome="stopped")
            logging.info(f"Stopped direct download id={download.id} ({download.filepath})")
            return

        try:
            os.remove(file_path)
        except OSError:
            pass
        text = f"""
            Download failed:
            __{download.filepath}__

            Error: {error or 'unknown error'}
        """
        logging.error(dedent(text))
        await _finalize_download(download, text, outcome="failed")
        return

    # result = await app.download_media(
    result = app.download_media(
        message=download.from_message,
        file_name=file_path,
        progress=progress,
        progress_args=tuple([download]),
        block=False,
    )
    try:
        await result
    except Exception as exc:
        text = f"""
            Download failed:
            __{download.filepath}__

            Error: {exc}
        """
        logging.error(dedent(text))
        await _finalize_download(download, text, outcome="failed")
        return

    # Fallback path: occasionally Pyrogram can complete without delivering
    # a final progress callback with received == total.
    if download.id not in _get_chat_downloads(chat_id):
        return

    try:
        final_size = os.path.getsize(file_path)
    except OSError:
        final_size = download.last_received or download.last_total or download.size

    if final_size <= 0:
        text = f"""
            Download failed:
            __{download.filepath}__

            Error: download finished without a readable output file
        """
        logging.error(dedent(text))
        await _finalize_download(download, text, outcome="failed")
        return

    finish = time()
    if download.last_call == 0:
        download.last_call = finish
    download.last_update = finish
    download.last_received = max(download.last_received, final_size)
    download.last_total = max(download.last_total, final_size)
    download.size = max(download.size, final_size)
    download.last_percent = 100

    elapsed = max(download.last_call - download.started, 1e-6)
    speed = human_readable(download.last_received / elapsed)
    text = f"""
        File downloaded:
        __{download.filepath}__ 

        Started at __{ctime(download.started)}__ 
        Finished at __{ctime(download.last_call)}__
        Average download speed: __{speed}/s__
    """
    logging.warning(f"Progress final callback missing for id={download.id}; finalized via download_media fallback")
    logging.info(text)
    await _finalize_download(download, text, outcome="completed")
    logging.info(f"Completed download id={download.id} ({download.filepath}) | elapsed={elapsed:.2f}s [fallback]")


async def progress(received: int, total: int, download: Download):
    global running
    if received == total:
        now = time()
        if download.last_call == 0:
            download.last_call = now
        if download.size == 0:
            download.size = total
            download.last_total = total
        elapsed = max(download.last_call - download.started, 1e-6)
        final_size = download.size or download.last_total or total
        speed = human_readable(final_size / elapsed)
        text = f"""
                    File downloaded:
                    __{download.filepath}__ 

                    Started at __{ctime(download.started)}__ 
                    Finished at __{ctime(download.last_call)}__
                    Average download speed: __{speed}/s__
                """
        logging.info(text)
        running -= 1
        await _finalize_download(download, text, outcome="completed")
        logging.info(f"Completed download id={download.id} ({download.filepath}) | elapsed={elapsed:.2f}s")
        return

    # This function is called every time that 1MB is downloaded
    if download.id in stop:
        stop.remove(download.id)
        running -= 1
        text = f"Download of __{download.filepath}__ stopped!"
        logging.info(text)
        await _finalize_download(download, text, outcome="stopped")
        await app.stop_transmission()
        logging.info(f"Stopped download id={download.id} ({download.filepath})")
        return
    # Only update download progress if the last update is 1 second old
    # : This avoid flood on networks that is more than 1MB/s speed
    now = time()
    if download.last_update != 0 and (time() - download.last_update) < 1:
        download.size = total
        download.last_call = now
        download.last_received = received
        download.last_total = total
        return
    percent = (received / total * 100) if total > 0 else 0
    if download.last_call == 0:
        delta_time = max(now - download.started, 1e-6)
        delta_bytes = received
    else:
        delta_time = max(now - download.last_call, 1e-6)
        delta_bytes = max(received - download.last_received, 0)

    speed = delta_bytes / delta_time
    avg_speed = received / max(now - download.started, 1e-6)
    download.last_received = received
    download.last_total = total
    download.size = total
    download.last_speed = speed
    download.last_avg_speed = avg_speed
    download.last_percent = percent
    logging.debug(f"Progress update id={download.id} {percent:.2f}%")
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
