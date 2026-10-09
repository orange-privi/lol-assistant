from __future__ import annotations

from typing import Any

from .util import int_value, text

# Data Dragon CDN host. Splash / loading artwork URLs never carry the patch
# version (see docs/offline-data.md §3.3), so no version needs to be threaded
# through here.
DDRAGON_HOST = "https://ddragon.leagueoflegends.com"


def localized_skin_names(
    ddragon_skins: list[dict[str, Any]] | None,
) -> dict[int, str]:
    """Map Data Dragon skin ``num`` -> localized name.

    The deep Data Dragon champion JSON (``raw/<ver>/<locale>/ddragon/
    champions/{id}.json``) already carries the localized skin name per ``num``,
    so it is the authoritative source for ``champion_skin.name``.
    """
    names: dict[int, str] = {}
    if not isinstance(ddragon_skins, list):
        return names
    for skin in ddragon_skins:
        if not isinstance(skin, dict):
            continue
        name = text(skin.get("name"))
        if name:
            names[int_value(skin.get("num"), -1)] = name
    return names


def local_image(champion_id: str, num: int) -> str:
    """In-pack path relative to ``assets/img`` for a skin loading image."""
    if not champion_id:
        return ""
    return f"champion/loading/{champion_id}_{num}.jpg"


def splash_url(champion_id: str, num: int) -> str:
    """Data Dragon online splash-art URL for a skin."""
    if not champion_id:
        return ""
    return (
        f"{DDRAGON_HOST}/cdn/img/champion/splash/{champion_id}_{num}.jpg"
    )


def loading_url(champion_id: str, num: int) -> str:
    """Data Dragon online loading-screen URL for a skin."""
    if not champion_id:
        return ""
    return (
        f"{DDRAGON_HOST}/cdn/img/champion/loading/{champion_id}_{num}.jpg"
    )


def parse_skins(
    cdragon: dict[str, Any] | None,
    champion_id: str,
    champion_key: int,
    ddragon_skins: list[dict[str, Any]] | None = None,
    available_skins: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Map CommunityDragon champion skins onto the ``champion_skin`` table.

    The *row identity* (champion + ``num``) is still derived from CommunityDragon
    ``skins`` (``num = skin_id - champion_key * 1000``): this keeps the row set at
    exactly 2127 and aligned with the Android app's ``(championId, num)``
    strategy. Only the four reported columns get corrected:

    * ``name``         -> localized name from Data Dragon (fallback: CDragon name)
    * ``localImage``   -> ``champion/loading/{id}_{num}.jpg``
    * ``splashUrl``    -> Data Dragon splash URL
    * ``loadingUrl``   -> Data Dragon loading URL
    * ``hasImage``     -> membership in the probed availability cache, or the
                          legacy ``splashPath`` heuristic when the cache is absent
    """
    if not cdragon:
        return []

    localized = localized_skin_names(ddragon_skins)
    skins: list[dict[str, Any]] = []

    for index, skin in enumerate(cdragon.get("skins") or []):
        if not isinstance(skin, dict):
            continue

        skin_id = int_value(skin.get("id"), -1)
        if skin_id >= 0 and champion_key > 0:
            num = skin_id - champion_key * 1000
            if num < 0:
                num = index
        else:
            num = index

        # Data Dragon is the localized name source; CommunityDragon otherwise.
        name = localized.get(num) or text(skin.get("name"))

        if available_skins is None:
            # Cache missing/corrupt: keep the previous heuristic so nothing breaks.
            has_image = 1 if text(skin.get("splashPath")) else 0
        else:
            has_image = 1 if f"{champion_id}_{num}" in available_skins else 0

        skins.append(
            {
                "championId": champion_id,
                "num": num,
                "name": name,
                "chromas": len(skin.get("chromas") or []),
                "hasImage": has_image,
                "localImage": local_image(champion_id, num),
                "splashUrl": splash_url(champion_id, num),
                "loadingUrl": loading_url(champion_id, num),
            }
        )

    return skins
