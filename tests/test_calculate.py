import unittest
from unittest.mock import patch

import app


class CalculateApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.base_payload = {
            "attacker": {
                "jp_name": "Garchomp",
                "types": ["dragon", "ground"],
                "stats": {"attack": 150, "special_attack": 100},
            },
            "defender": {
                "jp_name": "Dragonite",
                "types": ["dragon", "flying"],
                "stats": {"hp": 166, "defense": 115, "special_defense": 120},
            },
            "move": {"name": "Dragon Claw", "type": "dragon", "power": 80, "damage_class": "physical"},
        }

    def post_calculate(self, **overrides):
        payload = dict(self.base_payload)
        payload.update(overrides)
        return self.client.post("/calculate?key=" + app.ACCESS_KEY, json=payload)

    def test_basic_damage_range(self):
        response = self.post_calculate()
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["min_damage"], 117)
        self.assertEqual(data["max_damage"], 141)
        self.assertEqual(data["ko_text"], "確定2発")
        self.assertEqual(data["one_hit_chance"], 0.0)
        self.assertEqual(data["two_hit_chance"], 100.0)
        self.assertEqual(data["effectiveness"], 2.0)
        self.assertEqual(data["stab"], 1.5)

    def test_reflect_halves_physical_damage(self):
        response = self.post_calculate(wall="reflect")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["min_damage"], 58)
        self.assertEqual(data["max_damage"], 70)
        self.assertEqual(data["three_hit_chance"], 100.0)
        self.assertEqual(data["modifiers"]["wall"], 0.5)

    def test_critical_ignores_reflect(self):
        response = self.post_calculate(wall="reflect", critical=True)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["max_damage"], 211)
        self.assertEqual(data["modifiers"]["critical"], 1.5)
        self.assertEqual(data["modifiers"]["wall"], 1.0)

    def test_items_and_abilities_apply_modifiers(self):
        life_orb = self.post_calculate(attacker_item="life_orb").get_json()
        multiscale = self.post_calculate(defender_ability="マルチスケイル").get_json()
        self.assertEqual(life_orb["max_damage"], 183)
        self.assertEqual(life_orb["one_hit_chance"], 56.25)
        self.assertEqual(life_orb["items"]["attacker"], "life_orb")
        self.assertEqual(multiscale["max_damage"], 70)
        self.assertEqual(multiscale["abilities"]["defender"], "マルチスケイル")

    def test_multiscale_requires_full_hp(self):
        full_hp = self.post_calculate(defender_ability="マルチスケイル").get_json()
        chipped = self.post_calculate(
            defender_ability="マルチスケイル",
            defender_current_hp_percent=99,
        ).get_json()
        self.assertEqual(full_hp["max_damage"], 70)
        self.assertEqual(full_hp["hp"]["defender_current_percent"], 100.0)
        self.assertEqual(chipped["max_damage"], 141)
        self.assertEqual(chipped["hp"]["defender_current_percent"], 99.0)

    def test_defender_immunity_abilities_can_be_ignored(self):
        defender = {
            "jp_name": "Target",
            "types": ["normal"],
            "stats": {"hp": 166, "defense": 115, "special_defense": 120},
        }
        move = {"name": "Earthquake", "type": "ground", "power": 100, "damage_class": "physical"}

        levitate = self.post_calculate(
            defender=defender,
            move=move,
            defender_ability="\u3075\u3086\u3046",
        ).get_json()
        mold_breaker = self.post_calculate(
            defender=defender,
            move=move,
            attacker_ability="\u304b\u305f\u3084\u3076\u308a",
            defender_ability="\u3075\u3086\u3046",
        ).get_json()

        self.assertEqual(levitate["max_damage"], 0)
        self.assertEqual(levitate["modifiers"]["ability_final"], 0.0)
        self.assertGreater(mold_breaker["max_damage"], 0)
        self.assertEqual(mold_breaker["modifiers"]["ignores_defender_ability"], 1.0)

    def test_english_ability_names_are_accepted(self):
        defender = {
            "jp_name": "Target",
            "types": ["normal"],
            "stats": {"hp": 166, "defense": 115, "special_defense": 120},
        }
        move = {"name": "Earthquake", "type": "ground", "power": 100, "damage_class": "physical"}

        levitate = self.post_calculate(defender=defender, move=move, defender_ability="levitate").get_json()
        mold_breaker = self.post_calculate(
            defender=defender,
            move=move,
            attacker_ability="mold-breaker",
            defender_ability="levitate",
        ).get_json()
        multiscale = self.post_calculate(defender_ability="multiscale").get_json()
        huge_power = self.post_calculate(attacker_ability="huge-power").get_json()

        self.assertEqual(levitate["max_damage"], 0)
        self.assertGreater(mold_breaker["max_damage"], 0)
        self.assertEqual(multiscale["max_damage"], 70)
        self.assertEqual(huge_power["max_damage"], 279)

    def test_protean_like_abilities_gain_stab(self):
        defender = {
            "jp_name": "Target",
            "types": ["normal"],
            "stats": {"hp": 166, "defense": 115, "special_defense": 120},
        }
        move = {"name": "Close Combat", "type": "fighting", "power": 120, "damage_class": "physical"}

        normal = self.post_calculate(defender=defender, move=move).get_json()
        protean = self.post_calculate(defender=defender, move=move, attacker_ability="protean").get_json()
        libero = self.post_calculate(defender=defender, move=move, attacker_ability="リベロ").get_json()

        self.assertEqual(normal["stab"], 1.0)
        self.assertEqual(protean["stab"], 1.5)
        self.assertEqual(libero["stab"], 1.5)
        self.assertGreater(protean["max_damage"], normal["max_damage"])

    def test_wonder_guard_blocks_non_super_effective_moves(self):
        defender = {
            "jp_name": "Target",
            "types": ["normal"],
            "stats": {"hp": 166, "defense": 115, "special_defense": 120},
        }
        neutral = self.post_calculate(
            defender=defender,
            defender_ability="\u3075\u3057\u304e\u306a\u307e\u3082\u308a",
        ).get_json()
        super_effective = self.post_calculate(
            defender=defender,
            defender_ability="\u3075\u3057\u304e\u306a\u307e\u3082\u308a",
            move={"name": "Close Combat", "type": "fighting", "power": 120, "damage_class": "physical"},
        ).get_json()

        self.assertEqual(neutral["max_damage"], 0)
        self.assertEqual(neutral["modifiers"]["ability_final"], 0.0)
        self.assertGreater(super_effective["max_damage"], 0)
        self.assertEqual(super_effective["effectiveness"], 2.0)

    def test_refresh_all_status_endpoint(self):
        with patch.object(app, "get_refresh_state", return_value={
            "running": True,
            "total": 10,
            "done": 3,
            "error": "",
            "message": "updating",
            "started_at": 1.0,
            "finished_at": 0.0,
        }):
            response = self.client.get("/api/refresh-all-status?key=" + app.ACCESS_KEY)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["running"])
        self.assertEqual(data["done"], 3)

    def test_refresh_all_start_endpoint(self):
        with patch.object(app, "start_refresh_all_pokemon_details", return_value=True), patch.object(
            app,
            "get_refresh_state",
            return_value={
                "running": True,
                "total": 0,
                "done": 0,
                "error": "",
                "message": "started",
                "started_at": 1.0,
                "finished_at": 0.0,
            },
        ):
            response = self.client.post("/api/refresh-all?key=" + app.ACCESS_KEY)
        self.assertEqual(response.status_code, 202)
        data = response.get_json()
        self.assertTrue(data["running"])
        self.assertEqual(data["message"], "started")


if __name__ == "__main__":
    unittest.main()
