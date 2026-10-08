from __future__ import annotations

from typing import Any

from .util import dumps, int_value, text


def parse_items(item_file: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand Data Dragon ``item.json`` into ``item`` rows."""
    items = []
    for item_id, item in (item_file.get("data") or {}).items():
        if not isinstance(item, dict):
            continue

        gold = item.get("gold") or {}
        image = item.get("image") or {}

        items.append(
            {
                "id": int_value(item_id),
                "name": text(item.get("name")),
                "plaintext": text(item.get("plaintext")),
                "description": text(item.get("description")),
                "goldTotal": int_value(gold.get("total")),
                "goldBase": int_value(gold.get("base")),
                "goldSell": int_value(gold.get("sell")),
                "purchasable": 1 if gold.get("purchasable") else 0,
                "tags": ",".join(item.get("tags") or []),
                "maps": dumps(item.get("maps") or {}),
                "icon": (
                    f"img/item/{image.get('full', '')}"
                    if image.get("full")
                    else ""
                ),
                "fromItems": ",".join(str(x) for x in item.get("from") or []),
                "intoItems": ",".join(str(x) for x in item.get("into") or []),
                "statsJson": dumps(item.get("stats") or {}),
                "depth": int_value(item.get("depth")),
            }
        )

    return items
