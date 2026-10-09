import json
import re

import requests

UA = {"User-Agent": "lol-assistant-data/1.0"}

print("=== 403 body snippet ===")
try:
    r = requests.get(
        "https://wiki.leagueoflegends.com/en-us/api.php",
        params={"action": "query", "format": "json", "meta": "siteinfo"},
        headers=UA, timeout=40,
    )
    body = r.text
    print("HTTP", r.status_code, "server:", r.headers.get("server"),
          "cf-ray:", r.headers.get("cf-ray"))
    txt = re.sub(r"<[^>]+>", " ", body)
    print(re.sub(r"\s+", " ", txt)[:600])
except Exception as exc:  # noqa: BLE001
    print("EXC", exc)

print("\n=== alternate wiki hosts ===")
for host in [
    "https://leagueoflegends.fandom.com/api.php",
    "https://leagueoflegends.fandom.com/zh/api.php",
    "https://wiki.leagueoflegends.com/zh-cn/api.php",
]:
    try:
        r = requests.get(host, params={"action": "query", "format": "json",
                                       "meta": "siteinfo"},
                         headers=UA, timeout=40)
        print(f"{host} -> HTTP {r.status_code} ct={r.headers.get('content-type')}")
    except Exception as exc:  # noqa: BLE001
        print(f"{host} -> EXC {type(exc).__name__}: {str(exc)[:90]}")

print("\n=== CDragon perks.json: does it carry values? ===")
p = json.load(open("raw/16.20/zh_CN/cdragon/perks.json", encoding="utf-8"))
perks = p if isinstance(p, list) else p.get("perks", [])
print("perks:", len(perks))
print("sample keys:", sorted(perks[0].keys()))
for perk in perks:
    if perk.get("id") in (9101, 8463, 8360):
        print("\n---", perk.get("id"), perk.get("name"))
        print(json.dumps(perk, ensure_ascii=False)[:900])
