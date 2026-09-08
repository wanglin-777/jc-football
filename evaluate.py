"""离线评估已存档概率；不抓取数据，不修改预测或校准文件。"""
import json
import math
import argparse
from pathlib import Path

from config import DATA_DIR

LABELS = ["主胜", "平", "客胜"]


def valid_probs(p):
    return (isinstance(p, (list, tuple)) and len(p) == 3
            and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                    and math.isfinite(x) and 0 <= x <= 1 for x in p)
            and abs(sum(p) - 1) <= 0.001)


def probability_metrics(samples):
    """samples = [(三向概率, 实际类别索引)]，Brier 使用三类误差之和。"""
    count = len(samples)
    if not count:
        return {"samples": 0, "accuracy": None, "brier": None, "log_loss": None}
    hits = brier = log_loss = 0
    for p, target in samples:
        p = [x / sum(p) for x in p]
        hits += max(range(3), key=lambda i: p[i]) == target
        brier += sum((x - int(i == target)) ** 2 for i, x in enumerate(p))
        log_loss -= math.log(max(p[target], 1e-15))
    return {"samples": count, "accuracy": hits / count,
            "brier": brier / count, "log_loss": log_loss / count}


def evaluate(data_dir=DATA_DIR, since=None, until=None):
    samples, matched_model, matched_market = [], [], []
    paired_current, paired_legacy = [], []
    skipped = invalid_files = 0
    by_day = {}
    for path in sorted((Path(data_dir) / "history").glob("*.json")):
        if (since and path.stem < since) or (until and path.stem > until):
            continue
        result_path = Path(data_dir) / "verified_cache" / path.name
        if not result_path.exists():
            continue
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            results = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(snapshot, dict) or not isinstance(results, dict):
                raise ValueError("invalid snapshot")
        except (ValueError, OSError):
            invalid_files += 1
            continue
        for item in snapshot.get("items", []):
            actual = results.get(item.get("num"), {}).get("actual")
            if actual not in LABELS:
                continue
            p = item.get("probs") or []
            if not valid_probs(p):
                skipped += 1
                continue
            target = LABELS.index(actual)
            samples.append((p, target))
            by_day.setdefault(path.stem, []).append((p, target))
            market = item.get("market_probs")
            if valid_probs(market):
                matched_model.append((p, target))
                matched_market.append((market, target))
            legacy = item.get("legacy_probs")
            if valid_probs(legacy):
                paired_current.append((p, target))
                paired_legacy.append((legacy, target))
    return {**probability_metrics(samples), "skipped_invalid": skipped,
            "invalid_files": invalid_files,
            "by_day": {day: probability_metrics(rows) for day, rows in by_day.items()},
            "market_comparison": {"model": probability_metrics(matched_model),
                                  "market": probability_metrics(matched_market)},
            "legacy_comparison": {"current": probability_metrics(paired_current),
                                  "legacy": probability_metrics(paired_legacy)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", help="起始销售日 YYYY-MM-DD（包含）")
    parser.add_argument("--until", help="截止销售日 YYYY-MM-DD（包含）")
    args = parser.parse_args()
    print(json.dumps(evaluate(since=args.since, until=args.until), ensure_ascii=False, indent=2))
