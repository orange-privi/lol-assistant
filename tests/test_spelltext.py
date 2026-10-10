"""Tests for the client string-table spell-text index.

The fixtures in ``ENTRIES`` are **verbatim excerpts** of the 16.20 ``zh_cn``
client string table
(``raw/16.20/zh_CN/cdragon/game/stringtable/zh_cn.lol.stringtable.json``), so
the parser is exercised against the exact shapes a build meets:

* ``spell_<script>_tooltip``          -- bare body, no ``<titleLeft>`` wrapper
* ``generatedtip_passive_<script>_tooltip`` -- sectioned body inside
  ``<mainText>``, ability name inside ``<titleLeft>``
* ``game_buff_tooltip_<script>``      -- a *unit-state* aura text that must
  never win over the ability description
* ``spell_<script>_tooltipextended``  -- template-only body; never indexed
* ``spell_<script>_name`` / ``*_displayname`` -- name-index sources
"""

from __future__ import annotations

import json
import re
import unittest

from src.parser.spelltext import (
    SpellTextIndex,
    clean_official_text,
    official_tooltip,
    token_names,
)
from src.pipeline import render_spell_text, spell_value_names

# ---------------------------------------------------------------------------
# Fixtures (verbatim, 16.20 / zh_CN)
# ---------------------------------------------------------------------------

MK_TOOLTIP = (
    "孙悟空获得<scaleArmor>@BonusArmor@护甲</scaleArmor>并且<healing>"
    "每5秒回复他@HealthPercentPer5*100@%的最大生命值</healing>。每当他或他的"
    "<keywordMajor>分身</keywordMajor>用一次攻击或技能击中一名敌方英雄或野怪后，"
    "这些加成就会提升@StackMultiplier*100@%，持续@StackDuration@秒，"
    "最多可叠加@MaxStacks@层。"
)

MK_AURA = (
    "<titleLeft>金刚不坏</titleLeft>"
    "<mainText>周围每有一个敌方英雄，护甲和魔法抗性就提高@f1@。</mainText>"
)

CAITLYN_TOOLTIP = (
    "<titleLeft>爆头</titleLeft><titleRight></titleRight><mainText>"
    "每攻击@AttacksPerHeadshot@次，凯特琳就会发射一次<keywordMajor>爆头"
    "</keywordMajor>。草丛中的攻击在积攒<keywordMajor>爆头</keywordMajor>次数时"
    "会算为@BrushAttackTotal@次。<br><br><keywordMajor>爆头</keywordMajor>造成"
    "额外的<physicalDamage>@HeadShotBonusDamage@物理伤害</physicalDamage>。"
    "爆头对被<spellName>{{Spell_CaitlynEntrapment_Name}}</spellName>和"
    "<spellName>{{Spell_CaitlynYordleTrap_Name}}</spellName>影响的敌人们拥有"
    "双倍距离。<keywordMajor>爆头</keywordMajor>对被<spellName>"
    "{{Spell_CaitlynYordleTrap_Name}}</spellName>命中的敌人会造成额外的"
    "<physicalDamage>@spell.CaitlynW:HeadshotBonusDamage@物理伤害"
    "</physicalDamage>。</mainText>"
)

AATROX_TOOLTIP = (
    "<titleLeft>赐死剑气</titleLeft><titleRight><passiveCooldown>@PCooldown@秒"
    "%i:cooldown%</passiveCooldown></titleRight><mainText>亚托克斯的攻击造成额外的"
    "<magicDamage>@PDamage@最大生命值魔法伤害</magicDamage>并回复<healing>"
    "@PHealingRatio*100@%实际伤害值的生命值</healing>，对小兵时降低至"
    "@PHealingMinionMod*100@%。这个效果有@PCooldown@秒冷却时间。<br><br>"
    "对英雄和大型野怪进行的攻击和技能会使这个效果的冷却时间缩短2秒。"
    "用<spellName>暗裔利刃</spellName>的边缘命中时会使这个效果的冷却时间缩短4秒。"
    "</mainText>"
)

AKALI_TOOLTIP = (
    "当阿卡丽用一个技能命中一名敌方英雄时，她会在其周围显出一个持续4秒的圆环，"
    "并在朝着圆环时获得<speed>@PassiveSpeedBonus@移动速度</speed>。"
    "穿过圆环会使阿卡丽的下次攻击拥有双倍距离并造成额外的"
    "<magicDamage>@Damage@魔法伤害</magicDamage>。"
)

AKALI_EXTENDED = (
    "{{Spell_AkaliP_Tooltip}}<br><br><rules>一旦阿卡丽穿过圆环，"
    "她在朝着敌人移动时就会获得<speed>移动速度</speed>。</rules>"
)

AATROX_Q_TOOLTIP = (
    "亚托克斯猛砸他的巨剑，造成<physicalDamage>@QDamage@物理伤害</physicalDamage>。"
    "如果敌人被边缘命中，还会被暂时<status>击飞</status>并转而受到"
    "<physicalDamage>@QEdgeDamage@伤害</physicalDamage>。"
)

ENTRIES = {
    # -- MonkeyKing passive: the plain ``spell_*`` body wins on priority ----
    "spell_monkeykingpassive_name": "金刚不坏",
    "spell_monkeykingpassive_tooltip": MK_TOOLTIP,
    "spell_monkeykingpassive_tooltipextended": (
        "{{Spell_MonkeyKingPassive_Tooltip}}<br><br><rules>最大加成："
        "<scaleArmor>@TooltipMaxArmor@护甲</scaleArmor>和<healing>"
        "每5秒@TooltipMaxHealthPercentPer5@%最大生命值</healing>。</rules>"
    ),
    "generatedtip_passive_monkeykingpassive_tooltip": (
        "<titleLeft>金刚不坏</titleLeft><titleRight></titleRight>"
        f"<mainText>{MK_TOOLTIP}</mainText>"
    ),
    "generatedtip_passive_monkeykingpassive_displayname": "金刚不坏",
    # Aura on the *affected unit* -- reads as a unit state, not an ability.
    "game_buff_tooltip_monkeykingpassive": MK_AURA,
    # -- Caitlyn passive: no ``spell_*_tooltip``; sectioned source + refs ---
    "generatedtip_passive_caitlynpassive_tooltip": CAITLYN_TOOLTIP,
    "generatedtip_passive_caitlynpassive_displayname": "爆头",
    # -- Aatrox passive: only a sectioned source (``spell_aatroxpassive_*``
    #    exists solely as a jade variant, under a *different* ability name) --
    "generatedtip_passive_aatroxpassive_displayname": "赐死剑气",
    "generatedtip_passive_aatroxpassive_tooltip": AATROX_TOOLTIP,
    "spell_aatroxpassive_jade_name": "鲜血魔井",
    "spell_aatroxpassive_jade_tooltip": (
        "亚托克斯会将来自技能的自损伤害储存至<keywordMajor>鲜血魔井"
        "</keywordMajor>，每储存@SpeedPerBloodWell@%就会获得<attackSpeed>"
        "@AttackSpeedGain@%攻击速度</attackSpeed>。"
    ),
    # -- Akali passive: bare body + a template-only ``tooltipextended`` -----
    "spell_akalip_name": "我流忍法！潜龙印",
    "spell_akalip_tooltip": AKALI_TOOLTIP,
    "spell_akalip_tooltipextended": AKALI_EXTENDED,
    # -- Aatrox Q: a normal QWER slot (bare body) --------------------------
    "spell_aatroxq_name": "暗裔利刃",
    "spell_aatroxq_tooltip": AATROX_Q_TOOLTIP,
}

# Residue helpers: everything below must be gone after ``clean_official_text``
# (or, for ``@...@``, be a genuinely fillable placeholder).
EMPTY_TAG_PAIR = re.compile(r"<([A-Za-z0-9_]+)>[\s\r\n]*</\1>")
TEMPLATE_LEFTOVER = re.compile(r"\{\{|\}\}")
ICON_MARKER = re.compile(r"%i:")


def _index(entries=None) -> SpellTextIndex:
    return SpellTextIndex(ENTRIES if entries is None else entries)


def _assert_no_residue(test: unittest.TestCase, text: str) -> None:
    """No template refs, icon markers, empty tag pairs or empty ``@@``."""
    test.assertNotIn("{{", text)
    test.assertNotIn("}}", text)
    test.assertIsNone(TEMPLATE_LEFTOVER.search(text))
    test.assertIsNone(ICON_MARKER.search(text))
    test.assertIsNone(EMPTY_TAG_PAIR.search(text))
    test.assertNotIn("@@", text)


# ---------------------------------------------------------------------------
# clean_official_text
# ---------------------------------------------------------------------------


class CleanOfficialTextTest(unittest.TestCase):
    def test_strips_template_refs(self):
        self.assertEqual(
            clean_official_text("{{Spell_X_Tooltip}}结尾"), "结尾"
        )

    def test_strips_icon_markers(self):
        self.assertEqual(
            clean_official_text("冷却@PCooldown@秒%i:cooldown%"),
            "冷却@PCooldown@秒",
        )

    def test_drops_empty_tag_pairs_left_by_template_removal(self):
        # ``<spellName>{{Spell_X_Name}}</spellName>`` -> the value is filled at
        # runtime, so an empty pair only leaves a stray space behind.
        self.assertEqual(
            clean_official_text("对<spellName>{{Spell_X_Name}}</spellName>有效"),
            "对有效",
        )

    def test_keeps_non_empty_tag_pairs(self):
        self.assertEqual(
            clean_official_text("用<spellName>暗裔利刃</spellName>命中"),
            "用<spellName>暗裔利刃</spellName>命中",
        )

    def test_keeps_client_markup_and_tokens(self):
        # Markup drives colourisation and ``@Token@`` is filled client-side;
        # stripping either would lose information.
        text = clean_official_text(MK_TOOLTIP)
        self.assertIn("<scaleArmor>", text)
        self.assertIn("</scaleArmor>", text)
        self.assertIn("<keywordMajor>分身</keywordMajor>", text)
        self.assertIn("@HealthPercentPer5*100@", text)

    def test_decodes_entities_and_collapses_whitespace(self):
        self.assertEqual(
            clean_official_text("A&nbsp;B&amp;C   D \t E"),
            "A B&C D E",
        )

    def test_empty_and_none(self):
        self.assertEqual(clean_official_text(""), "")
        self.assertEqual(clean_official_text(None), "")

    def test_fixture_bodies_leave_no_residue(self):
        for body in (MK_TOOLTIP, CAITLYN_TOOLTIP, AATROX_TOOLTIP, AKALI_TOOLTIP):
            with self.subTest(body=body[:24]):
                _assert_no_residue(self, clean_official_text(body))


# ---------------------------------------------------------------------------
# token_names
# ---------------------------------------------------------------------------


class TokenNamesTest(unittest.TestCase):
    def test_lowercases_and_strips_arithmetic(self):
        self.assertEqual(token_names("@HealthPercentPer5*100@"), {"healthpercentper5"})
        self.assertEqual(token_names("@QDamage/2@"), {"qdamage"})

    def test_collects_several_tokens(self):
        self.assertEqual(
            token_names("回复<healing>@TTMinHeal@ - @TTMaxHeal@生命值</healing>"),
            {"ttminheal", "ttmaxheal"},
        )

    def test_ignores_modifier_append_marker(self):
        # Not a number: it is a marker telling the client where to splice the
        # "additional bonuses" block.
        self.assertEqual(token_names("@SpellModifierDescriptionAppend@"), set())

    def test_dotted_cross_spell_refs_are_not_fillable(self):
        # ``@spell.CaitlynW:HeadshotBonusDamage@`` points at another spell's
        # value, so it is not something *this* row can resolve. It stays in the
        # text for the client to deal with, but must not count as a filled
        # number (otherwise gate 2 in ``render_spell_text`` would open on a
        # spelled-out reference alone).
        self.assertEqual(
            token_names("@spell.CaitlynW:HeadshotBonusDamage@"), set()
        )

    def test_no_tokens(self):
        self.assertEqual(token_names("孙悟空会获得护甲。"), set())
        self.assertEqual(token_names(""), set())


# ---------------------------------------------------------------------------
# SpellTextIndex
# ---------------------------------------------------------------------------


class SpellTextIndexTest(unittest.TestCase):
    def test_unusable_when_empty(self):
        self.assertFalse(SpellTextIndex().is_usable())
        self.assertFalse(SpellTextIndex({}).is_usable())
        self.assertFalse(SpellTextIndex(None).is_usable())
        self.assertTrue(_index().is_usable())

    def test_unknown_script_returns_empty(self):
        self.assertEqual(_index().tooltip_for(["nobody"]), "")

    def test_script_lookup_returns_bare_body(self):
        # The ``spell_*_tooltip`` family has no section wrapper at all.
        self.assertEqual(
            _index().tooltip_for(["monkeykingpassive"]), MK_TOOLTIP
        )

    def test_priority_beats_insertion_order(self):
        # ``game_buff_tooltip_*`` (the aura on the affected unit) is registered
        # too, and string-table keys sort alphabetically -- ``game_`` comes
        # first. Without explicit priorities the aura text would win.
        text = _index().tooltip_for(["monkeykingpassive"])
        self.assertNotIn("周围每有一个敌方英雄", text)
        self.assertIn("孙悟空获得", text)

    def test_sectioned_body_is_main_text_only(self):
        # Aatrox's passive has no bare ``spell_*_tooltip``: the body comes from
        # ``generatedtip_passive_aatroxpassive_tooltip`` and must exclude
        # ``<titleLeft>`` (the ability name) so it does not repeat on the card.
        text = _index().tooltip_for(["aatroxpassive"])
        self.assertTrue(text.startswith("亚托克斯的攻击"))
        self.assertNotIn("<titleLeft>", text)
        self.assertNotIn("<titleRight>", text)
        self.assertNotIn("赐死剑气", text)

    def test_name_reverse_lookup(self):
        self.assertEqual(
            _index().tooltip_for([], "爆头", "Caitlyn"),
            clean_official_text(
                re.search(r"<mainText>(.*)</mainText>", CAITLYN_TOOLTIP).group(1)
            ),
        )

    def test_name_reverse_lookup_is_whitespace_tolerant(self):
        # Data Dragon pads some names with ``&nbsp;``.
        self.assertIn(
            "孙悟空获得", _index().tooltip_for([], "\u00a0金刚不坏\u00a0")
        )

    def test_variant_only_script_is_still_usable(self):
        # Filtering jade/ruby out entirely would lose abilities that exist
        # *only* as a variant; they are merely sorted last.
        text = _index().tooltip_for(["aatroxpassive_jade"])
        self.assertIn("鲜血魔井", text)
        self.assertNotIn("赐死剑气", text)

    def test_name_lookup_prefers_own_champion(self):
        # Synthetic: pins the ``champion_prefix`` tiebreak (last sort key).
        # Real 16.20 collisions are only jade/ultbook variants, but the
        # ordering is load-bearing whenever two champions ever share a name.
        entries = {
            "generatedtip_passive_alphaq_tooltip": (
                "<titleLeft>重名技能</titleLeft><mainText>甲：@V@点</mainText>"
            ),
            "generatedtip_passive_betaq_tooltip": (
                "<titleLeft>重名技能</titleLeft><mainText>乙：@V@点</mainText>"
            ),
        }
        index = SpellTextIndex(entries)
        self.assertEqual(index.tooltip_for([], "重名技能", "Beta"), "乙：@V@点")
        self.assertEqual(index.tooltip_for([], "重名技能", "Alpha"), "甲：@V@点")

    def test_official_text_beats_jade_variant_in_name_lookup(self):
        # Synthetic, but it pins a real ordering hazard: ``_jade``/``_ruby`` is
        # a second copy of the *same* ability and must lose to the normal
        # script. That only holds while the variant preference outranks the
        # champion-prefix heuristic -- variant script names are champion-
        # prefixed (``jannapassive_jade``) while normal ones often are not
        # (``tailwindself``, ``voidstone``, ``backstab``).
        entries = {
            "spell_realscript_name": "重名技能",
            "spell_realscript_tooltip": "正式版@X@",
            "spell_mychamppassive_jade_name": "重名技能",
            "spell_mychamppassive_jade_tooltip": "变体版@X@",
        }
        self.assertEqual(
            SpellTextIndex(entries).tooltip_for([], "重名技能", "MyChamp"),
            "正式版@X@",
        )

    def test_template_only_body_falls_through(self):
        # ``_best_priority`` must judge by "does it clean to something" rather
        # than "is the key present": a template-only body is present but empty.
        entries = {
            "spell_dummyp_tooltip": "{{Spell_DummyP_Tooltip}}",
            "generatedtip_passive_dummyp_tooltip": (
                "<titleLeft>假技能</titleLeft><mainText>真正的技能@X@</mainText>"
            ),
        }
        self.assertEqual(
            SpellTextIndex(entries).tooltip_for(["dummyp"]), "真正的技能@X@"
        )

    def test_extended_variant_is_not_indexed(self):
        # Only ``*_tooltip`` is a body source; ``*_tooltipextended`` is a
        # template include for the same ability (Akali's is ``{{ }}``-only).
        scripts = _index()._bodies.get("akalip", [])
        self.assertEqual(len(scripts), 1)
        self.assertNotIn("rules", scripts[0][1])

    def test_deterministic(self):
        index = _index()
        first = index.tooltip_for(["monkeykingpassive"])
        second = index.tooltip_for(["monkeykingpassive"])
        self.assertEqual(first, second)


class OfficialTooltipTest(unittest.TestCase):
    def test_unusable_index_returns_empty(self):
        self.assertEqual(official_tooltip(None, ["monkeykingpassive"]), "")
        self.assertEqual(
            official_tooltip(SpellTextIndex({}), ["monkeykingpassive"]), ""
        )

    def test_usable_index_delegates(self):
        self.assertEqual(
            official_tooltip(_index(), ["monkeykingpassive"]), MK_TOOLTIP
        )

    def test_never_invents(self):
        self.assertEqual(official_tooltip(_index(), ["zzz"], "", "MonkeyKing"), "")


# ---------------------------------------------------------------------------
# pipeline.render_spell_text
# ---------------------------------------------------------------------------


def _bin(champion: str, container: str, leaf: str) -> dict:
    """A BIN map with one spell object, keyed the way CommunityDragon does."""
    return {
        f"Characters/{champion}/Spells/{container}/{leaf}": {
            "mSpell": {"mImgIconName": [f"{leaf}_Passive.png"]}
        }
    }


def _spell(**overrides) -> dict:
    spell = {
        "id": "",
        "slot": "P",
        "name": "金刚不坏",
        "tooltip": "孙悟空在与英雄或野怪战斗时，会获得可叠加的护甲和最大生命值回复。",
        "dataValuesJson": json.dumps(
            {
                "CombatDuration": [3.0] * 7,
                "StackDuration": [5.0] * 7,
                "MaxStacks": [5.0] * 7,
                "StackMultiplier": [1.0] * 7,
                "HealthPercentPer5": [0.02] * 7,
            }
        ),
        "calculationJson": json.dumps({"BonusArmor": {}, "TooltipMaxArmor": {}}),
    }
    spell.update(overrides)
    return spell


MK_BIN = _bin("MonkeyKing", "MonkeyKingPassiveAbility", "MonkeyKingPassive")


class SpellValueNamesTest(unittest.TestCase):
    def test_union_of_both_named_tables(self):
        names = spell_value_names(_spell())
        self.assertIn("bonusarmor", names)
        self.assertIn("healthpercentper5", names)

    def test_tolerates_bad_json(self):
        self.assertEqual(
            spell_value_names(
                {"dataValuesJson": "{not json", "calculationJson": ""}
            ),
            set(),
        )


class RenderSpellTextTest(unittest.TestCase):
    def test_fills_monkeyking_passive(self):
        text = render_spell_text(
            _spell(), MK_BIN, "MonkeyKing", (), _index()
        )
        self.assertEqual(text, MK_TOOLTIP)
        self.assertIn("<scaleArmor>@BonusArmor@护甲</scaleArmor>", text)
        self.assertIn("@MaxStacks@层", text)
        _assert_no_residue(self, text)

    def test_gate_skips_tooltips_data_dragon_can_fill(self):
        # Data Dragon's Q/W/E/R tooltips carry ``{{ }}``; the client already
        # renders them, so the column must stay empty (no duplicate text).
        q_values = json.dumps({"QDamage": [70.0], "QEdgeDamage": [1.5]})
        spell = _spell(
            id="AatroxQ",
            slot="Q",
            name="暗裔利刃",
            tooltip="造成 {{ e1 }} 物理伤害。",
            dataValuesJson=q_values,
            calculationJson=json.dumps({"QRecast": {}}),
        )
        bin_json = _bin("Aatrox", "AatroxQAbility", "AatroxQ")
        self.assertEqual(
            render_spell_text(spell, bin_json, "Aatrox", (), _index()), ""
        )
        # Same spell, same BIN -- only the ``{{`` gate differs.
        spell["tooltip"] = AATROX_Q_TOOLTIP
        self.assertEqual(
            render_spell_text(spell, bin_json, "Aatrox", (), _index()),
            AATROX_Q_TOOLTIP,
        )

    def test_gate_rejects_values_that_do_not_match_the_text(self):
        # The row has values, but none of them is named in the official text
        # (here: MonkeyKing's numbers on an Aatrox Q row) -- nothing for the
        # client to substitute, so the column stays empty.
        self.assertEqual(
            render_spell_text(
                _spell(id="AatroxQ", slot="Q", name="暗裔利刃"),
                _bin("Aatrox", "AatroxQAbility", "AatroxQ"),
                "Aatrox",
                (),
                _index(),
            ),
            "",
        )

    def test_gate_requires_a_token_this_spell_can_fill(self):
        # The text resolves, but the row has no values for any of its tokens.
        self.assertEqual(
            render_spell_text(
                _spell(dataValuesJson="{}", calculationJson="{}"),
                MK_BIN,
                "MonkeyKing",
                (),
                _index(),
            ),
            "",
        )

    def test_gate_rejects_unit_state_text(self):
        # When the *only* retrievable candidate is the aura on the affected
        # unit (``game_buff_tooltip_*``), the column stays empty rather than
        # storing prose about a unit state. Its sole token ``@f1@`` is an
        # internal index the client cannot resolve either.
        self.assertEqual(token_names(clean_official_text(MK_AURA)), {"f1"})
        self.assertEqual(
            render_spell_text(
                _spell(),
                MK_BIN,
                "MonkeyKing",
                (),
                SpellTextIndex({"game_buff_tooltip_monkeykingpassive": MK_AURA}),
            ),
            "",
        )

    def test_unknown_script_and_name_returns_empty(self):
        # Both lookups miss -> nothing is invented.
        self.assertEqual(
            render_spell_text(
                _spell(id="Nobody", slot="Q", name="不存在的技能"),
                MK_BIN,
                "MonkeyKing",
                (),
                _index(),
            ),
            "",
        )

    def test_unknown_script_falls_back_to_localized_name(self):
        # A script-name miss is *not* the end: the localized-name reverse
        # lookup exists precisely to survive patch-to-patch script renames
        # (``AatroxPassive`` <-> ``AatroxP``), so this still resolves.
        self.assertEqual(
            render_spell_text(
                _spell(id="Nobody", slot="Q"), MK_BIN, "MonkeyKing", (), _index()
            ),
            MK_TOOLTIP,
        )

    def test_unusable_index_yields_empty(self):
        self.assertEqual(
            render_spell_text(
                _spell(), MK_BIN, "MonkeyKing", (), SpellTextIndex({})
            ),
            "",
        )

    def test_missing_bin_still_resolves_by_name(self):
        # Passives have no Data Dragon script id at all, so "no BIN" is normal
        # for them; the name lookup is what fills the row.
        self.assertEqual(
            render_spell_text(_spell(), None, "MonkeyKing", (), _index()),
            MK_TOOLTIP,
        )

    def test_golden_rows(self):
        """The four rows the design was validated against, end to end."""
        cases = [
            (
                "MonkeyKing",
                MK_BIN,
                _spell(),
                "孙悟空获得",
            ),
            (
                "Caitlyn",
                _bin("Caitlyn", "CaitlynPassiveAbility", "CaitlynPassive"),
                _spell(
                    name="爆头",
                    dataValuesJson=json.dumps(
                        {"AttacksPerHeadshot": [5.0], "BrushStackBonus": [1.0]}
                    ),
                    calculationJson=json.dumps(
                        {
                            "HeadShotBonusDamage": {},
                            "HeadShotMinionBonusDamage": {},
                            "BrushAttackTotal": {},
                        }
                    ),
                ),
                "每攻击@AttacksPerHeadshot@次",
            ),
            (
                "Aatrox",
                _bin("Aatrox", "AatroxPassiveAbility", "AatroxPassive"),
                _spell(
                    name="赐死剑气",
                    dataValuesJson=json.dumps(
                        {"PHealingRatio": [0.3], "PHealingMinionMod": [0.1]}
                    ),
                    calculationJson=json.dumps(
                        {"PDamage": {}, "PCooldown": {}}
                    ),
                ),
                "亚托克斯的攻击造成额外的",
            ),
            (
                "Akali",
                _bin("Akali", "AkaliPassiveAbility", "AkaliP"),
                _spell(
                    name="我流忍法！潜龙印",
                    dataValuesJson=json.dumps({"Level1MS": [0.3]}),
                    calculationJson=json.dumps(
                        {"Damage": {}, "PassiveSpeedBonus": {}}
                    ),
                ),
                "当阿卡丽用一个技能命中一名敌方英雄时",
            ),
        ]
        for champion, bin_json, spell, expected in cases:
            with self.subTest(champion=champion):
                text = render_spell_text(
                    spell, bin_json, champion, (), _index()
                )
                self.assertTrue(text, f"{champion}: expected text")
                self.assertIn(expected, text)
                self.assertNotIn("<titleLeft>", text)
                _assert_no_residue(self, text)


if __name__ == "__main__":
    unittest.main()
