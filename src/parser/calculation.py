from __future__ import annotations

from collections import Counter
from typing import Any


DAMAGE_TYPE_NAMES = {
    0: "physical",
    1: "magic",
    2: "true",
}


STAT_NAMES = {
    0: "ATTACK_DAMAGE",
    1: "ABILITY_POWER",
    2: "BONUS_ATTACK_DAMAGE",
    3: "ATTACK_SPEED",
    4: "CRITICAL_STRIKE",
    5: "CRITICAL_STRIKE_DAMAGE",
    6: "ARMOR",
    7: "MAGIC_RESIST",
    8: "HEALTH",
    9: "BONUS_HEALTH",
    10: "MANA",
    11: "BONUS_MANA",
    12: "MOVE_SPEED",
    13: "ABILITY_HASTE",
}


def normalize_stat(stat: Any) -> str:
    if isinstance(stat, str):
        return stat
    return STAT_NAMES.get(stat, str(stat))


def normalize_part(part: dict[str, Any]) -> dict[str, Any]:
    typ = part.get("__type", "")

    if typ == "NamedDataValueCalculationPart":
        return {
            "type": "dataValue",
            "name": part.get("mDataValue", ""),
        }

    if typ == "StatByNamedDataValueCalculationPart":
        return {
            "type": "statDataValue",
            "name": part.get("mDataValue", ""),
            "stat": normalize_stat(part.get("mStat")),
            "statFormula": part.get("mStatFormula"),
        }

    if typ == "StatByCoefficientCalculationPart":
        return {
            "type": "statCoefficient",
            "stat": normalize_stat(part.get("mStat")),
            "coefficient": part.get("mCoefficient"),
            "statFormula": part.get("mStatFormula"),
        }

    if typ == "NumberCalculationPart":
        return {
            "type": "number",
            "value": part.get("mNumber"),
        }

    if typ == "ByCharLevelBreakpointsCalculationPart":
        return {
            "type": "characterLevelBreakpoints",
            "data": part,
        }

    # Unknown calculation parts are deliberately retained instead of dropped.
    return {
        "type": "unknown",
        "class": typ,
        "data": part,
    }


def normalize_calculation(calculation: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    if "DamageType" in calculation:
        result["damageType"] = calculation["DamageType"]

    parts = calculation.get("mFormulaParts") or []
    result["parts"] = [
        normalize_part(part)
        for part in parts
        if isinstance(part, dict)
    ]

    # Preserve other scalar calculation metadata.
    for key in ("mMultiplier", "mCoefficient", "mDataValue"):
        if key in calculation:
            result[key] = calculation[key]

    return result


def extract_calculations(spell_object: dict[str, Any]) -> dict[str, Any]:
    """
    Extract mSpellCalculations from the CommunityDragon champion BIN JSON.

    The BIN JSON is a large object whose values can contain mSpellCalculations.
    We recursively walk it because the exact nesting can vary between champions.
    """
    found: dict[str, Any] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            calculations = value.get("mSpellCalculations")
            if isinstance(calculations, dict):
                for name, calc in calculations.items():
                    if isinstance(calc, dict):
                        found[name] = normalize_calculation(calc)

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(spell_object)
    return found


def extract_data_values(spell_object: dict[str, Any]) -> dict[str, list[Any]]:
    """
    Extract every SpellDataValue from DataValues arrays.
    """
    result: dict[str, list[Any]] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            data_values = value.get("DataValues")
            if isinstance(data_values, list):
                for item in data_values:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    values = item.get("values")
                    if name and isinstance(values, list):
                        result[name] = values

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(spell_object)
    return result


def extract_effects(spell_object: dict[str, Any]) -> dict[str, Any]:
    """
    Keep a conservative normalized copy of effect arrays.

    Different champions have different effect layouts. We intentionally retain
    the original effect object instead of guessing semantic names.
    """
    effects: dict[str, Any] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            effect = value.get("mEffectAmount")
            if isinstance(effect, list):
                effects.setdefault("effectAmounts", []).append(effect)

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(spell_object)
    return effects


def normalize_damage_type(value: Any) -> str:
    if isinstance(value, str):
        return value.removeprefix("k").lower()
    return DAMAGE_TYPE_NAMES.get(value, "")


def spell_damage_type(calculations: dict[str, Any]) -> str:
    """Pick the most common damage type across a spell's calculations."""
    counter: Counter[str] = Counter()
    for calc in calculations.values():
        if isinstance(calc, dict) and "damageType" in calc:
            name = normalize_damage_type(calc["damageType"])
            if name:
                counter[name] += 1
    if not counter:
        return ""
    return counter.most_common(1)[0][0]
