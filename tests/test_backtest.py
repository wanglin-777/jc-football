import unittest
from datetime import date
from unittest.mock import patch

import backtest
import history
import model


class HistoryModelTests(unittest.TestCase):
    def test_small_samples_stay_near_league_baseline(self):
        few = {"home_gf": 3, "home_home_gf": 4, "home_games": 2, "home_home_games": 1}
        many = dict(few, home_games=10, home_home_games=5)
        self.assertLess(model.poisson_lambdas(few, variant="shrunk_form")[0],
                        model.poisson_lambdas(many, variant="shrunk_form")[0])

    def test_zero_home_goals_remain_valid_with_samples(self):
        feat = {"home_gf": 1.5, "home_games": 10, "home_home_games": 5, "home_home_gf": 0}
        zero = model.poisson_lambdas(feat, variant="shrunk_form")
        missing = model.poisson_lambdas(dict(feat, home_home_gf=None), variant="shrunk_form")
        self.assertLess(zero[0], missing[0])

    def test_no_history_does_not_invoke_candidate(self):
        with patch.object(model, "poisson_lambdas", side_effect=AssertionError("no history")):
            pred = model.predict({"had_h": 2, "had_d": 3, "had_a": 4})
            self.assertEqual(pred["history_weight"], 0)

    def test_goal_market_remains_on_legacy_model(self):
        with patch.object(model, "poisson_lambdas", return_value=(1.5, 1.1)) as lambdas:
            model.total_goals({})
            lambdas.assert_called_once_with({}, variant="legacy")

    def test_shadow_baseline_matches_legacy_prediction(self):
        feat = {"home_games": 10, "away_games": 10, "home_home_games": 5,
                "away_away_games": 5, "home_gf": 2, "away_gf": .8,
                "had_h": 2, "had_d": 3, "had_a": 4}
        current = model.predict(feat)
        original = model.predict(feat, history_variant="legacy")
        self.assertEqual(current["legacy_probs"], [original[k] for k in ("home", "draw", "away")])
        self.assertNotIn("legacy_probs", original)

    def test_invalid_prior_is_rejected(self):
        for prior in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                model.poisson_lambdas({}, variant="shrunk_form", prior_games=prior)

    def test_future_results_cannot_change_historical_features(self):
        league = history.LeagueHistory.__new__(history.LeagueHistory)
        rows = [{"date": date(2025, 1, day), "home": "A", "away": "B", "gh": 1, "ga": 0}
                for day in range(1, 8)]
        with patch.object(league, "all_matches", side_effect=lambda: rows):
            before = backtest.form_feature(league, "A", "B", date(2025, 1, 8))
            rows.append({"date": date(2025, 1, 8), "home": "A", "away": "B", "gh": 100, "ga": 100})
            rows.append({"date": date(2025, 1, 10), "home": "A", "away": "B", "gh": 100, "ga": 100})
            self.assertEqual(backtest.form_feature(league, "A", "B", date(2025, 1, 8)), before)


if __name__ == "__main__":
    unittest.main()
