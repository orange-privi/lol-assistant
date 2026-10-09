from __future__ import annotations

import json
from pathlib import Path

from config import ROOT

# Which skins actually have their own splash art on the Data Dragon CDN. The
# list is produced offline by probing each ``{champion}_{num}`` URL once. It is
# stored as ``{"version": "...", "available": ["Aatrox_0", ...]}``.
DEFAULT_AVAILABILITY_CACHE = ROOT / "cache" / "skin_availability.json"


def load_skin_availability(path: Path | str | None = None) -> set[str] | None:
    """Load the set of skins that have their own splash art.

    Returns ``None`` when the cache is missing or corrupt so the caller can fall
    back to its heuristic (``splashPath`` present). A valid cache returns the set
    of ``"{champion}_{num}"`` keys, which may legitimately be empty.
    """
    cache_path = (
        Path(path) if path is not None else DEFAULT_AVAILABILITY_CACHE
    )
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(
            f"[WARN] skin availability cache unavailable ({cache_path}): {exc}"
        )
        return None

    raw_available = (
        payload.get("available") if isinstance(payload, dict) else None
    )
    if not isinstance(raw_available, list):
        print(f"[WARN] skin availability cache malformed ({cache_path})")
        return None

    return {str(item) for item in raw_available if isinstance(item, str)}
