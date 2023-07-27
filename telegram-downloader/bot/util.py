# from .util import dedent as _dedent
from typing import Coroutine

from pyrogram import Client
from pyrogram.types import Message, CallbackQuery

from .db import Chat
from . import ADMINS


def human_readable(n: float) -> str:
    symbol = "B"
    divider = 1
    if n >= 1024 ** 3:
        symbol, divider = "GiB", 1024 ** 3
    elif n >= 1024 ** 2:
        symbol, divider = "MiB", 1024 ** 2
    elif n >= 1024:
        symbol, divider = "KiB", 1024
    t = n / divider
    return f"{t:.2f} {symbol}"


def check_admins(func: Coroutine) -> Coroutine:
    async def x(app: Client, msg: Message):
        chat = await Chat.update_chat(msg)

        if str(msg.chat.id) not in ADMINS and f"@{msg.chat.username}" not in ADMINS:
            return
        await func(app, msg, chat)

    return x


def check_admins_callback(func: Coroutine) -> Coroutine:
    async def x(app: Client, callback: CallbackQuery):
        chat = await Chat.update_chat(callback.message)

        if str(callback.message.chat.id) not in ADMINS and f"@{callback.message.chat.username}" not in ADMINS:
            return
        await func(app, callback, chat)

    return x


import re
compiled_dedent_re = re.compile(r'(^|\n)[ \t]+')
def dedent(text: str) -> str:
    replacement = r'\1'
    return compiled_dedent_re.sub(replacement, text)
