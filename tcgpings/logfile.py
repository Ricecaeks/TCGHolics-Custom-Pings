"""Log file that survives container rebuilds: one file a day, capped in size, oldest dropped."""

from __future__ import annotations

import datetime as dt
import logging
import os
from logging.handlers import RotatingFileHandler

from tcgpings.config import safe_name


class DailyRotatingFileHandler(RotatingFileHandler):
    """Starts a new file at local midnight or once the current one reaches `max_bytes`.

    Keeps `backup_count` old files (`bot-<node>.log.1` is the newest), so disk use stays under
    `max_bytes * (backup_count + 1)` and, at normal volume, about `backup_count` days of history.
    """

    def __init__(self, filename: str, max_bytes: int, backup_count: int) -> None:
        super().__init__(filename, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        try:  # a file left by the previous container belongs to the day it was last written
            self._day = dt.date.fromtimestamp(os.path.getmtime(self.baseFilename))
        except OSError:
            self._day = dt.date.today()

    def shouldRollover(self, record: logging.LogRecord) -> bool:  # noqa: N802 (logging's name)
        if dt.date.fromtimestamp(record.created) != self._day:
            return True
        return bool(super().shouldRollover(record))

    def doRollover(self) -> None:  # noqa: N802
        super().doRollover()
        self._day = dt.date.today()


def log_file_name(node_name: str) -> str:
    """`bot-<node>.log`: containers on one machine share the log folder, and a process must only ever
    rotate its own file."""
    return f"bot-{safe_name(node_name)}.log"


def file_handler(log_dir: str, max_mb: int, keep: int, node_name: str) -> logging.Handler:
    os.makedirs(log_dir, exist_ok=True)
    return DailyRotatingFileHandler(os.path.join(log_dir, log_file_name(node_name)), max_mb * 1024 * 1024, keep)
