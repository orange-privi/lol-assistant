"""Merge the English and zh-CN Wiki ``SpellData`` modules into one pack and map
its wiki keys onto Data Dragon summoner-spell ids.

Responsibilities:

* :func:`clean_rendered_html` -- turn the Wiki parser's rendered HTML into the
  plain, Chinese effect text we store (tag strip, entity decode, whitespace
  collapse, English parenthetical localization). Pure / network-free. Retained
  for callers that already hold rendered HTML; no longer used on the effect
  path (see below).
* :func:`build_wiki_summoner_pack` -- combine the two Lua dumps. English values
  win for the numeric fields; the zh-CN sandbox supplies ``disp_name`` and the
  effect text, which is expanded **offline** via
  :func:`src.parser.wiki_expand.expand_wikitext` (the Wiki ``action=parse``
  renderer is no longer used).
* :func:`map_wiki_keys_to_ids` -- resolve ``wikiKey -> Data Dragon id`` using the
  Chinese name when unambiguous and an explicit override table otherwise.
* :func:`load_wiki_summoner_pack` -- load the cached pack, degrading to ``{}``
  when the cache is missing or corrupt (offline rebuild safety).

Nothing here performs I/O against the network.
"""

from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path
from typing import Any

from config import ROOT

from .util import int_value, text
from .wiki_expand import expand_wikitext
from .wiki_lua import parse_lua

# The rendered pack is produced by ``fetch`` (online) and consumed by ``build``
# (offline), so it lives next to the other hand-maintained caches.
DEFAULT_WIKI_SPELL_CACHE = ROOT / "cache" / "summoner_spells_wiki.json"

# Explicit ``wikiKey -> Data Dragon id`` overrides. The Chinese name match is
# ambiguous for most of these (several DDragon ids -- the ``_Jade`` / ``Cherry``
# derivatives -- share one name) or simply differs (Ignite -> SummonerDot), so
# the canonical id is pinned here. Ids absent from Data Dragon (e.g.
# ``SummonerRecall``) are dropped by the resolver, never invented.
SUMMONER_ID_OVERRIDES: dict[str, str] = {
    "Flash": "SummonerFlash",
    "Ignite": "SummonerDot",
    "Heal": "SummonerHeal",
    "Smite": "SummonerSmite",
    "Barrier": "SummonerBarrier",
    "Cleanse": "SummonerBoost",
    "Teleport": "SummonerTeleport",
    "Ghost": "SummonerHaste",
    "Exhaust": "SummonerExhaust",
    "Mark": "SummonerSnowball",
    "Clarity": "SummonerMana",
    "Recall": "SummonerRecall",
}

# Canonical map-key order for the ``maps`` CSV so the output is deterministic.
_MAP_ORDER = ("sr", "ar", "ha", "nb", "tt", "cs")

# English parentheticals the Wiki ``{{pp}}`` renderer emits. Localized so the
# effect text reads as Chinese; unknown parentheticals are kept verbatim but
# wrapped in full-width parentheses.
_PARENTHETICALS: dict[str, str] = {
    "based on level": "基于等级",
    "based on distance to target": "基于与目标的距离",
}

_ANY_TAG = re.compile(r"<[^>]+>")
_BR_TAG = re.compile(r"(?i)<br\s*/?>")
_BLOCK_TAG = re.compile(r"(?i)</(?:p|div|li|tr|h[1-6])>")
_PAREN = re.compile(r"\(([^)]*)\)")
_WHITESPACE = re.compile(r"\s+")


# --------------------------------------------------------------------------
# Rendered-HTML cleanup (pure)
# --------------------------------------------------------------------------


def _localize_parenthetical(match: "re.Match[str]") -> str:
    inner = match.group(1).strip()
    label = _PARENTHETICALS.get(inner.lower())
    if label is not None:
        return "（" + label + "）"
    if not inner:
        return ""
    return "（" + inner + "）"


def clean_rendered_html(rendered_html: str) -> str:
    """Rendered-parser HTML -> plain, Chinese effect text.

    Steps: ``<br>`` / block tags become line breaks, remaining tags are
    stripped, HTML entities (``&#160;`` / ``&amp;`` ...) are decoded, English
    parentheticals are localized and all whitespace runs collapse to a single
    space.
    """
    if not rendered_html:
        return ""
    value = _BR_TAG.sub("\n", rendered_html)
    value = _BLOCK_TAG.sub("\n", value)
    value = _ANY_TAG.sub("", value)
    value = _html.unescape(value)
    value = value.replace("\u00a0", " ")
    value = _PAREN.sub(_localize_parenthetical, value)
    value = _WHITESPACE.sub(" ", value)
    return value.strip()


# --------------------------------------------------------------------------
# Pack construction
# --------------------------------------------------------------------------


def maps_to_csv(raw: Any) -> str:
    """Wiki ``maps`` table -> ``"sr,ar,ha"`` in canonical order.

    A map counts as available when its flag is ``True`` or a non-false string
    (the module sometimes writes ``"unknown"``); anything else is skipped.
    """
    if not isinstance(raw, dict):
        return ""
    names: list[str] = []
    for name in _MAP_ORDER:
        if _is_available(raw.get(name)):
            names.append(name)
    for name, value in raw.items():
        if name not in _MAP_ORDER and _is_available(value):
            names.append(str(name))
    return ",".join(names)


def _is_available(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() not in ("", "false"):
        return True
    return False


def _numeric(en_entry: dict[str, Any], zh_entry: dict[str, Any], key: str) -> int:
    """Read one numeric field, preferring the (authoritative) English module."""
    if key in en_entry:
        return int_value(en_entry.get(key))
    return int_value(zh_entry.get(key))


# The zh-CN sandbox module has a typo that turns one ``{{tt|...}}`` template into
# a single-brace ``{tt|...}}`` (whole library: exactly one occurrence, on Flash;
# the English module has none). MediaWiki then emits the marker literally, so
# ``{`` leaks into the DB. We repair the *render input only* -- the raw ``.lua``
# is never rewritten, keeping the "faithful source" property.
_SINGLE_BRACE_TEMPLATE = re.compile(r"(?<!\{)\{([A-Za-z][A-Za-z0-9_]{0,12})\|")


def normalize_wiki_templates(text: str) -> str:
    """Repair a single-brace ``{name|`` template opener into ``{{name|``.

    Applied to the text handed to the Wiki renderer (never persisted). A real
    double-brace ``{{name|`` is left untouched because its second ``{`` is
    preceded by ``{`` and the lookbehind rejects it.
    """
    if not text:
        return text
    return _SINGLE_BRACE_TEMPLATE.sub(r"{{\1|", text)


def build_wiki_summoner_pack(
    en_lua: str,
    zh_lua: str,
) -> dict[str, dict[str, Any]]:
    """Merge the English and zh-CN Wiki modules into ``{wikiKey: entry}``.

    Each entry carries ``dispName`` (Chinese, from zh with an en fallback),
    ``nameEn`` (the wiki key), the numeric ``cooldown`` / ``castLevel`` /
    ``charges`` / ``recharge``, the ``maps`` CSV and the offline-expanded
    Chinese ``effect``. Numeric fields are cross-checked; a mismatch keeps the
    English value and logs ``[WARN]`` (the zh-CN sandbox can lag behind).

    The effect is produced by :func:`expand_wikitext` over the (typo-repaired)
    source text -- no network renderer is involved, so this runs fully offline.
    """
    en = _as_table(parse_lua(en_lua) if en_lua else {})
    zh = _as_table(parse_lua(zh_lua) if zh_lua else {})

    keys = list(en.keys())
    for key in zh:
        if key not in en:
            keys.append(key)

    pack: dict[str, dict[str, Any]] = {}
    for key in keys:
        en_entry = en.get(key) if isinstance(en.get(key), dict) else {}
        zh_entry = zh.get(key) if isinstance(zh.get(key), dict) else {}
        if not en_entry and not zh_entry:
            continue

        cooldown = _numeric(en_entry, zh_entry, "cooldown")
        cast_level = _numeric(en_entry, zh_entry, "level")
        charges = _numeric(en_entry, zh_entry, "charges")
        recharge = _numeric(en_entry, zh_entry, "recharge")

        for field in ("cooldown", "level", "charges", "recharge"):
            if field in en_entry and field in zh_entry:
                en_value = int_value(en_entry.get(field))
                zh_value = int_value(zh_entry.get(field))
                if en_value != zh_value:
                    print(
                        f"[WARN] wiki {key}: {field} en={en_value} "
                        f"zh={zh_value} (keeping en)"
                    )

        disp_name = (
            text(zh_entry.get("disp_name"))
            or text(en_entry.get("disp_name"))
            or key
        )
        effect_source = text(zh_entry.get("effect")) or text(en_entry.get("effect"))
        # Repair the source typo, then expand offline (no network renderer).
        effect = expand_wikitext(normalize_wiki_templates(effect_source))

        pack[key] = {
            "dispName": disp_name,
            "nameEn": key,
            "cooldown": cooldown,
            "castLevel": cast_level,
            "charges": charges,
            "recharge": recharge,
            "maps": maps_to_csv(en_entry.get("maps") or zh_entry.get("maps")),
            "effect": effect,
        }

    return pack


def _as_table(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


# --------------------------------------------------------------------------
# wikiKey -> Data Dragon id mapping
# --------------------------------------------------------------------------


def _ddragon_index(
    summoner_file: dict[str, Any],
) -> tuple[dict[str, list[str]], set[str]]:
    """``(name -> [ids], {ids})`` for a Data Dragon ``summoner.json``."""
    data = (summoner_file or {}).get("data") or {}
    by_name: dict[str, list[str]] = {}
    ids: set[str] = set()
    for spell_id, spell in data.items():
        if not isinstance(spell, dict):
            continue
        sid = str(spell_id)
        ids.add(sid)
        name = text(spell.get("name"))
        if name:
            by_name.setdefault(name, []).append(sid)
    return by_name, ids


def resolve_summoner_id(
    wiki_key: str,
    disp_name: str,
    by_name: dict[str, list[str]],
    ids: set[str],
) -> str | None:
    """Resolve one wiki key to a Data Dragon id, or ``None`` when unmappable."""
    candidates = [c for c in (by_name.get(disp_name) or []) if c in ids]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Several ids share the Chinese name (``_Jade`` / ``Cherry`` variants);
        # the base id is the one without an underscore suffix.
        base = [c for c in candidates if "_" not in c]
        if len(base) == 1:
            return base[0]

    override = SUMMONER_ID_OVERRIDES.get(wiki_key)
    if override and override in ids:
        return override
    return None


def map_wiki_keys_to_ids(
    wiki_pack: dict[str, dict[str, Any]] | None,
    summoner_file: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """``{Data Dragon id -> wiki entry}`` for every mappable wiki spell.

    Unmappable wiki keys are silently dropped -- the caller leaves those rows
    at their column defaults rather than inventing data.
    """
    if not wiki_pack:
        return {}
    by_name, ids = _ddragon_index(summoner_file)
    result: dict[str, dict[str, Any]] = {}
    for wiki_key, entry in wiki_pack.items():
        if not isinstance(entry, dict):
            continue
        ddragon_id = resolve_summoner_id(
            wiki_key, text(entry.get("dispName")), by_name, ids
        )
        if ddragon_id is None:
            continue
        result[ddragon_id] = entry
    return result


# --------------------------------------------------------------------------
# Cache I/O (offline)
# --------------------------------------------------------------------------


def load_wiki_summoner_pack(
    path: Path | str | None = None,
) -> dict[str, dict[str, Any]]:
    """Load ``cache/summoner_spells_wiki.json``.

    Returns ``{wikiKey: entry}``; a missing or corrupt cache degrades to ``{}``
    so an offline rebuild never aborts (every summoner row then keeps its
    column defaults).
    """
    cache_path = Path(path) if path is not None else DEFAULT_WIKI_SPELL_CACHE
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[WARN] wiki summoner spell cache unavailable ({cache_path}): {exc}")
        return {}

    spells = payload.get("spells") if isinstance(payload, dict) else None
    if not isinstance(spells, dict):
        print(f"[WARN] wiki summoner spell cache malformed ({cache_path})")
        return {}

    return {
        str(key): value
        for key, value in spells.items()
        if isinstance(value, dict)
    }
