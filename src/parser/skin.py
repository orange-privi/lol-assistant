from __future__ import annotations

from typing import Any

from .util import int_value, text


def parse_skins(
    cdragon: dict[str, Any] | None,
    champion_id: str,
    champion_key: int,
) -> list[dict[str, Any]]:
    """Map CommunityDragon champion skins onto the ``champion_skin`` table."""
    if not cdragon:
        return []

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

        splash = text(skin.get("splashPath"))
        tile = text(skin.get("tilePath"))

        skins.append(
            {
                "championId": champion_id,
                "num": num,
                "name": text(skin.get("name")),
                "chromas": len(skin.get("chromas") or []),
                "hasImage": 1 if splash else 0,
                "localImage": tile or splash,
                "splashUrl": splash,
                "loadingUrl": text(skin.get("loadScreenPath")),
            }
        )

    return skins
