"""One-off probe #6: augment definition location, KIWI queue names, real diff sample."""
import json
import re

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 lol-assistant-data/1.0"})
CD = "https://raw.communitydragon.org/latest"
blob = open("cache/_probe_map12.bin.json", encoding="utf-8").read().lower()

print("=== A. 少数符文 vs 多数符文：map12 中能否按名找到 ===")
for nm in ("ARAM_ApexInventor", "ARAM_BladeWaltz", "bladewaltz", "apexinventor",
           "ARAM_GetExcited", "ARAM_KingMe", "kingme"):
    print(f"   {nm}: {blob.count(nm.lower())}")

print("\n=== B. game/data 其它目录（看是否另存符文定义） ===")
def listing(u):
    r = S.get(u, timeout=45)
    return r.status_code, re.findall(r'href="([^"?/][^"]*)"', r.text) if r.status_code == 200 else []
for p in ("shared/", "loadouts/", "cfg/", "particles/"):
    c, n = listing(CD + "/game/data/" + p)
    n = [x for x in n if not x.startswith("http")]
    print(f"   {p} -> {c} {n[:12]}")

print("\n=== C. KIWI 队列文案（确认模式身份） ===")
ent = json.load(open("raw/16.20/zh_CN/cdragon/game/stringtable/zh_cn.lol.stringtable.json",
                    encoding="utf-8"))["entries"]
for k in ("queue_name_kiwi", "queue_name_kiwi_jade", "queue_description_kiwi",
          "queue_description_kiwi_jade", "queue_name_kiwi_5v5", "queue_hover_kiwi"):
    if k in ent:
        print(f"   {k} = {ent[k]!r}")
print("   kiwi 相关 queue_* 键:",
      [k for k in ent if "queue" in k and "kiwi" in k.lower()])

print("\n=== D. 真实改动记录样例：Cassiopeia / Swain 16.19.1 -> 16.20.1 ===")
def flat(o, pre="", out=None):
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            flat(v, f"{pre}.{k}" if pre else k, out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            flat(v, f"{pre}[{i}]", out)
    else:
        out[pre] = o
    return out

DD = "https://ddragon.leagueoflegends.com/cdn/{v}/data/zh_CN/champion/{c}.json"
for cid in ("Cassiopeia", "Swain"):
    a = flat(S.get(DD.format(v="16.19.1", c=cid), timeout=60).json()["data"][cid])
    b = flat(S.get(DD.format(v="16.20.1", c=cid), timeout=60).json()["data"][cid])
    keys = sorted(set(a) | set(b))
    d = [(k, a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)]
    print(f"   {cid}: {len(d)} 处差异")
    for k, va, vb in d[:14]:
        if re.search(r"image|key|id$|name$", k):
            continue
        print(f"     {k}: {str(va)[:55]} -> {str(vb)[:55]}")

print("\n=== E. CN 官方版本公告的可枚举性 ===")
for u in ("https://lol.qq.com/gicp/news/410/",
          "https://lol.qq.com/news/list.shtml",
          "https://lol.qq.com/web201310/news_list.shtml"):
    try:
        r = S.get(u, timeout=30)
        print(f"   {u} -> {r.status_code} {len(r.content)}b")
    except Exception as exc:  # noqa: BLE001
        print(f"   {u} -> ERR {type(exc).__name__}")
