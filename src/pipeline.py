from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR, SCHEMA_VERSION
from .db.schema import create_database
from .db.writer import (
    write_champion,
    write_items,
    write_meta,
    write_runes,
    write_summoner_spells,
)
from .downloader.http import HttpClient
from .downloader.sources import DataSources
from .parser.base_stats import apply_missing_stats, bin_base_stats
from .parser.bin_scope import icon_stem, scope_spell_objects
from .parser.calculation import (
    extract_calculations,
    extract_data_values,
    extract_effects,
    spell_damage_type,
)
from .parser.champion import parse_champion
from .parser.item import parse_items
from .parser.rune import parse_runes
from .parser.summoner import parse_summoner_spells
from .parser.util import dumps, int_value


def resolve_cdragon_version(version: str) -> str:
    # CommunityDragon has no stable patch API here; use its latest channel.
    # The final database stores the Data Dragon patch as the version label.
    return "latest" if version == "latest" else version


def passive_icon_stems(
    champion: dict[str, Any],
    cdragon: dict[str, Any] | None,
) -> list[str]:
    """Icon hints used to locate a passive that has no Data Dragon script id."""
    stems = []
    image = (champion.get("passive") or {}).get("image") or {}
    if image.get("full"):
        stems.append(icon_stem(image["full"]))
    if cdragon:
        passive = cdragon.get("passive") or {}
        if passive.get("abilityIconPath"):
            stems.append(icon_stem(passive["abilityIconPath"]))
    return [stem for stem in stems if stem]


def enrich_spell_from_bin(
    spell: dict[str, Any],
    bin_json: dict[str, Any] | None,
    champion_id: str,
    icon_stems: tuple[str, ...] = (),
) -> bool:
    """Attach the *scoped* calculations/data values for one spell.

    Returns False when no matching BIN objects were found.
    """
    scoped = scope_spell_objects(
        bin_json,
        champion_id,
        spell.get("id") or "",
        spell.get("slot") or "",
        icon_stems,
    )
    if not scoped:
        return False

    calculations: dict[str, Any] = {}
    data_values: dict[str, Any] = {}
    effects: dict[str, Any] = {}

    for obj in scoped:
        calculations.update(extract_calculations(obj))
        for name, values in extract_data_values(obj).items():
            data_values.setdefault(name, values)
        for key, value in extract_effects(obj).items():
            bucket = effects.setdefault(key, [])
            bucket.extend(value if isinstance(value, list) else [value])

    spell["calculationJson"] = dumps(calculations)
    spell["dataValuesJson"] = dumps(data_values)
    spell["effectsJson"] = dumps(effects)
    spell["damageType"] = spell_damage_type(calculations) or spell.get(
        "damageType", ""
    )
    return True


def build(version: str, locale: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    http = HttpClient()
    cdragon_version = resolve_cdragon_version(version)
    sources = DataSources(cdragon_version, locale, http)

    ddragon_version = (
        sources.resolve_ddragon_version()
        if version == "latest"
        else f"{version}.1"
    )

    print(f"[INFO] Data Dragon version: {ddragon_version}")
    print(f"[INFO] CommunityDragon channel: {cdragon_version}")

    base = sources.download_base_data(ddragon_version)
    champion_map = base["champions"]["data"]

    db_version = ddragon_version.removesuffix(".1")
    db_path = OUTPUT_DIR / f"lol-{db_version}.db"
    if db_path.exists():
        # Truncate instead of delete: an empty file is a valid empty SQLite
        # database, and this keeps the build idempotent without relying on
        # filesystem deletion semantics.
        db_path.open("wb").close()

    connection = create_database(str(db_path))
    generated_at = datetime.now(timezone.utc).isoformat()

    # -- Static catalogues (single pass) ----------------------------------
    items = parse_items(base["items"])
    summoners = parse_summoner_spells(base["summoners"])
    rune_trees, runes = parse_runes(base["runes"])
    write_items(connection, items)
    write_summoner_spells(connection, summoners)
    write_runes(connection, rune_trees, runes)
    print(
        f"[INFO] items={len(items)} summoners={len(summoners)} "
        f"runeTrees={len(rune_trees)} runes={len(runes)}"
    )

    # -- Champions --------------------------------------------------------
    empty_spells = 0
    for index, champion_id in enumerate(champion_map, start=1):
        print(f"[{index}/{len(champion_map)}] {champion_id}")

        deep = sources.download_champion(ddragon_version, champion_id)
        champion = deep["data"][champion_id]

        cdragon = sources.download_cdragon_champion(
            int_value(champion.get("key"))
        )
        bin_json = sources.download_character_bin(champion_id)

        entity, spells, skins = parse_champion(champion, db_version, cdragon)
        # Data Dragon reports attackdamageperlevel as 0 for every champion;
        # backfill it (and any other zeroed stat) from the game BIN.
        apply_missing_stats(entity, bin_base_stats(bin_json, champion_id))

        passive_stems = tuple(passive_icon_stems(champion, cdragon))
        for spell in spells:
            icons = passive_stems if spell.get("slot") == "P" else ()
            if not enrich_spell_from_bin(spell, bin_json, champion_id, icons):
                empty_spells += 1

        write_champion(connection, entity, spells, skins)

    if empty_spells:
        print(f"[WARN] {empty_spells} spells had no matching BIN data")

    write_meta(
        connection,
        {
            "data_version": db_version,
            "schema_version": str(SCHEMA_VERSION),
            "source": "DataDragon+CommunityDragon",
            "generated_at": generated_at,
            "ddragon_version": ddragon_version,
            "cdragon_version": cdragon_version,
        },
    )

    connection.commit()
    connection.execute("VACUUM")
    connection.close()

    sha256 = hashlib.sha256(db_path.read_bytes()).hexdigest()
    size = db_path.stat().st_size

    latest = {
        "version": db_version,
        "schemaVersion": SCHEMA_VERSION,
        "file": db_path.name,
        "sha256": sha256,
        "size": size,
        "locale": locale,
        "generatedAt": generated_at,
    }

    (OUTPUT_DIR / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] {db_path}")
    print(f"[OK] SHA-256: {sha256}")

    return db_path


def _open(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def inspect(db_path: str, champion: str, item: str | None = None) -> None:
    connection = _open(db_path)

    if item is not None:
        row = connection.execute(
            "SELECT * FROM item WHERE name = ? OR id = ?",
            (item, int_value(item, -1)),
        ).fetchone()
        print(dict(row) if row else f"Item not found: {item}")
        connection.close()
        return

    row = connection.execute(
        "SELECT * FROM champion WHERE id = ? OR name = ?",
        (champion, champion),
    ).fetchone()

    if not row:
        print("Champion not found:", champion)
        connection.close()
        return

    print(dict(row))

    spells = connection.execute(
        """
        SELECT slot, name, calculationJson, dataValuesJson, effectsJson
        FROM champion_spell
        WHERE championId = ?
        ORDER BY CASE slot
          WHEN 'P' THEN 0
          WHEN 'Q' THEN 1
          WHEN 'W' THEN 2
          WHEN 'E' THEN 3
          WHEN 'R' THEN 4
          ELSE 99
        END
        """,
        (row["id"],),
    ).fetchall()

    for spell in spells:
        print("\n===", spell["slot"], spell["name"], "===")
        print("calculations:", spell["calculationJson"])
        print("dataValues:", spell["dataValuesJson"])
        print("effects:", spell["effectsJson"])

    skins = connection.execute(
        "SELECT COUNT(*) FROM champion_skin WHERE championId = ?",
        (row["id"],),
    ).fetchone()[0]
    print(f"\nskins: {skins}")

    connection.close()


def stats(db_path: str) -> None:
    connection = _open(db_path)
    tables = [
        "champion",
        "champion_spell",
        "champion_skin",
        "item",
        "summoner_spell",
        "rune_tree",
        "rune",
        "meta",
    ]
    print(f"database: {db_path}")
    for table in tables:
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - fixed table list
        ).fetchone()[0]
        print(f"  {table:<18} {count}")

    print("meta:")
    for meta in connection.execute("SELECT key, value FROM meta ORDER BY key"):
        print(f"  {meta['key']:<16} {meta['value']}")

    connection.close()
