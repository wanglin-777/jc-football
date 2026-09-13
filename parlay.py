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
from config import (AVOID_AWAY_FORM_MAX, AVOID_AWAY_RANK_MIN, AVOID_SHORT_ODDS_MAX,
                    BANKER_MAX_ODDS, BANKER_MIN_PROB, BANKER_REQUIRE_VERIFY,
                    COMBO_MARGIN_TIERS, COMBO_MIN_ODDS, COMBO_LEGS,
                    MIN_PROB_LEG, N_RECOMMEND)
import itertools
import re


def _rank_num(s):
    if not s:
        return None
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else None


def _avoid_reason(x):
    """建议2: 强队主场 + 赔率偏低 + 对手有保级/反弹动机 -> 不建议纳入串关"""
    f = x["feat"]
    if x["pick"] != "主胜" or x["odds"] > AVOID_SHORT_ODDS_MAX:
        return ""
    ark = _rank_num(f.get("away_rank"))
    aform = f.get("away_win_w")
    why = []
    if ark is not None and ark >= AVOID_AWAY_RANK_MIN:
        why.append(f"客队排名{ark}(保级区/低位)")
    if aform is not None and aform <= AVOID_AWAY_FORM_MAX:
        why.append(f"客队状态差(胜率{aform:.0%}, 有反弹动机)")
    if not why:
        return ""
    return "强队主场低赔(" + f"{x['odds']:.2f}" + ") × " + "、".join(why)


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
    策略(稳定优先, 不足按稳定度补满):
      - 胆材: 仅 胜率≥BANKER_MIN_PROB 且 赔率≤BANKER_MAX_ODDS 且非高风险
      - 串关: 枚举所有"两腿都≥MIN_PROB_LEG + 串后赔率≥2 + 两腿胜率差≥5%"的组合,
        先按"稳定度"(两腿中较险一腿的风险档: 低>中>高)从高到低排, 同稳定度再按联合胜率降序,
        贪心补齐到 N_RECOMMEND(5) 组——低风险优先, 不够 5 组时才把风险更高的排进来补满。
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
    for x in full:
        x["avoid"] = _avoid_reason(x)

    # 建议1: 做胆门槛——胜率>=BANKER_MIN_PROB 且 赔率<=BANKER_MAX_ODDS 且 非高风险
    #        且通过"近期状态(完整情报)+伤停/动机(手动情报)"核验; 未通过 -> 观望
    bankers, watch = [], []
    for x in full:
        if x["prob"] < BANKER_MIN_PROB or x["odds"] > BANKER_MAX_ODDS:
            continue
        verified = (x["feat"].get("data_quality") == "full"
                    and bool(x["feat"].get("intel_note")))
        if x["risk"] == "低" and (verified or not BANKER_REQUIRE_VERIFY):
            bankers.append(x)
        else:
            miss = []
            if x["feat"].get("data_quality") != "full":
                miss.append("近期情报不足")
            if not x["feat"].get("intel_note"):
                miss.append("缺伤停/动机核验")
            if x["risk"] != "低":
                miss.append(f"爆冷风险{x['risk']}")
            x["watch_reason"] = "、".join(miss) or "未通过核验"
            watch.append(x)

    # 建议2: 枚举候选串(两腿都>=MIN_PROB_LEG, 串后赔率>=2, 胜率差>=5%; 剔除"避免"场)
    cand = []
    for a, b in itertools.combinations(full, COMBO_LEGS):
        odds = a["odds"] * b["odds"]
        if odds < COMBO_MIN_ODDS - 1e-9:
            continue
        if min(a["margin"], b["margin"]) < 0.05:
            continue
        s = {"低": 3, "中": 2, "高": 1}
        stab = min(s.get(a["risk"], 1), s.get(b["risk"], 1))  # 较险一腿决定稳定度
        avoided = bool(a.get("avoid")) or bool(b.get("avoid"))
        cand.append((a, b, odds, a["prob"] * b["prob"], stab, avoided))

    def _take(items):
        """按稳定度+联合胜率选组(多样性: 每场最多出现在2组)"""
        items = sorted(items, key=lambda t: (-t[4], -t[3]))
        used, out = {}, []
        for a, b, odds, joint, stab, avoided in items:
            if len(out) >= N_RECOMMEND:
                break
            keys = (a["feat"]["num_str"], b["feat"]["num_str"])
            if any(used.get(k, 0) >= 2 for k in keys):
                continue
            for k in keys:
                used[k] = used.get(k, 0) + 1
            cb = _format_combo({"a": a, "b": b, "odds": odds, "joint": joint})
            cb["avoided"] = avoided
            out.append(cb)
        return out

    combos = _take([c for c in cand if not c[5]])      # 先完全剔除"避免"场
    if not combos:                                     # 全被剔除时兜底(明确标注)
        combos = _take(cand)

    return {"candidates": full, "bankers": bankers, "watch": watch,
            "avoid": [x for x in full if x.get("avoid")], "combos": combos}


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
