from __future__ import annotations

from typing import Any

from .util import (
    clean_rich_text,
    dumps,
    int_value,
    json_array,
    text,
)


def rank_values(spell: dict[str, Any], key: str) -> list[Any]:
    value = spell.get(key)
    if isinstance(value, list):
        return value

    # Data Dragon sometimes provides a scalar in odd cases.
    if value is None:
        return []
    return [value]


def spell_resource(spell: dict[str, Any], champion_partype: str) -> str:
    """Human-readable resource label for a spell.

    Data Dragon exposes ``costType``/``resource`` as localization templates such
    as ``{{ cost }} {{ abilityresourcename }}`` which are useless to clients.
    Fall back to the champion's partype (or a "no cost" marker) when that
    happens.
    """
    cost = int_value((spell.get("cost") or [0])[0] if isinstance(spell.get("cost"), list) else 0)
    raw = text(spell.get("costType")).strip()
    if raw and "{{" not in raw:
        return raw
    if cost > 0:
        return champion_partype
    return "无消耗"


def parse_ddragon_spells(
    champion: dict[str, Any],
    partype: str,
) -> list[dict[str, Any]]:
    result = []

    for index, spell in enumerate(champion.get("spells") or []):
        result.append(
            {
                "id": text(spell.get("id")),
                "slot": "QWER"[index] if index < 4 else f"S{index}",
                "name": text(spell.get("name")),
                "description": clean_rich_text(text(spell.get("description"))),
                "tooltip": text(spell.get("tooltip")),
                "cooldown": text(spell.get("cooldownBurn")),
                "cost": text(spell.get("costBurn")),
                "range": text(spell.get("rangeBurn")),
                "cooldownLevels": json_array(rank_values(spell, "cooldown")),
                "costLevels": json_array(rank_values(spell, "cost")),
                "rangeLevels": json_array(rank_values(spell, "range")),
                "maxRank": int_value(spell.get("maxrank")),
                "resource": spell_resource(spell, partype),
                "ammoMax": max(0, int_value(spell.get("maxammo"))),
                "icon": (
                    f"img/spell/{spell.get('image', {}).get('full', '')}"
                    if spell.get("image")
                    else ""
                ),
            }
        )

    passive = champion.get("passive") or {}
    if passive:
        result.insert(
            0,
            {
                "id": "",
                "slot": "P",
                "name": text(passive.get("name")),
                "description": clean_rich_text(text(passive.get("description"))),
                "tooltip": clean_rich_text(text(passive.get("description"))),
                "cooldown": "",
                "cost": "",
                "range": "",
                "cooldownLevels": "[]",
                "costLevels": "[]",
                "rangeLevels": "[]",
                "maxRank": 1,
                "resource": "",
                "ammoMax": 0,
                "icon": (
                    f"img/passive/{passive.get('image', {}).get('full', '')}"
                    if passive.get("image")
                    else ""
                ),
            },
        )

    return result


def make_spell(
    base: dict[str, Any],
    champion_id: str,
    calculation_json: dict[str, Any],
    data_values: dict[str, list[Any]],
    effects: dict[str, Any],
    version: str,
    damage_type: str = "",
) -> dict[str, Any]:
    return {
        "championId": champion_id,
        **base,
        "ammoRechargeLevels": "[]",
        "calculationJson": dumps(calculation_json),
        "dataValuesJson": dumps(data_values),
        "effectsJson": dumps(effects),
        "damageType": damage_type,
        "dataVersion": version,
    }
