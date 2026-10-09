import json
import re
import requests

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}
CD = "https://raw.communitydragon.org/latest"

lg = requests.get(f"{CD}/game/zh_cn/data/menu/en_us/lol.stringtable.json",
                  headers=BROWSER_UA, timeout=180).json()["entries"]
en = requests.get(f"{CD}/game/en_us/data/menu/en_us/lol.stringtable.json",
                  headers=BROWSER_UA, timeout=180).json()["entries"]


def disp(key):
    if not key:
        return ("", "")
    k = "game_character_displayname_" + key.replace("game_character_displayname_", "")
    return (lg.get(k, ""), en.get(k, ""))


html = requests.get(f"{CD}/game/data/characters/", headers=BROWSER_UA, timeout=60).text
dirs = sorted({m for m in re.findall(r'href="(sru[^"]+/)"', html)})

rows = []
for d in dirs:
    name = d.rstrip("/")
    try:
        js = requests.get(f"{CD}/game/data/characters/{name}/{name}.bin.json",
                          headers=BROWSER_UA, timeout=60).json()
    except Exception as exc:  # noqa: BLE001
        rows.append({"codename": name, "tags": "ERR " + str(exc)[:40]})
        continue
    rk = next((k for k in js if k.endswith("CharacterRecords/Root")), None)
    r = js.get(rk, {}) if rk else {}

    def bv(key):
        v = r.get(key)
        return v.get("baseValue") if isinstance(v, dict) else v

    tags = r.get("unitTagsString", "")
    zh, en_n = disp(r.get("name", ""))
    rows.append({
        "codename": name,
        "mCharacterName": r.get("mCharacterName", ""),
        "zh": zh, "en": en_n,
        "tags": tags,
        "hp": bv("baseHPModifiable"), "hpLvl": bv("hpPerLevelModifiable"),
        "ad": bv("baseDamageModifiable"), "adLvl": bv("damagePerLevelModifiable"),
        "armor": bv("baseArmorModifiable"), "mr": bv("baseMR"),
        "gold": r.get("goldGivenOnDeath"), "ggold": r.get("globalGoldGivenOnDeath"),
        "exp": r.get("expGivenOnDeath"), "gexp": r.get("globalExpGivenOnDeath"),
        "nKeys": len(r),
    })

print(f"{'codename':<26}{'zh':<12}{'hp':>7}{'ad':>6}{'gold':>6}{'exp':>6}  tags")
for r in rows:
    if "tags" in r and isinstance(r.get("tags"), str):
        print(f"{r.get('codename',''):<26}{r.get('zh',''):<12}{str(r.get('hp')):>7}"
              f"{str(r.get('ad')):>6}{str(r.get('gold')):>6}{str(r.get('exp')):>6}  "
              f"{r['tags'][:70]}")
    else:
        print(r)

monsters = [r for r in rows if isinstance(r.get("tags"), str) and "Monster" in r["tags"]]
print(f"\ntotal sru dirs={len(rows)}  Monster-tagged={len(monsters)}")

import pathlib
pathlib.Path("_monster_dump.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote _monster_dump.json")
