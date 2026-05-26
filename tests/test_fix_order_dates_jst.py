from __future__ import annotations

from scripts.fix_order_dates_jst import _build_patch


def test_build_patch_uses_created_at_jst_date():
    doc = {
        "order_date": "2026-05-25",
        "delivery_date": "2026-05-25",
        "preparation_date": "2026-05-25",
        "created_at": "2026-05-25T15:30:00+00:00",
    }

    assert _build_patch(doc, adjust_same_day_fields=True) == {
        "order_date": "2026-05-26",
        "delivery_date": "2026-05-26",
        "preparation_date": "2026-05-26",
    }


def test_build_patch_keeps_explicit_delivery_date():
    doc = {
        "order_date": "2026-05-25",
        "delivery_date": "2026-05-27",
        "preparation_date": "2026-05-25",
        "created_at": "2026-05-25T15:30:00+00:00",
    }

    assert _build_patch(doc, adjust_same_day_fields=True) == {
        "order_date": "2026-05-26",
        "preparation_date": "2026-05-26",
    }


def test_build_patch_noops_when_order_date_matches_jst_created_date():
    doc = {
        "order_date": "2026-05-26",
        "delivery_date": "2026-05-26",
        "created_at": "2026-05-25T15:30:00+00:00",
    }

    assert _build_patch(doc, adjust_same_day_fields=True) is None
