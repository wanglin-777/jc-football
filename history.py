# -*- coding: utf-8 -*-
"""
历史赛果数据库
==============
从 fixturedownload(免费、无需注册)抓取各联赛整季赛果, 本地缓存。
提供:
  - 球队"最近 N 场"(先取当前赛季, 不足再从上一赛季补齐) -> 近况加权统计
  - 两队历史交锋
  - 联赛场均进球基线(主/客)

缓存文件: data/cache/<slug>.json
"""
import json
import os
import re
import ssl
import urllib.request
from datetime import date, datetime

from config import CACHE_DIR, HEADERS

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

FEED_BASE = "https://fixturedownload.com/feed/json/"


def _http(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.read().decode("utf-8", "ignore")


def _load_slug(slug, force=False):
    """拉取一个联赛 feed 并缓存; 失败返回 []"""
    cache = os.path.join(CACHE_DIR, slug + ".json")
    if (not force) and os.path.exists(cache):
        try:
            with open(cache, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        arr = json.loads(_http(FEED_BASE + slug))
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False)
        return arr
    except Exception:
        return []


def _split_year(slug):
    m = re.search(r"-(\d{4})$", slug)
    if m:
        return slug[: m.start()], int(m.group(1))
    return slug, None


def _to_d(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


class LeagueHistory:
    """某联赛当前赛季(+上一赛季)的历史赛果"""

    def __init__(self, slug):
        self.slug = slug
        stem, year = _split_year(slug)
        self.curr = _load_slug(slug)
        self.prev = []
        if year:
            prev_slug = f"{stem}-{year - 1}"
            self.prev = _load_slug(prev_slug)
        self.available = len(self.curr) > 0
        self.n_curr = len(self.curr)
        self.n_prev = len(self.prev)

    # ------- 基础 -------
    def all_matches(self):
        """已开赛(有比分)的比赛, 全部赛季合并, 按时间升序"""
        out = []
        for src in (self.curr, self.prev):
            for x in src:
                h, a = x.get("HomeTeamScore"), x.get("AwayTeamScore")
                d = _to_d(x.get("DateUtc") or "")
                if h is None or a is None or d is None:
                    continue
                try:
                    h, a = int(h), int(a)
                except (TypeError, ValueError):
                    continue
                out.append({"date": d, "home": x.get("HomeTeam"),
                            "away": x.get("AwayTeam"), "gh": h, "ga": a})
        out.sort(key=lambda x: x["date"])
        return out

    def league_base(self):
        """联赛场均主/客进球基线(只算当前赛季已赛场次)"""
        gh = ga = nh = na = 0
        for x in self.all_matches():
            if x["date"] > date.today():
                continue
            gh += x["gh"]; nh += 1
            ga += x["ga"]; na += 1
        base_h = (gh / nh) if nh else 1.5
        base_a = (ga / na) if na else 1.15
        return base_h, base_a

    def recent(self, team_en, before_d, k=10):
        """
        某队在某日期(before_d)之前最近的 k 场比赛, 按时间【近->远】排列。
        返回每条: {date, is_home, opp, gf, ga, pts}
        """
        rows = []
        for x in self.all_matches():
            if x["date"] >= before_d:
                continue
            if x["home"] == team_en:
                rows.append({"date": x["date"], "is_home": True,
                             "opp": x["away"], "gf": x["gh"], "ga": x["ga"],
                             "pts": 3 if x["gh"] > x["ga"] else (1 if x["gh"] == x["ga"] else 0)})
            elif x["away"] == team_en:
                rows.append({"date": x["date"], "is_home": False,
                             "opp": x["home"], "gf": x["ga"], "ga": x["gh"],
                             "pts": 3 if x["ga"] > x["gh"] else (1 if x["ga"] == x["gh"] else 0)})
        rows.sort(key=lambda r: r["date"], reverse=True)
        return rows[:k]

    def h2h(self, home_en, away_en, before_d, limit=8):
        """两队历史直接交锋(以主队视角记录), 近->远"""
        rows = []
        for x in self.all_matches():
            if x["date"] >= before_d:
                continue
            if {x["home"], x["away"]} == {home_en, away_en}:
                at_home = x["home"] == home_en
                rows.append({
                    "date": x["date"],
                    "at_home_of_home": at_home,
                    "gf": x["gh"] if at_home else x["ga"],
                    "ga": x["ga"] if at_home else x["gh"],
                    "result": "胜" if (x["gh"] > x["ga"]) == at_home
                              else ("平" if x["gh"] == x["ga"] else "负"),
                })
        rows.sort(key=lambda r: r["date"], reverse=True)
        return rows[:limit]


# 进程级缓存: 每个联赛只加载一次(网页/多次刷新不重复请求)
_HIST_CACHE = {}


def get_league(slug):
    if slug not in _HIST_CACHE:
        _HIST_CACHE[slug] = LeagueHistory(slug)
    return _HIST_CACHE[slug]
