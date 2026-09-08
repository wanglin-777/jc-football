import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import model
import selftune


class ModelTests(unittest.TestCase):
    def test_extreme_poisson_is_probability_distribution(self):
        for home, away in [(0, 0), (0.25, 3.8), (3.8, 0.25), (1.5, 1.5)]:
            p = model.score_matrix_p(home, away)
            self.assertTrue(all(0 <= x <= 1 for x in p))
            self.assertAlmostEqual(sum(p), 1)

    def test_invalid_odds_are_rejected(self):
        for odd in [None, 0, -2, 1, float("nan"), float("inf"), "bad"]:
            self.assertIsNone(model.implied_from_odds(odd, 3, 4))
        self.assertAlmostEqual(sum(model.implied_from_odds(2, 3, 4)), 1)

    def test_zero_goals_are_not_missing(self):
        zero = model.poisson_lambdas({"home_home_gf": 0, "home_gf": 2}, variant="legacy")
        missing = model.poisson_lambdas({"home_gf": 2}, variant="legacy")
        self.assertLess(zero[0], missing[0])

    def test_intel_normalization(self):
        with patch("selftune.apply_tune", side_effect=lambda p: p):
            p = model.predict({"had_h": 1.01, "had_d": 1000,
                               "had_a": 1000, "intel_adj": 3})
        self.assertAlmostEqual(sum(p[k] for k in ("home", "draw", "away")), 1, places=3)

    def test_missing_data_source(self):
        self.assertEqual(model.predict({})["source"], "中性先验(数据不足)")


class TuneTests(unittest.TestCase):
    def setUp(self):
        selftune._clear()

    def tearDown(self):
        selftune._clear()

    def test_all_outcomes_are_calibrated(self):
        stats, n = selftune._compute_calib([{"rows": [
            {"pick": "主胜", "probs": [.6, .3, .1], "actual": "平", "hit": False},
            {"pick": "主胜", "probs": [], "actual": "主胜", "hit": True}]}])
        self.assertEqual(n, 1)
        self.assertEqual(stats["平"]["rate"], 1)
        self.assertEqual(stats["客胜"]["avg_p"], .1)

    def test_refresh_is_idempotent_and_corrections_detected(self):
        rows = [{"num": str(i), "pick": "主胜", "probs": [.6, .3, .1],
                 "actual": "平", "hit": False} for i in range(12)]
        data = [{"date": "2026-09-07", "rows": rows}]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(selftune, "TUNE_FILE", str(Path(tmp) / "tune.json")):
                first = selftune.update_from_verify(data)
                selftune._clear()
                second = selftune.update_from_verify(data)
                self.assertEqual(first, second)
                rows[0]["actual"] = "客胜"
                third = selftune.update_from_verify(data)
                self.assertNotEqual(first["fingerprint"], third["fingerprint"])


if __name__ == "__main__":
    unittest.main()
