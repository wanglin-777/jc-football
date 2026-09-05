# -*- coding: utf-8 -*-
"""
统一数据入口 (source.py)
========================
自动选择可用数据源抓取"当天竞彩场次+赔率", 保证中国/海外都能跑:
  1. 中国体彩官方接口(仅中国大陆可访问; 本机优先)
  2. 500彩票网竞彩页(海外可访问; GitHub/云端用这个)
  3. 以上都失败 -> 使用本地缓存数据(可能过期)

返回结构统一为 {"date", "matches":[...], "source":"官方体彩"/"500彩票网"/"本地缓存"}
"""
import json
import os

from config import DATA_DIR


def fetch_today(force=True):
    # ---- 1) 官方体彩 ----
    try:
        from sporttery import fetch_today as _off
        r = _off(force=True)
        if r and r.get("matches"):
            r["source"] = "中国体彩官方"
            return r
    except Exception:
        pass
    # ---- 2) 500彩票网(云端可访问) ----
    try:
        from cai500 import fetch_online, save
        r = fetch_online()
        if r and r.get("matches"):
            save(r)
            r["source"] = "500彩票网(竞彩官方赔率)"
            return r
    except Exception:
        pass
    # ---- 3) 本地缓存兜底 ----
    try:
        from sporttery import fetch_today as _off2
        r = _off2(force=False)          # force=False -> 读 data/today_matches.json
        if r and r.get("matches"):
            r["source"] = "本地缓存(可能过期)"
            return r
    except Exception:
        pass
    raise RuntimeError("所有数据源均不可用, 且无本地缓存")


def cache_exists():
    return os.path.exists(os.path.join(DATA_DIR, "today_matches.json"))


def read_cache():
    try:
        with open(os.path.join(DATA_DIR, "today_matches.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
