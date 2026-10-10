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
* ``effect`` / ``effectEn`` come from the client string table's in-game
  "enemy info" text (``game_character_enemytooltip_<x>``), with the
  ``game_character_description_<x>`` family as a fallback -- the §kill reward
  prose lives in that ``<mainText>``.
* ``monster_buff`` is a *curated* catalogue: the source keys and granting camp
  are explicit (``MONSTER_BUFF_CATALOG``), because no machine-readable field
  links a reward buff to its monster.
* Missing numbers degrade to ``0``/``0.0``, missing text to ``""`` -- a value
  is never invented.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

from .spelltext import clean_official_text, main_text, title_left
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

# -- Client string table: per-monster "enemy info" text ---------------------
#
# The in-game enemy-info panel (``game_character_enemytooltip_<x>``) is the one
# place that spells out what killing a unit *does* ("击杀这个野怪会为你队伍中
# 还活着的成员提供男爵之手的增益…"). A few units only ship the sibling
# ``game_character_description_<x>`` form (e.g. the Hextech Drake), so both are
# tried, in priority order. The ``<x>`` suffix is the ``Root.name`` key with its
# ``game_character_displayname_`` prefix swapped out and lower-cased.
_DISPLAY_PREFIX = "game_character_displayname_"
_EFFECT_KEY_FAMILIES = (
    "game_character_enemytooltip_",
    "game_character_description_",
)

# Client markup; stripped only when a *plain* string is wanted (buff names).
_TAG = re.compile(r"<[^>]+>")

# Title / source sections that a *body* should not carry. Applied only on the
# no-``<mainText>`` fallback path (see :func:`official_body`).
_BODY_DROP_SECTIONS = tuple(
    re.compile(rf"<{tag}>.*?</{tag}>", re.IGNORECASE | re.DOTALL)
    for tag in ("titleLeft", "titleRight", "postScriptLeft", "postScriptRight")
)

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


# -- Official text helpers ---------------------------------------------------


def _lookup(entries: dict[str, str] | None, key: str) -> str:
    """Raw string-table value for ``key`` (``""`` when absent)."""
    if not entries or not key:
        return ""
    value = entries.get(key)
    return value if isinstance(value, str) else ""


def plain_text(raw: str) -> str:
    """Strip every client markup tag, leaving plain text.

    Used for buff *names*, which must not carry colourisation from the source
    (``<titleLeft><font color='#FFFFFF'>男爵之手</font></titleLeft>``).
    """
    return clean_official_text(_TAG.sub("", raw or ""))


def official_body(raw: str) -> str:
    """Sectioned tooltip -> client-renderable body.

    Prefers ``<mainText>``; when a key has none (e.g.
    ``buff_dragonbuff_chemtech_tooltip`` puts its text right after
    ``<titleLeft>``) it falls back to the whole string with the title / source
    sections removed. Client markup and ``@Token@`` placeholders are kept --
    rendering is the client's job (see ``spelltext``).
    """
    if not raw:
        return ""
    body = main_text(raw)
    if not body:
        body = raw
        for pattern in _BODY_DROP_SECTIONS:
            body = pattern.sub("", body)
    return clean_official_text(body)


def monster_effect_keys(name_key: str) -> tuple[str, ...]:
    """Enemy-info candidate keys derived from a ``Root.name`` localisation key.

    ``game_character_displayname_Baron`` ->
    ``game_character_enemytooltip_baron`` (then the ``..._description_...``
    family). Returns ``()` for an unexpected key shape, so callers degrade to
    ``""`` instead of guessing.
    """
    key = text(name_key)
    if not key.lower().startswith(_DISPLAY_PREFIX):
        return ()
    suffix = key[len(_DISPLAY_PREFIX):].lower()
    return tuple(family + suffix for family in _EFFECT_KEY_FAMILIES)


def resolve_effect(
    entries: dict[str, str] | None, name_key: str
) -> str:
    """Per-monster kill/description text, or ``""`` when no source carries it.

    Never invented: a unit with no enemy-info key (e.g. the Chemtech Drake, the
    Voidgrubs) simply keeps ``""``.
    """
    for key in monster_effect_keys(name_key):
        body = official_body(_lookup(entries, key))
        if body:
            return body
    return ""


# -- Reward-buff catalogue (``monster_buff``) --------------------------------
#
# No machine-readable field links a reward buff to its monster, so the source
# keys and the granting ``camp`` are an explicit, auditable list -- the same
# "hard-code the mapping, pull the text from the client" approach as
# ``MONSTER_ICONS``. Only *active* monsters are covered: Atakhan was removed in
# 26.1, so its 2025 reward buffs are deliberately absent.
class BuffSpec(NamedTuple):
    """One ``monster_buff`` row's sources.

    ``description_key`` must exist in both string tables; ``name_key`` is only
    needed when the description carries no ``<titleLeft>`` (the dragon souls).
    """

    id: str
    kind: str  # epic | drake | soul | camp
    camp: str  # granting camp, aligned with ``monster.camp``
    description_key: str
    name_key: str = ""


MONSTER_BUFF_CATALOG: tuple[BuffSpec, ...] = (
    # -- Epic-monster rewards -------------------------------------------
    BuffSpec("baron_hand", "epic", "baron",
             "game_buff_tooltip_handofbaronv2"),
    BuffSpec("elder_wrath", "epic", "dragon",
             "game_buff_tooltip_elderdragonbuff"),
    BuffSpec("rift_herald", "epic", "riftherald",
             "game_buff_tooltip_riftheraldbuffcounter"),
    BuffSpec("void_touch", "epic", "horde",
             "generatedtip_buff_srt_2024_horde_dot_tooltip"),
    BuffSpec("void_hunger", "epic", "horde",
             "generatedtip_buff_srt_2024_horde_summoner_tooltip"),
    # -- Elemental drake team buffs --------------------------------------
    BuffSpec("drake_infernal", "drake", "dragon",
             "buff_desc_srx_dragonbuffinfernal"),
    BuffSpec("drake_cloud", "drake", "dragon",
             "buff_desc_srx_dragonbuffcloud"),
    BuffSpec("drake_ocean", "drake", "dragon",
             "buff_desc_srx_dragonbuffocean"),
    BuffSpec("drake_mountain", "drake", "dragon",
             "buff_desc_srx_dragonbuffmountain"),
    BuffSpec("drake_chemtech", "drake", "dragon",
             "buff_dragonbuff_chemtech_tooltip"),
    BuffSpec("drake_hextech", "drake", "dragon",
             "buff_dragonbuff_hextech_tooltip"),
    # -- Dragon souls ----------------------------------------------------
    BuffSpec("soul_infernal", "soul", "dragon",
             "buff_dragonsoulinfernal_tooltip",
             "buff_dragonsoulinfernal_name"),
    BuffSpec("soul_cloud", "soul", "dragon",
             "buff_dragonsoulcloud_tooltip",
             "buff_dragonsoulcloud_name"),
    BuffSpec("soul_ocean", "soul", "dragon",
             "buff_dragonsoulocean_tooltip",
             "buff_dragonsoulocean_name"),
    BuffSpec("soul_mountain", "soul", "dragon",
             "buff_dragonsoulmountain_tooltip",
             "buff_dragonsoulmountain_name"),
    BuffSpec("soul_chemtech", "soul", "dragon",
             "buff_dragonsoul_chemtech_tooltip",
             "buff_dragonsoul_chemtech_name"),
    BuffSpec("soul_hextech", "soul", "dragon",
             "buff_dragonsoul_hextech_tooltip",
             "buff_dragonsoul_hextech_name"),
    # -- Camp buffs ------------------------------------------------------
    BuffSpec("blue_crest", "camp", "blue",
             "game_buff_tooltip_crestoftheancientgolem"),
    BuffSpec("red_crest", "camp", "red",
             "game_buff_tooltip_blessingofthelizardelder"),
)


def buff_name(
    entries: dict[str, str] | None, spec: BuffSpec
) -> str:
    """Localized buff name: the description's ``<titleLeft>``, else ``name_key``."""
    title = plain_text(title_left(_lookup(entries, spec.description_key)))
    if title:
        return title
    return plain_text(_lookup(entries, spec.name_key))


def monster_buff_row(
    spec: BuffSpec,
    zh_entries: dict[str, str] | None,
    en_entries: dict[str, str] | None,
    data_version: str,
) -> dict[str, Any] | None:
    """Assemble one ``monster_buff`` row, or ``None`` when it has no text.

    A row whose description does not resolve is skipped -- an empty menu entry
    carries no information, and the client cannot invent one.
    """
    description = official_body(_lookup(zh_entries, spec.description_key))
    if not description:
        return None

    return {
        "id": spec.id,
        "name": buff_name(zh_entries, spec),
        "nameEn": buff_name(en_entries, spec),
        "kind": spec.kind,
        "camp": spec.camp,
        "description": description,
        "descriptionEn": official_body(
            _lookup(en_entries, spec.description_key)
        ),
        "dataVersion": data_version,
    }


def parse_monster_buffs(
    zh_entries: dict[str, str] | None,
    en_entries: dict[str, str] | None,
    data_version: str,
) -> list[dict[str, Any]]:
    """Build the ``monster_buff`` rows in catalogue order (deterministic)."""
    rows: list[dict[str, Any]] = []
    for spec in MONSTER_BUFF_CATALOG:
        row = monster_buff_row(spec, zh_entries, en_entries, data_version)
        if row is not None:
            rows.append(row)
    return rows


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
        "effect": resolve_effect(zh_entries, name_key),
        "effectEn": resolve_effect(en_entries, name_key),
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
