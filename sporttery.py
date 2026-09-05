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
import urllib.request
from datetime import date

from config import CACHE_DIR, DATA_DIR, HEADERS, SPORTTERY_MATCH_URL

# 某些服务器证书校验问题兜底
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _http_json(url, timeout=12):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


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


def fetch_today(force=False):
    """抓取竞彩当天在售场次。

    返回 dict: {"date": "2026-09-05", "matches": [ {场次...}, ... ]}
    只保留状态为在售(Selling/On Sale) 且是最近一个开售日的场次。
    本地 json 存在且未 force 时直接读取缓存(离线可用)。
    """
    today_json = os.path.join(DATA_DIR, "today_matches.json")
    if (not force) and os.path.exists(today_json):
        with open(today_json, encoding="utf-8") as f:
            cached = json.load(f)
        if cached and cached.get("matches"):
            return cached

    data = _http_json(SPORTTERY_MATCH_URL)
    days = (data.get("value") or {}).get("matchInfoList") or []

    def selling(m):
        return (m.get("matchStatus") in ("Selling", "On Sale"))

    # 官方按天分组; 只取第一个(通常=当天开售日)在售场次
    matches = []
    picked_day = None
    for day in days:
        subs = [m for m in (day.get("subMatchList") or []) if selling(m)]
        if subs:
            matches = [_parse_match(m) for m in subs]
            picked_day = day.get("businessDate")
            break

    result = {"date": picked_day, "matches": matches}
    with open(today_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    # 顺便导出 CSV 便于 Excel 查看
    _export_csv(result)
    return result


def _export_csv(result):
    path = os.path.join(DATA_DIR, "today_matches.csv")
    cols = ["num_str", "league_abb", "time", "home", "home_rank", "away",
            "away_rank", "had_h", "had_d", "had_a",
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
