import json
import re
import requests

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}
BOT_UA = {"User-Agent": "lol-assistant-data/1.0 (ETL probe)"}
CD = "https://raw.communitydragon.org/latest"


def listdir(url):
    r = requests.get(url, headers=BROWSER_UA, timeout=60)
    links = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
    return [l for l in links if not l.startswith(("/", "..", "http"))]


print("=== sru_baron dir contents ===")
print(listdir(f"{CD}/game/data/characters/sru_baron/"))

print("\n=== sru_dragon dir contents ===")
print(listdir(f"{CD}/game/data/characters/sru_dragon/"))

print("\n=== sru_gromp dir contents ===")
print(listdir(f"{CD}/game/data/characters/sru_gromp/"))

# fetch one bin.json and inspect shape
for name in ["sru_baron", "sru_gromp"]:
    url = f"{CD}/game/data/characters/{name}/{name}.bin.json"
    try:
        r = requests.get(url, headers=BROWSER_UA, timeout=60)
        print(f"\n=== {name}.bin.json HTTP {r.status_code} len={len(r.content)} ===")
        if r.status_code == 200:
            js = r.json()
            keys = list(js.keys())
            print("top-level keys (%d):" % len(keys))
            for k in keys[:40]:
                v = js[k]
                print("   ", k, type(v).__name__, (str(v)[:100] if not isinstance(v, (dict, list)) else f"len={len(v)}"))
    except Exception as exc:  # noqa: BLE001
        print(name, "ERR", exc)

print("\n=== Wiki: all Module pages mentioning Monster ===")
r = requests.get(
    "https://wiki.leagueoflegends.com/en-us/api.php",
    params={
        "action": "query", "list": "allpages", "apnamespace": 828,
        "apprefix": "Monster", "aplimit": 30, "format": "json",
    },
    headers=BOT_UA, timeout=30,
)
for p in r.json().get("query", {}).get("allpages", []):
    print("   ", p["title"])

print("\n=== Wiki: search 'Baron Nashor stats' ===")
r = requests.get(
    "https://wiki.leagueoflegends.com/en-us/api.php",
    params={"action": "query", "list": "search", "srsearch": "Baron Nashor monster stats",
            "srnamespace": 828, "format": "json", "srlimit": 10},
    headers=BOT_UA, timeout=30,
)
for h in r.json().get("query", {}).get("search", []):
    print("   ", h["title"])
