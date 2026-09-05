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
from config import COMBO_MIN_ODDS, COMBO_LEGS, N_RECOMMEND
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


def recommend(feats, preds, min_prob=0.45):
    """
    输入: feats(每场特征), preds(每场 model.predict 结果)
    返回: {"candidates": 单场稳胆池(按胜率降序),
           "combos":  5组两串一(按联合胜率降序)}
    """
    pool = []
    for f, pr in zip(feats, preds):
        if not (f.get("had_h") and f.get("had_d") and f.get("had_a")):
            continue                      # 未开胜平负(如部分强弱悬殊场)不参与
        leg = pick_best_leg(f, pr)
        if leg and leg["prob"] >= min_prob:
            pool.append({"feat": f, "pred": pr, **leg})
    # 候选池按单场模型胜率降序
    pool.sort(key=lambda x: x["prob"], reverse=True)

    # 枚举两两组合
    cand = []
    for a, b in itertools.combinations(pool, COMBO_LEGS):
        odds = a["odds"] * b["odds"]
        if odds < COMBO_MIN_ODDS - 1e-9:
            continue
        joint = a["prob"] * b["prob"]
        cand.append({"a": a, "b": b, "odds": odds, "joint": joint})
    cand.sort(key=lambda x: x["joint"], reverse=True)

    # 贪心挑选 N_RECOMMEND 组, 每支球队/每场比赛最多出现在 2 组中保证多样
    used = {}
    combos = []
    for c in cand:
        if len(combos) >= N_RECOMMEND:
            break
        keys = (c["a"]["feat"]["num_str"], c["b"]["feat"]["num_str"])
        if any(used.get(k, 0) >= 2 for k in keys):
            continue
        # 排除"同一场比赛选两次"的不可能情形(组合本身保证不同场)
        for k in keys:
            used[k] = used.get(k, 0) + 1
        combos.append(_format_combo(c))
    return {"candidates": pool, "combos": combos}


def _format_combo(c):
    legs = []
    for x in (c["a"], c["b"]):
        f = x["feat"]
        side = "主" if x["pick"] == "主胜" else ("平" if x["pick"] == "平" else "客")
        legs.append({
            "num": f["num_str"], "league": f["league_abb"], "time": f["time"],
            "home": f["home"], "away": f["away"],
            "pick": x["pick"], "pick_short": f"{f['home']}vs{f['away']}选{side}",
            "prob": x["prob"], "odds": x["odds"], "source": x["source"],
            "home_rank": f.get("home_rank"), "away_rank": f.get("away_rank"),
            "home_summary": f.get("home_summary"), "away_summary": f.get("away_summary"),
        })
    return {"legs": legs, "odds": round(c["odds"], 2),
            "joint": round(c["joint"], 4)}
