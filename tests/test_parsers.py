import unittest

from src.parser.bin_scope import scope_spell_objects
from src.parser.base_stats import BIN_STAT_MAP, apply_missing_stats, bin_base_stats
from src.parser.item import parse_items
from src.parser.rune import parse_runes
from src.parser.summoner import parse_summoner_spells
from src.pipeline import enrich_spell_from_bin


class ItemParserTest(unittest.TestCase):
    def test_parse_item_fields(self):
        item_file = {
            "data": {
                "1001": {
                    "name": "鞋子",
                    "plaintext": "略微提升移动速度",
                    "description": "<mainText>25 移动速度</mainText>",
                    "gold": {
                        "base": 300,
                        "total": 300,
                        "sell": 210,
                        "purchasable": True,
                    },
                    "tags": ["Boots"],
                    "maps": {"11": True},
                    "image": {"full": "1001.png"},
                    "from": ["1000"],
                    "into": ["3005", "3047"],
                    "stats": {"FlatMovementSpeedMod": 25},
                    "depth": 0,
                }
            }
        }
        items = parse_items(item_file)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], 1001)
        self.assertEqual(item["goldTotal"], 300)
        self.assertEqual(item["purchasable"], 1)
        self.assertEqual(item["intoItems"], "3005,3047")
        self.assertEqual(item["icon"], "img/item/1001.png")
        self.assertEqual(item["maps"], '{"11":true}')


class SummonerParserTest(unittest.TestCase):
    def test_parse_summoner(self):
        data = {
            "data": {
                "SummonerFlash": {
                    "key": "4",
                    "name": "闪现",
                    "description": "向目标方向闪现。",
                    "tooltip": "闪现到目标位置。",
                    "cooldown": [300],
                    "cooldownBurn": "300",
                    "costBurn": "0",
                    "rangeBurn": "400",
                    "modes": ["CLASSIC"],
                    "image": {"full": "SummonerFlash.png"},
                }
            }
        }
        spells = parse_summoner_spells(data)
        self.assertEqual(len(spells), 1)
        self.assertEqual(spells[0]["id"], "SummonerFlash")
        self.assertEqual(spells[0]["key"], 4)
        self.assertEqual(spells[0]["cooldown"], 300)
        self.assertEqual(spells[0]["icon"], "img/spell/SummonerFlash.png")


class RuneParserTest(unittest.TestCase):
    def test_parse_runes(self):
        runes_file = [
            {
                "id": 8100,
                "key": "Domination",
                "name": "主宰",
                "icon": "perk-images/Styles/7200_Domination.png",
                "slots": [
                    {
                        "runes": [
                            {
                                "id": 8112,
                                "key": "Electrocute",
                                "name": "电刑",
                                "shortDesc": "短描述",
                                "longDesc": "长描述",
                                "icon": "perk-images/Electrocute.png",
                            }
                        ]
                    }
                ],
            }
        ]
        trees, runes = parse_runes(runes_file)
        self.assertEqual(len(trees), 1)
        self.assertEqual(trees[0]["id"], 8100)
        self.assertEqual(len(runes), 1)
        self.assertEqual(runes[0]["treeId"], 8100)
        self.assertEqual(runes[0]["slot"], 0)


class BinScopeTest(unittest.TestCase):
    def setUp(self):
        self.bin_json = {
            "Characters/Test/Spells/TestQAbility/TestQ": {
                "mSpell": {
                    "mSpellCalculations": {"QDamage": {"mFormulaParts": []}},
                    "DataValues": [{"name": "QValue", "values": [1, 2]}],
                }
            },
            "Characters/Test/Spells/TestWAbility/TestW": {
                "mSpell": {
                    "mSpellCalculations": {"WShield": {"mFormulaParts": []}},
                    "DataValues": [{"name": "WValue", "values": [3, 4]}],
                }
            },
            "Characters/Test/Spells/TestPassiveAbility/TestPassive": {
                "mSpell": {
                    "mSpellCalculations": {"PStack": {"mFormulaParts": []}},
                    "DataValues": [{"name": "PValue", "values": [5]}],
                }
            },
        }

    def test_scope_by_script_id(self):
        scoped = scope_spell_objects(self.bin_json, "Test", "TestQ", "Q")
        self.assertEqual(len(scoped), 1)
        values = scoped[0]["mSpell"]["DataValues"]
        self.assertEqual(values[0]["name"], "QValue")

    def test_scope_falls_back_to_container_for_passive(self):
        scoped = scope_spell_objects(self.bin_json, "Test", "", "P")
        self.assertEqual(len(scoped), 1)
        self.assertEqual(
            scoped[0]["mSpell"]["DataValues"][0]["name"], "PValue"
        )

    def test_scope_matches_p_ability_container_case_insensitively(self):
        bin_json = {
            "Characters/Tester/Spells/TesterPAbility/TesterP": {
                "mSpell": {
                    "mSpellCalculations": {"PDamage": {}},
                    "DataValues": [{"name": "PVal", "values": [1]}],
                }
            }
        }
        # Champion casing differs from the BIN object path ("Tester" vs id).
        scoped = scope_spell_objects(bin_json, "Tester", "", "P")
        self.assertEqual(len(scoped), 1)
        self.assertEqual(scoped[0]["mSpell"]["DataValues"][0]["name"], "PVal")

    def test_scope_falls_back_to_icon_stem(self):
        bin_json = {
            "Characters/Odd/Spells/OddHemoMarkerAbility/OddHemo": {
                "mSpell": {
                    "mImgIconName": [
                        "ASSETS/Characters/Odd/HUD/Icons2D/Odd_Hemorrhage.dds"
                    ],
                    "mSpellCalculations": {"HemoDamage": {}},
                    "DataValues": [{"name": "HemoVal", "values": [9]}],
                }
            }
        }
        scoped = scope_spell_objects(
            bin_json, "Odd", "", "P", ("Odd_Hemorrhage.png",)
        )
        self.assertEqual(len(scoped), 1)
        self.assertEqual(scoped[0]["mSpell"]["DataValues"][0]["name"], "HemoVal")

    def test_each_slot_is_isolated(self):
        q = {"id": "TestQ", "slot": "Q"}
        w = {"id": "TestW", "slot": "W"}
        self.assertTrue(enrich_spell_from_bin(q, self.bin_json, "Test"))
        self.assertTrue(enrich_spell_from_bin(w, self.bin_json, "Test"))
        self.assertIn("QDamage", q["calculationJson"])
        self.assertNotIn("WShield", q["calculationJson"])
        self.assertIn("WShield", w["calculationJson"])
        self.assertNotIn("QDamage", w["calculationJson"])


class BaseStatsTest(unittest.TestCase):
    def test_reads_modifiable_floats(self):
        bin_json = {
            "Characters/Darius/CharacterRecords/Root": {
                "baseDamageModifiable": {
                    "baseValue": 64.0,
                    "__type": "ModifiableFloat",
                },
                "damagePerLevelModifiable": {
                    "baseValue": 5.0,
                    "__type": "ModifiableFloat",
                },
                "baseStaticHPRegenModifiable": {
                    "baseValue": 2.0,
                    "__type": "ModifiableFloat",
                },
            }
        }
        stats = bin_base_stats(bin_json, "Darius")
        self.assertEqual(stats["attackDamage"], 64.0)
        self.assertEqual(stats["attackDamagePerLevel"], 5.0)
        # hpRegen is excluded on purpose (unit mismatch: per-second vs per-5s).
        self.assertNotIn("hpRegen", stats)

    def test_apply_only_fills_zeroed_fields(self):
        entity = {"attackDamage": 64.0, "attackDamagePerLevel": 0.0}
        apply_missing_stats(entity, {"attackDamage": 999.0, "attackDamagePerLevel": 5.0})
        self.assertEqual(entity["attackDamage"], 64.0)  # kept
        self.assertEqual(entity["attackDamagePerLevel"], 5.0)  # backfilled

    def test_hp_regen_never_sourced_from_bin(self):
        self.assertNotIn("hpRegen", BIN_STAT_MAP.values())
        self.assertNotIn("hpRegenPerLevel", BIN_STAT_MAP.values())


if __name__ == "__main__":
    unittest.main()
