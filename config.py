from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"
OUTPUT_DIR = ROOT / "output"

CDRAGON_BASE = "https://raw.communitydragon.org"
DDRAGON_BASE = "https://ddragon.leagueoflegends.com"

SCHEMA_VERSION = 3

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
