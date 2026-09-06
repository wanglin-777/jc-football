# -*- coding: utf-8 -*-
"""
预测验证 / 复盘 (verify.py)
============================
功能:
  1) 把每个销售日的预测快照存档到 data/history/<日期>.json
  2) 等该日比赛结束后, 自动比对"预测选项 vs 实际胜平负":
       - 首选: 竞彩口径快源 okooo(okooo_results.py, 覆盖所有竞彩联赛,
               含日职/韩职/挪超/巴甲/沙职等, 完场即出, 与体彩同套场次/队名)
       - 回退: fixturedownload 联赛历史库(history.py, 已接入联赛)
       - 每场: 命中? 赔率回报; 五大串关方案: 两场都命中才算中
"""
import glob
import json
import os
import re
from datetime import date, timedelta

import okooo_results
from config import DATA_DIR, LEAGUE_ABB_TO_CODE, LEAGUE_FEED
from history import get_league
from team_map import CH_TO_EN

HIST_DIR = os.path.join(DATA_DIR, "history")
VERIFY_CACHE_DIR = os.path.join(DATA_DIR, "verified_cache")
KEEP_DAYS = 30          # 验证页最多展示最近多少天


# ---------------- 已验证结果本地缓存 ----------------
def _vcache_load(d):
    """读某销售日的已验证结果缓存: {num: {actual, hit, score}}"""
    try:
        with open(os.path.join(VERIFY_CACHE_DIR, f"{d}.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _vcache_save(d, rows):
    """把当天已核验的场次缓存下来(源临时不可用时页面/校准仍可用)"""
    items = {}
    for r in rows:
        if r.get("actual"):
            items[r.get("num")] = {"actual": r["actual"],
                                    "hit": bool(r.get("hit")),
                                    "score": r.get("score")}
    if not items:
        return
    try:
        os.makedirs(VERIFY_CACHE_DIR, exist_ok=True)
        with open(os.path.join(VERIFY_CACHE_DIR, f"{d}.json"), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
    except Exception:
        pass



# ---------------- 存档 ----------------
def store(sales_date, ordered, preds, rec):
    """把当天预测快照存到 data/history/<sales_date>.json(同一天多次生成则覆盖为最新)"""
    if not sales_date or not ordered:
        return
    os.makedirs(HIST_DIR, exist_ok=True)
    items = []
    for f, pr in zip(ordered, preds):
        g = pr.get("goals") if isinstance(pr, dict) else None
        items.append({
            "num": f["num_str"], "league_abb": f["league_abb"],
            "league_code": LEAGUE_ABB_TO_CODE.get(f["league_abb"], f.get("league_code", "")),
            "home": f["home"], "away": f["away"],
            "pick": pr["pick"], "probs": [pr["home"], pr["draw"], pr["away"]],
            "odds": pr.get("pick_odds"), "source": pr["source"],
            "quality": f.get("data_quality", ""),
            "goals": ({"pick": g["pick"], "p": g["p"], "pick2": g.get("pick2"),
                       "p2": g.get("p2"), "avg": g["avg"],
                       "probs": g["probs"]} if g else None),
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
    # 同时生成方便阅读的 CSV(GitHub 可直接预览, Excel/WPS 可直接打开)
    export_csv(data)


def export_csv(snap):
    """把某日预测导出成 CSV: 每天一份 + 全量汇总(都在 data/history_csv/)"""
    import csv as _csv
    csv_dir = os.path.join(DATA_DIR, "history_csv")
    os.makedirs(csv_dir, exist_ok=True)
    cols = ["日期", "场次", "联赛", "主队", "客队", "推荐", "主胜%", "平局%", "客胜%", "赔率", "来源", "情报"]
    rows = []
    for it in snap.get("items", []):
        p = it.get("probs") or []
        rows.append([snap.get("date", ""), it.get("num", ""), it.get("league_abb", ""),
                     it.get("home", ""), it.get("away", ""), it.get("pick", ""),
                     _pct(p[0]), _pct(p[1]), _pct(p[2]),
                     it.get("odds", ""), it.get("source", ""), it.get("quality", "")])
    # 每天一份
    per = os.path.join(csv_dir, f"预测_{snap.get('date','')}.csv")
    with open(per, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    # 全量汇总(每次重写为全部历史)
    all_path = os.path.join(csv_dir, "历史预测_全量.csv")
    with open(all_path, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.writer(f)
        w.writerow(cols)
        for snap_old in _load_dates():
            for it in snap_old.get("items", []):
                p = it.get("probs") or []
                w.writerow([snap_old.get("date", ""), it.get("num", ""),
                            it.get("league_abb", ""), it.get("home", ""), it.get("away", ""),
                            it.get("pick", ""), _pct(p[0]), _pct(p[1]), _pct(p[2]),
                            it.get("odds", ""), it.get("source", ""), it.get("quality", "")])


def _pct(x):
    try:
        return f"{float(x):.1%}"
    except Exception:
        return ""


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


# ---------------- 结果获取(验证时强制拉取最新赛果) ----------------
_TABLES = {}


def _result_table(slug):
    if slug not in _TABLES:
        try:
            lh = get_league(slug, force=True)   # 强制联网拿最新赛果(避免用旧缓存)
        except Exception:
            lh = None
        tab = {}
        if lh is not None and lh.available:
            for x in lh.all_matches():
                tab.setdefault((x["home"], x["away"]), []).append((x["date"], x["gh"], x["ga"]))
        _TABLES[slug] = tab
    return _TABLES[slug]


def _find_result(slug, he, ae, d0, d1):
    for (h, a), lst in _result_table(slug).items():
        if h == he and a == ae:
            for dt, gf, ga in lst:
                if d0 <= dt <= d1:
                    return gf, ga
    return None


def _actual_label(gf, ga):
    return "主胜" if gf > ga else ("平" if gf == ga else "客胜")


def _score_total(score):
    """从 "1-2" 这类全场比分算总进球; 解析不了返回 None"""
    if not score:
        return None
    nums = re.findall(r"\d+", str(score))
    if len(nums) < 2:
        return None
    try:
        return int(nums[0]) + int(nums[1])
    except (TypeError, ValueError):
        return None


def _goal_bucket(total):
    """总进球 -> 竞彩档位(0~6, 7+)"""
    return str(total) if total <= 6 else "7+"


# 竞彩口径快源缓存(每销售日一次拉取; None=该日拉取失败)
_OKOOO = {}


def _okooo_rows(d):
    key = d.isoformat()
    if key not in _OKOOO:
        try:
            _OKOOO[key] = okooo_results.fetch(d.isoformat(),
                                              (d + timedelta(days=1)).isoformat())
        except Exception:
            _OKOOO[key] = None
    return _OKOOO[key]


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
        for it in snap.get("items", []):
            league_abb = it.get("league_abb", "")
            code = it.get("league_code") or LEAGUE_ABB_TO_CODE.get(league_abb, "")
            slug = LEAGUE_FEED.get(code, (None, None))[0]
            he = CH_TO_EN.get(it.get("home", ""))
            ae = CH_TO_EN.get(it.get("away", ""))
            row = {"num": it.get("num"), "league": league_abb,
                   "home": it.get("home"), "away": it.get("away"),
                   "pick": it.get("pick"), "odds": it.get("odds"),
                   "probs": it.get("probs"), "actual": None, "score": None,
                   "hit": None, "status": "待开奖"}
            _g = it.get("goals") or {}
            row["g_pick"] = _g.get("pick")        # 候选1
            row["g_pick2"] = _g.get("pick2")      # 候选2
            row["g_p"] = _g.get("p")
            row["g_avg"] = _g.get("avg")
            row["g_actual"] = None
            row["g_hit"] = None

            # 1) 首选: 竞彩口径快源 okooo(覆盖所有竞彩联赛, 含日职/韩职/巴甲等)
            okrows = _okooo_rows(d)
            if okrows:
                m = next((r for r in okrows
                          if r["home"] == it.get("home") and r["away"] == it.get("away")), None)
                if m is None:
                    m = next((r for r in okrows if r["num"] == it.get("num")), None)
                if m and m.get("spf"):
                    row["actual"] = m["spf"]
                    row["score"] = m.get("full")
                    row["hit"] = (row["actual"] == row["pick"])
                    row["status"] = "已核验"
                elif m is None and not (slug and he and ae):
                    if (now - d) > timedelta(days=3):
                        row["status"] = "未找到结果"

            # 2) 回退: fixturedownload 联赛结果源(未核验时兜底)
            if row["status"] != "已核验" and slug and he and ae:
                got = _find_result(slug, he, ae, d, d + timedelta(days=1))
                if got:
                    gf, ga = got
                    row["actual"] = _actual_label(gf, ga)
                    row["score"] = "{}-{}".format(gf, ga)
                    row["hit"] = (row["actual"] == row["pick"])
                    row["status"] = "已核验"
                elif row["status"] == "待开奖" and (now - d) > timedelta(days=3):
                    row["status"] = "未找到结果"

            # 3) 两个结果源都不可达且无联赛结果源
            if not okrows and not (slug and he and ae):
                row["status"] = "缺结果源"
            rows.append(row)

        # ---- 结果缓存回填: 源临时不可用时, 复用上次已核验结果(比分不会变) ----
        cc = _vcache_load(d)
        for r in rows:
            if r["actual"] is None:
                e = cc.get(r.get("num"))
                if e and e.get("actual"):
                    r["actual"] = e["actual"]
                    r["hit"] = (e["actual"] == r["pick"])
                    r["score"] = e.get("score")
                    r["status"] = "已核验"
        _vcache_save(d, rows)

        # ---- 总进球核验(与胜负分开): 两候选球数命中其一即算中 ----
        for r in rows:
            if r.get("g_pick") is not None and r.get("score"):
                t = _score_total(r["score"])
                if t is not None:
                    r["g_actual"] = _goal_bucket(t)
                    r["g_hit"] = (r["g_actual"] in
                                   {str(r["g_pick"]), str(r.get("g_pick2") or r["g_pick"])})

        # 统计(只算已核验)
        verified = [r for r in rows if r["hit"] is not None]
        hits = sum(1 for r in verified if r["hit"])
        net = 0.0
        for r in verified:
            net += (r["odds"] - 1.0) if r["hit"] else -1.0
        gv = [r for r in rows if r.get("g_hit") is not None]
        stats = {"total": len(rows), "verified": len(verified), "hits": hits,
                 "rate": (hits / len(verified)) if verified else None,
                 "roi": net,   # 每场按1注的净回报(单位:元)
                 "goals_n": len(gv),
                 "goals_hits": sum(1 for r in gv if r["g_hit"])}
        stats["goals_rate"] = (sum(1 for r in gv if r["g_hit"]) / len(gv)) if gv else None

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
