# -*- coding: utf-8 -*-
"""
预测验证 / 复盘 (verify.py)
============================
功能:
  1) 把每个销售日的预测快照存档到 data/history/<日期>.json
  2) 等该日比赛结束后, 用历史赛果库(fixturedownload, 已接入联赛)自动比对:
       - 每场: 预测选项 vs 实际胜平负 -> 命中? 赔率回报
       - 五大串关方案: 两场都命中才算中
       - 汇总: 命中场数/命中率/单关净回报
  说明: 西甲/葡超/挪超/巴甲/沙职等未接入历史结果库的联赛, 无法自动核验,
        会如实标注"缺结果源"; 后续若接入更多联赛结果即可自动覆盖。
"""
import glob
import json
import os
from datetime import date, timedelta

from config import DATA_DIR, LEAGUE_ABB_TO_CODE, LEAGUE_FEED
from history import get_league
from team_map import CH_TO_EN

HIST_DIR = os.path.join(DATA_DIR, "history")
KEEP_DAYS = 30          # 验证页最多展示最近多少天


# ---------------- 存档 ----------------
def store(sales_date, ordered, preds, rec):
    """把当天预测快照存到 data/history/<sales_date>.json(同一天多次生成则覆盖为最新)"""
    if not sales_date or not ordered:
        return
    os.makedirs(HIST_DIR, exist_ok=True)
    items = []
    for f, pr in zip(ordered, preds):
        items.append({
            "num": f["num_str"], "league_abb": f["league_abb"],
            "league_code": LEAGUE_ABB_TO_CODE.get(f["league_abb"], f.get("league_code", "")),
            "home": f["home"], "away": f["away"],
            "pick": pr["pick"], "probs": [pr["home"], pr["draw"], pr["away"]],
            "odds": pr.get("pick_odds"), "source": pr["source"],
            "quality": f.get("data_quality", ""),
        })
    combos = []
    for cb in (rec or {}).get("combos", []):
        combos.append({
            "odds": cb["odds"], "joint": cb["joint"], "risk": cb.get("risk", "低"),
            "legs": [{"num": l["num"], "pick": l["pick"]} for l in cb["legs"]],
        })
    data = {"date": sales_date, "n": len(items), "items": items, "combos": combos}
    path = os.path.join(HIST_DIR, f"{sales_date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _load_dates():
    paths = sorted(glob.glob(os.path.join(HIST_DIR, "*.json")), reverse=True)
    out = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("date") and d.get("items"):
                out.append(d)
        except Exception:
            continue
        if len(out) >= KEEP_DAYS:
            break
    return out


# ---------------- 结果获取 ----------------
def _results_for(slug, d0, d1):
    """返回该联赛在 [d0,d1] 已开赛结果的查找表 {(home,away):{gf,ga}}"""
    try:
        lh = get_league(slug)
    except Exception:
        return {}
    if not lh.available:
        return {}
    table = {}
    for x in lh.all_matches():
        if d0 <= x["date"] <= d1:
            table[(x["home"], x["away"])] = {"gf": x["gh"], "ga": x["ga"]}
    return table


def _actual_label(gf, ga):
    return "主胜" if gf > ga else ("平" if gf == ga else "客胜")


def verify_all(now=None):
    """遍历历史存档, 返回每日的验证数据 [{date, rows:[...], stats:{...}, combos:[...]}]"""
    if now is None:
        now = date.today()
    res = []
    for snap in _load_dates():
        try:
            d = date.fromisoformat(snap["date"])
        except Exception:
            continue
        rows = []
        # 每个联赛只取一次结果表
        cache = {}
        for it in snap.get("items", []):
            league_abb = it.get("league_abb", "")
            code = it.get("league_code") or LEAGUE_ABB_TO_CODE.get(league_abb, "")
            slug = LEAGUE_FEED.get(code, (None, None))[0]
            he = CH_TO_EN.get(it.get("home", ""))
            ae = CH_TO_EN.get(it.get("away", ""))
            row = {"num": it.get("num"), "league": league_abb,
                   "home": it.get("home"), "away": it.get("away"),
                   "pick": it.get("pick"), "odds": it.get("odds"),
                   "probs": it.get("probs"), "actual": None, "hit": None,
                   "status": "缺结果源" if not (slug and he and ae) else "待开奖"}
            if slug and he and ae:
                key = (slug, d)
                if key not in cache:
                    cache[key] = _results_for(slug, d, d + timedelta(days=1))
                m = cache[key].get((he, ae))
                if m:
                    row["actual"] = _actual_label(m["gf"], m["ga"])
                    row["hit"] = (row["actual"] == row["pick"])
                    row["status"] = "已核验"
                else:
                    # 比赛日太早还没开赛/没收录
                    if (now - d) > timedelta(days=3):
                        row["status"] = "未找到结果"
                    else:
                        row["status"] = "待开奖"
            rows.append(row)

        # 统计(只算已核验)
        verified = [r for r in rows if r["hit"] is not None]
        hits = sum(1 for r in verified if r["hit"])
        net = 0.0
        for r in verified:
            net += (r["odds"] - 1.0) if r["hit"] else -1.0
        stats = {"total": len(rows), "verified": len(verified), "hits": hits,
                 "rate": (hits / verified) if verified else None,
                 "roi": net}   # 每场按1注的净回报(单位:元)

        # 串关验证(两场均已核验且都命中)
        combos = []
        for cb in snap.get("combos", []):
            legs = []
            known = True
            for leg in cb.get("legs", []):
                r = next((x for x in rows if x["num"] == leg["num"]), None)
                leginfo = {"num": leg["num"], "pick": leg["pick"],
                           "actual": r["actual"] if r else None,
                           "ok": bool(r and r["actual"] and r["actual"] == leg["pick"])}
                legs.append(leginfo)
                if not r or not r["actual"]:
                    known = False
            combos.append({"odds": cb.get("odds"), "risk": cb.get("risk", "低"),
                           "legs": legs, "known": known,
                           "win": known and all(l["ok"] for l in legs)})

        # 串关口径: 五组两串一, 每组下1注; 两组都命中→赢(赔率-1), 否则输1注
        c_known = [c for c in combos if c.get("known")]
        c_win = sum(1 for c in c_known if c.get("win"))
        c_net = 0.0
        for c in c_known:
            c_net += (c["odds"] - 1.0) if c.get("win") else -1.0
        stats["combo_total"] = len(combos)
        stats["combo_known"] = len(c_known)
        stats["combo_win"] = c_win
        stats["combo_roi"] = c_net      # 串关净回报(每组按1注)
        res.append({"date": snap["date"], "rows": rows, "stats": stats,
                    "combos": combos, "n_pred": len(rows)})
    return res


# ---------------- 自我复盘(多日汇总) ----------------
def _pick_p(probs, pick):
    try:
        idx = {"主胜": 0, "平": 1, "客胜": 2}.get(pick, 0)
        return probs[idx] if probs and len(probs) == 3 else None
    except Exception:
        return None


BUCKETS = [(0.30, 0.40, "30-40%"), (0.40, 0.50, "40-50%"), (0.50, 0.60, "50-60%"),
           (0.60, 0.70, "60-70%"), (0.70, 0.80, "70-80%"), (0.80, 1.01, "80%以上")]


def aggregate(vdata):
    """对多日验证结果做模型自我复盘汇总(校准/翻车/以小博大/串关)"""
    all_rows, all_combos, dates = [], [], []
    for d in vdata:
        dates.append(d["date"])
        all_rows += [r for r in d["rows"] if r.get("hit") is not None]
        all_combos += d.get("combos", [])

    hits = sum(1 for r in all_rows if r["hit"])
    total = len(all_rows)
    by_pick = {}
    for r in all_rows:
        k = r.get("pick", "?")
        b = by_pick.setdefault(k, [0, 0])
        b[0] += 1
        if r["hit"]:
            b[1] += 1

    buckets = []
    for lo, hi, lab in BUCKETS:
        rows_in = []
        for r in all_rows:
            p = _pick_p(r.get("probs"), r.get("pick"))
            if p is not None and lo <= p < hi:
                rows_in.append(r)
        if rows_in:
            n = len(rows_in)
            h = sum(1 for r in rows_in if r["hit"])
            buckets.append({"lab": lab, "n": n, "hit": h, "rate": h / n,
                            "over": (h / n) < (lo + 0.02)})
    miss_high = [r for r in all_rows
                 if not r["hit"] and (p := _pick_p(r.get("probs"), r.get("pick"))) is not None
                 and p >= 0.60]
    miss_high.sort(key=lambda r: -(_pick_p(r.get("probs"), r.get("pick")) or 0))
    coups = [r for r in all_rows if r["hit"] and r.get("odds") and r["odds"] >= 2.0]
    coups.sort(key=lambda r: -(r.get("odds") or 0))

    ck = [c for c in all_combos if c.get("known")]
    cwin = sum(1 for c in ck if c.get("win"))
    cnet = sum((c.get("odds", 1) - 1) if c.get("win") else -1 for c in ck)
    return {"days": dates, "total": total, "hits": hits,
            "rate": (hits / total) if total else None,
            "by_pick": by_pick, "buckets": buckets,
            "miss_high": miss_high[:5], "coups": coups[:5],
            "combo_known": len(ck), "combo_win": cwin, "combo_net": cnet}
