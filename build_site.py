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
import traceback
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import model   # noqa: E402
import parlay  # noqa: E402
import scout   # noqa: E402
from config import BASE_DIR, DATA_DIR, N_RECOMMEND  # noqa: E402
from source import fetch_today  # noqa: E402

SITE_DIR = os.path.join(BASE_DIR, "docs")   # 生成到 docs/, 由 GitHub Pages 直接发布该目录
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
.pill-r{background:#fdecea;color:#c0392b;border-radius:8px;padding:4px 10px;font-size:13px;font-weight:600}
.warn{color:#c0392b;font-size:12px;margin-top:3px;font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:8px 0;font-size:13px}
.card .k{color:var(--mut);font-size:12px}
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
.tabbar{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:5}
.tabbtn{border:1px solid var(--line);background:#fff;border-radius:24px;padding:9px 16px;font-size:14px;cursor:pointer;color:var(--txt);font-weight:600}
.tabbtn.on{background:var(--green);color:#fff;border-color:var(--green)}
.tabbtn:hover:not(.on){border-color:var(--green)}
.panel{display:none}
.panel.show{display:block}
.mut{color:var(--mut);font-size:13px}
@media(max-width:600px){th,td{font-size:12px}}
"""


def esc(x):
    return html.escape(str(x), quote=True)


def fmt_p(x):
    try:
        return f"{float(x):.1%}"
    except Exception:
        return "-"


JS = r"""
function showTab(id){
  var ids=['combo','probs','upset','info'];
  for(var i=0;i<ids.length;i++){var p=document.getElementById('tab-'+ids[i]); if(p){p.style.display=(ids[i]===id)?'block':'none';}}
  var bs=document.querySelectorAll('.tabbtn');
  for(var j=0;j<bs.length;j++){bs[j].classList.toggle('on', bs[j].getAttribute('data-tab')===id);}
}
"""


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
                risk = l.get("upset_risk", "低")
                utxt = l.get("upset_text", "")
                if risk == "高" and utxt:
                    sub += f'<div class="warn">⚠ {esc(utxt)}</div>'
                elif risk == "中" and utxt:
                    sub += f'<div style="color:#b7950b;font-size:12px;margin-top:3px">⚠ {esc(utxt)}</div>'
                legs += (f'<div class="leg"><b>{esc(l["num"])} [{esc(l["league"])}] '
                         f'{esc(l["home"])} vs {esc(l["away"])}</b>　推荐 <b>【{esc(l["pick"])}】</b> '
                         f'胜率 {fmt_p(l["prob"])} · 单关赔率 {l["odds"]:.2f}'
                         f'<div class="sub">{sub}</div></div>')
            risk_chip = ""
            cr = cb.get("risk", "低")
            if cr in ("中", "高"):
                risk_chip = f'<span class="pill-r">爆冷风险 {cr}</span>'
            combo_html += (
                f'<div class="combo"><div class="top">'
                f'<b>TOP {i}</b>'
                f'<span class="pill">联合胜率 {cb["joint"]:.1%}</span>'
                f'<span class="pill">串后赔率 {cb["odds"]:.2f}</span>{risk_chip}</div>'
                f'<div class="prog"><i style="width:{min(cb["joint"]*100,100):.1f}%"></i></div>'
                f'{legs}</div>')
    else:
        combo_html = ('<div class="note">暂无满足条件的组合(场次不足或串后赔率<2)。'
                      '可补充队名/联赛数据源后重试。</div>')

    # ⚠️ 爆冷雷达: 有明显大热且防冷风险中/高的场次(含大概原因)
    radar = []
    for f, pr in zip(ordered, preds):
        u = pr.get("upset") or {}
        if u.get("hot") and u.get("risk") in ("中", "高"):
            radar.append((f, u))
    radar.sort(key=lambda x: (0 if x[1]["risk"] == "高" else 1,
                              -x[1].get("no_win_p", 0)))
    if radar:
        cards = []
        for f, u in radar:
            fav_side = "主胜" if u["fav"] == "主胜" else "客胜"
            reasons = "；".join(u["reasons"][:3])
            cards.append(
                f'<div class="card"><b>{esc(f["num_str"])} [{esc(f["league_abb"])}] '
                f'{esc(f["home"])} vs {esc(f["away"])}</b>　'
                f'大热 <b>{esc(u["fav_team"])}</b>(选{fav_side} @{u["fav_odds"]})　'
                f'<span class="pill-r">风险[{u["risk"]}]</span><br>'
                f'<span class="k">防冷概率(大热不胜) {u["no_win_p"]:.0%} · '
                f'其中直接输 {u["upset_win_p"]:.0%} · 盘口隐含 {u["mkt_no_win_p"]:.0%}</span><br>'
                f'<span class="k">原因:</span> {esc(reasons)}</div>')
        upset_html = ('<h2>⚠️ 爆冷雷达(防冷提醒)</h2>'
                      '<p style="color:var(--mut);font-size:13px">这些场次大热不胜风险较高, '
                      '串关/做胆时请谨慎或考虑放弃</p>' + "".join(cards))
    else:
        upset_html = ('<h2>⚠️ 爆冷雷达(防冷提醒)</h2>'
                      '<div class="note">今日暂无高风险爆冷场次(无明显大热或防冷概率低)。</div>')

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

    # 全部场次预测表(三向概率 + 推荐)
    all_html = ""
    for f, pr in sorted(zip(ordered, preds),
                        key=lambda x: x[1]["pick_p"], reverse=True):
        all_html += (f'<tr><td>{esc(f["num_str"])}</td><td>{esc(f["league_abb"])}</td>'
                     f'<td>{esc(f["home"])} vs {esc(f["away"])}</td>'
                     f'<td>{fmt_p(pr["home"])}</td><td>{fmt_p(pr["draw"])}</td><td>{fmt_p(pr["away"])}</td>'
                     f'<td><b>{esc(pr["pick"])}</b></td>'
                     f'<td>{fmt_p(pr["pick_p"])}</td>'
                     f'<td>{esc(pr.get("pick_odds") or "-")}</td>'
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
<p>销售日期 {esc(sales)} · 数据源 {esc((today or {}).get('source',''))}
 · 每 {NEXT_HOURS} 小时自动更新<span class="badge">更新于 {esc(gen_time)}</span></p>
</div></header>
<div class="wrap">
{warn_html}
<div class="metrics">{metrics}</div>

<div class="tabbar">
<button class="tabbtn on" data-tab="combo" onclick="showTab('combo')">🎯 串关方案</button>
<button class="tabbtn" data-tab="probs" onclick="showTab('probs')">📊 全部概率</button>
<button class="tabbtn" data-tab="upset" onclick="showTab('upset')">⚠️ 爆冷雷达</button>
<button class="tabbtn" data-tab="info" onclick="showTab('info')">ℹ️ 说明</button>
</div>

<section class="panel show" id="tab-combo">
<h2>🎯 五大「两串一」推荐</h2>
<p class="mut">规则: 只串两关 · 串后赔率 ≥ 2.0 · 按两场联合胜率从高到低</p>
{combo_html}

<h2>📊 单场稳胆池(胜率 Top 12)</h2>
<div class="tbl"><table><tr><th>场次</th><th>联赛</th><th>对阵</th><th>推荐</th>
<th>胜率</th><th>赔率</th><th>数据</th></tr>{cand_html}</table></div>
</section>

<section class="panel" id="tab-probs">
<h2>📊 全部场次概率</h2>
<p class="mut">每场 主胜 / 平 / 客胜 的模型概率与推荐(点上方「🎯 串关方案」可回看五大方案)</p>
<div class="tbl"><table><tr><th>场次</th><th>联赛</th><th>对阵</th>
<th>主胜</th><th>平局</th><th>客胜</th><th>推荐</th><th>胜率</th><th>赔率</th><th>数据</th>
</tr>{all_html}</table></div>
</section>

<section class="panel" id="tab-upset">
{upset_html}
</section>

<section class="panel" id="tab-info">
<h2>ℹ️ 说明与免责</h2>
<div class="note">
<b>本页怎么用:</b> 点上方按钮切换——
「🎯 串关方案」看五大两串一与单场稳胆；「📊 全部概率」看每场胜平负三向概率；
「⚠️ 爆冷雷达」看大热翻车风险与原因；「ℹ️ 说明」看数据来源与免责。
</div>
<div class="note">
<b>数据与免责:</b> 场次与胜平负/让球赔率自动取自 <b>中国体彩·竞彩官方</b> 或 <b>500彩票网</b>
(官方接口封锁境外, 云端自动用 500 网; 赔率同为竞彩口径)。近况由已接入联赛的真实赛果计算
(每场标注 完整/部分/仅赔率)。伤病、转会、教练、战意等无自动源, 需人工核实。
本页为统计模型分析, 足球存在偶然性, <b>不构成投注建议</b>; 请理性购彩、量力而行, 未成年人不得购彩。
</div>
<footer>
本页面由 GitHub Actions 自动发布: 数据每 {NEXT_HOURS} 小时由电脑更新并推送, 页面随之刷新;
生成时间 {esc(gen_time)}。<br>
模型 = 泊松强度(近10场近期加权) + 市场赔率隐含概率 融合 · 两串一按 p₁×p₂ 联合胜率排序。
</footer>
</section>

</div>
<script>{JS}</script>
</body></html>"""


def minimal_error_page(exc, tb):
    body = esc(tb or repr(exc)).replace("\n", "<br>")
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>生成失败</title></head><body style="font-family:monospace;padding:20px">
<h3>⚠ 网页生成失败(已保留此诊断页)</h3><div style="white-space:pre-wrap">{body}</div>
</body></html>"""


def main():
    os.makedirs(SITE_DIR, exist_ok=True)
    err_path = os.path.join(SITE_DIR, "_err.txt")
    if os.path.exists(err_path):
        try:
            os.remove(err_path)
        except Exception:
            pass
    try:
        offline = "--offline" in sys.argv
        today, ordered, preds, rec, msgs = _collect(offline=offline)
    except Exception as e:
        tb = traceback.format_exc()
        try:
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(tb)
            with open(INDEX, "w", encoding="utf-8") as f:
                f.write(minimal_error_page(e, tb))
        except Exception:
            pass
        print("❌ 生成异常:\n", tb)
        return 0                       # 仍成功结束, 便于读取诊断
    if today is None:
        try:
            with open(err_path, "w", encoding="utf-8") as f:
                f.write("无数据且无可用缓存")
            with open(INDEX, "w", encoding="utf-8") as f:
                f.write(minimal_error_page(RuntimeError("无数据且无可用缓存"), ""))
        except Exception:
            pass
        print("❌ 无数据且无可用缓存")
        return 0

    gen_time = time.strftime("%Y-%m-%d %H:%M")
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(build_html(today, ordered, preds, rec, msgs, gen_time))

    # 同时存一份结构化快照, 便于调试/其它展示
    snapshot = {"gen_time": gen_time, "date": today["date"],
                "source": today.get("source", ""),
                "total": len(today["matches"]), "predictable": len(ordered),
                "warns": msgs}
    with open(os.path.join(SITE_DIR, "snapshot.json"), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)

    print(f"✅ 网站已生成: {INDEX}  (销售日期 {today['date']}, 数据源 {today.get('source','')}, "
          f"{len(ordered)} 场可预测, 更新于 {gen_time})")
    for m in msgs:
        print(m)
    if "--open" in sys.argv:
        webbrowser.open("file:///" + INDEX.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
