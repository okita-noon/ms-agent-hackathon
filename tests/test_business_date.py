from __future__ import annotations

from datetime import date, datetime, timezone

from src.utils.business_date import JST, today_jst


def test_today_jst_converts_utc_evening_to_next_jst_date():
    utc_now = datetime(2026, 5, 25, 15, 30, tzinfo=timezone.utc)

    assert today_jst(utc_now) == date(2026, 5, 26)


def test_today_jst_treats_naive_datetime_as_jst():
    naive_jst_now = datetime(2026, 5, 26, 0, 30)

    assert today_jst(naive_jst_now) == date(2026, 5, 26)
    assert JST.utcoffset(None).total_seconds() == 9 * 60 * 60
