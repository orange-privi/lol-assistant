# lol-assistant-data

League of Legends static-data ETL for the Lolok Android app.

## Data flow

Data Dragon (localized base data)
+
CommunityDragon (current client/game data)
        |
        v
Python ETL
        |
        v
SQLite (`lol-<version>.db`)
        |
        v
Android Room

CommunityDragon:
- https://raw.communitydragon.org/latest/
- https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/
- https://raw.communitydragon.org/latest/game/data/characters/

Data Dragon:
- https://ddragon.leagueoflegends.com/

## Requirements

Python 3.11+.

Install:

```bash
python -m pip install -r requirements.txt
```

## Build

Build latest data:

```bash
python -m src.main build --version latest --locale zh_CN
```

Pin a patch:

```bash
python -m src.main build --version 16.20 --locale zh_CN
```

Output:

```text
output/
  lol-<resolved-version>.db
  latest.json
```

## What gets built

| Table | Source | Notes |
| --- | --- | --- |
| `champion` | Data Dragon + CommunityDragon v1 | stats, localized text, tags, `playstyleInfo`, `tacticalInfo` |
| `champion_spell` | Data Dragon + CommunityDragon BIN | per-slot calculations / data values |
| `champion_skin` | CommunityDragon v1 | splash + loading asset paths |
| `item` | Data Dragon `item.json` | gold, stats, build paths |
| `summoner_spell` | Data Dragon `summoner.json` | cooldown / cost / modes |
| `rune_tree`, `rune` | Data Dragon `runesReforged.json` | |

Spell deep data is scoped **per ability**: the ETL matches each Data Dragon
spell `id` (script name, e.g. `KayleQ`, `DariusCleave`) against the
CommunityDragon BIN object path
`Characters/<Champion>/Spells/<Container>/<scriptName>`, so a spell only carries
its own `mSpellCalculations` / `DataValues` instead of the whole champion blob.

Known limitation: champion price (BE/RP) is not exposed by Data Dragon or
CommunityDragon v1, so `priceBe` / `priceRp` remain `0`.

## Validation

```bash
python -m src.main inspect --db output/lol-<version>.db --champion Kayle
python -m src.main inspect --db output/lol-<version>.db --item 1001
python -m src.main stats   --db output/lol-<version>.db
python -m unittest discover -s tests
```

The milestone validates champion + spell + DataValue + GameCalculation parsing.
`stats` prints a row count per table so an empty load is obvious.
