"""One-off probe #4: does map12.bin.json carry augment (强化符文) numbers?"""
import collections
import json
import re
from pathlib import Path

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 lol-assistant-data/1.0"})
URL = "https://raw.communitydragon.org/latest/game/data/maps/shipping/map12/map12.bin.json"
CACHE = Path("cache/_probe_map12.bin.json")

if not CACHE.exists():
    r = S.get(URL, timeout=180)
    r.raise_for_status()
    CACHE.write_bytes(r.content)
    print(f"downloaded {len(r.content)} bytes")
data = json.loads(CACHE.read_text(encoding="utf-8"))
print("top-level keys:", len(data))

# 1) 谁带 Augment 字样
keyhits = collections.Counter()
aug_paths = []
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}/{k}"
            if "augment" in k.lower():
                keyhits[k] += 1
                aug_paths.append(p)
            walk(v, p)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{path}[{i}]")
walk(data)
print("\n带 'augment' 的键名 TOP20:", keyhits.most_common(20))
print("\n示例路径:")
for p in aug_paths[:12]:
    print("  ", p)

# 2) 取一个 Augment 对象看结构
parents = [p for p in aug_paths if not p.endswith("EventToTrack")]
if parents:
    p = parents[0]
    node = data
    for seg in p.strip("/").split("/"):
        m = re.match(r"(.*)\[(\d+)\]$", seg)
        if m:
            node = node[m.group(1)][int(m.group(2))]
        else:
            node = node[seg]
    print("\n示例 augment 对象:", p)
    print(json.dumps(node, ensure_ascii=False)[:1500])

# 3) 统计 Augment 类对象的数量与结构族
print("\n=== 统计 ===")
sizes = collections.Counter(len(aug_paths) and 0)
roots = collections.Counter(p.split("/")[1:3][-1] for p in aug_paths[:0])
# 找所有形如 Maps/ModeSpecificData/Augments/<Name> 的对象
print("含 Augments 的路径数:", sum(1 for p in aug_paths if "Augments" in p))
for p in [x for x in aug_paths if "Augments" in x][:5]:
    print("   ", p)

# 4) 数值：任何 DataValues / SpellDataValues 在 augment 附近？
print("\n=== 数值载体搜索 ===")
n_dv = 0
def find_dv(o, path=""):
    global n_dv
    if isinstance(o, dict):
        for k, v in o.items():
            if "DataValue" in k:
                n_dv += 1
                if n_dv <= 5:
                    print("  ", f"{path}/{k}", "->", json.dumps(v, ensure_ascii=False)[:200])
            find_dv(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            find_dv(v, f"{path}[{i}]")
find_dv(data)
print("  DataValue* 键出现次数:", n_dv)

# 5) 名字反查：170 个 ARAM_ 符文里能在 map12 找到几个
r = S.get("https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/zh_cn/v1/cherry-augments.json", timeout=45).json()
aram = [a for a in r if str(a["augmentNameId"]).startswith("ARAM_")]
blob = CACHE.read_text(encoding="utf-8").lower()
hit = [a["augmentNameId"] for a in aram if a["augmentNameId"].lower() in blob]
hit_no = [a["augmentNameId"][5:] for a in aram if a["augmentNameId"][5:].lower() in blob]
print(f"\n=== ARAM_* 符文 {len(aram)} 条，map12 全文命中 ===")
print(f"  含 'ARAM_x' 全名: {len(hit)}")
print(f"  含裸名 x: {len(hit_no)}")
print("  未命中示例:", [a['augmentNameId'] for a in aram if a['augmentNameId'].lower() not in blob][:12])
