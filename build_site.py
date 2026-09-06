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
import selftune  # noqa: E402
import verify  # noqa: E402
import deepseek_client  # noqa: E402
from config import (BANKER_MAX_ODDS, BANKER_MIN_PROB, BASE_DIR, COMBO_MARGIN_TIERS,
                    DATA_DIR, N_RECOMMEND)  # noqa: E402
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
            pr = model.predict(f)
            try:
                pr["goals"] = model.total_goals(f)   # 总进球预测(与胜负分开)
            except Exception:
                pr["goals"] = None
            pred_map[f["num_str"]] = pr
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
  var ids=['combo','probs','goals','upset','verify','self','info'];
  for(var i=0;i<ids.length;i++){var p=document.getElementById('tab-'+ids[i]); if(p){p.style.display=(ids[i]===id)?'block':'none';}}
  var bs=document.querySelectorAll('.tabbtn');
  for(var j=0;j<bs.length;j++){bs[j].classList.toggle('on', bs[j].getAttribute('data-tab')===id);}
}
function showProbs(m){
  document.getElementById('probs-num').style.display=(m==='num')?'block':'none';
  document.getElementById('probs-rate').style.display=(m==='rate')?'block':'none';
  document.getElementById('pb-num').classList.toggle('on', m==='num');
  document.getElementById('pb-rate').classList.toggle('on', m==='rate');
}
function showGoals(m){
  document.getElementById('goals-num').style.display=(m==='num')?'block':'none';
  document.getElementById('goals-rate').style.display=(m==='rate')?'block':'none';
  document.getElementById('gb-num').classList.toggle('on', m==='num');
  document.getElementById('gb-rate').classList.toggle('on', m==='rate');
}
var VP={'play':'spf','day':''};
function _vdnum(s){var m=(s||'').match(/(\d+)$/);return m?parseInt(m[1],10):0;}
function vpApply(){
  var i,x;
  var ds=document.querySelectorAll('[id^="vd-"]');
  for(i=0;i<ds.length;i++){x=ds[i];x.style.display=(VP.play==='spf'&&x.id==='vd-'+VP.day)?'block':'none';}
  var gs=document.querySelectorAll('[id^="vg-"]');
  for(i=0;i<gs.length;i++){x=gs[i];x.style.display=(VP.play==='goals'&&x.id==='vg-'+VP.day)?'block':'none';}
  var ps=document.querySelectorAll('[data-play]');
  for(i=0;i<ps.length;i++){ps[i].classList.toggle('on',ps[i].getAttribute('data-play')===VP.play);}
  var db=document.querySelectorAll('[data-vd]');
  for(i=0;i<db.length;i++){db[i].classList.toggle('on',db[i].getAttribute('data-vd')===VP.day);}
}
function showPlay(p){VP.play=p;vpApply();}
function showVD(d){VP.day=d;vpApply();}
function vpInit(){var c=document.querySelector('[data-vpday]');VP.day=c?c.getAttribute('data-vpday'):'';vpApply();}
function sortVD(d,m){
  var tb=document.getElementById('vt-'+d);
  if(!tb){return;}
  var rows=Array.prototype.slice.call(tb.querySelectorAll('tr.vrow'));
  rows.sort(function(a,b){
    if(m==='p'){var x=parseFloat(a.getAttribute('data-p'))||0,y=parseFloat(b.getAttribute('data-p'))||0;return y-x;}
    return _vdnum(a.getAttribute('data-num'))-_vdnum(b.getAttribute('data-num'));
  });
  for(var k=0;k<rows.length;k++){tb.appendChild(rows[k]);}
  var bs=document.querySelectorAll('#vd-'+d+' [data-vdm]');
  for(var j=0;j<bs.length;j++){bs[j].classList.toggle('on', bs[j].getAttribute('data-vdm')===m);}
}
function sortGT(d,m){
  var tb=document.getElementById('gv-'+d);
  if(!tb){return;}
  var rows=Array.prototype.slice.call(tb.querySelectorAll('tr.vg'));
  rows.sort(function(a,b){
    if(m==='p'){var x=parseFloat(a.getAttribute('data-gp'))||0,y=parseFloat(b.getAttribute('data-gp'))||0;return y-x;}
    return _vdnum(a.getAttribute('data-num'))-_vdnum(b.getAttribute('data-num'));
  });
  for(var k=0;k<rows.length;k++){tb.appendChild(rows[k]);}
  var bs=document.querySelectorAll('#vg-'+d+' [data-vgt]');
  for(var j=0;j<bs.length;j++){bs[j].classList.toggle('on', bs[j].getAttribute('data-vgt')===m);}
}
vpInit();
"""


def build_html(today, ordered, preds, rec, msgs, gen_time):
    # 记录本次预测并取历史验证数据(失败不影响出页)
    vdata = []
    try:
        verify.store(today.get("date") if today else None, ordered, preds, rec)
        vdata = verify.verify_all()
    except Exception:
        vdata = []

    # 复盘自调优: 用最新已核验结果更新 model_tune.json, 下一期预测即自动应用
    try:
        selftune.update_from_verify(
            vdata, ai=(deepseek_client.chat if deepseek_client.available() else None))
    except Exception:
        pass

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

    # 严格单关胆材(AI建议1) + 模型候选表(AI建议2过滤后)
    def _rowtr(c):
        f = c["feat"]
        return (f'<tr><td>{esc(f["num_str"])}</td><td>{esc(f["league_abb"])}</td>'
                f'<td>{esc(f["home"])} vs {esc(f["away"])}</td>'
                f'<td><b>{esc(c["pick"])}</b></td>'
                f'<td>{fmt_p(c["prob"])}</td>'
                f'<td>{c["odds"]:.2f}</td>'
                f'<td>{esc(f.get("data_quality", ""))}</td></tr>')
    banker_html = ""
    _bm = f"胜率≥{BANKER_MIN_PROB:.0%} 且 赔率≤{BANKER_MAX_ODDS:.2f}"
    if rec and rec.get("bankers"):
        inner = "".join(_rowtr(c) for c in rec["bankers"])
        banker_html = (f'<h2>🎯 严格单关胆材({esc(_bm)})</h2>'
                       '<div class="tbl"><table><tr><th>场次</th><th>联赛</th><th>对阵</th>'
                       f'<th>推荐</th><th>胜率</th><th>赔率</th><th>数据</th></tr>{inner}</table></div>')
    else:
        banker_html = (f'<div class="note">今日无符合严格单关胆材({esc(_bm)})的场次——'
                       '稳定优先, 不硬凑单关胆材(两串一仍按低风险档正常给出)。</div>')
    cand_html = ""
    if rec:
        pool = sorted(rec["candidates"], key=lambda c: c["prob"], reverse=True)
        cand_html = "".join(_rowtr(c) for c in pool[:12])

    # 全部场次预测表(三向概率 + 推荐): 生成两种排序(按场次/按胜率)
    def _prob_rows(pairs):
        s = ""
        for f, pr in pairs:
            s += (f'<tr><td>{esc(f["num_str"])}</td><td>{esc(f["league_abb"])}</td>'
                  f'<td>{esc(f["home"])} vs {esc(f["away"])}</td>'
                  f'<td>{fmt_p(pr["home"])}</td><td>{fmt_p(pr["draw"])}</td><td>{fmt_p(pr["away"])}</td>'
                  f'<td><b>{esc(pr["pick"])}</b></td>'
                  f'<td>{fmt_p(pr["pick_p"])}</td>'
                  f'<td>{esc(pr.get("pick_odds") or "-")}</td>'
                  f'<td>{esc(f.get("data_quality",""))}</td></tr>')
        return s
    _pairs = list(zip(ordered, preds))
    all_num_html = _prob_rows(sorted(_pairs, key=lambda x: x[0]["num_str"]))
    all_prob_html = _prob_rows(sorted(_pairs, key=lambda x: x[1]["pick_p"], reverse=True))

    # ⚽ 总进球预测(与胜负分开): 每场只给两种最可能进球数
    def _grow2(f, pr):
        g = pr.get("goals")
        if not g:
            return None
        p1, p2 = g.get("pick"), g.get("pick2")
        cand = (f'<b>{esc(p1)}球</b> / <b>{esc(p2)}球</b>' if p2
                else f'<b>{esc(p1)}球</b>')
        return (f'<tr><td>{esc(f["num_str"])}</td><td>{esc(f["league_abb"])}</td>'
                f'<td>{esc(f["home"])} vs {esc(f["away"])}</td>'
                f'<td>{cand}</td>'
                f'<td>{esc(f.get("data_quality", ""))}</td></tr>')
    _gpairs = [(f, pr) for f, pr in zip(ordered, preds) if pr.get("goals")]
    goals_tbl_html = "".join(
        x for x in (_grow2(f, pr) for f, pr in sorted(_gpairs, key=lambda q: q[0]["num_str"])) if x)

    metrics = (f'<div class="metric"><b>{total}</b><span>在售场次</span></div>'
               f'<div class="metric"><b>{len(ordered)}</b><span>可预测场次</span></div>'
               f'<div class="metric"><b>{full}</b><span>完整情报</span></div>'
               f'<div class="metric"><b>{parts}</b><span>部分情报</span></div>')

    verify_html = build_verify_html(vdata)
    self_html = build_self_html(vdata)
    daily_ai = _ai_daily_block(today, ordered, preds, rec)

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
<button class="tabbtn" data-tab="goals" onclick="showTab('goals')">⚽ 总进球</button>
<button class="tabbtn" data-tab="upset" onclick="showTab('upset')">⚠️ 爆冷雷达</button>
<button class="tabbtn" data-tab="verify" onclick="showTab('verify')">✅ 预测验证</button>
<button class="tabbtn" data-tab="self" onclick="showTab('self')">🧠 自我复盘</button>
<button class="tabbtn" data-tab="info" onclick="showTab('info')">ℹ️ 说明</button>
</div>

<section class="panel show" id="tab-combo">
<h2>🎯 两串一推荐(稳定优先·不足补齐)</h2>
<p class="mut">规则: 只串两关 · 串后赔率 ≥ 2.0 · 每腿胜率≥50% · 按稳定度从高到低排, 不足5组按稳定度补齐</p>
{daily_ai}
{combo_html}

{banker_html}
<h2>📈 模型候选(预测胜率 Top 12)</h2>
<p class="mut">稳定优先: 两腿都需 胜率≥50% 且 胜率差≥5%; 串关按稳定度(低风险优先)排, 不足5组时按稳定度补齐。</p>
<div class="tbl"><table><tr><th>场次</th><th>联赛</th><th>对阵</th><th>推荐</th>
<th>胜率</th><th>赔率</th><th>数据</th></tr>{cand_html}</table></div>
</section>

<section class="panel" id="tab-probs">
<h2>📊 全部场次概率</h2>
<p class="mut">每场 主胜 / 平 / 客胜 的模型概率与推荐</p>
<div class="tabbar" style="margin:8px 0">
<button class="tabbtn on" id="pb-num" onclick="showProbs('num')">🕑 按场次顺序</button>
<button class="tabbtn" id="pb-rate" onclick="showProbs('rate')">📈 按胜率高低</button>
</div>
<div id="probs-num">
<div class="tbl"><table><tr><th>场次</th><th>联赛</th><th>对阵</th>
<th>主胜</th><th>平局</th><th>客胜</th><th>推荐</th><th>胜率</th><th>赔率</th><th>数据</th>
</tr>{all_num_html}</table></div>
</div>
<div id="probs-rate" style="display:none">
<div class="tbl"><table><tr><th>场次</th><th>联赛</th><th>对阵</th>
<th>主胜</th><th>平局</th><th>客胜</th><th>推荐</th><th>胜率</th><th>赔率</th><th>数据</th>
</tr>{all_prob_html}</table></div>
</div>
</section>

<section class="panel" id="tab-goals">
<h2>⚽ 总进球预测(两种最可能进球数)</h2>
<p class="mut">每场只给出最可能的<b>两种总进球数</b>; 验证时命中其一即算中(与胜负分开)</p>
<div class="tbl"><table><tr><th>场次</th><th>联赛</th><th>对阵</th>
<th>两种最可能进球</th><th>数据</th>
</tr>{goals_tbl_html}</table></div>
</section>

<section class="panel" id="tab-upset">
{upset_html}
</section>

<section class="panel" id="tab-verify">
{verify_html}
</section>

<section class="panel" id="tab-self">
{self_html}
</section>

<section class="panel" id="tab-info">
<h2>ℹ️ 说明与免责</h2>
<div class="note">
<b>本页怎么用:</b> 点上方按钮切换——
「🎯 串关方案」看五大两串一与单场稳胆；「📊 全部概率」看每场胜平负三向概率；
「⚠️ 爆冷雷达」看大热翻车风险与原因；「✅ 预测验证」按日期查看逐场与串关验证；
「🧠 自我复盘」看多日命中率/概率校准与 AI 意见；「ℹ️ 说明」看数据来源与免责。
</div>
<div class="note">
<b>验证与自我调优:</b> 每期预测会自动存档, 当天完场后用<b>竞彩口径快源(okooo)</b>核验
(结果缓存于本地, 源临时不可用也不影响)。系统依据<b>已核验命中率 vs 预测概率</b>自动做温和校准
(如某方向长期被高估则下次小幅降权, 每方向最多 ±3%), 可由 DeepSeek 复核, 写入
<code>data/model_tune.json</code>, 自下一期预测起生效(见「🧠 自我复盘」的 ⚙️ 卡片)。
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


def build_verify_html(vdata):
    """把历史验证数据渲染成页面 HTML"""
    if not vdata:
        return ('<h2>✅ 预测验证 / 复盘</h2>'
                '<div class="note">还没有历史预测可验证。从今天起每次自动更新都会把当天预测存档，'
                '等当天比赛全部结束后即可在这里看到「预测 vs 实际」的复盘（命中率与回报）。</div>')
    # 玩法切换: 胜负/总进球 分开(都在预测验证里), 默认胜平负
    default = vdata[0]["date"]
    playbar = ('<div class="tabbar" style="margin:6px 0;flex-wrap:wrap" data-vpday="' + esc(default) + '">'
               '<button class="tabbtn on" data-play="spf" onclick="showPlay(\'spf\')">✅ 胜负(胜平负)验证</button>'
               '<button class="tabbtn" data-play="goals" onclick="showPlay(\'goals\')">⚽ 总进球验证</button></div>')
    btn_items = []
    for day in vdata:
        d = day["date"]
        on = " on" if d == default else ""
        btn_items.append(f'<button class="tabbtn{on}" data-vd="{esc(d)}" '
                         f'onclick="showVD(\'{esc(d)}\')">📅 {esc(d)}</button>')
    bar = ('<div class="tabbar" style="margin:10px 0;flex-wrap:wrap">'
           + "".join(btn_items) + '</div>')

    spf_blocks = []
    goal_blocks = []
    for day in vdata:
        rows, st = day["rows"], day["stats"]
        hit_rate = f"{st['rate']:.0%}" if st["rate"] is not None else "-"
        c_known = st.get("combo_known", 0)
        c_win = st.get("combo_win", 0)
        croi = st.get("combo_roi", 0.0)
        c_hit = f"{c_win}/{c_known}" if c_known else "—"
        croi_txt = f"+{croi:.2f}" if croi >= 0 else f"{croi:.2f}"
        summary = (
            f'<div class="metrics" style="grid-template-columns:repeat(auto-fit,minmax(118px,1fr))">'
            f'<div class="metric"><b>{st["total"]}</b><span>预测场次</span></div>'
            f'<div class="metric"><b>{st["verified"]}</b><span>可核验场次</span></div>'
            f'<div class="metric"><b>{st["hits"]}/{st["verified"]}</b><span>单场命中</span></div>'
            f'<div class="metric"><b>{hit_rate}</b><span>单场命中率</span></div>'
            f'<div class="metric"><b>{c_hit}</b><span>串关中(两组均中)</span></div>'
            f'<div class="metric"><b>{croi_txt}</b><span>串关净回报(5组各1注)</span></div></div>')
        trs = ""
        for r in rows:
            actual = r.get("actual")
            if actual is None:
                mark = f'<span style="color:var(--mut)">{esc(r["status"])}</span>'
            else:
                ok = r.get("hit")
                icon = "✅" if ok else "❌"
                col = "#0a7d3e" if ok else "#c0392b"
                sc = r.get("score")
                mark = f'<span style="color:{col};font-weight:700">{icon} {esc(actual)}</span>'
                if sc:
                    mark += f' <span class="mut">({esc(sc)})</span>'
            prob = r.get("probs") or []
            ptxt = (f"{fmt_p(prob[0])}/{fmt_p(prob[1])}/{fmt_p(prob[2])}"
                    if len(prob) == 3 else "-")
            _pi = {"主胜": 0, "平": 1, "客胜": 2}.get(r.get("pick"), 0)
            pv = (prob[_pi] if len(prob) == 3 else 0.0)
            trs += (f'<tr class="vrow" data-num="{esc(r["num"])}" data-p="{pv:.6f}">'
                    f'<td>{esc(r["num"])}</td><td>{esc(r["league"])}</td>'
                    f'<td>{esc(r["home"])} vs {esc(r["away"])}</td>'
                    f'<td><b>{esc(r["pick"])}</b></td><td>{ptxt}</td>'
                    f'<td>{esc(r["odds"] or "-")}</td><td>{mark}</td></tr>')
        c_txt = ""
        # ---- 串关方案验证明细(五组两串一, 逐组给出两场实际结果) ----
        rows_by_num = {r["num"]: r for r in rows}
        combo_html = ""
        if day.get("combos"):
            ctr = ""
            for ci, cb in enumerate(day["combos"], 1):
                legs_txt = []
                for leg in cb.get("legs", []):
                    rr = rows_by_num.get(leg["num"])
                    teams = f' {rr["home"]} vs {rr["away"]}' if rr else ""
                    act = leg.get("actual")
                    if act:
                        icon = "✅" if leg.get("ok") else "❌"
                        a = f'实际 <b>{esc(act)}</b> {icon}'
                    else:
                        a = '<span style="color:var(--mut)">待开奖</span>'
                    legs_txt.append(
                        f'{esc(leg["num"])}{esc(teams)}　预测 <b>【{esc(leg.get("pick", ""))}】</b>　{a}')
                if cb.get("known"):
                    if cb.get("win"):
                        res = '<b style="color:#0a7d3e">✅ 命中</b>'
                    else:
                        res = '<b style="color:#c0392b">❌ 未中</b>'
                else:
                    res = '<span style="color:var(--mut)">待开奖</span>'
                ctr += (f'<tr><td><b>方案{ci}</b></td>'
                        f'<td style="text-align:left">{"<br>".join(legs_txt)}</td>'
                        f'<td>{esc(cb.get("odds") or "-")}</td><td>{res}</td></tr>')
            combo_html = ('<h4>🎯 串关方案验证(五组两串一)</h4>'
                          '<div class="tbl"><table><tr><th>方案</th><th>两场(场次/预测/实际)</th>'
                          f'<th>串后赔率</th><th>结果</th></tr>{ctr}</table></div>')
        # ⚽ 总进球验证(与胜负分开)
        gv_rows = [r for r in rows if r.get("g_pick") is not None]
        goals_html = ""
        if gv_rows:
            gt = ""
            for r in gv_rows:
                p1, p2 = r.get("g_pick"), r.get("g_pick2")
                picktxt = (f'<b>{esc(p1)}球</b> / <b>{esc(p2)}球</b>' if p2
                           else f'<b>{esc(p1)}球</b>')
                if r.get("g_hit") is not None:
                    ok = r["g_hit"]
                    col = "#0a7d3e" if ok else "#c0392b"
                    res = (f'<span style="color:{col};font-weight:700">'
                           f'{"✅" if ok else "❌"} 实际{esc(r["g_actual"])}球</span>')
                else:
                    res = '<span style="color:var(--mut)">待开奖/无比分</span>'
                gpv = ("%.6f" % (r.get("g_p") or 0))
                gt += (f'<tr class="vg" data-num="{esc(r["num"])}" data-gp="{gpv}">'
                       f'<td>{esc(r["num"])}</td>'
                       f'<td>{esc(r["home"])} vs {esc(r["away"])}</td>'
                       f'<td>{picktxt}</td>'
                       f'<td>{esc(r.get("score") or "-")}</td>'
                       f'<td>{res}</td></tr>')
            gstat = ""
            if st.get("goals_n"):
                gstat = (f'<p class="mut">已核验 <b>{st["goals_n"]}</b> · 命中 '
                         f'<b>{st["goals_hits"]}</b>'
                         + (f' ({st["goals_rate"]:.0%})'
                            if st.get("goals_rate") is not None else '')
                         + '（两种候选命中其一即算中）</p>')
            gd = esc(day["date"])
            gbar = ('<div class="tabbar" style="margin:6px 0">'
                    f'<button class="tabbtn on" data-vgt="num" onclick="sortGT(\'{gd}\',\'num\')">🕑 场次顺序</button>'
                    f'<button class="tabbtn" data-vgt="p" onclick="sortGT(\'{gd}\',\'p\')">📈 按第一候选概率</button></div>')
            goals_html = ('<h4>⚽ 总进球验证(两种候选, 命中其一即中)</h4>' + gstat + gbar +
                          f'<div class="tbl"><table id="gv-{gd}"><tr><th>场次</th><th>对阵</th>'
                          f'<th>预测(两种球数)</th><th>全场比分</th><th>结果</th></tr>{gt}</table></div>')
        else:
            goals_html = ('<div class="note">该期未做总进球预测(自 09-06 起每期开始记录)。</div>')

        disp = "block" if day["date"] == default else "none"
        d_esc = esc(day["date"])
        sortbar = ('<div class="tabbar" style="margin:6px 0">'
                   f'<button class="tabbtn on" data-vdm="num" onclick="sortVD(\'{d_esc}\',\'num\')">🕑 场次顺序</button>'
                   f'<button class="tabbtn" data-vdm="p" onclick="sortVD(\'{d_esc}\',\'p\')">📈 按预测胜率</button></div>')
        # 胜平负视图(含串关验证)
        spf_blocks.append(
            f'<div class="vdbox" id="vd-{d_esc}" style="display:{disp}">'
            f'<h3>📅 {d_esc} 复盘</h3>{summary}{c_txt}'
            f'{sortbar}'
            f'<div class="tbl"><table id="vt-{d_esc}"><tr><th>场次</th><th>联赛</th><th>对阵</th>'
            f'<th>预测</th><th>主/平/客</th><th>赔率</th><th>实际结果</th></tr>'
            f'{trs}</table></div>'
            f'{combo_html}'
            '<div class="note">注: 赛果由竞彩口径快源(okooo, 与体彩同套场次/队名)自动核验,'
            '覆盖日职/韩职/挪超/巴甲/沙职等全部竞彩联赛; “待开奖”=尚未完场;'
            '“缺结果源”=本次自动更新时结果源暂不可达。命中只统计“已核验”场次。</div>'
            '</div>')
        # 总进球视图(与胜负分开, 单独统计)
        goal_blocks.append(
            f'<div id="vg-{d_esc}" style="display:none">'
            f'<h3>📅 {d_esc} · ⚽ 总进球验证</h3>{goals_html}'
            '</div>')
    return ('<h2>✅ 预测验证 / 复盘</h2>'
            '<p class="mut">先选玩法(胜负/总进球), 再用日期按钮切换查看某天</p>'
            + playbar + bar + "".join(spf_blocks) + "".join(goal_blocks))


def _fmt_row_pick(r):
    pp = r.get("probs") or []
    return (f"{fmt_p(pp[0])}/{fmt_p(pp[1])}/{fmt_p(pp[2])}" if len(pp) == 3 else "-")


def _card_rows(items):
    if not items:
        return ""
    html = ""
    for r in items[:4]:
        html += (f'<div class="card"><b>{esc(r["num"])} [{esc(r["league"])}] '
                 f'{esc(r["home"])} vs {esc(r["away"])}</b>　预测 <b>【{esc(r["pick"])}】</b>'
                 f'({_fmt_row_pick(r)}) · 实际 {esc(r.get("actual") or "-")} · '
                 f'赔率 {esc(r.get("odds") or "-")}</div>')
    return html


def _ai_self_block(agg):
    cache_path = os.path.join(DATA_DIR, "ai_cache.json")
    key_data = f'{len(agg.get("days") or [])}:{agg["total"]}:{agg["hits"]}'
    cache = {}
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass
    if key_data in cache:
        return ('<h2>🤖 DeepSeek AI 复盘</h2>'
                f'<div class="card"><div style="white-space:pre-wrap">{esc(cache[key_data])}</div></div>')
    if not deepseek_client.available():
        return ('<h2>🤖 AI 复盘(可选)</h2><div class="note">要生成 AI 复盘: 在 '
                '<code>jc_football/data/deepseek_key.txt</code> 粘贴 DeepSeek API Key 后保存并重新更新即可'
                '(Key 只在本机使用, 不会上传)。</div>')
    parts = [f"多日累计已核验 {agg['total']} 场, 命中 {agg['hits']} 场, 单场命中率 {agg['rate']:.1%}。"]
    bp = agg.get("by_pick", {})
    if bp:
        parts.append("按选项: " + ", ".join(f"{k} {v[1]}/{v[0]}" for k, v in bp.items()))
    bs = []
    for b in agg.get("buckets", []):
        flag = "正常" if not b["over"] else "低于区间下沿(略虚高)"
        bs.append(f"{b['lab']}: {b['hit']}/{b['n']} 实际{b['rate']:.0%}({flag})")
    if bs:
        parts.append("概率分桶: " + "; ".join(bs))
    if agg.get("combo_known"):
        parts.append(f"串关: 可判定{agg['combo_known']}组, 命中{agg['combo_win']}组, 净回报{agg['combo_net']:.2f}")
    if agg.get("miss_high"):
        m = []
        for r in agg["miss_high"][:3]:
            m.append(f"{r['league']}{r['home']}vs{r['away']}预测{r['pick']}(实际{r.get('actual')})")
        parts.append("高胜率翻车样例: " + "; ".join(m))
    if agg.get("coups"):
        c = []
        for r in agg["coups"][:3]:
            c.append(f"{r['league']}{r['home']}vs{r['away']}预测{r['pick']}命中(赔率{r.get('odds')})")
        parts.append("以小博大命中样例: " + "; ".join(c))
    prompt = ("请依据以下统计做中文自我复盘(不要编造数字, 不确定就直说):\n" + "\n".join(parts)
              + "\n请给出: 1)总体评价 2)主要问题(是否对大热过度乐观/平局难抓/样本不足等) "
              "3)2-3 条可执行改进建议(如提高做胆门槛、串关规避高爆冷风险场等)。300字内。")
    txt = deepseek_client.chat(prompt)
    if not txt:
        return ('<h2>🤖 AI 复盘(可选)</h2><div class="note">已配置 Key 但本次调用失败'
                '(网络/额度等)，已自动用规则版复盘代替。</div>')
    try:
        cache[key_data] = txt
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass
    return ('<h2>🤖 DeepSeek AI 复盘</h2>'
            f'<div class="card"><div style="white-space:pre-wrap">{esc(txt)}</div></div>')


def build_self_html(vdata):
    """🧠 模型自我复盘: 多日汇总 + 概率校准 + 翻车检讨 + (可选)DeepSeek AI"""
    agg = verify.aggregate(vdata) if vdata else {"total": 0}
    if not agg.get("total"):
        return ('<h2>🧠 模型自我复盘</h2>'
                '<div class="note">还没有可复盘数据。等出现已开奖场次后，这里会多日汇总：'
                '命中率 / 概率校准(预测 60% 是否真的约 60%) / 高胜率翻车检讨 / 以小博大 / 串关回报，'
                '并(可选)用 DeepSeek 生成 AI 复盘建议。</div>')
    days_n = len(set(agg.get("days") or []))
    total, hits = agg["total"], agg["hits"]
    rate = agg.get("rate") or 0.0
    ck, cw = agg.get("combo_known", 0), agg.get("combo_win", 0)
    cnet = agg.get("combo_net", 0.0)
    cnet_txt = f"+{cnet:.2f}" if cnet >= 0 else f"{cnet:.2f}"
    c_hit = f"{cw}/{ck}" if ck else "—"
    metrics = (
        f'<div class="metrics" style="grid-template-columns:repeat(auto-fit,minmax(120px,1fr))">'
        f'<div class="metric"><b>{days_n}</b><span>复盘天数</span></div>'
        f'<div class="metric"><b>{total}</b><span>已核验场次</span></div>'
        f'<div class="metric"><b>{hits}</b><span>命中</span></div>'
        f'<div class="metric"><b>{rate:.1%}</b><span>单场命中率</span></div>'
        f'<div class="metric"><b>{c_hit}</b><span>串关中</span></div>'
        f'<div class="metric"><b>{cnet_txt}</b><span>串关净回报</span></div></div>')
    by_txt = ""
    if agg.get("by_pick"):
        chips = "".join(f'<span class="pill" style="margin-right:6px">{esc(k)} {v[1]}/{v[0]}</span>'
                        for k, v in agg["by_pick"].items())
        by_txt = f'<p class="mut">按选项命中: {chips}</p>'
    brow = ""
    for b in agg.get("buckets", []):
        tag = "⚠ 略虚高" if b["over"] else "正常"
        col = "#c0392b" if b["over"] else "var(--green)"
        brow += (f'<tr><td>{b["lab"]}</td><td>{b["n"]}</td><td>{b["hit"]}</td>'
                 f'<td>{b["rate"]:.0%}</td><td style="color:{col}">{tag}</td></tr>')
    bucket_html = (""
                   if not brow else
                   '<h2>🎯 概率校准(预测概率 vs 实际命中)</h2>'
                   '<p class="mut">预测 60-70% 的场次若实际也接近 60-70%, 说明概率可信; '
                   '明显偏低表示对高概率有些“乐观”。</p>'
                   '<div class="tbl"><table><tr><th>预测区间</th><th>场次</th><th>命中</th>'
                   f'<th>实际命中率</th><th>判断</th></tr>{brow}</table></div>')
    miss_html = ""
    if agg.get("miss_high"):
        miss_html = ('<h2>📉 高胜率翻车检讨(预测≥60% 却打脸)</h2>' + _card_rows(agg["miss_high"]))
    coup_html = ""
    if agg.get("coups"):
        coup_html = ('<h2>💰 以小博大成功(≥2.0 赔率命中)</h2>' + _card_rows(agg["coups"]))
    ai_html = _ai_self_block(agg)

    # ⚙️ 模型自调优卡片: 显示复盘校准已应用到下次预测
    tune_card = ""
    try:
        t = selftune.load()
        tdesc = selftune.describe(t)
        if tdesc:
            extra = ''
            if t.get("ai_note"):
                extra = f'<p class="mut">🤖 DeepSeek 复盘意见: {esc(t["ai_note"])}</p>'
            tune_card = ('<h2>⚙️ 模型自调优(复盘已用于下次预测)</h2>'
                         '<div class="note"><b>' + esc(tdesc) + '</b>' + extra + '</div>')
    except Exception:
        tune_card = ""

    return (f"<h2>🧠 模型自我复盘(多日汇总)</h2>"
            f'<p class="mut">基于最近 {days_n} 个销售日已开奖场次的自动复盘</p>'
            f"{metrics}{by_txt}{tune_card}{bucket_html}{miss_html}{coup_html}{ai_html}")


def _ai_daily_block(today, ordered, preds, rec):
    """(可选) DeepSeek 今日胜率解读, 按销售日缓存; 未配 Key 或失败返回空"""
    sales = (today or {}).get("date")
    if not sales or not deepseek_client.available():
        return ""
    cache_path = os.path.join(DATA_DIR, "ai_cache.json")
    cache = {}
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass
    ckey = f"daily:{sales}"
    if ckey in cache:
        txt = cache[ckey]
    else:
        lines = [f"今日竞彩销售日 {sales}, 开胜平负可预测 {len(ordered)} 场。"]
        top = sorted(zip(ordered, preds), key=lambda x: x[1]["pick_p"], reverse=True)[:5]
        for f, pr in top:
            u = pr.get("upset") or {}
            extras = ""
            if u.get("hot"):
                extras = f"(大热不胜防冷 {u.get('no_win_p',0):.0%}, 风险[{u.get('risk')}])"
            lines.append(f"- {f['num_str']} {f['league_abb']} {f['home']}vs{f['away']}: "
                         f"推荐{pr['pick']} 胜率{pr['pick_p']:.0%} 赔率{pr.get('pick_odds')} "
                         f"数据{f.get('data_quality')} {extras}")
        prompt = ("请针对以上今日竞彩比赛做胜率解读(不编造数字, 只基于给到的信息): "
                  "哪些场较可放心做胆、哪些要防冷或回避、整体信心如何。250字内。\n"
                  + "\n".join(lines))
        txt = deepseek_client.chat(prompt, max_tokens=520)
        if not txt:
            return ""
        try:
            cache[ckey] = txt
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        except Exception:
            pass
    return ('<div class="note"><b>🤖 DeepSeek 今日胜率解读</b>'
            f'<div style="white-space:pre-wrap;margin-top:4px">{esc(txt)}</div></div>')


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
