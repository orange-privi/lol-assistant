from __future__ import annotations

from typing import Any

from .util import int_value, text


def parse_summoner_spells(summoner_file: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand Data Dragon ``summoner.json`` into ``summoner_spell`` rows."""
    spells = []
    for spell_id, spell in (summoner_file.get("data") or {}).items():
        if not isinstance(spell, dict):
            continue

        cooldown = spell.get("cooldown")
        first_cooldown = cooldown[0] if isinstance(cooldown, list) and cooldown else 0
        image = spell.get("image") or {}

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
                "icon": (
                    f"img/spell/{image.get('full', '')}"
                    if image.get("full")
                    else ""
                ),
            }
        )

    return spells
