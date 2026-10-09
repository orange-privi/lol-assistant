import unittest

from src.parser.monster import (
    MONSTER_EXCLUDE,
    MONSTER_EXTRA_INCLUDE,
    MONSTER_ICONS,
    classify,
    list_monster_codenames,
    monster_row,
    parse_monsters,
    resolve_name,
    should_include,
)

BARON_TAGS = (
    "Monster | Monster_Epic | Special_Void | Monster_Camp | Monster_Baron"
)


def _bin_json(code: str, root: dict) -> dict:
    """Wrap a root object the way CommunityDragon lays out a BIN file."""
    return {f"Characters/{code}/CharacterRecords/Root": root}


class ListCodenamesTest(unittest.TestCase):
    def test_only_sru_and_sorted_unique(self):
        html = (
            '<a href="sru_dragon/">dragon</a>'
            '<a href="aatrox/">aatrox</a>'
            '<a href="sruap_chaosnexus/">turret</a>'
            '<a href="sru_baron/">baron</a>'
            '<a href="sru_dragon/">dragon</a>'
        )
        self.assertEqual(
            list_monster_codenames(html), ["sru_baron", "sru_dragon"]
        )

    def test_empty_input(self):
        self.assertEqual(list_monster_codenames(""), [])


class ShouldIncludeTest(unittest.TestCase):
    def test_positive_monster_camp(self):
        self.assertTrue(should_include(BARON_TAGS, "sru_baron"))

    def test_negative_minion(self):
        self.assertFalse(should_include("Minion | Minion_Lane", "sru_minion"))

    def test_extra_include(self):
        self.assertIn("sru_horde_mini", MONSTER_EXTRA_INCLUDE)
        self.assertTrue(
            should_include("Monster | Monster_Horde", "sru_horde_mini")
        )

    def test_explicit_exclude(self):
        self.assertIn("sru_jungle_companions", MONSTER_EXCLUDE)
        self.assertFalse(
            should_include(
                "Monster | Monster_Camp | Monster_Jungle",
                "sru_jungle_companions",
            )
        )


class ClassifyTest(unittest.TestCase):
    def test_tier_priority_epic_wins(self):
        tags = "Monster | Monster_Large | Monster_Epic | Monster_Camp | Monster_Baron"
        self.assertEqual(classify(tags), ("epic", "baron"))

    def test_buff_token_ignored(self):
        tags = "Monster | Monster_Large | Monster_Camp | Monster_Red | Monster_Buff"
        self.assertEqual(classify(tags), ("large", "red"))

    def test_fallback(self):
        self.assertEqual(classify(""), ("small", ""))
        self.assertEqual(classify("Totally | Unknown"), ("small", ""))


class ResolveNameTest(unittest.TestCase):
    def test_lookup_is_case_insensitive(self):
        entries = {"game_character_displayname_baron": "纳什男爵"}
        self.assertEqual(
            resolve_name(entries, "game_character_displayname_Baron"),
            "纳什男爵",
        )

    def test_missing_key_or_table(self):
        self.assertEqual(resolve_name(None, "some_key"), "")
        self.assertEqual(resolve_name({}, "some_key"), "")
        self.assertEqual(resolve_name({"a": "b"}, ""), "")


class MonsterRowTest(unittest.TestCase):
    def test_field_mapping(self):
        root = {
            "unitTagsString": BARON_TAGS,
            "name": "game_character_displayname_Baron",
            "baseHPModifiable": {"baseValue": 16300.0},
            "hpPerLevelModifiable": {"baseValue": 170.0},
            "baseDamageModifiable": {"baseValue": 175.0},
            "damagePerLevelModifiable": {"baseValue": 20.0},
            "baseArmorModifiable": {"baseValue": 34.0},
            "armorPerLevelModifiable": {"baseValue": 8.0},
            "baseMR": {"baseValue": 32.0},
            "mrPerLevel": {"baseValue": 4.0},
            "baseMoveSpeedModifiable": {"baseValue": 300.0},
            "attackSpeedModifiable": {"baseValue": 0.625},
            "attackRangeModifiable": {"baseValue": 900.0},
            "goldGivenOnDeath": 100.0,
            "globalGoldGivenOnDeath": 150.0,
            "expGivenOnDeath": 0.0,
            "globalExpGivenOnDeath": 650.0,
        }
        zh = {"game_character_displayname_baron": "纳什男爵"}
        en = {"game_character_displayname_baron": "Baron Nashor"}
        row = monster_row(
            "sru_baron", _bin_json("SRU_Baron", root), zh, en, "16.20"
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "sru_baron")
        self.assertEqual(row["name"], "纳什男爵")
        self.assertEqual(row["nameEn"], "Baron Nashor")
        self.assertEqual(row["category"], "epic")
        self.assertEqual(row["camp"], "baron")
        self.assertEqual(row["hp"], 16300.0)
        self.assertEqual(row["attackDamage"], 175.0)
        self.assertEqual(row["magicResist"], 32.0)
        self.assertEqual(row["attackRange"], 900.0)
        self.assertEqual(row["goldGiven"], 100)
        self.assertEqual(row["goldGivenTotal"], 150)
        self.assertEqual(row["expGiven"], 0)
        self.assertEqual(row["expGivenTotal"], 650)
        self.assertEqual(row["icon"], MONSTER_ICONS["sru_baron"])
        self.assertEqual(row["dataVersion"], "16.20")

    def test_missing_numbers_default_to_zero(self):
        # Gromp has no per-level growth fields (design doc 1.1).
        root = {
            "unitTagsString": "Monster | Monster_Large | Monster_Camp | Monster_Gromp",
            "name": "game_character_displayname_Gromp",
            "baseHPModifiable": {"baseValue": 1800.0},
            "baseDamageModifiable": {"baseValue": 80.0},
            "baseArmorModifiable": {"baseValue": 20.0},
            "baseMR": {"baseValue": 20.0},
            "baseMoveSpeedModifiable": {"baseValue": 330.0},
            "attackSpeedModifiable": {"baseValue": 0.6},
            "attackRangeModifiable": {"baseValue": 175.0},
        }
        row = monster_row("sru_gromp", _bin_json("SRU_Gromp", root), {}, {}, "16.20")
        self.assertIsNotNone(row)
        self.assertEqual(row["hpPerLevel"], 0.0)
        self.assertEqual(row["attackDamagePerLevel"], 0.0)
        self.assertEqual(row["armorPerLevel"], 0.0)
        self.assertEqual(row["magicResistPerLevel"], 0.0)
        self.assertEqual(row["goldGiven"], 0)

    def test_non_included_returns_none(self):
        root = {
            "unitTagsString": "Minion | Minion_Lane",
            "name": "game_character_displayname_Minion",
        }
        self.assertIsNone(
            monster_row("sru_minion", _bin_json("SRU_Minion", root), {}, {}, "16.20")
        )

    def test_missing_root_returns_none(self):
        self.assertIsNone(monster_row("sru_baron", None, {}, {}, "16.20"))
        self.assertIsNone(monster_row("sru_baron", {}, {}, {}, "16.20"))


class ParseMonstersTest(unittest.TestCase):
    def _bins(self):
        baron = _bin_json(
            "SRU_Baron",
            {
                "unitTagsString": BARON_TAGS,
                "name": "game_character_displayname_Baron",
                "baseHPModifiable": {"baseValue": 16300.0},
            },
        )
        gromp = _bin_json(
            "SRU_Gromp",
            {
                "unitTagsString": "Monster | Monster_Large | Monster_Camp | Monster_Gromp",
                "name": "game_character_displayname_Gromp",
                "baseHPModifiable": {"baseValue": 1800.0},
            },
        )
        return {
            "sru_baron": baron,
            "sru_gromp": gromp,
            "sru_broken": None,
        }

    def test_deterministic(self):
        codenames = ["sru_baron", "sru_broken", "sru_gromp"]
        first = parse_monsters(codenames, self._bins(), {}, {}, "16.20")
        second = parse_monsters(codenames, self._bins(), {}, {}, "16.20")
        self.assertEqual(first, second)
        self.assertEqual([row["id"] for row in first], ["sru_baron", "sru_gromp"])

    def test_single_failure_skipped(self):
        codenames = ["sru_baron", "sru_broken", "sru_gromp"]
        rows = parse_monsters(codenames, self._bins(), {}, {}, "16.20")
        ids = [row["id"] for row in rows]
        self.assertNotIn("sru_broken", ids)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
