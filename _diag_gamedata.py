import json
import re
import time

import requests

UA = {"User-Agent": "lol-assistant-data/1.0"}
CD = "https://raw.communitydragon.org/latest"


def get(u, tries=3):
    for i in range(tries):
        try:
            return requests.get(u, headers=UA, timeout=60)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5)


def ls(u):
    r = get(u)
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    return [x for x in sorted(set(re.findall(r'href="([^"]+)"', r.text)))
            if not x.startswith(("/", "..", "http", "?"))]


print("=== game/data/ ===")
print(ls(f"{CD}/game/data/"))

for cand in [
    f"{CD}/game/data/spells/",
    f"{CD}/game/data/spells/summoner_spells/",
    f"{CD}/game/data/perks/",
    f"{CD}/game/data/runes/",
    f"{CD}/game/data/characters/summonerflash/",
]:
    print(f"\n{cand} -> {ls(cand)}")
