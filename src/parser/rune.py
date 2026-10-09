from __future__ import annotations

import html
import re
from typing import Any

from .util import int_value, text

# CommunityDragon ``perks.json`` carries fully-resolved rune tooltips, while
# Data Dragon ``runesReforged.json`` still contains ``@Token@`` placeholders
# (e.g. Absorb Life's ``@HealAmount@``). Structure (trees / slots / ids / icons)
# stays sourced from Data Dragon; only the display text is overridden when the
# CDragon entry is present and non-empty.
_BR_TAG = re.compile(r"(?i)<br\s*/?>")
_BLOCK_TAG = re.compile(r"(?i)</(?:p|div|li|tr|h[1-6]|rules)>")
_ANY_TAG = re.compile(r"<[^>]+>")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_INLINE_SPACE = re.compile(r"[ \t\u00a0]+")


def clean_perk_text(value: Any) -> str:
    """CommunityDragon rich-text tooltip -> plain text.

    ``<br>`` / block tags become line breaks (collapsing runs of blank lines to
    one), remaining tags are stripped, entities are decoded, inline whitespace
    collapses to single spaces and each line is trimmed. ``@Token@`` placeholders
    are intentionally preserved -- the client resolves them, and dropping them
    would be more misleading than leaving them.
    """
    if not value:
        return ""
    text_value = str(value)
    text_value = _BR_TAG.sub("\n", text_value)
    text_value = _BLOCK_TAG.sub("\n", text_value)
    text_value = _ANY_TAG.sub("", text_value)
    text_value = html.unescape(text_value)
    lines = [_INLINE_SPACE.sub(" ", line).strip() for line in text_value.split("\n")]
    text_value = "\n".join(lines)
    text_value = _MULTI_NEWLINE.sub("\n\n", text_value)
    return text_value.strip()


def _perk_index(perks: Any) -> dict[int, dict[str, Any]]:
    """``{rune id -> perk}`` from a CommunityDragon ``perks.json`` list."""
    index: dict[int, dict[str, Any]] = {}
    if not isinstance(perks, list):
        return index
    for perk in perks:
        if not isinstance(perk, dict):
            continue
        perk_id = perk.get("id")
        if isinstance(perk_id, int):
            index[perk_id] = perk
    return index


def parse_runes(
    runes_file: list[dict[str, Any]],
    perks: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand Data Dragon ``runesReforged.json`` into tree + rune rows.

    ``shortDesc`` / ``longDesc`` use the CommunityDragon ``perks.json`` text when
    the rune id is present there and the text is non-empty; otherwise they fall
    back to the Data Dragon strings (which may contain ``@Token@`` placeholders).
    """
    perk_index = _perk_index(perks)
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
                rune_id = int_value(rune.get("id"))
                perk = perk_index.get(rune_id)
                short_desc = ""
                long_desc = ""
                if perk:
                    short_desc = clean_perk_text(perk.get("shortDesc"))
                    long_desc = clean_perk_text(perk.get("longDesc"))
                runes.append(
                    {
                        "id": rune_id,
                        "treeId": tree_id,
                        "slot": slot_index,
                        "key": text(rune.get("key")),
                        "name": text(rune.get("name")),
                        "shortDesc": short_desc or text(rune.get("shortDesc")),
                        "longDesc": long_desc or text(rune.get("longDesc")),
                        "icon": text(rune.get("icon")),
                    }
                )

    return trees, runes
