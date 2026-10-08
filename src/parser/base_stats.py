from __future__ import annotations

from typing import Any

# CommunityDragon's ``CharacterRecords/Root`` exposes authoritative base stats.
# Data Dragon omits ``attackdamageperlevel`` (it is 0 for every champion in the
# 16.x locale files), so we fill missing values from here.
#
# NOTE: hpRegen/hpRegenPerLevel are deliberately excluded: CommunityDragon
# reports them *per second* while Data Dragon reports them *per 5 seconds*.
BIN_STAT_MAP = {
    "baseDamageModifiable": "attackDamage",
    "damagePerLevelModifiable": "attackDamagePerLevel",
    "baseHPModifiable": "hp",
    "hpPerLevelModifiable": "hpPerLevel",
    "baseArmorModifiable": "armor",
    "armorPerLevelModifiable": "armorPerLevel",
    "baseMR": "magicResist",
    "mrPerLevel": "magicResistPerLevel",
    "baseMoveSpeedModifiable": "moveSpeed",
    "attackRangeModifiable": "attackRange",
    "attackSpeedModifiable": "attackSpeed",
    "attackSpeedPerLevelModifiable": "attackSpeedPerLevel",
}


def _root_node(
    bin_json: dict[str, Any], champion_id: str
) -> dict[str, Any] | None:
    exact = bin_json.get(f"Characters/{champion_id}/CharacterRecords/Root")
    if isinstance(exact, dict):
        return exact

    suffix = "/CharacterRecords/Root"
    for key, value in bin_json.items():
        if key.endswith(suffix) and isinstance(value, dict):
            return value
    return None


def bin_base_stats(
    bin_json: dict[str, Any] | None,
    champion_id: str,
) -> dict[str, float]:
    if not bin_json:
        return {}

    root = _root_node(bin_json, champion_id)
    if not root:
        return {}

    stats: dict[str, float] = {}
    for bin_key, field in BIN_STAT_MAP.items():
        node = root.get(bin_key)
        if isinstance(node, dict) and "baseValue" in node:
            try:
                stats[field] = float(node["baseValue"])
            except (TypeError, ValueError):
                continue
    return stats


def apply_missing_stats(
    entity: dict[str, Any],
    stats: dict[str, float],
) -> None:
    """Fill only the fields Data Dragon left at zero."""
    for field, value in stats.items():
        if not entity.get(field) and value:
            entity[field] = value
