# lol-assistant-data

League of Legends static-data ETL for the Lolok Android app.

## Data flow

Data Dragon (localized base data)
+
CommunityDragon (current client/game data)
+
LoL Wiki (authoritative summoner-spell numbers)
        |
        v
Python ETL
        |
        v
SQLite (`lol-<version>.db`, schema v5)
        |
        v
Android Room

CommunityDragon:
- https://raw.communitydragon.org/latest/
- https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/
- https://raw.communitydragon.org/latest/game/data/characters/

Data Dragon:
- https://ddragon.leagueoflegends.com/

League of Legends Wiki (MediaWiki API: https://wiki.leagueoflegends.com/en-us/api.php):
- `Module:SpellData/data` (English, authoritative numbers)
- `Module:Sandbox/WordlessMeteor/SpellData/zh-CN/data` (Chinese names + effect text)

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
| `champion` | Data Dragon + CommunityDragon v1 | stats, localized text, tags, `playstyleInfo`, `tacticalInfo`, BE/RP price (`cache/champion_prices.json`) |
| `champion_spell` | Data Dragon + CommunityDragon BIN | per-slot calculations / data values |
| `champion_skin` | CommunityDragon v1 + Data Dragon | localized name, constructed `localImage` / `splashUrl` / `loadingUrl`, probed `hasImage` |
| `item` | Data Dragon `item.json` | gold, stats, build paths |
| `summoner_spell` | Data Dragon `summoner.json` + LoL Wiki | cooldown / cost / modes + Wiki numbers (`castLevel`, `charges`, `recharge`, `effect`) |
| `rune_tree`, `rune` | Data Dragon `runesReforged.json` | |
| `monster` | CommunityDragon `game/data/characters/` BIN + string tables | Summoner's-Rift jungle monsters (`sru_*`); stats, `category`/`camp`, localized name, icon path |

`summoner_spell` gained four Wiki-sourced columns in **schema v4**:

| Column | Meaning | Default (unmapped row) |
| --- | --- | --- |
| `castLevel` | summoner level required to unlock (Wiki `level`) | `0` |
| `charges` | number of charges (Wiki `charges`) | `0` |
| `recharge` | recharge time in seconds (Wiki `recharge`) | `0` |
| `effect` | rendered **Chinese** value description (Wiki `effect`) | `''` |

Neither Data Dragon nor CommunityDragon carries fillable numbers for summoner
spells (their descriptions are `{{ }}` placeholders with empty `datavalues`), so
the values come from the LoL Wiki. `wikiKey -> Data Dragon id` is resolved by
matching the Wiki Chinese `disp_name` against `summoner.json`'s `name`, with an
explicit override table for the ambiguous standard spells (Flash, Ignite, Heal,
Smite, Barrier, Cleanse, Teleport, Ghost, Exhaust, Mark, Clarity, Recall). Only
rows that resolve are filled; the rest keep the defaults above -- no value is
ever invented.

### Wiki fetch vs. build

* `fetch` downloads both Wiki modules to `raw/<version>/<locale>/wiki/`, renders
  every `effect` through the Wiki parser (`action=parse`) and writes
  `cache/summoner_spells_wiki.json`. This is the only step that touches the Wiki.
* `build` never goes online for Wiki data: it reads the cached pack. A missing or
  corrupt cache degrades to an empty pack (all four columns become defaults) with
  a `[WARN]`, so an offline rebuild always succeeds.

Spell deep data is scoped **per ability**: the ETL matches each Data Dragon
spell `id` (script name, e.g. `KayleQ`, `DariusCleave`) against the
CommunityDragon BIN object path
`Characters/<Champion>/Spells/<Container>/<scriptName>`, so a spell only carries
its own `mSpellCalculations` / `DataValues` instead of the whole champion blob.

## Local caches

Two hand-maintained / pre-probed caches live under `cache/`. Both are read at
build time and, if missing or corrupt, **degrade gracefully** (the build never
aborts on bad local data).

| File | Purpose | Missing behaviour |
| --- | --- | --- |
| `cache/champion_prices.json` | Champion BE / RP prices keyed by Data Dragon id (`{"prices": {"Aatrox": {"be": 2400, "rp": 880}}}`). Transcribed from the LoL Wiki — neither Data Dragon nor CommunityDragon exposes prices. | Absent id -> `priceBe` / `priceRp` stay `0` (never invented). |
| `cache/skin_availability.json` | Skins that have their own splash art on the CDN (`{"available": ["Aatrox_0", ...]}`), probed once per data version. | Falls back to the legacy heuristic (`splashPath` non-empty). |
| `cache/summoner_spells_wiki.json` | Rendered Wiki summoner-spell pack (`{"spells": {"Flash": {"castLevel": 7, ..., "effect": "..."}}}`), produced by `fetch`. | Empty pack -> the four `summoner_spell` columns keep their defaults (`0`/`0`/`0`/`''`). |

`champion_skin` fields are now contract-complete:

* `name` — localized name from the Data Dragon deep champion JSON (`skins[].name`),
  aligned to the CommunityDragon row by `num` (fallback: CommunityDragon name).
* `localImage` / `splashUrl` / `loadingUrl` — constructed as
  `champion/loading/{id}_{num}.jpg` and the version-less Data Dragon CDN URLs.
* `hasImage` — membership test against `cache/skin_availability.json`.

## Jungle monsters (`monster`, schema v5)

The `monster` table holds the Summoner's-Rift jungle monsters (`sru_*`
codenames). It is sourced **only** from CommunityDragon:

* `game/data/characters/` directory listing -> enumerates the `sru_*`
  codenames (only the `sru_` family; the `sruap_*` turret units are ignored).
* `game/data/characters/{codename}/{codename}.bin.json` -> `CharacterRecords/
  Root` stats (`baseHPModifiable`, `baseDamageModifiable`, `unitTagsString`,
  `name`, ...).
* `game/{locdir}/data/menu/en_us/lol.stringtable.json` -> display names, where
  `locdir` is the **lower-cased** build locale (`zh_CN -> zh_cn`) plus `en_us`
  for `nameEn`. Note this is *not* the `default` spelling used by the v1 API
  (`CDRAGON_LOCALE_DIRS`).

**Inclusion rule.** A unit is kept when its tag string contains both `Monster`
and `Monster_Camp`, with one explicit include (`sru_horde_mini`, the Voidmites)
and two explicit excludes (`sru_jungle_companions`, `sru_dragon_ruined`) ->
**27 rows** for the current patch. `category` is derived with priority
`epic > large > medium > small`; `camp` is the first `Monster_<X>` tag that is
not a tier / `Camp` / `Buff` marker (`baron`, `dragon`, `blue`, `red`, ...).

**Degrades, never invents.** A missing number becomes `0`/`0.0`, a missing name
becomes `''`, a single failed BIN is skipped with a `[WARN]`, and a missing
source yields an empty section -- the build always completes.

**`fetch` vs. `build`.**

* `fetch` warms `raw/<version>/<locale>/cdragon/game/` with the directory
  listing, every `sru_*` BIN and both string tables (~32 MB each). This is the
  only step that goes online for monster data.
* `build` reads those cached files offline -- there is **no** intermediate
  `cache/monster_*.json`; the parse is cheap and deterministic.

**`icon` convention.** `icon` is a path **relative to the CommunityDragon
`game/` root** (e.g. `assets/characters/sru_baron/hud/baron_circle.png`), or
`''` when no unambiguous circle icon exists (`sru_atakhan`, `sru_bluemini2`,
`sru_krugminimini`). The Android client builds the URL as
`https://raw.communitydragon.org/{channel}/game/` + `icon`.

## Validation

```bash
# one-off: refresh the Wiki summoner-spell pack (online), then rebuild offline
python -m src.main fetch   --version 16.20 --locale zh_CN
python -m src.main build   --version 16.20 --locale zh_CN
python -m src.main inspect --db output/lol-<version>.db --champion Kayle
python -m src.main inspect --db output/lol-<version>.db --item 1001
python -m src.main inspect --db output/lol-<version>.db --monster sru_baron
python -m src.main stats   --db output/lol-<version>.db
python -m unittest discover -s tests
```

The milestone validates champion + spell + DataValue + GameCalculation parsing.
`stats` prints a row count per table so an empty load is obvious.
