import json
import tempfile
import unittest
from pathlib import Path

from src.parser.prices import load_champion_prices, price_of
from src.parser.skin import (
    loading_url,
    local_image,
    parse_skins,
    splash_url,
)
from src.parser.skin_availability import load_skin_availability


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class ChampionPriceCacheTest(unittest.TestCase):
    def test_price_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _write(
                Path(tmp) / "prices.json",
                {"prices": {"Aatrox": {"be": 2400, "rp": 880, "name": "Aatrox"}}},
            )
            prices = load_champion_prices(cache)
            self.assertEqual(price_of(prices, "Aatrox"), (2400, 880))

    def test_price_cache_miss_is_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _write(
                Path(tmp) / "prices.json",
                {"prices": {"Aatrox": {"be": 2400, "rp": 880}}},
            )
            prices = load_champion_prices(cache)
            # Missing champion -> (0, 0), never invented.
            self.assertEqual(price_of(prices, "Yasuo"), (0, 0))

    def test_price_cache_missing_file_degrades(self):
        prices = load_champion_prices(Path("does-not-exist-prices.json"))
        self.assertEqual(prices, {})
        self.assertEqual(price_of(prices, "Aatrox"), (0, 0))

    def test_price_cache_corrupt_degrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "prices.json"
            cache.write_text("{ not valid json", encoding="utf-8")
            self.assertEqual(load_champion_prices(cache), {})

    def test_price_cache_malformed_shape_degrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _write(Path(tmp) / "prices.json", {"prices": "oops"})
            self.assertEqual(load_champion_prices(cache), {})

    def test_price_of_none_table(self):
        self.assertEqual(price_of(None, "Aatrox"), (0, 0))


class SkinAvailabilityCacheTest(unittest.TestCase):
    def test_availability_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = _write(
                Path(tmp) / "avail.json",
                {"version": "16.20.1", "available": ["Aatrox_0", "Aatrox_1"]},
            )
            self.assertEqual(
                load_skin_availability(cache), {"Aatrox_0", "Aatrox_1"}
            )

    def test_availability_cache_missing_returns_none(self):
        self.assertIsNone(
            load_skin_availability(Path("does-not-exist-avail.json"))
        )

    def test_availability_cache_corrupt_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "avail.json"
            cache.write_text("not json", encoding="utf-8")
            self.assertIsNone(load_skin_availability(cache))


class SkinUrlTest(unittest.TestCase):
    def test_url_and_path_construction(self):
        self.assertEqual(
            local_image("Aatrox", 1), "champion/loading/Aatrox_1.jpg"
        )
        self.assertEqual(
            splash_url("Aatrox", 1),
            "https://ddragon.leagueoflegends.com/cdn/img/champion/"
            "splash/Aatrox_1.jpg",
        )
        self.assertEqual(
            loading_url("Aatrox", 1),
            "https://ddragon.leagueoflegends.com/cdn/img/champion/"
            "loading/Aatrox_1.jpg",
        )
        # No champion id -> empty, never a broken half-URL.
        self.assertEqual(local_image("", 3), "")
        self.assertEqual(splash_url("", 3), "")
        self.assertEqual(loading_url("", 3), "")


class ParseSkinsTest(unittest.TestCase):
    def setUp(self):
        self.cdragon = {
            "skins": [
                {
                    "id": 266000,
                    "name": "Aatrox",
                    "splashPath": "/lol-game-data/assets/..._0.jpg",
                    "chromas": None,
                },
                {
                    "id": 266001,
                    "name": "Justicar Aatrox",
                    "splashPath": "/lol-game-data/assets/..._1.jpg",
                    "chromas": None,
                },
                {
                    "id": 266999,
                    "name": "CDragon Only Skin",
                    "splashPath": "/lol-game-data/assets/..._999.jpg",
                    "chromas": None,
                },
            ]
        }
        self.ddragon_skins = [
            {"num": 0, "name": "default"},
            {"num": 1, "name": "仲裁圣骑 亚托克斯"},
        ]

    def test_localized_name_alignment_by_num(self):
        skins = parse_skins(
            self.cdragon,
            "Aatrox",
            266,
            self.ddragon_skins,
            {"Aatrox_0"},
        )
        by_num = {s["num"]: s for s in skins}
        self.assertEqual(by_num[0]["name"], "default")
        self.assertEqual(by_num[1]["name"], "仲裁圣骑 亚托克斯")

    def test_name_falls_back_to_cdragon_when_num_absent(self):
        skins = parse_skins(
            self.cdragon, "Aatrox", 266, self.ddragon_skins, {"Aatrox_0"}
        )
        by_num = {s["num"]: s for s in skins}
        self.assertEqual(by_num[999]["name"], "CDragon Only Skin")

    def test_row_identity_and_urls(self):
        skins = parse_skins(
            self.cdragon, "Aatrox", 266, self.ddragon_skins, {"Aatrox_0"}
        )
        self.assertEqual([s["num"] for s in skins], [0, 1, 999])
        first = skins[0]
        self.assertEqual(first["localImage"], "champion/loading/Aatrox_0.jpg")
        self.assertEqual(
            first["splashUrl"],
            "https://ddragon.leagueoflegends.com/cdn/img/champion/"
            "splash/Aatrox_0.jpg",
        )
        self.assertEqual(
            first["loadingUrl"],
            "https://ddragon.leagueoflegends.com/cdn/img/champion/"
            "loading/Aatrox_0.jpg",
        )

    def test_has_image_membership(self):
        skins = parse_skins(
            self.cdragon, "Aatrox", 266, self.ddragon_skins, {"Aatrox_0"}
        )
        by_num = {s["num"]: s for s in skins}
        self.assertEqual(by_num[0]["hasImage"], 1)  # in cache
        self.assertEqual(by_num[1]["hasImage"], 0)  # present but not in cache
        self.assertEqual(by_num[999]["hasImage"], 0)

    def test_has_image_fallback_heuristic_when_cache_missing(self):
        skins = parse_skins(
            self.cdragon, "Aatrox", 266, self.ddragon_skins, None
        )
        # Cache absent -> legacy heuristic (splashPath non-empty -> 1).
        self.assertTrue(all(s["hasImage"] == 1 for s in skins))

    def test_chromas_semantics_unchanged(self):
        cdragon = {
            "skins": [
                {
                    "id": 266002,
                    "name": "Mecha Aatrox",
                    "splashPath": "/x_2.jpg",
                    "chromas": [{"id": 1}, {"id": 2}],
                }
            ]
        }
        skins = parse_skins(cdragon, "Aatrox", 266, [], set())
        self.assertEqual(skins[0]["chromas"], 2)


if __name__ == "__main__":
    unittest.main()
