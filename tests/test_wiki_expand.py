import unittest

from src.parser.wiki_expand import expand_wikitext, unknown_templates


class GoldenTest(unittest.TestCase):
    """The three strings the Wiki renderer produced in a previous round are the
    byte-for-byte acceptance baseline for the offline expander."""

    def test_blasting_smite(self):
        source = (
            "对目标中型和大型[[monster|野怪]]、敌方[[minion|小兵]]或"
            "[[Champion summoned units|英雄召唤物]]造成"
            "{{as|{{pp|390;410;430;450;480;510;540;570;600;640;680;720;760;"
            "800;850;900;950;1000|formula=370真实伤害{{plus}}20在1～4级、"
            "30在5～9级、40在10～14级、50在15～18级}}"
            "{{sti|true damage|真实伤害}}}}。"
        )
        expected = (
            "对目标中型和大型野怪、敌方小兵或英雄召唤物造成"
            "390 – 1000 （基于等级） 真实伤害。"
        )
        self.assertEqual(expand_wikitext(source), expected)

    def test_feel_the_burn(self):
        source = (
            "对1000码范围内的所有敌方英雄施放{{si|Exhaust|虚弱}}和"
            "{{si|Ignite|引燃}}，前者的{{tip|slow|减速}}效果提升至50%，"
            "后者转而在持续期间共造成{{as|{{pp|100 to 600}}真实伤害|true damage}}。"
        )
        expected = (
            "对1000码范围内的所有敌方英雄施放 虚弱和 引燃，前者的 减速效果"
            "提升至50%，后者转而在持续期间共造成100 – 600 （基于等级）真实伤害。"
        )
        self.assertEqual(expand_wikitext(source), expected)

    def test_hextech_mark(self):
        source = (
            "{{sbc|主动：}}向目标方向朝远处扔出一枚海克斯科技手榴弹，对命中的"
            "首个敌方单位造成{{as|{{pp|15 to 100}}{{sti|true damage|真实伤害}}"
            "|true damage}}，并提供目标的{{tip|true sight|真实视野}}，持续3秒。"
            "在接下来的3秒内，你可以再次施放{{si|Hextech Dash|海克斯科技冲刺}}。"
        )
        expected = (
            "主动：向目标方向朝远处扔出一枚海克斯科技手榴弹，对命中的首个敌方"
            "单位造成15 – 100 （基于等级） 真实伤害，并提供目标的 真实视野，"
            "持续3秒。在接下来的3秒内，你可以再次施放 海克斯科技冲刺。"
        )
        self.assertEqual(expand_wikitext(source), expected)


class PpFormsTest(unittest.TestCase):
    def test_range_form(self):
        self.assertEqual(expand_wikitext("{{pp|75 to 330}}"), "75 – 330 （基于等级）")

    def test_expression_form_clamped_to_level_cap(self):
        # ``(460-100)/17`` is authored for 18 levels; the level range caps at 18.
        self.assertEqual(
            expand_wikitext("{{pp|100 + (460-100)/17*(x-1)|1 to 20 by 1}}"),
            "100 – 460 （基于等级）",
        )

    def test_explicit_table_form(self):
        self.assertEqual(
            expand_wikitext("{{pp|390;410;430;1000|formula=ignored}}"),
            "390 – 1000 （基于等级）",
        )

    def test_expression_range_multiplication(self):
        self.assertEqual(
            expand_wikitext("{{pp|30*8 to 150*8}}"), "240 – 1200 （基于等级）"
        )

    def test_single_constant_collapses(self):
        self.assertEqual(expand_wikitext("{{pp|10 to 35|round=0}}"), "10 – 35 （基于等级）")
        self.assertEqual(expand_wikitext("{{pp|5}}"), "5")


class TooltipTemplateTest(unittest.TestCase):
    def test_tt_takes_first_argument(self):
        self.assertEqual(
            expand_wikitext("{{tt|<sup>*</sup>|仅限你的视角}}"), "*"
        )

    def test_si_family_takes_last_with_leading_space(self):
        # The leading space separates the inline icon from the preceding text.
        self.assertEqual(expand_wikitext("施放{{si|Exhaust|虚弱}}和"), "施放 虚弱和")
        self.assertEqual(expand_wikitext("A{{bi|A|B}}C"), "A BC")
        self.assertEqual(expand_wikitext("{{tt|A|B}}"), "A")

    def test_ap_arithmetic(self):
        self.assertEqual(expand_wikitext("{{ap|10*8}}"), "80")
        self.assertEqual(expand_wikitext("{{ap|40/7|round=3}}"), "5.714")
        self.assertEqual(expand_wikitext("{{ap|2.5-0.75}}"), "1.75")


class NestedTemplateTest(unittest.TestCase):
    def test_as_pp_sti_nested(self):
        source = "造成{{as|{{pp|15 to 100}}{{sti|true damage|真实伤害}}|true damage}}。"
        self.assertEqual(
            expand_wikitext(source), "造成15 – 100 （基于等级） 真实伤害。"
        )

    def test_as_without_leading_space(self):
        self.assertEqual(expand_wikitext("{{as|600|true damage}}"), "600")


class UnknownTemplateTest(unittest.TestCase):
    def test_unknown_keeps_args_and_warns(self):
        before = unknown_templates().get("Rune data Hextech Flashtraption", 0)
        out = expand_wikitext("{{Rune data Hextech Flashtraption|pst2|description}}")
        # Never invents: keeps the argument text, drops the name and braces.
        self.assertNotIn("{{", out)
        self.assertNotIn("}}", out)
        self.assertIn("description", out)
        after = unknown_templates().get("Rune data Hextech Flashtraption", 0)
        self.assertEqual(after, before + 1)

    def test_plain_text_untouched(self):
        self.assertEqual(expand_wikitext("造成600真实伤害。"), "造成600真实伤害。")
        self.assertEqual(expand_wikitext(""), "")


class DeterminismTest(unittest.TestCase):
    def test_same_input_same_output(self):
        source = (
            "{{sbc|主动：}}造成{{as|{{pp|70; then +20*x for 4;then +25*x"
            "|1 to 20 by 1}}真实伤害|true damage}}。"
        )
        self.assertEqual(expand_wikitext(source), expand_wikitext(source))


if __name__ == "__main__":
    unittest.main()
