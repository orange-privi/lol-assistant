"""Parse CommunityDragon ``sru_*`` character BIN data into ``monster`` rows.

Pure functions only -- no I/O. The caller hands in the directory-listing HTML,
a ``{codename: bin_json}`` map and the two string-table entry dicts; the module
returns ready-to-insert row dicts (see ``src/db/writer.py``).

Design notes (see ``docs/monster-etl-design.md``):

* Inclusion = the unit's tag string contains both ``Monster`` and
  ``Monster_Camp``, plus one explicit include and two explicit excludes.
* ``category`` is derived from the tier tokens (``Epic > Large > Medium``,
  everything else ``small``); ``camp`` is the first ``Monster_<X>`` token whose
  ``<X>`` is not a tier/``Camp``/``Buff`` marker.
* Missing numbers degrade to ``0``/``0.0``, missing text to ``""`` -- a value
  is never invented.
"""

from __future__ import annotations

import re
from typing import Any

from .util import float_value, int_value, text

# -- Tag vocabularies (see design doc sections 2-3) -------------------------

# Tier markers, in classification priority order.
TIER_TOKENS = {
    "Monster_Epic",
    "Monster_Large",
    "Monster_Medium",
    "Monster_Small",
}

# Tokens that must never be read as a camp name: the inclusion marker, the
# buff marker, and every tier marker.
CAMP_IGNORE_TOKENS = {"Monster_Camp", "Monster_Buff"} | TIER_TOKENS

# Explicit overrides on top of the "Monster and Monster_Camp" rule.
MONSTER_EXTRA_INCLUDE = {
    # Voidmites: the Voidgrubs' accompanying spawn -- missing ``Monster_Camp``.
    "sru_horde_mini",
}
MONSTER_EXCLUDE = {
    # Jungle companion pet: not a camp monster, and its ``Root.name`` is empty.
    "sru_jungle_companions",
    # Ruined Drake: a legacy drake outside the current elemental roster.
    "sru_dragon_ruined",
}

# Icon paths relative to the CommunityDragon ``game/`` root, hard-coded because
# the PNG file names do not follow any derivable rule from the codename (see
# design doc section 1.3; every path below was verified to exist). An empty
# string means "no unambiguous circle icon" -- never guess or reuse a sibling.
MONSTER_ICONS = {
    "sru_baron": "assets/characters/sru_baron/hud/baron_circle.png",
    "sru_dragon": "assets/characters/sru_dragon/hud/dragon_circle.png",
    "sru_dragon_air": "assets/characters/sru_dragon_air/hud/dragon_air_circle.png",
    "sru_dragon_fire": "assets/characters/sru_dragon_fire/hud/dragon_circle_fire.png",
    "sru_dragon_water": "assets/characters/sru_dragon_water/hud/dragon_circle_water.png",
    "sru_dragon_earth": "assets/characters/sru_dragon_earth/hud/dragon_circle_earth.png",
    "sru_dragon_elder": "assets/characters/sru_dragon_elder/hud/dragon_circle_elder.png",
    "sru_dragon_chemtech": (
        "assets/characters/sru_dragon_chemtech/hud/icons2d/"
        "dragon_circle_chemtech.png"
    ),
    "sru_dragon_hextech": (
        "assets/characters/sru_dragon_hextech/hud/icons2d/"
        "dragon_circle_hextech.png"
    ),
    "sru_gromp": "assets/characters/sru_gromp/hud/gromp_circle.png",
    "sru_blue": "assets/characters/sru_blue/hud/bluesentinel_circle.png",
    "sru_bluemini": "assets/characters/sru_bluemini/hud/sentry_circle.png",
    "sru_bluemini2": "",  # no dedicated hud/; see design doc 13-4
    "sru_red": "assets/characters/sru_red/hud/brambleback_circle.png",
    "sru_redmini": "assets/characters/sru_redmini/hud/cinderling_circle.png",
    "sru_krug": "assets/characters/sru_krug/hud/ancientkrug_circle.png",
    "sru_krugmini": "assets/characters/sru_krugmini/hud/krug_circle.png",
    "sru_krugminimini": "",  # no dedicated hud/; see design doc 13-4
    "sru_crab": "assets/characters/sru_crab/hud/crab_circle_0.png",
    "sru_murkwolf": "assets/characters/sru_murkwolf/hud/greatermurkwolf_circle.png",
    "sru_murkwolfmini": "assets/characters/sru_murkwolfmini/hud/murkwolf_circle.png",
    "sru_razorbeak": "assets/characters/sru_razorbeak/hud/razorbeak_circle.png",
    "sru_razorbeakmini": (
        "assets/characters/sru_razorbeakmini/hud/razorbeakmini_circle.png"
    ),
    "sru_riftherald": (
        "assets/characters/sru_riftherald/hud/sruriftherald_circle.png"
    ),
    "sru_atakhan": "",  # ambiguous v/r/t variants; see design doc 13-3
    "sru_horde": "assets/characters/sru_horde/hud/sru_voidgrub_circle.png",
    "sru_horde_mini": "assets/characters/sru_horde_mini/hud/sru_voidmite_circle.png",
}

# Directory-listing entries look like ``href="sru_baron/"``; only the ``sru_``
# (Summoner's Rift) family is relevant.
_CODENAME_RE = re.compile(r'href="(sru_[^"]+/)"')

# The character root object lives under a flat key ending in this suffix, e.g.
# ``Characters/SRU_Baron/CharacterRecords/Root``.
_ROOT_SUFFIX = "CharacterRecords/Root"


def _tokens(tags: str) -> list[str]:
    """Split a ``unitTagsString`` on ``"|"`` into trimmed, non-empty tokens."""
    if not tags:
        return []
    return [token.strip() for token in tags.split("|") if token.strip()]


def list_monster_codenames(index_html: str) -> list[str]:
    """Enumerate the ``sru_*`` codenames in a directory-listing HTML page.

    Returns a de-duplicated, sorted list so the parse order (and therefore the
    database content) is deterministic.
    """
    if not index_html:
        return []
    names = {match.rstrip("/") for match in _CODENAME_RE.findall(index_html)}
    return sorted(names)


def root_of(bin_json: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the first ``.../CharacterRecords/Root`` object in a BIN file."""
    if not isinstance(bin_json, dict):
        return None
    for key, value in bin_json.items():
        if isinstance(value, dict) and key.endswith(_ROOT_SUFFIX):
            return value
    return None


def should_include(tags: str, codename: str) -> bool:
    """Whether a unit belongs in the ``monster`` table.

    Explicit excludes win over everything; explicit includes win over the base
    "``Monster`` and ``Monster_Camp``" rule.
    """
    if codename in MONSTER_EXCLUDE:
        return False
    if codename in MONSTER_EXTRA_INCLUDE:
        return True
    tokens = _tokens(tags)
    return "Monster" in tokens and "Monster_Camp" in tokens


def classify(tags: str) -> tuple[str, str]:
    """Derive ``(category, camp)`` from a ``unitTagsString`` (see design doc 3).

    ``category`` follows the tier priority ``Epic > Large > Medium > small``;
    ``camp`` is the first ``Monster_<X>`` token whose ``<X>`` is not a tier /
    ``Camp`` / ``Buff`` marker, lower-cased. Unknown input degrades to
    ``("small", "")`` rather than raising.
    """
    tokens = _tokens(tags)

    if "Monster_Epic" in tokens:
        category = "epic"
    elif "Monster_Large" in tokens:
        category = "large"
    elif "Monster_Medium" in tokens:
        category = "medium"
    else:
        category = "small"

    camp = ""
    for token in tokens:
        if token.startswith("Monster_") and token not in CAMP_IGNORE_TOKENS:
            camp = token[len("Monster_"):].lower()
            break

    return category, camp


def _modifiable(root: dict[str, Any], key: str) -> float:
    """Read a ``ModifiableFloat`` (``{"baseValue": ...}``) or a bare number.

    Missing / malformed nodes degrade to ``0.0``.
    """
    node = root.get(key)
    if isinstance(node, dict):
        return float_value(node.get("baseValue"))
    return float_value(node)


def resolve_name(entries: dict[str, str] | None, key: str) -> str:
    """Look up a display name in a string-table ``entries`` dict.

    The key is matched case-insensitively (``key.lower()``); an empty key, an
    absent table or an unresolved key all yield ``""`` (never invented).
    """
    if not key or not entries:
        return ""
    return text(entries.get(key.lower(), ""))


def monster_row(
    codename: str,
    bin_json: dict[str, Any] | None,
    zh_entries: dict[str, str] | None,
    en_entries: dict[str, str] | None,
    data_version: str,
) -> dict[str, Any] | None:
    """Assemble one ``monster`` row, or ``None`` when it should be skipped.

    Returns ``None`` when the BIN has no root object or the unit does not pass
    :func:`should_include`.
    """
    root = root_of(bin_json)
    if root is None:
        return None

    tags = text(root.get("unitTagsString"))
    if not should_include(tags, codename):
        return None

    category, camp = classify(tags)
    name_key = text(root.get("name"))

    return {
        "id": codename,
        "name": resolve_name(zh_entries, name_key),
        "nameEn": resolve_name(en_entries, name_key),
        "category": category,
        "camp": camp,
        "tags": tags,
        "hp": _modifiable(root, "baseHPModifiable"),
        "hpPerLevel": _modifiable(root, "hpPerLevelModifiable"),
        "attackDamage": _modifiable(root, "baseDamageModifiable"),
        "attackDamagePerLevel": _modifiable(root, "damagePerLevelModifiable"),
        "armor": _modifiable(root, "baseArmorModifiable"),
        "armorPerLevel": _modifiable(root, "armorPerLevelModifiable"),
        "magicResist": _modifiable(root, "baseMR"),
        "magicResistPerLevel": _modifiable(root, "mrPerLevel"),
        "moveSpeed": _modifiable(root, "baseMoveSpeedModifiable"),
        "attackSpeed": _modifiable(root, "attackSpeedModifiable"),
        "attackRange": _modifiable(root, "attackRangeModifiable"),
        "goldGiven": int_value(root.get("goldGivenOnDeath")),
        "goldGivenTotal": int_value(root.get("globalGoldGivenOnDeath")),
        "expGiven": int_value(root.get("expGivenOnDeath")),
        "expGivenTotal": int_value(root.get("globalExpGivenOnDeath")),
        "icon": MONSTER_ICONS.get(codename, ""),
        "dataVersion": data_version,
    }


def parse_monsters(
    codenames: list[str],
    bins: dict[str, dict[str, Any] | None],
    zh_entries: dict[str, str] | None,
    en_entries: dict[str, str] | None,
    data_version: str,
) -> list[dict[str, Any]]:
    """Build the ``monster`` rows for ``codenames`` (expected pre-sorted).

    Units with a missing / unparseable BIN or that fail inclusion are skipped;
    the remaining rows keep the input order, so repeated runs are identical.
    """
    rows: list[dict[str, Any]] = []
    for codename in codenames:
        row = monster_row(
            codename,
            bins.get(codename),
            zh_entries,
            en_entries,
            data_version,
        )
        if row is not None:
            rows.append(row)
    return rows
