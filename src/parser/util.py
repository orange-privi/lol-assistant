from __future__ import annotations

import json
import re
from typing import Any


def dumps(value: Any) -> str:
    """Compact UTF-8 JSON. Falls back to tolerant encoding for NaN/Inf."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except ValueError:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )


def text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def json_array(values: Any) -> str:
    if values is None:
        return "[]"
    if not isinstance(values, list):
        return dumps([values])
    return dumps(values)


def clean_rich_text(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return value.strip()
