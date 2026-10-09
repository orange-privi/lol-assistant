from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from config import (
    CDRAGON_CHAMPION,
    CDRAGON_CHARACTER_BIN,
    CDRAGON_CHARACTERS_DIR,
    CDRAGON_LOCALE_DIRS,
    CDRAGON_PERKS,
    CDRAGON_PERKSTYLES,
    CDRAGON_STRINGTABLE,
    CDRAGON_STRINGTABLE_LOCALE,
    CDRAGON_SUMMONER_SPELLS,
    DDRAGON_CHAMPION,
    DDRAGON_CHAMPION_LIST,
    DDRAGON_ITEM,
    DDRAGON_RUNE,
    DDRAGON_SUMMONER,
    DDRAGON_VERSION_URL,
    RAW_DIR,
    WIKI_API,
    WIKI_SPELLDATA_TITLE,
    WIKI_SPELLDATA_ZH_TITLE,
)
from ..parser.wiki_summoner import clean_rendered_html
from .http import HttpClient

# Wiki module titles contain ``:`` / ``/`` which are unsafe in file names.
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class DataSources:
    """Locates and downloads every remote source the ETL depends on."""

    def __init__(self, version: str, locale: str, http: HttpClient):
        self.version = version
        self.locale = locale
        self.http = http

    def _raw(self, *parts: str) -> Path:
        return RAW_DIR / self.version / self.locale / Path(*parts)

    # -- Data Dragon (localized base data) --------------------------------

    def resolve_ddragon_version(self) -> str:
        versions = self.http.get_json(DDRAGON_VERSION_URL)
        if not versions:
            raise RuntimeError("Data Dragon returned no versions")
        # latest is normally a full x.y.1 version.
        return versions[0]

    def download_base_data(self, ddragon_version: str) -> dict[str, Any]:
        return {
            "champions": self.http.save_json(
                DDRAGON_CHAMPION_LIST.format(
                    version=ddragon_version, locale=self.locale
                ),
                self._raw("ddragon", "champion.json"),
            ),
            "items": self.http.save_json(
                DDRAGON_ITEM.format(
                    version=ddragon_version, locale=self.locale
                ),
                self._raw("ddragon", "item.json"),
            ),
            "summoners": self.http.save_json(
                DDRAGON_SUMMONER.format(
                    version=ddragon_version, locale=self.locale
                ),
                self._raw("ddragon", "summoner.json"),
            ),
            "runes": self.http.save_json(
                DDRAGON_RUNE.format(
                    version=ddragon_version, locale=self.locale
                ),
                self._raw("ddragon", "runesReforged.json"),
            ),
        }

    def download_support_seed(self, ddragon_version: str) -> dict[str, Any]:
        """Data Dragon seed files for runes / summoner spells only.

        Same URLs as :meth:`download_base_data`, but scoped so a targeted
        refresh does not touch the champion / item catalogues.
        """
        return {
            "runes": self.http.save_json(
                DDRAGON_RUNE.format(
                    version=ddragon_version, locale=self.locale
                ),
                self._raw("ddragon", "runesReforged.json"),
            ),
            "summoners": self.http.save_json(
                DDRAGON_SUMMONER.format(
                    version=ddragon_version, locale=self.locale
                ),
                self._raw("ddragon", "summoner.json"),
            ),
        }

    def download_champion(self, ddragon_version: str, champion_id: str) -> dict[str, Any]:
        return self.http.save_json(
            DDRAGON_CHAMPION.format(
                version=ddragon_version,
                locale=self.locale,
                champion=champion_id,
            ),
            self._raw("ddragon", "champions", f"{champion_id}.json"),
        )

    # -- CommunityDragon (client data) ------------------------------------

    def download_cdragon_champion(self, champion_key: int) -> dict[str, Any] | None:
        return self.http.save_json_optional(
            CDRAGON_CHAMPION.format(
                version=self.version, key=champion_key
            ),
            self._raw("cdragon", "champions", f"{champion_key}.json"),
        )

    def download_character_bin(self, champion_id: str) -> dict[str, Any] | None:
        name = champion_id.lower()
        return self.http.save_json_optional(
            CDRAGON_CHARACTER_BIN.format(
                version=self.version, champion=name
            ),
            self._raw(
                "cdragon",
                "game",
                "data",
                "characters",
                name,
                f"{name}.bin.json",
            ),
        )

    # -- CommunityDragon jungle monsters ("sru_*") ------------------------

    def stringtable_locale_dir(self, locale: str) -> str:
        """CommunityDragon stringtable directory name for a locale.

        The string tables live at ``game/{locdir}/data/menu/en_us/...`` where
        ``locdir`` is the *lower-cased* locale (``en_US -> en_us``,
        ``zh_CN -> zh_cn``). This is deliberately different from
        :meth:`cdragon_locale` (``en_US -> default``); never mix the two.
        """
        return (locale or "").lower()

    def download_monster_index(self) -> str | None:
        """GET the ``game/data/characters/`` directory listing.

        Returns the raw HTML (used to enumerate ``sru_*`` codenames) and caches
        it under ``raw/.../cdragon/game/data/characters/index.html``. A failed
        listing degrades to ``None`` instead of aborting the build.
        """
        path = self._raw(
            "cdragon", "game", "data", "characters", "index.html"
        )
        try:
            return self.http.save_text(
                CDRAGON_CHARACTERS_DIR.format(version=self.version), path
            )
        except Exception as exc:  # noqa: BLE001 - degraded source is tolerated
            print(f"[WARN] monster index unavailable: {exc}")
            return None

    def download_monster_bin(self, codename: str) -> dict[str, Any] | None:
        """GET one ``sru_*`` character BIN (``{codename}.bin.json``).

        Uses :meth:`HttpClient.save_json_optional` so a single failing unit
        (some return HTML) is skipped rather than aborting the run.
        """
        url = (
            CDRAGON_CHARACTERS_DIR.format(version=self.version)
            + f"{codename}/{codename}.bin.json"
        )
        return self.http.save_json_optional(
            url,
            self._raw(
                "cdragon",
                "game",
                "data",
                "characters",
                codename,
                f"{codename}.bin.json",
            ),
        )

    def download_stringtable(self, locdir: str) -> dict[str, Any] | None:
        """GET a localized string table (``{"entries": {...}, "version": 5}``).

        ``locdir`` is a lower-cased locale directory (``en_us`` / ``zh_cn``),
        not a Data Dragon locale -- see :meth:`stringtable_locale_dir`.
        """
        return self.http.save_json_optional(
            CDRAGON_STRINGTABLE.format(
                version=self.version, locdir=locdir
            ),
            self._raw(
                "cdragon",
                "game",
                "stringtable",
                f"{locdir}.lol.stringtable.json",
            ),
        )

    # -- CommunityDragon localized v1 (runes / summoner spells) -----------

    def cdragon_locale(self) -> str:
        """CommunityDragon locale directory for the current Data Dragon locale."""
        return CDRAGON_LOCALE_DIRS.get(self.locale, self.locale.lower())

    def download_cdragon_perks(self) -> Any | None:
        """Runes ("perks"), 103 entries incl. stat shards + numeric tooltips."""
        return self.http.save_json_optional(
            CDRAGON_PERKS.format(
                version=self.version, locale=self.cdragon_locale()
            ),
            self._raw("cdragon", "perks.json"),
        )

    def download_cdragon_perkstyles(self) -> Any | None:
        """Rune trees ("perk styles")."""
        return self.http.save_json_optional(
            CDRAGON_PERKSTYLES.format(
                version=self.version, locale=self.cdragon_locale()
            ),
            self._raw("cdragon", "perkstyles.json"),
        )

    def download_cdragon_summoner_spells(self) -> Any | None:
        """Summoner spells (39 entries, incl. ones Data Dragon omits)."""
        return self.http.save_json_optional(
            CDRAGON_SUMMONER_SPELLS.format(
                version=self.version, locale=self.cdragon_locale()
            ),
            self._raw("cdragon", "summoner-spells.json"),
        )

    # -- League of Legends Wiki (authoritative summoner-spell numbers) -----

    def _wiki_query_text(self, title: str) -> str | None:
        """Fetch the raw JSON of a module query, caching it under ``raw/wiki``."""
        url = (
            WIKI_API
            + "?action=query&prop=revisions&rvprop=content"
            + "&rvslots=main&format=json&titles="
            + quote(title, safe="")
        )
        path = self._raw("wiki", f"{_slug(title)}.query.json")
        try:
            return self.http.save_text(url, path)
        except Exception as exc:  # noqa: BLE001 - degraded source is tolerated
            print(f"[WARN] wiki module unavailable ({title}): {exc}")
            return None

    def _wiki_module(self, title: str) -> str | None:
        """Return the Lua source of a Wiki module, or ``None`` on failure."""
        raw = self._wiki_query_text(title)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            print(f"[WARN] wiki module not JSON ({title}): {exc}")
            return None

        pages = ((payload or {}).get("query") or {}).get("pages") or {}
        for page in pages.values():
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            slots = revisions[0].get("slots") or {}
            content = (slots.get("main") or {}).get("*")
            if content:
                return content
        return None

    def _write_wiki_module(self, title: str, filename: str) -> str | None:
        path = self._raw("wiki", filename)
        if path.exists():
            return path.read_text(encoding="utf-8")
        lua = self._wiki_module(title)
        if lua is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(lua, encoding="utf-8")
        return lua

    def download_wiki_spelldata(self) -> str | None:
        """English ``Module:SpellData/data`` -> ``raw/.../wiki/*.lua``."""
        return self._write_wiki_module(
            WIKI_SPELLDATA_TITLE, "SpellData_data.lua"
        )

    def download_wiki_spelldata_zh(self) -> str | None:
        """zh-CN sandbox ``SpellData`` module -> ``raw/.../wiki/*.lua``."""
        return self._write_wiki_module(
            WIKI_SPELLDATA_ZH_TITLE, "SpellData_data_zh.lua"
        )

    def render_wiki_wikitext(self, wikitext: str) -> str:
        """DEPRECATED / unused: render Wiki wikitext via the official parser.

        Superseded by the offline expander
        (:func:`src.parser.wiki_expand.expand_wikitext`): the Wiki host now
        answers ``action=parse`` with HTTP 403, so the summoner-spell effect
        text is expanded locally instead. Kept for reference only -- ``fetch``
        and ``build`` no longer call it.

        POSTs to ``action=parse`` and runs the HTML result through
        :func:`clean_rendered_html`. Any failure degrades to an empty string so
        one bad entry never aborts the fetch.
        """
        if not wikitext:
            return ""
        try:
            payload = self.http.post_json(
                WIKI_API,
                {
                    "action": "parse",
                    "contentmodel": "wikitext",
                    "text": wikitext,
                    "prop": "text",
                    "format": "json",
                    "disablelimitreport": "1",
                },
            )
        except Exception as exc:  # noqa: BLE001 - degraded source is tolerated
            print(f"[WARN] wiki render failed: {exc}")
            return ""
        finally:
            # Light throttle: the fetch renders ~60 entries back to back.
            time.sleep(0.05)

        html = ((payload or {}).get("parse") or {}).get("text") or {}
        rendered = html.get("*") if isinstance(html, dict) else None
        if not rendered:
            return ""
        return clean_rendered_html(rendered)


def _slug(title: str) -> str:
    return _SLUG_RE.sub("_", title).strip("_")
