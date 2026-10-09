import json
import requests

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}
CD = "https://raw.communitydragon.org/latest"


def root(name):
    url = f"{CD}/game/data/characters/{name}/{name}.bin.json"
    js = requests.get(url, headers=BROWSER_UA, timeout=60).json()
    key = next((k for k in js if k.endswith("CharacterRecords/Root")), None)
    return js, js.get(key, {})


for name in ["sru_baron", "sru_gromp"]:
    js, r = root(name)
    print(f"\n===== {name} Root ({len(r)} keys) =====")
    for k, v in r.items():
        s = str(v)
        print(f"  {k:<34} {type(v).__name__:<6} {s[:110]}")

# also show a spell object fully for gromp
js, _ = root("sru_gromp")
for k, v in js.items():
    if "/Spells/" in k:
        print(f"\n===== {k} =====")
        print(json.dumps(v, ensure_ascii=False)[:1500])
        break
