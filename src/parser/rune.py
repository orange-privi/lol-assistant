from __future__ import annotations

from typing import Any

from .util import int_value, text


def parse_runes(
    runes_file: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand Data Dragon ``runesReforged.json`` into tree + rune rows."""
    trees = []
    runes = []

    for tree in runes_file or []:
        if not isinstance(tree, dict):
            continue

        tree_id = int_value(tree.get("id"))
        trees.append(
            {
                "id": tree_id,
                "key": text(tree.get("key")),
                "name": text(tree.get("name")),
                "icon": text(tree.get("icon")),
            }
        )

        for slot_index, slot in enumerate(tree.get("slots") or []):
            for rune in slot.get("runes") or []:
                if not isinstance(rune, dict):
                    continue
                runes.append(
                    {
                        "id": int_value(rune.get("id")),
                        "treeId": tree_id,
                        "slot": slot_index,
                        "key": text(rune.get("key")),
                        "name": text(rune.get("name")),
                        "shortDesc": text(rune.get("shortDesc")),
                        "longDesc": text(rune.get("longDesc")),
                        "icon": text(rune.get("icon")),
                    }
                )

    return trees, runes
