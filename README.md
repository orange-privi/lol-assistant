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
SQLite (`lol-<version>.db`, schema v7)
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
| `champion_spell` | Data Dragon + CommunityDragon BIN + client string table | per-slot calculations / data values; `tooltipRendered` carries official client text where Data Dragon cannot fill the numbers |
| `champion_skin` | CommunityDragon v1 + Data Dragon | localized name, constructed `localImage` / `splashUrl` / `loadingUrl`, probed `hasImage` |
| `item` | Data Dragon `item.json` | gold, stats, build paths |
| `summoner_spell` | Data Dragon `summoner.json` + LoL Wiki | cooldown / cost / modes + Wiki numbers (`castLevel`, `charges`, `recharge`, `effect`) |
| `rune_tree`, `rune` | Data Dragon `runesReforged.json` | |
| `monster` | CommunityDragon `game/data/characters/` BIN + string tables | Summoner's-Rift jungle monsters (`sru_*`); stats, `category`/`camp`, localized name, icon path, `effect`/`effectEn` (in-game enemy-info / kill-effect text, schema v7) |
| `monster_buff` | CommunityDragon string tables | Reward buffs (Hand of Baron, elemental drakes, dragon souls, blue/red crest …) with localized name + description (schema v7) |

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

## `champion_spell.tooltipRendered` (schema v6)

Some abilities ship no usable numbers. Data Dragon's **passive** (slot `P`) is a
single numberless prose sentence (`孙悟空在与英雄或野怪战斗时，会获得可叠加的护甲和最大生命值回复。`),
so a client that wants to show the actual values has nowhere to read them from
except `dataValuesJson` -- which holds **engine-internal identifiers**
(`CombatDuration`, `StackMultiplier`, `HealthPercentPer5`, ...). The League
client never publishes a `field name -> localized label` dictionary, so those
cannot be relabelled locally. That is the "数值没归一化" symptom.

The official *localized text with the values in place* does exist, in the client
string table the ETL already downloads for monster names:

```text
raw/<version>/<locale>/cdragon/game/stringtable/<locdir>.lol.stringtable.json
```

`tooltipRendered` is that text. Three string-table families are indexed
(`src/parser/spelltext.py`), in explicit priority order -- explicit because the
table is alphabetical and `game_buff_tooltip_*` would otherwise be read first:

| Priority | Key family | Notes |
| --- | --- | --- |
| 0 | `spell_<script>_tooltip` | bare ability body |
| 1 | `generatedtip_(passive\|spell)_<script>_tooltip` | body inside `<mainText>`, name inside `<titleLeft>` |
| 2 | `game_(buff\|spell)_tooltip_<script>` | lowest: often a *unit-state* aura text |

Lookup is by **script name first** (the leaf of the CommunityDragon BIN object
path) and by **localized ability name second**, which absorbs patch-to-patch
script renames (`AatroxPassive` <-> `AatroxP`).

**Two gates decide whether the column is filled.** Both exist so that a row
keeps *today's* behaviour whenever the official text adds nothing:

1. **Only when Data Dragon cannot fill the numbers.** Its Q/W/E/R tooltips carry
   `{{ token }}` placeholders that the client already renders; those rows are
   left `''`. Widening this gate is one line in `render_spell_text`, but it would
   replace working tooltips with a second body to maintain.
2. **Only when the text carries a token this row has a value for.** Much of the
   candidate text is prose with no `@token@` (or only internal indices like
   `@f1@`, or dotted cross-spell refs such as
   `@spell.CaitlynW:HeadshotBonusDamage@`). Storing those would swap a clean
   sentence for an unfillable one -- and some read as a unit *state*
   (`这个单位被击晕了。`). Leaving `''` there is the correct answer.

**Placeholders and markup are preserved.** The syntax is `@Name@` /
`@Name*100@` (not Data Dragon's `{{ }}`), and client markup (`<scaleArmor>`,
`<keywordMajor>`, `<healing>`, ...) is kept verbatim -- it is the only source of
colourisation in the client. Only pure decoration is removed: `{{ }}` template
includes, `%i:icon%` markers, the empty tag pairs those leave behind (e.g.
`<spellName></spellName>`), and HTML entities. **Rendering is the client's
job** -- the Android side already has a tested `{{ }}`/formula interpreter
(`SpellNumbers`).

**Degrades, never invents.** A missing or corrupt string table makes the index
unusable and every `tooltipRendered` stays `''`, with a `[WARN]`; the build
still completes. An older data pack simply lacks the column, and the Android
importer treats a missing column as `''` (see `SourceDb`).

**Coverage on 16.20 / `zh_CN`** (865 `champion_spell` rows): **155 filled, 710
empty**, and every filled row is a passive --

| Slot | Filled | Empty |
| --- | --- | --- |
| `P` | 155 | 18 |
| `Q` / `W` / `E` / `R` | 0 | 173 each |

The 710 empty rows are the Q/W/E/R tooltips Data Dragon already renders (gate 1)
plus 18 passives whose official text carries no token the row has a value for
(gate 2). An audit over all 155 filled rows finds **zero** `{{ }}`, `%i:`,
empty-tag-pair or `@@` residue.

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

## Jungle monsters (`monster`, schema v5; effect since v7)

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

### Kill-effect text and the reward-buff catalogue (schema v7)

Two gaps are filled from data the ETL already caches — the client string table
(`raw/<version>/<locale>/cdragon/game/stringtable/<locdir>.lol.stringtable.json`)
— never a new source.

**`monster.effect` / `effectEn`** — the in-game *enemy-info* prose, which is
where the kill reward is spelled out. The keys are **derived, not curated**:
`Root.name` (`game_character_displayname_Baron`) has its prefix swapped for
`game_character_enemytooltip_` (fallback: `game_character_description_` — the
Hextech Drake only ships the latter), lower-cased. Only `<mainText>` is kept, so
the surrounding `titleLeft` / `subtitle` sections (name, respawn timer) do not
repeat the monster name.

Coverage on 16.20 / `zh_CN`: **22 of 27 filled**. The five blanks are exactly the
units whose client data carries no such key — Atakhan (removed in 26.1), the
Chemtech Drake, the Voidgrubs (camp and Voidmites) and the Mini Krug — and each
stays `''` rather than anything invented.

**`monster_buff`** — a curated catalogue of the reward buffs granted by active
jungle monsters: Hand of Baron, Aspect of the Dragon (Elder), the Herald's
Glimpse of the Void, the Voidgrubs' two buffs, the six elemental-drake buffs,
the six dragon souls, and the blue/red crests (**19 rows**). No machine-readable
field links a buff to its monster, so `MONSTER_BUFF_CATALOG` in
`src/parser/monster.py` fixes the source keys and the granting `camp` explicitly
— the same approach as `MONSTER_ICONS`. The text itself is pulled from the
string-table key, so no wording is transcribed by hand.

Both columns keep their client markup (`<font>`, `<healing>`, `<br>`, …) and
their `@Token@` / `@Spell.X:Y@` placeholders, exactly like
`champion_spell.tooltipRendered` — rendering is the client's job. A buff row
whose description does not resolve is skipped (an empty menu entry carries
nothing), and a missing string table degrades every column to `''` with a
`[WARN]`.

Notes and non-goals:

* **Krug splitting has no current text.** The 16.20 `sru_krug` enemy-info reads
  only `击败这个野怪会回复少量的法力值和生命值。`; the "splits into two Krugs"
  wording exists only in the 2015 key `..._enemytooltip_s2015_srukrug`, and the
  split itself is a *spell* (`SpawnMiniKrug_Mis`), not prose. Nothing is
  invented to cover it.
* **No icon column.** CommunityDragon has no `game/data/buffs/`, and the
  catalogue's long / cross-spell placeholders cannot be resolved offline, so the
  buff table carries text only.
* **Atakhan is excluded** because it is no longer an active monster (removed in
  26.1); its 2025 reward buffs are deliberately absent.

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

`tests/test_spelltext.py` covers the string-table index with verbatim 16.20
`zh_cn` fixtures: cleaning (template refs / icon markers / empty tag pairs /
entities), token extraction, the three-family priority order, the name reverse
lookup, and both `render_spell_text` gates. It also asserts that no rendered row
keeps a `{{ }}`, `%i:`, empty-tag-pair or `@@` residue.
