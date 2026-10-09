from __future__ import annotations

from typing import Any

from .calculation import normalize_damage_type
from .prices import price_of
from .skin import parse_skins
from .spell import make_spell, parse_ddragon_spells
from .util import clean_rich_text, int_value, text


def _playstyle(cdragon: dict[str, Any] | None) -> dict[str, Any]:
    if not cdragon:
        return {}
    info = cdragon.get("playstyleInfo")
    return info if isinstance(info, dict) else {}


def _tactical(cdragon: dict[str, Any] | None) -> dict[str, Any]:
    if not cdragon:
        return {}
    info = cdragon.get("tacticalInfo")
    return info if isinstance(info, dict) else {}


def _tags(cdragon: dict[str, Any] | None, fallback: list[str]) -> tuple[str, str]:
    if cdragon:
        info = cdragon.get("championTagInfo")
        if isinstance(info, dict) and info.get("championTagPrimary"):
            return (
                text(info.get("championTagPrimary")),
                text(info.get("championTagSecondary")),
            )
        roles = cdragon.get("roles")
        if isinstance(roles, list) and roles:
            primary = text(roles[0]).capitalize()
            secondary = text(roles[1]).capitalize() if len(roles) > 1 else ""
            return primary, secondary
    primary = fallback[0] if fallback else ""
    secondary = fallback[1] if len(fallback) > 1 else ""
    return primary, secondary


def parse_champion(
    champion: dict[str, Any],
    version: str,
    cdragon: dict[str, Any] | None = None,
    prices: dict[str, dict[str, int]] | None = None,
    available_skins: set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    stats = champion.get("stats") or {}
    info = champion.get("info") or {}
    image = champion.get("image") or {}
    champion_id = text(champion.get("id"))
    champion_key = int_value(champion.get("key"))

    tactical = _tactical(cdragon)
    playstyle = _playstyle(cdragon)
    tag_primary, tag_secondary = _tags(cdragon, champion.get("tags") or [])

    # Price (BE/RP) is not exposed by Data Dragon nor CommunityDragon v1; it is
    # merged from the hand-maintained cache (missing id -> 0, never invented).
    price_be, price_rp = price_of(prices, champion_id)

    # Data Dragon Chinese champion JSON is the primary localized source.
    # CommunityDragon supplements fields Data Dragon does not localize.
    entity = {
        "id": champion_id,
        "key": champion_key,
        "name": text(champion.get("name")),
        "title": text(champion.get("title")),
        "nameEn": text((cdragon or {}).get("name")) or champion_id,
        "titleEn": text((cdragon or {}).get("title")),
        "priceBe": price_be,
        "priceRp": price_rp,
        "lore": clean_rich_text(text(champion.get("lore"))),
        "blurb": clean_rich_text(text(champion.get("blurb"))),
        "tags": ",".join(champion.get("tags") or []),
        "partype": text(champion.get("partype")),
        "infoAttack": int_value(info.get("attack")),
        "infoDefense": int_value(info.get("defense")),
        "infoMagic": int_value(info.get("magic")),
        "infoDifficulty": int_value(info.get("difficulty")),
        "hp": float(stats.get("hp") or 0),
        "hpPerLevel": float(stats.get("hpperlevel") or 0),
        "mp": float(stats.get("mp") or 0),
        "mpPerLevel": float(stats.get("mpperlevel") or 0),
        "hpRegen": float(stats.get("hpregen") or 0),
        "hpRegenPerLevel": float(stats.get("hpregenperlevel") or 0),
        "mpRegen": float(stats.get("mpregen") or 0),
        "mpRegenPerLevel": float(stats.get("mpregenperlevel") or 0),
        "armor": float(stats.get("armor") or 0),
        "armorPerLevel": float(stats.get("armorperlevel") or 0),
        "magicResist": float(stats.get("spellblock") or 0),
        "magicResistPerLevel": float(stats.get("spellblockperlevel") or 0),
        "attackDamage": float(stats.get("attackdamage") or 0),
        "attackDamagePerLevel": float(stats.get("attackdamageperlevel") or 0),
        "attackSpeed": float(stats.get("attackspeed") or 0),
        "attackSpeedPerLevel": float(stats.get("attackspeedperlevel") or 0),
        "attackRange": float(stats.get("attackrange") or 0),
        "moveSpeed": float(stats.get("movespeed") or 0),
        "icon": (
            f"img/champion/{image.get('full', '')}"
            if image.get("full")
            else ""
        ),
        "loading": (
            f"img/champion/loading/{champion_id}_0.jpg"
            if champion_id
            else ""
        ),
        "allyTips": "\n".join(champion.get("allytips") or []),
        "enemyTips": "\n".join(champion.get("enemytips") or []),
        "attackType": text(tactical.get("attackType")),
        "damageType": normalize_damage_type(tactical.get("damageType")),
        "difficultyTier": int_value(tactical.get("difficulty")),
        "tagPrimary": tag_primary,
        "tagSecondary": tag_secondary,
        "playDamage": int_value(playstyle.get("damage")),
        "playDurability": int_value(playstyle.get("durability")),
        "playCrowdControl": int_value(playstyle.get("crowdControl")),
        "playMobility": int_value(playstyle.get("mobility")),
        "playUtility": int_value(playstyle.get("utility")),
    }

    spells = []
    for spell in parse_ddragon_spells(champion, entity["partype"]):
        spells.append(
            make_spell(
                spell,
                champion_id=champion_id,
                calculation_json={},
                data_values={},
                effects={},
                version=version,
            )
        )

    skins = parse_skins(
        cdragon,
        champion_id,
        champion_key,
        champion.get("skins"),
        available_skins,
    )

    return entity, spells, skins
