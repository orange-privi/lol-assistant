from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .util import json_number

# ---------------------------------------------------------------------------
# 「客户端能不能把这条计算式渲染成数值」的判定口径
#
# calcutionJson 的唯一消费方是 Android 侧的 `SpellNumbers.kt`：它按 `parts` 求和、
# 再决定要不要乘 `mMultiplier`。这里的判定**必须与它一致** —— 一旦不一致，上游会
# 以为「填得出」而实际客户端仍然显示 `?`，这种错是静默的。
#
# 客户端的两条硬规则（理由见 `SpellNumbers.kt` 的文件头）：
#   * `mCoefficient` / `mDataValue` 的语义没有权威依据 -> 整体放弃；
#   * `mMultiplier` 只在「引用了运行时属性」时才敢按 1 忽略（纯静态的必须乘进去，
#     直接丢掉会低报，所以也放弃）。
# ---------------------------------------------------------------------------
RUNTIME = "runtime"
STATIC = "static"
UNKNOWN = "unknown"

# Kotlin `readPart` 在 "unknown" 分支里唯一认得的客户端内部类
CLIENT_KNOWN_UNKNOWN_CLASS = "StatBySubPartCalculationPart"

# 客户端把一部分内部名字做了哈希（`{c8e45bc3}`）。它们**不可能**出现在官方文案里
# （占位符的名字必须是 `[A-Za-z0-9_]`），所以求值结果不必为它们取名落库。
HASHED_NAME = re.compile(r"^\{[0-9a-f]+\}$")


DAMAGE_TYPE_NAMES = {
    0: "physical",
    1: "magic",
    2: "true",
}


STAT_NAMES = {
    0: "ATTACK_DAMAGE",
    1: "ABILITY_POWER",
    2: "BONUS_ATTACK_DAMAGE",
    3: "ATTACK_SPEED",
    4: "CRITICAL_STRIKE",
    5: "CRITICAL_STRIKE_DAMAGE",
    6: "ARMOR",
    7: "MAGIC_RESIST",
    8: "HEALTH",
    9: "BONUS_HEALTH",
    10: "MANA",
    11: "BONUS_MANA",
    12: "MOVE_SPEED",
    13: "ABILITY_HASTE",
}


def normalize_stat(stat: Any) -> str:
    """`mStat` -> 属性枚举名。

    字段缺失时返回空串 —— cdragon 的 BIN 导出**会省略它**（实测全库 783 处），
    这是常态而非异常，调用方再用 `infer_stat_from_name` 从名字上找补。
    """
    if stat is None:
        return ""
    if isinstance(stat, str):
        return stat
    return STAT_NAMES.get(stat, str(stat))


# ---------------------------------------------------------------------------
# `mStat` 缺失时的属性推断
#
# 这个字段决定「这个系数乘的是哪个属性」，而 cdragon 的导出恰好会省略它。
# 名字是唯一线索：实测 mStat 缺失的 130 个命名数值里，绝大多数就叫 `APRatio`
# （166 处）或它的变体（`ShieldAPRatio` / `DamageAPRatio` / `HealAPRatio` / `APPercent` …），
# 也就是说这一档几乎全是法术强度加成。
#
# 判据要求「关键词 + 加成后缀」**同时出现**：光看关键词不够 —— 裸的 `ap` 会在
# `Shape` / `Apex` 这类词里误命中。读不出属性的（`DamageRatio` / `OnHitRatio`）
# 返回空串，公式里少一个属性名，总好过写错一个。
# ---------------------------------------------------------------------------
BONUS_SUFFIX_HINTS = ("ratio", "percent", "coefficient", "mod", "per")


def infer_stat_from_name(name: Any) -> str:
    low = str(name).lower()
    if not any(hint in low for hint in BONUS_SUFFIX_HINTS):
        return ""
    if "ap" in low:
        return "ABILITY_POWER"
    return ""


def normalize_part(part: dict[str, Any]) -> dict[str, Any]:
    typ = part.get("__type", "")

    if typ == "NamedDataValueCalculationPart":
        return {
            "type": "dataValue",
            "name": part.get("mDataValue", ""),
        }

    if typ == "StatByNamedDataValueCalculationPart":
        name = part.get("mDataValue", "")
        return {
            "type": "statDataValue",
            "name": name,
            "stat": normalize_stat(part.get("mStat")) or infer_stat_from_name(name),
            "statFormula": part.get("mStatFormula"),
        }

    # `StatBySubPartCalculationPart` 与上面语义完全相同（命名数值 × 属性），只是子项多包了
    # 一层。归一化成同一种写法，客户端就只需要认一套（`mStat` 同样会缺失）。
    if typ == "StatBySubPartCalculationPart":
        sub = part.get("mSubpart") or {}
        if isinstance(sub, dict) and sub.get("__type") == "NamedDataValueCalculationPart":
            name = sub.get("mDataValue", "")
            return {
                "type": "statDataValue",
                "name": name,
                "stat": normalize_stat(part.get("mStat")) or infer_stat_from_name(name),
                "statFormula": part.get("mStatFormula"),
            }

    if typ == "StatByCoefficientCalculationPart":
        return {
            "type": "statCoefficient",
            "stat": normalize_stat(part.get("mStat")),
            "coefficient": part.get("mCoefficient"),
            "statFormula": part.get("mStatFormula"),
        }

    if typ == "NumberCalculationPart":
        return {
            "type": "number",
            "value": part.get("mNumber"),
        }

    # 和 / 积：子项逐个归一化，结构原样保留 —— 客户端要靠它把整条式子渲染成
    # `a + b` / `a × b`。两种写法（`mSubparts` 数组、`mPart1`&`mPart2` 成对）同样都认。
    if typ in ("SumOfSubPartsCalculationPart", "ProductOfSubPartsCalculationPart"):
        normalized = [
            normalize_part(sub)
            for sub in _sub_parts(part)
            if isinstance(sub, dict)
        ]
        if normalized:
            return {
                "type": "sum" if typ.startswith("Sum") else "product",
                "parts": normalized,
            }

    if typ == "ByCharLevelBreakpointsCalculationPart":
        return {
            "type": "characterLevelBreakpoints",
            "data": part,
        }

    # Unknown calculation parts are deliberately retained instead of dropped.
    return {
        "type": "unknown",
        "class": typ,
        "data": part,
    }


def normalize_calculation(calculation: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    # 保留客户端内部类名。没有它，下游分不出「改写式」（GameCalculationModified：
    # 真正的公式在 `mModifiedGameCalculation` 指向的另一条计算式上，本体没有
    # `mFormulaParts`）与「确实没有公式」这两种 `parts: []`。
    if calculation.get("__type"):
        result["class"] = calculation["__type"]

    if "DamageType" in calculation:
        result["damageType"] = calculation["DamageType"]

    parts = calculation.get("mFormulaParts") or []
    result["parts"] = [
        normalize_part(part)
        for part in parts
        if isinstance(part, dict)
    ]

    # Preserve other scalar calculation metadata.
    for key in (
        "mMultiplier",
        "mCoefficient",
        "mDataValue",
        "mModifiedGameCalculation",
    ):
        if key in calculation:
            result[key] = calculation[key]

    # `mMultiplier` 的**归一化副本**：客户端要把它渲染成 `(式子) × (倍率)`，
    # 而原始结构（`__type` / `mSubparts`）它认不了。原字段保留 —— 求值与判定还在用它。
    multiplier = calculation.get("mMultiplier")
    if isinstance(multiplier, dict):
        result["multiplier"] = normalize_part(multiplier)

    return result


def collect_raw_calculations(
    spell_objects: Any,
) -> dict[str, dict[str, Any]]:
    """原始（未归一化）的 ``mSpellCalculations``，按名字索引。

    归一化只保留客户端渲染要用的那几列，改写式需要的内部结构（子项数组、
    `mModifiedGameCalculation` 引用）会被压成 ``unknown``；静态求值必须回到
    原始对象上做，所以单独留一个收集函数。
    """
    return _walk_calculations(spell_objects)


def _walk_calculations(spell_objects: Any) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            calculations = value.get("mSpellCalculations")
            if isinstance(calculations, dict):
                for name, calc in calculations.items():
                    if isinstance(calc, dict):
                        found[name] = calc

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    if isinstance(spell_objects, (list, tuple)):
        for obj in spell_objects:
            walk(obj)
    else:
        walk(spell_objects)
    return found


def extract_calculations(spell_object: dict[str, Any]) -> dict[str, Any]:
    """
    Extract mSpellCalculations from the CommunityDragon champion BIN JSON.

    The BIN JSON is a large object whose values can contain mSpellCalculations.
    We recursively walk it because the exact nesting can vary between champions.
    """
    return {
        name: normalize_calculation(calc)
        for name, calc in _walk_calculations(spell_object).items()
    }


def extract_data_values(spell_object: dict[str, Any]) -> dict[str, list[Any]]:
    """
    Extract every SpellDataValue from DataValues arrays.
    """
    result: dict[str, list[Any]] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            data_values = value.get("DataValues")
            if isinstance(data_values, list):
                for item in data_values:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    values = item.get("values")
                    if name and isinstance(values, list):
                        result[name] = values

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(spell_object)
    return result


def extract_effects(spell_object: dict[str, Any]) -> dict[str, Any]:
    """
    Keep a conservative normalized copy of effect arrays.

    Different champions have different effect layouts. We intentionally retain
    the original effect object instead of guessing semantic names.
    """
    effects: dict[str, Any] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            effect = value.get("mEffectAmount")
            if isinstance(effect, list):
                effects.setdefault("effectAmounts", []).append(effect)

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(spell_object)
    return effects


def normalize_damage_type(value: Any) -> str:
    if isinstance(value, str):
        return value.removeprefix("k").lower()
    return DAMAGE_TYPE_NAMES.get(value, "")


def spell_damage_type(calculations: dict[str, Any]) -> str:
    """Pick the most common damage type across a spell's calculations."""
    counter: Counter[str] = Counter()
    for calc in calculations.values():
        if isinstance(calc, dict) and "damageType" in calc:
            name = normalize_damage_type(calc["damageType"])
            if name:
                counter[name] += 1
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


# ---------------------------------------------------------------------------
# 静态求值：把客户端渲染不出来的计算式先算成逐级数值
#
# 客户端只能渲染 `parts` 里那几种 part，改写式（GameCalculationModified）与带静态
# `mMultiplier` 的式子它一律显示 `?`（理由见文件头注释）。但这些式子里很大一部分
# 只用到**命名数值与常量**，并不依赖运行时属性 —— 也就是说，在离线状态下完全算得出。
#
# 这里的做法：把这类式子按客户端同一套口径求值成逐级数组，作为**同名命名数值**
# 并进 `dataValuesJson`。客户端填占位符时先查命名数值表（`SpellNumbers.resolve`
# 里 `values[name]` 在 `calcs[name]` 之前），于是不改客户端就能取到值。
#
# 只处理「客户端跑不动、这里跑得动」的那部分 —— 客户端自己就能渲染的式子不碰，
# 免得两条路径对同一段文案给出不同写法。
# ---------------------------------------------------------------------------


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _rank_levels(raw: Any, max_rank: int) -> list[float] | None:
    """按客户端口径取逐级值：``rank r -> raw[r]``（``raw[0]`` 是填充位）。

    越界取末项 —— 与 Android `SpellNumbers.levelsOf` 完全一致。
    """
    if not isinstance(raw, list) or not raw:
        return None
    levels: list[float] = []
    for rank in range(1, max_rank + 1):
        item = raw[rank] if rank < len(raw) else raw[-1]
        number = _as_number(item)
        if number is None:
            return None
        levels.append(number)
    return levels


def _sub_parts(node: dict[str, Any]) -> list[Any]:
    """`Sum/ProductOfSubParts` 的子项。

    客户端内部有**两套写法**，实测都得认：

    * `mSubparts` —— 数组，乘数（`mMultiplier`）里用的是这种；
    * `mPart1` / `mPart2` —— 两两成对，`mFormulaParts` 里用的是这种
      （蒙多 Q 的 `HealthRestoreOnHitChampionMonster = 回复比例 × HealthCost`
      就是 `mPart1` × `mPart2`）。
    """
    subparts = node.get("mSubparts")
    if isinstance(subparts, list):
        return subparts
    return [
        part
        for part in (node.get("mPart1"), node.get("mPart2"))
        if isinstance(part, dict)
    ]


def _eval_node(
    node: Any,
    values: dict[str, Any],
    max_rank: int,
    depth: int = 0,
) -> list[float] | None:
    """一个计算节点 -> 逐级数值数组；算不出来返回 None。"""
    if depth > 8 or not isinstance(node, dict):
        return None

    kind = node.get("__type", "")

    if kind == "NumberCalculationPart":
        number = _as_number(node.get("mNumber"))
        return None if number is None else [number] * max_rank

    if kind in ("NamedDataValueCalculationPart", "DataValueCalculationPart"):
        name = str(node.get("mDataValue", "")).lower()
        return _rank_levels(values.get(name), max_rank)

    if kind in ("SumOfSubPartsCalculationPart", "ProductOfSubPartsCalculationPart"):
        subparts = _sub_parts(node)
        if not subparts:
            return None
        total: list[float] | None = None
        for sub in subparts:
            levels = _eval_node(sub, values, max_rank, depth + 1)
            if levels is None:
                return None
            if total is None:
                total = levels
            elif kind == "SumOfSubPartsCalculationPart":
                total = [a + b for a, b in zip(total, levels)]
            else:
                total = [a * b for a, b in zip(total, levels)]
        return total

    # StatBy*（吃运行时属性）、ByCharLevel*（吃英雄等级）、BuffCounter*、
    # EffectValue*、AbilityResource* —— 都要运行时上下文，离线算不出，不猜。
    return None


def classify_multiplier(node: Any) -> str:
    """``mMultiplier`` 里引用了什么（与 Android `classifyMultiplier` 同口径）。"""
    seen: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            kind = value.get("__type", "")
            if kind in (
                "StatByNamedDataValueCalculationPart",
                "StatByCoefficientCalculationPart",
            ):
                seen.add(RUNTIME)
            elif kind in (
                "NumberCalculationPart",
                "NamedDataValueCalculationPart",
                "DataValueCalculationPart",
                "SumOfSubPartsCalculationPart",
                "ProductOfSubPartsCalculationPart",
            ):
                seen.add(STATIC)
            else:
                seen.add(UNKNOWN)
            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    if UNKNOWN in seen:
        return UNKNOWN
    if RUNTIME in seen:
        return RUNTIME
    return STATIC


def _apply_multiplier(
    levels: list[float],
    node: Any,
    values: dict[str, Any],
    max_rank: int,
    depth: int,
) -> list[float] | None:
    if node is None:
        return levels
    kind = classify_multiplier(node)
    if kind == UNKNOWN:
        return None
    if kind == RUNTIME:
        # 面板显示的本来就是不含这些运行时属性的基础值 —— 与客户端同样按 1 处理
        return levels
    factor = _eval_node(node, values, max_rank, depth + 1)
    if factor is None:
        return None
    return [a * b for a, b in zip(levels, factor)]


def _eval_calculation(
    name: str,
    raw: dict[str, dict[str, Any]],
    values: dict[str, Any],
    max_rank: int,
    seen: frozenset[str],
    depth: int = 0,
) -> list[float] | None:
    if depth > 6 or name in seen:
        return None
    calc = raw.get(name)
    if not isinstance(calc, dict):
        return None
    seen = seen | {name}

    if calc.get("__type") == "GameCalculationModified":
        # 改写式：`mModifiedGameCalculation` 指向基础式，`mMultiplier` 乘在它上面
        reference = str(calc.get("mModifiedGameCalculation", ""))
        base = _eval_calculation(
            reference, raw, values, max_rank, seen, depth + 1
        )
    else:
        # `mCoefficient` / `mDataValue` 的语义没有权威依据 —— 与客户端一样放弃
        if calc.get("mCoefficient") is not None or calc.get("mDataValue") is not None:
            return None
        base = None
        for part in calc.get("mFormulaParts") or []:
            levels = _eval_node(part, values, max_rank, depth)
            if levels is None:
                return None
            base = levels if base is None else [a + b for a, b in zip(base, levels)]

    if base is None:
        return None
    return _apply_multiplier(base, calc.get("mMultiplier"), values, max_rank, depth)


def _numeric_part(part: dict[str, Any], values: dict[str, Any]) -> bool:
    """客户端能不能把这一项折成**一个确定数值**。

    比客户端的渲染能力**更严**：`sum` / `product` 这类多项结构，客户端渲染出来的是
    `30 + 50` 这样的算式（其中可能混着属性项），而不是 `80`。所以这里一律返回 False，
    好让 `evaluate_calculations` 有机会先算出确切数值写进别名表 —— 否则同一段文案
    会同时存在「算式」和「数值」两种写法。
    """
    kind = part.get("type")
    if kind == "dataValue":
        return str(part.get("name", "")).lower() in values
    if kind == "statDataValue":
        # 属性名可以缺（`mStat` 缺失、名字也读不出），系数必须在 —— 少了它这一项没有意义。
        return str(part.get("name", "")).lower() in values
    if kind == "statCoefficient":
        return part.get("coefficient") is not None
    if kind == "number":
        return part.get("value") is not None
    if kind == "unknown":
        if part.get("class") != CLIENT_KNOWN_UNKNOWN_CLASS:
            return False
        sub = (part.get("data") or {}).get("mSubpart") or {}
        return (
            sub.get("__type") == "NamedDataValueCalculationPart"
            and str(sub.get("mDataValue", "")).lower() in values
        )
    return False


def renderable_by_client(
    calculation: dict[str, Any],
    values: dict[str, Any],
) -> bool:
    """客户端 `SpellNumbers` 能不能自己给出**确定数值**（而不是算式）。

    只用于给 `evaluate_calculations` 剪枝：返回 True 的式子客户端已经能显示确切数字，
    不必再写一份别名。含属性项（`statDataValue` / `statCoefficient`）的式子同样算
    「已处理」—— 那些本来也求不出数值，交给客户端的算式渲染即可。
    """
    parts = calculation.get("parts") or []
    if not parts:
        return False
    if calculation.get("mCoefficient") is not None:
        return False
    if calculation.get("mDataValue") is not None:
        return False
    multiplier = calculation.get("mMultiplier")
    if multiplier is not None and classify_multiplier(multiplier) != RUNTIME:
        return False
    return all(_numeric_part(part, values) for part in parts)


def evaluate_calculations(
    raw: dict[str, dict[str, Any]],
    calculations: dict[str, Any],
    data_values: dict[str, Any],
    max_rank: int,
) -> dict[str, list[float]]:
    """把「客户端渲染不出、但能静态算出」的计算式算成逐级数值。

    返回 ``{计算式名: 逐级数组}``，数组前置一个 0 填充位（与
    `DataValues[].values` 同口径）。调用方并进命名数值表即可，客户端无需改动。

    被求值的式子有三个前提，缺一不可：

    1. 名字还没被命名数值占用（占用了客户端本来就能取到，不该覆盖）；
    2. 客户端自己渲染不出来（渲染得出就走原有路径，避免同一段文案两种写法）；
    3. 每一项都只用到命名数值与常量（``_eval_node`` 认得的那几种）。

    算不出的（吃英雄等级、buff 层数、运行时属性）原样留给客户端的 `?` ——
    **宁可留问号，也不编一个数**。
    """
    if max_rank <= 0:
        return {}

    values = {str(key).lower(): value for key, value in data_values.items()}
    evaluated: dict[str, list[float]] = {}

    for name, normalized in calculations.items():
        if HASHED_NAME.match(name):
            continue
        if str(name).lower() in values:
            continue
        if renderable_by_client(normalized, values):
            continue
        levels = _eval_calculation(name, raw, values, max_rank, frozenset())
        if levels is None:
            continue
        evaluated[name] = [0, *(json_number(level) for level in levels)]

    return evaluated
