import json
import tempfile
import unittest
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import build_site
import dashboard
import evaluate
import history
import model
import source
import verify


def fixture():
    return {"num_str": "周二001", "league_abb": "测试联赛", "home": "主队",
            "away": "客队", "date": "2026-09-08", "time": "18:30:00",
            "had_h": 2.0, "had_d": 3.0, "had_a": 4.0,
            "in_sale": True, "started": False, "data_quality": "odds_only"}


class OfflineTests(unittest.TestCase):
    def test_cache_request_never_fetches(self):
        with patch.object(source, "read_cache", return_value={"matches": []}), \
                patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            self.assertEqual(source.fetch_today(force=False)["matches"], [])
        with patch.object(source, "read_cache", return_value=None):
            with self.assertRaises(RuntimeError):
                source.fetch_today(force=False)

    def test_missing_league_cache_does_not_fetch(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(history, "CACHE_DIR", tmp), \
                patch.object(history, "_http", side_effect=AssertionError("network")):
            self.assertEqual(history._load_slug("missing-2026", offline=True), [])

    def test_offline_render_has_no_network_ai_or_archive_writes(self):
        f = fixture()
        pred = model.predict(f)
        today = {"date": f["date"], "matches": [f]}
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")) as network, \
                patch.object(verify, "store") as archive, \
                patch.object(verify, "_vcache_save") as cache_write, \
                patch.object(build_site.deepseek_client, "chat") as ai, \
                patch.object(build_site.selftune, "update_from_verify") as tune:
            page = build_site.build_html(today, [f], [pred], None, [], "test", offline=True)
            self.assertIn("全部场次概率", page)
            for mock in (network, archive, cache_write, ai, tune):
                mock.assert_not_called()

    def test_render_failure_preserves_previous_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.html"
            index.write_text("previous page", encoding="utf-8")
            with patch.object(build_site, "SITE_DIR", tmp), patch.object(build_site, "INDEX", str(index)), \
                    patch.object(build_site, "_collect", return_value=({"date": "2026-09-08", "matches": []}, [], [], None, [])), \
                    patch.object(build_site, "build_html", side_effect=ValueError("render failed")):
                self.assertEqual(build_site.main(), 1)
                self.assertEqual(index.read_text(encoding="utf-8"), "previous page")


class ArchiveTests(unittest.TestCase):
    def test_kickoff_freezes_original_prediction(self):
        f = fixture()
        pred = model.predict(f)
        with tempfile.TemporaryDirectory() as tmp, patch.object(verify, "HIST_DIR", tmp), \
                patch.object(verify, "export_csv"):
            verify.store(f["date"], [f], [pred], None, now=datetime(2026, 9, 8, 18, 0))
            path = Path(tmp) / "2026-09-08.json"
            before = json.loads(path.read_text(encoding="utf-8"))
            changed = dict(pred, pick="客胜", home=.1, draw=.2, away=.7)
            verify.store(f["date"], [f], [changed], None, now=datetime(2026, 9, 8, 18, 30))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), before)
            item = before["items"][0]
            self.assertEqual(item["features"]["home"], "主队")
            self.assertEqual(len(item["market_probs"]), 3)
            self.assertLess(item["predicted_at"], item["kickoff"])

    def test_no_post_match_backfill(self):
        f = fixture()
        with tempfile.TemporaryDirectory() as tmp, patch.object(verify, "HIST_DIR", tmp), \
                patch.object(verify, "export_csv"):
            verify.store(f["date"], [f], [model.predict(f)], None, now=datetime(2026, 9, 9))
            self.assertFalse((Path(tmp) / "2026-09-08.json").exists())

    def test_league_baseline_excludes_future_and_match_day(self):
        league = history.LeagueHistory.__new__(history.LeagueHistory)
        with patch.object(league, "all_matches", return_value=[
            {"date": date(2025, 1, 1), "gh": 1, "ga": 0},
            {"date": date(2025, 1, 2), "gh": 9, "ga": 8},
            {"date": date(2025, 1, 3), "gh": 10, "ga": 10}]):
            self.assertEqual(league.league_base(date(2025, 1, 2)), (1, 0))


class EvaluationTests(unittest.TestCase):
    def test_away_head_to_head_draw_is_not_win(self):
        league = history.LeagueHistory.__new__(history.LeagueHistory)
        with patch.object(league, "all_matches", return_value=[
            {"date": date(2025, 1, 1), "home": "B", "away": "A", "gh": 1, "ga": 1}]):
            self.assertEqual(league.h2h("A", "B", date(2025, 1, 2))[0]["result"], "平")

    def test_known_metrics(self):
        perfect = evaluate.probability_metrics([([1, 0, 0], 0)])
        self.assertEqual(perfect["brier"], 0)
        self.assertEqual(perfect["log_loss"], 0)
        self.assertAlmostEqual(evaluate.probability_metrics([([1/3]*3, 0)])["brier"], 2/3)

    def test_market_comparison_uses_same_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            for folder in ("history", "verified_cache"):
                (Path(tmp) / folder).mkdir()
            (Path(tmp) / "history" / "2026-09-07.json").write_text(json.dumps({"items": [
                {"num": "001", "probs": [.7, .2, .1], "market_probs": [.5, .3, .2]},
                {"num": "002", "probs": [.1, .2, .7]}]}), encoding="utf-8")
            (Path(tmp) / "verified_cache" / "2026-09-07.json").write_text(json.dumps({
                "001": {"actual": "主胜"}, "002": {"actual": "客胜"}}), encoding="utf-8")
            result = evaluate.evaluate(tmp)
            self.assertEqual(result["samples"], 2)
            comparison = result["market_comparison"]
            self.assertEqual(comparison["model"]["samples"], 1)
            self.assertEqual(comparison["market"]["samples"], 1)
            self.assertLess(comparison["model"]["brier"], comparison["market"]["brier"])
            self.assertEqual(evaluate.evaluate(tmp, since="2026-09-08")["samples"], 0)


class MarkupTests(unittest.TestCase):
    def test_untrusted_team_names_are_escaped(self):
        f = fixture()
        f["home"] = '<script>alert("x")</script>'
        markup = dashboard.match_explorer([f], [model.predict(f)])
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)

    def test_empty_state_and_unique_ids(self):
        class IdParser(HTMLParser):
            ids = []
            def handle_starttag(self, tag, attrs):
                self.ids.extend(value for key, value in attrs if key == "id")
        markup = dashboard.match_explorer([], [])
        parser = IdParser()
        parser.feed(markup)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertIn("暂无符合条件的比赛", markup)


if __name__ == "__main__":
    unittest.main()
