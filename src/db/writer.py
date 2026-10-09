from __future__ import annotations

import sqlite3
from typing import Any


CHAMPION_COLUMNS = [
    "id", "key", "name", "title", "nameEn", "titleEn",
    "priceBe", "priceRp", "lore", "blurb", "tags", "partype",
    "infoAttack", "infoDefense", "infoMagic", "infoDifficulty",
    "hp", "hpPerLevel", "mp", "mpPerLevel",
    "hpRegen", "hpRegenPerLevel", "mpRegen", "mpRegenPerLevel",
    "armor", "armorPerLevel", "magicResist", "magicResistPerLevel",
    "attackDamage", "attackDamagePerLevel",
    "attackSpeed", "attackSpeedPerLevel",
    "attackRange", "moveSpeed",
    "icon", "loading", "allyTips", "enemyTips",
    "attackType", "damageType", "difficultyTier",
    "tagPrimary", "tagSecondary",
    "playDamage", "playDurability", "playCrowdControl",
    "playMobility", "playUtility",
]

SPELL_COLUMNS = [
    "championId", "slot", "name", "description", "tooltip",
    "cooldown", "cost", "range",
    "cooldownLevels", "costLevels", "rangeLevels",
    "maxRank", "icon",
    "resource", "ammoMax", "ammoRechargeLevels",
    "calculationJson", "dataValuesJson", "effectsJson",
    "damageType", "dataVersion",
]

SKIN_COLUMNS = [
    "championId", "num", "name", "chromas",
    "hasImage", "localImage", "splashUrl", "loadingUrl",
]

ITEM_COLUMNS = [
    "id", "name", "plaintext", "description",
    "goldTotal", "goldBase", "goldSell", "purchasable",
    "tags", "maps", "icon", "fromItems", "intoItems",
    "statsJson", "depth",
]

SUMMONER_COLUMNS = [
    "id", "key", "name", "description", "tooltip",
    "cooldown", "cooldownBurn", "costBurn", "rangeBurn",
    "modes", "castLevel", "charges", "recharge", "effect", "icon",
]

RUNE_TREE_COLUMNS = ["id", "key", "name", "icon"]

RUNE_COLUMNS = [
    "id", "treeId", "slot", "key", "name",
    "shortDesc", "longDesc", "icon",
]

MONSTER_COLUMNS = [
    "id", "name", "nameEn", "category", "camp", "tags",
    "hp", "hpPerLevel", "attackDamage", "attackDamagePerLevel",
    "armor", "armorPerLevel", "magicResist", "magicResistPerLevel",
    "moveSpeed", "attackSpeed", "attackRange",
    "goldGiven", "goldGivenTotal", "expGiven", "expGivenTotal",
    "icon", "dataVersion",
]


def _insert_sql(table: str, columns: list[str]) -> str:
    quoted = ",".join(columns)
    placeholders = ",".join("?" for _ in columns)
    return f"INSERT OR REPLACE INTO {table} ({quoted}) VALUES ({placeholders})"


def insert_dict(
    connection: sqlite3.Connection,
    table: str,
    columns: list[str],
    row: dict[str, Any],
) -> None:
    values = [row.get(column) for column in columns]
    connection.execute(_insert_sql(table, columns), values)


def insert_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    values = [[row.get(column) for column in columns] for row in rows]
    connection.executemany(_insert_sql(table, columns), values)


def write_champion(
    connection: sqlite3.Connection,
    champion: dict[str, Any],
    spells: list[dict[str, Any]],
    skins: list[dict[str, Any]] | None = None,
) -> None:
    insert_dict(connection, "champion", CHAMPION_COLUMNS, champion)
    insert_rows(connection, "champion_spell", SPELL_COLUMNS, spells)
    if skins:
        insert_rows(connection, "champion_skin", SKIN_COLUMNS, skins)


def write_items(
    connection: sqlite3.Connection,
    items: list[dict[str, Any]],
) -> None:
    insert_rows(connection, "item", ITEM_COLUMNS, items)


def write_summoner_spells(
    connection: sqlite3.Connection,
    spells: list[dict[str, Any]],
) -> None:
    insert_rows(connection, "summoner_spell", SUMMONER_COLUMNS, spells)


def write_runes(
    connection: sqlite3.Connection,
    trees: list[dict[str, Any]],
    runes: list[dict[str, Any]],
) -> None:
    insert_rows(connection, "rune_tree", RUNE_TREE_COLUMNS, trees)
    insert_rows(connection, "rune", RUNE_COLUMNS, runes)


def write_monsters(
    connection: sqlite3.Connection,
    monsters: list[dict[str, Any]],
) -> None:
    insert_rows(connection, "monster", MONSTER_COLUMNS, monsters)


def write_meta(
    connection: sqlite3.Connection,
    values: dict[str, str],
) -> None:
    rows = [
        {"key": key, "value": value} for key, value in values.items()
    ]
    insert_rows(connection, "meta", ["key", "value"], rows)
