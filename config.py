from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"
OUTPUT_DIR = ROOT / "output"

CDRAGON_BASE = "https://raw.communitydragon.org"
DDRAGON_BASE = "https://ddragon.leagueoflegends.com"

SCHEMA_VERSION = 5

# League of Legends Wiki (MediaWiki) -- authoritative numeric summoner-spell
# data (cooldown / level / range / charges / recharge / maps / effect) that
# neither Data Dragon nor CommunityDragon exposes. The English module is the
# source of truth for numbers; the zh-CN sandbox module supplies Chinese names
# and effect text. Both are rendered through the Wiki's own parser so the
# ``{{ }}`` templates expand exactly as the site shows them.
WIKI_API = "https://wiki.leagueoflegends.com/en-us/api.php"
WIKI_SPELLDATA_TITLE = "Module:SpellData/data"
WIKI_SPELLDATA_ZH_TITLE = (
    "Module:Sandbox/WordlessMeteor/SpellData/zh-CN/data"
)

# CommunityDragon client-data endpoints.
CDRAGON_V1 = (
    CDRAGON_BASE
    + "/{version}/plugins/rcp-be-lol-game-data/global/default/v1"
)
CDRAGON_GAME = CDRAGON_BASE + "/{version}/game"

# Per-champion client data (roles, playstyle, skins). Keyed by numeric key.
CDRAGON_CHAMPION = CDRAGON_V1 + "/champions/{key}.json"

# Per-champion game BIN data (spell calculations + data values).
CDRAGON_CHARACTER_BIN = (
    CDRAGON_GAME + "/data/characters/{champion}/{champion}.bin.json"
)

# Summoner's-Rift jungle monsters ("sru_*"). The directory listing enumerates
# the available codenames (the set is not known ahead of time), and each unit's
# stats live in ``{codename}/{codename}.bin.json`` -- same shape as champions.
CDRAGON_CHARACTERS_DIR = CDRAGON_GAME + "/data/characters/"

# Localized string tables (``{"entries": {key: value}, "version": 5}``) that map
# a character's localization key (``Root.name``) to its display name. ``locdir``
# is the *lower-cased* locale (``en_US -> en_us``); note this differs from
# ``CDRAGON_LOCALE_DIRS`` (``en_US -> default``) which is used for the v1 API.
CDRAGON_STRINGTABLE = (
    CDRAGON_GAME + "/{locdir}/data/menu/en_us/lol.stringtable.json"
)
CDRAGON_STRINGTABLE_LOCALE = "en_us"

# Localized CommunityDragon v1. Unlike the champion endpoints above (which stay
# on ``default`` so ``nameEn``/``titleEn`` remain English), runes and summoner
# spells are only useful to the client in the user's language, so they read from
# the localized directory.
CDRAGON_V1_LOCALIZED = (
    CDRAGON_BASE
    + "/{version}/plugins/rcp-be-lol-game-data/global/{locale}/v1"
)

# Runes ("perks") and summoner spells, including the client-side numeric
# tooltips (``@Token@`` placeholders) that Data Dragon does not carry.
CDRAGON_PERKS = CDRAGON_V1_LOCALIZED + "/perks.json"
CDRAGON_PERKSTYLES = CDRAGON_V1_LOCALIZED + "/perkstyles.json"
CDRAGON_SUMMONER_SPELLS = CDRAGON_V1_LOCALIZED + "/summoner-spells.json"

# Data Dragon locale -> CommunityDragon ``global/<dir>`` spelling.
# Anything not listed falls back to the lower-cased locale.
CDRAGON_LOCALE_DIRS = {
    "en_US": "default",
    "zh_CN": "zh_cn",
    "zh_TW": "zh_tw",
    "ko_KR": "ko_kr",
    "ja_JP": "ja_jp",
    "es_ES": "es_es",
    "fr_FR": "fr_fr",
    "de_DE": "de_de",
    "pt_BR": "pt_br",
    "ru_RU": "ru_ru",
    "tr_TR": "tr_tr",
    "pl_PL": "pl_pl",
}

# Data Dragon is used for localized user-facing base data.
DDRAGON_VERSION_URL = DDRAGON_BASE + "/api/versions.json"
DDRAGON_CHAMPION_LIST = (
    DDRAGON_BASE + "/cdn/{version}/data/{locale}/champion.json"
)
DDRAGON_CHAMPION = (
    DDRAGON_BASE + "/cdn/{version}/data/{locale}/champion/{champion}.json"
)
DDRAGON_ITEM = (
    DDRAGON_BASE + "/cdn/{version}/data/{locale}/item.json"
)
DDRAGON_SUMMONER = (
    DDRAGON_BASE + "/cdn/{version}/data/{locale}/summoner.json"
)
DDRAGON_RUNE = (
    DDRAGON_BASE + "/cdn/{version}/data/{locale}/runesReforged.json"
)
