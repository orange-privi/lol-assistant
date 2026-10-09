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
    out = [x for x in sorted(set(re.findall(r'href="([^"]+)"', r.text)))
           if not x.startswith(("/", "..", "http", "?"))]
    return out[:40]


for u in [
    f"{CD}/game/data/shared/",
    f"{CD}/game/data/characters/",
]:
    print(f"{u}\n   -> {ls(u)}")

print("\n=== summoner spell bin candidates ===")
for p in [
    "game/data/spells/summonerflash/summonerflash.bin.json",
    "game/data/spells/summoner_flash/summoner_flash.bin.json",
    "game/data/characters/summonerflash/summonerflash.bin.json",
    "game/data/shared/spells/summonerflash.bin.json",
]:
    try:
        r = get(f"{CD}/{p}")
        print(f"   {r.status_code} {len(r.content):>7}  {p}")
    except Exception as exc:  # noqa: BLE001
        print(f"   EXC {str(exc)[:60]}  {p}")

print("\n=== wiki reachability retry ===")
for host in [
    "https://wiki.leagueoflegends.com/en-us/api.php",
    "https://wiki.leagueoflegends.com/en-us/",
]:
    try:
        r = get(host)
        print(f"   {r.status_code} ct={r.headers.get('content-type')} {host}")
    except Exception as exc:  # noqa: BLE001
        print(f"   EXC {str(exc)[:70]} {host}")
