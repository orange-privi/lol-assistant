"""诊断：技能正文里的占位符，最终变成了什么。

纯只读，复刻 Android `SpellNumbers` 的**当前**口径（数值 / 公式 / 问号三分）：

  * 数值 —— 命名数值表里直接命中；
  * 公式 —— 命中计算式且写得出来（含改写式的引用链与倍率）；
  * 问号 —— 名字两边都没有，或式子依赖运行时上下文（英雄等级 / buff 层数 / 效果值）。

用于对比改动前后的覆盖，并抽查具体技能的产出文本。
这类 `_diag_*` 脚本只读、不进管线，可以随时删。
"""

from __future__ import annotations

import collections
import json
import re
import sqlite3

TOKEN = re.compile(r"\{\{(.*?)\}\}", re.S)
EXPR = re.compile(r"^([A-Za-z0-9_]+)\s*(?:([*/])\s*(-?\d+(?:\.\d+)?))?$")

MODIFIER_APPEND = "spellmodifierdescriptionappend"

STAT_LABEL = {
    "ATTACK_DAMAGE": "攻击力",
    "BONUS_ATTACK_DAMAGE": "额外攻击力",
    "ABILITY_POWER": "法术强度",
    "MAX_HEALTH": "最大生命值",
    "BONUS_HEALTH": "额外生命值",
    "HEALTH": "生命值",
    "ARMOR": "护甲",
    "MAGIC_RESIST": "魔抗",
    "MOVE_SPEED": "移动速度",
    "MANA": "法力值",
    "BONUS_MANA": "额外法力值",
    "ATTACK_SPEED": "攻击速度",
    "CRITICAL_STRIKE": "暴击率",
    "CRITICAL_STRIKE_DAMAGE": "暴击伤害",
    "ABILITY_HASTE": "技能急速",
}

RUNTIME, STATIC, UNKNOWN = "runtime", "static", "unknown"


# ---------------------------------------------------------------------------
# 渲染（镜像 Kotlin，纯文本）
# ---------------------------------------------------------------------------

def fmt(value: float) -> str:
    rounded = round(value, 2)
    return str(int(rounded)) if rounded == int(rounded) else str(rounded)


def _ranks(raw, max_rank: int, scale: float = 1.0) -> list[str] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[str] = []
    for rank in range(1, max_rank + 1):
        item = raw[rank] if rank < len(raw) else raw[-1]
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        out.append(fmt(float(item) * scale))
    return out


def _collapse(parts: list[str]) -> str:
    distinct = list(dict.fromkeys(parts))
    return distinct[0] if len(distinct) == 1 else " / ".join(parts)


def with_stat(text: str, stat: str) -> str:
    label = STAT_LABEL.get(stat)
    return f"{text}% {label}" if label else f"{text}%"


def classify(node) -> str:
    """复刻 Kotlin `classifyMultiplier`（作用于归一化后的 part 树）。"""
    if not isinstance(node, dict):
        return UNKNOWN
    kind = node.get("type")
    if kind in ("dataValue", "number"):
        return STATIC
    if kind in ("statDataValue", "statCoefficient"):
        return RUNTIME
    if kind in ("sum", "product"):
        parts = node.get("parts") or []
        if not parts:
            return UNKNOWN
        static_seen = False
        for part in parts:
            sub = classify(part)
            if sub == RUNTIME:
                return RUNTIME
            if sub == UNKNOWN:
                return UNKNOWN
            static_seen = True
        return STATIC if static_seen else UNKNOWN
    if kind == "unknown":
        return RUNTIME if node.get("class") == "StatBySubPartCalculationPart" else UNKNOWN
    return UNKNOWN


def render_part(part, values: dict, max_rank: int) -> str | None:
    """一个归一化 part -> 文本；写不出返回 None。"""
    kind = part.get("type")

    if kind == "dataValue":
        ranks = _ranks(values.get(str(part.get("name", "")).lower()), max_rank)
        return None if ranks is None else _collapse(ranks)

    if kind == "statDataValue":
        ranks = _ranks(values.get(str(part.get("name", "")).lower()), max_rank, 100.0)
        return None if ranks is None else with_stat(_collapse(ranks), part.get("stat") or "")

    if kind == "statCoefficient":
        coefficient = part.get("coefficient")
        if not isinstance(coefficient, (int, float)) or isinstance(coefficient, bool):
            return None
        return with_stat(fmt(float(coefficient) * 100), part.get("stat") or "")

    if kind == "number":
        value = part.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return fmt(float(value))

    if kind in ("sum", "product"):
        parts = part.get("parts") or []
        if not parts:
            return None
        texts: list[str] = []
        for sub in parts:
            text = render_part(sub, values, max_rank)
            if text is None:
                return None
            texts.append(text)
        if kind == "sum":
            return " + ".join(texts)
        # 乘法：多值项与复合项要加括号，否则 `/` 会被读成除号
        wrapped = [
            text if sub.get("type") in ("number", "statCoefficient") else f"({text})"
            for sub, text in zip(parts, texts)
        ]
        return " × ".join(wrapped)

    if kind == "unknown" and part.get("class") == "StatBySubPartCalculationPart":
        sub = (part.get("data") or {}).get("mSubpart") or {}
        if sub.get("__type") != "NamedDataValueCalculationPart":
            return None
        ranks = _ranks(values.get(str(sub.get("mDataValue", "")).lower()), max_rank, 100.0)
        return None if ranks is None else with_stat(_collapse(ranks), "")

    return None


def build_formula(name: str, calcs: dict, values: dict, max_rank: int, seen: frozenset[str]):
    """复刻 Kotlin `Calculations.get`：沿改写式引用链展开，再套倍率。"""
    key = name.lower()
    if key in seen:
        return None
    node = calcs.get(key)
    if not isinstance(node, dict):
        return None

    reference = node.get("mModifiedGameCalculation")
    if isinstance(reference, str) and reference:
        base = build_formula(reference, calcs, values, max_rank, seen | {key})
        return None if base is None else apply_multiplier(node, base, values, max_rank)

    if node.get("mCoefficient") is not None or node.get("mDataValue") is not None:
        return None
    parts = node.get("parts") or []
    if not parts:
        return None
    terms: list[str] = []
    for part in parts:
        text = render_part(part, values, max_rank)
        if text is None:
            return None
        terms.append(text)
    return apply_multiplier(node, " + ".join(terms), values, max_rank)


def apply_multiplier(node, base: str, values: dict, max_rank: int) -> str | None:
    multiplier = node.get("multiplier")
    if not isinstance(multiplier, dict):
        return base
    kind = classify(multiplier)
    if kind == RUNTIME:
        return base
    if kind != STATIC:
        return None
    factor = render_part(multiplier, values, max_rank)
    return None if factor is None else f"({base}) × ({factor})"


# ---------------------------------------------------------------------------
# 问号的成因（剩下那 5% 要能说清卡在哪）
# ---------------------------------------------------------------------------

def block_reason(name: str, calcs: dict) -> str:
    node = calcs.get(name)
    if node is None:
        if re.fullmatch(r"[ef]\d+", name):
            return "effect 索引未注入"
        return "计算式不在本技能表"
    return _first_block(node, calcs)


def _first_block(node, calcs: dict) -> str:
    reference = node.get("mModifiedGameCalculation")
    if isinstance(reference, str) and reference:
        base = calcs.get(reference.lower())
        if base is None:
            return "引用的计算式不在本技能表"
        return _first_block(base, calcs)

    if node.get("mCoefficient") is not None or node.get("mDataValue") is not None:
        return "计算式带 mCoefficient/mDataValue"

    parts = node.get("parts") or []
    if not parts:
        return "没有 parts"

    for part in parts:
        reason = _part_block(part)
        if reason:
            return reason

    multiplier = node.get("multiplier")
    if isinstance(multiplier, dict) and classify(multiplier) == UNKNOWN:
        return "倍率结构认不出"
    return "其它"


def _part_block(part) -> str:
    kind = part.get("type")
    if kind in ("dataValue", "statDataValue", "number", "statCoefficient"):
        return None
    if kind in ("sum", "product"):
        for sub in part.get("parts") or []:
            reason = _part_block(sub)
            if reason:
                return reason
        return None
    if kind == "unknown":
        return f"运行时项({part.get('class')})"
    return f"未知项({kind})"


def main() -> None:
    conn = sqlite3.connect("output/lol-16.20.db")
    conn.row_factory = sqlite3.Row

    counts: collections.Counter[str] = collections.Counter()
    reasons: collections.Counter[str] = collections.Counter()
    samples: dict[str, list[str]] = collections.defaultdict(list)

    for row in conn.execute(
        "select championId, slot, name, tooltip, dataValuesJson, calculationJson, maxRank"
        " from champion_spell where tooltip like '%{{%'"
    ):
        values = {
            str(k).lower(): v
            for k, v in json.loads(row["dataValuesJson"] or "{}").items()
        }
        calcs = {
            str(k).lower(): v
            for k, v in json.loads(row["calculationJson"] or "{}").items()
        }
        max_rank = max(1, int(row["maxRank"] or 1))
        champion = row["championId"]

        for raw in TOKEN.findall(row["tooltip"]):
            token = raw.strip()
            if not token or "{{" in token:
                continue
            if token.lower() == MODIFIER_APPEND:
                counts["按设计不留问号"] += 1
                continue
            match = EXPR.match(token)
            if not match:
                counts["上下文表达式（spell.x:y）"] += 1
                continue
            name = match.group(1).lower()

            if name in values:
                counts["数值"] += 1
                continue

            formula = build_formula(name, calcs, values, max_rank, frozenset())
            if formula is None:
                counts["问号"] += 1
                reasons[block_reason(name, calcs)] += 1
                if len(samples["问号"]) < 12:
                    samples["问号"].append(f"{champion}/{row['slot']} {name}")
                continue

            counts["公式"] += 1
            if len(samples["公式"]) < 14:
                samples["公式"].append(f"{champion}/{row['slot']} {name} = {formula}")

    total = counts["数值"] + counts["公式"] + counts["问号"]
    print(f"可填的占位符（不含按设计跳过与上下文表达式）: {total}")
    print(f"  数值: {counts['数值']} ({counts['数值'] / max(total, 1):.1%})")
    print(f"  公式: {counts['公式']} ({counts['公式'] / max(total, 1):.1%})")
    print(f"  问号: {counts['问号']} ({counts['问号'] / max(total, 1):.1%})")
    print()
    print("其它计数:", {k: v for k, v in counts.items()
                        if k not in ("数值", "公式", "问号")})
    print()
    print("问号成因:")
    for key, count in reasons.most_common():
        print(f"  {count:>4}  {key}")
    print()
    for key in ("公式", "问号"):
        print(f"{key} 样例:")
        for item in samples[key]:
            print("   ", item)
        print()


if __name__ == "__main__":
    main()
