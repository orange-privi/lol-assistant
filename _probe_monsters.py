"""Throwaway probe: locate a usable jungle-monster data source."""
import json
import sys

import requests

BROWSER_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
BOT_UA = {"User-Agent": "lol-assistant-data/1.0 (ETL probe)"}


def head(url, ua=BROWSER_UA):
    try:
        r = requests.get(url, headers=ua, timeout=30)
        return r.status_code, len(r.content)
    except Exception as exc:  # noqa: BLE001
        return "ERR", str(exc)[:120]


def get_json(url, ua=BROWSER_UA):
    try:
        r = requests.get(url, headers=ua, timeout=60)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        return r.json(), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:160]


CD = "https://raw.communitydragon.org/latest"

targets = [
    f"{CD}/game/data/characters/",
    f"{CD}/game/data/",
    f"{CD}/game/data/characters/sru_baron/",
    f"{CD}/game/data/characters/sru_dragon/",
    f"{CD}/game/data/characters/sru_blue/",
    f"{CD}/plugins/rcp-be-lol-game-data/global/default/v1/",
    f"{CD}/plugins/rcp-be-lol-game-data/global/default/v1/monsters.json",
    f"{CD}/game/data/characters/jungle/",
    f"{CD}/game/data/characters/sru_red/",
]

for t in targets:
    print(head(t), t)

print("\n=== CDragon characters dir (look for sru_/non-champ) ===")
data, err = get_json(f"{CD}/game/data/characters/")
if err:
    print("err", err)
else:
    names = sorted(data.get("directories", [])) if isinstance(data, dict) else data
    if isinstance(data, dict):
        dirs = sorted(data.get("directories", []))
        files = sorted(data.get("files", []))
        print("dirs:", len(dirs), "files:", len(files))
        sru = [d for d in dirs if d.startswith("sru") or "monster" in d.lower()]
        print("sru/monster dirs:", sru[:60])
    else:
        print(type(data), len(data))

print("\n=== Wiki search: monster modules ===")
for term in ["Module:MonsterData", "Module:Monster", "MonsterData/data"]:
    try:
        r = requests.get(
            "https://wiki.leagueoflegends.com/en-us/api.php",
            params={
                "action": "query", "list": "search", "srsearch": term,
                "format": "json", "srlimit": 5,
            },
            headers=BOT_UA, timeout=30,
        )
        js = r.json()
        hits = [h["title"] for h in js.get("query", {}).get("search", [])]
        print(term, "->", r.status_code, hits)
    except Exception as exc:  # noqa: BLE001
        print(term, "ERR", exc)
