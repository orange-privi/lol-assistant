"""勘察：三类占位符缺口的真实规模与数据形态。

只读。分别统计：
  A. 「表达式形态解析不了」细分（`spell.xxx:yyy` 跨技能引用 / `f2.0` 这类 / 其他）
  B. BIN 里 GameCalculationModified 的结构（引用谁、multiplier 是什么）
  C. ddragon 技能级字段（maxammo / ammoRechargeTime / cost）与 `{{ cost }}` 占位符
"""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "output" / "lol-16.20.db"
RAW = ROOT / "raw" / "16.20" / "zh_CN"

TOKEN = re.compile(r"\{\{(.*?)\}\}", re.S)
EXPR = re.compile(r"^([A-Za-z0-9_]+)\s*(?:([*/])\s*(-?\d+(?:\.\d+)?))?$")


def part_a() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    buckets: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    for row in conn.execute(
        "select championId, slot, name, tooltip, dataValuesJson, calculationJson "
        "from champion_spell where tooltip like '%{{%'"
    ):
        values = {k.lower() for k in json.loads(row["dataValuesJson"] or "{}")}
        calcs = {k.lower() for k in json.loads(row["calculationJson"] or "{}")}
        for raw in TOKEN.findall(row["tooltip"]):
            token = raw.strip()
            if not token or "{{" in token:
                continue
            if EXPR.match(token):
                continue
            if token.lower().startswith("spell.") and ":" in token:
                key = "A1 spell.xxx:yyy（跨技能引用）"
            elif re.match(r"^[A-Za-z0-9_]+\s*[*/]\s*-?\d+\.\d+$", token):
                key = "A2 名字*小数（表达式）"
            elif re.match(r"^[A-Za-z0-9_]+\.\d+$", token):
                key = "A3 名字.数字（f2.0 这类）"
            else:
                key = "A4 其他"
            buckets[key] += 1
            if len(samples[key]) < 8:
                samples[key].append(f"{row['name']}({row['slot']}) {token}")
    print("=== A. 「表达式形态解析不了」细分 ===")
    for k, c in buckets.most_common():
        print(f"  {c:>5}  {k}")
    for k, v in samples.items():
        if buckets.get(k):
            print(f"    「{k}」样例: " + "; ".join(v[:4]))


def walk_calcs(node, out):
    def walk(value):
        if isinstance(value, dict):
            sc = value.get("mSpellCalculations")
            if isinstance(sc, dict):
                for name, calc in sc.items():
                    if isinstance(calc, dict):
                        out[name] = calc
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)


def classify_mult(node) -> str:
    seen = set()

    def walk(value):
        if isinstance(value, dict):
            t = value.get("__type")
            if t in ("StatByNamedDataValueCalculationPart",
                     "StatByCoefficientCalculationPart"):
                seen.add("runtime")
            elif t in ("NumberCalculationPart", "NamedDataValueCalculationPart",
                       "DataValueCalculationPart", "SumOfSubPartsCalculationPart",
                       "ProductOfSubPartsCalculationPart"):
                seen.add("static")
            else:
                seen.add(f"other:{t}")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    if node is None:
        return "none"
    walk(node)
    if len(seen) == 1:
        return next(iter(seen))
    return "+".join(sorted(seen))


def part_b() -> None:
    files = sorted(glob.glob(str(RAW / "cdragon/game/data/characters/*/*.bin.json")))
    print(f"\n=== B. BIN 计算式结构（扫描 {len(files)} 个英雄文件）===")
    type_counter: Counter[str] = Counter()
    modified_shapes: Counter[str] = Counter()
    modified_samples: list[str] = []
    has_modified_ref = 0
    total = 0
    # 全库计算式的 __type 分布 + mFormulaParts 情况
    formula_part_types: Counter[str] = Counter()
    for path in files:
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        calcs: dict = {}
        walk_calcs(data, calcs)
        for name, calc in calcs.items():
            total += 1
            t = calc.get("__type", "?")
            type_counter[t] += 1
            for p in calc.get("mFormulaParts") or []:
                if isinstance(p, dict):
                    formula_part_types[p.get("__type", "?")] += 1
            if t == "GameCalculationModified":
                has_modified_ref += 1
                ref = calc.get("mModifiedGameCalculation")
                mult = classify_mult(calc.get("mMultiplier"))
                parts = calc.get("mFormulaParts")
                shape = (f"ref={'有' if ref else '无'}"
                         f" parts={len(parts) if parts else 0}"
                         f" mult={mult}")
                modified_shapes[shape] += 1
                if len(modified_samples) < 10:
                    modified_samples.append(f"{os.path.basename(path)} {name} -> {ref}")
    print(f"  计算式总数: {total}")
    print("  __type 分布:")
    for k, c in type_counter.most_common():
        print(f"    {c:>5}  {k}")
    print(f"  GameCalculationModified: {has_modified_ref}")
    print("  modified 结构分布:")
    for k, c in modified_shapes.most_common():
        print(f"    {c:>5}  {k}")
    print("  modified 样例:")
    for s in modified_samples:
        print("    ", s)
    print("  mFormulaParts 里出现的 part 类型:")
    for k, c in formula_part_types.most_common(20):
        print(f"    {c:>5}  {k}")


def part_c() -> None:
    print("\n=== C. ddragon 技能级字段 ===")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # 谁在 tooltip 里用了 {{ cost }} / {{ maxammo }} / {{ ammorechargetime }}
    for token in ("cost", "maxammo", "ammorechargetime"):
        rows = conn.execute(
            "select championId, slot, name, tooltip from champion_spell "
            "where tooltip like ?", (f"%{{{{ {token} }}}}%",)
        ).fetchall()
        for r in rows:
            print(f"  {token}: {r['championId']} {r['slot']} {r['name']}")
            for t in TOKEN.findall(r["tooltip"]):
                if t.strip().lower() == token:
                    print(f"      上下文: ...{r['tooltip'][max(0, r['tooltip'].find('{{'+t+'}}')-40):r['tooltip'].find('{{'+t+'}}')+60]}...")
    # ddragon 原始字段
    print("  ddragon 原始字段样例:")
    for cid in ("KogMaw", "Cassiopeia", "Twitch"):
        p = RAW / "ddragon" / "champions" / f"{cid}.json"
        if not p.exists():
            continue
        d = json.load(open(p, encoding="utf-8"))["data"][cid]
        for sp in d["spells"]:
            if any(f"{{{{ {t} }}}}" in sp.get("tooltip", "")
                   for t in ("cost", "maxammo", "ammorechargetime")):
                print(f"    {cid} {sp['name']}: "
                      f"maxammo={sp.get('maxammo')} "
                      f"cost={sp.get('cost')} costBurn={sp.get('costBurn')} "
                      f"costType={sp.get('costType')} resource={sp.get('resource')!r}")
                print(f"      tooltip={sp['tooltip'][:200]}")


if __name__ == "__main__":
    part_a()
    part_c()
    part_b()
