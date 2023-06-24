from dataclasses import dataclass

import psutil

from . import util


@dataclass
class Usage:
    capacity: str
    used: str
    free: str
    percent: str


def disk_usage(f: str) -> Usage:
    u = psutil.disk_usage(f)
    return Usage(
        used=util.human_readable(u.used),
        capacity=util.human_readable(u.total),
        free=util.human_readable(u.total - u.used),
        percent=f"{u.percent:.0f}%"
    )
