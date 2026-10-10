"""One-off probe: locate Hextech ARAM ("Brawl") data in CommunityDragon.

Not part of the ETL. Run:  venv/Scripts/python.exe _probe_brawl.py
"""
import collections
import json
import re

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 lol-assistant-data/1.0"})
LATEST = "https://raw.communitydragon.org/latest"
V1 = LATEST + "/plugins/rcp-be-lol-game-data/global/{loc}/v1"
LOCAL_STRINGTABLE = (
    "raw/16.20/zh_CN/cdragon/game/stringtable/zh_cn.lol.stringtable.json"
)


def get_json(url):
    r = S.get(url, timeout=45)
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def listing(url):
    r = S.get(url, timeout=45)
    if r.status_code != 200:
        return []
    return re.findall(r'href="([^"?/][^"]*)"', r.text)


print("=== 1. cherry-augments.json (强化符文名录) ===")
for loc in ("default", "zh_cn"):
    d = get_json(V1.format(loc=loc) + "/cherry-augments.json")
    if d is None:
        print(f"  {loc}: MISSING")
        continue
    rar = collections.Counter(a.get("rarity") for a in d)
    aram = [a for a in d if str(a.get("augmentNameId", "")).startswith("ARAM_")]
    print(f"  {loc}: n={len(d)} rarity={dict(rar)} ARAM_*={len(aram)}")
    if loc == "zh_cn":
        for a in d[:3]:
            print("    ", json.dumps(a, ensure_ascii=False))

print("\n=== 2. augment-lists.json (按模式分组的符文池) ===")
al = get_json(V1.format(loc="default") + "/augment-lists.json")
if al:
    print("  top-level type:", type(al).__name__, "n=", len(al))
    for e in al[:6]:
        if isinstance(e, dict):
            print("   entry keys:", list(e.keys()))
            for k, v in e.items():
                if isinstance(v, list):
                    print(f"     {k}: n={len(v)} sample={v[:2]}")
                else:
                    print(f"     {k}: {v!r}"[:160])
        else:
            print("   entry:", str(e)[:160])

print("\n=== 3. queues.json / maps.json / game-mode-mutators.json ===")
q = get_json(V1.format(loc="default") + "/queues.json")
if q:
    for e in q:
        s = json.dumps(e, ensure_ascii=False)
        if re.search(r"brawl|aram|kiwi|augment", s, re.I):
            print("  queue:", s[:300])
mp = get_json(V1.format(loc="default") + "/maps.json")
if mp:
    for m in mp:
        if m.get("id") in (12, 30, 35, 33):
            print("  map:", json.dumps(m, ensure_ascii=False)[:220])
mm = get_json(V1.format(loc="default") + "/game-mode-mutators.json")
if mm:
    for e in mm[:3]:
        print("  mutator keys:", list(e.keys()))
        print("  mutator:", json.dumps(e, ensure_ascii=False)[:500])

print("\n=== 4. 客户端 stringtable 关键字命中 (raw/16.20/zh_CN) ===")
try:
    entries = json.load(open(LOCAL_STRINGTABLE, encoding="utf-8"))["entries"]
    for kw in ("kiwi", "brawl", "augment", "championbalancebuff", "augment_", "hex"):
        hits = [k for k in entries if kw in k.lower()]
        print(f"  '{kw}': {len(hits)}  e.g. {hits[:6]}")
except Exception as exc:  # noqa: BLE001
    print("  stringtable unavailable:", exc)

print("\n=== 5. CommunityDragon 里的 Brawl / 增幅 game data 路径 ===")
for path in (
    "/game/data/maps/",
    "/game/data/maps/modespecificdata/",
    "/game/data/maps/modespecificdata/augments/",
    "/game/data/characters/brawl_turret/",
):
    names = listing(LATEST + path)
    kw = [n for n in names if re.search(r"augment|brawl|aram|kiwi", n, re.I)]
    print(f"  {path}: total={len(names)} kw={kw[:14]}")

print("\n=== 6. 历史版本目录（自算 diff 的前提） ===")
root = listing("https://raw.communitydragon.org/")
vers = [n.rstrip("/") for n in root if re.match(r"^\d+\.\d+", n)]
print("  cdragon versions (first 12):", vers[:12])
for v in ("16.20", "16.19", "16.18"):
    r = S.get(f"https://raw.communitydragon.org/{v}/game/data/characters/aatrox/aatrox.bin.json",
              timeout=45, stream=True)
    print(f"  {v} aatrox.bin.json -> {r.status_code} {r.headers.get('Content-Length')}")
    r.close()
