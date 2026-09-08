"""Date helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Shanghai"


def today_iso(timezone_name: str = DEFAULT_TIMEZONE) -> str:
    return datetime.now(tz=ZoneInfo(timezone_name)).date().isoformat()
