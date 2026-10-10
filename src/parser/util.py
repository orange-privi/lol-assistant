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


def json_number(value: Any) -> Any:
    """JSON 里整数就写整数。

    客户端按 `List<Double>` 读这些数组，`50` 与 `50.0` 都能吃；但 `50` 更干净、
    也小一圈 —— 逐级数组在整包里出现上万次。非数值原样返回。
    """
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return int(value)
    return value


def clean_rich_text(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return value.strip()
