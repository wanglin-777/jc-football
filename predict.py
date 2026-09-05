# -*- coding: utf-8 -*-
"""
竞彩足球 - 命令行预测入口
=========================
一键完成: 抓当日竞彩 -> 合成两队情报 -> 胜平负概率预测 -> 输出5组"两串一"推荐。

用法:
    python predict.py            # 使用本地缓存(离线也行)
    python predict.py --force    # 强制联网刷新官方赔率
    python predict.py --json     # 额外把完整结果写到 data/predict_report.json
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402
from datetime import date  # noqa: E402

import model  # noqa: E402
import parlay  # noqa: E402
import scout  # noqa: E402
from config import DATA_DIR  # noqa: E402
from source import fetch_today  # noqa: E402


def run(force=False, with_json=False):
    today = fetch_today(force=force)
    ms = today["matches"]
    feats = scout.build_features(ms)

    # 预测: 只对开出"胜平负"赔率的场次出概率
    pred_map = {}
    for f in feats:
        if f["had_h"] and f["had_d"] and f["had_a"]:
            pred_map[f["num_str"]] = model.predict(f)

    ordered = [f for f in feats if f["num_str"] in pred_map]
    preds = [pred_map[f["num_str"]] for f in ordered]
    rec = parlay.recommend(ordered, preds)

    report = {
        "date": today["date"],
        "generated": str(date.today()),
        "total": len(ms),
        "predictable": len(ordered),
        "matches": [],
        "candidates": [],
        "combos": [],
    }
    lines = []
    lines.append("=" * 70)
    lines.append(f"竞彩足球 {today['date']} 在售 {len(ms)} 场, 可预测(开胜平负) {len(ordered)} 场")
    lines.append("=" * 70)

    lines.append("\n【一】全部场次(按模型胜率高的最稳选项降序) ----------")
    top = sorted(ordered, key=lambda f: pred_map[f["num_str"]]["pick_p"], reverse=True)
    for f in top:
        pr = pred_map[f["num_str"]]
        q = f.get("data_quality", "")
        lines.append(f"  {f['num_str']} [{f['league_abb']}] {f['home']} vs {f['away']} "
                     f"-> 荐{f['home'] if pr['pick']=='主胜' else (f['away'] if pr['pick']=='客胜' else '平')} "
                     f"胜率{pr['pick_p']:.0%} 赔率{pr.get('pick_odds')} "
                     f"({pr['source']}, {q})")
        report["matches"].append({
            "num": f["num_str"], "league": f["league_abb"], "home": f["home"],
            "away": f["away"], "pick": pr["pick"], "prob": pr["pick_p"],
            "odds": pr.get("pick_odds"), "source": pr["source"],
            "quality": q, "had": [f["had_h"], f["had_d"], f["had_a"]],
            "probs": [pr["home"], pr["draw"], pr["away"]],
        })

    lines.append("\n【二】单场稳胆池(模型胜率门槛以上) ----------")
    for c in rec["candidates"]:
        f = c["feat"]
        lines.append(f"  {f['num_str']} [{f['league_abb']}] {f['home']}vs{f['away']} "
                     f"选{c['pick']} 胜率{c['prob']:.0%} 赔率{c['odds']:.2f}")
        report["candidates"].append({
            "num": f["num_str"], "league": f["league_abb"], "home": f["home"],
            "away": f["away"], "pick": c["pick"], "prob": round(c["prob"], 4),
            "odds": round(c["odds"], 2),
        })

    lines.append(f"\n【三】五大「两串一」推荐(串后赔率>=2.0, 按联合胜率排序) ----------")
    for i, cb in enumerate(rec["combos"], 1):
        ls = "  ×  ".join(f"{l['num']} {l['pick_short']}({l['prob']:.0%}, {l['odds']:.2f})"
                          for l in cb["legs"])
        lines.append(f"  TOP{i}: 联合胜率 {cb['joint']:.1%}  串后赔率 {cb['odds']:.2f}")
        lines.append(f"        {ls}")
        for l in cb["legs"]:
            lines.append(f"        └ {l['pick_short']}: {l['home_summary']} | {l['away_summary']}")
        report["combos"].append({
            "rank": i, "odds": cb["odds"], "joint": cb["joint"],
            "legs": [{"num": l["num"], "home": l["home"], "away": l["away"],
                      "pick": l["pick"], "prob": l["prob"], "odds": l["odds"],
                      "home_summary": l.get("home_summary"), "away_summary": l.get("away_summary")}
                     for l in cb["legs"]],
        })

    if not rec["combos"]:
        lines.append("  (没有足够的满足条件组合: 请检查数据覆盖或调低门槛)")

    lines.append("\n免责声明: 以上为基于历史数据与赔率的统计估计, 仅供研究参考, 不构成投注建议;")
    lines.append("足球比赛充满偶然性, 请理性购彩、量力而行。")
    text = "\n".join(lines)
    print(text)
    # 纯文本报告另存 UTF-8(供离线查看/终端乱码时读取)
    with open(os.path.join(DATA_DIR, "predict_report.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    if with_json:
        with open(os.path.join(DATA_DIR, "predict_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    return report, text


if __name__ == "__main__":
    force = "--force" in sys.argv
    with_json = "--json" in sys.argv
    run(force=force, with_json=with_json)
