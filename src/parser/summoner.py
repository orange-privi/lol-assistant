from __future__ import annotations

from typing import Any

from .util import int_value, text
from .wiki_summoner import map_wiki_keys_to_ids


def parse_summoner_spells(
    summoner_file: dict[str, Any],
    wiki_pack: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Expand Data Dragon ``summoner.json`` into ``summoner_spell`` rows.

    ``wiki_pack`` is the LoL Wiki pack produced by ``fetch`` (see
    :mod:`src.parser.wiki_summoner`). When present, its numeric columns
    (``castLevel`` / ``charges`` / ``recharge``) and rendered Chinese ``effect``
    fill the last four columns of every row the wiki key maps to. Rows the wiki
    cannot map keep the column defaults (``0`` / ``0`` / ``0`` / ``""``) -- no
    value is ever invented.
    """
    wiki_by_id = map_wiki_keys_to_ids(wiki_pack, summoner_file)

    spells = []
    for spell_id, spell in (summoner_file.get("data") or {}).items():
        if not isinstance(spell, dict):
            continue

        cooldown = spell.get("cooldown")
        first_cooldown = cooldown[0] if isinstance(cooldown, list) and cooldown else 0
        image = spell.get("image") or {}
        wiki = wiki_by_id.get(str(spell_id)) or {}

        spells.append(
            {
                "id": text(spell_id),
                "key": int_value(spell.get("key")),
                "name": text(spell.get("name")),
                "description": text(spell.get("description")),
                "tooltip": text(spell.get("tooltip")),
                "cooldown": int_value(first_cooldown),
                "cooldownBurn": text(spell.get("cooldownBurn")),
                "costBurn": text(spell.get("costBurn")),
                "rangeBurn": text(spell.get("rangeBurn")),
                "modes": ",".join(spell.get("modes") or []),
                "castLevel": int_value(wiki.get("castLevel")),
                "charges": int_value(wiki.get("charges")),
                "recharge": int_value(wiki.get("recharge")),
                "effect": text(wiki.get("effect")),
                "icon": (
                    f"img/spell/{image.get('full', '')}"
                    if image.get("full")
                    else ""
                ),
            }
        )

    return spells
