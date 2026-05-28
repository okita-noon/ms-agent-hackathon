from __future__ import annotations

import re
from pathlib import Path
from string import Template
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LINE_TEMPLATE_DIR = _PROJECT_ROOT / "_templates" / "line"


def render_line_template(template_name: str, **variables: Any) -> str:
    template_path = _LINE_TEMPLATE_DIR / template_name
    template = Template(template_path.read_text(encoding="utf-8"))
    rendered = template.safe_substitute(**variables)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered.strip()


def format_line_order_items(items: list[Any] | None) -> str:
    lines: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            product_name = item.get("product_name", "商品")
            quantity = item.get("quantity", "")
            unit = item.get("unit", "")
        else:
            product_name = getattr(item, "product_name", "商品")
            quantity = getattr(item, "quantity", "")
            unit = getattr(item, "unit", "")
        qty_text = _format_quantity(quantity)
        lines.append(f"- {product_name} {qty_text}{unit}".rstrip())
    return "\n".join(lines)


def build_delivery_estimate_line(delivery_estimate: str | None, time_slot: str | None = None) -> str:
    if not delivery_estimate:
        return ""
    if time_slot:
        return f"納品予定は {delivery_estimate}・{time_slot} です。"
    return f"納品予定は {delivery_estimate} です。"


def _format_quantity(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:g}"
    return str(value or "")
