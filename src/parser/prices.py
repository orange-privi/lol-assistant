from __future__ import annotations

import json
from pathlib import Path

from config import ROOT

# Champion BE / RP prices are not exposed by Data Dragon or CommunityDragon v1.
# They are maintained by hand (transcribed from the LoL Wiki) into this cache
# file; every champion missing from it keeps a price of ``0`` (never invented).
DEFAULT_PRICE_CACHE = ROOT / "cache" / "champion_prices.json"


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def load_champion_prices(
    path: Path | str | None = None,
) -> dict[str, dict[str, int]]:
    """Load the champion price cache keyed by Data Dragon champion id.

    Returns a mapping ``{"Aatrox": {"be": 2400, "rp": 880}, ...}``. A missing or
    corrupt cache degrades to an empty mapping (every price becomes ``0``) so the
    build never aborts on bad local data.
    """
    cache_path = Path(path) if path is not None else DEFAULT_PRICE_CACHE
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[WARN] champion price cache unavailable ({cache_path}): {exc}")
        return {}

    raw_prices = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(raw_prices, dict):
        print(f"[WARN] champion price cache malformed ({cache_path})")
        return {}

    prices: dict[str, dict[str, int]] = {}
    for champion_id, entry in raw_prices.items():
        if not isinstance(entry, dict):
            continue
        prices[str(champion_id)] = {
            "be": _as_int(entry.get("be")),
            "rp": _as_int(entry.get("rp")),
        }
    return prices


def price_of(
    prices: dict[str, dict[str, int]] | None,
    champion_id: str,
) -> tuple[int, int]:
    """Return ``(blueEssence, riotPoints)`` for a champion; ``(0, 0)`` when absent."""
    entry = (prices or {}).get(champion_id)
    if not isinstance(entry, dict):
        return 0, 0
    return _as_int(entry.get("be")), _as_int(entry.get("rp"))
