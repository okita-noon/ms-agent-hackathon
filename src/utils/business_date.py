from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    return datetime.now(JST)


def today_jst(now: datetime | None = None) -> date:
    current = now or now_jst()
    if current.tzinfo is None:
        current = current.replace(tzinfo=JST)
    return current.astimezone(JST).date()
