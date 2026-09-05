# -*- coding: utf-8 -*-
"""临时诊断: 从(GitHub云/海外)视角测试各数据源连通性, 结果写入 stdout 供 workflow 落到 site/_diag.txt"""
import json
import ssl
import sys
import urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
     "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
     "Referer": "https://www.sporttery.cn/"}

URLS = [
    ("webapi.sporttery 计算器", "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?poolCode=hhad,had&channel=c"),
    ("www.sporttery 首页", "https://www.sporttery.cn/"),
    ("i.sporttery 旧接口", "https://i.sporttery.cn/api/fb_match_info/get_pool_rs?poolcode=hhad,had&channel=c"),
    ("trade.500.com", "https://trade.500.com/jczq/"),
    ("odds.500.com", "https://odds.500.com/"),
    ("fixturedownload(epl)", "https://fixturedownload.com/feed/json/epl-2026"),
]


def probe(url, timeout=20):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = r.read(400)
            head = body[:80].decode("utf-8", "ignore").replace("\n", " ")
            return f"OK  http={r.status} len_head={len(body)} head={head!r}"
    except Exception as e:
        return f"FAIL {type(e).__name__}: {e}"


def main():
    lines = []
    for name, url in URLS:
        lines.append(f"== {name}\n{url}\n   -> {probe(url)}")
    print("\n".join(lines))
    # 若当前就是从 CN 跑, 标注以区分
    print("\n(此输出由云端 runner 生成时为海外视角)")


if __name__ == "__main__":
    sys.exit(main())
