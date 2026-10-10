from __future__ import annotations

import json
import re
from typing import Any

from .util import (
    clean_rich_text,
    dumps,
    int_value,
    json_array,
    json_number,
    text,
)

# Data Dragon 的定位模板里引用数值的写法，如 `{{ healthcost }}生命值`
RESOURCE_TOKEN = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

# 技能字典上的内部字段名：原始 Data Dragon 技能对象的暂存位，由
# `pipeline.enrich_spell_from_bin` 消费后丢弃（`db.writer` 只按列名取值，
# 不会把它写进数据库）。
#
# 之所以要留原始对象而不是先算出结果：`resource` 这一列落库时是**给人看的中文标签**
# （「生命值」），模板本身会被覆盖掉；而「消耗量在哪个命名数值里」只有模板知道。
DDRAGON_SPELL_KEY = "_ddragonSpell"


def rank_values(spell: dict[str, Any], key: str) -> list[Any]:
    value = spell.get(key)
    if isinstance(value, list):
        return value

    # Data Dragon sometimes provides a scalar in odd cases.
    if value is None:
        return []
    return [value]


def _numeric_list(value: Any) -> list[float]:
    """数值数组；有任何一项不是数就整体放弃（宁可不填，也不填半个）。"""
    if not isinstance(value, list) or not value:
        return []
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return []
        numbers.append(float(item))
    return numbers


def _burn_levels(value: Any) -> list[float]:
    """``effectBurn`` 的展示串（``'40/55/70/85/100'``）-> 逐级数值。"""
    if not isinstance(value, str) or not value.strip():
        return []
    parts: list[float] = []
    for chunk in value.split("/"):
        try:
            parts.append(float(chunk.strip()))
        except ValueError:
            return []
    return parts


def _levels_from_json(value: Any) -> list[float]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return _numeric_list(value)


def format_number(value: float) -> str:
    """与 Android `SpellNumbers.formatNumber` 同口径：保留两位小数，整数不带小数点。"""
    rounded = round(value, 2)
    if rounded == int(rounded) and abs(rounded) < 1e15:
        return str(int(rounded))
    return str(rounded)


def fold_levels(levels: list[float]) -> str:
    """逐级值折成一行：全相同只留一个，否则用「 / 」连起来。

    与 Android `foldLevels` 同一套展示口径 —— 冷却/消耗/范围在界面上都是一行文字。
    """
    parts = [part for part in (format_number(level) for level in levels) if part]
    if not parts:
        return ""
    distinct = list(dict.fromkeys(parts))
    return distinct[0] if len(distinct) == 1 else " / ".join(parts)


def effect_values(spell: dict[str, Any]) -> dict[str, list[float]]:
    """Data Dragon 侧「BIN 里没有、但官方文案会引用」的技能级数值。

    客户端 tooltip 里的 `{{ eN }}` 按官方约定取 **effect 数组的第 N 项**，
    `{{ cost }}` / `{{ maxammo }}` 取技能自身的消耗与充能上限。这三样都不在 BIN 的
    命名数值表里（`effect` 与 `effectBurn` 此前根本没被读取过），只能从 Data Dragon 补。

    数组一律**前置一个 0 填充位**：客户端取逐级值的口径是 `rank r -> values[r]`
    （见 Android `SpellNumbers.levelsOf`），与 BIN 的 `DataValues[].values` 一致。

    全 0 的 effect 项不注入 —— 0 在客户端数据里常表示「这一项不存在」，
    与其在正文里显示一个可疑的 0，不如留给客户端的 `?`。
    """
    max_rank = max(1, int_value(spell.get("maxrank"), 1))
    values: dict[str, list[float]] = {}

    effects = spell.get("effect")
    burns = spell.get("effectBurn")
    if isinstance(effects, list):
        for index, item in enumerate(effects):
            if index == 0:  # effect[0] 恒为 null
                continue
            levels = _numeric_list(item)
            if not levels and isinstance(burns, list) and index < len(burns):
                levels = _burn_levels(burns[index])
            levels = levels[:max_rank]
            if not levels or not any(levels):
                continue
            values[f"e{index}"] = [0, *(json_number(level) for level in levels)]

    costs = _numeric_list(spell.get("cost"))[:max_rank]
    if costs and any(costs):
        values["cost"] = [0, *(json_number(cost) for cost in costs)]

    # Data Dragon 把 maxammo 给成**字符串**（'2'，不适用时 '-1'），和 cost 那种
    # 数字数组不是一回事，得先转。
    max_ammo = int_value(spell.get("maxammo"))
    if max_ammo > 0:
        values["maxammo"] = [0, max_ammo]

    return values


def resource_placeholder_names(spell: dict[str, Any]) -> list[str]:
    """`costType` / `resource` 模板里引用的名字。

    Data Dragon 对「消耗生命值」这类技能给的 `cost` 全是 0，消耗量藏在模板里
    （`resource = '{{ healthcost }}生命值'`）。同时出现的
    `{{ abilityresourcename }}` 是本地化键、不是数值，调用方按「命名数值表里
    找得到」过滤。
    """
    names: list[str] = []
    for key in ("costType", "resource"):
        for match in RESOURCE_TOKEN.finditer(text(spell.get(key))):
            name = match.group(1)
            if name not in names:
                names.append(name)
    return names


def backfill_cost_from_resource(
    ddragon_spell: dict[str, Any],
    spell: dict[str, Any],
    data_values: dict[str, Any],
) -> bool:
    """把 `costLevels` 从资源消耗模板里补出来。

    Data Dragon 对生命值消耗类技能给的 `cost` 是 `[0,0,0,0,0]`、`costBurn='0'`，
    真值在 `resource` 模板引用的命名数值里（如 Mundo Q 的 `HealthCost`）。
    此前 `resource` 只留下「生命值」三个字，界面上就成了「消耗 生命值」——
    数值一直都在，只是没落进 `costLevels`。

    只认**光名字**的模板；带运算的（`{{ currenthealthcost*100 }}%当前生命值`）
    单位与量纲都不同，交给客户端的 `?`，不猜。
    """
    if any(_levels_from_json(spell.get("costLevels"))):
        return False  # Data Dragon 自己给了消耗，不用补

    max_rank = max(1, int_value(spell.get("maxRank"), 1))
    values = {str(key).lower(): value for key, value in data_values.items()}

    for name in resource_placeholder_names(ddragon_spell):
        levels = _numeric_list(values.get(name.lower()))
        if len(levels) < 2 or not any(levels[1:]):
            continue
        # 去掉填充位，再按技能等级数截断
        levels = levels[1:][:max_rank]
        spell["costLevels"] = json_array(
            [json_number(level) for level in levels]
        )
        spell["cost"] = fold_levels(levels)
        return True
    return False


def spell_resource(spell: dict[str, Any], champion_partype: str) -> str:
    """Human-readable resource label for a spell.

    Data Dragon exposes ``costType``/``resource`` as localization templates such
    as ``{{ cost }} {{ abilityresourcename }}`` which are useless to clients.
    Fall back to the champion's partype (or a "no cost" marker) when that
    happens.
    """
    cost = int_value((spell.get("cost") or [0])[0] if isinstance(spell.get("cost"), list) else 0)
    raw = text(spell.get("costType")).strip()
    if raw and "{{" not in raw:
        return raw
    if cost > 0:
        return champion_partype
    return "无消耗"


def parse_ddragon_spells(
    champion: dict[str, Any],
    partype: str,
) -> list[dict[str, Any]]:
    result = []

    for index, spell in enumerate(champion.get("spells") or []):
        max_rank = max(1, int_value(spell.get("maxrank"), 1))
        result.append(
            {
                "id": text(spell.get("id")),
                "slot": "QWER"[index] if index < 4 else f"S{index}",
                "name": text(spell.get("name")),
                "description": clean_rich_text(text(spell.get("description"))),
                "tooltip": text(spell.get("tooltip")),
                "cooldown": text(spell.get("cooldownBurn")),
                "cost": text(spell.get("costBurn")),
                "range": text(spell.get("rangeBurn")),
                "cooldownLevels": json_array(rank_values(spell, "cooldown")),
                "costLevels": json_array(rank_values(spell, "cost")),
                "rangeLevels": json_array(rank_values(spell, "range")),
                "maxRank": max_rank,
                "resource": spell_resource(spell, partype),
                "ammoMax": max(0, int_value(spell.get("maxammo"))),
                "icon": (
                    f"img/spell/{spell.get('image', {}).get('full', '')}"
                    if spell.get("image")
                    else ""
                ),
                # 内部字段：原始 Data Dragon 技能对象，由
                # `pipeline.enrich_spell_from_bin` 用来补 `eN` / 消耗后丢弃。
                DDRAGON_SPELL_KEY: spell,
            }
        )

    passive = champion.get("passive") or {}
    if passive:
        result.insert(
            0,
            {
                "id": "",
                "slot": "P",
                "name": text(passive.get("name")),
                "description": clean_rich_text(text(passive.get("description"))),
                "tooltip": clean_rich_text(text(passive.get("description"))),
                "cooldown": "",
                "cost": "",
                "range": "",
                "cooldownLevels": "[]",
                "costLevels": "[]",
                "rangeLevels": "[]",
                "maxRank": 1,
                "resource": "",
                "ammoMax": 0,
                "icon": (
                    f"img/passive/{passive.get('image', {}).get('full', '')}"
                    if passive.get("image")
                    else ""
                ),
                DDRAGON_SPELL_KEY: {},
            },
        )

    return result


def make_spell(
    base: dict[str, Any],
    champion_id: str,
    calculation_json: dict[str, Any],
    data_values: dict[str, list[Any]],
    effects: dict[str, Any],
    version: str,
    damage_type: str = "",
) -> dict[str, Any]:
    return {
        "championId": champion_id,
        **base,
        # 官方文案（客户端字符串表来源，保留 `@占位符@`）。默认空串 ——
        # Data Dragon 自带的 `{{ 占位符 }}` 能渲染的技能不需要它，由
        # `pipeline._render_spell_text` 只对「填不出数值」的技能填上。
        "tooltipRendered": "",
        "ammoRechargeLevels": "[]",
        "calculationJson": dumps(calculation_json),
        "dataValuesJson": dumps(data_values),
        "effectsJson": dumps(effects),
        "damageType": damage_type,
        "dataVersion": version,
    }
