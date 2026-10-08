from __future__ import annotations

from pathlib import Path
from typing import Any

from config import (
    CDRAGON_CHAMPION,
    CDRAGON_CHARACTER_BIN,
    DDRAGON_CHAMPION,
    DDRAGON_CHAMPION_LIST,
    DDRAGON_ITEM,
    DDRAGON_RUNE,
    DDRAGON_SUMMONER,
    DDRAGON_VERSION_URL,
    RAW_DIR,
)
from .http import HttpClient


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
