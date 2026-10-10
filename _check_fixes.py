"""改动试跑：不必重建整库，先看几个代表英雄的结果。

只读 raw/ 与 src/，不写任何产出。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.parser.spell import parse_ddragon_spells
from src.pipeline import enrich_spell_from_bin

ROOT = Path(__file__).parent
RAW = ROOT / "raw" / "16.20" / "zh_CN"
TOKEN = re.compile(r"\{\{(.*?)\}\}", re.S)
EXPR = re.compile(r"^([A-Za-z0-9_]+)\s*(?:([*/])\s*(-?\d+(?:\.\d+)?))?$")


def levels_of(values, max_rank):
    if not values:
        return []
    return [
        values[r] if r < len(values) else values[-1]
        for r in range(1, max_rank + 1)
    ]


def fill(tooltip, data_values, calcs, max_rank):
    """按 Android `SpellNumbers` 的口径填一遍，返回填出/问号。"""
    values = {k.lower(): v for k, v in data_values.items()}
    lower_calcs = {k.lower(): v for k, v in calcs.items()}
    out = []
    missing = []
    for token in TOKEN.findall(tooltip):
        token = token.strip()
        if not token or "{{" in token:
            continue
        if token.lower() == "spellmodifierdescriptionappend":
            continue
        match = EXPR.match(token)
        if not match:
            missing.append((token, "表达式形态"))
            continue
        name, op = match.group(1), match.group(2)
        raw = values.get(name.lower())
        if raw is not None:
            per = levels_of(raw, max_rank)
            if op:
                per = [v * float(match.group(3)) if op == "*"
                       else v / float(match.group(3)) for v in per]
            parts = [format_level(v) for v in per]
            distinct = list(dict.fromkeys(parts))
            out.append((token, distinct[0] if len(distinct) == 1 else " / ".join(parts)))
            continue
        calc = lower_calcs.get(name.lower())
        if calc is None:
            missing.append((token, "名字不存在"))
        else:
            missing.append((token, "计算式无 parts" if not calc.get("parts")
                            else "计算式不可渲染"))
    return out, missing


def format_level(value):
    rounded = round(value, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


def check(champion_id, slots):
    ddragon = json.load(
        open(RAW / "ddragon" / "champions" / f"{champion_id}.json", encoding="utf-8")
    )["data"][champion_id]
    bin_json = json.load(
        open(
            RAW / "cdragon" / "game" / "data" / "characters" / champion_id.lower()
            / f"{champion_id.lower()}.bin.json",
            encoding="utf-8",
        )
    )
    partype = ddragon.get("partype", "")
    spells = parse_ddragon_spells(ddragon, partype)
    print("=" * 72)
    print(champion_id)
    for spell in spells:
        if spell["slot"] not in slots:
            continue
        enrich_spell_from_bin(spell, bin_json, champion_id, ())
        values = json.loads(spell["dataValuesJson"])
        calcs = json.loads(spell["calculationJson"])
        filled, missing = fill(spell["tooltip"], values, calcs, spell["maxRank"])
        print(f"--- {spell['slot']} {spell['name']}")
        print(f"    cost={spell['cost']!r} costLevels={spell['costLevels']!r} "
              f"resource={spell['resource']!r}")
        for token, text in filled:
            print(f"    [填出] {token:<40} -> {text}")
        for token, why in missing:
            print(f"    [问号] {token:<40} ({why})")


if __name__ == "__main__":
    check("DrMundo", {"Q", "E"})          # 生命消耗 / 回复
    check("Chogath", {"Q", "W"})          # effect 索引占位符
    check("Aatrox", {"Q"})                # GameCalculationModified
    check("Cassiopeia", {"E"})            # {{ cost }}
    check("Azir", {"W"})                  # {{ maxammo }}
