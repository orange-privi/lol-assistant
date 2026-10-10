from __future__ import annotations

import posixpath
from typing import Any, Iterable

# CommunityDragon's per-champion BIN JSON is a flat map whose top-level keys are
# object paths, e.g.
#   Characters/Kayle/Spells/KayleQAbility/KayleQ
# The object holding a spell's ``mSpell`` (calculations + DataValues) is keyed by
# the *script name*, which matches Data Dragon's spell ``id`` (e.g. "KayleQ",
# "DariusCleave"). Passives have no Data Dragon script id, so we fall back to
# container names and finally to the ability icon name.


def icon_stem(path: Any) -> str:
    """Normalize an icon path/asset name to a bare lowercase stem."""
    if not path:
        return ""
    return posixpath.basename(str(path)).rsplit(".", 1)[0].lower()


def _spell_prefix(champion_id: str) -> str:
    return f"Characters/{champion_id}/Spells/"


def _container_candidates(champion_id: str, slot: str) -> set[str]:
    if slot == "P":
        names = {"PassiveAbility", "Passive", "PAbility"}
    else:
        names = {f"{slot}Ability", slot}
    return {f"{champion_id}{name}".lower() for name in names}


def _icon_index(
    bin_json: dict[str, Any], champion_id: str
) -> dict[str, list[str]]:
    prefix = _spell_prefix(champion_id)
    index: dict[str, list[str]] = {}
    for key, value in bin_json.items():
        if not key.startswith(prefix) or not isinstance(value, dict):
            continue
        mspell = value.get("mSpell")
        if not isinstance(mspell, dict):
            continue
        names = mspell.get("mImgIconName") or []
        if isinstance(names, str):
            names = [names]
        for name in names:
            index.setdefault(icon_stem(name), []).append(key)
    return index


def scope_spell_keys(
    bin_json: dict[str, Any] | None,
    champion_id: str,
    script_id: str,
    slot: str,
    icon_stems: Iterable[str] = (),
) -> list[str]:
    """Return the BIN object *keys* belonging to a single spell.

    Same three-tier match as :func:`scope_spell_objects`; kept separate so
    callers that need the key itself (its leaf segment is the client script
    name, used to look up the string-table tooltip) do not have to re-derive it
    by scanning values.
    """
    if not bin_json:
        return []

    prefix = _spell_prefix(champion_id)

    # 1. Primary: match by Data Dragon script name (exact leaf segment).
    if script_id:
        matched = [
            key
            for key, value in bin_json.items()
            if key.startswith(prefix)
            and key.rsplit("/", 1)[-1] == script_id
            and isinstance(value, dict)
        ]
        if matched:
            return matched

    # 2. Fallback: match by slot-derived container name (case-insensitive).
    containers = _container_candidates(champion_id, slot)
    matched = []
    for key, value in bin_json.items():
        if not key.startswith(prefix) or not isinstance(value, dict):
            continue
        leaf = key[len(prefix):].split("/", 1)[0]
        if leaf.lower() in containers:
            matched.append(key)
    if matched:
        return matched

    # 3. Last resort (passives): match by ability icon stem.
    stems = {icon_stem(s) for s in icon_stems if s}
    if stems:
        index = _icon_index(bin_json, champion_id)
        seen: set[str] = set()
        for stem in stems:
            for key in index.get(stem, []):
                if key not in seen:
                    seen.add(key)
                    matched.append(key)

    return matched


def scope_spell_objects(
    bin_json: dict[str, Any] | None,
    champion_id: str,
    script_id: str,
    slot: str,
    icon_stems: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Return the BIN subtrees belonging to a single spell."""
    if not bin_json:
        return []
    return [
        bin_json[key]
        for key in scope_spell_keys(
            bin_json, champion_id, script_id, slot, icon_stems
        )
    ]
