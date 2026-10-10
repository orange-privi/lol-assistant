import unittest

from src.parser.calculation import (
    evaluate_calculations,
    infer_stat_from_name,
    normalize_calculation,
    normalize_part,
)
from src.parser.spell import (
    backfill_cost_from_resource,
    effect_values,
    fold_levels,
)


class NormalizeStatTest(unittest.TestCase):
    """`mStat` 缺失时的属性推断。

    cdragon 的 BIN 导出会省略这个字段（全库 783 处），名字是唯一线索。
    """

    def test_reads_ability_power_from_name(self):
        self.assertEqual(infer_stat_from_name("APRatio"), "ABILITY_POWER")
        self.assertEqual(infer_stat_from_name("ShieldAPRatio"), "ABILITY_POWER")
        self.assertEqual(infer_stat_from_name("APToPercentRatio"), "ABILITY_POWER")

    def test_requires_a_bonus_suffix(self):
        # 裸的 `ap` 会在别的词里误命中，必须与加成后缀同现
        self.assertEqual(infer_stat_from_name("Shape"), "")
        self.assertEqual(infer_stat_from_name("Apex"), "")

    def test_gives_up_when_name_says_nothing(self):
        self.assertEqual(infer_stat_from_name("DamageRatio"), "")
        self.assertEqual(infer_stat_from_name("None"), "")


class NormalizePartTest(unittest.TestCase):
    """`__type` -> 客户端认得的 `type`。"""

    def test_infers_stat_when_m_stat_is_missing(self):
        part = {
            "__type": "StatByNamedDataValueCalculationPart",
            "mDataValue": "APRatio",
        }

        self.assertEqual(normalize_part(part)["stat"], "ABILITY_POWER")

    def test_keeps_empty_stat_when_nothing_identifies_it(self):
        # `StatByCoefficientCalculationPart` 只有系数、连名字都没有 ——
        # 缺失的 mStat 分散在 AD / AP 英雄上，不能统一推断
        part = {"__type": "StatByCoefficientCalculationPart", "mCoefficient": 0.5}
        normalized = normalize_part(part)

        self.assertEqual(normalized["stat"], "")
        self.assertEqual(normalized["coefficient"], 0.5)

    def test_sub_parts_keep_their_structure(self):
        # 两套写法之一：`mPart1` / `mPart2` 成对
        part = {
            "__type": "ProductOfSubPartsCalculationPart",
            "mPart1": {"__type": "NumberCalculationPart", "mNumber": 1.0},
            "mPart2": {
                "__type": "NamedDataValueCalculationPart",
                "mDataValue": "RepeatDamageMod",
            },
        }

        normalized = normalize_part(part)

        self.assertEqual(normalized["type"], "product")
        self.assertEqual(
            [sub["type"] for sub in normalized["parts"]], ["number", "dataValue"]
        )

    def test_stat_by_sub_part_folds_into_stat_data_value(self):
        part = {
            "__type": "StatBySubPartCalculationPart",
            "mStat": 2,
            "mSubpart": {
                "__type": "NamedDataValueCalculationPart",
                "mDataValue": "tADRatio",
            },
        }

        normalized = normalize_part(part)

        self.assertEqual(normalized["type"], "statDataValue")
        self.assertEqual(normalized["name"], "tADRatio")


class NormalizeCalculationTest(unittest.TestCase):
    def test_modified_calculation_keeps_reference_and_multiplier(self):
        calculation = {
            "__type": "GameCalculationModified",
            "mModifiedGameCalculation": "SingleFireDamage",
            "mMultiplier": {
                "__type": "NamedDataValueCalculationPart",
                "mDataValue": "RepeatDamageMod",
            },
        }

        normalized = normalize_calculation(calculation)

        # 客户端要靠这两个键沿引用链展开，并渲染 `(式子) × (倍率)`
        self.assertEqual(normalized["class"], "GameCalculationModified")
        self.assertEqual(normalized["mModifiedGameCalculation"], "SingleFireDamage")
        self.assertEqual(
            normalized["multiplier"],
            {"type": "dataValue", "name": "RepeatDamageMod"},
        )


class EffectValuesTest(unittest.TestCase):
    """Data Dragon 侧那几样「BIN 里没有」的数值。"""

    def test_effect_cost_and_maxammo(self):
        # 结构取自科加斯 Q（`{{ e5 }}` / `{{ e2 }}` / `{{ e3 }}`）
        spell = {
            "maxrank": 5,
            "effect": [None, [0, 0, 0, 0, 0], [60, 60, 60, 60, 60],
                       [1.5, 1.5, 1.5, 1.5, 1.5], [0, 0, 0, 0, 0],
                       [1, 1, 1, 1, 1]],
            "effectBurn": [None, "0", "60", "1.5", "0.63", "1"],
            "cost": [50, 50, 50, 50, 50],
            "maxammo": "2",
        }

        values = effect_values(spell)

        # 逐级数组前置一个 0 填充位：客户端取 `rank r -> values[r]`
        self.assertEqual(values["e2"], [0, 60, 60, 60, 60, 60])
        self.assertEqual(values["e5"], [0, 1, 1, 1, 1, 1])
        # 全 0 的 effect 项不注入（0 在这份数据里常表示「没有这一项」）
        self.assertNotIn("e1", values)
        self.assertNotIn("e4", values)
        self.assertEqual(values["cost"], [0, 50, 50, 50, 50, 50])
        # maxammo 在 Data Dragon 里是**字符串**
        self.assertEqual(values["maxammo"], [0, 2])

    def test_effect_falls_back_to_effect_burn(self):
        spell = {
            "maxrank": 5,
            "effect": [None, None, [80, 130, 180, 230, 280]],
            "effectBurn": [None, "0", "80/130/180/230/280"],
        }

        values = effect_values(spell)

        self.assertEqual(values["e2"], [0, 80, 130, 180, 230, 280])

    def test_maxammo_not_applicable(self):
        self.assertNotIn(
            "maxammo", effect_values({"maxrank": 5, "maxammo": "-1"})
        )


class BackfillCostTest(unittest.TestCase):
    """消耗量在 `resource` 模板里，ddragon 的 `cost` 全是 0。"""

    def test_health_cost(self):
        ddragon = {
            "costType": "生命值",
            "resource": "{{ healthcost }}生命值",
            "maxrank": 5,
        }
        spell = {"cost": "0", "costLevels": "[0,0,0,0,0]", "maxRank": 5}
        data_values = {"HealthCost": [0, 50, 60, 70, 80, 90]}

        self.assertTrue(backfill_cost_from_resource(ddragon, spell, data_values))
        self.assertEqual(spell["costLevels"], "[50,60,70,80,90]")
        self.assertEqual(spell["cost"], "50 / 60 / 70 / 80 / 90")

    def test_keeps_ddragon_cost_when_present(self):
        ddragon = {"costType": "法力", "resource": "{{ cost }} {{ abilityresourcename }}"}
        spell = {"cost": "45", "costLevels": "[45,45,45,45,45]", "maxRank": 5}

        self.assertFalse(
            backfill_cost_from_resource(ddragon, spell, {"Cost": [0, 45, 45, 45, 45, 45]})
        )
        self.assertEqual(spell["costLevels"], "[45,45,45,45,45]")

    def test_skips_template_with_arithmetic(self):
        # `{{ currenthealthcost*100 }}%当前生命值` —— 量纲不同，不猜
        ddragon = {
            "costType": "%当前生命值",
            "resource": "{{ currenthealthcost*100 }}%当前生命值",
            "maxrank": 5,
        }
        spell = {"cost": "0", "costLevels": "[0,0,0,0,0]", "maxRank": 5}

        self.assertFalse(
            backfill_cost_from_resource(
                ddragon, spell, {"CurrentHealthCost": [0, 0.025] * 3}
            )
        )
        self.assertEqual(spell["costLevels"], "[0,0,0,0,0]")

    def test_fold_levels(self):
        self.assertEqual(fold_levels([60, 60, 60, 60, 60]), "60")
        self.assertEqual(fold_levels([20, 22.5, 25]), "20 / 22.5 / 25")


class EvaluateCalculationsTest(unittest.TestCase):
    """改写式（GameCalculationModified）：客户端渲染不出，但静态可算。"""

    def _evaluate(self, raw, data_values, max_rank=2):
        calculations = {
            name: normalize_calculation(calc) for name, calc in raw.items()
        }
        return evaluate_calculations(raw, calculations, data_values, max_rank)

    def test_modified_calculation_is_evaluated(self):
        raw = {
            "Base": {
                "__type": "GameCalculation",
                "mFormulaParts": [
                    {"__type": "NamedDataValueCalculationPart",
                     "mDataValue": "Damage"}
                ],
            },
            "Edge": {
                "__type": "GameCalculationModified",
                "mModifiedGameCalculation": "Base",
                "mMultiplier": {
                    "__type": "SumOfSubPartsCalculationPart",
                    "mSubparts": [
                        {"__type": "NumberCalculationPart", "mNumber": 1.0},
                        {"__type": "NamedDataValueCalculationPart",
                         "mDataValue": "Bonus"},
                    ],
                },
            },
        }
        data_values = {"Damage": [0, 100, 200], "Bonus": [0, 0.5, 0.5]}

        evaluated = self._evaluate(raw, data_values)

        # 边缘伤害 = 基础伤害 ×(1 + 中心加成)
        self.assertEqual(evaluated["Edge"], [0, 150, 300])

    def test_keeps_result_when_multiplier_is_runtime(self):
        raw = {
            "Base": {
                "__type": "GameCalculation",
                "mFormulaParts": [
                    {"__type": "NamedDataValueCalculationPart",
                     "mDataValue": "Damage"}
                ],
            },
            "Edge": {
                "__type": "GameCalculationModified",
                "mModifiedGameCalculation": "Base",
                "mMultiplier": {
                    "__type": "StatByNamedDataValueCalculationPart",
                    "mDataValue": "CritScale",
                    "mStat": 4,
                },
            },
        }

        evaluated = self._evaluate(raw, {"Damage": [0, 100, 200]})

        # 客户端对运行时倍率一律按 1 处理，这里同样忽略
        self.assertEqual(evaluated["Edge"], [0, 100, 200])

    def test_gives_up_on_runtime_base(self):
        raw = {
            "Base": {
                "__type": "GameCalculation",
                "mFormulaParts": [
                    {"__type": "NamedDataValueCalculationPart",
                     "mDataValue": "BaseDamage"},
                    {"__type": "StatByNamedDataValueCalculationPart",
                     "mDataValue": "TotalADRatio", "mStat": 2},
                ],
            },
            "Edge": {
                "__type": "GameCalculationModified",
                "mModifiedGameCalculation": "Base",
                "mMultiplier": {
                    "__type": "NumberCalculationPart", "mNumber": 1.5
                },
            },
        }
        data_values = {
            "BaseDamage": [0, 100, 200],
            "TotalADRatio": [0, 0.8, 0.8],
        }

        evaluated = self._evaluate(raw, data_values)

        # 基础式吃攻击力 -> 离线算不出，宁可留问号也不编
        self.assertNotIn("Edge", evaluated)

    def test_skips_what_the_client_can_render(self):
        raw = {
            "Damage": {
                "__type": "GameCalculation",
                "mFormulaParts": [
                    {"__type": "NamedDataValueCalculationPart",
                     "mDataValue": "BaseDamage"}
                ],
            }
        }

        evaluated = self._evaluate(raw, {"BaseDamage": [0, 100, 200]})

        self.assertEqual(evaluated, {})

    def test_hashed_names_are_not_emitted(self):
        raw = {
            "{c8e45bc3}": {
                "__type": "GameCalculation",
                "mFormulaParts": [
                    {"__type": "NumberCalculationPart", "mNumber": 5}
                ],
            }
        }

        self.assertEqual(self._evaluate(raw, {}), {})


if __name__ == "__main__":
    unittest.main()
