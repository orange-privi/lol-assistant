"""One-off probe #5: structure of the KIWI (Hextech ARAM) augment data in map12."""
import collections
import json
import re
from pathlib import Path

import requests

CACHE = Path("cache/_probe_map12.bin.json")
if not CACHE.exists():
    r = requests.get(
        "https://raw.communitydragon.org/latest/game/data/maps/shipping/map12/map12.bin.json",
        timeout=180, headers={"User-Agent": "Mozilla/5.0 lol-assistant-data/1.0"},
    )
    CACHE.write_bytes(r.content)
data = json.loads(CACHE.read_text(encoding="utf-8"))

print("=== 顶层键（前 25 个 + 计数） ===")
top = list(data)
print(f"  n={len(top)}")
for k in top[:25]:
    print("   ", k[:110])

with_name, with_pool, with_spell = [], [], []
def walk(o, segs):
    if isinstance(o, dict):
        if "AugmentNameId" in o:
            with_name.append((list(segs), o))
        if "AugmentPool" in o:
            with_pool.append((list(segs), o))
        if "mSpell" in o or "SpellObject" in o:
            with_spell.append(list(segs))
        for k, v in o.items():
            segs.append(k)
            walk(v, segs)
            segs.pop()
    elif isinstance(o, list):
        for i, v in enumerate(o):
            segs.append(f"[{i}]")
            walk(v, segs)
            segs.pop()
walk(data, [])

print(f"\n=== 带 AugmentNameId 的对象: {len(with_name)} ===")
names = [o["AugmentNameId"] for _, o in with_name]
print("  unique AugmentNameId:", collections.Counter(names).most_common(45))
print("\n  示例对象:")
segs, obj = with_name[0]
print("   path:", "/" + "/".join(segs))
print("  ", json.dumps(obj, ensure_ascii=False)[:900])

print(f"\n=== 带 AugmentPool 的对象: {len(with_pool)} ===")
for segs, obj in with_pool[:2]:
    print("   path:", "/" + "/".join(segs))
    print("  ", json.dumps(obj, ensure_ascii=False)[:1200])

print(f"\n=== 含 mSpell/SpellObject 的对象: {len(with_spell)}  last sample ===")
for s in with_spell[-3:]:
    print("   ", "/" + "/".join(s)[:150])

print("\n=== token 数值搜索（tooltip 占位符的来源） ===")
blob = CACHE.read_text(encoding="utf-8")
for tok in ("ResistsPerLevel", "AugDuration", "MaxStacks", "DamageAmp", "APPerProc",
            "AdaptiveForce", "CooldownBonus", "AbilityHaste", "AFAmp"):
    print(f"   {tok}: {blob.count(tok)}")

# 找出所有以 Kiwi 命名、且带 DataValues 的 mSpell
print("\n=== 以 Kiwi/Augment 命名的 spell 对象及其 DataValues ===")
found = 0
def scan(o, segs):
    global found
    if isinstance(o, dict):
        for k, v in o.items():
            segs.append(k)
            if isinstance(v, dict) and "DataValues" in v:
                leaf = segs[-1]
                if re.search(r"kiwi|augment|adamant|kingme", leaf, re.I) or \
                   re.search(r"kiwi|augment|adamant|kingme", "/".join(segs), re.I):
                    if found < 6:
                        print("   path:", "/".join(segs)[:130])
                        print("     DataValues:", json.dumps(v["DataValues"], ensure_ascii=False)[:300])
                    found += 1
            scan(v, segs)
            segs.pop()
    elif isinstance(o, list):
        for i, v in enumerate(o):
            segs.append(f"[{i}]"); scan(v, segs); segs.pop()
scan(data, [])
print("  命中数:", found)
