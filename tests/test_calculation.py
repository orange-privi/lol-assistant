import unittest

from src.parser.calculation import (
    extract_calculations,
    extract_data_values,
)


class CalculationTest(unittest.TestCase):
    def test_kayle_style_calculation(self):
        value = {
            "spell": {
                "mSpellCalculations": {
                    "EPassiveTotalDamage": {
                        "DamageType": 1,
                        "mFormulaParts": [
                            {
                                "mDataValue": "PassiveDamage",
                                "__type": "NamedDataValueCalculationPart",
                            },
                            {
                                "mDataValue": "PassiveAPRatio",
                                "__type": "StatByNamedDataValueCalculationPart",
                                "mStat": 2,
                                "mStatFormula": 2,
                            },
                        ],
                        "__type": "GameCalculation",
                    }
                },
                "DataValues": [
                    {
                        "name": "PassiveDamage",
                        "values": [15, 15, 20, 25, 30, 35, 40],
                        "__type": "SpellDataValue",
                    }
                ],
            }
        }

        calculations = extract_calculations(value)
        data_values = extract_data_values(value)

        self.assertIn("EPassiveTotalDamage", calculations)
        self.assertEqual(
            data_values["PassiveDamage"],
            [15, 15, 20, 25, 30, 35, 40],
        )
        self.assertEqual(
            calculations["EPassiveTotalDamage"]["parts"][0],
            {"type": "dataValue", "name": "PassiveDamage"},
        )


if __name__ == "__main__":
    unittest.main()
