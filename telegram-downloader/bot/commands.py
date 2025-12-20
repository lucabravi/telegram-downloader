import logging

from .util import dedent

from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from . import sysinfo
from .rate_limiter import catch_rate_limit
from .manage_path import VirtualFileSystem

from .db import Chat


MAX_MESSAGE_LENGTH = 4000


def _split_message(text: str, max_len: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text into chunks that respect Telegram message length limits."""
    chunks = []
    current = []
    current_len = 0

    for line in text.splitlines():
        # +1 for the newline we'll re-join
        line_len = len(line) + 1
        if current_len + line_len > max_len and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    return chunks


async def start(_, msg: Message, chat: Chat):
    text = dedent("""
        Hello!
        Send me a file and I will download it to my server.
        If you need help send /help
    """)
    logging.info(text)
    await catch_rate_limit(
        msg.reply,
        text=text)


async def bot_help(_, msg: Message, chat: Chat):
    text = dedent(f"""
        /usage | show disk usage
        /cd __foldername__ | choose the subfolder where to download the files
        /cd | go to root foolder
        /autofolder | put downloads on a subfolder named after the forwarded original group
        /autoname | instead of using original filename try to get the best from filename and caption
        /ls | show folders and files in current directories
        /pwd | show current directory
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply, text=text)


async def usage(_, msg: Message, chat: Chat):
    vfs = VirtualFileSystem()
    u = sysinfo.disk_usage(vfs.root)
    text = dedent(f"""
        Disk usage: __{u.used}__ / __{u.capacity}__ (__{u.percent}__)
        Free: __{u.free}__
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply,
                           text=text,
                           parse_mode=ParseMode.MARKDOWN)


async def change_folder(_, msg: Message, chat: Chat):
    new_folder = ' '.join(msg.text.split()[1:])

    vfs = VirtualFileSystem()
    ok, cur_path = vfs.abs_cd(chat.current_dir)
    if not ok:
        text = ("There was a problem moving to this folder. Retry with another one.")
        await catch_rate_limit(msg.reply, text=text)
        return

    ok, err = vfs.cd(new_folder)
    if not ok:
        text = dedent(f"""
        {err}
        {vfs.get_current_dir_info()}""")
        await catch_rate_limit(msg.reply, text=text)
        return

    await chat.update_current_dir(vfs.current_rel_path)

    text = dedent(f"""
        Ok, send me files now and I will put it on this folder:
        {vfs.current_rel_path}
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply, text=text)


async def use_autofolder(_, msg: Message, chat: Chat):
    autofolder = not chat.autofolder
    await chat.update_autofolder(autofolder)
    text = dedent(f"""
        Use autofolder {'enabled' if autofolder else 'disabled'}
    """)
    logging.info(text)
    await catch_rate_limit(
        msg.reply,
        text=text
    )


async def use_autoname(_, msg: Message, chat: Chat):
    autoname = not chat.autoname
    await chat.update_autoname(autoname)
    text = dedent(f"""
        Use autoname {'enabled' if autoname else 'disabled'}
    """)
    logging.info(text)
    await catch_rate_limit(
        msg.reply,
        text=text
    )


async def create_folder(_, msg: Message, chat: Chat):
    new_folder = ' '.join(msg.text.split()[1:])

    vfs = VirtualFileSystem()
    ok, cur_path = vfs.abs_cd(chat.current_dir)
    if not ok:
        text = ("There was a problem creating this new folder.")
        await catch_rate_limit(msg.reply, text=text)
        return

    ok, dir_name = vfs.mkdir(new_folder)
    if not ok:
        text = dedent(f"""
        {dir_name}
        {vfs.get_current_dir_info()}""")
        await catch_rate_limit(msg.reply, text=text)
        return

    base_path = '/' if vfs.current_rel_path == '.' else f"/{vfs.current_rel_path}"
    full_path = f"{base_path}/{dir_name}".replace('//', '/')
    text = dedent(f"""
        Folder "{full_path}" created.
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply, text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton(f"Open new folder \"{new_folder}\"", callback_data=f"cd {new_folder}")
    ]]))


async def show_folder(_, msg: Message, chat: Chat):
    vfs = VirtualFileSystem()
    ok, cur_path = vfs.abs_cd(chat.current_dir)
    if not ok:
        text = dedent("""There's a problem with saved current folder, i reset it to root.
                Change folder with /cd __foldername__ or create a new folder with /mkdir __foldername__.""")
        await chat.update_current_dir('.')
        await catch_rate_limit(msg.reply, text=text)
        return

    directories, files = vfs.ls()
    directories = (f'{len(directories)} \n' + '\n'.join(
        ["- " + directory for directory in directories]) + '\n').strip() if len(
        directories) > 0 else ''
    files = (f'{len(files)} \n' + '\n'.join(["- " + file for file in files]) + '\n').strip() if len(files) > 0 else ''

    text = dedent(f"""
        Path: {'/' if vfs.current_rel_path == '.' else vfs.current_rel_path}
    
        Folders: {directories if directories != '' else '0'}
        Files: {files if files != '' else '0'}
    """)

    logging.info(text)

    # Telegram limits messages to 4096 chars; split long listings into multiple replies.
    if len(text) > MAX_MESSAGE_LENGTH:
        chunks = _split_message(text, MAX_MESSAGE_LENGTH - 32)
        parts = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            header = f"(Part {idx}/{parts})\n" if parts > 1 else ""
            await catch_rate_limit(msg.reply, text=f"{header}{chunk}")
        return

    await catch_rate_limit(msg.reply, text=text)


async def show_pwd(_, msg: Message, chat: Chat):
    vfs = VirtualFileSystem()
    ok, cur_path = vfs.abs_cd(chat.current_dir)
    if not ok:
        text = dedent("""There's a problem with saved current folder, i reset it to root.
                Change folder with /cd __foldername__ or create a new folder with /mkdir __foldername__.""")
        await chat.update_current_dir('.')
        await catch_rate_limit(msg.reply, text=text)
        return

    current = '/' if vfs.current_rel_path == '.' else vfs.current_rel_path
    text = dedent(f"""
        Current directory:
        {current}
    """)
    logging.info(text)
    await catch_rate_limit(msg.reply, text=text)
