# -*- coding: utf-8 -*-
"""
500 彩票网·竞彩数据源 (cai500.py)
=================================
用途: GitHub/海外云端访问不了中国体彩官网(HTTP 567 封锁境外IP),
      而 500 彩票网(trade.500.com)海外可正常访问, 且展示的就是"竞彩官方"
      胜平负/让球赔率与当天对阵(中文)。
本模块解析其竞彩列表页, 输出与 sporttery.py 相同结构的场次字典,
供 scout/model/parlay 无缝使用。

字段口径: nspf = 不让球胜平负(主/平/客), spf = 让球胜平负, data-rangqiu = 让球数。
"""
import json
import os
import re
import ssl
import urllib.request
from datetime import datetime, timedelta

from config import DATA_DIR

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
HDR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://trade.500.com/",
}
PAGE = "https://trade.500.com/jczq/"


def _http(url):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=20, context=_CTX) as r:
        raw = r.read()
    # 按页面声明的 charset 解码(不同日期页可能是 gb2312 或 utf-8)
    m = re.search(rb"charset=[\"']?([\w-]+)", raw[:2048])
    declared = m.group(1).decode("ascii", "ignore").lower() if m else ""
    cand = []
    if declared and declared != "gb2312":
        cand.append(declared)
    cand += ["gb18030", "utf-8"]
    for enc in cand:
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("gb18030", "ignore")


def _cn_today():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")


def _f(s):
    """赔率字符串 -> float, 异常返回 None"""
    try:
        v = float(s)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _row_odds(body):
    """在 tr 内收集两类赔率: {type: {value: odds}}"""
    got = {}
    for m in re.finditer(
            r'<p class="betbtn" data-type="(nspf|spf)" data-value="(3|1|0)" data-sp="([\d.]+)"',
            body):
        typ, val, sp = m.group(1), int(m.group(2)), _f(m.group(3))
        got.setdefault(typ, {})[val] = sp
    return got


def _team(body, side):
    """从 tr 里取 球队中文名 + 排名(若有)"""
    if side == "l":
        pat = re.compile(
            r'<span class="team-l">.*?<a[^>]*title="([^"]*)"[^>]*>([^<]*)</a>.*?'
            r'(?:<i title="排名第(\d+)">)?', re.S)
    else:
        pat = re.compile(
            r'<span class="team-r">.*?<a[^>]*title="([^"]*)"[^>]*>([^<]*)</a>.*?'
            r'<i title="排名第(\d+)">', re.S)
    m = pat.search(body)
    if not m:
        return "", None
    name = (m.group(2) or m.group(1)).strip()
    rank = m.group(3)
    return name, (int(rank) if rank else None)


def fetch_online():
    """抓取并解析 500 竞彩列表页(默认当天在售), 返回 {date, matches:[...], source:'cai500'}"""
    html = _http(PAGE)          # 不带 date 参数: 服务器默认给"当前在售日"
    out = []
    day = _cn_today()
    pat = re.compile(r'<tr class="bet-tb-tr([^"]*)"([^>]*)>(.*?)</tr>', re.S)
    for cls, attrs, body in pat.findall(html):
        if "bet-tb-end" in cls:            # 已截止/停售
            continue
        attr = dict(re.findall(r'(\S+?)="([^"]*)"', attrs))
        odds = _row_odds(body)
        nspf = odds.get("nspf")
        spf = odds.get("spf")
        if not nspf:                        # 无胜平负赔率(未开/其它)跳过
            continue
        mtime = attr.get("data-matchtime", "")
        had = (nspf.get(3), nspf.get(1), nspf.get(0))
        hhad = (spf.get(3), spf.get(1), spf.get(0)) if spf else (None, None, None)
        hname, hrank = _team(body, "l")
        aname, arank = _team(body, "r")
        # 竞彩编号(周六00x)
        nm = re.search(r'bet-evt-hide[^>]*>\s*([^<\s]+)', body)
        num_str = nm.group(1).strip() if nm else ""
        gl = attr.get("data-rangqiu", "")
        try:
            gl = float(gl)
        except (TypeError, ValueError):
            gl = None
        out.append({
            "match_id": attr.get("data-id", ""),
            "num_str": num_str,
            "week": num_str[:2],
            "date": attr.get("data-matchdate", day),
            "time": mtime,
            "league_abb": attr.get("data-simpleleague", ""),
            "league_code": "",
            "home": hname or attr.get("data-homesxname", ""),
            "home_code": "", "home_en": "",
            "home_rank": ("[%s]" % hrank) if hrank else "",
            "away": aname or attr.get("data-awaysxname", ""),
            "away_code": "", "away_en": "",
            "away_rank": ("[%s]" % arank) if arank else "",
            "had_h": had[0], "had_d": had[1], "had_a": had[2],
            "hhad_gl": gl,
            "hhad_h": hhad[0], "hhad_d": hhad[1], "hhad_a": hhad[2],
            "status": "Selling",
            "league_all": "",
            "_processdate": attr.get("data-processdate", ""),
        })
    if not out:
        return {"date": day, "matches": [], "source": "cai500"}
    # 竞彩一个"销售日"跨自然日(晚上+次日凌晨): 按销售日 data-processdate 分组取最大一组
    from collections import Counter
    proc = [m["_processdate"] for m in out if m["_processdate"]]
    day = (max(set(proc), key=proc.count) if proc else day)
    out = [m for m in out if m["_processdate"] == day]
    for m in out:
        m.pop("_processdate", None)
    out.sort(key=lambda m: m["num_str"])
    return {"date": day, "matches": out, "source": "cai500"}


def save(result):
    """把结果写入与 sporttery 相同的数据文件(供其它流程/缓存读取)"""
    import csv as _csv
    with open(os.path.join(DATA_DIR, "today_matches.json"), "w", encoding="utf-8") as f:
        json.dump({"date": result["date"], "matches": result["matches"]},
                  f, ensure_ascii=False, indent=1)
    cols = ["num_str", "league_abb", "time", "home", "home_rank", "away",
            "away_rank", "had_h", "had_d", "had_a",
            "hhad_gl", "hhad_h", "hhad_d", "hhad_a"]
    with open(os.path.join(DATA_DIR, "today_matches.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = _csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for m in result["matches"]:
            w.writerow({k: m.get(k) for k in cols})
