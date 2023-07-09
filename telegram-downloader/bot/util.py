# from .util import dedent as _dedent
from typing import Coroutine

from pyrogram import Client
from pyrogram.types import Message

from . import ADMINS


def human_readable(n: int) -> str:
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
        if str(msg.chat.id) not in ADMINS and f"@{msg.chat.username}" not in ADMINS:
            return
        await func(app, msg)

    return x


def dedent(text: str):
    ret = ''
    for line in text.splitlines():
        ret += line.strip() + '\n'
    return ret
