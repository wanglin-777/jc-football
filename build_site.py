# -*- coding: utf-8 -*-
"""
静态网站生成器 (build_site.py)
===============================
把"当天竞彩预测"渲染成一个**纯静态网页** site/index.html
(单个 HTML 文件, 内嵌数据, 无需服务器/数据库, 可在任何静态托管上运行)。

设计目标: 支持"每 4 小时由定时任务自动重建"的云端部署(GitHub Pages/Actions),
也支持本机双击一键预览。

用法:
    python build_site.py             # 联网取最新数据并生成
    python build_site.py --offline   # 只用本地缓存生成(断网也能跑)
    python build_site.py --open      # 生成后自动打开浏览器预览

说明:
    - 取不到最新数据时会保留上一次生成的网站(不覆盖), 保证线上永远可用。
"""
import html
import json
import os
import subprocess
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import model   # noqa: E402
import parlay  # noqa: E402
import scout   # noqa: E402
from config import BASE_DIR, DATA_DIR, N_RECOMMEND  # noqa: E402
from source import fetch_today  # noqa: E402

SITE_DIR = os.path.join(BASE_DIR, "site")
INDEX = os.path.join(SITE_DIR, "index.html")
NEXT_HOURS = 4          # 更新周期(小时), 与 Actions cron 一致

# ---------------- 数据采集 ----------------
def _cache_age_hours():
    """本地缓存 today_matches.json 的年龄(小时); 无文件返回很大值"""
    p = os.path.join(DATA_DIR, "today_matches.json")
    try:
        return (time.time() - os.path.getmtime(p)) / 3600.0
    except Exception:
        return 9999.0


def _collect(offline=False):
    """返回 (today, ordered, preds, rec, msgs)"""
    msgs = []
    today = None
    try:
        today = fetch_today(force=not offline)
    except Exception:
        try:
            today = fetch_today(force=False)     # 回退到上次缓存
            # 只有缓存确实陈旧时才提示(避免每次重建都吓人)
            if _cache_age_hours() > 6:
                msgs.append("⚠ 联网获取失败, 当前为较早的缓存数据(将随下次定时更新自动刷新)")
        except Exception as e:
            msgs.append(f"⚠ 数据获取失败: {e}")
            return None, [], [], None, msgs
    feats = scout.build_features(today["matches"])
    pred_map, ordered, preds = {}, [], []
    for f in feats:
        if f["had_h"] and f["had_d"] and f["had_a"]:
            pred_map[f["num_str"]] = model.predict(f)
    ordered = [f for f in feats if f["num_str"] in pred_map]
    preds = [pred_map[f["num_str"]] for f in ordered]
    rec = parlay.recommend(ordered, preds)
    return today, ordered, preds, rec, msgs


# ---------------- HTML 渲染 ----------------
CSS = """
:root{--green:#0a7d3e;--bg:#f4f7f5;--card:#fff;--line:#e3e9e5;--txt:#1c2b24;--mut:#6b7a72;}
*{box-sizing:border-box}
body{margin:0;font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;background:var(--bg);color:var(--txt)}
.wrap{max-width:960px;margin:0 auto;padding:16px}
header{background:linear-gradient(135deg,#0a7d3e,#16a05a);color:#fff;padding:18px 16px}
header h1{margin:0;font-size:22px}
header p{margin:4px 0 0;opacity:.92;font-size:13px}
.badge{display:inline-block;background:rgba(255,255,255,.2);border-radius:20px;padding:2px 10px;font-size:12px;margin-left:6px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:14px 0}
.metric{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;text-align:center}
.metric b{display:block;font-size:24px;color:var(--green)}
.metric span{font-size:12px;color:var(--mut)}
h2{font-size:18px;margin:22px 0 10px;border-left:4px solid var(--green);padding-left:8px}
.combo{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:10px 0}
.combo .top{display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px}
.pill{background:#eaf6ef;color:var(--green);border-radius:8px;padding:4px 10px;font-size:13px;font-weight:600}
.leg{margin:8px 0;padding:10px;background:#f8fbf9;border-radius:8px;border-left:3px solid var(--green)}
.leg b{font-size:14px}
.leg .sub{color:var(--mut);font-size:12px;margin-top:4px;line-height:1.6}
.prog{height:8px;background:#e6eee9;border-radius:6px;overflow:hidden;margin-top:6px}
.prog i{display:block;height:100%;background:var(--green)}
table{width:100%;border-collapse:collapse;background:var(--card);font-size:13px}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{background:#eef4f0;color:#34503f}
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:10px}
.note{background:#fff8e6;border:1px solid #f0dcA0;border-radius:10px;padding:12px;font-size:13px;line-height:1.7;margin-top:16px}
footer{color:var(--mut);font-size:12px;line-height:1.8;margin:18px 0 40px}
@media(max-width:600px){th,td{font-size:12px}}
"""


def esc(x):
    return html.escape(str(x), quote=True)


def fmt_p(x):
    try:
        return f"{float(x):.1%}"
    except Exception:
        return "-"


def build_html(today, ordered, preds, rec, msgs, gen_time):
    # 顶部时间戳
    sales = today["date"] if today else "-"
    total = len(today["matches"]) if today else 0
    full = sum(1 for f in ordered if f.get("data_quality") == "full")
    parts = sum(1 for f in ordered if f.get("data_quality") == "partial")

    warn_html = "".join(f'<div class="note">⚠ {esc(m)}</div>' for m in msgs)

    # 串关卡片
    combo_html = ""
    if rec and rec.get("combos"):
        for i, cb in enumerate(rec["combos"], 1):
            legs = ""
            for l in cb["legs"]:
                sub = f"{esc(l['home_summary'])}<br>{esc(l['away_summary'])}"
                legs += (f'<div class="leg"><b>{esc(l["num"])} [{esc(l["league"])}] '
                         f'{esc(l["home"])} vs {esc(l["away"])}</b>　推荐 <b>【{esc(l["pick"])}】</b> '
                         f'胜率 {fmt_p(l["prob"])} · 单关赔率 {l["odds"]:.2f}'
                         f'<div class="sub">{sub}</div></div>')
            combo_html += (
                f'<div class="combo"><div class="top">'
                f'<b>TOP {i}</b>'
                f'<span class="pill">联合胜率 {cb["joint"]:.1%}</span>'
                f'<span class="pill">串后赔率 {cb["odds"]:.2f}</span></div>'
                f'<div class="prog"><i style="width:{min(cb["joint"]*100,100):.1f}%"></i></div>'
                f'{legs}</div>')
    else:
        combo_html = ('<div class="note">暂无满足条件的组合(场次不足或串后赔率<2)。'
                      '可补充队名/联赛数据源后重试。</div>')

    # 单场稳胆池(按胜率降序前 12 场, 表格)
    rows = sorted(zip(ordered, preds),
                  key=lambda x: x[1]["pick_p"], reverse=True)
    cand_html = ""
    if rec:
        pool = sorted(rec["candidates"], key=lambda c: c["prob"], reverse=True)
        for c in pool[:12]:
            f = c["feat"]
            cand_html += (f'<tr><td>{esc(f["num_str"])}</td><td>{esc(f["league_abb"])}</td>'
                          f'<td>{esc(f["home"])} vs {esc(f["away"])}</td>'
                          f'<td><b>{esc(c["pick"])}</b></td>'
                          f'<td>{fmt_p(c["prob"])}</td>'
                          f'<td>{c["odds"]:.2f}</td>'
                          f'<td>{esc(f.get("data_quality",""))}</td></tr>')

    # 全场预测表格
    all_html = ""
    for f, pr in sorted(zip(ordered, preds),
                        key=lambda x: x[1]["pick_p"], reverse=True):
        had = f"/".join(str(x) for x in [f["had_h"], f["had_d"], f["had_a"]])
        all_html += (f'<tr><td>{esc(f["num_str"])}</td><td>{esc(f["league_abb"])}</td>'
                     f'<td>{esc(f["home"])} vs {esc(f["away"])}</td>'
                     f'<td>{esc(pr["pick"])}</td>'
                     f'<td>{fmt_p(pr["pick_p"])}</td>'
                     f'<td>{esc(pr.get("pick_odds") or "-")}</td>'
                     f'<td>{had}</td>'
                     f'<td>{esc(f.get("data_quality",""))}</td></tr>')

    metrics = (f'<div class="metric"><b>{total}</b><span>在售场次</span></div>'
               f'<div class="metric"><b>{len(ordered)}</b><span>可预测场次</span></div>'
               f'<div class="metric"><b>{full}</b><span>完整情报</span></div>'
               f'<div class="metric"><b>{parts}</b><span>部分情报</span></div>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>竞彩两串一预测 · {esc(sales)}</title>
<style>{CSS}</style></head><body>
<header><div class="wrap">
<h1>⚽ 竞彩足球 · 两串一预测</h1>
<p>销售日期 {esc(sales)} · 每 {NEXT_HOURS} 小时自动更新<span class="badge">更新于 {esc(gen_time)}</span></p>
</div></header>
<div class="wrap">
{warn_html}
<div class="metrics">{metrics}</div>

<h2>🎯 五大「两串一」推荐</h2>
<p style="color:var(--mut);font-size:13px">规则: 只串两关 · 串后赔率 ≥ 2.0 · 按两场联合胜率从高到低</p>
{combo_html}

<h2>📊 单场稳胆池(胜率 Top 12)</h2>
<div class="tbl"><table><tr><th>场次</th><th>联赛</th><th>对阵</th><th>推荐</th>
<th>胜率</th><th>赔率</th><th>数据</th></tr>{cand_html}</table></div>

<h2>📋 全部场次预测</h2>
<div class="tbl"><table><tr><th>场次</th><th>联赛</th><th>对阵</th><th>推荐</th>
<th>胜率</th><th>赔率</th><th>胜平负</th><th>数据</th></tr>{all_html}</table></div>

<div class="note">
<b>数据与免责:</b> 胜平负/让球赔率来自中国体彩·竞彩足球官方; 近况由已接入联赛的真实赛果计算
(每场标注 完整/部分/仅赔率)。伤病、转会、教练、战意等无自动源, 需人工核实。
本页为统计模型分析, 足球存在偶然性, <b>不构成投注建议</b>; 请理性购彩、量力而行, 未成年人不得购彩。
</div>
<footer>
本页面由脚本自动生成: 每 {NEXT_HOURS} 小时重建一次, 时间为 {esc(gen_time)}。<br>
模型 = 泊松强度(近10场近期加权) + 官方赔率隐含概率 融合 · 两串一按 p₁×p₂ 联合胜率排序。
</footer>
</div></body></html>"""


def main():
    args = sys.argv[1:]
    offline = "--offline" in args
    do_open = "--open" in args

    today, ordered, preds, rec, msgs = _collect(offline=offline)
    if today is None:
        if os.path.exists(INDEX):
            print("⚠ 无法获取数据, 保留上一次生成的网站。")
        else:
            print("❌ 无法获取数据且无历史缓存, 无法生成。")
        return 1

    gen_time = time.strftime("%Y-%m-%d %H:%M")
    os.makedirs(SITE_DIR, exist_ok=True)
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(build_html(today, ordered, preds, rec, msgs, gen_time))

    # 同时存一份结构化快照, 便于调试/其它展示
    snapshot = {"gen_time": gen_time, "date": today["date"],
                "total": len(today["matches"]), "predictable": len(ordered),
                "warns": msgs}
    with open(os.path.join(SITE_DIR, "snapshot.json"), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)

    print(f"✅ 网站已生成: {INDEX}  (销售日期 {today['date']}, "
          f"{len(ordered)} 场可预测, 更新于 {gen_time})")
    for m in msgs:
        print(m)
    if do_open:
        webbrowser.open("file:///" + INDEX.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
