import json
import tempfile
import unittest
from pathlib import Path

from src.db.schema import create_database
from src.parser.summoner import parse_summoner_spells
from src.parser.wiki_lua import LuaParseError, parse_lua
from src.parser.wiki_summoner import (
    build_wiki_summoner_pack,
    clean_rendered_html,
    load_wiki_summoner_pack,
    map_wiki_keys_to_ids,
    maps_to_csv,
    normalize_wiki_templates,
    resolve_summoner_id,
)


class LuaParserTest(unittest.TestCase):
    def test_scalars_and_nesting(self):
        text = """
        -- leading comment
        return {
            ["cooldown"] = "180",
            ["level"]    = 4,
            ratio = 0.0,
            ["flag"] = true,
            ["none"] = nil,
            ["maps"] = { ["sr"] = true, ["ar"] = false },
        }
        -- trailing comment
        """
        data = parse_lua(text)
        self.assertEqual(data["cooldown"], "180")
        self.assertEqual(data["level"], 4)
        self.assertEqual(data["ratio"], 0.0)
        self.assertIs(data["flag"], True)
        self.assertIsNone(data["none"])
        self.assertEqual(data["maps"], {"sr": True, "ar": False})

    def test_mixed_tabs_spaces_and_trailing_commas(self):
        text = 'return {\n\t["A"] = 1,\n        ["B"] = 2,\n    }'
        self.assertEqual(parse_lua(text), {"A": 1, "B": 2})

    def test_line_and_block_comments(self):
        text = """
        --[[ multi
             line {{ template }} comment ]]
        return { ["x"] = 1, -- inline
                 ["y"] = 2 }
        """
        self.assertEqual(parse_lua(text), {"x": 1, "y": 2})

    def test_string_escapes(self):
        data = parse_lua(r'return { ["k"] = "a\"b\\c\nd\te" }')
        self.assertEqual(data["k"], 'a"b\\c\nd\te')

    def test_numbers_int_float_and_negative(self):
        data = parse_lua('return { ["a"] = -3, ["b"] = 2.5, ["c"] = 1e3 }')
        self.assertEqual(data["a"], -3)
        self.assertEqual(data["b"], 2.5)
        self.assertEqual(data["c"], 1000.0)

    def test_bareword_values_are_kept(self):
        data = parse_lua('return { ["stealth"] = unknown }')
        self.assertEqual(data["stealth"], "unknown")

    def test_unterminated_table_raises(self):
        with self.assertRaises(LuaParseError):
            parse_lua('return { ["a"] = 1 ')


class RenderPostprocessTest(unittest.TestCase):
    def test_localizes_based_on_level(self):
        html = "<span>75 &#8211; 330 (based on level)</span>"
        self.assertEqual(clean_rendered_html(html), "75 – 330 （基于等级）")

    def test_localizes_distance_parenthetical(self):
        html = "0.5 &#8211; 5 (based on distance to target)"
        self.assertEqual(
            clean_rendered_html(html), "0.5 – 5 （基于与目标的距离）"
        )

    def test_decodes_entities_and_collapses_whitespace(self):
        html = "造成&#160;600 真实伤害 &amp;  更多"
        # &#160; -> space, &amp; -> &, runs of spaces collapse to one.
        self.assertEqual(clean_rendered_html(html), "造成 600 真实伤害 & 更多")

    def test_strips_tags_and_keeps_text(self):
        html = "<span class='x' style='y'>护盾</span><small>2</small>.<small>5</small>"
        self.assertEqual(clean_rendered_html(html), "护盾2.5")

    def test_empty_input(self):
        self.assertEqual(clean_rendered_html(""), "")


class NormalizeTemplatesTest(unittest.TestCase):
    def test_single_brace_template_is_repaired(self):
        broken = "朝着{tt|目标位置|你的指针所停的区域}}（瞬间）传送"
        self.assertEqual(
            normalize_wiki_templates(broken),
            "朝着{{tt|目标位置|你的指针所停的区域}}（瞬间）传送",
        )

    def test_double_brace_template_untouched(self):
        good = "朝着{{tt|目标位置|你的指针所停的区域}}（瞬间）传送"
        self.assertEqual(normalize_wiki_templates(good), good)

    def test_plain_text_untouched(self):
        self.assertEqual(normalize_wiki_templates("造成600真实伤害。"), "造成600真实伤害。")
        self.assertEqual(normalize_wiki_templates(""), "")

    def test_normalized_before_expansion(self):
        # The single-brace typo is repaired, then ``{{tt|A|B}}`` -> A.
        en = 'return { ["Flash"] = { ["effect"] = "x" } }'
        zh = (
            'return { ["Flash"] = { ["disp_name"]="闪现", '
            '["effect"]="朝着{tt|目标位置|你的指针所停的区域}}走" } }'
        )
        pack = build_wiki_summoner_pack(en, zh)
        self.assertIn("目标位置", pack["Flash"]["effect"])
        self.assertNotIn("{", pack["Flash"]["effect"])


class MapsCsvTest(unittest.TestCase):
    def test_canonical_order_and_truthy(self):
        raw = {"sr": True, "ar": False, "ha": True, "nb": "unknown"}
        self.assertEqual(maps_to_csv(raw), "sr,ha,nb")

    def test_non_dict_is_empty(self):
        self.assertEqual(maps_to_csv(None), "")
        self.assertEqual(maps_to_csv("sr"), "")


class BuildPackTest(unittest.TestCase):
    EN = """
    return {
      ["Smite"] = {
        ["cooldown"] = "15", ["recharge"] = "90", ["charges"] = "2",
        ["level"] = "3",
        ["maps"] = { ["sr"] = true, ["ar"] = false },
        ["effect"] = "Deals 600 true damage.",
      },
    }
    """
    ZH = """
    return {
      ["Smite"] = {
        ["disp_name"] = "惩戒",
        ["cooldown"] = "15", ["recharge"] = "90", ["charges"] = "2",
        ["level"] = "3",
        ["effect"] = "造成600真实伤害。",
      },
      ["OnlyZh"] = { ["disp_name"] = "仅中文" },
    }
    """

    def test_merge_prefers_english_numbers_and_chinese_text(self):
        pack = build_wiki_summoner_pack(self.EN, self.ZH)
        smite = pack["Smite"]
        self.assertEqual(smite["cooldown"], 15)
        self.assertEqual(smite["charges"], 2)
        self.assertEqual(smite["recharge"], 90)
        self.assertEqual(smite["castLevel"], 3)
        self.assertEqual(smite["dispName"], "惩戒")
        self.assertEqual(smite["nameEn"], "Smite")
        self.assertEqual(smite["maps"], "sr")
        # Effect expanded offline from the zh text.
        self.assertEqual(smite["effect"], "造成600真实伤害。")
        # zh-only entries still surface (dispName fallback to the key).
        self.assertIn("OnlyZh", pack)
        self.assertEqual(pack["OnlyZh"]["dispName"], "仅中文")

    def test_numeric_mismatch_keeps_english(self):
        en = 'return { ["Flash"] = { ["cooldown"] = "300", ["level"] = "7" } }'
        zh = 'return { ["Flash"] = { ["disp_name"]="闪现", ["cooldown"]="999", ["level"]="7" } }'
        pack = build_wiki_summoner_pack(en, zh)
        self.assertEqual(pack["Flash"]["cooldown"], 300)

    def test_effect_template_expanded_offline(self):
        zh = (
            'return { ["Smite"] = { ["disp_name"]="惩戒", '
            '["effect"]="造成{{pp|100 to 600}}真实伤害。" } }'
        )
        pack = build_wiki_summoner_pack("", zh)
        self.assertEqual(
            pack["Smite"]["effect"], "造成100 – 600 （基于等级）真实伤害。"
        )


class IdMappingTest(unittest.TestCase):
    def setUp(self):
        self.summoner_file = {
            "data": {
                "SummonerFlash": {"key": "4", "name": "闪现"},
                "SummonerFlash_Jade": {"key": "74", "name": "闪现"},
                "SummonerCherryFlash": {"key": "2202", "name": "闪现"},
                "SummonerDot": {"key": "14", "name": "引燃"},
                "SummonerSnowball": {"key": "32", "name": "标记"},
                "SummonerSnowURFSnowball_Mark": {"key": "39", "name": "标记"},
            }
        }

    def test_ambiguous_name_resolved_by_override(self):
        pack = {
            "Flash": {"dispName": "闪现"},
            "Mark": {"dispName": "标记"},
        }
        mapping = map_wiki_keys_to_ids(pack, self.summoner_file)
        self.assertIn("SummonerFlash", mapping)
        # The base id wins over the _Jade / SnowURF derivatives.
        self.assertIn("SummonerSnowball", mapping)
        self.assertNotIn("SummonerSnowURFSnowball_Mark", mapping)

    def test_override_target_missing_is_dropped(self):
        # SummonerRecall is absent from DDragon -> Recall cannot be mapped.
        pack = {"Recall": {"dispName": "回城"}}
        self.assertEqual(map_wiki_keys_to_ids(pack, self.summoner_file), {})

    def test_resolve_returns_none_for_unknown(self):
        by_name = {"闪现": ["SummonerFlash"]}
        self.assertIsNone(
            resolve_summoner_id("Nope", "不存在", by_name, {"SummonerFlash"})
        )


class SummonerParseWithWikiTest(unittest.TestCase):
    def test_unmapped_row_keeps_defaults(self):
        summoner_file = {
            "data": {
                "SummonerFlash": {
                    "key": "4", "name": "闪现", "description": "d",
                    "tooltip": "t", "cooldown": [300], "cooldownBurn": "300",
                    "costBurn": "0", "rangeBurn": "400",
                    "modes": ["CLASSIC"], "image": {"full": "SummonerFlash.png"},
                },
                "SummonerUnknown": {
                    "key": "99", "name": "无从映射", "description": "d",
                    "tooltip": "t", "cooldown": [10], "cooldownBurn": "10",
                    "costBurn": "0", "rangeBurn": "0",
                    "modes": ["CLASSIC"], "image": {"full": "u.png"},
                },
            }
        }
        wiki_pack = {"Flash": {"dispName": "闪现", "castLevel": 7, "charges": 0,
                               "recharge": 0, "effect": "闪现效果"}}
        rows = {r["id"]: r for r in parse_summoner_spells(summoner_file, wiki_pack)}
        flash = rows["SummonerFlash"]
        self.assertEqual(flash["castLevel"], 7)
        self.assertEqual(flash["effect"], "闪现效果")
        unknown = rows["SummonerUnknown"]
        self.assertEqual(
            (unknown["castLevel"], unknown["charges"], unknown["recharge"],
             unknown["effect"]),
            (0, 0, 0, ""),
        )

    def test_no_pack_keeps_defaults(self):
        summoner_file = {
            "data": {
                "SummonerFlash": {
                    "key": "4", "name": "闪现", "cooldown": [300],
                    "image": {"full": "SummonerFlash.png"},
                }
            }
        }
        rows = parse_summoner_spells(summoner_file)
        self.assertEqual(rows[0]["castLevel"], 0)
        self.assertEqual(rows[0]["effect"], "")


class WikiCacheTest(unittest.TestCase):
    def test_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "w.json"
            cache.write_text(
                json.dumps({"spells": {"Flash": {"dispName": "闪现"}}}),
                encoding="utf-8",
            )
            self.assertEqual(
                load_wiki_summoner_pack(cache)["Flash"]["dispName"], "闪现"
            )

    def test_cache_missing_degrades(self):
        self.assertEqual(
            load_wiki_summoner_pack(Path("does-not-exist-wiki.json")), {}
        )

    def test_cache_corrupt_degrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "w.json"
            cache.write_text("{ not json", encoding="utf-8")
            self.assertEqual(load_wiki_summoner_pack(cache), {})

    def test_cache_malformed_shape_degrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "w.json"
            cache.write_text(json.dumps({"spells": "oops"}), encoding="utf-8")
            self.assertEqual(load_wiki_summoner_pack(cache), {})


class SchemaV4Test(unittest.TestCase):
    def test_summoner_spell_has_new_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            connection = create_database(str(Path(tmp) / "t.db"))
            columns = [
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(summoner_spell)"
                )
            ]
            connection.close()
        for column in ("castLevel", "charges", "recharge", "effect"):
            self.assertIn(column, columns)
        # New columns must sit before ``icon`` (frozen interface).
        self.assertLess(columns.index("effect"), columns.index("icon"))


if __name__ == "__main__":
    unittest.main()
