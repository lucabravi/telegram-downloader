from dataclasses import dataclass
import asyncio
from pyrogram.types import Message

@dataclass
class Download:
    id: int
    filename: str
    filepath: str
    from_message: Message
    added: float
    progress_message: Message | None = None
    progress_message_future: asyncio.Future | None = None
    started: float = 0
    last_update: float = 0
    last_call: float = 0
    size: int = 0
    last_received: int = 0
    last_total: int = 0
    last_speed: float = 0
    last_avg_speed: float = 0
    last_percent: float = 0
