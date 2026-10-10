"""One-off probe #3: KIWI mode identity, augment numbers, patch-note sources."""
import json
import re

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 lol-assistant-data/1.0"})
CD = "https://raw.communitydragon.org/latest"
V1 = CD + "/plugins/rcp-be-lol-game-data/global/{loc}/v1"
ST = "raw/16.20/zh_CN/cdragon/game/stringtable/zh_cn.lol.stringtable.json"


def listing(u):
    r = S.get(u, timeout=45)
    return r.status_code, (re.findall(r'href="([^"?/][^"]*)"', r.text) if r.status_code == 200 else [])


def getj(u):
    r = S.get(u, timeout=45)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, None


print("=== A. 海克斯大乱斗的显示名（stringtable 反查） ===")
ent = json.load(open(ST, encoding="utf-8"))["entries"]
for pat in ("海克斯大乱斗", "海克斯"):
    hits = [(k, v) for k, v in ent.items() if pat in str(v)]
    print(f"  含'{pat}'的键: {len(hits)}")
    for k, v in hits[:12]:
        print(f"    {k} = {v!r}"[:150])

print("\n=== B. kiwi-hub.json（模式大厅配置） ===")
c, d = getj(V1.format(loc="default") + "/kiwi-hub.json")
print("  status", c, type(d).__name__)
if isinstance(d, dict):
    for k, v in d.items():
        print(f"    {k}: {json.dumps(v, ensure_ascii=False)[:220]}")
elif isinstance(d, list):
    print("  n=", len(d), json.dumps(d[:2], ensure_ascii=False)[:400])

print("\n=== C. 增幅数值载体：game/data/spells 与 maps/shipping ===")
for u in (CD + "/game/data/spells/", CD + "/game/data/maps/shipping/"):
    c, n = listing(u)
    kw = [x for x in n if re.search(r"aug|kiwi|aram|map1|cherry|spell", x, re.I)]
    print(f"  {u} -> {c} total={len(n)} kw={kw[:16]}")
for p in ("game/data/maps/shipping/map12/map12.bin.json",
          "game/data/maps/shipping/map11/map11.bin.json",
          "game/data/maps/shipping/common/common.bin.json"):
    r = S.get(f"{CD}/{p}", timeout=60)
    hit = 0
    if r.status_code == 200:
        t = r.text
        hit = t.lower().count("augment")
    print(f"  {p} -> {r.status_code} {len(r.content)}b 'augment'x{hit}")

print("\n=== D. augment 的 name -> stringtable 键映射验证 ===")
aug = getj(V1.format(loc="zh_cn") + "/cherry-augments.json")[1]
aram = [a for a in aug if str(a["augmentNameId"]).startswith("ARAM_")]
print(f"  ARAM_* 符文 {len(aram)} 条；尝试 id->stringtable 键")
hit = miss = 0
samples = []
for a in aram:
    key = "kiwi_aram_" + a["augmentNameId"][5:].lower() + "_name"
    if key in ent:
        hit += 1
        if len(samples) < 5:
            samples.append((a["augmentNameId"], key, ent[key], a["nameTRA"]))
    else:
        miss += 1
print(f"  命中 {hit} / 未命中 {miss}")
for s in samples:
    print("   ", s)

print("\n=== E. 官方 / 社区可读源可达性 ===")
urls = {
    "riot_patch_notes_en": "https://www.leagueoflegends.com/en-us/news/game-updates/patch-16-20-notes/",
    "riot_patch_list_en": "https://www.leagueoflegends.com/en-us/news/tags/patch-notes/",
    "cn_lol_news": "https://lol.qq.com/news/detail.shtml?docid=14645770214471584183",
    "wiki_api_revisions": "https://wiki.leagueoflegends.com/en-us/api.php?action=query&prop=revisions&rvprop=content&rvslots=main&format=json&titles=Module%3ASpellData%2Fdata",
    "wiki_patch_history": "https://wiki.leagueoflegends.com/en-us/Aatrox/Patch_history",
    "fandom_mirror": "https://leagueoflegends.fandom.com/wiki/Module:ChampionData/data?action=raw",
    "meraki_champions": "https://cdn.merakianalytics.com/riot/lol/resources/latest/en-US/champions.json",
}
for k, u in urls.items():
    try:
        r = S.get(u, timeout=45)
        print(f"  {k}: {r.status_code} {len(r.content)}b  first={r.text[:70]!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {k}: ERR {type(exc).__name__} {exc}")
