from __future__ import annotations

import sqlite3

SCHEMA = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE champion (
    id TEXT PRIMARY KEY NOT NULL,
    key INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    nameEn TEXT NOT NULL,
    titleEn TEXT NOT NULL,
    priceBe INTEGER NOT NULL,
    priceRp INTEGER NOT NULL,
    lore TEXT NOT NULL,
    blurb TEXT NOT NULL,
    tags TEXT NOT NULL,
    partype TEXT NOT NULL,
    infoAttack INTEGER NOT NULL,
    infoDefense INTEGER NOT NULL,
    infoMagic INTEGER NOT NULL,
    infoDifficulty INTEGER NOT NULL,
    hp REAL NOT NULL,
    hpPerLevel REAL NOT NULL,
    mp REAL NOT NULL,
    mpPerLevel REAL NOT NULL,
    hpRegen REAL NOT NULL,
    hpRegenPerLevel REAL NOT NULL,
    mpRegen REAL NOT NULL,
    mpRegenPerLevel REAL NOT NULL,
    armor REAL NOT NULL,
    armorPerLevel REAL NOT NULL,
    magicResist REAL NOT NULL,
    magicResistPerLevel REAL NOT NULL,
    attackDamage REAL NOT NULL,
    attackDamagePerLevel REAL NOT NULL,
    attackSpeed REAL NOT NULL,
    attackSpeedPerLevel REAL NOT NULL,
    attackRange REAL NOT NULL,
    moveSpeed REAL NOT NULL,
    icon TEXT NOT NULL,
    loading TEXT NOT NULL,
    allyTips TEXT NOT NULL,
    enemyTips TEXT NOT NULL,
    attackType TEXT NOT NULL,
    damageType TEXT NOT NULL,
    difficultyTier INTEGER NOT NULL,
    tagPrimary TEXT NOT NULL,
    tagSecondary TEXT NOT NULL,
    playDamage INTEGER NOT NULL,
    playDurability INTEGER NOT NULL,
    playCrowdControl INTEGER NOT NULL,
    playMobility INTEGER NOT NULL,
    playUtility INTEGER NOT NULL
);

CREATE INDEX idx_champion_name ON champion(name);

CREATE TABLE champion_spell (
    championId TEXT NOT NULL,
    slot TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    tooltip TEXT NOT NULL,
    cooldown TEXT NOT NULL,
    cost TEXT NOT NULL,
    range TEXT NOT NULL,
    cooldownLevels TEXT NOT NULL,
    costLevels TEXT NOT NULL,
    rangeLevels TEXT NOT NULL,
    maxRank INTEGER NOT NULL,
    icon TEXT NOT NULL,
    resource TEXT NOT NULL,
    ammoMax INTEGER NOT NULL,
    ammoRechargeLevels TEXT NOT NULL,
    calculationJson TEXT NOT NULL,
    dataValuesJson TEXT NOT NULL,
    effectsJson TEXT NOT NULL,
    damageType TEXT NOT NULL,
    dataVersion TEXT NOT NULL,
    PRIMARY KEY (championId, slot),
    FOREIGN KEY (championId) REFERENCES champion(id) ON DELETE CASCADE
);

CREATE INDEX idx_champion_spell_championId
    ON champion_spell(championId);

CREATE TABLE champion_skin (
    championId TEXT NOT NULL,
    num INTEGER NOT NULL,
    name TEXT NOT NULL,
    chromas INTEGER NOT NULL,
    hasImage INTEGER NOT NULL,
    localImage TEXT NOT NULL,
    splashUrl TEXT NOT NULL,
    loadingUrl TEXT NOT NULL,
    PRIMARY KEY (championId, num),
    FOREIGN KEY (championId) REFERENCES champion(id) ON DELETE CASCADE
);

CREATE TABLE item (
    id INTEGER PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    plaintext TEXT NOT NULL,
    description TEXT NOT NULL,
    goldTotal INTEGER NOT NULL,
    goldBase INTEGER NOT NULL,
    goldSell INTEGER NOT NULL,
    purchasable INTEGER NOT NULL,
    tags TEXT NOT NULL,
    maps TEXT NOT NULL,
    icon TEXT NOT NULL,
    fromItems TEXT NOT NULL,
    intoItems TEXT NOT NULL,
    statsJson TEXT NOT NULL,
    depth INTEGER NOT NULL
);

CREATE INDEX idx_item_name ON item(name);
CREATE INDEX idx_item_goldTotal ON item(goldTotal);

CREATE TABLE summoner_spell (
    id TEXT PRIMARY KEY NOT NULL,
    key INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    tooltip TEXT NOT NULL,
    cooldown INTEGER NOT NULL,
    cooldownBurn TEXT NOT NULL,
    costBurn TEXT NOT NULL,
    rangeBurn TEXT NOT NULL,
    modes TEXT NOT NULL,
    icon TEXT NOT NULL
);

CREATE INDEX idx_summoner_spell_key ON summoner_spell(key);

CREATE TABLE rune_tree (
    id INTEGER PRIMARY KEY NOT NULL,
    key TEXT NOT NULL,
    name TEXT NOT NULL,
    icon TEXT NOT NULL
);

CREATE INDEX idx_rune_tree_key ON rune_tree(key);

CREATE TABLE rune (
    id INTEGER PRIMARY KEY NOT NULL,
    treeId INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    key TEXT NOT NULL,
    name TEXT NOT NULL,
    shortDesc TEXT NOT NULL,
    longDesc TEXT NOT NULL,
    icon TEXT NOT NULL,
    FOREIGN KEY (treeId) REFERENCES rune_tree(id) ON DELETE CASCADE
);

CREATE INDEX idx_rune_treeId ON rune(treeId);
CREATE INDEX idx_rune_name ON rune(name);

CREATE TABLE meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);
"""


def create_database(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    return connection
