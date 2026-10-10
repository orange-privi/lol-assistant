"""One-off probe #2: confirm KIWI == 海克斯大乱斗, locate augment numbers,
and prove that a patch-to-patch diff is computable from public snapshots."""
import collections
import json
import re

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 lol-assistant-data/1.0"})
CD = "https://raw.communitydragon.org"
ST = "raw/16.20/zh_CN/cdragon/game/stringtable/zh_cn.lol.stringtable.json"
ST_EN = "raw/16.20/zh_CN/cdragon/game/stringtable/en_us.lol.stringtable.json"

print("=== A. stringtable: Brawl / KIWI 文案取证 ===")
try:
    ent = json.load(open(ST, encoding="utf-8"))["entries"]
    for k in ("queue_name_brawl_5v5", "queue_name_brawl_1v1"):
        print(f"  {k} = {ent.get(k)!r}")
    bl = sorted(k for k in ent if k.startswith("brawl_"))
    print(f"  brawl_* keys={len(bl)} samples:")
    for k in bl[:10]:
        print(f"    {k} = {ent[k]!r}"[:150])
    ki = sorted(k for k in ent if k.startswith("kiwi_"))
    print(f"  kiwi_* keys={len(ki)}")
    for k in ki[:12]:
        print(f"    {k} = {ent[k]!r}"[:170])
    # augment 数值占位符统计
    for fam, pat in (("kiwi_*_tooltip", r"^kiwi_.*_tooltip$"),
                     ("kiwi_augment_*", r"^kiwi_augment_"),
                     ("kiwi_aram_*", r"^kiwi_aram_")):
        keys = [k for k in ent if re.match(pat, k)]
        with_tok = [k for k in keys if "@" in ent[k]]
        print(f"  {fam}: {len(keys)} keys, {len(with_tok)} carry @token@")
        for k in with_tok[:4]:
            print(f"    {k} = {ent[k]!r}"[:200])
except Exception as exc:  # noqa: BLE001
    print("  stringtable unavailable:", exc)

print("\n=== B. CDragon game/data 顶层与 maps 目录 ===")
def listing(u):
    r = S.get(u, timeout=45)
    return r.status_code, re.findall(r'href="([^"?/][^"]*)"', r.text) if r.status_code == 200 else []
for u in (CD + "/latest/game/data/", CD + "/latest/game/data/maps/"):
    c, n = listing(u)
    print(f"  {u} -> {c}: {n}")

print("\n=== C. 增幅对象的 game data 落点探测 ===")
for p in ("game/data/maps/modespecificdata/aram_bigbrain/aram_bigbrain.bin.json",
          "game/data/maps/modespecificdata/augments/aram_bigbrain/aram_bigbrain.bin.json",
          "game/data/spells/", "game/data/buffs/", "game/data/shared/"):
    r = S.get(f"{CD}/latest/{p}", timeout=30)
    print(f"  {p} -> {r.status_code} {len(r.content)}b")

print("\n=== D. v1 目录全量（找 brawl/kiwi 专项接口） ===")
c, names = listing(CD + "/latest/plugins/rcp-be-lol-game-data/global/default/v1/")
print("  ", c, len(names))
print("  ", [n for n in names if re.search(r"aug|brawl|kiwi|aram|cherry|map|queue|mutator|mode", n, re.I)])

print("\n=== E. Data Dragon 16.19 -> 16.20 英雄数值 diff（自算） ===")
def dd(ver):
    return S.get(f"https://ddragon.leagueoflegends.com/cdn/{ver}/data/zh_CN/champion.json",
                 timeout=60).json()["data"]
a, b = dd("16.19.1"), dd("16.20.1")
print(f"  champions: {len(a)} -> {len(b)}; added={sorted(set(b)-set(a))}; removed={sorted(set(a)-set(b))}")
changed = []
for cid in sorted(set(a) & set(b)):
    diffs = []
    for f in ("hp", "hpperlevel", "mp", "mpperlevel", "armor", "armorperlevel",
              "spellblock", "spellblockperlevel", "attackdamage",
              "attackdamageperlevel", "attackspeed", "attackspeedperlevel",
              "movespeed", "attackrange"):
        va, vb = a[cid]["stats"].get(f), b[cid]["stats"].get(f)
        if va != vb:
            diffs.append(f"{f}:{va}->{vb}")
    if diffs:
        changed.append((cid, a[cid]["name"], diffs))
print(f"  有基础属性改动的英雄: {len(changed)}")
for cid, nm, d in changed[:12]:
    print(f"    {cid}({nm}): {', '.join(d)}")

print("\n=== F. 技能级 diff（同一英雄，两个版本） ===")
for cid in ["Aatrox", "Ahri", "Sona"]:
    x = S.get(f"https://ddragon.leagueoflegends.com/cdn/16.19.1/data/zh_CN/champion/{cid}.json", timeout=60).json()["data"][cid]
    y = S.get(f"https://ddragon.leagueoflegends.com/cdn/16.20.1/data/zh_CN/champion/{cid}.json", timeout=60).json()["data"][cid]
    def flat(o, pre=""):
        out = {}
        if isinstance(o, dict):
            for k, v in o.items():
                out.update(flat(v, f"{pre}.{k}" if pre else k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                out.update(flat(v, f"{pre}[{i}]"))
        else:
            out[pre] = o
        return out
    fa, fb = flat(x), flat(y)
    keys = sorted(set(fa) | set(fb))
    diffs = [(k, fa.get(k), fb.get(k)) for k in keys if fa.get(k) != fb.get(k)]
    print(f"  {cid}: {len(diffs)} 个叶子差异")
    for k, va, vb in diffs[:8]:
        print(f"    {k}: {str(va)[:70]!r} -> {str(vb)[:70]!r}")

print("\n=== G. CommunityDragon BIN diff（16.19 vs 16.20, Aatrox） ===")
def bin_flat(ver, champ="aatrox"):
    u = f"{CD}/{ver}/game/data/characters/{champ}/{champ}.bin.json"
    r = S.get(u, timeout=90)
    if r.status_code != 200:
        return None
    return r.json()
def flat(o, pre="", out=None):
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            flat(v, f"{pre}/{k}" if pre else k, out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            flat(v, f"{pre}[{i}]", out)
    else:
        out[pre] = o
    return out
b19, b20 = bin_flat("16.19"), bin_flat("16.20")
if b19 and b20:
    f19, f20 = flat(b19), flat(b20)
    keys = set(f19) | set(f20)
    d = [(k, f19.get(k), f20.get(k)) for k in sorted(keys) if f19.get(k) != f20.get(k)]
    print(f"  16.19 叶子={len(f19)} 16.20 叶子={len(f20)} 差异={len(d)}")
    for k, va, vb in d[:10]:
        print(f"    {k}: {str(va)[:60]} -> {str(vb)[:60]}")
else:
    print("  BIN 不可得:", bool(b19), bool(b20))
