import json
import re
import requests

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}
CD = "https://raw.communitydragon.org/latest"

for u in [
    f"{CD}/plugins/rcp-be-lol-game-data/global/zh_cn/v1/objectives.json",
    f"{CD}/plugins/rcp-be-lol-game-data/global/default/v1/objectives.json",
]:
    r = requests.get(u, headers=BROWSER_UA, timeout=60)
    print("==", u, r.status_code, len(r.content))
    if r.status_code == 200:
        js = r.json()
        print(json.dumps(js, ensure_ascii=False)[:2500])

print("\n== maps.json (zh_cn) ==")
r = requests.get(f"{CD}/plugins/rcp-be-lol-game-data/global/zh_cn/v1/maps.json", headers=BROWSER_UA, timeout=60)
print(r.status_code)
if r.status_code == 200:
    print(json.dumps(r.json(), ensure_ascii=False)[:1200])

print("\n== menu l10n dir ==")
r = requests.get(f"{CD}/game/zh_cn/data/menu/en_us/", headers=BROWSER_UA, timeout=60)
links = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
print(len(links), [l for l in links if not l.startswith(("/", "..", "http", "?"))][:40])
