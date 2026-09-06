# -*- coding: utf-8 -*-
"""
两串一推荐算法
==============
规则(按需求):
  1. 只串两关(从不同的两场比赛中各选一个胜平负选项)
  2. 串后赔率 = 两场选项赔率相乘, 必须 >= 2.0
  3. 单场选项优先选模型胜率最高者(且满足最低胜率门槛)
  4. 输出 5 组"胜率最高"的两串一: 按两场联合胜率(p1*p2)从高到低

算法:
  先把每场"最稳选项"组成候选池(按单场模型胜率降序),
  再在所有两两组合中枚举满足 串后赔率>=2 的组合,
  按联合胜率排序, 贪心挑选同时兼顾"每支球队最多出现在两组串关中"的多样性。
"""
from config import (BANKER_MAX_ODDS, BANKER_MIN_PROB, COMBO_MARGIN_TIERS,
                    COMBO_MIN_ODDS, COMBO_LEGS, MIN_PROB_LEG, N_RECOMMEND)
import itertools


def pick_best_leg(feat, pred):
    """单场最优选项: 必须开售胜平负且有赔率; 取模型概率最高的结果"""
    odds = {"主胜": feat.get("had_h"), "平": feat.get("had_d"), "客胜": feat.get("had_a")}
    p = {"主胜": pred["home"], "平": pred["draw"], "客胜": pred["away"]}
    o = odds[pred["pick"]]
    if not o:
        return None
    return {"pick": pred["pick"], "prob": pred["pick_p"], "odds": o,
            "probs": [pred["home"], pred["draw"], pred["away"]],
            "source": pred["source"]}


def recommend(feats, preds, min_prob=MIN_PROB_LEG):
    """
    输入: feats(每场特征), preds(每场 model.predict 结果)
    返回: {"candidates": 全部候选(按胜率降序), "bankers": 严格单关胆材,
           "combos":  两串一(按联合胜率降序, 宁缺毋滥)}
    策略(稳定优先):
      - 胆材: 仅 胜率≥BANKER_MIN_PROB 且 赔率≤BANKER_MAX_ODDS 且非高风险
      - 串关: 默认只接受"低爆冷风险 + 胜率差≥COMBO_MARGIN_TIERS[0](25%)"的腿;
        若该严格档凑不出任一组, 才逐级放宽(18%/10% 仍只限低风险 → 4% 允许中等风险
        → 2% 才最后兜底允许高风险)。宁肯某天少出几组, 也不硬凑高风险串。
    """
    full = []
    for f, pr in zip(feats, preds):
        if not (f.get("had_h") and f.get("had_d") and f.get("had_a")):
            continue                      # 未开胜平负(如部分强弱悬殊场)不参与
        leg = pick_best_leg(f, pr)
        if leg and leg["prob"] >= min_prob:
            probs = leg["probs"] or []
            second = sorted(probs, reverse=True)[1] if len(probs) >= 2 else 0.0
            risk = (pr.get("upset") or {}).get("risk", "低")
            full.append({"feat": f, "pred": pr, **leg,
                         "margin": leg["prob"] - second, "risk": risk})
    full.sort(key=lambda x: x["prob"], reverse=True)

    # 严格单关胆材: 非高风险(仅用于展示, 不参与串关)
    bankers = [x for x in full
               if x["prob"] >= BANKER_MIN_PROB
               and x["odds"] <= BANKER_MAX_ODDS
               and x["risk"] == "低"]

    def make_combos(pool):
        cand = []
        for a, b in itertools.combinations(pool, COMBO_LEGS):
            odds = a["odds"] * b["odds"]
            if odds < COMBO_MIN_ODDS - 1e-9:
                continue
            cand.append((a, b, odds, a["prob"] * b["prob"]))
        cand.sort(key=lambda t: t[3], reverse=True)
        used = {}
        combos = []
        for a, b, odds, joint in cand:
            if len(combos) >= N_RECOMMEND:
                break
            keys = (a["feat"]["num_str"], b["feat"]["num_str"])
            if any(used.get(k, 0) >= 2 for k in keys):
                continue
            for k in keys:
                used[k] = used.get(k, 0) + 1
            combos.append(_format_combo({"a": a, "b": b, "odds": odds,
                                         "joint": joint}))
        return combos

    # 稳定优先的逐级筛选: 先从最严档取, 该档一旦有解就不再放宽去追 5 组
    rk = {"低": 0, "中": 1, "高": 2}
    stages = [(m, "低") for m in COMBO_MARGIN_TIERS]
    stages += [(0.04, "中"), (0.02, "高")]
    best = None
    for m, allow in stages:
        pool = [x for x in full
                if x["margin"] >= m and rk.get(x["risk"], 0) <= rk[allow]]
        c = make_combos(pool)
        if c:
            best = c
            break
    return {"candidates": full, "bankers": bankers, "combos": best or []}


def _upset_digest(x):
    """把爆冷分析压成一行短提示(供串关/网页显示)"""
    u = (x.get("pred") or {}).get("upset") or {}
    if not u.get("hot"):
        return "无明显大热, 双方较接近", "低"
    risk = u.get("risk", "低")
    txt = (f"大热{u.get('fav_team','')}不胜(防冷)概率 {u.get('no_win_p',0):.0%} "
           f"· 直接输 {u.get('upset_win_p',0):.0%} · 风险[{risk}]")
    return txt, risk


def _format_combo(c):
    legs = []
    combo_risk = "低"
    for x in (c["a"], c["b"]):
        f = x["feat"]
        side = "主" if x["pick"] == "主胜" else ("平" if x["pick"] == "平" else "客")
        u_txt, u_risk = _upset_digest(x)
        if u_risk == "高":
            combo_risk = "高"
        elif u_risk == "中" and combo_risk != "高":
            combo_risk = "中"
        legs.append({
            "num": f["num_str"], "league": f["league_abb"], "time": f["time"],
            "home": f["home"], "away": f["away"],
            "pick": x["pick"], "pick_short": f"{f['home']}vs{f['away']}选{side}",
            "prob": x["prob"], "odds": x["odds"], "source": x["source"],
            "home_rank": f.get("home_rank"), "away_rank": f.get("away_rank"),
            "home_summary": f.get("home_summary"), "away_summary": f.get("away_summary"),
            "upset_text": u_txt, "upset_risk": u_risk,
        })
    return {"legs": legs, "odds": round(c["odds"], 2),
            "joint": round(c["joint"], 4), "risk": combo_risk}
