"""静态比赛工作台：不联网、不调用 AI，所有外部文本均转义。"""
from html import escape
from pathlib import Path

from model import implied_from_odds

ASSETS = Path(__file__).parent / "ui"
QUALITY = {"full": "历史较完整", "partial": "部分历史", "odds_only": "仅赔率数据"}


def assets():
    return ((ASSETS / "dashboard.css").read_text(encoding="utf-8"),
            (ASSETS / "dashboard.js").read_text(encoding="utf-8"))


def esc(value):
    return escape(str(value or ""), quote=True)


def match_explorer(ordered, preds):
    leagues = sorted({f.get("league_abb") or "其他" for f in ordered})
    options = ''.join(f'<option value="{esc(x)}">{esc(x)}</option>' for x in leagues)
    cards = []
    for index, (f, pr) in enumerate(zip(ordered, preds)):
        probs = [pr[k] for k in ("home", "draw", "away")]
        labels = ["主胜", "平局", "客胜"]
        pick = max(range(3), key=lambda i: probs[i])
        market = implied_from_odds(*(f.get(k) for k in ("had_h", "had_d", "had_a")))
        risk = (pr.get("upset") or {}).get("risk", "低")
        league = f.get("league_abb") or "其他"
        quality = QUALITY.get(f.get("data_quality"), "数据待补充")
        qclass = "complete" if f.get("data_quality") == "full" else "limited"
        search = ' '.join(str(f.get(k) or '') for k in ("num_str", "home", "away", "league_abb"))
        bars = ''.join(f'<span class="segment s{i}" style="width:{p * 100:.4f}%"></span>'
                       for i, p in enumerate(probs))
        values = ''.join(f'<div class="prob-value {"selected" if i == pick else ""}">'
                         f'<span><i class="dot s{i}"></i>{labels[i]}</span><b>{p:.1%}</b></div>'
                         for i, p in enumerate(probs))
        edge = f'{(probs[pick] - market[pick]) * 100:+.1f} 个百分点' if market else '暂无基线'
        odds = pr.get("pick_odds")
        odds_text = f'{odds:.2f}' if isinstance(odds, (int, float)) else '—'
        history_share = pr.get("history_weight", 0)
        detail = ''.join(f'<p>{esc(f.get(k))}</p>' for k in
                         ("home_summary", "away_summary", "h2h_summary", "intel_note") if f.get(k))
        market_text = (' / '.join(f'{x:.1%}' for x in market)) if market else '无有效赔率'
        cards.append(f'''<tr class="match-card" data-search="{esc(search)}"
 data-league="{esc(league)}" data-risk="{esc(risk)}" data-prob="{pr['pick_p']}" data-index="{index}">
 <td>{esc(f.get('num_str'))}<br><span class="mut">{esc(league)}</span></td>
 <td><b>{esc(f.get('home'))} vs {esc(f.get('away'))}</b>
 <div class="match-meta"><time>{esc(f.get('date'))} {esc(str(f.get('time') or '')[:5])}</time></div>
 <details class="match-detail"><summary>预测依据 <span>{esc(pr['source'])}</span></summary>
 <div><p>市场基线（主 / 平 / 客）：{market_text}</p>
 <p>融合时历史模型占比 {history_share:.0%}；其后可能应用情报与复盘修正。</p>
 {detail}<p>与市场的差异不代表已验证的预测优势。</p></div></details></td>
 <td class="distribution"><div class="prob-values">{values}</div>
 <div class="prob-stack" role="img" aria-label="主胜 {probs[0]:.1%}，平局 {probs[1]:.1%}，客胜 {probs[2]:.1%}">{bars}</div></td>
 <td><b class="pick-label">{esc(pr['pick'])}</b><br>{pr['pick_p']:.1%} <span class="mut">@ {odds_text}</span>
 <div class="mut">较市场 {edge}</div></td>
 <td><span class="quality {qclass}">{quality}</span><br>
 <span class="risk risk-{esc(risk)}">风险 · {esc(risk)}</span></td></tr>''')
    return f'''<div class="section-heading"><div>
 <h2>📊 全部场次概率</h2><p class="mut">比较胜平负概率，查看每场预测的依据。</p></div>
 <span id="match-count" class="result-count" role="status" aria-live="polite">{len(cards)} 场比赛</span></div>
 <div class="match-toolbar" role="search" aria-label="筛选比赛">
 <label class="search-field"><span>搜索球队 / 场次</span><input id="match-search" type="search" placeholder="例如：主队名称或 001"></label>
 <label><span>联赛</span><select id="match-league"><option value="">全部联赛</option>{options}</select></label>
 <label><span>热门风险</span><select id="match-risk"><option value="">全部风险</option><option>低</option><option>中</option><option>高</option></select></label>
 <label><span>排序</span><select id="match-sort"><option value="index">场次顺序</option><option value="prob">首选概率优先</option></select></label>
 <button type="button" id="match-reset" class="reset-btn">重置</button></div>
 <div class="prob-legend"><span><i class="dot s0"></i>主胜</span><span><i class="dot s1"></i>平局</span>
 <span><i class="dot s2"></i>客胜</span><span class="mut">概率为模型估计，非确定结果</span></div>
 <div class="tbl"><table class="probability-table"><thead><tr><th>场次 / 联赛</th><th>对阵 / 依据</th>
 <th>主胜 / 平局 / 客胜</th><th>首选 / 概率 / 赔率</th><th>数据 / 风险</th></tr></thead>
 <tbody id="match-grid">{''.join(cards)}</tbody></table></div>
 <div id="match-empty" class="empty-state" {'' if not cards else 'hidden'}><b>暂无符合条件的比赛</b>
 <p>调整筛选条件，或在数据更新后查看。</p></div>'''
