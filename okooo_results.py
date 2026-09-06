# -*- coding: utf-8 -*-
"""
竞彩赛果快源 (okooo_results.py)
================================
澳客网(okooo.com)的"竞足赛果公告"页面, 按实际开赛日期返回竞彩足球每场的
官方开奖结果(与体彩竞彩同一套场次/队名口径), 更新及时(完场即出), 且覆盖
所有被列入竞彩的联赛(含日职/韩职/挪超/巴甲/沙职等 fixturedownload 没有的)。

页面: https://www.okooo.com/jingcai/kaijiang/?LotteryType=SportteryWDL&StartDate=...&EndDate=...
行字段(去掉注释列后):
  0 场次号(周六006)  1 联赛  2 开赛时间  3 主队  4 客队
  5 半场比分  6 全场比分  7 胜平负赛果(3=主胜/1=平/0=客胜)  ...
作用: 供"预测验证/自我复盘"以竞彩口径快速核验(作为 fixturedownload 的补充/首选)。
"""
import re
import ssl
import urllib.request

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_URL = "https://www.okooo.com/jingcai/kaijiang/?LotteryType=SportteryWDL&StartDate={}&EndDate={}"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "text/html, application/xhtml+xml, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

SPF_CN = {"3": "主胜", "1": "平", "0": "客胜"}

# 进程内缓存: (start, end) -> rows 列表
_CACHE = {}


def _http(url, timeout=20):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        raw = r.read()
    for enc in ("gb18030", "utf-8"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("gb18030", "ignore")


def _parse(html):
    """剥掉被注释的"指数"td 后, 解析每个数据行"""
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    rows = []
    for m in re.finditer(r'<tr[^>]*class="[^"]*trClass[^"]*"[^>]*>(.*?)</tr>', html, re.S):
        tds = [re.sub(r"<[^>]+>", "", x).strip()
               for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
        if len(tds) < 16:
            continue
        full = tds[6]
        code = tds[7]
        rows.append({
            "num": tds[0], "league": tds[1], "time": tds[2],
            "home": tds[3], "away": tds[4],
            "half": tds[5], "full": full, "spf": SPF_CN.get(code),
        })
    return rows


def fetch(start_date, end_date):
    """按实际开赛日期范围抓赛果; 失败抛异常(由调用方回退到旧源)"""
    key = (start_date, end_date)
    if key not in _CACHE:
        html = _http(_URL.format(start_date, end_date))
        _CACHE[key] = _parse(html)
    return _CACHE[key]


def clear_cache():
    _CACHE.clear()


def find_result(sales_date, num, home, away):
    """
    在销售日 sales_date 的竞彩场次中找 (num/主客队) 对应的赛果。
    返回 {"num","league","full","spf"} 或 None(未找到/未开赛)。
    竞彩某销售日的比赛通常于当日或次日凌晨开赛, 故查 [sales_date, sales_date+1]。
    """
    from datetime import date, timedelta
    if isinstance(sales_date, str):
        sales_date = date.fromisoformat(sales_date)
    try:
        rows = fetch(sales_date.isoformat(),
                     (sales_date + timedelta(days=1)).isoformat())
    except Exception:
        return None
    # 优先完全匹配主客队; 否则按场次号(同窗口内唯一)
    cands = [r for r in rows if r["home"] == home and r["away"] == away]
    if not cands:
        cands = [r for r in rows if r["num"] == num]
    if not cands:
        return None
    r = cands[0]
    if not r["spf"]:      # 尚未开赛/无赛果
        return None
    return r
