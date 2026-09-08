"""仅用本地联赛赛果做按日期推进的历史模型评估，不改校准与预测账本。

每场特征仅由此前日期的赛果形成；前 60% 日期用于建立候选参数的比较起点，
中间 20% 日期选参数，最后 20% 日期只评估一次。没有历史赔率，不评估融合模型。
"""
import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date
from pathlib import Path

from config import CACHE_DIR, N_RECENT
from evaluate import probability_metrics
from history import LeagueHistory
from model import poisson_lambdas, score_matrix_p
from scout import _team_stats, _rest_days


def form_feature(league, home, away, before):
    """与线上使用相同的近期统计、基线和上下文调整。"""
    hr = league.recent(home, before, N_RECENT)
    ar = league.recent(away, before, N_RECENT)
    if min(len(hr), len(ar)) < 6:
        return None
    hs, ast = _team_stats(hr), _team_stats(ar)
    bh, ba = league.league_base(before)
    h2h = league.h2h(home, away, before)
    advantage = ((sum(3 if r["result"] == "胜" else 1 if r["result"] == "平" else 0
                      for r in h2h) / (3 * len(h2h))) - .5) if h2h else None
    return {"home_games": len(hr), "away_games": len(ar),
            "home_home_games": hs["home_games"], "away_away_games": ast["away_games"],
            "home_gf": hs["gf"], "home_ga": hs["ga"],
            "away_gf": ast["gf"], "away_ga": ast["ga"],
            "home_home_gf": hs["gf_home"], "home_home_ga": hs["ga_home"],
            "away_away_gf": ast["gf_away"], "away_away_ga": ast["ga_away"],
            "base_home_goals": bh, "base_away_goals": ba,
            "home_rest": _rest_days(hr, before), "away_rest": _rest_days(ar, before),
            "h2h_home_adv": advantage}


def load_examples(cache_dir=CACHE_DIR):
    by_league = defaultdict(list)
    fingerprints = {}
    for path in sorted(Path(cache_dir).glob("*.json")):
        raw = path.read_bytes()
        fingerprints[path.name] = hashlib.sha256(raw).hexdigest()
        by_league[path.stem.rsplit("-", 1)[0]].extend(json.loads(raw))
    examples = []
    for slug, matches in by_league.items():
        league = LeagueHistory.__new__(LeagueHistory)
        league.curr, league.prev = matches, []
        # 两个缓存重复同一场时只计算一次。
        unique = {(m["date"], m["home"], m["away"]): m for m in league.all_matches()
                  if m["date"] < date.today()}
        rows = sorted(unique.values(), key=lambda m: (m["date"], m["home"], m["away"]))
        league.all_matches = lambda rows=rows: rows
        for row in rows:
            feat = form_feature(league, row["home"], row["away"], row["date"])
            if feat is not None:
                actual = 0 if row["gh"] > row["ga"] else 1 if row["gh"] == row["ga"] else 2
                examples.append({"date": row["date"].isoformat(), "league": slug,
                                 "feat": feat, "actual": actual})
    return sorted(examples, key=lambda row: (row["date"], row["league"])), fingerprints


def score(examples, variant, prior=6):
    samples = [(score_matrix_p(*poisson_lambdas(row["feat"], variant=variant, prior_games=prior)),
                row["actual"]) for row in examples]
    return probability_metrics(samples)


def paired_day_intervals(examples, prior, repetitions=1000):
    """按比赛日期成组重采样，报告候选减原模型的均值差 95% 区间。"""
    groups = defaultdict(list)
    for row in examples:
        old = score_matrix_p(*poisson_lambdas(row["feat"], variant="legacy"))
        new = score_matrix_p(*poisson_lambdas(row["feat"], variant="shrunk_form", prior_games=prior))
        target = row["actual"]
        hit_diff = int(max(range(3), key=lambda i: new[i]) == target) - int(max(range(3), key=lambda i: old[i]) == target)
        brier_diff = sum((new[i] - int(i == target)) ** 2 - (old[i] - int(i == target)) ** 2 for i in range(3))
        loss_diff = math.log(max(old[target], 1e-15)) - math.log(max(new[target], 1e-15))
        groups[row["date"]].append((hit_diff, brier_diff, loss_diff))
    blocks = list(groups.values())
    rng = random.Random(20260908)
    values = [[], [], []]
    for _ in range(repetitions):
        sample = [r for block in rng.choices(blocks, k=len(blocks)) for r in block]
        for i in range(3):
            values[i].append(sum(r[i] for r in sample) / len(sample))
    return {name: [sorted(v)[int(.025 * repetitions)], sorted(v)[min(repetitions - 1, int(.975 * repetitions))]]
            for name, v in zip(("accuracy_delta", "brier_delta", "log_loss_delta"), values)}


def run(cache_dir=CACHE_DIR):
    examples, fingerprints = load_examples(cache_dir)
    days = sorted({row["date"] for row in examples})
    if len(days) < 30:
        raise ValueError("有效比赛日期不足 30 天，无法划分验证与测试期")
    validation_start, test_start = days[int(len(days) * .6)], days[int(len(days) * .8)]
    validation = [r for r in examples if validation_start <= r["date"] < test_start]
    test = [r for r in examples if r["date"] >= test_start]
    candidates = {str(prior): score(validation, "shrunk_form", prior) for prior in (3, 6, 12)}
    selected = min(candidates, key=lambda key: candidates[key]["log_loss"])
    test_legacy = score(test, "legacy")
    test_candidate = score(test, "shrunk_form", int(selected))
    validation_legacy = score(validation, "legacy")
    def better(candidate, baseline):
        return (candidate["brier"] < baseline["brier"]
                and candidate["log_loss"] < baseline["log_loss"]
                and candidate["accuracy"] >= baseline["accuracy"])
    return {"scope": "历史攻防子模型，不含赔率、人工情报和在线复盘校准；缓存赛果未在本轮独立核实",
            "features": "近10场、严格排除同日及未来赛果；参数只在验证期选择",
            "samples": len(examples), "validation_start": validation_start, "test_start": test_start,
            "validation": {"legacy": validation_legacy, "candidates": candidates},
            "selected_prior_games": int(selected),
            "test": {"legacy": test_legacy, "candidate": test_candidate},
            "test_day_bootstrap_95pct": paired_day_intervals(test, int(selected)),
            "passes_point_estimate_gate": better(candidates[selected], validation_legacy)
                                            and better(test_candidate, test_legacy),
            "by_league_test": {slug: {"legacy": score([r for r in test if r["league"] == slug], "legacy"),
                                      "candidate": score([r for r in test if r["league"] == slug], "shrunk_form", int(selected))}
                               for slug in sorted({r["league"] for r in test})},
            "cache_sha256": fingerprints}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/backtest_report.json")
    args = parser.parse_args()
    report = run()
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("cache_sha256", "by_league_test")},
                     ensure_ascii=False, indent=2))
