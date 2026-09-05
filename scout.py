# -*- coding: utf-8 -*-
"""
比赛情报整合 (scout)
====================
对每一场在售竞彩, 综合:
  - 官方对阵/赔率/让球盘/联赛排名
  - 两队近 N 场(近→远, 近期加权): 战绩、进失球、主客倾向、赛程密度
  - 历史交锋
  - 手动补充情报 extra_intel.json(伤病/转会/教练/战意/热度等, 可选项)
产出统一的"特征 dict", 供 model.predict 与网页展示。

数据来源说明(诚实标注):
  - 官方赔率/排名/让球: 体彩竞彩官方接口(实时真实)
  - 近况/交锋: 由已开通数据源联赛的整季真实赛果计算(见 config.LEAGUE_FEED)
  - 伤病/转会/教练/战术/热度等: 无免费稳定自动源 -> 由 extra_intel.json 手动录入
    若未录入, 系统会用"排名/让球盘/赛程密度"等代理信号并明确标注缺失。
"""
import json
import os
from datetime import date, datetime

from config import (INTEL_FILE, LEAGUE_ABB_TO_CODE, LEAGUE_FEED,
                    N_RECENT, RECENT_DECAY)
from history import get_league
from team_map import CH_TO_EN


def _load_intel():
    """读取手动情报文件; 不存在或损坏返回空结构"""
    if not os.path.exists(INTEL_FILE):
        return {"matches": []}
    try:
        with open(INTEL_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"matches": []}


def _to_date(dstr):
    try:
        return datetime.strptime(dstr[:10], "%Y-%m-%d").date()
    except Exception:
        return date.today()


def _sum_wavg(rows, fn):
    """近期衰减加权求和。rows 已按 近->远。"""
    s = 0.0
    w = 0.0
    for i, r in enumerate(rows):
        v = fn(r)
        if v is None:
            continue
        ww = RECENT_DECAY ** i
        s += ww * v
        w += ww
    return (s / w) if w else None


def _team_stats(rows):
    """
    由一队近期比赛 rows(近->远) 计算:
      games, 加权胜率/积分, 场均进/失球(全部), 主/客场子集, 场均进失球
    """
    games = len(rows)
    if games == 0:
        return None
    win_w = _sum_wavg(rows, lambda r: 1 if r["pts"] == 3 else 0)
    pts_w = _sum_wavg(rows, lambda r: r["pts"])
    gf_all = _sum_wavg(rows, lambda r: r["gf"])
    ga_all = _sum_wavg(rows, lambda r: r["ga"])
    home = [r for r in rows if r["is_home"]]
    away = [r for r in rows if not r["is_home"]]
    gf_home = _sum_wavg(home, lambda r: r["gf"]) if home else None
    ga_home = _sum_wavg(home, lambda r: r["ga"]) if home else None
    gf_away = _sum_wavg(away, lambda r: r["gf"]) if away else None
    ga_away = _sum_wavg(away, lambda r: r["ga"]) if away else None
    return {"games": games, "win_w": win_w, "pts_w": pts_w,
            "gf": gf_all, "ga": ga_all,
            "gf_home": gf_home, "ga_home": ga_home,
            "gf_away": gf_away, "ga_away": ga_away}


def _rest_days(rows, mdate):
    if not rows:
        return None
    return max(0, (mdate - rows[0]["date"]).days)


def _summarize(team_cn, st, rest, rank):
    """生成中文近况摘要"""
    if st is None:
        return f"{team_cn}: 无历史赛果数据(仅赔率预测)"
    g = st["games"]
    parts = [f"{team_cn}(近{g}场)"]
    pts = st["pts_w"]
    win = st["win_w"]
    if pts is not None and win is not None:
        parts.append(f"场均积分{pts:.1f} 胜率{win:.0%}")
    if st["gf"] is not None and st["ga"] is not None:
        parts.append(f"场均进{st['gf']:.1f}/失{st['ga']:.1f}")
    parts.append(f"休息{rest if rest is not None else '?'}天")
    if rank:
        parts.append(f"排名{rank.strip('[]')}")
    return "，".join(parts)


def build_feature(match):
    """把一场竞彩对阵合成特征 dict"""
    mdate = _to_date(match.get("date"))
    league_code = LEAGUE_ABB_TO_CODE.get(match.get("league_abb"), match.get("league_code"))
    home_cn = match.get("home") or ""
    away_cn = match.get("away") or ""
    home_en = CH_TO_EN.get(home_cn)
    away_en = CH_TO_EN.get(away_cn)
    slug = None
    if league_code in LEAGUE_FEED:
        slug = LEAGUE_FEED[league_code][0]

    feat = {
        "num_str": match.get("num_str"), "league_abb": match.get("league_abb"),
        "league_code": league_code, "time": match.get("time"),
        "home": home_cn, "away": away_cn, "date": str(mdate),
        "home_rank": match.get("home_rank") or "", "away_rank": match.get("away_rank") or "",
        "had_h": match.get("had_h"), "had_d": match.get("had_d"), "had_a": match.get("had_a"),
        "hhad_gl": match.get("hhad_gl"),
        "home_games": 0, "away_games": 0, "h2h_games": 0,
        "data_quality": "odds_only",
        "home_summary": "", "away_summary": "", "h2h_summary": "", "intel_note": "",
        "intel_adj": 0.0,
    }

    # ---------- 历史情报(该联赛有数据源 + 两队都能匹配到英文名) ----------
    if slug and home_en and away_en:
        try:
            lh = get_league(slug)
        except Exception:
            lh = None
        if lh is not None and lh.available:
            hrows = lh.recent(home_en, mdate, N_RECENT)
            arows = lh.recent(away_en, mdate, N_RECENT)
            hh = lh.h2h(home_en, away_en, mdate)
            base_h, base_a = lh.league_base()

            hs = _team_stats(hrows)
            as_ = _team_stats(arows)

            feat["base_home_goals"] = base_h
            feat["base_away_goals"] = base_a
            if hs:
                feat.update({"home_games": hs["games"],
                             "home_gf": hs["gf"], "home_ga": hs["ga"],
                             "home_home_gf": hs["gf_home"], "home_home_ga": hs["ga_home"],
                             "home_win_w": hs["win_w"]})
            if as_:
                feat.update({"away_games": as_["games"],
                             "away_gf": as_["gf"], "away_ga": as_["ga"],
                             "away_away_gf": as_["gf_away"], "away_away_ga": as_["ga_away"],
                             "away_win_w": as_["win_w"]})

            hrest = _rest_days(hrows, mdate)
            arest = _rest_days(arows, mdate)
            feat["home_rest"] = hrest
            feat["away_rest"] = arest

            # 情报完整度
            if min(feat["home_games"], feat["away_games"]) >= 6:
                feat["data_quality"] = "full"
            elif min(feat["home_games"], feat["away_games"]) >= 2:
                feat["data_quality"] = "partial"
            else:
                feat["data_quality"] = "odds_only"

            # 交锋统计
            feat["h2h_games"] = len(hh)
            if hh:
                from collections import Counter
                cnt = Counter(r["result"] for r in hh)
                seq = "、".join(r["result"] for r in hh[:5])
                feat["h2h_summary"] = (f"近{len(hh)}次交锋(主队角度): "
                                       f"{cnt.get('胜',0)}胜{cnt.get('平',0)}平{cnt.get('负',0)}负"
                                       f"(由近到远:{seq}…)")
                tot = len(hh)
                pts = cnt.get("胜", 0) * 3 + cnt.get("平", 0)
                # 交锋优势: -0.5~+0.5, 正=主队占优(供胜率公式温和加权)
                feat["h2h_home_adv"] = (pts / (tot * 3)) - 0.5
            # 中文摘要
            feat["home_summary"] = _summarize(home_cn, hs, hrest, match.get("home_rank"))
            feat["away_summary"] = _summarize(away_cn, as_, arest, match.get("away_rank"))
        else:
            if not slug:
                feat["home_summary"] = f"{home_cn}: 联赛({match.get('league_abb')})暂无历史源, 仅赔率预测"
                feat["away_summary"] = f"{away_cn}: 同上"
            else:
                feat["home_summary"] = f"{home_cn}: 暂无匹配历史数据(请在 team_map.py 补充队名)"
                feat["away_summary"] = f"{away_cn}: 同上"
    elif not slug:
        feat["home_summary"] = f"{home_cn}: 联赛({match.get('league_abb')})暂无历史源, 仅赔率预测"
        feat["away_summary"] = f"{away_cn}: 同上"
    else:
        feat["home_summary"] = f"{home_cn}: 暂无匹配历史数据(请在 team_map.py 补充队名)"
        feat["away_summary"] = f"{away_cn}: 同上"

    # ---------- 手动情报(伤病/转会/教练/战意/热度) ----------
    intel = _load_intel()
    note = ""
    adj = 0.0
    for it in intel.get("matches", []):
        num_ok = it.get("num") and it.get("num") == feat["num_str"]
        names_ok = (it.get("home") == home_cn and it.get("away") == away_cn)
        if num_ok or names_ok:
            note = it.get("reason", "")
            try:
                adj = float(it.get("adj", 0) or 0)
            except (TypeError, ValueError):
                adj = 0.0
            break
    feat["intel_note"] = note
    feat["intel_adj"] = max(-3.0, min(3.0, adj))
    return feat


def build_features(matches):
    """批量合成特征"""
    return [build_feature(m) for m in matches]
