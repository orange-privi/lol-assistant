from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    CDRAGON_STRINGTABLE_LOCALE,
    OUTPUT_DIR,
    RAW_DIR,
    SCHEMA_VERSION,
)
from .db.schema import create_database
from .db.writer import (
    write_champion,
    write_items,
    write_meta,
    write_monster_buffs,
    write_monsters,
    write_runes,
    write_summoner_spells,
)
from .downloader.http import HttpClient
from .downloader.sources import DataSources
from .parser.base_stats import apply_missing_stats, bin_base_stats
from .parser.bin_scope import icon_stem, scope_spell_keys, scope_spell_objects
from .parser.calculation import (
    collect_raw_calculations,
    evaluate_calculations,
    extract_calculations,
    extract_data_values,
    extract_effects,
    spell_damage_type,
)
from .parser.champion import parse_champion
from .parser.item import parse_items
from .parser.monster import (
    list_monster_codenames,
    parse_monster_buffs,
    parse_monsters,
)
from .parser.prices import load_champion_prices
from .parser.rune import parse_runes
from .parser.skin_availability import load_skin_availability
from .parser.spell import (
    DDRAGON_SPELL_KEY,
    backfill_cost_from_resource,
    effect_values,
)
from .parser.spelltext import SpellTextIndex, official_tooltip, token_names
from .parser.summoner import parse_summoner_spells
from .parser.util import dumps, int_value
from .parser.wiki_summoner import (
    DEFAULT_WIKI_SPELL_CACHE,
    build_wiki_summoner_pack,
    load_wiki_summoner_pack,
)


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
    # Data Dragon 侧那几样「BIN 里没有」的数值（`eN` / `cost` / `maxammo`）与
    # 消耗模板，取自 `parse_ddragon_spells` 暂存的原始技能对象，用完即弃。
    ddragon_spell = spell.pop(DDRAGON_SPELL_KEY, None) or {}
    ddragon_values = effect_values(ddragon_spell)

    scoped = scope_spell_objects(
        bin_json,
        champion_id,
        spell.get("id") or "",
        spell.get("slot") or "",
        icon_stems,
    )
    if not scoped:
        # 没有 BIN 数据，但 Data Dragon 的 `eN` 依旧可用 —— 落库，
        # 免得客户端连这部分都填不出。
        if ddragon_values:
            spell["dataValuesJson"] = dumps(ddragon_values)
            backfill_cost_from_resource(ddragon_spell, spell, ddragon_values)
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

    # Data Dragon 的补位数值排在 BIN 之后；同名的（大小写不敏感）以 BIN 为准 ——
    # 客户端查表也是大小写不敏感的，两处同名会让取值变得看运气。
    merged = dict(data_values)
    taken = {str(name).lower() for name in merged}
    for name, values in ddragon_values.items():
        if name.lower() in taken:
            continue
        taken.add(name.lower())
        merged[name] = values

    # 客户端渲染不出来的改写式/静态式：能静态算出的直接算成逐级数值并进命名
    # 数值表，客户端查表时优先取到它们（见 `evaluate_calculations`）。
    for name, values in evaluate_calculations(
        collect_raw_calculations(scoped),
        calculations,
        merged,
        int_value(spell.get("maxRank"), 1),
    ).items():
        merged[name] = values

    spell["calculationJson"] = dumps(calculations)
    spell["dataValuesJson"] = dumps(merged)
    spell["effectsJson"] = dumps(effects)
    spell["damageType"] = spell_damage_type(calculations) or spell.get(
        "damageType", ""
    )
    backfill_cost_from_resource(ddragon_spell, spell, merged)
    return True


def load_stringtable_entries(sources: DataSources) -> dict[str, Any]:
    """Localized client string-table entries for the build locale.

    Cache-first (``fetch`` warms ``raw/``); a missing or corrupt table degrades
    to ``{}`` so the build still completes -- the spell-text index then reports
    itself unusable and every ``tooltipRendered`` stays ``''``.
    """
    table = sources.download_stringtable(
        sources.stringtable_locale_dir(sources.locale)
    )
    entries = table.get("entries") if isinstance(table, dict) else None
    return entries if isinstance(entries, dict) else {}


def spell_value_names(spell: dict[str, Any]) -> set[str]:
    """本技能能取到的数值名（小写），来自命名数值表与计算式。

    与 `spelltext.token_names` 求交集即可判断「这段官方文案能不能真的填出数」。
    """
    names: set[str] = set()
    for column in ("dataValuesJson", "calculationJson"):
        try:
            payload = json.loads(spell.get(column) or "{}")
        except ValueError:
            continue
        if isinstance(payload, dict):
            names.update(str(key).lower() for key in payload)
    return names


def render_spell_text(
    spell: dict[str, Any],
    bin_json: dict[str, Any] | None,
    champion_id: str,
    icon_stems: tuple[str, ...],
    index: SpellTextIndex,
) -> str:
    """Official client text for one spell, or ``''`` when it is not needed.

    Two gates, both deliberate:

    * **Only when Data Dragon cannot fill the numbers.** Its Q/W/E/R tooltips
      carry ``{{ token }}`` placeholders that the client already renders from
      ``dataValuesJson`` / ``calculationJson``; only the passive (P) is a
      numberless prose sentence, so it is the one slot that needs the client
      string table instead. Widening this gate is a one-line change, but it
      would replace 692 already-working tooltips.
    * **Only when the text actually carries a fillable number.** A chunk of the
      candidates are prose without a single ``@token@`` (or only tokens this
      spell has no values for, e.g. ``@f1@`` index placeholders) -- those add
      nothing over Data Dragon's ``description``, and some of them read like a
      *unit-state* description rather than an ability one
      (``这个单位被击晕了。``). Leaving the column empty there is the correct
      answer: the client falls back to exactly what it does today.

    The returned text keeps its client markup *and* its ``@Token@``
    placeholders -- rendering is the client's job (see ``spelltext``).
    """
    if "{{" in (spell.get("tooltip") or ""):
        return ""

    scripts = [
        key.rsplit("/", 1)[-1]
        for key in scope_spell_keys(
            bin_json,
            champion_id,
            spell.get("id") or "",
            spell.get("slot") or "",
            icon_stems,
        )
    ]
    text = official_tooltip(index, scripts, spell.get("name") or "", champion_id)
    if not text:
        return ""

    known = spell_value_names(spell)
    if not (token_names(text) & known):
        return ""
    return text


def _load_monster_stringtables(
    sources: DataSources,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Both localized string tables for the monster section, each degrading to ``{}``.

    Returns ``(build-locale entries, en_us entries)``. A missing/corrupt table
    only empties the names / effect text -- the build never aborts here.
    """
    build_locdir = sources.stringtable_locale_dir(sources.locale)
    en_table = sources.download_stringtable(CDRAGON_STRINGTABLE_LOCALE)
    build_table = (
        en_table
        if build_locdir == CDRAGON_STRINGTABLE_LOCALE
        else sources.download_stringtable(build_locdir)
    )

    zh_entries = (
        build_table.get("entries") if isinstance(build_table, dict) else None
    )
    en_entries = (
        en_table.get("entries") if isinstance(en_table, dict) else None
    )
    if not zh_entries:
        print(
            "[WARN] monster stringtable "
            f"({build_locdir}) unavailable; name/effect default to ''"
        )
    if not en_entries:
        print(
            "[WARN] monster stringtable "
            f"({CDRAGON_STRINGTABLE_LOCALE}) unavailable; nameEn/effectEn "
            "default to ''"
        )
    return (zh_entries or {}), (en_entries or {})


def _build_monsters(
    sources: DataSources, db_version: str
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Read the cached monster sources and return ``monster`` rows.

    Everything is read cache-first from ``raw/`` (no dedicated ``cache/``
    artefact). Every source degrades gracefully: a missing directory listing
    yields no rows, a single failed BIN is skipped, and missing string tables
    leave the name / effect columns empty -- the build never aborts here.

    Also returns the two string-table entry dicts, so the reward-buff catalogue
    (:func:`parse_monster_buffs`) can be built without re-reading a 33 MB table.

    Kept as a standalone function so it can be exercised without a full build.
    """
    zh_entries, en_entries = _load_monster_stringtables(sources)

    index_html = sources.download_monster_index()
    if not index_html:
        print("[WARN] monster index unavailable; skipping monster section")
        return [], zh_entries, en_entries

    codenames = list_monster_codenames(index_html)
    bins: dict[str, Any] = {
        codename: sources.download_monster_bin(codename)
        for codename in codenames
    }

    rows = parse_monsters(
        codenames, bins, zh_entries, en_entries, db_version
    )
    return rows, zh_entries, en_entries


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

    # -- Local caches (prices / skin availability) -----------------------
    # Loaded once; a missing or corrupt cache degrades gracefully instead of
    # aborting the build.
    prices = load_champion_prices()
    available_skins = load_skin_availability()
    availability_mode = (
        f"{len(available_skins)} entries"
        if available_skins is not None
        else "fallback heuristic"
    )
    print(
        f"[INFO] champion prices: {len(prices)} entries; "
        f"skin availability: {availability_mode}"
    )

    # -- Wiki summoner-spell pack (offline cache, produced by ``fetch``) --
    # Missing/corrupt -> {} -> the four wiki columns keep their defaults.
    wiki_pack = load_wiki_summoner_pack()
    if wiki_pack:
        print(f"[INFO] wiki summoner spells: {len(wiki_pack)} entries")

    # -- Client string table (skill text for the spells Data Dragon can't fill) --
    # Cache-first; missing/corrupt -> unusable index -> every ``tooltipRendered``
    # stays ''. Never a network fetch here: once warmed by ``fetch`` (or the
    # monster section) this is a plain file read.
    spell_text = SpellTextIndex(load_stringtable_entries(sources))
    if spell_text.is_usable():
        print("[INFO] client spell text available for tooltipRendered")
    else:
        print("[WARN] client stringtable unavailable; tooltipRendered stays empty")

    # -- Static catalogues (single pass) ----------------------------------
    items = parse_items(base["items"])
    summoners = parse_summoner_spells(base["summoners"], wiki_pack)
    # Rune display text prefers CommunityDragon ``perks.json`` (its tooltips are
    # fully resolved); Data Dragon text is the fallback when a rune is missing.
    perks = sources.download_cdragon_perks()
    if not perks:
        print(
            "[WARN] cdragon perks unavailable; rune text falls back to "
            "Data Dragon"
        )
    rune_trees, runes = parse_runes(base["runes"], perks)
    write_items(connection, items)
    write_summoner_spells(connection, summoners)
    write_runes(connection, rune_trees, runes)
    print(
        f"[INFO] items={len(items)} summoners={len(summoners)} "
        f"runeTrees={len(rune_trees)} runes={len(runes)}"
    )

    # -- Champions --------------------------------------------------------
    empty_spells = 0
    rendered_spells = 0
    for index, champion_id in enumerate(champion_map, start=1):
        print(f"[{index}/{len(champion_map)}] {champion_id}")

        deep = sources.download_champion(ddragon_version, champion_id)
        champion = deep["data"][champion_id]

        cdragon = sources.download_cdragon_champion(
            int_value(champion.get("key"))
        )
        bin_json = sources.download_character_bin(champion_id)

        entity, spells, skins = parse_champion(
            champion, db_version, cdragon, prices, available_skins
        )
        # Data Dragon reports attackdamageperlevel as 0 for every champion;
        # backfill it (and any other zeroed stat) from the game BIN.
        apply_missing_stats(entity, bin_base_stats(bin_json, champion_id))

        passive_stems = tuple(passive_icon_stems(champion, cdragon))
        for spell in spells:
            icons = passive_stems if spell.get("slot") == "P" else ()
            if not enrich_spell_from_bin(spell, bin_json, champion_id, icons):
                empty_spells += 1
            spell["tooltipRendered"] = render_spell_text(
                spell, bin_json, champion_id, icons, spell_text
            )
            if spell["tooltipRendered"]:
                rendered_spells += 1

        write_champion(connection, entity, spells, skins)

    if empty_spells:
        print(f"[WARN] {empty_spells} spells had no matching BIN data")
    print(f"[INFO] tooltipRendered filled for {rendered_spells} spells")

    # -- Jungle monsters (Summoner's Rift) --------------------------------
    # Read straight from the cached ``raw/`` sources; a missing source degrades
    # to fewer (or zero) rows with a [WARN], never an aborted build.
    monsters, zh_entries, en_entries = _build_monsters(sources, db_version)
    write_monsters(connection, monsters)
    buffs = parse_monster_buffs(zh_entries, en_entries, db_version)
    write_monster_buffs(connection, buffs)
    print(f"[INFO] monsters={len(monsters)} monsterBuffs={len(buffs)}")

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


def fetch_support(version: str, locale: str) -> None:
    """Pull the runes / summoner-spell sources into ``raw/`` (no DB build).

    Fetches both sides of the picture:

    * Data Dragon seed -- ``runesReforged.json`` (localized names + inline
      numbers) and ``summoner.json`` (localized tooltips with ``{{ }}``).
    * CommunityDragon localized v1 -- ``perks.json`` / ``perkstyles.json``
      (103 perks incl. stat shards, ``@Token@`` tooltips) and
      ``summoner-spells.json`` (39 spells).

    The DB build is not touched: this only warms the on-disk cache so later
    parsing work can run offline.
    """
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
    print(f"[INFO] CommunityDragon locale: {sources.cdragon_locale()}")

    seed = sources.download_support_seed(ddragon_version)
    trees = seed.get("runes") or []
    rune_count = sum(
        len(slot.get("runes") or [])
        for tree in trees
        if isinstance(tree, dict)
        for slot in tree.get("slots") or []
    )
    summoner_data = (seed.get("summoners") or {}).get("data") or {}
    print(f"[OK] ddragon/runesReforged.json   trees={len(trees)} runes={rune_count}")
    print(f"[OK] ddragon/summoner.json        spells={len(summoner_data)}")

    perks = sources.download_cdragon_perks()
    perkstyles = sources.download_cdragon_perkstyles()
    summoners = sources.download_cdragon_summoner_spells()

    def count(payload: Any, key: str | None = None) -> str:
        if payload is None:
            return "unavailable"
        if key is not None and isinstance(payload, dict):
            payload = payload.get(key)
        if isinstance(payload, list):
            return str(len(payload))
        return "ok"

    print(f"[OK] cdragon/perks.json           perks={count(perks)}")
    print(
        "[OK] cdragon/perkstyles.json      "
        f"styles={count(perkstyles, 'styles')}"
    )
    print(f"[OK] cdragon/summoner-spells.json spells={count(summoners)}")

    # -- CommunityDragon jungle monsters (Summoner's Rift ``sru_*``) -------
    # Warms the directory listing, every ``sru_*`` BIN and both string tables
    # so ``build`` can parse the monster table fully offline.
    monster_index = sources.download_monster_index()
    if monster_index:
        codenames = list_monster_codenames(monster_index)
        ready = sum(
            1
            for codename in codenames
            if sources.download_monster_bin(codename) is not None
        )
        print(
            "[OK] cdragon/game/data/characters/index.html  "
            f"codenames={len(codenames)}"
        )
        print(
            "[OK] cdragon/game/data/characters/*.bin.json  "
            f"ok={ready}/{len(codenames)}"
        )
    else:
        print("[WARN] cdragon monster index unavailable")

    en_table = sources.download_stringtable(CDRAGON_STRINGTABLE_LOCALE)
    build_locdir = sources.stringtable_locale_dir(locale)
    print(
        f"[OK] cdragon/game/stringtable/"
        f"{CDRAGON_STRINGTABLE_LOCALE}.lol.stringtable.json  "
        f"{'ok' if en_table else 'unavailable'}"
    )
    if build_locdir != CDRAGON_STRINGTABLE_LOCALE:
        build_table = sources.download_stringtable(build_locdir)
        print(
            f"[OK] cdragon/game/stringtable/"
            f"{build_locdir}.lol.stringtable.json  "
            f"{'ok' if build_table else 'unavailable'}"
        )

    # -- LoL Wiki summoner-spell numbers (authoritative, rendered) --------
    # Downloaded to raw/ for reproducibility and rendered here so ``build`` can
    # run fully offline against the cached pack.
    wiki_en = sources.download_wiki_spelldata()
    wiki_zh = sources.download_wiki_spelldata_zh()
    print(
        "[OK] wiki/SpellData_data.lua      "
        f"{'ok' if wiki_en else 'unavailable'}"
    )
    print(
        "[OK] wiki/SpellData_data_zh.lua   "
        f"{'ok' if wiki_zh else 'unavailable'}"
    )

    wiki_pack = build_wiki_summoner_pack(
        wiki_en or "",
        wiki_zh or "",
    )
    cache_payload = {
        "source": "LoL Wiki Module:SpellData/data (+ zh-CN sandbox)",
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "spellCount": len(wiki_pack),
        "spells": wiki_pack,
    }
    DEFAULT_WIKI_SPELL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_WIKI_SPELL_CACHE.write_text(
        json.dumps(cache_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "[OK] cache/summoner_spells_wiki.json "
        f"spells={len(wiki_pack)}"
    )
    print(f"[OK] raw -> {RAW_DIR / cdragon_version / locale}")


def _open(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def inspect(
    db_path: str,
    champion: str,
    item: str | None = None,
    monster: str | None = None,
) -> None:
    connection = _open(db_path)

    if item is not None:
        row = connection.execute(
            "SELECT * FROM item WHERE name = ? OR id = ?",
            (item, int_value(item, -1)),
        ).fetchone()
        print(dict(row) if row else f"Item not found: {item}")
        connection.close()
        return

    if monster is not None:
        row = connection.execute(
            "SELECT * FROM monster WHERE id = ? OR name = ?",
            (monster, monster),
        ).fetchone()
        print(dict(row) if row else f"Monster not found: {monster}")
        if row:
            buffs = connection.execute(
                "SELECT id, name, kind, camp, description "
                "FROM monster_buff WHERE camp = ? ORDER BY id",
                (row["camp"],),
            ).fetchall()
            for buff in buffs:
                print(f"\n=== buff {buff['id']} "
                      f"[{buff['kind']}/{buff['camp']}] {buff['name']} ===")
                print(buff["description"])
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
        SELECT slot, name, calculationJson, dataValuesJson, effectsJson,
               tooltipRendered
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
        print("tooltipRendered:", spell["tooltipRendered"] or "(empty)")

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
        "monster",
        "monster_buff",
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
