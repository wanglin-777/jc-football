# -*- coding: utf-8 -*-
"""
竞彩官方数据抓取
================
从中国体育彩票竞彩官方接口抓取【当天可购买的场次 + 胜平负/让球赔率】。
接口实测可用, 返回实时真实数据(队名/联赛/排名/赔率均为中文官方口径)。

输出:
    data/today_matches.json   (原始解析结果)
    data/today_matches.csv    (便于 Excel 查看)
"""

import csv
import json
import os
import ssl
import time
import urllib.request
from datetime import date, timedelta

from config import CACHE_DIR, DATA_DIR, HEADERS, SPORTTERY_MATCH_URL

# 某些服务器证书校验问题兜底
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# 同一开售日内的场次合并保留文件(记录今天"见过"的全部场次,
# 避免开赛后从官方"在售"接口消失 -> 当天看不到)
_SCHED_FILE = os.path.join(DATA_DIR, "day_schedule.json")


def _in_sale_status(m):
    return m.get("matchStatus") in ("Selling", "On Sale")


def _http_json(url, timeout=12, tries=3):
    req = urllib.request.Request(url, headers=HEADERS)
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:          # 网络抖动自动重试
            last = e
            time.sleep(0.6 * (i + 1))
    raise last


def _fmt_odds(o):
    """把 had/hhad 里的赔率字符串转 float; 空/0 返回 None"""
    if not o:
        return None
    try:
        v = float(o)
        return v if v and v > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_match(m):
    """把官方返回的一场数据整理成统一字段 dict"""
    had = m.get("had") or {}
    hhad = m.get("hhad") or {}
    gl = hhad.get("goalLine") or ""
    def gl_float(s):
        try:
            return float(s)
        except (TypeError, ValueError):
            return None
    return {
        "match_id": m.get("matchId"),
        "num_str": m.get("matchNumStr") or "",
        "week": m.get("matchWeek") or "",
        "date": m.get("matchDate") or m.get("businessDate"),
        "time": m.get("matchTime") or "",
        "league_abb": m.get("leagueAbbName") or "",
        "league_code": m.get("leagueCode") or "",
        "home": m.get("homeTeamAbbName") or "",
        "home_code": m.get("homeTeamCode") or "",
        "home_en": m.get("homeTeamAbbEnName") or "",
        "home_rank": m.get("homeRank") or "",
        "away": m.get("awayTeamAbbName") or "",
        "away_code": m.get("awayTeamCode") or "",
        "away_en": m.get("awayTeamAbbEnName") or "",
        "away_rank": m.get("awayRank") or "",
        # 胜平负(不包含让球): 主胜/平/客胜
        "had_h": _fmt_odds(had.get("h")),
        "had_d": _fmt_odds(had.get("d")),
        "had_a": _fmt_odds(had.get("a")),
        # 让球胜平负: 让球数(负=主让) + 主胜/平/客胜
        "hhad_gl": gl_float(gl),
        "hhad_h": _fmt_odds(hhad.get("h")),
        "hhad_d": _fmt_odds(hhad.get("d")),
        "hhad_a": _fmt_odds(hhad.get("a")),
        "status": m.get("matchStatus") or "",
        "league_all": m.get("leagueAllName") or "",
    }


def _load_schedule(day):
    """读同开售日已见过的场次(用于保留已开赛/已结束的比赛)"""
    try:
        with open(_SCHED_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("date") == day:
            return d.get("matches") or []
    except Exception:
        pass
    # 兼容旧版 today_matches.json
    try:
        with open(os.path.join(DATA_DIR, "today_matches.json"), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("date") == day:
            return d.get("matches") or []
    except Exception:
        pass
    return []


def fetch_today(force=False):
    """抓取竞彩当天场次(不只在售)。

    说明: 官方接口只返回【仍可投注】的场次, 一旦开赛就从接口消失。
    因此本函数做"同开售日合并保留": 今天已见过的场次(存于 day_schedule.json)
    即使之后开赛/结束, 仍保留在返回里并标记 started/in_sale, 避免"刷新后
    已开赛的比赛看不到"; 已结束场次仍可被验证/复盘读取。

    返回 dict: {"date": "2026-09-06", "matches": [{场次(含 in_sale/started)}, ...]}
    """
    import re as _re
    today_json = os.path.join(DATA_DIR, "today_matches.json")
    # 未 force: 直接读缓存(缓存里已含当天已开赛/结束的保留场次, 离线可用)
    if (not force) and os.path.exists(today_json):
        try:
            with open(today_json, encoding="utf-8") as f:
                cached = json.load(f)
            if cached and cached.get("matches"):
                return cached
        except Exception:
            pass

    data = _http_json(SPORTTERY_MATCH_URL)
    days = (data.get("value") or {}).get("matchInfoList") or []
    # 取"该开售日"(优先沿用上次已记录的日期, 否则第一个有在售的, 再否则第一个)
    prev_day = None
    for f in (_SCHED_FILE, today_json):
        try:
            with open(f, encoding="utf-8") as fp:
                prev_day = json.load(fp).get("date")
            if prev_day:
                break
        except Exception:
            prev_day = None
    target = None
    if prev_day:
        target = next((g for g in days if g.get("businessDate") == prev_day), None)
    if target is None:
        target = next((g for g in days
                       if any(_in_sale_status(m) for m in (g.get("subMatchList") or []))), None)
    if target is None and days:
        target = days[0]
    if target is None:
        raise RuntimeError("官方接口无返回任何场次")

    bd = target.get("businessDate")
    live = []
    for m in (target.get("subMatchList") or []):
        pm = _parse_match(m)
        pm["in_sale"] = _in_sale_status(m)
        pm["started"] = not pm["in_sale"]
        if not pm["in_sale"]:            # 已开赛/结束 -> 官方不再提供在售赔率
            pm["had_h"] = pm["had_d"] = pm["had_a"] = None
            pm["hhad_h"] = pm["hhad_d"] = pm["hhad_a"] = None
        live.append(pm)

    # 与当天已保留的场次合并(位置稳定, 保留已开赛的)
    prev = _load_schedule(bd)
    bynum, merged = {}, []
    for old in prev:
        merged.append(dict(old))
        bynum[old.get("num_str")] = len(merged) - 1
    cur = set()
    for pm in live:
        num = pm.get("num_str")
        if not num:
            continue
        cur.add(num)
        if num in bynum:
            merged[bynum[num]] = pm
        else:
            bynum[num] = len(merged)
            merged.append(pm)
    for old in prev:                     # 上次在售、这次没出现 -> 已开赛/截止
        num = old.get("num_str")
        if num and num not in cur:
            o2 = dict(old)
            o2["in_sale"] = False
            o2["started"] = True
            o2["had_h"] = o2["had_d"] = o2["had_a"] = None
            o2["hhad_h"] = o2["hhad_d"] = o2["hhad_a"] = None
            merged[bynum[num]] = o2

    def numkey(n):
        mm = _re.search(r"(\d+)$", n or "")
        return int(mm.group(1)) if mm else 0
    merged.sort(key=lambda m: numkey(m.get("num_str")))

    if not merged:                       # 空结果不覆盖已有缓存
        try:
            with open(today_json, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"date": bd, "matches": []}

    result = {"date": bd, "matches": merged}
    for f, obj in ((today_json, result), (_SCHED_FILE, result)):
        try:
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(obj, fp, ensure_ascii=False, indent=1)
        except Exception:
            pass
    _export_csv(result)
    return result


def _export_csv(result):
    path = os.path.join(DATA_DIR, "today_matches.csv")
    cols = ["num_str", "league_abb", "time", "home", "home_rank", "away",
            "away_rank", "in_sale", "started",
            "had_h", "had_d", "had_a",
            "hhad_gl", "hhad_h", "hhad_d", "hhad_a"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for m in result["matches"]:
            w.writerow({k: m.get(k) for k in cols})


if __name__ == "__main__":
    res = fetch_today(force=True)
    print(f"抓取完成: 日期 {res['date']}  在售 {len(res['matches'])} 场\n")
    for m in res["matches"]:
        had = (f"{m['had_h']}/{m['had_d']}/{m['had_a']}"
               if m["had_h"] else "未开")
        print(f"{m['num_str']} [{m['league_abb']}] {m['home']} vs {m['away']}"
              f"  胜平负 {had}  让球{m['hhad_gl'] or '-'}")
