import unittest

from src.parser.monster import (
    MONSTER_BUFF_CATALOG,
    MONSTER_EXCLUDE,
    MONSTER_EXTRA_INCLUDE,
    MONSTER_ICONS,
    classify,
    list_monster_codenames,
    monster_buff_row,
    monster_effect_keys,
    monster_row,
    official_body,
    parse_monster_buffs,
    parse_monsters,
    plain_text,
    resolve_effect,
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

    def test_effect_filled_from_enemy_tooltip(self):
        root = {
            "unitTagsString": BARON_TAGS,
            "name": "game_character_displayname_Baron",
        }
        entry = (
            "<titleLeft>纳什男爵</titleLeft>"
            "<subtitleLeft>史诗级野怪—团队增益</subtitleLeft>"
            "<mainText>击杀这个野怪会提供男爵之手。</mainText>"
        )
        zh = {
            "game_character_displayname_baron": "纳什男爵",
            "game_character_enemytooltip_baron": entry,
        }
        en = {
            "game_character_displayname_baron": "Baron Nashor",
            "game_character_enemytooltip_baron": "Killing this monster grants Hand of Baron.",
        }
        row = monster_row(
            "sru_baron", _bin_json("SRU_Baron", root), zh, en, "16.20"
        )
        # `<mainText>` only: the title/subtitle sections never leak into `effect`.
        self.assertEqual(row["effect"], "击杀这个野怪会提供男爵之手。")
        self.assertEqual(row["effectEn"], "Killing this monster grants Hand of Baron.")

    def test_effect_empty_when_no_source(self):
        root = {
            "unitTagsString": BARON_TAGS,
            "name": "game_character_displayname_Baron",
        }
        row = monster_row(
            "sru_baron", _bin_json("SRU_Baron", root), {}, {}, "16.20"
        )
        self.assertEqual(row["effect"], "")
        self.assertEqual(row["effectEn"], "")


class PlainTextTest(unittest.TestCase):
    def test_strips_nested_markup(self):
        raw = "<titleLeft><font color='#FFFFFF'>男爵之手</font></titleLeft>"
        self.assertEqual(plain_text(raw), "男爵之手")

    def test_empty(self):
        self.assertEqual(plain_text(""), "")


class OfficialBodyTest(unittest.TestCase):
    def test_prefers_main_text(self):
        raw = (
            "<titleLeft>炼狱亚龙</titleLeft>"
            "<mainText>强化攻击力和法术强度。</mainText>"
            "<postScriptLeft>来自：@SourceName@</postScriptLeft>"
        )
        self.assertEqual(official_body(raw), "强化攻击力和法术强度。")

    def test_falls_back_without_main_text(self):
        # Chemtech drake puts its body right after `<titleLeft>` (no mainText).
        raw = "<titleLeft>炼金科技巨龙</titleLeft><br>每层提供 10% 韧性。"
        body = official_body(raw)
        self.assertEqual(body, "<br>每层提供 10% 韧性。")

    def test_empty(self):
        self.assertEqual(official_body(""), "")


class MonsterEffectKeysTest(unittest.TestCase):
    def test_derives_both_families(self):
        keys = monster_effect_keys("game_character_displayname_SRUDragon_Hextech")
        self.assertEqual(
            keys,
            (
                "game_character_enemytooltip_srudragon_hextech",
                "game_character_description_srudragon_hextech",
            ),
        )

    def test_unexpected_key_shape(self):
        self.assertEqual(monster_effect_keys(""), ())
        self.assertEqual(monster_effect_keys("SomeOtherKey"), ())


class ResolveEffectTest(unittest.TestCase):
    def test_prefers_enemy_tooltip_then_description(self):
        name_key = "game_character_displayname_SRUDragon"
        only_description = {
            "game_character_description_srudragon": "<mainText>说明</mainText>",
        }
        self.assertEqual(resolve_effect(only_description, name_key), "说明")

        both = {
            "game_character_enemytooltip_srudragon": "<mainText>首选</mainText>",
            "game_character_description_srudragon": "<mainText>兜底</mainText>",
        }
        self.assertEqual(resolve_effect(both, name_key), "首选")

    def test_missing_degrades_to_empty(self):
        self.assertEqual(resolve_effect(None, "x"), "")
        self.assertEqual(resolve_effect({}, "game_character_displayname_Baron"), "")


class MonsterBuffCatalogTest(unittest.TestCase):
    def test_ids_unique_and_kinds_known(self):
        ids = [spec.id for spec in MONSTER_BUFF_CATALOG]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(
            {spec.kind for spec in MONSTER_BUFF_CATALOG}
            <= {"epic", "drake", "soul", "camp"}
        )

    def test_row_uses_title_left_for_name(self):
        spec = MONSTER_BUFF_CATALOG[0]  # baron_hand
        entries = {
            spec.description_key: (
                "<titleLeft><font color='#FFF'>男爵之手</font></titleLeft>"
                "<mainText>提升攻击力。</mainText>"
            )
        }
        row = monster_buff_row(spec, entries, {}, "16.20")
        self.assertEqual(row["name"], "男爵之手")
        self.assertEqual(row["description"], "提升攻击力。")
        self.assertEqual(row["kind"], spec.kind)
        self.assertEqual(row["camp"], spec.camp)
        self.assertEqual(row["nameEn"], "")

    def test_row_falls_back_to_name_key(self):
        # Dragon souls carry no `<titleLeft>`; the name comes from `*_name`.
        spec = next(s for s in MONSTER_BUFF_CATALOG if s.id == "soul_infernal")
        entries = {
            spec.description_key: "造成爆炸伤害。",
            spec.name_key: "炼狱龙魂",
        }
        row = monster_buff_row(spec, entries, {}, "16.20")
        self.assertEqual(row["name"], "炼狱龙魂")
        self.assertEqual(row["description"], "造成爆炸伤害。")

    def test_row_skipped_without_description(self):
        spec = MONSTER_BUFF_CATALOG[0]
        self.assertIsNone(monster_buff_row(spec, {}, {}, "16.20"))

    def test_parse_deterministic_and_skips_blanks(self):
        spec = MONSTER_BUFF_CATALOG[0]
        zh = {spec.description_key: "<mainText>效果</mainText>"}
        first = parse_monster_buffs(zh, {}, "16.20")
        second = parse_monster_buffs(zh, {}, "16.20")
        self.assertEqual(first, second)
        self.assertEqual([row["id"] for row in first], [spec.id])

    def test_parse_empty_table(self):
        self.assertEqual(parse_monster_buffs(None, None, "16.20"), [])


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
